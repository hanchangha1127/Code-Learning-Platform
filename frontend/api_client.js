(() => {
  function parseResponseBody(text) {
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { detail: text };
    }
  }

  function defaultAuthFailureHandler(authClient, status, message) {
    if (!authClient) return;
    if (typeof authClient.isAuthFailureStatus !== "function") return;
    if (!authClient.isAuthFailureStatus(status)) return;
    if (typeof authClient.handleSessionExpired === "function") {
      authClient.handleSessionExpired(message);
    }
  }

  function create({ getToken, authClient = null, defaultErrorMessage = "요청을 처리하지 못했습니다." }) {
    if (typeof getToken !== "function") {
      throw new Error("CodeApiClient.create requires a getToken function.");
    }

    return async function apiRequest(path, { method = "GET", body, auth = true } = {}) {
      const headers = {};
      if (body !== undefined) {
        headers["Content-Type"] = "application/json";
      }

      const token = getToken();
      if (auth && token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });

      const text = await response.text();
      const data = parseResponseBody(text);

      if (!response.ok) {
        const message = data.detail || data.message || defaultErrorMessage;
        defaultAuthFailureHandler(authClient, response.status, message);
        throw new Error(message);
      }

      return data;
    };
  }

  window.CodeApiClient = {
    create,
  };
})();
