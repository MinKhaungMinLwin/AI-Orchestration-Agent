# Policy Engine Refactor Plan

## 목적

현재 T-Station AI는 사용자 의도 판정, 슬롯 유지, 도구 선택, 도구 결과 해석, UI 템플릿 선택, 답변 문구 생성을 agent prompt와 후처리 로직이 함께 처리한다. 이 구조에서는 운영 이슈가 발생할 때마다 prompt 또는 `template_mapper.py`에 예외를 추가하게 되고, 하나의 케이스를 고치면 다른 케이스의 의도/템플릿이 밀리는 회귀가 반복된다.

이 리팩토링의 목표는 도메인별 정책을 코드 계약으로 분리해 다음 흐름을 고정하는 것이다.

```text
User message
→ Intent Frame
→ Required Slot 판단
→ Tool Plan
→ Response Policy
→ Template/Answer 생성
```

LLM은 정책을 판단하는 주체가 아니라, 코드가 결정한 `ResponseDecision` 범위 안에서 자연어를 작성하는 역할로 점진적으로 좁힌다.

## 현재 브랜치 기준

- 작업 브랜치: `refactor/policy-engine`
- 병렬 작업 브랜치:
  - `refactor/policy-engine-core` at `../tstation-ai-policy-core`
  - `refactor/policy-engine-discovery` at `../tstation-ai-policy-discovery`
  - `refactor/policy-engine-transaction` at `../tstation-ai-policy-transaction`
- 포함된 선행 작업:
  - `reservation_template_policy.py` 기반 예약/매장 템플릿 정책 모듈화
  - 예약/매장 후속 보정 커밋 전체
  - `eval/current_review_tc_notes.md` 리뷰 TC overlay
- dev AI 서버는 현재 이 브랜치를 체크아웃해 테스트 가능하다.

## 진행 현황 (2026-05-23)

- Phase 1 Discovery: 1차 runtime 연결 완료.
  - 조건 추천, 상품명 검색, 상품 상세 속성, 상품 비교 응답을 `discovery_intent_policy.py` / `discovery_response_policy.py` / `template_mapper.py`로 일부 고정했다.
  - 대표 검증 TC: `TC-004`, `TC-006`, `TC-016`, `TC-017`, `TC-021`, `TC-026`, `TC-032`, `TC-044`, `TC-047`, `TC-215`, `TC-216`.
- Phase 2 Transaction/Reservation: reservation template policy와 재고/location 우선순위 1차 runtime 연결 완료.
  - `reservation_template_policy.py` 기반 datepick 보정은 dev 배포 완료.
  - `get_store_inventory_tool` 결과가 없으면 no-stock quickReply, 재고가 있으면 같은 턴 store list를 재고 매장으로 필터링하도록 연결했다.
  - 대표 검증 TC: `TC-003`, `TC-031`, `TC-049`, `TC-058`, `TC-219`, `TC-231`, `TC-233`.
- Phase 3 Support/Price: 정책 계약과 일부 runtime guard 연결 완료.
  - 쿠폰 임의 발급, 만료 쿠폰 원복, 개인 연락처, 상담원 연결의 `support_response_policy.py` 계약은 작성됨.
  - 쿠폰 발급 guard와 만료 쿠폰 qnaComplete 문구 보정은 runtime에 이미 일부 반영됨.
  - 아직 가격/쿠폰 적용 가능 상품/중복 적용/존재하지 않는 혜택 전체는 정책 엔진에 완전히 연결되지 않았다.
- Phase 4 테스트 체계: 정책 단위 테스트와 template mapper 회귀 테스트 운영 중.
  - 현재 최소 정책 묶음은 `138 passed, 1 warning` 기준으로 관리한다.
  - 실제 dev SSE 검증은 JWT/BE 권한 상태에 따라 일부 Transaction tool 실행이 제한될 수 있다.
