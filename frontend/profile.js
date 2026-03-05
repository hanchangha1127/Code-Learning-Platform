const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";
const LANGUAGE_KEY = "code-learning-language";
const DIFFICULTY_KEY = "code-learning-difficulty";
const DEFAULT_LANGUAGE = "python";
const DEFAULT_DIFFICULTY = "beginner";
const DEFAULT_TOAST_DURATION = 3200;

const DIFFICULTY_OPTIONS = [
  { id: "beginner", label: "초급" },
  { id: "intermediate", label: "중급" },
  { id: "advanced", label: "고급" },
];
const MODE_LABELS = {
  diagnostic: "진단",
  practice: "맞춤 문제",
  "code-block": "빈칸 채우기",
  "code-calc": "코드 계산",
  "code-error": "오류 찾기",
  "code-arrange": "코드 정렬",
  auditor: "감사관 모드",
  "context-inference": "맥락 추론",
  "refactoring-choice": "최적의 선택",
  "code-blame": "범인 찾기",
};
const LANGUAGE_LABELS = {
  python: "파이썬",
  javascript: "자바스크립트",
  c: "C",
  java: "자바",
};

const state = {
  token: null,
  username: "",
  displayName: "",
  languages: [],
  selectedLanguage: DEFAULT_LANGUAGE,
  difficulty: DEFAULT_DIFFICULTY,
  toastTimer: null,
};

const apiRequest = window.CodeApiClient.create({
  getToken: () => state.token,
  authClient,
  defaultErrorMessage: "요청을 처리하지 못했습니다.",
});


const elements = {};

function normalizeText(value) {
  if (value === undefined || value === null) return "";
  return String(value).trim();
}

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeText(value, fallback = "") {
  const normalized = normalizeText(value);
  if (normalized) return escapeHtml(normalized);
  return fallback ? escapeHtml(fallback) : "";
}

function escapeList(values, fallback = "-", separator = ", ") {
  const items = Array.isArray(values)
    ? values.map((value) => normalizeText(value)).filter((value) => value.length > 0)
    : [];
  if (!items.length) return escapeHtml(fallback);
  return items.map((value) => escapeHtml(value)).join(separator);
}

function cacheDom() {
  elements.profileName = document.getElementById("profile-name");
  elements.profileTier = document.getElementById("profile-tier");
  elements.profileAvatar = document.getElementById("profile-avatar");
  elements.wrongNoteBtn = document.getElementById("btn-wrong-note");
  elements.reportBtn = document.getElementById("btn-report");
  elements.logoutBtn = document.getElementById("btn-logout");
  elements.languageSetting = document.getElementById("language-setting");
  elements.difficultySetting = document.getElementById("difficulty-setting");
  elements.toast = document.getElementById("toast");
  elements.modal = document.getElementById("modal");
  elements.modalTitle = document.getElementById("modal-title");
  elements.modalBody = document.getElementById("modal-body");
  elements.modalClose = document.getElementById("modal-close");
}

function init() {
  cacheDom();
  state.token = window.localStorage.getItem(TOKEN_KEY);
  if (!state.token) {
    window.location.href = "/index.html";
    return;
  }
  state.username = parseUsername(state.token);
  state.difficulty = getSavedDifficulty();
  renderUserInfo();
  bindEvents();
  loadLanguages();
  renderDifficultyOptions();
  loadProfile();
  loadUserInfo();
}

function bindEvents() {
  elements.wrongNoteBtn?.addEventListener("click", openWrongNote);
  elements.reportBtn?.addEventListener("click", openReportModal);
  elements.logoutBtn?.addEventListener("click", handleLogout);
  elements.modalClose?.addEventListener("click", hideModal);
  elements.modal?.addEventListener("click", (event) => {
    if (event.target === elements.modal) hideModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideModal();
  });
}

function renderUserInfo() {
  const label = state.displayName || state.username || "사용자";
  if (elements.profileName) elements.profileName.textContent = label;
  if (elements.profileAvatar) {
    elements.profileAvatar.textContent = "";
  }
}

