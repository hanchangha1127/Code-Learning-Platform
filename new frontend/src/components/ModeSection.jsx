import { useState } from "react";
import { ModeIcon } from "./SvgIcon.jsx";

const features = [
  {
    id: "analysis",
    title: "코드 분석",
    description: "코드를 읽고 흐름, 상태 변화, 출력 결과를 설명해 봅니다.",
    icon: "analysis",
    link: "/analysis.html",
  },
  {
    id: "code-block",
    title: "코드 블록",
    description: "빈칸을 채우고 정답을 고르며 문맥을 파악합니다.",
    icon: "code-block",
    link: "/codeblock.html",
  },
  {
    id: "code-arrange",
    title: "코드 배치",
    description: "섞인 코드 블록을 올바른 순서로 배치합니다.",
    icon: "code-arrange",
    link: "/arrange.html",
  },
  {
    id: "auditor",
    title: "감사관 모드",
    description: "숨은 위험을 찾아 이유가 담긴 감사 리포트를 작성합니다.",
    icon: "auditor",
    link: "/auditor.html",
  },
  {
    id: "refactoring-choice",
    title: "최적안 선택",
    description: "여러 구현 중 제약에 맞는 최적안을 고르고 근거를 작성합니다.",
    icon: "refactoring-choice",
    link: "/refactoring-choice.html",
  },
  {
    id: "code-blame",
    title: "범인 찾기",
    description: "오류 로그와 커밋 diff를 비교해 원인 커밋을 추리합니다.",
    icon: "code-blame",
    link: "/code-blame.html",
  },
];

const advancedFeatures = [
  {
    id: "single-file-analysis",
    title: "단일 파일 분석",
    description: "하나의 파일을 IDE처럼 살펴보며 끝까지 분석합니다.",
    icon: "single-file-analysis",
    link: "/single-file-analysis.html",
  },
  {
    id: "multi-file-analysis",
    title: "멀티 파일 분석",
    description: "여러 파일 사이의 호출 흐름과 책임 분리를 추적합니다.",
    icon: "multi-file-analysis",
    link: "/multi-file-analysis.html",
  },
  {
    id: "fullstack-analysis",
    title: "풀스택 코드 분석",
    description: "프론트엔드, API, 백엔드 흐름을 연결해 해석합니다.",
    icon: "fullstack-analysis",
    link: "/fullstack-analysis.html",
  },
];

function ModeSection({ recommendedModes }) {
  const [activeTab, setActiveTab] = useState("general");

  const recommendedSet = new Set(
    Array.isArray(recommendedModes)
      ? recommendedModes.map((item) => String(item.mode || "").trim().toLowerCase())
      : []
  );

  const currentFeatures = activeTab === "general" ? features : advancedFeatures;

  return (
    <section className="card dashboard-panel dashboard-mode-section">
      <div className="dashboard-panel-head">
        <div>
          <h3>학습 모드</h3>
          <p>추천 모드로 시작하거나 원하는 훈련을 바로 선택하세요.</p>
        </div>
      </div>

      <div id="dashboard-mode-tabs" className="dashboard-mode-tabs" role="tablist" aria-label="학습 모드 전환">
        <button
          id="dashboard-mode-tab-general"
          type="button"
          className={`dashboard-mode-tab ${activeTab === "general" ? "is-active" : ""}`}
          onClick={() => setActiveTab("general")}
        >
          일반 모드
        </button>

        <button
          id="dashboard-mode-tab-advanced"
          type="button"
          className={`dashboard-mode-tab ${activeTab === "advanced" ? "is-active" : ""}`}
          onClick={() => setActiveTab("advanced")}
        >
          고급 모드
        </button>
      </div>

      <div
        id={activeTab === "general" ? "dashboard-mode-panel-general" : "dashboard-mode-panel-advanced"}
        data-mode-panel={activeTab}
        className="dashboard-mode-panel is-active"
      >
        <div className="feature-grid">
          {currentFeatures.map((feature) => (
            <a key={feature.id} href={feature.link} className="feature-card">
              {recommendedSet.has(feature.id) && (
                <span className="badge soft">추천</span>
              )}

              <div className="feature-icon" aria-hidden="true">
                <ModeIcon type={feature.icon} />
              </div>

              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

export default ModeSection;
