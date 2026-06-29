# 개발 코드 구조 변경 히스토리

브랜치: `stabilize-turn-contract-policy`  
작성일: 2026-06-26

## 문서 목적

이 문서는 현재 개발 코드가 어떤 구조로 바뀌고 있는지, 왜 그 구조가 필요한지, 다음 구조 개선은 어떤 방향이어야 하는지를 기록한다.

용도:

- 현재 브랜치의 코드 구조 변경 방향 기록
- router, policy, TurnContract, QC, tool/template 실행 경계의 책임 분리 기록
- multi-goal, multi-turn 실행 구조로 확장하기 위한 설계 히스토리 보관
- 이후 구현자가 과거 대화나 임시 플랜을 다시 찾지 않아도 구조적 맥락을 이해할 수 있게 하는 기준 문서

개별 버그 수정 이력은 `FIX_LOG.md`에 기록한다. 이 문서는 특정 정책 변경 목록이 아니라 **구조 변경의 배경과 방향**을 다룬다.

## 2026-06-29 구조 변경 계획: Tool boundary 중앙화 1차

### 배경

최근 stock/store flow 오류는 router나 TurnContract intent 자체보다, 실행 가능한 tool boundary가 여러 위치에서
부분적으로 생성/보정되는 구조에서 반복됐다.

```text
transaction_intent_policy.plan_transaction_tools()
-> TurnContract.allowed_tools/forbidden_tools
-> chat.py flow advancement/recovery helper
-> BaseAgent contract tool guard
```

이 구조에서 정책은 `stock_inventory_lookup`을 요구하지만, `chat.py` 또는 BaseAgent recovery 경로가 예전 allow-list나
preferred tool 기본값을 사용하면 `search_stores_tool` 같은 정상 store/place lookup tool이 차단된다.

### 구조 원칙

이번 1차 중앙화의 목표는 새 executor를 만드는 것이 아니라, 이미 존재하는 `ToolPlan`을 더 명확한 단일 생성물로 쓰는 것이다.

- Router/FlowState/slots는 evidence만 제공한다.
- `transaction_intent_policy`가 intent/slot/flow step 기준으로 `allowed_tools`, `forbidden_tools`,
  `preferred_tool`, `tool_args_patch`를 만든다.
- `TurnContract`는 tool boundary를 보관하고 user-visible action gate에 사용한다.
- `chat.py`는 stock/store advancement/recovery에서 직접 preferred tool을 재판단하지 않고 정책 `ToolPlan`을 소비한다.
- BaseAgent/recovery executor는 contract 밖 tool을 실행하지 않는다.

### 1~3단계 적용 범위

1단계는 현재 boundary 생성 지점을 확인하고, stock/store inventory lookup에 대한 중앙 helper를 둔다.

2단계는 `stock_inventory_lookup`의 tool boundary를 보정한다.

- 확정 매장 재고 확인: `get_store_inventory_tool`
- 단순 지역/매장명 목록 조회: `get_store_list_tool`
- 역/장소/근처 기반 매장 조회: `search_stores_tool`
- 물류 재고 확인: `get_logistics_inventory_tool`

`search_place_tool`은 1차 executable boundary에 직접 포함하지 않는다. 장소 resolve는 우선 `search_stores_tool` 내부 단계로
보며, coordinate-only tool contract가 필요하면 별도 단계에서 설계한다.

3단계는 `chat.py`의 stock flow advancement/recovery가 중앙 policy helper를 소비하게 정리한다.

- `chat.py`에서 `get_store_list_tool`로 강제 보정하던 경로를 제거한다.
- contract-required recovery allow-list에 `search_stores_tool`을 포함한다.
- recovery executor는 현재 `ToolPlan.preferred_tool`을 우선 사용한다.
- 단순 region lookup은 기존처럼 `get_store_list_tool`을 유지하고, `nearby/place_query`가 있는 경우만
  `search_stores_tool`을 preferred로 둔다.

### 비목표

- quick_order/cart/preOrder/orderComplete 실행 허용 범위 확대는 하지 않는다.
- 전체 required tool executor 일반화는 하지 않는다.
- `chat.py` 대규모 구조 변경 대신 stock/store flow의 직접 ToolPlan 보정만 줄인다.

## 2026-06-29 구조 변경 적용: fast path gate / contract-required executor / seed-evidence 1차

### 배경

FlowState read-through와 stock/store tool boundary 중앙화 이후에도, deterministic fast path가 먼저 final response를
확정하면 TurnContract가 요구한 tool 실행이 막히는 구조가 남아 있었다.

대표 흐름은 다음과 같다.

```text
Router/FlowController/TurnContract: current-turn stock/store 또는 sized recommendation 계약 확정
-> deterministic fast path: context/regex/template evidence로 quickReply/product summary 확정
-> contract-required tool: 실행되지 않음
```

이 문제는 router intent 오류가 아니라 실행 우선순위 오류다. 따라서 fast path가 current-turn contract를 우회하지 못하게
하고, contract-required tool 실행 진입점을 더 명확하게 만드는 쪽이 구조적으로 맞다.

### 적용 내용

1단계는 fast path gate가 read-through state를 보게 한 것이다.

- fast path gate는 `active_flow_context + ConversationSlots + TurnContract.known_slots`를 같은 방식으로 읽는다.
- selected-store schedule, selected-store stock inventory, stock store lookup, sized recommendation에서 pending
  contract-required tool이 보이면 final response 확정을 막는다.
- context/regex evidence만으로 current-turn action이 만들어지는 경로를 좁힌다.

2단계는 contract-required 실행 진입점을 1차로 묶은 것이다.

- `_recover_contract_required_tool()`을 두고 기존 store-flow recovery와 sized recommendation recovery를 순서대로 소비한다.
- 각 세부 helper의 narrow 조건은 유지한다.
- quick_order/cart/preOrder/orderComplete 같은 downstream execution boundary는 열지 않는다.

3단계는 seed/evidence split을 TurnContract trace까지 올린 것이다.

- FlowController가 만든 `contract_seed`와 `context_evidence`를 `TurnContract`가 보관한다.
- `contract_seed`는 router/current-turn/UI action 같은 실행 계약 후보를 담는다.
- `context_evidence`는 parent flow, 최근 후보군, 선택 상품/수량/매장 같은 slot 보강 evidence를 담는다.
- 이번 단계는 trace와 contract object 보관까지이며, `build_turn_contract()` 내부 intent 생성 로직의 완전한 타입 분리는
  후속 migration으로 남긴다.

### 남은 방향

- contract-required executor가 `preferred_tool/tool_args_patch`를 공통으로 소비하도록 더 일반화한다.
- BaseAgent guard와 `chat.py` recovery가 같은 allow/deny source를 보게 한다.
- fast path callsite가 모두 `merged_slots` 또는 FlowController transition evidence를 넘기도록 정리한다.
- `contract_seed`만 intent/action을 만들고 `context_evidence`는 slot 보강에만 쓰는 규칙을 `build_turn_contract()` 입력
  구조로 강제한다.

## 2026-06-29 구조 변경 적용: contract-required executor 2차 1단계

### 배경

이전 단계에서 contract-required recovery 진입점은 생겼지만, executor가 여전히 domain policy를 다시 계산하거나
ContextVar의 tool plan을 fallback으로 읽는 구조가 남아 있었다.

구조적으로는 `ToolPlan`이 만든 실행 boundary가 `TurnContract`에 저장되고, executor는 최종 contract object만 보고
실행 후보를 고르는 방향이 맞다. 그래야 tool boundary를 생성하는 곳과 실행하는 곳이 달라져 생기는 drift를 줄일 수 있다.

### 적용 내용

- `TurnContract`가 `preferred_tool`과 `tool_args_patch`를 보관한다.
- `build_turn_contract()`는 최종 `allowed_tools/forbidden_tools` 재정렬 뒤 preferred가 contract 밖이면 제거하거나
  current-turn intent의 기본 preferred로 맞춘다.
- stale preferred가 바뀌면 stale `tool_args_patch`도 비운다.
- recovery executor는 discovery/support/transaction branch에서 contract preferred/tool args를 먼저 소비한다.
- 기존 blocklist와 narrow execution guard는 유지한다.

### 남은 방향

- domain별 branch 안에 남아 있는 candidate 생성 로직을 공통 candidate builder로 추출한다.
- BaseAgent의 contract tool guard와 chat-side recovery가 같은 candidate builder와 allow/deny source를 보게 한다.
- `preferred_tool/tool_args_patch`가 없는 contract는 정책 layer에서 보강하고, executor에서 policy를 재계산하는 경로를 줄인다.

## 2026-06-30 구조 변경 적용: contract-required executor 2차 2단계

### 배경

contract-required recovery는 `TurnContract.preferred_tool/tool_args_patch`를 우선 소비하게 되었지만, tool 후보 선정과
실행/template/SSE 조립이 여전히 `recover_blocked_fast_path_to_contract_tool()` 안에 섞여 있었다.

다음 구조 목표는 chat-side recovery와 BaseAgent guard가 같은 "contract-required tool candidate"를 보게 만드는 것이다.
이를 위해 먼저 후보 선정만 독립 helper로 분리했다.

### 적용 내용

- `_ContractRequiredToolCandidate`를 추가했다.
- `_contract_required_tool_candidate()`가 다음 값을 만든다.
  - `tool_name`
  - `tool_input`
  - `tool_input_source`
  - `display_name`
  - `source_domain`
- `recover_blocked_fast_path_to_contract_tool()`는 candidate를 받아 실제 tool invoke, template mapping, recovery metadata,
  SSE event 조립만 담당한다.
- 기존 narrow guard와 blocklist는 그대로 유지한다.

### 남은 방향

- candidate builder를 BaseAgent `code_contract_tool_guard`에서도 소비하게 한다.
- candidate builder를 `chat.py` 밖 policy/executor 모듈로 옮길지 결정한다.
- 실제 tool invoke/template mapping도 contract-required executor 계층으로 분리해 `chat.py`를 orchestration-only에 가깝게 줄인다.

## 2026-06-30 구조 변경 적용: FlowState progress evaluator 1단계

### 배경

완전한 flow loop executor를 한 번에 도입하면 회귀 위험이 크다. 하지만 FlowState가 업데이트될 때마다 현재 flow의
부족 슬롯과 다음 권장 tool을 계산해 저장하면, 기존 recovery/helper 구조를 크게 바꾸지 않고도 다음 단계 선택을
중앙화할 수 있다.

### 적용 내용

- `flow_state.py`에 `evaluate_flow_progress()`를 추가했다.
- `commit_flow_state()`의 active flow merge 이후 progress를 재계산해 active context에 저장한다.
- 저장되는 값은 다음과 같다.
  - `target_action`
  - `current_step`
  - `missing_slots`
  - `next_tool`
  - `tool_args_patch`
  - `allowed_tools`
- 1차 graph는 `stock`, `purchase`, `store_schedule`만 다룬다.
- 이 단계는 tool을 실행하지 않는다. context는 실행 근거가 아니라 TurnContract/candidate가 읽을 evidence다.

### 남은 방향

- TurnContract build가 current-turn continuation일 때만 progress를 allowed/preferred evidence로 읽게 한다.
- `_contract_required_tool_candidate()`가 active flow progress의 `next_tool/tool_args_patch`를 우선 소비하게 한다.
- progress 기반 경로가 안정화되면 `search_product_tool` 후 stock flow advance, confirmed state advance 같은 보정 helper를 줄인다.

## 2026-06-30 구조 변경 적용: FlowState progress candidate 연결

### 배경

FlowState는 업데이트 후 `next_tool/tool_args_patch`를 저장하지만, 실행 후보 생성기가 이를 읽지 않으면 여전히
기존 recovery helper와 ContextVar plan에 의존한다. 따라서 저장된 progress를 contract-required candidate의
우선 evidence로 연결했다.

### 적용 내용

- `flow_state.py`에 `flow_progress_from_active_context()`를 추가했다.
- `_contract_required_tool_candidate()`가 transaction contract에서 active flow progress를 먼저 확인한다.
- context 단독 실행을 막기 위해 아래 조건을 모두 요구한다.
  - active flow type이 `stock`, `purchase`, `store_schedule` 중 하나
  - contract intent 또는 response shape가 해당 flow와 정렬됨
  - `next_tool`이 contract `allowed_tools`에 포함되고 `forbidden_tools`에 없음
  - 1차 대상 tool은 transaction-side tool로 제한

### 남은 방향

- TurnContract build 단계에서 current-turn continuation일 때 progress를 preferred/tool args evidence로 반영한다.
- product resolve progress(`search_product_tool`)는 discovery-side safe candidate로 별도 연결한다.
- progress 기반 path가 안정화되면 기존 stock flow advance/recovery special case를 줄인다.

## 2026-06-30 구조 변경 적용: product resolve progress discovery candidate 연결

### 배경

FlowState progress candidate 1차는 transaction-side store/inventory/schedule tool만 실행 후보로 소비했다.
하지만 stock/purchase flow의 첫 단계가 상품 resolve일 때는 `search_product_tool`이 discovery domain tool이므로,
같은 progress evidence를 transaction executor에서 실행하면 domain/tool module drift 위험이 있다.

따라서 product resolve progress는 discovery contract 안에서만 소비하도록 별도 경계를 뒀다.

