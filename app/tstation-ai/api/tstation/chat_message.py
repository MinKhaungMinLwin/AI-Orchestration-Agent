"""
Chat Message API - CRUD operations for conversations via Redis.

Endpoints:
- POST /api/tstation/messages/chat - Chat with content only (history managed by service)
- GET /api/tstation/messages/sessions - List all sessions for user
- GET /api/tstation/messages/history/{session_id} - Get messages for a session
- DELETE /api/tstation/messages/{session_id} - Delete a session
- GET /api/tstation/messages/user-info - Get user info from JWT
- POST /api/tstation/messages/validate-token - Validate JWT token
"""
import asyncio
import json
import logging
import re
from urllib.parse import urlparse
import urllib.request
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from common.jwt_utils import TOKEN_EXPIRED_CODE, decode_jwt, is_jwt_payload_expired
from config.sec import get_api_key, security
from schemas.tstation.chat_message import (
    ChatMessageRequest,
    ChatMessageResponse,
    QuickOrderActionRequest,
    SessionListResponse,
    SessionInfo,
    ChatHistoryResponse,
    MessageResponse,
    UserInfoResponse,
    ValidateTokenResponse,
    DeleteSessionResponse,
    AppendMessageRequest,
    AppendMessageResponse,
)
from services.tstation.chat_history_service import get_chat_history_service
from services.tstation.chat import TStationChatServiceV2
from services.tstation.common.cta_urls import CTAUrls

logger = logging.getLogger(__name__)
router = APIRouter()

_TSTATION_ORIGIN_HOSTS = {
    "wwwqa.tstation.com",
    "mqa.tstation.com",
    "mbiz.tstation.com",
    "bizqa.tstation.com",
    "www.tstation.com",
    "m.tstation.com",
    "biz.tstation.com",
}


def _normalize_tstation_origin_host(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" in raw:
        host = urlparse(raw).hostname
    else:
        host = raw.split(",", 1)[0].split(":", 1)[0]
    host = (host or "").strip().lower()
    if host in _TSTATION_ORIGIN_HOSTS:
        return host
    return None


def _origin_host_from_request(request: Request) -> str | None:
    for header_name in ("origin", "referer", "x-forwarded-host", "host"):
        host = _normalize_tstation_origin_host(request.headers.get(header_name))
        if host:
            return host
    return None


def _log_task_error(task: asyncio.Task) -> None:
    if not task.cancelled() and (exc := task.exception()):
        logger.error("Background task %s failed: %s", task.get_name(), exc, exc_info=exc)

_LITELLM_REG_KEY = "litellm:registered:{user_id}"
_LITELLM_REG_TTL = 90 * 24 * 60 * 60  # 90 days


def _register_litellm_user(user_id: str) -> None:
    """Register user in LiteLLM budget system on first request.

    Cached in Redis for 90 days so the LiteLLM API is only called once per user.
    Failures are logged and ignored — chat continues normally regardless.
    """
    from config.env import settings
    from services.tstation.chat_history_service import get_redis_client

    redis = get_redis_client()
    cache_key = _LITELLM_REG_KEY.format(user_id=user_id)
    if redis.get(cache_key) is not None:
        return

    base = settings.AI_GATEWAY_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]

    payload = json.dumps({
        "user_id": user_id,
        "max_budget": settings.LITELLM_USER_MAX_BUDGET,
        "budget_duration": settings.LITELLM_USER_BUDGET_DURATION,
    }).encode()

    req = urllib.request.Request(
        f"{base}/user/new",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.AI_GATEWAY_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.getcode() in (200, 409):
                redis.setex(cache_key, _LITELLM_REG_TTL, "1")
                logger.info("[LITELLM] Registered user budget: %s ($%.2f/%s)",
                            user_id, settings.LITELLM_USER_MAX_BUDGET, settings.LITELLM_USER_BUDGET_DURATION)
    except Exception as exc:
        logger.warning("[LITELLM] Failed to register user %s: %s", user_id, exc)
        redis.setex(cache_key, 60, "0")  # back-off 60s to avoid retry storm on LiteLLM failure


_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _update_quota_score(user_id: str, tokens: int, trace_id: str, limit: int) -> None:
    from services.tstation.quota_service import add_monthly_tokens, post_langfuse_score
    new_total = add_monthly_tokens(user_id, tokens)
    logger.info("[QUOTA] %s: %d / %d tokens this month", user_id, new_total, limit)
    post_langfuse_score(
        trace_id, "monthly_tokens_used", float(new_total),
        f"{new_total:,} / {limit:,} tokens this month",
    )


def get_current_time() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _valid_tracing_id(value: str | None) -> str | None:
    """Langfuse trace IDs must be 32 lowercase hex chars."""
    if not value:
        return None
    if _TRACE_ID_RE.fullmatch(value):
        return value
    logger.warning("[CHAT_MESSAGE] Ignoring invalid tracing_id: %r", value)
    return None


def _ensure_session_owner(service, session_id: str, user_id: str) -> None:
    """Hide missing and cross-user sessions behind the same 404."""
    if not service.session_exists(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")


def _quick_order_action_event(message: str, *, metadata: dict | None = None) -> dict:
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_quick_order_action_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": [
                {"label": "주문 정보 다시 확인", "domain": "TRANSACTION"},
                {"label": "장바구니 확인", "domain": "TRANSACTION", "url": CTAUrls.CART},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": metadata or {},
        },
    }


