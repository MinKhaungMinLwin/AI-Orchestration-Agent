# Context Stabilization Execution Plan

This document is the master execution plan for stabilizing the T-Station AI conversation flows. It is meant for future Codex/AI agents and developers who need to continue the work without re-discovering the same context from Slack, hand-off notes, and scattered code paths.

## Executive Summary

The current architecture is about 80 percent implemented. The key pieces already exist:

- `TurnContract`
- `flow_state`
- `flow_controller`
- `ui_action_policy`
- `contract_required_tool_candidate`
- `contract_required_tool_executor`
- deterministic `template_mapper`

The remaining problem is not one isolated bug. It is execution-boundary instability between:

```text
current-turn intent -> active/dormant flow state -> tool execution -> template/action rendering
```

Recurring symptoms:

- selected product/store/quantity/schedule context is forgotten or reused incorrectly
- purchase, stock, store, and support flows drift into the wrong domain
- after a tool fills a missing slot, the same turn often stops instead of continuing to the next required tool
- stale slots, `pending_intent`, `goal_type`, or previous `template_data` can override current user intent
- `location`, `datepick`, `preOrder`, `orderComplete`, and product templates can conflict with the active contract
- patch-level regex/guard fixes in `chat.py` have accumulated and can regress nearby valid flows

The solution is not to remember more context. The solution is to promote only context related to the current-turn intent into active flow state, keep unrelated context dormant, and let the centralized contract/flow layers decide the next valid action.

## Non-Negotiable Principles

1. Current-turn intent wins over stale context.
2. Active context must be explicit; unrelated previous context must stay dormant.
3. Each decision must have one owning layer.
4. `chat.py` should orchestrate only. Do not add new phrase-specific branches there unless every other owner layer is demonstrably wrong for the case.
5. `preOrder`, `datepick`, `location`, and `orderComplete` are templates/actions, not tools.
6. `TurnContract.allowed_tools` and `TurnContract.forbidden_tools` must be treated as execution boundaries.
7. Fix by transition-table row and regression test, not by single symptom.
8. Tool execution and template/action rendering must be validated separately.
9. A tool output can update slots, but the next action must be chosen only after rebuilding flow state and the turn contract.
10. Previous `template_data`, `pending_intent`, and `goal_type` are weak context sources. They must never outrank current-turn UI action, user text, router evidence, or a compatible active flow.

## Context Source Priority

When multiple sources disagree, use this priority order:

```text
current UI action / chip payload
-> current user text and router evidence
-> current-turn extracted slots
-> compatible active_flow_context
-> explicitly resumed dormant flow context
-> previous tool data needed for factual grounding
-> previous template_data
-> previous pending_intent / goal_type
```

Rules:

1. A lower-priority source may fill missing details only when it is compatible with the current `TurnContract`.
2. A dormant flow may become active only through an explicit resume anchor or a compatible UI action.
3. Previous template metadata may explain a UI selection, but it must not create or override the current domain, intent, allowed tools, or expected template/action.
4. `pending_intent` and `goal_type` are hints for continuity, not authorization to execute tools or render risky templates.
5. Any source-priority override must be visible in trace metadata.

## Required Reading Before Any Patch

Read these files first:

```text
hand-off.md
docs/turn-contract-policy-current-work.md
docs/router-override-inventory.md
docs/flow-transition-tables/purchase_flow.md
docs/flow-transition-tables/stock_flow.md
docs/flow-transition-tables/store_flow.md
docs/flow-transition-tables/support_flow.md
docs/flow-transition-tables/reservation_preorder_flow.md
app/tstation-ai/services/tstation/chat.py
app/tstation-ai/services/tstation/policies/turn_contract.py
app/tstation-ai/services/tstation/policies/flow_state.py
app/tstation-ai/services/tstation/policies/flow_controller.py
app/tstation-ai/services/tstation/policies/ui_action_policy.py
app/tstation-ai/services/tstation/policies/contract_required_tool_candidate.py
app/tstation-ai/services/tstation/executors/contract_required_tool_executor.py
app/tstation-ai/services/tstation/policies/transaction_intent_policy.py
app/tstation-ai/services/tstation/policies/transaction_response_policy.py
app/tstation-ai/services/tstation/policies/reservation_template_policy.py
app/tstation-ai/services/tstation/template_mapper.py
```

