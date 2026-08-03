# 阶段一交接：MF-1750 Rev A1

交接日期：2026-07-13  
状态：已提交嘉立创加工，等待首板到货。  
下一阶段：验证 Rev A1 后，整合 ESP32-S3、USB-C 和单节锂电池电源。

## 1. 阶段结论

目标屏为 MF-1750 / M009F-T，7.5 英寸、1024×600、双 SPD1657 级联、
六色 4bpp。旧 DESPI-C73 能稳定控制左侧 512×600，但它的 50Pin 定义
与该屏不完全兼容：MF-1750 pin 4 是 `SL_CSB`，C73 对应位置为 `VDD`，
外部 8Pin 也没有第二片选。因此旧 C73 不再使用，屏幕 50Pin 排线改插
Rev A1 的 J1，ESP32 控制线直接接 Rev A1 的 J2。

Rev A1 是电子纸高压驱动/转接板，不含 ESP32、充电器或板载 3.3V 稳压，
需要外部稳定 3.3V。默认安装 R15，把 `CSB` 与 `SL_CSB` 相连，先验证
E2802 参考板使用的共片选级联方式；R16 默认不装。

## 2. 已下单制造冻结

只把下列三个带 `revA1_Q1FIX` 名称的文件视为已下单冻结版本：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| `Gerber_mf1750_revA1_Q1FIX.zip` | 84,183 | `64931DEC6C747119B3F4DFFBC625D600D28BE59D1BE35D3213807106C5153F18` |
| `BOM_mf1750_revA1_Q1FIX.csv` | 2,588 | `06CFE61DF14055D9EF3EA94F333C7E776E11984B8D0C519957DCD7439FB3BDF8` |
| `CPL_mf1750_revA1_Q1FIX.csv` | 1,625 | `EF9C46262F8689156FEFC4724699522D60560CCB20EC6ADFA33FC75B080F91ED` |

目录：`hardware/mf1750_production_v1/production/`

制造参数：80×75mm、2 层、1.6mm FR-4、1oz、最小线宽/间距
0.20/0.20mm、过孔 0.60/0.30mm、仅顶层 SMT。

不要重新使用修正前嘉立创订单缓存中的文件。若未来对 PCB 做 ECO，必须
使用新修订号和新文件名，不要覆盖 Rev A1 的制造冻结记录。

## 3. 下单前关键修正

最终审计在原始 Rev A 中发现并修复两项生产阻断问题：

1. Q1 SI1308EDL 按官方 SC-70 引脚修正为 `1=G、2=S、3=D`：
   pad1=`GDRH`、pad2=`RESEH`、pad3=`SW_H`。
2. D2 负压电荷泵修正为 `K=GND、A=NEG_PUMP_H`，CPL 旋转 180°。

Rev A1 极性冻结：D1/D2 阴极色带朝右，D3/D4 朝左；Q1 顶视一个脚在
上、两个在下、pin1 左下；Q2 两个脚在左、一个在右、pin1 左上；J1
pin1 在顶视左侧，排线从板顶边进入。

## 4. 最终检查证据

- KiCad 10 ERC：0 error、0 warning。
- DRC：0 violation、0 unconnected pad、0 footprint error。
- 原理图/PCB parity：0 error。
- 独立关键引脚断言：D1–D4、Q1、Q2 全部通过。
- BOM/CPL：各 46 个相同位号、全部 Top、LCSC 编号有效。
- R12、R13、R15 安装；R16 DNP。
- J2 手焊；TP1–TP10 和 H1/H2 不进入贴片。
- 制造 manifest：28 个文件大小和 SHA256 校验 0 失败。
- 固件 PlatformIO release build 成功，无编译/链接警告。

详细报告：`hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md`。

嘉立创对 C7–C12、C14、C15 提出的“焊盘窄/器件宽”提示已独立复核，
料号和 1210 封装正确，PCB land pattern 在厂家推荐范围内，不构成撤单或
更换器件理由。详见 `docs/REV_A1_1210_PAD_AUDIT.md`。这 8 颗在板上均为
竖放；若贴装预览把器件长轴显示成横向，则应要求旋转 90°。

## 5. 硬件接口

J2 从 pin1 到 pin10：

| J2 | 信号 | 当前 ESP32-S3 GPIO |
|---:|---|---:|
| 1 | 3V3 | 外部稳定 3.3V |
| 2 | GND | GND |
| 3 | SI0/MOSI | GPIO11 |
| 4 | SCL/SCK | GPIO12 |
| 5 | CSB | GPIO7 |
| 6 | DC | GPIO6 |
| 7 | RST_N | GPIO5 |
| 8 | BUSY_N | GPIO4 |
| 9 | 可选 CS2 | 默认不接；备选 GPIO10 |
| 10 | GND | GND |

