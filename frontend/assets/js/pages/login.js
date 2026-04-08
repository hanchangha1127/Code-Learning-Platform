const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;

async function init() {
  const token = window.localStorage.getItem(TOKEN_KEY);
  const isValid = await verifyToken(token);
  if (isValid) {
    ensureSessionMarker();
    window.location.href = "/dashboard.html";
    return;
  }

  clearInvalidSession(token);

  const googleButton = document.getElementById("google-login");
  const guestForm = document.getElementById("guest-login-form");
  const guestButton = document.getElementById("guest-login");
  const message = document.getElementById("auth-message");
  const params = new URLSearchParams(window.location.search);
  const reason = params.get("reason");
  const reasonMessage = params.get("message");

  if (reason === "expired" && message) {
    message.textContent = reasonMessage || "세션이 만료되었습니다. 다시 로그인해 주세요.";
  }

  googleButton?.addEventListener("click", () => {
    window.location.href = "/platform/auth/google/start";
  });

  if (!guestForm || !guestButton) return;
  guestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setGuestDisabled(guestButton, true);
    if (message) {
      message.textContent = "게스트 계정을 생성하고 있습니다...";
      message.className = "auth-message";
    }

    try {
      const response = await fetch("/platform/auth/guest", {
        method: "POST",
        credentials: "same-origin",
      });
      const text = await response.text();
      let data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = { detail: text };
        }
      }

      if (!response.ok) {
        throw new Error(data.detail || "게스트 로그인에 실패했습니다.");
      }

      ensureSessionMarker();
      clearDisplayName();
      window.location.href = "/dashboard.html";
    } catch (err) {
      if (message) {
        message.textContent = err?.message || "게스트 로그인에 실패했습니다.";
        message.className = "auth-message error";
      }
    } finally {
      setGuestDisabled(guestButton, false);
    }
  });
}

function ensureSessionMarker() {
  if (authClient?.ensureSessionMarker) {
    authClient.ensureSessionMarker();
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, "cookie-session");
}

function clearDisplayName() {
  if (authClient?.clearDisplayName) {
    authClient.clearDisplayName();
    return;
  }
  window.localStorage.removeItem("code-learning-display-name");
}

function clearInvalidSession(token) {
  if (!token) return;
  if (authClient?.clearSession) {
    authClient.clearSession();
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem("code-learning-display-name");
}

function setGuestDisabled(element, disabled) {
  if (!element) return;
  if (element.tagName === "BUTTON") {
    element.disabled = disabled;
    return;
  }
  if (disabled) {
    element.setAttribute("aria-disabled", "true");
    element.style.pointerEvents = "none";
    element.style.opacity = "0.7";
  } else {
    element.removeAttribute("aria-disabled");
    element.style.pointerEvents = "";
    element.style.opacity = "";
  }
}

async function verifyToken(token) {
  try {
    const headers = {};
    if (token && !(authClient?.isSessionMarker && authClient.isSessionMarker(token))) {
      headers.Authorization = `Bearer ${token}`;
    }
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

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