## Ownership Map

Use this table before changing code.

| Problem Area | Owning Layer | Notes |
|---|---|---|
| Current-turn intent, domain, protected high-confidence router contract | `turn_contract.py`, router/cross-domain policy | Prefer router when safe; override only for hard safety or slot/tool contract. |
| Active vs dormant context, stale context invalidation | `flow_state.py` | Product/size/quantity/store/schedule changes must clear dependent context. |
| Missing slots, next flow step, next expected tool/template | `flow_controller.py` | This is the state-machine step resolver. |
| UI card/chip selection, CTA interpretation, slot patch normalization | `ui_action_policy.py`, `reservation_template_policy.py` | UI actions should not be parsed as plain text in `chat.py`. |
| Required tool candidate after contract/flow progress | `contract_required_tool_candidate.py` | Candidate construction only; do not execute tools here. |
| Required tool execution/recovery/continuation | `contract_required_tool_executor.py` | Should not import from `chat.py`; move response builders out when found. |
| Tool output to FE template mapping | `template_mapper.py`, `reservation_template_policy.py` | Map data to templates only; do not invent flow intent. |
| Orchestration, streaming, tracing, final persistence | `chat.py` | Keep this layer thin. |

## Debugging Order For Every Reproduced Issue

Check the trace or local logs in this order:

1. Current user text and normalized UI action/chip context.
2. Router output: domains, execution plan, planner intent, confidence, reference resolution.
3. `TurnContract`: domain, intent, required slots, blocking slots, allowed tools, forbidden tools, preferred tool, response decision, context state, flow id/step.
4. `active_flow_context` and dormant flow context before the turn.
5. Called tools and their inputs.
6. Tool-derived slot changes and post-tool `TurnContract` rebuild.
7. Contract-required tool candidate and executor result.
8. Final template and `assistant_response_source`.
9. Contract/QC violations and fallback selection.
10. Persisted slots, `active_flow_context`, dormant context, and `template_data`.

Do not patch until you can answer which column of the relevant flow table is wrong:

```text
Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence
```

The flow tables must keep tools and FE templates/actions separate:

- Tools: `search_product_tool`, `get_store_list_tool`, `get_store_schedule_tool`, `quick_order_tool`, and other backend/tool calls.
- Templates/actions: `quickReply`, `product`, `location`, `datepick`, `preOrder`, `orderComplete`, `qnaComplete`, and UI action metadata such as `location.isBookingFlow=true`.

## Current Stabilization Checkpoint

Status after steps 1-18E:

1. The five flow transition tables now separate backend tools from FE templates/actions, next tool, next template/action, and expected persistence.
2. Purchase, stock, store, support, and reservation/preorder boundaries have focused regression coverage in the existing policy test suites.
3. Purchase flow now treats price as a required preOrder boundary:
   - `datepick` slot-fill may continue only to price resolution when price basis is missing.
   - `preOrder` is allowed only when product, tire size, quantity, store, schedule, and price basis are active and compatible.
   - `orderComplete` is still allowed only after successful order execution, not from stale preorder context.