### 적용 내용

- active flow progress가 `current_step=resolve_product`, `next_tool=search_product_tool`인 경우를 candidate로 연결했다.
- 소비 조건은 discovery contract로 제한했다.
  - flow type: `stock`, `purchase`
  - contract intent/response shape: product search 또는 missing stock/order slot flow와 정렬
  - `search_product_tool`이 `allowed_tools`에 있고 `forbidden_tools`에 없음
  - `tool_args_patch.keyword` 존재
- transaction contract는 같은 progress를 직접 실행하지 않는다. transaction은 product resolve 결과가 저장된 뒤
  다음 progress인 store/inventory 단계만 소비한다.

### 남은 방향

- `search_product_tool` 결과 저장 후 progress를 재평가해 store resolve 또는 inventory lookup으로 이어지는 loop를
  더 중앙화한다.
- candidate builder와 tool invoke/template mapping을 `chat.py` 밖 executor 계층으로 이동한다.
- BaseAgent guard도 같은 candidate source를 소비하게 해 chat-side recovery와 agent execution boundary를 맞춘다.

## 2026-06-30 구조 변경 적용: FlowState progress 전진 1~3단계

### 배경

FlowState progress를 candidate가 읽기 시작했지만, tool 결과 저장 시 active flow context에 필요한 evidence가 모두
보존되지 않으면 progress가 다음 step으로 전진하지 못한다.

대표적으로 stock flow에서는 다음 순서가 필요하다.

```text
search_product_tool result -> goods_no 저장
-> progress 재평가: resolve_store/search_stores_tool
-> store lookup result 또는 store selection -> shop_id 저장
-> progress 재평가: check_inventory/get_store_inventory_tool
```

### 적용 내용

1단계는 product resolve 후 store evidence 보존이다.

- `search_product_tool` 결과로 `goods_no`를 저장할 때 기존 `region/place_query/shop_name` evidence를 active flow delta에
  함께 보존한다.
- nearby/place search로 해석된 stock flow에서는 `region`을 `place_query`로 active flow에 직접 넣어
  `search_stores_tool` progress가 유지되게 했다.

2단계는 store resolve 후 target action 전진이다.

- store lookup/schedule/inventory tool 결과로 `shop_id/shop_name`이 확정될 때 flat slot의 product/quantity/intent evidence를
  active flow delta에 함께 병합한다.
- 단일 store result는 `store_selected` 후 `check_inventory/get_store_inventory_tool` progress로 재평가된다.

3단계는 progress candidate 판정 위치 이동이다.

- FlowState progress가 어떤 tool candidate가 될 수 있는지 판단하는 `flow_progress_tool_candidate()`를 `flow_state.py`에 둔다.
- `chat.py`는 active context를 읽고 helper 결과를 `_ContractRequiredToolCandidate`로 감싸는 orchestration 역할만 한다.
- 실제 tool invoke/template mapping은 아직 `chat.py`에 남겼다. 이번 단계에서 대규모 executor 이동은 하지 않았다.

### 남은 방향

- candidate dataclass, invoke, template mapping을 별도 executor 모듈로 분리한다.
- BaseAgent `code_contract_tool_guard`가 같은 progress/candidate source를 소비하게 한다.
- purchase flow의 schedule/payment 단계도 같은 progress graph로 확장한다.

## 2026-06-29 구조 변경 계획: current-turn execution boundary와 parent flow 분리

### 배경

최근 7일간의 FIX_LOG 흐름은 같은 원인 계열을 반복적으로 가리킨다.

```text
router가 현재 턴 intent를 맞춰도,
downstream code frame / regex slot / stale pending_intent / goal_type / active flow 복원이
current-turn intent를 덮어 TurnContract와 실행 domain/tool boundary를 바꾸는 문제
```

기존 `router_wins` 보정은 FAQ, policy, complaint, product info 같은 정보성 intent를 보호하는 데 효과가 있었다.
하지만 매장 검색, 재고 매장 검색, 매장 스케줄 확인처럼 주문/예약 parent flow 안에서 발생하는 실행성 중간 단계는
별도 경계가 필요하다.

중요한 점은 이 경계가 주문/예약 parent flow를 끊는 장치가 아니라는 것이다.
`router_wins_execution_boundary`는 **current-turn intent ownership**과 **parent flow context**를 분리해야 한다.

```text
current_turn_intent:
  이번 턴에서 실행할 계약. 예: store_search, stock_store_search, selected_store_schedule

parent_flow:
  이전부터 이어지는 큰 흐름. 예: order/place_order, stock/store_with_stock

preserved_slots:
  parent flow 연결에 필요한 goods_no, tire_size, ord_qty, payment_amount, pending_order_context
```

예를 들어 기존 주문 흐름에서 사용자가 `분당에서 장착 가능한 매장 찾아줘`라고 말하면, contract intent는
`stock_store_search` 또는 `store_search`로 잠가야 한다. 동시에 기존 `goods_no`, `tire_size`, `ord_qty`는
`transaction_store_preview_tool` 인자와 다음 단계 연결을 위해 보존해야 한다.

금지해야 하는 것은 parent context 자체가 아니라, parent context가 이번 턴 intent를 `quick_order_*`로 덮거나
`datepick`, `preOrder`, `quick_order_tool` 같은 downstream action을 조기 실행하는 것이다.

### 1차 수정 범위

1차 수정은 현재 구조를 크게 바꾸지 않고, router intent가 downstream에서 덮이는 핵심 경로를 좁게 막는 것을 목표로 한다.

- `TurnContract`에 current-turn execution boundary를 추가한다.
- 초기 대상은 `stock_store_search`, `store_schedule`, `open_store_search`, `store_service_search`로 제한한다.
- `quick_order_reservation`, `quick_order_execute`, `cart_add`는 1차 boundary 대상에서 제외한다.
- current-turn contract intent는 router/current-turn 기준으로 잠근다.
- parent order/stock context는 tool args와 next-step continuation evidence로만 보존한다.
- stale `pending_intent=order`, `goal_type=place_order`가 current-turn intent를 `quick_order_*`로 바꾸지 못하게 한다.
- `goods_no`, `tire_size`, `ord_qty`, 검증된 `payment_amount`, `pending_order_context`는 보존한다.
- 매장 찾기 턴에서는 `quick_order_tool`, `preOrder`, `orderComplete`, 조기 `datepick` emit을 금지한다.
- selected-store continuation에서는 `get_store_schedule_tool`만 허용하고 preview/store-list loop 및 `quick_order_tool`을 금지한다.
- TurnContract 이후 실행 domain, prompt profile, tool-plan ContextVar가 contract 기준과 맞는지 동기화 invariant를 강화한다.

1차 검증은 문구가 아니라 contract invariant를 기준으로 한다.

- router가 `stock_store_search`인데 stale order context가 `quick_order_reservation`으로 덮지 않는지 확인한다.
- parent `goods_no`, `tire_size`, `ord_qty`가 `transaction_store_preview_tool` 인자로 보존되는지 확인한다.
- 매장 찾기 턴에서 `datepick`, `preOrder`, `quick_order_tool`이 조기 실행되지 않는지 확인한다.
- 매장 선택 턴에서 `get_store_schedule_tool`만 허용되는지 확인한다.
- support/policy turn에서는 기존 informational router-wins와 dormant context 처리가 유지되는지 확인한다.

### 2차 수정 범위

2차 수정은 같은 계열의 재발을 줄이기 위한 구조 정리다.

- contract 입력을 `contract_seed`와 `context_evidence`로 분리한다.
- `contract_seed`에는 router domains, execution plan, policy intent, action mode, UI action slot patch, explicit resume source만 둔다.
- `context_evidence`에는 이전 상품/매장/주문/추천 context, dormant context, 최근 template metadata, 최근 tool result만 둔다.
- `contract_seed`만 current-turn intent와 action을 만들 수 있게 한다.
- `context_evidence`는 tool args 보강, 답변 grounding, next-step continuation에만 사용한다.
- `TurnContract`에 `parent_flow_id`, `parent_flow_type`, `parent_flow_state`, `parent_flow_slots` 같은 parent flow metadata를 명시한다.
- FlowController를 router result, UI action, current text를 받는 단일 flow-state 진입점으로 승격한다.
- `recover_blocked_fast_path_to_contract_tool()` 성격의 복구 경로를 `contract_required_tool_executor`로 재정의한다.
  - 2026-06-29 얇은 흡수 완료: 차량 선택 후 final contract가 `product_recommendation` + product template +
    `get_products_recommendations_tool` allowed + sized recommendation response shape이면, 차량 사이즈 안내 quickReply로
    종료하지 않고 contract-required recommendation recovery가 실행될 수 있게 했다.
  - 예: 안심서비스 sized recommendation은 선택 차량의 `tire_size`와 `rcmd_type=safe_kids`, `brand_cd=HK`를 보존해
    `get_products_recommendations_tool`로 이어진다.
  - 남은 과제: support FAQ direct executor, stock/store schedule recovery, discovery recommendation recovery를 명시적
    `contract_required_tool_executor`로 합치고 required/preferred tool metadata를 TurnContract에 명시한다.
- UI action carry-forward는 `ui_action_policy.py`에서 `select_product`, `select_quantity`, `select_store`, `select_schedule`, `select_vehicle`, CTA click 단위로 중앙화한다.
  - 2026-06-29 얇은 흡수 완료: active recommendation flow의 `select_vehicle` 결과를 sized recommendation contract-required
    tool 실행과 연결했다.
  - 남은 과제: `select_vehicle` carry-forward 판정을 `chat.py` recovery helper가 아니라 `ui_action_policy.py` /
    FlowState 단위로 중앙화한다.

2차 완료 기준은 다음과 같다.

```text
router result + ui_action + current text
-> FlowController
-> FlowState(active/dormant/resumed/completed)
-> TurnContract
-> contract-required tool execution
-> template/QC validation
```

이 구조에서는 parent flow가 유지되더라도 current-turn intent를 덮지 못하고, explicit resume 또는 current-turn UI action이 있을 때만
parent flow가 action source로 승격된다.

## 2026-06-28 구조 변경 기록: chat.py 책임 분리 리팩토링

### 배경

`services/tstation/chat.py`는 router schema, prompt, coordinator, service orchestration, helper, CTA/template 보정,
slot/flow 보정 로직이 한 파일에 누적되어 약 38k lines 규모가 되었다.

이 상태에서는 작은 버그 수정도 `chat.py`에 새 helper, regex, fallback, CTA 조립 로직을 추가하는 방향으로 흐르기 쉽고,
회귀 발생 시 원인을 특정하기 어렵다.

따라서 현재 구조 변경 방향은 다음과 같다.

- `chat.py`는 최종적으로 orchestration hub에 가깝게 축소한다.
- 기능 동작 변경 없이 helper를 도메인별 모듈로 이동한다.
- 기존 consumer가 `services.tstation.chat`에서 private 심볼을 import하는 경우가 있으므로, `chat.py` re-export는 유지한다.
- 새 helper 모듈은 `services.tstation.chat`를 import하지 않는다.
- 기능 수정과 pure move/refactor 커밋을 섞지 않는다.

### 현재 완료 상태

현재 완료된 구조 변경은 아래와 같다.

- Phase 3 alias/import cleanup
  - Commit: `01060bb`, `7087b39`
  - `ui_action_policy.py`에서 가져온 helper의 중복 alias 블록을 정리했다.
  - 실제 미사용 import는 제거하고, private consumer가 남은 심볼은 명시적 re-export 또는 `# noqa: F401`로 유지했다.

- Phase 4-a quickreply helper 추출
  - Commit: `0e167d6`, follow-up `e290a1e`
  - 신규 모듈: `services/tstation/helpers/quickreply.py`
  - quickReply CTA 정규화, 예약 변경 quickReply 보정, 매장 상세 quickReply 복구, listCar prompt 판별 등
    quickReply 보정 helper를 이동했다.
  - `chat.py`는 기존 import 호환을 위해 동일 심볼을 re-export한다.

- Phase 4-c vehicle helper 추출
  - Commit: `27ba76a`
  - 신규 모듈: `services/tstation/helpers/vehicle.py`
  - 차량 선택/차량 정보/순정 OE·RE 교체/정비 D-day 관련 pure helper를 이동했다.
  - `MultiAgentDomain.Domain.DISCOVERY.value` 의존은 helper에서 `chat.py`를 import하지 않기 위해 `"discovery"` 리터럴로 대체했다.

현재 기준 라인 수:

```text
services/tstation/chat.py                 37,525 lines
services/tstation/helpers/quickreply.py      417 lines
services/tstation/helpers/vehicle.py         525 lines
```

### 다음 진행 순서

다음 단계는 product helper 추출이다. 단, product 전체를 한 번에 이동하더라도 아래 경계를 지킨다.

포함 가능:

- 상품명/브랜드/사이즈 표시용 pure formatter
- product description quickReply/event builder
- product detail/result에서 텍스트를 조립하는 helper
- recent product template/context parsing
- product comparison text/helper
- product metadata extraction

제외:

- `goods_no`, `tire_size`, `ord_qty`를 flow state에 commit하는 로직
- discovery -> transaction route 변경
- order/stock/price/coupon tool 선택
- TurnContract, ToolPlan, ResponseDecision 생성 로직
- OE/RE처럼 vehicle helper와 product helper가 강하게 교차하는 flow 전이 로직