async function loadUserInfo() {
  try {
    const data = await apiRequest("/api/me");
    state.username = data.username || state.username;
    state.displayName = data.display_name || data.displayName || state.username;
    if (state.displayName) {
      window.localStorage.setItem(DISPLAY_NAME_KEY, state.displayName);
    }
    renderUserInfo();
  } catch {
    // Ignore and keep fallback from token
  }
}

async function loadProfile() {
  try {
    const profile = await apiRequest("/api/profile");
    const skillLevel = profile.skillLevel || "beginner";
    if (elements.profileTier) {
      elements.profileTier.textContent = `티어: ${formatSkillLabel(skillLevel)}`;
    }
  } catch (err) {
    if (elements.profileTier) {
      elements.profileTier.textContent = "티어: -";
    }
  }
}

async function loadLanguages() {
  if (!elements.languageSetting) return;
  elements.languageSetting.innerHTML = '<span class="empty">언어 목록을 불러오는 중...</span>';
  try {
    const payload = await apiRequest("/api/languages");
    state.languages = payload.languages || [];
    state.selectedLanguage = getSavedLanguage(state.languages);
    renderLanguageOptions();
  } catch (err) {
    elements.languageSetting.innerHTML = '<span class="empty">언어를 불러오지 못했습니다.</span>';
  }
}

function renderLanguageOptions() {
  if (!elements.languageSetting) return;
  elements.languageSetting.innerHTML = "";
  if (!state.languages.length) {
    elements.languageSetting.innerHTML = '<span class="empty">언어가 없습니다.</span>';
    return;
  }
  state.languages.forEach((lang) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill";
    button.dataset.value = lang.id;
    button.textContent = lang.title || lang.id;
    button.classList.toggle("active", lang.id === state.selectedLanguage);
    button.addEventListener("click", () => {
      setLanguage(lang.id);
    });
    elements.languageSetting.appendChild(button);
  });
}

function formatSkillLabel(level) {
  switch (level) {
    case "advanced":
      return "고급";
    case "intermediate":
      return "중급";
    case "beginner":
    default:
      return "초급";
  }
}

function renderDifficultyOptions() {
  if (!elements.difficultySetting) return;
  elements.difficultySetting.innerHTML = "";
  DIFFICULTY_OPTIONS.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill";
    button.dataset.value = option.id;
    button.textContent = option.label;
    button.classList.toggle("active", option.id === state.difficulty);
    button.addEventListener("click", () => {
      setDifficulty(option.id);
    });
    elements.difficultySetting.appendChild(button);
  });
}

function setLanguage(value) {
  const isValid = state.languages.some((lang) => lang.id === value);
  state.selectedLanguage = isValid ? value : DEFAULT_LANGUAGE;
  window.localStorage.setItem(LANGUAGE_KEY, state.selectedLanguage);
  renderLanguageOptions();
  showToast("언어 설정이 저장되었습니다.");
}

function setDifficulty(value) {
  const isValid = DIFFICULTY_OPTIONS.some((option) => option.id === value);
  state.difficulty = isValid ? value : DEFAULT_DIFFICULTY;
  window.localStorage.setItem(DIFFICULTY_KEY, state.difficulty);
  renderDifficultyOptions();
  showToast("난이도 설정이 저장되었습니다.");
}

function getSavedLanguage(languages = []) {
  const saved = window.localStorage.getItem(LANGUAGE_KEY);
  if (saved && languages.some((lang) => lang.id === saved)) {
    return saved;
  }
  const fallback = languages[0]?.id || DEFAULT_LANGUAGE;
  if (fallback) {
    window.localStorage.setItem(LANGUAGE_KEY, fallback);
  }
  return fallback;
}

function getSavedDifficulty() {
  const value = window.localStorage.getItem(DIFFICULTY_KEY);
  if (DIFFICULTY_OPTIONS.some((option) => option.id === value)) {
    return value;
  }
  return DEFAULT_DIFFICULTY;
}

