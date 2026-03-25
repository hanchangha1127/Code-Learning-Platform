const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const reviewResume = window.CodeReviewResume || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
const LANGUAGE_KEY = "code-learning-language";
const DIFFICULTY_KEY = "code-learning-difficulty";
const DEFAULT_LANGUAGE = "python";
const DEFAULT_DIFFICULTY = "beginner";
const DEFAULT_TOAST_DURATION = 3200;
const MODE_JOB_POLL_INTERVAL = 1200;
const MODE_JOB_MAX_POLL_ATTEMPTS = 60;

const DIFFICULTY_OPTIONS = new Set(["beginner", "intermediate", "advanced"]);
const DIFFICULTY_LABELS = {
  beginner: "초급",
  intermediate: "중급",
  advanced: "고급",
};

const state = {
  token: null,
  username: "",
  languages: [],
  languageMap: {},
  selectedLanguage: DEFAULT_LANGUAGE,
  selectedDifficulty: DEFAULT_DIFFICULTY,
  currentProblemId: null,
  problemStreamController: null,
  toastTimer: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리에 실패했습니다.",
});

const elements = {};

function cacheDom() {
  elements.userDisplay = document.getElementById("auditor-user-display");
  elements.languageDisplay = document.getElementById("auditor-language-display");
  elements.difficultyDisplay = document.getElementById("auditor-difficulty-display");
  elements.loadBtn = document.getElementById("auditor-load-btn");
  elements.loadStatus = document.getElementById("auditor-load-status");
  elements.problemTitle = document.getElementById("auditor-problem-title");
  elements.problemCode = document.getElementById("auditor-problem-code");
  elements.problemPrompt = document.getElementById("auditor-problem-prompt");
  elements.problemLanguage = document.getElementById("auditor-problem-language");
  elements.problemDifficulty = document.getElementById("auditor-problem-difficulty");
  elements.trapCount = document.getElementById("auditor-trap-count");
  elements.reportForm = document.getElementById("auditor-report-form");
  elements.reportText = document.getElementById("auditor-report-text");
  elements.score = document.getElementById("auditor-score");
  elements.verdict = document.getElementById("auditor-verdict");
  elements.thresholdText = document.getElementById("auditor-threshold-text");
  elements.feedbackSummary = document.getElementById("auditor-feedback-summary");
  elements.strengths = document.getElementById("auditor-strengths");
  elements.improvements = document.getElementById("auditor-improvements");
  elements.foundTypes = document.getElementById("auditor-found-types");
  elements.missedTypes = document.getElementById("auditor-missed-types");
  elements.referenceReport = document.getElementById("auditor-reference-report");
  elements.toast = document.getElementById("auditor-toast");
}

async function init() {
  cacheDom();
  if (authClient?.ensureActiveSession) {
    state.token = await authClient.ensureActiveSession({
      token: window.localStorage.getItem(TOKEN_KEY),
      redirectTo: "/index.html",
    });
  } else {
    state.token = window.localStorage.getItem(TOKEN_KEY);
  }
  if (!state.token) {
    return;
  }
  state.selectedDifficulty = getSavedDifficulty();
  state.selectedLanguage = getSavedLanguage();
  state.username = getDisplayName(state.token);
  if (elements.userDisplay) {
    elements.userDisplay.textContent = state.username;
  }

  bindEvents();
  clearProblem();
  clearFeedback();
  await bootstrapWorkspace();
  await tryResumeReview();
}

function bindEvents() {
  elements.loadBtn?.addEventListener("click", handleLoadProblem);
  elements.reportForm?.addEventListener("submit", handleSubmitReport);
}

async function bootstrapWorkspace() {
  if (elements.loadStatus) {
    elements.loadStatus.textContent = "언어 목록을 불러오는 중입니다.";
  }
  try {
    const payload = await apiRequest("/platform/languages");
    state.languages = payload.languages || [];
    state.languageMap = state.languages.reduce((acc, lang) => {
      acc[lang.id] = lang;
      return acc;
    }, {});
    state.selectedLanguage = getSavedLanguage(state.languages);
  } catch (error) {
    state.languages = [];
    state.languageMap = {};
    state.selectedLanguage = getSavedLanguage();
    showToast(error.message || "언어 목록을 불러오지 못했습니다.");
  } finally {
    renderLanguageDifficulty();
    if (elements.loadBtn) {
      elements.loadBtn.disabled = !state.selectedLanguage;
    }
    if (elements.loadStatus) {
      elements.loadStatus.textContent = state.selectedLanguage
        ? "문제 받기를 눌러 감사관 문제를 생성하세요."
        : "언어 설정을 확인하고 다시 시도하세요.";
    }
  }
}

