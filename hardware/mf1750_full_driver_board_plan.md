# MF-1750/M009F-T Full 50-pin Driver Board Plan

## Objective

Modify or recreate a DESPI-C73-like driver board so it directly supports the
Ink Cubic MF-1750 / M009F-T 7.50 inch 1024x600 panel.

This is no longer an interposer design. The 50-pin FPC connector on the board
must follow the MF-1750 panel pinout directly.

## Required Source Files

Preferred:

- Altium: `.PrjPcb`, `.SchDoc`, `.PcbDoc`, integrated libraries if any.
- KiCad: `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, custom footprint libraries.
- EasyEDA: project JSON/source export.

Usable but slower:

- Gerber + drill + schematic PDF. This can be used to recreate the board, but
  cannot be safely "edited" like a source PCB project.

Not enough by itself:

- Schematic PDF only.
- JPG/PNG only.

## Main Electrical Difference From DESPI-C73

DESPI-C73 is not pin-compatible with MF-1750 on the 50-pin FPC connector.

The most important conflict:

| FPC pin | DESPI-C73 meaning | MF-1750 meaning |
| --- | --- | --- |
| 4 | `VDD` | `SL_CSB` |

Therefore the new full board must not reuse the DESPI-C73 50-pin pinout
unchanged.

## MCU Connector

Use a 9-pin or 10-pin MCU connector. Keep the old DESPI-C73 signals, but add
the second chip select.

Recommended 10-pin connector:

| Pin | Signal | ESP32-S3 suggested GPIO |
| --- | --- | --- |
| 1 | `3V3` | 3.3 V |
| 2 | `GND` | GND |
| 3 | `SDI/SI0` | GPIO11 |
| 4 | `SCLK/SCL` | GPIO12 |
| 5 | `CSB` | GPIO7 |
| 6 | `SL_CSB` | GPIO10 |
| 7 | `D/C` | GPIO6 |
| 8 | `RST_N` | GPIO5 |
| 9 | `BUSY_N` | GPIO4 |
| 10 | `VDDIO` or `NC` | optional |

If physical compatibility with the old 8-pin C73 cable is desired, keep the old
8-pin connector and add a separate one-pin/two-pin `SL_CSB` header.

## MF-1750 50-pin FPC Mapping

The final board's FPC connector must use the MF-1750 pinout:

| Pin | Signal | Board connection |
| --- | --- | --- |
| 1 | `NC` | No connect |
| 2 | `TFT_VCOM` | TFT VCOM circuit |
| 3 | `FPL_VCOM` | FPL VCOM circuit |
| 4 | `SL_CSB` | MCU `SL_CSB`, add pull-up to `VDDIO` |
| 5 | `GDRH` | N-channel MOSFET gate drive circuit |
| 6 | `RESEH` | current sense high-side |
| 7 | `GDRL` | reserved or per reference circuit |
| 8 | `RESEL` | ground per reference circuit |
| 9 | `GDRC` | P-channel MOSFET gate drive circuit |
| 10 | `RESEC` | current sense common |
| 11 | `VPC` | VPC charge pump output |
| 12 | `GND` | ground |
| 13 | `VGL` | negative gate drive |
| 14 | `VPH` | positive high-voltage supply |
| 15 | `VSH` | positive source drive |
| 16 | `VSH_LV` | positive source drive |
| 17 | `VSH_LV2` | positive source drive |
| 18 | `VSL` | negative source drive |
| 19 | `VSL_LV` | negative source drive |
| 20 | `VSL_LV2` | negative source drive |
| 21 | `GNDA` | ground |
| 22 | `REFN` | reference network |
| 23 | `REFP` | reference network |
| 24 | `TSCL` | cascade signal, pull-up to `VDDIO` |
| 25 | `TSDA` | cascade signal, pull-up to `VDDIO` |
| 26 | `BS0` | default for selected SPI mode; use solder jumper |
| 27 | `BS1` | default for selected SPI mode; use solder jumper |
| 28 | `RST_N` | MCU reset signal |
| 29 | `BUSY_N` | MCU busy input |
| 30 | `DC` | MCU D/C signal |
| 31 | `CSB` | MCU main chip select |
| 32 | `SCL` | MCU SPI clock |
| 33 | `SI0` | MCU SPI MOSI |
| 34 | `SI1` | optional/reserved for current firmware |
| 35 | `SI2` | optional/reserved for current firmware |
| 36 | `SI3` | optional/reserved for current firmware |
| 37 | `VDDD` | core logic power |
| 38 | `VDD` | panel supply |
| 39 | `GND` | ground |
| 40 | `VDDIO` | logic I/O supply |
| 41 | `VCP2` | charge pump |
| 42 | `CP2N` | charge pump |
| 43 | `CP2P` | charge pump |
| 44 | `VCP1` | charge pump |
| 45 | `CP1N` | charge pump |
| 46 | `CP1P` | charge pump |
| 47 | `CGH1N` | charge pump/reserved |
| 48 | `CGH1P` | charge pump/reserved |
| 49 | `VGH` | positive gate drive |
| 50 | `VCOMBD` | VCOMBD drive |

## SPI Mode Selection

The current firmware uses 4-wire SPI with a real `D/C` pin. Per the MF-1750
interface table, default the board to this mode and provide solder jumpers for
experiments.

Recommended:

- `BS0`: default low through 0-ohm/solder jumper to `GND`.
- `BS1`: default low through 0-ohm/solder jumper to `GND`.
- Add optional alternate pads to pull either signal to `VDDIO`.

Do not hardwire `BS0/BS1` in a way that prevents debugging other SPI modes.

## Pull-ups and Protection

Recommended additions:

| Signal | Component | Purpose |
| --- | --- | --- |
| `CSB` | 47 kOhm to `VDDIO` | deselect panel during ESP32 boot |
| `SL_CSB` | 47 kOhm to `VDDIO` | deselect second controller during ESP32 boot |
| `RST_N` | 47 kOhm to `VDDIO` | keep panel out of reset unless MCU drives it |
| `TSCL` | 10 kOhm to 47 kOhm to `VDDIO` | datasheet says cascade signal needs pull-up |
| `TSDA` | 10 kOhm to 47 kOhm to `VDDIO` | datasheet says cascade signal needs pull-up |
| `BUSY_N` | optional series 100 Ohm | input protection/damping |
| SPI lines | optional series 22-100 Ohm | edge damping if cable is long |

## Firmware Setting For The New Board

After the full board exposes both chip-selects:

```cpp
static constexpr int EPD_PIN_CS = 7;
static constexpr int EPD_PIN_CS2 = 10;
```

No other firmware change should be required for split full-screen tests.

## PCB Review Checklist

Before ordering boards, verify:

- FPC connector pitch and pin-1 orientation match the MF-1750 flex cable.
- No DESPI-C73 `VDD` net is connected to MF-1750 pin 4.
- `SL_CSB` has its own MCU net and pull-up.
- `CSB` and `SL_CSB` are not shorted together.
- All high-voltage charge-pump pins follow MF-1750 pin numbers, not the old
  DESPI-C73 pin numbers.
- `VDD`, `VDDIO`, and ESP32 GPIO levels are all 3.3 V compatible.
- Creepage/spacing around high-voltage pump nets is preserved from C73.
- Board has test pads for `CSB`, `SL_CSB`, `SCL`, `SI0`, `DC`, `RST_N`,
  `BUSY_N`, `VDD`, `VDDIO`, `GND`.

