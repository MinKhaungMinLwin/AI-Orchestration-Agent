# Chat V3 — Migrating V2 features to V3 (LLM-first, zero-regex)

> **Status:** Phases 0–8 implemented (2026-07-07) · **Flag:** `AI_CHAT_V3_PURE_LLM_ENABLED` · **V2 stays untouched.**

> **Price policy update (2026-07-21):** V3 uses `extra_fvr_sale_prc` as the user-visible product price and does not
> bind `get_cheapest_price_tool`. Member-held-coupon `cheapest_*` fields may remain in BE responses but are removed
> from V3 model/tool-context inputs and are not used for product cards or preorder payment amounts.

## Implementation status

The entire `services/tstation/chat_v3/` package has been written (24 files, ~1,266 lines total, largest file 196 lines).
Verified: zero-regex grep clean, ruff clean, mocked E2E passing across 5 scenarios (pure chat / guard path / router-failure degrade / rich template builder / service emits rich event).
Verified against a real LLM through Docker: fixed the OpenAI strict `response_format` 400 error by using `with_structured_output(..., method="function_calling")` on all 4 structured-output calls (router / composer / QC / template builder).

Phase 7 rich templates (2026-07-07): `templates.py` maps tool output → `product` / `location` / `listCar` / `cheapestProduct` via a mini-model structured-output call, validated against the exact Pydantic models in `agents/templates/schemas.py`. When a rich template is available it is emitted instead of quickReply (like V2 — cards carry no chips); if the build fails, the turn falls back to quickReply. Remaining templates (`datepick`, `preOrder`, `orderComplete`, `voucher`, `previewYoutube`, `qnaComplete`): TODO.

Deviations from the original plan (discovered during implementation):
- `g_qc_agent` **does not exist** in the repo (stale CLAUDE.md) → `qc.py` implements its own fact-check using a mini-model with structured output, gated by `AI_QC_ENABLED`.
- The `price_policy` guard was split into 3 guard ids (`coupon_issue_request`, `expired_coupon_or_event`, `nonexistent_benefit`); `pickup_service` into 2 (`pickup_status`, `pickup_info`) — the LLM routes sub-intents directly, 13 guards in total.
- History summary needs no V3 work: the API layer already uses `get_history_for_llm` (summary + recent messages) when building `request.messages`.
- Slots: fully reuses `ConversationSlots` + `merge()` (dependency resets) + `ChatHistoryService.get_slots/save_slots_async` — V3 only replaces the *extraction* step with an LLM (`SlotsPatch` inside RouteDecision).
- V2's dynamic guard texts (brand label, internal product price interpolation) were rewritten as equivalent static versions; the reservation-date guard computes dates with `datetime` (no regex).

## Non-negotiable principles

1. **No regex.** V2 has ~253 `re.*` usages in `chat.py` (40k lines). V3 bans `import re` for business logic.
2. **LLM-based routing instead of regex.** Every decision — "what intent is this / which guard applies / which slots" — is made by **one LLM router call with structured output**. No rule tables, no keyword matching.
3. **Basics first.** Each phase runs independently with success criteria; finish one phase before starting the next.
4. **One responsibility per file, < 200 lines** (per `docs/code-standards.md`). Never repeat the 40k-line `chat.py` mistake.
5. **FE contract unchanged.** V3 emits exactly the SSE events V2 emits (`token`, `message`, `data`, `status`, `agent_flow`, `DONE`, `[DONE]`) — neither the FE nor the API layer (`stream_chat_response`) needs changes.

---

## Target module layout: `services/tstation/chat_v3/`

Convert `chat_v3.py` (originally a single file) into a package:

```
services/tstation/chat_v3/
├── __init__.py          # public API: chat(request), enabled() — no logic
├── service.py           # single entrypoint: orchestrates router → executor → composer
├── llm.py               # LLM instances (chat model, router model AI_MODEL_MINI)
├── sse.py               # SSE event builders: token/message/data/status/agent_flow/DONE
├── context.py           # build messages: user info (JWT/UI), history, summary
│
├── prompts/             # one prompt per file, text only — no logic
│   ├── __init__.py
│   ├── persona.py       # T-Station persona system prompt
│   ├── router.py        # router-call prompt (intent + guard + slots)
│   └── composer.py      # final answer + quickReplies prompt
│
├── router/              # LLM-based routing — replaces all of V2's regex classification
│   ├── __init__.py
│   ├── schemas.py       # RouteDecision (Pydantic): guard_id, domain, intents, slots_patch
│   ├── route.py         # 1 structured-output LLM call → RouteDecision
│   └── guards.py        # canned guard responses (answer TEXT only — trigger decided by the LLM)
│
├── slots/               # conversation state
│   ├── __init__.py
│   ├── schemas.py       # V3 slots model (reuses ConversationSlots fields)
│   ├── extract.py       # LLM structured-output extraction — replaces extract_from_user_text regex
│   └── store.py         # read/write slots in Redis (reuses chat_history_service)
│
├── tools/               # per-domain tool registry — re-exports existing tools, NEVER rewrites them
│   ├── __init__.py      # registry: domain → [tools]; every tool registered here
│   ├── discovery.py     # from agents/b_discovery_agent/tools.py
│   ├── transaction.py   # from agents/c_transaction_agent/tools.py
│   └── support.py       # from agents/e_support_agent/tools.py
│
├── executor.py          # native tool-calling loop: LLM picks + calls tools, emits tool events
├── composer.py          # final answer + quickReplies (LLM-generated chips — no hardcoded rules)
├── templates.py         # validate/map output → FE templates (schemas.py is the source of truth)
└── qc.py                # optional: QC pass (self-contained LLM fact-check)
```

