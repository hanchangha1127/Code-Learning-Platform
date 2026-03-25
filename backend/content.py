"""초기 로드 단계에서 사용하는 기본 학습 분류 정보."""

from __future__ import annotations

from typing import Dict


TRACKS: Dict[str, Dict[str, str]] = {
    "algorithms": {
        "title": "알고리즘",
        "description": "문제 해결력을 키워 주는 핵심 알고리즘 패턴을 학습합니다.",
    },
    "backend": {
        "title": "백엔드",
        "description": "서버 로직과 데이터 처리를 중심으로 시스템 동작을 분석합니다.",
    },
    "frontend": {
        "title": "프런트엔드",
        "description": "UI 중심의 JavaScript 코드 구조를 이해하고 개선합니다.",
    },
}


LANGUAGES: Dict[str, Dict[str, str]] = {
    "python": {
        "title": "파이썬",
        "description": "간결한 문법과 풍부한 라이브러리로 빠르게 로직을 구현할 수 있습니다.",
    },
    "javascript": {
        "title": "자바스크립트",
        "description": "브라우저와 서버 모두에서 사용되는 대표적인 스크립트 언어입니다.",
    },
    "c": {
        "title": "C",
        "description": "저수준 메모리 제어와 높은 성능이 필요한 시스템 개발에 적합합니다.",
    },
    "java": {
        "title": "자바",
        "description": "대규모 서비스와 기업 애플리케이션에서 널리 사용되는 객체지향 언어입니다.",
    },
    "typescript": {
        "title": "타입스크립트",
        "description": "정적 타입을 통해 대규모 프런트엔드와 서버 코드를 더 안정적으로 다룰 수 있습니다.",
    },
    "cpp": {
        "title": "C++",
        "description": "성능과 추상화 균형이 중요한 시스템, 게임, 인프라 개발에 널리 쓰입니다.",
    },
    "csharp": {
        "title": "C#",
        "description": ".NET 생태계에서 서비스, 데스크톱, 게임 개발까지 폭넓게 활용됩니다.",
    },
    "go": {
        "title": "Go",
        "description": "간결한 문법과 강한 동시성 모델 덕분에 서버와 인프라 개발에 적합합니다.",
    },
    "rust": {
        "title": "Rust",
        "description": "메모리 안전성과 성능을 함께 요구하는 시스템 프로그래밍에 강합니다.",
    },
    "php": {
        "title": "PHP",
        "description": "웹 백엔드와 CMS 생태계에서 여전히 널리 쓰이는 서버 스크립트 언어입니다.",
    },
}

LANGUAGE_ALIASES: Dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "c++": "cpp",
    "cs": "csharp",
    "c#": "csharp",
}


def normalize_language_id(language_id: str | None) -> str | None:
    value = str(language_id or "").strip().lower()
    if not value:
        return None
    if value in LANGUAGES:
        return value
    return LANGUAGE_ALIASES.get(value)
