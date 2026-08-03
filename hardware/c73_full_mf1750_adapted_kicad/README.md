# DESPI-C73 Full Circuit Adapted for MF-1750

This is the full C73-style circuit redraw for JLC/KiCad import. It is not just
a 50-pin interposer.

Main adaptation:

- C73 original P1 pin 4 was `VDD`.
- MF-1750 pin 4 is `SL_CSB`.
- This schematic routes J1 pin 4 to `SL_CSB` and exposes it on J2 pin 9.
- C73 original P1 pin 1 `VPP` is left unconnected because MF-1750 pin 1 is NC.

The schematic is divided into subsystem boxes: MCU interface, panel connector,
power distribution, HV boost/negative pump, VPC pump, panel-side capacitors,
and bring-up test pads.

Before PCB layout, verify connector contact side, pin-1 direction, diode
polarity, BS0/BS1 straps, and package choices against parts available in JLC.
