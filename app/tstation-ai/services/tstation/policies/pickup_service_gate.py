"""Intent gate for Smart Pickup / pickup-service questions."""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from textwrap import dedent
from typing import Literal

from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel, Field

from config.env import settings

logger = logging.getLogger(__name__)


PickupServiceIntent = Literal[
    "pickup_howto",
    "pickup_availability",
    "pickup_status",
    "pickup_request_context",
    "none",
]


class PickupServiceGateDecision(BaseModel):
    intent: PickupServiceIntent = Field(description="Classified pickup-service intent.")
    is_pickup: bool = Field(description="Whether the current user turn is about pickup service.")
    reason: str = Field(description="Short English reason for traces/logs only.")


_PICKUP_CHEAP_TRIGGER_RE = re.compile(
    r"픽업\s*서비스|픽업서비스|스마트\s*픽업|스마트픽업|타이어\s*픽업|"
    r"차\s*가지러|차량\s*수거|방문\s*픽업|직접\s*가지러|"
    r"집\s*앞|집앞|데려다|탁송|픽업\s*기사|픽업기사|기사",
    re.IGNORECASE,
)
_PICKUP_STATUS_RE = re.compile(
    r"(?:픽업\s*기사|픽업기사|기사님|기사).{0,12}(?:어디|위치|도착|언제|오고|오는|진행|상태)"
    r"|(?:어디|위치|도착|언제|오고|오는|진행|상태).{0,12}(?:픽업\s*기사|픽업기사|기사님|기사)",
    re.IGNORECASE,
)
_PICKUP_HOWTO_RE = re.compile(r"신청|방법|어떻게|어디서|접수|이용", re.IGNORECASE)
_PICKUP_REQUEST_CONTEXT_RE = re.compile(
    r"차\s*가지러|차량\s*수거|직접\s*가지러|회사로\s*차|집\s*앞까지|집앞까지|데려다|탁송|수거해서",
    re.IGNORECASE,
)
_PICKUP_AVAILABILITY_RE = re.compile(
    r"가능|돼|되나|될까|할\s*수|올\s*수|거리|몇\s*키로|몇\s*km|지역|매장|운영|제공",
    re.IGNORECASE,
)


def deterministic_pickup_service_gate_decision(user_text: str) -> PickupServiceGateDecision | None:
    """Return deterministic decisions for high-confidence pickup expressions."""
    text = (user_text or "").strip()
    if not text:
        return None
    if not _PICKUP_CHEAP_TRIGGER_RE.search(text):
        return PickupServiceGateDecision(
            intent="none",
            is_pickup=False,
            reason="No pickup cheap trigger.",
        )
    if _PICKUP_STATUS_RE.search(text):
        return PickupServiceGateDecision(
            intent="pickup_status",
            is_pickup=True,
            reason="Pickup driver status/location expression.",
        )
    if _PICKUP_REQUEST_CONTEXT_RE.search(text):
        return PickupServiceGateDecision(
            intent="pickup_request_context",
            is_pickup=True,
            reason="Customer asks for vehicle pickup and return/delivery service.",
        )
    if _PICKUP_HOWTO_RE.search(text):
        return PickupServiceGateDecision(
            intent="pickup_howto",
            is_pickup=True,
            reason="Pickup expression with application/how-to wording.",
        )
    if _PICKUP_AVAILABILITY_RE.search(text):
        return PickupServiceGateDecision(
            intent="pickup_availability",
            is_pickup=True,
            reason="Pickup expression with availability/coverage wording.",
        )
    return None


@lru_cache(maxsize=1)
def _pickup_gate_model():
    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_MINI}",
        streaming=False,
        request_timeout=8,
    )
    return llm.with_structured_output(PickupServiceGateDecision)


def decide_pickup_service_gate(
    *,
    user_text: str,
    recent_context: str = "",
) -> PickupServiceGateDecision:
    """Classify pickup-service intent for the current turn.

    The LLM fallback is only used after a cheap pickup trigger exists, so generic
    "신청 방법 알려줘" style questions do not get hijacked into pickup.
    """
    deterministic = deterministic_pickup_service_gate_decision(user_text)
    if deterministic is not None:
        return deterministic

    text = (user_text or "").strip()
    if not _PICKUP_CHEAP_TRIGGER_RE.search(text):
        return PickupServiceGateDecision(intent="none", is_pickup=False, reason="No pickup cheap trigger.")

    prompt = dedent(f"""
    You are an intent gate for a Korean tire-commerce chatbot.
    Classify whether the CURRENT user message is about Smart Pickup / pickup service.

    Valid intents:
    - pickup_howto: how to apply/register/use pickup service
    - pickup_availability: whether pickup is possible, by region/store/distance/coverage
    - pickup_status: pickup driver location, arrival time, progress/status
    - pickup_request_context: user asks the service to pick up the car, replace tires, and return/drop it off
    - none: not about pickup service

    Important:
    - Do NOT classify generic "신청 방법 알려줘" as pickup unless pickup-related words are present.
    - Return reason only for trace/debug; it is not user-facing.

    Current user message:
    {text}

    Recent context:
    {recent_context[-1000:]}
    """).strip()

    try:
        decision = _pickup_gate_model().invoke(prompt)
        if isinstance(decision, PickupServiceGateDecision):
            return decision
        return PickupServiceGateDecision.model_validate(decision)
    except Exception as exc:
        logger.warning("[PICKUP_SERVICE_GATE] LLM decision failed; returning none: %s", exc)
        return PickupServiceGateDecision(intent="none", is_pickup=False, reason="LLM gate failed.")