J2 只能输入 3.3V，不能输入 5V。首板调试建议使用独立限流 3.3V 电源，
额定能力至少 1A，并与 ESP32 共地。

测试点：TP1=3V3、TP2=GND、TP3=VPH、TP4=PREVGH、TP5=PREVGL、
TP6=VPC、TP7=VDDIO、TP8=CSB、TP9=SL_CSB、TP10=BUSY_N。

## 6. 固件冻结状态

- PlatformIO + Arduino，环境 `esp32-s3-devkitc-1`。
- ESP32-S3 DevKitC-1 N8，无 PSRAM；LittleFS；串口 115200。
- 固件标识：`FULLRES_1024_SINGLE_CS_2026-06-10`。
- 1024×600、4bpp、整帧 307,200 字节。
- 四线 SPI、Mode 0、MSB first、1MHz；3-wire 9-bit 实测失败。
- `EPD_PIN_CS2=-1`，与 Rev A1 默认 R15 共片选一致。
- `EPD_ENABLE_TEST_PATTERN=0`，上电不自动刷新。
- AP：`ESP32-S3-EINK` / `12345678`，地址 `http://192.168.4.1/`。

关键源码：`platformio.ini`、`src/epd_config.h`、`src/epd_driver.cpp`、
`src/main.cpp`。

常用接口：`/api/version`、`/api/white`、`/api/black`、`/api/bars`、
`/api/bars-512x600`、`POST /api/frame`。

当前 build：RAM 45,120/327,680（13.8%），Flash 761,829/3,342,336
（22.8%）。无 PSRAM 时 307,200 字节缓冲可能分配失败，纯色/色条已有
流式回退；整帧 HTTP 上传仍需在阶段二改为真正的分块接收。

## 7. 首板到货验证顺序

1. 外观检查 J1、D1–D4、Q1/Q2，确认 R15/R12/R13 已装、R16 未装。
2. 不接屏，用万用表检查 3V3 对 GND 无短路、R15 导通、R16 开路。
3. 不接屏限流上电，只确认 3V3/VDDIO 和静态电流；无屏内 SPD1657 时
   不会产生正常高压。
4. 断电后插入屏幕 FPC，实物复核 pin1 和接触面；禁止带电插拔。
5. 保持 `EPD_PIN_CS2=-1`，先 `/api/white`、`/api/black`，再
   `/api/bars-512x600`，最后 `/api/bars`。
6. PON/DRF 期间测 TP3 VPH、TP4 PREVGH 为正高压，TP5 PREVGL、TP6
   VPC 为负电压；用示波器检查 SW_H、SW_C 和 BUSY。
7. 测 Q1、Q2、L1、L2、D1–D4 温升。Q1 是参考图指定 SI1308EDL，
   但其 2.5V Rds(on) 高于同页通用数值要求，必须实测温升。
8. 目标结果是完整 1024×600 六色色条及两半同步刷新。
9. 若仍只有半屏，先测 TP8/TP9，确认经 R15 得到相同 CS 波形。
10. 只有共片选路径确认失败后，才拆 R15、装 R16、J2-9 接 GPIO10；
    同时修改固件为两颗控制器独立初始化及每行两个 512×600 半帧拆分。

## 8. 仿真边界与残余风险

SPD1657 的闭环驱动波形和 SPICE 模型未公开，现有工程不能可靠模拟高压
启动、环路稳定性、实际轨值或温升。已完成的 ERC/DRC、网络、器件额定值、
静态拓扑和制造数据检查不能替代首板实测。MF-1750 文档对 pin1 存在
机械/I/O 表 NC 与参考图 VPP 的内部冲突；Rev A1 按机械/I/O 表保持 NC。

## 9. 生成链与可维护文件

- 设计生成：`hardware/generate_mf1750_production_v1.py`
- 路由/制造导出：`hardware/route_mf1750_production_v1.py`
- Freerouting seed/finalize：`hardware/prepare_mf1750_freerouting_seed.py`、
  `hardware/finalize_mf1750_freerouting.py`
- Rev A1 ECO：`hardware/repair_mf1750_q1_pinout.py`
- KiCad 工程：`hardware/mf1750_production_v1/`

生产目录已经冻结，不应仅为整理文件而重新生成。

## 10. 清空对话后的启动提示

新对话可直接粘贴：

> 请先阅读 `docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md` 和
> `docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`。MF-1750 Rev A1 已
> 提交嘉立创，当前等待首板。继续阶段二：在首板实测数据基础上设计集成
> ESP32-S3、USB-C 烧录/供电、单节锂电充电与 3.3V 稳压的 Rev B；保持
> 现有屏接口、电源拓扑和 GPIO 基线，除非实测要求 ECO。
