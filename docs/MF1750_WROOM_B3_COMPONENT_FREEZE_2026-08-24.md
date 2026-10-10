# MF1750 WROOM B3 器件与布局冻结记录

日期：2026-08-24  
状态：`B3-WROOM-COMPONENT-FREEZE-R2 / SCHEMATIC FROZEN`  
发布等级：`R3 SCHEMATIC VERIFIED — PCB PLACEMENT/ROUTING HOLD — NOT PCBA RELEASE`

## 1. MCU 决策

采用 Espressif `ESP32-S3-WROOM-1-N16R8`，LCSC/JLC `C2913202`。不采用
ESP32-S3 裸芯片，也不把完整 DevKitC 开发板作为量产核心。

理由：模块已集成 ESP32-S3、晶振、16 MB Flash、8 MB Octal PSRAM、射频匹配和
PCB 天线；嘉立创可直接 SMT。与裸芯片相比，RF、存储器和晶振风险显著降低；与
DevKitC 相比，可删除电池到 5 V 的升压及防倒灌支路，降低静态功耗和板上器件数。

现有 B2 的 DevKitC 2×22 焊盘在放置候选中保留并标记 DNP，只作为工程调试/转接
候选；不得与 WROOM 同时装配或同时驱动信号。

证据：

- [Espressif ESP32-S3-WROOM-1 数据手册](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
- [JLCPCB C2913202](https://jlcpcb.com/partdetail/ESP32-S3-WROOM-1-N16R8/C2913202)

## 2. 冻结电源树

```text
USB-C VBUS ── BQ24074 PowerPath ── VSYS_RAW ── STM6600 / EN_SYS
     │                 │                              │
     │                 └── 1S 3.7V protected LiPo    └── TPS63070 → SYS_3V3
     │                                                      ├── WROOM
     └── D+/D- → ESD/series resistors → WROOM native USB    ├── TF
                                                            └── TPS22950 → EPD_SW_3V3
                                                                         └── B2 R4/R8 → EPD_3V3 / V_B
                                                                                          └── EPD 8-bit Ioff bus switch
```

- USB-C 同时承担充电和 ESP32-S3 原生 USB 下载/调试；不增加 USB-UART 芯片；
- 删除 DevKitC 路线中的 `TPS61023` 5 V 升压和 `LM66100` 5 V 防倒灌；
- `TPS63070` 输出 3.3 V，供应 WROOM、TF 和面板受控支路；首板核对 Wi-Fi、写卡和
  面板刷新同时发生时的峰值与热裕量；
- 面板由 `TPS22950CQDDCRQ1` 单独开关并限流，首板 `RILIM=1.50 kΩ/1%`，典型约
  0.76 A；
- WROOM/TF 同属 `SYS_3V3`，TF SPI 不需要跨断电域隔离；EPD 可独立断电，因此
  七根控制/状态线统一经过一颗 `SN74CB3Q3245PWR` 八位双向总线开关。该器件
  明确提供 Ioff/掉电隔离，且保留 `SI0/SDA` 寄存器读回；原计划的两片
  `SN74LVC125APWR` 加单通道开关不再装配；
- U6 由 `EPD_3V3` 供电并在 `/OE` 处上拉；GPIO38 通过
  `Q3=2N7002/C8545` 开漏下拉控制，不直接跨接到可断电域。GPIO38 高电平接通、
  复位或低电平隔离；
- `STM6600` 电源键提供开机、正常关机通知、PS_HOLD 和长按强制关机。
  当前 `CS25` 型号要求用户保持按键直至 ESP32 拉高 `PS_HOLD`；“短按即锁存
  开机”仍是功能 `HOLD`，如该交互不可接受则在 PCB 冻结前更换电源键控制方案；
- 可选电池 ADC 分压的 BAT+ 顶端电阻首板 DNP，避免关机时经 GPIO1 输入钳位
  反向供电；待关机漏电和 ADC 标定通过后再决定是否装配；

## 3. 主器件

| 功能 | 冻结料号 | LCSC/JLC | 状态 |
|---|---|---:|---|
| MCU/无线模块 | `ESP32-S3-WROOM-1-N16R8` | `C2913202` | 冻结 |
| 1S 充电 + PowerPath | `BQ24074RGTR` | `C54313` | 冻结 |
| 电源键控制 | `STM6600CS25DM6F` | `C443976` | 冻结 |
| 3.3 V buck-boost | `TPS63070RNMR` | `C109322` | 器件冻结；R29/C46/C47 已按 TI Rev.B §11.1 修正；PCB 紧贴布局待核 |
| EPD 限流开关 | `TPS22950CQDDCRQ1` | `C17349276` | 冻结 |
| EPD 八路双向掉电隔离 | `SN74CB3Q3245PWR` | `C470961` | 冻结 |
| EPD 隔离使能开漏 | `2N7002` SOT-23 | `C8545` | 冻结 |
| microSD/TF | Molex `1040310811` | `C585350` | 冻结 |
| USB-C | `TYPE-C-31-M-12` | `C165948` | 冻结 |
| 电源/用户按键 | Alps `SKSCLDE010` | `C115362` | 器件冻结；项目封装待核 |

库存、基础/扩展料和贴装类型只代表 2026-08-24 的可采购快照；BOM 上传时重新
匹配。

## 4. PCB 与机械合同

- 四层 PCB；B2 上方驱动区的器件相对位置和已测试关键走线不压缩、不重排；
- 板尺寸优先服从可焊、可返修、短电源回路和天线净空，不做极限小型化；
- 当前 R3 staging 板框为 `80 × 125 mm`；其中原 B2 功能区域为上部
  `65 × 60.5 mm`，其器件几何保持；
- WROOM 位于新增区右侧，PCB 天线朝右边缘，天线区禁止铜、走线、器件和金属
  紧固件；
- TF 卡座顶面安装，卡口在 PCB 下边缘，卡从外壳下侧向板内插入；
- USB-C 从左侧进入；电池接口使用三线 `BAT+/BAT-/10k NTC`；
- 新增区器件按手工热台及返修留较宽间距；开关电源的电感、电容仍必须贴近 IC，
  不能为了返修把高 di/dt 回路拉长；
- 新增下侧安装孔候选避开 TF 卡和 WROOM 天线区域。

## 5. 按键合同

至少保留：

- 1 个电源键；
- 2 个用户键，最终外壳位置待定；
- WROOM 的 BOOT/RESET 可使用独立维修键或测试焊盘；最终形式在原理图冻结，
  不得用 RESET 冒充第二个用户键。

## 6. 当前图纸边界

R3 权威原理图已经生成并晋升：

- `hardware/mf1750_wroom_b3_power_tf/mf1750_wroom_b3_power_tf.kicad_sch`
- SHA-256：`158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0`
- KiCad ERC：0 错误、0 警告；结构/电气契约 246/246；解析规模为 176 个器件、
  175 个网络、552 个引脚节点；B2 原理图继承检查
  655/655。

TPS63070 已按 Rev.B 数据手册 §11.1 固化：`R29=10 kΩ`，仍为
`VSYS_RAW -> DCDC_PS_SYNC`；`C46=10 µF/0603` 接 `VSYS_RAW-GND`，`C47=10
µF/0603` 接 `SYS_3V3-GND`，两者是待紧贴 U4 对应引脚的本地高频电容；
`C31-C37` 保持 bulk。

当前另有独立 PCB 同步候选：

- `hardware/mf1750_wroom_b3_power_tf/staging/mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb`
- SHA-256：`c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb`
- 自包含 KiCad 原生 schematic-parity：0；项目 verifier 13/13 PASS；
  U1 删除负向 canary 精确检出 1 项。

功能分组布局候选为：

- `hardware/mf1750_wroom_b3_power_tf/staging/mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb`
- SHA-256：`349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf`
- `hardware/mf1750_wroom_b3_power_tf/staging/r4_functional_placement_report.json`
- `hardware/mf1750_wroom_b3_power_tf/staging/r4_preview/`

R4 已纳入 C46/C47、H3/H4 与可返修间距修订；B2 保护铜/器件零漂移、native
parity 0、无 courtyard/clearance/short/items-not-allowed 新问题，并已两次重建得到
相同 PCB SHA。它仍是未布线 `HOLD` 候选（174 项 placement-stage DRC、205 个未连接）。
正式 `mf1750_wroom_b3_power_tf.kicad_pcb` 仍保持旧 R2 候选，尚未被 staging 覆盖。

## 7. 下一道门

1. 完成功能分组布局，优先关闭 TPS63070、BQ24074、TPS22950、U6、USB/TF ESD
   的短回路和可返修间距；
2. 冻结电池 MPN/容量/NTC，并在下单前复核所有 LCSC/JLC 料号库存与装配属性；
3. 完成 EPD 电源入口、U6 面板锚点、USB 差分、TF SPI 和电源树布线；
4. 对 STM6600“按住到 MCU 建立 PS_HOLD”的实际启动体验做首板门控；如产品要求
   瞬时短按锁存，则在投板前更换为经采购验证的固定启动窗口方案；
5. 完成严格 DRC、零未连接、原理图 parity、天线/机械/热审查后，才能进入嘉立创
   制造交付。
