from services.tstation.policies.ui_action_policy import datepick_slot_values_from_data


def test_datepick_followup_recovers_selected_date_and_first_available_hour() -> None:
    datepick = {
        "dates": [
            {
                "date": "2026\ub144 6\uc6d4 24\uc77c (\uc218)",
                "available": True,
                "availableTimes": [9, 13],
                "index": 0,
            }
        ],
        "selectedDate": 0,
        "metadata": {
            "shopId": "F00405",
            "shopName": "T-Station Gyeongpo",
            "goodsNo": "G000000317900",
            "productName": "Dynapro HPX",
            "tireSize": "235/55R19",
            "ordQty": 2,
        },
    }

    values = datepick_slot_values_from_data(
        datepick,
        user_text="\uc8fc\ubb38 \uc9c4\ud589\ud574\uc918",
    )

    assert values == {
        "shop_id": "F00405",
        "shop_name": "T-Station Gyeongpo",
        "goods_no": "G000000317900",
        "tire_model": "Dynapro HPX",
        "tire_size": "235/55R19",
        "ord_qty": 2,
        "rsv_hour": "09",
        "requested_cal_day": "20260624",
    }
