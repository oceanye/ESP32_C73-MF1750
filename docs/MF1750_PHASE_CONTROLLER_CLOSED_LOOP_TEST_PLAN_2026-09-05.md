# MF1750 E6 phase/controller closed-loop test plan

更新时间：`2026-09-05`  
适用对象：MF1750 1024×600、CS1/CS2、`SPD1657B rev 0x04`  
当前门：`NO-GO`；本文件不授权硬件执行。

2026-09-12 执行校正：[统一执行计划](MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md) 为当前完整顺序，STATUS 顶部为实际进度。本文件保留研究模型；各阶段不能自动串行，不能由历史诊断、旧 white 身份或旧 P2 消费游标放行新动作。用户已明确授权的工作继续执行，不重复请求同一权限；缺失物理证据仍须补齐。

本计划假定没有厂商提供可直接使用的 waveform ABI。在线资料只用于建立物理假设、测试维度和拒绝条件；它们不能直接生成本板 payload。

## 在线资料给出的可用约束

- Spectra 6 是四粒子 Microcup 系统，颜色状态取决于粒子顺序、起始状态和带极性的时间脉冲；因此每次测试必须记录 `controller + source_state + target_state + waveform/profile identity + temperature`。
- E Ink 模块资料把颜色与关联的 controller/waveform file 绑定；E Ink 2025 年的 Ripple/3-bit 扩展使用新的架构和兼容芯片，不能移植成 SPD1657B 的寄存器或电压命令。
- 2025 SID 资料将六种颜色视为主要原生状态，其他视觉颜色通常通过空间混合；本项目的单像素槽不能把空间抖动当作通过。
- 2026 年公开专利指出局部刷新会出现邻近像素耦合和颜色漂移，且不同颜色可能需要不同校正波形。这里仅作为“必须测量”的依据，不直接采用其 P/stomp 参数。

参考：

