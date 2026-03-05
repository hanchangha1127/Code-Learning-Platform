const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
const LANGUAGE_KEY = "code-learning-language";
const DIFFICULTY_KEY = "code-learning-difficulty";
const DEFAULT_LANGUAGE = "python";
const DEFAULT_DIFFICULTY = "beginner";
const DEFAULT_TOAST_DURATION = 3200;

const DIFFICULTY_OPTIONS = new Set(["beginner", "intermediate", "advanced"]);
const DIFFICULTY_LABELS = {
  beginner: "초급",
  intermediate: "중급",
  advanced: "고급",
};
const INFERENCE_TYPE_LABELS = {
  pre_condition: "실행 전 추론",
  post_condition: "실행 후 추론",
};

const state = {
  token: null,
  username: "",
  languages: [],
  languageMap: {},
  selectedLanguage: DEFAULT_LANGUAGE,
  selectedDifficulty: DEFAULT_DIFFICULTY,
  currentProblemId: null,
  toastTimer: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리에 실패했습니다.",
});

const elements = {};

function cacheDom() {
  elements.userDisplay = document.getElementById("ci-user-display");
  elements.languageDisplay = document.getElementById("ci-language-display");
  elements.difficultyDisplay = document.getElementById("ci-difficulty-display");
  elements.loadBtn = document.getElementById("ci-load-btn");
  elements.loadStatus = document.getElementById("ci-load-status");
  elements.problemTitle = document.getElementById("ci-problem-title");
  elements.problemSnippet = document.getElementById("ci-problem-snippet");
  elements.problemPrompt = document.getElementById("ci-problem-prompt");
  elements.problemLanguage = document.getElementById("ci-problem-language");
  elements.problemDifficulty = document.getElementById("ci-problem-difficulty");
  elements.problemType = document.getElementById("ci-problem-type");
  elements.reportForm = document.getElementById("ci-report-form");
  elements.reportText = document.getElementById("ci-report-text");
  elements.score = document.getElementById("ci-score");
  elements.verdict = document.getElementById("ci-verdict");
  elements.thresholdText = document.getElementById("ci-threshold-text");
  elements.feedbackSummary = document.getElementById("ci-feedback-summary");
  elements.strengths = document.getElementById("ci-strengths");
  elements.improvements = document.getElementById("ci-improvements");
  elements.foundTypes = document.getElementById("ci-found-types");
  elements.missedTypes = document.getElementById("ci-missed-types");
  elements.referenceReport = document.getElementById("ci-reference-report");
  elements.toast = document.getElementById("ci-toast");
}

function init() {
  cacheDom();
  state.token = window.localStorage.getItem(TOKEN_KEY);
  if (!state.token) {
    window.location.href = "/index.html";
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
  bootstrapWorkspace();
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
    const payload = await apiRequest("/api/languages");
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
        ? "문제 받기를 눌러 맥락 추론 문제를 생성하세요."
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

async function handleLoadProblem() {
  if (!state.selectedLanguage) {
    showToast("언어 정보가 없어 문제를 만들 수 없습니다.");
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  state.selectedDifficulty = getSavedDifficulty();
  renderLanguageDifficulty();

  setLoadingState(elements.loadBtn, true, "문제 생성 중...");
  if (elements.loadStatus) {
    elements.loadStatus.textContent = "AI가 맥락 추론 문제를 생성하고 있습니다.";
  }

  try {
    const payload = await apiRequest("/api/context-inference/problem", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        difficulty: state.selectedDifficulty,
      },
    });
    renderProblem(payload);
    clearFeedback();
    showToast("맥락 추론 문제를 불러왔습니다.");
  } catch (error) {
    showToast(error.message || "문제 생성에 실패했습니다. 다시 시도해 주세요.");
  } finally {
    if (elements.loadStatus) {
      elements.loadStatus.textContent = "새 문제가 필요하면 다시 문제 받기를 눌러주세요.";
    }
    setLoadingState(elements.loadBtn, false);
  }
}

function renderProblem(problem) {
  state.currentProblemId = problem.problemId || null;
  const inferenceType = problem.inferenceType || "pre_condition";
  const typeLabel = INFERENCE_TYPE_LABELS[inferenceType] || inferenceType;

  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title || "맥락 추론 문제";
  }
  if (elements.problemSnippet) {
    elements.problemSnippet.textContent = problem.snippet || "// 문제 코드가 비어 있습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = problem.prompt || "코드 맥락을 추론해 리포트를 작성하세요.";
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
  if (elements.problemType) {
    elements.problemType.textContent = `타입 ${typeLabel}`;
    elements.problemType.dataset.type = inferenceType;
  }
  elements.reportForm?.reset();
}

function clearProblem() {
  state.currentProblemId = null;
  if (elements.problemTitle) {
    elements.problemTitle.textContent = "문제를 불러오면 추론 리포트를 작성할 수 있습니다.";
  }
  if (elements.problemSnippet) {
    elements.problemSnippet.textContent = "// 아직 불러온 문제가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = "문제를 받은 뒤 추론 리포트를 자유롭게 작성하세요.";
  }
  if (elements.problemLanguage) {
    elements.problemLanguage.textContent = "언어 -";
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = "난이도 -";
  }
  if (elements.problemType) {
    elements.problemType.textContent = "타입 -";
    delete elements.problemType.dataset.type;
  }
}

async function handleSubmitReport(event) {
  event.preventDefault();
  if (!state.currentProblemId) {
    showToast("먼저 문제를 생성해 주세요.");
    return;
  }

  const report = (elements.reportText?.value || "").trim();
  if (!report) {
    showToast("추론 리포트를 입력해 주세요.");
    return;
  }

  const submitBtn = elements.reportForm?.querySelector("button[type='submit']");
  setLoadingState(submitBtn, true, "채점 중...");

  try {
    const payload = await apiRequest("/api/context-inference/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        report,
      },
    });
    renderFeedback(payload);
    showToast("채점이 완료되었습니다.");
  } catch (error) {
    showToast(error.message || "채점에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    setLoadingState(submitBtn, false);
  }
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
    elements.feedbackSummary.textContent = feedback.summary || "요약 정보가 없습니다.";
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
    elements.feedbackSummary.textContent = "리포트를 제출하면 AI가 요약을 제공합니다.";
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
