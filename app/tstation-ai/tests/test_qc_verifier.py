"""Unit tests for the deterministic QC verifier.

Goal of this suite: lock in the false-positive guarantees the verifier is
supposed to deliver (correct values never flagged) and the catch cases that
motivated replacing the LLM QC (wrong values still caught).

Run from repo root with:

    cd app/tstation-ai && uv run pytest tests/test_qc_verifier.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.qc_verifier import (
    Mismatch,
    collect_source_values,
    parse_tool_output,
    verify_draft,
)


# --------------------------------------------------------------------------- #
#  Sources fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def price_source() -> list[tuple[str, dict]]:
    """Mimics get_final_price_tool output for one product."""
    return [
        (
            "get_final_price_tool",
            {
                "status": "success",
                "data": {
                    "goods_no": "G000000317727",
                    "sale_prc": 686400,
                    "final_prc": 480500,
                    "extra_fvr_sale_prc": 0,
                    "labor_cost": 24000,
                },
            },
        )
    ]


@pytest.fixture
def product_list_source() -> list[tuple[str, dict]]:
    """Mimics search_product_tool output."""
    return [
        (
            "search_product_tool",
            {
                "status": "success",
                "data": {
                    "items": [
                        {"goods_no": "G000000317727", "goods_nm": "벤투스 S2 AS", "sale_prc": 200000},
                        {"goods_no": "G000000317729", "goods_nm": "아이온 에보 AS", "sale_prc": 533500},
                    ]
                },
            },
        )
    ]


@pytest.fixture
def store_source() -> list[tuple[str, dict]]:
    return [
        (
            "get_nearby_stores_tool",
            {
                "status": "success",
                "data": {
                    "stores": [
                        {"shop_id": "C01306", "shop_nm": "강남점"},
                        {"shop_id": "F203675", "shop_nm": "한남점"},
                    ]
                },
            },
        )
    ]


# --------------------------------------------------------------------------- #
#  PASS cases — no false positives
# --------------------------------------------------------------------------- #

def test_empty_draft_passes() -> None:
    assert verify_draft("", []) == []


def test_no_sources_passes() -> None:
    """Without source data the verifier cannot prove anything wrong."""
    assert verify_draft("이 타이어는 480,500원이에요", []) == []


def test_direct_price_quote_passes(price_source) -> None:
    draft = "이 타이어 최종가는 480,500원이에요."
    assert verify_draft(draft, price_source) == []


def test_yen_symbol_price_passes(price_source) -> None:
    draft = "최종가는 ₩480,500 입니다."
    assert verify_draft(draft, price_source) == []


def test_four_tire_total_passes(price_source) -> None:
    """4 x 480,500 = 1,922,000 — qty multiplier explainability."""
    draft = "4개 합계 1,922,000원이에요."
    assert verify_draft(draft, price_source) == []


def test_one_plus_one_per_unit_passes() -> None:
    """1+1 단가: originalPrice / 2."""
    source = [("get_product_promotions_tool", {"data": {"originalPrice": 305800, "price": 229500}})]
    draft = "1+1 적용 시 개당 152,900원이에요."  # 305,800 / 2
    assert verify_draft(draft, source) == []


def test_two_plus_two_per_unit_passes() -> None:
    source = [("get_product_promotions_tool", {"data": {"originalPrice": 400000}})]
    draft = "2+2 시 개당 100,000원이에요."  # 400,000 / 4
    assert verify_draft(draft, source) == []


def test_sum_of_two_prices_passes(price_source) -> None:
    """상품가 + 공임비 = 480,500 + 24,000 = 504,500."""
    draft = "공임비 포함 504,500원이에요."
    assert verify_draft(draft, price_source) == []


def test_member_cheapest_price_fields_pass_qc() -> None:
    source = [
        (
            "get_product_description_tool",
            {
                "status": "success",
                "data": {
                    "goods_no": "G000000310283",
                    "sale_prc": 128700,
                    "cheapest_final_prc": 122300,
                    "cheapest_total_discount": 6400,
                    "cheapest_applied_coupons": [
                        {"cpn_nm": "테스트 쿠폰", "discount_amt": 6400},
                    ],
                    "final_unit_price": 122300,
                },
            },
        )
    ]
    assert verify_draft("회원 최저가는 122,300원이고 할인액은 6,400원이에요.", source) == []


def test_known_goods_no_passes(product_list_source) -> None:
    draft = "추천 상품은 G000000317727 입니다."
    assert verify_draft(draft, product_list_source) == []


def test_known_shop_id_passes(store_source) -> None:
    draft = "강남점 (C01306) 위치를 확인해주세요."
    assert verify_draft(draft, store_source) == []


def test_no_extracted_facts_passes(price_source) -> None:
    """Prose with no prices/IDs always passes — verifier never fabricates."""
    draft = "정숙성이 뛰어난 프리미엄 사계절 타이어예요."
    assert verify_draft(draft, price_source) == []


def test_small_integers_ignored(price_source) -> None:
    """Quantities, ratings, percentages must not be treated as prices."""
    draft = "평점 4.5점, 리뷰 6건, 출고 후 24시간 이내 발송됩니다."
    assert verify_draft(draft, price_source) == []


# --------------------------------------------------------------------------- #
#  MISMATCH cases — wrong values caught
# --------------------------------------------------------------------------- #

def test_wrong_price_caught(price_source) -> None:
    """Agent quotes 456,500 but source says 480,500 — must catch."""
    draft = "최종가는 456,500원이에요."
    mismatches = verify_draft(draft, price_source)
    assert len(mismatches) == 1
    assert mismatches[0].field == "price"
    assert mismatches[0].value == "456,500원"


def test_hallucinated_goods_no_caught(product_list_source) -> None:
    """G000000999999 is not in source — flag it."""
    draft = "추천 상품은 G000000999999 입니다."
    mismatches = verify_draft(draft, product_list_source)
    assert mismatches == [Mismatch(field="goods_no", value="G000000999999")]


def test_hallucinated_shop_id_caught(store_source) -> None:
    """F999999 / C99999 not in source — flag."""
    draft = "F999999 매장에서 받으실 수 있어요."
    mismatches = verify_draft(draft, store_source)
    assert mismatches == [Mismatch(field="shop_id", value="F999999")]


def test_multiple_mismatches_reported(price_source) -> None:
    draft = "최종가 456,500원, 상품번호 G000000999999"
    mismatches = verify_draft(draft, price_source)
    fields = sorted(m.field for m in mismatches)
    # price_source contains a goods_no, so goods_no check is active.
    assert "price" in fields
    assert "goods_no" in fields


def test_correct_and_wrong_mixed(price_source) -> None:
    """One correct price, one wrong — only the wrong one flagged."""
    draft = "최종가 480,500원, 옆 매장 가격 999,999원"
    mismatches = verify_draft(draft, price_source)
    assert len(mismatches) == 1
    assert mismatches[0].value == "999,999원"


def test_member_cheapest_price_field_still_catches_unknown_amount() -> None:
    source = [
        (
            "get_product_description_tool",
            {
                "status": "success",
                "data": {
                    "goods_no": "G000000310283",
                    "cheapest_final_prc": 122300,
                    "cheapest_total_discount": 6400,
                },
            },
        )
    ]
    mismatches = verify_draft("회원 최저가는 119,900원이에요.", source)
    assert mismatches == [Mismatch(field="price", value="119,900원")]


# --------------------------------------------------------------------------- #
#  Tire-size cases
# --------------------------------------------------------------------------- #

@pytest.fixture
def tire_size_source() -> list[tuple[str, dict]]:
    return [
        (
            "search_product_tool",
            {
                "data": {
                    "items": [
                        {"goods_no": "G000000317727", "tire_size_1": "235/55R19"},
                        {"goods_no": "G000000317729", "tire_size_1": "225/45ZR17"},
                    ]
                }
            },
        )
    ]


def test_known_tire_size_passes(tire_size_source) -> None:
    draft = "이 차량에는 235/55R19 사이즈를 권장해요."
    assert verify_draft(draft, tire_size_source) == []


def test_tire_size_case_insensitive(tire_size_source) -> None:
    """Source may store '235/55r19'; draft writes '235/55R19'. Same size."""
    src = [("t", {"data": {"items": [{"tire_size_1": "235/55r19"}]}})]
    draft = "권장 사이즈: 235/55R19"
    assert verify_draft(draft, src) == []


def test_hallucinated_tire_size_caught(tire_size_source) -> None:
    """245/40R18 not in source — flag."""
    draft = "이 차량에는 245/40R18 사이즈를 권장해요."
    mismatches = verify_draft(draft, tire_size_source)
    assert mismatches == [Mismatch(field="tire_size", value="245/40R18")]


def test_zr_tire_size_passes(tire_size_source) -> None:
    """ZR (speed-rated) tires must match exactly."""
    draft = "퍼포먼스용으로 225/45ZR17 추천드려요."
    assert verify_draft(draft, tire_size_source) == []


def test_lt_truck_tire_size_passes() -> None:
    src = [("t", {"data": {"items": [{"tire_size_1": "LT235/85R16"}]}})]
    draft = "트럭용 LT235/85R16 권장합니다."
    assert verify_draft(draft, src) == []


def test_duplicate_tire_size_flagged_once(tire_size_source) -> None:
    """Same hallucinated size mentioned twice should produce one mismatch."""
    draft = "245/40R18 권장. 245/40R18 재고 확인 가능."
    mismatches = verify_draft(draft, tire_size_source)
    assert len(mismatches) == 1
    assert mismatches[0].field == "tire_size"


def test_tire_size_check_skipped_when_source_empty() -> None:
    """Verifier stays conservative when no source sizes are available."""
    src = [("t", {"data": {"items": []}})]
    draft = "245/40R18 권장합니다."
    assert verify_draft(draft, src) == []


def test_available_sizes_list_counts_as_valid_tire_size_source() -> None:
    src = [
        (
            "search_product_tool",
            {
                "data": {
                    "items": [
                        {
                            "goods_no": "G000000317729",
                            "goods_nm": "아이온 에보 AS",
                            "available_sizes": ["235/35R20", "235/40R19", "245/35R21"],
                        }
                    ]
                }
            },
        )
    ]
    draft = "사이즈: 235/35R20, 235/40R19, 245/35R21"
    assert verify_draft(draft, src) == []


# --------------------------------------------------------------------------- #
#  Edge cases
# --------------------------------------------------------------------------- #

def test_goods_no_check_skipped_when_source_empty() -> None:
    """If source has no goods_no at all, skip the check (verifier is conservative)."""
    source = [("get_faq_tool", {"data": {"faqs": []}})]
    draft = "상품번호 G000000999999"
    assert verify_draft(draft, source) == []


def test_shop_id_check_skipped_when_source_empty() -> None:
    source = [("get_faq_tool", {"data": {"faqs": []}})]
    draft = "F999999 매장에서"
    assert verify_draft(draft, source) == []


def test_price_with_zero_filtered_out() -> None:
    """Zero is below _MIN_PRICE; never collected, never flagged."""
    source = [("t", {"data": {"sale_prc": 0, "final_prc": 480500}})]
    draft = "최종가 480,500원"
    assert verify_draft(draft, source) == []


def test_collect_source_values_walks_nested() -> None:
    """Verifier must collect prices from arbitrarily nested structures."""
    sources = [
        (
            "x",
            {
                "data": {
                    "items": [
                        {"goods_no": "G000000111111", "sale_prc": 100000},
                        {"goods_no": "G000000222222", "sale_prc": 200000},
                    ]
                }
            },
        )
    ]
    values = collect_source_values(sources)
    assert values["prices"] == {100000, 200000}
    assert values["goods_no"] == {"G000000111111", "G000000222222"}


def test_collect_source_skips_non_pattern_strings() -> None:
    """A goods_no field with a junk value must not be collected."""
    sources = [("x", {"data": {"items": [{"goods_no": "INVALID-ID"}]}})]
    assert collect_source_values(sources)["goods_no"] == set()


# --------------------------------------------------------------------------- #
#  Store name
# --------------------------------------------------------------------------- #

def test_known_store_name_passes(store_source) -> None:
    assert verify_draft("티스테이션 강남점에서 확인해 보세요.", store_source) == []


def test_bare_store_name_without_brand_prefix_passes(store_source) -> None:
    assert verify_draft("한남점 방문을 추천드려요.", store_source) == []


def test_hallucinated_store_name_caught(store_source) -> None:
    mismatches = verify_draft("티스테이션 역삼점에서 확인해 보세요.", store_source)
    assert Mismatch(field="store_name", value="역삼점") in mismatches


def test_generic_jeom_suffix_nouns_do_not_false_positive(store_source) -> None:
    """1-syllable and denylisted "-점" nouns are common prose, not store names."""
    draft = "각각 장단점이 있고, 결정은 고객님의 관점과 시점에 따라 달라질 수 있어요."
    assert verify_draft(draft, store_source) == []


def test_service_text_musangjeomgeom_does_not_false_positive(store_source) -> None:
    """"무상점검" in a store's service list must not be read as store name "무상점"."""
    draft = "서비스: 휠얼라이먼트, 무상점검"
    assert verify_draft(draft, store_source) == []


