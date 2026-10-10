# MF1750 WROOM B3 R3 设计约束台账

日期：2026-08-24  
模式：`REVISION`  
目标修订：`B3-WROOM-POWER-TF-R3-SCHEMATIC`  
当前设计状态：`R3 SCHEMATIC VERIFIED / PCB HOLD`  
制造状态：`NOT RELEASED`

## 1. 权威源与不可变边界

- B3 权威项目：
  `hardware/mf1750_wroom_b3_power_tf/mf1750_wroom_b3_power_tf.{kicad_pro,kicad_sch,kicad_pcb}`；
- 前件 B2：`hardware/mf1750_devkitc_b2_pcba_margin/`；
- B2 三件套 SHA-256：
  - `.kicad_pro`：`fcd393069f22846615113f8296d6553c5ffeee8ba507b7475f81baae9fe4aa27`；
  - `.kicad_sch`：`bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb`；
  - `.kicad_pcb`：`462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238`；
- B2 已经真屏验证的 FPC、高压泵、并行双 CS 以及上部元件相对几何不重排、
  不压缩；B3 只改造控制与供电入口并向下扩展。

## 2. 硬需求

- MCU 采用 `ESP32-S3-WROOM-1-N16R8`，LCSC/JLC `C2913202`；
- 四层 PCB，当前 R3 staging 外形候选 `80 × 125 mm`；
- microSD/TF 从 PCB 下边缘向板内插入；
- 保护型单节 3.7 V LiPo，具备充电、PowerPath、按键开关机与低压关断；
- 1 个电源键、2 个用户键，BOOT/RESET 为额外维修键/测试点；
- 允许手工热台/返修，除开关电源热回路外不做极限密排；
- 所有主要器件以嘉立创/LCSC 可采购、可装配为目标，下单前重查库存与贴装属性。

## 3. 电源树与启动状态

```text
USB-C VBUS
  -> F1 resettable fuse
  -> 5 V TVS / USB ESD
  -> BQ24074 IN
       -> BAT+ protected 1S LiPo, external 10 k NTC
       -> OUT = VSYS_RAW
            -> STM6600CS25DM6F VCC
            -> TPS63070 VIN
STM6600 EN_SYS -> TPS63070 EN
TPS63070 3.3 V -> SYS_3V3
  -> ESP32-S3-WROOM-1-N16R8
  -> microSD
  -> TPS22950 -> EPD_SW_3V3 -> B2 R4/R8 -> EPD_3V3 / V_B
                                      -> SN74CB3Q3245 8-bit bus switch
```

- `BQ24074`：`EN1=1, EN2=0`，USB500 模式；`RISET=1.78 kΩ`，标称快充约
  500 mA；`RILIM=3.16–3.24 kΩ`，首板采用 1% E96 可采购值；`ITERM` 明确
  NC，使用内部约 10% 终止电流；`RTMR=46.4 kΩ`，约 6.25 h；`CE=0`；
- 电池接口必须是 `BAT+ / BAT- / 10 kΩ NTC`；若未连 NTC，充电不得被
  软件或固定电阻默认绕过；
- `STM6600CS25DM6F`：高有效 EN，`VTH+=3.4 V`，回差 200 mV，
  `tON_BLANK(min)=11.2 s`；`VREF` 必须 1 µF，`VCC` 就近 0.1 µF；本型号要求
  用户持续按键到 ESP32 拉高 `PS_HOLD`，若产品要求短按即锁存开机则保持功能
  `HOLD`，不得在未验证时宣称短按可用；
- `TPS63070`：1.5 µH；输入 bulk 为 `C31-C33` 3 × 10 µF，另有
  `C46=10 µF/0603` 紧贴 VIN-GND；输出 bulk 为 `C34-C36` 3 × 22 µF +
  `C37` 10 µF，另有 `C47=10 µF/0603` 紧贴 VOUT-GND；`R29=10 kΩ` 串在
  `VSYS_RAW(VIN) -> DCDC_PS_SYNC`；`VAUX=100 nF`；反馈 470 kΩ/150 kΩ
  对应 3.3 V；`VSEL=0`，`FB2=NC`。上述值与封装按 TI TPS63070 Rev.B
  §11.1 固化，紧贴程度仍须在 PCB 通过视觉/DRC 审查；
- `TPS22950-Q1`：`RILIM=1.50 kΩ`，首板标称限流约 0.76 A；ON 依靠内部
  下拉并另设 100 kΩ 外部下拉，保证启动默认断开；FLT 上拉到 `SYS_3V3`；
