import { BrandIcon } from "./SvgIcon.jsx";
import { clearSession } from "../lib/apiClient.js";

export function AppShell({ children, title = "코드 학습", subtitle = "Code Reading Lab", active = "", actions = null }) {
  return (
    <section className="app dashboard-shell route-page">
      <header className="app-header page-header dashboard-topbar">
        <a className="brand-lockup" href="/dashboard.html">
          <span className="brand-mark">
            <BrandIcon />
          </span>
          <div>
            <p className="eyebrow">{subtitle}</p>
            <h1>{title}</h1>
          </div>
        </a>
        <nav className="header-actions" aria-label="주요 이동">
          <a className={active === "dashboard" ? "primary" : "ghost"} href="/dashboard.html">대시보드</a>
          <a className={active === "profile" ? "primary" : "ghost"} href="/profile.html">프로필</a>
          <a className={active === "problems" ? "primary" : "ghost"} href="/problems.html">문제</a>
          {actions}
          <button
            type="button"
            className="ghost"
            onClick={async () => {
              await clearSession();
              window.location.replace("/index.html");
            }}
          >
            로그아웃
          </button>
        </nav>
      </header>
      {children}
    </section>
  );
}

export function LoadingScreen() {
  return <main className="dashboard-main"><section className="card dashboard-panel">세션을 확인하는 중입니다...</section></main>;
}
