"""Discord incoming webhook transport."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from io import BytesIO
from typing import Any

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

from team_alerts.constants import (
    DEFAULT_ALERT_BANNER_LINE,
    DISCORD_CONTENT_MAX_CHARS,
    DISCORD_REQUEST_TIMEOUT,
)
from team_alerts.discord_embeds import (
    allowed_mentions_payload,
    build_alert_embed,
    traceback_fits_single_exception_field,
)
from team_alerts.discord_options import DiscordTransportOptions, GitHubLinkOptions
from team_alerts.exceptions import ConfigurationError
from team_alerts.formatters import (
    append_footer_to_last_chunk,
    apply_identity_markers_to_split_chunks,
    format_alert_discord_chunks,
    format_exception,
)
from team_alerts.links import github_blob_url, pick_github_frame, repo_relative_path
from team_alerts.models import Alert
from team_alerts.result import SendResult
from team_alerts.transports.base import BaseTransport
from team_alerts.webhook_retry import is_retriable_http_status, sleep_before_retry


def _use_embeds_effective(options: DiscordTransportOptions, alert: Alert) -> bool:
    style = alert.discord_payload_style
    if style == "embed":
        return True
    if style == "plain":
        return False
    return options.use_embeds


class DiscordTransport(BaseTransport):
    """
    Send alerts to Discord using an incoming webhook URL.

    Baseline from :meth:`~team_alerts.discord_options.DiscordTransportOptions.from_env`,
    then non-default fields from ``options`` (if given), then keyword arguments.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        options: DiscordTransportOptions | None = None,
        **option_overrides: Any,
    ) -> None:
        stripped = (webhook_url or "").strip()
        if not stripped:
            raise ConfigurationError("Discord webhook URL is missing or empty.")
        self._webhook_url = stripped
        merged = DiscordTransportOptions.from_env()
        if options is not None:
            merged = replace(merged, **options.nondefault_option_overrides())
        if option_overrides:
            merged = replace(merged, **option_overrides)
        self._options = merged

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

        if _use_embeds_effective(self._options, prepared):
            return self._send_embed_mode(prepared, tb_text, mentions)

        if use_file:
            chunks = list(
                format_alert_discord_chunks(
                    prepared,
                    include_exception_in_body=False,
                    exception_attachment_filename=self._options.exception_attachment_filename,
                    metadata_url_link_style=self._options.metadata_url_link_style,
                    alert_banner=_alert_banner_line(self._options),
                )
            )
            chunks = append_footer_to_last_chunk(chunks, self._options.alert_footer)
            full_plain = "\n".join(chunks)
            tb_bytes = _traceback_attachment_bytes(tb_text, self._options.max_attachment_bytes)
            body_bytes = _traceback_attachment_bytes(full_plain, self._options.max_attachment_bytes)
            return self._post_multipart_files(
                content="*(Traceback and full alert are attached.)*",
                embeds=None,
                files=[
                    (self._options.exception_attachment_filename, tb_bytes, "Python traceback"),
                    (self._options.message_attachment_filename, body_bytes, "Full alert text"),
                ],
                mentions=mentions,
            )

        chunks = list(
            format_alert_discord_chunks(
                prepared,
                metadata_url_link_style=self._options.metadata_url_link_style,
                alert_banner=_alert_banner_line(self._options),
            )
        )
        chunks = append_footer_to_last_chunk(chunks, self._options.alert_footer)
        full_plain = "\n".join(chunks)
        if len(full_plain) <= DISCORD_CONTENT_MAX_CHARS:
            return self._post_payload({"content": full_plain}, mentions=mentions)
        return self._post_multipart_files(
            content="*(Full alert attached.)*",
            embeds=None,
            files=[
                (
                    self._options.message_attachment_filename,
                    _traceback_attachment_bytes(full_plain, self._options.max_attachment_bytes),
                    "Full alert text",
                )
            ],
            mentions=mentions,
        )

    def _send_embed_mode(
        self,
        alert: Alert,
        tb_text: str,
        mentions: dict[str, Any] | None,
    ) -> SendResult:
        threshold = self._options.attach_exception_over_chars
        use_tb_file = _embed_traceback_as_file(tb_text, threshold)
        embed, overflow = build_alert_embed(
            alert,
            options=self._options,
            include_exception_in_body=bool(tb_text) and not use_tb_file,
            exception_text=tb_text if not use_tb_file else None,
        )

        footer = (self._options.alert_footer or "").strip()
        overflow_text = overflow.strip()
        files: list[tuple[str, bytes, str]] = []

        if overflow_text:
            body = overflow_text
            if footer and not use_tb_file:
                body = f"{body}\n\n{footer}"
            files.append(
                (
                    self._options.message_attachment_filename,
                    _traceback_attachment_bytes(body, self._options.max_attachment_bytes),
                    "Full message text",
                )
            )
        if use_tb_file:
            tb_body = tb_text
            if footer:
                tb_body = f"{tb_text}\n\n{footer}"
            files.append(
                (
                    self._options.exception_attachment_filename,
                    _traceback_attachment_bytes(tb_body, self._options.max_attachment_bytes),
                    "Python traceback",
                )
            )

        if files:
            return self._post_multipart_files(
                content="",
                embeds=[embed],
                files=files,
                mentions=mentions,
            )

        payload = _embed_json_payload(embed, footer or None)
        return self._post_payload(payload, mentions=mentions)

    def _post_payload(self, payload: dict[str, Any], *, mentions: dict[str, Any] | None = None) -> SendResult:
        body = _merge_mentions(payload, mentions)
        opts = self._options
        max_attempts = max(1, opts.webhook_max_attempts)
        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    self._webhook_url,
                    json=body,
                    timeout=DISCORD_REQUEST_TIMEOUT,
                )
            except (ConnectionError, Timeout, ChunkedEncodingError) as exc:
                last = SendResult(
                    success=False,
                    status_code=None,
                    response_text="",
                    error_message=str(exc),
                )
                if attempt >= max_attempts - 1:
                    return last
                sleep_before_retry(
                    attempt_index=attempt,
                    response=None,
                    base_delay_seconds=opts.webhook_retry_base_delay_seconds,
                    max_delay_seconds=opts.webhook_retry_max_delay_seconds,
                    jitter_seconds=opts.webhook_retry_jitter_seconds,
                    sleep_fn=time.sleep,
                )
                continue

            text = response.text or ""
            if response.ok:
                return SendResult(success=True, status_code=response.status_code, response_text=text)
            last = SendResult(
                success=False,
                status_code=response.status_code,
                response_text=text,
                error_message=f"HTTP {response.status_code}",
            )
            if attempt >= max_attempts - 1 or not is_retriable_http_status(response.status_code):
                return last
            sleep_before_retry(
                attempt_index=attempt,
                response=response,
                base_delay_seconds=opts.webhook_retry_base_delay_seconds,
                max_delay_seconds=opts.webhook_retry_max_delay_seconds,
                jitter_seconds=opts.webhook_retry_jitter_seconds,
                sleep_fn=time.sleep,
            )
        return SendResult(success=False, status_code=None, response_text="", error_message="send failed")

    def _post_multipart_files(
        self,
        *,
        content: str,
        embeds: list[dict[str, Any]] | None,
        files: list[tuple[str, bytes, str]],
        mentions: dict[str, Any] | None,
    ) -> SendResult:
        attachments: list[dict[str, Any]] = []
        multipart: dict[str, Any] = {}
        for i, (filename, file_bytes, description) in enumerate(files):
            desc = description if len(description) <= 100 else description[:99] + "…"
            attachments.append({"id": i, "filename": filename, "description": desc})
            multipart[f"files[{i}]"] = (filename, BytesIO(file_bytes), "text/plain; charset=utf-8")
        payload: dict[str, Any] = {}
        if content:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        payload["attachments"] = attachments
        payload = _merge_mentions(payload, mentions)
        opts = self._options
        max_attempts = max(1, opts.webhook_max_attempts)
        for attempt in range(max_attempts):
            attempt_multipart = dict(multipart)
            attempt_multipart["payload_json"] = (
                None,
                json.dumps(payload),
                "application/json; charset=utf-8",
            )
            try:
                response = requests.post(
                    self._webhook_url,
                    files=attempt_multipart,
                    timeout=DISCORD_REQUEST_TIMEOUT,
                )
            except (ConnectionError, Timeout, ChunkedEncodingError) as exc:
                last = SendResult(
                    success=False,
                    status_code=None,
                    response_text="",
                    error_message=str(exc),
                )
                if attempt >= max_attempts - 1:
                    return last
                sleep_before_retry(
                    attempt_index=attempt,
                    response=None,
                    base_delay_seconds=opts.webhook_retry_base_delay_seconds,
                    max_delay_seconds=opts.webhook_retry_max_delay_seconds,
                    jitter_seconds=opts.webhook_retry_jitter_seconds,
                    sleep_fn=time.sleep,
                )
                continue

            text = response.text or ""
            if response.ok:
                return SendResult(success=True, status_code=response.status_code, response_text=text)
            last = SendResult(
                success=False,
                status_code=response.status_code,
                response_text=text,
                error_message=f"HTTP {response.status_code}",
            )
            if attempt >= max_attempts - 1 or not is_retriable_http_status(response.status_code):
                return last
            sleep_before_retry(
                attempt_index=attempt,
                response=response,
                base_delay_seconds=opts.webhook_retry_base_delay_seconds,
                max_delay_seconds=opts.webhook_retry_max_delay_seconds,
                jitter_seconds=opts.webhook_retry_jitter_seconds,
                sleep_fn=time.sleep,
            )
        return SendResult(success=False, status_code=None, response_text="", error_message="send failed")

    def _post_multipart(
        self,
        *,
        content: str,
        file_bytes: bytes,
        filename: str,
        embeds: list[dict[str, Any]] | None = None,
        mentions: dict[str, Any] | None = None,
    ) -> SendResult:
        body = content or "*(see attachment for traceback)*"
        return self._post_multipart_files(
            content=body,
            embeds=embeds,
            files=[(filename, file_bytes, "Python traceback")],
            mentions=mentions,
        )


def _embed_traceback_as_file(tb_text: str, attach_exception_over_chars: int | None) -> bool:
    if not tb_text:
        return False
    if attach_exception_over_chars is not None and len(tb_text) > attach_exception_over_chars:
        return True
    return not traceback_fits_single_exception_field(tb_text)


def _embed_json_payload(embed: dict[str, Any], footer: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["embeds"] = [embed]
    if footer:
        out["content"] = footer
    return out


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
