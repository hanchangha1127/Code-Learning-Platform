const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
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
  selectedLanguage: null,
  problemId: null,
  code: "",
  title: "",
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리 중 문제가 발생했습니다.",
});


const elements = {};

function cacheDom() {
  elements.userChip = document.getElementById("calc-user-display");
  elements.languageDisplay = document.getElementById("calc-language-display");
  elements.loadBtn = document.getElementById("calc-load-btn");
  elements.status = document.getElementById("calc-status");
  elements.title = document.getElementById("calc-title");
  elements.code = document.getElementById("calc-code-display");
  elements.output = document.getElementById("calc-output");
  elements.submitBtn = document.getElementById("calc-submit-btn");
  elements.nextBtn = document.getElementById("calc-next-btn");
  elements.feedback = document.getElementById("calc-feedback");
  elements.feedbackText = document.getElementById("calc-feedback-text");
  elements.expectedBox = document.getElementById("calc-expected");
  elements.expectedOutput = document.getElementById("calc-expected-output");
  elements.explanation = document.getElementById("calc-explanation");
}

function init() {
  cacheDom();
  state.token = window.localStorage.getItem(TOKEN_KEY);
  if (!state.token) {
    window.location.href = "/index.html";
    return;
  }
  state.selectedLanguage = getSavedLanguage();
  updateDifficultyDisplay();
  state.username = getDisplayName(state.token);
  if (elements.userChip) elements.userChip.textContent = state.username;
  bindEvents();
  loadLanguages();
}

function bindEvents() {
  elements.loadBtn?.addEventListener("click", handleLoadProblem);
  elements.submitBtn?.addEventListener("click", handleSubmitAnswer);
  elements.nextBtn?.addEventListener("click", handleLoadProblem);
}

async function loadLanguages() {
  if (!elements.languageDisplay) return;
  elements.languageDisplay.textContent = "언어 불러오는 중...";
  try {
    const data = await apiRequest("/api/languages");
    state.languages = data.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    const title = state.languages.find((lang) => lang.id === state.selectedLanguage)?.title;
    elements.languageDisplay.textContent = title || state.selectedLanguage || "언어 -";
    updateControls();
    updateDifficultyDisplay();
  } catch (err) {
    console.error(err);
    state.selectedLanguage = getSavedLanguage();
    if (elements.languageDisplay) {
      elements.languageDisplay.textContent = state.selectedLanguage || "언어 -";
    }
    updateControls();
    updateDifficultyDisplay();
  }
}

function updateControls() {
  if (elements.loadBtn) elements.loadBtn.disabled = !state.selectedLanguage;
  const ready = Boolean(state.problemId);
  if (elements.submitBtn) elements.submitBtn.disabled = !ready;
  if (elements.nextBtn) elements.nextBtn.disabled = !ready;
  if (elements.output) elements.output.disabled = !ready;
}

function resetBoard() {
  state.problemId = null;
  state.code = "";
  state.title = "";
  if (elements.code) elements.code.textContent = "// 문제를 불러오면 코드가 표시됩니다.";
  if (elements.title) elements.title.textContent = "문제를 불러와 주세요.";
  if (elements.output) {
    elements.output.value = "";
    elements.output.disabled = true;
  }
  hideFeedback();
  updateControls();
}

function hideFeedback() {
  elements.feedback?.classList.add("hidden");
  elements.expectedBox?.classList.add("hidden");
  if (elements.expectedOutput) elements.expectedOutput.textContent = "";
  if (elements.explanation) elements.explanation.textContent = "";
}

async function handleLoadProblem() {
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정하세요.");
    return;
  }
  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정하세요.");
    return;
  }
  setStatus("문제를 불러오는 중...");
  const originalText = elements.loadBtn?.textContent;
  if (elements.loadBtn) {
    elements.loadBtn.disabled = true;
    elements.loadBtn.classList.add("loading");
    elements.loadBtn.textContent = "불러오는 중...";
  }
  resetBoard();
  try {
    const data = await apiRequest("/api/code-calc/problem", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
    });
    state.problemId = data.problemId;
    state.code = data.code || "";
    state.title = data.title || "코드 계산 문제";
    if (elements.code) elements.code.textContent = state.code || "// 코드 없음";
    if (elements.title) elements.title.textContent = state.title;
    if (elements.output) {
      elements.output.value = "";
      elements.output.disabled = false;
    }
    setStatus("출력값을 계산해 입력한 뒤 정답 확인을 눌러보세요.");
  } catch (err) {
    console.error(err);
    setStatus(err.message || "문제를 불러오지 못했습니다.");
  }
  if (elements.loadBtn) {
    elements.loadBtn.disabled = false;
    elements.loadBtn.classList.remove("loading");
    if (originalText) elements.loadBtn.textContent = originalText;
  }
  updateControls();
}

async function handleSubmitAnswer() {
  if (!state.problemId) return;
  const answer = (elements.output?.value || "").trim();
  if (!answer) {
    setStatus("출력값을 입력해주세요.");
    return;
  }
  setStatus("정답 확인 중...");
  try {
    const result = await apiRequest("/api/code-calc/submit", {
      method: "POST",
      body: {
        problemId: state.problemId,
        output: answer,
      },
    });
    if (elements.feedback) elements.feedback.classList.remove("hidden");
    if (elements.feedbackText) {
      elements.feedbackText.textContent = result.correct
        ? "정답입니다! 출력값을 정확히 맞혔어요."
        : "아쉽습니다. 정답 출력과 설명을 확인해보세요.";
    }
    if (elements.expectedBox && elements.expectedOutput) {
      elements.expectedBox.classList.remove("hidden");
      elements.expectedOutput.textContent = result.expected_output || "";
    }
    if (elements.explanation) {
      elements.explanation.textContent = result.explanation || "";
    }
  } catch (err) {
    console.error(err);
    setStatus(err.message || "정답 확인 중 오류가 발생했습니다.");
  }
}

function setStatus(text) {
  if (elements.status) elements.status.textContent = text;
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

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTY_OPTIONS.has(value) ? value : DEFAULT_DIFFICULTY;
}

function formatDifficultyLabel(value) {
  return DIFFICULTY_LABELS[value] || value || "-";
}

function updateDifficultyDisplay() {
  const diffEl = document.getElementById("calc-difficulty-display");
  if (!diffEl) return;
  const label = formatDifficultyLabel(getSavedDifficulty());
  diffEl.textContent = `난이도: ${label}`;
}

function getSavedLanguage(languages = null) {
  const saved = window.localStorage.getItem(LANGUAGE_KEY);
  if (Array.isArray(languages) && languages.length > 0) {
    if (saved && languages.some((lang) => lang.id === saved)) {
      return saved;
    }
    const fallback = languages[0]?.id || DEFAULT_LANGUAGE;
    if (fallback) {
      window.localStorage.setItem(LANGUAGE_KEY, fallback);
    }
    return fallback;
  }
  return saved || DEFAULT_LANGUAGE;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
