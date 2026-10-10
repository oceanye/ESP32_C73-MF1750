# MF1750 EC5 dither Atlas photo capture handoff

## Current evidence boundary

- Atlas action `ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c` completed once.
- Result file SHA-256: `056fc4e3186938d095b07ed09ab0c8c08459a069cb8a0ca92724bef594a3d475`.
- Result canonical SHA-256: `348ee35094d341b76ea681a2e426a021eeb0f47884fd60bd044207448d968c0b`.
- Permanent claim file SHA-256: `98ecff5a540fb76075f15088bf5297dde6aa5ea3622c4824bb7cf8799f2bff64`.
- Boot nonce used by the action: `027ed5c3c397f64a`.
- Device terminal state was `COMPLETE`, next ordinal `2`, with exactly one ARM, one EXECUTE, and one driver call.
- The operator's final near/mid-distance, electrical, thermal, continuity, and abnormality report has been sealed and independently validated.
- Manual observation file/canonical SHA-256: `00fcc331967abb32c40cf51d6bc872146fc89c1783a8fe033e575e672cfebfb9` / `86b63ab0f590d8f91570da3aba5010bdc968573549b00fc2b21e96b145a96458`.
- J2 is explicitly OFF, current is `0.00 A`, current/maximum temperature is `25/25°C`, and no white recovery has been authorized or executed.

The electrophoretic image remains visible with J2 OFF. Photographing it does not require reconnecting J2. If the ESP32 USB, reset, firmware, or wiring changes before ordinal 2, report that change before white recovery because the ordinary ordinal-2 gate requires the same boot.

## Completed operator capture checklist

- [x] Keep J2 OFF; do not refresh the panel before photography.
- [x] Place a clean matte white A4 sheet beside the panel, as close as practical to the same plane and under the same illumination. Keep a substantial unclipped white-paper area visible without covering the panel.
- [x] Take the full-panel and two near-grid photographs below with unchanged camera settings.
- [x] Upload the original camera files, not screenshots or social-app compressed copies.
- [x] Report whether ESP32 USB/reset/flash/refresh/rewiring changed while away, plus current panel current, current/maximum temperature, residual or banding, and any sound, smell, or heating.

## Preliminary full-panel+A4 photo received at 21:16

One chat-delivered JPEG has been preserved and analyzed without any device access. It is 1706×1279, 92,840 bytes, has no EXIF, and is therefore treated as a likely messaging-compressed preliminary image rather than the requested original camera file. Its SHA-256 is `550bd3f993fcdf89274bad9a4aba529991bb0a824c768fbc8273b769133db5df`.

The perspective registration aligns all 70 analysis rectangles with the displayed cells. The sampled A4 region has zero pixels clipped at the 8-bit threshold of 250 and is usable as an uncalibrated camera-relative white reference. Both controller halves preserve monotonic endpoint ordering in all seven rows (`14/14`). Across each row, all 28 adjacent recipe steps are separated in this photograph by camera-relative ΔE76 `6.07–26.80`. Corresponding left/right cells have mean/max camera-relative ΔE76 `4.2868/10.7674`; this single oblique, unevenly illuminated compressed photograph cannot distinguish controller variation from lighting and viewing geometry.

The camera-visible intermediate families are consistent with orange/ochre, pale yellow, yellow-green/olive, purple/indigo, brown, teal/blue-green, and pink. These are spatially mixed perceived appearances, not proof of a new single-pixel pigment state or waveform/LUT colour.

The sealed preliminary report is `.test-output/offline/MF1750_EC5_DITHER_ATLAS_PHOTO_REAL_20260818_V1/photo-analysis.json`, file/canonical SHA-256 `286454efdcfc49fdf29b4b33d2c38ceee03ac4244405ab18f58a9c334b5e888d` / `4f02edd87cced3c66cfee5fae166998c47dc8a6abed7ab30959466c0ffbbbcbd`.

At that point, the original camera file, close-ups, operator judgment, continuity report, and electrical/thermal fields were still required. They were subsequently supplied and are sealed below; the preliminary image alone did not release ordinal-2 white.

## Full-resolution three-photo set received at 21:24

The requested photo evidence is now present and preserved:

