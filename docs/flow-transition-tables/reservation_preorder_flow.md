# Reservation And PreOrder Flow State Transition Table

Purpose: define the boundary between schedule selection, preorder creation, and existing reservation management. These
are related but must not share stale store/schedule/order context without current-turn intent.

## Invariants

- `datepick`, `preOrder`, and `orderComplete` are templates/actions and must be contract-gated.
- Existing reservation management is not the same as new purchase reservation.
- Schedule slot-fill after `datepick` should build `preOrder` only when product, quantity, store, schedule, and price are
  active and compatible.
- Reservation policy questions use support FAQ first; they must not lookup owned reservations unless the current turn asks
  for a personal reservation/order.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| reservation_preorder | store_resolved | schedule_request | product, quantity, store active | schedule | `get_store_schedule_tool`, `get_multi_store_schedule_tool` | `quick_order_tool`, `transaction_store_preview_tool` | `datepick`, `quickReply` | `preOrder`, `orderComplete` | `get_store_schedule_tool` or `get_multi_store_schedule_tool` | `datepick` | persist schedule candidates with compatible product/store context |
| reservation_preorder | datepick_shown | schedule_slot_fill | product, quantity, store active | `requested_cal_day`, `rsv_hour`, price basis | none or `get_store_schedule_tool` for revalidation | `search_product_tool`, `get_store_list_tool`, `quick_order_tool` | `preOrder`, `quickReply` | `orderComplete` | `get_store_schedule_tool` only for revalidation | `preOrder` only after compatible schedule and price basis exist | persist selected schedule and preorder payload; do not execute order |
| reservation_preorder | order_slots_complete | build_preorder | all order slots and price active | none | none | `search_product_tool`, `get_store_list_tool`, `get_store_schedule_tool`, `quick_order_tool` until user confirms execution | `preOrder` | `datepick`, `orderComplete` | none | `preOrder` | persist preorder payload as active pending confirmation |
| reservation_preorder | preorder_shown | quick_order_execute | preorder active | preorder payload | `quick_order_tool` | `search_product_tool`, `get_store_schedule_tool`, support FAQ tools | `orderComplete`, `quickReply` | `product`, `location`, `datepick`, `preOrder` after successful order | `quick_order_tool` | `orderComplete` only after successful tool result | persist completed order result and close preorder flow |
| reservation_preorder | preorder_shown | schedule_change_before_order | preorder active but new schedule explicit | schedule, price basis if changed | `get_store_schedule_tool` | `quick_order_tool` until schedule rebuilt | `datepick`, `preOrder` after rebuild | `orderComplete` | `get_store_schedule_tool` | `datepick` or rebuilt `preOrder` | invalidate old schedule/preorder price fields before rebuilding |
| reservation_preorder | preorder_shown | product_or_store_change | new product/store active | changed slot plus dependent slots | `search_product_tool` or `get_store_list_tool` | stale `quick_order_tool`, stale `get_store_schedule_tool` until store/product resolved | `product`, `location`, `quickReply` | `datepick` from stale store, `preOrder`, `orderComplete` | `search_product_tool` or `get_store_list_tool` | `product`, `location`, or `quickReply` | invalidate dependent preorder, schedule, and price slots |
| reservation_management | empty | reservation_status_lookup | owned record requested | reservation/order identity or member context | `get_my_reservations_tool`, `get_orders_of_user_tool`, `get_order_status_tool` | `get_store_schedule_tool`, `quick_order_tool`, `get_store_list_tool` | `quickReply` | `location`, `datepick`, `preOrder`, `orderComplete` | owned reservation/order lookup tool | `quickReply` | persist owned reservation/order result under management flow |
| reservation_management | empty | reservation_change_request/order_cancel_request | owned record requested | order/reservation identity | `get_my_reservations_tool`, `get_orders_of_user_tool`, `get_order_status_tool` | new purchase tools, `get_store_schedule_tool` unless change flow explicitly supports it, `quick_order_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete` | owned reservation/order lookup tool | `quickReply` | persist management lookup; do not create new preorder context |
| reservation_management | empty | reservation_window_policy/general_cancel_fee_policy | policy question | policy topic | `search_faq_hybrid_tool` | `get_orders_of_user_tool`, `get_order_status_tool`, `quick_order_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | persist policy topic only; no owned lookup unless current turn asks |
| reservation_preorder | any_active | support_faq/policy | preorder context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | move preorder to dormant; do not resume via previous template data |

## Regression Test Reorganization

- Keep new reservation/preorder tests separate from existing reservation management tests.
- Add tests for schedule slot-fill producing `preOrder` only when all required slots and price basis are active.
- Add negative tests where existing reservation lookup forbids stale store schedule/datepick actions.
