# Chat V3 — LLM-first Chat Service

Third-generation chat service for T-Station AI: **every decision is made by an LLM, zero regex, zero rule tables**.
V2 (`services/tstation/chat.py`, ~40k lines) stays untouched and remains the default; V3 is enabled by a flag.

> Migration plan + per-phase status: [`docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`](../../../../../docs/chat-v3/MIGRATE_V2_TO_V3_EN.md)

---

## 1. Design philosophy

| Principle | Meaning |
|---|---|
| **Zero regex** | No `import re` anywhere in this package. V2 uses regex in ~253 places to catch intents/guards/slots — V3 replaces all of it with LLM calls. |
| **LLM-based routing** | A single mini-model call (`RouteDecision`) decides: which guard, which domain, which slots — no keyword matching. |
| **One responsibility per file, < 200 lines** | Never repeat the 40k-line `chat.py` mistake. |
| **Reuse, never rewrite** | Tools, template schemas, the slots model, and the Redis store are all imported from existing V2 code. |
| **FE contract unchanged** | V3 emits exactly the SSE events V2 emits — neither the FE nor the API layer needs changes. |
| **Soft degrade at every layer** | Any failing LLM/Redis call degrades in a controlled way; a turn never dies. |

---

## 2. Architecture — one turn end to end

```
POST /chat (api/tstation/chat_message.py — unchanged)
  └─ TStationChatServiceV2.chat()          # chat.py:23905
       └─ if AI_CHAT_V3_PURE_LLM_ENABLED → TStationChatServiceV3.chat()   # 5-line branch
            │
            ├─ ①  route_request()                        [LLM: AI_MODEL_MINI]
            │     RouteDecision { guard_id, domain, intents[], slots_patch }
            │
            ├─ ②  guard_id ≠ none?
            │     └─ YES → guards.py streams the canned response (token/message/data) → DONE
            │
            ├─ ③  slots: load (Redis) → merge slots_patch (ConversationSlots.merge)
            │
            ├─ ④  ToolLoopExecutor                       [LLM: TOOL_SELECTOR → COMPOSER]
            │     bind the domain's tools → LLM picks tools → run → loop (max 4 rounds)
            │     streams: token / tool_start / tool / agent_flow
            │
            ├─ ⑤  qc.verify_answer()          (optional)  [LLM: AI_MODEL_MINI]
            │     checks the answer against tool output, corrects factual errors (gate: AI_QC_ENABLED)
            │
            ├─ ⑥  templates.build_rich_data_event()       [LLM: AI_MODEL_MINI]
            │     tool output → card payload (product/location/listCar)
            │     └─ no matching template → composer.suggest_quick_replies() → chips
            │
            ├─ ⑦  emit: message + data event (rich template OR quickReply) → DONE
            └─ ⑧  save slots (Redis) + latency log
```

**LLM calls per turn:**
- Guard turn: 1 (router)
- Normal turn: 2–3 (router + chat; + template builder *or* chips)
- With QC enabled: +1

---

## 3. Directory layout

```
chat_v3/
├── __init__.py          # Public API: chat(request), enabled(), TStationChatServiceV3
├── service.py           # The one orchestrator — the entire ①→⑧ flow above
├── llm.py               # Router + V3 selector/composer/fallback model singletons
├── sse.py               # SSE event builders — the ONLY place stream events are formatted
├── context.py           # Builds the message list: history + USER CONTEXT (JWT/UI) + current_time
├── executor.py          # ToolLoopExecutor: native tool-calling loop, the LLM picks tools itself
├── composer.py          # Generates quickReplies chips via the mini model (replaces V2's hardcoded chip tables)
├── templates.py         # Maps tool output → rich FE templates (validated with V2's schemas)
├── qc.py                # Fact-checks the answer against tool output (gate: AI_QC_ENABLED)
│
├── prompts/             # TEXT only — no logic
│   ├── persona.py       # SYSTEM_PROMPT, TRANSACTION_WRITE_GUIDANCE, ERROR_RESPONSE
│   ├── router.py        # ROUTER_PROMPT: 13 guard triggers + 4 domains + slot rules
│   ├── composer.py      # Chips-generation prompt
│   └── templates.py     # Card-payload builder prompt
│
├── router/
│   ├── schemas.py       # RouteDecision, GuardId (13 + none), Domain (4)
│   ├── route.py         # Router call: 6-turn history + chip_context/ui_action + current date
│   └── guards.py        # 13 canned guard responses — text ported VERBATIM from V2, zero logic
│
├── slots/
│   ├── schemas.py       # SlotsPatch — the subset of fields the LLM can extract from user text
│   ├── enrich.py        # backfill product label (goods_nm/tire_size_1) from goods_no via product-detail API
│   └── store.py         # load/merge/save via ChatHistoryService + ConversationSlots.merge()
│
└── tools/
    ├── __init__.py      # tools_for_domain(domain) — registry, lazy imports
    ├── discovery.py     # 20 tools from agents/b_discovery_agent/tools.py
    ├── transaction.py   # 24 tools from agents/c_transaction_agent (READ 21 + WRITE 3)
    └── support.py       # 8 tools from agents/e_support_agent/tools.py
```

