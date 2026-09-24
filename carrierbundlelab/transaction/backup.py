"""Verified carrier tree backup."""

from __future__ import annotations

from carrierbundlelab.carrier.manifest import compare_manifests, write_manifest
from carrierbundlelab.errors import BackupError
from carrierbundlelab.models import TransactionState


class BackupManager:
    def __init__(self, transport) -> None:
        self.transport = transport

    def create_verified_backup(self, tx) -> None:
        tx.transition(TransactionState.PROBED, "Transport probe started")
        probe = self.transport.probe(tx.session)
        if not probe.ok:
            tx.fail("; ".join(probe.messages) or "Transport probe failed")
            raise BackupError("Transport probe failed")
        tx.transition(TransactionState.BACKUP_STARTED, "Carrier tree export started")
        first = self.transport.export_tree(tx.session, tx.paths.original_tree)
        if not first.ok or first.manifest is None:
            tx.fail("Carrier tree export failed")
            raise BackupError("Carrier tree export failed")
        write_manifest(first.manifest, tx.paths.original_manifest)
        second = self.transport.export_tree(tx.session, tx.paths.root / "original" / "carrier-tree-second-read")
        if not second.ok or second.manifest is None:
            tx.fail("Carrier tree second-read verification failed")
            raise BackupError("Carrier tree second-read verification failed")
        diff = compare_manifests(first.manifest, second.manifest)
        if not diff.is_empty:
            tx.fail("Carrier tree backup verification mismatch")
            raise BackupError("Carrier tree backup verification mismatch")
        tx.transition(TransactionState.BACKUP_VERIFIED, "Backup manifest verified with second read")
