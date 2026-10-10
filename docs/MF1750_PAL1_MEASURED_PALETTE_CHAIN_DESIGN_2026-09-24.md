# MF1750 PAL1 实测调色板标定链设计（全彩 v0 主线）

> 日期：2026-09-24。状态：设计冻结候选。
> 前置：[`MF1750_E6_FULL_COLOR_INDUSTRY_SURVEY_2026-09-19.md`](MF1750_E6_FULL_COLOR_INDUSTRY_SURVEY_2026-09-19.md)（行业主线=实测调色板+抖动）、
> STATUS_HANDOFF 2026-09-24 15:40 条目（软件管线零缺口、唯一硬缺口=calibrated 调色板）、
> [`MF1750_LH3_DOSE_CHAIN_DESIGN_2026-09-21.md`](MF1750_LH3_DOSE_CHAIN_DESIGN_2026-09-21.md)（链架构与现场运维警示）。

## 1. 目标

产出 `host/color_pipeline/palettes/mf1750_measured_v1.json`：**calibrated=true** 的 6 物理码（0 黑/1 白/2 黄/3 红/5 蓝/6 绿）实测 Lab 调色板（palette schema v2，`palette.py:236`），绑定测量 artifact。附带产出实测 6 点 XYZ gamut profile（替换 synthetic 闸）。码 4/7 一并上屏测量留档（schema 外，供后续中间态研究）。

## 2. 链设计（单 action，active 全局头）

```
PAL1 (ordinal 1, active 全局头)  每侧 8 列 × 8 行；列 c 全列码 c（c=0..7）
```

- **渲染路径 = 生产路径**：active 全局头 + L535 active 表 + 冻结工厂驱动（与 LH3 SOURCE 同一电气路径；application 帧路径同表）。屏幕当前为 DOSE2 彩帧，active 全帧驱动不依赖起始历史（生产假设，本实验同时是它的又一项实测检查）。
- **布局与剂量帧相同**（列=码、行=8 空间重复）：直接复用 `mf1750_lh3_dose_photo_analyzer.py` 的 128-ROI 提取管线（列=码钉定、码 7 白列缺失容忍、homography）。
- 严格 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh；claim 先于 ARM；失败不重发；qualified 保持 0。
- 新 NVS 命名空间 `pal1_v1`；设备门断言：lh3dose_v2 终态（campaign complete）+ lh3dose_v1 fault 769 保留 + lh3srcw_v1 已消耗 + lh2map_v1 终态 + lhist_v1/lh1reb_v2 保留。
- **刷写后严禁任何 MCU 复位直到 action 完成**（2026-09-24 V1 事故教训，见剂量设计文档第 7 节）。

## 3. 测量（硬门槛：照明 ≥0.85 才动手）

- 1 整屏锚帧 + 10 同态帧；逐（侧，码列）8 格中位 Lab + max(5×MAD, CI95) 噪声。
- **照明门不达标不 ARM**（本次数据要跨 session 当校准基准用，0.85 是硬门，不接受用户特批放低——与剂量链的 session 内相对比较性质不同）。
- 白列（码 7）与 LH3 白 close-review 的同照明复核：本批白列 L* 与 9-17 亮场 65.8 的差异即 session 校准系数，写入调色板 measurement 块。

## 4. 交付件

| 件 | 说明 |
|---|---|
| 算法 `host/static_photo/palette_cal_pal1.py` | 单 stage PAL1，active 头，列=码布局（复用 base.placement） |
| pack `tools/mf1750_pal1_pack.py` | 单 action 包；ANCHOR_SHA 锚 = LH3 白 close-review 文件 sha（沿用 `5dd81034…`） |
| native 审计 + runner `tools/mf1750_pal1_once_v1.py` | validate/run --ordinal 1 |
| 提取 | 复用 `mf1750_lh3_dose_photo_analyzer.py`（或薄封装） |
| 调色板构建 `tools/mf1750_pal1_palette_build.py` | extraction → palette schema v2 JSON（calibrated=true、measurement_id、artifact sha 绑定、双侧一致性检查、白列校准系数）+ 实测 gamut profile XYZ |
| 测试 | 全绿 + 回归 + check_repo_contract |

## 5. 后续（PAL1 之后）

1. 端到端全彩 demo：实测调色板 + `quantize_panel_image`（蓝噪/FS 抖动）→ 帧 → 真屏显示一张照片（PAL2，又一次 1 刷新链）→ 相机验收。
2. 中间态扩展（码 4/7、MAP 中间态入 palette schema 扩展）视 PAL1 数据质量再定。

## 6. 缺陷记录 PAL1-R1-D1 与审计覆盖修复（2026-09-24 实证）

