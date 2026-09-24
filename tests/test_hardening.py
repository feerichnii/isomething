import hashlib
import json
import plistlib
import zipfile
from pathlib import Path

import pytest

from carrierbundlelab.activation import CommCenterMonitor
from carrierbundlelab.carrier.archive import safe_extract_ipcc
from carrierbundlelab.carrier.migration import CarrierLabMigrationService
from carrierbundlelab.carrier.resolver import CarrierAssetResolver
from carrierbundlelab.device.service import DeviceService
from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import (
    BundleCompatibilityError,
    InvalidTransactionTransition,
    MultipleDevicesError,
    RecoveryError,
    TransactionLockedError,
)
from carrierbundlelab.models import CarrierAsset, DeviceInfo, TransactionState
from carrierbundlelab.transaction.journal import CarrierTransaction, OperationLock
from carrierbundlelab.transaction.recovery import RecoveryManager
from carrierbundlelab.transport.mock import MockCarrierTransport
from carrierbundlelab.workflow import CarrierInstallWorkflow


def device_info(udid: str = "u1", build: str = "24A437") -> DeviceInfo:
    return DeviceInfo(
        udid=udid,
        product_type="iPhone14,7",
        product_version="27.0",
        build_version=build,
        hardware_model="D27AP",
        connection_type="mock",
    )


def session_for(info: DeviceInfo) -> DeviceSession:
    return DeviceSession(udid=info.udid, info=info, runner=lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))


def make_tree(root: Path) -> Path:
    tree = root / "carrier-tree"
    bundle = tree / "MTS_ru.bundle"
    bundle.mkdir(parents=True)
    (bundle / "Info.plist").write_text("operator-bytes")
    return tree


