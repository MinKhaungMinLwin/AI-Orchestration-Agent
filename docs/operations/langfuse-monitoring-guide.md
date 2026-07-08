# Langfuse 운영 모니터링 가이드

이 문서는 T-Station AI Chat V3 운영 모니터링과 3개월 운영 지원 리포트 작성을 위한 Langfuse 사용 방법을 정리한다.

## 목적

- 고객사/운영자가 대화 처리 상태를 빠르게 확인한다.
- 운영 지원자가 실패, fallback, QC 보정 케이스를 추적한다.
- 주간 운영 리포트를 반복 가능한 방식으로 작성한다.

## 기본 원칙

운영 모니터링은 `customer_monitoring` trace를 기준으로 본다.

```text
customer_monitoring
```

`customer_monitoring`은 사용자 한 턴을 아래 구조로 요약한다.

```text
Domain -> AF -> Tool -> Status
```

예:

```text
TRANSACTION -> Store AF -> get_store_schedule_tool -> success
```

router, tool loop, template builder, QC trace는 내부 디버깅용이다. 이 trace들은 프롬프트, tool schema, 원본 tool
payload를 포함할 수 있으므로 고객사 운영 리뷰의 기본 화면으로 쓰지 않는다.

## 대화 찾는 방법

1. 챗봇 로그 또는 SSE 첫 이벤트에서 `session_id`를 확인한다.
2. Langfuse에서 `tstation-ai` 프로젝트로 이동한다.
3. `Traces` 화면을 연다.
4. 아래 조건으로 필터링한다.

```text
Session ID = <session_id>
```

5. trace 이름이 `customer_monitoring`인 항목을 연다.

## 핵심 확인 필드

`customer_monitoring` trace 상세의 `metadata`를 확인한다.

| 필드 | 의미 |
| --- | --- |
| `session_id` | 대화 세션 ID |
| `message_id` | 사용자 메시지 ID. 특정 발화와 trace를 매칭할 때 사용 |
| `user_id` | 회원/사용자 ID |
| `route_domains` | router가 판단한 도메인 |
| `route_intents` | router가 판단한 세부 의도 |
| `primary_domain` | 해당 턴의 대표 도메인 |
| `af_path` | 해당 턴에서 거친 AF 목록 |
| `primary_af` | 해당 턴의 대표 AF |
| `tool_path` | 실제 호출된 tool 목록 |
| `primary_tool` | 최종 결과 기준 대표 tool |
| `tool_count` | tool 호출 수 |
| `result_count` | 대표 tool 결과 개수. 가능한 경우만 표시 |
| `final_template` | FE에 내려간 최종 템플릿 |
| `final_status` | 처리 상태: `success`, `partial_success`, `fallback`, `error` |
| `error_reason` | 운영 리포트용 사유: `none`, `tool_error`, `runtime_error`, `tool_no_results`, `fallback_response`, `quick_reply_fallback`, `qc_corrected` |
| `latency_ms` | 해당 턴 처리 시간 |
| `assistant_response` | 사용자에게 최종 노출된 답변 |

## 자주 쓰는 필터

### 상태별

```text
status:success
status:partial_success
status:fallback
status:error
```

운영 점검에서는 아래 3개를 우선 확인한다.

```text
status:error
status:fallback
status:partial_success
```

### 도메인별

```text
domain:discovery
domain:transaction
domain:support
```

### AF별

```text
af:store
af:price
af:inventory
af:order_delivery
af:quick_shopping
af:product_compatibility
af:product_recommendation
af:product_description
af:faq
af:fallback_escalation
```

### Tool별

예:

```text
tool:search_product_tool
tool:get_final_price_tool
tool:get_store_schedule_tool
tool:present_order_preview_tool
tool:quick_order_tool
tool:search_faq_hybrid_tool
tool:transfer_to_qna_tool
```

### Template별

예:

```text
template:product
template:location
template:datepick
template:preorder
template:ordercomplete
template:quickreply
template:qnacomplete
```

### Intent별

예:

```text
intent:place_order
intent:product_search
intent:tire_recommend
intent:store_search
intent:quick_order_reservation_schedule_select
```

## AF 기준

