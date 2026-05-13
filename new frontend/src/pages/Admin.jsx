import { useCallback, useEffect, useState } from "react";
import { BrandIcon } from "../components/SvgIcon.jsx";
import { readJson } from "../lib/apiClient.js";
import { displayModeLabel } from "../lib/modeLabels.js";
const ADMIN_REFRESH_INTERVAL_MS = 3000;
const ADMIN_LOCALE = "ko-KR";
const ADMIN_CHART_COLORS = ["#2563eb", "#16a34a", "#dc2626", "#7c3aed"];

function encodeAdminKey(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function adminHeaders(key) {
  return { "X-Admin-Key-B64": encodeAdminKey(key) };
}

function fmtAdminNumber(value) {
  return Number(value || 0).toLocaleString(ADMIN_LOCALE);
}

function fmtAdminPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function fmtAdminDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(ADMIN_LOCALE, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function adminErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const code = detail.code ? ` [${detail.code}]` : "";
    return `${detail.detail || detail.message || fallback}${code}`;
  }
  return payload?.message || fallback;
}

async function adminRequest(path, { method = "GET", key } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: adminHeaders(key),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(adminErrorMessage(payload, `관리자 요청 실패 (${response.status})`));
  }
  return payload;
}

function shutdownMessage(shutdown = {}) {
  if (shutdown.detail) return shutdown.detail;
  switch (shutdown.reason) {
    case "docker_socket_not_mounted":
      return "Docker socket이 API 컨테이너에 연결되지 않아 스택 종료를 사용할 수 없습니다.";
    case "shutdown_targets_not_found":
      return "Compose 스택 컨테이너를 찾지 못했습니다.";
    case "shutdown_targets_incomplete":
      return "API 컨테이너만 감지되어 전체 스택 종료를 보장할 수 없습니다.";
    case "docker_control_unavailable":
      return "API 컨테이너에서 Docker daemon에 접근할 수 없습니다.";
    case "local_process_disabled":
      return "로컬 프로세스에서는 스택 종료를 사용할 수 없습니다.";
    case "disabled_by_config":
      return "관리자 종료 기능이 설정에서 비활성화되어 있습니다.";
    default:
      return "현재 설정에서는 스택 안전 종료를 사용할 수 없습니다.";
  }
}

function chartMax(series) {
  const values = series.flatMap((row) => row.values || []).map((value) => Number(value || 0));
  return Math.max(1, ...values);
}

function labelIndexes(labels) {
  const last = labels.length - 1;
  if (last <= 0) return labels.length ? [0] : [];
  return [...new Set([0, Math.floor(last / 2), last])];
}

function AdminLineChart({ id, labels = [], series = [], suffix = "" }) {
  const width = 640;
  const height = 230;
  const pad = { top: 18, right: 18, bottom: 36, left: 44 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const max = chartMax(series);
  const hasData = labels.length > 0 && series.some((row) => (row.values || []).some((value) => Number(value || 0) > 0));
  const xFor = (index) => pad.left + (labels.length <= 1 ? plotWidth / 2 : (index * plotWidth) / (labels.length - 1));
  const yFor = (value) => pad.top + plotHeight - (Number(value || 0) / max) * plotHeight;
  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg id={id} className="admin-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={id}>
      {gridLines.map((line) => {
        const y = pad.top + plotHeight * line;
        const value = Math.round(max * (1 - line));
        return (
          <g key={line}>
            <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="admin-chart-grid-line" />
            <text x={pad.left - 8} y={y + 4} className="admin-chart-axis" textAnchor="end">{value}{suffix}</text>
          </g>
        );
      })}
      <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} className="admin-chart-axis-line" />
      <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="admin-chart-axis-line" />
      {labelIndexes(labels).map((index) => (
        <text key={index} x={xFor(index)} y={height - 10} className="admin-chart-axis" textAnchor="middle">{labels[index]}</text>
      ))}
      {hasData ? series.map((row, index) => {
        const points = (row.values || []).map((value, pointIndex) => `${xFor(pointIndex)},${yFor(value)}`).join(" ");
        return <polyline key={row.label} points={points} fill="none" stroke={row.color || ADMIN_CHART_COLORS[index % ADMIN_CHART_COLORS.length]} className="admin-chart-line" />;
      }) : (
        <text x={width / 2} y={height / 2} className="admin-chart-empty" textAnchor="middle">표시할 데이터가 없습니다.</text>
      )}
    </svg>
  );
}

