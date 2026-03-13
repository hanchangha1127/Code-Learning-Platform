(() => {
  function getResumeReviewId() {
    const raw = new URLSearchParams(window.location.search).get("resume_review");
    if (!raw) return null;
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return parsed;
  }

  function clearResumeReviewId() {
    const url = new URL(window.location.href);
    url.searchParams.delete("resume_review");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function resumeReviewProblem({
    mode,
    apiRequest,
    applyProblem,
    onStatus = null,
    onError = null,
  }) {
    const itemId = getResumeReviewId();
    if (!itemId) {
      return false;
    }

    if (typeof apiRequest !== "function") {
      throw new Error("resumeReviewProblem requires an apiRequest function.");
    }
    if (typeof applyProblem !== "function") {
      throw new Error("resumeReviewProblem requires an applyProblem function.");
    }

    if (typeof onStatus === "function") {
      onStatus("복습 문제를 다시 불러오는 중입니다.");
    }

    try {
      const payload = await apiRequest(`/platform/review-queue/${itemId}/resume`);
      if (String(payload?.mode || "").trim().toLowerCase() !== String(mode || "").trim().toLowerCase()) {
        throw new Error("현재 페이지와 맞지 않는 복습 문제입니다.");
      }
      if (!payload?.problem || typeof payload.problem !== "object") {
        throw new Error("복습 문제 데이터가 비어 있습니다.");
      }

      await applyProblem(payload.problem, payload);

      if (typeof onStatus === "function") {
        onStatus("같은 문제를 다시 열었습니다. 이어서 복습해 보세요.");
      }
      return true;
    } catch (error) {
      clearResumeReviewId();
      if (typeof onError === "function") {
        onError(error);
      } else if (typeof onStatus === "function") {
        onStatus(error?.message || "복습 문제를 다시 열지 못했습니다.");
      }
      return false;
    }
  }

  window.CodeReviewResume = {
    getResumeReviewId,
    clearResumeReviewId,
    resumeReviewProblem,
  };
})();
