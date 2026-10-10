# MF1750 L535 帧路径固件变体设计（全彩 demo 上屏）

> 日期：2026-09-26。状态：设计冻结候选，纯文档（不改固件、不编译、无设备动作）。
> 前置：[`MF1750_PAL1_MEASURED_PALETTE_CHAIN_DESIGN_2026-09-24.md`](MF1750_PAL1_MEASURED_PALETTE_CHAIN_DESIGN_2026-09-24.md)（PAL1 链、缺陷史、运维警示）、
> [`MF1750_PAL2_PRODUCTION_PALETTE_DESIGN_2026-09-25.md`](MF1750_PAL2_PRODUCTION_PALETTE_DESIGN_2026-09-25.md)（OTP 路径与实测 OTP LUT σ=[0,5,1,3,2,1,0,1]）、
> `.test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1/manifest.json`（demo 帧/预览/调色板绑定）。

## 1. 目标与范围

让生产式帧路径（POST `/api/frame` 接收任意 4bpp 帧）走 **L535 active runtime LUT**（R20 加载）而非 OTP，使
`.test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1/demo.frame4bpp`（sha256 `e11bee605910e71a9556d64655e4812768eb782ce751ab8d2a4807e393cc4244`）
这类 L535 语义帧正确呈色（实测 L535 码→色：黑=3 / 白=7 / 黄=4 / 红=1 / 绿=6 / 蓝=0，见
`host/color_pipeline/palettes/mf1750_l535_measured_v1.json`，canonical `50bd8193…`）。

与 OTP 路径**并存**：palette 按 `render_path` 选择（`otp` 为 stock 语义、`l535_r20` 为实测 L535 语义；schema 扩展见 `host/color_pipeline/palette.py` 的 `RENDER_PATH_*` 与 `host/gamut_mapping/profile.py` 的同名扩展）。本变体只做 L535 demo 上屏，不动生产 OTP 行为。

## 2. 固件变体设计

**生产路径现状（2026-09-25 代码审计）**：
`src/main.cpp:1370-1373` 注册 `/api/frame`（刷新）与 `/api/diagnostic/frame-ingress`（不刷新）；
`finishFrameUpload`（`src/main.cpp:1098`）经 `queueEpdJob`（`src/main.cpp:1128`）入队，job 派发在
`src/main.cpp:1425-1426` 调 `epdDisplayFrame(frameBuffer, EPD_FRAME_BYTES)`；
`epdDisplayFrame`（`src/epd_driver.cpp:2260`）→ `epdDisplayFrameAtFrequency`（`src/epd_driver.cpp:2213`）：
长度/频率校验 → `epdValidateFrameColors`（`src/epd_driver.cpp:2226`，实现 644，经 `epdIsSupportedColorCode` 630）
→ `epdPrepareCascade`（2233）→ 双侧 `epdStreamPackedFrameController`（1213）→ `epdSecondSettingAndRefresh`（547：PON/BTST2/DRF/POF）。

**变体注入点**：在 `epdDisplayFrameAtFrequency` 的 `epdPrepareCascade` **之后、DTM 写帧之前**插入 L535 LUT 加载，序列完全复用已审封印链的生成驱动：
`.test-output/offline/PAL1_CAL_20260925_R2/generated/pal1_cal_v5_driver.inc:313` `phUploadRuntimeLutToController()`——
0xE9 隐藏使能（`kHiddenEnable={0x01}`）→ 等 idle → 0x20 写 R20 payload（`ph_lut::active::kR20Payload`，799 字节）
→ 0x21 写 R21 payload；逐控制器各一次（643/647 行）。LUT 数据本体 =
`src/generated/spd1657_legacy_535_reference.inc`（`kR20Command=0x20` 行 50、`kR20PayloadBytes=799` 行 43、payload sha256 行 21），
该文件被 PINNED 进所有封印包（`tools/mf1750_lightness_history_firmware.py` PINNED 表）。

**顺序判定：先 cascade init，再加载 LUT，再写帧**。理由：①L535 链三代固件（LH1/LH2/LH3/PAL1）的 frozen 驱动都是这个顺序且经 native 审计 + 真屏验证；②0x20 写表需要面板已上电完成 init（0xAA/PWR/PSR 序列在 `epdPrepareCascade` 内）；③先收帧再加载没有收益且违反既有验证面。注意：生产 init 的 `epdData(0x20)`（`src/epd_driver.cpp:905`）是 0xAA 命令的**数据字节**，不是 R20 LUT 命令——"init 无 0x20"指的是无 0x20 **命令**。

