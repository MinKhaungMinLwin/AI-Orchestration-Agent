import importlib.util
import json
from pathlib import Path


_APP_ROOT = Path(__file__).resolve().parents[1]
_POLICY_PATH = _APP_ROOT / "services/tstation/policies/inventory_response_policy.py"
_SPEC = importlib.util.spec_from_file_location("inventory_response_policy", _POLICY_PATH)
assert _SPEC and _SPEC.loader
_POLICY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_POLICY)
redact_inventory_output_for_model = _POLICY.redact_inventory_output_for_model


def test_redact_inventory_output_for_model_lowers_quantities_to_availability_signals() -> None:
    output = json.dumps(
        {
            "status": "success",
            "data": {
                "todayShopArray": [
                    {
                        "shopId": "F00071",
                        "shopName": "티스테이션 한남점",
                        "status": "AVAILABLE",
                        "stock_qty": 8,
                        "total_qty": "12",
                    }
                ],
                "tnaShopArray": [{"shopId": "F07782", "qty": 0}],
            },
        },
        ensure_ascii=False,
    )

    redacted = json.loads(redact_inventory_output_for_model("get_store_inventory_tool", output))

    assert "status" not in redacted
    today = redacted["data"]["todayShopArray"][0]
    assert today["shopId"] == "F00071"
    assert today["shopName"] == "티스테이션 한남점"
    assert today["status"] == "AVAILABLE"
    assert today["stock_qty"] == "available_quantity_redacted"
    assert today["total_qty"] == "available_quantity_redacted"
    assert redacted["data"]["tnaShopArray"][0]["qty"] == "unavailable_quantity_redacted"


def test_redact_inventory_output_for_model_keeps_non_inventory_tool_output() -> None:
    output = '{"status":"success","data":{"total_qty":12}}'

    assert redact_inventory_output_for_model("search_product_tool", output) == output


def test_redact_inventory_output_for_model_keeps_non_quantity_values() -> None:
    output = json.dumps(
        {
            "data": {
                "shop_id": "F00071",
                "goods_no": "G000000309780",
                "available": True,
                "inventory_status": "AVAILABLE",
            }
        },
        ensure_ascii=False,
    )

    redacted = json.loads(redact_inventory_output_for_model("get_logistics_inventory_tool", output))

    assert redacted["data"]["shop_id"] == "F00071"
    assert redacted["data"]["goods_no"] == "G000000309780"
    assert redacted["data"]["available"] is True
    assert redacted["data"]["inventory_status"] == "AVAILABLE"
