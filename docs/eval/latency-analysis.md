# Latency Analysis — T-Station AI

Filters applied to both datasets: scored agents only (`discovery_agent` + `transaction_agent`), records with at least 1 tool call, outliers removed (mean + 2×std on `total_s`).

| Dataset | Source | Model(s) | Records after filter |
|---------|--------|----------|----------------------|
| **Baseline** | `benchmark_baseline.json` | gpt-5.5-reasoning-low | 37 |
| **v2 (r2)** | `benchmark_*_r2.json` | top 10 models combined | 120 |

---

## 1. What does a request go through?

```
 Request in
      │
      ▼
 ┌─────────────┐
 │   ROUTING   │  ← coordinator: auth, session load, dispatch agent
 └─────────────┘    NOT an LLM — pure infrastructure
      │
      ▼
 ┌─────────────┐
 │   THINKING  │  ← LLM reads system prompt + tool schemas, decides which tool to call
 └─────────────┘    1 LLM call
      │
      ▼
 ┌─────────────┐
 │  TOOL CALL  │  ← calls backend API (Oracle), fetches data
 └─────────────┘    sequential tools: LLM must finish processing before calling the next tool
      │
      ▼
 ┌─────────────┐
 │   RESPONSE  │  ← LLM reads tool results, generates FE template
 └─────────────┘    another LLM call
      │
      ▼
 Response out
```

**Unaccounted (~20%):** When multiple tools are called sequentially, the time the LLM spends deciding the next tool call falls in the gap between `tool_total` spans and is not captured separately.

---

## 2. Phase breakdown — baseline vs v2

| Phase | Baseline avg | Baseline p50 | Baseline p95 | Baseline p99 |
|-------|--------------|--------------|--------------|--------------|
| **total** | 13.53s | 13.22s | 17.79s | 18.83s |
| routing | 2.84s | 2.69s | 4.00s | 5.35s |
| thinking | 3.53s | 3.16s | 5.47s | 5.75s |
| tool_total | 1.18s | 0.40s | 3.66s | 4.53s |
| response | 3.28s | 3.09s | 5.01s | 5.40s |

| Phase | v2 avg | v2 p50 | v2 p95 | v2 p99 | Δ avg |
|-------|--------|--------|--------|--------|-------|
| **total** | 11.55s | 11.67s | 14.90s | 15.66s | **−2.0s** |
| routing | 2.27s | 2.10s | 3.50s | 5.02s | −0.6s |
| thinking | 3.13s | 2.86s | 4.95s | 6.88s | −0.4s |
| tool_total | 1.62s | 0.66s | 4.43s | 4.66s | +0.4s |
| response | 3.35s | 3.43s | 5.23s | 5.92s | ≈ 0 |

---

## 3. Comparative analysis

### Response phase unchanged (3.28s vs 3.35s)

This is the most important finding: **a better model does not make the response phase faster**. v2 uses top models but response still sits at ~3.3–3.4s — the same as baseline. The cause is not the model but **context size**: the LLM must read the full raw JSON from Oracle (many redundant fields) before rendering the template.

→ Optimizing response requires **trimming tool output** before feeding it to the LLM, not swapping models.

### Thinking is 0.4s faster in v2

Top models (v2) decide on tool calls 0.4s faster on average. However, v2's p99 (6.88s) is higher than baseline (5.75s) — some complex TCs make the model "think" longer.

### Routing is 0.6s faster in v2 — unrelated to model

Routing involves no LLM, yet v2 is still 0.6s faster. Most likely due to different run times (server load), not the model. This should not be interpreted as a routing improvement.

### Tool_total higher in v2 (+0.4s avg)

v2 ran more complex TCs (67 TCs vs 35 TCs), with more cases making multiple tool calls, resulting in longer wall time. p95/p99 are comparable.

---

## 4. Per-tool latency

| Tool | Baseline n | Baseline avg | Baseline p99 | v2 n | v2 avg | v2 p99 |
|------|------------|--------------|--------------|------|--------|--------|
| `get_my_cars_tool` | 20 | 0.44s | 1.45s | 9 | 0.26s | 0.27s |
| `get_orders_of_user_tool` | 8 | 0.62s | 0.73s | 71 | 0.56s | 1.39s |
| `get_final_price_tool` | 5 | 0.54s | 0.57s | 40 | 0.38s | 0.44s |
| `get_store_list_tool` | 4 | 0.37s | 0.48s | 16 | 0.21s | 0.43s |
| `get_order_status_tool` | 7 | 0.29s | 0.33s | 42 | 0.27s | 0.35s |
| `get_available_coupons_tool` | 1 | 0.32s | — | 9 | 0.49s | 2.30s |

`get_my_cars_tool` is significantly faster in v2 (0.26s vs 0.44s) — likely due to different run times or different TCs; needs further investigation.

`get_available_coupons_tool` in v2 has p99=2.30s (n=9, small sample) — high variance, worth monitoring.

---

## 5. Optimization priorities

| # | Issue | Impact | Baseline | v2 | Approach |
|---|-------|--------|----------|-----|----------|
| **1** | Response phase unchanged despite better model | **Every request with tools** | 3.28s | 3.35s | Trim tool output before feeding to LLM — keep only required fields |
| **2** | Thinking accounts for 26% of total time | **Every request** | 3.53s | 3.13s | Shorten system prompt; reduce tool schema count; split agents smaller |
| **3** | Routing ~2.3–2.8s, tail p99 > 5s | **Every request** | 2.84s | 2.27s | Profile coordinator for bottlenecks: session init, Qdrant warmup, agent loading |
| **4** | Tool_total tail (p95 ~3.7–4.4s) | Tool-heavy requests | p95=3.66s | p95=4.43s | Batch or parallelize multi-tool calls |
| **5** | `get_available_coupons_tool` p99=2.30s | Coupon-related TCs | — | 2.30s | Cache or optimize query; needs more samples to confirm |

**Priority order:** #1 and #2 first — both affect every request and can be improved with code changes alone (no infra required). #3 requires profiling on real server. #4 and #5 only improve tail latency.

**Expected gain from #1 + #2:** Cut 2–4s from avg total, bringing p50 from ~11–13s down to ~8–10s.
