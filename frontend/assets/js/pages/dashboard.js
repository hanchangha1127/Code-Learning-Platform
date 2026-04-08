const TOKEN_KEY = "code-learning-token";
const DISPLAY_NAME_KEY = "code-learning-display-name";
const authClient = window.CodeAuth || null;
const DEFAULT_DAILY_TARGET = 10;

const features = [];
const advancedFeatures = [
  normalizeFeature({
    id: "single-file-analysis",
    title: "단일 파일 분석",
    description: "하나의 핵심 파일을 읽기 전용 IDE 화면에서 끝까지 분석해 보세요.",
    icon: "🧠",
    link: "/single-file-analysis.html",
    badge: "",
  }, 0, "advanced-feature"),
  normalizeFeature({
    id: "multi-file-analysis",
    title: "다중 파일 분석",
    description: "2~6개 파일을 오가며 호출 흐름과 책임 분리를 추적해 보세요.",
    icon: "🗂️",
    link: "/multi-file-analysis.html",
    badge: "",
  }, 1, "advanced-feature"),
  normalizeFeature({
    id: "fullstack-analysis",
    title: "풀스택 코드 분석",
    description: "3~8개 파일과 백엔드/프론트엔드 흐름을 함께 해석해 보세요.",
    icon: "🌐",
    link: "/fullstack-analysis.html",
    badge: "",
  }, 2, "advanced-feature"),
];
const elements = {};
const state = {
  token: null,
  me: null,
  home: null,
  goal: null,
  isGeneratingReport: false,
  activeModeTab: "general",
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "대시보드 정보를 불러오지 못했습니다.",
});

function cacheDom() {
  elements.featureGrid = document.getElementById("feature-grid");
  elements.advancedFeatureGrid = document.getElementById("advanced-feature-grid");
  elements.userChip = document.getElementById("dashboard-user");
  elements.logoutBtn = document.getElementById("dashboard-logout-btn");
  elements.heroTitle = document.getElementById("dashboard-hero-title");
  elements.heroSummary = document.getElementById("dashboard-hero-summary");
  elements.recommendedModes = document.getElementById("dashboard-recommended-modes");
  elements.streakDays = document.getElementById("dashboard-streak-days");
  elements.goalProgress = document.getElementById("dashboard-goal-progress");
  elements.goalHint = document.getElementById("dashboard-goal-hint");
  elements.taskList = document.getElementById("dashboard-task-list");
  elements.reviewList = document.getElementById("dashboard-review-list");
  elements.weakTopics = document.getElementById("dashboard-weak-topics");
  elements.goalForm = document.getElementById("dashboard-goal-form");
  elements.goalInput = document.getElementById("dashboard-goal-input");
  elements.goalSubmit = document.getElementById("dashboard-goal-submit");
  elements.goalPresets = document.getElementById("dashboard-goal-presets");
  elements.weeklyReportCard = document.getElementById("dashboard-weekly-report-card");
  elements.reportStatus = document.getElementById("dashboard-report-status");
  elements.notificationList = document.getElementById("dashboard-notification-list");
  elements.modeTabs = Array.from(document.querySelectorAll("[data-mode-tab]"));
  elements.modePanels = Array.from(document.querySelectorAll("[data-mode-panel]"));
}

async function init() {
  cacheDom();
  state.token = await ensureSession();
  if (!state.token) return;

  bindEvents();
  seedDefaultFeatures();
  renderModePanels();
  renderAdvancedFeatures();
  renderLoadingState();

  try {
    await Promise.all([loadMe(), loadHomeAndGoal()]);
    renderHome();
    renderFeatures();
  } catch (error) {
    renderErrorState(error);
  }
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
  elements.logoutBtn?.addEventListener("click", handleLogout);
  elements.goalForm?.addEventListener("submit", handleGoalSubmit);
  elements.goalPresets?.addEventListener("click", handleGoalPresetClick);
  elements.weeklyReportCard?.addEventListener("click", handleWeeklyReportCardClick);
  elements.modeTabs?.forEach((button) => button.addEventListener("click", handleModeTabClick));
}

function handleModeTabClick(event) {
  const nextMode = event.currentTarget?.dataset?.modeTab;
  if (!nextMode || nextMode === state.activeModeTab) {
    return;
  }
  state.activeModeTab = nextMode;
  renderModePanels();
}

