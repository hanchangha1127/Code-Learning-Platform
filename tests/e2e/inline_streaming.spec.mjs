import { expect, test } from "@playwright/test";

const SESSION_MARKER = "cookie-session";

const analysisPayload = {
  problem: {
    problemId: "analysis-1",
    title: "Trace the accumulator",
    code: "total = 0\nfor value in [1, 2, 3]:\n    total += value\nprint(total)",
    prompt: "Explain the execution order and the final output.",
    mode: "analysis",
  },
};

const arrangePayload = {
  problemId: "arrange-1",
  title: "Order validation branches",
  prompt: "Arrange the validation code in execution order.",
  blocks: [
    { id: "a", code: "if not user:\n    return None" },
    { id: "b", code: "return build_profile(user)" },
  ],
};

const advancedPayload = {
  problemId: "sf-1",
  title: "Checkout discount flow",
  summary: "Trace the checkout discount path.",
  prompt: "Explain the discount flow and the guard clauses.",
  checklist: ["Find the entry function."],
  files: [
    {
      id: "checkout-service",
      path: "src/checkout_service.py",
      name: "checkout_service.py",
      content: "def checkout(cart):\n    return cart.total()",
    },
  ],
};

async function installSession(page) {
  await page.addInitScript((marker) => {
    window.localStorage.setItem("code-learning-token", marker);
    window.localStorage.setItem("code-learning-display-name", "Tester");
  }, SESSION_MARKER);

  await page.route("**/platform/profile", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ username: "tester", displayName: "Tester" }),
    });
  });
}

async function installStreamMock(page, {
  path,
  payload,
  partials = [JSON.stringify(payload)],
  failBeforePayload = false,
  lateError = false,
  payloadDelayMs = 250,
  streamStatus = 200,
}) {
  await page.addInitScript(({ streamPath, finalPayload, streamPartials, shouldFail, shouldLateError, delayMs, statusCode }) => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    window.__streamProblemCalls = { stream: 0, json: 0 };
    window.fetch = async (input, init) => {
      const requestUrl = typeof input === "string" ? input : input?.url || String(input);
      const pathname = new URL(requestUrl, window.location.origin).pathname;
      if (pathname !== streamPath) return originalFetch(input, init);

      const accept = new Headers(init?.headers || {}).get("Accept") || "";
      if (!accept.includes("text/event-stream")) {
        window.__streamProblemCalls.json += 1;
        return new Response(JSON.stringify(shouldFail ? { detail: "fallback failed" } : finalPayload), {
          status: shouldFail ? 500 : 200,
          headers: { "content-type": "application/json" },
        });
      }
      window.__streamProblemCalls.stream += 1;

      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('event: status\ndata: {"message":"문제를 생성 중입니다."}\n\n'));
          if (shouldFail) {
            controller.enqueue(encoder.encode('event: error\ndata: {"message":"stream failed"}\n\n'));
            controller.close();
            return;
          }
          for (const partial of streamPartials) {
            controller.enqueue(encoder.encode(`event: partial\ndata: ${JSON.stringify({ delta: partial })}\n\n`));
          }
          setTimeout(() => {
            controller.enqueue(encoder.encode(`event: payload\ndata: ${JSON.stringify({ payload: finalPayload })}\n\n`));
            if (shouldLateError) {
              controller.enqueue(encoder.encode('event: error\ndata: {"message":"late failure"}\n\n'));
              controller.enqueue(encoder.encode('event: done\ndata: {"ok":false}\n\n'));
            } else {
              controller.enqueue(encoder.encode('event: done\ndata: {"ok":true}\n\n'));
            }
            controller.close();
          }, delayMs);
        },
      });
      return new Response(stream, { status: statusCode, headers: { "content-type": "text/event-stream" } });
    };
  }, {
    streamPath: path,
    finalPayload: payload,
    streamPartials: partials,
    shouldFail: failBeforePayload,
    shouldLateError: lateError,
    delayMs: payloadDelayMs,
    statusCode: streamStatus,
  });
}

test.describe("inline problem streaming", () => {
  test("analysis renders fields before the final payload", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, {
      path: "/platform/analysis/problem",
      payload: analysisPayload,
      partials: [
        '{"problem":{"title":"Trace the accumulator","code":"total = 0\\nfor value in [1, 2, 3]:\\n    total += value","prompt":"Explain the execution order',
      ],
      payloadDelayMs: 1000,
    });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#analysis-stream-draft")).toContainText("실시간");
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
    await expect(page.locator("#btn-load-problem")).toBeDisabled();
    await expect(page.locator("#answer-form button[type='submit']")).toBeDisabled();
    await expect(page.locator("#problem-prompt")).toContainText("Explain the execution order");
  });

  test("analysis finalizes after payload and enables submit", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#analysis-stream-draft")).toHaveCount(0);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
    await expect(page.locator("#answer-form button[type='submit']")).toBeEnabled();
  });

  test("code arrange never reveals completed source before shuffled blocks", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, {
      path: "/platform/arrange/problem",
      payload: arrangePayload,
      partials: ['{"title":"Order validation branches","prompt":"Arrange the validation code in execution order.","code":"if not user:\\n    return None\\nreturn build_profile(user)"'],
      payloadDelayMs: 1000,
    });

    await page.goto("/arrange.html");
    await page.locator("#arr-load-btn").click();

    await expect(page.locator("#arr-stream-code")).toHaveCount(0);
    await expect(page.locator("#arr-stream-safe-note")).toContainText("완성 코드는 표시하지 않고");
    await expect(page.locator("#arr-blocks")).not.toContainText("return build_profile(user)");
    await expect(page.locator("#arr-check-btn")).toBeDisabled();
    await expect(page.locator("#arr-blocks .arrange-block")).toHaveCount(2);
    await expect(page.locator("#arr-check-btn")).toBeEnabled();
  });

  test("advanced analysis streams workspace metadata and then files", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, {
      path: "/platform/single-file-analysis/problem",
      payload: advancedPayload,
      partials: [JSON.stringify({ title: advancedPayload.title, summary: advancedPayload.summary, workspace: "single-file-analysis.workspace", files: advancedPayload.files })],
      payloadDelayMs: 1000,
    });

    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();

    await expect(page.locator("#advanced-mode-headline")).toContainText("Checkout discount flow");
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.py");
    await expect(page.locator("#advanced-submit-btn")).toBeDisabled();
    await expect(page.locator("#advanced-submit-btn")).toBeEnabled();
  });

  test("analysis reads stream errors without retrying the same POST", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload, failBeforePayload: true, streamStatus: 503 });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toHaveText("문제를 불러오면 시작할 수 있습니다.");
    await expect(page.locator("#problem-code")).toHaveText("// 불러온 문제가 없습니다.");
    await expect(page.locator("#problem-prompt")).toContainText("문제를 불러온 뒤");
    await expect(page.locator("#analysis-stream-draft")).toHaveCount(0);
    await expect(page.locator(".status-line")).toContainText("stream failed");
    await expect.poll(() => page.evaluate(() => window.__streamProblemCalls)).toEqual({ stream: 1, json: 0 });
  });

  test("analysis keeps payload after a late stream error", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload, lateError: true });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
    await expect(page.locator(".status-line")).toContainText("late failure");
  });
});
