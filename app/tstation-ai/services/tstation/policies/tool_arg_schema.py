"""Preferred-tool argument schema and canonicalization helpers.

This module is intentionally data-driven: policy code should decide the
preferred tool, then this module fills missing tool arguments from
existing_patch -> known_slots -> user_text extractors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from services.tstation.policies.discovery_intent_policy import extract_benefit_applicable_products_query


_UNSET = object()


@dataclass(frozen=True)
class ToolArgRule:
    """How to fill one argument for a tool."""

    description: str
    sources: tuple[str, ...] = ()
    extractors: tuple[str, ...] = ()
    default: Any = _UNSET
    required: bool = True


@dataclass(frozen=True)
class ToolInputSpec:
    """Required/optional argument spec for one preferred tool."""

    role: str
    args: Mapping[str, ToolArgRule] = field(default_factory=dict)


# NOTE:
# - sources are semantic aliases in known_slots/tool_args_patch.
# - defaults are applied only when the argument is still missing.
# - Korean role comments document why each tool exists and what the args mean.
TOOL_REQUIRED_INPUTS: dict[str, ToolInputSpec] = {
    # 역할: 차량과 상품의 호환 여부를 확인한다.
    "check_compatibility_tool": ToolInputSpec(
        role="차량번호/소유자명과 상품번호로 장착 호환성을 검증",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "car_no": ToolArgRule("차량번호", ("car_no", "carNo", "vehicle_no", "plate_no")),
            "owner_nm": ToolArgRule("소유자명", ("owner_nm", "ownerName", "owner_name")),
        },
    ),
    # 역할: 상품명/브랜드/사이즈 조건으로 상품 목록을 검색한다.
    "search_product_tool": ToolInputSpec(
        role="상품명, 브랜드, 사이즈, 가격 조건 기반 상품 검색",
        args={
            "keyword": ToolArgRule(
                "상품 검색어",
                (
                    "keyword",
                    "product_keyword",
                    "product_name",
                    "tire_model",
                    "tire_nm",
                    "pattern_name",
                    "pending_product_name",
                ),
                ("raw_user_text",),
                required=False,
            ),
            "limit": ToolArgRule("검색 개수", ("limit", "product_limit"), default=10, required=False),
            "size": ToolArgRule("타이어 사이즈", ("size", "tire_size", "tireSize"), required=False),
            "brand_cd": ToolArgRule("브랜드 코드", ("brand_cd", "brandCd", "brand_code"), required=False),
            "sort_by": ToolArgRule("정렬 기준", ("sort_by", "sortBy"), required=False),
            "min_price": ToolArgRule("최소 가격", ("min_price", "minPrice"), required=False),
            "max_price": ToolArgRule("최대 가격", ("max_price", "maxPrice"), required=False),
        },
    ),
    # 역할: 상품 요약/비교를 위해 상품번호 또는 상품명 묶음으로 요약 정보를 조회한다.
    "search_product_summary_tool": ToolInputSpec(
        role="상품번호/상품명 기반 상품 요약 조회",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"), required=False),
            "goods_no_list": ToolArgRule(
                "상품번호 목록",
                ("goods_no_list", "goodsNoList"),
                ("goods_no_list_from_slots",),
                required=False,
            ),
            "product_names": ToolArgRule(
                "상품명 목록",
                ("product_names", "productNames"),
                ("product_names_from_slots",),
                required=False,
            ),
            "keyword": ToolArgRule(
                "상품 요약 검색어",
                ("keyword", "product_name", "tire_model", "pending_product_name"),
                required=False,
            ),
        },
    ),
    # 역할: 등록 차량 목록을 조회한다.
    "get_user_vehicles_tool": ToolInputSpec(
        role="차량번호와 소유자명으로 사용자 차량 조회",
        args={
            "car_no": ToolArgRule("차량번호", ("car_no", "carNo", "vehicle_no", "plate_no")),
            "owner_nm": ToolArgRule("소유자명", ("owner_nm", "ownerName", "owner_name")),
        },
    ),
    # 역할: JWT 회원의 내 차량 목록을 조회한다.
    "get_my_cars_tool": ToolInputSpec(
        role="로그인 회원의 등록 차량 목록 조회",
        args={"mbr_no": ToolArgRule("회원번호", ("mbr_no", "mbrNo", "member_no"), required=False)},
    ),
    # 역할: 차량 모델명을 검색한다.
    "search_car_model_tool": ToolInputSpec(
        role="차량 모델명 검색",
        args={"keyword": ToolArgRule("차량 모델 검색어", ("keyword", "car_model", "car_nm"), ("raw_user_text",))},
    ),
    # 역할: 차량 모델 그룹을 검색한다.
    "search_car_model_groups_tool": ToolInputSpec(
        role="차량 모델 그룹 검색",
        args={"keyword": ToolArgRule("차량 모델 그룹 검색어", ("keyword", "car_model", "car_nm"), ("raw_user_text",))},
    ),
    # 역할: 차량 모델 상세 트림을 조회한다.
    "get_car_trims_tool": ToolInputSpec(
        role="차량 모델 상세 트림 조회",
        args={"car_model_det": ToolArgRule("차량 모델 상세 코드", ("car_model_det", "carModelDet"))},
    ),
    # 역할: 상품번호 기준 상품 설명을 조회한다.
    "get_product_description_tool": ToolInputSpec(
        role="상품번호 기준 상품 상세 설명 조회",
        args={"goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"))},
    ),
    # 역할: 사이즈/차량/추천 조건으로 추천 상품을 조회한다.
    "get_products_recommendations_tool": ToolInputSpec(
        role="차량/사이즈/추천 시나리오 기반 상품 추천",
        args={
            "tire_size": ToolArgRule("타이어 사이즈", ("tire_size", "tireSize", "size"), required=False),
            "car_lnc_cd": ToolArgRule("차량 라인 코드", ("car_lnc_cd", "carLncCd"), required=False),
            "rcmd_type": ToolArgRule("추천 유형", ("rcmd_type", "recommendation_scenario"), required=False),
            "brand_cd": ToolArgRule("브랜드 코드", ("brand_cd", "brandCd"), required=False),
            "min_price": ToolArgRule("최소 가격", ("min_price", "minPrice"), required=False),
            "max_price": ToolArgRule("최대 가격", ("max_price", "maxPrice"), required=False),
            "limit": ToolArgRule("추천 개수", ("limit",), default=10, required=False),
        },
    ),
    # 역할: 진행 중인 이벤트 목록을 조회한다.
    "get_events_tool": ToolInputSpec(
        role="진행 중 이벤트 목록 조회",
        args={"lang_cd": ToolArgRule("언어 코드", ("lang_cd", "langCd"), default="ko", required=False)},
    ),
    # 역할: 혜택명/이벤트명/상품명으로 적용 가능 상품을 검색한다.
    "search_benefit_applicable_products_tool": ToolInputSpec(
        role="혜택/이벤트/쿠폰/상품명 기준 적용 가능 상품 조회",
        args={
            "query": ToolArgRule(
                "혜택명 또는 적용 확인 대상 상품명",
                (
                    "query",
                    "benefit_applicable_products_query",
                    "event_name",
                    "deal_name",
                    "coupon_name",
                    "cpn_nm",
                    "product_name",
                    "tire_model",
                    "tire_nm",
                    "pending_product_name",
                    "pattern_name",
                ),
                ("benefit_query_from_user_text",),
            ),
            "lang_cd": ToolArgRule("언어 코드", ("lang_cd", "langCd"), default="ko", required=False),
        },
    ),
    # 역할: 이벤트 번호 목록으로 이벤트 적용 상품을 조회한다.
    "get_event_applicable_products_tool": ToolInputSpec(
        role="이벤트 번호 기준 적용 상품 조회",
        args={"evt_no_list": ToolArgRule("이벤트 번호 목록", ("evt_no_list", "evtNoList"), ("evt_no_list_from_slots",))},
    ),
    # 역할: 상품 패턴 코드 기준 적용 가능한 이벤트를 조회한다.
    "get_product_applicable_events_tool": ToolInputSpec(
        role="상품 패턴 기준 적용 이벤트 조회",
        args={
            "ptrn_cd": ToolArgRule("상품 패턴 코드", ("ptrn_cd", "ptrnCd", "pattern_cd", "patternCode")),
            "lang_cd": ToolArgRule("언어 코드", ("lang_cd", "langCd"), default="ko", required=False),
        },
    ),
    # 역할: 진행 중인 딜/기획전 목록을 조회한다.
    "get_deals_tool": ToolInputSpec(role="진행 중인 딜/기획전 목록 조회"),
    # 역할: 이벤트/딜/혜택 목록을 통합 조회한다.
    "get_benefit_event_deal_list_tool": ToolInputSpec(
        role="혜택/이벤트/딜 목록 통합 조회",
        args={"lang_cd": ToolArgRule("언어 코드", ("lang_cd", "langCd"), default="ko", required=False)},
    ),
    # 역할: 여러 상품의 할인/최저가를 비교한다.
    "compare_discount_tool": ToolInputSpec(
        role="상품 목록 할인 비교",
        args={
            "goods_no_list": ToolArgRule("상품번호 목록", ("goods_no_list", "goodsNoList"), ("goods_no_list_from_slots",)),
            "quantity": ToolArgRule("수량", ("quantity", "ord_qty", "ordQty"), default=1, required=False),
        },
    ),
    # 역할: 상품의 최저가를 조회한다.
    "get_cheapest_price_tool": ToolInputSpec(
        role="상품 최저가 조회",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "quantity": ToolArgRule("수량", ("quantity", "ord_qty", "ordQty"), default=1, required=False),
        },
    ),
    # 역할: 유튜브 영상 검색을 수행한다.
    "search_youtube_video_tool": ToolInputSpec(
        role="유튜브 영상 검색",
        args={
            "query": ToolArgRule(
                "영상 검색어",
                ("query", "product_name", "tire_model", "pending_product_name"),
                ("raw_user_text",),
            ),
            "max_results": ToolArgRule("최대 결과 수", ("max_results", "limit"), default=3, required=False),
        },
    ),
    # 역할: 신상품 목록을 조회한다.
    "get_newest_products_tool": ToolInputSpec(
        role="신상품 목록 조회",
        args={
            "brand_cd": ToolArgRule("브랜드 코드", ("brand_cd", "brandCd"), default="HK", required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=20, required=False),
        },
    ),
    # 역할: 최종 가격과 적용 가능한 쿠폰/할인 정보를 조회한다.
    "get_final_price_tool": ToolInputSpec(
        role="상품번호 기준 최종 가격/쿠폰/할인 조회",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "member_type": ToolArgRule("회원 유형", ("member_type", "memberType"), required=False),
        },
    ),
    # 역할: 베스트셀러 상품 목록을 조회한다.
    "get_best_selling_products_tool": ToolInputSpec(
        role="베스트셀러 상품 조회",
        args={
            "brand_cd": ToolArgRule("브랜드 코드", ("brand_cd", "brandCd"), default="HK", required=False),
            "vehicle_type": ToolArgRule("차종", ("vehicle_type", "vehicleType", "car_knd_nm"), required=False),
            "season": ToolArgRule("계절", ("season", "season_nm"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=20, required=False),
        },
    ),
    # 역할: 내 쿠폰 목록을 조회한다.
    "get_my_coupons_tool": ToolInputSpec(
        role="로그인 회원 보유 쿠폰 목록 조회",
        args={"lang_cd": ToolArgRule("언어 코드", ("lang_cd", "langCd"), default="ko", required=False)},
    ),
    # 역할: 쿠폰을 발급한다. 상품번호 또는 쿠폰번호 중 하나만 사용한다.
    "issue_coupon_tool": ToolInputSpec(
        role="쿠폰 발급",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"), required=False),
            "cpn_no": ToolArgRule("쿠폰번호", ("cpn_no", "cpnNo", "coupon_no"), required=False),
        },
    ),
    # 역할: 쿠폰/기획전 번호로 적용 가능 상품 또는 매장을 조회한다.
    "get_coupon_applicable_products_tool": ToolInputSpec(
        role="쿠폰/기획전 번호 기준 적용 가능 상품/매장 조회",
        args={
            "cpn_no": ToolArgRule("쿠폰번호 목록", ("cpn_no", "cpnNo"), ("cpn_no_list_from_slots",), required=False),
            "deal_no": ToolArgRule("기획전번호 목록", ("deal_no", "dealNo"), ("deal_no_list_from_slots",), required=False),
        },
    ),
    # 역할: 상품번호 기준 진행 중인 프로모션/기획전/쿠폰을 조회한다.
    "get_product_promotions_tool": ToolInputSpec(
        role="상품번호 기준 프로모션 조회",
        args={"goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"))},
    ),
    # 역할: 상품번호 기준 물류 재고를 조회한다.
    "get_logistics_inventory_tool": ToolInputSpec(
        role="상품 물류 재고 조회",
        args={"goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"))},
    ),
    # 역할: 상품/수량과 매장 목록으로 매장 재고를 조회한다.
    "get_store_inventory_tool": ToolInputSpec(
        role="선택 상품의 특정 매장 재고 조회",
        args={
            "goods_list": ToolArgRule("상품번호/수량 목록", ("goods_list", "goodsList"), ("goods_list_from_slots",)),
            "shop_id_list": ToolArgRule("매장 ID 목록", ("shop_id_list", "shopIdList"), ("shop_id_list_from_slots",)),
        },
    ),
    # 역할: 매장별 물류/매장 재고와 예약 가능 일정을 통합 조회한다.
    "get_store_install_availability_tool": ToolInputSpec(
        role="매장별 장착 가능 일정 통합 조회",
        args={
            "shop_id_list": ToolArgRule("매장 ID 목록", ("shop_id_list", "shop_ids", "shopIds"), ("shop_ids_from_slots",)),
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"), required=False),
            "ord_qty": ToolArgRule("주문 수량", ("ord_qty", "ordQty", "quantity"), default=1, required=False),
            "requested_cal_day": ToolArgRule(
                "희망 예약일",
                ("requested_cal_day", "requestedCalDay", "cal_day"),
                required=False,
            ),
        },
    ),
    # 역할: 장소명을 좌표/장소 후보로 검색한다.
    "search_place_tool": ToolInputSpec(
        role="장소명 검색",
        args={
            "query": ToolArgRule("장소 검색어", ("query", "place_query", "region", "store_name"), ("raw_user_text",)),
            "size": ToolArgRule("검색 개수", ("size", "limit"), default=10, required=False),
        },
    ),
    # 역할: 현재 좌표 또는 지정 좌표 주변 매장을 조회한다.
    "get_nearby_stores_tool": ToolInputSpec(
        role="좌표 기준 주변 매장 조회",
        args={
            "lat": ToolArgRule("위도", ("lat", "user_ypos", "ypos", "latitude")),
            "lng": ToolArgRule("경도", ("lng", "user_xpos", "xpos", "longitude")),
            "radius": ToolArgRule("반경", ("radius", "distance"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=10, required=False),
        },
    ),
    # 역할: 매장명/지역/서비스 조건으로 매장 목록을 조회한다.
    "get_store_list_tool": ToolInputSpec(
        role="매장 목록 조회",
        args={
            "store_nm": ToolArgRule("매장명", ("store_nm", "store_name", "shop_name", "shop_nm"), required=False),
            "region": ToolArgRule("지역", ("region", "region_code", "place_query"), required=False),
            "shop_id": ToolArgRule("매장 ID", ("shop_id", "shopId", "store_id"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=10, required=False),
        },
    ),
    # 역할: 지역/매장명/서비스 조건으로 매장을 검색한다.
    "search_stores_tool": ToolInputSpec(
        role="일반 매장 검색",
        args={
            "region": ToolArgRule("지역", ("region", "region_code", "place_query"), required=False),
            "store_name": ToolArgRule("매장명", ("store_name", "store_nm", "shop_name", "shop_nm"), required=False),
            "service_code": ToolArgRule("서비스 코드", ("service_code", "svc_code"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=10, required=False),
        },
    ),
    # 역할: 운영시간/서비스/복합 조건으로 매장을 검색한다.
    "search_stores_complex_tool": ToolInputSpec(
        role="복합 조건 매장 검색",
        args={
            "region": ToolArgRule("지역", ("region", "region_code", "place_query"), required=False),
            "store_name": ToolArgRule("매장명", ("store_name", "store_nm", "shop_name", "shop_nm"), required=False),
            "service_code": ToolArgRule("서비스 코드", ("service_code", "svc_code"), required=False),
            "open_only": ToolArgRule("영업 중 필터", ("open_only", "is_open"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=10, required=False),
        },
    ),
    # 역할: 매장 상세 정보를 조회한다.
    "get_store_detail_tool": ToolInputSpec(
        role="매장 상세 조회",
        args={
            "shop_id": ToolArgRule("매장 ID", ("shop_id", "shopId", "store_id")),
            "cal_day": ToolArgRule("기준일", ("cal_day", "requested_cal_day", "requestedCalDay"), required=False),
            "is_logistics_delivery": ToolArgRule(
                "물류 배송 여부",
                ("is_logistics_delivery", "isLogisticsDelivery"),
                default=False,
                required=False,
            ),
        },
    ),
    # 역할: 특정 매장의 예약 가능 일정을 조회한다.
    "get_store_schedule_tool": ToolInputSpec(
        role="매장 예약 가능 일정 조회",
        args={
            "shop_id": ToolArgRule("매장 ID", ("shop_id", "shopId", "store_id")),
            "mode": ToolArgRule("스케줄 조회 모드", ("mode", "schedule_mode", "inventory_mode"), default="combined"),
        },
    ),
    # 역할: 여러 매장의 예약 가능 일정을 한 번에 조회한다.
    "get_multi_store_schedule_tool": ToolInputSpec(
        role="복수 매장 예약 가능 일정 조회",
        args={
            "shop_ids": ToolArgRule("매장 ID 목록", ("shop_ids", "shopIds"), ("shop_ids_from_slots",)),
            "mode": ToolArgRule("스케줄 조회 모드", ("mode", "schedule_mode", "inventory_mode"), default="combined"),
        },
    ),
    # 역할: 특정 시간 이후 영업 가능한 매장을 검색한다.
    "get_stores_with_time_filter_tool": ToolInputSpec(
        role="시간 조건 매장 검색",
        args={
            "region_code": ToolArgRule("지역 코드/지역명", ("region_code", "region", "place_query")),
            "time_threshold_hour": ToolArgRule("기준 시간", ("time_threshold_hour", "hour", "rsv_hour")),
        },
    ),
    # 역할: 상품/수량/지역/매장 조건으로 장착 가능 매장 후보를 미리 조회한다.
    "transaction_store_preview_tool": ToolInputSpec(
        role="구매/재고 흐름의 장착 가능 매장 preview",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "tire_size": ToolArgRule("타이어 사이즈", ("tire_size", "tireSize", "size")),
            "ord_qty": ToolArgRule("주문 수량", ("ord_qty", "ordQty", "quantity")),
            "region_code": ToolArgRule("지역", ("region_code", "region", "place_query"), required=False),
            "shop_id": ToolArgRule("매장 ID", ("shop_id", "shopId", "store_id"), required=False),
            "shop_name": ToolArgRule("매장명", ("shop_name", "shop_nm", "store_name", "store_nm"), required=False),
            "user_xpos": ToolArgRule("사용자 경도", ("user_xpos", "xpos", "lng", "longitude"), required=False),
            "user_ypos": ToolArgRule("사용자 위도", ("user_ypos", "ypos", "lat", "latitude"), required=False),
            "stock_check_mode": ToolArgRule("재고 확인 모드", ("stock_check_mode",), required=False),
        },
    ),
    # 역할: 장바구니에 상품을 담는다.
    "save_to_cart_tool": ToolInputSpec(
        role="장바구니 담기",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "ord_qty": ToolArgRule("수량", ("ord_qty", "ordQty", "quantity")),
            "car_lnc_cd": ToolArgRule("차량 라인 코드", ("car_lnc_cd", "carLncCd"), required=False),
        },
    ),
    # 역할: 빠른 주문을 생성한다.
    "quick_order_tool": ToolInputSpec(
        role="빠른 주문 생성",
        args={
            "goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo")),
            "ord_qty": ToolArgRule("수량", ("ord_qty", "ordQty", "quantity")),
            "shop_id": ToolArgRule("매장 ID", ("shop_id", "shopId", "store_id")),
            "requested_cal_day": ToolArgRule("예약 날짜", ("requested_cal_day", "requestedCalDay", "cal_day")),
            "rsv_hour": ToolArgRule("예약 시간", ("rsv_hour", "rsvHour", "hour")),
            "car_lnc_cd": ToolArgRule("차량 라인 코드", ("car_lnc_cd", "carLncCd"), required=False),
            "payment_amount": ToolArgRule("결제 예상 금액", ("payment_amount", "paymentAmount"), required=False),
        },
    ),
    # 역할: 주문번호로 주문 상태를 조회한다.
    "get_order_status_tool": ToolInputSpec(
        role="주문번호 기준 주문 상태 조회",
        args={"query_no": ToolArgRule("주문번호", ("query_no", "order_no", "ord_no"), ("order_no_from_user_text",))},
    ),
    # 역할: 내 주문 목록을 조회한다.
    "get_orders_of_user_tool": ToolInputSpec(role="로그인 회원 주문 목록 조회"),
    # 역할: 정비 이력 목록을 조회한다.
    "get_maintenance_history_tool": ToolInputSpec(
        role="정비 이력 조회",
        args={
            "mbr_car_reg_seq": ToolArgRule("회원 차량 등록 순번", ("mbr_car_reg_seq", "mbrCarRegSeq"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=5, required=False),
        },
    ),
    # 역할: 내 예약 목록을 조회한다.
    "get_my_reservations_tool": ToolInputSpec(
        role="로그인 회원 예약 목록 조회",
        args={"sct_cd": ToolArgRule("예약 상태 필터", ("sct_cd", "sctCd"), default="all", required=False)},
    ),
    # 역할: 단골 매장 목록을 조회한다.
    "get_favorite_stores_tool": ToolInputSpec(role="로그인 회원 단골 매장 조회"),
    # 역할: FAQ 카테고리 기준으로 FAQ를 조회한다.
    "get_faq_tool": ToolInputSpec(
        role="FAQ 카테고리 조회",
        args={
            "lrcl_cd": ToolArgRule("FAQ 대분류 코드", ("lrcl_cd", "lrclCd"), required=False),
            "mdcl_cd": ToolArgRule("FAQ 중분류 코드", ("mdcl_cd", "mdclCd"), required=False),
            "limit": ToolArgRule("조회 개수", ("limit",), default=50, required=False),
        },
    ),
    # 역할: FAQ RAG 검색을 수행한다.
    "search_faq_rag_tool": ToolInputSpec(
        role="FAQ 벡터/RAG 검색",
        args={
            "query": ToolArgRule("FAQ 검색어", ("query", "faq_query", "support_query"), ("raw_user_text",)),
            "top_k": ToolArgRule("조회 개수", ("top_k", "limit"), default=8, required=False),
        },
    ),
    # 역할: FAQ 하이브리드 검색을 수행한다.
    "search_faq_hybrid_tool": ToolInputSpec(
        role="FAQ 하이브리드 검색",
        args={
            "query": ToolArgRule("FAQ 검색어", ("query", "faq_query", "support_query"), ("raw_user_text",)),
            "top_k": ToolArgRule("조회 개수", ("top_k", "limit"), default=8, required=False),
        },
    ),
    # 역할: 상담원 연결/상담 escalation을 수행한다.
    "escalate_tool": ToolInputSpec(
        role="상담원 escalation",
        args={
            "mbr_no": ToolArgRule("회원번호", ("mbr_no", "mbrNo", "member_no"), required=False),
            "inq_type_cd": ToolArgRule("문의 유형 코드", ("inq_type_cd", "inqTypeCd"), required=False),
            "msg_count": ToolArgRule("대화 메시지 수", ("msg_count", "message_count"), default=0, required=False),
            "summary": ToolArgRule("상담 요약", ("summary", "ai_summary"), ("raw_user_text",), required=False),
        },
    ),
    # 역할: 1:1 문의 작성 URL을 생성한다.
    "transfer_to_qna_tool": ToolInputSpec(
        role="1:1 문의 작성 URL 생성",
        args={
            "cnsl_clss_seq": ToolArgRule("상담 분류 코드", ("cnsl_clss_seq", "cnslClssSeq"), required=False),
            "inq_tit_nm": ToolArgRule("문의 제목", ("inq_tit_nm", "inqTitNm", "title"), required=False),
            "ai_summary": ToolArgRule("문의 요약", ("ai_summary", "summary"), ("raw_user_text",), required=False),
            "is_mobile": ToolArgRule("모바일 여부", ("is_mobile", "isMobile"), default=False, required=False),
        },
    ),
    # 역할: 차량 정비 D-day를 조회한다.
    "get_maintenance_dday_tool": ToolInputSpec(
        role="차량 정비 D-day 조회",
        args={"mbr_car_reg_seq": ToolArgRule("회원 차량 등록 순번", ("mbr_car_reg_seq", "mbrCarRegSeq"), required=False)},
    ),
    # 역할: 상품별 보증/워런티 적용 가능성을 조회한다.
    "get_product_warranties_tool": ToolInputSpec(
        role="상품별 워런티 조회",
        args={"goods_no": ToolArgRule("상품번호", ("goods_no", "goodsNo"))},
    ),
    # 역할: 내 보유 워런티 목록을 조회한다.
    "get_my_relief_services_tool": ToolInputSpec(role="로그인 회원 안심서비스 가입/보상 이력 조회"),
    "get_my_warranties_tool": ToolInputSpec(role="로그인 회원 보유 워런티 조회"),
    # 역할: 카드 무이자 할부 정보를 조회한다.
    "get_card_installments_tool": ToolInputSpec(
        role="카드 무이자 할부 정보 조회",
        args={
            "tgt_amt": ToolArgRule("결제 예상 금액", ("tgt_amt", "payment_amount", "paymentAmount"), required=False),
            "payment_type": ToolArgRule("결제 유형", ("payment_type", "paymentType"), default="일반", required=False),
        },
    ),
    # 역할: 쿠폰 중복 사용 가능 여부를 조회한다.
    "check_coupon_stacking_tool": ToolInputSpec(
        role="쿠폰 중복 사용 가능 여부 조회",
        args={"cpn_no_list": ToolArgRule("쿠폰번호 목록", ("cpn_no_list", "cpnNoList"), ("cpn_no_list_from_slots",))},
    ),
}


def canonicalize_tool_args_patch(
    *,
    preferred_tool: str | None,
    known_slots: Mapping[str, Any] | None = None,
    user_text: str = "",
    existing_patch: Mapping[str, Any] | None = None,
    use_known_slots: bool = True,
) -> dict[str, Any]:
    """Fill missing preferred-tool args from existing patch, known slots, and user text."""

    tool_name = str(preferred_tool or "").strip()
    patch = {str(key): value for key, value in dict(existing_patch or {}).items() if _present(value)}
    spec = TOOL_REQUIRED_INPUTS.get(tool_name)
    if spec is None:
        return patch
    slots = known_slots or {} if use_known_slots else {}
    for arg_name, rule in spec.args.items():
        if _present(patch.get(arg_name)):
            continue
        value = _first_source_value(rule.sources, patch=patch, known_slots=slots)
        if not _present(value):
            value = _first_extractor_value(rule.extractors, patch=patch, known_slots=slots, user_text=user_text)
        if _present(value):
            patch[arg_name] = value
        elif rule.default is not _UNSET:
            patch[arg_name] = rule.default
    patch = canonicalize_schedule_mode_for_inventory(preferred_tool=tool_name, tool_args=patch, known_slots=slots)
    return {key: value for key, value in patch.items() if _present(value)}


def _shop_ids_from_rows(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    result: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            shop_id = str(row.get("shop_id") or row.get("shopId") or row.get("store_id") or "").strip()
        else:
            shop_id = str(row or "").strip()
        if shop_id:
            result.add(shop_id)
    return result


def _inventory_shop_ids(known_slots: Mapping[str, Any], key: str) -> set[str]:
    snake_key = "today_shop_ids" if key == "todayShopArray" else "tna_shop_ids"
    values = _shop_ids_from_rows(known_slots.get(key)) | _shop_ids_from_rows(known_slots.get(snake_key))
    for container_key in ("inventory", "store_inventory", "preview_inventory"):
        container = known_slots.get(container_key)
        if isinstance(container, Mapping):
            values |= _shop_ids_from_rows(container.get(key))
            values |= _shop_ids_from_rows(container.get(snake_key))
    return values


def canonicalize_schedule_mode_for_inventory(
    *,
    preferred_tool: str | None,
    tool_args: Mapping[str, Any] | None,
    known_slots: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Correct single-store schedule mode when inventory tier evidence is present."""

    patch = {str(key): value for key, value in dict(tool_args or {}).items() if _present(value)}
    if str(preferred_tool or "").strip() != "get_store_schedule_tool":
        return patch
    shop_id = str(patch.get("shop_id") or "").strip()
    if not shop_id:
        return patch
    slots = known_slots or {}
    today_ids = _inventory_shop_ids(slots, "todayShopArray")
    tna_ids = _inventory_shop_ids(slots, "tnaShopArray")
    if shop_id in today_ids:
        return patch
    if shop_id in tna_ids:
        patch["mode"] = "tna_only"
    return patch


