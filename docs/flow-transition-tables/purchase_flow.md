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

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| purchase | empty | purchase_confirm/order | none | product, size, quantity, store, schedule | none or `search_product_tool` when product keyword exists | `quick_order_tool`, `get_final_price_tool`, `get_store_schedule_tool` | `quickReply`, `product` | `location`, `datepick`, `preOrder`, `orderComplete` | `search_product_tool` when product keyword exists | `product` or `quickReply` | persist only current-turn product keyword; do not revive old purchase slots |
| purchase | product_keyword_only | purchase_confirm/order | current product keyword | `goods_no`, size, quantity, store, schedule | `search_product_tool` | `quick_order_tool`, `get_final_price_tool`, `get_store_schedule_tool` | `product`, `quickReply` | `location`, `datepick`, `preOrder`, `orderComplete` | `search_product_tool` | `product` or `quickReply` | persist product candidates/keyword in active purchase flow |
| purchase | product_candidates | product_selected/ui_action | selected product candidate | size, quantity, store, schedule | none or `get_store_list_tool` if store text exists | `quick_order_tool` | `quickReply`, `location` | `datepick`, `preOrder`, `orderComplete` | `get_store_list_tool` only when store text exists | `quickReply` or `location` | persist selected product; clear stale store, schedule, and price slots |
| purchase | product_selected | quantity_fill | selected product active | quantity, store, schedule | none | `search_product_tool` unless new product is explicit, `quick_order_tool` | `quickReply`, `location` | `datepick`, `preOrder`, `orderComplete` | none | `quickReply` or `location` | persist product and quantity; stale schedule/price remain cleared |
| purchase | product_selected_quantity_set | store_fill/store_search | product and quantity active | store, schedule | `search_stores_tool`, `get_store_list_tool` | `quick_order_tool`, `get_store_schedule_tool` until store is resolved | `location`, `quickReply` | `datepick`, `preOrder`, `orderComplete` | `search_stores_tool` or `get_store_list_tool` | `location` | persist product/quantity and store candidates |
| purchase | store_candidates | store_selected/ui_action | selected product, quantity, selected store | schedule | `get_store_schedule_tool` | `transaction_store_preview_tool`, `quick_order_tool` | `datepick`, `quickReply` | `preOrder`, `orderComplete` | `get_store_schedule_tool` | `datepick` | persist selected store and schedule candidates; clear stale schedule selection/price |
| purchase | store_resolved | schedule_request | product, quantity, store active | schedule | `get_store_schedule_tool` | `quick_order_tool` until schedule is selected | `datepick`, `quickReply` | `preOrder`, `orderComplete` | `get_store_schedule_tool` | `datepick` | persist store and schedule candidates in active purchase flow |
| purchase | datepick_shown | schedule_slot_fill | product, quantity, store active | `requested_cal_day`, `rsv_hour`, price basis | none or `get_store_schedule_tool` only if schedule needs revalidation | `search_product_tool`, `transaction_store_preview_tool`, `quick_order_tool` | `preOrder`, `quickReply` | `orderComplete` | `get_store_schedule_tool` only for revalidation | `preOrder` only after compatible schedule and price basis exist | persist selected schedule and price basis; keep preorder unexecuted |
| purchase | order_slots_complete | purchase_confirm/build_preorder | product, quantity, store, schedule, price active | none | none | `search_product_tool`, `search_faq_hybrid_tool` unless current turn is support, `quick_order_tool` until user confirms execution | `preOrder` | `datepick`, `orderComplete` | none | `preOrder` | persist preorder payload as active, not executed |
| purchase | preorder_ready | quick_order_execute/confirm | preorder active | preorder payload fields | `quick_order_tool` | `search_product_tool`, `get_store_list_tool`, `get_store_schedule_tool` | `orderComplete`, `quickReply` | `product`, `location`, `datepick`, `preOrder` after successful order | `quick_order_tool` | `orderComplete` only after successful tool result | persist order result; close active purchase flow or move it to completed history |
| purchase | any_active | new_product_intent | new product text active; old product dormant/invalidated | product, size, quantity, store, schedule | `search_product_tool` | stale `quick_order_tool`, stale `get_store_schedule_tool` | `product`, `quickReply` | `location` from stale store, `datepick`, `preOrder`, `orderComplete` | `search_product_tool` | `product` or `quickReply` | invalidate old product-dependent store/schedule/payment slots before next action |
| purchase | any_active | support_faq/policy | purchase context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool`, `get_final_price_tool` | `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | move purchase to dormant; do not let `template_data`, `pending_intent`, or `goal_type` resume it |

## Regression Test Reorganization

- One test per row should assert `TurnContract.allowed_tools`, `forbidden_tools`, allowed/forbidden templates/actions, and expected persistence.
- Add paired negative tests for stale context: a new product or support intent must not reuse previous purchase slots.
- E2E tests should include post-tool continuation: `search_product_tool` can make `get_store_list_tool` executable in the
  same turn when the active purchase flow has enough slots.