**现象**：R1 包（contract `405ab788…`）刷入后首次启动即 fault_locked，report error `compiled_fixture_self_check_failed`；fault 未持久化（cursor 仍为 1、phase READY），但 campaign boot 绑定已写入——此后任何复位都会锁死为持久 FAULT。零 ARM/EXECUTE/driver/刷新。

**根因**：冻结驱动的 `epdValidateCompiledChromaGridFixtures()` 遍历 `kRoles={Source,Mid,Target}`，`phValidateRole()` 以 `ph::kActions[phRoleIndex(role)]`（`phRoleIndex=(size_t)role`，Source=1/Mid=2/Target=3）取编译期 identity；而单 action R1 包的 identity 只编译了 `kActions[2]`（slot 0 + 1 个 action），**Mid/Target 越界读**，histogram/identity 比对永不可能通过。这是单 action 架构特有的坑：3-action 链（LH2/LH3 剂量）的 `kActions[4]` 天然覆盖三个角色。

**为何 native 审计 R1 放行（覆盖洞，如实记录）**：审计的 protocol fixture 用 `testFixtureResult` stub 替代了 `epdValidateCompiledChromaGridFixtures()`，driver-gate probe 只调用 `phLayoutValid`/`phBuildExpectedFrame`，从不索引 `ph::kActions`——直方图/帧恒等比对路径完全没有 native 覆盖。

**修复（V2 包 `PAL1_CAL_20260924_R2`，contract `e62946aa…`）**：
1. 固件：`kRoles={Source}`（fixture 只校验存在的角色）+ `phRoleValid` 收窄为 role==1（纵深防御）。
2. 审计（R2，`PAL1_CAL_NATIVE_20260924_R2`）：新增静态角色/identity 越界断言 + fixture 等价 probe（编译真实 `kFixtureRoles` 声明，逐角色检查越界+histogram+帧 FNV），并新增 pal1_v1 三个门拒绝场景。配套 `tools/mf1750_pal1_fixture_defect_repro.py` 实证：对 R1 包 `fixture_self_check_equivalent=0`（FAIL），对 R2 包 =1（PASS）。
3. NVS：`pal1_v1`（cursor=1、boot key 存在、fault 未持久化、零执行）作为不可触碰历史证据保留；V2 用 `pal1_v2/cur_pal2/boot_pal2`，runner claim 目录换为 `.mf1750_pal1_v2_action_claims`。

**教训**：凡改动 action 数/角色集，编译期 identity 表容量必须与冻结驱动的 fixture 遍历角色集一致；native 审计必须覆盖 fixture 自检的等价路径（角色×identity 边界+帧恒等），不能止于布局门。

## 7. NVS 门与地面真值（2026-09-24 晚，PAL1-R2-D2）

**现象**：V2 固件 boot 自检通过（R1-D1 修复有效），但 runner preflight 拒绝——设备 `source_nvs_complete=false`，即七段 `whiteSourceReady()` 门至少一段在真机 NVS 上不成立。

**地面真值**：esptool 只读读出 NVS 分区（副作用：RTS 复位把 pal1_v2 的 boot 绑定也弄死——零执行，与 pal1_v1 同为"未开跑即死"）。离线解析（`tools/mf1750_nvs_dump_parse.py`，封印报告 `.test-output/offline/NVS_DUMP_PARSE_20260924_V1/`）确认：`pal1_v1` 只有 `boot_pal1`、`pal1_v2` 只有 `boot_pal2`，**均无 cursor 键**；其余保留段（lhist_v1/lh1reb_v2/lh2map_v1/lh2srcw_v1/lh3srcw_v1/lh3dose_v1/lh3dose_v2）全部与 pin 值一致。

**根因**：V2 门要求 `isKey("cur_pal1") && ==1`，但固件 boot 路径（`initializeOrValidateCampaignBootBinding`）**只写 boot key**——cursor 首次写发生在 ARM 转移。因此 pal1_v1 门在真机永假。这是"门逻辑 vs 真机写路径"类缺陷；桌面 Preferences stub 预设什么就是什么，native 审计自身抓不到，故 V3 审计把封印的 NVS 解析报告作为对账输入（`nvs_ground_truth` 全量逐项比对，不符即 FAIL）。

**修复（V3 包 `PAL1_CAL_20260924_R3`）**：pal1_v1/pal1_v2 门改为"boot key 存在 + cursor 缺失或=1"（与地面真值一致，contract 块记录依据）；NVS 换 `pal1_v3/cur_pal3/boot_pal3`；runner claim 目录 `.mf1750_pal1_v3_action_claims`；审计输出 `PAL1_CAL_NATIVE_20260924_R3`（51 场景 PASS）。

**教训**：① 门常量必须以真机写路径为准——boot 只写 boot key，cursor 首写在 ARM；② 只读 esptool 操作（read_mac/读 NVS）同样触发 RTS 复位，campaign 未开跑时一样致死（见第 6 节与剂量设计文档第 7 节）；③ native 审计的 NVS 模拟是"作者写什么就有什么"，对账真机 dump 是必要补洞。

