from services.tstation.policies.tool_arg_schema import canonicalize_tool_args_patch


def test_schedule_mode_canonicalizes_tna_only_store_over_stale_combined_mode() -> None:
    patch = canonicalize_tool_args_patch(
        preferred_tool="get_store_schedule_tool",
        existing_patch={"shop_id": "F07782", "mode": "in_store_logistics_combined"},
        known_slots={
            "todayShopArray": [],
            "tnaShopArray": [{"shopId": "F07782"}],
        },
    )

    assert patch == {"shop_id": "F07782", "mode": "tna_only"}


def test_schedule_mode_keeps_today_store_combined_mode() -> None:
    patch = canonicalize_tool_args_patch(
        preferred_tool="get_store_schedule_tool",
        existing_patch={"shop_id": "F00071", "mode": "in_store_logistics_combined"},
        known_slots={
            "todayShopArray": [{"shopId": "F00071"}],
            "tnaShopArray": [{"shopId": "F00071"}],
        },
    )

    assert patch == {"shop_id": "F00071", "mode": "in_store_logistics_combined"}


def test_search_product_keyword_normalizes_english_alias() -> None:
    patch = canonicalize_tool_args_patch(
        preferred_tool="search_product_tool",
        existing_patch={"keyword": "ventus air s", "limit": 10},
    )

    assert patch["keyword"] == "벤투스 에어S"


def test_search_product_keyword_normalizes_mixed_korean_alias() -> None:
    patch = canonicalize_tool_args_patch(
        preferred_tool="search_product_tool",
        existing_patch={"keyword": "벤투스 air s", "limit": 10},
    )

    assert patch["keyword"] == "벤투스 에어S"
