# Eval — Faithfulness Benchmark

LLM-as-Judge evaluation for chatbot faithfulness. Results are saved directly to Langfuse.

**Faithfulness** = does the bot's response match the actual tool call data (no hallucinations)?

---

## Setup

Set these variables in `docker/.env`:

```env
EVAL_JWT_TOKEN=your_jwt_token          # JWT to call chatbot API
AI_GATEWAY_API_KEY=sk-xxxx             # API key for judge LLM
HTTPS_PORT=8001                        # nginx HTTPS port (default 8001)
LANGFUSE_PUBLIC_KEY=pk-lf-xxx          # Langfuse project public key
LANGFUSE_SECRET_KEY=sk-lf-xxx          # Langfuse project secret key
LANGFUSE_HOST=http://localhost:3002    # Langfuse host (default localhost:3002)
```

---

## Step 1 — Upload dataset to Langfuse (run once)

```bash
python eval/upload_dataset.py
```

| Flag | Default | Description |
| --- | --- | --- |
| `--dataset` | `tstation-eval` | Dataset name on Langfuse |
| `--file` | `eval/test_cases_tool_only.json` | Test cases JSON file |
| `--limit N` | `0` (all) | Upload only first N cases |
| `--dry-run` | — | Preview without making API calls |

```bash
# Preview
python eval/upload_dataset.py --dry-run

# Upload 10 cases to a new dataset for quick testing
python eval/upload_dataset.py --dataset tstation-eval-v2 --limit 10

# Upload all
python eval/upload_dataset.py --dataset tstation-eval
```

> Safe to re-run — existing items are skipped (idempotent).

---

## Step 2 — Run eval

```bash
python eval/langfuse_eval.py --model <model> --run-name <run>
```

| Flag | Default | Description |
| --- | --- | --- |
| `--model` | _(required)_ | Model label (e.g. `gpt-5.5-reasoning-low`) |
| `--run-name` | _(required)_ | Langfuse run name (e.g. `gpt-5.5-r1`) |
| `--step` | `all` | `experiment` / `judge` / `all` — run one step or both |
| `--dataset` | `tstation-eval` | Dataset uploaded in Step 1 |
| `--limit N` | `0` (all) | Max items in experiment step (0 = all) |
| `--concurrency N` | `1` | Parallel workers |
| `--api-url` | `https://localhost:8001/api` | Chatbot URL (via nginx) |
| `--judge-api-url` | `http://localhost:4000/v1` | Judge LLM URL (ai-gateway) |
| `--judge-api-key` | `AI_GATEWAY_API_KEY` from env | Judge LLM API key |

```bash
# Run both steps (default)
python eval/langfuse_eval.py \
  --model gpt-5.5-reasoning-low \
  --run-name gpt-5.5-low-r1

# Experiment only (call chatbot, upload traces)
python eval/langfuse_eval.py \
  --model gpt-5.5-reasoning-low \
  --run-name gpt-5.5-low-r1 \
  --step experiment

# Judge only (re-score an existing run with a different judge model)
python eval/langfuse_eval.py \
  --model gpt-5.5-reasoning-low \
  --run-name gpt-5.5-low-r1 \
  --step judge

# Quick test: 5 items, 4 parallel workers
python eval/langfuse_eval.py \
  --model gpt-5.5-reasoning-low \
  --run-name gpt-5.5-low-test \
  --limit 5 --concurrency 4
```

---

## Viewing Results

Go to Langfuse UI → **Datasets** → select dataset → select run.

```text
Langfuse
└── Datasets
    └── tstation-eval
        ├── gpt-5.5-low-r1    ← click to view each item
        ├── claude-sonnet-r1
        └── o3-high-r1
```

Each item has:

- **Score `faithfulness`**: float 0.0–1.0 (`> 0.5` = PASS)
- **Trace**: full span (classify → agent → tools → response)

---

## How It Works

```text
upload_dataset.py         experiment.py (--step experiment)   judge.py (--step judge)
─────────────────         ──────────────────────────────────   ──────────────────────
Read test_cases.json
Create Langfuse dataset   Fetch dataset items
Upload items              For each item (parallel OK):          Fetch dataset run items
                          ├─ POST /tstation/messages/chat       For each run item:
                          │    → collect tool_evidence,         ├─ GET trace from Langfuse
                          │      template_events                │    → read input, output
                          ├─ upsert trace (input + output)      ├─ call judge LLM
                          └─ create dataset run item            └─ create_score(faithfulness)
```

---

## Scoring

Judge LLM (`JUDGE_MODEL`, default `gpt-5.5-reasoning-xhigh`) returns:

| Score | Verdict |
| --- | --- |
| `> 0.5` | **PASS** — faithful |
| `<= 0.5` | **FAIL** — hallucination or wrong data |
