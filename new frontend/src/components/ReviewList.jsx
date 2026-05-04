function ReviewList({ home, loading }) {
  const reviewQueue = home?.reviewQueue || {};
  const items = Array.isArray(reviewQueue.items) ? reviewQueue.items : [];

  return (
    <article className="card dashboard-panel">
      <div className="dashboard-panel-head">
        <div>
          <h3>복습 목록</h3>
          <p>다시 보면 좋은 문제를 모아두었습니다.</p>
        </div>
      </div>

      <div id="dashboard-review-list" className="review-list">
        {loading ? (
          <p className="empty">복습 목록을 불러오는 중입니다.</p>
        ) : items.length === 0 ? (
          <p className="empty">지금은 복습할 문제가 없습니다.</p>
        ) : (
          items.map((item, index) => (
            <article key={index} className="review-card">
              <div className="review-card-main">
                <div className="review-card-top">
                  <h4>{item.title || "복습 문제"}</h4>
                  <span className="review-priority">
                    우선순위 {item.priority ?? 0}
                  </span>
                </div>

                <div className="review-card-meta">
                  <span className="pill soft">
                    {item.modeLabel || item.mode || "학습"}
                  </span>
                  <span className="review-weakness">
                    {item.weaknessLabel || item.weaknessTag || "약점 보강"}
                  </span>
                </div>
              </div>

              <a
                className="ghost review-card-action"
                href={item.resumeLink || item.actionLink || "/dashboard.html"}
              >
                다시 풀기
              </a>
            </article>
          ))
        )}
      </div>
    </article>
  );
}

export default ReviewList;
