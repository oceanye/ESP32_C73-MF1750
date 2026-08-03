# JLC Import Notes

Import this package as a KiCad schematic/project in JLC EDA Professional.

Use this project when the goal is a DESPI-C73-based interposer:

- Keep the DESPI-C73 high-voltage driver.
- Pass through compatible 50-pin signals.
- Do not connect C73 P1 pin 1 `VPP` to MF-1750 pin 1 `NC`.
- Do not connect C73 P1 pin 4 `VDD` to MF-1750 pin 4.
- Route MF-1750 pin 4 `SL_CSB` to `H_CS2`.

After import, check:

- `J_HOST` contact side and pin-1 direction match the cable from DESPI-C73.
- `J_PANEL` contact side and pin-1 direction match the MF-1750 flex.
- `H_CS2` pin 1 goes to the ESP32 second chip-select GPIO.
- `R_SL` can be populated as a weak pull-up to `VDDIO`, or left DNP if the
  ESP32 pin has a reliable external/default pull-up.

Do not use `mf1750_full_driver_kicad` for this C73 interposer job; that is the
full-driver redraw route.
