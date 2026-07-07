# LLM-first 챗봇 작업 트랙 정리

## 문서 목적

이 문서는 앞으로 진행할 작업을 두 갈래로 명확히 분리하기 위한 문서입니다.

1. 기존 코드 리팩토링
2. 기존 API/tool/template만 재사용하는 신규 LLM-first MVP 챗봇

현재 우선순위는 2번입니다. 1번은 참고용 또는 긴급 버그 수정용으로만 사용합니다.

## 공통 제품 목표

챗봇은 사용자의 현재 질문을 LLM이 이해하고, 부족한 정보를 자연스럽게 물어보고, 필요한 API/tool을 실행한 뒤,
DB/API 결과에 근거해서 답변해야 합니다.

아래 방식은 목표에서 제외합니다.

- 정규식으로 intent를 확정하는 방식
- 키워드 기반으로 tool을 바로 실행하는 방식
- 과거 slot/context가 현재 질문을 강제로 덮는 방식
- 기존 flow fallback으로 자동 복귀하는 방식
- template mapper에서 고정 문구를 계속 조립하는 방식

챗봇이 지원해야 하는 주요 기능은 아래와 같습니다.

- 매장 조회
- 가격/쿠폰/할인 조회
- 재고/장착 가능 여부 조회
- 상품 추천
- 상품 설명
- FAQ/고객지원
- 퀵 쇼핑/주문서 초안 생성
- 구매/예약 흐름의 multi-turn 상태 관리
- 주문/장바구니/쿠폰발급/문의등록 같은 side-effect 실행 안전장치

## 트랙 1: 기존 코드 리팩토링

### 목표

현재 운영 중인 legacy 챗봇 런타임을 조금씩 개선하는 작업입니다.

이 방식은 기존 `chat.py`, domain agent, `TurnContract`, `FlowState`, `template_mapper`, policy layer를 유지하면서
문제가 되는 경계를 조금씩 정리합니다.

### 그대로 사용하는 기존 구조

- `TStationChatServiceV2`
- `StreamingMultiAgentCoordinator`
- 기존 domain agent
- 기존 `TurnContract`
- 기존 `flow_controller.py`
- 기존 `flow_state.py`
- 기존 `slot_fill_controller.py`
- 기존 `template_mapper.py`
- 기존 QC/policy guard

### 주요 작업 내용

- 과거 context가 현재 턴 intent를 덮지 못하게 수정
- 구매/예약 흐름의 기준을 `FlowState`로 통일
- `ConversationSlots`, `merged_slots`는 현재 턴 evidence로만 사용
- 정규식은 사이즈/수량/날짜 같은 구조화 값 추출용으로만 제한
- side-effect tool은 명시 확인 전 실행 금지
- 가격/재고/스케줄/쿠폰 응답은 FactBundle + LLM composer로 확대
- `template_mapper.py`의 고정 assistantResponse 축소
- 새 분기나 helper를 `chat.py`에 계속 추가하지 않기
- FIX_LOG에 남은 실패 계열을 회귀 테스트로 고정

### 장점

- 운영 중인 기존 기능을 유지하면서 조금씩 개선 가능
- 작은 단위로 배포 가능
- 긴급 버그 수정에는 적합

### 단점

- 느림
- 기존 rule/regex/fallback과 새 정책이 계속 충돌함
- `chat.py`가 계속 병목이 됨
- 기존 intent, pending state, fallback 경로가 계속 살아 있음
- 새 guard가 또 다른 룰엔진이 될 위험이 큼

### 사용 기준

이 트랙은 긴급 운영 버그 수정이나, 신규 MVP에 필요한 API/tool/template/safety logic을 추출할 때만 사용합니다.

## 트랙 2: 신규 LLM-first MVP 챗봇

### 목표

`origin/stg` 코드를 기반으로 새 챗봇 런타임을 만듭니다. 이 작업은 기존 챗봇 리팩토링이 아닙니다.

신규 런타임에서 재사용하는 것은 아래로 제한합니다.

- 기존 BE API
- 기존 tool 내부 API 호출 로직
- 기존 FE SSE/template 계약
- 기존 인증/session/logging 인프라
- FIX_LOG에 정리된 고위험 작업 안전 정책