def _quick_order_action_parse_booking_datetime(raw: str | None) -> tuple[str | None, str | None]:
    text = str(raw or "").strip()
    if not text:
        return None, None
    match = re.search(
        r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(?:\([^)]*\)\s*)?(\d{1,2})\s*(?::\s*\d{1,2}|시)?",
        text,
    )
    if not match:
        return None, None
    year, month, day, hour = (int(part) for part in match.groups())
    return f"{year:04d}{month:02d}{day:02d}", f"{hour:02d}"


def _latest_preorder_payload(history: list[dict]) -> dict:
    for message in reversed(history):
        template_data = message.get("template_data")
        if not isinstance(template_data, dict):
            continue
        if template_data.get("template") == "preOrder" and isinstance(template_data.get("data"), dict):
            return template_data["data"]
        if isinstance(template_data.get("orderInfo"), dict) and template_data.get("isReadyToOrder"):
            return template_data
    return {}


def _normalize_quick_order_action_payload(action_payload: dict, preorder_payload: dict) -> dict:
    metadata = preorder_payload.get("metadata") if isinstance(preorder_payload.get("metadata"), dict) else {}
    order_info = preorder_payload.get("orderInfo") if isinstance(preorder_payload.get("orderInfo"), dict) else {}
    payload = {**metadata, **action_payload}

    requested_cal_day = str(payload.get("requestedCalDay") or payload.get("requested_cal_day") or "").strip()
    rsv_hour = str(payload.get("rsvHour") or payload.get("rsv_hour") or "").strip()
    if not (requested_cal_day and rsv_hour):
        parsed_day, parsed_hour = _quick_order_action_parse_booking_datetime(
            payload.get("bookingDateTime") or order_info.get("bookingDateTime")
        )
        requested_cal_day = requested_cal_day or (parsed_day or "")
        rsv_hour = rsv_hour or (parsed_hour or "")

    raw_qty = payload.get("ordQty") or payload.get("ord_qty") or payload.get("quantity") or order_info.get("quantity")
    raw_amount = payload.get("paymentAmount") or payload.get("payment_amount") or order_info.get("paymentAmount")
    normalized: dict[str, object] = {
        "goods_no": str(payload.get("goodsNo") or payload.get("goodsId") or payload.get("goods_no") or "").strip(),
        "shop_id": str(payload.get("shopId") or payload.get("shop_id") or "").strip(),
        "requested_cal_day": requested_cal_day,
        "rsv_hour": str(rsv_hour).split(":", 1)[0].zfill(2) if rsv_hour else "",
        "car_no": str(payload.get("carNo") or payload.get("car_no") or "").strip(),
        "car_lnc_cd": str(payload.get("carLncCd") or payload.get("car_lnc_cd") or "").strip(),
        "product_name": str(payload.get("productName") or order_info.get("product") or "").strip(),
        "tire_size": str(payload.get("tireSize") or "").strip(),
        "store_name": str(payload.get("storeName") or payload.get("shopName") or order_info.get("storeName") or "").strip(),
        "booking_datetime": str(payload.get("bookingDateTime") or order_info.get("bookingDateTime") or "").strip(),
    }
    try:
        normalized["ord_qty"] = int(raw_qty or 0)
    except (TypeError, ValueError):
        normalized["ord_qty"] = 0
    try:
        normalized["payment_amount"] = int(raw_amount or 0)
    except (TypeError, ValueError):
        normalized["payment_amount"] = 0
    return normalized


