import { useState } from "react";
import {
  LANGUAGE_OPTIONS,
  PROFILE_DIFFICULTY_OPTIONS,
  languageTitle,
  normalizeLanguageId,
  normalizeProfileDifficulty,
  readStoredProfileSettings,
} from "../lib/learningSettings.js";

function DashboardHero({ me, home, loading, settings, onSettingsChange }) {
  const [isLanguageOpen, setIsLanguageOpen] = useState(false);
  const fallbackSettings = readStoredProfileSettings();
  const selectedLanguage = normalizeLanguageId(
    settings?.preferred_language ?? settings?.preferredLanguage,
    fallbackSettings.preferred_language,
  );
  const selectedDifficulty = normalizeProfileDifficulty(
    settings?.preferred_difficulty ?? settings?.preferredDifficulty,
    fallbackSettings.preferred_difficulty,
  );

  const displayName =
    home?.displayName ||
    me?.display_name ||
    me?.displayName ||
    me?.username ||
    "사용자";

  const dailyGoal = home?.dailyGoal || {};
  const trend = home?.trend || {};
  const stats = home?.stats || {};

  const totalAttempts = Number(stats.totalAttempts || 0);
  const accuracy =
    stats.accuracy === null || stats.accuracy === undefined
      ? "-"
      : `${Number(stats.accuracy).toFixed(1)}%`;

  const last7Attempts = Number(trend.last7DaysAttempts || 0);
  const goalText = dailyGoal.achieved
    ? "오늘 목표를 달성했습니다."
    : `오늘 목표까지 ${dailyGoal.remainingSessions || 0}문제가 남았습니다.`;

  return (
    <section className="card dashboard-hero">
      <div className="dashboard-hero-copy">
        <p className="dashboard-hero-kicker">오늘 추천 학습</p>

        <h2>
          {loading ? "학습 현황을 불러오는 중입니다." : `${displayName}님의 오늘 학습`}
        </h2>

        <p className="dashboard-hero-summary">
          {loading
            ? "최근 학습 기록을 바탕으로 오늘의 목표와 복습 우선순위를 정리하고 있습니다."
            : `최근 7일 동안 ${last7Attempts}회 학습, 전체 정답률 ${accuracy}. ${goalText}`}
        </p>

        <div className="practice-controls" aria-label="문제 설정">
          <div className="practice-control">
            <span className="practice-label">언어 선택</span>
            <div className="language-dropdown">
              <button
                type="button"
                className="language-trigger"
                aria-expanded={isLanguageOpen}
                onClick={() => setIsLanguageOpen((isOpen) => !isOpen)}
              >
                <span>{languageTitle(selectedLanguage)}</span>
                <svg className="chevron-svg" viewBox="0 0 16 16" aria-hidden="true">
                  <path d="m4 6 4 4 4-4" />
                </svg>
              </button>

              {isLanguageOpen && (
                <div className="language-menu" role="listbox">
                  {LANGUAGE_OPTIONS.map((language) => (
                    <button
                      key={language.id}
                      type="button"
                      className={language.id === selectedLanguage ? "is-selected" : ""}
                      onClick={() => {
                        onSettingsChange?.({ preferred_language: language.id });
                        setIsLanguageOpen(false);
                      }}
                    >
                      {language.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="practice-control">
            <span className="practice-label">난이도</span>
            <div className="difficulty-tabs" role="group" aria-label="난이도">
              {PROFILE_DIFFICULTY_OPTIONS.map((difficulty) => (
                <button
                  key={difficulty.id}
                  type="button"
                  className={difficulty.id === selectedDifficulty ? "is-active" : ""}
                  onClick={() => onSettingsChange?.({ preferred_difficulty: difficulty.id })}
                >
                  {difficulty.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <aside className="dashboard-code-preview" aria-label="예시 코드">
        <div className="code-window-header">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <pre>{`function getRole(user) {
  if (!user) return "guest";
  return user.isAdmin ? "admin" : "member";
}`}</pre>
        <div className="hero-stat-row">
          <div>
            <span>누적 풀이</span>
            <strong>{totalAttempts}</strong>
          </div>
          <div>
            <span>정답률</span>
            <strong>{accuracy}</strong>
          </div>
        </div>
      </aside>
    </section>
  );
}

export default DashboardHero;
