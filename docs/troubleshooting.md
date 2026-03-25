# 문제 해결

## 1. 페이지 수정이 바로 안 보임

확인 포인트:

- 사용자 페이지는 desktop/mobile variant 로 나뉩니다.
- 정적 자산에는 `?v=` 버전 쿼리가 자동 주입됩니다.
- 사용자 페이지 응답에는 `Vary: User-Agent` 가 붙습니다.

확인 대상:

- `frontend/desktop/*.html`
- `frontend/mobile/*.html`
- `frontend/shared/js/*`
- `server_runtime/routes/pages.py`
- `server_runtime/template_renderer.py`

권장 확인:

```bash
python -m unittest tests.test_pages_template_variant -v
```

## 2. 관리자 페이지에서 종료 버튼이 비활성화됨

주요 원인:

- `CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN=false`
- `ADMIN_PANEL_KEY` 미설정 또는 오설정
- Docker socket 미마운트 상태에서 전체 스택 종료를 기대함

확인:

- `/api/admin/metrics` 응답의 shutdown capability 관련 필드
- 실행 옵션 `--with-docker-socket` / `--without-docker-socket`

## 3. 로컬 실행이 기동 직후 실패함

주요 원인:

- `DB_PASSWORD` 누락
- `JWT_SECRET` 누락 또는 32자 미만
- Alembic 미적용
- MySQL / Redis 미기동

권장 순서:

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

참고:

- 런처의 로컬 기본 worker 값은 `16`
- 디버깅과 재현에는 `--workers 1` 이 더 낫습니다.

## 4. queued 응답만 오고 피드백이 안 돌아옴

먼저 아래를 확인합니다.

- `ANALYSIS_QUEUE_MODE=rq`
- `redis` 실행 여부
- `worker` 실행 여부

queued 제출이 가능한 대표 모드:

- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

클라이언트는 `jobId` 로 아래 경로를 polling 해야 합니다.

```text
GET /platform/mode-jobs/{job_id}
```

## 5. 문제는 보였는데 이력, 리포트, 오답 노트에 반영되지 않음

문제 생성 후속 저장이 별도 큐/워커로 분리된 상태인지 확인합니다.

확인 포인트:

- `PROBLEM_FOLLOW_UP_QUEUE_MODE=rq`
- `worker-follow-up` 실행 여부
- `problem-follow-up` 큐 backlog 유무

관련 증상:

- 새로 생성한 문제가 `/platform/learning/history` 에 늦게 보임
- 프로필 누적 통계가 바로 증가하지 않음
- 복습 큐/리포트 반영이 지연됨

## 6. 문제 생성이 느리게 느껴짐

현재 구조는 “본문 토큰 스트리밍” 이 아닙니다.

실제 동작:

- SSE 상태 이벤트 먼저 전송
- 최종 문제 본문은 `payload` 한 번으로 전달
- 그 뒤 `persisting` 단계를 거쳐 `done.persisted=true` 로 마감

예외:

- `arrange` 는 의도적인 가짜 스트리밍 UI입니다.

즉 “상태는 빨리 오는데 본문 시작이 늦다” 는 느낌은 현재 구조상 정상일 수 있습니다.

## 7. Google OAuth 시작 또는 callback 이 실패함

확인 포인트:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- 필요 시 `GOOGLE_OAUTH_REDIRECT_URI`

프록시 뒤 운영이면 아래 헤더 전달도 맞아야 합니다.

- `X-Forwarded-Proto`
- `X-Forwarded-Host`
- `X-Forwarded-Port`

또한 프록시 IP 신뢰 범위를 아래 값으로 명시해야 합니다.

- `CODE_PLATFORM_TRUSTED_PROXY_CIDRS`

외부/운영 callback URI 는 HTTPS 만 허용하는 것이 안전합니다.

## 8. 기존 `/api/...` 호출이 갑자기 실패함

학습 관련 레거시 `/api` 경로 대부분은 현재 기준 경로가 아닙니다.

대표 동작:

- `410 Gone`
- 응답 본문에 새 `/platform/...` 경로 포함

예시:

- `/api/report` -> `/platform/report`
- `/api/auth/register` -> `/platform/auth/signup`
- `/api/auth/guest/start` -> `/platform/auth/guest`
- `/api/learning/memory` -> `/platform/learning/memory`

예외적으로 `GET /api/tracks` 는 아직 레거시 조회 경로로 남아 있습니다.

## 9. 저장한 언어가 거부되거나 다시 기본값으로 돌아감

지원 언어는 canonical ID 기준으로만 저장됩니다.

canonical ID:

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

지원하지 않는 값은 `400` 으로 거부되거나, 기존에 저장된 잘못된 값이라면 조회 시 `python` 같은 유효값으로 복구될 수 있습니다.

## 10. 최신 리포트 카드가 비어 있음

프로필의 최신 리포트 카드는 milestone 리포트가 저장돼 있어야 채워집니다.

확인 순서:

- `POST /platform/reports/milestone` 호출 성공 여부
- `GET /platform/reports/latest` 응답의 `available` 값
- PDF 생성 시 `GET /platform/reports/{report_id}/pdf` 응답 여부

Playwright smoke 재실행:

```bash
set CI=1
set ENABLE_HTTPS=0
npx playwright test tests/e2e/smoke.spec.mjs
```
