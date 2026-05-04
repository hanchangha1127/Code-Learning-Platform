import { BrandIcon } from "./SvgIcon.jsx";

function Profile() {
  return (
    <section id="profile-section" className="app dashboard-shell profile-shell">
      <header className="app-header page-header dashboard-topbar">
        <div className="brand-lockup">
          <span className="brand-mark">
            <BrandIcon />
          </span>
          <div>
            <p className="eyebrow">Account</p>
            <h1>프로필</h1>
          </div>
        </div>

        <div className="header-actions">
          <a href="/dashboard.html" className="ghost">
            대시보드
          </a>
        </div>
      </header>

      <main className="profile-grid">
        <aside className="card dashboard-panel profile-summary-card">
          <p className="dashboard-section-label">학습자 카드</p>
          <div className="profile-identity">
            <div className="profile-avatar" aria-hidden="true">
              <BrandIcon />
            </div>
            <div>
              <h2>사용자</h2>
              <span className="pill soft">레벨 -</span>
              <p>
                저장된 학습 기록과 설정을 기준으로 훈련 모드가 시작됩니다.
              </p>
            </div>
          </div>

          <div className="profile-action-list">
            <button className="profile-action" type="button">
              <span>오답 노트</span>
              <small>틀린 문제와 해설 기록을 다시 확인합니다.</small>
            </button>
            <button className="profile-action" type="button">
              <span>학습 리포트</span>
              <small>최근 학습 흐름과 분석 결과를 확인합니다.</small>
            </button>
          </div>
        </aside>

        <section className="card dashboard-panel profile-settings-card">
          <div className="dashboard-panel-head">
            <div>
              <h3>학습 요약</h3>
            </div>
          </div>

          <div className="profile-stat-grid">
            <article>
              <span>누적 풀이</span>
              <strong>-</strong>
              <p>전체 풀이 수</p>
            </article>
            <article>
              <span>정답률</span>
              <strong>-</strong>
              <p>최근 기록 기준 정답률</p>
            </article>
            <article>
              <span>최근 7일</span>
              <strong>-</strong>
              <p>최근 7일 풀이 수</p>
            </article>
            <article>
              <span>복습 대기</span>
              <strong>-</strong>
              <p>다시 볼 문제 수</p>
            </article>
          </div>
        </section>
      </main>
    </section>
  );
}

export default Profile;
