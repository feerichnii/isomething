"""Minimal service-backed GUI shell.

The GUI intentionally delegates all work to the same services used by the CLI.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from carrierbundlelab.carrier import CarrierAssetResolver
from carrierbundlelab.carrier.state import CarrierStateService, format_carrier_state
from carrierbundlelab.device import DeviceService


def run() -> None:
    root = tk.Tk()
    root.title("CarrierBundleLab")
    text = tk.Text(root, width=88, height=28)
    text.pack(fill="both", expand=True)

    def refresh() -> None:
        text.delete("1.0", tk.END)
        try:
            devices = DeviceService().list_devices()
            if len(devices) != 1:
                text.insert("1.0", "Connect exactly one iPhone or use the CLI with --udid.")
                return
            session = DeviceService().connect(devices[0].udid)
            decision = CarrierAssetResolver().explain(session.info)
            state_text = format_carrier_state(CarrierStateService().read_current_state(session))
            text.insert(
                "1.0",
                state_text
                + "\n\n"
                + f"Compatible asset: {decision.asset.path if decision.asset else 'none'}\n"
                + f"Status: {'Compatible' if decision.ok else decision.reason}\n\n"
                + "Use the CLI for dry-run, install, rescan, verify, and restore.",
            )
        except Exception as exc:
            messagebox.showerror("CarrierBundleLab", str(exc))

    tk.Button(root, text="Refresh", command=refresh).pack()
    refresh()
    root.mainloop()
