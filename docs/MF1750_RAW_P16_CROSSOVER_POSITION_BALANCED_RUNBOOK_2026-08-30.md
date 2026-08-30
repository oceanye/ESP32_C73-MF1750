# MF1750 RAW-P16 crossover position-balanced runbook

Date: 2026-08-30
Status: offline implementation and build complete; no live result is claimed.

## Purpose

This campaign compares the legacy active-535 and commented-535 R20 endpoints while holding the packed image data, sample coordinates, and position balance constant. It is a controller/profile crossover experiment, not an absolute-colour qualification.

The atlas is the already-reviewed same-R20 V2 4 x 8 layout on each 512-pixel controller half. Every transport code 0 through 7 occurs four times per controller. T1, T2, and T3 use byte-identical 307,200-byte packed frames and byte-identical 153,600-byte controller DTM streams.

Analysis priority is C3/C5/C6/C7. C4 is a guard. C0/C1/C2 are controls. No stable new colour is claimed before retained live evidence passes the gates below.

## Fixed sequence

Each numbered item is a separate firmware, campaign, NVS namespace, claim root, and one-action execution. Nothing in the runner automatically flashes, resets, operates J2, retries, recovers, or advances to the next item.

1. Establish and retain an independent clean factory-white starting condition.
2. T1 AC: active global header; CS1 active-535; CS2 commented-535.
3. Retain three fixed-camera, J2-OFF atlas captures.
4. W1: independent factory-OTP white containment; confirm clean white.
5. T2 CA: commented global header; CS1 commented-535; CS2 active-535.
6. Retain three fixed-camera, J2-OFF atlas captures.
7. W2: independent factory-OTP white containment; confirm clean white.
8. Decide from T1/T2 evidence whether an AC repeat is needed.
9. If needed, T3 AC-repeat: a fresh AC action with a fresh campaign and NVS root.
10. Retain three fixed-camera, J2-OFF atlas captures, then run W3 final containment and confirm clean white.

T3 and W3 are conditional, but if T3 is run then W3 is mandatory as the final containment. If T3 is skipped, W2 is the final containment.

## Offline invariants

- Frame SHA-256 for every atlas: `1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23`.
- CS1 and CS2 DTM SHA-256 for every atlas: `2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb`.
- Frame histogram C0..C7: `41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200`.
- T1/T3 profile tuple: active header / CS1 active-535 / CS2 commented-535.
- T2 profile tuple: commented header / CS1 commented-535 / CS2 active-535.
- All six action IDs and all six NVS namespaces are unique.
- Every campaign has one visible refresh only; automatic chaining, retry, and recovery are false.
- Atlas stages require an explicit external pre-white confirmation before their request is constructed.

## Live qualification gates

For one code in one atlas, each controller supplies four spatial samples. Three retained captures therefore provide 12 samples per code/controller/stage.

A candidate should only advance when all of the following hold:

1. Within one controller/profile, its four positions agree beyond the camera/noise tolerance.
2. T1 and T2 show that the candidate follows the active/commented profile swap rather than fixed left/right controller position.
3. Controls C0/C1/C2 and guard C4 do not show a conflicting controller-geometry explanation.
4. If T3 is used, T3 AC agrees with T1 AC within the predeclared repeat tolerance.
5. The independent white stage returns both halves to clean white without retained colour, seam, border, or line anomaly.

Until those gates pass, observations remain experimental endpoint appearances, not qualified colours or an expanded palette.

## Clean-checkout build and validation order

The ignored `.pio` directory is not a repository artifact. On a clean checkout, do not run artifact-bound `dry-validate` or the artifact integration tests before compiling. Use this order; none of these commands uploads firmware or accesses a device:

```powershell
if (-not (Test-Path -LiteralPath src/wifi_secrets.h)) {
  Copy-Item -LiteralPath src/wifi_secrets.example.h -Destination src/wifi_secrets.h
}
python -B tools/mf1750_raw_p16_crossover_position_balanced_once.py prebuild-validate
python -B tools/mf1750_raw_p16_crossover_position_balanced_build.py build
python -B tools/mf1750_raw_p16_crossover_position_balanced_once.py dry-validate
python -B -m pytest -q tests/test_mf1750_raw_p16_crossover_position_balanced.py
```

`prebuild-validate` is intentionally artifact-free. The build command first repeats that preflight, compiles all six isolated images, and then enforces all 12 reviewed BIN/ELF hashes. The following explicit `dry-validate` is the artifact-bound post-build gate. The bootstrap never invokes a PlatformIO upload target. If local credentials already exist, do not overwrite them with the example.

For manual diagnosis, the six compile-only commands used by the bootstrap are:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_posbal_t1_ac_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_w1_after_t1_white_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_posbal_t2_ca_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_w2_after_t2_white_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_posbal_t3_ac_repeat_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -c platformio.raw_p16_crossover_w3_final_after_t3_white_v1.ini
```

The live subcommands are deliberately separate (`diagnose-atlas-j2-off`, `run-atlas`, and `run-white`). They are not invoked by offline validation and must not be chained by an outer script.

## Identity summary

| Stage | Contract ID | Action ID | NVS namespace |
|---|---|---|---|
| T1 AC | `6ea93bbd9be1d75e12bc6656614ac335faeb97aa1079ff04733b8babe7a247d7` | `73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72` | `p16x_t1ac_v1` |
| W1 | `7c6afcd9dd4bfd26d52659d22687bdfe3bf8b891ed86cd0783538a720ddddd70` | `f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5` | `p16x_w1_v1` |
| T2 CA | `ddcde0da8f5fec1b73924131a9a3e92fbee632430a041a72c56eea8a32b9d3cf` | `d38f77df0f02d1eb65641d2b8836bce46db2b563b75d711d86b2da1ebe989470` | `p16x_t2ca_v1` |
| W2 | `2888c7cdcb0ff22850ecfa25efcd722646cc21b68f4da43347d9af98a94a8615` | `b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f` | `p16x_w2_v1` |
| T3 AC repeat | `60f27623af8527f240173e457060ba008e61083f985e2b4a6ad4914a1f3705a0` | `4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a` | `p16x_t3ar_v1` |
| W3 final | `b7e984233f33c826f7882e44ede6297f38b5308947c02cd7561f2883e247ee6c` | `c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63` | `p16x_w3_v1` |

Artifact hashes are frozen separately in `MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt` and are also enforced by the offline runner before any live request.
