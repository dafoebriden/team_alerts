"""Tests for :class:`~team_alerts.discord_options.DiscordTransportOptions`."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from team_alerts.discord_options import DiscordTransportOptions


def _merge_like_discord_transport(
    *,
    options: DiscordTransportOptions | None = None,
    **kwargs: Any,
) -> DiscordTransportOptions:
    out = DiscordTransportOptions.from_env()
    if options is not None:
        out = replace(out, **options.nondefault_option_overrides())
    if kwargs:
        out = replace(out, **kwargs)
    return out


def test_from_env_github_and_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_SHA", "deadbeef")
    monkeypatch.setenv("TEAM_ALERTS_GITHUB_SOURCE_ROOT", "/src")
    monkeypatch.setenv("TEAM_ALERTS_ATTACH_EXCEPTION_OVER", "500")
    monkeypatch.setenv("TEAM_ALERTS_ENV_METADATA", "CI_JOB_URL,MISSING")

    opts = DiscordTransportOptions.from_env()
    assert opts.github is not None
    assert opts.github.repository == "org/repo"
    assert opts.github.ref == "deadbeef"
    assert opts.github.source_root == "/src"
    assert opts.attach_exception_over_chars == 500
    assert "CI_JOB_URL" in opts.env_metadata_keys


def test_from_env_without_github_when_repo_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    opts = DiscordTransportOptions.from_env()
    assert opts.github is None


def test_from_env_alert_banner_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_ALERT_BANNER", "0")
    assert DiscordTransportOptions.from_env().alert_banner == ""


def test_from_env_alert_banner_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_ALERT_BANNER", "~~~ staging ~~~")
    assert DiscordTransportOptions.from_env().alert_banner == "~~~ staging ~~~"


def test_from_env_use_embeds_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEAM_ALERTS_USE_EMBEDS", raising=False)
    assert DiscordTransportOptions.from_env().use_embeds is True


def test_from_env_use_embeds_plain_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_USE_EMBEDS", "plain")
    assert DiscordTransportOptions.from_env().use_embeds is False


def test_from_env_webhook_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "1")
    assert DiscordTransportOptions.from_env().webhook_max_attempts == 1
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "7")
    assert DiscordTransportOptions.from_env().webhook_max_attempts == 7


def test_from_env_metadata_url_link_style(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "markdown")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "markdown"
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "labeled")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "markdown"
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "angle")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "angle"


def test_from_env_severity_render_style(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_SEVERITY_RENDER_STYLE", "label")
    assert DiscordTransportOptions.from_env().severity_render_style == "label"
    monkeypatch.setenv("TEAM_ALERTS_SEVERITY_RENDER_STYLE", "emoji")
    assert DiscordTransportOptions.from_env().severity_render_style == "emoji"
    monkeypatch.setenv("TEAM_ALERTS_SEVERITY_RENDER_STYLE", "invalid")
    assert DiscordTransportOptions.from_env().severity_render_style == "emoji"


def test_nondefault_option_overrides_only_differs_from_defaults() -> None:
    opts = DiscordTransportOptions(use_embeds=False, webhook_max_attempts=5)
    keys = set(opts.nondefault_option_overrides())
    assert "use_embeds" in keys
    assert "webhook_max_attempts" in keys
    assert "github" not in keys


def test_merge_env_only_when_no_explicit_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_SHA", "abc")
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "9")
    merged = _merge_like_discord_transport()
    assert merged.github is not None
    assert merged.github.repository == "org/repo"
    assert merged.webhook_max_attempts == 9


def test_merge_explicit_options_patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_USE_EMBEDS", "1")
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "9")
    merged = _merge_like_discord_transport(
        options=DiscordTransportOptions(use_embeds=False, webhook_max_attempts=2),
    )
    assert merged.use_embeds is False
    assert merged.webhook_max_attempts == 2


def test_merge_env_keeps_field_when_options_matches_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "9")
    merged = _merge_like_discord_transport(options=DiscordTransportOptions(webhook_max_attempts=3))
    assert merged.webhook_max_attempts == 9


def test_merge_env_keeps_field_when_options_value_equals_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAM_ALERTS_USE_EMBEDS", "plain")
    merged = _merge_like_discord_transport(options=DiscordTransportOptions(use_embeds=True))
    assert merged.use_embeds is False


def test_merge_kwargs_override_env_even_when_options_matches_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAM_ALERTS_USE_EMBEDS", "plain")
    merged = _merge_like_discord_transport(
        options=DiscordTransportOptions(use_embeds=True),
        use_embeds=True,
    )
    assert merged.use_embeds is True


def test_from_env_metadata_embed_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_METADATA_EMBED_FIELDS_INLINE", "false")
    monkeypatch.setenv("TEAM_ALERTS_METADATA_EMBED_FIELD_ORDER", "alphabetical")
    monkeypatch.setenv("TEAM_ALERTS_METADATA_CODE_FENCE", "off")
    monkeypatch.setenv("TEAM_ALERTS_METADATA_CODE_FENCE_KEYS", "a,b")
    monkeypatch.setenv("TEAM_ALERTS_METADATA_PLAIN_KEYS", "c")

    opts = DiscordTransportOptions.from_env()
    assert opts.metadata_embed_fields_inline is False
    assert opts.metadata_embed_field_order == "alphabetical"
    assert opts.metadata_code_fence_style == "off"
    assert opts.metadata_code_fence_keys == ("a", "b")
    assert opts.metadata_plain_keys == ("c",)
