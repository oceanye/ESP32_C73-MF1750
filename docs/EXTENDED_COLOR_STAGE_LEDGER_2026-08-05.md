# MF-1750 扩展颜色 A～J 阶段执行账本

日期：2026-08-05（Asia/Shanghai）

本账本记录当前已授权的非硬件工作及所有尚未通过的门禁。它不构成上电、COM8
刷写、刷新、未知码、LUT、电压或 `main` 操作授权。

> 本文件保留远端研究会话的阶段快照，因此下面的工作区路径、分支和“未合并”
> 描述均指该次远端交付时点。当前本地集成状态、审查缺陷与修正结果见
> `docs/EXTENDED_COLOR_INTEGRATION_REVIEW_2026-08-05.md`；硬件门禁没有因此改变。

## 1. 冻结范围与结论

- 用户给出的工作区 `C:\Users\Ye\PycharmProjects\ESP32_C73` 在本会话环境不可用；
  实际仓库为 `C:\Users\ZJLZ1026\Documents\eink`，其 `origin` 是
  `https://github.com/oceanye/ESP32_C73-MF1750.git`。
- 远端基线与本研究分支 base：`origin/main` =
  `3dfd4776b749660a5462f27b80d0055f23f0c47e`。用户给出的“`main` / `origin/main`
  同为该提交”与实际本地引用有一处差异：本地 `main` 仍为
  `3033da082072c6088983bd07f36ad6b8aa7b9778`，落后 `origin/main` 33 个提交；按门禁
  未切换、移动、推送或以其他方式修改本地/远端 `main`。
- 独立分支：`research/extended-color-20260805`。
- 非硬件技术提交：`689549f32644ea2c3dbc7120d14a85baa648c778`。
- 阶段账本提交：`4a8575db9b0cadcd20d460c3efdc731fbbb654a3`。
- 本轮 Spectra 6 更多颜色离线工具/证据提交：以包含本次更新的后续研究分支 commit
  为准，避免在 commit 内记录自引用 hash。
- `main` 未推送、未合并；未创建 tag。
- `src/`、`platformio.ini`、正式 `/api/frame` 和公共六色 guard 相对基线无修改。
- `.test-output/` 未枚举、未读取内容、未删除、未覆盖、未提交；仓库规则现在明确
  忽略它，新增工具也主动拒绝向其中写入。
- Hardware tested: `NO`。

当前总判定：A、B 和 F 的离线设计范围已完成，其中 B 已增加正式六码空间抖动/
面积混色优化、强语义验证与可复现 frame/双 DTM 身份；C 的设计完成但硬件出口为
`BLOCKED / NO-GO`；D、E、G、H 未开始且被门禁阻断；I 为 `HARD BLOCKED`；J 的
当前非硬件交付范围已完成。下一处必须停下的门是“是否实现 F 实验固件”。

## 2. 用户授权记录

| 记录 | 已获授权 | 未获授权 |
|---|---|---|
| `AUTH-NHW-20260805` | 初始指令明确允许只读检查、官方检索、测试、静态检查、编译、新建独立研究分支、主机工具/文档、提交并推送独立研究分支 | 不扩展到任何硬件动作 |
| `AUTH-NHW-MORECOLOR-20260805` | 用户明确希望获得更多颜色并提供 Spectra 6“四粒子、六主色、dithering 全彩”页面文字；据此继续已获通用授权范围内的官方核对、六码空间混色工具、schema、模拟测试与研究分支交付 | 不授权额外编码、实验固件、波形/LUT/电压、COM8、上电或刷新；页面文字本身不作为可执行参数证据 |
| `AUTH-TOOLCHAIN-20260805` | 会话中批准在 `C:\tmp` 安装/运行固定 Python 3.12.10 与 PlatformIO 6.1.19，仅用于测试和 release build | 不含 upload、串口或 COM8 |
| `AUTH-GIT-20260805` | 会话中批准列明文件的 `git add`、独立分支 commit 和该分支 push | 不含 `main`、merge、tag |
| F 实验固件 | 无 | 尚未批准实现；`src/epd_driver.*` 精确修改范围也未批准 |
| 硬件七步门禁 | 无 | 断电、COM8、上电、电源确认、指定帧、刷新后确认、最终断电/TP1 均未授权 |
| LUT/phase/电压 | 无 | 全部保持 HARD BLOCKED |

