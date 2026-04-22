"""Pure formatting helpers for transport payloads (Discord-safe text first)."""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any, Iterable

from team_alerts.constants import DISCORD_CONTENT_MAX_CHARS, DEFAULT_CHUNK_SIZE, Severity
from team_alerts.discord_options import MetadataUrlLinkStyle
from team_alerts.models import Alert


def format_severity_label(severity: Severity) -> str:
    """Human-readable severity for plain-text messages."""
    return severity.value


_SEVERITY_BAR_FILLED: dict[Severity, int] = {
    Severity.LOW: 2,
    Severity.MEDIUM: 4,
    Severity.HIGH: 7,
    Severity.CRITICAL: 10,
}
_LEVEL_BAR_WIDTH = 10


def format_severity_with_level_bar(severity: Severity) -> str:
    """
    Severity label plus a short monospace bar (filled vs empty blocks) for quick
    visual level scanning in Discord.
    """
    label = format_severity_label(severity)
    filled = _SEVERITY_BAR_FILLED[severity]
    bar = "\u2588" * filled + "\u2591" * (_LEVEL_BAR_WIDTH - filled)
    return f"**{label}**  `{bar}`"


def discord_relative_timestamp(dt: datetime) -> str:
    """
    Format ``dt`` as a Discord relative timestamp (``<t:unix:R>``).

    Naive datetimes are treated as UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = int(dt.astimezone(timezone.utc).timestamp())
    return f"<t:{ts}:R>"


def format_exception(exc: Exception, *, limit: int | None = None) -> str:
    """Format an exception as a string including traceback."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=limit))
    return tb.rstrip()


def format_metadata_markdown(
    metadata: dict[str, Any],
    *,
    url_link_style: MetadataUrlLinkStyle = "angle",
) -> str:
    """
    Render metadata as readable markdown lines.

    Values that look like a single ``http://`` or ``https://`` URL are emitted
    **without** code fences so Discord can make them clickable.

    * ``angle`` — ``<url>`` (clickable; usually no link preview).
    * ``markdown`` — ``[label](url)`` using the metadata key as visible label.
    """
    if not metadata:
        return ""
    lines: list[str] = ["**Metadata**"]
    for key in sorted(metadata.keys()):
        value = metadata[key]
        raw = str(value)
        if _looks_like_single_http_url(raw):
            url = raw.strip()
            if url_link_style == "markdown":
                label = _markdown_link_label(key)
                safe = _escape_url_for_markdown_link(url)
                lines.append(f"- **{key}**: [{label}]({safe})")
            else:
                lines.append(f"- **{key}**: <{url}>")
        else:
            lines.append(f"- **{key}**: `{_escape_backticks(raw)}`")
    return "\n".join(lines)


def _markdown_link_label(key: str) -> str:
    """Strip characters that break ``[...](...)`` in Discord markdown."""
    k = (key.strip() or "link")[:200]
    cleaned = "".join(ch for ch in k if ch not in "[]()")
    return cleaned or "link"


def _escape_url_for_markdown_link(url: str) -> str:
    """Avoid closing ``](...)`` early when the URL contains ``)``."""
    return url.replace(")", "%29")


def _looks_like_single_http_url(text: str) -> bool:
    s = text.strip()
    if not s.startswith(("http://", "https://")):
        return False
    if any(c.isspace() for c in s):
        return False
    if "`" in s:
        return False
    return True


def _escape_backticks(text: str) -> str:
    """Avoid breaking markdown code spans in Discord."""
    return text.replace("`", "'")


def alert_has_identity_fields(alert: Alert) -> bool:
    """True when ``correlation_id``, ``run_id``, or ``dedupe_key`` is set."""
    return bool(alert.correlation_id or alert.run_id or alert.dedupe_key)


def _alert_identity_lines(alert: Alert) -> list[str]:
    lines: list[str] = []
    if alert.correlation_id:
        lines.append(f"**correlation_id:** `{_escape_backticks(alert.correlation_id)}`")
    if alert.run_id:
        lines.append(f"**run_id:** `{_escape_backticks(alert.run_id)}`")
    if alert.dedupe_key:
        lines.append(f"**dedupe_key:** `{_escape_backticks(alert.dedupe_key)}`")
    return lines


