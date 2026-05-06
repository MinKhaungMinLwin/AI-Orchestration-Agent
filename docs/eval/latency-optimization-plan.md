# Latency Optimization Plan — T-Station AI

Based on eval results: [results_gpt-5.5-reasoning-low-r1.csv](../../eval/results_gpt-5.5-reasoning-low-r1.csv) (80 test cases, gpt-5.5-reasoning-low).

Goal: cut total latency by **~50%** (P50 from ~11s → ~5-6s, P95 from ~18s → ~10s) **without hurting output quality**.

---

## 1. Current pipeline

```text
User message
    │
    ▼
┌──────────────────┐
│  classify_intent │  LLM call #1 (gpt-4o-mini, structured)         1-4s
│   (full / slim)  │  Picks 1 of 4 domains: discovery/transaction/...
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  extract_slots   │  Regex / light LLM                              <10ms
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Domain Agent    │  LLM call #2 (gpt-5.5-reasoning-low, stream)    5-15s
│  ┌────────────┐  │
│  │ llm_think  │  │  Read prompt + tools, decide which tool to call 1.5-7s
│  │   tools    │  │  Call backend API (Oracle DB)                   0.5-7s
│  │  llm_gen   │  │  Read tool result, write the reply              1.5-8s
│  └────────────┘  │
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  QC fact-check   │  LLM call #3 (gpt-4o-mini)                      0 / 5-8s
│  (conditional)   │  Compare reply against raw tool data
└──────────────────┘
    │
    ▼
┌──────────────────┐
│   Stream SSE     │  Token stream to client                         (overlap)
└──────────────────┘
```

**3 LLM calls + N tool calls** per request. Tools are pure API calls (no LLM-in-loop).

---

## 2. Hotspots from eval data

### 2.1. QC fact-check — bottleneck #1

| Metric | Value |
|--------|-------|
| Trigger rate | ~30% of test cases |
| Latency when it runs | 5-8s (median ~5.5s) |
| Latency when skipped | ~0s |

**Examples:**
- [tc_016](../../eval/results_gpt-5.5-reasoning-low-r1.csv) (`여름 타이어 세일 있어요?`): qc=7.798s / total=16.82s → **QC takes 46% of total time**
- [tc_045](../../eval/results_gpt-5.5-reasoning-low-r1.csv) (`한남점 매장 정보 알려줘`): qc=7.955s / total=18.751s → **42%**
- [tc_036](../../eval/results_gpt-5.5-reasoning-low-r1.csv): qc=7.287s / total=16.793s → **43%**

**Problem:** QC runs even when the reply has **no facts to check** (event lists, deal lists, plain FAQ text). The current `_has_factual_claims()` check is too loose.

### 2.2. Domain agent LLM — bottleneck #2

Takes **50-80%** of total latency. Average breakdown:

| Sub-step | Avg | Spike | Why it spikes |
|----------|-----|-------|---------------|
| `llm_think` | 2.5s | 7-8s | Big system prompt (250-300 lines) + 15 full tool docstrings |
| `tools` | 1.5s | 4-7s | Tools called one after another (search → final_price) |
| `llm_gen` | 3s | 8s | Long replies (store list, comparison) |

**Spike examples:**
- llm_think: tc_039 (7.31s), tc_057 (7.97s), tc_058 (7.22s), tc_066 (6.90s) — mostly transaction/support
- tools: tc_011 (7.33s — youtube tool), tc_002/tc_003/tc_019 (~4.5s — chained)
- llm_gen: tc_052/tc_054/tc_055 (~8s — long store lists)

**Problem:** The system prompt is sent in full on every request, but no prompt caching is used.

### 2.3. classify_intent — bottleneck #3

Two clear groups:
- **Slim variant** (~1.2s): tc_001, tc_003, tc_007, tc_009...
- **Full variant** (~3-4s): tc_002 (4.07s), tc_005 (4.30s), tc_006 (4.08s), tc_008 (4.16s), tc_010 (4.34s)

**Problem:** Using gpt-4o-mini structured output just to pick 1 of 4 classes is overkill. An embedding classifier can do it in <50ms with similar or better accuracy.

### 2.4. Multi-turn cases — quality problem, not latency

[tc_076-080](../../eval/results_gpt-5.5-reasoning-low-r1.csv): tools=0, faith=0.07-0.88. This is a quality bug — out of scope here, needs separate debugging.

---

## 3. Optimization roadmap

Sorted by **ROI = (impact × effort^-1)** from high to low.

### 🥇 P1 — Prompt caching across the pipeline

**Why first:** highest impact, lowest effort, zero quality risk.

**How it works.** Bedrock/Anthropic prompt caching marks the repeated prefix (system prompt + tool defs) with `cache_control: ephemeral`. Later requests skip prefill for the cached part → TTFT drops 50-85%.

