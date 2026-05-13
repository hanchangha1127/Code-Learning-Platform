import { expect, test } from "@playwright/test";

const SESSION_MARKER = "cookie-session";
const ADMIN_KEY = "test-admin-key-1234567890";

const me = { username: "tester", display_name: "Tester", displayName: "Tester" };
const profile = { username: "tester", displayName: "Tester", totalAttempts: 12, accuracy: 75, skillLevel: "level1" };
const home = {
  displayName: "Tester",
  streakDays: 4,
  stats: { totalAttempts: 12, accuracy: 75 },
  dailyGoal: { targetSessions: 10, completedSessions: 5, remainingSessions: 5 },
  reviewQueue: { dueCount: 1, items: [{ id: 1, title: "Trace the loop", weaknessLabel: "Logic", resumeLink: "/analysis.html?resume_review=1" }] },
  trend: { last7DaysAttempts: 5 },
  weakTopics: ["Logic"],
  recommendedModes: [{ mode: "analysis" }],
  focusModes: ["analysis"],
  focusTopics: ["Logic"],
};
const goal = { dailyTargetSessions: 10, focusModes: ["analysis"], focusTopics: ["Logic"] };
const historyPage = {
  history: [
    {
      problem_id: "missed-1",
      title: "Missed branch condition",
      mode: "analysis",
      correct: false,
      score: 42,
      feedback: { summary: "Revisit the branch condition." },
    },
  ],
  total: 1,
  hasMore: false,
  limit: 50,
};

