const MODE_LABELS = {
  analysis: "코드 분석",
  "code-block": "코드 블록",
  "code-arrange": "코드 배치",
  auditor: "감사관 모드",
  "refactoring-choice": "최적안 선택",
  "code-blame": "범인 찾기",
  "single-file-analysis": "단일 파일 분석",
  "multi-file-analysis": "멀티 파일 분석",
  "fullstack-analysis": "풀스택 분석",
};

const MODE_LABEL_ALIASES = {
  "코드 해석": "코드 분석",
  "순서 맞추기": "코드 배치",
  "코드 점검": "감사관 모드",
  "리팩터링 방식 선택": "최적안 선택",
  "최적의 선택": "최적안 선택",
  "원인 커밋 찾기": "범인 찾기",
};

export function displayModeLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "학습";
  return MODE_LABELS[text] || MODE_LABEL_ALIASES[text] || text;
}
