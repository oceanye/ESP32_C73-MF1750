# MF1750 DevKitC B3 器件与接口冻结记录

> **已被取代：** 用户于 2026-08-24 授权改用直接贴装的
> `ESP32-S3-WROOM-1-N16R8` 模块。本文保留为 DevKitC 路线的决策历史，禁止再按
> 本文的 5 V 升压/DevKitC 插座电源树实施。当前权威输入改为
> `MF1750_WROOM_B3_COMPONENT_FREEZE_2026-08-24.md`。

日期：2026-08-24  
状态：`B3-COMPONENT-FREEZE-R0`  
发布等级：`SCHEMATIC_INPUT — NOT PCBA RELEASE`

## 1. 本次冻结结论

B3 作为现有 B2 的非破坏性后继版本建立；不得覆盖或改名替换
`hardware/mf1750_devkitc_b2_pcba_margin/`。B2 的原理图、PCB、验证报告和
制造候选证据继续作为已冻结前身。

本次冻结以下输入：

- 延续 B2 的四层板结构；原 B2 已经真屏测试过的驱动区布局、器件相对位置和
  关键走线作为保留区，不为缩小尺寸而重新压缩；
- 板尺寸不是首要约束，新增区按可手工热台焊接和返修留出较宽器件间距；
- 单节 3.7 V 锂离子/锂聚合物电池；
- 独立充电 USB-C 和 DevKitC 调试 USB；
- 真正的 PowerPath 充电管理；
- 按键开机、通知 ESP32 后正常关机，并保留长按强制关机；
- DevKitC 由受控 5.0 V 标称支路供电，不从外部直接并入 DevKitC 的 3V3；
- TF 与电子纸使用独立 3.3 V buck-boost 电源域；
- DevKitC 与可断电的 TF/电子纸电源域之间加入带 `Ioff` 的信号隔离，避免调试
  USB 单独供电时经 GPIO 反向供电；
- 电子纸 3.3 V 支路具有 GPIO 开关、首板约 0.76 A 典型可调限流、短路保护、热关断、
  反向电流阻断和关断放电；
- TF 卡槽固定在 **PCB 下边缘**，卡口朝外；使用者从外壳下侧把卡向板内插入；
- 电源键和两个用户键统一采用同一种侧按键封装；两个用户键最终坐标暂不冻结。

这不是嘉立创投产批准。B3 仍需完成独立 KiCad 原理图、封装核图、布局布线、
ERC、DRC、网络一致性、BOM/CPL 匹配和嘉立创订单页复核。

## 2. 冻结电源树

```text
CHARGE_USB_C_5V
    │
    ├─ CC1/CC2 各 5.1 kΩ Rd、保险/限流、VBUS TVS
    │
    └─ BQ24074RGTR PowerPath ─────────────── VSYS_RAW
                 │                              │
                 └─ BAT ── 1S 3.7 V LiPo        └─ STM6600 电源键控制器
                            + 10 kΩ NTC                │ EN_SYS
                                                      ├─ TPS61023 → 5.0 V
                                                      │             │
                                                      │          LM66100
                                                      │             │
                                                      │      DevKitC EXT_5V
                                                      │
                                                      └─ TPS63070 → AUX_3V3
                                                                    ├─ TF 卡
                                                                    └─ TPS22950
                                                                          │
                                                                      EPD_3V3/J2
```

DevKitC 自身的 USB 只承担调试/刷写及其自身供电；充电 USB-C 只承担 5 V
充电输入。两者共地，但 VBUS 不直接相连。电池侧 5.0 V 经 LM66100 接入
DevKitC `EXT_5V`；DevKitC 板载 USB 路径中的二极管与 B3 的 LM66100 共同阻止
PC USB 和升压支路相互倒灌。调试 USB 插着时，电源键不能保证 DevKitC 本体
完全断电，这是明确的调试模式行为。

## 3. 主器件冻结表

下表中的库存只是 2026-08-24 的采购可行性证据；正式上传 BOM 时必须再次检查
嘉立创贴装状态、库存、基础/扩展料属性以及是否需要预购。

