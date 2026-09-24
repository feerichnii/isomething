from pathlib import Path

from carrierbundlelab.carrier.resolver import CarrierAssetResolver
from carrierbundlelab.models import DeviceInfo


CONFIG = """
ios27:
  builds:
    "24A437":
      product_version: "27.0"
      groups:
        d74:
          hardware_models: [D27AP]
          product_types: ["iPhone14,7"]
          asset: assets/CarrierLab.ipcc
          carrier_version: "72.0"
          bundle_identifier: com.apple.CarrierLab
          sha256: ""
"""


def test_exact_build_match(tmp_path: Path):
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    device = DeviceInfo(product_type="iPhone14,7", product_version="27.0", build_version="24A437", hardware_model="D27AP")
    decision = CarrierAssetResolver(cfg).explain(device)
    assert decision.ok
    assert decision.asset
    assert "build 24A437 is mapped" in decision.details


def test_unsupported_hardware(tmp_path: Path):
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    decision = CarrierAssetResolver(cfg).explain(
        DeviceInfo(product_type="iPhone14,7", product_version="27.0", build_version="24A437", hardware_model="UNKNOWN")
    )
    assert not decision.ok


def test_unsupported_build(tmp_path: Path):
    cfg = tmp_path / "compat.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    decision = CarrierAssetResolver(cfg).explain(
        DeviceInfo(product_type="iPhone14,7", product_version="27.0", build_version="24B100", hardware_model="D27AP")
    )
    assert not decision.ok
