# Eval — LLM-as-Judge Faithfulness Benchmark

Benchmark framework to evaluate **faithfulness**, **latency**, and **consistency** across LLM models for `tstation-ai`.

**Faithfulness** = chatbot response does not hallucinate relative to actual tool output (grounded in live API evidence, not training data).

---

## How it works

```text
test_cases_from_excel.json
        ↓ single-turn user messages
  tstation-ai chatbot  (live SSE API call)
        ↓ tool_evidence + template_events + timing
  Judge LLM  (AI Gateway)
        ↓ faithfulness score 0.0–1.0
  results/benchmark_<model>.json   ← one file per model
        ↓
  python eval/summarize_results.py
        ↓
  results/benchmark_summary.json   ← aggregate across all models
```

Only **discovery_agent** and **transaction_agent** responses count toward scores.
Multi-turn test cases are automatically skipped (single-turn only).

---

## Setup

**1. Set env vars in `docker/.env`:**

```env
EVAL_JWT_TOKEN=your_jwt_token_here     # JWT to call chatbot API
AI_GATEWAY_API_KEY=sk-xxxx             # Judge LLM API key
HTTPS_PORT=8001                        # nginx HTTPS port (default 8001)
```

**2. Start the stack:**

```powershell
just start
```

---

## Run — single model

```powershell
python eval/run_eval.py --model-endpoint gpt-4.1=https://localhost:8001/api --limit 20
```

| Flag | Default | Description |
| --- | --- | --- |
| `--model-endpoint model=url` | reads `AI_MODEL` + `EVAL_API_URL` from env | Model label and API URL |
| `--limit N` | `5` | Max test cases (`0` = all) |
| `--agents AGENT [...]` | `discovery_agent transaction_agent` | Only run cases for these agents. Pass `all` to disable filter. |
| `--skip-all-fail` / `--no-skip-all-fail` | on | Skip TCs that fail faithfulness in every existing result file (systemic failures) |
| `--skip-all-fallback` / `--no-skip-all-fallback` | off | Skip TCs where every existing run got `template_eval=FALLBACK` (single-turn not completable). Run baseline first, then enable. |
| `--tag TAG` | _(none)_ | Tag for re-runs — saves to `benchmark_<model>_<tag>.json` |
| `--judge-api-url URL` | `http://localhost:4000/v1` | Judge LLM base URL |
| `--judge-api-key KEY` | `AI_GATEWAY_API_KEY` env | Judge LLM API key |
| `--test-cases-file PATH` | `eval/test_cases_from_excel.json` | Custom test cases file |

---

## Recommended workflow — baseline then focused re-run

Because ~85% of single-turn TCs result in `template_eval=FALLBACK` (bot asks for clarification
instead of completing), most TCs do not differentiate models. This two-step workflow filters them out:

```powershell
# Step 1 — Baseline: run ALL TCs on one representative model (no filters)
python eval/run_eval.py \
  --model-endpoint gpt-5.5-reasoning-low=https://localhost:8001/api \
  --limit 0 \
  --no-skip-all-fail

# Step 2 — Focused: run other models, skipping TCs that were always FALLBACK in Step 1
python eval/run_eval_all.py \
  --models gpt-4.1 gpt-4.1-mini gpt-5.1 \
  --limit 0 \
  --skip-all-fallback
```

After Step 1, `--skip-all-fallback` automatically reads the baseline result file and removes TCs
where the bot could never complete in a single turn. The remaining TCs are the ones where models
can meaningfully diverge.

**Resume:** if interrupted, re-run the same command — already-completed TCs are skipped.
To restart from scratch, delete `results/benchmark_<model>.json`.

---

## Run — multiple models (batch)

Automatically restarts `tstation-ai` with the correct model between runs.

```powershell
python eval/run_eval_all.py --models gpt-4.1 gpt-4.1-mini gpt-5.1 --limit 20
```

All flags from `run_eval.py` apply, plus:

| Flag | Default | Description |
| --- | --- | --- |
| `--all` | — | Run all models defined in `ALL_MODELS` list |
| `--no-restart` | — | Skip docker compose restart (service already running) |
| `--service-name NAME` | `tstation-ai` | Docker compose service to restart |
| `--health-timeout N` | `60` | Seconds to wait for service health after restart |

**Resume:** if interrupted, re-run the same command — already-completed TCs are skipped automatically.
To restart from scratch, delete `results/benchmark_<model>.json`.

---

## Generate summary

Run after one or more benchmark files exist:

```powershell
python eval/summarize_results.py --output eval/results/benchmark_summary.json
```

Prints a ranked table to stdout and writes the JSON summary file.

---

## Compare models (cross-model analysis)

```powershell
python eval/summarize_results.py --compare
python eval/summarize_results.py --compare --models gpt-4.1 gpt-4.1-mini gpt-5.1
```

Groups TCs into three sections:

| Section | Meaning |
| --- | --- |
| **ALL PASS** | Every model answered correctly — reliable cases |
| **ALL FAIL** | Every model failed — systemic prompt/tool gap, not model-specific |
| **DIVERGENT** | Models disagree — key target for model selection analysis |

---

## Consistency check (re-run comparison)

Run the same test cases a second time with `--tag r2`, then compare verdict stability:

