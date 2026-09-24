"""Device discovery and USB/lockdown access."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from carrierbundlelab.errors import DeviceConnectionError
from carrierbundlelab.models import DeviceInfo, DeviceSession, SimInfo

log = logging.getLogger("device")


class DeviceService:
    """Thin wrapper around pymobiledevice3 with predictable models and timeouts."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self._session: DeviceSession | None = None

    def list_devices(self) -> list[DeviceInfo]:
        if not shutil.which("pymobiledevice3"):
            raise DeviceConnectionError("pymobiledevice3 not found")
        result = self._pmd("usbmux", "list")
        devices: list[DeviceInfo] = []
        try:
            parsed = json.loads(result.stdout)
            rows = parsed if isinstance(parsed, list) else parsed.get("DeviceList", [])
            for row in rows:
                udid = row.get("SerialNumber") or row.get("UDID") or row.get("Identifier")
                devices.append(DeviceInfo(udid=udid, connection_type="USB"))
        except Exception:
            for line in result.stdout.splitlines():
                if line.strip() and "UDID" not in line:
                    devices.append(DeviceInfo(udid=line.split()[0], connection_type="USB"))
        return devices

    def connect(self, udid: str | None = None) -> DeviceSession:
        info = self.get_device_info(udid)
        self._session = DeviceSession(info=info, raw={"udid": udid})
        return self._session

    def get_device_info(self, udid: str | None = None) -> DeviceInfo:
        args = ["lockdown", "info", "--color", "false"]
        if udid:
            args.extend(["--udid", udid])
        result = self._pmd(*args)
        info = self._parse_lockdown_info(result.stdout)
        log.info("Device detected: %s %s %s", info.product_type, info.product_version, info.build_version)
        return info

    def get_sim_info(self) -> list[SimInfo]:
        # pymobiledevice3 does not expose a stable cross-version SIM schema through lockdown.
        # Keep this best-effort and never fail the workflow solely because SIM details are absent.
        sims: list[SimInfo] = []
        try:
            result = self._pmd("lockdown", "info", "com.apple.mobile.phone", "--color", "false")
            data = self._parse_any(result.stdout)
            if isinstance(data, dict):
                sims.append(
                    SimInfo(
                        slot=1,
                        iccid=_first(data, "ICCID", "IntegratedCircuitCardIdentity"),
                        imsi=_first(data, "IMSI", "InternationalMobileSubscriberIdentity"),
                        mcc=_first(data, "MCC", "MobileCountryCode"),
                        mnc=_first(data, "MNC", "MobileNetworkCode"),
                        carrier_name=_first(data, "CarrierName", "Carrier"),
                    )
                )
        except Exception as exc:  # logged, but intentionally non-fatal
            log.debug("SIM info unavailable: %s", exc)
        return sims

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

    @staticmethod
    def _parse_lockdown_info(stdout: str) -> DeviceInfo:
        data = DeviceService._parse_any(stdout)
        if not isinstance(data, dict):
            data = {}
            for line in stdout.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    data[key.strip()] = value.strip()
        return DeviceInfo(
            udid=_first(data, "UniqueDeviceID", "UDID"),
            device_name=_first(data, "DeviceName"),
            product_type=_first(data, "ProductType"),
            product_version=_first(data, "ProductVersion"),
            build_version=_first(data, "BuildVersion"),
            hardware_model=_first(data, "HardwareModel", "BoardId"),
            serial_number=_first(data, "SerialNumber"),
            baseband_version=_first(data, "BasebandVersion"),
            wifi_address=_first(data, "WiFiAddress"),
            connection_type="USB",
        )

    @staticmethod
    def _parse_any(stdout: str) -> Any:
        try:
            return json.loads(stdout)
        except Exception:
            return {}


def _first(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return None
