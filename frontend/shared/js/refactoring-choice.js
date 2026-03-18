const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const reviewResume = window.CodeReviewResume || null;
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

const state = {
  token: null,
  username: "",
  languages: [],
  languageMap: {},
  selectedLanguage: DEFAULT_LANGUAGE,
  selectedDifficulty: DEFAULT_DIFFICULTY,
  currentProblemId: null,
  currentOptions: [],
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
  elements.userDisplay = document.getElementById("rc-user-display");
  elements.languageDisplay = document.getElementById("rc-language-display");
  elements.difficultyDisplay = document.getElementById("rc-difficulty-display");
  elements.loadBtn = document.getElementById("rc-load-btn");
  elements.loadStatus = document.getElementById("rc-load-status");
  elements.problemTitle = document.getElementById("rc-problem-title");
  elements.problemScenario = document.getElementById("rc-problem-scenario");
  elements.problemConstraints = document.getElementById("rc-problem-constraints");
  elements.problemOptions = document.getElementById("rc-options");
  elements.problemPrompt = document.getElementById("rc-problem-prompt");
  elements.problemLanguage = document.getElementById("rc-problem-language");
  elements.problemDifficulty = document.getElementById("rc-problem-difficulty");
  elements.problemFacets = document.getElementById("rc-problem-facets");
  elements.reportForm = document.getElementById("rc-report-form");
  elements.reportText = document.getElementById("rc-report-text");
  elements.optionRadios = document.querySelectorAll("input[name='selected-option']");
  elements.score = document.getElementById("rc-score");
  elements.verdict = document.getElementById("rc-verdict");
  elements.thresholdText = document.getElementById("rc-threshold-text");
  elements.feedbackSummary = document.getElementById("rc-feedback-summary");
  elements.strengths = document.getElementById("rc-strengths");
  elements.improvements = document.getElementById("rc-improvements");
  elements.selectedOption = document.getElementById("rc-selected-option");
  elements.bestOption = document.getElementById("rc-best-option");
  elements.foundTypes = document.getElementById("rc-found-types");
  elements.missedTypes = document.getElementById("rc-missed-types");
  elements.optionReviews = document.getElementById("rc-option-reviews");
  elements.referenceReport = document.getElementById("rc-reference-report");
  elements.toast = document.getElementById("rc-toast");
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
  elements.optionRadios?.forEach((radio) => {
    radio.addEventListener("change", () => highlightSelectedOption(radio.value));
  });
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
        ? "문제 받기를 눌러 최적의 선택 문제를 생성하세요."
        : "언어 설정을 확인하고 다시 시도해 주세요.";
    }
  }
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "refactoring-choice",
    apiRequest,
    applyProblem: async (problem) => {
      renderProblem(problem);
      clearFeedback();
      if (elements.loadStatus) {
        elements.loadStatus.textContent = "같은 문제를 다시 열었습니다. 선택 근거를 다시 정리해 보세요.";
      }
    },
    onError: (error) => {
      showToast(error.message || "복습 문제를 다시 열지 못했습니다.");
    },
  });
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

function shouldFallbackToJson(streamError) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.shouldFallbackToJson !== "function") {
    return false;
  }
  return Boolean(streamClient.shouldFallbackToJson(streamError));
}


async function loadRefactoringChoiceProblemViaStream() {
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
      path: "/platform/refactoring-choice/problem",
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
      signal: state.problemStreamController.signal,
    });
  } finally {
    state.problemStreamController = null;
  }
}