const analysisProblem = {
  problem: {
    problemId: "analysis-1",
    title: "Trace the accumulator",
    code: "total = 0\nfor value in [1, 2, 3]:\n    total += value\nprint(total)",
    prompt: "Explain the execution order and the final output.",
  },
};
const analysisResult = {
  feedback: { summary: "You tracked the execution flow correctly.", score: 86, correct: true },
  model_answer: "The final output is 6.",
};
const codeBlockProblem = {
  problemId: "cb-1",
  title: "Complete the sum",
  objective: "Add the current number.",
  code: "total = [BLANK]",
  options: ["total + number", "number"],
};
const arrangeProblem = {
  problemId: "arr-1",
  title: "Arrange the loop",
  blocks: [
    { id: "b1", code: "for value in [1, 2, 3]:" },
    { id: "b2", code: "    total += value" },
  ],
};
const auditorProblem = { problemId: "aud-1", title: "Audit payment", code: "def pay(amount):\n    return amount", prompt: "Find risks." };
const refactoringProblem = {
  problemId: "ref-1",
  title: "Pick the best cache strategy",
  scenario: "Choose the option that avoids duplicate work.",
  constraints: ["Keep it testable."],
  options: [{ optionId: "B", title: "Request coalescing", code: "return inflight.get(id)" }],
};
const blameProblem = {
  problemId: "blame-1",
  title: "Find the breaking commit",
  errorLog: "TypeError: user is undefined",
  commits: [{ optionId: "B", title: "Remove guard", diff: "- if (!user) return null;" }],
};
const reportResult = {
  correct: true,
  score: 91,
  verdict: "passed",
  feedback: { summary: "Solid reasoning.", strengths: ["Clear"], improvements: ["Add one detail"] },
  referenceReport: "Reference report.",
  selectedOption: "B",
  bestOption: "B",
  selectedCommits: ["B"],
  culpritCommits: ["B"],
  optionReviews: [{ optionId: "B", summary: "Best option." }],
  commitReviews: [{ optionId: "B", summary: "Introduced the crash." }],
};
const advancedProblem = {
  problemId: "sf-1",
  title: "Checkout flow",
  prompt: "Trace the payment flow.",
  checklist: ["Find the entrypoint."],
  files: [
    { id: "controller", name: "checkout_controller.ts", path: "src/controller.ts", content: "export function checkout() {}" },
    { id: "service", name: "checkout_service.ts", path: "src/service.ts", content: "export class CheckoutService {}" },
  ],
};
const problemBankPage = {
  items: [
    {
      id: 1,
      title: "Bank analysis problem",
      mode: "analysis",
      mode_label: "코드 분석",
      language: "python",
      difficulty: "easy",
      submissions: 12,
      success_rate: 75,
      my_status: "unsolved",
      updated_at: "2026-03-06T09:20:00",
      solve_link: "/analysis.html?bank_problem=1",
    },
    {
      id: 2,
      title: "Bank code block",
      mode: "code-block",
      mode_label: "코드 블록",
      language: "python",
      difficulty: "medium",
      submissions: 8,
      success_rate: 62.5,
      my_status: "tried",
      updated_at: "2026-03-05T09:20:00",
      solve_link: "/codeblock.html?bank_problem=2",
    },
    {
      id: 3,
      title: "Bank arrange",
      mode: "code-arrange",
      mode_label: "코드 배치",
      language: "python",
      difficulty: "easy",
      submissions: 5,
      success_rate: 80,
      my_status: "solved",
      updated_at: "2026-03-04T09:20:00",
      solve_link: "/arrange.html?bank_problem=3",
    },
    {
      id: 4,
      title: "Bank advanced",
      mode: "multi-file-analysis",
      mode_label: "다중 파일 분석",
      language: "typescript",
      difficulty: "hard",
      submissions: 3,
      success_rate: 33.3,
      my_status: "unsolved",
      updated_at: "2026-03-03T09:20:00",
      solve_link: "/multi-file-analysis.html?bank_problem=4",
    },
  ],
  summary: {
    total_problems: 4,
    total_submissions: 28,
    solved_count: 1,
    tried_count: 1,
    average_success_rate: 64.3,
  },
  total: 4,
  limit: 30,
  offset: 0,
};
const adminMetrics = {
  generatedAt: "2026-03-06T09:30:00",
  activeUsers: 3,
  activeClients: 5,
  inFlightRequests: 1,
  requestTotals: { total: 42, errors: 2, errorRate: 4.76 },
  userTimeline: { labels: ["09:28", "09:29", "09:30"], activeUsers: [1, 2, 3], activeClients: [2, 4, 5] },
  requestsTimeline: { labels: ["09:28", "09:29", "09:30"], calls: [8, 10, 12], errors: [0, 1, 1] },
  ai: {
    inFlight: 1,
    totals: { calls: 15, success: 13, failure: 2, successRate: 86.7, avgLatencyMs: 1200 },
    timeline: {
      labels: ["09:28", "09:29", "09:30"],
      calls: [3, 5, 7],
      success: [3, 4, 6],
      failure: [0, 1, 1],
      avgLatencyMs: [900, 1100, 1200],
    },
  },
  platformModes: {
    inFlight: 1,
    modes: {
      analysis: {
        problem: { calls: 4, success: 4, failure: 0, avgLatencyMs: 300 },
        submit: { calls: 3, success: 2, failure: 1, avgLatencyMs: 500 },
        submitBackground: { calls: 1, success: 1, failure: 0, avgLatencyMs: 700 },
        dispatch: { queued: 1, inline: 2, enqueueFailure: 0 },
      },
    },
  },
  admin: {
    shutdown: { supported: true, reason: "ok", requires_socket_override: false },
    contentSummary: {
      totals: 12,
      statusCounts: { pending: 2, approved: 9, hidden: 1 },
      topPromptVersions: [{ version: "v2", count: 8 }],
      recentPendingProblems: [{ id: 1, title: "Pending problem", mode: "analysis", promptVersion: "v2", createdAt: "2026-03-06T09:20:00" }],
    },
    opsEvents: {
      windowHours: 24,
      total: 7,
      statusCounts: { success: 5, failure: 1, review_required: 1 },
      topEventTypes: [{ eventType: "problem_generated", count: 4 }],
      modeSummary: [{ mode: "analysis", total: 4, failure: 1, avgLatencyMs: 360 }],
      latest: [{ eventType: "submit", mode: "analysis", status: "success", requestId: "req-1", createdAt: "2026-03-06T09:28:00" }],
    },
  },
};

