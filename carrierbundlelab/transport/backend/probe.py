"""Fail-closed AirTraffic probe."""

from __future__ import annotations

import shutil

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.models import TransportProbe


def backend_probe(session: DeviceSession) -> TransportProbe:
    tool_present = shutil.which("pymobiledevice3") is not None
    return TransportProbe(
        available=False,
        backend="airtraffic",
        sync_service_available=False,
        staging_available=False,
        canary_successful=False,
        reason="AirTraffic carrier backend is not configured; install stays fail closed.",
        checks={
            "usb_connection_available": bool(session.udid),
            "lockdown_available": tool_present,
            "afc_available": tool_present,
        },
        messages=["Install/export are unavailable until a carrier-only backend capability is confirmed."],
    )
