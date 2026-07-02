# Store Flow State Transition Table

Purpose: separate store search, store detail, store service verification, and store schedule flows. Store questions
should not automatically become purchase or reservation actions.

## Invariants

- Store information/search can show `location`, but `location.isBookingFlow=true` is an action and requires booking intent.
- Store service/attribute claims must be verified by store data when available, or answered with an explicit limitation.
- Store search context must not initiate `datepick`, `preOrder`, or `quick_order_tool` without current-turn booking/order intent.
- A selected store can resume purchase/stock only when the current turn or active parent flow explicitly connects it.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| store_search | empty | store_search/open_store_search | current location text | region/place/store condition | `search_stores_tool`, `search_stores_complex_tool`, `get_store_list_tool`, `get_nearby_stores_tool` | `quick_order_tool`, `get_store_schedule_tool`, `transaction_store_preview_tool` | search stores | `location` |
| store_search | candidate_list | store_selected/ui_action | selected store active | none | `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool` unless booking intent | show store detail | `location` or `quickReply` |
| store_search | store_selected | store_detail_inquiry | selected store active | none | `get_store_detail_tool`, `get_store_list_tool` | `quick_order_tool`, `preOrder` template | answer detail from store data | `quickReply` or `location` |
| store_schedule | store_resolved | store_schedule_request | selected store active | date intent if present | `get_store_schedule_tool` | `quick_order_tool`, `preOrder` template | fetch available schedule | `datepick` |
| store_schedule | no_store | store_schedule_request | current store text active if present | store | `get_store_list_tool`, `search_stores_tool` | `quick_order_tool` | resolve store first | `location` |
| store_service_search | empty | store_service_search | requested service/location active | service condition, location | `search_stores_complex_tool`, `get_store_list_tool`, `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool`, `transaction_store_preview_tool` | search/verify service-capable stores | `location` or `quickReply` |
| store_service_search | store_resolved | store_attribute_inquiry/store_service_availability | selected store active | service/attribute | `get_store_list_tool`, `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool`, `preOrder` template | verify attribute or disclose unverifiable condition | `quickReply` |
| favorite_store | empty | favorite_store_lookup | member context | member identity | favorite-store/member store tool when available | `quick_order_tool`, `get_store_schedule_tool` | list favorite stores | `location` |
| store_search | any_active | purchase_confirm/order | selected store can be active only if product/quantity parent flow exists | product, quantity, schedule | purchase tools via parent flow | support/store-only tools that conflict with purchase | transition to purchase flow | purchase expected template |
| store_search | any_active | support_faq/policy | store context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool` | answer policy | `quickReply` |

## Regression Test Reorganization

- For every store row, assert whether booking action is allowed or forbidden.
- Add negative tests where store attribute questions containing purchase-like words do not become purchase/order.
- Add parent-flow tests where store selection correctly resumes purchase or stock only when the parent active flow exists.
