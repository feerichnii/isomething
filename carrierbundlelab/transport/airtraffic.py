"""Thin AirTraffic adapter. Backend modules own probe/export/placement/cleanup."""

from __future__ import annotations

from pathlib import Path

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.models import CleanupResult, ExportResult, InstallResult, TransportProbe, TreeManifest, VerificationResult
from carrierbundlelab.transport.backend.cleanup import backend_cleanup
from carrierbundlelab.transport.backend.export import backend_export
from carrierbundlelab.transport.backend.placement import backend_install, backend_verify
from carrierbundlelab.transport.backend.probe import backend_probe


class AirTrafficCarrierTransport:
    def probe(self, session: DeviceSession) -> TransportProbe:
        return backend_probe(session)

    def export_tree(self, session: DeviceSession, destination: Path) -> ExportResult:
        return backend_export(session, destination)

    def install_tree(self, session: DeviceSession, source: Path) -> InstallResult:
        return backend_install(session, source)

    def verify_tree(self, session: DeviceSession, expected: TreeManifest) -> VerificationResult:
        return backend_verify(session, expected)

    def cleanup(self, session: DeviceSession) -> CleanupResult:
        return backend_cleanup(session)
