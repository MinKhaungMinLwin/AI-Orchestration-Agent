from services.tstation.template_mapper import try_build_template


def test_quick_order_success_guides_user_to_order_form_page() -> None:
    order_form_data = {"cartNoArrStr": "15722", "goodsInfoArrStr": "G000000315068|4|Y"}
    event = try_build_template(
        [
            {
                "tool": "quick_order_tool",
                "args": {
                    "goods_no": "G000000315068",
                    "ord_qty": 4,
                    "shop_id": "F00721",
                    "rsv_date": "20260605",
                    "rsv_hour": "17",
                },
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "result": True,
                        "message": "",
                        "drtPurYn": "Y",
                        "data": order_form_data,
                    },
                },
            }
        ],
        "",
    )

    assert event is not None
    assert event["template"] == "orderComplete"
    message = event["data"]["assistantResponse"]
    assert "주문서가 준비되었습니다" in message
    assert "주문/결제 페이지" in message
    assert "완료" not in message
    assert "확정" not in message
    assert event["data"]["render"] is False
    assert event["data"]["autoMoveOrderPage"] is True
    assert event["data"]["moveOrderPageData"] == order_form_data


def test_save_to_cart_success_carries_product_quantity_metadata() -> None:
    event = try_build_template(
        [
            {
                "tool": "save_to_cart_tool",
                "args": {
                    "goods_no": "G000000309783",
                    "ord_qty": 2,
                },
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "result": True,
                        "message": "",
                        "drtPurYn": "N",
                        "data": {
                            "cartNoArrStr": "15766",
                            "goodsInfoArrStr": "G000000309783|2|Y",
                        },
                    },
                },
            },
            {
                "tool": "search_product_tool",
                "args": {"keyword": "벤투스 S2 AS", "size": "225/45R17"},
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309783",
                                "goods_nm": "벤투스 S2 AS",
                                "tire_size_1": "225/45R17",
                            }
                        ]
                    },
                },
            },
        ],
        "",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["data"]["metadata"] == {
        "goodsId": "G000000309783",
        "ordQty": 2,
        "productName": "벤투스 S2 AS",
        "quantity": 2,
        "tireSize": "225/45R17",
    }