- right-half close-up: 3072×4096, 6,738,294 bytes, SHA-256 `d7bce5d590217045f245a87cb90eceee6931d199c6cbae0478897384851f3f3e`;
- left-half close-up: 3072×4096, 9,513,508 bytes, SHA-256 `9cf8814ed7282132fec04d0a5881abd930069ba83f667cd6a6deb1c880848e36`;
- full-panel+A4: 4096×3072, 9,269,912 bytes, SHA-256 `ca74728e984fe7d5ff0b0b16c46afe9c28a5297e2ceda83d87ec122b64bdbbde`.

The files identify a Xiaomi 14 rear camera with HDR off and retain ICC/embedded camera metadata. The close-ups visibly resolve the periodic spatial pattern in columns 2–4 across both controller halves; the 50% cells show the expected fine checker-like texture and the 25/75% cells show the complementary sparse/dense texture. No mixed cell is replaced by an unintended solid fill. This is photographic confirmation of spatial mixing; exact recipe ratios remain established by the frozen frame/firmware identities rather than estimated from camera pixels.

An independent full-resolution perspective analysis again aligned all 70 ROIs. Its A4 region has zero high-clipped pixels, all `14/14` row projections are monotonic, and the 28 adjacent camera-relative ΔE76 steps span `5.24–24.70`. The first compressed view and this original view differ in projected B fraction by only `0.0110` mean / `0.0601` maximum, supporting stable ordering despite viewpoint and lighting changes. Corresponding left/right cells in the original full view have mean/max camera-relative ΔE76 `5.0928/13.0315`; these values still include illumination, angle, glass reflection, and camera-pipeline differences and are not controller qualification.

The sealed original-photo report is `.test-output/offline/MF1750_EC5_DITHER_ATLAS_PHOTO_REAL_20260818_V2/analysis-full/photo-analysis.json`, file/canonical SHA-256 `e0efc3268abfa9e2c2379c7af7571dc8fe8675237054492678c451211edb964a` / `251ce9eb069062f0ca761b99f8bbad28b86b6a9d892dac051d1483d4660939c0`. A 2× rectified inspection image is retained with SHA-256 `7a3565a5f8a1fcafb38b4f7e70cd532a3d77f9a5a6cdf259eda00aa84abe14e6`.

Photo evidence is complete. The operator subsequently supplied the required verbatim near/mid-distance judgment, electrical/thermal state, and boot/USB continuity; the formal observation is sealed below.

## Formal operator observation sealed at 21:55

The operator reported J2 OFF, `0.001 A` immediately after the action, `0.00 A` currently, maximum/current temperature `25/25°C`, no ESP32 restart, and no USB/reset/flash/refresh/rewire change since the Atlas refresh. Grid geometry, white gaps, edges, left/right ordering, approximately 1 m progression, and absence of residual, banding, sound, smell, or abnormal heating were all confirmed.

The seven operator colour-family words, top to bottom, are `橙/赭黄、浅黄、黄绿/橄榄、紫/靛、棕、青绿/蓝绿、粉红`. The operator explicitly reported that rows 2, 4, and 6 do **not** show a dot pattern to the unaided eye even at close range. This wording is preserved verbatim and is not rewritten as “all rows visibly show dots.” It does not conflict with the original close-up photographs resolving periodic pixel patterns: the two observations have different evidence levels and show that those three rows are already strongly fused perceptually for this viewer and distance.

The sealed observation is `.test-output/hardware/MF1750_EC5_DITHER_COLOR_ATLAS_REBOUND_LIVE_20260818_V1/ordinal-01-atlas-observation.json`, 2,555 bytes, file/canonical SHA-256 `00fcc331967abb32c40cf51d6bc872146fc89c1783a8fe033e575e672cfebfb9` / `86b63ab0f590d8f91570da3aba5010bdc968573549b00fc2b21e96b145a96458`. Deep validation passed with ordinal `1`, action `ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c`, MAP fidelity and sequence gate true, and retry/recovery/automatic-next-action all false. The record explicitly leaves `physical_colour_qualification_inferred=false`: these are spatially mixed appearances, not proof of additional single-pixel pigment states or a new waveform/LUT palette.

## Requested photographs

Keep the original full-resolution files and do not apply a colour filter.