이후 권장 순서:

```text
Phase 4-b: product helper
Phase 4-d: order helper
Phase 4-e: store helper
Phase 4-f: slot_flow helper
Phase 2-a: routing schema
Phase 2-b: router prompts
Phase 5-a: StreamingMultiAgentCoordinator
Phase 5-b: TStationChatServiceV2
Phase 6: compatibility re-export cleanup
```

### 검증 기준

각 단계는 다음 기준을 만족해야 한다.

- `ruff check` 대상 파일 통과
- dummy env import smoke 통과
- 관련 targeted pytest 실행. 0 tests selected는 검증으로 인정하지 않는다.
- `git show --stat`와 diff로 pure move 또는 alias cleanup 범위를 확인한다.
- 새 helper가 `services.tstation.chat`를 import하지 않는지 확인한다.
- 기능 버그 수정은 별도 커밋으로 분리한다.

## 현재 코드 구조의 변화 방향

현재 브랜치의 핵심은 단순한 router 분기 수정이 아니라, 한 turn에서 실행 가능한 행동의 경계를 `TurnContract`로 고정하는 구조로 이동하는 것이다.

기존 흐름은 대략 다음과 같다.

```text
사용자 발화
-> router/classifier
-> domain agent
-> tool 실행
-> template mapper
-> QC
-> SSE 응답
```

현재 개발 방향은 이 흐름 중간에 policy와 contract layer를 명확히 두는 것이다.

```text
사용자 발화
-> router/classifier
-> intent/policy frame
-> tool plan
-> response decision
-> TurnContract
-> agent/tool 실행
-> template mapper
-> contract/QC 검증
-> SSE 응답
```

이 구조에서 각 계층의 책임은 다음과 같다.

- router/classifier: 현재 사용자 발화의 1차 의도와 실행 도메인 판단
- policy frame: router 결과를 실행 가능한 intent/sub-intent와 slot 조건으로 정리
- tool plan: 이번 turn에서 허용되는 tool과 선호 tool, tool args patch 정의
- response decision: 허용되는 응답 형태와 template, 금지 행동 정의
- TurnContract: 위 판단을 하나의 실행 계약으로 고정
- QC: 실제 tool data와 contract 기준으로 최종 응답 검증

## 왜 구조 변경이 필요한가

단일 intent 기반 구조는 단순 질문에는 잘 동작하지만, 실제 대화에서는 한 발화 안에 여러 목표가 함께 들어온다.

예시:

```text
내 차에 적합한 올웨더 상품 추천해줘. 그리고 추천되는 상품들 장단점 비교해주고
```

이 발화는 하나의 `product_recommendation`이 아니라 다음 목표들의 묶음이다.

```text
내차목록 조회
-> 차량 선택 또는 자동 확정
-> 사이즈 확보
-> 올웨더 추천
-> 추천 상품 비교
```

또 다른 예시:

```text
벤투스 S2 AS 내일 장착 가능 매장은?
```

필요한 실행 흐름은 다음과 같다.

```text
사이즈 확보
-> 수량 확보
-> 모델명+사이즈로 상품번호 확보
-> 날짜 기준 장착 가능 매장 검색
```

이런 발화를 단일 intent/action mode로 압축하면 다음 문제가 생긴다.

- 선행 tool이 `allowed_tools`에서 빠진다.
- tool로 해소 가능한 slot이 처음부터 missing으로만 판단된다.
- 앞 단계 tool 결과로 slot이 확보되어도 response policy가 이를 반영하지 못한다.
- 최종 product/location/datepick template이 contract/QC에서 잘못 차단된다.
- 후보 선택 이후 원래 목표가 이어지지 않고 새 intent처럼 처리된다.
- stale slot 또는 raw regex candidate가 빈 slot을 잘못 채운다.

## 현재 브랜치에서 정리된 구조 원칙

### Current-turn intent 우선

현재 사용자 발화의 intent가 항상 출발점이다.

이전 상품, 매장, 주문, 쿠폰, 예약, 차량 context는 현재 intent를 보조할 수는 있지만, 현재 intent를 대신 결정하면 안 된다.

### Context는 실행 근거가 아니라 입력 후보

저장된 `goods_no`, `tire_size`, `shop_name`, `ord_qty`, `pending_intent`, `goal_type`, template metadata는 곧바로 실행 가능한 근거가 아니다.

현재 turn의 intent와 연결되었을 때만 active context가 된다.

### Regex는 후보 추출까지만 담당

정규식은 차량번호, 주문번호, 사이즈, 수량, 날짜처럼 구조화된 값을 추출하는 데 적합하다.

반대로 추천, 비교, 구매, 쿠폰, 매장 문의처럼 문맥과 slot이 섞이는 문제는 정규식 단독으로 확정하지 않는다.

### Tool/template도 action이다

tool 호출만 action이 아니다.

다음도 모두 실행 행동으로 본다.

- product card
- location card
- datepick
- preOrder
- orderComplete
- billProduct
- CTA URL
- quickReply button

따라서 tool뿐 아니라 template과 CTA도 TurnContract 기준으로 검증해야 한다.

### QC는 사실 검증과 contract 위반 차단에 집중

QC는 새로운 intent를 만들거나 router 역할을 대신하지 않는다.

QC의 역할은 다음으로 제한한다.

- tool data와 다른 사실 주장 차단
- required slot 없이 위험 template이 나가는 것 차단
- forbidden behavior 위반 차단
- contract와 맞지 않는 template/action 차단

## Multi-goal 구조 개선 방향

현재 구조를 바로 full agenda executor로 교체하면 회귀 위험이 크다.

따라서 첫 단계는 `goal_steps`를 실행기가 아니라 **계약 보조 메타데이터**로 추가하는 것이다.

예시:

```json
{
  "goal_steps": [
    {
      "goal": "resolve_vehicle",
      "required_slots": ["mbr_no"],
      "produced_slots": ["vehicle", "tire_size"],
      "allowed_tools": ["get_my_cars_tool"]
    },
    {
      "goal": "recommend_products",
      "required_slots": ["tire_size", "recommendation_scenario"],
      "produced_slots": ["product_set"],
      "allowed_tools": ["get_products_recommendations_tool"]
    },
    {
      "goal": "compare_products",
      "required_slots": ["product_set"],
      "produced_slots": ["comparison_summary"],
      "allowed_tools": []
    }
  ]
}
```

초기 적용 목적:

- 선행 goal의 tool을 allowed tool로 인정
- 앞 단계 tool이 만든 `produced_slots`를 required slot 해소로 인정
- 같은 turn에서 해소된 slot 때문에 template이 잘못 차단되는 문제 방지
- 후보 선택 이후 어떤 goal을 재개해야 하는지 추적
- Langfuse trace에서 복합 목표 실행 순서를 관찰

## 저위험 적용 순서

기본 원칙은 **simple flow 유지 + multi-goal flow 선택적 실행**이다.

router가 단순 질문으로 판단한 경우에는 기존 flow를 그대로 사용한다.

```text
사용자 발화
-> LLM router/classifier
   -> simple_turn: 기존 flow 유지
   -> multi_goal_turn: goal agenda flow 사용
```

처음부터 모든 대화를 agenda executor로 보내지 않는다. 기존에 이미 동작하는 단순 질문, 단일 상품 검색, 단일 주문 조회, 단일 FAQ/지원 문의는 현재 구조를 유지한다.

### 1단계: current-turn goal metadata 추가

기존 `domain`, `intent`, `sub_intent`, `action_mode`, `tool_plan`, `response_decision`은 그대로 둔다.

명확한 복합 목표에만 `goal_steps`를 추가한다.

우선 적용 대상:

- 내 차 기반 추천 + 비교
- 상품명 + 장착 가능 매장 문의
- 매장 후보 선택 후 원래 매장 속성 문의 재개
- 주문 목록 조회 후 특정 상태 follow-up

### 2단계: TurnContract/QC 보정

`goal_steps`를 실제 실행기가 아니라 contract 보정에 먼저 사용한다.

예:

- `resolve_vehicle`이 있으면 `get_my_cars_tool`을 unexpected tool로 보지 않는다.
- `resolve_vehicle` 결과로 `tire_size`가 생기면 product card를 `product_card_without_size`로 차단하지 않는다.
- `recommend_products`가 `product_set`을 만들면 `compare_products`는 그 결과를 입력으로 쓴다.
- store selection goal이 pending이면 사용자의 매장 선택은 새 intent가 아니라 blocked goal resume으로 처리한다.

### 3단계: pending goal resume

사용자 선택이 필요한 경우에만 agenda state를 세션에 저장한다.

예:

- 차량 여러 대 -> 차량 선택 대기
- 상품 후보 여러 개 -> 상품 선택 대기
- 매장 후보 여러 개 -> 매장 선택 대기
- 주문 후보 여러 개 -> 주문 선택 대기
- 사이즈/수량 없음 -> 해당 slot 입력 대기

사용자가 선택하면 기존 goal을 이어서 진행한다.

### 4단계: agenda executor 검토

metadata와 contract 보정 방식이 안정화된 뒤에만 full agenda executor를 검토한다.

executor가 생기더라도 원칙은 같다.

- goal은 순서대로 실행한다.
- required slot이 없으면 그 goal에서 멈춘다.
- 이전 goal의 produced slot만 다음 goal 입력으로 넘긴다.
- 임의 첫 row 선택은 하지 않는다.

## 5개 실행 플랜

아래 5개는 새 기능이라기보다, 이미 산발적으로 구현된 흐름을 goal 기반 구조로 정렬하기 위한 초기 적용 대상이다.

### 1. 내 차 기반 추천

목표:

- `내 차`, `내 차량`, `내 차에 맞는`, `내 차에 적합한` 추천 요청을 vehicle-grounded recommendation으로 고정한다.

실행 구조:

```text
resolve_vehicle
-> recommend_products
```

필요한 구조 변경:

- router가 `turn_complexity=multi_goal` 또는 동등한 metadata를 내려준다.
- `goal_steps`에 `resolve_vehicle`, `recommend_products`를 기록한다.
- `get_my_cars_tool`을 선행 goal의 allowed tool로 인정한다.
- `get_my_cars_tool` 결과에서 `tire_size`가 확보되면 후행 추천 goal의 required slot이 해소된 것으로 본다.
- 차량이 여러 대면 차량 선택에서 멈추고, 선택 후 `recommend_products`부터 재개한다.

회귀 방지:

- 일반 추천인 `올웨더 타이어 추천해줘`는 기존 simple/unsized flow를 유지한다.
- 명시 사이즈 추천은 차량 조회 없이 추천 tool로 간다.

### 2. 추천 상품 비교

목표:

- 추천 결과를 받은 뒤 `장단점 비교`, `뭐가 더 좋아`, `비교해줘` 같은 후속 요청을 기존 `product_set` 기반 비교로 처리한다.
- 한 발화 안의 `추천해줘 + 비교해줘`도 동일한 구조로 처리한다.

실행 구조:

```text
recommend_products
-> compare_products
```

필요한 구조 변경:

- 추천 tool 결과를 `product_set` produced slot으로 기록한다.
- `compare_products`는 `product_set` 없이는 실행하지 않는다.
- `장단점`, `장점`, `단점` 같은 비교 표현은 store slot 후보로 승격하지 않는다.
- 비교 결과는 우선 quickReply summary 또는 텍스트 요약으로 처리하고, 별도 FE template은 후속 결정으로 둔다.

회귀 방지:

- 상품 context가 없는 `장단점 비교해줘`는 무엇을 비교할지 확인한다.
- 상품 비교는 transaction tool 실행을 유발하지 않는다.

### 3. 매장 후보 선택 후 원래 질문 재개

목표:

- 매장 특정이 필요한 질문에서 후보가 나오고, 사용자가 후보를 선택하면 원래 질문을 이어서 답한다.

실행 구조:

```text
resolve_store
-> answer_store_attribute
```

필요한 구조 변경:

- 매장 후보 노출 시 pending goal에 원래 attribute 질문을 저장한다.
- 사용자의 매장 선택은 새 support intent가 아니라 `resolve_store` 완료로 처리한다.
- 선택된 store detail로 `answer_store_attribute`를 실행한다.
- store detail로 검증 불가능하면 확인 필요 답변과 매장 상세 정보를 함께 제공한다.

회귀 방지:

- 후보가 여러 개면 첫 번째 매장을 임의 선택하지 않는다.
- 매장 선택이 아닌 새 질문이 들어오면 pending goal을 무조건 resume하지 않는다.

### 4. 상품명 + 사이즈 선택 후 상품 확정

목표:

- 상품 패밀리/모델명만 있는 질문에서 사이즈 선택을 거쳐 `goods_no`를 확정한다.

실행 구조:

```text
resolve_tire_size
-> resolve_product
```

필요한 구조 변경:

- 모델명만 있고 사이즈가 없으면 사이즈 후보 또는 사이즈 입력 요청에서 멈춘다.
- 사용자가 사이즈를 입력하면 기존 모델명 goal을 이어서 상품번호를 resolve한다.
- 확정된 `goods_no`, `product_name`, `tire_size`를 produced slot으로 저장한다.

회귀 방지:

