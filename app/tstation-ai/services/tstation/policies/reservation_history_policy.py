"""Deterministic response builders for reservation history lookups."""

from __future__ import annotations

import re
from typing import Any, Mapping

from services.tstation.common.cta_urls import CTAUrls


_ORDER_DIRECT_NO_RE = re.compile(r"\bO[A-Za-z0-9]{8,}\b", re.IGNORECASE)


def _unwrap_tool_data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        data = payload.get("data")
        return dict(data) if isinstance(data, Mapping) else dict(payload)
    return {}


def _format_store_phone(raw: str) -> str:
    digits = re.sub(r"\D+", "", str(raw or ""))
    if not digits:
        return ""
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:]}"
    if digits.startswith("02") and len(digits) in {9, 10}:
        return f"{digits[:2]}-{digits[2:-4]}-{digits[-4:]}"
    if len(digits) in {10, 11}:
        return f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    return str(raw or "").strip()


def _reservation_rows_from_result(tool_result: dict) -> list[dict]:
    data = _unwrap_tool_data(tool_result)
    rows = data.get("reservations") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        rows = data.get("items") if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _reservation_row_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value in (None, "") and isinstance(row.get("detail"), dict):
            value = row["detail"].get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _reservation_sort_key(row: dict) -> str:
    return _reservation_row_value(row, "vst_rsv_dtime", "rsv_dtime", "sys_reg_dtime", "ord_dtime")


def select_reservation_store_row(user_text: str, reservations_result: dict) -> tuple[dict | None, str]:
    rows = sorted(_reservation_rows_from_result(reservations_result), key=_reservation_sort_key, reverse=True)
    if not rows:
        return None, "no_reservation"
    direct_order = _ORDER_DIRECT_NO_RE.search(user_text or "")
    if direct_order:
        ord_no = direct_order.group(0).upper()
        matches = [row for row in rows if _reservation_row_value(row, "ord_no", "ordNo").upper() == ord_no]
        if matches:
            return matches[0], "order_number"
        return None, "order_number_not_found"
    if len(rows) == 1:
        return rows[0], "single_reservation"
    return None, "ambiguous"


def build_reservation_store_not_found_event(reason: str) -> dict:
    if reason == "ambiguous":
        response = "예약 내역이 여러 건 있어요. 어느 예약 건의 매장인지 선택해 주세요."
        quick_replies = [
            {"label": "내 예약 조회", "domain": "TRANSACTION"},
            {"label": "주문번호로 확인", "domain": "TRANSACTION"},
        ]
    else:
        response = "예약 내역을 먼저 확인해야 해요. 주문번호나 예약번호가 있으면 알려주세요."
        quick_replies = [
            {"label": "내 예약 조회", "domain": "TRANSACTION"},
            {"label": "내 주문 조회", "domain": "TRANSACTION"},
        ]
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_reservation_store_info_lookup",
        "data": {
            "assistantResponse": response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "responseShapeKey": "reservation_store_info_lookup",
                "reservationStoreSource": "reservation_history",
                "matchReason": reason,
            },
        },
    }


def build_reservation_store_info_event(reservation_row: dict, *, match_reason: str) -> dict:
    shop_nm = _reservation_row_value(reservation_row, "shop_nm", "shopName", "store_name", "storeName")
    tel_no = _format_store_phone(_reservation_row_value(reservation_row, "tel_no", "tel", "phone", "shop_tel_no"))
    address = " ".join(
        part
        for part in (
            _reservation_row_value(reservation_row, "road_addr_base", "addr_base", "address"),
            _reservation_row_value(reservation_row, "road_addr_dtl", "addr_dtl"),
        )
        if part
    ).strip()
    rsv_dtime = _reservation_row_value(reservation_row, "vst_rsv_dtime", "rsv_dtime")
    rsv_label = _reservation_row_value(reservation_row, "shop_rsv_sct_label", "reservationType") or "예약"
    ord_no = _reservation_row_value(reservation_row, "ord_no", "ordNo")

    lines = ["예약 내역 기준으로 매장 정보를 확인했어요."]
    if rsv_label:
        lines.append(f"- 예약 유형: {rsv_label}")
    if ord_no:
        lines.append(f"- 주문번호: {ord_no}")
    if shop_nm:
        lines.append(f"- 예약하신 매장: {shop_nm}")
    if tel_no:
        lines.append(f"- 전화번호: {tel_no}")
    else:
        lines.append("- 전화번호: 예약 내역에서 확인되지 않았어요.")
    if address:
        lines.append(f"- 주소: {address}")
    if rsv_dtime:
        lines.append(f"- 예약 일시: {rsv_dtime}")

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_reservation_store_info_lookup",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "내 예약 조회", "domain": "TRANSACTION"},
                {"label": "내 주문 조회", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "responseShapeKey": "reservation_store_info_lookup",
                "reservationStoreSource": "reservation_history",
                "matchReason": match_reason,
                "shopName": shop_nm,
                "telNo": tel_no,
                "ordNo": ord_no,
            },
        },
    }


def build_reservation_status_lookup_event(reservations_result: dict) -> dict:
    rows = sorted(_reservation_rows_from_result(reservations_result), key=_reservation_sort_key, reverse=True)
    metadata = {
        "responseShapeKey": "reservation_status_lookup",
        "reservationStatusSource": "reservation_history",
        "reservationCount": len(rows),
    }
    if not rows:
        response = "예약 내역을 확인했지만 현재 예약된 매장 방문은 찾지 못했어요."
        quick_replies = [
            {"label": "매장 찾기", "domain": "TRANSACTION"},
            {"label": "주문 내역 보기", "url": CTAUrls.ORDER_HISTORY, "domain": "TRANSACTION"},
        ]
    else:
        lines = ["예약 내역을 확인했어요."]
        for idx, row in enumerate(rows[:3], start=1):
            shop_nm = _reservation_row_value(row, "shop_nm", "shopName", "store_name", "storeName") or "매장명 확인 필요"
            rsv_dtime = _reservation_row_value(row, "vst_rsv_dtime", "rsv_dtime") or "예약 일시 확인 필요"
            status = _reservation_row_value(row, "shop_vst_rsv_sts_label", "status_nm", "status") or "상태 확인 필요"
            rsv_label = _reservation_row_value(row, "shop_rsv_sct_label", "reservationType")
            label_part = f" / {rsv_label}" if rsv_label else ""
            lines.append(f"{idx}. {shop_nm} / {rsv_dtime} / {status}{label_part}")
        if len(rows) > 3:
            lines.append(f"외 {len(rows) - 3}건은 예약 내역에서 확인해 주세요.")
        response = "\n".join(lines)
        quick_replies = [
            {"label": "주문 내역 보기", "url": CTAUrls.ORDER_HISTORY, "domain": "TRANSACTION"},
            {"label": "다른 예약 확인", "domain": "TRANSACTION"},
        ]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_reservation_status_lookup",
        "data": {
            "assistantResponse": response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
            "metadata": metadata,
        },
    }
