"""Restore and recovery workflows."""

from __future__ import annotations

import json
from pathlib import Path

from carrierbundlelab.carrier.manifest import read_manifest
from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import RecoveryError, RestoreVerificationError
from carrierbundlelab.models import CleanupResult, TransactionState
from carrierbundlelab.transaction.journal import CarrierTransaction, OperationLock, work_root


class RecoveryManager:
    def __init__(self, transport) -> None:
        self.transport = transport

    def restore_latest(self, session: DeviceSession, force: bool = False) -> CleanupResult:
        incomplete = CarrierTransaction.find_incomplete(session.udid)
        if incomplete:
            raise RecoveryError(
                f"Incomplete carrier transaction found: {incomplete[-1].get('transaction_id')}. "
                f"Run carrierlab transaction recover {incomplete[-1].get('transaction_id')}"
            )
        journal = self._latest_verified_backup(session.udid)
        return self.restore_transaction(str(journal), session, force=force)

    def restore_transaction(self, transaction_id: str, session: DeviceSession, force: bool = False) -> CleanupResult:
        tx = CarrierTransaction.open(transaction_id)
        self._check_identity(tx, session, force)
        if tx.state not in {TransactionState.BACKUP_VERIFIED, TransactionState.RECOVERY_REQUIRED}:
            raise RecoveryError(f"Transaction {tx.transaction_id} cannot be restored from {tx.state.value}")
        lock = OperationLock(session.udid)
        lock.acquire(f"{tx.transaction_id}-restore")
        tx._lock = lock
        try:
            tx.session = session
            tx.transition(TransactionState.RESTORE_STARTED, "Restore original carrier tree started", operation="restore")
            manifest = read_manifest(tx.paths.original_manifest)
            result = self.transport.install_tree(session, tx.paths.original_tree)
            if not result.ok:
                tx.fail(result.message)
                raise RecoveryError(result.message)
            verify = self.transport.verify_tree(session, manifest)
            if not verify.ok:
                tx.fail(verify.message)
                raise RestoreVerificationError(verify.message)
            tx.transition(TransactionState.RESTORE_VERIFIED, "Restore readback matches original manifest", operation="restore")
            tx.transition(TransactionState.ROLLED_BACK, "Original carrier tree restored", operation="restore")
            return CleanupResult(ok=True, message=f"restored from {tx.transaction_id}")
        finally:
            tx.release_lock()

    def _check_identity(self, tx: CarrierTransaction, session: DeviceSession, force: bool) -> None:
        raw = json.loads(tx.paths.device_json.read_text(encoding="utf-8"))
        if raw.get("udid") != session.udid:
            raise RecoveryError("Backup UDID does not match connected device")
        for field in ("product_type", "hardware_model", "product_version"):
            expected = raw.get(field)
            actual = getattr(session.info, field)
            if expected and actual and expected != actual:
                raise RecoveryError(f"Backup {field} {expected} does not match device {actual}")
        expected_build = raw.get("build_version")
        actual_build = session.info.build_version
        if expected_build and actual_build and expected_build != actual_build and not force:
            raise RecoveryError("WARNING: backup was created on a different iOS build; pass --force")

    def _latest_verified_backup(self, udid: str | None) -> Path:
        roots = [work_root() / udid] if udid else list(work_root().glob("*"))
        candidates: list[Path] = []
        for root in roots:
            for journal in root.glob("transactions/*/journal.json"):
                data = json.loads(journal.read_text(encoding="utf-8"))
                states = [event.get("state") for event in data.get("events", [])]
                if "BACKUP_VERIFIED" in states and data.get("state") != TransactionState.ROLLED_BACK.value:
                    candidates.append(journal)
        if not candidates:
            raise RecoveryError("No verified backup transaction found")
        return sorted(candidates)[-1]
