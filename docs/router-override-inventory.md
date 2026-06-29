# Router Override Inventory

This inventory records deterministic routing changes around the LLM router contract.
Classification:

- Hard safety: must override/block even when router confidence is high.
- Slot/tool contract: may patch required slots, stale slots, allowed tools, forbidden tools, or tool args without changing router intent unless safety requires it.
- Heuristic routing override: semantic rerouting based on regex or deterministic policy; these should be limited to low-confidence, ambiguous, or unsafe router results.

## chat.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| `_force_keyword_routing()` pre-router gates | Bypasses LLM router for pickup, order history/reorder, hard regex routing, and some deterministic keyword flows. | Mixed: hard safety for order/pickup guards, heuristic routing override for broad keyword reroutes. | Keep hard guards. Inventory each keyword reroute before adding new ones; require explicit support/policy/order safety reason. |
| P0/P0b/P0c Discovery/Transaction chaining | Rewrites single-domain routes to `DISCOVERY -> TRANSACTION` when a transactional turn lacks `goods_no` and needs product resolution. | Slot/tool contract with hard safety guard. | Keep only for missing product identity or explicit current-turn transaction action. Do not override protected high-confidence router contracts. |
| Coupon policy redirects (`P0e`, `P0f`, specific coupon usage) | Rewrites transaction/support/coupon routes to force canonical coupon policy or transaction coupon flow. | Hard safety for coupon issuance and policy text; heuristic for specific coupon usage prioritization. | Keep coupon issuance and hard policy guards. Require override metadata when changing domains. |
| Cross-domain normalization (`plan_cross_domain_turn`) | Computes deterministic multi-domain plan and may replace router domains/execution plan. | Mixed: slot/tool contract for product-first resolution, heuristic routing override for broad domain changes, hard safety for support/policy guards. | Skip heuristic plan for high-confidence router contracts, including transaction store/order/stock. Allow when router is low confidence, needs clarification, or hard guard applies. |
| Turn contract fallback/guard events | Replaces unsafe output when required slots or response policy would be violated. | Hard safety / slot-tool contract. | Keep. Turn contract is the final safety verifier, not primary semantic router. |

## cross_domain_policy.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Product resolution first | Routes product-name price/stock/order turns to Discovery before Transaction. | Slot/tool contract. | Keep when `goods_no` is missing or stale. Do not override high-confidence non-product transaction store/order routes. |
| Coupon / warranty / support policy detection | Routes policy-like coupon/support questions away from transaction tools. | Hard safety. | Keep. |
| Maintenance addon / reservation-store lookup | Creates transaction subtasks from structured current text and slots. | Slot/tool contract. | Keep when explicit and slot-compatible. |
| Generic domain replacement | Replaces router domains when deterministic plan differs. | Heuristic routing override. | Require low confidence, clarification, required-slot conflict, or safety reason. |

## transaction_intent_policy.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Intent frame construction | Assigns final transaction intent from regexes and slots. | Mixed; many branches are heuristic routing overrides. | Treat regexes as candidates and slot extractors. Preserve high-confidence router store/order/stock unless required-slot or tool safety says otherwise. |
| Required slot and stale slot handling | Computes missing slots and clears stale product/store context for plain store search. | Slot/tool contract. | Keep and expand where stale slots can leak into new store/search flows. |
| Allowed/forbidden tool plan | Maps intents to allowed tools, preferred tool, forbidden tools, and args patch. | Slot/tool contract / hard safety. | Keep. Tool safety should block unsafe tool calls even when router is high confidence. |
| `store_visit_advisory` regex | Previously classified regional Sunday/holiday open-store searches as advisory and forbade schedule tools. | Heuristic routing override. | Split regional open-store filters into `open_store_search`; keep specific-store timing/lunch/congestion advisory. |

## discovery_intent_policy.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Product/search/recommendation intent frame | Determines discovery sub-intents and recommendation context. | Slot/tool contract plus heuristic routing within Discovery. | Keep within Discovery. Do not use it to override high-confidence transaction/support router contracts except product-first missing identity guard. |
| Guardrails such as occupation-neutral and mileage bias | Blocks unsafe or biased recommendation behavior. | Hard safety. | Keep. |
| Tool plan and response policy | Restricts search/recommendation/event tools and templates. | Slot/tool contract. | Keep. |

## price_response_policy.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Coupon issuance and stacking policy | Forbids `issue_coupon_tool`, requires coupon condition checks. | Hard safety. | Keep. |
| Product price/coupon tool selection | Allows price/coupon tools only when product or coupon context supports it. | Slot/tool contract. | Keep. |

## transaction_response_policy.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Response shape for stock/order/schedule | Chooses `location`, `datepick`, `quickReply`, or order templates based on intent and slots. | Slot/tool contract. | Keep as presentation safety. |
| `store_visit_advisory` response | Forbids datepick and schedule-tool expansion for congestion/lunch/walk-in advice. | Hard safety for advisory semantics. | Keep only for specific-store advisory, not regional open-store filters. |
| `open_store_search` response | Location response for regional day/holiday open-store filtering. | Slot/tool contract. | Keep; requires filtered store tool results or no-open-store quickReply fallback. |

## turn_contract.py

| Area | Current behavior | Classification | Safety-only direction |
| --- | --- | --- | --- |
| Required slot guard | Blocks templates/tools when required slots are missing. | Hard safety. | Keep. |
| Allowed/forbidden tool validation | Flags forbidden or unexpected tools. | Hard safety / slot-tool contract. | Keep. |
| Planner/code drift tracking | Records drift between router and deterministic frame. | Observability. | Keep and prefer router contract unless safety guard applies. |
| Intent corrections for hard policies | Forces maintenance history access, event content, quick order execute with ready slots, etc. | Hard safety / slot-tool contract. | Keep only where explicitly safety-bound. |

## Current Preservation Rule

High-confidence router contracts are preserved when:

- `planner_confidence >= 0.8`
- `needs_clarification == false`
- router chose a protected support policy, discovery comparison, discovery event/recommendation, protected action, or transaction store/order/stock flow

Allowed deterministic overrides despite high confidence:

- explicit current-turn product/price/stock/order action requiring product resolution first
- hard safety guards such as coupon issuance, null order fields, required-slot violations, support/legal/policy guards