未上电或假定面板已上电；未访问 COM8；未调用刷新 HTTP 接口；未发送任何帧。

## 3. 阶段状态总表

| 阶段 | 状态 | Hardware tested | 原始数据路径 / SHA-256 | 当前 go/no-go |
|---|---|---|---|---|
| A | `COMPLETED`（证据调研范围） | NO | 无硬件原始数据；`null` | 非硬件 B/C/F：GO；任何未知命令/参数：NO-GO |
| B | `COMPLETED` | NO | 仅确定性模拟数据；不冒充实测 | 主机离线工作：GO；设备 I/O：NO-GO |
| C | `BLOCKED`（设计完成，实物资格未完成） | NO | `null` | D/G/H/I：NO-GO |
| D | `BLOCKED / NOT STARTED` | NO | `null` | 等待 C GO 与逐步硬件授权 |
| E | `BLOCKED / NOT STARTED` | NO | `null` | 必须先完成 D 并确认恢复可靠 |
| F | `COMPLETED`（离线设计）；实现 `BLOCKED` | NO | 仅固定模拟帧/hash；无实测 | 等待用户审查与实现授权 |
| G | `BLOCKED / NOT STARTED` | NO | `null` | F 实现/审查/build/hash、C/D 和硬件逐项授权缺失 |
| H | `BLOCKED / NOT STARTED` | NO | `null` | 必须先提交 G 报告并再次授权；bit3 仍未知 |
| I | `HARD BLOCKED / NOT STARTED` | NO | `null` | 全部资料、夹具、联锁和单独 safety review 缺失 |
| J | `COMPLETED`（当前非硬件范围） | NO | 无硬件原始数据 | 仅研究分支交付；main/merge/tag：NO-GO |

## 4. A：官方资料与证据调研

状态：`COMPLETED`。

实际执行：完整阅读用户列出的 README、六份项目文档、原证据矩阵、精确面板 PDF
全部 24 页及 E6_73 官方样例工程；检索并核对面板厂、E Ink、Solomon Systech、
正式 SID/IDW 论文和原理限定专利。针对用户补充的 Spectra 6 页面文字，又以 E Ink
2024 年报、IDW/SID 正式论文和 2025 官方公告做交叉核对。输出 D/P/I/U（直接证据/
平台证据/推论/未知）矩阵，覆盖用户列出的 13 个主题。

新增结论：白/红/黄/蓝四种带电粒子形成黑/白/红/黄/蓝/绿六个量产设备色，再由
dithering/advanced color mixing 形成更多视觉颜色；这直接支持六码空间混色路线。
IDW 论文和后续公告只支持额外混合光学输出的物理可能性，不证明本机拥有稳定、
可寻址、可保持的额外单像素状态。E Ink 公告先述 Ripple 转场，再以“in addition”
另述新混色 waveform architecture；二者关系未知，公告只列六家芯片供应商而没有
具体型号，不能据 Solomon 入列推断 SPD1657/B 兼容。

未执行：未把 800×480、192000 B 的相邻样例寄存器移植到本机；未把 SPD1656
当作 SPD1657B；未把专利变成可执行参数。由于未取得 SPD1657B rev 0x04 完整
datasheet，0x4/0x7、bit3、OTP manifest、LUT、0x86 精确定义、partial/window、
温度读回、高压轨绝对范围和耐久限制等 54 个关键可执行字段保持 `null`。

授权：`AUTH-NHW-20260805`。异常/恢复：无硬件异常；恢复不适用。

产物与 SHA-256：

- `docs/EPD_EXTENDED_COLOR_OFFICIAL_EVIDENCE_2026-08-05.md`：
  `96EC3A5D3D0D72950C4C0A42B1D017C08B384F6C7CD78ACB00D85C1370D469FF`
- `research/extended_color/evidence_matrix.json`：
  `E91101A2C97E324C46DBBFD5783117FADA59AC1FFE856D260B19F77219215A23`
- `docs/SPECTRA6_MORE_COLOR_TECHNICAL_PATH_2026-08-05.md`：
  `5CE487F19B8593BAFBC319B2470154CCF724F4B6E279C8FFFF8BC0388413A661`

本地输入资料身份：

