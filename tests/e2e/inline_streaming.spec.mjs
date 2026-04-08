import { expect, test } from "@playwright/test";

const SESSION_MARKER = "cookie-session";

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
  totalAttempts: 3,
  accuracy: 67,
  diagnosticRemaining: 0,
  diagnosticAnswered: 3,
  diagnosticTotal: 3,
};

const analysisProblemPayload = {
  problem: {
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
};

const singleFileAnalysisPayload = {
  problemId: "sf-1",
  title: "Checkout discount flow",
  summary: "Trace the single file execution path.",
  language: "python",
  difficulty: "beginner",
  workspace: "single-file-analysis.workspace",
  prompt: "Explain the discount flow and the guard clauses.",
  checklist: [
    "Find the entry function.",
    "Track the state changes.",
    "Call out risky edge cases.",
  ],
  files: [
    {
      id: "checkout-service",
      path: "src/checkout_service.py",
      name: "checkout_service.py",
      role: "service",
      language: "python",
      content: `def checkout(cart, coupon):
    subtotal = cart.total()
    if not cart.items:
        return 0
    return subtotal`,
    },
  ],
};

function buildStreamChunks(text, size = 48) {
  const value = String(text || "");
  const chunks = [];
  for (let index = 0; index < value.length; index += size) {
    chunks.push(value.slice(index, index + size));
  }
  return chunks;
}

async function installCommonMocks(page, { language = "python", difficulty = "beginner" } = {}) {
  await page.addInitScript(({ marker, languageId, difficultyId }) => {
    window.localStorage.setItem("code-learning-token", marker);
    window.localStorage.setItem("code-learning-display-name", "Tester");
    window.localStorage.setItem("code-learning-language", languageId);
    window.localStorage.setItem("code-learning-difficulty", difficultyId);
  }, { marker: SESSION_MARKER, languageId: language, difficultyId: difficulty });

  await page.route("**/platform/languages", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(languagePayload),
    });
  });

  await page.route("**/platform/profile", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(profilePayload),
    });
  });
}

async function installStreamFetchMock(page, { path, payload, statusMessage = "Generating..." }) {
  const chunks = buildStreamChunks(JSON.stringify(payload));
  await page.addInitScript(({ streamPath, streamChunks, finalPayload, message }) => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();

    window.fetch = async (input, init) => {
      const requestUrl =
        typeof input === "string" ? input : input instanceof Request ? input.url : String(input?.url || "");
      const pathname = new URL(requestUrl, window.location.origin).pathname;
      if (pathname !== streamPath) {
        return originalFetch(input, init);
      }

      let delay = 0;
      const stream = new ReadableStream({
        start(controller) {
          const emit = (eventName, data, waitMs = 0) => {
            delay += waitMs;
            window.setTimeout(() => {
              controller.enqueue(
                encoder.encode(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`)
              );
            }, delay);
          };

          emit("status", { phase: "generating", message }, 10);
          streamChunks.forEach((chunk) => {
            emit("partial", { delta: chunk }, 140);
          });
          emit("status", { phase: "rendering", message: "Rendering..." }, 160);
          emit("payload", { payload: finalPayload }, 220);
          emit("done", { ok: true }, 60);
          window.setTimeout(() => controller.close(), delay + 80);
        },
      });

      return new Response(stream, {
        status: 200,
        headers: {
          "content-type": "text/event-stream",
        },
      });
    };
  }, {
    streamPath: path,
    streamChunks: chunks,
    finalPayload: payload,
    message: statusMessage,
  });
}

async function installFailingStreamThenJsonFallbackMock(
  page,
  {
    path,
    previewPayload,
    fallbackMessage = "fallback failed",
    statusMessage = "Generating...",
  }
) {
  const previewText = JSON.stringify(previewPayload);
  await page.addInitScript(({ streamPath, partialText, detailMessage, message }) => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();

    window.fetch = async (input, init) => {
      const requestUrl =
        typeof input === "string" ? input : input instanceof Request ? input.url : String(input?.url || "");
      const pathname = new URL(requestUrl, window.location.origin).pathname;
      if (pathname !== streamPath) {
        return originalFetch(input, init);
      }

      const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
      const accept = (headers.get("Accept") || "").toLowerCase();
      if (!accept.includes("text/event-stream")) {
        return new Response(JSON.stringify({ detail: detailMessage }), {
          status: 500,
          headers: {
            "content-type": "application/json",
          },
        });
      }

      let delay = 0;
      const stream = new ReadableStream({
        start(controller) {
          const emit = (eventName, data, waitMs = 0) => {
            delay += waitMs;
            window.setTimeout(() => {
              controller.enqueue(
                encoder.encode(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`)
              );
            }, delay);
          };

          emit("status", { phase: "generating", message }, 10);
          emit("partial", { delta: partialText }, 120);
          emit("error", { code: "stream_failed", message: "stream failed", retryable: true }, 120);
          emit("done", { ok: false, code: "stream_failed", persisted: false }, 40);
          window.setTimeout(() => controller.close(), delay + 60);
        },
      });

      return new Response(stream, {
        status: 200,
        headers: {
          "content-type": "text/event-stream",
        },
      });
    };
  }, {
    streamPath: path,
    partialText: previewText,
    detailMessage: fallbackMessage,
    message: statusMessage,
  });
}

