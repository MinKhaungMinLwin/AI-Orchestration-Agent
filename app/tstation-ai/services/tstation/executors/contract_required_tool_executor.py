import asyncio
import json
import re
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation import qc_verifier
from services.tstation.policies.contract_required_tool_candidate import (
    _OWNED_RECORD_RECOVERY_INTENTS,
    _OWNED_RECORD_RECOVERY_TOOLS,
    _contract_required_tool_candidate,
    _is_contract_required_selected_store_schedule,
    _is_contract_required_stock_inventory_selected_store,
    _is_contract_required_stock_inventory_store_lookup,
    _is_contract_required_transaction_store_preview,
    _is_contract_required_vehicle_recommendation,
    _is_vehicle_selection_recommendation_contract,
)
from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.intent_frame import PolicyDomain
from services.tstation.policies.resolved_context import (
    canonical_context_from_template_boundary,
    canonical_context_from_tool_boundary,
)
from services.tstation.policies.turn_contract import TurnContract


def _enrich_best_selling_result_for_product_cards(tool_result: dict) -> dict:
    data = tool_result.get("data") if isinstance(tool_result, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return tool_result

    from services.tstation.agents.b_discovery_agent.tools import enrich_product_card_items

    enriched_data = dict(data)
    enriched_data["items"] = enrich_product_card_items(data["items"])
    enriched_result = dict(tool_result)
    enriched_result["data"] = enriched_data
    return enriched_result


def _best_selling_general_fallback_input(
    tool_input: Mapping[str, Any],
    tool_result: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return a general best-seller retry input when a vehicle-scoped lookup has no cards."""
    original_vehicle_query = str(tool_input.get("vehicle_query") or "").strip()
    if not original_vehicle_query:
        return None
    data = tool_result.get("data") if isinstance(tool_result, Mapping) else None
    if not isinstance(data, Mapping):
        return None
    status = str(data.get("status") or "").strip().lower()
    if status not in {"resolved_no_order_data", "no_order_data"}:
        return None
    items = data.get("items")
    if isinstance(items, list) and items:
        return None
    fallback_input = {
        str(key): value
        for key, value in dict(tool_input).items()
        if key != "vehicle_query" and value not in (None, "", [], {})
    }
    fallback_input.setdefault("limit", 5)
    return fallback_input


def _contract_annotation_metadata(event_data: dict[str, Any]) -> dict[str, Any]:
    metadata = event_data.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    contract_metadata = event_data.get("contractMetadata")
    if isinstance(contract_metadata, dict):
        return contract_metadata
    contract_metadata = {}
    event_data["contractMetadata"] = contract_metadata
    return contract_metadata


def _annotate_contract_tool_recovery_event(
    event: dict[str, Any],
    *,
    turn_contract: TurnContract,
    blocked_fast_path_source: str,
    recovered_tool: str,
    recovery_reason: str,
    tool_input_source: str,
) -> dict[str, Any]:
    event["contract_intent"] = str(turn_contract.intent or "")
    event["allowed_tools"] = list(turn_contract.allowed_tools)
    event["blocked_tools"] = list(turn_contract.forbidden_tools)
    event["assistant_response_source"] = "contract_tool_recovery_after_fast_path_block"
    event["contract_tool_recovery"] = True
    event["blocked_fast_path_source"] = blocked_fast_path_source
    event["recovered_tool"] = recovered_tool
    event["recovery_reason"] = recovery_reason
    event["tool_input_source"] = tool_input_source
    event_data = event.get("data")
    if isinstance(event_data, dict):
        metadata = _contract_annotation_metadata(event_data)
        metadata["contract_intent"] = str(turn_contract.intent or "")
        metadata["allowed_tools"] = list(turn_contract.allowed_tools)
        metadata["blocked_tools"] = list(turn_contract.forbidden_tools)
        metadata["assistant_response_source"] = "contract_tool_recovery_after_fast_path_block"
        metadata["contract_tool_recovery"] = True
        metadata["blocked_fast_path_source"] = blocked_fast_path_source
        metadata["recovered_tool"] = recovered_tool
        metadata["recovery_reason"] = recovery_reason
        metadata["tool_input_source"] = tool_input_source
    return event


def _annotate_stock_inventory_store_lookup_event(
    event: dict[str, Any],
    *,
    turn_contract: TurnContract,
    tool_input: Mapping[str, Any],
) -> None:
    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "") if isinstance(response_metadata, Mapping) else ""
    if response_shape_key != "stock_inventory_lookup":
        return
    event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
    stores = event_data.get("stores") if isinstance(event_data, dict) else None
    metadata = event_data.get("metadata") if isinstance(event_data, dict) else None
    if not isinstance(stores, list) or not isinstance(metadata, list):
        return
    known_slots = turn_contract.known_slots or {}
    region = str(
        known_slots.get("region")
        or known_slots.get("place_query")
        or tool_input.get("region_code")
        or ""
    ).strip()
    common = {
        "sourceTool": "get_store_list_tool",
        "source_tool": "get_store_list_tool",
        "goodsNo": known_slots.get("goods_no"),
        "goods_no": known_slots.get("goods_no"),
        "tireSize": known_slots.get("tire_size"),
        "tire_size": known_slots.get("tire_size"),
        "ordQty": known_slots.get("ord_qty") or known_slots.get("quantity"),
        "ord_qty": known_slots.get("ord_qty") or known_slots.get("quantity"),
        "region": region,
        "pendingIntent": "stock",
        "pending_intent": "stock",
        "goalType": "store_with_stock",
        "goal_type": "store_with_stock",
        "stockCheckMode": "inventory_only",
        "stock_check_mode": "inventory_only",
        "inventoryMode": "inventory_only",
        "inventory_mode": "inventory_only",
    }
    for idx, meta in enumerate(metadata):
        if not isinstance(meta, dict):
            continue
        store = stores[idx] if idx < len(stores) and isinstance(stores[idx], Mapping) else {}
        canonical_store = canonical_context_from_template_boundary(meta)
        if not canonical_store:
            canonical_store = canonical_context_from_tool_boundary(store)
        shop_id = str(
            meta.get("shopId")
            or meta.get("shop_id")
            or canonical_store.get("shop_id")
            or ""
        ).strip()
        shop_name = str(
            meta.get("shopName")
            or meta.get("shop_name")
            or canonical_store.get("shop_name")
            or store.get("nameAddress")
            or store.get("name")
            or ""
        ).strip()
        if shop_id:
            meta.setdefault("shopId", shop_id)
            meta.setdefault("shop_id", shop_id)
            meta.setdefault("stableId", shop_id)
        if shop_name:
            meta.setdefault("shopName", shop_name)
            meta.setdefault("shop_name", shop_name)
        for key, value in common.items():
            if value not in (None, "", [], {}):
                meta.setdefault(key, value)


async def _recover_contract_required_store_flow_tool(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_store_flow_tool",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    if not (
        _is_contract_required_selected_store_schedule(turn_contract, merged_slots=merged_slots)
        or _is_contract_required_stock_inventory_store_lookup(turn_contract, merged_slots=merged_slots)
        or _is_contract_required_stock_inventory_selected_store(turn_contract, merged_slots=merged_slots)
    ):
        return None
    return await recover_blocked_fast_path_to_contract_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


async def _recover_contract_required_vehicle_recommendation(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_vehicle_recommendation",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    current_turn_direct_path = str(blocked_fast_path_source or "").startswith("contract_direct_executor:")
    if not current_turn_direct_path and not _is_contract_required_vehicle_recommendation(turn_contract, merged_slots):
        return None
    return await recover_blocked_fast_path_to_contract_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


async def _recover_contract_required_transaction_store_preview(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_transaction_store_preview",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    if not _is_contract_required_transaction_store_preview(turn_contract, merged_slots=merged_slots):
        return None
    return await recover_blocked_fast_path_to_contract_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


async def _recover_contract_required_owned_record_lookup(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_owned_record_lookup",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    if turn_contract is None:
        return None
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return None
    if str(turn_contract.intent or "").strip() not in _OWNED_RECORD_RECOVERY_INTENTS:
        return None
    preferred_tool = str(getattr(turn_contract, "preferred_tool", None) or "").strip()
    if preferred_tool not in _OWNED_RECORD_RECOVERY_TOOLS:
        return None
    return await recover_blocked_fast_path_to_contract_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


async def _recover_contract_required_flow_progress_tool(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_flow_progress_tool",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    if turn_contract is None:
        return None
    candidate = _contract_required_tool_candidate(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        member_no=member_no,
    )
    if candidate is None or candidate.tool_input_source != "flow_state_progress":
        return None
    return await recover_blocked_fast_path_to_contract_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


async def _recover_contract_required_tool(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_tool_executor",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    """Run the deterministic tool required by the current TurnContract, if one is known."""

    store_flow_recovery = await _recover_contract_required_store_flow_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )
    if store_flow_recovery is not None:
        return store_flow_recovery
    preview_recovery = await _recover_contract_required_transaction_store_preview(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )
    if preview_recovery is not None:
        return preview_recovery
    owned_record_recovery = await _recover_contract_required_owned_record_lookup(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )
    if owned_record_recovery is not None:
        return owned_record_recovery
    flow_progress_recovery = await _recover_contract_required_flow_progress_tool(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )
    if flow_progress_recovery is not None:
        return flow_progress_recovery
    return await _recover_contract_required_vehicle_recommendation(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        blocked_fast_path_source=blocked_fast_path_source,
        member_no=member_no,
    )


def contract_required_tool_start_event(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str = "contract_required_tool_executor",
    member_no: str | None = None,
) -> dict[str, Any] | None:
    """Preview the first deterministic contract tool status before the tool blocks."""

    if turn_contract is None:
        return None
    if tuple(getattr(turn_contract, "blocking_required_slots", ()) or ()):
        return None
    context_state = str(getattr(turn_contract, "context_state", "") or "")
    current_turn_vehicle_recommendation = _is_vehicle_selection_recommendation_contract(turn_contract)
    current_turn_direct_path = str(blocked_fast_path_source or "").startswith("contract_direct_executor:")
    if context_state not in {"active", "resumed"} and not current_turn_vehicle_recommendation and not current_turn_direct_path:
        return None

    candidate = _contract_required_tool_candidate(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        member_no=member_no,
    )
    if candidate is None:
        return None
    return {
        "type": "status",
        "status": "tool_start",
        "tool": candidate.tool_name,
        "display_name": candidate.display_name,
        "source_domain": candidate.source_domain,
    }


def _tool_rows(tool_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = tool_result.get("data") if isinstance(tool_result, Mapping) else None
    if isinstance(data, Mapping):
        raw_rows = data.get("items") or data.get("rows") or data.get("cars") or data.get("stores") or []
        if isinstance(raw_rows, list):
            return [dict(row) for row in raw_rows if isinstance(row, Mapping)]
        if raw_rows in (None, "", [], {}):
            return []
        return [dict(data)]
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, Mapping)]
    return []


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _registered_vehicle_anchor_matches(row: Mapping[str, Any], anchor: str) -> bool:
    normalized_anchor = _normalize_match_text(anchor)
    if not normalized_anchor:
        return False
    for key in (
        "car_mdl_nm",
        "car_model_nm",
        "model_nm",
        "modelName",
        "car_nm",
        "carName",
        "car_no",
        "carNo",
        "licensePlate",
    ):
        normalized_value = _normalize_match_text(row.get(key))
        if normalized_value and (normalized_anchor in normalized_value or normalized_value in normalized_anchor):
            return True
    return False


def _single_registered_vehicle_match(
    tool_result: Mapping[str, Any],
    *,
    anchor: str,
) -> dict[str, Any] | None:
    matches = _registered_vehicle_matches(tool_result, anchor=anchor)
    if len(matches) != 1:
        return None
    return matches[0]


def _registered_vehicle_matches(
    tool_result: Mapping[str, Any],
    *,
    anchor: str,
) -> list[dict[str, Any]]:
    return [row for row in _tool_rows(tool_result) if _registered_vehicle_anchor_matches(row, anchor)]


def _registered_vehicle_recommendation_input(
    *,
    turn_contract: TurnContract,
    vehicle_row: Mapping[str, Any],
) -> dict[str, Any]:
    tool_input = {
        str(key): value
        for key, value in dict(getattr(turn_contract, "tool_args_patch", {}) or {}).items()
        if value not in (None, "", [], {})
    }
    front_size = normalize_tire_size(str(vehicle_row.get("tire_size_fr") or vehicle_row.get("tireSizeFr") or ""))
    rear_size = normalize_tire_size(str(vehicle_row.get("tire_size_re") or vehicle_row.get("tireSizeRr") or ""))
    if front_size and (not rear_size or front_size == rear_size):
        tool_input["tire_size"] = front_size
    car_lnc_cd = str(vehicle_row.get("car_lnc_cd") or vehicle_row.get("carLncCd") or "").strip()
    if car_lnc_cd:
        tool_input["car_lnc_cd"] = car_lnc_cd
    vehicle_type = str(vehicle_row.get("vehicle_type") or vehicle_row.get("vehicleType") or "").strip()
    if vehicle_type:
        tool_input["vehicle_type"] = vehicle_type
    tool_input.setdefault("rcmd_type", "tstation")
    return {key: value for key, value in tool_input.items() if value not in (None, "", [], {})}


def _registered_vehicle_general_recommendation_input(*, turn_contract: TurnContract) -> dict[str, Any] | None:
    tool_input = {
        str(key): value
        for key, value in dict(getattr(turn_contract, "tool_args_patch", {}) or {}).items()
        if value not in (None, "", [], {})
    }
    for key in ("car_lnc_cd", "carLncCd", "vehicle_type", "vehicleType", "vehicle_query"):
        tool_input.pop(key, None)
    tool_input.setdefault("rcmd_type", "tstation")
    return {key: value for key, value in tool_input.items() if value not in (None, "", [], {})}


async def _maybe_run_registered_vehicle_recommendation(
    *,
    turn_contract: TurnContract,
    car_tool_result: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    known_slots = turn_contract.known_slots or {}
    anchor = str(known_slots.get("named_registered_vehicle_anchor") or "").strip()
    if not anchor:
        return None
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool)}
    forbidden_tools = {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool)}
    recommendation_tool = "get_products_recommendations_tool"
    if recommendation_tool not in allowed_tools or recommendation_tool in forbidden_tools:
        return None
    matches = _registered_vehicle_matches(car_tool_result, anchor=anchor)
    if len(matches) > 1:
        return None
    recovery_reason = "registered_vehicle_direct_recommendation"
    if len(matches) == 1:
        recommendation_input = _registered_vehicle_recommendation_input(
            turn_contract=turn_contract,
            vehicle_row=matches[0],
        )
        if not (recommendation_input.get("tire_size") or recommendation_input.get("car_lnc_cd")):
            return None
    else:
        recommendation_input = _registered_vehicle_general_recommendation_input(turn_contract=turn_contract)
        if not recommendation_input:
            return None
        recovery_reason = "registered_vehicle_no_match_general_recommendation"
    from services.tstation.agents.b_discovery_agent.tools import get_products_recommendations_tool

    raw_result = await asyncio.to_thread(get_products_recommendations_tool.invoke, recommendation_input)
    recommendation_result = raw_result if isinstance(raw_result, dict) else qc_verifier.parse_tool_output(raw_result)
    if not isinstance(recommendation_result, dict):
        recommendation_result = {
            "status": "error",
            "http_status": None,
            "message": "Invalid tool response",
            "data": {},
        }
    return recommendation_input, recommendation_result, recovery_reason


async def recover_blocked_fast_path_to_contract_tool(
    *,
    turn_contract: TurnContract | None,
    user_text: str,
    merged_slots: ConversationSlots | None,
    blocked_fast_path_source: str,
    member_no: str | None = None,
) -> dict[str, Any] | None:
    if turn_contract is None:
        return None
    if tuple(getattr(turn_contract, "blocking_required_slots", ()) or ()):
        return None
    context_state = str(getattr(turn_contract, "context_state", "") or "")
    current_turn_vehicle_recommendation = _is_vehicle_selection_recommendation_contract(turn_contract)
    current_turn_direct_path = str(blocked_fast_path_source or "").startswith("contract_direct_executor:")
    if context_state not in {"active", "resumed"} and not current_turn_vehicle_recommendation and not current_turn_direct_path:
        return None

    contract_intent = str(turn_contract.intent or "")
    domain = str(turn_contract.domain or "").strip().lower()
    candidate = _contract_required_tool_candidate(
        turn_contract=turn_contract,
        user_text=user_text,
        merged_slots=merged_slots,
        member_no=member_no,
    )
    if candidate is None:
        return None
    preferred_tool = candidate.tool_name
    tool_input = candidate.tool_input
    tool_input_source = candidate.tool_input_source
    display_name = candidate.display_name
    source_domain = candidate.source_domain
    execution_domain = source_domain if source_domain in {PolicyDomain.DISCOVERY.value, PolicyDomain.TRANSACTION.value} else domain
    chained_tool_name = ""
    chained_tool_input: dict[str, Any] = {}
    chained_tool_result: dict[str, Any] = {}
    chained_recovery_reason = ""

    if execution_domain in {PolicyDomain.DISCOVERY.value, PolicyDomain.TRANSACTION.value}:
        from services.tstation.template_mapper import try_build_template

        if execution_domain == PolicyDomain.DISCOVERY.value:
            from services.tstation.agents.b_discovery_agent import tools as discovery_tools

            tool = getattr(discovery_tools, preferred_tool, None)
        else:
            from services.tstation.agents.c_transaction_agent import tools as transaction_tools

            tool = getattr(transaction_tools, preferred_tool, None)
        if tool is None or not hasattr(tool, "invoke"):
            return None
        raw_result = await asyncio.to_thread(tool.invoke, tool_input)
        tool_result = raw_result if isinstance(raw_result, dict) else qc_verifier.parse_tool_output(raw_result)
        if not isinstance(tool_result, dict):
            tool_result = {"status": "error", "http_status": None, "message": "Invalid tool response", "data": {}}
        if preferred_tool == "get_best_selling_products_tool":
            tool_result = _enrich_best_selling_result_for_product_cards(tool_result)
            fallback_input = _best_selling_general_fallback_input(tool_input, tool_result)
            if fallback_input is not None:
                fallback_raw_result = await asyncio.to_thread(tool.invoke, fallback_input)
                fallback_tool_result = (
                    fallback_raw_result
                    if isinstance(fallback_raw_result, dict)
                    else qc_verifier.parse_tool_output(fallback_raw_result)
                )
                if not isinstance(fallback_tool_result, dict):
                    fallback_tool_result = {
                        "status": "error",
                        "http_status": None,
                        "message": "Invalid tool response",
                        "data": {},
                    }
                fallback_tool_result = _enrich_best_selling_result_for_product_cards(fallback_tool_result)
                fallback_data = fallback_tool_result.get("data") if isinstance(fallback_tool_result, Mapping) else None
                fallback_items = fallback_data.get("items") if isinstance(fallback_data, Mapping) else None
                if isinstance(fallback_items, list) and fallback_items:
                    tool_input = fallback_input
                    tool_result = fallback_tool_result
        if preferred_tool == "get_my_cars_tool":
            chained_recommendation = await _maybe_run_registered_vehicle_recommendation(
                turn_contract=turn_contract,
                car_tool_result=tool_result,
            )
            if chained_recommendation is not None:
                chained_tool_name = "get_products_recommendations_tool"
                chained_tool_input, chained_tool_result, chained_recovery_reason = chained_recommendation
        if preferred_tool == "search_product_tool":
            assistant_text = f"{str(tool_input.get('keyword') or '상품')} 상품을 확인했어요."
        elif preferred_tool == "get_product_description_tool":
            assistant_text = "상품 상세 정보를 확인했어요."
        elif preferred_tool == "get_products_recommendations_tool":
            assistant_text = "추천 상품을 확인했어요."
        elif preferred_tool == "get_my_cars_tool":
            assistant_text = "추천 상품을 확인했어요." if chained_tool_name else "등록된 차량을 확인했어요."
        elif preferred_tool == "get_store_schedule_tool":
            assistant_text = "예약 가능 일정을 확인했어요."
        elif preferred_tool == "get_store_inventory_tool":
            assistant_text = "매장 재고를 확인했어요."
        else:
            assistant_text = "요청하신 정보를 확인했어요."
        tool_data_list = [{"tool": preferred_tool, "args": tool_input, "data": tool_result}]
        if chained_tool_name:
            tool_data_list.append({
                "tool": chained_tool_name,
                "args": chained_tool_input,
                "data": chained_tool_result,
            })
        mapped_event = try_build_template(tool_data_list, assistant_text)
        from services.tstation.chat import (
            _build_reservation_status_lookup_event,
            _build_reservation_store_info_event,
            _reservation_store_not_found_event,
            _select_reservation_store_row,
        )

        if not isinstance(mapped_event, dict) and preferred_tool == "get_my_reservations_tool":
            if contract_intent == "reservation_store_info_lookup":
                reservation_row, match_reason = _select_reservation_store_row(user_text, tool_result)
                mapped_event = (
                    _build_reservation_store_info_event(reservation_row, match_reason=match_reason)
                    if reservation_row is not None
                    else _reservation_store_not_found_event(match_reason)
                )
            else:
                mapped_event = _build_reservation_status_lookup_event(tool_result)
        if not isinstance(mapped_event, dict):
            return None
        mapped_event["source_domain"] = source_domain
        if (
            preferred_tool in {"get_store_list_tool", "search_stores_tool"}
            and tool_input_source == "turn_contract_required_stock_inventory_store_lookup"
        ):
            _annotate_stock_inventory_store_lookup_event(
                mapped_event,
                turn_contract=turn_contract,
                tool_input=tool_input,
            )
    else:
        if preferred_tool == "search_faq_hybrid_tool":
            from services.tstation.agents.e_support_agent.tools import search_faq_hybrid_tool as _support_tool
        elif preferred_tool == "get_card_installments_tool":
            from services.tstation.agents.e_support_agent.tools import get_card_installments_tool as _support_tool
        else:
            return None

        raw_result = await asyncio.to_thread(_support_tool.invoke, tool_input)
        tool_result = raw_result if isinstance(raw_result, dict) else {"status": "success", "data": raw_result}
        from services.tstation.chat import (
            _build_general_cancel_fee_policy_event,
            _build_general_card_cancel_timing_policy_event,
            _build_support_faq_policy_event,
        )

        if contract_intent == "general_cancel_fee_policy":
            mapped_event = _build_general_cancel_fee_policy_event(user_text, tool_result=tool_result)
        elif contract_intent == "general_card_cancel_timing_policy":
            mapped_event = _build_general_card_cancel_timing_policy_event(user_text, tool_result=tool_result)
        else:
            mapped_event = _build_support_faq_policy_event(contract_intent, user_text, tool_result=tool_result)
        if not isinstance(mapped_event, dict):
            return None

    mapped_event = _annotate_contract_tool_recovery_event(
        mapped_event,
        turn_contract=turn_contract,
        blocked_fast_path_source=blocked_fast_path_source,
        recovered_tool=chained_tool_name or preferred_tool,
        recovery_reason=(
            chained_recovery_reason
            if chained_tool_name
            else "fast_path_blocked_but_contract_tool_executable"
        ),
        tool_input_source=(
            "router_evidence_registered_vehicle_anchor"
            if chained_tool_name
            else tool_input_source or "contract_tool_plan"
        ),
    )
    return {
        "tool_name": chained_tool_name or preferred_tool,
        "tool_input": chained_tool_input or tool_input,
        "tool_result": chained_tool_result or tool_result,
        "event": mapped_event,
        "events": [
            {
                "type": "status",
                "status": "tool_start",
                "tool": preferred_tool,
                "display_name": display_name,
                "source_domain": source_domain,
            },
            {
                "type": "agent_flow",
                "agent": "[CONTRACT RECOVERY AF]",
                "agent_class": "Contract Recovery",
                "status": tool_result.get("status", "success"),
                "source_domain": source_domain,
            },
            {
                "type": "tool",
                "input": tool_input,
                "output": json.dumps(tool_result, ensure_ascii=False),
                "node": "tools",
                "tool": preferred_tool,
                "source_domain": source_domain,
            },
            *(
                [
                    {
                        "type": "status",
                        "status": "tool_start",
                        "tool": chained_tool_name,
                        "display_name": "추천 상품 확인 중...",
                        "source_domain": source_domain,
                    },
                    {
                        "type": "agent_flow",
                        "agent": "[CONTRACT RECOVERY AF]",
                        "agent_class": "Contract Recovery",
                        "status": chained_tool_result.get("status", "success"),
                        "source_domain": source_domain,
                    },
                    {
                        "type": "tool",
                        "input": chained_tool_input,
                        "output": json.dumps(chained_tool_result, ensure_ascii=False),
                        "node": "tools",
                        "tool": chained_tool_name,
                        "source_domain": source_domain,
                    },
                ]
                if chained_tool_name
                else []
            ),
        ],
    }
