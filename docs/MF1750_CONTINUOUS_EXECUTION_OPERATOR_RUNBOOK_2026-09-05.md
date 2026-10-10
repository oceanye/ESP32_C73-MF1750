# MF1750 E6 连续执行操作者运行手册

更新时间：`2026-09-05`  
目标：在没有官方 SPD1657B waveform ABI 的情况下，用在线资料约束下的 phase/controller 闭环，逐步判定单像素颜色和明度候选。  
当前现场门：`NO-GO`；本手册不改变现有授权。

2026-09-12 执行校正：当前完整顺序以 [统一执行计划](MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md) 为准，实际进度以 STATUS 顶部为准。本手册的批次是依赖关系，不是自动串行命令；当前彩色源先走独立 W0 恢复，不能声称已有白源或重新运行旧 P2。已有明确授权无需反复申请，但不能代替缺失的物理/协议证据。

详细变量和状态机见：
[`MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md`](MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md)。

## 操作原则

操作者只执行当前批次中明确写出的动作。每个批次结束后停住，将证据包交给判定者；判定者返回下一状态。禁止根据肉眼颜色自动放行下一 ordinal、自动刷白、重试或串联。

每次结果都绑定以下完整身份：

`panel_id / controller / controller_revision / firmware_hash / profile_hash / waveform_or_action_hash / source_state / target_state / test_phase / temperature / camera_setup / run_id`

缺少任一身份字段时，结果只能是 `HOLD_FOR_REVIEW`，不能计入资格。

## 连续执行批次

### Batch A：离线执行包确认

**目的**：确保现场只会执行已封印材料。

操作者拿到：

- P2-C 主固件、独立 white successor、contract、descriptor、action；
- 每个文件的 SHA-256 和本次 session ID；
- 相机配置、ROI 图、结果 JSON 模板、人工观察表；
- 本批次允许的 ordinal 和停止条件。

验收：

- 文件哈希全部匹配；
- 固件身份与 panel/controller identity 一致；
- action 合同写明 `1 driver / 1 visible refresh`；
- 没有 HOLD、seed、perturbation 或未知 opcode；
- 未出现额外 ordinal。

失败：`OFFLINE_PACKAGE_FAIL`，不得接触设备。

### Batch B：现场入口和安全基线

**目的**：只建立当前 session，不刷新屏幕。

顺序：

1. 肉眼确认 retained screen 全屏干净白；记录无色块、边框、色斑、固定线和旧网格。
2. 枚举 COM、IPv4、MAC、相机；建立 exact binding。旧身份全部标记为历史资料。
3. 确认相机是项目指定的 `VID_32E4:PID_4801`。
4. 若需 app-only 写入，先在已核对的安全条件下写入/verify，保留 NVS；重启后重新取得运行目标固件的 boot，再执行本 boot J2-OFF diagnostic：`4 GET / 0 POST / 0 claim / 0 driver / 0 visible refresh`。刷写前诊断只作历史记录，不可复用。
5. 保存原始 GET、BUSY、relay 命令/查询和 session manifest。

验收：

- retained white 通过人工门；
- session binding 唯一；
- J2-OFF diagnostic 计数完全匹配；
- BUSY 为预期空闲；
- 没有 POST、claim、driver 或 visible refresh。

失败：`ENTRY_FAIL`。不执行 P2-C；保持 relay/J2 OFF。`electrical_state_proven=false` 必须原样保留，不能由 query OFF 改写为 true。

### Batch C：P2-C ordinal 1 单动作

**目的**：只测 position-balanced endpoint atlas 的一次诊断动作。

前置：Batch B 必须由判定者返回 `RELEASE_ORDINAL_1`。

顺序：

1. 核对 Batch B 已完成的 app-only 写入/verify 和**刷写后**目标固件同 boot 的 J2-OFF diagnostic；若又发生刷写/复位，旧诊断失效，必须返回 Batch B。旧 P2 ordinal 1 已消费时不得重跑。
2. 在同一 boot 完成恰好 `1 ARM / 1 EXECUTE`，执行 ordinal 1 一次。
3. 等待正常 BUSY 完成；不 retry、不 reset、不自动执行 ordinal 2。
4. 采集 action JSON、status timeline、电流/温度（若本次装置支持）、48MP 原图和人工观察。
5. 动作完成后停住，不自行刷 white successor。

硬验收：

- `complete=true`、`result=true`、`valid=true`；
- `1 ARM / 1 EXECUTE`；
- `1 driver / 1 visible refresh`；
- `0 retry / 0 recovery / 0 autochain`；
- firmware、contract、descriptor、action hash 匹配；
- 无 BUSY 超时、身份漂移或未知请求。

硬失败：`PROTOCOL_FAIL`。立即停止并保持安全状态；不得用相机结果抵消协议失败。

### Batch D：光学判读包

**目的**：判断动作是无效、稳定端点、候选明度还是一次性过渡态。

必须提交：

- 原图、曝光、ISO、白平衡、镜头/机位、光源和温度；
- 每个 `CS1/CS2 × position` 的 ROI；
- `L* / a* / b* / ΔL* / ΔE76 / ΔE00 / hue`；
- 四位置重复性、左右同位差异、边缘污染、邻域 blooming；
- 人工观察原文，不用“看起来更亮”替代数值。

