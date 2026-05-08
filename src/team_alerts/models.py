"""Core alert data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from team_alerts.constants import Severity

DiscordPayloadStyle = Literal["auto", "embed", "plain"]
"""
Per-alert Discord layout override.

* ``auto`` — follow :attr:`~team_alerts.discord_options.DiscordTransportOptions.use_embeds`.
* ``embed`` — rich embed for this alert only.
* ``plain`` — plain ``content`` (classic text layout) for this alert only.
"""

SeverityRenderStyle = Literal["bar", "label", "emoji", "emoji_bar"]
"""
How Discord severity is rendered in alert headers.

* ``emoji`` — emoji plus bold severity label (default).
* ``bar`` — bold severity plus a level bar.
* ``label`` — bold severity only.
* ``emoji_bar`` — emoji, bold severity, and level bar.
"""

AlertSeverityRenderStyle = Literal["auto", "bar", "label", "emoji", "emoji_bar"]
"""
Per-alert override for Discord severity rendering.

* ``auto`` — use transport/default options.
* other values — force the selected style for this alert.
"""


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
    correlation_id: str | None = None
    """Optional id to correlate this alert with logs, traces, or tickets."""

    run_id: str | None = None
    """Optional run or job identifier (CI build, workflow, batch id, etc.)."""

    dedupe_key: str | None = None
    """Optional stable key for deduplication or aggregation upstream."""

    occurred_at: datetime | None = None
    """
    Optional instant when the event occurred.

    Use a timezone-aware UTC ``datetime`` for correct Discord relative timestamps
    (``<t:unix:R>``) and embed ``timestamp``. Naive values are interpreted as UTC.
    """

    discord_payload_style: DiscordPayloadStyle = "auto"
    """
    Override how this alert is rendered on Discord relative to transport defaults.
    """

    discord_severity_render_style: AlertSeverityRenderStyle = "auto"
    """
    Override severity rendering for this alert relative to transport defaults.
    """
