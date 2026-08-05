# MF-1750 扩展颜色与亮度测试 TODO

创建日期：2026-08-05

状态：`SOFTWARE GROUNDWORK INTEGRATED / HARDWARE NOT STARTED`

硬件授权：无；等待用户逐阶段安排

技术审查源码基线：`867efdd`

Hardware tested in this review: `NO`
完整可行性结论：`docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`

离线成果与集成审查：`docs/EXTENDED_COLOR_INTEGRATION_REVIEW_2026-08-05.md`

已完成的仅是官方证据矩阵、测量/安全门、固定图案及身份、空 6×6 profile、
六码面积混色模拟和机器记录合同。它们不构成硬件授权，也不把下表任何硬件出口
提升为已通过。

## 1. 范围和执行原则

若用户后续逐阶段明确授权，第一轮最大范围仅限于在厂家初始化、OTP waveform、
CCSET、PON/DRF/POF/PSR 和高压参数完全不变的条件下执行：

```text
资料和测量系统冻结
→ 原厂六色电气基线
→ 原厂六色光学基线
→ 恢复流程资格验证
→ 6×6 转换矩阵
→ 0x4 小面积探针
→ 0x7 小面积探针
→ 第一轮评审
```

`0x8～0xF` 只作为后续 bit3 alias/协议鲁棒性子阶段，不能预先作为八个新颜色。
LUT、内部 phase、partial/window 和电压实验不属于本 TODO 的可安排范围，继续保持
硬阻断。

每个硬件步骤都必须满足：

- 用户明确确认 J2-1 上电状态和电源正常；
- 实验前记录 panel、board、firmware、frame 和仪器身份；
- 每次未知码只允许单次 job，不自动重试；
- 未确认恢复前不得进入下一码值或扩大面积；
- 未经用户明确授权，不刷写 COM8、不推送会触发刷新的请求；
- FPC 禁止带电插拔；结束后执行 POF、人工断 J2-1 并确认 TP1 接近 0V。

## 2. 工作包状态

| ID | 工作包 | 状态 | 主要出口 |
|---|---|---|---|
| EC0 | 身份、资料和 Git 基线冻结 | TODO | panel/board/controller/firmware/OTP 资料表 |
| EC1 | 测量系统资格 | TODO | 光学、电气、温度测量重复性合格 |
| EC2 | 原厂六色电气/光学基线 | TODO | 六色 Lab、功耗、轨包络、保持基线 |
| EC3 | 原厂恢复流程资格 | TODO | B/W/B/W 可重复恢复且有最大尝试限制 |
| EC4 | 6×6 转换矩阵 | OFFLINE FIXTURE READY / HARDWARE TODO | 36 转换的历史依赖、残影、能耗和统计 |
| EC5 | `0x4/0x7` 小面积编码探针 | OFFLINE DESIGN READY / HARDWARE BLOCKED | 需隔离实验固件、硬件保护和 EC0–EC4 |
| EC6 | bit3 alias `0x8～0xF` | BLOCKED | 需 EC5 通过及单独风险评审/厂家资料 |
| EC7 | 第一轮报告 | TODO | 回答十个问题并形成下一阶段 go/no-go |
| EC8 | 自定义 waveform/LUT/电压 | HARD BLOCKED | 需 SPD1657B/OTP 资料和新硬件联锁 |
| EC9 | 温度、耐久、图像算法适配 | FUTURE | 仅对已通过筛选的候选执行 |

## 3. EC0：身份、资料和软件基线

- [ ] 拍摄屏幕背面、FPC 丝印、条码、批次和生产日期；
- [ ] 分配不可复用的 `panel_id`、`board_id` 和操作者；
- [ ] 记录 MF1750 Rev A1、R15 拆除、R16=0 Ω；
- [ ] 读取并保存 CS1/CS2 SPD1657B revision；预期均为 `0x04`；
- [ ] 记录当前 firmware commit、build tag、binary SHA-256、git dirty；
- [ ] 保存 mapping、full frame、CS1/CS2 DTM hash；
- [ ] 向厂家确认确切墨水体系和该料号是否属于 Spectra 6；
- [ ] 索取 SPD1657B rev `0x04` 完整命令手册；
- [ ] 索取当前批次 OTP waveform ID、版本、温区和支持模式；
- [ ] 索取 3-bit code 表、`0x4/0x7` 定义、`0x86` 和温度读取方法；
- [ ] 索取最大连续刷新、冷却、恢复、寿命和保修限制；
- [ ] 明确没有资料时 EC8 继续保持 HARD BLOCKED。

