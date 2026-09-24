"""Restore and recovery workflows."""

from __future__ import annotations

import json
from pathlib import Path

from carrierbundlelab.carrier.manifest import read_manifest
from carrierbundlelab.errors import RecoveryError
from carrierbundlelab.models import CleanupResult, TransactionState
from carrierbundlelab.transaction.journal import CarrierTransaction, work_root


class RecoveryManager:
    def __init__(self, transport) -> None:
        self.transport = transport

    def restore_latest(self, session) -> CleanupResult:
        journal = self._latest_verified_backup(session.info.udid)
        tx = CarrierTransaction.open(str(journal))
        if tx.session.info.udid != session.info.udid:
            raise RecoveryError("Backup UDID does not match connected device")
        tx.session = session
        tx.transition(TransactionState.ROLLBACK_STARTED, "Restore original carrier tree started")
        manifest = read_manifest(tx.paths.original_manifest)
        result = self.transport.install_tree(session, tx.paths.original_tree)
        if not result.ok:
            tx.fail(result.message)
            raise RecoveryError(result.message)
        verify = self.transport.verify_tree(session, manifest)
        if not verify.ok:
            tx.fail(verify.message)
            raise RecoveryError(verify.message)
        tx.transition(TransactionState.ROLLBACK_VERIFIED, "Original manifest restored")
        return CleanupResult(ok=True, message=f"restored from {tx.transaction_id}")

    def _latest_verified_backup(self, udid: str | None) -> Path:
        root_base = work_root()
        roots = [root_base / (udid or "unknown-device")] if udid else list(root_base.glob("*"))
        candidates: list[Path] = []
        for root in roots:
            for journal in root.glob("transactions/*/journal.json"):
                data = json.loads(journal.read_text(encoding="utf-8"))
                states = [event.get("state") for event in data.get("events", [])]
                if "BACKUP_VERIFIED" in states:
                    candidates.append(journal)
        if not candidates:
            raise RecoveryError("No verified backup transaction found")
        return sorted(candidates)[-1]
