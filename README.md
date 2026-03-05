# 코드 학습 플랫폼 (code)

FastAPI 기반 학습 플랫폼입니다. 현재 프로젝트는 **두 백엔드가 함께 동작하는 혼합 구조**입니다.

- `run_server.py`(런처) + `server_runtime/webapp.py`(앱 조립) + `server_runtime/routes/*`(라우터) + `backend/*`: JSONL 기반 API/프론트 통합 서버 (`/api/*`)
- `app/*`: SQL(MySQL) 기반 API (`/platform/*`로 마운트)

## 현재 아키텍처

### 1) JSONL 백엔드 (`/api/*`)
- 실행 엔트리: `run_server.py` (런처)
- 앱 조립: `server_runtime/webapp.py` (라우터 등록/마운트)
- 관리자 API: `server_runtime/admin_api.py`
- 저장소: `data/users/*.jsonl`
- 기능: Google/Guest 로그인, 학습 모드(analysis, code-block, arrange, code-calc, code-error, auditor, context-inference, refactoring-choice, code-blame), 관리자 패널
- AI 문제 생성: `backend/problem_generator.py` (Gemini 키 필요)

### 2) SQL 백엔드 (`/platform/*`)
- 엔트리: `app/main.py` (실행은 `run_server.py`에서 `/platform`로 마운트)
- 저장소: MySQL (`users`, `problems`, `submissions`, `user_problem_stats`, `reports` 등)
- 분석 처리: Redis + RQ worker 비동기 큐
- 리포트: 마일스톤 리포트 고도화(오답유형/난이도별/언어별/추세)

### 3) 프런트엔드 엔트리 구조
- 화면은 페이지별 엔트리 JS(`dashboard.js`, `analysis.js`, `codeblock.js` 등)를 각 HTML에서 직접 로드합니다.
- `app.html`은 하위호환용 진입점으로 유지되며, 요청 시 `dashboard.html`로 리다이렉트됩니다.

## 실행 모드

### Docker 모드 (권장)
기본 실행은 Docker Compose를 사용합니다.

```bash
python run_server.py
```

또는 백그라운드 실행:

```bash
python run_server.py --detach --no-build --no-open-admin
```

관리자 패널의 `스택 안전 종료`는 기본 실행에서 동작하도록 Docker 소켓 override가 자동 적용됩니다.
보안상 종료 권한을 끄고 싶다면 아래 옵션을 사용하세요:

```bash
python run_server.py --without-docker-socket
```

실행 컨테이너:
- `code-platform-api` (FastAPI)
- `code-platform-mysql` (MySQL 8)
- `code-platform-redis` (Redis 7)
- `code-platform-worker` (RQ worker)

중지:

```bash
docker compose down
```

### 로컬 uvicorn 모드