function renderLanguageDifficulty() {
  const langTitle =
    state.languageMap[state.selectedLanguage]?.title || state.selectedLanguage || DEFAULT_LANGUAGE;
  const diffLabel = DIFFICULTY_LABELS[state.selectedDifficulty] || state.selectedDifficulty;

  if (elements.languageDisplay) {
    elements.languageDisplay.textContent = `언어 ${langTitle}`;
  }
  if (elements.difficultyDisplay) {
    elements.difficultyDisplay.textContent = `난이도 ${diffLabel}`;
  }
}

function getProblemStreamClient() {
  return window.CodeProblemStream || null;
}

function getProblemStreamPreviewContainer() {
  return elements.problemCode?.closest(".problem-card") || elements.problemPrompt?.closest(".problem-card") || null;
}

function shouldFallbackToJson(streamError) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.shouldFallbackToJson !== "function") {
    return false;
  }
  return Boolean(streamClient.shouldFallbackToJson(streamError));
}

function applyStreamingAuditorPreview(draft) {
  if (!draft || typeof draft !== "object") {
    return;
  }
  if (typeof draft.title === "string" && draft.title.trim() && elements.problemTitle) {
    elements.problemTitle.textContent = draft.title.trim();
  }
  if (elements.problemLanguage) {
    const languageLabel = state.languageMap[state.selectedLanguage]?.title || state.selectedLanguage || "-";
    elements.problemLanguage.textContent = `언어 ${languageLabel}`;
  }
  if (elements.problemDifficulty) {
    const difficultyLabel = DIFFICULTY_LABELS[state.selectedDifficulty] || state.selectedDifficulty || "-";
    elements.problemDifficulty.textContent = `난이도 ${difficultyLabel}`;
  }
  if (typeof draft.code === "string" && draft.code.length > 0 && elements.problemCode) {
    elements.problemCode.textContent = draft.code;
  }
  if (typeof draft.prompt === "string" && draft.prompt.trim() && elements.problemPrompt) {
    elements.problemPrompt.textContent = draft.prompt.trim();
  }
}


async function loadAuditorProblemViaStream() {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.streamProblem !== "function") {
    return null;
  }

  if (state.problemStreamController) {
    state.problemStreamController.abort();
  }
  state.problemStreamController = new AbortController();

  try {
    return await streamClient.streamProblem({
      path: "/platform/auditor/problem",
      token: state.token,
      body: {
        language: state.selectedLanguage,
        difficulty: state.selectedDifficulty,
      },
      onStatus: (statusPayload) => {
        if (!elements.loadStatus) return;
        elements.loadStatus.textContent = statusPayload?.message || elements.loadStatus.textContent;
        if (statusPayload?.phase === "rendering") {
          setLoadingState(elements.loadBtn, true, "문제 표시 중...");
        }
      },
      showPartialPreview: false,
      onPreview: (draft) => {
        applyStreamingAuditorPreview(draft);
      },
      signal: state.problemStreamController.signal,
    });
  } finally {
    state.problemStreamController = null;
  }
}

