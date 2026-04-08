const REFRESH_INTERVAL_MS = 3000;
const LOCALE = "ko-KR";

const palette = {
  text: "#27313d",
  grid: "rgba(40, 50, 60, 0.16)",
  users: "#2f80ed",
  clients: "#2f9e44",
  aiLatency: "#c37d12",
  requests: "#2f80ed",
  errors: "#c84545",
};

const els = {
  activeUsers: document.getElementById("active-users"),
  activeClients: document.getElementById("active-clients"),
  inFlightRequests: document.getElementById("inflight-requests"),
  aiSuccessRate: document.getElementById("ai-success-rate"),
  aiSummary: document.getElementById("ai-summary"),
  lastUpdated: document.getElementById("last-updated"),
  statusText: document.getElementById("status-text"),
  statusBox: document.getElementById("status-box"),
  refreshBtn: document.getElementById("refresh-btn"),
  shutdownBtn: document.getElementById("shutdown-btn"),
  usersChart: document.getElementById("users-chart"),
  aiUsageChart: document.getElementById("ai-usage-chart"),
  aiLatencyChart: document.getElementById("ai-latency-chart"),
  requestChart: document.getElementById("request-chart"),
  contentSummaryPanel: document.getElementById("content-summary-panel"),
  opsEventsPanel: document.getElementById("ops-events-panel"),
};

let adminKey = "";
let refreshTimer = null;
let shutdownSupport = {
  supported: true,
  reason: "unknown",
  requiresSocketOverride: false,
  detail: "",
};

const chartState = {
  users: null,
  aiUsage: null,
  aiLatency: null,
  requests: null,
};

setAdminKey(window.sessionStorage.getItem("admin_panel_key") || "");
if (!adminKey) {
  promptAdminKey("관리자 키를 입력해 주세요.");
}

function setStatus(message, level = "ok") {
  if (!els.statusText || !els.statusBox) return;
  els.statusText.textContent = String(message || "");
  els.statusBox.classList.remove("ok", "warn", "bad");
  els.statusBox.classList.add(level);
}

function setAdminKey(value) {
  adminKey = String(value || "").trim();
  if (adminKey) {
    window.sessionStorage.setItem("admin_panel_key", adminKey);
  } else {
    window.sessionStorage.removeItem("admin_panel_key");
  }
}

function promptAdminKey(message) {
  const entered = window.prompt(message, adminKey || "");
  if (entered === null) return false;
  setAdminKey(entered);
  return Boolean(adminKey);
}

function createAdminHeaders() {
  return { "X-Admin-Key-B64": encodeAdminKey(adminKey) };
}

function encodeAdminKey(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fmtNumber(value) {
  return Number(value || 0).toLocaleString(LOCALE);
}

function fmtPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function fmtDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(LOCALE, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function parseJsonBody(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function extractErrorInfo(payload, fallbackMessage) {
  const detail = payload?.detail;
  if (typeof detail === "string") {
    return { message: detail, code: null };
  }
  if (detail && typeof detail === "object") {
    const code = detail.code ? String(detail.code) : null;
    const message = detail.detail || detail.message || payload?.message || fallbackMessage;
    return { message: String(message), code };
  }
  return {
    message: String(payload?.message || fallbackMessage),
    code: null,
  };
}

function chartScales(yPrecision = null) {
  const yTicks = { color: palette.text };
  if (yPrecision !== null) {
    yTicks.precision = yPrecision;
  }
  return {
    x: { ticks: { color: palette.text }, grid: { color: palette.grid } },
    y: { ticks: yTicks, grid: { color: palette.grid } },
  };
}

function ensureCharts() {
  if (!window.Chart) {
    throw new Error("Chart.js를 불러오지 못했습니다.");
  }

  if (!chartState.users) {
    chartState.users = new Chart(els.usersChart, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "활성 사용자",
            data: [],
            borderColor: palette.users,
            backgroundColor: "rgba(47, 128, 237, 0.16)",
            tension: 0.3,
            fill: true,
            pointRadius: 2,
          },
          {
            label: "활성 클라이언트",
            data: [],
            borderColor: palette.clients,
            backgroundColor: "rgba(47, 158, 68, 0.14)",
            tension: 0.3,
            fill: true,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: palette.text } } },
        scales: chartScales(0),
      },
    });
  }

  if (!chartState.aiUsage) {
    chartState.aiUsage = new Chart(els.aiUsageChart, {
      type: "bar",
      data: {
        labels: [],
        datasets: [
          { label: "전체 호출", data: [], backgroundColor: "rgba(111, 66, 193, 0.54)" },
          { label: "성공", data: [], backgroundColor: "rgba(47, 158, 68, 0.62)" },
          { label: "실패", data: [], backgroundColor: "rgba(200, 69, 69, 0.67)" },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: palette.text } } },
        scales: chartScales(0),
      },
    });
  }

  if (!chartState.aiLatency) {
    chartState.aiLatency = new Chart(els.aiLatencyChart, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "평균 지연 시간(ms)",
            data: [],
            borderColor: palette.aiLatency,
            backgroundColor: "rgba(195, 125, 18, 0.2)",
            tension: 0.25,
            fill: true,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: palette.text } } },
        scales: chartScales(),
      },
    });
  }

  if (!chartState.requests) {
    chartState.requests = new Chart(els.requestChart, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "요청 수",
            data: [],
            borderColor: palette.requests,
            backgroundColor: "rgba(47, 128, 237, 0.14)",
            tension: 0.3,
            fill: true,
            pointRadius: 2,
          },
          {
            label: "오류 수",
            data: [],
            borderColor: palette.errors,
            backgroundColor: "rgba(200, 69, 69, 0.14)",
            tension: 0.3,
            fill: true,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: palette.text } } },
        scales: chartScales(0),
      },
    });
  }
}

