# Model Evaluation - LLM-as-Judge Faithfulness Benchmark

Benchmark framework to compare **faithfulness** and **latency** across different LLM models for `tstation-ai`.

**Faithfulness** = chatbot response does not hallucinate relative to actual tool output.

---

## How it works

```
test_cases_from_excel.json
        ↓ user messages (1 or multi-turn)
  tstation-ai chatbot  (live API call)
        ↓ SSE stream → tool_evidence + template_events
  judge LLM  (AI Gateway)
        ↓ faithfulness score 0.0–1.0
  results/benchmark_<model>.json
  results/benchmark_summary.json
```

---

## Available models

From `docker/config/llm/conf-gateway.yaml`:

| model_name | Description |
|---|---|
| `gpt-5.5` | gpt-5.5 |
| `gpt-5.5-reasoning-low` | gpt-5.5 + reasoning_effort=low |
| `gpt-5.4-reasoning` | gpt-5.4 + reasoning_effort=medium |
| `gpt-5.4` | gpt-5.4 no reasoning |
| `gpt-4o-mini` | gpt-4o-mini |

---

## Setup

**1. Set env vars in `docker/.env`:**

```env
# Required: JWT token to call chatbot API
EVAL_JWT_TOKEN=your_jwt_token_here

# Required: model being tested (used as result file label)
AI_MODEL=gpt-5.5-reasoning-low

# Judge LLM (already set in docker/.env)
AI_GATEWAY_BASE_URL=http://ai-gateway:8000/v1
AI_GATEWAY_API_KEY=sk-xxxx
```

**2. Start the stack:**

```powershell
docker compose -f docker/docker-compose.yml up -d
```

---

## Run benchmark

**Run (after `docker compose -f docker/docker-compose.yml up -d --build`):**

```powershell
docker run --rm `
  --network docker_internal-net `
  -v "${PWD}:/workspace" -w /workspace `
  --env-file docker/.env `
  python:3.12-slim bash -c "pip install httpx -q && python eval/run_eval.py --limit 10"
```

- `--env-file docker/.env` — auto-reads `AI_MODEL`, `AI_GATEWAY_*`, `EVAL_JWT_TOKEN`
- `--limit 10` — run first 10 cases; use `--limit 0` to run all 233 cases
- `--network docker_internal-net` — same network as `tstation-ai` and `ai-gateway`

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--limit N` | `5` | Max test cases per model (`0` = all 233) |
| `--test-cases-file PATH` | `test_cases_from_excel.json` | Custom test cases file |
| `--model-endpoint model=url` | reads `AI_MODEL` + `EVAL_API_URL` | Override model label and API URL |
| `--judge-api-url URL` | `AI_GATEWAY_BASE_URL` | Judge LLM base URL |
| `--judge-api-key KEY` | `AI_GATEWAY_API_KEY` | Judge LLM API key |

---

## Compare models

```powershell
# 1. Set model A in docker/.env: AI_MODEL=gpt-5.5-reasoning-low
docker compose -f docker/docker-compose.yml up -d tstation-ai
docker run --rm --network docker_internal-net -v "${PWD}:/workspace" -w /workspace --env-file docker/.env python:3.12-slim bash -c "pip install httpx -q && python eval/run_eval.py --limit 0"
# → saves eval/results/benchmark_gpt-5.5-reasoning-low.json

# 2. Swap to model B in docker/.env: AI_MODEL=gpt-4o-mini
docker compose -f docker/docker-compose.yml up -d tstation-ai
docker run --rm --network docker_internal-net -v "${PWD}:/workspace" -w /workspace --env-file docker/.env python:3.12-slim bash -c "pip install httpx -q && python eval/run_eval.py --limit 0"
# → saves eval/results/benchmark_gpt-4o-mini.json

# 3. Compare → eval/results/benchmark_summary.json
```

---

## Output

**Per-case record** (`results/benchmark_<model>.json`):
```json
{
  "id": "tc_001",
  "category": "product_compatibility",
  "latency_s": 5.4,
  "tool_evidence": [...],
  "template_events": [...],
  "agent_flow_events": [...],
  "faithfulness_eval": {
    "faithfulness": 0.95,
    "faithfulness_bin": 1,
    "verdict": "PASS",
    "reason": "..."
  }
}
```

**Summary** (`results/benchmark_summary.json`):
```json
{
  "models": [{
    "model": "gpt-5.5-reasoning-low",
    "summary": {
      "total_count": 233,
      "scored_count": 233,
      "avg_latency_s": 6.2,
      "latency_p50_s": 5.8,
      "latency_p90_s": 9.1,
      "latency_p95_s": 11.3,
      "latency_p99_s": 14.0,
      "avg_faithfulness": 0.87,
      "pass_rate_pct": 91.4
    }
  }]
}
```

---

## Scoring

Judge LLM returns `faithfulness` float `0.0–1.0`. Binarized at threshold `0.5`:

| Raw score | Binary | Verdict |
|---|---|---|
| `> 0.5` | `1` | PASS |
| `<= 0.5` | `0` | FAIL |

**Faithfulness**: does the chatbot response avoid hallucinating relative to tool evidence?

- `1.0` = fully faithful to tool output
- `0.0` = severe hallucination or factually incorrect

---

## Resume

If interrupted, re-run the same command — eval automatically skips already-completed cases.
To restart from scratch, delete `results/benchmark_<model>.json`.
