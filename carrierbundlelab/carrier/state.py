"""Readonly carrier state aggregation."""

from __future__ import annotations

import logging
from pathlib import Path

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.models import CarrierPreferenceState, CarrierState, InstalledBundle
from carrierbundlelab.redaction import mask_identifier

log = logging.getLogger("carrier-tree")


class CarrierStateService:
    def __init__(self, transport=None) -> None:
        self.transport = transport

    def read_current_state(self, session: DeviceSession) -> CarrierState:
        sims = session.get_sim_info()
        bundles = self.read_installed_bundles(session)
        preferences = self.read_carrier_preferences(session)
        log.info("udid=%s read carrier state", session.udid)
        return CarrierState(
            device=session.info,
            sims=sims,
            installed_bundles=bundles,
            preferences=preferences,
            resolved_bundle=_text(preferences.values.get("resolved_bundle")),
            resolved_path=_text(preferences.values.get("resolved_path")),
            linking_path=_text(preferences.values.get("linking_path")),
            override_result=_text(preferences.values.get("override_result")),
        )

    def read_installed_bundles(self, session: DeviceSession | None = None) -> list[InstalledBundle]:
        if self.transport is None or session is None:
            return []
        destination = Path("work") / session.udid / "state-export"
        try:
            exported = self.transport.export_tree(session, destination)
        except Exception as exc:
            log.debug("udid=%s installed bundle export unavailable: %s", session.udid, exc)
            return []
        if not exported.ok:
            return []
        bundles = []
        for path in sorted(exported.path.iterdir()):
            if path.name.endswith(".bundle"):
                bundles.append(InstalledBundle(name=path.name, path=str(path)))
        return bundles

    def read_carrier_preferences(self, session: DeviceSession | None = None) -> CarrierPreferenceState:
        if session is None:
            return CarrierPreferenceState(values={})
        return CarrierPreferenceState(values=session.get_carrier_info())


def format_carrier_state(state: CarrierState) -> str:
    device = state.device
    lines = [
        "Device",
        "------",
        f"UDID: {show(device.udid)}",
        f"ProductType: {show(device.product_type)}",
        f"HardwareModel: {show(device.hardware_model)}",
        f"iOS: {show(device.product_version)}",
        f"Build: {show(device.build_version)}",
        "",
    ]
    if not state.sims:
        lines.extend(["SIM", "-----", "unknown", ""])
    for sim in state.sims:
        lines.extend(
            [
                f"SIM {show(sim.slot)}",
                "-----",
                f"ICCID: {mask_identifier(sim.iccid) if sim.iccid else 'unknown'}",
                f"IMSI: {mask_identifier(sim.imsi) if sim.imsi else 'unknown'}",
                f"MCC/MNC: {show(sim.mcc)}/{show(sim.mnc)}",
                "",
            ]
        )
    lines.extend(
        [
            "Carrier binding",
            "---------------",
            f"Resolved bundle: {show(state.resolved_bundle)}",
            f"Resolved path: {show(state.resolved_path)}",
            f"Linking path: {show(state.linking_path)}",
            f"Override result: {show(state.override_result)}",
            "",
            "Installed carrier bundles",
            "-------------------------",
        ]
    )
    if state.installed_bundles:
        lines.extend(bundle.name for bundle in state.installed_bundles)
    else:
        lines.append("unknown")
    return "\n".join(lines)


def show(value) -> str:
    return str(value) if value not in (None, "") else "unknown"


def _text(value):
    if value in (None, ""):
        return None
    return str(value)
