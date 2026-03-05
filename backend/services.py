"""Domain services orchestrating storage, diagnostics, and learning logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import random
from typing import Any, Dict, List, Optional

from backend.ai_client import AIClient
from backend.content import LANGUAGES, TRACKS
from backend import learning_mode_handlers, learning_reporting, learning_tier
from backend.problem_generator import ProblemGenerator
from backend.user_storage import UserStorageManager
from backend.user_service import UserService

DEFAULT_DIAGNOSTIC_TOTAL = 5
DEFAULT_TRACK_ID = "algorithms"
TIER_REVIEW_WINDOW = 10
TIER_ADVANCED_THRESHOLD = 0.8
TIER_INTERMEDIATE_THRESHOLD = 0.6
TIER_BEGINNER_RATIO_LIMIT = 0.7

DIFFICULTY_CHOICES: Dict[str, Dict[str, str]] = {
    "beginner": {"title": "초급", "generator": "beginner"},
    "intermediate": {"title": "중급", "generator": "intermediate"},
    "advanced": {"title": "고급", "generator": "advanced"},
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)
    if not start_dt or not end_dt:
        return None
    delta = end_dt - start_dt
    seconds = delta.total_seconds()
    return seconds if seconds >= 0 else None


def _accuracy_from_events(events: list[dict]) -> float | None:
    attempts = len(events)
    if attempts == 0:
        return None
    correct = sum(1 for event in events if event.get("correct") is True)
    return round((correct / attempts) * 100, 1)


def _lighten_hint(text: str) -> str:
    """Trim and shorten a hint for display."""

    stripped = (text or "").strip()
    if len(stripped) > 280:
        return stripped[:277] + "..."
    return stripped


def _default_profile(username: str) -> Dict[str, Any]:
    now = _utcnow()
    return {
        "type": "profile",
        "username": username,
        "skill_level": "beginner",
        "diagnostic_completed": True,
        "diagnostic_total": 0,
        "diagnostic_given": 0,
        "diagnostic_results": [],
        "pending_problems": [],
        "stats": {"attempts": 0, "correct": 0},
        "created_at": now,
        "updated_at": now,
    }


class LearningService:
    """Handle diagnostics, problem generation, and feedback persistence."""

    def __init__(
        self,
        storage_manager: UserStorageManager,
        ai_client: Optional[AIClient] = None,
        problem_generator: Optional[ProblemGenerator] = None,
    ):
        self.storage_manager = storage_manager
        self.ai_client = ai_client or AIClient()
        self.problem_generator = problem_generator or ProblemGenerator()

    # Catalog lookups -----------------------------------------------------

    def list_tracks(self) -> List[Dict[str, str]]:
        languages = list(LANGUAGES.keys())
        return [
            {
                "id": key,
                "title": meta["title"],
                "description": meta["description"],
                "languages": languages,
            }
            for key, meta in TRACKS.items()
        ]

    def list_languages(self) -> List[Dict[str, str]]:
        return [
            {"id": key, "title": meta["title"], "description": meta["description"]}
            for key, meta in LANGUAGES.items()
        ]

    # Profile -------------------------------------------------------------

    def get_profile(self, username: str) -> Dict[str, Any]:
        storage = self._get_user_storage(username)
        profile = self._ensure_profile(storage, username)
        profile = self._ensure_practice_ready(storage, username, profile)
        answered = len(profile.get("diagnostic_results", []))
        pending = len(profile.get("pending_problems", []))
        total = profile.get("diagnostic_total", DEFAULT_DIAGNOSTIC_TOTAL)
        remaining = max(total - answered, 0)
        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        attempts = len(events)
        correct = sum(1 for event in events if event.get("correct") is True)
        accuracy = round((correct / attempts) * 100, 1) if attempts else 0.0

        return {
            "username": username,
            "skillLevel": profile.get("skill_level", "beginner"),
            "diagnosticCompleted": profile.get("diagnostic_completed", False),
            "diagnosticTotal": total,
            "diagnosticAnswered": answered,
            "diagnosticPending": pending,
            "diagnosticRemaining": remaining,
            "totalAttempts": attempts,
            "correctAnswers": correct,
            "accuracy": accuracy,
        }

    # Problem lifecycle ---------------------------------------------------
    async def request_problem_async(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_problem, username, language_id, difficulty_id)

    async def request_code_block_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_block_problem, username, language_id, difficulty_id)

    async def request_code_arrange_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_arrange_problem, username, language_id, difficulty_id)

    async def request_code_calc_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_calc_problem, username, language_id, difficulty_id)

    async def request_code_error_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_error_problem, username, language_id, difficulty_id)

    async def request_auditor_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_auditor_problem, username, language_id, difficulty_id)

    async def request_context_inference_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_context_inference_problem, username, language_id, difficulty_id)

    async def request_refactoring_choice_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_refactoring_choice_problem, username, language_id, difficulty_id)

    async def request_code_blame_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_blame_problem, username, language_id, difficulty_id)


    async def submit_explanation_async(
        self,
        username: str,
        language_id: str,
        problem_id: str,
        explanation: str,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_explanation, username, language_id, problem_id, explanation)

    async def submit_code_block_answer_async(
        self, username: str, problem_id: str, selected_option: int
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_block_answer, username, problem_id, selected_option)

    async def submit_code_arrange_answer_async(
        self, username: str, problem_id: str, order: List[str]
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_arrange_answer, username, problem_id, order)

    async def submit_code_calc_answer_async(
        self, username: str, problem_id: str, output_text: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_calc_answer, username, problem_id, output_text)

    async def submit_code_error_answer_async(
        self, username: str, problem_id: str, selected_index: int
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_error_answer, username, problem_id, selected_index)

    async def submit_auditor_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_auditor_report, username, problem_id, report)

    async def submit_context_inference_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_context_inference_report, username, problem_id, report)

    async def submit_refactoring_choice_report_async(
        self, username: str, problem_id: str, selected_option: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.submit_refactoring_choice_report,
            username,
            problem_id,
            selected_option,
            report,
        )

    async def submit_code_blame_report_async(
        self, username: str, problem_id: str, selected_commits: List[str], report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.submit_code_blame_report,
            username,
            problem_id,
            selected_commits,
            report,
        )

    def request_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def request_code_block_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_code_block_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_block_answer(self, username: str, problem_id: str, selected_option: int) -> Dict[str, Any]:
        return learning_mode_handlers.submit_code_block_answer(
            self,
            username,
            problem_id,
            selected_option,
            default_track_id=DEFAULT_TRACK_ID,
            utcnow=_utcnow,
        )

    def request_code_calc_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_code_calc_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_calc_answer(self, username: str, problem_id: str, output_text: str) -> Dict[str, Any]:
        return learning_mode_handlers.submit_code_calc_answer(
            self,
            username,
            problem_id,
            output_text,
            utcnow=_utcnow,
        )

    def request_code_error_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_code_error_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_error_answer(self, username: str, problem_id: str, selected_index: int) -> Dict[str, Any]:
        return learning_mode_handlers.submit_code_error_answer(
            self,
            username,
            problem_id,
            selected_index,
            utcnow=_utcnow,
        )

    def request_auditor_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_auditor_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def request_context_inference_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_context_inference_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def request_refactoring_choice_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_refactoring_choice_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def request_code_blame_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_code_blame_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_auditor_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return learning_mode_handlers.submit_auditor_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_context_inference_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return learning_mode_handlers.submit_context_inference_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_refactoring_choice_report(
        self,
        username: str,
        problem_id: str,
        selected_option: str,
        report: str,
    ) -> Dict[str, Any]:
        return learning_mode_handlers.submit_refactoring_choice_report(
            self,
            username,
            problem_id,
            selected_option,
            report,
            utcnow=_utcnow,
        )

    def submit_code_blame_report(
        self,
        username: str,
        problem_id: str,
        selected_commits: List[str],
        report: str,
    ) -> Dict[str, Any]:
        return learning_mode_handlers.submit_code_blame_report(
            self,
            username,
            problem_id,
            selected_commits,
            report,
            utcnow=_utcnow,
        )

    def submit_explanation(
        self,
        username: str,
        language_id: str,
        problem_id: str,
        explanation: str,
    ) -> Dict[str, Any]:
        return learning_mode_handlers.submit_explanation(
            self,
            username,
            language_id,
            problem_id,
            explanation,
            default_track_id=DEFAULT_TRACK_ID,
            utcnow=_utcnow,
        )

    def request_code_arrange_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return learning_mode_handlers.request_code_arrange_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_arrange_answer(self, username: str, problem_id: str, order: List[str]) -> Dict[str, Any]:
        return learning_mode_handlers.submit_code_arrange_answer(
            self,
            username,
            problem_id,
            order,
            utcnow=_utcnow,
        )

    # Reporting -----------------------------------------------------------

    def user_history(self, username: str) -> List[Dict[str, Any]]:
        return learning_reporting.user_history(
            self,
            username,
            duration_seconds=_duration_seconds,
        )

    def user_memory(self, username: str) -> List[Dict[str, Any]]:
        storage = self._get_user_storage(username)
        memory_entries = storage.filter(lambda item: item.get("type") == "memory")
        return sorted(memory_entries, key=lambda item: item.get("created_at", ""), reverse=True)

    def learning_report(self, username: str) -> Dict[str, Any]:
        return learning_reporting.learning_report(
            self,
            username,
            accuracy_from_events=_accuracy_from_events,
            duration_seconds=_duration_seconds,
        )


    # Internal helpers ----------------------------------------------------

    def _get_user_storage(self, username: str):
        try:
            return self.storage_manager.get_storage(username)
        except FileNotFoundError as exc:
            raise ValueError("사용자 저장소를 찾을 수 없습니다.") from exc

    def _ensure_profile(self, storage, username: str) -> Dict[str, Any]:
        profile = storage.find_one(lambda item: item.get("type") == "profile")
        if profile:
            return profile
        default = _default_profile(username)
        storage.append(default)
        return default

    def _update_profile(self, storage, username: str, mutator) -> Dict[str, Any]:
        def predicate(item: Dict[str, Any]) -> bool:
            return item.get("type") == "profile"

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:
            profile = dict(current)
            mutator(profile)
            profile["updated_at"] = _utcnow()
            return profile

        updated = storage.update_record(predicate, updater)
        if updated is not None:
            return updated

        profile = _default_profile(username)
        mutator(profile)
        profile["updated_at"] = _utcnow()
        storage.append(profile)
        return profile

    def _profile_after_assignment(self, profile: Dict[str, Any], problem_id: str, diagnostic: bool) -> Dict[str, Any]:
        pending = list(profile.get("pending_problems", []))
        pending.append(problem_id)
        profile["pending_problems"] = pending
        if diagnostic:
            profile["diagnostic_given"] = int(profile.get("diagnostic_given", 0)) + 1
        return profile

    def _profile_after_submission(
        self,
        profile: Dict[str, Any],
        problem_id: str,
        score: Optional[float],
        mode: Optional[str],
        is_correct: Optional[bool],
    ) -> Dict[str, Any]:
        profile["pending_problems"] = [
            pid for pid in profile.get("pending_problems", []) if pid != problem_id
        ]

        stats = dict(profile.get("stats", {"attempts": 0, "correct": 0}))
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if is_correct is True:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["correct"] = int(stats.get("correct", 0))
        profile["stats"] = stats

        if mode == "diagnostic":
            score_value = float(score) if score is not None else 50.0
            results = list(profile.get("diagnostic_results", []))
            results.append(
                {
                    "problem_id": problem_id,
                    "score": score_value,
                    "correct": is_correct,
                    "created_at": _utcnow(),
                }
            )
            profile["diagnostic_results"] = results

            total = max(profile.get("diagnostic_total", DEFAULT_DIAGNOSTIC_TOTAL), 1)
            if len(results) >= total:
                average_points = sum(item.get("score", 0.0) for item in results[-total:]) / total
                profile["skill_level"] = self._score_to_level(average_points / 100.0)
                profile["diagnostic_completed"] = True

        if profile.get("diagnostic_completed") and not profile.get("skill_level"):
            profile["skill_level"] = "beginner"

        return profile

    def _ensure_practice_ready(self, storage, username: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        if profile.get("diagnostic_completed", False):
            return profile
        return self._update_profile(storage, username, self._mark_practice_ready)

    def _mark_practice_ready(self, profile: Dict[str, Any]) -> None:
        profile["diagnostic_completed"] = True
        profile["diagnostic_total"] = 0
        profile["diagnostic_given"] = 0
        profile["diagnostic_results"] = []

    def _score_to_level(self, score: float) -> str:
        if score < 0.45:
            return "beginner"
        if score < 0.75:
            return "intermediate"
        return "advanced"

    def _accuracy_to_level(self, accuracy: float) -> str:
        if accuracy >= TIER_ADVANCED_THRESHOLD:
            return "advanced"
        if accuracy >= TIER_INTERMEDIATE_THRESHOLD:
            return "intermediate"
        return "beginner"

    def _collect_attempt_events(self, storage) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        events.extend(storage.filter(lambda item: item.get("type") == "learning_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_calc_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_error_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_arrange_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "auditor_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "context_inference_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "refactoring_choice_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_blame_event"))
        return events

    def _instances_by_id(self, storage) -> Dict[str, Dict[str, Any]]:
        instances: Dict[str, Dict[str, Any]] = {}
        for item in storage.filter(lambda it: it.get("type") == "problem_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_block_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_calc_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_error_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_arrange_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "auditor_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "context_inference_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "refactoring_choice_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_blame_instance"):
            instances[item.get("problem_id")] = item
        return instances

    def _recent_attempts(self, storage, limit: int = TIER_REVIEW_WINDOW) -> List[Dict[str, Any]]:
        return learning_tier.recent_attempts(self, storage, limit=limit)

    def _update_tier_if_needed(self, storage, username: str) -> None:
        learning_tier.update_tier_if_needed(
            self,
            storage,
            username,
            tier_review_window=TIER_REVIEW_WINDOW,
            tier_beginner_ratio_limit=TIER_BEGINNER_RATIO_LIMIT,
            utcnow=_utcnow,
        )


    def _get_problem_instance(self, storage, problem_id: str) -> Optional[Dict[str, Any]]:
        return storage.find_one(
            lambda item: item.get("type") == "problem_instance" and item.get("problem_id") == problem_id
        )

    def _code_block_history_context(self, storage, limit: int = 5) -> Optional[str]:
        instances = storage.filter(lambda item: item.get("type") == "code_block_instance")
        if not instances:
            return None
        sorted_items = sorted(instances, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "제목 없음"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            lines.append(f"{idx}. {lang}/{diff} · {title} · 코드 첫 줄: {first_line}")
        return "\n".join(lines)

    def get_problem_hint(self, username: str, problem_id: str) -> Dict[str, str]:
        storage = self._get_user_storage(username)
        instance = self._get_problem_instance(storage, problem_id)
        if not instance:
            raise ValueError("요청한 문제를 찾을 수 없습니다. 다시 불러와 주세요.")

        reference = instance.get("reference") or ""
        prompt = instance.get("prompt") or ""
        source = reference or prompt or "힌트가 준비되지 않았습니다."
        return {"hint": _lighten_hint(source)}

    def _get_last_learning_event(self, storage) -> Optional[Dict[str, Any]]:
        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        if not events:
            return None
        # Sort by created_at descending and take the first one
        return sorted(events, key=lambda item: item.get("created_at", ""), reverse=True)[0]

    def _problem_history_context(self, storage, limit: int = 5) -> Optional[str]:
        """Summarize recent learning events so the generator can avoid duplicates."""

        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        if not events:
            return None

        instances = {
            item.get("problem_id"): item
            for item in storage.filter(lambda entry: entry.get("type") == "problem_instance")
        }

        sorted_events = sorted(events, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, event in enumerate(sorted_events, start=1):
            language_id = event.get("language")
            language_label = LANGUAGES.get(language_id, {}).get("title", language_id or "-")
            difficulty = event.get("difficulty") or "-"
            verdict = event.get("correct")
            verdict_label = "정답" if verdict is True else "오답" if verdict is False else "미정"
            instance = instances.get(event.get("problem_id")) or {}
            title = instance.get("title") or ""
            prompt = instance.get("prompt") or ""
            feedback = event.get("feedback") or {}
            summary = ""
            if isinstance(feedback, dict):
                summary = feedback.get("summary") or ""
            if not summary:
                summary = prompt or (event.get("explanation") or "")[:160]
            summary = summary.replace("\n", " ").strip()
            topic = title or prompt.splitlines()[0] if prompt else ""
            duration = _duration_seconds(instance.get("created_at"), event.get("created_at"))
            duration_label = f"{int(duration)}초" if duration is not None else "시간 미기록"
            lines.append(
                f"{idx}. {language_label}/{difficulty} · {verdict_label} · "
                f"주제: {topic or '제목 없음'} · 요약: {summary} · 소요시간: {duration_label}"
            )
        return "\n".join(lines)

    def _code_calc_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_calc_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "미정 제목"
            lang = item.get("language") or "-"
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            lines.append(f"{idx}. {lang} · {title} · 첫줄: {first_line}")
        return "\n".join(lines)

    def _code_error_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_error_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "미정 제목"
            lang = item.get("language") or "-"
            sample = (item.get("blocks") or [])
            first = sample[0].splitlines()[0] if sample else ""
            lines.append(f"{idx}. {lang} · {title} · 첫줄: {first}")
        return "\n".join(lines)

    def _auditor_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "auditor_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            trap_count = item.get("trap_count") or len(item.get("trap_catalog") or [])
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            lines.append(f"{idx}. {lang}/{diff} - traps {trap_count} - {title} - first line: {first_line}")
        return "\n".join(lines)

    def _context_inference_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "context_inference_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            inference_type = item.get("inference_type") or "-"
            first_line = (item.get("snippet") or "").splitlines()[0] if item.get("snippet") else ""
            lines.append(f"{idx}. {lang}/{diff} - {inference_type} - {title} - first line: {first_line}")
        return "\n".join(lines)

    def _refactoring_choice_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "refactoring_choice_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            best_option = item.get("best_option") or "-"
            scenario = (item.get("scenario") or "").splitlines()[0] if item.get("scenario") else ""
            lines.append(f"{idx}. {lang}/{diff} - best {best_option} - {title} - scenario: {scenario}")
        return "\n".join(lines)

    def _code_blame_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_blame_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            commit_count = len(item.get("commits") or [])
            log_head = (item.get("error_log") or "").splitlines()[0] if item.get("error_log") else ""
            lines.append(f"{idx}. {lang}/{diff} - commits {commit_count} - {title} - log: {log_head}")
        return "\n".join(lines)

    def _chunk_and_shuffle_code(self, code: str) -> Dict[str, Any]:
        """Split code into 2~3 line chunks, keep correct order, and return a shuffled variant."""

        raw_lines = [line for line in (code or "").splitlines() if line.strip() != ""]
        chunks: List[List[str]] = []
        idx = 0
        while idx < len(raw_lines):
            remaining = len(raw_lines) - idx
            group_size = 3 if remaining >= 5 else 2 if remaining >= 2 else 1
            chunk = raw_lines[idx : idx + group_size]
            chunks.append(chunk)
            idx += group_size

        ordered_blocks = []
        for i, chunk in enumerate(chunks):
            ordered_blocks.append({"id": f"blk-{i+1}", "code": "\n".join(chunk)})

        shuffled_blocks = ordered_blocks.copy()
        random.shuffle(shuffled_blocks)

        return {"ordered": ordered_blocks, "shuffled": shuffled_blocks}

    def _build_report_recommendations(
        self,
        history: List[Dict[str, Any]],
        strengths: Dict[str, int],
        improvements: Dict[str, int],
    ) -> List[str]:
        recommendations: List[str] = []
        recent_incorrect = [event for event in history if event.get("correct") is False][:3]
        if recent_incorrect:
            failed_topics = ", ".join(
                f"{LANGUAGES.get(evt.get('language'), {}).get('title', evt.get('language', '-'))}/{evt.get('difficulty')}"
                for evt in recent_incorrect
            )
            recommendations.append(f"최근 틀린 주제 다시 보기: {failed_topics}")

        if strengths:
            top_strength = max(strengths.items(), key=lambda item: item[1])[0]
            recommendations.append(f"강점 보강: '{top_strength}' 문제를 더 풀어보세요.")

        if improvements:
            top_gap = max(improvements.items(), key=lambda item: item[1])[0]
            recommendations.append(f"취약 보완: '{top_gap}' 유형을 집중 연습하세요.")

        if not recommendations:
            recommendations.append("추가 권장 사항이 없습니다. 현재 페이스를 유지하세요.")
        return recommendations
