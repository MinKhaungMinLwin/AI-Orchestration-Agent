# Chat V3 — TODO: Port tính năng V2 sang V3 (LLM-first, zero-regex)

> **Trạng thái:** Phase 0–8 đã triển khai (2026-07-07) · **Flag:** `AI_CHAT_V3_PURE_LLM_ENABLED` · **V2 giữ nguyên, không đụng.**

## Hiện trạng triển khai

Toàn bộ package `services/tstation/chat_v3/` đã được viết (22 file, tổng ~1.150 dòng, file lớn nhất 196 dòng).
Đã verify: zero-regex grep sạch, ruff sạch, mocked E2E pass (pure chat / guard path / router-failure degrade).
**Chưa verify với LLM thật** — gateway `ai-gateway:8000` chỉ resolve trong Docker network, cần chạy `just start` và test qua `/chat`.

Các điểm lệch so với plan ban đầu (phát hiện khi triển khai):
- `g_qc_agent` **không tồn tại** trong repo (CLAUDE.md cũ) → `qc.py` tự triển khai fact-check bằng mini-model structured output, gate bằng `AI_QC_ENABLED`.
- Guard `price_policy` tách thành 3 guard id (`coupon_issue_request`, `expired_coupon_or_event`, `nonexistent_benefit`); `pickup_service` tách thành 2 (`pickup_status`, `pickup_info`) — LLM route sub-intent trực tiếp, tổng 13 guard.
- History summary không cần làm ở V3: API layer đã dùng `get_history_for_llm` (summary + recent) khi build `request.messages`.
- Slots: reuse nguyên `ConversationSlots` + `merge()` (dependency resets) + `ChatHistoryService.get_slots/save_slots_async` — V3 chỉ thay phần *extraction* bằng LLM (`SlotsPatch` trong RouteDecision).
- Guard text dynamic của V2 (brand label, giá sản phẩm nội bộ) được viết lại thành bản tĩnh tương đương; guard ngày đặt hẹn tính ngày bằng `datetime` (không regex).

## Nguyên tắc bất di bất dịch

1. **Không regex.** V2 có ~253 chỗ dùng `re.*` trong `chat.py` (40k dòng). V3 cấm `import re` cho logic nghiệp vụ.
2. **LLM-based routing thay regex.** Mọi quyết định "câu này là intent gì / cần guard nào / slot nào" đều do **một LLM router call với structured output** quyết định — không rule table, không keyword match.
3. **Gắn từ cơ bản trước.** Mỗi phase chạy được độc lập, có success criteria, xong phase này mới sang phase sau.
4. **Mỗi file một trách nhiệm, < 200 dòng** (theo `docs/code-standards.md`). Không bao giờ lặp lại sai lầm `chat.py` 40k dòng.
5. **Contract FE không đổi.** V3 emit đúng SSE events V2 đang emit (`token`, `message`, `data`, `status`, `agent_flow`, `DONE`, `[DONE]`) — FE và API layer (`stream_chat_response`) không cần sửa.

---

## Cấu trúc module đích: `services/tstation/chat_v3/`

Chuyển `chat_v3.py` (1 file hiện tại) thành package:

