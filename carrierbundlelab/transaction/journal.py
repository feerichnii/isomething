"""Transaction state machine, atomic journal, and per-UDID lock."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import InvalidTransactionTransition, TransactionLockedError
from carrierbundlelab.logging_config import log_operation
from carrierbundlelab.models import DeviceInfo, TransactionState
import logging

log = logging.getLogger("transaction")

INCOMPLETE_STATES = {
    TransactionState.INSTALL_STARTED,
    TransactionState.INSTALL_FINISHED,
    TransactionState.READBACK_VERIFIED,
    TransactionState.RECOVERY_REQUIRED,
    TransactionState.RESTORE_STARTED,
}

LOCKED_OPERATIONS = {"install_carrierlab", "restore", "recover"}

ALLOWED_TRANSITIONS: dict[TransactionState, set[TransactionState]] = {
    TransactionState.NEW: {TransactionState.DEVICE_CONNECTED, TransactionState.FAILED},
    TransactionState.DEVICE_CONNECTED: {TransactionState.PROBED, TransactionState.FAILED},
    TransactionState.PROBED: {TransactionState.COMPATIBILITY_VERIFIED, TransactionState.FAILED},
    TransactionState.COMPATIBILITY_VERIFIED: {TransactionState.BACKUP_STARTED, TransactionState.FAILED},
    TransactionState.BACKUP_STARTED: {TransactionState.BACKUP_VERIFIED, TransactionState.FAILED},
    TransactionState.BACKUP_VERIFIED: {
        TransactionState.DESIRED_TREE_READY,
        TransactionState.RESTORE_STARTED,
        TransactionState.FAILED,
    },
    TransactionState.DESIRED_TREE_READY: {TransactionState.INSTALL_STARTED, TransactionState.FAILED},
    TransactionState.INSTALL_STARTED: {
        TransactionState.INSTALL_FINISHED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.INSTALL_FINISHED: {
        TransactionState.READBACK_VERIFIED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.READBACK_VERIFIED: {
        TransactionState.RESCAN_REQUESTED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.RESCAN_REQUESTED: {
        TransactionState.BINDING_OBSERVED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.BINDING_OBSERVED: {
        TransactionState.BINDING_VERIFIED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.BINDING_VERIFIED: {TransactionState.COMMITTED, TransactionState.RECOVERY_REQUIRED},
    TransactionState.RECOVERY_REQUIRED: {TransactionState.RESTORE_STARTED},
    TransactionState.RESTORE_STARTED: {TransactionState.RESTORE_VERIFIED, TransactionState.FAILED},
    TransactionState.RESTORE_VERIFIED: {TransactionState.ROLLED_BACK},
}


def work_root() -> Path:
    return Path(os.environ.get("CARRIERLAB_WORK", "work"))


@dataclass(frozen=True)
class TransactionPaths:
    root: Path
    journal: Path
    device_json: Path
    sim_json: Path
    original_tree: Path
    original_manifest: Path
    desired_tree: Path
    desired_manifest: Path
    readback_tree: Path
    readback_manifest: Path
    logs: Path


class OperationLock:
    def __init__(self, udid: str) -> None:
        self.udid = udid
        self.path = work_root() / udid / "operation.lock"

    def acquire(self, transaction_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.is_stale():
            self.release()
        payload = json.dumps({"transaction_id": transaction_id, "pid": os.getpid(), "udid": self.udid})
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise TransactionLockedError("another carrier transaction is already active") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def release(self) -> None:
        self.path.unlink(missing_ok=True)

    def is_stale(self) -> bool:
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
        except Exception:
            return True
        if pid == os.getpid():
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        return False


class CarrierTransaction:
    def __init__(self, transaction_id: str, session: DeviceSession, operation: str, paths: TransactionPaths) -> None:
        self.transaction_id = transaction_id
        self.session = session
        self.operation = operation
        self.paths = paths
        self.root = paths.root
        self.state = TransactionState.NEW
        self.events: list[dict] = []
        self._lock: OperationLock | None = None

    @classmethod
    def start(cls, session: DeviceSession, operation: str) -> "CarrierTransaction":
        udid = session.udid
        if operation in LOCKED_OPERATIONS:
            _reject_incomplete(udid)
        txid = f"{_now_stamp()}_{uuid.uuid4().hex[:12]}"
        root = work_root() / udid / "transactions" / txid
        paths = _paths(root)
        paths.logs.mkdir(parents=True, exist_ok=True)
        tx = cls(txid, session, operation, paths)
        if operation in LOCKED_OPERATIONS:
            tx._lock = OperationLock(udid)
            tx._lock.acquire(txid)
        tx._write_static_metadata()
        tx.transition(TransactionState.DEVICE_CONNECTED, "Device connected")
        return tx

    @classmethod
    def list_journals(cls) -> list[str]:
        return [str(path) for path in sorted(work_root().glob("*/transactions/*/journal.json"))]

    @classmethod
    def find_incomplete(cls, udid: str | None = None) -> list[dict]:
        found: list[dict] = []
        for journal in cls.list_journals():
            data = json.loads(Path(journal).read_text(encoding="utf-8"))
            if udid and data.get("udid") != udid:
                continue
            if data.get("state") in {state.value for state in INCOMPLETE_STATES}:
                data["journal_path"] = journal
                found.append(data)
        return found

    @classmethod
    def read_journal(cls, path_or_id: str) -> str:
        return _journal_path(path_or_id).read_text(encoding="utf-8")

    @classmethod
    def open(cls, path_or_id: str) -> "CarrierTransaction":
        path = _journal_path(path_or_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        device_path = path.parent / "device.json"
        info = DeviceInfo(udid=data.get("udid"))
        if device_path.exists():
            raw = json.loads(device_path.read_text(encoding="utf-8"))
            info = DeviceInfo(**{key: raw.get(key) for key in DeviceInfo.__dataclass_fields__})
        session = DeviceSession(udid=info.udid, info=info)
        tx = cls(data["transaction_id"], session, data.get("operation", "recover"), _paths(path.parent))
        tx.state = TransactionState(data.get("state", "NEW"))
        tx.events = data.get("events", [])
        return tx

    def transition(self, state: TransactionState, message: str, operation: str = "transition") -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if state not in allowed:
            raise InvalidTransactionTransition(f"{self.state.value} -> {state.value}")
        before = self.state
        self.state = state
        self.events.append({"ts": _now_iso(), "state": state.value, "message": message})
        try:
            self.write_journal()
        except Exception:
            self.state = before
            self.events.pop()
            raise
        log_operation(
            log,
            transaction_id=self.transaction_id,
            udid=self.session.udid,
            module="transaction",
            operation=operation,
            state_before=before.value,
            state_after=state.value,
            result="OK",
        )

    def fail(self, message: str) -> None:
        backup_verified = any(event.get("state") == TransactionState.BACKUP_VERIFIED.value for event in self.events)
        if backup_verified and TransactionState.RECOVERY_REQUIRED in ALLOWED_TRANSITIONS.get(self.state, set()):
            self.transition(TransactionState.RECOVERY_REQUIRED, message, operation="fail")
            return
        self.transition(TransactionState.FAILED, message, operation="fail")

    def mark_recovery_required(self, message: str) -> None:
        self.transition(TransactionState.RECOVERY_REQUIRED, message, operation="mark-recovery")

    def release_lock(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def write_journal(self) -> None:
        data = {
            "transaction_id": self.transaction_id,
            "udid": self.session.udid,
            "started_at": self.events[0]["ts"] if self.events else _now_iso(),
            "operation": self.operation,
            "state": self.state.value,
            "original_manifest": str(self.paths.original_manifest),
            "desired_manifest": str(self.paths.desired_manifest),
            "events": self.events,
        }
        _atomic_write_json(self.paths.journal, data)

    def _write_static_metadata(self) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.paths.device_json, asdict(self.session.info))
        _atomic_write_json(self.paths.sim_json, [])


def _reject_incomplete(udid: str) -> None:
    incomplete = CarrierTransaction.find_incomplete(udid)
    if incomplete:
        current = incomplete[-1]
        raise TransactionLockedError(
            f"Incomplete carrier transaction found: {current.get('transaction_id')} state={current.get('state')}"
        )


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _paths(root: Path) -> TransactionPaths:
    return TransactionPaths(
        root=root,
        journal=root / "journal.json",
        device_json=root / "device.json",
        sim_json=root / "sim.json",
        original_tree=root / "original" / "carrier-tree",
        original_manifest=root / "original" / "manifest.json",
        desired_tree=root / "desired" / "carrier-tree",
        desired_manifest=root / "desired" / "manifest.json",
        readback_tree=root / "readback" / "carrier-tree",
        readback_manifest=root / "readback" / "manifest.json",
        logs=root / "logs",
    )


def _journal_path(path_or_id: str) -> Path:
    candidate = Path(path_or_id)
    if candidate.exists():
        return candidate
    matches = list(work_root().glob(f"*/transactions/{path_or_id}/journal.json"))
    if not matches:
        matches = list(work_root().glob(f"*/transactions/*{path_or_id}*/journal.json"))
    if not matches:
        raise FileNotFoundError(path_or_id)
    return matches[0]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
