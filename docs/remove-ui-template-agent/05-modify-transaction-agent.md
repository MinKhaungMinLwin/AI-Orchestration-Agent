# Modify Transaction Agent

## Role

Transaction Agent handles:

- coupon information
- nearby stores
- store schedule
- order preview
- order completion
- cart save flow

This is the most complex agent in the migration.

## Final Output

Transaction Agent must return direct JSON in its own response.

The response should contain:

- normal assistant text
- one JSON object for the final chosen template

It should use these templates:

- `voucher`
- `location`
- `datepick`
- `orderComplete`
- `preOrder`
- `quickReply`

## When To Use Each Template

Use `voucher` for coupon results.

Use `location` for store search results.

Use `datepick` for schedule results.

Use `orderComplete` for:

- quick order success or failure
- save to cart success or failure

Use `preOrder` for order preview before final confirmation.

Use `quickReply` for text-only transaction answers.

## Example: voucher

```json
{
  "type": "data",
  "template": "voucher",
  "data": {
    "assistantResponse": "사용 가능한 쿠폰을 확인해 주세요.",
    "vouchers": [
      {
        "nameVoucher": "타이어 10% 할인",
        "discount": "10%",
        "dateVoucher": "2026-04-30",
        "downloadLink": "",
        "myCouponLink": {
          "pc": "https://...",
          "mobile": "https://..."
        }
      }
    ],
    "metadata": [
      {
        "couponId": "C12345"
      }
    ]
  }
}
```

## Example: location

```json
{
  "type": "data",
  "template": "location",
  "data": {
    "assistantResponse": "가까운 매장을 확인해 주세요.",
    "stores": [
      {
        "nameAddress": "티스테이션 강남점",
        "distance": "1.2km",
        "detailAddress": "서울시 강남구 ...",
        "isAllMyT": true,
        "todayInstall": true,
        "tnaDelivery": true,
        "description": "영업시간과 연락처 정보"
      }
    ],
    "metadata": [
      {
        "shopId": "S12345"
      }
    ]
  }
}
```

## Special Focus: preOrder

`preOrder` does not come from one single tool.

It must combine data from several sources:

- slots
- previous tool results
- current user message
- previously selected date and time
- price result if available

The agent must build a complete order preview from that combined context.

This is still part of the same LLM response. There is no second formatting pass later.

## Example: preOrder

```json
{
  "type": "data",
  "template": "preOrder",
  "data": {
    "assistantResponse": "주문 내용을 확인해 주세요.",
    "orderInfo": {
      "carInfo": "K7 (12가3456)",
      "product": "Ventus S2 AS (G0123456789)",
      "quantity": 4,
      "storeName": "티스테이션 강남점 (S12345)",
      "bookingDateTime": "2026-04-22 10:00",
      "paymentAmount": 600000
    },
    "isReadyToOrder": true,
    "isReadyToAddToCart": true,
    "recommendActions": {
      "question": "주문을 진행할까요?",
      "listActions": ["주문 확정", "장바구니에 담기"]
    },
    "metadata": {
      "goodsId": "G0123456789",
      "shopId": "S12345",
      "carNo": "12가3456",
      "carLncCd": "01"
    }
  }
}
```

## Example: orderComplete

```json
{
  "type": "data",
  "template": "orderComplete",
  "data": {
    "assistantResponse": "주문이 완료되었습니다.",
    "orderInfo": {
      "carInfo": "K7 (12가3456)",
      "product": "Ventus S2 AS (G0123456789)",
      "quantity": 4,
      "storeName": "티스테이션 강남점 (S12345)",
      "bookingDateTime": "2026-04-22 10:00",
      "paymentAmount": 600000
    },
    "isSuccess": true,
    "type": "order",
    "message": null,
    "data": {
      "status": "success"
    },
    "metadata": {
      "ordNo": "O123456789",
      "goodsId": "G0123456789",
      "shopId": "S12345"
    }
  }
}
```

## preOrder Rules

The payload should show:

- car information
- product information
- quantity
- store information
- booking date and time if available
- payment amount if available

It must also decide:

- `isReadyToOrder`
- `isReadyToAddToCart`
- `recommendActions`

## Safety Rules

- do not expose raw stock quantity to the user
- do not show internal backend names in user text
- use `T바로배송`, not `T-NA`
- keep list-style results within limit

## Edge Cases

### Multi-step order flow

Different turns may produce different templates in order:

- product
- location
- datepick
- preOrder
- orderComplete

### User gives all info in one turn

Do not skip directly to final order.

Still return `preOrder` first so the user can confirm.

### User changes store or time

Return the updated store or schedule template, not final order completion.

### Order failure

Return `orderComplete` with failure state and safe message.

## Success Criteria

- exactly one template per turn
- `preOrder` fields are correctly aggregated
- no stock leakage in user-facing text
- naming stays brand-safe
- no second formatting step after Transaction Agent
