"""Validation and intersection logic for multi-product installation availability."""

from typing import Any


def _available_stores(data: Any) -> dict[str, dict[str, Any]]:
    """Return installable schedule rows whose product status is available."""
    items = data.get("items") if isinstance(data, dict) else None
    schedule = data.get("schedule") if isinstance(data, dict) else None
    stores = schedule.get("stores") if isinstance(schedule, dict) else None
    if not isinstance(items, list) or not isinstance(stores, list):
        return {}
    available_ids = {
        str(item.get("shop_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("status") or "").strip() == "available"
    }
    return {
        shop_id: store
        for store in stores
        if isinstance(store, dict) and bool(store.get("is_installable"))
        for shop_id in [str(store.get("shop_id") or "").strip()]
        if shop_id in available_ids
    }


def combine_install_availability(
    *,
    results: list[dict],
    candidate_shop_ids: list[str],
    requested_cal_day: str | None,
) -> dict[str, Any]:
    """Intersect installable stores and exact schedule slots across product results."""
    store_maps = [
        _available_stores(result.get("data") if isinstance(result.get("data"), dict) else {}) for result in results
    ]
    common_shop_ids = set(store_maps[0])
    for store_map in store_maps[1:]:
        common_shop_ids.intersection_update(store_map)

    combined_stores: list[dict[str, Any]] = []
    for shop_id in candidate_shop_ids:
        if shop_id not in common_shop_ids:
            continue
        stores = [store_map[shop_id] for store_map in store_maps]
        slot_sets = [
            {
                (str(slot.get("cal_day") or "").strip(), str(slot.get("tm") or "").strip())
                for slot in store.get("slots", [])
                if isinstance(slot, dict) and slot.get("cal_day") and slot.get("tm")
            }
            for store in stores
        ]
        common_slots = sorted(set.intersection(*slot_sets))
        if not common_slots:
            continue
        first_day = common_slots[0][0]
        combined_stores.append(
            {
                "shop_id": shop_id,
                "shop_nm": stores[0].get("shop_nm"),
                "status": "available",
                "is_installable": True,
                "first_available_slot": {"cal_day": common_slots[0][0], "tm": common_slots[0][1]},
                "available_times_on_first_day": [tm for cal_day, tm in common_slots if cal_day == first_day],
            }
        )

    schedule: dict[str, Any] = {
        "tier": "combined",
        "stores": combined_stores,
        "candidate_shop_ids": candidate_shop_ids,
    }
    requested_day = str(requested_cal_day or "").strip()
    if requested_day:
        schedule["requested_cal_day"] = requested_day
    first_slot = min(
        (store["first_available_slot"] for store in combined_stores),
        key=lambda slot: (slot["cal_day"], slot["tm"]),
        default=None,
    )
    return {
        "items": combined_stores,
        "combined": {
            "all_products_available_together": bool(combined_stores),
            "common_shop_ids": [store["shop_id"] for store in combined_stores],
            "first_available_slot": first_slot,
        },
        "schedule": schedule,
    }