---

## 4. Layer details

### 4.1. Router (`router/`) — V3's backbone

One `AI_MODEL_MINI` call with `with_structured_output(RouteDecision, method="function_calling")` returns:

```python
RouteDecision(
    guard_id: GuardId,        # one of 13 guards or "none"
    domain: Domain,           # LEADING | DISCOVERY | TRANSACTION | SUPPORT
    intents: list[str],       # 1-3 free-form keywords, for logging/debugging
    slots_patch: SlotsPatch,  # slots newly stated this turn (merged in — no extra call)
)
```

> ⚠️ Always pass `method="function_calling"`. The `langchain-litellm` default (`json_schema`)
> sends a strict `response_format` — OpenAI requires every field to be listed in `required`,
> so any model with optional fields gets a 400. This failed in production; do not drop the parameter.

**13 guards** (triggers described in `prompts/router.py`, response content in `router/guards.py`):

| GuardId | What it blocks |
|---|---|
| `pii` | Requests to display/transform personal data (passwords, card numbers, ID numbers...) |
| `privacy_contact` | Asking for a staff member's/manager's personal phone number |
| `regional_cheapest` | "Cheapest store in <region>" — cannot be answered with one store |
| `unsupported_brand` | Questions about unsupported brands (Kumho, Nexen, Dunlop...) |
| `external_price` | Requests to compare prices with Danawa/Naver/Google |
| `past_event_page` | Viewing ended events |
| `coupon_issue_request` | Asking the bot to issue a coupon directly |
| `expired_coupon_or_event` | Asking to restore expired coupons/event benefits |
| `nonexistent_benefit` | Claiming non-existent benefits (VIP/black card/50%...) |
| `reservation_date_range` | Reservation date in the past or >30 days out (text computes dates with `datetime`) |
| `vehicle_type_compatibility` | Asking to fit sedan tires on an SUV |
| `pickup_status` | Asking about a running pickup's location/progress |
| `pickup_info` | Asking what Smart Pickup is / how to sign up |

Guard text is **pure data** (Korean, ported verbatim from V2). To add a guard: add the enum in `schemas.py`, describe the trigger in `prompts/router.py`, add text+chips in `guards.py`. No logic code.

### 4.2. Slots (`slots/`)

- **Extraction**: the LLM fills `SlotsPatch` inside the router call itself (tire_size, car_no, region, date/time, goal_type...).
- **Merge**: reuses V2's `ConversationSlots.merge()` — dependency resets included (changing cars resets the old size...).
- **Persistence**: reuses `ChatHistoryService.get_slots/save_slots_async` (Redis, encrypted) — same place V2 stores them.
- Fields the LLM fills with out-of-vocabulary values (unknown goal_type...) are dropped via Pydantic ValidationError; the turn survives.
- **Label backfill** (`slots/enrich.py`): after tool harvesting, if `goods_no` is set but no product label
  (`tire_model`/`pending_product_name`), the label is resolved from the product-detail endpoint. Order cards never
  render the internal goods_no code — `OrderInfo.product` is optional and a missing label renders as "—" in the FE.
- Current slots are injected into the system prompt as a `## CONVERSATION SLOTS` block so the LLM keeps context.

### 4.3. Tools + Executor

- `tools_for_domain(domain)`: LEADING → `[]` (pure chat), DISCOVERY → 20, TRANSACTION → 24, SUPPORT → 8.
- Tools are **re-exported** from the V2 agents, never rewritten — any fix to V2 tools applies to V3 automatically.
- `ToolLoopExecutor`: bind tools → select with `AI_MODEL_TOOL_SELECTOR` → validate against the bound tool set,
  runtime guard, and tool input schema → execute. A rejected selection is retried once with `AI_MODEL_FALLBACK`.
  After tool execution, `AI_MODEL_COMPOSER` produces the grounded answer. Max **4 rounds**, then a forced
  no-tools final answer.
- **3 write tools** (`quick_order_tool`, `save_to_cart_tool`, `issue_coupon_tool`): the `TRANSACTION_WRITE_GUIDANCE` prompt requires the LLM to summarize the order and get explicit confirmation before calling them.
- Note: the service calls `set_tstation_be_token()` before the executor — tools need the BE token.

### 4.4. Rich templates (`templates.py`)

Whatever tool ran determines what card can be rendered (data availability, not routing):

| FE template | Source tools |
|---|---|
| `product` | search_product, recommendations, best_selling, newest, benefit/event/coupon products... |
| `location` | search_stores, nearby_stores, store_list, stores_with_time_filter... |
| `listCar` | get_user_vehicles, get_my_cars |

