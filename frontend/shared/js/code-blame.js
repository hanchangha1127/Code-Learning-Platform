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
  currentCommits: [],
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
  elements.userDisplay = document.getElementById("cb-user-display");
  elements.languageDisplay = document.getElementById("cb-language-display");
  elements.difficultyDisplay = document.getElementById("cb-difficulty-display");
  elements.loadBtn = document.getElementById("cb-load-btn");
  elements.loadStatus = document.getElementById("cb-load-status");
  elements.problemTitle = document.getElementById("cb-problem-title");
  elements.problemLanguage = document.getElementById("cb-problem-language");
  elements.problemDifficulty = document.getElementById("cb-problem-difficulty");
  elements.problemCount = document.getElementById("cb-problem-count");
  elements.errorLog = document.getElementById("cb-error-log");
  elements.commitList = document.getElementById("cb-commit-list");
  elements.problemPrompt = document.getElementById("cb-problem-prompt");
  elements.reportForm = document.getElementById("cb-report-form");
  elements.reportText = document.getElementById("cb-report-text");
  elements.score = document.getElementById("cb-score");
  elements.verdict = document.getElementById("cb-verdict");
  elements.thresholdText = document.getElementById("cb-threshold-text");
  elements.feedbackSummary = document.getElementById("cb-feedback-summary");
  elements.strengths = document.getElementById("cb-strengths");
  elements.improvements = document.getElementById("cb-improvements");
  elements.selectedCommits = document.getElementById("cb-selected-commits");
  elements.culpritCommits = document.getElementById("cb-culprit-commits");
  elements.foundTypes = document.getElementById("cb-found-types");
  elements.missedTypes = document.getElementById("cb-missed-types");
  elements.commitReviews = document.getElementById("cb-commit-reviews");
  elements.referenceReport = document.getElementById("cb-reference-report");
  elements.toast = document.getElementById("cb-toast");
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
        ? "문제 받기를 눌러 범인 찾기 문제를 생성하세요."
        : "언어 설정을 확인하고 다시 시도해 주세요.";
    }
  }
}

