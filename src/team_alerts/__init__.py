"""
Structured operational alerts with pluggable transports.

Public API surface is intentionally small. Heavy imports (e.g. ``requests``) load
only when you reference ``DiscordTransport`` or ``AlertClient``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "Alert",
    "AlertClient",
    "AllowedMentionsOptions",
    "DiscordTransport",
    "DiscordTransportOptions",
    "GitHubLinkOptions",
    "MetadataUrlLinkStyle",
    "Severity",
    "discord_relative_timestamp",
    "github_blob_url",
]


def __getattr__(name: str) -> Any:
    if name == "Alert":
        from team_alerts.models import Alert

        return Alert
    if name == "Severity":
        from team_alerts.constants import Severity

        return Severity
    if name == "DiscordTransport":
        from team_alerts.transports.discord import DiscordTransport

        return DiscordTransport
    if name == "AlertClient":
        from team_alerts.client import AlertClient

        return AlertClient
    if name == "DiscordTransportOptions":
        from team_alerts.discord_options import DiscordTransportOptions

        return DiscordTransportOptions
    if name == "GitHubLinkOptions":
        from team_alerts.discord_options import GitHubLinkOptions

        return GitHubLinkOptions
    if name == "AllowedMentionsOptions":
        from team_alerts.discord_options import AllowedMentionsOptions

        return AllowedMentionsOptions
    if name == "MetadataUrlLinkStyle":
        from team_alerts.discord_options import MetadataUrlLinkStyle

        return MetadataUrlLinkStyle
    if name == "github_blob_url":
        from team_alerts.links import github_blob_url

        return github_blob_url
    if name == "discord_relative_timestamp":
        from team_alerts.formatters import discord_relative_timestamp

        return discord_relative_timestamp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from team_alerts.client import AlertClient
    from team_alerts.constants import Severity
    from team_alerts.discord_options import (
        AllowedMentionsOptions,
        DiscordTransportOptions,
        GitHubLinkOptions,
        MetadataUrlLinkStyle,
    )
    from team_alerts.formatters import discord_relative_timestamp
    from team_alerts.links import github_blob_url
    from team_alerts.models import Alert
    from team_alerts.transports.discord import DiscordTransport