async function openWrongNote() {
  try {
    const payload = await apiRequest("/api/learning/history");
    const list = (payload.history || []).filter((item) => item.correct === false);
    if (list.length === 0) {
      showModal("오답 노트", '<p class="empty">틀린 기록이 없습니다.</p>');
      return;
    }
    const items = list.map((item) => renderWrongNoteItem(item)).join("");
    showModal("오답 노트", `<ul class="list history-list">${items}</ul>`);
  } catch (error) {
    showModal("오답 노트", `<p class="empty">${escapeText(error.message, "기록을 불러오지 못했습니다.")}</p>`);
  }
}

function renderWrongNoteItem(item) {
  const modeLabel = formatModeLabel(item.mode);
  const modeKey = item.mode || "practice";
  const summaryText = escapeText(item.summary || modeLabel || "요약 없음", "요약 없음");
  const metaParts = [];
  if (item.language) metaParts.push(`언어: ${formatLanguageLabel(item.language)}`);
  if (item.difficulty) metaParts.push(`난이도: ${formatDifficultyLabel(item.difficulty)}`);
  const metaHtml = metaParts.length
    ? `<p><strong>설정:</strong> ${metaParts.map((part) => escapeHtml(part)).join(" · ")}</p>`
    : "";
  const showRawCode = !["code-error", "code-arrange"].includes(modeKey);
  const codeHtml = showRawCode && item.problem_code
    ? `<div class="code-block"><pre><code>${escapeHtml(item.problem_code)}</code></pre></div>`
    : "";
  const promptHtml = item.problem_prompt
    ? `<p><strong>질문:</strong> ${escapeText(item.problem_prompt)}</p>`
    : "";
  const modeHtml = buildModeDetail(item);
  const feedbackSummary = item.feedback?.summary;
  const feedbackHtml = feedbackSummary
    ? `<p><strong>AI 피드백:</strong> ${escapeText(feedbackSummary)}</p>`
    : "";
  const scoreHtml =
    item.score !== undefined && item.score !== null
      ? `<p>점수: ${escapeText(item.score)}점</p>`
      : "";
  const safeDate = escapeHtml(formatDate(item.created_at));
  const safeModeLabel = escapeHtml(modeLabel || "학습 기록");
  const problemTitle = escapeText(item.problem_title, "제목 없음");

  return `
    <li>
      <details>
        <summary>
          <strong>${safeDate}</strong>
          <span>${summaryText}</span>
          <span class="badge soft">${safeModeLabel}</span>
          <span class="badge" data-state="negative">오답</span>
        </summary>
        <div class="history-detail">
          <p><strong>문제:</strong> ${problemTitle}</p>
          ${metaHtml}
          ${codeHtml}
          ${promptHtml}
          <hr />
          ${modeHtml}
          ${feedbackHtml}
          ${scoreHtml}
        </div>
      </details>
    </li>`;
}