**`epdValidateFrameColors` 放行 0..7**：变体在 `epdIsSupportedColorCode`（`src/epd_driver.cpp:630`）加变体分支（宏 `MF1750_L535_FRAME_PATH_BUILD`）：case 0..7 全放行。host 侧已对应：`validate_frame(frame, allowed_colors=list(range(8)))`（`tools/mf1750_l535_fullcolor_demo.py`），管线 `quantize_image`/`quantize_panel_image` 按 `palette.render_path` 选码集（`host/color_pipeline/pipeline.py` 中 pack/validate 两处的 `l535_r20` 分支）。OTP 默认路径行为不变（既有测试 pin）。

**DTM 映射沿用生产 identity**：`src/epd_config.h:43/47`（CS1=左半、CS2=右半、无翻转无 nibble swap）；PAL2 的 refresh-report 已实证设备 DTM 哈希与 host identity 映射逐字节一致（双控制器 fnv1a `2716789829`，`.test-output/hardware/PAL2_CAL_20260925_V1/refresh-report.json`）。

**白保护语义**：L535 下白=码 7；管线量化按 palette 码集走，无额外改动；变体固件的色表校验放行后，码 7 随帧直写 DTM 即白。

## 3. 清底策略

PAL2 教训（`docs/MF1750_PAL2_PRODUCTION_PALETTE_DESIGN_2026-09-25.md` §6-7）：OTP 直写不清底会留混合屏（v1 批码 1 三色矛盾即由此暴露并被 v2 证伪/确诊）。
L535 变体上屏前必须整屏白清，选 **OTP 生产全白帧路径**（`frame_tool --pattern solid-white`，fixture 名见 `host/epd_frame/fixtures.py:26`，本 bench 已于 PAL2 v2 前实证有效）：
生产固件在板上、路径已验证、无 LUT 加载依赖。LH3 白恢复链（R5 出厂 OTP 白恢复，`tools/mf1750_lh3_source_white_firmware_v1.py`）**不选**：它是一次性 claim 链，消耗白额度且引入 campaign 复杂度；全白帧刷新在双稳态屏上等效且零门槛。
清底后用相机确认均匀白场（block means 检查，参照 PAL2 批 `post-white-clear.jpg` 证据样式），再发 demo 帧。

## 4. 治理架构选择

**推荐：无 campaign（PAL2 式）**。理由：
- 生产式变体固件无 NVS campaign 架构，**复位安全**——PAL1 链的三连砖（R1 fixture 缺陷、R2 门/写路径错配、R3 dump 时序）全部源于 campaign boot 绑定；demo 上屏是探索性动作，不值得这个风险面。
- 放行证据用手工密封批次记录（user-release + camera-review + refresh-report 模式，PAL1/PAL2 批次先例）。
- campaign 链的一次性门（claim 先于 ARM、永久 claim）对"可能要调参重拍多次"的 demo 阶段是负担而非保护。

刷新预算：白清 1 + demo 1 = 2；qualified 保持 0。若 demo 后要固化行为再考虑转正评估，另起设计。

## 5. 安全/验收闸

- **版本预检**：`frame_tool` 的 `ALLOWED_BUILD_TAGS`（`tools/mf1750_frame_tool.py:54-63`）需加入变体 build tag（现场构建后填入；既有两条 RC2F/RC2G 生产 tag 不许复用——变体固件必须有独立 tag 使误刷即刻拒绝）。
- **帧 sha 钉定**：demo 帧 sha256 `e11bee60…` 写入批次证据；refresh-report 的 job/diagnostic 全量验证（fnv1a、DTM 双哈希、BUSY 时序、safe finish）沿用 frame_tool 既有校验面。
- **validate_frame**：host 侧 `allowed_colors=0..7` 显式校验（demo 工具已做）；变体端 `epdValidateFrameColors` 放行 0..7。
- **相机亮光门 0.85 硬门**（无 --force，同 PAL1 标定批纪律）。
- **与模拟预览的对照验收**：预览图 `.test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1/preview-quantized.png` 即预期呈色。冻结光学门 `MF1750_LIGHTNESS_TEST_V1_20260911`（`host/static_photo/lightness_test.py:26-44`：ΔL*≥2、ΔE00≥3、Δh≤5°、噪声 max(5×MAD, CI95)）的适用性：
  - **适用**：整屏白列/中性区的 L* 一致性、双侧一致（ΔL*≤3、ΔE76≤5 的 cross-controller 限）、噪声带公式。
  - **豁免**：Δh≤5° 的色相一致门——demo 帧的量化结果本来就把连续色映射到 6 个实测端点，屏上呈色=端点色=预览色，验收的是"屏上=预览"而非"屏上=原图"；对"屏上 vs 预览"的 ROI 抽检用 ΔE00≤3 + 噪声带即可。原图保真度（ΔE00 vs 原图）不是本实验目标，只记录不判定。

