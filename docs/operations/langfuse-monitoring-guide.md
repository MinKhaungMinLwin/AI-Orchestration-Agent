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

## 고객사 EC2에서 통계 및 trace 로그 가져오기

고객사 EC2는 Docker Compose가 아니라 Docker Swarm으로 운영된다. 아래 명령은 Swarm 서비스
`tstation-agent-dev_tstation-ai`와 자체 호스팅 Langfuse를 기준으로 한다. 명령은 Swarm manager에서 시작한다.

### 1. AI task 실행 노드와 컨테이너 확인

AI task가 어느 노드에서 실행 중인지 확인한다.

```bash
docker service ps tstation-agent-dev_tstation-ai \
  --filter desired-state=running \
  --format 'table {{.Node}}\t{{.CurrentState}}\t{{.Image}}'
```

표시된 task 노드에 접속한 뒤 컨테이너 ID를 구한다.

```bash
AI_CID=$(docker ps \
  --filter 'name=tstation-agent-dev_tstation-ai' \
  -q | head -1)

docker ps --filter "id=$AI_CID" \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
```

집계 스크립트가 배포 이미지에 포함됐는지 확인한다.

```bash
docker exec "$AI_CID" ls -l /app/scripts/langfuse_weekly_report.py
```

### 2. 최근 24시간 운영 통계 생성

아래 명령은 `customer_monitoring` trace를 최근 24시간 기준으로 집계한다. 화면에는 요약을 출력하고,
컨테이너 `/tmp`에 질문(`input_text`)과 최종 답변(`assistant_response`)을 포함한 상세 CSV를 저장한다.

```bash
docker exec "$AI_CID" sh -lc '
cd /app
PY=".venv/bin/python"
[ -x "$PY" ] || PY="uv run python"

$PY scripts/langfuse_weekly_report.py \
  --days 1 \
  --csv /tmp/customer-monitoring-today.csv
'
```

`--days 1`은 한국시간 오늘 00시부터가 아니라 실행 시점 기준 최근 24시간이다.

### 3. 한국시간 오늘 00시부터 현재까지 집계

정확한 KST 일일 통계가 필요하면 아래 명령으로 KST 자정을 계산해 조회한다. 합의된 테스터 13개 계정은 이름과
회원번호 원문 대신 SHA-256 allowlist로 관리한다. 이 값은 영구 환경변수가 아니며 통계 생성 중에만 권한이 제한된
임시 파일로 사용한다.

```bash
umask 077
TESTER_HASHES=/tmp/tstation-ai-tester-member-id-sha256.txt

cat > "$TESTER_HASHES" <<'EOF'
9ef9d38286aeb020b3b11b314f28ca9ea6eee5058150883f072947ef96a9c3f5
fbde5e285122e25473dd6449d0f6ff7d2bb0cf7b8c42e0548506b3962074a2d7
301af5b057c103b15100bd57a098e3a9d372a587b89af360051eebce42de755b
fc4b02e3c70b77f65f012722ee2a5c82fa70671525fc3d13ba949e4ed7526880
dbd526297f872c1d55a6c08232c2b055be9c737a3583823af56b0820834625f1
87919f08f1142173b6394b42c547dae629cef75f9360b174a6bba983d6cba1c5
b6ad2be7137b1936f3660e4b0d4c1163f9fc27c2d1bda1b0d45519743a5b8ae0
5cb4cfa86e1a46664551bba53a37e7f42619d36c2e0500ed719db98d0dd5cfa6
473a791db4aa6cb90f6b82a88b181fb3af826a4c109a4a1c419fda1428531af5
32d2342bf8d212034c2cb7fe12b86fbb981a5e6e688ea1986c832d344eaa6336
7418b06f7372e1c687698d264ac6528655dce2b25da95a4a9613f27283f59120
4ed9ba466268e1d93d268a59fb91abdccc22ef98f1422ed8f37c1d31e372d860
96f8356fb7bfa353dcc37b6fd003360b4b2915ec45e89ce43ec9661a0e635382
EOF

chmod 600 "$TESTER_HASHES"
docker cp "$TESTER_HASHES" "$AI_CID":/tmp/tstation-ai-tester-member-id-sha256.txt
```

