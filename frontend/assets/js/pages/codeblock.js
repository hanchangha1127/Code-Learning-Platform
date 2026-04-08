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

const OPTION_PLACEHOLDER_COUNT = 3;

const state = {
  token: null,
  username: "",
  languages: [],
  currentProblemId: null,
  currentOptions: [],
  selectedLanguage: null,
  problemStreamController: null,
  isLoadingProblem: false,
  optionButtons: [],
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청 처리 중 문제가 발생했습니다.",
});

const elements = {};

function cacheDom() {
  elements.userChip = document.getElementById("cb-user-display");
  elements.languageDisplay = document.getElementById("cb-language-display");
  elements.difficultyDisplay = document.getElementById("cb-difficulty-display");
  elements.loadBtn = document.getElementById("cb-load-btn");
  elements.nextBtn = document.getElementById("cb-next-btn");
  elements.status = document.getElementById("cb-status");
  elements.title = document.getElementById("cb-problem-title");
  elements.objective = document.getElementById("cb-problem-purpose");
  elements.code = document.getElementById("cb-code-display");
  elements.options = document.getElementById("cb-options-container");
  elements.feedbackArea = document.getElementById("cb-feedback-area");
  elements.resultMessage = document.getElementById("cb-result-message");
  elements.explanation = document.getElementById("cb-explanation");
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
  state.username = getDisplayName(state.token);
  if (elements.userChip) {
    elements.userChip.textContent = state.username;
  }

  updateDifficultyDisplay();
  bindControls();
  await loadLanguages();
  resetProblemDisplay();
  await tryResumeReview();
}

function bindControls() {
  elements.loadBtn?.addEventListener("click", handleLoadProblem);
  elements.nextBtn?.addEventListener("click", handleLoadProblem);
}

function setStatus(message) {
  if (elements.status) {
    elements.status.textContent = message;
  }
}

function updateLoadButtonState() {
  const busy = state.isLoadingProblem;
  const ready = Boolean(state.currentProblemId);

  if (elements.loadBtn) {
    elements.loadBtn.disabled = busy || !state.selectedLanguage;
  }
  if (elements.nextBtn) {
    elements.nextBtn.disabled = busy || !ready;
  }
}

function setLoadButtonLoading(loading, label = "") {
  if (!elements.loadBtn) return;
  if (loading) {
    elements.loadBtn.classList.add("loading");
    elements.loadBtn.textContent = label || "문제 생성 중...";
  } else {
    elements.loadBtn.classList.remove("loading");
    elements.loadBtn.textContent = "문제 받기";
  }
}

function hideFeedback() {
  elements.feedbackArea?.classList.add("hidden");
  if (elements.resultMessage) {
    elements.resultMessage.textContent = "";
    elements.resultMessage.className = "cb-result-message";
  }
  if (elements.explanation) {
    elements.explanation.textContent = "";
  }
}

function createOptionButton(index, { placeholder = false, text = "" } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "cb-option-btn";
  if (placeholder) {
    button.classList.add("is-placeholder");
  }
  button.dataset.index = String(index);
  button.disabled = true;
  button.textContent = text;
  return button;
}

function renderOptionMessage(message) {
  if (!elements.options) return;
  elements.options.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
  state.optionButtons = [];
}

function renderOptionSkeleton(count = OPTION_PLACEHOLDER_COUNT) {
  if (!elements.options) return;
  elements.options.innerHTML = "";
  const safeCount = Math.max(1, Number(count) || OPTION_PLACEHOLDER_COUNT);
  for (let index = 0; index < safeCount; index += 1) {
    const button = createOptionButton(index, {
      placeholder: true,
      text: "선택지 생성 중...",
    });
    elements.options.appendChild(button);
  }
  state.optionButtons = Array.from(elements.options.querySelectorAll(".cb-option-btn"));
}

function prepareOptionSlots(optionCount) {
  if (!elements.options) return;
  const safeCount = Math.max(0, Number(optionCount) || 0);
  if (safeCount === 0) {
    renderOptionMessage("선택지가 없습니다. 다시 시도해 주세요.");
    return;
  }

  elements.options.innerHTML = "";
  for (let index = 0; index < safeCount; index += 1) {
    const button = createOptionButton(index, {
      placeholder: true,
      text: "",
    });
    elements.options.appendChild(button);
  }
  state.optionButtons = Array.from(elements.options.querySelectorAll(".cb-option-btn"));
}

function getProblemObjective(problem) {
  const candidates = [problem?.objective, problem?.goal, problem?.prompt, problem?.summary];
  for (const candidate of candidates) {
    const normalized = String(candidate || "").trim();
    if (normalized) {
      return normalized;
    }
  }

  const title = String(problem?.title || "").trim();
  if (title && title !== "코드 빈칸 채우기") {
    return `${title} 흐름을 완성하는 빈칸입니다.`;
  }
  return "이 코드가 어떤 동작을 완성하려는지 먼저 읽고 빈칸의 역할을 추론해 보세요.";
}

