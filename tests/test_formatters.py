"""Tests for pure formatting helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from team_alerts.constants import DEFAULT_ALERT_BANNER_LINE, DISCORD_CONTENT_MAX_CHARS, Severity
from team_alerts.formatters import (
    append_footer_to_last_chunk,
    discord_relative_timestamp,
    format_alert_discord_chunks,
    format_alert_discord_text,
    format_exception,
    format_metadata_markdown,
    format_severity_label,
    split_long_text,
    truncate_text,
)
from team_alerts.models import Alert


def test_format_severity_label() -> None:
    assert format_severity_label(Severity.HIGH) == "HIGH"


def test_format_metadata_markdown_empty() -> None:
    assert format_metadata_markdown({}) == ""


def test_format_metadata_markdown_sorted_keys() -> None:
    md = format_metadata_markdown({"b": 2, "a": 1})
    assert "**Metadata**" in md
    assert "**a**" in md and "**b**" in md
    assert md.index("**a**") < md.index("**b**")


def test_format_metadata_http_urls_use_angle_brackets_not_code_fences() -> None:
    url = "https://github.com/acme/repo/blob/deadbeef/src/app.py#L10"
    md = format_metadata_markdown({"GitHub": url, "count": 3})
    assert f"<{url}>" in md
    assert "`https://" not in md
    assert "`3`" in md


def test_format_metadata_markdown_visible_link_text() -> None:
    url = "https://github.com/acme/repo/actions/runs/99"
    md = format_metadata_markdown({"CI run": url}, url_link_style="markdown")
    assert "- **CI run**: [CI run](" in md
    assert ")" in md
    assert f"]({url})" in md
    assert "<https://" not in md


def test_format_metadata_markdown_escapes_close_paren_in_url() -> None:
    url = "https://example.com/a)b"
    md = format_metadata_markdown({"link": url}, url_link_style="markdown")
    assert "](https://example.com/a%29b)" in md


def test_format_metadata_url_with_whitespace_stays_code_span() -> None:
    md = format_metadata_markdown({"bad": "https://a.com ok"})
    assert "`" in md
    assert "<https://" not in md


def test_format_exception_includes_message_and_type() -> None:
    try:
        raise RuntimeError("nope")
    except RuntimeError as exc:
        text = format_exception(exc)
    assert "RuntimeError" in text
    assert "nope" in text


def test_format_alert_discord_text_no_banner_by_default() -> None:
    alert = Alert(message="x", severity=Severity.LOW)
    out = format_alert_discord_text(alert)
    assert out.startswith("**[LOW]**")


def test_format_alert_discord_text_with_banner() -> None:
    alert = Alert(message="Something happened", severity=Severity.LOW, title="Job failed")
    banner = "━━━━ prod alert ━━━━"
    out = format_alert_discord_text(alert, alert_banner=banner)
    assert out.startswith(banner + "\n")
    assert "[LOW]" in out
    assert not out.startswith(banner + "\n\n")


def test_format_alert_discord_chunks_banner_only_on_first_segment() -> None:
    alert = Alert(message="LINE\n" * 400, severity=Severity.HIGH)
    chunks = format_alert_discord_chunks(alert, chunk_size=200, alert_banner=DEFAULT_ALERT_BANNER_LINE)
    assert len(chunks) >= 2
    assert chunks[0].startswith(DEFAULT_ALERT_BANNER_LINE + "\n")
    assert DEFAULT_ALERT_BANNER_LINE not in chunks[1]


def test_format_alert_discord_text_basic() -> None:
    alert = Alert(
        message="Something happened",
        severity=Severity.LOW,
        title="Job failed",
        service="worker",
        environment="prod",
        metadata={"request_id": "abc"},
    )
    out = format_alert_discord_text(alert)
    assert "[LOW]" in out
    assert "Something happened" in out
    assert "Job failed" in out
    assert "worker" in out and "prod" in out
    assert "request_id" in out


def test_format_alert_exception_attachment_mode() -> None:
    try:
        raise ValueError("bad")
    except ValueError as exc:
        alert = Alert(message="m", severity=Severity.HIGH, exception=exc)
    out = format_alert_discord_text(
        alert,
        include_exception_in_body=False,
        exception_attachment_filename="err.txt",
    )
    assert "Exception" in out
    assert "err.txt" in out
    assert "ValueError" not in out


def test_format_alert_with_exception_block() -> None:
    try:
        raise ValueError("bad")
    except ValueError as exc:
        alert = Alert(message="m", severity=Severity.HIGH, exception=exc)
    out = format_alert_discord_text(alert)
    assert "Exception" in out
    assert "ValueError" in out


def test_truncate_text_unmodified_when_short() -> None:
    s = "hi"
    assert truncate_text(s, max_chars=100) == s


def test_truncate_text_long() -> None:
    long = "x" * 5000
    out = truncate_text(long, max_chars=200, chunk_size=50)
    assert len(out) <= 200
    assert "truncated" in out


def test_split_long_text_single_chunk() -> None:
    assert list(split_long_text("abc", chunk_size=100)) == ["abc"]


def test_split_long_text_empty() -> None:
    assert list(split_long_text("", chunk_size=10)) == [""]


def test_split_long_text_multiple() -> None:
    body = "a" * 100 + "\n" + "b" * 100
    chunks = list(split_long_text(body, chunk_size=120))
    assert len(chunks) >= 2
    assert "".join(chunks) == body


def test_split_long_text_invalid_chunk_size() -> None:
    with pytest.raises(ValueError):
        list(split_long_text("x", chunk_size=0))


def test_format_alert_respects_discord_max_length() -> None:
    alert = Alert(message="m" * (DISCORD_CONTENT_MAX_CHARS + 500), severity=Severity.CRITICAL)
    out = format_alert_discord_text(alert)
    assert len(out) <= DISCORD_CONTENT_MAX_CHARS


def test_discord_relative_timestamp_utc() -> None:
    dt = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert discord_relative_timestamp(dt) == "<t:1577836800:R>"


def test_format_alert_includes_occurred_at_line() -> None:
    dt = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    alert = Alert(message="m", severity=Severity.LOW, occurred_at=dt)
    out = format_alert_discord_text(alert)
    assert "When:" in out
    assert "<t:1577836800:R>" in out


def test_append_footer_to_last_chunk_appends() -> None:
    chunks = ["a", "b"]
    out = append_footer_to_last_chunk(chunks, "footer")
    assert out == ["a", "b\nfooter"]


def test_append_footer_to_last_chunk_new_chunk_when_full() -> None:
    base = "x" * (DISCORD_CONTENT_MAX_CHARS - 1)
    chunks = [base]
    out = append_footer_to_last_chunk(chunks, "tail")
    assert len(out) == 2
    assert out[0] == base
    assert "tail" in out[1]