function handleGoalPresetClick(event) {
  const button = event.target.closest("button[data-goal]");
  if (!button || !elements.goalInput) return;
  elements.goalInput.value = button.dataset.goal || String(DEFAULT_DAILY_TARGET);
}

function handleLogout() {
  if (authClient?.clearSession) {
    authClient.clearSession();
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(DISPLAY_NAME_KEY);
  }
  window.location.replace("/index.html");
}

async function loadMe() {
  state.me = await apiRequest("/platform/me");
  const displayName = state.me.display_name || state.me.displayName || state.me.username || "사용자";
  window.localStorage.setItem(DISPLAY_NAME_KEY, displayName);
  if (elements.userChip) {
    elements.userChip.textContent = displayName;
  }
}

async function loadHomeAndGoal() {
  const [home, goal] = await Promise.all([
    apiRequest("/platform/home"),
    apiRequest("/platform/me/goal"),
  ]);
  state.home = home;
  state.goal = goal;
}

function renderLoadingState() {
  if (elements.taskList) {
    elements.taskList.innerHTML = '<p class="empty">오늘 할 일을 정리하는 중입니다.</p>';
  }
  if (elements.reviewList) {
    elements.reviewList.innerHTML = '<p class="empty">복습 큐를 불러오는 중입니다.</p>';
  }
  if (elements.weeklyReportCard) {
    elements.weeklyReportCard.innerHTML = '<p class="empty">주간 리포트를 불러오는 중입니다.</p>';
  }
  if (elements.notificationList) {
    elements.notificationList.innerHTML = '<p class="empty">알림을 계산하는 중입니다.</p>';
  }
  if (elements.weakTopics) {
    elements.weakTopics.innerHTML = '<p class="empty">약점 주제를 정리하는 중입니다.</p>';
  }
}

function renderHome() {
  const home = state.home || {};
  const goal = state.goal || {};
  const displayName = home.displayName || state.me?.display_name || state.me?.displayName || state.me?.username || "사용자";
  const dailyGoal = home.dailyGoal || {};
  const trend = home.trend || {};
  const reviewQueue = home.reviewQueue || { dueCount: 0, items: [] };
  const stats = home.stats || {};
  const todayTasks = Array.isArray(home.todayTasks) ? home.todayTasks : [];
  const weakTopics = Array.isArray(home.weakTopics) ? home.weakTopics : [];
  const recommendedModes = Array.isArray(home.recommendedModes) ? home.recommendedModes : [];
  const totalAttempts = Number(stats.totalAttempts || 0);
  const accuracy = formatAccuracyText(stats.accuracy);
  const last7Attempts = Number(trend.last7DaysAttempts || 0);

  if (elements.userChip) {
    elements.userChip.textContent = displayName;
  }
  if (elements.heroTitle) {
    elements.heroTitle.textContent = `${displayName}님의 오늘 학습 홈`;
  }
  if (elements.heroSummary) {
    const goalText = dailyGoal.achieved
      ? "오늘 목표를 달성했습니다."
      : `오늘 목표까지 ${dailyGoal.remainingSessions || 0}문제가 남았습니다.`;
    elements.heroSummary.textContent = `최근 7일 ${last7Attempts}회 시도, 정확도 ${accuracy}. ${goalText}`;
  }
  if (elements.streakDays) {
    elements.streakDays.textContent = `${home.streakDays || 0}일`;
  }
  if (elements.goalProgress) {
    elements.goalProgress.textContent = `${dailyGoal.completedSessions || 0} / ${dailyGoal.targetSessions || goal.dailyTargetSessions || 0}`;
  }
  if (elements.goalHint) {
    elements.goalHint.textContent = dailyGoal.achieved
      ? "오늘 목표를 채웠습니다."
      : `오늘 목표까지 ${dailyGoal.remainingSessions || 0}문제가 남았습니다.`;
  }
  if (elements.goalInput) {
    elements.goalInput.value = String(goal.dailyTargetSessions || dailyGoal.targetSessions || DEFAULT_DAILY_TARGET);
  }

  renderTodayTasks(todayTasks);
  renderReviewQueue(reviewQueue.items || []);
  renderWeakTopics(weakTopics, totalAttempts, accuracy);
  renderRecommendedModes(recommendedModes);
  renderWeeklyReportCard(home.weeklyReportCard || {});
  renderNotifications(home.notifications || []);
  applyFeatureBadges(recommendedModes);
  renderFeatures();
}

