# 아키텍처

## 1. 서버 조립 구조

현재 프로젝트는 하나의 FastAPI 프로세스 안에서 두 계층을 함께 제공합니다.

- `run_server.py`
  - 프로세스 진입점입니다.
- `server_runtime.webapp`
  - 루트 FastAPI 앱입니다.
  - `/health`, `/admin.html`, `/api/admin/*`, 페이지 렌더링, 레거시 `/api` 경로를 담당합니다.
- `app.main`
  - 메인 플랫폼 백엔드입니다.
  - `server_runtime.webapp`에 `/platform`으로 mount 됩니다.

즉 실제 공개 구조는 `run_server.py -> server_runtime.webapp -> /platform(app.main)` 입니다.

## 2. 역할 경계

### `/platform`

- 현재의 주 공개 API입니다.
- MySQL 기반 사용자, 문제, 제출, AI 분석, 리포트, 복습 큐, 운영 이벤트를 관리합니다.
- Redis 기반 큐를 사용해 분석 작업과 일부 모드 제출을 비동기로 처리할 수 있습니다.

### `/api`

- 페이지/헬스/관리 셸입니다.
- 레거시 런타임 인증과 호환 경로 일부를 유지합니다.
- 기존 학습 공개 경로 대부분은 `410 Gone`으로 새 `/platform` 경로를 안내합니다.

장기적으로 공개 계약의 기준은 `/platform`입니다.

## 3. 백엔드 계층

### `app`

- 플랫폼 API 라우터와 SQLAlchemy 모델을 관리합니다.
- 얇은 라우터 + 서비스 계층 구조입니다.
- 사용자 설정, 학습 목표, 문제/제출, 리포트, 큐 상태 조회를 제공합니다.

### `backend`

- 기존 JSONL 기반 학습 엔진과 문제 생성 로직을 유지합니다.
- `LearningService`, `ProblemGenerator`, JSONL 사용자 저장소가 이 계층에 있습니다.

### `platform_public_bridge`

- `app.services.platform_public_bridge`가 `backend` 학습 엔진을 호출합니다.
- 런타임 결과를 그대로 반환하면서, 동시에 플랫폼 DB에도 문제/제출/분석/리포트 데이터를 저장합니다.
- 현재 하이브리드 구조의 핵심 접점입니다.

## 4. 데이터 계층

### MySQL

- `users`, `user_settings`, `user_sessions`
- `problems`, `submissions`, `ai_analyses`
- `reports`
- `review_queue_items`
- `platform_ops_events`

### Redis

- `ANALYSIS_QUEUE_MODE=rq`일 때 `rq` 작업 큐와 작업 상태 저장소로 사용됩니다.
- compose 실행에서는 `api`와 별도 `worker` 컨테이너가 이 큐를 소비합니다.

### JSONL

- 사용자별 레거시 프로필, 학습 이력, 일부 런타임 상태를 저장합니다.
- `backend.user_storage.UserStorageManager`가 `data/users/*.jsonl` 파일을 관리합니다.
- 현재는 브리지/호환 계층으로 남아 있으며, 일부 프로필/이력 집계가 여기서도 읽힙니다.

## 5. 프런트와 템플릿 렌더링

### 사용자 페이지

- `frontend/desktop/*.html`
- `frontend/mobile/*.html`

`server_runtime.routes.pages`가 User-Agent를 보고 desktop/mobile variant를 선택합니다.

### 관리자 페이지

- `frontend/app/admin.html`

관리자 페이지는 responsive 단일 템플릿으로 렌더링되며, 사용자 페이지처럼 User-Agent 분기를 사용하지 않습니다.

### 공용 자산

- `frontend/shared/css/*`
- `frontend/shared/js/*`

`server_runtime.template_renderer`가 HTML 응답 직전에 `/static/...` 자산에 `?v=`를 자동 주입합니다. 사용자 페이지 응답에는 `Vary: User-Agent`가 설정됩니다.

## 6. 큐와 백그라운드 실행

### 일반 코드 제출 분석

- `POST /platform/problems/{problem_id}/submit`
- `POST /platform/submissions/{submission_id}/analyze`
- `GET /platform/submissions/{submission_id}/status`

일반 코드 제출 분석은 `rq` 또는 인프로세스 background task로 동작합니다.

### 고급 모드 제출

- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

이 모드들은 `rq`가 켜져 있으면 queued 응답을 반환할 수 있습니다. 상태 조회는 `GET /platform/mode-jobs/{job_id}`를 사용합니다.

문제 생성 경로는 대부분 SSE 상태 이벤트를 먼저 보내고, 최종 문제 본문은 `payload` 1회로 전달합니다. `arrange`는 예외로 클라이언트 애니메이션 기반 가짜 스트리밍을 사용합니다.

## 7. 레거시 호환 정책

- `/api` 학습 경로는 더 이상 주 API가 아닙니다.
- 주요 레거시 경로는 `410 Gone`과 함께 새 `/platform` 경로를 응답에 포함합니다.
- `/api/auth/*`는 런타임 셸 호환 때문에 일부 유지되지만, 문서 기준의 주 인증 경로는 `/platform/auth/*`입니다.
