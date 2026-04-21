# Modify Discovery Agent (Phase 2)

## Role

Discovery Agent handles the product-facing side of the conversation:

- product search
- product recommendations
- compatibility answers
- product descriptions
- user car lookup and car selection
- discount comparison
- tire-related YouTube videos

## Migration Goal

Discovery Agent must directly emit the final FE payload, exactly like Leading Agent does in Phase 1.

Target flow per turn:

1. Discovery Agent runs its business tools.
2. Discovery Agent writes one fenced JSON block matching the FE schema.
3. BaseAgent adapter validates the JSON against a Pydantic schema.
4. BaseAgent adapter emits `token`, `message`, and `data` events from `assistantResponse`.
5. Coordinator skips UI Template Agent because a `data` event already exists.

## Templates Owned By Discovery

Discovery Agent must be able to return one of these templates per turn:

| Template | Primary Intent | Source Tools |
|----------|----------------|--------------|
| `quickReply` | text-only replies, fallback | any text-only case |
| `product` | product search / recommendation results | `search_product_tool`, `get_products_recommendations_tool` |
| `listCar` | multi-car selection | `get_my_cars_tool`, `get_user_vehicles_tool` |
| `cheapestProduct` | discount comparison | `compare_discount_tool` |
| `previewYoutube` | tire-related videos | `search_youtube_video_tool` |

Every turn must produce **exactly one** template.

## Migration Phases

Discovery is migrated in five incremental steps so each step can be tested in isolation before moving on.

### Phase 2A — Foundations
**Intent:** add the schema contract and make sure `BaseAgent` adapter can validate a Union of Pydantic models.

**Work:**
- Add Pydantic schemas for the 4 new templates alongside existing `QuickReplyDataEvent`:
  - `ProductTemplate` + `ProductDataEvent`
  - `ListCarTemplate` + `ListCarDataEvent`
  - `CheapestProductTemplate` + `CheapestProductDataEvent`
  - `PreviewYoutubeTemplate` + `PreviewYoutubeDataEvent`
- Expose a Discovery Union type:
  - `DiscoveryDataEvent = QuickReplyDataEvent | ProductDataEvent | ListCarDataEvent | CheapestProductDataEvent | PreviewYoutubeDataEvent`
- Confirm `BaseAgent._build_data_event_from_text` accepts the Union through `model_validate`.

**Verify:**
- Lint + syntax.
- Pydantic validates each template JSON from the examples below.
- Union validation picks the correct variant based on `template` discriminator.

### Phase 2B — Discovery + `quickReply` only
**Intent:** prove the adapter works for Discovery before adding data templates.

**Work:**
- Set `DiscoverySubAgent.OUTPUT_TEMPLATE = QuickReplyDataEvent`.
- Add MANDATORY OUTPUT FORMAT section to the prompt using `quickReply` only.
- Escape every `{` / `}` inside JSON examples (prompt uses `.format(...)`).

**Verify on Streamlit:**
- Compatibility text reply → `quickReply`.
- No-result fallback → `quickReply`.
- Single-car flow (only 1 car registered) → `quickReply`.
- Product description text → `quickReply`.

Success criteria:
- every turn emits exactly one `quickReply` data event
- `source_domain = discovery`
- no `[UI TEMPLATE AGENT]` in the log

### Phase 2C — Add `product`
**Intent:** cover the most common Discovery turn: search / recommendation result cards.

**Work:**
- Widen `DiscoverySubAgent.OUTPUT_TEMPLATE` to the Union `QuickReplyDataEvent | ProductDataEvent`.
- Expand the prompt with:
  - when to pick `product`
  - field mapping from tool output to FE fields
  - `metadata` rule
  - list size limit
  - empty-list fallback rule

**Verify on Streamlit:**
- Product search with results → `product` with up to 5 items.
- Product recommendation → `product`.
- Empty search result → `quickReply` fallback.

### Phase 2D — Add `listCar`
**Intent:** cover the car selection flow.

**Work:**
- Widen the Union with `ListCarDataEvent`.
- Add prompt rules:
  - multi-car → `listCar`
  - single-car → auto-select → `quickReply`
  - field mapping from backend vehicle fields

**Verify on Streamlit:**
- Multi-car user asking for a recommendation → `listCar`.
- Single-car user asking for a recommendation → `quickReply`.