신규 런타임에서 사용하지 않는 것은 아래입니다.

- 기존 agent routing
- 기존 legacy flow fallback
- 정규식 기반 intent routing
- `pending_intent`, `goal_type` 기반 action 결정
- 기존 slot-fill heuristic을 action authority로 사용하는 구조
- 기존 template mapper의 고정 답변 문구
- 기존 `chat.py` orchestration을 메인 실행 경로로 사용하는 구조

### 목표 구조

```text
Chat endpoint
-> 신규 LLM-first runtime
   -> Leading Planner
   -> State Manager
   -> AF Executor
   -> Tool Capability Registry
   -> Tool Executor
   -> Fact Bundle Builder
   -> LLM Composer
   -> Template/SSE Adapter
   -> QC Boundary
```

### 간소화된 Agent 역할

#### Leading Planner

LLM 기반의 현재 턴 판단 담당입니다.

- 현재 사용자 질문 이해
- 필요한 Agent Flow 선택
- 이미 알고 있는 정보와 부족한 정보 구분
- 답변할지, 질문할지, 조회할지, 구매 흐름을 이어갈지 판단
- tool 직접 실행은 하지 않음

#### AF Executor

Planner가 선택한 Agent Flow를 실제 tool 실행 계획으로 바꾸는 역할입니다.

- Agent Flow를 tool subtask로 변환
- Tool Capability Registry로 required input 확인
- read-only tool 실행
- side-effect tool 차단 또는 확인 요청

#### QC Boundary

최종 답변이 tool fact와 충돌하지 않는지 확인합니다.

- 가격/재고/스케줄/주문/쿠폰/매장 정보 검증
- tool 결과 없는 단정 차단
- 주문/예약/장바구니/문의등록 완료 표현 차단
- intent 재분류는 하지 않음

## MVP Agent Flow 범위

### 1. Store AF

목적:

- 사용자 위치, 관심 지역, 매장명 기반 매장 조회
- 장착 가능 매장과 방문에 필요한 정보 제공

재사용 tool:

- `search_place_tool`
- `get_nearby_stores_tool`
- `search_stores_tool`
- `search_stores_complex_tool`
- `get_store_detail_tool`

출력:

- `location` template
- LLM이 작성한 매장 요약 답변

MVP 규칙:

- 매장이 여러 개면 임의로 `shop_id`를 확정하지 않습니다.
- 반드시 매장 목록을 보여주고 사용자가 선택하게 합니다.

### 2. Price AF

목적:

- 기본 판매가, 혜택가, 쿠폰, 할인, 최종 예상 부담 금액 안내

재사용 tool:

- `get_final_price_tool`
- `get_my_coupons_tool`
- `get_coupon_applicable_products_tool`
- `get_product_promotions_tool`

출력:

- LLM이 작성한 가격/할인 설명
- 필요 시 `priceSummary`

MVP 규칙:

- 가격, 할인, 쿠폰 정보는 tool fact가 있을 때만 답변합니다.
- tool 결과 없는 가격 단정은 금지합니다.

### 3. Inventory AF

목적:

- 온라인/오프라인 재고와 즉시 장착 가능 여부 확인

재사용 tool:

- `transaction_store_preview_tool`
- `get_store_inventory_tool`
- `get_logistics_inventory_tool`

출력:

- 가능한 매장 후보 `location` template
- 재고/장착 가능 여부 요약

MVP 규칙:

- 상품, 수량, 지역/매장이 있는 경우 `transaction_store_preview_tool`을 우선 사용합니다.

### 4. Quick Shopping AF

목적:

- 구매에 필요한 정보를 모아 주문서 초안을 생성합니다.

필수 정보 순서:

1. 상품
2. 수량
3. 매장 또는 지역
4. 스케줄
5. 가격

재사용 tool:

- `transaction_store_preview_tool`
- `get_store_schedule_tool`
- `get_final_price_tool`

출력:

- 부족한 정보 질문
- `location`
- `datepick`
- `preOrder`

MVP 규칙:

- 첫 MVP에서는 `quick_order_tool`, `save_to_cart_tool`을 바로 실행하지 않습니다.
- 주문/장바구니 실행은 side-effect confirmation이 완성된 뒤에만 허용합니다.

### 5. Product Recommendation AF

목적:

- 사이즈, 차량, 가격대, 성능 선호도 기반 타이어 추천

재사용 tool:

- `get_products_recommendations_tool`
- `search_product_tool`
- `get_best_selling_products_tool`
- `get_newest_products_tool`

출력:

- `product` template
- LLM이 작성한 추천 이유

MVP 규칙:

- 타이어 사이즈나 차량 정보가 없으면 먼저 물어봅니다.
- 근거 없는 광범위 추천은 하지 않습니다.

### 6. Product Description AF

목적:

- 상품 특장점, 기술력, 성능, 리뷰, 순위, 비교 설명

재사용 tool:

- `search_product_tool`
- `search_product_summary_tool`
- `get_product_description_tool`
- `compare_discount_tool`

출력:

- LLM이 작성한 상품 설명
- 필요 시 상품 카드

MVP 규칙:

- 상품 성능/특징은 product fact 또는 description fact 안에서만 설명합니다.

### 7. FAQ AF

목적:

- 회원, 포인트, 서비스 정책, 보증, 반품, 교환, 결제 등 일반 문의 처리

재사용 tool:

- `search_faq_hybrid_tool`
- `search_faq_rag_tool`
- `get_faq_tool`
- `get_card_installments_tool`

출력:

- FAQ/RAG 기반 답변
- 필요 시 상담/1:1 문의 안내

MVP 규칙:

- 사용자가 명시적으로 상담원, 1:1 문의, 접수를 요청하지 않으면 FAQ/RAG 답변을 먼저 시도합니다.

## MVP에서 후순위로 미루는 AF

### Order / Delivery AF

나중에 재사용할 tool:

- `get_order_status_tool`
- `get_orders_of_user_tool`
- `get_my_reservations_tool`

후순위 이유:

- 개인 주문/예약 정보는 인증, 개인정보, 주문번호 매칭 정책이 더 필요합니다.

### Product Compatibility AF

나중에 재사용할 tool:

- `get_my_cars_tool`
- `get_user_vehicles_tool`
- `check_compatibility_tool`
- `search_car_model_tool`

후순위 이유:

- 차량번호, 소유자명, 차량 선택 UI가 얽혀 있어 하루 MVP 범위가 커집니다.

### Fallback / Escalation AF

신규 MVP에는 legacy fallback이 없습니다.

- 이해 실패 시 clarification
- 지원 불가 기능은 지원 불가 안내
- 명시적 상담 요청 시에만 escalation flow
- `transfer_to_qna_tool`은 side-effect이므로 명시 확인 전 실행 금지

## 기존 프로젝트에서 재사용할 것

### Runtime 계약

- 채팅 요청 형식
- SSE event 형식
- session/message ID
- FE template payload schema
- 인증/member context
- Langfuse/Docker logging 인프라

### Tool/API 자산

- 기존 agent tool 함수
- 기존 BE API client
- 안전한 기존 `tool_cache`
- 결과 정규화/helper는 필요한 부분만 참고 또는 얇게 재사용

### FIX_LOG 기반 안전 정책

- 현재 턴 intent 우선
- context는 action을 시작할 수 없음
- regex는 LLM planner를 덮을 수 없음
- side-effect tool은 명시 확인 필요
- 상품/사이즈/수량/매장/스케줄 변경 시 종속 상태 초기화
- 매장이 여러 개면 사용자 선택 전 매장 확정 금지
- 가격/쿠폰/재고/스케줄/주문 정보는 tool fact 기반으로만 답변
- FAQ 근거 답변을 상담 연결보다 먼저 시도
- 결제수단 변경, 임의 쿠폰 발급 등 API가 없는 기능을 완료했다고 말하지 않음

## 신규 MVP State Model

