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
  skillLevel: "level1",
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
      recentPendingProblems: [
        { id: 9, title: "Trace loop", mode: "analysis", promptVersion: "analysis-v2", createdAt: "2026-03-06T10:00:00" },
      ],
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
  skillLevel: "level1",
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

function toBackendDifficulty(value) {
  if (value === "advanced") return "hard";
  if (value === "intermediate") return "medium";
  return "easy";
}

const codeBlockProblemPayload = {
  problemId: "cb-1",
  title: "짝수 합계 누적",
  objective: "짝수 값만 더해 총합을 계산하는 반복문을 완성하세요.",
  code: `numbers = [1, 2, 3, 4]
total = 0
for number in numbers:
    if number % 2 == 0:
        total = [BLANK]
print(total)`,
  options: ["total + number", "total - number", "number"],
  difficulty: "beginner",
  language: "python",
};

const codeBlockSubmitPayload = {
  correct: true,
  correctAnswer: 0,
  explanation: "The blank must add the current even number to total.",
};

const analysisProblemPayload = {
  problem: {
    id: "analysis-1",
    problemId: "analysis-1",
    title: "Trace the accumulator",
    code: `total = 0
for value in [1, 2, 3]:
    total += value
print(total)`,
    prompt: "Explain the execution order and the final output.",
    mode: "analysis",
    difficulty: "beginner",
    track: "algorithms",
    language: "python",
  },
  mode: "analysis",
  skillLevel: "level1",
  selectedDifficulty: "초급",
};

const analysisSubmitPayload = {
  feedback: {
    summary: "You tracked the execution flow correctly.",
    strengths: ["The accumulator updates are explained in order."],
    improvements: ["Mention the final printed value explicitly."],
    score: 86,
    correct: true,
  },
  model_answer: "The loop adds 1, 2, and 3, so the final output is 6.",
  skillLevel: "level1",
};

const codeArrangeProblemPayload = {
  problemId: "arr-1",
  title: "Arrange the loop",
  language: "python",
  blocks: [
    { id: "b2", code: "    total += value" },
    { id: "b1", code: "for value in [1, 2, 3]:" },
    { id: "b3", code: "print(total)" },
    { id: "b0", code: "total = 0" },
  ],
};

const codeArrangeSubmitPayload = {
  correct: false,
  results: [
    { id: "b2", correct: false },
    { id: "b1", correct: false },
    { id: "b3", correct: false },
    { id: "b0", correct: false },
  ],
  answerOrder: ["b0", "b1", "b2", "b3"],
  answerCode: `total = 0
for value in [1, 2, 3]:
    total += value
print(total)`,
};

const refactoringChoiceProblemPayload = {
  problemId: "ref-1",
  title: "Pick the best cache strategy",
  language: "javascript",
  difficulty: "intermediate",
  scenario: "Choose the option that removes duplicate fetches without making invalidation brittle.",
  constraints: ["Avoid duplicate network calls.", "Keep the code easy to test."],
  decisionFacets: ["performance", "maintainability"],
  prompt: "Pick A, B, or C and justify the trade-off.",
  options: [
    {
      optionId: "A",
      title: "Inline cache",
      code: `const cache = new Map();
export async function loadUser(id) {
  if (cache.has(id)) return cache.get(id);
  const user = await api.getUser(id);
  cache.set(id, user);
  return user;
}`,
    },
    {
      optionId: "B",
      title: "Request coalescing",
      code: `const inflight = new Map();
export async function loadUser(id) {
  if (!inflight.has(id)) {
    inflight.set(id, api.getUser(id).finally(() => inflight.delete(id)));
  }
  return inflight.get(id);
}`,
    },
    {
      optionId: "C",
      title: "Always refetch",
      code: `export async function loadUser(id) {
  return api.getUser(id);
}`,
    },
  ],
};

const queuedRefactoringChoiceSubmitResult = {
  correct: true,
  score: 92,
  verdict: "passed",
  feedback: {
    summary: "You balanced duplicate-call prevention with maintainability.",
    strengths: ["You identified why request coalescing reduces redundant work."],
    improvements: ["Call out cache invalidation trade-offs a bit more directly."],
  },
  foundTypes: ["performance", "maintainability"],
  missedTypes: [],
  referenceReport: "Use request coalescing to deduplicate concurrent fetches without long-lived stale cache entries.",
  passThreshold: 70,
  selectedOption: "B",
  bestOption: "B",
  optionReviews: [
    { optionId: "A", summary: "Works, but invalidation grows brittle." },
    { optionId: "B", summary: "Best balance of concurrency control and readability." },
    { optionId: "C", summary: "Simple, but it keeps duplicate requests." },
  ],
};

