# C2 六色量化与空间抖动移交（2026-08-04）

> 下列代码块保留 `7cc015e` 原始 C2 分支的 21/45-test 历史移交；当前
> schema v2 加固与联合回归结果见后文。

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

## 集成后安全加固（report schema v2）

- 物理色码与色名现在是不可交换的硬契约：`0=black`、`1=white`、
  `2=yellow`、`3=red`、`5=blue`、`6=green`。即使配置声明
  `calibrated=true`，交换黑白的配置也会在加载时失败，不能再破坏白底保护。
- 色表同时执行保守的 Lab 粗语义检查：black L* < white L*、red a* >
  green a*、yellow b* > blue b*，因此仅交换 Lab 而保留名称也会失败。
- Palette JSON 已升级到 schema v2。`calibrated=true` 必须提供结构化
  `calibration.measurement_id` 和精确 64 位十六进制
  `calibration.artifact_sha256`；未校准参考色表明确使用 `calibration=null`。
- `quantize_panel_image()` 以及直接用 `quantize_image()` 生成
  `1024x600` 整屏帧时，默认拒绝 `calibrated=false` 色表。只有受控实验可以
  显式传入 `allow_uncalibrated_palette=True`，且该授权会写入报告；小尺寸离线
  回归仍可安全使用参考色表。
- 任意非 `1024x600` 尺寸只要也会打包成 307200 字节，就会在量化前直接
  失败；`2048x300`、`512x1200` 已作为回归反例。报告分别记录
  `canonical_panel_dimensions`、`panel_frame_bytes_output` 和
  `authorization_reason`，不再输出可能造成假阳性的总括授权布尔值。
- 量化报告升级为 schema v2。报告新增输入紧密像素字节 SHA256、RGB/RGBA
  模式、像素字节数、top-left row-major、IEC 61966-2-1 sRGB 传递函数、
  straight-alpha/线性光白底合成约定、pipeline version/build ID，以及整屏色表
  授权状态。输入 SHA256 的范围仅为已解码紧密像素字节；尺寸和模式作为独立
  必填来源字段保存。
- 报告明确把 straight-alpha/IEC sRGB 标记为 caller declaration，而不是测量
  事实；有效色表和报告均提供定义了范围的 canonical SHA256。两者只用于审计
  与复现，不是数字签名，也不是信任库判定。
- Palette/Options 参数、palette schema version、公开颜色数值入口均采用严格
  类型与有限值检查；bool、字符串、NaN、inf 不能再被静默转换或截断。
- 这些变化仅是主机侧安全契约与可复现来源加固，`Hardware tested` 仍为
  `NO`，也不声称参考 sRGB 色表已经获得实屏校准。

本轮加固验证：`python -m unittest tests.test_color_pipeline -v` 为 29 项通过；
当前全仓 `Ran 152 tests`、`OK`，repository contract、`compileall` 与
`git diff --check` 均通过。该计数是本轮共享工作树快照，最终集成仍应以提交后
CI 为准；`Hardware tested` 仍为 `NO`。

## Palette safety boundary

`host/color_pipeline/palettes/reference_srgb_v1.json` contains mathematical
sRGB/D65 anchors only. It is intentionally marked:

```json
"schema_version": 2,
"calibrated": false,
"calibration": null
```

A measured profile must retain the six physical codes `0,1,2,3,5,6`, record a
non-empty source, explicitly use `D65` / `2deg`, and set `calibrated=true` only
after controlled measurement. Each code must retain its canonical physical
name (`black`, `white`, `yellow`, `red`, `blue`, `green`); names are contract
semantics rather than editable labels. A calibrated profile must reference its
measurement artifact by ID and SHA256. D50 or 10-degree data is rejected rather
than silently compared with the D65/2-degree input pipeline.

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
