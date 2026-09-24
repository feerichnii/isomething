"""Transaction state machine and on-disk journal."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from carrierbundlelab.models import DeviceSession, TransactionState


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


class CarrierTransaction:
    def __init__(self, transaction_id: str, session: DeviceSession, operation: str, paths: TransactionPaths) -> None:
        self.transaction_id = transaction_id
        self.session = session
        self.operation = operation
        self.paths = paths
        self.root = paths.root
        self.state = TransactionState.NEW
        self.events: list[dict] = []

    @classmethod
    def start(cls, session: DeviceSession, operation: str) -> "CarrierTransaction":
        udid = session.info.udid or "unknown-device"
        txid = f"{_now_stamp()}_{uuid.uuid4().hex[:12]}"
        root = work_root() / udid / "transactions" / txid
        paths = _paths(root)
        paths.logs.mkdir(parents=True, exist_ok=True)
        tx = cls(txid, session, operation, paths)
        tx._write_static_metadata()
        tx.transition(TransactionState.DEVICE_CONNECTED, "Device connected")
        return tx

    @classmethod
    def list_journals(cls) -> list[str]:
        return [str(p) for p in sorted(work_root().glob("*/transactions/*/journal.json"))]

    @classmethod
    def read_journal(cls, path_or_id: str) -> str:
        path = _journal_path(path_or_id)
        return path.read_text(encoding="utf-8")

    @classmethod
    def open(cls, path_or_id: str) -> "CarrierTransaction":
        path = _journal_path(path_or_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        from carrierbundlelab.models import DeviceInfo

        session = DeviceSession(info=DeviceInfo(udid=data.get("udid")))
        tx = cls(data["transaction_id"], session, data.get("operation", "recover"), _paths(path.parent))
        tx.state = TransactionState(data.get("state", "NEW"))
        tx.events = data.get("events", [])
        return tx

    def transition(self, state: TransactionState, message: str) -> None:
        self.state = state
        self.events.append({"ts": _now_iso(), "state": state.value, "message": message})
        self.write_journal()

    def fail(self, message: str) -> None:
        self.transition(TransactionState.FAILED, message)
        self.transition(TransactionState.ROLLBACK_REQUIRED, "Rollback required")

    def mark_recovery_required(self, message: str) -> None:
        self.transition(TransactionState.ROLLBACK_REQUIRED, message)

    def install(self, plan, transport) -> None:
        from carrierbundlelab.errors import InstallError, ReadbackVerificationError

        self.transition(TransactionState.INSTALL_STARTED, "Carrier tree placement started")
        result = transport.install_tree(self.session, plan.desired_tree)
        if not result.ok:
            self.fail(result.message)
            raise InstallError(result.message)
        self.transition(TransactionState.INSTALL_FINISHED, result.message or "Carrier tree placement finished")
        verification = transport.verify_tree(self.session, plan.manifest)
        if not verification.ok:
            self.fail(verification.message)
            raise ReadbackVerificationError(verification.message)
        self.transition(TransactionState.READBACK_VERIFIED, "Readback manifest matches desired manifest")

    def write_journal(self) -> None:
        data = {
            "transaction_id": self.transaction_id,
            "udid": self.session.info.udid,
            "started_at": self.events[0]["ts"] if self.events else _now_iso(),
            "operation": self.operation,
            "state": self.state.value,
            "original_manifest": str(self.paths.original_manifest),
            "desired_manifest": str(self.paths.desired_manifest),
            "events": self.events,
        }
        self.paths.journal.parent.mkdir(parents=True, exist_ok=True)
        self.paths.journal.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_static_metadata(self) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.device_json.write_text(json.dumps(asdict(self.session.info), indent=2), encoding="utf-8")
        self.paths.sim_json.write_text("[]\n", encoding="utf-8")


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
    p = Path(path_or_id)
    if p.exists():
        return p
    matches = list(work_root().glob(f"*/transactions/{path_or_id}/journal.json"))
    if not matches:
        raise FileNotFoundError(path_or_id)
    return matches[0]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
