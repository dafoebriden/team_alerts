"""Discord embed payloads and safe ``allowed_mentions`` helpers."""

from __future__ import annotations

import re
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
from team_alerts.discord_options import (
    AllowedMentionsOptions,
    DiscordTransportOptions,
    MetadataCodeFenceStyle,
    MetadataEmbedFieldOrder,
    MetadataUrlLinkStyle,
)
from team_alerts.formatters import discord_relative_timestamp, format_severity_for_discord
from team_alerts.models import Alert, SeverityRenderStyle


def traceback_fits_single_exception_field(traceback_text: str) -> bool:
    """
    Return True if ``traceback_text`` can be sent in one embed field wrapped as
    `` ```…``` `` without exceeding Discord's field value limit.
    """
    if not traceback_text:
        return True
    wrapped = f"```{traceback_text}```"
    return len(wrapped) <= DISCORD_EMBED_FIELD_VALUE_MAX


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


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    reserve = min(40, max_len // 8)
    return s[: max_len - reserve] + "…"


def _strip_outer_code_fence(val: str) -> tuple[str, bool]:
    """Return ``(inner_text, stripped_fence)`` when the value is wrapped in ```…```."""
    t = val.strip()
    if not t.startswith("```"):
        return val, False
    end = t.rfind("```")
    if end < 3:
        return val, False
    inner = t[3:end]
    inner_stripped = inner.strip()
    if "\n" in inner_stripped:
        first, _, rest = inner_stripped.partition("\n")
        if first and len(first) <= 12 and " " not in first:
            inner_stripped = rest.strip()
    return inner_stripped, True


def _is_discord_metadata_link_display(val: str) -> bool:
    v = val.strip()
    if v.startswith(("http://", "https://")):
        return True
    if v.startswith("<http://") or v.startswith("<https://"):
        return True
    return v.startswith("[") and "](" in v and v.endswith(")")


def _should_fence_metadata_value(
    *,
    key: str,
    had_fence: bool,
    inner_unwrapped: str,
    display: str,
    fence_style: MetadataCodeFenceStyle,
    fence_keys: tuple[str, ...],
    plain_keys: tuple[str, ...],
) -> bool:
    if key in plain_keys:
        return False
    if key in fence_keys:
        return True
    if fence_style == "off":
        return False
    if _is_discord_metadata_link_display(display):
        return False
    if fence_style == "all":
        return bool(display.strip())
    if had_fence:
        return True
    if not inner_unwrapped.strip():
        return False
    if "\n" in inner_unwrapped:
        return True
    line = inner_unwrapped.strip()
    if len(line) >= 48:
        return True
    if _UUID_RE.match(line):
        return True
    if line.isdigit() and len(line) >= 15:
        return True
    if len(line) >= 32 and re.fullmatch(r"[0-9a-fA-F]+", line):
        return True
    digitish = sum(1 for c in line if c.isdigit() or c in "-_")
    if len(line) >= 16 and digitish >= len(line) * 2 // 3:
        return True
    return False


def _format_metadata_field_value(inner: str, *, use_fence: bool) -> str:
    if not use_fence:
        return _truncate(inner, DISCORD_EMBED_FIELD_VALUE_MAX)
    reserve = 7
    max_inner = max(0, DISCORD_EMBED_FIELD_VALUE_MAX - reserve)
    body = _truncate(inner.strip(), max_inner)
    wrapped = f"```{body}```"
    if len(wrapped) > DISCORD_EMBED_FIELD_VALUE_MAX:
        wrapped = wrapped[: DISCORD_EMBED_FIELD_VALUE_MAX - 1] + "…"
    return wrapped


def metadata_to_embed_fields(
    metadata: dict[str, Any],
    *,
    url_link_style: MetadataUrlLinkStyle,
    max_fields: int = DISCORD_EMBED_MAX_FIELDS,
    metadata_embed_fields_inline: bool = True,
    metadata_embed_field_order: MetadataEmbedFieldOrder = "plain_then_fenced",
    metadata_code_fence_style: MetadataCodeFenceStyle = "auto",
    metadata_code_fence_keys: tuple[str, ...] = (),
    metadata_plain_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """
    Turn stringable metadata into Discord embed ``fields``.

    Keys are sorted within each group. With default ``plain_then_fenced`` order,
    values that receive a code fence (IDs, multiline text, etc.) are listed after
    plain values so they sit just above an ``Exception`` field when both exist.
    """
    entries: list[tuple[str, str, str, bool]] = []
    for key in sorted(metadata.keys()):
        name = _truncate(str(key), DISCORD_EMBED_FIELD_NAME_MAX)
        raw = metadata[key]
        inner_unwrapped, had_fence = _strip_outer_code_fence(str(raw))
        display = inner_unwrapped
        if (
            url_link_style == "markdown"
            and display.startswith(("http://", "https://"))
            and "\n" not in display
        ):
            display = f"[{name}]({display.replace(')', '%29')})"
        use_fence = _should_fence_metadata_value(
            key=key,
            had_fence=had_fence,
            inner_unwrapped=inner_unwrapped,
            display=display,
            fence_style=metadata_code_fence_style,
            fence_keys=metadata_code_fence_keys,
            plain_keys=metadata_plain_keys,
        )
        final_val = _format_metadata_field_value(
            inner_unwrapped if use_fence else display,
            use_fence=use_fence,
        )
        entries.append((key, name, final_val, use_fence))

    if metadata_embed_field_order == "alphabetical":
        ordered = sorted(entries, key=lambda e: e[0])
    else:
        plain = [e for e in entries if not e[3]]
        fenced = [e for e in entries if e[3]]
        ordered = sorted(plain, key=lambda e: e[0]) + sorted(fenced, key=lambda e: e[0])

    cap = max(0, max_fields)
    out: list[dict[str, Any]] = []
    for _key, name, final_val, _use_fence in ordered[:cap]:
        inline = (len(final_val) < 80) if metadata_embed_fields_inline else False
        out.append({"name": name, "value": final_val, "inline": inline})
    return out


def _embed_header_block(alert: Alert, *, severity_render_style: SeverityRenderStyle = "emoji") -> str:
    """Severity bar, service, env, identity lines, and when — no ``Alert.message`` body."""
    lines: list[str] = []
    lines.append(format_severity_for_discord(alert.severity, render_style=severity_render_style))
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
    return "\n".join(lines).strip()


def _description_header_and_overflow(
    alert: Alert, *, severity_render_style: SeverityRenderStyle = "emoji"
) -> tuple[str, str]:
    """
    Embed description and optional plain-text overflow for ``message.txt``.

    The message is inlined when ``header + message`` fits in the embed description
    limit; otherwise the description points to an attachment with the full body.
    """
    header = _embed_header_block(alert, severity_render_style=severity_render_style)
    raw_msg = alert.message or ""
    if not raw_msg.strip():
        desc = header
        if len(desc) > DISCORD_EMBED_DESCRIPTION_MAX:
            desc = desc[:DISCORD_EMBED_DESCRIPTION_MAX]
        return desc, ""
    inline = f"{header}\n\n{raw_msg}".strip()
    if len(inline) <= DISCORD_EMBED_DESCRIPTION_MAX:
        return inline, ""
    note = f"{header}\n\n*(Full message in attachment.)*".strip()
    if len(note) > DISCORD_EMBED_DESCRIPTION_MAX:
        note = note[:DISCORD_EMBED_DESCRIPTION_MAX]
    return note, raw_msg


def build_alert_embed(
    alert: Alert,
    *,
    options: DiscordTransportOptions,
    include_exception_in_body: bool,
    exception_text: str | None,
    severity_render_style: SeverityRenderStyle = "emoji",
) -> tuple[dict[str, Any], str]:
    """
    Build a single Discord embed dict for ``alert`` plus plain-text overflow from
    the message body when it did not fit the embed description.
    """
    raw_title = (alert.title or "").strip()
    title = _truncate(raw_title if raw_title else "Alert", 256)

    desc, overflow = _description_header_and_overflow(alert, severity_render_style=severity_render_style)

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
            metadata_embed_fields_inline=options.metadata_embed_fields_inline,
            metadata_embed_field_order=options.metadata_embed_field_order,
            metadata_code_fence_style=options.metadata_code_fence_style,
            metadata_code_fence_keys=options.metadata_code_fence_keys,
            metadata_plain_keys=options.metadata_plain_keys,
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

    embed, overflow_patch = _fit_embed_under_total_cap(
        embed, overflow == "", alert, severity_render_style=severity_render_style
    )
    if overflow_patch is not None:
        overflow = overflow_patch
    embed = _shrink_embed_until_under_cap(embed)
    return embed, overflow


def _fit_embed_under_total_cap(
    embed: dict[str, Any],
    message_is_inlined: bool,
    alert: Alert,
    *,
    severity_render_style: SeverityRenderStyle = "emoji",
) -> tuple[dict[str, Any], str | None]:
    """
    If the message is inlined but the embed JSON still exceeds Discord's total cap
    (e.g. many metadata fields or a long footer), move the body to overflow
    (``message.txt``) and shorten the description.

    Returns ``(embed, None)`` when unchanged, or ``(embed, full_message)`` when the
    caller must attach the message body.
    """
    if not message_is_inlined:
        return embed, None

    def size() -> int:
        return embed_json_size_estimate(embed)

    while size() > DISCORD_EMBED_TOTAL_MAX and embed.get("fields"):
        if not _pop_one_non_exception_field(embed):
            break

    if size() <= DISCORD_EMBED_TOTAL_MAX:
        return embed, None

    header = _embed_header_block(alert, severity_render_style=severity_render_style)
    note = f"{header}\n\n*(Full message in attachment.)*".strip()
    if len(note) > DISCORD_EMBED_DESCRIPTION_MAX:
        note = note[:DISCORD_EMBED_DESCRIPTION_MAX]
    embed["description"] = note
    while size() > DISCORD_EMBED_TOTAL_MAX and embed.get("fields"):
        if not _pop_one_non_exception_field(embed):
            break
    return embed, (alert.message or "")


def _pop_one_non_exception_field(embed: dict[str, Any]) -> bool:
    fields = embed.get("fields")
    if not fields:
        return False
    for i in range(len(fields) - 1, -1, -1):
        if fields[i].get("name") != "Exception":
            embed["fields"] = fields[:i] + fields[i + 1 :]
            return True
    embed["fields"] = fields[:-1]
    return True


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
