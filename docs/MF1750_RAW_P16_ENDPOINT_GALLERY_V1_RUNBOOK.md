# MF1750 RAW-P16 endpoint gallery V1 runbook

Status: successor-bound offline build ready for a later controlled screen session.
The 2026-08-28 V1B rebind/build/validation pass performed no hardware, device
network, COM-port, relay, flashing, reset, or display-refresh operation.

## What this campaign establishes

The campaign is a three-firmware, three-campaign sequence:

1. `PRE-WHITE ANCHOR V1B`: one fresh successor factory-OTP WF23_25 white action.
2. `RAW-P16 ENDPOINT GALLERY V1`: one full-screen `L535_ACTIVE_GLOBAL`
   refresh displaying transport codes 0 through 7 once on each controller.
3. `WHITE CONTAINMENT V1`: one independent factory-OTP WF23_25 white action.

Each step has a fresh campaign/test/build identity, API route, NVS namespace,
claim root, and output root. Nothing autochains. The gallery runner requires an
explicit clean-white confirmation after the pre-white action, and the post-white
campaign remains independently armed and consumed.

Runtime code 7 is an endpoint/background transport code. It is not accepted or
described as factory-OTP white recovery.

## Frozen gallery layout

Both controllers use the same pure-field, non-dithered 2-column by 4-row DTM
layout. Each cell is 200 by 96 pixels. Controller-local X positions are 36 and
276; Y positions are 36, 180, 324, and 468.

| Row | Left cell | Right cell |
| --- | ---: | ---: |
| 1 | code 0 | code 1 |
| 2 | code 2 | code 3 |
| 3 | code 4 | code 5 |
| 4 | code 6 | code 7 |

The background is also runtime code 7, so the code-7 endpoint is identified by
its frozen coordinates rather than by an outline. There are 8 observations per
controller and 16 observations total. This is not evidence for 16 unique colors,
nor for any qualified color set. Cyan/teal, violet/magenta, and brown/orange
labels remain deliberately unresolved pending calibrated observation.

The waveform tuple is intentionally mixed:

- global header: active (`L535_ACTIVE_GLOBAL`, selecting the active PWR/PLL family)
- CS1 R20: active535, SHA-256
  `716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`
- CS2 R20: commented535, SHA-256
  `2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26`
- controller DTM streams are byte-identical; controller R20 payloads are not

## Frozen identities and artifacts

| Step | Contract ID | BIN bytes / SHA-256 | ELF bytes / SHA-256 |
| --- | --- | --- | --- |
| Pre-white anchor V1B | `d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61` | 786,704 / `54f7e6f588a35730add6a5edd16e7e4b375e273d467d717277ec0a4cde413bc6` | 13,214,676 / `70101044f9207eb8df43ee8e719158f3d8441be058bf172980681e195fa5d5a7` |
| RAW-P16 gallery, V1B-pre bound | `f9b1f6b8052322bedc6b702cb895425e7c3dc5e2d1b7d9ae6e68edaa1ffc409d` | 797,712 / `1cd68a43b8398e76636ebc80123e13aecb4edc6db4d0e7d927e7bcfc84680bef` | 13,282,824 / `a1d1ad39460ba494f981b20a5d4f169792e2956749611a58b8b6037e2a639b4d` |
| Post-white containment | `1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14` | 786,448 / `8c33085d0c9e0f03d651ad82a99a6336275f881fe9eb9e296cf526b5f80503c1` | 13,214,304 / `b65a4562b987de7adabe1d561504f1cf9c1b91d41b676ace32fd7adf81ab3a2a` |

The previous RAW-P16 main artifact (`contract 5d4d6084...6185c`, BIN
`6aa3660d...1f75`, ELF `587ae586...914b0`) is
**OFFLINE_SUPERSEDED_NEVER_FLASHED**. It retained the same main campaign, NVS,
action, layout, mixed-R20 tuple, and post-containment source, but was bound to the
sealed V1 pre-white predecessor. It must not be flashed or used for a future
gallery action.

The gallery action ID is
`9f5b84a12ac93c85898d2e843db6a5a4d174daa6ce0f18ffd8da974737f0a088`.

## Offline verification

From the repository root:

```powershell
& 'C:\Users\Ye\.platformio\penv\Scripts\platformio.exe' run -c platformio.raw_p16_endpoint_gallery_pre_white_anchor_v1b.ini
& 'C:\Users\Ye\.platformio\penv\Scripts\platformio.exe' run -c platformio.raw_p16_endpoint_gallery_v1.ini
& 'C:\Users\Ye\.platformio\penv\Scripts\platformio.exe' run -c platformio.raw_p16_endpoint_gallery_v1_white_containment.ini

python tools/mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_pack.py
python tools/mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_once.py dry-validate
python tools/mf1750_raw_p16_endpoint_gallery_v1_pack.py
python tools/mf1750_raw_p16_endpoint_gallery_v1_once.py dry-validate
python tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_pack.py
```

These commands build or validate local files only. The pack and dry-validation
commands do not access the device.

## Later controlled screen order

1. Flash and boot only the reviewed **V1B successor pre-white** BIN; arm/execute
   its single action. The sealed V1 predecessor is not an acceptable anchor.
2. Confirm a clean factory-OTP white result. Do not substitute runtime code 7.
3. Flash and boot only the reviewed gallery BIN. Run ordinal 1 with both the J2-ON
   and external-pre-white confirmations. Record one image containing all 16
   coordinate-bound endpoint observations.
4. Do not infer unique or qualified color count from that image alone.
5. Flash and boot only the reviewed post-white BIN; arm/execute its single action.
6. Confirm clean white containment and preserve the three independent evidence
   files and claims roots.

The once runners never flash, reset, control J2 or power, retry, recover, skip,
or autochain. Firmware switching and power control remain separate operations in
the later authorized live session.