function renderTodayTasks(tasks) {
  if (!elements.taskList) return;
  if (!Array.isArray(tasks) || tasks.length === 0) {
    elements.taskList.innerHTML = '<p class="empty">오늘 바로 처리할 작업이 없습니다.</p>';
    return;
  }

  elements.taskList.innerHTML = tasks.map((task) => `
    <article class="task-card">
      <div>
        <span class="task-type">${escapeHtml(task.type || "task")}</span>
        <h4>${escapeHtml(task.title || "학습 작업")}</h4>
        <p>${escapeHtml(task.description || "")}</p>
      </div>
      <a class="primary" href="${escapeAttr(task.actionLink || "/dashboard.html")}">${escapeHtml(task.actionLabel || "시작")}</a>
    </article>
  `).join("");
}

function renderReviewQueue(items) {
  if (!elements.reviewList) return;
  if (!Array.isArray(items) || items.length === 0) {
    elements.reviewList.innerHTML = '<p class="empty">지금 바로 다시 볼 복습 문제가 없습니다.</p>';
    return;
  }

  elements.reviewList.innerHTML = items.map((item) => `
    <article class="review-card">
      <div class="review-card-main">
        <div class="review-card-top">
          <h4>${escapeHtml(item.title || "복습 문제")}</h4>
          <span class="review-priority">우선순위 ${escapeHtml(item.priority ?? 0)}</span>
        </div>
        <div class="review-card-meta">
          <span class="pill soft">${escapeHtml(item.modeLabel || item.mode || "학습")}</span>
          <span class="review-weakness">${escapeHtml(item.weaknessLabel || item.weaknessTag || "약점 보강")}</span>
        </div>
      </div>
      <a class="ghost review-card-action" href="${escapeAttr(item.resumeLink || item.actionLink || "/dashboard.html")}">다시 열기</a>
    </article>
  `).join("");
}

function renderWeakTopics(topics, totalAttempts, accuracyText) {
  if (!elements.weakTopics) return;
  if (!Array.isArray(topics) || topics.length === 0) {
    elements.weakTopics.innerHTML = `
      <div class="dashboard-inline-note">
        <span class="pill soft">누적 시도 ${escapeHtml(totalAttempts)}</span>
        <span class="pill soft">전체 정확도 ${escapeHtml(accuracyText)}</span>
      </div>
    `;
    return;
  }

  const visibleTopics = topics.slice(0, 2);
  const extraCount = Math.max(topics.length - visibleTopics.length, 0);

  elements.weakTopics.innerHTML = `
    <div class="dashboard-inline-note">
      <span class="pill soft">누적 시도 ${escapeHtml(totalAttempts)}</span>
      <span class="pill soft">전체 정확도 ${escapeHtml(accuracyText)}</span>
      ${visibleTopics.map((topic) => `<span class="mode-chip weak">${escapeHtml(topic)}</span>`).join("")}
      ${extraCount ? `<span class="pill soft">+${escapeHtml(extraCount)}개</span>` : ""}
    </div>
  `;
}

function renderRecommendedModes(modes) {
  if (!elements.recommendedModes) return;
  if (!Array.isArray(modes) || modes.length === 0) {
    elements.recommendedModes.innerHTML = "";
    return;
  }
  elements.recommendedModes.innerHTML = modes.slice(0, 3).map((mode) => `
    <a class="mode-chip" href="${escapeAttr(mode.link || "/dashboard.html")}">${escapeHtml(mode.label || mode.mode || "추천")}</a>
  `).join("");
}

function renderWeeklyReportCard(reportCard) {
  if (!elements.weeklyReportCard) return;
  const card = reportCard || {};

  if (!card.available) {
    elements.weeklyReportCard.innerHTML = `
      <div class="report-card-empty">
        <p class="empty">아직 저장된 주간 리포트가 없습니다.</p>
        <button type="button" class="primary" data-report-refresh ${state.isGeneratingReport ? "disabled" : ""}>
          ${state.isGeneratingReport ? "생성 중..." : "주간 리포트 생성"}
        </button>
      </div>
    `;
    if (elements.reportStatus) {
      elements.reportStatus.textContent = state.isGeneratingReport ? "리포트를 생성하는 중입니다." : "";
    }
    return;
  }

  const staleBadge = card.stale ? '<span class="pill soft warn">갱신 권장</span>' : '<span class="pill soft ok">최신</span>';
  elements.weeklyReportCard.innerHTML = `
    <article class="report-card">
      <div class="report-card-head">
        <div>
          <h4>${escapeHtml(card.goal || "주간 학습 리포트")}</h4>
          <p class="report-card-date">생성 시각 ${escapeHtml(formatDate(card.createdAt))}</p>
        </div>
        ${staleBadge}
      </div>
      <p class="report-card-summary">${escapeHtml(card.solutionSummary || "요약 정보가 없습니다.")}</p>
      <div class="report-card-actions">
        <a class="ghost" href="${escapeAttr(card.actionLink || "/profile.html")}">프로필에서 보기</a>
        <button type="button" class="primary" data-report-refresh ${state.isGeneratingReport ? "disabled" : ""}>
          ${state.isGeneratingReport ? "생성 중..." : "리포트 재생성"}
        </button>
      </div>
    </article>
  `;
  if (elements.reportStatus) {
    elements.reportStatus.textContent = card.stale ? "최근 리포트가 7일 이상 지났습니다. 갱신을 권장합니다." : "";
  }
}