```json
{
  "conversation_summary": "",
  "commerce_state": {
    "product": {
      "goods_no": null,
      "product_name": null,
      "tire_size": null
    },
    "quantity": null,
    "store": {
      "shop_id": null,
      "shop_name": null,
      "region": null
    },
    "schedule": {
      "date": null,
      "time": null
    },
    "price": {
      "final_price": null,
      "source": null
    },
    "status": "collecting_info"
  },
  "last_facts": {}
}
```

상태 초기화 규칙:

- 상품 변경: 수량, 매장, 스케줄, 가격 초기화
- 타이어 사이즈 변경: 상품, 수량, 매장, 스케줄, 가격 초기화
- 수량 변경: 매장, 스케줄, 가격 초기화
- 매장 변경: 스케줄, 가격 초기화
- 스케줄 변경: 가격 초기화

## 하루 MVP 구현 순서

### 오전

1. 신규 runtime package 생성
2. chat endpoint에서 신규 runtime 진입점 연결
3. Leading Planner schema/prompt 작성
4. Redis 기반 최소 state load/save 구현

### 오후

1. MVP tool용 Tool Capability Registry 구현
2. Store, Price, Inventory, Product Recommendation, Product Description, FAQ용 AF Executor 구현
3. Fact Bundle Builder 구현
4. LLM Composer 구현
5. `product`, `location`, `datepick`, text response adapter 구현

### 마감 전

1. side-effect tool hard block
2. 주요 MVP 시나리오 수동 테스트
3. 개발 서버 배포
4. Langfuse에서 planner output, selected AF, tool result, fact, final answer 확인

## 하루 MVP 성공 시나리오

- `245/45R19 타이어 추천해줘`
  - Product Recommendation AF
  - 상품 카드
  - 추천 이유 설명

- `벤투스 S2 가격 알려줘`
  - 상품 resolve
  - Price AF
  - 가격/할인 설명

- `판교 근처 장착 가능한 매장 보여줘`
  - Store/Inventory AF
  - 매장 카드

- `오늘 가능한 시간 있어?`
  - 선택된 매장 기준 schedule 조회
  - `datepick`

- `주문 진행해줘`
  - Quick Shopping AF
  - 부족한 정보 수집 또는 `preOrder`
  - 실제 주문 생성은 하지 않음

- 구매 중 `적용된 할인이 뭐야?`
  - Price AF side question
  - preOrder 강제 전환 금지

- `계속 진행해줘`
  - 필요한 state가 있을 때만 Quick Shopping AF 재개

## MVP 1차 개발 완료 후 남아있는 작업

하루 MVP는 신규 LLM-first runtime의 최소 수직 흐름을 만드는 단계입니다. 1차 완료 후에도 아래 작업은 남습니다.

### 1. Quick Shopping AF 완성

1차 MVP에서는 주문서 초안 또는 `preOrder`까지만 처리합니다.

남은 작업:

- `quick_order_tool` 실행 전 명시 확인 flow 구현
- `save_to_cart_tool` 실행 전 명시 확인 flow 구현
- 주문/장바구니 실행 결과를 `orderComplete`, `cartComplete`로 연결
- 주문 실행 전 상품, 수량, 매장, 일정, 가격 최종 요약 검증
- 주문 실행 실패 시 재시도/수정/상담 안내 처리

### 2. Order / Delivery AF 추가

1차 MVP에서는 주문/배송 조회를 후순위로 둡니다.

남은 작업:

- `get_orders_of_user_tool` 연결
- `get_order_status_tool` 연결
- `get_my_reservations_tool` 연결
- 짧은 주문번호 suffix 매칭 정책 구현
- 주문 후보가 여러 개일 때 사용자 선택 UI 연결
- 개인 주문/예약 정보 응답에 대한 QC 강화

### 3. Product Compatibility AF 추가

1차 MVP에서는 차량 호환 검증을 제외합니다.

남은 작업:

- `get_my_cars_tool` 연결
- `get_user_vehicles_tool` 연결
- `search_car_model_tool` 연결
- `check_compatibility_tool` 연결
- 차량번호/소유자명/차량 선택 상태 관리
- 상품 선택 후 차량 호환 검증 flow 연결

### 4. Fallback / Escalation AF 정리

