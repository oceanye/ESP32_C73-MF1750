# C2 六色量化与空间抖动移交（2026-08-04）

```text
Work package ID: C2
Baseline commit SHA: c59a1f2 (C1 + C5), based on main 3033da0
Branch name: feature/color-dither
Objective: 将已解码 RGB/RGBA 栅格确定性转换为规范六色 4bpp 帧，并输出预览 PNG 与可审计使用率/哈希报告。
Files changed: host/color_pipeline/, tests/test_color_pipeline.py, docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md
Files intentionally not changed: src/, hardware/, platformio.ini, hardware/mf1750_production_v1/production/
Assumptions: 输入为 top-left row-major 紧密 RGB 或 straight-alpha RGBA；透明像素在线性光中合成到白底；Lab 统一为 D65/2deg。
Commands run: python -m unittest tests.test_color_pipeline -v; python -m unittest discover -s tests -v; python -m compileall -q host tests tools; git diff --check
Exact test output / exit codes: C2 21 tests OK；C1+C5+C2 共 45 tests，Ran 45 tests in 10.315s，OK；全部命令 exit code 0。
Hardware tested: NO
Known limitations: bundled reference-srgb-v1 is calibrated=false and is not an MF-1750 measurement; input decoding/resizing/EXIF orientation are outside C2; pure-Python exact CIEDE2000 full-photo conversion may take tens of seconds.
Risks requiring integrator review: replace the reference palette with controlled six-patch D65/2deg Lab measurements before judging panel colour; conduct subjective screen acceptance for white protection, edge threshold and dithering; do not label CI or preview success as hardware success.
Suggested merge order: D0 baseline -> C1 -> C5 -> C2
```

## 远端验证与集成状态

- `feature/color-dither` @ `7cc015e` 已推送；
- [C2 Actions run 30862376043](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862376043)
  的 45 项分支回归与 PlatformIO release 编译成功；
- 已合入 `integration/host-fast-refresh-ci-color`，代码合并点 `42773d4`；
- [完整集成 Actions run 30862770816](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862770816)
  成功，仍明确为 `Hardware tested: NO`。

## Delivered contract

- Reuses C1 `pack_pixels`, `validate_frame`, physical colour codes and FNV-1a;
  nibble packing is not reimplemented.
- `quantize_panel_image()` only accepts `1024x600` and returns exactly 307200
  bytes. `quantize_image()` accepts smaller even-width rasters for tests and
  offline exploration.
- Conversion is IEC sRGB transfer -> linear RGB -> D65 CIE Lab. Nearest-colour
  selection uses CIEDE2000. The implementation is checked against all 34
  Sharma/Wu/Dalal supplementary pairs in both directions.
- Modes: nearest/no dither, serpentine Floyd-Steinberg, serpentine Atkinson,
  Bayer 8x8 and deterministic 32-bit-seeded hashed thresholding.
- Hashed thresholding is not claimed to be blue noise. No global random state
  is used.
- White protection blocks near-white neutral pixels from accepting or emitting
  diffusion error. Edge protection uses maximum linear-RGB channel difference,
  including similar-luminance hue boundaries. Text mode is explicit black/white
  thresholding, and its report records the effective no-dither/no-edge path.
- `preview_png()` is a deterministic, dependency-free, 8-bit RGB PNG encoder.
  Reports contain palette provenance, all six usage counts/ratios, SHA256,
  FNV-1a and `hardware_tested: false`.

## Palette safety boundary

`host/color_pipeline/palettes/reference_srgb_v1.json` contains mathematical
sRGB/D65 anchors only. It is intentionally marked:

```json
"calibrated": false
```

A measured profile must retain the six physical codes `0,1,2,3,5,6`, record a
non-empty source, explicitly use `D65` / `2deg`, and set `calibrated=true` only
after controlled measurement. D50 or 10-degree data is rejected rather than
silently compared with the D65/2-degree input pipeline.

## Reproduce

```powershell
python -m unittest tests.test_color_pipeline -v
python -m unittest discover -s tests -v
python -m compileall -q host tests tools
git diff --check
```

The small 16x12 regression fixture freezes raw-frame SHA256 for all five modes.
PNG tests check signature, chunk CRC, dimensions and decompressed RGB instead of
freezing the compressed stream, because zlib output can differ by runtime.

Reference for the numerical CIEDE2000 tests: [Sharma, Wu and Dalal,
"The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary
Test Data, and Mathematical Observations"](https://www.ece.rochester.edu/~gsharma/ciede2000/ciede2000noteCRNA.pdf).
