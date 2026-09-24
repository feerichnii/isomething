"""Readonly carrier state aggregation."""

from __future__ import annotations

import logging

from carrierbundlelab.device import DeviceService
from carrierbundlelab.models import CarrierPreferenceState, CarrierState, DeviceSession, InstalledBundle

log = logging.getLogger("carrier-tree")


class CarrierStateService:
    def __init__(self, device_service: DeviceService | None = None) -> None:
        self.device_service = device_service or DeviceService()

    def read_current_state(self, session: DeviceSession | None = None) -> CarrierState:
        device = session.info if session else self.device_service.get_device_info()
        sims = self.device_service.get_sim_info()
        preferences = self.read_carrier_preferences()
        resolved = preferences.values.get("resolved_bundle")
        return CarrierState(
            device=device,
            sims=sims,
            installed_bundles=self.read_installed_bundles(),
            preferences=preferences,
            resolved_bundle=str(resolved) if resolved else None,
            resolved_path=preferences.values.get("resolved_path"),
        )

    def read_installed_bundles(self) -> list[InstalledBundle]:
        # USB-read visibility into /var/mobile/Library/Carrier Bundles is transport-specific.
        # Keep the service readonly and let transport/readback populate this in later phases.
        return []

    def read_carrier_preferences(self) -> CarrierPreferenceState:
        # Placeholder for a future read_carrier_preference adapter. Returning an empty state
        # is intentional: absence of preferences must not block probe/status workflows.
        return CarrierPreferenceState(values={})
