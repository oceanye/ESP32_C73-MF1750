# MF1750 WROOM B3 R3 布线约束与关键网络独立审计

日期：2026-08-24  
模式：`REVIEW_ONLY`  
目标修订：`B3-WROOM-POWER-TF-R3-SCHEMATIC`  
结论：`CONSTRAINT AUDIT COMPLETE / ROUTING AND MANUFACTURING HOLD`

## 1. 结论先行

本审计已经把 R3 的电源树、关键热环路、USB、TF SPI、EPD 七线及供电、反馈、
ADC 和开关节点转成可执行的布线次序与复核门。当前资料足以继续功能分组布局、
B2 保护核接口重连和非阻抗低速布线，但还不能宣称“已完成布线约束”或进入制造：

1. `SYS_3V3` 的整机峰值没有闭环。ESP32-S3 模组要求外部 3.3 V 电源至少能提供
   0.5 A；EPD 分支 `RILIM=1.50 kΩ` 只给出约 0.764 A 的**典型**限流设定；TF 卡
   写入峰值、电池放电能力和三路同时工作的热裕量均未冻结。
2. USB 必须是 `90 Ω ±10%` 差分，但 R3 的最终嘉立创层叠尚未批准，因此线宽、
   线距和允许 skew 均为 `HOLD`。项目当前默认 `0.20/0.25 mm` 不能被当作控阻结果。
3. TPS63070 原理图缺口已按 Rev.B §11.1 关闭：`R29=10 kΩ`；新增
   `C46=10 µF/0603`（VIN-GND）与 `C47=10 µF/0603`（VOUT-GND），原
   C31-C37 继续作为 bulk。尚未关闭的是 PCB 紧贴布局、热环路与重新同步后的
   parity/DRC，因此仍是版图 `HOLD`，不是原理图 `HOLD`。
4. 本地面板 A1 规格书第 11 页将 `Iupdate` 明确写为 `TBD`；不能用已有照片刷新
   成功、器件额定 2 A、1 A 台式电源限流或一次“可能 0.4 A”的观察替代正式峰值。
5. B2 的显示驱动区继续按保护子集冻结。其既有宽度和 0.6/0.3 mm 过孔是继承
   几何，不是对未知电流、高压或新层叠的重新认证。

机器可读的**修正前审计快照**：
`hardware/mf1750_wroom_b3_power_tf/staging/r3_routing_constraint_audit.json`。其中旧原理图
SHA、R29/C46/C47 缺口和旧 staging PCB 统计只保留为发现问题时的证据；现行原理图
放行证据改由 `tps63070_rev_b_r3_contract.json`、`tps63070_rev_b_r3_b2_parity.json`
和 `tps63070_rev_b_r3_promotion_manifest.json` 承载。

## 2. 权威边界

| 对象 | 路径 / SHA-256 | 用途 |
|---|---|---|
| R3 权威项目 | `hardware/mf1750_wroom_b3_power_tf/mf1750_wroom_b3_power_tf.kicad_pro` / `2FA48D53...FE6C` | 项目规则来源 |
| R3 权威原理图 | `hardware/mf1750_wroom_b3_power_tf/mf1750_wroom_b3_power_tf.kicad_sch` / `158E54C1...BF0` | 电气连接唯一权威；ERC 0，合同 246/246，B2 655/655 |
| 正式 PCB | `hardware/mf1750_wroom_b3_power_tf/mf1750_wroom_b3_power_tf.kicad_pcb` / `6DA0E247...E3A7` | 旧 R2 摆放，不是 R3 路由权威 |
| R3 staging PCB | `hardware/mf1750_wroom_b3_power_tf/staging/mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb` / `C43446B3...22FB` | 现行 176 器件同步；native parity 0；13/13 PASS；144 DRC/205 未连接，HOLD |
| R4 功能布局 PCB | `hardware/mf1750_wroom_b3_power_tf/staging/mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb` / `349EF014...2FBF` | C46/C47/U4 岛和板边可返修布局；native parity 0；174 DRC/205 未连接，HOLD |
| 冻结 B2 PCB | `hardware/mf1750_devkitc_b2_pcba_margin/mf1750_devkitc_b2_pcba_margin.kicad_pcb` / `462E1272...4238` | 已真屏验证显示驱动前件 |

