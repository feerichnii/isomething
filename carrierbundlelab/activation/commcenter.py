"""Stateful CommCenter binding parser."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

RESOLVED_RE = re.compile(r"(?:Resolved path|kResolvedPath).*?([A-Za-z0-9_]+\.bundle)", re.I)
LINK_RE = re.compile(r"(?:Linking Path|kLinkingPath)\s*:?\s*(\S+)", re.I)
SLOT_RE = re.compile(r"(?:slot|sim)\s*[:= ]\s*([12])", re.I)
REEVAL_RE = re.compile(r"re-evaluat\w*.*carrier bundle", re.I)


@dataclass
class BindingAttempt:
    slot: int | None
    started_at: datetime
    resolved_path: str | None = None
    linking_path: str | None = None
    override_success: bool | None = None
    override_failure: str | None = None
    completed_at: datetime | None = None


class CommCenterMonitor:
    def __init__(self, log_path: Path | None = None, udid: str | None = None) -> None:
        self.log_path = log_path
        self.udid = udid
        self._proc: subprocess.Popen[str] | None = None
        self._handle = None

    def start(self) -> None:
        if self._proc is not None:
            return
        if self.log_path and self.log_path.exists():
            return
        if self.log_path is None:
            self.log_path = Path("work") / (self.udid or "unknown") / "commcenter-live.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        args = ["pymobiledevice3", "syslog", "live", "--format", "json"]
        if self.udid:
            args.extend(["--udid", self.udid])
        self._handle = self.log_path.open("w", encoding="utf-8")
        self._proc = subprocess.Popen(args, stdout=self._handle, stderr=subprocess.DEVNULL, text=True)

    def wait_for_binding(self, expected_bundle: str, timeout: int = 120) -> list[BindingAttempt]:
        expected = _bundle_name(expected_bundle).lower()
        deadline = time.time() + timeout
        while time.time() < deadline:
            attempts = self.attempts()
            if any((attempt.resolved_path or "").lower() == expected and attempt.override_success for attempt in attempts):
                return attempts
            time.sleep(0.2 if timeout < 5 else 1)
        return self.attempts()

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def attempts(self) -> list[BindingAttempt]:
        if not self.log_path or not self.log_path.exists():
            return []
        return correlate_attempts(self.log_path.read_text(errors="ignore").splitlines())


def correlate_attempts(lines: list[str]) -> list[BindingAttempt]:
    open_by_slot: dict[int | None, BindingAttempt] = {}
    attempts: list[BindingAttempt] = []
    for line in lines:
        parsed = _parse_record(line)
        if parsed is None:
            continue
        message, slot = parsed
        if REEVAL_RE.search(message):
            attempt = BindingAttempt(slot=slot, started_at=datetime.now(UTC))
            open_by_slot[slot] = attempt
            attempts.append(attempt)
            continue
        attempt = open_by_slot.get(slot)
        if attempt is None and slot is None and len(open_by_slot) == 1:
            attempt = next(iter(open_by_slot.values()))
        if attempt is None:
            attempt = BindingAttempt(slot=slot, started_at=datetime.now(UTC))
            open_by_slot[slot] = attempt
            attempts.append(attempt)
        resolved = RESOLVED_RE.search(message)
        if resolved:
            attempt.resolved_path = resolved.group(1)
        link = LINK_RE.search(message)
        if link:
            attempt.linking_path = link.group(1)
        if "kOverrideBundleSuccess" in message:
            attempt.override_success = True
            attempt.completed_at = datetime.now(UTC)
        elif "kOverrideBundleFailure" in message or "OverlayWriteFailure" in message:
            attempt.override_success = False
            attempt.override_failure = message.strip()
            attempt.completed_at = datetime.now(UTC)
    return attempts


def _parse_record(line: str) -> tuple[str, int | None] | None:
    message = line
    process = None
    if line.lstrip().startswith("{"):
        try:
            obj = json.loads(line)
        except Exception:
            return None
        process = str(obj.get("process") or obj.get("subsystem") or obj.get("category") or "")
        message = str(obj.get("message", ""))
    if process and "commcenter" not in process.lower():
        return None
    if not _is_known_marker(message):
        return None
    slot_match = SLOT_RE.search(message)
    slot = int(slot_match.group(1)) if slot_match else None
    return message, slot


def _is_known_marker(message: str) -> bool:
    markers = (
        "Resolved path",
        "kResolvedPath",
        "Linking Path",
        "kLinkingPath",
        "kOverrideBundleSuccess",
        "kOverrideBundleFailure",
        "OverlayWriteFailure",
    )
    if any(marker in message for marker in markers):
        return True
    return REEVAL_RE.search(message) is not None


def _bundle_name(name: str) -> str:
    return name if name.endswith(".bundle") else f"{name}.bundle"
