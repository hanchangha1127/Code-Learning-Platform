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
  "refactoring-choice": "최적안 선택",
  "code-blame": "범인 찾기",
};

const LANGUAGE_LABELS = {
  python: "파이썬",
  javascript: "자바스크립트",
  c: "C",
  java: "자바",
};

const REPORT_LOADING_STEPS = [
  {
    label: "학습 데이터 분석",
    description: "최근 학습 기록과 점수 흐름을 정리하고 있어요.",
  },
  {
    label: "학습 패턴 탐색",
    description: "집중해야 할 주제와 학습 공백을 추출하고 있어요.",
  },
  {
    label: "실행 계획 생성",
    description: "바로 적용할 수 있는 액션 플랜을 만들고 있어요.",
  },
];

const state = {
  token: null,
  username: "",
  displayName: "",
  languages: [],
  selectedLanguage: DEFAULT_LANGUAGE,
  difficulty: DEFAULT_DIFFICULTY,
  toastTimer: null,
  reportLoadingTimer: null,
  activeReportRequestId: null,
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
  elements.modalCard = elements.modal?.querySelector(".modal-card");
  elements.modalTitle = document.getElementById("modal-title");
  elements.modalBody = document.getElementById("modal-body");
  elements.modalClose = document.getElementById("modal-close");
}

async function init() {
  cacheDom();
  if (authClient?.ensureActiveSession) {
    state.token = await authClient.ensureActiveSession({
      token: window.localStorage.getItem(TOKEN_KEY),
      redirectTo: "/index.html",
    });
  } else {
    state.token = window.localStorage.getItem(TOKEN_KEY);
  }
  if (!state.token) {
    return;
  }  state.username = parseUsername(state.token);
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
    const glyph = Array.from(label).find((char) => char.trim().length > 0) || "학";
    elements.profileAvatar.textContent = glyph;
  }
}

