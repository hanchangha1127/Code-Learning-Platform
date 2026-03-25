# 환경 변수

실제 기본값과 검증 로직의 기준은 아래 파일입니다.

- `app/core/config.py`
- `backend/config.py`
- `.env.example`

## 1. 최소 필수값

아래 값이 없으면 플랫폼 API가 정상 기동하지 않습니다.

- `DB_PASSWORD`
- `JWT_SECRET`

제약:

- `JWT_SECRET` 는 32자 이상이어야 합니다.
- 운영 환경(`development`, `local`, `test` 외)에서는 개발용 접두사 secret 사용을 막습니다.

## 2. 데이터베이스 / JWT

플랫폼 API:

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_PASSWORD_FILE`
- `JWT_SECRET`
- `JWT_SECRET_FILE`
- `JWT_ALG`
- `ACCESS_TOKEN_EXPIRES_MIN`
- `REFRESH_TOKEN_EXPIRES_DAYS`

`*_FILE` 값은 secret file indirection 용도입니다.

## 3. AI / 모델 설정

공통:

- `AI_PROVIDER`
- `AI_API_KEY`
- `AI_API_KEY_FILE`
- `AI_REQUEST_TIMEOUT_SECONDS`

Google 계열:

- `GOOGLE_API_KEY`
- `GOOGLE_API_KEY_FILE`
- `GOOGLE_MODEL`
- `GOOGLE_API_ENDPOINT`

OpenAI 계열:

- `OPENAI_API_KEY`
- `OPENAI_API_KEY_FILE`
- `OPENAI_MODEL`

현재 `.env.example` 기본값:

- `AI_PROVIDER=mock`
- `GOOGLE_MODEL=gemini-3-flash-preview`
- `OPENAI_MODEL=gpt-4o-mini`

주의:

- 일반 문제 생성과 제출 피드백은 선택된 provider/model을 따릅니다.
- 학습 리포트 생성은 Google provider 경로에서 `gemini-3.1-pro-preview` 를 사용합니다.
- OpenAI provider 경로에서는 학습 리포트도 `OPENAI_MODEL` 을 사용합니다.

## 4. Google OAuth

필수값:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`

허용 URI:

- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- 선택 fallback: `GOOGLE_OAUTH_REDIRECT_URI`

file indirection:

- `GOOGLE_OAUTH_CLIENT_ID_FILE`
- `GOOGLE_OAUTH_CLIENT_SECRET_FILE`

주의:

- 외부/운영 도메인은 HTTPS URI만 허용 목록에 넣어야 합니다.
- 프록시 뒤에서 운영할 때는 `X-Forwarded-Proto`, `X-Forwarded-Host`, 필요 시 `X-Forwarded-Port` 전달이 맞아야 합니다.

## 5. 플랫폼 비밀번호 인증

기본값은 비활성입니다.

- `ALLOW_PLATFORM_PASSWORD_AUTH=false`

활성화 시 사용 경로:

- `POST /platform/auth/signup`
- `POST /platform/auth/login`
- `POST /platform/auth/refresh`

## 6. 게스트 / 레거시 호환

- `CODE_PLATFORM_GUEST_TTL_SECONDS`
- `CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS`
- `CODE_PLATFORM_LEGACY_TOKEN_SUNSET_DATE`
- `CODE_PLATFORM_LEGACY_TOKEN_MAX_AGE_SECONDS`
- `CODE_PLATFORM_ALLOW_SIDLESS_COOKIE_COMPAT`
- `CODE_PLATFORM_SIDLESS_COOKIE_SUNSET_AT`

의미:

- 게스트 토큰 TTL
- 레거시 JSONL 토큰 호환 여부
- sid 없는 쿠키 호환 유지 여부와 종료 시각

중요:

- 코드 기본값 기준으로 `CODE_PLATFORM_ALLOW_SIDLESS_COOKIE_COMPAT` 는 `false` 입니다.
- 현재 `.env.example` 은 rollout 점검용 예시값을 포함할 수 있으므로, 운영에서는 샘플 파일을 그대로 믿지 말고 최종 의도를 명시해야 합니다.

## 7. 프록시 신뢰 범위

- `CODE_PLATFORM_TRUSTED_PROXY_CIDRS`

설명:

- 게스트 rate limit, 관리자 throttling, forwarded IP 추출은 이 CIDR 목록에 포함된 프록시에서 들어온 요청에만 `X-Forwarded-For` / `X-Real-IP` 를 신뢰합니다.
- 미설정 시 기본 신뢰 범위는 loopback(`127.0.0.1/32`, `::1/128`) 입니다.

## 8. 큐 / Redis

