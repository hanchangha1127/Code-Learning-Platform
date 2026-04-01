const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
const LANGUAGE_KEY = "code-learning-language";
const DIFFICULTY_KEY = "code-learning-difficulty";
const LATEST_REPORT_CACHE_KEY = "code-learning-latest-report";
const DEFAULT_LANGUAGE = "python";
const DEFAULT_DIFFICULTY = "beginner";
const DEFAULT_TOAST_DURATION = 3200;
const LATEST_REPORT_REFRESH_TTL_MS = 5 * 60 * 1000;

const DIFFICULTY_OPTIONS = [
  { id: "beginner", label: "초급" },
  { id: "intermediate", label: "중급" },
  { id: "advanced", label: "고급" },
];
const ADVANCED_HISTORY_MODES = new Set(["single-file-analysis", "multi-file-analysis", "fullstack-analysis"]);

const MODE_LABELS = {
  diagnostic: "진단",
  practice: "맞춤 문제",
  "code-block": "코드 블록",
  "code-calc": "코드 계산",
  "code-error": "오류 찾기",
  "code-arrange": "코드 배치",
  auditor: "감사관 모드",
  "context-inference": "맥락 추론",
  "refactoring-choice": "최적의 선택",
  "code-blame": "범인 찾기",
  "single-file-analysis": "단일 파일 분석",
  "multi-file-analysis": "다중 파일 분석",
  "fullstack-analysis": "풀스택 코드 분석",
};

const LANGUAGE_LABELS = {
  python: "파이썬",
  javascript: "자바스크립트",
  typescript: "타입스크립트",
  c: "C",
  java: "자바",
  cpp: "C++",
  "c++": "C++",
  csharp: "C#",
  cs: "C#",
  "c#": "C#",
  go: "Go",
  rust: "Rust",
  php: "PHP",
  golfscript: "골프스크립트",
};
const LANGUAGE_ALIASES = {
  py: "python",
  js: "javascript",
  ts: "typescript",
  "c++": "cpp",
  cs: "csharp",
  "c#": "csharp",
  gs: "golfscript",
};

const REPORT_LOADING_STEPS = [
  {
    label: "학습 데이터 분석",
    description: "최근 학습 기록과 점수 흐름을 정리하고 있어요.",
  },
  {
    label: "학습 패턴 탐색",
    description: "집중해야 할 주제와 학습 공백을 추출하고 있어요.",
  },
  {
    label: "실행 계획 생성",
    description: "바로 적용할 수 있는 액션 플랜을 만들고 있어요.",
  },
];

const state = {
  token: null,
  userId: null,
  username: "",
  displayName: "",
  languages: [],
  selectedLanguage: DEFAULT_LANGUAGE,
  difficulty: DEFAULT_DIFFICULTY,
  latestReport: null,
  latestReportStatus: "idle",
  latestReportError: "",
  latestReportRequestId: 0,
  latestReportCheckedAt: 0,
  toastTimer: null,
  reportLoadingTimer: null,
  activeReportRequestId: null,
  wrongNoteAdvancedProblems: new Map(),
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청을 처리하지 못했습니다.",
});

import {
  buildAdvancedHistoryWorkbenchMarkup,
  mountAdvancedHistoryWorkbench,
  normalizeAdvancedHistoryProblem,
} from "./advanced_history_view.js";


const elements = {};

function normalizeText(value) {
  if (value === undefined || value === null) return "";
  return String(value).trim();
}

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeText(value, fallback = "") {
  const normalized = normalizeText(value);
  if (normalized) return escapeHtml(normalized);
  return fallback ? escapeHtml(fallback) : "";
}

function escapeList(values, fallback = "-", separator = ", ") {
  const items = Array.isArray(values)
    ? values.map((value) => normalizeText(value)).filter((value) => value.length > 0)
    : [];
  if (!items.length) return escapeHtml(fallback);
  return items.map((value) => escapeHtml(value)).join(separator);
}

function normalizeLanguageId(value) {
  const normalized = normalizeText(value).toLowerCase();
  if (!normalized) return "";
  return LANGUAGE_ALIASES[normalized] || normalized;
}

function cacheDom() {
  elements.profileName = document.getElementById("profile-name");
  elements.profileTier = document.getElementById("profile-tier");
  elements.profileAvatar = document.getElementById("profile-avatar");
  elements.wrongNoteBtn = document.getElementById("btn-wrong-note");
  elements.reportBtn = document.getElementById("btn-report");
  elements.latestReportCard = document.getElementById("latest-report-card");
  elements.latestReportTitle = document.getElementById("latest-report-title");
  elements.latestReportMeta = document.getElementById("latest-report-meta");
  elements.latestReportDownloadBtn = document.getElementById("btn-latest-report-download");
  elements.logoutBtn = document.getElementById("btn-logout");
  elements.languageSetting = document.getElementById("language-setting");
  elements.difficultySetting = document.getElementById("difficulty-setting");
  elements.toast = document.getElementById("toast");
  elements.modal = document.getElementById("modal");
  elements.modalCard = elements.modal?.querySelector(".modal-card");
  elements.modalTitle = document.getElementById("modal-title");
  elements.modalBody = document.getElementById("modal-body");
  elements.modalClose = document.getElementById("modal-close");
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
  }  state.username = parseUsername(state.token);
  state.difficulty = getSavedDifficulty();
  renderUserInfo();
  bindEvents();
  renderDifficultyOptions();
  void loadLanguages();
  void loadProfile();
  await loadUserInfo();
  restoreLatestReportFromCache();
  renderLatestReportSummary();
  void loadLatestReportSummary();
}

function bindEvents() {
  elements.wrongNoteBtn?.addEventListener("click", openWrongNote);
  elements.reportBtn?.addEventListener("click", openReportModal);
  elements.latestReportDownloadBtn?.addEventListener("click", handleLatestReportDownload);
  elements.logoutBtn?.addEventListener("click", handleLogout);
  elements.modalClose?.addEventListener("click", hideModal);
  elements.modal?.addEventListener("click", (event) => {
    if (event.target === elements.modal) hideModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideModal();
  });
}

function renderUserInfo() {
  const label = state.displayName || state.username || "사용자";
  if (elements.profileName) elements.profileName.textContent = label;
  if (elements.profileAvatar) {
    const glyph = Array.from(label).find((char) => char.trim().length > 0) || "학";
    elements.profileAvatar.textContent = glyph;
  }
}

