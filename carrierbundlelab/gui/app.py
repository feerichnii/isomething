"""Minimal service-backed GUI shell.

The GUI intentionally delegates all work to the same services used by the CLI.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from carrierbundlelab.carrier import CarrierAssetResolver, CarrierStateService
from carrierbundlelab.device import DeviceService


def run() -> None:
    root = tk.Tk()
    root.title("CarrierBundleLab")
    text = tk.Text(root, width=88, height=28)
    text.pack(fill="both", expand=True)

    def refresh() -> None:
        text.delete("1.0", tk.END)
        try:
            device = DeviceService().get_device_info()
            state = CarrierStateService().read_current_state()
            decision = CarrierAssetResolver().explain(device)
            lines = [
                "CarrierBundleLab",
                "",
                f"Device: {device.product_type or '?'}",
                f"iOS: {device.product_version or '?'} ({device.build_version or '?'})",
                f"Hardware: {device.hardware_model or '?'}",
                "",
                "SIMs:",
            ]
            lines.extend(f"  SIM {sim.slot}: {sim.carrier_name or '?'}" for sim in state.sims)
            if not state.sims:
                lines.append("  unavailable")
            lines.extend(
                [
                    "",
                    f"Compatible asset: {decision.asset.path if decision.asset else 'none'}",
                    f"Status: {'Compatible' if decision.ok else decision.reason}",
                    "",
                    "Use the CLI for Dry run / Install / Rescan / Verify / Restore.",
                ]
            )
            text.insert("1.0", "\n".join(lines))
        except Exception as exc:
            messagebox.showerror("CarrierBundleLab", str(exc))

    tk.Button(root, text="Refresh", command=refresh).pack()
    refresh()
    root.mainloop()
