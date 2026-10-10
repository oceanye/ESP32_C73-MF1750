# MF-1750 扩展颜色测量系统与安全门禁

文档日期：2026-08-05

阶段：C（测量系统与安全门禁设计）

状态：`BLOCKED / NO-GO FOR HARDWARE TEST`

Hardware tested: `NO`

硬件授权记录：无。本文件不授权上电、刷写 COM8、访问任何刷新接口、连接带电
探头或发送测试帧。

适用基线：MF-17506-M009F-T、1024×600、MF1750 Rev A1、双 SPD1657B
revision `0x04`、R15 已拆、R16=0 Ω、GPIO7=CS1、GPIO10=CS2。

相关边界：

- [`EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`](EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md)
- [`TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)
- [`MF1750_DRIVER_API.md`](MF1750_DRIVER_API.md)
- [`REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)

## 1. 结论与适用边界

现有资料已经足够设计测量系统，但还不足以把它认定为可执行的危险测试平台。
当前缺少真实仪器清单、校准与不确定度、同步采集验收、外部 J2-1 断电急停、
高压节点绝对工作窗口和输入电流绝对限值。因此：

> 在本文件全部必需项打勾、数值占位被实测/审查值替换，并完成独立安全复核前，
> D 阶段及任何未知码硬件探针均为 NO-GO。

本文件只覆盖原厂初始化和片上 OTP waveform 不变的测量门禁。LUT、phase、
window/partial、未知 SPI 命令和电压修改继续 HARD BLOCKED。

## 2. 已知直接限制与术语修正

面板规格给出的可直接使用限制包括：

- 逻辑供电绝对最大范围：`-0.5～+3.6 V`；
- VDD 工作范围：`2.4～3.6 V`；
- 面板工作温度：`0～50℃`；
- `Iupdate` 仍为 `TBD`，不能从规格书得到安全输入电流上限；
- 光学规格在 25℃、45°照明/法线检测条件下给出，但没有给出完整
  illuminant/observer/孔径合同；
- 电气和光学性能只在 InkCubic 指定控制器及匹配 waveform 下保证。

Rev A1 测试点为：

| 测试点 | 信号 | 本阶段用途 |
|---|---|---|
| TP1 | 3V3 | J2-1 输入电源、droop、物理断电证明 |
| TP2 | GND | 测量参考地 |
| TP3 | VPH | 正高压轨包络 |
| TP4 | PREVGH | 与 VPH 经 0 Ω 相连，只作一致性检查 |
| TP5 | PREVGL | 负高压轨包络 |
| TP6 | VPC | 负压泵轨包络 |
| TP7 | VDDIO | 控制器逻辑供电 |
| TP8 | CS1 | 主控制器片选 |
| TP9 | CS2 | 从控制器片选 |
| TP10 | BUSY_N | PON/DRF/POF 时序同步 |

此前提示中的“确认 TP10V”存在歧义。正确的断电门禁是：

```text
人工切断 J2-1
→ 测 TP1 接近 0 V
→ 若高压探头仍连接，同时确认 TP3/TP5/TP6 已释放
```

TP10 是 `BUSY_N`，不能作为 3.3 V 断电证明。

## 3. C 阶段出口检查表

以下任一必需项未完成，C 保持 `BLOCKED`：

- [ ] 仪器、探头、夹具、电源、安全开关均已分配不可复用的资产 ID；
- [ ] 型号、序列号、固件、量程、校准证书、日期和扩展不确定度已归档；
- [ ] 光学夹具、相机、照明、ROI 和环境参数已按第 7 节冻结；
- [ ] 电流、TP1、TP3、TP5、TP6 和 TP10 可以在同一次未知码 job 中同步采集；
- [ ] 探头共模/差模、带宽、衰减、输入电容和节点额定已经审查；
- [ ] 所有探头均可在断电状态机械固定，无需带电手持；
- [ ] 外部 J2-1 开关默认断开、锁存关断，并独立于 ESP32 软件；
- [ ] 实体急停已在假负载上验证切断时间、残压和手动复位；
- [ ] 电源 OVP/OCP/限流值已基于硬件审查冻结，不是凭经验填写；
- [ ] 分光测色、相机、电气和温度测量链已完成第 9 节资格试验；
- [ ] 绝对电流、高压和器件温度门限已替换第 10 节中的 `PENDING`；
- [ ] 原厂已知码匹配控制已形成足够的相对基线；
- [ ] 数据采集、设备日志和主机记录的时钟偏差不超过 1 ms；
- [ ] 任一数据缺失、探头脱落或量程饱和时均能 fail closed；
- [ ] 一次恢复序列的合格线和失败后的隔离流程已经批准；
- [ ] 操作者完成上电、急停、高压探测和 FPC 禁止带电插拔培训；
- [ ] 安全复核人签署 C 阶段 GO 结论；
- [ ] 用户另行授予具体硬件动作的逐步授权。

