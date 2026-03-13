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

const state = {
  token: null,
  username: "",
  languages: [],
  selectedLanguage: null,
  problemId: null,
  blocks: [],
  selectedIndex: null,
  problemStreamController: null,
  isLoadingProblem: false,
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
  if (elements.userChip) {
    elements.userChip.textContent = state.username;
  }

  bindEvents();
  await loadLanguages();
  resetBoard();
  await tryResumeReview();
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
    const data = await apiRequest("/platform/languages");
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

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "code-error",
    apiRequest,
    applyProblem: async (problem) => {
      state.problemId = problem.problemId || null;
      state.blocks = normalizeBlocks(problem.blocks);
      state.selectedIndex = null;
      state.selectedLanguage = problem.language || state.selectedLanguage;
      if (elements.title) {
        elements.title.textContent = problem.title || "코드 오류 문제";
      }
      renderBlocks();
      hideFeedback();
      setStatus("같은 문제를 다시 열었습니다. 오류 블록을 다시 찾아보세요.");
      updateControls();
    },
    onError: (error) => {
      setStatus(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
}

function updateControls() {
  if (elements.loadBtn) {
    elements.loadBtn.disabled = state.isLoadingProblem || !state.selectedLanguage;
  }
  const ready = Boolean(state.problemId);
  if (elements.submitBtn) {
    elements.submitBtn.disabled = !ready || state.selectedIndex === null;
  }
  if (elements.nextBtn) {
    elements.nextBtn.disabled = !ready;
  }
}

function hideFeedback() {
  elements.feedback?.classList.add("hidden");
  elements.explanationBox?.classList.add("hidden");
  if (elements.feedbackText) elements.feedbackText.textContent = "";
  if (elements.explanation) elements.explanation.textContent = "";
}

function resetBoard() {
  state.problemId = null;
  state.blocks = [];
  state.selectedIndex = null;

  if (elements.title) {
    elements.title.textContent = "문제를 불러와 주세요.";
  }
  if (elements.blocks) {
    elements.blocks.innerHTML = '<p class="empty">문제를 불러오면 여기에서 코드 블록을 확인할 수 있습니다.</p>';
  }
  hideFeedback();
}

function getProblemStreamClient() {
  return window.CodeProblemStream || null;
}

function shouldFallbackToJson(streamError) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.shouldFallbackToJson !== "function") {
    return false;
  }
  return Boolean(streamClient.shouldFallbackToJson(streamError));
}

function normalizeBlocks(rawBlocks) {
  const source = Array.isArray(rawBlocks) ? rawBlocks : [];
  return source.map((item, index) => {
    if (typeof item === "string") {
      return { id: `block-${index + 1}`, code: item };
    }
    return {
      id: String(item?.id ?? `block-${index + 1}`),
      code: String(item?.code ?? ""),
    };
  });
}

async function loadCodeErrorProblemViaStream() {
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
      path: "/platform/codeerror/problem",
      token: state.token,
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
      onStatus: (statusPayload) => {
        if (statusPayload?.phase === "rendering") {
          setStatus("문제 표시 중...");
          if (elements.loadBtn) {
            elements.loadBtn.textContent = "문제 표시 중...";
          }
        }
      },
      signal: state.problemStreamController.signal,
    });
  } finally {
    state.problemStreamController = null;
  }
}

function createBlockCard(block, index) {
  const card = document.createElement("div");
  card.className = "cerr-block";
  card.dataset.index = String(index);

  const badge = document.createElement("span");
  badge.className = "cerr-badge";
  badge.textContent = `블록 ${index + 1}`;

  const pre = document.createElement("pre");
  pre.className = "code-block";
  pre.textContent = block?.code || "";

  card.appendChild(badge);
  card.appendChild(pre);
  return card;
}

async function animateCodeErrorProblem(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    return;
  }

  if (elements.title) {
    await streamClient.typeText(elements.title, problem.title || "코드 오류 문제", {
      minDelay: 10,
      maxDelay: 16,
    });
  }

  const blocks = normalizeBlocks(problem.blocks);
  if (!elements.blocks) return;

  elements.blocks.innerHTML = "";
  if (!blocks.length) {
    elements.blocks.innerHTML = '<p class="empty">코드 블록 정보가 없습니다.</p>';
    return;
  }

  for (let index = 0; index < blocks.length; index += 1) {
    const block = blocks[index];
    const card = createBlockCard(block, index);
    const pre = card.querySelector("pre");
    elements.blocks.appendChild(card);

    if (pre) {
      await streamClient.revealLines(pre, block.code || "", { lineDelay: 70 });
    }
    await streamClient.sleep(70);
  }
}

