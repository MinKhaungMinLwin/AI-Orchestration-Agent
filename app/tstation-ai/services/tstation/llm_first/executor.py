from __future__ import annotations

import asyncio
import logging
from typing import Any

from services.tstation.llm_first.models import AgentFlow, ConversationState, FactBundle, PlannerDecision, ToolCallRecord
from services.tstation.llm_first.state import apply_state_rules
from services.tstation.llm_first.templates import build_datepick_template, build_list_car_template, build_location_template, build_preorder_template, build_product_template, build_voucher_template
from services.tstation.llm_first.tools import invoke_tool

logger = logging.getLogger(__name__)


def _append_template(bundle: FactBundle, event: dict[str, Any] | None) -> None:
    if event is not None:
        bundle.templates.append(event)


def _success_payload(result: Any) -> Any:
    if isinstance(result, dict) and result.get("status") == "error":
        return None
    return result


def _first_item(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    for key in ("items", "products", "goods", "stores"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
    return data if isinstance(data, dict) else None


class AFExecutor:
    async def execute(self, *, user_text: str, state: ConversationState, planner: PlannerDecision) -> FactBundle:
        bundle = FactBundle(planner=planner, state=state)
        working_state = state
        for selected in planner.selected_afs:
            if selected.af == AgentFlow.PRODUCT_RECOMMENDATION:
                working_state = await self._recommend(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRODUCT_DESCRIPTION:
                working_state = await self._description(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRICE:
                if selected.known_inputs.get("account_lookup") == "coupons":
                    working_state = await self._coupons(user_text, working_state, selected.known_inputs, bundle)
                else:
                    working_state = await self._price(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.STORE:
                working_state = await self._store(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.INVENTORY:
                working_state = await self._inventory(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.QUICK_SHOPPING:
                working_state = await self._quick_shopping(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.FAQ:
                if selected.known_inputs.get("account_lookup") == "warranties":
                    working_state = await self._warranties(user_text, working_state, selected.known_inputs, bundle)
                else:
                    working_state = await self._faq(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.ORDER_DELIVERY:
                working_state = await self._account_order_delivery(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRODUCT_COMPATIBILITY:
                working_state = await self._compatibility(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.FALLBACK_ESCALATION:
                working_state = await self._fallback_escalation(user_text, working_state, selected.known_inputs, bundle)
        bundle.state = working_state
        bundle.facts["commerce_state"] = working_state.commerce_state.model_dump(exclude_none=True)
        return bundle

    async def _call(self, bundle: FactBundle, af: AgentFlow, tool_name: str, args: dict[str, Any]) -> Any:
        try:
            result = await asyncio.to_thread(invoke_tool, tool_name, args, af=af)
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            bundle.facts[tool_name] = result
            return result
        except PermissionError as exc:
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, blocked=True, reason=str(exc)))
            return None
        except Exception as exc:
            logger.warning("[LLM_FIRST_EXECUTOR] tool failed: %s", tool_name, exc_info=True)
            result = {"status": "error", "message": str(exc)}
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            return result

    async def _resolve_product(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> tuple[ConversationState, str | None]:
        goods_no = known.get("goods_no") or state.commerce_state.product.goods_no
        if goods_no:
            return state, str(goods_no)
        keyword = known.get("product_name")
        if not keyword and not known.get("tire_size"):
            bundle.missing_inputs.append("product")
            return state, None
        result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "search_product_tool", {
            "keyword": keyword,
            "size": known.get("tire_size"),
            "limit": 5,
        })
        item = _first_item(_success_payload(result))
        if not item:
            bundle.missing_inputs.append("product_selection")
            return state, None
        goods_no = item.get("goods_no") or item.get("goodsNo")
        product_name = item.get("goods_nm") or item.get("goodsNm") or item.get("title")
        next_state = apply_state_rules(
            state,
            product_patch={
                "goods_no": goods_no,
                "product_name": product_name,
                "tire_size": known.get("tire_size"),
            },
        )
        return next_state, str(goods_no) if goods_no else None

    async def _recommend(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        if known.get("recommendation_source") == "best_seller":
            args: dict[str, Any] = {"limit": int(known.get("limit") or 5)}
            if known.get("vehicle_query") or known.get("car_model"):
                args["vehicle_query"] = known.get("vehicle_query") or known.get("car_model")
            if known.get("months"):
                args["months"] = int(known["months"])
            if known.get("from_date") and known.get("to_date"):
                args["from_date"] = known["from_date"]
                args["to_date"] = known["to_date"]
            result = await self._call(bundle, AgentFlow.PRODUCT_RECOMMENDATION, "get_best_selling_products_tool", args)
            _append_template(bundle, build_product_template(result, "인기 상품을 확인해 주세요."))
            return state

        tire_size = known.get("tire_size") or state.commerce_state.product.tire_size
        recommendation_type = known.get("recommendation_type")
        if recommendation_type in (None, "", "none"):
            recommendation_type = "tstation"
        args = {
            "rcmd_type": recommendation_type,
            "limit": min(max(int(known.get("limit") or 3), 1), 10),
        }
        optional_keys = (
            "brand_cd",
            "car_lnc_cd",
            "vehicle_type",
            "season_nm",
            "sort_by",
            "min_price",
            "max_price",
        )
        if tire_size:
            args["tire_size"] = tire_size
        for key in optional_keys:
            value = known.get(key)
            if value not in (None, "", "none"):
                args[key] = value
        result = await self._call(bundle, AgentFlow.PRODUCT_RECOMMENDATION, "get_products_recommendations_tool", args)
        _append_template(bundle, build_product_template(result, "추천 상품을 확인해 주세요."))
        return apply_state_rules(state, product_patch={"tire_size": tire_size} if tire_size else None)

    async def _description(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        if not goods_no:
            return next_state
        await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "get_product_description_tool", {"goods_no": goods_no})
        return next_state

    async def _price(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        if not goods_no:
            return next_state
        result = await self._call(bundle, AgentFlow.PRICE, "get_final_price_tool", {"goods_no": goods_no})
        data = result.get("data", {}) if isinstance(result, dict) else {}
        final_price = data.get("cheapest_final_prc") or data.get("final_prc") or data.get("extra_fvr_sale_prc") or data.get("sale_prc")
        return apply_state_rules(next_state, price_patch={"final_price": final_price, "source": "get_final_price_tool"})

    async def _coupons(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        result = await self._call(bundle, AgentFlow.PRICE, "get_my_coupons_tool", {"lang_cd": "ko"})
        _append_template(bundle, build_voucher_template(result, "보유 쿠폰 목록을 확인해 주세요."))
        return state

    async def _account_order_delivery(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        lookup = known.get("account_lookup")
        if lookup == "orders":
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_orders_of_user_tool", {})
        elif lookup == "maintenance_history":
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_maintenance_history_tool", {"limit": 5})
        else:
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_my_reservations_tool", {"sct_cd": "all"})
        return state

    async def _store(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        query = known.get("region") or known.get("store_name") or state.commerce_state.store.region
        if not query:
            bundle.missing_inputs.append("region_or_store")
            return state
        result = await self._call(bundle, AgentFlow.STORE, "search_stores_tool", {"place_query": str(query), "limit": 10})
        store_attribute = str(known.get("store_attribute") or "").strip()
        assistant_response = "매장 후보를 확인해 주세요."
        if store_attribute:
            assistant_response = (
                f"조회된 매장 기본정보에는 {store_attribute} 여부가 포함되어 있지 않아요. "
                "아래 매장은 지역 기준 후보이며, 방문 전 매장에 직접 확인해 주세요."
            )
        is_booking_flow = bool(
            (known.get("goods_no") or state.commerce_state.product.goods_no)
            and (known.get("ord_qty") or state.commerce_state.quantity)
        )
        _append_template(bundle, build_location_template(
            result,
            assistant_response,
            is_booking_flow=is_booking_flow,
        ))
        return apply_state_rules(state, store_patch={"region": str(query)})

    async def _inventory(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        qty = known.get("ord_qty") or next_state.commerce_state.quantity
        region = known.get("region") or next_state.commerce_state.store.region
        shop_id = known.get("shop_id") or next_state.commerce_state.store.shop_id
        if not goods_no:
            bundle.missing_inputs.append("goods_no")
            return next_state
        if not qty:
            bundle.missing_inputs.append("ord_qty")
            return next_state
        if not (region or shop_id):
            bundle.missing_inputs.append("region_or_store")
            return apply_state_rules(next_state, quantity=int(qty))
        args = {"goods_no": goods_no, "ord_qty": int(qty), "region_code": region, "store_nm": known.get("store_name")}
        result = await self._call(bundle, AgentFlow.INVENTORY, "transaction_store_preview_tool", args)
        _append_template(bundle, build_location_template(result, "장착 가능한 후보 매장을 확인해 주세요.", is_booking_flow=True))
        return apply_state_rules(next_state, quantity=int(qty), store_patch={"region": region})

    async def _quick_shopping(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        qty = known.get("ord_qty") or next_state.commerce_state.quantity
        if not goods_no:
            bundle.missing_inputs.append("product")
            return next_state
        if not qty:
            bundle.missing_inputs.append("quantity")
            return next_state
        next_state = apply_state_rules(next_state, quantity=int(qty))
        if not (next_state.commerce_state.store.shop_id or next_state.commerce_state.store.region):
            bundle.missing_inputs.append("store_or_region")
            return next_state
        if next_state.commerce_state.store.shop_id and not (next_state.commerce_state.schedule.date and next_state.commerce_state.schedule.time):
            result = await self._call(bundle, AgentFlow.QUICK_SHOPPING, "get_store_schedule_tool", {
                "shop_id": next_state.commerce_state.store.shop_id,
                "mode": "INSTALL",
            })
            _append_template(bundle, build_datepick_template(result, "가능한 일정을 선택해 주세요."))
            bundle.missing_inputs.append("schedule")
            return next_state
        if not next_state.commerce_state.price.final_price:
            next_state = await self._price(user_text, next_state, {"goods_no": goods_no}, bundle)
        preorder = build_preorder_template(next_state, "주문 초안을 확인해 주세요. 실제 주문 실행은 아직 하지 않았습니다.")
        if preorder:
            bundle.templates.append(preorder)
        else:
            bundle.missing_inputs.append("preorder_required_inputs")
        return next_state

    async def _faq(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        await self._call(bundle, AgentFlow.FAQ, "search_faq_hybrid_tool", {"query": user_text, "top_k": 5})
        return state

    async def _warranties(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        await self._call(bundle, AgentFlow.FAQ, "get_my_warranties_tool", {})
        return state

    async def _compatibility(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        car_no = str(known.get("car_no") or "").strip()
        owner_nm = str(known.get("owner_nm") or "").strip()
        car_model = str(known.get("car_model") or known.get("product_name") or "").strip()
        mbr_no = str(known.get("mbr_no") or "").strip()
        if car_no and owner_nm:
            result = await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "get_user_vehicles_tool", {
                "car_no": car_no,
                "owner_nm": owner_nm,
            })
            _append_template(bundle, build_list_car_template(result, "차량 정보를 확인해 주세요."))
            return state
        if car_model:
            await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "search_car_model_groups_tool", {
                "keyword": car_model,
            })
            return state
        if mbr_no:
            result = await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "get_my_cars_tool", {"mbr_no": mbr_no})
            _append_template(bundle, build_list_car_template(result, "등록된 차량을 확인해 주세요."))
            return state
        bundle.missing_inputs.append("vehicle")
        return state

    async def _fallback_escalation(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        target = str(known.get("escalation_target") or "qna").strip()
        if target == "human":
            await self._call(bundle, AgentFlow.FALLBACK_ESCALATION, "escalate_tool", {
                "mbr_no": known.get("mbr_no"),
                "inq_type_cd": known.get("inq_type_cd"),
                "msg_count": known.get("msg_count") or 0,
                "summary": known.get("summary") or user_text,
            })
        else:
            await self._call(bundle, AgentFlow.FALLBACK_ESCALATION, "transfer_to_qna_tool", {
                "cnsl_clss_seq": known.get("cnsl_clss_seq") or "10019",
                "inq_tit_nm": known.get("inq_tit_nm") or user_text[:100],
                "ai_summary": known.get("ai_summary") or user_text[:400],
                "is_mobile": bool(known.get("is_mobile")),
            })
        bundle.missing_inputs.append("confirmation")
        return state
