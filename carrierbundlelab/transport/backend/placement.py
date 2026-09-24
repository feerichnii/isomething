"""Fail-closed carrier tree placement and verification."""

from __future__ import annotations

from pathlib import Path

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import TransportUnavailableError
from carrierbundlelab.models import InstallResult, TreeManifest, VerificationResult


def backend_install(session: DeviceSession, source: Path) -> InstallResult:
    raise TransportUnavailableError(f"udid={session.udid} AirTraffic install backend is not configured")


def backend_verify(session: DeviceSession, expected: TreeManifest) -> VerificationResult:
    raise TransportUnavailableError(f"udid={session.udid} AirTraffic verify backend is not configured")
