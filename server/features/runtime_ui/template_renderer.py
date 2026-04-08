from __future__ import annotations

import re
from pathlib import Path

from fastapi.responses import HTMLResponse

_STATIC_ASSET_PATTERN = re.compile(
    r'(?P<prefix>\b(?:href|src)=["\'])(?P<url>/static/[^"\'?#]+)(?:\?[^"\']*)?(?P<suffix>["\'])'
)


def _asset_version(frontend_dir: Path, asset_url: str) -> str:
    asset_path = frontend_dir / asset_url.removeprefix("/static/")
    try:
        stat = asset_path.stat()
    except OSError:
        return asset_url
    return f"{asset_url}?v={stat.st_mtime_ns:x}{stat.st_size:x}"


def inject_asset_versions(template: str, frontend_dir: Path) -> str:
    def _replace(match: re.Match[str]) -> str:
        asset_url = match.group("url")
        versioned = _asset_version(frontend_dir, asset_url)
        return f'{match.group("prefix")}{versioned}{match.group("suffix")}'

    return _STATIC_ASSET_PATTERN.sub(_replace, template)


def render_template_response(
    template_path: Path,
    *,
    frontend_dir: Path,
    template_variant: str,
    vary_user_agent: bool = False,
) -> HTMLResponse:
    content = template_path.read_text(encoding="utf-8")
    rendered = inject_asset_versions(content, frontend_dir)
    response = HTMLResponse(rendered, media_type="text/html; charset=utf-8")
    response.headers["X-Template-Variant"] = template_variant
    if vary_user_agent:
        response.headers["Vary"] = "User-Agent"
    return response
