# JLC Import Checks - Relaxed Autoroute Version

Use this project/zip for the next quick autoroute attempt:

```text
hardware/mf1750_jlc_relaxed_kicad.zip
```

## Must Pass Before Autoroute

1. `J1 pad 4` must be `SL_CSB`.
2. `J1 pad 31` must be `CSB`.
3. `J2 pad 5` must be `CSB`.
4. `J2 pad 6` must be `SL_CSB`.
5. There must be no `unconnected-(J1-Pad4)`.

## Why This Version Exists

The previous compact board left many same-net objects disconnected after autorouting. This version increases the board area and spreads the high-voltage pump, logic header, and FPC-side capacitors so JLC autorouting has more channels.

## Quick Autoroute Settings

- Board type: 2-layer first.
- Allow vias.
- Completion priority: high.
- Signal width: 0.15-0.20 mm.
- Power/HV width after routing: manually thicken where possible.
- Pour copper only after autorouting; use `GND` on top and bottom.

## If It Still Fails

If connectivity errors remain above roughly 50 after autoroute and GND repour, switch to a 4-layer board instead of continuing to fight the 2-layer layout.