function updateCards(metrics) {
  els.activeUsers.textContent = fmtNumber(metrics.activeUsers);
  els.activeClients.textContent = fmtNumber(metrics.activeClients);
  els.inFlightRequests.textContent = fmtNumber(metrics.inFlightRequests);

  const aiTotals = metrics.ai?.totals || {};
  els.aiSuccessRate.textContent = fmtPercent(aiTotals.successRate);
  els.aiSummary.textContent = `호출 ${fmtNumber(aiTotals.calls)} | 평균 지연 ${fmtNumber(aiTotals.avgLatencyMs)}ms | 처리 중 ${fmtNumber(metrics.ai?.inFlight)}`;

  const timestamp = metrics.generatedAt || new Date().toISOString();
  els.lastUpdated.textContent = `마지막 갱신: ${fmtDate(timestamp)}`;
}

function getShutdownSupportMessage() {
  if (shutdownSupport.detail) {
    return shutdownSupport.detail;
  }

  switch (shutdownSupport.reason) {
    case "docker_socket_not_mounted":
      return "Docker socket이 API 컨테이너에 마운트되지 않아 스택 종료를 사용할 수 없습니다.";
    case "shutdown_targets_not_found":
      return "Compose 스택 컨테이너를 찾지 못해 스택 종료를 진행할 수 없습니다.";
    case "shutdown_targets_incomplete":
      return "API 컨테이너만 감지되어 전체 스택 종료를 보장할 수 없습니다.";
    case "docker_control_unavailable":
      return "API 컨테이너에서 Docker daemon에 접근할 수 없습니다.";
    case "docker_sdk_unavailable":
      return "API 컨테이너에 Docker SDK가 없어 스택 종료를 사용할 수 없습니다.";
    case "not_in_docker":
      return "현재 API가 Docker 밖에서 실행 중이어서 스택 종료를 사용할 수 없습니다.";
    default:
      return "현재 설정에서는 스택 안전 종료를 사용할 수 없습니다.";
  }
}

function updateShutdownSupport(metrics) {
  const shutdown = metrics?.admin?.shutdown || {};
  shutdownSupport = {
    supported: shutdown.supported !== false,
    reason: shutdown.reason || "unknown",
    requiresSocketOverride: Boolean(shutdown.requires_socket_override),
    detail: shutdown.detail || "",
  };

  if (!els.shutdownBtn) return;
  els.shutdownBtn.disabled = !shutdownSupport.supported;
  els.shutdownBtn.title = shutdownSupport.supported ? "" : getShutdownSupportMessage();
}

function updateCharts(metrics) {
  ensureCharts();

  const userTimeline = metrics.userTimeline || { labels: [], activeUsers: [], activeClients: [] };
  chartState.users.data.labels = userTimeline.labels || [];
  chartState.users.data.datasets[0].data = userTimeline.activeUsers || [];
  chartState.users.data.datasets[1].data = userTimeline.activeClients || [];
  chartState.users.update();

  const aiTimeline = metrics.ai?.timeline || { labels: [], calls: [], success: [], failure: [], avgLatencyMs: [] };
  chartState.aiUsage.data.labels = aiTimeline.labels || [];
  chartState.aiUsage.data.datasets[0].data = aiTimeline.calls || [];
  chartState.aiUsage.data.datasets[1].data = aiTimeline.success || [];
  chartState.aiUsage.data.datasets[2].data = aiTimeline.failure || [];
  chartState.aiUsage.update();

  chartState.aiLatency.data.labels = aiTimeline.labels || [];
  chartState.aiLatency.data.datasets[0].data = aiTimeline.avgLatencyMs || [];
  chartState.aiLatency.update();

  const requestTimeline = metrics.requestsTimeline || { labels: [], calls: [], errors: [] };
  chartState.requests.data.labels = requestTimeline.labels || [];
  chartState.requests.data.datasets[0].data = requestTimeline.calls || [];
  chartState.requests.data.datasets[1].data = requestTimeline.errors || [];
  chartState.requests.update();
}

