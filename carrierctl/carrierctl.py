#!/usr/bin/env python3
"""Compatibility wrapper for the new service-backed carrierlab CLI."""

from __future__ import annotations

import sys

from carrierbundlelab.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
