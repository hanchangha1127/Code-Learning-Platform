const REFRESH_INTERVAL_MS = 3000;
const LOCALE = "ko-KR";

const palette = {
  text: "#27313d",
  grid: "rgba(40, 50, 60, 0.16)",
  users: "#2f80ed",
  clients: "#2f9e44",
  aiTotal: "#6f42c1",
  aiSuccess: "#2f9e44",
  aiFailure: "#c84545",
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
};

let adminKey = "";
setAdminKey(sessionStorage.getItem("admin_panel_key") || "");
if (!adminKey) {
  promptAdminKey("관리자 키를 입력하세요");
}

let refreshTimer = null;
const chartState = {
  users: null,
  aiUsage: null,
  aiLatency: null,
  requests: null,
};
let shutdownSupport = {
  supported: true,
  reason: "unknown",
  requiresSocketOverride: false,
  detail: "",
};

function setStatus(message, level = "ok") {
  els.statusText.textContent = message;
  els.statusBox.classList.remove("ok", "warn", "bad");
  els.statusBox.classList.add(level);
}

function setAdminKey(value) {
  adminKey = String(value || "").trim();
  if (adminKey) {
    sessionStorage.setItem("admin_panel_key", adminKey);
  } else {
    sessionStorage.removeItem("admin_panel_key");
  }
}

function promptAdminKey(message) {
  const entered = window.prompt(message, adminKey || "");
  if (entered === null) {
    return false;
  }
  setAdminKey(entered);
  return Boolean(adminKey);
}

function fmtNumber(value) {
  return Number(value || 0).toLocaleString(LOCALE);
}

function fmtPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
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
    const message =
      detail.detail ||
      detail.message ||
      payload?.message ||
      fallbackMessage;
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
    throw new Error("Chart.js 로딩에 실패했습니다.");
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
          {
            label: "전체 호출",
            data: [],
            backgroundColor: "rgba(111, 66, 193, 0.54)",
          },
          {
            label: "성공",
            data: [],
            backgroundColor: "rgba(47, 158, 68, 0.62)",
          },
          {
            label: "실패",
            data: [],
            backgroundColor: "rgba(200, 69, 69, 0.67)",
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
  els.aiSummary.textContent = `호출: ${fmtNumber(aiTotals.calls)} | 평균 지연: ${fmtNumber(aiTotals.avgLatencyMs)}ms | 처리 중: ${fmtNumber(metrics.ai?.inFlight)}`;

  const timestamp = metrics.generatedAt || new Date().toISOString();
  els.lastUpdated.textContent = `마지막 갱신: ${timestamp}`;
}

function updateShutdownSupport(metrics) {
  const shutdown = metrics?.admin?.shutdown || {};
  shutdownSupport = {
    supported: shutdown.supported !== false,
    reason: shutdown.reason || "unknown",
    requiresSocketOverride: Boolean(shutdown.requires_socket_override),
    detail: shutdown.detail || "",
  };

  if (els.shutdownBtn) {
    els.shutdownBtn.disabled = !shutdownSupport.supported;
    if (!shutdownSupport.supported) {
      els.shutdownBtn.title = shutdownSupport.detail || "현재 환경에서는 스택 종료를 지원하지 않습니다.";
    } else {
      els.shutdownBtn.title = "";
    }
  }
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

function renderMetrics(metrics) {
  updateCards(metrics);
  updateShutdownSupport(metrics);
  updateCharts(metrics);
  if (shutdownSupport.supported) {
    setStatus("실시간 모니터링 정상 동작 중", "ok");
  } else {
    const reason = shutdownSupport.detail || "현재 설정에서는 스택 안전 종료를 사용할 수 없습니다.";
    setStatus(`실시간 모니터링 정상 동작 중 | 종료 기능 제한: ${reason}`, "warn");
  }
}

async function fetchMetrics() {
  if (!adminKey) {
    setStatus("관리자 키가 없습니다.", "bad");
    return null;
  }

  const response = await fetch("/api/admin/metrics", {
    headers: {
      "X-Admin-Key": adminKey,
    },
    cache: "no-store",
  });
  const text = await response.text();
  const payload = parseJsonBody(text);

  if (!response.ok) {
    const fallback = response.status === 403
      ? "관리자 키가 올바르지 않습니다. 키를 확인해주세요."
      : response.status === 429
        ? "관리자 키 입력 시도가 너무 많습니다. 키를 다시 확인해주세요."
        : response.status === 503
          ? "관리자 API를 사용할 수 없습니다."
          : `메트릭 요청 실패 (${response.status})`;
    const { message, code } = extractErrorInfo(payload, fallback);
    const retryAfter = response.headers.get("Retry-After");
    let fullMessage = code ? `${message} [${code}]` : message;
    if (response.status === 429 && retryAfter) {
      fullMessage = `${fullMessage} (${retryAfter}초 후 재시도)`;
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
    if (!metrics) {
      return;
    }
    renderMetrics(metrics);
  } catch (error) {
    if (error?.status === 403 || error?.status === 429) {
      const retryPrompt = error.status === 429
        ? "관리자 키 입력 제한이 발생했습니다. 올바른 관리자 키를 다시 입력하세요."
        : "관리자 키가 올바르지 않습니다. 관리자 키를 다시 입력하세요.";

      if (promptAdminKey(retryPrompt)) {
        try {
          const retryMetrics = await fetchMetrics();
          if (retryMetrics) {
            renderMetrics(retryMetrics);
            return;
          }
        } catch (retryError) {
          error = retryError;
        }
      }
    }
    setStatus(String(error.message || error), "bad");
  }
}

async function shutdownStack() {
  if (!adminKey) {
    setStatus("관리자 키가 없습니다.", "bad");
    return;
  }

  if (!shutdownSupport.supported) {
    setStatus(
      shutdownSupport.detail || "현재 설정에서는 스택 안전 종료를 사용할 수 없습니다.",
      "warn"
    );
    return;
  }

  const ok = window.confirm("Docker 스택을 안전하게 종료할까요? 현재 접속이 끊어집니다.");
  if (!ok) {
    return;
  }

  els.shutdownBtn.disabled = true;
  setStatus("종료 요청을 전송하는 중...", "warn");

  try {
    const response = await fetch("/api/admin/shutdown", {
      method: "POST",
      headers: {
        "X-Admin-Key": adminKey,
      },
    });

    const text = await response.text();
    const payload = parseJsonBody(text);

    if (!response.ok) {
      const { message, code } = extractErrorInfo(payload, `종료 요청 실패 (${response.status})`);
      throw new Error(code ? `${message} [${code}]` : message);
    }

    const result = payload;
    setStatus(`${result.detail || "종료 요청이 접수되었습니다."} 서비스가 순차적으로 중지됩니다.`, "warn");
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

els.refreshBtn?.addEventListener("click", refresh);
els.shutdownBtn?.addEventListener("click", shutdownStack);

refresh();
startAutoRefresh();



