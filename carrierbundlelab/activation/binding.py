"""Binding verification from CommCenter events."""

from __future__ import annotations

from carrierbundlelab.models import BindingStatus, BindingVerification


class BindingVerifier:
    def __init__(self, monitor) -> None:
        self.monitor = monitor

    def verify(self, expected_bundle: str, timeout: int = 0) -> BindingVerification:
        expected = expected_bundle if expected_bundle.endswith(".bundle") else expected_bundle + ".bundle"
        events = self.monitor.wait_for_binding(expected, timeout) if timeout else self.monitor.events()
        observed = None
        status = BindingStatus.INSTALLED_NOT_ACTIVATED
        for event in events:
            if event.resolved_path:
                observed = event.resolved_path.split("/")[-1]
                status = BindingStatus.BINDING_OBSERVED
                if observed.lower() == expected.lower() and event.verification_result in (None, "success"):
                    status = BindingStatus.BINDING_VERIFIED
                    break
        return BindingVerification(status=status, expected_bundle=expected, observed_bundle=observed, events=events)
