"""Unit tests for ConversationSlots goal_candidate inference.

Specifically protects the price_inquiry escalation when product keyword + qty
co-occur in the same turn, while preserving existing precedence rules.
"""

from schemas.tstation.slots import ConversationSlots


def _goal_candidate(text: str) -> str | None:
    return ConversationSlots.extract_from_user_text(text).goal_candidate


# --------------------------------------------------------------------------- #
# Positive: product keyword + qty in same turn → price_inquiry
# --------------------------------------------------------------------------- #

def test_product_keyword_with_qty_escalates_to_price_inquiry() -> None:
    assert _goal_candidate("벤투스 S2 AS 245/45R18 4개") == "price_inquiry"


def test_product_keyword_with_qty_only_no_size_still_escalates() -> None:
    assert _goal_candidate("벤투스 S2 4개") == "price_inquiry"


def test_other_model_keyword_with_qty_escalates() -> None:
    assert _goal_candidate("다이나프로 HPX 2개") == "price_inquiry"


# --------------------------------------------------------------------------- #
# Negative: qty without product keyword → unchanged (bare slot fill turn)
# --------------------------------------------------------------------------- #

def test_qty_only_no_keyword_does_not_escalate() -> None:
    assert _goal_candidate("4개") is None


def test_size_and_qty_without_keyword_does_not_escalate() -> None:
    assert _goal_candidate("245/45R18 4개") is None


# --------------------------------------------------------------------------- #
# Negative: product keyword without qty → product_search (preserved)
# --------------------------------------------------------------------------- #

def test_product_keyword_alone_stays_product_search() -> None:
    assert _goal_candidate("벤투스 S2 AS") == "product_search"


def test_product_keyword_with_size_no_qty_stays_product_search() -> None:
    assert _goal_candidate("벤투스 S2 AS 245/45R18") == "product_search"


def test_mileage_product_like_query_goes_to_product_search() -> None:
    assert _goal_candidate("마일리지 타이어") == "product_search"
    assert _goal_candidate("마일리지 타이어 추천") == "product_search"
    assert _goal_candidate("마일리지 플러스 2") == "product_search"
    assert _goal_candidate("마일리지 플러스 3 추천해줘") == "product_search"


def test_mileage_attribute_query_stays_recommendation() -> None:
    assert _goal_candidate("마일리지 좋은 타이어 추천") == "product_recommend"
    assert _goal_candidate("수명 긴 타이어 추천") == "product_recommend"


# --------------------------------------------------------------------------- #
# Precedence: explicit intent verbs win over the new branch
# --------------------------------------------------------------------------- #

def test_explicit_price_keyword_keeps_price_inquiry() -> None:
    assert _goal_candidate("벤투스 4개 가격 얼마야") == "price_inquiry"


def test_explicit_order_keyword_wins_over_qty_escalation() -> None:
    assert _goal_candidate("벤투스 4개 주문할게") == "price_inquiry"


def test_explicit_stock_keyword_wins_over_qty_escalation() -> None:
    assert _goal_candidate("벤투스 4개 재고 있어?") == "price_inquiry"


def test_recommend_keyword_wins_over_qty_escalation() -> None:
    assert _goal_candidate("벤투스 4개 추천해줘") == "product_recommend"


def test_reservation_keyword_wins_over_qty_escalation() -> None:
    assert _goal_candidate("벤투스 4개 예약하고 싶어") == "price_inquiry"


def test_store_finder_captures_unverifiable_preference_text() -> None:
    slots = ConversationSlots.extract_from_user_text("내 차 타스만인데 리프트 있어야 되더라고... 하남 지역에 리프트 있는 매장 있어?")

    assert slots.goal_type is None
    assert slots.goal_candidate == "store_finder"
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


def test_merge_does_not_promote_current_turn_goal_candidate_to_goal_type() -> None:
    existing = ConversationSlots(pending_intent="order", goal_type="place_order")
    new_turn = ConversationSlots.extract_from_user_text("벤투스 S2 AS 245/45R18 4개")

    merged = existing.merge(new_turn)

    assert new_turn.goal_candidate == "price_inquiry"
    assert new_turn.goal_type is None
    assert merged.goal_type == "place_order"


