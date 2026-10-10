# MF-1750 六色电子纸扩展颜色与亮度等级技术可行性结论

文档日期：2026-08-05

结论状态：2026-08-09 已按新增 STM32/OQC runtime-LUT 证据修订；仍未授权波形硬件实验

适用对象：MF-17506-M009F-T / M009F-T、1024×600、MF1750 Rev A1、双 SPD1657B rev `0x04`

基线硬件：R15 已拆、R16=0 Ω、GPIO7=CS1、GPIO10=CS2

技术审查源码基线：`867efdd`

Hardware tested in this review: `NO`

## 1. 决策摘要

扩展单像素颜色和亮度等级在多粒子电子纸的物理原理上具有研究价值。当前正式
ESP32 固件仍只具备在厂家片上 OTP 波形不变条件下做黑盒验证的能力；2026-08-09
新增的 STM32/OQC 工程已直接证明 SPD1657/E2802 存在 MCU runtime-LUT 模式，
但尚未提供可确认适配当前双控 3-bit 屏、且可移植到 ESP32 的完整 waveform 实现。

当前判定为技术上可研究的范围（不构成执行授权）：

- 整理屏幕、控制器、PCB、批次和测量系统资料；
- 建立厂家六色的电气、光学和保持基线；
- 测量原厂六色 `6×6` 旧状态到新状态转换矩阵；
- 在隔离实验入口、小面积、单次刷新和强制恢复条件下验证未分配像素码；
- 继续比较六色原生最近色、误差扩散和面积混色。

当前禁止执行：

- 猜测或枚举 SPD1657B 寄存器；
- 从 SPD1656 移植 LUT、PartialRAM、电压、帧率或局刷命令；
- 修改 `PWR/BTST/POFS/PLL/PWS/T_VDCS` 固定参数；
- 自定义 LUT、内部相位、帧数、占空比或末端修正脉冲；
- 修改 VCOM、VGH/VGL、VSH/VSL 或照搬专利电压；
- 在没有硬件断电、过流、过压和温度联锁时做无人耐久测试。

所以本项目目前的正式结论是：

> 第一轮“六色基线 + 6×6 转换矩阵 + 小面积数字编码探针”有条件可行；runtime
> LUT 的存在性不再阻断。当前阻断已收窄为：匹配当前屏的 3-bit 格式/载荷、
> ESP32 可移植 loader、字段/电压/温区定义、可观测性和保护能力。

## 2. 直接证据与推论边界

### 2.1 面板直接证据

`参考资料/MF-1750..1).pdf` 记录：

- 完整型号 `MF-17506-M009F-T`，模块 `M009F-T`；
- 7.50 英寸、1024×600；
- `3-bit E6 full display capabilities`；
- 双 SPD1657，参考电路标注 SPD1657B；
- 片上显示 RAM、LUT、内部温度传感器和片上 OTP waveform；
- on-chip booster/regulator 控制 VCOM、Gate 和 Source 电压；
- 工作温度 0～50℃；
- 命令表要求另查 SPD1657B datasheet；
- 电气及光学性能只在 InkCubic 指定控制器和波形下保证。

该规格书没有写明 `Spectra 6` 商标或具体颜料配方。因此，“当前屏就是
Spectra 6 四颜料体系”属于高度一致的推论，不是料号级直接证据；最终仍需
InkCubic/E Ink 对该型号和批次确认。

E Ink 官方资料可以证明 Spectra 6 平台为四颜料体系，也可以证明 Ripple/第二代
waveform 与兼容的新控制器能够增加颜色，但不能证明当前 SPD1657B rev `0x04`
和当前 OTP 已包含 Ripple、Sparkle 或额外颜色模式。

### 2.2 像素格式的三层含义

必须区分：

1. 应用帧容器：当前为 4bpp，每个 byte 放两个 nibble；
2. 面板标称颜色能力：规格写 3-bit E6；
3. 最终稳定光学状态：取决于当前控制器、OTP、温度和历史状态。

当前正式有效码是：

