const TOKEN_KEY = "code-learning-token";
const authClient = window.CodeAuth || null;

async function init() {
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (token) {
    const isValid = await verifyToken(token);
    if (isValid) {
      window.location.href = "/dashboard.html";
      return;
    }
    if (authClient) {
      authClient.clearSession();
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem("code-learning-display-name");
    }
  }

  const googleButton = document.getElementById("google-login");
  const guestForm = document.getElementById("guest-login-form");
  const guestButton = document.getElementById("guest-login");
  const message = document.getElementById("auth-message");
  const params = new URLSearchParams(window.location.search);
  const reason = params.get("reason");
  const reasonMessage = params.get("message");
  if (reason === "expired" && message) {
    message.textContent = reasonMessage || "Session expired. Please log in again.";
  }
  googleButton?.addEventListener("click", () => {
    window.location.href = "/api/auth/google/start";
  });
  if (!guestForm || !guestButton) return;
  guestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setGuestDisabled(guestButton, true);
    if (message) message.textContent = "게스트 계정을 생성 중입니다...";
    try {
      const response = await fetch("/api/auth/guest", { method: "POST" });
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
      window.localStorage.setItem(TOKEN_KEY, data.token);
      if (authClient) {
        authClient.clearDisplayName();
      } else {
        window.localStorage.removeItem("code-learning-display-name");
      }
      window.location.href = "/dashboard.html";
    } catch (err) {
      if (message) message.textContent = err.message || "게스트 로그인에 실패했습니다.";
    } finally {
      setGuestDisabled(guestButton, false);
    }
  });
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
