# ESP32-S3 + E2802 Cascade eInk 调试工程

## 当前交接入口

- 阶段一制造与固件交接：[`docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`](docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md)
- 阶段二 ESP32/电池整合设计输入：[`docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`](docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md)
- Rev A1 R16 级联整屏实测：[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)
- 主机快速刷新、CI 与六色流水线总集成：[`docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`](docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md)
- 多 AI TODO 与 Git 集成计划：[`docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`](docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md)
- 新对话启动提示：[`docs/NEXT_SESSION_PROMPT.md`](docs/NEXT_SESSION_PROMPT.md)
- 1210 电容焊盘复核：[`docs/REV_A1_1210_PAD_AUDIT.md`](docs/REV_A1_1210_PAD_AUDIT.md)
- Rev A1 最终生产检查：[`hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md`](hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md)

当前状态：`MF1750 REV A1` 已完成加工与首板软件级联验证。生产冻结文件
仍为带 `revA1_Q1FIX` 名称的 Gerber、BOM、CPL，禁止重新生成或覆盖。

## 2026-08-04 首板最新结论

- 当前硬件为 R15 拆除、R16 0 Ω 安装、GPIO10 独立控制 `SL_CSB`。
- 两颗 SPD1657B 的 revision 均稳定读为 `0x04`。
- 向两颗控制器分别写 `CCSET(0xE0)=0x01` 后，左右半屏可独立显示纯色，
  并已实测完整 1024x600 连续六色色条。
- 从左到右白/黑/红/黄/蓝/绿正确，中央红/黄中缝清晰；正式分帧为每行
  512 字节，CS1 取前 256 字节、CS2 取后 256 字节。
- ESP32-S3 模组标称 N8R8，当前候选按 OPI PSRAM 构建；约 8 MB PSRAM 的实机
  启动识别仍是 D0 门禁。307200 字节规范帧已完成主机侧字节数与 FNV-1a 校验。
- 仓库当前构建候选为
  `MF1750_DRIVER_RC2B_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_2026-08-04`
  / driver API V2：HTTP ingress 与公开驱动 API 都会在任何面板 I/O 前拒绝
  `0x4/0x7..0xF` 非法像素码；四个正式高压阶段未观察到 BUSY 会 fail closed，
  诊断报告以匹配的 operation ID 与产生它的 job/build 绑定；本地编译已通过，
  尚未刷入实机。
- 硬件步骤的前置门禁是提交并推送最终 `main`、对应 GitHub CI 成功，以及用户
  明确许可刷写/上电；随后依次确认约 8 MB OPI PSRAM、MAP_ORIENT_V1 上下/角点，
  再用同一规范帧完成 1 MHz 上传。当前无 Rev A1 硬件 ECO 证据。普通图片与
  Web UI 属于后续 C4 应用验收，不再混入驱动 D0 定版。
- 远端 `integration/host-fast-refresh-ci-color` @ `dd711c9` 已拉取并快进合入
  本地 `main`，其 64 项历史 GitHub CI 成功；`dd711c9` 本身仍是 RC1/V1。
  随后的本地 RC2B/V2、上传工具、抖动安全契约和 handoff 加固已通过 152 项
  回归、冻结契约与 clean firmware build。
  发布仍以最终推送 SHA 对应的 `main` GitHub CI 为准；CI 不代表硬件验收。

## 构建与仓库边界

固件使用 PlatformIO。首次克隆后先复制 Wi-Fi 配置模板；真实凭据文件不会进入
Git：

```powershell
Copy-Item src\wifi_secrets.example.h src\wifi_secrets.h
platformio run
```

当前固件优先连接 `wifi_secrets.h` 配置的现有 Wi-Fi，并由路由器 DHCP 分配地址；
串口启动日志会打印 `WiFi STA IP`。只有 STA 在超时内连接失败时才回退到设备热点，
因此不要把历史示例中的 `192.168.4.1` 当成固定调试地址。

`hardware/mf1750_production_v1/production/` 内带 `revA1_Q1FIX` 名称的冻结生产
文件属于版本基线，禁止重新生成或覆盖。工作区可另外保留 EPDiy 与 Seeed Wiki
的第三方镜像、EDA 日志和调试截图；这些体积较大且可重新获取，已由 `.gitignore`
排除，不属于本项目的可交付源文件。

驱动 API 的输入边界是规范的 `1024x600`、4bpp 六色像素帧。完整字库、文字
排版、图像缩放、抖动和颜色量化属于后期渲染/应用层；不得耦合进
`epd_driver`。诊断层可以保留少量固定测试图元，但不承担通用字体渲染。

当前实验固件的 HTTP 控制接口没有应用层认证，只能放在可信、隔离的调试网络；
无人看管时保持 J2-1 断电。正式应用版必须增加 token/一次性 arm，或在 release
构建中关闭 legacy/危险诊断路由，不能把主机 CLI 的确认参数当成设备端权限控制。

## 2026-07-13 可生产 PCB 状态