## 6. 执行序列（runbook）

1. fresh 枚举 → 相机 anchor → IP 绑定 → relay rebind（900 秒证据新鲜窗：`tools/mf1750_lh1_lh4_once_operator_v2.py:35` `EVIDENCE_MAX_AGE_SECONDS=900`，超窗全部重来）。
2. relay OFF → 刷生产固件 → relay ON → 白清（`frame_tool --pattern solid-white --url … --refresh --confirm-cold-start --controller-mapping 0,0,0,0 --controller-mapping 1,0,0,0`）→ 相机确认均匀白场 → relay OFF。
3. relay OFF → 刷 L535 变体固件 → relay ON（等 BUSY 稳定）→ 通电诊断。
4. 发 demo 帧（同 frame_tool 治理：帧 sha 钉定、双映射、job+diagnostic 验证）。
5. 亮光批（0.85 硬门）拍照：锚帧 + 10 帧 → 离线对照预览图验收（§5）→ 封存批次（手工密封证据）。

**刷写铁律**（PAL1 事故史）：J2-off 刷写；本变体无 campaign boot 绑定故复位安全，但**生产固件若含 campaign 链残留 NVS 不受影响**（保留命名空间只读即可）；demo 期间避免一切不必要的 MCU 复位仍是好习惯（任何串口开启都会拉 RTS）。

## 7. 回退方案

demo 结束后重刷生产固件（`.pio/build/esp32-s3-devkitc-1/firmware.bin`，sha256 `ba59c3d6111a15c3426eddedf63188bf323083fdca24dec98939835b43dacdc3`，与 PAL2 批 `app-flash-production.json` 绑定值一致）即回到 OTP 路径，复位安全。
屏幕终态建议：以**整屏白**（solid-white 帧刷新一次）结束——双稳态白场是对后续实验最干净的起点，也避免 demo 帧长期滞留的残影老化评估缺口。

## 8. 风险登记表

| 风险 | 缓解 |
|---|---|
| 温度依赖未标定（LUT 未含温度补偿） | 标定与 demo 同温（37±3°C 记录）；现场批次记录温度；后续若要正式化，另起温度扫描实验 |
| L535 表批次一致性（面板间 OTP/驱动差异） | 本调色板绑定 panel_id `MF1750-DEVKITC-B2-01`；换面板必须重测 PAL1 批 |
| OTP/L535 混用状态（变体刷回生产后 NVS/屏幕状态） | 回退即整屏白终态；两条路径 palette 文件分离（render_path 隔离） |
| 900 秒证据新鲜窗过期 | runbook 第 1 步集中采集；超窗重来，不豁免 |
| 亮光依赖（用户强光临时） | 0.85 硬门无 --force；不达标不动手（PAL1 纪律） |
| 变体误刷到生产用途 | 独立 build tag + 白名单即刻拒绝；生产 bin sha 钉定 |
| 码 4/7 语义混淆（OTP 拒、L535 放行） | host `validate_frame` 按 render_path 分流；变体宏隔离；文档钉死 |

## 9. 开放问题（给主代理）

1. 变体固件的具体载体：改 `src/main.cpp`+宏（与生产同树）还是独立 main（如 `l535_demo_main.cpp`+独立 pio env）？推荐后者（生产面零扰动），待主代理定。
2. 变体 build tag 命名与 ALLOWED_BUILD_TAGS 加入时机（构建后）。
3. demo 验收的 ROI 抽检密度（全屏 128 格 vs 抽 16 格）。
4. L535 表与 OTP 表长期是否合并为一个双模式驱动（本次不合）。

## 10. 实施记录（2026-09-26，构建完成，无设备动作）

**裁定落地**：独立 main + 独立 pio env；build tag `MF1750_L535_FRAME_V1_20260926` 已加入
`tools/mf1750_frame_tool.py` ALLOWED_BUILD_TAGS；验收按全屏 128 格；L535/OTP 不合并。

