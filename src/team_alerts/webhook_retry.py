"""Backoff and Retry-After handling for outbound webhook HTTP posts."""

from __future__ import annotations

import random
import time
from email.utils import parsedate_to_datetime
from typing import Callable

import requests


def parse_retry_after_seconds(response: requests.Response) -> float | None:
    """
    Parse ``Retry-After`` from a response.

    Supports delay-seconds (integer) and HTTP-date forms. Returns ``None`` if the
    header is missing or cannot be parsed.
    """
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None
        delay = dt.timestamp() - time.time()
        return max(0.0, delay)
    except (TypeError, ValueError, OSError):
        return None


def is_retriable_http_status(status_code: int) -> bool:
    """Whether an HTTP status code is worth retrying for Discord webhooks."""
    return status_code in (408, 429, 502, 503, 504)


def sleep_before_retry(
    *,
    attempt_index: int,
    response: requests.Response | None,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_seconds: float,
    sleep_fn: Callable[[float], None],
) -> None:
    """
    ``attempt_index`` is zero-based: first retry wait uses ``attempt_index == 0``.

    For 429 responses, prefers ``Retry-After`` when present, otherwise exponential
    backoff. Other retriable statuses use exponential backoff with optional jitter.
    When ``response`` is ``None`` (connection-level failure), only backoff+jitter
    applies.
    """
    jitter = random.uniform(0.0, max(0.0, jitter_seconds))
    if response is None:
        base = max(0.0, base_delay_seconds)
        cap = max(0.0, max_delay_seconds)
        sleep_fn(min(cap, base * (2**attempt_index)) + jitter)
        return
    if response.status_code == 429:
        ra = parse_retry_after_seconds(response)
        if ra is not None:
            delay = min(max_delay_seconds, ra + jitter)
            sleep_fn(delay)
            return
    base = max(0.0, base_delay_seconds)
    cap = max(0.0, max_delay_seconds)
    exp = min(cap, base * (2**attempt_index)) + jitter
    sleep_fn(exp)