**Per-turn processing flow (once complete):**

```
request
  → context.py   (messages + user info + current slots)
  → router/      (1 LLM call: safety? guard? domain? new slots?)
      ├─ guard   → guards.py returns canned response → sse → DONE
      └─ pass    → executor.py (tool-calling loop with the domain's tools)
                     → composer.py (answer + quickReplies + template)
                     → templates.py (validate FE payload)
                     → sse → DONE
  → slots/store.py (persist slots after the turn)
```

---

## Conversion table: V2 regex → V3 LLM

| V2 (regex/rule) | V3 (LLM-based) |
|---|---|
| `check_pii()` regex | `router` call returns `guard_id: "pii"` — guard text kept, only the trigger changes |
| 10 fast-path guards (`_privacy_contact_request_event`, `_is_regional_cheapest_query`, `_price_policy_guard_event`, …) | `router` returns a `guard_id` enum; `guards.py` keeps the canned answer **content** verbatim |
| `_rule_based_classify` + `_goal_based_classify` + `classify_multi_intent` (3 layers) | One `domain` field + `intents[]` in RouteDecision |
| ~60 `_router_contract_*` / `_restore_*_contract` override functions | Dropped entirely — the router prompt states the criteria, no post-hoc patching |
| `ConversationSlots.extract_from_user_text` (regex slots) | `slots/` structured output (`SlotsPatch`) |
| Rule-based agent dispatch by prefix (a_/b_/c_/e_) | LLM tool-calling: tools bound per domain, the model picks the tool itself |
| `f_ui_template_agent` rendering | `composer.py` + `OUTPUT_TEMPLATE`-style validation (aligned with the ongoing refactor) |

**Key insight:** the guard/canned **response text** was never regex — only the **trigger** was. V3 keeps the text verbatim and replaces the trigger with the LLM router. This is the cheapest part of the port.

---

## Implementation steps (basic → advanced)

### Phase 0 — Split into a package (no behavior change) — ✅ DONE
- [x] Convert `chat_v3.py` → package `chat_v3/` with `__init__.py`, `service.py`, `llm.py`, `sse.py`, `prompts/persona.py`
- [x] `chat.py` keeps working unchanged (`from services.tstation.chat_v3 import ...` resolves via `__init__.py`)
- [x] Ruff + py_compile pass
- **Success:** flag on, pure-LLM chat behaves exactly as before.

### Phase 1 — Context: user info + history summary — ✅ DONE
- [x] `context.py`: port V2's `_build_messages_with_user_info` (JWT `get_user_info_from_token`, merge `request.user_info`, USER CONTEXT block) — pure formatting, no regex
- [x] History summary needs no work — API layer already includes it via `get_history_for_llm`
- **Success:** the bot knows the user's name and location (xpos/ypos), remembers long sessions.

### Phase 2 — LLM Router (V3's backbone) — ✅ DONE (sample-sentence test set: TODO)
- [x] `router/schemas.py`: `RouteDecision` Pydantic — `guard_id` (13-guard enum or none), `domain` (LEADING/DISCOVERY/TRANSACTION/SUPPORT), `intents[]`, `slots_patch`
- [x] `router/route.py`: one `AI_MODEL_MINI` call with `with_structured_output(RouteDecision)` — safety + guard + classify merged into **one** call to protect latency
- [x] `router/guards.py`: canned guard responses copied verbatim from V2 (regional cheapest, unsupported brand, coupon policies, reservation date, vehicle type, pickup, past events, privacy contact, PII, external price) — text + chips only, zero logic
- [x] `service.py`: route → guard hit streams the canned response; pass falls through to the executor
- [ ] Test set: Korean sample sentences per guard/domain, assert correct routing (pytest against the real router or a mock)
- **Success:** messages V2 blocked with regex are now blocked by V3 via LLM, with the same answers.

