"""Redaction helpers for device identifiers."""

from __future__ import annotations


def mask_identifier(value: str | None) -> str:
    if not value:
        return "unknown"
    if len(value) <= 8:
        return value[:2] + "******"
    return value[:5] + "******" + value[-4:]
