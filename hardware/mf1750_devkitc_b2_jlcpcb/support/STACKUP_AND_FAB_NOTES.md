# Stackup and fabrication notes

- Order stackup: `JLC04161H-7628`, 4 layers, nominal 1.6 mm.
- Surface finish: ENIG, 1 microinch option; do not substitute HASL at order time.
- L1 F.Cu: 0.035 mm / 1 oz.
- Prepreg: 7628, nominal 0.2104 mm.
- L2 In1.Cu: 0.0152 mm / 0.5 oz, solid GND plane.
- Core: nominal 1.065 mm.
- L3 In2.Cu: 0.0152 mm / 0.5 oz, power routing.
- Prepreg: 7628, nominal 0.2104 mm.
- L4 B.Cu: 0.035 mm / 1 oz.
- Finished thickness: 1.6 mm nominal; no controlled-impedance claim.
- Ordinary through vias only; 0.30 mm drill / 0.60 mm pad for routed vias.
- Add >=5 mm assembly rails, fiducials, and tooling holes at JLCPCB panelization.
- Gerber job file is deliberately excluded so an inferred KiCad dielectric model cannot
  override the explicit order stackup above.