- 사이즈 없는 상태에서 가격/재고/예약을 단정하지 않는다.
- 유사 모델 첫 row를 임의 선택하지 않는다.

### 5. 주문 목록에서 특정 주문 선택

목표:

- 주문 목록 조회 후 상태/취소/환불 follow-up에서 특정 주문을 안전하게 resolve한다.

실행 구조:

```text
resolve_order
-> answer_order_status
```

필요한 구조 변경:

- 주문 목록 tool 결과를 `order_set` produced slot으로 기록한다.
- 주문번호 suffix, 주문상태, 상품명 등 deterministic signal로 단일 주문을 resolve한다.
- 후보가 여러 개면 주문 선택에서 멈추고, 선택 후 `answer_order_status`를 재개한다.
- 취소/환불 질문은 취소/환불 상태 row selector를 사용한다.

회귀 방지:

- 주문 취소 실행, 결제 변경, 환불 처리 완료 같은 high-risk action은 이 플랜 범위에서 제외한다.
- 조회/상태 안내까지만 먼저 goal 구조에 편입한다.

## 대표 구조 시나리오

### 내 차 기반 올웨더 추천 + 비교

입력:

```text
내 차에 적합한 올웨더 상품 추천해줘. 그리고 추천되는 상품들 장단점 비교해주고
```

목표 구조:

```text
resolve_vehicle
-> recommend_products(scenario=all_weather)
-> compare_products(metric=detail)
```

기대 실행:

- `get_my_cars_tool`로 차량 조회
- 차량이 1대 또는 확정 가능하면 `tire_size` produced
- `get_products_recommendations_tool`에 `tire_size`, `rcmd_type=all_weather`, `season_nm=올웨더` 전달
- 추천 결과 `product_set` produced
- 같은 `product_set`으로 장단점 비교 요약
- store slot 생성 없음
- product card 차단 없음

### 상품명 기반 장착 가능 매장 문의

입력:

```text
벤투스 S2 AS 내일 장착 가능 매장은?
```

목표 구조:

```text
resolve_tire_size
-> resolve_quantity
-> resolve_product
-> search_installable_stores
```

기대 실행:

- 사이즈가 없으면 사이즈 확인
- 수량이 없으면 기본값을 임의로 넣지 말고 확인 또는 정책상 기본 수량을 명시
- 모델명+사이즈로 `goods_no` 확보
- 날짜 조건으로 매장 재고/스케줄 검색

### 매장 후보 선택 후 원래 질문 재개

입력 흐름:

```text
야간정비도 가능한가요? 티스테이션 정자점
-> 매장 후보 노출
-> 티스테이션 분당정자점 선택
```

목표 구조:

```text
resolve_store
-> answer_store_attribute(attribute=night_service)
```

기대 실행:

- 후보 선택은 새 support 답변이 아니라 `resolve_store` 완료로 처리
- 선택된 store detail로 원래 attribute 질문에 답변
- detail로 검증이 안 되면 확인 필요 안내 + 매장 상세 정보 제공

## 회귀 위험 제어 기준

- 기존 단일 intent pipeline을 한 번에 제거하지 않는다.
- `goal_steps`는 처음에는 실행 기준이 아니라 contract/QC 보정 기준으로만 사용한다.
- `goal_steps`만으로 domain을 변경하지 않는다.
- transaction tool 실행은 기존 transaction policy/slot guard를 계속 통과해야 한다.
- raw regex candidate는 slot으로 바로 승격하지 않는다.
- 후보가 여러 개면 첫 row를 고르지 않고 사용자 선택을 받는다.
- tests는 문구 하나가 아니라 "복합 목표 + 선행 slot produced + 후행 goal resume" 원인 계열을 고정한다.

## 테스트 기준

필수 테스트 축:

- router 결과가 올바른지
- `goal_steps`가 기대 순서로 생성되는지
- 선행 tool이 `allowed_tools`에 포함되는지
- 선행 tool의 `produced_slots`가 후행 goal의 `required_slots`를 해소하는지
- template/QC가 해소된 slot을 반영하는지
- 후보 선택 후 기존 goal이 resume 되는지
- stale context나 regex candidate가 현재 goal을 오염시키지 않는지

대표 테스트:

- `내 차에 적합한 올웨더 상품 추천해줘. 그리고 추천되는 상품들 장단점 비교해주고`
- `장단점 비교해줘`
- `벤투스 S2 AS 내일 장착 가능 매장은?`
- `정자점 야간정비 가능?` 후 매장 후보 선택
- `주문 취소했는데 카드사 환불 처리 언제됨?`

## 남은 구조 결정 사항

- `goal_steps`는 1차 적용에서 `TurnContract` dedicated field로 추가했다. 아직 실행기는 아니며, contract/QC 보정 metadata로만 사용한다.
- agenda state를 어느 시점부터 Redis/session에 저장할지 결정해야 한다.
- 비교 결과를 quickReply summary, 표 형태 텍스트, 별도 FE template 중 무엇으로 표준화할지 결정해야 한다.
- full agenda executor를 도입하기 전까지 contract 보정만으로 처리할 flow 범위를 정해야 한다.

## 2026-06-26 1차 적용 기록

`multi_goal_policy.py`를 추가해 명확한 복합 목표에서만 `goal_steps`를 만든다.

초기 적용 대상은 아래 조합으로 제한했다.

- `resolve_vehicle -> recommend_products`
- `recommend_products -> compare_products`
- `resolve_store -> answer_store_attribute`
- `resolve_tire_size -> resolve_product`
- `resolve_order -> answer_order_status`

적용 방식:

- 기존 router/domain/intent/action/tool 실행 흐름은 바꾸지 않는다.
- `TurnContract`에 `turn_complexity`, `goal_steps`, `produced_slots`를 노출한다.
- `goal_steps.allowed_tools`는 contract의 allowed tool에 병합해 선행 goal tool을 unexpected tool로 보지 않는다.
- 호출된 선행 tool이 만든 `produced_slots`는 QC/template guard에서 same-turn 해소 슬롯으로 인정한다.
- simple 추천 턴에는 차량 goal을 붙이지 않아 기존 unsized/simple flow를 유지한다.
- 매장 후보 선택 payload에는 `goal_steps`, `turnComplexity`, `pendingGoal`을 남겨 선택 턴이 새 질문이 아니라
  `answer_store_attribute` resume임을 복원할 수 있게 한다.

## 2026-06-26 추가 설계 기록: router/TurnContract intent 소유권 회복

현재 브랜치의 원래 목적은 current-turn intent를 router와 TurnContract가 소유하게 만드는 것이다.

그러나 실제 코드에는 이전 구조에서 남은 regex 기반 fast-path와 code-emitted `quickReply`/`data` path가 아직 존재한다. 이 path들은
router/TurnContract가 판단한 intent와 다른 user-visible action을 직접 만들 수 있어, 사용자가 보기에는 "챗봇이 의도를 못 알아듣는"
형태의 회귀로 나타난다.

### 현재 수정 목표

목표:

```text
Align T-Station AI routing with current-turn intent ownership by removing or gating legacy regex/code fast-path paths
that can override the LLM router and TurnContract.
```

수정 범위:

- `store_attribute_inquiry`, coupon, order cancel/status/refund, reservation flow의 direct `quickReply`/`data` emit path를 audit/refactor한다.
- code fast-path는 active `TurnContract.intent`, template, action mode와 일치할 때만 emit한다.
- regex 기반 intent path는 candidate signal, slot extraction, safety guard로 강등한다.
- store-name regex match가 support/warranty/complaint intent를 override하지 못하게 한다.
- 의미가 동일한 warranty/store/coupon/order intent anchor와 slot regex는 shared helper로 통합한다.

성공 기준:

- user-visible tool/template/CTA/code-emitted event의 source of truth는 router/TurnContract intent다.
- current contract가 `warranty_claim` 또는 다른 support intent이면 `store_attribute` direct response는 금지된다.
- store name은 store attribute 동작을 열기 전에 `target` 또는 `context`로 분류된다.
- 의미가 같은 duplicated regex/helper는 안전한 범위에서 공유 정의로 통합된다.
- trace에는 router intent, policy intent, contract intent, override reason, code fast-path contract gate 결과가 남는다.
- regression test는 문구 하나가 아니라 invariant를 검증한다.

대표 invariant:

```text
router/contract = warranty_claim
+ store name present
=> store_attribute direct emit forbidden
```

```text
router/contract = store_attribute_inquiry
+ explicit store service question
=> store_attribute direct emit allowed
```

```text
router/contract = coupon how-to
=> owned coupon lookup tool/template forbidden
```

```text
router/contract = order cancel fee inquiry
=> cancel execution guidance forbidden
```

핵심은 regex가 무엇을 찾았는지가 아니라, regex 결과가 current TurnContract를 바꾸거나 직접 action을 만들 수 없게 하는 것이다.

### Direct emit path 정리 원칙

기존 direct emit path는 아래 조건을 모두 만족할 때만 허용한다.

- 현재 `TurnContract.intent`와 code event의 intent가 일치한다.
- `TurnContract.response_decision.template` 또는 action mode가 해당 template/action을 허용한다.
- forbidden tool/template/CTA/action에 걸리지 않는다.
- emit metadata에 `assistant_response_source`, `contract_intent`, `contract_matched`, `contract_gate_reason`을 남긴다.

일치하지 않으면 direct emit fallback을 만들지 않고 agent/router/contract flow로 되돌린다.

우선 audit 대상:

- `_store_attribute_inquiry_event`
- coupon issue/applicability/owned lookup 관련 code fallback/event
- order cancel/status/refund 관련 code fallback/event
- reservation/datepick/preOrder/quick_order 관련 code path

### Regex 권한 재정의

regex가 계속 담당해도 되는 영역:

- 차량번호, 주문번호, 배송번호, 쿠폰번호, 상품번호 같은 구조화 ID 추출
- 타이어 사이즈, 수량, 날짜/시간 추출
- 명백한 safety guard
- LLM/router 결과 검증 또는 좁은 보정

regex가 단독으로 담당하면 안 되는 영역:

- 보증 claim vs 매장 속성 문의 최종 결정
- 쿠폰 사용법 vs 보유 쿠폰 조회 최종 결정
- 상품 추천 vs 가격/재고/구매 최종 결정
- 예약 취소 요청 vs 취소 위약금 문의 최종 결정
- store name이 action target인지 단순 context인지 결정하지 않은 상태의 store flow 실행

### Active/interrupted/resumed goal 설계

대화 중 주문, 예약, 추천 같은 목표가 진행 중일 때 새 질문이 들어오는 경우를 case-by-case regex로 막지 않는다.

목표 상태를 다음처럼 일반화한다.

```text
active goal
-> same_goal: 계속 진행
-> interrupting_question: 기존 goal은 dormant/interrupted로 보존하고 현재 질문에 답변
-> resumed_goal: 명시적 재개 anchor가 있을 때만 이전 goal을 resumed로 승격
-> replacement_goal: 새 목표가 기존 목표를 대체하면 기존 goal abandon/reset
```

예시:

```text
현재 active goal = 주문 진행

사용자: 이 타이어 보증서비스 돼?
=> relation_to_active_goal = interrupting_question
=> order goal은 dormant로 보존
=> warranty/support 답변
=> preOrder/datepick/quick_order emit 금지

사용자: 아까 주문 계속하자
=> relation_to_active_goal = resumed_goal
=> dormant order goal을 resumed로 승격
=> 저장된 주문 slot 재사용 가능

사용자: 그건 됐고 다른 타이어 추천해줘
=> relation_to_active_goal = replacement_goal
=> 기존 order goal abandon/reset
=> discovery recommendation goal 시작
```

router schema 또는 TurnContract metadata에는 장기적으로 아래와 같은 관계 필드를 둔다.

```json
{
  "current_intent": "warranty_claim",
  "current_domain": "support",
  "relation_to_active_goal": "interrupting_question",
  "active_goal_should_remain": true,
  "active_goal_should_resume_now": false,
  "active_goal_should_reset": false
}
```

이 구조의 목적은 이전 주문/예약 context를 지우지 않고 보존하되, 현재 턴에서 실행 권한을 제거하는 것이다.

원칙:

- 이전 goal context는 reference로 사용할 수 있지만 action을 시작할 수 없다.
- 명시적 resume anchor 없이 `pending_intent=order`, `goal_type=place_order`, latest `preOrder/datepick`만으로
  purchase/datepick/quick_order action을 실행하지 않는다.
- 현재 질문이 support/discovery/policy/owned-record lookup이면 이전 transaction context는 dormant가 된다.
- dormant goal은 사용자가 명시적으로 재개할 때만 active/resumed가 된다.

### 주제 전환 회귀 테스트 기준

필수 invariant:

- preOrder 이후 `이 타이어 보증서비스 돼?` -> support/warranty, preOrder/datepick/quick_order 금지
- 주문 플로우 중 `쿠폰 등록은 어디서 해?` -> coupon how-to/support policy, purchase continuation 금지
- 주문 플로우 중 `온라인 가격이랑 매장 가격 왜 달라?` -> support price policy, price/order tool 강제 금지
- 주문 플로우 중 `다른 추천 보여줘` -> discovery recommendation, stale order context action 금지
- preOrder 직후 `네 진행해` -> explicit confirmation으로 quick_order_execute 허용