function buildAuthHeaders() {
  const headers = {};
  const token = state.token;
  const canUseBearer =
    token &&
    !(authClient && typeof authClient.isSessionMarker === "function" && authClient.isSessionMarker(token));
  if (canUseBearer) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function parseResponseBody(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function getLatestReportCacheUserKey() {
  if (
    authClient &&
    typeof authClient.isSessionMarker === "function" &&
    authClient.isSessionMarker(state.token) &&
    !Number.isInteger(Number(state.userId))
  ) {
    return "";
  }

  const userId = Number(state.userId);
  if (Number.isInteger(userId) && userId > 0) {
    return `id:${userId}`;
  }
  const username = normalizeText(state.username).toLowerCase();
  if (username) {
    return `username:${username}`;
  }
  return "";
}

function normalizeLatestReportPayload(payload) {
  const reportId = Number(payload?.reportId ?? payload?.report_id);
  const createdAt = payload?.createdAt ?? payload?.created_at ?? null;
  const goal = normalizeText(payload?.goal || payload?.title || payload?.reportGoal);
  const summary = normalizeText(payload?.summary || payload?.headline || payload?.solutionSummary);
  const pdfDownloadUrl = normalizeText(payload?.pdfDownloadUrl ?? payload?.pdf_download_url);
  const hasDownloadTarget = (Number.isInteger(reportId) && reportId > 0) || pdfDownloadUrl;

  if (!payload || payload.available === false || !hasDownloadTarget) {
    return null;
  }

  return {
    available: true,
    reportId: Number.isInteger(reportId) && reportId > 0 ? reportId : null,
    createdAt,
    goal,
    summary,
    pdfDownloadUrl,
  };
}

function persistLatestReportCache(latestReport, checkedAt = Date.now()) {
  const userKey = getLatestReportCacheUserKey();
  if (!userKey || !latestReport) {
    return;
  }

  try {
    window.localStorage.setItem(
      LATEST_REPORT_CACHE_KEY,
      JSON.stringify({
        userKey,
        userId: Number.isInteger(Number(state.userId)) ? Number(state.userId) : null,
        username: normalizeText(state.username).toLowerCase(),
        checkedAt: Number.isFinite(Number(checkedAt)) ? Number(checkedAt) : Date.now(),
        report: latestReport,
      })
    );
  } catch {
    // Ignore localStorage write failures.
  }
}

function readLatestReportCache() {
  const userKey = getLatestReportCacheUserKey();
  if (!userKey) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(LATEST_REPORT_CACHE_KEY);
    if (!raw) {
      return null;
    }
    const payload = JSON.parse(raw);
    if (!payload || payload.userKey !== userKey) {
      return null;
    }
    const report = normalizeLatestReportPayload({ available: true, ...(payload.report || {}) });
    if (!report) {
      return null;
    }
    const checkedAt = Number(payload.checkedAt);
    return {
      report,
      checkedAt: Number.isFinite(checkedAt) && checkedAt > 0 ? checkedAt : 0,
    };
  } catch {
    return null;
  }
}

function clearLatestReportCache() {
  try {
    window.localStorage.removeItem(LATEST_REPORT_CACHE_KEY);
  } catch {
    // Ignore localStorage delete failures.
  }
}

function restoreLatestReportFromCache() {
  const cached = readLatestReportCache();
  if (!cached) {
    return false;
  }

  state.latestReport = cached.report;
  state.latestReportStatus = "ready";
  state.latestReportError = "";
  state.latestReportCheckedAt = cached.checkedAt;
  return true;
}

function setLatestReport(payload, { persist = true, clearCache = true, checkedAt = Date.now() } = {}) {
  const latestReport = normalizeLatestReportPayload(payload);
  if (!latestReport) {
    state.latestReport = null;
    state.latestReportStatus = "empty";
    state.latestReportError = "";
    state.latestReportCheckedAt = Number.isFinite(Number(checkedAt)) ? Number(checkedAt) : 0;
    if (clearCache) {
      clearLatestReportCache();
    }
    return false;
  }

  state.latestReport = latestReport;
  state.latestReportStatus = "ready";
  state.latestReportError = "";
  state.latestReportCheckedAt = Number.isFinite(Number(checkedAt)) ? Number(checkedAt) : Date.now();
  if (persist) {
    persistLatestReportCache(latestReport, state.latestReportCheckedAt);
  }
  return true;
}

function isLatestReportSummaryStale(now = Date.now()) {
  if (!Number.isFinite(Number(state.latestReportCheckedAt)) || state.latestReportCheckedAt <= 0) {
    return true;
  }
  return now - state.latestReportCheckedAt >= LATEST_REPORT_REFRESH_TTL_MS;
}

function renderLatestReportSummary() {
  if (!elements.latestReportCard || !elements.latestReportTitle || !elements.latestReportMeta || !elements.latestReportDownloadBtn) {
    return;
  }

  elements.latestReportCard.classList.toggle("is-loading", state.latestReportStatus === "loading");
  elements.latestReportCard.classList.toggle("is-error", state.latestReportStatus === "error");

  if (state.latestReportStatus === "loading") {
    elements.latestReportCard.classList.add("is-empty");
    elements.latestReportTitle.textContent = "최근 학습 리포트를 확인하는 중입니다.";
    elements.latestReportMeta.textContent = "프로필 화면에서 바로 다시 다운로드할 수 있도록 최신 리포트를 불러오고 있습니다.";
    elements.latestReportDownloadBtn.textContent = "불러오는 중...";
    elements.latestReportDownloadBtn.disabled = true;
    elements.latestReportDownloadBtn.setAttribute("aria-busy", "true");
    return;
  }

  if (state.latestReportStatus === "error") {
    elements.latestReportCard.classList.add("is-empty");
    elements.latestReportTitle.textContent = "최근 학습 리포트를 불러오지 못했습니다.";
    elements.latestReportMeta.textContent = state.latestReportError || "잠시 후 다시 시도해 주세요.";
    elements.latestReportDownloadBtn.textContent = "다시 불러오기";
    elements.latestReportDownloadBtn.disabled = false;
    elements.latestReportDownloadBtn.setAttribute("aria-busy", "false");
    return;
  }

  const latest = state.latestReport;
  if (!latest || (!Number.isInteger(latest.reportId) && !latest.pdfDownloadUrl)) {
    elements.latestReportCard.classList.add("is-empty");
    elements.latestReportTitle.textContent = "아직 저장된 리포트가 없습니다.";
    elements.latestReportMeta.textContent = "학습 리포트를 생성하면 여기서 다시 PDF로 내려받을 수 있습니다.";
    elements.latestReportDownloadBtn.textContent = "최근 PDF 다운로드";
    elements.latestReportDownloadBtn.disabled = true;
    elements.latestReportDownloadBtn.setAttribute("aria-busy", "false");
    return;
  }

  elements.latestReportCard.classList.remove("is-empty");
  elements.latestReportTitle.textContent = latest.goal || "최근 학습 리포트";
  const metaParts = [];
  if (latest.createdAt) {
    metaParts.push(`생성 ${formatDate(latest.createdAt)}`);
  }
  if (latest.summary) {
    metaParts.push(latest.summary);
  }
  elements.latestReportMeta.textContent = metaParts.join(" · ") || "최근 생성한 학습 리포트를 다시 내려받을 수 있습니다.";
  elements.latestReportDownloadBtn.textContent = "최근 PDF 다운로드";
  elements.latestReportDownloadBtn.disabled = false;
  elements.latestReportDownloadBtn.setAttribute("aria-busy", "false");
}

async function requestLatestReportSummary() {
  const response = await fetch("/platform/reports/latest", {
    method: "GET",
    credentials: "same-origin",
    headers: buildAuthHeaders(),
  });
  const text = await response.text().catch(() => "");
  const data = parseResponseBody(text);

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const message = data?.detail || data?.message || "최근 리포트를 불러오지 못했습니다.";
    if (
      authClient &&
      typeof authClient.isAuthFailureStatus === "function" &&
      authClient.isAuthFailureStatus(response.status) &&
      typeof authClient.handleSessionExpired === "function"
    ) {
      authClient.handleSessionExpired(message);
    }
    throw new Error(message);
  }

  return data;
}

