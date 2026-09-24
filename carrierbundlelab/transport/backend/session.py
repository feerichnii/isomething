"""AirTraffic session binding. No filesystem writes."""

from __future__ import annotations

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import TransportUnavailableError


def backend_session(session: DeviceSession) -> str:
    if not session.udid:
        raise TransportUnavailableError("AirTraffic session requires a UDID")
    return session.udid
