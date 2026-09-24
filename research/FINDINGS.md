# Carrier Bundle Binding on iOS 27 (iPhone14,7 / 24A437) — Reverse-Engineering Findings

Scope: static analysis of the mounted system filesystem
`/private/tmp/043-68793-657.dmg.mount` and the extracted binaries
`CommCenter` and `CommCenterMobileHelper`
(`/System/Library/Frameworks/CoreTelephony.framework/Support/`).

---

## TL;DR (answer to §47 "the main research question")

There is **no** iOS system call, XPC verb, Mach message, or Darwin notification whose
argument is "use `CarrierLab.bundle` for subscription N".

Carrier binding is **not a settable property**. It is a **pure function of the SIM's
identity** (PLMN = MCC+MNC, plus GID1/GID2 and MVNO/GSMA attributes), evaluated by
`CommCenter`. The evaluator matches the SIM against every bundle's
`carrier.plist → SupportedSIMs` and picks the best match. The result is written to the
`BundleLinks` slots (`kResolvedPath`) and an overlay is generated (`kOverlayBundle`),
ending in `kOverrideBundleSuccess`.

`CarrierLab.bundle` is bound **iff** the active SIM presents one of the PLMNs it declares
in `SupportedSIMs` (chiefly `001/01`, the reserved test network). See the exact list below.

Consequently:

* The only way to make `BindingEvaluator` resolve to `CarrierLab` is to present a SIM whose
  PLMN is in `CarrierLab.bundle`'s `SupportedSIMs` (a test SIM on a base-station simulator —
  literally an "Carrier Lab" setup). Then the **normal** re-evaluation triggered by SIM
  insertion / Airplane-mode toggle selects it automatically — no override is needed or exists.
* The write verbs that do exist (`Install` = IPCC, `Reset`, OTA update) are gated behind
  Apple-private entitlements and are **not exposed through any lockdown/USB service**.

Therefore **Acceptance Criteria §43 (force binding to CarrierLab from a Mac over USB, without
IPCC and without a matching SIM) is not achievable on a non-jailbroken device.** It would
require code running on-device with Apple-only entitlements — i.e. a jailbreak or an exploit,
which is explicitly out of scope.

---

## §42 Acceptance Criteria №1 — the 10 required answers

### 1. Where "BindingEvaluator" is implemented
There is no symbol literally named `BindingEvaluator`. The evaluation logic lives **inside the
`CommCenter` daemon** (not `CommCenterMobileHelper`, not a separate framework, not the DSC — all
the relevant strings resolve inside the `CommCenter` Mach-O). It is the carrier-bundle matching
subsystem exposed via the internal `CarrierBundleXpcServer` / `CarrierBundleHandler` C++ classes.
Key result keys (all present in `CommCenter`):
`kMatchingCriteria`, `kBundleMatchResult`, `kMatchedPath`, `kResolvedPath`, `kLinkingPath`,
`matching_bundle_name`, `resolved_bundle_name`.

### 2. Who calls it
It is invoked internally by `CommCenter` on **SIM / carrier-context change events**, not by any
external client. Confirmed log strings:
* `User data SIM has changed from %s to %s, re-evaluating state (change type: %s)`
* `re-evaluating carrier bundle for %s`
* `re-evaluating carrier bundle for [%s] for bundleInfo change [%s]`
* `re-evaluate on carrier bundle change event %s`
* `QS carrier context changed, reevaluating`  (QS = Quick Switch)
* `Checking for already-enrolled slots after carrier context binding`

### 3. Where kResolvedPath is formed
In the bundle-matching routine of `CommCenter`, alongside `Resolved path        : ` (human log)
and the machine key `kResolvedPath` / `resolved_bundle_name`. It is the winning `carrier.plist`
path after matching the SIM's `mcc`/`mnc`/`supportedSims` against each installed bundle. The
resolved path is then linked into the `BundleLinks` slots
(`kDefaultBundle`, `kOperatorBundle`, `kCarrier1CountryBundle`, `kCarrier2Bundle`, `kBootstrapBundle`, …).