async function loadLatestReportSummary() {
  const requestId = state.latestReportRequestId + 1;
  state.latestReportRequestId = requestId;
  if (!state.latestReport) {
    state.latestReportStatus = "loading";
    state.latestReportError = "";
  }
  renderLatestReportSummary();

  try {
    const payload = await requestLatestReportSummary();
    if (state.latestReportRequestId !== requestId) return;
    if (payload === null) {
      setLatestReport(null, { persist: false, clearCache: true, checkedAt: Date.now() });
    } else if (!setLatestReport(payload, { persist: true, clearCache: false, checkedAt: Date.now() }) && !restoreLatestReportFromCache()) {
      setLatestReport(null, { persist: false, clearCache: false });
    }
  } catch (error) {
    if (state.latestReportRequestId !== requestId) return;
    if (!restoreLatestReportFromCache()) {
      state.latestReport = null;
      state.latestReportStatus = "error";
      state.latestReportError = error?.message || "최근 리포트를 불러오지 못했습니다.";
    }
  }

  if (state.latestReportRequestId === requestId) {
    renderLatestReportSummary();
  }
}

function renderReportOverviewModal() {
  const latest = state.latestReport;
  const hasLatest = latest && (Number.isInteger(latest.reportId) || normalizeText(latest.pdfDownloadUrl));
  const generatedAt = hasLatest && latest.createdAt
    ? `<p class="report-summary-meta">생성 ${escapeText(formatDate(latest.createdAt), "-")}</p>`
    : "";
  const latestSummary = hasLatest
    ? `
      <article class="report-summary-card report-summary-card-hero">
        <p class="report-summary-label">최근 저장본</p>
        <h4>${escapeText(latest.goal, "최근 학습 리포트")}</h4>
        ${generatedAt}
        <p class="report-summary-text">${escapeText(latest.summary, "최근 생성한 리포트를 다시 내려받을 수 있습니다.")}</p>
      </article>
    `
    : `
      <article class="report-summary-card report-summary-card-hero">
        <p class="report-summary-label">저장된 리포트</p>
        <h4>아직 저장된 리포트가 없습니다.</h4>
        <p class="report-summary-text">지금 생성하면 최근 학습 기록을 기준으로 새 리포트를 만들 수 있습니다.</p>
      </article>
    `;

  const statusBody = (() => {
    if (state.latestReportStatus === "loading") {
      return `
        <article class="report-summary-card">
          <p class="report-summary-label">최근 상태 확인 중</p>
          <p class="report-summary-text">최신 리포트 메타데이터를 불러오고 있습니다.</p>
        </article>
      `;
    }
    if (state.latestReportStatus === "error") {
      return `
        <article class="report-summary-card">
          <p class="report-summary-label">최근 상태 확인 실패</p>
          <p class="report-summary-text">${escapeText(state.latestReportError, "최근 리포트를 불러오지 못했습니다.")}</p>
        </article>
      `;
    }
    return `
      <article class="report-summary-card">
        <p class="report-summary-label">생성 방식</p>
        <p class="report-summary-text">모달을 열기만 해서는 새 리포트를 만들지 않습니다. 버튼을 눌렀을 때만 생성합니다.</p>
      </article>
    `;
  })();

  return `
    <section class="report-summary">
      <div class="report-summary-head">
        <div class="report-summary-copy">
          <p class="report-summary-kicker">학습 리포트</p>
          <h4>${hasLatest ? "최근 리포트 확인" : "새 리포트 생성"}</h4>
          <p class="report-summary-meta">최신 저장본을 확인하거나 필요할 때만 새 리포트를 생성하세요.</p>
        </div>
      </div>
      <div class="report-summary-cards">
        ${latestSummary}
        ${statusBody}
        <article class="report-summary-card">
          <p class="report-summary-label">다음 동작</p>
          <div class="dashboard-action-stack">
            <button id="report-generate-btn" type="button" class="primary">
              ${hasLatest ? "새 리포트 생성" : "지금 리포트 생성"}
            </button>
            ${hasLatest ? '<button id="report-modal-download-btn" type="button" class="ghost">최근 PDF 다운로드</button>' : ""}
            <button id="report-refresh-summary-btn" type="button" class="ghost">최신 상태 다시 확인</button>
          </div>
        </article>
      </div>
    </section>`;
}

function showReportOverviewModal() {
  showModal("학습 리포트", renderReportOverviewModal(), { wide: true });
  bindReportOverviewActions();
}

function isReportOverviewModalActive() {
  if (!elements.modal || elements.modal.classList.contains("hidden")) {
    return false;
  }
  return Boolean(document.getElementById("report-refresh-summary-btn"));
}

function bindReportOverviewActions() {
  const generateButton = document.getElementById("report-generate-btn");
  generateButton?.addEventListener("click", () => {
    void generateReport();
  });

  const refreshButton = document.getElementById("report-refresh-summary-btn");
  refreshButton?.addEventListener("click", async () => {
    await loadLatestReportSummary();
    if (!isReportOverviewModalActive()) return;
    showReportOverviewModal();
  });

  const downloadButton = document.getElementById("report-modal-download-btn");
  downloadButton?.addEventListener("click", () => {
    const latest = state.latestReport;
    if (!latest) return;
    void downloadReportPdf(latest.reportId, downloadButton, latest.pdfDownloadUrl);
  });
}

async function loadUserInfo() {
  try {
    const data = await apiRequest("/platform/me");
    state.userId = Number.isInteger(Number(data.id)) ? Number(data.id) : state.userId;
    state.username = data.username || state.username;
    state.displayName = data.display_name || data.displayName || state.username;
    if (state.displayName) {
      window.localStorage.setItem(DISPLAY_NAME_KEY, state.displayName);
    }
    renderUserInfo();
    return data;
  } catch {
    // Ignore and keep fallback from token
    return null;
  }
}

async function loadProfile() {
  try {
    const profile = await apiRequest("/platform/profile");
    const skillLevel = normalizeSkillLevel(profile.skillLevel || "level1");
    if (elements.profileTier) {
      elements.profileTier.textContent = formatSkillLabel(skillLevel);
    }
  } catch (err) {
    if (elements.profileTier) {
      elements.profileTier.textContent = "레벨 -";
    }
  }
}

async function loadLanguages() {
  if (!elements.languageSetting) return;
  elements.languageSetting.innerHTML = '<span class="empty">언어 목록을 불러오는 중...</span>';
  try {
    const payload = await apiRequest("/platform/languages");
    state.languages = payload.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    renderLanguageOptions();
  } catch (err) {
    elements.languageSetting.innerHTML = '<span class="empty">언어를 불러오지 못했습니다.</span>';
  }
}

function renderLanguageOptions() {
  if (!elements.languageSetting) return;
  elements.languageSetting.innerHTML = "";
  if (!state.languages.length) {
    elements.languageSetting.innerHTML = '<span class="empty">언어가 없습니다.</span>';
    return;
  }
  const select = document.createElement("select");
  select.className = "setting-select-control";
  select.id = "language-setting-select";
  select.setAttribute("aria-label", "문제 언어 선택");

  state.languages.forEach((lang) => {
    const option = document.createElement("option");
    option.value = lang.id;
    option.textContent = lang.title || formatLanguageLabel(lang.id);
    option.selected = lang.id === state.selectedLanguage;
    select.appendChild(option);
  });

  select.addEventListener("change", () => {
    setLanguage(select.value);
  });

  const hint = document.createElement("span");
  hint.className = "setting-select-hint";
  hint.textContent = "누르면 언어 목록이 열리고, 선택한 값이 모든 학습 모드에 공통 적용됩니다.";

  elements.languageSetting.appendChild(select);
  elements.languageSetting.appendChild(hint);
}