| 功能 | 冻结料号 | LCSC/JLC 编号 | 封装 | 冻结理由 |
|---|---|---:|---|---|
| 1S 充电 + PowerPath | TI `BQ24074RGTR` | `C54313` | QFN-16-EP 3×3 | 4.2 V 单节、PowerPath、NTC、输入/充电电流可配置；嘉立创支持 SMT |
| 智能电源键 | ST `STM6600CS25DM6F` | `C443976` | TDFN-12 2×3 | 按键去抖、INT、PS_HOLD、正常关机和长按强制关机；优于直接瞬断 TF 写卡 |
| DevKitC 5.0 V 升压 | TI `TPS61023DRLR` | `C919459` | SOT-563 | 从单节电池/PowerPath 输出生成 DevKitC 5 V 标称支路 |
| 5 V 防倒灌 | TI `LM66100DCKR` | `C2869734` | SC70-6 | 低压降理想二极管，隔离 DevKitC USB 与电池升压支路 |
| TF/EPD 3.3 V buck-boost | TI `TPS63070RNMR` | `C109322` | VQFN-15 2.5×3 | 覆盖单节电池全电压范围，给 TF 和面板提供独立 3.3 V 电源域 |
| 面板限流负载开关 | TI `TPS22950CQDDCRQ1` | `C17349276` | SOT-23-6 | 可调限流、短路/热保护、反向阻断、故障输出及关断放电；首板降额 |
| 断电信号隔离（3 片） | TI `SN74LVC125APWR` | `C7813` | TSSOP-14 | 每片四路固定方向三态缓冲，支持 partial-power-down/`Ioff`；两片隔离 EPD 七线，一片隔离 TF SPI 四线 |
| microSD/TF 卡槽 | Molex `1040310811` | `C585350` | 正装 SMT | 1.42 mm、前进卡、push-pull、卡检测、10,000 次插拔；下侧向外 |
| 充电 USB-C | Korean Hroparts `TYPE-C-31-M-12` | `C165948` | 16-pin SMT | 大库存 5 V Type-C 母座；本项目只接 VBUS/GND/CC1/CC2 |
| 电源键 + USER1 + USER2 | ALPS Alpine `SKSCLDE010` | `C115362` | 侧按 SMD | 三键统一封装，约 1.6 N，100,000 次寿命 |

`C443976` 与 `STM6600CS25DM6F` 的映射已通过 LCSC/JLC 官方料库接口独立核验；
它属于扩展料。接口在 2026-08-22 更新的库存快照显示为千片级，但这仍不是对
下单时库存的保证。

主器件证据：