function renderNotifications(notifications) {
  if (!elements.notificationList) return;
  if (!Array.isArray(notifications) || notifications.length === 0) {
    elements.notificationList.innerHTML = '<p class="empty">지금 표시할 알림이 없습니다.</p>';
    return;
  }

  elements.notificationList.innerHTML = notifications.map((item) => `
    <article class="notification-card severity-${escapeAttr(item.severity || "info")}">
      <div class="notification-copy">
        <div class="notification-head">
          <h4>${escapeHtml(item.title || "알림")}</h4>
          ${item.count ? `<span class="pill soft">${escapeHtml(item.count)}</span>` : ""}
        </div>
        <p>${escapeHtml(item.description || "")}</p>
      </div>
      <a class="ghost" href="${escapeAttr(item.actionLink || "/dashboard.html")}">${escapeHtml(item.actionLabel || "확인")}</a>
    </article>
  `).join("");
}

async function handleGoalSubmit(event) {
  event.preventDefault();
  if (!elements.goalInput || !elements.goalSubmit) return;

  const nextValue = Number.parseInt(elements.goalInput.value || "0", 10);
  if (!Number.isFinite(nextValue) || nextValue < 1 || nextValue > 70) {
    window.alert("일간 목표는 1 이상 70 이하로 입력해 주세요.");
    return;
  }

  const payload = {
    daily_target_sessions: nextValue,
    focus_modes: Array.isArray(state.home?.focusModes) ? state.home.focusModes : [],
    focus_topics: Array.isArray(state.home?.focusTopics) ? state.home.focusTopics : [],
  };

  elements.goalSubmit.disabled = true;
  try {
    state.goal = await apiRequest("/platform/me/goal", { method: "PUT", body: payload });
    await loadHomeAndGoal();
    renderHome();
  } catch (error) {
    window.alert(error.message || "일간 목표 저장에 실패했습니다.");
  } finally {
    elements.goalSubmit.disabled = false;
  }
}

async function handleWeeklyReportCardClick(event) {
  const button = event.target.closest("[data-report-refresh]");
  if (!button || state.isGeneratingReport) {
    return;
  }
  await generateWeeklyReport();
}

async function generateWeeklyReport() {
  let refreshed = false;
  state.isGeneratingReport = true;
  renderWeeklyReportCard(state.home?.weeklyReportCard || {});
  if (elements.reportStatus) {
    elements.reportStatus.textContent = "최근 학습 데이터를 기준으로 주간 리포트를 생성하는 중입니다.";
  }

  try {
    await apiRequest("/platform/reports/milestone", {
      method: "POST",
      body: { problem_count: 10 },
    });
    await loadHomeAndGoal();
    refreshed = true;
  } catch (error) {
    if (elements.reportStatus) {
      elements.reportStatus.textContent = error.message || "주간 리포트 생성에 실패했습니다.";
    }
  } finally {
    state.isGeneratingReport = false;
    if (refreshed) {
      renderHome();
      if (elements.reportStatus) {
        elements.reportStatus.textContent = "주간 리포트를 갱신했습니다.";
      }
    } else {
      renderWeeklyReportCard(state.home?.weeklyReportCard || {});
    }
  }
}

