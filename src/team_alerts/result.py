"""Outcome of a transport send operation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SendResult:
    """Result of attempting to deliver an alert via a transport."""

    success: bool
    status_code: int | None
    response_text: str
    error_message: str | None = None