## 4. 必需设备与夹具

### 4.1 光学

- [ ] 可输出光谱反射率和 Lab 的分光测色仪；
- [ ] 固定 45/0 几何夹具，探测方向相对面板法线可验证；
- [ ] 不使面板受扭曲应力的刚性平面支撑；
- [ ] 稳定、可暖机、可记录 SPD/lux/CCT 的固定光源；
- [ ] 标准白板、灰卡及其有效校准/溯源信息；
- [ ] RAW 相机、固定镜头、刚性支架、遮光罩；
- [ ] 位于显示活动区外的夹具定位标记；测量 ROI 内禁止文字；
- [ ] 相机暗场、平场和几何标定采集办法。

分光测色仪是正式 Lab/ΔE00 门禁的必需设备。RAW 相机只负责均匀性、色斑、
边缘和残影空间分布，未经光谱、暗场、平场和线性标定不得单独生成正式 Lab。

### 4.2 电气

- [ ] 可编程 3.3 V 电源，支持远端采样或能直接测得 TP1 实际电压；
- [ ] 独立 OVP/OCP/硬件限流；
- [ ] 输入电流探头或经审查的四端分流器与隔离放大器；
- [ ] 额定范围满足节点及瞬态要求的高压差分探头至少三支；
- [ ] 足够模拟通道的示波器，或经公共触发同步的示波器、功率分析仪和 DAQ；
- [ ] 逻辑分析仪或混合信号通道，用于 BUSY_N、CS1、CS2、DC、SCLK、MOSI；
- [ ] 探头固定夹、应力释放和绝缘隔离件；
- [ ] 可记录供电电压、电流、能量以及 PSU CV/CC/OVP/OCP 状态的接口。

禁止使用接地型普通探头直接探测未经审查的高压节点。不得由 TP3/TP5/TP6
外部轨包络推断单像素相对 VCOM 的内部驱动波形。

### 4.3 温度与环境

- [ ] 热像仪，或对 Q1/Q2/L1/L2、控制器区和面板设置接触温度探头；
- [ ] 已知 emissivity、反射温度和距离的热像配置；
- [ ] 温湿度记录仪；
- [ ] 光源开启期间可连续监测面板温度；
- [ ] 温度实验前另配恒温箱和独立参考温度探头。

### 4.4 电源切断和急停

`EPD_PIN_SWC=-1`，POF 及 GPIO 拉低都不能物理切断 J2-1。必需的外部安全链为：

```text
可编程 3.3 V 电源
→ OVP/OCP
→ 默认断开的锁存式 J2-1 电源开关
→ 实体急停
→ 输入电流测量
→ TP1/J2-1
```

要求：

- [ ] MCU 未运行、复位、卡死或 USB 仍供电时，J2-1 不会自动闭合；
- [ ] 急停直接断开 J2-1，不依赖 HTTP、串口、BUSY 或软件 watchdog；
- [ ] 断开后必须人工复位，不允许自动重新上电；
- [ ] 急停动作及电源输出状态进入独立日志；
- [ ] 首次接屏前已使用假负载验证；
- [ ] 面板、FPC、探头和测点的任何重新连接都在 TP1 已确认接近 0 V 后进行。

## 5. 仪器元数据最小合同

所有测量文件必须引用一份不可变的仪器配置记录。通用字段至少包括：

```text
instrument_id, category, manufacturer, model, serial_number, firmware_version,
owner, location, calibration_certificate_id, calibration_lab, calibrated_at,
calibration_due_at, calibration_range, traceability, coverage_factor,
expanded_uncertainty, selected_range, self_check_before, self_check_after,
operator, setup_photo, configuration_sha256
```

