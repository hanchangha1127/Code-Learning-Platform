const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const reviewResume = window.CodeReviewResume || null;
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

const ARRANGE_REVEAL_BUDGET_MS = 700;
const ARRANGE_STATUS_TRANSITION_MS = 80;
const ARRANGE_TITLE_REVEAL_MS = 160;
const ARRANGE_BLOCK_REVEAL_MS = 460;

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
  isLoadingProblem: false,
  isAnimatingProblem: false,
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
  elements.difficultyDisplay = document.getElementById("arr-difficulty-display");
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
  state.selectedLanguage = getSavedLanguage();
  updateDifficultyDisplay();
  state.username = getDisplayName(state.token);
  if (elements.user) {
    elements.user.textContent = state.username;
  }

  bindEvents();
  await loadLanguages();
  resetBoard();
  await tryResumeReview();
}

function bindEvents() {
  elements.loadBtn?.addEventListener("click", handleLoadProblem);
  elements.checkBtn?.addEventListener("click", handleSubmitOrder);
  elements.nextBtn?.addEventListener("click", handleLoadProblem);
}

async function loadLanguages() {
  if (!elements.languageDisplay) return;

  elements.languageDisplay.textContent = "언어 불러오는 중...";
  updateControls();

  try {
    const data = await apiRequest("/platform/languages");
    state.languages = data.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    const title = state.languages.find((lang) => lang.id === state.selectedLanguage)?.title;
    elements.languageDisplay.textContent = title || state.selectedLanguage || "언어 -";
  } catch (err) {
    console.error(err);
    state.selectedLanguage = getSavedLanguage();
    if (elements.languageDisplay) {
      elements.languageDisplay.textContent = state.selectedLanguage || "언어 -";
    }
  } finally {
    updateControls();
    updateDifficultyDisplay();
  }
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "code-arrange",
    apiRequest,
    applyProblem: async (problem) => {
      applyProblemData(problem);
      if (elements.title) {
        elements.title.textContent = problem.title || "코드 배치 문제";
      }
      renderBlocks();
      if (elements.feedback) {
        elements.feedback.classList.add("hidden");
      }
      if (elements.answer) {
        elements.answer.classList.add("hidden");
      }
      if (elements.feedbackText) {
        elements.feedbackText.textContent = "";
      }
      if (elements.answerCode) {
        elements.answerCode.textContent = "";
      }
      setStatus("같은 문제를 다시 열었습니다. 블록 순서를 다시 맞춰보세요.");
      updateControls();
    },
    onError: (error) => {
      setStatus(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
}

function updateControls() {
  const busy = state.isLoadingProblem || state.isAnimatingProblem;

  if (elements.loadBtn) {
    elements.loadBtn.disabled = busy || !state.selectedLanguage;
  }
  if (elements.checkBtn) {
    elements.checkBtn.disabled = busy || !state.problemId;
  }
  if (elements.nextBtn) {
    elements.nextBtn.disabled = busy || !state.problemId;
  }
}

function setLoadButtonLoading(loading, label) {
  if (!elements.loadBtn) return;

  if (loading) {
    elements.loadBtn.classList.add("loading");
    elements.loadBtn.textContent = label || "문제 생성 중...";
  } else {
    elements.loadBtn.classList.remove("loading");
    elements.loadBtn.textContent = "문제 받기";
  }
}

function setStatus(text) {
  if (elements.status) {
    elements.status.textContent = text;
  }
}

function resetBoard() {
  state.problemId = null;
  state.blocks = [];
  state.order = [];
  state.results = {};
  state.answerCode = "";

  if (elements.title) {
    elements.title.textContent = "문제를 불러와 주세요.";
  }
  if (elements.blocks) {
    elements.blocks.innerHTML = '<p class="empty">문제를 불러오면 여기에서 블록을 재배열할 수 있습니다.</p>';
  }
  if (elements.feedback) {
    elements.feedback.classList.add("hidden");
  }
  if (elements.feedbackText) {
    elements.feedbackText.textContent = "";
  }
  if (elements.answer) {
    elements.answer.classList.add("hidden");
  }
  if (elements.answerCode) {
    elements.answerCode.textContent = "";
  }
}

function normalizeBlocks(rawBlocks) {
  const source = Array.isArray(rawBlocks) ? rawBlocks : [];
  return source.map((item, index) => ({
    id: String(item?.id ?? `block-${index + 1}`),
    code: String(item?.code ?? ""),
  }));
}

function applyProblemData(data) {
  state.problemId = data?.problemId || null;
  state.blocks = normalizeBlocks(data?.blocks || []);
  state.order = state.blocks.map((block) => block.id);
  state.results = {};
  state.answerCode = "";
}

async function handleLoadProblem() {
  if (state.isLoadingProblem || state.isAnimatingProblem) {
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해주세요.");
    return;
  }

  state.isLoadingProblem = true;
  setLoadButtonLoading(true, "문제 생성 중...");
  setStatus("문제 생성 중...");
  resetBoard();
  updateControls();

  try {
    let data;
    try {
      data = await apiRequest("/platform/arrange/problem", {
        method: "POST",
        body: {
          language: state.selectedLanguage,
          difficulty: getSavedDifficulty(),
        },
      });
    } catch (fetchError) {
      console.error(fetchError);
      setStatus(fetchError?.message || "문제를 불러오지 못했습니다.");
      return;
    }

    applyProblemData(data);

    state.isLoadingProblem = false;
    state.isAnimatingProblem = true;
    setLoadButtonLoading(true, "문제 표시 중...");
    updateControls();

    try {
      await animateArrangeProblem(data);
    } catch (animationError) {
      console.error(animationError);
    }

    if (elements.title) {
      elements.title.textContent = data?.title || "코드 배치 문제";
    }
    renderBlocks();
    setStatus("블록을 순서대로 배치한 뒤 정답 확인을 눌러보세요.");
  } finally {
    state.isLoadingProblem = false;
    state.isAnimatingProblem = false;
    setLoadButtonLoading(false);
    updateControls();
  }
}

function renderBlocks() {
  if (!elements.blocks) return;

  elements.blocks.innerHTML = "";
  if (!state.order.length) {
    elements.blocks.innerHTML = '<p class="empty">블록이 없습니다.</p>';
    return;
  }

  state.order.forEach((id) => {
    const block = state.blocks.find((item) => item.id === id);
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

function renderPreviewBlocks(blocks) {
  if (!elements.blocks) return;

  elements.blocks.innerHTML = "";
  if (!blocks.length) {
    elements.blocks.innerHTML = '<p class="empty">블록이 없습니다.</p>';
    return;
  }

  blocks.forEach((block) => {
    const card = document.createElement("div");
    card.className = "arrange-block";

    const code = document.createElement("pre");
    code.textContent = block?.code || "";
    card.appendChild(code);

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

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, Math.max(0, Math.floor(ms)));
  });
}

async function typeTitleWithinBudget(title, budgetMs) {
  const text = String(title || "코드 배치 문제");
  if (!elements.title) {
    await sleep(budgetMs);
    return;
  }
  if (!text) {
    elements.title.textContent = "";
    return;
  }
  if (budgetMs <= 0 || text.length <= 1) {
    elements.title.textContent = text;
    return;
  }

  const start = performance.now();
  elements.title.textContent = "";

  for (let index = 0; index < text.length; index += 1) {
    elements.title.textContent = text.slice(0, index + 1);

    if (index >= text.length - 1) {
      break;
    }

    const targetElapsed = ((index + 1) / text.length) * budgetMs;
    const elapsed = performance.now() - start;
    const waitMs = targetElapsed - elapsed;
    if (waitMs > 1) {
      await sleep(waitMs);
    }
  }

  elements.title.textContent = text;
}

async function revealBlocksWithinBudget(blocks, budgetMs, { stepOffset = 0, totalSteps = 1 } = {}) {
  const source = Array.isArray(blocks) ? blocks : [];
  if (!source.length) {
    renderPreviewBlocks([]);
    setStatus(`문제 표시 중... (${totalSteps}/${totalSteps})`);
    await sleep(Math.min(80, budgetMs));
    return;
  }

  const blockCount = source.length;
  const steps = Math.min(blockCount, 10);
  const chunkSize = Math.ceil(blockCount / steps);
  const stepDelay = steps > 1 ? Math.floor(budgetMs / steps) : 0;

  for (let step = 0; step < steps; step += 1) {
    const visibleCount = Math.min(blockCount, (step + 1) * chunkSize);
    renderPreviewBlocks(source.slice(0, visibleCount));

    const stepNumber = Math.min(totalSteps, stepOffset + step + 1);
    setStatus(`문제 표시 중... (${stepNumber}/${totalSteps})`);

    if (step < steps - 1 && stepDelay > 0) {
      await sleep(stepDelay);
    }
  }
}

async function animateArrangeProblem(problem) {
  await sleep(ARRANGE_STATUS_TRANSITION_MS);

  const blockCount = state.blocks.length;
  const blockSteps = Math.max(1, Math.min(blockCount || 1, 10));
  const totalSteps = blockSteps + 1;

  setStatus(`문제 표시 중... (1/${totalSteps})`);
  await typeTitleWithinBudget(problem?.title || "코드 배치 문제", ARRANGE_TITLE_REVEAL_MS);

  await revealBlocksWithinBudget(state.blocks, ARRANGE_BLOCK_REVEAL_MS, {
    stepOffset: 1,
    totalSteps,
  });

  // Keep total budget deterministic under 700ms window.
  const used = ARRANGE_STATUS_TRANSITION_MS + ARRANGE_TITLE_REVEAL_MS + ARRANGE_BLOCK_REVEAL_MS;
  if (used < ARRANGE_REVEAL_BUDGET_MS) {
    await sleep(ARRANGE_REVEAL_BUDGET_MS - used);
  }
}

async function handleSubmitOrder() {
  if (!state.problemId || state.isLoadingProblem || state.isAnimatingProblem) {
    return;
  }

  state.isLoadingProblem = true;
  updateControls();

  try {
    const result = await apiRequest("/platform/arrange/submit", {
      method: "POST",
      body: {
        problemId: state.problemId,
        order: state.order,
      },
    });

    state.results = {};
    (result.results || []).forEach((item) => {
      state.results[String(item.id)] = Boolean(item.correct);
    });
    state.answerCode = result.answerCode || "";

    renderBlocks();

    if (elements.feedback) {
      elements.feedback.classList.remove("hidden");
    }
    if (elements.feedbackText) {
      elements.feedbackText.textContent = result.correct
        ? "정답입니다! 모든 블록이 올바른 순서입니다."
        : "일부 블록 순서가 잘못되었습니다. 정답 코드를 확인해보세요.";
    }

    if (elements.answer) {
      if (state.answerCode) {
        elements.answer.classList.remove("hidden");
        if (elements.answerCode) {
          elements.answerCode.textContent = state.answerCode;
        }
      } else {
        elements.answer.classList.add("hidden");
      }
    }
  } catch (err) {
    console.error(err);
    setStatus(err?.message || "정답 확인 중 문제가 발생했습니다.");
  } finally {
    state.isLoadingProblem = false;
    updateControls();
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

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTY_OPTIONS.has(value) ? value : DEFAULT_DIFFICULTY;
}

function formatDifficultyLabel(value) {
  return DIFFICULTY_LABELS[value] || value || "-";
}

function updateDifficultyDisplay() {
  if (!elements.difficultyDisplay) return;
  const label = formatDifficultyLabel(getSavedDifficulty());
  elements.difficultyDisplay.textContent = `난이도 ${label}`;
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

window.app = {
  loadArrangeProblem: handleLoadProblem,
  submitArrangeOrder: handleSubmitOrder,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}