### Phase 2E — Add `cheapestProduct` and `previewYoutube`
**Intent:** complete Discovery template coverage.

**Work:**
- Widen the Union with `CheapestProductDataEvent` and `PreviewYoutubeDataEvent`.
- Add prompt rules:
  - `cheapestProduct` when `compare_discount_tool` was used
  - `previewYoutube` when `search_youtube_video_tool` was used
  - max 5 items
  - 1 turn = 1 template

**Verify on Streamlit:**
- Discount comparison → `cheapestProduct`.
- YouTube tire videos → `previewYoutube`.

## Pydantic Schema Contract

All Discovery templates must match FE exactly.

### `quickReply`
```text
data:
  assistantResponse: str (non-empty)
  quickReplies: list[str] (0-4 items)
```

### `product`
```text
data:
  assistantResponse: str
  products: list[ProductItem]   (max 5)
  metadata: list[ProductMeta]   (aligned with products)

ProductItem:
  imageUrl: str
  title: str
  tires: str
  comfort: str
  price: int (>= 0)
  rate: float (0.0 - 5.0)
  totalQuantity: int (>= 0)

ProductMeta:
  goodsId: str
```

### `listCar`
```text
data:
  assistantResponse: str
  listCar: list[CarItem]        (max 5)
  metadata: list[CarMeta]       (aligned with listCar)

CarItem:
  licensePlate: str
  info: str
  description: str
  imageUrl: str

CarMeta:
  carNo: str
  carLncCd: str | None
```

### `cheapestProduct`
```text
data:
  assistantResponse: str
  cheapestProduct: list[CheapestItem]   (always length 1)
  metadata: list[ProductMeta]

CheapestItem:
  title: str
  originalPrice: int
  quantity: int
  totalDiscount: int
  productDiscount: int
  couponDiscount: int
  finalPrice: int
```

### `previewYoutube`
```text
data:
  assistantResponse: str
  items: list[YoutubeItem]      (max 5)

YoutubeItem:
  title: str
  thumbnailUrl: str
  youtubeUrl: str
  videoId: str
```

## Backend → FE Field Mapping

The prompt must explicitly instruct the model how to map backend fields.

### Product (from `search_product_tool` / `get_products_recommendations_tool`)

| Backend field | FE field |
|---------------|----------|
| `image_url` | `imageUrl` |
| `goods_nm` or `title` | `title` |
| `tire_class` | `tires` |
| `comfort_level` | `comfort` |
| `sale_prc` | `price` |
| `rate` / `review_rate` | `rate` |
| `stock_qty` | `totalQuantity` |
| `goods_no` | `metadata[i].goodsId` |

### Car (from `get_my_cars_tool` / `get_user_vehicles_tool`)

| Backend field | FE field |
|---------------|----------|
| `license_plate` / `car_no` | `licensePlate` |
| `car_model_nm` + `trim_nm` | `info`, `description` |
| `car_image_url` | `imageUrl` |
| `car_no` | `metadata[i].carNo` |
| `car_lnc_cd` | `metadata[i].carLncCd` |

### Cheapest Product (from `compare_discount_tool`)

| Backend field | FE field |
|---------------|----------|
| `title` / `goods_nm` | `title` |
| `sale_prc` | `originalPrice` |
| `quantity` | `quantity` |
| `total_discount` | `totalDiscount` |
| `product_discount` | `productDiscount` |
| `coupon_discount` | `couponDiscount` |
| `final_unit_price` | `finalPrice` |
| `goods_no` | `metadata[i].goodsId` |

### YouTube (from `search_youtube_video_tool`)

| Backend field | FE field |
|---------------|----------|
| `title` | `title` |
| `thumbnail_url` | `thumbnailUrl` |
| `video_url` | `youtubeUrl` |
| `video_id` | `videoId` |

## Template Selection Rules

The prompt must enforce these rules:

1. Exactly one template per turn.
2. If there is tool data to display, prefer the matching data template.
3. If no data or data is empty, fall back to `quickReply`.
4. If user has one car only, auto-select it and reply with `quickReply` — never use `listCar`.
5. If user has multiple cars and the turn needs a car pick, use `listCar` and stop at that.
6. List templates: max 5 items, aligned metadata.
7. Never fabricate URLs; use empty string `""` if backend provides nothing.
8. Never put internal ids (`goods_no`, `car_no`, `shop_id`) into user-facing text.

