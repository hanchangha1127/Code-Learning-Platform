import { useCallback, useEffect, useRef, useState } from "react";
import { ModeIcon } from "../components/SvgIcon.jsx";
import { AppShell, LoadingScreen } from "../components/AppShell.jsx";
import { apiRequest, useSessionGuard } from "../lib/apiClient.js";
import { displayModeLabel } from "../lib/modeLabels.js";
import { languageTitle } from "../lib/learningSettings.js";

function displayLanguage(value, fallback = "-") {
  return languageTitle(value || fallback);
}

function modeSolveLink(mode, problemId) {
  const links = {
    analysis: "/analysis.html",
    "code-block": "/codeblock.html",
    "code-arrange": "/arrange.html",
    auditor: "/auditor.html",
    "refactoring-choice": "/refactoring-choice.html",
    "code-blame": "/code-blame.html",
    "single-file-analysis": "/single-file-analysis.html",
    "multi-file-analysis": "/multi-file-analysis.html",
    "fullstack-analysis": "/fullstack-analysis.html",
  };
  const page = links[String(mode || "").trim().toLowerCase()] || "/analysis.html";
  return `${page}?bank_problem=${encodeURIComponent(problemId)}`;
}
const PROBLEM_BANK_LIMIT = 30;
const PROBLEM_BANK_MODES = [
  "analysis",
  "code-block",
  "code-arrange",
  "auditor",
  "refactoring-choice",
  "code-blame",
  "single-file-analysis",
  "multi-file-analysis",
  "fullstack-analysis",
];

function difficultyLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "easy" || normalized === "beginner") return "초급";
  if (normalized === "medium" || normalized === "intermediate") return "중급";
  if (normalized === "hard" || normalized === "advanced") return "고급";
  return value || "-";
}

function myProblemStatusLabel(value) {
  if (value === "solved") return "해결";
  if (value === "tried") return "시도";
  return "미풀이";
}

function problemBankSummary(payload) {
  return payload?.summary || {
    total_problems: Number(payload?.total || 0),
    total_submissions: 0,
    solved_count: 0,
    tried_count: 0,
    average_success_rate: null,
  };
}