| 资料 | bytes | SHA-256 |
|---|---:|---|
| `参考资料/MF-1750..1).pdf` | 2189983 | `C03EF3C34BBF4ECE7D280D37197ADD64C67D0E13C26BFF0861A1D399ABBED187` |
| `参考资料/E6_73_sample code_V1.2_20250116.7z` | 376465 | `8F326E897810CFDE51906198568239DE87F7C7BBBF2983640480BC4FB9B1B2EE` |
| `参考资料/Solomon-SPD1656.pdf` | 2339387 | `1F3F5DB0600EE6E8133A4C31F9A3F59C1B5BFCC1A916BE98AE848EC64581DE07` |

下一步：允许继续安全的主机工作；不允许根据缺失字段执行硬件实验。

## 5. B：软件基线与测试基础设施

状态：`COMPLETED`。

实际执行：fetch、分支建立和基线核对；新增六色纯色/大色块、6×6 转换矩阵、
CS1/CS2 镜像布局、72 个 ROI、轮次布局旋转、frame/双 DTM SHA-256 与 FNV-1a、
确定性 test ID、固定 0x4/0x7 离线 fixture、空 36-cell optimizer profile、run/
optical/electrical/event-recovery/asset/transition schema、显式资产 manifest 工具和
报告模板。所有新 CLI 都没有网络、串口、设备、刷新、删除或自动重试能力。

本轮新增六码面积混色优化器：精确枚举 2×2 的 126 种或 4×4 的 20,349 种整数
配方；把校准 Lab 转到 CIE XYZ 后做面积平均，再以 CIEDE2000 排名；用固定
`bayer-threshold-interval-v1` 布局生成正式六码 tile，并为每个候选重算 1024×600、
4bpp、307200 B frame 和 CS1/CS2 DTM 身份。报告嵌入完整 palette、模型/layout/hash
scope、预测/实测区分和选择绑定；语义 validator 会重算真实 top-N、预测、tile、
frame 和双 DTM，所有尚未测量的能量、残影、转换成本和 Lab 字段保持 `null`。

输出工具不含设备通信参数；frame 输出必须带报告 sidecar，先写报告、后写帧，并用
exclusive-create 禁止覆盖。共享路径门禁在解析/打开前拒绝 `.test-output/`、冻结生产
目录、Windows DOS 设备名（含 `COM8` 扩展名/尾随空格别名）、UNC/device namespace、
NTFS ADS 和映射网络盘。正式 `validate_frame()` 与正式 API 的六色 guard 没有放宽。

未执行：未生成或读取硬件原始数据；未调用现有设备工具；未修改设备固件。

授权：`AUTH-NHW-20260805`、`AUTH-NHW-MORECOLOR-20260805`、
`AUTH-TOOLCHAIN-20260805`。Hardware tested: `NO`。

关键离线 fixture SHA-256：

| fixture（repetition 1） | frame | CS1 DTM | CS2 DTM |
|---|---|---|---|
| transition initial | `db4c425ebed64e5f5bf3b5322d5afa1af2670f854626115cb8b7df55d5b64820` | `17f2a7cf4e142c2afe1b5e6f2abcf0bc5c714ec0385a84ef3af22b2065128896` | 同 CS1 |
| mirrored transition target | `7a3546d06ffb3afc155abfc459bb587f4c45b9c857272069f2c39f57799624a0` | `1003a5217a32f71fb191911046e142f15ed9f24a43cd98afae3a6209a3b7fb0d` | `e5f68d6a5c801858bc6e4935db5921dd18f0e20d32cb4f301c6944cd101805e2` |
| unknown 0x4 design fixture | `5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e` | `a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00` | 同 CS1 |
| unknown 0x7 design fixture | `d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e` | `2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac` | 同 CS1 |

未知 fixture 只存在于固定布局离线生成器；`formal_api_compatible=false`，正式
`validate_frame()` 仍拒绝它们。

更多颜色离线示例（目标 sRGB8 `0,180,190`，4×4，未校准参考 palette，显式
simulation opt-in；没有写出 frame 或报告文件）：

