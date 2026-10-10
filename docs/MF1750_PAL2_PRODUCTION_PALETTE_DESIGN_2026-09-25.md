# MF1750 PAL2 生产 OTP 路径调色板标定设计

> 日期：2026-09-25。状态：离线构建完成，待现场执行。
> 前置：[`MF1750_PAL1_MEASURED_PALETTE_CHAIN_DESIGN_2026-09-24.md`](MF1750_PAL1_MEASURED_PALETTE_CHAIN_DESIGN_2026-09-24.md)（PAL1 链与其缺陷史）、
> `.test-output/offline/PAL1_CAL_ANALYSIS_20260925_V1/bright-findings.json`（PAL1 亮光批发现：L535 active 渲染的不是 stock Spectra-6 索引语义——码 1 实测浓品红而非白，schema 物理门 fail-closed，palette v1 暂缓）。

## 1. 动机与根因承接

PAL1 的"渲染路径=生产路径"假设被亮光数据证伪。已实证的生产路径（2026-09-25 代码审计）：

- `src/main.cpp` POST `/api/frame` → `src/epd_driver.cpp`（init 不发 0x20、不传 LUT，OTP 波形）；
- stock 码语义 `src/epd_config.h:52-57`：0 黑 / 1 白 / 2 黄 / 3 红 / 5 蓝 / 6 绿；
- 4bpp nibble 直写 DTM（`host/epd_frame` 打包器即该契约的 host 侧实现）。

PAL2 在此路径上重测 6 物理码，产出 calibrated=true 的实测调色板（替换 synthetic 闸）。

## 2. 标定帧（与 PAL1 的对照实验设计）

- **布局与 PAL1 完全同构**：每侧 8 列 × 8 行，列 c=码 c，帧几何/ROI 网格不变。
- **码 4/7 双拒绝**（host `validate_frame` 与生产固件 `epdValidateFrameColors` 都不接受 4/7）→ 退路：码 4/7 列填白（码 1）。白参照列=码 1（列 1 与列 7 均为白）。
- 六个共享码列（0/1/2/3/5/6）与 PAL1 帧**逐字节相同**（`pal1_column_comparison: PASS` 已封印于 `PAL2_SWATCH_20260925_V1/report.json`）——PAL1 亮光批 vs PAL2 批构成"L535 active vs OTP 唯一自变量"对照。
- 帧：`.test-output/offline/PAL2_SWATCH_20260925_V1/pal2.frame4bpp`（sha256 `d1a9577c…`），kit contract `ff023231…`。

## 3. 现场执行序列（frame_tool 治理结论）

`tools/mf1750_frame_tool.py` 治理要点（已全读）：

- 帧校验先行：`validate_frame`（307200 字节 + 码 ⊆{0,1,2,3,5,6}）在任何 URL 处理之前；畸形帧永远到不了设备。
- 刷新硬条件：`--refresh` 必须同时给 `--url`、`--confirm-cold-start`（≥10s J2-1 断电后的冷启动确认）、**恰好两个 `--controller-mapping`**（CS1、CS2 顺序）；本机映射 `0,0,0,0` 与 `1,0,0,0`（`epd_config.h`：CS1 左半、CS2 右半、无翻转无 nibble swap）。
- preflight `GET /api/version`：build tag 白名单（RC2G BUSYEDGE 系）、Panel/Frame bytes/PSRAM/SPI Hz/映射全校验。
- POST 202 → job 轮询（queued→running→completed，fnv1a/时间序/结果校验）→ `GET /api/diagnostic/report` 全量诊断校验（operation/job 恒等、BUSY 时序、DTM 双哈希、safe finish）。
- **无一次性 claim、无刷新计数门**（生产固件无 campaign 架构）；放行证据用手工密封批次记录（参照 PAL1 批次 `user-release`/`camera-review` 模式）。
- 生产固件**没有 campaign boot 绑定，复位安全**（与 PAL1 链的"刷写后严禁复位"规则不同——NV S 不变砖）。

操作序列：
1. 构建生产固件：`pio run`（默认 env `esp32-s3-devkitc-1`，产物 `.pio/build/esp32-s3-devkitc-1/firmware.bin`；已离线编译验证 SUCCESS）。
2. 现场刷写由主代理做（app 写流程）；relay ON。
3. `PYTHONPATH=. python tools/mf1750_frame_tool.py --url http://<ip> --refresh --confirm-cold-start --controller-mapping 0,0,0,0 --controller-mapping 1,0,0,0 --output <批次>/pal2.frame4bpp --force`（`--pattern` 默认 fixture 与 PAL2 帧无关——frame_tool 只生成自己的 fixture；PAL2 帧由 swatch 工具产出，frame_tool 当前不接受外部帧文件上传，上传路径需主代理按其现场惯例改派或用既有上传工具；**治理结论以 frame_tool 校验语义为准**）。

   > 备注（如实）：frame_tool 的 `--pattern` 只覆盖内置 fixture，PAL2 自定义帧不在其列；现场上传若走 frame_tool 需先扩 `--frame-file` 入口（本次未扩，避免动生产工具的冻结面），否则用既有上传路径（9 月批次有先例）并把 frame sha `d1a9577c…` 写进批次证据。
