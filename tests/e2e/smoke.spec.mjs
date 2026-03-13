import { expect, test } from "@playwright/test";

const SESSION_MARKER = "cookie-session";
const ADMIN_KEY = "test-admin-key-1234567890";

const languagePayload = {
  languages: [
    { id: "python", title: "Python" },
    { id: "javascript", title: "JavaScript" },
  ],
};

const profilePayload = {
  username: "tester",
  displayName: "Tester",
  display_name: "Tester",
  skillLevel: "beginner",
  totalAttempts: 3,
  accuracy: 67,
  diagnosticRemaining: 0,
  diagnosticAnswered: 3,
  diagnosticTotal: 3,
};

const adminMetricsPayload = {
  activeUsers: 1,
  activeClients: 1,
  inFlightRequests: 0,
  generatedAt: "2026-03-06T10:00:00+09:00",
  userTimeline: { labels: ["10:00"], activeUsers: [1], activeClients: [1] },
  requestsTimeline: { labels: ["10:00"], calls: [4], errors: [0] },
  ai: {
    inFlight: 0,
    totals: { calls: 4, successRate: 100, avgLatencyMs: 120 },
    timeline: {
      labels: ["10:00"],
      calls: [4],
      success: [4],
      failure: [0],
      avgLatencyMs: [120],
    },
  },
  admin: {
    shutdown: {
      supported: true,
      reason: "ok",
      requires_socket_override: false,
      detail: "Docker control is available.",
    },
    contentSummary: {
      totals: 12,
      statusCounts: { pending: 3, approved: 8, hidden: 1 },
      topPromptVersions: [{ version: "analysis-v2", count: 5 }],
      recentPendingProblems: [{ id: 9, title: "Trace loop", mode: "analysis", promptVersion: "analysis-v2", createdAt: "2026-03-06T10:00:00" }],
    },
    opsEvents: {
      windowHours: 24,
      total: 7,
      statusCounts: { success: 4, failure: 2, review_required: 1 },
      topEventTypes: [{ eventType: "problem_requested", count: 3 }],
      modeSummary: [{ mode: "analysis", total: 4, failure: 1, avgLatencyMs: 132.4 }],
      latest: [{ id: 1, eventType: "submission_processed", mode: "analysis", status: "success", latencyMs: 120, requestId: "req-1", createdAt: "2026-03-06T10:00:00" }],
    },
  },
};

const homePayload = {
  displayName: "Tester",
  todayDate: "2026-03-06",
  streakDays: 4,
  skillLevel: "beginner",
  dailyGoal: {
    date: "2026-03-06",
    targetSessions: 10,
    completedSessions: 5,
    remainingSessions: 5,
    progressPercent: 50,
    achieved: false,
  },
  reviewQueue: {
    dueCount: 1,
    items: [
      {
        id: 1,
        mode: "analysis",
        modeLabel: "Code Analysis",
        title: "Trace the loop",
        weaknessTag: "logic_error",
        weaknessLabel: "Logic",
        dueAt: "2026-03-06T10:00:00",
        priority: 80,
        actionLink: "/analysis.html",
        resumeLink: "/analysis.html?resume_review=1",
        sourceProblemId: "an-1",
      },
    ],
  },
  todayTasks: [
    {
      type: "review",
      title: "Review one wrong answer",
      description: "Retry the latest wrong answer.",
      actionLabel: "Start",
      actionLink: "/analysis.html",
    },
  ],
  weakTopics: ["Logic", "Runtime"],
  recommendedModes: [
    { mode: "analysis", label: "Code Analysis", link: "/analysis.html" },
    { mode: "code-calc", label: "Code Calc", link: "/codecalc.html" },
  ],
  trend: {
    last7DaysAttempts: 5,
    last30DaysAttempts: 12,
    last7DaysAccuracy: 60,
    last30DaysAccuracy: 75,
  },
  stats: { totalAttempts: 12, accuracy: 75 },
  focusModes: ["analysis"],
  focusTopics: ["Logic"],
  weeklyReportCard: {
    available: true,
    reportId: 1,
    createdAt: "2026-03-06T10:00:00+09:00",
    goal: "Keep the weekly review cadence",
    solutionSummary: "Review wrong answers first and maintain a daily routine.",
    actionLink: "/profile.html",
    stale: false,
  },
  notifications: [
    {
      type: "review_queue",
      severity: "warn",
      title: "You have review work waiting",
      description: "Retry the same problem from the review queue.",
      actionLabel: "Resume review",
      actionLink: "/analysis.html?resume_review=1",
      count: 1,
    },
  ],
};

