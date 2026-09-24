"""Local IPCC and .bundle inspector."""

from __future__ import annotations

import hashlib
import plistlib
import tempfile
from pathlib import Path
from typing import Any

from carrierbundlelab.carrier.archive import safe_extract_ipcc
from carrierbundlelab.carrier.manifest import build_manifest
from carrierbundlelab.errors import BundleCompatibilityError
from carrierbundlelab.models import BundleInspection


class CarrierBundleInspector:
    def inspect(self, source: Path | str) -> BundleInspection:
        source_path = Path(source)
        if source_path.suffix.lower() == ".ipcc":
            with tempfile.TemporaryDirectory(prefix="carrierbundlelab_ipcc_") as tmp:
                extracted = Path(tmp)
                safe_extract_ipcc(source_path, extracted)
                bundle = self._find_payload_bundle(extracted)
                return self._inspect_bundle(bundle, source_path)
        if source_path.suffix.lower() == ".bundle" or source_path.is_dir():
            return self._inspect_bundle(source_path, source_path)
        raise BundleCompatibilityError(f"Unsupported carrier asset: {source_path}")

    def _find_payload_bundle(self, root: Path) -> Path:
        bundles = sorted((root / "Payload").glob("*.bundle"))
        if not bundles:
            bundles = sorted(path for path in root.glob("**/*.bundle") if path.is_dir())
        if len(bundles) != 1:
            raise BundleCompatibilityError(f"Expected exactly one bundle in IPCC, found {len(bundles)}")
        return bundles[0]

    def _inspect_bundle(self, bundle: Path, source: Path) -> BundleInspection:
        if not bundle.exists() or not bundle.is_dir():
            raise BundleCompatibilityError(f"Bundle does not exist: {bundle}")
        info = _read_plist(bundle / "Info.plist")
        carrier = _read_plist(bundle / "carrier.plist")
        overrides = sorted(path.name for path in bundle.glob("overrides*"))
        manifest = build_manifest(bundle)
        details = _bundle_details(bundle, info, carrier, manifest)
        return BundleInspection(
            source=source,
            bundle_name=bundle.name,
            bundle_identifier=info.get("CFBundleIdentifier"),
            carrier_version=str(info.get("CFBundleVersion") or info.get("CFBundleShortVersionString") or "") or None,
            payload_hash=details["sha256"],
            compatibility={
                "supported_sims": carrier.get("SupportedSIMs", []),
                "device_overrides": overrides,
                "supported_devices": info.get("SupportedDevices", carrier.get("SupportedDevices", [])),
                "supported_devices_exact_match": info.get("SupportedDevicesExactMatch"),
            },
            overrides=overrides,
            manifest=manifest,
            details=details,
        )


def format_inspection(inspection: BundleInspection) -> str:
    details = inspection.details
    ims = details.get("ims", {})
    five_g = details.get("five_g", {})
    lines = [
        f"Bundle name: {inspection.bundle_name}",
        f"CFBundleIdentifier: {inspection.bundle_identifier or 'unknown'}",
        f"CFBundleVersion: {inspection.carrier_version or 'unknown'}",
        f"Carrier version: {details.get('carrier_name') or inspection.carrier_version or 'unknown'}",
        "",
        "SupportedSIMs",
        *[f"  {sim}" for sim in inspection.compatibility.get("supported_sims", [])],
        "",
        f"SupportedDevices: {inspection.compatibility.get('supported_devices') or 'unknown'}",
        f"SupportedDevicesExactMatch: {inspection.compatibility.get('supported_devices_exact_match') or 'unknown'}",
        "",
        "Hardware overrides",
        *[f"  {name}" for name in inspection.overrides],
        "",
        "IMS",
        f"  VoLTE: {ims.get('volte', 'unknown')}",
        f"  VoWiFi: {ims.get('vowifi', 'unknown')}",
        f"  SMS over IMS: {ims.get('sms', 'unknown')}",
        f"  VoNR: {ims.get('vonr', 'unknown')}",
        "",
        "5G",
        f"  NSA: {five_g.get('nsa', 'unknown')}",
        f"  SA: {five_g.get('sa', 'unknown')}",
        f"  Enable5GStandaloneByDefault: {five_g.get('sa_default', 'unknown')}",
        "",
        "APN",
        f"  profiles: {details.get('apn_count', 'unknown')}",
        "",
        "Integrity",
        f"  file count: {details.get('file_count', 0)}",
        f"  total size: {details.get('total_size', 0)}",
        f"  SHA-256: {details.get('sha256')}",
    ]
    return "\n".join(lines)


def _bundle_details(bundle: Path, info: dict[str, Any], carrier: dict[str, Any], manifest) -> dict[str, Any]:
    ims = carrier.get("IMSConfig", {}) if isinstance(carrier.get("IMSConfig"), dict) else {}
    voice = ims.get("Voice", {}) if isinstance(ims.get("Voice"), dict) else {}
    sms = ims.get("SMS", {}) if isinstance(ims.get("SMS"), dict) else {}
    apns = carrier.get("apns", [])
    digest = hashlib.sha256()
    total = 0
    for rel, entry in sorted(manifest.files.items()):
        digest.update(rel.encode("utf-8"))
        digest.update((entry.sha256 or "").encode("ascii"))
        total += entry.size or 0
    return {
        "carrier_name": carrier.get("CarrierName") or info.get("CFBundleName"),
        "ims": {
            "volte": carrier.get("ShowVolteSwitch", voice.get("EnableVoLTE")),
            "vowifi": carrier.get("ShowVoWiFiSwitch", carrier.get("SupportsVoWiFi")),
            "sms": sms.get("SupportedDomains", carrier.get("SupportsIMSSignalingIndication")),
            "vonr": voice.get("EnableVoNRByDefault", carrier.get("SupportsVoNR")),
        },
        "five_g": {
            "nsa": carrier.get("SupportsNRNSAInboundRoaming", carrier.get("Show5GSwitch")),
            "sa": carrier.get("Show5GStandaloneSwitch", carrier.get("Enable5GStandaloneByDefault")),
            "sa_default": carrier.get("Enable5GStandaloneByDefault"),
        },
        "apn_count": len(apns) if isinstance(apns, list) else "unknown",
        "file_count": len(manifest.files),
        "total_size": total,
        "sha256": digest.hexdigest(),
    }


def _read_plist(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = plistlib.load(handle)
    return data if isinstance(data, dict) else {}