def _compact_identity_marker(alert: Alert) -> str:
    bits: list[str] = []
    if alert.correlation_id:
        bits.append(f"correlation_id=`{_escape_backticks(alert.correlation_id)}`")
    if alert.run_id:
        bits.append(f"run_id=`{_escape_backticks(alert.run_id)}`")
    if alert.dedupe_key:
        bits.append(f"dedupe_key=`{_escape_backticks(alert.dedupe_key)}`")
    return " · ".join(bits)


def effective_split_chunk_size_for_identity_markers(
    alert: Alert,
    requested_chunk_size: int,
    *,
    prefix_on_every_chunk: bool,
) -> int:
    """
    Reduce split size so ``**[n/m]**`` + compact identity marker + body stays within
    Discord's ``2000`` character ``content`` cap after ``apply_identity_markers_to_split_chunks``.
    """
    if not alert_has_identity_fields(alert):
        return requested_chunk_size
    marker = _compact_identity_marker(alert)
    header_reserve = 36 if not prefix_on_every_chunk else 40
    overhead = len(marker) + header_reserve
    limit = DISCORD_CONTENT_MAX_CHARS - overhead
    return min(requested_chunk_size, max(200, limit))


def apply_identity_markers_to_split_chunks(
    chunks: list[str],
    alert: Alert,
    *,
    leading_chunk_includes_identity: bool,
) -> list[str]:
    """
    Prefix split webhook payloads so identifiers survive partial delivery.

    When ``leading_chunk_includes_identity`` is true (plain multi-chunk alerts),
    only chunks after the first are prefixed. When false (e.g. embed overflow
    tails), every chunk is prefixed because no earlier payload carried the lines.
    """
    if not chunks:
        return []
    if not alert_has_identity_fields(alert):
        return list(chunks)
    marker = _compact_identity_marker(alert)
    total = len(chunks)
    if total == 1 and not leading_chunk_includes_identity:
        return [f"**[1/1]** {marker}\n\n{chunks[0]}"]
    if leading_chunk_includes_identity:
        if total <= 1:
            return list(chunks)
        out = [chunks[0]]
        for i in range(1, total):
            out.append(f"**[{i + 1}/{total}]** {marker}\n\n{chunks[i]}")
        return out
    out = []
    for i, chunk in enumerate(chunks):
        out.append(f"**[{i + 1}/{total}]** {marker}\n\n{chunk}")
    return out


def _normalize_banner_line(alert_banner: str) -> str:
    """Return a single sanitized banner line, or empty string when disabled."""
    if not alert_banner:
        return ""
    line = alert_banner.split("\n", 1)[0].strip()
    if len(line) > 400:
        line = line[:400]
    return line


def format_alert_discord_text(
    alert: Alert,
    *,
    max_chars: int = DISCORD_CONTENT_MAX_CHARS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    include_exception_in_body: bool = True,
    exception_attachment_filename: str = "traceback.txt",
    metadata_url_link_style: MetadataUrlLinkStyle = "angle",
    alert_banner: str = "",
) -> str:
    """
    Format an alert as a single Discord-safe plain-text/markdown string.

    Long output is truncated with a suffix; use ``split_long_text`` on the result
    if you need multiple webhook payloads.
    """
    parts = _alert_body_parts(
        alert,
        include_exception_in_body=include_exception_in_body,
        exception_attachment_filename=exception_attachment_filename,
        metadata_url_link_style=metadata_url_link_style,
    )
    body = "\n".join(parts)
    line = _normalize_banner_line(alert_banner)
    if line:
        reserve = len(line) + 1
        capped = max(1, max_chars - reserve)
        body = truncate_text(body, max_chars=capped, chunk_size=chunk_size)
        return f"{line}\n{body}"
    return truncate_text(body, max_chars=max_chars, chunk_size=chunk_size)