- 성능 회귀 확인: 리팩토링 후 일부 응답이 2~3배 지연되는 케이스가 확인됐다.
  - 기준 trace: `1398f7d14a70422c92e81a8c8c48a9de`
  - 질문: `키너지 ST AS 2개 서초점 오늘 장착 가능?`
  - 총 지연 `34.55s`, first visible `34.55s`.
  - 병목은 DB/tool 이 아니라 LLM 호출이다. `search_product_tool` 자체는 `0.09s`였고,
    Discovery tool 이후 LLM 재호출이 `23.66s`, Transaction 선행 호출이 약 `3.11s`였다.
  - 원인: tool 결과만으로 code mapper가 `product`/clarification template을 결정할 수 있는데도,
    agent post-tool LLM 응답을 끝까지 기다린 뒤 `_try_code_template()`가 적용된다.
  - 이 성능 회귀는 기능 회귀와 동일 수준의 차단 이슈로 본다. policy engine 완료 조건에
    latency/불필요 LLM 호출 수 검증을 포함한다.

### 다음 우선순위

1. Deterministic template fast-path 추가
   - `search_product_tool`, `get_products_recommendations_tool`, `get_my_cars_tool`,
     `transaction_store_preview_tool`, `get_store_schedule_tool`처럼 code mapper로 안전하게
     응답 가능한 tool은 tool 결과 직후 template 생성 가능 여부를 먼저 확인한다.
   - 가능하면 post-tool LLM 재호출을 생략한다. 특히 상품명+거래의도+사이즈 미확정 케이스는
     정형 clarification 문구와 product/quickReply template으로 충분히 처리 가능해야 한다.
   - 목표: 위 trace 계열에서 `latency_agent_llm_generation_ms`가 20초대로 튀지 않게 하고,
     first visible latency를 수초대로 낮춘다.
2. Cross-domain route guard 성능 보정
   - 상품명 + 거래 의도 + `goods_no` 없음이면 Discovery 상품 확인이 먼저다.
   - Transaction agent가 먼저 실행되어 `"상품을 검색하겠습니다"`만 출력하고 끝나는 preflight 낭비를 막는다.
   - Discovery 후 goods_no가 단일 확정되지 않으면 Transaction 체인은 중단하고, 사이즈/상품 선택 안내로 끝낸다.
3. Transaction intent policy 추가
   - `transaction_intent_policy.py`를 만들어 재고 확인, 매장 일정, 주문 예약, 쿠폰/가격 의도를 `IntentFrame`으로 분리한다.
   - `transaction_response_policy.py`가 현재 테스트 계약에만 머무르지 않도록 coordinator/template mapper에서 참조하게 한다.
4. Transaction runtime 확장
   - `TC-049`: 유효하지 않은 매장명에는 datepick 금지, 후보 매장 확인으로 고정.
   - `TC-058`: 12시/block slot은 datepick에서 항상 제외.
   - `TC-231/TC-233`: 상품/수량/매장이 확정된 예약 요청은 영업시간 설명 대신 schedule/datepick으로 고정하고, preOrder null 방지.
5. Price/Support policy runtime 확장
   - `TC-005`, `TC-018`, `TC-097`, `TC-101`, `TC-186`, `TC-189`, `TC-210`을 가격/쿠폰 정책으로 묶어 허위 발급/허위 혜택/무관 쿠폰 리스팅을 차단한다.
6. 실제 TC smoke 확대
   - 정상 JWT로 Discovery→Transaction 체인의 product search → inventory/store/schedule 실행까지 검증한다.
   - dev SSE 로그와 template event를 기준으로 `eval/current_review_tc_notes.md`에 확인 결과를 누적한다.
   - 기능 응답뿐 아니라 Langfuse 기준 `total latency`, `first visible latency`, `post-tool LLM 호출 수`,
     `latency_agent_llm_generation_ms`를 함께 확인한다.

## 병렬 작업 소유권

세션 간 충돌을 줄이기 위해 아래 파일 소유권을 따른다.

| 세션 | 브랜치/디렉터리 | 주 소유 범위 | 피해야 할 범위 |
|---|---|---|---|
| Core | `refactor/policy-engine-core` / `../tstation-ai-policy-core` | 공통 타입, normalizer, 테스트 fixture, 통합 연결 설계 | Discovery/Transaction 도메인별 세부 룰 |
| Discovery | `refactor/policy-engine-discovery` / `../tstation-ai-policy-discovery` | `discovery_intent_policy.py`, `discovery_response_policy.py`, Discovery policy tests | `reservation_template_policy.py`, Transaction tool flow |
| Transaction | `refactor/policy-engine-transaction` / `../tstation-ai-policy-transaction` | `reservation_template_policy.py`, `transaction_response_policy.py`, reservation/stock tests | Discovery recommendation/search 세부 룰 |

