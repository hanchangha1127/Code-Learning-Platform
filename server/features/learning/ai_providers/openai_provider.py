from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request

from server.infra.admin_metrics import get_admin_metrics

from .base import AnalysisResult


def _extract_json_blob(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "{}"

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and first < last:
        return cleaned[first : last + 1].strip()

    return cleaned


def _clamp_score(value: Any) -> int:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, numeric))


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: int = 30,
        metrics: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = max(timeout_seconds, 5)
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.metrics = metrics or get_admin_metrics()

    def _start_metrics_token(self) -> Any | None:
        try:
            return self.metrics.start_ai_call(provider="openai", operation="submission_analysis")
        except Exception:
            return None

    def _finish_metrics_token(self, token: Any | None, *, success: bool) -> None:
        if token is None:
            return
        try:
            self.metrics.end_ai_call(token, success=success)
        except Exception:
            return

    def analyze(self, *, language: str, code: str, problem_prompt: str) -> AnalysisResult:
        metrics_token = self._start_metrics_token()
        system_prompt = (
            "You are a strict code reviewer. Return ONLY JSON with this schema: "
            '{"status":"passed|failed","score":0-100,"summary":"short text","detail":{"strengths":[],"improvements":[]}}.'
        )
        user_prompt = (
            f"Language: {language}\n"
            f"Problem: {problem_prompt}\n"
            f"Code:\n{code}\n"
            "Evaluate correctness first, then quality."
        )

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                raise RuntimeError(f"OpenAI API error ({exc.code}): {detail[:300]}") from exc
            except Exception as exc:
                raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

            try:
                data = json.loads(raw)
                content = data["choices"][0]["message"]["content"]
            except Exception as exc:
                raise RuntimeError(f"Invalid OpenAI response payload: {exc}") from exc

            if isinstance(content, list):
                # Defensive: some SDK/formatters may return segmented content.
                content = "\n".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )

            try:
                parsed = json.loads(_extract_json_blob(str(content)))
            except json.JSONDecodeError:
                parsed = {
                    "status": "failed",
                    "score": 0,
                    "summary": "ai_response_parse_failed",
                    "detail": {"raw": str(content)[:1000]},
                }

            status_raw = str(parsed.get("status", "failed")).lower()
            if status_raw not in {"passed", "failed"}:
                status_raw = "passed" if bool(parsed.get("correct")) else "failed"

            result = AnalysisResult(
                status="passed" if status_raw == "passed" else "failed",
                score=_clamp_score(parsed.get("score")),
                summary=str(parsed.get("summary") or "analysis_completed")[:200],
                detail=parsed.get("detail") if isinstance(parsed.get("detail"), (dict, list, str, int, float, bool, type(None))) else str(parsed.get("detail")),
            )
        except Exception:
            self._finish_metrics_token(metrics_token, success=False)
            raise

        self._finish_metrics_token(metrics_token, success=True)
        return result
