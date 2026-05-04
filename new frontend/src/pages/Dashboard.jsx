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
const DEFAULT_DAILY_TARGET = 10;

function Dashboard() {
  const [token] = useState(localStorage.getItem(TOKEN_KEY));
  const [me, setMe] = useState(null);
  const [home, setHome] = useState(null);
  const [goal, setGoal] = useState(null);
  const [settings, setSettings] = useState(readStoredProfileSettings);
  const [loading, setLoading] = useState(true);

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

    if (!response.ok) {
      throw new Error("대시보드 정보를 불러오지 못했습니다.");
    }

    return response.json();
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
    } catch (error) {
      console.warn(error);

      // 백엔드 연결 전에도 화면을 확인할 수 있도록 기본값 처리
      setMe({ display_name: "사용자" });
      setHome(null);
      setGoal({ dailyTargetSessions: DEFAULT_DAILY_TARGET });
      setSettings(readStoredProfileSettings());
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
    } catch (error) {
      console.warn(error);
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
    } catch (error) {
      alert(error.message || "일간 목표 저장에 실패했습니다.");
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
    } catch (error) {
      console.warn(error);
    }
  };

  return (
    <section id="dashboard-section" className="app dashboard-shell" aria-live="polite">
      <DashboardHeader onLogout={handleLogout} />

      <main className="dashboard-main">
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
    </section>
  );
}

export default Dashboard;
