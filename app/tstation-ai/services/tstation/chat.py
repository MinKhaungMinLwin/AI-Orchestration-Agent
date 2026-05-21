import asyncio
import concurrent.futures
import datetime
import json
import threading
import logging
import re
import time
from typing import Any, AsyncIterator, ClassVar, Iterator
from textwrap import dedent

from pydantic import BaseModel, Field
from enum import Enum

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.common.tstation_be_client import set_tstation_be_token
from config.env import settings
from config.prompts import load_client_injection
from fastapi.responses import StreamingResponse
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.router import (
    DECISION_LLM as _decision_llm,
    leading_agent,
    discovery_subagent,
    transaction_subagent,
    support_subagent,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time
from services.tstation.common.pii_guardrail import check_pii, GUARDRAIL_RESPONSE

from services.tstation.source_filter import filter_source_data, filter_for_context
from services.tstation import qc_verifier
from services.tstation.classifier_feedback import log_classifier_redirect
from config.tracing import (
    build_trace_config,
    trace_span as _trace_span,
    truncate_for_trace as _truncate,
    _tracing_enabled,
    tracer,
    set_trace_name as _set_trace_name,
)

logger = logging.getLogger(__name__)


class NextAction(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


class AgentDecision(BaseModel):
    next_action: NextAction = Field(description="STOP or CONTINUE")
    next_domain: str = Field(description="Next domain if CONTINUE ('null' if STOP)")
    reason: str = Field(description="Reason for decision, using english")


class AgentPromptProfile(str, Enum):
    FULL = "full"
    TRANSACTION_COUPON = "transaction_coupon"
    TRANSACTION_ORDER = "transaction_order"
    TRANSACTION_STORE = "transaction_store"
    TRANSACTION_PRICE_STOCK = "transaction_price_stock"
    DISCOVERY_SEARCH = "discovery_search"
    DISCOVERY_RECOMMENDATION = "discovery_recommendation"
    DISCOVERY_EVENT_CONTENT = "discovery_event_content"


# Module-level singleton: avoid re-creating LLM client + structured-output wrapper per request.
_decision_structured_model = _decision_llm.with_structured_output(AgentDecision)
_speculative_classify_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_speculative_classify_sem = threading.Semaphore(4)
_decision_verify_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_DISCOVERY_PROFILE_CLASSIFIER_TIMEOUT_S = 0.15
_SYNC_ITER_SENTINEL = object()


def _try_submit_speculative(fn, *args, **kwargs) -> concurrent.futures.Future | None:
    """Submit fn to speculative executor only if a worker is immediately available.

    Returns None when all workers are busy so callers fall back to the non-speculative
    path rather than growing the internal queue unbounded under high load.
    """
    if not _speculative_classify_sem.acquire(blocking=False):
        return None

    def _run():
        try:
            return fn(*args, **kwargs)
        finally:
            _speculative_classify_sem.release()

    return _speculative_classify_executor.submit(_run)


def _next_or_sentinel(iterator: Iterator[dict]) -> dict | object:
    """Advance a sync generator in a worker thread without leaking StopIteration."""
    try:
        return next(iterator)
    except StopIteration:
        return _SYNC_ITER_SENTINEL


async def _async_from_sync_iter(iterator: Iterator[dict]) -> AsyncIterator[dict]:
    """Bridge blocking sync agent streams into async SSE without blocking the event loop."""
    while True:
        item = await asyncio.to_thread(_next_or_sentinel, iterator)
        if item is _SYNC_ITER_SENTINEL:
            break
        yield item


def _parse_agent_declared_next_action(payload: object) -> AgentDecision | None:
    """Normalize agent-emitted nextAction payload into AgentDecision."""
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("type", "")).strip().lower()
    reason = "agent_declared_next_action"
    if action == NextAction.STOP.value:
        if payload.get("domain") is not None:
            return None
        return AgentDecision(next_action=NextAction.STOP, next_domain="null", reason=reason)
    if action != NextAction.CONTINUE.value:
        return None
    domain = str(payload.get("domain", "")).strip().lower()
    if domain not in {"discovery", "transaction", "support"}:
        return None
    return AgentDecision(next_action=NextAction.CONTINUE, next_domain=domain, reason=reason)


def prompt_router() -> str:
    return dedent("""
    You are a domain classifier and decision engine for T-Station AI.

    MODE 1 - Initial Classification: Classify user message into ONE domain.
    MODE 2 - Next Action Decision: After agent completes, decide STOP or CONTINUE.

    DOMAINS:
    - LEADING: Greeting, unclear intent
    - DISCOVERY: Product search, recommendations, vehicle compatibility
    - TRANSACTION: Price, stock, store inventory, store search, purchase, checkout, order tracking, reservation
    - SUPPORT: Warranty, returns, FAQ, human agent

    DECISION RULES:

    DEFAULT: STOP after every agent turn.
    Each agent does its ONE job, returns the result, and waits for the user's next explicit action.
    The user drives every step — agents never auto-chain into the next domain.

    ONLY CONTINUE when the agent was routed to the WRONG domain and cannot complete the task:
    - Transaction Agent has no product search tools → needs goods_no → CONTINUE → DISCOVERY
    - Discovery Agent has no price/order/store tools → CONTINUE → TRANSACTION
    - Discovery Agent says "다른 사이즈로 검색" (internal retry) → CONTINUE → DISCOVERY

    STOP in ALL other cases:
    - Agent completed its task (showed products, stores, prices, schedule, etc.) → STOP
    - Agent is showing a list waiting for user selection (cars, tires, stores) → STOP
    - Agent asks user for any input → STOP
    - Pre-order preview shown → STOP
    - Any confirmation step → STOP

    KEY PRINCIPLE: One agent, one turn, one job. User explicitly triggers the next step.
    """)


def decide_next_action(
    original_messages: list[dict],
    previous_agent_response: str,
    previous_domain: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> AgentDecision:
    from langchain_core.messages import SystemMessage, HumanMessage

    structured_model = _decision_structured_model

    user_message = ""
    for msg in reversed(original_messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    system_msg = SystemMessage(content=prompt_router())
    human_msg = HumanMessage(
        content=dedent(f"""
        <user_request>{user_message}</user_request>

        Previous Agent Domain: {previous_domain}

        Previous Agent Response:
        {previous_agent_response}

        Please decide the next action.
    """)
    )

    trace_config = build_trace_config(
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        tags=["router", "decide_next_action"],
        prompt_name="router",
        run_name="💭 next_action",
    )

    try:
        result: AgentDecision = structured_model.with_retry(stop_after_attempt=3).invoke([system_msg, human_msg], config=trace_config)
        return result
    except Exception as e:
        logger.warning(f"[DECISION] LLM decision failed after retries: {e}")
        return AgentDecision(
            next_action=NextAction.STOP,
            next_domain=None,
            reason=f"Decision failed: {str(e)[:100]}",
        )


class MultiAgentDomain(BaseModel):
    """Router result that supports multiple domains (multi-intent)."""

    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        TRANSACTION = "transaction"
        SUPPORT = "support"

    reason: str = Field(description="Reason for the classification, using english")
    domains: list[Domain] = Field(description="List of domains detected in the request, ordered by priority")
    execution_plan: list[str] = Field(
        description="Short ordered plan for the selected domains, without tool names or parameters"
    )
    user_behavior: str = Field(
        description=(
            "What the user is currently doing in this conversation turn, inferred from full history. "
            "Examples: 'selecting car from list shown in previous turn', "
            "'providing car number to resolve vehicle', "
            "'confirming product selection', 'responding to recommendation', "
            "'requesting NEW recommendation with different scenario (e.g. 빗길 → 주말)', "
            "'requesting fresh search to replace previous list', "
            "'fresh start — first message'. "
            "⚠️ When the user provides a NEW scenario keyword (빗길/눈길/사계절/주말/정숙성/"
            "출퇴근/가족/전기차 등) OR re-search trigger ('다시', '새로', '이전 추천 말고') "
            "AFTER a previous recommendation, the user is NOT 'filtering' or 'selecting from "
            "previous list' — they want a NEW recommendation. Write user_behavior accordingly. "
            "Always provide a value."
        ),
    )
    flow: str = Field(
        description=(
            "One-line summary of the conversation journey so far. "
            "Examples: 'user requested tires → agent showed 2 cars → user is selecting car', "
            "'user asked price → discovery found goods_no → transaction showing price', "
            "'fresh start — no prior context'. "
            "Keep under 120 chars."
        ),
    )

    agent_prompt_profile: AgentPromptProfile = Field(
        description=(
            "Prompt profile for the selected domain agent. "
            "Transaction narrow profiles: 'transaction_coupon' (coupon/promotion), 'transaction_order' (order/cart/status/cancellation fee), "
            "'transaction_store' (store search/schedule/inventory), 'transaction_price_stock' (price/stock with known goods_no). "
            "Discovery narrow profiles: 'discovery_search' (product search by name/keyword/size, price/stock/discount-price with specific product name, run-flat vs normal price comparison, best-sellers — goods_no NOT yet known). "
            "'discovery_recommendation' (tire recommendation by vehicle, tire size, scenario, discount ranking WITHOUT specific product name, or continuation from recommendation cards). "
            "'discovery_event_content' (events, deals, event-applicable products, product events, YouTube/video). "
            "Use 'full' for compatibility-only or any mixed/uncertain case."
        )
    )

    def get_agents(self):
        """Return list of agents based on detected domains."""
        agent_map = {
            self.Domain.DISCOVERY: discovery_subagent,
            self.Domain.TRANSACTION: transaction_subagent,
            self.Domain.SUPPORT: support_subagent,
            self.Domain.LEADING: leading_agent,
        }
        return [agent_map[d] for d in self.domains if d in agent_map]


class _SlimMultiAgentDomain(BaseModel):
    """First-turn slim classification schema.

    Drops user_behavior / flow narrative fields — they only carry signal
    once prior conversation history exists. On a fresh session they would
    be placeholders ("fresh start — no prior context"), so we skip
    generating them to save output tokens on every first message.
    """

    reason: str = Field(description="Reason for the classification, using english")
    domains: list[MultiAgentDomain.Domain] = Field(
        description="List of domains detected in the request, ordered by priority"
    )
    execution_plan: list[str] = Field(
        description="Short ordered plan for the selected domains, without tool names or parameters"
    )
    agent_prompt_profile: AgentPromptProfile = Field(
        description=(
            "Prompt profile for the selected domain agent. "
            "Use 'transaction_*' for clear transaction flows; 'discovery_search' for product search by name/keyword/size, "
            "price/stock/discount-price with specific product name, run-flat vs normal price comparison, or best-sellers (no goods_no in context); "
            "'discovery_recommendation' for tire recommendation by vehicle, tire size, scenario, "
            "discount ranking WITHOUT a specific product name, or continuation from recommendation cards; "
            "'discovery_event_content' for events/deals/video; 'full' for compatibility-only or uncertain cases."
        )
    )


# Module-level singletons — avoid re-wrapping LLM per request.
# DECISION_LLM (small/fast) is sufficient for routing classification since the
# schemas are descriptive only — no prescriptive `next_action` field that would
# require recalling tool signatures (which the small model used to hallucinate).
_multi_intent_model = _decision_llm.with_structured_output(MultiAgentDomain, strict=True)
_slim_intent_model = _decision_llm.with_structured_output(_SlimMultiAgentDomain, strict=True)


def prompt_router_multi() -> str:
    """Classification prompt that detects multi-intent with flow sequences and conversation context."""
    return """
You are a domain classifier for T-Station AI (Hankook Tire).
Read the FULL conversation history to classify the current user message.

Produce 6 outputs:
1. domains — ONE OR MORE domains based on detected intents (ordered by priority)
2. reason — why you chose these domains
3. execution_plan — short ordered plan for the selected domains, without tool names or parameters
4. user_behavior — what the user is currently doing based on the full conversation (e.g. "selecting car from list shown in previous turn", "providing tire size", "confirming product")
5. flow — one-line summary of the journey so far (e.g. "user requested tires → agent showed 2 cars → user selecting")

6. agent_prompt_profile - use a narrow profile only for clear single-flow requests:
   - "transaction_coupon": coupon/promotion/coupon issue
   - "transaction_order": order history, order status, cart, quick order, order cancellation/cancellation-fee inquiry (must check order/logistics state, not FAQ)
   - "transaction_store": store search, nearby store, store detail, schedule, store inventory, store holiday/closure info, reservation availability on a specific date or holiday period; also use when the user selects a product size/variant (e.g. "255/45R20") AND the conversation history shows an active store reservation/booking intent ("예약", "장착", "방문") — the goal is store schedule, not price
     ⚠️ "매장에서 예약 받아?" / "X일에 예약 가능한지" / "연휴에도 예약 받아" targeting a STORE → transaction_store (NOT transaction_order — those are for "내 예약" personal lookup)
   - "transaction_price_stock": price/final price/logistics stock when goods_no is already known AND there is NO active store reservation intent in the conversation history
   - "discovery_recommendation": tire recommendation by vehicle, tire size, scenario, discount ranking WITHOUT a specific product name, or continuation from recommendation cards ("추천", "맞는 타이어", "12가3456 타이어", "세일 많이 하는 타이어", "할인율 높은 타이어")
   - "discovery_search": product search by name/keyword/brand/size (no goods_no), price/stock/discount-price query with product name only (e.g. "벤투스 S2 할인가 얼마야?", "다이나프로 HPX 할인된 가격"), run-flat vs normal price comparison, best-sellers ("많이 팔린/베스트셀러/잘 팔리는") — goods_no NOT yet known in context
   - "discovery_event_content": explicit events/deals/event-product requests ("이벤트", "기획전", "행사 목록", "이벤트 대상 상품"), product-applicable events, YouTube/video
   - "full": compatibility-only, mixed, ambiguous, or uncertain cases; ALSO use when: (a) user message matches datepick selection pattern (ONLY a date+time, e.g. "2026년 5월 15일 (금)\n17:00") — preOrder+quick_order flow requires full profile, (b) user confirms a preOrder card shown in a previous turn ("ㅇㅇ", "네", "주문해줘" after preOrder was displayed)

IMPORTANT: user_behavior must reflect the FULL conversation context, not just the current message.
If the user is responding to a previous agent question (e.g. selecting a car, confirming a product, providing a car number),
identify WHAT they are responding to in user_behavior. The agent will pick the actual tool to call based on its own flow rules — do NOT prescribe specific tool names or parameters here.

⚠️ CRITICAL — RE-RECOMMENDATION INTENT (replaces "filter previous list" default):
When ANY previous turn in this conversation produced a tire recommendation list
(via get_products_recommendations_tool — even if it was several turns ago, NOT
just the immediately previous turn; intervening turns like product description
or unrelated questions do NOT reset this) AND the current user message contains
EITHER:
  (a) a NEW scenario keyword (빗길, 눈길, 사계절, 고속, 핸들링, 정숙, 퍼포먼스,
      출퇴근, 장거리, 도심, 가족/패밀리, 전기차/EV, SUV, 짐 많이, 주말,
      아이/안전, 가성비, 워런티, 통근, 스포츠 등) whose scenario family is
      DIFFERENT from the previous tool's rcmd_type, OR
  (b) a re-search trigger ("다시", "새로", "이번엔", "바꿔서", "다른 거",
      "이전 추천 말고", "아까 거 말고", "이거 말고", "아까 그거 말고",
      "다른 종류로"),
the user is requesting a NEW recommendation, NOT filtering the previous list.

⚠️ The 다시 keyword is OPTIONAL. A new scenario alone is enough — even an
explicit "추천" request like "패밀리 SUV에 잘 맞는 사계절용 추천" after a
previous "전기차용" recommendation is RE-RECOMMENDATION, not filtering.

⚠️ Price-similarity follow-up is always DISCOVERY, not TRANSACTION:
If the previous turn showed a product price (via price breakdown, product card, or
description) and the user now asks to see products at a comparable price level,
this is a NEW recommendation request — route to DISCOVERY. The user wants to
browse by price positioning, not to complete a purchase or check stock.
Example: TRANSACTION showed ₩154,300 price → user asks "비슷한 가격대 타이어 추천" → DISCOVERY.

PREV=CUR escape (do NOT mark as RE-RECOMMENDATION):
  - If the user's scenario word matches the SAME scenario family as PREV
    (e.g. PREV rcmd_type="ev" and user says "이 EV용 중에서 18인치"), this is
    a continuation/filter, not a re-recommendation. Do NOT trigger this rule.
  - If the user uses a demonstrative/ordinal/filter-only phrase ("이 중에서",
    "첫번째", "할인만", "가장 저렴한") — even if a scenario word also appears
    — treat as filter, not re-recommendation.

In RE-RECOMMENDATION cases:
  - user_behavior MUST be like: "requesting NEW recommendation with different scenario (X)"
    or "requesting fresh search to replace previous list"
  - NEVER write 'filter previous tire list', 'pick from previous list',
    'select X-friendly items from previous Y list' — these phrases push the agent
    into wrong behavior. The Discovery agent has its own Branch A/B logic that
    reads user_behavior to decide whether to re-call the recommendation tool.

Worked examples (RE-RECOMMENDATION vs FILTER):
1. PREV="wet" → USER="주말 나들이용으로 다시" → CORRECT behavior: "requesting new recommendation with weekend scenario...". WRONG: "selecting/filtering previous tire list".
2. PREV="ev" → intervening turn → USER="패밀리 SUV에 잘 맞는 사계절용 추천" → family+사계절 ≠ ev → RE-RECOMMENDATION. CORRECT: "requesting NEW recommendation...". WRONG: "filter previous EV list...".
3. PREV="ev" → USER="이 EV 타이어 중에서 18인치로" → "이 중에서" (demonstrative) = filter/continuation. CORRECT: "filtering previous EV recommendation list...".

Also identify the FLOW SEQUENCE (ordered list of domains) for the request and mirror it in execution_plan.

DOMAINS:
- TRANSACTION: Price, stock (logistics/store), inventory, store availability, store search by location/name, purchase, checkout, order tracking, reservation time change (예약 시간 변경 / 방문 시간 변경 / 일정 변경), order cancellation/cancellation fee (주문 취소 / 취소하고 싶어 / 취소해줘 / 취소 수수료 / 오늘 취소하면 수수료), store visit reservation (specific date/time slot booking), coupon inquiry (내 쿠폰 / 쿠폰함 / 쿠폰 사용 조건 / 쿠폰 어떻게 써 / 쿠폰 사용법), order history inquiry (내 주문내역 / 주문 내역 / 주문 조회), maintenance/service history lookup (정비이력 / 정비내역 / 관리받은 내역 / 서비스 이력)
- SUPPORT: FAQ, warranty, returns policy questions, general maintenance info, **per-vehicle maintenance D-day / 정비 시기·주기 / 교체 시기 / 점검 만기일 (내 차 정비 일정 / 엔진오일 언제 갈아야 / all my T 점검 만기 / 타이어 교체 시기)** ⚠️ NOT to be confused with store visit reservation booking (=TRANSACTION), human agent
- DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features, product video reviews, YouTube video search
- LEADING: Greeting, unclear intent

====================================================
DOMAIN ROUTING EXAMPLES
====================================================

DISCOVERY — product search, recommendation, compatibility (no goods_no yet):
- "buy tires for 12가3456", "쏘나타 타이어 추천", "벤투스 S2 가격/재고/매장" (resolve goods_no first), "런플랫이 얼마나 더 비싸?", "225/45R18 런플랫 가격 차이", "이벤트", "리뷰 영상", "추천 가격 비교해줘"
- 가격 범위/예산으로 타이어 찾기: "30만원 이하 타이어 추천", "20만원에서 30만원 사이 타이어", "예산 50만원 이상 프리미엄 타이어", "한국타이어 30만원 이하 있어?" — goods_no 없으므로 반드시 DISCOVERY
- 가격 유사성 기반 추천 follow-up: 직전 대화에서 특정 상품의 가격이 표시된 후 그 가격대와 비슷한 다른 타이어를 요청하는 경우 — 이전 도메인이 TRANSACTION(가격 조회)이어도 반드시 DISCOVERY. 사용자 의도는 가격 포지셔닝 기반 새 추천이므로 TRANSACTION이 아님.
- 상품명 + 예약/주문 + 사이즈 없음: "판교점에서 벤투스 S2 AS 4개 예약해줘", "키너지 GT 2개 주문해줘" — goods_no 없으므로 DISCOVERY (사이즈 선택을 위해 검색 결과 목록 먼저 제시)

TRANSACTION — price/stock/store/order with goods_no already known in context:
- "{{goods_no}} 가격 얼마야?", "주문/장바구니", "강남 매장", "예약 날짜", "한남점 선택", "주문 내역", "내 쿠폰", "오늘 취소하면 수수료 있나요?"

SUPPORT — policy, warranty, human agent:
- "보증/반품", "상담원/1:1문의"

⚠️ NEVER classify as SUPPORT (must be TRANSACTION): "내 쿠폰/쿠폰함", "쿠폰 사용 조건/쿠폰 어떻게 써", "내 주문/주문 조회", "주문 취소/취소하고 싶어/취소해줘", "취소 수수료/취소비용/취소 비용 있나요", "오늘 취소하면/예약 취소하면 수수료" — cancellation fee questions must check order/logistics state, not FAQ

⚠️ ALWAYS classify as SUPPORT (NOT TRANSACTION, NOT DISCOVERY): 두 개 이상의 할인 수단(쿠폰/딜/이벤트/프로모션/기획전/혜택) 사이의 **중복 적용 여부** 발화 — "X 중복 가능?", "X이랑 Y 같이 쓸 수 있어?", "X이랑 Y 동시 적용?", "둘 다 쓸 수 있어?", "함께 사용 가능?" — DBA 의 stacking 룰을 응답해야 하므로 SUPPORT 로 라우팅. "쿠폰" 단독 단어만 보고 transaction_coupon 으로, "기획전/이벤트" 단독 단어만 보고 discovery_event_content 로 분류 금지.
Examples:
- "반짝블랙딜이랑 우동딜 중복 가능?" → SUPPORT
- "반짝블랙딜에 내 생일쿠폰 같이 쓸 수 있어?" → SUPPORT
- "기획전 할인이랑 쿠폰 같이 돼?" → SUPPORT
- "두 쿠폰 동시 적용 가능?" → SUPPORT

LEADING — greeting, unclear intent:
- "안녕하세요/도와줘"

====================================================
DECISION RULES
====================================================

CORE RULE: Prefer one domain per turn. Return multiple domains only when the current user request clearly needs a handoff in the same turn.
Each domain does its ONE job. The coordinator may skip the extra next-action LLM call when your multi-domain plan is already clear.

DISCOVERY when:
- Product search by name/keyword (goods_no not yet known)
- Tire recommendation (vehicle-specific or general)
- Compatibility check
- Product specs/features/tech
- Price/stock/store queries where goods_no is NOT yet known → DISCOVERY resolves goods_no first, then STOP
- Event/deal/video content

TRANSACTION when:
- goods_no is already known in conversation context (G + 12 digits)
- Store search by location/name
- Store schedule / reservation slots
- Order creation, cart save, order tracking
- Pre-order confirmation flow

⚠️ "buy/order/purchase/reserve/예약" with product NAME (not goods_no) → DISCOVERY first to find goods_no. If the same message ALSO has a size that narrows to 1 result, return [DISCOVERY, TRANSACTION]. If NO size → DISCOVERY only (list shown, user selects size next turn).
⚠️ "buy/order/purchase" with goods_no already in context → TRANSACTION directly.

SUPPORT when: warranty, returns, policy, human agent, 1:1 inquiry
LEADING when: greeting, unclear intent, OR bare ambiguous re-trigger (see below)

====================================================
AMBIGUOUS RE-TRIGGER → LEADING
====================================================

If the user's message is essentially ONLY a bare re-trigger / re-search word with
NO other meaningful context, classify as LEADING so the leading agent can ask the
user to clarify what they want to redo.

Bare re-trigger words (alone or with trivial padding only):
  - "다시", "다시요", "다시 해줘", "다시 보여줘", "다시 찾아줘", "다시 알려줘"
  - "새로", "새로 해줘", "새로 찾아줘"
  - "다른 거", "다른 거로", "바꿔서", "이번엔", "또"

A message qualifies as "bare re-trigger" when it does NOT include ANY of the
following alongside the re-trigger word:
  - 시나리오 / 사용 키워드: 빗길, 눈길, 사계절, 고속, 핸들링, 정숙, 퍼포먼스,
    출퇴근, 장거리, 도심, 가족, 전기차, 짐, 주말, 아이/안전, 가성비, 워런티,
    통근, 스포츠, 사이즈, 차종, 가격, 재고, 매장, 주문, 배송, 워런티, 환불 등
  - 상품명 / 브랜드명: 벤투스, 키네르기, 옵티모, 다이나프로, 라우펜, Ventus,
    Kinergy, Optimo, Dynapro, Laufenn, Michelin, Pirelli, Bridgestone,
    Continental, Goodyear, 한국타이어, Hankook
  - 차량번호 패턴: {{vehicle_number}} (예: "12가3456")
  - 구체적 의도 동사: 추천, 검색, 찾, 알려, 비교, 보여, 확인, 사고, 살래

Examples:
- LEADING (bare): "다시", "다시 해줘", "다른 거 보여줘", "이전 추천 말고"
- DISCOVERY/TRANSACTION (has context): "주말용 다시"(scenario), "벤투스 S2 다시"(product), "가격 다시"(domain anchor), "다시 추천해줘"(verb)

⚠️ This rule overrides CONTINUATION DETECTION below for bare re-triggers — a
bare re-trigger is NOT a valid continuation; it's an ambiguous request that
needs clarification before any agent runs.

====================================================
CONTINUATION DETECTION
====================================================

If the previous agent showed a list and asked user to SELECT (cars, tires, stores, dates):
→ User's short reply (number, name, tire size, store name) is a CONTINUATION of the SAME domain.
→ Classify into that SAME domain — do NOT chain to another domain.

Examples:
- DISCOVERY continues: Pick car ("제타"), pick tire ("벤투스 S2", "1. 벤투스", "1번")
- TRANSACTION continues: Pick store ("한남점"), pick date ("내일 10시")

⚠️ HARD RULE — Tire pick from a Discovery recommendation/search list stays in DISCOVERY.
Even when user_behavior reads "confirming product selection" or "user picked a tire", the
correct domain is DISCOVERY (so `get_product_description_tool` runs and the customer sees
the product detail card with the closing "원하시면 이어서 가격, 재고, 주문 진행까지 도와
드릴게요" offer). DO NOT route to TRANSACTION unless the user's CURRENT message itself
contains an explicit transactional verb — "주문", "구매", "살래", "결제", "장바구니",
"가격", "얼마", "재고", "예약", "매장". A bare product name (with or without an ordinal
"1." / "1번") is NEVER a transactional trigger by itself, even though it confirms a pick.

⚠️ Do NOT analogize "한남점 선택할게 → TRANSACTION" (store selection in an order flow) to
product selection. They are different: store selection happens AFTER goods_no is locked
in, so it advances Flow 6; tire selection happens BEFORE goods_no is locked in, so it
just resolves goods_no inside Discovery. Stay in DISCOVERY for tire picks.

⚠️ Exception: If the user's short reply is a BARE re-trigger word (다시 / 새로 /
다른 거 alone, no other anchors), do NOT classify as continuation — route to
LEADING per AMBIGUOUS RE-TRIGGER rule above.

Korean vehicle numbers follow patterns: {{vehicle_number}} (e.g., "12가3456", "123가1234")
"""


def prompt_router_slim() -> str:
    """First-turn classifier prompt.

    Continuation / re-recommendation / bare re-trigger rules are dropped
    because there is no prior conversation context to leverage on a fresh
    session. Use only when the message history contains a single user message.
    """
    return """
You are a domain classifier for T-Station AI (Hankook Tire).
Classify the user's FIRST message into EXACTLY ONE domain.

DOMAINS:
- TRANSACTION: store search by location or name (강남/근처/올마이티/All My T); goods_no (G+12 digits) price/stock/order; store visit reservation (specific date/time slot booking); reservation time change (예약 시간 변경/방문 시간 변경/일정 변경/시간 바꿀 수 있어); cart; coupon inquiry (내 쿠폰/쿠폰함/쿠폰 사용 조건/쿠폰 어떻게 써/쿠폰 사용법) [⚠️ NOT SUPPORT]; order history (내 주문내역/주문 조회/내 주문/내가 주문한 거) [⚠️ NOT SUPPORT]; maintenance/service history lookup (정비이력/정비내역/관리받은 내역/서비스 이력) [⚠️ NOT SUPPORT — must query member history]; order cancellation (주문 취소/취소하고 싶어/취소해줘) [⚠️ NOT SUPPORT]; cancellation/return fee inquiry (취소 수수료/취소비용/오늘 취소하면 수수료/예약 취소 비용/택배비/왕복 배송비/반품 비용/반품수수료) [⚠️ NOT SUPPORT — must check order/logistics state].
- DISCOVERY: product search by name or keyword; tire recommendation; vehicle-tire compatibility; product specs/features/videos; run-flat vs normal tire price comparison; price/stock/buy with PRODUCT NAME ONLY (no goods_no — Discovery resolves goods_no first).
- SUPPORT: warranty, returns, refund, general maintenance info, **per-vehicle maintenance D-day / 정비 시기·주기 / 교체 시기 / 점검 만기일 (내 차 정비 일정 / 엔진오일 언제 갈아야 / all my T 점검 만기 / 타이어 교체 시기)** [⚠️ NOT TRANSACTION — registered-car D-day matrix, not a store-visit slot booking], shipping fee policy (배송비/도서산간/제주/서귀포), online-vs-store price policy, 1:1 문의, 상담원 연결, customer complaints (짜증/엉망/화나/뭐 이런). ⚠️ Do NOT route cancellation fee questions here — Transaction checks actual order state.
- LEADING: pure greeting; unclear intent; bare re-trigger words (다시/또) with no domain anchor.

RULES:
- G+12 digits in message → TRANSACTION
- Product name only (벤투스/Ventus/다이나프로/Dynapro/...) + price/stock/buy, no goods_no → DISCOVERY
- Product name + explicit same-turn order/store request + size, no goods_no → [DISCOVERY, TRANSACTION]
- Product name + 예약/주문 + NO size, no goods_no → DISCOVERY only (must show list so user picks size)
- Vehicle number (e.g. 12가3456) + tire request → DISCOVERY
- 추천/맞는 타이어/어떤 타이어 → DISCOVERY
- 가격 범위/예산으로 타이어 찾기 (X만원 이하/이상/사이 타이어 등, goods_no 없음) → DISCOVERY
- 런플랫 가격 차이/추가 비용/일반 타이어 대비 비교 → DISCOVERY, agent_prompt_profile=discovery_search
- 매장/근처/올마이티/All My T → TRANSACTION
- 정비이력/정비내역/관리받은 내역/서비스 이력/받은 서비스 → TRANSACTION, agent_prompt_profile=transaction_order
- 예약 시간 변경/방문 시간 변경/일정 변경/시간 바꿀 수 있어 → TRANSACTION, agent_prompt_profile=transaction_order
- 단순 변심 + 반품 + (왕복 배송비/택배비/배송비/반품 비용/반품수수료) → TRANSACTION, agent_prompt_profile=transaction_order
- 환불/반품/보증/워런티/1:1 문의/상담원 → SUPPORT, except the cancellation/return shipping-fee rule above
- 두 개 이상의 할인 수단(쿠폰/딜/이벤트/프로모션/기획전/혜택) 사이의 중복 적용 여부 — "X 중복 가능?", "X이랑 Y 같이 쓸 수 있어?", "동시 적용?", "둘 다 쓸 수 있어?" → SUPPORT (NOT transaction_coupon, NOT discovery — DBA stacking 룰 응답 필요)
- 온라인 전용 상품 차이/온라인에서만 구매/매장 방문 구매 가능 여부 → SUPPORT
- 제주/서귀포/도서산간 + 배송비/추가 비용/온라인 가격 정책 질문 → SUPPORT
- 취소 수수료/취소비용/오늘 취소하면 수수료/예약 취소 비용/택배비 물어내야/왕복 배송비/반품수수료 → TRANSACTION, agent_prompt_profile=transaction_order
- Complaint tone (짜증/엉망/화나/뭐 이런) → SUPPORT
- Greeting only (안녕/hi/hello) → LEADING

EXAMPLES (tricky cases):
- "벤투스 S2 가격 얼마야?" → DISCOVERY, agent_prompt_profile=discovery_search (product name, no goods_no)
- "G012345678901 가격" → TRANSACTION, agent_prompt_profile=transaction_price_stock
- "G012345678901 재고 있어?" → TRANSACTION, agent_prompt_profile=transaction_price_stock
- "내 쿠폰 보여줘" → TRANSACTION, agent_prompt_profile=transaction_coupon (NOT SUPPORT)
- "쿠폰 사용 조건이 어떻게 돼?" → TRANSACTION, agent_prompt_profile=transaction_coupon (NOT SUPPORT)
- "반짝블랙딜이랑 우동딜 중복 가능?" → SUPPORT (discount-means stacking — DBA 룰 응답 필요, NOT transaction_coupon)
- "반짝블랙딜에 내 생일쿠폰 같이 쓸 수 있어?" → SUPPORT (딜+쿠폰 stacking)
- "기획전 할인이랑 쿠폰 같이 돼?" → SUPPORT (기획전+쿠폰 stacking, NOT discovery_event_content)
- "두 쿠폰 동시 적용 가능?" → SUPPORT (쿠폰+쿠폰 stacking, NOT transaction_coupon)
- "내 주문내역 알려줘" → TRANSACTION, agent_prompt_profile=transaction_order (NOT SUPPORT)
- "정비이력 보여줘", "내가 관리받은 내역 알려줘" → TRANSACTION, agent_prompt_profile=transaction_order (maintenance/service history lookup, NOT SUPPORT)
- "내 예약 알려줘", "예약 조회", "예약 어떻게 돼있어", "다음 방문 언제" → TRANSACTION, agent_prompt_profile=transaction_order (visit reservation lookup, NOT SUPPORT, NOT creating new reservation)
- "오늘 예약한거 시간 변경하고 싶어" → TRANSACTION, agent_prompt_profile=transaction_order
- "내일 2시 예약인데 4시로 바꿀 수 있어?" → TRANSACTION, agent_prompt_profile=transaction_order
- "오늘 취소하면 수수료 있나요?" → TRANSACTION, agent_prompt_profile=transaction_order (check order/logistics state, NOT FAQ)
- "예약 취소하면 비용이 발생하나요?" → TRANSACTION, agent_prompt_profile=transaction_order (store visit vs online order must be determined from orders)
- "단순 변심으로 반품하면 왕복 배송비 얼마야?" → TRANSACTION, agent_prompt_profile=transaction_order (return shipping-fee policy must use order/logistics policy, NOT Support FAQ)
- "강남역 근처 매장 찾아줘" → TRANSACTION, agent_prompt_profile=transaction_store
- "강남점에서 추석 연휴에도 타이어 교체 예약 받아?" → TRANSACTION, agent_prompt_profile=transaction_store (store holiday availability — 매장 운영/예약 가능 여부 조회, NOT "내 예약" lookup)
- "티스테이션 강남점에서 2026/06/25에도 타이어 교체 예약받는지 알려줘" → TRANSACTION, agent_prompt_profile=transaction_store (store schedule availability on specific date)
- "내일 석가탄신일인데 티스테이션 한남점 열어?" → TRANSACTION, agent_prompt_profile=transaction_store (store holiday check)
- "제주도 매장에서도 온라인 가격이랑 똑같아?" → SUPPORT (Jeju/island shipping-fee and online-vs-store policy FAQ, NOT store search)
- "서귀포시인데 배송비 더 들어?" → SUPPORT (Seogwipo/Jeju additional shipping-fee policy FAQ)
- "12가3456 타이어 추천" → DISCOVERY, agent_prompt_profile=discovery_recommendation
- "30만원 이하 타이어 추천해줘" → DISCOVERY, agent_prompt_profile=discovery_recommendation (price range recommendation)
- "지금 세일 많이 하는 타이어 위주로 보여줘" → DISCOVERY, agent_prompt_profile=discovery_recommendation (discounted tire ranking, NOT events/deals)
- "할인율 높은 타이어 보여줘" → DISCOVERY, agent_prompt_profile=discovery_recommendation (highest discount applied)
- "20만원에서 30만원 사이 한국타이어" → DISCOVERY, agent_prompt_profile=discovery_search (product search by price range)
- "벤투스 S2 225/45R17 가격" → DISCOVERY, agent_prompt_profile=discovery_search
- "런플랫 타이어는 더 비싸다며? 얼마나 더 내야해?" → DISCOVERY, agent_prompt_profile=discovery_search
- "225/45R18 런플랫은 일반 타이어보다 얼마나 비싸?" → DISCOVERY, agent_prompt_profile=discovery_search
- "다이나프로 HPX 할인된 가격이 얼마야?" → DISCOVERY, agent_prompt_profile=discovery_search (specific product + discount price = search, NOT recommendation)
- "벤투스 S2 할인가 얼마야?" → DISCOVERY, agent_prompt_profile=discovery_search (specific product name → search for it, not discount ranking)
- "미쉐린 235/55R19 재고 있어?" → DISCOVERY, agent_prompt_profile=discovery_search
- "요즘 많이 팔리는 타이어" → DISCOVERY, agent_prompt_profile=discovery_search
- "제일 최근에 나온 타이어 신제품이 뭐야?" → DISCOVERY, agent_prompt_profile=discovery_search
- "진행 중인 이벤트 보여줘" → DISCOVERY, agent_prompt_profile=discovery_event_content
- "리뷰 영상 찾아줘" → DISCOVERY, agent_prompt_profile=discovery_event_content
- "판교점에서 벤투스 S2 AS 4개 예약해줘" → DISCOVERY, agent_prompt_profile=full (product name + 예약, no size, no goods_no — need to show size list first)
- "벤투스 S2 AS 205/55R16 4개 판교점 예약해줘" → [DISCOVERY, TRANSACTION], agent_prompt_profile=full (product name + size → narrows to 1 result)
- [Prior context: agent showed size options for "오목천점 예약" request] User says "255/45R20" → TRANSACTION, agent_prompt_profile=transaction_store (size selection inside active reservation flow — needs store+schedule, NOT price/stock)
- [Prior context: agent showed size options for "오목천점 예약" request] User says "255/55R18" → TRANSACTION, agent_prompt_profile=transaction_store (same rule: reservation context overrides price_stock profile)
- "2026년 4월 23일 (목)\n11:00" → TRANSACTION, agent_prompt_profile=full (datepick UI selection — date+newline+time pattern means user picked a slot; full profile needed for preOrder → quick_order flow)
- "2026년 5월 15일 (금)\n17:00" → TRANSACTION, agent_prompt_profile=full (same rule: any message that is ONLY date+newline+time is a datepick selection, always use full profile)
- [Prior context: agent showed preOrder card] User says "ㅇㅇ" or "네" or "주문해줘" → TRANSACTION, agent_prompt_profile=full (confirmation after preOrder card — needs quick_order_tool which is only in full profile)

Output: domains (list with EXACTLY ONE domain), reason, execution_plan, and agent_prompt_profile.
agent_prompt_profile:
- transaction_coupon: coupon/promotion -> transaction_coupon
- transaction_order: order/cart/status/cancellation fee -> transaction_order
- transaction_store: store/search/schedule/store inventory -> transaction_store
- transaction_price_stock: goods_no + price/final price/logistics stock -> transaction_price_stock
- discovery_search: product search by name/keyword/brand/size (no goods_no in context), price/stock/discount-price query with specific product name ("벤투스 S2 할인가 얼마야?", "다이나프로 HPX 할인된 가격"), run-flat vs normal price comparison, best-sellers ("많이 팔린/베스트셀러/잘 팔리는"), newest products ("최신/신제품/최근 출시")
- discovery_recommendation: tire recommendation by vehicle, tire size, scenario, discount ranking WITHOUT a specific product name, or continuation from recommendation cards ("추천", "내 차에 맞는", "세일 많이 하는 타이어", "할인율 높은 타이어")
- discovery_event_content: explicit events/deals, event-applicable products, product-applicable events, YouTube/video
- full: compatibility-only, mixed, ambiguous, or uncertain
"""


class StreamingMultiAgentCoordinator:
    """Orchestrates multiple agents with streaming support."""

    @staticmethod
    def _compact_tool_results_for_llm(tool_data: list[dict]) -> list[dict]:
        """Build a smaller tool-result view for agent handoff prompts only."""
        compact_items: list[dict] = []
        for item in tool_data:
            tool_name = item.get("tool", "")
            data = item.get("data")
            input_data = item.get("input", item.get("args", {}))
            raw_output = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            compact = filter_for_context(tool_name, raw_output, input_data)
            if compact is not None:
                compact_items.append(compact)
            else:
                compact_items.append({"tool": tool_name, "input": input_data, "data": data})
        return compact_items

    # ---------------------------------------------------------------------
    # Hardcoded keyword routing (runs BEFORE the LLM router)
    # ---------------------------------------------------------------------
    # The LLM router was observed ignoring its own prompt-level routing rules
    # under heavy slot/context bias (e.g., post-cart "이벤트 목록" got routed
    # to TRANSACTION because the conversation history was order-flow heavy).
    # When the user's CURRENT message contains any of the listed phrases, we
    # hard-pin the domain without invoking the LLM at all — fast and
    # deterministic.
    #
    # Match style: case-sensitive substring match on the cleaned current
    # user input (after stripping the injected "# Respond in Korean language"
    # wrapper and the trailing [current_time: ...] suffix).
    _KEYWORD_FORCE_TABLE: ClassVar[
        list[tuple[list[str], "MultiAgentDomain.Domain"]]
    ] = [
        # SUPPORT — discount-means stacking eligibility (coupon/promotion/event/deal/기획전).
        # MUST come first so "기획전 + 중복" doesn't get hijacked by the broader
        # DISCOVERY 기획전/이벤트 keyword below, and "쿠폰 중복" doesn't get hijacked
        # by TRANSACTION 쿠폰함 keyword. The LLM classifier consistently mis-routes
        # these stacking questions to transaction_coupon because the TRANSACTION
        # domain description owns "coupon inquiry" — substring force is the
        # deterministic fix.
        (
            [
                # "중복" + verb/adjective — strong stacking signal
                "중복 가능",
                "중복 적용",
                "중복 사용",
                "중복 돼",
                "중복돼",
                "중복 사용 가능",
                # "같이/동시/함께/둘 다" + 사용/적용 verbs
                "같이 쓸 수 있",
                "같이 쓸수 있",
                "같이 써도",
                "같이 쓰면",
                "같이 사용 가능",
                "같이 돼",
                "같이 됨",
                "같이 적용",
                "동시 적용",
                "동시 사용",
                "동시에 사용",
                "동시에 적용",
                "동시에 돼",
                "동시에돼",
                "함께 사용 가능",
                "함께 쓸 수 있",
                "둘 다 쓸",
                "둘 다 적용",
                "둘 다 사용",
                "두 개 다 쓸",
                "두 개 다 적용",
                # "추가" 계열 — "쿠폰 더 추가 돼?", "할인 추가 사용", "추가 적용?"
                "추가 돼",
                "추가 사용",
                "추가 적용",
            ],
            MultiAgentDomain.Domain.SUPPORT,
        ),
        # TRANSACTION — cancellation/return shipping-fee inquiry (TC-118).
        # Keep this before the broad SUPPORT "반품" rule so round-trip return-fee
        # questions check order/logistics policy instead of FAQ hallucinating 5천 원.
        (
            [
                "취소하면 택배비",
                "택배비 물어내",
                "왕복 배송비",
                "반품 비용",
                "반품수수료",
                "취소 수수료",
                "취소비용",
            ],
            MultiAgentDomain.Domain.TRANSACTION,
        ),
        # SUPPORT — pickup-driver (스마트픽업) status/location query.
        # The chatbot has no tool to query a smart-pickup driver's real-time
        # position. Without this force, "기사님 어디쯤 오고계셔?" style messages
        # hit TRANSACTION → get_order_delivery, which only returns the user's
        # online order/visit reservation (often a 직접방문 record with no driver)
        # and the agent falls back to "기사님 위치 조회 불가". Route these to
        # SUPPORT so the 픽업서비스 rule answers with the pickup management CTA.
        (
            [
                "픽업기사", "픽업 기사",
                "기사님 어디", "기사 어디",
                "기사님 위치", "기사 위치",
                "기사님 오고", "기사 오고",
                "기사님 도착", "기사 도착",
                "기사님 언제", "기사 언제",
            ],
            MultiAgentDomain.Domain.SUPPORT,
        ),
        # SUPPORT — return / refund / warranty / 1:1
        (
            [
                "정비이력", "정비 이력",
                "정비내역", "정비 내역",
                "관리받은 내역", "관리 받은 내역",
                "관리받은 거", "관리 받은 거",
                "서비스 이력", "서비스 내역",
                "받은 서비스", "받은 정비",
            ],
            MultiAgentDomain.Domain.TRANSACTION,
        ),
        (
            ["1:1 문의", "상담원 연결", "환불", "반품", "교환", "보증", "워런티"],
            MultiAgentDomain.Domain.SUPPORT,
        ),
        # SUPPORT — online-only product policy / online vs in-store purchase (TC-028, TC-104).
        # Keep this narrower than "온라인 전용" so the CTA label "온라인 전용 상품 보기"
        # can still route to Discovery instead of looping back to FAQ.
        (
            [
                "온전용",
                "매장 가서 사는",
                "매장 방문해서도 구매",
                "매장에서도 구매",
                "온라인에서만",
                "온라인에서만 사야",
                # generic online vs in-store price difference queries
                "매장에서 구매하는거랑 온라인",
                "매장 구매랑 온라인",
                "온라인 주문이랑 매장",
                "온라인이랑 매장 가격 차이",
                "매장 가격 온라인 가격",
                "매장에서 사는 거랑 온라인",
                "매장 가서 직접 사는 거랑 온라인",
                "매장 가서 직접 사는",
                "매장에서 사는거랑 온라인",
            ],
            MultiAgentDomain.Domain.SUPPORT,
        ),
        # SUPPORT — Jeju/island-mountain shipping-fee policy (TC-057).
        # Policy questions about regional surcharge should use FAQ guidance, not store search.
        (
            [
                "도서산간",
                "제주도 매장에서도 온라인 가격",
                "제주 배송비",
                "제주도 배송비",
                "서귀포시인데 배송비",
                "서귀포 배송비",
                "배송비 더 들어",
                "추가 배송비",
            ],
            MultiAgentDomain.Domain.SUPPORT,
        ),
        # DISCOVERY — vehicle lookup / video / event
        (
            [
                "내 차 목록", "내차 목록", "내차목록",
                "내 차량", "내차량",
                "내 등록차", "등록차 보여", "등록차량 보여", "등록차량", "등록차",
                "내 차 보여", "내차 보여", "내차보여",
                "내 차 중", "내 차중", "내차 중", "내차중",
                "리뷰 영상", "유튜브", "동영상", "영상 보여",
                "이벤트", "기획전",
            ],
            MultiAgentDomain.Domain.DISCOVERY,
        ),
        # TRANSACTION — coupon list inquiry (topic shift mid-flow must override
        # recommendation/order context bias that otherwise traps the LLM router
        # in DISCOVERY and triggers hallucinated "혜택 영역으로 안내" deflections).
        (
            [
                "내 쿠폰", "내쿠폰",
                "쿠폰함",
                "쿠폰 목록", "쿠폰목록",
                "보유 쿠폰", "보유쿠폰",
                "사용 가능한 쿠폰", "사용가능한 쿠폰",
            ],
            MultiAgentDomain.Domain.TRANSACTION,
        ),
        # TRANSACTION — Smart Pay installment calculation is a price/payment
        # question. Keep it out of Discovery even when a product name appears.
        (
            ["스마트페이", "스마트 페이", "Smart Pay", "smart pay", "SmartPay", "smartpay"],
            MultiAgentDomain.Domain.TRANSACTION,
        ),
    ]

    def __init__(self):
        self.agent_map = {
            MultiAgentDomain.Domain.DISCOVERY: discovery_subagent,
            MultiAgentDomain.Domain.TRANSACTION: transaction_subagent,
            MultiAgentDomain.Domain.SUPPORT: support_subagent,
            MultiAgentDomain.Domain.LEADING: leading_agent,
        }

    def _select_agent(self, domain: MultiAgentDomain.Domain, routing: MultiAgentDomain | None):
        agent = self.agent_map.get(domain)
        if agent is None:
            return None
        profile = getattr(routing, "agent_prompt_profile", AgentPromptProfile.FULL)
        if domain in (MultiAgentDomain.Domain.TRANSACTION, MultiAgentDomain.Domain.DISCOVERY) and hasattr(
            agent, "for_prompt_profile"
        ):
            profile_value = profile.value if isinstance(profile, AgentPromptProfile) else str(profile)
            selected_agent = agent.for_prompt_profile(profile_value)
            logger.info(
                "[AGENT_PROFILE] domain=%s profile=%s agent=%s",
                domain.value,
                profile_value,
                getattr(selected_agent, "name", selected_agent.__class__.__name__),
            )
            return selected_agent
        return agent

    @staticmethod
    def _resolve_routing_for_agent_profile(
        classify_future: concurrent.futures.Future | None,
        domains: list[MultiAgentDomain.Domain],
    ) -> MultiAgentDomain | None:
        if classify_future is None:
            return None

        if MultiAgentDomain.Domain.TRANSACTION in domains:
            timeout: float | None = None
        elif MultiAgentDomain.Domain.DISCOVERY in domains:
            timeout = 0 if classify_future.done() else _DISCOVERY_PROFILE_CLASSIFIER_TIMEOUT_S
        elif classify_future.done():
            timeout = 0
        else:
            return None

        try:
            verified_domains, routing_result = classify_future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            timeout_ms = timeout * 1000 if timeout is not None else 0
            logger.warning("[COORDINATOR] classifier profile not ready after %.0fms", timeout_ms)
            return None
        except Exception as exc:
            logger.warning("[COORDINATOR] classifier profile unavailable before agent selection: %s", exc)
            return None

        if routing_result is None or not _domains_equal(verified_domains, domains):
            return None
        return routing_result

    # Korean license plate + owner name pattern (e.g. "14다5499 이동주", "12가3456 홍길동").
    # When the user provides this exact combo alone, the LLM classifier sometimes routes
    # to `discovery_search` profile, which does NOT expose `get_user_vehicles_tool` /
    # `get_my_cars_tool` / `check_compatibility_tool`. The agent then hallucinates a
    # "찾지 못했어요" reply without calling the carzen API. Force DISCOVERY +
    # `discovery_recommendation` profile so the vehicle-lookup tool is available.
    _CAR_NO_OWNER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*\d{2,3}[가-힣]\d{4}\s+[가-힣]{2,4}\s*$"
    )

    @staticmethod
    def _extract_current_user_input(message_content: str) -> str:
        """Strip the injected `# Respond in Korean language` wrapper and the
        trailing `[current_time: ...]` block so the result is just the user's
        typed text.
        """
        if not message_content:
            return ""
        text = message_content
        if "# Respond in Korean language" in text:
            text = text.split("# Respond in Korean language", 1)[1]
        if "[current_time:" in text:
            text = text.split("[current_time:", 1)[0]
        return text.strip()

    @classmethod
    def _force_keyword_routing(cls, user_input: str) -> "MultiAgentDomain | None":
        """Return a forced MultiAgentDomain when the user's CURRENT message
        clearly names a topic that should not depend on conversation context.

        Returns None when no keyword matches — caller should then fall through
        to the LLM-based router.
        """
        if not user_input:
            return None
        text = user_input.strip()
        if not text:
            return None

        # Regex force — license plate + owner name → DISCOVERY_RECOMMENDATION profile.
        if cls._CAR_NO_OWNER_RE.match(text):
            return MultiAgentDomain(
                reason="regex routing matched license-plate + owner-name pattern",
                domains=[MultiAgentDomain.Domain.DISCOVERY],
                execution_plan=[
                    "Call get_user_vehicles_tool(car_no, owner_nm) → "
                    "proceed to RECOMMEND ENGINE with returned tire_size",
                ],
                user_behavior="providing vehicle number and owner name to identify the vehicle",
                agent_prompt_profile=AgentPromptProfile.DISCOVERY_RECOMMENDATION,
                flow="hardcoded regex routing — bypassed LLM router",
            )

        for keywords, domain in cls._KEYWORD_FORCE_TABLE:
            for kw in keywords:
                if kw in text:
                    return MultiAgentDomain(
                        reason=f"hardcoded keyword routing matched '{kw}'",
                        domains=[domain],
                        execution_plan=[f"Run {domain.value} for the matched current-turn topic"],
                        user_behavior=f"topic shift via keyword '{kw}'",
                        agent_prompt_profile=(
                            AgentPromptProfile.TRANSACTION_ORDER
                            if domain == MultiAgentDomain.Domain.TRANSACTION
                            and any(
                                order_kw in text
                                for order_kw in (
                                    "취소", "택배비", "왕복 배송비", "반품 비용", "반품수수료",
                                    "정비이력", "정비 이력", "정비내역", "정비 내역",
                                    "관리받은", "관리 받은", "서비스 이력", "서비스 내역",
                                    "받은 서비스", "받은 정비",
                                )
                            )
                            else AgentPromptProfile.FULL
                        ),
                        flow="hardcoded keyword routing — bypassed LLM router",
                    )
        return None

    def classify_multi_intent(
        self,
        messages: list,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> tuple[list[MultiAgentDomain.Domain], MultiAgentDomain | None]:
        """Classify user message into one or more domains.

        First turn (no prior history) uses a slim schema + slim prompt to skip
        narrative fields. Multi-turn keeps the full schema + prompt because
        user_behavior / flow carry real signal once history exists.

        Both paths use DECISION_LLM (small/fast model) — routing is a low-reasoning
        task and the schemas are descriptive only, so the small model has no
        prescriptive tool-signature field to hallucinate in.

        Returns:
            (domains, routing_result) — domains for backward compat, full result for context injection.
        """
        from langchain_core.messages import SystemMessage

        # ---------- Hardcoded keyword routing (bypasses LLM) ----------
        last_user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_text = self._extract_current_user_input(msg.get("content", ""))
                break

        forced_result = self._force_keyword_routing(last_user_text)
        if forced_result is not None:
            logger.debug(
                "[MULTI-DOMAIN] Hardcoded routing: domain=%s, msg=%r",
                forced_result.domains,
                last_user_text[:80],
            )
            return forced_result.domains, forced_result
        # --------------------------------------------------------------

        # First turn = single user message, no prior conversation history.
        is_first_turn = len(messages) == 1 and messages[0].get("role") == "user"

        try:
            if is_first_turn:
                structured_model = _slim_intent_model
                system_msg = SystemMessage(content=prompt_router_slim())
                run_name = "classify_multi_intent_slim"
            else:
                structured_model = _multi_intent_model
                system_msg = SystemMessage(content=prompt_router_multi())
                run_name = "classify_multi_intent"

            all_messages = [system_msg] + list(messages)

            trace_config = build_trace_config(
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                tags=["router", run_name],
                prompt_name="router",
                run_name=f"💭 {run_name}",
            )
            raw_result = structured_model.invoke(all_messages, config=trace_config)

            # Normalize slim result to MultiAgentDomain for downstream compat.
            # Empty narrative fields short-circuit _inject_conversation_context.
            if is_first_turn:
                result = MultiAgentDomain(
                    reason=raw_result.reason,
                    domains=raw_result.domains,
                    execution_plan=raw_result.execution_plan,
                    user_behavior="",
                    agent_prompt_profile=raw_result.agent_prompt_profile,
                    flow="",
                )
            else:
                result = raw_result

            # Deterministic profile override — datepick selection turn must use FULL profile.
            # FE 가 datepick 슬롯 클릭 시 보내는 메시지 패턴 "YYYY년 M월 D일 (요일)\nHH:MM"
            # 은 routing prompt L325 의 `full` profile 룰에 명시되어 있지만, 분류 LLM
            # (gpt-4.1-mini) 이 직전 대화 컨텍스트 (datepick 카드 = store schedule) 에
            # 가려 `transaction_store` 로 분류하는 회귀가 반복. narrow 프로필은 STEP 5.5
            # PRE-ORDER PREVIEW 룰을 못 보므로 datepick → preOrder 흐름이 끊기고 dead-end
            # chip ("1:1 문의하기"/"처음으로") 으로 빠진다. 분류기 출력 무관하게 강제 override.
            if (
                last_user_text
                and _DATEPICK_SELECTION_RE.match(last_user_text)
                and MultiAgentDomain.Domain.TRANSACTION in (result.domains or [])
                and result.agent_prompt_profile != AgentPromptProfile.FULL
            ):
                logger.info(
                    "[MULTI-DOMAIN] Datepick pattern detected — forcing profile %s → FULL",
                    result.agent_prompt_profile,
                )
                result.agent_prompt_profile = AgentPromptProfile.FULL

            logger.debug(
                f"[MULTI-DOMAIN] Classification result: domain={result.domains}, "
                f"plan={result.execution_plan!r}, behavior={result.user_behavior!r}, "
                f"flow={result.flow!r}, profile={result.agent_prompt_profile!r}"
            )
            domains = result.domains if result.domains else [MultiAgentDomain.Domain.LEADING]
            return domains, result

        except Exception as e:
            logger.exception(f"[MULTI-DOMAIN] Classification failed: {e}")
            return [MultiAgentDomain.Domain.LEADING], None

    @staticmethod
    def _inject_conversation_context(messages: list[dict], routing: MultiAgentDomain | None) -> list[dict]:
        """Inject conversation context (user_behavior, flow) above the Korean instruction
        in the last user message.

        The current last user message already has the format:
            # Respond in Korean language
            <original user text>

        After injection:
            ## CONVERSATION CONTEXT
            - User behavior: ...
            - Flow so far: ...

            # Respond in Korean language
            <original user text>
        """
        if routing is None:
            return messages

        # Only inject if at least one field is non-empty
        context_parts = []
        if routing.user_behavior:
            context_parts.append(f"- User behavior: {routing.user_behavior}")
        if routing.flow:
            context_parts.append(f"- Flow so far: {routing.flow}")

        if not context_parts:
            return messages

        context_block = "## CONVERSATION CONTEXT\n" + "\n".join(context_parts) + "\n"

        # Find last user message and prepend the context block above "# Respond in Korean language"
        messages = [dict(m) for m in messages]
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                content = messages[i]["content"]
                if content.startswith("# Respond in Korean language"):
                    messages[i]["content"] = context_block + "\n" + content
                else:
                    messages[i]["content"] = context_block + "\n# Respond in Korean language\n" + content
                break

        return messages

    @staticmethod
    def _inject_client_prompt(messages: list[dict]) -> list[dict]:
        """Inject client custom prompt from Langfuse as a system message.

        Client sets the prompt on Langfuse UI under the name 'client_prompt'.
        Changes propagate within ~60 seconds, no redeploy needed.
        If no prompt is configured, messages are returned unchanged.
        """
        injection = load_client_injection()
        if not injection:
            logger.debug("[CLIENT_PROMPT] No client prompt configured, skipping injection.")
            return messages

        system_msg = {"role": "system", "content": f"## CLIENT INSTRUCTIONS\n{injection}"}
        logger.debug("[CLIENT_PROMPT] Injected as system message (chars=%d).", len(injection))
        return [system_msg] + list(messages)

    @staticmethod
    def _planner_decision(
        domains: list[MultiAgentDomain.Domain],
        routing: MultiAgentDomain | None,
        current_domain: MultiAgentDomain.Domain,
    ) -> AgentDecision | None:
        if routing is None or len(domains) < 2:
            return None
        if not routing.execution_plan:
            return None
        if current_domain not in domains:
            return None
        next_index = domains.index(current_domain) + 1
        if next_index >= len(domains):
            return AgentDecision(
                next_action=NextAction.STOP,
                next_domain="null",
                reason="planner_execution_plan_completed",
            )
        return AgentDecision(
            next_action=NextAction.CONTINUE,
            next_domain=domains[next_index].value,
            reason="planner_execution_plan",
        )

    def _build_context_message(
        self,
        domain: MultiAgentDomain.Domain,
        accumulated_context: dict,
    ) -> dict | None:
        """Build context message from previous agent results."""
        if not accumulated_context:
            return None

        parts = []
        for dom, content in accumulated_context.items():
            if content:
                parts.append(f"- {dom}: {content[:5000]}")  # Truncate to avoid bloat

        if not parts:
            return None

        return {"role": "assistant", "content": "[Context from previous steps]\n" + "\n".join(parts)}

    # Tool → pending_intent that the tool FULFILLS (clears from slots on successful run).
    # When one of these tools returns a successful result, the matching pending_intent
    # is considered satisfied and cleared, so later turns don't re-route on a stale intent.
    _TOOL_TO_FULFILL: ClassVar[dict[str, str]] = {
        "get_final_price_tool": "price",
        "get_logistics_inventory_tool": "stock",
        "get_store_inventory_tool": "stock",
        "quick_order_tool": "order",
        "save_to_cart_tool": "order",
    }

    @staticmethod
    def _apply_tool_derived_slots(slots: Any, tool_name: str, parsed_data: dict, tool_input: dict | None = None) -> bool:
        """Apply tool-derived slot changes in memory; caller persists once after streaming."""
        from schemas.tstation.slots import ConversationSlots

        changed = False

        fulfilled_intent = StreamingMultiAgentCoordinator._TOOL_TO_FULFILL.get(tool_name)
        tool_succeeded = isinstance(parsed_data, dict) and parsed_data.get("status") == "success"
        if fulfilled_intent and tool_succeeded and slots.pending_intent == fulfilled_intent:
            slots.pending_intent = None
            changed = True
            logger.debug(
                f"[SLOTS] Cleared pending_intent={fulfilled_intent!r} after {tool_name} completed successfully"
            )

        if tool_name == "search_car_model_tool" and (slots.tire_size is not None or slots.goods_no is not None):
            slots.tire_size = None
            slots.goods_no = None
            changed = True
            logger.debug("[SLOTS] Reset tire_size and goods_no due to search_car_model_tool call")

        tool_slots = {}
        if tool_name == "get_products_recommendations_tool" and tool_input:
            input_tire_size = tool_input.get("tire_size")
            if input_tire_size:
                tool_slots["tire_size"] = input_tire_size

        if tool_name == "get_product_description_tool" and tool_input:
            input_goods_no = tool_input.get("goods_no")
            if input_goods_no:
                tool_slots["goods_no"] = input_goods_no

        # `get_store_schedule_tool` / `get_store_detail_tool` 은 사용자가 매장을 확정한 뒤
        # 호출되는 도구다 (datepick / 매장 상세 페이지 진입). list-tool 의 result-count
        # 가드와 무관하게, agent 가 shop_id 를 input 으로 전달했다는 사실 자체가 그
        # 매장이 사용자의 확정 선택임을 의미한다. 이 값을 슬롯에 persist 하지 않으면
        # place_order goal 의 `shop` step 이 풀리지 않아 state header 가 "다음: 매장 선택"
        # 으로 남고, datepick 이후 "주문 진행하기" chip click 턴에서 agent 가 매장
        # chip 을 다시 emit 하는 루프가 발생한다.
        if tool_name in ("get_store_schedule_tool", "get_store_detail_tool") and tool_input:
            input_shop_id = tool_input.get("shop_id")
            if input_shop_id:
                tool_slots["shop_id"] = input_shop_id

        # 결제금액 slot 산출: get_final_price_tool 성공 + ord_qty 슬롯 보유 시
        # `payment_amount = (extra_fvr_sale_prc + wage_prc) * ord_qty` 로 계산.
        # template_mapper 의 orderComplete payment_amount 계산식과 동일.
        # 산출된 슬롯은 다음 턴 LLM 컨텍스트(`[확인된 고객 정보]`)에 "결제금액"으로
        # 노출되어, 할부 계산 같은 후속 질문에서 LLM 이 단가·수량을 임의로 곱해
        # 가짜 총액을 만들지 않도록 한다.
        if tool_name == "get_final_price_tool" and tool_succeeded:
            price_data = parsed_data.get("data", parsed_data)
            if isinstance(price_data, dict):
                final_unit = price_data.get("extra_fvr_sale_prc") or price_data.get("sale_prc")
                wage = price_data.get("wage_prc") or 0
                qty = slots.ord_qty
                if final_unit is not None and qty is not None and qty > 0:
                    try:
                        tool_slots["payment_amount"] = int((int(final_unit) + int(wage)) * int(qty))
                    except (TypeError, ValueError):
                        logger.debug(
                            "[SLOTS] payment_amount calc skipped: non-numeric inputs "
                            f"(final_unit={final_unit!r}, wage={wage!r}, qty={qty!r})"
                        )

        tool_slot_extractors = {
            "search_product_tool": ["goods_no"],
            "get_store_list_tool": ["shop_id"],
            "get_nearby_stores_tool": ["shop_id"],
            "get_store_inventory_tool": ["shop_id"],
        }
        fields = tool_slot_extractors.get(tool_name)
        if fields:
            data = parsed_data.get("data", parsed_data)
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
                data = items[0] if isinstance(items, list) and len(items) == 1 else None
            elif isinstance(data, dict) and "stores" in data:
                stores = data["stores"]
                data = stores[0] if isinstance(stores, list) and len(stores) == 1 else None

            if isinstance(data, dict):
                for field in fields:
                    val = data.get(field)
                    if val:
                        tool_slots[field] = val

        if tool_slots:
            updated = slots.merge(ConversationSlots(**tool_slots))
            if updated.model_dump() != slots.model_dump():
                slots.__dict__.update(updated.__dict__)
                changed = True
                logger.debug(f"[SLOTS] Tool-derived slots staged from {tool_name}: {tool_slots}")

        return changed

    def stream(
        self,
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
        slot_context: str | None = None,
        session_id: str | None = None,
        tool_context: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        skip_decision: bool = False,
        slot_context_with_intent: str | None = None,
        classify_future: concurrent.futures.Future | None = None,
        speculative_guard: dict | None = None,
        routing_result: MultiAgentDomain | None = None,
        initial_slots: Any | None = None,
    ) -> Iterator[dict]:
        """
        Chain multiple agents and stream their outputs.

        Args:
            messages: Original user messages
            domains: Pre-classified domains (optional, will classify if not provided)
            slot_context: Formatted slot context string (WITHOUT pending_intent block).
                Default for Discovery / Support / Leading agents.
            session_id: Session ID for persisting tool-derived slots (goods_no, shop_id)
            tool_context: Formatted tool results from previous turn for context preservation
            user_id: User ID for Langfuse tracing
            trace_id: Trace ID to group all LLM calls of this request under one trace
            skip_decision: When True AND domains has >= 2 entries, skip the
                `decide_next_action` LLM call between the first and second agent
                (the chain is pre-committed by the caller — e.g., P0 code gate).
            slot_context_with_intent: Slot context WITH pending_intent block.
                Injected ONLY for the Transaction agent — that agent acts directly
                on the intent (Flow 1 price / Flow 2-3 stock / Flow 6 order).
                Discovery / Support / Leading must route purely from prior
                conversation context, never from a stale intent slot, so they keep
                receiving `slot_context` (no intent block) instead.
                When None (no pending_intent set), Transaction also receives plain
                `slot_context`.

        Yields:
            Stream events from all agents in sequence
        """
        # Classify if domains not provided
        # Save original messages before CONVERSATION CONTEXT injection for UI Template Agent
        original_messages = list(messages)
        if domains is None:
            domains, routing_result = self.classify_multi_intent(
                messages,
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
            )
            messages = StreamingMultiAgentCoordinator._inject_conversation_context(messages, routing_result)

        if not domains:
            domains = [MultiAgentDomain.Domain.LEADING]

        logger.debug(f"[COORDINATOR] Streaming for domains: {[d.value for d in domains]}")

        accumulated_context = {}
        accumulated_tool_data = []  # Collect tool outputs for UI Template Agent
        domain_data_event_emitted = False  # Domain agent emitted a `data` event itself
        pending_slots = initial_slots.model_copy() if initial_slots is not None else None
        pending_slots_dirty = False

        is_first_agent = True
        decision_verify_future: concurrent.futures.Future | None = None
        decision_guard: dict | None = None
        active_routing_result = routing_result
        if active_routing_result is None:
            active_routing_result = self._resolve_routing_for_agent_profile(classify_future, domains)

        for domain in domains:
            agent = self._select_agent(domain, active_routing_result)
            if not agent:
                logger.warning(f"[COORDINATOR] No agent found for domain: {domain}")
                continue

            # Build enriched messages with context from previous agents
            # Order: slot_context | messages (with user_context inside) | current_user_msg LAST | accumulated_context LAST
            enriched_messages = []

            # 1. slot_context FIRST
            # Per-domain slot context: only the Transaction agent sees the
            # `[사용자의 진행 중인 요청]` block, since it is the only agent that
            # acts directly on the intent slot. Other agents would otherwise let
            # a stale intent silently override their conversation-history-based
            # routing (e.g., Discovery would emit "바로 가격 조회로 이어갑니다"
            # on a recommendation pick instead of calling
            # `get_product_description_tool`).
            if domain == MultiAgentDomain.Domain.TRANSACTION and slot_context_with_intent:
                domain_slot_context = slot_context_with_intent
            else:
                domain_slot_context = slot_context

            if domain_slot_context:
                enriched_messages.append(
                    {
                        "role": "assistant",
                        "content": domain_slot_context,
                    }
                )

            # 1.5. tool_context from previous turn (structured tool results)
            if tool_context:
                enriched_messages.append(
                    {
                        "role": "assistant",
                        "content": tool_context,
                    }
                )

            # 2. Original messages (already contains user_context from _build_messages_with_user_info)
            #    These messages have current_user_msg at the LAST position
            enriched_messages.extend(list(messages))

            # 3. Append accumulated_context AFTER current_user_msg (for handover agents)
            if accumulated_context:
                for prev_domain, content in accumulated_context.items():
                    if content and content.strip():
                        enriched_messages.append({"role": "assistant", "content": str(content)})
                        enriched_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Based on the previous agent's findings above, produce a SINGLE unified response for the user. "
                                    "Include key findings from the previous agent (e.g., compatibility results, product info) and "
                                    "seamlessly add your own results (e.g., pricing, inventory, store info). "
                                    "Do NOT repeat introductory greetings or offer intermediate choices that are already resolved. "
                                    "The response must read as ONE coherent answer, not two separate answers concatenated together."
                                ),
                            }
                        )
                        logger.debug(f"[COORDINATOR] Passing context to {domain.value}")
                        break  # Only take first previous agent

            # 4. Append accumulated_tool_data LAST (for UI Template Agent)
            if accumulated_tool_data:
                # Extract ord_qty from user messages when chaining to Transaction Agent
                if domain == MultiAgentDomain.Domain.TRANSACTION:
                    has_ord_qty = any(
                        isinstance(item.get("data"), dict) and "ord_qty" in item.get("data", {})
                        for item in accumulated_tool_data
                    )
                    if not has_ord_qty:
                        user_text = " ".join(msg.get("content", "") for msg in messages if msg.get("role") == "user")
                        qty_match = re.search(r"(\d+)\s*개", user_text)
                        if qty_match:
                            ord_qty = int(qty_match.group(1))
                            accumulated_tool_data.append({"tool": "user_intent", "data": {"ord_qty": ord_qty}})
                            logger.debug(f"[COORDINATOR] Extracted ord_qty={ord_qty} from user message")

                llm_tool_data = StreamingMultiAgentCoordinator._compact_tool_results_for_llm(accumulated_tool_data)
                tool_summary = json.dumps(llm_tool_data, ensure_ascii=False, separators=(",", ":"))
                enriched_messages.append(
                    {"role": "assistant", "content": f"[Previous agent tool facts]\n{tool_summary}"}
                )
                logger.debug(f"[COORDINATOR] Passing {len(accumulated_tool_data)} tool results to {domain.value}")

            domain_key = domain.value
            # logger.debug(
            #     f"[COORDINATOR_MESSAGE] Domain: {domain_key}, enriched_messages: {json.dumps(enriched_messages, ensure_ascii=False, indent=2)}"
            # )

            speculative_buffer: list[dict] = []
            active_speculative_guard = speculative_guard or decision_guard
            classifier_done = threading.Event()
            classifier_result: tuple[list[MultiAgentDomain.Domain], MultiAgentDomain | None] | None = None
            restart_routing_result: MultiAgentDomain | None = None

            if classify_future is not None:
                def _on_classify_done(future: concurrent.futures.Future):
                    nonlocal classifier_result
                    classified_domains, routing = future.result()
                    classifier_result = (_normalize_domains(classified_domains), routing)
                    classifier_done.set()

                classify_future.add_done_callback(_on_classify_done)

            def _flush_speculative_buffer() -> Iterator[dict]:
                nonlocal speculative_buffer
                yield from speculative_buffer
                speculative_buffer = []

            def _buffer_or_emit(evt: dict) -> Iterator[dict]:
                if classify_future is None:
                    yield evt
                    return
                speculative_buffer.append(evt)

            def _verify_speculative_branch() -> tuple[bool, list[MultiAgentDomain.Domain], MultiAgentDomain | None]:
                nonlocal classify_future, classifier_result
                if classify_future is None:
                    return True, domains, None
                if classifier_result is None:
                    classified_domains, routing = classify_future.result()
                    classifier_result = (_normalize_domains(classified_domains), routing)
                classify_future = None
                verified_domains, routing_result = classifier_result
                return _domains_equal(verified_domains, domains), verified_domains, routing_result

            def _wait_for_speculative_confirmation() -> bool:
                is_match, verified_domains, verified_routing_result = _verify_speculative_branch()
                if is_match:
                    if speculative_guard:
                        speculative_guard["confirm_event"].set()
                    return True
                if speculative_guard:
                    speculative_guard["mismatch_domains"] = verified_domains
                    speculative_guard["routing_result"] = verified_routing_result
                return False

            # Yield agent start event
            yield from _buffer_or_emit({
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "start",
            })

            # Stream from agent and yield events immediately after speculation is confirmed
            full_response = ""
            last_agent_called_tools = False
            agent_tools_called: list[str] = []
            agent_declared_decision: AgentDecision | None = None
            restart_domains: list[MultiAgentDomain.Domain] | None = None

            # Last user message becomes the agent span's input — keeps the
            # trace readable instead of dumping the entire enriched_messages
            # array (which includes slot/tool context blocks).
            _agent_input_msg = next(
                (m.get("content", "") for m in reversed(enriched_messages) if m.get("role") == "user"),
                "",
            )
            _agent_prompt_chars = getattr(agent, "system_prompt_chars", 0)
            _agent_input_chars = sum(len(str(m.get("content", ""))) for m in enriched_messages)
            _agent_message_count = len(enriched_messages)
            _agent_started_at = time.perf_counter()
            _agent_first_tool_ms: float | None = None
            _agent_first_visible_ms: float | None = None
            _agent_first_token_ms: float | None = None
            _agent_first_data_ms: float | None = None

            with _trace_span(
                f"agent:{domain_key}",
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                input=_agent_input_msg,
            ) as _agent_span:
                # Nest LangChain auto-captured spans (LLM generations, tools)
                # under this manual agent span. Falls back to the chat root
                # when tracing is disabled (span.id is None).
                agent_trace_config = build_trace_config(
                    session_id=session_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    parent_span_id=_agent_span.id or parent_span_id,
                    tags=[domain_key, "agent"],
                    prompt_name=f"{domain_key}_agent",
                    run_name=f"💭 {domain_key}_agent",
                )
                if active_speculative_guard:
                    if active_speculative_guard is speculative_guard:
                        active_speculative_guard["wait_for_confirmation"] = _wait_for_speculative_confirmation
                    agent_trace_config.setdefault("configurable", {})["speculative_tool_guard"] = active_speculative_guard
                for event in agent.stream(enriched_messages, config=agent_trace_config):
                    _elapsed_ms = (time.perf_counter() - _agent_started_at) * 1000
                    if speculative_buffer and active_speculative_guard and active_speculative_guard["confirm_event"].is_set():
                        yield from _flush_speculative_buffer()
                    if classify_future is not None and classifier_done.is_set():
                        is_match, verified_domains, verified_routing_result = _verify_speculative_branch()
                        if is_match:
                            logger.debug(
                                "[COORDINATOR] speculative confirmed: %s — flushing %d events",
                                [d.value for d in verified_domains],
                                len(speculative_buffer),
                            )
                            if speculative_guard:
                                speculative_guard["confirm_event"].set()
                            yield from _flush_speculative_buffer()
                        else:
                            logger.debug(
                                "[COORDINATOR] speculative mismatch during %s: predicted=%s classify=%s",
                                domain.value,
                                [d.value for d in domains],
                                [d.value for d in verified_domains],
                            )
                            restart_domains = verified_domains
                            restart_routing_result = verified_routing_result
                            break

                    # Tag with source domain for UI
                    event["source_domain"] = domain_key
                    event_type = event.get("type")
                    if (
                        _agent_first_visible_ms is None
                        and (
                            event_type == "data"
                            or (event_type in {"token", "message"} and bool(event.get("content")))
                        )
                    ):
                        _agent_first_visible_ms = _elapsed_ms
                    if _agent_first_token_ms is None and event_type == "token" and event.get("content"):
                        _agent_first_token_ms = _elapsed_ms
                    if _agent_first_data_ms is None and event_type == "data":
                        _agent_first_data_ms = _elapsed_ms

                    # Track direct data events emitted by the domain agent (JSON output).
                    # When present, skip the UI Template stage below.
                    if event_type == "data":
                        domain_data_event_emitted = True
                        parsed_decision = _parse_agent_declared_next_action(event.pop("nextAction", None))
                        if parsed_decision is not None:
                            agent_declared_decision = parsed_decision
                            logger.debug(
                                "[COORDINATOR] Agent-declared nextAction accepted: %s -> %s",
                                parsed_decision.next_action.value,
                                parsed_decision.next_domain,
                            )
                    yield from _buffer_or_emit(event)

                    # Capture message content for context passing
                    if event_type == "message":
                        content = event.get("content", "")
                        if content:
                            accumulated_context[domain_key] = content
                            full_response = content
                            logger.debug(f"[COORDINATOR] Captured message for {domain_key}: {content}...")

                    # Capture tool outputs for UI Template Agent
                    if event_type == "tool":
                        if _agent_first_tool_ms is None:
                            _agent_first_tool_ms = _elapsed_ms
                        last_agent_called_tools = True
                        tool_name = event.get("tool", "")
                        if tool_name:
                            agent_tools_called.append(tool_name)
                        tool_output = event.get("output", "")
                        if tool_output:
                            try:
                                parsed = json.loads(tool_output) if isinstance(tool_output, str) else tool_output
                                accumulated_tool_data.append({
                                    "tool": tool_name,
                                    "input": event.get("input", {}),
                                    "data": parsed,
                                })

                                # Stage tool-derived slot changes in memory; persist once after streaming.
                                if pending_slots is not None and isinstance(parsed, dict):
                                    pending_slots_dirty = self._apply_tool_derived_slots(
                                        pending_slots, tool_name, parsed, event.get("input", {})
                                    ) or pending_slots_dirty

                            except (json.JSONDecodeError, TypeError):
                                accumulated_tool_data.append({
                                    "tool": tool_name,
                                    "input": event.get("input", {}),
                                    "data": tool_output,
                                })

                # One-line story summary leads the dict so Langfuse's tree preview
                # reads like "discovery → search_product_tool, get_product_description_tool → data".
                _tools_label = ", ".join(agent_tools_called) if agent_tools_called else "no tools"
                _data_label = "data" if domain_data_event_emitted else "text"
                _agent_summary = f"{domain_key} → {_tools_label} → {_data_label}"
                _agent_total_ms = (time.perf_counter() - _agent_started_at) * 1000
                logger.debug(
                    "[AGENT_METRICS] domain=%s total_ms=%.0f first_visible_ms=%s first_tool_ms=%s "
                    "first_token_ms=%s first_data_ms=%s prompt_chars=%d input_chars=%d messages=%d tools=%d",
                    domain_key,
                    _agent_total_ms,
                    f"{_agent_first_visible_ms:.0f}" if _agent_first_visible_ms is not None else "n/a",
                    f"{_agent_first_tool_ms:.0f}" if _agent_first_tool_ms is not None else "n/a",
                    f"{_agent_first_token_ms:.0f}" if _agent_first_token_ms is not None else "n/a",
                    f"{_agent_first_data_ms:.0f}" if _agent_first_data_ms is not None else "n/a",
                    _agent_prompt_chars,
                    _agent_input_chars,
                    _agent_message_count,
                    len(agent_tools_called),
                )
                _agent_span.update(
                    output=_truncate({
                        "summary": _agent_summary,
                        "response": full_response,
                        "tools_called": agent_tools_called,
                        "data_event_emitted": domain_data_event_emitted,
                        "metrics": {
                            "total_ms": round(_agent_total_ms, 1),
                            "first_visible_ms": round(_agent_first_visible_ms, 1)
                            if _agent_first_visible_ms is not None else None,
                            "first_tool_ms": round(_agent_first_tool_ms, 1)
                            if _agent_first_tool_ms is not None else None,
                            "first_token_ms": round(_agent_first_token_ms, 1)
                            if _agent_first_token_ms is not None else None,
                            "first_data_ms": round(_agent_first_data_ms, 1)
                            if _agent_first_data_ms is not None else None,
                            "system_prompt_chars": _agent_prompt_chars,
                            "input_chars": _agent_input_chars,
                            "message_count": _agent_message_count,
                        },
                    }),
                )

            if restart_domains is None and speculative_guard and speculative_guard.get("mismatch_domains"):
                restart_domains = speculative_guard.get("mismatch_domains")
                restart_routing_result = speculative_guard.get("routing_result")
                logger.debug(
                    "[COORDINATOR] speculative mismatch before mutating tool: predicted=%s classify=%s",
                    [d.value for d in domains],
                    [d.value for d in restart_domains],
                )

            if restart_domains is None and classify_future is not None:
                is_match, verified_domains, verified_routing_result = _verify_speculative_branch()
                if is_match:
                    if speculative_guard:
                        speculative_guard["confirm_event"].set()
                    logger.debug(
                        "[COORDINATOR] speculative confirmed after %s finished — flushing %d events",
                        domain.value,
                        len(speculative_buffer),
                    )
                    yield from _flush_speculative_buffer()
                else:
                    restart_domains = verified_domains
                    restart_routing_result = verified_routing_result
                    logger.debug(
                        "[COORDINATOR] speculative mismatch after %s finished: predicted=%s classify=%s",
                        domain.value,
                        [d.value for d in domains],
                        [d.value for d in restart_domains],
                    )

            if restart_domains:
                if speculative_guard:
                    speculative_guard["confirm_event"].set()
                restart_messages = StreamingMultiAgentCoordinator._inject_conversation_context(
                    original_messages, restart_routing_result
                )
                logger.debug(
                    "[COORDINATOR] discarding speculative %s branch; restarting with %s",
                    domain.value,
                    [d.value for d in restart_domains],
                )
                yield from self.stream(
                    messages=restart_messages,
                    domains=restart_domains,
                    slot_context=slot_context,
                    session_id=session_id,
                    tool_context=tool_context,
                    user_id=user_id,
                    trace_id=trace_id,
                    parent_span_id=parent_span_id,
                    skip_decision=skip_decision,
                    slot_context_with_intent=slot_context_with_intent,
                    routing_result=restart_routing_result,
                    initial_slots=pending_slots,
                )
                return

            # Yield agent completion event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "done",
            }

            if decision_verify_future is not None and decision_verify_future.done():
                verified_decision = decision_verify_future.result()
                mismatch_decision = decision_guard.get("mismatch_decision") if decision_guard else None
                if mismatch_decision is None:
                    logger.debug(
                        "[COORDINATOR] planner verifier confirmed in background: %s -> %s",
                        verified_decision.next_action,
                        verified_decision.next_domain,
                    )
                else:
                    logger.warning(
                        "[COORDINATOR] planner verifier mismatch after speculative continuation: %s -> %s",
                        mismatch_decision.next_action,
                        mismatch_decision.next_domain,
                    )
                decision_verify_future = None
                decision_guard = None

            # LLM Decision: After first agent, use LLM to decide next action
            # Support domain rarely chains to other agents — skip LLM decision to save ~300ms
            if is_first_agent:
                is_first_agent = False
                if domain == MultiAgentDomain.Domain.SUPPORT:
                    logger.debug("[COORDINATOR] Support domain — skipping LLM decision, stopping chain")
                    break

                # Caller pre-committed the chain (e.g., P0 auto-chain code gate) —
                # skip the decide_next_action LLM call (saves ~300ms) and proceed
                # directly to the next domain in `domains`.
                #
                # BUT: only proceed if Discovery actually resolved a single goods_no.
                # `_apply_tool_derived_slots` (search_product_tool extractor) only
                # stages goods_no when the tool returns exactly 1 item;
                # 0/multiple-result cases leave goods_no=None and Discovery is
                # already in clarification/selection mode. Chaining Transaction on
                # top would produce a contradictory "상품 검색이 필요합니다" fallback.
                if skip_decision and len(domains) >= 2:
                    goods_no_resolved = pending_slots is not None and pending_slots.goods_no is not None
                    if not goods_no_resolved:
                        logger.debug(
                            "[COORDINATOR] skip_decision=True but Discovery did not resolve "
                            "goods_no (0 or multiple results) — stopping chain"
                        )
                        break
                    logger.debug(
                        "[COORDINATOR] skip_decision=True — proceeding to next domain "
                        f"({domains[1].value}) without LLM decision"
                    )
                    continue

                # P1-B stall recovery (LAST RESORT): when domains was [TRANSACTION]
                # alone (P0b gate did not catch the case) and Transaction emitted a
                # "상품을 검색…" fallback line WITHOUT calling any tool, with goods_no
                # still unresolved, the user is stranded — coordinator would otherwise
                # fall through to decide_next_action, which often returns STOP because
                # full_response looks complete.
                #
                # Recovery: extend `domains` IN-PLACE with [DISCOVERY, TRANSACTION] so
                # the for-loop iterator picks up the appended entries (mutation works;
                # reassignment would not). Set skip_decision=True so the LLM decision
                # is bypassed for the recovery chain. The existing post-Discovery
                # goods_no verification above will stop the chain naturally if
                # Discovery's search returns 0/multiple results.
                #
                # Conditions (ALL must hold):
                #   1. The first/only domain executed was TRANSACTION.
                #   2. `last_agent_called_tools is False` — Transaction did not call
                #      any tool (it just produced a stall text). Cases where TX
                #      legitimately called e.g. get_orders_of_user_tool stay untouched.
                #   3. `full_response` matches a search-fallback regex.
                #   4. `goods_no` still None in slots after the Transaction turn.
                #
                # IMPORTANT: this check must run BEFORE the `domain_data_event_emitted`
                # early break below — Transaction often emits a `quickReply` template
                # with empty `quickReplies` when stalled (e.g. "정확한 상품을 선택해
                # 주세요"), which sets domain_data_event_emitted=True and would
                # otherwise short-circuit recovery.
                if (
                    domain == MultiAgentDomain.Domain.TRANSACTION
                    and len(domains) == 1
                    and not last_agent_called_tools
                    and re.search(
                        r"상품을?\s*검색|상품\s*검색이?\s*필요|상품을?\s*선택|먼저\s*선택|정확한\s*상품",
                        full_response or "",
                    )
                ):
                    goods_no_still_none = pending_slots is None or pending_slots.goods_no is None
                    if goods_no_still_none:
                        logger.warning(
                            "[COORDINATOR] P1-B stall recovery: TX-only emitted "
                            "search-fallback with no tool call and goods_no=None — "
                            "extending chain to [DISCOVERY, TRANSACTION] as recovery."
                        )
                        domains.extend([
                            MultiAgentDomain.Domain.DISCOVERY,
                            MultiAgentDomain.Domain.TRANSACTION,
                        ])
                        skip_decision = True
                        continue

                # P1-D stall recovery (DISCOVERY counterpart of P1-B): when
                # domains was [DISCOVERY] alone and Discovery emitted a
                # transactional handoff line (재고/가격/매장/주문/도착/배송 ...
                # 이어갈게요/이어드릴게요/이어갑니다/확인해 드릴게요/
                # 진행해 드릴게요) without a tool call OR after only a
                # product-search tool call (the 1-result transaction handoff
                # path which intentionally calls search_product_tool and then
                # hands off). Without recovery, the user is stranded — the
                # stream ends with only an "I'll continue" message and the
                # actual transactional tool never runs.
                #
                # Conditions (ALL must hold):
                #   1. The first/only domain executed was DISCOVERY.
                #   2. EITHER no tool was called OR only product-search-class
                #      tools were called (search_product_tool /
                #      get_products_recommendations_tool /
                #      get_best_selling_products_tool). Other tool calls
                #      (e.g. youtube preview, car list) stay untouched.
                #   3. `full_response` matches the transactional handoff regex.
                #   4. `goods_no` is set in slots — TRANSACTION can run.
                #
                # Recovery: extend `domains` IN-PLACE with [TRANSACTION]
                # (mutation propagates to the active for-loop iterator).
                _PRODUCT_SEARCH_TOOLS = {
                    "search_product_tool",
                    "get_products_recommendations_tool",
                    "get_best_selling_products_tool",
                }
                only_product_search_called = bool(agent_tools_called) and all(
                    t in _PRODUCT_SEARCH_TOOLS for t in agent_tools_called
                )
                if (
                    domain == MultiAgentDomain.Domain.DISCOVERY
                    and len(domains) == 1
                    and (not last_agent_called_tools or only_product_search_called)
                    and re.search(
                        r"(재고|가격|매장|주문|장착|예약|도착|배송).{0,30}"
                        r"(이어갈게요|이어드릴게요|이어갑니다|확인해\s*드릴게요|진행해\s*드릴게요|진행할게요|진행합니다|확인합니다)",
                        full_response or "",
                    )
                ):
                    goods_no_set = pending_slots is not None and pending_slots.goods_no is not None
                    if goods_no_set:
                        logger.warning(
                            "[COORDINATOR] P1-D stall recovery: DISCOVERY-only emitted "
                            "transactional-handoff text (tools_called=%s) and goods_no "
                            "set — extending chain to [TRANSACTION] as recovery.",
                            agent_tools_called,
                        )
                        domains.append(MultiAgentDomain.Domain.TRANSACTION)
                        skip_decision = True
                        continue

                # Agent already produced a complete UI payload — decide_next_action
                # would return STOP anyway. Keep multi-domain planner/nextAction paths active.
                # NOTE: positioned AFTER P1-B/P1-D stall recovery so that recovery can
                # fire even when a stuck quickReply (e.g. empty quickReplies asking the
                # user to "select" with no options) was emitted as a data event.
                if (
                    domain_data_event_emitted
                    and agent_declared_decision is None
                    and self._planner_decision(domains, routing_result, domain) is None
                ):
                    logger.debug("[COORDINATOR] Data event emitted — skipping decide_next_action")
                    break

                planner_decision = self._planner_decision(domains, routing_result, domain)
                if agent_declared_decision is not None:
                    decision = agent_declared_decision
                    logger.debug(
                        "[COORDINATOR] Using agent-declared nextAction: %s - %s",
                        decision.next_action,
                        decision.reason,
                    )
                elif planner_decision is not None:
                    decision = planner_decision
                    logger.debug(
                        "[COORDINATOR] Using planner execution_plan: %s - %s",
                        decision.next_action,
                        decision.reason,
                    )
                    if decision.next_action == NextAction.CONTINUE and decision.next_domain:
                        decision_guard = {
                            "confirm_event": threading.Event(),
                            "mutating_tools": _SPECULATIVE_MUTATING_TOOLS,
                        }

                        def _verify_planner_decision() -> AgentDecision:
                            llm_decision = decide_next_action(
                                original_messages=messages,
                                previous_agent_response=full_response,
                                previous_domain=domain_key,
                                session_id=session_id,
                                user_id=user_id,
                                trace_id=trace_id,
                                parent_span_id=parent_span_id,
                            )
                            planned_domain = decision.next_domain.lower()
                            verified_domain = (llm_decision.next_domain or "").lower()
                            verified = (
                                llm_decision.next_action == decision.next_action
                                and verified_domain == planned_domain
                            )
                            if verified:
                                decision_guard["confirm_event"].set()
                            else:
                                decision_guard["mismatch_decision"] = llm_decision
                            return llm_decision

                        def _wait_for_decision_verifier() -> bool:
                            decision_verify_future.result()
                            return decision_guard["confirm_event"].is_set()

                        decision_guard["wait_for_confirmation"] = _wait_for_decision_verifier
                        decision_verify_future = _decision_verify_executor.submit(_verify_planner_decision)
                else:
                    decision = decide_next_action(
                        original_messages=messages,
                        previous_agent_response=full_response,
                        previous_domain=domain_key,
                        session_id=session_id,
                        user_id=user_id,
                        trace_id=trace_id,
                        parent_span_id=parent_span_id,
                    )
                    logger.debug(f"[COORDINATOR] LLM Decision: {decision.next_action} - {decision.reason}")

                if decision.next_action == NextAction.STOP or not decision.next_domain:
                    logger.debug("[COORDINATOR] Stopping multi-agent chain")
                    break

                # Map next_domain string to enum
                next_domain_map = {
                    "discovery": MultiAgentDomain.Domain.DISCOVERY,
                    "transaction": MultiAgentDomain.Domain.TRANSACTION,
                    "support": MultiAgentDomain.Domain.SUPPORT,
                }
                next_domain = next_domain_map.get(decision.next_domain.lower())
                if next_domain and next_domain not in domains:
                    # IMPORTANT: in-place mutation only — the enclosing
                    # `for domain in domains` iterator must see the new
                    # entry. Rebinding `domains = [...]` (the previous
                    # implementation) silently leaves the iterator on the
                    # original list, so a CONTINUE decision after a
                    # speculative DISCOVERY turn was dropped and the chain
                    # stalled (e.g. "강남점 예약 가능 시간" → Discovery emits
                    # `nextAction.continue.transaction` but TRANSACTION never
                    # runs and the user sees only "이어갈게요" prose).
                    # `append` matches the P1-D recovery shape (line 1610).
                    domains.append(next_domain)

        # Legacy UI Template Agent path is disabled.
        # Domain agents should emit `data` events directly. If a migrated agent misses a
        # structured payload, fall back to a minimal quickReply built from the last
        # assistant response instead of calling the UI Template Agent.
        _has_qna = any(item.get("tool") == "transfer_to_qna_tool" for item in accumulated_tool_data)
        _has_non_support_data = any(
            item.get("tool") not in ("get_faq_tool", "search_faq_rag_tool", "transfer_to_qna_tool")
            for item in accumulated_tool_data
        )
        _has_agent_response = bool(accumulated_context)
        _no_tools_called = not accumulated_tool_data
        _has_relevant_tool_data = accumulated_tool_data and (_has_qna or _has_non_support_data)
        assistant_text = next((c for c in reversed(list(accumulated_context.values())) if c and c.strip()), "")
        if domain_data_event_emitted:
            logger.debug("[COORDINATOR] Domain agent emitted data event — skipping UI Template Agent")
        elif _has_agent_response and (_no_tools_called or _has_relevant_tool_data):
            trigger_reason = f"{len(accumulated_tool_data)} tool outputs"
            logger.warning(
                "[COORDINATOR] UI Template Agent disabled — generating fallback quickReply (%s)",
                trigger_reason,
            )
            yield {
                "type": "data",
                "template": "quickReply",
                "data": {
                    "assistantResponse": assistant_text,
                    "quickReplies": [],
                },
                "source_domain": domain_key if "domain_key" in locals() else "ui_template",
            }

        if pending_slots_dirty and pending_slots is not None:
            yield {"type": "internal_slots", "slots": pending_slots}

        # Final done event
        yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}