```
services/tstation/chat_v3/
├── __init__.py          # public API: chat(request), enabled() — không chứa logic
├── service.py           # entrypoint duy nhất: orchestrate router → executor → composer
├── llm.py               # LLM instances (chat model, router model AI_MODEL_MINI)
├── sse.py               # SSE event builders: token/message/data/status/agent_flow/DONE
├── context.py           # build messages: user info (JWT/UI), history, summary
│
├── prompts/             # mỗi prompt 1 file, chỉ chứa text — không logic
│   ├── __init__.py
│   ├── persona.py       # system prompt persona T-Station
│   ├── router.py        # prompt cho router call (intent + guard + slots)
│   └── composer.py      # prompt sinh câu trả lời + quickReplies
│
├── router/              # LLM-based routing — thay toàn bộ regex classify của V2
│   ├── __init__.py
│   ├── schemas.py       # RouteDecision (Pydantic): safety, guard_id, domain, intents, slots_patch
│   ├── route.py         # 1 LLM call structured output → RouteDecision
│   └── guards.py        # canned guard responses (chỉ TEXT trả lời — trigger do LLM quyết)
│
├── slots/               # conversation state
│   ├── __init__.py
│   ├── schemas.py       # V3 slots model (reuse field của ConversationSlots)
│   ├── extract.py       # LLM structured-output extraction — thay extract_from_user_text regex
│   └── store.py         # đọc/ghi slots vào Redis (reuse chat_history_service)
│
├── tools/               # tool registry theo domain — re-export tool sẵn có, KHÔNG viết lại
│   ├── __init__.py      # registry: domain → [tools]; mọi tool đăng ký tại đây
│   ├── discovery.py     # từ agents/b_discovery_agent/tools.py
│   ├── transaction.py   # từ agents/c_transaction_agent/tools.py
│   └── support.py       # từ agents/e_support_agent/tools.py
│
├── executor.py          # native tool-calling loop: LLM tự chọn + gọi tool, emit tool events
├── composer.py          # final answer + quickReplies (LLM sinh chips — không hardcode rule)
├── templates.py         # validate/map output → FE templates (schemas.py là source of truth)
└── qc.py                # optional: QC pass reuse g_qc_agent chain
```

**Luồng xử lý mỗi turn (sau khi hoàn thành):**

```
request
  → context.py   (messages + user info + slots hiện tại)
  → router/      (1 LLM call: safety? guard? domain? slots mới?)
      ├─ guard   → guards.py trả canned response → sse → DONE
      └─ pass    → executor.py (tool-calling loop với tools của domain)
                     → composer.py (answer + quickReplies + template)
                     → templates.py (validate FE payload)
                     → sse → DONE
  → slots/store.py (persist slots sau turn)
```

---

## Bảng quy đổi: V2 regex → V3 LLM

| V2 (regex/rule) | V3 (LLM-based) |
|---|---|
| `check_pii()` regex | `router` call trả `safety: "pii"` — hoặc giữ guard text, chỉ thay trigger |
| 10 fast-path guards (`_privacy_contact_request_event`, `_is_regional_cheapest_query`, `_price_policy_guard_event`, …) | `router` trả `guard_id` enum; `guards.py` giữ nguyên **nội dung** câu trả lời canned |
| `_rule_based_classify` + `_goal_based_classify` + `classify_multi_intent` (3 tầng) | 1 field `domain` + `intents[]` trong RouteDecision |
| ~60 hàm `_router_contract_*` / `_restore_*_contract` override | Bỏ hẳn — prompt router viết rõ tiêu chí, không cần vá sau |
| `ConversationSlots.extract_from_user_text` (regex slots) | `slots/extract.py` structured output |
| Rule dispatch agent theo prefix (a_/b_/c_/e_) | LLM tool-calling: bind tools theo domain, model tự chọn tool |
| `f_ui_template_agent` render | `composer.py` + `OUTPUT_TEMPLATE`-style validation (theo refactor đang chạy) |

**Điểm mấu chốt:** guard/canned **response text** không phải regex — chỉ **trigger** mới là regex. V3 giữ nguyên text, thay trigger bằng LLM router. Đây là phần port rẻ nhất.

---

## Các bước thực hiện (cơ bản → nâng cao)

### Phase 0 — Tách package (không đổi behavior) — ✅ DONE
- [ ] Chuyển `chat_v3.py` → package `chat_v3/` với `__init__.py`, `service.py`, `llm.py`, `sse.py`, `prompts/persona.py`
- [ ] `chat.py` chỉ đổi import path (`from services.tstation.chat_v3 import ...` vẫn chạy nhờ `__init__.py`)
- [ ] Ruff + py_compile pass
- **Success:** bật flag, chat thuần LLM hoạt động y hệt hiện tại.

