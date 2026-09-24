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
