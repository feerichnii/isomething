"""CarrierLab desired tree construction."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from carrierbundlelab.carrier.inspector import CarrierBundleInspector
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

        inspector = CarrierBundleInspector()
        with tempfile.TemporaryDirectory(prefix="carrierlab_asset_") as tmp:
            asset_bundle = self._materialize_asset(Path(carrierlab.path), Path(tmp))
            target = destination / asset_bundle.name
            if target.exists():
                if strategy == "abort":
                    raise MigrationError("CarrierLab already exists and strategy=abort")
                if strategy == "preserve-and-replace":
                    backup = destination / f"{asset_bundle.name}.previous"
                    if backup.exists():
                        shutil.rmtree(backup)
                    shutil.move(str(target), str(backup))
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(asset_bundle, target, symlinks=True)

        before = build_manifest(original_tree)
        after = build_manifest(destination)
        diff = compare_manifests(before, after)
        allowed = _allowed_carrierlab_paths(diff)
        unexpected = [
            p for p in (diff.added + diff.removed + diff.modified + diff.symlink_target_changed)
            if not _is_allowed_path(p)
        ]
        if unexpected:
            raise MigrationError(f"Unexpected migration diff outside CarrierLab scope: {unexpected[:5]}")
        manifest_path = destination.parent / "manifest.json"
        write_manifest(after, manifest_path)
        return MigrationPlan(
            original_tree=original_tree,
            desired_tree=destination,
            asset=carrierlab,
            manifest=after,
            diff=diff,
            strategy=strategy,
            allowed_paths=allowed,
        )

    def _materialize_asset(self, source: Path, tmp: Path) -> Path:
        if source.suffix.lower() == ".ipcc":
            import zipfile

            with zipfile.ZipFile(source) as zf:
                zf.extractall(tmp)
            bundles = sorted((tmp / "Payload").glob("*.bundle")) or sorted(tmp.glob("**/*.bundle"))
            if len(bundles) != 1:
                raise MigrationError(f"Expected exactly one bundle in IPCC, found {len(bundles)}")
            return bundles[0]
        if source.is_dir() and source.suffix == ".bundle":
            return source
        raise MigrationError(f"Unsupported CarrierLab asset: {source}")


def _is_allowed_path(path: str) -> bool:
    return path.startswith("CarrierLab.bundle") or path.startswith("CarrierLab.bundle.previous")


def _allowed_carrierlab_paths(diff) -> set[str]:
    return {
        p for p in (diff.added + diff.removed + diff.modified + diff.symlink_target_changed)
        if _is_allowed_path(p)
    }
