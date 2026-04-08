# 운영 가이드

## 1. 개발 스택 실행

기본 개발 스택:

```bash
python run_server.py
```

자주 쓰는 옵션:

```bash
python run_server.py --foreground
python run_server.py --no-open-admin
python run_server.py --without-docker-socket
```

## 2. 운영용 compose 실행

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

Docker socket 없이 올리려면:

```bash
python run_server.py --compose-mode ops --without-docker-socket
```

## 3. 로컬 uvicorn 직접 실행

HTTP:

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

HTTPS:

```bash
set ENABLE_HTTPS=true
python run_server.py --local --host 127.0.0.1 --workers 1
```

## 4. 도메인 HTTPS 운영 체크리스트

확인 항목:

- `ENABLE_HTTPS=true`
- `SSL_CERTFILE` / `SSL_KEYFILE` 또는 `TLS_CERTS_DIR` 설정
- `HTTPS_PUBLIC_PORT=443`
- 프록시나 포트포워딩에서 `80`과 `443`이 실제 컨테이너까지 전달되는지 확인
- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`에 실제 도메인 callback 포함

빠른 확인:

```bash
curl.exe -k --resolve hhtj.site:443:127.0.0.1 -I https://hhtj.site/health
curl.exe --resolve hhtj.site:80:127.0.0.1 -I http://hhtj.site/health
```

정상이라면 HTTP는 HTTPS로 리디렉트되고, HTTPS health는 `200 OK`가 반환됩니다.

## 5. 관리자 기능

관리자 페이지:

- `/admin.html`

관리자 API:

- `GET /api/admin/metrics`
- `POST /api/admin/shutdown`

인증 헤더:

- `X-Admin-Key`
- `X-Admin-Key-B64`

종료 기능을 실제로 열려면 다음이 필요합니다.

- `CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN=true`
- `ADMIN_PANEL_KEY`
- 전체 스택 종료까지 원하면 Docker socket mount

## 6. queue 운영

개발 기본값:

- `ANALYSIS_QUEUE_MODE=inline`
- `PROBLEM_FOLLOW_UP_QUEUE_MODE=inline`

compose 권장값:

- `ANALYSIS_QUEUE_MODE=rq`
- `PROBLEM_FOLLOW_UP_QUEUE_MODE=rq`
- `redis`
- `worker`
- `worker-follow-up`

queued 제출이 가능한 대표 모드:

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

## 7. 스트리밍 운영 메모

문제 생성 SSE는 보통 아래 phase를 거칩니다.

- `queued`
- `generating`
- `rendering`
- `persisting`
- `done`

운영 시 주의:

- 브라우저는 `payload`를 받는 순간 이미 문제를 렌더링할 수 있습니다.
- 후속 persistence나 follow-up 단계의 늦은 오류가 있더라도, 최신 프런트는 이미 받은 문제를 유지하도록 되어 있습니다.
- 고급 분석 3모드는 공통 생성 경로를 쓰므로, 하나가 깨지면 셋이 같이 깨질 가능성이 큽니다.

## 8. 프로필 / 리포트 메모

- `/platform/home`은 대시보드 요약과 추천 문제를 제공합니다.
- `/platform/me/settings`는 공통 학습 설정의 실제 저장 위치입니다.
- `/platform/me/goal`은 목표 설정 API입니다.
- 최신 리포트 메타데이터는 `GET /platform/reports/latest`
- PDF 다운로드는 `/platform/reports/{report_id}/pdf`

## 9. 종료 명령

개발 스택 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans
```

개발 스택 + Docker socket override 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

운영 스택 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml down --remove-orphans
```

운영 스택 + Docker socket override 종료:

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

## 10. 배포 전 확인

서버 테스트:

```bash
python -m unittest discover -s tests/server -t . -v
```

E2E:

```bash
cmd /c npm run test:e2e -- tests/e2e/smoke.spec.mjs tests/e2e/inline_streaming.spec.mjs
```