| 字段 | 值 |
|---|---|
| analysis ID | `MF1750-EC-MIX-0ACC8C0E2FFD` |
| model / layout | `xyz-area-v1` / `bayer-threshold-interval-v1` |
| palette SHA-256 | `181770a2de3bb23bcc31666573279c8cde8225d2f4c27a24c9c1345dba54965e` |
| 配方（code:pixels） | `0:1, 1:0, 2:0, 3:0, 5:8, 6:7` |
| predicted Lab / ΔE00 | `65.668111,-33.092393,-16.251683` / `1.018405`；预测，不是实测 |
| tile SHA-256 | `665c17f59491ad7fb3efc27c763a41e9824953b22e1aa0e11d6583361c523a52` |
| frame SHA-256 / FNV-1a | `44c22fbef27d24b22cafe3c196fc669f05524f36030d33b79a6b3ce1c82aa26d` / `0xC7C471C5` |
| CS1 DTM SHA-256 / FNV-1a | `97b902644e05a93b6580877507972d80215a4a278fdbf92c87d402899568dca4` / `0xA55487C5` |
| CS2 DTM SHA-256 / FNV-1a | 同 CS1（全帧周期 tile 对称） |
| Hardware tested / 原始数据路径 | `NO` / `null` |

新增实现身份：

| 文件 | SHA-256 |
|---|---|
| `host/extended_color/mixing.py` | `E70505822FB10CCA775021DB1553C5C964E655D3B247C93DCC9059ACDB4F3617` |
| `tools/mf1750_area_mix.py` | `ABC665F249020A4B3416DF07E09DCEA8AADC35005A3EFBA5FA974DFEEAAB5196` |
| `schemas/extended_color/area_mix.schema.json` | `2C04043211DCE12CA730E5A25FC421818F4C349DDAD9F94B502955F83E25DB8A` |

异常/恢复：早期一次 schema regex 负例失败，修正后通过；早期一次 Windows
loopback 测试出现 `WinError 10053`，单测和最终全仓复跑均通过。独立审查还发现并
在提交前修正了 Bayer 排列方向性色带、Windows `COM8`/UNC/ADS 路径、报告 hash
自包含性和 candidate/frame 选择绑定问题；增加了空间分散、路径攻击和报告篡改单测。
均不是硬件异常，无面板动作或恢复。

下一步：离线基础设施可用；禁止自动进入设备刷新。

## 6. C：测量系统与安全门禁

状态：`BLOCKED / NO-GO FOR HARDWARE TEST`；文档设计已完成。

实际执行：建立 45/0 光学、RAW、示波器/高压差分/电流探头、3.3 V PSU、实体
急停与 J2-1 锁存切断、热像/温湿度、仪器序号/校准/采样/带宽/U95/R&R 清单；
冻结 t0 为 POF BUSY_N 释放后 60 s。明确 TP10 是 `BUSY_N`，断电证明是实体切断
J2-1 后 TP1 `<=0.10 V` 持续至少 5 s，而不是用 TP10 证明掉电。

未执行：没有仪器实物资格、同步通道验证、测点/探头签核、R&R 数据，也没有厂家
输入电流、高压轨和器件温度绝对停止值。相对阈值不得替代这些 blocker。

授权：仅文档设计；硬件授权为 `NONE`。Hardware tested: `NO`。原始数据和 SHA：
`null`。异常/恢复：未发生；不适用。

文档 SHA-256：`93EDD5F3DE8AA0B21071B6BCA20940AF675B85F164884AE0AE5E65F4B1327F90`。

下一步：NO-GO；补齐设备、联锁、不确定度和绝对阈值后，仍需单独逐项硬件授权。

## 7. D：原厂六色基线与恢复

状态：`BLOCKED / NOT STARTED`。

实际执行：仅准备离线图案、schema、检查表和报告模板。未执行上电、刷写、刷新、
测轨、温度、Lab、保持或黑白恢复。用户硬件授权：`NONE`。Hardware tested: `NO`。
原始数据路径/SHA、异常、恢复结果：`null`。

下一步：必须先使 C 为 GO，再按断电、COM8（如需）、上电、电源确认、指定六色帧、
刷新后确认和最终断电/TP1 七步逐项申请；任何异常不得自动重试。

## 8. E：6×6 状态转换矩阵

状态：`BLOCKED / NOT STARTED`。

实际执行：完成 old-horizontal/new-vertical 镜像帧、每控制器 36 个转换 ROI、轮次
换位和空 transition profile；所有未测字段为 `null`，语义 validator 强制 36 对
唯一完整。未执行 pilot 或正式重复。用户硬件授权：`NONE`。Hardware tested: `NO`。
原始数据/SHA、异常、恢复结果：`null`。

