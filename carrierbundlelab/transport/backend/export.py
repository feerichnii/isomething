"""Fail-closed carrier tree export."""

from __future__ import annotations

from pathlib import Path

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import TransportUnavailableError
from carrierbundlelab.models import ExportResult


def backend_export(session: DeviceSession, destination: Path) -> ExportResult:
    raise TransportUnavailableError(f"udid={session.udid} AirTraffic export backend is not configured")
