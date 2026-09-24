from pathlib import Path

from carrierbundlelab.activation import BindingVerifier, CommCenterMonitor
from carrierbundlelab.activation.commcenter import parse_line
from carrierbundlelab.models import BindingStatus


def test_parse_resolved_path_json_line():
    event = parse_line('{"message":"Resolved path        : /var/mobile/Library/Carrier Bundles/CarrierLab.bundle"}')
    assert event is not None
    assert event.resolved_path == "CarrierLab.bundle"


def test_binding_verifier_observes_expected_bundle(tmp_path: Path):
    log = tmp_path / "oslog.jsonl"
    log.write_text(
        '{"message":"User data SIM has changed from A to B, re-evaluating state"}\n'
        '{"message":"Resolved path        : /var/mobile/Library/Carrier Bundles/CarrierLab.bundle"}\n'
        '{"message":"OverlayBundle response kOverrideBundleSuccess"}\n',
        encoding="utf-8",
    )
    verification = BindingVerifier(CommCenterMonitor(log)).verify("CarrierLab")
    assert verification.status == BindingStatus.BINDING_VERIFIED
    assert verification.observed_bundle == "CarrierLab.bundle"
