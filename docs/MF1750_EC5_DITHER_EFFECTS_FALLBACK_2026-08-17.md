# MF1750 factory-OTP 像素抖动备选上机方案

日期：2026-08-17

离线隔离重构更新：2026-08-18

## 结论

如果 runtime waveform 暂时不能安全激活更多单像素颜色，可以转入独立的
factory-OTP 空间抖色分支。完整基础套件是 **3 张目标图 + 3 次白屏恢复，共 6 次可见
action**；其中前两次“比例色块 → 白屏”已经是十次核心色彩筛选的第 9/10 次，因此若它们
已经 committed PASS，备选分支只新增 **4 次**，不得重放已消费动作。

本方案只研究相邻原生像素在观察距离下形成的知觉混色。它不改变 R20/R21、LUT、waveform、
VCOM、电压或时序，也不声称产生新的单像素电泳原色。

## 六次基础流程

| 备选次序 | 测试图 / 动作 | 主要观察 | 当前离线状态 | 安全停点 |
|---:|---|---|---|---|
| 1 | 已冻结 7×5 比例色块 | 7 组双色的纯 A、75/25、50/50、25/75、纯 B | 既有 compiled release PASS；也是核心第 9 次 | 否 |
| 2 | factory-OTP 白恢复 | 色块是否完全消失 | 既有 compiled release PASS；也是核心第 10 次 | 是 |
| 3 | 七组连续双色渐变 | 单调性、断层、颗粒、左右一致 | fixed-compiled 固件、adapter、暂存 release PASS；等待核心第 10 次白屏证据 | 否 |
| 4 | factory-OTP 白恢复 | 渐变是否完全消失 | 同一固定固件 ordinal 2；独立授权 | 是 |
| 5 | 综合效果图 | 暖/冷二维过渡、中性灰阶、六码大色块、1/2/4/8 px 细节 | 同一固定固件 ordinal 3；独立授权 | 否 |
| 6 | factory-OTP 白恢复 | 最终干净白屏 | 同一固定固件 ordinal 4；独立授权 | 是 |

若核心第 9/10 次已经完成，从本表第 3 次开始。若没有运行核心筛选，则按 1→6 顺序完整执行。
任何分支都不能自动续播。

## 测试图设计

### 比例色块

沿用既有 V1 固定图：两控制器半屏完全同构，7 组原生双色各有 5 个比例块。它回答“哪些
颜色组合在近看仍是点阵、约 1 m 看起来像新的中间色”，但不回答单像素是否具有新状态。

### 连续双色渐变

新增图在每个 512×600 半屏重复 7 条水平渐变：

1. 红→黄；
2. 黄→白；
3. 绿→黄；
4. 红→蓝；
5. 红→绿；
6. 绿→蓝；
7. 红→白。

每条从纯 A 精确过渡到纯 B，使用固定 8×8 Bayer rank mask，局部比例分辨率为 1/64；左右
半屏的布局和 mask 相位完全一致。重点不是预览中的 RGB，而是真屏上的视觉单调性、明显 banding
数量、周期纹理、颗粒尺度和左右控制器一致性。

### 综合效果图

每个半屏包含：

- 红/黄/白二维三色场；
- 蓝/绿/白二维三色场；
- 黑→白中性渐变；
- 带 2 px 黑框的黑、白、黄、红、蓝、绿大色块；
- 1/2/4/8 px 黑白细节条。

这张图用于判断“实际信息图/海报式内容能达到什么效果”，同时把渐变连续性、平坦区域均匀性、
边缘分辨率和控制器左右一致性放在同一画面中。

## 固定身份

- 渐变 frame SHA-256：
  `531306ff2f309ce8f85b76c851cbb90512b65f92c608ca5b0ae518920778f122`
- 综合图 frame SHA-256：
  `02351166adb9d52e36eaccef0b50360c7c74806608ab404b5a08b648f5dc0865`
- 白恢复 frame SHA-256：
  `91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`
- 新 bundle manifest file/canonical SHA-256：
  `30c5b81c9f9f806e9c7fc9e69b4f925be147ccde61cc163b16f373066234a983` /
  `78c5397d1cb596cfb864875bdf0884f3fee5e118415df3d7655301e17b070e94`
- 新 layout canonical SHA-256：
  `6916cec7b87d8ad7c80b44d6f9a1c95f556320a90ef2ad28da36319773bbf56c`

新增四个 action ID：

| 新增次序 | 角色 | Action ID |
|---:|---|---|
| 1 | `OTP_DITHER_PAIR_GRADIENTS` | `3fe8e7a26dd643fc4a6b0ff887dfca9f69fc869678338882d85df6d113ade9cf` |
| 2 | `OTP_WHITE_AFTER_GRADIENTS` | `2e885371bc2614700e88fa144032b0871030e79ac6b4577f9a7cc410055a4e33` |
| 3 | `OTP_DITHER_EFFECTS_CHART` | `e09e33aaa4302c1f706ff799567bd44d461e4198e72047a649f9d62978f6283a` |
| 4 | `OTP_WHITE_AFTER_EFFECTS` | `da37411abb0dbab31ce51da96a2a2929e51398d94a055c47d28ccdfe28a551a4` |

专用 compiled contract ID 为
`5efc7fabcde9d4a96e36eb8f8702b705d9cafc916999a7c5f3f3eb48f6720fe4`。P0 中绑定
RC2G `/api/frame` 传输候选的旧四个 action ID 已由本 fixed-compiled 合同取代，不得用于上机。

## 上机边界

### 既有比例色块对

沿用已经深验的 dither-atlas compiled release。只在 J2 OFF 下刷写一次；action 1 与 action 2
必须按该 release 的同 boot/无中间刷新合同分别授权和 claim，不能在两者之间 reset、reflash 或
换固件。

