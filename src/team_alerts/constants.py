"""Shared constants for formatting and transports."""

from enum import Enum


class Severity(str, Enum):
    """Alert severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Discord message content limit (characters).
DISCORD_CONTENT_MAX_CHARS = 2000

# Default chunk size when splitting long content (stay under Discord limit with margin).
DEFAULT_CHUNK_SIZE = 1900

# HTTP timeout for outbound webhook requests (connect, read) in seconds.
DISCORD_REQUEST_TIMEOUT = (5, 15)

# First line of Discord alert bodies when banner is enabled (plain text, no markdown).
# Box-drawing reads clearly in the channel timeline between separate alerts.
DEFAULT_ALERT_BANNER_LINE = "▬" * 28
