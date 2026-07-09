"""Deterministic FAQ policy answers keyed by policy intent.

These are policy FAQ answers that should not depend on vector retrieval.
The router/planner chooses the key; callers only fetch the official text.
"""

from __future__ import annotations

from typing import TypedDict

from services.tstation.common.cta_urls import CTAUrls


class StaticFaqPolicy(TypedDict):
    answer: str
    quick_replies: list[dict[str, str]]
    predicted_domains: list[str]


STATIC_FAQ_POLICY_DATABASE: dict[str, StaticFaqPolicy] = {
    "vehicle_type_compatibility": {
        "answer": (
            "SUV에는 승용차/세단용 타이어를 임의로 장착하는 건 권장하지 않아요. "
            "같은 사이즈처럼 보여도 하중지수와 설계 기준이 다를 수 있어서, "
            "차량 규격에 맞는 SUV용 또는 SUV 호환 타이어로 확인하는 게 안전합니다."
        ),
        "quick_replies": [
            {"label": "SUV용 추천", "domain": "DISCOVERY"},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 차량으로 확인", "domain": "DISCOVERY"},
        ],
        "predicted_domains": ["DISCOVERY"],
    },
    "runflat_mixed_install_policy": {
        "answer": (
            "기존에 런플랫 타이어가 장착된 차량이라면 앞바퀴 2짝만 일반 타이어로 바꾸는 것은 권장하지 않아요. "
            "런플랫과 일반 타이어는 사이드월 강성, 승차감, 핸들링, 공기압 저하 시 거동이 달라서 전후 또는 좌우 혼용 시 "
            "주행 안정성에 영향을 줄 수 있습니다.\n\n"
            "교체가 필요하다면 차량 제조사 권장 규격과 장착 기준을 먼저 확인하고, 가능하면 4짝 모두 같은 구조와 규격의 "
            "타이어로 맞추는 것이 안전합니다. 부득이하게 2짝만 교체해야 하는 경우에도 같은 축의 좌우 타이어는 동일한 "
            "제품·규격·마모 상태로 맞추고, 장착 전 매장에서 차량 기준을 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "런플랫 상품 보기", "domain": "DISCOVERY"},
            {"label": "내 차량으로 확인", "domain": "DISCOVERY"},
            {"label": "가까운 매장 찾기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "DISCOVERY", "TRANSACTION"],
    },
    "pickup_status": {
        "answer": (
            "픽업기사의 실시간 위치나 도착 시간은 챗봇에서 바로 확인하기 어려워요. "
            "신청하신 픽업/딜리버리 진행 현황은 아래 '픽업서비스 내역'에서 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "픽업서비스 내역", "url": CTAUrls.SMART_PICKUP_LIST, "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT"],
    },
    "pickup_info": {
        "answer": (
            "스마트픽업은 매장에서 고객 차량을 픽업해 타이어를 교체한 뒤 다시 인도하는 서비스예요. "
            "아래 '픽업서비스 신청'에서 신청/관리하실 수 있으며, 픽업 가능 거리는 매장 기준 최대 30km까지예요. "
            "요금과 실제 가능 여부는 픽업/인도 위치와 매장 운영에 따라 달라질 수 있어요."
        ),
        "quick_replies": [
            {"label": "픽업서비스 신청", "url": CTAUrls.SMART_PICKUP, "domain": "SUPPORT"},
            {"label": "내 근처 매장 찾기", "domain": "TRANSACTION"},
            {"label": "타이어 추천", "domain": "DISCOVERY"},
        ],
        "predicted_domains": ["SUPPORT", "TRANSACTION", "DISCOVERY"],
    },
    "late_night_store_hours_policy": {
        "answer": (
            "티스테이션 공식 영업시간은 평일 기준 09:00 ~ 19:00입니다.\n\n"
            "다만 매장별 영업시간은 상이할 수 있어, 심야 영업이나 19시 이후 방문 가능 여부는 "
            "이용하시려는 매장의 상세 영업시간을 방문 전 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "매장 찾기", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT", "TRANSACTION"],
    },
    "direct_home_delivery": {
        "answer": (
            "현재 티스테이션닷컴에서는 타이어를 집으로 배송받아 직접 장착하는 방식은 지원하지 않아요. "
            "온라인 주문은 선택하신 장착점으로 상품이 이동하고, 예약한 매장에서 장착받는 방식으로 진행됩니다."
        ),
        "quick_replies": [
            {"label": "장착 매장 찾기", "domain": "TRANSACTION"},
            {"label": "타이어 추천", "domain": "DISCOVERY"},
            {"label": "구매하기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "TRANSACTION", "DISCOVERY"],
    },
    "shipping_fee_region": {
        "answer": (
            "서귀포시를 포함한 제주 지역은 상품 1개당 배송비 1만 원이 발생해요.\n\n"
            "티스테이션닷컴은 기본적으로 무료배송·무료장착 원칙으로 운영되지만, "
            "제주 지역은 추가 배송비가 적용됩니다.\n\n"
            "정확한 배송비 내역은 실제 주문/결제 페이지의 결제금액에서 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "타이어 추천", "domain": "DISCOVERY"},
            {"label": "장착 매장 찾기", "domain": "TRANSACTION"},
            {"label": "구매하기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "DISCOVERY", "TRANSACTION"],
    },
    "online_store_price_policy": {
        "answer": (
            "서울이든 제주든 온라인 주문 자체는 같은 방식으로 진행돼요. "
            "주문/결제 단계에서 최종 금액을 확인한 뒤 선택한 장착점에서 장착받는 방식입니다.\n\n"
            "온라인 판매가와 매장 현장 판매가는 행사, 쿠폰, 재고, 매장 운영 조건에 따라 다를 수 있어요. "
            "제주 지역은 상품 1개당 배송비 1만 원이 추가될 수 있어 최종 결제금액에서 함께 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "온라인 상품 보기", "domain": "DISCOVERY"},
            {"label": "장착 매장 찾기", "domain": "TRANSACTION"},
            {"label": "구매하기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "DISCOVERY", "TRANSACTION"],
    },
    "regional_price_policy": {
        "answer": (
            "같은 상품이라도 지역, 장착점, 행사, 쿠폰, 재고, 배송 조건에 따라 최종 결제금액이 달라질 수 있어요.\n\n"
            "특히 제주 지역은 상품 1개당 배송비 1만 원이 추가될 수 있어 서울 지역과 최종 금액이 다를 수 있습니다. "
            "정확한 가격은 상품 규격과 장착점을 선택한 뒤 주문/결제 단계에서 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "상품 검색", "domain": "DISCOVERY"},
            {"label": "장착 매장 찾기", "domain": "TRANSACTION"},
            {"label": "구매하기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "DISCOVERY", "TRANSACTION"],
    },
    "past_event_page": {
        "answer": "지난 이벤트와 종료된 이벤트는 티스테이션 이벤트의 '지난 이벤트' 페이지에서 확인하실 수 있어요.",
        "quick_replies": [
            {"label": "지난 이벤트 보기", "url": CTAUrls.PROMOTION_PAST_EVENT_LIST, "domain": "DISCOVERY"},
            {"label": "진행 중인 이벤트 보기", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
        ],
        "predicted_domains": ["DISCOVERY"],
    },
    "maintenance_history_access_policy": {
        "answer": (
            "정비이력과 매장서비스 내역은 마이페이지의 매장서비스 내역에서 확인할 수 있어요.\n\n"
            "다른 지역 매장에 방문하더라도 차량번호나 예약자 정보로 이력 확인을 요청할 수 있지만, "
            "매장 시스템 권한이나 이력 종류에 따라 확인 범위는 달라질 수 있습니다."
        ),
        "quick_replies": [
            {"label": "매장서비스 내역", "url": CTAUrls.STORE_SERVICE_HISTORY, "domain": "SUPPORT"},
            {"label": "가까운 매장 찾기", "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["SUPPORT", "TRANSACTION"],
    },
    "maintenance_reminding_alarm": {
        "answer": (
            "점검·교체 알림과 all my T 점검 정보는 멤버십 대시보드 또는 리마인딩 알림 메뉴에서 확인할 수 있어요.\n\n"
            "차량별 실제 점검 시기와 교체 주기는 등록 차량 정보와 이용 이력에 따라 달라질 수 있습니다."
        ),
        "quick_replies": [
            {"label": "점검/교체 알림", "url": CTAUrls.REMINDING_ALARM, "domain": "SUPPORT"},
            {"label": "all my T 점검", "url": CTAUrls.MEMBERSHIP_DASHBOARD, "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT"],
    },
    "my_goods_review_lookup": {
        "answer": (
            "내가 작성한 상품 리뷰나 구매후기, 베스트리뷰 선정 여부는 마이페이지의 리뷰관리에서 확인할 수 있어요.\n\n"
            "개별 상품 페이지보다 내 리뷰 관리 화면을 먼저 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "상품 리뷰", "url": CTAUrls.GOODS_REVIEW, "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT"],
    },
    "store_service_review_write": {
        "answer": (
            "매장 리뷰나 매장 서비스 후기, 칭찬, 별점 작성은 마이페이지의 매장서비스 내역에서 확인하는 것이 기본입니다.\n\n"
            "장착 또는 서비스 이용 내역을 기준으로 작성 가능 여부가 달라질 수 있어 해당 내역 화면을 먼저 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "매장서비스 내역", "url": CTAUrls.STORE_SERVICE_HISTORY, "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT"],
    },
    "keep_service_history_lookup": {
        "answer": (
            "매장에 보관 중인 타이어는 보관 서비스 이력에서 확인할 수 있어요.\n\n"
            "분실이나 훼손이 걱정되는 경우에도 먼저 보관 이력과 등록 내역을 확인한 뒤 매장 또는 1:1 문의로 확인해 주세요."
        ),
        "quick_replies": [
            {"label": "보관 서비스 이력", "url": CTAUrls.KEEP_SERVICE_HIST, "domain": "SUPPORT"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ],
        "predicted_domains": ["SUPPORT"],
    },
    "tire_check_result_lookup": {
        "answer": (
            "타이어 마모도 측정 결과는 마모도 측정 결과 화면에서 확인할 수 있어요.\n\n"
            "새로 측정이 필요하면 마모도 측정 서비스를 이용해 주세요."
        ),
        "quick_replies": [
            {"label": "마모도 측정 결과", "url": CTAUrls.TIRE_CHECK_RESULT_LIST, "domain": "TRANSACTION"},
            {"label": "마모도 측정 서비스", "url": CTAUrls.TIRE_CHECK, "domain": "TRANSACTION"},
        ],
        "predicted_domains": ["TRANSACTION"],
    },
}


def get_static_faq_policy(policy_key: str) -> StaticFaqPolicy | None:
    return STATIC_FAQ_POLICY_DATABASE.get(str(policy_key or "").strip())
