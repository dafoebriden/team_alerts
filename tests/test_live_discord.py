"""
Live integration tests against a real Discord webhook.

Set ``RUN_LIVE_DISCORD_TESTS=1`` and ``DISCORD_WEBHOOK`` to enable, or define
them in ``.env.local`` at the repo root (loaded automatically by ``conftest.py``).
"""

from __future__ import annotations

import os
import uuid

import pytest

from team_alerts.client import AlertClient
from team_alerts.constants import Severity
from team_alerts.discord_options import DiscordTransportOptions
from team_alerts.models import Alert
from team_alerts.transports.discord import DiscordTransport

RUN_LIVE = os.environ.get("RUN_LIVE_DISCORD_TESTS", "").strip() == "1"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()


pytestmark = pytest.mark.skipif(
    not RUN_LIVE or not WEBHOOK,
    reason="Set RUN_LIVE_DISCORD_TESTS=1 and DISCORD_WEBHOOK to run live Discord tests.",
)


def _assert_send_ok(result, *, label: str) -> None:
    assert result.success, (
        f"{label}: "
        f"success={result.success} status={result.status_code} "
        f"err={result.error_message!r} body={result.response_text[:500]!r}"
    )


def test_live_plain_operational_ping() -> None:
    """Routine low-severity notice (deploy marker, smoke check)."""
    client = AlertClient.from_discord_webhook_env()
    result = client.low(
        "Scheduled job finished successfully; no action required.",
        title="Live suite: operational ping",
        service="team_alerts",
        environment=os.environ.get("PYTEST_CURRENT_TEST", "pytest")[:80],
    )
    _assert_send_ok(result, label="plain ping")


def test_live_upstream_dependency_failure() -> None:
    """Typical API / dependency outage: HIGH with structured metadata."""
    client = AlertClient.from_discord_webhook_env()
    alert = Alert(
        message=(
            "Brightree SalesOrder API returned HTTP 503 three times in a row. "
            "Circuit breaker opened; intake queue paused for 60s."
        ),
        severity=Severity.HIGH,
        title="Live suite: upstream dependency",
        service="lehans-webhook",
        environment=os.environ.get("ENV", "local"),
        metadata={
            "endpoint": "https://api.brightree.net/…/SalesOrder",
            "attempts": 3,
            "last_status": 503,
            "correlation_id": str(uuid.uuid4()),
        },
    )
    result = client.send(alert)
    _assert_send_ok(result, label="upstream failure")


def test_live_handler_exception_with_traceback() -> None:
    """Webhook-style failure: real exception so Discord shows a traceback block."""

    def _inner_parse_payload(raw: dict) -> str:
        if "submission_id" not in raw:
            raise KeyError("submission_id")
        return raw["submission_id"]

    def _handler_simulation() -> None:
        payload = {"form_id": "901234"}
        _inner_parse_payload(payload)

    exc: Exception | None = None
    try:
        _handler_simulation()
    except KeyError as err:
        exc = err

    assert exc is not None
    client = AlertClient.from_discord_webhook_env()
    alert = Alert(
        message="Jotform webhook could not be routed: missing submission_id on payload.",
        severity=Severity.CRITICAL,
        title="Live suite: handler exception",
        exception=exc,
        service="jotform-router",
        environment=os.environ.get("ENV", "local"),
        metadata={"form_id": "901234", "live_test": "test_live_discord"},
    )
    result = client.send(alert)
    _assert_send_ok(result, label="handler traceback")


def test_live_long_log_tail_style_message() -> None:
    """Simulates dumping last N lines of logs into the alert (chunked delivery)."""
    lines = [f"[{i:04d}] worker=pool-A status=ok latency_ms={20 + (i % 17)}" for i in range(120)]
    body = "Recent worker log tail (synthetic):\n" + "\n".join(lines)
    client = AlertClient.from_discord_webhook_env()
    result = client.high(
        body,
        title="Live suite: long message / multi-chunk",
        service="campaign-worker",
        environment="staging",
        metadata={"line_count": len(lines), "truncation": "none"},
    )
    _assert_send_ok(result, label="long message")


def test_live_traceback_as_file_attachment() -> None:
    """
    Forces multipart upload: short in-body summary + traceback.txt attachment.

    Uses a low character threshold so a normal Python traceback exceeds it.
    """

    def _deep_stack() -> None:
        def layer_three() -> None:
            raise RuntimeError(
                "Simulated vendor timeout after 30s\n" + ("…waiting for ACK\n" * 80)
            )

        def layer_two() -> None:
            layer_three()

        def layer_one() -> None:
            layer_two()

        layer_one()

    exc: Exception | None = None
    try:
        _deep_stack()
    except RuntimeError as err:
        exc = err

    assert exc is not None
    opts = DiscordTransportOptions(
        attach_exception_over_chars=400,
        exception_attachment_filename="live_test_traceback.txt",
        static_links={
            "docs": "https://discord.com/developers/docs/resources/webhook",
        },
    )
    transport = DiscordTransport(WEBHOOK, options=opts)
    client = AlertClient(transport)
    alert = Alert(
        message="Downstream call failed; full stack in attachment.",
        severity=Severity.CRITICAL,
        title="Live suite: traceback attachment",
        exception=exc,
        service="team_alerts-live",
        environment=os.environ.get("ENV", "local"),
        metadata={"attachment_mode": "forced", "threshold_chars": 400},
    )
    result = client.send(alert)
    _assert_send_ok(result, label="traceback attachment")


@pytest.mark.skipif(
    not os.environ.get("GITHUB_REPOSITORY", "").strip()
    or not (
        os.environ.get("GITHUB_SHA", "").strip()
        or os.environ.get("GIT_COMMIT", "").strip()
        or os.environ.get("GITHUB_REF_NAME", "").strip()
    ),
    reason="Set GITHUB_REPOSITORY and GITHUB_SHA (or GIT_COMMIT / GITHUB_REF_NAME) for GitHub link live test.",
)
def test_live_github_metadata_when_ci_env_present() -> None:
    """If CI-style env vars exist, verify GitHub line link appears in the message."""
    opts = DiscordTransportOptions.from_env()
    if opts.github is None or not opts.github.source_root:
        pytest.skip("DiscordTransportOptions.from_env() did not yield github + source_root")

    try:
        raise AssertionError("deliberate failure for GitHub link frame")
    except AssertionError as exc:
        pass_exc = exc

    transport = DiscordTransport(WEBHOOK, options=opts)
    client = AlertClient(transport)
    result = client.send(
        Alert(
            message="CI live check: exception frame should link to this test file.",
            severity=Severity.HIGH,
            title="Live suite: GitHub metadata",
            exception=pass_exc,
            service="github-actions",
            environment="ci",
            metadata={"workflow": os.environ.get("GITHUB_WORKFLOW", "n/a")},
        )
    )
    _assert_send_ok(result, label="github metadata")