| code | 颜色 |
|---:|---|
| `0x0` | 黑 |
| `0x1` | 白 |
| `0x2` | 黄 |
| `0x3` | 红 |
| `0x5` | 蓝 |
| `0x6` | 绿 |

因此需求中的“`0x6～0xF` 是否有效”必须改为：

```text
0x4、0x7 是否为 3-bit 空余索引；
0x8～0xF 的 bit3 是否被忽略、形成 alias、被保留或产生未定义结果。
```

4bpp 只证明传输容器可携带 16 个 nibble 值，不证明存在 16 个 LUT 状态。
`0x4/0x7` 是优先级最高的候选；`0x8～0xF` 应归类为 bit3 alias/协议鲁棒性
验证，而不是八个独立的新颜色候选。

### 2.3 当前固件和控制器能力

当前正式入口会在任何初始化、DTM、PON 或 DRF 前拒绝 `0x4/0x7..0xF`：

- HTTP raw ingress 在 `src/main.cpp` 逐 nibble 检查；
- `epdDisplayFrameAtFrequency()` 在 `src/epd_driver.cpp` 再次完整检查；
- 正式 `/api/frame` 不能直接用于未知码扫描。

现有刷新链路是：

```text
双控制器初始化与 CCSET
→ 分别上传两个 512×600 DTM
→ 双选 PON
→ 固定 BTST2 second setting
→ DRF(0x12, 0x00)
→ POF
→ 厂商规定的等待、PSR 和安全收尾
```

当前正式 ESP32 固件仍没有：

- waveform ID 读取或选择；
- phase table、每阶段帧数或每阶段电压 API；
- old-frame RAM；
- x/y window addressing；
- 可验证的局部刷新流程；
- 内部温度传感器读取 API。

新增 `参考资料/REG-API-oqc(1)(1)/REG-API-oqc/` 提供了不同层级的新证据：

- `User/EDP_init.c` 可在 MCU-LUT/CRC-bypass 模式向 `0x20` 写 535-byte 2-bit
  明文表，且 OQC YX 产物实际保留 UART 更新该表的入口；
- 该明文入口只控制 master CS，却写全屏 `1024×600` TRES 且没有 CCSET；表头 VCOM/
  Frame 被保存但没有用于实际 VCOM/PLL，UART 更新也不检查提供长度，不能直接替代当前
  双控制器 3-bit 链；其 BUSY 等待也没有超时；
- Cortex-M3 库导出加密 `loadWF`，包含 `LUT1_DATA` 和 AES/MD5/SHA 逻辑；库名
  含 3bits，但对象宏为 `E5_3Bit_Mode=0`，其语义、源码及 ESP32 ABI 均缺失；
- 842-byte `WF20_25` 标注 E5 2-bit，是封装输入，不是可直接写入 LUT 的 payload；
- 3-bit 样例与 2-bit 路径的红黄码命名冲突；2-bit 文件自身对白色也同时出现 `0x11`/
  `0x55` 两种填充值，必须以具体模式和本项目真屏映射为准。

详见 [`SPD1657_RUNTIME_WAVEFORM_REFERENCE_AUDIT_2026-08-09.md`](SPD1657_RUNTIME_WAVEFORM_REFERENCE_AUDIT_2026-08-09.md)。

实测约 21.7 秒的 DRF 由 SPD1657B 在 BUSY 期间自主运行。SPI 时钟或主机命令间
等待只能改变数据上传或外围时间，不能据此声称改变了内部电泳相位。

样例中的 `0x86 Interlace` 只标记为未来 dither image 预留，并注明依赖
dithering area；没有区域格式、波形、旧帧要求和安全限制，当前不得调用。

## 3. Rev A1 硬件能力与缺口

Rev A1 是屏幕接口和参考高压外围板，不是独立的可编程 TCON 或 waveform
发生器。两颗 SPD1657B 位于屏模组，ESP32 当前只能控制 SPI、RST、BUSY 和
双 CS。

现有测试点：