下一步：必须先完成 D 并确认恢复可靠；然后另行申请 2～3 次 pilot，不能直接申请
5 次正式重复。

## 9. F：0x4/0x7 未知编码实验准备

状态：离线设计 `COMPLETED / READY FOR USER REVIEW`；固件实现
`BLOCKED / NOT IMPLEMENTED`。

实际执行：冻结白底、左右各 64×64 镜像 ROI、32 px guard band 和 8192 px
（1.333333%）未知面积；设计分离的 U04/U07 binary、编译期 fixture、设备内生成、
frame/双 DTM allowlist、一次性 arm/job、冷启动、持久 consumed、无自动重试、
全局 refresh lock、固定恢复和 fail-closed 负例。binary SHA 使用外部只读 sidecar
绑定，嵌入 manifest 使用 RFC 8785 JCS payload digest，避免自引用。

未执行：未实现实验固件；未修改 `src/epd_driver.*`；未建立 route、arm 或设备入口；
未构建 U04/U07；未刷写或刷新。正式 API/guard 保持不变。

授权：设计授权来自 `AUTH-NHW-20260805`；实现授权和精确 driver 修改授权均为
`NONE`。Hardware tested: `NO`。原始数据：仅模拟 fixture；实测数据 `null`。
异常/恢复：无硬件异常；恢复未执行。

文档 SHA-256：`78C7241AF97F02A6A7166C31459D1F1E0E80D27C4E764F03260353B9E29FAF2A`。

下一步：在此暂停，请求用户审查是否授权实现；即使批准，也不自动获得刷写、上电、
刷新或硬件测试权限，且 C/D blocker 仍然有效。

## 10. G：0x4/0x7 硬件探针

状态：`BLOCKED / NOT STARTED`。实际执行：无。未执行内容为 G 的全部硬件步骤。
授权：`NONE`。Hardware tested: `NO`。原始数据、hash、异常与恢复：`null`。

下一步：NO-GO。需要 F 实现代码审查、独立 build/hash、C/D 通过以及每一步硬件
授权；不能因离线 hash 已冻结而开始测试。

## 11. H：0x8～0xF bit3 alias

状态：`BLOCKED / NOT STARTED`。实际执行：仅 A 阶段确认 bit3 行为未知；未生成或
发送任何 pair。授权：`NONE`。Hardware tested: `NO`。原始数据、异常与恢复：
`null`。

下一步：NO-GO。必须先完成并提交 G 报告，再次取得用户批准；若厂家明确禁止
bit3，则取消 H。

## 12. I：自定义波形、时间、电压、温度和耐久

状态：`HARD BLOCKED / NOT STARTED`。

实际执行：仅完成原理证据归类和 safety review 前置条件清单。波形有可能通过粒子
状态控制产生中间光学态，但当前不能把这种平台原理转换成本机参数。空间抖动/面积
混色可继续作为六色离线研究，不构成波形授权。

E Ink 官方公告显示，平台上存在利用现有粒子的“新混色 waveform architecture”
路线，但它与 Ripple 转场的实现关系未公开；公告中的升级 3-bit 配置声称八主色，
另一 T2000 配置声称增加 cyan/light green/orange，二者不得自行合并。公告没有列出
兼容芯片型号，也没有点名 MF-17506、SPD1657/B revision 或当前 OTP，因此本机支持度
仍为 `null`，不能把新色映射到 `0x4`、`0x7` 或 bit3。

未执行：未上传/选择/读回 LUT，未改 phase、时序、电压、PLL、PWR、BTST、POFS、
PWS、VCOM 或高压；未做温度、耐久或候选颜色测试。

授权：`NONE`。Hardware tested: `NO`。原始数据、异常和恢复：`null`。

下一步：NO-GO。只有 SPD1657B 完整资料、OTP 包、正式 LUT 接口、字段换算/限值、
VCOM/Source 夹具、全部硬联锁、牺牲屏/黄金屏和厂家恢复/寿命要求齐全后，才可提交
单独 waveform safety review；电压扫描仍需再次授权。

## 13. J：报告、Git 与交接

状态：`COMPLETED`（当前已授权的非硬件范围）。

