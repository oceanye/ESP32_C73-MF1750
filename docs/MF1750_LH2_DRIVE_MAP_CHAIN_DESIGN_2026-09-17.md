# LH2：8×8 驱动图谱链设计（SOURCE→MIDDLE→MAP）

本页是下一条明度链的离线设计。实时状态以 `STATUS_HANDOFF.md` 顶部为准。
本页不授权任何现场动作；新链需要新合同、新固件、新 NVS、新 claim 和独立放行。

## 已测得的机制事实（LH1_REBOUND_V2，2026-09-17，camera-relative）

CS1 中位 Lab（10 帧，中央 60% 采样）：

| 阶段 | 配方 | L* | a* | b* | 色相角 | 备注 |
|---|---|---|---|---|---|---|
| MIDDLE | M0 | 29.7 | 33.1 | -2.0 | 356° | 红 |
| MIDDLE | M1 | 48.4 | 17.8 | -3.6 | 349° | 浅粉 |
| MIDDLE | M2 | 40.3 | 25.8 | -3.5 | 352° | 粉 |
| MIDDLE | M3 | 18.3 | 16.5 | -32.5 | 297° | 藏青 |
| MIDDLE | M4 | 39.1 | 12.4 | 7.6 | 32° | 棕 |
| MIDDLE | M5 | 30.4 | 21.2 | -51.9 | 292° | 亮蓝 |
| MIDDLE | M6 | 32.3 | -7.4 | -13.0 | 240° | 青 |
| MIDDLE | M7 | 65.5 | 2.8 | -12.4 | 白（C*=12.7 微彩） | 白 |
| TARGET T3 | 全部8种历史 | 14.7 | 13.1 | -16.1 | 309° | **全收敛暗端点** |
| TARGET T7 | 全部8种历史 | ≈MIDDLE原值 | | | | **白目标无驱动** |

机制结论：
1. commented profile 从白出发产生 8 个可分辨端点（唯一的等级发生机制）。
2. active profile code3 是历史无关的暗吸引子（L*14.7）；收敛破坏色相。
3. active profile code7 对彩色历史无驱动（|ΔL*|≤1.5，色相保持）。
4. 位置一致性（CS1 P95 |ΔL*| 0.12–0.95）和双 controller 收敛（T3 质心差 0.07 L*）都良好。

## 为什么现有配方空间到不了"每色 10 级"

- 码只有 3 bit（0–7），从白出发的 commented 端点就是全部 8 个；
  按冻结的 12 色相族口径实测覆盖：红族 3 级（29.7/40.3/48.4）、蓝靛族 2 级（30.4/18.3）、
  青 1、棕 1、白 1。T3 吸引子（309°）与 M3（297°）色相差 12°，超出 5° 同色相门，不能并链。
- 每族 10 级只能靠**中间态**：`(历史, 目标码)` 组合产生的中间明度，或剂量轴（P3 后置）。
- 因此下一步必须先把"从非白状态出发的驱动映射"测出来——这正是本链的目的。

## 链设计（3 action，架构与 V2 相同）

| 项目 | 设计 |
|---|---|
| ordinal1 SOURCE | 不变：active profile、全屏 C7 白基线 |
| ordinal2 MIDDLE | 不变：commented profile、16 配方 M0…M7 位置平衡矩阵（重建 8 种历史） |
| ordinal3 MAP | **新帧**：64 格/侧 = 8 历史 × 8 目标码全映射，每对每侧恰好 1 格 |

MAP 动作设计：
- 16 配方重新定义为 `LH2-S7-M{m}-H{h}`（m=0…7 历史，h=0/1 目标码半区）。
  h=0 的 4 个位置分别写目标码 {0,1,2,3}，h=1 写 {4,5,6,7}；每侧每个 (历史,码) 对恰一次。
- **2026-09-17 构建期修正（替代原"分侧双 profile"方案）**：驱动在每个动作内按角色
  选择唯一 tuple（`useCommentedGlobal`，role==Mid 时选 commented），同一动作无法按
  侧拆分；因此 MAP 动作两侧统一使用 commented tuple（驱动分支改为
  `role == Mid || role == Target` 选 commented，单行锚点修改）。等级发生机制在
  commented tuple（机制事实 1），所以单侧探"commented 从彩色态"映射已覆盖核心问题；
  "active 从彩色态"图谱留作后续独立链（如需）。
- 已知控制列自动包含：commented code7 列应复现 MIDDLE 白端点（M7 行），
  code3 列观察是否仍存在收敛吸引；控制列不符即判该帧异常。
- 帧大小/布局/几何（GRID_X0/Y0、CELL_W/H、GAP、双矩阵、placement）逐字节沿用
  `lightness_history.py` 的放置表，仅替换每格目标码赋值表；分析器/ROI 计划不变。