이 테스트들은 특정 문구 대응이 아니라 active goal relation과 TurnContract action gate가 지켜지는지 검증해야 한다.

### 2026-06-26 적용 결과: direct fast-path contract gate 확대

이번 적용의 구조적 결론은 다음과 같다.

- `router/TurnContract -> tool/template/CTA/direct emit` 순서를 기준 실행 경계로 고정한다.
- code fast-path는 더 이상 user-visible event를 스스로 확정하지 않고, `TurnContract`와 일치할 때만 emit한다.
- regex는 현재 턴 action을 여는 결정자가 아니라 slot 추출, candidate signal, safety guard, 좁은 보정으로 제한한다.
- store name은 매장 action target인지, 과거 교체/방문/구매 context인지 먼저 분류한다.
- context store가 support/warranty/complaint intent의 설명 정보일 때는 store attribute, store detail, store holiday,
  store schedule flow를 열지 않는다.

구현상 공통 경계는 아래 helper에 모았다.

- `_direct_code_fast_path_contract_gate()`
  - `TurnContract.intent` 또는 response shape가 code path intent와 일치하는지 확인한다.
  - emitted template이 contract forbidden template에 걸리지 않는지 확인한다.
  - `required_tools`가 `forbidden_tools`에 걸리지 않고, `allowed_tools` 안에 있는지 확인한다.
  - `allowed_tools=()`는 "제한 없음"이 아니라 "tool 허용 없음"으로 해석한다.
- `_finalize_direct_code_event()`
  - 실제 emitted template 기준으로 마지막 gate를 수행한다.
  - 허용 event에는 `contract_intent`, `contract_gate_result`, `contract_gate_reason`, `direct_source`,
    `emitted_template`, `required_tools` metadata를 남긴다.
- `_finalize_coerced_template_event()`
  - `quickReply -> datepick`, `quickReply -> preOrder` 같은 coercer/normalizer 변형 직후에도 template contract를 다시 확인한다.
  - 위반 시 변형 event를 버리고 원본 event에 `blocked_template`, `transform_source`, `contract_gate_result`를 남긴다.
- synthetic policy guard contract
  - classifier/TurnContract 이전 safety/policy guard도 `exempt`로 우회하지 않고, synthetic contract를 만들어 동일한 metadata 체계로 기록한다.

이번 적용에서 gate 대상에 포함한 대표 경로:

- store attribute/detail/holiday/service availability
- coupon owned lookup/applicability/issue/channel policy
- order cancel/status/refund/arrival/payment method/order-history reorder
- reservation store info/datepick/preOrder/quick order execute
- pure inventory stock follow-up
- product comparison/detail/attribute/size list/quantity benefit/multi-variant recommendation
- selected vehicle auto-continuation purchase/recommendation/OE guidance
- streaming 후처리 coercer/normalizer replacement
- no-visible-output fallback, required-slot clarification, generic policy guard

원래 클레임 계열에 대한 구조적 처리:

```text
사용자 발화:
"35버0991 차량에 웨더플렉스GT 4개 장착해서 끼고 있는 중인데
 광교신도시점에서 교체한 뒤 사이드월이 벌써 갈라졌어. 보증서비스 확인해줘"

store name role = context
cross-domain = support / policy_notice_or_escalation
transaction frame = transaction_fallback
allowed transaction tools = ()
store_attribute/store_schedule direct emit = forbidden
```

여기서 `광교신도시점`은 사용자의 현재 요청 대상이 아니라 과거 교체 장소 설명이다.
따라서 store regex match가 있더라도 `get_store_detail_tool`, `get_store_schedule_tool`, store attribute quickReply를 열 수 없다.
반대로 아래처럼 현재 턴 목적이 명시적인 매장 예약/시간 확인이면 기존 transaction flow를 유지한다.

```text
사용자 발화:
"광교신도시점 예약 가능 시간 확인해줘"

store name role = target
cross-domain = transaction
transaction frame = store_schedule / store_visit
allowed tools includes get_store_schedule_tool
```

이번 단계에서 확인한 주요 invariant:

- support/warranty contract에서는 store attribute/detail/schedule direct emit 금지
- empty `allowed_tools` contract에서는 required tool을 가진 fast-path 금지
- pure inventory stock follow-up은 inventory-only contract를 유지해 `get_store_inventory_tool`과
  `get_logistics_inventory_tool` allowlist를 보존
- explicit store schedule request는 정상적으로 `store_schedule` contract와 datepick/store schedule tool을 유지
- coercer/normalizer가 template을 바꾸더라도 최종 emitted template은 contract validation을 통과해야 함

검증 기록:

- `ruff check` 대상 변경 파일 통과
- untracked policy/regression test 묶음: `228 passed, 4 warnings`
- `test_quickreply_fallback_routing.py`: `1083 passed, 2 warnings`
- 원래 보증/사이드월/광교신도시점 원문 재현:
  - `store_role=context`
  - `store_attribute=None`
  - `cross_domain=SUPPORT`
  - `transaction_frame=transaction_fallback`
  - `allowed_tools=()`

남은 구조적 주의점:

- `.gitignore`에서 `app/tstation-ai/tests/` ignore가 제거되어 기존 untracked regression test들이 커밋 대상으로 노출된다.
  이번 브랜치에서 테스트를 함께 버전 관리할 의도가 맞는지 커밋 전에 스코프를 확인해야 한다.
- active/interrupted/resumed goal relation은 아직 완전한 router schema field로 승격되지는 않았다.
  현재 적용은 `action_mode`, `context_state`, `resume_source`, TurnContract gate, dormant context 원칙으로 같은 효과를 좁게 구현한 상태다.

## 2026-06-26 현재 상태 보정: 커밋 히스토리 기준 적용/설계 구분

현재 기준 브랜치:

```text
stabilize-turn-contract-policy
HEAD = 1eb46d2 Ground support QC in FAQ sources
origin/stabilize-turn-contract-policy = 1eb46d2
```

현재 구조를 해석할 때는 아래 커밋 흐름을 기준으로 본다.

```text
822de6b Add store service search intent
bf0a95b Restore store service search transaction contract
fc29be8 Sync store service search current-turn slots
22a5bd2 Route signup benefits through FAQ policy
28e2875 Split partner-member coupon policy intent
8c9bab4 Separate signup coupon guidance intent
36d889c Lock turn contracts to confirmed router results
1a75cd7 Split card cancel timing from order status lookup
b3a2156 Narrow card cancel timing policy anchors
3fe8428 Guide order document support intent
8fd11d2 Prioritize support FAQ policy buckets
f406f58 Correct signup coupon policy guidance
1eb46d2 Ground support QC in FAQ sources
```

반대로 multi-goal agenda executor 계열 실험은 아래 revert 커밋들이 존재한다.

```text
384085b Revert "Append recommendation comparison by goal"
c1fb907 Revert "Refine recommendation comparison and size followup"
a4b375a Revert "Add multi-goal turn contract metadata"
```

따라서 이 문서 앞부분의 `goal_steps`, `turn_complexity`, multi-goal agenda 적용 기록은 현재 HEAD에서 동작 중인
적용 사항이 아니라 **설계 히스토리와 재검토 후보**로 해석한다. 현재 active 구조의 중심은 full agenda executor가 아니라
`router/policy -> TurnContract -> allowed tools/templates/CTA -> QC/contract violation` 경계다.

현재 코드 기준 적용 완료로 보는 항목:

- `store_service_search` intent와 transaction contract 복원
- router가 낸 store service search 슬롯의 current-turn working slot 동기화
- store service search에서 이전 `region`, `user_preferences_text`, `availability_context`, tool context가 현재 region/service와 충돌하면
  dormant 또는 prompt 제외 처리
- partner-member coupon policy와 signup coupon guidance 분리
- signup/new-member/first-purchase benefit 문의를 FAQ/support policy로 고정
- 주문 증빙/거래명세서 intent를 `order_document_guidance`로 분리하고 주문 내역 CTA 우선화
- 일반 카드 승인취소/환불 반영 기간을 주문 상태 조회와 분리
- FAQ-first support policy bucket 7개 추가
- FAQ source 기반 support QC 보강

현재 로컬 미커밋 변경으로 확인되는 항목:

- OE/RE 관련 router prompt taxonomy 추가
- OE replacement quickReply에 `intentKey=oe_replacement`, `metadata.ctaContext.source_intent`,
  `expected_contract_intent`를 붙이는 보정
- `_is_oe_replacement_context()`가 recent context regex만으로 발동하지 않고 current turn의 명시 OE/RE 발화 또는
  OE CTA metadata가 있을 때만 follow-up으로 인정하도록 축소

현재 로컬 미커밋 변경 중 `cross_domain_policy.py`, `store_service_gate.py`는 status에는 보이나 diff stat에는 잡히지 않는다.
현 시점 문서 기준으로는 실제 구조 변경 내용이 있는 파일은 `chat.py`와 `test_quickreply_fallback_routing.py` 중심으로 본다.

## 2026-06-26 현재 상태: coupon/store/FAQ policy 정리

### Coupon policy

현재 coupon intent는 아래처럼 분리되어 있다.

- `owned_coupon_lookup`
  - 보유 쿠폰 조회
  - `get_my_coupons_tool` 기반 transaction flow
- `partner_member_coupon_policy`
  - 제휴회원, 제휴사, 복지몰, 임직원 전용 쿠폰/혜택 접근 조건 안내
  - 보유 쿠폰 조회가 아니라 제휴 전용 접속 경로, 권한, 기간 정책 안내
  - `get_my_coupons_tool`, `issue_coupon_tool`, `get_coupon_applicable_products_tool` 금지
- `signup_coupon_guidance`
  - 회원가입 전용, 신규회원, 웰컴, 첫구매 쿠폰처럼 묻는 표현을 받는다
  - 실제 정책 문구는 "첫구매 전용"이 아니라 `all my T 회원 + 마케팅 수신 동의` 조건으로 안내한다
  - `회원 혜택 확인` CTA를 제공한다
- `signup_first_purchase_benefit_policy`
  - 사용자가 첫구매 혜택이라고 물어도 첫구매 전용 쿠폰으로 단정하지 않는다
  - 확인된 정책 기준으로 `all my T 회원이고 마케팅 수신 동의를 하면 5% 할인 쿠폰 발급 가능`이라고 안내한다
  - 계정의 회원 상태, 마케팅 동의 상태, 발급 여부는 챗봇이 직접 확정하지 않는다

회원 혜택 CTA:

```json
{
  "label": "회원 혜택 확인",
  "url": "https://www.tstation.com/membership/dashboard/benefit",
  "domain": "SUPPORT"
}
```

금지 invariant:

```text
signup_coupon_guidance
=> get_my_coupons_tool forbidden
=> issue_coupon_tool forbidden
=> transfer_to_qna_tool/qnaComplete direct-first forbidden
=> "첫구매 전용" 단정 forbidden
=> "이미 발급" 단정 forbidden
```

```text
partner_member_coupon_policy
=> owned coupon voucher/listing forbidden
=> signup coupon guidance로 흡수 forbidden
=> 현재 사용자가 제휴회원임을 검증했다고 단정 forbidden
```

### Store service search context sync

`store_service_search`는 현재 턴 router structured fields를 source of truth로 본다.

필수 current-turn slot:

- `policy_intent=store_service_search`
- `service_name` 또는 `service_code`
- `region` 또는 `place_query`

현재 동작:

- router slot이 충족되면 `merged_slots.region`, `service_name`, `service_codes`를 현재 턴 기준으로 동기화한다.
- 이전 `region`이나 `user_preferences_text`가 현재 region/service와 충돌하면 active prompt에서 제거하고
  `dormant_store_finder_context`로 보관한다.
- 이전 tool context는 현재 `region/place_query/service_codes`와 맞지 않으면 prompt 주입에서 제외한다.

대표 원인 계열:

```text
이전 턴: 강남 키즈존/쾌적한 매장 추천
현재 턴: 경기권 타이어 보관 매장 어디 있어?

=> tool args는 경기/119로 맞더라도 prompt known_slots에 강남/키즈존이 남으면 답변이 오염된다.
=> 현재 구현은 store_service_search router slots를 BE/tool 호출 전 working slots에 반영하고,
   stale preference/tool context를 prompt에서 제외하는 방향이다.
```

### FAQ-first support policy bucket

현재 7개 deterministic support policy bucket은 적용된 상태다.

- `tire_manufacture_date_policy`
- `tire_quality_warranty_policy`
- `assurance_service_policy`
- `reservation_policy_guidance`
- `installation_work_policy`
- `promotion_gift_policy`
- `tire_condition_photo_policy`

공통 순서:

```text
명시적 1:1/상담원/접수 요청
-> escalation 허용

그 외 정책성 질문
-> deterministic FAQ policy bucket 우선
-> search_faq_hybrid_tool
-> FAQ/RAG 근거 기반 quickReply
-> 근거 부족/해결 불가 시에만 1:1 문의 보조
```

공통 금지:

- `transfer_to_qna_tool` direct-first
- `qnaComplete` direct-first
- FAQ/RAG 또는 policy 근거 없이 교환/환불/보상/안전 여부 확정
- owned anchor 없이 개인 주문/예약 조회 시작
- 매장명/과거 방문 정보만으로 store attribute inquiry 전환

