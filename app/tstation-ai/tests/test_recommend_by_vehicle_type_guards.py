"""Step 6 — Gap B transition guard + negative-drift guards for the
recommend-by-vehicle-type feature.

Kept at the slots / intent-policy / helper layer so it runs without importing the
chat orchestration stack (which pulls the langgraph agent import).

Coverage map to plan section 1.3 / Step 6:
- T1/T2: Gap B — a card picked from an unsized vehicle-type recommendation is a
  concrete SKU; when the user then enters a different size the stale goods_no must
  be invalidated before the purchase continues on the correct SKU.
- N2: SUV/passenger compatibility question stays advice, not a recommendation.
- N3: negative-ownership + plate only still asks for owner name.
- N4: a size-tied request never carries a model_inference marker.
- N5: best-seller intent is not polluted by catalog vehicle_type inference.

N1 (registered vehicle uses its real size) and N7 (multi-car listCar) are
prompt-driven and locked by the b_discovery_agent prompt (Step 3); N6 (모델Y → ev
via catalog) is covered in test_discovery_intent_policy.
"""

from schemas.tstation.slots import ConversationSlots
from services.tstation.helpers.vehicle import (
    _non_self_vehicle_plate_owner_lookup_prompt_event,
    _vehicle_type_compatibility_guard_event,
)
from services.tstation.policies.discovery_intent_policy import (
    build_discovery_intent_frame,
    is_best_seller_request,
)


# --- T1 / T2: Gap B wrong-SKU guard ------------------------------------------


def test_t1_size_change_after_card_pick_invalidates_stale_goods_no() -> None:
    # Unsized SUV recommendation -> user picked a concrete SKU card (size X).
    picked = ConversationSlots(
        goods_no="G-SUV-SIZE-X",
        tire_size="235/60R18",
        payment_amount=500_000,
    )
    # User then supplies a different size Y.
    resized = picked.merge(ConversationSlots(tire_size="245/45R18"))

    assert resized.tire_size == "245/45R18"
    # goods_no belonged to size X -> must be cleared so the SKU is re-resolved.
    assert resized.goods_no is None
    assert resized.payment_amount is None


def test_t2_reresolved_sku_for_new_size_continues_cleanly() -> None:
    picked = ConversationSlots(goods_no="G-SUV-SIZE-X", tire_size="235/60R18")
    resized = picked.merge(ConversationSlots(tire_size="245/45R18"))
    assert resized.goods_no is None

    # A fresh SKU resolved for the new size takes over without re-clearing.
    reresolved = resized.merge(ConversationSlots(goods_no="G-NEW-SIZE-Y", tire_size="245/45R18"))
    assert reresolved.goods_no == "G-NEW-SIZE-Y"
    assert reresolved.tire_size == "245/45R18"


# --- N2: compatibility advice, not recommendation ----------------------------


def test_n2_suv_passenger_compatibility_stays_advice() -> None:
    event = _vehicle_type_compatibility_guard_event("내 차 SUV인데 승용차 타이어 껴도 돼?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_vehicle_type_compatibility_guard"


# --- N3: negative ownership + plate only asks for owner name ------------------


def test_n3_negative_ownership_plate_only_prompts_for_owner() -> None:
    event = _non_self_vehicle_plate_owner_lookup_prompt_event("내차말고 09조8765")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "차량번호 + 소유주명" in event["data"]["assistantResponse"]


# --- N4: size-tied request carries no model inference -------------------------


def test_n4_size_tied_request_has_no_model_inference() -> None:
    frame = build_discovery_intent_frame("225/45R17 추천해줘")

    assert frame.entities.get("vehicle_category") is None
    assert "vehicle_category_source" not in frame.entities


# --- N5: best-seller not polluted by catalog vehicle_type --------------------


def test_n5_best_seller_intent_not_polluted_by_vehicle_type() -> None:
    frame = build_discovery_intent_frame("인기 타이어 추천")

    assert is_best_seller_request("인기 타이어 추천") is True
    assert frame.entities.get("vehicle_category") is None
    assert "vehicle_category_source" not in frame.entities