出口：所有可获得资料归档；缺失项显式为 `missing`，禁止由 SPD1656 或专利补造。

## 4. EC1：测量系统资格

### 4.1 必需设备

- [ ] 四通道以上示波器；复杂同步采集配合逻辑分析仪；
- [ ] 额定范围和共模满足要求的高压差分探头；
- [ ] 电流探头或经审查的四端输入采样；
- [ ] 可编程 3.3V 电源、硬件限流和实体急停；
- [ ] 分光测色仪；
- [ ] 固定 RAW 相机、手动曝光和固定支架；
- [ ] 45/0 固定照明夹具、标准白/灰参考和稳定光源；
- [ ] 热像仪或关键器件贴片温度探头；
- [ ] 温湿度记录；候选温度实验再增加恒温箱。

### 4.2 冻结参数

- [ ] illuminant、observer、光学几何、孔径、lux 和 CCT；
- [ ] RAW 相机 ISO、光圈、快门、焦距、白平衡和距离；
- [ ] 示波器/逻辑分析仪采样率、带宽、探头序号和衰减；
- [ ] 电流、温度和颜色仪器的校准日期与不确定度；
- [ ] 统一测量时点：建议 BUSY/POF 后 1 分钟为 optical `t0`；
- [ ] 通过重复测量建立 Lab、电流、轨电压和温度的基线噪声；
- [ ] 形成 Gage R&R 或至少重复性/再现性说明。

出口：测量系统噪声显著小于候选筛选阈值；否则不得使用 ΔE00 做正式判断。

## 5. EC2：原厂六色基线

### 5.1 电气基线

- [ ] 冻结六色色条、纯色和高负载随机图；
- [ ] 每个基准至少执行 3 次冷启动刷新；
- [ ] 记录 PON、DRF、POF、post-PSR BUSY 边沿和耗时；
- [ ] 记录输入峰值、平均、RMS 电流、输入能量和 3.3V droop；
- [ ] 测 TP3 VPH、TP5 PREVGL、TP6 VPC 的峰值、建立、纹波和释放；
- [ ] TP4 只作 VPH/PREVGH 同轨一致性证据，不当作独立电源；
- [ ] 记录 Q1、Q2、L1、L2、FPC 控制器区和面板中心最高温度；
- [ ] 按器件绝对限制、面板 0～50℃和基线统计共同冻结停止门；
- [ ] 解决 BUSY 文档文字与 BUSY_N/样例/实测极性的冲突，保存示波器证据。

### 5.2 光学基线

- [ ] 分别测黑、白、红、黄、蓝、绿的 L/a/b、L*、C*、h；
- [ ] 中心和固定网格测均匀性；
- [ ] 固定大块图比较同一照明下的六色；
- [ ] 记录 `1min/10min/1h/24h`；pilot 可先做 `1min/10min`；
- [ ] 24 小时漂移统一相对 `1min` 结果计算；
- [ ] RAW 记录色斑、边缘、颗粒和残影空间分布；
- [ ] 不把规格书第 15 页限值当成实测 palette centroid；
- [ ] 输出经过测量系统资格验证的 calibrated palette artifact。

时间说明：一块面板逐个做六种全屏 24 小时保持，日历下限约 6 天；若改用同屏
多 ROI，必须明确它不再是六次独立全屏保持。

## 6. EC3：恢复流程资格

暂定流程：

```text
原厂全黑
→ 原厂全白
→ 原厂全黑
→ 原厂全白
→ POF
→ 厂商等待和 PSR 收尾
→ 人工切断 J2-1
→ 确认 TP1≈0V
→ 静置
```

- [ ] 在所有六种已知初始状态后验证；
- [ ] 每次记录最终白色 Lab、均匀性、残影和轨释放；
- [ ] 定义最大恢复尝试次数；不得无限自动清屏；
- [ ] 任一已知状态恢复失败，停止 EC4/EC5；
- [ ] 将其称为“暂定恢复流程”，不能称为供应商认证安全 waveform。

## 7. EC4：6×6 转换矩阵

推荐图案：

```text
Initial frame: 六条水平色带 = old color
Target frame:  六条垂直色带 = new color
Intersection:  old(row) → new(column)
```

