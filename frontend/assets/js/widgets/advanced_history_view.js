const DEFAULT_LANGUAGE = "python";
const DEFAULT_PASS_THRESHOLD = 70;
const ADVANCED_MODES = new Set(["single-file-analysis", "multi-file-analysis", "fullstack-analysis"]);
const MODE_CONFIGS = {
  "single-file-analysis": {
    title: "단일 파일 분석",
    headline: "하나의 파일을 깊게 읽으며 제어 흐름과 상태 변화를 설명하는 고급 분석 모드입니다.",
    scope: "단일 파일 흐름 분석",
  },
  "multi-file-analysis": {
    title: "다중 파일 분석",
    headline: "여러 파일의 호출 관계와 책임 분리를 연결해서 읽는 고급 분석 모드입니다.",
    scope: "모듈 간 호출 분석",
  },
  "fullstack-analysis": {
    title: "풀스택 코드 분석",
    headline: "프론트엔드와 백엔드를 함께 보며 요청-응답 전체 흐름을 해석하는 고급 분석 모드입니다.",
    scope: "풀스택 요청 흐름 분석",
  },
};
const DIFFICULTY_LABELS = {
  beginner: "초급",
  intermediate: "중급",
  advanced: "고급",
  easy: "초급",
  medium: "중급",
  hard: "고급",
};
const KEYWORD_PATTERN =
  /\b(async|await|case|catch|class|const|constructor|def|else|export|for|from|function|if|import|new|return|switch|try|while)\b/g;