| AF | 도메인 | 대표 tool |
| --- | --- | --- |
| Store AF | TRANSACTION | `search_stores_tool`, `get_store_list_tool`, `get_store_schedule_tool`, `get_nearby_stores_tool` |
| Price AF | TRANSACTION | `get_final_price_tool`, `compare_discount_tool`, `get_my_coupons_tool` |
| Inventory AF | TRANSACTION | `get_logistics_inventory_tool`, `get_store_inventory_tool` |
| Order / Delivery AF | TRANSACTION | `get_orders_of_user_tool`, `get_order_status_tool`, `get_my_reservations_tool` |
| Quick Shopping AF | TRANSACTION | `present_order_preview_tool`, `save_to_cart_tool`, `quick_order_tool` |
| Product Compatibility AF | DISCOVERY | `check_compatibility_tool`, `get_user_vehicles_tool`, `get_my_cars_tool` |
| Product Recommendation AF | DISCOVERY | `search_product_tool`, `get_products_recommendations_tool`, `get_best_selling_products_tool` |
| Product Description AF | DISCOVERY | `get_product_description_tool`, event/deal 관련 tool |
| FAQ AF | SUPPORT | `search_faq_hybrid_tool`, 보증/정비 FAQ 관련 tool |
| Fallback / Escalation AF | SUPPORT | `transfer_to_qna_tool`, `escalate_tool` |

## 일일 점검 절차

1. Langfuse에서 `customer_monitoring` trace만 확인한다.
2. 아래 상태를 먼저 필터링한다.

```text
status:error
status:fallback
status:partial_success
```

3. 각 케이스에서 아래 정보를 기록한다.

```text
session_id
message_id
trace_id
input
primary_af
tool_path
final_status
error_reason
assistant_response
```

4. 원인 분석이 필요한 경우에만 같은 session의 router/tool/QC trace를 추가로 확인한다.

## 주간 리포트 작성

주간 집계는 스크립트로 생성한다.

```bash
cd /home/kongg/tstation/code/tstation-ai
uv run python app/tstation-ai/scripts/langfuse_weekly_report.py --days 7
```

CSV도 함께 저장하려면:

```bash
uv run python app/tstation-ai/scripts/langfuse_weekly_report.py --days 7 --csv weekly.csv
```

기간을 직접 지정하려면:

```bash
uv run python app/tstation-ai/scripts/langfuse_weekly_report.py --from 2026-07-01 --to 2026-07-08
```

필요한 환경변수:

```text
LANGFUSE_HOST
LANGFUSE_PUBLIC_KEY
LANGFUSE_SECRET_KEY
```

개발서버에서는 AI 컨테이너 내부에서 실행하거나, 컨테이너와 동일한 Langfuse 환경변수를 로드한 뒤 실행한다.

## 주간 리포트 템플릿

```text
T-Station AI 챗봇 운영 모니터링 주간 리포트

기간:
환경:
총 customer_monitoring trace 수:
정상 처리율:
평균 latency:
P95 latency:

1. 요약
- 주요 사용 AF:
- 주요 이슈 유형:
- 조치 완료 항목:
- 모니터링 중인 항목:

2. 상태별 현황
- success:
- partial_success:
- fallback:
- error:

3. AF별 현황
- Store AF:
- Price AF:
- Inventory AF:
- Order / Delivery AF:
- Quick Shopping AF:
- Product Compatibility AF:
- Product Recommendation AF:
- Product Description AF:
- FAQ AF:
- Fallback / Escalation AF:

4. 주요 검토 케이스
- session_id:
- message_id:
- trace_id:
- 증상:
- 원인:
- 조치:
- 상태:

5. 다음 주 관찰 포인트
- 반복 fallback 패턴:
- latency가 높은 AF:
- 사용자 응답 품질 이슈:
```

## 상태 해석 기준

| 상태 | 의미 | 조치 |
| --- | --- | --- |
| `success` | tool/template 흐름이 정상 완료됨 | 별도 조치 없음. 답변 품질 이슈가 있으면 샘플링 |
| `partial_success` | 답변은 생성됐지만 QC가 보정함 | prompt/tool 데이터 불일치 여부 확인 |
| `fallback` | 결과 없음 또는 fallback 응답 사용 | missing slot, no-result tool, 미지원 요청 여부 확인 |
| `error` | tool 또는 runtime 오류 | 내부 trace와 서버 로그 확인 |

## 고객사 안내 문구

고객사에는 아래처럼 안내한다.

```text
운영 모니터링은 Langfuse의 customer_monitoring trace를 기준으로 확인합니다.
session_id로 검색하면 각 사용자 턴이 어떤 Domain, AF, Tool을 거쳤고,
최종 상태가 success/fallback/error 중 무엇인지 확인할 수 있습니다.
상세 원인 분석이 필요한 경우 내부 운영자가 router/tool/QC trace를 추가 확인합니다.
```

## 주의사항

- 고객사 공유 기준은 `customer_monitoring`이다.
- router/tool/QC trace는 내부 분석용이다.
- raw prompt나 raw tool payload를 고객사 리포트에 그대로 옮기지 않는다.
- 리포트에는 `session_id`, `message_id`, `trace_id`, `primary_af`, `final_status`, `error_reason`, 조치 내역 중심으로 기록한다.

