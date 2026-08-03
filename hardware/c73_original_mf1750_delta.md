# DESPI-C73 Original vs MF-1750 Adaptation Delta

This note is the source-of-truth comparison for a DESPI-C73-based MF-1750 /
M009F-T adaptation. The intended hardware change is not a full driver redesign:
reuse the DESPI-C73 high-voltage and panel-support circuitry, isolate the
incompatible connector pins, and add the missing second chip select.

Reference files checked:

- `参考资料/DESPI-C73-SCH-20251014_01.png`
- `参考资料/DESPI-C73-SCH-20251014.pdf`
- `hardware/despi_c73_mf1750_pinmap.csv`
- `hardware/mf1750_full_driver_kicad/mf1750_fpc_pinmap.csv`

## Conclusion

DESPI-C73 P1 is already very close to the MF-1750 50-pin panel pinout. The
critical change is:

- DESPI-C73 P1 pin 4 = `VDD`
- MF-1750 pin 4 = `SL_CSB`

Therefore, an adapter based on C73 must not connect host P1 pin 4 to panel pin
4. Panel pin 4 must instead go to a new `SL_CSB` / `CS2` input from the ESP32,
with a weak pull-up to `VDDIO` or `3V3`.

## Pin-Level Delta

| Pin | DESPI-C73 P1 original | MF-1750 target | C73-based adapter action |
| --- | --- | --- | --- |
| 1 | `VPP`, marked NC in C73 schematic | `NC` | Leave panel pin 1 unconnected; do not pass C73 `VPP` through |
| 2 | `TFT_VCOM` | `TFT_VCOM` | Pass through |
| 3 | `FPL_VCOM` | `FPL_VCOM` | Pass through |
| 4 | `VDD` | `SL_CSB` | Do not pass through; route panel pin 4 to new `CS2/SL_CSB` header |
| 5 | `GDRH` | `GDRH` | Pass through |
| 6 | `RESEH` | `RESEH` | Pass through |
| 7 | `GDRL`, marked NC in C73 schematic | `GDRL` | Keep same C73 behavior unless panel reference proves it must be driven |
| 8 | `RESEL` | `RESEL` | Pass through; do not replace with a hard GND tie on an interposer |
| 9 | `GDRC` | `GDRC` | Pass through |
| 10 | `RESEC` | `RESEC` | Pass through |
| 11 | `VPC` | `VPC` | Pass through |
| 12 | `GND` | `GND` | Pass through |
| 13 | `VGL` / `PREVGL` rail | `VGL` / `PREVGL` | Pass through; name alias only |
| 14 | `VPH` | `VPH` | Pass through |
| 15-23 | source/reference rails | same rails | Pass through |
| 24 | `TSCL` | `TSCL` | Keep C73 behavior; optional pull-up only if reference/bring-up requires |
| 25 | `TSDA`, marked NC in C73 schematic | `TSDA` | Keep same C73 behavior unless cascade reference requires it |
| 26 | `BS0` | `BS0` | Keep C73 mode strap behavior |
| 27 | `BS1` | `BS1` | Keep C73 mode strap behavior |
| 28 | `RST_N` / `RES` | `RST_N` | Pass through |
| 29 | `BUSY_N` / `BUSY` | `BUSY_N` | Pass through |
| 30 | `DC` / `D/C` | `DC` | Pass through |
| 31 | `CSB1` / `CS` | `CSB` | Pass through as the main chip select |
| 32 | `SCL` / `SCLK` | `SCL` | Pass through |
| 33 | `SI0` / `SDI` | `SI0` | Pass through |
| 34-36 | `SI1`/`SI2`/`SI3`, marked NC in C73 schematic | reserved for non-4-wire modes | Keep same C73 behavior |
| 37-48 | logic and charge-pump pins | same pins | Pass through |
| 49 | `VGH` / `PREVGH` rail | `VGH` / `PREVGH` | Pass through; name alias only |
| 50 | `VCOMBD` | `VCOMBD` | Pass through |

## What The C73-Based Board Should Contain

- `J_HOST`: 50-pin connector/cable from DESPI-C73 P1.
- `J_PANEL`: 50-pin connector to the MF-1750 panel.
- Straight-through routing for all compatible pins.
- Host pin 4 isolated and clearly marked `C73_P1_4_VDD_DO_NOT_CONNECT_TO_PANEL4`.
- Panel pin 4 routed to `H_CS2` / `SL_CSB`.
- Optional weak pull-up from `SL_CSB` to `VDDIO` or `3V3`.
- Optional test pads for `CSB`, `SL_CSB`, `GND`, and `VDDIO`.

## What It Should Not Do

- Do not redesign the boost/negative-pump/VPC high-voltage circuitry if the
  board is meant to be based on DESPI-C73.
- Do not tie MF-1750 pin 4 to C73 P1 pin 4.
- Do not hard-change C73 mode or analog pins unless a verified panel reference
  requires it.
- Do not treat the `mf1750_full_driver_kicad` project as the C73 interposer;
  that project is a full reference-driver draft.