```powershell
# Step 1 — baseline already done:
#   results/benchmark_gpt-4.1.json

# Step 2 — re-run with tag:
python eval/run_eval_all.py --models gpt-4.1 gpt-5.1 --limit 20 --tag r2
#   → results/benchmark_gpt-4.1_r2.json

# Step 3 — compare:
python eval/summarize_results.py --consistency --tag r2
python eval/summarize_results.py --consistency --tag r2 --models gpt-4.1
```

| Verdict | Meaning |
| --- | --- |
| **Stable PASS** | Both runs PASS — model is reliable on this TC |
| **Stable FAIL** | Both runs FAIL — systemic issue, not random |
| **Flipped** | PASS ↔ FAIL between runs — hallucination or judge inconsistency, needs review |

---

## Output format

### Per-model result file — `results/benchmark_<model>.json`

Array of records, one per test case:

```json
{
  "tc_id": "TC-001",
  "category": "product_compatibility",
  "description": "차량번호로 규격 자동조회",
  "model": "gpt-4.1",
  "run_tag": "",
  "actual_agent": "discovery_agent",
  "user_message": "내 차 번호가 99구9999인데 맞는 타이어 뭐야?",
  "tool_evidence": [
    {
      "tool_name": "get_my_cars_tool",
      "tool_input": { "license_plate": "99구9999" },
      "tool_output": "...",
      "source_domain": "vehicle"
    }
  ],
  "template_events": [
    { "type": "data", "template": "listCar", "data": { ... } }
  ],
  "timing": {
    "total_s": 8.47,
    "routing_s": 2.30,
    "thinking_s": 2.60,
    "tool_calls": [{ "tool": "get_my_cars_tool", "duration_s": 0.27 }],
    "tool_total_s": 0.27,
    "response_s": 2.31
  },
  "faithfulness_eval": {
    "faithfulness": 1.0,
    "verdict": "PASS",
    "reason": "The response only lists the registered car details..."
  },
  "template_eval": {
    "verdict": "FALLBACK",
    "expected": ["product"],
    "actual": ["listCar"],
    "reason": "Bot returned 'listCar' (clarification) instead of completing with ['product']"
  },
  "grounding_eval": {
    "verdict": "PASS",
    "reason": "All structured templates are backed by tool evidence",
    "called_tools": ["get_my_cars_tool"]
  }
}
```

### Timing segments

All segments measured directly from SSE event arrival times:

| Field | What it measures |
| --- | --- |
| `total_s` | Request start → `[DONE]` marker |
| `routing_s` | Request start → sub-agent start (coordinator dispatch overhead) |
| `thinking_s` | Sub-agent start → first `tool_start` event (LLM decision time) |
| `tool_total_s` | Earliest tool start → latest tool result (wall time across all tools) |
| `response_s` | Last tool result → first `data` template event (post-tool LLM reasoning) |

### Template eval verdicts

| Verdict | Meaning |
| --- | --- |
| `PASS` | Bot emitted the expected template type |
| `FALLBACK` | Bot asked for clarification (`listCar`/`quickReply`) instead of completing — correct multi-turn behavior, but eval is single-turn |
| `FAIL` | Bot emitted a wrong structured template |

> FALLBACK (~85%) is expected and normal — production is multi-turn but eval sends only the first message.

### Grounding eval verdicts

| Verdict | Meaning |
| --- | --- |
| `PASS` | Every structured template is backed by a matching tool call |
| `FAIL` | Structured template emitted with no supporting tool call (hallucination) |
| `SKIP` | Only exempt templates returned (`quickReply`, `qnaComplete`) — no factual data to ground |

---

## Summary file — `results/benchmark_summary.json`

```json
{
  "results_dir": "...",
  "total_models": 4,
  "models": [
    {
      "model": "gpt-4.1-mini",
      "summary": {
        "total_count": 20,
        "included_count": 20,
        "excluded_count": 0,
        "scored_count": 20,
        "pass_count": 18,
        "fail_count": 2,
        "avg_faithfulness": 0.894,
        "avg_faithfulness_bin": 0.9,
        "pass_rate_pct": 90.0,
        "avg_latency_s": 11.74,
        "latency_p50_s": 12.33,
        "latency_p90_s": 17.73,
        "avg_routing_s": 3.71,
        "avg_thinking_s": 3.75,
        "avg_tool_total_s": 0.34,
        "avg_response_s": 3.06,
        "pass_tc_ids": ["TC-001", "TC-003", "..."],
        "fail_tc_ids": ["TC-002", "TC-014"],
        "excluded_tc_ids": []
      }
    }
  ]
}
```

**Two faithfulness metrics:**
- `avg_faithfulness` — mean of raw float scores (0–1); reflects *degree* of faithfulness per response
- `avg_faithfulness_bin` — mean of binary scores (PASS=1, FAIL=0); equals `pass_rate_pct / 100`

`excluded_count` = records where the actual responding agent was not `discovery_agent` or `transaction_agent` (e.g. `leading_agent`); these are excluded from all metrics.

---

## Scoring

Judge LLM (`JUDGE_MODEL`, default `gpt-5.5-reasoning-xhigh`) returns a faithfulness float `0.0–1.0`:

| Raw score | Verdict |
| --- | --- |
| `> 0.5` | PASS |
| `<= 0.5` | FAIL |

- `1.0` = fully faithful to tool evidence
- `0.0` = severe hallucination or wrong facts asserted without tool backing