_FALLBACK_RESPONSE = (
    "죄송합니다, 해당 내용은 제가 안내해 드리기 어려운 부분이에요.\n\n"
    "타이어 추천, 가격 조회, 매장 검색 등 타이어 관련 문의사항이 있으시면 편하게 말씀해 주세요."
)

_INTERNAL_JARGON_PATTERN = re.compile(
    r"No tool data retrieved|tool data|source data",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Rule-Based Routing — fast-path classifier (no LLM call)
# ---------------------------------------------------------------------------

_GREETING_ONLY_RE = re.compile(
    r"^[\s!?.]*"
    r"(안녕|hi|hello|hey|하이|ㅎㅇ|안녕하세요|안녕하십시오|반가워|반갑습니다)"
    r"[\s!?.]*$",
    re.IGNORECASE,
)

_SUPPORT_FAST_RE = re.compile(
    r"환불|반품|보증|품질보증|워런티|warranty|"
    r"AS\s*신청|A/S|사후\s*서비스|"
    r"상담원|상담사|사람\s*연결|직원\s*연결|상담\s*연결|1:1\s*문의|1대1\s*문의|"
    r"불만입니다|짜증나|화나|뭐\s*이런|제대로\s*해|엉망이|이딴",
    re.IGNORECASE,
)

_TRANSACTION_FAST_RE = re.compile(
    r"가격|얼마(?!나)|비용|할인|재고|입고|장착\s*가능|"
    r"주문|구매|사고\s*싶|사려고|살래|쿠폰|장바구니|"
    r"매장\s*찾|가까운\s*매장|근처\s*매장|올마이티|all\s*my\s*t",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# P0e: 5% (할인)쿠폰 정책 정보 질문 → SUPPORT redirect
# ---------------------------------------------------------------------------
# "5% 쿠폰이 뭐야?" / "5%할인쿠폰 알려줘" 류 정책 정보 질문은
# e_support_agent prompt 의 HARD STOP (PR #169, e_support_agent/agent.py:44-)
# 에서 처리되어야 한다. 그러나 LLM classifier 는 "쿠폰" 키워드만 보고
# TRANSACTION + transaction_coupon 으로 분류 → c_transaction_agent 가
# get_my_coupons_tool 을 호출해 voucher 카드로 응답 → HARD STOP 발동
# 기회 자체가 없어진다 (Langfuse trace `5a2da3ff...` 검증).
#
# negative guard:
#   - ownership keyword ("내/받은/보유/가진/갖고/소유") → 보유 조회 의도, TX 유지
#   - action keyword  ("받아/받기/받을/발급/다운로드/다운받") → 발급/획득 의도,
#     c_transaction_agent 의 GLOBAL 룰 (line 33-) 이 "쿠폰함에서 가능합니다"
#     로 안내. HARD STOP (정책 정보 fixed text) 발동시키지 않는다.
_FIVE_PERCENT_COUPON_POSITIVE_RE = re.compile(
    r"5\s*%\s*(?:할인\s*)?쿠폰"
)
_FIVE_PERCENT_COUPON_OWNERSHIP_OR_ACTION_RE = re.compile(
    # ownership
    r"내\s*쿠폰|내\s*5\s*%|내가\s|받은|보유|가진|가지고|갖고|소유한|"
    # action (issue / download intent)
    r"받아|받기|받을|발급(?!\s*안|\s*기능)|다운(?:로드|받)"
)

# ---------------------------------------------------------------------------
# P0f: 쿠폰 발급/안내 발화 → single [TRANSACTION] domain 강제
# ---------------------------------------------------------------------------
# "쿠폰 어떻게 받아?", "쿠폰 받아줘", "쿠폰 다운로드" 류 쿠폰 발급/안내 발화는
# c_transaction_agent 의 GLOBAL 룰 (agent.py:33-) 이 단일 응답
# ("쿠폰 받기는 쿠폰함에서 가능합니다." + 쿠폰함 바로가기/내 쿠폰 조회 chip)
# 을 emit 한다. 그러나 LLM classifier 가 multi-domain ([transaction, support])
# 또는 speculative discovery 까지 추가 라우팅하면 discovery_agent 가 자체
# 응답 ("이벤트/기획전 페이지에서 받기" + 이벤트/기획전 chip) 을 emit 해
# FE 가 잘못된 chip 을 보여준다 (Langfuse trace `b14fdcf8...` 검증).
#
# P0f 는 transaction_coupon profile + issue intent 키워드 매칭 시 domains 를
# 단일 [TRANSACTION] 으로 강제 narrow — discovery/support speculative
# 차단 → c_transaction_agent 만 실행 → GLOBAL 룰의 응답이 deterministic
# 하게 emit.
_COUPON_ISSUE_INTENT_RE = re.compile(
    r"쿠폰\s*(?:받(?:아|기|을|은)|다운(?:로드|받)|발급|어떻게\s*받)"
)

# ---------------------------------------------------------------------------
# Regional "cheapest store" fast-path intercept
# ---------------------------------------------------------------------------
# "X 도/시/군/구 에서 제일 저렴한 매장" 류 광역 가격 비교 질문은 매장·시기·
# 상품(쿠폰/기획전/이벤트)에 따라 동적으로 달라지므로 단일 매장으로 일률
# 안내가 불가능. Transaction agent prompt 가드만으로는 LLM 이 우회할 수
# 있어 분류기 전 단계에서 결정적으로 차단하고 canned quickReply 응답으로
# 즉시 종료.
_REGION_KEYWORDS = (
    # 도
    "경상남도", "경상북도", "충청남도", "충청북도", "전라남도", "전라북도",
    "강원도", "경기도", "제주도", "충청도", "전라도", "경상도", "강원특별자치도",
    "전북특별자치도", "제주특별자치도",
    # 특별/광역시
    "서울특별시", "부산광역시", "대구광역시", "대전광역시", "광주광역시",
    "울산광역시", "인천광역시", "세종특별자치시",
    # 약어
    "서울", "부산", "대구", "대전", "광주", "울산", "인천", "세종", "경기",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_REGION_SUFFIX_RE = re.compile(r"[가-힣]{2,5}(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구)")
_CHEAP_KEYWORDS_RE = re.compile(
    r"(제일|가장)\s*(저렴|싼|싸|싸게)|"
    r"가격\s*비교|"
    r"어디가\s*(제일|가장)|"
    r"최저\s*가격|최저가",
    re.IGNORECASE,
)


def _is_regional_cheapest_query(msg: str | None) -> bool:
    """Return True for '도/시/군/구 + 제일 저렴' style regional price-comparison queries."""
    if not msg:
        return False
    has_region = any(r in msg for r in _REGION_KEYWORDS) or bool(_REGION_SUFFIX_RE.search(msg))
    if not has_region:
        return False
    return bool(_CHEAP_KEYWORDS_RE.search(msg))


# ---------------------------------------------------------------------------
# Service reservation (wiper / battery / alignment / 경정비) datepick redirect
# ---------------------------------------------------------------------------
# Non-tire service reservations are not bookable inside the chatbot — the
# user must complete them on the tstation.com 매장 상세 페이지. The
# `c_transaction_agent` system prompt has a SERVICE RESERVATION REDIRECT
# rule for this, but the LLM sometimes ignores it after a datepick
# selection and emits a vague "필요한 정보를 이어서 입력해 주세요" with
# dead-end "1:1 문의하기 / 처음으로" chips, leaving the user stuck.
#
# Detect the situation deterministically pre-coordinator and short-circuit
# with a fixed redirect payload, mirroring `_is_regional_cheapest_query`.

_DATEPICK_SELECTION_RE = re.compile(
    r"^\s*(?P<year>\d{4})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일"
    r"\s*(?:\([^)]+\))?\s*[\n\s]+\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*$"
)
_TIRE_PRODUCT_CONTEXT_RE = re.compile(
    r"goods_no|G\d{12}|"
    r"\d{3}\s*/\s*\d{2}\s*R\s*\d{2}|"
    r"벤투스|키너지|아이온|마일리지|드라이브웨이|다이나프로|라우펜|"
    r"ventus|kinergy|ion\b|mileage",
    re.IGNORECASE,
)
_SHOP_SEQ_RE = re.compile(r'"shop[_\s]*seq"\s*:\s*"([A-Z]?\d{4,})"', re.IGNORECASE)
_STORE_NAME_RE = re.compile(r"티스테이션\s*[가-힣A-Za-z0-9]+\s*점")


def _scan_recent_messages_for(
    messages: list[dict], pattern: re.Pattern, *, max_msgs: int = 10
) -> str | None:
    """Walk last `max_msgs` messages newest-first; return first regex match."""
    for msg in reversed(messages[-max_msgs:]):
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, str) or not content:
            continue
        match = pattern.search(content)
        if match:
            return match.group(1) if match.groups() else match.group(0)
    return None


def _is_service_reservation_redirect(
    last_user_text: str | None,
    pending_intent: str | None,
    messages: list[dict],
) -> bool:
    """True when a datepick selection should be routed to the matjang detail page.

    All three conditions must hold:
      1. The user message is *only* a date + time (FE datepick click payload).
      2. The conversation has a pending `reservation` intent (set by
         ConversationSlots.extract when the user said 와이퍼/배터리/경정비/
         얼라인먼트 + 예약).
      3. No tire-product context (goods_no / size / model name) appears in
         the recent history — that signals a tire booking which has its own
         preOrder flow.
    """
    if not last_user_text or pending_intent != "reservation":
        return False
    if not _DATEPICK_SELECTION_RE.match(last_user_text):
        return False
    if _scan_recent_messages_for(messages, _TIRE_PRODUCT_CONTEXT_RE):
        return False
    return True


def _build_service_reservation_redirect_payload(
    last_user_text: str,
    messages: list[dict],
) -> dict:
    """Compose the deterministic redirect text + chips for emit/non-stream paths.

    Best-effort store-name and shop_seq extraction from recent history; if
    shop_seq is unavailable we omit the URL chip rather than fabricate one.
    """
    from services.tstation.common.cta_urls import CTAUrls

    m = _DATEPICK_SELECTION_RE.match(last_user_text)
    assert m is not None, "caller must guard with _is_service_reservation_redirect"
    yyyy = m.group("year")
    mm = m.group("month").zfill(2)
    dd = m.group("day").zfill(2)
    hh = m.group("hour").zfill(2)
    mi = m.group("minute")

    store_name = _scan_recent_messages_for(messages, _STORE_NAME_RE) or "선택하신 매장"
    shop_seq = _scan_recent_messages_for(messages, _SHOP_SEQ_RE)

    text = (
        f"{store_name} {yyyy}-{mm}-{dd} {hh}:{mi} 방문을 원하시는 것으로 확인했어요 😊\n\n"
        "방문 예약은 티스테이션닷컴 매장 상세 페이지에서 가능해요. "
        "아래 버튼으로 이동해 주세요."
    )

    chips: list[dict] = []
    if shop_seq:
        chips.append({
            "label": "매장 상세 페이지로 이동",
            "url": CTAUrls.STORE_DETAIL.replace("<shop_seq>", shop_seq),
            "domain": "TRANSACTION",
        })
    chips.extend([
        {"label": "다른 시간 선택", "domain": "TRANSACTION"},
        {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
    ])

    return {"text": text, "chips": chips, "shop_seq": shop_seq, "store_name": store_name}


# Goal-based fast-path routing tables — kept beside _goal_based_classify so the
# classifier code and its decision data stay together. Only goal_types defined
# in slots.py's GOAL_PLANS appear here; mismatches simply fall through to the
# next classifier.
_GOAL_NEXT_STEP_DOMAIN: "dict[tuple[str, str], MultiAgentDomain.Domain]" = {
    # product_search: bare product-keyword turn (no transactional intent, no
    # recommend verb). Goal completes when goods_no resolves; until then the
    # search step lives in Discovery (search_product_tool).
    ("product_search", "search"): MultiAgentDomain.Domain.DISCOVERY,
    # store_with_stock: model/size live in Discovery (search_product_tool),
    # qty/shop in Transaction (qty quickReply + store search).
    ("store_with_stock", "model"): MultiAgentDomain.Domain.DISCOVERY,
    ("store_with_stock", "size"): MultiAgentDomain.Domain.DISCOVERY,
    ("store_with_stock", "qty"): MultiAgentDomain.Domain.TRANSACTION,
    ("store_with_stock", "shop"): MultiAgentDomain.Domain.TRANSACTION,
    # price_inquiry: same product-resolution pipeline; final price is Transaction.
    ("price_inquiry", "model"): MultiAgentDomain.Domain.DISCOVERY,
    ("price_inquiry", "size"): MultiAgentDomain.Domain.DISCOVERY,
    ("price_inquiry", "qty"): MultiAgentDomain.Domain.TRANSACTION,
    # place_order: identical product pipeline + shop selection in Transaction.
    ("place_order", "model"): MultiAgentDomain.Domain.DISCOVERY,
    ("place_order", "size"): MultiAgentDomain.Domain.DISCOVERY,
    ("place_order", "qty"): MultiAgentDomain.Domain.TRANSACTION,
    ("place_order", "shop"): MultiAgentDomain.Domain.TRANSACTION,
    # store_finder: pure store search. region is the only checklist step.
    # Missing region → Transaction asks (with quickReply chips); the
    # user_preferences_text slot persists across the clarification turn so
    # the criteria carry into the completion step (see _GOAL_COMPLETE_DOMAIN).
    ("store_finder", "region"): MultiAgentDomain.Domain.TRANSACTION,
}

# Where to route when every checklist step is satisfied — final tool call lives
# here. product_recommend is intentionally excluded: its plan is empty so it
# never reaches "completion" via this path; LLM classifier owns that turn.
_GOAL_COMPLETE_DOMAIN: "dict[str, MultiAgentDomain.Domain]" = {
    "store_with_stock": MultiAgentDomain.Domain.TRANSACTION,
    "price_inquiry": MultiAgentDomain.Domain.TRANSACTION,
    "place_order": MultiAgentDomain.Domain.TRANSACTION,
    # store_finder: once region is filled, Transaction runs the store search
    # and applies the captured user_preferences_text (if any) to filter/rank.
    "store_finder": MultiAgentDomain.Domain.TRANSACTION,
}

# When the user's latest turn signals a deliberate pivot away from the persisted
# goal ("다른", "이번엔", "이전 추천 말고", etc.), skip the fast-path and let the
# LLM classifier re-evaluate. Cheaper to spend one classifier call than to
# mis-route a goal-switch turn through a stale checklist.
_GOAL_SWITCH_RE = re.compile(r"다른|새로|이번엔|바꿔|이전\s*추천\s*말고", re.IGNORECASE)

# "Non-self car" negation: user explicitly excludes their registered/saved cars
# and asks about a different vehicle model. When this fires, any stale
# tire_size / goods_no / car_model carried over from a prior turn refers to the
# WRONG vehicle and must be cleared before the slot context is injected into
# the agent prompt — otherwise the LLM reuses the stale size and ignores the
# car model the user just named (see CAR MODEL DISPLAY rule in
# b_discovery_agent/agent.py).
#
# Covers:
#   "내차말고", "내 차 말고", "내차 말고", "내차아닌", "내 차 아닌",
#   "내차아니라", "내 차가 아닌", "내차빼고", "내 차 빼고",
#   "저장차 아닌", "저장차말고", "등록차 아닌", "등록차말고",
#   "보유차 아닌", "보유한 차 말고",
#   "다른 차종", "다른 차"
_NON_SELF_CAR_RE = re.compile(
    r"(내\s*차|저장\s*차|등록\s*차|보유\s*차|보유한\s*차|내가\s*가진\s*차)"
    r"\s*(말고|아닌|아니라|아니고|빼고|이외|제외)"
    r"|다른\s*차(?:종)?",
    re.IGNORECASE,
)

# Master toggle. Set False to disable goal-based fast-path without removing the
# code (useful if downstream telemetry shows mis-routes; the LLM classifier
# remains the safety net regardless).
_GOAL_FAST_PATH_ENABLED = True


_SPECULATIVE_UNSAFE_DOMAINS = set()
_SPECULATIVE_MUTATING_TOOLS = {
    "quick_order_tool",
    "save_to_cart_tool",
    "issue_coupon_tool",
    "escalate_tool",
    "transfer_to_qna_tool",
}


def _normalize_domains(domains: "list[MultiAgentDomain.Domain] | None") -> list[MultiAgentDomain.Domain]:
    if not domains:
        return [MultiAgentDomain.Domain.LEADING]
    normalized = []
    for domain in domains:
        if domain not in normalized:
            normalized.append(domain)
    return normalized or [MultiAgentDomain.Domain.LEADING]


def _domains_equal(left: "list[MultiAgentDomain.Domain] | None", right: "list[MultiAgentDomain.Domain] | None") -> bool:
    return _normalize_domains(left) == _normalize_domains(right)


def _domains_from_strings(values: list[str]) -> "list[MultiAgentDomain.Domain] | None":
    domain_map = {domain.value: domain for domain in MultiAgentDomain.Domain}
    domains = []
    for value in values:
        domain = domain_map.get(str(value).upper())
        if domain is not None and domain not in domains:
            domains.append(domain)
    return domains or None


def _dedupe_domain_values(values: list[str]) -> list[str]:
    deduped = []
    for value in values:
        domain = str(value).upper()
        if domain in _VALID_CHIP_DOMAINS and domain not in deduped:
            deduped.append(domain)
    return deduped


def _quick_reply_domain_values_from_event(event: dict) -> list[str]:
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return []
    quick_replies = event_data.get("quickReplies")
    if not isinstance(quick_replies, list):
        return []
    return _dedupe_domain_values([
        str(item.get("domain", "")).upper()
        for item in quick_replies
        if isinstance(item, dict)
    ])


def _predicted_domain_values_from_event(event: dict) -> list[str]:
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return []
    predicted = event_data.get("predictedDomains") or event_data.get("predicted_domains")
    if not isinstance(predicted, list):
        return []
    return _dedupe_domain_values([str(item).upper() for item in predicted])


def _is_speculative_safe(domains: "list[MultiAgentDomain.Domain] | None") -> bool:
    return bool(domains) and not any(domain in _SPECULATIVE_UNSAFE_DOMAINS for domain in domains)


# Tool-name → context-aware fallback chip set. Picked when the LLM emits an
# empty quickReplies array so the user lands on chips that fit the conversation
# (e.g., order list → order-history CTA, not the generic "1:1 문의" pair which
# makes the flow look broken).
_FALLBACK_GENERIC: list[dict] = [
    {"label": "1:1 문의하기", "domain": "SUPPORT"},
]

_FALLBACK_ORDER_LIST: list[dict] = [
    {"label": "주문 내역 보기", "url": CTAUrls.ORDER_HISTORY, "domain": "TRANSACTION"},
    {"label": "1:1 문의하기", "domain": "SUPPORT"},
]

_FALLBACK_COUPON: list[dict] = [
    {"label": "내 쿠폰함", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
    {"label": "1:1 문의하기", "domain": "SUPPORT"},
]

# LEADING 도메인의 fallback 은 진행형(발견 → 구매) chip 으로 시작해야 자연스럽다.
# "1:1 문의하기" 같은 escalation chip 은 사용자가 인사·일반 문의를 한 직후엔 부적절.
_FALLBACK_LEADING_PROGRESS: list[dict] = [
    {"label": "상품 검색", "domain": "DISCOVERY"},
    {"label": "타이어 추천", "domain": "DISCOVERY"},
]

# Order matters: more specific tools first so the dispatch picks the most
# relevant chip set when multiple tools ran in the same turn.
_FALLBACK_DISPATCH: list[tuple[set[str], list[dict], str]] = [
    ({"get_orders_of_user_tool", "get_order_status_tool"}, _FALLBACK_ORDER_LIST, "order"),
    ({"get_my_coupons_tool", "get_available_coupons_tool"}, _FALLBACK_COUPON, "coupon"),
]

_GENERIC_DEAD_END_LABELS = {"1:1 문의하기", "처음으로"}
_HOME_QUICK_REPLY_LABEL = "처음으로"
_DISCOVERY_SIZE_VEHICLE_CHIPS: list[dict] = [
    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
    {"label": "차량번호로 찾기", "domain": "DISCOVERY"},
    {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
]
_DISCOVERY_NO_RESULT_CHIPS: list[dict] = [
    {"label": "다시 검색", "domain": "DISCOVERY"},
    {"label": "다른 조건으로 찾기", "domain": "DISCOVERY"},
    {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
]
_DISCOVERY_PRODUCT_CHIPS: list[dict] = [
    {"label": "다른 조건으로 찾기", "domain": "DISCOVERY"},
    {"label": "구매하기", "domain": "TRANSACTION"},
    {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
]
_DISCOVERY_DEFAULT_CHIPS: list[dict] = [
    {"label": "상품 검색", "domain": "DISCOVERY"},
    {"label": "타이어 추천", "domain": "DISCOVERY"},
]
_DISCOVERY_SIZE_VEHICLE_TEXT_RE = re.compile(
    r"타이어\s*사이즈|차량번호|소유주|등록\s*차량|내\s*차|내차|"
    r"차종|규격|하중(?:지수)?|트럭|화물",
    re.IGNORECASE,
)
_DISCOVERY_NO_RESULT_TEXT_RE = re.compile(
    r"찾을\s*수\s*없|검색\s*결과가?\s*없|조회(?:된)?\s*상품이?\s*없|"
    r"조건에\s*맞는\s*타이어|매칭(?:되는)?\s*상품",
    re.IGNORECASE,
)
_DISCOVERY_PRODUCT_TEXT_RE = re.compile(
    r"타이어\s*추천|상품\s*추천|추천해\s*드릴|제품을?\s*선택|"
    r"상품을?\s*찾았|구매|장바구니",
    re.IGNORECASE,
)
_EXPLICIT_SUPPORT_TEXT_RE = re.compile(
    r"1\s*:\s*1\s*문의|상담(?:원|사)?|클레임|환불\s*신청|교환\s*신청|"
    r"문의로\s*문의|고객센터",
    re.IGNORECASE,
)
_DISCOVERY_DEAD_END_ALLOWED_TEXT_RE = re.compile(
    r"제조\s*(?:일자|시점|주차|번호)|DOT|생산(?:된|일자|시점|주차)?|"
    r"확정(?:해|하여)?\s*안내.*어려|조회.*어려|확인.*어려|"
    r"시스템.*확인.*불가|일시적(?:인)?\s*(?:오류|문제|실패)|"
    r"불러오지\s*못|제공(?:해)?\s*드리기\s*어려",
    re.IGNORECASE,
)

_RESERVATION_TIME_CHIP_RE = re.compile(r"^\s*(?:[01]?\d|2[0-3])\s*시\s*예약\s*$")
_RESERVATION_OTHER_TIME_LABELS = {"다른 시간 선택", "다른 시간대 선택"}
_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


def _yyyymmdd_to_korean_date(s: str) -> str:
    try:
        dt = datetime.datetime.strptime(s, "%Y%m%d")
    except (TypeError, ValueError):
        return s
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({_WEEKDAY_KO[dt.weekday()]})"


def _parse_preview_slot_hour(tm: object) -> int | None:
    s = str(tm or "").strip()
    if not s.isdigit():
        return None
    if len(s) <= 2:
        hour = int(s)
    elif len(s) == 4:
        hour = int(s[:2])
    else:
        return None
    if hour == 12:
        return None
    return hour if 0 <= hour <= 23 else None


def _extract_preview_payload(parsed: dict) -> dict | None:
    if parsed.get("status") == "success" and isinstance(parsed.get("data"), dict):
        return parsed["data"]
    data = parsed.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return parsed if isinstance(parsed, dict) else None


def _coerce_reservation_quickreply_to_datepick(
    event: dict,
    structured_sources: list[tuple[str, dict]],
    slot_state: Any | None,
) -> dict | None:
    """Narrowly convert LLM reservation-time chips to the datepick template.

    This only handles the regression where transaction_store_preview_tool
    returned concrete slots but the LLM rendered "09시 예약" style quickReply
    chips instead of the FE date picker. It deliberately avoids stock-store
    contexts, where the correct answer is a stocked-store location card.
    """
    if event.get("template") != "quickReply":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    chips = event_data.get("quickReplies")
    if not isinstance(chips, list) or not chips:
        return None
    labels = [
        str(chip.get("label", "")).strip()
        for chip in chips
        if isinstance(chip, dict)
    ]
    has_reservation_time_chip = any(_RESERVATION_TIME_CHIP_RE.match(label) for label in labels)
    has_only_reservation_chips = all(
        _RESERVATION_TIME_CHIP_RE.match(label) or label in _RESERVATION_OTHER_TIME_LABELS
        for label in labels
    )
    if not has_reservation_time_chip or not has_only_reservation_chips:
        return None

    pending_intent = getattr(slot_state, "pending_intent", None)
    goal_type = getattr(slot_state, "goal_type", None)
    assistant_text = str(event_data.get("assistantResponse") or "")
    if pending_intent == "stock" or goal_type == "store_with_stock":
        return None
    if re.search(r"재고\s*(있는|가\s*확인된)\s*매장|재고있는\s*매장", assistant_text):
        return None

    preview_payload = None
    for tool_name, parsed in reversed(structured_sources):
        if tool_name != "transaction_store_preview_tool" or not isinstance(parsed, dict):
            continue
        preview_payload = _extract_preview_payload(parsed)
        if isinstance(preview_payload, dict):
            break
    if not isinstance(preview_payload, dict):
        return None

    schedule = preview_payload.get("schedule")
    if not isinstance(schedule, dict) or str(schedule.get("tier") or "").lower() == "none":
        return None
    schedule_stores = schedule.get("stores")
    if not isinstance(schedule_stores, list):
        return None

    for store in schedule_stores:
        if not isinstance(store, dict):
            continue
        shop_id = str(store.get("shop_id") or "").strip()
        slots = store.get("slots")
        if not shop_id or not isinstance(slots, list):
            continue
        by_day: dict[str, set[int]] = {}
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            cal_day = str(slot.get("cal_day") or "").strip()
            hour = _parse_preview_slot_hour(slot.get("tm"))
            if cal_day and hour is not None:
                by_day.setdefault(cal_day, set()).add(hour)
        if not by_day:
            continue

        dates: list[dict] = []
        selected_idx: int | None = None
        for idx, cal_day in enumerate(sorted(by_day.keys())):
            times = sorted(by_day[cal_day])
            available = bool(times)
            dates.append({
                "date": _yyyymmdd_to_korean_date(cal_day),
                "available": available,
                "availableTimes": times,
                "index": idx,
            })
            if selected_idx is None and available:
                selected_idx = idx
        if selected_idx is None:
            continue

        metadata = {"shopId": shop_id}
        shop_name = str(store.get("shop_nm") or "").strip()
        if shop_name:
            metadata["shopName"] = shop_name
        return {
            "type": "data",
            "template": "datepick",
            "source_domain": event.get("source_domain"),
            "assistant_response_source": "code_mapper_preview_quickreply",
            "data": {
                "assistantResponse": assistant_text or "예약 가능한 날짜와 시간을 선택해 주세요.",
                "dates": dates,
                "selectedDate": selected_idx,
                "metadata": metadata,
            },
        }
    return None


_LISTCAR_SELECTION_NEEDLES: tuple[str, ...] = (
    "선택",
    "골라",
    "어떤 차량",
    "이 차량으로 진행",
    "차량을 확인해",
    "등록된 차량",
    "차량 목록",
)


def _looks_like_vehicle_selection_prompt(text: str | None) -> bool:
    normalized = (text or "").strip()
    return bool(normalized) and any(needle in normalized for needle in _LISTCAR_SELECTION_NEEDLES)


def _coerce_non_selection_listcar_to_quickreply(event: dict) -> dict | None:
    """Suppress direct listCar JSON when the answer is plain advice.

    The template mapper already suppresses get_my_cars_tool → listCar for
    generic advice turns. This catches the sibling path where the LLM emits a
    valid listCar JSON directly, bypassing the mapper guard.
    """
    if event.get("template") != "listCar":
        return None
    source_domain = str(event.get("source_domain") or "").lower()
    if source_domain != "discovery":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    assistant_text = str(event_data.get("assistantResponse") or "")
    if _looks_like_vehicle_selection_prompt(assistant_text):
        return None
    recovery = _discovery_recovery_chips_for_text(assistant_text, event.get("source_domain"))
    if recovery is None:
        chips = list(_DISCOVERY_DEFAULT_CHIPS)
    else:
        chips, _label = recovery
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": event.get("source_domain"),
        "assistant_response_source": "code_mapper_listcar_advice_guard",
        "data": {
            "assistantResponse": assistant_text,
            "quickReplies": chips,
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _choose_quickreply_fallback(
    called_tool_names: set[str], source_domain: str | None
) -> tuple[list[dict], str]:
    """Pick a context-aware fallback chip set when the LLM emits empty quickReplies.

    Returns (chips, label) where label is a short tag for logging/telemetry.

    Routing priority:
      1. Tool-based dispatch (order/coupon) — turn ran a tool that needs a specific CTA.
      2. LEADING domain → 진행형 chip ([상품 검색, 타이어 추천, 처음으로]). 인사/일반
         문의에서 "1:1 문의" 로 떨어지는 부자연스러운 fallback 을 방지.
      3. Generic ([1:1 문의하기, 처음으로]) — 마지막 안전망.
    """
    for tool_set, chips, label in _FALLBACK_DISPATCH:
        if called_tool_names & tool_set:
            return chips, label
    if source_domain and source_domain.lower() == "leading":
        return _FALLBACK_LEADING_PROGRESS, "leading_progress"
    return _FALLBACK_GENERIC, "generic"


def _looks_like_generic_dead_end_chips(chips: object) -> bool:
    if not isinstance(chips, list) or not chips:
        return False
    labels = {
        str(item.get("label", "")).strip()
        for item in chips
        if isinstance(item, dict)
    }
    return bool(labels) and labels <= _GENERIC_DEAD_END_LABELS and _GENERIC_DEAD_END_LABELS <= labels


def _remove_home_quick_reply_chips(event_data: dict) -> bool:
    """Strip the global home quick button from any FE payload before streaming."""
    chips = event_data.get("quickReplies")
    if not isinstance(chips, list):
        return False
    filtered = [
        chip for chip in chips
        if not (
            isinstance(chip, dict)
            and str(chip.get("label") or "").strip() == _HOME_QUICK_REPLY_LABEL
        )
    ]
    if len(filtered) == len(chips):
        return False
    event_data["quickReplies"] = filtered
    if not any(
        isinstance(chip, dict) and str(chip.get("domain") or "").upper() == "LEADING"
        for chip in filtered
    ):
        predicted = event_data.get("predictedDomains")
        if isinstance(predicted, list):
            event_data["predictedDomains"] = [
                domain for domain in predicted
                if str(domain).upper() != "LEADING"
            ]
    return True


def _discovery_recovery_chips_for_text(
    assistant_text: str | None,
    source_domain: str | None,
) -> tuple[list[dict], str] | None:
    """Return progress chips when Discovery accidentally emits dead-end chips.

    Generic support chips are only appropriate for explicit support/policy
    dead-ends. Normal Discovery guidance should keep the user in the discovery
    flow with chips that match the answer.
    """
    if not source_domain or source_domain.lower() != "discovery":
        return None
    text = assistant_text or ""
    if not text:
        return None
    if _EXPLICIT_SUPPORT_TEXT_RE.search(text) or _DISCOVERY_DEAD_END_ALLOWED_TEXT_RE.search(text):
        return None
    if _DISCOVERY_SIZE_VEHICLE_TEXT_RE.search(text):
        return list(_DISCOVERY_SIZE_VEHICLE_CHIPS), "discovery_size_vehicle"
    if _DISCOVERY_NO_RESULT_TEXT_RE.search(text):
        return list(_DISCOVERY_NO_RESULT_CHIPS), "discovery_no_result"
    if _DISCOVERY_PRODUCT_TEXT_RE.search(text):
        return list(_DISCOVERY_PRODUCT_CHIPS), "discovery_product"
    return list(_DISCOVERY_DEFAULT_CHIPS), "discovery_default"


def _should_replace_discovery_dead_end_chips(
    assistant_text: str | None,
    source_domain: str | None,
) -> bool:
    return _discovery_recovery_chips_for_text(assistant_text, source_domain) is not None


def _goal_based_classify(
    last_user_text: str,
    merged_slots,
) -> "list[MultiAgentDomain.Domain] | None":
    """Goal-driven fast-path classifier.

    When `merged_slots.goal_type` is set and the user message does not signal
    a goal switch, route by the next missing checklist step (or the goal's
    completion-domain when every step is satisfied).

    Returns a single-domain list on hit, or None to fall through to
    `_rule_based_classify` / the LLM classifier.

    Pure function: no I/O, no LLM, ~tens of microseconds per call. Cost is
    bounded by GOAL_PLANS size (≲5 steps).
    """
    if not _GOAL_FAST_PATH_ENABLED:
        return None

    goal_type = getattr(merged_slots, "goal_type", None)
    if not goal_type:
        return None

    if last_user_text and _GOAL_SWITCH_RE.search(last_user_text):
        logger.debug("[GOAL_ROUTER] goal-switch keyword in text — falling through")
        return None

    next_step_id = merged_slots.next_goal_step_id()

    if next_step_id is None:
        domain = _GOAL_COMPLETE_DOMAIN.get(goal_type)
        if domain is not None:
            logger.debug(f"[GOAL_ROUTER] goal={goal_type} all steps done → {domain.value}")
            return [domain]
        return None

    domain = _GOAL_NEXT_STEP_DOMAIN.get((goal_type, next_step_id))
    if domain is not None:
        logger.debug(f"[GOAL_ROUTER] goal={goal_type} next_step={next_step_id} → {domain.value}")
        return [domain]
    return None


def _support_fast_path(text: str) -> "list[MultiAgentDomain.Domain] | None":
    """Always-on SUPPORT fast-path for unambiguous escalation/policy keywords.

    DECISION_LLM (small QC-tier model) has been observed to mis-route
    '상담사 연결' / '상담원 연결' to LEADING — leaving LeadingAgent (which has
    no transfer_to_qna_tool) to refuse the request and surface a "상담사 연결"
    quickReply chip that, when tapped, loops back into the same refusal.

    Bypass classification when an explicit support trigger is present so the
    request always reaches SupportAgent's transfer_to_qna_tool. Independent of
    `_RULE_BASED_ROUTING_ENABLED` so escalation cannot be silently disabled
    alongside the broader rule-based path.
    """
    if not text:
        return None
    if _SUPPORT_FAST_RE.search(text):
        logger.debug(f"[SUPPORT_FAST_PATH] → SUPPORT: {text[:60]!r}")
        return [MultiAgentDomain.Domain.SUPPORT]
    return None


def _rule_based_classify(
    last_user_text: str,
    merged_slots,
) -> "list[MultiAgentDomain.Domain] | None":
    """Fast-path domain classifier using regex rules.

    Returns a domain list when intent is unambiguous, or None to fall through
    to the LLM classifier (classify_multi_intent).

    Cases handled:
      1. Pure greeting            → [LEADING]
      2. Clear support keywords   → [SUPPORT]
      3. goods_no in slots + transactional keyword in text → [TRANSACTION]
      4. goods_no pattern in text + transactional keyword  → [TRANSACTION]
    """
    # DISABLED — set to True to re-enable rule-based routing
    _RULE_BASED_ROUTING_ENABLED = False
    if not _RULE_BASED_ROUTING_ENABLED:
        return None

    text = last_user_text.strip()
    if not text:
        return None

    # Case 1: Pure greeting (short, no additional intent)
    if _GREETING_ONLY_RE.match(text):
        logger.debug("[RULE_ROUTER] Greeting fast-path → LEADING")
        return [MultiAgentDomain.Domain.LEADING]

    # Case 2: Clear support / escalation keywords
    if _SUPPORT_FAST_RE.search(text):
        logger.debug(f"[RULE_ROUTER] Support keyword fast-path → SUPPORT: {text[:60]!r}")
        return [MultiAgentDomain.Domain.SUPPORT]

    # Case 3: goods_no already in slots + transactional keyword in current turn
    if merged_slots.goods_no and _TRANSACTION_FAST_RE.search(text):
        logger.debug(f"[RULE_ROUTER] goods_no={merged_slots.goods_no!r} in slots + transactional keyword → TRANSACTION")
        return [MultiAgentDomain.Domain.TRANSACTION]

    # Case 4: goods_no pattern directly written in user text + transactional keyword
    if re.search(r"G\d{9,}", text) and _TRANSACTION_FAST_RE.search(text):
        logger.debug("[RULE_ROUTER] goods_no literal in text + transactional keyword → TRANSACTION")
        return [MultiAgentDomain.Domain.TRANSACTION]

    return None


def _sanitize_response(text: str) -> str:
    """Replace internal jargon with user-friendly fallback if response has no useful content."""
    stripped = _strip_qc_verdict_from_user_text(text).strip()
    if not stripped:
        return _FALLBACK_RESPONSE
    if _INTERNAL_JARGON_PATTERN.search(stripped) and len(stripped) < 100:
        return _FALLBACK_RESPONSE
    return stripped


def _strip_qc_verdict_from_user_text(text: str) -> str:
    """Remove standalone QC verdict markers from user-facing text."""
    if not isinstance(text, str):
        return ""
    lines = [line for line in text.splitlines() if line.strip().upper() != "PASS"]
    return "\n".join(lines)



_QC_REQUIRED_TOOLS = frozenset({
    # Price, discount, promotion, coupon
    "get_final_price_tool",
    "compare_discount_tool",
    "get_cheapest_price_tool",
    "get_my_coupons_tool",
    "issue_coupon_tool",
    "get_product_promotions_tool",
    "get_product_applicable_events_tool",
    "get_event_applicable_products_tool",
    "get_deals_tool",
    # Stock, store detail, schedule, purchase preview
    "get_logistics_inventory_tool",
    "get_store_inventory_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "transaction_store_preview_tool",
    "get_store_detail_tool",
    # Cart, order, order status
    "save_to_cart_tool",
    "quick_order_tool",
    "get_order_status_tool",
    "get_orders_of_user_tool",
    # Product facts, fitment, policy/support answers
    "check_compatibility_tool",
    "search_product_tool",
    "get_products_recommendations_tool",
    "get_product_description_tool",
    "get_best_selling_products_tool",
    "get_faq_tool",
    "search_faq_rag_tool",
})
_QC_SKIP_TEMPLATES = frozenset({"listCar", "qnaComplete", "datepick"})
_TEMPLATE_QC_POLICY = {
    "product": {"source": "code_mapper", "qc": "skip_default_response"},
    "voucher": {"source": "code_mapper", "qc": "skip_default_response"},
    "cheapestProduct": {"source": "code_mapper", "qc": "skip_default_response"},
    "previewYoutube": {"source": "code_mapper", "qc": "skip_default_response"},
    "location": {"source": "code_mapper", "qc": "skip_default_response"},
    "datepick": {"source": "code_mapper", "qc": "skip_default_response"},
    "listCar": {"source": "code_mapper", "qc": "skip_default_response"},
    "qnaComplete": {"source": "code_mapper", "qc": "skip_default_response"},
    # Path B: LLM writes the JSON; QC may correct field values.
    "preOrder": {"source": "llm_json", "qc": "required"},
    "orderComplete": {"source": "llm_json", "qc": "required"},
}
_QC_SKIP_CODE_MAPPED_TEMPLATES = frozenset(
    template for template, policy in _TEMPLATE_QC_POLICY.items()
    if policy["source"] == "code_mapper" and policy["qc"] == "skip_default_response"
)
_LLM_WRITTEN_TEMPLATES = frozenset(
    template for template, policy in _TEMPLATE_QC_POLICY.items()
    if policy["source"] == "llm_json"
)
# Valid domains a quick reply chip may declare for classifier skip
_VALID_CHIP_DOMAINS = frozenset({"DISCOVERY", "TRANSACTION", "SUPPORT", "LEADING"})


def _qc_skip_reason(
    called_tool_names: set[str],
    last_template: str | None,
    template_source: str | None = None,
    assistant_response_source: str | None = None,
) -> str | None:
    if (
        template_source == "code_mapper"
        and assistant_response_source == "default"
        and last_template in _QC_SKIP_CODE_MAPPED_TEMPLATES
    ):
        return f"code_mapped_{last_template}"
    if last_template in _QC_SKIP_TEMPLATES:
        return f"template_{last_template}"
    if not bool(called_tool_names & _QC_REQUIRED_TOOLS):
        return "no_qc_required_tools"
    return None


def _should_skip_qc(
    called_tool_names: set[str],
    last_template: str | None,
    template_source: str | None = None,
    assistant_response_source: str | None = None,
) -> bool:
    return _qc_skip_reason(
        called_tool_names,
        last_template,
        template_source,
        assistant_response_source,
    ) is not None


# Singleton coordinator instance
_coordinator = StreamingMultiAgentCoordinator()


# Cap on how many recent assistant card turns get template_data attached.
# Past versions enriched only turn_age=0 (latest), which dropped product/store/
# voucher card structure from earlier turns. We briefly raised the cap to 5
# to recover multi-turn references ("이 매장에 그 사이즈 재고 있어?"), but in
# practice a 5-turn snapshot of stale tool data nudged the LLM to "answer from
# memory" instead of re-issuing the proper tool call — most visibly on the
# turn right after a vehicle pick, where Discovery skipped
# `get_products_recommendations_tool` and produced a prose response with no
# product cards. Dropping back to 1 keeps the immediately-prior card context
# (enough for "1번", "벤투스 S2 AS", "그 매장" demonstratives in the very next
# turn) while preventing further turns from biasing the LLM away from fresh
# tool calls. Older structured data is still available via the BE-filtered
# tool_context system message.
_TEMPLATE_ENRICH_MAX_TURNS = 1


def _enrich_messages_with_template_data(
    messages: list[dict],
    session_id: str,
    *,
    assistant_template_messages: list[dict] | None = None,
) -> list[dict]:
    """Attach template_data from Redis to recent assistant card turns.

    Walks messages in reverse and enriches up to _TEMPLATE_ENRICH_MAX_TURNS
    most-recent assistant turns whose content matches a Redis-stored
    template_data entry. Each enriched turn gets a `[이전 선택된 상품 데이터]`
    JSON appended to its content so the LLM can resolve references like
    "두번째 매장", "그 사이즈" across multi-turn card flows.

    Token-context concerns are bounded by the cap; the BE-filtered
    tool_context (loaded as a separate system message) preserves additional
    older-turn structured data.

    Pass `assistant_template_messages` to reuse already-fetched recent
    assistant messages with template_data and skip the extra Redis round-trip.
    """
    if not session_id:
        return messages

    try:
        if assistant_template_messages is None:
            from services.tstation.chat_history_service import get_chat_history_service
            assistant_template_messages = (
                get_chat_history_service()
                .get_recent_assistant_messages_with_template_data(session_id, _TEMPLATE_ENRICH_MAX_TURNS)
            )

        redis_messages = assistant_template_messages

        # content -> template_data map. If two assistant turns share identical
        # content, the chronologically-latest template_data wins — acceptable
        # because identical content typically implies identical structured data.
        template_map = {
            msg["content"]: msg["template_data"]
            for msg in redis_messages
            if msg.get("role") == "assistant" and msg.get("template_data") and msg.get("content")
        }

        if not template_map:
            return messages

        enriched = 0
        for msg in reversed(messages):
            if enriched >= _TEMPLATE_ENRICH_MAX_TURNS:
                break
            if msg.get("role") == "assistant" and msg.get("content") in template_map:
                template_str = json.dumps(template_map[msg["content"]], ensure_ascii=False)
                msg["content"] += f"\n\n[이전 선택된 상품 데이터]\n{template_str}"
                enriched += 1

        return messages

    except Exception as e:
        logger.warning(f"[TEMPLATE_DATA] Failed: {e}")
        return messages


class TStationChatServiceV2:
    """V2 Chat service with multi-agent streaming support."""

    @staticmethod
    def _build_messages_with_user_info(request: TStationChatRequest) -> list[dict]:
        """Build messages with user info injected before current user message."""
        messages = [dict(msg) for msg in request.messages]

        # Remove duplicate "hi" from frontend
        if len(messages) >= 2 and messages[-2].get("role") == "user" and messages[-2].get("content") == "hi":
            messages.pop(-2)

        # Merge user info: JWT + UI (UI overrides)
        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)
        if request.user_info:
            user_info = {**(user_info or {}), **request.user_info}

        def _has_valid_location(location: dict | None) -> bool:
            if not isinstance(location, dict):
                return False
            xpos = location.get("xpos")
            ypos = location.get("ypos")
            return isinstance(xpos, (int, float)) and isinstance(ypos, (int, float))

        if user_info and not _has_valid_location(user_info.get("location")):
            user_info = {k: v for k, v in user_info.items() if k != "location"}

        # Build USER CONTEXT message if user_info available
        user_context_msg = None
        if user_info:
            safe_fields = {"mbr_nm", "location", "user_id"}
            lines = []
            for k, v in user_info.items():
                if k not in safe_fields:
                    continue
                if k == "location" and isinstance(v, dict):
                    lines.append(f"xpos: {v.get('xpos')}, ypos: {v.get('ypos')}")
                elif k == "user_id":
                    lines.append(f"mbr_no: {v}")
                else:
                    lines.append(f"{k}: {v}")

            if lines:
                user_context_msg = {
                    "role": "user",
                    "content": (
                        "## USER CONTEXT INFORMATION (Always Available)\n"
                        f"{chr(10).join(lines)}\n\n"
                        "## INSTRUCTIONS FOR AGENTS:\n"
                        "🔹 Always prioritize data provided directly by the user\n"
                        "🔹 If no direct data is provided, reference the personal data below\n"
                        "🔹 NEVER expose internal identifiers in responses\n"
                    ),
                }

        # Find last user message index and insert user_context before it
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx == -1:
            return messages

        # Insert user_context before last user message
        if user_context_msg:
            messages.insert(last_user_idx, user_context_msg)
            last_user_idx += 1

        # Add Korean prefix + current time to the current user message (now at last_user_idx)
        messages[last_user_idx]["content"] = (
            f"# Respond in Korean language\n{messages[last_user_idx]['content']}"
            f"\n\n[current_time: {get_current_time()}]"
        )

        return messages

    @staticmethod
    def _format_tool_context(tool_data: list[dict]) -> str:
        """Format accumulated structured tool results as a system prompt for conversation context.

        Results are ordered most-recent-first. Each entry shows the tool label,
        query conditions, and the structured data rows.
        """
        tool_labels = {
            "get_products_recommendations_tool": "타이어 추천 결과",
            "search_product_tool": "상품 검색 결과",
            "get_nearby_stores_tool": "근처 매장 목록",
            "get_store_list_tool": "매장 검색 결과",
            "get_store_inventory_tool": "매장 재고 현황",
            "get_orders_of_user_tool": "주문 내역",
            "check_compatibility_tool": "호환 사이즈 조회",
            "get_final_price_tool": "가격 조회",
            "compare_discount_tool": "할인 가격 비교",
            "get_cheapest_price_tool": "최저 혜택가",
            "get_product_description_tool": "상품 상세",
        }

        lines = [
            "[대화 중 조회한 데이터 — 참조용 (최신순)]",
            "아래는 이번 대화에서 tool로 조회한 실제 결과입니다.",
            "",
            "사용 규칙:",
            "A) 고객이 *이전 결과를 가리키는 경우* (예: '첫번째', '아까 18인치',",
            "   '가장 저렴한 것', '이 중에서') → 아래 데이터에서 매칭되는 항목으로 응답하세요.",
            "B) 고객이 *새 조건/시나리오를 제시*하거나(예: '빗길', '주말', '사계절',",
            "   '정숙성', '눈길' 등 새 사용 시나리오) *재시도를 요청*하는 경우",
            "   (예: '다시', '새로', '이번엔', '바꿔서', '다른 거', '이전 추천 말고')",
            "   → 적절한 tool을 다시 호출해 새 결과를 받아오세요. 아래 데이터에",
            "   *갇히지 마세요*. 이전 시나리오의 결과 안에서 새 시나리오 답을",
            "   *추정해 고르지 마세요* — 잘못된 추천이 됩니다.",
            "",
            "환각 금지: 가격·상품번호·재고 같은 *사실 데이터*를 *지어내지* 마세요.",
            "단, 신규 tool 호출로 새 데이터를 가져오는 것은 정상이며 권장되는 동작입니다.",
            "tool 결과만이 신뢰할 수 있는 사실의 출처입니다.",
            "",
        ]

        for idx, item in enumerate(tool_data[:3]):
            tool_name = item.get("tool", "")
            label = tool_labels.get(tool_name, tool_name)
            tool_input = item.get("input", {})
            data = item.get("data")

            # Mark recency
            recency = "최신" if idx == 0 else f"{idx + 1}번째 전"
            header = f"• [{recency}] {label}"
            if tool_input:
                input_str = ", ".join(f"{k}={v}" for k, v in tool_input.items())
                header += f" (조회 조건: {input_str})"
            lines.append(header)

            if isinstance(data, list):
                for i, row in enumerate(data[:5], 1):
                    if isinstance(row, dict):
                        if row.get("_truncated"):
                            lines.append(f"  ... {row['_truncated']}")
                        else:
                            row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
                            lines.append(f"  {i}. {row_str[:1000]}")
                    else:
                        lines.append(f"  {i}. {row}")
            elif isinstance(data, dict):
                row_str = " | ".join(f"{k}: {v}" for k, v in data.items())
                lines.append(f"  {row_str[:1500]}")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _active_context_values(slots: Any) -> set[str]:
        """Return stable confirmed identifiers used to prune prompt context.

        This is data-based compaction, not intent/routing logic: it only keeps
        facts that match already-confirmed IDs or sizes.
        """
        values = set()
        for field in ("goods_no", "shop_id", "tire_size"):
            value = getattr(slots, field, None)
            if value is not None:
                values.add(str(value))
        return values

    @staticmethod
    def _value_contains_active_context(value: Any, active_values: set[str]) -> bool:
        if not active_values:
            return False
        if isinstance(value, dict):
            return any(
                TStationChatServiceV2._value_contains_active_context(v, active_values)
                for v in value.values()
            )
        if isinstance(value, list):
            return any(TStationChatServiceV2._value_contains_active_context(v, active_values) for v in value)
        text = str(value)
        return any(active in text for active in active_values)

    @staticmethod
    def _compact_context_item(item: dict, active_values: set[str]) -> dict:
        """Narrow list rows to confirmed IDs/sizes when possible."""
        if not active_values:
            return item
        data = item.get("data")
        if not isinstance(data, list):
            return item

        matched_rows = [
            row
            for row in data
            if isinstance(row, dict)
            and TStationChatServiceV2._value_contains_active_context(row, active_values)
        ]
        if not matched_rows:
            return item

        compacted = dict(item)
        compacted["data"] = matched_rows
        if len(matched_rows) < len(data):
            compacted["data"].append(
                {"_truncated": f"{len(data) - len(matched_rows)} non-active row(s) omitted"}
            )
        return compacted

    @staticmethod
    def _select_tool_context_for_prompt(
        tool_data: list[dict],
        slots: Any,
        max_items: int = 3,
    ) -> list[dict]:
        """Select prompt context by confirmed data and recency.

        Redis keeps the full tool context for deterministic resolvers. This
        function only reduces what the LLM has to read in the current prompt.
        """
        if not tool_data:
            return []

        active_values = TStationChatServiceV2._active_context_values(slots)
        selected: list[dict] = []
        selected_ids: set[int] = set()

        if active_values:
            for item in tool_data:
                if TStationChatServiceV2._value_contains_active_context(item, active_values):
                    selected.append(TStationChatServiceV2._compact_context_item(item, active_values))
                    selected_ids.add(id(item))
                    if len(selected) >= max_items:
                        break

        for item in tool_data:
            if len(selected) >= max_items:
                break
            if id(item) in selected_ids:
                continue
            selected.append(item)

        return selected

    @staticmethod
    def _messages_chars(messages: list[dict]) -> int:
        """Count text chars in message contents for prompt-size observability."""
        total = 0
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total += len(content)
            else:
                total += len(str(content))
        return total

    @staticmethod
    def _is_user_context_message(message: dict) -> bool:
        """Identify injected user profile context that does not help domain classification."""
        content = message.get("content", "")
        return isinstance(content, str) and content.startswith("## USER CONTEXT INFORMATION")

    @staticmethod
    def _compact_messages_for_classifier(
        messages: list[dict],
        max_messages: int = 6,
        max_chars: int = 6000,
    ) -> list[dict]:
        """Build a smaller message view for the router LLM only.

        Domain classification needs recent conversation shape and the current
        user request. The full agent prompt still receives the unmodified
        messages, but the classifier should not pay for user-profile blocks or
        stale long history.
        """
        candidates = [
            dict(message)
            for message in messages
            if not TStationChatServiceV2._is_user_context_message(message)
        ]
        if not candidates:
            return [dict(message) for message in messages[-1:]]

        selected = candidates[-max_messages:]
        while len(selected) > 1 and TStationChatServiceV2._messages_chars(selected) > max_chars:
            selected = selected[1:]
        return selected

    @staticmethod
    def _resolve_goods_no_from_selection(user_text: str, prev_tool_data: list[dict]) -> str | None:
        """Match a user's list-selection reply against the prior search_product_tool
        result and return the goods_no of the matched item.

        When a previous turn returned multiple products and the user responds with
        an ordinal ("3.", "3번") or a name + size ("Ventus S2 AS 225/45R18"), this
        lets the coordinator capture goods_no before any agent runs — so that the
        subsequent Discovery→Transaction handoff is not blocked by the "goods_no
        missing in slots" safety check (Discovery may skip calling the search tool
        when it can resolve the pick from conversation history alone).

        Matching strategy (first hit wins):
          1. Ordinal at the start of the message → items[idx-1]
          2. Single item with matching tire_size
          3. Multiple items with matching tire_size → pick the one whose goods_nm
             has the highest token overlap (≥2 tokens required to avoid false hits)

        Only the most recent product-listing tool entry is inspected.
        Returns None when no confident match is found.

        Expected tool_context entry shape (produced by filter_for_context in
        services/tstation/source_filter.py, which is what gets persisted to Redis):
            {"tool": "search_product_tool" | "get_products_recommendations_tool",
             "data": [{"goods_no": "...", "goods_nm": "...", "tire_size_1": "..."}],
             "input": {...}}
        Note: `data` is a LIST directly, and the size field is `tire_size_1`
        (filter whitelist is {"goods_no", "goods_nm", "tire_size_1", ...}).
        """
        if not user_text or not prev_tool_data:
            return None

        items: list[dict] = []
        PRODUCT_LIST_TOOLS = {"search_product_tool", "get_products_recommendations_tool"}
        for entry in prev_tool_data:
            if entry.get("tool") not in PRODUCT_LIST_TOOLS:
                continue
            data = entry.get("data")
            # Primary shape: filter_for_context stores data as a list directly
            if isinstance(data, list):
                items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
                break
            # Defensive fallback: {"items": [...]} shape (raw tool output)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items = [it for it in data["items"] if isinstance(it, dict)]
                break
        if not items:
            return None

        text = user_text.strip()

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(items):
                goods_no = items[idx].get("goods_no")
                if goods_no:
                    return goods_no

        size_match = re.search(r"\d{3}/\d{2}R\d{2}", text)
        if size_match:
            target_size = size_match.group(0)
            # filter_for_context keeps `tire_size_1`; include legacy aliases
            # for safety if another path ever stores the raw field name.
            same_size = [
                item
                for item in items
                if (item.get("tire_size_1") or item.get("tire_size") or item.get("tireSize") or "") == target_size
            ]

            if len(same_size) == 1:
                goods_no = same_size[0].get("goods_no")
                if goods_no:
                    return goods_no

            if len(same_size) >= 2:
                tokens = [t.lower() for t in re.findall(r"[A-Za-z가-힣]+", text) if len(t) >= 2]
                best_item: dict | None = None
                best_score = 0
                for item in same_size:
                    goods_nm = (item.get("goods_nm") or "").lower()
                    score = sum(1 for tok in tokens if tok in goods_nm)
                    if score > best_score:
                        best_score = score
                        best_item = item
                if best_item is not None and best_score >= 2:
                    goods_no = best_item.get("goods_no")
                    if goods_no:
                        return goods_no

        return None

    @staticmethod
    def _resolve_tire_size_from_history_template(user_text: str, template_data: dict | None) -> str | None:
        """Match a user's vehicle-selection reply against the metadata of the
        most recent assistant message that rendered a `listCar` template, and
        return the picked car's tireSize.

        Mirrors `_resolve_shop_id_from_history_template` for cars. Uses the
        listCar template metadata as the source of truth because:
          - filter_for_context drops car_no as PII, so prev_tool_data has no
            usable per-car identifiers.
          - The listCar metadata is what was actually shown to the user and is
            persisted to Redis history (template_data field).
          - tireSize / tireSizeRe were added to CarMeta specifically so that
            tire_size can be recovered at selection time without an extra LLM
            tool call.

        Expected template_data shape (from chat_history_service.get_latest_template_data):
            {"type": "data", "template": "listCar",
             "data": {"listCar": [{"licensePlate": "12가3456", "info": "K7 2.5 GDI", ...}],
                      "metadata": [{"carNo": "12가3456", "carLncCd": "01",
                                    "tireSize": "225/45R17", "tireSizeRe": "225/45R17"}]}}

        Matching strategy (first hit wins):
          1. License plate verbatim ("12가3456", "123가4567") against carNo.
          2. Ordinal at the start ("1.", "1번", "2)") → metadata[idx-1].
          3. Token-overlap against listCar[i].info — unique top scorer required.
        """
        if not user_text or not isinstance(template_data, dict):
            return None

        latest_listcar: dict | None = None
        if template_data.get("template") == "listCar" and isinstance(template_data.get("data"), dict):
            latest_listcar = template_data.get("data")
        elif isinstance(template_data.get("listCar"), list):
            # Defensive: allow passing the inner payload directly.
            latest_listcar = template_data
        if latest_listcar is None:
            return None

        cars = latest_listcar.get("listCar") or []
        metadata = latest_listcar.get("metadata") or []
        if not isinstance(cars, list) or not isinstance(metadata, list) or not metadata:
            return None

        text = user_text.strip()

        # 1. License plate match against metadata[i].carNo.
        plate_match = re.search(r"\d{2,3}[가-힣]\d{4}", text)
        if plate_match:
            target_plate = plate_match.group(0)
            for meta in metadata:
                if not isinstance(meta, dict):
                    continue
                if meta.get("carNo") == target_plate:
                    tire_size = meta.get("tireSize")
                    if tire_size:
                        return tire_size

        # 2. Ordinal pick.
        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(metadata):
                meta = metadata[idx]
                if isinstance(meta, dict):
                    tire_size = meta.get("tireSize")
                    if tire_size:
                        return tire_size

        # 3. Token-overlap against listCar[i].info. Require unique top scorer.
        tokens = [t for t in re.findall(r"[A-Za-z가-힣0-9]+", text) if len(t) >= 2]
        if tokens:
            scored: list[tuple[int, dict]] = []
            for car, meta in zip(cars, metadata):
                if not isinstance(car, dict) or not isinstance(meta, dict):
                    continue
                info = (car.get("info") or car.get("description") or "").lower()
                score = sum(1 for tok in tokens if tok.lower() in info)
                if score > 0:
                    scored.append((score, meta))
            if scored:
                max_score = max(s for s, _ in scored)
                top = [meta for s, meta in scored if s == max_score]
                if len(top) == 1:
                    tire_size = top[0].get("tireSize")
                    if tire_size:
                        return tire_size

        return None

    @staticmethod
    def _resolve_shop_id_from_selection(user_text: str, prev_tool_data: list[dict]) -> str | None:
        """Match a user's list-selection reply against the prior
        get_nearby_stores_tool / get_store_list_tool result and return the
        shop_id of the matched store.

        Mirrors _resolve_goods_no_from_selection for stores. When a store list
        had more than 1 store, `_apply_tool_derived_slots` skips shop_id
        auto-save (can't guess which one). This resolver fills that gap by
        matching the user's selection reply to the prior list.

        Matching strategy (first hit wins):
          1. Ordinal at the start ("1.", "5번", "3)") → items[idx-1]
          2. Token-overlap against shop_nm — only resolves when exactly ONE
             store has the top score (≥1 token match), to avoid ambiguous
             resolution when multiple stores share a substring like "한남점".

        Expected tool_context entry shape (from filter_for_context):
            {"tool": "get_nearby_stores_tool" | "get_store_list_tool",
             "data": [{"shop_id": "F07782", "shop_nm": "티스테이션 한남점",
                       "distance_km": 4.59, "addr_base": "..."}],
             "input": {...}}
        """
        if not user_text or not prev_tool_data:
            return None

        STORE_TOOLS = {"get_nearby_stores_tool", "get_store_list_tool"}
        items: list[dict] = []
        for entry in prev_tool_data:
            if entry.get("tool") not in STORE_TOOLS:
                continue
            data = entry.get("data")
            # Primary shape: filter_for_context stores data as a list directly
            if isinstance(data, list):
                items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
                break
            # Defensive fallback: {"stores": [...]} shape (raw tool output)
            if isinstance(data, dict) and isinstance(data.get("stores"), list):
                items = [it for it in data["stores"] if isinstance(it, dict)]
                break
        if not items:
            return None

        text = user_text.strip()

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(items):
                shop_id = items[idx].get("shop_id")
                if shop_id:
                    return shop_id

        # Token-overlap match against shop_nm. Require a unique top-scoring
        # store to avoid auto-resolving ambiguous replies like a bare "한남점"
        # that could match several brands at the same address area.
        tokens = [t for t in re.findall(r"[A-Za-z가-힣]+", text) if len(t) >= 2]
        if tokens:
            scored: list[tuple[int, dict]] = []
            for item in items:
                shop_nm = item.get("shop_nm") or ""
                score = sum(1 for tok in tokens if tok in shop_nm)
                if score > 0:
                    scored.append((score, item))
            if scored:
                max_score = max(s for s, _ in scored)
                top = [item for s, item in scored if s == max_score]
                if len(top) == 1:
                    shop_id = top[0].get("shop_id")
                    if shop_id:
                        return shop_id

        return None

    @staticmethod
    def _resolve_shop_id_from_history_template(user_text: str, template_data: dict | None) -> str | None:
        """Match a user's list-selection reply against the metadata of the most
        recent assistant message that rendered a `location` template.

        Used as a fallback when prev_tool_data lookup fails (e.g., tool entry
        was evicted, or filter_for_context never persisted it). The template
        metadata is the authoritative source of "what stores were actually
        shown to the user", so matching against it is more robust than against
        raw tool output.

        Expected template_data shape (from chat_history_service.get_latest_template_data):
            {"type": "data", "template": "location",
             "data": {"stores": [{"nameAddress": "티스테이션 한남점", ...}],
                      "metadata": [{"shopId": "F07782"}]}}

        Matching strategy:
          1. Ordinal at the start ("1.", "5번", "3)") → metadata[idx-1].shopId
          2. Token-overlap against stores[].nameAddress — only resolves when
             exactly ONE store has the top score
        """
        if not user_text or not isinstance(template_data, dict):
            return None

        text = user_text.strip()

        target_template: dict | None = None
        if template_data.get("template") == "location" and isinstance(template_data.get("data"), dict):
            target_template = template_data.get("data")
        elif isinstance(template_data.get("stores"), list):
            # Defensive: allow passing the inner payload directly.
            target_template = template_data

        if not target_template:
            return None

        stores = target_template.get("stores") or []
        metadata = target_template.get("metadata") or []
        if not isinstance(stores, list) or not isinstance(metadata, list):
            return None
        if not stores or len(stores) != len(metadata):
            return None

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(metadata):
                meta = metadata[idx]
                if isinstance(meta, dict):
                    shop_id = meta.get("shopId")
                    if shop_id:
                        return shop_id

        tokens = [t for t in re.findall(r"[A-Za-z가-힣]+", text) if len(t) >= 2]
        if tokens:
            scored: list[tuple[int, dict]] = []
            for store, meta in zip(stores, metadata):
                if not isinstance(store, dict) or not isinstance(meta, dict):
                    continue
                name = store.get("nameAddress") or store.get("name") or store.get("title") or ""
                score = sum(1 for tok in tokens if tok in name)
                if score > 0:
                    scored.append((score, meta))
            if scored:
                max_score = max(s for s, _ in scored)
                top = [meta for s, meta in scored if s == max_score]
                if len(top) == 1:
                    shop_id = top[0].get("shopId")
                    if shop_id:
                        return shop_id

        return None

    @staticmethod
    async def chat(request: TStationChatRequest):
        """
        T-Station AI Chat V2 - Multi-Agent Streaming
        """
        logger.debug(f"[CHAT_V2] Received request: {request}")
        _t0 = time.perf_counter()
        _t_slots = _t0  # fallback: if slot processing fails, slots latency shows 0ms
        _t_classify = _t0  # fallback: if classify fails

        set_tstation_be_token(request.access_token)

        # PII Guardrail: check the latest user message before any agent processing
        last_user_msg = next(
            (m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"),
            "",
        )
        # Seed Discovery's car_no mismatch audit (deterministic guard against
        # the LLM recommending tires for a registered car the user did not name).
        from services.tstation.agents.b_discovery_agent._car_no_audit import set_user_message as _audit_set_user_message
        _audit_set_user_message(last_user_msg)
        pii_detected = check_pii(last_user_msg)
        if pii_detected:
            logger.warning(f"[CHAT_V2] PII guardrail blocked: {pii_detected}")
            if request.stream:
                return StreamingResponse(
                    TStationChatServiceV2._stream_guardrail_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            return TStationChatResponse(content=GUARDRAIL_RESPONSE)

        # Pre-classifier intercept: "<지역> 제일 저렴한 매장" 류 광역 가격
        # 비교 질문은 단일 매장으로 안내할 수 없으므로 분류기/agent 호출 없이
        # 즉시 canned quickReply 응답으로 종료. Transaction agent prompt
        # 가드는 LLM 우회 가능성이 있어 보조 layer 로만 유지.
        if _is_regional_cheapest_query(last_user_msg):
            logger.info(
                "[CHAT_V2] Regional cheapest-store fast-path intercept: %s",
                last_user_msg[:80],
            )
            _regional_canned_msg = (
                "매장·시기·상품에 따라 적용되는 프로모션이 달라 '제일 저렴한 매장' 을 "
                "한 곳으로 안내드리기 어려워요 😊\n\n"
                "다만 **온라인 구매 시 무료배송 + 무료장착**이고, 원하시는 상품을 선택하시면 "
                "실시간 할인가를 바로 확인하실 수 있어요."
            )
            if request.stream:
                return StreamingResponse(
                    TStationChatServiceV2._stream_regional_cheapest_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            return TStationChatResponse(content=_regional_canned_msg)

        # Create parent "chat" span before classify so ALL sub-calls (classify,
        # agents, qc) are nested under it as children in Langfuse.
        _parent_span = None
        _parent_span_id = None
        _set_trace_name(last_user_msg[:60] if last_user_msg else None)
        if _tracing_enabled:
            _parent_span = tracer.start_span(
                name="chat",
                trace_context={"trace_id": request.tracing_id},
                input=_truncate(last_user_msg),
            )
            # Lock trace.input to the user's message right at the start so the
            # Langfuse UI doesn't fall back to whichever child chain (e.g. QC)
            # last touched the trace. trace.output is set in _stream_response_multi
            # at the end of the stream.
            _parent_span.update_trace(
                name=(last_user_msg[:60] if last_user_msg else "chat"),
                session_id=request.session_id,
                user_id=request.user_id,
                input=_truncate(last_user_msg),
            )
            _parent_span_id = _parent_span.id

        # Step 1: Prep raw messages — enrichment happens after Redis prefetch below.
        # Build plain messages now as a fallback (used if Redis prefetch fails entirely).
        raw_messages = [dict(msg) for msg in request.messages]
        _request_plain = TStationChatRequest(
            messages=raw_messages,
            session_id=request.session_id,
            user_id=request.user_id,
            access_token=request.access_token,
            stream=request.stream,
            user_info=request.user_info,
        )
        messages = TStationChatServiceV2._build_messages_with_user_info(_request_plain)

        # Keep at most 20 messages (10 turns) before sending to LLM.
        # Slots and last_user_text are extracted from request.messages (untouched above).
        _MAX_HISTORY_MESSAGES = 20
        if len(messages) > _MAX_HISTORY_MESSAGES:
            dropped = len(messages) - _MAX_HISTORY_MESSAGES
            messages = messages[-_MAX_HISTORY_MESSAGES:]
            logger.debug(f"[CHAT_V2] History truncated: dropped {dropped} oldest messages, keeping last {_MAX_HISTORY_MESSAGES}")
        classifier_messages = TStationChatServiceV2._compact_messages_for_classifier(messages)

        # Slot processing: load → extract → classify (with LLM slots) → merge → save → inject
        # Wrapped in try/except so slot failures never block the main chat flow
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

        domains = None
        slot_context = None
        slot_context_with_intent = None
        tool_context = None
        routing_result = None
        speculative_classify_future: concurrent.futures.Future | None = None
        classify_future: concurrent.futures.Future | None = None

        # Defaults hoisted above the try block so the P0 auto-chain gate below
        # can safely inspect them even if slot processing raises.
        last_user_text = ""
        regex_slots = ConversationSlots()
        merged_slots = ConversationSlots()
        goods_no_resolved_this_turn = False
        quick_reply_domain_values: list[str] = []
        predicted_domain_values: list[str] = []

        try:
            chat_history_svc = get_chat_history_service()

            # 1) Load only the targeted Redis data needed on the hot path (using async Pipeline).
            (
                recent_template_msgs,
                existing_slots,
                prev_tool_data,
                latest_listcar_tmpl,
                latest_location_tmpl,
                quick_reply_domain_values,
                predicted_domain_values,
            ) = await chat_history_svc.get_chat_context_pipeline_async(
                request.session_id, _TEMPLATE_ENRICH_MAX_TURNS
            )
            _t_slots = time.perf_counter()
            logger.debug(f"[SLOTS] Loaded existing slots: {existing_slots.model_dump()}")

            # 1a) Enrich messages with template_data from prefetched history and rebuild.
            # Overrides the plain fallback built above — no extra Redis round-trip.
            enriched_messages = _enrich_messages_with_template_data(
                raw_messages, request.session_id, assistant_template_messages=recent_template_msgs
            )
            _request_enriched = TStationChatRequest(
                messages=enriched_messages,
                session_id=request.session_id,
                user_id=request.user_id,
                access_token=request.access_token,
                stream=request.stream,
                user_info=request.user_info,
            )
            messages = TStationChatServiceV2._build_messages_with_user_info(_request_enriched)
            if len(messages) > _MAX_HISTORY_MESSAGES:
                messages = messages[-_MAX_HISTORY_MESSAGES:]
            messages_chars = TStationChatServiceV2._messages_chars(messages)
            classifier_messages = TStationChatServiceV2._compact_messages_for_classifier(messages)
            classifier_messages_chars = TStationChatServiceV2._messages_chars(classifier_messages)
            logger.debug("[CONTEXT] messages_count=%d messages_chars=%d", len(messages), messages_chars)
            logger.debug(
                "[CLASSIFIER_CTX] messages_count=%d messages_chars=%d original_messages=%d original_chars=%d",
                len(classifier_messages),
                classifier_messages_chars,
                len(messages),
                messages_chars,
            )
            logger.debug(f"[CHAT_V2] Messages: {json.dumps(messages, ensure_ascii=False, separators=(',', ':'))}")

            classify_future = _try_submit_speculative(
                _coordinator.classify_multi_intent,
                classifier_messages,
                session_id=request.session_id,
                user_id=request.user_id,
                trace_id=request.tracing_id,
                parent_span_id=_parent_span_id,
            )

            # 2) Extract regex-based slots from the LATEST user message only
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    last_user_text = msg.get("content", "")
                    break
            regex_slots = ConversationSlots.extract_from_user_text(last_user_text)

            # 3) Merge: existing → regex (full merge with dependency reset)
            merged_slots = existing_slots.merge(regex_slots)
            logger.debug(f"[SLOTS] Merged slots: {merged_slots.model_dump()}")

            # 3.5) If the user explicitly asked for a recommendation in THIS turn
            # AND did not also include a fresh transactional keyword, clear any
            # stale transactional pending_intent from earlier turns.
            # A mixed turn like "추천해준 것 중 이거 가격 얼마야?" must NOT be cleared —
            # the fresh "price" extracted this turn wins over the old intent.
            # merge() only applies non-None values so we can't express "clear" via
            # regex_slots alone — it has to happen here after the merge.
            user_asked_for_recommend = ConversationSlots.has_recommend_intent(last_user_text)
            turn_has_new_transactional = regex_slots.pending_intent is not None
            if merged_slots.pending_intent is not None and user_asked_for_recommend and not turn_has_new_transactional:
                logger.debug(
                    f"[SLOTS] Clearing stale pending_intent={merged_slots.pending_intent!r} "
                    f"— user switched back to recommendation"
                )
                merged_slots.pending_intent = None

            # 3.6) Non-self car negation: when user explicitly excludes their
            # registered cars and asks about a different vehicle model
            # ("내차말고 G90", "다른 차종 그랜저", "저장차 아닌 모델Y" etc.), any
            # tire_size / goods_no / car_model carried over from a prior turn
            # belongs to the WRONG vehicle. If we keep them in merged_slots, the
            # discovery agent receives `[확인된 고객 정보 - 타이어 사이즈: ...]`
            # for the OLD car and reuses that size for the NEW car's
            # recommendation (observed in Langfuse trace
            # 97dde3aa79d2415e90ed5fdaf93243d6: "내차말고 제네시스 g90" → recs
            # came back for 235/55R19 from a prior turn instead of G90 sizes).
            #
            # Clearing here (not in `_apply_tool_derived_slots`) is necessary
            # because the stale values must be gone BEFORE slot_context is
            # built for this turn's LLM prompt — `_apply_tool_derived_slots`
            # only runs AFTER tool calls, which is too late.
            if last_user_text and _NON_SELF_CAR_RE.search(last_user_text):
                cleared = []
                if merged_slots.tire_size is not None:
                    cleared.append(f"tire_size={merged_slots.tire_size!r}")
                    merged_slots.tire_size = None
                if merged_slots.goods_no is not None:
                    cleared.append(f"goods_no={merged_slots.goods_no!r}")
                    merged_slots.goods_no = None
                if merged_slots.car_model is not None:
                    cleared.append(f"car_model={merged_slots.car_model!r}")
                    merged_slots.car_model = None
                if cleared:
                    logger.debug(
                        f"[SLOTS] Non-self car negation in user text "
                        f"{last_user_text[:60]!r} — cleared {', '.join(cleared)} "
                        f"so the new vehicle's CAR MODEL DISPLAY flow can run"
                    )

            # 3.7) Tool context already loaded in step 1 (parallel with get_slots).

            # 3.7.5) Recommendation-flow stale-clear.
            # If the most recent product-listing tool in the conversation is
            # `get_products_recommendations_tool` AND the current turn carries no
            # fresh transactional keyword, the customer is browsing recommendations
            # — any inherited transactional `pending_intent` from a much earlier
            # turn is stale and must NOT be allowed to redirect a bare product-name
            # selection (e.g. "1. 벤투스 S2 AS") into the Transaction auto-chain
            # (P0 gate at step 4 below). Without this, picking a product after a
            # recommendation list silently calls `get_final_price_tool` instead of
            # `get_product_description_tool`, which surprises the user.
            #
            # Step 3.5 above only fires when the user explicitly re-asks for a
            # recommendation in this turn. Step 3.7.5 covers the implicit case
            # where the user just *continues* the recommendation flow by picking.
            #
            # Search-triggered flows (`search_product_tool` is the most recent
            # listing tool, fired because the user said e.g. "벤투스 가격") are
            # intentionally left untouched so the auto-chain still runs once
            # goods_no resolves — that's the design behind the P0 gate.
            #
            # `goods_no is None` guard: when the user has already committed to a
            # specific product (slots.goods_no inherited from a prior pick), they
            # have moved past pure recommendation browsing into the order/store
            # selection phase. Clearing pending_intent here would emit downstream
            # store cards with `isBookingFlow=false`, dead-ending the FE click
            # (description-only `/append` short path). Only fire when goods_no is
            # still unresolved (true browsing state, e.g. bare list pick "1. 벤투스").
            if (
                merged_slots.pending_intent is not None
                and not turn_has_new_transactional
                and prev_tool_data
                and merged_slots.goods_no is None
            ):
                most_recent_listing_tool: str | None = None
                for entry in reversed(prev_tool_data):
                    tool = entry.get("tool")
                    if tool in ("search_product_tool", "get_products_recommendations_tool"):
                        most_recent_listing_tool = tool
                        break
                if most_recent_listing_tool == "get_products_recommendations_tool":
                    logger.debug(
                        f"[SLOTS] Clearing stale pending_intent={merged_slots.pending_intent!r} "
                        f"— most recent list source is get_products_recommendations_tool "
                        f"(user is in recommendation flow, not transactional)"
                    )
                    merged_slots.pending_intent = None

            # 3.8) Resolve goods_no from the user's list-selection reply matched against
            # the most recent search_product_tool result. Without this, Discovery may
            # hand off ("상품 확인했어요. 바로 재고 확인으로 이어갑니다") without
            # actually calling a tool in the current turn — leaving goods_no=None in
            # slots and causing the coordinator's P0 safety check to stop the chain
            # before Transaction runs.
            if merged_slots.goods_no is None and prev_tool_data:
                resolved_goods_no = TStationChatServiceV2._resolve_goods_no_from_selection(
                    last_user_text, prev_tool_data
                )
                if resolved_goods_no:
                    merged_slots.goods_no = resolved_goods_no
                    goods_no_resolved_this_turn = True
                    logger.debug(
                        f"[SLOTS] Resolved goods_no={resolved_goods_no!r} from user's "
                        f"list-selection against prior search_product_tool result"
                    )

            # 3.85) Resolve tire_size from the user's vehicle-selection reply matched
            # against the metadata of the most recent `listCar` template.
            # filter_for_context drops car_no as PII, so prev_tool_data has no
            # car identifiers to match against — instead we read the listCar
            # template metadata (which now carries tireSize / tireSizeRe per
            # entry, populated by _map_list_car). Without this, a listCar pick
            # that the LLM later "answers from memory" (skipping
            # get_products_recommendations_tool) leaves tire_size=None — and
            # subsequent "구매할게" / "매장 선택 후 주문" turns then fail the
            # goal-router's `size` step and route to Discovery instead of
            # Transaction.
            if merged_slots.tire_size is None:
                try:
                    resolved_tire_size = TStationChatServiceV2._resolve_tire_size_from_history_template(
                        last_user_text, latest_listcar_tmpl
                    )
                    if resolved_tire_size:
                        merged_slots.tire_size = resolved_tire_size
                        logger.debug(
                            f"[SLOTS] Resolved tire_size={resolved_tire_size!r} from user's "
                            f"vehicle-selection against last `listCar` template metadata"
                        )
                except Exception as e:
                    logger.warning(f"[SLOTS] history tire_size resolver failed: {e}")

            # 3.9) Resolve shop_id from the user's list-selection reply matched against
            # the most recent get_nearby_stores_tool / get_store_list_tool result.
            # `_apply_tool_derived_slots` only auto-saves shop_id when the tool returned
            # exactly 1 store — multi-result lists (nearby stores within radius, region
            # searches) leave shop_id=None. When the user then picks a store from that
            # list, STEP 5A Step 4 needs shop_id to call get_store_schedule_tool; without
            # this resolver the LLM tends to re-run get_store_list_tool and stall at the
            # location template instead of progressing to datepick.
            if merged_slots.shop_id is None and prev_tool_data:
                resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_selection(last_user_text, prev_tool_data)
                if resolved_shop_id:
                    merged_slots.shop_id = resolved_shop_id
                    logger.debug(
                        f"[SLOTS] Resolved shop_id={resolved_shop_id!r} from user's "
                        f"list-selection against prior store-list tool result"
                    )
                else:
                    # Diagnostic: log why prev_tool_data path didn't match.
                    store_tool_entries = [
                        e.get("tool")
                        for e in prev_tool_data
                        if e.get("tool") in ("get_nearby_stores_tool", "get_store_list_tool")
                    ]
                    logger.debug(
                        f"[SLOTS] shop_id resolver (tool path) no-match: "
                        f"user_text={last_user_text[:60]!r}, "
                        f"store_tool_entries={store_tool_entries}"
                    )

            # 3.91) Fallback: resolve shop_id from the metadata of the most recent
            # assistant message that rendered a `location` template. This covers
            # cases where prev_tool_data is missing or stale (e.g., the prior
            # multi-store turn hit silent template-validation failure but the
            # template_data was still persisted by chat_message.stream_chat_response).
            # template_data shape (from chat_message.py):
            #   {"type": "data", "template": "location",
            #    "data": {"stores": [...], "metadata": [{"shopId": "F00098"}, ...]}}
            if merged_slots.shop_id is None:
                try:
                    resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_history_template(
                        last_user_text, latest_location_tmpl
                    )
                    if resolved_shop_id:
                        merged_slots.shop_id = resolved_shop_id
                        logger.debug(
                            f"[SLOTS] Resolved shop_id={resolved_shop_id!r} from user's "
                            f"list-selection against last `location` template metadata"
                        )
                except Exception as e:
                    logger.warning(f"[SLOTS] history shop_id fallback failed: {e}")

            # 4) Save merged slots to Redis without blocking the async request path.
            await chat_history_svc.save_slots_async(request.session_id, merged_slots, user_id=request.user_id)

            # 5) Build slot context strings for agent injection.
            # `slot_context` (no pending_intent) is the default for all agents — Discovery,
            # Support, and Leading must route purely from prior conversation context, never
            # from a coordinator-set intent slot, so a stale "가격" / "재고" intent from an
            # earlier turn does not silently force a Transaction handoff on a recommendation
            # pick. `slot_context_with_intent` is the full version, injected ONLY for the
            # Transaction agent which acts directly on the intent (Flow 1 / 2 / 6 routing).
            slot_context = merged_slots.to_prompt_context(include_pending_intent=False) if merged_slots.has_any() else None
            slot_context_with_intent = merged_slots.to_prompt_context(include_pending_intent=True) if merged_slots.has_any() else None
            # When pending_intent is unset both strings are equal — collapse so the
            # downstream coordinator only injects one block.
            if slot_context_with_intent == slot_context:
                slot_context_with_intent = None

            # 6) Format tool context for prompt injection
            if prev_tool_data:
                prompt_tool_data = TStationChatServiceV2._select_tool_context_for_prompt(prev_tool_data, merged_slots)
                tool_context = TStationChatServiceV2._format_tool_context(prompt_tool_data)
                # Cap tool context to avoid consuming too much of the context window
                if len(tool_context) > 4000:
                    tool_context = tool_context[:4000] + "\n... (일부 생략)"
                logger.debug(
                    "[TOOL_CTX] Loaded %d tool results, injected %d (%d chars)",
                    len(prev_tool_data),
                    len(prompt_tool_data),
                    len(tool_context),
                )

        except Exception as e:
            logger.exception(f"[SLOTS] Slot processing failed, continuing without slots: {e}")
            slot_context = None
            slot_context_with_intent = None

        # Domain classification (separate from slot processing — must not fail)
        # Fast-path order: chip_context → quickReplies → predictedDomains → goal/rule → LLM.
        # Each layer returns None to defer to the next.
        # Wrapped in a manual `classify` span so Langfuse shows a single clean
        # node: input=last user text, output=domains. Any nested LLM call from
        # classify_multi_intent attaches under this span via parent_span_id.
        _chip_domain: str | None = None
        _chip_ctx = request.chip_context or {}
        if isinstance(_chip_ctx, dict):
            _d = _chip_ctx.get("domain")
            if _d in _VALID_CHIP_DOMAINS:
                _chip_domain = _d

        with _trace_span(
            "classify",
            trace_id=request.tracing_id,
            parent_span_id=_parent_span_id,
            input=last_user_text,
        ) as _classify_span:
            import asyncio

            if classify_future is None:
                classify_future = _speculative_classify_executor.submit(
                    _coordinator.classify_multi_intent,
                    classifier_messages,
                    session_id=request.session_id,
                    user_id=request.user_id,
                    trace_id=request.tracing_id,
                    parent_span_id=_classify_span.id or _parent_span_id,
                )

            if settings.AI_SPECULATIVE_CLASSIFY_ENABLED:
                predicted_domains = None
                if _chip_domain:
                    predicted_domains = [MultiAgentDomain.Domain[_chip_domain]]
                    _classify_path = "chip_speculative"
                else:
                    predicted_domains = (
                        _domains_from_strings(quick_reply_domain_values)
                        or _domains_from_strings(predicted_domain_values)
                        or _goal_based_classify(last_user_text, merged_slots)
                        or _support_fast_path(last_user_text)
                        or _rule_based_classify(last_user_text, merged_slots)
                    )
                    _classify_path = "speculative"

                transaction_predicted = (
                    predicted_domains is not None
                    and MultiAgentDomain.Domain.TRANSACTION in predicted_domains
                )
                if (
                    predicted_domains is not None
                    and not transaction_predicted
                    and (_chip_domain or _is_speculative_safe(predicted_domains))
                ):
                    domains = predicted_domains
                    speculative_classify_future = classify_future
                    logger.debug("[CLASSIFIER] %s domains=%s — background verify", _classify_path, [d.value for d in domains])
                else:
                    domains, routing_result = await asyncio.to_thread(classify_future.result)
                    _classify_path = "llm_profile" if transaction_predicted else "llm"
            else:
                domains, routing_result = await asyncio.to_thread(classify_future.result)
                _classify_path = "llm"

            if routing_result is not None:
                messages = StreamingMultiAgentCoordinator._inject_conversation_context(messages, routing_result)
            messages = StreamingMultiAgentCoordinator._inject_client_prompt(messages)
            # Langfuse shows the first ~100 chars of `output` as the span preview.
            # Lead with a one-line summary so the trace tree reads like a story
            # without needing to expand the node.
            _domain_label = "+".join(d.value for d in domains) if domains else "?"
            _classify_summary = f"{_classify_path} → {_domain_label}"
            logger.info(
                "[CLASSIFIER_RESULT] path=%s domains=%s profile=%s",
                _classify_path,
                [d.value for d in domains],
                (
                    routing_result.agent_prompt_profile.value
                    if routing_result and isinstance(routing_result.agent_prompt_profile, AgentPromptProfile)
                    else None
                ),
            )
            _classify_span.update(
                output=_truncate({
                    "summary": _classify_summary,
                    "domains": [d.value for d in domains],
                    "path": _classify_path,
                    "user_behavior": getattr(routing_result, "user_behavior", None) if routing_result else None,
                    "flow": getattr(routing_result, "flow", None) if routing_result else None,
                    "agent_prompt_profile": (
                        routing_result.agent_prompt_profile.value
                        if routing_result and isinstance(routing_result.agent_prompt_profile, AgentPromptProfile)
                        else None
                    ),
                }),
            )
        _t_classify = time.perf_counter()

        # Post-classification redirect: when the user's current-turn reply was a
        # list-selection that just resolved goods_no (via step 3.8) and a
        # transactional intent is still pending, the classifier may still pick
        # [DISCOVERY] alone because the CONTINUATION DETECTION rule treats
        # list-selection replies as same-domain continuation. But at this point
        # Discovery has nothing useful to do — it would only emit a handoff line
        # ("상품 확인했어요. 바로 재고 조회로 이어갑니다") and then decide_next_action
        # often returns STOP, stranding the user without the actual transactional
        # answer. Force-route directly to [TRANSACTION] for this narrow case.
        #
        # Guard: only when goods_no was resolved THIS turn from a list-selection,
        # so later "다른 사이즈 보기" / "이 타이어 맞아?" type turns (goods_no carried
        # but not freshly picked) still go through Discovery normally.
        if (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.DISCOVERY
            and goods_no_resolved_this_turn
            and merged_slots.pending_intent is not None
        ):
            logger.debug(
                f"[COORDINATOR] Post-classification redirect: goods_no={merged_slots.goods_no!r} "
                f"resolved from list-selection + pending_intent={merged_slots.pending_intent!r} "
                f"→ [DISCOVERY] → [TRANSACTION]"
            )
            log_classifier_redirect(
                trace_id=request.tracing_id,
                rule="post_classification",
                classifier_domains=["discovery"],
                corrected_domains=["transaction"],
                user_text=last_user_text,
                user_behavior=getattr(routing_result, "user_behavior", "") or "",
                slots={
                    "goods_no": merged_slots.goods_no,
                    "pending_intent": merged_slots.pending_intent,
                    "goods_no_resolved_this_turn": True,
                },
            )
            domains = [MultiAgentDomain.Domain.TRANSACTION]

        # P0c redirect: classifier picked [DISCOVERY] but goods_no is ALREADY
        # known (carried from a prior turn) AND the user expressed a FRESH
        # transactional intent this turn (재고/가격/주문/매장). Without this,
        # Discovery has no useful action — it would emit a fallback line like
        # "재고 확인을 이어갈게요" without calling any tool, then the stream ends.
        #
        # Difference from the redirect above:
        #   - The above requires `goods_no_resolved_this_turn=True` (just-resolved
        #     via list-selection THIS turn).
        #   - This one fires when goods_no was resolved in a PRIOR turn and
        #     carried via slots into the current turn.
        #
        # Guard: `regex_slots.pending_intent is not None` — the intent must be
        # FRESHLY expressed in the current user message (regex extraction over
        # last_user_text). Using `merged_slots.pending_intent` would over-route
        # cases where a stale intent lingers from many turns ago without the
        # user re-asking. Fresh-intent guard prevents misrouting follow-up
        # browse turns ("이 타이어 맞아?" / "다른 사이즈 있어?") that carry
        # goods_no but no transactional anchor.
        elif (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.DISCOVERY
            and merged_slots.goods_no is not None
            and regex_slots.pending_intent is not None
            and not (
                routing_result is not None
                and routing_result.agent_prompt_profile == AgentPromptProfile.DISCOVERY_RECOMMENDATION
            )
        ):
            logger.debug(
                f"[COORDINATOR] P0c DISCOVERY→TX redirect: classifier=[DISCOVERY], "
                f"goods_no={merged_slots.goods_no!r} (carried), "
                f"fresh_intent={regex_slots.pending_intent!r}, "
                f"session_id={request.session_id} → domains=[TRANSACTION]"
            )
            log_classifier_redirect(
                trace_id=request.tracing_id,
                rule="P0c",
                classifier_domains=["discovery"],
                corrected_domains=["transaction"],
                user_text=last_user_text,
                user_behavior=getattr(routing_result, "user_behavior", "") or "",
                slots={
                    "goods_no_carried": merged_slots.goods_no,
                    "fresh_intent": regex_slots.pending_intent,
                },
            )
            domains = [MultiAgentDomain.Domain.TRANSACTION]

        # P0 auto-chain code gate: when a transactional intent (price/stock/order)
        # is outstanding — either expressed THIS turn or inherited from a prior turn
        # whose tool has not yet fulfilled it — and some product is identifiable
        # (current turn text OR inherited from prior turns), but no goods_no is yet
        # confirmed, override the classifier's single-domain [DISCOVERY] pick to
        # [DISCOVERY, TRANSACTION]. Discovery resolves goods_no via search_product_tool,
        # then Transaction proceeds (price/inventory/order) in the same user turn —
        # removing the redundant "네" confirmation step.
        #
        # Guard conditions (ALL must hold):
        #   1. Classifier chose exactly [DISCOVERY] — no override of TX/SUPPORT/LEADING.
        #   2. `merged_slots.pending_intent` is set — fresh this turn OR inherited
        #      from an earlier turn whose tool has not yet fulfilled the intent.
        #      Example: user asks "재고 있어?" in turn 1, search returns multiple
        #      results, user picks a specific size in turn 2 — the stock intent is
        #      still pending and should chain to Transaction once goods_no resolves.
        #      Short replies like "네" do NOT trigger because condition #4 requires
        #      a real product hint (tire_size / tire_model / brand keyword), which
        #      a bare "네" never satisfies.
        #   3. `merged_slots.goods_no is None` — goods_no-known turns stay TX-only.
        #   4. Product hint present via ONE of:
        #        a. `merged_slots.tire_size` — current turn OR inherited from a prior
        #           turn (intentional: user says "225/45R18" then later "가격 얼마?"
        #           should continue the same product context, not re-ask).
        #        b. `merged_slots.tire_model` — typically confirmed in prior turns via
        #           LLM slot extraction; inheriting it is by design.
        #        c. Brand/model keyword in CURRENT turn text (벤투스/Dynapro/...).
        #      Pure no-product queries with no prior context ("가격 얼마에요?" on a
        #      fresh session) stay Discovery-only so Discovery can ask which model.
        #
        # Safety: even when the gate fires, the coordinator verifies goods_no was
        # actually resolved after Discovery before running Transaction (search with
        # 0/multiple results → chain stops). See StreamingMultiAgentCoordinator.stream().
        skip_decision = False
        if (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.DISCOVERY
            and merged_slots.pending_intent is not None
            and merged_slots.goods_no is None
            and (
                merged_slots.tire_size is not None
                or merged_slots.tire_model is not None
                or ConversationSlots.has_product_keyword(last_user_text)
            )
            and not (
                routing_result is not None
                and routing_result.agent_prompt_profile == AgentPromptProfile.DISCOVERY_RECOMMENDATION
            )
        ):
            domains = [MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION]
            skip_decision = True
            logger.debug(
                f"[COORDINATOR] P0 auto-chain gate triggered: "
                f"pending_intent={merged_slots.pending_intent!r} "
                f"(fresh_this_turn={regex_slots.pending_intent!r}), goods_no=None, "
                f"tire_size={merged_slots.tire_size!r}, tire_model={merged_slots.tire_model!r}, "
                f"session_id={request.session_id} → domains=[DISCOVERY, TRANSACTION]"
            )
            log_classifier_redirect(
                trace_id=request.tracing_id,
                rule="P0_auto_chain",
                classifier_domains=["discovery"],
                corrected_domains=["discovery", "transaction"],
                user_text=last_user_text,
                user_behavior=getattr(routing_result, "user_behavior", "") or "",
                slots={
                    "pending_intent": merged_slots.pending_intent,
                    "fresh_intent_this_turn": regex_slots.pending_intent,
                    "tire_size": merged_slots.tire_size,
                    "tire_model": merged_slots.tire_model,
                },
            )

        # P0b TRANSACTION → DISCOVERY+TRANSACTION redirect: when the classifier
        # picked [TRANSACTION] alone but the user actually provided product
        # name/model/size with no resolved goods_no, force Discovery to search
        # first. Transaction has NO search tool (per c_transaction_agent prompt
        # GOODS_NO RESOLUTION), so without this redirect the classifier mismatch
        # leads to either (a) a quickReply confirmation prompt asking the user
        # to click "상품 검색" — the ACT-FIRST anti-pattern — or (b) a fallback
        # "상품을 검색하겠습니다" line with the chain stopping because domains
        # has only one entry.
        #
        # Guard conditions (ALL must hold):
        #   1. Classifier chose exactly [TRANSACTION].
        #   2. `merged_slots.goods_no is None` — resolved goods_no doesn't need search.
        #   3. ANY product hint via ONE of:
        #        a. `merged_slots.tire_size` — size present (current or inherited).
        #        b. `merged_slots.tire_model` — LLM-confirmed model (current or inherited).
        #        c. Brand/model keyword in CURRENT turn text (미쉐린/다이나프로/Dynapro/...).
        #
        # Loosened from the historical "size AND (model OR keyword)" form: a
        # single hint suffices because Discovery's search_product_tool gracefully
        # handles partial inputs (size-only, brand-only, model-only) and the
        # downstream guard stops the chain when search returns 0/multiple
        # results, so over-redirecting is safe.
        #
        # Safety: same as P0 — coordinator verifies goods_no was resolved after
        # Discovery before running Transaction (search returning 0/multiple
        # results leaves goods_no=None and the chain stops).
        elif (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.TRANSACTION
            # P0b assumes the user intends to buy/order — Discovery resolves
            # goods_no first. Favorite-store queries ("내 단골매장 / 단골 가게 /
            # 자주 가는 매장 / 마이샵 / 단골점") are info-only Transaction calls
            # that have nothing to do with product selection. Skip the redirect
            # so the favorite-stores tool fires under the transaction profile.
            and not re.search(
                r"단골\s*매장|단골\s*가게|단골점|마이샵|자주\s*가는\s*매장",
                last_user_text,
            )
            # Narrow transaction profiles (store / order / coupon) are flows where
            # the user is NOT searching for a product. Lingering tire_size from
            # earlier turns must not coerce a discovery prefix; the matching narrow
            # profile already owns the right tools (store_preview, my_orders,
            # my_coupons). transaction_price_stock is intentionally NOT excluded
            # — that profile assumes a known goods_no, so goods_no=None still
            # warrants a Discovery search.
            and (
                routing_result is None
                or routing_result.agent_prompt_profile
                not in (
                    AgentPromptProfile.TRANSACTION_STORE,
                    AgentPromptProfile.TRANSACTION_ORDER,
                    AgentPromptProfile.TRANSACTION_COUPON,
                )
            )
            and (
                # Original case: no goods_no in slots + any product hint
                (
                    merged_slots.goods_no is None
                    and (
                        merged_slots.tire_size is not None
                        or merged_slots.tire_model is not None
                        or ConversationSlots.has_product_keyword(last_user_text)
                    )
                )
                # Fresh-product case: user mentioned brand keyword + fresh size in
                # CURRENT turn — treat any prior goods_no as stale (different product
                # from prior session activity). Without this, P0b would skip the
                # redirect and Transaction would emit a "정확한 상품을 선택해 주세요"
                # quickReply with no path forward.
                or (
                    ConversationSlots.has_product_keyword(last_user_text)
                    and regex_slots.tire_size is not None
                )
            )
        ):
            domains = [MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION]
            skip_decision = True
            logger.debug(
                f"[COORDINATOR] P0b TX→DISC+TX redirect: classifier=[TRANSACTION], "
                f"goods_no=None, tire_size={merged_slots.tire_size!r}, "
                f"tire_model={merged_slots.tire_model!r}, "
                f"has_product_keyword={ConversationSlots.has_product_keyword(last_user_text)}, "
                f"session_id={request.session_id} → domains=[DISCOVERY, TRANSACTION]"
            )
            log_classifier_redirect(
                trace_id=request.tracing_id,
                rule="P0b",
                classifier_domains=["transaction"],
                corrected_domains=["discovery", "transaction"],
                user_text=last_user_text,
                user_behavior=getattr(routing_result, "user_behavior", "") or "",
                slots={
                    "tire_size": merged_slots.tire_size,
                    "tire_model": merged_slots.tire_model,
                    "has_product_keyword": ConversationSlots.has_product_keyword(last_user_text),
                },
            )

        # P0d profile upgrade: classifier picked [TRANSACTION] + transaction_price_stock,
        # but the user is mid-order (pending_intent=order + goods_no resolved). The
        # narrow price_stock profile lacks order-flow CTA guidance — its Output Policy
        # ("Return the shortest useful Korean answer") emits a generic fallback chip
        # set ("1:1 문의하기 / 처음으로") after price+stock confirmation, dead-ending
        # the order continuation. Upgrade to FULL so the agent loads the full
        # transaction prompt incl. order-flow chips (주문하기 / 장바구니 / 매장 찾기).
        #
        # Narrow trigger so unrelated flows aren't disturbed:
        #   - domains must be EXACTLY [TRANSACTION] (multi-domain chains skip this)
        #   - profile must be transaction_price_stock (transaction_order /
        #     transaction_store / transaction_coupon already carry their own CTAs)
        #   - pending_intent must be "order" AND goods_no resolved (user has
        #     committed to a specific product in the buy flow)
        if (
            routing_result is not None
            and len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.TRANSACTION
            and routing_result.agent_prompt_profile == AgentPromptProfile.TRANSACTION_PRICE_STOCK
            and merged_slots.pending_intent == "order"
            and merged_slots.goods_no is not None
        ):
            logger.info(
                "[COORDINATOR] P0d profile upgrade: transaction_price_stock → full "
                f"(pending_intent=order, goods_no={merged_slots.goods_no!r}, "
                f"session_id={request.session_id})"
            )
            routing_result.agent_prompt_profile = AgentPromptProfile.FULL

        # P0e domain override: classifier picks [TRANSACTION] + transaction_coupon
        # for "5% (할인)쿠폰" policy info questions, but PR #169's HARD STOP
        # lives in e_support_agent prompt only. Without this gate the user
        # sees voucher card lookup (get_my_coupons_tool) instead of the
        # fixed-text policy response. Force redirect to SUPPORT + FULL profile
        # so e_support_agent's HARD STOP fires deterministically.
        #
        # Narrow trigger:
        #   - domains EXACTLY [TRANSACTION] (multi-domain chains skip)
        #   - profile transaction_coupon (other transaction profiles unrelated)
        #   - last_user_text matches 5% coupon positive regex
        #   - ownership / action keywords ABSENT (see module-level negative regex)
        if (
            routing_result is not None
            and len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.TRANSACTION
            and routing_result.agent_prompt_profile == AgentPromptProfile.TRANSACTION_COUPON
            and last_user_text
            and _FIVE_PERCENT_COUPON_POSITIVE_RE.search(last_user_text)
            and not _FIVE_PERCENT_COUPON_OWNERSHIP_OR_ACTION_RE.search(last_user_text)
        ):
            logger.info(
                "[COORDINATOR] P0e domain override: 5%% coupon policy → SUPPORT/full "
                f"(text={last_user_text[:80]!r}, session_id={request.session_id})"
            )
            domains[:] = [MultiAgentDomain.Domain.SUPPORT]
            routing_result.domains = [MultiAgentDomain.Domain.SUPPORT]
            routing_result.agent_prompt_profile = AgentPromptProfile.FULL

        # P0f domain narrowing: classifier picks multi-domain
        # ([transaction, support]) or speculative discovery for coupon
        # issue/inquiry questions ("쿠폰 어떻게 받아?", "쿠폰 받아줘"). The
        # c_transaction GLOBAL rule (agent.py:33-) is the single source of
        # truth for the canned response + chip, but speculative discovery /
        # support agents emit their own answer (e.g. "이벤트/기획전" chips)
        # overriding the FE payload (Langfuse trace `b14fdcf8...` verified).
        # Force single [TRANSACTION] so only c_transaction_agent runs.
        #
        # Narrow trigger:
        #   - profile transaction_coupon (P0e may have already redirected
        #     5% policy questions to SUPPORT/full — skipped here)
        #   - last_user_text matches coupon issue intent regex
        #   - domains is NOT already exactly [TRANSACTION] (no-op skip)
        if (
            routing_result is not None
            and routing_result.agent_prompt_profile == AgentPromptProfile.TRANSACTION_COUPON
            and last_user_text
            and _COUPON_ISSUE_INTENT_RE.search(last_user_text)
            and domains != [MultiAgentDomain.Domain.TRANSACTION]
        ):
            logger.info(
                "[COORDINATOR] P0f domain narrowing: coupon issue intent → "
                f"[TRANSACTION] (prev={[d.value for d in domains]}, "
                f"text={last_user_text[:80]!r}, session_id={request.session_id})"
            )
            domains[:] = [MultiAgentDomain.Domain.TRANSACTION]
            routing_result.domains = [MultiAgentDomain.Domain.TRANSACTION]

        # Publish the active goal_type to the request-scoped ContextVar consumed
        # by template_mapper. This lets _map_location / _map_product set
        # isBookingFlow=True when a downstream tool call (inventory / price /
        # order) must follow the user's card pick — without threading goal_type
        # through every signature in the agent → mapper chain.
        # ContextVar scoping: set once per request, FastAPI's request lifecycle
        # confines propagation; no manual reset needed.
        from services.tstation.template_mapper import (
            current_ev_suitability_comparison,
            current_goal_type,
            current_pending_intent,
            current_runflat_comparison,
            current_return_visit_store_flow,
        )
        current_goal_type.set(merged_slots.goal_type)
        current_pending_intent.set(merged_slots.pending_intent)
        current_runflat_comparison.set(bool(
            re.search(r"런\s*플랫|런플랫|run[-\s]?flat|runflat", last_user_text, re.IGNORECASE)
            and re.search(r"가격|차이|비싸|얼마|비용|추가|더\s*내", last_user_text, re.IGNORECASE)
        ))
        current_ev_suitability_comparison.set(bool(
            re.search(r"전기차|EV|electric|테슬라|모델\s*Y|모델Y", last_user_text, re.IGNORECASE)
            and re.search(r"전용|꼭|이유|껴|장착|써도|되나|되나요|일반\s*타이어|차이|비교|뭐가\s*달라", last_user_text, re.IGNORECASE)
        ))
        current_return_visit_store_flow.set(bool(
            re.search(r"매장\s*다시\s*이용하기|점\s*다시\s*이용하기", last_user_text)
        ))

        _t_prestream = time.perf_counter()
        logger.debug(
            f"[LATENCY] pre-stream — slots={(_t_slots - _t0)*1000:.0f}ms "
            f"classify={(_t_classify - _t_slots)*1000:.0f}ms "
            f"other={(_t_prestream - _t_classify)*1000:.0f}ms "
            f"total={(_t_prestream - _t0)*1000:.0f}ms"
        )

        # STREAM MODE
        # Post-classifier intercept: 비-타이어 방문 예약 (와이퍼/배터리/얼라인먼트/
        # 경정비 등) 흐름에서 사용자가 datepick 시간 슬롯을 클릭한 turn은 결정적
        # redirect 으로 처리한다. LLM 의 SERVICE RESERVATION REDIRECT 규칙
        # 우회로 인한 vague "필요한 정보를 이어서 입력해 주세요" + dead-end chip
        # 회귀를 차단. pending_intent=="reservation" + datepick 패턴 + 타이어
        # 컨텍스트 부재 — 세 조건 모두 만족 시에만 발동.
        if _is_service_reservation_redirect(
            last_user_text, merged_slots.pending_intent, messages
        ):
            redirect_payload = _build_service_reservation_redirect_payload(
                last_user_text, messages
            )
            logger.info(
                "[CHAT_V2] Service-reservation redirect intercept: store=%r shop_seq=%r user=%r",
                redirect_payload["store_name"],
                redirect_payload["shop_seq"],
                last_user_text[:40],
            )
            if request.stream:
                return StreamingResponse(
                    TStationChatServiceV2._stream_service_reservation_redirect(redirect_payload),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            return TStationChatResponse(content=redirect_payload["text"])

        if request.stream:
            return StreamingResponse(
                TStationChatServiceV2._stream_response_multi(
                    messages,
                    domains,
                    slot_context,
                    request.session_id,
                    tool_context,
                    user_id=request.user_id,
                    trace_id=request.tracing_id,
                    skip_decision=skip_decision,
                    slot_context_with_intent=slot_context_with_intent,
                    classify_future=speculative_classify_future,
                    routing_result=routing_result,
                    initial_slots=merged_slots,
                    parent_span=_parent_span,
                    parent_span_id=_parent_span_id,
                    request_started_at=_t0,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # NON STREAM MODE
        try:
            final_content = ""
            last_message_content = ""

            async for event_str in TStationChatServiceV2._stream_response_multi(
                messages,
                domains,
                slot_context,
                request.session_id,
                tool_context,
                user_id=request.user_id,
                trace_id=request.tracing_id,
                skip_decision=skip_decision,
                slot_context_with_intent=slot_context_with_intent,
                classify_future=speculative_classify_future,
                routing_result=routing_result,
                initial_slots=merged_slots,
                parent_span=_parent_span,
                parent_span_id=_parent_span_id,
                request_started_at=_t0,
            ):
                if event_str.startswith("data: "):
                    json_str = event_str[6:].strip()
                    if json_str and json_str != "[DONE]":
                        event = json.loads(json_str)

                        if event.get("type") == "token":
                            final_content += event.get("content", "")
                        elif event.get("type") == "message":
                            last_message_content = event.get("content", "")

            # FIX: Always prefer the final message event, because it contains the QC-corrected text!
            if last_message_content:
                final_content = last_message_content

            return TStationChatResponse(content=final_content)

        except ValueError as e:
            logger.warning(f"User Error: {e}")
            raise ValueError(e)
        except Exception as e:
            logger.exception(f"Server Error: {e}")
            raise Exception("Internal Server Error")

    @staticmethod
    def _stream_guardrail_response():
        """Stream a guardrail rejection response without invoking any agent."""
        yield f"data: {json.dumps({'type': 'token', 'content': GUARDRAIL_RESPONSE}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    @staticmethod
    def _stream_service_reservation_redirect(payload: dict):
        """Stream the deterministic SERVICE RESERVATION REDIRECT response.

        Emits token + message + data(quickReply) + sub-agent[DONE] + DONE,
        bypassing the multi-agent pipeline entirely. Used when a user clicks
        a datepick slot in a wiper/battery/alignment booking flow where the
        LLM has been observed to ignore the prompt-level redirect rule.
        """
        msg = payload["text"]
        chips = payload["chips"]
        yield f"data: {json.dumps({'type': 'token', 'content': msg}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'message', 'content': msg, 'agent': '[TRANSACTION AGENT]'}, ensure_ascii=False)}\n\n"
        data_event = {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": msg,
                "quickReplies": chips,
                "predictedDomains": ["TRANSACTION"],
            },
        }
        yield f"data: {json.dumps(data_event, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    @staticmethod
    def _stream_regional_cheapest_response():
        """Stream a canned response for '도/시/군/구 + 제일 저렴한 매장' queries."""
        msg = (
            "매장·시기·상품에 따라 적용되는 프로모션이 달라 '제일 저렴한 매장' 을 "
            "한 곳으로 안내드리기 어려워요 😊\n\n"
            "다만 **온라인 구매 시 무료배송 + 무료장착**이고, 원하시는 상품을 선택하시면 "
            "실시간 할인가를 바로 확인하실 수 있어요."
        )
        chips = [
            {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
            {"label": "가까운 매장 찾기", "domain": "TRANSACTION"},
            {"label": "진행 중인 이벤트", "domain": "DISCOVERY"},
        ]
        yield f"data: {json.dumps({'type': 'token', 'content': msg}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'message', 'content': msg, 'agent': '[LEADING AGENT]'}, ensure_ascii=False)}\n\n"
        data_event = {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": msg,
                "quickReplies": chips,
                "predictedDomains": ["DISCOVERY", "TRANSACTION"],
            },
        }
        yield f"data: {json.dumps(data_event, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


    @staticmethod
    async def _stream_response_multi(
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
        slot_context: str | None = None,
        session_id: str | None = None,
        tool_context: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span: Any | None = None,
        parent_span_id: str | None = None,
        skip_decision: bool = False,
        slot_context_with_intent: str | None = None,
        classify_future: concurrent.futures.Future | None = None,
        routing_result: MultiAgentDomain | None = None,
        initial_slots: Any | None = None,
        request_started_at: float | None = None,
    ):
        """Stream response from multi-agent coordinator with Strict QC Layer."""
        from config.env import settings as _s
        logger.debug(
            "[REQUEST_CONFIG] "
            f"default={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL} | "
            f"leading={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_LEADING_AGENT} | "
            f"transaction={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_TRANSACTION_AGENT} | "
            f"qc={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_QC_AGENT} | "
            f"qc_enabled={_s.AI_QC_ENABLED} | "
            f"session_id={session_id!r}"
        )

        _t_stream_start = time.perf_counter()
        _t_request_start = request_started_at or _t_stream_start
        draft_response = ""       # text only — used for history/message sync
        draft_for_qc = ""         # text + template payload — passed to QC only
        source_data_chunks = []
        # Parsed dicts paired with tool name — handed to the deterministic verifier
        # so it can scan all source values without re-parsing strings.
        structured_sources: list[tuple[str, dict]] = []
        buffered_data_events: list[dict] = []  # DATA events held until after QC
        tool_context_items = []  # Structured tool results for context preservation
        original_message_events = []  # Hold message events to sync history
        called_tool_names: set[str] = set()
        last_template: str | None = None
        last_template_source: str | None = None
        last_assistant_response_source: str | None = None
        coordinator_done_event = None  # Hold the premature [DONE] event
        agent_count = 0  # Track how many agents have started
        next_quick_reply_domain_values: list[str] = []
        next_predicted_domain_values: list[str] = []
        pending_slots = None
        # Hoisted so the trace summary at end-of-stream can reference QC verdict
        # even when the draft was empty and the QC block below never ran.
        _qc_passed = True

        # Detailed latency tracking state
        _lat_tool_start: dict[str, float] = {}
        _lat_agent_start: float | None = None
        _lat_agent_name: str = ""
        _lat_think_start: float | None = None       # reset each time "생각 중..." is seen
        _lat_pre_tool_think_start: float | None = None  # first "생각 중..." per agent
        _lat_first_token_seen: bool = False
        _lat_first_token_time: float | None = None
        _lat_prev_agent_done: float | None = None
        _lat_waiting_post_tool_output_since: float | None = None
        _lat_agent_pre_tool_think_ms = 0.0
        _lat_agent_post_tool_output_ms = 0.0
        _lat_agent_llm_generation_ms = 0.0
        _lat_tool_ms = 0.0
        _lat_decide_next_action_ms = 0.0
        _lat_qc_ms = 0.0
        _lat_first_visible_ms: float | None = None
        qc_skip_reason: str | None = None
        qc_executed = False

        def _mark_first_visible(now: float | None = None) -> None:
            nonlocal _lat_first_visible_ms
            if _lat_first_visible_ms is None:
                _lat_first_visible_ms = ((now or time.perf_counter()) - _t_request_start) * 1000
                logger.debug(f"[LATENCY] first_visible={_lat_first_visible_ms:.0f}ms")

        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # 1. Iterate through the main coordinator stream
        yield f"data: {json.dumps({'type': 'agent_flow', 'agent': '[응답 생성 중]', 'status': 'processing'}, ensure_ascii=False)}\n\n"
        # Track whether a code-mapper-eligible tool was called — if so, suppress token streaming
        # to avoid the "long text flashes then gets replaced by card" UX issue.
        from services.tstation.template_mapper import _TOOL_TEMPLATE_MAP

        _SUPPRESS_ON_TOOLS = frozenset(
            tool
            for tool, template in _TOOL_TEMPLATE_MAP.items()
            if template in {"product", "voucher", "cheapestProduct", "previewYoutube", "location", "datepick"}
        )
        _suppress_tokens = False

        speculative_guard = None
        if classify_future is not None:
            speculative_guard = {
                "confirm_event": threading.Event(),
                "mutating_tools": _SPECULATIVE_MUTATING_TOOLS,
            }

        coordinator_iter = _coordinator.stream(
            messages,
            domains=domains,
            slot_context=slot_context,
            session_id=session_id,
            tool_context=tool_context,
            user_id=user_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            skip_decision=skip_decision,
            slot_context_with_intent=slot_context_with_intent,
            classify_future=classify_future,
            speculative_guard=speculative_guard,
            routing_result=routing_result,
            initial_slots=initial_slots,
        )
        async for event in _async_from_sync_iter(coordinator_iter):
            _lat_now = time.perf_counter()
            event_type = event.get("type")

            # --- INTERCEPT TOKENS (Draft Response only — FE ignores `token` events
            # already and renders text from data.assistantResponse on the final
            # template, so streaming partial tokens to the client adds no UI value
            # and inflates SSE bandwidth. Keep accumulating into draft_response so
            # the local QC / sanitize step still has the full text). ---
            if event_type == "token":
                if event.get("content"):
                    if _lat_waiting_post_tool_output_since is not None:
                        _post_tool_ms = (_lat_now - _lat_waiting_post_tool_output_since) * 1000
                        _lat_agent_post_tool_output_ms += _post_tool_ms
                        logger.debug(f"[LATENCY]   llm_post_tool_output={_post_tool_ms:.0f}ms")
                        _lat_waiting_post_tool_output_since = None
                    if not _suppress_tokens:
                        draft_response += event["content"]
                        draft_for_qc += event["content"]
                    if not _lat_first_token_seen:
                        _lat_first_token_seen = True
                        _lat_first_token_time = _lat_now
                        if _lat_think_start is not None:
                            logger.debug(f"[LATENCY]   llm_think={(_lat_now - _lat_think_start)*1000:.0f}ms")
                continue

            # --- INTERCEPT MESSAGES (History Sync ONLY) ---
            if event_type == "message":
                original_message_events.append(event)
                continue

            # --- COLLECT SOURCE DATA (Tools Only = True Ground Truth) ---
            if event_type == "tool":
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                tool_name = event.get("tool", "Unknown")
                called_tool_names.add(tool_name)
                if tool_name in _lat_tool_start:
                    _tool_ms = (_lat_now - _lat_tool_start.pop(tool_name)) * 1000
                    _lat_tool_ms += _tool_ms
                    logger.debug(f"[LATENCY]   tool={tool_name} {_tool_ms:.0f}ms")
                _lat_waiting_post_tool_output_since = _lat_now
                # Suppress tokens when a "list display" tool is called (card will replace text).
                # Exclude car lookup tools — agent may need to show selection text first.
                if tool_name in _SUPPRESS_ON_TOOLS:
                    _suppress_tokens = True
                input_data = event.get("input", {})
                output_data = event.get("output", "")
                source_parts = []
                if input_data:
                    source_parts.append(f"Input: {json.dumps(input_data, ensure_ascii=False)}")
                if output_data:
                    filtered = filter_source_data(tool_name, output_data)
                    source_parts.append(f"Output: {filtered}")
                if source_parts:
                    source_data_chunks.append(f"Tool [{tool_name}]:\n" + "\n".join(source_parts))

                # Collect structured tool results for context preservation
                if output_data:
                    ctx_item = filter_for_context(tool_name, output_data, input_data)
                    if ctx_item:
                        tool_context_items.append(ctx_item)
                    parsed_for_verifier = qc_verifier.parse_tool_output(output_data)
                    if parsed_for_verifier is not None:
                        structured_sources.append((tool_name, parsed_for_verifier))

                continue

            if event_type == "internal_slots":
                pending_slots = event.get("slots")
                continue

            # --- INTERCEPT EARLY DONE EVENT ---
            if event_type == "sub-agent" and event.get("agent") == "[DONE]":
                coordinator_done_event = event
                continue

            # --- INTERCEPT DATA EVENTS (UI Template Agent) ---
            if event_type == "data":
                if _lat_waiting_post_tool_output_since is not None:
                    _post_tool_ms = (_lat_now - _lat_waiting_post_tool_output_since) * 1000
                    _lat_agent_post_tool_output_ms += _post_tool_ms
                    logger.debug(f"[LATENCY]   post_tool_data_event={_post_tool_ms:.0f}ms")
                    _lat_waiting_post_tool_output_since = None
                last_template = event.get("template") or last_template
                event_template_source = event.pop("template_source", None)
                if isinstance(event_template_source, str):
                    last_template_source = event_template_source
                event_response_source = event.pop("assistant_response_source", None)
                if isinstance(event_response_source, str):
                    last_assistant_response_source = event_response_source
                event_data = event.get("data", {})
                coerced_event = _coerce_reservation_quickreply_to_datepick(
                    event,
                    structured_sources,
                    pending_slots or initial_slots,
                )
                if coerced_event is not None:
                    logger.warning(
                        "[TEMPLATE_COERCE] transaction_store_preview quickReply time chips → datepick"
                    )
                    event = coerced_event
                    last_template = "datepick"
                    last_template_source = "code_mapper"
                    last_assistant_response_source = "code_mapper_preview_quickreply"
                    event_data = event.get("data", {})
                coerced_event = _coerce_non_selection_listcar_to_quickreply(event)
                if coerced_event is not None:
                    logger.warning(
                        "[TEMPLATE_COERCE] discovery listCar advice turn → quickReply"
                    )
                    event = coerced_event
                    last_template = "quickReply"
                    last_template_source = "code_mapper"
                    last_assistant_response_source = "code_mapper_listcar_advice_guard"
                    event_data = event.get("data", {})
                for value in _quick_reply_domain_values_from_event(event):
                    if value not in next_quick_reply_domain_values:
                        next_quick_reply_domain_values.append(value)
                for value in _predicted_domain_values_from_event(event):
                    if value not in next_predicted_domain_values:
                        next_predicted_domain_values.append(value)
                if isinstance(event_data, dict):
                    if event_data.get("assistantResponse"):
                        assistant_response = _sanitize_response(event_data["assistantResponse"])
                        event_data["assistantResponse"] = assistant_response
                        if _suppress_tokens:
                            draft_response = assistant_response
                            draft_for_qc = assistant_response
                        source_domain = str(event.get("source_domain", "ui_template")).upper()
                        assistant_msg_event = {
                            "type": "message",
                            "content": assistant_response,
                            "agent": f"[{source_domain} AGENT]",
                        }
                        original_message_events.append(assistant_msg_event)
                        logger.debug(
                            f"[COORDINATOR] Captured assistantResponse from data event ({source_domain}): {assistant_response[:50]}..."
                        )
                    # For Path B templates only — LLM wrote the JSON so QC must verify it.
                    # Path A templates (code mapper) are correct by construction; including their
                    # JSON confuses QC into unnecessary text rewrites.
                    if last_template in _LLM_WRITTEN_TEMPLATES:
                        template_payload = {k: v for k, v in event_data.items() if k != "assistantResponse"}
                        if template_payload:
                            draft_for_qc += f"\n\n[Template: {last_template}]\n{json.dumps(template_payload, ensure_ascii=False)}"
                # Inject quickReplies into orderComplete (LLM-written path; mapper path injects via _map_order_complete).
                if last_template == "orderComplete" and isinstance(event_data, dict) and "quickReplies" not in event_data:
                    if event_data.get("isSuccess"):
                        event_data["quickReplies"] = [
                            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
                            {"label": "배송 상태 확인", "domain": "TRANSACTION"},
                        ]
                    else:
                        event_data["quickReplies"] = [
                            {"label": "다시 시도", "domain": "TRANSACTION"},
                        ]
                # Defensive fallback for quickReply template: if LLM emitted empty quickReplies,
                # inject context-aware chips so the user is never stranded. Skip when the turn
                # is an auto-chained handoff (nextAction.type == "continue") because the
                # coordinator runs the next agent in the same turn and chips would be noise.
                # Chip set is selected from called_tool_names so the fallback matches the
                # conversation context (e.g., order list → order-related chips, not a generic
                # "1:1 문의" pair which makes the order flow look broken).
                if last_template == "quickReply" and isinstance(event_data, dict):
                    existing_chips = event_data.get("quickReplies")
                    chips_empty = not isinstance(existing_chips, list) or len(existing_chips) == 0
                    next_action = event.get("nextAction") or {}
                    is_handoff = isinstance(next_action, dict) and next_action.get("type") == "continue"
                    if chips_empty and not is_handoff:
                        fallback_chips, fallback_label = _choose_quickreply_fallback(
                            called_tool_names, source_domain
                        )
                        logger.warning(
                            "[QUICKREPLY_FALLBACK] empty quickReplies (domain=%s tools=%s) → %s",
                            source_domain,
                            sorted(called_tool_names),
                            fallback_label,
                        )
                        event_data["quickReplies"] = fallback_chips
                    if (
                        not is_handoff
                        and _looks_like_generic_dead_end_chips(event_data.get("quickReplies"))
                    ):
                        recovery = _discovery_recovery_chips_for_text(
                            str(event_data.get("assistantResponse") or ""),
                            source_domain,
                        )
                        if recovery is not None:
                            recovery_chips, recovery_label = recovery
                            logger.warning(
                                "[QUICKREPLY_FALLBACK] replacing discovery dead-end chips "
                                "(domain=%s tools=%s) → %s",
                                source_domain,
                                sorted(called_tool_names),
                                recovery_label,
                            )
                            event_data["quickReplies"] = recovery_chips
                            event_data["predictedDomains"] = _dedupe_domain_values([
                                str(chip.get("domain", ""))
                                for chip in recovery_chips
                                if isinstance(chip, dict)
                            ])
                if isinstance(event_data, dict) and _remove_home_quick_reply_chips(event_data):
                    logger.info(
                        "[QUICKREPLY_FILTER] removed home chip from %s template",
                        last_template,
                    )
                # Buffer data event — yield after QC so assistantResponse is always verified
                buffered_data_events.append(event)
                continue

            # --- RESET DRAFT when a new sub-agent starts (multi-agent chaining) ---
            # The second agent receives the first agent's context and produces a unified response,
            # so we only need the last agent's output for QC.
            if event_type == "sub-agent" and event.get("agent", "") != "[UI TEMPLATE AGENT]":
                _sub_status = event.get("status")
                _sub_agent = event.get("agent", "?")
                if _sub_status == "start":
                    if _lat_prev_agent_done is not None:
                        _decision_ms = (_lat_now - _lat_prev_agent_done) * 1000
                        _lat_decide_next_action_ms += _decision_ms
                        logger.debug(f"[LATENCY] decide_next_action={_decision_ms:.0f}ms")
                    _lat_agent_start = _lat_now
                    _lat_agent_name = _sub_agent
                    _lat_think_start = None
                    _lat_pre_tool_think_start = None
                    _lat_first_token_seen = False
                    _lat_first_token_time = None
                    _lat_waiting_post_tool_output_since = None
                    agent_count += 1
                    if agent_count > 1 and draft_response.strip():
                        logger.debug(
                            f"[QC_LAYER] Resetting draft_response for agent #{agent_count} — last agent should produce unified response"
                        )
                        draft_response = ""
                        draft_for_qc = ""
                        original_message_events = []
                        buffered_data_events = []
                        last_template_source = None
                        last_assistant_response_source = None
                elif _sub_status == "done" and _lat_agent_start is not None:
                    _llm_gen = (_lat_now - _lat_first_token_time) * 1000 if _lat_first_token_time else 0
                    _lat_agent_llm_generation_ms += _llm_gen
                    if _lat_waiting_post_tool_output_since is not None:
                        _post_tool_ms = (_lat_now - _lat_waiting_post_tool_output_since) * 1000
                        _lat_agent_post_tool_output_ms += _post_tool_ms
                        logger.debug(f"[LATENCY]   post_tool_done={_post_tool_ms:.0f}ms")
                        _lat_waiting_post_tool_output_since = None
                    logger.debug(
                        f"[LATENCY] agent={_lat_agent_name} total={(_lat_now - _lat_agent_start)*1000:.0f}ms "
                        f"llm_gen={_llm_gen:.0f}ms"
                    )
                    _lat_prev_agent_done = _lat_now

            # Track tool_start and LLM think timing from status events
            if event_type == "status":
                _status_val = event.get("status", "")
                if _status_val == "tool_start":
                    if _lat_pre_tool_think_start is not None:
                        _pre_tool_ms = (_lat_now - _lat_pre_tool_think_start) * 1000
                        _lat_agent_pre_tool_think_ms += _pre_tool_ms
                        logger.debug(f"[LATENCY]   llm_pre_tool_think={_pre_tool_ms:.0f}ms")
                        _lat_pre_tool_think_start = None
                    _lat_tool_start[event.get("tool", "?")] = _lat_now
                elif _status_val == "생각 중...":
                    if _lat_pre_tool_think_start is None:
                        _lat_pre_tool_think_start = _lat_now
                    _lat_think_start = _lat_now
                    _lat_first_token_seen = False

            # Pass all other events (UI templates, agent flows) through
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        _t_agents = time.perf_counter()

        # 2. QC VERIFIER (deterministic)
        # Gated by AI_QC_ENABLED. Scans the draft for prices, goods_no, and
        # shop_id literals and checks them against the raw tool outputs
        # collected this turn. Pass-through policy: mismatches are logged and
        # surfaced in the Langfuse trace, but the draft is NEVER rewritten —
        # the verifier has no safe replacement value, and rewriting was the
        # source of the prior LLM QC's false-positive problem.
        if draft_response.strip():
            draft_response = _sanitize_response(draft_response)

            _qc_passed = True
            _parallel_qc = _s.AI_QC_ENABLED and _s.AI_QC_PARALLEL

            # PARALLEL MODE: yield data events immediately so FE renders without waiting for QC.
            if _parallel_qc:
                for buffered_evt in buffered_data_events:
                    _mark_first_visible()
                    yield f"data: {json.dumps(buffered_evt, ensure_ascii=False)}\n\n"

            if _s.AI_QC_ENABLED:
                _qc_started_at = time.perf_counter()
                qc_skip_reason = _qc_skip_reason(
                    called_tool_names,
                    last_template,
                    last_template_source,
                    last_assistant_response_source,
                )

                if called_tool_names and qc_skip_reason is None:
                    qc_executed = True
                    try:
                        with _trace_span(
                            "qc",
                            trace_id=trace_id,
                            parent_span_id=parent_span_id,
                            input={
                                "user_query": user_query,
                                "draft": draft_for_qc,
                                "source_tool_count": len(structured_sources),
                            },
                        ) as _qc_span:
                            mismatches = qc_verifier.verify_draft(draft_for_qc, structured_sources)
                            _qc_passed = not mismatches
                            if _qc_passed:
                                logger.debug("[QC_VERIFIER] PASS")
                                _qc_summary = "PASS"
                            else:
                                logger.warning(
                                    "[QC_VERIFIER] %d mismatch(es) in draft: %s",
                                    len(mismatches),
                                    [m.as_dict() for m in mismatches],
                                )
                                _qc_summary = f"MISMATCH ({len(mismatches)})"
                            _qc_span.update(
                                output=_truncate({
                                    "summary": _qc_summary,
                                    "verdict": "PASS" if _qc_passed else "MISMATCH",
                                    "mismatches": [m.as_dict() for m in mismatches],
                                }),
                            )
                    except Exception as e:
                        logger.warning(f"[QC_VERIFIER] Verifier failed, using original draft: {e}")
                elif called_tool_names:
                    logger.debug(
                        "[QC_VERIFIER] Skipped QC: reason=%s template=%s source=%s response_source=%s tools=%s",
                        qc_skip_reason,
                        last_template,
                        last_template_source,
                        last_assistant_response_source,
                        sorted(called_tool_names),
                    )
                _lat_qc_ms = (time.perf_counter() - _qc_started_at) * 1000

            if not _parallel_qc:
                # SEQUENTIAL (default): data events were buffered; yield them as-is now.
                # Verifier never rewrites the draft, so no patching is needed.
                for buffered_evt in buffered_data_events:
                    _mark_first_visible()
                    yield f"data: {json.dumps(buffered_evt, ensure_ascii=False)}\n\n"

            if original_message_events:
                final_msg_event = original_message_events[-1]
                final_msg_event["content"] = draft_response
                _mark_first_visible()
                yield f"data: {json.dumps(final_msg_event, ensure_ascii=False)}\n\n"
        else:
            # FALLBACK HISTORY SYNC: If no text was generated, only yield message events
            # if they actually contain text. We DO NOT want to save empty assistant
            # messages to Redis, as it pollutes the LLM's future context window.
            for msg_event in original_message_events:
                if msg_event.get("content", "").strip():  # <-- ONLY yield if it has text
                    _mark_first_visible()
                    yield f"data: {json.dumps(msg_event, ensure_ascii=False)}\n\n"

        # 4. PERSIST NEXT-TURN CONTEXT
        if session_id and (
            tool_context_items
            or next_quick_reply_domain_values
            or next_predicted_domain_values
            or pending_slots is not None
        ):
            try:
                from services.tstation.chat_history_service import get_chat_history_service

                history_svc = get_chat_history_service()

                await history_svc.finalize_chat_context_async(
                    session_id=session_id,
                    tool_data=tool_context_items,
                    quick_reply_domains=next_quick_reply_domain_values,
                    predicted_domains=next_predicted_domain_values,
                    user_id=user_id,
                )
                if pending_slots is not None:
                    await history_svc.save_slots_async(session_id, pending_slots, user_id=user_id)
            except Exception as e:
                logger.warning(f"[STREAM_CTX] Failed to save stream context: {e}")

        _t_qc = time.perf_counter()
        _lat_stream_total_ms = (_t_qc - _t_request_start) * 1000
        logger.debug(
            f"[LATENCY] stream — agents={(_t_agents - _t_stream_start)*1000:.0f}ms "
            f"first_visible={_lat_first_visible_ms or 0:.0f}ms "
            f"pre_tool_think={_lat_agent_pre_tool_think_ms:.0f}ms "
            f"post_tool_output={_lat_agent_post_tool_output_ms:.0f}ms "
            f"llm_gen={_lat_agent_llm_generation_ms:.0f}ms "
            f"tools={_lat_tool_ms:.0f}ms "
            f"decision={_lat_decide_next_action_ms:.0f}ms "
            f"qc={_lat_qc_ms:.0f}ms "
            f"stream_total={_lat_stream_total_ms:.0f}ms"
        )

        if parent_span is not None:
            # The augmented user message has a CONVERSATION CONTEXT prefix and
            # a [current_time: ...] suffix injected upstream. Strip them so the
            # trace name reflects what the user actually typed (e.g.
            # "벤투스 S2 AS 225/55R17") instead of the augmentation header.
            _last_user_raw = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
            )
            _last_user = StreamingMultiAgentCoordinator._extract_current_user_input(_last_user_raw) or _last_user_raw
            # Trace `output` carries the actual assistant response so the Langfuse
            # trace list shows what the user saw. Routing / tool / template / QC
            # metadata moves to `metadata` (and the `qc` child span already holds
            # the verdict + result for drill-down).
            _route = "→".join(d.value for d in domains) if domains else ""
            _trace_metadata = {
                "route": _route,
                "tools": sorted(called_tool_names),
                "template": last_template,
                "template_source": last_template_source,
                "template_qc_policy": _TEMPLATE_QC_POLICY.get(last_template or ""),
                "assistant_response_source": last_assistant_response_source,
                "qc": "PASS" if _qc_passed else "CORRECTED",
                "qc_executed": qc_executed,
                "qc_skip_reason": qc_skip_reason,
                "latency_ms": int(_lat_stream_total_ms),
                "latency_first_visible_ms": (
                    round(_lat_first_visible_ms) if _lat_first_visible_ms is not None else None
                ),
                "latency_stream_total_ms": round(_lat_stream_total_ms),
                "latency_agent_pre_tool_think_ms": round(_lat_agent_pre_tool_think_ms),
                "latency_agent_post_tool_output_ms": round(_lat_agent_post_tool_output_ms),
                "latency_agent_llm_generation_ms": round(_lat_agent_llm_generation_ms),
                "latency_qc_ms": round(_lat_qc_ms),
            }
            _trace_output = _truncate(draft_response)
            _trace_input = _truncate(_last_user)
            # Set both the parent span's own output AND the trace-level output.
            parent_span.update(output=_trace_output)
            parent_span.update_trace(
                name=(_last_user[:60] if _last_user else "chat"),
                input=_trace_input,
                output=_trace_output,
                metadata=_trace_metadata,
            )
            # Create a final "✅ response" observation that carries the
            # user-visible answer as its I/O. Langfuse v3 trace overview falls
            # back to displaying the latest child chain's I/O (e.g. QC chain
            # returning "PASS", or the agent chain dumping the message
            # history) when no other signal wins. By making this the very last
            # observation in the trace with input=user-message and output=
            # assistant-response, the trace overview reads what the user
            # actually saw — regardless of which child chains ran earlier.
            if trace_id and _tracing_enabled:
                try:
                    # Name the final span with the user's question — Langfuse v3
                    # also derives trace.name from the latest observation, so a
                    # generic "response" name would override the user-message
                    # trace name we set on the parent span.
                    _response_span_name = (_last_user[:60] if _last_user else "response")
                    response_span = tracer.start_span(
                        name=_response_span_name,
                        trace_context={"trace_id": trace_id, "parent_span_id": parent_span_id},
                        input=_trace_input,
                    )
                    response_span.update(output=_trace_output)
                    response_span.update_trace(
                        name=_response_span_name,
                        input=_trace_input,
                        output=_trace_output,
                    )
                    response_span.end()
                except Exception as exc:
                    logger.debug("[TRACE] response span failed: %s", exc)
            logger.debug(
                "[TRACE] Sealed trace output (%d chars) route=%s qc=%s recording=%s",
                len(draft_response),
                _route or "?",
                "PASS" if _qc_passed else "CORRECTED",
                getattr(getattr(parent_span, "_otel_span", None), "is_recording", lambda: "?")(),
            )
            parent_span.end()
            # Force immediate OTel batch export so the trace.output update we just
            # set is visible in Langfuse UI without waiting for the next periodic
            # flush.
            try:
                tracer.flush()
            except Exception as exc:
                logger.debug("[TRACE] flush failed: %s", exc)

        # 5. FINALIZE THE STREAM
        if coordinator_done_event:
            yield f"data: {json.dumps(coordinator_done_event, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
