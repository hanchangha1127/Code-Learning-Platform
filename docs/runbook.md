# 운영 런북

## 1. 기본 개발 스택 기동

```bash
python run_server.py
```

기본 동작:

- `docker compose up -d --build` 형태로 백그라운드 실행
- `docker-compose.yml` + `docker-compose.dev.yml` + `docker-compose.docker-socket.yml` 사용
- `mysql`, `redis`, `api`, `worker` readiness 대기
- `/admin.html` 자동 오픈
- Docker socket 기본 활성화

유용한 옵션:

- 포그라운드 실행

```bash
python run_server.py --foreground
```

- 관리자 페이지 자동 오픈 끄기

```bash
python run_server.py --no-open-admin
```

- Docker socket 비활성화

```bash
python run_server.py --without-docker-socket
```

```env
ENABLE_HTTPS=true
TLS_CERTS_DIR=certs
HTTPS_BIND_PORT=8443
HTTPS_PUBLIC_PORT=443
HTTP_REDIRECT_PORT=8000
```

HTTPS Compose를 켜면 `80 -> 8000`은 redirect, `443 -> 8443`은 TLS 앱 서버로 노출됩니다.

## 2. 운영형 스택 기동

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

운영형 특징:

- `docker-compose.yml` + `docker-compose.ops.yml` 사용
- `api`, `worker`는 read-only root filesystem + `tmpfs`
- 개발용 소스 바인드 마운트 제거

운영형에서 관리자 종료 기능을 끄려면:

```bash
python run_server.py --compose-mode ops --without-docker-socket
```

## 3. 로컬 모드

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

```bash
ENABLE_HTTPS=true TLS_CERTS_DIR=certs python run_server.py --local --host 127.0.0.1 --workers 1
```

로컬 모드 특징:

- 컨테이너를 띄우지 않고 uvicorn만 실행
- MySQL/Redis는 별도 준비 필요
- 컨테이너와 달리 Alembic을 수동 적용해야 함
- `.env.example` 기준 기본 큐 모드는 `inline`

## 4. 컨테이너 기동 시 자동 처리

컨테이너의 `entrypoint.sh`는 다음 순서로 동작합니다.

1. MySQL 연결 대기
2. `alembic upgrade head`
3. `python -m server_runtime.runtime_server`

즉 Compose 모드에서는 마이그레이션이 자동 적용됩니다.

## 5. 큐 운영 기준

### Compose 모드

- `api` 컨테이너는 작업을 enqueue
- `worker` 컨테이너가 Redis `rq` 큐를 소비
- `ANALYSIS_QUEUE_MODE=rq`가 강제됨
- `auditor`, `refactoring-choice`, `code-blame`, `single-file-analysis`, `multi-file-analysis`, `fullstack-analysis` 제출은 queued 응답을 반환할 수 있음
- 상태 조회는 `GET /platform/mode-jobs/{job_id}` 사용

### Local 모드

- 기본값은 `inline`
- 환경변수로 `rq`를 켤 수 있지만, 이 경우 Redis와 worker 구성이 별도로 필요
- 문제 생성은 대부분 SSE 상태 이벤트 이후 최종 `payload` 1회 전달 구조이며, `arrange`는 클라이언트 가짜 스트리밍이 정상 동작임

## 6. 관리자 패널

- 주소: `/admin.html`
- 인증: `X-Admin-Key` 또는 `X-Admin-Key-B64`
- 메트릭: `GET /api/admin/metrics`
- 종료 요청: `POST /api/admin/shutdown`

관리자 종료 기능이 활성화되려면 다음 조건이 모두 필요합니다.

- API가 Docker 안에서 실행 중일 것
- `/var/run/docker.sock`가 mount 되어 있을 것
- Compose 스택 대상 컨테이너를 정상적으로 식별할 수 있을 것

잘못된 관리자 키는 반복 실패 시 일시적으로 차단됩니다.

## 7. 종료 명령

### 개발용, Docker socket 미사용

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans
```

### 개발용, Docker socket 사용

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

### 운영형, Docker socket 미사용

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml down --remove-orphans
```

### 운영형, Docker socket 사용

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.docker-socket.yml down --remove-orphans
```

## 8. 운영 체크리스트

- 강한 `JWT_SECRET` 사용
- 강한 `ADMIN_PANEL_KEY` 사용
- 필요한 경우에만 Docker socket 활성화
- Google OAuth 사용 시 허용 redirect URI와 프록시 헤더 검토
- 배포 전 최소한 다음 테스트 확인

```bash
python -m unittest tests.test_mode_api_platform_parity tests.test_auth_unification tests.test_pages_template_variant tests.test_launcher_defaults -v
```