def should_use_known_slots_for_tool_args(
    *,
    context_state: str | None,
    resume_anchor_detected: bool = False,
    resume_source: str | None = None,
    action_mode: str | None = None,
) -> bool:
    """Whether stale context slots may be used to fill preferred-tool args."""

    normalized_context = str(context_state or "").strip()
    normalized_resume_source = str(resume_source or "").strip()
    normalized_action_mode = str(action_mode or "").strip()
    if normalized_context in {"active", "resumed"}:
        return True
    if resume_anchor_detected:
        return True
    if normalized_resume_source and normalized_resume_source != "none":
        return True
    return normalized_action_mode in {
        "purchase_continuation",
        "slot_fill",
        "ui_action",
        "tool_recovery",
    }


def missing_required_tool_args(preferred_tool: str | None, tool_args: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Return missing required args according to TOOL_REQUIRED_INPUTS."""

    spec = TOOL_REQUIRED_INPUTS.get(str(preferred_tool or "").strip())
    if spec is None:
        return ()
    args = tool_args or {}
    missing: list[str] = []
    for arg_name, rule in spec.args.items():
        if rule.required and not _present(args.get(arg_name)):
            missing.append(arg_name)
    return tuple(missing)


def _first_source_value(
    sources: tuple[str, ...],
    *,
    patch: Mapping[str, Any],
    known_slots: Mapping[str, Any],
) -> Any:
    for source in sources:
        if _present(patch.get(source)):
            return patch[source]
        value = _slot_value(known_slots, source)
        if _present(value):
            return value
    return None


def _first_extractor_value(
    extractors: tuple[str, ...],
    *,
    patch: Mapping[str, Any],
    known_slots: Mapping[str, Any],
    user_text: str,
) -> Any:
    for extractor in extractors:
        value = _extract_value(extractor, patch=patch, known_slots=known_slots, user_text=user_text)
        if _present(value):
            return value
    return None


def _extract_value(
    extractor: str,
    *,
    patch: Mapping[str, Any],
    known_slots: Mapping[str, Any],
    user_text: str,
) -> Any:
    if extractor == "raw_user_text":
        return user_text.strip()
    if extractor == "benefit_query_from_user_text":
        return extract_benefit_applicable_products_query(user_text)
    if extractor == "order_no_from_user_text":
        match = re.search(r"\b([A-Z]?\d{4,})\b", user_text or "", re.IGNORECASE)
        return match.group(1) if match else None
    if extractor == "goods_list_from_slots":
        goods_no = _slot_value(known_slots, "goods_no")
        quantity = _slot_value(known_slots, "ord_qty") or _slot_value(known_slots, "quantity")
        if goods_no and quantity:
            return [{"goodsNo": str(goods_no), "qty": str(quantity)}]
    if extractor == "shop_id_list_from_slots":
        shop_id = _slot_value(known_slots, "shop_id")
        if shop_id:
            return [{"shopId": str(shop_id)}]
    if extractor == "shop_ids_from_slots":
        value = _slot_value(known_slots, "shop_ids") or _slot_value(known_slots, "candidate_shop_ids")
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item or "").strip()]
        shop_id = _slot_value(known_slots, "shop_id")
        return [str(shop_id)] if shop_id else None
    if extractor == "goods_no_list_from_slots":
        value = _slot_value(known_slots, "goods_no_list") or _slot_value(known_slots, "goods_nos")
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item or "").strip()]
        goods_no = _slot_value(known_slots, "goods_no")
        return [str(goods_no)] if goods_no else None
    if extractor == "product_names_from_slots":
        value = _slot_value(known_slots, "product_names") or _slot_value(known_slots, "productNames")
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item or "").strip()]
        product_name = (
            _slot_value(known_slots, "product_name")
            or _slot_value(known_slots, "tire_model")
            or _slot_value(known_slots, "pending_product_name")
        )
        return [str(product_name)] if product_name else None
    if extractor == "evt_no_list_from_slots":
        return _list_value(known_slots, "evt_no_list", "evt_no", "event_no", "eventNo")
    if extractor == "cpn_no_list_from_slots":
        return _list_value(known_slots, "cpn_no_list", "cpn_no", "coupon_no", "couponNo")
    if extractor == "deal_no_list_from_slots":
        return _list_value(known_slots, "deal_no_list", "deal_no", "dealNo")
    return patch.get(extractor) or _slot_value(known_slots, extractor)


def _list_value(known_slots: Mapping[str, Any], *keys: str) -> list[str] | None:
    for key in keys:
        value = _slot_value(known_slots, key)
        if isinstance(value, (list, tuple)):
            items = [str(item) for item in value if str(item or "").strip()]
            if items:
                return items
        if _present(value):
            return [str(value)]
    return None


def _slot_value(slots: Mapping[str, Any], key: str) -> Any:
    if key in slots:
        return slots[key]
    for container_key in ("product", "store", "schedule", "intent", "payment", "vehicle"):
        container = slots.get(container_key)
        if isinstance(container, Mapping) and key in container:
            return container[key]
    active_flow = slots.get("active_flow_context")
    if isinstance(active_flow, Mapping):
        for container_key in ("product", "store", "schedule", "intent", "payment", "vehicle"):
            container = active_flow.get(container_key)
            if isinstance(container, Mapping) and key in container:
                return container[key]
    availability_context = slots.get("availability_context")
    if isinstance(availability_context, Mapping):
        active_flow = availability_context.get("active_flow_context")
        if isinstance(active_flow, Mapping):
            for container_key in ("product", "store", "schedule", "intent", "payment", "vehicle"):
                container = active_flow.get(container_key)
                if isinstance(container, Mapping) and key in container:
                    return container[key]
    return None


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})
