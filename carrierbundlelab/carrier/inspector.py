"""Local IPCC and .bundle inspector."""

from __future__ import annotations

import hashlib
import plistlib
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from carrierbundlelab.carrier.manifest import build_manifest
from carrierbundlelab.errors import BundleCompatibilityError
from carrierbundlelab.models import BundleInspection


class CarrierBundleInspector:
    def inspect(self, source: Path | str) -> BundleInspection:
        source_path = Path(source)
        if source_path.suffix.lower() == ".ipcc":
            with tempfile.TemporaryDirectory(prefix="carrierbundlelab_ipcc_") as tmp:
                extracted = Path(tmp)
                with zipfile.ZipFile(source_path) as zf:
                    zf.extractall(extracted)
                bundle = self._find_payload_bundle(extracted)
                return self._inspect_bundle(bundle, source_path)
        if source_path.suffix.lower() == ".bundle" or source_path.is_dir():
            return self._inspect_bundle(source_path, source_path)
        raise BundleCompatibilityError(f"Unsupported carrier asset: {source_path}")

    def _find_payload_bundle(self, root: Path) -> Path:
        bundles = sorted((root / "Payload").glob("*.bundle"))
        if not bundles:
            bundles = sorted(root.glob("**/*.bundle"))
        if len(bundles) != 1:
            raise BundleCompatibilityError(f"Expected exactly one bundle in IPCC, found {len(bundles)}")
        return bundles[0]

    def _inspect_bundle(self, bundle: Path, source: Path) -> BundleInspection:
        if not bundle.exists() or not bundle.is_dir():
            raise BundleCompatibilityError(f"Bundle does not exist: {bundle}")
        info = _read_plist(bundle / "Info.plist")
        carrier = _read_plist(bundle / "carrier.plist")
        overrides = sorted(p.name for p in bundle.glob("overrides*"))
        manifest = build_manifest(bundle)
        payload_hash = self._payload_hash(manifest)
        compatibility = {
            "supported_sims": carrier.get("SupportedSIMs", []),
            "device_overrides": overrides,
        }
        return BundleInspection(
            source=source,
            bundle_name=bundle.name,
            bundle_identifier=info.get("CFBundleIdentifier"),
            carrier_version=str(info.get("CFBundleVersion") or info.get("CFBundleShortVersionString") or "")
            or None,
            payload_hash=payload_hash,
            compatibility=compatibility,
            overrides=overrides,
            manifest=manifest,
        )

    @staticmethod
    def _payload_hash(manifest) -> str:
        h = hashlib.sha256()
        for rel, entry in sorted(manifest.files.items()):
            h.update(rel.encode("utf-8"))
            h.update((entry.sha256 or "").encode("ascii"))
        return h.hexdigest()


def _read_plist(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    return data if isinstance(data, dict) else {}