function normalizeSkillLevel(level) {
  const text = String(level || "").trim().toLowerCase();
  if (!text) return "level1";
  if (text === "beginner") return "level1";
  if (text === "intermediate") return "level5";
  if (text === "advanced") return "level10";
  if (/^\d+$/.test(text)) {
    const numeric = Math.min(10, Math.max(1, Number(text)));
    return `level${numeric}`;
  }
  const match = text.match(/^(?:level|레벨)[\s_-]*(\d{1,2})$/i);
  if (match) {
    const numeric = Math.min(10, Math.max(1, Number(match[1])));
    return `level${numeric}`;
  }
  return "level1";
}

function formatSkillLabel(level) {
  const match = normalizeSkillLevel(level).match(/\d+/);
  return `레벨 ${match ? match[0] : "1"}`;
}

function renderDifficultyOptions() {
  if (!elements.difficultySetting) return;
  elements.difficultySetting.innerHTML = "";
  DIFFICULTY_OPTIONS.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill";
    button.dataset.value = option.id;
    button.textContent = option.label;
    button.classList.toggle("active", option.id === state.difficulty);
    button.addEventListener("click", () => {
      setDifficulty(option.id);
    });
    elements.difficultySetting.appendChild(button);
  });
}

function setLanguage(value) {
  const normalizedValue = normalizeLanguageId(value);
  const isValid = state.languages.some((lang) => lang.id === normalizedValue);
  state.selectedLanguage = isValid ? normalizedValue : DEFAULT_LANGUAGE;
  window.localStorage.setItem(LANGUAGE_KEY, state.selectedLanguage);
  renderLanguageOptions();
  showToast("언어 설정이 저장되었습니다.");
}

function setDifficulty(value) {
  const isValid = DIFFICULTY_OPTIONS.some((option) => option.id === value);
  state.difficulty = isValid ? value : DEFAULT_DIFFICULTY;
  window.localStorage.setItem(DIFFICULTY_KEY, state.difficulty);
  renderDifficultyOptions();
  showToast("난이도 설정이 저장되었습니다.");
}

function getSavedLanguage(languages = []) {
  const saved = normalizeLanguageId(window.localStorage.getItem(LANGUAGE_KEY));
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
  if (DIFFICULTY_OPTIONS.some((option) => option.id === value)) {
    return value;
  }
  return DEFAULT_DIFFICULTY;
}

async function openWrongNote() {
  state.wrongNoteAdvancedProblems.clear();
  try {
    const payload = await apiRequest("/platform/learning/history");
    const list = (payload.history || []).filter((item) => item.correct === false);
    if (list.length === 0) {
      showModal("오답 노트", '<p class="empty">틀린 기록이 없습니다.</p>', { wide: true });
      return;
    }
    const items = list.map((item, index) => renderWrongNoteItem(item, index)).join("");
    showModal("오답 노트", `<ul class="list history-list">${items}</ul>`, {
      wide: true,
      maxWidth: "min(1280px, 97vw)",
    });
    mountWrongNoteAdvancedWorkbenches();
  } catch (error) {
    state.wrongNoteAdvancedProblems.clear();
    showModal("오답 노트", `<p class="empty">${escapeText(error.message, "기록을 불러오지 못했습니다.")}</p>`, { wide: true });
  }
}

function renderWrongNoteItem(item, index) {
  const modeLabel = formatModeLabel(item.mode);
  const modeKey = item.mode || "practice";
  const noteId = buildWrongNoteId(index);
  const advancedProblem = normalizeAdvancedHistoryProblem(item);
  if (advancedProblem) {
    state.wrongNoteAdvancedProblems.set(noteId, advancedProblem);
  }
  const summaryText = escapeText(item.summary || modeLabel || "요약 없음", "요약 없음");
  const metaParts = [];
  if (item.language) metaParts.push(`언어: ${formatLanguageLabel(item.language)}`);
  if (item.difficulty) metaParts.push(`난이도: ${formatDifficultyLabel(item.difficulty)}`);
  const metaHtml = metaParts.length
    ? `<p><strong>설정:</strong> ${metaParts.map((part) => escapeHtml(part)).join(" · ")}</p>`
    : "";
  const showRawCode = !["code-error", "code-arrange", "code-block"].includes(modeKey);
  const codeHtml = !advancedProblem && showRawCode && item.problem_code
    ? `<div class="code-block"><pre><code>${escapeHtml(item.problem_code)}</code></pre></div>`
    : "";
  const promptHtml = !advancedProblem && item.problem_prompt
    ? `<p><strong>질문:</strong> ${escapeText(item.problem_prompt)}</p>`
    : "";
  const modeHtml = buildModeDetail(item);
  const feedbackSummary = item.feedback?.summary;
  const feedbackHtml = !isAdvancedAnalysisMode(modeKey) && feedbackSummary
    ? `<p><strong>AI 피드백:</strong> ${escapeText(feedbackSummary)}</p>`
    : "";
  const scoreHtml =
    !isAdvancedAnalysisMode(modeKey) && item.score !== undefined && item.score !== null
      ? `<p>점수: ${escapeText(item.score)}</p>`
      : "";
  const safeDate = escapeHtml(formatDate(item.created_at));
  const safeModeLabel = escapeHtml(modeLabel || "학습 기록");
  const problemTitle = escapeText(item.problem_title, "제목 없음");
  const advancedContextHtml = advancedProblem
    ? renderAdvancedHistoryContext(noteId, advancedProblem)
    : "";
  const detailHtml = advancedProblem
    ? advancedContextHtml
    : `
        ${codeHtml}
        ${promptHtml}
        <hr />
        ${modeHtml}
        ${feedbackHtml}
        ${scoreHtml}
      `;

  return `
    <li>
      <details>
        <summary>
          <strong>${safeDate}</strong>
          <span>${summaryText}</span>
          <span class="badge soft">${safeModeLabel}</span>
          <span class="badge" data-state="negative">오답</span>
        </summary>
        <div class="history-detail">
          <p><strong>문제:</strong> ${problemTitle}</p>
          ${metaHtml}
          ${detailHtml}
        </div>
      </details>
    </li>`;
}

