# MF-1750 DevKitC Compact Carrier Rev B0

Independent engineering revision; the verified Rev A1 manufacturing handoff is
unchanged.

- 62 x 58 mm, 2 layers, 1.6 mm FR-4, Top-side SMT.
- Socketed ESP32-S3-DevKitC-1 N16R8, rotated 90 degrees.  USB overhangs the
  left edge and the WROOM PCB antenna overhangs the right edge.
- J2 uses Espressif's official 2x22, 22.86 mm row-spacing footprint geometry.
- GPIO mapping is identical to the tested firmware: BUSY=4, RST=5, DC=6,
  CS1=7, CS2=10, MOSI=11, SCK=12.
- R16 is fitted and R15 is DNP.  Never fit both.
- Both DevKitC 3V3 header pins are deliberately isolated on the carrier.
  J3 pin 1 is the current-limited external EPD 3V3 input and J3 pin 2 is GND;
  fitted R4/R8 feed EPD_3V3 and V_B. USB powers only the DevKitC. TP1/TP2 are
  measurement pads and must not carry the panel supply cable.
- Power sequence for B0: connect USB first, then enable the current-limited
  J3 panel supply. Disable J3 before removing USB. While J3 is off, firmware
  must keep all seven cross-domain GPIOs as inputs/high impedance with no
  sourcing pulls; this sequence alone does not provide Ioff isolation. Add
  Ioff-rated buffers in a future revision if independent sequencing is required.
- The MF-1750 high-voltage parts and packages remain the Rev A1 set; no
  unmeasured inductor/capacitor downsizing is hidden in this layout.
- The antenna end has an explicit all-copper/all-track keepout; do not place
  metal, battery, display frame, cable or enclosure hardware over it.
- Use two 1x22 stacking sockets with at least 11 mm board-to-board clearance;
  validate the actual N16R8 underside height, tail-pin size, and antenna
  position first.  The placeholder socket has 0.80 mm finished holes and must
  not be released until a selected socket manufacturer's drill recommendation
  is substituted and checked.

## Current verification

- Routing is complete with dual-layer GND pours, partial/discontinuous local
  3V3 copper relief, explicit antenna/edge rule areas, and selected widened
  converter paths.  The 3V3 relief is two filled islands, not a continuous
  J3-to-R4/R8 bus.  Dense `/3V3`, `/EPD_3V3`, and `/V_B` distribution still
  contains 0.20 mm necks; this is a known B0 power-integrity limitation and is
  not electrically equivalent to Rev A1.
- KiCad 10.0.3: ERC 0 errors / 0 warnings; DRC 0 violations; 0 unconnected;
  schematic parity 0 footprint errors.  See `erc_final.rpt` and `drc_final.rpt`.
- Canonical files are `mf1750_devkitc_compact.kicad_sch` and
  `mf1750_devkitc_compact.kicad_pcb`; previews are `preview/final_top.png` and
  `preview/final_bottom.png`.  `bom_reference.csv` is the full engineering BOM.
  `verification_manifest.json` is the authoritative hash-bound artifact list;
  files not listed there are intermediate evidence, not manufacturing inputs.
- Rebuild order: generator -> Freerouting 2.2.4 (`-mp 600 -mt 1 -da
  --gui.enabled=false`) -> importer -> finalizer -> fresh ERC/DRC with
  schematic parity -> final top/bottom renders.  The finalizer is
  `../finalize_mf1750_devkitc_compact.py`; run
  `../verify_mf1750_devkitc_compact.py` with KiCad's bundled Python for the
  final gates and renders.  A new route is not authoritative until that script
  passes.  The generator writes `unrouted_source.kicad_pcb` and
  `README.provisional.md`; it deliberately cannot overwrite this verified
  canonical PCB or this handoff README.

The validated routing run used Freerouting `2.2.4`, one routing thread, up to
600 passes, and the exact arguments recorded in
`freerouting-user22/freerouting.log`.  A reroute is nondeterministic and may
change the coordinate-selected local reinforcements, so the importer and
finalizer must abort on identity/count drift and the final verifier must pass
again before its result can replace the canonical board.

This B0 remains an engineering prototype, not a production release.  Before
ordering, measure the actual N16R8 socket/USB/antenna Z-envelope and connector
access against the intended enclosure.  Provide enclosure support below the
lower board edge; the two upper mounting holes do not carry connector insertion
loads by themselves.  First article must use current limit,
rail/current/temperature monitoring and the physical cut-off; confirm all MF-
1750 rails before attaching the panel.  Software checks do not qualify the
high-voltage stage or the panel electrically.
