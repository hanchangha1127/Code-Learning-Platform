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
  blocks: [],
  selectedIndex: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리 중 문제가 발생했습니다.",
});


const elements = {};

function cacheDom() {
  elements.userChip = document.getElementById("cerr-user-display");
  elements.languageDisplay = document.getElementById("cerr-language-display");
  elements.loadBtn = document.getElementById("cerr-load-btn");
  elements.status = document.getElementById("cerr-status");
  elements.title = document.getElementById("cerr-title");
  elements.blocks = document.getElementById("cerr-blocks");
  elements.submitBtn = document.getElementById("cerr-submit-btn");
  elements.nextBtn = document.getElementById("cerr-next-btn");
  elements.feedback = document.getElementById("cerr-feedback");
  elements.feedbackText = document.getElementById("cerr-feedback-text");
  elements.explanationBox = document.getElementById("cerr-explanation-box");
  elements.explanation = document.getElementById("cerr-explanation");
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
  if (elements.submitBtn) elements.submitBtn.disabled = !ready || state.selectedIndex === null;
  if (elements.nextBtn) elements.nextBtn.disabled = !ready;
}

function resetBoard() {
  state.problemId = null;
  state.blocks = [];
  state.selectedIndex = null;
  if (elements.blocks) elements.blocks.innerHTML = '<p class="empty">문제를 불러오면 블록이 표시됩니다.</p>';
  if (elements.title) elements.title.textContent = "문제를 불러와 주세요.";
  hideFeedback();
  updateControls();
}

function hideFeedback() {
  elements.feedback?.classList.add("hidden");
  elements.explanationBox?.classList.add("hidden");
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
    const data = await apiRequest("/api/code-error/problem", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
    });
    state.problemId = data.problemId;
    state.blocks = data.blocks || [];
    state.selectedIndex = null;
    if (elements.title) elements.title.textContent = data.title || "코드 오류 문제";
    renderBlocks();
    setStatus("잘못된 블록 하나를 선택한 뒤 정답 확인을 눌러보세요.");
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

function renderBlocks() {
  if (!elements.blocks) return;
  elements.blocks.innerHTML = "";
  if (!state.blocks.length) {
    elements.blocks.innerHTML = '<p class="empty">블록이 없습니다.</p>';
    return;
  }
  state.blocks.forEach((code, idx) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "cerr-block";
    card.dataset.index = String(idx);
    card.addEventListener("click", () => selectBlock(idx, card));

    const pre = document.createElement("pre");
    pre.className = "code-block";
    pre.textContent = code;

    card.appendChild(pre);

    elements.blocks.appendChild(card);
  });
}

function selectBlock(idx, cardEl) {
  state.selectedIndex = idx;
  elements.blocks?.querySelectorAll(".cerr-block").forEach((el) => {
    el.classList.toggle("selected", el === cardEl);
  });
  updateControls();
  hideFeedback();
}

async function handleSubmitAnswer() {
  if (state.selectedIndex === null || !state.problemId) {
    setStatus("잘못된 블록을 먼저 선택하세요.");
    return;
  }
  setStatus("정답 확인 중...");
  try {
    const result = await apiRequest("/api/code-error/submit", {
      method: "POST",
      body: {
        problemId: state.problemId,
        selectedIndex: state.selectedIndex,
      },
    });
    if (elements.feedback) elements.feedback.classList.remove("hidden");
    if (elements.feedbackText) {
      elements.feedbackText.textContent = result.correct
        ? "정답입니다! 잘못된 블록을 찾았습니다."
        : "아쉽습니다. 정답 블록을 확인하세요.";
    }
    if (elements.explanationBox && elements.explanation) {
      elements.explanationBox.classList.remove("hidden");
      elements.explanation.textContent = result.explanation || "";
    }
    // highlight correct/incorrect
    if (elements.blocks) {
      elements.blocks.querySelectorAll(".cerr-block").forEach((el) => {
        const idx = Number(el.dataset.index);
        el.classList.toggle("is-correct", idx === result.correctIndex);
        if (idx === state.selectedIndex && idx !== result.correctIndex) {
          el.classList.add("is-wrong");
        }
        if (idx !== result.correctIndex) {
          el.classList.remove("is-correct");
        }
      });
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
  const diffEl = document.getElementById("cerr-difficulty-display");
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
