# E Ink 相邻 runtime-waveform / WBF 合同边界

冻结日期：2026-08-12（Asia/Shanghai）

## 1. 判定

公开资料能够证明：电子纸系统可以在运行时换入 waveform 文件，并依据温度选择 waveform；
也能够证明 ED2208-DOA 评估套件允许更新某种 `Initial Data (.eink)`。这些事实提升了
“通过波形改变光学结果”这条路线的工程可信度。

它们不能证明本项目 SPD1657/E2802 的 `0x20 + 799`、`0x21 + 704`、外层 800-byte
wrapper、11-byte record 字段或双控制器提交合同。尤其不能把其他 TCON 文档中的电压值、命令号
或 WBF 格式直接移植到 MF-17506。

## 2. EPM-100：公开的完整相邻运行时合同

E Ink 下载站托管的 [EPM-100 USB Programming Guide v0.1](https://shopkits.eink.com/en/download/0223020711rk338873/Content%20transfer%20programming%20guide.pdf)
由 Digital View 编写，日期为 2021-03-16，对应 EPM-100 firmware v1.4 起。它是外置 TCON/灰阶
系统的相邻资料，不是 SPD1657、E2802 或 ED2208 COG 规范。

该文档公开了一个可核验的 waveform 更新闭环：

1. 系统信息返回当前 LUT version、WBF buffer address、温度段数量、显示模式数量及各模式
   frame count（pp. 10、27–28）。
2. host 先把完整 WBF 文件装入专用 buffer，再发送 mailbox command `0x003B`（p. 30）。
3. TCON 自己解析 WBF，并把结果更新为当前 volatile waveform；文档明确说不写 external flash
   （p. 30）。
4. 解析完成后 HRDY 变高，HSPI host 还可读状态寄存器 `0x0224`（p. 30）。
5. 正常显示由每块 TCON 的外部温度传感器选择 mapped waveform；`0x0033` 只提供显式的 host
   temperature override，并说明 override 会停用传感器监测（pp. 31–32）。
6. EPD source/VCOM voltage 是另一个显式命令 `0x0042` 的独立参数（pp. 40–41），不隐藏在上述
   `0x003B` 无参数的 commit 命令中。

这份资料最重要的用途不是提供数值，而是给出一个反例边界：成熟 runtime-waveform 系统会把
文件缓冲、解析/生效、完成状态、温度映射、易失/持久化和电压设置分别定义。当前本地
`799/704` opaque sender 尚未恢复这些同代合同，因此不能因“payload 被发送”就声称 waveform
已由两颗控制器一致接受。

文档中的命令号、寄存器和电压示例全部标记为 `EPM-100-only / non-portable`，不进入任何
本项目 firmware、profile 或上屏候选。

## 3. ED2208-DOA：同面板家族的 Initial Data 路径

E Ink 的 [4.0-inch ED2208-DOA User Manual](https://shopkits.eink.com/en/download/0224112222me459948/User%20Manual_4%27%27%20Spectra%206%20ePaper%20Display%20%28ED2208-DOA%29.pdf)
是 2024-09-13 draft。文档直接说明：

- 400×600 ED2208-DOA 内嵌 all-in-one IC，其中含 source/gate driver、TCON、PMIC 和 temperature
  sensor（p. 7）；
- PC 工具 `Flash_Burner.exe` 可把 `Initial Data (.eink)` 写入 HULK kit，写入后需断开并重新
  插拔 USB，成功时设备名显示为 `WF29KWR`（pp. 14–15）；
- 文档没有公开 `.eink` 容器、LUT record、命令流、校验、温区、持久化目标或电气字段。

因此它证明 exact ED2208-DOA 评估链中存在厂家初始数据更新机制，但不能把 `.eink` 等同于本地
2508-byte slot，也不能证明它是可在每次刷新前使用的 COG runtime-LUT。

M5Stack 的官方 [PaperColor 文档](https://docs.m5stack.com/en/core/PaperColor)进一步确认量产开发板
使用 ED2208-DOA / EL040EF1、400×600、单 `EINK_CS` SPI 连接。其公开示例仍只展示白、黑、红、
黄、绿、蓝六码和普通刷新 API；没有公开 waveform upload、brightness/contrast register 或
`.eink` parser。该 one-CS 实现不能证明 MF-17506 的双控制器装载拓扑。

## 4. 对“能否用波形得到更多颜色”的贡献

| 问题 | 当前证据判定 |
|---|---|
| 波形能否改变粒子最终层级/光学状态 | 物理路线成立；本地真屏也已观察到同一蓝色码的多个亮度层级 |
| 系统能否运行时换 waveform | EPM-100 相邻 TCON 明确支持 volatile WBF update；不能移植其 ABI |
| ED2208-DOA 是否有可更新的厂家初始数据 | 有 `.eink` Initial Data 路径；格式和 runtime 语义未公开 |
| 本地 800/799/704 是否已能安全任意编辑 | 否；container/send length 的证据增强，字段语义仍不闭合 |
| 能否直接尝试 EPM-100 电压示例 | 否；控制器、PMIC、面板、waveform 和量产 lot 均不匹配 |
| 现在最有信息量的真屏测试 | matched C 基线与既有 empirical-H3 T 的同图矩阵比较；不新增猜测电气字段 |

## 5. 下一步证据门

在生成新的 byte-level LUT 变体前，至少还需满足以下一项：

- 同代 SPD1657/E2802 loader/parser 对 799-byte body 的字段读取；
- 两份只改单一已知参数且有厂家元数据的 profile，用差分定位该参数；
- 完整 command/data/CS/BUSY capture，把 payload 身份、两颗控制器目的端与接受状态绑定；
- 厂家提供 `.eink`/WBF/runtime payload 格式或精确 revision command specification。

在这些证据出现前，公开资料支持继续做一次一授权、温度固定、物理切断就绪、前后白屏恢复的
经验 profile 对照；不支持自动扫描、跨控制器移植电压或把观察到的颜色层级升级为生产 LUT。