Langfuse에서 trace를 수집한 직후 테스터를 제외하고, 제외된 목록으로 화면 요약과 CSV를 모두 생성한다.

```bash
docker exec "$AI_CID" sh -lc '
cd /app
PY=".venv/bin/python"
[ -x "$PY" ] || PY="uv run python"

PYTHONPATH=/app $PY -c "
import hashlib
from datetime import UTC, datetime, timedelta, timezone
from scripts.langfuse_weekly_report import _collect_traces, _print_report, _write_csv

with open(\"/tmp/tstation-ai-tester-member-id-sha256.txt\", encoding=\"utf-8\") as file:
    tester_hashes = {line.strip().lower() for line in file if line.strip()}
if len(tester_hashes) != 13 or any(len(value) != 64 for value in tester_hashes):
    raise SystemExit(\"Invalid tester SHA-256 allowlist.\")

def is_tester_user_id(user_id):
    normalized = user_id.strip()
    lowered = normalized.lower()
    if lowered in tester_hashes:
        return True
    if len(lowered) == 12 and any(digest.startswith(lowered) for digest in tester_hashes):
        return True
    return hashlib.sha256(normalized.upper().encode()).hexdigest() in tester_hashes

kst = timezone(timedelta(hours=9))
end = datetime.now(kst)
start = end.replace(hour=0, minute=0, second=0, microsecond=0)
all_traces = _collect_traces(
    start.astimezone(UTC),
    end.astimezone(UTC),
    limit=100,
    max_pages=50,
)
traces = [trace for trace in all_traces if not is_tester_user_id(trace.user_id)]
print(f\"Collected: {len(all_traces)}, excluded testers: {len(all_traces) - len(traces)}\")
_print_report(traces, start.astimezone(UTC), end.astimezone(UTC))
_write_csv(\"/tmp/customer-monitoring-kst-today.csv\", traces)
"
'
```

### 4. CSV를 EC2 host로 복사하고 확인

최근 24시간 파일:

```bash
docker cp \
  "$AI_CID":/tmp/customer-monitoring-today.csv \
  /tmp/customer-monitoring-today.csv

cat /tmp/customer-monitoring-today.csv
```

KST 오늘 파일:

```bash
docker cp \
  "$AI_CID":/tmp/customer-monitoring-kst-today.csv \
  /tmp/customer-monitoring-kst-today.csv
```

출력이 길어 터미널에서 잘리면 구간별로 확인한다.

```bash
sed -n '1,150p' /tmp/customer-monitoring-kst-today.csv
sed -n '151,300p' /tmp/customer-monitoring-kst-today.csv
```

직접 파일 전송이 차단된 환경에서는 6단계의 최종 검증을 통과한 CSV만 gzip+Base64로 압축해 승인된 채널로 전달한다.

로컬 보관 경로는 아래 규칙을 사용한다. 이 폴더의 CSV는 `.gitignore`로 제외한다.

```text
tstation-ai/reports/langfuse/YYYY-MM-DD.csv
```

CSV의 마지막 두 컬럼은 아래와 같다.

```text
input_text,assistant_response
```

구버전 스크립트에서 생성한 CSV에 `assistant_response`가 없으면 배포 이미지가 답변 컬럼 추가 이전 버전이다.
가능하면 업데이트된 이미지로 다시 생성하고, 재생성이 어려운 과거 CSV만 다음 절차로 복원한다.

### 5. 구버전 CSV에 채팅 이력 답변 보강

특정 세션의 저장된 질문과 답변을 먼저 확인한다.

```bash
SESSION_ID='<session_id>'

docker exec -e SESSION_ID="$SESSION_ID" "$AI_CID" sh -lc '
cd /app
PY=".venv/bin/python"
[ -x "$PY" ] || PY="uv run python"

PYTHONPATH=/app $PY -c "
import json
import os
from services.tstation.chat_history_service import get_chat_history_service

service = get_chat_history_service()
history = service.get_history(os.environ[\"SESSION_ID\"])
print(json.dumps(history, ensure_ascii=False, indent=2))
"
'
```

