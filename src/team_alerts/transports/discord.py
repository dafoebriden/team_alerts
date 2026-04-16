"""Discord incoming webhook transport."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from io import BytesIO
from typing import Any

import requests

from team_alerts.constants import DEFAULT_ALERT_BANNER_LINE, DISCORD_REQUEST_TIMEOUT
from team_alerts.discord_options import DiscordTransportOptions, GitHubLinkOptions
from team_alerts.exceptions import ConfigurationError
from team_alerts.formatters import format_alert_discord_chunks, format_exception
from team_alerts.links import github_blob_url, pick_github_frame, repo_relative_path
from team_alerts.models import Alert
from team_alerts.result import SendResult
from team_alerts.transports.base import BaseTransport


class DiscordTransport(BaseTransport):
    """Send alerts to Discord using an incoming webhook URL."""

    def __init__(
        self,
        webhook_url: str,
        *,
        options: DiscordTransportOptions | None = None,
    ) -> None:
        stripped = (webhook_url or "").strip()
        if not stripped:
            raise ConfigurationError("Discord webhook URL is missing or empty.")
        self._webhook_url = stripped
        self._options = options or DiscordTransportOptions()

    @property
    def webhook_url(self) -> str:
        return self._webhook_url

    @property
    def options(self) -> DiscordTransportOptions:
        return self._options

    def send(self, alert: Alert) -> SendResult:
        prepared = _enrich_alert(alert, self._options)
        tb_text = (
            format_exception(prepared.exception) if prepared.exception is not None else ""
        )
        threshold = self._options.attach_exception_over_chars
        use_file = (
            threshold is not None
            and prepared.exception is not None
            and tb_text
            and len(tb_text) > threshold
        )

        if use_file:
            chunks = format_alert_discord_chunks(
                prepared,
                include_exception_in_body=False,
                exception_attachment_filename=self._options.exception_attachment_filename,
                metadata_url_link_style=self._options.metadata_url_link_style,
                alert_banner=_alert_banner_line(self._options),
            )
            tb_bytes = _traceback_attachment_bytes(tb_text, self._options.max_attachment_bytes)
            first, rest = chunks[0], chunks[1:]
            last = self._post_multipart(first, tb_bytes, self._options.exception_attachment_filename)
            if not last.success:
                return last
            for content in rest:
                last = self._post_payload({"content": content})
                if not last.success:
                    return last
            return last

        last: SendResult | None = None
        for content in format_alert_discord_chunks(
            prepared,
            metadata_url_link_style=self._options.metadata_url_link_style,
            alert_banner=_alert_banner_line(self._options),
        ):
            last = self._post_payload({"content": content})
            if not last.success:
                return last
        return last or SendResult(success=True, status_code=None, response_text="", error_message=None)

    def _post_payload(self, payload: dict[str, Any]) -> SendResult:
        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=DISCORD_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            return SendResult(
                success=False,
                status_code=None,
                response_text="",
                error_message=str(exc),
            )

        text = response.text or ""
        if response.ok:
            return SendResult(success=True, status_code=response.status_code, response_text=text)
        return SendResult(
            success=False,
            status_code=response.status_code,
            response_text=text,
            error_message=f"HTTP {response.status_code}",
        )

    def _post_multipart(self, content: str, file_bytes: bytes, filename: str) -> SendResult:
        payload = {
            "content": content or "*(see attachment for traceback)*",
            "attachments": [{"id": 0, "filename": filename, "description": "Python traceback"}],
        }
        multipart: dict[str, Any] = {
            "payload_json": (None, json.dumps(payload), "application/json; charset=utf-8"),
            "files[0]": (filename, BytesIO(file_bytes), "text/plain; charset=utf-8"),
        }
        try:
            response = requests.post(
                self._webhook_url,
                files=multipart,
                timeout=DISCORD_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            return SendResult(
                success=False,
                status_code=None,
                response_text="",
                error_message=str(exc),
            )
        text = response.text or ""
        if response.ok:
            return SendResult(success=True, status_code=response.status_code, response_text=text)
        return SendResult(
            success=False,
            status_code=response.status_code,
            response_text=text,
            error_message=f"HTTP {response.status_code}",
        )


def _alert_banner_line(opts: DiscordTransportOptions) -> str:
    """Resolve banner text for ``format_alert_discord_chunks`` (empty = disabled)."""
    raw = opts.alert_banner
    if raw == "":
        return ""
    if raw is None:
        return DEFAULT_ALERT_BANNER_LINE
    line = raw.split("\n", 1)[0].strip()
    return line[:400] if line else DEFAULT_ALERT_BANNER_LINE


def _traceback_attachment_bytes(text: str, max_bytes: int) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return raw
    note = "\n\n… (traceback truncated for Discord attachment size cap)\n"
    note_b = note.encode("utf-8")
    budget = max_bytes - len(note_b)
    if budget <= 0:
        return note_b[:max_bytes]
    truncated = raw[:budget].decode("utf-8", errors="replace")
    out = (truncated + note).encode("utf-8")
    if len(out) > max_bytes:
        return out[:max_bytes]
    return out


def _enrich_alert(alert: Alert, options: DiscordTransportOptions) -> Alert:
    meta = dict(alert.metadata)
    changed = False
    for key, url in options.static_links.items():
        if key not in meta:
            meta[key] = url
            changed = True
    for env_name in options.env_metadata_keys:
        val = os.environ.get(env_name)
        if val not in (None, "") and env_name not in meta:
            meta[env_name] = val
            changed = True
    if options.github and alert.exception is not None:
        url = _github_url_for_exception(alert.exception, options.github)
        if url and options.github.metadata_key not in meta:
            meta[options.github.metadata_key] = url
            changed = True
    if not changed:
        return alert
    return replace(alert, metadata=meta)


def _github_url_for_exception(exc: Exception, gh: GitHubLinkOptions) -> str | None:
    if not gh.source_root:
        return None
    frame = pick_github_frame(
        exc,
        skip_site_packages=gh.skip_site_packages_frames,
    )
    if frame is None:
        return None
    file_path, lineno = frame
    rel = repo_relative_path(file_path, gh.source_root)
    if rel is None:
        return None
    return github_blob_url(
        repository=gh.repository,
        ref=gh.ref,
        repo_path=rel,
        line=lineno,
        base_url=gh.base_url,
    )
