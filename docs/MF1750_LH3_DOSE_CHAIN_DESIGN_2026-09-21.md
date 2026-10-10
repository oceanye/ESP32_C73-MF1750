# MF1750 LH3 剂量轴链设计（P3 判决实验）

> 日期：2026-09-21。状态：设计冻结候选，待离线构建验证。
> 前置：[`MF1750_E6_FULL_COLOR_INDUSTRY_SURVEY_2026-09-19.md`](MF1750_E6_FULL_COLOR_INDUSTRY_SURVEY_2026-09-19.md)（剂量轴定位）、
> `.test-output/offline/LH2_XOR3_MECHANISM_20260918_V1/xor3-report.md`（码轴漂移与帧设计建议）、
> [`MF1750_LH2_DRIVE_MAP_CHAIN_DESIGN_2026-09-17.md`](MF1750_LH2_DRIVE_MAP_CHAIN_DESIGN_2026-09-17.md)（3-action 链架构范本）。

## 1. 科学问题

**同一驱动码第二次施加（dose2）相对第一次（dose1），是否使颜色沿同色相加深（剂量=明度旋钮），还是无色变 / 色相漂移？**

三种可判结果（冻结门 `MF1750_LIGHTNESS_TEST_V1_20260911`：ΔL*≥2、ΔE00≥3、Δh≤5°，噪声 max(5×MAD, CI95)）：

| 结果 | 判定 | 含义 |
|---|---|---|
| A | dose2≈dose1（差值落入噪声带） | 该码剂量饱和，剂量轴对此码无效 |
| B | dose2 更深且 Δh≤5°、ΔL*≥2、ΔE00≥3 | 剂量是该色相族的明度旋钮 → 每族级数可翻倍 |
| C | dose2 色变且 Δh>5° | 码轴漂移（XOR-3 类）主导，同码二次施加不等于"同色加深"，剂量轴不能直接用 |

按码逐列判决：8 个码可能落在不同结果类。

## 2. 链设计（最小版：复用 3-action 架构，不扩 action 数）

```
SOURCE (ordinal 1, active 全局头)   全屏码 7 白 —— 链位深度 1
DOSE1 (ordinal 2, commented 全局头) 每侧 8 列 × 8 行；列 c 全列码 c —— 链位深度 2
DOSE2 (ordinal 3, commented 全局头) 帧与 DOSE1 逐字节相同          —— 链位深度 3
```

- **帧逐字节相同是自变量的关键**：DOSE1 与 DOSE2 之间唯一差异是"历史多了一次同码施加"。frame_sha256 相同、action 序不同。
- **列=码、行=重复**：每码每侧 8 个空间重复（16 合计），给中位数 + MAD 噪声估计；左右两侧给出 CS1/CS2 一致性。
- **白参照列内建**：码 7 列即 commented 白在链位 2、3 的参照（XOR-3 报告"白参照列"建议的 3-action 可实现形式）。
- **码轴标定条的取舍（如实记录）**：XOR-3 报告建议帧内嵌"新鲜白历史+码 0..7"标定条。3-action 架构下全屏每格都被 DOSE1 驱过，**不存在**"新鲜白历史"区域；本设计不扩 action 数，故以①SOURCE active 白场照片（链位 1 参照）+ ②码 7 列（commented 白参照）替代同帧新鲜白条。若剂量有信号需扩展，另起 LH3b（kActionCount=4，SOURCE 后留保护区）——本版不做。
- **DOSE2 用原码 c 而非 XOR-3 补偿码 c^3**：补偿会混淆"剂量"与"码轴漂移"两个自变量；原码重打让漂移以 Δh 形式显形（结果 C），本身就是诊断。
- qualified 保持 0/256；每段严格 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh；claim 先于 ARM；失败不重发。

## 3. 测量与判决

- DOSE1 后、DOSE2 后各拍 1 张整屏 + 10 同态帧（噪声）。屏幕双稳态保留帧，拍照不消耗 action。
- 逐（侧， 码列）取 8 格中位 Lab → dose2−dose1 的 ΔL*、ΔE00、Δh；噪声带 = max(5×MAD, CI95)。
- 同时给出每码"dose1 绝对端点"（与亮光 MIDDLE 端点对照，验证 commented 从白出发的再现性——LH2 控制列异常提示 commented-C7 从非 SOURCE 白出发行为不同，本链 DOSE1 历史恰是 active 白，是最干净的对照）。

## 4. 构建件（全部仿 LH2/LH3 白既有件）

