"""CarrierLab asset compatibility resolver."""

from __future__ import annotations

from pathlib import Path

import yaml

from carrierbundlelab.errors import BundleCompatibilityError
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
        version = device.product_version or ""
        hardware = device.hardware_model or ""
        details = [
            f"ProductVersion = {version or 'unknown'}",
            f"HardwareModel = {hardware or 'unknown'}",
        ]
        for ios_family, family in config.items():
            if not _version_in_range(version, str(family.get("min_version", "")), str(family.get("max_version", ""))):
                continue
            for group_name, group in family.get("hardware_groups", {}).items():
                models = [str(x) for x in group.get("hardware_models", [])]
                if hardware in models:
                    asset = CarrierAsset(
                        path=Path(group["asset"]),
                        ios_family=ios_family,
                        hardware_group=group_name,
                    )
                    return CompatibilityDecision(
                        ok=True,
                        reason=f"Selected {asset.path.name}",
                        asset=asset,
                        details=details + [f"{hardware} belongs to {group_name}"],
                    )
        return CompatibilityDecision(
            ok=False,
            reason="No exact CarrierLab asset mapping for this iOS/hardware combination",
            details=details,
        )

    def _load(self) -> dict:
        if not self.config_path.exists():
            raise BundleCompatibilityError(f"Compatibility config not found: {self.config_path}")
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise BundleCompatibilityError("Compatibility config must be a mapping")
        return data


def _version_in_range(version: str, min_version: str, max_version: str) -> bool:
    if not version:
        return False
    parsed = _parse(version)
    return _parse(min_version) <= parsed <= _parse(max_version)


def _parse(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])