4. 亮光批（0.85 硬门）拍照 10 帧+锚帧。
5. 提取：`tools/mf1750_pal2_photo_extract.py --frames-dir <批>/pal2-frames --stage PAL2 --package .test-output/offline/PAL2_SWATCH_20260925_V1/analysis-kit --live-result <批次>/frame-evidence.json --middle-extraction .test-output/offline/LH1_REBOUND_MIDDLE_20260917_ANALYSIS_V1/extraction.json --anchor-frame <批>/post-pal2.jpg --output <分析目录>/extraction-pal2.json`。帧证据 JSON（`mf1750-pal2-frame-evidence-v1`）密封：frame_sha256 + refresh_report 绑定 + camera_review 绑定。
6. 调色板：`tools/mf1750_pal1_palette_build.py --extraction <提取> --package .test-output/offline/PAL2_SWATCH_20260925_V1/analysis-kit --provenance <批次>/palette-provenance.json --measurement-id <批次> --palette-out host/color_pipeline/palettes/mf1750_measured_v1.json --profile-out host/gamut_mapping/profiles/mf1750_measured_xyz_v1.json`（O_EXCL 正式路径）。provenance 的 `waveform_version='OTP_PRODUCTION_SRC_MAIN_2026'`、`firmware_commit`=生产 bin sha（现场刷写后填）。
7. 门预期：OTP stock 下黑 L* << 白 L*，schema 物理门应通过；双侧一致性 ΔL*≤3/ΔE00≤5；均匀性列规则（PAL1 已建档）同样适用。

## 4. 分析链

- 提取复用剂量/PAL1 网格管线（列=码钉定、码 7 白列缺失容忍、homography、blackhat）；PAL2 无 campaign 包，身份绑定=帧 sha + 密封批次证据。
- palette build 兼容：recipe `PAL2-C{c}-R{r}`、白码 1（`--white-code` 默认自动：PAL2 提取→1，PAL1→7）。
- 码 4/7 在 PAL2 是填白列，extras 留档语义不变（记录为白填）。

## 5. 对照读法

PAL1 亮光批（L535 active）与 PAL2 批（OTP stock）同布局同码列：逐（侧，码列）对比 ΔL*/ΔE00/Δh 即得 L535-vs-OTP 渲染差表；码 7（PAL1 白）与码 1/7（PAL2 白）做跨批白锚。

## 6. 首拍诊断（2026-09-25 亮光批）：混合屏，标定暂缓

亮光批提取 PASS（检测 40/64/侧，码 2/5/7 白列不可见由 homography 预测；RMSE ≤0.83px；0 质量失败；双侧 ΔE00≤1.97），但逐列判读给出决定性异常：

- 空间 identity 映射**确证无误**（候选列集播种 RMSE 0.45–0.48，备选集 RMSE ≥37；双侧一致；refresh-report 的 DTM 哈希在字节级验证过上传帧）——**不是 nibble swap、不是空间置换**。
- **决定性异常**：码 1（白）写在了列 1/4/7，却分别显示**紫罗兰 / 黄 / 白**。单一 LUT（任何置换/XOR/空间映射）不可能把一个 nibble 渲染成三种颜色——屏幕不是 PAL2 帧的纯净呈现。
- 鬼影证据：列 0/1/4 与 PAL1 L535 亮光批同列颜色高度吻合（C0 蓝灰、C1 浓紫罗兰、C4 黄绿）；而列 2/3/5/6 呈现 OTP 预期方向（白/红/白/深藏青）。**生产 /api/frame OTP 刷新没有把双稳态 PAL1 帧完全覆盖**（init 路径不发 0x20/LUT，亦未见全清动作），屏上为 PAL1↔PAL2 混合内容。
- **处置（已执行）**：palette v1 不写盘（混合屏无标定意义；正式路径未动）。
- **建议**：先整屏白清（生产全白帧刷新，或 R5 出厂 OTP 白恢复路径），确认全白后再做 PAL2 测量批。

完整证据：`.test-output/offline/PAL2_CAL_ANALYSIS_20260925_V1/bright-diagnosis.json`（含 OTP vs L535 逐列对照表）。

## 7. v2 批判决（白清后重测）：实测 OTP LUT 表，schema 码表冲突，标定暂缓

白清+重发后的 v2 批与 v1 批逐列 ΔE00≤3.2——**v1 的"混合屏/鬼影"假设被否**：OTP 渲染是确定性的。空间 identity 再次确证（几何残差 + 9-17 映射 + DTM 哈希）。

**实测 OTP LUT（两批复现）**：`0=黑(蓝灰偏弱) / 1=蓝(浓紫罗兰) / 2=白 / 3=红 / 4=黄 / 5=白 / 6=暗(近黑藏青) / 7=白`，即 OTP 呈现 `nominal[σ(c)]`，**σ=[0,5,1,3,2,1,0,1]**——白在 nibble 2（非 1）、黄在 nibble 4（非 2）、蓝在 nibble 1（非 5）、**绿完全不可寻址**。此前"码 1 三色"矛盾由此消解：列 1/4/7 虽同写码 1，对应的是 σ 的三个不同 LUT 项（5/2/1）。

**schema 冲突**：管线物理码表（`epd_config.h` 与 palette schema：0黑/1白/2黄/3红/5蓝/6绿）与本面板 OTP LUT 不符；按 schema 构建 palette 会把白保护驱成蓝墨（nibble 1=蓝）、且物理门（黄 b*>蓝 b*，两列皆白）必拒。**palette v1 不写盘**（正式路径未动）。

**决策点**（给主代理）：①管线颜色契约改为实测 OTP LUT（black=0/white=2/yellow=4/red=3/blue=1/green=OTP 不可渲染）；②或核实面板/OTP 变体（厂商 E1002 样例表 0黑/1白/2黄…与本面板 OTP 不符，MF1750 面板的 OTP 烧录可能为定制测试表）；③更正码表后重拍标定帧，schema 门预期通过；④PAL1 L535 批仍是唯一观测到绿色（nibble 6, hue 132）的路径。

证据：`.test-output/offline/PAL2_CAL_ANALYSIS_20260925_V1/bright-diagnosis-v2.json`（v1==v2 判据、σ 表、逐列 Lab、OTP vs L535 对照）。