## Prompt Contract

Add a MANDATORY OUTPUT FORMAT section to Discovery prompt. It must:

- require exactly one fenced `json` block, no text outside the block
- list the allowed `template` values
- show a minimal example per template
- repeat the "1 turn = 1 template" rule
- remind the model to keep `assistantResponse` natural and concise

All JSON examples in the prompt must escape `{` and `}` as `{{` and `}}` because the prompt is passed through `str.format(...)`.

## Example Payloads

Examples the prompt should include (escaped when placed into the prompt template).

### `product`
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
      {"goodsId": "G0123456789"}
    ]
  }
}
```

### `listCar`
```json
{
  "type": "data",
  "template": "listCar",
  "data": {
    "assistantResponse": "등록된 차량을 선택해 주세요.",
    "listCar": [
      {
        "licensePlate": "12가3456",
        "info": "K7 2.5 GDI",
        "description": "K7 2.5 GDI",
        "imageUrl": "https://..."
      }
    ],
    "metadata": [
      {"carNo": "12가3456", "carLncCd": "01"}
    ]
  }
}
```

### `cheapestProduct`
```json
{
  "type": "data",
  "template": "cheapestProduct",
  "data": {
    "assistantResponse": "가장 저렴한 옵션을 확인해 주세요.",
    "cheapestProduct": [
      {
        "title": "Ventus S2 AS",
        "originalPrice": 521000,
        "quantity": 4,
        "totalDiscount": 22000,
        "productDiscount": 13000,
        "couponDiscount": 9000,
        "finalPrice": 499000
      }
    ],
    "metadata": [
      {"goodsId": "G0123456789"}
    ]
  }
}
```

### `previewYoutube`
```json
{
  "type": "data",
  "template": "previewYoutube",
  "data": {
    "assistantResponse": "관련 영상을 확인해 보세요.",
    "items": [
      {
        "title": "Ventus S2 Review",
        "thumbnailUrl": "https://...",
        "youtubeUrl": "https://youtube.com/watch?v=abc123",
        "videoId": "abc123"
      }
    ]
  }
}
```

## Edge Cases

### Empty search result
Return `quickReply` with a friendly fallback message and guided suggestions (e.g. check size, try a different model).

### Single-car flow
Skip `listCar` completely. Auto-select the user's only car and answer with `quickReply`.

### Multiple car selection turn
Emit `listCar` and stop at that turn. Do not also emit `product` in the same turn.

### Multiple tool calls in one turn
Pick the single most important final template based on the user intent. Typically:
- recommendation intent → `product`
- discount intent → `cheapestProduct`
- video intent → `previewYoutube`
- car-pick intent → `listCar`

### Tool returns partial data
Fill only the fields that backend returned. Do not fabricate missing values. If a required field is missing, fallback to `quickReply`.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Model picks wrong template | Strong examples per case, explicit rules in the prompt |
| Field mapping errors | Mapping table in prompt, adapter logs validation errors |
| Multiple tool calls in one turn | Rule "1 turn = 1 template", intent-based priority |
| List too long | Schema-level `max_length=5` enforced by Pydantic |
| Empty list slipping through | Prompt rule "never output empty list" plus fallback to `quickReply` |
| Raw JSON leaking into Coordinator text | `BaseAgent` suppresses raw `AIMessage.content` when `OUTPUT_TEMPLATE` is set (already done in Phase 1) |
| Prompt `.format` breaking on JSON braces | Escape all `{}` as `{{}}` in prompt JSON examples |

## Out Of Scope For Phase 2

- Remove UI Template Agent code.
- Remove `template_mapper.py`.
- Migrate Support Agent.
- Migrate Transaction Agent.
- Touch QC, slot handling, or tool context persistence logic.

These stay untouched during Phase 2.

## Success Criteria

Phase 2 is done when:

- Every Discovery turn produces exactly one valid `data` event.
- `source_domain = discovery` on every Discovery `data` event.
- No `[UI TEMPLATE AGENT]` invocation for any Discovery turn.
- FE renders all five templates correctly with no FE schema changes.
- Lint, syntax, and Pydantic validation all pass.
- Leading Agent (Phase 1) still works unchanged.

## Non-Goals

- perfect model behavior on edge prompts (monitored, not blocked on)
- Transaction migration
- FE schema changes
