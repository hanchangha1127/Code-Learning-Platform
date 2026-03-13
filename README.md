# 코드 학습 플랫폼

FastAPI 기반 코드 학습 플랫폼입니다. 현재 구현은 하나의 프로세스 안에서 다음 세 축을 함께 제공합니다.

- `run_server.py`
  - 전체 서버 진입점입니다.
- `server_runtime`
  - 루트 FastAPI 셸입니다.
  - `/health`, `/admin.html`, `/api/admin/*`, 페이지 렌더링, 레거시 `/api` 안내 경로를 담당합니다.
- `app`
  - `/platform`에 mount 되는 메인 백엔드입니다.
  - 인증, 학습 모드, 문제/제출, 리포트, 복습 큐, 사용자 설정을 담당합니다.

핵심 요청 흐름은 `run_server.py -> server_runtime.webapp -> /platform(app.main)` 입니다.

## 아키텍처 요약

- `/platform`
  - 현재의 주 공개 API입니다.
  - MySQL 기반 사용자/문제/제출/리포트 데이터를 관리합니다.
  - Redis 기반 큐와 작업 상태를 사용합니다.
- `/api`
  - 페이지/헬스/관리 셸과 레거시 호환 계층입니다.
  - 학습 관련 다수 경로는 `410 Gone`으로 새 `/platform` 경로를 안내합니다.
- `backend`
  - 기존 JSONL 기반 학습 엔진과 문제 생성 로직이 남아 있습니다.
  - `app.services.platform_public_bridge`가 이 계층을 호출하고 결과를 플랫폼 DB에 이중 저장합니다.

## 프런트 구조

- 사용자 페이지
  - `frontend/desktop/*.html`
  - `frontend/mobile/*.html`
  - `server_runtime/routes/pages.py`가 User-Agent를 보고 desktop/mobile variant를 선택합니다.
- 관리자 페이지
  - `frontend/app/admin.html`
  - responsive 단일 템플릿으로 렌더링됩니다.
- 공용 자산
  - `frontend/shared/css/*`
  - `frontend/shared/js/*`

정적 자산은 응답 직전에 `?v=` 버전 쿼리가 자동 주입됩니다. 사용자 페이지 응답에는 `Vary: User-Agent`가 설정됩니다.

## 데이터 저장소

- MySQL
  - 플랫폼 사용자, 설정, 문제, 제출, AI 분석, 리포트, 복습 큐, 운영 이벤트를 저장합니다.
- Redis
  - `rq` 큐 모드에서 분석 작업과 고급 학습 모드 제출 작업을 처리합니다.
- JSONL
  - 레거시 사용자 프로필, 학습 이력, 일부 런타임 상태를 저장합니다.
  - 현재는 브리지/호환 계층으로 유지됩니다.

## 빠른 시작

### 1. 환경 준비

```bash
pip install -r requirements.txt
copy .env.example .env
```

필수 시작 조건:

- `DB_PASSWORD`
- `JWT_SECRET`

`JWT_SECRET`는 최소 32자여야 합니다.

### 2. 기본 개발 실행

```bash
python run_server.py
```

기본 동작:

- `docker compose`를 백그라운드로 실행합니다.
- `docker-compose.yml` + `docker-compose.dev.yml` + `docker-compose.docker-socket.yml` 조합을 사용합니다.
- `mysql`, `redis`, `api`, `worker` 4개 서비스를 기동합니다.
- readiness를 기다린 뒤 `/admin.html`을 브라우저로 엽니다.
- Docker socket mount가 기본 활성화되어 관리자 종료 기능을 사용할 수 있습니다.

개발용에서 Docker socket을 끄려면:

```bash
python run_server.py --without-docker-socket
```

브라우저 자동 오픈을 끄려면:

```bash
python run_server.py --no-open-admin
```

```env
ENABLE_HTTPS=true
TLS_CERTS_DIR=certs
HTTPS_BIND_PORT=8443
HTTPS_PUBLIC_PORT=443
HTTP_REDIRECT_PORT=8000
```

HTTPS Compose를 켜면 `80 -> 8000`은 HTTP to HTTPS redirect, `443 -> 8443`은 TLS 앱 서버로 동작합니다. 기본 인증서 경로는 `certs/fullchain.pem`, `certs/privkey.pem` 입니다.

### 3. 운영형 Compose 실행

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

운영형 특징:

- `docker-compose.yml` + `docker-compose.ops.yml` 조합을 사용합니다.
- `api`와 `worker`는 read-only root filesystem + `tmpfs`로 실행됩니다.
- 개발용 소스 바인드 마운트가 제거됩니다.

운영형에서 관리자 종료 기능을 끄려면:

```bash
python run_server.py --compose-mode ops --without-docker-socket
```

### 4. 로컬 uvicorn 실행

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

```bash
ENABLE_HTTPS=true TLS_CERTS_DIR=certs python run_server.py --local --host 127.0.0.1 --workers 1
```

로컬 모드 주의사항:

- MySQL/Redis는 별도로 준비해야 합니다.
- 컨테이너와 달리 Alembic 마이그레이션을 수동 적용해야 합니다.
- `.env.example` 기준 기본 큐 모드는 `inline`입니다.

### 5. 컨테이너 실행 시 마이그레이션

컨테이너 모드에서는 `entrypoint.sh`가 다음 순서로 자동 처리합니다.

1. MySQL 대기
2. `alembic upgrade head`
3. `python -m server_runtime.runtime_server`

## 인증과 세션

### 기본 제공 인증

