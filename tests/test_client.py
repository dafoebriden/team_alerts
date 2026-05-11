"""Tests for ``AlertClient``."""

from __future__ import annotations

import pytest

from team_alerts.client import AlertClient
from team_alerts.constants import Severity
from team_alerts.discord_options import DiscordTransportOptions
from team_alerts.exceptions import ConfigurationError
from team_alerts.models import Alert
from team_alerts.result import SendResult
from team_alerts.transports.discord import DiscordTransport


class DummyTransport:
    def __init__(self) -> None:
        self.calls: list[Alert] = []

    def send(self, alert: Alert) -> SendResult:
        self.calls.append(alert)
        return SendResult(success=True, status_code=200, response_text="ok")


def test_client_send_delegates_to_transport() -> None:
    dummy = DummyTransport()
    client = AlertClient(dummy)
    alert = Alert(message="x", severity=Severity.LOW)
    result = client.send(alert)
    assert result.success
    assert dummy.calls == [alert]


def test_client_severity_helpers() -> None:
    dummy = DummyTransport()
    client = AlertClient(dummy)

    client.low("a", title="t")
    client.high("b", metadata={"k": "v"})
    client.critical("c", service="s", environment="e")

    assert len(dummy.calls) == 3
    assert dummy.calls[0].severity is Severity.LOW
    assert dummy.calls[1].severity is Severity.HIGH
    assert dummy.calls[1].metadata == {"k": "v"}
    assert dummy.calls[2].severity is Severity.CRITICAL
    assert dummy.calls[2].service == "s"
    assert dummy.calls[2].environment == "e"


def test_from_discord_webhook_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    client = AlertClient.from_discord_webhook_env()
    assert isinstance(client._transport, DiscordTransport)  # noqa: SLF001


def test_from_discord_webhook_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK", raising=False)
    with pytest.raises(ConfigurationError):
        AlertClient.from_discord_webhook_env()


def test_from_discord_webhook_env_custom_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK", raising=False)
    monkeypatch.setenv("MY_HOOK", "https://discord.com/api/webhooks/x/y")
    client = AlertClient.from_discord_webhook_env("MY_HOOK")
    transport = client._transport  # noqa: SLF001
    assert isinstance(transport, DiscordTransport)
    assert transport.webhook_url.endswith("/y")


def test_from_discord_webhook_env_loads_from_env_when_no_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "4")
    client = AlertClient.from_discord_webhook_env()
    transport = client._transport  # noqa: SLF001
    assert isinstance(transport, DiscordTransport)
    assert transport.options.webhook_max_attempts == 4


def test_from_discord_webhook_env_explicit_overrides_env_for_nondefault_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    monkeypatch.setenv("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "9")
    opts = DiscordTransportOptions(webhook_max_attempts=1)
    client = AlertClient.from_discord_webhook_env(discord_options=opts)
    transport = client._transport  # noqa: SLF001
    assert transport.options.webhook_max_attempts == 1


def test_from_discord_webhook_env_config_primary_env_fills_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/org")
    monkeypatch.setenv("GITHUB_SHA", "envsha")
    override = DiscordTransportOptions(use_embeds=False)
    client = AlertClient.from_discord_webhook_env(discord_options=override)
    transport = client._transport  # noqa: SLF001
    assert transport.options.use_embeds is False
    assert transport.options.github is not None
    assert transport.options.github.repository == "env/org"
    assert transport.options.github.ref == "envsha"


def test_from_discord_webhook_env_option_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    monkeypatch.setenv("TEAM_ALERTS_USE_EMBEDS", "1")
    client = AlertClient.from_discord_webhook_env(use_embeds=False)
    transport = client._transport  # noqa: SLF001
    assert transport.options.use_embeds is False


def test_from_discord_webhook_env_partial_inline_true_keeps_env_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/test/token")
    monkeypatch.setenv("TEAM_ALERTS_METADATA_EMBED_FIELDS_INLINE", "false")
    client = AlertClient.from_discord_webhook_env(
        discord_options=DiscordTransportOptions(metadata_embed_fields_inline=True),
    )
    transport = client._transport  # noqa: SLF001
    assert isinstance(transport, DiscordTransport)
    assert transport.options.metadata_embed_fields_inline is False
