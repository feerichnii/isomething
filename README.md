# isomething — iOS 27 carrier-bundle binding research

Reverse-engineering of how iOS 27 (iPhone14,7 / build 24A437) selects a carrier bundle,
and an honest `carrierctl` tool to observe/verify binding over USB from a Mac.

## Key result

Carrier binding is **not** a settable property. `CommCenter` picks a bundle by matching the
active SIM's PLMN (MCC+MNC) against each installed bundle's `carrier.plist → SupportedSIMs`,
writes `BundleLinks` (`kResolvedPath`), generates an overlay (`kOverlayBundle`), and reports
`kOverrideBundleSuccess`.

There is **no** USB / lockdown / Darwin-notification API to force a specific bundle.
`CarrierLab.bundle` binds only when the SIM presents one of its declared PLMNs (chiefly
`001/01`, the reserved test network used with a base-station simulator). See
[`research/FINDINGS.md`](research/FINDINGS.md) and
[`research/bundlelinks_callflow.md`](research/bundlelinks_callflow.md).

## carrierctl

```bash
pip install -U pymobiledevice3
python3 carrierctl/carrierctl.py device
python3 carrierctl/carrierctl.py status --subscription 1
python3 carrierctl/carrierctl.py verify --log <captured.jsonl> --bundle CarrierLab
```

`bind` / `reset` drive the only legitimate path (present matching SIM → trigger
re-evaluation via Airplane-mode toggle → verify from the device log). They do **not**
fabricate a "force" that iOS does not expose.

## Not included

Apple-proprietary artifacts are intentionally excluded (see `.gitignore`): the IPSW, the
copied `CommCenter`/`CommCenterMobileHelper` binaries, and the raw strings dumps. The repo
contains only original analysis and code.
