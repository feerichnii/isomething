"""Carrier re-evaluation trigger service."""

from __future__ import annotations

from dataclasses import dataclass

from carrierbundlelab.models import DeviceSession


@dataclass(frozen=True)
class RescanResult:
    ok: bool
    message: str


class CarrierRescanService:
    def trigger(self, session: DeviceSession) -> RescanResult:
        # The safe, supported external trigger is SIM/radio re-registration. We avoid
        # pretending there is a USB API to force binding; users may repeat this step
        # without rewriting the carrier tree.
        return RescanResult(
            ok=True,
            message=(
                "Toggle Airplane Mode ON then OFF to trigger CommCenter carrier "
                "configuration re-evaluation; monitor logs with carrierlab carrier verify."
            ),
        )