async function loadUserInfo() {
  try {
    const data = await apiRequest("/platform/me");
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
    const profile = await apiRequest("/platform/profile");
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
    const payload = await apiRequest("/platform/languages");
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
    const payload = await apiRequest("/platform/learning/history");
    const list = (payload.history || []).filter((item) => item.correct === false);
    if (list.length === 0) {
      showModal("오답 노트", '<p class="empty">틀린 기록이 없습니다.</p>', { wide: true });
      return;
    }
    const items = list.map((item) => renderWrongNoteItem(item)).join("");
    showModal("오답 노트", `<ul class="list history-list">${items}</ul>`, { wide: true });
  } catch (error) {
    showModal("오답 노트", `<p class="empty">${escapeText(error.message, "기록을 불러오지 못했습니다.")}</p>`, { wide: true });
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
  const showRawCode = !["code-error", "code-arrange", "code-block"].includes(modeKey);
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
      ? `<p>점수: ${escapeText(item.score)}</p>`
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
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 유형:</strong> ${foundText}</p>
      <p><strong>놓친 유형:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
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
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
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
      ? `<p><strong>옵션 리뷰:</strong></p><p class="user-answer">${optionReviewText}</p>`
      : "";
    const explanation = escapeText(item.explanation, "내용 없음");
    return `
      <p><strong>선택한 옵션:</strong> ${selectedOption}</p>
      <p><strong>최적 옵션:</strong> ${bestOption}</p>
      <p><strong>제출 리포트:</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${optionReviewHtml}
      ${reference ? `<p><strong>모범 리포트:</strong></p><p class="user-answer">${reference}</p>` : ""}
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
      ? `<p><strong>커밋 리뷰:</strong></p><p class="user-answer">${commitReviewText}</p>`
      : "";
    const logHtml = errorLog
      ? `<p><strong>에러 로그:</strong></p><div class="code-block"><pre><code>${errorLog}</code></pre></div>`
      : "";
    const explanation = escapeText(item.explanation, "-");
    return `
      ${logHtml}
      <p><strong>선택 커밋:</strong> ${selectedCommitsText}</p>
      <p><strong>범인 커밋:</strong> ${culpritCommitsText}</p>
      <p><strong>제출 리포트</strong></p>
      <p class="user-answer">${explanation}</p>
      <p><strong>찾은 관점:</strong> ${foundText}</p>
      <p><strong>놓친 관점:</strong> ${missedText}</p>
      ${reviewHtml}
      ${reference ? `<p><strong>모범 리포트</strong></p><p class="user-answer">${reference}</p>` : ""}
    `;
  }
  if (mode === "code-block") {
    const options = Array.isArray(item.problem_options) ? item.problem_options : [];
    const selectedIndex = normalizeOptionIndex(item.selected_option);
    const selectedLabel =
      item.selected_option_text ||
      formatOptionLabel(options, item.selected_option) ||
      stripPrefix(item.explanation || "", "선택:") ||
      stripPrefix(item.explanation || "", "선택 옵션:");
    const rawCorrectIndex =
      item.correct_answer_index !== undefined && item.correct_answer_index !== null
        ? item.correct_answer_index
        : item.answer_index;
    const correctIndex = normalizeOptionIndex(rawCorrectIndex);
    const correctLabel = item.correct_option_text || formatOptionLabel(options, correctIndex);
    const selectedText = escapeText(selectedLabel || "없음", "없음");
    const correctText = escapeText(correctLabel || "없음", "없음");
    const codeWithBlankTiles = escapeHtml(item.problem_code || "")
      .replace(/\[BLANK\]/g, '<span class="history-blank-tile" aria-label="빈칸"></span>');
    const codeHtml = item.problem_code
      ? `
        <div class="history-code-window">
          <div class="history-code-title">문제 코드</div>
          <div class="history-code-block"><pre><code>${codeWithBlankTiles}</code></pre></div>
        </div>
      `
      : "";
    const choicesHtml = buildCodeBlockChoiceCards(options, selectedIndex, correctIndex);
    const pointText = buildCodeBlockLearningPoint({
      selectedLabel,
      correctLabel,
      selectedIndex,
      correctIndex,
    });
    return `
      ${codeHtml}
      <p><strong>내 선택:</strong> ${selectedText}</p>
      <p><strong>정답:</strong> ${correctText}</p>
      ${choicesHtml}
      <div class="history-learning-point">
        <strong>학습 포인트</strong>
        <p>${escapeHtml(pointText)}</p>
      </div>
    `;
  }
  const answer = escapeText(item.explanation, "내용 없음");
  return `
    <p><strong>제출 답변:</strong></p>
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

function normalizeOptionIndex(value) {
  const index = Number(value);
  return Number.isInteger(index) && index >= 0 ? index : null;
}

function buildCodeBlockChoiceCards(options, selectedIndex, correctIndex) {
  if (!Array.isArray(options) || options.length === 0) {
    return '<p class="empty">선택지 정보가 없습니다.</p>';
  }
  const cardsHtml = options
    .map((option, idx) => {
      const classes = ["history-choice-card"];
      if (idx === selectedIndex) classes.push("is-selected");
      if (idx === correctIndex) classes.push("is-correct");
      if (idx === selectedIndex && idx !== correctIndex) classes.push("is-wrong");
      return `
        <div class="${classes.join(" ")}">
          <div class="history-choice-index">${idx + 1}번 선택지</div>
          <pre><code>${escapeHtml(String(option ?? ""))}</code></pre>
        </div>
      `;
    })
    .join("");
  return `
    <div class="history-choice-grid">
      ${cardsHtml}
    </div>
  `;
}

function buildCodeBlockLearningPoint({ selectedLabel, correctLabel, selectedIndex, correctIndex }) {
  if (selectedLabel && correctLabel && selectedIndex !== null && correctIndex !== null) {
    if (selectedIndex === correctIndex) {
      return `정답(${correctLabel})을 정확히 선택했습니다. 같은 유형에서 왜 이 선택지가 맞는지 근거까지 함께 설명해 보세요.`;
    }
    return `내 선택은 "${selectedLabel}"이고 정답은 "${correctLabel}"입니다. 코드 흐름에서 빈칸 앞뒤 문맥을 기준으로 차이를 비교해 보세요.`;
  }
  return "선택지의 의미와 코드 문맥을 함께 비교해 빈칸의 의도를 파악해 보세요.";
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

function setReportButtonLoading(isLoading) {
  if (!elements.reportBtn) return;
  elements.reportBtn.disabled = isLoading;
  elements.reportBtn.classList.toggle("loading", isLoading);
  elements.reportBtn.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function stopReportLoadingAnimation() {
  if (!state.reportLoadingTimer) return;
  window.clearInterval(state.reportLoadingTimer);
  state.reportLoadingTimer = null;
}

function waitForNextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    });
  });
}

function renderReportLoadingBody(activeStepIndex, tickCount = 0) {
  const activeIndex = Math.max(0, Math.min(activeStepIndex, REPORT_LOADING_STEPS.length - 1));
  const step = REPORT_LOADING_STEPS[activeIndex];
  const progress = Math.min(94, 24 + tickCount * 10);
  const steps = REPORT_LOADING_STEPS.map((item, index) => {
    const statusClass = index < activeIndex ? "is-done" : index === activeIndex ? "is-active" : "";
    return `<li class="${statusClass}">${escapeHtml(item.label)}</li>`;
  }).join("");

  return `
    <section class="report-loading" role="status" aria-live="polite">
      <div class="report-loading-head">
        <span class="report-loading-spinner" aria-hidden="true"></span>
        <div class="report-loading-copy">
          <p class="report-loading-kicker">학습 리포트 생성 중</p>
          <p class="report-loading-title">${escapeHtml(step.label)}</p>
          <p class="report-loading-desc">${escapeHtml(step.description)}</p>
        </div>
      </div>
      <div class="report-loading-bar" aria-hidden="true">
        <span style="width:${progress}%"></span>
      </div>
      <ol class="report-loading-steps">${steps}</ol>
      <div class="report-loading-skeleton" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
        <span></span>
      </div>
    </section>`;
}

