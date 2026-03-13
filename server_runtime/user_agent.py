from __future__ import annotations


def is_mobile_user_agent(user_agent: str | None) -> bool:
    value = (user_agent or "").strip().lower()
    if not value:
        return False

    if "ipad" in value or "tablet" in value:
        return False

    if "iphone" in value or "ipod" in value:
        return True

    if "android" in value and "mobile" in value:
        return True

    if "mobile" in value:
        return True

    return False
