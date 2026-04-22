"""Unit tests for webhook retry helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from team_alerts.webhook_retry import (
    is_retriable_http_status,
    parse_retry_after_seconds,
    sleep_before_retry,
)


def test_parse_retry_after_seconds_integer() -> None:
    r = MagicMock()
    r.headers = {"Retry-After": "12"}
    assert parse_retry_after_seconds(r) == 12.0


def test_parse_retry_after_seconds_missing() -> None:
    r = MagicMock()
    r.headers = {}
    assert parse_retry_after_seconds(r) is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [(429, True), (503, True), (400, False), (200, False)],
)
def test_is_retriable_http_status(code: int, expected: bool) -> None:
    assert is_retriable_http_status(code) is expected


def test_sleep_before_retry_none_response_uses_backoff() -> None:
    slept: list[float] = []

    sleep_before_retry(
        attempt_index=1,
        response=None,
        base_delay_seconds=1.0,
        max_delay_seconds=100.0,
        jitter_seconds=0.0,
        sleep_fn=slept.append,
    )

    assert slept == [2.0]


def test_sleep_before_retry_429_with_retry_after() -> None:
    slept: list[float] = []
    r = MagicMock()
    r.status_code = 429
    r.headers = {"Retry-After": "5"}

    sleep_before_retry(
        attempt_index=0,
        response=r,
        base_delay_seconds=1.0,
        max_delay_seconds=100.0,
        jitter_seconds=0.0,
        sleep_fn=slept.append,
    )

    assert slept == [5.0]
