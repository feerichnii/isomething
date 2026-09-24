"""Carrier transport protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.models import (
    CleanupResult,
    ExportResult,
    InstallResult,
    TransportProbe,
    TreeManifest,
    VerificationResult,
)


class CarrierTransport(Protocol):
    def probe(self, session: DeviceSession) -> TransportProbe: ...

    def export_tree(self, session: DeviceSession, destination: Path) -> ExportResult: ...

    def install_tree(self, session: DeviceSession, source: Path) -> InstallResult: ...

    def verify_tree(self, session: DeviceSession, expected: TreeManifest) -> VerificationResult: ...

    def cleanup(self, session: DeviceSession) -> CleanupResult: ...
