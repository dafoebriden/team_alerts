"""Tests for the ``Alert`` model."""

from __future__ import annotations

import pytest

from team_alerts.constants import Severity
from team_alerts.models import Alert


def test_alert_defaults() -> None:
    alert = Alert(message="hello", severity=Severity.LOW)
    assert alert.message == "hello"
    assert alert.severity is Severity.LOW
    assert alert.title is None
    assert alert.exception is None
    assert alert.metadata == {}
    assert alert.service is None
    assert alert.environment is None


def test_alert_metadata_is_isolated_per_instance() -> None:
    a = Alert(message="a", severity=Severity.HIGH)
    b = Alert(message="b", severity=Severity.HIGH)
    a.metadata["k"] = 1
    assert b.metadata == {}


def test_alert_with_optional_fields() -> None:
    err = ValueError("boom")
    alert = Alert(
        message="m",
        severity=Severity.CRITICAL,
        title="T",
        exception=err,
        metadata={"x": 1},
        service="api",
        environment="staging",
    )
    assert alert.title == "T"
    assert alert.exception is err
    assert alert.metadata == {"x": 1}
    assert alert.service == "api"
    assert alert.environment == "staging"


def test_severity_values() -> None:
    assert Severity.LOW.value == "LOW"
    assert Severity.HIGH.value == "HIGH"
    assert Severity.CRITICAL.value == "CRITICAL"


@pytest.mark.parametrize(
    "member",
    [Severity.LOW, Severity.HIGH, Severity.CRITICAL],
)
def test_severity_is_str_enum(member: Severity) -> None:
    assert isinstance(member, str)
    assert member in ("LOW", "HIGH", "CRITICAL")