项目现在包含一块面向 MF-1750 / M009F-T（7.5 英寸、1024 x 600、
双 SPD1657）的完整级联驱动转接板 `MF1750 REV A1`：

- 生产目录：`hardware/mf1750_production_v1/production/`
- 嘉立创 PCB：`Gerber_mf1750_revA1_Q1FIX.zip`
- 嘉立创 SMT：`BOM_mf1750_revA1_Q1FIX.csv` +
  `CPL_mf1750_revA1_Q1FIX.csv`
- KiCad 源文件：`hardware/mf1750_production_v1/`
- 下单和首板检查：`production/PCB下单与首板检查.md`

这块板替代不兼容的 DESPI-C73 50pin 屏接口，并包含 MF-1750 A1 参考
电路所需的升压、负压和电荷泵网络。它不是 ESP32 主控板，也不含板载
3.3 V 稳压器；J2 需要外接 ESP32-S3 和稳定的 3.3 V 电源。

默认装配 R15，把 `CSB` 与 `SL_CSB` 相连，按 E2802 cascade 参考板的
单 CS 方式工作。需要独立第二片选时，先拆 R15，再装 R16，并将 J2-9
连接到 GPIO10；两者禁止同时安装。J2 前 8 脚沿用现有 DESPI-C73 顺序。

最终自动检查结果：ERC 0、DRC 0、未连接焊盘 0、原理图/PCB 一致性
错误 0。以上只能证明设计文件内部一致，首板仍必须核对屏尾 pin 1 与
接触面、嘉立创贴装方向，并在接屏前限流测量各高压电源轨。

Rev A1 已按器件数据手册修正 Q1 为 `1=G、2=S、3=D`，并把负压泵
D2 修正为 `K=GND、A=NEG_PUMP_H`；下单时只使用带 `revA1_Q1FIX`
名称的三个文件，避免与修正前上传记录混淆。

当前工程基于你提供的 `E6_73_sample code_V1.2_20250116` 和 `InkCubic_ E2802_cascade 电子纸E6转接板.pdf` 调整。

## 2026-06-10 验证记录（历史，已被 Rev A1/R16 结果取代）

> 本节及其后的 C73 接口排查是历史记录，用于解释为什么制作 Rev A1。
> 本段记录当时按 R15 共片选与 `EPD_PIN_CS2=-1` 排查的过程；当前首板已经
> 拆 R15、装 R16=0 Ω，并以 GPIO7/GPIO10 独立控制两颗 SPD1657B。不得把下述
> 旧 C73/R15 结论当成当前接线。

本轮软件/硬件联合测试结论：

- 当前 ESP32 + DESPI-C73 接线可以稳定驱动左半屏 `512x600`。
- `/api/bars-512x600` 测试结果：左侧通高显示完整 `白/黑/红/黄/蓝/绿` 六色条，说明当前 SPI、颜色编码、4bpp 像素格式、初始化和刷新流程对左半屏是正确的。
- `/api/bars-800x480` 测试结果：左侧显示 `白/黑/红/黄`，黄色略窄，底部出现通长肉色条。原因是 `800x480` 只覆盖 480 行，物理屏高为 600，底部 `120` 行未被刷新，保留残影/中间态。
- `/api/bars` 当前按 `1024x600` 发送 `307200` 字节，全屏会进入刷新流程，但最终仍主要只有左半屏出现渐变/残影，不能形成完整六色条。
- 3-wire 9-bit SPI 已测试，`PON/DRF/POF` 的 BUSY 立即返回，面板没有进入正常约 21 秒刷新流程；当前接线应继续使用 4-wire SPI + DC。
- 因此，“调整分辨率”只能解释并修正左半屏显示格式，不能在当前 DESPI-C73 硬件上单独解决右半屏不显示。

当前明确结论：

```text
整屏物理分辨率：1024 x 600
当前可驱动区域：左半屏 512 x 600
当前可用片选：CSB
缺失关键控制：SL_CSB / CS2
```

要实现完整 `1024x600`，仍需要把 MF-1750 pin 4 `SL_CSB` 引到 ESP32 的第二片选 GPIO，并在软件中分别向两颗控制器写入两个 `512x600` 半帧。现有 DESPI-C73 的 50pin pin 4 在图纸中不是 `SL_CSB`，不能直接当作第二片选使用。

关键结论：