def test_runtime_product_change_keeps_size_quantity_region_but_clears_product_dependents() -> None:
    existing = ConversationSlots(
        goods_no="GOLD00000001",
        tire_model="벤투스 S2 AS",
        tire_size="245/45R18",
        ord_qty=4,
        region="분당",
        payment_amount=480000,
    )

    updated = existing.apply_runtime_values({"goods_no": "GNEW00000001"}, source="product_event")

    assert updated.goods_no == "GNEW00000001"
    assert updated.tire_model is None
    assert updated.payment_amount is None
    assert updated.tire_size == "245/45R18"
    assert updated.ord_qty == 4
    assert updated.region == "분당"


def test_runtime_size_change_requires_product_requery_but_keeps_model_quantity_store() -> None:
    existing = ConversationSlots(
        goods_no="GOLD00000001",
        tire_model="벤투스 S2 AS",
        tire_size="245/45R18",
        ord_qty=2,
        shop_id="F00721",
        payment_amount=240000,
    )

    updated = existing.apply_runtime_values({"tire_size": "225/45R18"}, source="user_size_change")

    assert updated.tire_size == "225/45R18"
    assert updated.goods_no is None
    assert updated.payment_amount is None
    assert updated.tire_model == "벤투스 S2 AS"
    assert updated.ord_qty == 2
    assert updated.shop_id == "F00721"


def test_named_store_stock_turn_extracts_store_name_without_region_reset() -> None:
    slots = ConversationSlots.extract_from_user_text("판교점에 ion evo as 재고 있어?")

    assert slots.pending_intent is None
    assert slots.intent_candidate == "stock"
    assert slots.goal_type is None
    assert slots.goal_candidate == "product_search"
    assert slots.shop_name == "판교점"
    assert slots.region is None


def test_policy_like_purchase_text_keeps_quantity_but_not_transactional_pending_intent() -> None:
    slots = ConversationSlots.extract_from_user_text(
        "주문 선착순으로 사은품 주는 이벤트가 진행중일때 선착순 끝났으면 결제해도 사은품 안줘?"
    )

    assert slots.ord_qty is None
    assert slots.pending_intent is None
    assert slots.goal_type is None


def test_runtime_store_change_clears_store_dependent_amount() -> None:
    existing = ConversationSlots(
        goods_no="G000000312970",
        tire_size="245/45R18",
        ord_qty=2,
        shop_id="F00001",
        payment_amount=240000,
    )

    updated = existing.apply_runtime_values({"shop_id": "F00002"}, source="store_selection")

    assert updated.shop_id == "F00002"
    assert updated.payment_amount is None
    assert updated.goods_no == "G000000312970"
    assert updated.tire_size == "245/45R18"
    assert updated.ord_qty == 2


def test_runtime_vehicle_change_clears_vehicle_bound_product_slots() -> None:
    existing = ConversationSlots(
        car_no="12가3456",
        car_model="K7",
        car_lnc_cd="OLD",
        mbr_car_reg_seq="1",
        tire_size="245/45R18",
        tire_size_front="245/45R18",
        tire_size_rear="245/45R18",
        goods_no="G000000312970",
        payment_amount=240000,
    )

    updated = existing.apply_runtime_values({"car_no": "34나5678"}, source="vehicle_selection")

    assert updated.car_no == "34나5678"
    assert updated.car_model is None
    assert updated.car_lnc_cd is None
    assert updated.mbr_car_reg_seq is None
    assert updated.tire_size is None
    assert updated.tire_size_front is None
    assert updated.tire_size_rear is None
    assert updated.goods_no is None
    assert updated.payment_amount is None


def test_seoul_region_followup_is_extracted() -> None:
    slots = ConversationSlots.extract_from_user_text("서울은?")

    assert slots.region == "서울"