| 测试点 | 信号 | 备注 |
|---|---|---|
| TP1 | 3V3 | 面板输入电源 |
| TP2 | GND | 参考地 |
| TP3 | VPH | 正高压 |
| TP4 | PREVGH | 经 R5=0 Ω 与 VPH 相连，基本为同一轨 |
| TP5 | PREVGL | 负高压轨 |
| TP6 | VPC | 负压泵轨 |
| TP7 | VDDIO | 逻辑电源 |
| TP8 | CS1 | 主控制器片选 |
| TP9 | CS2 | 从控制器片选 |
| TP10 | BUSY_N | 共享忙信号 |

当前没有专用测试点或 MCU 反馈用于：

- VCOM、VSH/VSH_LV/VSH_LV2、VSL/VSL_LV/VSL_LV2；
- 单像素 Source 电压、TFT Gate clock、行/帧同步；
- 输入电流、高压轨 ADC、PGOOD；
- 面板、SPD1657、Q1/Q2、L1/L2 温度；
- 高压过压、过流和硬件比较器急停。

`EPD_PIN_SWC=-1`，软件 POF 后 J2-1 的 3.3V 仍然存在；GPIO 拉低不是物理断电。
因此当前不能无人值守进行未知波形扫描或耐久循环。

板上多颗高压相关电容额定为 25V。任何专利中的 ±27V/±30V 示例都不能移植，
也不能只按平均值判断电容、二极管、MOSFET 和开关节点是否安全。

## 4. 对五个核心假设的判定

### H1：存在未公开颜色编码

有条件可验证。最有信息价值的是 `0x4/0x7`；`0x8～0xF` 的主要问题是 bit3
别名或保留行为。未知码属于数据值，不是未知 SPI 命令，风险低于改 LUT/高压，
但仍可能选择保留 OTP 状态、保持旧态或产生难清残影，因此必须小面积、单次、
冷启动和强制恢复。

### H2：同一基础颜色存在多个稳定亮度

物理上可能，当前平台不可直接验证。相同目标码在固定 OTP 下只会调用既定状态；
ESP32 目前不能改变目标色选择阶段的内部脉冲。若只利用历史状态得到浅色或深色，
通常会与 H3 的残影/历史依赖混淆，不能直接认定为可用亮度等级。

### H3：初始状态影响最终颜色

当前完全可验证，且应先于未知码测试。它既能评价现有 OTP 的擦除能力，也能为
C3 转移感知图像优化器提供真实 6×6 光学、功耗和残影代价。

### H4：中间颜色稳定保持

判据合理，但只能在发现候选后进行。必须以统一的 1 分钟结果为保持基线，再测
10 分钟、1 小时、24 小时和必要的 72 小时，且固定温度、湿度和照明条件。

### H5：扩展颜色具有工程价值

判据方向正确。正式采用还需跨位置、左右控制器、多个面板和多个批次验证；单屏
发现只能标为 `experimental`。同时必须与现有六色误差扩散和面积混色比较，证明
单像素状态在色差、颗粒感、边缘、刷新、恢复和寿命上确有综合优势。

## 5. 原需求必须修订的项目

### 5.1 小区域与测试图面积

全屏为 614400 像素：

- `64×64` = 4096 px = 0.667%；
- 左右各一个 `64×64` = 8192 px = 1.333%；
- `128×128` = 16384 px = 2.667%；
- 16 个 `200×100` = 320000 px = 52.083%；
- 十个非正式码的 `200×100` 区域合计占 32.552%。

所以完整 16 编码图不能作为第一次未知码实验。第一轮应每次只测一个候选，
在左右半屏各放一个 `64×64` 镜像 ROI，其余使用已知白色和黑白定位锚点。

这只是“未知目标码面积受控”；由于当前仍执行全屏 DRF，不能称为电气上的局刷。

### 5.2 6×6 转换矩阵

采用一张六条水平初始色带和一张六条垂直目标色带，交叉区域一次覆盖全部 36 个
转换。每半屏镜像一套矩阵，重复轮次交换或旋转位置，以把历史效应与面板位置、
控制器差异分离。