기존 CSV 전체를 보강하려면 먼저 AI 컨테이너로 복사한다.

```bash
SRC=/tmp/customer-monitoring-kst-today.csv
docker cp "$SRC" "$AI_CID":/tmp/customer-monitoring-kst-today.csv
```

아래 명령은 CSV의 `session_id`, `message_id`와 채팅 이력의 user `msg_id`를 맞춘 뒤 바로 다음 assistant
메시지의 `content`를 추가한다. 여러 줄 답변을 안전하게 처리하기 위해 Python `csv` 모듈을 사용한다.

```bash
docker exec "$AI_CID" sh -lc '
cd /app
PY=".venv/bin/python"
[ -x "$PY" ] || PY="uv run python"

PYTHONPATH=/app $PY - <<"PY"
import csv
from services.tstation.chat_history_service import get_chat_history_service

src = "/tmp/customer-monitoring-kst-today.csv"
dst = "/tmp/customer-monitoring-kst-today-with-answer.csv"

with open(src, encoding="utf-8", newline="") as file:
    reader = csv.DictReader(file)
    rows = list(reader)
    fieldnames = list(reader.fieldnames or [])

if "session_id" not in fieldnames or "message_id" not in fieldnames:
    raise SystemExit("CSV에 session_id 또는 message_id 컬럼이 없습니다.")
if "assistant_response" not in fieldnames:
    fieldnames.append("assistant_response")

service = get_chat_history_service()
answer_by_message_id = {}

for session_id in sorted({(row.get("session_id") or "").strip() for row in rows} - {""}):
    history = service.get_history(session_id) or []
    for index, message in enumerate(history):
        if message.get("role") != "user" or not message.get("msg_id"):
            continue
        for candidate in history[index + 1 :]:
            if candidate.get("role") == "user":
                break
            if candidate.get("role") == "assistant":
                answer_by_message_id[str(message["msg_id"])] = candidate.get("content") or ""
                break

filled = 0
missing = 0
for row in rows:
    if row.get("assistant_response"):
        continue
    answer = answer_by_message_id.get((row.get("message_id") or "").strip(), "")
    row["assistant_response"] = answer
    if answer:
        filled += 1
    else:
        missing += 1

with open(dst, "w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"records={len(rows)} answers_filled={filled} answers_missing={missing}")
PY
'

docker cp \
  "$AI_CID":/tmp/customer-monitoring-kst-today-with-answer.csv \
  /tmp/customer-monitoring-kst-today-with-answer.csv
```

`answers_missing`은 채팅 이력 만료, message ID 불일치, assistant 메시지 미저장 등으로 복원하지 못한 건수다.
최신 집계 스크립트가 배포된 뒤에는 trace의 `assistant_response`를 직접 사용한다.

### 6. 테스터 제외 결과 재검증 및 Base64 생성

3단계에서 화면 요약과 CSV 모두 테스터를 제외하지만, 전달 전 EC2 host에서 같은 SHA-256 allowlist로 CSV를 한 번 더
필터링해 잔존 테스터가 없는지 검증한다. 이 방어적 재필터링에서 제외 건수가 0인 것은 정상이다.

필터링할 CSV와 결과 파일을 지정한다. 최신 집계 스크립트로 생성한 KST 오늘 CSV에는
`assistant_response`가 포함되어 있으므로 별도 답변 보강 없이 이 파일을 원본으로 사용한다.

```bash
SRC=/tmp/customer-monitoring-kst-today.csv
DST=/tmp/customer-monitoring-kst-today-with-answer-excluded.csv
TESTER_HASHES=/tmp/tstation-ai-tester-member-id-sha256.txt
export SRC DST TESTER_HASHES
```

CSV의 `assistant_response`에는 줄바꿈이 들어갈 수 있으므로 `grep`, `awk`, `wc -l`로 레코드를 처리하거나 세지 않는다.
아래 명령은 Python `csv` 모듈로 원문 회원번호, SHA-256 전체값, SHA-256 앞 12자리 형태의 `user_id`를 모두
allowlist와 비교해 제외한다. 필터링 결과에는 헤더를 유지하며, 테스터 회원번호 자체는 출력하지 않는다.