### Phase 3 — Slots via LLM — ✅ DONE
- [x] `slots/schemas.py`: V3 slot-patch model (fields taken from `ConversationSlots`: car_no, region, schedule, goal_type, pending_intent…)
- [x] Extraction merged into the **same router call** (`slots_patch` field on RouteDecision) — no extra call
- [x] `slots/store.py`: persist/merge slots via Redis, reusing `ConversationSlots.merge()` (dependency resets) — plain dict merge, no regex; invalid LLM values dropped via Pydantic validation
- [x] Slots injected into the system context for subsequent calls
- **Success:** user states their plate number once, the bot still remembers next turn; changing cars resets dependent slots correctly.

### Phase 4 — Read-only tools (Discovery first — safest) — ✅ DONE
- [x] `tools/discovery.py`: 20 tools registered (search, recommendations, compatibility, vehicles, events, prices)
- [x] `executor.py`: binds tools per `RouteDecision.domain`, native tool-calling loop (max 4 rounds), the LLM **decides** which tool to call — no dispatch rules
- [x] `sse.py`: emits `status: tool_start` (+ display name from `TOOL_DISPLAY_NAMES`), `tool`, `agent_flow` like V2 so the FE shows progress
- [x] BE token set via `set_tstation_be_token(request.access_token)` before the executor runs
- **Success:** "타이어 추천해줘" → the bot calls real tools and returns real products.

### Phase 5 — Store search + FAQ (still read-only) — ✅ DONE
- [x] `tools/transaction.py` (read side): 21 store/price/order-lookup tools
- [x] `tools/support.py`: FAQ hybrid search, warranties, maintenance d-day, escalation — 8 tools
- **Success:** finds stores near the user's location, answers FAQs from RAG.

### Phase 6 — Transaction writes (dangerous — done last among tools) — ✅ DONE (confirmation via prompt)
- [x] `tools/transaction.py` (write side): `quick_order_tool`, `save_to_cart_tool`, `issue_coupon_tool` — kept in a separate `TRANSACTION_WRITE_TOOLS` list
- [x] Confirm-before-write enforced in the **prompt** (`TRANSACTION_WRITE_GUIDANCE`): the LLM must summarize product/quantity/store/schedule and get explicit user confirmation before calling any write tool
- [x] Order slots (goods_no, ord_qty, schedule) flow through `slots/` like any other slot
- **Success:** end-to-end ordering includes a confirmation step; no accidental orders.

