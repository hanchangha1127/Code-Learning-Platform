import { useCallback, useEffect, useRef, useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";
import ProblemBankPage from "./pages/ProblemBank.jsx";
import AdminPage from "./pages/Admin.jsx";
import { AppShell, LoadingScreen } from "./components/AppShell.jsx";
import { BrandIcon } from "./components/SvgIcon.jsx";
import {
  apiRequest,
  authHeaders,
  errorMessageFromPayload,
  isEventStreamResponse,
  readJson,
  saveSession,
  useSessionGuard,
  verifySession,
} from "./lib/apiClient.js";
import { displayModeLabel } from "./lib/modeLabels.js";
import {
  languageTitle,
  normalizeLanguageId,
  normalizeProfileSettings,
  normalizeRuntimeDifficulty,
  persistLearningSettings,
  readStoredRuntimeSettings,
} from "./lib/learningSettings.js";

const SUBMITTING_MESSAGE = "제출했습니다. 피드백을 불러오는 중입니다.";
const SUBMITTED_MESSAGE = "제출 완료. 아래 피드백을 확인하세요.";
const SUBMIT_FAILED_MESSAGE = "제출에 실패했습니다.";
const STREAM_INITIAL_STATUS = "문제 생성을 시작했습니다.";
const STREAM_FALLBACK_STATUS = "스트리밍을 사용할 수 없어 일반 요청으로 전환합니다.";
const STREAM_LATE_ERROR_STATUS = "문제는 표시되었지만 저장 확인 중 오류가 발생했습니다.";

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

const PATH_ALIASES = {
  "/index": "/index.html",
  "/login": "/index.html",
  "/dashboard": "/dashboard.html",
  "/profile": "/profile.html",
  "/problems": "/problems.html",
  "/analysis": "/analysis.html",
  "/codeblock": "/codeblock.html",
  "/code-block": "/codeblock.html",
  "/arrange": "/arrange.html",
  "/auditor": "/auditor.html",
  "/refactoring-choice": "/refactoring-choice.html",
  "/code-blame": "/code-blame.html",
  "/single-file-analysis": "/single-file-analysis.html",
  "/multi-file-analysis": "/multi-file-analysis.html",
  "/fullstack-analysis": "/fullstack-analysis.html",
  "/admin": "/admin.html",
};

function normalizePath() {
  const path = window.location.pathname || "/";
  if (path === "/" || path === "/app.html") return "/dashboard.html";
  return PATH_ALIASES[path] || path;
}

function submitButtonClass(submitting) {
  return `primary submit-button ${submitting ? "is-submitting" : ""}`.trim();
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
  const firstReviewItem = Array.isArray(state.home?.reviewQueue?.items) ? state.home.reviewQueue.items[0] : null;
  const reviewResumeLink = firstReviewItem?.resumeLink || firstReviewItem?.actionLink || "/analysis.html";

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
            <a id="profile-review-link" className="ghost" href={reviewResumeLink}>복습 이어가기</a>
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

function normalizeProblemPayload(payload) {
  return payload?.problem || payload;
}

function isProblemFinal(problem) {
  if (!problem || problem.__streaming) return false;
  return Boolean(problem.problemId || problem.problem_id || problem.id);
}

function streamButtonClass(loading) {
  return `primary ${loading ? "is-streaming" : ""}`.trim();
}

function useStreamAbortRef() {
  const ref = useRef(null);
  useEffect(() => () => {
    if (ref.current) ref.current.abort();
  }, []);
  return ref;
}

function createStreamController(ref) {
  if (ref.current) ref.current.abort();
  const controller = new AbortController();
  ref.current = controller;
  return controller;
}

function clearStreamController(ref, controller) {
  if (ref.current === controller) ref.current = null;
}

function decodeJsonString(value) {
  try {
    return JSON.parse(`"${String(value || "")}"`);
  } catch {
    return String(value || "").replace(/\\"/g, '"').replace(/\\n/g, "\n").replace(/\\\\/g, "\\");
  }
}

function extractStringField(raw, names) {
  for (const name of names) {
    const pattern = new RegExp(`"${name}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`, "s");
    const match = pattern.exec(raw);
    if (match?.[1]) return decodeJsonString(match[1]);
  }
  return "";
}

function stripJsonFences(raw) {
  return String(raw || "").replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
}

function tryParseJsonObject(raw) {
  const text = stripJsonFences(raw);
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(text.slice(start, end + 1));
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function copyDraftArray(target, source, key) {
  if (Array.isArray(source?.[key])) target[key] = source[key];
}

function parseStreamingProblemDraft(raw, mode) {
  const text = String(raw || "");
  if (!text.trim()) return null;
  const parsed = tryParseJsonObject(text);
  const source = parsed ? normalizeProblemPayload(parsed) : {};
  const draft = { __streaming: true, mode };
  const fieldMap = {
    title: ["title"],
    code: ["code"],
    prompt: ["prompt"],
    objective: ["objective"],
    summary: ["summary"],
    scenario: ["scenario"],
    description: ["description"],
    workspace: ["workspace"],
    errorLog: ["errorLog", "error_log"],
    language: ["language", "languageId", "language_id"],
    difficulty: ["difficulty"],
  };
  Object.entries(fieldMap).forEach(([targetKey, names]) => {
    const parsedValue = names.map((name) => source?.[name]).find((value) => typeof value === "string" && value.trim());
    const value = parsedValue || extractStringField(text, names);
    if (value) draft[targetKey] = value;
  });
  ["options", "constraints", "commits", "checklist", "files", "blocks"].forEach((key) => copyDraftArray(draft, source, key));
  return Object.keys(draft).length > 2 ? draft : null;
}

function makeStreamingHandlers({ mode, setProblem, setStatus, onFinalPayload, onDraft }) {
  let raw = "";
  return {
    onStatus(event) {
      if (event?.message) setStatus(event.message);
    },
    onPartial(event) {
      const delta = event?.delta ?? event?.text ?? event?.raw ?? "";
      if (!delta) return;
      raw += String(delta);
      const draft = parseStreamingProblemDraft(raw, mode);
      if (!draft) return;
      if (onDraft) onDraft(draft);
      else setProblem(draft);
    },
    onPayload(payload) {
      const finalProblem = normalizeProblemPayload(payload);
      if (onFinalPayload) onFinalPayload(finalProblem, payload);
      else setProblem(finalProblem);
    },
    onError(error, context) {
      if (context?.payloadSeen) {
        setStatus(errorMessageFromPayload(error, STREAM_LATE_ERROR_STATUS));
      }
    },
    onDone(event) {
      if (event?.ok === true) setStatus("");
    },
  };
}

async function loadStreamedProblem({
  path,
  body,
  mode,
  abortRef,
  setProblem,
  setStatus,
  setLoading,
  onDraft,
  onFinalPayload,
}) {
  const controller = createStreamController(abortRef);
  setLoading(true);
  setStatus(STREAM_INITIAL_STATUS);
  try {
    const handlers = makeStreamingHandlers({ mode, setProblem, setStatus, onFinalPayload, onDraft });
    const payload = await streamProblem(path, body, { ...handlers, signal: controller.signal });
    const finalProblem = normalizeProblemPayload(payload);
    if (!finalProblem) throw new Error("문제를 불러오지 못했습니다.");
    return finalProblem;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    setProblem(null);
    setStatus(error.message || "문제를 불러오지 못했습니다.");
    return null;
  } finally {
    setLoading(false);
    clearStreamController(abortRef, controller);
  }
}

async function streamProblem(path, body, handlers = {}) {
  let payload;
  let responseStarted = false;
  try {
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
      signal: handlers.signal,
      body: JSON.stringify(body),
    });
    responseStarted = true;
    if (!isEventStreamResponse(response)) {
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(errorMessageFromPayload(data, `요청에 실패했습니다. (${response.status})`));
      }
      handlers.onStatus?.({ message: STREAM_FALLBACK_STATUS });
      payload = data;
      handlers.onPayload?.(payload);
      handlers.onDone?.({ ok: true });
      return payload;
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
        if (event.name === "status") handlers.onStatus?.(event.data);
        if (event.name === "partial") handlers.onPartial?.(event.data);
        if (event.name === "payload") {
          payload = event.data?.payload ?? event.data;
          handlers.onPayload?.(payload);
        }
        if (event.name === "error" && payload === undefined) {
          throw new Error(errorMessageFromPayload(event.data, "스트리밍 처리에 실패했습니다."));
        }
        if (event.name === "error" && payload !== undefined) {
          handlers.onError?.(event.data, { payloadSeen: true });
        }
        if (event.name === "done") handlers.onDone?.(event.data);
      }
    }
    if (payload === undefined) {
      throw new Error(response.ok ? "문제를 불러오지 못했습니다." : `요청에 실패했습니다. (${response.status})`);
    }
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (payload !== undefined) return payload;
    if (responseStarted) throw error;

    handlers.onStatus?.({ message: STREAM_FALLBACK_STATUS });
    payload = await apiRequest(path, { method: "POST", body });
    handlers.onPayload?.(payload);
    handlers.onDone?.({ ok: true });
    return payload;
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

function getResumeReviewId() {
  const value = new URLSearchParams(window.location.search || "").get("resume_review");
  return /^\d+$/.test(String(value || "")) ? value : "";
}

function getBankProblemId() {
  const value = new URLSearchParams(window.location.search || "").get("bank_problem");
  return /^\d+$/.test(String(value || "")) ? value : "";
}

function extractProblemPayload(payload) {
  const root = payload?.problem && typeof payload.problem === "object" ? payload.problem : payload;
  if (!root || typeof root !== "object") return null;
  if (root.problem && typeof root.problem === "object") {
    const { problem, ...rest } = root;
    return { ...problem, ...rest };
  }
  return root;
}

async function fetchReviewResumeProblem(reviewId) {
  const payload = await apiRequest(`/platform/review-queue/${encodeURIComponent(reviewId)}/resume`);
  const problem = extractProblemPayload(payload);
  if (!problem) throw new Error("복습 문제를 불러오지 못했습니다.");
  return problem;
}

async function fetchBankProblem(bankProblemId) {
  const payload = await apiRequest(`/platform/problem-bank/${encodeURIComponent(bankProblemId)}/resume`);
  const problem = extractProblemPayload(payload);
  if (!problem) throw new Error("문제를 불러오지 못했습니다.");
  return problem;
}

function fetchStoredProblem(resumeReviewId, bankProblemId) {
  if (resumeReviewId) return fetchReviewResumeProblem(resumeReviewId);
  if (bankProblemId) return fetchBankProblem(bankProblemId);
  return null;
}

function arrangeBlocksFromProblem(problem) {
  return (problem?.blocks || []).map((block, index) => ({
    id: String(block.id || `block-${index + 1}`),
    code: block.code || block.content || String(block),
  }));
}

function AnalysisPage() {
  const ready = useSessionGuard();
  const settings = useLearningSettings();
  const [problem, setProblem] = useState(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const streamAbortRef = useStreamAbortRef();
  const resumeReviewId = getResumeReviewId();
  const bankProblemId = getBankProblemId();

  useEffect(() => {
    if (!ready || (!resumeReviewId && !bankProblemId)) return undefined;
    let active = true;
    fetchStoredProblem(resumeReviewId, bankProblemId)
      .then((resumedProblem) => {
        if (!active) return;
        setProblem(resumedProblem);
        setAnswer("");
        setFeedback(null);
        setSubmitting(false);
        setLoading(false);
        setStatus("");
      })
      .catch((error) => {
        if (!active) return;
        setProblem(null);
        setStatus(error.message || "복습 문제를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [ready, resumeReviewId, bankProblemId]);

  if (!ready) return <LoadingScreen />;
  const problemReady = isProblemFinal(problem);

  async function loadProblem() {
    if (submitting) return;
    setProblem(null);
    setFeedback(null);
    setAnswer("");
    setSubmitting(false);
    await loadStreamedProblem({
      path: "/platform/analysis/problem",
      body: { language: settings.language, difficulty: settings.difficulty },
      mode: "analysis",
      abortRef: streamAbortRef,
      setProblem,
      setStatus,
      setLoading,
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (!problemReady || submitting) return;
    setSubmitting(true);
    setFeedback(null);
    setStatus(SUBMITTING_MESSAGE);
    try {
      const result = await resolveQueued(await apiRequest("/platform/analysis/submit", {
        method: "POST",
        body: { problemId: problem?.problemId || problem?.id, languageId: problem?.language || settings.language, explanation: answer },
      }));
      setFeedback(result);
      setStatus(SUBMITTED_MESSAGE);
    } catch (error) {
      setStatus(error.message || SUBMIT_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell title="코드 분석">
      <main className="mode-shell">
        <section className="card dashboard-panel quiz-panel">
          <div className="mode-head"><h2 id="problem-title">{problem?.title || "문제를 불러오면 시작할 수 있습니다."}</h2><button id="btn-load-problem" className={streamButtonClass(loading)} onClick={loadProblem} disabled={loading || submitting}>{loading ? "생성 중" : "문제 불러오기"}</button></div>
          <p className="status-line">{status}</p>
          {problem?.__streaming ? <p id="analysis-stream-draft" className="stream-draft-label">생성 중인 문제를 실시간으로 표시하고 있습니다.</p> : null}
          <pre id="problem-code" className="code-block">{problem?.code || problem?.starterCode || "// 불러온 문제가 없습니다."}</pre>
          <p id="problem-prompt">{problem?.prompt || problem?.description || "문제를 불러온 뒤 코드의 동작을 설명하세요."}</p>
          <button id="btn-hint" className="ghost" type="button">힌트</button>
          <form id="answer-form" onSubmit={submit}>
            <textarea id="answer-text" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="코드 동작을 설명하세요." />
            <button className={submitButtonClass(submitting)} type="submit" disabled={!problemReady || submitting}>{submitting ? "제출됨" : "제출"}</button>
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
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const streamAbortRef = useStreamAbortRef();
  const resumeReviewId = getResumeReviewId();
  const bankProblemId = getBankProblemId();

  useEffect(() => {
    if (!ready || (!resumeReviewId && !bankProblemId)) return undefined;
    let active = true;
    fetchStoredProblem(resumeReviewId, bankProblemId)
      .then((resumedProblem) => {
        if (!active) return;
        setProblem(resumedProblem);
        setResult(null);
        setSelectedOption(null);
        setSubmitting(false);
        setLoading(false);
        setStatus("");
      })
      .catch((error) => {
        if (!active) return;
        setProblem(null);
        setStatus(error.message || "복습 문제를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [ready, resumeReviewId, bankProblemId]);

  if (!ready) return <LoadingScreen />;
  const problemReady = isProblemFinal(problem);

  async function loadProblem() {
    if (submitting) return;
    setProblem(null);
    setResult(null);
    setSelectedOption(null);
    setSubmitting(false);
    await loadStreamedProblem({
      path: "/platform/codeblock/problem",
      body: { language: settings.language, difficulty: settings.difficulty },
      mode: "code-block",
      abortRef: streamAbortRef,
      setProblem,
      setStatus,
      setLoading,
    });
  }

  async function submit(index) {
    if (!problemReady || submitting || result) return;
    setSelectedOption(index);
    setResult(null);
    setSubmitting(true);
    setStatus(SUBMITTING_MESSAGE);
    try {
      const payload = await apiRequest("/platform/codeblock/submit", { method: "POST", body: { problemId: problem?.problemId || problem?.id, selectedOption: index } });
      setResult(payload);
      setStatus(SUBMITTED_MESSAGE);
    } catch (error) {
      setStatus(error.message || SUBMIT_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
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
          <div className="mode-head"><h2 id="cb-problem-title">{problem?.title || "코드 블록 문제를 불러오세요."}</h2><button id="cb-load-btn" className={streamButtonClass(loading)} onClick={loadProblem} disabled={loading || submitting}>{loading ? "생성 중" : "불러오기"}</button></div>
          <p id="cb-status" className="status-line">{status}</p>
          {problem?.__streaming ? <p className="stream-draft-label">빈칸 문제를 생성하며 코드와 지시문을 먼저 표시합니다.</p> : null}
          <p id="cb-problem-purpose" className="mode-instruction">{problem?.objective || problem?.summary || problem?.prompt || "빈칸에 들어갈 코드를 선택해 전체 흐름을 완성하세요."}</p>
          <pre id="cb-code-display" className="code-block"><CodeWithBlanks code={problem?.code} /></pre>
          <div id="cb-options-container" className="option-grid cb-options">
            {(problem?.options || []).map((option, index) => (
              <button
                key={`${option}-${index}`}
                className={`ghost cb-option-btn ${optionResultClass(index)} ${submitting && selectedOption === index ? "is-submitting" : ""}`.trim()}
                type="button"
                onClick={() => submit(index)}
                disabled={!problemReady || Boolean(result) || submitting}
                aria-pressed={selectedOption === index}
              >
                {String(option)}
              </button>
            ))}
          </div>
          <p id="cb-result-message">{result ? (result.correct ? "정답입니다" : "다시 시도해 보세요") : ""}</p>
          <p id="cb-explanation">{result?.explanation || result?.feedback?.summary || ""}</p>
          <button id="cb-next-btn" className="ghost" onClick={loadProblem} disabled={loading || submitting}>다음</button>
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
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const streamAbortRef = useStreamAbortRef();
  const resumeReviewId = getResumeReviewId();
  const bankProblemId = getBankProblemId();

  useEffect(() => {
    if (!ready || (!resumeReviewId && !bankProblemId)) return undefined;
    let active = true;
    fetchStoredProblem(resumeReviewId, bankProblemId)
      .then((resumedProblem) => {
        if (!active) return;
        setProblem(resumedProblem);
        setBlocks(arrangeBlocksFromProblem(resumedProblem));
        setResult(null);
        setDraggingId("");
        setSubmitting(false);
        setLoading(false);
        setStatus("");
      })
      .catch((error) => {
        if (!active) return;
        setProblem(null);
        setBlocks([]);
        setStatus(error.message || "복습 문제를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [ready, resumeReviewId, bankProblemId]);

  if (!ready) return <LoadingScreen />;
  const problemReady = isProblemFinal(problem);

  async function loadProblem() {
    if (submitting) return;
    setProblem(null);
    setBlocks([]);
    setResult(null);
    setDraggingId("");
    setSubmitting(false);
    await loadStreamedProblem({
      path: "/platform/arrange/problem",
      body: { language: settings.language, difficulty: settings.difficulty },
      mode: "code-arrange",
      abortRef: streamAbortRef,
      setProblem,
      setStatus,
      setLoading,
      onDraft: (draft) => {
        const safeDraft = { ...draft };
        delete safeDraft.code;
        delete safeDraft.blocks;
        setProblem(safeDraft);
        setBlocks([]);
      },
      onFinalPayload: (finalProblem) => {
        setProblem(finalProblem);
        setBlocks(arrangeBlocksFromProblem(finalProblem));
      },
    });
  }

  async function submit() {
    if (!problemReady || submitting) return;
    setSubmitting(true);
    setResult(null);
    setStatus(SUBMITTING_MESSAGE);
    try {
      const payload = await apiRequest("/platform/arrange/submit", { method: "POST", body: { problemId: problem?.problemId || problem?.id, order: blocks.map((block) => block.id) } });
      setResult(payload);
      setStatus(SUBMITTED_MESSAGE);
    } catch (error) {
      setStatus(error.message || SUBMIT_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
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
          <div className="mode-head"><h2 id="arr-title">{problem?.title || "코드 배치 문제를 불러오세요."}</h2><button id="arr-load-btn" className={streamButtonClass(loading)} onClick={loadProblem} disabled={loading || submitting}>{loading ? "생성 중" : "불러오기"}</button></div>
          <p id="arr-status" className="status-line">{status}</p>
          <p id="arr-problem-prompt" className="mode-instruction">{problem?.prompt || problem?.objective || problem?.description || "섞인 코드 블록을 실행 순서에 맞게 드래그 앤 드롭으로 배치하세요."}</p>
          <p className="status-line">마우스 드래그 앤 드롭 또는 화살표 버튼으로 순서를 바꿀 수 있습니다.</p>
          {problem?.__streaming ? <p id="arr-stream-safe-note" className="stream-draft-label">문제를 생성 중입니다. 완성 코드는 표시하지 않고, 섞인 블록이 준비되면 바로 나타납니다.</p> : null}
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
          <button id="arr-check-btn" className={submitButtonClass(submitting)} onClick={submit} disabled={!problemReady || submitting}>{submitting ? "제출됨" : "확인"}</button>
          <button id="arr-next-btn" className="ghost" onClick={loadProblem} disabled={loading || submitting}>다음</button>
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
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const streamAbortRef = useStreamAbortRef();
  const resumeReviewId = getResumeReviewId();
  const bankProblemId = getBankProblemId();

  useEffect(() => {
    if (!ready || (!resumeReviewId && !bankProblemId)) return undefined;
    let active = true;
    fetchStoredProblem(resumeReviewId, bankProblemId)
      .then((resumedProblem) => {
        if (!active) return;
        setProblem(resumedProblem);
        setReport("");
        setSelected([]);
        setResult(null);
        setSubmitting(false);
        setLoading(false);
        setStatus("");
      })
      .catch((error) => {
        if (!active) return;
        setProblem(null);
        setStatus(error.message || "복습 문제를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [ready, resumeReviewId, bankProblemId]);

  if (!ready) return <LoadingScreen />;
  const problemReady = isProblemFinal(problem);

  async function loadProblem() {
    if (submitting) return;
    setProblem(null);
    setResult(null);
    setSelected([]);
    setSubmitting(false);
    await loadStreamedProblem({
      path: config.problemPath,
      body: { language: settings.language, difficulty: settings.difficulty },
      mode: kind,
      abortRef: streamAbortRef,
      setProblem,
      setStatus,
      setLoading,
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (!problemReady || submitting) return;
    const body = { problemId: problem?.problemId || problem?.id, report };
    if (kind === "refactoring-choice") body.selectedOption = selected[0] || "";
    if (kind === "code-blame") body.selectedCommits = selected;
    setSubmitting(true);
    setResult(null);
    setStatus(SUBMITTING_MESSAGE);
    try {
      const payload = await resolveQueued(await apiRequest(config.submitPath, { method: "POST", body }));
      setResult(payload);
      setStatus(SUBMITTED_MESSAGE);
    } catch (error) {
      setStatus(error.message || SUBMIT_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  const options = problem?.options || problem?.commits || [];
  const loadId = kind === "auditor" ? "auditor-load-btn" : `${config.prefix}-load-btn`;
  const statusId = kind === "auditor" ? "auditor-load-status" : `${config.prefix}-load-status`;

  return (
    <AppShell title={config.title}>
      <main className="mode-shell">
        <section className="card dashboard-panel quiz-panel">
          <div className="mode-head"><h2 id={`${config.prefix}-problem-title`}>{problem?.title || `${config.title} 문제를 불러오세요.`}</h2><button id={loadId} className={streamButtonClass(loading)} onClick={loadProblem} disabled={loading || submitting}>{loading ? "생성 중" : "불러오기"}</button></div>
          <p id={statusId} className="status-line">{status}</p>
          {problem?.__streaming ? <p className="stream-draft-label">문제 본문을 생성되는 순서대로 먼저 표시합니다.</p> : null}
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
                    disabled={!problemReady}
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
            <button id={`${config.prefix}-submit-btn`} className={submitButtonClass(submitting)} type="submit" disabled={!problemReady || submitting}>{submitting ? "제출됨" : "제출"}</button>
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
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const streamAbortRef = useStreamAbortRef();
  const resumeReviewId = getResumeReviewId();
  const bankProblemId = getBankProblemId();

  useEffect(() => {
    document.body.dataset.advancedAnalysisMode = config.mode;
    return () => {
      delete document.body.dataset.advancedAnalysisMode;
    };
  }, [config.mode]);

  useEffect(() => {
    if (!ready || (!resumeReviewId && !bankProblemId)) return undefined;
    let active = true;
    fetchStoredProblem(resumeReviewId, bankProblemId)
      .then((resumedProblem) => {
        if (!active) return;
        setProblem(resumedProblem);
        setActiveFileId((resumedProblem.files || [])[0]?.id || "");
        setReport("");
        setResult(null);
        setSubmitting(false);
        setLoading(false);
        setStatus("");
      })
      .catch((error) => {
        if (!active) return;
        setProblem(null);
        setActiveFileId("");
        setStatus(error.message || "복습 문제를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [ready, resumeReviewId, bankProblemId]);

  if (!ready) return <LoadingScreen />;

  const files = problem?.files || [];
  const activeFile = files.find((file) => file.id === activeFileId) || files[0] || {};
  const activePathParts = pathParts(activeFile);
  const activeLanguage = displayLanguage(fileLanguage(activeFile, settings.language));
  const activeRole = fileRole(activeFile);
  const activeLines = codeLines(activeFile.content);
  const loadedCount = files.length;
  const problemReady = isProblemFinal(problem);

  async function loadProblem() {
    if (submitting) return;
    setProblem(null);
    setActiveFileId("");
    setResult(null);
    setSubmitting(false);
    await loadStreamedProblem({
      path: config.problemPath,
      body: { language: settings.language, difficulty: settings.difficulty },
      mode: config.mode,
      abortRef: streamAbortRef,
      setProblem,
      setStatus,
      setLoading,
      onDraft: (draft) => {
        setProblem(draft);
        if ((draft.files || [])[0]?.id) setActiveFileId(draft.files[0].id);
      },
      onFinalPayload: (finalProblem) => {
        setProblem(finalProblem);
        setActiveFileId((finalProblem.files || [])[0]?.id || "");
      },
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (!problemReady || submitting) return;
    setSubmitting(true);
    setResult(null);
    setStatus(SUBMITTING_MESSAGE);
    try {
      const payload = await resolveQueued(await apiRequest(config.submitPath, { method: "POST", body: { problemId: problem?.problemId || problem?.id, report } }));
      setResult(payload);
      setStatus(SUBMITTED_MESSAGE);
    } catch (error) {
      setStatus(error.message || SUBMIT_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
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
              <button id="advanced-load-btn" className={streamButtonClass(loading)} type="button" onClick={loadProblem} disabled={loading || submitting}>{loading ? "생성 중" : "문제 받기"}</button>
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
                <button id="advanced-submit-btn" className={submitButtonClass(submitting)} type="submit" disabled={!problemReady || submitting}>{submitting ? "제출됨" : "분석 제출"}</button>
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
  if (path === "/problems.html") return <ProblemBankPage />;
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