```bash
python3 - <<'PY'
import csv
import hashlib
import os

src = os.environ["SRC"]
dst = os.environ["DST"]
tester_hashes_path = os.environ["TESTER_HASHES"]

with open(tester_hashes_path, encoding="utf-8") as file:
    tester_hashes = {line.strip().lower() for line in file if line.strip()}

if len(tester_hashes) != 13 or any(len(value) != 64 for value in tester_hashes):
    raise SystemExit("테스터 SHA-256 allowlist 검증에 실패했습니다.")


def is_tester_user_id(user_id: str) -> bool:
    normalized = user_id.strip()
    lowered = normalized.lower()
    if lowered in tester_hashes:
        return True
    if len(lowered) == 12 and any(digest.startswith(lowered) for digest in tester_hashes):
        return True
    raw_digest = hashlib.sha256(normalized.upper().encode()).hexdigest()
    return raw_digest in tester_hashes

read_count = 0
excluded_count = 0
written_count = 0

with open(src, encoding="utf-8", newline="") as source, open(
    dst,
    "w",
    encoding="utf-8",
    newline="",
) as target:
    reader = csv.DictReader(source)
    required = {"user_id", "input_text", "assistant_response"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"CSV 필수 컬럼이 없습니다: {sorted(missing)}")

    writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
    writer.writeheader()

    for row in reader:
        read_count += 1
        user_id = (row.get("user_id") or "").strip()
        if is_tester_user_id(user_id):
            excluded_count += 1
            continue
        writer.writerow(row)
        written_count += 1

if read_count != excluded_count + written_count:
    raise SystemExit("필터링 건수 검증에 실패했습니다.")

print(f"read={read_count} excluded={excluded_count} written={written_count}")
PY
```

헤더와 실제 CSV 레코드 수를 확인하고, 테스터 ID가 남지 않았는지 다시 검증한다. 질문과 답변 컬럼이 존재하는지와
값이 비어 있는 레코드 수도 함께 출력한다.

```bash
head -1 "$DST"

python3 - <<'PY'
import csv
import hashlib
import os

with open(os.environ["TESTER_HASHES"], encoding="utf-8") as file:
    tester_hashes = {line.strip().lower() for line in file if line.strip()}


def is_tester_user_id(user_id: str) -> bool:
    normalized = user_id.strip()
    lowered = normalized.lower()
    if lowered in tester_hashes:
        return True
    if len(lowered) == 12 and any(digest.startswith(lowered) for digest in tester_hashes):
        return True
    raw_digest = hashlib.sha256(normalized.upper().encode()).hexdigest()
    return raw_digest in tester_hashes

with open(os.environ["DST"], encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))

remaining = [
    row
    for row in rows
    if is_tester_user_id(row.get("user_id") or "")
]
empty_questions = sum(not (row.get("input_text") or "").strip() for row in rows)
empty_answers = sum(not (row.get("assistant_response") or "").strip() for row in rows)

print(
    f"records={len(rows)} remaining_testers={len(remaining)} "
    f"empty_questions={empty_questions} empty_answers={empty_answers}"
)
if remaining:
    raise SystemExit("테스터 trace가 결과 CSV에 남아 있습니다.")
PY
```

전달용 Base64 파일과 SHA-256 checksum도 파일명을 먼저 지정한 뒤 생성한다. `ENCODED`를 지정하지 않으면
`> "$ENCODED"`가 빈 경로로 평가되어 `No such file or directory`가 발생한다.

```bash
ENCODED=/tmp/customer-monitoring-kst-today-with-answer-excluded.csv.gz.b64

gzip -c "$DST" | base64 -w 0 > "$ENCODED"
printf '\n' >> "$ENCODED"

sha256sum "$DST" "$ENCODED"
ls -lh "$DST" "$ENCODED"
```

통계 분석과 전달이 끝나면 임시 SHA-256 allowlist 파일은 고객사 보관 정책에 따라 삭제한다. 영구 환경변수나
Swarm service env에는 테스터 ID 또는 해시를 추가하지 않는다.