const goalPayload = {
  dailyTargetSessions: 10,
  focusModes: ["analysis"],
  focusTopics: ["Logic"],
  updatedAt: "2026-03-06T09:00:00",
};

const userPageSmokeTargets = [
  {
    path: "/dashboard.html",
    ready: "#feature-grid",
    extra: [
      "#dashboard-weekly-report-card",
      "#dashboard-notification-list",
      '#dashboard-goal-presets button[data-goal="10"]',
      '#dashboard-goal-presets button[data-goal="20"]',
      '#dashboard-goal-presets button[data-goal="30"]',
    ],
  },
  { path: "/profile.html", ready: "#profile-section" },
  { path: "/analysis.html", ready: "#app-section" },
  { path: "/codeblock.html", ready: "#code-block-section" },
  { path: "/arrange.html", ready: "#arrange-section" },
  { path: "/codecalc.html", ready: "#code-calc-section" },
  { path: "/codeerror.html", ready: "#code-error-section" },
  { path: "/auditor.html", ready: "#auditor-section" },
  { path: "/context-inference.html", ready: "#context-inference-section" },
  { path: "/refactoring-choice.html", ready: "#refactoring-choice-section" },
  { path: "/code-blame.html", ready: "#code-blame-section" },
];

const adminPageTarget = {
  path: "/admin.html",
  ready: ".admin-shell",
  extra: ["#content-summary-panel", "#ops-events-panel"],
};

async function installShellMocks(page) {
  await page.addInitScript(({ marker, adminKey }) => {
    window.localStorage.setItem("code-learning-token", marker);
    window.localStorage.setItem("code-learning-display-name", "Tester");
    window.localStorage.setItem("code-learning-language", "python");
    window.localStorage.setItem("code-learning-difficulty", "beginner");
    window.sessionStorage.setItem("admin_panel_key", adminKey);
  }, { marker: SESSION_MARKER, adminKey: ADMIN_KEY });

  await page.route("https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `window.Chart = class Chart { constructor(element, config) { this.element = element; this.config = config; this.data = config?.data || { labels: [], datasets: [] }; } update() {} destroy() {} };`,
    });
  });

  await page.route("**/platform/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    switch (url.pathname) {
      case "/platform/profile":
        return json(profilePayload);
      case "/platform/me":
        return json({ username: profilePayload.username, displayName: profilePayload.displayName, display_name: profilePayload.display_name });
      case "/platform/me/goal":
        return json(goalPayload);
      case "/platform/home":
        return json(homePayload);
      case "/platform/languages":
        return json(languagePayload);
      case "/platform/learning/history":
        return json({ history: [] });
      case "/platform/learning/review-queue":
        return json(homePayload.reviewQueue);
      case "/platform/report":
        return json({
          reportId: 1,
          createdAt: "2026-03-06T10:00:00+09:00",
          goal: "Weekly routine",
          solutionSummary: "Review wrong answers and keep a daily cadence.",
          priorityActions: ["Review wrong answers"],
          phasePlan: ["Phase 1"],
          dailyHabits: ["Solve two problems"],
          focusTopics: ["Data structures"],
          metricsToTrack: ["Accuracy"],
          checkpoints: ["Weekend check"],
          riskMitigation: ["Time blocking"],
          metricSnapshot: { attempts: 3, accuracy: 67, avgScore: 72, trend: "stable" },
        });
      default:
        return json({});
    }
  });

  await page.route("**/api/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    switch (url.pathname) {
      case "/api/admin/metrics":
        return json(adminMetricsPayload);
      case "/api/admin/shutdown":
        return json({ ok: true, accepted: true });
      default:
        return json({});
    }
  });
}

