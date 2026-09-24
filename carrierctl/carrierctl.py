#!/usr/bin/env python3
"""
carrierctl - observe & verify iOS carrier-bundle binding over USB (read-only + honest).

Based on reverse engineering of CommCenter (iOS 27, iPhone14,7 / 24A437):

  * Carrier binding is NOT a settable property. CommCenter picks a bundle by matching
    the active SIM's PLMN (MCC+MNC) against each bundle's carrier.plist -> SupportedSIMs,
    writes BundleLinks (kResolvedPath), generates an overlay (kOverlayBundle), and reports
    kOverrideBundleSuccess.
  * There is NO USB/lockdown API to force "use CarrierLab.bundle". The write verbs that
    exist (Install=IPCC, Reset, OTA) are on-device XPC gated by Apple-private entitlements.

So this tool does what is actually possible from a Mac over USB, without IPCC / jailbreak:
    device  - show device identity
    status  - capture the live log and report the currently RESOLVED bundle + overlay
    verify  - scan a captured log for the binding markers
    bind    - drive the ONLY legitimate path: (re)present a matching SIM + trigger
              re-evaluation (airplane toggle), then verify whether it resolved to --bundle.
              It cannot and will not fake a "force" that iOS does not expose.
    reset   - guidance + verification for returning to automatic (operator) binding.

Everything on-device is done via `pymobiledevice3` (install: pip install -U pymobiledevice3).
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time

# ---- binding markers discovered in CommCenter --------------------------------
MARKERS = {
    "BindingEvaluator": r"re-evaluat.*carrier bundle|carrier context binding|User data SIM has changed",
    "kResolvedPath":    r"Resolved path|resolved_bundle_name|kResolvedPath",
    "kOverlayBundle":   r"OverlayBundle (request|response)|kOverlayBundle|overlay_file_name|CBOverlay",
    "kOverrideBundleSuccess": r"kOverrideBundleSuccess",
    "getSupportsNG":    r"SupportsNG|SupportsVoNR|5G ?Standalone",
}
# Grab the final "<name>.bundle" token; works even when the path contains
# a space ("Carrier Bundles"). Anchored to a resolution context.
RESOLVED_RE = re.compile(
    r"(?:Resolved path|resolved_bundle_name|matching_bundle_name|kResolvedPath).*?"
    r"([A-Za-z0-9_]+\.bundle)", re.I)
BUNDLE_NAME_RE = RESOLVED_RE

C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[1m", "x": "\033[0m"}
def c(s, k):  # color helper
    return f"{C[k]}{s}{C['x']}" if sys.stdout.isatty() else s

def have_pmd() -> bool:
    return shutil.which("pymobiledevice3") is not None

def pmd(*args, timeout=None, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(["pymobiledevice3", *args],
                          capture_output=capture, text=True, timeout=timeout)

def require_pmd():
    if not have_pmd():
        sys.exit(c("pymobiledevice3 not found. Install: pip install -U pymobiledevice3", "r"))

# ---- device ------------------------------------------------------------------
def cmd_device(_):
    require_pmd()
    try:
        r = pmd("lockdown", "info", "--color", "false", timeout=30)
        info = {}
        try:
            info = json.loads(r.stdout)
        except Exception:
            for line in r.stdout.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    info[k.strip()] = v.strip()
    except Exception as e:
        sys.exit(c(f"Could not query device: {e}", "r"))
    g = lambda *k: next((info[x] for x in k if info.get(x)), "?")
    print(c("Device:", "b"))
    print(f"  {g('DeviceName')}")
    print(f"  {g('ProductType')}")
    print(f"  {g('HardwareModel','BoardId')}")
    print(f"  iOS {g('ProductVersion')} {g('BuildVersion')}")
    print(f"  ECID {g('UniqueChipID')}  UDID {g('UniqueDeviceID')}")

# ---- log capture -------------------------------------------------------------
def capture_syslog(seconds: int, outfile: str) -> None:
    """Capture NDJSON syslog for `seconds` into outfile (best-effort)."""
    require_pmd()
    print(c(f"Capturing device log for {seconds}s -> {outfile}", "y"))
    with open(outfile, "w") as fh:
        try:
            p = subprocess.Popen(["pymobiledevice3", "syslog", "live", "--format", "json"],
                                 stdout=fh, stderr=subprocess.DEVNULL, text=True)
            time.sleep(seconds)
        finally:
            try:
                p.terminate(); p.wait(timeout=5)
            except Exception:
                p.kill()

def scan(path: str) -> dict:
    """Scan a captured NDJSON/plain log for binding markers + resolved bundle."""
    hits = {k: 0 for k in MARKERS}
    resolved = None
    supports_ng = False
    if not os.path.exists(path):
        return {"hits": hits, "resolved": None, "supports_ng": False, "lines": 0}
    n = 0
    pats = {k: re.compile(v, re.I) for k, v in MARKERS.items()}
    with open(path, errors="ignore") as fh:
        for line in fh:
            n += 1
            msg = line
            if line.lstrip().startswith("{"):
                try:
                    msg = json.loads(line).get("message", line)
                except Exception:
                    pass
            for k, rx in pats.items():
                if rx.search(msg):
                    hits[k] += 1
            m = RESOLVED_RE.search(msg) or BUNDLE_NAME_RE.search(msg)
            if m:
                resolved = os.path.basename(m.group(1) if m.lastindex else m.group(0))
            if pats["getSupportsNG"].search(msg):
                supports_ng = True
    return {"hits": hits, "resolved": resolved, "supports_ng": supports_ng, "lines": n}

# ---- status ------------------------------------------------------------------
def cmd_status(a):
    tmp = a.log or tempfile.mktemp(suffix=".jsonl", prefix="carrierctl_")
    if not a.log:
        print("Toggle Airplane Mode ON then OFF now (forces SIM re-registration)...")
        capture_syslog(a.seconds, tmp)
    res = scan(tmp)
    print(c(f"\nSubscription {a.subscription}", "b"))
    print(f"  Resolved bundle : {c(res['resolved'] or 'not observed in this window', 'g' if res['resolved'] else 'y')}")
    print(f"  getSupportsNG   : {res['supports_ng']}")
    print(f"  log lines       : {res['lines']}  (source: {tmp})")
    print(f"  markers         : " + ", ".join(f"{k}={v}" for k, v in res['hits'].items()))

# ---- verify ------------------------------------------------------------------
def cmd_verify(a):
    if not a.log:
        sys.exit(c("verify needs a captured log: --log <file>  (or run `status`/`bind` first)", "r"))
    res = scan(a.log)
    print(c("Verification", "b"))
    ok = True
    for k in ("BindingEvaluator", "kResolvedPath", "kOverlayBundle", "kOverrideBundleSuccess"):
        seen = res["hits"][k] > 0
        ok &= seen
        print(f"  {k:<24}: {c('observed', 'g') if seen else c('not seen', 'y')}")
    print(f"  Resolved bundle         : {res['resolved'] or '?'}")
    print(f"  getSupportsNG           : {res['supports_ng']}")
    if a.bundle and res["resolved"]:
        want = a.bundle if a.bundle.endswith(".bundle") else a.bundle + ".bundle"
        good = res["resolved"].lower() == want.lower()
        print(f"\n  RESULT: {c(res['resolved'] + ' ACTIVE', 'g') if good else c('target NOT active (got ' + res['resolved'] + ')', 'r')}")

# ---- bind / reset (honest) ---------------------------------------------------
BIND_EXPLANATION = """\
NOTE: iOS 27 exposes NO command (USB/XPC/Darwin) to force a specific carrier bundle.
CommCenter binds a bundle purely by matching the SIM's PLMN (MCC+MNC) against each
bundle's carrier.plist -> SupportedSIMs. To bind CarrierLab.bundle you must present a
SIM whose PLMN is in its SupportedSIMs (e.g. 001/01 test network), then re-evaluate.
This tool drives that legitimate path and verifies the outcome from the device log.
"""
CARRIERLAB_PLMNS = ["001/01", "001/011", "246/08", "311/011", "262/80", "262/84"]

def cmd_bind(a):
    tmp = a.log or tempfile.mktemp(suffix=".jsonl", prefix="carrierctl_bind_")
    if (a.bundle or "").lower() in ("auto", "reset"):
        return cmd_reset(a)
    print(c(BIND_EXPLANATION, "y"))
    print(c(f"Target: {a.bundle}.bundle for subscription {a.subscription}", "b"))
    if a.bundle.lower() == "carrierlab":
        print("  Required: active SIM PLMN in one of: " + ", ".join(CARRIERLAB_PLMNS) + " ...")
    print("\nStep 1: ensure the matching SIM is in the slot.")
    print("Step 2: toggle Airplane Mode ON->OFF (triggers CommCenter re-evaluation).")
    if not a.yes:
        try:
            input("Press Enter once you've toggled Airplane Mode (Ctrl-C to abort)... ")
        except KeyboardInterrupt:
            sys.exit("\naborted")
    capture_syslog(a.seconds, tmp)
    a.log = tmp
    cmd_verify(a)

def cmd_reset(a):
    print(c(f"Reset subscription {a.subscription} to automatic (operator) binding", "b"))
    print("Insert the normal operator SIM and toggle Airplane Mode ON->OFF.")
    print("CommCenter will re-run BindingEvaluator and resolve the operator bundle by SIM PLMN.")
    print(c("(There is no privileged 'reset' call reachable over USB; this is the supported path.)", "y"))
    if a.verify_after:
        tmp = tempfile.mktemp(suffix=".jsonl", prefix="carrierctl_reset_")
        if not a.yes:
            input("Press Enter after toggling Airplane Mode to verify... ")
        capture_syslog(a.seconds, tmp)
        a.log = tmp; a.bundle = None
        cmd_verify(a)

# ---- argparse ----------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(prog="carrierctl", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("device").set_defaults(func=cmd_device)

    for name, fn in (("status", cmd_status), ("bind", cmd_bind), ("reset", cmd_reset), ("verify", cmd_verify)):
        sp = sub.add_parser(name)
        sp.add_argument("--subscription", type=int, default=1)
        sp.add_argument("--seconds", type=int, default=25, help="log capture window")
        sp.add_argument("--log", help="use/observe this captured log file instead of capturing")
        sp.add_argument("--yes", action="store_true", help="non-interactive (no Enter prompts)")
        if name in ("bind", "verify"):
            sp.add_argument("--bundle", help="target bundle, e.g. CarrierLab (or 'auto' to reset)")
        if name == "reset":
            sp.add_argument("--bundle", help=argparse.SUPPRESS)
            sp.add_argument("--verify-after", action="store_true")
        sp.set_defaults(func=fn)

    a = p.parse_args()
    a.func(a)

if __name__ == "__main__":
    main()
