# Structured Output Mechanism

## Core Idea

The Domain Agent must return the final UI payload itself.

It does not call another agent later.

It does not wait for a second formatting step.

The key design choice is this:

- the Domain Agent returns one structured payload
- BaseAgent adapts that payload into the old runtime events

This is important because the later layers still expect text-like events.

## End-To-End Flow

### Step 1: Domain Agent understands the request

The agent decides:

- what the user wants
- which business tool to call
- what final template should be shown

### Step 2: Domain Agent calls normal business tools

Examples:

- Discovery reads product, car, or video data
- Support reads FAQ or QnA transfer data
- Transaction reads coupon, store, or order data

### Step 3: Domain Agent returns one structured payload

That payload already matches the final FE schema.

The payload must still contain `assistantResponse`, because BaseAgent will use it to rebuild the old text-style flow.

Main rules:

- exactly one template per turn
- correct template name
- correct field names
- correct field types
- no internal backend fields shown to the user
- `assistantResponse` must be present when the template needs user-facing text

### Step 4: BaseAgent validates the structured payload

Pydantic is used only for validation.

It checks:

- required fields exist
- types are correct
- nested objects are correct
- optional fields are acceptable

### Step 5: BaseAgent acts as the adapter

BaseAgent should turn one structured payload into the existing runtime events.

For example:

- `assistantResponse` becomes `token`
- `assistantResponse` becomes `message`
- the full payload becomes `data`

This means later layers do not need to understand the structured payload format directly.

### Step 6: BaseAgent emits the FE event

If validation passes, BaseAgent emits the final `data` event.

FE only sees the final result. FE does not care whether the data came from an old or new internal flow.

At the same time, Coordinator, QC, and history sync can keep working with `message` and `token` events.

## Simple Response Shape

The structured payload concept is:

1. one top-level `data` event shape
2. `assistantResponse` inside `data`

BaseAgent uses `assistantResponse` to recreate text-style events.

Example for a quick reply:

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

Example for a product result:

```json
{
  "type": "data",
  "template": "product",
  "data": {
    "assistantResponse": "추천 상품을 확인해 주세요.",
    "products": [
      {
        "imageUrl": "https://...",
        "title": "Ventus S2 AS 225/45R18",
        "tires": "고급형",
        "comfort": "높음",
        "price": 150000,
        "rate": 4.8,
        "totalQuantity": 12
      }
    ],
    "metadata": [
      {
        "goodsId": "G0123456789"
      }
    ]
  }
}
```

## Why This Design Is Better

### One agent already has enough context

The Domain Agent already saw:

- user request
- tool output
- slot context
- conversation history

So it is the best place to create the final UI payload.

### One schema source

Pydantic models become the single schema reference.

### No extra LLM call

The second formatting step disappears.

### Easier debugging

If something is wrong, inspect:

- the Domain Agent structured response
- the validation error
- the BaseAgent adapter output

### Minimal downstream change

Coordinator, QC, history, and FE can keep their old assumptions much longer.

## What Each Agent Must Return

### Leading Agent

Always returns `quickReply`.

### Support Agent

Returns:

- `qnaComplete` for QnA transfer
- `quickReply` for FAQ and normal support answers

### Discovery Agent

Returns one of:

- `product`
- `listCar`
- `cheapestProduct`
- `previewYoutube`
- `quickReply`

### Transaction Agent

Returns one of:

- `voucher`
- `location`
- `datepick`
- `orderComplete`
- `preOrder`
- `quickReply`

## Prompt Contract

Each Domain Agent prompt must clearly explain:

- when to use each template
- which fields are required
- how to map backend fields to FE fields
- that one valid structured payload must be returned

The prompt should be short, strict, and easy to follow.

## Output Rules

The final JSON object must follow these rules:

- only one template per turn
- FE field names only
- use camelCase where FE expects camelCase
- keep URLs unchanged
- keep numbers as numbers
- keep lists within allowed size
- never expose internal values to users

## Failure Handling

If structured output is missing or invalid:

- BaseAgent logs the error
- invalid `data` is not sent to FE
- the issue must be fixed in prompt rules or schema rules

The final design should not depend on a second formatting agent.

## Final Outcome

This mechanism replaces UI Template Agent completely.

The final UI payload is created in the first agent response, and BaseAgent adapts it for the rest of the system.
