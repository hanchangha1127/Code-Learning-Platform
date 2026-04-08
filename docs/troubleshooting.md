# 트러블슈팅

## 1. 서버가 바로 뜨지 않음

확인 순서:

1. `.env`에 `DB_PASSWORD` 또는 `DB_PASSWORD_FILE`이 있는지 확인
2. `.env`에 `JWT_SECRET` 또는 `JWT_SECRET_FILE`이 있는지 확인
3. `alembic upgrade head` 실행
4. MySQL / Redis 상태 확인
5. `python run_server.py --local --workers 1`로 최소 구성 재현

자주 보이는 원인:

- `DB_PASSWORD`가 비어 있음
- `JWT_SECRET` 길이가 32자 미만
- `.env`에는 빈 값만 있고 실제 비밀 파일 경로가 잘못됨

## 2. 도커는 떴는데 도메인 접속이 안 됨

확인 항목:

- `ENABLE_HTTPS=true`
- 인증서 파일 존재 여부
- `80`, `443` 포트포워딩
- 방화벽 인바운드 허용
- `https://<도메인>/health` 응답 여부

확인 명령:

```bash
curl.exe -k --resolve hhtj.site:443:127.0.0.1 -I https://hhtj.site/health
curl.exe --resolve hhtj.site:80:127.0.0.1 -I http://hhtj.site/health
```

## 3. `/api/*`가 410을 반환함

정상 동작일 수 있습니다. 현재 canonical 경로는 `/platform/*`이고, 대부분의 제거된 옛 학습 경로는 `410 Gone`으로 새 경로를 안내합니다.

## 4. 페이지가 desktop/mobile 기준과 다르게 보임

확인 파일:

- `server/features/runtime_ui/pages.py`
- `server/features/runtime_ui/template_renderer.py`
- `server/features/runtime_ui/user_agent.py`

빠른 검증:

```bash
python -m unittest discover -s tests/server/runtime -t . -p "test_pages_template_variant.py" -v
```

## 5. queued submit만 되고 결과가 돌아오지 않음

확인 항목:

- `ANALYSIS_QUEUE_MODE=rq`
- Redis 연결 가능 여부
- `python -m server.worker` 또는 worker 컨테이너 실행 여부
- `RQ_WORKER_QUEUES` 설정

job 상태 확인:

```text
GET /platform/mode-jobs/{job_id}
```

## 6. 문제 생성 후 늦게 에러가 나면서 화면에서 문제가 사라짐

최근 프런트는 `payload`를 받은 뒤 늦은 stream 오류가 와도 이미 받은 문제를 유지하도록 수정되어 있습니다.

그래도 같은 현상이 보이면 먼저 확인할 것:

- 브라우저 강력 새로고침 `Ctrl+F5`
- `frontend/assets/js/core/problem_stream_client.js`
- `frontend/assets/js/widgets/advanced_analysis_shell.js`
- `tests/e2e/inline_streaming.spec.mjs`

## 7. 고급 분석 3모드가 생성 후 500 에러가 남

`single-file-analysis`, `multi-file-analysis`, `fullstack-analysis`는 공통 생성 경로를 공유합니다. 하나가 깨지면 셋이 같이 영향받을 수 있습니다.

우선 확인할 파일:

- `server/features/learning/api_advanced_analysis.py`
- `server/features/learning/service.py`
- `server/features/learning/generator.py`
- `server/features/learning/generator_normalize.py`
- `server/features/learning/history.py`

빠른 검증:

```bash
python -m unittest tests.server.learning.test_advanced_analysis_runtime tests.server.learning.test_problem_generator -v
cmd /c npm run test:e2e -- tests/e2e/inline_streaming.spec.mjs
```

## 8. AI 피드백이 생성되지 않음

확인 항목:

- 제출 API가 500 없이 끝나는지
- `server/features/learning/history.py`의 persistence helper가 정상인지
- worker / follow-up queue가 막히지 않았는지

우선 확인할 파일:

- `server/features/learning/history.py`
- `server/features/learning/reporting.py`
- `server/features/learning/streaming.py`

## 9. 프로필에서 공통 학습 설정이 비어 있음

프로필은 로컬 저장값만 보지 않고 `/platform/me/settings`를 기준으로 렌더링해야 합니다.

확인 파일:

- `frontend/assets/js/pages/profile.js`
- `frontend/pages/desktop/profile.html`
- `frontend/pages/mobile/profile.html`

캐시된 JS 때문에 예전 화면이 보일 수 있으니 `Ctrl+F5`를 먼저 해보는 것이 좋습니다.

## 10. Google OAuth 시작 또는 콜백이 실패함

확인 항목:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS`
- 프록시의 forwarded header 전달 상태

대표 원인:

- 실제 도메인 callback URL이 허용 목록에 없음
- `X-Forwarded-Proto` / `X-Forwarded-Host`가 올바르게 전달되지 않음

## 11. 관리자 종료 버튼이 비활성화됨

주요 원인:

- `CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN=false`
- `ADMIN_PANEL_KEY` 미설정
- Docker socket 없이 전체 stack 종료를 기대하는 경우

확인 API:

```text
GET /api/admin/metrics
```
