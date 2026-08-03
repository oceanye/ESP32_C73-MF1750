# DESPI-C73 to MF-1750 Pin-4 Interposer

This KiCad project is the C73-based adaptation path. It preserves the original
DESPI-C73 high-voltage driver and 50-pin panel support circuitry.

Status: schematic import package for JLC/KiCad review. KiCad ERC is clean in
`erc.rpt`; still verify connector contact side and pin-1 orientation before PCB
layout or fabrication.

Intentional differences from DESPI-C73:

- C73 P1 pin 1 `VPP` is not passed to MF-1750 pin 1 `NC`.
- C73 P1 pin 4 `VDD` is not passed to MF-1750 pin 4.
- MF-1750 pin 4 `SL_CSB` is routed to `H_CS2` for a second ESP32 chip-select.
- `R_SL` is an optional weak pull-up from `SL_CSB` to `VDDIO`.

Everything else is pass-through unless the C73 original already leaves that
node unconnected internally.

See also:

- `../c73_original_mf1750_delta.md`
- `../despi_c73_mf1750_pinmap.csv`
