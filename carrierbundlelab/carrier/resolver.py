"""Exact-build CarrierLab asset compatibility resolver."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from packaging.version import Version

from carrierbundlelab.errors import BundleCompatibilityError, UnsupportedIOSBuildError
from carrierbundlelab.models import CarrierAsset, CompatibilityDecision, DeviceInfo


class CarrierAssetResolver:
    def __init__(self, config_path: Path | str = "config/carrierlab_compatibility.yaml") -> None:
        self.config_path = Path(config_path)

    def resolve(self, device: DeviceInfo) -> CarrierAsset:
        decision = self.explain(device)
        if not decision.ok or decision.asset is None:
            raise BundleCompatibilityError(decision.reason)
        return decision.asset

    def explain(self, device: DeviceInfo) -> CompatibilityDecision:
        config = self._load()
        build = device.build_version or ""
        hardware = device.hardware_model or ""
        product = device.product_type or ""
        version = device.product_version or ""
        details = [
            f"ProductType = {product or 'unknown'}",
            f"HardwareModel = {hardware or 'unknown'}",
            f"ProductVersion = {version or 'unknown'}",
            f"BuildVersion = {build or 'unknown'}",
        ]
        for ios_family, family in config.items():
            builds = family.get("builds", {})
            if build not in builds:
                continue
            build_entry = builds[build]
            expected_version = str(build_entry.get("product_version", ""))
            if expected_version and version:
                if Version(version) != Version(expected_version):
                    continue
            for group_name, group in build_entry.get("groups", {}).items():
                models = [str(item) for item in group.get("hardware_models", [])]
                products = [str(item) for item in group.get("product_types", [])]
                if hardware not in models or (products and product not in products):
                    continue
                asset_path = Path(group["asset"])
                expected_hash = str(group.get("sha256") or "")
                if expected_hash and asset_path.exists() and _sha256(asset_path) != expected_hash:
                    return CompatibilityDecision(ok=False, reason="CarrierLab asset SHA-256 does not match", details=details)
                asset = CarrierAsset(
                    path=asset_path,
                    ios_family=ios_family,
                    hardware_group=group_name,
                    bundle_name=str(group.get("bundle_identifier") or "com.apple.CarrierLab"),
                    carrier_version=str(group.get("carrier_version") or "") or None,
                )
                return CompatibilityDecision(
                    ok=True,
                    reason=f"Selected {asset.path.name}",
                    asset=asset,
                    details=details + [f"{hardware} belongs to {group_name}", f"build {build} is mapped"],
                )
        if build:
            return CompatibilityDecision(
                ok=False,
                reason=str(UnsupportedIOSBuildError(f"No exact compatible asset for build {build}")),
                details=details,
            )
        return CompatibilityDecision(ok=False, reason="No exact compatible asset", details=details)

    def _load(self) -> dict:
        if not self.config_path.exists():
            raise BundleCompatibilityError(f"Compatibility config not found: {self.config_path}")
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise BundleCompatibilityError("Compatibility config must be a mapping")
        return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
