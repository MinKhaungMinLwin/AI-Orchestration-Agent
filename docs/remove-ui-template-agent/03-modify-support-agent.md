# Modify Support Agent

## Role

Support Agent handles:

- FAQ answers
- warranty and return questions
- escalation to human support
- 1:1 inquiry transfer

## Final Output

Support Agent must return direct JSON in its own response.

The response should contain:

- normal assistant text
- one JSON object for either `qnaComplete` or `quickReply`

It should use only these templates:

- `qnaComplete`
- `quickReply`

## When To Use Each Template

### Use `qnaComplete` when

- `transfer_to_qna_tool` was used

### Use `quickReply` when

- answering FAQ
- answering RAG-based FAQ
- confirming escalation
- handling text-only support turns

## qnaComplete Fields

Important fields:

- `redictLink`
- `cnslType`
- `title`
- `summary`
- `assistantResponse`

Important rules:

- keep URLs exactly as they came from the tool output
- map `cnsl_clss_seq` to the correct Korean label
- keep summary short and safe

## quickReply Fields

Important fields:

- `assistantResponse`
- `quickReplies`

## Example: qnaComplete

```json
{
  "type": "data",
  "template": "qnaComplete",
  "data": {
    "assistantResponse": "1:1 문의 페이지로 이동합니다. 내용을 확인하고 제출해 주세요.",
    "redictLink": {
      "pc": "https://...",
      "mobile": "https://..."
    },
    "cnslType": "주문/결제/배송",
    "title": "배송 지연 문의",
    "summary": "주문한 상품의 배송 일정 확인을 요청하는 내용입니다."
  }
}
```

## Example: quickReply For FAQ

```json
{
  "type": "data",
  "template": "quickReply",
  "data": {
    "assistantResponse": "타이어 보증은 제조일 기준과 주행거리 기준을 함께 확인해야 합니다.",
    "quickReplies": ["보증 조건", "교환 절차", "다른 질문"]
  }
}
```

## What The Prompt Must Explain

The Support prompt must clearly tell the agent:

- which template to choose for each tool result
- which fields are required
- which fields must be copied exactly
- that the response must include one valid JSON object

## Main Risks

### Long FAQ context

Long retrieved content may make the agent focus on text and forget the JSON object.

### URL corruption

The agent may change a URL slightly and break the final link.

### Wrong support type mapping

The agent may map the category code to the wrong label.

## Success Criteria

- exactly one template per turn
- `qnaComplete` only for QnA transfer
- URLs preserved exactly
- support type mapping correct
- no second formatting step after Support Agent