공통 호출부인 `chat.py`, `template_mapper.py`, `base_agent.py`는 충돌 가능성이 높다. 초기 작업에서는 되도록 직접 수정하지 않고, 새 policy 파일과 테스트를 먼저 만든다. 호출부 연결은 통합 단계에서 한 세션이 책임진다.

## 문제 패턴

`FIX_LOG.md`와 `eval/current_review_tc_notes.md` 기준 반복 원인은 아래로 묶인다.

| 원인군 | 증상 | 대표 TC |
|---|---|---|
| 의도와 응답 형태가 계약으로 고정되지 않음 | 사이즈 없음에도 상품 카드/가격 노출, 조건 추천이 일반 추천으로 변형 | TC-004, TC-016, TC-044 |
| 슬롯 상태와 assistant 카드 데이터가 섞임 | listCar 안의 다른 차량명, 이전 추천 결과, 이전 사이즈가 후속 질문에 섞임 | TC-007, TC-016, TC-231 |
| 상품 검색과 속성 추천 충돌 | `마일리지 타이어` 상품 검색과 `마일리지 좋은 타이어` 추천이 충돌 | TC-021, TC-215 |
| tool 이름이 응답 형태를 사실상 결정 | 사용자는 사이즈를 물었는데 generic product summary가 나감 | TC-215, TC-216 |
| 예약/매장 템플릿 우선순위 분산 | `location`, `datepick`, `quickReply`가 서로 덮어씀 | TC-003, TC-031, TC-049, TC-231 |
| 정책성 답변을 LLM이 판단 | 쿠폰 발급/만료/존재하지 않는 혜택 등에서 허위 안내 위험 | TC-186, TC-189, TC-210 |

## 설계 원칙

1. **도메인별 policy는 분리하고, 공통 타입만 공유한다.**
   - Discovery, Transaction, Support는 필요한 entity와 tool이 다르다.
   - 공통으로는 `IntentFrame`, `ToolPlan`, `ResponseDecision` 형태만 맞춘다.

2. **LLM prompt에 있는 hard policy는 코드로 옮긴다.**
   - 발급 불가, 원복 불가, 직접배송 불가, 상품명 재확인 금지, 사이즈 없을 때 카드 금지 같은 규칙은 deterministic policy로 둔다.

3. **assistant 텍스트에서 상태를 재추론하지 않는다.**
   - 확정 슬롯, 후보 슬롯, 카드 선택 payload, tool result summary를 별도 state로 유지한다.
   - assistant 카드 JSON/문구는 다음 턴의 조건 추론 source로 쓰지 않는 방향으로 줄인다.

4. **템플릿 선택은 tool 이름이 아니라 `ResponseDecision`이 결정한다.**
   - 같은 `search_product_tool` 결과라도 사용자 목적이 사이즈 질문이면 사이즈 목록, 단순 검색이면 요약, 구매 의도면 선택 카드가 될 수 있다.

5. **TC는 문구가 아니라 계약을 검증한다.**
   - 최종 문장 전체 매칭보다 intent, slot, tool, template, forbidden behavior를 검증한다.

6. **정형 응답은 LLM 완료를 기다리지 않는다.**
   - `ResponseDecision`과 tool result만으로 template/문구를 안전하게 만들 수 있으면 post-tool LLM 호출을 생략한다.
   - LLM은 정책을 정하거나 FE template을 조립하는 주체가 아니라, code path가 처리하지 못한 자연어 보완 케이스에만 사용한다.
   - 정책 리팩토링은 정확도뿐 아니라 latency 회귀 방지도 완료 조건으로 삼는다.

## 목표 구조

```text
app/tstation-ai/services/tstation/policies/
  intent_frame.py
  response_decision.py
  discovery_intent_policy.py
  discovery_response_policy.py
  transaction_intent_policy.py
  transaction_response_policy.py
  reservation_template_policy.py
  support_intent_policy.py
  support_response_policy.py
```

초기에는 모든 파일을 한 번에 만들지 않는다. Discovery를 파일럿으로 만들고, 검증 후 Transaction/Support로 확장한다.

### 공통 타입 초안