const codeBlameProblemPayload = {
  problemId: "blame-1",
  title: "Find the breaking commit",
  language: "javascript",
  difficulty: "intermediate",
  errorLog: "TypeError: Cannot read properties of undefined (reading 'id')",
  commits: [
    {
      optionId: "A",
      title: "Rename payload field",
      diff: `- const userId = user.id;
+ const userId = account.id;`,
    },
    {
      optionId: "B",
      title: "Remove null guard",
      diff: `- if (!user) return null;
+ const userId = user.id;`,
    },
    {
      optionId: "C",
      title: "Change logging format",
      diff: `- logger.info(user.id);
+ logger.info({ userId: user?.id });`,
    },
  ],
  prompt: "Pick the commit that introduced the crash and explain why.",
};

const queuedCodeBlameSubmitResult = {
  correct: true,
  score: 89,
  verdict: "passed",
  feedback: {
    summary: "You linked the crash to the removed guard and the now-reachable property access.",
    strengths: ["The diff-to-error connection is explicit."],
    improvements: ["Describe the recovery or rollback path in one more sentence."],
  },
  foundTypes: ["root_cause_diff"],
  missedTypes: ["failure_mechanism"],
  referenceReport: "Commit B removed the null guard and made the undefined access reachable.",
  passThreshold: 70,
  selectedCommits: ["B"],
  culpritCommits: ["B"],
  commitReviews: [
    { optionId: "A", summary: "Touches naming, but does not explain the crash." },
    { optionId: "B", summary: "Removes the guard and directly enables the failure." },
    { optionId: "C", summary: "Only changes logging output." },
  ],
};

const singleFileAnalysisPayload = {
  problemId: "sf-1",
  title: "결제 마감 로직 분석",
  summary: "할인 적용과 세금 계산 순서를 추적해야 하는 단일 파일 문제입니다.",
  language: "python",
  difficulty: "beginner",
  workspace: "single-file-analysis.workspace",
  prompt: "이 파일을 읽고 총액 계산 흐름, 예외 조건, 테스트가 필요한 경계를 설명하세요.",
  checklist: [
    "핵심 진입 함수와 반환 값을 추적하세요.",
    "상태 변경과 예외 처리 분기를 정리하세요.",
    "테스트가 필요한 경계 조건을 요약하세요.",
  ],
  files: [
    {
      id: "billing-service",
      name: "billing_service.py",
      path: "app/services/billing_service.py",
      language: "python",
      role: "entrypoint",
      content: `class BillingService:
    def finalize_invoice(self, invoice, discounts):
        subtotal = invoice.subtotal()
        applied = []

        for discount in discounts:
            if discount.is_available_for(invoice):
                subtotal = discount.apply(subtotal)
                applied.append(discount.code)

        if subtotal < 0:
            raise ValueError("subtotal must not be negative")

        tax = self._tax_policy.calculate(invoice.region, subtotal)
        total = subtotal + tax

        return {
            "invoice_id": invoice.id,
            "total": total,
            "applied_discounts": applied,
            "tax": tax,
        }
`,
    },
  ],
};

const multiFileAnalysisPayload = {
  problemId: "mf-1",
  title: "체크아웃 호출 흐름 분석",
  summary: "컨트롤러, 서비스, 리포지토리, 노티파이어 사이의 책임 분리를 읽어야 하는 문제입니다.",
  language: "python",
  difficulty: "beginner",
  workspace: "multi-file-analysis.workspace",
  prompt: "파일 간 호출 순서와 각 계층의 책임 분리를 설명하고, 결합이 강한 지점을 짚어보세요.",
  checklist: [
    "진입점에서 실제 비즈니스 로직까지 호출 순서를 정리하세요.",
    "파일별 책임과 결합 지점을 분리해서 설명하세요.",
    "중복 책임이나 테스트 취약 구간을 찾으세요.",
  ],
  files: [
    {
      id: "checkout-controller",
      name: "checkout_controller.ts",
      path: "src/controllers/checkout_controller.ts",
      language: "typescript",
      role: "controller",
      content: `export async function createCheckout(req, res) {
  const command = mapCheckoutCommand(req.body);
  const result = await checkoutService.execute(command);
  return res.status(201).json(result);
}
`,
    },
    {
      id: "checkout-service",
      name: "checkout_service.ts",
      path: "src/services/checkout_service.ts",
      language: "typescript",
      role: "service",
      content: `export class CheckoutService {
  constructor(orderRepo, paymentGateway, notifier) {
    this.orderRepo = orderRepo;
    this.paymentGateway = paymentGateway;
    this.notifier = notifier;
  }

  async execute(command) {
    const order = await this.orderRepo.load(command.orderId);
    order.assertReady();

    const payment = await this.paymentGateway.authorize({
      orderId: order.id,
      amount: order.total,
    });

    order.markPaid(payment.transactionId);
    await this.orderRepo.save(order);
    await this.notifier.sendReceipt(order.customerEmail, order.summary());

    return order.summary();
  }
}
`,
    },
    {
      id: "order-repository",
      name: "order_repository.ts",
      path: "src/repositories/order_repository.ts",
      language: "typescript",
      role: "repository",
      content: `export class OrderRepository {
  async load(orderId) {
    return Order.fromRecord(await db.orders.findById(orderId));
  }

  async save(order) {
    await db.orders.update(order.id, order.toRecord());
  }
}
`,
    },
    {
      id: "receipt-notifier",
      name: "receipt_notifier.ts",
      path: "src/notifications/receipt_notifier.ts",
      language: "typescript",
      role: "helper",
      content: `export class ReceiptNotifier {
  async sendReceipt(email, summary) {
    await mailer.send({
      to: email,
      template: "checkout-complete",
      variables: summary,
    });
  }
}
`,
    },
  ],
};

