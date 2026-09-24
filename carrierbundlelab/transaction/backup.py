"""Verified carrier tree backup."""

from __future__ import annotations

from carrierbundlelab.carrier.manifest import build_manifest, compare_manifests, write_manifest
from carrierbundlelab.errors import BackupError, BackupVerificationError
from carrierbundlelab.models import TransactionState


class BackupManager:
    def __init__(self, transport) -> None:
        self.transport = transport

    def create_verified_backup(self, tx) -> None:
        if tx.state != TransactionState.COMPATIBILITY_VERIFIED:
            raise BackupError(f"Backup requires COMPATIBILITY_VERIFIED, got {tx.state.value}")
        probe = self.transport.probe(tx.session)
        if not probe.available:
            tx.fail(probe.reason or "Transport probe failed")
            raise BackupError(probe.reason or "Transport probe failed")
        tx.transition(TransactionState.BACKUP_STARTED, "Carrier tree export started", operation="backup")
        first = self.transport.export_tree(tx.session, tx.paths.original_tree)
        if not first.ok or first.manifest is None:
            tx.fail("Carrier tree export failed")
            raise BackupError("Carrier tree export failed")
        manifest = build_manifest(first.path, device=tx.session.info)
        write_manifest(manifest, tx.paths.original_manifest)
        second = self.transport.export_tree(tx.session, tx.paths.root / "original" / "carrier-tree-second-read")
        if not second.ok or second.manifest is None:
            tx.fail("Carrier tree second-read verification failed")
            raise BackupVerificationError("Carrier tree second-read verification failed")
        second_manifest = build_manifest(second.path, device=tx.session.info)
        diff = compare_manifests(manifest, second_manifest)
        if not diff.is_empty:
            tx.fail("Carrier tree backup verification mismatch")
            raise BackupVerificationError("Carrier tree backup verification mismatch")
        tx.transition(TransactionState.BACKUP_VERIFIED, "Backup manifest verified with second read", operation="backup")