KiCad：`10.0.3`。检查时未发现项目锁文件。本审计未修改任何 KiCad 源，也未访问
继电器、J2、USB/COM、ESP32 或真屏。

当前 self-contained R3 同步报告为 144 项 DRC、205 个未连接、native
schematic-parity=0；U1 删除负向 canary 报告 1 项并明确命中 U1。R4 功能布局在
固定项目路径报告 174 项 DRC、205 个未连接；增加项来自当前丝印/库/孔径/热焊盘
检查，不含 clearance、short、courtyard overlap 或 items-not-allowed。两者都不是
已布线或可生产状态。

## 3. 层与返回路径

R3 继续采用四层：

| 层 | 布线职责 | 不允许事项 |
|---|---|---|
| L1 `F.Cu` | 元件、U4/U2/U5 热环路、USB、TF、EPD 短线 | 不跨天线禁布，不让敏感线穿过开关节点 |
| L2 `In1.Cu` | 连续 GND 参考 | 除 WROOM 天线明确缺口外不切割、不走信号 |
| L3 `In2.Cu` | 电源分配、极少量低速线 | 不在 USB/TF/EPD 时钟下方制造参考断口 |
| L4 `B.Cu` | 少量非关键线、必要测试访问 | 尽量不放元件；天线区无铜、无过孔 |

B2 曾使用 `JLC04161H-7628`、1.6 mm、L1/L4 1 oz、L2/L3 0.5 oz。它可以作为
估算起点，但 B3 订单层叠尚未批准，因此不能直接继承其控阻或载流结论。

ESP32-S3 官方指南还给出两个可以直接执行的量化要求：主 3.3 V 供电线不小于
25 mil（0.635 mm）；若主电源换层，至少使用两个过孔。该要求用于 U1 供电，
不等于已经完成整条 `SYS_3V3` 的载流/温升计算。

## 4. 电源树与最大“已知”电流

| 路径 | 最大已知量 | 布线决策 | 尚未证明 |
|---|---|---|---|
| `J5 -> F1 -> USB_5V_FUSED -> U2 IN` | `EN1=1, EN2=0` 固定 USB500，即 500 mA 输入限制 | 顶层最短宽铜；D5、C24、C25、U2 IN 回流成入口小环路 | F1 的 750 mA 标签不是硬限流；线宽需最终铜厚/温升计算 |
| `J6 BAT_POS <-> U2 BAT` | `R21=1.78 kΩ` 对应约 500 mA 快充 | 宽铜或铺铜，C26 贴 U2 BAT/VSS；NTC 单独安静走线 | 电池包/保护板/插头的持续与峰值放电能力 |
| `U2 OUT -> VSYS_RAW -> U4 VIN` | 无批准上限；PowerPath 可由电池补足 USB 不足的系统峰值 | C27 贴 U2 OUT；C46/0603 紧贴 U4 VIN-GND，C31-C33 为 bulk；避免单过孔/细颈 | USB+电池补充的最坏组合电流、BQ 热耗散 |
| `U4 -> SYS_3V3` | TPS63070 标题是 3.6 A switch current；特定条件下列出 2 A 输出，两者都不是整机负载预算 | U4、L3、输入/输出电容形成最小回路，主干宽铜/内层电源 | ESP32+TF+EPD 同时峰值、效率、最低电池电压和温升 |
| `SYS_3V3 -> U1` | 外部电源能力至少 0.5 A；官方 Wi-Fi TX 表中最高列值 355 mA | 到 U1 主馈线 ≥0.635 mm；C41/C42 贴供电脚；换层至少两过孔 | 整机条件下模组+PSRAM+外设实际峰值 |
| `SYS_3V3 -> J4` | `HOLD` | C43/C44 贴 J4，独立短分支，不与 U1/U5 共用细颈 | 任意用户 TF 卡写入峰值和最终 SPI 时钟 |
| `SYS_3V3 -> U5 -> EPD_SW_3V3` | TPS22950 公式给 `R33=1.50 kΩ` 约 0.764 A 典型限流 | U5/C39/C40/R33 紧凑，VIN/VOUT/GND 宽，OUT 直达 TP1 | 限流容差、故障值、真实面板峰值 |
| `TP1 -> R4/R8 -> EPD_3V3/V_B` | 面板 A1 规格的 `Iupdate=TBD` | 保留 B2：EPD_3V3 0.4/0.6 mm、V_B 0.5/0.8 mm、过孔 0.6/0.3 mm | 新板载流、面板峰值和高压轨绝对工作值 |