def test_store_name_check_skipped_when_source_empty() -> None:
    source = [("get_faq_tool", {"data": {"faqs": []}})]
    assert verify_draft("티스테이션 아무말점에서 확인해 보세요.", source) == []


# --------------------------------------------------------------------------- #
#  Date
# --------------------------------------------------------------------------- #

@pytest.fixture
def schedule_source() -> list[tuple[str, dict]]:
    """Mimics get_store_schedule_tool output."""
    return [
        (
            "get_store_schedule_tool",
            {
                "status": "success",
                "data": {
                    "dates": [
                        {"cal_day": "2026-07-15", "availableTimes": [10, 14]},
                        {"cal_day": "2026-07-16", "availableTimes": [11]},
                    ]
                },
            },
        )
    ]


def test_known_iso_date_passes(schedule_source) -> None:
    assert verify_draft("2026-07-15에 방문 가능해요.", schedule_source) == []


def test_korean_month_day_without_year_passes(schedule_source) -> None:
    """Casual Korean phrasing that omits the year must not be flagged."""
    assert verify_draft("7월 15일에 방문 가능해요.", schedule_source) == []


def test_korean_month_day_with_matching_year_passes(schedule_source) -> None:
    assert verify_draft("2026년 7월 15일에 방문 가능해요.", schedule_source) == []