async function animateRefactoringChoiceProblem(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    renderProblem(problem);
    return;
  }

  const languageId = problem.language || state.selectedLanguage;
  const languageLabel = state.languageMap[languageId]?.title || languageId || "-";
  const difficultyId = problem.difficulty || state.selectedDifficulty;
  const difficultyLabel = DIFFICULTY_LABELS[difficultyId] || difficultyId || "-";
  const facets = Array.isArray(problem.decisionFacets) ? problem.decisionFacets : [];

  if (elements.problemTitle) {
    await streamClient.typeText(elements.problemTitle, problem.title || "최적의 선택 문제", {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemLanguage) {
    await streamClient.typeText(elements.problemLanguage, `언어 ${languageLabel}`, { minDelay: 10, maxDelay: 16 });
  }
  if (elements.problemDifficulty) {
    await streamClient.typeText(elements.problemDifficulty, `난이도 ${difficultyLabel}`, {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.problemFacets) {
    await streamClient.typeText(
      elements.problemFacets,
      facets.length ? `판단 기준 ${facets.join(", ")}` : "판단 기준 -",
      {
      minDelay: 10,
      maxDelay: 16,
      }
    );
  }
  if (elements.problemScenario) {
    await streamClient.typeText(elements.problemScenario, problem.scenario || "시나리오 정보가 없습니다.", {
      minDelay: 10,
      maxDelay: 16,
    });
  }

  if (elements.problemConstraints) {
    const rows = Array.isArray(problem.constraints)
      ? problem.constraints.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
      : [];
    await streamClient.revealList(elements.problemConstraints, rows, {
      itemDelay: 70,
      renderItem: (item) => {
        const li = document.createElement("li");
        li.textContent = item;
        return li;
      },
    });
  }

  if (elements.problemOptions) {
    elements.problemOptions.innerHTML = "";
    const rows = Array.isArray(problem.options) ? problem.options : [];
    for (const option of rows) {
      const optionId = String(option.optionId || "").trim().toUpperCase();
      const card = document.createElement("article");
      card.className = "choice-option-card";
      const title = document.createElement("h4");
      title.textContent = `${optionId} - ${option.title || "옵션"}`;
      const code = document.createElement("pre");
      code.className = "code-block";
      card.appendChild(title);
      card.appendChild(code);
      elements.problemOptions.appendChild(card);
      await streamClient.revealLines(code, option.code || "// 코드 없음", { lineDelay: 70 });
      await streamClient.sleep(70);
    }
  }

  if (elements.problemPrompt) {
    await streamClient.typeText(
      elements.problemPrompt,
      problem.prompt || "A/B/C 중 가장 적절한 선택지를 고르고 근거를 작성해 주세요.",
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
    showToast("언어 정보가 없어 문제를 만들 수 없습니다.");
    return;
  }

  state.selectedLanguage = getSavedLanguage(state.languages);
  state.selectedDifficulty = getSavedDifficulty();
  renderLanguageDifficulty();

  setLoadingState(elements.loadBtn, true, "문제 생성 중...");
  if (elements.loadStatus) {
    elements.loadStatus.textContent = "AI가 최적의 선택 문제를 생성하고 있습니다.";
  }

  try {
    let payload = null;
    let streamed = false;
    let usedJsonFallback = false;
    let allowJsonFallback = false;

    try {
      payload = await loadRefactoringChoiceProblemViaStream();
      streamed = Boolean(payload);
    } catch (streamError) {
      allowJsonFallback = shouldFallbackToJson(streamError);
      if (!allowJsonFallback) {
        throw streamError;
      }
    }

    if (!payload && !allowJsonFallback) {
      const streamClient = getProblemStreamClient();
      allowJsonFallback = !streamClient || typeof streamClient.streamProblem !== "function";
    }

    if (!payload && allowJsonFallback) {
      if (elements.loadStatus) {
        elements.loadStatus.textContent = "스트리밍 연결이 끊겨 일반 모드로 재시도 중...";
      }
      setLoadingState(elements.loadBtn, true, "일반 모드 재시도 중...");
      payload = await apiRequest("/platform/refactoring-choice/problem", {
        method: "POST",
        body: {
          language: state.selectedLanguage,
          difficulty: state.selectedDifficulty,
        },
      });
      usedJsonFallback = true;
    }
    if (!payload) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    if (streamed || usedJsonFallback) {
      await animateRefactoringChoiceProblem(payload);
    } else {
      renderProblem(payload);
    }

    clearFeedback();
    showToast("최적의 선택 문제를 불러왔습니다.");
  } catch (error) {
    showToast(error.message || "문제 생성에 실패했습니다. 다시 시도해 주세요.");
  } finally {
    if (elements.loadStatus) {
    elements.loadStatus.textContent = "다른 문제가 필요하면 다시 문제 받기를 눌러주세요.";
    }
    setLoadingState(elements.loadBtn, false);
  }
}

function renderProblem(problem) {
  state.currentProblemId = problem.problemId || null;
  state.currentOptions = Array.isArray(problem.options) ? problem.options : [];

  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title || "최적의 선택 문제";
  }
  if (elements.problemScenario) {
    elements.problemScenario.textContent = problem.scenario || "시나리오 정보가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = problem.prompt || "A/B/C 중 가장 적절한 선택지를 고르고 근거를 작성해 주세요.";
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
  if (elements.problemFacets) {
    const facets = Array.isArray(problem.decisionFacets) ? problem.decisionFacets : [];
    elements.problemFacets.textContent = facets.length ? `판단 기준 ${facets.join(", ")}` : "판단 기준 -";
  }

  renderConstraintList(problem.constraints);
  renderOptionCards(state.currentOptions);
  resetOptionSelection();
  elements.reportForm?.reset();
}

function renderConstraintList(constraints) {
  if (!elements.problemConstraints) return;
  elements.problemConstraints.innerHTML = "";
  const rows = Array.isArray(constraints)
    ? constraints.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];
  if (rows.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "제약 조건이 없습니다.";
    elements.problemConstraints.appendChild(empty);
    return;
  }
  rows.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = row;
    elements.problemConstraints.appendChild(li);
  });
}

function renderOptionCards(options) {
  if (!elements.problemOptions) return;
  elements.problemOptions.innerHTML = "";
  const rows = Array.isArray(options) ? options : [];
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "옵션 정보가 없습니다.";
    elements.problemOptions.appendChild(empty);
    return;
  }
  rows.forEach((option) => {
    const optionId = String(option.optionId || "").trim().toUpperCase();
    const card = document.createElement("article");
    card.className = "choice-option-card";
    card.dataset.optionId = optionId;

    const title = document.createElement("h4");
    title.textContent = `${optionId} - ${option.title || "옵션"}`;

    const code = document.createElement("pre");
    code.className = "code-block";
    code.textContent = option.code || "// 코드 없음";

    card.appendChild(title);
    card.appendChild(code);
    elements.problemOptions.appendChild(card);
  });
}

