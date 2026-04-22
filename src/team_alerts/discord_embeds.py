"""Discord embed payloads and safe ``allowed_mentions`` helpers."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from team_alerts.constants import (
    DISCORD_EMBED_DESCRIPTION_MAX,
    DISCORD_EMBED_FIELD_NAME_MAX,
    DISCORD_EMBED_FIELD_VALUE_MAX,
    DISCORD_EMBED_MAX_FIELDS,
    DISCORD_EMBED_TOTAL_MAX,
    EMBED_COLOR_CRITICAL,
    EMBED_COLOR_HIGH,
    EMBED_COLOR_LOW,
    EMBED_COLOR_MEDIUM,
    Severity,
)
from team_alerts.discord_options import AllowedMentionsOptions, DiscordTransportOptions, MetadataUrlLinkStyle
from team_alerts.formatters import discord_relative_timestamp, format_severity_with_level_bar
from team_alerts.models import Alert


def severity_embed_color(severity: Severity) -> int:
    """Discord embed ``color`` (left sidebar) by severity."""
    return {
        Severity.LOW: EMBED_COLOR_LOW,
        Severity.MEDIUM: EMBED_COLOR_MEDIUM,
        Severity.HIGH: EMBED_COLOR_HIGH,
        Severity.CRITICAL: EMBED_COLOR_CRITICAL,
    }[severity]


def allowed_mentions_payload(opts: AllowedMentionsOptions | None) -> dict[str, Any] | None:
    """
    Build Discord ``allowed_mentions`` JSON.

    By default nothing is parsed from message text (no surprise pings). Only
    explicit numeric snowflake IDs in ``roles`` / ``users`` are mentionable.

    If ``allow_everyone`` is true, Discord may ping ``@everyone`` — use only when
    you fully intend to notify the whole channel.
    """
    if opts is None:
        return None
    if opts.allow_everyone:
        return {"parse": ["everyone"]}
    # Explicit options object: never parse mentions from message text unless
    # ``allow_everyone`` (handled above). Caller may still pass role/user IDs.
    out: dict[str, Any] = {"parse": []}
    if opts.role_ids:
        out["roles"] = [str(x).strip() for x in opts.role_ids if str(x).strip()]
    if opts.user_ids:
        out["users"] = [str(x).strip() for x in opts.user_ids if str(x).strip()]
    return out


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    reserve = min(40, max_len // 8)
    return s[: max_len - reserve] + "…"


def metadata_to_embed_fields(
    metadata: dict[str, Any],
    *,
    url_link_style: MetadataUrlLinkStyle,
    max_fields: int = DISCORD_EMBED_MAX_FIELDS,
) -> list[dict[str, Any]]:
    """Turn stringable metadata into Discord embed ``fields`` (sorted keys)."""
    fields: list[dict[str, Any]] = []
    for key in sorted(metadata.keys())[:max_fields]:
        name = _truncate(str(key), DISCORD_EMBED_FIELD_NAME_MAX)
        raw = metadata[key]
        val = str(raw)
        if url_link_style == "markdown" and val.startswith(("http://", "https://")) and "\n" not in val:
            val = f"[{name}]({val.replace(')', '%29')})"
        val = _truncate(val, DISCORD_EMBED_FIELD_VALUE_MAX)
        fields.append({"name": name, "value": val, "inline": len(val) < 80})
    return fields


def _description_header_and_overflow(alert: Alert) -> tuple[str, str]:
    """First embed description segment (within API limit) and plain-text overflow."""
    lines: list[str] = []
    lines.append(format_severity_with_level_bar(alert.severity))
    if alert.service:
        lines.append(f"**Service:** {alert.service}")
    if alert.environment:
        lines.append(f"**Environment:** {alert.environment}")
    if alert.correlation_id:
        lines.append(f"**correlation_id:** {_truncate(str(alert.correlation_id), 512)}")
    if alert.run_id:
        lines.append(f"**run_id:** {_truncate(str(alert.run_id), 512)}")
    if alert.dedupe_key:
        lines.append(f"**dedupe_key:** {_truncate(str(alert.dedupe_key), 512)}")
    if alert.occurred_at is not None:
        lines.append(f"**When:** {discord_relative_timestamp(alert.occurred_at)} (UTC)")
    header = "\n".join(lines).strip()
    joiner = "\n\n" if header else ""
    prefix_len = len(header) + len(joiner)
    budget = DISCORD_EMBED_DESCRIPTION_MAX - prefix_len
    if budget < 1:
        budget = 1
    msg = alert.message
    head = msg[:budget]
    overflow = msg[budget:]
    desc = (header + joiner + head).strip()
    if len(desc) > DISCORD_EMBED_DESCRIPTION_MAX:
        desc = desc[:DISCORD_EMBED_DESCRIPTION_MAX]
    return desc, overflow


def build_alert_embed(
    alert: Alert,
    *,
    options: DiscordTransportOptions,
    include_exception_in_body: bool,
    exception_text: str | None,
) -> tuple[dict[str, Any], str]:
    """
    Build a single Discord embed dict for ``alert`` plus plain-text overflow from
    the message body when it did not fit the embed description.
    """
    raw_title = (alert.title or "").strip()
    title = _truncate(raw_title if raw_title else "Alert", 256)

    desc, overflow = _description_header_and_overflow(alert)

    need_exc = bool(include_exception_in_body and exception_text)
    max_meta = DISCORD_EMBED_MAX_FIELDS - (1 if need_exc else 0)

    embed: dict[str, Any] = {
        "title": title,
        "description": desc,
        "color": severity_embed_color(alert.severity),
    }

    if alert.metadata:
        embed["fields"] = metadata_to_embed_fields(
            alert.metadata,
            url_link_style=options.metadata_url_link_style,
            max_fields=max(0, max_meta),
        )

    if need_exc and exception_text:
        tb = _truncate(exception_text, DISCORD_EMBED_FIELD_VALUE_MAX - 10)
        val = f"```{tb}```"
        if len(val) > DISCORD_EMBED_FIELD_VALUE_MAX:
            val = val[: DISCORD_EMBED_FIELD_VALUE_MAX - 1] + "…"
        embed.setdefault("fields", []).append(
            {
                "name": "Exception",
                "value": val,
                "inline": False,
            }
        )

    foot_bits: list[str] = []
    if options.embed_footer_text:
        foot_bits.append(options.embed_footer_text)
    if options.embed_footer_append_service_env and (alert.service or alert.environment):
        bits = [x for x in (alert.service, alert.environment) if x]
        foot_bits.append(" · ".join(bits))
    if foot_bits:
        embed["footer"] = {"text": _truncate(" · ".join(foot_bits), 2048)}

    if alert.occurred_at is not None:
        dt = alert.occurred_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        embed["timestamp"] = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    embed = _shrink_embed_until_under_cap(embed)
    return embed, overflow


def _shrink_embed_until_under_cap(embed: dict[str, Any]) -> dict[str, Any]:
    """Best-effort trim so JSON size stays under Discord's rough total embed cap."""
    import json

    def size() -> int:
        return len(json.dumps(embed))

    while size() > DISCORD_EMBED_TOTAL_MAX and embed.get("fields"):
        embed["fields"] = embed["fields"][:-1]
    while size() > DISCORD_EMBED_TOTAL_MAX:
        desc = str(embed.get("description") or "")
        if len(desc) < 200:
            break
        embed["description"] = desc[: len(desc) // 2] + "…"
    return embed


def embed_json_size_estimate(embed: dict[str, Any]) -> int:
    """Rough character count for embed payload size guarding."""
    import json

    return len(json.dumps(embed))