注意：不能把 ESP32 的 0.5 A 电源能力要求与 EPD 的 0.764 A 典型限流简单相加，
再宣称系统“最大 1.264 A”。前者是供电能力下限，后者是一个器件的典型设置，
二者都不是相同统计条件下的真实负载上限。

## 5. 关键热环路

### 5.1 TPS63070

优先级最高，必须先完成布局再走其他线：

```text
输入环路：C46 -> U4 VIN/PGND -> 本地 GND -> C46；C31-C33 为 bulk
功率级：  U4 L1 -> L3 -> U4 L2
输出环路：U4 VOUT/PGND -> C47 -> U4；C34-C37 为 bulk
反馈：    输出电容后端 -> R31 -> DCDC_FB/U4 -> R32 -> quiet GND
```

- `DCDC_L1/DCDC_L2` 只在顶层，铜面积只满足器件/电感焊盘连接，禁止过孔、测试点
  和长支线；
- FB、BAT_ADC、USB、TF_SCLK 不得从电感下方或两个 switch node 旁穿过；
- 功率地与控制地按 TI 建议各自短回路，在 U4 接地附近汇合，不切割 L2；
- **原理图已关闭**：C46/C47 均为 10 µF、0603，并分别接 VIN-GND/VOUT-GND；
  R29 已改为 10 kΩ。**PCB 仍阻断**：必须证明两颗电容尽量贴近 U4 对应电源与地
  引脚，且热环路、Kelvin FB 与回流不被手焊间距拉长。

### 5.2 BQ24074

```text
USB 输入：J5/F1 -> C24/C25 -> U2 IN -> U2 EPAD/VSS
电池：    U2 BAT <-> C26/J6 -> U2 EPAD/VSS
系统：    U2 OUT -> C27 -> VSYS_RAW/U4
```

U2 暴露焊盘既是主要地连接也是热路径。`BQ_ISET/BQ_ILIM/BQ_TMR/BAT_NTC` 的
小信号地不得共享 BAT/OUT 大电流的细长返回段。

### 5.3 TPS22950

`C39-U5-IN-GND`、`U5-OUT-C40-GND` 和 `R33-ILIM-GND` 各自必须最短；U5 OUT
优先直接进入 `TP1` 的 B2 保护铜。不能用一颗普通信号过孔作为 0.764 A 分支的
唯一瓶颈。

### 5.4 B2 高压/电荷泵

`SW_H/SW_C/NEG_PUMP_H/VPH/VPC/PREVGH/PREVGL` 继续保持 B2 原有走线、层、过孔
和器件相对几何。当前面板规格没有给出生成高压轨的合格绝对工作范围，因此：

- 不从 25 V 电容或 30 V MOSFET反推轨电压；
- 不新增探针支线或将高压铜改到新层；
- 不把 B2 DRC=0 或真屏成功解释为完整的高压间距/寿命认证。

## 6. USB D+/D-

拓扑固定为：

```text
J5 -> U8 USBLC6-2SC6 -> R19/R20 22R -> U1 GPIO19/GPIO20
```

执行约束：

- U8 靠 J5，U8 地到 L2 以最短低电感路径泄放；
- R19/R20 靠 U1，不靠连接器；
- 顶层平行、等长、全程参考连续 L2 GND，两侧可包地；
- 避免过孔；必须换层时两根信号成对换层，并在该处增加一对地回流过孔；
- TP26/TP27 只能内联或保持严格对称、近零支线，不能形成两个长 stub；
- 目标阻抗 `90 Ω ±10%`；实际线宽、间距和允许 skew 等最终 B3 层叠后场求解，
  目前全部为 `HOLD`。

## 7. TF SPI

当前是 SPI，不是四位 SDIO；不能直接把官方 SDIO 的 50 Ω、±50 mil 和 2000 mil
规则冒充已经批准的 SPI 约束。建议仍采用更稳健的物理组织：

