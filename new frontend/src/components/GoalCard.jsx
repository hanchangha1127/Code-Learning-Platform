import { useEffect, useState } from "react";

const DEFAULT_DAILY_TARGET = 10;

function GoalCard({ home, goal, loading, onGoalSave }) {
  const dailyGoal = home?.dailyGoal || {};

  const target =
    dailyGoal.targetSessions ||
    goal?.dailyTargetSessions ||
    goal?.daily_target_sessions ||
    DEFAULT_DAILY_TARGET;

  const completed = dailyGoal.completedSessions || 0;
  const remaining = dailyGoal.remainingSessions || 0;
  const achieved = dailyGoal.achieved || false;
  const streakDays = home?.streakDays || 0;

  const [inputGoal, setInputGoal] = useState(target);

  useEffect(() => {
    setInputGoal(target);
  }, [target]);

  const handleSubmit = async (event) => {
    event.preventDefault();

    const nextGoal = Number(inputGoal);

    if (!Number.isFinite(nextGoal) || nextGoal < 1 || nextGoal > 70) {
      alert("하루 목표는 1 이상 70 이하로 입력해 주세요.");
      return;
    }

    await onGoalSave(nextGoal);
  };

  return (
    <article className="card dashboard-panel dashboard-goal-card dashboard-goal-card--merged">
      <div className="dashboard-panel-head dashboard-panel-head--split">
        <div>
          <h3>오늘 목표</h3>
          <p>오늘 목표와 연속 학습 현황을 확인합니다.</p>
        </div>

        <div className="dashboard-streak-mini" aria-label="연속 학습 현황">
          <span className="dashboard-streak-label">연속 학습</span>
          <strong>{streakDays}일</strong>
        </div>
      </div>

      <div className="dashboard-goal-overview">
        <div className="dashboard-goal-progress-block">
          <span className="dashboard-section-label">오늘 진행</span>
          <strong id="dashboard-goal-progress">
            {completed} / {target}
          </strong>
          <p>
            {loading
              ? "오늘 목표를 불러오는 중입니다."
              : achieved
              ? "오늘 목표를 달성했습니다."
              : `오늘 목표까지 ${remaining}문제가 남았습니다.`}
          </p>
        </div>

        <p className="dashboard-goal-note">
          연속 학습은 하루 목표를 달성한 날만 이어집니다.
        </p>
      </div>

      <form className="goal-form" onSubmit={handleSubmit}>
        <label htmlFor="dashboard-goal-input">하루 목표</label>

        <div className="goal-form-row">
          <input
            id="dashboard-goal-input"
            type="number"
            min="1"
            max="70"
            step="1"
            value={inputGoal}
            onChange={(event) => setInputGoal(event.target.value)}
          />
          <button id="dashboard-goal-submit" type="submit" className="primary">
            저장
          </button>
        </div>

        <div id="dashboard-goal-presets" className="preset-row">
          {[10, 20, 30].map((value) => (
            <button
              key={value}
              type="button"
              className="ghost"
              data-goal={value}
              onClick={() => setInputGoal(value)}
            >
              {value}문제
            </button>
          ))}
        </div>
      </form>
    </article>
  );
}

export default GoalCard;
