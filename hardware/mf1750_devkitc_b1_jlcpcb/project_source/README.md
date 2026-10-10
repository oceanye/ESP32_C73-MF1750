# MF1750 + ESP32-S3-DevKitC compact carrier — Rev B1 4-layer engineering candidate

This directory is an independent four-layer derivative of the verified Rev B0
board.  It does not overwrite or modify Rev B0.  The outline remains 62 x 58 mm
and the socketed ESP32-S3-DevKitC-1 N16R8 topology remains unchanged.

## Layer contract

- F.Cu: components, existing signal routing, and short supply dog-bones.
- In1.Cu: one full-outline `/GND` zone; no tracks and no non-GND zone.  Solid
  pad connections and eight added return vias produce one continuous
  3205.48 mm2 filled copper outline.
- In2.Cu: all `/3V3`, `/EPD_3V3`, and `/V_B` distribution.
- B.Cu: existing signal routing, bottom test point dog-bone, and GND pour.

The supply buses are 0.60 mm `/3V3`, 0.60 mm `/EPD_3V3`, and 0.80 mm
`/V_B`.  The only narrower internal segment is the intentional 0.50 mm local
neck from R4.1.  Fifteen SMD endpoints use ordinary 0.60/0.30 mm plated
through vias and separated dog-bones.  Eight additional ordinary GND stitching
vias serve J3, the FPC return region and C2/C6/C22/C23; C0 already has a nearby
GND via.  There are no blind/buried/microvias and no via-in-pad.

The DevKit antenna and all board-edge rule areas cover all four copper layers.
F.Paste and B.Paste are explicitly enabled in the PCB layer table; the fitted
SMT population uses the generated top stencil, while the bottom stencil is
intentionally empty.
The two DevKit 3V3 header pins remain NC, so USB cannot power the EPD rails.
R16 remains FIT and R15 remains DNP.

## Verification status

- KiCad 10 strict PCB DRC: 0 violations, 0 unconnected pads.
- KiCad 10 schematic ERC: 0 errors, 0 warnings.
- `drc_refill_gate.rpt` repeats strict DRC/parity after a fresh zone refill and
  saves the exact audited board before the final report is generated.
- Structural audit: In1 has zero tracks and exactly one `/GND` plane; all
  supply distribution is on In2; all fifteen supply vias are ordinary through
  vias; all 75 board vias are ordinary through vias; all eight added GND return
  vias are position/diameter/drill checked; antenna keepout spans
  F.Cu/In1.Cu/In2.Cu/B.Cu.
- `design_audit.json` records the machine-readable layer/width/via contract.
- `verification_manifest.json` binds the final PCB/SCH/project, ERC/DRC,
  netlist, audit, README and two final previews by SHA-256.  Any other file in
  this directory is intermediate evidence, not a manufacturing input.

Rebuild with KiCad's bundled Python:

```powershell
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware\build_mf1750_devkitc_b1_single_power_layer.py
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware\verify_mf1750_devkitc_b1_single_power_layer.py
```

## Production hold points

This is still an engineering candidate, not a manufacturing release.  Before
Gerbers, select a fabricator-qualified four-layer 1.6 mm stack-up and confirm
the exact J2 socket MPN, 0.80 mm finished-hole compatibility, DevKit underside
and antenna/USB Z envelopes, J3/H1 mechanical clearance, lower mechanical
support, and exact FPC connector fit.  The external J3 power sequencing and
GPIO back-power precautions documented for Rev B0 still apply.
