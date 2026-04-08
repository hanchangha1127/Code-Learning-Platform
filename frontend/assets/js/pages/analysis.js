const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const reviewResume = window.CodeReviewResume || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
const DEFAULT_TOAST_DURATION = 3200;
const LANGUAGE_KEY = "code-learning-language";
const DEFAULT_LANGUAGE = "python";
const DIFFICULTY_KEY = "code-learning-difficulty";
const DEFAULT_DIFFICULTY = "beginner";
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
  selectedLanguage: null,
  selectedDifficulty: DEFAULT_DIFFICULTY,
  currentProblem: null,
  problemStreamController: null,
  toastTimer: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청을 처리하지 못했습니다.",
});


const elements = {};

function cacheDom() {
  elements.profileStatus = document.getElementById("profile-status");
  elements.diagnosticStatus = document.getElementById("diagnostic-status");
  elements.statsAttempts = document.getElementById("stats-attempts");
  elements.statsAccuracy = document.getElementById("stats-accuracy");
  elements.activeUser = document.getElementById("active-user");
  elements.selectedLanguage = document.getElementById("selected-language");
  elements.selectedDifficulty = document.getElementById("selected-difficulty");
  elements.loadProblemBtn = document.getElementById("btn-load-problem");
  elements.problemMode = document.getElementById("problem-mode");
  elements.problemTitle = document.getElementById("problem-title");
  elements.problemDifficulty = document.getElementById("problem-difficulty");
  elements.problemTrack = document.getElementById("problem-track");
  elements.problemLanguage = document.getElementById("problem-language");
  elements.problemCode = document.getElementById("problem-code");
  elements.problemPrompt = document.getElementById("problem-prompt");
  elements.hintBtn = document.getElementById("btn-hint");
  elements.hintText = document.getElementById("hint-text");
  elements.answerForm = document.getElementById("answer-form");
  elements.feedbackSummary = document.getElementById("feedback-summary");
  elements.feedbackStrengths = document.getElementById("feedback-strengths");
  elements.feedbackImprovements = document.getElementById("feedback-improvements");
  elements.feedbackScore = document.getElementById("feedback-score");
  elements.feedbackVerdict = document.getElementById("feedback-verdict");
  elements.toast = document.getElementById("toast");
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
  }  state.selectedDifficulty = getSavedDifficulty();
  state.selectedLanguage = getSavedLanguage();
  state.username = getDisplayName(state.token);
  if (elements.activeUser) elements.activeUser.textContent = state.username;
  renderDifficulty();
  bindEvents();
  await bootstrapWorkspace();
  resetProblemView();
  clearFeedback();
  await tryResumeReview();
}

function bindEvents() {
  elements.loadProblemBtn?.addEventListener("click", handleLoadProblem);
  elements.hintBtn?.addEventListener("click", handleHint);
  elements.answerForm?.addEventListener("submit", handleAnswerSubmit);
}

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTY_OPTIONS.has(value) ? value : DEFAULT_DIFFICULTY;
}

function formatDifficultyLabel(value) {
  return DIFFICULTY_LABELS[value] || value || "-";
}

function renderDifficulty() {
  state.selectedDifficulty = getSavedDifficulty();
  const label = formatDifficultyLabel(state.selectedDifficulty);
  if (elements.selectedDifficulty) {
    elements.selectedDifficulty.textContent = `난이도 ${label}`;
  }
}