def _validate_quick_order_action_payload(normalized: dict, preorder_payload: dict) -> tuple[bool, str]:
    required = ("goods_no", "shop_id", "requested_cal_day", "rsv_hour")
    missing = [field for field in required if not normalized.get(field)]
    if int(normalized.get("ord_qty") or 0) <= 0:
        missing.append("ord_qty")
    if missing:
        return False, "missing:" + ",".join(missing)

    metadata = preorder_payload.get("metadata") if isinstance(preorder_payload.get("metadata"), dict) else {}
    order_info = preorder_payload.get("orderInfo") if isinstance(preorder_payload.get("orderInfo"), dict) else {}
    expected_goods_no = str(metadata.get("goodsNo") or metadata.get("goodsId") or "").strip()
    expected_shop_id = str(metadata.get("shopId") or "").strip()
    if expected_goods_no and expected_goods_no != normalized.get("goods_no"):
        return False, "goods_no_mismatch"
    if expected_shop_id and expected_shop_id != normalized.get("shop_id"):
        return False, "shop_id_mismatch"

    expected_amount_raw = metadata.get("paymentAmount") or order_info.get("paymentAmount")
    try:
        expected_amount = int(expected_amount_raw or 0)
    except (TypeError, ValueError):
        expected_amount = 0
    payment_amount = int(normalized.get("payment_amount") or 0)
    if expected_amount and payment_amount:
        tolerance = max(1000, int(expected_amount * 0.1))
        if abs(expected_amount - payment_amount) > tolerance:
            return False, "payment_amount_mismatch"
    return True, "ok"


def _dict_tool_result(raw_result) -> dict:
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
            return parsed if isinstance(parsed, dict) else {"status": "success", "data": parsed}
        except json.JSONDecodeError:
            return {"status": "success", "data": raw_result}
    return {"status": "success", "data": raw_result}


def _append_should_route_to_chat(request: AppendMessageRequest) -> bool:
    if request.role != "user":
        return False
    if request.ui_action or request.chip_context or request.slots or request.user_info or request.tracing_id:
        return True
    template_data = request.template_data if isinstance(request.template_data, dict) else {}
    if not template_data:
        return False
    for key in ("ui_action", "chip_context", "slots", "user_info", "tracing_id"):
        value = template_data.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    metadata = template_data.get("metadata")
    if isinstance(metadata, dict):
        nested_ui_action = metadata.get("ui_action")
        nested_slots = metadata.get("slots")
        if isinstance(nested_ui_action, dict) and nested_ui_action:
            return True
        if isinstance(nested_slots, dict) and nested_slots:
            return True
    return False


def _append_request_to_chat_body(request: AppendMessageRequest) -> ChatMessageRequest:
    template_data = request.template_data if isinstance(request.template_data, dict) else {}
    chip_context = request.chip_context
    template_chip_context = template_data.get("chip_context")
    if chip_context is None and isinstance(template_chip_context, dict):
        chip_context = template_chip_context

    template_metadata = template_data.get("metadata")
    template_ui_action = template_data.get("ui_action")
    template_slots = template_data.get("slots")
    metadata_ui_action = template_metadata.get("ui_action") if isinstance(template_metadata, dict) else None
    metadata_slots = template_metadata.get("slots") if isinstance(template_metadata, dict) else None

    return ChatMessageRequest(
        content=request.content,
        session_id=request.session_id,
        stream=False,
        user_info=request.user_info or template_data.get("user_info"),
        tracing_id=request.tracing_id or template_data.get("tracing_id"),
        chip_context=chip_context,
        ui_action=request.ui_action or template_ui_action or metadata_ui_action,
        slots=request.slots or template_slots or metadata_slots,
    )