- `ANALYSIS_QUEUE_MODE`
- `ANALYSIS_QUEUE_NAME`
- `PROBLEM_FOLLOW_UP_QUEUE_MODE`
- `PROBLEM_FOLLOW_UP_QUEUE_NAME`
- `ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS`
- `ANALYSIS_QUEUE_RESULT_TTL_SECONDS`
- `ANALYSIS_QUEUE_FAILURE_TTL_SECONDS`
- `ANALYSIS_PROCESSING_STALE_SECONDS`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`
- `REDIS_PASSWORD_FILE`

설명:

- 기본 개발 `.env.example` 는 `ANALYSIS_QUEUE_MODE=inline`
- 문제 생성 후속 저장도 별도 큐로 분리하려면 `PROBLEM_FOLLOW_UP_QUEUE_MODE=rq` 를 함께 켭니다.
- Compose 에서는 보통 Redis + `worker` + `worker-follow-up` 조합을 씁니다.
- queued 제출 상태 조회는 `GET /platform/mode-jobs/{job_id}` 로 합니다.

## 9. 워커 전용 환경 변수

- `RQ_WORKER_QUEUES`

설명:

- 워커 프로세스가 감시할 큐를 쉼표 구분으로 직접 지정합니다.
- 미설정 시 설정값을 기준으로 자동 계산합니다.
- 기본 Compose 예시는 `worker=analysis`, `worker-follow-up=problem-follow-up` 입니다.

## 10. 관리자 / 운영 제어

- `ADMIN_PANEL_KEY`
- `ADMIN_PANEL_KEY_FILE`
- `ADMIN_METRICS_WINDOW_MINUTES`
- `ADMIN_ACTIVE_WINDOW_SECONDS`
- `CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN`
- `ADMIN_THROTTLE_BACKEND`

주의:

- `ADMIN_PANEL_KEY` 는 20자 이상 랜덤 값으로 교체해야 합니다.
- `ADMIN_THROTTLE_BACKEND` 는 `redis` 또는 `memory` 만 허용됩니다.
- 관리자 종료는 기본 비활성입니다.
- Docker 스택 전체 종료는 보통 Docker socket mount 가 있을 때만 의미가 있습니다.

## 11. HTTPS

- `ENABLE_HTTPS`
- `TLS_CERTS_DIR`
- `SSL_CERTFILE`
- `SSL_KEYFILE`
- `HTTPS_BIND_PORT`
- `HTTPS_PUBLIC_PORT`
- `HTTP_REDIRECT_PORT`

동작:

- `ENABLE_HTTPS=true` 이면 앱 서버는 TLS 로 뜨고, 별도 HTTP redirect 서버가 함께 실행됩니다.
- cert/key 파일을 직접 지정하지 않으면 기본값은 `certs/fullchain.pem`, `certs/privkey.pem` 입니다.

## 12. CORS

- `CODE_PLATFORM_CORS_ORIGINS`

정책:

- credentialed CORS origin 은 `http` 인 경우 loopback host 에만 허용됩니다.
- 외부 origin 은 HTTPS 를 써야 합니다.
- 정책에 맞지 않는 origin 은 런타임에서 경고와 함께 drop 됩니다.

## 13. JSONL 데이터 경로

- `CODE_PLATFORM_DATA_DIR`
- `CODE_PLATFORM_USERS_DIR`

이 값들은 레거시 JSONL 데이터 디렉터리 위치를 결정합니다.

## 14. 사용자 설정과 언어 정규화 참고

선호 언어 저장은 아래 canonical ID 기준입니다.

- `python`
- `javascript`
- `typescript`
- `c`
- `java`
- `cpp`
- `csharp`
- `go`
- `rust`
- `php`

허용 alias:

- `py`
- `js`
- `ts`
- `c++`
- `cs`
- `c#`

유효하지 않은 저장값은 조회 시 canonical ID로 self-heal 되거나 기본값(`python`)으로 복구됩니다.

## 15. 추천 조합

### 로컬 개발

```env
APP_ENV=development
DB_HOST=localhost
REDIS_HOST=localhost
ANALYSIS_QUEUE_MODE=inline
PROBLEM_FOLLOW_UP_QUEUE_MODE=inline
ENABLE_HTTPS=false
```

### Docker Compose 개발

```env
DB_HOST=mysql
REDIS_HOST=redis
ANALYSIS_QUEUE_MODE=rq
PROBLEM_FOLLOW_UP_QUEUE_MODE=rq
```

### 운영

- 강한 `JWT_SECRET`
- 강한 `ADMIN_PANEL_KEY`
- 명시적인 `CODE_PLATFORM_TRUSTED_PROXY_CIDRS`
- 필요할 때만 Docker socket 사용
- OAuth 허용 URI와 프록시 헤더 구성을 같이 검토
- 레거시 토큰/쿠키 호환은 sunset 계획 없이 켜 두지 않기
