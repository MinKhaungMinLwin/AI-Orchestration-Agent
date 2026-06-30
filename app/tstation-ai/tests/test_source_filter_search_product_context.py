from __future__ import annotations

from services.tstation.source_filter import filter_for_context


def test_search_product_context_keeps_card_display_fields() -> None:
    result = filter_for_context(
        "search_product_tool",
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "G000000319584",
                        "goods_nm": "벤투스 에어S",
                        "tire_size_1": "245/45R19",
                        "image_url": "https://example.test/tire.png",
                        "sale_prc": 300000,
                        "extra_fvr_sale_prc": 261500,
                        "rating_avg": 4.6,
                        "review_count": 12,
                    }
                ]
            },
        },
        {"keyword": "벤투스 에어S", "size": "245/45R19"},
    )

    assert result is not None
    item = result["data"][0]
    assert item["image_url"] == "https://example.test/tire.png"
    assert item["sale_prc"] == 300000
    assert item["extra_fvr_sale_prc"] == 261500
    assert item["rating_avg"] == 4.6
    assert item["review_count"] == 12
