(() => {
  const TOKEN_KEY = "code-learning-token";
  const DISPLAY_NAME_KEY = "code-learning-display-name";
  const SESSION_MARKER = "cookie-session";

  function isSessionMarker(token) {
    return String(token || "").trim() === SESSION_MARKER;
  }

  function ensureSessionMarker() {
    window.localStorage.setItem(TOKEN_KEY, SESSION_MARKER);
  }

  function parseUsername(token) {
    if (!token) return "";
    if (isSessionMarker(token)) {
      return window.localStorage.getItem(DISPLAY_NAME_KEY) || "사용자";
    }

    if (token.includes(":")) {
      return token.split(":", 1)[0];
    }

    // JWT fallback: decode payload and try common identity claims.
    try {
      const parts = token.split(".");
      if (parts.length < 2) return "";
      const payloadPart = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padLength = payloadPart.length % 4;
      const padded = payloadPart + (padLength ? "=".repeat(4 - padLength) : "");
      const payload = JSON.parse(window.atob(padded));
      const candidate = payload.username || payload.preferred_username || payload.email || payload.sub;
      return candidate ? String(candidate) : "";
    } catch {
      return "";
    }
  }

  async function verifySession(token) {
    const headers = {};
    const candidate = String(token || "").trim();
    if (candidate && !isSessionMarker(candidate)) {
      headers.Authorization = `Bearer ${candidate}`;
    }

    try {
      const response = await fetch("/platform/profile", {
        method: "GET",
        credentials: "same-origin",
        headers,
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async function ensureActiveSession({ token = null, redirectTo = "/index.html" } = {}) {
    const candidate = String(token || window.localStorage.getItem(TOKEN_KEY) || "").trim();
    const active = await verifySession(candidate);
    if (active) {
      ensureSessionMarker();
      return window.localStorage.getItem(TOKEN_KEY) || SESSION_MARKER;
    }

    clearSession();
    window.location.replace(redirectTo);
    return null;
  }

  function clearSession() {
    try {
      fetch("/platform/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
      }).catch(() => {});
    } catch {
      // ignore network errors during logout cleanup
    }
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(DISPLAY_NAME_KEY);
  }

  function clearDisplayName() {
    window.localStorage.removeItem(DISPLAY_NAME_KEY);
  }

  function isAuthFailureStatus(status) {
    return status === 401 || status === 403;
  }

  function handleSessionExpired(message = "로그인이 만료되었습니다. 다시 로그인해 주세요.") {
    clearSession();
    const encoded = encodeURIComponent(message);
    window.location.replace(`/index.html?reason=expired&message=${encoded}`);
  }

  window.CodeAuth = {
    TOKEN_KEY,
    DISPLAY_NAME_KEY,
    SESSION_MARKER,
    isSessionMarker,
    verifySession,
    ensureActiveSession,
    ensureSessionMarker,
    parseUsername,
    clearSession,
    clearDisplayName,
    isAuthFailureStatus,
    handleSessionExpired,
  };
})();

