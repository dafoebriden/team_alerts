"""
Live integration tests against a real Discord webhook.

Default transport uses **embed mode**: short ``Alert.message`` text is inlined in the
embed description; long bodies use ``message.txt``. Short tracebacks use an
``Exception`` embed field; long ones use ``traceback.txt`` on the same multipart
post when needed. No multi-chunk ``content`` chains for overflow.

Set ``RUN_LIVE_DISCORD_TESTS=1`` and ``DISCORD_WEBHOOK`` to enable, or define
them in ``.env.local`` at the repo root (loaded automatically by ``conftest.py``).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace

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
    """Low-severity default transport: embed with short narrative inlined (JSON webhook)."""
    client = AlertClient.from_discord_webhook_env()
    result = client.low(
        "Nightly eligibility export finished within SLA; no operator action required.",
        title="Scheduled export completed",
        service="scheduling-worker",
        environment=os.environ.get("DEPLOY_ENV", os.environ.get("ENV", "staging")),
        run_id=f"nightly-export-{uuid.uuid4().hex[:10]}",
    )
    _assert_send_ok(result, label="embed ping")


def test_live_explicit_plain_text_payload() -> None:
    """Short body: classic ``content`` only (``discord_payload_style='plain'``)."""
    client = AlertClient.from_discord_webhook_env()
    result = client.send(
        Alert(
            message="Canary check: plain-text path still delivers to this webhook.",
            severity=Severity.LOW,
            title="Synthetic canary",
            service="observability",
            environment=os.environ.get("ENV", "staging"),
            discord_payload_style="plain",
        )
    )
    _assert_send_ok(result, label="plain canary")


def test_live_plain_long_body_single_multipart_file() -> None:
    """Plain mode over 2000 chars: one webhook with ``message.txt`` (no follow-up chunks)."""
    client = AlertClient.from_discord_webhook_env()
    lines = [f"[{i:04d}] indexer shard=replica-B bytes_out={8000 + i}" for i in range(350)]
    body = "Log excerpt (plain transport):\n" + "\n".join(lines)
    result = client.send(
        Alert(
            message=body,
            severity=Severity.HIGH,
            title="Indexer saturation snapshot",
            service="search-indexer",
            environment=os.environ.get("ENV", "staging"),
            discord_payload_style="plain",
            run_id=f"plain-long-{uuid.uuid4().hex[:10]}",
        )
    )
    _assert_send_ok(result, label="plain long multipart")


def test_live_upstream_dependency_failure() -> None:
    """HIGH outage: embed with metadata fields and narrative inlined in the description."""
    client = AlertClient.from_discord_webhook_env()
    cid = str(uuid.uuid4())
    alert = Alert(
        message=(
            "SalesOrder API returned HTTP 503 on three consecutive attempts. "
            "Circuit breaker opened; intake paused for 60 seconds before automatic retry."
        ),
        severity=Severity.HIGH,
        title="Upstream EHR API unavailable",
        service="lehans-webhook",
        environment=os.environ.get("ENV", "production"),
        correlation_id=cid,
        run_id=f"ingest-{uuid.uuid4().hex[:12]}",
        dedupe_key="dependency:brightree:salesorder:503",
        metadata={
            "endpoint": "https://api.brightree.net/…/SalesOrder",
            "attempts": 3,
            "last_status": 503,
        },
    )
    result = client.send(alert)
    _assert_send_ok(result, label="upstream failure")


def test_live_handler_exception_with_traceback() -> None:
    """Critical failure: embed with narrative + ``Exception`` field for a typical short stack."""

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
        message=(
            "Could not route inbound form webhook: payload is missing submission_id. "
            "Request was rejected before persistence."
        ),
        severity=Severity.CRITICAL,
        title="Inbound webhook rejected",
        exception=exc,
        service="jotform-router",
        environment=os.environ.get("ENV", "production"),
        correlation_id=str(uuid.uuid4()),
        dedupe_key="jotform:webhook:missing_submission_id",
        metadata={"form_id": "901234", "ingress": "public-webhook"},
    )
    result = client.send(alert)
    _assert_send_ok(result, label="handler traceback")


def test_live_long_log_tail_style_message() -> None:
    """Long log body: full text in ``message.txt``; embed description is headers + pointer + metadata fields."""
    lines = [f"[{i:04d}] worker=pool-A status=ok latency_ms={20 + (i % 17)}" for i in range(120)]
    body = "Last 120 lines from campaign-worker (rolling window):\n" + "\n".join(lines)
    client = AlertClient.from_discord_webhook_env()
    cid = str(uuid.uuid4())
    result = client.high(
        body,
        title="Worker log tail — elevated latency pattern",
        service="campaign-worker",
        environment="staging",
        correlation_id=cid,
        run_id=f"diag-{uuid.uuid4().hex[:12]}",
        dedupe_key="campaign-worker:pool-a:latency-snapshot",
        metadata={"line_count": len(lines), "window": "2m"},
    )
    _assert_send_ok(result, label="long message")


def test_live_traceback_as_file_attachment() -> None:
    """
    Deep stack: short narrative stays in the embed description; formatted traceback
    exceeds one ``Exception`` field so it is ``stacktrace.txt`` (custom filename) on
    the same multipart post as the embed.
    """

    def _deep_stack() -> None:
        def layer_three() -> None:
            raise RuntimeError(
                "Partner ACK window exceeded (30s)\n" + ("awaiting vendor response\n" * 80)
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
        exception_attachment_filename="stacktrace.txt",
        static_links={
            "runbook": "https://wiki.example.com/runbooks/vendor-timeouts",
        },
    )
    transport = DiscordTransport(WEBHOOK, options=opts)
    client = AlertClient(transport)
    alert = Alert(
        message="Settlement file pull failed after repeated vendor timeouts. Stack trace is attached as stacktrace.txt.",
        severity=Severity.CRITICAL,
        title="Vendor integration timeout",
        exception=exc,
        service="payments-adapter",
        environment=os.environ.get("ENV", "production"),
        correlation_id=str(uuid.uuid4()),
        run_id=f"payout-batch-{uuid.uuid4().hex[:10]}",
        metadata={"attachment": "stacktrace.txt", "partner": "ach-vendor"},
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
    """CI env: GitHub URL in embed fields; short narrative and typical traceback inlined in the embed when they fit."""
    opts = DiscordTransportOptions.from_env()
    if opts.github is None or not opts.github.source_root:
        pytest.skip("DiscordTransportOptions.from_env() did not yield github + source_root")

    try:
        raise AssertionError("Schema validation failed on deploy artifact")
    except AssertionError as exc:
        pass_exc = exc

    transport = DiscordTransport(WEBHOOK, options=opts)
    client = AlertClient(transport)
    result = client.send(
        Alert(
            message="Deploy gate failed during artifact verification. Traceback file shows the frame; GitHub link is in metadata.",
            severity=Severity.HIGH,
            title="Build verification failed",
            exception=pass_exc,
            service="github-actions",
            environment="ci",
            correlation_id=str(uuid.uuid4()),
            metadata={"workflow": os.environ.get("GITHUB_WORKFLOW", "unknown")},
        )
    )
    _assert_send_ok(result, label="github metadata")


def test_live_embed_mode_with_model_identity_fields() -> None:
    """Identity fields and reconciliation note inlined in the embed description (JSON post)."""
    base_opts = DiscordTransportOptions.from_env()
    opts = replace(
        base_opts,
        alert_banner="",
        embed_footer_text="reconciliation-monitor",
    )
    transport = DiscordTransport(WEBHOOK, options=opts)
    client = AlertClient(transport)
    cid = str(uuid.uuid4())
    result = client.send(
        Alert(
            message=(
                "Daily AR subledger is 0.18% off the GL control total for posting date. "
                "Variance is within auto-accept band but flagged for finance review."
            ),
            severity=Severity.MEDIUM,
            title="Reconciliation variance — review queue",
            service="finance-ledger",
            environment=os.environ.get("ENV", "production"),
            correlation_id=cid,
            run_id=f"recon-{uuid.uuid4().hex[:12]}",
            dedupe_key="finance:daily-recon:gl-drift",
        )
    )
    _assert_send_ok(result, label="embed identity")
