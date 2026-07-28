from __future__ import annotations

import datetime

from services.tstation.policies.coupon_response_policy import (
    build_coupon_applicability_event,
    build_coupon_channel_policy_event,
    build_my_coupons_list_event,
    build_owned_coupon_best_discount_event,
    build_owned_coupon_expiry_lookup_event,
    build_product_coupon_eligibility_event,
    coupon_channel_type,
    find_coupon_from_owned_coupons,
    find_single_confident_coupon_from_owned_coupons,
    is_owned_coupon_best_discount_query,
    is_owned_coupon_expiry_lookup_query,
    merge_coupon_applicable_products_results,
    owned_coupon_lookup_summary_text,
    specific_owned_coupon_lookup_hint,
)


def test_owned_coupon_expiry_lookup_filters_current_month() -> None:
    today = datetime.date.today()
    event = build_owned_coupon_expiry_lookup_event(
        "보유 쿠폰 중에 이번달 만료인거 뭐 있어?",
        {
            "data": {
                "coupons": [
                    {"cpn_nm": "이번달 쿠폰", "use_end_dtime": today.strftime("%Y%m%d"), "rt_amt_val": "10"},
                    {"cpn_nm": "내년 쿠폰", "use_end_dtime": f"{today.year + 1}0101", "rt_amt_val": "5000"},
                ]
            }
        },
    )

    assert event["assistant_response_source"] == "code_owned_coupon_expiry_lookup"
    assert "이번달 쿠폰" in event["data"]["assistantResponse"]
    assert "내년 쿠폰" not in event["data"]["assistantResponse"]
    assert is_owned_coupon_expiry_lookup_query("보유 쿠폰 중에 이번달 만료인거 뭐 있어?")


def test_owned_coupon_best_discount_summarizes_percent_and_amount() -> None:
    event = build_owned_coupon_best_discount_event(
        {
            "data": {
                "coupons": [
                    {"cpn_nm": "10% 쿠폰", "rt_amt_val": "10", "min_pur_amt": "30000"},
                    {"cpn_nm": "20% 쿠폰", "rt_amt_val": "20", "max_dscnt_amt": "10000"},
                    {"cpn_nm": "정액 쿠폰", "rt_amt_val": "15000"},
                ]
            }
        }
    )

    text = event["data"]["assistantResponse"]
    assert event["assistant_response_source"] == "code_owned_coupon_best_discount"
    assert "20% 쿠폰" in text
    assert "정액 쿠폰" in text
    assert is_owned_coupon_best_discount_query("내 쿠폰 중 가장 할인 큰 쿠폰 뭐야?")


def test_my_coupons_list_tolerates_missing_or_invalid_discount_values() -> None:
    event = build_my_coupons_list_event(
        {
            "data": {
                "coupons": [
                    {"cpn_nm": "할인값 NULL 쿠폰", "rt_amt_val": None},
                    {"cpn_nm": "할인값 누락 쿠폰"},
                    {"cpn_nm": "할인값 비정상 쿠폰", "rt_amt_val": "미정"},
                    {"cpn_nm": "할인값 0원 쿠폰", "rt_amt_val": 0},
                    {"cpn_nm": "30% 쿠폰", "rt_amt_val": 30},
                    {"cpn_nm": "정액 쿠폰", "rt_amt_val": 15000},
                ]
            }
        }
    )

    text = event["data"]["assistantResponse"]
    assert event["assistant_response_source"] == "code_my_coupons_lookup"
    assert "보유 쿠폰은 총 6개예요." in text
    assert "할인값 NULL 쿠폰" in text
    assert "할인값 누락 쿠폰" in text
    assert "할인값 비정상 쿠폰" in text
    assert "할인값 0원 쿠폰" in text
    assert "30% 쿠폰 (30% 할인)" in text
    assert "정액 쿠폰 (15,000원 할인)" in text


def test_specific_owned_coupon_matching_handles_ambiguous_names() -> None:
    matched, ambiguous = find_single_confident_coupon_from_owned_coupons(
        "패밀리 쿠폰 있어?",
        {
            "data": {
                "coupons": [
                    {"cpn_no": "C000000001", "cpn_nm": "패밀리 쿠폰 1"},
                    {"cpn_no": "C000000002", "cpn_nm": "패밀리 쿠폰 2"},
                ]
            }
        },
    )

    assert matched is None
    assert [row["cpn_no"] for row in ambiguous] == ["C000000001", "C000000002"]
    assert specific_owned_coupon_lookup_hint("혹시 패밀리쿠폰 있어?") == "패밀리"