function renderContentSummary(summary) {
  if (!els.contentSummaryPanel) return;
  const data = summary || {};
  const statusCounts = data.statusCounts || {};
  const promptVersions = Array.isArray(data.topPromptVersions) ? data.topPromptVersions : [];
  const pendingProblems = Array.isArray(data.recentPendingProblems) ? data.recentPendingProblems : [];

  els.contentSummaryPanel.innerHTML = `
    <div class="summary-metrics">
      <div class="summary-metric">
        <span>추적 중인 문제</span>
        <strong>${fmtNumber(data.totals)}</strong>
      </div>
      <div class="summary-metric">
        <span>pending</span>
        <strong>${fmtNumber(statusCounts.pending)}</strong>
      </div>
      <div class="summary-metric">
        <span>approved</span>
        <strong>${fmtNumber(statusCounts.approved)}</strong>
      </div>
      <div class="summary-metric">
        <span>hidden</span>
        <strong>${fmtNumber(statusCounts.hidden)}</strong>
      </div>
    </div>
    <div class="summary-columns">
      <section>
        <h4>상위 prompt version</h4>
        ${promptVersions.length ? `
          <ul class="summary-list">
            ${promptVersions.map((item) => `<li><span>${escapeHtml(item.version)}</span><strong>${fmtNumber(item.count)}</strong></li>`).join("")}
          </ul>
        ` : '<p class="summary-empty">아직 기록된 prompt version이 없습니다.</p>'}
      </section>
      <section>
        <h4>최근 pending 문제</h4>
        ${pendingProblems.length ? `
          <ul class="summary-list summary-problem-list">
            ${pendingProblems.map((item) => `
              <li>
                <div>
                  <strong>${escapeHtml(item.title || "제목 없는 문제")}</strong>
                  <p>${escapeHtml(item.mode || "-")} | ${escapeHtml(item.promptVersion || "버전 없음")}</p>
                </div>
                <span>${escapeHtml(fmtDate(item.createdAt))}</span>
              </li>
            `).join("")}
          </ul>
        ` : '<p class="summary-empty">현재 pending 상태 문제는 없습니다.</p>'}
      </section>
    </div>
  `;
}

function renderOpsEvents(summary) {
  if (!els.opsEventsPanel) return;
  const data = summary || {};
  const statusCounts = data.statusCounts || {};
  const topEventTypes = Array.isArray(data.topEventTypes) ? data.topEventTypes : [];
  const modeSummary = Array.isArray(data.modeSummary) ? data.modeSummary : [];
  const latest = Array.isArray(data.latest) ? data.latest : [];

  els.opsEventsPanel.innerHTML = `
    <div class="summary-metrics">
      <div class="summary-metric">
        <span>최근 ${fmtNumber(data.windowHours || 24)}시간 이벤트</span>
        <strong>${fmtNumber(data.total)}</strong>
      </div>
      <div class="summary-metric">
        <span>success</span>
        <strong>${fmtNumber(statusCounts.success)}</strong>
      </div>
      <div class="summary-metric">
        <span>failure</span>
        <strong>${fmtNumber(statusCounts.failure)}</strong>
      </div>
      <div class="summary-metric">
        <span>review_required</span>
        <strong>${fmtNumber(statusCounts.review_required)}</strong>
      </div>
    </div>
    <div class="summary-columns">
      <section>
        <h4>이벤트 타입 상위</h4>
        ${topEventTypes.length ? `
          <ul class="summary-list">
            ${topEventTypes.map((item) => `<li><span>${escapeHtml(item.eventType)}</span><strong>${fmtNumber(item.count)}</strong></li>`).join("")}
          </ul>
        ` : '<p class="summary-empty">최근 이벤트가 없습니다.</p>'}
      </section>
      <section>
        <h4>모드별 상태</h4>
        ${modeSummary.length ? `
          <ul class="summary-list">
            ${modeSummary.map((item) => `
              <li>
                <span>${escapeHtml(item.mode)}</span>
                <strong>호출 ${fmtNumber(item.total)} / 실패 ${fmtNumber(item.failure)} / ${fmtNumber(item.avgLatencyMs)}ms</strong>
              </li>
            `).join("")}
          </ul>
        ` : '<p class="summary-empty">최근 모드 이벤트가 없습니다.</p>'}
      </section>
    </div>
    <section class="latest-events">
      <h4>최신 이벤트</h4>
      ${latest.length ? `
        <ul class="summary-list latest-event-list">
          ${latest.map((item) => `
            <li>
              <div>
                <strong>${escapeHtml(item.eventType || "event")}</strong>
                <p>${escapeHtml(item.mode || "-")} | ${escapeHtml(item.status || "-")} | ${escapeHtml(item.requestId || "request id 없음")}</p>
              </div>
              <span>${escapeHtml(fmtDate(item.createdAt))}</span>
            </li>
          `).join("")}
        </ul>
      ` : '<p class="summary-empty">표시할 최신 이벤트가 없습니다.</p>'}
    </section>
  `;
}

