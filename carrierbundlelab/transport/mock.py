"""Filesystem-backed mock transport for tests and dry-run orchestration."""

from __future__ import annotations

import shutil
from pathlib import Path

from carrierbundlelab.carrier.manifest import build_manifest, compare_manifests
from carrierbundlelab.models import (
    CleanupResult,
    DeviceSession,
    ExportResult,
    InstallResult,
    TransportProbe,
    TreeManifest,
    VerificationResult,
)


class MockCarrierTransport:
    def __init__(self, device_tree: Path, fail_install: bool = False) -> None:
        self.device_tree = Path(device_tree)
        self.fail_install = fail_install

    def probe(self, session: DeviceSession) -> TransportProbe:
        checks = {
            "usb_connection_available": bool(session.info.udid or session.info.product_type),
            "lockdown_available": True,
            "afc_available": True,
            "required_sync_service_available": True,
            "books_staging_area_available": True,
            "transport_canary_successful": self.device_tree.exists(),
            "no_unfinished_transaction_exists": True,
            "local_free_space_sufficient": True,
            "compatible_ios_build": True,
        }
        return TransportProbe(ok=all(checks.values()), checks=checks)

    def export_tree(self, session: DeviceSession, destination: Path) -> ExportResult:
        destination = Path(destination)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self.device_tree, destination, symlinks=True)
        manifest = build_manifest(destination)
        return ExportResult(ok=True, path=destination, manifest=manifest)

    def install_tree(self, session: DeviceSession, source: Path) -> InstallResult:
        if self.fail_install:
            return InstallResult(ok=False, message="mock install failure")
        if self.device_tree.exists():
            shutil.rmtree(self.device_tree)
        shutil.copytree(source, self.device_tree, symlinks=True)
        return InstallResult(ok=True, message="mock install complete")

    def verify_tree(self, session: DeviceSession, expected: TreeManifest) -> VerificationResult:
        actual = build_manifest(self.device_tree)
        diff = compare_manifests(expected, actual)
        return VerificationResult(ok=diff.is_empty, message="verified" if diff.is_empty else "manifest mismatch", diff=diff)

    def cleanup(self, session: DeviceSession) -> CleanupResult:
        return CleanupResult(ok=True, message="mock cleanup complete")