The LiteLLM gateway passes `cache_control` markers through automatically, translating between OpenAI format and Bedrock native format.

**How to apply:**

| LLM call | Prefix to cache |
|----------|-----------------|
| `classify_multi_intent` | `prompt_router_multi()` (~440 lines) |
| `classify_multi_intent_slim` | `prompt_router_slim()` (~52 lines) |
| Discovery/Transaction/Support/Leading agents | `*_AGENT_SYSTEM_PROMPT_TEMPLATE` + tool definitions (~250-300 lines each) |
| `qc_agent` | `QC_SYSTEM_PROMPT` (~60 lines) |

Add a `cache_control: ephemeral` block at the end of each system message.

Verify cache hits with `cache_creation_input_tokens` / `cache_read_input_tokens` in Langfuse traces.

**Expected impact:**

| Step | Before | After (cache hit) | Drop |
|------|--------|-------------------|------|
| classify (full) | 3-4s | 1.2-1.6s | -60% |
| agent llm_think | 2.5s | 1.0s | -60% |
| qc | 5-8s | 2-3s | -60% |

**Total:** Saves **3-5s per request** on cache hits. Cache miss happens every 5 minutes (ephemeral TTL) or 1 hour (extended TTL on Claude 4.5+).

**Quality.** Zero impact — same model, same prompt, just skips prefill.

**Effort.** 1-2 days. Mostly wiring + verifying cache hit rate.

---

### 🥈 P2 — Skip-QC heuristics

**Why:** QC costs 5-8s but many turns don't need fact-checking.

**Suggested rules:**

```python
def should_run_qc(draft, tool_evidence, template) -> bool:
    # Rule 1: no tool was called → no new facts to check
    if not tool_evidence:
        return False

    # Rule 2: template is plain quick_reply text (events, deals, FAQ list)
    if template in {"quickReply"} and not _contains_numerical_facts(draft):
        return False

    # Rule 3: tool output is a deterministic mapping (e.g., listCar)
    deterministic_tools = {"get_my_cars_tool", "get_available_coupons_tool"}
    if all(t["tool_name"] in deterministic_tools for t in tool_evidence):
        return False

    # Rule 4: reply uses a code-based template (built from tool data, not from the LLM)
    if _used_code_based_mapper(template):
        return False

    return _has_factual_claims(draft)  # current logic as fallback
```

**Variant: Async QC (advanced).** Stream the reply first → run QC in parallel → log any mismatches to Langfuse for offline review. The user gets the reply right away instead of waiting 5-8s.

Tradeoff: if QC finds an error after streaming finishes, we can't fix it on the fly → only safe for low-risk turns.

**Expected impact:**

- Removes 5-8s on ~30-50% of turns that currently run QC
- Average total latency drops by **~2-3s**

**Quality.** ⚠️ Watch the `faith` score after rolling out. If it drops by more than 5%, tighten the rules.

**Effort.** 2-3 days + 1 week of monitoring.

---

### 🥉 P3 — Embedding-based classifier

**Why:** classify takes 1-4s for a task that just picks 1 of 4 classes.

**Approach:**

```text
User message
    │
    ▼
┌──────────────────┐
│  Sentence-BERT   │  multilingual model (Korean)                    <50ms
│  (in-process)    │  → embedding vector
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Cosine + Logit  │  classify 4 domains + confidence                 <5ms
└──────────────────┘
    │
    ▼
  confidence > 0.7?
    │       │
   Yes      No
    │       │
    ▼       ▼
  Use     Fall back
  result  to LLM classify
          (current path)
```

**Training data:**

- Existing test cases (~80 labels) as seed data
- Synthetic examples generated from current prompts (~500-1000 samples)
- Fine-tune a logistic regression head on top of the embeddings

**Expected impact:**

- Cache-hit path: 1.2-1.6s → ~50-100ms
- Saves **1-3s per request** on ~80% of requests (high-confidence path)

**Quality.** Need to benchmark against the current classifier. Embedding classifiers usually:

- Beat LLMs on multi-class label tasks (per arXiv 2504.04277)
- Have better-calibrated confidence scores

⚠️ Risk: misclassification on edge cases with mixed intent. Mitigation: use a confidence threshold + LLM fallback.

**Effort.** 3-5 days: data prep + training + integration + benchmark.

---

### P4 — Run classify and extract_slots in parallel

Use `asyncio.gather(classify_task, slot_task)` instead of running them one after another.

**Impact:** Saves 50-200ms (slots are usually <10ms but sometimes 30-40ms).

**Effort:** 1 day. Quality: zero risk.

---

### P5 — Parallel tool calls inside the agent

LangGraph's `ToolNode` runs tools in parallel when the LLM returns multiple tool calls in a single message.

**Today.** The agent calls tools one after another:

