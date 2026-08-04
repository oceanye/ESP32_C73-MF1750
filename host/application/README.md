# MF-1750 application layer

This package accepts decoded, tightly packed RGB/RGBA rasters, normalizes them
to 1024x600, delegates all six-colour conversion to `host.color_pipeline`, and
revalidates output with `host.epd_frame`. It never applies controller mapping,
mirroring, flipping, or nibble compensation.

The default `OfflineAdapter` cannot make network requests. The optional
`HttpDeviceAdapter` requires an explicit root URL, connection permission, an
exact one-shot arm phrase, a calibrated-palette `ApplicationArtifact`, and two
explicit controller mappings. Its protocol checks reuse
`tools.mf1750_frame_tool`; HTTP 202 remains only a queued state and success is
not reported until the final job and diagnostic operation evidence match.
The adapter enforces a method/route allowlist for `/api/version`, safe frame
ingress, `/api/frame`, `/api/job`, and `/api/diagnostic/report`; legacy solid,
white, black, and test routes cannot be requested through this API. Device URLs
with credentials, paths, queries, or fragments are rejected. This skeleton does
not accept or persist tokens.

Pillow is optional and used only by `PillowImageDecoder`. Synthetic rasters and
the browser UI need no Pillow installation.

Run the offline UI service:

```powershell
python -m app.server
```

Enabling a device still sends no startup request:

```powershell
python -m app.server --enable-device --device-url http://DEVICE-IP
```

The browser must then explicitly allow connection and separately arm refresh.
The default reference palette is uncalibrated, so it can create labelled
offline previews but cannot enable formal refresh.