legacy fallback은 사용하지 않지만, 신규 runtime 내부의 예외 처리는 필요합니다.

남은 작업:

- planner 이해 실패 시 clarification 품질 개선
- 지원 불가 기능 안내 템플릿 정리
- `transfer_to_qna_tool` 명시 확인 flow 구현
- 상담/1:1 문의 요청과 일반 FAQ 질문 구분
- FAQ 답변 실패 후 escalation 안내 기준 정리

### 5. Multi-tool planning 고도화

1차 MVP는 핵심 조회 tool 중심으로 시작합니다.

남은 작업:

- 복합 질문의 subtask dependency 처리 강화
- 독립 조회 병렬 실행
- partial failure 응답 품질 개선
- tool result conflict 감지
- 여러 AF 결과를 하나의 FactBundle로 합치는 기준 정리

예시:

- `가격이랑 판교 근처 오늘 장착 가능한 곳 알려줘`
- `이 상품 할인 적용가랑 재고 있는 매장 같이 보여줘`
- `추천 상품 중 제일 싼 거랑 오늘 가능한 매장 알려줘`

### 6. State Manager 안정화

1차 MVP의 state는 최소 구조입니다.

남은 작업:

- Redis 저장 스키마 버전 관리
- session history 기반 conversation summary 생성
- commerce state와 semantic memory 분리 강화
- dormant purchase flow 재개 조건 정리
- UI action으로 들어온 상품/매장/스케줄 선택 patch 처리
- 기존 `/messages/append` 이벤트와 신규 state 동기화
- stale state 감지 trace 추가

### 7. Template/SSE Adapter 확대

1차 MVP는 `product`, `location`, `datepick`, text 중심입니다.

남은 작업:

- `preOrder` payload 완성
- `priceSummary` payload 완성
- `voucher` payload 연결
- `listCar` payload 연결
- `orderComplete`, `cartComplete` payload 연결
- template과 composer 자연어 답변 충돌 방지
- quickReply CTA metadata 정리

### 8. FactBundle/QC 강화

1차 MVP에서는 최소 fact grounding만 합니다.

남은 작업:

- 가격 fact schema 정교화
- 쿠폰 fact schema 정교화
- 재고/물류/오늘장착 fact schema 정교화
- 스케줄 fact schema 정교화
- order/reservation fact schema 추가
- composer 응답과 fact mismatch 자동 검출
- 금액/날짜/매장명/상품명 hallucination 검출

### 9. LLM Composer 품질 개선

1차 MVP는 고정 답변 제거와 자연어 응답이 목표입니다.

남은 작업:

- 도메인별 composer instruction 분리
- 가격/쿠폰 답변 스타일 정리
- 상품 추천 이유 표현 품질 개선
- 매장/재고/스케줄 답변 표현 정리
- FAQ 답변에서 근거와 한계 표현 개선
- 카드 UI가 있는 경우 text 길이와 역할 조정

### 10. 테스트/검증 보강

1차 MVP는 수동 테스트 중심입니다.

남은 작업:

- planner schema 단위 테스트
- AF 선택 테스트
- tool registry validation 테스트
- state invalidation 테스트
- FactBundle 변환 테스트
- composer grounding 테스트
- side-effect confirmation 테스트
- FIX_LOG 기반 회귀 시나리오 자동화
- Langfuse trace 기반 실패/성공 비교 절차 정리

### 11. 운영 배포 준비

1차 MVP 개발 서버 배포 이후 운영 반영 전 필요한 작업입니다.

남은 작업:

- dev trace 기준 주요 시나리오 검증
- latency 측정
- tool 호출 수 측정
- LLM 호출 수 측정
- 장애 응답 문구 정리
- timeout/retry 정책 정리
- error logging/alert 기준 정리
- 운영 배포 전 rollback 전략 정리

## 최종 결정

현재 구현 우선순위는 트랙 2입니다.

트랙 1과 트랙 2를 섞지 않습니다. 기존 리팩토링 코드는 참고용으로만 사용하고, 신규 MVP는 기존 API wrapper,
template schema, 운영 안전 정책만 가져와 별도 LLM-first runtime으로 구현합니다.
