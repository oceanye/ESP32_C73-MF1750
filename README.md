# ESP32-S3 + E2802 Cascade eInk 调试工程

## 当前交接入口

- 阶段一制造与固件交接：[`docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`](docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md)
- 阶段二 ESP32/电池整合设计输入：[`docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`](docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md)
- Rev A1 R16 级联整屏实测：[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)
- 基础驱动与 API 参考：[`docs/MF1750_DRIVER_API.md`](docs/MF1750_DRIVER_API.md)
- 网络照片与随机刷新 TODO：[`docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md`](docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md)
- 扩展颜色/亮度技术可行性结论：[`docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`](docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md)
- 扩展颜色/亮度后续测试 TODO：[`docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)
- 主机快速刷新、CI 与六色流水线总集成：[`docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`](docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md)
- 多 AI TODO 与 Git 集成计划：[`docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`](docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md)
- 新对话启动提示：[`docs/NEXT_SESSION_PROMPT.md`](docs/NEXT_SESSION_PROMPT.md)
- 1210 电容焊盘复核：[`docs/REV_A1_1210_PAD_AUDIT.md`](docs/REV_A1_1210_PAD_AUDIT.md)
- Rev A1 最终生产检查：[`hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md`](hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md)

当前状态：`MF1750 REV A1` 已完成加工与基础驱动 D0 实机验收。生产冻结文件
仍为带 `revA1_Q1FIX` 名称的 Gerber、BOM、CPL，禁止重新生成或覆盖。

## 2026-08-04 首板最新结论

- 当前硬件为 R15 拆除、R16 0 Ω 安装、GPIO10 独立控制 `SL_CSB`。
- 两颗 SPD1657B 的 revision 均稳定读为 `0x04`。
- 向两颗控制器分别写 `CCSET(0xE0)=0x01` 后，左右半屏可独立显示纯色，
  并已实测完整 1024x600 连续六色色条。
- 从左到右白/黑/红/黄/蓝/绿正确，中央红/黄中缝清晰；正式分帧为每行
  512 字节，CS1 取前 256 字节、CS2 取后 256 字节。
- ESP32-S3 已由 esptool 与运行时共同确认约 8 MB OPI PSRAM；307200 字节
  规范帧的主机、设备生成器和非刷新 ingress 哈希均已通过。
- 当前源码候选固件为
  `MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05`
  / driver API V3；它在 RC2E 交互构图上增加 MF-1750 物理有效区和非正方形像素
  模拟，clean build 为 811056 字节、SHA-256 `AE5261…3A4A20`，尚待刷写和实屏复验。
  HTTP ingress 与公开驱动 API 都会在任何面板 I/O 前拒绝
  `0x4/0x7..0xF` 非法像素码；PON/DRF/POF 未观察到 BUSY 会 fail closed，
  POF 后的 PSR 寄存器写入保留等待证据但不要求额外 BUSY assertion；诊断报告
  以匹配的 operation ID 与产生它的 job/build 绑定。
- RC2C/V3 已用同一 MAP_ORIENT_V1 完成 100 kHz 协议复验和正式 1 MHz
  `/api/frame` 实屏验收；方向、中缝、颜色、完整/双 DTM 哈希、PON/DRF/POF
  BUSY、电源、温度及断电安全状态均正确。1 MHz 总耗时 34.187 秒，其中两半
  DTM 上传各 2.444 秒、DRF 约 21.7 秒。
- 主机 PSRAM 预检修正点 `2b19f75` 的 203 项回归、repository contract、
  PlatformIO build 与 GitHub CI run `30917129233` 全部通过；验收记录提交
  `fd548e3` 的 CI run `30918209821` 也通过。RC2C 实测 `firmware.bin` 为
  796272 字节、SHA-256 `F763FE…F45C475B`；RC2D 为 803120 字节、SHA-256
  `AE7427…943DAD`，
  在重新实屏验收前不得与 RC2C 的硬件证据混用。当前无 Rev A1 硬件 ECO 证据。
- 基础驱动 D0 已定版；普通图片与 Web UI 的软件合同已合入，但 calibrated palette
  真屏色彩、设备端认证、更高 SPI 扫频、快速波形和局刷仍是独立后续工作，不能
  由本次硬件通过自动提升状态。

## 2026-08-05 扩展颜色与亮度可行性结论

- 面板规格写明 `3-bit E6`，当前应用帧则是 4bpp packed 容器；4bpp 不代表存在
  16 个独立颜色。正式有效码仍只有 `0/1/2/3/5/6`。
- 第一轮只允许原厂初始化和片上 OTP waveform 不变的六色基线、恢复流程、
  `6×6` 转换矩阵，以及受控的小面积 `0x4/0x7` 数字编码探针。
- 正式 `/api/frame` 继续拒绝 `0x4/0x7..0xF`。未来未知码只能通过默认关闭、
  固定图案、哈希锁定、一次性授权的隔离实验入口执行，不能放宽生产颜色校验。
- 当前 Rev A1 不是可编程 TCON：没有已知 LUT upload、内部 phase、局刷窗口、
  温度读取或独立高压控制接口。取得 SPD1657B rev `0x04`、当前 OTP 和厂商安全
  资料前，禁止猜寄存器、改 LUT/相位/高压或移植 SPD1656 命令。
- 当前没有软件可控 J2-1、PGOOD、板载电流/温度/高压联锁，因此未知码、耐久和
  waveform 实验均处于 `PENDING/BLOCKED`，等待用户逐阶段安排和授权。

完整证据、公式修订、测量门禁和第一轮十个问题见扩色可行性文档；可执行任务、
依赖和停止条件见扩色测试 TODO。两份文档都不构成上电、COM8 刷写或刷新授权。

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
调试地址。RC2C/V3 已完成实机验收；默认驱动板断电，未经用户明确确认，不刷写
COM8、不访问任何会触发刷新的 HTTP 路由。

RC2F 候选固件的设备首页提供照片工具模式：选择一次原图后，可在 Atkinson、
Floyd–Steinberg、无抖动和 8x8 有序抖动间切换，同时对比原图构图与实际六色
上传预览；可在原图画布拖动、滚轮/滑杆缩放、按 90° 旋转并重置构图。照片优化、
裁剪、构图和处理方式的变化只在浏览器本地重算，点击“上传并刷新”
后才提交当前帧。该网页仍使用未校准 reference RGB 色板，属于便捷实验入口，不
替代 calibrated host pipeline。

右侧六色预览按 M009F-T A1 规格书的 `163.84×97.20 mm` 有效区、
`0.160×0.162 mm` 像素间距和约 158 PPI 校正显示比例，不再假定像素为正方形；
像素检查支持适应窗口及 1×/2×/4×倍率，并可叠加像素边界。浏览器显示器的毫米
尺寸不保证物理 1:1，且 reference RGB 色板仍不是实屏测色结果。

D0 的唯一正式实屏顺序和命令见
[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)：
该顺序已经完成。正式调用方法与响应结构见
[`docs/MF1750_DRIVER_API.md`](docs/MF1750_DRIVER_API.md)；历史 `/api/white`、
`/api/black`、`/api/test` 和半屏上传流程只用于诊断溯源，不属于稳定应用 API。

## 2026-06-10 当时的已知限制（不要作为当前状态）

- 当时使用的 ESP32-S3 没检测到 PSRAM，无法一次性分配 `307200` 字节全屏帧缓冲；
  当前 esptool 与 RC2B 运行时均已确认约 8 MB OPI PSRAM，因此该历史限制已解除。
- 当时的图片入口只上传 `512x600` 半屏；当前 Rev A1/R16 已改为规范
  `1024x600`、307200 字节完整帧入口。
- E6 全彩 eInk 刷新需要几十秒，`DRF` 阶段 BUSY 拉低约 20 秒是正常现象。