若每次重复包含 `黑→白→黑→白`、初始图和目标图，5 次正式重复约 30 次刷新，
远少于逐组合执行。

### 5.3 波形解析输出名称

当前只能形成“原厂命令、BUSY、输入电流和外部电源轨包络表”。VPH/VSH/VSL
等供电轨并不等于某个像素相对 VCOM 的实际驱动波形，不能由外部包络反推完整
phase table。

### 5.4 电荷平衡公式

原 `I_wave = Σ(Vi × ti)` 的单位是 V·s，不是电流或电荷。若未来取得 LUT，建议
至少分别记录：

```text
A_dc  = ∫[V_pixel(t) - VCOM(t)]dt
D_abs = ∫|V_pixel(t) - VCOM(t)|dt
Q     = ∫i_pixel(t)dt
E_in  = ∫V_supply(t) × I_supply(t)dt
```

同时限制峰值有效电压、最长连续同极性时间、总时长和累计刷新剂量。只满足 signed
area 接近零不是安全充分条件。当前读不到像素电压和 OTP phase，因此只能记录外部
代理量，不能声称已经证明单像素 DC balance。

### 5.5 测色与统计

若 Lab/ΔE00 是正式门禁，分光测色仪应从“推荐”提升为“必需”。RAW 相机主要
用于均匀性、色斑、边缘和残影空间图；未经光谱、暗场、平场和线性标定，不能
单独生成可追溯 Lab。

必须冻结 illuminant、observer、45/0 几何、孔径、lux/CCT、仪器和校准信息。
规格书第 15 页的 Lab 数值是产品验收边界，不是当前面板调色板中心。

`L*差≥8、色相角≤10°` 只适用于有足够彩度的颜色；黑、白、灰附近应比较 L* 和
C*，不能使用不稳定的 hue。重复性应报告均值、标准差、P95/最大值和 95% CI；
新增色与最近基础色距离建议以置信区间下限判定。正式产品结论需要多屏、多批次；
单屏只作为 feasibility。

### 5.6 停止条件

“峰值电流小于基准 120%”和“温升小于基准 10℃”只能作为相对预警。当前尚无
定量基准，而且在 45℃环境下再允许升温 10℃会超过面板 50℃工作上限。

后续必须同时冻结：

- 基于元件、面板和电源规格的绝对限值；
- 基于多次原厂刷新统计的相对限值；
- 测量误差和探头带宽；
- 3.3V droop、退出 CV、高压建立和释放时间；
- BUSY 边沿、日志完整性、探头连接和仪器饱和状态。

任一保护证据丢失都应 fail closed，禁止自动重试。

## 6. 当前对第一轮十个问题的回答

| 问题 | 当前答案 |
|---|---|
| 1. 墨水体系 | 只证实 3-bit E6；高度符合 Spectra 6，但料号级四颜料配方待厂家确认 |
| 2. 每像素位数 | 外部帧是 4bpp packed；面板标称 3-bit 颜色能力 |
| 3. 未使用编码 | `0x6` 已是绿；`0x4/0x7..0xF` 尚未实测且正式 API 主动阻断 |
| 4. 六色是否依赖初态 | 尚未系统测量；6×6 矩阵可回答 |
| 5. 是否上传可修改 LUT | 已直接证实 MCU runtime-LUT、`0x20` 和 CRC-bypass 路径；当前仅有不完整的 2-bit 明文实现及 Cortex-M3 加密 loader，尚无可安全移植的双控 3-bit ESP32 实现 |
| 6. PCB 能否独立控制相位/电压 | 当前不能；没有可编程 TCON、高压 DAC 或已知寄存器定义 |
| 7. 原厂电压和阶段数 | 只知外部初始化参数和 DRF 约 21.7 秒；内部 phase 数和像素电压未知 |
| 8. 是否有安全全白恢复 | 有原厂 OTP 黑白动作，但异常恢复尚未资格验证；物理断电仍需 J2-1 |
| 9. 是否适合自定义波形 | 机制可行性已提升，但当前真屏仍不适合；先完成 3-bit 格式、匹配载荷、loader、安全与恢复资格 |
| 10. 仍需补什么 | SPD1657B/OTP 资料、VCOM/Source 测量夹具、自动断电、温流/高压/PGOOD 联锁、牺牲屏和黄金屏 |