## 判定与产出

- 产出一张 8×8 `L*(历史, 码)` 图谱（commented tuple，双 controller 同帧同 tuple，
  CS1/CS2 互为独立复测），camera-relative。
- 对每色相族统计可分辨等级数（ΔL*≥2、ΔE00≥3、Δh≤5° 的冻结门），回答
  "每色能否形成多级明度阶梯"。**2026-09-17 用户口径：10 级不是硬指标，
  每色相族 4–6 级可用的明度阶梯即可接受；目标是多级明度支撑全彩。**
  发现性筛查允许每对 1 格（无位置重复），正式资格仍须
  后续 4 位置/HOLD/fresh 重建链；本链本身 qualified 保持 0。
- 若某列（码）产生跨历史的中间 L* 梯度，即为多级阶梯候选轴；若全部收敛/不动，
  则判该 profile 无极窄中间态，转向剂量轴（P3）或新 LUT 研究。

## 冻结不变项

- 阈值 `MF1750_LIGHTNESS_TEST_V1_20260911` 不动；几何门沿用用户豁免后的 V2 口径。
- 电气 record-only；`electrical_state_proven=false`；波形内部 phase=OPAQUE。
- 相机仅 `VID_32E4:PID_4801`；每阶段 10 同态帧 + 前后整屏照片。
- 永久 claim、O_EXCL、freshness 900s、release 绑定链全部沿用 V2 TARGET 模式。
- 白恢复：**本链前置一个独立 successor**——LH2 factory-OTP 白
  （`lh2srcw_v1/used_lh2sw1`，绑 V2 TARGET 终态 cursor4 + 旧 fault 保留断言，
  工具 `tools/mf1750_lh2_source_white_firmware_v1.py`）。SOURCE 动作需要干净白起点，
  而 V2 TARGET 帧残留在屏；白 successor 完成并封存后 LH2 主包才能最终封印
  （`tools/mf1750_lh2_drive_map_pack.py` 的 `ANCHOR_SHA` 待真白 close-review 填入，
  为空时 prepare 拒绝）。
- 旧 claim（ordinal1/2/3）全部已消费，禁止重放；旧 V2 固件不接纳新链。

## 构建清单（离线，2026-09-17 进行中）

1. ~~新算法模块~~ ✅ `host/static_photo/lightness_history_lh2.py`
   （16 配方 `LH2-S7-M{m}-H{h}` + MAP 帧 `code=4*h+quadrant` + MAP 语义空白观测）；
   `tests/test_lightness_history_lh2.py` 6 passed。
2. ~~白恢复 successor 包~~ ✅ 离线构建完成：
   `.test-output/offline/LH2_SOURCE_WHITE_20260917_R1/`
   （contract `aa9cd737…`；BIN `3244c7b5…`；ELF `8aac99ad…`；编译 PASS，marker 校验过）。
   Strict native 审计 ✅ PASS（32 场景 77 文档，含双命名空间门与旧 fault 篡改负例）：
   `.test-output/offline/LH2_SOURCE_WHITE_STRICT_NATIVE_20260917_R1/`。
3. ~~新 pack 封装~~ ✅ `tools/mf1750_lh2_drive_map_pack.py`（新 campaign/NVS
   `lh2map_v1`/合同/action 身份；旧 fault + V2 终态双保留门；合成白证据全链测试
   `tests/test_mf1750_lh2_drive_map_pack.py` 4 passed，含 C++/Python 帧规则逐字节一致）。
   **真包封印等白恢复真屏完成（`ANCHOR_SHA` 待填）。**
4. ~~LH2 主包 native 审计（合成白锚）~~ ✅ PASS（39 场景 45 文档，含驱动门探针）：
   `.test-output/offline/LH2_DRIVE_MAP_NATIVE_20260917_R1/`；探针抓出并修复阻断级缺陷
   LH2-DM-D1（phLayoutValid 钉旧 kTargetCodes {3,7} → 改钉 {0..7} 端点）。
   合成锚 PlatformIO 编译 ✅ PASS：
   `.test-output/offline/LH2_DRIVE_MAP_SYNTHETIC_BUILD_20260917_R1/`（证明固件可构建）。
5. ~~白 host runner~~ ✅ `tools/mf1750_lh2_source_white_once_v1.py`（14 tests）；
   ~~主链 runner~~ ✅ `tools/mf1750_lh2_drive_map_once_v1.py`（27 tests，无硬编码 pin，
   真包封印后逻辑零改动）。
6. 现场前另行取得用户对**两次刷写 + 四次刷新**（白 1 + LH2 三动作）的明确放行。
