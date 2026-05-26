"""Unit tests for ConversationSlots goal_type inference.

Specifically protects the price_inquiry escalation when product keyword + qty
co-occur in the same turn, while preserving existing precedence rules.
"""

from schemas.tstation.slots import ConversationSlots


def _goal(text: str) -> str | None:
    return ConversationSlots.extract_from_user_text(text).goal_type


# --------------------------------------------------------------------------- #
# Positive: product keyword + qty in same turn → price_inquiry
# --------------------------------------------------------------------------- #

def test_product_keyword_with_qty_escalates_to_price_inquiry() -> None:
    assert _goal("벤투스 S2 AS 245/45R18 4개") == "price_inquiry"


def test_product_keyword_with_qty_only_no_size_still_escalates() -> None:
    assert _goal("벤투스 S2 4개") == "price_inquiry"


def test_other_model_keyword_with_qty_escalates() -> None:
    assert _goal("다이나프로 HPX 2개") == "price_inquiry"


# --------------------------------------------------------------------------- #
# Negative: qty without product keyword → unchanged (bare slot fill turn)
# --------------------------------------------------------------------------- #

def test_qty_only_no_keyword_does_not_escalate() -> None:
    assert _goal("4개") is None


def test_size_and_qty_without_keyword_does_not_escalate() -> None:
    assert _goal("245/45R18 4개") is None


# --------------------------------------------------------------------------- #
# Negative: product keyword without qty → product_search (preserved)
# --------------------------------------------------------------------------- #

def test_product_keyword_alone_stays_product_search() -> None:
    assert _goal("벤투스 S2 AS") == "product_search"


def test_product_keyword_with_size_no_qty_stays_product_search() -> None:
    assert _goal("벤투스 S2 AS 245/45R18") == "product_search"


def test_mileage_product_like_query_goes_to_product_search() -> None:
    assert _goal("마일리지 타이어") == "product_search"
    assert _goal("마일리지 타이어 추천") == "product_search"
    assert _goal("마일리지 플러스 2") == "product_search"
    assert _goal("마일리지 플러스 3 추천해줘") == "product_search"


def test_mileage_attribute_query_stays_recommendation() -> None:
    assert _goal("마일리지 좋은 타이어 추천") == "product_recommend"
    assert _goal("수명 긴 타이어 추천") == "product_recommend"


# --------------------------------------------------------------------------- #
# Precedence: explicit intent verbs win over the new branch
# --------------------------------------------------------------------------- #

def test_explicit_price_keyword_keeps_price_inquiry() -> None:
    assert _goal("벤투스 4개 가격 얼마야") == "price_inquiry"


def test_explicit_order_keyword_wins_over_qty_escalation() -> None:
    assert _goal("벤투스 4개 주문할게") == "place_order"


def test_explicit_stock_keyword_wins_over_qty_escalation() -> None:
    assert _goal("벤투스 4개 재고 있어?") == "store_with_stock"


def test_recommend_keyword_wins_over_qty_escalation() -> None:
    assert _goal("벤투스 4개 추천해줘") == "product_recommend"


def test_reservation_keyword_wins_over_qty_escalation() -> None:
    assert _goal("벤투스 4개 예약하고 싶어") == "store_finder"


def test_store_finder_captures_unverifiable_preference_text() -> None:
    slots = ConversationSlots.extract_from_user_text("내 차 타스만인데 리프트 있어야 되더라고... 하남 지역에 리프트 있는 매장 있어?")

    assert slots.goal_type == "store_finder"
    assert slots.region == "하남"
    assert slots.user_preferences_text is not None
    assert "리프트" in slots.user_preferences_text


def test_region_change_clears_stale_store_identity() -> None:
    existing = ConversationSlots(
        goods_no="G000000312970",
        ord_qty=2,
        shop_id="F00302",
        shop_name="성남 선택 매장",
        region="부산",
        goal_type="place_order",
    )
    new_region = ConversationSlots.extract_from_user_text("성남은?")

    merged = existing.merge(new_region)

    assert merged.region == "성남"
    assert merged.shop_id is None
    assert merged.shop_name is None
    assert merged.goods_no == "G000000312970"
    assert merged.ord_qty == 2


def test_seoul_region_followup_is_extracted() -> None:
    slots = ConversationSlots.extract_from_user_text("서울은?")

    assert slots.region == "서울"
