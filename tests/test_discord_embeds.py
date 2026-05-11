"""Tests for Discord embed metadata field layout and code fences."""

from __future__ import annotations

from team_alerts.constants import Severity
from team_alerts.discord_embeds import build_alert_embed, metadata_to_embed_fields
from team_alerts.discord_options import DiscordTransportOptions
from team_alerts.models import Alert


def test_metadata_plain_then_fenced_puts_short_values_first() -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fields = metadata_to_embed_fields(
        {"z_id": uid, "handler": "run_job", "state": "failed"},
        url_link_style="angle",
        metadata_embed_field_order="plain_then_fenced",
        metadata_code_fence_style="auto",
    )
    names = [f["name"] for f in fields]
    assert names.index("handler") < names.index("state")
    assert names.index("state") < names.index("z_id")
    assert fields[-1]["value"] == f"```{uid}```"
    assert fields[0]["inline"] is True
    assert fields[1]["inline"] is True


def test_metadata_alphabetical_order_ignores_fence_groups() -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fields = metadata_to_embed_fields(
        {"z_id": uid, "handler": "x"},
        url_link_style="angle",
        metadata_embed_field_order="alphabetical",
        metadata_code_fence_style="auto",
    )
    assert [f["name"] for f in fields] == ["handler", "z_id"]


def test_metadata_embed_fields_inline_false() -> None:
    fields = metadata_to_embed_fields(
        {"k": "hi"},
        url_link_style="angle",
        metadata_embed_fields_inline=False,
    )
    assert fields[0]["inline"] is False


def test_metadata_code_fence_off() -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fields = metadata_to_embed_fields(
        {"id": uid},
        url_link_style="angle",
        metadata_code_fence_style="off",
    )
    assert not fields[0]["value"].startswith("```")


def test_metadata_code_fence_all() -> None:
    fields = metadata_to_embed_fields(
        {"k": "short"},
        url_link_style="angle",
        metadata_code_fence_style="all",
    )
    assert fields[0]["value"] == "```short```"


def test_metadata_plain_keys_override_fence() -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fields = metadata_to_embed_fields(
        {"id": uid},
        url_link_style="angle",
        metadata_code_fence_style="all",
        metadata_plain_keys=("id",),
    )
    assert fields[0]["value"] == uid


def test_metadata_code_fence_keys_force_fence() -> None:
    fields = metadata_to_embed_fields(
        {"label": "ok"},
        url_link_style="angle",
        metadata_code_fence_style="auto",
        metadata_code_fence_keys=("label",),
    )
    assert fields[0]["value"] == "```ok```"


def test_build_alert_embed_exception_after_metadata_fenced_block() -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    alert = Alert(
        title="t",
        message="m",
        severity=Severity.HIGH,
        metadata={"handler": "h", "trace_id": uid},
    )
    opts = DiscordTransportOptions()
    embed, _overflow = build_alert_embed(
        alert,
        options=opts,
        include_exception_in_body=True,
        exception_text="boom",
    )
    names = [f["name"] for f in embed["fields"]]
    assert names == ["handler", "trace_id", "Exception"]
    assert embed["fields"][-1]["name"] == "Exception"
    assert embed["fields"][-1]["inline"] is False