function buildModeDetail(item) {
  const mode = item.mode || "practice";
  if (mode === "code-calc") {
    const submitted = escapeText(item.submitted_output, "없음");
    const expected = escapeText(item.expected_output, "없음");
    return `
      <p><strong>제출 출력:</strong> ${submitted}</p>
      <p><strong>정답 출력:</strong> ${expected}</p>
    `;
  }
  if (mode === "code-error") {
    const blocksHtml = buildErrorBlocks(item.problem_blocks, item.selected_index, item.correct_index);
    return blocksHtml || "<p class=\"empty\">블록 정보가 없습니다.</p>";
  }
  if (mode === "code-arrange") {
    const compareHtml = buildArrangeComparison(
      item.problem_blocks,
      item.submitted_order,
      item.correct_order
    );
    return compareHtml || "<p class=\"empty\">정렬 비교 정보를 찾지 못했습니다.</p>";
  }
  if (mode === "auditor") {
    const foundText = escapeList(item.found_types, "없음");
    const missedText = escapeList(item.missed_types, "없음");
    const reference = escapeText(item.reference_report);
    const explanation = escapeText(item.explanation, "내용 없음");
    return `
      <p><strong>제출 리포트:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 함정:</strong> ${foundText}</p>
      <p><strong>놓친 함정:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트:</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "context-inference") {
    const foundText = escapeList(item.found_types, "없음");
    const missedText = escapeList(item.missed_types, "없음");
    const reference = escapeText(item.reference_report);
    const inferenceType = normalizeText(item.inference_type);
    const inferenceTypeLabel =
      inferenceType === "pre_condition"
        ? "실행 전 추론"
        : inferenceType === "post_condition"
          ? "실행 후 추론"
          : inferenceType || "-";
    const explanation = escapeText(item.explanation, "내용 없음");
    const safeInferenceType = escapeHtml(inferenceTypeLabel);
    return `
      <p><strong>추론 타입:</strong> ${safeInferenceType}</p>
      <p><strong>제출 리포트:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>맞춘 facet:</strong> ${foundText}</p>
      <p><strong>놓친 facet:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트:</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "refactoring-choice") {
    const foundText = escapeList(item.found_types, "-");
    const missedText = escapeList(item.missed_types, "-");
    const selectedOption = escapeText(item.selected_option, "-");
    const bestOption = escapeText(item.best_option, "-");
    const reference = escapeText(item.reference_report);
    const optionReviews = Array.isArray(item.option_reviews)
      ? item.option_reviews
          .filter((row) => row && typeof row === "object")
          .map((row) => `${row.optionId || row.option_id || "-"}: ${row.summary || ""}`.trim())
          .filter((row) => row !== ":" && row.length > 0)
      : [];
    const optionReviewText = optionReviews.map((row) => escapeHtml(row)).join("\n");
    const optionReviewHtml = optionReviews.length
      ? `<p><strong>Option reviews:</strong></p><p class="user-answer">${optionReviewText}</p>`
      : "";
    const explanation = escapeText(item.explanation, "No content");
    return `
      <p><strong>Selected option:</strong> ${selectedOption}</p>
      <p><strong>Best option:</strong> ${bestOption}</p>
      <p><strong>Submitted report:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>Found facets:</strong> ${foundText}</p>
      <p><strong>Missed facets:</strong> ${missedText}</p>
      ${optionReviewHtml}
      ${reference ? `<p><strong>Reference report:</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "code-blame") {
    const foundText = escapeList(item.found_types, "-");
    const missedText = escapeList(item.missed_types, "-");
    const selectedCommitsText = escapeList(item.selected_commits, "-");
    const culpritCommitsText = escapeList(item.culprit_commits, "-");
    const commitReviews = Array.isArray(item.commit_reviews)
      ? item.commit_reviews
          .filter((row) => row && typeof row === "object")
          .map((row) => `${row.optionId || row.option_id || "-"}: ${row.summary || ""}`.trim())
          .filter((row) => row !== ":" && row.length > 0)
      : [];
    const commitReviewText = commitReviews.map((row) => escapeHtml(row)).join("\n");
    const reference = escapeText(item.reference_report);
    const errorLog = escapeText(item.problem_error_log);
    const reviewHtml = commitReviews.length
      ? `<p><strong>커밋별 해설:</strong></p><p class="user-answer">${commitReviewText}</p>`
      : "";
    const logHtml = errorLog
      ? `<p><strong>에러 로그:</strong></p><div class="code-block"><pre><code>${errorLog}</code></pre></div>`
      : "";
    const explanation = escapeText(item.explanation, "-");
    return `
      ${logHtml}
      <p><strong>선택 커밋:</strong> ${selectedCommitsText}</p>
      <p><strong>범인 커밋:</strong> ${culpritCommitsText}</p>
      <p><strong>제출 리포트:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>맞춘 facet:</strong> ${foundText}</p>
      <p><strong>놓친 facet:</strong> ${missedText}</p>
      ${reviewHtml}
      ${reference ? `<p><strong>모범 리포트:</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "code-block") {
    const options = Array.isArray(item.problem_options) ? item.problem_options : [];
    const selectedLabel =
      item.selected_option_text ||
      formatOptionLabel(options, item.selected_option) ||
      stripPrefix(item.explanation || "", "선택:") ||
      stripPrefix(item.explanation || "", "선택 옵션:");
    const correctIndex =
      item.correct_answer_index !== undefined && item.correct_answer_index !== null
        ? item.correct_answer_index
        : item.answer_index;
    const correctLabel = item.correct_option_text || formatOptionLabel(options, correctIndex);
    const selectedText = escapeText(selectedLabel || "없음", "없음");
    const correctText = escapeText(correctLabel || "없음", "없음");
    return `
      <p><strong>내 선택:</strong> ${selectedText}</p>
      <p><strong>정답:</strong> ${correctText}</p>
    `;
  }
  const answer = escapeText(item.explanation, "내용 없음");
  return `
    <p><strong>내 답변:</strong></p>
    <p class="user-answer">${answer}</p>
  `;
}