function seedDefaultFeatures() {
  if (features.length > 0) return;

  registerFeature({
    id: "analysis",
    title: "코드 분석",
    description: "코드를 읽고 흐름, 상태 변화, 의도를 설명해 보세요.",
    icon: "🔍",
    link: "/analysis.html",
  });
  registerFeature({
    id: "code-block",
    title: "코드 블록",
    description: "빈칸을 채우고 정답을 골라 문법을 익혀보세요.",
    icon: "🧩",
    link: "/codeblock.html",
  });
  registerFeature({
    id: "code-arrange",
    title: "코드 배치",
    description: "섞인 코드 블록을 올바른 순서로 재배열해 보세요.",
    icon: "🔀",
    link: "/arrange.html",
  });
  registerFeature({
    id: "auditor",
    title: "감사관 모드",
    description: "치명적 함정을 찾아 자유서술 감사 리포트를 제출하세요.",
    icon: "🕵️",
    link: "/auditor.html",
  });
  registerFeature({
    id: "refactoring-choice",
    title: "최적의 선택",
    description: "A/B/C 구현 중 제약에 맞는 최적안을 선택하고 근거를 작성하세요.",
    icon: "⚖️",
    link: "/refactoring-choice.html",
  });
  registerFeature({
    id: "code-blame",
    title: "범인 찾기",
    description: "서버 에러 로그와 커밋 diff를 비교해 장애 원인 커밋을 추리하세요.",
    icon: "🧯",
    link: "/code-blame.html",
  });
}

function registerFeature(feature) {
  features.push(normalizeFeature(feature, features.length));
}

function applyFeatureBadges(recommendedModes) {
  const recommendedSet = new Set(
    Array.isArray(recommendedModes)
      ? recommendedModes.map((item) => String(item.mode || "").trim().toLowerCase())
      : []
  );
  features.forEach((feature) => {
    feature.badge = recommendedSet.has(feature.id) ? "추천" : "";
  });
}

function renderFeatures() {
  renderFeatureList(elements.featureGrid, features);
}

function renderAdvancedFeatures() {
  renderFeatureList(elements.advancedFeatureGrid, advancedFeatures);
}

function renderFeatureList(container, list) {
  if (!container) return;
  container.innerHTML = "";
  list.forEach((feature) => container.appendChild(buildFeatureCard(feature)));
}

function buildFeatureCard(feature) {
  const card = document.createElement(feature.disabled ? "div" : "a");
  card.className = "feature-card";
  if (!feature.disabled) {
    card.href = feature.link;
  } else {
    card.classList.add("disabled");
    card.setAttribute("aria-disabled", "true");
  }

  if (feature.badge) {
    const badge = document.createElement("span");
    badge.className = "badge soft";
    badge.textContent = feature.badge;
    card.appendChild(badge);
  }

  const icon = document.createElement("div");
  icon.className = "feature-icon";
  icon.textContent = feature.icon;
  icon.setAttribute("aria-hidden", "true");

  const title = document.createElement("h3");
  title.textContent = feature.title;

  const desc = document.createElement("p");
  desc.textContent = feature.description;

  card.appendChild(icon);
  card.appendChild(title);
  card.appendChild(desc);
  return card;
}

function normalizeFeature(feature, index, prefix = "feature") {
  const defaults = {
    id: `${prefix}-${index}`,
    title: "학습 기능",
    description: "",
    icon: "✨",
    link: "#",
    disabled: false,
    badge: "",
  };
  return { ...defaults, ...feature };
}

function renderModePanels() {
  elements.modeTabs?.forEach((button) => {
    const isActive = button.dataset.modeTab === state.activeModeTab;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    button.tabIndex = isActive ? 0 : -1;
  });

  elements.modePanels?.forEach((panel) => {
    const isActive = panel.dataset.modePanel === state.activeModeTab;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });
}

function renderErrorState(error) {
  const message = error?.message || "대시보드를 불러오지 못했습니다.";
  if (elements.heroSummary) {
    elements.heroSummary.textContent = message;
  }
  if (elements.goalHint) {
    elements.goalHint.textContent = "잠시 후 다시 시도해 주세요.";
  }
  if (elements.taskList) {
    elements.taskList.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
  }
  if (elements.reviewList) {
    elements.reviewList.innerHTML = '<p class="empty">잠시 후 다시 시도해 주세요.</p>';
  }
  if (elements.weeklyReportCard) {
    elements.weeklyReportCard.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
  }
  if (elements.notificationList) {
    elements.notificationList.innerHTML = '<p class="empty">알림을 불러오지 못했습니다.</p>';
  }
}

function formatAccuracyText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value = "") {
  return escapeHtml(value);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}



