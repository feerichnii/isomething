"""CommCenter log monitor and parser."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from carrierbundlelab.models import BindingEvent

MARKERS = {
    "BindingEvaluator": re.compile(r"re-evaluat.*carrier bundle|carrier context binding|User data SIM has changed", re.I),
    "Resolved path": re.compile(r"Resolved path|resolved_bundle_name|kResolvedPath", re.I),
    "Linking Path": re.compile(r"Linking Path|kLinkingPath", re.I),
    "Verification Result": re.compile(r"Verification Result|kOverrideBundleSuccess", re.I),
    "Verification Skipped": re.compile(r"Verification Skipped", re.I),
    "reload": re.compile(r"carrier bundle reload|carrier bundle update|OverlayBundle", re.I),
}
RESOLVED_RE = re.compile(
    r"(?:Resolved path|resolved_bundle_name|matching_bundle_name|kResolvedPath).*?([A-Za-z0-9_]+\.bundle)",
    re.I,
)
LINK_RE = re.compile(r"(?:Linking Path|kLinkingPath).*?([^\s]+)", re.I)


class CommCenterMonitor:
    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self.log_path is None:
            self.log_path = Path("work") / "commcenter-live.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.log_path.open("w", encoding="utf-8")
        self._proc = subprocess.Popen(
            ["pymobiledevice3", "syslog", "live", "--format", "json"],
            stdout=fh,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def wait_for_binding(self, expected_bundle: str, timeout: int = 120) -> list[BindingEvent]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            events = self.events()
            if any((event.resolved_path or "").lower().endswith(_bundle(expected_bundle).lower()) for event in events):
                return events
            time.sleep(1)
        return self.events()

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def events(self) -> list[BindingEvent]:
        if not self.log_path or not self.log_path.exists():
            return []
        events: list[BindingEvent] = []
        for line in self.log_path.read_text(errors="ignore").splitlines():
            event = parse_line(line)
            if event:
                events.append(event)
        return events


def parse_line(line: str) -> BindingEvent | None:
    raw = line
    timestamp = None
    if line.lstrip().startswith("{"):
        try:
            obj = json.loads(line)
            raw = str(obj.get("message", line))
            timestamp = str(obj.get("timestamp") or obj.get("time") or "") or None
        except Exception:
            raw = line
    if not any(pattern.search(raw) for pattern in MARKERS.values()):
        return None
    resolved = None
    link = None
    verification = None
    m = RESOLVED_RE.search(raw)
    if m:
        resolved = m.group(1)
    l = LINK_RE.search(raw)
    if l:
        link = l.group(1)
    if "kOverrideBundleSuccess" in raw or "success" in raw.lower():
        verification = "success"
    elif "failure" in raw.lower():
        verification = "failure"
    return BindingEvent(timestamp=timestamp, resolved_path=resolved, linking_path=link, verification_result=verification, raw_line=raw)


def _bundle(name: str) -> str:
    return name if name.endswith(".bundle") else f"{name}.bundle"
