"""Optional configuration for :class:`~team_alerts.transports.discord.DiscordTransport`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

MetadataUrlLinkStyle = Literal["angle", "markdown"]


@dataclass(slots=True)
class AllowedMentionsOptions:
    """
    Explicit Discord ``allowed_mentions`` wiring (safe defaults).

    Only numeric snowflake IDs you list under ``role_ids`` / ``users`` are mentionable.
    Nothing is parsed from message text, so stray ``@everyone`` in content does not ping.

    Set ``allow_everyone`` only when you intentionally notify the whole channel.
    """

    role_ids: tuple[str, ...] = ()
    user_ids: tuple[str, ...] = ()
    allow_everyone: bool = False

    @classmethod
    def from_env(cls) -> AllowedMentionsOptions | None:
        """
        Parse ``TEAM_ALERTS_ALLOWED_ROLE_IDS`` and ``TEAM_ALERTS_ALLOWED_USER_IDS``
        (comma-separated snowflakes). Returns ``None`` when both are empty and
        ``TEAM_ALERTS_ALLOW_EVERYONE_MENTION`` is unset/false.
        """
        roles_raw = os.environ.get("TEAM_ALERTS_ALLOWED_ROLE_IDS", "").strip()
        users_raw = os.environ.get("TEAM_ALERTS_ALLOWED_USER_IDS", "").strip()
        everyone_raw = os.environ.get("TEAM_ALERTS_ALLOW_EVERYONE_MENTION", "").strip().lower()
        allow_everyone = everyone_raw in ("1", "true", "yes", "on")

        role_ids = tuple(r.strip() for r in roles_raw.split(",") if r.strip())
        user_ids = tuple(u.strip() for u in users_raw.split(",") if u.strip())

        if not role_ids and not user_ids and not allow_everyone:
            return None
        return cls(role_ids=role_ids, user_ids=user_ids, allow_everyone=allow_everyone)


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

    message_attachment_filename: str = "message.txt"
    """Filename when embed mode moves overflow message text into an attachment."""

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

    use_embeds: bool = True
    """When true, send a rich embed (color by severity, fields, optional timestamp)."""

    allowed_mentions: AllowedMentionsOptions | None = None
    """Optional explicit role/user pings; see :class:`AllowedMentionsOptions`."""

    alert_footer: str | None = None
    """
    Extra plain-text footer appended to the **last** webhook payload when an alert
    is split across multiple posts (plain mode or embed continuations).
    """

    embed_footer_text: str | None = None
    """Optional short line in the embed ``footer`` (distinct from ``alert_footer``)."""

    embed_footer_append_service_env: bool = False
    """When true and ``embed_footer_text`` is set, also append ``service · env`` to the embed footer."""

    webhook_max_attempts: int = 3
    """
    Total HTTP attempts per webhook POST (including the first). Retries apply only
    to the chunk being sent, not to earlier chunks of a split alert.
    """

    webhook_retry_base_delay_seconds: float = 0.5
    """Initial backoff base for retries (seconds); grows exponentially."""

    webhook_retry_max_delay_seconds: float = 60.0
    """Upper bound for a single sleep before a retry (seconds)."""

    webhook_retry_jitter_seconds: float = 0.25
    """Random jitter in ``[0, jitter]`` added to backoff sleeps."""

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
        * ``TEAM_ALERTS_USE_EMBEDS`` — ``0`` / ``false`` / ``no`` / ``off`` / ``plain`` to
          force **plain** ``content``; ``1`` / ``true`` / ``yes`` / ``on`` / ``embed`` for
          embeds (default is embeds **on** when this variable is unset)
        * ``TEAM_ALERTS_ALERT_FOOTER`` — text appended on the **last** chunk when split
        * ``TEAM_ALERTS_EMBED_FOOTER`` — optional embed footer line (embed mode)
        * ``TEAM_ALERTS_ALLOWED_ROLE_IDS`` / ``TEAM_ALERTS_ALLOWED_USER_IDS`` — comma
          snowflakes for :class:`AllowedMentionsOptions`
        * ``TEAM_ALERTS_ALLOW_EVERYONE_MENTION`` — must be ``1``/``true`` to allow
          ``@everyone`` (dangerous; off by default)
        * ``TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS`` — positive integer; max attempts per
          HTTP POST (default ``3`` when unset)
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

        embeds_raw = os.environ.get("TEAM_ALERTS_USE_EMBEDS", "").strip().lower()
        use_embeds = True
        if embeds_raw in ("0", "false", "no", "off", "plain", "raw"):
            use_embeds = False
        elif embeds_raw in ("1", "true", "yes", "on", "embed"):
            use_embeds = True

        alert_footer = os.environ.get("TEAM_ALERTS_ALERT_FOOTER", "").strip() or None
        embed_footer = os.environ.get("TEAM_ALERTS_EMBED_FOOTER", "").strip() or None

        allowed = AllowedMentionsOptions.from_env()

        max_attempts_raw = os.environ.get("TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS", "").strip()
        webhook_max_attempts = 3
        if max_attempts_raw.isdigit() and int(max_attempts_raw) >= 1:
            webhook_max_attempts = int(max_attempts_raw)

        return cls(
            attach_exception_over_chars=threshold,
            exception_attachment_filename=exception_attachment_filename,
            github=github,
            env_metadata_keys=env_keys,
            metadata_url_link_style=link_style,
            alert_banner=alert_banner,
            use_embeds=use_embeds,
            allowed_mentions=allowed,
            alert_footer=alert_footer,
            embed_footer_text=embed_footer,
            webhook_max_attempts=webhook_max_attempts,
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