const STRING_PATTERN = /(`[^`]*`|"[^"]*"|'[^']*')/g;

export function normalizeAdvancedHistoryProblem(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  const mode = normalizeMode(item.mode);
  if (!ADVANCED_MODES.has(mode)) {
    return null;
  }

  const fallbackLanguage = String(item.language || DEFAULT_LANGUAGE).trim().toLowerCase() || DEFAULT_LANGUAGE;
  const filesSource = Array.isArray(item.problem_files)
    ? item.problem_files
    : Array.isArray(item.files)
      ? item.files
      : parseFilesFromStarterCode(item.problem_code || item.code, {
          mode,
          fallbackLanguage,
        });
  const files = filesSource
    .map((file, index) => normalizeFile(file, index, fallbackLanguage))
    .filter((file) => file && file.content);

  if (files.length === 0) {
    return null;
  }

  const feedback = normalizeFeedback(item.feedback);
  const passThreshold = normalizeNumber(item.passThreshold ?? item.pass_threshold) ?? DEFAULT_PASS_THRESHOLD;
  const score = normalizeNumber(item.score);
  const verdict = normalizeVerdict(item.verdict, item.correct, score, passThreshold);
  const modeConfig = MODE_CONFIGS[mode] || MODE_CONFIGS["multi-file-analysis"];

  return {
    mode,
    modeTitle: modeConfig.title,
    headline: modeConfig.headline,
    scope: modeConfig.scope,
    title: String(item.problem_title || item.title || "AI 분석 문제"),
    summary: String(item.problem_summary || item.summary || "").trim(),
    prompt: String(item.problem_prompt || item.prompt || "").trim(),
    workspace: String(item.problem_workspace || item.workspace || inferWorkspace(mode)).trim() || inferWorkspace(mode),
    files,
    checklist: normalizeChecklist(item.problem_checklist),
    language: fallbackLanguage,
    difficulty: String(item.difficulty || "").trim().toLowerCase(),
    explanation: String(item.explanation || "").trim(),
    feedback,
    score,
    verdict,
    passThreshold,
    referenceReport: String(item.reference_report || item.referenceReport || "").trim(),
    createdAt: String(item.created_at || item.createdAt || "").trim(),
  };
}

export function buildAdvancedHistoryWorkbenchMarkup(noteId) {
  const safeNoteId = escapeAttribute(noteId);

  return `
    <section class="history-advanced-shell advanced-analysis-view" data-history-workbench-id="${safeNoteId}">
      <div class="advanced-analysis-layout">
        <section class="panel advanced-analysis-panel advanced-analysis-overview">
          <div class="advanced-mode-summary">
            <p class="badge soft" data-history-mode-state>오답 기록</p>
            <h2 data-history-mode-headline>고급모드 문제를 다시 여는 중입니다.</h2>
            <p data-history-mode-summary>학습 당시의 문제 맥락과 제출 리포트를 읽기 전용으로 다시 확인할 수 있습니다.</p>
          </div>
          <div class="advanced-mode-meta">
            <span class="pill" data-history-file-range>파일 수 -</span>
            <span class="pill" data-history-language-range>언어 범위 -</span>
            <span class="pill" data-history-scope>범위 -</span>
            <span class="pill soft" data-history-selected-language>언어 -</span>
            <span class="pill soft" data-history-selected-difficulty>난이도 -</span>
          </div>
          <div class="advanced-mode-actions">
            <span class="pill soft" data-history-workspace-pill>workspace -</span>
            <p class="advanced-load-status" data-history-load-status>출제 당시 코드와 제출 내용을 다시 불러옵니다.</p>
          </div>
        </section>

        <section class="panel advanced-analysis-panel advanced-analysis-stage">
          <div class="advanced-workbench-titlebar">
            <div class="advanced-workbench-title">
              <span class="advanced-workbench-title-label">ADVANCED ANALYSIS</span>
              <strong data-history-workspace-title>analysis.workspace</strong>
            </div>
          </div>

          <div class="advanced-workbench">
            <aside class="advanced-activity-bar" aria-label="IDE 활동">
              <button type="button" class="advanced-activity-item is-active" aria-pressed="true">EX</button>
              <button type="button" class="advanced-activity-item" aria-pressed="false">AI</button>
              <button type="button" class="advanced-activity-item" aria-pressed="false">OUT</button>
            </aside>

            <aside class="advanced-sidebar">
              <div class="advanced-sidebar-head">
                <span class="advanced-sidebar-label">Explorer</span>
                <strong>읽기 전용 워크스페이스</strong>
              </div>
              <div class="advanced-sidebar-section-label">FILES</div>
              <div class="advanced-file-rail" data-history-file-rail></div>
            </aside>

            <div class="advanced-editor-workbench">
              <div class="advanced-editor-topbar">
                <div class="advanced-file-strip" data-history-file-strip></div>
                <div class="advanced-file-meta">
                  <span class="pill soft" data-history-active-language>언어 -</span>
                  <span class="pill soft" data-history-active-role>역할 -</span>
                </div>
              </div>

              <div class="advanced-editor-breadcrumbs" data-history-breadcrumbs></div>

              <div class="advanced-editor-surface">
                <div class="advanced-editor-header">
                  <div>
                    <p class="eyebrow">Read-only IDE</p>
                    <h2 data-history-active-name>파일을 여는 중입니다.</h2>
                    <p data-history-active-path>경로 -</p>
                  </div>
                </div>
                <div class="advanced-code-view" data-history-code-view role="region" aria-label="문제 코드 보기"></div>
              </div>

              <div class="advanced-statusbar">
                <span data-history-statusbar-left>0 files loaded</span>
                <span data-history-statusbar-right>Read-only</span>
              </div>
            </div>
          </div>
        </section>

        <section class="advanced-analysis-bottom">
          <article class="panel advanced-analysis-panel advanced-task-panel">
            <div class="advanced-task-head">
              <h3>분석 과제</h3>
              <p class="advanced-problem-title" data-history-problem-title>문제 제목을 불러오는 중입니다.</p>
              <p data-history-task-prompt>문제 지시를 불러오는 중입니다.</p>
            </div>
            <ul class="advanced-checklist" data-history-checklist></ul>
            <label>내 제출 리포트</label>
            <textarea rows="10" readonly data-history-report-text></textarea>
          </article>

          <article class="panel advanced-analysis-panel advanced-status-panel">
            <div class="advanced-status-head">
              <h3>채점 결과</h3>
              <p data-history-status-head>문제 생성, 제출, 채점 결과를 한 번에 다시 확인할 수 있습니다.</p>
            </div>
            <div class="advanced-status-cards" data-history-status-cards></div>
            <section class="advanced-result-panel" data-history-result-panel>
              <div class="advanced-result-summary-bar">
                <strong data-history-result-score>점수 대기</strong>
                <span class="badge soft" data-state="neutral" data-history-result-verdict>판정 대기</span>
                <span class="pill soft" data-history-result-threshold>합격 기준 70점</span>
              </div>
              <p class="advanced-result-summary" data-history-result-summary>요약 피드백이 없습니다.</p>
              <div class="advanced-result-columns">
                <article class="advanced-result-card">
                  <h4>강점</h4>
                  <ul class="advanced-result-list" data-history-result-strengths></ul>
                </article>
                <article class="advanced-result-card">
                  <h4>개선 포인트</h4>
                  <ul class="advanced-result-list" data-history-result-improvements></ul>
                </article>
              </div>
              <article class="advanced-result-card advanced-reference-card">
                <h4>모범 분석 리포트</h4>
                <pre class="advanced-reference-report" data-history-reference-report>모범 분석 리포트가 제공되지 않았습니다.</pre>
              </article>
            </section>
          </article>
        </section>
      </div>
    </section>
  `;
}

export function mountAdvancedHistoryWorkbench(root, problem) {
  if (!(root instanceof HTMLElement) || !problem || !Array.isArray(problem.files) || problem.files.length === 0) {
    return;
  }

  const elements = {
    modeState: root.querySelector("[data-history-mode-state]"),
    modeHeadline: root.querySelector("[data-history-mode-headline]"),
    modeSummary: root.querySelector("[data-history-mode-summary]"),
    fileRange: root.querySelector("[data-history-file-range]"),
    languageRange: root.querySelector("[data-history-language-range]"),
    scope: root.querySelector("[data-history-scope]"),
    selectedLanguage: root.querySelector("[data-history-selected-language]"),
    selectedDifficulty: root.querySelector("[data-history-selected-difficulty]"),
    workspacePill: root.querySelector("[data-history-workspace-pill]"),
    loadStatus: root.querySelector("[data-history-load-status]"),
    workspaceTitle: root.querySelector("[data-history-workspace-title]"),
    fileStrip: root.querySelector("[data-history-file-strip]"),
    fileRail: root.querySelector("[data-history-file-rail]"),
    breadcrumbs: root.querySelector("[data-history-breadcrumbs]"),
    activeName: root.querySelector("[data-history-active-name]"),
    activePath: root.querySelector("[data-history-active-path]"),
    activeRole: root.querySelector("[data-history-active-role]"),
    activeLanguage: root.querySelector("[data-history-active-language]"),
    codeView: root.querySelector("[data-history-code-view]"),
    statusbarLeft: root.querySelector("[data-history-statusbar-left]"),
    statusbarRight: root.querySelector("[data-history-statusbar-right]"),
    problemTitle: root.querySelector("[data-history-problem-title]"),
    taskPrompt: root.querySelector("[data-history-task-prompt]"),
    checklist: root.querySelector("[data-history-checklist]"),
    reportText: root.querySelector("[data-history-report-text]"),
    statusHead: root.querySelector("[data-history-status-head]"),
    statusCards: root.querySelector("[data-history-status-cards]"),
    resultPanel: root.querySelector("[data-history-result-panel]"),
    resultScore: root.querySelector("[data-history-result-score]"),
    resultVerdict: root.querySelector("[data-history-result-verdict]"),
    resultThreshold: root.querySelector("[data-history-result-threshold]"),
    resultSummary: root.querySelector("[data-history-result-summary]"),
    resultStrengths: root.querySelector("[data-history-result-strengths]"),
    resultImprovements: root.querySelector("[data-history-result-improvements]"),
    referenceReport: root.querySelector("[data-history-reference-report]"),
  };

  let activeFileId = problem.files[0]?.id || "";
  const fileLanguageRange = buildLanguageRange(problem.files);

  const render = () => {
    const activeFile = problem.files.find((file) => file.id === activeFileId) || problem.files[0];
    if (elements.modeState) {
      elements.modeState.textContent = "오답 기록";
    }
    if (elements.modeHeadline) {
      elements.modeHeadline.textContent = problem.headline;
    }
    if (elements.modeSummary) {
      elements.modeSummary.textContent =
        problem.summary || "학습 당시 문제를 구성했던 파일과 제출 리포트를 읽기 전용으로 다시 확인합니다.";
    }
    if (elements.fileRange) {
      elements.fileRange.textContent = `${problem.files.length} files`;
    }
    if (elements.languageRange) {
      elements.languageRange.textContent = fileLanguageRange;
    }
    if (elements.scope) {
      elements.scope.textContent = problem.scope;
    }
    if (elements.selectedLanguage) {
      elements.selectedLanguage.textContent = `언어 ${formatLanguageLabel(problem.language, problem.files)}`;
    }
    if (elements.selectedDifficulty) {
      elements.selectedDifficulty.textContent = `난이도 ${formatDifficultyLabel(problem.difficulty)}`;
    }
    if (elements.workspacePill) {
      elements.workspacePill.textContent = `workspace ${problem.workspace}`;
    }
    if (elements.loadStatus) {
      elements.loadStatus.textContent = buildLoadStatus(problem);
    }
    if (elements.workspaceTitle) {
      elements.workspaceTitle.textContent = problem.workspace || "analysis.workspace";
    }
    if (elements.problemTitle) {
      elements.problemTitle.textContent = problem.title;
    }
    if (elements.taskPrompt) {
      elements.taskPrompt.textContent = problem.prompt || "문제 지시가 없습니다.";
    }
    if (elements.statusHead) {
      elements.statusHead.textContent = "문제 생성, 제출 리포트, 채점 결과를 같은 IDE 문맥에서 다시 봅니다.";
    }
    renderChecklist(elements.checklist, problem.checklist);
    renderReportText(elements.reportText, problem.explanation);
    renderStatusCards(elements.statusCards, problem);
    renderResultPanel(elements, problem);
    renderFileCollections(elements, problem.files, activeFile?.id || "");
    renderActiveFile(elements, activeFile, problem.files.length);
  };

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-history-file-id]");
    if (!button) {
      return;
    }
    const nextFileId = button.dataset.historyFileId || "";
    if (!nextFileId || nextFileId === activeFileId) {
      return;
    }
    activeFileId = nextFileId;
    render();
  });

  render();
}

function normalizeMode(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeFeedback(feedback) {
  if (!feedback || typeof feedback !== "object") {
    return { summary: "", strengths: [], improvements: [] };
  }
  return {
    summary: String(feedback.summary || "").trim(),
    strengths: Array.isArray(feedback.strengths)
      ? feedback.strengths.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    improvements: Array.isArray(feedback.improvements)
      ? feedback.improvements.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
  };
}

function normalizeChecklist(checklist) {
  return Array.isArray(checklist)
    ? checklist.map((entry) => String(entry || "").trim()).filter(Boolean)
    : [];
}

function normalizeNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeVerdict(verdict, correct, score, passThreshold) {
  const normalized = String(verdict || "").trim().toLowerCase();
  if (normalized === "passed" || normalized === "failed") {
    return normalized;
  }
  if (correct === true) {
    return "passed";
  }
  if (correct === false) {
    return "failed";
  }
  if (typeof score === "number") {
    return score >= passThreshold ? "passed" : "failed";
  }
  return "neutral";
}

function normalizeFile(file, index, fallbackLanguage) {
  if (!file || typeof file !== "object") {
    return null;
  }
  const path = String(file.path || file.name || inferFallbackPath(fallbackLanguage, index)).trim() || inferFallbackPath(fallbackLanguage, index);
  const name = String(file.name || path.split("/").pop() || `file_${index + 1}.txt`).trim() || `file_${index + 1}.txt`;
  const inferredLanguage = inferLanguageFromPath(path) || fallbackLanguage;
  const language = String(file.language || inferredLanguage || DEFAULT_LANGUAGE).trim().toLowerCase() || DEFAULT_LANGUAGE;
  const role = String(file.role || inferRoleFromPath(path) || "module").trim() || "module";
  const content = String(file.content || file.code || "").replace(/\r\n/g, "\n").replace(/\n+$/, "\n");
  const id = String(file.id || buildFileId(path, index)).trim();
  if (!content.trim()) {
    return null;
  }
  return {
    id: id || `file-${index + 1}`,
    path,
    name,
    language,
    role,
    content,
  };
}

function parseFilesFromStarterCode(source, { mode, fallbackLanguage }) {
  const text = String(source || "").replace(/\r\n/g, "\n").trim();
  if (!text) {
    return [];
  }

  const lines = text.split("\n");
  const files = [];
  let current = null;

  const pushCurrent = () => {
    if (!current) {
      return;
    }
    const content = current.lines.join("\n").replace(/\n+$/, "");
    if (content.trim()) {
      files.push({
        path: current.path,
        name: current.path.split("/").pop(),
        language: inferLanguageFromPath(current.path) || fallbackLanguage,
        role: inferRoleFromPath(current.path) || "module",
        content,
      });
    }
    current = null;
  };

  lines.forEach((line) => {
    if (line.startsWith("File: ")) {
      pushCurrent();
      const path = line.slice(6).trim() || inferFallbackPath(fallbackLanguage, files.length, mode);
      current = { path, lines: [] };
      return;
    }

    if (!current) {
      current = {
        path: inferFallbackPath(fallbackLanguage, files.length, mode),
        lines: [],
      };
    }
    current.lines.push(line);
  });

  pushCurrent();
  return files;
}

function inferWorkspace(mode) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  if (normalizedMode === "single-file-analysis") {
    return "single-file-analysis.workspace";
  }
  if (normalizedMode === "multi-file-analysis") {
    return "multi-file-analysis.workspace";
  }
  if (normalizedMode === "fullstack-analysis") {
    return "fullstack-analysis.workspace";
  }
  return "analysis.workspace";
}

function inferFallbackPath(language, index, mode = "analysis") {
  const extension = extensionForLanguage(language);
  if (mode === "fullstack-analysis" && index === 0) {
    return `frontend/file_${index + 1}.${extension}`;
  }
  if (mode === "fullstack-analysis" && index > 0) {
    return `backend/file_${index + 1}.${extension}`;
  }
  return `src/file_${index + 1}.${extension}`;
}

function extensionForLanguage(language) {
  if (language === "python" || language === "py") return "py";
  if (language === "javascript" || language === "js") return "js";
  if (language === "typescript" || language === "ts") return "ts";
  if (language === "tsx") return "tsx";
  if (language === "html") return "html";
  if (language === "css") return "css";
  if (language === "json") return "json";
  return "txt";
}

function inferLanguageFromPath(path) {
  const extension = String(path || "").split(".").pop()?.toLowerCase() || "";
  if (extension === "py") return "python";
  if (extension === "js") return "javascript";
  if (extension === "ts") return "typescript";
  if (extension === "tsx") return "tsx";
  if (extension === "html") return "html";
  if (extension === "css") return "css";
  if (extension === "json") return "json";
  return "";
}

function inferRoleFromPath(path) {
  const normalized = String(path || "").trim().toLowerCase();
  if (!normalized) return "";
  if (normalized.includes("frontend/") || normalized.includes("/pages/") || normalized.includes("/components/")) {
    return "frontend";
  }
  if (normalized.includes("backend/") || normalized.includes("/api/") || normalized.includes("/service")) {
    return "backend";
  }
  if (normalized.includes("/test") || normalized.includes(".spec.") || normalized.includes(".test.")) {
    return "test";
  }
  return "module";
}

function buildFileId(path, index) {
  const token = String(path || "")
    .toLowerCase()
    .split("")
    .map((char) => (/[a-z0-9]/.test(char) ? char : "-"))
    .join("")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return token || `file-${index + 1}`;
}

function buildLanguageRange(files) {
  const languages = [...new Set((Array.isArray(files) ? files : []).map((file) => String(file.language || "").trim()).filter(Boolean))];
  if (languages.length === 0) {
    return "언어 범위 미상";
  }
  if (languages.length === 1) {
    return `언어 범위 ${formatLanguageLabel(languages[0])}`;
  }
  return `언어 범위 혼합 (${languages.map((language) => formatLanguageLabel(language)).join(", ")})`;
}

function formatLanguageLabel(language, files = []) {
  const normalized = String(language || "").trim().toLowerCase();
  if (normalized === "python") return "Python";
  if (normalized === "javascript") return "JavaScript";
  if (normalized === "typescript") return "TypeScript";
  if (normalized === "cpp" || normalized === "c++") return "C++";
  if (normalized === "csharp" || normalized === "cs" || normalized === "c#") return "C#";
  if (normalized === "go") return "Go";
  if (normalized === "rust") return "Rust";
  if (normalized === "php") return "PHP";
  if (normalized === "golfscript" || normalized === "gs") return "GolfScript";
  if (normalized === "tsx") return "TSX";
  if (normalized === "html") return "HTML";
  if (normalized === "css") return "CSS";
  if (normalized === "json") return "JSON";
  if (normalized) return normalized;

  const fallback = Array.isArray(files) && files[0] ? files[0].language : DEFAULT_LANGUAGE;
  return formatLanguageLabel(fallback);
}

function formatDifficultyLabel(difficulty) {
  return DIFFICULTY_LABELS[String(difficulty || "").trim().toLowerCase()] || "기록 없음";
}

function buildLoadStatus(problem) {
  const when = formatDateTime(problem.createdAt);
  if (when) {
    return `${when}에 풀이한 고급모드 문제를 다시 보고 있습니다.`;
  }
  return "학습 당시 문제를 구성한 코드와 제출 리포트를 읽기 전용으로 다시 보고 있습니다.";
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function renderFileCollections(elements, files, activeId) {
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
      button.dataset.historyFileId = file.id;
      button.classList.toggle("is-active", file.id === activeId);
      button.setAttribute("aria-pressed", file.id === activeId ? "true" : "false");

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
      button.dataset.historyFileId = file.id;
      button.classList.toggle("is-active", file.id === activeId);
      button.setAttribute("aria-pressed", file.id === activeId ? "true" : "false");

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

function renderActiveFile(elements, file, fileCount) {
  if (!file) {
    return;
  }
  if (elements.activeName) {
    elements.activeName.textContent = file.name;
  }
  if (elements.activePath) {
    elements.activePath.textContent = file.path;
  }
  if (elements.activeRole) {
    elements.activeRole.textContent = `역할 ${file.role}`;
  }
  if (elements.activeLanguage) {
    elements.activeLanguage.textContent = `언어 ${file.language}`;
  }
  if (elements.statusbarLeft) {
    elements.statusbarLeft.textContent = `${fileCount} files loaded`;
  }
  if (elements.statusbarRight) {
    elements.statusbarRight.textContent = `Read-only · ${file.language}`;
  }
  renderBreadcrumbs(elements.breadcrumbs, file.path);
  renderCodeView(elements.codeView, file.content);
}

function renderChecklist(container, checklist) {
  if (!(container instanceof HTMLElement)) {
    return;
  }
  container.innerHTML = "";
  const items = Array.isArray(checklist) ? checklist : [];
  if (items.length === 0) {
    const fallback = document.createElement("li");
    fallback.className = "empty";
    fallback.textContent = "체크리스트가 저장되지 않았습니다.";
    container.appendChild(fallback);
    return;
  }
  items.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = entry;
    container.appendChild(li);
  });
}

function renderReportText(target, explanation) {
  if (!(target instanceof HTMLTextAreaElement)) {
    return;
  }
  target.value = explanation || "";
  target.placeholder = "저장된 제출 리포트가 없습니다.";
}

function renderStatusCards(container, problem) {
  if (!(container instanceof HTMLElement)) {
    return;
  }
  container.innerHTML = "";
  const cards = [
    {
      title: "문제 생성",
      status: "완료",
      description: `문제 출제에 사용된 ${problem.files.length}개 파일을 다시 확인할 수 있습니다.`,
    },
    {
      title: "리포트 제출",
      status: problem.explanation ? "완료" : "기록 없음",
      description: problem.explanation
        ? "제출한 분석 리포트가 그대로 보존되어 있습니다."
        : "제출 리포트 본문은 저장되지 않았습니다.",
    },
    {
      title: "채점 결과",
      status: problem.score !== null || problem.feedback.summary || problem.referenceReport ? "완료" : "기록 없음",
      description: problem.score !== null
        ? `점수 ${Math.round(problem.score)}점과 피드백이 저장되어 있습니다.`
        : "채점 결과 요약만 저장되었거나 결과가 남아 있지 않습니다.",
    },
  ];

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
    container.appendChild(article);
  });
}

function renderResultPanel(elements, problem) {
  if (elements.resultPanel instanceof HTMLElement) {
    elements.resultPanel.classList.remove("hidden");
  }
  if (elements.resultScore) {
    elements.resultScore.textContent = typeof problem.score === "number" ? `${Math.round(problem.score)}점` : "점수 기록 없음";
  }
  if (elements.resultVerdict) {
    if (problem.verdict === "passed") {
      elements.resultVerdict.textContent = "합격";
      elements.resultVerdict.dataset.state = "success";
    } else if (problem.verdict === "failed") {
      elements.resultVerdict.textContent = "불합격";
      elements.resultVerdict.dataset.state = "danger";
    } else {
      elements.resultVerdict.textContent = "판정 기록 없음";
      elements.resultVerdict.dataset.state = "neutral";
    }
  }
  if (elements.resultThreshold) {
    elements.resultThreshold.textContent = `합격 기준 ${problem.passThreshold}점`;
  }
  if (elements.resultSummary) {
    elements.resultSummary.textContent = problem.feedback.summary || "요약 피드백이 저장되지 않았습니다.";
  }
  renderFeedbackList(elements.resultStrengths, problem.feedback.strengths, "강점이 저장되지 않았습니다.");
  renderFeedbackList(elements.resultImprovements, problem.feedback.improvements, "개선 포인트가 저장되지 않았습니다.");
  if (elements.referenceReport) {
    elements.referenceReport.textContent = problem.referenceReport || "모범 분석 리포트가 제공되지 않았습니다.";
  }
}

function renderFeedbackList(target, items, emptyText) {
  if (!(target instanceof HTMLElement)) {
    return;
  }
  target.innerHTML = "";
  const rows = Array.isArray(items) ? items : [];
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

function renderBreadcrumbs(container, path) {
  if (!(container instanceof HTMLElement)) {
    return;
  }
  container.innerHTML = "";
  if (!path) {
    return;
  }

  path.split("/").forEach((part, index, parts) => {
    const crumb = document.createElement("span");
    crumb.className = "advanced-breadcrumb-item";
    crumb.textContent = part;
    container.appendChild(crumb);

    if (index < parts.length - 1) {
      const divider = document.createElement("span");
      divider.className = "advanced-breadcrumb-divider";
      divider.textContent = "/";
      container.appendChild(divider);
    }
  });
}

function renderCodeView(container, code) {
  if (!(container instanceof HTMLElement)) {
    return;
  }
  container.innerHTML = "";
  const lines = String(code || "").replace(/\n$/, "").split("\n");
  lines.forEach((line, index) => {
    container.appendChild(buildCodeRow(line, index + 1));
  });
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

function getFileIconLabel(fileName) {
  const extension = fileName.split(".").pop()?.toLowerCase() || "";
  if (extension === "py") return "PY";
  if (extension === "tsx") return "TSX";
  if (extension === "ts") return "TS";
  if (extension === "js") return "JS";
  if (extension === "html") return "HTML";
  if (extension === "css") return "CSS";
  if (extension === "json") return "JSON";
  return "TXT";
}

function escapeAttribute(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