4. Stale product/store/schedule/payment context invalidation has been tightened in `flow_state.py` and purchase flow resolution.
5. Flow continuation is centralized through `flow_controller.py`, `contract_required_tool_candidate.py`, and direct executor paths instead of one-off orchestration branches.
6. Support-policy turns during purchase/stock/store context now keep transaction tools dormant unless the user explicitly resumes commerce.
7. Direct executor regression tests can run without the previous `langgraph.runtime.ExecutionInfo` import blocker by importing tool decorators from `langchain_core.tools`.
8. Purchase and reservation/preorder transition rows now have a compact matrix test for schedule request, schedule slot-fill, preOrder readiness, order execution, and reservation-policy drift.
9. Stock, store, and support transition rows now have matrix coverage for inventory-only, preview schedule, unavailable inventory, store-only booking-action blocking, support policy dormant parent contexts, and explicit purchase resume.
10. Stock post-tool continuation now has direct executor coverage proving product resolution can continue to inventory lookup, and mapper output is contract-checked before recovery emission.
11. Store-only and purchase schedule recovery paths now have mapper/template compatibility coverage, including blocking `datepick` from store-only results and blocking premature `preOrder` before the purchase schedule/price boundary is complete.
12. Next-turn persistence assertions now cover stale preorder invalidation, support-policy turns ignoring stale preorder/template metadata, and stock context moving into purchase only when the current turn explicitly resumes purchase.
13. Step 17D audit found no additional owner-layer gaps exposed by the new transition coverage; focused checkpoint tests and ruff both pass without adding new `chat.py` branches.
14. Step 18A added a risky-template contract matrix for `datepick`, `preOrder`, `orderComplete`, `product`, `location`, and `voucher`, with one allowed and one forbidden contract-field case for each template.
15. Step 18B now sanitizes guard-event contract snapshots so blocked-template fallbacks emit safe `quickReply` payloads without carrying stale `template_data`, `ui_action`, `pending_intent`, or `goal_type` context into guard metadata.
16. Step 18C tightened the hard template gate so `orderComplete` requires the current execution event to include `quick_order_tool`, and added direct executor coverage proving support recovery builders cannot override contract blocks with action templates.
17. Step 18D centralizes final UI-action handling through `finalize_ui_action_metadata_for_contract()`, so final buffered events are normalized and contract-validated before yield/persistence boundaries.
18. Step 18E keeps mapper priority subordinate to the current contract by annotating direct-executor mapper events with current `called_tools` before validation, and adding coverage for compatible mapper output, forbidden mapper output, and same mapper event/different contract outcomes.
19. Phase 9 local E2E exposed an active-purchase interrupt gap where support/policy questions could be consumed as purchase slot-fill values. Steps 19A-19B make router-wins informational/policy intents override `expected_slot_fill:*`, dormant the purchase context, and drop interrupted `region`, `store`, and `schedule` slot-fill values before contract validation.

Verified checkpoint command:

```powershell
$env:PYTHONPATH=(Resolve-Path app/tstation-ai).Path
uv run pytest `
  app/tstation-ai/tests/test_context_transition_contracts.py `
  app/tstation-ai/tests/test_transaction_intent_policy.py `
  app/tstation-ai/tests/test_price_basis_policy.py `
  app/tstation-ai/tests/test_contract_required_tool_candidate.py `
  app/tstation-ai/tests/test_contract_direct_executor.py `
  -q
```

Latest result: `132 passed, 1 warning`.

Current next step:

```text
Phase 9: run end-to-end SSE verification for the stabilized purchase, stock, store, support, and reservation boundaries.
```

If Phase 9 exposes a remaining boundary gap, add the smallest scenario coverage and persistence assertion for that transition row. Do not add new flow branches in `chat.py` unless a transition-table row proves the owner layer cannot express the behavior.

## Phase 0: Freeze Patch-Level Expansion

Goal: stop making the architecture harder to stabilize.

Steps:

1. Do not add new broad keyword routes or case-specific flow helpers in `chat.py`.
2. If a temporary `chat.py` guard is unavoidable, document the exact transition-table row and add a TODO with the target owner layer.
3. Inventory any new issue under one of the five flow tables before coding.
4. Keep fixes surgical and tied to a regression test.

Success criteria:

- New flow bugs are classified by transition-table row.
- No new unowned context source is added.
- No new template/action decision is added directly to `chat.py` unless explicitly justified.

## Phase 1: Build A Transition-Test Harness

Goal: make the flow tables executable as regression tests.

Steps:

1. Create or extend test helpers that can build these objects from a compact scenario fixture:
   - input user text
   - existing slots
   - active/dormant flow context
   - optional UI action/chip context
   - optional latest template data
   - optional mocked router result
2. For each scenario, assert:
   - `TurnContract.domain`
   - `TurnContract.intent`
   - `blocking_required_slots`
   - `allowed_tools`
   - `forbidden_tools`
   - allowed templates/actions
   - forbidden templates/actions
   - `preferred_tool`
   - active/dormant flow state after slot merge
   - contract-required tool candidate, if any
   - final expected template or fallback guard
   - expected persistence state after final slot commit
