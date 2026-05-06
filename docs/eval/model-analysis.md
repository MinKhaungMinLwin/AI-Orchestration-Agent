# T-Station AI — Model Benchmark Analysis

- **Date:** 2026-05-03
- **v1 (Baseline):** 45 models × 35 TCs — selects top 10 for v2
- **v2 (r2):** Top 10 models × 67 TCs
- **Scripts:** `python eval/summarize_results.py --v1` · `python eval/summarize_results.py --consistency --tag r2`

---

## 1. Glossary

| Term | Meaning |
|---|---|
| **Faith** | Faithfulness score 0.0–1.0. Higher = more accurate. 1.0 = perfect, 0.0 = hallucination |
| **Pass%** | % of answers with Faith > 0.5 |
| **Incl** | Number of scored records per model (only `discovery_agent` and `transaction_agent` count) |
| **p50 / p90 / p95 / p99** | Latency percentiles. p99 = the slowest 1% of requests |

All metrics are **clean** — slow outlier test cases removed before measurement.

---

## 2. Version 1 — Baseline (45 models)

Tested 45 models on 35 test cases. Goal: pick the top 10 for deeper testing in v2.
Ranked by Pass% then Faith.

| # | Model | Incl | Pass% | Faith | Avg | p50 | p90 | p95 | p99 |
|---|-------|:----:|------:|------:|----:|----:|----:|----:|----:|
| 1 | `gpt-5.0-reasoning-minimal` ★ | 13 | 92.3% | 0.856 | 8.46s | 8.56s | 10.67s | 11.01s | 11.01s |
| 2 | `o4-mini-low` ★ | 13 | 92.3% | 0.852 | 8.45s | 7.99s | 10.84s | 11.58s | 11.58s |
| 3 | `o1-mini` ★ | 12 | 91.7% | 0.873 | 10.02s | 8.98s | 12.44s | 19.04s | 19.04s |
| 4 | `gpt-5.2` ★ | 12 | 91.7% | 0.848 | 8.47s | 7.37s | 12.86s | 12.88s | 12.88s |
| 5 | `gpt-5.0-reasoning-high` ★ | 12 | 91.7% | 0.839 | 9.13s | 9.60s | 11.30s | 12.77s | 12.77s |
| 6 | `o1-low` | 11 | 90.9% | 0.877 | 10.34s | 9.37s | 16.15s | 18.63s | 18.63s |
| 7 | `o1-medium` ★ | 11 | 90.9% | 0.841 | 9.31s | 9.17s | 10.21s | 12.54s | 12.54s |
| 8 | `gpt-5.2-reasoning` | 9 | 88.9% | 0.789 | 7.84s | 7.66s | 9.73s | 9.73s | 9.73s |
| 9 | `o1-high` | 9 | 88.9% | 0.789 | 8.93s | 8.75s | 11.77s | 11.77s | 11.77s |
| 10 | `gpt-5.5-reasoning` ★ | 14 | 85.7% | 0.829 | 7.98s | 8.07s | 10.63s | 11.40s | 11.40s |
| 11 | `o4-mini-medium` ★ | 14 | 85.7% | 0.825 | 7.41s | 6.63s | 10.21s | 11.56s | 11.56s |
| 12 | `gpt-5.1-reasoning` ★ | 14 | 85.7% | 0.821 | 8.75s | 8.74s | 11.20s | 11.29s | 11.29s |
| 13 | `gpt-5.4-reasoning-low` | 13 | 84.6% | 0.804 | 8.24s | 8.00s | 10.14s | 11.01s | 11.01s |
| 14 | `gpt-5.2-reasoning-minimal` | 13 | 84.6% | 0.798 | 9.22s | 8.40s | 12.96s | 13.32s | 13.32s |
| 15 | `gpt-5.2-reasoning-low` ★ | 11 | 81.8% | 0.855 | 7.68s | 7.16s | 9.45s | 12.39s | 12.39s |
| 16 | `gpt-5.1-reasoning-low` | 11 | 81.8% | 0.809 | 9.22s | 9.66s | 10.87s | 11.66s | 11.66s |
| 17 | `gpt-5.1-reasoning-high` | 11 | 81.8% | 0.775 | 8.39s | 7.96s | 9.32s | 13.83s | 13.83s |
| 18 | `gpt-5.5` | 16 | 81.2% | 0.823 | 8.14s | 8.12s | 10.65s | 14.42s | 14.42s |
| 19 | `o3-high` | 16 | 81.2% | 0.794 | 8.22s | 8.36s | 9.42s | 11.90s | 11.90s |
| 20 | `gpt-5.4` | 15 | 80.0% | 0.791 | 9.78s | 10.50s | 12.57s | 14.65s | 14.65s |
| 21 | `gpt-5.5-reasoning-high` | 15 | 80.0% | 0.787 | 7.99s | 7.50s | 11.19s | 12.32s | 12.32s |
| 22 | `gpt-5.0` | 14 | 78.6% | 0.782 | 8.63s | 7.48s | 13.31s | 13.34s | 13.34s |
| 23 | `o1-preview` | 14 | 78.6% | 0.768 | 11.80s | 11.76s | 17.43s | 17.44s | 17.44s |
| 24 | `gpt-4.1` | 14 | 78.6% | 0.764 | 11.18s | 10.64s | 14.98s | 16.80s | 16.80s |
| 25 | `o3-mini-high` | 13 | 76.9% | 0.785 | 8.36s | 8.22s | 9.83s | 10.37s | 10.37s |
| 26 | `gpt-5.0-reasoning-low` | 13 | 76.9% | 0.775 | 8.57s | 7.73s | 10.87s | 11.50s | 11.50s |
| 27 | `gpt-5.5-reasoning-xhigh` | 13 | 76.9% | 0.775 | 9.92s | 8.34s | 16.37s | 17.39s | 17.39s |
| 28 | `o3-medium` | 13 | 76.9% | 0.762 | 8.21s | 8.55s | 9.31s | 10.58s | 10.58s |
| 29 | `o3-mini-low` | 12 | 75.0% | 0.779 | 10.13s | 10.57s | 13.53s | 16.51s | 16.51s |
| 30 | `gpt-5.5-reasoning-none` | 15 | 73.3% | 0.743 | 8.05s | 7.78s | 9.65s | 12.41s | 12.41s |
| 31 | `gpt-5.4-reasoning` | 11 | 72.7% | 0.809 | 9.43s | 8.77s | 12.29s | 14.80s | 14.80s |
| 32 | `gpt-5.2-reasoning-high` | 11 | 72.7% | 0.745 | 10.26s | 9.43s | 11.65s | 16.93s | 16.93s |
| 33 | `gpt-4.5` | 14 | 71.4% | 0.755 | 10.43s | 10.20s | 11.93s | 16.05s | 16.05s |
| 34 | `gpt-4o-mini` | 14 | 71.4% | 0.725 | 10.63s | 10.29s | 13.92s | 15.59s | 15.59s |
| 35 | `o3-low` | 14 | 71.4% | 0.721 | 8.58s | 9.21s | 10.25s | 10.94s | 10.94s |
| 36 | `gpt-5.4-reasoning-high` | 10 | 70.0% | 0.740 | 8.05s | 7.71s | 10.51s | 10.51s | 10.51s |
| 37 | `gpt-4o` | 10 | 70.0% | 0.698 | 10.71s | 11.10s | 15.20s | 15.20s | 15.20s |
| 38 | `gpt-5.5-reasoning-low` | 13 | 69.2% | 0.738 | 10.00s | 9.91s | 13.17s | 15.11s | 15.11s |
| 39 | `o3-mini-medium` | 13 | 69.2% | 0.738 | 9.10s | 8.32s | 14.02s | 14.17s | 14.17s |
| 40 | `gpt-5.1` | 13 | 69.2% | 0.727 | 8.79s | 8.61s | 10.97s | 11.50s | 11.50s |
| 41 | `gpt-5.4-reasoning-minimal` | 13 | 69.2% | 0.719 | 9.11s | 8.74s | 12.18s | 15.87s | 15.87s |
| 42 | `gpt-5.1-reasoning-minimal` | 16 | 68.8% | 0.738 | 9.10s | 8.77s | 14.28s | 14.44s | 14.44s |
| 43 | `gpt-4.1-mini` | 12 | 66.7% | 0.723 | 10.53s | 9.37s | 12.82s | 16.71s | 16.71s |
| 44 | `gpt-5.0-reasoning` | 12 | 66.7% | 0.713 | 8.39s | 8.20s | 9.94s | 9.95s | 9.95s |
| 45 | `o4-mini-high` | 12 | 66.7% | 0.696 | 8.11s | 8.45s | 10.03s | 11.68s | 11.68s |

