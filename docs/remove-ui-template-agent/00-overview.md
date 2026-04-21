# Remove UI Template Agent — Overview

## Goal

Remove UI Template Agent from the runtime flow.

The final direction is:

1. Router selects one Domain Agent.
2. Domain Agent calls business tools if needed.
3. Domain Agent returns one structured payload in the final FE shape.
4. BaseAgent acts as an adapter.
5. BaseAgent emits the old event types that the rest of the system already understands.

There is no second LLM call for UI formatting.

## Main Idea

Today the system does this:

- Domain Agent thinks and gathers data
- later, UI Template Agent reads the result again
- UI Template Agent formats UI payload for FE

The new design removes that second step.

The Domain Agent already knows:

- what the user asked
- which tool was called
- what the tool returned
- what text it wants to say

So the Domain Agent should also create the final UI payload.

## What The LLM Must Return

The target direction is that the LLM returns one structured payload that already matches the FE template schema.

Important point:

- downstream layers should not need to read JSON directly
- BaseAgent should convert the structured payload into the event flow that already exists

That means BaseAgent should emit:

- `token`
- `message`
- `data`

from the same structured payload

Simple example:

```json
{
  "type": "data",
  "template": "quickReply",
  "data": {
    "assistantResponse": "안녕하세요! 무엇을 도와드릴까요?",
    "quickReplies": ["타이어 추천", "매장 찾기", "주문 조회"]
  }
}
```

FE should receive the same `data` event shape as before.

The rest of the backend should also continue to receive the same text-style events as before.

## Why This Is Better

### Lower latency

One LLM call disappears.

### Lower cost

There is no second prompt just for formatting UI.

### Simpler ownership

The same agent that understands the task also creates the final template.

### Easier debugging

When something is wrong, check:

- the Domain Agent output
- the JSON validation result

You do not need to debug a separate UI formatting agent.

### One schema source

Pydantic models become the main schema source.

## What Does Not Change

These parts should stay the same:

- FE schema
- FE event types
- router logic
- QC logic
- slot handling
- tool context persistence

The change is about who creates the UI payload, not about what FE receives.

It is also about where compatibility is handled:

- not in Coordinator
- not in QC
- not in history sync
- but in BaseAgent

## Before And After

### Before

1. Domain Agent returns text.
2. Coordinator collects the text.
3. UI Template Agent reads the result again.
4. UI Template Agent creates the final `data` event.

### After

1. Domain Agent returns one structured payload.
2. BaseAgent validates it.
3. BaseAgent emits:
   - `token`
   - `message`
   - `data`
4. Coordinator and later layers continue to work almost the same way.

## Final Runtime Flow

End-to-end example:

1. User asks for a tire recommendation.
2. Discovery Agent calls product tools.
3. Discovery Agent writes a human answer.
4. Discovery Agent returns one structured `product` payload.
5. BaseAgent validates that payload.
6. BaseAgent emits `message` and `data` events.
7. SSE stream sends the final `data` event to FE.
8. FE renders the card.

## Template Ownership

| Template | Main Agent |
|----------|------------|
| `quickReply` | All agents |
| `qnaComplete` | Support |
| `product` | Discovery |
| `listCar` | Discovery |
| `cheapestProduct` | Discovery |
| `previewYoutube` | Discovery |
| `voucher` | Transaction |
| `location` | Transaction |
| `datepick` | Transaction |
| `orderComplete` | Transaction |
| `preOrder` | Transaction |

## Change Size By Agent

| Agent | Change size | Reason |
|-------|-------------|--------|
| Leading | Low | only `quickReply` |
| Support | Low | 2 templates only |
| Discovery | Medium | many result shapes |
| Transaction | High | `preOrder` is complex |

## Implementation Order

1. Define shared Pydantic schema models.
2. Update BaseAgent to validate structured output and adapt it to the old event flow.
3. Update Leading Agent.
4. Update Support Agent.
5. Update Discovery Agent.
6. Update Transaction Agent.
7. Remove UI Template Agent and template mapper.

## Expected Result

- one less LLM call per turn
- lower latency
- lower cost
- less code to maintain
- simpler debugging
- same FE contract

## Scope Of These Docs

This document set describes the target final design.

That final design means:

- no UI Template Agent in the runtime path
- Domain Agent owns the final UI payload
- BaseAgent is the compatibility adapter
- LLM response must already be in the final structured format

## Documents In This Folder

| File | Purpose |
|------|---------|
| `00-overview.md` | Overall design |
| `01-json-mechanism.md` | How the direct JSON flow works |
| `02-modify-leading-agent.md` | Leading Agent rules |
| `03-modify-support-agent.md` | Support Agent rules |
| `04-modify-discovery-agent.md` | Discovery Agent rules |
| `05-modify-transaction-agent.md` | Transaction Agent rules |
| `06-coordinator-cleanup.md` | Cleanup after migration |
| `07-fe-contract.md` | FE impact and guarantees |
| `08-migration-strategy.md` | Rollout order |
| `09-risks-mitigation.md` | Risks and mitigation |
