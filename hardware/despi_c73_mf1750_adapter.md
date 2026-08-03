# DESPI-C73 to MF-1750/M009F-T Adapter PCB Notes

## Goal

Build a small FPC interposer board so the existing DESPI-C73 high-voltage
driver can still be used, while exposing the MF-1750 panel's second chip
select signal:

- MF-1750 pin 31: `CSB` -> DESPI-C73 `CSB1`
- MF-1750 pin 4: `SL_CSB` -> new ESP32 GPIO, recommended `GPIO10`

The board should not redesign the e-paper high-voltage driver. It should only
remap the 50-pin FPC signals and add one external control input for `SL_CSB`.
See `c73_original_mf1750_delta.md` for the pin-by-pin comparison against the
DESPI-C73 original schematic.

## Why This Is Needed

The DESPI-C73 schematic exposes only one SPI chip-select on the MCU connector:

| DESPI-C73 P2 pin | Signal |
| --- | --- |
| 1 | `3V3` |
| 2 | `GND` |
| 3 | `SDI` |
| 4 | `SCLK` |
| 5 | `CS` |
| 6 | `D/C` |
| 7 | `RES` |
| 8 | `BUSY` |

On the 50-pin side, DESPI-C73 P1 is already close to the MF-1750 panel pinout.
The critical incompatibility is pin 4: DESPI-C73 pin 4 is `VDD`, but the
MF-1750 panel expects pin 4 to be `SL_CSB`. Directly connecting an ESP32 GPIO
to DESPI-C73 P1 pin 4 is dangerous unless the `VDD` trace is physically
isolated first.

## Recommended PCB Topology

Use an interposer between DESPI-C73 and the panel:

```text
ESP32 P2 wiring -> DESPI-C73 -> 50-pin FFC cable -> adapter PCB -> MF-1750 FPC
                                                        |
                                                        +-- SL_CSB header -> ESP32 GPIO10
```

Recommended connector approach:

- `J_HOST`: 50-pin, 0.5 mm pitch FFC/FPC connector for a short FFC cable from DESPI-C73.
- `J_PANEL`: 50-pin, 0.5 mm pitch FPC connector for the MF-1750 panel flex.
- `H_CS2`: 2-pin or 3-pin header for `SL_CSB`, `GND`, optional `3V3/VDDIO`.

Before layout, confirm:

- FPC pitch is 0.5 mm.
- Contact side/orientation of DESPI-C73 connector.
- Contact side/orientation of MF-1750 panel flex.
- Whether the panel flex inserts with contacts up or contacts down.

## Critical Signal Mapping

Do not connect DESPI-C73 P1 pin 4 to MF-1750 pin 4. All compatible C73 P1
signals should otherwise remain pass-through so the adapter remains a C73-based
pin-4 correction, not a new driver board.

| MF-1750 pin | MF-1750 signal | Adapter source |
| --- | --- | --- |
| 1 | `NC` | Leave unconnected |
| 2 | `TFT_VCOM` | DESPI-C73 P1 pin 2 |
| 3 | `FPL_VCOM` | DESPI-C73 P1 pin 3 |
| 4 | `SL_CSB` | New header `H_CS2`, ESP32 `GPIO10`; add pull-up to `VDDIO` |
| 5 | `GDRH` | DESPI-C73 P1 pin 5 |
| 6 | `RESEH` | DESPI-C73 P1 pin 6 |
| 7 | `GDRL` | DESPI-C73 P1 pin 7 |
| 8 | `RESEL` | DESPI-C73 P1 pin 8 `RESEL`; pass through |
| 9 | `GDRC` | DESPI-C73 P1 pin 9 |
| 10 | `RESEC` | DESPI-C73 P1 pin 10 |
| 11 | `VPC` | DESPI-C73 P1 pin 11 |
| 12 | `GND` | DESPI-C73 ground |
| 13 | `VGL` | DESPI-C73 P1 pin 13 `PREVGL` |
| 14 | `VPH` | DESPI-C73 P1 pin 14 |
| 15-23 | Power/reference pins | DESPI-C73 P1 pins 15-23 |
| 24 | `TSCL` | DESPI-C73 P1 pin 24 `TSCL`; keep C73 behavior |
| 25 | `TSDA` | DESPI-C73 P1 pin 25 `TSDA`; C73 schematic marks this node NC |
| 26 | `BS0` | DESPI-C73 P1 pin 26 `BS0`; keep C73 mode strap behavior |
| 27 | `BS1` | DESPI-C73 P1 pin 27 `BS1`; keep C73 mode strap behavior |
| 28 | `RST_N` | DESPI-C73 P1 pin 28 |
| 29 | `BUSY_N` | DESPI-C73 P1 pin 29 |
| 30 | `DC` | DESPI-C73 P1 pin 30 |
| 31 | `CSB` | DESPI-C73 P1 pin 31 `CSB1` |
| 32 | `SCL` | DESPI-C73 P1 pin 32 |
| 33 | `SI0` | DESPI-C73 P1 pin 33 |
| 34-36 | `SI1`/`SI2`/`SI3` | Keep C73 behavior; C73 schematic marks these nodes NC |
| 37-50 | Power/charge-pump pins | DESPI-C73 P1 pins 37-50 |

## Added Parts

Recommended additions on the adapter:

| Ref | Value | Purpose |
| --- | --- | --- |
| `R_SL` | 47 kOhm to 100 kOhm | Pull `SL_CSB` high to `VDDIO` when ESP32 is reset |
| `H_CS2` | 2.54 mm header or test pad | `SL_CSB` to ESP32 `GPIO10` plus `GND` |

Do not add TSCL/TSDA pull-ups or BS0/BS1 mode jumpers by default on the C73
interposer. Preserve the original C73 strap behavior unless a measured bring-up
issue requires a controlled ECO.

## Firmware Change After Hardware Is Ready

After `SL_CSB` is wired to ESP32 `GPIO10`, set:

```cpp
static constexpr int EPD_PIN_CS2 = 10;
```

in `src/epd_config.h`.

Then use the normal full-screen split-frame path. The firmware already supports
two controller chip-selects.

## Information Still Needed Before Final PCB Layout

Provide clear photos or part numbers for:

- DESPI-C73 50-pin connector contact side.
- MF-1750 flex cable contact side.
- Whether the DESPI-C73 connector is top-contact or bottom-contact.
- Desired physical adapter shape and cable exit direction.
- Preferred fabrication method: 2-layer rigid PCB with FFC cable, or thin 0.3 mm
  PCB edge-finger interposer.
