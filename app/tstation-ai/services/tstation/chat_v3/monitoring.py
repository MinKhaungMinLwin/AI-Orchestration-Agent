"""Customer-facing monitoring labels for Chat V3 Langfuse traces."""

from __future__ import annotations

import json
import re
from typing import Any

from config.env import settings

AF_DOMAIN: dict[str, str] = {
    "Product Compatibility AF": "DISCOVERY",
    "Product Recommendation AF": "DISCOVERY",
    "Product Description AF": "DISCOVERY",
    "Store AF": "TRANSACTION",
    "Price AF": "TRANSACTION",
    "Inventory AF": "TRANSACTION",
    "Order / Delivery AF": "TRANSACTION",
    "Quick Shopping AF": "TRANSACTION",
    "FAQ AF": "SUPPORT",
    "Fallback / Escalation AF": "SUPPORT",
}

V3_TOOL_TO_CUSTOMER_AF: dict[str, str] = {
    # Product Compatibility AF
    "check_compatibility_tool": "Product Compatibility AF",
    "get_user_vehicles_tool": "Product Compatibility AF",
    "get_my_cars_tool": "Product Compatibility AF",
    "search_car_model_tool": "Product Compatibility AF",
    "search_car_model_groups_tool": "Product Compatibility AF",
    "get_car_trims_tool": "Product Compatibility AF",
    # Product Recommendation AF
    "search_product_tool": "Product Recommendation AF",
    "search_product_summary_tool": "Product Recommendation AF",
    "get_products_recommendations_tool": "Product Recommendation AF",
    "get_best_selling_products_tool": "Product Recommendation AF",
    "get_newest_products_tool": "Product Recommendation AF",
    # Product Description AF
    "get_product_description_tool": "Product Description AF",
    "get_events_tool": "Product Description AF",
    "get_deals_tool": "Product Description AF",
    "get_benefit_event_deal_list_tool": "Product Description AF",
    "search_benefit_applicable_products_tool": "Product Description AF",
    "get_event_applicable_products_tool": "Product Description AF",
    "get_product_applicable_events_tool": "Product Description AF",
    # Store AF
    "search_place_tool": "Store AF",
    "get_nearby_stores_tool": "Store AF",
    "get_store_list_tool": "Store AF",
    "search_stores_tool": "Store AF",
    "search_stores_complex_tool": "Store AF",
    "get_store_detail_tool": "Store AF",
    "get_store_schedule_tool": "Store AF",
    "get_multi_store_schedule_tool": "Store AF",
    "get_store_install_availability_tool": "Store AF",
    "get_stores_with_time_filter_tool": "Store AF",
    "transaction_store_preview_tool": "Store AF",
    "get_favorite_stores_tool": "Store AF",
    # Price AF
    "get_final_price_tool": "Price AF",
    "compare_discount_tool": "Price AF",
    "get_cheapest_price_tool": "Price AF",
    "get_my_coupons_tool": "Price AF",
    "get_coupon_applicable_products_tool": "Price AF",
    "get_product_promotions_tool": "Price AF",
    "issue_coupon_tool": "Price AF",
    # Inventory AF
    "get_store_inventory_tool": "Inventory AF",
    "get_logistics_inventory_tool": "Inventory AF",
    # Order / Delivery AF
    "get_order_status_tool": "Order / Delivery AF",
    "get_orders_of_user_tool": "Order / Delivery AF",
    "get_maintenance_history_tool": "Order / Delivery AF",
    "get_my_reservations_tool": "Order / Delivery AF",
    # Quick Shopping AF
    "present_order_preview_tool": "Quick Shopping AF",
    "save_to_cart_tool": "Quick Shopping AF",
    "quick_order_tool": "Quick Shopping AF",
    # FAQ AF
    "search_faq_hybrid_tool": "FAQ AF",
    "get_product_warranties_tool": "FAQ AF",
    "get_my_warranties_tool": "FAQ AF",
    "get_maintenance_dday_tool": "FAQ AF",
    "get_card_installments_tool": "FAQ AF",
    "check_coupon_stacking_tool": "FAQ AF",
    # Fallback / Escalation AF
    "transfer_to_qna_tool": "Fallback / Escalation AF",
    "escalate_tool": "Fallback / Escalation AF",
}

TEMPLATE_TO_AF: dict[str, str] = {
    "product": "Product Recommendation AF",
    "location": "Store AF",
    "datepick": "Store AF",
    "preOrder": "Quick Shopping AF",
    "orderComplete": "Quick Shopping AF",
    "cartComplete": "Quick Shopping AF",
    "qnaComplete": "Fallback / Escalation AF",
    "quickReply": "FAQ AF",
}

_TAG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _slug(value: str) -> str:
    return _TAG_SANITIZE_RE.sub("_", value.lower()).strip("_")


