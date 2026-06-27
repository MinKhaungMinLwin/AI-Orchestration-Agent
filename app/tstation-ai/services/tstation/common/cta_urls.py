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

from dataclasses import dataclass
from typing import Final, Mapping
from urllib.parse import urlparse, urlunparse

from config.env import settings
from services.tstation.common.tstation_be_client import get_tstation_origin_host


_PC: Final[str] = settings.TSTATION_WEB_PC_BASE.rstrip("/")
_MOBILE: Final[str] = settings.TSTATION_WEB_MOBILE_BASE.rstrip("/")
_PROD_PC: Final[str] = "https://www.tstation.com"
_PROD_MOBILE: Final[str] = "https://m.tstation.com"
_PC_HOSTS: Final[set[str]] = {
    "wwwqa.tstation.com",
    "www.tstation.com",
    "bizqa.tstation.com",
    "biz.tstation.com",
}
_MOBILE_HOSTS: Final[set[str]] = {
    "mqa.tstation.com",
    "m.tstation.com",
    "mbiz.tstation.com",
}
_TSTATION_CTA_HOSTS: Final[set[str]] = {
    *_PC_HOSTS,
    *_MOBILE_HOSTS,
}


@dataclass(frozen=True)
class _CTAPathPair:
    key: str
    pc_path: str
    mobile_path: str
    mobile_verified: bool = False


def _path_pair(key: str, pc_path: str, mobile_path: str | None = None, *, mobile_verified: bool = False) -> _CTAPathPair:
    return _CTAPathPair(
        key=key,
        pc_path=pc_path,
        mobile_path=mobile_path or pc_path,
        mobile_verified=mobile_verified,
    )


_CTA_PATH_PAIRS: Final[tuple[_CTAPathPair, ...]] = (
    _path_pair("CART", "/cart"),
    _path_pair("ORDER_HISTORY", "/mypage/tstation/order-history"),
    _path_pair("ORDER_HISTORY_DETAIL", "/mypage/tstation/order-history/detail/<ord_no>"),
    _path_pair("STORE_SERVICE_HISTORY", "/mypage/tstation/custservice/carservice-hist"),
    _path_pair("GOODS_REVIEW", "/mypage/activity/goods-review"),
    _path_pair("KEEP_SERVICE_HIST", "/mypage/tstation/custservice/keepservice-hist"),
    _path_pair("PROMOTION_EVENT_LIST", "/promotion/event-list"),
    _path_pair("PROMOTION_PAST_EVENT_LIST", "/promotion/past-event-list"),
    _path_pair(
        "MY_COUPON_LIST",
        "/mypage/tstation/coupon/couponList",
        "/coupon/myCouponList",
        mobile_verified=True,
    ),
    _path_pair(
        "WARRANTY_MAIN",
        "/mypage/tstation/warranty/main",
        "/mypage/tstation/warranty",
        mobile_verified=True,
    ),
    _path_pair("REMINDING_ALARM", "/membership/reminding-alarm"),
    _path_pair("TIRE_CHECK", "/mypage/tireTest/tireCheck.do"),
    _path_pair("TIRE_CHECK_RESULT_LIST", "/mypage/tireTest/tireCheckResultList.do"),
    _path_pair("SMART_PICKUP", "/membership/dashboard/membership_smartPickup"),
    _path_pair("SMART_PICKUP_LIST", "/mypage/tstation/reservation/pickupList"),
    _path_pair("MEMBERSHIP_DASHBOARD", "/membership/dashboard"),
    _path_pair("MEMBERSHIP_BENEFIT", "/membership/dashboard/benefit"),
    _path_pair("STORE_DETAIL", "/store/locals/<shop_seq>"),
)
CTA_MOBILE_PATHS_NEED_CONFIRMATION: Final[tuple[str, ...]] = tuple(
    pair.key for pair in _CTA_PATH_PAIRS if not pair.mobile_verified
)