- [SID Digest 92-4](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-4.pdf)
- [E Ink Spectra 6](https://www.eink.com/brand/detail/Spectra6)
- [E Ink Ripple / Second-Generation Waveform Architecture](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)
- [E Ink Spectra 6 module information](https://shopkits.eink.com/en/product/detail/13.3%27%27Spectra6ePaperDisplay)
- [公开专利 US20260065870A1](https://patents.google.com/patent/US20260065870A1/en)
- [Modos-Labs/Glider waveform notes](https://github.com/Modos-Labs/Glider)：公开了 `lut[src][dst][frame]`、温度 bucket、帧数和 E6 专用编码的资料模型，但不含本板安全 payload。
- [EP1738347A1](https://patents.google.com/patent/EP1738347A1/en)：说明 reset/shaking 与起始态依赖，只作为实验假设来源。
- [US12718777（2026-08-25）](https://patentsgazette.uspto.gov/week34/OG/html/1549-4/US12718777-20260825.html)：公开了 seed → 实屏光学测量 → perturbation → 再测量的闭环方法学；它不提供 SPD1657B 的安全写入 ABI，因此当前仍只能作为未来方法参考。

## 测试对象和索引

每个实验单元由下列不可省略的键组成：

`cell_id = controller × recipe_id × source_state × target_state × phase × run_id`

其中：

- `controller` 只能是 `CS1` 或 `CS2`，两者先分别分析，不能把左右屏计数相加。
- `recipe_id` 是已封印 profile/固件/action 的身份；未知或修改后的 profile 不进入 live 测试。
- `source_state` 是刷新前实际状态，不使用“假定白场”；必须由前一动作、fresh white 或已封存观察证明。
- `target_state` 是一个单像素候选 endpoint 或明度候选，不是 RGB 值。
- `phase` 是实验阶段标签。驱动器内部的脉冲相位仍视为 opaque；在没有 ABI 时禁止修改其电压、极性、帧数或时序。
- `run_id` 用于区分独立 fresh reconstruction、重复和保持观察。

### 两层 phase 标记

为了避免把“实验阶段”和“波形内部 phase”混淆，日志同时保留两个字段：

- `test_phase`：`SAFE`、`WHITE_ANCHOR`、`SOURCE_OBSERVED`、`TARGET_DRIVE`、`OPTICAL_REVIEW`、`HOLD_REVIEW`、`RETENTION`、`RECOVERY`、`CROSS_CONTROLLER`。
- `waveform_phase_observed`：只有在现有 driver/profile 的协议或可信 trace 中确实可见时，才记录 `RESET`、`SHAKE/PRECONDITION`、`BALANCE/DC`、`DRIVE`、`SETTLE`、`HOLD`；不可见时写 `OPAQUE`，不允许根据公开专利猜填。

闭环的最小实验矩阵为：

`CS1/CS2 × recipe/profile × source_state × target_state × temperature_bucket × test_phase × run_id`

温度 bucket、waveform/profile hash、mode、帧数和 controller revision 必须一起记录。开源 waveform 资料中的字段只能作为日志结构参考，不能直接迁移其值。

相机也属于闭环键：`camera_id + lens/机位 + RAW exposure/ISO/WB + 光源设置 + patch 尺寸 + flat-field/color-card calibration`。单个物理像素可能低于镜头分辨率，因此测试对象应是可分辨的同态单像素逻辑 patch，并记录 patch 的尺寸和成像 PSF/MTF 约束。

## 阶段状态机

```text
S0_SAFE_OFF
  -> S1_RETAINED_WHITE_CONFIRMED
  -> S2_SESSION_BOUND
  -> S3_J2_OFF_DIAGNOSTIC_PASS
  -> S4_FRESH_WHITE_ANCHORED
  -> S5_SOURCE_STATE_OBSERVED
  -> S6_SINGLE_TARGET_ACTION
  -> S7_OPTICAL_REVIEW
  -> S8_CONTROLLER_LOCAL_CLASSIFICATION
  -> S9_HOLD_OR_FRESH_RECONSTRUCTION
  -> S10_REPEAT_AND_RETENTION
  -> S11_CROSS_CONTROLLER_MATCH
  -> S12_SLOT_ADMITTED
```

任一阶段失败都回到离线分析或 `S0_SAFE_OFF`。动作执行器不能自动跨越阶段，也不能在 `S7` 前执行下一 ordinal。

## 每个 phase 的闭环

### Phase 0：安全和身份

输入：retained clean-white 人工确认、fresh COM/IP/MAC 枚举。  
检查：J2-OFF diagnostic 达到 `4 GET / 0 POST / 0 claim / 0 driver / 0 refresh`；固件、contract、descriptor、action 哈希一致。  
若发生 app-only 写入/verify/重启，必须重新取得**刷写后运行目标固件同 boot**的 J2-OFF diagnostic；刷写前记录不得复用。断电诊断 raw BUSY=0，与接通后执行前须读到 BUSY=1 是两个独立门。当前彩色源先按统一计划 W0 建立白源，不伪称 retained clean-white。  
停止：白屏不干净、身份不唯一、BUSY 非预期、或 `electrical_state_proven=false` 且没有外部电气测量。  
输出：`session_manifest`，不产生光学资格。

### Phase 1：控制器本地基线

对 CS1、CS2 分别执行已知 stable endpoint atlas 的一个单次动作。每次仅 `1 driver / 1 visible refresh`，不 HOLD、不历史叠加、不自动恢复。

记录：位置、recipe、source/target、动作时长、BUSY timeline、原图、ROI、人工观察。  
判定：只建立位置/控制器重复性基线；不得称为新颜色或明度。

在第一次候选前，先对同一白场和已知 endpoint 做 `N=10` 同态拍摄，估计相机噪声底。候选差异门必须使用预先封存的 `5×MAD` 或 95% 置信区间规则；若没有噪声底，观察只能记为 `UNRESOLVED`。

### Phase 2：source → target 单像素候选

只在 Phase 1 通过后，固定一个 controller、一个 source、一个 target 和一个位置平衡 atlas。先做 `source → target`，再独立 fresh white，不在同一 action 中追加其他 transition。

记录：`source_state` 的来源、目标是否单像素同态、四位置副本、CS1/CS2 独立观察、边缘污染和残影。  
判定：

- `NO_EFFECT`：没有可重复光学差异；
- `ENDPOINT_ONLY`：端点稳定但没有同色相明度差异；
- `CANDIDATE_LIGHTNESS`：同色相且测量上可分离，进入 Phase 3；
- `INVALID_TRANSIENT`：有效证据显示静置漂移、邻域刷新干扰或独立 fresh 重建失败，保持 `qualified=0`。白恢复清除候选是正常恢复；仅历史依赖或只测一次不能独自证明瞬态。

每个 source/target 对都至少保留两条路径：

1. `direct(source → target)`：探索历史依赖；
2. `white-reset(source → white → target)`：测试 reset 是否消除历史。

两条路径必须分别归档，不能把 direct 路径的结果当作 white-reset 的结果。

### Phase 3：fresh reconstruction

对 `CANDIDATE_LIGHTNESS` 重新建立独立 fresh-white 锚，在相同 controller、recipe、温度和光学设置下重复构色。discovery 后至少完成三条独立重建链，每条使用不同 run_id 和合法一次性 action identity：

`fresh white → source → candidate target → fresh white`

每条链只允许一个目标动作；配方包含 middle 时须单独计数、逐步停审。任一重建链不能复现方向和幅度，候选退回 `candidate_only`。结尾 white 必须另行核对已授权 successor，不自动执行或循环旧 claim/NVS。

### Phase 4：HOLD / 邻域耦合

HOLD 仅在 Phase 3 命中后离线生成、审计并单独放行。测试必须把“目标像素保持”和“邻近像素刷新后目标是否漂移”分开：

1. 目标像素构色后静置并拍摄；
2. 只刷新相邻 ROI；
3. 再拍摄目标像素；
4. 与未刷新对照 ROI 比较 `ΔL* / ΔE00 / hue drift`。

不得使用公开专利中的电压或 P/stomp 参数；没有本板 ABI 时，HOLD 只测试已有安全 profile 的语义。

每轮闭环最多改变一个变量（controller、recipe、source/target、phase 或温度中的一个），并保存 candidate signature、回滚点和前一轮 manifest。SPI/BUSY/电流异常时立即停止，保持白恢复 successor，不继续优化。

### Phase 5：重复、保持和回收

对每个候选执行同 recipe 的独立 fresh repeat，记录 5 s、60 s、600 s 的图像和环境温度；缺测为 HOLD_FOR_EVIDENCE，任一时间点发生不可解释漂移时不进入稳定等级。仅在独立 successor 已核对且获得相应批次放行时才执行 factory-OTP white，确认回收状态；白恢复清除候选不证明瞬态。

### Phase 6：跨控制器匹配

CS1 和 CS2 的候选先各自通过 `stable-3`，再在同一相机、照明、曝光和 ROI 标定下比较：

- 颜色差：`ΔE00`；
- 明度差：`ΔL*`；
- 色相差：色相角差；
- 位置重复：同 controller 四位置离散度；
- 控制器差异：同槽 CS1↔CS2 差异。

缺少任一侧 recipe 或光学匹配时，状态只能是 `CONTROLLER_TARGET_COMPLETE_PANEL_MATCH_PENDING`。

## 3→5→10 明度门

一个 hue family/track 必须按以下顺序推进：

1. `stable-3`：三个单像素等级，方向单调，独立 fresh reconstruction 可复现；
2. `stable-5`：增加两个等级，不能靠重复测量噪声或位置差异凑数；
3. `stable-10`：十等级全部满足同一门槛，并通过 HOLD、保持和白恢复。

任一级失败，保留较低一级或退回 `candidate_only`；不允许用空间抖动、跨像素混合或控制器左右相加补足数量。

## 每轮动作的输入/输出契约

### 输入

- 当前状态机节点和允许的下一节点；
- 精确 controller、recipe、source/target、phase、ordinal；
- 固件/contract/action 哈希；
- 预期 driver/refresh 次数；
- 停止条件与白恢复 successor；
- 相机和电气测量配置。

### 输出

- 协议结果：GET/POST、claim、driver、refresh、BUSY、耗时；
- 光学结果：原图、ROI、色彩指标和人工原文；
- 电气结果：relay 命令/查询与外部测量来源；
- 分类：`NO_EFFECT`、`ENDPOINT_ONLY`、`CANDIDATE_LIGHTNESS`、`INVALID_TRANSIENT`、`FAIL_PROTOCOL`、`FAIL_ELECTRICAL`；
- 下一节点建议。下一节点必须由人工或离线审计确认，禁止执行器自动串联。

每个可见 action 还必须记录每个 phase 的 `t_start/t_end`、SPI/BUSY trace、 settle 完成标志和白恢复结果；闭环优化的反馈只来自已完成 settle 的光学结果。

## 量化门和现有实现的衔接

现有 `host/static_photo/position_balanced_hold_compare.py` 已定义一组 position/HOLD 审查阈值，可作为 Phase 4 的默认配置来源：controller cell centered `ΔL* P95 ≤ 3.0`、`ΔE76 P95 ≤ 5.0`；recipe median `|ΔL*| ≤ 2.0`、`ΔE76 ≤ 4.0`；同 recipe 位置差 `ΔE76 ≤ 8.0`；H2 probe appearance `ΔE76 ≥ 4.0`；probe retention `ΔE76 ≤ 5.0`。这些阈值只适用于对应 compare schema，不能自动替代新 endpoint/lightness 的资格门。新门必须在离线 schema 中显式版本化，缺失时 fail-closed。

## 最小数据表

| 字段 | 要求 |
|---|---|
| `controller` | `CS1` / `CS2`，不可空 |
| `recipe_id` | 封印身份和 SHA-256 |
| `source_state` / `target_state` | 明确 code、来源和角色 |
| `phase` | 状态机阶段，不可写自由文本替代 |
| `run_id` | fresh/repeat/retention 唯一标识 |
| `driver_count` / `visible_refresh_count` | 与合同一致 |
| `temperature_c` | 记录或明确缺失 |
| `camera_metadata` | 设备 VID/PID、曝光、白平衡、机位 |
| `roi_metrics` | `L* / a* / b* / ΔL* / ΔE00 / hue` |
| `qualification` | fail-closed 枚举值 |
| `next_action` | 离线建议，不代表授权 |

## 当前执行决策

当前仍停在 `S0_SAFE_OFF`。下一次只允许完成 retained white、session binding、J2-OFF diagnostic 和 P2-C ordinal 1；P2-C 的结果进入本计划的 Phase 1/Phase 2 归档。没有新的安全 waveform ABI 前，不生成 seed/perturbation payload，不改变 relay/J2，不宣称 256 槽已经可实现。
