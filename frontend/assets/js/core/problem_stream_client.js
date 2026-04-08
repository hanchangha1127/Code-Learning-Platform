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

  function prefersReducedMotion() {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function streamAnimationsEnabled() {
    const bodySetting =
      typeof document !== "undefined" ? document.body?.dataset?.problemStreamAnimation : undefined;
    const globalSetting = window.CodeProblemStreamConfig?.animation;
    const setting = bodySetting || globalSetting;
    if (setting === "on") {
      return !prefersReducedMotion();
    }
    if (setting === "off") {
      return false;
    }
    return false;
  }

  function shouldAnimateStep({ force = false, valueLength = 0, lineCount = 0 } = {}) {
    if (!force && !streamAnimationsEnabled()) {
      return false;
    }
    if (valueLength > 240 || lineCount > 24) {
      return false;
    }
    return true;
  }

  async function typeText(target, text, { minDelay = 2, maxDelay = 4, force = false } = {}) {
    if (!target) return;
    const value = String(text ?? "");
    if (!shouldAnimateStep({ force, valueLength: value.length }) || value.length > 1200) {
      target.textContent = value;
      return;
    }

    target.textContent = "";
    for (const ch of value) {
      target.textContent += ch;
      await sleep(randomInt(minDelay, maxDelay));
    }
  }

  async function revealLines(target, text, { lineDelay = 20, force = false } = {}) {
    if (!target) return;
    const value = String(text ?? "");
    const lines = value.split("\n");
    if (!shouldAnimateStep({ force, valueLength: value.length, lineCount: lines.length })) {
      target.textContent = value;
      return;
    }
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
      itemDelay = 20,
      force = false,
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
    if (!shouldAnimateStep({ force, lineCount: list.length })) {
      for (const item of list) {
        const node = renderItem(item);
        if (node) {
          target.appendChild(node);
        }
      }
      return;
    }
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

  function scanJsonStringEnd(text, startIndex) {
    let escaped = false;
    for (let index = startIndex + 1; index < text.length; index += 1) {
      const ch = text[index];
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        return index + 1;
      }
    }
    return -1;
  }

  function scanJsonCompositeEnd(text, startIndex, openChar, closeChar) {
    let depth = 0;
    let inString = false;
    let escaped = false;

    for (let index = startIndex; index < text.length; index += 1) {
      const ch = text[index];
      if (inString) {
        if (escaped) {
          escaped = false;
          continue;
        }
        if (ch === "\\") {
          escaped = true;
          continue;
        }
        if (ch === '"') {
          inString = false;
        }
        continue;
      }

      if (ch === '"') {
        inString = true;
        continue;
      }
      if (ch === openChar) {
        depth += 1;
        continue;
      }
      if (ch === closeChar) {
        depth -= 1;
        if (depth === 0) {
          return index + 1;
        }
      }
    }
    return -1;
  }

  function findJsonValueRange(text, key) {
    const keyToken = `"${key}"`;
    let searchIndex = 0;
    let lastRange = null;

    while (searchIndex < text.length) {
      const keyIndex = text.indexOf(keyToken, searchIndex);
      if (keyIndex === -1) {
        break;
      }
      let cursor = keyIndex + keyToken.length;
      while (cursor < text.length && /\s/.test(text[cursor])) {
        cursor += 1;
      }
      if (text[cursor] !== ":") {
        searchIndex = keyIndex + keyToken.length;
        continue;
      }
      cursor += 1;
      while (cursor < text.length && /\s/.test(text[cursor])) {
        cursor += 1;
      }
      if (cursor >= text.length) {
        break;
      }

      let endIndex = -1;
      const firstChar = text[cursor];
      if (firstChar === '"') {
        endIndex = scanJsonStringEnd(text, cursor);
      } else if (firstChar === "[") {
        endIndex = scanJsonCompositeEnd(text, cursor, "[", "]");
      } else if (firstChar === "{") {
        endIndex = scanJsonCompositeEnd(text, cursor, "{", "}");
      } else {
        let primitiveEnd = cursor;
        while (primitiveEnd < text.length && !/[,\]}]/.test(text[primitiveEnd])) {
          primitiveEnd += 1;
        }
        const primitive = text.slice(cursor, primitiveEnd).trim();
        if (primitive) {
          endIndex = cursor + primitive.length;
        }
      }

      if (endIndex === -1) {
        break;
      }

      lastRange = [cursor, endIndex];
      searchIndex = endIndex;
    }

    return lastRange;
  }

  function parseJsonValueByKey(text, key) {
    const range = findJsonValueRange(text, key);
    if (!range) {
      return null;
    }
    try {
      return JSON.parse(text.slice(range[0], range[1]));
    } catch {
      return null;
    }
  }

  function normalizePreviewText(value) {
    return String(value ?? "")
      .replace(/\r\n?/g, "\n")
      .trim();
  }

  function pushPreviewSection(sections, value) {
    const text = normalizePreviewText(value);
    if (!text) {
      return;
    }
    sections.push(text);
  }

  function pushLabeledList(sections, label, value) {
    const items = Array.isArray(value)
      ? value.map((item) => normalizePreviewText(item)).filter(Boolean)
      : [];
    if (!items.length) {
      return;
    }
    sections.push(`${label}\n- ${items.join("\n- ")}`);
  }

  function pushCodeOptions(sections, label, rows, { codeKey = "code", titleKey = "title" } = {}) {
    const items = Array.isArray(rows) ? rows : [];
    if (!items.length) {
      return;
    }
    const rendered = items
      .map((row) => {
        const optionId = normalizePreviewText(row?.optionId || row?.option_id);
        const title = normalizePreviewText(row?.[titleKey] || "옵션");
        const code = normalizePreviewText(row?.[codeKey]);
        const head = optionId ? `${optionId} - ${title}` : title;
        return code ? `${head}\n${code}` : head;
      })
      .filter(Boolean);
    if (!rendered.length) {
      return;
    }
    sections.push(`${label}\n\n${rendered.join("\n\n")}`);
  }

  function pushFilesPreview(sections, files) {
    const rows = Array.isArray(files) ? files : [];
    if (!rows.length) {
      return;
    }
    const rendered = rows
      .map((file) => {
        const path = normalizePreviewText(file?.path || file?.name || "file");
        const content = normalizePreviewText(file?.content);
        return content ? `${path}\n${content}` : path;
      })
      .filter(Boolean);
    if (!rendered.length) {
      return;
    }
    sections.push(`파일 미리보기\n\n${rendered.join("\n\n")}`);
  }

  function inferPreviewKindFromPath(path) {
    const normalized = String(path || "").toLowerCase();
    if (normalized.includes("/analysis/problem")) return "analysis";
    if (normalized.includes("/codeblock/problem")) return "code-block";
    if (normalized.includes("/auditor/problem")) return "auditor";
    if (normalized.includes("/refactoring-choice/problem")) return "refactoring-choice";
    if (normalized.includes("/code-blame/problem")) return "code-blame";
    if (
      normalized.includes("/single-file-analysis/problem") ||
      normalized.includes("/multi-file-analysis/problem") ||
      normalized.includes("/fullstack-analysis/problem")
    ) {
      return "advanced-analysis";
    }
    return "";
  }

  function tryParseCompletePreviewPayload(partialText) {
    const source = String(partialText || "").trim();
    if (!source) {
      return null;
    }
    try {
      return JSON.parse(source);
    } catch {
      return null;
    }
  }

  function getPreviewSourceObject(payload) {
    if (!payload || typeof payload !== "object") {
      return null;
    }
    if (payload.problem && typeof payload.problem === "object") {
      return payload.problem;
    }
    return payload;
  }

  function buildProblemPreviewDraftFromObject(payload, previewKind) {
    const kind = String(previewKind || "").trim().toLowerCase();
    const source = getPreviewSourceObject(payload);
    if (!source) {
      return {};
    }

    if (kind === "analysis") {
      return {
        title: source.title,
        code: source.code,
        prompt: source.prompt,
      };
    }
    if (kind === "code-block") {
      return {
        title: source.title,
        objective: source.objective || source.goal || source.summary,
        code: source.code,
        options: source.options,
        prompt: source.prompt,
      };
    }
    if (kind === "auditor") {
      return {
        title: source.title,
        code: source.code,
        prompt: source.prompt,
      };
    }
    if (kind === "refactoring-choice") {
      return {
        title: source.title,
        scenario: source.scenario,
        constraints: source.constraints,
        options: source.options,
        prompt: source.prompt,
      };
    }
    if (kind === "code-blame") {
      return {
        title: source.title,
        errorLog: source.errorLog,
        commits: source.commits,
        prompt: source.prompt,
      };
    }
    if (kind === "advanced-analysis") {
      return {
        title: source.title,
        prompt: source.prompt,
        checklist: source.checklist,
        files: source.files,
      };
    }
    return {};
  }

  function buildProblemPreviewDraftFromText(partialText, previewKind) {
    const kind = String(previewKind || "").trim().toLowerCase();

    if (kind === "analysis") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        code: parseJsonValueByKey(partialText, "code"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
      };
    }
    if (kind === "code-block") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        objective:
          parseJsonValueByKey(partialText, "objective") ||
          parseJsonValueByKey(partialText, "goal") ||
          parseJsonValueByKey(partialText, "summary"),
        code: parseJsonValueByKey(partialText, "code"),
        options: parseJsonValueByKey(partialText, "options"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
      };
    }
    if (kind === "auditor") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        code: parseJsonValueByKey(partialText, "code"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
      };
    }
    if (kind === "refactoring-choice") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        scenario: parseJsonValueByKey(partialText, "scenario"),
        constraints: parseJsonValueByKey(partialText, "constraints"),
        options: parseJsonValueByKey(partialText, "options"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
      };
    }
    if (kind === "code-blame") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        errorLog: parseJsonValueByKey(partialText, "errorLog"),
        commits: parseJsonValueByKey(partialText, "commits"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
      };
    }
    if (kind === "advanced-analysis") {
      return {
        title: parseJsonValueByKey(partialText, "title"),
        prompt: parseJsonValueByKey(partialText, "prompt"),
        checklist: parseJsonValueByKey(partialText, "checklist"),
        files: parseJsonValueByKey(partialText, "files"),
      };
    }
    return {};
  }

  function buildProblemPreviewDraft(partialText, previewKind) {
    const parsedPayload = tryParseCompletePreviewPayload(partialText);
    if (parsedPayload) {
      return buildProblemPreviewDraftFromObject(parsedPayload, previewKind);
    }
    return buildProblemPreviewDraftFromText(partialText, previewKind);
  }

  function buildProblemPreviewText(partialText, previewKind) {
    const kind = String(previewKind || "").trim().toLowerCase();
    const draft = buildProblemPreviewDraft(partialText, previewKind);
    const sections = [];

    if (kind === "analysis") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.code);
      pushPreviewSection(sections, draft.prompt);
    } else if (kind === "code-block") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.objective);
      pushPreviewSection(sections, draft.code);
      pushLabeledList(sections, "선택지", draft.options);
      pushPreviewSection(sections, draft.prompt);
    } else if (kind === "auditor") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.code);
      pushPreviewSection(sections, draft.prompt);
    } else if (kind === "refactoring-choice") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.scenario);
      pushLabeledList(sections, "제약 조건", draft.constraints);
      pushCodeOptions(sections, "선택지", draft.options);
      pushPreviewSection(sections, draft.prompt);
    } else if (kind === "code-blame") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.errorLog);
      pushCodeOptions(sections, "커밋 후보", draft.commits, {
        codeKey: "diff",
      });
      pushPreviewSection(sections, draft.prompt);
    } else if (kind === "advanced-analysis") {
      pushPreviewSection(sections, draft.title);
      pushPreviewSection(sections, draft.prompt);
      pushLabeledList(sections, "체크리스트", draft.checklist);
      pushFilesPreview(sections, draft.files);
    }

    return sections.join("\n\n").trim();
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

  function isAbortError(error) {
    return error?.code === STREAM_ERROR_CODES.STREAM_ABORTED || error?.name === "AbortError";
  }

  async function loadProblemTransport({
    streamClient = window.CodeProblemStream || null,
    streamRequest,
    jsonRequest,
    shouldFallback = shouldFallbackToJson,
  }) {
    let payload = null;
    let streamed = false;
    let usedJsonFallback = false;
    let allowJsonFallback = false;

    try {
      payload = await streamRequest();
      streamed = Boolean(payload);
    } catch (streamError) {
      allowJsonFallback = typeof shouldFallback === "function" ? Boolean(shouldFallback(streamError)) : Boolean(shouldFallback);
      if (!allowJsonFallback) {
        throw streamError;
      }
    }

    if (!payload && !allowJsonFallback) {
      allowJsonFallback = !streamClient || typeof streamClient.streamProblem !== "function";
    }

    if (!payload && allowJsonFallback) {
      payload = await jsonRequest();
      usedJsonFallback = true;
    }

    return { payload, streamed, usedJsonFallback };
  }

  function ensureStreamPreviewStyles() {
    if (typeof document === "undefined" || document.getElementById("code-problem-stream-preview-style")) {
      return;
    }
    const style = document.createElement("style");
    style.id = "code-problem-stream-preview-style";
    style.textContent = `
      .code-problem-stream-preview {
        position: fixed;
        right: 16px;
        bottom: 16px;
        z-index: 9999;
        width: min(520px, calc(100vw - 32px));
        max-height: min(44vh, 420px);
        border: 1px solid rgba(15, 23, 42, 0.14);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18);
        overflow: hidden;
        backdrop-filter: blur(12px);
      }
      .code-problem-stream-preview[hidden] {
        display: none;
      }
      .code-problem-stream-preview__head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 14px;
        font: 600 12px/1.4 "Segoe UI", sans-serif;
        color: #0f172a;
        background: rgba(148, 163, 184, 0.12);
        border-bottom: 1px solid rgba(15, 23, 42, 0.08);
      }
      .code-problem-stream-preview__body {
        margin: 0;
        padding: 14px;
        overflow: auto;
        max-height: min(34vh, 340px);
        white-space: pre-wrap;
        word-break: break-word;
        font: 12px/1.5 "Cascadia Code", "Consolas", monospace;
        color: #111827;
      }
      .code-problem-stream-preview--inline {
        position: static;
        right: auto;
        bottom: auto;
        width: 100%;
        max-height: none;
        margin-bottom: 14px;
        border-radius: 14px;
        box-shadow: none;
        backdrop-filter: none;
      }
      .code-problem-stream-preview--inline .code-problem-stream-preview__body {
        max-height: min(32vh, 320px);
      }
    `;
    document.head.appendChild(style);
  }

  function createStreamPreview({
    ownerId = `stream-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    container = null,
    title = "AI 생성 스트림",
    subtitle = "최종 렌더 전 초안",
  } = {}) {
    if (typeof document === "undefined" || !document.body) {
      return null;
    }
    ensureStreamPreviewStyles();
    const rootId = container ? "code-problem-stream-preview-inline" : "code-problem-stream-preview";
    let root = document.getElementById(rootId);
    let body = root?.querySelector(".code-problem-stream-preview__body");
    if (!root || !body) {
      root = document.createElement("section");
      root.id = rootId;
      root.className = "code-problem-stream-preview";
      root.hidden = true;
      root.innerHTML = `
        <div class="code-problem-stream-preview__head">
          <span class="code-problem-stream-preview__title"></span>
          <span class="code-problem-stream-preview__subtitle"></span>
        </div>
        <pre class="code-problem-stream-preview__body"></pre>
      `;
      if (container) {
        container.prepend(root);
      } else {
        document.body.appendChild(root);
      }
      body = root.querySelector(".code-problem-stream-preview__body");
    }
    if (!body) {
      return null;
    }
    if (container) {
      root.classList.add("code-problem-stream-preview--inline");
      if (root.parentElement !== container) {
        container.prepend(root);
      }
    } else {
      root.classList.remove("code-problem-stream-preview--inline");
      if (root.parentElement !== document.body) {
        document.body.appendChild(root);
      }
    }
    const titleEl = root.querySelector(".code-problem-stream-preview__title");
    const subtitleEl = root.querySelector(".code-problem-stream-preview__subtitle");
    if (titleEl) {
      titleEl.textContent = title;
    }
    if (subtitleEl) {
      subtitleEl.textContent = subtitle;
    }
    return {
      append(text) {
        const next = String(text ?? "");
        if (!next) return;
        if (root.dataset.owner && root.dataset.owner !== ownerId) {
          return;
        }
        root.hidden = false;
        body.textContent = `${body.textContent}${next}`.slice(-12000);
        body.scrollTop = body.scrollHeight;
      },
      set(text) {
        if (root.dataset.owner && root.dataset.owner !== ownerId) {
          return;
        }
        root.hidden = false;
        body.textContent = String(text ?? "");
        body.scrollTop = body.scrollHeight;
      },
      reset() {
        root.dataset.owner = ownerId;
        body.textContent = "";
        root.hidden = true;
      },
      hide() {
        if (root.dataset.owner && root.dataset.owner !== ownerId) {
          return;
        }
        delete root.dataset.owner;
        body.textContent = "";
        root.hidden = true;
      },
    };
  }

  function createStreamPreviewOverlay(ownerId = `stream-${Date.now()}-${Math.random().toString(16).slice(2)}`) {
    return createStreamPreview({ ownerId });
  }

  async function streamProblem({
    path,
    token,
    body,
    onStatus = null,
    onPartial = null,
    onPayload = null,
    onDone = null,
    onPreview = null,
    returnOnPayload = false,
    showPartialPreview = true,
    partialPreviewContainer = null,
    partialPreviewTitle = "AI 생성 스트림",
    partialPreviewSubtitle = "최종 렌더 전 초안",
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
    let partialDraftText = "";
    const partialPreview = showPartialPreview
      ? createStreamPreview({
          container: partialPreviewContainer,
          title: partialPreviewTitle,
          subtitle: partialPreviewSubtitle,
        })
      : null;
    partialPreview?.reset();
    const previewKind = inferPreviewKindFromPath(path);
    let earlyResolve;
    let earlyReject;
    let earlySettled = false;
    const earlyPayloadPromise = returnOnPayload
      ? new Promise((resolve, reject) => {
          earlyResolve = resolve;
          earlyReject = reject;
        })
      : null;

    const settleEarlySuccess = (payload) => {
      if (!returnOnPayload || earlySettled || payload === undefined) {
        return;
      }
      earlySettled = true;
      earlyResolve(payload);
    };

    const settleEarlyFailure = (error) => {
      if (!returnOnPayload || earlySettled) {
        return false;
      }
      earlySettled = true;
      earlyReject(error);
      return true;
    };

    const processEvent = (eventName, data) => {
      streamStarted = true;
      if (eventName === "status") {
        if (typeof onStatus === "function") onStatus(data);
        return;
      }
      if (eventName === "partial") {
        if (receivedPayload !== undefined) {
          return;
        }
        if (typeof onPartial === "function") onPartial(data);
        const previewText =
          data && typeof data === "object" ? data.delta || data.text || data.raw || "" : data || "";
        partialDraftText += String(previewText || "");
        if (typeof onPreview === "function") {
          const previewDraft = buildProblemPreviewDraft(partialDraftText, previewKind);
          onPreview(previewDraft, data);
        }
        if (partialPreview) {
          const fieldOnlyPreview =
            buildProblemPreviewText(partialDraftText, previewKind) || "AI가 문제 내용을 구성하는 중입니다.";
          partialPreview.set(fieldOnlyPreview);
        }
        return;
      }
      if (eventName === "payload") {
        receivedPayload = data && typeof data === "object" && "payload" in data ? data.payload : data;
        if (typeof onPayload === "function") onPayload(receivedPayload, data);
        settleEarlySuccess(receivedPayload);
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

    const readStream = async () => {
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
        if (receivedPayload !== undefined && returnOnPayload) {
          if (!donePayload && typeof onDone === "function") {
            onDone({
              ok: false,
              code: streamErrorPayload.code,
              httpStatus: streamErrorPayload.httpStatus,
              retryable: streamErrorPayload.retryable,
              message: streamErrorPayload.message || "문제 스트리밍 중 오류가 발생했습니다.",
            });
          }
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

      if (donePayload && donePayload.ok === false) {
        if (receivedPayload !== undefined && returnOnPayload) {
          return receivedPayload;
        }
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
        const isAbortError = trailingReadError?.name === "AbortError";
        if (typeof onDone === "function" && !donePayload) {
          onDone({
            ok: false,
            code: isAbortError ? STREAM_ERROR_CODES.STREAM_ABORTED : STREAM_ERROR_CODES.STREAM_NETWORK_ERROR,
            retryable: !isAbortError,
            message: trailingReadError?.message || "스트리밍 수신이 비정상적으로 종료되었습니다.",
          });
        }
        if (!returnOnPayload) {
          throw createStreamError(
            isAbortError ? STREAM_ERROR_CODES.STREAM_ABORTED : STREAM_ERROR_CODES.STREAM_NETWORK_ERROR,
            trailingReadError?.message || "스트리밍 수신이 비정상적으로 종료되었습니다.",
            {
              retryable: !isAbortError,
              streamStarted: true,
            }
          );
        }
      }
      return receivedPayload;
    };

    if (!returnOnPayload) {
      try {
        return await readStream();
      } finally {
        partialPreview?.hide();
      }
    }

    void readStream()
      .then((payload) => {
        settleEarlySuccess(payload);
      })
      .catch((error) => {
        if (!settleEarlyFailure(error)) {
          console.warn("Problem stream completed with trailing error.", error);
        }
      })
      .finally(() => {
        partialPreview?.hide();
      });

    return earlyPayloadPromise;
  }

  window.CodeProblemStream = {
    ERROR_CODES: STREAM_ERROR_CODES,
    sleep,
    isAbortError,
    shouldFallbackToJson,
    loadProblemTransport,
    typeText,
    revealLines,
    revealList,
    streamProblem,
    createStreamPreviewOverlay,
    createStreamPreview,
  };
})();

