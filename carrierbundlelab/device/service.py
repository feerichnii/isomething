"""Device discovery. Carrier installation logic does not belong here."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable

from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import DeviceConnectionError, DeviceNotFoundError, MultipleDevicesError
from carrierbundlelab.models import DeviceInfo

log = logging.getLogger("device")


class DeviceService:
    def __init__(self, timeout: int = 10, lister: Callable[[], list[DeviceInfo]] | None = None) -> None:
        self.timeout = timeout
        self._lister = lister

    def list_devices(self) -> list[DeviceInfo]:
        if self._lister is not None:
            return self._lister()
        if not shutil.which("pymobiledevice3"):
            raise DeviceConnectionError("pymobiledevice3 not found")
        result = self._pmd("usbmux", "list")
        return _parse_device_list(result.stdout)

    def connect(self, udid: str | None = None) -> DeviceSession:
        devices = self.list_devices()
        selected = _select_udid(devices, udid)
        log.info("udid=%s selected for session", selected)
        return DeviceSession(selected, timeout=self.timeout)

    def _pmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["pymobiledevice3", *args],
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DeviceConnectionError(f"pymobiledevice3 timed out: {' '.join(args)}") from exc
        if result.returncode != 0:
            raise DeviceConnectionError(result.stderr.strip() or result.stdout.strip())
        return result


def _select_udid(devices: list[DeviceInfo], udid: str | None) -> str:
    known = [device.udid for device in devices if device.udid]
    if udid:
        if udid not in known and known:
            raise DeviceNotFoundError(f"UDID {udid} is not connected")
        return udid
    if len(known) > 1:
        raise MultipleDevicesError("Multiple iPhones connected; pass --udid")
    if len(known) == 1:
        return known[0]
    raise DeviceNotFoundError("No iPhone connected")


def _parse_device_list(stdout: str) -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    try:
        parsed = json.loads(stdout)
        rows = parsed if isinstance(parsed, list) else parsed.get("DeviceList", [])
        for row in rows:
            udid = row.get("SerialNumber") or row.get("UDID") or row.get("Identifier")
            if udid:
                devices.append(DeviceInfo(udid=str(udid), connection_type="USB"))
        return devices
    except Exception:
        for line in stdout.splitlines():
            if line.strip() and "UDID" not in line:
                devices.append(DeviceInfo(udid=line.split()[0], connection_type="USB"))
    return devices