현재 `1eb46d2` 이후에는 support QC가 FAQ source와 응답 claim을 대조한다.
예를 들어 제조일자 policy에서 FAQ source가 뒷받침하지 않는 무조건 교환/환불/불량 단정은 contract violation으로 본다.

## 2026-06-26 신규 구조 결정: CTA registry와 실행 계약화

### 문제

현재 quickReply/CTA는 대부분 `label`, `domain`, 선택적 `url` 중심으로 만들어진다.
사용자가 버튼을 누르면 label이 새 user text처럼 들어오고, router/code/regex가 다시 자연어 intent로 해석한다.

이 구조의 문제:

- 버튼의 원래 목적이 사라진다.
- 같은 label이 다른 intent에서 다른 의미로 쓰일 수 있다.
- 이전 context나 후처리 regex가 버튼 클릭을 잘못 해석한다.
- 실제 FE/BE 동작이 없는 CTA가 노출될 수 있다.
- contract가 허용하지 않은 tool/template으로 후속 턴이 이동할 수 있다.

대표 장애:

```text
사용자: 17인치에서 19인치로 인치업 하려면 타이어 규격 어떻게 바꿔야 해?
AI: 정상 인치업 규격 안내 + "내 차량으로 확인" CTA
사용자: "내 차량으로 확인" 클릭

실제 agent: get_my_cars_tool 호출, 차량 목록 생성
최종 응답: code_oe_replacement_guidance로 교체

원인: 버튼 label만 재해석되면서 recent context의 OE/RE 문구가 후처리 조건을 열었다.
```

### 목표

CTA를 단순 텍스트가 아니라 실행 가능한 action contract로 관리한다.

중앙 파일 후보:

```text
services/tstation/policies/cta_registry.py
```

registry가 관리할 필드:

```json
{
  "label": "내 차량으로 확인",
  "domain": "DISCOVERY",
  "url": null,
  "cta_id": "owned_vehicle.select_for_inch_up",
  "cta_action": "select_owned_vehicle",
  "source_intent": "inch_up_size_guidance",
  "expected_domain": "DISCOVERY",
  "expected_contract_intent": "vehicle_based_inch_up_size_guidance",
  "allowed_tools": ["get_my_cars_tool"],
  "forbidden_tools": [],
  "forbidden_templates": ["oe_replacement_guidance"],
  "required_context": ["source_intent"],
  "fallback_behavior": "ask_vehicle_or_size_again"
}
```

### 적용 방식

1차 목표는 모든 생성부를 한 번에 치환하는 것이 아니다.

우선순위:

1. `build_cta()`, `build_ctas()`, `normalize_cta()`, `validate_cta()` helper를 만든다.
2. 최종 SSE emit 직전 모든 `quickReplies`에 validator를 적용한다.
3. registry에 있는 label/action은 metadata를 보강한다.
4. registry에 없는 동적 chip은 명시 타입을 부여한다.
5. contract와 맞지 않는 CTA는 제거하거나 안전 fallback으로 바꾼다.
6. 위험 CTA부터 생성부를 registry helper로 이관한다.

동적 CTA 타입:

- `dynamic_tire_size`
- `dynamic_store_candidate`
- `dynamic_region_candidate`
- `dynamic_event_candidate`
- `dynamic_product_candidate`
- `dynamic_order_candidate`

우선 registry 대상:

- 차량/사이즈: `내 차량으로 확인`, `내 차량 보기`, `보유차량 중 선택`, `차량번호로 확인`, `차번+이름으로 검색`,
  `사이즈 직접 입력`
- 주문/문서: `주문 내역 확인`, `주문 내역 보기`, `주문 상세 확인`
- coupon/member: `쿠폰함 바로가기`, `내 쿠폰함`, `회원 혜택 확인`
- support: `1:1 문의하기`, `상담사 연결`, `고객센터 안내`
- store/reservation: `매장 찾기`, `다른 매장 찾기`, `예약 가능 시간 확인`, `다른 날짜 확인`
- purchase/cart: `구매하기`, `장바구니 확인`, `장바구니 보기`

### 클릭 처리 원칙

기존:

```text
button label
-> user text
-> router/code/regex reinterpretation
```

변경:

```text
button label + CTA metadata
-> current-turn contract seed
-> router는 metadata를 참고하되, 사용자가 추가 입력한 자연어가 있으면 current text 우선
-> TurnContract가 expected_contract_intent/allowed_tools/forbidden_templates로 후속 실행 제한
```

### 검증 기준

- CTA마다 실제 FE/BE 동작이 있어야 한다.
- URL CTA는 URL이 있어야 한다.
- tool 실행 CTA는 allowed tool이 정의되어야 한다.
- 필요한 context가 없으면 fallback이 정의되어야 한다.
- invalid CTA 발생 시 trace에 `cta_action`, `expected_contract_intent`, `actual_contract_intent`, `called_tools`,
  `final_template`, `fallback_behavior`를 남긴다.

## 2026-06-26 신규 구조 결정: OE/RE는 router intent와 CTA metadata로 발동

### 현재 상태

HEAD 기준 OE/RE 처리는 아직 일부 regex/code 후처리에 의존한다.
로컬 미커밋 변경에서는 router prompt에 OE/RE taxonomy를 추가하고, OE CTA metadata가 있을 때만 label-only follow-up을
OE context로 인정하도록 축소했다.

추가된 router taxonomy 방향:

- `discovery:oe_re_concept_explanation`
- `discovery:oe_re_product_filter`

대표 발화:

- `OE랑 RE 차이가 뭐야?`
- `순정 타이어가 뭐야?`
- `출고 때 끼워진 거랑 같은 타이어 있어?`
- `순정이랑 비슷한 교체용 추천해줘`
- `2454518 사이즈 OE 타이어 있어?`

### 발동 원칙

OE/RE flow는 아래 경우에만 발동한다.

- 현재 user text가 OE/RE/순정/출고/교체용을 직접 묻는다.
- router가 OE/RE 계열 discovery plan을 낸다.
- 직전 CTA metadata가 OE/RE 계열이다.
- 차량 선택 후 CTA action이 `oe_same_product_lookup` 또는 `oe_replacement_recommendation`이다.

금지:

- recent context에 `OE`, `RE`, `순정`, `출고`, `같은 상품` 단어가 있다는 이유만으로 발동
- contract intent가 OE 계열이 아닌데 `code_oe_replacement_guidance`로 template coercion
- 인치업/차량 규격/일반 추천의 `내 차량으로 확인` 클릭을 OE guidance로 교체
- `listCar` 결과를 OE quickReply로 덮어쓰기

### 구현 방향

정규식은 OE/RE 발화 후보 감지나 safety check 정도로만 남긴다.
최종 발동 권한은 router intent 또는 CTA metadata가 가져야 한다.

단기 보정:

- OE guidance가 만든 quickReply에는 `intentKey=oe_replacement`와 `metadata.ctaContext`를 붙인다.
- `_is_oe_replacement_context()`는 current text가 명시 OE/RE 질의일 때는 허용한다.
- label-only follow-up은 최신 quickReply의 CTA context가 OE 계열일 때만 허용한다.

장기 보정:

- `oe_re_explanation`
- `oe_same_product_lookup`
- `oe_replacement_recommendation`
- `oe_re_product_filter_summary`

를 TurnContract intent/response decision으로 명시하고, 일반 recommendation/inch-up/vehicle-information contract에서는
OE guidance를 forbidden template으로 둔다.

## 2026-06-26 신규 구조 결정: `chat.py`는 orchestration 중심으로 점진 분리

### 현재 상태

최신 코드 기준:

```text
branch: stabilize-turn-contract-policy
HEAD: f498376 Resolve purchase size selection from product search
chat.py: 37,085 lines
ui_action_policy.py: 5,741 lines
flow_controller.py: 796 lines
cta_registry.py: 532 lines
```

`services/tstation/chat.py`는 일부 helper를 policy layer로 분리했지만, 여전히 단순 orchestration을 넘어 아래 책임을
동시에 가진다.

- router 결과 보정
- TurnContract 생성/검증 및 direct code fast-path gate
- quickReply/CTA 생성, 보정, validation
- `listCar`/product/store/schedule 등 UI 선택 이벤트 처리
- 차량/매장/쿠폰/주문/예약/support별 특수 fallback
- stale slot 정리와 current-turn slot rewrite
- template coercion, destination CTA injection, Langfuse trace metadata 구성

이 구조에서는 한 기능을 수정해도 다른 code path가 같은 의도/CTA/slot을 다시 해석할 수 있다. `listCar` 차량
선택, 상품 후보 선택, 수량/매장/스케줄 선택, 구매 CTA, 재고/예약 follow-up이 같은 계열이다. `listCar` 자체는
CTA가 아니지만, 그 안의 차량 카드 클릭은 user-visible interactive action이다. 따라서 CTA만 별도로 보는 대신
UI action 전체를 하나의 정책 경계로 다룬다.

### 현재까지 분리된 영역

`ui_action_policy.py`는 계획 단계가 아니라 이미 공통 UI action 정책 레이어로 사용 중이다.

분리 완료 또는 부분 완료된 영역:

- quickReply/CTA metadata 정규화 일부
- product/list candidate 선택에서 `goods_no` 해석
- `listCar` 차량 선택 slot patch와 staggered tire size 후속 선택
- purchase/cart CTA에서 confirmed product recovery
- `preOrder` / `datepick` template slot recovery
- preview store selection의 selected order context recovery
- OE replacement guidance/follow-up CTA metadata
- store availability size-only / quantity-only / product-selection continuation helper
- store availability follow-up context, action decision, preview event/status payload builder

아직 `chat.py`에 남아 있는 책임:

- router/classifier 호출 순서와 slot-fill context 주입
- TurnContract 생성/보정과 post-tool contract rebuild
- 일부 direct deterministic dispatch와 fast-path event emit
- tool invoke 자체와 final SSE emit orchestration
- Langfuse trace metadata 조립 일부

따라서 현재 목표는 `ui_action_policy.py`를 새로 만드는 것이 아니라, 이미 분리된 policy helper를 기준으로
`chat.py`의 남은 분기와 direct helper를 더 얇은 호출부로 줄이는 것이다.

### 리팩토링 원칙

목표는 파일 줄 수를 줄이는 것이 아니라 실행 경계를 명확히 하는 것이다.

```text
User input / UI action
-> router/classifier
-> policy / TurnContract
-> slot rewrite
-> allowed tool/template/CTA
-> final emit / trace
```

`chat.py`에는 위 흐름의 호출 순서만 남기고, UI action 해석과 slot patch, CTA validation은 별도 policy 모듈로 이동한다.

금지 방향:

- 줄 수를 줄이기 위한 무작위 함수 이동
- `chat.py`에 `if listCar`, `if vehicle selected`, `if CTA label` 분기를 계속 추가
- 차량번호/버튼 label을 정규식으로만 감지해 flow를 확정
- direct resolver가 TurnContract 밖에서 user-visible response를 직접 emit

### 1차 분리 대상: UI action policy

현재 파일:

```text
services/tstation/policies/ui_action_policy.py
```

초기 판단처럼 `cta_registry.py`, CTA validation, selection context를 무리하게 3개 파일로 쪼개지는 않았다.
상위 개념은 CTA가 아니라 user-visible UI action이므로, 현재는 `ui_action_policy.py`가 선택/CTA/slot patch helper의
중심 역할을 한다. `cta_registry.py`는 별도 파일로 존재하지만, CTA 전체 실행 계약의 단일 소스는 아직 완성되지 않았다.

포함 범위:

- quickReply CTA
- URL CTA
- conversation-action CTA
- dynamic chip
- `listCar` 차량 선택
- product/store candidate selection
- schedule/date selection
- `actionId`, `intentKey`, `chip_context`, `ctaContext`
- `source_intent`, `expected_contract_intent`
- 선택 entity metadata

내부 섹션:

```python
# ui_action_policy.py

# 1. Data models
# CTADefinition / UIActionContext / SelectionContext

# 2. Registry
# known URL CTA, conversation CTA, dynamic action type

# 3. Normalize
# normalize quickReply / chip / card action metadata

# 4. Validate
# validate action against TurnContract

# 5. Selection resolve
# resolve listCar/product/store/schedule selection

# 6. Slot patch
# build current-turn slot patch from selected entity
```

### `listCar` 처리 원칙

`listCar`는 template이고 CTA가 아니다. 그러나 차량 카드 클릭은 `select_vehicle_candidate` action이다.

기존 위험 흐름:

```text
listCar 표시
-> 차량번호 label만 다음 턴 content로 전송
-> router/code/regex가 일반 text로 재해석
-> listCar 재표출 또는 stale slot 유지
```

변경 흐름:

```text
listCar 표시
-> 차량 카드 클릭 + selected row metadata 전송
-> ui_action_policy가 직전 후보와 매칭
-> TurnContract/known_slots/resolved_context를 선택 차량 기준으로 갱신
-> 원래 source_intent를 재개
```

필수 metadata:

```json
{
  "cta_action": "select_vehicle_candidate",
  "source_intent": "vehicle_tire_size_lookup",
  "car_no": "14다5499",
  "mbr_car_reg_seq": "...",
  "car_lnc_cd": "...",
  "car_type": "...",
  "vehicle_type": "...",
  "tire_size_fr": "2255518",
  "tire_size_re": "2255518"
}
```