function formatModeLabel(value) {
  return MODE_LABELS[value] || value || "학습 기록";
}

function formatDifficultyLabel(value) {
  const found = DIFFICULTY_OPTIONS.find((option) => option.id === value);
  return found?.label || value || "-";
}

function formatLanguageLabel(value) {
  return LANGUAGE_LABELS[value] || value || "-";
}

function formatIndexLabel(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "없음";
  }
  return `${numeric + 1}번`;
}

function stripPrefix(text, prefix) {
  if (!text) return "";
  return text.startsWith(prefix) ? text.slice(prefix.length).trim() : text;
}

function buildErrorBlocks(blocks, selectedIndex, correctIndex) {
  if (!Array.isArray(blocks) || blocks.length === 0) return "";
  return `
    <div class="history-blocks">
      ${blocks
        .map((block, idx) => {
          const classes = ["history-block"];
          if (idx === selectedIndex) classes.push("is-selected");
          if (idx === correctIndex) classes.push("is-correct");
          if (idx === selectedIndex && idx !== correctIndex) classes.push("is-wrong");
          const code = typeof block === "string" ? block : block?.code || "";
          return `
            <div class="${classes.join(" ")}">
              <div class="history-block-label">${idx + 1}번</div>
              <pre><code>${escapeHtml(code)}</code></pre>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildArrangeComparison(blocks, submittedOrder, correctOrder) {
  if (!Array.isArray(blocks) || blocks.length === 0) return "";
  const blockMap = new Map();
  blocks.forEach((block, idx) => {
    if (block && typeof block === "object") {
      const id = block.id ?? String(idx);
      blockMap.set(id, block.code || "");
    } else {
      blockMap.set(String(idx), String(block ?? ""));
    }
  });
  const submitted = Array.isArray(submittedOrder) ? submittedOrder : [];
  const correct = Array.isArray(correctOrder) ? correctOrder : [];
  return `
    <div class="compare-grid">
      <div class="compare-panel">
        <p class="compare-title">제출 순서</p>
        ${renderArrangeBlocks(submitted, blockMap)}
      </div>
      <div class="compare-panel">
        <p class="compare-title">정답 순서</p>
        ${renderArrangeBlocks(correct, blockMap)}
      </div>
    </div>
  `;
}

function renderArrangeBlocks(order, blockMap) {
  if (!order.length) {
    return '<p class="empty">블록 정보가 없습니다.</p>';
  }
  const blocksHtml = order
    .map((id, idx) => {
      const code = blockMap.get(id) ?? blockMap.get(String(idx)) ?? "";
      return `
        <div class="history-block">
          <div class="history-block-label">${idx + 1}번</div>
          <pre><code>${escapeHtml(code)}</code></pre>
        </div>
      `;
    })
    .join("");
  return `<div class="history-blocks">${blocksHtml}</div>`;
}

function formatOptionLabel(options, indexValue) {
  if (!Array.isArray(options)) return "";
  const idx = Number(indexValue);
  if (!Number.isFinite(idx) || idx < 0 || idx >= options.length) return "";
  const value = options[idx];
  return value ? value : "";
}

async function openReportModal() {
  if (elements.reportBtn) elements.reportBtn.disabled = true;
  try {
    const payload = await apiRequest("/api/report");
    const trend = payload.trend || {};
    const strengths = buildList(
      (payload.common_strengths || []).map((item) => `${item[0]} (${item[1]}회)`),
      "강점 요약이 없습니다."
    );
    const improvements = buildList(
      (payload.common_improvements || []).map((item) => `${item[0]} (${item[1]}회)`),
      "개선 요약이 없습니다."
    );
    const preferredLangs = (payload.preferred_languages || [])
      .map((lang) => `<li>${escapeText(lang.language, "-")} · ${escapeText(lang.count, "0")}회</li>`)
      .join("");
    const recommendations = buildList(payload.recommendations || [], "추천 조언이 없습니다.");
    const avgDuration =
      typeof payload.averageDurationSeconds === "number"
        ? `${Math.round(payload.averageDurationSeconds)}초`
        : "시간 미기록";
    const trendSummary = escapeText(trend.summary, "최근/과거 비교 정보가 없습니다.");
    const trendDetails = `
      <p>최근 정확도: ${escapeText(trend.recentAccuracy ?? "-", "-")}%</p>
      <p>과거 정확도: ${escapeText(trend.previousAccuracy ?? "-", "-")}%</p>
      <p>정확도 변화: ${escapeText(trend.accuracyChange ?? "-", "-")}%p</p>
      <p>${trendSummary}</p>
    `;
    const body = `
      <section class="report-grid">
        <div>
          <h4>누적 성과</h4>
          <p>시도 ${escapeText(payload.attempts ?? 0, "0")} · 정답 ${escapeText(payload.correctAnswers ?? 0, "0")}</p>
          <p>정확도 ${escapeText(payload.accuracy ?? 0, "0")}%</p>
          <p>평균 소요시간 ${escapeText(avgDuration, "시간 미기록")}</p>
        </div>
        <div>
          <h4>변화 추이</h4>
          ${trendDetails}
        </div>
        <div>
          <h4>선호 언어</h4>
          <ul class="list">${preferredLangs || "<li>기록 없음</li>"}</ul>
        </div>
        <div>
          <h4>맞춤 조언</h4>
          ${recommendations}
        </div>
      </section>`;
    showModal("학습 리포트", body);
  } catch (error) {
    showModal("학습 리포트", `<p class="empty">${escapeText(error.message, "리포트를 불러오지 못했습니다.")}</p>`);
  } finally {
    if (elements.reportBtn) elements.reportBtn.disabled = false;
  }
}

function handleLogout() {
  if (authClient) {
    authClient.clearSession();
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem("code-learning-display-name");
  }
  window.location.href = "/index.html";
}

function showModal(title, bodyHtml) {
  if (!elements.modal) return;
  elements.modalTitle.textContent = title;
  elements.modalBody.innerHTML = bodyHtml;
  elements.modal.classList.remove("hidden");
}

function hideModal() {
  elements.modal?.classList.add("hidden");
}

function showToast(message) {
  if (!elements.toast) return;
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  elements.toast.classList.add("visible");
  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }
  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
    elements.toast.classList.add("hidden");
  }, DEFAULT_TOAST_DURATION);
}

function parseUsername(token) {
  if (authClient) {
    return authClient.parseUsername(token);
  }
  if (!token) return "";
  return token.split(":", 1)[0];
}


function buildList(items, emptyText) {
  const normalized = Array.isArray(items)
    ? items.map((item) => normalizeText(item)).filter((item) => item.length > 0)
    : [];
  if (!normalized.length) {
    return `<p class="empty">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="list">${normalized.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
