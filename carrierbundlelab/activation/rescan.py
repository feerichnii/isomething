"""Carrier re-evaluation trigger service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from carrierbundlelab.device.session import DeviceSession


class RescanStatus(str, Enum):
    TRIGGERED = "triggered"
    MANUAL_ACTION_REQUIRED = "manual_action_required"
    FAILED = "failed"


@dataclass(frozen=True)
class RescanResult:
    status: RescanStatus
    message: str

    @property
    def ok(self) -> bool:
        return self.status == RescanStatus.TRIGGERED


class CarrierRescanService:
    def trigger(self, session: DeviceSession, monitor=None) -> RescanResult:
        if monitor is not None:
            if monitor.log_path is None:
                monitor.udid = session.udid
            try:
                monitor.start()
            except OSError as exc:
                return RescanResult(status=RescanStatus.FAILED, message=str(exc))
        return RescanResult(
            status=RescanStatus.MANUAL_ACTION_REQUIRED,
            message="Toggle Airplane Mode ON and OFF. CommCenter monitor is already running.",
        )