@router.post("/chat", dependencies=[Depends(get_api_key)])
async def chat(chat_body: ChatMessageRequest, http_request: Request, user: dict = Security(get_api_key)):
    """
    Chat endpoint - only content, history managed by service via Redis.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Request:
        - session_id (str): Session ID (required)
        - content (str): Message content
        - stream (bool): default is False

    - Response:
        - session_id (str): Session ID
        - message_id (str): User message ID
        - role (str): "user"
        - content (str): Echo of user message
        - created_at (str): Timestamp
    """
    # user is already the decoded JWT payload
    user_id = user.get("user_id")

    # Register user in LiteLLM budget system on first request (fire-and-forget)
    if user_id:
        asyncio.create_task(asyncio.to_thread(_register_litellm_user, user_id)).add_done_callback(_log_task_error)

    # Always generate a trace ID so Langfuse scores are linkable
    tracing_id = _valid_tracing_id(chat_body.tracing_id) or uuid.uuid4().hex

    # ── Monthly token quota check ──────────────────────────────────────────────
    if user_id:
        from config.env import settings
        from services.tstation.quota_service import is_quota_exceeded, get_monthly_tokens, post_langfuse_score
        if is_quota_exceeded(user_id, settings.MONTHLY_TOKEN_LIMIT):
            current = get_monthly_tokens(user_id)
            post_langfuse_score(
                tracing_id, "quota_blocked", 1.0,
                f"Blocked: {current:,} / {settings.MONTHLY_TOKEN_LIMIT:,} tokens this month"
            )
            logger.warning("[QUOTA] %s blocked — %d / %d tokens", user_id, current, settings.MONTHLY_TOKEN_LIMIT)
            raise HTTPException(
                status_code=429,
                detail="이번 달 토큰 한도를 초과했어요. 다음 달 1일에 초기화됩니다. 🙏",
            )

    service = get_chat_history_service()

    # Redis client is sync; run hot-path calls in worker threads so FastAPI's event loop stays free.
    session_id = await asyncio.to_thread(service.get_or_create_session_id, chat_body.session_id, user_id)
    msg_id = await asyncio.to_thread(service.save_message, session_id, "user", chat_body.content, user_id=user_id)
    history = await asyncio.to_thread(service.get_history_for_llm, session_id)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Add current user message only if not duplicate of last history
    if not (messages and messages[-1].get("role") == "user" and messages[-1].get("content") == chat_body.content):
        messages.append({"role": "user", "content": chat_body.content})

    # Prepare request for chat service
    from schemas.tstation.chat import TStationChatRequest
    from schemas.tstation.chat import TStationChatResponse

    chat_request = TStationChatRequest(
        messages=messages,
        stream=chat_body.stream,
        user_id=user_id,
        session_id=session_id,
        access_token=user["token"],
        origin_host=_origin_host_from_request(http_request),
        user_info=chat_body.user_info,
        chip_context=chat_body.chip_context.model_dump() if chat_body.chip_context else None,
        ui_action=chat_body.ui_action,
        slots=chat_body.slots,
        metadata={"message_id": msg_id},
        **({"tracing_id": tracing_id} if tracing_id else {}),
    )

    # ── Token quota increment (fire-and-forget) ───────────────────────────────
    if user_id:
        from services.tstation.quota_service import estimate_tokens
        from config.env import settings
        input_tokens = estimate_tokens(chat_body.content)
        output_estimate = 400  # conservative avg response size in tokens
        asyncio.create_task(asyncio.to_thread(
            _update_quota_score, user_id, input_tokens + output_estimate,
            tracing_id, settings.MONTHLY_TOKEN_LIMIT,
        )).add_done_callback(_log_task_error)

    # Call chat service
    if chat_body.stream:
        from services.tstation.chat_history_service import get_async_redis_client
        _redis = get_async_redis_client()
        _streaming_key = _STREAMING_KEY.format(session_id)
        if not await _redis.set(_streaming_key, "1", nx=True, ex=_STREAMING_TTL):
            raise HTTPException(status_code=409, detail="session_busy")
        return StreamingResponse(
            stream_chat_response(chat_request, session_id, msg_id, service),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-stream mode
    from services.tstation.chat_history_service import get_async_redis_client
    _redis = get_async_redis_client()
    _session_key = _STREAMING_KEY.format(session_id)
    if not await _redis.set(_session_key, "1", nx=True, ex=_STREAMING_TTL):
        raise HTTPException(status_code=409, detail="session_busy")
    try:
        response = await TStationChatServiceV2.chat(chat_request)
    finally:
        await _redis.delete(_session_key)

    if isinstance(response, TStationChatResponse):
        # Save assistant response to history without blocking the event loop.
        await asyncio.to_thread(service.save_message, session_id, "assistant", response.content, user_id=user_id)

        return ChatMessageResponse(
            session_id=session_id,
            message_id=msg_id,
            role="user",
            content=chat_body.content,
            created_at=get_current_time(),
        )

    raise HTTPException(status_code=500, detail="Unexpected response type")


_STREAMING_KEY = "chat:streaming:{}"
_ABORT_KEY = "chat:abort:{}"
_STREAMING_TTL = 120  # seconds


async def stream_chat_response(chat_request, session_id: str, user_msg_id: str, service):
    """Stream chat response and save assistant messages as they arrive."""
    from services.tstation.chat import TStationChatServiceV2
    from services.tstation.chat_history_service import get_async_redis_client

    _redis = get_async_redis_client()
    _streaming_key = _STREAMING_KEY.format(session_id)
    _abort_key = _ABORT_KEY.format(session_id)

    full_assistant_content = ""
    assistant_response_ui = None
    template_data = None

    try:
        stream_response = await TStationChatServiceV2.chat(chat_request)

        initial_response = {
            "session_id": session_id,
            "message_id": user_msg_id,
            "role": "user",
            "content": chat_request.messages[-1]["content"],
            "created_at": get_current_time(),
            "stream_started": True,
        }
        yield f"data: {json.dumps(initial_response, ensure_ascii=False)}\n\n"

        chunk_count = 0
        async for chunk in stream_response.body_iterator:
            chunk_count += 1
            if chunk_count % 5 == 0 and await _redis.exists(_abort_key):
                await _redis.delete(_abort_key)
                logger.info("[CHAT_MESSAGE] Stream aborted by client: %s", session_id)
                yield f"data: {json.dumps({'type': 'aborted'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            if chunk.strip().startswith("data: "):
                data_str = chunk.strip()[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    yield chunk
                    continue

                if event.get("type") == "data":
                    event_data = event.get("data", {})
                    if event.get("assistantResponse"):
                        assistant_response_ui = event["assistantResponse"]
                    elif event_data.get("assistantResponse"):
                        assistant_response_ui = event_data["assistantResponse"]
                    if assistant_response_ui:
                        logger.debug(f"[CHAT_MESSAGE] Captured assistantResponse from UI Template: {assistant_response_ui[:50]}...")
                    template_data = event
                    logger.debug(f"[CHAT_MESSAGE] Captured template_data: type={template_data.get('type')}, template={template_data.get('template')}")

                if event.get("type") == "qc_correction" and event.get("assistantResponse"):
                    assistant_response_ui = event["assistantResponse"]
                    logger.debug(f"[CHAT_MESSAGE] QC correction applied: {assistant_response_ui[:50]}...")

                if event.get("type") == "message" and event.get("content"):
                    content = event.get("content", "")
                    if content:
                        full_assistant_content += content

            yield chunk

        message_to_save = assistant_response_ui if assistant_response_ui else full_assistant_content
        if message_to_save:
            logger.debug(
                "[CHAT_MESSAGE] Saving assistant message"
                + (" with template_data" if template_data else "")
                + f": {message_to_save[:50]}..."
            )

            from services.tstation.history_summarizer import refresh_summary
            asyncio.create_task(asyncio.to_thread(
                service.save_message,
                session_id,
                "assistant",
                message_to_save,
                template_data=template_data,
                user_id=chat_request.user_id,
            )).add_done_callback(_log_task_error)
            asyncio.create_task(refresh_summary(session_id)).add_done_callback(_log_task_error)

        yield "data: [DONE]\n\n"

    finally:
        await _redis.delete(_streaming_key)


@router.post("/actions/quick-order", dependencies=[Depends(get_api_key)])
async def quick_order_action(
    action_body: QuickOrderActionRequest,
    http_request: Request,
    user: dict = Security(get_api_key),
):
    """Execute a ready preOrder CTA as a structured action without LLM/router."""
    user_id = user.get("user_id")
    service = get_chat_history_service()
    await asyncio.to_thread(_ensure_session_owner, service, action_body.session_id, user_id)

    from services.tstation.chat_history_service import get_async_redis_client

    _redis = get_async_redis_client()
    _streaming_key = _STREAMING_KEY.format(action_body.session_id)
    if not await _redis.set(_streaming_key, "1", nx=True, ex=_STREAMING_TTL):
        raise HTTPException(status_code=409, detail="session_busy")

    action_id = str(action_body.message_id or uuid.uuid4().hex)
    dedup_key = f"chat:action:quick_order:{action_body.session_id}:{action_id}"
    if not await _redis.set(dedup_key, "1", nx=True, ex=120):
        await _redis.delete(_streaming_key)
        raise HTTPException(status_code=409, detail="duplicate_action")

    user_msg_id = await asyncio.to_thread(
        service.save_message,
        action_body.session_id,
        "user",
        "주문하기",
        user_id=user_id,
    )

    async def _stream():
        assistant_response = ""
        template_data = None
        try:
            from services.tstation.common.tstation_be_client import set_tstation_be_token, set_tstation_origin_host

            set_tstation_be_token(user.get("token"))
            set_tstation_origin_host(_origin_host_from_request(http_request))

            initial_response = {
                "session_id": action_body.session_id,
                "message_id": user_msg_id,
                "role": "user",
                "content": "주문하기",
                "created_at": get_current_time(),
                "stream_started": True,
            }
            yield f"data: {json.dumps(initial_response, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'agent_flow', 'agent': '[응답 생성 중]', 'status': 'processing'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[TRANSACTION AGENT]', 'status': 'start'}, ensure_ascii=False)}\n\n"

            history = await asyncio.to_thread(service.get_history, action_body.session_id)
            preorder_payload = _latest_preorder_payload(history)
            normalized = _normalize_quick_order_action_payload(action_body.payload.model_dump(), preorder_payload)
            valid, reason = _validate_quick_order_action_payload(normalized, preorder_payload)
            if action_body.action != "quick_order_execute":
                valid, reason = False, "unsupported_action"
            if not valid:
                event = _quick_order_action_event(
                    "주문 정보를 다시 확인해 주세요.",
                    metadata={
                        "action": "quick_order_execute",
                        "router_skipped": True,
                        "source": "preOrder_action",
                        "validationReason": reason,
                    },
                )
                template_data = event
                assistant_response = event["data"]["assistantResponse"]
                yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[TRANSACTION AGENT]', 'status': 'done'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'message', 'content': assistant_response, 'agent': '[TRANSACTION AGENT]'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            tool_input = {
                "goods_no": str(normalized["goods_no"]),
                "ord_qty": int(normalized["ord_qty"]),
                "shop_id": str(normalized["shop_id"]),
                "rsv_date": str(normalized["requested_cal_day"]),
                "rsv_hour": str(normalized["rsv_hour"]),
            }
            if normalized.get("car_lnc_cd"):
                tool_input["car_lnc_cd"] = str(normalized["car_lnc_cd"])
            status_event = {
                "type": "status",
                "status": "tool_start",
                "tool": "quick_order_tool",
                "display_name": "주문서 생성 중...",
                "source_domain": "transaction",
            }
            yield f"data: {json.dumps(status_event, ensure_ascii=False)}\n\n"

            from services.tstation.agents.c_transaction_agent.tools import quick_order_tool
            from services.tstation.template_mapper import try_build_template

            try:
                raw_result = await asyncio.to_thread(quick_order_tool.invoke, tool_input)
                quick_order_result = _dict_tool_result(raw_result)
            except Exception as exc:
                logger.exception("[QUICK_ORDER_ACTION] quick_order_tool failed: %s", exc)
                quick_order_result = {"status": "error", "http_status": None, "message": str(exc), "data": {}}

            agent_flow_event = {
                "type": "agent_flow",
                "agent": "[Quick Shopping AF]",
                "agent_class": "Transaction Agent",
                "status": quick_order_result.get("status", "success"),
                "source_domain": "transaction",
            }
            tool_event = {
                "type": "tool",
                "input": tool_input,
                "output": json.dumps(quick_order_result, ensure_ascii=False),
                "node": "tools",
                "tool": "quick_order_tool",
                "source_domain": "transaction",
            }
            yield f"data: {json.dumps(agent_flow_event, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(tool_event, ensure_ascii=False)}\n\n"

            event = try_build_template(
                [{"tool": "quick_order_tool", "args": tool_input, "data": quick_order_result}],
                "",
            )
            if event is None:
                event = _quick_order_action_event(
                    "주문서 생성에 실패했어요. 주문 정보를 다시 확인해 주세요.",
                    metadata={
                        "action": "quick_order_execute",
                        "router_skipped": True,
                        "source": "preOrder_action",
                        "called_tools": ["quick_order_tool"],
                    },
                )
            event.setdefault("source_domain", "transaction")
            event.setdefault("assistant_response_source", "code_quick_order_action")
            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
            metadata = event_data.setdefault("metadata", {}) if isinstance(event_data, dict) else {}
            if isinstance(metadata, dict):
                metadata.update({
                    "action": "quick_order_execute",
                    "router_skipped": True,
                    "source": "preOrder_action",
                    "called_tools": ["quick_order_tool"],
                })
            assistant_response = str(event_data.get("assistantResponse") or "")
            template_data = event

            yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[TRANSACTION AGENT]', 'status': 'done'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if assistant_response:
                yield f"data: {json.dumps({'type': 'message', 'content': assistant_response, 'agent': '[TRANSACTION AGENT]'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await _redis.delete(_streaming_key)
            if assistant_response:
                from services.tstation.history_summarizer import refresh_summary

                asyncio.create_task(asyncio.to_thread(
                    service.save_message,
                    action_body.session_id,
                    "assistant",
                    assistant_response,
                    template_data=template_data,
                    user_id=user_id,
                )).add_done_callback(_log_task_error)
                asyncio.create_task(refresh_summary(action_body.session_id)).add_done_callback(_log_task_error)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", dependencies=[Depends(get_api_key)], response_model=SessionListResponse)
async def list_sessions(user: dict = Security(get_api_key)):
    """
    List all sessions for the current user.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - sessions (list): List of SessionInfo
        - total (int): Total number of sessions
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()
    sessions = await asyncio.to_thread(service.list_sessions, user_id)

    return SessionListResponse(
        sessions=[SessionInfo(**s) for s in sessions],
        total=len(sessions),
    )


@router.get("/history/{session_id}", dependencies=[Depends(get_api_key)], response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    user: dict = Security(get_api_key),
):
    """
    Get chat history for a session.

    Parameters:

    - Path:
        - session_id (str): Session ID

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - session_id (str): Session ID
        - total (int): Total number of messages
        - messages (list): List of MessageResponse
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()
    await asyncio.to_thread(_ensure_session_owner, service, session_id, user_id)

    messages = await asyncio.to_thread(service.get_history, session_id)

    return ChatHistoryResponse(
        session_id=session_id,
        total=len(messages),
        messages=[MessageResponse(**msg) for msg in messages],
    )


@router.post("/append", dependencies=[Depends(get_api_key)], response_model=AppendMessageResponse | ChatMessageResponse)
async def append_message(
    request: AppendMessageRequest,
    http_request: Request,
    user: dict = Security(get_api_key),
):
    """
    Append a message to chat history (without AI processing).

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Request:
        - session_id (str): Session ID
        - content (str): Message content
        - role (str): "user" or "assistant" (default "user")
        - template_data (dict): Optional template data for assistant messages

    - Response:
        - success (bool): Append success flag
        - session_id (str): Session ID
        - msg_id (str): Created message ID
        - role (str): Message role
        - created_at (str): Created timestamp
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()

    await asyncio.to_thread(_ensure_session_owner, service, request.session_id, user_id)

    # Validate role
    if request.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'assistant'")

    if _append_should_route_to_chat(request):
        return await chat(_append_request_to_chat_body(request), http_request, user)

    # Append message (saved at end due to timestamp score)
    msg_id = await asyncio.to_thread(
        service.save_message,
        session_id=request.session_id,
        role=request.role,
        content=request.content,
        template_data=request.template_data,
        user_id=user_id,
    )

    return AppendMessageResponse(
        success=True,
        session_id=request.session_id,
        msg_id=msg_id,
        role=request.role,
        created_at=get_current_time(),
    )


@router.post("/{session_id}/abort", dependencies=[Depends(get_api_key)])
async def abort_stream(session_id: str, user: dict = Security(get_api_key)):
    """
    Abort an active streaming response for a session.

    Returns {"aborted": true} if a stream was cancelled, {"aborted": false} if no active stream.
    """
    user_id = user.get("user_id")
    service = get_chat_history_service()
    await asyncio.to_thread(_ensure_session_owner, service, session_id, user_id)

    from services.tstation.chat_history_service import get_async_redis_client
    _redis = get_async_redis_client()
    _streaming_key = _STREAMING_KEY.format(session_id)
    _abort_key = _ABORT_KEY.format(session_id)

    if not await _redis.exists(_streaming_key):
        return {"aborted": False, "session_id": session_id}

    await _redis.set(_abort_key, "1", ex=30)
    return {"aborted": True, "session_id": session_id}


@router.delete("/{session_id}", dependencies=[Depends(get_api_key)], response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    user: dict = Security(get_api_key),
):
    """
    Delete a session and all its messages.

    Parameters:

    - Path:
        - session_id (str): Session ID to delete

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - success (bool): True if deleted
        - session_id (str): Deleted session ID
        - messages_deleted (int): Number of messages deleted
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()

    await asyncio.to_thread(_ensure_session_owner, service, session_id, user_id)

    messages_deleted = await asyncio.to_thread(service.delete_session, session_id)

    return DeleteSessionResponse(
        success=True,
        session_id=session_id,
        messages_deleted=messages_deleted,
    )


@router.get("/user-info", dependencies=[Depends(get_api_key)], response_model=UserInfoResponse)
async def get_user_info(user: dict = Security(get_api_key)):
    """
    Get user info from JWT token.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - user_id (str): User ID
        - user_type (str): User type
        - affiliate_yn (str): Affiliate flag
        - issued_at (str): Token issued timestamp
        - expire_at (str): Token expiration timestamp
    """
    # credentials is already the decoded user payload
    # Exclude token from user dict before returning
    user_data = {k: v for k, v in user.items() if k != "token"}
    return UserInfoResponse(**user_data)


@router.post("/validate-token", response_model=ValidateTokenResponse)
async def validate_token_endpoint(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Validate JWT token.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token to validate

    - Response:
        - valid (bool): True if token is valid
        - user_id (str): User ID if valid
        - reason (str): Reason if invalid
    """
    if not credentials:
        return ValidateTokenResponse(valid=False, reason="Missing token")

    payload = decode_jwt(credentials.credentials)
    user_id = payload.get("user_id") if payload else None
    if not user_id:
        return ValidateTokenResponse(valid=False, reason="Invalid token")
    try:
        if is_jwt_payload_expired(payload):
            return ValidateTokenResponse(valid=False, user_id=user_id, reason=TOKEN_EXPIRED_CODE)
    except ValueError:
        return ValidateTokenResponse(valid=False, user_id=user_id, reason="Invalid token expiration")
    return ValidateTokenResponse(valid=True, user_id=user_id)