### 新增四次

已改为专用 fixed-compiled 固件，不再使用 RC2G `/api/frame`。2026-08-18 又把扩展声明和实现
移入专用 header/translation-unit wrapper；共享 `epd_driver.cpp/.h` 继续保持封存 SHA-256
`386acdd3...2f6c` / `3bbddfe8...2343`，扩展可以从当前源码独立重建，不再污染核心固件身份。
新 application BIN 为 789,088 bytes，SHA-256
`031c31badfcdde9067e7aeeee4e3fdd811f1955c169f92699d7b1604a59a66b1`；对应 ELF
13,251,496 bytes，SHA-256
`a6a1c488f26414c8ed6debcaea928fbcfc424da656067fb65464acf9172ef93d`。链接后门禁已解析
`kActions` 与 `DEE_IDENTITIES`，确认四个动作、三类帧、唯一 display 调用、唯一 setup 自检和 exact
BIN↔ELF app descriptor；固件没有 raw-frame、LUT/waveform、retry/recovery endpoint。

当前 staged release 11,438 bytes，file/canonical SHA-256 为
`14bc3568891b359a8a37c5adfb4911aff6ae37dfc5e44a0ca1efae01e04f6d5a` /
`62fd222ea3d026da27b8fbbc5d69c87e91ab5a366ca275d7b7c5423b86a3a03a`。它绑定固件、ELF、
面板、bundle、campaign 及“核心第 10 次 dither-atlas white”静态 action ID，但故意保持
`execution_eligible=false`：未来真实第 10 次的 result、人工 observation 和永久 claim 尚未发生。
旧 2026-08-17 V1 staged 包仅保留历史证据，不得用于新的 real release。

现场新增分支固定为：

1. 核心第 9/10 次完成并在干净白屏停点 finalization；不得重放；
2. 纯离线运行 `finalize-real`，把第 10 次的 exact result/observation/claim 封入 real release；
3. 经人工决定进入备选窗口后，J2 OFF，仅刷上述 exact application image 并做写后哈希；不擦
   NVS、bootloader 或分区表；
4. 同一 fresh boot 完成 J2-OFF `version→manifest→status→report`，0 visible refresh；
5. 人工重报电源、电流、温度、屏幕前态、监测和物理切断；
6. 每个 ordinal 分别使用 bodyless `/arm` 与 `/execute`：先永久 claim，再各允许最多一次 POST；
7. 每次 result 深验与人工 observation finalization 后才可进入下一项；四次之间保持同一 boot、
   不 reflash/reset、不做中间 refresh。ordinal 2/4 是白屏决策停点，不是自动续播点；
8. 禁止 retry、fallback、自动 recovery 或 autochain。任何 action 异常后永久停止本分支。

## 拍摄与裁决

每张目标图至少保留两种观察距离：20–30 cm 用于观察点阵/周期纹理，约 1 m 用于观察知觉混色。
相机固定机位、光源、曝光、白平衡和焦点；所有比较图必须使用同一设置。

严格 PNG 只把六码映射为名义 RGB，用于核对几何和像素配方，不是面板色度预测。建议记录：

- 色块：三个混合比例是否按视觉顺序排列，中间块是否形成稳定中间色；
- 渐变：是否单调、明显断层数量、颗粒/周期纹理、左右是否一致；
- 综合图：暖/冷场连续性、灰阶中性、色块均匀性、1/2/4/8 px 可辨性；
- 每次目标后的白恢复是否干净；
- 全过程温度、电流、ESP32 重启及电气异常。

仅凭肉眼可以形成“可用效果候选”。若要比较色域或生成正式颜色配置，仍需固定采集和色度测量。

## 当前 readiness

- 完整备选：3 目标 + 3 白恢复 = 6 次；
- 核心筛选完成后新增：2 目标 + 2 白恢复 = 4 次；
- 测试帧、严格预览、观察模板、动作身份和排程：PASS；
- 既有比例色块 compiled release：PASS；
- 新增 fixed-compiled firmware、链接后身份门、一次性 adapter：PASS；
- 新增 staged release：PASS，且正确保持不可执行；
- real execution release：等待未来核心第 10 次白屏 result/observation/claim 后离线 finalization；
- execution gate：未到；live authorization：0；设备/网络 I/O：0；可见刷新：0。

当前 V3 readiness file/ID/canonical：
`5c102d320cd6d97364b5dfa85a9c4148f48f818e0dd09f8c53b626cec53d7dee` /
`8f4a4850683465d2e64b1394888530316a3023aaa9acae7e32cd5e4bde4f87d6` /
`5ce179631132ec9edf24ce5c8c4649d09dabb9946d00f56352584379e0e4b911`。旧 V1/V2 readiness
仅保留为历史证据，已被本次 source-isolated fixed-compiled 路径取代。V3 仍明确
`future_core_action_10_white_evidence_available=false / extension_execution_release_ready=false /
execution_gate_reached=false / live_authorized=false`。

2026-08-18 source-isolation、扩展固件、staged release 和既有 atlas 身份门联合专项回归
`23 passed, 1 skipped`。本轮所有编译、门禁、暂存 release 和测试均为本地离线动作，未访问
设备网络、COM/USB，未 reset/flash/J2/refresh。
现场逐步命令和停止条件见 `docs/MF1750_EC5_DITHER_EFFECTS_OPERATOR_CARD_2026-08-17.md`。

本方案是条件式备选窗口，不自动追加到十次核心筛选。当晚是否增加这 4 次，应在核心白屏安全停点
重新决定并另开 fresh gate。