分类规则：

| 分类 | 条件 | 后续 |
|---|---|---|
| `NO_EFFECT` | 差异未超过噪声门 | 保持 `qualified=0`，不执行下一 ordinal |
| `ENDPOINT_ONLY` | 端点可复现，但没有同色相明度证据 | 只记 endpoint，不能进入明度族 |
| `CANDIDATE_LIGHTNESS` | 差异超过噪声门、同色相、方向可重复 | 进入 Batch E，需单独放行 |
| `INVALID_TRANSIENT` | 有静置漂移、邻域刷新干扰或独立 fresh 重建失败的有效证据 | 归档为不稳定候选；白恢复清除候选是正常恢复，不能作为瞬态判据 |
| `OPTICAL_UNRESOLVED` | 相机噪声、曝光、ROI 或照明不完整 | 重新建立基线，不计资格 |

### Batch E：候选 fresh reconstruction

**目的**：排除历史态和位置效应。

每个候选必须执行至少三条独立链，并分开记录；三条链使用不同的 `run_id` 和一次性 action identity：

```text
fresh white → source → target → fresh white
fresh white → source → target → fresh white
fresh white → source → target → fresh white
```

每条链只允许一个 target action。CS1、CS2 分开做，不得左右拼接成一个槽。

上面的箭头只说明依赖。每个 white/source/middle（若配方包含）/target 均为独立动作，按当前批次放行逐次停审；结尾 white 不自动执行。三条重建链独立于 discovery，不能循环旧 successor 的一次性 NVS/claim。

验收：

- 三条链方向一致，方向复现率必须为 100%；
- 四位置保持在同一 controller 的位置门内；
- 同一 recipe 的中值差异不超过既定重复门；
- target 与相邻等级的差异超过相机噪声门；
- 独立 white recovery 通过。

任一条件失败：`CANDIDATE_ONLY`。

### Batch F：HOLD 和邻域串扰

**目的**：确认候选不是一次性 transition，也不会被邻域刷新破坏。

顺序：

1. 构色后拍目标 ROI；
2. 静置并按预定时间点拍摄；
3. 只刷新邻近 ROI，保留 moat；
4. 再拍目标 ROI；
5. 比较邻域刷新前后的 `ΔL* / ΔE00 / hue drift`；
6. 若已另行核对并放行独立白恢复，才执行并拍摄；否则保持候选并停住。恢复清除候选不用于判定瞬态。

验收：

- 目标 ROI 的保持漂移在已封存 HOLD 门内；
- 邻域刷新后没有超门的 blooming、edge ghosting 或色漂移；
- 目标和对照 ROI 都有完整照片；
- white recovery 通过。

公开专利中的 P/stomp 电压、脉宽和次数不得直接采用；没有本板 ABI 时，只能测试已有安全 profile 的 HOLD 语义。

### Batch G：3→5→10 明度推进

**目的**：将候选逐级提升为稳定明度族。

推进规则：

1. `stable-3`：三个单像素等级各自完成三条独立 fresh chain，并通过 Batch F；
2. `stable-5`：新增两个等级；五个等级都重复完整 fresh/HOLD/white recovery；
3. `stable-10`：补齐剩余五个等级；十个等级全部满足相同门槛，并通过跨 controller 匹配。

任何一级失败都停在上一个已通过等级；不能用空间抖动、混合色、左右相加或一次性过渡态补数。

### Batch H：跨控制器匹配和槽位接纳

CS1、CS2 必须分别拥有 recipe 和独立证据。使用同一相机、机位、曝光、白平衡、光源和 ROI 标定，比较：

- `ΔL*`；
- `ΔE00`；
- 色相角差；
- controller-local 位置离散度；
- 邻域刷新后的漂移。

缺少任意一侧证据或光学匹配时，状态为：

`CONTROLLER_TARGET_COMPLETE_PANEL_MATCH_PENDING`

不得写入 256 槽总数。

## 当前已知量化门

下列门来自现有 `position_balanced_hold_compare` schema，只能在对应 schema 完整时使用：

- controller cell centered `ΔL* P95 ≤ 3.0`；
- controller cell centered `ΔE76 P95 ≤ 5.0`；
- recipe median `|ΔL*| ≤ 2.0`；
- recipe median `ΔE76 ≤ 4.0`；
- 同 recipe 位置差 `ΔE76 ≤ 8.0`；
- H2 probe appearance `ΔE76 ≥ 4.0`；
- probe retention `ΔE76 ≤ 5.0`。

这些门的用途必须区分：controller-local repeat 使用前四项，HOLD 使用 probe appearance/retention；它们不能直接替代明度分离门。

### candidate-separation-v1（现场前离线封存）

在第一次候选前，对同一白场和已知 endpoint 做 `N=10` 同态拍摄。对每个 ROI 计算 MAD 和 95% 置信区间，定义噪声门：

`noise_gate(metric) = max(5×MAD(metric), CI95_half_width(metric))`；L* 与 ΔE00 分别估计，配对取两 ROI 对应指标噪声门较大者，不能共享不同色差空间的数值门。