| 件 | 仿照 | 说明 |
|---|---|---|
| 算法 `host/static_photo/lightness_history_lh3_dose.py` | `lightness_history_lh2.py` | TEST_ID `MF1750_LIGHTNESS_HISTORY_LH3_DOSE_V1_20260921`；STAGES=(SOURCE,DOSE1,DOSE2)；HEADERS=(active,commented,commented)；DOSE2 帧 == DOSE1 帧（断言逐字节相等） |
| pack `tools/mf1750_lh3_dose_pack.py` | `mf1750_lh2_drive_map_pack.py` | ANCHOR_SHA 模式不变：合成锚先行，真包封印等 LH3 白真屏 close-review |
| native 审计 `tools/mf1750_lh3_dose_native_audit.py` | `mf1750_lh2_drive_map_native_audit.py` | 合成锚全链 + `--package` 真包模式 |
| runner `tools/mf1750_lh3_dose_once_v1.py` | `mf1750_lh2_drive_map_once_v1.py` | validate / run --ordinal {1,2,3}；新 NVS namespace/claim |
| 分析 | 复用 `mf1750_lh2_drive_map_photo_analyzer.py` ROI 网格 | 新增 dose 对比脚本（dose2−dose1 表） |

## 5. 固件已知坑（构建时必须处理）

1. `phLayoutValid()` 冻结检查锚定 `kTargetCodes[0]!=3||[1]!=7`（LH2-DM-D1 缺陷同款）——新 identity 常量必须同步改布局门锚点。
2. `useCommentedGlobal` 按角色选择：Target 角色需 commented 时改 `Mid||Target` 分支，两行锚点定位防误改 V3 同文本行（LH2-DM-D1 修复点）。
3. transport dispatch `"CC" if ordinal==2 else "AA"` 需按新 HEADERS 改。
4. `kHistoryLayoutJson` 的 target_codes / symmetric_tuple_sequence 同步。
5. 设备门：剂量主固件 gate 应断言 lh3 白已消耗（lh3srcw_v1 used）+ lh2map_v1 终态 + lhist_v1/lh1reb_v2 保留（在 LH3 白 runner 设备门基础上加白 claim）。

## 6. 现场流程（白天亮天后，照明门 0.85 达标才动手）

1. fresh 枚举 → 相机 anchor → IP 绑定 → relay rebind。
2. relay OFF 刷 LH3 白固件 → diagnose-j2-off → relay ON（等 ~10s BUSY 稳定）→ 通电诊断 → run 白（1 refresh）→ 拍照确认全白 → relay OFF。
3. 白 close-review sha 填入 dose pack ANCHOR_SHA → 真包封印 → 真包 native 审计 PASS。
4. 刷剂量主固件 → SOURCE → 拍照 → DOSE1 → 拍照+10 帧 → DOSE2 → 拍照+10 帧 → relay OFF。
5. 离线分析 → 按第 1 节三结果判决 → STATUS_HANDOFF 记录。

本轮新增刷新预算：白 1 + 链 3 = 4。

## 7. 现场运维警示（2026-09-24 实证）

**剂量主固件刷写后的首次启动即写入 campaign boot 绑定**（`initializeOrValidateCampaignBootBinding`，admission 为 FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY）。此后任何 MCU 复位都会产生新 boot nonce，触发 `campaign_boot_binding_mismatch_at_boot` → `enterFault`，FAULT cursor 永久持久化，无恢复路由。

- **从刷写完成到三段链全部完成之间，严禁任何 MCU 复位**：包括 esptool（read_mac 等任何子命令都会拉 RTS 硬复位）、串口监视器开 RTS、pyserial 打开端口等一切会触发 RTS 的操作。
- 如需读串口日志，只能在 campaign 结束之后；刷写用 `app_only` 写流程本身不算复位违规（写后首次启动即绑定点）。
- 2026-09-24 实证：一次 `esptool read_mac`（RTS 硬复位）把尚未开跑的 V1 campaign 砖掉——设备 fault_locked，`lh3dose_v1` cursor_raw=769（phase FAULT | ordinal 1），total_driver_call_count=0，**无任何 ARM/EXECUTE/driver/刷新发生**。
- **若 campaign 未开跑即砖掉（driver_calls=0），换 NVS 命名空间重建包即可**：白锚继续有效（屏幕双稳态白场未被触碰），禁止擦 NVS（会毁掉 lh2map_v1/lhist_v1/lh1reb_v2/lh3srcw_v1 保留证据）。V2 重建（`.test-output/offline/LH3_DOSE_20260924_R2/`，命名空间 `lh3dose_v2`）的设备门额外断言 V1 命名空间恰为砖态 cursor 769 且不可恢复，作为不可触碰的历史证据保留；runner 侧 claim 目录同步换为 `.mf1750_lh3_dose_v2_action_claims`。
