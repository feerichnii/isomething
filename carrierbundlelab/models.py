"""Shared dataclasses and enums for CarrierBundleLab."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DeviceInfo:
    udid: str | None = None
    device_name: str | None = None
    product_type: str | None = None
    product_version: str | None = None
    build_version: str | None = None
    hardware_model: str | None = None
    serial_number: str | None = None
    baseband_version: str | None = None
    wifi_address: str | None = None
    connection_type: str | None = None


@dataclass(frozen=True)
class SimInfo:
    slot: int | str | None = None
    subscription_id: str | None = None
    iccid: str | None = None
    imsi: str | None = None
    mcc: str | None = None
    mnc: str | None = None
    carrier_name: str | None = None
    current_carrier_bundle: str | None = None
    carrier_bundle_version: str | None = None


@dataclass(frozen=True)
class InstalledBundle:
    name: str
    path: str | None = None
    version: str | None = None
    identifier: str | None = None


@dataclass(frozen=True)
class CarrierPreferenceState:
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CarrierState:
    device: DeviceInfo
    sims: list[SimInfo] = field(default_factory=list)
    installed_bundles: list[InstalledBundle] = field(default_factory=list)
    preferences: CarrierPreferenceState = field(default_factory=CarrierPreferenceState)
    resolved_bundle: str | None = None
    resolved_path: str | None = None
    linking_path: str | None = None
    override_result: str | None = None


@dataclass(frozen=True)
class FileManifestEntry:
    type: str
    size: int | None = None
    sha256: str | None = None
    mode: int | None = None
    target: str | None = None


@dataclass(frozen=True)
class TreeManifest:
    files: dict[str, FileManifestEntry] = field(default_factory=dict)
    directories: dict[str, FileManifestEntry] = field(default_factory=dict)
    symlinks: dict[str, FileManifestEntry] = field(default_factory=dict)
    created_at: str | None = None
    udid: str | None = None
    product_type: str | None = None
    hardware_model: str | None = None
    product_version: str | None = None
    build_version: str | None = None


@dataclass(frozen=True)
class ManifestDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    symlink_target_changed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified or self.symlink_target_changed)


@dataclass(frozen=True)
class BundleInspection:
    source: Path
    bundle_name: str
    bundle_identifier: str | None
    carrier_version: str | None
    payload_hash: str
    compatibility: dict[str, Any] = field(default_factory=dict)
    overrides: list[str] = field(default_factory=list)
    manifest: TreeManifest = field(default_factory=TreeManifest)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CarrierAsset:
    path: Path
    ios_family: str
    hardware_group: str
    bundle_name: str | None = None
    carrier_version: str | None = None


@dataclass(frozen=True)
class CompatibilityDecision:
    ok: bool
    reason: str
    asset: CarrierAsset | None = None
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TransportProbe:
    available: bool
    backend: str
    sync_service_available: bool = False
    staging_available: bool = False
    canary_successful: bool = False
    reason: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.available


@dataclass(frozen=True)
class ExportResult:
    ok: bool
    path: Path
    manifest: TreeManifest | None = None


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    message: str = ""
    diff: ManifestDiff | None = None


@dataclass(frozen=True)
class CleanupResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class MigrationPlan:
    original_tree: Path
    desired_tree: Path
    asset: CarrierAsset
    manifest: TreeManifest
    diff: ManifestDiff
    strategy: str
    allowed_paths: set[str]


class TransactionState(str, Enum):
    NEW = "NEW"
    DEVICE_CONNECTED = "DEVICE_CONNECTED"
    PROBED = "PROBED"
    COMPATIBILITY_VERIFIED = "COMPATIBILITY_VERIFIED"
    BACKUP_STARTED = "BACKUP_STARTED"
    BACKUP_VERIFIED = "BACKUP_VERIFIED"
    DESIRED_TREE_READY = "DESIRED_TREE_READY"
    INSTALL_STARTED = "INSTALL_STARTED"
    INSTALL_FINISHED = "INSTALL_FINISHED"
    READBACK_VERIFIED = "READBACK_VERIFIED"
    RESCAN_REQUESTED = "RESCAN_REQUESTED"
    BINDING_OBSERVED = "BINDING_OBSERVED"
    BINDING_VERIFIED = "BINDING_VERIFIED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RESTORE_STARTED = "RESTORE_STARTED"
    RESTORE_VERIFIED = "RESTORE_VERIFIED"
    ROLLED_BACK = "ROLLED_BACK"


class BindingStatus(str, Enum):
    WAITING = "WAITING"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class BindingEvent:
    timestamp: str | None = None
    sim_slot: str | None = None
    resolved_path: str | None = None
    linking_path: str | None = None
    verification_result: str | None = None
    raw_line: str = ""


@dataclass(frozen=True)
class BindingVerification:
    status: BindingStatus
    expected_bundle: str
    observed_bundle: str | None = None
    events: list[BindingEvent] = field(default_factory=list)
