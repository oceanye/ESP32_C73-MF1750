# MF-1750 application layer

The complete accepted driver, device HTTP, and loopback application API
contract is documented in [`docs/MF1750_DRIVER_API.md`](../../docs/MF1750_DRIVER_API.md).

The legacy in-process path accepts decoded, tightly packed RGB/RGBA rasters,
normalizes them to 1024x600, delegates six-colour conversion to
`host.color_pipeline`, and revalidates output with `host.epd_frame`. Application
v2 instead accepts the original PNG, JPEG, or WebP bytes. The server recomputes
their SHA-256 before state mutation, verifies the declared media type, applies
EXIF orientation and explicit rotation, converts an embedded ICC profile to
sRGB (or records an explicit sRGB assumption for an untagged source), and uses
Pillow LANCZOS normalization. The browser does not normalize or quantize v2
input. Neither path applies controller mapping, mirroring, flipping, or nibble
compensation.

## G1/S1 monitor simulation

The v2 UI exposes ten algorithm IDs:

1. five canonical C2 baselines: `none`, `floyd-steinberg`, `atkinson`,
   `ordered-bayer-8x8`, and `hashed-threshold`;
2. one explicitly legacy nearest-two comparison: `blue-noise`, which uses a
   nearest-two CIEDE2000 ratio and is not six-colour G1 area mixing;
3. four G1/S1 paths: `area-weighted-ordered-8x8`,
   `area-weighted-blue-noise`, `multicolor-dbs`, and `overlap-aware-dbs`.

Each successful v2 conversion publishes four report-hash-bound PNG previews:

- `source`: server-decoded and normalized source;
- `mapped`: continuous G1 mapped target;
- `final`: strict rendering rebuilt from the emitted physical six-code stream;
- `model`: the uncalibrated overlapping observation-model simulation.

Preview byte lengths and SHA-256 values are bound into the report; the browser
verifies each downloaded PNG's SHA-256 before display. These are monitor soft
proofs, not panel measurements.

Every v2 artifact is deliberately `offline_verified=true`,
`formal_upload_authorized=false`, `protocol_verified=false`, and
`hardware_tested=false`, including when a calibrated palette happens to be
loaded. The v2 UI keeps arm and refresh unavailable, and device enqueue rejects
the offline-only artifact; it cannot be promoted merely by relabelling a
synthetic profile. A future true-screen G1/S1 path requires a separate
qualification gate with measured palette/mixture characterization, qualified
optical kernels, panel/waveform/temperature binding, and the existing device
preflight and one-shot safety authorization. The calibrated legacy C2 formal
path remains a separate contract.

The default `OfflineAdapter` cannot make network requests. The optional
`HttpDeviceAdapter` requires an explicit root URL, connection permission, an
exact one-shot arm phrase, a calibrated-palette `ApplicationArtifact`, and two
explicit controller mappings. The preflight and short-lived arm are bound to
the immutable application-report/frame identity and those mappings; replacing
an artifact revokes all previous authorization and protocol evidence. Its
protocol checks reuse
`tools.mf1750_frame_tool`; HTTP 202 remains only a queued state and success is
not reported until the final job and diagnostic operation evidence match.
Local abort is not remote cancellation.  Once `/api/frame` may have been sent,
the adapter latches the unresolved job before I/O and keeps new submissions
quarantined after local tracking is discarded.  A matching terminal job closes
only the remote-activity uncertainty; matching diagnostic and safe-finish
evidence are still required for a normal unlock.  This quarantine is currently
process-local, so an application restart requires manual device-idle and
safe-finish verification.
The adapter enforces a method/route allowlist for `/api/version`, safe frame
ingress, `/api/frame`, `/api/job`, and `/api/diagnostic/report`; legacy solid,
white, black, and test routes cannot be requested through this API. Device URLs
with credentials, paths, queries, or fragments are rejected. This skeleton does
not persist credentials. The loopback Web server generates a new high-entropy
process token at each start, prints it only in the URL fragment, and requires it
on every application API request. Strict numeric Host and same-origin checks
keep the token/session boundary separate from the unauthenticated ESP32 API.

Pillow remains optional for decoded-raster and synthetic in-process use. The v2
original-file Web UI path requires Pillow with ImageCms support on the server.

Run the offline UI service:

```powershell
python -m app.server
```

Open the exact fragment-bearing URL printed by the process. The browser moves
the token into same-origin `sessionStorage` and removes it from the visible URL;
arbitrary static or API GET responses never disclose it.

Enabling a device still sends no startup request:

```powershell
python -m app.server --enable-device --device-url http://DEVICE-IP
```

The browser must then explicitly allow connection and separately arm refresh.
The default reference palette is uncalibrated, so it can create labelled
offline previews but cannot enable formal refresh. The ESP32 firmware API still
has no device-side authentication and must remain on a trusted isolated network.

## N6 real-browser safety harness

`n6_browser_campaign` compiles a convert-v2 artifact into an offline-only N6
manifest tied to the shared P0 fixed-action identity and workspace-global claim
declaration. It has no claim writer, device requester, retry, recovery, or
authorization generator. Missing measured palette/profile evidence is emitted
as an explicit blocker and the description always remains non-executable.

The real Playwright suite uses locally installed Chromium plus ephemeral
numeric-loopback application and fake-device servers. It exercises original
file upload, four preview hashes, contain/cover geometry, stale artifacts,
reload, token/origin rejection, and the current unqualified-device boundary.
See
[`docs/N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md`](../../docs/N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md)
for the exact tested counts and remaining hardware gates.

The production-physical continuation lives in `n6_physical_execution`. It
requires a physical panel/build binding, authenticated authority/profile and
runtime evidence, and a complete N5 physical palette reconstructed from the
raw observations and finalized strict-RC2G results. The only operator surface
is `tools/mf1750_n6_physical_once.py`; the older
`tools/mf1750_n6_visible_once.py serve` path is hard-blocked before claim or
network I/O. Production execution uses an exact atomic claim store and exact
one-shot HTTP driver, durably commits the receipt and sidecar before returning
success to the browser, and records a fixed per-claim terminal incident if a
post-claim outcome cannot be proved. This software closure remains
`NOT HARDWARE-EXECUTED` until the external evidence and one-action authorization
exist.