test.describe("desktop UA", () => {
  test.use({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    viewport: { width: 1440, height: 960 },
  });

  test("login page renders", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#google-login")).toBeVisible();
    await expect(page.locator("body")).toHaveAttribute("data-template-variant", "desktop");
  });

  test("login shell stays centered with balanced columns", async ({ page }) => {
    await page.goto("/index.html");
    const shellBox = await page.locator(".auth-shell").boundingBox();
    const heroBox = await page.locator(".auth-hero-card").boundingBox();
    const panelBox = await page.locator(".auth-panel").boundingBox();
    expect(shellBox).not.toBeNull();
    expect(heroBox).not.toBeNull();
    expect(panelBox).not.toBeNull();
    const viewportWidth = page.viewportSize().width;
    const shellCenter = shellBox.x + shellBox.width / 2;
    expect(Math.abs(shellCenter - viewportWidth / 2)).toBeLessThan(24);
    expect(panelBox.width).toBeGreaterThan(500);
    expect(Math.abs(heroBox.height - panelBox.height)).toBeLessThan(40);
  });

  for (const target of userPageSmokeTargets) {
    test(`${target.path} renders desktop shell`, async ({ page }) => {
      await installShellMocks(page);
      await page.goto(target.path);
      await expect(page.locator(target.ready)).toBeVisible();
      await expect(page.locator("body")).toHaveAttribute("data-template-variant", "desktop");
      for (const selector of target.extra || []) {
        await expect(page.locator(selector)).toBeVisible();
      }
    });
  }

  test("dashboard keeps a single profile action", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/dashboard.html");
    await expect(page.locator(".app-header a[href=\"/profile.html\"]")).toHaveCount(0);
    await expect(page.locator(".dashboard-action-stack a[href=\"/profile.html\"]")).toHaveCount(1);
  });

  test("analysis settings panel is not sticky", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/analysis.html");
    const position = await page.locator(".control-panel").evaluate((el) => getComputedStyle(el).position);
    expect(position).not.toBe("sticky");
  });

  test("codeblock desktop settings panel stays wide enough", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    const width = await page.locator(".cb-controls").evaluate((el) => el.getBoundingClientRect().width);
    expect(width).toBeGreaterThan(360);
  });
});

test.describe("mobile UA", () => {
  test.use({
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    viewport: { width: 390, height: 844 },
  });

  test("login page renders", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#google-login")).toBeVisible();
    await expect(page.locator("body")).toHaveAttribute("data-template-variant", "mobile");
  });

  for (const target of userPageSmokeTargets) {
    test(`${target.path} renders mobile shell`, async ({ page }) => {
      await installShellMocks(page);
      await page.goto(target.path);
      await expect(page.locator(target.ready)).toBeVisible();
      await expect(page.locator("body")).toHaveAttribute("data-template-variant", "mobile");
      for (const selector of target.extra || []) {
        await expect(page.locator(selector)).toBeVisible();
      }
    });
  }

  test("dashboard keeps a single profile action", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/dashboard.html");
    await expect(page.locator(".app-header a[href=\"/profile.html\"]")).toHaveCount(0);
    await expect(page.locator(".dashboard-action-stack a[href=\"/profile.html\"]")).toHaveCount(1);
  });

  async function expectTopBefore(page, firstSelector, secondSelector) {
    const firstBox = await page.locator(firstSelector).boundingBox();
    const secondBox = await page.locator(secondSelector).boundingBox();
    expect(firstBox).not.toBeNull();
    expect(secondBox).not.toBeNull();
    expect(firstBox.y).toBeLessThan(secondBox.y);
  }

  test("analysis places settings before the problem board", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/analysis.html");
    await expectTopBefore(page, ".mobile-mode-shell > .control-panel", ".mobile-mode-shell > .quiz-panel");
    await expectTopBefore(page, ".mobile-mode-shell > .quiz-panel", ".mobile-mode-shell > .feedback-panel");
  });

  test("codecalc places settings before the problem board", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codecalc.html");
    await expectTopBefore(page, ".mobile-mode-shell > .calc-controls", ".mobile-mode-shell > .calc-board");
  });

  test("codeblock places settings before the problem board", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    await expectTopBefore(page, ".mobile-mode-shell > .cb-controls", ".mobile-mode-shell > .cb-board");
  });

  test("codeblock settings panel uses the full mobile width", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    const shellBox = await page.locator(".mobile-mode-shell").boundingBox();
    const controlsBox = await page.locator(".mobile-mode-shell > .cb-controls").boundingBox();
    expect(shellBox).not.toBeNull();
    expect(controlsBox).not.toBeNull();
    expect(Math.abs(shellBox.width - controlsBox.width)).toBeLessThan(8);
  });

  test("auditor places settings before problem and feedback last", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/auditor.html");
    await expectTopBefore(page, ".mobile-mode-shell > .control-panel", ".mobile-mode-shell > .quiz-panel");
    await expectTopBefore(page, ".mobile-mode-shell > .quiz-panel", ".mobile-mode-shell > .feedback-panel");
  });
});

test("admin page renders", async ({ page }) => {
  await installShellMocks(page);
  await page.goto(adminPageTarget.path);
  await expect(page.locator(adminPageTarget.ready)).toBeVisible();
  await expect(page.locator("body")).toHaveAttribute("data-template-variant", "responsive");
  for (const selector of adminPageTarget.extra || []) {
    await expect(page.locator(selector)).toBeVisible();
  }
});
