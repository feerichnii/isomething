import plistlib
from pathlib import Path

from carrierbundlelab.carrier.migration import CarrierLabMigrationService
from carrierbundlelab.models import CarrierAsset, DeviceInfo, DeviceSession
from carrierbundlelab.transaction import BackupManager, CarrierTransaction
from carrierbundlelab.transport import MockCarrierTransport


def make_carrier_tree(root: Path) -> Path:
    tree = root / "carrier-tree"
    (tree / "MTS_ru.bundle").mkdir(parents=True)
    (tree / "MTS_ru.bundle" / "Info.plist").write_text("operator")
    return tree


def make_carrierlab_asset(root: Path) -> Path:
    bundle = root / "CarrierLab.bundle"
    bundle.mkdir()
    (bundle / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.apple.CarrierLab"}))
    (bundle / "carrier.plist").write_bytes(plistlib.dumps({"SupportedSIMs": ["00101"]}))
    return bundle


def test_migration_only_adds_carrierlab(tmp_path: Path):
    original = make_carrier_tree(tmp_path)
    asset = make_carrierlab_asset(tmp_path)
    plan = CarrierLabMigrationService().build_desired_tree(
        original,
        CarrierAsset(path=asset, ios_family="ios27", hardware_group="group_d74"),
        tmp_path / "desired",
    )
    assert "CarrierLab.bundle/Info.plist" in plan.diff.added
    assert not plan.diff.modified
    assert (plan.desired_tree / "MTS_ru.bundle" / "Info.plist").read_text() == "operator"


def test_backup_transaction_with_mock_transport(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CARRIERLAB_WORK", str(tmp_path / "work"))
    device_tree = make_carrier_tree(tmp_path)
    session = DeviceSession(info=DeviceInfo(udid="u1", product_type="iPhone14,7", product_version="27.0", hardware_model="D27AP"))
    tx = CarrierTransaction.start(session, "backup")
    BackupManager(MockCarrierTransport(device_tree)).create_verified_backup(tx)
    assert tx.paths.journal.exists()
    assert tx.paths.original_manifest.exists()
