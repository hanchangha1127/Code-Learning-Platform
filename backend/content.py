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
}
