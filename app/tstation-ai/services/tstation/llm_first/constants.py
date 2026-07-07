from __future__ import annotations

from typing import Final

from config.env import settings

_PC: Final[str] = settings.TSTATION_WEB_PC_BASE.rstrip("/")
_MOBILE: Final[str] = settings.TSTATION_WEB_MOBILE_BASE.rstrip("/")

MY_COUPON_LIST_LINK: Final[dict[str, str]] = {
    "pc": f"{_PC}/mypage/tstation/coupon/couponList",
    "mobile": f"{_MOBILE}/coupon/myCouponList",
}
PROMOTION_EVENT_LIST_URL: Final[str] = f"{_PC}/promotion/event-list"
