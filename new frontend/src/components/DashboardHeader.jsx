import { BrandIcon } from "./SvgIcon.jsx";

function DashboardHeader({ onLogout }) {
  return (
    <header className="app-header page-header dashboard-topbar">
      <div className="brand-lockup">
        <span className="brand-mark">
          <BrandIcon />
        </span>
        <div>
          <p className="eyebrow">Code Reading Lab</p>
          <h1>코드 학습 대시보드</h1>
        </div>
      </div>

      <div className="header-actions">
        <a className="ghost" href="/profile.html">
          프로필
        </a>
        <button type="button" className="primary" onClick={onLogout}>
          로그아웃
        </button>
      </div>
    </header>
  );
}

export default DashboardHeader;
