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
from team_alerts.transports.discord import DiscordTransport


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
    content = kwargs["json"]["content"]
    assert content
    assert content.startswith(DEFAULT_ALERT_BANNER_LINE + "\n")
    assert "timeout" in kwargs


def test_discord_transport_send_http_error() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 429
    mock_resp.text = "rate limited"

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp):
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(Alert(message="m", severity=Severity.HIGH))

    assert result.success is False
    assert result.status_code == 429
    assert result.error_message == "HTTP 429"


def test_discord_transport_sends_multiple_chunks_for_long_alert() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    huge = "LINE\n" * 1500
    alert = Alert(message=huge, severity=Severity.LOW, title="long")

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(alert)

    assert result.success is True
    assert post.call_count >= 2


def test_discord_transport_includes_github_url_in_content() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    tests_dir = str(Path(__file__).resolve().parent)
    gh = GitHubLinkOptions(repository="org/repo", ref="deadbeef", source_root=tests_dir)
    opts = DiscordTransportOptions(github=gh)

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

    opts = DiscordTransportOptions(attach_exception_over_chars=50)
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

    opts = DiscordTransportOptions(alert_banner="")
    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        transport.send(Alert(message="m", severity=Severity.LOW))

    content = post.call_args.kwargs["json"]["content"]
    assert not content.startswith(DEFAULT_ALERT_BANNER_LINE)
    assert content.startswith("**[LOW]**")


def test_discord_transport_request_exception() -> None:
    with patch(
        "team_alerts.transports.discord.requests.post",
        side_effect=requests.Timeout("timed out"),
    ):
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y")
        result = transport.send(Alert(message="m", severity=Severity.LOW))

    assert result.success is False
    assert result.status_code is None
    assert result.error_message is not None
    assert "timed out" in result.error_message


def test_discord_transport_embed_mode_posts_embed() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(use_embeds=True)
    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        result = transport.send(Alert(message="hello", severity=Severity.CRITICAL, title="T"))

    assert result.success is True
    kwargs = post.call_args.kwargs
    assert "json" in kwargs
    embeds = kwargs["json"]["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["color"] == EMBED_COLOR_CRITICAL
    assert embeds[0]["title"] == "T"
    assert "hello" in embeds[0]["description"]


def test_discord_transport_allowed_mentions_roles() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    mentions = AllowedMentionsOptions(role_ids=("111", "222"))
    opts = DiscordTransportOptions(allowed_mentions=mentions)

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

    opts = DiscordTransportOptions(alert_banner="", alert_footer="— end —")
    huge = "LINE\n" * 1500
    alert = Alert(message=huge, severity=Severity.LOW)

    with patch("team_alerts.transports.discord.requests.post", return_value=mock_resp) as post:
        transport = DiscordTransport("https://discord.com/api/webhooks/x/y", options=opts)
        result = transport.send(alert)

    assert result.success is True
    assert post.call_count >= 2
    last = post.call_args_list[-1].kwargs["json"]["content"]
    assert last.rstrip().endswith("— end —")


def test_discord_transport_embed_mode_multipart_with_embed() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    opts = DiscordTransportOptions(use_embeds=True, attach_exception_over_chars=50)
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
