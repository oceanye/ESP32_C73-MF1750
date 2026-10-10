# MF-1750 G1 gamut mapping

This package is the software-only pre-dither layer between a normalized
`RasterImage` and the existing C2 six-colour quantizer. It has no serial,
network, firmware, waveform or panel-refresh code.

```python
from host.color_pipeline import PipelineOptions, quantize_image, reference_palette
from host.gamut_mapping import (
    MappingOptions,
    build_synthetic_reference_profile,
    build_three_stage_preview,
    map_raster,
)

palette = reference_palette()
profile = build_synthetic_reference_profile(palette)
mapped = map_raster(
    source_raster,
    palette=palette,
    profile=profile,
    options=MappingOptions(intent="photographic", strength=1.0),
    allow_unqualified_simulation=True,
)
quantized = quantize_image(
    mapped.mapped_image,
    palette=palette,
    options=PipelineOptions(dither="atkinson"),
)
proof = build_three_stage_preview(mapped, quantized)
```

`mapped.mapped_image` is the application-facing C2 input. The result also
provides original/mapped RGB bytes and PNGs, a deterministic Q16 linear-sRGB
mapped-raster identity, compression statistics and a strict report. The three
stage artifact binds the original preview, continuous mapped preview, and a
final preview rendered from the actual C2 code stream.

Supported intent names are `relative-colorimetric`, `perceptual`, and
`saturation`; the UI-oriented aliases are `faithful`, `photographic`, and
`vivid`. `MappingOptions(mode="none")` and `mode="legacy"` return the exact
original raster mode and bytes.

The bundled builder uses the uncalibrated reference palette and a first-order
3-D XYZ convex hull. It therefore requires
`allow_unqualified_simulation=True`, reports `simulation=true`, keeps hardware
qualification and formal upload false, and is suitable only for monitor
experiments. The JSON fingerprint is not a signature.

`AreaWeightSolver` exposes deterministic non-negative six-code weights for a
mapped Lab target. The 2x2 default precomputes 126 recipes for inexpensive
per-pixel/cache use; 4x4 precomputes 20,349 recipes for offline higher-resolution
search. Its objective reports separate CIEDE2000, L*, chroma, hue, grain and
colour-count terms. It does not claim that an XYZ area average is measured
panel behaviour.

Real-panel use remains blocked until a calibrated palette and controlled
mixture characterization are supplied and separately trusted. Monitor PNGs
cannot reproduce reflective colour, ambient light, viewing geometry, texture,
ghosting, transition history or waveform behaviour.