3. Add post-tool continuation scenarios that assert the whole sequence:

   ```text
   initial TurnContract
   -> first required tool input/output
   -> tool-derived slot delta
   -> rebuilt FlowState
   -> rebuilt TurnContract
   -> next required tool candidate or terminal template/action
   ```

4. Add two-turn and three-turn persistence scenarios for stale context risks:
   - persisted `active_flow_context`
   - persisted `dormant_flows`
   - persisted `template_data`
   - persisted `pending_intent` and `goal_type`
   - `final_persist_flow_state_before`
   - `final_persist_flow_state_after`
5. Add a small matrix file or parametrized tests for each transition table.
6. Use existing tests where possible instead of creating duplicate fixtures.

Useful existing test areas:

```text
app/tstation-ai/tests/test_contract_required_tool_candidate.py
app/tstation-ai/tests/test_contract_direct_executor.py
app/tstation-ai/tests/test_transaction_intent_policy.py
app/tstation-ai/tests/test_transaction_response_policy.py
app/tstation-ai/tests/test_template_mapper_location.py
app/tstation-ai/tests/test_reservation_template_policy.py
app/tstation-ai/tests/test_support_response_policy.py
app/tstation-ai/tests/test_cross_domain_policy.py
app/tstation-ai/tests/test_router_context_evidence.py
```

Success criteria:

- Every high-risk row in the five transition tables has at least one contract-level test.
- Purchase and stock have post-tool continuation tests.
- Store and support have negative drift tests.
- Reservation/preorder has stale context and template gating tests.
- At least one test per major flow validates persisted state across the next user turn.
- No transition harness test requires adding a new phrase-specific branch in `chat.py`.

## Phase 2: Stabilize Purchase Flow First

Why first: purchase touches product, quantity, store, schedule, price, `datepick`, `preOrder`, and `quick_order_tool`.

Scope:

```text
docs/flow-transition-tables/purchase_flow.md
docs/flow-transition-tables/reservation_preorder_flow.md
```

Steps:

0. Update the purchase and preorder transition tables to separate:
   - allowed/forbidden tools
   - allowed/forbidden templates/actions
   - next tool
   - next template/action
   - expected persisted state
1. Make product selection canonical.
   - UI product card selection must be handled through `ui_action_policy.py`.
   - Plain text product labels should not create order context unless current-turn intent supports it.
2. Enforce stale product invalidation.
   - New product/size must clear old `goods_no`, store, schedule, payment, and price source fields.
   - Verify both `ConversationSlots` and `flow_state.py` dependency resets agree.
3. Enforce quantity progression.
   - Quantity-only turns should continue only when purchase/stock parent context is active or resumed.
4. Enforce store progression.
   - Product + quantity + store/region should allow store resolution tools.
   - `quick_order_tool` remains forbidden until schedule and preorder fields are ready.
5. Enforce schedule progression.
   - Store selected or resolved should prefer `get_store_schedule_tool` when schedule is missing.
   - Date/time slot fill after `datepick` should build `preOrder` only when product, quantity, store, schedule, and price are active and compatible.
6. Enforce purchase/support boundary.
   - Support policy during purchase makes purchase context dormant.
   - Explicit purchase resume can reactivate dormant purchase context.

Primary owner files:

```text
flow_state.py
flow_controller.py
ui_action_policy.py
turn_contract.py
contract_required_tool_candidate.py
contract_required_tool_executor.py
reservation_template_policy.py
template_mapper.py
```

Success criteria:

- Product changes never reuse old store/schedule/payment fields.
- Store selection continues to schedule lookup when contract allows it.
- Schedule slot fill builds `preOrder` only with complete compatible order slots.
- `quick_order_tool` runs only for explicit ready preorder execution.
- `preOrder` is blocked unless product, tire size, quantity, store, schedule, and price basis are active and compatible.
- `orderComplete` appears only after a successful order tool result, never from stale preorder context alone.

## Phase 3: Stabilize Stock Flow

Scope:

```text
docs/flow-transition-tables/stock_flow.md
```

Steps:

0. Update the stock transition table to separate tool boundaries from template/action boundaries.
1. Separate pure inventory from today-install/schedule intent.
   - Pure stock checks must not emit `preOrder`.
   - Pure stock checks must not emit `datepick` unless schedule availability is part of current-turn intent.
