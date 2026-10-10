# EC5 U04/U05 comparison white-recovery contract (2026-08-09)

## Purpose and frozen identity

This action removes the already completed U04/U05 comparison pattern with one
exact RC2G solid-white refresh. It is the only valid immediate predecessor for
the next U07T action after the comparison; the earlier U07T action
`303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310`
is invalidated because the comparison intervened.

- Action ID: `f9d41bfcd55558391cf189da2ffbe4606f4c81fa1edd896c0b59e227e9ec1f36`
- Authorization:
  `AUTHORIZE_ONE_VISIBLE_RC2G_EC5_SOLID_WHITE_AFTER_U04_U05_COMPARE__ACTION_F9D41BFCD55558391CF189DA2FFBE4606F4C81FA1EDD896C0B59E227E9EC1F36__NO_RETRY_NO_RECOVERY`
- Exact RC2G binary SHA-256:
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`
- Solid-white frame SHA-256:
  `91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`
- Independent claim registry ID:
  `workspace-mf1750-ec5-u04-u05-compare-white-claims-v1`

The action cannot use the formal EC5 white claim registry. It cannot reuse the
baseline, after-U04, or after-U07 white action IDs or claims.

## Required sequence

1. With J2 physically off, run `prepare-j2-off`. This performs no device or
   network I/O and creates no claim. It deep-validates and seals the completed
   comparison release, result, permanent claim, blind manual observation,
   panel, exact RC2G binary, and formal-claim snapshot.
2. While J2 remains off, flash only the archived RC2G binary above. Firmware
   upload is deliberately outside the recovery runner.
3. Turn J2 on and confirm electrical readings are normal. Run `preflight`.
   It performs exactly four GET requests and zero POST requests, and creates no
   claim. Required state is RC2G, idle job 0, invalid report 0, and safe GPIO
   `BUSY=1, RST=0, CS=0, CS2=0`.
4. After the exact authorization is supplied, run `run` once. It repeats the
   four fresh GET checks, permanently claims the new action before the first
   mutation, and permits at most one `/api/frame` POST. There is no retry or
   automatic recovery even if the outcome is uncertain.
5. The operator confirms full clean white, all four comparison patches gone,
   no residual image, normal electrical state and temperature, and no ESP32
   restart. Seal and validate that report with `seal-observation` and
   `validate-observation`.
6. Run `u07t-binding` to produce the latest-white predecessor binding. U07T
   must accept it only after `validate-u07t-binding` deep-replays the result,
   independent claim, manual observation, integrity and time chain. It must
   freeze a new action identity from that output and obtain a live confirmation
   that no visible refresh occurred after the white observation.

Every evidence/output path is create-only. A claim permanently consumes the
action even when a result says `unknown_do_not_retry_or_recover`. A
post-refresh formal-registry read failure is also durably sealed as that unknown
outcome; it never authorizes a retry.

Future consumers such as an `EC5_COLOR_LAB` first fixed-white action may reuse
the deep `validate_result` plus `validate_white_manual_observation` evidence
boundary. They must not reuse this action ID, authorization, or claim; their own
complete preimage and independently derived action identity remain mandatory.

## Authoritative inputs

- Compare release:
  `.test-output/hardware/MF1750_EC5_U04_U05_COMPARE_RELEASE_OFFLINE_20260809_V2/release-manifest.json`
- Compare result:
  `.test-output/hardware/MF1750_EC5_U04_U05_COMPARE_PHYSICAL_SESSION_20260809_2300/u04-u05-compare-result.json`
- Blind observation:
  `.test-output/hardware/MF1750_EC5_U04_U05_COMPARE_PHYSICAL_SESSION_20260809_2300/u04-u05-blind-manual-observation.json`
- Compare claim registry:
  `.test-output/hardware/.mf1750_ec5_u04_u05_compare_claims`
- Panel:
  `.test-output/hardware/RC2G_N2_PHYSICAL_SESSION_20260808_2132/inputs/physical-panel.json`
- RC2G binary:
  `.test-output/hardware/RC2G_N2_PHYSICAL_SESSION_20260808_2132/q1-map-primer-result/FIRMWARE.bin`

Implementation is in `tools/mf1750_ec5_compare_white_identity.py` and
`tools/mf1750_ec5_compare_white_recovery_once.py`. The regression contract is
in `tests/test_mf1750_ec5_compare_white_recovery_once.py`.
