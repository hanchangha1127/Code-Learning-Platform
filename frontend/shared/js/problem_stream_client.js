(() => {
  const STREAM_ERROR_CODES = Object.freeze({
    STREAM_UNSUPPORTED: "STREAM_UNSUPPORTED",
    STREAM_HANDSHAKE_FAILED: "STREAM_HANDSHAKE_FAILED",
    STREAM_RUNTIME_ERROR: "STREAM_RUNTIME_ERROR",
    STREAM_ABORTED: "STREAM_ABORTED",
    STREAM_NETWORK_ERROR: "STREAM_NETWORK_ERROR",
  });
  const JSON_FALLBACK_CODES = new Set([
    STREAM_ERROR_CODES.STREAM_UNSUPPORTED,
    STREAM_ERROR_CODES.STREAM_HANDSHAKE_FAILED,
    STREAM_ERROR_CODES.STREAM_RUNTIME_ERROR,
    STREAM_ERROR_CODES.STREAM_ABORTED,
    STREAM_ERROR_CODES.STREAM_NETWORK_ERROR,
  ]);

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function randomInt(min, max) {
    const safeMin = Math.max(0, Number(min) || 0);
    const safeMax = Math.max(safeMin, Number(max) || safeMin);
    return Math.floor(Math.random() * (safeMax - safeMin + 1)) + safeMin;
  }

  async function typeText(target, text, { minDelay = 10, maxDelay = 16 } = {}) {
    if (!target) return;
    const value = String(text ?? "");
    if (value.length > 1200) {
      target.textContent = value;
      return;
    }

    target.textContent = "";
    for (const ch of value) {
      target.textContent += ch;
      await sleep(randomInt(minDelay, maxDelay));
    }
  }

  async function revealLines(target, text, { lineDelay = 70 } = {}) {
    if (!target) return;
    const value = String(text ?? "");
    const lines = value.split("\n");
    target.textContent = "";
    for (let i = 0; i < lines.length; i += 1) {
      target.textContent = lines.slice(0, i + 1).join("\n");
      if (i < lines.length - 1) {
        await sleep(lineDelay);
      }
    }
  }

  async function revealList(
    target,
    items,
    {
      itemDelay = 70,
      renderItem = (item) => {
        const li = document.createElement("li");
        li.textContent = String(item ?? "");
        return li;
      },
    } = {}
  ) {
    if (!target) return;
    target.innerHTML = "";
    const list = Array.isArray(items) ? items : [];
    for (const item of list) {
      const node = renderItem(item);
      if (node) {
        target.appendChild(node);
      }
      await sleep(itemDelay);
    }
  }

  function parseSseChunk(chunk) {
    let eventName = "message";
    const dataLines = [];
    const lines = String(chunk || "").split(/\r?\n/);

    for (const line of lines) {
      if (!line || line.startsWith(":")) continue;
      const sep = line.indexOf(":");
      const field = sep === -1 ? line : line.slice(0, sep);
      let value = sep === -1 ? "" : line.slice(sep + 1);
      if (value.startsWith(" ")) {
        value = value.slice(1);
      }

      if (field === "event") {
        eventName = value || "message";
      } else if (field === "data") {
        dataLines.push(value);
      }
    }

    const dataText = dataLines.join("\n");
    if (!dataText) {
      return { event: eventName, data: {} };
    }

    try {
      return { event: eventName, data: JSON.parse(dataText) };
    } catch {
      return { event: eventName, data: { raw: dataText } };
    }
  }

  async function readErrorMessage(response) {
    const text = (await response.text()) || "";
    if (!text) {
      return `요청에 실패했습니다. (${response.status})`;
    }

    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object") {
        return parsed.detail || parsed.message || text;
      }
      return text;
    } catch {
      return text;
    }
  }

  function createStreamError(code, message, { httpStatus, retryable, serverCode, streamStarted } = {}) {
    const error = new Error(message || "문제 스트리밍 중 오류가 발생했습니다.");
    error.name = "ProblemStreamError";
    error.code = code || STREAM_ERROR_CODES.STREAM_RUNTIME_ERROR;
    if (typeof httpStatus === "number") {
      error.httpStatus = httpStatus;
    }
    if (typeof retryable === "boolean") {
      error.retryable = retryable;
    }
    if (serverCode) {
      error.serverCode = serverCode;
    }
    error.streamStarted = Boolean(streamStarted);
    return error;
  }

  function shouldFallbackToJson(error) {
    return JSON_FALLBACK_CODES.has(error?.code);
  }

  async function streamProblem({
    path,
    token,
    body,
    onStatus = null,
    onPayload = null,
    onDone = null,
    signal = undefined,
  }) {
    const authClient = window.CodeAuth || null;
    const headers = {
      Accept: "text/event-stream",
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const canUseBearer =
      token &&
      !(authClient && typeof authClient.isSessionMarker === "function" && authClient.isSessionMarker(token));
    if (canUseBearer) {
      headers.Authorization = `Bearer ${token}`;
    }

    let response;
    try {
      response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal,
      });
    } catch (fetchError) {
      if (fetchError?.name === "AbortError") {
        throw createStreamError(STREAM_ERROR_CODES.STREAM_ABORTED, "요청이 취소되었습니다.", {
          retryable: false,
          streamStarted: false,
        });
      }
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_NETWORK_ERROR,
        fetchError?.message || "스트리밍 요청 중 네트워크 오류가 발생했습니다.",
        {
          retryable: true,
          streamStarted: false,
        }
      );
    }

    if (!response.ok) {
      throw createStreamError(STREAM_ERROR_CODES.STREAM_HANDSHAKE_FAILED, await readErrorMessage(response), {
        httpStatus: response.status,
        retryable: response.status >= 500,
        streamStarted: false,
      });
    }

    const contentType = (response.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("text/event-stream")) {
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_UNSUPPORTED,
        "스트리밍 응답을 지원하지 않는 환경입니다.",
        {
          retryable: true,
          streamStarted: false,
        }
      );
    }
    if (!response.body) {
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_UNSUPPORTED,
        "스트리밍 본문을 읽을 수 없습니다.",
        {
          retryable: true,
          streamStarted: false,
        }
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamStarted = false;
    let receivedPayload;
    let streamErrorPayload = null;
    let donePayload = null;
    let trailingReadError = null;

    const processEvent = (eventName, data) => {
      streamStarted = true;
      if (eventName === "status") {
        if (typeof onStatus === "function") onStatus(data);
        return;
      }
      if (eventName === "payload") {
        receivedPayload = data && typeof data === "object" && "payload" in data ? data.payload : data;
        if (typeof onPayload === "function") onPayload(receivedPayload, data);
        return;
      }
      if (eventName === "error") {
        streamErrorPayload = data || {};
        return;
      }
      if (eventName === "done") {
        donePayload = data || {};
        if (typeof onDone === "function") onDone(data);
      }
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && value.length > 0) {
          streamStarted = true;
        }
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split(/\r?\n\r?\n/);
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          if (!chunk.trim()) continue;
          const parsed = parseSseChunk(chunk);
          processEvent(parsed.event, parsed.data);
        }
      }
    } catch (streamReadError) {
      if (streamReadError?.name === "AbortError") {
        if (receivedPayload !== undefined) {
          trailingReadError = streamReadError;
        } else {
          throw createStreamError(STREAM_ERROR_CODES.STREAM_ABORTED, "요청이 취소되었습니다.", {
            retryable: false,
            streamStarted,
          });
        }
      } else if (receivedPayload !== undefined) {
        trailingReadError = streamReadError;
      } else {
        throw createStreamError(
          STREAM_ERROR_CODES.STREAM_NETWORK_ERROR,
          streamReadError?.message || "스트리밍 수신 중 네트워크 오류가 발생했습니다.",
          {
            retryable: true,
            streamStarted,
          }
        );
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      const parsed = parseSseChunk(buffer);
      processEvent(parsed.event, parsed.data);
    }

    if (streamErrorPayload) {
      if (receivedPayload !== undefined) {
        return receivedPayload;
      }
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_RUNTIME_ERROR,
        streamErrorPayload.message || "문제 스트리밍 중 오류가 발생했습니다.",
        {
          httpStatus: streamErrorPayload.httpStatus,
          retryable: streamErrorPayload.retryable,
          serverCode: streamErrorPayload.code,
          streamStarted: true,
        }
      );
    }

    if (donePayload && donePayload.ok === false && receivedPayload === undefined) {
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_RUNTIME_ERROR,
        "문제 스트리밍이 실패로 종료되었습니다.",
        {
          retryable: true,
          serverCode: donePayload.code,
          streamStarted: true,
        }
      );
    }

    if (receivedPayload === undefined) {
      throw createStreamError(
        STREAM_ERROR_CODES.STREAM_RUNTIME_ERROR,
        "스트리밍 payload를 받지 못했습니다.",
        {
          retryable: true,
          streamStarted,
        }
      );
    }

    if (trailingReadError) {
      return receivedPayload;
    }
    return receivedPayload;
  }

  window.CodeProblemStream = {
    ERROR_CODES: STREAM_ERROR_CODES,
    sleep,
    shouldFallbackToJson,
    typeText,
    revealLines,
    revealList,
    streamProblem,
  };
})();