function startReportLoadingAnimation(requestId) {
  stopReportLoadingAnimation();

  let tickCount = 0;
  showModal("학습 리포트", renderReportLoadingBody(0, tickCount), { wide: true });

  state.reportLoadingTimer = window.setInterval(() => {
    if (state.activeReportRequestId !== requestId) {
      stopReportLoadingAnimation();
      return;
    }
    tickCount += 1;
    const activeStepIndex = tickCount % REPORT_LOADING_STEPS.length;
    if (elements.modalBody) {
      elements.modalBody.innerHTML = renderReportLoadingBody(activeStepIndex, tickCount);
    }
  }, 1200);
}

function renderReportContent(payload) {
  const metric = payload.metricSnapshot || {};
  const priorityActions = buildList(payload.priorityActions || [], "우선 실행 액션이 없습니다.");
  const phasePlan = buildList(payload.phasePlan || [], "단계별 계획이 없습니다.");
  const dailyHabits = buildList(payload.dailyHabits || [], "일일 학습 습관 제안이 없습니다.");
  const focusTopics = buildList(payload.focusTopics || [], "집중 학습 주제가 없습니다.");
  const metricsToTrack = buildList(payload.metricsToTrack || [], "추적 지표가 없습니다.");
  const checkpoints = buildList(payload.checkpoints || [], "체크포인트가 없습니다.");
  const riskMitigation = buildList(payload.riskMitigation || [], "리스크 대응 항목이 없습니다.");
  const metricSnapshot = `
    <p>시도 횟수: ${escapeText(metric.attempts ?? 0, "0")}</p>
    <p>정확도: ${escapeText(metric.accuracy ?? "-", "-")}%</p>
    <p>평균 점수: ${escapeText(metric.avgScore ?? "-", "-")}</p>
    <p>추세: ${escapeText(metric.trend ?? "데이터 부족", "데이터 부족")}</p>
  `;

  return `
    <section class="report-grid">
      <div>
        <h4>학습 목표</h4>
        <p>${escapeText(payload.goal, "목표가 없습니다.")}</p>
        <p><strong>생성 시각:</strong> ${escapeText(formatDate(payload.createdAt), "-")}</p>
      </div>
      <div>
        <h4>솔루션 요약</h4>
        <p>${escapeText(payload.solutionSummary, "요약이 없습니다.")}</p>
      </div>
      <div>
        <h4>지표 스냅샷</h4>
        ${metricSnapshot}
      </div>
      <div>
        <h4>우선 실행 액션</h4>
        ${priorityActions}
      </div>
      <div>
        <h4>단계별 계획</h4>
        ${phasePlan}
      </div>
      <div>
        <h4>일일 습관</h4>
        ${dailyHabits}
      </div>
      <div>
        <h4>집중 학습 주제</h4>
        ${focusTopics}
      </div>
      <div>
        <h4>추적 지표</h4>
        ${metricsToTrack}
      </div>
      <div>
        <h4>체크포인트</h4>
        ${checkpoints}
      </div>
      <div>
        <h4>리스크 대응</h4>
        ${riskMitigation}
      </div>
    </section>`;
}

function showReportErrorModal(error) {
  const message = escapeText(error?.message, "리포트를 불러오지 못했습니다.");
  const body = `
    <div class="report-loading-error">
      <p class="report-loading-error-title">리포트 생성에 실패했습니다.</p>
      <p class="report-loading-error-desc">${message}</p>
      <button id="report-retry-btn" type="button" class="primary block">다시 시도</button>
    </div>
  `;
  showModal("학습 리포트", body, { wide: true });
  const retryButton = document.getElementById("report-retry-btn");
  retryButton?.addEventListener(
    "click",
    () => {
      void openReportModal();
    },
    { once: true }
  );
}

async function openReportModal() {
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  state.activeReportRequestId = requestId;
  setReportButtonLoading(true);
  startReportLoadingAnimation(requestId);

  try {
    await waitForNextPaint();
    if (state.activeReportRequestId !== requestId) return;
    const payload = await apiRequest("/platform/report");
    if (state.activeReportRequestId !== requestId) return;
    stopReportLoadingAnimation();
    showModal("학습 리포트", renderReportContent(payload), { wide: true });
  } catch (error) {
    if (state.activeReportRequestId !== requestId) return;
    stopReportLoadingAnimation();
    showReportErrorModal(error);
  } finally {
    if (state.activeReportRequestId === requestId) {
      state.activeReportRequestId = null;
    }
    setReportButtonLoading(false);
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

function showModal(title, bodyHtml, options = {}) {
  if (!elements.modal) return;
  const { wide = false } = options;
  const desktopWide = wide && window.matchMedia("(min-width: 1024px)").matches;
  elements.modalTitle.textContent = title;
  elements.modalBody.innerHTML = bodyHtml;
  elements.modalCard?.classList.toggle("modal-wide", wide);
  if (elements.modalCard) {
    elements.modalCard.style.width = desktopWide ? "min(1100px, 96vw)" : "";
  }
  elements.modal.classList.remove("hidden");
}

function hideModal() {
  stopReportLoadingAnimation();
  state.activeReportRequestId = null;
  elements.modalCard?.classList.remove("modal-wide");
  if (elements.modalCard) {
    elements.modalCard.style.width = "";
  }
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