const fullstackAnalysisPayload = {
  problemId: "fs-1",
  title: "체크아웃 사용자 흐름 분석",
  summary: "프런트 이벤트에서 API 호출, 서버 처리, 화면 반영까지 전체 흐름을 추적해야 하는 문제입니다.",
  language: "python",
  difficulty: "beginner",
  workspace: "fullstack-analysis.workspace",
  prompt: "사용자 액션부터 API 응답과 UI 갱신까지 어떤 흐름으로 이어지는지 설명하세요.",
  checklist: [
    "사용자 액션이 어디서 시작되는지 확인하세요.",
    "API 호출과 서버 진입점을 연결해서 설명하세요.",
    "응답이 상태와 UI에 어떻게 반영되는지 추적하세요.",
    "장애가 생길 수 있는 경계와 복구 포인트를 정리하세요.",
  ],
  files: [
    {
      id: "checkout-page",
      name: "CheckoutPage.tsx",
      path: "frontend/pages/CheckoutPage.tsx",
      language: "tsx",
      role: "frontend",
      content: `export function CheckoutPage() {
  const { submitCheckout, loading, summary } = useCheckout();

  return (
    <CheckoutLayout
      onSubmit={submitCheckout}
      loading={loading}
      summary={summary}
    />
  );
}
`,
    },
    {
      id: "use-checkout",
      name: "useCheckout.ts",
      path: "frontend/hooks/useCheckout.ts",
      language: "typescript",
      role: "frontend",
      content: `export function useCheckout() {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(null);

  async function submitCheckout(payload) {
    setLoading(true);
    const response = await api.post("/api/checkout", payload);
    setSummary(response.data);
    setLoading(false);
  }

  return { loading, summary, submitCheckout };
}
`,
    },
    {
      id: "checkout-route",
      name: "checkout.py",
      path: "backend/routes/checkout.py",
      language: "python",
      role: "backend",
      content: `@router.post("/api/checkout")
def create_checkout(payload: CheckoutPayload):
    result = checkout_service.process(payload)
    return {
        "orderId": result.order_id,
        "status": result.status,
        "total": result.total,
    }
`,
    },
    {
      id: "checkout-service",
      name: "checkout_service.py",
      path: "backend/services/checkout_service.py",
      language: "python",
      role: "backend",
      content: `class CheckoutService:
    def process(self, payload):
        cart = self.cart_repo.load(payload.cart_id)
        order = self.order_factory.from_cart(cart)
        payment = self.payment_gateway.charge(order.total)
        order.mark_paid(payment.transaction_id)
        self.order_repo.save(order)
        return order
`,
    },
  ],
};

const singleFileAnalysisSubmitPayload = {
  correct: true,
  score: 84,
  verdict: "passed",
  feedback: {
    summary: "핵심 제어 흐름과 상태 변화를 잘 정리했습니다.",
    strengths: ["진입 함수와 반환 흐름을 명확히 설명했습니다."],
    improvements: ["예외 조건과 경계 사례를 조금 더 구체적으로 적어 보세요."],
  },
  referenceReport: "모범 단일 파일 리포트",
  passThreshold: 70,
};

