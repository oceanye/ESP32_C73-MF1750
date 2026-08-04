# MF-1750 host colour pipeline

This package converts decoded RGB or straight-alpha RGBA rasters into the
canonical row-major MF-1750 4bpp frame. It has no third-party dependencies and
never accesses GPIO, HTTP endpoints, firmware, or panel hardware.

```python
from host.color_pipeline import RasterImage, load_palette, quantize_panel_image

image = RasterImage(1024, 600, "RGBA", decoded_rgba_bytes)
measured_palette = load_palette("mf1750_measured_d65_2deg.json")
result = quantize_panel_image(image, palette=measured_palette)
raw_frame = result.frame                 # exactly 307200 bytes
preview_png = result.preview_png()       # deterministic decoded RGB pixels
report = result.report.to_dict()         # usage, hashes, provenance
```

The bundled `reference-srgb-v1` palette is deliberately marked
`calibrated=false`. Its Lab values are mathematical sRGB/D65 anchors for
offline tests, not MF-1750 measurements. For panel work, copy the JSON shape,
replace all six Lab patches with controlled measurements, record provenance,
and set `calibrated=true` only after measurement.

Physical names are not editable labels. Every palette is rejected unless it
binds `0=black`, `1=white`, `2=yellow`, `3=red`, `5=blue`, and `6=green`.
Setting `calibrated=true` cannot override this check. Coarse Lab semantics are
also enforced: black L* must be below white L*, red a* above green a*, and
yellow b* above blue b*. This catches name-preserving Lab swaps without
pretending to replace real panel calibration.

Palette JSON uses schema v2. An uncalibrated palette must use
`"calibration": null`. A calibrated palette must include an auditable artifact
reference:

```json
"calibrated": true,
"calibration": {
  "measurement_id": "mf1750-d65-run-2026-08-04",
  "artifact_sha256": "<exactly 64 hexadecimal digits>"
}
```

Small-raster `quantize_image()` calls may use the bundled reference palette for
offline regression and algorithm exploration. Both `quantize_panel_image()`
and a direct panel-sized `quantize_image()` call reject an uncalibrated palette
by default. A controlled experiment may opt in explicitly:

```python
result = quantize_panel_image(
    image,
    allow_uncalibrated_palette=True,  # recorded; not production calibration
)
```

Any noncanonical dimensions that would nevertheless pack to the panel's exact
307200-byte frame size are rejected. For example, `2048x300` and `512x1200`
cannot be used to bypass the canonical `1024x600` authorization boundary.

Report schema v2 records the SHA256 of the exact decoded, tightly packed input
pixel bytes, RGB/RGBA mode and dimensions, straight-alpha handling and white
linear-light background, IEC sRGB transfer function, all effective conversion
options, palette provenance, and a static pipeline version/build identifier.
It also records whether an uncalibrated panel-sized conversion was explicitly
authorized. The raster SHA256 does not include dimensions or mode; those are
separate mandatory report fields.

The caller declaration in the report says that input bytes are assumed to be
decoded 8-bit IEC sRGB and RGBA alpha is straight. Palette and report canonical
SHA256 values have explicit scopes. They are reproducibility/audit fingerprints
only, not digital signatures and not trust-store approvals.

Available modes are nearest colour, Floyd-Steinberg, Atkinson, ordered Bayer
8x8, and seeded hashed thresholding. The hash mode is deterministic stochastic
thresholding; it is not claimed to be blue noise. White protection prevents
near-white neutral backgrounds from receiving coloured dots. Edge protection
blocks error diffusion into detected high-contrast boundaries. Text mode is an
explicit black/white luminance threshold mode.

Preview RGB values are presentation metadata only. Quantization distances use
the configured Lab values and CIEDE2000; diffusion uses those Lab values
projected to clamped linear sRGB.

The PNG encoder is byte-deterministic for a fixed Python/zlib runtime. The
portable regression contract is the decoded RGB content and valid chunk CRCs,
not the compressed IDAT byte stream across different zlib versions.
