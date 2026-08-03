# JLC Import Checks

Use this project/zip for the next JLC import:

```text
hardware/mf1750_jlc_simplified_kicad.zip
```

## Must Pass Before Layout

1. Open PCB and confirm `J1` is a 50-pin 0.5 mm FPC connector.
2. Select `J1 pad 4`; its net must be `SL_CSB`.
3. Select `J1 pad 31`; its net must be `CSB`.
4. Select `J2 pad 5`; its net must be `CSB`.
5. Select `J2 pad 6`; its net must be `SL_CSB`.
6. Confirm no object is named `unconnected-(J1-Pad4)`.

## Expected Warnings

- Unrouted-net warnings are expected before manual or AI routing.
- Do not ignore net mismatch between schematic and PCB. If it appears, run import/update from schematic again, then recheck `J1-4` and `J1-31`.

## Routing Priority

1. Place and lock `J1` orientation first.
2. Place `J2` so SPI lines route cleanly to J1.
3. Route `SL_CSB` and `CSB` explicitly before autorouting.
4. Place charge-pump parts close to the corresponding FPC pins.
5. Keep `VPH`, `PREVGH`, `PREVGL`, `VPC`, and `VCOM` traces short and wide.

## Do Not Copy From EE04

The Seeed EE04 footprint geometry is used only as a connector reference. Its original EE04 net mapping is not valid for MF-1750 because EE04 leaves `J1-4` unconnected, while MF-1750 requires `J1-4 = SL_CSB`.
