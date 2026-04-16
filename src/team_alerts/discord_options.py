"""Optional configuration for :class:`~team_alerts.transports.discord.DiscordTransport`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

MetadataUrlLinkStyle = Literal["angle", "markdown"]


@dataclass(slots=True)
class GitHubLinkOptions:
    """
    When set on :class:`DiscordTransportOptions`, a GitHub ``/blob/`` link for the
    primary traceback frame is merged into alert metadata (if resolvable).

    Set ``source_root`` to the absolute path of your repository checkout so file
    paths can be relativized for the URL.
    """

    repository: str
    """``owner/repo`` (e.g. ``acme/vortech``)."""

    ref: str
    """Commit SHA, tag, or branch name (e.g. ``GITHUB_SHA`` in Actions)."""

    source_root: str | None = None
    """Absolute path to repo root for ``relpath`` from traceback filenames."""

    base_url: str = "https://github.com"
    """Use a GitHub Enterprise host if needed."""

    skip_site_packages_frames: bool = True
    """Prefer application frames when choosing a line to link."""

    metadata_key: str = "GitHub"
    """Metadata key for the resolved URL."""


@dataclass(slots=True)
class DiscordTransportOptions:
    """
    Optional Discord delivery behavior: long tracebacks as file uploads, GitHub
    links, static links, and copying selected environment variables into metadata.
    """

    attach_exception_over_chars: int | None = None
    """
    When not ``None`` and the formatted traceback exceeds this length, the traceback
    is sent as a file attachment instead of inline code (first webhook only).
    """

    exception_attachment_filename: str = "traceback.txt"
    """Filename for the traceback attachment."""

    max_attachment_bytes: int = 8_000_000
    """Hard cap on attachment payload (bytes); longer text is truncated with a note."""

    github: GitHubLinkOptions | None = None

    static_links: dict[str, str] = field(default_factory=dict)
    """Arbitrary URLs merged into metadata (e.g. ``{"CI": "https://..."}``)."""

    env_metadata_keys: tuple[str, ...] = ()
    """
    Names of environment variables to copy into metadata when set
    (values are plain strings).
    """

    metadata_url_link_style: MetadataUrlLinkStyle = "angle"
    """
    How single-line ``http(s)`` metadata URLs are rendered in Discord:

    * ``angle`` — ``<https://…>`` (clickable; usually no link preview).
    * ``markdown`` — ``[key](https://…)`` with visible label from the metadata key.
    """

    alert_banner: str | None = None
    """
    Visual separator prepended before the alert body (first chunk only when split).

    * ``None`` — use :data:`team_alerts.constants.DEFAULT_ALERT_BANNER_LINE`.
    * ``""`` — disable the banner.
    * Any other string — first line only (truncated if extremely long); use for a
      custom divider or short label (e.g. ``"━━━ production ━━━"``).
    """

    @classmethod
    def from_env(
        cls,
        *,
        attach_exception_over_chars: int | None = None,
        exception_attachment_filename: str = "traceback.txt",
    ) -> DiscordTransportOptions:
        """
        Build options from common environment variables (all optional).

        Recognized variables:

        * ``GITHUB_REPOSITORY`` — ``owner/repo`` for GitHub links
        * ``GITHUB_SHA``, ``GITHUB_REF_NAME``, ``GIT_COMMIT`` — first set wins for ``ref``
        * ``GITHUB_SERVER_URL`` — enterprise API host mapped to HTML host (best-effort)
        * ``TEAM_ALERTS_GITHUB_SOURCE_ROOT`` — repo checkout root for path relativization
        * ``TEAM_ALERTS_ATTACH_EXCEPTION_OVER`` — integer threshold for file attachments
        * ``TEAM_ALERTS_ENV_METADATA`` — comma-separated env var names to copy to metadata
        * ``TEAM_ALERTS_METADATA_URL_STYLE`` — ``markdown`` (or ``md`` / ``labeled``) for
          ``[visible text](url)`` metadata links; otherwise ``angle`` brackets
        * ``TEAM_ALERTS_ALERT_BANNER`` — ``0`` / ``false`` / ``off`` to disable the top
          separator; any other non-empty value becomes a **custom** banner line
          (otherwise the package default is used)
        """
        repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        ref = (
            os.environ.get("GITHUB_SHA", "").strip()
            or os.environ.get("GIT_COMMIT", "").strip()
            or os.environ.get("GITHUB_REF_NAME", "").strip()
        )
        source_root = os.environ.get("TEAM_ALERTS_GITHUB_SOURCE_ROOT", "").strip() or None

        github: GitHubLinkOptions | None = None
        if repo and ref:
            base = _github_html_base_from_env()
            github = GitHubLinkOptions(
                repository=repo,
                ref=ref,
                source_root=source_root,
                base_url=base,
            )

        thresh_raw = os.environ.get("TEAM_ALERTS_ATTACH_EXCEPTION_OVER", "").strip()
        threshold = attach_exception_over_chars
        if threshold is None and thresh_raw.isdigit():
            threshold = int(thresh_raw)

        env_keys_raw = os.environ.get("TEAM_ALERTS_ENV_METADATA", "").strip()
        env_keys = tuple(k.strip() for k in env_keys_raw.split(",") if k.strip())

        style_raw = os.environ.get("TEAM_ALERTS_METADATA_URL_STYLE", "").strip().lower()
        link_style: MetadataUrlLinkStyle = "angle"
        if style_raw in ("markdown", "md", "labeled"):
            link_style = "markdown"

        banner_raw = os.environ.get("TEAM_ALERTS_ALERT_BANNER", "").strip()
        alert_banner: str | None = None
        if banner_raw.lower() in ("0", "false", "no", "off"):
            alert_banner = ""
        elif banner_raw:
            alert_banner = banner_raw

        return cls(
            attach_exception_over_chars=threshold,
            exception_attachment_filename=exception_attachment_filename,
            github=github,
            env_metadata_keys=env_keys,
            metadata_url_link_style=link_style,
            alert_banner=alert_banner,
        )


def _github_html_base_from_env() -> str:
    """
    Map ``GITHUB_SERVER_URL`` (API style) to a reasonable HTML base when possible.

    Falls back to ``https://github.com``.
    """
    raw = os.environ.get("GITHUB_SERVER_URL", "").strip().rstrip("/")
    if not raw:
        return "https://github.com"
    # GitHub Enterprise Server often uses same host for web; API may be under /api/v3.
    if raw.endswith("/api/v3"):
        return raw[: -len("/api/v3")] or "https://github.com"
    return raw
