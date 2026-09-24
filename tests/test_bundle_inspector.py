import plistlib
import zipfile
from pathlib import Path

from carrierbundlelab.carrier.inspector import CarrierBundleInspector


def make_bundle(root: Path, name: str = "CarrierLab.bundle") -> Path:
    bundle = root / name
    bundle.mkdir(parents=True)
    (bundle / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "com.apple.CarrierLab",
                "CFBundleVersion": "72.0",
            }
        )
    )
    (bundle / "carrier.plist").write_bytes(plistlib.dumps({"SupportedSIMs": ["00101"]}))
    (bundle / "overrides_D27.plist").write_text("x")
    return bundle


def test_inspects_bundle(tmp_path: Path):
    bundle = make_bundle(tmp_path)
    result = CarrierBundleInspector().inspect(bundle)
    assert result.bundle_name == "CarrierLab.bundle"
    assert result.bundle_identifier == "com.apple.CarrierLab"
    assert result.compatibility["supported_sims"] == ["00101"]
    assert "overrides_D27.plist" in result.overrides


def test_inspects_ipcc_payload(tmp_path: Path):
    payload = tmp_path / "payload_src" / "Payload"
    bundle = make_bundle(payload)
    ipcc = tmp_path / "CarrierLab.ipcc"
    with zipfile.ZipFile(ipcc, "w") as zf:
        for path in bundle.rglob("*"):
            zf.write(path, path.relative_to(tmp_path / "payload_src"))
    result = CarrierBundleInspector().inspect(ipcc)
    assert result.bundle_name == "CarrierLab.bundle"