async function handleLoadProblem() {
  if (state.isLoadingProblem) {
    return;
  }

  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해 주세요.");
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해 주세요.");
    return;
  }

  setStatus("문제를 불러오는 중...");
  const originalText = elements.loadBtn?.textContent;
  state.isLoadingProblem = true;
  updateControls();
  if (elements.loadBtn) {
    elements.loadBtn.classList.add("loading");
    elements.loadBtn.textContent = "불러오는 중...";
  }

  resetBoard();
  updateControls();

  try {
    let data = null;
    let streamed = false;
    let usedJsonFallback = false;
    let allowJsonFallback = false;

    try {
      data = await loadCodeErrorProblemViaStream();
      streamed = Boolean(data);
    } catch (streamError) {
      allowJsonFallback = shouldFallbackToJson(streamError);
      if (!allowJsonFallback) {
        throw streamError;
      }
    }

    if (!data && !allowJsonFallback) {
      const streamClient = getProblemStreamClient();
      allowJsonFallback = !streamClient || typeof streamClient.streamProblem !== "function";
    }

    if (!data && allowJsonFallback) {
      setStatus("스트리밍 연결이 끊겨 일반 모드로 재시도 중...");
      if (elements.loadBtn) {
        elements.loadBtn.textContent = "일반 모드 재시도 중...";
      }
      data = await apiRequest("/platform/codeerror/problem", {
        method: "POST",
        body: {
          language: state.selectedLanguage,
          difficulty: getSavedDifficulty(),
        },
      });
      usedJsonFallback = true;
    }
    if (!data) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    state.problemId = data.problemId;
    state.blocks = normalizeBlocks(data.blocks);
    state.selectedIndex = null;

    if (streamed || usedJsonFallback) {
      await animateCodeErrorProblem(data);
    } else if (elements.title) {
      elements.title.textContent = data.title || "코드 오류 문제";
    }

    renderBlocks();
    setStatus("오류가 있는 블록을 선택한 뒤 정답 확인을 눌러주세요.");
  } catch (err) {
    console.error(err);
    setStatus(err.message || "문제를 불러오지 못했습니다.");
  } finally {
    state.isLoadingProblem = false;
    if (elements.loadBtn) {
      elements.loadBtn.classList.remove("loading");
      if (originalText) elements.loadBtn.textContent = originalText;
    }
    updateControls();
  }
}

function renderBlocks() {
  if (!elements.blocks) return;

  elements.blocks.innerHTML = "";
  if (!state.blocks.length) {
    elements.blocks.innerHTML = '<p class="empty">코드 블록 정보가 없습니다.</p>';
    return;
  }

  state.blocks.forEach((block, index) => {
    const card = createBlockCard(block, index);
    card.addEventListener("click", () => selectBlock(index, card));

    if (state.selectedIndex === index) {
      card.classList.add("selected");
    }

    elements.blocks.appendChild(card);
  });
}

function selectBlock(index, cardEl) {
  state.selectedIndex = index;
  if (elements.blocks) {
    elements.blocks.querySelectorAll(".cerr-block").forEach((el) => {
      el.classList.remove("selected", "is-correct", "is-wrong");
    });
  }
  cardEl.classList.add("selected");
  hideFeedback();
  updateControls();
}

async function handleSubmitAnswer() {
  if (state.selectedIndex === null || !state.problemId) {
    setStatus("오류 블록을 먼저 선택해 주세요.");
    return;
  }

  setStatus("정답 확인 중...");
  try {
    const result = await apiRequest("/platform/codeerror/submit", {
      method: "POST",
      body: {
        problemId: state.problemId,
        selectedIndex: state.selectedIndex,
      },
    });

    if (elements.feedback) elements.feedback.classList.remove("hidden");
    if (elements.feedbackText) {
      elements.feedbackText.textContent = result.correct
        ? "정답입니다. 오류 블록을 정확하게 찾았습니다."
        : "아쉽습니다. 정답 블록과 해설을 확인해 보세요.";
    }
    if (elements.explanationBox && elements.explanation) {
      elements.explanationBox.classList.remove("hidden");
      elements.explanation.textContent = result.explanation || "";
    }

    if (elements.blocks) {
      elements.blocks.querySelectorAll(".cerr-block").forEach((el) => {
        const idx = Number(el.dataset.index);
        el.classList.toggle("is-correct", idx === result.correctIndex);
        if (idx === state.selectedIndex && idx !== result.correctIndex) {
          el.classList.add("is-wrong");
        } else if (idx !== result.correctIndex) {
          el.classList.remove("is-wrong");
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
  diffEl.textContent = `난이도 ${label}`;
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

