"""Filesystem-backed mock transport for workflow tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from carrierbundlelab.carrier.manifest import build_manifest, compare_manifests
from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import TransportUnavailableError
from carrierbundlelab.models import (
    CleanupResult,
    ExportResult,
    InstallResult,
    TransportProbe,
    TreeManifest,
    VerificationResult,
)


class MockCarrierTransport:
    def __init__(
        self,
        device_tree: Path,
        fail_install: bool = False,
        fail_export: bool = False,
        fail_verify: bool = False,
        partial_install: bool = False,
        fail_connection: bool = False,
    ) -> None:
        self.device_tree = Path(device_tree)
        self.fail_install = fail_install
        self.fail_export = fail_export
        self.fail_verify = fail_verify
        self.partial_install = partial_install
        self.fail_connection = fail_connection

    def probe(self, session: DeviceSession) -> TransportProbe:
        available = self.device_tree.exists() and not self.fail_connection
        return TransportProbe(
            available=available,
            backend="mock",
            sync_service_available=not self.fail_connection,
            staging_available=not self.fail_connection,
            canary_successful=available,
            reason=None if available else "connection failure",
        )

    def export_tree(self, session: DeviceSession, destination: Path) -> ExportResult:
        self._require_connection()
        if self.fail_export:
            return ExportResult(ok=False, path=destination)
        destination = Path(destination)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self.device_tree, destination, symlinks=True)
        return ExportResult(ok=True, path=destination, manifest=build_manifest(destination, device=session.info))

    def install_tree(self, session: DeviceSession, source: Path) -> InstallResult:
        self._require_connection()
        if self.fail_install:
            return InstallResult(ok=False, message="mock install failure")
        if self.device_tree.exists():
            shutil.rmtree(self.device_tree)
        self.device_tree.mkdir(parents=True, exist_ok=True)
        if self.partial_install:
            first = next(Path(source).rglob("*"))
            if first.is_file():
                target = self.device_tree / first.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(first, target)
            return InstallResult(ok=True, message="partial install")
        shutil.copytree(source, self.device_tree, dirs_exist_ok=True)
        return InstallResult(ok=True, message="mock install complete")

    def verify_tree(self, session: DeviceSession, expected: TreeManifest) -> VerificationResult:
        self._require_connection()
        actual = build_manifest(self.device_tree, device=session.info)
        diff = compare_manifests(expected, actual)
        if self.fail_verify:
            return VerificationResult(ok=False, message="verification failure", diff=diff)
        return VerificationResult(ok=diff.is_empty, message="verified" if diff.is_empty else "manifest mismatch", diff=diff)

    def cleanup(self, session: DeviceSession) -> CleanupResult:
        return CleanupResult(ok=True, message="mock cleanup complete")

    def _require_connection(self) -> None:
        if self.fail_connection:
            raise TransportUnavailableError("mock connection failure")