```bash
docker exec "$AI_CID" rm -f /tmp/tstation-ai-tester-member-id-sha256.txt
rm -f "$TESTER_HASHES"
```

통계 리포트에는 원본 건수, 제외 건수, 최종 분석 건수와 집계 종료 시각(KST)을 함께 적는다. 제외 대상의 이름이나
회원번호 원문은 리포트에 기재하지 않는다.

### 7. 최신 customer_monitoring trace 시각 확인

현재 시각까지 trace가 정상 적재되고 있는지 확인할 때 최신 trace의 UTC와 KST 시각을 함께 출력한다. 컨테이너
교체로 ID가 바뀔 수 있으므로 `AI_CID`부터 다시 구한다.

```bash
AI_CID=$(docker ps \
  --filter 'name=tstation-agent-dev_tstation-ai' \
  -q | head -1)

docker exec "$AI_CID" sh -lc '
cd /app
set -a
[ -f /app/.env ] && . /app/.env
set +a

PY=".venv/bin/python"
[ -x "$PY" ] || PY="uv run python"

curl -sS --fail-with-body --max-time 20 \
  -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?name=customer_monitoring&limit=1&orderBy=timestamp.desc" \
| $PY -c "
import json
import sys
from datetime import datetime, timedelta, timezone

payload = json.load(sys.stdin)
rows = payload.get(\"data\", [])
if not rows:
    raise SystemExit(\"customer_monitoring trace가 없습니다.\")

trace = rows[0]
timestamp = datetime.fromisoformat(trace[\"timestamp\"].replace(\"Z\", \"+00:00\"))
kst = timezone(timedelta(hours=9))

print(\"trace_id:\", trace.get(\"id\"))
print(\"UTC:\", timestamp.isoformat())
print(\"KST:\", timestamp.astimezone(kst).isoformat())
"
'
```

실패하면 `AI_CID`와 Langfuse 환경변수 주입 여부를 확인한다. secret 값 자체는 출력하지 않는다.

```bash
printf 'AI_CID=<%s>\n' "$AI_CID"

docker exec "$AI_CID" sh -lc '
printf "host=%s public_len=%s secret_len=%s\n" \
  "$LANGFUSE_HOST" "${#LANGFUSE_PUBLIC_KEY}" "${#LANGFUSE_SECRET_KEY}"
'
```

### 8. session ID로 Langfuse trace 조회

AI 컨테이너에는 Langfuse host와 API key가 환경변수로 주입되어 있으므로 값을 화면에 출력하지 않고 바로 사용한다.

```bash
SESSION_ID='<session_id>'

docker exec -e SESSION_ID="$SESSION_ID" "$AI_CID" sh -lc '
curl -sS --max-time 20 \
  -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?sessionId=$SESSION_ID&limit=20"
'
```

세션에 trace가 여러 개 있으면 `timestamp`, `input`, `output`, `metadata.final_status`,
`metadata.final_template`, `metadata.called_tools`를 비교해 최종 사용자 응답과 일치하는 성공 trace를 선택한다.

### 9. trace ID로 observation 상세 조회

선택한 trace의 router, tool, composer, QC observation을 조회한다.

```bash
TRACE_ID='<trace_id>'

docker exec -e TRACE_ID="$TRACE_ID" "$AI_CID" sh -lc '
curl -sS --max-time 20 \
  -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/observations?traceId=$TRACE_ID&limit=100"
'
```

응답이 너무 크면 운영 터미널에서만 다음처럼 크기를 제한한다.

```bash
TRACE_ID='<trace_id>'

docker exec -e TRACE_ID="$TRACE_ID" "$AI_CID" sh -lc '
curl -sS --max-time 20 \
  -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/observations?traceId=$TRACE_ID&limit=100" \
  | head -c 120000
'
```

### 10. Public API에서 trace가 없을 때 ClickHouse 조회

Public API가 빈 결과를 반환해도 ClickHouse `default.traces`에는 데이터가 남아 있을 수 있다.