### 4. Who creates kOverlayBundle
`CommCenter`'s overlay generator, after resolution. Given the resolved bundle + device/SIM class,
it selects an overlay flavour and writes an overlay file:
* Flavours: `kNoOverlay`, `kDeviceOverlay`, `kMultimodeOverlay`, `kMVNOOverlay`, `kGSMAOverlay`,
  `kMvnoGsmaOverlay`, `kDeviceMVNOMultimodeGSMAOverlay`, … (chosen from SIM/device type, **not** user input)
* IO: `OverlayBundle request` / `OverlayBundle response`, `overlay_file_name`, `CBOverlay`,
  failure = `commCenterBundleOverlayFileWriteFailure` / `OverlayWriteFailure`.

### 5. What kOverrideBundleSuccess means
The terminal status of the overlay/override write step: the computed overlay was successfully
materialised for the resolved bundle. Sibling = `kOverrideBundleFailure`. It reports that the
override overlay file was written, **not** that a user chose a bundle.

### 6. What object holds the selected carrier bundle
The `BundleLinks` slot set (per subscription/SIM slot): symlink/link entries keyed by
`kDefaultBundle`, `kOperatorBundle`, `kCarrier1CountryBundle`, `kOperator1CountryBundle`,
`kCarrier2Bundle`, `kOperator2Bundle`, `kBootstrapBundle`, `kDefaultBootstrapBundle`, each with
`kBundleIdentifier`, `kBundleVersion`, `kResolvedPath`, `kLinkingPath`, `kPrefFile`,
`kBundleTechnologyType`. This lives under the data partition's `Carrier Bundles/BundleLinks`.

### 7. Is there an API to change the bundle
The carrier-bundle XPC surface (`CarrierBundleXpcServer`, service
`com.apple.commcenter.mobile-helper-cbupdateservice` / `com.apple.commcenter.carrierspace.xpc`)
exposes only these triggers — **none of them is "select/force bundle X"**:
* `kCarrierBundleTriggerInstallCarrierBundle`  → `CarrierBundleHandler::installCarrierBundle_sync(CFURL, …)`  — this is the **IPCC install** path (takes a URL to a bundle to add).
* `kCarrierBundleTriggerResetCarrierBundle` / `kResetBundleMatches` — reset to auto.
* `kCarrierBundleTriggerGetUpdatedCarrierBundle`, `kCarrierBundleGetRemoteBundleInfo` — OTA update.
* `kCarrierBundleSetOTAServerOverrideUrl` / `…Get…` — point OTA at another server.
* `kCarrierBundleModifyAttachAPNSettings` / `…Get…` — tweak attach APN only.

`setTestBundleIdForSlice:` exists but is for **network slicing**, not carrier bundles.
Selection itself is implicit: install a bundle + present a matching SIM ⇒ it wins.

### 8. What the subscription identifier looks like
Internally the unit is the **SIM slot / data-SIM context**, not ICCID/IMSI:
`kSimSlot`, "User data SIM", `QuickSwitchCarrierContext` / `QuickSwitchCarrierManager`
(`ctu::rest`), `BasicSimInfo`, `sims_on_device`. The matching inputs are `carrierMCC`,
`carrierMNC`, `isoMcc`, `supportedSims`, GID. CoreTelephony public identity is
`CTServiceDescriptor` (slot 1 / slot 2). So "Subscription 1" = physical/data SIM slot 1.

### 9. How refresh / re-evaluation is triggered
By radio/SIM state transitions inside `CommCenter` (SIM insert/remove, carrier-context change,
Airplane-mode toggle → SIM re-registration). There is **no public "re-evaluate now" notification**;
the daemon's launchd `LaunchEvents` only listen for
`com.apple.ManagedConfiguration.profileListChanged` and `com.apple.purplebuddy.setupdone`.
The practical external trigger is toggling Airplane mode (re-reads the SIM ⇒ re-evaluation).

