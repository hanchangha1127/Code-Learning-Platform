import { useEffect, useState } from "react";

const TOKEN_KEY = "code-learning-token";
const DISPLAY_NAME_KEY = "code-learning-display-name";
const SESSION_MARKER = "cookie-session";

export function getToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function isSessionMarker(token) {
  return String(token || "").trim() === SESSION_MARKER;
}

export function authHeaders() {
  const token = getToken();
  if (!token || isSessionMarker(token)) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export function errorMessageFromPayload(data, fallback) {
  const detail = data?.detail ?? data?.message;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .filter(Boolean)
      .join(" ");
  }
  if (typeof detail === "object") return detail.msg || detail.message || JSON.stringify(detail);
  return String(detail);
}

export async function apiRequest(path, { method = "GET", body, auth = true, headers = {}, signal } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    signal,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(auth ? authHeaders() : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await readJson(response);
  if (!response.ok) {
    throw new Error(errorMessageFromPayload(data, `요청에 실패했습니다. (${response.status})`));
  }
  return data;
}

export function isEventStreamResponse(response) {
  return Boolean(
    response?.body &&
    (response.headers.get("content-type") || "").toLowerCase().includes("text/event-stream"),
  );
}

export function saveSession(payload) {
  const token = payload?.accessToken || payload?.access_token || payload?.token || SESSION_MARKER;
  window.localStorage.setItem(TOKEN_KEY, token || SESSION_MARKER);
  const displayName = payload?.displayName || payload?.display_name || payload?.username || payload?.email || "";
  if (displayName) window.localStorage.setItem(DISPLAY_NAME_KEY, displayName);
}

export async function clearSession() {
  try {
    await fetch("/platform/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch {
    // Ignore logout network cleanup.
  }
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(DISPLAY_NAME_KEY);
}

export async function verifySession() {
  try {
    await apiRequest("/platform/profile");
    const existingToken = getToken();
    if (!existingToken || isSessionMarker(existingToken)) {
      window.localStorage.setItem(TOKEN_KEY, SESSION_MARKER);
    }
    return true;
  } catch {
    return false;
  }
}

export function useSessionGuard(enabled = true) {
  const [ready, setReady] = useState(!enabled);
  useEffect(() => {
    let active = true;
    if (!enabled) return undefined;
    verifySession().then((ok) => {
      if (!active) return;
      if (!ok) {
        clearSession();
        window.location.replace("/index.html");
        return;
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, [enabled]);
  return ready;
}
