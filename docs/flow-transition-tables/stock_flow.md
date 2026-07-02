# Stock Flow State Transition Table

Purpose: define inventory and store-availability transitions separately from purchase. Stock checks may lead to
`datepick` only when the current turn asks for availability/schedule, not when it is pure inventory-only.

## Invariants

- Inventory-only answers must not create `preOrder`.
- `datepick` is allowed only when the contract is availability/schedule oriented and inventory or logistics data supports it.
- Product resolution can start in discovery, but stock flow owns the next transaction tool once `goods_no` is available.
- Store context from previous purchase/search is dormant unless the current turn references or selects it.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| stock | empty | inventory_availability/stock_store_search | none | product, size, quantity, store or location | `search_product_tool` when product text exists | `quick_order_tool`, `get_store_schedule_tool` until product/store are resolved | resolve product or ask missing product | `product` or `quickReply` |
| stock | product_keyword_only | inventory_availability | current product keyword | `goods_no`, size, quantity, store or location | `search_product_tool` | `quick_order_tool` | resolve product candidates | `product` |
| stock | product_selected | quantity_fill | product active | quantity, store or location | none | `quick_order_tool`, `get_store_schedule_tool` | commit quantity and ask/resolve store | `quickReply` |
| stock | product_quantity_set | store_or_region_fill | product and quantity active | store or location | `search_stores_tool`, `get_store_list_tool`, `transaction_store_preview_tool` | `quick_order_tool` | find candidate stores with stock | `location` |
| stock | store_resolved_inventory_only | pure_inventory_check | product, quantity, store active | none | `get_store_inventory_tool` | `get_store_schedule_tool`, `quick_order_tool`, `preOrder` template | check inventory only | `quickReply` or `location` |
| stock | store_resolved_today_install | today_install/availability_schedule | product, quantity, store active | schedule availability | `get_store_inventory_tool`, `get_store_schedule_tool` | `quick_order_tool` until schedule selected | check inventory then available schedule | `datepick` or `quickReply` |
| stock | region_candidates | store_selected/ui_action | selected store and stock context active | store inventory | `get_store_inventory_tool`, `get_store_schedule_tool` if schedule intent exists | `quick_order_tool` | verify selected store inventory | `datepick` or `quickReply` |
| stock | unavailable_inventory | any_stock_continuation | product/store active but unavailable | none | `get_store_list_tool`, `search_stores_tool` for other stores | `datepick` template, `preOrder` template, `quick_order_tool` | offer other-store search or safe fallback | `quickReply` or `location` |
| stock | datepick_shown | schedule_slot_fill | stock availability active | `requested_cal_day`, `rsv_hour` only if user switches to purchase/order | none or purchase transition tools | `quick_order_tool` unless purchase intent is explicit | either answer availability or transition to purchase | `quickReply` or `preOrder` |
| stock | any_active | support_faq/policy | stock context dormant | support topic | `search_faq_hybrid_tool` | stock/order tools | answer FAQ first | `quickReply` |

## Regression Test Reorganization

- Separate pure inventory tests from today-install/purchase-preview tests.
- Assert that unavailable inventory blocks `datepick` and `preOrder`.
- Add post-search tests where `search_product_tool` fills `goods_no`, then active stock flow continues to store/inventory
  lookup without ending as product description.