```bash
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

주의:
- 로컬 모드에서는 DB/Redis를 별도로 준비해야 합니다.
- 인자 없이 실행하면 Docker 모드가 기본입니다.

## 주요 엔드포인트

### JSONL 백엔드 (`/api/*`, server_runtime/routes/*)
- `GET /health`
- `GET /api/auth/google/start`
- `GET /api/auth/google/callback`
- `GET /api/auth/guest/start`
- `POST /api/auth/register` (비활성, 410)
- `POST /api/auth/login` (비활성, 410)
- `POST /api/auth/guest`
- `GET /api/tracks`
- `GET /api/languages`
- `GET /api/profile`
- `GET /api/me`
- `POST /api/diagnostics/start`
- `POST /api/problem/submit`
- `POST /api/code-block/problem`
- `POST /api/code-block/submit`
- `POST /api/code-arrange/problem`
- `POST /api/code-arrange/submit`
- `POST /api/code-calc/problem`
- `POST /api/code-calc/submit`
- `POST /api/code-error/problem`
- `POST /api/code-error/submit`
- `POST /api/auditor/problem`
- `POST /api/auditor/submit`
- `POST /api/context-inference/problem`
- `POST /api/context-inference/submit`
- `POST /api/refactoring-choice/problem`
- `POST /api/refactoring-choice/submit`
- `POST /api/code-blame/problem`
- `POST /api/code-blame/submit`
- `GET /api/learning/history`
- `GET /api/learning/memory`
- `GET /api/report`
- `GET /api/admin/metrics`
- `POST /api/admin/shutdown`

### SQL 백엔드 (`/platform/*`, app)
- `GET /platform/health`
- `POST /platform/auth/signup`
- `POST /platform/auth/login`
- `POST /platform/auth/refresh`
- `POST /platform/auth/logout`
- `GET /platform/problems`
- `GET /platform/problems/{problem_id}`
- `POST /platform/problems/{problem_id}/submit`
- `POST /platform/submissions/{submission_id}/analyze`
- `GET /platform/submissions/{submission_id}/status`
- `GET /platform/submissions/{submission_id}/analyses`
- `POST /platform/reports/milestone`
- `POST /platform/auditor/problem`
- `POST /platform/auditor/submit`
- `POST /platform/context-inference/problem`
- `POST /platform/context-inference/submit`
- `POST /platform/refactoring-choice/problem`
- `POST /platform/refactoring-choice/submit`
- `POST /platform/code-blame/problem`
- `POST /platform/code-blame/submit`
- `GET /platform/mode-jobs/{job_id}` (mode submit queue status)

## 분석 큐 (Redis + RQ)

분석 시작 API(`/platform/submissions/{id}/analyze`)는 기본적으로 큐에 작업을 넣고 즉시 반환합니다.

- 응답 필드: `analysis_id`, `message`, `job_id`
- 워커가 `app.services.analysis_service.run_analysis_background` 실행

관련 설정(`.env`):

```env
ANALYSIS_QUEUE_MODE=inline   # local 기본값: inline
ANALYSIS_QUEUE_NAME=analysis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

Docker에서는 `ANALYSIS_QUEUE_MODE=rq`, `REDIS_HOST=redis`로 오버라이드됩니다.


Platform mode submit queue behavior (auditor/context-inference/refactoring-choice/code-blame):

- queue response fields: `queued`, `message`, `jobId`
- queue job status: `GET /platform/mode-jobs/{job_id}`
- when finished, `result` includes the original submit response payload
## 리포트 고도화 (Milestone)

`POST /platform/reports/milestone` 결과 `stats`에 다음 정보가 포함됩니다.

- 기본: `total`, `passed`, `failed`, `error`, `pending`, `processing`, `avg_score`, `accuracy`
- 오답 분석: `wrong_type_breakdown`, `top_wrong_types`
- 세부 성과: `difficulty_breakdown`, `language_breakdown`
- 추세: `trend` (`label`, `accuracy_delta`, `avg_score_delta`, recent/previous window)
- 취약 구간: `weak_difficulties`, `weak_languages`

오답 유형 통계는 `user_problem_stats.wrong_answer_types` JSON 컬럼에 누적됩니다.

## 마이그레이션

```bash
alembic -c alembic.ini upgrade head
```

현재 헤드:
- `c3b7d2e9f14a` (`problems.kind`에 `code_blame` enum 추가)

직전 주요 리비전:
- `a1f5d8e7c9ab` (`problems.kind`에 `refactoring_choice` enum 추가)
- `9c2a7f54b3de` (`problems.kind`에 `context_inference` enum 추가)
- `4f1d5e9b2c31` (`problems.kind`에 `auditor` enum 추가)
- `d7a6c9b14e2f` (user_problem_stats에 `wrong_answer_types` 추가)

## 개발 의존성 설치

```bash
pip install -r requirements.txt
```

추가된 주요 의존성:
- `rq>=1.16`
- `redis>=5,<6`

## 보안 주의

`.env`의 값들은 개발용 예시입니다. 운영 시 다음 항목은 반드시 안전한 시크릿으로 교체하세요.
- `JWT_SECRET`
- `ADMIN_PANEL_KEY`
- `DB_PASSWORD`
- OAuth client secret/API keys

운영 보안 체크리스트:
- `DB_PASSWORD`, `JWT_SECRET`는 필수값으로 설정되어야 하며, 빈 값/약한 기본값으로 실행되지 않도록 구성되어 있습니다.
- `docker-compose.docker-socket.yml`(또는 런처 기본 동작)의 `/var/run/docker.sock:/var/run/docker.sock` 마운트는 컨테이너에 호스트 Docker 제어 권한을 줍니다.
- 가능하면 운영 환경에서는 Docker 소켓 마운트를 제거하거나, 별도 권한 분리된 관리 채널로 종료 기능을 대체하세요.
- 시크릿은 `.env` 평문 대신 Docker/Kubernetes secret 또는 파일 기반 주입(`*_FILE`) 사용을 권장합니다.
- 로그/에러 응답에 시크릿 값이 출력되지 않도록 운영 로그 레벨과 예외 메시지를 제한하세요.

## 현재 한계

- JSONL(`/api/*`)과 SQL(`/platform/*`)의 계정/학습 데이터가 아직 완전히 통합되지 않았습니다.
- JSONL 저장소는 파일 기반이라 다중 인스턴스/고가용성 운영에는 한계가 있습니다.

## 트러블슈팅

### 1) PowerShell에서 venv 활성화가 막힐 때
증상:
- `Activate.ps1` 실행 시 `PSSecurityException` 발생

해결:
- 활성화 없이 venv의 python을 직접 실행하세요.

```powershell
.venv\Scripts\python.exe run_server.py
```

또는(현재 세션만 정책 완화):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 2) Docker 모드와 로컬 모드가 헷갈릴 때
기준:
- `python run_server.py` => Docker Compose 모드
- `python run_server.py --local` => 로컬 uvicorn 모드

확인:

```powershell
docker compose ps
```

### 3) MySQL은 내려갔는데 API 컨테이너가 남아 있을 때
정상 종료 명령:

```powershell
docker compose down --remove-orphans
```

강제 정리(필요 시):

```powershell
docker rm -f code-platform-api code-platform-worker code-platform-mysql code-platform-redis
```

### 4) AI API 키를 못 읽을 때
점검 순서:
- `.env`에 `AI_API_KEY`(또는 사용하는 provider 키)가 실제로 설정되어 있는지 확인
- Docker 모드면 `env_file: .env`가 반영되도록 재시작

```powershell
docker compose up -d --build
```

- 로컬 모드면 같은 셸에서 실행했는지 확인하고, 필요하면 아래처럼 직접 주입

```powershell
$env:AI_API_KEY="your-key"
.venv\Scripts\python.exe run_server.py --local
```

### 5) 분석 큐 작업이 처리되지 않을 때
증상:
- `/platform/submissions/{id}/analyze` 호출 후 상태가 오래 `pending/processing`

확인:

```powershell
docker compose logs worker --tail=200
docker compose logs redis --tail=100
```

점검:
- `ANALYSIS_QUEUE_MODE=rq`(Docker), `REDIS_HOST=redis`
- 로컬 테스트는 `ANALYSIS_QUEUE_MODE=inline`으로 즉시 실행 가능

### 6) 관리자 API가 503(Admin key not configured)를 반환할 때
원인:
- `ADMIN_PANEL_KEY`가 설정되지 않은 상태입니다.

해결:
- `.env`에 키를 설정한 뒤 재시작하세요.
- 관리자 API는 쿼리스트링이 아니라 `X-Admin-Key` 헤더로 인증합니다.

```powershell
docker compose up -d --build
```

### 7) 관리자 패널에서 "스택 안전 종료"가 안 될 때
증상:
- 버튼이 비활성화되거나 종료 API가 `503`과 함께 `docker_socket_not_mounted`, `docker_control_unavailable` 등을 반환

원인:
- `--without-docker-socket`로 실행했거나, base compose 파일만으로 실행되어 소켓이 미마운트된 상태입니다.

해결:
- 기본 런처로 재시작하거나, socket override를 명시해 실행하세요.

```bash
python run_server.py
```

또는 compose를 직접 실행:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker-socket.yml up -d --build
```

## Observability

- Every `/platform/*` request gets `X-Request-Id` in response headers.
- Platform mode logs (`problem`, `submit`, `submit_background`) include `request_id`.
- Queue dispatch and enqueue-failure logs also include `request_id`.

## Auth Token Unification

`/api/*` and `/platform/*` now use JWT access tokens consistently.

- `/api/auth/guest` and `/api/auth/google/callback` issue platform JWT tokens.
- The same token can call both `/api/*` and `/platform/*` endpoints.
- Legacy JSONL session tokens (`username:randomhex`) are supported only during the migration window.

Legacy token settings (`.env`):

```env
CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS=true
CODE_PLATFORM_LEGACY_TOKEN_SUNSET_DATE=2026-03-31
```

Recommended migration timeline:
- `2026-02-09` to `2026-03-31`: allow legacy tokens and force users to re-login gradually.
- `2026-04-01` onward: set `CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS=false`.

When `/api` accepts a legacy token, these response headers are added:
- `X-Auth-Legacy-Token: true`
- `X-Auth-Legacy-Sunset-Date: 2026-03-31`

## 테스트/검증

현재 저장소에는 GitHub Actions workflow 파일(`.github/workflows/ci.yml`)이 포함되어 있지 않습니다.
로컬 검증 명령:
- `python -m compileall backend app server_runtime`
- `python -m unittest discover -s tests -q`

Added integration-focused tests in `tests/test_auth_unification.py`:
- `/api/auth/guest` token issuance path
- JWT-based `/api/me` access path
- Legacy token deprecation headers
- Platform JWT dependency check (`app.api.security_deps.get_current_user`)

## Extra Security Checklist

- Do not use weak/default `ADMIN_PANEL_KEY` values (for example: `change-this-admin-key`).
- Launcher (`python run_server.py`) now prints a warning if Docker socket mount is detected.
- Include `CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS` transition in your operation runbook.


## Docker Socket Override

Launcher 기본 실행(`python run_server.py`)은 관리자 패널의 전체 스택 종료를 위해
`docker-compose.docker-socket.yml` override를 자동으로 사용합니다.

Compose를 직접 실행할 때 동일 동작이 필요하면 override 파일을 함께 사용하세요:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker-socket.yml up -d --build
```

Equivalent launcher command:

```bash
python run_server.py --with-docker-socket
```

소켓 마운트를 비활성화하려면:

```bash
python run_server.py --without-docker-socket
```

소켓이 비활성화된 상태에서는 `/api/admin/shutdown`이 `503` 가이드를 반환합니다.

## Secrets And Build Context

- `.dockerignore` now excludes `.env` and `.env.*` from Docker build context.
- Use `.env.example` as a template and keep real secrets only in local `.env` (or secret manager).