**载体修正（相对 §2 的字面表述）**：§2 描述的注入点在实施时改为**专用编译单元全拷贝**——
`src/l535_frame_epd_driver.cpp`（= `src/epd_driver.cpp` 386acdd3 全拷贝 + `MF1750_L535_FRAME_PATH_BUILD`
宏门控的 L535 块）与 `src/l535_frame_main.cpp`（= `src/main.cpp` 拷贝，仅换 build tag 与 boot banner）。
原因：仓内 17 份历史封印包的 manifest/contract 绑定 `src/epd_driver.cpp` 的 sha256
（386acdd3…），另有 3 处活钉（`tools/mf1750_lightness_history_firmware.py` PINNED、
`tools/mf1750_p2_white_lh4_pack.py` LH4_SOURCE_SHA256、
`tests/test_mf1750_ec5_dither_effects_extension_firmware_contract.py`）——任何原地改动都会使全部
once-runner 校验与 pack 测试系统性转红，而修改封存档案属于篡改证据。专用 TU 是本仓既有变体惯例
（chroma_grid / blue_history_focused 等同构），生产面**零扰动**由构造保证。
宏名以本文 §2 的 `MF1750_L535_FRAME_PATH_BUILD` 为准。

**构建产物**（`.test-output/offline/L535_FRAME_FW_20260926_V1/`，自封 manifest）：
- 变体 env `esp32-s3-devkitc-1-l535-frame`：bin sha256 `cb25e57c424ad7c9be703268afe6d944800b2a636af938bc8713508763d204ae`
- 生产 env `esp32-s3-devkitc-1`（当前工作树直编）：bin sha256 `ba59c3d6111a15c3426eddedf63188bf323083fdca24dec98939835b43dacdc3` —— 与 PAL2 批 `app-flash-production.json` 现场绑定值**逐字节一致**，零差异成立
- 中途曾验证原地 #if 方案在宏关闭时的等价性（strip debug 后 .o 逐字节相同；bin 差异仅 65 字节、全部落在 esp_app_desc.app_elf_sha256 自引用字段与镜像尾部校验/SHA-256），该方案已废弃，仅作记录

**测试**：目标套件 255 passed + 122 subtests；platformio.ini 扫描类 44 passed + 4 skipped；
`tools/check_repo_contract.py` passed: True；lh1/lh2 once-runner 与 pal1/lh3 pack 钉值测试全绿。

## 11. 批次结果（L535_DEMO_20260926_V1，2026-09-27 上午，亮光 ratio 1.013）

**执行**：刷新预算 2/2 用尽（OTP 全白清底 1 + L535 demo 帧 1），qualified 0/256，无重发。
两次 app-only 刷写（变体 cb25e57c 进、生产 ba59c3d6 回）verify 全过，NVS 未动，终态 relay OFF、
生产 RC2G 身份恢复、屏上保留 demo 帧。批次证据自封：
`.test-output/hardware/L535_DEMO_20260926_V1/manifest.json`（canonical sha `88339344a6b4915e8775bc0cf44b8bcfba7207b1314bea858578aa72ede44cb6`）。

**结果**：协议面 PASS（两次刷新 job/diagnostic 全量验证，DTM 双哈希=identity 映射）。
光学验收 **FAIL**（§5 门）：屏上内容 = demo 帧经 L535 LUT 呈色（六色族齐，含 OTP 不可寻址的绿；
三角形量化伪影逐像素对应预览），但相对 host 帧坐标系**整体旋转 180°**
（global-180 相关 0.766，其余 10 种几何候选 ≤0.31；帧 unpack==预览逐字节一致、DTM=identity、
面板/相机物理朝向经胶带标记逐帧排除翻转）。根因未定，候选与矛盾点见批次
`acceptance-verdict.json`；需专用探针批次（建议：变体固件刷 PAL1 列帧复核朝向，
再按结果定位 PSR/TRES/半区映射层）。

**中途工具变更**：`tools/mf1750_frame_tool.py` 的 `perform_refresh`/`_validate_diagnostic`
增加可选 `allowed_colors` 透传（默认 None=stock 语义不变）。首次上传时 stock 校验在任何网络
I/O 前 fail-closed；刷新实际已在该次调用执行；随后用 `l535_verify_completion.py` 对设备不可变
证据离线完成验证（零额外设备变更）。pin 测试已补（`test_refresh_accepts_l535_code_set_with_explicit_allowed_colors`），
frame_tool 33+52、关联套件 88+70、`check_repo_contract.py` passed: True。

## 12. 朝向探针批次（L535_ORIENTATION_20260927_V1，2026-09-27 中午，照明 ratio 1.21）

