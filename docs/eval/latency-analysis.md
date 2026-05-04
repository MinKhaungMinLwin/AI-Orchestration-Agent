# Latency Analysis — T-Station AI

Filters applied to both datasets: scored agents only (`discovery_agent` + `transaction_agent`), records with at least 1 tool call, outliers removed (mean + 2×std on `total_s`).

| Dataset | Source | Model(s) | Records after filter |
|---------|--------|----------|----------------------|
| **Baseline** | `benchmark_baseline.json` | gpt-5.5-reasoning-low | 37 |
| **v2 (r2)** | `benchmark_*_r2.json` | top 10 models combined | 120 |

---

## 1. Một request đi qua những gì?

```
 Request vào
      │
      ▼
 ┌─────────────┐
 │   ROUTING   │  ← coordinator: auth, session load, dispatch agent
 └─────────────┘    KHÔNG phải LLM — infrastructure thuần
      │
      ▼
 ┌─────────────┐
 │   THINKING  │  ← LLM đọc system prompt + tool schemas, quyết định gọi tool nào
 └─────────────┘    1 LLM call
      │
      ▼
 ┌─────────────┐
 │  TOOL CALL  │  ← gọi API backend (Oracle), lấy data
 └─────────────┘    nếu nhiều tool tuần tự: LLM xử lý xong mới gọi tool tiếp theo
      │
      ▼
 ┌─────────────┐
 │   RESPONSE  │  ← LLM đọc kết quả tool, sinh ra template FE
 └─────────────┘    1 LLM call nữa
      │
      ▼
 Response ra
```

**Unaccounted (~20%):** Khi gọi nhiều tool tuần tự, thời gian LLM quyết định tool tiếp theo nằm trong khoảng trống giữa `tool_total` và không được capture riêng.

---

## 2. Phase breakdown — baseline vs v2

| Phase | Baseline avg | Baseline p50 | Baseline p95 | Baseline p99 |
|-------|--------------|--------------|--------------|--------------|
| **total** | 13.53s | 13.22s | 17.79s | 18.83s |
| routing | 2.84s | 2.69s | 4.00s | 5.35s |
| thinking | 3.53s | 3.16s | 5.47s | 5.75s |
| tool_total | 1.18s | 0.40s | 3.66s | 4.53s |
| response | 3.28s | 3.09s | 5.01s | 5.40s |

| Phase | v2 avg | v2 p50 | v2 p95 | v2 p99 | Δ avg |
|-------|--------|--------|--------|--------|-------|
| **total** | 11.55s | 11.67s | 14.90s | 15.66s | **−2.0s** |
| routing | 2.27s | 2.10s | 3.50s | 5.02s | −0.6s |
| thinking | 3.13s | 2.86s | 4.95s | 6.88s | −0.4s |
| tool_total | 1.62s | 0.66s | 4.43s | 4.66s | +0.4s |
| response | 3.35s | 3.43s | 5.23s | 5.92s | ≈ 0 |

---

## 3. Phân tích so sánh

### Response phase không đổi (3.28s vs 3.35s)

Đây là điểm quan trọng nhất: **model tốt hơn không làm response phase nhanh hơn**. v2 dùng các model top nhưng response vẫn ~3.3–3.4s — bằng với baseline. Nguyên nhân không phải model mà là **context size**: LLM phải đọc toàn bộ raw JSON từ Oracle (nhiều fields dư) trước khi render template.

→ Tối ưu response không phải bằng cách đổi model, mà bằng cách **trim tool output** trước khi đưa vào LLM.

### Thinking nhanh hơn 0.4s ở v2

Top models (v2) quyết định tool call nhanh hơn 0.4s avg. Nhưng p99 của v2 (6.88s) lại cao hơn baseline (5.75s) — một số TCs phức tạp làm model "suy nghĩ" lâu hơn.

### Routing nhanh hơn 0.6s ở v2 — không liên quan model

Routing không có LLM nào, nhưng v2 vẫn nhanh hơn 0.6s. Khả năng cao do thời điểm chạy khác nhau (server load), không phải do model. Không nên kết luận routing đã được cải thiện.

### Tool_total cao hơn ở v2 (+0.4s avg)

v2 chạy nhiều TC phức tạp hơn (67 TCs vs 35 TCs), có nhiều cases gọi nhiều tool hơn, nên wall time dài hơn. p95/p99 tương đương nhau.

---

## 4. Per-tool latency

| Tool | Baseline n | Baseline avg | Baseline p99 | v2 n | v2 avg | v2 p99 |
|------|------------|--------------|--------------|------|--------|--------|
| `get_my_cars_tool` | 20 | 0.44s | 1.45s | 9 | 0.26s | 0.27s |
| `get_orders_of_user_tool` | 8 | 0.62s | 0.73s | 71 | 0.56s | 1.39s |
| `get_final_price_tool` | 5 | 0.54s | 0.57s | 40 | 0.38s | 0.44s |
| `get_store_list_tool` | 4 | 0.37s | 0.48s | 16 | 0.21s | 0.43s |
| `get_order_status_tool` | 7 | 0.29s | 0.33s | 42 | 0.27s | 0.35s |
| `get_available_coupons_tool` | 1 | 0.32s | — | 9 | 0.49s | 2.30s |

`get_my_cars_tool` nhanh hơn hẳn ở v2 (0.26s vs 0.44s) — có thể do thời điểm chạy hoặc TCs khác nhau, cần kiểm tra thêm.

`get_available_coupons_tool` ở v2 có p99=2.30s (n=9, còn ít sample) — variance lớn, đáng theo dõi.

---

## 5. Ưu tiên optimize

| # | Vấn đề | Ảnh hưởng | Baseline | v2 | Hướng xử lý |
|---|--------|-----------|----------|-----|-------------|
| **1** | Response không giảm dù đổi model tốt hơn | **Mọi request có tool** | 3.28s | 3.35s | Trim tool output trước khi đưa vào LLM — chỉ giữ fields cần thiết |
| **2** | Thinking chiếm 26% tổng thời gian | **Mọi request** | 3.53s | 3.13s | Rút ngắn system prompt; giảm số tool schema; tách agent nhỏ hơn |
| **3** | Routing ~2.3–2.8s, tail p99 > 5s | **Mọi request** | 2.84s | 2.27s | Profile coordinator để tìm bottleneck: session init, Qdrant warmup, agent loading |
| **4** | Tool_total tail (p95 ~3.7–4.4s) | Tool-heavy requests | p95=3.66s | p95=4.43s | Batch hoặc song song hóa multi-tool calls |
| **5** | `get_available_coupons_tool` p99=2.30s | Coupon-related TCs | — | 2.30s | Cache hoặc tối ưu query; cần thêm sample để xác nhận |

**Thứ tự làm:** #1 và #2 trước — cả hai ảnh hưởng đến mọi request, cải thiện được ngay bằng code (không cần infra). #3 cần profile thực tế trên server. #4 và #5 chỉ cải thiện tail.

**Kỳ vọng nếu làm #1 + #2:** Cắt được 2–4s khỏi avg total, đưa p50 từ ~11–13s xuống ~8–10s.
