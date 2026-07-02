# TurnContract Policy Stabilization Current Work

Branch: `stabilize-turn-contract-policy`
Date: 2026-06-23

## Objective

Reduce regressions caused by fixed regex/code-path answers by introducing a per-turn contract that combines:

- LLM planner result: current intent, multi-domain execution order, reference resolution, confidence.
- Slot state: known slots, blocking required slots, context-resolvable required slots.
- Tool policy: allowed tools, forbidden tools, high-risk post-tool failure constraints.
- Response policy: allowed response shape/template and forbidden behaviors.
- QC policy: deterministic contract/template violations and factual mismatch fallback.

The intended responsibility split is:

- LLM/planner judges user intent and previous-context reference resolution.
- Code policy validates safety invariants and blocks only clearly unsafe tool/template responses.
- Agent/tool execution remains responsible for BE data retrieval and normal response generation.
- QC verifies final response against tool data and the turn contract before emitting sequential responses.

## Current Coverage

This branch covers Phase 2 and part of Phase 3.

Implemented coverage:

- Router schema now includes `referred_object_status`, `referred_object_type`, `needs_clarification`, and `planner_confidence`.
- Router prompt now asks for one or more ordered domains and reference-resolution judgment.
- `TurnContract` aggregates planner intent, domain order, slot state, tool plan, response decision, and contract drift.
- Missing or ambiguous referred objects are guarded even when planner starts with `discovery`.
- Blocking required slots are separated from slots that can be resolved by the discovery step.
- High-risk missing-slot turns return a safe `quickReply` before agent/tool execution.
- High-risk post-tool failures and parse failures generate forbidden behaviors and safe response policy.
- Post-tool forbidden behaviors are accumulated through the whole turn instead of being overwritten by later successful tools.
- Template guard blocks risky templates such as `datepick`, `preOrder`, `orderComplete`, `billProduct`, and `voucher` when they conflict with required slots or tool-result policy.
- QC can replace buffered sequential responses with a safe fallback for contract violations or factual mismatches.
- Real-dialogue regression tests cover source-less product cards after unresolved price follow-ups.

## Key Risk Controls

Pre-tool controls:

- `그거 구매할래`, `그거 가격 알려줘`, `가격 얼마야?` without a resolvable product should clarify before tool execution.
- Product-name price requests such as `벤투스 에어S 가격 알려줘` can route through discovery then transaction without being blocked as missing product.
- Ambiguous product-set references should not select the first product implicitly.

Post-tool controls:

- Price tool failure blocks price assertion templates.
- Coupon tool failure blocks coupon/application assertions.
- Inventory unavailable blocks `datepick` and `preOrder`.
- Order tool failure blocks `orderComplete`.
- Parse failure from high-risk tools is treated as unsafe and cannot produce success/price/order/coupon assertions.

QC controls:

- Contract violations are logged and can be replaced with policy fallback.
- Factual mismatches can be replaced with `code_qc_factual_mismatch_guard`.
- Sequential QC is required for actual blocking.

## Test Focus

Highest-priority real dialogue flows:

- New session: `그거 구매할래` -> clarify product, no transaction tool.
- New session: `가격 얼마야?` -> clarify product, no price assertion.
- New session: `벤투스 에어S 가격 알려줘` -> discovery resolves product, transaction price path can proceed.
- Product card selected, then `그거 구매할래` -> use selected product, no missing-reference guard.
- Multiple product cards, then `그거 가격 알려줘` -> clarify if ambiguous, no first-row fallback.
- Prior recommendation, then `주말 장거리용으로 다른 거 추천해줘` -> new recommendation, no stale goods/payment state.
- `가격이랑 쿠폰 알려줘` with price tool failure and coupon success -> keep price forbidden behavior to turn end.
- Inventory unavailable, then agent attempts reservation UI -> replace `datepick`/`preOrder` with safe `quickReply`.
- `dynapro hp3 설명해줘` -> product description/search, not transaction clarification.
- QC mismatch with `AI_QC_ENABLED=true` and `AI_QC_PARALLEL=false` -> safe fallback before response emission.

## Operational Requirements

For the target "QC before response" behavior:

- `AI_QC_ENABLED=true`
- `AI_QC_PARALLEL=false`

If `AI_QC_PARALLEL=true`, data events are emitted before QC and QC becomes observation/logging only for already-emitted data.

## Remaining Work

- Verify production/dev environment variables use sequential QC for launch.
- Run real SSE E2E scenarios on the dev agent server, not only unit tests.
- Confirm Langfuse traces include `turn_contract`, `contract_drift`, `contract_violations`, and QC mismatches.
- Expand factual QC beyond current core fields into coupon applicability, inventory quantity, store/date availability, and order success.
- Continue shadow-log review for planner reference judgments to find false positives and false negatives before adding broader hard guards.

## Latest Local Verification

Command:

```bash
PYTHONPATH=app/tstation-ai REDIS_QUEUE_URL=redis://localhost:6379/0 AI_MODEL_REASONING=dummy AI_MODEL_MINI=dummy AI_MODEL_LEADING_AGENT=dummy AI_MODEL_QC_AGENT=dummy AI_MODEL_TRANSACTION_AGENT=dummy UV_CACHE_DIR=/tmp/uv-cache uv run pytest app/tstation-ai/tests/test_quickreply_fallback_routing.py -q -k 'turn_contract or transaction_policy_context or qc_factual_mismatch or real_dialogue'
```

Result:

```text
39 passed, 519 deselected, 1 warning
```

Command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check app/tstation-ai/tests/test_quickreply_fallback_routing.py
```

Result:

```text
All checks passed!
```
