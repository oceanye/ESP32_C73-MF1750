# MF1750 RAW-P16 T3 camera-assisted observation — offline readiness

Date: 2026-08-31
State: `OFFLINE_READY`
Scope: supplemental camera screening for the fresh T3 AC profile-following atlas. This document and the analyzer do not access the camera, ESP32, relay, serial port, or network.

## Frozen boundary

The analyzer accepts only the project formal still profile from `README camera.md` and the frozen schema-v2 retained-capture validator:

- exact camera: `48MP USB Camera`, `USB_VID_32E4_PID_4801`, DirectShow instance containing `VID_32E4&PID_4801`;
- explicitly excluded: `VID_1BCF:PID_0B15`;
- `MJPG`, `4000x3000`, `15 fps`, autofocus `0`, focus `79`, auto exposure `0.25`, exposure `-6`, auto white balance `0`, white balance `4600`;
- current W3 white and all three T3 frames must have the same exact camera instance, `mount_id`, requested settings, effective settings before/after, and dimensions;
- the separate fresh-V2 exposure `-3` profile is rejected. Profiles cannot be mixed.

T3 remains human-primary. Camera evidence is optional, camera-relative, and incapable of making an absolute-colour or formal-qualification claim. The only automatic conclusions are:

- `HUMAN_CAMERA_SCREEN_PASS`
- `HUMAN_CAMERA_SCREEN_REVIEW`
- `HUMAN_CAMERA_SCREEN_FAIL`

Low machine confidence can never produce `PASS`.

## Inputs

The offline generator reads:

1. one current W3 clean-white JPEG and its schema-v2 locked-retained sidecar, both bound to the exact final W3 action;
2. the existing W3 clean-white human authority;
3. exactly three chronological T3 atlas JPEG/sidecar pairs, each bound to the same exact completed T3 action;
4. one explicit current-photo corner string for each of the four JPEGs;
5. optionally, a truthful compact human seed.

Each corner string is ordered `TL;TR;BR;BL`:

```text
TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy
```

Do not reuse one string by assumption. Record the white corners and all three atlas corner sets from their own 4000x3000 JPEGs. Each quadrilateral must be convex, in-bounds, at least 8% of the photo, and project every one of the 64 cells in-bounds with a minimum cell side of 20 px. The analyzer warps each photo with its own homography, then checks pairwise corresponding-corner drift and residual phase alignment.

## Future capture command shape

The existing capture tool is the only component that should touch the camera in the attended daylight session. The same options apply to the current W3 white and each T3 frame; only action/photo/sidecar paths change.

```powershell
python tools/mf1750_camera_capture_evidence.py capture-retained `
  --action-result <EXACT_ACTION_RESULT.json> `
  --photo <OUTPUT_4000x3000.jpg> `
  --sidecar <OUTPUT_CAPTURE.json> `
  --mount-id <ONE_FROZEN_SESSION_MOUNT_ID> `
  --coverage full_panel `
  --width 4000 --height 3000 --fps 15 `
  --warmup-frames 8 --require-all-setting-writes `
  --autofocus 0 --focus 79 `
  --auto-exposure 0.25 --exposure -6 `
  --auto-white-balance 0 --white-balance-temperature 4600
```

This is a future attended command template, not authorization to execute hardware now. Capture the white while W3 clean white is still retained, then execute T3 exactly once under its own runbook, command the relay off, and capture three T3 retained frames with unchanged mount/settings.

## Camera-only report

A seed is deliberately optional. This permits the 64-cell camera screen to run while the operator is unavailable. With no seed, all camera metrics are produced, the result is capped at `HUMAN_CAMERA_SCREEN_REVIEW`, no compact file is written, and no placeholder is treated as a human fact.