示波器/探头追加：

```text
channel, probe_id, probe_type, attenuation, differential_range,
common_mode_range, bandwidth_limit, sample_rate, record_length,
input_impedance, coupling, offset, zero_result, deskew_ns,
trigger_source, trigger_level, trigger_slope, connection_from, connection_to
```

电流链追加：

```text
measurement_method, shunt_resistance, shunt_tolerance, shunt_tcr,
amplifier_gain, amplifier_bandwidth, current_probe_degauss_zero,
polarity, remote_sense, integration_method
```

光学追加：

```text
spectral_range, spectral_interval, measurement_condition, illuminant,
observer, geometry, aperture_mm, specular_mode, uv_mode,
white_reference_id, white_reference_before, white_reference_after,
light_source_id, warmup_minutes, lux, cct, panel_normal_error_deg
```

相机追加：

```text
camera_body, sensor_serial, lens, focal_length_mm, focus_mode,
camera_distance_mm, iso, aperture, shutter, white_balance,
raw_format, bit_depth, crop, orientation, dark_frame_id, flat_frame_id,
color_management_disabled, software_version
```

温度/环境追加：

```text
sensor_location, attachment_method, emissivity, reflected_temperature,
working_distance, ambient_temperature, relative_humidity,
sample_interval, sensor_time_constant
```

任何必需字段未知时使用 `null` 加 `null_reason`，不得用空字符串表示“正常”。

## 6. 同步采集与通道合同

### 6.1 同一次运行的最低信号集合

| 类型 | 信号 | 用途 |
|---|---|---|
| 模拟 | J2-1 输入电流 | peak/mean/RMS/energy、硬件限流证据 |
| 模拟 | TP1 3V3 | min/max/droop、断电证明 |
| 模拟 | TP3 VPH | 正轨建立、峰值、纹波、释放 |
| 模拟 | TP5 PREVGL | 负轨建立、谷值、纹波、释放 |
| 模拟 | TP6 VPC | 负压泵轨建立、谷值、纹波、释放 |
| 数字 | TP10 BUSY_N | PON/DRF/POF 时序基准 |
| 数字 | TP8/TP9、DC、SCLK、MOSI | 控制器身份和命令阶段对齐 |

因此至少需要五路同步模拟量和一路数字量。四通道示波器单独使用不合格；可以
使用同步功率分析仪承担 TP1/输入电流，并用四通道示波器采三条高压轨，但必须有
公共硬件触发和已验证的时间对齐。禁止通过重复第一次未知码 job 来补采通道。

### 6.2 采集档位

- 全运行包络：建议不低于 `100 kS/s`，并配置匹配的模拟抗混叠带宽；
- 开关瞬态：建议不低于 `100 MS/s`、带宽不低于 `20 MHz`，采用分段触发；
- 数字时序：不低于 `1 MS/s`；
- 所有采集设备的相对时间偏差：`≤1 ms`；
- 峰值必须附带带宽后缀，例如 `input_peak_current_20MHz`；
- 不同带宽下的峰值禁止直接比较；
- 仪器饱和、overrange、丢触发或缺少某阶段记录时，本 run 无效并停止后续。

### 6.3 探头操作

- [ ] 确认 J2-1 断开；
- [ ] 测 TP1 并记录接近 0 V；
- [ ] 若前次有高压，确认 TP3/TP5/TP6 已释放；
- [ ] 安装并机械固定探头；
- [ ] 检查相邻焊盘、FPC 和探头夹无短路风险；
- [ ] 执行差分探头零点、衰减和通道 deskew；
- [ ] 拍摄连接全景和每个测点近照；
- [ ] 上电后禁止移动或手持探头；
- [ ] 拆探头前重复断电与残压确认。

## 7. 冻结参数与待补占位