- tc_002 (`벤투스 타이어 찾아줘`): `search_product_tool` → `get_final_price_tool` → tools=4.57s
- tc_003: tools=4.64s
- tc_019: tools=4.37s

**How to apply:**

1. Update the system prompt: tell the LLM to call multiple tools in one message when they're independent

   ```text
   When you need to call multiple independent tools, call them in parallel
   in a single response — do NOT chain unless one tool's output is required
   for another's input.
   ```

2. Verify the state reducer: `Annotated[list, add]` so results merge correctly
3. Add a dependency graph if needed (e.g., search → final_price really is dependent)

**Expected impact.** tc_002/003/019 (~4.5s) → ~2.5s when independent. Saves ~2s on multi-tool turns.

**Quality.** Zero if dependencies are right. Risk: race conditions if the reducer is wrong.

**Effort.** 2-3 days + prompt tuning + eval.

---

### P6 — Bedrock latency-optimized inference

**How it works:** `performanceConfig.latency = "optimized"` runs on Trainium2 with optimized kernels. Reports show ~30-40% latency drop, zero quality impact.

**Requirements:**

- Model must support it: Claude 3.5 Haiku, Llama 3.1 70B/405B, Nova Pro
- Need to check: does gpt-5.5-reasoning route through Bedrock?

**Effort:** A few hours if supported. One config flag.

---

### P7 — Tune reasoning effort

We currently use `reasoning-low` everywhere. Analysis:

| Agent | Needs reasoning? | Suggestion |
|-------|------------------|------------|
| Discovery | Yes (compatibility, recommendations) | Keep `low` |
| Transaction | Yes (pricing, store filtering) | Keep `low` |
| Support FAQ | ❓ A/B test | Maybe disable |
| Leading (greeting/fallback) | No | Disable, switch to gpt-4o-mini |
| QC (already temp=0) | No | Already fine |
| Classify | No | Replace with embedding (P3) |

**Impact:** Saves 1-3s on Leading/Support paths.

**Effort:** 1 day + A/B eval.

---

## 4. Execution roadmap

| Week | Work | Latency target |
|------|------|----------------|
| **W1** | P1 (prompt caching) + P6 (Bedrock latency flag) | -30% to -40% |
| **W2** | P2 (skip-QC) + P4 (parallel classify/slots) | -2-3s avg |
| **W3** | P3 (embedding classifier) — POC + benchmark | -2s avg (80% of requests) |
| **W4** | P5 (parallel tools) + P7 (reasoning tune) + monitoring | -1-2s on edge cases |

### Acceptance criteria for each phase

- ✅ `faith` score doesn't drop by more than 2%
- ✅ `relevance` score doesn't drop by more than 2%
- ✅ `tools` score doesn't drop by more than 5%
- ✅ Latency target met on the test set
- ✅ Verified on Langfuse production traces

---

## 5. Targets

### Before optimization (r1 baseline)

| Percentile | Total latency |
|------------|---------------|
| P50 | ~11s |
| P90 | ~16s |
| P95 | ~18s |
| P99 | ~19s |

### After optimization (target)

| Percentile | Total latency | Δ |
|------------|---------------|---|
| P50 | ~5-6s | -45% |
| P90 | ~9s | -44% |
| P95 | ~10s | -45% |
| P99 | ~12s | -37% |

---

## 6. Side observations — no action needed yet

- **Tool latency tc_011 (`youtube_search`)**: 7.33s — hard to optimize if it's an external API; if internal, cache the video metadata.
- **`llm_gen` 7-8s on store lists (tc_052/054/055)**: replies are too verbose. Options:
  - Set a tighter `max_tokens` for store list replies
  - Use a code-based template instead of LLM rendering (cuts both latency and token cost)
- **Multi-turn failures (tc_076-080)**: tools=0, low faith → quality bug, not latency. Needs separate debugging.

---

## 7. References

- [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [AWS Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [LiteLLM Prompt Caching](https://docs.litellm.ai/docs/completion/prompt_caching)
- [Bedrock Latency-Optimized Inference](https://docs.aws.amazon.com/bedrock/latest/userguide/latency-optimized-inference.html)
- [LangGraph Parallel Tool Execution](https://medium.com/data-science-collective/running-parallel-tool-calls-in-langgraph-3aaa691f25cb)
- [Embedding vs LLM Classification (arXiv 2504.04277)](https://arxiv.org/html/2504.04277v1)
- [Trust or Escalate: Selective LLM Judges (ICLR 2025)](https://proceedings.iclr.cc/paper_files/paper/2025/file/08dabd5345b37fffcbe335bd578b15a0-Paper-Conference.pdf)
- [PASTE: Speculative Tool Execution (arXiv 2603.18897)](https://arxiv.org/abs/2603.18897)
