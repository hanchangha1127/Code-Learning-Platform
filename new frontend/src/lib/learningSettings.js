export const LEARNING_LANGUAGE_KEY = "code-learning-language";
export const LEARNING_DIFFICULTY_KEY = "code-learning-difficulty";

export const LANGUAGE_OPTIONS = [
  { id: "python", title: "Python" },
  { id: "javascript", title: "JavaScript" },
  { id: "c", title: "C" },
  { id: "java", title: "Java" },
  { id: "typescript", title: "TypeScript" },
  { id: "cpp", title: "C++" },
  { id: "csharp", title: "C#" },
  { id: "go", title: "Go" },
  { id: "rust", title: "Rust" },
  { id: "php", title: "PHP" },
  { id: "golfscript", title: "GolfScript" },
];

export const PROFILE_DIFFICULTY_OPTIONS = [
  { id: "easy", runtimeId: "beginner", label: "초급" },
  { id: "medium", runtimeId: "intermediate", label: "중급" },
  { id: "hard", runtimeId: "advanced", label: "고급" },
];

const LANGUAGE_ALIASES = {
  js: "javascript",
  py: "python",
  "c++": "cpp",
  "c#": "csharp",
};

const PROFILE_TO_RUNTIME_DIFFICULTY = {
  easy: "beginner",
  medium: "intermediate",
  hard: "advanced",
  beginner: "beginner",
  intermediate: "intermediate",
  advanced: "advanced",
};

const RUNTIME_TO_PROFILE_DIFFICULTY = {
  beginner: "easy",
  intermediate: "medium",
  advanced: "hard",
  easy: "easy",
  medium: "medium",
  hard: "hard",
};

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

export function normalizeLanguageId(value, fallback = "python") {
  const raw = String(value || "").trim().toLowerCase();
  const normalized = LANGUAGE_ALIASES[raw] || raw;
  return LANGUAGE_OPTIONS.some((language) => language.id === normalized) ? normalized : fallback;
}

export function languageTitle(languageId) {
  const normalized = normalizeLanguageId(languageId);
  return LANGUAGE_OPTIONS.find((language) => language.id === normalized)?.title || normalized;
}

export function normalizeProfileDifficulty(value, fallback = "medium") {
  const raw = String(value || "").trim().toLowerCase();
  return RUNTIME_TO_PROFILE_DIFFICULTY[raw] || fallback;
}

export function normalizeRuntimeDifficulty(value, fallback = "intermediate") {
  const raw = String(value || "").trim().toLowerCase();
  return PROFILE_TO_RUNTIME_DIFFICULTY[raw] || fallback;
}

export function profileDifficultyToRuntime(value) {
  return normalizeRuntimeDifficulty(value);
}

export function runtimeDifficultyToProfile(value) {
  return normalizeProfileDifficulty(value);
}

export function readStoredProfileSettings() {
  if (!canUseStorage()) {
    return { preferred_language: "python", preferred_difficulty: "medium" };
  }
  const language = normalizeLanguageId(window.localStorage.getItem(LEARNING_LANGUAGE_KEY), "python");
  const difficulty = normalizeProfileDifficulty(window.localStorage.getItem(LEARNING_DIFFICULTY_KEY), "medium");
  return { preferred_language: language, preferred_difficulty: difficulty };
}

export function readStoredRuntimeSettings() {
  const stored = readStoredProfileSettings();
  return {
    language: stored.preferred_language,
    difficulty: profileDifficultyToRuntime(stored.preferred_difficulty),
  };
}

export function normalizeProfileSettings(payload, fallback = readStoredProfileSettings()) {
  return {
    preferred_language: normalizeLanguageId(
      payload?.preferred_language ?? payload?.preferredLanguage,
      fallback.preferred_language || "python",
    ),
    preferred_difficulty: normalizeProfileDifficulty(
      payload?.preferred_difficulty ?? payload?.preferredDifficulty,
      fallback.preferred_difficulty || "medium",
    ),
  };
}

export function persistLearningSettings(settings) {
  if (!canUseStorage()) return;
  const normalized = normalizeProfileSettings(settings);
  window.localStorage.setItem(LEARNING_LANGUAGE_KEY, normalized.preferred_language);
  window.localStorage.setItem(
    LEARNING_DIFFICULTY_KEY,
    profileDifficultyToRuntime(normalized.preferred_difficulty),
  );
}