### Phase 1 — Context: user info + history summary — ✅ DONE
- [ ] `context.py`: port logic `_build_messages_with_user_info` của V2 (JWT `get_user_info_from_token`, merge `request.user_info`, USER CONTEXT message) — logic này là format thuần, không regex
- [ ] Nhét history summary (reuse `history_summarizer`) vào system context khi hội thoại dài
- **Success:** bot biết tên user, vị trí (xpos/ypos), nhớ ngữ cảnh phiên dài.

### Phase 2 — LLM Router (xương sống của V3) — ✅ DONE (test set câu mẫu: TODO)
- [ ] `router/schemas.py`: `RouteDecision` Pydantic — `safety` (pass/pii/privacy_contact), `guard_id` (enum ~10 guard của V2 hoặc none), `domain` (LEADING/DISCOVERY/TRANSACTION/SUPPORT), `intents[]`, `needs_clarification`
- [ ] `router/route.py`: 1 call `AI_MODEL_MINI` với `with_structured_output(RouteDecision)` — gộp safety + guard + classify vào **một** call để giữ latency
- [ ] `router/guards.py`: copy nguyên văn ~10 canned guard responses từ V2 (regional cheapest, unsupported brand, price policy, reservation date, vehicle type, pickup, past event, privacy contact, PII, external price) — chỉ text + chips, zero logic
- [ ] `service.py`: route → nếu guard thì stream canned response, nếu pass thì (tạm) pure chat như Phase 0
- [ ] Test set: file câu mẫu tiếng Hàn cho từng guard/domain, assert route đúng (chạy bằng pytest gọi router thật hoặc mock)
- **Success:** các câu từng bị V2 chặn bằng regex giờ bị V3 chặn bằng LLM, cùng câu trả lời.

### Phase 3 — Slots bằng LLM — ✅ DONE
- [ ] `slots/schemas.py`: model slots V3 (lấy field từ `ConversationSlots`: car_no, owner_nm, goods_no, region, schedule, goal_type, pending_intent…)
- [ ] `slots/extract.py`: gộp extraction vào **cùng router call** (thêm field `slots_patch` vào RouteDecision) — không tốn call riêng
- [ ] `slots/store.py`: persist/merge slots qua Redis (merge là dict-merge thuần, không regex)
- [ ] Truyền slots vào system context cho các call sau
- **Success:** user nói biển số xe 1 lần, turn sau bot vẫn nhớ; đổi xe thì slots reset đúng.

### Phase 4 — Tools read-only (Discovery trước — an toàn nhất)
- [ ] `tools/discovery.py`: đăng ký `search_product_tool`, `search_product_summary_tool`, `get_user_vehicles_tool`, `check_compatibility_tool`, `get_car_trims_tool`, `search_car_model_tool`, `get_products_recommendations_tool`, `get_best_selling_products_tool`
- [ ] `executor.py`: bind tools theo `RouteDecision.domain`, chạy native tool-calling loop (max N vòng), LLM **tự quyết** gọi tool nào — không dispatch rule
- [ ] `sse.py`: emit `status: tool_start` (+ display name từ `TOOL_DISPLAY_NAMES`), `tool`, `agent_flow` như V2 để FE hiện tiến trình
- [ ] Set BE token: `set_tstation_be_token(request.access_token)` trước khi executor chạy
- **Success:** "타이어 추천해줘" → bot gọi tool thật, trả sản phẩm thật.

### Phase 5 — Store search + FAQ (vẫn read-only)
- [ ] `tools/transaction.py` (phần đọc): `search_stores_tool`, `get_store_detail_tool`, `get_nearby_stores_tool`, `get_store_schedule_tool`, `get_stores_with_time_filter_tool`, `search_place_tool`, `get_cheapest_price_tool`, `get_final_price_tool`
- [ ] `tools/support.py`: `search_faq_hybrid_tool` / `search_faq_rag_tool` / `get_faq_tool`, `get_my_warranties_tool`, `transfer_to_qna_tool`, `escalate_tool`
- **Success:** tìm matjang theo vị trí user, trả lời FAQ từ RAG.