- [BQ24074 官方资料](https://www.ti.com/product/BQ24074)；
  [JLCPCB C54313](https://jlcpcb.com/partdetail/TexasInstruments-BQ24074RGTR/C54313)
- [STM6600 官方资料](https://www.st.com/en/reset-and-supervisor-ics/stm6600.html)
- [TPS61023 官方资料](https://www.ti.com/product/TPS61023)；
  [LCSC C919459](https://www.lcsc.com/product-detail/dc-dc%20converters_texas%20instruments_tps61023drlr_C919459.html)
- [TPS63070 官方资料](https://www.ti.com/product/TPS63070)；
  [JLCPCB C109322](https://jlcpcb.com/partdetail/TexasInstruments-TPS63070RNMR/C109322)
- [LM66100 官方资料](https://www.ti.com/product/LM66100)；
  [JLCPCB C2869734](https://jlcpcb.com/partdetail/TexasInstruments-LM66100DCKR/C2869734)
- [TPS22950-Q1 官方数据手册](https://www.ti.com/lit/ds/symlink/tps22950-q1.pdf)；
  [LCSC C17349276](https://www.lcsc.com/product-detail/Power-Distribution-Switches_Texas-Instruments-TPS22950CQDDCRQ1_C17349276.html)
- [SN74LVC125A 官方数据手册](https://www.ti.com/lit/ds/symlink/sn74lvc125a.pdf)；
  [JLCPCB C7813](https://jlcpcb.com/partdetail/TexasInstruments-SN74LVC125APWR/C7813)
- [Molex 1040310811](https://www.molex.com/en-us/products/part-detail/1040310811)；
  [LCSC C585350](https://www.lcsc.com/product-detail/SD-Card-Connectors_MOLEX_C585350.html)
- [ALPS SKSCLDE010](https://tech.alpsalpine.com/e/products/detail/SKSCLDE010/)；
  [LCSC C115362](https://www.lcsc.com/product-detail/C115362.html)
- [LCSC C165948 USB-C](https://www.lcsc.com/product-detail/C165948.html)

## 4. 首板电气设定

### 4.1 充电

- `BQ24074` 默认固定为 USB500：`EN1=1`、`EN2=0`，输入上限 500 mA；
- 快充电流首板默认 500 mA：`RISET=1.78 kΩ`；
- 原理图保留电阻/焊桥选项，只有在电池额定充电电流、USB-C 电源能力和板上
  热测试冻结后，才允许改为 800 mA 或更高；
- 生产版本要求电池包提供 10 kΩ NTC。不得把固定电阻伪装成已验证的电池温度
  保护；
- `CHG`、`PGOOD` 先接指示灯/测试点，不占用紧张的 ESP32 GPIO。

500 mA 输入可能在 Wi-Fi、TF 和整屏刷新同时工作时暂停或降低充电电流，电池可
通过 PowerPath 补充瞬态负载。这是首板的安全取向，不是最终充电速度承诺。

### 4.2 电源键关机合同

- 同一个物理电源键必须按 ST 参考电路同时实现 `PB` 正常按键路径与 `SR`
  长按 Smart Reset 路径，不允许把 `SR` 留空后宣称具备强制关机；
- `INT` 连接 `PWR_INT/GPIO21`，提示 ESP32 停止任务、同步并卸载 TF；
- `PS_HOLD` 连接 `PWR_HOLD/GPIO2`；ESP32 完成清理后释放保持信号；
- `EN_SYS` 同时控制 5.0 V 和 AUX_3V3 两个转换器；
- 长按关机只作为固件失效时的兜底，具体长按时间由 `CSRD` 和数据手册计算后
  在原理图评审冻结。

### 4.3 面板保护

- `TPS22950-Q1` 的主 `RILIM` 首板取 `1.50 kΩ`，典型限流约 0.76 A；
- 另放一个 `5.10 kΩ` 并联升级电阻位，首板 `DNP`；经实测确认余量后装入时，
  等效 `RILIM` 约 1.16 kΩ、典型限流约 1.0 A；
- 数据手册限流存在工艺、输入电压和温度离散；“典型 1.0 A”不能写成硬件绝对
  上限。首板必须记录实测限流拐点和全工作条件下的峰值；
- `EPD_PWR_EN` 默认由硬件下拉保持关闭；只有 ESP32 完成启动和状态检查后才打开；
- `FLT` 接测试点并分配给固件可读 GPIO/扩展输入的候选焊桥，最终由 GPIO
  预算复核决定；
- 首板必须实测启动浪涌、正常刷新峰值、限流响应、故障恢复和关断后的反灌；
- 不再使用固定过载点约 2.7 A、且厂家已列为非首选新设计器件的 AP22802。

### 4.4 断电域信号隔离

- 使用 3 片 `SN74LVC125APWR/C7813`：两片覆盖 EPD 的 MOSI、SCK、CS1、CS2、
  DC、RST、BUSY，一片覆盖 TF 的 SCK、MOSI、CS、MISO；
- 隔离器分别由其外设侧的 `EPD_3V3` 或 `AUX_3V3` 供电；外设断电时依靠器件
  的 partial-power-down/`Ioff` 保持高阻，不能只依赖固件把 ESP32 GPIO 拉低；
- 各通道按实际信号方向固定连接，未使用通道不得悬空；`BUSY`、`MISO` 的
  ESP32 侧设置确定的弱上拉/下拉，避免外设断电时输入漂浮；
- `/OE` 的上电/断电默认状态、电阻值以及 SPI 边沿完整性在原理图与首板测试中
  复核；隔离器靠近外设连接器布置；
- `LM66100` 的 `CE` 按 TI 数据手册连接到 `VOUT`，实现常开反向电流阻断；仅在
  冻结的 DevKitC 版本确认板载 USB 输入二极管方向后，才允许接入 `EXT_5V`。

## 5. GPIO 冻结

现有电子纸映射保持不变：

| 功能 | GPIO |
|---|---:|
| EPD BUSY | 4 |
| EPD RST | 5 |
| EPD DC | 6 |
| EPD CS1 | 7 |
| EPD CS2 | 10 |
| EPD MOSI | 11 |
| EPD SCK | 12 |

B3 新增映射：

| 功能 | GPIO | 说明 |
|---|---:|---|
| TF SCK | 15 | 独立 SPI，不改已验收的 EPD SPI 合同 |
| TF MOSI | 16 | 独立 SPI |
| TF MISO | 17 | 独立 SPI |
| TF CS | 18 | 独立 SPI |
| TF CARD_DETECT | 14 | 卡插入检测 |
| EPD_PWR_EN | 13 | TPS22950 ON；硬件默认下拉 |
| USER1 | 8 | 两脚按键到 GND，使用上拉 |
| USER2 | 9 | 两脚按键到 GND，使用上拉 |
| PWR_INT | 21 | STM6600 关机请求 |
| PWR_HOLD | 2 | ESP32 正常关机握手 |
| BAT_ADC | 1 | 电池分压采样；分压/RC/误差另行计算 |

避免 GPIO0/3/45/46 启动绑带脚、GPIO19/20 原生 USB 脚以及 N8R8 内存相关脚。
当前 B2 KiCad 中 `J2` 是 DevKitC socket；旧固件资料里的“历史 10-pin 主机
接口 J2”不是同一个连接器。B3 原理图将改用不重名的功能网络名，防止按旧编号
误接。

## 6. TF 下侧机械合同

`1040310811` 是顶层正装、前进卡的卡座。B3 的机械定义为：

- 卡座入口与 PCB 下方 Edge.Cuts 对齐；
- 卡从外壳下侧进入，运动方向由板外指向板内；
- 卡检测开关必须接入；
- 卡座、卡片伸出量、手指拔卡空间和外壳开口都进入机械图；
- 卡座下方及卡运动区域禁止高器件和螺钉；
- 在卡座附近增加板边支撑/安装孔候选，避免插拔力只由上侧两个安装孔承受。

B2 的 DevKitC 下排针位于约 `y=58.5 mm`，距现有下边仅约 2 mm，当前下边带
不能容纳深约 11 mm 的卡座。B3 采用“向下扩板、保持原电子纸电路不动”的
低风险路径，不重排已测试驱动区。精确扩展量由 Molex 官方封装、卡片包络、
2.5 mm 贴装边距目标和新增电源区的手工返修间距共同求解；尺寸优化优先级低于
布局清楚、热回路短和可返修性。

## 7. 仍然保持 HOLD 的输入

下列项目不阻止开始 B3 原理图，但在 PCB 生产发布前必须冻结：

- 电池包 MPN、容量、最大尺寸、保护板、3 线连接器和 10 kΩ NTC 曲线；
- 充电 USB-C、电源键、USER1、USER2 的最终外壳坐标；
- B3 最大长宽、下侧允许扩板量、外壳开口和总 Z 高度；
- 转换器电感、电容和热铜的最终嘉立创料号；
- USB/TF 的 ESD、输入保险/限流和电池连接器的最终料号；
- 充电 500 mA 是否升级、面板 0.99 A 限流是否需要按实测微调。

## 8. B3 下一道工作门

1. 建立全新的 `hardware/mf1750_devkitc_b3_power_tf/`，冻结 B2 三个源文件哈希；
2. 为上表主器件建立/核验 KiCad symbol、footprint、pin-1、EP pad、courtyard 和
   3D/官方尺寸证据；
3. 完成 B3 原理图和 GPIO/启动绑带/USB 倒灌审计；
4. 先做下侧 TF、充电口和按键机械布局，再做电源热布局、断电域隔离和其余布线；
5. 执行 ERC、严格 DRC、零未连接、原理图/PCB 网络一致性和电源/回流审计；
6. 生成 Gerber、钻孔、BOM、CPL、源文件 ZIP 和 SHA-256 manifest；
7. 在嘉立创订单页重新匹配所有 C 编号并完成方向预览后，才能升级为
   `ENGINEERING FIRST ARTICLE RELEASE CANDIDATE`。