- `R45 SCLK`、`R46 MOSI`、`R48 CS` 靠 U1，因为这三根的源端是 MCU；
- `R47 MISO` 靠 J4，因为 MISO 源端是 TF 卡；
- U9/U10/U11 靠 J4，卡侧上拉 R39-R43 靠 J4；
- F.Cu 短直走线、连续 L2 GND，尽量不换层；SCLK 可包地；
- 不穿 WROOM 天线区、不邻近 TPS63070 的 DCDC_L1/DCDC_L2；
- 当前普通线的项目下限为 0.20 mm。是否做单端控阻、具体阻抗、最大长度和
  匹配误差，等待最终 SPI 时钟和层叠后再冻结；
- `TF_CD_N` 极性继续等实物首件确认。

## 8. EPD 七线与受控供电

U6 必须保留一颗 `SN74CB3Q3245PWR` 的双向结构：

| MCU 侧 | 面板侧 | 方向注意事项 |
|---|---|---|
| `MCU_RST_N` | `RST_N` | MCU -> panel |
| `MCU_DC` | `DC` | MCU -> panel |
| `MCU_CSB` | `CSB` | MCU -> panel |
| `MCU_CS2` | `CS2` | MCU -> panel |
| `MCU_SCL` | `SCL` | MCU -> panel |
| `MCU_SI0` | `SI0` | **双向**，支持 SDA/register readback |
| `MCU_BUSY_N` | `BUSY_N` | panel -> MCU |

约束：

- U6/C45/Q3/R36/R63 紧贴布置；面板安全偏置 R54-R59 在 U6 面板侧；
- U1-U6 是主路径，J2 DNP 只能成为很短的调试 tee，不能把七线变成长支线树；
- 新线按 B2 数字线 0.20 mm 基线，F.Cu/B.Cu 参考连续 L2 GND；
- 面板侧只接入迁移审计已列出的九个 B2 锚点，不扩展进入其他保护铜；
- 避开 TPS63070 岛、USB pair、天线区与 B2 高压 switch node；
- 上电顺序保持“GPIO38 低 -> U5 ON -> 等待 EPD rail -> GPIO38 高”，关机反向。

供电 `U5 -> TP1` 的数值线宽不能只照抄 0.20 mm 默认规则；在没有最终电流/铜厚
计算前，应使用宽铜/铺铜和多个并联过孔，具体宽度与孔数保持 `HOLD`。

## 9. ADC、反馈和小信号节点

| 网络 | 约束 |
|---|---|
| `DCDC_FB` | R31/R32 贴 U4，从本地输出电容后端 Kelvin 取样；R32 回 quiet GND；不邻近/平行 DCDC_L1/L2 |
| `DCDC_VAUX` | C38 贴 U4 VAUX/GND，不形成远端支路 |
| `DCDC_PS_SYNC` | R29=10 kΩ，从 VSYS_RAW(VIN) 串到 PS/SYNC；原理图合同已关闭，走线保持短且避开 switch node |
| `BQ_ISET/BQ_ILIM/BQ_TMR` | 电阻贴 U2，地回 U2 小信号/EPAD 汇合点，不共享大电流细颈 |
| `BAT_NTC` | 离 U4/L3、USB 与 TF 时钟；J6 的线序、NTC 曲线仍 HOLD |
| `BAT_ADC` | R49 继续 DNP；R50/C49 和 ADC 节点贴 U1，装 R49 前完成关机漏电/反灌/标定 |
| `EPD_ILIM` | R33 贴 U5，最小接地环，不共享面板负载电流返回 |
| `STM_VREF/STM_CSRD` | C29/C30 贴 U3，以安静地返回，避开 U4 switch node |

## 10. 线宽、过孔与间距的可执行边界

