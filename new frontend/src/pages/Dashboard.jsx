import { useCallback, useEffect, useState } from "react";
import DashboardHeader from "../components/DashboardHeader.jsx";
import DashboardHero from "../components/DashboardHero.jsx";
import GoalCard from "../components/GoalCard.jsx";
import ReviewList from "../components/ReviewList.jsx";
import ModeSection from "../components/ModeSection.jsx";
import {
  normalizeProfileSettings,
  persistLearningSettings,
  readStoredProfileSettings,
} from "../lib/learningSettings.js";

const TOKEN_KEY = "code-learning-token";
const SESSION_MARKER = "cookie-session";
function Dashboard() {
  const [token] = useState(localStorage.getItem(TOKEN_KEY));
  const [me, setMe] = useState(null);
  const [home, setHome] = useState(null);
  const [goal, setGoal] = useState(null);
  const [settings, setSettings] = useState(readStoredProfileSettings);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [notice, setNotice] = useState("");

  const apiRequest = useCallback(async (url, options = {}) => {
    const response = await fetch(url, {
      method: options.method || "GET",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(token && token !== SESSION_MARKER ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text };
      }
    }

    if (!response.ok) {
      const error = new Error(payload.detail || payload.message || `대시보드 정보를 불러오지 못했습니다. (${response.status})`);
      error.status = response.status;
      throw error;
    }

    return payload;
  }, [token]);

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);

      const [meData, homeData, goalData, settingsData] = await Promise.all([
        apiRequest("/platform/me"),
        apiRequest("/platform/home"),
        apiRequest("/platform/me/goal"),
        apiRequest("/platform/me/settings"),
      ]);
      const normalizedSettings = normalizeProfileSettings(settingsData);

      setMe(meData);
      setHome(homeData);
      setGoal(goalData);
      setSettings(normalizedSettings);
      persistLearningSettings(normalizedSettings);
      setErrorMessage("");
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem("code-learning-display-name");
        window.location.replace("/index.html");
        return;
      }
      setErrorMessage(error.message || "대시보드를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [apiRequest]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleLogout = async () => {
    try {
      await fetch("/platform/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: token && token !== SESSION_MARKER ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      // Local session cleanup below is enough for the user-facing logout flow.
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("code-learning-display-name");
    window.location.replace("/index.html");
  };

  const handleGoalSave = async (nextGoal) => {
    try {
      await apiRequest("/platform/me/goal", {
        method: "PUT",
        body: {
          daily_target_sessions: nextGoal,
          focus_modes: Array.isArray(home?.focusModes) ? home.focusModes : [],
          focus_topics: Array.isArray(home?.focusTopics) ? home.focusTopics : [],
        },
      });

      await loadDashboard();
      setNotice("일간 목표를 저장했습니다.");
    } catch (error) {
      setNotice(error.message || "일간 목표 저장에 실패했습니다.");
    }
  };

  const handleSettingsChange = async (patch) => {
    const nextSettings = normalizeProfileSettings({ ...settings, ...patch }, settings);
    setSettings(nextSettings);
    persistLearningSettings(nextSettings);

    try {
      const saved = await apiRequest("/platform/me/settings", {
        method: "PUT",
        body: nextSettings,
      });
      const normalizedSaved = normalizeProfileSettings(saved, nextSettings);
      setSettings(normalizedSaved);
      persistLearningSettings(normalizedSaved);
      setNotice("학습 설정을 저장했습니다.");
    } catch (error) {
      setNotice(error.message || "학습 설정 저장에 실패했습니다.");
    }
  };

  const showBlockingError = Boolean(errorMessage && !home);

  return (
    <section id="dashboard-section" className="app dashboard-shell" aria-live="polite">
      <DashboardHeader onLogout={handleLogout} />

      {showBlockingError ? (
        <main className="dashboard-main">
          <section id="dashboard-error" className="card dashboard-panel feedback-panel">
            <h2>대시보드를 불러오지 못했습니다.</h2>
            <p className="status-line">{errorMessage}</p>
            <button className="primary" type="button" onClick={loadDashboard} disabled={loading}>
              {loading ? "다시 불러오는 중" : "다시 시도"}
            </button>
          </section>
        </main>
      ) : (
      <main className="dashboard-main">
        {notice ? <p id="dashboard-notice" className="toast">{notice}</p> : null}
        {errorMessage ? <p id="dashboard-error-inline" className="status-line">{errorMessage}</p> : null}
        <DashboardHero
          me={me}
          home={home}
          loading={loading}
          settings={settings}
          onSettingsChange={handleSettingsChange}
        />

        <section className="dashboard-focus-grid">
          <GoalCard
            home={home}
            goal={goal}
            loading={loading}
            onGoalSave={handleGoalSave}
          />

          <ReviewList home={home} loading={loading} />
        </section>

        <ModeSection recommendedModes={home?.recommendedModes || []} />
      </main>
      )}
    </section>
  );
}

export default Dashboard;