### 규모

초기 예상:

- CTA/chip context helper: 약 250~400 lines
- CTA action preview/guard 일부: 약 400~700 lines
- `listCar` 차량 선택 resolve/helper: 약 600~900 lines
- 차량 선택 slot patch/helper: 약 200~350 lines
- selection trace metadata 구성: 약 100~200 lines

```text
현재 chat.py: 약 34k lines
1차 분리 후 chat.py: 약 32k lines 전후
신규 ui_action_policy.py: 약 1.8k~2.5k lines 예상
```

최신 코드 기준:

```text
chat.py: 37,085 lines
ui_action_policy.py: 5,741 lines
flow_controller.py: 796 lines
cta_registry.py: 532 lines
```

초기 예상과 달리 `chat.py` 줄 수는 줄지 않았다. 구매/재고/베스트셀러/FAQ/CTA 회귀 대응 과정에서 orchestration
본문에 새로운 contract recovery, deterministic dispatch, trace metadata 조립이 추가됐기 때문이다. 다만 많은
selection/slot recovery helper는 `ui_action_policy.py`로 이동해 책임 경계는 일부 개선됐다.

핵심 효과는 줄 수 감소보다 `chat.py`에서 UI action, selection, slot rewrite 책임이 점진적으로 빠지고, 새
interactive action이 추가될 때 같은 경계에서 관리된다는 점이다.

### 남은 단계

1. `chat.py`에 남은 label/chip/template metadata parsing helper를 `ui_action_policy.py`로 추가 이관한다.
2. `chat.py`의 direct deterministic dispatch는 TurnContract/FlowState에서 계산된 preferred tool/template만 소비하게 줄인다.
3. final emit 직전 quickReply/action validation은 `validate_ui_actions_for_contract()` 계열로 통일한다.
4. URL CTA, conversation CTA, card selection action의 metadata 스키마를 같은 validator에서 검사한다.
5. Langfuse trace에는 `ui_action_detected`, `ui_action_type`, `selection_source`, `expected_contract_intent`,
   `actual_contract_intent`, `slots_rewritten`, `fallback_behavior`를 기록한다.

### 검증 기준

- `내 차에 맞는 타이어 사이즈는?` 후 `listCar` 차량 선택 시 목록 재표출 금지
- 선택 차량의 `tire_size`가 답변 전 `known_slots`에 반영
- 선택 후 CTA가 이전 차량/사이즈가 아니라 선택 차량/사이즈 기준으로 이어짐
- URL CTA는 기존처럼 페이지 이동만 수행하고 router에 재진입하지 않음
- conversation-action CTA는 `expected_contract_intent`와 allowed tool/template을 가진다
- 후보 metadata가 없는 label-only click은 safe fallback 또는 재확인으로 처리

### Latency 영향

1차 리팩토링은 local metadata normalization, selection resolve, slot patch 중심이다. 새 LLM 호출은 추가하지 않는다.
직전 template 후보 데이터를 재사용할 수 있으면 차량 선택 턴의 불필요한 `get_my_cars_tool` 재호출은 줄어들 수 있다.

## 2026-06-27 추가 설계 기록: flow step 결정 책임의 단계적 중앙화

### 배경

최근 구매/재고/매장 선택 흐름에서 반복된 실패는 router가 current-turn intent를 대체로 맞히더라도, 그 다음 단계 결정이
여러 파일에 분산되어 서로 다른 결론을 내기 때문에 발생했다.

대표 케이스:

```text
벤투스 S2 AS 245/45R18 2개 구매할래
```

기대 흐름:

```text
상품 resolve
-> 수량 resolve
-> 매장/지역 요청
-> 매장 확정
-> 스케줄 조회
-> preOrder
```

실제 장애 흐름:

```text
search_product_tool 성공
-> goods_no/tire_size/ord_qty 확보
-> transaction agent가 get_logistics_inventory_tool 또는 get_final_price_tool 제안
-> BaseAgent tool guard가 contract 밖 tool로 차단
-> fallback이 실제 slot state를 반영하지 못해 generic quickReply 출력
```

이 문제는 특정 문구 문제가 아니라, **확정된 TurnContract 안에서 다음 flow step을 어디서 결정하는가**의 문제다.

### 현재 코드 기준 적용 상태

현재 브랜치:

```text
stabilize-turn-contract-policy
HEAD = f498376 Resolve purchase size selection from product search
```

초기에는 `9ff7d3c`에서 아래 보정이 들어갔다.

- `transaction_response_policy.py`
  - `quick_order_reservation`에서 상품/수량은 있고 매장 scope가 없으면 `missing_order_slots.store`로 판단한다.
  - `region/place`는 store candidate step의 유효 store scope로 인정한다.
- `chat.py`
  - `_build_transaction_resolved_product_missing_store_event()`를 추가했다.
  - `search_product_tool` 결과가 단일 상품으로 resolve되고 `pending_intent=order`, `ord_qty`가 있으며 매장/지역이 없으면
    generic fallback 대신 매장/지역 요청 quickReply를 만든다.
- `transaction_intent_policy.py`
  - `quick_order_reservation` required slot 계산에서 region을 store scope로 인정한다.
- `test_quickreply_fallback_routing.py`
  - `test_turn_contract_fallback_event_uses_resolved_product_and_quantity_to_ask_for_store`를 추가했다.

검증된 현재 동작:

```text
상품 resolve + 수량 resolve + 매장 없음
-> "구매를 진행할 매장이나 지역을 알려주세요."
```

단, 이 보정은 주로 `chat.py`의 turn-contract fallback 경로에 들어가 있다.
`BaseAgent._blocked_contract_tool_guard_events()`는 여전히 tool 차단 시 synthetic `TurnContract`를 만들고,
실제 `search_product_tool` 결과나 resolved product context를 충분히 보존하지 못할 수 있다.

이후 최신 코드에서는 `flow_controller.py`가 실제로 추가되어 구매/장바구니 flow step 계산에 사용된다.

현재 `resolve_purchase_order_flow()`가 계산하는 대표 step:

```text
product_name only + tire_size missing
-> ask_size

goods_no missing
-> resolve_product / search_product_tool

quantity missing
-> ask_quantity

cart flow + quantity resolved
-> execute_cart / save_to_cart_tool

store/location missing
-> ask_store

region/place/browser_location present, shop_id missing
-> show_store_candidates / transaction_store_preview_tool

store_name present, shop_id missing
-> resolve_store / transaction_store_preview_tool

shop_id present, booking datetime missing
-> show_schedule / get_store_schedule_tool

booking datetime present
-> build_preorder

quick_order_execute with all slots
-> execute_order / quick_order_tool
```

`transaction_intent_policy.py`와 `transaction_response_policy.py`는 `resolve_purchase_order_flow()`를 호출해
`IntentFrame.missing_slots`, `ToolPlan`, `ResponseDecision`의 flow step을 맞춘다. `chat.py`도 router slot-fill
context 생성, preOrder direct path, post-tool contract rebuild에서 같은 flow state를 참조한다.

### FlowController에 대한 현재 판단

`FlowController`는 이제 별도 파일로 존재하며, 구매/장바구니 flow의 다음 step 계산을 담당한다. 기존에 분산된 아래
책임 중 일부가 이 파일로 이동했다.

```text
현재 contract + slot state + tool results
-> 이 flow의 다음 step
-> 필요한 slot
-> allowed/preferred/forbidden tool
-> allowed template/CTA
-> blocked tool fallback
```

다만 완전한 central controller는 아니다. `IntentFrame`, `ToolPlan`, `ResponseDecision`, `TurnContract`, `BaseAgent`,
`chat.py`가 여전히 각자의 단계에서 flow state를 소비하거나 보정한다. 현재 단계의 결정은 **FlowController가 router를
대체하지 않고, 확정된 transaction contract 안에서 slot state 기반 다음 step만 계산**하도록 제한하는 것이다.

현재 구성요소의 역할:

```text
transaction_intent_policy.py
-> IntentFrame 생성, FlowController 결과로 missing_slots/flow_step 정렬

plan_transaction_tools()
-> FlowController 결과 기반 allowed/preferred/forbidden tool 정렬

transaction_response_policy.py
-> FlowController 결과 기반 response_shape/template/fallback 정렬

turn_contract.py
-> flow_step별 tool/template validation

flow_controller.py
-> purchase/cart flow_id, flow_step, missing_slots, allowed/preferred/forbidden tool, template 계산

base_agent.py
-> tool execution guard, blocked tool fallback
```

### 단기 설계 원칙

아래 metadata는 이미 여러 객체와 trace에 싣는 방향으로 적용되어 있다.

```text
flow_id
flow_step
missing_slot / missing_slots
slot_patch
```

예:

```python
IntentFrame(
    intent="quick_order_reservation",
    known_slots={
        "tire_size": "245/45R18",
        "ord_qty": 2,
        "pending_intent": "order",
        "goal_type": "place_order",
    },
    missing_slots=("store",),
    entities={
        "flow_id": "purchase_order",
        "flow_step": "ask_store",
    },
)
```

`ToolPlan.metadata`와 `ResponseDecision.metadata`에도 같은 `flow_id/flow_step`을 싣는다. BaseAgent guard가 tool을
막을 때는 이 metadata와 `tool_args_patch`를 보존해 fallback contract를 만들어야 한다. 이 부분은 일부 적용됐지만,
모든 flow와 fallback path가 단일 진입으로 정리된 상태는 아니다.

### 구매 flow의 slot 우선순위

`quick_order_reservation` 안에서는 문구가 아니라 slot state로 다음 step을 결정한다.

```text
product missing
-> resolve_product / ask_product_or_size

quantity missing
-> ask_quantity

store missing
-> ask_store_or_region

region present but shop_id missing
-> show_store_candidates

store_name present but shop_id missing
-> resolve_store

shop_id present and booking datetime missing
-> show_schedule

booking datetime present and preOrder not confirmed
-> build_preorder

preOrder confirmed
-> quick_order_execute
```

이 원칙은 아래 두 케이스를 모두 포함해야 한다.

```text
벤투스 S2 AS 245/45R18 2개 구매할래
-> ask_store

벤투스 S2 AS 245/45R18 한남점에서 구매할래
-> ask_quantity, 단 store context 보존
```

### BaseAgent tool guard의 남은 구조 과제

현재 `BaseAgent`는 LLM agent가 contract 밖 tool을 호출하려 할 때 실행 전에 차단한다.
이 역할은 필요하다.

문제는 차단 후 fallback을 만들 때 synthetic contract가 실제 current-turn slot/tool-result context를 잃을 수 있다는 점이다.

개선 방향:

- `BaseAgent`는 tool 차단 책임을 유지한다.
- fallback 생성 시 기존 `ToolPlan.tool_args_patch`, `ToolPlan.metadata`, `ResponseDecision.metadata`를 보존한다.
- `required_slots`만 보고 `pending_intent=price` 같은 값을 임의로 만들지 않는다.
- `flow_step=ask_quantity`면 수량 질문, `flow_step=ask_store`면 매장/지역 질문을 생성한다.
- policy fallback이 불가능할 때만 기존 generic guard fallback을 사용한다.

### 남은 구조 과제

`FlowController`는 이미 구매/장바구니 flow에 도입됐다. 남은 과제는 아래와 같다.

- `chat.py` direct helper가 flow별 fallback과 deterministic dispatch를 계속 추가하는 구조를 줄인다.
- `stock_store_search`, store availability, reservation schedule, cart, order cancel/status, FAQ policy 같은 flow로
  flow-state 계산 범위를 확장할지 결정한다.
- `BaseAgent` blocked-tool fallback이 `ToolPlan.metadata`, `ResponseDecision.metadata`, `FlowState.slot_patch`를
  잃지 않게 한다.
- FlowController가 current-turn intent를 판단하지 않고, router/TurnContract가 확정한 flow 안에서만 동작한다는
  경계를 유지한다.

장기 구조:

```text
Router / policy / TurnContract
-> select flow
-> resolve flow state
-> allowed tools/templates/CTA
-> BaseAgent guard uses flow-state fallback
```

단, FlowController가 router를 대체하거나 current-turn intent를 새로 판단해서는 안 된다.
FlowController의 책임은 **이미 확정된 contract 안에서 다음 step을 계산하는 것**으로 제한한다.

## 2026-06-27 추가 설계 기록: router prompt token 최적화

현재 router prompt는 `classify_multi_intent` 하나가 너무 많은 판단을 동시에 담당하면서 비대해진 상태다.

최신 코드 기준 측정값:

- `prompt_router_multi()`
  - system prompt 약 33,000자
  - `MultiAgentDomain` schema 문자열 약 14,700자
- `prompt_router_slim()`
  - system prompt 약 30,000자
  - `_SlimMultiAgentDomain` schema 문자열 약 8,300자
- LiteLLM 기준 이전 측정에서 slim/full router는 대략 10k tokens 이상이었다.

이 크기는 router의 중요도 때문에 구조상 불가피한 값이라기보다, 아래 책임이 하나의 prompt와 schema에 누적된 결과로 본다.

