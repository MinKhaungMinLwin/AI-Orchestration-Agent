# Model Evaluation — LLM-as-Judge

Experiment framework to compare response quality and latency across different LLM models for tstation-ai.

## How it works

```
1. Run BASELINE    → collect responses using gpt-5.4-reasoning-medium (current prod model)
2. Swap model      → change AI_MODEL_REASONING in .env, restart container (no rebuild)
3. Run EXPERIMENT  → collect responses using experiment model
4. Judge           → LLM-as-Judge scores experiment vs baseline
```

## Available models (from docker/config/llm/conf-gateway.yaml)

| model_name | Description |
|---|---|
| `gpt-5.4-reasoning` | gpt-5.4 + reasoning_effort=medium **(BASELINE)** |
| `gpt-5.4` | gpt-5.4 no reasoning |
| `gpt-5.3` | gpt-5.3 |
| `gpt-5.2` | gpt-5.2 |
| `gpt-5.1` | gpt-5.1 |
| `gpt-5.0` | gpt-5.0 |
| `gpt-4o-mini` | gpt-4o-mini |


## Step 1 — Collect baseline responses

Make sure `.env` has `AI_MODEL_REASONING=gpt-5.4-reasoning`.

```powershell
docker run --rm --network docker_internal-net -v "c:/Users/ngvda/Desktop/BLUE_ DRAGON_PROJECT/tstation-ai/eval:/eval" python:3.12-slim bash -c "pip install httpx -q && python /eval/run_eval.py responses --api-url http://tstation-ai:8000 --api-key YOUR_JWT_TOKEN --run-name baseline --model gpt-5.4-reasoning --limit 10"
```

Saves to: `eval/results/baseline.json`  


## Step 2 — Swap model (no rebuild needed)

Change `AI_MODEL_REASONING` in `.env`:
```
AI_MODEL_REASONING=gpt-5.4 or 5.3 or smaller models
```

Recreate container (fast, ~5 seconds, no image rebuild):
```powershell
docker compose -f docker/docker-compose.yml up -d tstation-ai
```

Verify new model in logs:
```powershell
docker logs docker-tstation-ai-1 --tail 5
# Should show: [MODEL_CONFIG] reasoning=openai/gpt-5.4 | ...
```

## Step 3 — Collect experiment responses

```powershell
docker run --rm --network docker_internal-net -v "c:/Users/ngvda/Desktop/BLUE_ DRAGON_PROJECT/tstation-ai/eval:/eval" python:3.12-slim bash -c "pip install httpx -q && python /eval/run_eval.py responses --api-url http://tstation-ai:8000 --api-key YOUR_JWT_TOKEN --run-name exp_gpt4omini --model gpt-5.1 --limit 10"
```

Saves to: `eval/results/exp_gpt54_no_reasoning.json`


## Step 4 — Judge (compare baseline vs experiment)

Judge calls AI Gateway internally (must run on same Docker network):

```powershell
docker run --rm --network docker_internal-net -v "c:/Users/ngvda/Desktop/BLUE_ DRAGON_PROJECT/tstation-ai/eval:/eval" python:3.12-slim bash -c "pip install httpx -q && python /eval/run_eval.py judge --judge-api-url http://ai-gateway:8000/v1 --judge-api-key LLM_api_key --baseline baseline --experiment exp_gpt54_no_reasoning"
```

Saves to: `eval/results/judge_results.json`


## Scoring

Judge LLM returns float scores 0.0–1.0. Binarized at threshold 0.5:

| Raw score | Binary | Meaning |
|-----------|--------|---------|
| > 0.5 | 1 (PASS) | Acceptable |
| ≤ 0.5 | 0 (FAIL) | Not acceptable |

- **faithfulness**: does the response avoid hallucination?
- **correctness**: does the response convey the same info as baseline?

**PASS** = faithfulness > 0.5 AND correctness > 0.5