| 类别 | 现在可用 | 必须保持 HOLD |
|---|---|---|
| B2 冻结核 | 原样：数字 0.20 mm；EPD_3V3 0.4/0.6；V_B 0.5/0.8；普通过孔 0.6/0.3 mm | 不据此宣称新电流或高压认证 |
| 新低速线 | 项目最小 0.20 mm、普通间距 0.20 mm、普通过孔 0.6/0.3 mm | 机械返修允许时可加宽，但不把偏好写成额定值 |
| U1 3.3 V | 主馈线 ≥0.635 mm；换层至少两过孔 | 整机 SYS_3V3 主干还需热/电流预算 |
| USB | 90 Ω ±10%、同层、少过孔、连续 L2 | 线宽/线距/skew 等最终层叠场求解 |
| TF SPI | 0.20 mm 起点，短直、少过孔 | 阻抗、最大长度和 skew 等最终时钟/层叠 |
| USB/BAT/VSYS/SYS/EPD 电源 | 优先铺铜、只在焊盘处短暂 neck-down | 数值宽度、并联过孔数量、温升 |
| U4 switch node | 顶层、无过孔、焊盘定义的最小回路 | 不给无依据的固定宽度/间距 |
| 铜到板边 | 当前项目规则 0.50 mm | 连接器特殊盘、拼板/铣边能力仍需制造复核 |
| 高压 | 只保留 B2 原样 | 电压、间距、爬电和寿命均缺权威上限 |

WROOM pad 41 的 0.20 mm 热孔与项目 0.30 mm 最小钻孔冲突。必须由最终嘉立创
工艺、焊盘/钢网策略决定，不得通过 DRC 排除直接放行。

## 11. 推荐布线顺序

1. 先冻结板边连接器、WROOM 天线禁布和功能布局；未通过则不开始走线。
2. 锁住 B2 保护铜及 11 条明示接口豁免，任何其他漂移立即失败。
3. 解决 U4 两颗本地高频小电容，再走 TPS63070 输入、switch、输出和反馈。
4. 走 BQ24074 的 USB/BAT/OUT PowerPath 与暴露焊盘热/地结构。
5. 走 TPS22950 的 `SYS_3V3 -> U5 -> TP1`。
6. 最终层叠确认后场求解并走 USB D+/D-。
7. 走 U6/Q3 与七根 EPD 线到冻结锚点。
8. 走 TF SPI、ESD、源端串阻、卡侧上拉。
9. 走按键、状态、JTAG/UART、ADC 选件和测试点。
10. 重铺 GND/电源区，逐层看返回路径、孤岛、热焊盘、细颈、天线缺口和板边。

## 12. PCB review gates

| Gate | 通过条件 | 当前 |
|---|---|---|
| G1 源保护 | B2 SHA/保护子集/75 过孔/11 豁免检查通过，正式 PCB 未被静默覆盖 | 本审计 `PASS` |
| G2 布局/机械 | U2/U4/U5 短环路、USB/TF/J6/按键可达、WROOM 15 mm 三维净空 | `HOLD` |
| G3 功率预算 | 电池、TF、同步负载、效率、温升、铜宽/过孔计算与实测齐全 | `HOLD` |
| G4 U4 实现 | R29=10 kΩ、C46/C47=10 µF/0603 的原理图合同已闭环；仍需 PCB 紧贴、热环路与 DRC/视觉证明 | R5 局部路由、连通与视觉审计 `PASS`；整机热/电流仍 `HOLD` |
| G5 层叠/USB | B3 层叠批准，90 Ω ±10% W/G 入规则并后验复核 | `HOLD` |
| G6 路由/返回 | 热环路最小、L2 连续、换层回流、敏感线隔离逐项通过 | U4、BQ/PowerPath、EPD panel-side 局部范围 `PASS`；其余网络 `HOLD` |
| G7 自动检查 | ERC、DRC、未连接、parity、项目 verifier 全部 0/PASS，无未记载排除 | parity 0、verifier 13/13、fatal DRC 0；仍有 37 DRC / 141 unconnected，故整板 `HOLD` |
| G8 视觉/机械 | 顶底 3D、四铜层、装配/极性/插卡/线缆/返修复核 | `NOT RUN` |
| G9 首件 | 限流上电、USB、电池、TF 写入、Wi-Fi、EPD 峰值/故障/温度和 RF 距离 | 外部 `HOLD` |

## 13. 主要 HOLD 清单

- 电池 MPN、容量、放电、保护板、NTC、J6 配对件与线序；
- TF 卡最坏写入峰值及最终 SPI 时钟；
- `SYS_3V3` 同时负载、TPS63070 效率/温升、功率铜宽和过孔数量；
- TPS63070 C46/C47 在 PCB 上相对 VIN/VOUT/GND 的实际紧贴位置、最小热环路与
  重新同步后的 parity/DRC；R29=10 kΩ 与两颗 10 µF/0603 的原理图值已关闭；