function buildModeDetail(item) {
  const mode = item.mode || "practice";
  if (isAdvancedAnalysisMode(mode)) {
    return "";
  }
  if (mode === "code-calc") {
    const submitted = escapeText(item.submitted_output, "없음");
    const expected = escapeText(item.expected_output, "없음");
    return `
      <p><strong>제출 출력:</strong> ${submitted}</p>
      <p><strong>정답 출력:</strong> ${expected}</p>
    `;
  }
  if (mode === "code-error") {
    const blocksHtml = buildErrorBlocks(item.problem_blocks, item.selected_index, item.correct_index);
    return blocksHtml || "<p class=\"empty\">블록 정보가 없습니다.</p>";
  }
  if (mode === "code-arrange") {
    const compareHtml = buildArrangeComparison(
      item.problem_blocks,
      item.submitted_order,
      item.correct_order
    );
    return compareHtml || "<p class=\"empty\">정렬 비교 정보를 찾지 못했습니다.</p>";
  }
  if (mode === "auditor") {
    const foundText = escapeList(item.found_types, "없음");
    const missedText = escapeList(item.missed_types, "없음");
    const reference = escapeText(item.reference_report);
    const explanation = escapeText(item.explanation, "내용 없음");
    return `
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 유형:</strong> ${foundText}</p>
      <p><strong>놓친 유형:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "context-inference") {
    const foundText = escapeList(item.found_types, "없음");
    const missedText = escapeList(item.missed_types, "없음");
    const reference = escapeText(item.reference_report);
    const inferenceType = normalizeText(item.inference_type);
    const inferenceTypeLabel =
      inferenceType === "pre_condition"
        ? "실행 전 추론"
        : inferenceType === "post_condition"
          ? "실행 후 추론"
          : inferenceType || "-";
    const explanation = escapeText(item.explanation, "내용 없음");
    const safeInferenceType = escapeHtml(inferenceTypeLabel);
    return `
      <p><strong>추론 타입:</strong> ${safeInferenceType}</p>
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "refactoring-choice") {
    const foundText = escapeList(item.found_types, "-");
    const missedText = escapeList(item.missed_types, "-");
    const selectedOption = escapeText(item.selected_option, "-");
    const bestOption = escapeText(item.best_option, "-");
    const reference = escapeText(item.reference_report);
    const optionReviews = Array.isArray(item.option_reviews)
      ? item.option_reviews
          .filter((row) => row && typeof row === "object")
          .map((row) => `${row.optionId || row.option_id || "-"}: ${row.summary || ""}`.trim())
          .filter((row) => row !== ":" && row.length > 0)
      : [];
    const optionReviewText = optionReviews.map((row) => escapeHtml(row)).join("\n");
    const optionReviewHtml = optionReviews.length
      ? `<p><strong>옵션 리뷰:</strong></p><p class="user-answer">${optionReviewText}</p>`
      : "";
    const explanation = escapeText(item.explanation, "내용 없음");
    return `
      <p><strong>선택한 옵션:</strong> ${selectedOption}</p>
      <p><strong>최적 옵션:</strong> ${bestOption}</p>
      <p><strong>제출 리포트:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${optionReviewHtml}
      ${reference ? `<p><strong>모범 리포트:</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "code-blame") {
    const foundText = escapeList(item.found_types, "-");
    const missedText = escapeList(item.missed_types, "-");
    const selectedCommitsText = escapeList(item.selected_commits, "-");
    const culpritCommitsText = escapeList(item.culprit_commits, "-");
    const commitReviews = Array.isArray(item.commit_reviews)
      ? item.commit_reviews
          .filter((row) => row && typeof row === "object")
          .map((row) => `${row.optionId || row.option_id || "-"}: ${row.summary || ""}`.trim())
          .filter((row) => row !== ":" && row.length > 0)
      : [];
    const commitReviewText = commitReviews.map((row) => escapeHtml(row)).join("\n");
    const reference = escapeText(item.reference_report);
    const errorLog = escapeText(item.problem_error_log);
    const reviewHtml = commitReviews.length
      ? `<p><strong>커밋 리뷰:</strong></p><p class="user-answer">${commitReviewText}</p>`
      : "";
    const logHtml = errorLog
      ? `<p><strong>에러 로그:</strong></p><div class="code-block"><pre><code>${errorLog}</code></pre></div>`
      : "";
    const explanation = escapeText(item.explanation, "-");
    return `
      ${logHtml}
      <p><strong>선택 커밋:</strong> ${selectedCommitsText}</p>
      <p><strong>범인 커밋:</strong> ${culpritCommitsText}</p>
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${reviewHtml}
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "code-block") {
    const options = Array.isArray(item.problem_options) ? item.problem_options : [];
    const selectedIndex = normalizeOptionIndex(item.selected_option);
    const selectedLabel =
      item.selected_option_text ||
      formatOptionLabel(options, item.selected_option) ||
      stripPrefix(item.explanation || "", "선택:") ||
      stripPrefix(item.explanation || "", "선택 옵션:");
    const rawCorrectIndex =
      item.correct_answer_index !== undefined && item.correct_answer_index !== null
        ? item.correct_answer_index
        : item.answer_index;
    const correctIndex = normalizeOptionIndex(rawCorrectIndex);
    const correctLabel = item.correct_option_text || formatOptionLabel(options, correctIndex);
    const selectedText = escapeText(selectedLabel || "없음", "없음");
    const correctText = escapeText(correctLabel || "없음", "없음");
    const codeWithBlankTiles = escapeHtml(item.problem_code || "")
      .replace(/\[BLANK\]/g, '<span class="history-blank-tile" aria-label="빈칸"></span>');
    const codeHtml = item.problem_code
      ? `
        <div class="history-code-window">
          <div class="history-code-title">문제 코드</div>
          <div class="history-code-block"><pre><code>${codeWithBlankTiles}</code></pre></div>
        </div>
      `
      : "";
    const choicesHtml = buildCodeBlockChoiceCards(options, selectedIndex, correctIndex);
    const pointText = buildCodeBlockLearningPoint({
      selectedLabel,
      correctLabel,
      selectedIndex,
      correctIndex,
    });
    return `
      ${codeHtml}
      <p><strong>내 선택:</strong> ${selectedText}</p>
      <p><strong>정답:</strong> ${correctText}</p>
      ${choicesHtml}
      <div class="history-learning-point">
        <strong>학습 포인트</strong>
        <p>${escapeHtml(pointText)}</p>
      </div>
    `;
  }
  const answer = escapeText(item.explanation, "내용 없음");
  return `
    <p><strong>제출 답변:</strong></p>
    <p class="user-answer">${answer}</p>
  `;
}

function isAdvancedAnalysisMode(mode) {
  return ADVANCED_HISTORY_MODES.has(String(mode || "").trim().toLowerCase());
}

function buildWrongNoteId(index) {
  return `wrong-note-${index + 1}`;
}

function mountWrongNoteAdvancedWorkbenches() {
  if (!elements.modalBody || state.wrongNoteAdvancedProblems.size === 0) {
    return;
  }

  state.wrongNoteAdvancedProblems.forEach((problem, noteId) => {
    const root = elements.modalBody.querySelector(`[data-history-workbench-id="${noteId}"]`);
    if (root) {
      mountAdvancedHistoryWorkbench(root, problem);
    }
  });
}

function renderAdvancedHistoryContext(noteId, problem) {
  return `
    <section class="history-advanced-context">
      ${buildAdvancedHistoryWorkbenchMarkup(noteId)}
    </section>
  `;
}

function buildAdvancedChecklist(checklist) {
  if (!Array.isArray(checklist) || checklist.length === 0) {
    return "";
  }
  const items = checklist.map((entry) => `<li>${escapeText(entry)}</li>`).join("");
  return `
    <div class="history-advanced-checklist">
      <strong>체크리스트</strong>
      <ul>${items}</ul>
    </div>
  `;
}

function buildAdvancedAnalysisModeDetail(item) {
  const explanation = escapeText(item.explanation, "내용 없음");
  const feedbackSummary = escapeText(item.feedback?.summary, "요약 없음");
  const strengths = escapeList(item.feedback?.strengths, "없음");
  const improvements = escapeList(item.feedback?.improvements, "없음");
  const score = escapeText(item.score, "-");
  const reference = escapeText(item.reference_report);
  const referenceHtml = reference
    ? `
      <article class="advanced-result-card history-advanced-reference-card">
        <h4>모범 리포트</h4>
        <p class="user-answer">${reference}</p>
      </article>
    `
    : "";

  return `
    <div class="history-advanced-report-grid">
      <article class="advanced-result-card">
        <h4>내 제출 리포트</h4>
        <p class="user-answer">${explanation}</p>
      </article>
      <article class="advanced-result-card">
        <h4>채점 결과</h4>
        <p><strong>점수:</strong> ${score}</p>
        <p><strong>AI 요약:</strong> ${feedbackSummary}</p>
        <p><strong>강점:</strong> ${strengths}</p>
        <p><strong>개선 포인트:</strong> ${improvements}</p>
      </article>
      ${referenceHtml}
    </div>
  `;
}

function formatModeLabel(value) {
  return MODE_LABELS[value] || value || "학습 기록";
}

function formatDifficultyLabel(value) {
  const found = DIFFICULTY_OPTIONS.find((option) => option.id === value);
  return found?.label || value || "-";
}

function formatLanguageLabel(value) {
  const normalized = normalizeLanguageId(value);
  return LANGUAGE_LABELS[normalized] || normalized || "-";
}

function formatIndexLabel(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "없음";
  }
  return `${numeric + 1}번`;
}

function stripPrefix(text, prefix) {
  if (!text) return "";
  return text.startsWith(prefix) ? text.slice(prefix.length).trim() : text;
}

function normalizeOptionIndex(value) {
  const index = Number(value);
  return Number.isInteger(index) && index >= 0 ? index : null;
}

function buildCodeBlockChoiceCards(options, selectedIndex, correctIndex) {
  if (!Array.isArray(options) || options.length === 0) {
    return '<p class="empty">선택지 정보가 없습니다.</p>';
  }
  const cardsHtml = options
    .map((option, idx) => {
      const classes = ["history-choice-card"];
      if (idx === selectedIndex) classes.push("is-selected");
      if (idx === correctIndex) classes.push("is-correct");
      if (idx === selectedIndex && idx !== correctIndex) classes.push("is-wrong");
      return `
        <div class="${classes.join(" ")}">
          <div class="history-choice-index">${idx + 1}번 선택지</div>
          <pre><code>${escapeHtml(String(option ?? ""))}</code></pre>
        </div>
      `;
    })
    .join("");
  return `
    <div class="history-choice-grid">
      ${cardsHtml}
    </div>
  `;
}

function buildCodeBlockLearningPoint({ selectedLabel, correctLabel, selectedIndex, correctIndex }) {
  if (selectedLabel && correctLabel && selectedIndex !== null && correctIndex !== null) {
    if (selectedIndex === correctIndex) {
      return `정답(${correctLabel})을 정확히 선택했습니다. 같은 유형에서 왜 이 선택지가 맞는지 근거까지 함께 설명해 보세요.`;
    }
    return `내 선택은 "${selectedLabel}"이고 정답은 "${correctLabel}"입니다. 코드 흐름에서 빈칸 앞뒤 문맥을 기준으로 차이를 비교해 보세요.`;
  }
  return "선택지의 의미와 코드 문맥을 함께 비교해 빈칸의 의도를 파악해 보세요.";
}

function buildErrorBlocks(blocks, selectedIndex, correctIndex) {
  if (!Array.isArray(blocks) || blocks.length === 0) return "";
  return `
    <div class="history-blocks">
      ${blocks
        .map((block, idx) => {
          const classes = ["history-block"];
          if (idx === selectedIndex) classes.push("is-selected");
          if (idx === correctIndex) classes.push("is-correct");
          if (idx === selectedIndex && idx !== correctIndex) classes.push("is-wrong");
          const code = typeof block === "string" ? block : block?.code || "";
          return `
            <div class="${classes.join(" ")}">
              <div class="history-block-label">${idx + 1}번</div>
              <pre><code>${escapeHtml(code)}</code></pre>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildArrangeComparison(blocks, submittedOrder, correctOrder) {
  if (!Array.isArray(blocks) || blocks.length === 0) return "";
  const blockMap = new Map();
  blocks.forEach((block, idx) => {
    if (block && typeof block === "object") {
      const id = block.id ?? String(idx);
      blockMap.set(id, block.code || "");
    } else {
      blockMap.set(String(idx), String(block ?? ""));
    }
  });
  const submitted = Array.isArray(submittedOrder) ? submittedOrder : [];
  const correct = Array.isArray(correctOrder) ? correctOrder : [];
  return `
    <div class="compare-grid">
      <div class="compare-panel">
        <p class="compare-title">제출 순서</p>
        ${renderArrangeBlocks(submitted, blockMap)}
      </div>
      <div class="compare-panel">
        <p class="compare-title">정답 순서</p>
        ${renderArrangeBlocks(correct, blockMap)}
      </div>
    </div>
  `;
}

function renderArrangeBlocks(order, blockMap) {
  if (!order.length) {
    return '<p class="empty">블록 정보가 없습니다.</p>';
  }
  const blocksHtml = order
    .map((id, idx) => {
      const code = blockMap.get(id) ?? blockMap.get(String(idx)) ?? "";
      return `
        <div class="history-block">
          <div class="history-block-label">${idx + 1}번</div>
          <pre><code>${escapeHtml(code)}</code></pre>
        </div>
      `;
    })
    .join("");
  return `<div class="history-blocks">${blocksHtml}</div>`;
}

function formatOptionLabel(options, indexValue) {
  if (!Array.isArray(options)) return "";
  const idx = Number(indexValue);
  if (!Number.isFinite(idx) || idx < 0 || idx >= options.length) return "";
  const value = options[idx];
  return value ? value : "";
}

function setReportButtonLoading(isLoading) {
  if (!elements.reportBtn) return;
  elements.reportBtn.disabled = isLoading;
  elements.reportBtn.classList.toggle("loading", isLoading);
  elements.reportBtn.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function stopReportLoadingAnimation() {
  if (!state.reportLoadingTimer) return;
  window.clearInterval(state.reportLoadingTimer);
  state.reportLoadingTimer = null;
}

function waitForNextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    });
  });
}

function renderReportLoadingBody(activeStepIndex, tickCount = 0) {
  const activeIndex = Math.max(0, Math.min(activeStepIndex, REPORT_LOADING_STEPS.length - 1));
  const step = REPORT_LOADING_STEPS[activeIndex];
  const progress = Math.min(94, 24 + tickCount * 10);
  const steps = REPORT_LOADING_STEPS.map((item, index) => {
    const statusClass = index < activeIndex ? "is-done" : index === activeIndex ? "is-active" : "";
    return `<li class="${statusClass}">${escapeHtml(item.label)}</li>`;
  }).join("");

  return `
    <section class="report-loading" role="status" aria-live="polite">
      <div class="report-loading-head">
        <span class="report-loading-spinner" aria-hidden="true"></span>
        <div class="report-loading-copy">
          <p class="report-loading-kicker">학습 리포트 생성 중</p>
          <p class="report-loading-title">${escapeHtml(step.label)}</p>
          <p class="report-loading-desc">${escapeHtml(step.description)}</p>
        </div>
      </div>
      <div class="report-loading-bar" aria-hidden="true">
        <span style="width:${progress}%"></span>
      </div>
      <ol class="report-loading-steps">${steps}</ol>
      <div class="report-loading-skeleton" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
        <span></span>
      </div>
    </section>`;
}

function startReportLoadingAnimation(requestId) {
  stopReportLoadingAnimation();

  let tickCount = 0;
  showModal("학습 리포트", renderReportLoadingBody(0, tickCount), { wide: true });

  state.reportLoadingTimer = window.setInterval(() => {
    if (state.activeReportRequestId !== requestId) {
      stopReportLoadingAnimation();
      return;
    }
    tickCount += 1;
    const activeStepIndex = tickCount % REPORT_LOADING_STEPS.length;
    if (elements.modalBody) {
      elements.modalBody.innerHTML = renderReportLoadingBody(activeStepIndex, tickCount);
    }
  }, 1200);
}

function collectReportActions(payload) {
  const briefActions = Array.isArray(payload?.reportBrief?.nextSteps)
    ? payload.reportBrief.nextSteps
    : Array.isArray(payload?.reportBrief?.focusActions)
      ? payload.reportBrief.focusActions
    : [];
  const sources = [briefActions, payload?.priorityActions, payload?.phasePlan, payload?.dailyHabits];
  const deduped = [];
  const seen = new Set();

  sources.forEach((items) => {
    if (!Array.isArray(items)) return;
    items.forEach((item) => {
      const normalized = normalizeText(item);
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      deduped.push(normalized);
    });
  });

  return deduped.slice(0, 3);
}

function collectReportCheckpoints(payload) {
  const briefCheckpoints = Array.isArray(payload?.reportBrief?.checkpoints)
    ? payload.reportBrief.checkpoints
    : [];
  const sources = [briefCheckpoints, payload?.checkpoints, payload?.metricsToTrack];
  const deduped = [];
  const seen = new Set();

  sources.forEach((items) => {
    if (!Array.isArray(items)) return;
    items.forEach((item) => {
      const normalized = normalizeText(item);
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      deduped.push(normalized);
    });
  });

  return deduped.slice(0, 3);
}

function renderReportMetricGrid(metric, metricItems) {
  const normalizedItems = Array.isArray(metricItems) && metricItems.length
    ? metricItems
    : [
        { label: "시도 수", value: `${normalizeText(metric.attempts || 0) || "0"}회` },
        { label: "정확도", value: `${normalizeText(metric.accuracy ?? "-") || "-"}%` },
        { label: "평균 점수", value: normalizeText(metric.avgScore ?? "-") || "-" },
        { label: "추세", value: normalizeText(metric.trend ?? "데이터 부족") || "데이터 부족" },
      ];

  return normalizedItems
    .map(
      (item) => `
        <div class="report-metric-item">
          <span class="report-metric-label">${escapeHtml(item.label || "-")}</span>
          <strong class="report-metric-value">${escapeHtml(item.value || "-")}</strong>
        </div>
      `
    )
    .join("");
}

function renderReportActionList(actions) {
  if (!actions.length) {
    return '<p class="empty">바로 실행할 액션이 없습니다.</p>';
  }

  return `
    <ol class="report-action-list">
      ${actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ol>
  `;
}

function collectReportStudyGuide(brief) {
  const candidates = [brief?.studyGuide, brief?.nextSteps];
  const lines = [];
  const seen = new Set();

  candidates.forEach((value) => {
    if (Array.isArray(value)) {
      value.forEach((entry) => {
        const normalized = normalizeText(entry);
        if (!normalized || seen.has(normalized)) return;
        seen.add(normalized);
        lines.push(normalized);
      });
      return;
    }

    const normalized = normalizeText(value);
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    lines.push(normalized);
  });

  return lines.slice(0, 4);
}

function renderReportStudyGuide(lines) {
  if (!Array.isArray(lines) || lines.length === 0) {
    return "";
  }

  const hasMultipleItems = lines.length > 1;
  const contentHtml = hasMultipleItems
    ? `
      <ol class="report-guide-list">
        ${lines.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ol>
    `
    : `<p class="report-summary-text">${escapeHtml(lines[0])}</p>`;

  return `
    <article class="report-summary-card report-summary-card-guide">
      <div class="report-guide-head">
        <p class="report-summary-label">앞으로 이렇게 학습하세요</p>
        <p class="report-guide-caption">다음 학습에서 바로 적용할 수 있는 안내입니다.</p>
      </div>
      ${contentHtml}
    </article>
  `;
}

function renderReportContent(payload) {
  const metric = payload.metricSnapshot || {};
  const brief = payload.reportBrief || {};
  const reportId = Number(payload.reportId);
  const actions = collectReportActions(payload);
  const checkpoints = collectReportCheckpoints(payload);
  const studyGuide = collectReportStudyGuide(brief);
  const canDownload = Number.isInteger(reportId) && reportId > 0;
  const metaParts = [
    `생성 ${escapeText(formatDate(payload.createdAt), "-")}`,
    normalizeText(brief.title || payload.goal) ? `목표 ${escapeText(brief.title || payload.goal)}` : "",
  ].filter(Boolean);
  const headline = brief.headline || payload.goal || "핵심만 빠르게 확인하세요";
  const summary = brief.summary || payload.solutionSummary || "요약이 없습니다.";

  return `
    <section class="report-summary">
      <div class="report-summary-head">
        <div class="report-summary-copy">
          <p class="report-summary-kicker">학습 리포트</p>
          <h4>${escapeText(headline, "핵심만 빠르게 확인하세요")}</h4>
          <p class="report-summary-meta">${metaParts.join('<span aria-hidden="true">·</span>')}</p>
        </div>
        ${
          canDownload
            ? '<button id="report-pdf-download" type="button" class="ghost report-download-btn">PDF 다운로드</button>'
            : ""
        }
      </div>
      <div class="report-summary-cards">
        <article class="report-summary-card report-summary-card-hero">
          <p class="report-summary-label">핵심 요약</p>
          <p class="report-summary-text">${escapeText(summary, "요약이 없습니다.")}</p>
        </article>
        <article class="report-summary-card">
          <p class="report-summary-label">핵심 지표</p>
          <div class="report-metric-grid">
            ${renderReportMetricGrid(metric, brief.metrics)}
          </div>
        </article>
        <article class="report-summary-card">
          <p class="report-summary-label">실행 지시</p>
          ${renderReportActionList(actions)}
        </article>
        <article class="report-summary-card">
          <p class="report-summary-label">체크포인트</p>
          ${renderReportActionList(checkpoints)}
        </article>
        ${renderReportStudyGuide(studyGuide)}
      </div>
    </section>`;
}

async function downloadReportPdf(reportId, trigger, downloadUrl) {
  const normalizedDownloadUrl = normalizeText(downloadUrl);
  const hasReportId = Number.isInteger(reportId) && reportId > 0;
  if (!hasReportId && !normalizedDownloadUrl) {
    showToast("다운로드할 리포트가 없습니다.");
    return;
  }

  trigger?.setAttribute("aria-busy", "true");
  if (trigger instanceof HTMLButtonElement) {
    trigger.disabled = true;
  }

  try {
    const response = await fetch(normalizedDownloadUrl || `/platform/reports/${reportId}/pdf`, {
      method: "GET",
      credentials: "same-origin",
      headers: buildAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 404) {
        clearLatestReportCache();
        if (state.latestReport && state.latestReport.reportId === reportId) {
          state.latestReport = null;
          state.latestReportStatus = "empty";
          state.latestReportError = "";
          renderLatestReportSummary();
        }
      }
      const contentType = response.headers.get("content-type") || "";
      let message = "PDF 다운로드에 실패했습니다.";

      if (contentType.includes("application/json")) {
        const data = await response.json().catch(() => null);
        message = data?.detail || data?.message || message;
      } else {
        const text = await response.text().catch(() => "");
        if (text) {
          message = text;
        }
      }

      if (
        authClient &&
        typeof authClient.isAuthFailureStatus === "function" &&
        authClient.isAuthFailureStatus(response.status) &&
        typeof authClient.handleSessionExpired === "function"
      ) {
        authClient.handleSessionExpired(message);
      }

      throw new Error(message);
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = hasReportId ? `learning-report-${reportId}.pdf` : "learning-report.pdf";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    showToast("PDF 다운로드를 시작했습니다.");
  } catch (error) {
    showToast(error?.message || "PDF 다운로드에 실패했습니다.");
  } finally {
    trigger?.setAttribute("aria-busy", "false");
    if (trigger instanceof HTMLButtonElement) {
      trigger.disabled = false;
    }
  }
}

function handleLatestReportDownload() {
  if (state.latestReportStatus === "error") {
    void loadLatestReportSummary();
    return;
  }

  const latest = state.latestReport;
  if (!latest) {
    showToast("다운로드할 최근 리포트가 없습니다.");
    return;
  }
  void downloadReportPdf(latest.reportId, elements.latestReportDownloadBtn, latest.pdfDownloadUrl);
}

function bindReportModalActions(payload) {
  const reportId = Number(payload?.reportId);
  const downloadUrl = normalizeText(payload?.pdfDownloadUrl);
  const downloadButton = document.getElementById("report-pdf-download");
  downloadButton?.addEventListener("click", () => {
    void downloadReportPdf(reportId, downloadButton, downloadUrl);
  });
}

function showReportErrorModal(error) {
  const message = escapeText(error?.message, "리포트를 불러오지 못했습니다.");
  const body = `
    <div class="report-loading-error">
      <p class="report-loading-error-title">리포트 생성에 실패했습니다.</p>
      <p class="report-loading-error-desc">${message}</p>
      <button id="report-retry-btn" type="button" class="primary block">다시 시도</button>
    </div>
  `;
  showModal("학습 리포트", body, { wide: true });
  const retryButton = document.getElementById("report-retry-btn");
  retryButton?.addEventListener(
    "click",
    () => {
      void generateReport();
    },
    { once: true }
  );
}

function showReportBlockedModal(payload) {
  const currentAttemptCount = Number(payload?.currentAttemptCount);
  const minimumRequiredAttempts = Number(payload?.minimumRequiredAttempts);
  const current = Number.isFinite(currentAttemptCount) ? currentAttemptCount : 0;
  const minimum = Number.isFinite(minimumRequiredAttempts) && minimumRequiredAttempts > 0 ? minimumRequiredAttempts : 10;
  const blockingMessage = escapeText(
    payload?.blockingMessage,
    `학습 리포트를 생성하려면 최소 ${minimum}문제 이상 풀이해야 합니다. 현재 ${current}문제를 풀었으니 문제를 더 풀어 주세요.`
  );
  const body = `
    <div class="report-loading-error">
      <p class="report-loading-error-title">리포트 생성 준비 중입니다.</p>
      <p class="report-loading-error-desc">${blockingMessage}</p>
      <p class="report-loading-error-desc">현재 ${current}문제 · 최소 ${minimum}문제</p>
      <button id="report-blocked-close-btn" type="button" class="primary block">확인</button>
    </div>
  `;
  showModal("학습 리포트", body, { wide: true });
  document.getElementById("report-blocked-close-btn")?.addEventListener("click", hideModal, { once: true });
}

async function openReportModal() {
  showReportOverviewModal();

  if (
    state.latestReportStatus === "idle" ||
    state.latestReportStatus === "loading" ||
    isLatestReportSummaryStale()
  ) {
    await loadLatestReportSummary();
    if (!isReportOverviewModalActive()) return;
    showReportOverviewModal();
  }
}

async function generateReport() {
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  state.activeReportRequestId = requestId;
  setReportButtonLoading(true);
  startReportLoadingAnimation(requestId);

  try {
    await waitForNextPaint();
    if (state.activeReportRequestId !== requestId) return;
    const payload = await apiRequest("/platform/reports/milestone", {
      method: "POST",
      body: { problem_count: 10 },
    });
    if (state.activeReportRequestId !== requestId) return;
    if (normalizeText(payload?.status) === "insufficient_history") {
      stopReportLoadingAnimation();
      showReportBlockedModal(payload);
      return;
    }
    state.latestReportRequestId += 1;
    setLatestReport({
      available: Number(payload?.reportId) > 0,
      reportId: payload?.reportId,
      createdAt: payload?.createdAt || null,
      goal: payload?.reportBrief?.title || payload?.goal || "",
      summary: payload?.reportBrief?.summary || payload?.solutionSummary || "",
      pdfDownloadUrl: payload?.pdfDownloadUrl || "",
    });
    renderLatestReportSummary();
    stopReportLoadingAnimation();
    showModal("학습 리포트", renderReportContent(payload), { wide: true });
    bindReportModalActions(payload);
  } catch (error) {
    if (state.activeReportRequestId !== requestId) return;
    stopReportLoadingAnimation();
    showReportErrorModal(error);
  } finally {
    if (state.activeReportRequestId === requestId) {
      state.activeReportRequestId = null;
    }
    setReportButtonLoading(false);
  }
}

function handleLogout() {
  clearLatestReportCache();
  if (authClient) {
    authClient.clearSession();
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem("code-learning-display-name");
  }
  window.location.href = "/index.html";
}

function showModal(title, bodyHtml, options = {}) {
  if (!elements.modal) return;
  const { wide = false, maxWidth = "min(1100px, 96vw)" } = options;
  const desktopWide = wide && window.matchMedia("(min-width: 1024px)").matches;
  elements.modalTitle.textContent = title;
  elements.modalBody.innerHTML = bodyHtml;
  elements.modalCard?.classList.toggle("modal-wide", wide);
  if (elements.modalCard) {
    elements.modalCard.style.width = desktopWide ? maxWidth : "";
  }
  elements.modal.classList.remove("hidden");
}

function hideModal() {
  stopReportLoadingAnimation();
  state.activeReportRequestId = null;
  state.wrongNoteAdvancedProblems.clear();
  elements.modalCard?.classList.remove("modal-wide");
  if (elements.modalCard) {
    elements.modalCard.style.width = "";
  }
  elements.modal?.classList.add("hidden");
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

function parseUsername(token) {
  if (authClient) {
    return authClient.parseUsername(token);
  }
  if (!token) return "";
  return token.split(":", 1)[0];
}


function buildList(items, emptyText) {
  const normalized = Array.isArray(items)
    ? items.map((item) => normalizeText(item)).filter((item) => item.length > 0)
    : [];
  if (!normalized.length) {
    return `<p class="empty">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="list">${normalized.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Seoul",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