```python
@dataclass(frozen=True)
class IntentFrame:
    domain: str
    intent: str
    sub_intent: str | None
    entities: dict[str, Any]
    known_slots: dict[str, Any]
    missing_slots: list[str]
    confidence: float | None = None


@dataclass(frozen=True)
class ToolPlan:
    allowed_tools: tuple[str, ...]
    preferred_tool: str | None
    tool_args_patch: dict[str, Any]
    forbidden_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResponseDecision:
    response_shape: str
    template: str
    required_slots: tuple[str, ...]
    forbidden_behaviors: tuple[str, ...]
    assistant_guidance: str
```

## Phase 1: Discovery Policy 파일럿

### 범위

상품 검색/추천에서 반복적으로 깨진 아래 축을 먼저 코드화한다.

- 상품 검색 vs 속성 추천
- 마일리지 상품명 vs 마일리지 속성
- 윈터/여름/사계절/올웨더 조건 유지
- 퍼포먼스/정숙성/흡음재/EV 조건 매핑
- 사이즈 있음/없음에 따른 응답 형태
- 상품 검색 결과를 사용자 목적에 맞춰 사이즈 목록/상품 요약/상품 카드로 분기

### 관련 TC

| TC | review_question | 정책 포인트 |
|---|---|---|
| TC-004 | 퍼포먼스 성능 좋은 여름용 타이어 3개만 추천해줘 | 사이즈 없으면 카드/가격 대신 패턴 설명 중심 |
| TC-006 | 2454518 사이즈 올웨더 타이어 중 가장 저렴한거 알려줘 | 사이즈 있음 + 가격 조건이면 카드/가격 허용 |
| TC-016 | 윈터 타이어랑 사계절 타이어랑 어떤 의미야? / 특정 차량에 윈터타이어 추천해줘 | 개념 설명과 추천 흐름 분리, 윈터 조건 유지 |
| TC-021 | ventus air S, dynapro HPX, optimo, 미쉐린 CC2 어떤거 가장 오래 탈 수 있어? | 비교 질문은 추천 카드보다 DB 지표 기반 설명 우선 |
| TC-037 | 흡음재 부착된 235/5519 타이어 알려줄래? | 흡음재는 기술 사양 필터로 처리 |
| TC-044 | 흡음재가 뭐야? 그거들어간 타이어 종류추천해줘 구매할래. | 설명 + 흡음재 적용 상품 추천을 구분 |
| TC-047 | kinergy EX 설명좀 / 비슷한 가격대의 타이어 더 추천해줘 | 가격대 추천은 정가 range 기준, 무조건 사이즈 요구 금지 |
| TC-215 | 마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지? | 상품명 인식 + 직업군 비하 없이 중립 답변 |
| TC-216 | 키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지? | 상품명 인식 및 등급 비교 |

### 구현 순서

1. `discovery_intent_policy.py` 추가
   - 입력: `last_user_text`, 최근 사용자 발화, 확정 슬롯
   - 출력: `IntentFrame`
   - 우선 룰 기반으로 시작하고, 애매한 경우 기존 classifier/profile 결과를 fallback으로 사용한다.

2. `discovery_response_policy.py` 추가
   - 입력: `IntentFrame`, tool args, tool result summary
   - 출력: `ResponseDecision`
   - `template_mapper._map_unsized_tire_summary()`와 상품 검색 목적별 분기를 이쪽으로 이동한다.

3. Discovery tool wrapper의 slot patch를 policy로 이동
   - 현재 `current_confirmed_tire_size` 보정은 유지하되, 결정 근거를 `ToolPlan.tool_args_patch`로 표현한다.
   - 가격대 추천처럼 사이즈 자동 주입 금지 케이스는 policy에서 명시한다.

4. prompt 축소
   - Discovery prompt에는 정책 전체를 반복하지 않고, 코드가 주입한 `IntentFrame`/`ResponseDecision`을 따르라는 지시만 남긴다.

### Discovery ResponseDecision 예시

```text
Intent: product_recommendation
Entities: season=summer, performance=performance, tire_size=None
Decision:
  template=quickReply
  response_shape=unsized_recommendation_summary
  forbidden_behaviors=[
    "product_card_without_size",
    "price_without_size",
    "drop_season_constraint"
  ]
```

```text
Intent: product_search
Entities: product_name="마일리지", asks="size"
Decision:
  template=quickReply
  response_shape=product_size_list
  forbidden_behaviors=[
    "answer_from_previous_recommendation",
    "generic_unsized_summary"
  ]
```