2. Ensure product-first resolution can continue into stock tools.
   - `search_product_tool` can fill `goods_no`.
   - The same turn should continue to store/inventory lookup if the active stock flow has enough slots.
3. Enforce unavailable inventory guards.
   - Unavailable inventory blocks `datepick`, `preOrder`, and `quick_order_tool`.
   - Offer other-store search or safe `quickReply`/`location` fallback.
4. Keep purchase context dormant unless the user explicitly asks to buy/order.

Primary owner files:

```text
transaction_intent_policy.py
transaction_response_policy.py
flow_state.py
flow_controller.py
contract_required_tool_candidate.py
contract_required_tool_executor.py
template_mapper.py
reservation_template_policy.py
```

Success criteria:

- Inventory-only and today-install flows have distinct contracts and expected templates.
- Product resolution followed by inventory/store lookup works in the same turn when executable.
- Unavailable inventory cannot produce `datepick` or `preOrder`.
- A stock flow can transition to purchase/preorder only when the current turn explicitly asks to buy, reserve, or install.

## Phase 4: Stabilize Store Flow

Scope:

```text
docs/flow-transition-tables/store_flow.md
```

Steps:

0. Update the store transition table to separate tools from templates/actions, including `location.isBookingFlow=true`.
1. Keep store search/detail separate from purchase.
   - Store search can show `location`.
   - Store search must not start `quick_order_tool`, `transaction_store_preview_tool`, or `datepick` without booking/order intent.
2. Treat `location.isBookingFlow=true` as an action boundary.
   - It requires current-turn booking/order intent or an active parent purchase/stock flow.
3. Verify store service/attribute requests with store data when possible.
   - If data cannot verify the claim, answer with an explicit limitation instead of creating booking/order flow.
4. Allow selected store to resume purchase/stock only when a compatible parent flow exists.

Primary owner files:

```text
transaction_intent_policy.py
transaction_response_policy.py
flow_state.py
flow_controller.py
ui_action_policy.py
template_mapper.py
reservation_template_policy.py
```

Success criteria:

- Store-only turns never emit `datepick`, `preOrder`, or `quick_order_tool`.
- Store selection resumes purchase/stock only with compatible active or resumed parent context.
- Store service/attribute questions do not drift into order flow.
- `location.isBookingFlow=true` is emitted only when the current contract allows a booking/order action.

## Phase 5: Stabilize Support Flow

Scope:

```text
docs/flow-transition-tables/support_flow.md
```

Steps:

0. Update the support transition table to include active purchase, stock, and store parent contexts.
1. Separate general policy from owned-record lookup.
   - General cancel/refund/payment/coupon policy should use FAQ/RAG first.
   - Owned order/reservation/coupon tools are allowed only when current user text asks for personal records.
2. Keep purchase/stock/store context dormant during support turns.
   - Do not continue order/stock tools after a support question unless the user explicitly resumes that flow.
3. Keep escalation explicit.
   - `transfer_to_qna_tool` should run only for explicit human/1:1/inquiry intent or a supported fallback path after FAQ.
4. Ensure support contract forbids transaction tools for policy-only turns.

Primary owner files:

```text
support_response_policy.py
turn_contract.py
flow_state.py
contract_required_tool_candidate.py
contract_required_tool_executor.py
template_mapper.py
```

Success criteria:

- General policy questions do not call owned-record tools.
- Support turns during active purchase/stock do not continue transaction tools.
- Explicit escalation produces `qnaComplete`; normal FAQ produces `quickReply`.
- Support turns during active store search do not start booking/order actions unless the user explicitly resumes purchase/stock.

## Phase 6: Stabilize Reservation And PreOrder Boundaries

Scope:

```text
docs/flow-transition-tables/reservation_preorder_flow.md
```

Steps:

0. Update the reservation/preorder transition table to separate:
   - new purchase reservation
   - existing reservation management
   - schedule selection templates/actions
   - order execution tools
1. Keep new purchase reservation separate from existing reservation management.
2. Gate `datepick`, `preOrder`, and `orderComplete` through `TurnContract`.
3. Schedule slot fill should build `preOrder` only when active order context is complete and compatible.
4. Existing reservation lookup/change/cancel should use owned-record tools and must not start new store schedule flow.
5. Reservation policy questions should use support FAQ first.

