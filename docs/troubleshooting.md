# 트러블슈팅

## 1. 페이지 변경이 바로 반영되지 않음

- HTML은 `server_runtime.template_renderer`가 `/static/...` 자산에 `?v=`를 자동 주입합니다.
- 사용자 페이지는 `frontend/desktop/*.html`, `frontend/mobile/*.html` variant를 사용합니다.
- 관리자 페이지는 `frontend/app/admin.html` responsive 템플릿을 사용합니다.
- 브라우저 강력 새로고침 후에도 같다면 응답 HTML의 `X-Template-Variant`와 `?v=` 주입 여부를 확인합니다.

확인 지점:

- `server_runtime/routes/pages.py`
- `server_runtime/template_renderer.py`
- `python -m unittest tests.test_pages_template_variant -v`

## 2. 관리자 패널에서 종료 버튼이 비활성화됨

다음 중 하나일 가능성이 큽니다.

- API 컨테이너에 Docker socket이 mount 되어 있지 않음
- API가 Docker 밖에서 실행 중임
- Compose 스택 대상 컨테이너를 완전히 식별하지 못함

재기동 예시:

```bash
python run_server.py --compose-mode dev --with-docker-socket
```

또는:

```bash
python run_server.py --compose-mode ops --with-docker-socket
```

## 3. `run_server.py` 실행 후 일부 서비스만 올라옴

런처는 `mysql`, `redis`, `api`, `worker` readiness를 기다립니다. 일부 서비스가 준비되지 않으면 실패 로그를 출력합니다.

직접 확인:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs api worker mysql redis
```

Docker socket override를 함께 썼다면 동일하게 `docker-compose.docker-socket.yml`도 포함합니다.

## 4. 로컬 모드에서 API는 뜨는데 분석/큐 동작이 다름

로컬 `--local` 모드와 Compose 모드는 큐 동작이 다를 수 있습니다.

- Compose
  - `ANALYSIS_QUEUE_MODE=rq`
  - `worker` 컨테이너가 별도 실행됨
- Local
  - `.env.example` 기준 기본값은 `inline`

`rq` 모드 상태 조회 경로:

- `GET /platform/mode-jobs/{job_id}`

이 경로는 queue mode가 `rq`일 때만 의미가 있습니다.

## 5. 고급 모드 제출이 queued 응답만 오고 완료가 안 됨

다음 조건을 확인합니다.

- Redis가 정상 실행 중인지
- `worker`가 떠 있는지
- `ANALYSIS_QUEUE_MODE=rq`인지

확인 예시:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs worker redis
```

대상 모드:

- `auditor`
- `refactoring-choice`
- `code-blame`
- `single-file-analysis`
- `multi-file-analysis`
- `fullstack-analysis`

참고:

- queued 응답은 최종 피드백이 아니므로 `jobId` 완료 polling 뒤 `result.feedback`를 렌더링해야 합니다.
- 대부분의 문제 생성 모드는 SSE 상태 이벤트를 먼저 보내고, 본문은 생성 완료 뒤 최종 `payload` 1회로 도착합니다.
- `arrange`는 의도적인 가짜 스트리밍(UI 애니메이션)이라 서버 본문 스트리밍이 없어도 정상입니다.

## 6. Google OAuth 시작 시 redirect URI 오류가 남

주로 계산된 callback URI가 허용 목록과 다를 때 발생합니다.

확인 항목:

- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- 필요 시 `GOOGLE_OAUTH_REDIRECT_URI`
- 프록시 헤더
  - `X-Forwarded-Proto`
  - `X-Forwarded-Host`
  - `X-Forwarded-Port`

Google Cloud Console의 승인된 redirect URI와 서버 설정 값이 정확히 일치해야 합니다.

## 7. 로컬 모드에서 인증/플랫폼 API가 시작되지 않음

`app/core/config.py`는 시작 시 다음 값을 강하게 검증합니다.

- `DB_PASSWORD`
- `JWT_SECRET`

또한 로컬 모드에서는 마이그레이션을 수동으로 적용해야 합니다.

```bash
alembic upgrade head
python run_server.py --local --host 127.0.0.1 --port 8000 --workers 1
```

## 8. 학습 페이지는 열리는데 데이터가 비어 보임

페이지 템플릿 문제와 API 문제를 분리해서 봐야 합니다.

템플릿 확인:

- `frontend/desktop/*.html`
- `frontend/mobile/*.html`
- `frontend/shared/js/*.js`

API 계약 확인:

```bash
python -m unittest tests.test_mode_api_platform_parity tests.test_auth_unification tests.test_pages_template_variant -v
```

레거시 `/api` 학습 경로는 현재 다수 경로에서 `410 Gone`으로 `/platform` 새 경로를 안내합니다. 프런트가 아직 `/api/...`를 직접 호출하는지 같이 확인합니다.