```bash
SESSION_ID='<session_id>'
CH_CID=$(docker ps \
  --filter 'name=tstation-agent-dev_langfuse-clickhouse' \
  -q | head -1)

docker exec "$CH_CID" clickhouse-client --query "
SELECT
  timestamp,
  session_id,
  id AS trace_id,
  user_id,
  name,
  substring(toString(input), 1, 500) AS input_preview,
  substring(toString(output), 1, 500) AS output_preview
FROM default.traces
WHERE session_id = '${SESSION_ID}'
ORDER BY timestamp
FORMAT Vertical
"
```

### 11. gzip+Base64 전달 파일 복원

전달받은 문자열을 파일에 저장했다면 Base64를 해제한 뒤 gzip을 풀어 CSV를 복원한다.

```bash
B64=/tmp/customer-monitoring-kst-today-with-answer-excluded.csv.gz.b64
OUT=/tmp/customer-monitoring-kst-today-with-answer-excluded.csv

base64 -d "$B64" | gzip -dc > "$OUT"
head -1 "$OUT"
sha256sum "$OUT"
```

CSV의 `assistant_response`에는 줄바꿈이 있을 수 있으므로 실제 레코드 수는 `wc -l`이 아니라 다음처럼 확인한다.

```bash
export OUT
python3 - <<'PY'
import csv
import os

with open(os.environ["OUT"], encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))

print(f"records={len(rows)}")
PY
```

### 12. 고객사 EC2 프런트 배포 적용 확인

고객사 프런트는 Docker Swarm 서비스 `tstation-frontend-dev_web`으로 실행되고, agent stack의 nginx는 이
서비스로 reverse proxy한다. 먼저 실제 task 노드와 실행 시간을 확인한다.

```bash
docker service ps tstation-frontend-dev_web \
  --filter desired-state=running \
  --format 'table {{.Node}}\t{{.CurrentState}}\t{{.Image}}'

docker service inspect tstation-frontend-dev_web \
  --format $'UpdatedAt: {{.UpdatedAt}}\nImage: {{.Spec.TaskTemplate.ContainerSpec.Image}}\nUpdateStatus: {{json .UpdateStatus}}'
```

agent stack의 nginx 컨테이너와 실제 upstream 설정을 확인한다.

```bash
FE_CID=$(docker ps \
  --filter 'name=tstation-agent-dev_nginx' \
  -q | head -1)

docker exec "$FE_CID" nginx -T 2>&1 \
  | grep -nE 'server_name|listen|proxy_pass|fe_upstream|location '
```

nginx 컨테이너에는 FE 정적 파일이 없으므로 overlay network의 실제 FE upstream에서 cache-busting query로
배포된 JS를 직접 읽는다.

```bash
docker exec "$FE_CID" sh -lc '
wget -qO- "http://tstation-frontend-dev_web/components/chatbox/chatbox-template.js?cb=$(date +%s)"
' | grep -nE -B5 -A10 \
  'mbrNm|고객님, 반가워요|chatbox-greeting-body'

docker exec "$FE_CID" sh -lc '
wget -qO- "http://tstation-frontend-dev_web/components/chatbox/chatbox-component.js?cb=$(date +%s)"
' | grep -nE -B12 -A20 \
  '_appendWelcomeGreetingIfNeeded|_getChatEntryGreetingInnerHtml|mbrNm|user-info|chatbox-greeting-body'
```

예를 들어 `mbrNm || "고객"`과 별도의 `" 고객님"` suffix가 함께 남아 있으면 화면에는
`고객 고객님`이 만들어질 수 있다. EC2 host에 소스만 복사해도 mount가 없는 Swarm 컨테이너에는 반영되지 않는다.
이미지를 다시 build/push한 뒤 service task가 새로 생성됐는지와 upstream JS 내용을 모두 확인해야 한다.

### 보안 주의사항

- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` 값을 `echo`하거나 문서·리포트에 복사하지 않는다.
- CSV에는 회원 ID, 사용자 입력, session/trace ID가 포함되므로 승인된 저장 위치와 전달 채널만 사용한다.
- 고객사 공유 자료에는 raw prompt, 전체 tool payload, 내부 슬롯과 정책 정보를 그대로 포함하지 않는다.
- 분석 종료 후 EC2와 컨테이너 `/tmp`에 남은 CSV는 고객사 보관 정책에 따라 삭제한다.

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
