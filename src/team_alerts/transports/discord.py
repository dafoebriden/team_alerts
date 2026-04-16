"""Discord incoming webhook transport."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from io import BytesIO
from typing import Any

import requests

from team_alerts.constants import DEFAULT_ALERT_BANNER_LINE, DEFAULT_CHUNK_SIZE, DISCORD_REQUEST_TIMEOUT
from team_alerts.discord_embeds import allowed_mentions_payload, build_alert_embed
from team_alerts.discord_options import DiscordTransportOptions, GitHubLinkOptions
from team_alerts.exceptions import ConfigurationError
from team_alerts.formatters import (
    append_footer_to_last_chunk,
    format_alert_discord_chunks,
    format_exception,
    split_long_text,
)
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
        mentions = allowed_mentions_payload(self._options.allowed_mentions)

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

        if self._options.use_embeds:
            return self._send_embed_mode(prepared, tb_text, use_file, mentions)

        if use_file:
            chunks = format_alert_discord_chunks(
                prepared,
                include_exception_in_body=False,
                exception_attachment_filename=self._options.exception_attachment_filename,
                metadata_url_link_style=self._options.metadata_url_link_style,
                alert_banner=_alert_banner_line(self._options),
            )
            chunks = append_footer_to_last_chunk(chunks, self._options.alert_footer)
            tb_bytes = _traceback_attachment_bytes(tb_text, self._options.max_attachment_bytes)
            first, rest = chunks[0], chunks[1:]
            last = self._post_multipart(
                content=first,
                file_bytes=tb_bytes,
                filename=self._options.exception_attachment_filename,
                mentions=mentions,
            )
            if not last.success:
                return last
            for content in rest:
                last = self._post_payload({"content": content}, mentions=mentions)
                if not last.success:
                    return last
            return last

        chunks = list(
            format_alert_discord_chunks(
                prepared,
                metadata_url_link_style=self._options.metadata_url_link_style,
                alert_banner=_alert_banner_line(self._options),
            )
        )
        chunks = append_footer_to_last_chunk(chunks, self._options.alert_footer)

        last: SendResult | None = None
        for content in chunks:
            last = self._post_payload({"content": content}, mentions=mentions)
            if not last.success:
                return last
        return last or SendResult(success=True, status_code=None, response_text="", error_message=None)

    def _send_embed_mode(
        self,
        alert: Alert,
        tb_text: str,
        use_file: bool,
        mentions: dict[str, Any] | None,
    ) -> SendResult:
        threshold = self._options.attach_exception_over_chars
        include_tb_in_embed = (
            alert.exception is not None
            and bool(tb_text)
            and not use_file
            and (threshold is None or len(tb_text) <= threshold)
        )
        exc_for_embed = tb_text if include_tb_in_embed else None

        embed, overflow = build_alert_embed(
            alert,
            options=self._options,
            include_exception_in_body=bool(exc_for_embed),
            exception_text=exc_for_embed,
        )

        tail: list[str] = []
        if overflow.strip():
            tail.extend(split_long_text(overflow.strip(), chunk_size=DEFAULT_CHUNK_SIZE))
        tail = append_footer_to_last_chunk(tail, self._options.alert_footer)

        last: SendResult | None = None

        if use_file:
            tb_bytes = _traceback_attachment_bytes(tb_text, self._options.max_attachment_bytes)
            note = "*(traceback attached)*"
            last = self._post_multipart(
                content=note,
                file_bytes=tb_bytes,
                filename=self._options.exception_attachment_filename,
                embeds=[embed],
                mentions=mentions,
            )
        else:
            payload: dict[str, Any] = {"embeds": [embed]}
            last = self._post_payload(payload, mentions=mentions)

        if last is None or not last.success:
            return last or SendResult(success=False, status_code=None, response_text="", error_message="send failed")

        for content in tail:
            last = self._post_payload({"content": content}, mentions=mentions)
            if not last.success:
                return last
        return last

    def _post_payload(self, payload: dict[str, Any], *, mentions: dict[str, Any] | None = None) -> SendResult:
        body = _merge_mentions(payload, mentions)
        try:
            response = requests.post(
                self._webhook_url,
                json=body,
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

    def _post_multipart(
        self,
        *,
        content: str,
        file_bytes: bytes,
        filename: str,
        embeds: list[dict[str, Any]] | None = None,
        mentions: dict[str, Any] | None = None,
    ) -> SendResult:
        payload: dict[str, Any] = {
            "content": content or "*(see attachment for traceback)*",
            "attachments": [{"id": 0, "filename": filename, "description": "Python traceback"}],
        }
        if embeds is not None:
            payload["embeds"] = embeds
        payload = _merge_mentions(payload, mentions)
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


def _merge_mentions(payload: dict[str, Any], mentions: dict[str, Any] | None) -> dict[str, Any]:
    if not mentions:
        return payload
    merged = dict(payload)
    merged["allowed_mentions"] = mentions
    return merged


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