| 项目 | 冻结值/规则 | 当前状态 |
|---|---|---|
| baseline ambient | `25.0±1.0℃` | FROZEN |
| baseline RH | `55±5%RH` | FROZEN |
| canonical illuminant/observer | `D65 / 2°`，同时保存原始光谱反射率 | FROZEN |
| secondary result | 可从同一原始光谱另行计算 `D50 / 2°`，必须记录积分/色适应算法与版本 | OPTIONAL；不得冒充 D65 |
| geometry | `45/0`，探测法线误差 `≤2°` | FROZEN |
| unknown ROI aperture | 实际光斑直径 `≤5 mm` | FROZEN |
| external RAW light | `5000±100 K, 1000±20 lx` | PROVISIONAL；待夹具验收 |
| light warmup | `≥30 min` 或厂家要求较长者 | FROZEN |
| camera ISO | 最低原生 ISO；具体数字 | `PENDING_CAMERA_SELECTION` |
| camera aperture | 建议 `f/8`；若镜头不支持则冻结等效档 | PROVISIONAL |
| camera shutter | 白参考线性满量程 70～80%，无通道 clipping | `PENDING_EXPOSURE_QUALIFICATION` |
| focal length/distance | 固定且记录毫米值 | `PENDING_FIXTURE_SELECTION` |
| white balance | 固定自定义灰卡，不使用 AWB | FROZEN RULE |
| optical t0 | POF BUSY_N 低→高后 `60±5 s` | FROZEN |
| hold timepoints | `10 min±30 s, 1 h±2 min, 24 h±15 min` | FROZEN |
| supply setpoint | TP1 目标 `3.30 V` | FROZEN |
| supply OVP/OCP/current limit | 经节点和最坏已知码审查的数值 | `PENDING / BLOCKER` |
| TP1 off proof | `≤0.10 V` 持续 `≥5 s` | FROZEN PROCESS LIMIT |
| rail release before handling | `|TP3/TP5/TP6|≤1 V` 持续 `≥5 s` | PROVISIONAL PROCESS LIMIT |
| input current absolute limit | 厂家/硬件审查数值 | `PENDING / BLOCKER` |
| TP3/TP5/TP6 absolute windows | SPD1657B和节点应力审查数值 | `PENDING / BLOCKER` |
| component temperature limits | 各器件额定、贴装和不确定度后的门限 | `PENDING / BLOCKER` |
| recovery candidate | `B/W/B/W` 仅为待 EC3 资格验证的候选，不是厂商认证或当前可执行流程 | `NOT QUALIFIED / BLOCKER` |
| recovery maximum attempts | 绝对上限一套；EC3 必须冻结最终允许值（只能为 0 或 1） | `PENDING / BLOCKER` |
| recovery inter-step gate | 每步均需 POF、J2-1 断电、TP1/高压轨释放、温度复核和已批准 cooldown | `PENDING / BLOCKER` |

厂家若提供与本表不同的正式测量方法或安全范围，应形成版本化变更评审；不得静默
覆盖已经采集的数据条件。

本项目所有进入 palette、面积混合、综合色域或 ΔE00 正式判定的 canonical Lab 均为
`D65/2°`。可以保留或另行导出 D50 结果，但必须从原始光谱按已记录的方法重新积分，
或使用明确命名和版本化的色适应步骤；禁止只改 illuminant 标签，也禁止把 D50 与
D65 数值放入同一统计序列。表中的 `5000±100 K` 外部 RAW 光源只服务空间均匀性、
色斑和残影成像，不定义 canonical Lab 的 illuminant。

## 8. 指标定义

所有指标必须同时记录值、单位、采样区间、带宽和不确定度：

```text
input_peak_current = 指定带宽下 PON 到 POF BUSY 结束的最大输入电流
input_mean_current = 同一区间的时间平均值
input_rms_current  = 同一区间的 RMS
input_energy       = ∫ V_TP1(t) × I_input(t) dt
vdd_droop          = 预刷新 TP1 中位值 - 刷新期间 TP1 最小值
rail_establish     = 命令/阶段标记到进入已冻结平台容差带的时间
rail_ripple_pp     = 已冻结平台区间内、指定带宽下的峰峰值
rail_decay         = POF BUSY 结束到轨进入释放阈值并持续 5 s 的时间
temperature_rise  = 运行中/运行后最高温度 - 运行前稳定温度
```

光学结果必须记录实际测量时点，而不只记录名义 `1min/10min/...`。初始状态必须
保存实测 Lab，不能只保存意图颜色。

## 9. 测量系统资格、R&R 与不确定度

### 9.1 仪器链资格

