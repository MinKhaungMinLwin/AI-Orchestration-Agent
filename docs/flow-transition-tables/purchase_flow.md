# Purchase Flow State Transition Table

Purpose: define the expected state transitions for purchase/order continuation before adding more case patches.
This table follows the current TurnContract direction: current-turn intent decides whether stored purchase context is
active, dormant, or invalidated.

## Invariants

- `preOrder` is a template/action, not a tool.
- Stored product/store/schedule context can execute only when the current turn resumes or continues purchase intent.
- New product, size, quantity, store, or schedule input invalidates dependent stale slots before the next action is chosen.
- Product and store card selections should be handled as UI actions or slot fills, not as plain text labels in `chat.py`.
- FAQ/support intents during purchase make the purchase flow dormant unless the current turn explicitly resumes purchase.

## Required Slot Groups

| Slot Group | Fields |
|---|---|
| product | `goods_no`, `product_name` or `tire_model`, `tire_size` |
| quantity | `ord_qty` |
| store | `shop_id` or resolvable `shop_name`/`store_name`/`region`/`place_query` |
| schedule | `requested_cal_day`, `rsv_hour` |
| price | `payment_amount` or recoverable price basis fields |

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| purchase | empty | purchase_confirm/order | none | product, size, quantity, store, schedule | none or `search_product_tool` when product keyword exists | `quick_order_tool`, `get_final_price_tool`, `get_store_schedule_tool` | ask for missing product or resolve product | `quickReply` or `product` |
| purchase | product_keyword_only | purchase_confirm/order | current product keyword | `goods_no`, size, quantity, store, schedule | `search_product_tool` | `quick_order_tool`, `get_final_price_tool`, `get_store_schedule_tool` | resolve product candidate | `product` or `quickReply` |
| purchase | product_candidates | product_selected/ui_action | selected product candidate | size, quantity, store, schedule | none or `get_store_list_tool` if store text exists | `quick_order_tool` | commit product slot and ask next missing slot | `quickReply` or `location` |
| purchase | product_selected | quantity_fill | selected product active | quantity, store, schedule | none | `search_product_tool` unless new product is explicit | commit quantity and ask/resolve store | `quickReply` or `location` |
| purchase | product_selected_quantity_set | store_fill/store_search | product and quantity active | store, schedule | `search_stores_tool`, `get_store_list_tool` | `quick_order_tool`, `get_store_schedule_tool` until store is resolved | resolve store candidates | `location` |
| purchase | store_candidates | store_selected/ui_action | selected product, quantity, selected store | schedule | `get_store_schedule_tool` | `transaction_store_preview_tool`, `quick_order_tool` | fetch schedule slots | `datepick` |
| purchase | store_resolved | schedule_request | product, quantity, store active | schedule | `get_store_schedule_tool` | `quick_order_tool` until schedule is selected | fetch schedule slots | `datepick` |
| purchase | datepick_shown | schedule_slot_fill | product, quantity, store active | `requested_cal_day`, `rsv_hour` | none or `get_store_schedule_tool` only if schedule needs revalidation | `search_product_tool`, `transaction_store_preview_tool`, `quick_order_tool` | commit selected schedule | `preOrder` |
| purchase | order_slots_complete | purchase_confirm/build_preorder | product, quantity, store, schedule, price active | none | none | `search_product_tool`, `search_faq_hybrid_tool` unless current turn is support | build preorder event | `preOrder` |
| purchase | preorder_ready | quick_order_execute/confirm | preorder active | preorder payload fields | `quick_order_tool` | `search_product_tool`, `get_store_list_tool`, `get_store_schedule_tool` | execute order | `orderComplete` |
| purchase | any_active | new_product_intent | new product text active; old product dormant/invalidated | product, size, quantity, store, schedule | `search_product_tool` | stale `quick_order_tool` | clear dependent product/store/schedule/payment slots and resolve product | `product` or `quickReply` |
| purchase | any_active | support_faq/policy | purchase context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool`, `get_final_price_tool` | answer FAQ first | `quickReply` |

## Regression Test Reorganization

- One test per row should assert `TurnContract.allowed_tools`, `forbidden_tools`, `response_shape_key`, and expected template.
- Add paired negative tests for stale context: a new product or support intent must not reuse previous purchase slots.
- E2E tests should include post-tool continuation: `search_product_tool` can make `get_store_list_tool` executable in the
  same turn when the active purchase flow has enough slots.
