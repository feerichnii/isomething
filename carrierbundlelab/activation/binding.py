"""Binding verification from correlated CommCenter attempts."""

from __future__ import annotations

from carrierbundlelab.activation.commcenter import BindingAttempt
from carrierbundlelab.models import BindingStatus, BindingVerification


class BindingVerifier:
    def __init__(self, monitor) -> None:
        self.monitor = monitor

    def verify(self, expected_bundle: str, timeout: int = 0) -> BindingVerification:
        expected = expected_bundle if expected_bundle.endswith(".bundle") else expected_bundle + ".bundle"
        attempts = self.monitor.wait_for_binding(expected, timeout) if timeout else self.monitor.attempts()
        status, observed = _status_for(attempts, expected, timed_out=bool(timeout) and not _verified(attempts, expected))
        return BindingVerification(status=status, expected_bundle=expected, observed_bundle=observed, events=[])


def _status_for(attempts: list[BindingAttempt], expected: str, timed_out: bool) -> tuple[BindingStatus, str | None]:
    if not attempts:
        return (BindingStatus.TIMEOUT if timed_out else BindingStatus.WAITING), None
    attempt = attempts[-1]
    observed = attempt.resolved_path
    if attempt.override_failure:
        return BindingStatus.FAILED, observed
    if observed and observed.lower() != expected.lower() and attempt.completed_at:
        return BindingStatus.FAILED, observed
    if observed and observed.lower() == expected.lower() and attempt.override_success is True:
        return BindingStatus.VERIFIED, observed
    if observed and observed.lower() == expected.lower():
        return BindingStatus.OBSERVED, observed
    if timed_out:
        return BindingStatus.TIMEOUT, observed
    return BindingStatus.WAITING, observed


def _verified(attempts: list[BindingAttempt], expected: str) -> bool:
    return any(
        (attempt.resolved_path or "").lower() == expected.lower() and attempt.override_success is True
        for attempt in attempts
    )
