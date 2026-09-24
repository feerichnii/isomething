"""carrierlab command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from carrierbundlelab.activation import BindingVerifier, CarrierRescanService, CommCenterMonitor
from carrierbundlelab.carrier import (
    CarrierAssetResolver,
    CarrierBundleInspector,
    CarrierLabMigrationService,
    CarrierStateService,
)
from carrierbundlelab.device import DeviceService
from carrierbundlelab.errors import CarrierLabError
from carrierbundlelab.logging_config import configure_logging
from carrierbundlelab.models import DeviceInfo, DeviceSession
from carrierbundlelab.transaction import BackupManager, CarrierTransaction, RecoveryManager
from carrierbundlelab.transport import AirTrafficCarrierTransport, MockCarrierTransport


EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_DEVICE = 3
EXIT_RECOVERY_REQUIRED = 4


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.debug)
    try:
        return args.func(args)
    except CarrierLabError as exc:
        if args.debug:
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carrierlab")
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(required=True)

    device = sub.add_parser("device")
    device_sub = device.add_subparsers(required=True)
    device_sub.add_parser("list").set_defaults(func=cmd_device_list)
    device_sub.add_parser("info").set_defaults(func=cmd_device_info)

    sim = sub.add_parser("sim")
    sim_sub = sim.add_subparsers(required=True)
    sim_sub.add_parser("info").set_defaults(func=cmd_sim_info)

    bundle = sub.add_parser("bundle")
    bundle_sub = bundle.add_subparsers(required=True)
    inspect_p = bundle_sub.add_parser("inspect")
    inspect_p.add_argument("file")
    inspect_p.set_defaults(func=cmd_bundle_inspect)
    bundle_sub.add_parser("resolve").set_defaults(func=cmd_bundle_resolve)

    transport = sub.add_parser("transport")
    transport_sub = transport.add_subparsers(required=True)
    transport_sub.add_parser("probe").set_defaults(func=cmd_transport_probe)

    carrier = sub.add_parser("carrier")
    carrier_sub = carrier.add_subparsers(required=True)
    carrier_sub.add_parser("state").set_defaults(func=cmd_carrier_state)
    carrier_sub.add_parser("list").set_defaults(func=cmd_carrier_list)
    carrier_sub.add_parser("backup").set_defaults(func=cmd_carrier_backup)
    plan_p = carrier_sub.add_parser("plan")
    plan_p.add_argument("file")
    plan_p.set_defaults(func=cmd_carrier_plan)
    install_p = carrier_sub.add_parser("install")
    install_p.add_argument("file")
    install_p.add_argument("--dry-run", action="store_true")
    install_p.set_defaults(func=cmd_carrier_install)
    carrier_sub.add_parser("rescan").set_defaults(func=cmd_carrier_rescan)
    verify_p = carrier_sub.add_parser("verify")
    verify_p.add_argument("--log")
    verify_p.add_argument("--bundle", default="CarrierLab")
    verify_p.set_defaults(func=cmd_carrier_verify)
    carrier_sub.add_parser("restore").set_defaults(func=cmd_carrier_restore)

    tx = sub.add_parser("transaction")
    tx_sub = tx.add_subparsers(required=True)
    tx_sub.add_parser("list").set_defaults(func=cmd_transaction_list)
    show_p = tx_sub.add_parser("show")
    show_p.add_argument("id")
    show_p.set_defaults(func=cmd_transaction_show)
    recover_p = tx_sub.add_parser("recover")
    recover_p.add_argument("id")
    recover_p.set_defaults(func=cmd_transaction_recover)

    gui = sub.add_parser("gui")
    gui.set_defaults(func=cmd_gui)
    return parser


def cmd_device_list(args) -> int:
    for device in DeviceService().list_devices():
        print(_device_line(device))
    return EXIT_SUCCESS


def cmd_device_info(args) -> int:
    print_device(DeviceService().get_device_info())
    return EXIT_SUCCESS


def cmd_sim_info(args) -> int:
    sims = DeviceService().get_sim_info()
    if not sims:
        print("No SIM information available")
    for sim in sims:
        print(json.dumps(asdict(sim), indent=2))
    return EXIT_SUCCESS


def cmd_carrier_state(args) -> int:
    state = CarrierStateService().read_current_state()
    print_device(state.device)
    print("\nSIMs:")
    if not state.sims:
        print("  unavailable")
    for sim in state.sims:
        print(f"  SIM {sim.slot}: {sim.carrier_name or '?'} {sim.mcc or '?'}/{sim.mnc or '?'}")
    print("\nResolved carrier state:")
    print(f"  Bundle: {state.resolved_bundle or 'not observed'}")
    print(f"  Path: {state.resolved_path or 'not observed'}")
    return EXIT_SUCCESS


def cmd_carrier_list(args) -> int:
    for bundle in CarrierStateService().read_installed_bundles():
        print(json.dumps(asdict(bundle), indent=2))
    return EXIT_SUCCESS


def cmd_bundle_inspect(args) -> int:
    inspection = CarrierBundleInspector().inspect(args.file)
    print(f"Bundle: {inspection.bundle_name}")
    print(f"Identifier: {inspection.bundle_identifier}")
    print(f"Carrier version: {inspection.carrier_version}")
    print(f"Payload hash: {inspection.payload_hash}")
    print("Compatibility:")
    print(json.dumps(inspection.compatibility, indent=2))
    print("Overrides:")
    for override in inspection.overrides:
        print(f"  {override}")
    return EXIT_SUCCESS


def cmd_bundle_resolve(args) -> int:
    device = DeviceService().get_device_info()
    decision = CarrierAssetResolver().explain(device)
    print(decision.reason)
    for detail in decision.details:
        print(f"  {detail}")
    if decision.asset:
        print(f"Asset: {decision.asset.path}")
    return EXIT_SUCCESS if decision.ok else EXIT_VALIDATION


def cmd_transport_probe(args) -> int:
    session = _session()
    probe = _transport().probe(session)
    print(f"Transport: {'READY' if probe.ok else 'NOT READY'}")
    for key, value in probe.checks.items():
        print(f"  {key}: {value}")
    for message in probe.messages:
        print(f"  note: {message}")
    return EXIT_SUCCESS if probe.ok else EXIT_VALIDATION


def cmd_carrier_backup(args) -> int:
    tx = CarrierTransaction.start(_session(), operation="backup")
    manager = BackupManager(_transport())
    manager.create_verified_backup(tx)
    print(f"Backup: VERIFIED ({tx.root})")
    return EXIT_SUCCESS


def cmd_carrier_plan(args) -> int:
    tx = CarrierTransaction.start(_session(), operation="plan")
    BackupManager(_transport()).create_verified_backup(tx)
    _build_plan(tx, Path(args.file))
    print(f"Plan written: {tx.root}")
    return EXIT_SUCCESS


def cmd_carrier_install(args) -> int:
    tx = CarrierTransaction.start(_session(), operation="install_carrierlab")
    BackupManager(_transport()).create_verified_backup(tx)
    plan = _build_plan(tx, Path(args.file))
    if args.dry_run:
        print("DRY RUN COMPLETE")
        return EXIT_SUCCESS
    tx.install(plan, _transport())
    print("Install: OK")
    return EXIT_SUCCESS


def cmd_carrier_rescan(args) -> int:
    result = CarrierRescanService().trigger(_session())
    print(f"Carrier rescan: {'OK' if result.ok else 'FAILED'} {result.message}")
    return EXIT_SUCCESS if result.ok else EXIT_VALIDATION


def cmd_carrier_verify(args) -> int:
    monitor = CommCenterMonitor(log_path=Path(args.log) if args.log else None)
    verification = BindingVerifier(monitor).verify(args.bundle)
    print(f"CommCenter binding: {verification.status.value}")
    print(f"Resolved bundle: {verification.observed_bundle or 'not observed'}")
    return EXIT_SUCCESS if verification.observed_bundle else EXIT_VALIDATION


def cmd_carrier_restore(args) -> int:
    result = RecoveryManager(_transport()).restore_latest(_session())
    print(f"Restore: {'OK' if result.ok else 'FAILED'} {result.message}")
    return EXIT_SUCCESS if result.ok else EXIT_VALIDATION


def cmd_transaction_list(args) -> int:
    for journal in CarrierTransaction.list_journals():
        print(journal)
    return EXIT_SUCCESS


def cmd_transaction_show(args) -> int:
    print(CarrierTransaction.read_journal(args.id))
    return EXIT_SUCCESS


def cmd_transaction_recover(args) -> int:
    tx = CarrierTransaction.open(args.id)
    tx.mark_recovery_required("manual recover requested")
    print(f"Recovery required: {tx.transaction_id}")
    return EXIT_RECOVERY_REQUIRED


def cmd_gui(args) -> int:
    from carrierbundlelab.gui.app import run

    run()
    return EXIT_SUCCESS


def _session() -> DeviceSession:
    if os.environ.get("CARRIERLAB_MOCK_TREE"):
        return DeviceSession(
            info=DeviceInfo(
                udid=os.environ.get("CARRIERLAB_MOCK_UDID", "mock-udid"),
                product_type=os.environ.get("CARRIERLAB_MOCK_PRODUCT", "iPhone14,7"),
                product_version=os.environ.get("CARRIERLAB_MOCK_IOS", "27.0"),
                build_version=os.environ.get("CARRIERLAB_MOCK_BUILD", "24A437"),
                hardware_model=os.environ.get("CARRIERLAB_MOCK_HARDWARE", "D27AP"),
                connection_type="mock",
            )
        )
    return DeviceService().connect()


def _transport():
    mock_tree = os.environ.get("CARRIERLAB_MOCK_TREE")
    if mock_tree:
        return MockCarrierTransport(Path(mock_tree))
    return AirTrafficCarrierTransport()


def _build_plan(tx: CarrierTransaction, file: Path):
    asset = CarrierAssetResolver().resolve(tx.session.info)
    asset = type(asset)(path=file, ios_family=asset.ios_family, hardware_group=asset.hardware_group)
    return CarrierLabMigrationService().build_desired_tree(tx.paths.original_tree, asset, tx.paths.desired_tree)


def print_device(device: DeviceInfo) -> None:
    print(f"Device: {device.product_type or '?'}")
    print(f"HardwareModel: {device.hardware_model or '?'}")
    print(f"IOS: {device.product_version or '?'}")
    print(f"Build: {device.build_version or '?'}")
    print(f"UDID: {device.udid or '?'}")


def _device_line(device: DeviceInfo) -> str:
    return f"{device.udid or '?'} {device.product_type or '?'} {device.product_version or '?'}"


if __name__ == "__main__":
    raise SystemExit(main())