async function installMocks(page, { language = "python", difficulty = "beginner", authenticated = true, problemBankResponder = null } = {}) {
  let jobPolls = 0;
  let sessionActive = authenticated;
  await page.addInitScript(({ marker, adminKey, languageId, difficultyId }) => {
    if (marker) {
      window.localStorage.setItem("code-learning-token", marker);
      window.localStorage.setItem("code-learning-display-name", "Tester");
    }
    window.localStorage.setItem("code-learning-language", languageId);
    window.localStorage.setItem("code-learning-difficulty", difficultyId);
    window.sessionStorage.setItem("admin_panel_key", adminKey);
  }, { marker: authenticated ? SESSION_MARKER : "", adminKey: ADMIN_KEY, languageId: language, difficultyId: difficulty });

  await page.route("**/platform/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    switch (url.pathname) {
      case "/platform/profile":
        return sessionActive ? json(profile) : json({ detail: "not authenticated" }, 401);
      case "/platform/me":
        return json(me);
      case "/platform/home":
        return json(home);
      case "/platform/me/goal":
        return json(goal);
      case "/platform/me/settings":
        return json({ preferredLanguage: language, preferredDifficulty: difficulty === "advanced" ? "hard" : "medium" });
      case "/platform/languages":
        return json({ languages: [{ id: "python", title: "Python" }, { id: "javascript", title: "JavaScript" }] });
      case "/platform/learning/history":
        return json(historyPage);
      case "/platform/learning/review-queue":
        return json(home.reviewQueue);
      case "/platform/review-queue/1/resume":
        return json({ reviewItemId: 1, mode: "analysis", resumeLink: "/analysis.html?resume_review=1", problem: analysisProblem.problem });
      case "/platform/problem-bank":
        if (problemBankResponder) return problemBankResponder(route, url, json);
        return json(problemBankPage);
      case "/platform/problem-bank/1/resume":
        return json({ bank_problem_id: 1, mode: "analysis", resume_link: "/analysis.html?bank_problem=1", problem: analysisProblem.problem });
      case "/platform/problem-bank/2/resume":
        return json({ bank_problem_id: 2, mode: "code-block", resume_link: "/codeblock.html?bank_problem=2", problem: codeBlockProblem });
      case "/platform/problem-bank/3/resume":
        return json({ bank_problem_id: 3, mode: "code-arrange", resume_link: "/arrange.html?bank_problem=3", problem: arrangeProblem });
      case "/platform/problem-bank/4/resume":
        return json({ bank_problem_id: 4, mode: "multi-file-analysis", resume_link: "/multi-file-analysis.html?bank_problem=4", problem: advancedProblem });
      case "/platform/auth/guest":
        sessionActive = true;
        return json({ accessToken: SESSION_MARKER, username: "guest" });
      case "/platform/auth/logout":
        sessionActive = false;
        return json({ ok: true });
      case "/platform/reports/latest":
        return json({ available: true, reportId: 1, goal: "Latest report", summary: "Recent learning summary.", createdAt: "2026-03-06", pdfDownloadUrl: "/platform/reports/1/pdf" });
      case "/platform/reports/milestone":
        return json({ reportId: 2, goal: "Milestone report", solutionSummary: "Keep reviewing branches.", priorityActions: ["Review branch conditions"], pdfDownloadUrl: "/platform/reports/2/pdf" });
      case "/platform/analysis/problem":
        return json(analysisProblem);
      case "/platform/analysis/submit":
        return json(analysisResult);
      case "/platform/codeblock/problem":
        return json(codeBlockProblem);
      case "/platform/codeblock/submit":
        return json({ correct: true, explanation: "Add the current number." });
      case "/platform/arrange/problem":
        return json(arrangeProblem);
      case "/platform/arrange/submit":
        return json({ correct: true, answerCode: "for value in [1, 2, 3]:\n    total += value", feedback: { summary: "Good order." } });
      case "/platform/auditor/problem":
        return json(auditorProblem);
      case "/platform/refactoring-choice/problem":
        return json(refactoringProblem);
      case "/platform/code-blame/problem":
        return json(blameProblem);
      case "/platform/auditor/submit":
      case "/platform/refactoring-choice/submit":
      case "/platform/code-blame/submit":
      case "/platform/multi-file-analysis/submit":
        return json({ queued: true, jobId: "job-1" });
      case "/platform/single-file-analysis/problem":
      case "/platform/multi-file-analysis/problem":
      case "/platform/fullstack-analysis/problem":
        return json(advancedProblem);
      case "/platform/single-file-analysis/submit":
      case "/platform/fullstack-analysis/submit":
        return json(reportResult);
      case "/platform/mode-jobs/job-1":
        jobPolls += 1;
        return json(jobPolls > 0 ? { jobId: "job-1", status: "finished", queued: false, finished: true, failed: false, result: reportResult } : { jobId: "job-1", status: "queued", queued: true, finished: false, failed: false });
      default:
        return json({});
    }
  });

  await page.route("**/api/admin/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(route.request().method() === "POST" ? { status: "accepted", detail: "Shutdown has been scheduled." } : adminMetrics),
    });
  });
}

