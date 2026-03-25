# 코드 학습 플랫폼

FastAPI 기반의 코드 학습 플랫폼입니다. 현재 구조는 정적 HTML 프런트엔드, `/platform` 중심의 새 API, `backend` 레거시 학습 엔진 브리지, MySQL/Redis 기반 저장소가 함께 동작하는 하이브리드 형태입니다.

## 현재 구조

- 진입점: `run_server.py`
- 루트 앱: `server_runtime.webapp`
- 새 API: `app.main` 이 `/platform` 으로 mount
- 레거시 호환: `/api/*` 일부는 `410 Gone` 으로 `/platform/*` 경로를 안내
- 프런트엔드: `frontend/desktop/*.html`, `frontend/mobile/*.html`, `frontend/shared/js/*`
- 관리자 페이지: `/admin.html`

실제 요청 흐름은 아래와 같습니다.

`run_server.py -> server_runtime.webapp -> /platform(app.main)`

## 현재 학습 모드

현재 활성 모드는 10개입니다.

- `analysis`
- `codeblock`
- `arrange`
- `codecalc`
- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

`context-inference` 관련 백엔드 코드는 남아 있지만, 현재 사용자 노출 모드에는 포함되지 않습니다.

## 지원 언어

현재 공용 언어 카탈로그의 canonical ID는 아래 10개입니다.

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

허용 alias는 아래처럼 canonical ID로 정규화됩니다.

- `py` -> `python`
- `js` -> `javascript`
- `ts` -> `typescript`
- `c++` -> `cpp`
- `cs`, `c#` -> `csharp`

## 실행 방법

### 1. 환경 준비

```bash
pip install -r requirements.txt
copy .env.example .env
```

최소 필수값:

- `DB_PASSWORD`
- `JWT_SECRET`

`JWT_SECRET` 는 32자 이상이어야 합니다.

### 2. 기본 개발 실행

```bash
python run_server.py
```

기본 동작:

- `docker compose` 개발 스택을 백그라운드로 실행합니다.
- 기본 대상 서비스는 `mysql`, `redis`, `api`, `worker`, `worker-follow-up` 입니다.
- 준비가 끝나면 `/admin.html` 을 엽니다.
- Docker socket mount 는 기본 활성화입니다.

자주 쓰는 옵션:

```bash
python run_server.py --foreground
python run_server.py --no-open-admin
python run_server.py --without-docker-socket
```

### 3. 운영형 Compose 실행

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

운영형 스택은 `docker-compose.ops.yml` 을 사용하고, `api`, `worker`, `worker-follow-up` 을 read-only root filesystem + `tmpfs` 형태로 실행합니다.

### 4. 로컬 uvicorn 실행

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

로컬 모드에서는 MySQL/Redis 를 별도로 준비해야 합니다.

참고:

- `server_runtime/launcher.py` 의 로컬 기본 worker 값은 `16` 입니다.
- 문서 예시는 개발 재현성과 로그 확인 편의를 위해 `--workers 1` 기준으로 적었습니다.

## 인증

기본 활성 인증:

- Google OAuth: `GET /platform/auth/google/start`, `GET /platform/auth/google/callback`
- 게스트 로그인: `POST /platform/auth/guest`
- 로그아웃: `POST /platform/auth/logout`

비밀번호 인증은 기본 비활성입니다. 아래 값을 켜야 사용 가능합니다.

```env
ALLOW_PLATFORM_PASSWORD_AUTH=true
```

관련 경로:

- `POST /platform/auth/signup`
- `POST /platform/auth/login`
- `POST /platform/auth/refresh`

레거시 JWT/쿠키 호환은 점진적으로 축소 중입니다. 코드 기본값 기준으로 sid 없는 쿠키 호환은 꺼져 있으며, 필요 시 명시적으로만 활성화해야 합니다.

## 큐와 스트리밍

### 큐

