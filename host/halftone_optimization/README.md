# S1 offline halftone optimization

This package implements the software-only S1 baseline without importing the
application device adapter:

- deterministic void-and-cluster ranked blue-noise threshold tiles;
- deterministic six-colour area-weighted Bayer 8x8 assignment;
- preferred six-channel area-weighted blue-noise assignment using a strict
  `(0, 1, 2, 3, 5, 6)` non-negative/sum-to-one weight contract;
- a clearly labelled legacy nearest-two CIEDE2000 blue-noise baseline;
- six-mask overlap-aware convolution with per-colour kernels;
- 3x3, 7x7 and 15x15 overlapping visual losses plus edge, direction,
  periodicity and same-colour-cluster terms;
- bounded multicolour DBS with single-pixel recolours, nearby pair swaps,
  deterministic seeds, evaluation/accepted/stagnation/time budgets,
  cooperative cancellation and canonical reports.

## Application algorithm paths

The application exposes ten explicit paths.  They are intentionally separated
so a nearest-two comparison cannot be mistaken for a six-colour G1 mixture:

| Group | Application ID | Implemented path |
| --- | --- | --- |
| canonical C2 baseline | `none` | nearest palette colour, no dither |
| canonical C2 baseline | `floyd-steinberg` | Floyd-Steinberg error diffusion |
| canonical C2 baseline | `atkinson` | Atkinson error diffusion |
| canonical C2 baseline | `ordered-bayer-8x8` | legacy C2 nearest-two Bayer threshold |
| canonical C2 baseline | `hashed-threshold` | legacy seeded nearest-two threshold |
| legacy S1 comparison | `blue-noise` | nearest-two CIEDE2000 ratio plus void-and-cluster threshold; **not** G1 area mixing |
| G1/S1 | `area-weighted-ordered-8x8` | G1 six-colour area weights plus deterministic Bayer inverse-CDF assignment |
| G1/S1 | `area-weighted-blue-noise` | G1 six-colour area weights plus six decorrelated void-and-cluster channels |
| G1/S1 | `multicolor-dbs` | G1 mapped continuous target plus bounded six-colour DBS with the identity observation model |
| G1/S1 | `overlap-aware-dbs` | G1 mapped continuous target plus bounded multiscale DBS with the simulated overlap model |

The four G1/S1 rows are the new mixing/optimization paths.  The standalone
`blue-noise` row remains a deliberately labelled legacy nearest-two baseline.
All S1 paths consume the canonical C2 protection-constraint mask, so protected
white, edge and text-mode pixels remain fixed and the mask identity is recorded
in their reports.

All outputs contain only the six physical codes.  The default Gaussian model,
all previews and all metrics are `simulation_only`, `hardware_tested=false`
and `hardware_qualified=false`.  No function in this package accesses a serial
port, network device or refresh endpoint.

The preferred G1/S1 bridge is:

```python
weighted = quantize_area_weighted_blue_noise(
    width,
    height,
    flat_six_colour_weights,
    solver_id="g1-area-weight-solver-id",
)
optimized = optimize_multicolor_dbs(image, weighted.codes)
```

`quantize_blue_noise(image)` remains available only as a legacy comparison.
Its report explicitly records that nearest-two Delta E ratios were used and
must not be interpreted as physical six-colour mixing weights.

Through application v2 these algorithms produce four monitor views:
server-normalized source, continuous G1 mapped target, final rendering rebuilt
from the physical six-code stream, and the simulated overlapping observation
model.  This integration is always offline-only with
`formal_upload_authorized=false`; none of these monitor results qualifies a
real panel.  True-screen use requires a separate measured/calibrated and
hardware-qualified gate, including qualified mixture/observation evidence and
the normal device safety workflow.

DBS initialization is a fixed number of linear image passes.  Search work is
strictly capped by `DBSOptions.max_evaluations`; callers can additionally use a
time limit and a `cancel_check` callback.  Pure Python local-move cost is
proportional to the observation-kernel support multiplied by
`3^2 + 7^2 + 15^2`; it does not scale with the full image area after
initialization.
