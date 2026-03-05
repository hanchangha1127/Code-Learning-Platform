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
  currentProblemId: null,
  selectedLanguage: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리 중 문제가 발생했습니다.",
});


function init() {
  state.token = window.localStorage.getItem(TOKEN_KEY);
  if (!state.token) {
    window.location.href = "/index.html";
    return;
  }
  state.selectedLanguage = getSavedLanguage();
  updateDifficultyDisplay();
  state.username = getDisplayName(state.token);
  const chip = document.getElementById("cb-user-display");
  if (chip) chip.textContent = state.username;
  bindControls();
  loadLanguages();
}

function bindControls() {
  const loadBtn = document.getElementById("cb-load-btn");
  if (loadBtn) {
    loadBtn.addEventListener("click", () => {
      if (!state.selectedLanguage) {
        showStatus("내 정보에서 언어를 설정해주세요.");
        return;
      }
      loadCodeBlockProblem();
    });
  }
}

async function loadLanguages() {
  const labelEl = document.getElementById("cb-language-display");
  const loadBtn = document.getElementById("cb-load-btn");
  if (!labelEl || !loadBtn) return;

  labelEl.textContent = "언어 불러오는 중...";
  loadBtn.disabled = true;

  try {
    const data = await apiRequest("/api/languages", { method: "GET" });
    state.languages = data.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    const title = state.languages.find((lang) => lang.id === state.selectedLanguage)?.title;
    labelEl.textContent = title || state.selectedLanguage || "언어 -";
    loadBtn.disabled = !state.selectedLanguage;
    updateDifficultyDisplay();
  } catch (err) {
    console.error(err);
    state.selectedLanguage = getSavedLanguage();
    labelEl.textContent = state.selectedLanguage || "언어 -";
    loadBtn.disabled = !state.selectedLanguage;
    updateDifficultyDisplay();
  }
}

async function loadCodeBlockProblem() {
  if (!state.selectedLanguage) return;
  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    showStatus("내 정보에서 언어를 설정해주세요.");
    return;
  }

  const codeDisplay = document.getElementById("cb-code-display");
  const titleDisplay = document.getElementById("cb-problem-title");
  const optionsContainer = document.getElementById("cb-options-container");
  const feedbackArea = document.getElementById("cb-feedback-area");

  if (!codeDisplay || !titleDisplay || !optionsContainer || !feedbackArea) return;

  codeDisplay.textContent = "문제를 불러오는 중입니다...";
  titleDisplay.textContent = "문제를 준비 중입니다.";
  optionsContainer.innerHTML = "";
  feedbackArea.classList.add("hidden");

  try {
    const data = await apiRequest("/api/code-block/problem", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
    });

    state.currentProblemId = data.problemId;
    titleDisplay.textContent = data.title;
    renderCodeWithBlanks(codeDisplay, data.code);
    if (!data.options || data.options.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "선택지가 없습니다. 다시 시도해주세요.";
      optionsContainer.appendChild(empty);
      return;
    }

    data.options.forEach((opt, index) => {
      const btn = document.createElement("button");
      btn.className = "cb-option-btn";
      btn.textContent = opt;
      btn.onclick = () => submitCodeBlockAnswer(index, btn);
      optionsContainer.appendChild(btn);
    });

    if (window.hljs) window.hljs.highlightElement(codeDisplay);
  } catch (err) {
    console.error(err);
    titleDisplay.textContent = "문제를 불러오지 못했습니다.";
    codeDisplay.textContent = "다시 시도해주세요.";
  }
}

async function submitCodeBlockAnswer(selectedIndex, btnElement) {
  if (!state.currentProblemId) return;

  const buttons = document.querySelectorAll(".cb-option-btn");
  buttons.forEach((b) => {
    b.disabled = true;
  });

  try {
    const result = await apiRequest("/api/code-block/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        selectedOption: selectedIndex,
      },
    });

    const feedbackArea = document.getElementById("cb-feedback-area");
    const resultMessage = document.getElementById("cb-result-message");
    const explanation = document.getElementById("cb-explanation");

    if (!feedbackArea || !resultMessage || !explanation) return;

    feedbackArea.classList.remove("hidden");
    explanation.textContent = result.explanation || "";

    if (result.correct) {
      btnElement.classList.add("correct");
      resultMessage.textContent = "정답입니다!";
      resultMessage.className = "cb-result-message success";
    } else {
      btnElement.classList.add("wrong");
      if (result.correctAnswer !== undefined && buttons[result.correctAnswer]) {
        buttons[result.correctAnswer].classList.add("correct");
      }
      resultMessage.textContent = "아쉽습니다. 정답을 확인해보세요!";
      resultMessage.className = "cb-result-message error";
    }
  } catch (err) {
    console.error(err);
    showStatus(err.message || "정답 제출 중 문제가 발생했습니다.");
    buttons.forEach((b) => {
      b.disabled = false;
    });
  }
}

function escapeHtml(text = "") {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderCodeWithBlanks(target, codeText = "") {
  if (!target) return;
  const escaped = escapeHtml(codeText);
  const withTiles = escaped.replace(/\[BLANK\]/g, '<span class="blank-tile" aria-label="빈칸"></span>');
  target.innerHTML = withTiles;
}

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTY_OPTIONS.has(value) ? value : DEFAULT_DIFFICULTY;
}

function formatDifficultyLabel(value) {
  return DIFFICULTY_LABELS[value] || value || "-";
}

function updateDifficultyDisplay() {
  const diffEl = document.getElementById("cb-difficulty-display");
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

function showStatus(message) {
  const titleDisplay = document.getElementById("cb-problem-title");
  if (titleDisplay) titleDisplay.textContent = message;
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

const app = {
  loadCodeBlockProblem,
  submitCodeBlockAnswer,
};
window.app = app;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