## 8. 门位图自诊断（V4，PAL1-R3-D3）

**现象**：V3 固件 boot 正常（ready / self_check pass / cursor 1），但 runner preflight 仍见 `source_nvs_complete=false`；九段门的期望值/实际值/类型与 NVS dump 地面真值逐位核实全部 MATCH，分析层面定位不到失败段。

**代码级复核结论（如实）**：对 vendored arduino-esp32 2.0.17 的 `Preferences` 实现逐行核对（`begin(ns, ro)` 只读打开既有命名空间、`isKey=getType!=PT_INVALID` 按序探测 i8..u64/str/blob、`getUShort`/`getULong64` 类型直读），与固件门用法无语义差异；九段门无 `#if` 分支包裹、无优先级/拼写问题、无第二处 `source_nvs_complete` 计算点。**未找到确定性代码级根因**——需要设备按段自报。

**V4 修复（包 `PAL1_CAL_20260925_R1`）**：
1. status/identity JSON 新增 `gate_detail` 位图（`old_fault/rebound_v2/lh2_map/lh2_white/lh3dose_v1/lh3dose_v2/pal1_v1/pal1_v2/pal1_v3/lh3_white` 十段，直读各 Preserved() 函数返回值；lh3_white 段从 whiteSourceReady 拆出为 `lh3WhiteConsumed()`）。runner 的 require() 是子集匹配，加字段向后兼容；且 runner 现在对任何携带位图的文档强制全 true。
2. 设备门新增 `pal1_v3` 保留段（boot key 存在 + cursor 缺失或=1；boot 09665a142b77a580 为 V3 首启写入、晚于 dump，值来自现场记录）。
3. NVS 换 `pal1_v4/cur_pal4/boot_pal4`；runner claim 目录 `.mf1750_pal1_v4_action_claims`。
4. native 审计 `PAL1_CAL_NATIVE_20260925_R1`（54 场景 PASS）：新增 `gate_detail_partial` 场景（lh2map 段置失 → status 200 READY 且位图 lh2_map=false、source_nvs_complete=false）+ read_only/chain 全文档位图全 true 校验 + pal1_v3 两个门拒绝场景 + NVS 对账扩展（pal1_v3 标注为 dump 后首启、现场值）。

**现场读法**：V4 刷入后 GET status，`gate_detail` 中唯一 false 段即失败段；若全 true 而 source_nvs_complete=false，则矛盾在 lh3_white 段拼接处（不可能，两段同函数直读）——届时把全量 status 拿回来离线对账。

## 9. pal1_v2 的 769 与 dump 时序教训（V5）

**确诊**：V4 的 `gate_detail` 位图十段中仅 `pal1_v2=false`，其余全 true。根因是时序坑：NVS dump（`read_flash`）结束时的 RTS 硬复位让 V2 固件二次启动 → campaign boot 绑定不匹配 → `enterFault` 持久化 **`cur_pal2=769`**（phase FAULT | ordinal 1）。dump 内容读于复位**之前**（故 dump 无 cur_pal2，解析无误）；写发生在 dump 之后。推断可靠性：V2 固件 ordinal 1 唯一可能的 cursor 写路径就是 boot fault 769（runner 在 ARM 前拒发、无 POST、无 ARM 写），且 boot_pal2 在设备上存在（否则同构门也不会 true）。pal1_v2 与 lh3dose_v1 同型：boot fault 致死、零执行。

**V5（包 `PAL1_CAL_20260925_R2`）**：
1. pal1_v2 门接受 cursor 缺失 / 1 / 769（contract 块记录推断依据：dump 时序 + 写路径唯一性 + V4 位图实证）。
2. 新增 pal1_v4 保留段（boot 存在 + cursor 缺失或=1；boot f434e324f1bca44f 现场值）。
3. 位图扩为 11 段（+pal1_v4）；NVS `pal1_v5/cur_pal5/boot_pal5`；runner claim `.mf1750_pal1_v5_action_claims`。
4. 审计 R2（`PAL1_CAL_NATIVE_20260925_R2`，58 场景 PASS）：pal1_v2 的 769 接受场景（status 全 true）与 767 拒绝场景；NVS 对账中 pal1_v2/cur_pal2 标 `inferred_post_dump_write`（dump 结构性无法自证，靠写路径唯一性 + 位图实证）。

**运维规则（再次强调，实证两次）**：**任何会复位 MCU 的操作（esptool 任意子命令——包括 read_mac、read_flash/dump、串口开启/pyserial open 等拉 RTS 的动作）在"固件已刷、campaign 未开跑"状态下都会把该命名空间砖成持久 769**。dump/串口日志只能在链全部完成后做。
