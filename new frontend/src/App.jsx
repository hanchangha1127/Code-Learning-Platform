import { useCallback, useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";
import { BrandIcon } from "./components/SvgIcon.jsx";
import {
  languageTitle,
  normalizeLanguageId,
  normalizeProfileSettings,
  normalizeRuntimeDifficulty,
  persistLearningSettings,
  readStoredRuntimeSettings,
} from "./lib/learningSettings.js";

const TOKEN_KEY = "code-learning-token";
const DISPLAY_NAME_KEY = "code-learning-display-name";
const SESSION_MARKER = "cookie-session";

const MODE_LABELS = {
  analysis: "코드 분석",
  "code-block": "코드 블록",
  "code-arrange": "코드 배치",
  auditor: "감사관 모드",
  "refactoring-choice": "최적안 선택",
  "code-blame": "범인 찾기",
  "single-file-analysis": "단일 파일 분석",
  "multi-file-analysis": "멀티 파일 분석",
  "fullstack-analysis": "풀스택 분석",
};

const MODE_LABEL_ALIASES = {
  "코드 해석": "코드 분석",
  "순서 맞추기": "코드 배치",
  "코드 점검": "감사관 모드",
  "리팩터링 방식 선택": "최적안 선택",
  "최적의 선택": "최적안 선택",
  "원인 커밋 찾기": "범인 찾기",
};

const OUTCOME_LABELS = {
  passed: "정답",
  correct: "정답",
  success: "정답",
  failed: "오답",
  fail: "오답",
  incorrect: "오답",
  wrong: "오답",
  error: "오류",
};

const ADVANCED_CONFIG = {
  "/single-file-analysis.html": {
    mode: "single-file",
    title: "단일 파일 분석",
    problemPath: "/platform/single-file-analysis/problem",
    submitPath: "/platform/single-file-analysis/submit",
  },
  "/multi-file-analysis.html": {
    mode: "multi-file",
    title: "멀티 파일 분석",
    problemPath: "/platform/multi-file-analysis/problem",
    submitPath: "/platform/multi-file-analysis/submit",
  },
  "/fullstack-analysis.html": {
    mode: "fullstack",
    title: "풀스택 분석",
    problemPath: "/platform/fullstack-analysis/problem",
    submitPath: "/platform/fullstack-analysis/submit",
  },
};

function normalizePath() {
  const path = window.location.pathname || "/";
  if (path === "/" || path === "/app.html") return "/dashboard.html";
  return path;
}

function getToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

function isSessionMarker(token) {
  return String(token || "").trim() === SESSION_MARKER;
}

function authHeaders() {
  const token = getToken();
  if (!token || isSessionMarker(token)) return {};
  return { Authorization: `Bearer ${token}` };
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function errorMessageFromPayload(data, fallback) {
  const detail = data?.detail ?? data?.message;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .filter(Boolean)
      .join(" ");
  }
  if (typeof detail === "object") return detail.msg || detail.message || JSON.stringify(detail);
  return String(detail);
}

function displayModeLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "학습";
  return MODE_LABELS[text] || MODE_LABEL_ALIASES[text] || text;
}

function reportTitle(report) {
  return report?.title || report?.goal || report?.reportBrief?.title || "최근 리포트";
}

function reportSummary(report) {
  return report?.summary || report?.solutionSummary || report?.reportBrief?.summary || report?.blockingMessage || "";
}

function reportCreatedAt(report) {
  return report?.createdAt || report?.created_at || "";
}

function reportDownloadUrl(report) {
  if (report?.pdfDownloadUrl) return report.pdfDownloadUrl;
  const id = report?.reportId || report?.id;
  return id ? `/platform/reports/${id}/pdf` : "";
}

function isWrongHistoryItem(item) {
  const correct = item?.correct ?? item?.isCorrect ?? item?.feedback?.correct;
  if (correct === false) return true;
  const status = String(item?.outcome || item?.result || item?.status || item?.verdict || "").toLowerCase();
  if (["failed", "fail", "incorrect", "wrong", "오답"].includes(status)) return true;
  const score = Number(item?.score ?? item?.feedback?.score);
  return Number.isFinite(score) && score < 60;
}

function historyItemTitle(item, index) {
  return item?.title || item?.problemTitle || item?.problem_title || item?.prompt || `오답 기록 ${index + 1}`;
}

function historyItemSummary(item) {
  return item?.feedback?.summary || item?.summary || item?.resultSummary || item?.result_summary || item?.explanation || "";
}

async function apiRequest(path, { method = "GET", body, auth = true, headers = {} } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(auth ? authHeaders() : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(errorMessageFromPayload(data, `요청에 실패했습니다. (${response.status})`));
  }
  return data;
}

function saveSession(payload) {
  const token = payload?.accessToken || payload?.access_token || payload?.token || SESSION_MARKER;
  window.localStorage.setItem(TOKEN_KEY, token || SESSION_MARKER);
  const displayName = payload?.displayName || payload?.display_name || payload?.username || payload?.email || "";
  if (displayName) window.localStorage.setItem(DISPLAY_NAME_KEY, displayName);
}