- [ ] 每半屏镜像一套 6×6，避免只测一颗控制器；
- [ ] ROI 内不放文字，使用外部坐标表或测量区外黑白标记；
- [ ] pilot：一块牺牲屏，每组合 2～3 次；
- [ ] pilot 无异常后正式重复 5 次；
- [ ] 重复轮次交换/旋转矩阵，平衡位置和控制器效应；
- [ ] 每次确认实测旧态，而不只记录意图旧态；
- [ ] 报告每个转换的 Lab、ΔE00、均匀性、残影、电流、能量和温度；
- [ ] 报告六组初始态的最大 pairwise ΔE00 和置信区间；
- [ ] 输出 C3 可读取的 6×6 transition profile；未测值为 null。

按每次重复包含四次恢复、一次 initial 和一次 target，5 次约 30 次刷新；当前
34.2 秒/次只代表约 17 分钟刷新机器时间，实际测量、断电和静置时间更长。

## 8. EC5：`0x4/0x7` 小区域编码探针

状态：BLOCKED。开始前必须完成 EC0–EC4，并另行实现和审查隔离实验入口。

### 8.1 实验入口合同

- [ ] 正式 `/api/frame` 和 `epdDisplayFrame*` 的六色 guard 保持不变；
- [ ] 使用默认关闭、实验 build 专用的固定 action；
- [ ] 设备内部生成固定布局，不接受任意网络 raw frame；
- [ ] test ID、布局、unknown code、面积和预期 frame/DTM hash 进入 allowlist；
- [ ] 一次性 arm、一次 job、冷启动、无自动重试；
- [ ] 完成后必须检查 immutable report、BUSY、hash 和安全收尾；
- [ ] 恢复并由人工确认后才允许重新 arm；
- [ ] 生产/release build 默认不包含或禁用该 action。

### 8.2 图案和顺序

- [ ] 其余区域使用已知白色；
- [ ] CS1、CS2 各一个 `64×64` 镜像 unknown ROI；
- [ ] 未知总面积 8192 px，即全屏 1.333%；
- [ ] ROI 周围留 guard band，文字不进入测色区域；
- [ ] 先 `0x4`，恢复成功后再 `0x7`；
- [ ] 分别从白、黑、红、黄、蓝、绿初始状态进入；
- [ ] 首次只做一次，检查 BUSY、电流、温度、轨包络、画面和恢复；
- [ ] 通过后逐步增加到 10 次重复；
- [ ] 通过短期重复后才测 1h/24h 保持；
- [ ] 分类为独立状态、已知色 alias、保持旧态、不稳定、异常，而不是默认“新色”。

立即停止：任何恢复失败、持续色斑、左右控制器不一致恶化、峰流/温度/轨门禁、
BUSY 异常、日志或探头证据丢失。

## 9. EC6：bit3 alias 与完整编码图

状态：BLOCKED。只有 EC5 完全通过且风险重新审批后执行。

- [ ] 逐对测试 `0↔8、1↔9、…、7↔F`；
- [ ] 每次只测试一个 pair，小 ROI，不直接上完整 4×4 图；
- [ ] 判断 bit3 ignored、alias、reserved、保持旧态或独立状态；
- [ ] 左右控制器镜像并在后续轮次交换位置；
- [ ] 只有全部 pair 恢复、重复、保持均通过后才生成 16 编码总览；
- [ ] 完整图仅用于最终视觉汇总，不承担首轮安全探针功能。

如果厂商资料明确 bit3 为无效/保留且禁止置位，则取消 EC6，不为“回答十六码”而
违背控制器协议。

## 10. EC7：第一轮输出和 go/no-go

- [ ] 屏幕、批次、PCB、控制器和固件信息表；
- [ ] 测量系统资格及不确定度说明；
- [ ] 原厂六色 Lab 标定表；
- [ ] 原厂电气/温度/BUSY 基线；
- [ ] 暂定恢复流程和资格结果；
- [ ] 6×6 转换矩阵；
- [ ] `0x4/0x7` 结果；若获批执行，再附 bit3 alias 结果；
- [ ] 异常、损伤、残影和恢复失败清单；
- [ ] 第一轮十个问题逐项回答；
- [ ] 明确 `GO / CONDITIONAL GO / NO-GO`；
- [ ] 未取得内部波形资料时，第7问必须记录为 `blocked by primary documentation`，
  不得用外部 rail 包络伪装成内部 phase table。