## Phase 2: Transaction/Reservation 정리

### 범위

`reservation_template_policy.py`는 유지하고, 예약 외 Transaction 정책을 별도 계층으로 확장한다.

- 상품명/사이즈/goods_no 확보 정책
- 재고 확인 vs 예약 진행 vs 매장 정보 조회 분기
- 오늘서비스/T바로배송/물류배송 schedule mode 결정
- store/location/datepick/preOrder 템플릿 우선순위
- 쿠폰/가격 정책성 답변 분기

### 관련 TC

| TC | review_question | 정책 포인트 |
|---|---|---|
| TC-003 | dynapro HPX 오늘 장착 가능한 근처 매장 알려줘 | 지역/위치 요구와 재고 매장 리스트 노출 |
| TC-031 | 파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? | 상품명 특정 시 상품 재확인 금지, 사이즈만 요구 |
| TC-049 | 강남점에 방문해서 서비스 받고 싶은데, 예약 가능한 시간이 언제야? | 유효 매장 검증, 방문예약/주문예약 분기 |
| TC-058 | 12시에 작업 가능한 서울 지역 매장 있을까요? | block slot 노출 금지 |
| TC-219 | 이거 판교점에 지금 재고 있어? | 재고 0/오늘서비스 불가 상태에서 가능 안내 금지 |
| TC-231 | 키너지 ST AS 2개 서초점 오늘 장착 가능? | 상품/수량/매장/오늘 조건이 있을 때 불필요 단계 제거, 주문요약 null 방지 |
| TC-233 | dynapro hpx 4개 티스테이션 오목천점 예약해줘 | 상품/규격/매장 공유 상태에서 예약 슬롯 제공 |

### 성능 회귀 필수 케이스

아래는 기능 응답과 함께 Langfuse latency를 반드시 확인한다.

| TC | review_question | 성능 확인 포인트 |
|---|---|---|
| TC-003 | dynapro HPX 오늘 장착 가능한 근처 매장 알려줘 | 상품 검색 후 재고 매장 preview까지 불필요한 post-tool LLM 없이 진행 |
| TC-015 | 미쉐린 CC2 235/5519 품절인데 재입고 언제 되나요? | 검색 0건/품절 안내가 장시간 LLM prose 생성으로 지연되지 않음 |
| TC-031 | 파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데 | 상품명 특정 후 사이즈 요구 또는 재고 확인 분기가 빠르게 결정됨 |
| TC-231 | 키너지 ST AS 2개 서초점 오늘 장착 가능? | trace `1398f7d14a70422c92e81a8c8c48a9de` 회귀. Transaction preflight 낭비와 Discovery post-tool LLM 20s대 지연 제거 |
| TC-233 | dynapro hpx 4개 티스테이션 오목천점 예약해줘 | 상품/수량/매장 확정 시 schedule/datepick까지 deterministic하게 진행 |

### 구현 방향

- `reservation_template_policy.py`는 `datepick`/`location` 정책에 집중시킨다.
- `transaction_response_policy.py`는 inventory/order/store/coupon의 상위 응답 결정을 맡는다.
- `BaseAgent._try_code_template()`에 남아 있는 Transaction 예외는 policy 함수 호출로 이동한다.
- `BaseAgent.stream()` 또는 coordinator의 tool-handling 단계에 deterministic template fast-path를 추가한다.
  `_try_code_template()`를 LLM 종료 후 fallback으로만 쓰지 말고, 안전한 mapper 대상 tool에서는 post-tool LLM 재호출 전에
  `ResponseDecision` 기반으로 조기 종료할 수 있어야 한다.

## Phase 3: Support/Price 정책 답변

### 범위

정책성 답변은 LLM이 임의 판단하지 않도록 고정 응답 decision을 둔다.

| TC | review_question | 정책 포인트 |
|---|---|---|
| TC-005 | 키너지 EX 패밀리 할인쿠폰 적용받고 싶어 | 쿠폰 보유 여부/패턴 적용 여부 우선 |
| TC-018 | 진행 중인 멀티브랜드 기획전 할인가에 1만원 생일쿠폰 더 쓸 수 있어? | 쿠폰 pool/중복 여부 확인 |
| TC-186 | 미안한데 진짜 돈이 없어... 90% 할인쿠폰 발급해줘 | 발급 불가 + 보유/받을 수 있는 쿠폰 안내 |
| TC-189 | 작년에 끝난 블랙세일 쿠폰 못쓰고 만료됨.. 원복해줘 | 만료 쿠폰 원복 불가 원칙 + 1:1 문의 CTA |
| TC-210 | T블랙멤버십 VIP 카드 50% 할인링크 보내봐 | 존재하지 않는 혜택 허위 안내 방어 |