- 分光测色：标准板不移位 `n=10`，重新定位 `n=10`，至少跨两个会话；
- RAW：标准灰/白和暗场各 `n=10`，检查 clipping、平场和配准；
- 电流链：使用可溯源假负载在代表性 `0.1/0.5/0.9 A` 点校验；
- 电压链：TP1 档位及正/负高压档位分别用可溯源源表/校准器检查；
- 温度链：至少在 25℃和一个较高代表点与参考温度计比较；
- 时间链：用同一方波同时输入所有设备，验证相对偏移和漂移；
- 急停：假负载下至少三次验证切断、残压和人工复位。

### 9.2 系统级重复性

- 每个原厂六色基线至少三次冷启动是初步数据，不足以声称 P95/P99；
- 相对停止门应使用同布局、同初始态、同环境的匹配已知码控制；
- 进入未知码前，最坏已知码匹配 fixture 建议至少 `n=5`，正式统计建议 `n≥10`；
- `n<10` 时只使用“最大实测值 + U95”，报告中禁止标记为 P95/P99；
- 重复轮次记录重新夹持、操作者、日期和环境，以分离 repeatability/reproducibility。

### 9.3 建议验收线

| 指标 | 最低资格目标 |
|---|---|
| 固定夹具 Lab | 最大 pairwise `ΔE00≤0.5` |
| 重新定位 Lab | 最大 pairwise `ΔE00≤1.0` |
| 电流/能量/轨平台 | CV `≤3%` |
| 瞬态峰值 | CV `≤5%`，且带宽相同 |
| 稳态温度 | 标准差 `≤0.3℃`，测量链 `U95≤1℃` |
| RAW 标准灰 | 归一化亮度重复 `≤1%` |
| RAW 几何配准 | `≤1 px` |
| 时钟同步 | 偏差 `≤1 ms` |

总测量 `U95` 应不大于最小判定余量的 20%。Gage R&R 占判定跨度 `≤10%` 为
合格，`10～30%` 只能条件使用，`>30%` 为 NO-GO。

### 9.4 不确定度预算

每个正式结果至少合成：

- 仪器校准不确定度；
- 探头/分流器/放大器误差、温漂和带宽；
- 零点、量程、量化和数值积分；
- 夹具重复定位、光源漂移、环境变化；
- 操作者和会话间再现性；
- 温度探头滞后和热像 emissivity；
- 时间同步误差。

报告保存标准不确定度、合成方法、coverage factor 和 `U95`，不能只抄仪器
datasheet accuracy。

## 10. 绝对与相对停止门

令：

```text
U95(X) = 指标 X 的扩展不确定度
u_rep  = 重复性标准不确定度
B_lo/B_hi = 同布局、同初始态已知码基线的单侧界限
```

### 10.1 已可冻结的绝对门

| 事件 | 停止条件 | 动作 |
|---|---|---|
| TP1/VDD 低压 | `Vmeas - U95 < 2.4 V` | 立即停止、POF（若安全）、切断 J2-1 |
| TP1/VDD 过压 | `Vmeas + U95 > 3.6 V` | 立即硬件切断 |
| 面板温度 | `Tmeas + U95 + sensor_lag_margin ≥50℃` | 立即硬件切断 |
| 温度预警 | 任一点 `≥45℃` | 不再开始新 job，准备切断 |
| BUSY assertion | PON/DRF/POF 任一阶段 250 ms 内未观察到 BUSY | fail closed，无重试 |
| BUSY timeout | 任一正式阶段触发现有 timeout | POF/切断、锁定 |
| 电源状态 | PSU 离开 CV、进入 CC、OVP/OCP 或外部保护动作 | 立即切断 |
| 证据丢失 | 探头断开、overrange、丢触发、日志/hash/时钟证据缺失 | run 无效并停止 |
| 物理异常 | 异响、异味、烟、裂纹、弧光、快速热点或永久色斑 | 急停、隔离 |
| 断电证明 | J2-1 切断后 TP1 未在合理时间降至 `≤0.10 V` | 禁止接触和重上电 |

若温度测量链的 `U95 + lag margin >2℃`，不得把 48℃设为实测硬切值，必须相应
降低门限。

### 10.2 尚缺绝对数值的 HARD BLOCKER

