"""Constrained AirTraffic carrier transport adapter.

This adapter intentionally does not expose a generic file writer. Until a verified
project-specific AirTraffic backend is plugged in, modifying methods fail closed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from carrierbundlelab.errors import TransportUnavailableError
from carrierbundlelab.models import (
    CleanupResult,
    DeviceSession,
    ExportResult,
    InstallResult,
    TransportProbe,
    TreeManifest,
    VerificationResult,
)


class AirTrafficCarrierTransport:
    def probe(self, session: DeviceSession) -> TransportProbe:
        checks = {
            "usb_connection_available": bool(session.info.udid or session.info.product_type),
            "lockdown_available": shutil.which("pymobiledevice3") is not None,
            "afc_available": shutil.which("pymobiledevice3") is not None,
            "required_sync_service_available": False,
            "books_staging_area_available": False,
            "transport_canary_successful": False,
            "no_unfinished_transaction_exists": True,
            "local_free_space_sufficient": True,
            "compatible_ios_build": bool(session.info.product_version),
        }
        return TransportProbe(
            ok=False,
            checks=checks,
            messages=[
                "AirTraffic backend is not configured in this repository yet.",
                "Install/export fail closed to avoid exposing an arbitrary protected-path writer.",
            ],
        )

    def export_tree(self, session: DeviceSession, destination: Path) -> ExportResult:
        raise TransportUnavailableError("AirTraffic export backend is not configured")

    def install_tree(self, session: DeviceSession, source: Path) -> InstallResult:
        raise TransportUnavailableError("AirTraffic install backend is not configured")

    def verify_tree(self, session: DeviceSession, expected: TreeManifest) -> VerificationResult:
        raise TransportUnavailableError("AirTraffic verify backend is not configured")

    def cleanup(self, session: DeviceSession) -> CleanupResult:
        return CleanupResult(ok=True, message="no AirTraffic staging was created")
