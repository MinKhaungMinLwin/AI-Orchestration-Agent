# Store Flow State Transition Table

Purpose: separate store search, store detail, store service verification, and store schedule flows. Store questions
should not automatically become purchase or reservation actions.

## Invariants

- Store information/search can show `location`, but `location.isBookingFlow=true` is an action and requires booking intent.
- Store service/attribute claims must be verified by store data when available, or answered with an explicit limitation.
- Store search context must not initiate `datepick`, `preOrder`, or `quick_order_tool` without current-turn booking/order intent.
- A selected store can resume purchase/stock only when the current turn or active parent flow explicitly connects it.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| store_search | empty | store_search/open_store_search | current location text | region/place/store condition | `search_stores_tool`, `search_stores_complex_tool`, `get_store_list_tool`, `get_nearby_stores_tool` | `quick_order_tool`, `get_store_schedule_tool`, `transaction_store_preview_tool` | `location` with `isBookingFlow=false`, `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | store search tool matching evidence | `location` | persist store candidates as store_search context only |
| store_search | candidate_list | store_selected/ui_action | selected store active | none | `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool` unless booking intent | `location` with `isBookingFlow=false`, `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` unless booking/order context exists | `get_store_detail_tool` | `location` or `quickReply` | persist selected store; keep purchase/stock parent dormant unless compatible |
| store_search | store_selected | store_detail_inquiry | selected store active | none | `get_store_detail_tool`, `get_store_list_tool` | `quick_order_tool` | `quickReply`, `location` with `isBookingFlow=false` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | `get_store_detail_tool` | `quickReply` or `location` | persist store detail facts; do not create booking context |
| store_schedule | store_resolved | store_schedule_request | selected store active | date intent if present | `get_store_schedule_tool` | `quick_order_tool` | `datepick`, `quickReply` | `preOrder`, `orderComplete`, `location.isBookingFlow=true` unless booking/order context exists | `get_store_schedule_tool` | `datepick` | persist schedule candidates as store schedule context, not order context |
| store_schedule | no_store | store_schedule_request | current store text active if present | store | `get_store_list_tool`, `search_stores_tool` | `quick_order_tool`, `get_store_schedule_tool` until store is resolved | `location`, `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | `get_store_list_tool` or `search_stores_tool` | `location` | persist resolved store candidates only |
| store_service_search | empty | store_service_search | requested service/location active | service condition, location | `search_stores_complex_tool`, `get_store_list_tool`, `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool`, `transaction_store_preview_tool` | `location` with `isBookingFlow=false`, `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | service-capable store search/detail tool | `location` or `quickReply` | persist service/location filters and candidate stores |
| store_service_search | store_resolved | store_attribute_inquiry/store_service_availability | selected store active | service/attribute | `get_store_list_tool`, `get_store_detail_tool` | `quick_order_tool`, `get_store_schedule_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | `get_store_detail_tool` or `get_store_list_tool` | `quickReply` | persist verified attribute result with explicit grounding limits |
| favorite_store | empty | favorite_store_lookup | member context | member identity | favorite-store/member store tool when available | `quick_order_tool`, `get_store_schedule_tool` | `location` with `isBookingFlow=false`, `quickReply` | `datepick`, `preOrder`, `orderComplete`, `location.isBookingFlow=true` | favorite-store/member store tool when available | `location` | persist favorite stores as store context only |
| store_search | any_active | purchase_confirm/order | selected store can be active only if product/quantity parent flow exists | product, quantity, schedule | purchase tools via parent flow | support/store-only tools that conflict with purchase | purchase templates/actions allowed by parent contract | store-only `location.isBookingFlow=false` when parent purchase continues | parent purchase next tool | parent purchase next template/action | resume parent purchase only with compatible current-turn purchase anchor |
| store_search | any_active | support_faq/policy | store context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool` | `quickReply` | `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | move store context dormant; do not revive via prior location template |

## Regression Test Reorganization

- For every store row, assert whether booking action is allowed or forbidden.
- Add negative tests where store attribute questions containing purchase-like words do not become purchase/order.
- Add parent-flow tests where store selection correctly resumes purchase or stock only when the parent active flow exists.
