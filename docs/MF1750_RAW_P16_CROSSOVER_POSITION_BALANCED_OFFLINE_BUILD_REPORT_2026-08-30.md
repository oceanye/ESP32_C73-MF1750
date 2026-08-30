# MF1750 RAW-P16 crossover offline build report

Date: 2026-08-30
Scope: T1 AC, W1, T2 CA, W2, optional T3 AC-repeat, and W3 final containment.

## Result in the reviewed local worktree

All six isolated PlatformIO environments built successfully in the original reviewed worktree with `platformio/espressif32@7.0.1`, Arduino ESP32 framework `3.20017.241212`, and the ESP32-S3 DevKitC-1 target. The local reviewed BIN and ELF identities are listed in `MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt` and are enforced by the runner before a live request.

Offline validation result:

- artifact-free source/contract prebuild validation: PASS;
- campaign dry validation: PASS;
- fresh action IDs: 6 of 6 unique;
- fresh NVS namespaces: 6 of 6 unique;
- T1/T2/T3 packed frame and both controller DTM identities: byte-identical;
- new campaign tests: 13 passed;
- related same-R20/white mechanics tests: 15 passed, with the historical same-R20 frozen-artifact replay test deliberately excluded;
- Python lint and format checks: PASS.

No device, network endpoint, serial/COM port, relay, camera, firmware flash, reset, J2 operation, or display refresh was accessed during this work.

The `.pio` products remain ignored. The local-worktree bootstrap uses this order:

1. artifact-free `prebuild-validate`;
2. six compile-only PlatformIO builds;
3. artifact-bound `dry-validate` and campaign tests.

The build wrapper repeats the artifact-free preflight before it starts the six builds and enforces all 12 reviewed BIN/ELF hashes after them. No upload target is used and no large ELF is committed.

## Independent clean-checkout audit: exact-hash NO-GO

A separate short-path export of `origin/main` plus the documented 46-file closure passed source preflight and compiled all six images. It did **not** reproduce the 12 frozen BIN/ELF hashes:

- the ELF embeds the absolute checkout path, so a different checkout directory changes the ELF;
- `src/wifi_secrets.h` is intentionally local and ignored; building with the example file changes firmware content;
- even after using the same local credential file without exposing its contents, the T1 BIN retained the same byte count but differed in 65 bytes associated with the embedded ELF identity and final image checksum;
- an excessively long Windows temporary path also caused W3 dependency-file creation to fail; a short path compiled successfully.

Therefore the current state is:

```text
source_preflight = PASS
six_clean_checkout_compiles = PASS
original_worktree_artifact_binding = PASS
cross_path_exact_hash_reproduction = FAIL
github_code_handoff = NO_GO
```

The current reviewed artifacts remain usable only as local, identity-bound artifacts. The repository must not claim clean-checkout exact reproducibility until either deterministic prefix mapping plus non-secret/runtime provisioning is introduced and all 12 hashes are re-frozen, or the reviewed binaries are published separately as a hash-bound release artifact.

## Historical-artifact boundary

The prior same-R20 V2 action is not part of this campaign and must not be replayed. Its frozen runner hashes were not changed. A locally rebuilt old same-R20 artifact does not match that historical frozen identity, so the old runner correctly fails closed instead of treating the rebuild as the reviewed old action.

The new campaign has its own six artifact bindings, six action IDs, six NVS namespaces, and six claim/output roots. No compatibility shortcut aliases a new action to the historical action.

## Review boundary

This report proves local offline consistency and source compile availability only. It does not prove cross-path exact artifact reproducibility, a device identity, boot state, electrical state, display result, colour equivalence, or a stable new colour. Those remain open gates.
