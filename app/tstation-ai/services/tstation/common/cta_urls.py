"""Centralized CTA URLs for chatbot quickReply chips, qnaComplete redirects, and template cards.

Domain bases (PC + mobile) come from `settings.TSTATION_WEB_PC_BASE` /
`TSTATION_WEB_MOBILE_BASE` so a single env-var change flips QA → prod.

Two usage paths:

1. Agent system prompts (LLM emits the URL string literally):
   - Write `__URL_FOO__` sentinel in the prompt template.
   - Call `expand_url_sentinels(template)` once inside `get_*_system_prompt()`.
   - Substitution happens at agent instantiation (router.py module load),
     so there is zero per-request overhead.

2. Python runtime code (e.g., template_mapper, qnaComplete payload builders):
   - Import `CTAUrls` and reference attributes directly:
     `CTAUrls.MY_COUPON_LIST_PC`, `CTAUrls.ORDER_HISTORY`, etc.

LLM-substituted placeholders like `<ord_no>` and `<shop_seq>` are part of the
URL string by design. The agent prompt instructs the model to replace them
with real values from tool outputs before emitting the chip JSON.
"""
from __future__ import annotations

from typing import Final, Mapping

from config.env import settings


_PC: Final[str] = settings.TSTATION_WEB_PC_BASE.rstrip("/")
_MOBILE: Final[str] = settings.TSTATION_WEB_MOBILE_BASE.rstrip("/")


class CTAUrls:
    """Concrete URLs written into LLM outputs and template cards.

    Group A (no parameters) — emitted as-is.
    Group B (LLM placeholders) — agent prompt instructs the model to substitute.
    """

    # Group A — fixed paths
    CART: Final[str] = f"{_PC}/cart"
    ORDER_HISTORY: Final[str] = f"{_PC}/mypage/tstation/order-history"
    STORE_SERVICE_HISTORY: Final[str] = f"{_PC}/mypage/tstation/custservice/carservice-hist"
    PROMOTION_EVENT_LIST: Final[str] = f"{_PC}/promotion/event-list"
    PROMOTION_PAST_EVENT_LIST: Final[str] = f"{_PC}/promotion/past-event-list"
    MY_COUPON_LIST_PC: Final[str] = f"{_PC}/mypage/tstation/coupon/couponList"
    MY_COUPON_LIST_MOBILE: Final[str] = f"{_MOBILE}/coupon/myCouponList"
    WARRANTY_MAIN: Final[str] = f"{_PC}/mypage/tstation/warranty/main"
    REMINDING_ALARM: Final[str] = f"{_PC}/membership/reminding-alarm"
    TIRE_CHECK_RESULT_LIST: Final[str] = f"{_PC}/mypage/tireTest/tireCheckResultList.do"
    SMART_PICKUP: Final[str] = f"{_PC}/membership/dashboard/membership_smartPickup"
    MEMBERSHIP_DASHBOARD: Final[str] = f"{_PC}/membership/dashboard"
    MEMBERSHIP_BENEFIT: Final[str] = f"{_PC}/membership/dashboard/benefit"

    # Group B — contain LLM placeholders (<ord_no>, <shop_seq>)
    ORDER_HISTORY_DETAIL: Final[str] = f"{_PC}/mypage/tstation/order-history/detail/<ord_no>"
    STORE_DETAIL: Final[str] = f"{_PC}/store/locals/<shop_seq>"


# Sentinel → URL mapping. Use only inside prompt template strings.
# Agent prompts contain `__URL_FOO__` literals; expand_url_sentinels() replaces them.
_SENTINEL_MAP: Mapping[str, str] = {
    "__URL_ORDER_HISTORY__": CTAUrls.ORDER_HISTORY,
    "__URL_CART__": CTAUrls.CART,
    "__URL_ORDER_HISTORY_DETAIL__": CTAUrls.ORDER_HISTORY_DETAIL,
    "__URL_STORE_DETAIL__": CTAUrls.STORE_DETAIL,
    "__URL_STORE_SERVICE_HISTORY__": CTAUrls.STORE_SERVICE_HISTORY,
    "__URL_PROMOTION_EVENT_LIST__": CTAUrls.PROMOTION_EVENT_LIST,
    "__URL_PROMOTION_PAST_EVENT_LIST__": CTAUrls.PROMOTION_PAST_EVENT_LIST,
    "__URL_MY_COUPON_LIST_PC__": CTAUrls.MY_COUPON_LIST_PC,
    "__URL_MY_COUPON_LIST_MOBILE__": CTAUrls.MY_COUPON_LIST_MOBILE,
    "__URL_WARRANTY_MAIN__": CTAUrls.WARRANTY_MAIN,
    "__URL_REMINDING_ALARM__": CTAUrls.REMINDING_ALARM,
    "__URL_TIRE_CHECK_RESULT_LIST__": CTAUrls.TIRE_CHECK_RESULT_LIST,
    "__URL_SMART_PICKUP__": CTAUrls.SMART_PICKUP,
    "__URL_MEMBERSHIP_DASHBOARD__": CTAUrls.MEMBERSHIP_DASHBOARD,
    "__URL_MEMBERSHIP_BENEFIT__": CTAUrls.MEMBERSHIP_BENEFIT,
}


def expand_url_sentinels(text: str) -> str:
    """Substitute every `__URL_*__` sentinel with its concrete URL.

    Intended for prompt templates. Call once per `get_*_system_prompt()`;
    results are stable across requests once env is fixed at process start.
    """
    for sentinel, url in _SENTINEL_MAP.items():
        text = text.replace(sentinel, url)
    return text
