"""CarrierLab desired tree construction."""

from __future__ import annotations

import plistlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from carrierbundlelab.carrier.archive import safe_extract_ipcc
from carrierbundlelab.carrier.manifest import build_manifest, compare_manifests, write_manifest
from carrierbundlelab.errors import MigrationError
from carrierbundlelab.models import CarrierAsset, MigrationPlan


class CarrierLabMigrationService:
    def build_desired_tree(
        self,
        original_tree: Path,
        carrierlab: CarrierAsset,
        destination: Path | None = None,
        strategy: str = "preserve-and-replace",
    ) -> MigrationPlan:
        if strategy not in {"replace", "preserve-and-replace", "abort"}:
            raise MigrationError(f"Unknown CarrierLab strategy: {strategy}")
        original_tree = Path(original_tree)
        destination = Path(destination) if destination else original_tree.parent.parent / "desired" / "carrier-tree"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(original_tree, destination, symlinks=True)

        with tempfile.TemporaryDirectory(prefix="carrierlab_asset_") as tmp:
            asset_bundle = self._materialize_asset(Path(carrierlab.path), Path(tmp))
            validate_carrierlab_bundle(asset_bundle)
            target = destination / "CarrierLab.bundle"
            if target.exists():
                if strategy == "abort":
                    raise MigrationError("CarrierLab already exists and strategy=abort")
                if strategy == "preserve-and-replace":
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    preserved = destination / f"CarrierLab-preserved-{stamp}.bundle"
                    shutil.move(str(target), str(preserved))
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(asset_bundle, target, symlinks=True)

        before = build_manifest(original_tree)
        after = build_manifest(destination)
        diff = compare_manifests(before, after)
        unexpected = [
            path
            for path in (diff.added + diff.removed + diff.modified + diff.symlink_target_changed)
            if not _is_allowed_path(path)
        ]
        if unexpected:
            raise MigrationError(f"Unexpected migration diff outside CarrierLab scope: {unexpected[:5]}")
        write_manifest(after, destination.parent / "manifest.json")
        return MigrationPlan(
            original_tree=original_tree,
            desired_tree=destination,
            asset=carrierlab,
            manifest=after,
            diff=diff,
            strategy=strategy,
            allowed_paths={path for path in (diff.added + diff.removed + diff.modified) if _is_allowed_path(path)},
        )

    def _materialize_asset(self, source: Path, tmp: Path) -> Path:
        if source.suffix.lower() == ".ipcc":
            safe_extract_ipcc(source, tmp)
            bundles = sorted((tmp / "Payload").glob("*.bundle")) or sorted(path for path in tmp.glob("**/*.bundle") if path.is_dir())
            if len(bundles) != 1:
                raise MigrationError(f"Expected exactly one bundle in IPCC, found {len(bundles)}")
            return bundles[0]
        if source.is_dir() and source.name == "CarrierLab.bundle":
            return source
        raise MigrationError(f"Unsupported CarrierLab asset: {source}")


def validate_carrierlab_bundle(bundle: Path) -> None:
    if bundle.name != "CarrierLab.bundle":
        raise MigrationError(f"Expected CarrierLab.bundle, got {bundle.name}")
    info_path = bundle / "Info.plist"
    carrier_path = bundle / "carrier.plist"
    if not info_path.exists() or not carrier_path.exists():
        raise MigrationError("CarrierLab.bundle requires Info.plist and carrier.plist")
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    with carrier_path.open("rb") as handle:
        carrier = plistlib.load(handle)
    if info.get("CFBundleIdentifier") != "com.apple.CarrierLab":
        raise MigrationError("CFBundleIdentifier must be com.apple.CarrierLab")
    sims = carrier.get("SupportedSIMs")
    if not isinstance(sims, list):
        raise MigrationError("SupportedSIMs must be a list")


def _is_allowed_path(path: str) -> bool:
    return path.startswith("CarrierLab.bundle") or path.startswith("CarrierLab-preserved-")