function renderProblemHeading(problem) {
  if (elements.title) {
    elements.title.textContent = problem?.title || "코드 블록 문제";
  }
  if (elements.objective) {
    elements.objective.textContent = getProblemObjective(problem);
  }
}

function wireOptionButton(button, index) {
  button.disabled = false;
  button.onclick = () => submitCodeBlockAnswer(index, button);
}

function resetProblemDisplay() {
  state.currentProblemId = null;
  state.currentOptions = [];

  if (elements.title) {
    elements.title.textContent = "문제를 불러와 주세요.";
  }
  if (elements.objective) {
    elements.objective.textContent = "빈칸이 어떤 동작을 완성하는지 여기에 표시됩니다.";
  }
  if (elements.code) {
    elements.code.textContent = "# 문제를 불러오는 중입니다...";
  }

  renderOptionSkeleton();
  hideFeedback();
}

async function loadLanguages() {
  if (!elements.languageDisplay) return;

  elements.languageDisplay.textContent = "언어 불러오는 중...";
  updateLoadButtonState();

  try {
    const data = await apiRequest("/platform/languages", { method: "GET" });
    state.languages = data.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    const title = state.languages.find((lang) => lang.id === state.selectedLanguage)?.title;
    elements.languageDisplay.textContent = title || state.selectedLanguage || "언어 -";
  } catch (err) {
    console.error(err);
    state.selectedLanguage = getSavedLanguage();
    elements.languageDisplay.textContent = state.selectedLanguage || "언어 -";
  } finally {
    updateLoadButtonState();
    updateDifficultyDisplay();
  }
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "code-block",
    apiRequest,
    applyProblem: async (problem) => {
      renderProblem(problem);
      hideFeedback();
      setStatus("같은 문제를 다시 열었습니다. 이어서 복습하세요.");
      updateLoadButtonState();
    },
    onError: (error) => {
      setStatus(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
}

function getProblemStreamClient() {
  return window.CodeProblemStream || null;
}

function getProblemStreamPreviewContainer() {
  return elements.code?.parentElement || elements.objective?.closest(".cb-board") || null;
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

function applyStreamingCodeBlockPreview(draft) {
  if (!draft || typeof draft !== "object") {
    return;
  }
  renderProblemHeading({
    title: typeof draft.title === "string" && draft.title.trim() ? draft.title.trim() : undefined,
    objective: typeof draft.objective === "string" && draft.objective.trim() ? draft.objective.trim() : undefined,
  });
  if (typeof draft.code === "string" && draft.code.length > 0 && elements.code) {
    renderCodeWithBlanks(elements.code, draft.code);
  }
  if (Array.isArray(draft.options) && draft.options.length) {
    prepareOptionSlots(draft.options.length);
    draft.options.forEach((option, index) => {
      const button = state.optionButtons[index];
      if (!button) return;
      button.textContent = String(option ?? "");
    });
  }
}

async function loadCodeBlockProblemViaStream() {
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
      path: "/platform/codeblock/problem",
      token: state.token,
      body: {
        language: state.selectedLanguage,
        difficulty: getSavedDifficulty(),
      },
      returnOnPayload: true,
      onStatus: (statusPayload) => {
        if (statusPayload?.phase === "rendering") {
          setStatus("문제 표시 중...");
          setLoadButtonLoading(true, "문제 표시 중...");
        } else {
          setStatus(statusPayload?.message || "문제 생성 중...");
          setLoadButtonLoading(true, "문제 생성 중...");
        }
      },
      showPartialPreview: false,
      onPreview: (draft) => {
        applyStreamingCodeBlockPreview(draft);
      },
      signal: controller.signal,
    });
  } finally {
    if (state.problemStreamController === controller) {
      state.problemStreamController = null;
    }
  }
}

function renderProblem(problem) {
  if (!problem) return;

  state.currentProblemId = problem.problemId || null;
  state.currentOptions = Array.isArray(problem.options) ? problem.options : [];

  renderProblemHeading(problem);

  if (elements.code) {
    renderCodeWithBlanks(elements.code, problem.code || "# 코드가 없습니다.");
  }

  if (!state.currentOptions.length) {
    renderOptionMessage("선택지가 없습니다. 다시 시도해 주세요.");
    return;
  }

  prepareOptionSlots(state.currentOptions.length);
  state.currentOptions.forEach((option, index) => {
    const button = state.optionButtons[index];
    if (!button) return;
    button.classList.remove("is-placeholder");
    button.textContent = String(option ?? "");
    wireOptionButton(button, index);
  });
}

