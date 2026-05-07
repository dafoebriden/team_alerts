"""Pytest hooks and local test environment loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_DISCORD_OPTIONS_ENV_KEYS = (
    "GITHUB_REPOSITORY",
    "GITHUB_SHA",
    "GIT_COMMIT",
    "GITHUB_REF_NAME",
    "GITHUB_SERVER_URL",
    "TEAM_ALERTS_GITHUB_SOURCE_ROOT",
    "TEAM_ALERTS_ATTACH_EXCEPTION_OVER",
    "TEAM_ALERTS_ENV_METADATA",
    "TEAM_ALERTS_METADATA_URL_STYLE",
    "TEAM_ALERTS_ALERT_BANNER",
    "TEAM_ALERTS_USE_EMBEDS",
    "TEAM_ALERTS_ALERT_FOOTER",
    "TEAM_ALERTS_EMBED_FOOTER",
    "TEAM_ALERTS_ALLOWED_ROLE_IDS",
    "TEAM_ALERTS_ALLOWED_USER_IDS",
    "TEAM_ALERTS_ALLOW_EVERYONE_MENTION",
    "TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS",
)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()
    if "=" not in stripped:
        return None
    key, _, raw_value = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def _load_dotenv_local() -> None:
    """Populate ``os.environ`` from ``.env.local`` at repo root if the file exists."""
    root = Path(__file__).resolve().parent.parent
    path = root / ".env.local"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)


_load_dotenv_local()


@pytest.fixture(autouse=True)
def _clear_discord_options_env_for_unit_tests(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    path = getattr(request.node, "path", None)
    if path is not None and path.name == "test_live_discord.py":
        return
    for key in _DISCORD_OPTIONS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