1. Full-panel, front-on image from about 1 m. Include all four panel edges, minimize perspective, avoid glare, and do not use flash.
2. Near image from about 20–30 cm covering the full left 7×5 grid. Focus closely enough that dot/checker patterns can be seen.
3. Near image from about 20–30 cm covering the full right 7×5 grid under the same light and exposure.
4. Full-panel reference image with the clean white A4 sheet beside—but not covering—the panel. Keep the paper from clipping to featureless maximum white. It is a camera-relative neutral/exposure reference, not a colorimeter calibration.

If the camera supports it, keep white balance, exposure, focus, HDR, and lens selection unchanged across all images. Send originals rather than screenshots or social-app recompressions.

## Frozen grid meaning

Each half has the same seven rows. Columns run from pure A through three spatial mixtures to pure B.

| Row, top to bottom | Endpoint A | Endpoint B | Appearance name is only a hypothesis |
|---:|---|---|---|
| 1 | red | yellow | orange |
| 2 | yellow | white | light yellow |
| 3 | green | yellow | lime |
| 4 | red | blue | purple |
| 5 | red | green | brown |
| 6 | green | blue | cyan or sky blue |
| 7 | red | white | light pink |

| Column, left to right | A fraction | B fraction | Pattern |
|---:|---:|---:|---|
| 1 | 100% | 0% | solid A |
| 2 | 75% | 25% | 2×2 quarter-area dither |
| 3 | 50% | 50% | one-pixel checkerboard |
| 4 | 25% | 75% | 2×2 quarter-area dither |
| 5 | 0% | 100% | solid B |

## Prepared offline analysis

`tools/mf1750_ec5_dither_atlas_photo_analyzer.py` accepts either a tightly cropped panel photo or four panel-corner coordinates in TL, TR, BR, BL order. It perspective-rectifies the photo to the frozen 1024×600 layout, measures all 70 ROIs, compares corresponding left/right cells, checks camera-relative endpoint ordering, and emits rectified/annotated PNGs plus sealed JSON.

For the full-panel+A4 original, pass the paper rectangle in **source-photo pixels**, with the right and lower edges exclusive:

```text
--white-reference "x0,y0,x1,y1"
```

The report records the exact sampled rectangle, paper mean/median RGB, mean/std Lab, per-channel and any-channel high-clipping fractions, neutral relative gains, and for every panel ROI its Lab offset/ΔE76, RGB ratio, and neutralized camera RGB relative to the paper. If more than 5% of reference pixels have any channel at or above 250, the paper is flagged unsuitable for relative normalization. The A4 sheet remains an uncalibrated exposure/neutral reference and cannot provide absolute colour qualification.

The schema-V2 self-test uses a synthetic off-panel A4 region together with the frozen strict preview. It produced 70 ROI measurements, exact left/right camera ΔE76 of zero, a valid unclipped paper reference, and a sealed report at `.test-output/offline/MF1750_EC5_DITHER_ATLAS_PHOTO_ANALYZER_SELFTEST_20260818_V2/analysis/photo-analysis.json` (file/canonical SHA-256 `2ec46999baad0f49587075f6a0659e8c3e2e530d01f3c481f8bab5408a0e3750` / `3b7664f5b73d204de6bd87f2a8eba095dc22f961e29ac715a004bb65dcff6836`). The tool deliberately records these limits:

- camera-relative only;
- camera is not a colorimeter;
- no absolute colour qualification;
- no inference of a new single-pixel pigment state;
- no inference of a new waveform or LUT state;
- near-view and roughly 1 m human observations remain required.

## Next live gate

The exact ordinal-2 prior-result/observation evidence validates offline and its permanent claim remains absent. However, the first live attempt on 2026-08-18 stopped before claim or POST: direct read-only status proved that the device had moved from the Atlas boot `027ed5c3c397f64a` to a new boot `8c1391dabe9d1d31`. NVS correctly retained READY/next ordinal 2, while the new boot's ARM/EXECUTE/driver counters were all zero and its report was `NOT_EXECUTED`. The ordinary same-boot gate therefore cannot be used.

Ordinal 2 remains the one unconsumed visible action and still targets full clean white, but it is blocked pending a narrow reboot-resume review. The operator has been instructed to turn J2 OFF. No ARM, EXECUTE, firmware write, reset, or visible refresh is permitted until J2-OFF evidence and a replacement gate are completed and a later fresh J2-ON report is requested.
