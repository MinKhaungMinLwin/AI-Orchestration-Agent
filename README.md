# T-Station AI

T-Station AI는 티스테이션 챗봇의 Agent 서비스입니다. 사용자의 발화를 분류하고, 상품 추천/검색, 가격/재고/주문, FAQ/상담 연결 등의 도구를 호출한 뒤 프론트엔드가 렌더링할 수 있는 SSE 이벤트와 템플릿 데이터를 반환합니다.

## Agent Runtime 진입점

현재 agent/runtime 진입점은 `app/tstation-ai/services/tstation/chat_v3/` (`/chat_v3`)입니다.
Agent 라우팅, tool loop, template, QC, SSE 동작은 `chat_v3/`의 현재 구현을 기준으로 확인합니다.

`services/tstation/chat.py`와 `services/tstation/agents/`는 레거시 V2 호환 및 V3가 재사용하는 tool/schema 계층입니다.
새 런타임 동작은 `chat_v3/`에서 시작하고, 공유 도구나 FE schema 변경이 필요할 때만 `agents/*/tools.py` 또는
`agents/templates/schemas.py`를 수정합니다.

## 주요 역할

- 채팅 API 제공: `/api/tstation/messages/chat`
- Chat V3 LLM-first 라우팅: leading, discovery, transaction, support 도메인 결정
- 백엔드 API 호출 도구 실행
- 상품, 매장, 쿠폰, 차량, 예약 등 리치 UI 템플릿 데이터 생성
- Langfuse tracing, Redis/Celery 작업 큐, Qdrant 기반 RAG 연동
- 백엔드 OpenAPI 스펙으로 Python API client 생성

## 폴더 구조

```text
tstation-ai/
├── app/
│   ├── tstation-ai/
│   │   ├── main.py                    # FastAPI 앱 진입점
│   │   ├── api/                       # API 라우터
│   │   ├── common/                    # 공통 유틸, 생성된 BE API client
│   │   ├── config/                    # 환경 설정
│   │   ├── schemas/                   # 요청/응답 스키마
│   │   ├── services/
│   │   │   └── tstation/
│   │   │       ├── chat.py            # API branch + 레거시 V2 호환 계층
│   │   │       ├── chat_v3/           # 현재 agent/runtime 진입점
│   │   │       ├── template_mapper.py # 레거시 V2 tool 결과 → FE 템플릿 매핑
│   │   │       ├── agents/            # V3가 재사용하는 tool/schema + 레거시 V2 Agent
│   │   │       ├── policies/          # deterministic 정책/가드
│   │   │       └── rag/               # RAG 검색
│   │   └── tests/                     # AI 서비스 테스트
│   └── tstation-ingestion/            # RAG 데이터 적재/색인
├── docker/                            # Docker Compose 설정
├── example/                           # 로컬 실행용 예시 파일
├── justfile                           # 개발/실행 태스크
├── pyproject.toml                     # uv 의존성 정의
└── .env.example                       # 환경 변수 예시
```

## V3 구성

V3는 `app/tstation-ai/services/tstation/chat_v3/` 아래에서 router → executor → composer/template/QC 흐름으로 동작합니다.

`app/tstation-ai/services/tstation/agents/` 아래 prefix 폴더는 현재 V3의 root runtime이 아니라 공유 tool/schema 및
레거시 V2 호환 계층입니다.

| Prefix | Agent | 역할 |
| --- | --- | --- |
| `a_` | leading_agent | 레거시 V2 leading agent |
| `b_` | discovery_agent | V3가 재사용하는 상품 검색, 추천, 차량 호환, 유튜브 도구 |
| `c_` | transaction_agent | V3가 재사용하는 가격, 재고, 매장, 주문, 쿠폰, 예약 도구 |
| `e_` | support_agent | V3가 재사용하는 FAQ, 보증, 반품, 1:1 문의 도구 |

## 준비

필수 도구:

- Python 3.12 이상
- `uv`
- `just`
- Docker / Docker Compose

환경 파일을 준비합니다.

```bash
cd tstation-ai
cp .env.example .env
```

`.env.example`의 빈 값은 의도적인 placeholder입니다. 대상 환경의 실제 credential과 private endpoint를
Git에 커밋하지 말고 `.env` 또는 승인된 secret store에 설정해야 합니다. Compose는 필수 RabbitMQ/Langfuse
credential이 비어 있으면 약한 기본값을 사용하지 않고 배포 전에 실패합니다.

로컬 개발 기본 파일까지 한 번에 준비하려면:

```bash
just setup
```

의존성만 설치하려면:

```bash
just install
```

## 실행 방법

### Docker로 실행

```bash
cd tstation-ai
just start
```

중지:

```bash
just stop
```

상태와 로그:

```bash
just ps
just logs
```

특정 서비스만 다시 띄우려면:

```bash
just up-service tstation-ai
```

### Swarm Nginx TLS 개인키

원격 Swarm 배포는 Nginx 개인키를 Git 파일이 아닌 외부 Docker Secret으로 주입합니다.
배포 전에 Swarm manager에 `tstation-agent-dev-nginx-key-20260724` Secret이 존재해야 합니다.

```bash
docker secret inspect tstation-agent-dev-nginx-key-20260724
```

신규 Swarm을 구성할 때는 저장소 밖의 권한 제한 경로에 보관한 키로
Secret을 먼저 생성합니다.

```bash
docker secret create tstation-agent-dev-nginx-key-20260724 /secure/path/server.key
```

개인키를 저장소, Docker 이미지, 빌드 산출물 또는 배포 디렉터리에 복사하지 않습니다.
Secret은 Swarm 클러스터 단위 리소스이므로 새 클러스터를 만들 때 별도로 준비해야 합니다.

### 로컬 프로세스로 실행

AI 서비스:

```bash
cd tstation-ai
set -a && source .env && set +a
uv run app/tstation-ai/main.py
```

## 개발 명령

```bash
just lint          # ruff check
just fmt           # ruff fix + isort
just install-hooks # pre-commit hook 설치
```

특정 테스트 실행 예시:

```bash
uv run pytest app/tstation-ai/tests/test_quickreply_fallback_routing.py -q
```

## OpenAPI client 갱신

백엔드 OpenAPI 스펙이 바뀌면 BE API client를 재생성합니다.

```bash
just update-openapi
```

주의:

- `app/tstation-ai/common/tstation_be_api_client/`는 생성 코드입니다.
- 이 폴더의 파일을 직접 수정하지 말고 OpenAPI 스펙을 갱신한 뒤 재생성합니다.

## 주요 연동

- Backend API: 상품, 가격, 재고, 매장, 주문, FAQ 데이터 조회
- Redis/Celery: 비동기 작업 큐
- Qdrant: RAG vector store
- Langfuse: trace 및 품질 확인
- LiteLLM/OpenAI 호환 LLM gateway: Agent 추론

## 작업 시 주의사항

- 프롬프트 변경은 기존 정상 플로우와 충돌 가능성을 먼저 검토합니다.
- 오류 수정은 특정 케이스만 막지 말고 같은 원인 계열에 적용 가능한 방식으로 처리합니다.
- FE로 나가는 SSE `type`, `template`, `data` 구조는 `tstation/` 위젯과 호환되어야 합니다.