def _parse_tool_output(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    if not isinstance(output, str):
        return {}
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_status(call: dict[str, Any]) -> str:
    output = call.get("output")
    if isinstance(output, str) and output.startswith("Tool error"):
        return "error"
    parsed = _parse_tool_output(output)
    status = str(parsed.get("status") or "").strip().lower()
    if status:
        return status
    return "success"


def _result_count(call: dict[str, Any] | None) -> int | None:
    if not call:
        return None
    parsed = _parse_tool_output(call.get("output"))
    candidates: list[Any] = []
    for container in (parsed, parsed.get("data") if isinstance(parsed.get("data"), dict) else {}):
        if not isinstance(container, dict):
            continue
        candidates.extend(
            container.get(key)
            for key in ("items", "stores", "products", "results", "dates", "vehicles", "orders")
        )
    for value in candidates:
        if isinstance(value, list):
            return len(value)
    for container in (parsed, parsed.get("data") if isinstance(parsed.get("data"), dict) else {}):
        if isinstance(container, dict):
            for key in ("total", "count", "result_count"):
                try:
                    return int(container[key])
                except (KeyError, TypeError, ValueError):
                    continue
    return None


def _status_reason(
    *,
    final_status: str,
    tool_errors: list[str],
    no_result_tools: list[str],
    fallback_used: bool,
    qc_corrected: bool,
) -> str:
    if final_status == "error":
        return "tool_error" if tool_errors else "runtime_error"
    if no_result_tools:
        return "tool_no_results"
    if fallback_used:
        return "fallback_response"
    if qc_corrected:
        return "qc_corrected"
    return "tool_success_with_template"


def _error_reason(status_reason: str) -> str:
    if status_reason in {
        "tool_error",
        "runtime_error",
        "tool_no_results",
        "fallback_response",
        "quick_reply_fallback",
        "qc_corrected",
    }:
        return status_reason
    return "none"


def _classify_status(
    *,
    tool_calls: list[dict[str, Any]],
    final_template: str,
    fallback_used: bool,
    qc_corrected: bool,
    runtime_error: bool = False,
) -> tuple[str, str, list[str], list[str]]:
    tool_errors = [str(call.get("name") or "") for call in tool_calls if _tool_status(call) == "error"]
    no_result_tools = [
        str(call.get("name") or "")
        for call in tool_calls
        if _tool_status(call) in {"no_results", "not_found"}
    ]
    if runtime_error or tool_errors:
        final_status = "error"
    elif no_result_tools or fallback_used:
        final_status = "fallback"
    elif qc_corrected:
        final_status = "partial_success"
    else:
        final_status = "success"
    reason = _status_reason(
        final_status=final_status,
        tool_errors=tool_errors,
        no_result_tools=no_result_tools,
        fallback_used=fallback_used,
        qc_corrected=qc_corrected,
    )
    if final_template == "quickReply" and not tool_calls and fallback_used:
        reason = "quick_reply_fallback"
    return final_status, reason, tool_errors, no_result_tools


def build_customer_monitoring(
    *,
    route_domains: list[str],
    tool_calls: list[dict[str, Any]],
    final_template: str,
    fallback_used: bool = False,
    qc_corrected: bool = False,
    runtime_error: bool = False,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    """Build customer-facing Domain → AF → Tool trace metadata and tags."""
    tool_path = [str(call.get("name") or "") for call in tool_calls if str(call.get("name") or "").strip()]
    af_path = _dedupe([V3_TOOL_TO_CUSTOMER_AF.get(tool) or "" for tool in tool_path])
    if not af_path and final_template:
        template_af = TEMPLATE_TO_AF.get(final_template)
        if template_af:
            af_path = [template_af]

    tool_domains = _dedupe([AF_DOMAIN.get(af) or "" for af in af_path])
    route_domains = _dedupe([str(domain).upper() for domain in route_domains])
    primary_tool = tool_path[-1] if tool_path else ""
    primary_call = next((call for call in reversed(tool_calls) if call.get("name") == primary_tool), None)
    primary_af = V3_TOOL_TO_CUSTOMER_AF.get(primary_tool) or (af_path[-1] if af_path else "")
    primary_domain = AF_DOMAIN.get(primary_af) or (tool_domains[-1] if tool_domains else (route_domains[0] if route_domains else ""))
    final_status, status_reason, tool_errors, no_result_tools = _classify_status(
        tool_calls=tool_calls,
        final_template=final_template,
        fallback_used=fallback_used,
        qc_corrected=qc_corrected,
        runtime_error=runtime_error,
    )

    metadata: dict[str, Any] = {
        "monitoring_schema": "chat_v3_customer_af_v1",
        "route_domains": route_domains,
        "tool_domains": tool_domains,
        "primary_domain": primary_domain,
        "af_path": af_path,
        "primary_af": primary_af,
        "tool_path": tool_path,
        "primary_tool": primary_tool,
        "tool_count": len(tool_path),
        "result_count": _result_count(primary_call),
        "final_template": final_template,
        "final_status": final_status,
        "status_reason": status_reason,
        "error_reason": _error_reason(status_reason),
        "tool_errors": tool_errors,
        "no_result_tools": no_result_tools,
        "fallback_used": fallback_used,
        "qc_corrected": qc_corrected,
        "user_visible": not runtime_error,
    }
    if latency_ms is not None:
        metadata["latency_ms"] = latency_ms

    env = settings.ENV.value if hasattr(settings.ENV, "value") else str(settings.ENV)
    tags = ["chat_v3", env, f"status:{final_status}"]
    tags.extend(f"domain:{_slug(domain)}" for domain in route_domains)
    tags.extend(f"tool_domain:{_slug(domain)}" for domain in tool_domains)
    tags.extend(f"af:{_slug(af.removesuffix(' AF'))}" for af in af_path)
    tags.extend(f"tool:{tool}" for tool in tool_path)
    if final_template:
        tags.append(f"template:{_slug(final_template)}")
    return {"metadata": metadata, "tags": _dedupe(tags)}
