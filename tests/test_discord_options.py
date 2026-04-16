"""Tests for :class:`~team_alerts.discord_options.DiscordTransportOptions`."""

from __future__ import annotations

import pytest

from team_alerts.discord_options import DiscordTransportOptions


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


def test_from_env_metadata_url_link_style(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "markdown")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "markdown"
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "labeled")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "markdown"
    monkeypatch.setenv("TEAM_ALERTS_METADATA_URL_STYLE", "angle")
    assert DiscordTransportOptions.from_env().metadata_url_link_style == "angle"
