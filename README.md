# 코드 학습 플랫폼

FastAPI 기반 학습 플랫폼입니다. 현재 서버 코드는 `server/` 패키지 하나를 기준으로 정리되어 있고, 루트 실행 진입점은 `run_server.py`입니다.

## 구조

```text
server/      # 백엔드와 런타임
frontend/    # 정적 HTML/CSS/JS 자산
tests/       # 서버 테스트와 E2E
docs/        # 구조/운영 문서
alembic/     # DB 마이그레이션
```

## 서버 패키지

```text
server/
  app.py               # FastAPI 앱 조립
  bootstrap.py         # settings, storage, singleton 초기화
  dependencies.py      # 공용 FastAPI dependency
  launcher.py          # 로컬/도커 실행 제어
  runtime_server.py    # uvicorn 실행기
  worker.py            # RQ worker 실행기
  core/                # config, runtime_config, security, proxy helper
  db/                  # SQLAlchemy models, session, base
  infra/               # AI client, metrics, user storage/service
  schemas/             # Pydantic schema
  features/
    auth/              # 인증 API, legacy auth API, helper/dependency
    account/           # /platform/me, 설정, 학습 목표
    learning/          # 학습 모드, 생성기, streaming, history, tiering
    reports/           # 리포트 조회와 PDF
    jobs/              # mode job queue/status
    runtime_ui/        # pages, health, admin
```

## 프런트 자산

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

## 현재 공개 학습 모드

- `analysis`
- `codeblock`
- `arrange`
- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

`codecalc` 공개 UI/API는 제거되었습니다. 다만 과거 `code-calc` 학습 이력과 리포트 호환 해석은 일부 유지합니다.

## 실행

### 로컬 실행

```bash
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

HTTPS 로컬 실행:

```bash
set ENABLE_HTTPS=true
python run_server.py --local --host 127.0.0.1 --workers 1
```

### 도커 실행

개발용 compose:

```bash
python run_server.py --compose-mode dev --with-docker-socket
```

운영용 compose:

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

직접 compose를 쓰려면:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.docker-socket.yml up -d --build
```

## 필수 환경 변수

- `DB_PASSWORD` 또는 `DB_PASSWORD_FILE`
- `JWT_SECRET` 또는 `JWT_SECRET_FILE`

도메인 HTTPS를 쓸 경우 추가로 확인할 항목:

- `ENABLE_HTTPS`
- `HTTPS_BIND_PORT`
- `HTTPS_PUBLIC_PORT`
- `HTTP_REDIRECT_PORT`
- `TLS_CERTS_DIR` 또는 `SSL_CERTFILE` / `SSL_KEYFILE`

자세한 목록은 [docs/environment.md](docs/environment.md)를 참고하면 됩니다.

## 테스트

서버 테스트:

```bash
python -m unittest discover -s tests/server -t . -v
```

E2E:

```bash
cmd /c npm run test:e2e -- tests/e2e/smoke.spec.mjs tests/e2e/inline_streaming.spec.mjs
```

## 문서

- [아키텍처](docs/architecture.md)
- [환경 변수](docs/environment.md)
- [운영 가이드](docs/runbook.md)
- [트러블슈팅](docs/troubleshooting.md)