async function installPayloadThenLateErrorMock(
  page,
  {
    path,
    payload,
    fallbackPayload,
    statusMessage = "Generating...",
  }
) {
  await page.addInitScript(({ streamPath, finalPayload, fallbackBody, message }) => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();

    window.fetch = async (input, init) => {
      const requestUrl =
        typeof input === "string" ? input : input instanceof Request ? input.url : String(input?.url || "");
      const pathname = new URL(requestUrl, window.location.origin).pathname;
      if (pathname !== streamPath) {
        return originalFetch(input, init);
      }

      const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
      const accept = (headers.get("Accept") || "").toLowerCase();
      if (!accept.includes("text/event-stream")) {
        return new Response(JSON.stringify(fallbackBody), {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        });
      }

      let delay = 0;
      const stream = new ReadableStream({
        start(controller) {
          const emit = (eventName, data, waitMs = 0) => {
            delay += waitMs;
            window.setTimeout(() => {
              controller.enqueue(
                encoder.encode(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`)
              );
            }, delay);
          };

          emit("status", { phase: "generating", message }, 10);
          emit("status", { phase: "rendering", message: "Rendering..." }, 120);
          emit("payload", { payload: finalPayload }, 120);
          emit("error", { code: "stream_failed", message: "late stream failed", retryable: true }, 200);
          emit("done", { ok: false, code: "stream_failed", persisted: false }, 40);
          window.setTimeout(() => controller.close(), delay + 80);
        },
      });

      return new Response(stream, {
        status: 200,
        headers: {
          "content-type": "text/event-stream",
        },
      });
    };
  }, {
    streamPath: path,
    finalPayload: payload,
    fallbackBody: fallbackPayload,
    message: statusMessage,
  });
}

test.describe("inline problem streaming", () => {
  test("analysis streams into the existing problem card without a preview block", async ({ page }) => {
    await installCommonMocks(page);
    await installStreamFetchMock(page, {
      path: "/platform/analysis/problem",
      payload: analysisProblemPayload,
    });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await page.waitForTimeout(260);
    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");

    await expect(page.locator("#problem-prompt")).toContainText("Explain the execution order");
  });

  test("advanced analysis streams into the existing task panel without a preview block", async ({ page }) => {
    await installCommonMocks(page);
    await installStreamFetchMock(page, {
      path: "/platform/single-file-analysis/problem",
      payload: singleFileAnalysisPayload,
    });

    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();

    await page.waitForTimeout(260);
    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
    await expect(page.locator("#advanced-problem-title")).toContainText("Checkout discount flow");
    await expect(page.locator("#advanced-task-prompt")).toContainText("discount flow");

    await expect(page.locator("#advanced-active-file-name")).toContainText("checkout_service.py");
    await expect(page.locator("#advanced-code-view")).toContainText("def checkout");
  });

  test("analysis resets the existing problem card when streamed preview and json fallback both fail", async ({ page }) => {
    await installCommonMocks(page);
    await installFailingStreamThenJsonFallbackMock(page, {
      path: "/platform/analysis/problem",
      previewPayload: {
        title: "Half rendered title",
        code: "print('partial')",
        prompt: "Half rendered prompt",
      },
    });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toHaveText(
      "내 정보에서 언어를 설정하면 문제를 보여드릴게요."
    );
    await expect(page.locator("#problem-code")).toHaveText("// 아직 로드된 문제가 없습니다.");
    await expect(page.locator("#problem-prompt")).toContainText("맞춤 문제를 받은 뒤");
    await expect(page.locator("#code-problem-stream-preview-inline")).toHaveCount(0);
  });

  test("analysis keeps the streamed problem after a late stream error", async ({ page }) => {
    await installCommonMocks(page);
    await installPayloadThenLateErrorMock(page, {
      path: "/platform/analysis/problem",
      payload: analysisProblemPayload,
      fallbackPayload: {
        problem: {
          problemId: "analysis-fallback",
          title: "JSON fallback title",
          code: "print('fallback')",
          prompt: "Fallback prompt",
          mode: "analysis",
          difficulty: "beginner",
          track: "fallback",
          language: "python",
        },
      },
    });

    await page.goto("/analysis.html");
    await page.locator("#btn-load-problem").click();

    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-code")).toContainText("total = 0");
    await page.waitForTimeout(500);
    await expect(page.locator("#problem-title")).toContainText("Trace the accumulator");
    await expect(page.locator("#problem-title")).not.toContainText("JSON fallback title");
  });

  test("advanced analysis keeps the streamed problem after a late stream error", async ({ page }) => {
    await installCommonMocks(page);
    await installPayloadThenLateErrorMock(page, {
      path: "/platform/single-file-analysis/problem",
      payload: singleFileAnalysisPayload,
      fallbackPayload: {
        problemId: "advanced-fallback",
        title: "Fallback advanced title",
        prompt: "Fallback prompt",
        workspace: "single-file-analysis.workspace",
        language: "python",
        difficulty: "beginner",
        checklist: ["fallback"],
        files: [
          {
            id: "fallback-file",
            path: "src/fallback.py",
            name: "fallback.py",
            language: "python",
            role: "entrypoint",
            content: "print('fallback')",
          },
        ],
      },
    });

    await page.goto("/single-file-analysis.html");
    await page.locator("#advanced-load-btn").click();

    await expect(page.locator("#advanced-problem-title")).toContainText("Checkout discount flow");
    await expect(page.locator("#advanced-code-view")).toContainText("def checkout");
    await page.waitForTimeout(500);
    await expect(page.locator("#advanced-problem-title")).toContainText("Checkout discount flow");
    await expect(page.locator("#advanced-problem-title")).not.toContainText("Fallback advanced title");
    await expect(page.locator("#advanced-code-view")).toContainText("def checkout");
  });
});
