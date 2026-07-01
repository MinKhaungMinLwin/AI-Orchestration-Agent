"""User-request/result alignment helpers for deterministic template responses."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PriceRangeRequest:
    min_price: int | None = None
    max_price: int | None = None
    label: str = ""


def product_price_alignment_notice(
    *,
    user_text: str,
    products: Sequence[Mapping[str, Any]],
    tool_args: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Return a short caveat when product card prices do not satisfy the requested price range."""

    request = _price_range_request(user_text=user_text, tool_args=tool_args)
    if request is None:
        return ""

    prices = [_positive_int(product.get("price")) for product in products]
    prices = [price for price in prices if price is not None]
    if not prices:
        return ""
    if any(_price_satisfies(price, request) for price in prices):
        return ""

    requested_label = request.label or _format_price_request(request)
    direction = _fallback_price_direction(prices=prices, request=request)
    return f"요청하신 {requested_label} 상품은 현재 결과에 없어서, 확인 가능한 {direction} 상품을 보여드릴게요."


def _price_range_request(
    *,
    user_text: str,
    tool_args: Sequence[Mapping[str, Any]],
) -> PriceRangeRequest | None:
    text_request = _price_range_from_text(user_text)
    if text_request is not None:
        return text_request

    for args in reversed(list(tool_args)):
        min_price = _positive_int(args.get("min_price"))
        max_price = _positive_int(args.get("max_price"))
        if min_price is not None or max_price is not None:
            return PriceRangeRequest(
                min_price=min_price,
                max_price=max_price,
                label=_format_price_request(PriceRangeRequest(min_price=min_price, max_price=max_price)),
            )
    return None


def _price_range_from_text(text: str) -> PriceRangeRequest | None:
    normalized = re.sub(r"\s+", "", text or "")
    if not normalized:
        return None

    match = re.search(r"(?P<low>\d{1,3})만원(?:대|선)", normalized)
    if match:
        low = int(match.group("low")) * 10_000
        label = f"{match.group('low')}만원대"
        return PriceRangeRequest(min_price=low, max_price=low + 99_999, label=label)

    match = re.search(r"(?P<low>\d{1,3})만원(?:부터|이상)[~\-]?(?P<high>\d{1,3})?만원?(?:까지|이하)?", normalized)
    if match:
        low = int(match.group("low")) * 10_000
        high = int(match.group("high")) * 10_000 if match.group("high") else None
        label = f"{match.group('low')}만원~{match.group('high')}만원" if match.group("high") else f"{match.group('low')}만원 이상"
        return PriceRangeRequest(min_price=low, max_price=high, label=label)

    match = re.search(r"(?P<low>\d{1,3})만원[~\-](?P<high>\d{1,3})만원", normalized)
    if match:
        return PriceRangeRequest(
            min_price=int(match.group("low")) * 10_000,
            max_price=int(match.group("high")) * 10_000,
            label=f"{match.group('low')}만원~{match.group('high')}만원",
        )

    match = re.search(r"(?P<price>\d{1,3})만원(?:이하|까지|안쪽|미만)", normalized)
    if match:
        return PriceRangeRequest(max_price=int(match.group("price")) * 10_000, label=f"{match.group('price')}만원 이하")

    match = re.search(r"(?P<price>\d{1,3})만원(?:이상|부터)", normalized)
    if match:
        return PriceRangeRequest(min_price=int(match.group("price")) * 10_000, label=f"{match.group('price')}만원 이상")

    return None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _price_satisfies(price: int, request: PriceRangeRequest) -> bool:
    if request.min_price is not None and price < request.min_price:
        return False
    if request.max_price is not None and price > request.max_price:
        return False
    return True


def _fallback_price_direction(*, prices: Sequence[int], request: PriceRangeRequest) -> str:
    if request.min_price is not None and max(prices) < request.min_price:
        return "더 낮은 가격대"
    if request.max_price is not None and min(prices) > request.max_price:
        return "더 높은 가격대"
    return "다른 가격대"


def _format_price_request(request: PriceRangeRequest) -> str:
    min_price = request.min_price
    max_price = request.max_price
    if min_price is not None and max_price == min_price + 99_999 and min_price % 10_000 == 0:
        return f"{min_price // 10_000}만원대"
    if min_price is not None and max_price is not None:
        return f"{min_price // 10_000}만원~{max_price // 10_000}만원"
    if max_price is not None:
        return f"{max_price // 10_000}만원 이하"
    if min_price is not None:
        return f"{min_price // 10_000}만원 이상"
    return "요청 가격대"
