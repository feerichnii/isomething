from pathlib import Path

from carrierbundlelab.carrier.resolver import CarrierAssetResolver
from carrierbundlelab.models import DeviceInfo


def test_resolver_explains_matching_device(tmp_path: Path):
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(
        """
ios27:
  min_version: "27.0"
  max_version: "27.99"
  hardware_groups:
    group_d74:
      hardware_models: [D27AP]
      asset: assets/CarrierLab.ipcc
""",
        encoding="utf-8",
    )
    decision = CarrierAssetResolver(cfg).explain(DeviceInfo(product_version="27.0", hardware_model="D27AP"))
    assert decision.ok
    assert decision.asset
    assert "D27AP belongs to group_d74" in decision.details


def test_resolver_blocks_unknown_device(tmp_path: Path):
    cfg = tmp_path / "compat.yaml"
    cfg.write_text("ios27: {min_version: '27.0', max_version: '27.99', hardware_groups: {}}\n", encoding="utf-8")
    decision = CarrierAssetResolver(cfg).explain(DeviceInfo(product_version="27.0", hardware_model="UNKNOWN"))
    assert not decision.ok
