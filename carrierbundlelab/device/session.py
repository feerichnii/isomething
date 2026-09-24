"""UDID-scoped device session.

Every pymobiledevice3 invocation made through this session carries the same UDID.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Callable

from carrierbundlelab.errors import DeviceConnectionError
from carrierbundlelab.models import DeviceInfo, SimInfo
from carrierbundlelab.redaction import mask_identifier

log = logging.getLogger("device")

Runner = Callable[..., subprocess.CompletedProcess[str]]


class DeviceSession:
    def __init__(
        self,
        udid: str | None = None,
        info: DeviceInfo | None = None,
        runner: Runner | None = None,
        timeout: int = 10,
    ) -> None:
        resolved = udid or (info.udid if info else None)
        if not resolved:
            raise DeviceConnectionError("UDID is required")
        self.udid = resolved
        self._info = info
        self.timeout = timeout
        self._runner = runner
        self._syslog: subprocess.Popen[str] | None = None

    @property
    def info(self) -> DeviceInfo:
        if self._info is None:
            self._info = self.get_device_info()
        return self._info

    def get_device_info(self) -> DeviceInfo:
        result = self._pmd("lockdown", "info", "--color", "false")
        info = _parse_lockdown_info(result.stdout, fallback_udid=self.udid)
        self._info = info
        log.info(
            "udid=%s device product=%s hardware=%s ios=%s build=%s",
            self.udid,
            info.product_type,
            info.hardware_model,
            info.product_version,
            info.build_version,
        )
        return info

    def get_sim_info(self) -> list[SimInfo]:
        sims: list[SimInfo] = []
        try:
            result = self._pmd("lockdown", "info", "com.apple.mobile.phone", "--color", "false")
            data = _parse_any(result.stdout)
            if isinstance(data, dict) and data:
                sim = SimInfo(
                    slot=1,
                    iccid=_first(data, "ICCID", "IntegratedCircuitCardIdentity"),
                    imsi=_first(data, "IMSI", "InternationalMobileSubscriberIdentity"),
                    mcc=_first(data, "MCC", "MobileCountryCode"),
                    mnc=_first(data, "MNC", "MobileNetworkCode"),
                    carrier_name=_first(data, "CarrierName", "Carrier"),
                )
                sims.append(sim)
                log.info(
                    "udid=%s sim slot=%s iccid=%s imsi=%s",
                    self.udid,
                    sim.slot,
                    mask_identifier(sim.iccid),
                    mask_identifier(sim.imsi),
                )
                log.debug("udid=%s iccid=%s imsi=%s", self.udid, sim.iccid, sim.imsi)
        except Exception as exc:
            log.debug("udid=%s SIM info unavailable: %s", self.udid, exc)
        return sims

    def get_carrier_info(self) -> dict[str, Any]:
        try:
            result = self._pmd("lockdown", "info", "com.apple.commcenter", "--color", "false")
            data = _parse_any(result.stdout)
            if isinstance(data, dict):
                log.info("udid=%s carrier info keys=%s", self.udid, sorted(data))
                return data
        except Exception as exc:
            log.debug("udid=%s carrier info unavailable: %s", self.udid, exc)
        return {}

    def start_syslog(self, outfile: str) -> None:
        self.stop_syslog()
        args = ["pymobiledevice3", "syslog", "live", "--format", "json", "--udid", self.udid]
        log.info("udid=%s start syslog -> %s", self.udid, outfile)
        handle = open(outfile, "w", encoding="utf-8")
        self._syslog = subprocess.Popen(args, stdout=handle, stderr=subprocess.DEVNULL, text=True)

    def stop_syslog(self) -> None:
        if self._syslog is None:
            return
        log.info("udid=%s stop syslog", self.udid)
        self._syslog.terminate()
        try:
            self._syslog.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._syslog.kill()
        self._syslog = None

    def close(self) -> None:
        self.stop_syslog()

    def _pmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        command = list(args)
        if "--udid" not in command:
            command.extend(["--udid", self.udid])
        log.info("udid=%s pymobiledevice3 %s", self.udid, " ".join(command))
        if self._runner is not None:
            return self._runner(*command)
        try:
            result = subprocess.run(
                ["pymobiledevice3", *command],
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DeviceConnectionError(f"udid={self.udid} pymobiledevice3 timed out") from exc
        if result.returncode != 0:
            raise DeviceConnectionError(result.stderr.strip() or result.stdout.strip() or f"udid={self.udid} command failed")
        return result


def _parse_lockdown_info(stdout: str, fallback_udid: str) -> DeviceInfo:
    data = _parse_any(stdout)
    if not isinstance(data, dict) or not data:
        data = {}
        for line in stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                data[key.strip()] = value.strip()
    return DeviceInfo(
        udid=_first(data, "UniqueDeviceID", "UDID") or fallback_udid,
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
