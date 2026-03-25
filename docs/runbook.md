# 운영 가이드

## 1. 개발 스택 실행

기본 개발 스택:

```bash
python run_server.py
```

이 명령은 보통 아래를 수행합니다.

- 개발용 Compose 스택 기동
- 대상 서비스 readiness 확인: `mysql`, `redis`, `api`, `worker`, `worker-follow-up`
- `/admin.html` 자동 오픈

자주 쓰는 옵션:

```bash
python run_server.py --foreground
python run_server.py --no-open-admin
python run_server.py --without-docker-socket
```

## 2. 운영형 Compose 실행

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

특징:

- `docker-compose.ops.yml` 사용
- `api`, `worker`, `worker-follow-up` 은 read-only root filesystem + `tmpfs`
- 개발용 바인드 마운트가 빠짐

보안상 Docker socket 이 꼭 필요하지 않으면 아래 형태를 우선 고려합니다.

```bash
python run_server.py --compose-mode ops --without-docker-socket
```

## 3. 로컬 서버 실행

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

HTTPS 직접 실행:

```bash
set ENABLE_HTTPS=true
python run_server.py --local --host 127.0.0.1 --workers 1
```

로컬 모드 전제:

- MySQL / Redis 별도 준비
- `.env` 필수값 준비
- Alembic 수동 적용
- 런처의 로컬 기본 worker 값은 `16`
- 문서 예시는 개발 재현을 위해 `--workers 1`

## 4. 관리자 기능

관리자 페이지:

- `/admin.html`

관리자 API:

- `GET /api/admin/metrics`
- `POST /api/admin/shutdown`

인증 헤더:

- `X-Admin-Key`
- `X-Admin-Key-B64`

종료 기능이 실제로 유효하려면 다음이 맞아야 합니다.

- `CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN=true`
- 유효한 `ADMIN_PANEL_KEY`
- Docker 기반 스택 종료를 원하면 Docker socket mount 활성화

프록시 뒤 운영 시에는 `CODE_PLATFORM_TRUSTED_PROXY_CIDRS` 를 맞춰야 관리자 throttling 식별자가 올바르게 동작합니다.

## 5. 큐 운영 기준

기본 개발 `.env.example`:

- `ANALYSIS_QUEUE_MODE=inline`
- `PROBLEM_FOLLOW_UP_QUEUE_MODE=inline`

Compose 일반 패턴:

- `ANALYSIS_QUEUE_MODE=rq`
- `PROBLEM_FOLLOW_UP_QUEUE_MODE=rq`
- `redis` 실행
- `worker` 실행
- `worker-follow-up` 실행

큐 역할:

- `analysis`
  - queued 제출 분석, 고급 모드 제출 처리
- `problem-follow-up`
  - 문제 생성 후속 저장, 이력/리포트/운영 이벤트 반영

queued 제출이 가능한 모드:

- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

job 상태 조회:

```text
GET /platform/mode-jobs/{job_id}
```

워커를 수동으로 커스터마이즈할 때는 `RQ_WORKER_QUEUES` 로 감시 큐를 명시할 수 있습니다.

## 6. 스트리밍 운영 메모

문제 생성 SSE는 보통 아래 phase를 거칩니다.

- `queued`
- `generating`
- `rendering`
- `persisting`
- `done`

운영 관점 주의:

- 현재는 본문 토큰 스트리밍이 아니라 최종 `payload` 1회 전달 구조입니다.
- 성공 여부는 `payload` 수신 자체가 아니라 마지막 `done.persisted=true` 로 판단해야 합니다.
- `arrange` 는 예외적으로 가짜 스트리밍 UI입니다.

## 7. 프로필 / 리포트 운영 메모

- `/platform/profile` 과 `/platform/home` 의 통계는 런타임 이력과 DB 제출 이력을 병합해 계산합니다.
- 프로필 화면은 최신 리포트 카드와 `GET /platform/reports/latest` 기반 PDF 다운로드를 제공합니다.
- 고급 분석 오답 기록은 읽기 전용 workbench 로 다시 열 수 있습니다.
- 구버전 리포트의 `repeatedWrongTypes` 형식도 최신 PDF 생성기에서 계속 지원합니다.

## 8. HTTPS 운영 메모

관련 값:

- `ENABLE_HTTPS`
- `TLS_CERTS_DIR`
- `SSL_CERTFILE`
- `SSL_KEYFILE`
- `HTTPS_BIND_PORT`
- `HTTPS_PUBLIC_PORT`
- `HTTP_REDIRECT_PORT`

주의:

- 직접 HTTPS 모드에서는 앱 서버 외에 HTTP redirect 서버도 같이 뜹니다.
- cert/key 를 직접 지정하지 않으면 `certs/fullchain.pem`, `certs/privkey.pem` 을 찾습니다.

## 9. 종료 명령

개발 스택 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans
```

개발 스택 + Docker socket override 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

운영형 스택 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml down --remove-orphans
```

운영형 스택 + Docker socket override 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

## 10. 배포 전 권장 확인

Python 테스트:

```bash
python -m unittest discover -s tests -v
```

Playwright smoke:

```bash
set CI=1
set ENABLE_HTTPS=0
npx playwright test tests/e2e/smoke.spec.mjs
```

2026-03-21 최신 확인 결과:

- Python `269/269`
- Playwright smoke `54/54`
