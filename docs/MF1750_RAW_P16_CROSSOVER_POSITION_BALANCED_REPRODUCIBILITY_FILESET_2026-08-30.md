# RAW-P16 crossover clean-checkout reproducibility fileset

Baseline inspected: `origin/main` at `172840c091bd963633860b5dfde6f327d30ab665`. No Git mutation was performed.

## Important repository-state finding

The six builds are reproducible in the current worktree, but this campaign is not a self-contained delta against `origin/main`. It intentionally reuses a substantial runtime-LUT/white-containment foundation that is still untracked, plus the current modified versions of two tracked EPD driver files. Therefore, staging only the new crossover-named files would produce a broken clean checkout.

Several prerequisite aggregate files contain other campaign implementations. This is not hidden: they should be reviewed and committed as a separate shared-foundation change, or refactored into campaign-neutral committed modules before the crossover delta is merged.

## Crossover campaign delta

All of these paths are currently untracked and belong directly to this campaign:

```text
docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_OFFLINE_BUILD_REPORT_2026-08-30.md
docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_REPRODUCIBILITY_FILESET_2026-08-30.md
docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_RUNBOOK_2026-08-30.md
docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt
platformio.raw_p16_crossover_posbal_t1_ac_v1.ini
platformio.raw_p16_crossover_posbal_t2_ca_v1.ini
platformio.raw_p16_crossover_posbal_t3_ac_repeat_v1.ini
platformio.raw_p16_crossover_w1_after_t1_white_v1.ini
platformio.raw_p16_crossover_w2_after_t2_white_v1.ini
platformio.raw_p16_crossover_w3_final_after_t3_white_v1.ini
src/ec5_raw_p16_crossover_position_balanced_epd_driver.cpp
src/ec5_raw_p16_crossover_position_balanced_identity.inc
src/ec5_raw_p16_crossover_position_balanced_main.cpp
src/ec5_raw_p16_crossover_position_balanced_main_config.inc
src/ec5_raw_p16_crossover_white_containment_identity.inc
tests/test_mf1750_raw_p16_crossover_position_balanced.py
tools/mf1750_raw_p16_crossover_position_balanced_once.py
tools/mf1750_raw_p16_crossover_position_balanced_pack.py
tools/mf1750_raw_p16_crossover_position_balanced_build.py
```

## Shared files changed for this campaign

These files are also currently untracked, but they pre-existed this subtask and contain other campaign code. The crossover implementation adds conditional selectors/manifest bindings to them; staging them necessarily stages their existing aggregate content too:

```text
src/ec5_raw_p16_endpoint_gallery_v1_white_containment_program.inc
src/ec5_runtime_lut_same_r20_parity_4x8_v2_driver.inc
src/ec5_runtime_lut_same_r20_parity_4x8_v2_main.cpp
src/ec5_runtime_lut_same_r20_parity_4x8_v2_main_config.inc
```

Other-campaign content is present in particular in the shared driver and white program. The old frozen same-R20 action identity was not updated and must not be replayed.

## Shared build prerequisites absent from origin/main

These untracked files are required by the six C++ dependency graphs but were not created by this subtask. They also contain shared or other-campaign implementation:

```text
src/ec5_chroma_grid_epd_driver.h
src/ec5_factory_otp_white_recovery_driver.inc
src/ec5_raw_p16_endpoint_gallery_v1_white_containment_main.cpp
src/generated/spd1657_legacy_535_reference.inc
```

The current builds also depend on these tracked-modified files. This subtask did not author their unrelated modifications, so they require a separate diff review before staging:

```text
src/epd_driver.cpp
src/epd_driver.h
```

The following build dependencies are tracked and clean, so no additional staging is needed:

```text
src/epd_config.h
src/epd_diagnostics.h
src/wifi_secrets.example.h
```

`src/wifi_secrets.h` is local and ignored. Never stage it. On a clean checkout, create the local ignored file from `src/wifi_secrets.example.h` and set appropriate local credentials before compiling; the example, not the secret file, is the repository artifact.

## Shared host-runner prerequisites absent from origin/main

The fail-closed runner deliberately reuses reviewed mechanics from these currently untracked files. They are needed to reproduce offline validation and live-runner behavior, but not merely to invoke the C++ compiler:

```text
tools/mf1750_ec5_otp_transition_matrix_recheck_once.py
tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_once.py
tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_pack.py
tools/mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py
tools/mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_pack.py
tools/mf1750_runtime_lut_hue_brightness_blue_v1_white_containment_once.py
tools/mf1750_runtime_lut_hue_brightness_blue_v1_white_containment_pack.py
tools/mf1750_runtime_lut_partial_hold_once.py
tools/mf1750_runtime_lut_partial_hold_pack.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_once.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_pack.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_once.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_pack.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py
tools/mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_pack.py
tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py
tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_pack.py
```

These are shared historical mechanics, not campaign-only content.

## Recommended staging split

Do not use a broad `git add .`. The recommended review/staging order is:

1. A separately reviewed shared-foundation change containing the four untracked C++ build prerequisites, the four shared files changed for crossover, the two tracked-modified EPD driver files, and the 17 shared host-runner prerequisites above.
2. A campaign-only change containing exactly the 19 crossover campaign-delta paths above.

This split is the minimum honest handoff from a clean `origin/main`: the first set exposes all mixed-campaign content for explicit review, while the second set remains attributable to this campaign. If the shared foundation is already staged by another coordinated task, do not stage duplicate path arguments; verify its final blobs match the six reviewed artifact hashes before staging the campaign delta.
