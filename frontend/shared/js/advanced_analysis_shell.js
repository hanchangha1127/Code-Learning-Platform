const TOKEN_KEY = "code-learning-token";
const DISPLAY_NAME_KEY = "code-learning-display-name";
const LANGUAGE_KEY = "code-learning-language";
const DIFFICULTY_KEY = "code-learning-difficulty";
const DEFAULT_LANGUAGE = "python";
const DEFAULT_DIFFICULTY = "beginner";
const DEFAULT_TOAST_DURATION = 3200;
const MODE_JOB_POLL_INTERVAL = 1200;
const MODE_JOB_MAX_POLL_ATTEMPTS = 60;

const authClient = window.CodeAuth || null;
const streamClient = window.CodeProblemStream || null;

const DIFFICULTY_OPTIONS = new Set(["beginner", "intermediate", "advanced"]);
const DIFFICULTY_LABELS = {
  beginner: "초급",
  intermediate: "중급",
  advanced: "고급",
};

const KEYWORD_PATTERN =
  /\b(async|await|class|const|constructor|def|else|export|for|from|function|if|import|new|return|try|while)\b/g;
const STRING_PATTERN = /(`[^`]*`|"[^"]*"|'[^']*')/g;

const MODE_CONFIGS = {
  "single-file": {
    apiPath: "/platform/single-file-analysis/problem",
    submitPath: "/platform/single-file-analysis/submit",
    workspace: "single-file-analysis.workspace",
    headline: "하나의 파일만 보고 흐름과 상태 변화를 설명하는 고급 분석 모드입니다.",
    summary: "AI가 단일 파일 분석 문제를 생성합니다. 진입 함수, 상태 변화, 예외 흐름을 읽고 서술형 리포트로 정리하세요.",
    fileRange: "파일 수 1개",
    languageRange: "언어 범위 단일 언어",
    scope: "단일 파일 흐름 분석",
    idleStatus: "문제 받기를 누르면 AI가 단일 파일 분석 문제를 생성합니다.",
    loadingStatus: "AI가 단일 파일 분석 문제를 생성하고 있습니다.",
    readyStatus: "단일 파일 분석 문제가 준비되었습니다.",
    emptyPrompt: "문제를 받은 뒤 파일 하나를 읽고 제어 흐름, 상태 변화, 예외 조건을 설명하세요.",
    emptyProblemTitle: "문제를 아직 불러오지 않았습니다.",
    fallbackChecklist: [
      "진입 함수와 반환 값을 추적하세요.",
      "상태 변화와 예외 분기를 정리하세요.",
      "경계 조건과 테스트 포인트를 설명하세요.",
    ],
  },
  "multi-file": {
    apiPath: "/platform/multi-file-analysis/problem",
    submitPath: "/platform/multi-file-analysis/submit",
    workspace: "multi-file-analysis.workspace",
    headline: "여러 파일의 호출 흐름과 책임 분리를 설명하는 고급 분석 모드입니다.",
    summary: "AI가 2~6개 파일로 구성된 분석 문제를 생성합니다. 파일 간 호출 순서와 결합 지점을 연결해서 설명하세요.",
    fileRange: "파일 수 2~6개",
    languageRange: "언어 범위 단일 언어",
    scope: "모듈 간 호출 분석",
    idleStatus: "문제 받기를 누르면 AI가 다중 파일 분석 문제를 생성합니다.",
    loadingStatus: "AI가 다중 파일 분석 문제를 생성하고 있습니다.",
    readyStatus: "다중 파일 분석 문제가 준비되었습니다.",
    emptyPrompt: "문제를 받은 뒤 파일 간 호출 순서, 책임 분리, 결합 지점을 설명하세요.",
    emptyProblemTitle: "문제를 아직 불러오지 않았습니다.",
    fallbackChecklist: [
      "진입 지점부터 실제 비즈니스 로직까지 호출 순서를 정리하세요.",
      "파일별 책임과 결합 지점을 나눠 설명하세요.",
      "중복 책임이나 테스트 취약 지점을 찾아보세요.",
    ],
  },
  fullstack: {
    apiPath: "/platform/fullstack-analysis/problem",
    submitPath: "/platform/fullstack-analysis/submit",
    workspace: "fullstack-analysis.workspace",
    headline: "프론트엔드와 백엔드를 함께 읽으며 사용자 요청의 전체 흐름을 분석하는 고급 모드입니다.",
    summary: "AI가 3~8개 파일로 구성된 풀스택 분석 문제를 생성합니다. 사용자 액션부터 API, 서버 처리, UI 반영까지 설명하세요.",
    fileRange: "파일 수 3~8개",
    languageRange: "언어 범위 혼합 언어",
    scope: "풀스택 요청 흐름 분석",
    idleStatus: "문제 받기를 누르면 AI가 풀스택 분석 문제를 생성합니다.",
    loadingStatus: "AI가 풀스택 분석 문제를 생성하고 있습니다.",
    readyStatus: "풀스택 코드 분석 문제가 준비되었습니다.",
    emptyPrompt: "문제를 받은 뒤 사용자 액션에서 UI 반영까지 이어지는 전체 흐름을 설명하세요.",
    emptyProblemTitle: "문제를 아직 불러오지 않았습니다.",
    fallbackChecklist: [
      "사용자 액션이 어디에서 시작되는지 확인하세요.",
      "API 호출과 서버 진입 지점을 연결하세요.",
      "응답 데이터가 UI에 어떻게 반영되는지 설명하세요.",
      "경계 조건, 실패 지점, 복구 포인트를 정리하세요.",
    ],
  },
};

const state = {
  token: null,
  modeConfig: null,
  selectedLanguage: DEFAULT_LANGUAGE,
  selectedDifficulty: DEFAULT_DIFFICULTY,
  languageMap: {},
  currentProblem: null,
  activeFileId: null,
  problemStreamController: null,
  submitJobId: null,
  submitPollTimer: null,
  submitPollAttempts: 0,
  submissionPhase: "idle",
  latestResult: null,
  submitPending: false,
  toastTimer: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청을 처리하지 못했습니다.",
});

const elements = {};

function cacheDom() {
  elements.userChip = document.getElementById("advanced-user-display");
  elements.workspaceTitle = document.getElementById("advanced-workspace-title");
  elements.modeState = document.getElementById("advanced-mode-state");
  elements.modeHeadline = document.getElementById("advanced-mode-headline");
  elements.modeSummary = document.getElementById("advanced-mode-summary");
  elements.fileRange = document.getElementById("advanced-mode-file-range");
  elements.languageRange = document.getElementById("advanced-mode-language-range");
  elements.scope = document.getElementById("advanced-mode-scope");
  elements.selectedLanguage = document.getElementById("advanced-selected-language");
  elements.selectedDifficulty = document.getElementById("advanced-selected-difficulty");
  elements.loadButton = document.getElementById("advanced-load-btn");
  elements.loadStatus = document.getElementById("advanced-load-status");
  elements.problemTitle = document.getElementById("advanced-problem-title");
  elements.fileStrip = document.getElementById("advanced-file-strip");
  elements.fileRail = document.getElementById("advanced-file-rail");
  elements.breadcrumbs = document.getElementById("advanced-editor-breadcrumbs");
  elements.activeFileName = document.getElementById("advanced-active-file-name");
  elements.activeFilePath = document.getElementById("advanced-active-file-path");
  elements.activeFileRole = document.getElementById("advanced-active-file-role");
  elements.activeFileLanguage = document.getElementById("advanced-active-file-language");
  elements.statusbarLeft = document.getElementById("advanced-statusbar-left");
  elements.statusbarRight = document.getElementById("advanced-statusbar-right");
  elements.codeView = document.getElementById("advanced-code-view");
  elements.taskPrompt = document.getElementById("advanced-task-prompt");
  elements.checklist = document.getElementById("advanced-checklist");
  elements.reportText = document.getElementById("advanced-report-text");
  elements.submitButton = document.getElementById("advanced-submit-btn");
  elements.statusCards = document.getElementById("advanced-status-cards");
  elements.resultPanel = document.getElementById("advanced-result-panel");
  elements.resultScore = document.getElementById("advanced-result-score");
  elements.resultVerdict = document.getElementById("advanced-result-verdict");
  elements.resultThreshold = document.getElementById("advanced-result-threshold");
  elements.resultSummary = document.getElementById("advanced-result-summary");
  elements.resultStrengths = document.getElementById("advanced-result-strengths");
  elements.resultImprovements = document.getElementById("advanced-result-improvements");
  elements.referenceReport = document.getElementById("advanced-reference-report");
  elements.toast = document.getElementById("advanced-analysis-toast");
  elements.statusHeadMessage = document.querySelector(".advanced-status-head p");
}

async function init() {
  cacheDom();
  state.modeConfig = resolveModeConfig();
  if (!state.modeConfig) {
    return;
  }

  state.token = await ensureSession();
  if (!state.token) {
    return;
  }

  state.selectedLanguage = getSavedLanguage();
  state.selectedDifficulty = getSavedDifficulty();

  bindEvents();
  renderStaticChrome();
  renderUserChip();
  await tryLoadLanguages();
  renderLanguageDifficulty();
  renderEmptyState();
}

function resolveModeConfig() {
  const modeId = document.body?.dataset?.advancedAnalysisMode || "";
  return MODE_CONFIGS[modeId] || null;
}

async function ensureSession() {
  if (authClient?.ensureActiveSession) {
    return authClient.ensureActiveSession({
      token: window.localStorage.getItem(TOKEN_KEY),
      redirectTo: "/index.html",
    });
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

function bindEvents() {
  elements.fileStrip?.addEventListener("click", handleFileSelect);
  elements.fileRail?.addEventListener("click", handleFileSelect);
  elements.loadButton?.addEventListener("click", () => {
    void loadProblem();
  });
  elements.submitButton?.addEventListener("click", (event) => {
    void handleSubmitReport(event);
  });
  elements.reportText?.addEventListener("input", updateSubmitButtonState);
  window.addEventListener("beforeunload", () => {
    stopSubmitPolling();
    if (state.problemStreamController) {
      state.problemStreamController.abort();
      state.problemStreamController = null;
    }
  });
}

async function tryLoadLanguages() {
  try {
    const payload = await apiRequest("/platform/languages");
    const languages = Array.isArray(payload.languages) ? payload.languages : [];
    state.languageMap = languages.reduce((acc, item) => {
      if (item?.id) {
        acc[item.id] = item.title || item.id;
      }
      return acc;
    }, {});
  } catch (error) {
    console.error(error);
    state.languageMap = {};
  }
}

function renderStaticChrome() {
  const config = state.modeConfig;
  if (!config) {
    return;
  }
  if (elements.workspaceTitle) {
    elements.workspaceTitle.textContent = config.workspace;
  }
  if (elements.modeState) {
    elements.modeState.textContent = "문제 대기";
  }
  if (elements.modeHeadline) {
    elements.modeHeadline.textContent = config.headline;
  }
  if (elements.modeSummary) {
    elements.modeSummary.textContent = config.summary;
  }
  if (elements.fileRange) {
    elements.fileRange.textContent = config.fileRange;
  }
  if (elements.languageRange) {
    elements.languageRange.textContent = config.languageRange;
  }
  if (elements.scope) {
    elements.scope.textContent = config.scope;
  }
  if (elements.loadStatus) {
    elements.loadStatus.textContent = config.idleStatus;
  }
  if (elements.submitButton) {
    elements.submitButton.textContent = "리포트 제출";
  }
  if (elements.statusHeadMessage) {
    elements.statusHeadMessage.textContent = "문제 생성, 리포트 제출, 채점 결과가 이 영역에서 단계별로 갱신됩니다.";
  }
  renderStatusCards(false);
}

function renderLanguageDifficulty() {
  const languageLabel = state.languageMap[state.selectedLanguage] || state.selectedLanguage || DEFAULT_LANGUAGE;
  const difficultyLabel = DIFFICULTY_LABELS[state.selectedDifficulty] || state.selectedDifficulty;
  if (elements.selectedLanguage) {
    elements.selectedLanguage.textContent = `언어 ${languageLabel}`;
  }
  if (elements.selectedDifficulty) {
    elements.selectedDifficulty.textContent = `난이도 ${difficultyLabel}`;
  }
}

function renderUserChip() {
  if (!elements.userChip) {
    return;
  }
  const cached = window.localStorage.getItem(DISPLAY_NAME_KEY);
  if (cached) {
    elements.userChip.textContent = cached;
    return;
  }
  if (authClient?.parseUsername) {
    elements.userChip.textContent = authClient.parseUsername(state.token);
    return;
  }
  elements.userChip.textContent = state.token ? state.token.split(":", 1)[0] : "user";
}

function renderEmptyState() {
  const config = state.modeConfig;
  if (!config) {
    return;
  }

  state.currentProblem = null;
  state.activeFileId = null;
  stopSubmitPolling();
  state.submissionPhase = "idle";
  state.latestResult = null;
  state.submitPending = false;

  if (elements.problemTitle) {
    elements.problemTitle.textContent = config.emptyProblemTitle;
  }
  if (elements.taskPrompt) {
    elements.taskPrompt.textContent = config.emptyPrompt;
  }
  if (elements.reportText) {
    elements.reportText.value = "";
    elements.reportText.placeholder = "분석 리포트를 작성하세요.";
  }

  renderChecklist(config.fallbackChecklist);
  renderFileCollections([]);
  renderActiveFile(null);
  clearFeedback();
  renderStatusCards(false);
  updateSubmitButtonState();
}

async function loadProblem() {
  const config = state.modeConfig;
  if (!config) {
    return;
  }
  if (!state.selectedLanguage) {
    showToast("기본 언어 설정을 확인해 주세요.");
    return;
  }

  if (state.problemStreamController) {
    state.problemStreamController.abort();
    state.problemStreamController = null;
  }

  setLoadingState(elements.loadButton, true, "문제 생성 중...");
  if (elements.modeState) {
    elements.modeState.textContent = "생성 중";
  }
  if (elements.loadStatus) {
    elements.loadStatus.textContent = config.loadingStatus;
  }

  stopSubmitPolling();
  state.submissionPhase = "idle";
  state.latestResult = null;
  state.submitPending = false;
  clearFeedback();
  updateSubmitButtonState();

  try {
    let payload = null;
    let streamed = false;
    let allowJsonFallback = false;

    try {
      payload = await loadProblemViaStream(config.apiPath);
      streamed = Boolean(payload);
    } catch (streamError) {
      allowJsonFallback = shouldFallbackToJson(streamError);
      if (!allowJsonFallback) {
        throw streamError;
      }
    }

    if (!payload && !allowJsonFallback) {
      allowJsonFallback = !streamClient || typeof streamClient.streamProblem !== "function";
    }

    if (!payload && allowJsonFallback) {
      setLoadingState(elements.loadButton, true, "문제 불러오는 중...");
      payload = await apiRequest(config.apiPath, {
        method: "POST",
        body: {
          language: state.selectedLanguage,
          difficulty: state.selectedDifficulty,
        },
      });
    }

    const problem = normalizeProblemPayload(payload);
    if (!problem) {
      throw new Error("문제를 불러오지 못했습니다.");
    }

    state.currentProblem = problem;
    state.activeFileId = problem.files[0]?.id || null;
    state.submissionPhase = "ready";
    state.submitPending = false;
    clearFeedback();

    if (streamed) {
      await animateProblemRender(problem);
    } else {
      renderProblem(problem);
    }

    renderStatusCards(true);
    if (elements.modeState) {
      elements.modeState.textContent = "문제 준비 완료";
    }
    if (elements.loadStatus) {
      elements.loadStatus.textContent = problem.summary || config.readyStatus;
    }
    updateSubmitButtonState();
    showToast("문제를 불러왔습니다.");
  } catch (error) {
    console.error(error);
    state.submitPending = false;
    if (elements.modeState) {
      elements.modeState.textContent = "문제 생성 실패";
    }
    if (elements.loadStatus) {
      elements.loadStatus.textContent = error.message || "문제를 불러오지 못했습니다.";
    }
    if (!state.currentProblem) {
      renderEmptyState();
    } else {
      renderStatusCards(true);
      updateSubmitButtonState();
    }
    showToast(error.message || "문제를 불러오지 못했습니다.");
  } finally {
    setLoadingState(elements.loadButton, false);
  }
}

async function loadProblemViaStream(path) {
  if (!streamClient || typeof streamClient.streamProblem !== "function") {
    return null;
  }

  state.problemStreamController = new AbortController();
  try {
    return await streamClient.streamProblem({
      path,
      token: state.token,
      body: {
        language: state.selectedLanguage,
        difficulty: state.selectedDifficulty,
      },
      onStatus: (statusPayload) => {
        if (elements.loadStatus && statusPayload?.message) {
          elements.loadStatus.textContent = statusPayload.message;
        }
        if (!elements.modeState || !statusPayload?.phase) {
          return;
        }
        if (statusPayload.phase === "queued") {
          elements.modeState.textContent = "대기 중";
        } else if (statusPayload.phase === "generating") {
          elements.modeState.textContent = "생성 중";
        } else if (statusPayload.phase === "rendering") {
          elements.modeState.textContent = "표시 중";
          setLoadingState(elements.loadButton, true, "문제 표시 중...");
        }
      },
      signal: state.problemStreamController.signal,
    });
  } finally {
    state.problemStreamController = null;
  }
}

function shouldFallbackToJson(error) {
  if (!streamClient || typeof streamClient.shouldFallbackToJson !== "function") {
    return false;
  }
  return Boolean(streamClient.shouldFallbackToJson(error));
}

function normalizeProblemPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const source = payload.problem && typeof payload.problem === "object" ? payload.problem : payload;
  const files = Array.isArray(source.files)
    ? source.files.map((file, index) => normalizeFile(file, index)).filter((file) => file && file.content)
    : [];

  if (files.length === 0) {
    return null;
  }

  return {
    problemId: String(source.problemId || source.id || ""),
    title: String(source.title || "AI 분석 문제"),
    summary: String(source.summary || ""),
    prompt: String(source.prompt || ""),
    workspace: String(source.workspace || state.modeConfig?.workspace || "analysis.workspace"),
    checklist: Array.isArray(source.checklist)
      ? source.checklist.map((item) => String(item || "").trim()).filter(Boolean)
      : [...(state.modeConfig?.fallbackChecklist || [])],
    language: String(source.language || state.selectedLanguage),
    difficulty: String(source.difficulty || state.selectedDifficulty),
    files,
  };
}

function normalizeFile(file, index) {
  if (!file || typeof file !== "object") {
    return null;
  }
  const path = String(file.path || file.name || `src/file_${index + 1}.txt`);
  const name = String(file.name || path.split("/").pop() || `file_${index + 1}.txt`);
  const language = String(file.language || state.selectedLanguage || DEFAULT_LANGUAGE).toLowerCase();
  const role = String(file.role || "module");
  const content = String(file.content || file.code || "").replace(/\r\n/g, "\n");
  const id = String(file.id || buildFileId(path, index));
  return { id, path, name, language, role, content };
}

function buildFileId(path, index) {
  const token = String(path || "")
    .toLowerCase()
    .split("")
    .map((ch) => (/[a-z0-9]/.test(ch) ? ch : "-"))
    .join("")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return token || `file-${index + 1}`;
}

function renderProblem(problem) {
  renderProblemHeader(problem);
  renderChecklist(problem.checklist);
  renderFileCollections(problem.files);
  renderActiveFile(getActiveFile(problem.files));
}

async function animateProblemRender(problem) {
  renderProblemHeader(problem);
  renderChecklist(problem.checklist);
  renderFileCollections(problem.files);
  const activeFile = getActiveFile(problem.files);
  renderActiveFileMeta(activeFile, problem.files.length);
  if (elements.codeView) {
    await renderCodeView(activeFile?.content || "", { animate: true });
  }
  setActiveButtons(activeFile?.id || "");
}

function renderProblemHeader(problem) {
  if (elements.workspaceTitle) {
    elements.workspaceTitle.textContent = problem.workspace;
  }
  if (elements.problemTitle) {
    elements.problemTitle.textContent = problem.title;
  }
  if (elements.taskPrompt) {
    elements.taskPrompt.textContent = problem.prompt || state.modeConfig?.emptyPrompt || "";
  }
}

function renderChecklist(items) {
  if (!elements.checklist) {
    return;
  }
  elements.checklist.innerHTML = "";
  const list = Array.isArray(items) && items.length > 0 ? items : state.modeConfig?.fallbackChecklist || [];
  list.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = String(item || "");
    elements.checklist.appendChild(li);
  });
}

function renderStatusCards(hasProblem) {
  if (!elements.statusCards) {
    return;
  }

  const cards = [];
  cards.push(
    hasProblem
      ? {
          title: "문제 생성",
          status: "완료",
          description: "문제가 IDE 화면에 반영되었습니다.",
        }
      : {
          title: "문제 생성",
          status: "대기",
          description: "문제 받기를 누르면 AI가 분석 문제를 생성합니다.",
        }
  );

  if (!hasProblem) {
    cards.push(
      {
        title: "리포트 제출",
        status: "대기",
        description: "문제를 받은 뒤 리포트를 작성해 제출하세요.",
      },
      {
        title: "채점 결과",
        status: "대기",
        description: "제출 후 점수, 피드백, 모범 분석 리포트를 확인할 수 있습니다.",
      }
    );
  } else if (state.submissionPhase === "submitting") {
    cards.push(
      {
        title: "리포트 제출",
        status: "제출 중",
        description: "리포트를 전송하고 있습니다.",
      },
      {
        title: "채점 결과",
        status: "채점 중",
        description: "AI가 리포트를 평가하고 있습니다.",
      }
    );
  } else if (state.submissionPhase === "queued") {
    cards.push(
      {
        title: "리포트 제출",
        status: "접수됨",
        description: "리포트가 큐에 등록되었습니다.",
      },
      {
        title: "채점 결과",
        status: "대기 중",
        description: "백그라운드 채점이 끝나면 결과를 자동으로 불러옵니다.",
      }
    );
  } else if (state.submissionPhase === "finished" && state.latestResult) {
    cards.push(
      {
        title: "리포트 제출",
        status: "완료",
        description: "리포트가 정상적으로 제출되었습니다.",
      },
      {
        title: "채점 결과",
        status: state.latestResult.correct ? "합격" : "불합격",
        description: "아래 결과 패널에서 점수와 피드백을 확인할 수 있습니다.",
      }
    );
  } else if (state.submissionPhase === "failed") {
    cards.push(
      {
        title: "리포트 제출",
        status: "다시 시도",
        description: "제출 또는 채점 처리 중 문제가 발생했습니다.",
      },
      {
        title: "채점 결과",
        status: "실패",
        description: "잠시 후 다시 제출해 주세요.",
      }
    );
  } else {
    cards.push(
      {
        title: "리포트 제출",
        status: "준비됨",
        description: "분석 리포트를 작성하고 제출할 수 있습니다.",
      },
      {
        title: "채점 결과",
        status: "대기",
        description: "제출 후 점수, 피드백, 모범 분석 리포트를 표시합니다.",
      }
    );
  }

  elements.statusCards.innerHTML = "";
  cards.forEach((card) => {
    const article = document.createElement("article");
    article.className = "advanced-status-card";

    const head = document.createElement("div");
    head.className = "advanced-status-card-head";

    const title = document.createElement("strong");
    title.textContent = card.title;

    const badge = document.createElement("span");
    badge.className = "pill soft";
    badge.textContent = card.status;

    const desc = document.createElement("p");
    desc.textContent = card.description;

    head.append(title, badge);
    article.append(head, desc);
    elements.statusCards.appendChild(article);
  });
}

function renderFileCollections(files) {
  if (elements.fileStrip) {
    elements.fileStrip.innerHTML = "";
  }
  if (elements.fileRail) {
    elements.fileRail.innerHTML = "";
  }

  files.forEach((file) => {
    if (elements.fileStrip) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "advanced-editor-tab";
      button.dataset.advancedFileId = file.id;
      button.setAttribute("aria-pressed", "false");

      const icon = document.createElement("span");
      icon.className = "advanced-file-icon";
      icon.textContent = getFileIconLabel(file.name);

      const title = document.createElement("span");
      title.className = "advanced-editor-tab-title";
      title.textContent = file.name;

      button.append(icon, title);
      elements.fileStrip.appendChild(button);
    }

    if (elements.fileRail) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "advanced-explorer-item";
      button.dataset.advancedFileId = file.id;
      button.setAttribute("aria-pressed", "false");

      const row = document.createElement("div");
      row.className = "advanced-explorer-row";

      const icon = document.createElement("span");
      icon.className = "advanced-file-icon";
      icon.textContent = getFileIconLabel(file.name);

      const title = document.createElement("span");
      title.className = "advanced-file-button-title";
      title.textContent = file.name;

      const meta = document.createElement("span");
      meta.className = "advanced-file-button-meta";
      meta.textContent = file.path;

      const badges = document.createElement("div");
      badges.className = "advanced-file-button-badges";

      const language = document.createElement("span");
      language.className = "pill soft";
      language.textContent = file.language;

      const role = document.createElement("span");
      role.className = "pill soft";
      role.textContent = file.role;

      row.append(icon, title);
      badges.append(language, role);
      button.append(row, meta, badges);
      elements.fileRail.appendChild(button);
    }
  });
}

function getActiveFile(files) {
  const list = Array.isArray(files) ? files : [];
  return list.find((file) => file.id === state.activeFileId) || list[0] || null;
}

function renderActiveFile(file) {
  renderActiveFileMeta(file, state.currentProblem?.files?.length || 0);
  void renderCodeView(file?.content || "", { animate: false });
  setActiveButtons(file?.id || "");
}

function renderActiveFileMeta(file, fileCount) {
  if (elements.activeFileName) {
    elements.activeFileName.textContent = file?.name || "파일을 기다리는 중입니다.";
  }
  if (elements.activeFilePath) {
    elements.activeFilePath.textContent = file?.path || "경로 -";
  }
  if (elements.activeFileRole) {
    elements.activeFileRole.textContent = file ? `역할 ${file.role}` : "역할 -";
  }
  if (elements.activeFileLanguage) {
    elements.activeFileLanguage.textContent = file ? `언어 ${file.language}` : "언어 -";
  }
  if (elements.statusbarLeft) {
    elements.statusbarLeft.textContent = `${fileCount} files loaded`;
  }
  if (elements.statusbarRight) {
    elements.statusbarRight.textContent = file ? `Read-only · ${file.language}` : "Read-only";
  }
  renderBreadcrumbs(file?.path || "");
}

function renderBreadcrumbs(path) {
  if (!elements.breadcrumbs) {
    return;
  }
  elements.breadcrumbs.innerHTML = "";
  if (!path) {
    return;
  }

  path.split("/").forEach((part, index, parts) => {
    const crumb = document.createElement("span");
    crumb.className = "advanced-breadcrumb-item";
    crumb.textContent = part;
    elements.breadcrumbs.appendChild(crumb);

    if (index < parts.length - 1) {
      const divider = document.createElement("span");
      divider.className = "advanced-breadcrumb-divider";
      divider.textContent = "/";
      elements.breadcrumbs.appendChild(divider);
    }
  });
}

function setActiveButtons(activeId) {
  document.querySelectorAll("[data-advanced-file-id]").forEach((button) => {
    const isActive = button.dataset.advancedFileId === activeId;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

async function renderCodeView(code, { animate }) {
  if (!elements.codeView) {
    return;
  }

  elements.codeView.innerHTML = "";
  const lines = String(code || "").replace(/\n$/, "").split("\n");
  const animated = Boolean(animate && streamClient && typeof streamClient.sleep === "function");

  for (let index = 0; index < lines.length; index += 1) {
    const row = buildCodeRow(lines[index], index + 1);
    elements.codeView.appendChild(row);
    if (animated && index < lines.length - 1) {
      await streamClient.sleep(28);
    }
  }
}

function buildCodeRow(line, lineNumber) {
  const row = document.createElement("div");
  row.className = "advanced-code-row";

  const number = document.createElement("span");
  number.className = "advanced-code-line-number";
  number.textContent = String(lineNumber);

  const content = document.createElement("span");
  content.className = "advanced-code-line-content";
  appendHighlightedCode(content, line);

  row.append(number, content);
  return row;
}

function appendHighlightedCode(target, line) {
  const trimmed = line.trim();
  if (!trimmed) {
    target.textContent = " ";
    return;
  }

  if (trimmed.startsWith("//") || trimmed.startsWith("#")) {
    const comment = document.createElement("span");
    comment.className = "token-comment";
    comment.textContent = line;
    target.appendChild(comment);
    return;
  }

  let cursor = 0;
  for (const match of line.matchAll(STRING_PATTERN)) {
    appendKeywordTokens(target, line.slice(cursor, match.index));
    const token = document.createElement("span");
    token.className = "token-string";
    token.textContent = match[0];
    target.appendChild(token);
    cursor = match.index + match[0].length;
  }
  appendKeywordTokens(target, line.slice(cursor));
}

function appendKeywordTokens(target, text) {
  let cursor = 0;
  for (const match of text.matchAll(KEYWORD_PATTERN)) {
    target.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    const token = document.createElement("span");
    token.className = "token-keyword";
    token.textContent = match[0];
    target.appendChild(token);
    cursor = match.index + match[0].length;
  }
  target.appendChild(document.createTextNode(text.slice(cursor)));
}

function handleFileSelect(event) {
  const button = event.target.closest("[data-advanced-file-id]");
  if (!button || !state.currentProblem) {
    return;
  }

  const nextFileId = button.dataset.advancedFileId;
  if (!nextFileId || nextFileId === state.activeFileId) {
    return;
  }

  state.activeFileId = nextFileId;
  renderActiveFile(getActiveFile(state.currentProblem.files));
}

async function handleSubmitReport(event) {
  event?.preventDefault?.();

  if (!state.currentProblem || !state.modeConfig) {
    showToast("먼저 문제를 받아 주세요.");
    return;
  }

  const report = (elements.reportText?.value || "").trim();
  if (!report) {
    showToast("분석 리포트를 입력해 주세요.");
    updateSubmitButtonState();
    return;
  }

  state.submitPending = true;
  state.submissionPhase = "submitting";
  renderStatusCards(true);
  updateSubmitButtonState();
  setLoadingState(elements.submitButton, true, "채점 중...");

  try {
    const payload = await apiRequest(state.modeConfig.submitPath, {
      method: "POST",
      body: {
        problemId: state.currentProblem.problemId,
        report,
      },
    });

    if (payload?.queued && payload?.jobId) {
      state.submissionPhase = "queued";
      renderStatusCards(true);
      showToast("채점 요청이 접수되었습니다.");
      startSubmitPolling(payload.jobId);
      return;
    }

    renderFeedback(payload);
    showToast("채점이 완료되었습니다.");
  } catch (error) {
    console.error(error);
    state.submitPending = false;
    state.submissionPhase = "failed";
    renderStatusCards(true);
    updateSubmitButtonState();
    showToast(error.message || "채점에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    setLoadingState(elements.submitButton, false);
  }
}

function clearFeedback() {
  state.latestResult = null;
  if (elements.resultPanel) {
    elements.resultPanel.classList.add("hidden");
  }
  if (elements.resultScore) {
    elements.resultScore.textContent = "점수 대기";
  }
  if (elements.resultVerdict) {
    elements.resultVerdict.textContent = "판정 대기";
    elements.resultVerdict.dataset.state = "neutral";
  }
  if (elements.resultThreshold) {
    elements.resultThreshold.textContent = "합격 기준 70점";
  }
  if (elements.resultSummary) {
    elements.resultSummary.textContent = "리포트를 제출하면 요약 피드백이 이곳에 표시됩니다.";
  }
  renderFeedbackList(elements.resultStrengths, [], "강점이 아직 없습니다.");
  renderFeedbackList(elements.resultImprovements, [], "개선 포인트가 아직 없습니다.");
  if (elements.referenceReport) {
    elements.referenceReport.textContent = "모범 분석 리포트가 이곳에 표시됩니다.";
  }
}

function renderFeedback(payload) {
  const score = Number(payload?.score);
  const hasScore = Number.isFinite(score);
  const verdict = payload?.verdict || (payload?.correct ? "passed" : "failed");
  const threshold = Number(payload?.passThreshold ?? 70);
  const feedback = payload?.feedback || {};

  state.latestResult = payload || null;
  state.submissionPhase = "finished";
  state.submitPending = false;

  if (elements.resultPanel) {
    elements.resultPanel.classList.remove("hidden");
  }
  if (elements.resultScore) {
    elements.resultScore.textContent = hasScore ? `${Math.round(score)}점` : "점수 없음";
  }
  if (elements.resultVerdict) {
    if (verdict === "passed") {
      elements.resultVerdict.textContent = "합격";
      elements.resultVerdict.dataset.state = "success";
    } else if (verdict === "failed") {
      elements.resultVerdict.textContent = "불합격";
      elements.resultVerdict.dataset.state = "danger";
    } else {
      elements.resultVerdict.textContent = "판정 대기";
      elements.resultVerdict.dataset.state = "neutral";
    }
  }
  if (elements.resultThreshold) {
    elements.resultThreshold.textContent = `합격 기준 ${Number.isFinite(threshold) ? threshold : 70}점`;
  }
  if (elements.resultSummary) {
    elements.resultSummary.textContent = feedback.summary || "요약 피드백이 없습니다.";
  }
  renderFeedbackList(elements.resultStrengths, feedback.strengths, "강점이 없습니다.");
  renderFeedbackList(elements.resultImprovements, feedback.improvements, "개선 포인트가 없습니다.");
  if (elements.referenceReport) {
    elements.referenceReport.textContent = payload?.referenceReport || "모범 분석 리포트가 제공되지 않았습니다.";
  }

  renderStatusCards(Boolean(state.currentProblem));
  updateSubmitButtonState();
}

function renderFeedbackList(target, items, emptyText) {
  if (!target) {
    return;
  }

  target.innerHTML = "";
  const rows = Array.isArray(items) ? items.map((item) => String(item || "").trim()).filter(Boolean) : [];
  if (rows.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = emptyText;
    target.appendChild(li);
    return;
  }

  rows.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    target.appendChild(li);
  });
}

function startSubmitPolling(jobId) {
  stopSubmitPolling();
  state.submitJobId = String(jobId || "");
  state.submitPollAttempts = 0;
  state.submitPending = true;
  state.submissionPhase = "queued";
  renderStatusCards(Boolean(state.currentProblem));
  updateSubmitButtonState();
  void pollSubmitJob();
}

function stopSubmitPolling() {
  if (state.submitPollTimer) {
    window.clearTimeout(state.submitPollTimer);
    state.submitPollTimer = null;
  }
  state.submitJobId = null;
  state.submitPollAttempts = 0;
}

async function pollSubmitJob() {
  if (!state.submitJobId) {
    return;
  }

  state.submitPollAttempts += 1;
  try {
    const payload = await apiRequest(`/platform/mode-jobs/${encodeURIComponent(state.submitJobId)}`);

    if (payload?.finished) {
      stopSubmitPolling();
      renderFeedback(payload.result || {});
      showToast("채점이 완료되었습니다.");
      return;
    }

    if (payload?.failed) {
      stopSubmitPolling();
      state.submitPending = false;
      state.submissionPhase = "failed";
      renderStatusCards(Boolean(state.currentProblem));
      updateSubmitButtonState();
      showToast(payload.error || "채점 작업이 실패했습니다.");
      return;
    }

    state.submissionPhase = payload?.status === "started" ? "submitting" : "queued";
    renderStatusCards(Boolean(state.currentProblem));

    if (state.submitPollAttempts >= MODE_JOB_MAX_POLL_ATTEMPTS) {
      stopSubmitPolling();
      state.submitPending = false;
      state.submissionPhase = "failed";
      renderStatusCards(Boolean(state.currentProblem));
      updateSubmitButtonState();
      showToast("채점 결과를 불러오는 데 시간이 오래 걸리고 있습니다. 잠시 후 다시 확인해 주세요.");
      return;
    }

    state.submitPollTimer = window.setTimeout(() => {
      void pollSubmitJob();
    }, MODE_JOB_POLL_INTERVAL);
  } catch (error) {
    console.error(error);
    stopSubmitPolling();
    state.submitPending = false;
    state.submissionPhase = "failed";
    renderStatusCards(Boolean(state.currentProblem));
    updateSubmitButtonState();
    showToast(error.message || "채점 상태를 확인하지 못했습니다.");
  }
}

function updateSubmitButtonState() {
  if (!elements.submitButton) {
    return;
  }
  const report = (elements.reportText?.value || "").trim();
  elements.submitButton.disabled = !state.currentProblem || !report || state.submitPending;
}

function setLoadingState(button, isLoading, label) {
  if (!button) {
    return;
  }
  if (isLoading) {
    button.disabled = true;
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent || "";
    }
    if (label) {
      button.textContent = label;
    }
    return;
  }

  if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
    delete button.dataset.originalText;
  }

  if (button === elements.submitButton) {
    updateSubmitButtonState();
    return;
  }

  button.disabled = false;
}

function showToast(message) {
  if (!elements.toast) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  elements.toast.classList.add("visible");

  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }

  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
    elements.toast.classList.add("hidden");
    state.toastTimer = null;
  }, DEFAULT_TOAST_DURATION);
}

function getSavedLanguage() {
  return window.localStorage.getItem(LANGUAGE_KEY) || DEFAULT_LANGUAGE;
}

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  return DIFFICULTY_OPTIONS.has(value) ? value : DEFAULT_DIFFICULTY;
}

function getFileIconLabel(fileName) {
  const extension = fileName.split(".").pop()?.toLowerCase() || "";
  if (extension === "py") {
    return "PY";
  }
  if (extension === "tsx") {
    return "TSX";
  }
  if (extension === "ts") {
    return "TS";
  }
  if (extension === "js") {
    return "JS";
  }
  if (extension === "html") {
    return "HTML";
  }
  if (extension === "css") {
    return "CSS";
  }
  return "TXT";
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  void init();
}