### Phase 7 — FE templates + quickReplies — ✅ DONE (product/location/listCar/cheapestProduct; transactional templates datepick/preOrder/orderComplete: TODO)
- [x] `composer.py`: after the executor, one mini-model call generates context-relevant `quickReplies` (replaces V2's hardcoded chip tables)
- [x] `templates.py`: map tool results → rich FE templates (`product`, `location`, `listCar`, `cheapestProduct`) validated against the Pydantic models in `agents/templates/schemas.py` (single source of truth)
- [x] Structured output via `with_structured_output(..., method="function_calling")` — no fenced-JSON parsing needed
- **Success:** the FE renders product cards / store lists exactly like V2.

### Phase 8 — QC + observability + hardening — ⚠️ PARTIAL (Langfuse spans + router test set: TODO)
- [x] `qc.py`: self-contained LLM fact-check (answer vs raw tool outputs) after the executor, toggled by `AI_QC_ENABLED`; corrections emitted as `qc_correction` events
- [ ] Langfuse tracing: parent `chat_v3` span, child spans for router/executor/composer
- [x] Per-stage latency logging (route/tools/total) under the `[CHAT_V3]` log prefix
- [x] Chip context / `ui_action` from the FE: fed into the **router input** (as context) instead of fast-path rules
- **Success:** full traces in Langfuse; QC fixes factually wrong answers.

---

## Gap audit V2 → V3 (2026-07-07, full sweep of chat.py + policies/ + helpers/ + api layer)

**Critical (production blockers):** — ✅ ALL 5 RESOLVED (2026-07-07, see per-item notes)
1. ✅ **Multi-domain within one turn** — V2 chains agents (`[DISCOVERY, TRANSACTION]` auto-chains, execution_plan, nextAction continue, stall recovery). V3 binds exactly one domain's tools → "order a Ventus" with no goods_no stalls (search_product is DISCOVERY, ordering is TRANSACTION). → FIXED: `RouteDecision.extra_domains` + `tools_for_domains()` union (deduped by tool name); the router prompt explains when to add a secondary domain.
2. ✅ **Cross-turn tool-context memory** — V2 stores tool outputs in Redis (`chat:tool_ctx:*`, 2h TTL) and injects them into the next turn's prompt (`_format_tool_context`); → FIXED: `chat_v3/memory.py` — reads `chat:tool_ctx` at turn start into a `PREVIOUS TOOL RESULTS` block, persists at turn end via `finalize_chat_context_async` (incl. quick_reply_domains/predicted_domains — V2-compatible).
3. ✅ **Transactional templates** (`datepick`/`preOrder`/`orderComplete`) — ADDED to `_TOOL_TEMPLATES` (schedule tools → datepick, store_preview → preOrder, quick_order/save_to_cart → orderComplete) → the ordering flow can't render on the FE; the `quick_order_execute` CTA (`/actions/quick-order` endpoint) needs a `preOrder` template to complete the chain.
4. ✅ **car_no audit not seeded** — FIXED: `service.py` calls `_audit_set_user_message(user_text)` at turn start — V2 calls `_car_no_audit.set_user_message(last_user_msg)` at turn start; V3 doesn't → the wrong-vehicle recommendation guard inside discovery tools is inert (2-line fix in `service.py`).
5. ✅ **Token double-render on the real FE** — FIXED: `AI_CHAT_V3_STREAM_TOKENS` flag (default true for the demo UI; set false for the production FE, which renders from `data.assistantResponse` like V2) — V2 does **not** forward `token` events (FE renders from `data.assistantResponse`); V3 streams tokens. The demo UI is fine; the production FE must be checked for duplicated text.

**Medium:**
6. QC: V2 uses **deterministic** `qc_verifier.verify_draft` (compares prices/goods_no/shop_id/size/dates/ranking/brand against tool output, with a repair loop) — V3 should reuse it (free, no LLM call) and keep LLM QC as a second layer.
7. Chips lack the **ui_action envelope** (`normalize_ui_action_metadata`: cta_id/cta_action/slot metadata) → V3 chip clicks send a poorer `chip_context` than V2; label-only CTAs (`enter_region`/`enter_date`) have no canned clarification.
8. **Fallback chips** when the composer fails/returns empty (V2 has tool-aware `_FALLBACK_*` families) — V3 returns `[]`.
9. **Order-flow slot recovery** (rehydration from preOrder/datepick templates, `_finalize_purchase_stock_slots_for_persistence`) — V3 relies on LLM extraction alone; long flows can drop goods_no/qty.
10. Langfuse spans (already in the Phase 8 TODO).

**Dropped deliberately (V3 philosophy — not ported):** ~200 direct-code fast-path handlers for known-answer queries, TurnContract + the entire template-coercion/contract-gate machinery, speculative classify + validated_ui_action_router_skip, the 3-layer classifier, router contract overrides. Precondition for confidence: the sample-sentence test set (Phase 2 TODO) must cover these cases.

## Ongoing quality controls

- **Zero-regex check:** add to CI/pre-commit: `grep -rn "^import re\|^from re\|re\.compile\|re\.search\|re\.match" app/tstation-ai/services/tstation/chat_v3/` must return nothing.
- **File size check:** no file in `chat_v3/` may exceed 200 lines.
- **No imports from `chat.py`:** `chat_v3/` may only import from `agents/*/tools.py`, `agents/templates/schemas.py`, `chat_history_service`, `common/*`, `config` — never pull helpers from `chat.py` (avoids dragging in regex and tangled dependencies).
- **Latency budget:** the router call uses `AI_MODEL_MINI`; total target ≤ V2 (which pays for 3 classification layers + a sequential guard chain).

## Known risks

| Risk | Mitigation |
|---|---|
| LLM router misses a guard that regex caught 100% of the time | Per-guard sample-sentence test set in CI; router prompt lists examples per guard |
| Latency increase from the extra router call | Safety + guard + classify + slots merged into one mini-model call; V2 pays a comparable cost |
| Write tools called by mistake | Phase 6 done last; mandatory confirmation in the prompt; staging tests first |
| Router call failure | Fallback: pure chat (Phase 0 behavior) — soft degrade, the request never dies |

## Operations

| Env var | Role in V3 |
|---|---|
| `AI_CHAT_V3_PURE_LLM_ENABLED` | V3 switch (`false` = V2; rollback needs only a restart) |
| `AI_MODEL` | Main conversation model (executor) |
| `AI_MODEL_MINI` | Router + composer + QC |
| `AI_QC_ENABLED` | Enables the fact-check pass |

V3 shares Redis storage with V2 (`ChatHistoryService` — history, summary, slots use the same keys/schema), so flipping the flag mid-session loses no conversation context. Trace logs use the `[CHAT_V3]` prefix: route decision, guard hits, tool count, per-stage latency.
