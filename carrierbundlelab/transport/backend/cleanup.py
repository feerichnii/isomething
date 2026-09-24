"""AirTraffic cleanup. No staging is created by the fail-closed backend."""

from __future__ import annotations

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.models import CleanupResult


def backend_cleanup(session: DeviceSession) -> CleanupResult:
    return CleanupResult(ok=True, message=f"udid={session.udid} no AirTraffic staging was created")
