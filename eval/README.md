# Model Evaluation - LLM-as-Judge

Experiment framework to compare response quality and latency across different LLM models for `tstation-ai`.

## How it works

```text
1. Run BASELINE    -> collect responses using baseline model
2. Swap model      -> change AI_MODEL_REASONING in .env, restart container
3. Run EXPERIMENT  -> collect responses using experiment model
4. Judge           -> LLM-as-Judge scores experiment vs baseline
```

## Available models

From `docker/config/llm/conf-gateway.yaml`.

| model_name | Description |
|---|---|
| `gpt-5.4-reasoning` | gpt-5.4 + reasoning_effort=medium (baseline) |
| `gpt-5.4` | gpt-5.4 no reasoning |
| `gpt-5.3` | gpt-5.3 |
| `gpt-5.2` | gpt-5.2 |
| `gpt-5.1` | gpt-5.1 |
| `gpt-5.0` | gpt-5.0 |
| `gpt-4o-mini` | gpt-4o-mini |

## Step 1 - Collect baseline responses

Make sure root `.env` has the baseline model, for example:

```text
AI_MODEL_REASONING=gpt-5.4-reasoning
```

Run baseline:

```powershell
docker run --rm --network docker_internal-net -v "${PWD}:/workspace" -w /workspace python:3.12-slim bash -c "pip install httpx -q && python -m eval.run_eval responses --api-url http://tstation-ai:8000 --jwt-token YOUR_JWT_TOKEN --run-name baseline --model gpt-5.4-reasoning --judge-api-url http://ai-gateway:8000/v1 --judge-api-key YOUR_JUDGE_API_KEY --limit 10"
```

Saves to: `eval/results/baseline.json`

Notes:
- `baseline` now uses `eval/test_cases_from_excel.json` by default.
- Progress logs are printed through `eval.response_runner`.

## Step 2 - Swap model

Change root `.env`:

```text
AI_MODEL_REASONING=gpt-4o-mini
```

Restart only `tstation-ai`:

```powershell
docker compose -f docker/docker-compose.yml up -d tstation-ai
```

Verify the model loaded:

```powershell
docker compose -f docker/docker-compose.yml logs tstation-ai --tail 20
```

Look for:

```text
[MODEL_CONFIG] main=openai/... | reasoning=openai/gpt-4o-mini | ...
```

Or inspect the env directly:

```powershell
docker compose -f docker/docker-compose.yml exec tstation-ai printenv AI_MODEL_REASONING
```

## Step 3 - Collect experiment responses

Run experiment:

```powershell
docker run --rm --network docker_internal-net -v "${PWD}:/workspace" -w /workspace python:3.12-slim bash -c "pip install httpx -q && python -m eval.run_eval responses --api-url http://tstation-ai:8000 --jwt-token YOUR_JWT_TOKEN --run-name experiment --model gpt-4o-mini --judge-api-url http://ai-gateway:8000/v1 --judge-api-key YOUR_JUDGE_API_KEY --limit 10"
```

Saves to: `eval/results/experiment.json`

Notes:
- `experiment` now also uses `eval/test_cases_from_excel.json` by default.
- If needed, you can override the file explicitly with `--test-cases-file test_cases_from_excel.json`.

## Step 4 - Judge baseline vs experiment

Judge calls AI Gateway internally and must run on the same Docker network:

```powershell
docker run --rm --network docker_internal-net -v "${PWD}:/workspace" -w /workspace python:3.12-slim bash -c "pip install httpx -q && python -m eval.run_eval judge --judge-api-url http://ai-gateway:8000/v1 --judge-api-key YOUR_JUDGE_API_KEY --baseline baseline --experiment experiment"
```

Saves to: `eval/results/judgment_baseline_vs_experiment_*.json`

## Scoring

Judge LLM returns float scores `0.0-1.0`. Binarized at threshold `0.5`:

| Raw score | Binary | Meaning |
|---|---|---|
| `> 0.5` | `1 (PASS)` | Acceptable |
| `<= 0.5` | `0 (FAIL)` | Not acceptable |

- `faithfulness`: does the response avoid hallucination?
- `correctness`: does the response convey the same info as baseline?

`PASS` = `faithfulness > 0.5` and `correctness > 0.5`