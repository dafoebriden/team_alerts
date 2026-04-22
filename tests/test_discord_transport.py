"""Discord transport tests with mocked HTTP."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from team_alerts.constants import DEFAULT_ALERT_BANNER_LINE, EMBED_COLOR_CRITICAL, Severity
from team_alerts.discord_options import (
    AllowedMentionsOptions,
    DiscordTransportOptions,
    GitHubLinkOptions,
)
from team_alerts.exceptions import ConfigurationError
from team_alerts.models import Alert
from team_alerts.discord_embeds import traceback_fits_single_exception_field
from team_alerts.transports.discord import DiscordTransport

_PLAIN = DiscordTransportOptions(use_embeds=False)


def test_traceback_fits_single_exception_field_boundary() -> None:
    assert traceback_fits_single_exception_field("x" * 1018)
    assert not traceback_fits_single_exception_field("x" * 1019)


def test_discord_transport_rejects_empty_url() -> None:
    with pytest.raises(ConfigurationError):
        DiscordTransport("")
    with pytest.raises(ConfigurationError):
        DiscordTransport("   ")


def test_discord_transport_send_success() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        alert = Alert(message="hello", severity=Severity.LOW)
        result = transport.send(alert)

    assert result.success is True
    assert result.status_code == 204
    assert result.error_message is None
    post.assert_called_once()
    kwargs = post.call_args.kwargs
    assert "json" in kwargs
    payload = kwargs["json"]
    assert payload["embeds"]
    desc = payload["embeds"][0]["description"]
    assert "hello" in desc
    assert "\u2588" in desc
    assert "files" not in kwargs
    assert "timeout" in kwargs


def test_discord_transport_plain_payload_style_overrides_default_embed() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(
            Alert(message="plain body", severity=Severity.HIGH, discord_payload_style="plain")
        )

    assert result.success is True
    payload = post.call_args.kwargs["json"]
    assert "embeds" not in payload or not payload.get("embeds")
    assert payload["content"]
    assert "plain body" in payload["content"]
    assert "\u2588" in payload["content"]


def test_discord_transport_send_http_error() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 429
    mock_resp.text = "rate limited"

    with patch("team_alerts.transports.discord.time.sleep"):
        with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=_PLAIN)
            result = transport.send(Alert(message="m", severity=Severity.HIGH))

    assert result.success is False
    assert result.status_code == 429
    assert result.error_message == "HTTP 429"
    assert post.call_count == 3


def test_discord_transport_long_plain_alert_single_multipart_file() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    huge = "LINE\n" * 1500
    alert = Alert(message=huge, severity=Severity.LOW, title="long")

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=_PLAIN)
        result = transport.send(alert)

    assert result.success is True
    post.assert_called_once()
    assert "files" in post.call_args.kwargs
    payload = json.loads(post.call_args.kwargs["files"]["payload_json"][1])
    assert len(payload["attachments"]) == 1


def test_discord_transport_includes_github_url_in_content() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    tests_dir = str(Path(__file__).resolve().parent)
    gh = GitHubLinkOptions(repository="org/repo", ref="deadbeef", source_root=tests_dir)
    opts = DiscordTransportOptions(github=gh, use_embeds=False)

    try:
        raise RuntimeError("fail")
    except RuntimeError as exc:
        alert = Alert(message="m", severity=Severity.CRITICAL, exception=exc)

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        result = transport.send(alert)

    assert result.success is True
    payload = post.call_args.kwargs["json"]
    content = payload["content"]
    assert "github.com/org/repo/blob/deadbeef" in content.replace("\\", "/")
    assert "test_discord_transport.py" in content


def test_discord_transport_long_exception_uses_multipart() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(attach_exception_over_chars=50, use_embeds=False)
    alert = Alert(message="short", severity=Severity.HIGH, exception=ValueError("x"))

    with patch("team_alerts.transports.discord.format_exception", return_value="E" * 200) as fe:
        with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
            result = transport.send(alert)

    assert result.success is True
    fe.assert_called_once()
    post.assert_called_once()
    kwargs = post.call_args.kwargs
    assert "files" in kwargs
    assert "json" not in kwargs
    files = kwargs["files"]
    assert "payload_json" in files
    assert "files[0]" in files


def test_discord_transport_banner_disabled_when_blank_option() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(alert_banner="", use_embeds=False)
    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        transport.send(Alert(message="m", severity=Severity.LOW))

    content = post.call_args.kwargs["json"]["content"]
    assert not content.startswith(DEFAULT_ALERT_BANNER_LINE)
    assert content.startswith("**LOW**")


def test_discord_transport_request_exception() -> None:
    with patch("team_alerts.transports.discord.time.sleep"):
        with patch(
            "team_alerts.transports.discord.requests.post",
            side_effect=requests.Timeout("timed out"),
        ) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=_PLAIN)
            result = transport.send(Alert(message="m", severity=Severity.LOW))

    assert result.success is False
    assert result.status_code is None
    assert result.error_message is not None
    assert "timed out" in result.error_message
    assert post.call_count == 3


def test_discord_transport_retries_until_success_after_429() -> None:
    bad = MagicMock()
    bad.ok = False
    bad.status_code = 429
    bad.text = "wait"
    bad.headers = {"Retry-After": "0"}
    good = MagicMock()
    good.ok = True
    good.status_code = 204
    good.text = ""

    with patch("team_alerts.transports.discord.time.sleep"):
        with patch(
            "team_alerts.transports.discord.requests.post",
            side_effect=[bad, good],
        ) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=_PLAIN)
            result = transport.send(Alert(message="m", severity=Severity.LOW))

    assert result.success is True
    assert post.call_count == 2


def test_discord_transport_no_retry_on_400() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 400
    mock_resp.text = "bad"

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=_PLAIN)
        result = transport.send(Alert(message="m", severity=Severity.LOW))

    assert result.success is False
    assert post.call_count == 1


def test_discord_transport_embed_mode_posts_embed() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(
            Alert(
                message="hello",
                severity=Severity.CRITICAL,
                title="T",
                correlation_id="trace-99",
            )
        )

    assert result.success is True
    kwargs = post.call_args.kwargs
    assert "json" in kwargs
    payload = kwargs["json"]
    embeds = payload["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["color"] == EMBED_COLOR_CRITICAL
    assert embeds[0]["title"] == "T"
    assert "hello" in embeds[0]["description"]
    assert "trace-99" in embeds[0]["description"]
    assert "\u2588" in embeds[0]["description"]


def test_discord_transport_allowed_mentions_roles() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    mentions = AllowedMentionsOptions(role_ids=("111", "222"))
    opts = DiscordTransportOptions(allowed_mentions=mentions, use_embeds=False)

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        transport.send(Alert(message="m", severity=Severity.LOW))

    assert post.call_args.kwargs["json"]["allowed_mentions"] == {
        "parse": [],
        "roles": ["111", "222"],
    }


def test_discord_transport_alert_footer_on_last_chunk() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(alert_banner="", alert_footer="— end —", use_embeds=False)
    huge = "LINE\n" * 1500
    alert = Alert(message=huge, severity=Severity.LOW)

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        result = transport.send(alert)

    assert result.success is True
    post.assert_called_once()
    bio = post.call_args.kwargs["files"]["files[0]"][1]
    bio.seek(0)
    assert bio.read().decode("utf-8").rstrip().endswith("— end —")


def test_discord_transport_embed_mode_multipart_with_embed() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(attach_exception_over_chars=50)
    alert = Alert(message="short", severity=Severity.HIGH, exception=ValueError("x"))

    with patch("team_alerts.transports.discord.format_exception", return_value="E" * 200):
        with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
            result = transport.send(alert)

    assert result.success is True
    post.assert_called_once()
    files = post.call_args.kwargs["files"]
    payload = json.loads(files["payload_json"][1])
    assert "embeds" in payload
    assert payload["embeds"][0]["color"] is not None
    assert "attachments" in payload
    assert len(payload["attachments"]) == 1
    assert [a["filename"] for a in payload["attachments"]] == ["traceback.txt"]
    assert "short" in payload["embeds"][0].get("description", "")
    fields = payload["embeds"][0].get("fields") or []
    assert not any(f.get("name") == "Exception" for f in fields)


def test_discord_transport_embed_overflow_and_traceback_two_attachments() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    body = ("X" * 120 + "\n") * 400
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        err = exc

    alert = Alert(message=body, severity=Severity.HIGH, title="T", exception=err, service="s", environment="e")
    long_tb = ("Z" * 100 + "\n") * 20

    with patch("team_alerts.transports.discord.format_exception", return_value=long_tb):
        with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
            result = transport.send(alert)

    assert result.success is True
    payload = json.loads(post.call_args.kwargs["files"]["payload_json"][1])
    names = [a["filename"] for a in payload["attachments"]]
    assert names == ["message.txt", "traceback.txt"]


def test_discord_transport_embed_overflow_long_message_short_traceback_one_file() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    body = ("X" * 120 + "\n") * 400
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        err = exc

    alert = Alert(message=body, severity=Severity.HIGH, title="T", exception=err, service="s", environment="e")

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(alert)

    assert result.success is True
    payload = json.loads(post.call_args.kwargs["files"]["payload_json"][1])
    assert [a["filename"] for a in payload["attachments"]] == ["message.txt"]
    fields = payload["embeds"][0].get("fields") or []
    assert any(f.get("name") == "Exception" for f in fields)


def test_discord_transport_embed_short_traceback_json_exception_field() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    alert = Alert(message="ok", severity=Severity.HIGH, exception=ValueError("x"))

    with patch("team_alerts.transports.discord.format_exception", return_value="ValueError: x\n  short"):
        with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
            transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
            result = transport.send(alert)

    assert result.success is True
    assert "json" in post.call_args.kwargs
    payload = post.call_args.kwargs["json"]
    fields = payload["embeds"][0].get("fields") or []
    exc_f = next(f for f in fields if f.get("name") == "Exception")
    assert "ValueError" in exc_f["value"]
    assert "files" not in post.call_args.kwargs


def test_discord_transport_embed_overflow_message_as_attachment() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    body = ("Lorem line " * 500 + "\n") * 30
    alert = Alert(message=body, severity=Severity.LOW, title="Bulk export", service="etl", environment="prod")

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(alert)

    assert result.success is True
    post.assert_called_once()
    files = post.call_args.kwargs["files"]
    payload = json.loads(files["payload_json"][1])
    assert payload["attachments"][0]["filename"] == "message.txt"
    bio = files["files[0]"][1]
    bio.seek(0)
    assert b"Lorem line" in bio.read()
