# BundleLinks call-flow (reconstructed from CommCenter strings)

```
SIM inserted / Airplane-mode OFF / carrier-context change
        │   ("User data SIM has changed from %s to %s, re-evaluating state")
        ▼
CommCenter: re-evaluate carrier bundle
        │   ("re-evaluating carrier bundle for [%s] for bundleInfo change [%s]")
        ▼
Matcher (CarrierBundleHandler)
        │   inputs: carrierMCC, carrierMNC, isoMcc, GID, wireless technology (kWirelessTechnology),
        │           kSimSlot ; compared against every installed bundle's
        │           carrier.plist -> SupportedSIMs
        ▼
kBundleMatchResult / kMatchingCriteria
        │   winner -> matching_bundle_name, kMatchedPath
        ▼
kResolvedPath   ("Resolved path        : <...>.bundle")
        │   resolved_bundle_name, carrier_plist_name
        ▼
Write BundleLinks slots (per slot):
        kDefaultBundle / kOperatorBundle / kCarrier1CountryBundle /
        kCarrier2Bundle / kOperator2Bundle / kBootstrapBundle / kDefaultBootstrapBundle
        each: kBundleIdentifier, kBundleVersion, kResolvedPath, kLinkingPath, kPrefFile
        ▼
Overlay generator
        │   pick flavour from SIM/device class:
        │   kNoOverlay | kDeviceOverlay | kMultimodeOverlay | kMVNOOverlay | kGSMAOverlay | ...
        │   ("OverlayBundle request" -> "OverlayBundle response")
        ▼
kOverlayBundle written (overlay_file_name, CBOverlay)
        ▼
kOverrideBundleSuccess        (else kOverrideBundleFailure / OverlayWriteFailure)
```

## The XPC surface (CarrierBundleXpcServer) — write verbs only
- kCarrierBundleTriggerInstallCarrierBundle  -> installCarrierBundle_sync(CFURL)   [IPCC add]
- kCarrierBundleTriggerResetCarrierBundle / kResetBundleMatches                     [reset to auto]
- kCarrierBundleTriggerGetUpdatedCarrierBundle / kCarrierBundleGetRemoteBundleInfo  [OTA update]
- kCarrierBundleSetOTAServerOverrideUrl / ...Get...                                 [OTA server]
- kCarrierBundleModifyAttachAPNSettings / ...Get...                                 [attach APN]

No "select/force/bind bundle X" verb exists. Selection = (installed bundle) x (matching SIM PLMN).

## Read surface (safe, could be reachable if a proxy existed)
- copyCarrierBundleValue:key:bundleType:completion:
- copyCarrierBundleValueWithCountryBundleLookup:keyHierarchy:matchingInfo:completion:
  (these READ values from the currently-resolved bundle; they do not change binding)
```
