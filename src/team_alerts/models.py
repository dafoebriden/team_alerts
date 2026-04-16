"""Core alert data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from team_alerts.constants import Severity


@dataclass(slots=True)
class Alert:
    """A structured operational alert independent of any specific transport."""

    message: str
    severity: Severity
    title: str | None = None
    exception: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    service: str | None = None
    environment: str | None = None
    occurred_at: datetime | None = None
    """
    Optional instant when the event occurred.

    Use a timezone-aware UTC ``datetime`` for correct Discord relative timestamps
    (``<t:unix:R>``) and embed ``timestamp``. Naive values are interpreted as UTC.
    """