```powershell
python tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py generate `
  --white-photo <W3_WHITE.jpg> `
  --white-sidecar <W3_WHITE.capture.json> `
  --white-action-result <W3_ACTION.json> `
  --white-human-authority <W3_HUMAN_CLEAN_WHITE_AUTHORITY.json> `
  --atlas-photo <T3_1.jpg> <T3_2.jpg> <T3_3.jpg> `
  --atlas-sidecar <T3_1.capture.json> <T3_2.capture.json> <T3_3.capture.json> `
  --atlas-action-result <T3_ACTION.json> `
  --white-panel-corners '<WHITE_TL_TR_BR_BL>' `
  --atlas-panel-corners '<T3_1_TL_TR_BR_BL>' '<T3_2_TL_TR_BR_BL>' '<T3_3_TL_TR_BR_BL>' `
  --report-output <camera-screen.json>
```

## Human-assisted compact output

First write a non-overwriting template:

```powershell
python tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py `
  write-seed-template --output <human-seed.json>
```

Every `FILL_...` sentinel must be replaced by the operator's actual words. The validator rejects an unfilled template. The operator supplies only eight labels per controller plus explicit whole-side four-copy and stability confirmations; the tool does not derive names from pixels. Add these options to `generate`:

```powershell
  --human-seed <human-seed.json> `
  --compact-output <profile-following-human-compact-input.json>
```

The compact path is created with `O_EXCL` only when both controllers explicitly confirm all four copies and stability. It is expanded and checked against the fixed 64-cell layout before writing. If the seed is absent or those confirmations are not true, the report still writes, the requested compact path is left untouched, and the operator must resolve the card or use the human tool's expanded 64-cell schema.

The generated compact file is directly consumable by:

```powershell
python tools/mf1750_raw_p16_crossover_profile_following_human_observation.py seal `
  --stage t3-ac-profile-following-successor-v1 `
  --action-result <T3_ACTION.json> `
  --input <profile-following-human-compact-input.json> `
  --output <sealed-human-observation.json>
```

## Checks and downgrade rules

- White reference: every sampled cell must have `L* >= 25`. Any cell below 25 is `FAIL`; minimum `L*` from 25 through below 35 is `REVIEW`. Noise, clipping, or normalization saturation can lower confidence and force `REVIEW`.
- Geometry: malformed, singular, off-photo, too-small, or under-resolved corners are rejected fail-closed before a report because no honest 64-cell measurement exists. For valid geometry, maximum cross-capture corner drift is `PASS <= 12 px`, `REVIEW <= 30 px`, otherwise `FAIL`.
- Alignment confidence: the three independently warped atlas frames use phase correlation. Weak response or residual shift lowers confidence; low confidence forces at least `REVIEW` rather than inventing a defect or a pass.
- Four copies: the frozen daylight-plan gate is group maximum `Delta E00 <= 8` for `PASS`, `<= 12` for `REVIEW`, otherwise `FAIL`. The old single-frame 3/5 position heuristic does not decide this item.
- Temporal stability: each physical cell across three frames uses maximum `Delta E76 <= 3` for `PASS`, `<= 6` for `REVIEW`, otherwise `FAIL`.
- Controls 2/3/5: a separate existing camera-relative cross-controller 3/5 `Delta E00` heuristic is reported, together with exact human label equality when a seed is supplied.
- Artifacts: the screen reports inner-cell 3x3 residuals, horizontal and vertical bands, the lower logical band against each controller's code-7 background, human edge/stripe/residual flags, and frame stability.

Invalid source identity/settings/paths/hashes/integrity, exposure `-3`, or invalid geometry exits `2` without fabricating a screen. A valid generated screen exits `0` for `PASS`, `3` for `REVIEW`, and `4` for `FAIL`. `validate` deep-recomputes from every bound source and exits `2` on any drift.

## Offline verification performed

```powershell
ruff check tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py tests/test_mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py
pytest -q tests/test_mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py
```

The synthetic replay covers clean `PASS`, low-light `REVIEW`, `L* < 25` `FAIL`, low-information/low-confidence `REVIEW`, four-copy mismatch, control mismatch, stripe, bottom edge, per-photo geometry drift, camera-only seed absence, exact 64-cell compact expansion, unfilled-template rejection, exposure `-3` rejection, final W3 allowlist identity, and dual `O_EXCL` output handling.
