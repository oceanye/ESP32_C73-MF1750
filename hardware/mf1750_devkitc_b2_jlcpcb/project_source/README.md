# MF1750 + ESP32-S3-DevKitC carrier — Rev B2 PCBA edge-margin candidate

B2 is a reproducible, non-destructive derivative of the frozen verified B1
board.  Existing components, pads, tracks, vias, drawings, and connectivity are
moved rigidly by `(+0.5, +2.5) mm`.  The finished board is enlarged from
62 x 58 mm to 65 x 60.5 mm.  Only the board outline, the three GND-zone
outlines, four edge rule areas, antenna keepout extent, and revision identity
are subsequently rewritten.  One J2 `ANTENNA` mechanical label retains its
exact position but is changed from F.SilkS to F.Fab: after enlarging the board,
the formerly fully off-board text intersected the new edge and became clipped
fabricated silkscreen.  No copper, mask, paste, body, courtyard, or placement
geometry is changed by that cleanup.

Rebuild and verify with KiCad 10's bundled Python:

```powershell
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware\build_mf1750_devkitc_b2_pcba_margin.py
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware\verify_mf1750_devkitc_b2_pcba_margin.py
```

The local JLCPCB handoff gate requires the generic board audit to pass at
`body_edge >= 2.5 mm` and `courtyard_edge >= 2.5 mm`, in addition to clean ERC,
strict DRC with schematic parity, zero unconnected pads, frozen-source hashes,
and the project-specific topology verifier.  This does not constitute portal
or factory acceptance.

Mechanical holds remain for the FPC/J1 cable exit, side-entry J3, the extended
FR4 under/near the DevKitC antenna, J2 socket/hole/Z-envelope fit, and enclosure
or mounting clearances.  These require physical review before release.
