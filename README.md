# CarrierBundleLab

Service-first Python toolkit for laboratory work with iOS carrier bundles on owned USB-connected devices.
It includes bundle inspection, compatibility resolution, transaction journaling, verified backups,
manifest diffing, constrained transport interfaces, CommCenter binding verification, recovery, and a
minimal GUI shell backed by the same services as the CLI.

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

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## CLI

```bash
carrierlab device list
carrierlab device info --udid <UDID>
carrierlab carrier state --udid <UDID>
carrierlab bundle inspect FILE
carrierlab bundle check FILE --udid <UDID>
carrierlab transport probe --udid <UDID>
carrierlab carrier install FILE --udid <UDID> --dry-run
carrierlab carrier install FILE --udid <UDID>
carrierlab carrier verify --log commcenter.jsonl --expected CarrierLab.bundle
carrierlab carrier restore --udid <UDID>
carrierlab transaction recover <TRANSACTION_ID> --udid <UDID>
```

`COMMITTED` requires a verified backup, a matching readback, and CommCenter `kOverrideBundleSuccess`. A resolved path alone stays `OBSERVED` / `WAITING`. When more than one iPhone is connected, pass `--udid`.

For local orchestration tests without an iPhone, set:

```bash
export CARRIERLAB_MOCK_TREE=/path/to/local/carrier-tree
export CARRIERLAB_MOCK_UDID=mock-udid
```

The real AirTraffic backend currently fails closed until a verified project-specific transport is
plugged in. The code deliberately does **not** expose arbitrary protected-path writing.

## Tests

```bash
python -m pytest -q
```

## Not included

Apple-proprietary artifacts are intentionally excluded (see `.gitignore`): the IPSW, the
copied `CommCenter`/`CommCenterMobileHelper` binaries, and the raw strings dumps. The repo
contains only original analysis and code.
