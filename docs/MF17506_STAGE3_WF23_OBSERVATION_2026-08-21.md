# MF17506 Stage-III WF23 observation

Recorded: `2026-08-21 23:07 +08:00`

Status: `TREATMENT COMPLETE / NO NEW VISUAL COLOUR / CLEAN WHITE RECOVERED / J2 OFF`

## Treatment

- profile: `WF23_25`
- action ID:
  `fd3e4294c56c8b5545413c193563a6bfde5b8abf3784e4f42da25b7cf4f85fb9`
- boot nonce: `7bd375c5b24dafac`
- treatment result:
  `.test-output/hardware/MF1750_STAGE3_WF23_STANDALONE_20260821/treatment-result-v2.json`
- result SHA-256:
  `abe3b375b7a2cb6d09dbe4aedbd9bee56a8f689509cda8a726918b9103f9a820`
- protocol: one ARM, one EXECUTE, one visible refresh, terminal success;
  no retry, automatic recovery, automatic chaining or profile switch

The operator's exact observation was:

> 六色，左右屏幕一致；第二排第一个和第四个是白色

The atlas layout is four columns by two rows. On CS1, row 1 contains codes
0–3 and row 2 contains codes 4–7. Therefore row 2 column 1 and row 2 column 4
are exactly code 4 and code 7. CS2 uses the counterbalanced mirrored order.

Decision:

- code 4 and code 7 both appeared white;
- both controllers agreed;
- only six apparent colour groups were present;
- no visually distinguishable new colour was found;
- at the gross visual level this matches the earlier WF20 treatment result.

This establishes a repeatable profile-level visible effect. It does not prove
the meaning of an individual R20/R21 byte or a public SPD1657B RAM-LUT ABI.

## Independent white recovery

The earlier WF23 recovery action was not reused. A new isolated recovery image
was built with NVS namespace `s3w23_0821` and a new action identity.

- recovery BIN: `785904 bytes`
- BIN SHA-256:
  `8717cb868a127fbf6645bc7613ab132dfe918a2184dc726e2df63a25dbc0e2e9`
- ELF SHA-256:
  `3d73545a037e3deb2815b4b491626039806f89ad34323f79f0995d9d3a2d578f`
- action ID:
  `b6357c9ee6e7a680b052a6a75586431073a36b0e48ab016131a608080686ccf7`
- diagnostic SHA-256:
  `f31862e273db0e99c64cc38efe3732ea5307bbc159ffc07c22a6e4c157ea6f8c`
- result SHA-256:
  `bcd11a4ac93c77462d0f076be4f6afcf7c497105ba871e615da8d8c4e947113b`
- claim SHA-256:
  `a0585d1bda57c17880a3ebaf5e6ba41e1e2d24bd803e7b9364cc570115435a75`

The recovery completed with one ARM, one EXECUTE and terminal success. The
operator's exact final observation was:

> 目前全白

COM14/channel 1 was then commanded OFF and queried as OFF. Relay feedback does
not independently measure downstream voltage, current or temperature.

