# MF1750 WROOM B3 power / TF board

State: `R8D_EPD_INTERNAL_DCDC_PG_PWR_INT_EDGE_ACCESS_CANDIDATE_HOLD`

This project preserves the real-panel-tested B2 display-driver region and adds
an ESP32-S3-WROOM-1-N16R8 module, protected 1S LiPo charge/PowerPath, keyed
power control, regulated 3.3 V, native USB, bottom-entry microSD/TF, two user
buttons, BOOT/RESET service buttons, and powered-off EPD signal isolation.

Do **not** fabricate the formal PCB yet.  The editable authoritative schematic
is current, but the formal `mf1750_wroom_b3_power_tf.kicad_pcb` intentionally
remains the older R2 candidate.  Work proceeds through staging files until all
route, DRC, mechanical and manufacturing gates pass.

## Current frozen facts

- Board: 80.0 x 125.0 mm, four copper layers.
- TF entry: lower edge, card travels from outside toward the board.
- ESP32: `ESP32-S3-WROOM-1-N16R8`, antenna beside the right edge with an
  all-four-copper-layer no-copper/no-track/no-via/no-footprint rule area.
- Schematic SHA-256:
  `158E54C1B8E0301860239BD69D837215CAF2A9F5D5A34687A32FEE922B310BF0`.
- KiCad 10.0.3 ERC: 0 error / 0 warning.
- Schematic contract: 246/246 PASS; B2 inheritance: 655/655 PASS.
- Native schematic-to-PCB parity: 0 on the self-contained R3 synchronization
  candidate; the U1-deletion negative canary reports exactly one mismatch.

## Current staging artifacts

- `staging/mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb` is the deterministic,
  schematic-synchronized parking candidate.
- `staging/mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb` is the
  deterministic functional-placement candidate.  SHA-256:
  `349EF014B520AEDCB061EE8BBCADBB03BFAAD3249B512937091280918D0F2FBF`.
- `staging/r4_functional_placement_report.json` records the placement audit.
- `staging/r4_preview/` contains current top and bottom renders.
- `staging/mf1750_wroom_b3_power_tf_r5_u4_routed.kicad_pcb` is the
  deterministic TPS63070-island candidate.  SHA-256:
  `BC4B13F8764965B0FBD3B9F65A2183DC9B8C46E9025229006E6C1BB6CC28A8E4`.
- `staging/mf1750_wroom_b3_power_tf_r5_bq_powerpath_routed.kicad_pcb` adds
  the reviewed BQ24074/PowerPath branch.  SHA-256:
  `4B0FBC2BA0EA5E6C3F3569648823C5A1E06A238291D9A024D82D07535E279C89`.
- `staging/mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb` is the cleaned
  route-chain baseline.  It preserves B2 and reduces the prior R6 findings to
  13 known items while retaining 141 unconnected items.  SHA-256:
  `88DFC906BD8D15ADCCECC54CCDBB9A6D2E5F1EC3149EDE199475923BA22C1CF8`.
- `staging/mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb` adds the ten
  reviewed EPD MCU-side networks.  SHA-256:
  `ADF3A61C2231049F4A50B6BA97D95D5BD7B7FE9FF54BE3F27469EB3F78CDC009`.
- `staging/mf1750_wroom_b3_power_tf_r8a_internal_control_routed.kicad_pcb`
  adds only `/USB_INPUT_VALID_N`; `r8b_dcdc_pg_routed` then adds
  `/DCDC_PG`; `r8c_pwr_int_n_routed` then adds `/PWR_INT_N`.
- `staging/mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb`
  is the current unified candidate.  SHA-256:
  `9A0F1E309ABE27CC8577404E2EF62A719CA7A39934553023C941BFF5B5C62403`.
- `staging/r8d_epd_internal_dcdc_pg_pwr_int_edge_access_report.json` binds the
  full route ancestry, exact UUID/geometry preservation, DRC, connectivity,
  edge-placement changes and deterministic double build.  SHA-256:
  `5D40570068144CF192CD73B403C5773D663A6677A0C363B6FAA22677AB6B0EF6`.

R8d preserves the protected B2 display region, all ten EPD MCU-side routes and
the three reviewed internal control branches.  SW1--SW5 now face the left
edge, J5 USB-C faces left, J4 microSD/TF faces the lower edge, and the current
reversible J6 candidate faces the lower edge.  Fresh KiCad 10.0.3 gates report
native parity 0, board verifier 13/13 PASS, deterministic byte-identical
rebuilds, no B2/antenna/In1 intrusion, 13 inherited DRC findings and 123
unconnected items.  The 13 findings are the twelve 0.20 mm WROOM thermal-pad
drills and one preserved `/EPD_SW_3V3` dangling track.  `/DCDC_EN` was tested
separately but did not pass the zero-new-DRC gate and is not part of R8d.

## Remaining release gates

1. Route the remaining internal controls (`/DCDC_EN`, `/PS_HOLD`), button and
   service signals, then the remaining `SYS_3V3`/battery/power distribution.
2. Keep TF as SPI-only in this revision; route it on F.Cu over continuous In1
   GND after the final clock limit is frozen.
3. Enter the exact JLC04161H-7628 four-layer stackup through a verified KiCad
   editing path, then calculate and route USB as 90-ohm differential.  The
   KiCad 10.0.3 Python stackup API probe failed closed and deliberately did not
   generate a candidate board.
4. Resolve the twelve WROOM thermal-via drill violations and decide the
   via-in-pad filling/tenting process.
5. Freeze the battery pack/J6 mating connector and `BAT+ / GND / NTC` physical
   wire order, improve the current J6--C49 assembly margin, and approve the
   enclosure openings, button travel, TF/USB insertion envelopes and Z-height.
6. Reach the documented zero-open target, complete return-path/thermal/RF and
   manufacturing reviews, then promote a staging PCB to the formal path.