class CTAUrls:
    """Concrete URLs written into LLM outputs and template cards.

    Group A (no parameters) — emitted as-is.
    Group B (LLM placeholders) — agent prompt instructs the model to substitute.
    """

    # Group A — fixed paths
    CART: Final[str] = f"{_PC}/cart"
    ORDER_HISTORY: Final[str] = f"{_PC}/mypage/tstation/order-history"
    STORE_SERVICE_HISTORY: Final[str] = f"{_PC}/mypage/tstation/custservice/carservice-hist"
    GOODS_REVIEW: Final[str] = f"{_PC}/mypage/activity/goods-review"
    KEEP_SERVICE_HIST: Final[str] = f"{_PC}/mypage/tstation/custservice/keepservice-hist"
    PROMOTION_EVENT_LIST: Final[str] = f"{_PC}/promotion/event-list"
    PROMOTION_PAST_EVENT_LIST: Final[str] = f"{_PC}/promotion/past-event-list"
    MY_COUPON_LIST_PC: Final[str] = f"{_PC}/mypage/tstation/coupon/couponList"
    MY_COUPON_LIST_MOBILE: Final[str] = f"{_MOBILE}/coupon/myCouponList"
    WARRANTY_MAIN: Final[str] = f"{_PC}/mypage/tstation/warranty/main"
    REMINDING_ALARM: Final[str] = f"{_PC}/membership/reminding-alarm"
    TIRE_CHECK: Final[str] = f"{_PC}/mypage/tireTest/tireCheck.do"
    TIRE_CHECK_RESULT_LIST: Final[str] = f"{_PC}/mypage/tireTest/tireCheckResultList.do"
    SMART_PICKUP: Final[str] = f"{_PC}/membership/dashboard/membership_smartPickup"
    SMART_PICKUP_LIST: Final[str] = f"{_PC}/mypage/tstation/reservation/pickupList"
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
    "__URL_GOODS_REVIEW__": CTAUrls.GOODS_REVIEW,
    "__URL_KEEP_SERVICE_HIST__": CTAUrls.KEEP_SERVICE_HIST,
    "__URL_PROMOTION_EVENT_LIST__": CTAUrls.PROMOTION_EVENT_LIST,
    "__URL_PROMOTION_PAST_EVENT_LIST__": CTAUrls.PROMOTION_PAST_EVENT_LIST,
    "__URL_MY_COUPON_LIST_PC__": CTAUrls.MY_COUPON_LIST_PC,
    "__URL_MY_COUPON_LIST_MOBILE__": CTAUrls.MY_COUPON_LIST_MOBILE,
    "__URL_WARRANTY_MAIN__": CTAUrls.WARRANTY_MAIN,
    "__URL_REMINDING_ALARM__": CTAUrls.REMINDING_ALARM,
    "__URL_TIRE_CHECK__": CTAUrls.TIRE_CHECK,
    "__URL_TIRE_CHECK_RESULT_LIST__": CTAUrls.TIRE_CHECK_RESULT_LIST,
    "__URL_SMART_PICKUP__": CTAUrls.SMART_PICKUP,
    "__URL_SMART_PICKUP_LIST__": CTAUrls.SMART_PICKUP_LIST,
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


def _path_matches_template(path: str, template: str) -> bool:
    if "<" not in template:
        return path.rstrip("/") == template.rstrip("/")
    path_parts = path.strip("/").split("/")
    template_parts = template.strip("/").split("/")
    if len(path_parts) != len(template_parts):
        return False
    return all(
        template_part.startswith("<") and template_part.endswith(">") or path_part == template_part
        for path_part, template_part in zip(path_parts, template_parts, strict=True)
    )


def _render_path_from_template(path: str, source_template: str, target_template: str) -> str:
    if "<" not in source_template and "<" not in target_template:
        return target_template
    path_parts = path.strip("/").split("/")
    source_parts = source_template.strip("/").split("/")
    values: dict[str, str] = {}
    for path_part, source_part in zip(path_parts, source_parts, strict=True):
        if source_part.startswith("<") and source_part.endswith(">"):
            values[source_part] = path_part
    rendered_parts = [
        values.get(target_part, target_part)
        for target_part in target_template.strip("/").split("/")
    ]
    return "/" + "/".join(rendered_parts)


def _match_cta_path(path: str) -> tuple[_CTAPathPair, str] | None:
    for pair in _CTA_PATH_PAIRS:
        if _path_matches_template(path, pair.pc_path):
            return pair, pair.pc_path
        if _path_matches_template(path, pair.mobile_path):
            return pair, pair.mobile_path
    return None


def _origin_channel(origin_host: str | None) -> str | None:
    host = str(origin_host or "").strip().lower()
    if host in _MOBILE_HOSTS:
        return "mobile"
    if host in _PC_HOSTS:
        return "pc"
    return None


def _fallback_channel_for_url(parsed_host: str, matched_pair: _CTAPathPair, source_template: str) -> str:
    if parsed_host in _MOBILE_HOSTS:
        return "mobile"
    if parsed_host in _PC_HOSTS:
        return "pc"
    if source_template == matched_pair.mobile_path and matched_pair.mobile_path != matched_pair.pc_path:
        return "mobile"
    return "pc"


def _target_base_for_channel(channel: str, origin_host: str | None) -> str:
    origin = str(origin_host or "").strip().lower()
    if origin in _TSTATION_CTA_HOSTS:
        return f"https://{origin}"
    return _PROD_MOBILE if channel == "mobile" else _PROD_PC


def rebase_tstation_url_to_origin(url: str | None) -> str:
    """Map known CTA URLs to the current request origin channel and host."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    origin_host = str(get_tstation_origin_host() or "").strip().lower()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw
    parsed_host = (parsed.hostname or "").lower()
    if parsed_host not in _TSTATION_CTA_HOSTS:
        return raw
    matched = _match_cta_path(parsed.path)
    if matched is None:
        channel = _origin_channel(origin_host) or ("mobile" if parsed_host in _MOBILE_HOSTS else "pc")
        target_base = urlparse(_target_base_for_channel(channel, origin_host))
        return urlunparse(parsed._replace(scheme=target_base.scheme, netloc=target_base.netloc))
    matched_pair, source_template = matched
    channel = _origin_channel(origin_host) or _fallback_channel_for_url(parsed_host, matched_pair, source_template)
    target_template = matched_pair.mobile_path if channel == "mobile" else matched_pair.pc_path
    target_path = _render_path_from_template(parsed.path, source_template, target_template)
    target_base = urlparse(_target_base_for_channel(channel, origin_host))
    return urlunparse(parsed._replace(scheme=target_base.scheme, netloc=target_base.netloc, path=target_path))