function renderMetrics(metrics) {
  updateCards(metrics);
  updateShutdownSupport(metrics);
  updateCharts(metrics);
  renderContentSummary(metrics?.admin?.contentSummary || {});
  renderOpsEvents(metrics?.admin?.opsEvents || {});

  if (shutdownSupport.supported) {
    setStatus("관리자 메트릭과 백엔드 기능이 정상 동작 중입니다.", "ok");
  } else {
    setStatus(`메트릭은 정상 동작 중이지만 종료 기능은 제한됩니다. ${getShutdownSupportMessage()}`, "warn");
  }
}

async function fetchMetrics() {
  if (!adminKey) {
    setStatus("관리자 키가 없습니다.", "bad");
    return null;
  }

  const response = await fetch("/api/admin/metrics", {
    headers: createAdminHeaders(),
    cache: "no-store",
  });
  const text = await response.text();
  const payload = parseJsonBody(text);

  if (!response.ok) {
    const fallback = response.status === 403
      ? "관리자 키가 올바르지 않습니다."
      : response.status === 429
        ? "관리자 키 입력 시도가 너무 많습니다."
        : response.status === 503
          ? "관리자 API를 사용할 수 없습니다."
          : `메트릭 요청 실패 (${response.status})`;
    const { message, code } = extractErrorInfo(payload, fallback);
    const retryAfter = response.headers.get("Retry-After");
    let fullMessage = code ? `${message} [${code}]` : message;
    if (response.status === 429 && retryAfter) {
      fullMessage = `${fullMessage} (${retryAfter}초 후 다시 시도)`;
    }
    const error = new Error(fullMessage);
    error.status = response.status;
    error.code = code;
    throw error;
  }

  return payload;
}

async function refresh() {
  try {
    const metrics = await fetchMetrics();
    if (!metrics) return;
    renderMetrics(metrics);
  } catch (error) {
    let currentError = error;

    if (currentError?.status === 403 || currentError?.status === 429) {
      const retryPrompt = currentError.status === 429
        ? "관리자 키 입력 제한이 발생했습니다. 올바른 관리자 키를 다시 입력해 주세요."
        : "관리자 키가 올바르지 않습니다. 관리자 키를 다시 입력해 주세요.";

      if (promptAdminKey(retryPrompt)) {
        try {
          const retryMetrics = await fetchMetrics();
          if (retryMetrics) {
            renderMetrics(retryMetrics);
            return;
          }
        } catch (retryError) {
          currentError = retryError;
        }
      }
    }

    setStatus(String(currentError.message || currentError), "bad");
  }
}

async function shutdownStack() {
  if (!adminKey) {
    setStatus("관리자 키가 없습니다.", "bad");
    return;
  }
  if (!shutdownSupport.supported) {
    setStatus(getShutdownSupportMessage(), "warn");
    return;
  }

  const ok = window.confirm("Docker 스택을 안전하게 종료할까요? 현재 접속과 작업이 모두 중단됩니다.");
  if (!ok) return;

  els.shutdownBtn.disabled = true;
  setStatus("종료 요청을 전송하는 중입니다...", "warn");

  try {
    const response = await fetch("/api/admin/shutdown", {
      method: "POST",
      headers: createAdminHeaders(),
    });
    const text = await response.text();
    const payload = parseJsonBody(text);

    if (!response.ok) {
      const { message, code } = extractErrorInfo(payload, `종료 요청 실패 (${response.status})`);
      throw new Error(code ? `${message} [${code}]` : message);
    }

    setStatus(`${payload.detail || "종료 요청이 접수되었습니다."} 서비스가 순차적으로 중지됩니다.`, "warn");
  } catch (error) {
    setStatus(String(error.message || error), "bad");
    els.shutdownBtn.disabled = false;
    return;
  }

  window.setTimeout(() => {
    window.location.reload();
  }, 6000);
}

function startAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
  refreshTimer = window.setInterval(refresh, REFRESH_INTERVAL_MS);
}

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

els.refreshBtn?.addEventListener("click", refresh);
els.shutdownBtn?.addEventListener("click", shutdownStack);

refresh();
startAutoRefresh();