- `SI0/SDA` 是双向线：固件在寄存器读回时会把 GPIO11 切为输入。因此全部七根
  EPD 数字线统一使用 `SN74CB3Q3245PWR`（TI，LCSC `C470961`）八位双向总线
  开关；该器件由 R4 后端 `EPD_3V3` 供电并有官方 Ioff/掉电隔离规格；
- U6 的 `/OE` 以 10 kΩ 上拉到 `EPD_3V3`。GPIO38 不直接跨接到这个可断电域，
  而是驱动 `Q3=2N7002/C8545` 的栅极；Q3 漏极拉低 `/OE`，源极接 GND，栅极
  另有 100 kΩ 下拉。因此 GPIO38 高电平才接通七根线，复位/低电平时默认隔离；
  EPD 断电时不消耗总线开关约 1 mA 的工作电流，也不存在 MCU 控制脚向断电域
  注入电流的直连路径。

## 4. ESP32-S3 GPIO 候选分配

| GPIO | 候选功能 | 备注 |
|---:|---|---|
| 1 | `BAT_ADC_OPTION` | R49 顶端首板 DNP；R50=100 kΩ 与 100 nF 保留 |
| 2 | `PS_HOLD` | 启动后、释放电源键前尽快置高；100 kΩ 下拉 |
| 4 | `MCU_BUSY_N` | 保持已验证面板映射，输入 |
| 5 | `MCU_RST_N` | 面板输出 |
| 6 | `MCU_DC` | 面板输出 |
| 7 | `MCU_CSB` | 面板主 CS |
| 8 | `USER_KEY_1_N` | 10 kΩ 上拉，按键到 GND |
| 9 | `USER_KEY_2_N` | 10 kΩ 上拉，按键到 GND |
| 10 | `MCU_CS2` | 保持已验证独立从 CS |
| 11 | `MCU_SI0` | 保持已验证双向 `SI0/SDA`，支持寄存器读回 |
| 12 | `MCU_SCL` | 保持已验证面板 SCLK |
| 13 | `EPD_PWR_EN` | TPS22950 ON，100 kΩ 下拉 |
| 14 | `TF_CD_N` | 卡检测；极性待实物复核 |
| 15 | `TF_SCLK` | microSD SPI |
| 16 | `TF_MOSI` | microSD SPI |
| 17 | `TF_MISO` | microSD SPI |
| 18 | `TF_CS_N` | microSD SPI |
| 19 | `USB_D-` | 固定原生 USB，不改用 |
| 20 | `USB_D+` | 固定原生 USB，不改用 |
| 21 | `PWR_INT_N` | STM6600 开漏中断，10 kΩ 上拉 |
| 38 | `EPD_BUF_CONNECT` | 高有效；经 Q3 下拉 U6 `/OE`，100 kΩ 栅极下拉 |
| 43/44 | UART0 TX/RX 测试点 | 不做常规接口插座 |
| 47 | `USB_INPUT_VALID_N` | BQ24074 PGOOD，100 kΩ 上拉 |
| 48 | `EPD_FAULT_N` | TPS22950 FLT，10–100 kΩ 上拉 |

禁用/保留：

- GPIO0 仅用于 BOOT 维修键；
- GPIO3/45/46 是 strapping 引脚，不承担外设控制；
- N16R8 上 GPIO35/36/37 被 Octal PSRAM 占用，不引出为可用 GPIO；
- GPIO19/20 仅用于 USB D-/D+；
- GPIO39–42 保留外部 JTAG 测试焊盘；
- GPIO43/44 保留 UART0 调试。

`BAT_ADC_OPTION` 不作为首板必装功能。若直接把常供电 `BAT+` 经 220 kΩ 接到
关机的 ESP32 输入，可能通过输入钳位产生反向供电；因此 R49 默认 DNP。只有在
实测关机漏电并确认不会破坏 STM6600 硬关机后，才允许装配并标定该分压。

## 5. 信号隔离与原 B2 网络迁移

- U6 `SN74CB3Q3245PWR` 七路分别连接：`MCU_RST_N <-> RST_N`、
  `MCU_DC <-> DC`、`MCU_CSB <-> CSB`、`MCU_CS2 <-> CS2`、
  `MCU_SCL <-> SCL`、`MCU_SI0 <-> SI0`、`MCU_BUSY_N <-> BUSY_N`；
  第八通道两端明确 NC；
- `EPD_BUF_CONNECT` 高电平导通 Q3 并拉低 U6 `/OE`；复位时 Q3 栅极下拉，U6
  `/OE` 由 `EPD_3V3` 上拉并隔离。上电顺序为“GPIO 安全态 -> U5 ON -> 等待
  EPD_3V3 -> GPIO38 置高”，关机顺序完全反向；
