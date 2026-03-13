# 환경변수

환경변수의 실제 소비 지점은 주로 다음 두 곳입니다.

- `app/core/config.py`
  - `/platform` 메인 백엔드 설정
- `backend/config.py`
  - 레거시 JSONL 런타임, Google OAuth, 관리자 설정

자세한 기본값은 [`.env.example`](../.env.example)를 기준으로 확인하면 됩니다.

## 1. 항상 필요한 값

다음 값은 플랫폼 서버를 정상 부팅하려면 반드시 유효해야 합니다.

- `DB_PASSWORD`
  - `/platform` 설정 검증에서 필수입니다.
- `JWT_SECRET`
  - 최소 32자여야 합니다.

다음 값은 보통 함께 사용합니다.

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `APP_ENV`
- `JWT_ALG`
- `ACCESS_TOKEN_EXPIRES_MIN`
- `REFRESH_TOKEN_EXPIRES_DAYS`

## 2. 기능 사용 시 필요한 값

### Google OAuth 로그인

다음 기능을 사용할 때 필요합니다.

- `GET /platform/auth/google/start`
- `GET /platform/auth/google/callback`
- 레거시 `/api/auth/google/*`

필요 값:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- 선택: `GOOGLE_OAUTH_REDIRECT_URI`
  - 레거시 단일 URI fallback입니다.

파일 기반 비밀값도 지원합니다.

- `GOOGLE_OAUTH_CLIENT_ID_FILE`
- `GOOGLE_OAUTH_CLIENT_SECRET_FILE`

### AI 문제 생성 / 리포트 생성

문제 생성과 학습 리포트 생성 기능을 사용할 때 필요합니다.

- `AI_PROVIDER`
- `GOOGLE_API_KEY`
- `AI_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_MODEL`
- `GOOGLE_API_ENDPOINT`
- `OPENAI_MODEL`
- `AI_REQUEST_TIMEOUT_SECONDS`

파일 기반 비밀값 지원:

- `GOOGLE_API_KEY_FILE`
- `AI_API_KEY_FILE`

참고:

- 일반 문제 생성기는 주로 `GOOGLE_API_KEY` 또는 `AI_API_KEY`를 사용합니다.
- `OPENAI_API_KEY`는 `AI_PROVIDER=openai` 계열 설정일 때 사용됩니다.

### 플랫폼 비밀번호 인증

다음 경로를 활성화할 때 사용합니다.

- `POST /platform/auth/signup`
- `POST /platform/auth/login`
- `POST /platform/auth/refresh`

설정:

- `ALLOW_PLATFORM_PASSWORD_AUTH`

기본값은 `false`입니다.

### 게스트 / 레거시 JSONL 토큰 호환

- `CODE_PLATFORM_GUEST_TTL_SECONDS`
- `CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS`
- `CODE_PLATFORM_LEGACY_TOKEN_SUNSET_DATE`
- `CODE_PLATFORM_LEGACY_TOKEN_MAX_AGE_SECONDS`

## 3. 운영 / 큐 / 관리자용 값

### Redis / 큐

- `ANALYSIS_QUEUE_MODE`
  - `inline` 또는 `rq`
- `ANALYSIS_QUEUE_NAME`
- `ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS`
- `ANALYSIS_QUEUE_RESULT_TTL_SECONDS`
- `ANALYSIS_QUEUE_FAILURE_TTL_SECONDS`
- `ANALYSIS_PROCESSING_STALE_SECONDS`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`

참고:

- `.env.example` 기본값은 `inline`입니다.
- Docker Compose 실행에서는 `api`와 `worker` 컨테이너에 `ANALYSIS_QUEUE_MODE=rq`가 주입됩니다.

### 관리자 / 관측

- `ADMIN_PANEL_KEY`
- `ADMIN_METRICS_WINDOW_MINUTES`
- `ADMIN_ACTIVE_WINDOW_SECONDS`

`ADMIN_PANEL_KEY`가 없으면 `/api/admin/*`는 정상 운영이 어렵습니다. 관리자 종료 기능은 여기에 더해 Docker socket mount가 있어야 활성화됩니다.

### 브라우저 접근 제어

- `CODE_PLATFORM_CORS_ORIGINS`

### JSONL 데이터 경로

- `CODE_PLATFORM_DATA_DIR`
- `CODE_PLATFORM_USERS_DIR`

이 값은 레거시 런타임의 JSONL 저장 경로를 결정합니다.

## 4. 값 선택 가이드

### 로컬 개발

- `APP_ENV=development`
- `DB_HOST=localhost`
- `REDIS_HOST=localhost`
- `ANALYSIS_QUEUE_MODE=inline`

### Docker Compose

Compose 파일이 다음 값을 덮어씁니다.

- `DB_HOST=mysql`
- `REDIS_HOST=redis`
- `ANALYSIS_QUEUE_MODE=rq`

### 운영 환경

- 강한 `JWT_SECRET` 사용
- 강한 `ADMIN_PANEL_KEY` 사용
- 필요한 경우에만 Docker socket mount 사용
- 프록시 환경에서는 Google OAuth 리디렉션 허용 URI와 `X-Forwarded-*` 헤더를 함께 검토
