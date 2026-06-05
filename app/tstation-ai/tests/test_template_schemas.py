from __future__ import annotations

from pydantic import TypeAdapter

from services.tstation.agents.templates.schemas import PreOrderDataEvent


def test_preorder_schema_accepts_shop_seq_metadata() -> None:
    payload = {
        "type": "data",
        "template": "preOrder",
        "data": {
            "assistantResponse": "주문 정보를 확인해 주세요.",
            "orderInfo": {
                "carInfo": None,
                "product": "벤투스 S2 AS 225/45R17",
                "quantity": 4,
                "storeName": "티스테이션 판교점",
                "bookingDateTime": "2026년 6월 5일 (금) 17:00",
                "paymentAmount": 475200,
            },
            "isReadyToOrder": True,
            "isReadyToAddToCart": False,
            "metadata": {
                "goodsId": "G000000309783",
                "shopId": "F00721",
                "shopSeq": "F100001277",
                "carNo": None,
                "carLncCd": None,
            },
        },
    }

    event = TypeAdapter(PreOrderDataEvent).validate_python(payload)

    assert event.data.metadata.shopId == "F00721"
    assert event.data.metadata.shopSeq == "F100001277"
