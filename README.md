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
carrierlab device info
carrierlab sim info

carrierlab carrier state
carrierlab carrier list

carrierlab bundle inspect FILE
carrierlab bundle resolve

carrierlab transport probe

carrierlab carrier backup
carrierlab carrier plan FILE
carrierlab carrier install FILE --dry-run
carrierlab carrier install FILE
carrierlab carrier rescan
carrierlab carrier verify --log commcenter.jsonl --bundle CarrierLab
carrierlab carrier restore

carrierlab transaction list
carrierlab transaction show ID
carrierlab transaction recover ID
```

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