async function clearSession() {
  try {
    await fetch("/platform/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch {
    // Ignore logout network cleanup.
  }
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(DISPLAY_NAME_KEY);
}

async function verifySession() {
  try {
    await apiRequest("/platform/profile");
    const existingToken = getToken();
    if (!existingToken || isSessionMarker(existingToken)) {
      window.localStorage.setItem(TOKEN_KEY, SESSION_MARKER);
    }
    return true;
  } catch {
    return false;
  }
}

function useSessionGuard(enabled = true) {
  const [ready, setReady] = useState(!enabled);
  useEffect(() => {
    let active = true;
    if (!enabled) return undefined;
    verifySession().then((ok) => {
      if (!active) return;
      if (!ok) {
        clearSession();
        window.location.replace("/index.html");
        return;
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, [enabled]);
  return ready;
}

function useLearningSettings() {
  const storedSettings = readStoredRuntimeSettings();
  const [language, setLanguage] = useState(storedSettings.language);
  const [difficulty, setDifficulty] = useState(storedSettings.difficulty);

  useEffect(() => {
    let active = true;
    apiRequest("/platform/me/settings")
      .then((payload) => {
        if (!active) return;
        const profileSettings = normalizeProfileSettings(payload);
        setLanguage(profileSettings.preferred_language);
        setDifficulty(normalizeRuntimeDifficulty(profileSettings.preferred_difficulty, "intermediate"));
        persistLearningSettings(profileSettings);
      })
      .catch(() => {
        // Keep the locally stored settings when the profile API is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  return { language, difficulty };
}

function variantFromUserAgent() {
  const ua = window.navigator.userAgent || "";
  return /iPhone|Android.+Mobile|IEMobile|BlackBerry|Opera Mini/i.test(ua) ? "mobile" : "desktop";
}

function AppShell({ children, title = "코드 학습", subtitle = "Code Reading Lab", active = "", actions = null }) {
  return (
    <section className="app dashboard-shell route-page">
      <header className="app-header page-header dashboard-topbar">
        <a className="brand-lockup" href="/dashboard.html">
          <span className="brand-mark">
            <BrandIcon />
          </span>
          <div>
            <p className="eyebrow">{subtitle}</p>
            <h1>{title}</h1>
          </div>
        </a>
        <nav className="header-actions" aria-label="주요 이동">
          <a className={active === "dashboard" ? "primary" : "ghost"} href="/dashboard.html">대시보드</a>
          <a className={active === "profile" ? "primary" : "ghost"} href="/profile.html">프로필</a>
          {actions}
          <button
            type="button"
            className="ghost"
            onClick={async () => {
              await clearSession();
              window.location.replace("/index.html");
            }}
          >
            로그아웃
          </button>
        </nav>
      </header>
      {children}
    </section>
  );
}

function LoadingScreen() {
  return <main className="dashboard-main"><section className="card dashboard-panel">세션을 확인하는 중입니다...</section></main>;
}

function LoginPage() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    verifySession().then((ok) => {
      if (ok) window.location.replace("/dashboard.html");
    });
  }, []);

  async function startGuest(event) {
    event.preventDefault();
    setLoading(true);
    setMessage("게스트 세션을 시작하는 중입니다...");
    try {
      const payload = await apiRequest("/platform/auth/guest", { method: "POST", auth: false });
      saveSession(payload);
      window.location.href = "/dashboard.html";
    } catch (error) {
      setMessage(error.message || "게스트 로그인에 실패했습니다.");
      setLoading(false);
    }
  }

  return (
    <section className="login-shell">
      <main className="card login-card">
        <div className="brand-lockup">
          <span className="brand-mark">
            <BrandIcon />
          </span>
          <div>
            <p className="eyebrow">Code Reading Lab</p>
            <h1>코드 학습 플랫폼</h1>
          </div>
        </div>
        <p className="login-copy">코드 해석, 디버깅, 구조 분석을 짧은 훈련 단위로 연습하세요.</p>
        <div className="login-actions">
          <a id="google-login" className="primary" href="/platform/auth/google/start">Google로 계속하기</a>
          <form id="guest-login-form" onSubmit={startGuest}>
            <button id="guest-login" type="submit" className="ghost" disabled={loading}>게스트로 시작</button>
          </form>
        </div>
        <p id="auth-message" className="status-line">{message}</p>
      </main>
    </section>
  );
}

function DashboardPage() {
  const ready = useSessionGuard();
  if (!ready) return <LoadingScreen />;
  return <Dashboard />;
}

function ProfilePage() {
  const ready = useSessionGuard();
  const [state, setState] = useState({
    me: null,
    profile: null,
    home: null,
    goal: null,
    report: null,
    history: [],
    modal: null,
    busyAction: "",
    toast: "",
  });

  const load = useCallback(async () => {
    const [me, profile, home, goal, history, report] = await Promise.all([
      apiRequest("/platform/me").catch(() => ({})),
      apiRequest("/platform/profile").catch(() => ({})),
      apiRequest("/platform/home").catch(() => ({})),
      apiRequest("/platform/me/goal").catch(() => ({})),
      apiRequest("/platform/learning/history?limit=25").catch(() => ({ history: [] })),
      apiRequest("/platform/reports/latest").catch(() => null),
    ]);
    setState((current) => ({
      ...current,
      me,
      profile,
      home,
      goal,
      history: history.history || history || [],
      report,
      toast: "",
    }));
  }, []);

  useEffect(() => {
    if (!ready) return undefined;
    const timer = window.setTimeout(() => {
      load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [ready, load]);

  if (!ready) return <LoadingScreen />;

  const name = state.me?.display_name || state.profile?.displayName || state.profile?.username || "학습자";
  const total = state.profile?.totalAttempts || state.home?.stats?.totalAttempts || 0;
  const accuracy = state.profile?.accuracy ?? state.home?.stats?.accuracy ?? "-";
  const week = state.home?.trend?.last7DaysAttempts || 0;
  const reviewCount = state.home?.reviewQueue?.dueCount || 0;
  const target = state.home?.dailyGoal?.targetSessions || state.goal?.dailyTargetSessions || 10;
  const completed = state.home?.dailyGoal?.completedSessions || 0;

  async function generateReport() {
    setState((current) => ({ ...current, busyAction: "report", toast: "" }));
    try {
      const payload = await apiRequest("/platform/reports/milestone", { method: "POST", body: { problem_count: 10 } });
      const latest = payload.reportId
        ? await apiRequest("/platform/reports/latest").catch(() => null)
        : null;
      const report = latest?.available ? { ...payload, ...latest } : payload;
      const toast = payload.status === "insufficient_history"
        ? "리포트 생성 조건을 확인해 주세요."
        : "학습 리포트를 생성했습니다.";
      setState((current) => ({
        ...current,
        report,
        modal: { type: "report", report },
        busyAction: "",
        toast,
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busyAction: "",
        toast: error.message || "학습 리포트를 생성하지 못했습니다.",
      }));
    }
  }

  async function openWrongNote() {
    setState((current) => ({ ...current, busyAction: "wrong-note", toast: "" }));
    try {
      const [queuePayload, historyPayload] = await Promise.all([
        apiRequest("/platform/learning/review-queue").catch(() => state.home?.reviewQueue || { items: [] }),
        apiRequest("/platform/learning/history?limit=50").catch(() => ({ history: state.history || [] })),
      ]);
      const reviewItems = Array.isArray(queuePayload?.items) ? queuePayload.items : [];
      const historyRows = Array.isArray(historyPayload?.history) ? historyPayload.history : [];
      const wrongItems = historyRows.filter(isWrongHistoryItem).slice(0, 10);
      setState((current) => ({
        ...current,
        modal: { type: "wrong-note", reviewItems, wrongItems },
        busyAction: "",
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        busyAction: "",
        toast: error.message || "오답 노트를 불러오지 못했습니다.",
      }));
    }
  }

  const currentReportTitle = state.report?.available === false ? "최근 리포트" : reportTitle(state.report);
  const currentReportSummary = reportSummary(state.report);
  const currentReportCreatedAt = reportCreatedAt(state.report);
  const currentReportDownloadUrl = reportDownloadUrl(state.report);

  return (
    <AppShell active="profile" title="프로필" subtitle="계정">
      <main id="profile-section" className="profile-grid">
        <aside className="card dashboard-panel profile-summary-card">
          <p className="dashboard-section-label">학습자 카드</p>
          <div className="profile-identity">
            <div id="profile-avatar" className="profile-avatar"><BrandIcon /></div>
            <div>
              <h2 id="profile-name">{name}</h2>
              <span id="profile-tier" className="pill soft">{state.profile?.skillLevel || "레벨 -"}</span>
              <p>모든 학습 모드는 이 진행도와 설정을 기준으로 맞춰집니다.</p>
            </div>
          </div>
          <div className="profile-action-list">
            <button id="btn-wrong-note" className="profile-action" type="button" onClick={openWrongNote} disabled={state.busyAction === "wrong-note"}>
              <span>오답 노트</span>
              <small>{state.busyAction === "wrong-note" ? "오답 기록을 불러오는 중입니다." : "복습할 문제와 최근 오답을 확인합니다."}</small>
            </button>
            <button id="btn-report" className="profile-action" type="button" onClick={generateReport} disabled={state.busyAction === "report"}>
              <span>학습 리포트</span>
              <small>{state.busyAction === "report" ? "리포트를 생성하는 중입니다." : "최근 풀이를 바탕으로 학습 리포트를 만듭니다."}</small>
            </button>
          </div>
          <section id="latest-report-card" className="report-card">
            <h3 id="latest-report-title">{currentReportTitle}</h3>
            <p id="latest-report-meta">{currentReportCreatedAt || "아직 생성된 리포트가 없습니다."}</p>
            {currentReportSummary ? <p id="latest-report-summary">{currentReportSummary}</p> : null}
            {currentReportDownloadUrl ? <a id="btn-latest-report-download" className="ghost" href={currentReportDownloadUrl}>PDF 다운로드</a> : null}
          </section>
        </aside>
        <section className="card dashboard-panel profile-settings-card">
          <div className="dashboard-panel-head"><div><h3>학습 요약</h3><p id="profile-goal-note">오늘 목표의 진행 상황입니다.</p></div></div>
          <div className="profile-stat-grid">
            <article><span>누적 풀이</span><strong id="profile-total-attempts">{total}</strong><p>전체 풀이 수</p></article>
            <article><span>정답률</span><strong id="profile-accuracy">{accuracy}%</strong><p>최근 정답률</p></article>
            <article><span>최근 7일</span><strong id="profile-week-attempts">{week}</strong><p>주간 풀이 수</p></article>
            <article><span>복습</span><strong id="profile-review-count">{reviewCount}</strong><p>복습할 항목</p></article>
          </div>
          <p id="profile-goal-progress" className="status-line">{completed} / {target}</p>
          <p id="profile-streak-days" className="status-line">{state.home?.streakDays || 0}일 연속 학습</p>
          <div className="profile-links">
            <a id="profile-review-link" className="ghost" href="/analysis.html">복습 이어가기</a>
            <a id="profile-recommend-link" className="ghost" href="/dashboard.html">추천 모드 보기</a>
          </div>
        </section>
      </main>
      <div id="toast" className="toast" hidden={!state.toast}>{state.toast}</div>
      <ProfileModal modal={state.modal} onClose={() => setState((current) => ({ ...current, modal: null }))} />
    </AppShell>
  );
}

function ProfileModal({ modal, onClose }) {
  if (!modal) return null;

  if (modal.type === "wrong-note") {
    const reviewItems = modal.reviewItems || [];
    const wrongItems = modal.wrongItems || [];
    return (
      <div id="modal" className="modal profile-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-card">
          <button id="modal-close" className="ghost modal-close" type="button" onClick={onClose}>닫기</button>
          <p className="dashboard-section-label">오답 노트</p>
          <h2 id="modal-title">지금 다시 볼 문제</h2>
          <div id="modal-body" className="modal-body">
            <section>
              <h3>복습 대기</h3>
              {reviewItems.length === 0 ? (
                <p className="empty">지금은 복습할 문제가 없습니다.</p>
              ) : (
                <div className="modal-list">
                  {reviewItems.map((item) => (
                    <article key={item.id || item.resumeLink || item.title} className="modal-list-item">
                      <div>
                        <strong>{item.title || "복습 문제"}</strong>
                        <p>{displayModeLabel(item.modeLabel || item.mode)} · {item.weaknessLabel || item.weaknessTag || "약점 보강"}</p>
                      </div>
                      <a className="ghost" href={item.resumeLink || item.actionLink || "/dashboard.html"}>다시 풀기</a>
                    </article>
                  ))}
                </div>
              )}
            </section>
            <section>
              <h3>최근 오답</h3>
              {wrongItems.length === 0 ? (
                <p className="empty">최근 오답 기록이 없습니다.</p>
              ) : (
                <div className="modal-list">
                  {wrongItems.map((item, index) => (
                    <article key={item.problem_id || item.problemId || item.id || index} className="modal-list-item">
                      <div>
                        <strong>{historyItemTitle(item, index)}</strong>
                        <p>{displayModeLabel(item.modeLabel || item.mode)} · {OUTCOME_LABELS[String(item.result || item.outcome || item.status || "").toLowerCase()] || "오답"}</p>
                        {historyItemSummary(item) ? <small>{historyItemSummary(item)}</small> : null}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    );
  }

  const report = modal.report || {};
  const summary = reportSummary(report);
  const downloadUrl = reportDownloadUrl(report);
  const brief = report.reportBrief || {};
  const nextSteps = report.priorityActions?.length ? report.priorityActions : (brief.nextSteps || []);
  return (
    <div id="modal" className="modal profile-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-card">
        <button id="modal-close" className="ghost modal-close" type="button" onClick={onClose}>닫기</button>
        <p className="dashboard-section-label">학습 리포트</p>
        <h2 id="modal-title">{reportTitle(report)}</h2>
        <div id="modal-body" className="modal-body">
          {summary ? <p>{summary}</p> : <p className="empty">리포트 요약을 준비 중입니다.</p>}
          {report.blockingMessage ? <p className="status-line">{report.blockingMessage}</p> : null}
          {nextSteps.length ? (
            <section>
              <h3>다음 학습</h3>
              <ul>
                {nextSteps.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
              </ul>
            </section>
          ) : null}
          {downloadUrl ? <a id="modal-report-download" className="primary" href={downloadUrl}>PDF 다운로드</a> : null}
        </div>
      </div>
    </div>
  );
}

async function streamProblem(path, body) {
  let payload;
  let failedBeforePayload = false;
  try {
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!response.ok || !response.body || !(response.headers.get("content-type") || "").includes("text/event-stream")) {
      failedBeforePayload = true;
      throw new Error("스트리밍 응답을 사용할 수 없습니다.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        const event = parseSseEvent(chunk);
        if (event.name === "payload") payload = event.data?.payload ?? event.data;
        if (event.name === "error" && payload === undefined) {
          throw new Error(errorMessageFromPayload(event.data, "스트리밍 처리에 실패했습니다."));
        }
      }
    }
  } catch {
    if (payload !== undefined) return payload;
    failedBeforePayload = true;
  }
  if (failedBeforePayload) {
    return apiRequest(path, { method: "POST", body });
  }
  return payload;
}

function parseSseEvent(chunk) {
  let name = "message";
  const data = [];
  String(chunk || "").split(/\r?\n/).forEach((line) => {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trim());
  });
  try {
    return { name, data: JSON.parse(data.join("\n") || "{}") };
  } catch {
    return { name, data: {} };
  }
}

async function resolveQueued(result) {
  if (!result?.queued || !result?.jobId) return result;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    const status = await apiRequest(`/platform/mode-jobs/${result.jobId}`);
    if (status.finished) return status.result || {};
    if (status.failed) throw new Error(status.error || "대기열 작업에 실패했습니다.");
  }
  throw new Error("대기열 작업 시간이 초과되었습니다.");
}

function AnalysisPage() {
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [status, setStatus] = useState("");

  if (!ready) return <LoadingScreen />;

  async function loadProblem() {
    setStatus("문제를 불러오는 중입니다...");
    setFeedback(null);
    try {
      const payload = await streamProblem("/platform/analysis/problem", { language: settings.language, difficulty: settings.difficulty });
      setProblem(payload.problem || payload);
      setStatus("");
    } catch (error) {
      setProblem(null);
      setStatus(error.message);
    }
  }

  async function submit(event) {
    event.preventDefault();
    const result = await resolveQueued(await apiRequest("/platform/analysis/submit", {
      method: "POST",
      body: { problemId: problem?.problemId || problem?.id, languageId: settings.language, explanation: answer },
    }));
    setFeedback(result);
  }

  return (
    <AppShell title="코드 분석">
      <main className="mode-shell">
        <section className="card dashboard-panel quiz-panel">
          <div className="mode-head"><h2 id="problem-title">{problem?.title || "문제를 불러오면 시작할 수 있습니다."}</h2><button id="btn-load-problem" className="primary" onClick={loadProblem}>문제 불러오기</button></div>
          <p className="status-line">{status}</p>
          <pre id="problem-code" className="code-block">{problem?.code || problem?.starterCode || "// 불러온 문제가 없습니다."}</pre>
          <p id="problem-prompt">{problem?.prompt || problem?.description || "문제를 불러온 뒤 코드의 동작을 설명하세요."}</p>
          <button id="btn-hint" className="ghost" type="button">힌트</button>
          <form id="answer-form" onSubmit={submit}>
            <textarea id="answer-text" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="코드 동작을 설명하세요." />
            <button className="primary" type="submit" disabled={!problem}>제출</button>
          </form>
        </section>
        <FeedbackPanel feedback={feedback} prefix="feedback" />
      </main>
    </AppShell>
  );
}

function CodeWithBlanks({ code, fallback = "// 불러온 코드가 없습니다." }) {
  const text = String(code || fallback);
  return text.split(/(\[BLANK\])/g).map((part, index) => (
    part === "[BLANK]"
      ? <span key={`blank-${index}`} className="blank-tile" aria-label="빈칸" />
      : part
  ));
}

function CodeBlockPage() {
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [result, setResult] = useState(null);
  const [selectedOption, setSelectedOption] = useState(null);
  const [status, setStatus] = useState("");

  if (!ready) return <LoadingScreen />;

  async function loadProblem() {
    setStatus("불러오는 중입니다...");
    const payload = await streamProblem("/platform/codeblock/problem", { language: settings.language, difficulty: settings.difficulty });
    setProblem(payload.problem || payload);
    setResult(null);
    setSelectedOption(null);
    setStatus("");
  }

  async function submit(index) {
    setSelectedOption(index);
    setResult(null);
    const payload = await apiRequest("/platform/codeblock/submit", { method: "POST", body: { problemId: problem?.problemId || problem?.id, selectedOption: index } });
    setResult(payload);
  }

  const correctAnswerValue = result?.correctAnswer ?? result?.correctAnswerIndex ?? result?.correct_answer_index ?? result?.answerIndex ?? result?.answer_index;
  const correctAnswerIndex = correctAnswerValue === undefined || correctAnswerValue === null ? null : Number(correctAnswerValue);

  function optionResultClass(index) {
    if (!result) return "";
    if (selectedOption === index) return result.correct ? "correct" : "wrong";
    if (!Number.isNaN(correctAnswerIndex) && correctAnswerIndex === index) return "correct";
    return "";
  }

  return (
    <AppShell title="코드 블록">
      <main className="mode-shell">
        <section className="card dashboard-panel cb-board">
          <div className="mode-head"><h2 id="cb-problem-title">{problem?.title || "코드 블록 문제를 불러오세요."}</h2><button id="cb-load-btn" className="primary" onClick={loadProblem}>불러오기</button></div>
          <p id="cb-status" className="status-line">{status}</p>
          <p id="cb-problem-purpose" className="mode-instruction">{problem?.objective || problem?.summary || problem?.prompt || "빈칸에 들어갈 코드를 선택해 전체 흐름을 완성하세요."}</p>
          <pre id="cb-code-display" className="code-block"><CodeWithBlanks code={problem?.code} /></pre>
          <div id="cb-options-container" className="option-grid cb-options">
            {(problem?.options || []).map((option, index) => (
              <button
                key={`${option}-${index}`}
                className={`ghost cb-option-btn ${optionResultClass(index)}`.trim()}
                type="button"
                onClick={() => submit(index)}
                disabled={!problem || Boolean(result)}
                aria-pressed={selectedOption === index}
              >
                {String(option)}
              </button>
            ))}
          </div>
          <p id="cb-result-message">{result ? (result.correct ? "정답입니다" : "다시 시도해 보세요") : ""}</p>
          <p id="cb-explanation">{result?.explanation || result?.feedback?.summary || ""}</p>
          <button id="cb-next-btn" className="ghost" onClick={loadProblem}>다음</button>
        </section>
      </main>
    </AppShell>
  );
}

function ArrangePage() {
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [blocks, setBlocks] = useState([]);
  const [draggingId, setDraggingId] = useState("");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("");

  if (!ready) return <LoadingScreen />;

  async function loadProblem() {
    setStatus("불러오는 중입니다...");
    const payload = await apiRequest("/platform/arrange/problem", { method: "POST", body: { language: settings.language, difficulty: settings.difficulty } });
    setProblem(payload.problem || payload);
    setBlocks((payload.blocks || payload.problem?.blocks || []).map((block, index) => ({
      id: String(block.id || `block-${index + 1}`),
      code: block.code || block.content || String(block),
    })));
    setResult(null);
    setDraggingId("");
    setStatus("");
  }

  async function submit() {
    const payload = await apiRequest("/platform/arrange/submit", { method: "POST", body: { problemId: problem?.problemId || problem?.id, order: blocks.map((block) => block.id) } });
    setResult(payload);
  }

  const arrangeResultById = new Map(
    (Array.isArray(result?.results) ? result.results : Array.isArray(result?.blockResults) ? result.blockResults : [])
      .map((item) => [
        String(item?.id ?? item?.blockId ?? item?.block_id ?? ""),
        item?.correct ?? item?.isCorrect ?? item?.is_correct,
      ])
      .filter(([id, value]) => id && value !== undefined)
  );
  const answerOrder = Array.isArray(result?.answerOrder)
    ? result.answerOrder
    : Array.isArray(result?.correctOrder)
      ? result.correctOrder
      : Array.isArray(result?.correct_order)
        ? result.correct_order
        : [];

  function arrangeBlockResultClass(block, index) {
    if (!result) return "";
    const explicitResult = arrangeResultById.get(String(block.id));
    if (explicitResult === true) return "is-correct";
    if (explicitResult === false) return "is-wrong";
    if (answerOrder.length === blocks.length) {
      return String(answerOrder[index]) === String(block.id) ? "is-correct" : "is-wrong";
    }
    return result.correct === true ? "is-correct" : "";
  }

  function clearArrangeResult() {
    if (result) setResult(null);
  }

  function moveBlock(sourceId, targetId, placeAfter = false) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    clearArrangeResult();
    setBlocks((current) => {
      const sourceIndex = current.findIndex((block) => block.id === sourceId);
      const targetIndex = current.findIndex((block) => block.id === targetId);
      if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return current;
      const next = [...current];
      const [moved] = next.splice(sourceIndex, 1);
      const adjustedTargetIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
      const insertIndex = Math.max(0, Math.min(next.length, adjustedTargetIndex + (placeAfter ? 1 : 0)));
      next.splice(insertIndex, 0, moved);
      return next;
    });
  }

  function moveBlockByOffset(index, offset) {
    const targetIndex = index + offset;
    if (targetIndex < 0 || targetIndex >= blocks.length) return;
    clearArrangeResult();
    setBlocks((current) => {
      const next = [...current];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  }

  function handleBlockDrop(event, targetId) {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const placeAfter = event.clientY > rect.top + rect.height / 2;
    moveBlock(draggingId || event.dataTransfer.getData("text/plain"), targetId, placeAfter);
    setDraggingId("");
  }

  return (
    <AppShell title="코드 배치">
      <main className="mode-shell">
        <section className="card dashboard-panel quiz-panel">
          <div className="mode-head"><h2 id="arr-title">{problem?.title || "코드 배치 문제를 불러오세요."}</h2><button id="arr-load-btn" className="primary" onClick={loadProblem}>불러오기</button></div>
          <p id="arr-status" className="status-line">{status}</p>
          <p id="arr-problem-prompt" className="mode-instruction">{problem?.prompt || problem?.objective || problem?.description || "섞인 코드 블록을 실행 순서에 맞게 드래그 앤 드롭으로 배치하세요."}</p>
          <p className="status-line">마우스 드래그 앤 드롭 또는 화살표 버튼으로 순서를 바꿀 수 있습니다.</p>
          <div id="arr-blocks" className="arrange-list arrange-blocks">
            {blocks.map((block, index) => (
              <div
                key={block.id}
                className={`arrange-block ${draggingId === block.id ? "dragging" : ""} ${arrangeBlockResultClass(block, index)}`.trim()}
                draggable
                onDragStart={(event) => {
                  setDraggingId(block.id);
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", block.id);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  const rect = event.currentTarget.getBoundingClientRect();
                  const placeAfter = event.clientY > rect.top + rect.height / 2;
                  moveBlock(draggingId || event.dataTransfer.getData("text/plain"), block.id, placeAfter);
                }}
                onDrop={(event) => handleBlockDrop(event, block.id)}
                onDragEnd={() => setDraggingId("")}
              >
                <pre>{block.code}</pre>
                <div className="arrange-block-actions" aria-label="블록 순서 변경">
                  <button type="button" className="ghost" onClick={() => moveBlockByOffset(index, -1)} disabled={index === 0} aria-label="위로 이동">↑</button>
                  <button type="button" className="ghost" onClick={() => moveBlockByOffset(index, 1)} disabled={index === blocks.length - 1} aria-label="아래로 이동">↓</button>
                </div>
              </div>
            ))}
          </div>
          <button id="arr-check-btn" className="primary" onClick={submit} disabled={!problem}>확인</button>
          <button id="arr-next-btn" className="ghost" onClick={loadProblem}>다음</button>
          <section id="arr-feedback" className="feedback-panel" hidden={!result}><p id="arr-feedback-text">{result?.feedback?.summary || (result?.correct ? "정답입니다" : "순서를 다시 검토하세요.")}</p></section>
          <section id="arr-answer" hidden={!result}><pre id="arr-answer-code" className="code-block">{result?.answerCode || (result?.answerOrder || []).join("\n")}</pre></section>
        </section>
      </main>
    </AppShell>
  );
}

function ReportModePage({ kind }) {
  const configs = {
    auditor: { title: "감사관 모드", problemPath: "/platform/auditor/problem", submitPath: "/platform/auditor/submit", prefix: "auditor", idPrefix: "auditor" },
    "refactoring-choice": { title: "최적안 선택", problemPath: "/platform/refactoring-choice/problem", submitPath: "/platform/refactoring-choice/submit", prefix: "rc", idPrefix: "rc" },
    "code-blame": { title: "범인 찾기", problemPath: "/platform/code-blame/problem", submitPath: "/platform/code-blame/submit", prefix: "cb", idPrefix: "cb" },
  };
  const config = configs[kind];
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [report, setReport] = useState("");
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("");

  if (!ready) return <LoadingScreen />;

  async function loadProblem() {
    setStatus("불러오는 중입니다...");
    const payload = await streamProblem(config.problemPath, { language: settings.language, difficulty: settings.difficulty });
    setProblem(payload.problem || payload);
    setResult(null);
    setSelected([]);
    setStatus("");
  }

  async function submit(event) {
    event.preventDefault();
    const body = { problemId: problem?.problemId || problem?.id, report };
    if (kind === "refactoring-choice") body.selectedOption = selected[0] || "";
    if (kind === "code-blame") body.selectedCommits = selected;
    const payload = await resolveQueued(await apiRequest(config.submitPath, { method: "POST", body }));
    setResult(payload);
  }

  const options = problem?.options || problem?.commits || [];
  const loadId = kind === "auditor" ? "auditor-load-btn" : `${config.prefix}-load-btn`;
  const statusId = kind === "auditor" ? "auditor-load-status" : `${config.prefix}-load-status`;

  return (
    <AppShell title={config.title}>
      <main className="mode-shell">
        <section className="card dashboard-panel quiz-panel">
          <div className="mode-head"><h2 id={`${config.prefix}-problem-title`}>{problem?.title || `${config.title} 문제를 불러오세요.`}</h2><button id={loadId} className="primary" onClick={loadProblem}>불러오기</button></div>
          <p id={statusId} className="status-line">{status}</p>
          {kind === "auditor" ? (
            <>
              <pre id="auditor-problem-code" className="code-block">{problem?.code || "// 불러온 코드가 없습니다."}</pre>
              <p id="auditor-problem-prompt" className="mode-instruction">{problem?.prompt || problem?.description || "코드에서 위험한 지점과 근거를 찾아 감사 리포트를 작성하세요."}</p>
            </>
          ) : null}
          {kind === "refactoring-choice" ? (
            <>
              <p id="rc-problem-scenario" className="mode-instruction">{problem?.scenario || problem?.prompt || "주어진 제약 조건을 기준으로 가장 적합한 리팩터링 안을 선택하세요."}</p>
              <ul id="rc-problem-constraints">{(problem?.constraints || []).map((row) => <li key={row}>{row}</li>)}</ul>
              <p id="rc-problem-prompt" className="mode-instruction">{problem?.prompt || problem?.description || "선택한 안이 왜 최적인지 근거를 작성하세요."}</p>
            </>
          ) : null}
          {kind === "code-blame" ? (
            <>
              <p id="cb-problem-count">커밋 {options.length}개</p>
              <pre id="cb-error-log" className="code-block">{problem?.errorLog || ""}</pre>
              <p id="cb-problem-prompt" className="mode-instruction">{problem?.prompt || problem?.description || "에러 로그와 커밋 diff를 비교해 원인 커밋을 고르고 근거를 작성하세요."}</p>
            </>
          ) : null}
          <div id={kind === "refactoring-choice" ? "rc-options" : kind === "code-blame" ? "cb-commit-list" : `${config.prefix}-options`} className="option-grid">
            {options.map((option, index) => {
              const value = option.optionId || option.id || String(index);
              const checked = selected.includes(value);
              return (
                <label key={value} className="option-card">
                  <input
                    type={kind === "code-blame" ? "checkbox" : "radio"}
                    name={kind === "refactoring-choice" ? "selected-option" : "selected-commit"}
                    value={value}
                    checked={checked}
                    onChange={(event) => {
                      if (kind === "code-blame") {
                        setSelected((current) => event.target.checked ? [...current, value] : current.filter((item) => item !== value));
                      } else {
                        setSelected([value]);
                      }
                    }}
                  />
                  <strong>{option.title || value}</strong>
                  <pre>{option.code || option.diff || ""}</pre>
                </label>
              );
            })}
          </div>
          <form id={`${config.prefix}-report-form`} onSubmit={submit}>
            <textarea id={`${config.prefix}-report-text`} value={report} onChange={(event) => setReport(event.target.value)} placeholder="판단 근거를 작성하세요." />
            <button id={`${config.prefix}-submit-btn`} className="primary" type="submit" disabled={!problem}>제출</button>
          </form>
        </section>
        <ReportFeedback prefix={config.prefix} result={result} kind={kind} />
      </main>
    </AppShell>
  );
}

function ReportFeedback({ prefix, result, kind }) {
  const feedback = result?.feedback || {};
  return (
    <section className="card dashboard-panel feedback-panel" hidden={!result}>
      <strong id={`${prefix}-score`}>{result?.score ?? feedback.score ?? "-"}</strong>
      <p id={`${prefix}-verdict`}>{result?.verdict || (result?.correct ? "통과" : "검토 필요")}</p>
      <p id={`${prefix}-feedback-summary`}>{feedback.summary || result?.summary || ""}</p>
      <List id={`${prefix}-strengths`} items={feedback.strengths || []} />
      <List id={`${prefix}-improvements`} items={feedback.improvements || []} />
      <List id={`${prefix}-found-types`} items={result?.foundTypes || []} />
      <List id={`${prefix}-missed-types`} items={result?.missedTypes || []} />
      {kind === "refactoring-choice" ? <><p id="rc-selected-option">{result?.selectedOption || ""}</p><p id="rc-best-option">{result?.bestOption || ""}</p><List id="rc-option-reviews" items={(result?.optionReviews || []).map((row) => `${row.optionId}: ${row.summary}`)} /></> : null}
      {kind === "code-blame" ? <><p id="cb-selected-commits">{(result?.selectedCommits || []).join(", ")}</p><p id="cb-culprit-commits">{(result?.culpritCommits || []).join(", ")}</p><List id="cb-commit-reviews" items={(result?.commitReviews || []).map((row) => `${row.optionId}: ${row.summary}`)} /></> : null}
      <p id={`${prefix}-reference-report`}>{result?.referenceReport || ""}</p>
    </section>
  );
}

function fileIconLabel(file) {
  const name = String(file?.name || file?.path || "file");
  const ext = name.includes(".") ? name.split(".").pop() : name.slice(0, 2);
  return String(ext || "FILE").slice(0, 4).toUpperCase();
}

function displayLanguage(value, fallback = "-") {
  const raw = String(value || "").trim();
  if (!raw) return fallback;
  const normalized = normalizeLanguageId(raw, "");
  return normalized ? languageTitle(normalized) : raw;
}

function fileLanguage(file, fallback = "-") {
  return file?.language || file?.lang || fallback;
}

function fileRole(file) {
  return file?.role || file?.type || "source";
}

function codeLines(content) {
  const text = String(content || "");
  if (!text) return ["// 불러온 파일이 없습니다."];
  return text.replace(/\n$/, "").split("\n");
}

function pathParts(file) {
  const path = String(file?.path || file?.name || "");
  return path ? path.split(/[\\/]/).filter(Boolean) : [];
}

function AdvancedAnalysisPage({ config }) {
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [activeFileId, setActiveFileId] = useState("");
  const [report, setReport] = useState("");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    document.body.dataset.advancedAnalysisMode = config.mode;
    return () => {
      delete document.body.dataset.advancedAnalysisMode;
    };
  }, [config.mode]);

  if (!ready) return <LoadingScreen />;

  const files = problem?.files || [];
  const activeFile = files.find((file) => file.id === activeFileId) || files[0] || {};
  const activePathParts = pathParts(activeFile);
  const activeLanguage = displayLanguage(fileLanguage(activeFile, settings.language));
  const activeRole = fileRole(activeFile);
  const activeLines = codeLines(activeFile.content);
  const loadedCount = files.length;

  async function loadProblem() {
    setStatus("작업 공간을 불러오는 중입니다...");
    const payload = await streamProblem(config.problemPath, { language: settings.language, difficulty: settings.difficulty });
    setProblem(payload.problem || payload);
    setActiveFileId((payload.files || payload.problem?.files || [])[0]?.id || "");
    setResult(null);
    setStatus("");
  }

  async function submit(event) {
    event.preventDefault();
    const payload = await resolveQueued(await apiRequest(config.submitPath, { method: "POST", body: { problemId: problem?.problemId || problem?.id, report } }));
    setResult(payload);
  }

  return (
    <AppShell title={config.title}>
      <main id="advanced-analysis-shell" className="advanced-analysis-view">
        <section className="advanced-analysis-layout">
          <section className="card dashboard-panel advanced-analysis-panel advanced-analysis-overview">
            <div className="advanced-mode-summary">
              <p id="advanced-mode-state" className="badge soft">{problem ? "문제 준비됨" : "문제 대기"}</p>
              <h2 id="advanced-mode-headline">{problem?.title || `${config.title} 문제를 생성할 준비가 되어 있습니다.`}</h2>
              <p id="advanced-mode-summary">{problem?.summary || "문제 받기를 누르면 AI가 워크스페이스 파일과 분석 과제를 생성합니다."}</p>
            </div>
            <div className="advanced-mode-meta">
              <span id="advanced-mode-file-range" className="pill">파일 {loadedCount || "-"}개</span>
            </div>
            <div className="advanced-mode-actions">
              <button id="advanced-load-btn" className="primary" type="button" onClick={loadProblem}>문제 받기</button>
              <p id="advanced-load-status" className="advanced-load-status">{status || "문제 받기를 누르면 IDE 워크스페이스가 채워집니다."}</p>
            </div>
          </section>

          <section className="card dashboard-panel advanced-analysis-panel advanced-analysis-stage">
            <div className="advanced-workbench-titlebar">
              <div className="advanced-workbench-title">
                <span className="advanced-workbench-title-label">ADVANCED ANALYSIS</span>
                <strong id="advanced-workspace-title">{problem?.workspace || `${config.mode}-analysis.workspace`}</strong>
              </div>
              <span className="pill soft">Read-only</span>
            </div>

            <div className="advanced-workbench">
              <aside className="advanced-sidebar">
                <div className="advanced-sidebar-head">
                  <span className="advanced-sidebar-label">Explorer</span>
                  <strong>읽기 전용 워크스페이스</strong>
                </div>
                <div className="advanced-sidebar-section-label">FILES</div>
                <div id="advanced-file-rail" className="advanced-file-rail">
                  {files.length === 0 ? (
                    <p className="empty">파일을 불러오면 여기에 표시됩니다.</p>
                  ) : files.map((file) => {
                    const isActive = file === activeFile;
                    return (
                      <button key={file.id || file.path} type="button" data-advanced-file-id={file.id} className={`advanced-explorer-item ${isActive ? "is-active" : ""}`} aria-pressed={isActive} onClick={() => setActiveFileId(file.id)}>
                        <span className="advanced-explorer-row">
                          <span className="advanced-file-icon">{fileIconLabel(file)}</span>
                          <span className="advanced-file-button-title">{file.name || file.path}</span>
                        </span>
                        <span className="advanced-file-button-meta">{file.path || file.name}</span>
                        <span className="advanced-file-button-badges">
                          <span className="pill soft">{displayLanguage(fileLanguage(file, settings.language))}</span>
                          <span className="pill soft">{fileRole(file)}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </aside>

              <div className="advanced-editor-workbench">
                <div className="advanced-editor-topbar">
                  <div id="advanced-file-strip" className="advanced-file-strip">
                    {files.map((file) => {
                      const isActive = file === activeFile;
                      return (
                        <button key={file.id || file.path} type="button" data-advanced-file-id={file.id} className={`advanced-editor-tab ${isActive ? "is-active" : ""}`} aria-pressed={isActive} onClick={() => setActiveFileId(file.id)}>
                          <span className="advanced-file-icon">{fileIconLabel(file)}</span>
                          <span className="advanced-editor-tab-title">{file.name || file.path}</span>
                        </button>
                      );
                    })}
                  </div>
                  <div className="advanced-file-meta">
                    <span id="advanced-active-file-language" className="pill soft">언어 {activeLanguage}</span>
                    <span id="advanced-active-file-role" className="pill soft">역할 {activeRole}</span>
                  </div>
                </div>

                <div id="advanced-editor-breadcrumbs" className="advanced-editor-breadcrumbs">
                  {activePathParts.length === 0 ? <span>경로 -</span> : activePathParts.map((part, index) => (
                    <span key={`${part}-${index}`} className="advanced-breadcrumb-group">
                      <span className="advanced-breadcrumb-item">{part}</span>
                      {index < activePathParts.length - 1 ? <span className="advanced-breadcrumb-divider">/</span> : null}
                    </span>
                  ))}
                </div>

                <div className="advanced-editor-surface">
                  <div className="advanced-editor-header">
                    <div>
                      <p className="eyebrow">Read-only IDE</p>
                      <h2 id="advanced-active-file-name">{activeFile.name || activeFile.path || "파일을 선택해 주세요."}</h2>
                      <p id="advanced-active-file-path">{activeFile.path || "경로 -"}</p>
                    </div>
                  </div>
                  <div id="advanced-code-view" className="advanced-code-view" role="region" aria-label="코드 보기">
                    {activeLines.map((line, index) => (
                      <div key={`${index}-${line}`} className="advanced-code-row">
                        <span className="advanced-code-line-number">{index + 1}</span>
                        <code className="advanced-code-line-content">{line || " "}</code>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="advanced-statusbar">
                  <span id="advanced-statusbar-left">{loadedCount} files loaded</span>
                  <span id="advanced-statusbar-right">Read-only · {activeLanguage}</span>
                </div>
              </div>
            </div>
          </section>

          <section className="advanced-analysis-bottom">
            <article className="card dashboard-panel advanced-analysis-panel advanced-task-panel">
              <div className="advanced-task-head">
                <h3>분석 과제</h3>
                <p id="advanced-problem-title" className="advanced-problem-title">{problem?.title || "문제를 아직 불러오지 않았습니다."}</p>
                <p id="advanced-task-prompt">{problem?.prompt || problem?.description || "문제를 받은 뒤 파일의 핵심 흐름을 설명해 주세요."}</p>
              </div>
              <List id="advanced-checklist" items={problem?.checklist || []} />
              <form onSubmit={submit}>
                <label htmlFor="advanced-report-text">분석 리포트</label>
                <textarea id="advanced-report-text" value={report} onChange={(event) => setReport(event.target.value)} placeholder="분석 내용을 작성하세요." />
                <button id="advanced-submit-btn" className="primary" type="submit" disabled={!problem}>분석 제출</button>
              </form>
            </article>

            <article className="card dashboard-panel advanced-analysis-panel advanced-status-panel">
              <div className="advanced-status-head">
                <h3>연결 상태</h3>
                <p>문제 생성, 리포트 제출, AI 피드백 결과가 이 영역에서 갱신됩니다.</p>
              </div>
              <div id="advanced-status-cards" className="advanced-status-cards">
                <article className="advanced-status-card">
                  <div className="advanced-status-card-head"><strong>워크스페이스</strong><span className="pill soft">{problem ? "준비됨" : "대기"}</span></div>
                  <p>{loadedCount ? `${loadedCount}개 파일을 불러왔습니다.` : "문제 받기 후 파일이 표시됩니다."}</p>
                </article>
                <article className="advanced-status-card">
                  <div className="advanced-status-card-head"><strong>리포트</strong><span className="pill soft">{result ? "완료" : "대기"}</span></div>
                  <p>{result ? "피드백을 확인할 수 있습니다." : "분석 내용을 제출하면 점수와 피드백이 표시됩니다."}</p>
                </article>
              </div>
              <section id="advanced-result-panel" className="advanced-result-panel" hidden={!result}>
                <div className="advanced-result-summary-bar">
                  <strong id="advanced-result-score">{result?.score ?? result?.feedback?.score ?? "-"}</strong>
                  <span id="advanced-result-verdict" className="badge soft">{result?.verdict || (result?.correct ? "통과" : "검토 필요")}</span>
                  <span id="advanced-result-threshold" className="pill soft">{result?.threshold ? `기준 ${result.threshold}` : "기준 -"}</span>
                </div>
                <p id="advanced-result-summary" className="advanced-result-summary">{result?.feedback?.summary || result?.summary || ""}</p>
                <div className="advanced-result-lists">
                  <article className="advanced-result-card">
                    <h4>강점</h4>
                    <List id="advanced-result-strengths" items={result?.feedback?.strengths || result?.strengths || []} />
                  </article>
                  <article className="advanced-result-card">
                    <h4>개선점</h4>
                    <List id="advanced-result-improvements" items={result?.feedback?.improvements || result?.improvements || []} />
                  </article>
                </div>
                <article className="advanced-result-card advanced-reference-card">
                  <h4>모범 분석 리포트</h4>
                  <pre id="advanced-reference-report" className="advanced-reference-report">{result?.referenceReport || ""}</pre>
                </article>
              </section>
            </article>
          </section>
        </section>
        <p id="advanced-analysis-toast" className="toast" hidden>{status}</p>
      </main>
    </AppShell>
  );
}

const ADMIN_REFRESH_INTERVAL_MS = 3000;
const ADMIN_LOCALE = "ko-KR";
const ADMIN_CHART_COLORS = ["#2563eb", "#16a34a", "#dc2626", "#7c3aed"];

function encodeAdminKey(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function adminHeaders(key) {
  return { "X-Admin-Key-B64": encodeAdminKey(key) };
}

function fmtAdminNumber(value) {
  return Number(value || 0).toLocaleString(ADMIN_LOCALE);
}

function fmtAdminPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function fmtAdminDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(ADMIN_LOCALE, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function adminErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const code = detail.code ? ` [${detail.code}]` : "";
    return `${detail.detail || detail.message || fallback}${code}`;
  }
  return payload?.message || fallback;
}

async function adminRequest(path, { method = "GET", key } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: adminHeaders(key),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(adminErrorMessage(payload, `관리자 요청 실패 (${response.status})`));
  }
  return payload;
}

function shutdownMessage(shutdown = {}) {
  if (shutdown.detail) return shutdown.detail;
  switch (shutdown.reason) {
    case "docker_socket_not_mounted":
      return "Docker socket이 API 컨테이너에 연결되지 않아 스택 종료를 사용할 수 없습니다.";
    case "shutdown_targets_not_found":
      return "Compose 스택 컨테이너를 찾지 못했습니다.";
    case "shutdown_targets_incomplete":
      return "API 컨테이너만 감지되어 전체 스택 종료를 보장할 수 없습니다.";
    case "docker_control_unavailable":
      return "API 컨테이너에서 Docker daemon에 접근할 수 없습니다.";
    case "local_process_disabled":
      return "로컬 프로세스에서는 스택 종료를 사용할 수 없습니다.";
    case "disabled_by_config":
      return "관리자 종료 기능이 설정에서 비활성화되어 있습니다.";
    default:
      return "현재 설정에서는 스택 안전 종료를 사용할 수 없습니다.";
  }
}

function chartMax(series) {
  const values = series.flatMap((row) => row.values || []).map((value) => Number(value || 0));
  return Math.max(1, ...values);
}

function labelIndexes(labels) {
  const last = labels.length - 1;
  if (last <= 0) return labels.length ? [0] : [];
  return [...new Set([0, Math.floor(last / 2), last])];
}

function AdminLineChart({ id, labels = [], series = [], suffix = "" }) {
  const width = 640;
  const height = 230;
  const pad = { top: 18, right: 18, bottom: 36, left: 44 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const max = chartMax(series);
  const hasData = labels.length > 0 && series.some((row) => (row.values || []).some((value) => Number(value || 0) > 0));
  const xFor = (index) => pad.left + (labels.length <= 1 ? plotWidth / 2 : (index * plotWidth) / (labels.length - 1));
  const yFor = (value) => pad.top + plotHeight - (Number(value || 0) / max) * plotHeight;
  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg id={id} className="admin-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={id}>
      {gridLines.map((line) => {
        const y = pad.top + plotHeight * line;
        const value = Math.round(max * (1 - line));
        return (
          <g key={line}>
            <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="admin-chart-grid-line" />
            <text x={pad.left - 8} y={y + 4} className="admin-chart-axis" textAnchor="end">{value}{suffix}</text>
          </g>
        );
      })}
      <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} className="admin-chart-axis-line" />
      <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="admin-chart-axis-line" />
      {labelIndexes(labels).map((index) => (
        <text key={index} x={xFor(index)} y={height - 10} className="admin-chart-axis" textAnchor="middle">{labels[index]}</text>
      ))}
      {hasData ? series.map((row, index) => {
        const points = (row.values || []).map((value, pointIndex) => `${xFor(pointIndex)},${yFor(value)}`).join(" ");
        return <polyline key={row.label} points={points} fill="none" stroke={row.color || ADMIN_CHART_COLORS[index % ADMIN_CHART_COLORS.length]} className="admin-chart-line" />;
      }) : (
        <text x={width / 2} y={height / 2} className="admin-chart-empty" textAnchor="middle">표시할 데이터가 없습니다.</text>
      )}
    </svg>
  );
}

function AdminBarChart({ id, labels = [], series = [] }) {
  const width = 640;
  const height = 230;
  const pad = { top: 18, right: 18, bottom: 36, left: 44 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const max = chartMax(series);
  const groupCount = Math.max(labels.length, 1);
  const groupWidth = plotWidth / groupCount;
  const barWidth = Math.max(4, (groupWidth * 0.72) / Math.max(series.length, 1));
  const hasData = labels.length > 0 && series.some((row) => (row.values || []).some((value) => Number(value || 0) > 0));
  const yFor = (value) => pad.top + plotHeight - (Number(value || 0) / max) * plotHeight;

  return (
    <svg id={id} className="admin-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={id}>
      {[0, 0.25, 0.5, 0.75, 1].map((line) => {
        const y = pad.top + plotHeight * line;
        return <line key={line} x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="admin-chart-grid-line" />;
      })}
      <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="admin-chart-axis-line" />
      {hasData ? labels.map((label, labelIndex) => {
        const groupX = pad.left + labelIndex * groupWidth + groupWidth * 0.14;
        return (
          <g key={label}>
            {series.map((row, seriesIndex) => {
              const value = Number(row.values?.[labelIndex] || 0);
              const barHeight = height - pad.bottom - yFor(value);
              return (
                <rect
                  key={row.label}
                  x={groupX + seriesIndex * barWidth}
                  y={yFor(value)}
                  width={barWidth - 2}
                  height={Math.max(0, barHeight)}
                  rx="3"
                  fill={row.color || ADMIN_CHART_COLORS[seriesIndex % ADMIN_CHART_COLORS.length]}
                />
              );
            })}
          </g>
        );
      }) : (
        <text x={width / 2} y={height / 2} className="admin-chart-empty" textAnchor="middle">표시할 데이터가 없습니다.</text>
      )}
      {labelIndexes(labels).map((index) => (
        <text key={index} x={pad.left + index * groupWidth + groupWidth / 2} y={height - 10} className="admin-chart-axis" textAnchor="middle">{labels[index]}</text>
      ))}
    </svg>
  );
}

function AdminChartCard({ title, legend = [], children }) {
  return (
    <article className="card dashboard-panel admin-chart-card">
      <div className="admin-chart-head">
        <h3>{title}</h3>
        <div className="admin-chart-legend">
          {legend.map((item, index) => (
            <span key={item.label}><i style={{ background: item.color || ADMIN_CHART_COLORS[index % ADMIN_CHART_COLORS.length] }} />{item.label}</span>
          ))}
        </div>
      </div>
      <div className="admin-chart-wrap">{children}</div>
    </article>
  );
}

function AdminStatCard({ id, hintId, title, value, hint, tone = "blue" }) {
  return (
    <article className={`card dashboard-panel admin-stat-card tone-${tone}`}>
      <span>{title}</span>
      <strong id={id}>{value}</strong>
      <p id={hintId}>{hint}</p>
    </article>
  );
}

function SummaryMetric({ label, value }) {
  return <div className="admin-summary-metric"><span>{label}</span><strong>{fmtAdminNumber(value)}</strong></div>;
}

function SummaryList({ items, empty, renderItem }) {
  if (!items?.length) return <p className="summary-empty">{empty}</p>;
  return <ul className="summary-list">{items.map((item, index) => <li key={`${index}-${JSON.stringify(item)}`}>{renderItem(item)}</li>)}</ul>;
}

function ContentSummaryPanel({ summary = {} }) {
  const statusCounts = summary.statusCounts || {};
  const promptVersions = Array.isArray(summary.topPromptVersions) ? summary.topPromptVersions : [];
  const pendingProblems = Array.isArray(summary.recentPendingProblems) ? summary.recentPendingProblems : [];

  return (
    <section id="content-summary-panel" className="card dashboard-panel admin-summary-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>콘텐츠 운영 요약</h3>
          <p>prompt version, 검수 상태, 최근 pending 문제를 확인합니다.</p>
        </div>
      </div>
      <div className="admin-summary-metrics">
        <SummaryMetric label="추적 중인 문제" value={summary.totals} />
        <SummaryMetric label="pending" value={statusCounts.pending} />
        <SummaryMetric label="approved" value={statusCounts.approved} />
        <SummaryMetric label="hidden" value={statusCounts.hidden} />
      </div>
      <div className="admin-summary-columns">
        <section>
          <h4>상위 prompt version</h4>
          <SummaryList
            items={promptVersions}
            empty="아직 기록된 prompt version이 없습니다."
            renderItem={(item) => <><span>{item.version || "-"}</span><strong>{fmtAdminNumber(item.count)}</strong></>}
          />
        </section>
        <section>
          <h4>최근 pending 문제</h4>
          <SummaryList
            items={pendingProblems}
            empty="현재 pending 상태 문제는 없습니다."
            renderItem={(item) => (
              <>
                <div><strong>{item.title || "제목 없는 문제"}</strong><p>{item.mode || "-"} · {item.promptVersion || "버전 없음"}</p></div>
                <span>{fmtAdminDate(item.createdAt)}</span>
              </>
            )}
          />
        </section>
      </div>
    </section>
  );
}

function OpsEventsPanel({ summary = {} }) {
  const statusCounts = summary.statusCounts || {};
  const topEventTypes = Array.isArray(summary.topEventTypes) ? summary.topEventTypes : [];
  const modeSummary = Array.isArray(summary.modeSummary) ? summary.modeSummary : [];
  const latest = Array.isArray(summary.latest) ? summary.latest : [];

  return (
    <section id="ops-events-panel" className="card dashboard-panel admin-summary-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>운영 이벤트 요약</h3>
          <p>최근 {fmtAdminNumber(summary.windowHours || 24)}시간 이벤트 상태, 모드별 실패, 최신 이벤트를 확인합니다.</p>
        </div>
      </div>
      <div className="admin-summary-metrics">
        <SummaryMetric label="이벤트" value={summary.total} />
        <SummaryMetric label="success" value={statusCounts.success} />
        <SummaryMetric label="failure" value={statusCounts.failure} />
        <SummaryMetric label="review_required" value={statusCounts.review_required} />
      </div>
      <div className="admin-summary-columns">
        <section>
          <h4>이벤트 타입 상위</h4>
          <SummaryList
            items={topEventTypes}
            empty="최근 이벤트가 없습니다."
            renderItem={(item) => <><span>{item.eventType || "-"}</span><strong>{fmtAdminNumber(item.count)}</strong></>}
          />
        </section>
        <section>
          <h4>모드별 상태</h4>
          <SummaryList
            items={modeSummary}
            empty="최근 모드 이벤트가 없습니다."
            renderItem={(item) => (
              <>
                <span>{displayModeLabel(item.mode)}</span>
                <strong>호출 {fmtAdminNumber(item.total)} / 실패 {fmtAdminNumber(item.failure)} / {fmtAdminNumber(item.avgLatencyMs)}ms</strong>
              </>
            )}
          />
        </section>
      </div>
      <section className="latest-events">
        <h4>최신 이벤트</h4>
        <SummaryList
          items={latest}
          empty="표시할 최신 이벤트가 없습니다."
          renderItem={(item) => (
            <>
              <div><strong>{item.eventType || "event"}</strong><p>{displayModeLabel(item.mode)} · {item.status || "-"} · {item.requestId || "request id 없음"}</p></div>
              <span>{fmtAdminDate(item.createdAt)}</span>
            </>
          )}
        />
      </section>
    </section>
  );
}

function PlatformModesPanel({ platformModes = {} }) {
  const modes = platformModes.modes || {};
  const rows = Object.entries(modes).map(([mode, data]) => ({
    mode,
    problem: data.problem || {},
    submit: data.submit || {},
    background: data.submitBackground || {},
    dispatch: data.dispatch || {},
  }));
  const count = (value) => Number(value || 0);

  return (
    <section className="card dashboard-panel admin-summary-panel admin-platform-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>학습 모드 런타임</h3>
          <p>문제 생성, 제출, 큐 처리 상태를 모드별로 확인합니다.</p>
        </div>
        <span className="pill soft">처리 중 {fmtAdminNumber(platformModes.inFlight)}</span>
      </div>
      <div className="admin-mode-table" role="table" aria-label="학습 모드 런타임">
        <div role="row" className="admin-mode-table-head">
          <span role="columnheader">모드</span>
          <span role="columnheader">문제 생성</span>
          <span role="columnheader">제출</span>
          <span role="columnheader">큐</span>
        </div>
        {rows.length ? rows.map((row) => (
          <div role="row" className="admin-mode-table-row" key={row.mode}>
            <strong role="cell">{displayModeLabel(row.mode)}</strong>
            <span role="cell">{fmtAdminNumber(row.problem.calls)}회 · 실패 {fmtAdminNumber(row.problem.failure)}</span>
            <span role="cell">{fmtAdminNumber(count(row.submit.calls) + count(row.background.calls))}회 · 실패 {fmtAdminNumber(count(row.submit.failure) + count(row.background.failure))}</span>
            <span role="cell">queued {fmtAdminNumber(row.dispatch.queued)} / inline {fmtAdminNumber(row.dispatch.inline)}</span>
          </div>
        )) : <p className="summary-empty">아직 기록된 학습 모드 호출이 없습니다.</p>}
      </div>
    </section>
  );
}

function AdminPage() {
  const [key, setKey] = useState(window.sessionStorage.getItem("admin_panel_key") || "");
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState("메트릭 응답을 기다리는 중입니다.");
  const [statusLevel, setStatusLevel] = useState("warn");
  const [loading, setLoading] = useState(false);
  const [shutdownBusy, setShutdownBusy] = useState(false);

  const load = useCallback(async () => {
    const trimmedKey = key.trim();
    if (!trimmedKey) {
      setStatus("관리자 키를 입력해 주세요.");
      setStatusLevel("bad");
      return;
    }

    setLoading(true);
    try {
      const payload = await adminRequest("/api/admin/metrics", { key: trimmedKey });
      const shutdown = payload?.admin?.shutdown || {};
      setMetrics(payload);
      if (shutdown.supported === false) {
        setStatus(`메트릭은 정상 동작 중이지만 종료 기능은 제한됩니다. ${shutdownMessage(shutdown)}`);
        setStatusLevel("warn");
      } else {
        setStatus("관리자 메트릭과 백엔드 기능이 정상 동작 중입니다.");
        setStatusLevel("ok");
      }
    } catch (err) {
      setStatus(err.message || "관리자 메트릭을 불러오지 못했습니다.");
      setStatusLevel("bad");
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    if (!key.trim()) return undefined;
    load();
    const timer = window.setInterval(load, ADMIN_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [key, load]);

  async function shutdownStack() {
    const trimmedKey = key.trim();
    const shutdown = metrics?.admin?.shutdown || {};
    if (!trimmedKey) {
      setStatus("관리자 키를 입력해 주세요.");
      setStatusLevel("bad");
      return;
    }
    if (shutdown.supported === false) {
      setStatus(shutdownMessage(shutdown));
      setStatusLevel("warn");
      return;
    }

    const ok = window.confirm("Docker 스택을 안전하게 종료할까요? 현재 접속과 작업이 모두 중단됩니다.");
    if (!ok) return;

    setShutdownBusy(true);
    setStatus("종료 요청을 전송하는 중입니다...");
    setStatusLevel("warn");
    try {
      const payload = await adminRequest("/api/admin/shutdown", { method: "POST", key: trimmedKey });
      setStatus(`${payload.detail || "종료 요청이 접수되었습니다."} 서비스가 순차적으로 중지됩니다.`);
      setStatusLevel("warn");
    } catch (err) {
      setStatus(err.message || "종료 요청에 실패했습니다.");
      setStatusLevel("bad");
      setShutdownBusy(false);
    }
  }

  const aiTotals = metrics?.ai?.totals || {};
  const aiTimeline = metrics?.ai?.timeline || {};
  const userTimeline = metrics?.userTimeline || {};
  const requestTimeline = metrics?.requestsTimeline || {};
  const requestTotals = metrics?.requestTotals || {};
  const shutdown = metrics?.admin?.shutdown || {};
  const shutdownDisabled = shutdown.supported === false || shutdownBusy || loading;

  return (
    <section className="app dashboard-shell admin-shell">
      <header className="app-header page-header dashboard-topbar admin-topbar">
        <div className="brand-lockup">
          <span className="brand-mark"><BrandIcon /></span>
          <div>
            <p className="eyebrow">관리자</p>
            <h1>운영 현황</h1>
            <p>실시간 접속, AI 사용량, 콘텐츠 상태, 운영 이벤트를 확인합니다.</p>
          </div>
        </div>
        <div className="admin-topbar-actions">
          <span id="last-updated" className="pill soft">마지막 갱신: {fmtAdminDate(metrics?.generatedAt)}</span>
          <button id="refresh-btn" className="primary" type="button" onClick={load} disabled={loading}>{loading ? "갱신 중" : "지금 새로고침"}</button>
          <button id="shutdown-btn" className="ghost danger" type="button" onClick={shutdownStack} disabled={shutdownDisabled} title={shutdown.supported === false ? shutdownMessage(shutdown) : ""}>스택 안전 종료</button>
          <a className="ghost" href="/dashboard.html">대시보드</a>
        </div>
      </header>

      <main className="admin-main">
        <section className="card dashboard-panel admin-key-panel">
          <div>
            <h2>관리자 키</h2>
            <p>키는 이 브라우저 세션에만 저장됩니다.</p>
          </div>
          <div className="goal-form-row">
            <input id="admin-key" value={key} onChange={(event) => {
              const nextKey = event.target.value;
              setKey(nextKey);
              if (nextKey.trim()) window.sessionStorage.setItem("admin_panel_key", nextKey);
              else window.sessionStorage.removeItem("admin_panel_key");
            }} placeholder="관리자 패널 키" />
            <button id="admin-load" className="primary" type="button" onClick={load} disabled={loading}>지표 불러오기</button>
          </div>
        </section>

        <section className="admin-stat-grid" aria-live="polite">
          <AdminStatCard id="active-users" title="활성 사용자" value={fmtAdminNumber(metrics?.activeUsers)} hint="최근 활동 기준 사용자 수" tone="blue" />
          <AdminStatCard id="active-clients" title="활성 클라이언트" value={fmtAdminNumber(metrics?.activeClients)} hint="현재 접속 중인 클라이언트 수" tone="green" />
          <AdminStatCard id="inflight-requests" title="처리 중 요청" value={fmtAdminNumber(metrics?.inFlightRequests)} hint={`누적 요청 ${fmtAdminNumber(requestTotals.total)} · 오류율 ${fmtAdminPercent(requestTotals.errorRate)}`} tone="purple" />
          <AdminStatCard id="ai-success-rate" hintId="ai-summary" title="AI 성공률" value={fmtAdminPercent(aiTotals.successRate)} hint={`호출 ${fmtAdminNumber(aiTotals.calls)} · 평균 지연 ${fmtAdminNumber(aiTotals.avgLatencyMs)}ms · 처리 중 ${fmtAdminNumber(metrics?.ai?.inFlight)}`} tone="orange" />
        </section>

        <section className="admin-chart-grid">
          <AdminChartCard title="접속 추이" legend={[{ label: "활성 사용자", color: "#2563eb" }, { label: "활성 클라이언트", color: "#16a34a" }]}>
            <AdminLineChart id="users-chart" labels={userTimeline.labels || []} series={[
              { label: "활성 사용자", values: userTimeline.activeUsers || [], color: "#2563eb" },
              { label: "활성 클라이언트", values: userTimeline.activeClients || [], color: "#16a34a" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="분당 AI 사용량" legend={[{ label: "전체 호출", color: "#7c3aed" }, { label: "성공", color: "#16a34a" }, { label: "실패", color: "#dc2626" }]}>
            <AdminBarChart id="ai-usage-chart" labels={aiTimeline.labels || []} series={[
              { label: "전체 호출", values: aiTimeline.calls || [], color: "#7c3aed" },
              { label: "성공", values: aiTimeline.success || [], color: "#16a34a" },
              { label: "실패", values: aiTimeline.failure || [], color: "#dc2626" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="AI 평균 지연 시간 (ms)" legend={[{ label: "평균 지연", color: "#c37d12" }]}>
            <AdminLineChart id="ai-latency-chart" labels={aiTimeline.labels || []} series={[
              { label: "평균 지연", values: aiTimeline.avgLatencyMs || [], color: "#c37d12" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="요청 및 오류 추이" legend={[{ label: "요청 수", color: "#2563eb" }, { label: "오류 수", color: "#dc2626" }]}>
            <AdminLineChart id="request-chart" labels={requestTimeline.labels || []} series={[
              { label: "요청 수", values: requestTimeline.calls || [], color: "#2563eb" },
              { label: "오류 수", values: requestTimeline.errors || [], color: "#dc2626" },
            ]} />
          </AdminChartCard>
        </section>

        <section className="admin-summary-grid">
          <ContentSummaryPanel summary={metrics?.admin?.contentSummary || {}} />
          <OpsEventsPanel summary={metrics?.admin?.opsEvents || {}} />
        </section>
        <PlatformModesPanel platformModes={metrics?.platformModes || {}} />

        <section id="status-box" className={`status-row ${statusLevel}`}>
          <strong>상태:</strong>
          <span id="status-text">{status}</span>
        </section>
      </main>
    </section>
  );
}

function FeedbackPanel({ feedback, prefix }) {
  const body = feedback?.feedback || feedback;
  return (
    <section className="card dashboard-panel feedback-panel" hidden={!feedback}>
      <strong id={`${prefix}-score`}>{body?.score ?? "-"}</strong>
      <p id={`${prefix}-verdict`}>{body?.correct || feedback?.correct ? "정답" : "검토 필요"}</p>
      <p id={`${prefix}-summary`}>{body?.summary || ""}</p>
      <p id="model-answer-text">{feedback?.model_answer || feedback?.modelAnswer || ""}</p>
    </section>
  );
}

function List({ id, items }) {
  return <ul id={id}>{(items || []).map((item) => <li key={String(item)}>{String(item)}</li>)}</ul>;
}

function App() {
  const path = normalizePath();
  const advancedConfig = ADVANCED_CONFIG[path];

  useEffect(() => {
    document.body.dataset.templateVariant = path === "/admin.html" ? "responsive" : variantFromUserAgent();
    document.body.dataset.reactFrontend = "true";
  }, [path]);

  if (path === "/index.html") return <LoginPage />;
  if (path === "/dashboard.html") return <DashboardPage />;
  if (path === "/profile.html") return <ProfilePage />;
  if (path === "/analysis.html") return <AnalysisPage />;
  if (path === "/codeblock.html") return <CodeBlockPage />;
  if (path === "/arrange.html") return <ArrangePage />;
  if (path === "/auditor.html") return <ReportModePage kind="auditor" />;
  if (path === "/refactoring-choice.html") return <ReportModePage kind="refactoring-choice" />;
  if (path === "/code-blame.html") return <ReportModePage kind="code-blame" />;
  if (advancedConfig) return <AdvancedAnalysisPage config={advancedConfig} />;
  if (path === "/admin.html") return <AdminPage />;
  return <LoginPage />;
}

export default App;