function AdminBarChart({ id, labels = [], series = [] }) {
  const width = 640;
  const height = 230;
  const pad = { top: 18, right: 18, bottom: 36, left: 44 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const max = chartMax(series);
  const groupCount = Math.max(labels.length, 1);
  const groupWidth = plotWidth / groupCount;
  const barWidth = Math.max(4, (groupWidth * 0.72) / Math.max(series.length, 1));
  const hasData = labels.length > 0 && series.some((row) => (row.values || []).some((value) => Number(value || 0) > 0));
  const yFor = (value) => pad.top + plotHeight - (Number(value || 0) / max) * plotHeight;

  return (
    <svg id={id} className="admin-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={id}>
      {[0, 0.25, 0.5, 0.75, 1].map((line) => {
        const y = pad.top + plotHeight * line;
        return <line key={line} x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="admin-chart-grid-line" />;
      })}
      <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="admin-chart-axis-line" />
      {hasData ? labels.map((label, labelIndex) => {
        const groupX = pad.left + labelIndex * groupWidth + groupWidth * 0.14;
        return (
          <g key={label}>
            {series.map((row, seriesIndex) => {
              const value = Number(row.values?.[labelIndex] || 0);
              const barHeight = height - pad.bottom - yFor(value);
              return (
                <rect
                  key={row.label}
                  x={groupX + seriesIndex * barWidth}
                  y={yFor(value)}
                  width={barWidth - 2}
                  height={Math.max(0, barHeight)}
                  rx="3"
                  fill={row.color || ADMIN_CHART_COLORS[seriesIndex % ADMIN_CHART_COLORS.length]}
                />
              );
            })}
          </g>
        );
      }) : (
        <text x={width / 2} y={height / 2} className="admin-chart-empty" textAnchor="middle">표시할 데이터가 없습니다.</text>
      )}
      {labelIndexes(labels).map((index) => (
        <text key={index} x={pad.left + index * groupWidth + groupWidth / 2} y={height - 10} className="admin-chart-axis" textAnchor="middle">{labels[index]}</text>
      ))}
    </svg>
  );
}

function AdminChartCard({ title, legend = [], children }) {
  return (
    <article className="card dashboard-panel admin-chart-card">
      <div className="admin-chart-head">
        <h3>{title}</h3>
        <div className="admin-chart-legend">
          {legend.map((item, index) => (
            <span key={item.label}><i style={{ background: item.color || ADMIN_CHART_COLORS[index % ADMIN_CHART_COLORS.length] }} />{item.label}</span>
          ))}
        </div>
      </div>
      <div className="admin-chart-wrap">{children}</div>
    </article>
  );
}

function AdminStatCard({ id, hintId, title, value, hint, tone = "blue" }) {
  return (
    <article className={`card dashboard-panel admin-stat-card tone-${tone}`}>
      <span>{title}</span>
      <strong id={id}>{value}</strong>
      <p id={hintId}>{hint}</p>
    </article>
  );
}

function SummaryMetric({ label, value }) {
  return <div className="admin-summary-metric"><span>{label}</span><strong>{fmtAdminNumber(value)}</strong></div>;
}

function SummaryList({ items, empty, renderItem }) {
  if (!items?.length) return <p className="summary-empty">{empty}</p>;
  return <ul className="summary-list">{items.map((item, index) => <li key={`${index}-${JSON.stringify(item)}`}>{renderItem(item)}</li>)}</ul>;
}

function ContentSummaryPanel({ summary = {} }) {
  const statusCounts = summary.statusCounts || {};
  const promptVersions = Array.isArray(summary.topPromptVersions) ? summary.topPromptVersions : [];
  const pendingProblems = Array.isArray(summary.recentPendingProblems) ? summary.recentPendingProblems : [];

  return (
    <section id="content-summary-panel" className="card dashboard-panel admin-summary-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>콘텐츠 운영 요약</h3>
          <p>prompt version, 검수 상태, 최근 pending 문제를 확인합니다.</p>
        </div>
      </div>
      <div className="admin-summary-metrics">
        <SummaryMetric label="추적 중인 문제" value={summary.totals} />
        <SummaryMetric label="pending" value={statusCounts.pending} />
        <SummaryMetric label="approved" value={statusCounts.approved} />
        <SummaryMetric label="hidden" value={statusCounts.hidden} />
      </div>
      <div className="admin-summary-columns">
        <section>
          <h4>상위 prompt version</h4>
          <SummaryList
            items={promptVersions}
            empty="아직 기록된 prompt version이 없습니다."
            renderItem={(item) => <><span>{item.version || "-"}</span><strong>{fmtAdminNumber(item.count)}</strong></>}
          />
        </section>
        <section>
          <h4>최근 pending 문제</h4>
          <SummaryList
            items={pendingProblems}
            empty="현재 pending 상태 문제는 없습니다."
            renderItem={(item) => (
              <>
                <div><strong>{item.title || "제목 없는 문제"}</strong><p>{item.mode || "-"} · {item.promptVersion || "버전 없음"}</p></div>
                <span>{fmtAdminDate(item.createdAt)}</span>
              </>
            )}
          />
        </section>
      </div>
    </section>
  );
}

function OpsEventsPanel({ summary = {} }) {
  const statusCounts = summary.statusCounts || {};
  const topEventTypes = Array.isArray(summary.topEventTypes) ? summary.topEventTypes : [];
  const modeSummary = Array.isArray(summary.modeSummary) ? summary.modeSummary : [];
  const latest = Array.isArray(summary.latest) ? summary.latest : [];

  return (
    <section id="ops-events-panel" className="card dashboard-panel admin-summary-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>운영 이벤트 요약</h3>
          <p>최근 {fmtAdminNumber(summary.windowHours || 24)}시간 이벤트 상태, 모드별 실패, 최신 이벤트를 확인합니다.</p>
        </div>
      </div>
      <div className="admin-summary-metrics">
        <SummaryMetric label="이벤트" value={summary.total} />
        <SummaryMetric label="success" value={statusCounts.success} />
        <SummaryMetric label="failure" value={statusCounts.failure} />
        <SummaryMetric label="review_required" value={statusCounts.review_required} />
      </div>
      <div className="admin-summary-columns">
        <section>
          <h4>이벤트 타입 상위</h4>
          <SummaryList
            items={topEventTypes}
            empty="최근 이벤트가 없습니다."
            renderItem={(item) => <><span>{item.eventType || "-"}</span><strong>{fmtAdminNumber(item.count)}</strong></>}
          />
        </section>
        <section>
          <h4>모드별 상태</h4>
          <SummaryList
            items={modeSummary}
            empty="최근 모드 이벤트가 없습니다."
            renderItem={(item) => (
              <>
                <span>{displayModeLabel(item.mode)}</span>
                <strong>호출 {fmtAdminNumber(item.total)} / 실패 {fmtAdminNumber(item.failure)} / {fmtAdminNumber(item.avgLatencyMs)}ms</strong>
              </>
            )}
          />
        </section>
      </div>
      <section className="latest-events">
        <h4>최신 이벤트</h4>
        <SummaryList
          items={latest}
          empty="표시할 최신 이벤트가 없습니다."
          renderItem={(item) => (
            <>
              <div><strong>{item.eventType || "event"}</strong><p>{displayModeLabel(item.mode)} · {item.status || "-"} · {item.requestId || "request id 없음"}</p></div>
              <span>{fmtAdminDate(item.createdAt)}</span>
            </>
          )}
        />
      </section>
    </section>
  );
}

function PlatformModesPanel({ platformModes = {} }) {
  const modes = platformModes.modes || {};
  const rows = Object.entries(modes).map(([mode, data]) => ({
    mode,
    problem: data.problem || {},
    submit: data.submit || {},
    background: data.submitBackground || {},
    dispatch: data.dispatch || {},
  }));
  const count = (value) => Number(value || 0);

  return (
    <section className="card dashboard-panel admin-summary-panel admin-platform-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>학습 모드 런타임</h3>
          <p>문제 생성, 제출, 큐 처리 상태를 모드별로 확인합니다.</p>
        </div>
        <span className="pill soft">처리 중 {fmtAdminNumber(platformModes.inFlight)}</span>
      </div>
      <div className="admin-mode-table" role="table" aria-label="학습 모드 런타임">
        <div role="row" className="admin-mode-table-head">
          <span role="columnheader">모드</span>
          <span role="columnheader">문제 생성</span>
          <span role="columnheader">제출</span>
          <span role="columnheader">큐</span>
        </div>
        {rows.length ? rows.map((row) => (
          <div role="row" className="admin-mode-table-row" key={row.mode}>
            <strong role="cell">{displayModeLabel(row.mode)}</strong>
            <span role="cell">{fmtAdminNumber(row.problem.calls)}회 · 실패 {fmtAdminNumber(row.problem.failure)}</span>
            <span role="cell">{fmtAdminNumber(count(row.submit.calls) + count(row.background.calls))}회 · 실패 {fmtAdminNumber(count(row.submit.failure) + count(row.background.failure))}</span>
            <span role="cell">queued {fmtAdminNumber(row.dispatch.queued)} / inline {fmtAdminNumber(row.dispatch.inline)}</span>
          </div>
        )) : <p className="summary-empty">아직 기록된 학습 모드 호출이 없습니다.</p>}
      </div>
    </section>
  );
}

export default function AdminPage() {
  const [key, setKey] = useState(window.sessionStorage.getItem("admin_panel_key") || "");
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState("메트릭 응답을 기다리는 중입니다.");
  const [statusLevel, setStatusLevel] = useState("warn");
  const [loading, setLoading] = useState(false);
  const [shutdownBusy, setShutdownBusy] = useState(false);

  const load = useCallback(async () => {
    const trimmedKey = key.trim();
    if (!trimmedKey) {
      setStatus("관리자 키를 입력해 주세요.");
      setStatusLevel("bad");
      return;
    }

    setLoading(true);
    try {
      const payload = await adminRequest("/api/admin/metrics", { key: trimmedKey });
      const shutdown = payload?.admin?.shutdown || {};
      setMetrics(payload);
      if (shutdown.supported === false) {
        setStatus(`메트릭은 정상 동작 중이지만 종료 기능은 제한됩니다. ${shutdownMessage(shutdown)}`);
        setStatusLevel("warn");
      } else {
        setStatus("관리자 메트릭과 백엔드 기능이 정상 동작 중입니다.");
        setStatusLevel("ok");
      }
    } catch (err) {
      setStatus(err.message || "관리자 메트릭을 불러오지 못했습니다.");
      setStatusLevel("bad");
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    if (!key.trim()) return undefined;
    load();
    const timer = window.setInterval(load, ADMIN_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [key, load]);

  async function shutdownStack() {
    const trimmedKey = key.trim();
    const shutdown = metrics?.admin?.shutdown || {};
    if (!trimmedKey) {
      setStatus("관리자 키를 입력해 주세요.");
      setStatusLevel("bad");
      return;
    }
    if (shutdown.supported === false) {
      setStatus(shutdownMessage(shutdown));
      setStatusLevel("warn");
      return;
    }

    const ok = window.confirm("Docker 스택을 안전하게 종료할까요? 현재 접속과 작업이 모두 중단됩니다.");
    if (!ok) return;

    setShutdownBusy(true);
    setStatus("종료 요청을 전송하는 중입니다...");
    setStatusLevel("warn");
    try {
      const payload = await adminRequest("/api/admin/shutdown", { method: "POST", key: trimmedKey });
      setStatus(`${payload.detail || "종료 요청이 접수되었습니다."} 서비스가 순차적으로 중지됩니다.`);
      setStatusLevel("warn");
    } catch (err) {
      setStatus(err.message || "종료 요청에 실패했습니다.");
      setStatusLevel("bad");
      setShutdownBusy(false);
    }
  }

  const aiTotals = metrics?.ai?.totals || {};
  const aiTimeline = metrics?.ai?.timeline || {};
  const userTimeline = metrics?.userTimeline || {};
  const requestTimeline = metrics?.requestsTimeline || {};
  const requestTotals = metrics?.requestTotals || {};
  const shutdown = metrics?.admin?.shutdown || {};
  const shutdownDisabled = shutdown.supported === false || shutdownBusy || loading;

  return (
    <section className="app dashboard-shell admin-shell">
      <header className="app-header page-header dashboard-topbar admin-topbar">
        <div className="brand-lockup">
          <span className="brand-mark"><BrandIcon /></span>
          <div>
            <p className="eyebrow">관리자</p>
            <h1>운영 현황</h1>
            <p>실시간 접속, AI 사용량, 콘텐츠 상태, 운영 이벤트를 확인합니다.</p>
          </div>
        </div>
        <div className="admin-topbar-actions">
          <span id="last-updated" className="pill soft">마지막 갱신: {fmtAdminDate(metrics?.generatedAt)}</span>
          <button id="refresh-btn" className="primary" type="button" onClick={load} disabled={loading}>{loading ? "갱신 중" : "지금 새로고침"}</button>
          <button id="shutdown-btn" className="ghost danger" type="button" onClick={shutdownStack} disabled={shutdownDisabled} title={shutdown.supported === false ? shutdownMessage(shutdown) : ""}>스택 안전 종료</button>
          <a className="ghost" href="/dashboard.html">대시보드</a>
        </div>
      </header>

      <main className="admin-main">
        <section className="card dashboard-panel admin-key-panel">
          <div>
            <h2>관리자 키</h2>
            <p>키는 이 브라우저 세션에만 저장됩니다.</p>
          </div>
          <div className="goal-form-row">
            <input id="admin-key" value={key} onChange={(event) => {
              const nextKey = event.target.value;
              setKey(nextKey);
              if (nextKey.trim()) window.sessionStorage.setItem("admin_panel_key", nextKey);
              else window.sessionStorage.removeItem("admin_panel_key");
            }} placeholder="관리자 패널 키" />
            <button id="admin-load" className="primary" type="button" onClick={load} disabled={loading}>지표 불러오기</button>
          </div>
        </section>

        <section className="admin-stat-grid" aria-live="polite">
          <AdminStatCard id="active-users" title="활성 사용자" value={fmtAdminNumber(metrics?.activeUsers)} hint="최근 활동 기준 사용자 수" tone="blue" />
          <AdminStatCard id="active-clients" title="활성 클라이언트" value={fmtAdminNumber(metrics?.activeClients)} hint="현재 접속 중인 클라이언트 수" tone="green" />
          <AdminStatCard id="inflight-requests" title="처리 중 요청" value={fmtAdminNumber(metrics?.inFlightRequests)} hint={`누적 요청 ${fmtAdminNumber(requestTotals.total)} · 오류율 ${fmtAdminPercent(requestTotals.errorRate)}`} tone="purple" />
          <AdminStatCard id="ai-success-rate" hintId="ai-summary" title="AI 성공률" value={fmtAdminPercent(aiTotals.successRate)} hint={`호출 ${fmtAdminNumber(aiTotals.calls)} · 평균 지연 ${fmtAdminNumber(aiTotals.avgLatencyMs)}ms · 처리 중 ${fmtAdminNumber(metrics?.ai?.inFlight)}`} tone="orange" />
        </section>

        <section className="admin-chart-grid">
          <AdminChartCard title="접속 추이" legend={[{ label: "활성 사용자", color: "#2563eb" }, { label: "활성 클라이언트", color: "#16a34a" }]}>
            <AdminLineChart id="users-chart" labels={userTimeline.labels || []} series={[
              { label: "활성 사용자", values: userTimeline.activeUsers || [], color: "#2563eb" },
              { label: "활성 클라이언트", values: userTimeline.activeClients || [], color: "#16a34a" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="분당 AI 사용량" legend={[{ label: "전체 호출", color: "#7c3aed" }, { label: "성공", color: "#16a34a" }, { label: "실패", color: "#dc2626" }]}>
            <AdminBarChart id="ai-usage-chart" labels={aiTimeline.labels || []} series={[
              { label: "전체 호출", values: aiTimeline.calls || [], color: "#7c3aed" },
              { label: "성공", values: aiTimeline.success || [], color: "#16a34a" },
              { label: "실패", values: aiTimeline.failure || [], color: "#dc2626" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="AI 평균 지연 시간 (ms)" legend={[{ label: "평균 지연", color: "#c37d12" }]}>
            <AdminLineChart id="ai-latency-chart" labels={aiTimeline.labels || []} series={[
              { label: "평균 지연", values: aiTimeline.avgLatencyMs || [], color: "#c37d12" },
            ]} />
          </AdminChartCard>
          <AdminChartCard title="요청 및 오류 추이" legend={[{ label: "요청 수", color: "#2563eb" }, { label: "오류 수", color: "#dc2626" }]}>
            <AdminLineChart id="request-chart" labels={requestTimeline.labels || []} series={[
              { label: "요청 수", values: requestTimeline.calls || [], color: "#2563eb" },
              { label: "오류 수", values: requestTimeline.errors || [], color: "#dc2626" },
            ]} />
          </AdminChartCard>
        </section>

        <section className="admin-summary-grid">
          <ContentSummaryPanel summary={metrics?.admin?.contentSummary || {}} />
          <OpsEventsPanel summary={metrics?.admin?.opsEvents || {}} />
        </section>
        <PlatformModesPanel platformModes={metrics?.platformModes || {}} />

        <section id="status-box" className={`status-row ${statusLevel}`}>
          <strong>상태:</strong>
          <span id="status-text">{status}</span>
        </section>
      </main>
    </section>
  );
}