async function bootstrapWorkspace() {
  let languages = [];
  let profile = null;
  try {
    languages = await fetchLanguages();
  } catch (err) {
    console.error(err);
    state.languages = [];
    state.languageMap = {};
  }
  try {
    profile = await fetchProfile();
  } catch (err) {
    console.error(err);
  }
  renderLanguages(languages);
  if (profile) {
    renderProfile(profile);
  }
  resetProblemView();
  clearFeedback();
  updateLoadButtonState();
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "analysis",
    apiRequest,
    applyProblem: async (problem) => {
      const normalizedProblem = normalizeAnalysisProblem(problem);
      if (!normalizedProblem) {
        throw new Error("복습 문제 데이터가 비어 있습니다.");
      }
      state.currentProblem = normalizedProblem;
      renderProblem(normalizedProblem);
      clearFeedback();
      elements.answerForm?.reset();
    },
    onError: (error) => {
      showToast(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
}

async function fetchLanguages() {
  const payload = await apiRequest("/platform/languages");
  state.languages = payload.languages || [];
  state.languageMap = state.languages.reduce((acc, lang) => {
    acc[lang.id] = lang;
    return acc;
  }, {});
  return state.languages;
}

async function fetchProfile() {
  const profile = await apiRequest("/platform/profile");
  return profile;
}

function renderProfile(profile) {
  if (!profile) return;
  const skillLabel = "맞춤 문제를 바로 풀어보세요.";
  if (elements.profileStatus) {
    elements.profileStatus.textContent = skillLabel;
  }
  if (elements.diagnosticStatus) {
    const remaining = profile.diagnosticRemaining ?? 0;
    const answered = profile.diagnosticAnswered ?? 0;
    const total = profile.diagnosticTotal ?? 0;
    elements.diagnosticStatus.textContent =
      remaining > 0 ? `진단 ${answered}/${total} 진행 중` : "";
  }
  if (elements.statsAttempts) {
    elements.statsAttempts.textContent = profile.totalAttempts ?? 0;
  }
  if (elements.statsAccuracy) {
    const accuracy = profile.accuracy ?? 0;
    elements.statsAccuracy.textContent = `${accuracy}%`;
  }
}

function renderLanguages(languages) {
  state.selectedLanguage = getSavedLanguage(languages);
  const label = state.languageMap[state.selectedLanguage]?.title || state.selectedLanguage || "-";
  if (elements.selectedLanguage) {
    elements.selectedLanguage.textContent = label;
  }
  renderDifficulty();
}

function updateLoadButtonState() {
  const isReady = Boolean(state.selectedLanguage);
  if (elements.loadProblemBtn) {
    elements.loadProblemBtn.disabled = !isReady;
  }
}

function normalizeAnalysisProblem(payload) {
  const source =
    payload && typeof payload === "object" && payload.problem && typeof payload.problem === "object"
      ? payload.problem
      : payload;

  if (!source || typeof source !== "object") {
    return null;
  }

  const problemId =
    source.problemId ||
    source.id ||
    (payload && typeof payload === "object" ? payload.problemId || payload.id : null) ||
    null;

  return {
    ...source,
    problemId,
    id: source.id || problemId,
    title: source.title || (payload && typeof payload === "object" ? payload.title : null) || "",
    code: source.code || (payload && typeof payload === "object" ? payload.code : null) || "",
    prompt: source.prompt || (payload && typeof payload === "object" ? payload.prompt : null) || "",
    mode: source.mode || (payload && typeof payload === "object" ? payload.mode : null) || "analysis",
    difficulty:
      source.difficulty || (payload && typeof payload === "object" ? payload.difficulty : null) || state.selectedDifficulty,
    track: source.track || (payload && typeof payload === "object" ? payload.track : null) || "algorithms",
    language:
      source.language || (payload && typeof payload === "object" ? payload.language : null) || state.selectedLanguage,
  };
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

function isProblemLoadCancelled(error) {
  const streamClient = getProblemStreamClient();
  if (streamClient && typeof streamClient.isAbortError === "function") {
    return Boolean(streamClient.isAbortError(error));
  }
  return error?.code === "STREAM_ABORTED" || error?.name === "AbortError";
}

function applyStreamingProblemPreview(draft) {
  if (!draft || typeof draft !== "object") {
    return;
  }
  if (elements.problemMode) {
    elements.problemMode.textContent = "문제 생성 중";
  }
  if (typeof draft.title === "string" && draft.title.trim()) {
    elements.problemTitle.textContent = draft.title.trim();
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = `난이도 ${state.selectedDifficulty ?? "-"}`;
  }
  if (elements.problemTrack) {
    elements.problemTrack.textContent = "분야 -";
  }
  if (elements.problemLanguage) {
    const languageTitle = state.languageMap[state.selectedLanguage]?.title || state.selectedLanguage || "-";
    elements.problemLanguage.textContent = `언어 ${languageTitle}`;
  }
  if (typeof draft.code === "string" && draft.code.length > 0 && elements.problemCode) {
    elements.problemCode.textContent = draft.code;
  }
  if (typeof draft.prompt === "string" && draft.prompt.trim() && elements.problemPrompt) {
    elements.problemPrompt.textContent = draft.prompt.trim();
  }
}


async function loadProblemViaStream() {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.streamProblem !== "function") {
    return null;
  }

  if (state.problemStreamController) {
    state.problemStreamController.abort();
  }
  const controller = new AbortController();
  state.problemStreamController = controller;

  try {
    return await streamClient.streamProblem({
      path: "/platform/analysis/problem",
      token: state.token,
      body: {
        languageId: state.selectedLanguage,
        difficulty: state.selectedDifficulty,
      },
      returnOnPayload: true,
      onStatus: (statusPayload) => {
        if (statusPayload?.phase === "rendering") {
          setLoadingState(elements.loadProblemBtn, true, "문제 표시 중...");
        }
      },
      showPartialPreview: false,
      onPreview: (draft) => {
        applyStreamingProblemPreview(draft);
      },
      signal: controller.signal,
    });
  } finally {
    if (state.problemStreamController === controller) {
      state.problemStreamController = null;
    }
  }
}

async function animateProblemRender(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    renderProblem(problem);
    return;
  }

  const modeLabel = problem.mode === "diagnostic" ? "진단" : "맞춤 문제";
  const languageTitle = state.languageMap[problem.language]?.title || problem.language || "-";

  if (elements.problemMode) {
    await streamClient.typeText(elements.problemMode, modeLabel, { minDelay: 10, maxDelay: 16 });
  }
  if (elements.problemTitle) {
    await streamClient.typeText(elements.problemTitle, problem.title || "제목 없는 문제", {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemDifficulty) {
    await streamClient.typeText(elements.problemDifficulty, `난이도 ${problem.difficulty ?? "-"}`, {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemTrack) {
    await streamClient.typeText(elements.problemTrack, `분야 ${problem.track ?? "-"}`, {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemLanguage) {
    await streamClient.typeText(elements.problemLanguage, `언어 ${languageTitle}`, {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemCode) {
    await streamClient.revealLines(elements.problemCode, problem.code || "// 코드가 제공되지 않았어요.", {
      lineDelay: 70,
    });
  }
  if (elements.problemPrompt) {
    await streamClient.typeText(
      elements.problemPrompt,
      problem.prompt || "실행 흐름과 주요 상태 변화가 왜 생기는지 설명해 주세요.",
      {
      minDelay: 10,
      maxDelay: 16,
      }
    );
  }

  renderProblem(problem);
}

async function handleLoadProblem() {
  if (!state.selectedLanguage) {
    showToast("내 정보에서 언어를 먼저 설정해 주세요.");
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  if (!state.selectedLanguage) {
    showToast("내 정보에서 언어를 먼저 설정해 주세요.");
    return;
  }

  setLoadingState(elements.loadProblemBtn, true, "문제 생성 중...");
  state.currentProblem = null;
  resetProblemView();
  clearFeedback();
  try {
    state.selectedDifficulty = getSavedDifficulty();
    renderDifficulty();
    const streamClient = getProblemStreamClient();
    const { payload, streamed, usedJsonFallback } = await streamClient.loadProblemTransport({
      streamClient,
      streamRequest: loadProblemViaStream,
      jsonRequest: async () => {
        setLoadingState(elements.loadProblemBtn, true, "일반 모드 재시도 중...");
        return apiRequest("/platform/analysis/problem", {
          method: "POST",
          body: {
            languageId: state.selectedLanguage,
            difficulty: state.selectedDifficulty,
          },
        });
      },
      shouldFallback: shouldFallbackToJson,
    });
    if (!payload) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    const problem = normalizeAnalysisProblem(payload);
    if (problem) {
      state.currentProblem = problem;
      if (streamed) {
        renderProblem(problem);
      } else if (usedJsonFallback) {
        await animateProblemRender(problem);
      } else {
        renderProblem(problem);
      }
      showToast("문제를 불러왔어요.");
    }
  } catch (error) {
    if (isProblemLoadCancelled(error)) {
      state.currentProblem = null;
      resetProblemView();
      clearFeedback();
      return;
    }
    state.currentProblem = null;
    resetProblemView();
    clearFeedback();
    showToast(error.message || "문제를 불러오지 못했습니다.");
  } finally {
    setLoadingState(elements.loadProblemBtn, false);
  }
}

function renderProblem(problem) {
  if (!problem) return;
  if (elements.problemMode) {
    const label = problem.mode === "diagnostic" ? "진단" : "맞춤 문제";
    elements.problemMode.textContent = label;
  }
  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title || "제목 없는 문제";
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = `난이도 ${problem.difficulty ?? "-"}`;
  }
  if (elements.problemTrack) {
    elements.problemTrack.textContent = `분야 ${problem.track ?? "-"}`;
  }
  const languageTitle = state.languageMap[problem.language]?.title || problem.language || "-";
  if (elements.problemLanguage) {
    elements.problemLanguage.textContent = `언어 ${languageTitle}`;
  }
  if (elements.problemCode) {
    elements.problemCode.textContent = problem.code || "// 코드가 제공되지 않았어요.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent =
      problem.prompt || "실행 흐름과 주요 상태 변화가 왜 생기는지 설명해 주세요.";
  }
  if (elements.hintText) {
    elements.hintText.textContent = "";
    elements.hintText.classList.add("hidden");
  }
  if (elements.hintBtn) {
    elements.hintBtn.disabled = false;
  }
}

function resetProblemView() {
  if (elements.problemMode) elements.problemMode.textContent = "문제 대기";
  if (elements.problemTitle) elements.problemTitle.textContent = "내 정보에서 언어를 설정하면 문제를 보여드릴게요.";
  if (elements.problemDifficulty) elements.problemDifficulty.textContent = "난이도 -";
  if (elements.problemTrack) elements.problemTrack.textContent = "분야 - 알고리즘";
  if (elements.problemLanguage) elements.problemLanguage.textContent = "언어 -";
  if (elements.problemCode) elements.problemCode.textContent = "// 아직 로드된 문제가 없습니다.";
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent =
      "맞춤 문제를 받은 뒤 실행 흐름과 주요 상태 변화가 왜 생기는지 설명해 주세요.";
  }
  if (elements.hintText) {
    elements.hintText.textContent = "";
    elements.hintText.classList.add("hidden");
  }
  if (elements.hintBtn) {
    elements.hintBtn.disabled = true;
  }
  elements.answerForm?.reset();
}

function clearFeedback() {
  if (elements.feedbackSummary) {
    elements.feedbackSummary.textContent = "설명을 제출하면 AI가 요약해 정리해줍니다.";
  }
  if (elements.feedbackStrengths) {
    elements.feedbackStrengths.innerHTML = "";
  }
  if (elements.feedbackImprovements) {
    elements.feedbackImprovements.innerHTML = "";
  }
  if (elements.feedbackScore) {
    elements.feedbackScore.textContent = "점수 대기";
  }
  if (elements.feedbackVerdict) {
    elements.feedbackVerdict.textContent = "판정 대기";
    elements.feedbackVerdict.dataset.state = "neutral";
  }
}

async function handleAnswerSubmit(event) {
  event.preventDefault();
  if (!state.currentProblem) {
    showToast("먼저 문제를 받아주세요.");
    return;
  }
  const explanation = (new FormData(event.currentTarget).get("explanation") || "").toString().trim();
  if (!explanation) {
    showToast("설명을 입력해 주세요.");
    return;
  }
  const submitBtn = elements.answerForm?.querySelector("button[type='submit']");
  setLoadingState(submitBtn, true, "분석 요청 중...");
  try {
    const payload = await apiRequest("/platform/analysis/submit", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        problemId: state.currentProblem.problemId || state.currentProblem.id,
        explanation,
      },
    });
    renderFeedback(payload.feedback, payload.model_answer);
    const profile = await fetchProfile();
    renderProfile(profile);
    elements.answerForm?.reset();
    showToast("AI 피드백을 받았어요.");
  } catch (error) {
    showToast(error.message || "제출에 실패했습니다.");
  } finally {
    setLoadingState(submitBtn, false);
  }
}

function renderFeedback(feedback = {}, modelAnswer = null) {
  if (elements.feedbackSummary) {
    elements.feedbackSummary.textContent = feedback.summary || "요약 정보가 없습니다.";
  }
  const strengths = normalizePoints(feedback.strengths);
  const improvements = normalizePoints(feedback.improvements);
  renderFeedbackList(elements.feedbackStrengths, strengths, "강점 항목이 없습니다.");
  renderFeedbackList(elements.feedbackImprovements, improvements, "개선 항목이 없습니다.");
  if (elements.feedbackScore) {
    const score = feedback.score;
    elements.feedbackScore.textContent =
      typeof score === "number" && !Number.isNaN(score) ? `${Math.round(score)}점` : "점수 정보 없음";
  }
  applyVerdictBadge(feedback.correct);
  if (elements.hintText) {
    elements.hintText.textContent = "";
    elements.hintText.classList.add("hidden");
  }

  const modelContainer = document.getElementById("model-answer-container");
  const modelText = document.getElementById("model-answer-text");
  if (modelContainer && modelText) {
    if (modelAnswer) {
      modelText.textContent = modelAnswer;
      modelContainer.classList.remove("hidden");
    } else {
      modelContainer.classList.add("hidden");
    }
  }
  if (elements.hintBtn) {
    elements.hintBtn.disabled = false;
  }
}

function applyVerdictBadge(correct) {
  if (!elements.feedbackVerdict) return;
  if (correct === true) {
    elements.feedbackVerdict.textContent = "정답";
    elements.feedbackVerdict.dataset.state = "positive";
  } else if (correct === false) {
    elements.feedbackVerdict.textContent = "오답";
    elements.feedbackVerdict.dataset.state = "negative";
  } else {
    elements.feedbackVerdict.textContent = "판정 대기";
    elements.feedbackVerdict.dataset.state = "neutral";
  }
}

async function handleHint() {
  showToast("힌트 기능은 비활성화되어 있습니다.");
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

function setLoadingState(button, isLoading, label) {
  if (!button) return;
  if (isLoading) {
    button.disabled = true;
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent ?? "";
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

function normalizePoints(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => (item ?? "").toString().trim())
    .filter((item) => item.length > 0);
}

function renderFeedbackList(target, items, emptyText) {
  if (!target) return;
  while (target.firstChild) {
    target.removeChild(target.firstChild);
  }
  if (!items || items.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = emptyText;
    target.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = String(item ?? "");
    target.appendChild(li);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

export const app = {};