const fullstackAnalysisSubmitPayload = {
  correct: false,
  score: 62,
  verdict: "failed",
  feedback: {
    summary: "전체 흐름은 짚었지만 프런트엔드와 백엔드 연결 설명이 부족합니다.",
    strengths: ["사용자 액션의 시작 지점을 설명했습니다."],
    improvements: ["API 응답 이후 UI 상태 반영 흐름을 더 자세히 적어 보세요."],
  },
  referenceReport: "모범 풀스택 리포트",
  passThreshold: 70,
};

const queuedMultiFileAnalysisSubmitResult = {
  correct: true,
  score: 88,
  verdict: "passed",
  feedback: {
    summary: "파일 간 호출 흐름과 책임 분리를 구조적으로 설명했습니다.",
    strengths: ["서비스와 저장소 계층의 역할을 구분했습니다."],
    improvements: ["알림 전송 시점의 부수 효과를 조금 더 설명해 보세요."],
  },
  referenceReport: "모범 다중 파일 리포트",
  passThreshold: 70,
};

const auditorProblemPayload = {
  problemId: "aud-1",
  title: "결제 검증 로직 감사",
  language: "python",
  difficulty: "beginner",
  code: `def validate_payment(user, amount, cache, db):
    if cache.get(user.id):
        return True
    if amount < 0:
        return True
    db.record_attempt(user.id, amount)
    return amount <= user.credit_limit
`,
  prompt: "숨겨진 함정과 영향 범위를 감사 리포트로 작성해 주세요.",
  trapCount: 3,
};

const queuedAuditorSubmitResult = {
  correct: true,
  score: 91,
  verdict: "passed",
  feedback: {
    summary: "입력 검증 누락과 캐시 우회 위험을 핵심 근거와 함께 잘 짚었습니다.",
    strengths: ["음수 금액 처리 버그와 감사 로그 흐름을 함께 설명했습니다."],
    improvements: ["재현 조건을 한 단계 더 구체화하면 더 좋습니다."],
  },
  foundTypes: ["validation", "cache"],
  missedTypes: ["logging"],
  referenceReport: "모범 감사 리포트",
  passThreshold: 70,
};

const userPageSmokeTargets = [
  {
    path: "/dashboard.html",
    ready: "#feature-grid",
    extra: [
      "#dashboard-mode-tabs",
      "#dashboard-mode-tab-general",
      "#dashboard-mode-tab-advanced",
      "#dashboard-hero-title",
      "#dashboard-goal-form",
      "#dashboard-review-list",
      '#dashboard-goal-presets button[data-goal="10"]',
      '#dashboard-goal-presets button[data-goal="20"]',
      '#dashboard-goal-presets button[data-goal="30"]',
    ],
  },
  {
    path: "/profile.html",
    ready: "#profile-section",
    extra: ["#language-setting-select", "#profile-total-attempts", "#profile-goal-progress"],
  },
  { path: "/analysis.html", ready: "#app-section" },
  { path: "/codeblock.html", ready: "#code-block-section" },
  { path: "/arrange.html", ready: "#arrange-section" },
  { path: "/auditor.html", ready: "#auditor-section" },
  { path: "/refactoring-choice.html", ready: "#refactoring-choice-section" },
  { path: "/code-blame.html", ready: "#code-blame-section" },
  {
    path: "/single-file-analysis.html",
    ready: "#advanced-analysis-shell",
    extra: ["#advanced-code-view", "#advanced-report-text", "#advanced-submit-btn", "#advanced-load-btn"],
  },
  {
    path: "/multi-file-analysis.html",
    ready: "#advanced-analysis-shell",
    extra: ["#advanced-file-strip", "#advanced-code-view", "#advanced-report-text", "#advanced-load-btn"],
  },
  {
    path: "/fullstack-analysis.html",
    ready: "#advanced-analysis-shell",
    extra: ["#advanced-file-strip", "#advanced-code-view", "#advanced-report-text", "#advanced-load-btn"],
  },
];

const adminPageTarget = {
  path: "/admin.html",
  ready: ".admin-shell",
  extra: ["#content-summary-panel", "#ops-events-panel"],
};

