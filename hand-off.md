# T-Station AI Stabilization Handoff

Hi team,

We need to treat the current `tstation-ai` situation as a high-priority stabilization issue.

Current branch/repo:

```text
https://github.com/bluedragonvnbiz/tstation-agent/tree/aaron
```

Current local reference:

```text
branch: aaron
latest observed commit: 420a1f4d Build preorder when order slots are ready
```

## Current Refactoring Direction

The recent refactoring direction was to stop adding ad-hoc logic in `chat.py` and instead centralize execution decisions
around:

- `TurnContract`
- `flow_state`
- `flow_controller`
- `ui_action_policy`
- `contract_required_tool_executor`

The intended architecture is:

```text
Current user turn intent
-> TurnContract
-> Active / dormant flow state
-> Flow controller progress
-> Required tool execution
-> Deterministic template/action mapping
```

The main goal is to prevent `chat.py` from directly interpreting phrases, card labels, or previous template metadata and
making case-specific decisions.

## Current Critical Problem

The system is still unstable in several core flows.

The most serious issues are:

1. Previously selected product/store/quantity/schedule context is sometimes forgotten or incorrectly reused.
2. `purchase`, `stock`, `store`, and `support` flows can drift into another domain mid-conversation.
3. After a tool fills new slots, the same turn often does not continue using those newly filled slots.
4. Stale slots, `pending_intent`, `goal_type`, or previous template metadata sometimes override the current user intent.
5. `datepick`, `preOrder`, `location`, and product template selection can become inconsistent with the active contract.
6. Single-case regex/guard fixes are accumulating and causing regressions in nearby valid flows.

This is no longer just a bug-fixing issue. The core problem is execution-boundary instability between intent, flow state,
tool execution, and template selection.

## Important Files To Review First

Please review these files before making any patch:

```text
tstation-ai/app/tstation-ai/services/tstation/chat.py
tstation-ai/app/tstation-ai/services/tstation/policies/turn_contract.py
tstation-ai/app/tstation-ai/services/tstation/policies/flow_state.py
tstation-ai/app/tstation-ai/services/tstation/policies/flow_controller.py
tstation-ai/app/tstation-ai/services/tstation/policies/ui_action_policy.py
tstation-ai/app/tstation-ai/services/tstation/policies/contract_required_tool_candidate.py
tstation-ai/app/tstation-ai/services/tstation/executors/contract_required_tool_executor.py
tstation-ai/app/tstation-ai/services/tstation/policies/transaction_intent_policy.py
tstation-ai/app/tstation-ai/services/tstation/policies/transaction_response_policy.py
tstation-ai/app/tstation-ai/services/tstation/policies/reservation_template_policy.py
tstation-ai/app/tstation-ai/services/tstation/template_mapper.py
```

`chat.py` should remain the orchestration layer only. Please avoid adding new case-specific helper functions or
phrase-based branches there unless there is no other option.

## Key Rule Before Any Fix

Before adding a new condition, regex, or guard, please decide which layer owns the problem:

| Problem Area | Owning Layer |
|---|---|
| Intent, allowed tools, forbidden tools | `turn_contract.py` |
| Active vs dormant previous context | `flow_state.py` |
| Slot-fill progress and next step | `flow_controller.py` |
| UI action, CTA, template action interpretation | `ui_action_policy.py` or `reservation_template_policy.py` |
| Required tool candidate and execution continuation | `contract_required_tool_candidate.py` / `contract_required_tool_executor.py` |
| Tool output to FE template mapping | `template_mapper.py` |

Please do not fix flow bugs by adding more one-off logic directly in `chat.py`.

## Debugging Process

For every reproduced issue, please check Langfuse trace in this order:

1. Router output
2. `turn_contract`
3. `active_flow_context`
4. `called_tools`
5. `final_template`
6. QC result

Most failures happen because the current-turn intent and active flow state disagree, or because a stale previous
slot/template/action is treated as stronger than the current contract.

## What Was Recently Improved

Recent work already attempted to:

- Recalculate active flow progress after post-tool execution.
- Continue to the next required tool in the same turn when new slots are filled.
- Allow discovery/product-search flows to continue into purchase or stock tools when executable.
- Treat `preOrder` as ready when product, size, quantity, store, schedule, and price are filled.
- Prevent stale `goods_no`, price, store, and schedule from being reused when the selected product changes.
- Add regression tests around date/time slot-fill, same-day installation, registered vehicle recommendation,
  order/coupon/FAQ drift, purchase/stock continuation, and template consistency.

However, the structure is still not fully stable.

## Immediate Stabilization Work

Please do not continue with small patch-by-patch fixes first.

The recommended next step is:

1. Review the boundary between:
   - `TurnContract`
   - `FlowState`
   - `FlowController`
   - `UIActionPolicy`
   - `ContractRequiredToolExecutor`
2. Review and refine the state transition tables for the major flows.
3. Rebuild the E2E regression tests around those state transitions.

Initial transition table drafts have been added here:

```text
tstation-ai/docs/flow-transition-tables/purchase_flow.md
tstation-ai/docs/flow-transition-tables/stock_flow.md
tstation-ai/docs/flow-transition-tables/store_flow.md
tstation-ai/docs/flow-transition-tables/support_flow.md
tstation-ai/docs/flow-transition-tables/reservation_preorder_flow.md
```

Important correction: `preOrder`, `datepick`, `location`, and `orderComplete` are templates/actions, not tools. The flow
tables should keep tools and templates/actions separate.

Recommended table shape:

```markdown
| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| purchase | product_selected | purchase_confirm | selected product active | size, quantity, store, schedule | get_store_list_tool, get_store_schedule_tool | search_faq_hybrid_tool | resolve next missing slot or build preorder | quickReply/datepick/preOrder |
```

## Most Important Principle

The solution is not to remember more conversation context.

The correct solution is:

```text
Only promote context related to the current-turn intent into active flow state.
Keep unrelated context dormant.
Let the centralized flow state and contract decide the next valid action.
```

This should prevent:

- Stale slot reuse
- Previous template metadata overpowering current intent
- Purchase flow drifting into stock/store/support
- Support flow accidentally triggering transaction tools
- Tool execution ending too early after slot filling
- Template actions becoming inconsistent with contract state

## Final Warning

Please avoid adding another layer of regex-based or single-case defensive logic.

That approach has already caused repeated regressions.

At this point, we need to stabilize the architecture boundary first, then fix individual cases through cause-level
regression tests.
