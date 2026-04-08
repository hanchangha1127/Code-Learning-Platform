# 아키텍처

## 개요

현재 서버 구조는 `server/` 단일 패키지를 기준으로 합니다.

```text
run_server.py
  -> server.app
    -> server.bootstrap
    -> server.features.*
    -> server.infra.*
```

핵심 원칙은 다음 3개입니다.

1. 루트 진입은 `run_server.py -> server.app` 하나로 고정합니다.
2. feature 진입은 `api.py` 또는 `legacy_api.py`로 통일합니다.
3. router는 service와 infra를 호출하고, feature끼리 서로의 router를 직접 import하지 않습니다.

## 루트 구조

```text
server/
frontend/
tests/
docs/
alembic/
```

- `server/`: 백엔드와 런타임
- `frontend/`: 정적 페이지와 공용 자산
- `tests/`: 서버 테스트와 E2E
- `docs/`: 구조와 운영 문서
- `alembic/`: DB 마이그레이션

## 서버 구조

### 앱 조립

- `server/app.py`
  - FastAPI 앱 생성
  - CORS, request-id, metrics, redirect middleware 등록
  - canonical `/platform/*` router 등록
  - legacy `/api/*` router 등록
  - `/static/*` mount
  - admin / health / page endpoint 등록

### 부트스트랩과 dependency

- `server/bootstrap.py`
  - 설정 로드
  - storage/service singleton 초기화
  - Google OAuth helper 구성
  - admin metrics와 user service 초기화

- `server/dependencies.py`
  - DB session dependency
  - runtime/service accessor
  - 공통 request user dependency

### core / infra / db

- `server/core`
  - `config.py`: DB, JWT, queue 관련 설정
  - `runtime_config.py`: OAuth, HTTPS, CORS, admin, runtime 설정
  - `security.py`: 토큰/비밀번호 보안 helper
  - `proxy.py`: trusted proxy 해석

- `server/infra`
  - AI client
  - admin metrics
  - JSONL user storage/service
  - 기타 기술 인프라 helper

- `server/db`
  - SQLAlchemy model과 session

## feature 지도

### `server/features/auth`

- `api.py`: `/platform/auth/*`
- `legacy_api.py`: `/api/auth/*`
- `service.py`: 인증 로직
- `dependencies.py`: current user dependency
- `helpers.py`: OAuth, cookie, guest helper

### `server/features/account`

- `api.py`: `/platform/me`, `/platform/me/settings`, `/platform/me/goal`
- `service.py`: 사용자 설정과 목표 관리

### `server/features/learning`

학습 기능의 중심 feature입니다.

- `api.py`: canonical 학습 router 진입
- `legacy_api.py`: `/api/*` 호환 학습 경로
- `service.py`: `LearningService` façade와 공통 orchestration
- `analysis_service.py`: 일반 분석형 문제 처리
- `problem_service.py`: 문제 생성/조회 helper
- `submission_service.py`: 제출 처리 helper
- `history.py`: 문제/제출 persistence, history/profile 집계
- `streaming.py`: SSE problem streaming
- `generator.py`: 문제 생성 orchestration
- `generator_normalize.py`: 생성기 normalize/parse helper
- `continuity.py`: 복습/연속 학습
- `reporting.py`: 학습 리포트 집계 helper
- `tiering.py`: 숙련도와 tier 계산
- `policies.py`: 모드 정책 상수
- `normalization.py`: 공용 normalize 규칙
- `catalog.py`: 모드/문제 kind 매핑

고급 분석 3모드인 `single-file-analysis`, `multi-file-analysis`, `fullstack-analysis`는 공통 생성 경로를 공유합니다.

```text
api_advanced_analysis.py
  -> service.py
    -> generator.py
      -> generator_normalize.py
    -> history.py
    -> streaming.py
```

### `server/features/reports`

- `api.py`: `/platform/reports/*`
- `service.py`: report assembly
- `pdf.py`: PDF rendering

### `server/features/jobs`

- `api.py`: `/platform/mode-jobs/*`
- `queue.py`: enqueue/status helper

### `server/features/runtime_ui`

- `pages.py`: desktop/mobile HTML 응답
- `health.py`: health endpoint
- `admin.py`: admin page와 shutdown API
- `template_renderer.py`: asset version injection
- `user_agent.py`: 모바일/데스크톱 분기

## 라우팅 정책

### canonical

- `/platform/auth/*`
- `/platform/me/*`
- `/platform/*` 학습 모드
- `/platform/reports/*`
- `/platform/mode-jobs/*`

### legacy

- `/api/auth/*`
- `/api/*` 학습 호환 경로
- `/api/admin/*`

대부분의 제거된 옛 학습 경로는 `410 Gone`으로 canonical `/platform/*` 경로를 안내합니다.

## 프런트 구조

```text
frontend/
  pages/
    admin.html
    desktop/
    mobile/
  assets/
    css/
    js/
      core/
      pages/
      widgets/
```

- `pages/`: 실제 HTML 엔트리
- `assets/js/core`: API/auth/stream 공용 클라이언트
- `assets/js/pages`: 페이지별 엔트리 스크립트
- `assets/js/widgets`: 고급 분석 셸, history view, review resume 같은 UI 모듈

## 저장소와 queue

### MySQL

주요 영속 데이터:

- user / session
- problem / submission / ai analysis
- report
- mode job / queue state
- platform ops events

### Redis + RQ

사용 용도:

- queued mode submit
- problem follow-up
- mode job status

### JSONL user storage

과거 학습 엔진과의 호환용 저장소입니다.

## 테스트 구조

```text
tests/
  server/
    auth/
    infra/
    learning/
    reports/
    runtime/
  e2e/
```

기본 서버 테스트:

```bash
python -m unittest discover -s tests/server -t . -v
```

E2E:

```bash
cmd /c npm run test:e2e -- tests/e2e/smoke.spec.mjs tests/e2e/inline_streaming.spec.mjs
```
