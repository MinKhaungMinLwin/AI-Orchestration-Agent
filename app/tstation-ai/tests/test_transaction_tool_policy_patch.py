from services.tstation.agents.c_transaction_agent.tools import _apply_store_preview_policy_patch


def test_store_preview_policy_patch_fills_missing_location_and_quantity() -> None:
    goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos = _apply_store_preview_policy_patch(
        patch={
            "goods_no": "G000000309001",
            "quantity": 4,
            "region": "서초",
            "store_name": "서초점",
        },
        goods_no="G000000309001",
        ord_qty=0,
        region_code=None,
        store_nm=None,
        user_xpos=None,
        user_ypos=None,
    )

    assert goods_no == "G000000309001"
    assert ord_qty == 4
    assert region_code == "서초"
    assert store_nm == "서초점"
    assert user_xpos is None
    assert user_ypos is None


def test_store_preview_policy_patch_does_not_override_explicit_tool_args() -> None:
    goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos = _apply_store_preview_policy_patch(
        patch={
            "goods_no": "G000000309001",
            "quantity": 4,
            "region": "서초",
            "store_name": "서초점",
        },
        goods_no="G000000319999",
        ord_qty=2,
        region_code="강남",
        store_nm="강남점",
        user_xpos=127.0,
        user_ypos=37.5,
    )

    assert goods_no == "G000000319999"
    assert ord_qty == 2
    assert region_code == "강남"
    assert store_nm == "강남점"
    assert user_xpos == 127.0
    assert user_ypos == 37.5