test.describe("React frontend smoke", () => {
  test("login page renders and guest login enters dashboard", async ({ page }) => {
    await installMocks(page, { authenticated: false });
    await page.goto("/index.html");
    await expect(page.locator("#google-login")).toBeVisible();
    await page.locator("#guest-login").click();
    await expect(page).toHaveURL(/dashboard\.html$/);
  });

  test("dashboard and profile render core panels", async ({ page }) => {
    await installMocks(page);
    await page.goto("/dashboard.html");
    await expect(page.locator("#dashboard-section")).toBeVisible();
    await expect(page.locator(".language-trigger")).toContainText("Python");
    await expect(page.locator(".difficulty-tabs .is-active")).toContainText("중급");
    await expect(page.locator("#dashboard-goal-progress")).toContainText("5 / 10");
    await page.locator("#dashboard-mode-tab-advanced").click();
    await expect(page.locator("#dashboard-mode-panel-advanced .feature-card")).toHaveCount(3);
    await page.goto("/profile.html");
    await expect(page.locator("#profile-name")).toContainText("Tester");
    await expect(page.locator("#language-setting")).toHaveCount(0);
    await expect(page.locator("#difficulty-setting")).toHaveCount(0);
    await expect(page.locator("#profile-total-attempts")).toContainText("12");
    await page.locator("#btn-wrong-note").click();
    await expect(page.locator("#modal-title")).toContainText("지금 다시 볼 문제");
    await expect(page.locator("#modal-body")).toContainText("Missed branch condition");
    await page.locator("#modal-close").click();
    await page.locator("#btn-report").click();
    await expect(page.locator("#modal-title")).toContainText("Latest report");
    await expect(page.locator("#latest-report-summary")).toContainText("Recent learning summary.");
    await page.goto("/dashboard.html");
    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/index\.html$/);
    await expect(page.locator("#google-login")).toBeVisible();
  });

  test("profile wrong note review link resumes the selected problem", async ({ page }) => {
    await installMocks(page);
    await page.goto("/profile.html");
    await page.locator("#btn-wrong-note").click();
    await page.locator("#modal-body a.ghost").first().click();
    await expect(page).toHaveURL(/analysis\.html\?resume_review=1$/);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
  });

  test("problem bank lists shared problems and reuses mode pages", async ({ page }) => {
    await installMocks(page);
    await page.goto("/problems.html");
    await expect(page.locator("#problem-bank-table")).toContainText("Bank analysis problem");
    await expect(page.locator("#problem-bank-table")).toContainText("75%");
    await page.locator(".problem-bank-title-link").first().click();
    await expect(page).toHaveURL(/analysis\.html\?bank_problem=1$/);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");

    await page.goto("/codeblock.html?bank_problem=2");
    await expect(page.locator("#cb-problem-title")).toContainText("Complete the sum");

    await page.goto("/arrange.html?bank_problem=3");
    await expect(page.locator("#arr-title")).toContainText("Arrange the loop");

    await page.goto("/multi-file-analysis.html?bank_problem=4");
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_controller.ts");
  });

  test("problem bank ignores stale filter responses", async ({ page }) => {
    const seenQueries = [];
    const fastPage = {
      ...problemBankPage,
      items: [{ ...problemBankPage.items[0], id: 21, title: "Fast filter result", solve_link: "" }],
      total: 1,
      summary: { ...problemBankPage.summary, total_problems: 1 },
    };
    const slowPage = {
      ...problemBankPage,
      items: [{ ...problemBankPage.items[0], id: 22, title: "Slow stale result", solve_link: "" }],
      total: 1,
      summary: { ...problemBankPage.summary, total_problems: 1 },
    };

    await installMocks(page, {
      problemBankResponder: async (_route, url, json) => {
        const query = url.searchParams.get("q") || "";
        seenQueries.push(query);
        if (query === "slow") {
          await new Promise((resolve) => setTimeout(resolve, 500));
          return json(slowPage);
        }
        if (query === "fast") return json(fastPage);
        return json(problemBankPage);
      },
    });
    await page.goto("/problems.html");
    await expect(page.locator("#problem-bank-table")).toContainText("Bank analysis problem");

    await page.locator("#problem-bank-search").fill("slow");
    await expect.poll(() => seenQueries.includes("slow")).toBeTruthy();
    await page.locator("#problem-bank-search").fill("fast");

    await expect(page.locator("#problem-bank-table")).toContainText("Fast filter result");
    await expect(page.locator("#problem-bank-table")).not.toContainText("Slow stale result");
    await expect(page.locator(".problem-bank-title-link").first()).toHaveAttribute("href", /analysis\.html\?bank_problem=21$/);
  });

  test("analysis mode loads and submits", async ({ page }) => {
    await installMocks(page);
    await page.goto("/analysis.html");
    await expect(page.locator("#selected-language")).toHaveCount(0);
    await expect(page.locator("#selected-difficulty")).toHaveCount(0);
    await page.locator("#btn-load-problem").click();
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await page.locator("#answer-text").fill("It prints 6.");
    await page.locator("#answer-form button[type='submit']").click();
    await expect(page.locator("#feedback-summary")).toContainText("tracked");
  });

  test("code block and arrange modes complete", async ({ page }) => {
    await installMocks(page);
    await page.goto("/codeblock.html");
    await page.locator("#cb-load-btn").click();
    await expect(page.locator("#cb-code-display .blank-tile")).toHaveCount(1);
    await page.locator("#cb-options-container button").first().click();
    await expect(page.locator("#cb-result-message")).toContainText("정답");
    await page.goto("/arrange.html");
    await expect(page.locator(".app-header h1")).toContainText("코드 배치");
    await page.locator("#arr-load-btn").click();
    await expect(page.locator("#arr-problem-prompt")).toContainText("드래그 앤 드롭");
    await expect(page.locator("#arr-blocks .arrange-block").first()).toHaveAttribute("draggable", "true");
    await page.locator("#arr-check-btn").click();
    await expect(page.locator("#arr-answer-code")).toContainText("total");
  });

  test("report modes handle queued submit results", async ({ page }) => {
    await installMocks(page);
    for (const scenario of [
      { path: "/auditor.html", load: "#auditor-load-btn", text: "#auditor-report-text", submit: "#auditor-submit-btn", score: "#auditor-score" },
      { path: "/refactoring-choice.html", load: "#rc-load-btn", text: "#rc-report-text", submit: "#rc-submit-btn", score: "#rc-score", option: 'input[name="selected-option"]' },
      { path: "/code-blame.html", load: "#cb-load-btn", text: "#cb-report-text", submit: "#cb-submit-btn", score: "#cb-score", option: 'input[name="selected-commit"]' },
    ]) {
      await page.goto(scenario.path);
      await page.locator(scenario.load).click();
      if (scenario.option) await page.locator(scenario.option).first().check();
      await page.locator(scenario.text).fill("Reasoned report.");
      await page.locator(scenario.submit).click();
      await expect(page.locator(scenario.score)).toContainText("91");
    }
  });

  test("advanced analysis loads files and submits", async ({ page }) => {
    await installMocks(page);
    await page.goto("/multi-file-analysis.html");
    await expect(page.locator("#advanced-selected-language")).toHaveCount(0);
    await expect(page.locator("#advanced-selected-difficulty")).toHaveCount(0);
    await page.locator("#advanced-load-btn").click();
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_controller.ts");
    await page.locator('[data-advanced-file-id="service"]').first().click();
    await expect(page.locator("#advanced-code-view")).toContainText("CheckoutService");
    await page.locator("#advanced-report-text").fill("Trace the flow.");
    await page.locator("#advanced-submit-btn").click();
    await expect(page.locator("#advanced-result-score")).toContainText("91");
  });

  test("mobile route and admin render", async ({ page }) => {
    await installMocks(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard.html");
    await expect(page.locator("body")).toHaveAttribute("data-react-frontend", "true");
    await page.goto("/admin.html");
    await expect(page.locator(".admin-shell")).toBeVisible();
    await expect(page.locator("#active-users")).toContainText("3");
    await expect(page.locator("#ai-success-rate")).toContainText("86.7%");
    await expect(page.locator("#users-chart")).toBeVisible();
    await expect(page.locator("#ai-usage-chart")).toBeVisible();
    await expect(page.locator("#ai-latency-chart")).toBeVisible();
    await expect(page.locator("#request-chart")).toBeVisible();
    await expect(page.locator("#content-summary-panel")).toBeVisible();
    await expect(page.locator("#content-summary-panel")).toContainText("Pending problem");
    await expect(page.locator("#ops-events-panel")).toContainText("problem_generated");
    await expect(page.locator(".admin-platform-panel")).toContainText("코드 분석");
  });
});
