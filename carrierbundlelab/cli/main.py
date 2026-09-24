"""carrierlab command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from carrierbundlelab.activation import BindingVerifier, CarrierRescanService, CommCenterMonitor
from carrierbundlelab.carrier import CarrierAssetResolver, CarrierBundleInspector
from carrierbundlelab.carrier.inspector import format_inspection
from carrierbundlelab.carrier.state import CarrierStateService, format_carrier_state
from carrierbundlelab.device import DeviceService
from carrierbundlelab.device.session import DeviceSession
from carrierbundlelab.errors import CarrierLabError, DeviceConnectionError, MultipleDevicesError
from carrierbundlelab.logging_config import configure_logging
from carrierbundlelab.models import DeviceInfo, TransactionState
from carrierbundlelab.transaction import BackupManager, CarrierTransaction, RecoveryManager
from carrierbundlelab.transport import AirTrafficCarrierTransport, MockCarrierTransport
from carrierbundlelab.workflow import CarrierInstallWorkflow

EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_DEVICE = 3
EXIT_RECOVERY_REQUIRED = 4


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.debug)
    _warn_incomplete()
    try:
        return args.func(args)
    except MultipleDevicesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DEVICE
    except CarrierLabError as exc:
        if args.debug:
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        code = EXIT_RECOVERY_REQUIRED if "Incomplete" in str(exc) or "RECOVERY" in str(exc) else EXIT_VALIDATION
        return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carrierlab")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--udid", default=None)
    sub = parser.add_subparsers(required=True)

    device = sub.add_parser("device")
    device_sub = device.add_subparsers(required=True)
    device_sub.add_parser("list").set_defaults(func=cmd_device_list)
    device_sub.add_parser("info").set_defaults(func=cmd_device_info)

    sim = sub.add_parser("sim")
    sim.add_subparsers(required=True).add_parser("info").set_defaults(func=cmd_sim_info)

    bundle = sub.add_parser("bundle")
    bundle_sub = bundle.add_subparsers(required=True)
    inspect_p = bundle_sub.add_parser("inspect")
    inspect_p.add_argument("file")
    inspect_p.set_defaults(func=cmd_bundle_inspect)
    bundle_sub.add_parser("resolve").set_defaults(func=cmd_bundle_resolve)
    check_p = bundle_sub.add_parser("check")
    check_p.add_argument("file")
    check_p.set_defaults(func=cmd_bundle_check)

    transport = sub.add_parser("transport")
    transport.add_subparsers(required=True).add_parser("probe").set_defaults(func=cmd_transport_probe)

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
    install_p.add_argument("--expected", default="CarrierLab.bundle")
    install_p.set_defaults(func=cmd_carrier_install)
    carrier_sub.add_parser("rescan").set_defaults(func=cmd_carrier_rescan)
    verify_p = carrier_sub.add_parser("verify")
    verify_p.add_argument("--log")
    verify_p.add_argument("--expected", default="CarrierLab.bundle")
    verify_p.set_defaults(func=cmd_carrier_verify)
    restore_p = carrier_sub.add_parser("restore")
    restore_p.add_argument("--force", action="store_true")
    restore_p.set_defaults(func=cmd_carrier_restore)

    tx = sub.add_parser("transaction")
    tx_sub = tx.add_subparsers(required=True)
    tx_sub.add_parser("list").set_defaults(func=cmd_transaction_list)
    show_p = tx_sub.add_parser("show")
    show_p.add_argument("id")
    show_p.set_defaults(func=cmd_transaction_show)
    recover_p = tx_sub.add_parser("recover")
    recover_p.add_argument("id")
    recover_p.add_argument("--force", action="store_true")
    recover_p.set_defaults(func=cmd_transaction_recover)
    mark_p = tx_sub.add_parser("mark-recovery")
    mark_p.add_argument("id")
    mark_p.set_defaults(func=cmd_transaction_mark)

    sub.add_parser("gui").set_defaults(func=cmd_gui)
    return parser


def cmd_device_list(args) -> int:
    for device in DeviceService().list_devices():
        print(f"{device.udid or 'unknown'} {device.product_type or 'unknown'}")
    return EXIT_SUCCESS


def cmd_device_info(args) -> int:
    print(_device_text(_session(args).info))
    return EXIT_SUCCESS


def cmd_sim_info(args) -> int:
    sims = _session(args).get_sim_info()
    if not sims:
        print("unknown")
    for sim in sims:
        print(f"SIM {sim.slot or 'unknown'}")
    return EXIT_SUCCESS


def cmd_carrier_state(args) -> int:
    session = _session(args)
    print(format_carrier_state(CarrierStateService(_transport()).read_current_state(session)))
    return EXIT_SUCCESS


def cmd_carrier_list(args) -> int:
    session = _session(args)
    bundles = CarrierStateService(_transport()).read_installed_bundles(session)
    if not bundles:
        print("unknown")
    for bundle in bundles:
        print(bundle.name)
    return EXIT_SUCCESS


def cmd_bundle_inspect(args) -> int:
    print(format_inspection(CarrierBundleInspector().inspect(args.file)))
    return EXIT_SUCCESS


def cmd_bundle_resolve(args) -> int:
    decision = CarrierAssetResolver().explain(_session(args).info)
    print(decision.reason)
    for detail in decision.details:
        print(f"  {detail}")
    return EXIT_SUCCESS if decision.ok else EXIT_VALIDATION


def cmd_bundle_check(args) -> int:
    session = _session(args)
    decision = CarrierAssetResolver().explain(session.info)
    inspection = CarrierBundleInspector().inspect(args.file)
    print(decision.reason)
    print(f"Bundle: {inspection.bundle_name}")
    print(f"Identifier: {inspection.bundle_identifier or 'unknown'}")
    compatible = decision.ok and inspection.bundle_identifier == "com.apple.CarrierLab"
    return EXIT_SUCCESS if compatible else EXIT_VALIDATION


def cmd_transport_probe(args) -> int:
    probe = _transport().probe(_session(args))
    print(f"Transport: {'READY' if probe.available else 'NOT READY'}")
    print(f"  backend: {probe.backend}")
    print(f"  sync_service_available: {probe.sync_service_available}")
    print(f"  staging_available: {probe.staging_available}")
    print(f"  canary_successful: {probe.canary_successful}")
    if probe.reason:
        print(f"  reason: {probe.reason}")
    return EXIT_SUCCESS if probe.available else EXIT_VALIDATION


def cmd_carrier_backup(args) -> int:
    session = _session(args)
    tx = CarrierTransaction.start(session, operation="backup")
    tx.transition(TransactionState.PROBED, "probe")
    decision = CarrierAssetResolver().explain(session.info)
    if not decision.ok:
        tx.fail(decision.reason)
        print(decision.reason)
        return EXIT_VALIDATION
    tx.transition(TransactionState.COMPATIBILITY_VERIFIED, decision.reason)
    BackupManager(_transport()).create_verified_backup(tx)
    print(f"Backup: VERIFIED ({tx.root})")
    return EXIT_SUCCESS


def cmd_carrier_plan(args) -> int:
    args.dry_run = True
    args.expected = "CarrierLab.bundle"
    return cmd_carrier_install(args)


def cmd_carrier_install(args) -> int:
    session = _session(args)
    result = CarrierInstallWorkflow(session, _transport(), CarrierAssetResolver()).install(
        Path(args.file),
        dry_run=args.dry_run,
        expected_bundle=args.expected,
    )
    print(f"Transaction: {result.transaction_id}")
    print(f"Status: {result.status}")
    for line in result.lines:
        print(line)
    return EXIT_SUCCESS if result.status in {"COMMITTED", "DRY RUN", "WAITING"} else EXIT_VALIDATION


def cmd_carrier_rescan(args) -> int:
    session = _session(args)
    monitor = CommCenterMonitor(udid=session.udid)
    result = CarrierRescanService().trigger(session, monitor)
    print(result.status.value)
    print(result.message)
    return EXIT_SUCCESS if result.status.value != "failed" else EXIT_VALIDATION


def cmd_carrier_verify(args) -> int:
    monitor = CommCenterMonitor(log_path=Path(args.log) if args.log else None, udid=None if args.log else _session(args).udid)
    verification = BindingVerifier(monitor).verify(args.expected)
    print(f"CommCenter binding: {verification.status.value}")
    print(f"Resolved bundle: {verification.observed_bundle or 'unknown'}")
    return EXIT_SUCCESS if verification.status.value == "VERIFIED" else EXIT_VALIDATION


def cmd_carrier_restore(args) -> int:
    result = RecoveryManager(_transport()).restore_latest(_session(args), force=args.force)
    print(f"Restore: OK {result.message}")
    return EXIT_SUCCESS


def cmd_transaction_list(args) -> int:
    journals = CarrierTransaction.list_journals()
    if not journals:
        print("none")
    for journal in journals:
        print(journal)
    return EXIT_SUCCESS


def cmd_transaction_show(args) -> int:
    print(CarrierTransaction.read_journal(args.id))
    return EXIT_SUCCESS


def cmd_transaction_recover(args) -> int:
    result = RecoveryManager(_transport()).restore_transaction(args.id, _session(args), force=args.force)
    print(f"Restore: OK {result.message}")
    return EXIT_SUCCESS


def cmd_transaction_mark(args) -> int:
    tx = CarrierTransaction.open(args.id)
    tx.mark_recovery_required("manual recovery mark")
    print(f"Recovery required: {tx.transaction_id}")
    return EXIT_RECOVERY_REQUIRED


def cmd_gui(args) -> int:
    from carrierbundlelab.gui.app import run

    run()
    return EXIT_SUCCESS


def _session(args) -> DeviceSession:
    if os.environ.get("CARRIERLAB_MOCK_TREE"):
        info = DeviceInfo(
            udid=args.udid or os.environ.get("CARRIERLAB_MOCK_UDID", "mock-udid"),
            product_type=os.environ.get("CARRIERLAB_MOCK_PRODUCT", "iPhone14,7"),
            product_version=os.environ.get("CARRIERLAB_MOCK_IOS", "27.0"),
            build_version=os.environ.get("CARRIERLAB_MOCK_BUILD", "24A437"),
            hardware_model=os.environ.get("CARRIERLAB_MOCK_HARDWARE", "D27AP"),
            connection_type="mock",
        )
        return DeviceSession(udid=info.udid, info=info, runner=_offline_runner)
    return DeviceService().connect(args.udid)


def _transport():
    mock_tree = os.environ.get("CARRIERLAB_MOCK_TREE")
    if mock_tree:
        return MockCarrierTransport(Path(mock_tree))
    return AirTrafficCarrierTransport()


def _offline_runner(*args: str):
    raise DeviceConnectionError("offline mock session")


def _device_text(device: DeviceInfo) -> str:
    return "\n".join(
        [
            f"Device: {device.product_type or 'unknown'}",
            f"HardwareModel: {device.hardware_model or 'unknown'}",
            f"IOS: {device.product_version or 'unknown'}",
            f"Build: {device.build_version or 'unknown'}",
            f"UDID: {device.udid or 'unknown'}",
        ]
    )


def _warn_incomplete() -> None:
    for item in CarrierTransaction.find_incomplete():
        print(
            "WARNING\n\nIncomplete carrier transaction found:\n"
            f"ID: {item.get('transaction_id')}\n"
            f"Device: {item.get('udid')}\n"
            f"State: {item.get('state')}\n\n"
            f"Run:\n\ncarrierlab transaction recover {item.get('transaction_id')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
