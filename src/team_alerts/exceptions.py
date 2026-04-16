"""Package-specific errors."""


class TeamAlertsError(Exception):
    """Base error for team_alerts."""


class ConfigurationError(TeamAlertsError):
    """Raised when required configuration is missing or invalid."""