原需求的阶段出口存在冲突：第一轮被定义为止于编码扫描和 6×6 矩阵，却又要求
给出原厂内部电压等级和阶段数量。后者依赖 SPD1657B/OTP 资料或专用测量平台，
不能作为当前第一轮必须获得的数值；第一轮允许把它明确关闭为“资料阻断”。

## 7. 进入自定义波形前的硬门禁

以下项目全部完成后，才能单独评审自定义 LUT、时间或电压实验：

1. SPD1657B rev `0x04` 完整 command datasheet，或至少取得与参考库一致的 runtime-LUT 字段合同；
2. 当前 MF-17506-M009F-T 批次的 OTP waveform ID、版本和温区；
3. 3-bit 颜色编码、`0x86`、window/old-frame/partial 定义；
4. 535/544-byte、`LUT1_DATA`、模式选择、字段换算、合法范围和读回办法；
5. 厂商规定的恢复、冷却、最大连续刷新和寿命限制；
6. VCOM、VSH/VSL 各档、SW_H/SW_C 和 sense 节点的安全测量夹具；
7. 输入电流、关键器件温度、高压窗口和 PGOOD 监测；
8. 默认断开的硬件 VDD 开关、看门狗和实体急停；
9. 专用牺牲屏，以及不执行未知波形的黄金参考屏；
10. 能复现厂家波形并验证恢复、DC dose、峰值和温度的批准记录。

新增参考已排除“本控制器绝对没有 runtime LUT”这一分支。如果厂家不能提供
`eload_20250305b1.c`、ESP32/Xtensa loader 或 decoded 3-bit 格式，Rev A1 + ESP32
仍无法安全完成 H2/H5，需要使用厂商专用开发平台或取得正式移植包。

## 8. 数据与交付边界

单张宽 CSV 不足以表达多相波形和多个 ROI。后续建议至少拆分：

- `run`：panel/board/controller/firmware/frame/test identity；
- `optical_measurement`：ROI、timepoint、Lab、仪器、光学几何；
- `electrical_summary`：输入电流、能量、各 rail 包络、BUSY、温度；
- `waveform_phase`：仅在取得正式 LUT 后记录 phase、repeat、source、VCOM 和 dose；
- `event_recovery`：停止原因、异常、恢复次数与结果；
- 原始 scope、RAW、测色和日志文件路径、SHA-256、仪器/探头/采样参数。

`firmware_commit` 之外还必须记录 build tag、binary SHA-256、git dirty 状态、配置
hash、完整帧和双 DTM hash。所有字段应带单位、枚举或 `null_reason`，不得用空值
暗示“正常”。

## 9. 参考证据

- 面板规格：`参考资料/MF-1750..1).pdf`；
- 厂商样例：`参考资料/E6_73_sample code_V1.2_20250116/`；
- 新增 runtime-LUT 参考：`参考资料/REG-API-oqc(1)(1)/REG-API-oqc/`，审计见
  `docs/SPD1657_RUNTIME_WAVEFORM_REFERENCE_AUDIT_2026-08-09.md`；
- 正式颜色和帧格式：`src/epd_config.h`；
- 正式颜色校验与刷新链：`src/epd_driver.cpp`、`src/main.cpp`；
- Rev A1 硬件测试点：`docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`；
- D0 真屏证据：`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`；
- 快速/局刷证据边界：`docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md`、
  `research/fast_refresh/evidence_matrix.json`；
- E Ink Spectra 6：<https://www.eink.com/tech/detail/How_it_works>；
- E Ink Ripple：
  <https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays>。

本文件只冻结技术判断，不授权上电、刷写 COM8、访问刷新 API 或执行任何硬件
测试。实际任务由 `TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md` 管理，必须由
用户另行安排并逐门授权。