The mini model reads raw tool output → fills the Pydantic model from **`agents/templates/schemas.py`** (the FE's single source of truth — V3 never redefines schemas). Build failure / no data → fallback to `quickReply`. When a rich template is emitted, the composer chips call is **skipped** (like V2: cards carry no chips).

### 4.5. SSE contract (`sse.py`)

| Event | When | Consumer |
|---|---|---|
| `status` `"생각 중..."` | turn start | FE spinner |
| `status` `tool_start` (+`tool`, `display_name`) | before each tool | FE progress |
| `token` | each answer chunk | FE text rendering |
| `tool` | after each tool | FE debug panel |
| `agent_flow` | start/success/error | FE progress |
| `message` | full answer | **API layer saves history** |
| `data` | final template payload | FE renders card/chips; API layer captures `assistantResponse` |
| `qc_correction` | QC corrected the answer | API layer overrides history |
| `DONE` + `data: [DONE]` | end | FE closes the stream |

### 4.6. Degrade matrix

| Failure point | Behavior |
|---|---|
| Router call | Pure chat, domain=LEADING, no tools — still answers |
| Redis (slots) | Empty slots / not saved — the turn still runs |
| A tool | `Tool error: ...` is handed back to the LLM to handle in its answer |
| QC | Original answer kept |
| Template builder | Falls back to quickReply |
| Composer (chips) | `quickReplies: []` |
| Any other exception | `_run_turn_safe` catches it → ERROR_RESPONSE + DONE; the stream never hangs |

---

## 5. Usage

### Enable/disable

```bash
# .env
AI_CHAT_V3_PURE_LLM_ENABLED=true    # false → V2 runs as before
```

No FE/endpoint changes needed — still `POST /chat`. The branch point is at the top of `TStationChatServiceV2.chat()`.

### Relevant env vars

| Var | Used for |
|---|---|
| `AI_MODEL` | Backward-compatible main model when a V3-specific model is unset |
| `AI_MODEL_TOOL_SELECTOR` | V3 fast tool-selection model; falls back to `AI_MODEL` when empty |
| `AI_MODEL_COMPOSER` | V3 fast grounded-answer model; falls back to `AI_MODEL` when empty |
| `AI_MODEL_FALLBACK` | V3 stronger retry after contract or deterministic-QC failure |
| `AI_MODEL_MINI` | Router / chips / QC / template builder |
| `AI_QC_ENABLED` | Enables fact-checking (+1 call per tool-using turn) |
| `AI_GATEWAY_BASE_URL`, `AI_GATEWAY_API_KEY`, `AI_DEFAULT_PROVIDER` | LiteLLM gateway |

### Direct invocation (test/debug)

```python
from schemas.tstation.chat import TStationChatRequest
from services.tstation.chat_v3 import chat

request = TStationChatRequest(
    messages=[{"role": "user", "content": "타이어 추천해줘"}],
    stream=True,                      # False → TStationChatResponse(content=...)
    user_id="u1", session_id="s1",
    access_token="<jwt>",             # needed for tools to call the BE
)
response = await chat(request)        # StreamingResponse (SSE)
```

### Extending

- **Add a guard**: enum (`router/schemas.py`) → trigger text (`prompts/router.py`) → text+chips (`router/guards.py`).
- **Add a tool**: import it in `tools/<domain>.py`, append to the list. Done.
- **Add a rich template**: add an entry to `_TOOL_TEMPLATES` (`templates.py`) pointing to a model in `agents/templates/schemas.py`.
- **Change persona/behavior rules**: edit `prompts/persona.py` only.

---

## 6. Quality gates (mandatory when touching this package)

```bash
# 1. Zero-regex — must return nothing
grep -rn "import re\b|re\.compile|re\.search|re\.match|re\.sub" app/tstation-ai/services/tstation/chat_v3/

# 2. No file ≥ 200 lines
find app/tstation-ai/services/tstation/chat_v3 -name "*.py" -exec wc -l {} + | sort -rn | head -3

# 3. Lint
just lint
```

- **Never import from `chat.py`** — allowed imports only: `agents/*/tools.py`, `agents/templates/schemas.py`, `agents/base_agent.py` (TOOL_DISPLAY_NAMES), `schemas/tstation/*`, `chat_history_service`, `common/*`, `config`.
- Mocked E2E tests (5 scenarios: pure chat / guard / router-fail degrade / template builder / rich event): see the session-scratchpad test script, or rewrite following the pattern of patching `route_request` + `GenericFakeChatModel`.

## 7. Not done yet (see the MIGRATE doc)

- Transactional templates: `datepick`, `preOrder`, `orderComplete`, `voucher`, `previewYoutube`, `qnaComplete`.
- Korean sample-sentence router test set running in CI.
- Langfuse spans (currently only per-stage latency logs).
- Reuse of `llm_first/schedule_validation.py` for booking flows.