实际执行：新增本账本、A/C/F 文档、schema、manifest、报告模板、离线生成器与测试；
本轮又新增 Spectra 6 更多颜色技术路线、六码面积混色优化/语义 validator、自包含
schema、可审计 frame/双 DTM 身份和 Windows 本地路径安全门禁。已完成代码与证据两轮
独立只读审查。研究提交仅推送到 `origin/research/extended-color-20260805`；未推送
`main`、未合并、未创建 tag、未修改冻结生产目录。

Git：

- base：`3dfd4776b749660a5462f27b80d0055f23f0c47e`
- local `main`（未修改）：`3033da082072c6088983bd07f36ad6b8aa7b9778`
- `origin/main`：`3dfd4776b749660a5462f27b80d0055f23f0c47e`
- 技术提交：`689549f32644ea2c3dbc7120d14a85baa648c778`
- 阶段账本提交：`4a8575db9b0cadcd20d460c3efdc731fbbb654a3`
- 本轮更多颜色提交：以包含本次更新的后续分支 commit 为准，避免自引用 hash
- remote branch：`origin/research/extended-color-20260805`

Hardware tested: `NO`。硬件原始数据：无；路径和 SHA-256 为 `null`。异常/恢复：
没有硬件异常。一次 PowerShell module analysis cache 曾在仓库根生成；在核对绝对
路径和内容后，经明确批准删除该可再生成缓存；项目文件及 `.test-output/` 未受影响。

下一步：保持研究分支隔离，停在 F 实现授权门。

## 14. 命令、退出码与构建身份

| 命令 | 最终结果 |
|---|---|
| `git fetch --prune origin` | exit 0 |
| `git rev-list --left-right --count main...origin/main` | exit 0；`0 33`，本地 main 落后且保持未修改 |
| `git rev-list --left-right --count HEAD...origin/research/extended-color-20260805`（提交前） | exit 0；`0 0` |
| 未加引号的 PowerShell `HEAD...@{upstream}` 检查 | exit 128；`@{}` 被 shell 解释，随后改用显式远端分支成功；无引用或文件变化 |
| 建立 `research/extended-color-20260805` 于 `origin/main` | exit 0 |
| `C:\tmp\mf1750-python312\python.exe tools\check_repo_contract.py` | exit 0；`passed=true`、`hardware_tested=false`；仅保留既有 manufacturing manifest warning |
| `C:\tmp\mf1750-python312\python.exe -m unittest discover -s tests` | exit 0；256 tests，OK，skipped=1（可选 Pillow）；93.272 s |
| `C:\tmp\mf1750-python312\python.exe -m compileall -q host app tests tools` | exit 0 |
| `node --check web\app.js` | exit 0 |
| PlatformIO 6.1.19 `run`，release | exit 0；RAM 45568/327680（13.9%），Flash 810325/3342336（24.2%） |
| `git diff --check` / `git diff --cached --check` | exit 0 |
| `git diff -- src platformio.ini host/epd_frame web app` | exit 0，无输出 |
| 原扩展颜色定向测试 | exit 0；29 tests，OK |
| `tests.test_extended_color_mixing` 定向测试 | exit 0；14 tests，OK；独立审查复跑 |
| mixing + extended-color + record 定向测试 | exit 0；46 tests，OK |
| area-mix 模拟 CLI（4×4、limit 1） | exit 0；只输出内存报告，`hardware_tested=false`；未写文件 |
| `python -m json.tool`（evidence matrix + area-mix schema） | exit 0 |
| 技术提交 `git commit` | exit 0；22 files，4970 insertions |
| `git push -u origin research/extended-color-20260805` | exit 0；仅新建研究分支 |

首次尝试 PlatformIO 时本机缺少可用 Python/PlatformIO，且非提权进程遇到本地工具
ACL；随后使用用户批准的 `C:\tmp` 固定环境完成 build。没有执行 `platformio upload`
或任何串口命令。

最终 release binary：

- 路径：`.pio/build/esp32-s3-devkitc-1/firmware.bin`（ignored build artifact）
- bytes：810688
- SHA-256：`175097C2E97C69CA7333CCA677BCF0E974AAD6549C0B2BE63CA0EE0E01E10358`
- Hardware tested: `NO`

## 15. 最终安全声明

本轮没有用模拟数据冒充实测，没有用“电压×时间求和”冒充电流或电荷，没有从
SPD1656 移植命令，也没有因研究“可能获得更多颜色”而放松任何门禁。所有未知硬件
值继续为 `null`；所有硬件阶段继续等待明确授权与前置条件。
