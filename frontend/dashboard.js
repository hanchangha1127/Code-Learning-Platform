const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;
const DISPLAY_NAME_KEY = "code-learning-display-name";

const features = [];
const elements = {};

function cacheDom() {
  elements.featureGrid = document.getElementById("feature-grid");
  elements.userChip = document.getElementById("dashboard-user");
  elements.logoutBtn = document.getElementById("dashboard-logout-btn");
}

function init() {
  cacheDom();
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (!token) {
    window.location.href = "/index.html";
    return;
  }

  verifyToken(token).then(async (isValid) => {
    if (!isValid) {
      if (authClient) {
        authClient.clearSession();
      } else {
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(DISPLAY_NAME_KEY);
      }
      window.location.href = "/index.html";
      return;
    }

    const username = await loadDisplayName(token);
    if (elements.userChip) {
      elements.userChip.textContent = username;
    }

    seedDefaultFeatures();
    renderFeatures();
    elements.logoutBtn?.addEventListener("click", handleLogout);
  });
}

function handleLogout() {
  if (authClient) {
    authClient.clearSession();
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(DISPLAY_NAME_KEY);
  }
  window.location.href = "/index.html";
}

function seedDefaultFeatures() {
  if (features.length > 0) return;

  registerFeature({
    id: "analysis",
    title: "코드 분석",
    description: "AI가 출제한 알고리즘 문제를 읽고 설명해 보세요.",
    icon: "🔍",
    link: "/analysis.html",
  });
  registerFeature({
    id: "codeblock",
    title: "코드 블록",
    description: "빈칸을 채우고 정답을 골라 문법을 익혀보세요.",
    icon: "🧩",
    link: "/codeblock.html",
  });
  registerFeature({
    id: "codecalc",
    title: "코드 계산",
    description: "코드를 실행하지 않고 출력값을 추론해 보세요.",
    icon: "🧮",
    link: "/codecalc.html",
  });
  registerFeature({
    id: "code-arrange",
    title: "코드 배치",
    description: "섞인 코드 블록을 올바른 순서로 재배열해 보세요.",
    icon: "🔀",
    link: "/arrange.html",
  });
  registerFeature({
    id: "code-error",
    title: "코드 오류",
    description: "여러 블록 중 오류가 있는 코드를 찾아보세요.",
    icon: "🐞",
    link: "/codeerror.html",
  });
  registerFeature({
    id: "auditor",
    title: "감사관 모드",
    description: "치명적 함정을 찾아 자유서술 감사 리포트를 제출하세요.",
    icon: "🕵️",
    link: "/auditor.html",
  });
  registerFeature({
    id: "context-inference",
    title: "맥락 추론",
    description: "코드 일부와 질문을 보고 전후 맥락을 추론해 보세요.",
    icon: "🧭",
    link: "/context-inference.html",
  });
  registerFeature({
    id: "refactoring-choice",
    title: "최적의 선택",
    description: "A/B/C 구현 중 제약에 맞는 최적안을 선택하고 근거를 작성하세요.",
    icon: "⚖️",
    link: "/refactoring-choice.html",
  });
  registerFeature({
    id: "code-blame",
    title: "범인 찾기",
    description: "서버 에러 로그와 커밋 diff를 비교해 장애 원인 커밋을 추리하세요.",
    icon: "🧯",
    link: "/code-blame.html",
  });
  registerFeature({
    id: "coming-soon",
    title: "준비중",
    description: "앞으로 더 많은 학습 모드가 추가될 예정입니다.",
    icon: "🚧",
    link: "#",
    disabled: true,
  });
}

function registerFeature(feature) {
  const defaults = {
    id: `feature-${features.length}`,
    title: "새 기능",
    description: "",
    icon: "✨",
    link: "#",
    disabled: false,
    badge: "",
  };
  features.push({ ...defaults, ...feature });
}

function renderFeatures() {
  if (!elements.featureGrid) return;
  elements.featureGrid.innerHTML = "";

  features.forEach((feature) => {
    const card = document.createElement("a");
    card.className = "feature-card";
    card.href = feature.disabled ? "#" : feature.link;
    if (feature.disabled) {
      card.classList.add("disabled");
      card.setAttribute("aria-disabled", "true");
    }

    const icon = document.createElement("div");
    icon.className = "feature-icon";
    icon.textContent = feature.icon;

    const title = document.createElement("h3");
    title.textContent = feature.title;

    const desc = document.createElement("p");
    desc.textContent = feature.description;

    if (feature.badge) {
      const badge = document.createElement("span");
      badge.className = "badge soft";
      badge.textContent = feature.badge;
      card.appendChild(badge);
    }

    card.appendChild(icon);
    card.appendChild(title);
    card.appendChild(desc);
    elements.featureGrid.appendChild(card);
  });
}

function parseUsername(token) {
  if (authClient) {
    return authClient.parseUsername(token);
  }
  if (!token) return "";
  return token.split(":", 1)[0];
}

async function loadDisplayName(token) {
  const cached = window.localStorage.getItem(DISPLAY_NAME_KEY);
  if (cached) {
    return cached;
  }
  try {
    const response = await fetch("/api/me", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      throw new Error("profile fetch failed");
    }
    const data = await response.json();
    const label = data.display_name || data.displayName || data.username || parseUsername(token);
    window.localStorage.setItem(DISPLAY_NAME_KEY, label);
    return label;
  } catch {
    return parseUsername(token);
  }
}

async function verifyToken(token) {
  try {
    const response = await fetch("/api/profile", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
