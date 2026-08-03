# EPDiy Hardware Reference Assessment

This note records how the local `epdiy-hardware` clone should be used for the
MF-1750 / M009F-T full 50-pin driver board work.

Local clone:

```text
hardware/reference_epdiy_hardware
```

## Useful Reference Projects

| Path | Use |
| --- | --- |
| `hardware/reference_epdiy_hardware/epdiy-v7-raw` | ESP32-S3 controller-board organization, KiCad project structure, BOM/export conventions |
| `hardware/reference_epdiy_hardware/versions/v7-kaleido-34` | Full controller-board layout reference and fabrication package organization |
| `hardware/reference_epdiy_hardware/adapters/40_to_WP27D-P050VA3` | Small FPC adapter-board layout style, connector pin-1 marking, simple routing style |
| `hardware/reference_epdiy_hardware/adapters/40_to_EPSON40` | Additional FPC-to-FPC adapter example |

## What Can Be Reused

- KiCad project organization: local symbols, local footprints, fabrication outputs,
  README/BOM style.
- PCB layout conventions: board edge, FPC keepout, pin-1 marker, silkscreen warnings,
  test pad placement, connector-to-connector routing strategy.
- Manufacturing workflow references: JLC-oriented BOM and placement file examples.

## What Must Not Be Copied Directly

- The EPDiy display interface is mostly raw/parallel e-paper oriented, while MF-1750
  is an SPI 6-color panel with two SPD1657 controllers.
- EPDiy uses different panel pinouts. Its nets must not be mapped blindly to MF-1750.
- The EPDiy `WP27D-S050VA3` 50-pin footprint is 0.35 mm pitch. MF-1750 mechanical
  notes require 50 pins, 0.5 mm pitch. Keep the current 0.5 mm FPC footprint unless
  the real panel tail measurement proves otherwise.
- EPDiy power architecture includes PMIC-based raw-panel supplies in some variants.
  MF-1750 should continue to follow the MF-1750 reference circuit / DESPI-C73 style
  discrete charge-pump rails unless a panel vendor confirms an alternate design.

## Current MF-1750 Board Direction

The active draft remains:

```text
hardware/mf1750_jlc_simplified_kicad
```

Critical MF-1750 connections:

```text
J1 pin 4  SL_CSB -> ESP32 second chip select, recommended GPIO10
J1 pin 31 CSB    -> ESP32 main chip select, current GPIO7
```

The board should not reuse the DESPI-C73 50-pin pinout because DESPI-C73 uses
`P1 pin 4 = VDD`, while MF-1750 uses `pin 4 = SL_CSB`.

## Next PCB Tasks

1. Keep `J1` as a 50-pin 0.5 mm FPC connector and verify the exact contact side
   against the real MF-1750 tail.
2. Use the EPDiy adapter boards only as mechanical/layout references for FPC
   placement, pin-1 marking, board edge, and DRC-clean routing style.
3. Place the high-voltage charge-pump parts close to the corresponding FPC pins
   following the MF-1750 reference circuit, not the EPDiy PMIC circuit.
4. Keep `CSB` and `SL_CSB` separated and add pull-ups to `VDDIO/3V3`.
5. Add clear silkscreen labels: `PIN1`, `CSB`, `SL_CSB`, `VERIFY CONTACT SIDE`.
6. Before fabrication, run ERC/DRC and then manually inspect:
   `J1-4`, `J1-31`, `VDD`, `VDDIO`, `GND`, `VPH`, `PREVGH`, `PREVGL`, and `VCOM`.