- domain 분류
- intent 분류
- policy intent 세부분류
- complaint scope 분류
- coupon/order/store 예외 분류
- OE/RE 분류
- discovery 추천 follow-up 분류
- slot-fill 판단
- agent prompt profile 결정
- execution plan 작성

### 구조적 결론

router를 제거하지 않는다.

다만 장기적으로는 router 역할을 아래처럼 조건부 cascade로 나눈다.

```text
deterministic UI action / slot validation
-> Slot-Fill Router
-> Domain Router
-> PolicyIntentClassifier or TransactionIntentClassifier or DiscoveryFollowupClassifier
-> TurnContract
```

중요한 원칙:

- 모든 턴에서 모든 classifier를 순차 호출하지 않는다.
- 명확한 UI action은 LLM 없이 deterministic validation으로 처리한다.
- slot-fill 후보가 있을 때만 짧은 Slot-Fill Router를 사용한다.
- policy catalog는 SUPPORT/policy 후보일 때만 별도 classifier에서 사용한다.
- transaction 세부 분류는 TRANSACTION 후보일 때만 별도 classifier에서 사용한다.
- 최종 실행 권한은 계속 `TurnContract`가 가진다.

### 이번 적용 범위

테스트 시간이 충분하지 않은 상황에서는 3차 구조 변경을 한 번에 적용하지 않는다.

이번 최적화는 아래 범위로 제한한다.

1. `prompt_router_slim()`을 실제 first-turn 전용으로 축소한다.
2. `_SlimMultiAgentDomain`의 긴 `Field(description=...)`을 줄인다.
3. 명확하게 검증된 UI action slot-fill만 router LLM 호출을 생략한다.
4. full `prompt_router_multi()` 분해, policy/transaction classifier 신설, `MultiAgentDomain` 대체는 이번 범위에서 제외한다.

### slim router 축소 기준

`prompt_router_slim()`은 세션 첫 사용자 발화에만 사용된다.

따라서 first-turn에 존재할 수 없는 아래 내용은 제거 또는 최소화한다.

- previous recommendation follow-up
- recent product set follow-up
- comparison continuation
- previous active flow 기반 slot-fill 상세 예시
- 긴 tricky examples
- multi-turn context 전환 설명

남겨야 할 내용:

- `LEADING / DISCOVERY / TRANSACTION / SUPPORT` 기본 분류 기준
- first-turn에서 자주 필요한 policy 후보
- 주문내역, 쿠폰함, 매장검색, 취소/환불, 예약 같은 transaction 후보
- 상품명, 사이즈, 추천, 가격 문의 같은 discovery 후보
- ambiguous/greeting/out-of-scope를 `LEADING`으로 보내는 최소 설명

`LEADING` 설명은 필요하다.
router prompt 자체가 leading agent인 것은 아니며, router가 leading agent로 보낼 발화를 분류해야 하기 때문이다.

### validated UI action router skip

아래 UI action은 이미 FE/BE metadata와 서버 slot state로 검증할 수 있으므로, 조건을 만족하면 router LLM 호출을 생략할 수 있다.

- `select_product`
- `select_quantity`
- `select_store`
- `select_schedule`

허용 조건:

- request metadata에 `ui_action`, `slots`, `expected_contract_intent`, `fills_slot` 등 구조화 정보가 있다.
- 서버의 기존 slot state와 결합했을 때 `transaction_slot_fill_resolution()`이 유효한 slot-fill로 검증한다.
- stable ID가 필요한 경우 LLM이 아니라 code가 후보 row와 매칭한다.

이 경우 synthetic routing result를 기존 `MultiAgentDomain` 형태로 만들어 downstream 호환성을 유지한다.

예상 routing result:

```json
{
  "domains": ["transaction"],
  "intent": "quick_order_reservation",
  "slot_fill_intent": "quick_order_reservation",
  "is_slot_fill": true,
  "filled_slot": "product",
  "slot_fill_source": "ui_action",
  "continue_flow": true,
  "new_intent": false
}
```

제한:

- 사용자가 직접 입력한 `분당`, `4개`, `내일 2시` 같은 direct text는 이번 범위에서 router skip하지 않는다.
- direct text slot-fill은 기존 router 판단을 유지한다.
- UI action metadata가 불완전하거나 서버 slot 검증에 실패하면 기존 router로 fallback한다.

### feature flag

안전한 rollout을 위해 flag로 제어한다.

```text
AI_ROUTER_USE_SLIM_PROMPT_V2
AI_ROUTER_SKIP_VALIDATED_UI_ACTION
```

문제 발생 시 기존 router 경로로 되돌릴 수 있어야 한다.

### Langfuse metadata

router skip 또는 slim v2 적용 시 trace에 아래 값을 남긴다.

- `router_prompt_version`
- `router_skipped`
- `router_skip_reason`
- `filled_slot`
- `slot_fill_intent`
- `resume_source`
- `expected_contract_intent`
- `router_input_token_estimate`

목적은 latency 개선 여부와 오분류 회귀를 trace에서 바로 비교하는 것이다.

### 최소 검증 기준

전체 회귀를 돌릴 시간이 없을 때 최소한 아래 축은 확인한다.

- 첫 턴 `회원가입하면 첫구매 혜택은 뭐가 있어?` -> SUPPORT + 신규회원/첫구매 policy
- 첫 턴 `내 주문내역 알려줘` -> TRANSACTION
- 첫 턴 `벤투스 S2 가격 알려줘` -> DISCOVERY
- 첫 턴 `강남역 근처 매장 찾아줘` -> TRANSACTION
- 상품 선택 UI action -> purchase flow 유지
- 수량 선택 UI action -> `ord_qty` 반영
- 매장 선택 UI action -> booking store 확정
- 일정 선택 UI action -> datepick/preOrder 흐름 유지

### 장기 방향

테스트 여유가 생기면 3차 구조로 확장한다.

```text
1차: slim prompt/schema 다이어트
2차: slot-fill router fast path 분리
3차: domain / policy / transaction / discovery follow-up classifier 분리
```

3차는 하나의 거대한 변경으로 merge/deploy하지 않는다.
같은 브랜치에서 개발하더라도 커밋과 feature flag를 분리해 원인 추적과 rollback 단위를 유지한다.

## 2026-06-28 추가 설계 기록: 주문 흐름 FlowState 1차 전환

최근 구매 예약 흐름에서 반복된 실패는 router/TurnContract intent 자체보다, 주문 흐름 상태가 여러 형식으로
동시에 존재하는 데서 발생했다.

관측된 대표 증상:

```text
2454519 벤투스 s2 as 2개 구매
-> product_event 단계에서는 goods_no/product_name/tire_size/ord_qty commit 성공

분당
-> 다음 턴의 pending_order_context에는 goods_no/tire_size/ord_qty/region만 남고
   product_name/tire_model/pending_product_name이 사라짐
```

trace/log 기준으로 `product_event` commit 자체는 실행됐다.
문제는 최종 세션 저장 경로에서 product 없는 context가 다시 만들어져 다음 턴 state로 사용된다는 점이다.

현재 주문 흐름 안에는 아래 형식들이 모두 상태처럼 쓰인다.

- flat `ConversationSlots`
- `availability_context.pending_order_context`
- `dormant_purchase_context`
- `datepick` template metadata
- `preOrder` template metadata
- `transaction_store_preview_tool` result
- product card / quickReply / CTA metadata

이 형식들은 모두 입력 source일 뿐이며, 저장/판단의 최종 형식으로 직접 경쟁하면 안 된다.

### 구조적 결론

공통 `FlowState` 모델을 만들되, 1차에서는 주문 흐름만 `flow_type=purchase`로 이관한다.

전체 stock/cart/store/reservation 흐름을 한 번에 옮기지 않는다.
기존 Redis 저장 위치도 당장은 유지한다.

```text
pending_order_context / flat slots / template metadata / tool result / CTA metadata
-> normalize_to_flow_state(flow_type=purchase)
-> merge_flow_state(existing, delta)
-> serialize_to_pending_order_context()
-> availability_context.pending_order_context 저장
```

즉 1차의 목적은 새 저장소 도입이 아니라, 주문 흐름의 저장 schema와 merge 규칙을 단일화하는 것이다.

### FlowState 1차 schema

1차 schema는 주문 흐름에서 필요한 공통 축만 포함한다.

```text
FlowState
  flow_type: purchase
  status: active | dormant | resumed

  product
    goods_no
    product_name
    tire_model
    pending_product_name
    tire_size
    ord_qty

  store
    region
    shop_id
    shop_name

  schedule
    requested_cal_day
    rsv_hour

  payment
    payment_amount
    price_basis
    price_source_tool
    payment_amount_stale

  intent
    pending_intent
    goal_type
    stock_check_mode
    schedule_mode

  meta
    source
    updated_at
```

저장 시에는 위 구조를 기존 `availability_context.pending_order_context` dict로 직렬화한다.
외부 저장 포맷을 한 번에 바꾸지 않아 기존 downstream 회귀를 줄인다.

### merge 원칙

주문 흐름에서는 아래 규칙을 공통 함수 하나가 소유한다.

- current delta에 없는 기존 값은 보존한다.
- 빈 값으로 기존 값을 삭제하지 않는다.
- 상품이 명시적으로 바뀔 때만 store/schedule/payment을 무효화한다.
- 수량이 바뀔 때는 payment를 stale 처리한다.
- 매장이 바뀔 때는 schedule/payment을 stale 처리한다.
- 지역만 입력된 턴은 product/quantity를 보존하고 region만 추가한다.
- 일정 선택 턴은 product/store/payment을 삭제하지 않고 schedule만 추가한다.

현재 실패는 `region` delta만 들어온 턴에서 기존 product group이 보존되지 않았기 때문에 발생했다.
FlowState merge 이후에는 아래 결과가 되어야 한다.

```text
existing.product = 벤투스 S2 AS / G000000310126 / 245/45R19 / 2개
delta.store.region = 분당

merged = product 유지 + region 추가
```

### 적용 범위

1차 포함:

- `quick_order_reservation`
- `purchase_continuation`
- 상품 확정
- 수량 확정
- 지역 확정
- 매장 확정
- 일정 확정
- 가격 확정
- `datepick`
- `preOrder`
- `transaction_store_preview_tool` 기반 구매 예약

1차 제외:

- 일반 재고 조회
- 오늘장착 조회
- 장바구니
- 일반 매장검색
- 주문내역 조회
- 쿠폰/FAQ/support

stock/cart/store/reservation은 같은 `FlowState` 모델로 확장할 수 있지만, 이번 변경에서는 adapter만 준비하고 실행 경로는 건드리지 않는다.

### 코드 정리 방향

기존 함수는 바로 삭제하지 않고 내부 위임으로 바꾼다.

```text
_stage_pending_order_context()
-> FlowState.from_slots()
-> FlowState.from_pending_order_context()
-> merge_purchase_flow_state()
-> to_pending_order_context()
```

정리 대상:

- `_pending_order_context_values()`
- `_merge_pending_order_context()`
- `_stage_pending_order_context()`
- `_apply_purchase_stock_canonical_readthrough()`
- `_finalize_purchase_stock_slots_for_persistence()`

특히 stream 종료 시 final persist 경로는 반드시 FlowState를 기준으로 저장해야 한다.

```text
product_event commit
-> final persist
-> save_slots_async
```

이 사이에서 product 없는 context가 기존 product group을 덮어쓰면 안 된다.

### TurnContract와의 관계

FlowState는 router나 TurnContract를 대체하지 않는다.

역할 분리:

- router: current-turn intent 판단
- TurnContract: 실행 가능한 tool/template/action 경계 결정
- FlowState: 이미 확정된 주문 흐름 slot의 저장/merge/보존

TurnContract 생성 전에는 purchase FlowState를 flat slots/known_slots로 rehydrate한다.
따라서 `분당` 같은 지역 입력 턴에서도 contract는 `product_name/goods_no/tire_size/ord_qty`를 가진 상태로 만들어져야 한다.

### trace metadata

FlowState 적용 후 trace에는 아래 값을 남긴다.

- `flow_state_type`
- `flow_state_before`
- `flow_state_delta`
- `flow_state_after`
- `flow_state_committed_fields`
- `flow_state_preserved_fields`
- `flow_state_cleared_fields`
- `flow_state_conflicts`
- `flow_state_commit_source`
- `payment_amount_stale`

목적은 다음 두 경우를 즉시 구분하는 것이다.

```text
1. 확정 값이 처음부터 commit되지 않음
2. commit은 됐지만 final persist에서 사라짐
```

### 최소 검증 기준

아래 purchase-only 시나리오를 먼저 고정한다.

```text
2454519 벤투스 s2 as 2개 구매
-> pending_order_context.product_name = 벤투스 S2 AS

분당
-> product 유지 + region=분당 추가

매장 선택
-> product 유지 + shop_id/shop_name 추가

일정 선택
-> product/store 유지 + requested_cal_day/rsv_hour 추가

preOrder
-> 상품명과 결제금액 표시
```

반대 케이스:

```text
다른 상품으로 바꿀게
-> 기존 store/schedule/payment 무효화

4개로 바꿀게
-> ord_qty 변경 + payment_amount_stale=true
```

### latency 영향

새 LLM 호출, BE 호출, tool fan-out 증가는 없다.
로컬 상태 normalize/merge만 추가되므로 latency 영향은 무시 가능한 수준이어야 한다.