- ESP32 在面板仍有电时复位也必须有确定状态：Q3 关闭后 U6 被上拉隔离；安全
  偏置必须放在 U6 的面板侧：`CSB`、`CS2` 各以 100 kΩ 上拉到 `EPD_3V3`，
  `RST_N`、`DC`、`SCL`、`SI0` 各以 100 kΩ 下拉到 GND。MCU 侧
  `MCU_BUSY_N` 以 100 kΩ 上拉到 `SYS_3V3`，与当前固件 idle=HIGH 一致；
- 已验证 B2 中 R16 继续装配，将 `CS2` 接至 `SL_CSB`；R15 继续 DNP；
- 旧 J2 DevKitC 排针只作 DNP 调试位，七根面板信号改接 MCU 侧网名，
  不与缓冲器输出对打；
- B2 原 `3V3` 入口在 B3 语义上更名为 `EPD_SW_3V3`；B2 PCB 局部名
  `/GND` 同步规范化为 R3 全局 `GND`。U5 输出接该网，
  R4/R8 及已验证屏端分配保持。

## 5.1 已完成的 R3 原理图与 PCB 同步门

- 权威 R3 原理图 SHA-256：
  `158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0`；
- KiCad ERC 0 错误/0 警告，结构/电气契约 246/246，B2 原理图继承 655/655；
  解析规模为 176 个器件、175 个网络、552 个引脚节点；
- R3 PCB 已从现行 176 器件原理图重新同步：SHA
  `c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb`，
  native schematic-parity=0，项目 verifier 13/13 PASS；停车布局 DRC 为 144 项、
  205 个未连接，仍是 `HOLD`。
- R4 功能布局候选另加 H3/H4，SHA
  `349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf`；
  B2 保护集、693 个铜项目与 7 个 zone 设置保持，native parity=0、无 courtyard
  overlap/clearance/short/items-not-allowed，新区仍待布线。

## 6. USB、TF 与 ESD

- USB-C：CC1/CC2 各 5.1 kΩ Rd；D+/D- 各 22 Ω 串联，靠近 WROOM；
- USB 保护：`USBLC6-2SC6`，JLC `C2827654`；VBUS TVS 候选
  `SMF5.0A`/SOD-123，JLC `C908213`；
- USB 输入自恢复保险丝候选 `BSMD1206-075-16V`，JLC `C883128`；
- TF：Molex `1040310811`/`C585350`，使用 SPI 模式；CLK/CMD(MOSI)/DAT0(MISO)/
  DAT3(CS) 串联 22 Ω；卡侧 CMD、DAT0、DAT1、DAT2、DAT3 五根信号各
  10 kΩ 上拉；卡检测独立上拉；
- TF 六根暴露信号用 3 颗同型两路 ESD 阵列，不与 USB 共用器件位号。

## 7. 器件与机械 HOLD

- `J6` 的板端物料暂定 `JST S3B-PH-KL` / `C20089271`，但电池线序、
  塑壳防反插与电池包实物尚未对插确认，维持 `HOLD`；
- 电池具体 MPN、容量、放电能力与 10 kΩ NTC 曲线未冻结；
- 用户键最终外壳位置尚未冻结；电气上可先完成，PCB 位置不锁定；
- WROOM 天线上方/下方/前方金属、电池、排线和外壳净空必须在外壳 CAD
  到位后复核；
- 本台账不解除任何真屏上电门，PCB 修订期间不操作继电器/J2/刷屏。

## 8. 一手资料

- Espressif `ESP32-S3-WROOM-1/1U` datasheet v1.8：
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
- Espressif ESP32-S3 hardware design guidelines：
  <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html>
- TI BQ2407x datasheet：<https://www.ti.com/lit/ds/symlink/bq24072.pdf>
- ST STM6600/STM6601 datasheet：<https://www.st.com/resource/en/datasheet/stm6600.pdf>
- TI TPS63070 datasheet：<https://www.ti.com/lit/ds/symlink/tps63070.pdf>
- TI TPS22950-Q1 datasheet：<https://www.ti.com/lit/ds/symlink/tps22950-q1.pdf>
- TI SN74CB3Q3245 datasheet：<https://www.ti.com/lit/ds/symlink/sn74cb3q3245.pdf>
- JLC/LCSC `2N7002` / `C8545`：<https://jlcpcb.com/partdetail/JiangsuChangjingElec-2N7002/C8545>
