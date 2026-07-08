import os

from schemas.tstation.slots import ConversationSlots
from services.tstation.agents.templates.schemas import DatepickTemplate, ProductItem, ProductMeta, ProductTemplate, ScheduleItem
from schemas.tstation.chat import TStationChatRequest


for key in (
    "PROJECT_NAME",
    "ROOT_PATH",
    "API_SECRET_KEY",
    "TSTATION_BE_API",
    "TSTATION_BE_MCP",
    "AI_DEFAULT_PROVIDER",
    "AI_GATEWAY_BASE_URL",
    "AI_GATEWAY_API_KEY",
    "AI_MODEL",
    "AI_MODEL_REASONING",
    "AI_MODEL_MINI",
    "AI_MODEL_LEADING_AGENT",
    "AI_MODEL_QC_AGENT",
    "AI_MODEL_TRANSACTION_AGENT",
    "UPSTAGE_API_KEY",
    "OPENAI_API_KEY",
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD",
    "REDIS_CONVERSATION_MANAGEMENT_URL",
    "REDIS_QUEUE_URL",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_NODENAME",
    "RABBITMQ_USERNAME",
    "RABBITMQ_PASSWORD",
    "RABBITMQ_URL",
    "RABBITMQ_URL_MANAGEMENT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "S3_BUCKET_NAME",
    "GF_SECURITY_ADMIN_USER",
    "GF_SECURITY_ADMIN_PASSWORD",
    "LOKI_URL",
    "PROMETHEUS_URL",
    "LANGFUSE_HOST",
    "LANGFUSE_PROJECT_NAME",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
):
    os.environ.setdefault(key, "test")
os.environ["REDIS_CONVERSATION_MANAGEMENT_URL"] = "redis://localhost:6379/0"
os.environ["REDIS_QUEUE_URL"] = "redis://localhost:6379/1"
os.environ["REDIS_URL"] = "redis://localhost:6379/2"

from services.tstation.chat_v3.slots.derive import fe_slot_patch  # noqa: E402
from services.tstation.chat_v3.templates import _normalize_datepick_payload, _normalize_product_selection_payload  # noqa: E402


def test_order_product_template_carries_select_product_slots() -> None:
    payload = ProductTemplate(
        assistantResponse="Select a product.",
        products=[
            ProductItem(
                imageUrl="https://example.com/tire.png",
                title="Ventus S2 AS 245/45R19",
                tires="245/45R19",
                titleProductName="Ventus S2 AS",
                titleTires="245/45R19",
                brandName="HANKOOK",
                price=180500,
                rate=4.5,
                totalQuantity=68,
            )
        ],
        metadata=[ProductMeta(goodsId="G000000310126")],
    )
    slots = ConversationSlots(pending_intent="order", goal_type="place_order")

    _normalize_product_selection_payload(payload, slots)

    assert payload.isBookingFlow is True
    assert payload.metadata[0].goodsNo == "G000000310126"
    assert payload.metadata[0].goods_no == "G000000310126"
    assert payload.metadata[0].slots["goods_no"] == "G000000310126"
    assert payload.metadata[0].slots["tire_size"] == "245/45R19"
    assert payload.metadata[0].ui_action["action_type"] == "select_product"
    assert payload.metadata[0].ui_action["slots"]["goods_no"] == "G000000310126"


def test_fe_slot_patch_accepts_product_card_ui_action_slots() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "Ventus S2 AS 245/45R19"}],
        user_id="u1",
        session_id="s1",
        ui_action={
            "action_type": "select_product",
            "slots": {"goodsId": "G000000310126", "tire_size": "245/45R19"},
        },
    )

    assert fe_slot_patch(request) == {"goods_no": "G000000310126", "tire_size": "245/45R19"}


def test_order_datepick_template_carries_existing_order_slots() -> None:
    payload = DatepickTemplate(
        assistantResponse="Select a schedule.",
        dates=[ScheduleItem(date="20260709", available=True, availableTimes=[9, 10, 16], index=0)],
    )
    slots = ConversationSlots(
        goods_no="G000000310126",
        ord_qty=4,
        tire_model="Ventus S2 AS",
        pending_product_name="Ventus S2 AS",
        tire_size="245/45R19",
        shop_id="S0001",
        shop_name="T-Station Bundang",
        pending_intent="order",
        goal_type="place_order",
    )

    _normalize_datepick_payload(payload, slots)

    metadata_slots = payload.metadata["slots"]
    assert metadata_slots["goods_no"] == "G000000310126"
    assert metadata_slots["ord_qty"] == 4
    assert metadata_slots["shop_id"] == "S0001"
    assert metadata_slots["pending_intent"] == "order"
    assert payload.metadata["ui_action"]["slots"]["goods_no"] == "G000000310126"
