import concurrent.futures
import json
import logging
import re
import time
from typing import ClassVar, Iterator, Optional
from textwrap import dedent

from pydantic import BaseModel, Field
from enum import Enum

from services.tstation.common.tstation_be_client import set_tstation_be_token
from config.env import settings
from fastapi.responses import StreamingResponse
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.router import (
    AgentDomain,
    DECISION_LLM as _decision_llm,
    leading_agent,
    discovery_subagent,
    transaction_subagent,
    support_subagent,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time
from services.tstation.common.pii_guardrail import check_pii, GUARDRAIL_RESPONSE

from services.tstation.agents.g_qc_agent.source_filter import filter_source_data, filter_for_context
from services.tstation.agents.g_qc_agent.agent import ainvoke_qc
from services.tstation.agents.router import QC_LLM
import anyio.from_thread as _anyio_ft

logger = logging.getLogger(__name__)


class NextAction(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


class AgentDecision(BaseModel):
    next_action: NextAction = Field(description="STOP or CONTINUE")
    next_domain: str = Field(description="Next domain if CONTINUE ('null' if STOP)")
    reason: str = Field(description="Reason for decision, using english")


# Module-level singleton: avoid re-creating LLM client + structured-output wrapper per request.
_decision_structured_model = _decision_llm.with_structured_output(AgentDecision)


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
    from config.tracing import build_trace_config

    structured_model = _decision_structured_model

    user_message = ""
    for msg in reversed(original_messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    system_msg = SystemMessage(content=prompt_router())
    human_msg = HumanMessage(
        content=dedent(f"""
        Original User Request: {user_message}

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
    )

    try:
        result: AgentDecision = structured_model.invoke([system_msg, human_msg], config=trace_config)
        return result
    except Exception as e:
        logger.warning(f"[DECISION] LLM decision failed: {e}")
        # Fallback: stop if cannot decide
        return AgentDecision(
            next_action=NextAction.STOP,
            next_domain=None,
            reason=f"Decision failed: {str(e)[:100]}",
        )


class RouterEntities(BaseModel):
    """Entities extracted by the router LLM from the user's current message.

    Slim schema: only fields directly consumed by Discovery agent intent
    guards or with high routing signal. Agents requiring other fields
    (brand, goods_no, store_keyword, owner_nm, quantity) re-extract from
    the user message text — they're not worth the per-request output
    tokens here.

    All fields are declared without Pydantic defaults so they end up in
    the JSON schema's `required` array (OpenAI's strict structured output
    requirement). The LLM must explicitly emit `null` / `false` when a
    field does not apply.
    """

    vehicle_mention: str | None = Field(
        description="Car model name mentioned (e.g., '제타', 'GV70', 'K7'). Use null if absent.",
    )
    vehicle_possessive: bool = Field(
        description="True only when the user references the car as their own ('내', '내 차', '등록차', 'my car'). False if just a model name with no ownership marker, or no vehicle mentioned.",
    )
    vehicle_number: str | None = Field(
        description="Korean license plate when present (e.g., '12가3456'). Use null if absent.",
    )
    tire_size: str | None = Field(
        description="Normalized tire size (e.g., '225/45R17'). Use null if absent.",
    )
    tire_attribute: str | None = Field(
        description="Tire-type attribute mentioned (e.g., '전기차용', '사계절', '런플랫', '광폭', '스노우'). Use null if absent.",
    )
    product_name: str | None = Field(
        description="Product/model name (e.g., '벤투스 S2', 'Dynapro HPX', '키너지 GT'). Use null if absent.",
    )
    scenario: str | None = Field(
        description="Scenario keyword (e.g., '빗길', '눈길', '사계절', '주말', '가족', '전기차', '고속'). Use null if absent.",
    )
    question_form: str | None = Field(
        description=(
            "Form of the user's request — pick ONE of: "
            "'yes_no' (yes/no question like '껴도 돼?', '맞아?', '써도 돼?'), "
            "'info_request' (asking for information / explanation, e.g. '공기압 얼마?'), "
            "'action_request' (wants the agent to do something / produce a list, e.g. '추천해줘'), "
            "'selection' (picking from a previously shown list — bare item name, ordinal, plate number), "
            "'confirmation' (yes/ok/맞아 confirming a previous prompt). "
            "Use null if none applies."
        ),
    )


class MultiAgentDomain(BaseModel):
    """Router result that supports multiple domains (multi-intent)."""

    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        TRANSACTION = "transaction"
        SUPPORT = "support"

    class Intent(str, Enum):
        # Slim taxonomy (20 values). Removed values that rarely fire or
        # collapse cleanly to a remaining one — kept by the agent's own
        # internal classification (Transaction / Support agents).
        #   cart → ORDER, reservation/order_tracking/order_history → OTHER,
        #   warranty/escalation → FAQ, unclear → OTHER.
        # ---- Discovery domain (full taxonomy — used by guards) ----
        RECOMMEND = "recommend"  # "추천해줘", "맞는 타이어 알려줘"
        COMPATIBILITY = "compatibility"  # "X 타이어 껴도 돼?", "맞아?", yes/no fit question
        INFO_QUESTION = "info_question"  # "언제 갈아야?", "공기압 얼마?", general knowledge q
        PRODUCT_SEARCH = "product_search"  # 상품명/모델명 검색 (벤투스 S2, Dynapro HPX...)
        VEHICLE_LOOKUP = "vehicle_lookup"  # "내 차 목록 보여줘"
        COMPARE = "compare"  # "최저가", "가격 비교", compare_discount
        EVENT_INQUIRY = "event_inquiry"  # 이벤트, 기획전
        VIDEO_INQUIRY = "video_inquiry"  # 영상, 리뷰 영상, YouTube
        # ---- Transaction domain (high-signal subset) ----
        PRICE = "price"  # goods_no 가격 조회
        STOCK = "stock"  # 재고 / 물류 / 매장 재고
        ORDER = "order"  # 주문 / 장바구니 / 결제
        STORE_SEARCH = "store_search"  # 매장 위치/이름 검색 / 예약 매장 찾기
        COUPON = "coupon"  # 쿠폰 조회
        # ---- Support domain (high-signal subset) ----
        FAQ = "faq"  # 보증·정책·일반 안내·반품 정책 문의
        RETURN = "return"  # 환불/반품 액션 요청
        COMPLAINT = "complaint"  # 불만/짜증/엉망 + 1:1 상담원 연결 요청
        # ---- Leading domain ----
        GREETING = "greeting"  # 인사
        # ---- Cross-domain ----
        SELECTION = "selection"  # 이전 턴에서 보여준 목록에서 선택 (continuation)
        CONFIRMATION = "confirmation"  # "네", "맞아", 직전 질문에 대한 확인
        OTHER = "other"  # 위 어디에도 안 맞는 경우 (unclear, 추적, 예약 등 포함)

    reason: str = Field(description="Reason for the classification, using english")
    domains: list[Domain] = Field(description="List of domains detected in the request, ordered by priority")
    intent: Intent = Field(
        description=(
            "PRIMARY intent of the user's CURRENT message. Choose the single best match. "
            "Decoupled from `domains`: e.g., a yes/no compatibility question 'X 타이어 껴도 돼?' "
            "→ domain=DISCOVERY but intent=COMPATIBILITY (not RECOMMEND). "
            "Use SELECTION when the user is just picking an item from a list shown in a previous turn "
            "(bare product/store name, ordinal, plate number) without a new action verb. "
            "Use CONFIRMATION for short yes/ok answers to a prior agent question."
        ),
    )
    entities: RouterEntities = Field(
        description="Structured entities extracted from the current message. Populate fields that apply; pass null/false for the rest. ALL keys must be present (OpenAI strict structured output requirement).",
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

    intent / entities ARE populated even on the first turn — they are the
    primary routing signal that future agent refactors will consume.
    """

    reason: str = Field(description="Reason for the classification, using english")
    domains: list[MultiAgentDomain.Domain] = Field(
        description="List of domains detected in the request, ordered by priority"
    )
    intent: MultiAgentDomain.Intent = Field(
        description=(
            "PRIMARY intent of the user's first message. See MultiAgentDomain.Intent for the full list. "
            "yes/no compatibility question ('X 타이어 껴도 돼?') → COMPATIBILITY (not RECOMMEND)."
        ),
    )
    entities: RouterEntities = Field(
        description="Structured entities extracted from the first message. ALL keys must be present (use null/false for fields that don't apply).",
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

====================================================
RULE 0 — HARDCODED KEYWORD ROUTING (HIGHEST PRECEDENCE — CHECK FIRST)
====================================================

Before applying any other rule, scan the user's CURRENT message text for these keywords. When matched, the listed (domain, intent) is final — IGNORE conversation history, IGNORE the recent slot context, IGNORE CONTINUATION DETECTION, IGNORE RE-RECOMMENDATION rules. The classification is determined by the keyword alone.

| Keyword in current user message            | domains            | intent          |
|---------------------------------------------|--------------------|-----------------|
| 이벤트, 이벤트 목록, 진행 중인 이벤트         | [DISCOVERY]        | event_inquiry   |
| 기획전, 기획전 목록, 기획전 보여줘, 기획전 내용 | [DISCOVERY]        | event_inquiry   |
| 영상, 리뷰 영상, 유튜브, 동영상               | [DISCOVERY]        | video_inquiry   |
| 내 차 목록, 등록차 보여줘, 내 등록차, 내 차량 | [DISCOVERY]        | vehicle_lookup  |
| 내 쿠폰, 받을 수 있는 쿠폰, 쿠폰함, 쿠폰 조회 | [TRANSACTION]      | coupon          |
| 내 주문내역, 주문 내역, 주문 조회             | [TRANSACTION]      | other           |
| 환불, 반품, 교환, 보증, 워런티               | [SUPPORT]          | (return / faq)  |
| 1:1 문의, 상담원 연결                        | [SUPPORT]          | faq             |

⚠️ This rule beats EVERYTHING below. A user who just finished cart-save / order-confirmation / store-selection and types "이벤트 목록" is NOT continuing the cart flow — the keyword "이벤트 목록" alone forces (DISCOVERY, event_inquiry). The slot context block (`[목표: 주문 진행]`, `[확인된 고객 정보]`) injected into the system prompt MUST NOT influence this classification. Set `user_behavior` to reflect the topic shift (e.g., "user shifted topic to 이벤트 inquiry from prior order flow").

⚠️ The keyword list is exact-substring. Case-insensitive. Whitespace-tolerant. If the user's CURRENT message contains the keyword anywhere in the text, the rule fires.

⚠️ The rule does NOT fire for ambiguous short messages with no keyword (bare ordinals "1번", bare yes "네", bare product names "벤투스 S2") — those follow CONTINUATION DETECTION later in this prompt.

If RULE 0 does NOT match, proceed with the rules below.

Produce 6 outputs:
1. domains — ONE OR MORE domains based on detected intents (ordered by priority)
2. intent — PRIMARY intent of the current message (see INTENT TAXONOMY below)
3. entities — structured fields extracted from the current message (see ENTITY EXTRACTION below)
4. reason — why you chose these domains/intent
5. user_behavior — what the user is currently doing based on the full conversation (e.g. "selecting car from list shown in previous turn", "providing tire size", "confirming product")
6. flow — one-line summary of the journey so far (e.g. "user requested tires → agent showed 2 cars → user selecting")

====================================================
INTENT TAXONOMY (always pick exactly ONE — 20 values)
====================================================

DISCOVERY domain intents (full taxonomy — used by Discovery agent guards):
- recommend         — user wants tire recommendations ("추천해줘", "맞는 타이어 알려줘")
- compatibility     — yes/no compatibility question ("X 타이어 껴도 돼?", "맞아?", "써도 돼?", "장착 돼?")
                      Pattern: tire-attribute or tire-size + yes/no question form. The user wants a fit/feasibility verdict, NOT a list.
- info_question     — general knowledge / explanation question ("타이어 언제 갈아야?", "공기압 얼마?", "마모 한계?")
                      Pattern: educational / advisory question, not a recommendation request.
- product_search    — user mentions a specific product/model name and wants info on it ("벤투스 S2", "Dynapro HPX 가격")
- vehicle_lookup    — user wants to see their registered vehicles ("내 차 목록", "내 등록차량 보여줘")
- compare           — user wants comparison / cheapest among candidates ("최저가", "가격 비교", "이 중에 제일 싼 거")
- event_inquiry     — events / 기획전 ("이벤트 알려줘", "기획전")
- video_inquiry     — video reviews / YouTube ("리뷰 영상", "유튜브")

TRANSACTION domain intents (high-signal subset — Transaction agent re-classifies internally):
- price             — price query when goods_no is already known
- stock             — inventory / logistics / store stock check
- order             — create order / cart save / checkout ("주문할게", "장바구니에 담아줘")
- store_search      — store search by location / name / reservation ("강남 매장", "올마이티", "한남점 예약")
- coupon            — coupon inquiry ("내 쿠폰", "받을 수 있는 쿠폰", "쿠폰함")

SUPPORT domain intents (high-signal subset — Support agent re-classifies internally):
- faq               — general FAQ / warranty / 보증 / 정책 정보 / 1:1 문의 작성 / 상담원 연결
- return            — returns / refunds / 반품 / 환불 (action request)
- complaint         — frustration / anger ("짜증나", "엉망이야", "뭐 이런 서비스가")

LEADING domain intents:
- greeting          — pure greeting ("안녕하세요", "hi")

Cross-domain intents (override the domain-specific intents above when applicable):
- selection         — user is picking an item from a list shown in the IMMEDIATELY previous turn
                      (bare product name like "벤투스 S2", ordinal like "1번", "첫번째", license plate like "12가3456",
                      store name like "한남점", date/time like "내일 10시"). The current message contains
                      no new action verb — just an identifier matching the previous list.
                      ⚠️ Use this intent regardless of the resolved domain.
- confirmation      — short yes/ok answer to the agent's previous question ("네", "맞아", "ok", "응")
- other             — fallback for cases that don't fit cleanly above (order tracking, order history, reservation date selection, unclear intent, bare re-trigger, general capability question, etc.)

⚠️ INTENT vs DOMAIN — they are decoupled axes. Examples:
- "내 제타에 전기차용 타이어 껴도 돼?"     → domain=DISCOVERY, intent=compatibility   (NOT recommend; it's a yes/no fit question)
- "내 그랜저 공기압 얼마가 적정?"          → domain=DISCOVERY, intent=info_question   (NOT recommend; it's a knowledge question)
- "내 K7 타이어 언제 갈아야 돼?"           → domain=DISCOVERY, intent=info_question
- "내 GV70에 맞는 타이어 추천해줘"          → domain=DISCOVERY, intent=recommend
- "벤투스 S2 가격 얼마야?"                  → domain=DISCOVERY, intent=product_search (goods_no not yet known)
- "G012345678901 가격"                       → domain=TRANSACTION, intent=price
- "내 쿠폰 보여줘"                           → domain=TRANSACTION, intent=coupon
- (prev turn showed car list) "제타"        → domain=DISCOVERY, intent=selection      (continuation)
- (prev turn asked confirmation) "네"       → domain=(prev domain), intent=confirmation

====================================================
ENTITY EXTRACTION (8 fields)
====================================================

Populate `entities` with whatever applies in the CURRENT user message; leave the rest null/false.
- vehicle_mention      — car model name (e.g., "제타", "GV70", "K7", "쏘나타"). Null if absent.
- vehicle_possessive   — true ONLY when the user marks the car as theirs ("내", "내 차", "등록차"). False otherwise.
- vehicle_number       — Korean plate (e.g., "12가3456"). Null if absent.
- tire_size            — normalized "WWW/AAR DD" (e.g., "225/45R17"). Convert "2254517" / "225 45 17" to canonical form.
- tire_attribute       — tire type/attribute mention (e.g., "전기차용", "사계절", "런플랫", "광폭", "스노우").
- product_name         — model name (e.g., "벤투스 S2", "Dynapro HPX", "키너지 GT").
- scenario             — driving scenario (e.g., "빗길", "눈길", "주말", "가족", "전기차", "고속").
- question_form        — one of: "yes_no" | "info_request" | "action_request" | "selection" | "confirmation"; null if none applies.

⚠️ Extraction is structural only. Do NOT infer values that are not present. Empty/null is preferred over a guess.
⚠️ goods_no, brand, quantity, store_keyword, owner_nm fields were removed from the schema — agents extract these from the user message text directly when needed.

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

Worked example 1 (with 다시 keyword):
  - Previous: get_products_recommendations_tool(rcmd_type="wet") returned 4 items
  - Current user message: "주말 나들이용으로 다시"
  - CORRECT user_behavior: "requesting new recommendation with weekend scenario after previous wet recommendation"
  - WRONG user_behavior: "selecting weekend-suitable items from previous tire list"
  - WRONG user_behavior: "filter previous recommendations for weekend use"

Worked example 2 (NO 다시 keyword — scenario change with intervening turn):
  - Earlier turn: get_products_recommendations_tool(rcmd_type="ev") returned 4 items (235/55R19)
  - Intervening turn: get_product_description_tool (description only — does NOT reset PREV)
  - Current user message: "패밀리 SUV에 잘 맞는 사계절용 추천"
  - PREV rcmd_type = "ev"; user mentions "패밀리/가족" + "사계절" — clearly
    different scenario family from "ev" → RE-RECOMMENDATION applies.
  - CORRECT user_behavior: "requesting NEW recommendation with family + 사계절 scenario; previous rcmd_type='ev' no longer matches"
  - WRONG user_behavior: "filter previous EV list for family-friendly all-season options"
  - WRONG user_behavior: "pick 사계절 candidates from previous list"

Worked example 3 (PREV=CUR escape — NOT re-recommendation):
  - Previous: get_products_recommendations_tool(rcmd_type="ev") returned 4 items
  - Current user message: "이 EV 타이어 중에서 18인치로"
  - "EV" matches PREV; "이 중에서" is a demonstrative → continuation, NOT re-recommendation.
  - user_behavior: "filtering previous EV recommendation list by size 18인치"

Also identify the FLOW SEQUENCE (ordered list of domains) for the request.

DOMAINS:
- TRANSACTION: Price, stock (logistics/store), inventory, store availability, store search by location/name, purchase, checkout, order tracking, reservation, coupon inquiry (내 쿠폰 / 받을 수 있는 쿠폰 / 쿠폰함 / 다운로드 가능 쿠폰), order history inquiry (내 주문내역 / 주문 내역 / 주문 조회)
- SUPPORT: FAQ, warranty, returns, policies, maintenance, human agent
- DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features, product video reviews, YouTube video search
- LEADING: Greeting, unclear intent

====================================================
DOMAIN ROUTING EXAMPLES
====================================================

DISCOVERY — product search, recommendation, compatibility (no goods_no yet):
1. "i want to buy tires for 12가3456" → DISCOVERY (lookup car → recommend tires → STOP, wait for user)
2. "쏘나타에 맞는 타이어 추천해줘" → DISCOVERY
3. "벤투스 S2 가격" / "Dynapro HPX 얼마야?" → DISCOVERY (resolve goods_no first → STOP)
4. "벤투스 S2 재고 확인해줘" → DISCOVERY (resolve goods_no → STOP)
5. "벤투스 S2 AS 살 수 있는 매장" → DISCOVERY (resolve goods_no → STOP)
6. "이벤트 알려줘" / "기획전 정보" → DISCOVERY
7. "타이어 리뷰 영상 보여줘" → DISCOVERY
8. "추천 타이어들 가격 비교해줘" → DISCOVERY (compare_discount_tool is in Discovery)

TRANSACTION — price/stock/store/order with goods_no already known in context:
1. "{{goods_no}} 가격 얼마야?" → TRANSACTION
2. "주문할게" / "바로 주문할게" → TRANSACTION
3. "장바구니에 담아줘" → TRANSACTION
4. "강남 매장 찾아줘" / "근처 매장" → TRANSACTION
5. "한남점 예약 가능한 날짜 알려줘" → TRANSACTION
6. "주문 내역 확인해줘" / "내 주문내역 알려줘" / "주문 조회해줘" → TRANSACTION
7. "내 쿠폰 보여줘" / "받을 수 있는 쿠폰" / "다운로드 가능 쿠폰은?" / "쿠폰함" → TRANSACTION
8. "티스테이션 한남점 선택할게" → TRANSACTION (store selection continuation)

SUPPORT — policy, warranty, human agent:
1. "보증 정책 알려줘" / "반품 가능해?" → SUPPORT
2. "1:1 문의 작성해줘" / "상담원 연결" → SUPPORT

⚠️ NEVER classify these as SUPPORT — always TRANSACTION (handled by coupon/order tools, NOT FAQ):
- 내 쿠폰 / 쿠폰 조회 / 쿠폰함 / 다운로드 가능 쿠폰
- 내 주문내역 / 주문 내역 / 주문 조회 / 내 주문

LEADING — greeting, unclear intent:
1. "안녕하세요" / "뭘 도와줄 수 있어?" → LEADING

====================================================
DECISION RULES
====================================================

CORE RULE: Classify into EXACTLY ONE domain per turn.
Each domain does its ONE job and stops. User drives every next step.

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

⚠️ "buy/order/purchase" with product NAME (not goods_no) → DISCOVERY first to find goods_no, then STOP and wait for user.
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
- "다시" → LEADING (bare, no context)
- "다시 해줘" → LEADING (bare)
- "다른 거 보여줘" → LEADING (bare; "보여줘" is generic, no domain anchor)
- "이전 추천 말고" → LEADING (bare re-trigger only)
- "주말 나들이용으로 다시" → DISCOVERY (has scenario keyword "주말")
- "벤투스 S2 다시 알려줘" → DISCOVERY/TRANSACTION (has product name)
- "가격 다시 알려줘" → 이전 컨텍스트의 도메인 그대로 (TRANSACTION if goods_no
  known, DISCOVERY otherwise — "가격" is a clear domain anchor)
- "다시 추천해줘" → DISCOVERY (has explicit intent verb "추천")

⚠️ This rule overrides CONTINUATION DETECTION below for bare re-triggers — a
bare re-trigger is NOT a valid continuation; it's an ambiguous request that
needs clarification before any agent runs.

====================================================
FRESH TOPIC OVERRIDE (highest precedence)
====================================================

When the user's CURRENT message clearly introduces a NEW topic — even if the conversation just finished a cart save, order confirmation, store selection, or any other transaction-domain state — classify the message by the topic in the message itself, NOT by the surrounding conversation context. The slot context (`[목표: 주문 진행]`, `[확인된 고객 정보]`) and recent transaction history must NOT bias the classification when the user has clearly pivoted.

Topic keywords that ALWAYS trigger the listed domain regardless of conversation history:

- "이벤트", "이벤트 목록", "진행 중인 이벤트", "기획전", "기획전 보여줘", "기획전 내용"
  → DISCOVERY, intent=event_inquiry
- "영상", "리뷰 영상", "유튜브", "동영상"
  → DISCOVERY, intent=video_inquiry
- "내 차 목록", "내 차량", "등록차 보여줘", "내 등록차"
  → DISCOVERY, intent=vehicle_lookup
- "타이어 추천", "어떤 타이어", "추천해줘" (with no specific tire name in current message)
  → DISCOVERY, intent=recommend
- "껴도 돼?", "맞아?", "써도 돼?", "장착 돼?" (yes/no fit question)
  → DISCOVERY, intent=compatibility
- "내 쿠폰", "받을 수 있는 쿠폰", "쿠폰함", "다운로드 가능 쿠폰", "쿠폰 조회"
  → TRANSACTION, intent=coupon
- "내 주문내역", "주문 내역", "주문 조회", "내가 주문한"
  → TRANSACTION, intent=other (order history)
- "강남 매장", "근처 매장", "매장 찾아줘", "올마이티", "All My T"
  → TRANSACTION, intent=store_search
- "환불", "반품", "교환", "보증", "워런티", "1:1 문의", "상담원 연결"
  → SUPPORT (intent per Support taxonomy)

⚠️ This override beats CONTINUATION DETECTION below. A user who just finished cart-save and types "이벤트 목록" has NOT continued the cart flow — they've changed topic. Do NOT classify as TRANSACTION just because the recent history is transactional.

⚠️ The override does NOT apply to ambiguous short messages (bare ordinals "1번", bare product names without verb, bare yes/no "네") — those follow CONTINUATION DETECTION below.

Worked examples (post-cart context):
- Just emitted preOrder/cartComplete → User: "이벤트 목록" → DISCOVERY/event_inquiry (NOT TRANSACTION)
- Just confirmed order → User: "내 쿠폰 보여줘" → TRANSACTION/coupon (different intent within same domain — not continuation of order flow)
- Just showed store list → User: "타이어 추천해줘" → DISCOVERY/recommend (NOT continuation of store selection)
- Just showed tire cards → User: "환불은 어떻게 해?" → SUPPORT (NOT DISCOVERY)


====================================================
CONTINUATION DETECTION
====================================================

If the previous agent showed a list and asked user to SELECT (cars, tires, stores, dates):
→ User's short reply (number, name, tire size, store name) is a CONTINUATION of the SAME domain.
→ Classify into that SAME domain — do NOT chain to another domain.

Examples:
- Previous: Discovery showed car list → User: "제타" → DISCOVERY (same domain continues)
- Previous: Discovery showed tires → User: "벤투스 S2 AS" → DISCOVERY (same domain continues)
- Previous: Discovery showed tires → User: "1. 벤투스 S2 AS" → DISCOVERY (ordinal prefix
  does NOT change domain; the user is still picking a tire from the recommendation list,
  not placing an order)
- Previous: Discovery showed tires → User: "1번", "3", "첫번째" → DISCOVERY (pure ordinal)
- Previous: Transaction showed stores → User: "한남점" → TRANSACTION (same domain continues)
- Previous: Transaction showed schedule → User: "내일 10시" → TRANSACTION (same domain continues)

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

    intent / entities ARE populated even on the first turn — they are the
    primary routing signal that future agent refactors will consume.
    """
    return """
You are a domain classifier for T-Station AI (Hankook Tire).
Classify the user's FIRST message into EXACTLY ONE domain plus a primary intent and structured entities.

DOMAINS:
- TRANSACTION: store search by location or name (강남/근처/올마이티/All My T); goods_no (G+12 digits) price/stock/order; reservation; cart; coupon inquiry (내 쿠폰/쿠폰함/받을 수 있는 쿠폰/다운로드 가능 쿠폰) [⚠️ NOT SUPPORT]; order history (내 주문내역/주문 조회/내 주문/내가 주문한 거) [⚠️ NOT SUPPORT].
- DISCOVERY: product search by name or keyword; tire recommendation; vehicle-tire compatibility; product specs/features/videos; price/stock/buy with PRODUCT NAME ONLY (no goods_no — Discovery resolves goods_no first).
- SUPPORT: warranty, returns, refund, maintenance, 1:1 문의, 상담원 연결, customer complaints (짜증/엉망/화나/뭐 이런).
- LEADING: pure greeting; unclear intent; bare re-trigger words (다시/또) with no domain anchor.

DOMAIN RULES:
- G+12 digits in message → TRANSACTION
- Product name only (벤투스/Ventus/다이나프로/Dynapro/...) + price/stock/buy, no goods_no → DISCOVERY
- Vehicle number (e.g. 12가3456) + tire request → DISCOVERY
- 추천/맞는 타이어/어떤 타이어 → DISCOVERY
- 매장/근처/올마이티/All My T → TRANSACTION
- 환불/반품/보증/워런티/1:1 문의/상담원 → SUPPORT
- Complaint tone (짜증/엉망/화나/뭐 이런) → SUPPORT
- Greeting only (안녕/hi/hello) → LEADING

DOMAIN EXAMPLES (tricky cases):
- "벤투스 S2 가격 얼마야?" → DISCOVERY (product name, no goods_no)
- "G012345678901 가격" → TRANSACTION (goods_no present)
- "내 쿠폰 보여줘" → TRANSACTION (NOT SUPPORT)
- "내 주문내역 알려줘" → TRANSACTION (NOT SUPPORT)
- "12가3456 타이어 추천" → DISCOVERY

====================================================
INTENT TAXONOMY (always pick exactly ONE — 20 values)
====================================================

DISCOVERY: recommend | compatibility | info_question | product_search | vehicle_lookup | compare | event_inquiry | video_inquiry
TRANSACTION: price | stock | order | store_search | coupon
SUPPORT: faq | return | complaint
LEADING: greeting
Cross-domain: selection | confirmation | other (use `other` for unclear intent / re-trigger / order tracking / reservation / etc.)

⚠️ INTENT vs DOMAIN are decoupled. Common confusions on first turn:
- "내 제타에 전기차용 타이어 껴도 돼?"     → domain=DISCOVERY, intent=compatibility   (yes/no fit question, NOT recommend)
- "타이어 언제 갈아야 돼?"                  → domain=DISCOVERY, intent=info_question   (knowledge question, NOT recommend)
- "공기압 얼마가 적정?"                     → domain=DISCOVERY, intent=info_question
- "내 GV70에 맞는 타이어 추천해줘"          → domain=DISCOVERY, intent=recommend
- "벤투스 S2 가격 얼마야?"                  → domain=DISCOVERY, intent=product_search
- "G012345678901 가격"                       → domain=TRANSACTION, intent=price
- "강남 매장 찾아줘"                         → domain=TRANSACTION, intent=store_search
- "내 쿠폰 보여줘"                           → domain=TRANSACTION, intent=coupon
- "환불하고 싶어"                            → domain=SUPPORT, intent=return
- "안녕"                                     → domain=LEADING, intent=greeting

Compatibility detection signals (intent=compatibility on DISCOVERY):
- yes/no question form: ends with "돼?", "맞아?", "맞나?", "되나요?", "돼요?", "써도 돼?", "껴도 돼?", "장착 돼?", "OK?"
- combined with a tire-attribute or tire-size mention.

====================================================
ENTITY EXTRACTION (8 fields)
====================================================

Populate `entities` with whatever applies; leave the rest null/false.
- vehicle_mention      — car model name (e.g., "제타", "GV70", "K7"). Null if absent.
- vehicle_possessive   — true ONLY when the user marks the car as theirs ("내", "내 차", "등록차").
- vehicle_number       — Korean plate (e.g., "12가3456"). Null if absent.
- tire_size            — normalized "WWW/AAR DD" (e.g., "225/45R17"). Convert "2254517" / "225 45 17" to canonical.
- tire_attribute       — tire type (e.g., "전기차용", "사계절", "런플랫", "광폭", "스노우").
- product_name         — model name (e.g., "벤투스 S2", "Dynapro HPX").
- scenario             — driving scenario (e.g., "빗길", "눈길", "주말", "가족", "전기차", "고속").
- question_form        — one of: "yes_no" | "info_request" | "action_request" | "selection" | "confirmation"; null if none.

⚠️ Extraction is structural. Do NOT infer values not present. Null is preferred over a guess.

Output: domains (EXACTLY ONE) + intent + entities + reason (english).
"""


class StreamingMultiAgentCoordinator:
    """Orchestrates multiple agents with streaming support."""

    def __init__(self):
        self.agent_map = {
            MultiAgentDomain.Domain.DISCOVERY: discovery_subagent,
            MultiAgentDomain.Domain.TRANSACTION: transaction_subagent,
            MultiAgentDomain.Domain.SUPPORT: support_subagent,
            MultiAgentDomain.Domain.LEADING: leading_agent,
        }

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
        from config.tracing import build_trace_config

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
            )
            raw_result = structured_model.invoke(all_messages, config=trace_config)

            # Normalize slim result to MultiAgentDomain for downstream compat.
            # Empty narrative fields short-circuit _inject_conversation_context.
            if is_first_turn:
                result = MultiAgentDomain(
                    reason=raw_result.reason,
                    domains=raw_result.domains,
                    intent=raw_result.intent,
                    entities=raw_result.entities,
                    user_behavior="",
                    flow="",
                )
            else:
                result = raw_result

            logger.info(
                "[MULTI-DOMAIN] Classification result: domain=%s, intent=%s, behavior=%r, flow=%r",
                result.domains,
                result.intent,
                result.user_behavior,
                result.flow,
            )
            domains = result.domains if result.domains else [MultiAgentDomain.Domain.LEADING]
            return domains, result

        except Exception as e:
            logger.exception(f"[MULTI-DOMAIN] Classification failed: {e}")
            return [MultiAgentDomain.Domain.LEADING], None

    @staticmethod
    def _inject_conversation_context(messages: list[dict], routing: MultiAgentDomain | None) -> list[dict]:
        """Inject conversation context (intent, entities, user_behavior, flow) above
        the Korean instruction in the last user message.

        Intent + Entities are surfaced as advisory context for the domain agent —
        agent prompts may ignore them today, but observability (Langfuse traces +
        logs) still benefits, and a future agent refactor can read them without
        another schema change.

        After injection:
            ## CONVERSATION CONTEXT
            - Intent: <intent>
            - Entities: <key1=val1, key2=val2, ...>     (only non-null fields)
            - User behavior: ...
            - Flow so far: ...

            # Respond in Korean language
            <original user text>
        """
        if routing is None:
            return messages

        context_parts: list[str] = []

        if getattr(routing, "intent", None) is not None:
            try:
                intent_value = routing.intent.value
            except AttributeError:
                intent_value = str(routing.intent)
            context_parts.append(f"- Intent: {intent_value}")

        entities_kv: list[str] = []
        entities = getattr(routing, "entities", None)
        if entities is not None:
            entity_dump = entities.model_dump(exclude_none=True)
            for key, val in entity_dump.items():
                # vehicle_possessive is bool — only surface when True (its False default carries no signal)
                if key == "vehicle_possessive" and not val:
                    continue
                if val is None or val == "":
                    continue
                entities_kv.append(f"{key}={val}")
        if entities_kv:
            context_parts.append("- Entities: " + ", ".join(entities_kv))

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

        return {"role": "assistant", "content": f"[Context from previous steps]\n" + "\n".join(parts)}

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
    def _save_tool_derived_slots(session_id: str, tool_name: str, parsed_data: dict, tool_input: dict | None = None):
        """Persist goods_no, shop_id, and tire_size from successful tool results/inputs to slots.

        Also clears `pending_intent` when the tool that ran fulfills that intent
        (see `_TOOL_TO_FULFILL`).
        """
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

        # Fulfillment: if this tool satisfies a pending intent AND succeeded, clear it.
        # Tools return {"status": "success"|"error", ...}; only "success" counts as fulfillment
        # so a failed price/stock/order lookup still leaves the intent for retry.
        # Done BEFORE other slot updates so the cleared state is the one we save.
        fulfilled_intent = StreamingMultiAgentCoordinator._TOOL_TO_FULFILL.get(tool_name)
        tool_succeeded = isinstance(parsed_data, dict) and parsed_data.get("status") == "success"
        if fulfilled_intent and tool_succeeded:
            try:
                svc = get_chat_history_service()
                current_slots = svc.get_slots(session_id)
                if current_slots.pending_intent == fulfilled_intent:
                    new_slots = current_slots.model_copy()
                    new_slots.pending_intent = None
                    svc.save_slots(session_id, new_slots)
                    logger.info(
                        f"[SLOTS] Cleared pending_intent={fulfilled_intent!r} after {tool_name} completed successfully"
                    )
            except Exception as e:
                logger.warning(f"[SLOTS] Failed to clear pending_intent: {e}")

        # Map tool names to the slot fields they can provide (from output)
        tool_slot_extractors = {
            "search_product_tool": ["goods_no"],
            "get_store_list_tool": ["shop_id"],
            "get_nearby_stores_tool": ["shop_id"],
            "get_store_inventory_tool": ["shop_id"],
        }

        # When user searches for a different car model, reset tire_size and goods_no
        # so the previous vehicle's tire_size doesn't persist
        if tool_name == "search_car_model_tool":
            try:
                svc = get_chat_history_service()
                current_slots = svc.get_slots(session_id)
                if current_slots.tire_size is not None or current_slots.goods_no is not None:
                    new_slots = current_slots.model_copy()
                    new_slots.tire_size = None
                    new_slots.goods_no = None
                    svc.save_slots(session_id, new_slots)
                    logger.info("[SLOTS] Reset tire_size and goods_no due to search_car_model_tool call")
            except Exception as e:
                logger.warning(f"[SLOTS] Failed to reset slots on car model search: {e}")

        # Extract tire_size from tool INPUT when recommendation tool is called
        # This captures the confirmed tire_size that the LLM used for recommendations
        if tool_name == "get_products_recommendations_tool" and tool_input:
            input_tire_size = tool_input.get("tire_size")
            if input_tire_size:
                try:
                    svc = get_chat_history_service()
                    current_slots = svc.get_slots(session_id)
                    new_slots = ConversationSlots(tire_size=input_tire_size)
                    updated = current_slots.merge(new_slots)
                    svc.save_slots(session_id, updated)
                    logger.info(f"[SLOTS] tire_size saved from {tool_name} input: {input_tire_size}")
                except Exception as e:
                    logger.warning(f"[SLOTS] Failed to save tire_size from tool input: {e}")

        # Extract goods_no from tool INPUT when product description tool is called.
        # Without this, picking a product from the recommend list (Branch S — "1번",
        # "벤투스 S2 AS") routes through get_product_description_tool but leaves
        # goods_no=None. The goal-router then treats `model` as missing on the next
        # "구매할게" turn and routes to Discovery instead of Transaction, breaking
        # the order auto-chain.
        if tool_name == "get_product_description_tool" and tool_input:
            input_goods_no = tool_input.get("goods_no")
            if input_goods_no:
                try:
                    svc = get_chat_history_service()
                    current_slots = svc.get_slots(session_id)
                    new_slots = ConversationSlots(goods_no=input_goods_no)
                    updated = current_slots.merge(new_slots)
                    svc.save_slots(session_id, updated)
                    logger.info(f"[SLOTS] goods_no saved from {tool_name} input: {input_goods_no}")
                except Exception as e:
                    logger.warning(f"[SLOTS] Failed to save goods_no from tool input: {e}")

        fields = tool_slot_extractors.get(tool_name)
        if not fields:
            return

        # Extract values from tool result data
        tool_slots = {}
        data = parsed_data.get("data", parsed_data)

        # Handle list results (e.g., search results) — only auto-fill if exactly 1 item
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
            if isinstance(items, list) and len(items) == 1:
                data = items[0]
            else:
                return  # Multiple or no results — don't auto-fill
        elif isinstance(data, dict) and "stores" in data:
            stores = data["stores"]
            if isinstance(stores, list) and len(stores) == 1:
                data = stores[0]
            else:
                return

        for field in fields:
            val = data.get(field) if isinstance(data, dict) else None
            if val:
                tool_slots[field] = val

        if not tool_slots:
            return

        try:
            svc = get_chat_history_service()
            current_slots = svc.get_slots(session_id)
            new_slots = ConversationSlots(**tool_slots)
            updated = current_slots.merge(new_slots)
            svc.save_slots(session_id, updated)
            logger.info(f"[SLOTS] Tool-derived slots saved from {tool_name}: {tool_slots}")
        except Exception as e:
            logger.warning(f"[SLOTS] Failed to save tool-derived slots: {e}")

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
        from config.tracing import build_trace_config, trace_span as _trace_span, truncate_for_trace as _truncate

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

        logger.info(f"[COORDINATOR] Streaming for domains: {[d.value for d in domains]}")

        accumulated_context = {}
        accumulated_tool_data = []  # Collect tool outputs for UI Template Agent
        domain_data_event_emitted = False  # Domain agent emitted a `data` event itself

        is_first_agent = True

        for domain in domains:
            agent = self.agent_map.get(domain)
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
                        logger.info(f"[COORDINATOR] Passing context to {domain.value}")
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
                            logger.info(f"[COORDINATOR] Extracted ord_qty={ord_qty} from user message")

                tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
                enriched_messages.append(
                    {"role": "assistant", "content": f"[Previous agent tool results]\n{tool_summary}"}
                )
                logger.info(f"[COORDINATOR] Passing {len(accumulated_tool_data)} tool results to {domain.value}")

            domain_key = domain.value
            logger.info(
                f"[COORDINATOR_MESSAGE] Domain: {domain_key}, enriched_messages: {json.dumps(enriched_messages, ensure_ascii=False, indent=2)}"
            )

            # Yield agent start event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "start",
            }

            # Stream from agent and yield events immediately
            full_response = ""
            last_agent_called_tools = False
            agent_tools_called: list[str] = []

            # Last user message becomes the agent span's input — keeps the
            # trace readable instead of dumping the entire enriched_messages
            # array (which includes slot/tool context blocks).
            _agent_input_msg = next(
                (m.get("content", "") for m in reversed(enriched_messages) if m.get("role") == "user"),
                "",
            )

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
                )
                for event in agent.stream(enriched_messages, config=agent_trace_config):
                    # Tag with source domain for UI
                    event["source_domain"] = domain_key
                    yield event

                    # Track direct data events emitted by the domain agent (JSON output).
                    # When present, skip the UI Template stage below.
                    if event.get("type") == "data":
                        domain_data_event_emitted = True

                    # Capture message content for context passing
                    if event.get("type") == "message":
                        content = event.get("content", "")
                        if content:
                            accumulated_context[domain_key] = content
                            full_response = content
                            logger.info(f"[COORDINATOR] Captured message for {domain_key}: {content}...")

                    # Capture tool outputs for UI Template Agent
                    if event.get("type") == "tool":
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

                                # Persist tool-derived goods_no, shop_id, and tire_size to slots
                                if session_id and isinstance(parsed, dict):
                                    self._save_tool_derived_slots(
                                        session_id, tool_name, parsed, event.get("input", {})
                                    )

                            except (json.JSONDecodeError, TypeError):
                                accumulated_tool_data.append({
                                    "tool": tool_name,
                                    "input": event.get("input", {}),
                                    "data": tool_output,
                                })

                _agent_span.update(
                    output=_truncate({
                        "response": full_response,
                        "tools_called": agent_tools_called,
                        "data_event_emitted": domain_data_event_emitted,
                    }),
                )

            # Yield agent completion event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "done",
            }

            # LLM Decision: After first agent, use LLM to decide next action
            # Support domain rarely chains to other agents — skip LLM decision to save ~300ms
            if is_first_agent:
                is_first_agent = False
                if domain == MultiAgentDomain.Domain.SUPPORT:
                    logger.info("[COORDINATOR] Support domain — skipping LLM decision, stopping chain")
                    break

                # Caller pre-committed the chain (e.g., P0 auto-chain code gate) —
                # skip the decide_next_action LLM call (saves ~300ms) and proceed
                # directly to the next domain in `domains`.
                #
                # BUT: only proceed if Discovery actually resolved a single goods_no.
                # `_save_tool_derived_slots` (search_product_tool extractor) only
                # writes goods_no to slots when the tool returns exactly 1 item;
                # 0/multiple-result cases leave goods_no=None and Discovery is
                # already in clarification/selection mode. Chaining Transaction on
                # top would produce a contradictory "상품 검색이 필요합니다" fallback.
                if skip_decision and len(domains) >= 2:
                    goods_no_resolved = False
                    if session_id:
                        try:
                            from services.tstation.chat_history_service import get_chat_history_service

                            post_slots = get_chat_history_service().get_slots(session_id)
                            goods_no_resolved = post_slots.goods_no is not None
                        except Exception as e:
                            logger.warning(f"[COORDINATOR] Failed to verify goods_no post-Discovery: {e}")
                    if not goods_no_resolved:
                        logger.info(
                            "[COORDINATOR] skip_decision=True but Discovery did not resolve "
                            "goods_no (0 or multiple results) — stopping chain"
                        )
                        break
                    logger.info(
                        "[COORDINATOR] skip_decision=True — proceeding to next domain "
                        f"({domains[1].value}) without LLM decision"
                    )
                    continue

                # Agent already produced a complete UI payload — decide_next_action
                # would return STOP anyway (its prompt: "ONLY CONTINUE when agent cannot complete the task").
                if domain_data_event_emitted:
                    logger.info("[COORDINATOR] Data event emitted — skipping decide_next_action")
                    break

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
                if (
                    domain == MultiAgentDomain.Domain.TRANSACTION
                    and len(domains) == 1
                    and not last_agent_called_tools
                    and re.search(r"상품을?\s*검색|상품\s*검색이?\s*필요", full_response or "")
                ):
                    goods_no_still_none = True
                    if session_id:
                        try:
                            from services.tstation.chat_history_service import get_chat_history_service

                            post_slots = get_chat_history_service().get_slots(session_id)
                            goods_no_still_none = post_slots.goods_no is None
                        except Exception as e:
                            logger.warning(f"[COORDINATOR] P1-B slot check failed: {e}")
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
                # transactional handoff line (재고/가격/매장/주문 ... 이어갈게요/
                # 이어드릴게요/확인해 드릴게요/진행해 드릴게요) WITHOUT calling
                # any tool, with goods_no already resolved in slots. Without
                # recovery, the user is stranded — the stream ends with only
                # an "I'll continue" message and the actual transactional
                # tool never runs.
                #
                # Conditions (ALL must hold):
                #   1. The first/only domain executed was DISCOVERY.
                #   2. `last_agent_called_tools is False` — Discovery did not
                #      call any tool (legitimate Discovery turns calling
                #      search_product_tool / get_youtube_video_tool stay untouched).
                #   3. `full_response` matches the transactional handoff regex.
                #   4. `goods_no` is set in slots — TRANSACTION can run.
                #
                # Recovery: extend `domains` IN-PLACE with [TRANSACTION]
                # (mutation propagates to the active for-loop iterator).
                if (
                    domain == MultiAgentDomain.Domain.DISCOVERY
                    and len(domains) == 1
                    and not last_agent_called_tools
                    and re.search(
                        r"(재고|가격|매장|주문|장착|예약).{0,30}"
                        r"(이어갈게요|이어드릴게요|확인해\s*드릴게요|진행해\s*드릴게요|진행할게요)",
                        full_response or "",
                    )
                ):
                    goods_no_set = False
                    if session_id:
                        try:
                            from services.tstation.chat_history_service import get_chat_history_service

                            post_slots = get_chat_history_service().get_slots(session_id)
                            goods_no_set = post_slots.goods_no is not None
                        except Exception as e:
                            logger.warning(f"[COORDINATOR] P1-D slot check failed: {e}")
                    if goods_no_set:
                        logger.warning(
                            "[COORDINATOR] P1-D stall recovery: DISCOVERY-only emitted "
                            "transactional-handoff text with no tool call and goods_no "
                            "set — extending chain to [TRANSACTION] as recovery."
                        )
                        domains.append(MultiAgentDomain.Domain.TRANSACTION)
                        skip_decision = True
                        continue

                decision = decide_next_action(
                    original_messages=messages,
                    previous_agent_response=full_response,
                    previous_domain=domain_key,
                    session_id=session_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    parent_span_id=parent_span_id,
                )
                logger.info(f"[COORDINATOR] LLM Decision: {decision.next_action} - {decision.reason}")

                if decision.next_action == NextAction.STOP or not decision.next_domain:
                    logger.info("[COORDINATOR] Stopping multi-agent chain")
                    break

                # Map next_domain string to enum
                next_domain_map = {
                    "discovery": MultiAgentDomain.Domain.DISCOVERY,
                    "transaction": MultiAgentDomain.Domain.TRANSACTION,
                    "support": MultiAgentDomain.Domain.SUPPORT,
                }
                next_domain = next_domain_map.get(decision.next_domain.lower())
                if next_domain:
                    domains = [next_domain] + [d for d in domains if d != next_domain]

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
            logger.info("[COORDINATOR] Domain agent emitted data event — skipping UI Template Agent")
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

        # Final done event
        yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}


import re

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

# Master toggle. Set False to disable goal-based fast-path without removing the
# code (useful if downstream telemetry shows mis-routes; the LLM classifier
# remains the safety net regardless).
_GOAL_FAST_PATH_ENABLED = True


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
        logger.info("[GOAL_ROUTER] goal-switch keyword in text — falling through")
        return None

    next_step_id = merged_slots.next_goal_step_id()

    if next_step_id is None:
        domain = _GOAL_COMPLETE_DOMAIN.get(goal_type)
        if domain is not None:
            logger.info(f"[GOAL_ROUTER] goal={goal_type} all steps done → {domain.value}")
            return [domain]
        return None

    domain = _GOAL_NEXT_STEP_DOMAIN.get((goal_type, next_step_id))
    if domain is not None:
        logger.info(f"[GOAL_ROUTER] goal={goal_type} next_step={next_step_id} → {domain.value}")
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
        logger.info(f"[SUPPORT_FAST_PATH] → SUPPORT: {text[:60]!r}")
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
        logger.info("[RULE_ROUTER] Greeting fast-path → LEADING")
        return [MultiAgentDomain.Domain.LEADING]

    # Case 2: Clear support / escalation keywords
    if _SUPPORT_FAST_RE.search(text):
        logger.info(f"[RULE_ROUTER] Support keyword fast-path → SUPPORT: {text[:60]!r}")
        return [MultiAgentDomain.Domain.SUPPORT]

    # Case 3: goods_no already in slots + transactional keyword in current turn
    if merged_slots.goods_no and _TRANSACTION_FAST_RE.search(text):
        logger.info(f"[RULE_ROUTER] goods_no={merged_slots.goods_no!r} in slots + transactional keyword → TRANSACTION")
        return [MultiAgentDomain.Domain.TRANSACTION]

    # Case 4: goods_no pattern directly written in user text + transactional keyword
    if re.search(r"G\d{9,}", text) and _TRANSACTION_FAST_RE.search(text):
        logger.info("[RULE_ROUTER] goods_no literal in text + transactional keyword → TRANSACTION")
        return [MultiAgentDomain.Domain.TRANSACTION]

    return None


def _sanitize_response(text: str) -> str:
    """Replace internal jargon with user-friendly fallback if response has no useful content."""
    stripped = text.strip()
    if not stripped:
        return _FALLBACK_RESPONSE
    if _INTERNAL_JARGON_PATTERN.search(stripped) and len(stripped) < 100:
        return _FALLBACK_RESPONSE
    return text


_FACTUAL_CLAIM_PATTERN = re.compile(
    r"\d{1,3}(?:,\d{3})*\s*원"       # 가격 (e.g. 150,000원)
    r"|G\d{9,}"                        # goods_no (e.g. G000000313150)
    r"|\d{3}/\d{2,3}[a-zA-Z]+\d{2}"  # 타이어 사이즈 (e.g. 225/40R18, 245/40ZR19)
    r"|티스테이션\s*\S*점"             # 매장명 (e.g. 티스테이션양평점)
    r"|F\d{5}\b",                      # shop_id (e.g. F01234)
    re.IGNORECASE,
)


def _has_factual_claims(text: str) -> bool:
    return bool(_FACTUAL_CLAIM_PATTERN.search(text))


_QC_SKIP_TOOLS = frozenset({"get_my_cars_tool", "transfer_to_qna_tool"})
_QC_SKIP_TEMPLATES = frozenset({"listCar", "qnaComplete", "datepick"})
# Path B: LLM writes the JSON → QC may correct field values
_LLM_WRITTEN_TEMPLATES = frozenset({"preOrder", "orderComplete"})


def _should_skip_qc(called_tool_names: set[str], last_template: str | None) -> bool:
    if last_template in _QC_SKIP_TEMPLATES:
        return True
    if called_tool_names and called_tool_names.issubset(_QC_SKIP_TOOLS):
        return True
    return False


def _parse_qc_output(qc_result: str) -> tuple[str, dict | None]:
    """Returns (corrected_text, template_json | None)."""
    if "[Template:" not in qc_result:
        return qc_result, None
    parts = qc_result.split("[Template:", 1)
    corrected_text = parts[0].strip()
    try:
        newline_idx = parts[1].index("\n")
        json_str = parts[1][newline_idx + 1:].strip()
        return corrected_text, json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        return corrected_text, None


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


def _enrich_messages_with_template_data(messages: list[dict], session_id: str) -> list[dict]:
    """Attach template_data from Redis to recent assistant card turns.

    Walks messages in reverse and enriches up to _TEMPLATE_ENRICH_MAX_TURNS
    most-recent assistant turns whose content matches a Redis-stored
    template_data entry. Each enriched turn gets a `[이전 선택된 상품 데이터]`
    JSON appended to its content so the LLM can resolve references like
    "두번째 매장", "그 사이즈" across multi-turn card flows.

    Token-context concerns are bounded by the cap; the BE-filtered
    tool_context (loaded as a separate system message) preserves additional
    older-turn structured data.
    """
    if not session_id:
        return messages

    try:
        from services.tstation.chat_history_service import get_chat_history_service

        redis_messages = get_chat_history_service().get_history(session_id)

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

        for idx, item in enumerate(tool_data):
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
                for i, row in enumerate(data, 1):
                    if isinstance(row, dict):
                        if row.get("_truncated"):
                            lines.append(f"  ... {row['_truncated']}")
                        else:
                            row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
                            lines.append(f"  {i}. {row_str}")
                    else:
                        lines.append(f"  {i}. {row}")
            elif isinstance(data, dict):
                row_str = " | ".join(f"{k}: {v}" for k, v in data.items())
                lines.append(f"  {row_str}")

            lines.append("")

        return "\n".join(lines)

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

        Only the most recent search_product_tool entry is inspected.
        Returns None when no confident match is found.

        Expected tool_context entry shape (produced by filter_for_context in
        g_qc_agent/source_filter.py, which is what gets persisted to Redis):
            {"tool": "search_product_tool",
             "data": [{"goods_no": "...", "goods_nm": "...", "tire_size_1": "..."}],
             "input": {...}}
        Note: `data` is a LIST directly, and the size field is `tire_size_1`
        (filter whitelist is {"goods_no", "goods_nm", "tire_size_1", ...}).
        """
        if not user_text or not prev_tool_data:
            return None

        items: list[dict] = []
        for entry in prev_tool_data:
            if entry.get("tool") != "search_product_tool":
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
    def _resolve_tire_size_from_history_template(user_text: str, history: list[dict]) -> str | None:
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

        Expected history msg shape (from chat_history_service.get_history):
            {"role": "assistant", "content": "...",
             "template_data": {"type": "data", "template": "listCar",
                               "data": {"listCar": [{"licensePlate": "12가3456",
                                                     "info": "K7 2.5 GDI", ...}],
                                        "metadata": [{"carNo": "12가3456",
                                                      "carLncCd": "01",
                                                      "tireSize": "225/45R17",
                                                      "tireSizeRe": "225/45R17"}]}}}

        Matching strategy (first hit wins):
          1. License plate verbatim ("12가3456", "123가4567") against carNo.
          2. Ordinal at the start ("1.", "1번", "2)") → metadata[idx-1].
          3. Token-overlap against listCar[i].info — unique top scorer required.
        """
        if not user_text or not history:
            return None

        latest_listcar: dict | None = None
        for msg in reversed(history):
            if msg.get("role") != "assistant":
                continue
            template_data = msg.get("template_data")
            if not isinstance(template_data, dict):
                continue
            if template_data.get("template") != "listCar":
                continue
            data = template_data.get("data")
            if isinstance(data, dict):
                latest_listcar = data
                break
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
        had more than 1 store, `_save_tool_derived_slots` skips shop_id
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
    def _resolve_shop_id_from_history_template(user_text: str, history: list[dict]) -> str | None:
        """Match a user's list-selection reply against the metadata of the most
        recent assistant message that rendered a `location` template.

        Used as a fallback when prev_tool_data lookup fails (e.g., tool entry
        was evicted, or filter_for_context never persisted it). The template
        metadata is the authoritative source of "what stores were actually
        shown to the user", so matching against it is more robust than against
        raw tool output.

        Expected history msg shape (from chat_history_service.get_history):
            {"role": "assistant", "content": "...",
             "template_data": {"type": "data", "template": "location",
                               "data": {"stores": [{"nameAddress": "티스테이션 한남점", ...}],
                                        "metadata": [{"shopId": "F07782"}]}}}

        Matching strategy:
          1. Ordinal at the start ("1.", "5번", "3)") → metadata[idx-1].shopId
          2. Token-overlap against stores[].nameAddress — only resolves when
             exactly ONE store has the top score
        """
        if not user_text or not history:
            return None

        text = user_text.strip()

        # Find the most recent assistant message with a `location` template.
        # Stop at the first such message; do not fall through to older lists,
        # because the user's selection refers to the latest one shown.
        target_template: dict | None = None
        for msg in reversed(history):
            if msg.get("role") != "assistant":
                continue
            td = msg.get("template_data")
            if not isinstance(td, dict):
                continue
            if td.get("template") != "location":
                continue
            inner = td.get("data")
            if isinstance(inner, dict):
                target_template = inner
            break

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
    def chat(request: TStationChatRequest):
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

        # Create parent "chat" span before classify so ALL sub-calls (classify,
        # agents, qc) are nested under it as children in Langfuse.
        _parent_span = None
        _parent_span_id = None
        from config.tracing import _tracing_enabled, tracer, truncate_for_trace as _truncate_root, set_trace_name as _set_trace_name
        _set_trace_name(last_user_msg[:60] if last_user_msg else None)
        if _tracing_enabled:
            _parent_span = tracer.start_span(
                name="chat",
                trace_context={"trace_id": request.tracing_id},
                input=_truncate_root(last_user_msg),
            )
            _parent_span.update_trace(
                name=(last_user_msg[:60] if last_user_msg else "chat"),
                session_id=request.session_id,
                user_id=request.user_id,
            )
            _parent_span_id = _parent_span.id

        # Step 1: Enrich messages with template_data from Redis history
        enriched_messages = _enrich_messages_with_template_data(
            [dict(msg) for msg in request.messages],
            request.session_id,
        )
        # Step 2: Build messages with user info
        request_with_enriched = TStationChatRequest(
            messages=enriched_messages,
            session_id=request.session_id,
            user_id=request.user_id,
            access_token=request.access_token,
            stream=request.stream,
            user_info=request.user_info,
        )
        messages = TStationChatServiceV2._build_messages_with_user_info(request_with_enriched)

        # Keep at most 20 messages (10 turns) before sending to LLM.
        # Slots and last_user_text are extracted from request.messages (untouched above).
        _MAX_HISTORY_MESSAGES = 20
        if len(messages) > _MAX_HISTORY_MESSAGES:
            dropped = len(messages) - _MAX_HISTORY_MESSAGES
            messages = messages[-_MAX_HISTORY_MESSAGES:]
            logger.info(f"[CHAT_V2] History truncated: dropped {dropped} oldest messages, keeping last {_MAX_HISTORY_MESSAGES}")

        logger.debug(f"[CHAT_V2] Messages: {json.dumps(messages, ensure_ascii=False, indent=2)}")

        # Slot processing: load → extract → classify (with LLM slots) → merge → save → inject
        # Wrapped in try/except so slot failures never block the main chat flow
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

        domains = None
        slot_context = None
        slot_context_with_intent = None
        tool_context = None

        # Defaults hoisted above the try block so the P0 auto-chain gate below
        # can safely inspect them even if slot processing raises.
        last_user_text = ""
        regex_slots = ConversationSlots()
        merged_slots = ConversationSlots()
        goods_no_resolved_this_turn = False

        try:
            chat_history_svc = get_chat_history_service()

            # 1) Load existing slots + tool context from Redis in parallel (independent reads)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _pool:
                _slots_f = _pool.submit(chat_history_svc.get_slots, request.session_id)
                _tool_ctx_f = _pool.submit(chat_history_svc.get_tool_context, request.session_id)
                existing_slots = _slots_f.result()
                prev_tool_data = _tool_ctx_f.result()
            _t_slots = time.perf_counter()
            logger.info(f"[SLOTS] Loaded existing slots: {existing_slots.model_dump()}")

            # 2) Extract regex-based slots from the LATEST user message only
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    last_user_text = msg.get("content", "")
                    break
            regex_slots = ConversationSlots.extract_from_user_text(last_user_text)

            # 3) Merge: existing → regex (full merge with dependency reset)
            merged_slots = existing_slots.merge(regex_slots)
            logger.info(f"[SLOTS] Merged slots: {merged_slots.model_dump()}")

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
                logger.info(
                    f"[SLOTS] Clearing stale pending_intent={merged_slots.pending_intent!r} "
                    f"— user switched back to recommendation"
                )
                merged_slots.pending_intent = None

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
            if (
                merged_slots.pending_intent is not None
                and not turn_has_new_transactional
                and prev_tool_data
            ):
                most_recent_listing_tool: str | None = None
                for entry in reversed(prev_tool_data):
                    tool = entry.get("tool")
                    if tool in ("search_product_tool", "get_products_recommendations_tool"):
                        most_recent_listing_tool = tool
                        break
                if most_recent_listing_tool == "get_products_recommendations_tool":
                    logger.info(
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
                    logger.info(
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
                    history = chat_history_svc.get_history(request.session_id)
                    resolved_tire_size = TStationChatServiceV2._resolve_tire_size_from_history_template(
                        last_user_text, history
                    )
                    if resolved_tire_size:
                        merged_slots.tire_size = resolved_tire_size
                        logger.info(
                            f"[SLOTS] Resolved tire_size={resolved_tire_size!r} from user's "
                            f"vehicle-selection against last `listCar` template metadata"
                        )
                except Exception as e:
                    logger.warning(f"[SLOTS] history tire_size resolver failed: {e}")

            # 3.9) Resolve shop_id from the user's list-selection reply matched against
            # the most recent get_nearby_stores_tool / get_store_list_tool result.
            # `_save_tool_derived_slots` only auto-saves shop_id when the tool returned
            # exactly 1 store — multi-result lists (nearby stores within radius, region
            # searches) leave shop_id=None. When the user then picks a store from that
            # list, STEP 5A Step 4 needs shop_id to call get_store_schedule_tool; without
            # this resolver the LLM tends to re-run get_store_list_tool and stall at the
            # location template instead of progressing to datepick.
            if merged_slots.shop_id is None and prev_tool_data:
                resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_selection(last_user_text, prev_tool_data)
                if resolved_shop_id:
                    merged_slots.shop_id = resolved_shop_id
                    logger.info(
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
                    logger.info(
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
                    history = chat_history_svc.get_history(request.session_id)
                    resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_history_template(
                        last_user_text, history
                    )
                    if resolved_shop_id:
                        merged_slots.shop_id = resolved_shop_id
                        logger.info(
                            f"[SLOTS] Resolved shop_id={resolved_shop_id!r} from user's "
                            f"list-selection against last `location` template metadata"
                        )
                except Exception as e:
                    logger.warning(f"[SLOTS] history shop_id fallback failed: {e}")

            # 4) Save merged slots to Redis
            chat_history_svc.save_slots(request.session_id, merged_slots)

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
                tool_context = TStationChatServiceV2._format_tool_context(prev_tool_data)
                # Cap tool context to avoid consuming too much of the context window
                if len(tool_context) > 8000:
                    tool_context = tool_context[:8000] + "\n... (일부 생략)"
                logger.info(f"[TOOL_CTX] Loaded {len(prev_tool_data)} tool results ({len(tool_context)} chars)")

        except Exception as e:
            logger.exception(f"[SLOTS] Slot processing failed, continuing without slots: {e}")
            slot_context = None
            slot_context_with_intent = None

        # Domain classification (separate from slot processing — must not fail)
        # Fast-path order: goal-based (deterministic checklist) → rule-based
        # (regex) → LLM classifier (multi-intent, conversational context).
        # Each layer returns None to defer to the next.
        # Wrapped in a manual `classify` span so Langfuse shows a single clean
        # node: input=last user text, output=domains. Any nested LLM call from
        # classify_multi_intent attaches under this span via parent_span_id.
        from config.tracing import trace_span as _trace_span, truncate_for_trace as _truncate
        routing_result = None
        with _trace_span(
            "classify",
            trace_id=request.tracing_id,
            parent_span_id=_parent_span_id,
            input=last_user_text,
        ) as _classify_span:
            fast_domains = (
                _support_fast_path(last_user_text)
                or _goal_based_classify(last_user_text, merged_slots)
                or _rule_based_classify(last_user_text, merged_slots)
            )
            if fast_domains is not None:
                domains = fast_domains
                _classify_path = "fast"
                # No routing_result → no CONVERSATION CONTEXT injection (not needed for clear-intent cases)
            else:
                domains, routing_result = _coordinator.classify_multi_intent(
                    messages,
                    session_id=request.session_id,
                    user_id=request.user_id,
                    trace_id=request.tracing_id,
                    parent_span_id=_classify_span.id or _parent_span_id,
                )
                messages = StreamingMultiAgentCoordinator._inject_conversation_context(messages, routing_result)
                _classify_path = "llm"
            _classify_span.update(
                output=_truncate({
                    "domains": [d.value for d in domains],
                    "path": _classify_path,
                    "user_behavior": getattr(routing_result, "user_behavior", None) if routing_result else None,
                    "flow": getattr(routing_result, "flow", None) if routing_result else None,
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
            logger.info(
                f"[COORDINATOR] Post-classification redirect: goods_no={merged_slots.goods_no!r} "
                f"resolved from list-selection + pending_intent={merged_slots.pending_intent!r} "
                f"→ [DISCOVERY] → [TRANSACTION]"
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
        ):
            logger.info(
                f"[COORDINATOR] P0c DISCOVERY→TX redirect: classifier=[DISCOVERY], "
                f"goods_no={merged_slots.goods_no!r} (carried), "
                f"fresh_intent={regex_slots.pending_intent!r}, "
                f"session_id={request.session_id} → domains=[TRANSACTION]"
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
        ):
            domains = [MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION]
            skip_decision = True
            logger.info(
                f"[COORDINATOR] P0 auto-chain gate triggered: "
                f"pending_intent={merged_slots.pending_intent!r} "
                f"(fresh_this_turn={regex_slots.pending_intent!r}), goods_no=None, "
                f"tire_size={merged_slots.tire_size!r}, tire_model={merged_slots.tire_model!r}, "
                f"session_id={request.session_id} → domains=[DISCOVERY, TRANSACTION]"
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
            and merged_slots.goods_no is None
            and (
                merged_slots.tire_size is not None
                or merged_slots.tire_model is not None
                or ConversationSlots.has_product_keyword(last_user_text)
            )
        ):
            domains = [MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION]
            skip_decision = True
            logger.info(
                f"[COORDINATOR] P0b TX→DISC+TX redirect: classifier=[TRANSACTION], "
                f"goods_no=None, tire_size={merged_slots.tire_size!r}, "
                f"tire_model={merged_slots.tire_model!r}, "
                f"has_product_keyword={ConversationSlots.has_product_keyword(last_user_text)}, "
                f"session_id={request.session_id} → domains=[DISCOVERY, TRANSACTION]"
            )

        # Publish the active goal_type to the request-scoped ContextVar consumed
        # by template_mapper. This lets _map_location / _map_product set
        # isBookingFlow=True when a downstream tool call (inventory / price /
        # order) must follow the user's card pick — without threading goal_type
        # through every signature in the agent → mapper chain.
        # ContextVar scoping: set once per request, FastAPI's request lifecycle
        # confines propagation; no manual reset needed.
        from services.tstation.template_mapper import current_goal_type
        current_goal_type.set(merged_slots.goal_type)

        _t_prestream = time.perf_counter()
        logger.info(
            f"[LATENCY] pre-stream — slots={(_t_slots - _t0)*1000:.0f}ms "
            f"classify={(_t_classify - _t_slots)*1000:.0f}ms "
            f"other={(_t_prestream - _t_classify)*1000:.0f}ms "
            f"total={(_t_prestream - _t0)*1000:.0f}ms"
        )
        if request.tracing_id:
            from config.tracing import _tracing_enabled, tracer
            if _tracing_enabled:
                # slots has no manual span — keep as score. classify/agents/qc
                # are now covered by business spans in Langfuse.
                tracer.create_score(trace_id=request.tracing_id, name="latency.slots_ms", value=round((_t_slots - _t0) * 1000))

        # STREAM MODE
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
                    parent_span=_parent_span,
                    parent_span_id=_parent_span_id,
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

            for event_str in TStationChatServiceV2._stream_response_multi(
                messages,
                domains,
                slot_context,
                request.session_id,
                tool_context,
                user_id=request.user_id,
                trace_id=request.tracing_id,
                skip_decision=skip_decision,
                slot_context_with_intent=slot_context_with_intent,
                parent_span=_parent_span,
                parent_span_id=_parent_span_id,
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
    def _stream_response_multi(
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
        slot_context: str | None = None,
        session_id: str | None = None,
        tool_context: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span=None,
        parent_span_id: str | None = None,
        skip_decision: bool = False,
        slot_context_with_intent: str | None = None,
    ):
        """Stream response from multi-agent coordinator with Strict QC Layer."""
        from config.env import settings as _s
        from config.tracing import trace_span as _trace_span, truncate_for_trace as _truncate
        logger.info(
            "[REQUEST_CONFIG] "
            f"default={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL} | "
            f"leading={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_LEADING_AGENT} | "
            f"transaction={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_TRANSACTION_AGENT} | "
            f"qc={_s.AI_DEFAULT_PROVIDER}/{_s.AI_MODEL_QC_AGENT} | "
            f"qc_enabled={_s.AI_QC_ENABLED} | "
            f"session_id={session_id!r}"
        )

        _t_stream_start = time.perf_counter()
        draft_response = ""       # text only — used for history/message sync
        draft_for_qc = ""         # text + template payload — passed to QC only
        source_data_chunks = []
        buffered_data_events: list[dict] = []  # DATA events held until after QC
        tool_context_items = []  # Structured tool results for context preservation
        original_message_events = []  # Hold message events to sync history
        called_tool_names: set[str] = set()
        last_template: str | None = None
        coordinator_done_event = None  # Hold the premature [DONE] event
        agent_count = 0  # Track how many agents have started

        # Detailed latency tracking state
        _lat_tool_start: dict[str, float] = {}
        _lat_agent_start: float | None = None
        _lat_agent_name: str = ""
        _lat_think_start: float | None = None       # reset each time "생각 중..." is seen
        _lat_pre_tool_think_start: float | None = None  # first "생각 중..." per agent
        _lat_first_token_seen: bool = False
        _lat_first_token_time: float | None = None
        _lat_prev_agent_done: float | None = None

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

        _suppress_tokens = False

        for event in _coordinator.stream(
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
        ):
            _lat_now = time.perf_counter()
            event_type = event.get("type")

            # --- INTERCEPT TOKENS (Draft Response only — FE ignores `token` events
            # already and renders text from data.assistantResponse on the final
            # template, so streaming partial tokens to the client adds no UI value
            # and inflates SSE bandwidth. Keep accumulating into draft_response so
            # the local QC / sanitize step still has the full text). ---
            if event_type == "token":
                if event.get("content"):
                    draft_response += event["content"]
                    draft_for_qc += event["content"]
                    if not _lat_first_token_seen:
                        _lat_first_token_seen = True
                        _lat_first_token_time = _lat_now
                        if _lat_think_start is not None:
                            logger.info(f"[LATENCY]   llm_think={(_lat_now - _lat_think_start)*1000:.0f}ms")
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
                    logger.info(f"[LATENCY]   tool={tool_name} {(_lat_now - _lat_tool_start.pop(tool_name))*1000:.0f}ms")
                # Suppress tokens when a "list display" tool is called (card will replace text).
                # Exclude car lookup tools — agent may need to show selection text first.
                _SUPPRESS_ON_TOOLS = {
                    "search_product_tool",
                    "get_products_recommendations_tool",
                    "get_available_coupons_tool",
                    "get_my_coupons_tool",
                    "compare_discount_tool",
                    "search_youtube_video_tool",
                }
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

                continue

            # --- INTERCEPT EARLY DONE EVENT ---
            if event_type == "sub-agent" and event.get("agent") == "[DONE]":
                coordinator_done_event = event
                continue

            # --- INTERCEPT DATA EVENTS (UI Template Agent) ---
            if event_type == "data":
                last_template = event.get("template") or last_template
                event_data = event.get("data", {})
                if isinstance(event_data, dict):
                    if event_data.get("assistantResponse"):
                        assistant_response = event_data["assistantResponse"]
                        source_domain = str(event.get("source_domain", "ui_template")).upper()
                        assistant_msg_event = {
                            "type": "message",
                            "content": assistant_response,
                            "agent": f"[{source_domain} AGENT]",
                        }
                        original_message_events.append(assistant_msg_event)
                        logger.info(
                            f"[COORDINATOR] Captured assistantResponse from data event ({source_domain}): {assistant_response[:50]}..."
                        )
                    # For Path B templates only — LLM wrote the JSON so QC must verify it.
                    # Path A templates (code mapper) are correct by construction; including their
                    # JSON confuses QC into unnecessary text rewrites.
                    if last_template in _LLM_WRITTEN_TEMPLATES:
                        template_payload = {k: v for k, v in event_data.items() if k != "assistantResponse"}
                        if template_payload:
                            draft_for_qc += f"\n\n[Template: {last_template}]\n{json.dumps(template_payload, ensure_ascii=False)}"
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
                        logger.info(f"[LATENCY] decide_next_action={(_lat_now - _lat_prev_agent_done)*1000:.0f}ms")
                    _lat_agent_start = _lat_now
                    _lat_agent_name = _sub_agent
                    _lat_think_start = None
                    _lat_pre_tool_think_start = None
                    _lat_first_token_seen = False
                    _lat_first_token_time = None
                    agent_count += 1
                    if agent_count > 1 and draft_response.strip():
                        logger.info(
                            f"[QC_LAYER] Resetting draft_response for agent #{agent_count} — last agent should produce unified response"
                        )
                        draft_response = ""
                        draft_for_qc = ""
                        original_message_events = []
                        buffered_data_events = []
                elif _sub_status == "done" and _lat_agent_start is not None:
                    _llm_gen = (_lat_now - _lat_first_token_time) * 1000 if _lat_first_token_time else 0
                    logger.info(
                        f"[LATENCY] agent={_lat_agent_name} total={(_lat_now - _lat_agent_start)*1000:.0f}ms "
                        f"llm_gen={_llm_gen:.0f}ms"
                    )
                    _lat_prev_agent_done = _lat_now

            # Track tool_start and LLM think timing from status events
            if event_type == "status":
                _status_val = event.get("status", "")
                if _status_val == "tool_start":
                    if _lat_pre_tool_think_start is not None:
                        logger.info(f"[LATENCY]   llm_pre_tool_think={(_lat_now - _lat_pre_tool_think_start)*1000:.0f}ms")
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

        # 2. QC AGENT
        # Gated by AI_QC_ENABLED. When enabled, fact-checks the draft against
        # filtered tool source data using AI_MODEL_QC_AGENT (lightweight model).
        # AI_QC_PARALLEL=true: yield data events before QC so FE renders immediately;
        # a qc_correction event is emitted afterward only when a correction is needed.
        if draft_response.strip():
            draft_response = _sanitize_response(draft_response)

            _qc_passed = True  # default: no correction needed
            qc_template_corrections: dict | None = None
            _can_apply_json = False
            _parallel_qc = _s.AI_QC_ENABLED and _s.AI_QC_PARALLEL

            # PARALLEL MODE: yield data events immediately so FE can render before QC completes
            if _parallel_qc:
                for buffered_evt in buffered_data_events:
                    yield f"data: {json.dumps(buffered_evt, ensure_ascii=False)}\n\n"

            if _s.AI_QC_ENABLED:
                source_data = "\n\n".join(source_data_chunks) if source_data_chunks else "No tool data retrieved"

                if (
                    _has_factual_claims(draft_for_qc)
                    and called_tool_names
                    and not _should_skip_qc(called_tool_names, last_template)
                ):
                    try:
                        from config.tracing import build_trace_config

                        with _trace_span(
                            "qc",
                            trace_id=trace_id,
                            parent_span_id=parent_span_id,
                            input={
                                "user_query": user_query,
                                "draft": draft_for_qc,
                                "source_data": source_data,
                            },
                        ) as _qc_span:
                            trace_config = build_trace_config(
                                session_id=session_id,
                                user_id=user_id,
                                trace_id=trace_id,
                                parent_span_id=_qc_span.id or parent_span_id,
                                tags=["qc"],
                                prompt_name="qc_agent",
                            )
                            async def _run_qc():
                                return await ainvoke_qc(
                                    QC_LLM, user_query, draft_for_qc, source_data, config=trace_config
                                )
                            qc_result = _anyio_ft.run(_run_qc)
                            qc_result = qc_result.strip()
                            _qc_passed = not qc_result or qc_result.upper() == "PASS"
                            logger.info(f"[QC_LAYER] QC result: {qc_result[:300]}")
                            if not _qc_passed:
                                corrected_text, qc_template_corrections = _parse_qc_output(qc_result)
                                draft_response = corrected_text or draft_response
                                _can_apply_json = qc_template_corrections and last_template in _LLM_WRITTEN_TEMPLATES
                                logger.info(
                                    f"[QC_LAYER] QC corrected the response"
                                    + (f" (+ {len(qc_template_corrections)} JSON field(s) applied)" if _can_apply_json else " (text only)")
                                )
                            else:
                                logger.info("[QC_LAYER] QC passed")
                            _qc_span.update(
                                output=_truncate({
                                    "verdict": "PASS" if _qc_passed else "CORRECTED",
                                    "result": qc_result,
                                }),
                            )
                    except Exception as e:
                        logger.warning(f"[QC_LAYER] QC failed, using original draft: {e}")

            if _parallel_qc:
                # Emit a correction patch only when QC found issues; FE applies it over the already-rendered response
                if not _qc_passed:
                    correction_evt: dict = {"type": "qc_correction", "assistantResponse": draft_response}
                    if _can_apply_json:
                        correction_evt["template"] = last_template
                        correction_evt["corrections"] = qc_template_corrections
                    yield f"data: {json.dumps(correction_evt, ensure_ascii=False)}\n\n"
                    logger.info("[QC_LAYER] Parallel mode: emitted qc_correction patch")
            else:
                # SEQUENTIAL (default): yield buffered DATA events with corrections applied
                for buffered_evt in buffered_data_events:
                    if not _qc_passed:
                        evt_data = buffered_evt.get("data", {})
                        if isinstance(evt_data, dict):
                            if "assistantResponse" in evt_data:
                                evt_data["assistantResponse"] = draft_response
                            if _can_apply_json:
                                for k, v in qc_template_corrections.items():
                                    if k != "assistantResponse" and k in evt_data:
                                        evt_data[k] = v
                    yield f"data: {json.dumps(buffered_evt, ensure_ascii=False)}\n\n"

            if original_message_events:
                final_msg_event = original_message_events[-1]
                final_msg_event["content"] = draft_response
                yield f"data: {json.dumps(final_msg_event, ensure_ascii=False)}\n\n"
        else:
            # FALLBACK HISTORY SYNC: If no text was generated, only yield message events
            # if they actually contain text. We DO NOT want to save empty assistant
            # messages to Redis, as it pollutes the LLM's future context window.
            for msg_event in original_message_events:
                if msg_event.get("content", "").strip():  # <-- ONLY yield if it has text
                    yield f"data: {json.dumps(msg_event, ensure_ascii=False)}\n\n"

        # 4. PERSIST TOOL CONTEXT for next turn (only overwrite when new tool results exist)
        if session_id and tool_context_items:
            try:
                from services.tstation.chat_history_service import get_chat_history_service

                get_chat_history_service().save_tool_context(session_id, tool_context_items)
            except Exception as e:
                logger.warning(f"[TOOL_CTX] Failed to save tool context: {e}")

        _t_qc = time.perf_counter()
        logger.info(
            f"[LATENCY] stream — agents={(_t_agents - _t_stream_start)*1000:.0f}ms "
            f"qc={(_t_qc - _t_agents)*1000:.0f}ms "
            f"total={(_t_qc - _t_stream_start)*1000:.0f}ms"
        )
        # agents / qc / stream_total latency is now tracked via manual Langfuse
        # spans ("agent:*", "qc") — no need to submit redundant scores.

        if parent_span is not None:
            from config.tracing import truncate_for_trace as _truncate_root_out
            _last_user = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
            )
            parent_span.update_trace(
                name=(_last_user[:60] if _last_user else "chat"),
                output=_truncate_root_out(draft_response),
            )
            parent_span.end()

        # 5. FINALIZE THE STREAM
        if coordinator_done_event:
            yield f"data: {json.dumps(coordinator_done_event, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