async function animateCodeBlockProblem(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    return false;
  }

  state.currentProblemId = problem.problemId || null;
  state.currentOptions = Array.isArray(problem.options) ? problem.options : [];

  if (elements.title) {
    await streamClient.typeText(elements.title, problem.title || "코드 블록 문제", {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.objective) {
    await streamClient.typeText(elements.objective, getProblemObjective(problem), {
      minDelay: 4,
      maxDelay: 8,
    });
  }

  if (elements.code) {
    await streamClient.revealLines(elements.code, problem.code || "# 코드가 없습니다.", {
      lineDelay: 70,
    });
    await streamClient.sleep(50);
    renderCodeWithBlanks(elements.code, problem.code || "# 코드가 없습니다.");
  }

  if (!state.currentOptions.length) {
    renderOptionMessage("선택지가 없습니다. 다시 시도해 주세요.");
    return true;
  }

  prepareOptionSlots(state.currentOptions.length);
  for (let index = 0; index < state.currentOptions.length; index += 1) {
    const button = state.optionButtons[index];
    if (!button) continue;

    button.classList.remove("is-placeholder");
    button.textContent = "";
    await streamClient.typeText(button, String(state.currentOptions[index] ?? ""), {
      minDelay: 8,
      maxDelay: 14,
    });
    wireOptionButton(button, index);
    await streamClient.sleep(55);
  }

  return true;
}

async function handleLoadProblem() {
  if (state.isLoadingProblem) {
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  updateDifficultyDisplay();
  if (!state.selectedLanguage) {
    setStatus("내 정보에서 언어를 먼저 설정해 주세요.");
    return;
  }

  state.isLoadingProblem = true;
  updateLoadButtonState();
  setLoadButtonLoading(true, "문제 생성 중...");
  setStatus("문제 생성 중...");
  resetProblemDisplay();

  try {
    const streamClient = getProblemStreamClient();
    const { payload, streamed, usedJsonFallback } = await streamClient.loadProblemTransport({
      streamClient,
      streamRequest: loadCodeBlockProblemViaStream,
      jsonRequest: async () => {
        setStatus("스트림 연결이 불안정해 일반 모드로 다시 시도합니다...");
        setLoadButtonLoading(true, "일반 모드로 다시 시도 중...");
        return apiRequest("/platform/codeblock/problem", {
          method: "POST",
          body: {
            language: state.selectedLanguage,
            difficulty: getSavedDifficulty(),
          },
        });
      },
      shouldFallback: shouldFallbackToJson,
    });

    if (!payload) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    let animated = false;
    if (streamed) {
      renderProblem(payload);
      animated = true;
    } else if (usedJsonFallback) {
      animated = await animateCodeBlockProblem(payload);
    }
    if (!animated) {
      renderProblem(payload);
    }

    setStatus("코드를 분석하고 빈칸에 들어갈 정답을 선택해 보세요.");
  } catch (err) {
    if (isProblemLoadCancelled(err)) {
      resetProblemDisplay();
      setStatus("문제 불러오기를 취소했습니다.");
      return;
    }
    console.error(err);
    resetProblemDisplay();
    setStatus(err?.message || "문제를 불러오지 못했습니다.");
  } finally {
    state.isLoadingProblem = false;
    setLoadButtonLoading(false);
    updateLoadButtonState();
  }
}

async function submitCodeBlockAnswer(selectedIndex, btnElement) {
  if (!state.currentProblemId) return;

  const buttons = Array.from(elements.options?.querySelectorAll(".cb-option-btn") || []);
  buttons.forEach((button) => {
    button.disabled = true;
  });

  try {
    const result = await apiRequest("/platform/codeblock/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        selectedOption: selectedIndex,
      },
    });

    if (!elements.feedbackArea || !elements.resultMessage || !elements.explanation) return;

    elements.feedbackArea.classList.remove("hidden");
    elements.explanation.textContent = result.explanation || "";

    if (result.correct) {
      btnElement.classList.add("correct");
      elements.resultMessage.textContent = "정답입니다.";
      elements.resultMessage.className = "cb-result-message success";
    } else {
      btnElement.classList.add("wrong");
      if (result.correctAnswer !== undefined && buttons[result.correctAnswer]) {
        buttons[result.correctAnswer].classList.add("correct");
      }
      elements.resultMessage.textContent = "오답입니다. 정답을 확인해 보세요.";
      elements.resultMessage.className = "cb-result-message error";
    }
  } catch (err) {
    console.error(err);
    setStatus(err?.message || "정답 확인 중 오류가 발생했습니다.");
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
}

function escapeHtml(text = "") {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
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

window.app = {
  loadCodeBlockProblem: handleLoadProblem,
  submitCodeBlockAnswer,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}


