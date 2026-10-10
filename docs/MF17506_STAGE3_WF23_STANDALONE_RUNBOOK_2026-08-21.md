# MF17506 Stage-III WF23 standalone runbook

Recorded: `2026-08-21 22:33 +08:00`

Status: `TREATMENT COMPLETE / NO NEW VISUAL COLOUR / CLEAN WHITE RECOVERED / J2 OFF`

## Decision basis

- Stage II is closed by operator decision because the complete 8^3 single-pixel
  history screen did not reveal a visually distinguishable new colour.
- The 24-colour-card qualification and delayed 60 s/10 min observations are
  closed as not decision-relevant for Stage II. They are not recorded as PASS.
- A logic analyser is an auxiliary trace-capture instrument. Its absence does
  not block this profile-level empirical test.
- Public evidence does not expose a trustworthy SPD1657B command/register/LUT
  ABI. Therefore this runbook tests one complete, identity-pinned vendor profile
  and does not assign meanings to unknown bytes.

The governing closeout decision is:

`docs/MF-17506-M009F-T_阶段二关闭与阶段三推进裁决_2026-08-21.md`

SHA-256:

`cf54c0340c8f7ca532b599d0b4105c32f527263ed0acc4772e98c99508dcf36f`

## Exact release

Profile: `WF23_25`

Release:

`.test-output/hardware/MF1750_STAGE3_WF23_STANDALONE_20260821/WF23_25-release.json`

- release file SHA-256:
  `c06ebabb7096ba848d9635c02609f86f0cc97302ae83cade3b315b6ab6346f3b`
- release ID:
  `9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4`
- canonical SHA-256:
  `0f5dfeb8359abea5d0d4b5b800958737f161f78ca81ec3515877920fcd759b7a`
- host execution bundle SHA-256:
  `3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0`

Treatment app:

- environment: `ec5_runtime_lut_wf23_25`
- BIN: `793776 bytes`
- BIN SHA-256:
  `6eb9115ef143142de801c96fe31c8b9898455f550a52a85c51cfa7a2026698e2`
- ELF SHA-256:
  `d385b01ffcee182d9614d9462489c44628990a576c54979cc9254c8fc3824aa1`
- action: one fixed 8-code atlas using the complete WF23 empirical-H3 profile

Independent factory-OTP white recovery app:

- environment: `ec5_otp_white_wf23_25`
- BIN: `785888 bytes`
- BIN SHA-256:
  `2712984d39f1c295841a4b9994c72ee13f6c6935e514ce918648cce2a6159e7c`
- ELF SHA-256:
  `9c3587285d2b4748ca1594dffbc0848dd394d48c74bd205d6d7ce90699bd3939`
- action: one independent factory-OTP clean-white refresh

Both apps were rebuilt from current source on 2026-08-21. All four BIN/ELF
hashes exactly reproduce the sealed 2026-08-12 release.

The original recovery identity had already been consumed by an earlier
containment action. It was therefore not reused for the live closeout. A new
isolated recovery build was added after the treatment observation:

- environment: `ec5_stage3_wf23_white_20260821`
- NVS namespace: `s3w23_0821`
- BIN: `785904 bytes`
- BIN SHA-256:
  `8717cb868a127fbf6645bc7613ab132dfe918a2184dc726e2df63a25dbc0e2e9`
- ELF SHA-256:
  `3d73545a037e3deb2815b4b491626039806f89ad34323f79f0995d9d3a2d578f`
- action ID:
  `b6357c9ee6e7a680b052a6a75586431073a36b0e48ab016131a608080686ccf7`
- focused regression: `68 passed`; Ruff PASS; PlatformIO PASS

## What is and is not being tested

The Stage-III treatment sends the fixed vendor-derived H3 profile through the
already bounded sequence and displays the same eight code positions used by the
factory atlas. The earlier WF20 treatment visibly changed code 4 and code 7 from
blue to white. WF23 is the next unchanged profile and has not yet received its
standalone treatment trial.

This run can establish whether WF23 produces a repeatable visible mapping that
differs from the factory atlas or WF20. It cannot by itself prove:

- the semantics of individual R20 bytes;
- the SPD1657B RAM-LUT ABI;
- a safe arbitrary LUT editor;
- film-lot or temperature qualification;
- a new colour before human observation confirms it.

The implementation has no raw-payload endpoint, profile switch, VCOM sweep,
unknown-command scan, SPI sweep, retry, automatic recovery, or action chaining.
It does not require a logic-analyser input or logic-analyser evidence file.

## Supervised live order

1. Command COM14/channel 1 OFF and read back commanded OFF.
2. With J2 OFF, write only the treatment app partition at `0x10000`, independently
   verify the flash digest, then boot the treatment app.
3. Perform the four GET-only identity/manifest/status/report checks. Require exact
   release identity, ordinal 1 READY, zero prior driver calls and no existing claim.
4. Command J2 ON. Execute exactly one ARM and one EXECUTE for ordinal 1. Never
   resend a mutation after a timeout; use only delayed GET reconciliation.
5. Stop at the human observation gate. Record the eight apparent colours, left/
   right agreement, any genuinely new hue, defects and abnormalities. Then command
   J2 OFF.
6. Only after the observation is stored, write and verify the independent recovery
   app while J2 remains OFF. Its diagnostic and visible action are separate from
   the treatment action.
7. Command J2 ON and execute exactly one factory-OTP white action. After human
   confirmation of clean white, command J2 OFF and close the trial.

No colour-card measurement is required unless the treatment first produces a
visually distinguishable candidate worth qualification.

## Executed result

WF23 treatment completed with one ARM, one EXECUTE and terminal success. The
operator observed six colours, identical left/right results, and white at row 2
columns 1 and 4. These positions are code 4 and code 7. This matches the earlier
WF20 result at the gross visual level and does not add a new colour.

The fresh recovery action then completed with one ARM, one EXECUTE and terminal
success. The operator confirmed the screen was fully white. COM14/channel 1 was
commanded OFF and queried OFF. Full evidence is recorded in
`docs/MF17506_STAGE3_WF23_OBSERVATION_2026-08-21.md`.

## Stop conditions

Immediately command J2 OFF and do not retry if any of the following occurs:

- current limiting or unexpected current rise;
- abnormal sound, smell or heating;
- BUSY or driver time exceeds the bounded firmware limit;
- left/right controller disagreement, fixed line or large-area corruption;
- terminal FAULT or identity/manifest mismatch;
- a white recovery does not complete cleanly.
