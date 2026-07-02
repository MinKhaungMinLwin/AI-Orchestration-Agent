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

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| reservation_preorder | store_resolved | schedule_request | product, quantity, store active | schedule | `get_store_schedule_tool`, `get_multi_store_schedule_tool` | `quick_order_tool`, `transaction_store_preview_tool` | fetch schedule choices | `datepick` |
| reservation_preorder | datepick_shown | schedule_slot_fill | product, quantity, store active | `requested_cal_day`, `rsv_hour` | none or `get_store_schedule_tool` for revalidation | `search_product_tool`, `get_store_list_tool`, `quick_order_tool` | commit schedule and build preorder | `preOrder` |
| reservation_preorder | order_slots_complete | build_preorder | all order slots active | none | none | `search_product_tool`, `get_store_list_tool`, `get_store_schedule_tool` | build preorder event | `preOrder` |
| reservation_preorder | preorder_shown | quick_order_execute | preorder active | preorder payload | `quick_order_tool` | `search_product_tool`, `get_store_schedule_tool`, support FAQ tools | execute order | `orderComplete` |
| reservation_preorder | preorder_shown | schedule_change_before_order | preorder active but new schedule explicit | schedule | `get_store_schedule_tool` | `quick_order_tool` until schedule rebuilt | re-fetch/rebuild schedule | `datepick` or `preOrder` |
| reservation_preorder | preorder_shown | product_or_store_change | new product/store active | changed slot plus dependent slots | `search_product_tool` or `get_store_list_tool` | stale `quick_order_tool` | invalidate dependent preorder context | `product`, `location`, or `quickReply` |
| reservation_management | empty | reservation_status_lookup | owned record requested | reservation/order identity or member context | `get_my_reservations_tool`, `get_orders_of_user_tool`, `get_order_status_tool` | `get_store_schedule_tool`, `quick_order_tool`, `get_store_list_tool` | lookup existing reservation/order | `quickReply` |
| reservation_management | empty | reservation_change_request/order_cancel_request | owned record requested | order/reservation identity | `get_my_reservations_tool`, `get_orders_of_user_tool`, `get_order_status_tool` | new purchase tools, `get_store_schedule_tool` unless change flow explicitly supports it | lookup and guide allowed action | `quickReply` |
| reservation_management | empty | reservation_window_policy/general_cancel_fee_policy | policy question | policy topic | `search_faq_hybrid_tool` | `get_orders_of_user_tool`, `get_order_status_tool`, `quick_order_tool` | answer policy first | `quickReply` |
| reservation_preorder | any_active | support_faq/policy | preorder context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool` | answer support and preserve dormant preorder | `quickReply` |

## Regression Test Reorganization

- Keep new reservation/preorder tests separate from existing reservation management tests.
- Add tests for schedule slot-fill producing `preOrder` only when all required slots are active.
- Add negative tests where existing reservation lookup forbids stale store schedule/datepick actions.