def test_hallucinated_date_caught(schedule_source) -> None:
    mismatches = verify_draft("7월 20일에 방문 가능해요.", schedule_source)
    assert Mismatch(field="date", value="7월 20일") in mismatches


def test_date_check_skipped_when_source_empty() -> None:
    source = [("get_faq_tool", {"data": {"faqs": []}})]
    assert verify_draft("7월 20일에 방문 가능해요.", source) == []


# --------------------------------------------------------------------------- #
#  parse_tool_output
# --------------------------------------------------------------------------- #

def test_parse_tool_output_dict_passthrough() -> None:
    raw = {"data": {"goods_no": "G000000317727"}}
    assert parse_tool_output(raw) == raw


def test_parse_tool_output_json_string() -> None:
    raw = '{"data": {"goods_no": "G000000317727"}}'
    parsed = parse_tool_output(raw)
    assert parsed is not None
    assert parsed["data"]["goods_no"] == "G000000317727"


def test_parse_tool_output_invalid_json_returns_none() -> None:
    assert parse_tool_output("not json {{{") is None


def test_parse_tool_output_non_object_returns_none() -> None:
    """JSON array is valid JSON but not the expected dict shape."""
    assert parse_tool_output("[1, 2, 3]") is None


def test_parse_tool_output_empty_string_returns_none() -> None:
    assert parse_tool_output("") is None
    assert parse_tool_output(None) is None  # type: ignore[arg-type]