- B3 最终层叠、USB 90 Ω 的 W/G/skew；
- TPS22950 限流容差、面板 `Iupdate`、故障和峰值；
- B2 生成高压的绝对值和对应间距；
- WROOM EPAD 0.20 mm 钻孔工艺；
- 天线/外壳/金属/线束、TF 插拔、按钮和连接器机械；
- STM6600 CS25 必须按住到 MCU 建立 `PS_HOLD` 的交互首件验证。

## 14. 一手资料

- 本地面板规格：`参考资料/MF-1750..1).pdf`，A1，第 11 页；
- Espressif ESP32-S3-WROOM-1/1U datasheet：
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>；
- Espressif ESP32-S3 PCB layout guideline：
  <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html>；
- TI BQ24074：<https://www.ti.com/lit/ds/symlink/bq24074.pdf>；
- TI TPS63070：<https://www.ti.com/lit/ds/symlink/tps63070.pdf>；
- TI TPS22950-Q1：<https://www.ti.com/lit/ds/symlink/tps22950-q1.pdf>；
- 本地冻结台账：`docs/MF1750_WROOM_B3_R3_CONSTRAINT_LEDGER_2026-08-24.md`；
- 本地迁移审计：`docs/MF1750_WROOM_B3_R3_PLACEMENT_MIGRATION_AUDIT_2026-08-24.md`。

## 15. R5 关键路由链实测证据

2026-08-24 已在 staging-only 模式完成固定顺序
`R4 -> TPS63070 -> BQ24074/PowerPath -> EPD boundary`。正式 PCB、R3、R4、
原理图与工程文件均由哈希门保护且未改动；没有访问继电器、J2、ESP32、COM 或屏幕。

| 工件 | SHA-256 | 结果 |
|---|---|---|
| U4 candidate | `BC4B13F8764965B0FBD3B9F65A2183DC9B8C46E9025229006E6C1BB6CC28A8E4` | parity 0，局部连通 PASS |
| BQ candidate | `4B0FBC2BA0EA5E6C3F3569648823C5A1E06A238291D9A024D82D07535E279C89` | 932/932 copper UUID unique，VSYS chain PASS |
| EPD/final candidate | `3AA2E70D96C54EED4F0653ECB46B9C721F9ACEC42D88AA0F3B9654E0D08C73EC` | 1091/1091 unique；7 nets / 9 anchors PASS |
| chain audit | `56E802A9A62457D9489395A2189DFDD1964A463047D05E322BA11186B7BB9B8E` | complete run PASS |
| final DRC JSON | `8FB608590D17F21395BF60675B198FA0D50C3847C0403F15DAFE9471146C2C4A` | fatal set 0；37 open；141 unconnected |
| board verifier | `13504138460E2950AF0D1E440382B6EE098EE5459FDAEF9CB870322855CC802A` | 13/13 PASS |

EPD 七线均从 J2 右端绕行；独立复核确认新增铜没有进入 WROOM 全层天线禁布区，
最紧的 CS2 铜边到 J2 pad 22 铜边仍为 0.56 mm，而当前规则要求 0.20 mm。
曾发现 U4/BQ 使用相同确定性 UUID seed，造成 74 对重复 UUID；BQ seed 已独立化，
分支与链尾均加入全铜 UUID 唯一性 fail-closed 门，旧重复候选负向 canary 会被拒绝。

本节只把三个关键局部范围推进为可追溯的 `ROUTED_CANDIDATE`。141 个未连接、
USB 控阻、TF/MCU/system trunks、热/电流、机械与制造问题仍阻止整板放行。

---

最终判定：本审计可作为 R3 下一版功能布局和关键网络走线的输入，但不能解除
功率、U4 高频去耦、USB 控阻、高压与机械 `HOLD`。只有第 12 节的 G2-G8 全部
通过，才可把 PCB 从 `PLACED_CANDIDATE` 推进到 `ROUTED_CANDIDATE`；制造交付
还需要独立的嘉立创 handoff 审计。
