# Thread Issues To Solve

## Open Issues

### 1. Purchase flow: discount question reopens schedule

- Status: TODO
- Reported behavior: after the user reaches the preorder/order confirmation step and asks a discount question, the bot shows the schedule/datepick template again instead of answering the discount question.
- Example flow:
  - User asks to buy 4 Ventus S2 AS tires, size 275/35R20, at T-Station Pangyo.
  - User selects an installation schedule.
  - User asks: "How is the discount applied?"
- Expected behavior: answer the discount/price question in the current purchase context without reopening date selection.

### 2. Product name parsing error

- Status: TODO
- Reported behavior: the bot does not reliably preserve the selected product identity during purchase flow, especially when a product name and size are provided together.
- Example flow:
  - User asks to buy 4 Ventus S2 AS tires with size 275/35R20.
  - Or user asks to reserve installation for 4 Ventus S2 AS tires with size 275/35R20 at T-Station Pangyo.
- Expected behavior: parse and keep the intended product name/selected product correctly, then continue the purchase flow without asking unrelated product clarification.

### 3. Purchase flow pivot is not working

- Status: TODO
- Reported behavior: pivot works in normal situations but not inside the purchase flow. When the user changes topic or selects a support/contact action after an order failure, the bot falls back to reservation schedule/datepick instead of answering the pivoted request.
- Screenshot context: after order failure, user selected "1:1 inquiry", but the bot responded with the fastest available installation date and showed the schedule picker again.
- Expected behavior: honor the user's pivot intent inside purchase flow, answer or route the support/contact request, and avoid stale purchase-flow schedule recovery unless the user asks to continue scheduling.