def format_alert_discord_chunks(
    alert: Alert,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    include_exception_in_body: bool = True,
    exception_attachment_filename: str = "traceback.txt",
    metadata_url_link_style: MetadataUrlLinkStyle = "angle",
    alert_banner: str = "",
) -> list[str]:
    """Format an alert and split into Discord-sized chunks if needed."""
    parts = _alert_body_parts(
        alert,
        include_exception_in_body=include_exception_in_body,
        exception_attachment_filename=exception_attachment_filename,
        metadata_url_link_style=metadata_url_link_style,
    )
    body = "\n".join(parts)
    line = _normalize_banner_line(alert_banner)
    if line:
        body = f"{line}\n{body}"
    eff = effective_split_chunk_size_for_identity_markers(
        alert, chunk_size, prefix_on_every_chunk=False
    )
    chunks = list(split_long_text(body, chunk_size=eff))
    return apply_identity_markers_to_split_chunks(
        chunks, alert, leading_chunk_includes_identity=True
    )


def append_footer_to_last_chunk(chunks: list[str], footer: str | None) -> list[str]:
    """
    Append ``footer`` to the last chunk when it fits under ``DISCORD_CONTENT_MAX_CHARS``;
    otherwise append one or more new chunks (split) so the footer is never dropped.
    """
    if not footer or not footer.strip():
        return list(chunks)
    f = footer.strip()
    if not chunks:
        return list(split_long_text(f, chunk_size=DISCORD_CONTENT_MAX_CHARS))
    out = list(chunks)
    last = out[-1]
    candidate = f"{last}\n{f}" if last else f
    if len(candidate) <= DISCORD_CONTENT_MAX_CHARS:
        out[-1] = candidate
        return out
    for piece in split_long_text(f, chunk_size=DISCORD_CONTENT_MAX_CHARS):
        out.append(piece)
    return out


def _alert_body_parts(
    alert: Alert,
    *,
    include_exception_in_body: bool = True,
    exception_attachment_filename: str = "traceback.txt",
    metadata_url_link_style: MetadataUrlLinkStyle = "angle",
) -> list[str]:
    lines: list[str] = []
    lines.append(format_severity_with_level_bar(alert.severity))
    if alert.service:
        lines.append(f"**Service:** `{_escape_backticks(alert.service)}`")
    if alert.environment:
        lines.append(f"**Environment:** `{_escape_backticks(alert.environment)}`")
    lines.extend(_alert_identity_lines(alert))

    if alert.title:
        lines.append(f"**{_escape_backticks(alert.title)}**")

    if alert.occurred_at is not None:
        when = discord_relative_timestamp(alert.occurred_at)
        lines.append(f"**When:** {when} (UTC)")

    lines.append(_escape_backticks(alert.message))

    meta = format_metadata_markdown(
        alert.metadata,
        url_link_style=metadata_url_link_style,
    )
    if meta:
        lines.append(meta)

    if alert.exception is not None:
        lines.append("**Exception**")
        if include_exception_in_body:
            tb = format_exception(alert.exception)
            lines.append("```")
            lines.append(tb)
            lines.append("```")
        else:
            fn = _escape_backticks(exception_attachment_filename)
            lines.append(f"(full traceback attached as `{fn}`)")

    return lines


def truncate_text(
    text: str,
    *,
    max_chars: int = DISCORD_CONTENT_MAX_CHARS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """
    Truncate text so the returned string length is never greater than ``max_chars``.

    ``chunk_size`` is accepted for API symmetry with ``split_long_text``; truncation
    always fits within ``max_chars`` including the suffix.
    """
    _ = chunk_size
    if len(text) <= max_chars:
        return text
    cut = max_chars
    while cut > 0:
        omitted = len(text) - cut
        suffix = f"\n\n… (truncated, {omitted} chars omitted)"
        if cut + len(suffix) <= max_chars:
            return text[:cut] + suffix
        cut -= 1
    return text[:max_chars]


def split_long_text(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterable[str]:
    """
    Split text into chunks no longer than ``chunk_size``.

    Splits on newlines when possible to avoid breaking mid-word; otherwise hard-splits.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if text == "":
        yield ""
        return
    if len(text) <= chunk_size:
        yield text
        return

    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if end < n:
            nl = chunk.rfind("\n")
            if nl > chunk_size // 4:
                chunk = chunk[: nl + 1]
                end = start + len(chunk)
        yield chunk
        start = end