async function animateAuditorProblem(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    renderProblem(problem);
    return;
  }

  const languageId = problem.language || state.selectedLanguage;
  const languageLabel = state.languageMap[languageId]?.title || languageId || "-";
  const difficultyId = problem.difficulty || state.selectedDifficulty;
  const difficultyLabel = DIFFICULTY_LABELS[difficultyId] || difficultyId || "-";

  if (elements.problemTitle) {
    await streamClient.typeText(elements.problemTitle, problem.title || "감사관 문제", { minDelay: 10, maxDelay: 16 });
  }
  if (elements.problemLanguage) {
    await streamClient.typeText(elements.problemLanguage, `언어 ${languageLabel}`, { minDelay: 10, maxDelay: 16 });
  }
  if (elements.problemDifficulty) {
    await streamClient.typeText(elements.problemDifficulty, `난이도 ${difficultyLabel}`, { minDelay: 10, maxDelay: 16 });
  }
  if (elements.trapCount) {
    await streamClient.typeText(elements.trapCount, `함정 ${problem.trapCount ?? "-"}`, { minDelay: 10, maxDelay: 16 });
  }
  if (elements.problemCode) {
    await streamClient.revealLines(elements.problemCode, problem.code || "// 문제 코드가 비어 있습니다.", {
      lineDelay: 70,
    });
  }
  if (elements.problemPrompt) {
    await streamClient.typeText(elements.problemPrompt, problem.prompt || "코드를 감사하고 리포트를 작성하세요.", {
      minDelay: 10,
      maxDelay: 16,
    });
  }

  renderProblem(problem);
}

async function handleLoadProblem() {
  if (!state.selectedLanguage) {
    showToast("언어 정보가 없어 문제를 만들 수 없습니다.");
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  state.selectedDifficulty = getSavedDifficulty();
  renderLanguageDifficulty();

  setLoadingState(elements.loadBtn, true, "문제 생성 중...");
  clearProblem();
  clearFeedback();
  if (elements.loadStatus) {
    elements.loadStatus.textContent = "AI가 감사관 문제를 생성하고 있습니다.";
  }
  let loadSucceeded = false;

  try {
    const streamClient = getProblemStreamClient();
    const { payload, streamed, usedJsonFallback } = await streamClient.loadProblemTransport({
      streamClient,
      streamRequest: loadAuditorProblemViaStream,
      jsonRequest: async () => {
        if (elements.loadStatus) {
          elements.loadStatus.textContent = "스트리밍 연결이 끊겨 일반 모드로 재시도 중...";
        }
        setLoadingState(elements.loadBtn, true, "일반 모드 재시도 중...");
        return apiRequest("/platform/auditor/problem", {
          method: "POST",
          body: {
            language: state.selectedLanguage,
            difficulty: state.selectedDifficulty,
          },
        });
      },
      shouldFallback: shouldFallbackToJson,
    });
    if (!payload) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    if (streamed) {
      renderProblem(payload);
    } else if (usedJsonFallback) {
      await animateAuditorProblem(payload);
    } else {
      renderProblem(payload);
    }

    clearFeedback();
    loadSucceeded = true;
    showToast("감사관 문제를 불러왔습니다.");
  } catch (error) {
    clearProblem();
    clearFeedback();
    showToast(error.message || "문제 생성에 실패했습니다. 다시 시도해 주세요.");
  } finally {
    if (elements.loadStatus) {
      elements.loadStatus.textContent = loadSucceeded
        ? "다른 문제가 필요하면 다시 문제 받기를 눌러주세요."
        : "문제 생성에 실패했습니다. 다시 시도해 주세요.";
    }
    setLoadingState(elements.loadBtn, false);
  }
}

function renderProblem(problem) {
  state.currentProblemId = problem.problemId || null;
  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title || "감사관 문제";
  }
  if (elements.problemCode) {
    elements.problemCode.textContent = problem.code || "// 문제 코드가 비어 있습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = problem.prompt || "코드를 감사하고 리포트를 작성하세요.";
  }
  if (elements.problemLanguage) {
    const languageId = problem.language || state.selectedLanguage;
    const languageLabel = state.languageMap[languageId]?.title || languageId || "-";
    elements.problemLanguage.textContent = `언어 ${languageLabel}`;
  }
  if (elements.problemDifficulty) {
    const difficultyId = problem.difficulty || state.selectedDifficulty;
    const difficultyLabel = DIFFICULTY_LABELS[difficultyId] || difficultyId || "-";
    elements.problemDifficulty.textContent = `난이도 ${difficultyLabel}`;
  }
  if (elements.trapCount) {
    elements.trapCount.textContent = `함정 ${problem.trapCount ?? "-"}`;
  }
  elements.reportForm?.reset();
}