★ = selected for v2 (r2) run

**Key findings:**

- More reasoning is not always better: `o4-mini-high` ranks last (66.7%) while `o4-mini-low` ranks 2nd (92.3%). Heavy reasoning hurts tool-grounding tasks.
- Newer models are not always better: `gpt-5.5` (Faith 0.823) scores lower than `gpt-5.2` (Faith 0.848). gpt-5.5 is tuned for writing, not for tool accuracy.
- Do not use: `o4-mini-high`, `gpt-5.0-reasoning`, `gpt-4.1-mini`, `gpt-4o` — all below 70% Pass%.

---

## 3. Version 2 — r2 (top 10 models, 67 TCs)

Tested the top 10 models from v1 on a larger set of 67 test cases.
Only records that called at least one tool are included. Outlier TCs removed (threshold 17.01s = mean+2std, removed TC-098, TC-124, TC-129).

**Key finding: all 10 models achieve 100% Pass% on tool-call records.** Quality failures in v1/v2 full metrics came entirely from no-tool responses (model answered from general knowledge without retrieving data). When the model does call a tool, all models are accurate.

Ranked by avg latency (lower = better).

| # | Model | N | Faith | Avg | p50 | p90 | p95 | p99 |
|---|-------|---|-------|-----|-----|-----|-----|-----|
| **1** | `o1-medium` | 13 | 0.950 | **10.58s** | **10.53s** | **12.67s** | 13.14s | 13.58s |
| **2** | `gpt-5.2-reasoning-low` | 9 | **0.961** | 10.75s | 11.25s | 13.17s | 13.80s | 14.30s |
| **3** | `gpt-5.1-reasoning` | 10 | 0.960 | 11.24s | 11.81s | **13.02s** | **13.42s** | **13.75s** |
| **4** | `gpt-5.0-reasoning-high` | 9 | 0.928 | 11.26s | 11.29s | 13.59s | 13.64s | 13.69s |
| **5** | `o4-mini-low` | 11 | 0.941 | 11.30s | 11.51s | 14.28s | 14.32s | 14.35s |
| 6 | `gpt-5.2` | 11 | 0.950 | 11.36s | 11.67s | 13.65s | 14.28s | 14.78s |
| 7 | `o1-mini` | 8 | 0.937 | 11.66s | 11.88s | 14.60s | 15.15s | 15.58s |
| 8 | `gpt-5.0-reasoning-minimal` | 11 | 0.950 | 11.74s | 12.31s | 14.91s | 15.76s | 16.44s |
| 9 | `gpt-5.5-reasoning` | 9 | 0.944 | 12.04s | 11.66s | 14.26s | 14.50s | 14.69s |
| 10 | `o4-mini-medium` | 10 | 0.931 | 12.58s | 12.47s | 15.14s | 15.17s | 15.19s |

**Top picks (tool-call latency):**

| Goal | Model | Faith | Avg | p99 |
| --- | --- | --- | --- | --- |
| Fastest | `o1-medium` | 0.950 | **10.58s** | **13.58s** |
| Best p99 | `gpt-5.1-reasoning` | 0.960 | 11.24s | **13.75s** |
| Best faith | `gpt-5.2-reasoning-low` | **0.961** | 10.75s | 14.30s |

**Notable rank changes from v1 to v2:**

| Model | v1 rank | v2 rank | Why |
|-------|---------|---------|-----|
| `o1-mini` | 3 | **7** | Slowest avg (11.66s) in tool-call cases |
| `o1-medium` | 7 | **1** | Fastest avg and p50 when tool calls happen |
| `gpt-5.1-reasoning` | 12 | **3** | Best p90/p95/p99 — most predictable tail |
| `o4-mini-medium` | 11 | **10** | Slowest overall (avg 12.58s) |