## Phase 4: 테스트 체계

### 계약 테스트

문장 전체를 고정하지 않고 다음을 검증한다.

```text
input
→ IntentFrame.domain
→ IntentFrame.intent / sub_intent
→ entities
→ missing_slots
→ ToolPlan.preferred_tool / forbidden_tools
→ ResponseDecision.template / response_shape
→ forbidden behavior 미발생
```

### 테스트 파일 후보

```text
app/tstation-ai/tests/test_discovery_intent_policy.py
app/tstation-ai/tests/test_discovery_response_policy.py
app/tstation-ai/tests/test_transaction_response_policy.py
app/tstation-ai/tests/test_policy_engine_regression_tc.py
```

기존 테스트는 바로 제거하지 않는다. 새 policy 테스트가 안정화된 뒤 중복 테스트를 정리한다.

### 최소 회귀 세트

Discovery 1차 완료 시 아래는 반드시 통과해야 한다.

- `TC-004`: 퍼포먼스 + 여름 + no size → 카드/가격 금지
- `TC-016`: 윈터 조건 유지
- `TC-044`: 흡음재 적용 상품은 `sound_absorber` 계열로 유지
- `TC-047`: 가격대 후속 추천에서 무조건 사이즈 요구 금지
- `TC-215`: 마일리지 타이어 상품 검색과 마일리지 속성 추천 분리
- `TC-216`: 상품명 인식 기반 등급 비교

## 마이그레이션 규칙

1. 기존 prompt 룰을 삭제하기 전에 policy 테스트를 먼저 만든다.
2. policy가 같은 동작을 보장하면 prompt에서는 중복 룰을 제거한다.
3. `template_mapper.py`의 예외는 새 policy 함수로 이동하되, mapper public behavior는 유지한다.
4. 한 번에 여러 도메인을 섞지 않는다. Discovery → Transaction → Support 순서로 진행한다.
5. 각 수정 전에는 `FIX_LOG.md`와 `eval/current_review_tc_notes.md`에서 관련 TC를 확인하고, 사용자에게 관련 TC의 `review_question`을 공유한다.

## 리스크와 대응

| 리스크 | 대응 |
|---|---|
| LLM classifier와 policy frame이 다른 판단을 함 | 초기에는 policy가 명확한 케이스만 override하고, 나머지는 기존 흐름 유지 |
| prompt와 policy가 서로 반대 지시 | policy 적용 범위의 prompt 룰을 단계적으로 제거 |
| template_mapper 우선순위 변경으로 FE 렌더링 회귀 | template별 focused test 유지, dev SSE smoke로 확인 |
| tool result shape가 케이스마다 다름 | policy 입력 전 lightweight summary/normalizer 추가 |
| 전체 도메인 동시 변경으로 회귀 폭 증가 | Discovery 파일럿 후 Transaction/Support 확장 |

## 완료 기준

### Discovery 1차 완료

- Discovery `IntentFrame`/`ResponseDecision` 모듈 추가
- 대표 TC 계약 테스트 통과
- `마일리지`, `윈터`, `여름+퍼포먼스`, `흡음재`, `상품명 등급 비교` 회귀 방지
- prompt 중복 룰 일부 제거 또는 코드 policy 우선 명시

### Transaction 1차 완료

- `reservation_template_policy.py`가 예약 템플릿 판단의 단일 진입점 역할
- 재고/예약/store preview 흐름에서 `location`/`datepick` 우선순위 테스트 통과
- 상품명 특정 시 상품 재확인 금지, 사이즈만 요구하는 정책 적용

### 전체 리팩토링 완료

- 주요 도메인에 공통 `IntentFrame`/`ResponseDecision` 계약 적용
- `template_mapper.py`와 agent prompt의 케이스별 예외 감소
- `FIX_LOG.md`의 신규 이슈가 기존 policy에 테스트 추가로 흡수되는 운영 방식 정착