- Google OAuth
  - 시작: `GET /platform/auth/google/start`
  - 콜백: `GET /platform/auth/google/callback`
- 게스트 로그인
  - `POST /platform/auth/guest`
  - IP 기준 분당 12회 rate limit
- 로그아웃
  - `POST /platform/auth/logout`

### 선택적 비밀번호 인증

다음 경로는 기본 비활성입니다.

- `POST /platform/auth/signup`
- `POST /platform/auth/login`
- `POST /platform/auth/refresh`

활성화하려면 `.env`에 다음 값을 설정합니다.

```env
ALLOW_PLATFORM_PASSWORD_AUTH=true
```

### 세션 쿠키

- 쿠키명: `code_learning_access`
- 속성: `HttpOnly`, `SameSite=Lax`, `Path=/`
- `APP_ENV`가 개발 계열이 아니면 `Secure=true`

### Google OAuth 환경변수

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- `ENABLE_HTTPS=true` local direct TLS를 쓰면 `https://localhost:8443/platform/auth/google/callback` 도 허용 목록에 추가해야 합니다.

프록시 뒤에서 운영할 때는 다음 헤더가 올바르게 전달되어야 합니다.

- `X-Forwarded-Proto`
- `X-Forwarded-Host`
- 필요 시 `X-Forwarded-Port`

## 학습 모드

현재 제공 모드:

- 코드 분석
- 코드 블록
- 코드 배치
- 코드 계산
- 코드 오류
- 감사관 모드
- 맥락 추론
- 최적의 선택
- 범인 찾기

`/platform`은 모든 모드의 문제 생성과 제출 경로를 제공합니다.

- `POST /platform/analysis/problem`
- `POST /platform/analysis/submit`
- `POST /platform/codeblock/problem`
- `POST /platform/codeblock/submit`
- `POST /platform/arrange/problem`
- `POST /platform/arrange/submit`
- `POST /platform/codecalc/problem`
- `POST /platform/codecalc/submit`
- `POST /platform/codeerror/problem`
- `POST /platform/codeerror/submit`
- `POST /platform/auditor/problem`
- `POST /platform/auditor/submit`
- `POST /platform/context-inference/problem`
- `POST /platform/context-inference/submit`
- `POST /platform/refactoring-choice/problem`
- `POST /platform/refactoring-choice/submit`
- `POST /platform/code-blame/problem`
- `POST /platform/code-blame/submit`

고급 모드 제출(`auditor`, `context-inference`, `refactoring-choice`, `code-blame`)은 `ANALYSIS_QUEUE_MODE=rq`일 때 queued 응답을 반환할 수 있습니다. 이 경우 상태 조회는 다음 경로를 사용합니다.

- `GET /platform/mode-jobs/{job_id}`

## 주요 공개 경로

### 공통 / 사용자

- `GET /health`
- `GET /platform/health`
- `GET /platform/languages`
- `GET /platform/profile`
- `GET /platform/me`
- `GET /platform/me/settings`
- `PUT /platform/me/settings`
- `GET /platform/me/goal`
- `PUT /platform/me/goal`
- `GET /platform/home`
- `GET /platform/report`
- `POST /platform/reports/milestone`
- `GET /platform/learning/history`
- `GET /platform/learning/memory`
- `GET /platform/learning/review-queue`
- `GET /platform/review-queue/{item_id}/resume`

### 문제 / 제출 / 분석

- `GET /platform/problems`
- `GET /platform/problems/{problem_id}`
- `POST /platform/problems/{problem_id}/submit`
- `POST /platform/submissions/{submission_id}/analyze`
- `GET /platform/submissions/{submission_id}/status`
- `GET /platform/submissions/{submission_id}/analyses`

### 관리자

- `GET /api/admin/metrics`
- `POST /api/admin/shutdown`

## 레거시 `/api` 경로

`/api`는 현재도 다음 역할을 가집니다.

- `/admin.html`과 관리자 API
- `/health`
- 페이지 렌더링 셸
- 일부 레거시 인증 호환 경로

하지만 학습 관련 기존 공개 계약은 더 이상 주 사용 경로가 아닙니다. 예를 들어 다음 경로들은 `410 Gone`으로 `/platform` 새 경로를 안내합니다.

- `/api/profile`
- `/api/languages`
- `/api/report`
- `/api/diagnostics/start`
- `/api/problem/submit`
- `/api/code-block/problem`
- `/api/code-arrange/problem`
- `/api/code-calc/problem`
- `/api/code-error/problem`
- `/api/auditor/problem`
- `/api/context-inference/problem`
- `/api/refactoring-choice/problem`
- `/api/code-blame/problem`

`/api/auth/*` 경로는 런타임 셸 호환 때문에 일부 남아 있지만, 문서상 주 인증 경로는 `/platform/auth/*`를 기준으로 봐야 합니다.

## 테스트

### 전체 Python 테스트

```bash
python -m unittest discover -s tests -v
```

### 문서/계약 관련 핵심 테스트

```bash
python -m unittest tests.test_mode_api_platform_parity tests.test_auth_unification tests.test_pages_template_variant tests.test_launcher_defaults -v
```

### JS 문법 확인

```bash
Get-ChildItem frontend/shared/js/*.js | ForEach-Object { node --check $_.FullName }
```

### 브라우저 스모크 테스트

```bash
npm install
npx playwright install chromium
npx playwright test
```

## 문서

- [아키텍처](./docs/architecture.md)
- [환경변수](./docs/environment.md)
- [운영 런북](./docs/runbook.md)
- [트러블슈팅](./docs/troubleshooting.md)
