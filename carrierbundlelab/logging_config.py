"""Logging setup shared by CLI, GUI, and services."""

from __future__ import annotations

import logging

LOG_CATEGORIES = [
    "device",
    "lockdown",
    "afc",
    "transport",
    "airtraffic",
    "books",
    "carrier-tree",
    "migration",
    "backup",
    "restore",
    "rescan",
    "commcenter",
    "binding",
    "transaction",
]


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    for category in LOG_CATEGORIES:
        logging.getLogger(category).setLevel(level)


def log_operation(
    logger: logging.Logger,
    *,
    transaction_id: str | None,
    udid: str | None,
    module: str,
    operation: str,
    state_before: str | None,
    state_after: str | None,
    result: str,
    error: str | None = None,
) -> None:
    logger.info(
        "tx=%s udid=%s module=%s operation=%s state=%s->%s result=%s error=%s",
        transaction_id or "-",
        udid or "-",
        module,
        operation,
        state_before or "-",
        state_after or "-",
        result,
        error or "-",
    )