def test_owned_coupon_lookup_uses_gate_coupon_hint_and_product_name() -> None:
    summary = owned_coupon_lookup_summary_text(
        "1월 키너지EX 특가전 쿠폰은?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "cpn_nm": "[1월 키너지EX 특가전] 한국타이어 30% 할인쿠폰",
                        "rt_amt_val": 30,
                    },
                    {"cpn_no": "C002", "cpn_nm": "DRIVE X 월디페 참여고객 쿠폰", "rt_amt_val": 30},
                ],
            },
        },
        coupon_hint="1월 특가전 쿠폰",
        product_name="키너지EX",
    )

    assert summary is not None
    assert "‘[1월 키너지EX 특가전] 한국타이어 30% 할인쿠폰’ 관련 쿠폰을 보유 중이에요" in summary


def test_coupon_channel_policy_store_only_does_not_offer_price_cta() -> None:
    event = build_coupon_channel_policy_event(
        {"cpn_no": "C001", "cpn_nm": "매장 쿠폰", "coupon_channel_type": "store_only"},
        applicable_result={
            "data": {"stores": [{"items": [{"shop_nm": "강남점"}, {"shop_nm": "서초점"}]}]},
        },
    )

    assert coupon_channel_type({"cpn_onoff_cd": "30", "has_store_mapping": True}) == "store_only"
    assert event is not None
    assert event["assistant_response_source"] == "code_coupon_channel_policy"
    labels = [chip["label"] for chip in event["data"]["quickReplies"]]
    assert "상품 가격 확인" not in labels
    assert "적용 매장 보기" in labels
    assert "강남점" in event["data"]["assistantResponse"]


def test_coupon_applicability_answers_target_pattern_without_size_listing() -> None:
    event = build_coupon_applicability_event(
        {
            "data": {
                "total_products": 1,
                "coupons": [{"items": [{"goods_nm": "Ventus S2 AS"}]}],
            }
        },
        {"cpn_nm": "패밀리 쿠폰"},
        target_product_name="벤투스 S2 AS",
    )

    assert event["assistant_response_source"] == "code_coupon_resolver"
    assert "Ventus S2 AS" in event["data"]["assistantResponse"]
    assert event["data"]["predictedDomains"] == ["DISCOVERY", "TRANSACTION"]


def test_product_coupon_eligibility_filters_owned_coupons_by_target_pattern() -> None:
    event = build_product_coupon_eligibility_event(
        {
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "items": [{"goods_nm": "Ventus S2 AS"}]},
                    {"cpn_no": "C002", "items": [{"goods_nm": "Kinergy EX"}]},
                ]
            }
        },
        [
            {"cpn_no": "C001", "cpn_nm": "벤투스 쿠폰"},
            {"cpn_no": "C002", "cpn_nm": "키너지 쿠폰"},
        ],
        target_product_name="벤투스 S2 AS",
    )

    text = event["data"]["assistantResponse"]
    assert event["assistant_response_source"] == "code_product_coupon_resolver"
    assert "벤투스 쿠폰" in text
    assert "키너지 쿠폰" not in text


def test_coupon_merge_combines_batched_applicable_products_results() -> None:
    merged = merge_coupon_applicable_products_results(
        [
            {"data": {"coupons": [{"total": 2}], "deals": [], "stores": []}},
            {"data": {"coupons": [], "deals": [{"total": 3}], "stores": [{"total": 1}]}},
        ]
    )

    assert merged["data"]["total_coupons"] == 1
    assert merged["data"]["total_deals"] == 1
    assert merged["data"]["total_products"] == 5
    assert merged["data"]["total_stores"] == 1


def test_coupon_direct_id_match_wins_over_name_terms() -> None:
    result = find_coupon_from_owned_coupons(
        "C000000002 쿠폰 보여줘",
        {"data": {"coupons": [{"cpn_no": "C000000001"}, {"cpn_no": "C000000002"}]}},
    )

    assert result == {"cpn_no": "C000000002"}