Primary owner files:

```text
reservation_template_policy.py
flow_controller.py
flow_state.py
turn_contract.py
contract_required_tool_candidate.py
contract_required_tool_executor.py
template_mapper.py
```

Success criteria:

- Existing reservation management does not reuse new purchase store/schedule context.
- New preorder flow does not reuse stale preorder when product/store/schedule changes.
- `orderComplete` appears only after successful order execution.

## Phase 7: Remove Reverse Dependencies From Executor To `chat.py`

Timing: start this in parallel with Phase 1 and Phase 2. Do not wait until all flow stabilization work is complete.

Current issue:

```text
contract_required_tool_executor.py imports response builders from services.tstation.chat
```

This means the executor still depends on the orchestration layer.

Steps:

1. Identify every helper imported by `contract_required_tool_executor.py` from `chat.py`.
2. Move response builders to the owning policy module:
   - reservation response builders -> reservation/order policy module
   - support FAQ/policy builders -> support response policy module
   - general cancel/card policy builders -> support/transaction policy module, depending on contract owner
3. Update executor imports to use policy modules only.
4. Add tests that call executor without importing `services.tstation.chat`.

Success criteria:

- No executor or policy module should import response builders from `services.tstation.chat`.
- Executor can be tested as a policy execution layer, not as a side effect of loading `chat.py`.
- `BaseAgent` contract-tool guard paths do not import support/order response builders from `services.tstation.chat`.
- Response-builder modules have focused unit tests independent of the streaming coordinator.

## Phase 8: Tighten Contract And Template Gates

Steps:

1. Review `violates_response_template_contract()` for all risky templates:
   - `datepick`
   - `preOrder`
   - `orderComplete`
   - `product`
   - `location`
   - `voucher`
2. Ensure `build_response_policy_guard_event()` and `build_required_slot_clarification_event()` produce user-safe `quickReply` responses for blocked states.
3. Ensure `template_mapper.py` never overrides an explicit contract block.
4. Ensure UI action metadata normalization and validation happen before final persistence.
5. Ensure mapper priority is subordinate to the current contract:
   - tool priority may choose among compatible renderers
   - tool priority must not authorize a forbidden template/action
   - previous tool/template context must not outrank current contract state
6. Add negative tests where the same tool output can map to different templates depending on contract.

Success criteria:

- Risky templates are blocked when required slots or source tool results are missing.
- Template fallback is deterministic and traced with `assistant_response_source`.
- UI action metadata matches the emitted template and contract intent.
- Every risky template/action has at least one allowed test and one forbidden test.
- Template mapper tests assert both tool input and contract/template compatibility, not only template name.

## Phase 9: End-To-End Verification

After unit/contract tests pass, run live or local SSE scenarios.

Minimum scenarios:

1. Product search -> product select -> quantity -> store -> datepick -> preOrder -> orderComplete.
2. Product stock lookup -> product resolution -> store inventory -> unavailable inventory fallback.
3. Store search -> store detail -> support policy question -> no transaction tool.
4. Active purchase -> support FAQ -> purchase dormant -> explicit purchase resume.
5. Existing reservation lookup -> no new `datepick` or `quick_order_tool`.
6. New product after preorder -> stale preorder invalidated.
7. General cancel fee policy -> FAQ answer, no owned order lookup.

Trace fields to confirm:

```text
router output
turn_contract
contract_drift
active_flow_context
dormant_flows
called_tools
final_template
qc_result
final_persist_flow_state_before
final_persist_flow_state_after
```

Operational note:

- For blocking QC behavior, use `AI_QC_ENABLED=true` and `AI_QC_PARALLEL=false`.
- If `AI_QC_PARALLEL=true`, QC is mostly observational for already-emitted data events.

## Phase 10: Cleanup And Guardrails

Steps:

1. Remove or quarantine obsolete one-off guards that are covered by transition tests.
2. Update `docs/router-override-inventory.md` whenever a deterministic override remains necessary.
3. Keep transition tables current when behavior intentionally changes.
4. Add comments only where ownership is non-obvious.
5. Avoid broad regex expansion without a transition-table row and a failing test.
6. Track `chat.py` policy surface:
   - no new phrase-specific routing helpers without an owner-layer TODO and transition-row test
   - no new response builders in `chat.py`
   - no new direct template/action decisions in `chat.py` when a policy or mapper owner exists
   - new orchestration code must call owner-layer APIs instead of duplicating their decisions

Success criteria:

- `chat.py` trends toward orchestration, not policy ownership.
- New bugs can be assigned to an owner layer quickly.
- Transition tests prevent regression when prompts or router behavior change.
- Response builders used by executor or `BaseAgent` live outside `chat.py`.
- Any remaining `chat.py` exception path is documented with the transition-table row it protects.

## How To Handle A New Bug Report

Use this workflow every time:

1. Reproduce the user turns and capture the full SSE event stream or Langfuse trace.
2. Pick the matching transition table and row.
3. Identify the first wrong column:
   - wrong intent/domain -> router, cross-domain policy, or `turn_contract.py`
   - wrong active/dormant context -> `flow_state.py`
   - wrong missing slot or next step -> `flow_controller.py`
   - wrong UI/chip/card interpretation -> `ui_action_policy.py` or `reservation_template_policy.py`
   - wrong tool candidate -> `contract_required_tool_candidate.py`
   - wrong tool execution/continuation -> `contract_required_tool_executor.py`
   - wrong template -> `template_mapper.py` or contract template guard
4. Add or update the smallest regression test for that row.
5. Make the smallest owner-layer fix.
6. Run focused tests, then relevant broader tests.
7. Check that no unrelated `chat.py` branch or prompt-only patch was introduced.

## Suggested Focused Test Commands

Adjust env values as needed for local setup.

```bash
uv run pytest app/tstation-ai/tests/test_contract_required_tool_candidate.py -q
uv run pytest app/tstation-ai/tests/test_contract_direct_executor.py -q
uv run pytest app/tstation-ai/tests/test_transaction_intent_policy.py -q
uv run pytest app/tstation-ai/tests/test_transaction_response_policy.py -q
uv run pytest app/tstation-ai/tests/test_template_mapper_location.py -q
uv run pytest app/tstation-ai/tests/test_reservation_template_policy.py -q
uv run pytest app/tstation-ai/tests/test_support_response_policy.py -q
uv run pytest app/tstation-ai/tests/test_cross_domain_policy.py -q
uv run ruff check app/tstation-ai/services/tstation app/tstation-ai/tests
```

For larger stabilization checkpoints:

```bash
uv run pytest app/tstation-ai/tests -q
```

## Definition Of Done

The stabilization effort is done when:

- all high-risk rows in the five transition tables have regression coverage
- the five transition tables separate tools from templates/actions
- purchase, stock, store, support, and reservation/preorder flows pass live SSE smoke tests
- `chat.py` no longer owns new flow-specific phrase parsing or template decisions
- `contract_required_tool_executor.py` and `BaseAgent` do not import response builders from `chat.py`
- stale product/store/schedule/payment context cannot override current-turn intent
- post-tool continuation works for product-resolution-to-transaction flows
- post-tool continuation rebuilds flow state and `TurnContract` before choosing the next tool/template
- persisted `active_flow_context`, `dormant_flows`, `template_data`, `pending_intent`, and `goal_type` cannot revive an incompatible flow on the next turn
- risky templates are contract-gated before final emission
- Langfuse traces expose enough metadata to diagnose the next failure without guessing
- source-priority overrides are visible in trace metadata

## Practical Priority Order

If time is limited, use this order:

1. Update the five flow tables to separate tools, templates/actions, next tool, next template/action, and expected persistence.
2. Add transition-test harness for purchase and stock.
3. Add post-tool rebuild/continuation assertions and next-turn persistence assertions.
4. Move executor and `BaseAgent` response-builder imports out of `chat.py` where they block isolated tests.
5. Fix stale context invalidation in `flow_state.py`.
6. Fix next-step resolution in `flow_controller.py`.
7. Fix post-tool continuation in candidate/executor layers.
8. Gate risky templates through `TurnContract`.
9. Add support/store negative drift tests.
10. Run live SSE smoke tests and update transition tables with any intentional behavior changes.
