# MF-1750 Full Driver KiCad Reference Draft

This project is a KiCad 10 schematic-first reverse model of the MF-1750 /
M009F-T reference circuit.

Generated files:

- `mf1750_jlc_simplified.kicad_pro`
- `mf1750_jlc_simplified.kicad_sch`
- `mf1750_jlc_simplified.kicad_pcb` semi-auto placement draft with all footprints
- `bom_reference.csv`
- `mf1750_fpc_pinmap.csv`
- `mf1750_jlc_simplified_pcb_preview.svg` can be generated separately by KiCad CLI
  for quick placement review.

Important hardware conclusion:

- MF-1750 pin 4 is `SL_CSB`.
- MF-1750 pin 31 is `CSB`.
- MF-1750 pin 1 is treated as true `NC` from the I/O table and mechanical
  pin map, even though the page-10 reference drawing labels the connector side
  as `VPP`.
- DESPI-C73 ties its 50-pin pin 4 position differently, so it cannot drive the
  second SPD1657B controller on this 1024x600 cascade panel.
- Seeed EE04 is useful as a 50-pin 0.5 mm connector/layout reference, but its
  KiCad source leaves `J1-4` unconnected and has only one `SPI0_CS`; the
  generated MF-1750 PCB deliberately overrides that mapping with `SL_CSB`.
- The new board must route both `CSB` and `SL_CSB` to ESP32 GPIOs.
- Reserved pins `GDRL`, `SI1`, `SI2`, `SI3`, `CGH1N`, and `CGH1P` have no
  extra test pads in this simplified JLC import version.
- Diode polarity is assigned in `bom_reference.csv`: D1 pad1/K=VPH and
  pad2/A=SW_H; D2 pad1/K=NEG_PUMP_H and pad2/A=GND; D3
  pad1/K=NEG_PUMP_H and pad2/A=PREVGL; D4 pad1/K=SW_C and pad2/A=VPC.
- MOSFET footprints assume SOT-23 pinout 1=G, 2=S, 3=D.
- Current default footprints: resistors 0603 except R1/R3 as 1206, capacitors
  per reference package sizes, diodes SOD-123, inductors 7.3x7.3 mm, MOSFETs
  SOT-23-3.

Before fabrication:

- Re-check J1 FPC orientation/contact side with the real panel tail.
- Panel tail requirement from the mechanical drawing: 50 pins, 0.5 mm pitch,
  exposed finger width about 24.5 mm, stiffener thickness about 0.30 mm.
- J1 footprint geometry is based on the Seeed EE04 50-pin connector when the
  official EE04 KiCad source is present locally; otherwise generation falls
  back to a stock KiCad 50-pin 0.5 mm FPC footprint.
- For installation certainty, either use a dual-contact 50-pin 0.5 mm FPC
  connector, or copy the exact contact-side orientation from the working
  DESPI-C73 connector.
- Verify all assigned footprints against JLC/LCSC orderable parts before
  fabrication, especially J1, Q1/Q2, D1-D4, L1/L2, R1/R3.
- Ensure diode footprint pad numbering matches the assigned anode/cathode nets.
- Keep the high-voltage pump layout compact and use suitable voltage ratings.
- Default 4-wire SPI mode is BS0=0 and BS1=0 with R12/R13 populated.
- The PCB is intentionally unrouted. The remaining DRC unconnected items are
  expected until KiCad/JLC routing is completed.