export default function ProblemBankPage() {
  const ready = useSessionGuard();
  const [filters, setFilters] = useState({ q: "", mode: "", language: "", difficulty: "", myStatus: "" });
  const [page, setPage] = useState(0);
  const [payload, setPayload] = useState({ items: [], total: 0, limit: PROBLEM_BANK_LIMIT, offset: 0, summary: problemBankSummary() });
  const [status, setStatus] = useState("문제 목록을 불러오는 중입니다.");
  const [loading, setLoading] = useState(false);
  const requestSeqRef = useRef(0);

  const loadProblems = useCallback(async (signal) => {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PROBLEM_BANK_LIMIT),
      offset: String(page * PROBLEM_BANK_LIMIT),
    });
    if (filters.q.trim()) params.set("q", filters.q.trim());
    if (filters.mode) params.set("mode", filters.mode);
    if (filters.language.trim()) params.set("language", filters.language.trim());
    if (filters.difficulty) params.set("difficulty", filters.difficulty);
    if (filters.myStatus) params.set("my_status", filters.myStatus);

    try {
      const nextPayload = await apiRequest(`/platform/problem-bank?${params.toString()}`, { signal });
      if (requestSeq !== requestSeqRef.current) return;
      setPayload({
        items: Array.isArray(nextPayload.items) ? nextPayload.items : [],
        total: Number(nextPayload.total || 0),
        limit: Number(nextPayload.limit || PROBLEM_BANK_LIMIT),
        offset: Number(nextPayload.offset || 0),
        summary: problemBankSummary(nextPayload),
      });
      setStatus("");
    } catch (error) {
      if (error?.name === "AbortError" || requestSeq !== requestSeqRef.current) return;
      setPayload({ items: [], total: 0, limit: PROBLEM_BANK_LIMIT, offset: 0, summary: problemBankSummary() });
      setStatus(error.message || "문제 목록을 불러오지 못했습니다.");
    } finally {
      if (requestSeq === requestSeqRef.current) setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    if (!ready) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(() => loadProblems(controller.signal), 120);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [ready, loadProblems]);

  if (!ready) return <LoadingScreen />;

  const totalPages = Math.max(1, Math.ceil((payload.total || 0) / PROBLEM_BANK_LIMIT));
  const currentPage = page + 1;
  const summary = problemBankSummary(payload);
  const hasFilters = Object.values(filters).some((value) => String(value || "").trim());
  const emptyText = hasFilters
    ? "조건에 맞는 문제가 없습니다. 필터를 줄여서 다시 확인하세요."
    : "아직 공개된 제출 문제가 없습니다. 학습 모드에서 문제를 풀고 제출하면 이곳에 자동으로 쌓입니다.";

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(0);
  }

  return (
    <AppShell active="problems" title="문제" subtitle="Problem Bank">
      <main id="problem-bank-page" className="problem-bank-page">
        <section className="card dashboard-panel problem-bank-hero">
          <div>
            <p className="dashboard-section-label">공개 문제 목록</p>
            <h2>다른 학습자가 풀었던 문제를 다시 풀어보세요.</h2>
            <p>제출된 문제 본문만 공개되며 정답과 채점 기준은 노출하지 않습니다.</p>
          </div>
          <div className="problem-bank-metrics" aria-label="문제은행 요약">
            <span className="problem-bank-metric">
              <small>문제</small>
              <strong id="problem-bank-total">{summary.total_problems}</strong>
            </span>
            <span className="problem-bank-metric">
              <small>제출</small>
              <strong>{summary.total_submissions}</strong>
            </span>
            <span className="problem-bank-metric">
              <small>성공률</small>
              <strong>{summary.average_success_rate === null || summary.average_success_rate === undefined ? "-" : `${summary.average_success_rate}%`}</strong>
            </span>
          </div>
        </section>

        <section className="card dashboard-panel problem-bank-filters" aria-label="문제 필터">
          <input
            id="problem-bank-search"
            value={filters.q}
            onChange={(event) => updateFilter("q", event.target.value)}
            placeholder="제목 또는 설명 검색"
          />
          <select id="problem-bank-mode" value={filters.mode} onChange={(event) => updateFilter("mode", event.target.value)}>
            <option value="">전체 모드</option>
            {PROBLEM_BANK_MODES.map((mode) => <option key={mode} value={mode}>{displayModeLabel(mode)}</option>)}
          </select>
          <input
            id="problem-bank-language"
            value={filters.language}
            onChange={(event) => updateFilter("language", event.target.value)}
            placeholder="언어"
          />
          <select id="problem-bank-difficulty" value={filters.difficulty} onChange={(event) => updateFilter("difficulty", event.target.value)}>
            <option value="">전체 난이도</option>
            <option value="easy">초급</option>
            <option value="medium">중급</option>
            <option value="hard">고급</option>
          </select>
          <select id="problem-bank-my-status" value={filters.myStatus} onChange={(event) => updateFilter("myStatus", event.target.value)}>
            <option value="">내 상태 전체</option>
            <option value="unsolved">미풀이</option>
            <option value="tried">시도</option>
            <option value="solved">해결</option>
          </select>
        </section>

        <section className="card dashboard-panel problem-bank-table-card">
          <div className="dashboard-panel-head">
            <div>
              <h3>문제 목록</h3>
              <p>{loading ? "불러오는 중입니다." : status || `${payload.items.length}개 표시 중 · 내 해결 ${summary.solved_count}개 · 시도 ${summary.tried_count}개`}</p>
            </div>
          </div>
          <div className="problem-bank-table-wrap">
            <table id="problem-bank-table" className="problem-bank-table">
              <thead>
                <tr>
                  <th>번호</th>
                  <th>제목</th>
                  <th>모드</th>
                  <th>언어</th>
                  <th>난이도</th>
                  <th>제출</th>
                  <th>성공률</th>
                  <th>내 상태</th>
                  <th>최근 등록일</th>
                </tr>
              </thead>
              <tbody>
                {payload.items.length === 0 ? (
                  <tr><td colSpan="9" className="problem-bank-empty">{status || emptyText}</td></tr>
                ) : payload.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td><a className="problem-bank-title-link" href={item.solve_link || modeSolveLink(item.mode, item.id)}>{item.title}</a></td>
                    <td>
                      <span className="problem-bank-mode-chip">
                        <ModeIcon type={item.mode} />
                        {item.mode_label || displayModeLabel(item.mode)}
                      </span>
                    </td>
                    <td>{displayLanguage(item.language)}</td>
                    <td>{difficultyLabel(item.difficulty)}</td>
                    <td>{item.submissions}</td>
                    <td>{item.success_rate === null || item.success_rate === undefined ? "-" : `${item.success_rate}%`}</td>
                    <td><span className={`problem-status-pill status-${item.my_status || "unsolved"}`}>{myProblemStatusLabel(item.my_status)}</span></td>
                    <td>{item.updated_at ? new Date(item.updated_at).toLocaleDateString("ko-KR") : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="problem-bank-pagination">
            <button className="ghost" type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page <= 0}>이전</button>
            <span id="problem-bank-page-label">{currentPage} / {totalPages}</span>
            <button className="ghost" type="button" onClick={() => setPage((value) => Math.min(totalPages - 1, value + 1))} disabled={currentPage >= totalPages}>다음</button>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

