# Stock Flow State Transition Table

Purpose: define inventory and store-availability transitions separately from purchase. Stock checks may lead to
`datepick` only when the current turn asks for availability/schedule, not when it is pure inventory-only.

## Invariants

- Inventory-only answers must not create `preOrder`.
- `datepick` is allowed only when the contract is availability/schedule oriented and inventory or logistics data supports it.
- Product resolution can start in discovery, but stock flow owns the next transaction tool once `goods_no` is available.
- Store context from previous purchase/search is dormant unless the current turn references or selects it.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| stock | empty | inventory_availability/stock_store_search | none | product, size, quantity, store or location | `search_product_tool` when product text exists | `quick_order_tool`, `get_store_schedule_tool` until product/store are resolved | `product`, `quickReply` | `datepick`, `preOrder`, `orderComplete` | `search_product_tool` when product text exists | `product` or `quickReply` | persist only current-turn product/location hints |
| stock | product_keyword_only | inventory_availability | current product keyword | `goods_no`, size, quantity, store or location | `search_product_tool` | `quick_order_tool`, `get_store_schedule_tool` | `product`, `quickReply` | `location` unless store/location exists, `datepick`, `preOrder`, `orderComplete` | `search_product_tool` | `product` | persist product candidates/keyword in active stock flow |
| stock | product_selected | quantity_fill | product active | quantity, store or location | none | `quick_order_tool`, `get_store_schedule_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete` | none | `quickReply` | persist product and quantity; keep purchase context dormant |
| stock | product_quantity_set | store_or_region_fill | product and quantity active | store or location | `search_stores_tool`, `get_store_list_tool`, `transaction_store_preview_tool` | `quick_order_tool` | `location`, `quickReply` | `datepick` unless schedule intent exists, `preOrder`, `orderComplete` | `search_stores_tool`, `get_store_list_tool`, or `transaction_store_preview_tool` | `location` | persist product/quantity and candidate stores with stock context |
| stock | store_resolved_inventory_only | pure_inventory_check | product, quantity, store active | none | `get_store_inventory_tool` | `get_store_schedule_tool`, `quick_order_tool` | `quickReply`, `location` | `datepick`, `preOrder`, `orderComplete` | `get_store_inventory_tool` | `quickReply` or `location` | persist inventory result only; do not create purchase preorder context |
| stock | store_resolved_today_install | today_install/availability_schedule | product, quantity, store active | schedule availability | `get_store_inventory_tool`, `get_store_schedule_tool` | `quick_order_tool` until explicit purchase/order intent and schedule selected | `datepick`, `quickReply` | `preOrder`, `orderComplete` | `get_store_inventory_tool`, then `get_store_schedule_tool` if inventory permits | `datepick` or `quickReply` | persist availability schedule as stock context, not purchase execution context |
| stock | region_candidates | store_selected/ui_action | selected store and stock context active | store inventory | `get_store_inventory_tool`, `get_store_schedule_tool` if schedule intent exists | `quick_order_tool` | `quickReply`, `datepick` when schedule intent exists | `preOrder`, `orderComplete` | `get_store_inventory_tool`, optional `get_store_schedule_tool` | `datepick` or `quickReply` | persist selected store and inventory/schedule result under stock |
| stock | unavailable_inventory | any_stock_continuation | product/store active but unavailable | none | `get_store_list_tool`, `search_stores_tool` for other stores | `quick_order_tool` | `quickReply`, `location` | `datepick`, `preOrder`, `orderComplete` | `get_store_list_tool` or `search_stores_tool` only when user wants alternatives | `quickReply` or `location` | persist unavailable result; clear schedule/preorder candidates |
| stock | datepick_shown | schedule_slot_fill | stock availability active | `requested_cal_day`, `rsv_hour` only if user explicitly switches to purchase/order | none or purchase transition tools | `quick_order_tool` unless purchase intent is explicit | `quickReply`, `preOrder` only after explicit purchase transition | `orderComplete` | purchase flow next tool only when buy/reserve/install is explicit | `quickReply` or purchase `preOrder` | move to purchase only with current-turn buy/reserve/install anchor; otherwise keep stock context |
| stock | any_active | support_faq/policy | stock context dormant | support topic | `search_faq_hybrid_tool` | stock/order tools | `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | move stock to dormant; weak previous template metadata cannot resume it |

## Regression Test Reorganization

- Separate pure inventory tests from today-install/purchase-preview tests.
- Assert that unavailable inventory blocks `datepick` and `preOrder`.
- Add post-search tests where `search_product_tool` fills `goods_no`, then active stock flow continues to store/inventory
  lookup without ending as product description.
