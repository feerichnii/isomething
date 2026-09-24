"""Install orchestration. Transport details stay behind CarrierTransport."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from carrierbundlelab.activation.binding import BindingVerifier
from carrierbundlelab.activation.commcenter import CommCenterMonitor
from carrierbundlelab.activation.rescan import CarrierRescanService, RescanStatus
from carrierbundlelab.carrier.migration import CarrierLabMigrationService
from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import (
    BundleCompatibilityError,
    InstallError,
    ReadbackVerificationError,
    TransportUnavailableError,
)
from carrierbundlelab.logging_config import log_operation
from carrierbundlelab.models import BindingStatus, CarrierAsset, TransactionState
from carrierbundlelab.transaction.backup import BackupManager
from carrierbundlelab.transaction.journal import CarrierTransaction
from carrierbundlelab.transaction.recovery import RecoveryManager

log = logging.getLogger("transaction")


@dataclass
class InstallWorkflowResult:
    transaction_id: str
    status: str
    message: str
    dry_run: bool = False
    binding_status: str | None = None
    lines: list[str] = field(default_factory=list)


class CarrierInstallWorkflow:
    def __init__(
        self,
        device_session: DeviceSession,
        transport,
        resolver,
        backup_manager: BackupManager | None = None,
        commcenter_monitor: CommCenterMonitor | None = None,
        rescan_manager: CarrierRescanService | None = None,
        recovery_manager: RecoveryManager | None = None,
    ) -> None:
        self.device_session = device_session
        self.transport = transport
        self.resolver = resolver
        self.backup_manager = backup_manager or BackupManager(transport)
        self.commcenter_monitor = commcenter_monitor
        self.rescan_manager = rescan_manager or CarrierRescanService()
        self.recovery_manager = recovery_manager or RecoveryManager(transport)
        self.migration = CarrierLabMigrationService()

    def install(
        self,
        source_ipcc: Path,
        dry_run: bool = False,
        expected_bundle: str = "CarrierLab.bundle",
        binding_timeout: int = 0,
    ) -> InstallWorkflowResult:
        source_ipcc = Path(source_ipcc)
        tx = CarrierTransaction.start(self.device_session, "plan" if dry_run else "install_carrierlab")
        try:
            return self._run(tx, source_ipcc, dry_run, expected_bundle, binding_timeout)
        finally:
            tx.release_lock()

    def _run(self, tx: CarrierTransaction, source_ipcc: Path, dry_run: bool, expected_bundle: str, binding_timeout: int) -> InstallWorkflowResult:
        probe = self.transport.probe(self.device_session)
        tx.transition(TransactionState.PROBED, probe.reason or "Transport probed", operation="probe")
        decision = self.resolver.explain(self.device_session.info)
        if not decision.ok or decision.asset is None:
            tx.fail(decision.reason)
            raise BundleCompatibilityError(decision.reason)
        if decision.asset.path.name != source_ipcc.name and decision.asset.path != source_ipcc:
            tx.fail("Supplied IPCC does not match the resolved asset")
            raise BundleCompatibilityError(f"Resolved asset is {decision.asset.path.name}")
        tx.transition(TransactionState.COMPATIBILITY_VERIFIED, decision.reason, operation="compatibility")
        if not probe.available:
            message = probe.reason or "Transport unavailable"
            if dry_run:
                return self._result(tx, "DRY RUN", message, dry_run, lines=[f"Transport: available: no", message, "No changes were made."])
            tx.fail(message)
            raise TransportUnavailableError(message)
        self.backup_manager.create_verified_backup(tx)
        asset = CarrierAsset(
            path=source_ipcc,
            ios_family=decision.asset.ios_family,
            hardware_group=decision.asset.hardware_group,
            bundle_name=decision.asset.bundle_name,
            carrier_version=decision.asset.carrier_version,
        )
        plan = self.migration.build_desired_tree(tx.paths.original_tree, asset, tx.paths.desired_tree)
        tx.transition(TransactionState.DESIRED_TREE_READY, "Desired tree ready", operation="plan")
        lines = _diff_lines(plan.diff)
        if dry_run:
            lines.extend(["Transport: available: yes", "No changes were made."])
            return self._result(tx, "DRY RUN", "No changes were made.", True, lines=lines)
        try:
            tx.transition(TransactionState.INSTALL_STARTED, "Carrier tree placement started", operation="install")
            installed = self.transport.install_tree(self.device_session, plan.desired_tree)
            if not installed.ok:
                tx.fail(installed.message)
                raise InstallError(installed.message)
            tx.transition(TransactionState.INSTALL_FINISHED, installed.message or "Filesystem placement finished", operation="install")
            readback = self.transport.verify_tree(self.device_session, plan.manifest)
            if not readback.ok:
                tx.fail(readback.message)
                raise ReadbackVerificationError(readback.message)
            tx.transition(TransactionState.READBACK_VERIFIED, "Readback manifest matches desired manifest", operation="verify_readback")
            lines.append("Filesystem installation: VERIFIED")
            monitor = self.commcenter_monitor or CommCenterMonitor(udid=self.device_session.udid)
            rescan = self.rescan_manager.trigger(self.device_session, monitor)
            if rescan.status == RescanStatus.FAILED:
                tx.fail(rescan.message)
                raise InstallError(rescan.message)
            tx.transition(TransactionState.RESCAN_REQUESTED, rescan.message, operation="rescan")
            lines.append(f"Carrier binding: WAITING")
            lines.append(rescan.message)
            verification = BindingVerifier(monitor).verify(expected_bundle, timeout=binding_timeout)
            if verification.status == BindingStatus.VERIFIED:
                tx.transition(TransactionState.BINDING_OBSERVED, "Resolved path observed", operation="binding")
                tx.transition(TransactionState.BINDING_VERIFIED, "Override success confirmed", operation="binding")
                tx.transition(TransactionState.COMMITTED, "Backup, readback, and binding verified", operation="commit")
                lines.extend(["Carrier binding: VERIFIED", "Transaction: COMMITTED"])
                return self._result(tx, "COMMITTED", "SUCCESS", False, verification.status.value, lines)
            if verification.status == BindingStatus.OBSERVED:
                tx.transition(TransactionState.BINDING_OBSERVED, "Resolved path observed without override success", operation="binding")
                lines.append("Carrier binding: OBSERVED")
                return self._result(tx, "WAITING", "INSTALLED_NOT_ACTIVATED", False, verification.status.value, lines)
            if verification.status in {BindingStatus.FAILED, BindingStatus.TIMEOUT}:
                tx.fail(verification.status.value)
                lines.append(f"Carrier binding: {verification.status.value}")
                return self._result(tx, tx.state.value, verification.status.value, False, verification.status.value, lines)
            lines.append("Carrier binding: WAITING")
            return self._result(tx, "WAITING", rescan.message, False, verification.status.value, lines)
        except Exception as exc:
            self._mark_recovery(tx, str(exc))
            raise

    def _mark_recovery(self, tx: CarrierTransaction, message: str) -> None:
        backup_verified = any(event.get("state") == TransactionState.BACKUP_VERIFIED.value for event in tx.events)
        if not backup_verified:
            log_operation(log, transaction_id=tx.transaction_id, udid=self.device_session.udid, module="workflow.install", operation="recovery", state_before=tx.state.value, state_after=tx.state.value, result="MANUAL", error=message)
            return
        if TransactionState.RECOVERY_REQUIRED in {TransactionState.RECOVERY_REQUIRED} and tx.state != TransactionState.RECOVERY_REQUIRED:
            allowed = tx.state in {
                TransactionState.INSTALL_STARTED,
                TransactionState.INSTALL_FINISHED,
                TransactionState.READBACK_VERIFIED,
                TransactionState.RESCAN_REQUESTED,
                TransactionState.BINDING_OBSERVED,
                TransactionState.BINDING_VERIFIED,
            }
            if allowed:
                tx.fail(message)

    def _result(self, tx, status, message, dry_run, binding_status=None, lines=None) -> InstallWorkflowResult:
        log_operation(
            log,
            transaction_id=tx.transaction_id,
            udid=self.device_session.udid,
            module="workflow.install",
            operation="install",
            state_before=None,
            state_after=tx.state.value,
            result=status,
        )
        return InstallWorkflowResult(
            transaction_id=tx.transaction_id,
            status=status,
            message=message,
            dry_run=dry_run,
            binding_status=binding_status,
            lines=lines or [],
        )


def _diff_lines(diff) -> list[str]:
    lines = ["Changes:"]
    lines.extend(f"  ADD {path}" for path in diff.added)
    lines.extend(f"  REMOVE {path}" for path in diff.removed)
    lines.extend(f"  MODIFY {path}" for path in diff.modified)
    if diff.is_empty:
        lines.append("  none")
    return lines