| 指标 | 当前值 | 缺失证据 |
|---|---|---|
| 输入峰值/RMS/能量绝对门 | `PENDING` | `Iupdate` 为 TBD、供电与节点热审查 |
| TP3 VPH 正轨窗口 | `PENDING` | SPD1657B 正式范围和节点应力表 |
| TP5 PREVGL 负轨窗口 | `PENDING` | SPD1657B 正式范围和节点应力表 |
| TP6 VPC 负轨窗口 | `PENDING` | SPD1657B 正式范围和节点应力表 |
| Q1/Q2/L1/L2 绝对温度 | `PENDING` | 器件 datasheet、贴装降额和测量不确定度 |
| 控制器区绝对温度 | `PENDING` | SPD1657B/模组限制和测点相关性 |

25 V 电容、Q1 30 V、Q2 -20 V 等绝对额定只用于建立节点应力表，不能直接当作
正常工作窗口。历史“电源额定能力至少 1 A”也不是 1 A 安全限值。相对门不能替代
这些绝对门；占位未关闭时 C 不能 GO。

### 10.3 建议相对门

| 指标 | 建议停止线 |
|---|---|
| peak/RMS current、energy | `X > B_hi + max(0.20×|B_hi|, 5×u_rep)` |
| TP3/TP5/TP6 包络 | 超出 `[B_lo, B_hi]` 扩张 `max(0.10×max(|B_lo|, |B_hi|), 5×u_rep)` |
| 3.3 V droop | `droop > B_hi + max(0.10 V, 5×u_rep)` |
| temperature rise | `ΔT > B_hi + max(3℃, 5×u_rep)`，且仍受绝对温度门约束 |
| PON/DRF/POF duration | 超出匹配基线 `±20%` 或 `5×u_rep`；过短和过长均异常 |
| rail establish/decay | 超过基线上界 `20%` 或 `5×u_rep` |

所有相对门取“相对限值”和“绝对限值”中更严格者。原有少量约
`181 ms / 21.700 s / 140 ms` 的 PON/DRF/POF 记录只是 sanity reference，不能
单独建立统计门限。

### 10.4 未资格恢复候选与判据

`B/W/B/W` 当前只是 EC3 的恢复候选。它不是厂商认证安全 waveform，也没有完成
cooldown、连续刷新、温度和最大尝试次数资格验证；因此当前为 `NO-GO`，不能因发生
未知码残影或异常而直接执行。

进入 G 阶段前，EC3 必须生成经审查的不可变 recovery profile，至少冻结：每一步的
已知码 frame/hash、逐步授权、POF 与 J2-1 断电证据、TP1/高压轨释放阈值、开始下一步
前的器件/面板温度门、数值化 cooldown、最大尝试次数（绝对上限一套）以及失败隔离
规则。只有该 profile 已通过六种已知初始状态的资格测试，才可申请执行候选序列：

```text
原厂全黑
→ POF → J2-1 断电 → TP1/高压轨释放 → 温度复核 → 已批准 cooldown
→ 原厂全白
→ POF → J2-1 断电 → TP1/高压轨释放 → 温度复核 → 已批准 cooldown
→ 原厂全黑
→ POF → J2-1 断电 → TP1/高压轨释放 → 温度复核 → 已批准 cooldown
→ 原厂全白
→ POF → J2-1 断电 → TP1/高压轨释放 → 温度复核
```

每个颜色步骤都是新的、单独授权的已知码 job；不得在设备内自动连刷。cooldown 或
温度证据缺失、profile/hash 不匹配、任一步失败或已达到最大尝试次数时均 fail closed。

最终白色建议同时满足：

- `ΔE00 ≤ max(1.0, 已知恢复基线95%上界 + U95)`；当 `n<10` 时，“95%上界”沿用
  本文小样本规则 `max observed + U95`，不得伪报分位数；
- RAW 残影指标不超过已知恢复基线 `P95 + 3σ`；
- 均匀性、电流、轨释放、BUSY 和温度全部通过；
- POF 后人工切断 J2-1，并通过 TP1 断电门。

若测量系统噪声本身不能支持 `ΔE00=1.0`，应先改进测量系统，不能放宽恢复线。
恢复失败后隔离该面板，禁止下一初始态、下一候选或自动再次清屏。