async function installShellMocks(page, { language = "python", difficulty = "beginner" } = {}) {
  let multiFileJobPollCount = 0;

  await page.addInitScript(({ marker, adminKey, languageId, difficultyId }) => {
    window.localStorage.setItem("code-learning-token", marker);
    window.localStorage.setItem("code-learning-display-name", "Tester");
    window.localStorage.setItem("code-learning-language", languageId);
    window.localStorage.setItem("code-learning-difficulty", difficultyId);
    window.sessionStorage.setItem("admin_panel_key", adminKey);
  }, { marker: SESSION_MARKER, adminKey: ADMIN_KEY, languageId: language, difficultyId: difficulty });

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
      case "/platform/me/settings":
        if (route.request().method() === "PUT") {
          const body = route.request().postDataJSON();
          return json(body);
        }
        return json({
          preferred_language: language,
          preferred_difficulty: toBackendDifficulty(difficulty),
        });
      case "/platform/me/goal":
        return json(goalPayload);
      case "/platform/home":
        return json(homePayload);
      case "/platform/reports/latest":
        return json({
          available: true,
          reportId: 1,
          createdAt: "2026-03-06T10:00:00+09:00",
          goal: "Keep the weekly review cadence",
          summary: "Review wrong answers first and maintain a daily routine.",
          pdfDownloadUrl: "/platform/reports/1/pdf",
        });
      case "/platform/languages":
        return json(languagePayload);
      case "/platform/learning/history":
        return json({ history: [], total: 0, hasMore: false, limit: 200 });
      case "/platform/learning/review-queue":
        return json(homePayload.reviewQueue);
      case "/platform/codeblock/problem":
        return json(codeBlockProblemPayload);
      case "/platform/codeblock/submit":
        return json(codeBlockSubmitPayload);
      case "/platform/analysis/problem":
        return json(analysisProblemPayload);
      case "/platform/analysis/submit":
        return json(analysisSubmitPayload);
      case "/platform/arrange/problem":
        return json(codeArrangeProblemPayload);
      case "/platform/arrange/submit":
        return json(codeArrangeSubmitPayload);
      case "/platform/single-file-analysis/problem":
        return json(singleFileAnalysisPayload);
      case "/platform/multi-file-analysis/problem":
        return json(multiFileAnalysisPayload);
      case "/platform/fullstack-analysis/problem":
        return json(fullstackAnalysisPayload);
      case "/platform/auditor/problem":
        return json(auditorProblemPayload);
      case "/platform/refactoring-choice/problem":
        return json(refactoringChoiceProblemPayload);
      case "/platform/refactoring-choice/submit":
        return json({ queued: true, message: "Submission queued", jobId: "job-refactor-1" });
      case "/platform/code-blame/problem":
        return json(codeBlameProblemPayload);
      case "/platform/code-blame/submit":
        return json({ queued: true, message: "Submission queued", jobId: "job-blame-1" });
      case "/platform/single-file-analysis/submit":
        return json(singleFileAnalysisSubmitPayload);
      case "/platform/multi-file-analysis/submit":
        return json({ queued: true, message: "Submission queued", jobId: "job-multi-1" });
      case "/platform/fullstack-analysis/submit":
        return json(fullstackAnalysisSubmitPayload);
      case "/platform/auditor/submit":
        return json({ queued: true, message: "Submission queued", jobId: "job-auditor-1" });
      case "/platform/mode-jobs/job-multi-1":
        multiFileJobPollCount += 1;
        if (multiFileJobPollCount === 1) {
          return json({
            jobId: "job-multi-1",
            status: "queued",
            queued: true,
            finished: false,
            failed: false,
          });
        }
        return json({
          jobId: "job-multi-1",
          status: "finished",
          queued: false,
          finished: true,
          failed: false,
          result: queuedMultiFileAnalysisSubmitResult,
        });
      case "/platform/mode-jobs/job-auditor-1":
        return json({
          jobId: "job-auditor-1",
          status: "finished",
          queued: false,
          finished: true,
          failed: false,
          result: queuedAuditorSubmitResult,
        });
      case "/platform/mode-jobs/job-refactor-1":
        return json({
          jobId: "job-refactor-1",
          status: "finished",
          queued: false,
          finished: true,
          failed: false,
          result: queuedRefactoringChoiceSubmitResult,
        });
      case "/platform/mode-jobs/job-blame-1":
        return json({
          jobId: "job-blame-1",
          status: "finished",
          queued: false,
          finished: true,
          failed: false,
          result: queuedCodeBlameSubmitResult,
        });
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

  test("login shell stays centered with a single panel layout", async ({ page }) => {
    await page.goto("/index.html");
    const shellBox = await page.locator(".auth-shell").boundingBox();
    const panelBox = await page.locator(".auth-panel").boundingBox();
    expect(shellBox).not.toBeNull();
    expect(panelBox).not.toBeNull();
    const viewportWidth = page.viewportSize().width;
    const shellCenter = shellBox.x + shellBox.width / 2;
    expect(Math.abs(shellCenter - viewportWidth / 2)).toBeLessThan(24);
    expect(panelBox.width).toBeGreaterThan(420);
    expect(panelBox.height).toBeGreaterThan(220);
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

  test("profile renders shared settings and learning summary", async ({ page }) => {
    await installShellMocks(page, { language: "javascript", difficulty: "advanced" });
    await page.goto("/profile.html");
    await expect(page.locator("#language-setting-select")).toHaveValue("javascript");
    await expect(page.locator('#difficulty-setting button[data-value="advanced"]')).toHaveClass(/active/);
    await expect(page.locator("#profile-settings-status")).toContainText("공통 학습 설정");
    await expect(page.locator("#profile-total-attempts")).toContainText("12");
    await expect(page.locator("#profile-accuracy")).toContainText("75%");
    await expect(page.locator("#profile-review-count")).toContainText("1");
    await expect(page.locator("#profile-goal-progress")).toContainText("5 / 10");
    await expect(page.locator("#profile-focus-modes")).toContainText("코드 분석");
  });

  test("dashboard exposes advanced analysis links", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/dashboard.html");
    await expect(page.locator("#dashboard-mode-panel-general")).toBeVisible();
    await expect(page.locator("#dashboard-mode-panel-advanced")).toBeHidden();
    await page.locator("#dashboard-mode-tab-advanced").click();
    await expect(page.locator("#dashboard-mode-panel-general")).toBeHidden();
    await expect(page.locator("#dashboard-mode-panel-advanced")).toBeVisible();
    await expect(page.locator("#advanced-feature-grid .feature-card")).toHaveCount(3);
    await expect(page.locator("#advanced-feature-grid .feature-card-advanced")).toHaveCount(0);
    await expect(page.locator(".dashboard-mode-note")).toHaveCount(0);
    await expect(page.locator('a[href="/single-file-analysis.html"]')).toContainText("단일 파일 분석");
    await expect(page.locator('a[href="/multi-file-analysis.html"]')).toContainText("다중 파일 분석");
    await expect(page.locator('a[href="/fullstack-analysis.html"]')).toContainText("풀스택 코드 분석");
    await page.locator("#dashboard-mode-tab-general").click();
    await expect(page.locator("#dashboard-mode-panel-general")).toBeVisible();
  });

  test("dashboard advanced link opens single file analysis shell", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/dashboard.html");
    await page.locator("#dashboard-mode-tab-advanced").click();
    await page.locator('a[href="/single-file-analysis.html"]').click();
    await expect(page).toHaveURL(/single-file-analysis\.html$/);
    await expect(page.locator("#advanced-analysis-shell")).toBeVisible();
    await expect(page.locator("#advanced-problem-title")).toContainText("문제를 아직 불러오지 않았습니다.");
    await expect(page.locator("#advanced-active-file-name")).toContainText("파일을 기다리는 중입니다.");
    await expect(page.locator("#advanced-load-btn")).toBeVisible();
  });

  test("single file analysis keeps the editor compact for short code", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();
    const metrics = await page.locator("#advanced-code-view").evaluate((el) => {
      const row = el.querySelector(".advanced-code-row");
      const lineNumber = row?.querySelector(".advanced-code-line-number");
      const lineContent = row?.querySelector(".advanced-code-line-content");
      const lineNumberStyle = lineNumber ? getComputedStyle(lineNumber) : null;
      const lineContentStyle = lineContent ? getComputedStyle(lineContent) : null;
      return {
        editorHeight: el.getBoundingClientRect().height,
        rowHeight: row ? row.getBoundingClientRect().height : 0,
        lineNumberHeight: lineNumber ? lineNumber.getBoundingClientRect().height : 0,
        lineNumberLineHeight: lineNumberStyle ? parseFloat(lineNumberStyle.lineHeight) : 0,
        lineContentLineHeight: lineContentStyle ? parseFloat(lineContentStyle.lineHeight) : 0,
      };
    });

    expect(metrics.editorHeight).toBeGreaterThan(300);
    expect(metrics.editorHeight).toBeLessThan(620);
    expect(metrics.rowHeight).toBeLessThan(32);
    expect(metrics.lineNumberHeight).toBeLessThan(30);
    expect(metrics.lineContentLineHeight).toBeLessThan(24);
    expect(Math.abs(metrics.lineNumberLineHeight - metrics.lineContentLineHeight)).toBeLessThan(0.5);
  });

  test("single file analysis submits a report and renders feedback", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();
    await page.locator("#advanced-report-text").fill("진입 함수와 상태 변화를 중심으로 분석했습니다.");
    await page.locator("#advanced-submit-btn").click();
    await expect(page.locator("#advanced-result-panel")).toBeVisible();
    await expect(page.locator("#advanced-result-score")).toContainText("84");
    await expect(page.locator("#advanced-result-verdict")).toContainText("합격");
    await expect(page.locator("#advanced-reference-report")).toContainText("모범 단일 파일 리포트");
  });

  test("analysis loads a problem and renders feedback", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/analysis.html");
    await expect(page.locator("#btn-load-problem")).toBeEnabled();
    await page.locator("#btn-load-problem").click();
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await page.locator("#answer-text").fill("The loop adds each value to total and prints 6.");
    await page.locator("#answer-form button[type='submit']").click();
    await expect(page.locator("#feedback-summary")).toContainText("tracked the execution flow");
    await expect(page.locator("#feedback-score")).toContainText("86");
    await expect(page.locator("#feedback-verdict")).toContainText("정답");
    await expect(page.locator("#model-answer-text")).toContainText("final output is 6");
  });

  test("arrange reveals feedback and the answer code after submit", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/arrange.html");
    await expect(page.locator("#arr-load-btn")).toBeEnabled();
    await page.locator("#arr-load-btn").click();
    await expect(page.locator("#arr-title")).toContainText("Arrange the loop");
    await page.locator("#arr-check-btn").click();
    await expect(page.locator("#arr-feedback")).toBeVisible();
    await expect(page.locator("#arr-answer")).toBeVisible();
    await expect(page.locator("#arr-answer-code")).toContainText("total = 0");
  });

  test("refactoring choice renders queued submit feedback after job polling", async ({ page }) => {
    await installShellMocks(page, { language: "javascript", difficulty: "intermediate" });
    await page.goto("/refactoring-choice.html");
    await expect(page.locator("#rc-load-btn")).toBeEnabled();
    await page.locator("#rc-load-btn").click();
    await expect(page.locator("#rc-problem-title")).toContainText("Pick the best cache strategy");
    await page.locator('input[name="selected-option"][value="B"]').check();
    await page.locator("#rc-report-text").fill("B removes duplicate in-flight calls without long-lived stale cache state.");
    await page.locator("#rc-report-form button[type='submit']").click();
    await expect(page.locator("#rc-score")).toContainText("92");
    await expect(page.locator("#rc-verdict")).toContainText("합격");
    await expect(page.locator("#rc-best-option")).toContainText("B");
    await expect(page.locator("#rc-reference-report")).toContainText("request coalescing");
  });

  test("code blame renders queued submit feedback after job polling", async ({ page }) => {
    await installShellMocks(page, { language: "javascript", difficulty: "intermediate" });
    await page.goto("/code-blame.html");
    await expect(page.locator("#cb-load-btn")).toBeEnabled();
    await page.locator("#cb-load-btn").click();
    await expect(page.locator("#cb-problem-title")).toContainText("Find the breaking commit");
    await page.locator('#cb-commit-list input[type="checkbox"][value="B"]').check();
    await page.locator("#cb-report-text").fill("Commit B removes the guard and makes the undefined access reachable.");
    await page.locator("#cb-report-form button[type='submit']").click();
    await expect(page.locator("#cb-score")).toContainText("89");
    await expect(page.locator("#cb-verdict")).toContainText("합격");
    await expect(page.locator("#cb-culprit-commits")).toContainText("B");
    await expect(page.locator("#cb-reference-report")).toContainText("removed the null guard");
  });

  test("multi file analysis switches files and renders queued submit results", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/multi-file-analysis.html");
    await page.locator("#advanced-load-btn").click();
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_controller.ts");
    await page.locator('[data-advanced-file-id="checkout-service"]').first().click();
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.ts");
    await expect(page.locator("#advanced-code-view")).toContainText("class CheckoutService");
    await page.locator("#advanced-report-text").fill("컨트롤러에서 서비스, 저장소, 알림으로 이어지는 호출 흐름을 정리했습니다.");
    await page.locator("#advanced-submit-btn").click();
    await expect(page.locator("#advanced-result-panel")).toBeVisible();
    await expect(page.locator("#advanced-result-score")).toContainText("88");
    await expect(page.locator("#advanced-result-verdict")).toContainText("합격");
    await expect(page.locator("#advanced-reference-report")).toContainText("모범 다중 파일 리포트");
  });

  test("multi file analysis keeps a fast manual file switch during initial render", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/multi-file-analysis.html");
    await page.locator("#advanced-load-btn").click();
    const secondFile = page.locator('[data-advanced-file-id="checkout-service"]').first();
    await expect(secondFile).toBeVisible();
    await secondFile.click();
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.ts");
    await expect(page.locator("#advanced-code-view")).toContainText("class CheckoutService");
  });

  test("fullstack analysis uses the saved language instead of defaulting to python", async ({ page }) => {
    let requestedLanguage = null;
    await installShellMocks(page, { language: "javascript", difficulty: "advanced" });
    await page.route("**/platform/fullstack-analysis/problem", async (route) => {
      const body = route.request().postDataJSON();
      requestedLanguage = body?.language || null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...fullstackAnalysisPayload,
          language: body?.language || fullstackAnalysisPayload.language,
          difficulty: body?.difficulty || fullstackAnalysisPayload.difficulty,
        }),
      });
    });

    await page.goto("/fullstack-analysis.html");
    await expect(page.locator("#advanced-load-btn")).toBeEnabled();
    await page.locator("#advanced-load-btn").click();
    expect(requestedLanguage).toBe("javascript");
    await expect(page.locator("#advanced-selected-language")).toContainText("JavaScript");
    await page.locator("#advanced-report-text").fill("The request flows from the page into the API and back into the UI state.");
    await page.locator("#advanced-submit-btn").click();
    await expect(page.locator("#advanced-result-panel")).toBeVisible();
    await expect(page.locator("#advanced-result-score")).toContainText("62");
  });

  test("analysis settings panel is not sticky", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/analysis.html");
    const position = await page.locator(".control-panel").evaluate((el) => getComputedStyle(el).position);
    expect(position).not.toBe("sticky");
  });

  test("auditor renders queued submit feedback after job polling", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/auditor.html");
    await page.locator("#auditor-load-btn").click();
    await page.locator("#auditor-report-text").fill("입력 검증과 캐시 분기를 중심으로 위험을 정리했습니다.");
    await page.locator("#auditor-report-form button[type='submit']").click();
    await expect(page.locator("#auditor-score")).toContainText("91", { timeout: 10000 });
    await expect(page.locator("#auditor-verdict")).toContainText("합격");
    await expect(page.locator("#auditor-feedback-summary")).toContainText("입력 검증 누락");
    await expect(page.locator("#auditor-reference-report")).toContainText("모범 감사 리포트");
  });

  test("codeblock submits an answer and renders the explanation", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    await expect(page.locator("#cb-load-btn")).toBeEnabled();
    await page.locator("#cb-load-btn").click();
    await page.locator("#cb-options-container button").first().click();
    await expect(page.locator("#cb-result-message")).toContainText("정답입니다.");
    await expect(page.locator("#cb-explanation")).toContainText("add the current even number");
  });

  test("codeblock desktop settings panel stays wide enough", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    const width = await page.locator(".cb-controls").evaluate((el) => el.getBoundingClientRect().width);
    expect(width).toBeGreaterThan(360);
  });

  test("codeblock shows the code purpose after loading a problem", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/codeblock.html");
    await page.locator("#cb-load-btn").click();
    await expect(page.locator("#cb-problem-title")).toContainText("짝수 합계 누적");
    await expect(page.locator("#cb-problem-purpose")).toContainText("짝수 값만 더해 총합을 계산하는 반복문을 완성하세요.");
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

  test("dashboard exposes advanced analysis links", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/dashboard.html");
    await expect(page.locator("#dashboard-mode-panel-general")).toBeVisible();
    await expect(page.locator("#dashboard-mode-panel-advanced")).toBeHidden();
    await page.locator("#dashboard-mode-tab-advanced").click();
    await expect(page.locator("#dashboard-mode-panel-general")).toBeHidden();
    await expect(page.locator("#dashboard-mode-panel-advanced")).toBeVisible();
    await expect(page.locator("#advanced-feature-grid .feature-card")).toHaveCount(3);
    await expect(page.locator("#advanced-feature-grid .feature-card-advanced")).toHaveCount(0);
    await expect(page.locator(".dashboard-mode-note")).toHaveCount(0);
    await expect(page.locator('a[href="/single-file-analysis.html"]')).toContainText("단일 파일 분석");
    await page.locator("#dashboard-mode-tab-general").click();
    await expect(page.locator("#dashboard-mode-panel-general")).toBeVisible();
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

  test("advanced analysis places file strip before editor on mobile", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/fullstack-analysis.html");
    await expectTopBefore(page, "#advanced-file-strip", "#advanced-code-view");
  });

  test("mobile multi file analysis switches files", async ({ page }) => {
    await installShellMocks(page);
    await page.goto("/multi-file-analysis.html");
    await page.locator("#advanced-load-btn").click();
    await page.locator('[data-advanced-file-id="checkout-service"]').first().click();
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.ts");
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