- 기본 `.env.example` 값은 `ANALYSIS_QUEUE_MODE=inline`
- 제출 분석 큐는 `ANALYSIS_QUEUE_MODE` / `ANALYSIS_QUEUE_NAME`
- 문제 생성 후속 저장 큐는 `PROBLEM_FOLLOW_UP_QUEUE_MODE` / `PROBLEM_FOLLOW_UP_QUEUE_NAME`
- Compose 스택에서는 보통 Redis + `worker` + `worker-follow-up` 조합을 사용합니다.

아래 모드의 제출은 `rq` 모드에서 queued 응답을 반환할 수 있습니다.

- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

상태 조회:

```text
GET /platform/mode-jobs/{job_id}
```

### 문제 생성 스트리밍

- 대부분의 문제 생성은 SSE 상태 이벤트를 먼저 보내고, 최종 문제 본문은 마지막 `payload` 한 번으로 전달합니다.
- 서버 상태 phase는 보통 `queued -> generating -> rendering -> persisting -> done` 순서입니다.
- 현재 구조는 “토큰 단위 본문 스트리밍”이 아니라 “상태 스트리밍 + 최종 payload 전달”에 가깝습니다.
- 스트림 성공 판정은 `payload` 자체가 아니라 마지막 `done` 이벤트의 `persisted=true` 까지 포함합니다.
- `arrange` 는 의도적으로 가짜 스트리밍 UI를 사용합니다.

## 자주 쓰는 공개 경로

### 공통

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

추가 참고:

- `/platform/profile` 은 런타임 이력과 DB 제출 이력을 합산한 누적 통계를 반환합니다.
- `/platform/home` 은 streak, daily goal, review queue, 추천 모드, 최신 리포트 카드 데이터를 함께 제공합니다.
- `/platform/learning/history` 는 `history`, `total`, `hasMore`, `limit` 을 포함한 페이지형 응답입니다.

### 리포트

- `GET /platform/report`
- `POST /platform/reports/milestone`
- `GET /platform/reports/latest`
- `GET /platform/reports/{report_id}/pdf`

프로필 페이지는 `GET /platform/reports/latest` 를 이용해 최신 리포트 카드와 PDF 다운로드 버튼을 구성합니다.

### 학습 이력 / 복습

- `GET /platform/learning/history`
- `GET /platform/learning/memory`
- `GET /platform/learning/review-queue`
- `GET /platform/review-queue/{item_id}/resume`

고급 분석 3종 이력은 프로필의 오답 노트에서 읽기 전용 workbench 형태로 다시 열 수 있습니다.

### 제출 / 분석

- `GET /platform/problems`
- `GET /platform/problems/{problem_id}`
- `POST /platform/problems/{problem_id}/submit`
- `POST /platform/submissions/{submission_id}/analyze`
- `GET /platform/submissions/{submission_id}/status`
- `GET /platform/submissions/{submission_id}/analyses`

## 레거시 `/api` 경로

레거시 학습 경로 대부분은 더 이상 주 경로가 아닙니다. 대표 경로들은 `410 Gone` 과 함께 새 `/platform` 경로를 응답합니다.

인증 레거시 경로 매핑 예시:

- `/api/auth/register` -> `/platform/auth/signup`
- `/api/auth/login` -> `/platform/auth/login`
- `/api/auth/guest/start` -> `/platform/auth/guest`

기타 예시:

- `/api/learning/memory` -> `/platform/learning/memory`

예외적으로 아직 남아 있는 레거시 조회 경로도 있습니다.

- `GET /api/tracks`

## 테스트

전체 Python 테스트:

```bash
python -m unittest discover -s tests -v
```

Playwright 스모크:

```bash
npm install
npx playwright install chromium
set CI=1
set ENABLE_HTTPS=0
npx playwright test tests/e2e/smoke.spec.mjs
```

2026-03-21 기준 최신 검증 스냅샷:

- Python `unittest`: `269/269` 통과
- Playwright smoke: `54/54` 통과

## 문서

- [아키텍처](./docs/architecture.md)
- [환경 변수](./docs/environment.md)
- [운영 가이드](./docs/runbook.md)
- [문제 해결](./docs/troubleshooting.md)
