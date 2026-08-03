# MF-1750 Cascade Driver Rev A1

This directory is generated from `../generate_mf1750_production_v1.py`,
`../prepare_mf1750_freerouting_seed.py`, Freerouting 2.2.4, and
`../finalize_mf1750_freerouting.py`. The checked-in `production/` directory is
the verified manufacturing handoff; regeneration is only needed after edits.

Design baseline:

- MF-1750 / M009F-T A1 reference circuit, page 10.
- 80 mm x 75 mm, 2-layer, 1.6 mm FR-4, 1 oz copper.
- J1 is XUNPU FPC-05FB-50PH20 / C2856838 (50 pin, 0.5 mm, 0.3 mm,
  dual-contact). Its footprint is reconstructed from the official JLC land
  pattern and the manufacturer drawing. It is rotated so the cable exits the
  top board edge and panel pin 1 is at the PCB's left-hand PIN1 marker.
- Host pins 1..8 retain the DESPI-C73 order; pin 9 is optional CS2 and pin 10 is GND.
- R15 is fitted by default and links CSB to SL_CSB, matching the E2802 cascade
  board's J4 link. For independent CS2, remove R15 and fit R16. Never fit both.
- R12/R13 fix BS0=BS1=0 (4-wire SPI per the MF-1750 interface table).

Important first-article checks:

1. Confirm panel flex pin 1 against the board's PIN1 silkscreen before insertion.
2. Power the board from a current-limited 3.3 V supply; start at 100 mA.
3. Check VDD/VDDIO before allowing a refresh, then verify VPH/PREVGH/PREVGL/VPC.
4. Use the default R15 single-CS configuration first. Only test CS2 after the
   single-CS cascade path has been measured.
5. J2 is intentionally through-hole/manual assembly; all SMT DNP parts are
   excluded from the normal placement file.
6. Q1 uses the official Si1308EDL SC-70 pinout (1=G, 2=S, 3=D). Its
   specified 2.5 V RDS(on) is a documented deviation from one numerical limit
   in the A1 component note, so verify switching temperature on first articles.

`production/` is populated by the routing/export script with Gerber, drill,
BOM, CPL, reports, and an order checklist.
