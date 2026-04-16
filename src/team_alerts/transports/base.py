"""Transport abstraction for alert delivery channels."""

from __future__ import annotations

from abc import ABC, abstractmethod

from team_alerts.models import Alert
from team_alerts.result import SendResult


class BaseTransport(ABC):
    """Abstract base class for alert transports (Discord, Slack, email, etc.)."""

    @abstractmethod
    def send(self, alert: Alert) -> SendResult:
        """Deliver ``alert`` and return a structured result."""
