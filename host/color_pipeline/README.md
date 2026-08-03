# MF-1750 host colour pipeline

This package converts decoded RGB or straight-alpha RGBA rasters into the
canonical row-major MF-1750 4bpp frame. It has no third-party dependencies and
never accesses GPIO, HTTP endpoints, firmware, or panel hardware.

```python
from host.color_pipeline import RasterImage, quantize_panel_image

image = RasterImage(1024, 600, "RGBA", decoded_rgba_bytes)
result = quantize_panel_image(image)
raw_frame = result.frame                 # exactly 307200 bytes
preview_png = result.preview_png()       # deterministic decoded RGB pixels
report = result.report.to_dict()         # usage, hashes, provenance
```

The bundled `reference-srgb-v1` palette is deliberately marked
`calibrated=false`. Its Lab values are mathematical sRGB/D65 anchors for
offline tests, not MF-1750 measurements. For panel work, copy the JSON shape,
replace all six Lab patches with controlled measurements, record provenance,
and set `calibrated=true` only after measurement.

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