function clearProblem() {
  state.currentProblemId = null;
  if (elements.problemTitle) {
    elements.problemTitle.textContent = "문제를 불러오면 감사 리포트를 작성할 수 있습니다.";
  }
  if (elements.problemCode) {
    elements.problemCode.textContent = "// 아직 불러온 문제가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = "문제를 받은 뒤 감사 리포트를 자유롭게 작성하세요.";
  }
  if (elements.problemLanguage) {
    elements.problemLanguage.textContent = "언어 -";
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = "난이도 -";
  }
  if (elements.trapCount) {
    elements.trapCount.textContent = "함정 -";
  }
  elements.reportForm?.reset();
}

async function handleSubmitReport(event) {
  event.preventDefault();
  if (!state.currentProblemId) {
    showToast("먼저 문제를 생성해 주세요.");
    return;
  }

  const report = (elements.reportText?.value || "").trim();
  if (!report) {
    showToast("감사 리포트를 입력해 주세요.");
    return;
  }

  const submitBtn = elements.reportForm?.querySelector("button[type='submit']");
  setLoadingState(submitBtn, true, "채점 중...");

  try {
    let payload = await apiRequest("/platform/auditor/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        report,
      },
    });
    if (payload?.queued && payload?.jobId) {
      if (elements.feedbackSummary) {
        elements.feedbackSummary.textContent = "AI가 감사 리포트를 채점하는 중입니다.";
      }
      showToast("AI 피드백 요청이 접수되었습니다.");
      payload = await pollSubmitJob(payload.jobId);
    }
    renderFeedback(payload);
    showToast(isFallbackFeedback(payload) ? "기본 피드백으로 결과를 표시했습니다." : "AI 피드백이 완료되었습니다.");
  } catch (error) {
    showToast(error.message || "채점에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    setLoadingState(submitBtn, false);
  }
}

async function pollSubmitJob(jobId) {
  const normalizedJobId = String(jobId || "").trim();
  if (!normalizedJobId) {
    throw new Error("채점 작업 정보를 확인하지 못했습니다.");
  }

  for (let attempt = 0; attempt < MODE_JOB_MAX_POLL_ATTEMPTS; attempt += 1) {
    const payload = await apiRequest(`/platform/mode-jobs/${encodeURIComponent(normalizedJobId)}`);
    if (payload?.finished) {
      return payload.result || {};
    }
    if (payload?.failed) {
      throw new Error(payload.error || "채점 작업이 실패했습니다.");
    }
    await waitForNextPoll();
  }

  throw new Error("채점 결과를 불러오는 데 시간이 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요.");
}

function waitForNextPoll() {
  return new Promise((resolve) => {
    window.setTimeout(resolve, MODE_JOB_POLL_INTERVAL);
  });
}

