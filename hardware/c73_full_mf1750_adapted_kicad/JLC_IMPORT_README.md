# JLC Import Notes

Import `c73_full_mf1750_adapted.kicad_pro` or the whole zip into JLC EDA
Professional as a KiCad project.

This is the full DESPI-C73-style circuit adapted for MF-1750. It is not the
50-pin-only interposer.

Critical adaptation:

- C73 original P1 pin 4 was `VDD`.
- In this schematic J1 pin 4 is `SL_CSB`.
- `SL_CSB` is exposed on J2 pin 9 as the second chip-select.
- C73 original P1 pin 1 `VPP` is not connected because MF-1750 pin 1 is `NC`.

Before PCB layout:

- Verify J1 contact side and pin-1 orientation against the real MF-1750 flex.
- Verify J2 wiring against your ESP32 board.
- Re-check D1-D4 diode polarity in the footprint library.
- Re-check BS0/BS1 strap default against the controller mode you will use.
- Check all footprints against JLC/LCSC availability.
