# MF1750 RAW-P16 crossover offline build report

Date: 2026-08-30
Scope: T1 AC, W1, T2 CA, W2, optional T3 AC-repeat, and W3 final containment.

## Result

All six isolated PlatformIO environments built successfully with `platformio/espressif32@7.0.1`, Arduino ESP32 framework `3.20017.241212`, and the ESP32-S3 DevKitC-1 target. The reviewed BIN and ELF identities are listed in `MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt` and are enforced by the runner before a live request.

Offline validation result:

- clean-checkout artifact-free prebuild validation: PASS;
- campaign dry validation: PASS;
- fresh action IDs: 6 of 6 unique;
- fresh NVS namespaces: 6 of 6 unique;
- T1/T2/T3 packed frame and both controller DTM identities: byte-identical;
- new campaign tests: 13 passed;
- related same-R20/white mechanics tests: 15 passed, with the historical same-R20 frozen-artifact replay test deliberately excluded;
- Python lint and format checks: PASS.

No device, network endpoint, serial/COM port, relay, camera, firmware flash, reset, J2 operation, or display refresh was accessed during this work.

The `.pio` products remain ignored. Clean-checkout reproduction therefore uses the documented artifact-bootstrap split, in this exact order:

1. artifact-free `prebuild-validate`;
2. six compile-only PlatformIO builds;
3. artifact-bound `dry-validate` and campaign tests.

The build wrapper repeats the artifact-free preflight before it starts the six builds and enforces all 12 reviewed BIN/ELF hashes after them. No upload target is used and no large ELF is committed.

## Historical-artifact boundary

The prior same-R20 V2 action is not part of this campaign and must not be replayed. Its frozen runner hashes were not changed. A locally rebuilt old same-R20 artifact does not match that historical frozen identity, so the old runner correctly fails closed instead of treating the rebuild as the reviewed old action.

The new campaign has its own six artifact bindings, six action IDs, six NVS namespaces, and six claim/output roots. No compatibility shortcut aliases a new action to the historical action.

## Review boundary

This report proves offline consistency and reproducible build availability only. It does not prove a device identity, boot state, electrical state, display result, colour equivalence, or a stable new colour. Those remain live evidence gates in the runbook.