- 当前面板整屏分辨率按你确认配置为 `1024x600`。
- `MF-1750..1).pdf` 的面板说明包含 `0.5T + SPD1657 * 2ea` 和 `7.50" TFT; 1024 X 600 DOTS`，因此这块屏本身就是双驱动/双半屏结构。
- `MF-1750` 的 50pin FPC 定义里，pin 4 是 `SL_CSB`，pin 31 是 `CSB`。当前只刷一半屏，最可能就是只驱动了 `CSB`，而 `SL_CSB` 没有被 MCU 控制。
- `DESPI-C73-SCH-20251014.pdf` 的 P2 8pin 只引出 `3V3/GND/SDI/SCLK/CS/D-C/RES/BUSY`，没有第二片选；它的 P1 50pin 里 pin 4 标为 `VDD`，不是 `SL_CSB`，因此不能把 DESPI-C73 的 P1 当作 MF-1750 的完全匹配接口。
- 参考资料里的级联转接板是 `E2802 cascade`，PDF 明确标注 `4-wire SPI(Default)`。
- E2802 转接板 PDF 的主接口能看到 `3V3/SDI/SCLK/CS/D/C/RES/BUSY`，原理图内部还能看到 `SL_CSB`、`BS0`、`BS1`；其中 `BS0/BS1` 被拉到 `VDD`，说明无需单独接 `BS`。
- 只显示长边一半不是屏幕坏，而是级联屏只驱动了其中一颗 E2802。
- 工程现在按两颗控制器处理：每颗 E2802 的 `TRES` 为 `512x600`，整屏为两个 `512x600` 半屏拼接。

## 图纸比对结论

`MF-1750` 屏的关键 FPC 引脚：

| Pin | Signal | 作用 |
| --- | --- | --- |
| 4 | `SL_CSB` | Slave chip select，第二片/级联片选 |
| 26 | `BS0` | 低电平为 4-wire SPI，高电平为 3-wire 9-bit SPI |
| 27 | `BS1` | 低电平参考 `BS0`，高电平为 standard/dual/quad 4-wire SPI |
| 28 | `RST_N` | 复位 |
| 29 | `BUSY_N` | 忙信号 |
| 30 | `DC` | Data/Command |
| 31 | `CSB` | 主片选 |
| 32 | `SCL` | SPI 时钟 |
| 33 | `SI0` | SPI 数据输入 |

`DESPI-C73` 的 P2 8pin 接口只适合单片选 SPI：

| P2 Pin | Signal |
| --- | --- |
| 1 | `3V3` |
| 2 | `GND` |
| 3 | `SDI` |
| 4 | `SCLK` |
| 5 | `CS` |
| 6 | `D/C` |
| 7 | `RES` |
| 8 | `BUSY` |

危险点：`DESPI-C73` 的 P1 pin 4 在图纸中接 `VDD`，而 `MF-1750` 的 pin 4 是 `SL_CSB`。如果直接把 ESP32 GPIO 接到这个点，GPIO 拉低时可能短接电源。要驱动全屏，必须使用真正把 `SL_CSB` 引出的 E2802 cascade 转接板焊盘/排针，或改板前先断开 `P1 pin 4 -> VDD` 的连接。

## 当前接线（Rev A1 / R16 双独立片选）

| Rev A1 J2 | 信号 | ESP32-S3 |
| ---: | --- | --- |
| 1 | `3V3` | 稳定 3.3 V；用于驱动板上/断电 |
| 2 | `GND` | `GND` |
| 3 | `SI0/MOSI` | `GPIO11` |
| 4 | `SCL/SCK` | `GPIO12` |
| 5 | `CSB` / CS1 | `GPIO7` |
| 6 | `DC` | `GPIO6` |
| 7 | `RST_N` | `GPIO5` |
| 8 | `BUSY_N` | `GPIO4` |
| 9 | `SL_CSB` / CS2 | `GPIO10` |
| 10 | `GND` | `GND` |

当前实板必须保持 R15 拆除、R16=0 Ω；R15 与 R16 禁止同时安装。FPC 禁止
带电插拔，所有逻辑信号均为 3.3 V。旧 C73、单 CS、R15 共片选和
`EPD_PIN_CS2=-1` 只属于前期排查记录，不能作为当前接线执行。

## 当前测试入口与边界

固件优先接入 `wifi_secrets.h` 配置的现有 Wi-Fi，实际 URL 以串口打印的
`WiFi STA IP` 为准；`192.168.4.1` 仅是 STA 失败后的 AP 回退地址，不是固定
调试地址。RC2B 尚未刷入，默认驱动板断电；未经用户明确确认，不刷写 COM8、
不访问任何会触发刷新的 HTTP 路由。

D0 的唯一正式实屏顺序和命令见
[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)：
先核对约 8 MB OPI PSRAM，再做低速 MAP_ORIENT_V1，最后用同一规范帧完成
1 MHz 上传。历史 `/api/white`、`/api/black`、`/api/test` 和半屏上传流程只用于
诊断溯源，不构成当前驱动验收。

## 2026-06-10 当时的已知限制（不要作为当前状态）

- 当时使用的 ESP32-S3 没检测到 PSRAM，无法一次性分配 `307200` 字节全屏帧缓冲；
  当前 esptool/模组标识为 N8R8，但 RC2B 运行时成功初始化约 8 MB OPI PSRAM
  仍待正式启动日志确认，因此该历史限制尚不能只凭型号判定为已解除。
- 当时的图片入口只上传 `512x600` 半屏；当前 Rev A1/R16 已改为规范
  `1024x600`、307200 字节完整帧入口。
- E6 全彩 eInk 刷新需要几十秒，`DRF` 阶段 BUSY 拉低约 20 秒是正常现象。