“强制恢复”表示恢复合格是继续测试的必要条件，不表示过流、过压或过温后自动
发起四次刷新。发生电气异常时先急停、断电和评审，恢复本身仍需新的明确授权。

## 11. 每次硬件动作的人工门禁

即使 C 最终通过，每次动作仍按以下顺序逐项向用户取得明确授权：

1. 面板是否已经断电；
2. 如需刷写，是否允许刷写 COM8；
3. 探头是否在断电状态安装并复核；
4. 是否允许上电；
5. 用户是否确认 3.3 V、电源 CV、限流、温度和仪器正常；
6. 是否允许发送该精确 test ID/hash 的指定测试帧；
7. 刷新后用户是否确认画面、电流、轨和温度；
8. 若需恢复，是否授权精确的恢复动作；
9. 是否已经人工切断 J2-1；
10. 用户是否确认 TP1 接近 0 V，且必要时高压轨已经释放。

任何异常禁止自动重试。网络超时也不得重发刷新请求，应先查询既有 job/report。

## 12. 当前状态与 go/no-go

| 项目 | 状态 |
|---|---|
| 测量系统设计 | IN PROGRESS |
| 实际仪器清单与元数据 | NOT STARTED |
| 光学夹具资格 | NOT STARTED |
| 电气同步采集资格 | NOT STARTED |
| 外部 J2-1 急停 | NOT VERIFIED |
| R&R / uncertainty | NOT STARTED |
| 绝对电流/高压/器件温度门 | BLOCKED |
| Hardware tested | NO |
| D 阶段硬件 GO | NO-GO |
| F 未知码硬件 GO | NO-GO |

下一步只允许继续完成仪器盘点、夹具/安全链设计、元数据、模拟数据和离线审查。
本文件不得被解释为任何硬件授权。2026-08-06 的可行性阶段降级修订见 §13。

## 13. 版本化变更评审记录

### 13.1 2026-08-06：可行性探索阶段的测量链降级（用户批准）

背景与范围：用户明确当前目标为"更多单像素颜色"的可行性分析（yes/no 级判断），
不要求完整色度精度。本修订仅在可行性探索范围内放宽 §4 的仪器配置要求，不改变
§10 的停止门框架、§11 的每次动作人工门禁和 §12 的正式 go/no-go 结论。

允许项（仅适用于可行性探索）：

1. 高压轨测量：确认可编程电源输出为隔离/浮地，并把板 GND 与示波器地做单点、
   明确、经记录的连接后，允许用额定足够的 10× 无源探头单端测量 TP3/TP5/TP6
   对板 GND 的包络，万用表测稳态轨压；该连接审查记录写入对应 run 文档。开关
   节点与跨元件测量（SW 振铃、Q1/Q2 Vds 等 H1 项目）仍要求差分探头，不在本次
   放宽范围。
2. 光学证据：允许以 RAW 相机 + 灰卡 + 固定 5000 K 光源 + 固定几何的相对对比，
   作为"未知码是否产生与六个已知色均不同且可保持的颜色"的可行性证据。

限制与标注：

- 依本条获得的全部结果必须标注 `experimental`，不得回填正式 palette，不得用于
  formal Lab/ΔE00、保持率判据或 area-mix 正式资格；canonical Lab 仍以分光测色仪
  补测为准，补测前 §3 相关出口项保持未勾选。
- §10.2 六个绝对门保持 `PENDING / BLOCKER`；正式 C/D/F 资格照旧 NO-GO，须补齐
  §4 完整仪器链与 §9 R&R 后重新评审。
- 未知码实验仍需独立的实验固件实现授权与 §11 逐项人工授权；本修订不构成任何
  硬件动作授权。

不放松项：§4.4 电源切断与急停安全链（可编程电源 + OVP/OCP + 锁存开关 + 实体
急停 + 输入电流测量）、温度监视（任一点 ≥45℃ 不再开始新 job，面板 ≥50℃ 立即
硬件切断）、TP1 `≤0.10 V` 断电证明、正式六色 guard、单次运行无自动重试、任何
异常 fail closed。

批准：用户于 2026-08-06 会话中明确批准；记录：集成会话。后续若厂家提供正式
测量方法或安全范围，按 §7 形成新的版本化变更评审，本条不覆盖厂家数据。
