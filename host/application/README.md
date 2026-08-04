# MF-1750 application layer

The complete accepted driver, device HTTP, and loopback application API
contract is documented in [`docs/MF1750_DRIVER_API.md`](../../docs/MF1750_DRIVER_API.md).

This package accepts decoded, tightly packed RGB/RGBA rasters, normalizes them
to 1024x600, delegates all six-colour conversion to `host.color_pipeline`, and
revalidates output with `host.epd_frame`. It never applies controller mapping,
mirroring, flipping, or nibble compensation.

The default `OfflineAdapter` cannot make network requests. The optional
`HttpDeviceAdapter` requires an explicit root URL, connection permission, an
exact one-shot arm phrase, a calibrated-palette `ApplicationArtifact`, and two
explicit controller mappings. The preflight and short-lived arm are bound to
the immutable application-report/frame identity and those mappings; replacing
an artifact revokes all previous authorization and protocol evidence. Its
protocol checks reuse
`tools.mf1750_frame_tool`; HTTP 202 remains only a queued state and success is
not reported until the final job and diagnostic operation evidence match.
The adapter enforces a method/route allowlist for `/api/version`, safe frame
ingress, `/api/frame`, `/api/job`, and `/api/diagnostic/report`; legacy solid,
white, black, and test routes cannot be requested through this API. Device URLs
with credentials, paths, queries, or fragments are rejected. This skeleton does
not persist credentials. The loopback Web server generates a new high-entropy
process token at each start, prints it only in the URL fragment, and requires it
on every application API request. Strict numeric Host and same-origin checks
keep the token/session boundary separate from the unauthenticated ESP32 API.

Pillow is optional and used only by `PillowImageDecoder`. Synthetic rasters and
the browser UI need no Pillow installation.

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