function resetOptionSelection() {
  elements.optionRadios?.forEach((radio) => {
    radio.checked = false;
  });
  highlightSelectedOption("");
}

function highlightSelectedOption(optionId) {
  const cards = elements.problemOptions?.querySelectorAll(".choice-option-card") || [];
  cards.forEach((card) => {
    card.classList.toggle("selected", card.dataset.optionId === optionId);
  });
}

async function handleSubmitReport(event) {
  event.preventDefault();
  if (!state.currentProblemId) {
    showToast("먼저 문제를 생성해 주세요.");
    return;
  }

  const selectedOption = getSelectedOption();
  if (!selectedOption) {
    showToast("A/B/C 중 하나를 선택해 주세요.");
    return;
  }

  const report = (elements.reportText?.value || "").trim();
  if (!report) {
    showToast("선택 근거를 입력해 주세요.");
    return;
  }

  const submitBtn = elements.reportForm?.querySelector("button[type='submit']");
  setLoadingState(submitBtn, true, "채점 중...");

  try {
    const payload = await apiRequest("/platform/refactoring-choice/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        selectedOption,
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

function getSelectedOption() {
  for (const radio of elements.optionRadios || []) {
    if (radio.checked) {
      return radio.value;
    }
  }
  return "";
}

function renderFeedback(payload) {
  const score = Number(payload.score);
  const hasScore = Number.isFinite(score);
  const verdict = payload.verdict || (payload.correct ? "passed" : "failed");
  const threshold = Number(payload.passThreshold ?? 70);
  const feedback = payload.feedback || {};
  const foundTypes = Array.isArray(payload.foundTypes) ? payload.foundTypes : [];
  const missedTypes = Array.isArray(payload.missedTypes) ? payload.missedTypes : [];
  const selectedOption = String(payload.selectedOption || "").trim().toUpperCase();
  const bestOption = String(payload.bestOption || "").trim().toUpperCase();

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

  if (elements.selectedOption) {
    elements.selectedOption.textContent = selectedOption || "-";
  }
  if (elements.bestOption) {
    elements.bestOption.textContent = bestOption || "-";
  }
  if (elements.foundTypes) {
    elements.foundTypes.textContent = foundTypes.length ? foundTypes.join(", ") : "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = missedTypes.length ? missedTypes.join(", ") : "-";
  }
  renderOptionReviews(payload.optionReviews);
  if (elements.referenceReport) {
    elements.referenceReport.textContent = payload.referenceReport || "모범 리포트가 제공되지 않았습니다.";
  }
}

function renderOptionReviews(optionReviews) {
  if (!elements.optionReviews) return;
  elements.optionReviews.innerHTML = "";
  const rows = Array.isArray(optionReviews)
    ? optionReviews
        .filter((row) => row && typeof row === "object")
        .map((row) => ({
          optionId: String(row.optionId || "").trim().toUpperCase(),
          summary: String(row.summary || "").trim(),
        }))
        .filter((row) => row.optionId && row.summary)
    : [];

  if (rows.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "옵션별 비교 요약이 없습니다.";
    elements.optionReviews.appendChild(li);
    return;
  }

  rows.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = `${row.optionId}: ${row.summary}`;
    elements.optionReviews.appendChild(li);
  });
}

function clearProblem() {
  state.currentProblemId = null;
  state.currentOptions = [];
  if (elements.problemTitle) {
    elements.problemTitle.textContent = "문제를 불러오면 최적의 선택을 할 수 있습니다.";
  }
  if (elements.problemScenario) {
    elements.problemScenario.textContent = "아직 불러온 시나리오가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = "문제를 받은 뒤 선택 근거를 작성해 주세요.";
  }
  if (elements.problemLanguage) {
    elements.problemLanguage.textContent = "언어 -";
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = "난이도 -";
  }
  if (elements.problemFacets) {
    elements.problemFacets.textContent = "판단 기준 -";
  }
  renderConstraintList([]);
  renderOptionCards([]);
  resetOptionSelection();
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
  if (elements.selectedOption) {
    elements.selectedOption.textContent = "-";
  }
  if (elements.bestOption) {
    elements.bestOption.textContent = "-";
  }
  if (elements.foundTypes) {
    elements.foundTypes.textContent = "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = "-";
  }
  renderList(elements.strengths, [], "강점이 없습니다.");
  renderList(elements.improvements, [], "개선 포인트가 없습니다.");
  renderOptionReviews([]);
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

function getSavedLanguage(languages = []) {
  const saved = window.localStorage.getItem(LANGUAGE_KEY);
  if (saved && languages.some((lang) => lang.id === saved)) {
    return saved;
  }
  const fallback = languages[0]?.id || DEFAULT_LANGUAGE;
  if (fallback) {
    window.localStorage.setItem(LANGUAGE_KEY, fallback);
  }
  return fallback;
}

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  if (DIFFICULTY_OPTIONS.has(value)) {
    return value;
  }
  return DEFAULT_DIFFICULTY;
}

function getDisplayName(token) {
  const cached = window.localStorage.getItem(DISPLAY_NAME_KEY);
  if (cached) return cached;
  if (authClient?.parseUsername) return authClient.parseUsername(token);
  return parseUsername(token);
}

function parseUsername(token) {
  if (!token) return "";
  return token.split(":", 1)[0];
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}