### Phase 6 — Transaction ghi dữ liệu (nguy hiểm — làm cuối cùng của tools)
- [ ] `tools/transaction.py` (phần ghi): `quick_order_tool`, `save_to_cart_tool`, `issue_coupon_tool`
- [ ] Confirm-trước-khi-ghi trong **prompt** (không code rule): LLM phải hỏi xác nhận trước khi gọi tool ghi; validate schedule datetime reuse `llm_first/schedule_validation.py`
- [ ] Order slots (goods_no, ord_qty, schedule) đi qua `slots/` như mọi slot khác
- **Success:** flow đặt hàng end-to-end có bước xác nhận, không đặt nhầm.

### Phase 7 — FE templates + quickReplies — ⚠️ PARTIAL (quickReply DONE; rich templates: TODO)
- [ ] `composer.py`: sau executor, 1 call sinh `assistantResponse` + `quickReplies` (LLM đề xuất chips theo ngữ cảnh — thay các bảng chips hardcode của V2)
- [ ] `templates.py`: map tool results → template FE (`productCarousel`, `storeList`, `datepick`…) validate bằng Pydantic models trong `agents/templates/schemas.py` (source of truth, không định nghĩa lại)
- [ ] Structured output / fenced-JSON parse theo pattern `OUTPUT_TEMPLATE` của `BaseAgent`
- **Success:** FE render card sản phẩm/danh sách matjang y như V2.

### Phase 8 — QC + observability + hardening — ⚠️ PARTIAL (QC + latency log DONE; Langfuse spans: TODO)
- [ ] `qc.py`: reuse chain `g_qc_agent` (`invoke_qc`) sau composer, bật/tắt bằng `AI_QC_ENABLED`
- [ ] Langfuse tracing: span `chat_v3` cha, child spans cho router/executor/composer
- [ ] Latency log từng stage (slots/route/tools/compose) như V2 đang log
- [ ] Chip context / `ui_action` từ FE: đưa vào **input của router** (như 1 message) thay vì fast-path rule
- **Success:** trace đầy đủ trên Langfuse, QC sửa được câu trả lời sai fact.

---

## Kiểm soát chất lượng xuyên suốt

- **Zero-regex check:** thêm vào CI/pre-commit: `grep -rn "^import re\|^from re\|re\.compile\|re\.search\|re\.match" app/tstation-ai/services/tstation/chat_v3/` phải trả rỗng.
- **File size check:** không file nào trong `chat_v3/` vượt 200 dòng.
- **Không import từ `chat.py`:** `chat_v3/` chỉ được import từ `agents/*/tools.py`, `agents/templates/schemas.py`, `llm_first/schedule_validation.py`, `chat_history_service`, `config` — tuyệt đối không kéo helper từ `chat.py` (tránh dính regex và dây mơ rễ má).
- **Latency budget:** router call dùng `AI_MODEL_MINI`; mục tiêu tổng ≤ V2 (V2 đang tốn 3 tầng classify + chuỗi guard tuần tự).

## Rủi ro cần biết trước

| Rủi ro | Đối sách |
|---|---|
| LLM router miss guard mà regex bắt được 100% | Test set câu mẫu per guard chạy trong CI; prompt router liệt kê ví dụ từng guard |
| Latency tăng vì thêm router call | Gộp safety+guard+classify+slots vào 1 call mini-model; V2 cũng đang tốn tương đương |
| Tool ghi dữ liệu bị gọi nhầm | Phase 6 làm cuối; confirm bắt buộc trong prompt; test staging trước |
| Router call fail | Fallback: pure chat (Phase 0 behavior) — degrade mềm, không chết request |