刷新预算 2/2(PAL1 码列帧 + demo v2 源图 180° 预补偿帧），无重发；变体 cb25e57c 进出、生产
ba59c3d6 回刷均 verify pass；协议面两次刷新全 PASS(DTM 双哈希=identity)。

**朝向结论**:
- PAL1 码列帧（变体固件）= **upright**（列序升序 0..7，亮蓝列双侧均左二；与 09-25 PAL1 链渲染一致）
- demo v2 = **再次 180°**(v2 预览的 dihedral_2 相关 0.263 最优 = v1 意图 upright 相关 0.264 最优，互洽）
- 三次 L535 渲染呈**逐刷交替**:demo v1=180°(OTP 清底后）→ PAL1=upright(L535 后）→ demo v2=180°(L535 后）。
  DTM 逐字节一致排除固件/帧数据层；交替指向控制器扫描状态与 PSR 0xE9/0xE9-hidden/R20-R21 上传的交互。
  下批探针建议：同帧连刷两次逐拍验证交替；再接 OTP 刷新后两次连刷定位状态机入口。
- 附带发现：**L535 全刷新不完全自清**（PAL1 网格残留贯穿 demo v2)，批次计划"L535 全刷新自清"假设证伪。

批次证据自封：`.test-output/hardware/L535_ORIENTATION_20260927_V1/manifest.json`
(canonical sha `a857f1ae0dbdd78e1039f724f284c7675822c67e9b1924480b88f44213617002`)。
demo v2 离线包：`.test-output/offline/L535_DEMO_V2_20260927_V1/`（帧 sha `eb2a79ea…`）。
终态：生产 RC2G 身份恢复，relay OFF，屏上保留 demo v2 帧。

## 13. 交替探针批次（L535_ALTERNATION_PROBE_20260927_V1，2026-09-27 午后，照明 ratio 1.032）

刷新预算 2/2（同一 PAL1 码列帧连刷两次，sha `ee1704b2…` 钉定），无重发；变体/生产刷写均
verify pass；协议面全 PASS。**逐刷交替假设证伪**：两次连刷均 upright（亮蓝列双侧同位，
B-R 剖面 128.6/127.3、96.2/95.5 几乎相同）。

**当前认知状态**（详见批次 `alternation-verdict.json`）：
- 高置信数据链：demo v1=180°（OTP 清底后首刷，干净证据）→ PAL1×3=upright；demo v2=180° 为低置信（鬼影污染）。
- 存活模型：①"OTP 路径刷新后的首次 L535 刷=180°，链内后续 upright"（拟合全部高置信点）；
  ②帧内容相关（与数据无关路径矛盾，无机制）；③未映射的驱动历史态依赖。
- **几何寄存器已全部排除**（SPD1657B datasheet 提取件 `tmp/pdfs/spd1657b.txt`）：PSR A 的
  UD/SHL 扫描位两路径一致；PSR B 差异仅 LUT_EN(OTP↔MCU LUT)+FOPT；TRES 均 512×600；
  级联 M/S# 硬件固定。0xE9/0x20/0x21 为 datasheet 未载的厂商隐藏命令。
- 修复候选：①PSR 写后回读校验（datasheet：读命令 ALWAYS AVAILABLE）；②把 LUT 源字节并入
  init 的 PSR 写点、消除 0x69→0xE9 二次改写；③复核 R20 535B 前缀 vs 799B 全长
  （datasheet："命令须参数写全才生效"——535 前缀或致 R20 静默不全，全链共用此前缀）；
  ④双刷同帧清鬼影（本批量化：鬼影区均亮 88.5→95.8→100.9 / 99.0→109.2→113.3）。

批次证据自封：`.test-output/hardware/L535_ALTERNATION_PROBE_20260927_V1/manifest.json`
（canonical sha `621af71ffe5b5a25461727aa803df8298663da5554b4fb290a84f0266380ca8e`）。
终态：生产 RC2G 恢复，relay OFF，屏上保留 PAL1 帧（第 2 刷）。

## 14. 判别验收批次（L535_VERIFY_20260927_V1，2026-10-06 晨）——失败于刷新 #1

批次经两段中止恢复（J2 未接通→用户恢复；照明 0.752→开灯后 1.14 达标）。**刷新 #1（生产固件
OTP 全白清底）设备侧失败**：PON 正常（180ms）后 DRF 断言 BUSY 但 60s 超时未释放
（drf_ms=60001, timeout_stage=DRF, POF 清理已跑）；DTM 双哈希与帧哈希均一致（数据路径正常，
失败在驱动执行）。视觉：PAL1 网格残留，白清未完成。按纪律未重试，保护性 relay OFF 收尾。
0/256 qualified，消耗刷新 1/3。批次自封 manifest sha
`48c655581f6b275e9466897901d7f9117990d6e29ca9566ac14421ac547b1f79`。

**待查**：DRF 挂起候选——面板 9 天未通电深置、晨温偏低、供电轨异常、或多次实验刷新后的
硬件老化。模型①（OTP 后首刷 L535=180°）未获判别机会，留待面板恢复后重试。

## 15. 判别验收批次完成段（2026-10-06 上午，通电静置恢复后）

**恢复**：面板通电静置 20 分钟后 OTP 白清 DRF 21681ms 正常完成（对比超时 60001ms)——
深置粒子假设成立；白场干净（PAL1 残留全清，interior std 13.9)。

**模型①证伪**：demo 第 2 刷（同帧逐字节）仍 180°(transform-2 相关 0.606,identity -0.338;
ECC 精配 0.90)。更新后的完整证据表：**PAL1 帧 upright 3/3,demo 帧 180° 3/3**——朝向与帧内容
相关，机制未定（几何寄存器已全排除，数据路径逐字节验证；剩余未探区=厂商隐藏命令
0xE9/0x20/0x21 与显示 RAM 寻址的交互）。

**验收（demo r3,rot180 对齐后）**:§5 门 FAIL——raw 1/128 格 ΔE00≤3(median 19.89);
session 白锚归一化后 12/128(median 8.82)。单全局偏移可解释白/黑/黄（残差 3-7)，但绿
(median 20.4)、品红（11.4）偏离——强灯光谱与 09-25 标定日光逐色相不同。结构呈色精确，
色彩验收需在匹配照明（日光类、ratio~1.0）下重测。

批次总自封：`.test-output/hardware/L535_VERIFY_20260927_V1/manifest-final.json`
(canonical sha `2ed62019744f7d3e638dc1ada792ca52bb436880a83e59e55147c9305bd82c34`,
92 证据文件，含中止段/失败段/完成段）。终态：生产 RC2G 恢复，relay OFF，屏保留 demo r3 帧。

## 16. v2 变体固件构建（2026-10-06，纯离线）与 A/B 判别方案

### 16.1 R20/R21 取证修正（先纠正上批嫌疑表述）

`src/generated/spd1657_legacy_535_reference.inc` 头部注释（5–8 行）明确：**799 字节是本仓证据
容器，535 字节才是厂商 EDP_init.c 的两张身份钉定表全长**；535 之后的 264 字节全 0xFF 是为共享
799 容器而补的填充（"Stage-III reference builds transmit exactly the first 535 R20 bytes"）。
常量行：`kR20PayloadBytes=799`(43 行）、`kTransmittedR20PrefixBytes=535=7+6×8×11`(44 行 +
174 行 static_assert)、`kR21PayloadBytes=704` 且全 0xFF(45/31 行）。SPD1657B datasheet
（提取件 `tmp/pdfs/spd1657b.txt` 2915 行）的"参数须写全"指每条命令**自身**参数个数；R20 是
datasheet 未载的厂商隐藏命令，其参数个数由厂商加载器定义为 535。**结论："datasheet 要求
799"不成立；但"R20 写长是否影响渲染态"仍值得一次 A/B 排除**——v2 因而写全 799（尾部本来就是
0xFF，不引入新数据），与 v1 的 535 前缀构成干净对照臂。

### 16.2 v2 差异（env `esp32-s3-devkitc-1-l535-frame-v2`,tag `MF1750_L535_FRAME_V2_20261006`)

1. **单次 PSR 写**：级联 init 的 PSR 写点直接写 `{0x5F,0xE9}`(LUT_EN=1)，消除 v1 的
   0x69→0xE9 中途改写；helper 不再写 PSR。每刷后段的断电 PSR `{0x4F,0x6E}`（厂商断电序列）
   保留不动。
2. **R20 写全 799B**（容器全长，含 0xFF 填充尾）。R21 维持 704B 全 0xFF。
3. **PSR 回读不做**：本板无 MISO 线（`src/epd_config.h:27` 仅 MOSI)，控制器回读物理不可能；
   改为写侧取证——`/api/version` 追加 v2 写侧参数行（frame_tool `_parse_version` 兼容，
   行内含冒号即可）。
- 产物：`.test-output/offline/L535_FRAME_FW_V2_20261006/`,v2 bin sha
  `e1b6b754548fd2c0cad48911c75cbb2bfc6e78c4bf6df5bb0071889ea5b29a2d`,manifest 自封 sha
  `6b13cc072c62cce98d7c6762ff5a6058c121e1b9b5158fe34a8d222de6d78b54`。
- 零差异：生产 env 重编仍精确 `ba59c3d6…`,v1 env 仍精确 `cb25e57c…`；反汇编 diff 证据：
  init PSR `movi a10,105(0x69)→233(0xE9)`、helper PSR 写移除、R20 长度常量变更，其余一致。
- 测试：frame_tool/palette/pipeline/gamut 102 passed + 94 subtests;`check_repo_contract.py`
  passed: True;ALLOWED_BUILD_TAGS 已加 v2 tag。

### 16.3 A/B 判别方案（最小刷新设计，建议下一现场批）

**判别问题**:demo 帧 180° 的根因是否在 R20 写长（535↔799）或 PSR 二次改写。
**最小刷新预算 = 3**(qualified 0/256，照明 0.85 硬门，刷写铁律同前）:
1. 生产固件 OTP 全白清底（1 刷）——统一初态，顺带验证面板健康（记录 drf_ms)。
2. 刷 v2 变体 → demo 帧（`e11bee60…`）第 1 刷 → 拍照朝向判定。
3. 同帧第 2 刷 → 拍照朝向判定。

**判定矩阵**（朝向判据：几何候选相关 + 三角形伪影坐标 + 亮蓝区位置）:
- v2 两刷均 upright → R20 写长或 PSR 二次改写是根因，v2 即修复；顺势在日光类照明下补正式验收。
- v2 第 1 刷 180°、第 2 刷 upright → 修复改变了状态机但首刷仍受 OTP 残留影响；再加一刷确认。
- v2 两刷均 180° → R20 写长与 PSR 二次改写**双双排除**；剩余唯一未探区 = 0xE9 隐藏命令与
  LUT RAM 寻址交互 → 转向厂商资料核对（0xE9/0x20/0x21 语义函证）或受控寄存器实验（需带
  MISO 的转接板改造才能回读，记入硬件 backlog)。
**回退**：同前（relay OFF + J2-off 回刷生产 `ba59c3d6…`，屏保留最后一刷）。**附带观察**:
v2 的 799B R20 若改变鬼影/呈色（对比 v1 同照明批照片），为 R20 语义提供第二证据。

## 17. v2 A/B 判别批（L535_V2_AB_20261006_V1，2026-10-06 晚，照明 ratio 1.573）

刷新预算 3/3(OTP 白清 + v2 demo 两刷），无重发；v2(e1b6b754）进、生产（ba59c3d6）回均
verify pass；协议面全 PASS；面板健康 drf_ms=21691（与晨基线 21681 一致）。

**判别结论：R20 写长与 PSR 二次改写双双排除。** v2（单次 PSR {5F,E9} init + 全 799B R20）的
demo 两刷均 180°(transform-2 corr 0.553/0.549,identity ≈ -0.30)。朝向帧内容相关的最终统计：
**PAL1 帧 upright 3/3,demo 帧 180° 5/5**(v1×3 + v2×2)。datasheet 已载几何全部排除后，
剩余唯一未探区 = 厂商隐藏命令（0xE9/0x20/0x21）与显示 RAM 寻址的交互——现场手段到头
（无 MISO)，转厂商函证 + MISO 转接板硬件 backlog。

**务实路径**：demo 类帧在 host 管线预旋转 180°(L535_DEMO_V2 方法）即可上屏 upright
（变换按帧类确定）;PAL1 类帧无需补偿。色彩正式验收留日光轨（灯光谱不符）。

批次自封：`.test-output/hardware/L535_V2_AB_20261006_V1/manifest.json`,canonical sha
`0804b753b449e6858846fb5d619c9f8117423e46cf3c0c4259c369213f0e2f24`(59 证据文件）。
终态：生产 RC2G,relay OFF，屏保留 v2 demo r3 帧。

## 18. 色彩验收批（L535_COLOR_ACCEPT_20261007_V1，2026-10-09 傍晚，照明 ratio 1.102）

刷新预算 3/3(OTP 白清 + demo v2 两刷），无重发；v1(cb25e57c）进、生产（ba59c3d6）回均
verify pass;drf_ms=21691（三次 session 基线一致，面板健康）。

**结构验收 PASS**:demo v2 预补偿生效——屏上 = 原始 demo 意图 **upright**(vs rot180(v2 预览）
相关 0.389/0.384,vs 原样 v2 预览 -0.08);demo 帧渲染 180° 更新为 6/6 实证。屏上现为 upright
全彩 demo（保留展示）。**色彩门 FAIL**:raw 9/128 格 ΔE00≤3(median 9.66)；白锚 b\* 与调色板
几乎一致（-20.5 vs -20.5)，白色族最近（median 7.91)，品红 11.1、黄 14.4、**绿 30.0**
（实测 L\* 29.4 vs 标定 47.3——绿在本灯光谱下明显偏暗）。缝配对本批无可评对（N/A 非失败）。
无鬼影（白清+双刷干净，r2/r3 差 6.61 为噪声级）。

**结论**:L535 全彩 demo 链路**结构完成**（帧路径 + 预旋转补偿端到端验证）；绝对色彩验收被
照明卡住——调色板标定于 09-25 日光，灯光谱下色相敏感码系统性超门。最终 PASS 需同日光类
重拍或灯光谱标定。批次自封 manifest sha
`13d58460076b45f4642d14ce9cec920677babf12ac3836c1c63bd7a9177f3cc1`(68 证据文件，含台架
出框中止段）。终态：生产 RC2G,relay OFF，屏保留 upright demo。

## 19. 波形方案重启第一步：runtime_waveform 信封内任意表生成（2026-10-09，纯离线）

**首个注册格式**:`SPD1657_R20_L535_GEOMETRY_V1`(`format_registry.py` 生产注册表从空字典
变为恰好一项，MappingProxyType 只读；审查基础=PAL1 链严格 native 审计
`5b95aa0b…` + 真屏 PAL1 证据；loader 源=厂商 `EDP_init.c` 钉 `1b6bbcf3…`)。格式文档
`host/runtime_waveform/formats/SPD1657_R20_L535_GEOMETRY_V1.json`(canonical sha
`f45f161e…`)：结构 schema 535B=7B 头+6 组×8 record×11B,record 字段保持 OPAQUE。

**生成器** `host/runtime_waveform/l535_table_builder.py`:
- `from_reference(role)` 加载 active/commented 钉死表为可审计对象（active 前缀 sha 与
  `716cc229…` 钉值逐字节校验）
- `build_table(knobs)` 默认输出与 reference **逐字节相等**（硬测试钉死）；第一批旋钮=表头
  7 字节的 6 个命名参数（vsh_lv/vsl_lv/vsh_lv2/vsl_lv2/gate mV + pll_code，全部经
  3000+100n / 1000n 编码校验）,record 区默认原样继承；旋钮改动进 canonical manifest
- `to_candidate_manifest()` → contracts 候选（payload=plaintext_decoded_3bit_lut、双控制器
  535B 身份、电气段填表头电压域）;`canonical_manifest_bytes()` 直接接
  `execution_plan.load_canonical_manifest_bytes`

**合同七段现状**:panel/encoding/payload/operation_contract 四段首次真正可填；
provenance 部分可填（reference/loader/audit 身份齐）;electrical 部分（电压域在、
vcom/温度/帧率/相位时序缺）;recovery 保持 BLOCKED。可证门 4/13:
panel_and_batch_exact、dual_controller_3bit_format_documented、
plaintext_decoded_payload_available、register_sequence_reviewed；其余 9 门及深证据包
保持 fail-closed(record 语义、电气批准、温度 bin、OTP 等价、独立恢复、牺牲板授权、
功率门、控制器修订、loader 审查）。执行计划在已注册格式下仍正确要求完整 P0 证据包
（fail-closed 不变）。

**结构差分**(`.test-output/offline/WAVEFORM_STRUCT_DIFF_20261009_V1/`,bundle sha
`18a05192…`)：四张真屏表 record 级对照。关键：gate 0x14 四表通用（勿扰）;vsh_lv
6000..7200 四值均已真屏证明=**推荐第一扰动轴**(6000/6600/7200 阶梯）;pll 02↔03 最小
变更（次选）;vsl_lv 分域（L535=-15000 vs WF≈-8300，缓议）;active vs commented R20 表体
差 389/535 字节（XOR-3 的"只差表头"只适用于 PWR/PLL 全局配置，不适用于 R20 表体）;
全 FF record=no-op(WF20 21、WF23 13、active 8、commented 0)。

**测试**：新测试文件 16 项（注册/忠实性/旋钮/合同集成）;runtime_waveform+waveform+l535
相关套件 **119 passed**;`check_repo_contract.py` passed: True。两个既有 pin 测试按新
注册状态更新（registry 非空+读、reference 候选仍 BLOCKED_FORMAT_NOT_REGISTERED)。