def make_carrierlab(root: Path) -> Path:
    bundle = root / "CarrierLab.bundle"
    bundle.mkdir(parents=True)
    (bundle / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.apple.CarrierLab", "CFBundleVersion": "72.0"}))
    (bundle / "carrier.plist").write_bytes(plistlib.dumps({"SupportedSIMs": ["00101"], "ShowVolteSwitch": True}))
    return bundle


def test_device_session_uses_selected_udid():
    calls: list[tuple[str, ...]] = []

    def runner(*args: str):
        calls.append(args)
        completed = type("Result", (), {"stdout": "{}", "stderr": "", "returncode": 0})()
        return completed

    session = DeviceSession("ABCDEF123456", runner=runner)
    session.get_device_info()
    assert calls
    assert calls[0][-2:] == ("--udid", "ABCDEF123456")


def test_multiple_devices_require_udid():
    service = DeviceService(lister=lambda: [DeviceInfo(udid="a"), DeviceInfo(udid="b")])
    with pytest.raises(MultipleDevicesError):
        service.connect()
    assert service.connect("b").udid == "b"


def test_invalid_transition_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    tx = CarrierTransaction.start(session_for(device_info()), "backup")
    before = tx.paths.journal.read_text(encoding="utf-8")
    with pytest.raises(InvalidTransactionTransition):
        tx.transition(TransactionState.COMMITTED, "nope")
    assert tx.state == TransactionState.DEVICE_CONNECTED
    assert tx.paths.journal.read_text(encoding="utf-8") == before
    assert not tx.paths.journal.with_suffix(".json.tmp").exists()


def test_atomic_journal_and_lock(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    tx = CarrierTransaction.start(session_for(device_info()), "backup")
    data = json.loads(tx.paths.journal.read_text(encoding="utf-8"))
    assert data["udid"] == "u1"
    lock = OperationLock("u1")
    lock.acquire("one")
    with pytest.raises(TransactionLockedError):
        OperationLock("u1").acquire("two")
    lock.release()
    stale = OperationLock("u2")
    stale.path.parent.mkdir(parents=True, exist_ok=True)
    stale.path.write_text(json.dumps({"pid": 2**31 - 1, "transaction_id": "dead", "udid": "u2"}), encoding="utf-8")
    assert stale.is_stale()
    stale.acquire("fresh")
    assert json.loads(stale.path.read_text(encoding="utf-8"))["transaction_id"] == "fresh"
    stale.release()


def test_zip_traversal_rejected(tmp_path: Path):
    ipcc = tmp_path / "bad.ipcc"
    with zipfile.ZipFile(ipcc, "w") as archive:
        archive.writestr("../evil.txt", "nope")
    with pytest.raises(BundleCompatibilityError):
        safe_extract_ipcc(ipcc, tmp_path / "out")


def test_safe_ipcc_extract(tmp_path: Path):
    ipcc = tmp_path / "ok.ipcc"
    with zipfile.ZipFile(ipcc, "w") as archive:
        archive.writestr("Payload/CarrierLab.bundle/Info.plist", "x")
    safe_extract_ipcc(ipcc, tmp_path / "out")
    assert (tmp_path / "out" / "Payload" / "CarrierLab.bundle" / "Info.plist").read_text() == "x"


def test_existing_carrierlab_preserved_and_other_bundles_identical(tmp_path: Path):
    original = make_tree(tmp_path)
    existing = original / "CarrierLab.bundle"
    existing.mkdir()
    (existing / "Info.plist").write_text("old-lab")
    (existing / "carrier.plist").write_bytes(plistlib.dumps({"SupportedSIMs": ["00101"]}))
    before = hashlib.sha256((original / "MTS_ru.bundle" / "Info.plist").read_bytes()).hexdigest()
    asset = make_carrierlab(tmp_path / "asset")
    plan = CarrierLabMigrationService().build_desired_tree(
        original,
        CarrierAsset(path=asset, ios_family="ios27", hardware_group="d74"),
        tmp_path / "desired",
    )
    preserved = list((tmp_path / "desired").glob("CarrierLab-preserved-*.bundle"))
    assert preserved
    assert (preserved[0] / "Info.plist").read_text() == "old-lab"
    assert hashlib.sha256((plan.desired_tree / "MTS_ru.bundle" / "Info.plist").read_bytes()).hexdigest() == before


def test_restore_rejects_different_udid_and_build(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    tree = make_tree(tmp_path)
    info = device_info()
    session = session_for(info)
    tx = CarrierTransaction.start(session, "backup")
    tx.transition(TransactionState.PROBED, "probe")
    tx.transition(TransactionState.COMPATIBILITY_VERIFIED, "compat")
    from carrierbundlelab.transaction.backup import BackupManager

    BackupManager(MockCarrierTransport(tree)).create_verified_backup(tx)
    manager = RecoveryManager(MockCarrierTransport(tree))
    with pytest.raises(RecoveryError, match="UDID"):
        manager.restore_transaction(tx.transaction_id, session_for(device_info("other")), force=False)
    with pytest.raises(RecoveryError, match="different iOS build"):
        manager.restore_transaction(tx.transaction_id, session_for(device_info(build="24B100")), force=False)
    result = manager.restore_transaction(tx.transaction_id, session_for(device_info(build="24B100")), force=True)
    assert result.ok
    assert tx.paths.original_manifest.exists()


def test_dry_run_does_not_modify_device_tree(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    tree = make_tree(tmp_path)
    asset = make_carrierlab(tmp_path / "asset")
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(
        f"""
ios27:
  builds:
    "24A437":
      product_version: "27.0"
      groups:
        d74:
          hardware_models: [D27AP]
          product_types: ["iPhone14,7"]
          asset: "{asset}"
          carrier_version: "72.0"
          bundle_identifier: com.apple.CarrierLab
          sha256: ""
""",
        encoding="utf-8",
    )
    workflow = CarrierInstallWorkflow(session_for(device_info()), MockCarrierTransport(tree), CarrierAssetResolver(cfg))
    result = workflow.install(asset, dry_run=True)
    assert result.status == "DRY RUN"
    assert not (tree / "CarrierLab.bundle").exists()
    assert (tree / "MTS_ru.bundle" / "Info.plist").read_text() == "operator-bytes"


def test_install_commits_only_after_override_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    tree = make_tree(tmp_path)
    asset = make_carrierlab(tmp_path / "asset")
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(
        f"""
ios27:
  builds:
    "24A437":
      product_version: "27.0"
      groups:
        d74:
          hardware_models: [D27AP]
          product_types: ["iPhone14,7"]
          asset: "{asset}"
          carrier_version: "72.0"
          bundle_identifier: com.apple.CarrierLab
          sha256: ""
""",
        encoding="utf-8",
    )
    log = tmp_path / "os.jsonl"
    log.write_text(
        "\n".join(
            [
                '{"process":"CommCenter","message":"re-evaluating carrier bundle for slot 1"}',
                '{"process":"CommCenter","message":"Resolved path: /var/mobile/Library/Carrier Bundles/CarrierLab.bundle"}',
                '{"process":"CommCenter","message":"kOverrideBundleSuccess"}',
            ]
        ),
        encoding="utf-8",
    )
    workflow = CarrierInstallWorkflow(
        session_for(device_info()),
        MockCarrierTransport(tree),
        CarrierAssetResolver(cfg),
        commcenter_monitor=CommCenterMonitor(log),
    )
    result = workflow.install(asset)
    assert result.status == "COMMITTED"
    assert (tree / "CarrierLab.bundle" / "carrier.plist").exists()
    assert (tree / "MTS_ru.bundle" / "Info.plist").read_text() == "operator-bytes"