明度候选必须同时满足：

- `|ΔL*| ≥ 2.0` 且大于 L* 的 `noise_gate`；
- `ΔE00 ≥ 3.0` 且大于 ΔE00 的 `noise_gate`；
- 相邻等级方向单调，排序反转数为 0；
- 三条独立 fresh chain 的方向复现率为 100%。

这些数值必须写入本次 session 的 sealed schema/hash，现场不能临时改门。新 endpoint 或新明度门没有版本化 schema 时，判定为 `OPTICAL_UNRESOLVED`。

### retention-v1 和 cross-controller-v1

- `retention-v1`：T=5 s、60 s、600 s 均有图像；相对 T0 的 `ΔL*`、`ΔE76` 和 hue drift 必须在预封存门内。缺测是 `UNTESTED`，不得自动通过。
- `cross-controller-v1`：两侧先各自 local pass；配对时 `P95 |ΔL*| ≤ 3.0`、`P95 ΔE76 ≤ 5.0`、hue drift `≤5°`。缺一侧或相机设置不一致，保持 `CONTROLLER_TARGET_COMPLETE_PANEL_MATCH_PENDING`。

## 每批提交格式

操作者每批只提交一条结构化回报：

```text
SESSION_ID=
BATCH=
STATE_BEFORE=
STATE_AFTER=
PANEL_ID=
CONTROLLER=
RECIPE_ID=
SOURCE_STATE=
TARGET_STATE=
TEST_PHASE=
WAVEFORM_PHASE_OBSERVED=OPAQUE|RESET|SHAKE|BALANCE|DRIVE|SETTLE|HOLD
DRIVER_COUNT=
VISIBLE_REFRESH_COUNT=
RETRY_COUNT=
RECOVERY_COUNT=
BUSY_RESULT=
TEMPERATURE_C=
CAMERA_ID=
PHOTO_SHA256=
ACTION_SHA256=
ROI_METRICS_FILE=
MANUAL_OBSERVATION=
OPERATOR_STOP_REASON=
REQUESTED_DECISION=PASS|HOLD|FAIL|RECOVERY_REQUIRED
EVIDENCE_COMPLETENESS=COMPLETE|INCOMPLETE_NO_QUALIFICATION|INVALID_PROTOCOL
```

我将只根据该回报和绑定文件返回以下四种决定：

- `PASS_NEXT_BATCH`：满足本批次门，允许进入计划中的下一批；
- `HOLD_FOR_EVIDENCE`：动作结束但证据不完整，不得继续；
- `FAIL_STOP`：协议、身份、电气或光学硬门失败；
- `RECOVERY_REQUIRED`：只能执行预先封印的 white recovery，完成后重新回到安全入口。

单个槽只有在下式全部成立时才具备资格：

`eligible = protocol_pass && source_proven && target_single_pixel && camera_lock_pass && settle_pass && optical_gate_pass && repeat_gate_pass && retention_gate_pass && recovery_white_pass && electrical_state_policy_pass`

缺失值不能当作 `false` 或 `true` 猜测，必须输出 `UNRESOLVED/INCOMPLETE`。`electrical_state_proven=false` 可以保留协议诊断继续，但禁止据此授予颜色、明度或 HOLD 资格；relay 命令/查询不一致则直接 `FAIL_STOP`。

## 失败回退矩阵

| 失败 | 操作 | 资格结果 |
|---|---|---|
| retained white、身份或 J2-OFF 失败 | 不执行可见 action，保持 relay/J2 OFF | `FAILED_SAFE` |
| ARM/EXECUTE/driver/refresh 计数、BUSY、SPI、电流或温度异常 | 停止；action 视为 consumed，不 retry；仅在安全条件满足时执行已封印 white recovery | `INVALID_PROTOCOL` |
| 相机锁、曝光、ROI、settle 或哈希缺失 | 本 run 作废；新 run_id 和新 action 才能复测 | `INCOMPLETE_NO_QUALIFICATION` |
| 只出现一次的差异、历史依赖或白恢复后消失 | 封存为 transient/candidate-only | `qualified=0` |
| 温度不在 bucket 或跨 bucket 合并 | 不合并统计，重新建立对应 bucket | `TEMP_OUT_OF_SCOPE` |
| 白恢复后不是 clean-white | 封存 campaign，保持 NO-GO | `RECOVERY_REQUIRED` |

## 每个 action 后的 Stop Card

操作者固定执行：

1. `STOP`：不发下一条 mutation；
2. 保存 raw status、BUSY、action、照片和哈希；
3. 在 5 s settle 点拍摄一张固定设置的照片；
4. 填写人工观察原文和停止原因；
5. 等待判定者返回下一 action token。

## 当前可执行边界

当前只可安排 Batch B；Batch C 必须在 Batch B 合格后，由我明确判断是否放行 P2-C ordinal 1。Batch D 及以后全部是条件批次，不得连续自动执行。当前 `qualified_new_colours=0`、`qualified_lightness_levels=0`、`electrical_state_proven=false` 保持不变。
