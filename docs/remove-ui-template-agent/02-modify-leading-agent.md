# Modify Leading Agent

## Role

Leading Agent is the simplest case.

It mainly handles:

- greeting
- self introduction
- out-of-scope redirect
- complaint tone
- simple first-contact replies

It usually does not need business tools.

## Final Output

Leading Agent should always return `quickReply` directly in its own response.

There should be no later UI formatting step.

In the Phase 1 implementation, Leading Agent returns one structured `quickReply` payload.

BaseAgent then converts that single payload into:

- `token`
- `message`
- `data`

So the rest of the system can keep working almost unchanged.

## Why Leading Agent Goes First

This is the easiest migration target because:

- only one template is needed
- field structure is simple
- no complex data mapping is needed

If this works well, the same pattern can be applied to the other agents.

## Required Structured Shape

Leading Agent should always return this structure:

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

## What The Prompt Must Say

The prompt must make these rules very clear:

- always produce one `quickReply` payload
- put the full user-facing answer inside `assistantResponse`
- keep `quickReplies` short and useful

Important note:

In this phase, the model is not expected to output separate free text and JSON.
It should output the structured payload, and BaseAgent will rebuild the text-style events from `assistantResponse`.

## quickReply Rules

The payload must include:

- `assistantResponse`
- `quickReplies`

Quick reply rules:

- 2 to 4 items
- short and natural
- useful next actions
- same language as the user when needed

## Suggested Quick Replies

Greeting:

- tire recommendation
- find a store
- check order
- ask support

Self introduction:

- tire recommendation
- find a store
- price check

Complaint:

- connect to support
- try again

Out of scope:

- tire recommendation
- price check

## Example Situations

### Greeting

Text meaning:

- polite hello
- ask what user needs

JSON example:

```json
{
  "type": "data",
  "template": "quickReply",
  "data": {
    "assistantResponse": "안녕하세요! 무엇을 도와드릴까요?",
    "quickReplies": ["타이어 추천", "매장 찾기", "주문 조회", "1:1 문의"]
  }
}
```

### Complaint

Text meaning:

- apology
- calm tone
- offer next step

JSON example:

```json
{
  "type": "data",
  "template": "quickReply",
  "data": {
    "assistantResponse": "불편을 드려 죄송합니다. 자세히 말씀해 주시면 확인해 드릴게요.",
    "quickReplies": ["상담사 연결", "다시 설명할게요"]
  }
}
```

## Before And After

### Before

- Leading Agent returned normal text only
- UI Template Agent later created `quickReply`

### After

- Leading Agent returns one structured `quickReply`
- BaseAgent emits `token`, `message`, and `data`
- Coordinator can skip UI Template Agent for Leading turns

## Main Risk

The agent may fail to return the structured payload.

The prompt and schema must make the output requirement explicit and mandatory.

## Success Criteria

- exactly one `quickReply` payload per turn
- no second formatting step after Leading Agent
- downstream layers still receive text-style events through BaseAgent
- quick replies stay useful and short
