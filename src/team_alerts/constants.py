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

# Discord embed limits (API).
DISCORD_EMBED_DESCRIPTION_MAX = 4096
DISCORD_EMBED_FIELD_NAME_MAX = 256
DISCORD_EMBED_FIELD_VALUE_MAX = 1024
DISCORD_EMBED_MAX_FIELDS = 25
DISCORD_EMBED_TOTAL_MAX = 6000

# Left-color bar on embeds (decimal integers for Discord API).
EMBED_COLOR_LOW = 0x57F287
EMBED_COLOR_MEDIUM = 0xFEE75C
EMBED_COLOR_HIGH = 0xF26522
EMBED_COLOR_CRITICAL = 0xED4245
