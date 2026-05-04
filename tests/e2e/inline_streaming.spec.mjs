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

const advancedPayload = {
  problemId: "sf-1",
  title: "Checkout discount flow",
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

async function installStreamMock(page, { path, payload, failBeforePayload = false, lateError = false }) {
  await page.addInitScript(({ streamPath, finalPayload, shouldFail, shouldLateError }) => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    window.fetch = async (input, init) => {
      const requestUrl = typeof input === "string" ? input : input?.url || String(input);
      const pathname = new URL(requestUrl, window.location.origin).pathname;
      if (pathname !== streamPath) return originalFetch(input, init);

      const accept = new Headers(init?.headers || {}).get("Accept") || "";
      if (!accept.includes("text/event-stream")) {
        return new Response(JSON.stringify(shouldFail ? { detail: "fallback failed" } : finalPayload), {
          status: shouldFail ? 500 : 200,
          headers: { "content-type": "application/json" },
        });
      }

      const stream = new ReadableStream({
        start(controller) {
          if (shouldFail) {
            controller.enqueue(encoder.encode('event: error\ndata: {"message":"stream failed"}\n\n'));
            controller.close();
            return;
          }
          controller.enqueue(encoder.encode(`event: partial\ndata: ${JSON.stringify({ delta: JSON.stringify(finalPayload).slice(0, 60) })}\n\n`));
          controller.enqueue(encoder.encode(`event: payload\ndata: ${JSON.stringify({ payload: finalPayload })}\n\n`));
          if (shouldLateError) {
            controller.enqueue(encoder.encode('event: error\ndata: {"message":"late failure"}\n\n'));
          }
          controller.enqueue(encoder.encode('event: done\ndata: {"ok":true}\n\n'));
          controller.close();
        },
      });
      return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
  }, { streamPath: path, finalPayload: payload, shouldFail: failBeforePayload, shouldLateError: lateError });
}

test.describe("inline problem streaming", () => {
  test("analysis streams into the problem card", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
    await expect(page.locator("#problem-prompt")).toContainText("Explain the execution order");
  });

  test("advanced analysis streams into the workspace", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/single-file-analysis/problem", payload: advancedPayload });

    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();

    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
    await expect(page.locator("#advanced-problem-title")).toContainText("Checkout discount flow");
    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.py");
    await expect(page.locator("#advanced-code-view")).toContainText("def checkout");
  });

  test("analysis resets when stream and json fallback both fail", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload, failBeforePayload: true });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toHaveText("문제를 불러오면 시작할 수 있습니다.");
    await expect(page.locator("#problem-code")).toHaveText("// 불러온 문제가 없습니다.");
    await expect(page.locator("#problem-prompt")).toContainText("문제를 불러온 뒤");
    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
  });

  test("analysis keeps payload after a late stream error", async ({ page }) => {
    await installSession(page);
    await installStreamMock(page, { path: "/platform/analysis/problem", payload: analysisPayload, lateError: true });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
  });
});
