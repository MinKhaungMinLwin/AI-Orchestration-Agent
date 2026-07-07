"""Canned policy-guard responses — texts ported verbatim from V2.

Only the DATA lives here (text + chips). The trigger decision is made by
the router LLM (see prompts/router.py); no matching logic in this file.
"""

from datetime import date, timedelta

from pydantic import BaseModel

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.chat_v3.router.schemas import GuardId


class Guard(BaseModel):
    id: str
    text: str
    chips: list[dict]
    predicted_domains: list[str]


_STATIC_GUARDS: dict[GuardId, Guard] = {
    GuardId.PII: Guard(
        id="pii",
        text=(
            "보안상 비밀번호, 카드번호, 주민번호, 여권번호, 연락처 같은 개인정보나 민감정보는 "
            "채팅창에 표시하거나 다른 형태로 변환해 드릴 수 없어요."
        ),
        chips=[{"label": "1:1 문의하기", "domain": "SUPPORT"}, {"label": "마이페이지 확인", "domain": "SUPPORT"}],
        predicted_domains=["SUPPORT"],
    ),
    GuardId.PRIVACY_CONTACT: Guard(
        id="privacy_contact",
        text=(
            "관리자나 직원의 개인 휴대폰 번호는 개인정보라 안내해드릴 수 없어요. "
            "문의나 불편사항은 공식 고객센터 또는 1:1 문의로 접수해 주세요."
        ),
        chips=[
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
            {"label": "고객센터 안내", "domain": "SUPPORT"},
            {"label": "매장 찾기", "domain": "TRANSACTION"},
        ],
        predicted_domains=["SUPPORT", "TRANSACTION"],
    ),
    GuardId.REGIONAL_CHEAPEST: Guard(
        id="regional_cheapest",
        text=(
            "매장·시기·상품에 따라 적용되는 프로모션이 달라 '제일 저렴한 매장' 을 "
            "한 곳으로 안내드리기 어려워요 😊\n\n"
            "다만 **온라인 구매 시 무료배송 + 무료장착**이고, 원하시는 상품을 선택하시면 "
            "실시간 할인가를 바로 확인하실 수 있어요."
        ),
        chips=[
            {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
            {"label": "가까운 매장 찾기", "domain": "TRANSACTION"},
            {"label": "진행 중인 이벤트", "domain": "DISCOVERY"},
        ],
        predicted_domains=["DISCOVERY", "TRANSACTION"],
    ),
    GuardId.UNSUPPORTED_BRAND: Guard(
        id="unsupported_brand",
        text=(
            "현재 챗봇에서 바로 안내 가능한 브랜드는 한국타이어, 라우펜, 미쉐린, 피렐리, "
            "브리지스톤, 콘티넨탈, 굿이어예요.\n"
            "말씀하신 브랜드는 현재 상품 검색/추천 대상이 아니어서 가격·재고·장착 가능 여부를 "
            "확정 안내하기 어려워요. 매장별 별도 취급 여부는 매장에 직접 확인해 주세요."
        ),
        chips=[
            {"label": "지원 브랜드 상품 보기", "domain": "DISCOVERY"},
            {"label": "다른 브랜드 추천", "domain": "DISCOVERY"},
        ],
        predicted_domains=["DISCOVERY"],
    ),
    GuardId.EXTERNAL_PRICE: Guard(
        id="external_price",
        text=(
            "다나와/구글/네이버 같은 외부 사이트의 실시간 최저가를 제가 직접 수집하거나 비교할 수는 없어요.\n"
            "대신 T'Station 내부 판매가와 회원 쿠폰 기준 최저 혜택가는 확인해 드릴 수 있습니다."
        ),
        chips=[
            {"label": "T'Station 가격 확인", "domain": "TRANSACTION"},
            {"label": "회원 쿠폰 적용가 보기", "domain": "TRANSACTION"},
            {"label": "다른 사이즈 확인", "domain": "DISCOVERY"},
        ],
        predicted_domains=["TRANSACTION", "DISCOVERY"],
    ),
    GuardId.PAST_EVENT_PAGE: Guard(
        id="past_event_page",
        text="지난 이벤트와 종료된 이벤트는 티스테이션 이벤트의 '지난 이벤트' 페이지에서 확인하실 수 있어요.",
        chips=[
            {"label": "지난 이벤트 보기", "url": CTAUrls.PROMOTION_PAST_EVENT_LIST, "domain": "DISCOVERY"},
            {"label": "진행 중인 이벤트", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
        ],
        predicted_domains=["DISCOVERY"],
    ),
    GuardId.COUPON_ISSUE_REQUEST: Guard(
        id="coupon_issue_request",
        text=(
            "고객님, 현재 채팅에서는 쿠폰을 직접 발급해 드릴 수 없어요. "
            "쿠폰 받기는 쿠폰함에서 확인하고 진행하실 수 있습니다."
        ),
        chips=[
            {"label": "쿠폰함 바로가기", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
        ],
        predicted_domains=["TRANSACTION"],
    ),
    GuardId.EXPIRED_COUPON_OR_EVENT: Guard(
        id="expired_coupon_or_event",
        text=(
            "만료된 쿠폰이나 종료된 이벤트 혜택은 원칙적으로 원복 또는 재사용이 어렵습니다. "
            "자세한 확인이 필요하시면 1:1 문의로 접수해 주세요."
        ),
        chips=[
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
            {"label": "내 쿠폰함", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
        ],
        predicted_domains=["SUPPORT", "TRANSACTION"],
    ),
    GuardId.NONEXISTENT_BENEFIT: Guard(
        id="nonexistent_benefit",
        text=(
            "확인되지 않은 VIP/블랙카드/50% 전용 혜택이나 할인 링크는 제공할 수 없어요. "
            "공식 쿠폰함과 진행 중인 이벤트에서 확인되는 혜택만 안내드릴 수 있습니다."
        ),
        chips=[
            {"label": "내 쿠폰함", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
            {"label": "진행 중인 이벤트", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ],
        predicted_domains=["TRANSACTION", "DISCOVERY", "SUPPORT"],
    ),
    GuardId.VEHICLE_TYPE_COMPATIBILITY: Guard(
        id="vehicle_type_compatibility",
        text=(
            "SUV에는 승용차/세단용 타이어를 임의로 장착하는 건 권장하지 않아요. "
            "같은 사이즈처럼 보여도 하중지수와 설계 기준이 다를 수 있어서, "
            "차량 규격에 맞는 SUV용 또는 SUV 호환 타이어로 확인하는 게 안전합니다."
        ),
        chips=[
            {"label": "SUV용 추천", "domain": "DISCOVERY"},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 차량으로 확인", "domain": "DISCOVERY"},
        ],
        predicted_domains=["DISCOVERY"],
    ),
    GuardId.PICKUP_STATUS: Guard(
        id="pickup_status",
        text=(
            "픽업기사의 실시간 위치나 도착 시간은 챗봇에서 바로 확인하기 어려워요. "
            "신청하신 픽업/딜리버리 진행 현황은 아래 '픽업서비스 내역'에서 확인해 주세요."
        ),
        chips=[{"label": "픽업서비스 내역", "url": CTAUrls.SMART_PICKUP_LIST, "domain": "SUPPORT"}],
        predicted_domains=["SUPPORT"],
    ),
    GuardId.PICKUP_INFO: Guard(
        id="pickup_info",
        text=(
            "스마트픽업은 매장에서 고객 차량을 픽업해 타이어를 교체한 뒤 다시 인도하는 서비스예요. "
            "아래 '픽업서비스 신청'에서 신청/관리하실 수 있으며, 픽업 가능 거리는 매장 기준 최대 30km까지예요. "
            "요금과 실제 가능 여부는 픽업/인도 위치와 매장 운영에 따라 달라질 수 있어요."
        ),
        chips=[
            {"label": "픽업서비스 신청", "url": CTAUrls.SMART_PICKUP, "domain": "SUPPORT"},
            {"label": "내 근처 매장 찾기", "domain": "TRANSACTION"},
            {"label": "타이어 추천", "domain": "DISCOVERY"},
        ],
        predicted_domains=["SUPPORT", "TRANSACTION", "DISCOVERY"],
    ),
}


def _reservation_date_guard() -> Guard:
    today = date.today()
    max_day = today + timedelta(days=30)
    return Guard(
        id="reservation_date_range",
        text=(
            f"예약 가능 일정은 오늘({today.isoformat()})부터 {max_day.year}년 {max_day.month}월 {max_day.day}일까지로 "
            "확인돼요. 지난 날짜나 그 이후 날짜는 예약 가능 여부를 확인할 수 없으니, "
            "예약 가능 기간 내 날짜로 다시 선택해 주세요."
        ),
        chips=[
            {"label": "예약 가능 날짜 보기", "domain": "TRANSACTION"},
            {"label": "다른 매장 보기", "domain": "TRANSACTION"},
        ],
        predicted_domains=["TRANSACTION"],
    )


def get_guard(guard_id: GuardId | None) -> Guard | None:
    if guard_id is None or guard_id == GuardId.NONE:
        return None
    if guard_id == GuardId.RESERVATION_DATE_RANGE:
        return _reservation_date_guard()
    return _STATIC_GUARDS.get(guard_id)
