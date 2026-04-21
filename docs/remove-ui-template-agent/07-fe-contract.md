# FE Contract

## Main Rule

FE should not need any schema change.

The backend implementation changes, but the FE contract stays the same.

## Event Types

FE still receives the same main event types:

- `token`
- `data`
- `message`
- `status`
- `sub-agent`
- `tool`

## What Changes For FE

Only small behavior details may change:

- fewer `sub-agent` events because UI Template Agent is gone
- `data` may arrive earlier in the turn
- `source_domain` may now be the real Domain Agent name

## What Does Not Change

- template names
- template field names
- data event structure
- frontend rendering contract

## Canonical data Event Shape

FE should still receive this top-level structure:

```json
{
  "type": "data",
  "template": "product",
  "data": {
  }
}
```

Only the content of `data` changes by template.

## Templates That Stay The Same

These template names stay unchanged:

- `quickReply`
- `listCar`
- `product`
- `voucher`
- `location`
- `previewYoutube`
- `datepick`
- `preOrder`
- `orderComplete`
- `qnaComplete`
- `cheapestProduct`

## Example Templates

### quickReply

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

### product

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

### qnaComplete

```json
{
  "type": "data",
  "template": "qnaComplete",
  "data": {
    "assistantResponse": "1:1 문의 페이지로 이동합니다.",
    "redictLink": {
      "pc": "https://...",
      "mobile": "https://..."
    },
    "cnslType": "주문/결제/배송",
    "title": "배송 문의",
    "summary": "배송 지연에 대한 문의입니다."
  }
}
```

## Validation Rules

Before release, confirm:

- all required fields still exist
- field names still match FE expectations
- numbers stay numbers
- URLs stay unchanged
- metadata stays aligned with visible list items
- null handling matches FE expectations

## FE Checkpoints

Before rollout, confirm whether FE depends on:

- `[UI TEMPLATE AGENT]` as a special name
- exact event order between `data` and `message`
- `source_domain` values
- a fixed number of `sub-agent` events

If FE does not rely on those details, the migration is transparent.

## Final Statement

The UI rendering contract stays the same.

Only the producer of the payload changes.

In the final design, that producer is the Domain Agent response parsed by BaseAgent.