function renderFeedback(payload) {
  const score = Number(payload.score);
  const hasScore = Number.isFinite(score);
  const verdict = payload.verdict || (payload.correct ? "passed" : "failed");
  const threshold = Number(payload.passThreshold ?? 70);
  const feedback = payload.feedback || {};
  const foundTypes = Array.isArray(payload.foundTypes) ? payload.foundTypes : [];
  const missedTypes = Array.isArray(payload.missedTypes) ? payload.missedTypes : [];

  if (elements.score) {
    elements.score.textContent = hasScore ? `${Math.round(score)}점` : "점수 없음";
  }
  if (elements.verdict) {
    if (verdict === "passed") {
      elements.verdict.textContent = "합격";
      elements.verdict.dataset.state = "success";
    } else if (verdict === "failed") {
      elements.verdict.textContent = "불합격";
      elements.verdict.dataset.state = "danger";
    } else {
      elements.verdict.textContent = "판정 대기";
      elements.verdict.dataset.state = "neutral";
    }
  }
  if (elements.thresholdText) {
    elements.thresholdText.textContent = `합격 기준: ${Number.isFinite(threshold) ? threshold : 70}점`;
  }
  if (elements.feedbackSummary) {
    elements.feedbackSummary.textContent = formatFeedbackSummary(payload, feedback.summary, "AI 피드백 요약이 없습니다.");
  }
  renderList(elements.strengths, feedback.strengths, "강점이 없습니다.");
  renderList(elements.improvements, feedback.improvements, "개선 포인트가 없습니다.");

  if (elements.foundTypes) {
    elements.foundTypes.textContent = foundTypes.length ? foundTypes.join(", ") : "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = missedTypes.length ? missedTypes.join(", ") : "-";
  }
  if (elements.referenceReport) {
    elements.referenceReport.textContent = payload.referenceReport || "모범 리포트가 제공되지 않았습니다.";
  }
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "auditor",
    apiRequest,
    applyProblem: async (problem) => {
      renderProblem(problem);
      clearFeedback();
      if (elements.loadStatus) {
        elements.loadStatus.textContent = "같은 문제를 다시 열었습니다. 감사 리포트를 다시 작성해 보세요.";
      }
    },
    onError: (error) => {
      showToast(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
}

function clearFeedback() {
  if (elements.score) {
    elements.score.textContent = "점수 대기";
  }
  if (elements.verdict) {
    elements.verdict.textContent = "판정 대기";
    elements.verdict.dataset.state = "neutral";
  }
  if (elements.thresholdText) {
    elements.thresholdText.textContent = "합격 기준: 70점";
  }
  if (elements.feedbackSummary) {
    elements.feedbackSummary.textContent = "리포트를 제출하면 AI 피드백이 여기에 표시됩니다.";
  }
  renderList(elements.strengths, [], "강점이 없습니다.");
  renderList(elements.improvements, [], "개선 포인트가 없습니다.");
  if (elements.foundTypes) {
    elements.foundTypes.textContent = "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = "-";
  }
  if (elements.referenceReport) {
    elements.referenceReport.textContent = "제출 후 항상 공개됩니다.";
  }
}

function renderList(target, items, emptyText) {
  if (!target) return;
  target.innerHTML = "";
  const normalized = Array.isArray(items)
    ? items.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];
  if (normalized.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = emptyText;
    target.appendChild(li);
    return;
  }
  normalized.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    target.appendChild(li);
  });
}

function getFeedbackSource(payload) {
  return String(payload?.feedbackSource || "").trim().toLowerCase() || "ai";
}

function isFallbackFeedback(payload) {
  return getFeedbackSource(payload) === "fallback";
}

function formatFeedbackSummary(payload, summary, emptyText) {
  const normalized = String(summary || "").trim();
  if (!normalized) {
    return isFallbackFeedback(payload) ? "기본 피드백 요약이 없습니다." : emptyText;
  }
  return isFallbackFeedback(payload) ? `기본 피드백: ${normalized}` : normalized;
}

function setLoadingState(button, isLoading, label) {
  if (!button) return;
  if (isLoading) {
    button.disabled = true;
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent || "";
    }
    if (label) {
      button.textContent = label;
    }
  } else {
    button.disabled = false;
    if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
      delete button.dataset.originalText;
    }
  }
}

function showToast(message) {
  if (!elements.toast) return;
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  elements.toast.classList.add("visible");
  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }
  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
    elements.toast.classList.add("hidden");
  }, DEFAULT_TOAST_DURATION);
}

function getSavedLanguage(languages = null) {
  const saved = window.localStorage.getItem(LANGUAGE_KEY);
  if (Array.isArray(languages) && languages.length > 0) {
    if (saved && languages.some((lang) => lang.id === saved)) {
      return saved;
    }
    const fallback = languages[0]?.id || DEFAULT_LANGUAGE;
    window.localStorage.setItem(LANGUAGE_KEY, fallback);
    return fallback;
  }
  return saved || DEFAULT_LANGUAGE;
}

function getSavedDifficulty() {
  const saved = window.localStorage.getItem(DIFFICULTY_KEY);
  if (saved && DIFFICULTY_OPTIONS.has(saved)) {
    return saved;
  }
  return DEFAULT_DIFFICULTY;
}

function parseUsername(token) {
  if (authClient) {
    return authClient.parseUsername(token);
  }
  if (!token) return "";
  return token.split(":", 1)[0];
}

function getDisplayName(token) {
  const cached = window.localStorage.getItem(DISPLAY_NAME_KEY);
  return cached || parseUsername(token);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}




