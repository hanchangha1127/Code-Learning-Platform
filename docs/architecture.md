# 아키텍처

## 1. 시스템 개요

현재 프로젝트는 하나의 FastAPI 런타임 안에 아래 3개 계층이 공존합니다.

- `server_runtime`
  - 루트 웹앱, 페이지 라우팅, 관리자 API, 레거시 `/api` 호환 레이어
- `app`
  - `/platform` 기준의 새 API, DB 모델, 인증, 리포트, 복습 큐, 플랫폼 운영 로직
- `backend`
  - 레거시 학습 엔진, 문제 생성기, JSONL 기반 사용자 데이터/이력 처리

실제 진입 흐름:

`run_server.py -> server_runtime.webapp -> /platform(app.main)`

## 2. 책임 경계

### `server_runtime`

주요 역할:

- `/health`
- `/admin.html`
- `/api/admin/*`
- 정적 페이지 렌더링
- 레거시 `/api/*` 경로 410 안내
- `/platform` mount

주의:

- 공용 API 계약의 기준은 `/platform` 입니다.
- 관리자 throttling 과 게스트 rate limit 은 프록시 헤더를 무조건 신뢰하지 않고, `CODE_PLATFORM_TRUSTED_PROXY_CIDRS` 범위에서만 `X-Forwarded-For` / `X-Real-IP` 를 반영합니다.

### `app`

주요 역할:

- 인증과 세션
- 사용자 설정 / 목표 / 홈 대시보드
- 학습 모드 문제 생성 / 제출
- 문제 / 제출 / 분석 조회
- 마일스톤 리포트와 PDF 다운로드
- 복습 큐와 학습 연속성
- RQ job 상태 조회

대표 라우터:

- `app/api/routes/auth.py`
- `app/api/routes/me.py`
- `app/api/routes/public_learning.py`
- `app/api/routes/reports.py`
- `app/api/routes/submissions.py`
- `app/api/routes/platform_mode_jobs.py`
- `app/api/routes/advanced_analysis.py`

### `backend`

주요 역할:

- 일반 학습 엔진
- 문제 생성 프롬프트 / 후처리
- 언어 카탈로그와 alias 정규화
- JSONL 사용자 저장소
- 레거시 학습 리포팅
- Google/OpenAI 모델 호출 보조

이 계층은 완전히 제거된 것이 아니라, `platform_public_bridge` 를 통해 새 플랫폼 레이어에 연결되어 있습니다.

## 3. 핵심 브리지

`app/services/platform_public_bridge.py` 가 현재 구조의 중심입니다.

이 서비스는 다음을 동시에 수행합니다.

- `backend` 학습 엔진 호출
- 문제/제출/분석 결과를 MySQL 로 영속화
- 리포트/복습 큐/운영 이벤트 연결
- 고급 분석 모드와 일반 모드의 응답 정규화
- 레거시 이력과 플랫폼 이력 병합
- 프로필 통계를 런타임 이력과 DB 제출 기준으로 다시 계산

즉 “문제 생성 엔진” 은 여전히 일부 `backend` 쪽에 있고, “공개 계약과 영속화” 는 `app` 쪽이 담당합니다.

## 4. 프런트엔드 구조

프런트엔드는 React SPA가 아니라 정적 HTML + 공유 JS 구조입니다.

- 데스크톱: `frontend/desktop/*.html`
- 모바일: `frontend/mobile/*.html`
- 공용 스크립트: `frontend/shared/js/*`
- 공용 스타일: `frontend/shared/css/*`

렌더링 방식:

- `server_runtime/routes/pages.py` 가 User-Agent 기준으로 desktop/mobile variant를 선택합니다.
- 관리자 페이지는 `/admin.html` 단일 responsive 템플릿입니다.
- HTML 응답 시 정적 자산에 `?v=` 버전 쿼리가 주입됩니다.
- 사용자 페이지 응답에는 `Vary: User-Agent` 가 붙습니다.

현재 프로필 화면은 아래를 함께 담당합니다.

- 공통 언어/난이도 설정
- 오답 노트 진입
- 최신 학습 리포트 카드와 PDF 다운로드
- 고급 분석 3종 이력을 읽기 전용 workbench 로 재열기

## 5. 데이터 저장소

### MySQL

주요 플랫폼 영속화 저장소입니다.

대표 테이블:

- `users`
- `user_settings`
- `user_sessions`
- `problems`
- `submissions`
- `ai_analyses`
- `reports`
- `review_queue_items`
- `platform_ops_events`

### Redis

Redis 는 단순 분석 큐 외에도 여러 운영 용도로 사용합니다.

주요 용도:

- queued 제출 작업
- 문제 생성 후속 저장 작업
- RQ job 상태 저장
- 공용 이력 total 캐시
- 관리자 throttling backend

### JSONL

레거시 학습 엔진과의 호환 계층으로 아직 남아 있습니다.

- 기본 경로: `data/`, `data/users/`
- 관리 클래스: `backend.user_storage.UserStorageManager`

## 6. 큐와 스트리밍

### 큐

RQ 사용 시 큐는 두 갈래로 분리됩니다.

- `analysis`
  - queued 제출 분석, 고급 모드 제출 처리
- `problem-follow-up`
  - 문제 생성 후속 저장, 운영 이벤트 기록, 이력 반영

Compose 기준 워커 구조:

- `worker`
  - 기본적으로 `analysis` 큐 담당
- `worker-follow-up`
  - 기본적으로 `problem-follow-up` 큐 담당

`RQ_WORKER_QUEUES` 로 워커가 감시할 큐를 명시 override 할 수 있습니다.

### 문제 생성 스트리밍

현재 문제 생성 스트림은 대부분 아래 구조를 따릅니다.

- SSE `status` 이벤트 먼저 전송
- 최종 문제 본문은 `payload` 한 번으로 전달
- 후속 저장 단계는 `persisting` status 로 노출
- 마지막 `done` 이벤트에 `persisted` 플래그 포함

중요:

- 현재 구조는 “실제 본문 토큰 스트리밍” 이 아닙니다.
- `payload` 가 먼저 와도 스트림 성공은 `done.persisted=true` 까지 읽는 것을 기준으로 해야 합니다.
- `arrange` 는 의도적인 가짜 스트리밍 UI입니다.

## 7. 프로필, 이력, 리포트

### 프로필 / 홈

- `/platform/profile` 은 런타임 시도와 DB 제출을 합산한 누적 `totalAttempts`, `correctAnswers`, `accuracy` 를 제공합니다.
- `/platform/home` 은 streak, daily goal, review queue, 추천 모드, 주간 리포트 카드까지 묶어서 반환합니다.
- 홈 계산은 최근 이력 일부가 아니라 병합 이력 기준 누적 통계를 사용합니다.

### 이력

- `/platform/learning/history` 는 `history`, `total`, `hasMore`, `limit` 을 함께 주는 페이지형 응답입니다.
- 고급 분석 3종 이력은 문제 당시 파일 목록, 언어, 체크리스트, 제출 리포트, 점수까지 다시 보여줄 수 있도록 보강되어 있습니다.

### 리포트

- `/platform/report` 는 최신 milestone 리포트 상세를 반환합니다.
- `/platform/reports/latest` 는 프로필 카드용 축약 정보와 `pdfDownloadUrl` 을 반환합니다.
- PDF 생성기는 구버전 `repeatedWrongTypes/label` 형식과 현재 `topWrongTypes/type` 형식을 모두 읽어 차트를 그립니다.

## 8. 활성 학습 모드와 언어 카탈로그

현재 사용자에게 노출되는 활성 모드:

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

공용 언어 카탈로그:

- `python`, `javascript`, `typescript`, `c`, `java`, `cpp`, `csharp`, `go`, `rust`, `php`

허용 alias:

- `py`, `js`, `ts`, `c++`, `cs`, `c#`

내부 숙련도는 기존 `beginner/intermediate/advanced` 3단계가 아니라 `level1`~`level10` 10단계로 정규화됩니다. 기존 3단계 명칭은 호환용 입력으로만 유지됩니다.

## 9. 레거시 호환

주요 레거시 `/api` 경로는 `410 Gone` 으로 새 경로를 안내합니다.

예시:

- `/api/profile` -> `/platform/profile`
- `/api/languages` -> `/platform/languages`
- `/api/report` -> `/platform/report`
- `/api/learning/memory` -> `/platform/learning/memory`
- `/api/refactoring-choice/problem` -> `/platform/refactoring-choice/problem`
- `/api/auth/register` -> `/platform/auth/signup`

예외적으로 아직 살아 있는 레거시 조회 경로:

- `GET /api/tracks`

## 10. 운영상 유의점

- 프록시 뒤에서 운영할 때는 `CODE_PLATFORM_TRUSTED_PROXY_CIDRS` 를 명시하지 않으면 loopback 소스만 forwarded IP 로 인정합니다.
- sid 없는 쿠키 호환은 코드 기본값 기준 비활성입니다. 운영에서는 sunset 계획 없이 켜 두지 않는 편이 안전합니다.
- 커스텀 SSE 클라이언트를 붙일 경우 `payload` 수신 시점이 아니라 `done.persisted` 까지 소비해야 저장 실패를 놓치지 않습니다.
