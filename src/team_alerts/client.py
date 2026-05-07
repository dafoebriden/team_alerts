"""High-level client for sending alerts through a transport."""

from __future__ import annotations

import os
from typing import Any

from team_alerts.constants import Severity
from team_alerts.discord_options import DiscordTransportOptions
from team_alerts.exceptions import ConfigurationError
from team_alerts.models import Alert
from team_alerts.result import SendResult
from team_alerts.transports.base import BaseTransport
from team_alerts.transports.discord import DiscordTransport


class AlertClient:
    """Thin facade over a transport with convenience helpers for severity levels."""

    def __init__(self, transport: BaseTransport) -> None:
        self._transport = transport

    @classmethod
    def from_discord_webhook_env(
        cls,
        env_var: str = "DISCORD_WEBHOOK",
        *,
        discord_options: DiscordTransportOptions | None = None,
        **discord_option_overrides: Any,
    ) -> AlertClient:
        """
        Build a client using ``DiscordTransport`` from ``os.environ[env_var]``.

        Options are resolved inside ``DiscordTransport`` (env base, then
        ``discord_options``, then keyword overrides).
        """
        url = os.environ.get(env_var, "").strip()
        if not url:
            raise ConfigurationError(
                f"Environment variable {env_var!r} is not set or is empty; cannot create Discord transport."
            )
        return cls(
            DiscordTransport(
                url,
                options=discord_options,
                **discord_option_overrides,
            )
        )

    def send(self, alert: Alert) -> SendResult:
        """Send a fully constructed alert."""
        return self._transport.send(alert)

    def low(self, message: str, **kwargs: Any) -> SendResult:
        return self._send_with_severity(Severity.LOW, message, kwargs)

    def high(self, message: str, **kwargs: Any) -> SendResult:
        return self._send_with_severity(Severity.HIGH, message, kwargs)

    def critical(self, message: str, **kwargs: Any) -> SendResult:
        return self._send_with_severity(Severity.CRITICAL, message, kwargs)

    def _send_with_severity(self, severity: Severity, message: str, kwargs: dict[str, Any]) -> SendResult:
        alert = Alert(message=message, severity=severity, **kwargs)
        return self.send(alert)