async function tryResumeReview() {
  if (!reviewResume?.resumeReviewProblem) {
    return false;
  }
  return reviewResume.resumeReviewProblem({
    mode: "code-blame",
    apiRequest,
    applyProblem: async (problem) => {
      renderProblem(problem);
      clearFeedback();
      if (elements.loadStatus) {
        elements.loadStatus.textContent = "같은 문제를 다시 열었습니다. 원인 커밋을 다시 추적해 보세요.";
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


async function loadCodeBlameProblemViaStream() {
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
      path: "/platform/code-blame/problem",
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

async function animateCodeBlameProblem(problem) {
  const streamClient = getProblemStreamClient();
  if (!streamClient || typeof streamClient.typeText !== "function") {
    renderProblem(problem);
    return;
  }

  const languageId = problem.language || state.selectedLanguage;
  const languageLabel = state.languageMap[languageId]?.title || languageId || "-";
  const difficultyId = problem.difficulty || state.selectedDifficulty;
  const difficultyLabel = DIFFICULTY_LABELS[difficultyId] || difficultyId || "-";
  const commits = Array.isArray(problem.commits) ? problem.commits : [];

  if (elements.problemTitle) {
    await streamClient.typeText(elements.problemTitle, problem.title || "범인 찾기 문제", { minDelay: 10, maxDelay: 16 });
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
  if (elements.problemCount) {
    await streamClient.typeText(elements.problemCount, `커밋 수 ${commits.length || "-"}`, {
      minDelay: 10,
      maxDelay: 16,
    });
  }
  if (elements.errorLog) {
    await streamClient.revealLines(elements.errorLog, problem.errorLog || "# 에러 로그가 없습니다.", {
      lineDelay: 70,
    });
  }

  if (elements.commitList) {
    elements.commitList.innerHTML = "";
    for (const commit of commits) {
      const optionId = String(commit.optionId || "").trim().toUpperCase();
      const commitTitle = String(commit.title || "커밋").trim() || "커밋";
      const card = document.createElement("article");
      card.className = "commit-option-card";
      const header = document.createElement("label");
      header.className = "commit-option-header";
      const title = document.createElement("span");
      title.textContent = `${optionId} - ${commitTitle}`;
      header.appendChild(title);
      const diff = document.createElement("pre");
      diff.className = "code-block";
      card.appendChild(header);
      card.appendChild(diff);
      elements.commitList.appendChild(card);
      await streamClient.revealLines(diff, commit.diff || "diff 정보가 없습니다.", { lineDelay: 70 });
      await streamClient.sleep(70);
    }
  }

  if (elements.problemPrompt) {
    await streamClient.typeText(elements.problemPrompt, problem.prompt || "에러 로그와 diff를 비교해 범인 커밋을 추리해 보세요.", {
      minDelay: 10,
      maxDelay: 16,
    });
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
    elements.loadStatus.textContent = "AI가 범인 찾기 문제를 생성하고 있습니다.";
  }

  try {
    let payload = null;
    let streamed = false;
    let usedJsonFallback = false;
    let allowJsonFallback = false;

    try {
      payload = await loadCodeBlameProblemViaStream();
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
      payload = await apiRequest("/platform/code-blame/problem", {
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
      await animateCodeBlameProblem(payload);
    } else {
      renderProblem(payload);
    }

    clearFeedback();
    showToast("범인 찾기 문제를 불러왔습니다.");
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
  state.currentCommits = Array.isArray(problem.commits) ? problem.commits : [];

  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title || "범인 찾기 문제";
  }
  if (elements.errorLog) {
    elements.errorLog.textContent = problem.errorLog || "# 에러 로그가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = problem.prompt || "에러 로그와 diff를 비교해 범인 커밋을 추리해 보세요.";
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
  if (elements.problemCount) {
    elements.problemCount.textContent = `커밋 수 ${state.currentCommits.length || "-"}`;
  }

  renderCommitList(state.currentCommits);
  elements.reportForm?.reset();
}

function renderCommitList(commits) {
  if (!elements.commitList) return;
  elements.commitList.innerHTML = "";

  const rows = Array.isArray(commits) ? commits : [];
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "커밋 정보가 없습니다.";
    elements.commitList.appendChild(empty);
    return;
  }

  rows.forEach((commit) => {
    const optionId = String(commit.optionId || "").trim().toUpperCase();
      const commitTitle = String(commit.title || "커밋").trim() || "커밋";
    const card = document.createElement("article");
    card.className = "commit-option-card";
    card.dataset.optionId = optionId;

    const header = document.createElement("label");
    header.className = "commit-option-header";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "commit-checkbox";
    checkbox.value = optionId;
    const title = document.createElement("span");
    title.textContent = `${optionId} - ${commitTitle}`;
    header.append(checkbox, title);

    const diff = document.createElement("pre");
    diff.className = "code-block";
    diff.textContent = commit.diff || "diff 정보가 없습니다.";

    card.appendChild(header);
    card.appendChild(diff);
    elements.commitList.appendChild(card);
  });

  const checkboxes = elements.commitList.querySelectorAll(".commit-checkbox");
  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const selected = getSelectedCommits();
      if (selected.length > 2) {
        checkbox.checked = false;
        showToast("커밋은 최대 2개까지만 선택할 수 있습니다.");
      }
      syncSelectedCardStyles();
    });
  });
}

function getSelectedCommits() {
  const checkboxes = elements.commitList?.querySelectorAll(".commit-checkbox:checked") || [];
  return Array.from(checkboxes).map((item) => String(item.value || "").trim().toUpperCase());
}

function syncSelectedCardStyles(culpritCommits = []) {
  const culpritSet = new Set((Array.isArray(culpritCommits) ? culpritCommits : []).map((item) => String(item || "").trim().toUpperCase()));
  const selectedSet = new Set(getSelectedCommits());
  const cards = elements.commitList?.querySelectorAll(".commit-option-card") || [];
  cards.forEach((card) => {
    const optionId = String(card.dataset.optionId || "").trim().toUpperCase();
    card.classList.toggle("selected", selectedSet.has(optionId));
    card.classList.toggle("culprit", culpritSet.has(optionId));
  });
}

async function handleSubmitReport(event) {
  event.preventDefault();
  if (!state.currentProblemId) {
    showToast("먼저 문제를 생성해 주세요.");
    return;
  }

  const selectedCommits = getSelectedCommits();
  if (selectedCommits.length === 0 || selectedCommits.length > 2) {
    showToast("커밋을 1~2개 선택해 주세요.");
    return;
  }

  const report = (elements.reportText?.value || "").trim();
  if (!report) {
    showToast("근거 리포트를 입력해 주세요.");
    return;
  }

  const submitBtn = elements.reportForm?.querySelector("button[type='submit']");
  setLoadingState(submitBtn, true, "채점 중...");

  try {
    const payload = await apiRequest("/platform/code-blame/submit", {
      method: "POST",
      body: {
        problemId: state.currentProblemId,
        selectedCommits,
        report,
      },
    });
    renderFeedback(payload);
    syncSelectedCardStyles(payload.culpritCommits || []);
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
  const selectedCommits = Array.isArray(payload.selectedCommits) ? payload.selectedCommits : [];
  const culpritCommits = Array.isArray(payload.culpritCommits) ? payload.culpritCommits : [];

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

  if (elements.selectedCommits) {
    elements.selectedCommits.textContent = selectedCommits.length ? selectedCommits.join(", ") : "-";
  }
  if (elements.culpritCommits) {
    elements.culpritCommits.textContent = culpritCommits.length ? culpritCommits.join(", ") : "-";
  }
  if (elements.foundTypes) {
    elements.foundTypes.textContent = foundTypes.length ? foundTypes.join(", ") : "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = missedTypes.length ? missedTypes.join(", ") : "-";
  }
  if (elements.referenceReport) {
    elements.referenceReport.textContent = payload.referenceReport || "모범 추론 리포트가 제공되지 않았습니다.";
  }
  renderCommitReviews(payload.commitReviews);
}

function renderCommitReviews(items) {
  if (!elements.commitReviews) return;
  elements.commitReviews.innerHTML = "";

  const rows = Array.isArray(items)
    ? items
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          optionId: String(item.optionId || "").trim().toUpperCase(),
          summary: String(item.summary || "").trim(),
        }))
        .filter((item) => item.optionId && item.summary)
    : [];

  if (!rows.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "커밋 비교 요약이 없습니다.";
    elements.commitReviews.appendChild(li);
    return;
  }

  rows.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.optionId}: ${item.summary}`;
    elements.commitReviews.appendChild(li);
  });
}

function clearProblem() {
  state.currentProblemId = null;
  state.currentCommits = [];
  if (elements.problemTitle) {
    elements.problemTitle.textContent = "문제를 불러오면 범인 커밋을 선택할 수 있습니다.";
  }
  if (elements.problemLanguage) {
    elements.problemLanguage.textContent = "언어 -";
  }
  if (elements.problemDifficulty) {
    elements.problemDifficulty.textContent = "난이도 -";
  }
  if (elements.problemCount) {
    elements.problemCount.textContent = "커밋 수 -";
  }
  if (elements.errorLog) {
    elements.errorLog.textContent = "# 아직 불러온 로그가 없습니다.";
  }
  if (elements.problemPrompt) {
    elements.problemPrompt.textContent = "문제를 받은 뒤 범인 커밋을 선택하고 근거 리포트를 작성해 주세요.";
  }
  if (elements.commitList) {
    elements.commitList.innerHTML = "";
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
  if (elements.selectedCommits) {
    elements.selectedCommits.textContent = "-";
  }
  if (elements.culpritCommits) {
    elements.culpritCommits.textContent = "-";
  }
  if (elements.foundTypes) {
    elements.foundTypes.textContent = "-";
  }
  if (elements.missedTypes) {
    elements.missedTypes.textContent = "-";
  }
  if (elements.referenceReport) {
    elements.referenceReport.textContent = "제출 후 항상 공개됩니다.";
  }
  renderCommitReviews([]);
}

function renderList(target, items, emptyText) {
  if (!target) return;
  target.innerHTML = "";
  const normalized = Array.isArray(items)
    ? items.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];
  if (!normalized.length) {
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
    button.textContent = button.dataset.originalText || button.textContent;
  }
}

function showToast(message) {
  if (!elements.toast) return;
  elements.toast.textContent = message || "요청 처리에 실패했습니다.";
  elements.toast.classList.remove("hidden");
  elements.toast.classList.add("visible");
  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }
  state.toastTimer = window.setTimeout(() => {
    elements.toast?.classList.remove("visible");
    elements.toast?.classList.add("hidden");
    state.toastTimer = null;
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
  if (authClient) {
    return authClient.parseUsername(token);
  }
  const cached = window.localStorage.getItem(DISPLAY_NAME_KEY);
  if (cached) return cached;
  if (!token) return "";
  return token.split(":", 1)[0];
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}




