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
  order: [],
  results: {},
  answerCode: "",
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리 중 문제가 발생했습니다.",
});


const elements = {};
let draggingId = null;

function cacheDom() {
  elements.user = document.getElementById("arr-user");
  elements.languageDisplay = document.getElementById("arr-language-display");
  elements.loadBtn = document.getElementById("arr-load-btn");
  elements.status = document.getElementById("arr-status");
  elements.title = document.getElementById("arr-title");
  elements.blocks = document.getElementById("arr-blocks");
  elements.checkBtn = document.getElementById("arr-check-btn");
  elements.nextBtn = document.getElementById("arr-next-btn");
  elements.feedback = document.getElementById("arr-feedback");
  elements.feedbackText = document.getElementById("arr-feedback-text");
  elements.answer = document.getElementById("arr-answer");
  elements.answerCode = document.getElementById("arr-answer-code");
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
  if (elements.user) elements.user.textContent = state.username;
  bindEvents();
  loadLanguages();
}

function bindEvents() {
  elements.loadBtn?.addEventListener("click", handleLoadProblem);
  elements.checkBtn?.addEventListener("click", handleSubmitOrder);
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
  if (elements.loadBtn) {
    elements.loadBtn.disabled = !state.selectedLanguage;
  }
  if (elements.checkBtn) {
    elements.checkBtn.disabled = !state.problemId;
  }
  if (elements.nextBtn) {
    elements.nextBtn.disabled = !state.problemId;
  }
}

async function handleLoadProblem() {
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해주세요.");
    return;
  }
  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해주세요.");
    return;
  }
  setStatus("문제를 불러오는 중...");
  toggleButtons(true);
  resetBoard();
  try {
    const data = await apiRequest("/api/code-arrange/problem", {
      method: "POST",
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
    });
    state.problemId = data.problemId;
    state.blocks = data.blocks || [];
    state.order = state.blocks.map((b) => b.id);
    state.results = {};
    state.answerCode = "";
    elements.title.textContent = data.title || "코드 배치 문제";
    renderBlocks();
    setStatus("블록을 순서대로 배치한 뒤 정답을 확인하세요.");
    if (elements.checkBtn) elements.checkBtn.disabled = false;
    if (elements.nextBtn) elements.nextBtn.disabled = false;
  } catch (err) {
    console.error(err);
    setStatus(err.message || "문제를 불러오지 못했습니다.");
  } finally {
    toggleButtons(false);
  }
}

function resetBoard() {
  if (elements.blocks) {
    elements.blocks.innerHTML = '<p class="empty">문제를 불러오면 여기에서 블록을 재배열할 수 있습니다.</p>';
  }
  if (elements.feedback) elements.feedback.classList.add("hidden");
  if (elements.answer) elements.answer.classList.add("hidden");
  if (elements.answerCode) elements.answerCode.textContent = "";
}

function renderBlocks() {
  if (!elements.blocks) return;
  elements.blocks.innerHTML = "";
  if (!state.order.length) {
    elements.blocks.innerHTML = '<p class="empty">블록이 없습니다.</p>';
    return;
  }

  state.order.forEach((id) => {
    const block = state.blocks.find((b) => b.id === id);
    const card = document.createElement("div");
    card.className = "arrange-block";
    card.draggable = true;
    card.dataset.id = id;
    card.addEventListener("dragstart", onDragStart);
    card.addEventListener("dragover", onDragOver);
    card.addEventListener("drop", onDrop);
    card.addEventListener("dragend", onDragEnd);

    const code = document.createElement("pre");
    code.textContent = block?.code || "";
    card.appendChild(code);

    if (state.results[id] === true) {
      card.classList.add("is-correct");
    } else if (state.results[id] === false) {
      card.classList.add("is-wrong");
    }

    elements.blocks.appendChild(card);
  });
}

function onDragStart(event) {
  draggingId = event.currentTarget.dataset.id;
  event.dataTransfer.effectAllowed = "move";
  event.currentTarget.classList.add("dragging");
}

function onDragOver(event) {
  event.preventDefault();
  const targetId = event.currentTarget.dataset.id;
  if (!draggingId || draggingId === targetId) return;
  reorderBlocks(draggingId, targetId);
  renderBlocks();
}

function onDrop(event) {
  event.preventDefault();
}

function onDragEnd(event) {
  event.currentTarget.classList.remove("dragging");
  draggingId = null;
}

function reorderBlocks(sourceId, targetId) {
  const fromIndex = state.order.indexOf(sourceId);
  const toIndex = state.order.indexOf(targetId);
  if (fromIndex === -1 || toIndex === -1) return;
  state.order.splice(fromIndex, 1);
  state.order.splice(toIndex, 0, sourceId);
}

async function handleSubmitOrder() {
  if (!state.problemId) return;
  try {
    toggleButtons(true);
    const result = await apiRequest("/api/code-arrange/submit", {
      method: "POST",
      body: {
        problemId: state.problemId,
        order: state.order,
      },
    });
    state.results = {};
    (result.results || []).forEach((item) => {
      state.results[item.id] = Boolean(item.correct);
    });
    state.answerCode = result.answerCode || "";
    renderBlocks();
    if (elements.feedback) elements.feedback.classList.remove("hidden");
    if (elements.feedbackText) {
      elements.feedbackText.textContent = result.correct
        ? "정답입니다! 모든 블록이 올바른 순서입니다."
        : "일부 블록 순서가 잘못됐어요. 정답 코드를 확인해보세요.";
    }
    if (elements.answer) {
      if (state.answerCode) {
        elements.answer.classList.remove("hidden");
        elements.answerCode.textContent = state.answerCode;
      } else {
        elements.answer.classList.add("hidden");
      }
    }
  } catch (err) {
    console.error(err);
    setStatus(err.message || "정답 확인 중 문제가 발생했습니다.");
  } finally {
    toggleButtons(false);
  }
}

function setStatus(text) {
  if (elements.status) elements.status.textContent = text;
}

function toggleButtons(isLoading) {
  if (elements.loadBtn) elements.loadBtn.disabled = isLoading || !state.selectedLanguage;
  if (elements.checkBtn) elements.checkBtn.disabled = isLoading || !state.problemId;
  if (elements.nextBtn) elements.nextBtn.disabled = isLoading || !state.problemId;
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
  const diffEl = document.getElementById("arr-difficulty-display");
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