## 11. EC8：自定义波形的硬门禁

状态：HARD BLOCKED。以下全部完成前不建立执行任务：

- [ ] SPD1657B rev `0x04` command datasheet；
- [ ] 当前 OTP ID、温区、模式和 LUT 兼容包；
- [ ] 正式 LUT upload/select/readback 定义；
- [ ] VCOM、Source、Gate、window/old-frame 和温度接口定义；
- [ ] 厂商电压、phase、DC、寿命和恢复限制；
- [ ] VCOM/VSH/VSL/SW/sense 安全测量夹具；
- [ ] 自动 VDD 断电与放电、硬件看门狗和实体急停；
- [ ] 输入电流、关键温度、高压窗口和 PGOOD 硬联锁；
- [ ] 专用牺牲屏和黄金参考屏；
- [ ] 原厂 waveform 可重复复现并完成基线审查。

若硬门禁满足，另建独立的 waveform safety review；不得直接从本 TODO 进入
`80%～120%` 时间扫描或 `±2%～±6%` 电压扫描。

## 12. EC9：候选后的温度、耐久和图像对比

仅对通过第一轮及独立 waveform 审查的候选执行：

- [ ] 温度：10/20/25/35/45℃；先室温，再扩温；
- [ ] 每温点充分 soak，记录面板实温、RH、刷新、功耗、残影；
- [ ] 耐久：候选↔白、候选↔黑、候选↔对立色，各500次；
- [ ] 每100次测 Lab、恢复、温度、电流和轨包络；
- [ ] 保持：1h/24h/72h；
- [ ] 比较原生最近色、Floyd–Steinberg、Atkinson、蓝噪声/有序面积混色、候选
  单像素状态和候选+抖动；
- [ ] 输出画质/稳定性/功耗/寿命 Pareto，而不是只追求颜色数量。

每个候选 1500 次刷新按当前约34.2秒/次，仅机器刷新下限约14.25小时，尚未包含
静置、恢复、测量和冷却。必须使用筛选漏斗，不能对所有搜索参数直接全因子耐久。

## 13. 数据记录最小合同

建议拆分记录而不是使用一张宽 CSV：

### `run`

```text
test_id, timestamp, timezone, panel_id, panel_lot, board_id, pcb_revision,
controller_revision_cs1, controller_revision_cs2, firmware_commit, build_tag,
binary_sha256, git_dirty, frame_sha256, cs1_dtm_hash, cs2_dtm_hash,
waveform_id, config_hash, job_id, operation_id, intended_initial_state,
measured_initial_state, target_code, roi, status, operator
```

### `optical_measurement`

```text
test_id, roi, controller_half, timepoint, L, a, b, C, hue,
deltaE00, reference_id, uniformity_metric, ghosting_metric,
instrument, illuminant, observer, geometry, aperture, calibration_id
```

### `electrical_summary`

```text
test_id, vdd_min, vdd_droop, input_peak_current, input_mean_current,
input_rms_current, input_energy, rail_min_max_settle_decay,
pon_busy_ms, drf_busy_ms, pof_busy_ms, panel_temperature,
component_temperature, ambient_temperature, humidity
```

### `event_recovery`

```text
test_id, event_time, stop_reason, evidence_lost, recovery_attempt,
recovery_result, final_white_deltaE00, remarks
```

每个字段必须有单位、枚举或 `null_reason`。原始示波器、RAW、测色、温度和日志
文件都要记录 SHA-256、仪器配置和对应 test ID。

## 14. 当前等待用户安排的决策

- [ ] 是否有专用牺牲面板和黄金参考面板；
- [ ] 是否可以取得或借用分光测色仪；
- [ ] 是否具备高压差分探头、电流探头、热像/温度探头；
- [ ] 是否有可编程电源、硬件急停和后续恒温箱；
- [ ] 是否先安排 EC0 厂家资料索取；
- [ ] 是否先执行 EC1/EC2，不涉及未知码；
- [ ] 何时授权设计隔离的 EC5 实验固件；
- [ ] 每次硬件测试的上电、刷写、刷新和断电授权窗口。

用户未安排前，本 TODO 不产生任何上电、刷写、刷新、LUT、高压或 PCB 动作。