### 10. Can it be called from a Mac (USB)
**No.** All carrier services are on-device Mach/XPC services
(`com.apple.commcenter.carrierspace.xpc`, `com.apple.commcenter.coretelephony.xpc`,
`com.apple.commcenter.mobile-helper-cbupdateservice`), gated by entitlements
`com.apple.private.security.storage.CarrierBundles`, `com.apple.CommCenter.fine-grained`
(`spi`,`internal`,`carrier-settings`), `com.apple.commcenter.mobile-helper-xpc.allow`,
`com.apple.carrierspace.control.allow`, `com.apple.private.mobileinstall.allowedSPI`.
`/System/Library/Lockdown/Services.plist` exposes **no** carrier/telephony/CommCenter service,
so nothing bridges these to USB. A Mac tool cannot obtain these entitlements without jailbreak.

---

## §47 Result card

```
Function/API:
    CommCenter carrier-bundle matching subsystem (CarrierBundleHandler /
    CarrierBundleXpcServer). Selection verb: NONE. Nearest write verbs:
    kCarrierBundleTriggerInstallCarrierBundle (= IPCC install, takes CFURL),
    kCarrierBundleTriggerResetCarrierBundle (= reset to auto).

Process:
    CommCenter  (/System/Library/Frameworks/CoreTelephony.framework/Support/CommCenter)
    (CommCenterMobileHelper only proxies mobile-side helpers; matching lives in CommCenter)

Service:
    com.apple.commcenter.mobile-helper-cbupdateservice  (Mach, on-device)
    com.apple.commcenter.carrierspace.xpc               (Mach, on-device)

Transport:
    Mach / XPC, on-device only. NOT a Darwin notification. NOT a lockdown service.

Arguments:
    Install: CFURL to a signed bundle (IPCC).  Reset: slot.
    Selection is NOT parameterised by a target bundle name.

Required entitlement:
    com.apple.private.security.storage.CarrierBundles
    com.apple.CommCenter.fine-grained = {spi, internal, carrier-settings}
    com.apple.commcenter.mobile-helper-xpc.allow
    com.apple.carrierspace.control.allow
    com.apple.private.mobileinstall.allowedSPI

Can be called through USB:
    NO. No lockdown service bridges it; entitlements unobtainable off-device.

Trigger (the real mechanism):
    Present a SIM whose PLMN (MCC+MNC) is listed in
    CarrierLab.bundle/carrier.plist -> SupportedSIMs, then let CommCenter
    re-evaluate (SIM insert or Airplane-mode toggle). No override call exists.

Verification:
    kResolvedPath -> .../CarrierLab.bundle  (only when the SIM PLMN matches)
    kOverlayBundle written -> kOverrideBundleSuccess
```

---

## CarrierLab.bundle selection rule (the actual "how to get it bound")

`CarrierLab.bundle/carrier.plist → SupportedSIMs` (MCC+MNC PLMNs that bind this bundle):

```
00101  00281  001011 00102 00111 00211 00321 00431 00541 00651 00761 00871
00902  01012  01122  01232 10101 24608 246081 24681 246813 311011 29981
26280  26284  262820 240681 240680
```

`00101` = **MCC 001 / MNC 01 = the reserved 3GPP test network** (used with an Amarisoft/
base-station simulator in an actual carrier lab). Insert a programmable test SIM set to one of
these PLMNs (or camp on a test network broadcasting it) and CommCenter binds `CarrierLab.bundle`
automatically. `CarrierName = "Carrier Lab"`, and it turns on `Enable5GStandaloneByDefault`,
`SupportsVoNR`, etc.

There is nothing to "command from the Mac" — the SIM identity is the command.

---

## Why steps 17–19 (dyld_shared_cache extraction) were skipped
All target symbols (`kResolvedPath`, `kOverlayBundle`, `kOverrideBundleSuccess`,
`copyCarrierBundleValue…`, the overlay flavours, the XPC triggers) are present **directly in the
`CommCenter` Mach-O**. Extracting the ~12 GB DSC would add nothing. If deeper disassembly of the
matcher is wanted, disassemble `CommCenter` around `CarrierBundleHandler` /
`CarrierBundleXpcServer` symbols.
