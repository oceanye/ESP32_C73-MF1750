# MF1750 明度构色与局部 HOLD 功能链 V1

## 目的

本轮不扩大色相枚举。目标是先验证静态照片真正需要的完整操作路径：

```text
干净白锚
  -> 单次历史构色
  -> 保留构色结果，不再重刷这些像素
  -> 切换已知兼容 LUT，仅局刷新区域
  -> 原区域局部 HOLD
  -> 从白屏重新构色，验证可复现性
  -> 独立 factory-OTP 白恢复
```

空间抖动、交错条纹和网点不计作颜色。CS1 与 CS2 分开判定；相同码、相同波形不自动代表
两侧光学结果相同。

## 在当前测试队列中的位置

用户要求先扩展功能、后扩展更多色相，因此下一轮真屏顺序固定为：

1. 将已经离线完成的 16-recipe 位置平衡灰阶／明度机制重新绑定到本轮 fresh 白锚；
2. 先回答是否存在单像素中性灰或同色相明度差；
3. 命中项优先进入 `POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1`：保留 G3 终态，J2 OFF
   换入只含 H1/H2 的 successor，不重做或覆盖候选格；
4. 若 16-recipe 机制没有命中，才把 V3 的 CS2 一次性历史明度信号作为 REVIEW 级 HOLD
   诊断输入，并执行本文五动作 `LIGHTNESS_HOLD_FUNCTION_CHAIN_V1`；
5. 在灰阶／明度、HOLD、重建和白恢复链路闭合前，不扩大色相枚举。

旧 `LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2` 的算法和固件实现可以复用，但它原来绑定的
W11 白锚已经被 V3 消费，绝不能直接执行；必须生成新的 campaign/contract/NVS/claim 身份，并
精确绑定当前 V3 factory-OTP white successor 的 COMPLETE、48MP retained review 和 relay-OFF
证据。

## V3 已确认的机制边界

`STABLE_CODE0_LUMA_LATIN_V3` 已在同一 boot 完成 L1--L4，每个 action 恰好一次
ARM、EXECUTE、driver 和可见刷新，无 retry、recovery 或 autochain。

同曝光 `-4` 的 48MP 复核结果：

- L3 后 CS2 的 8 个历史码中值跨度为 `7.059 L*`；
- 相同 active-code0 target 再刷一次后，L4 跨度只剩 `2.157 L*`；
- 跨度保留率 `30.56%`；
- controller-local centred 逐格 `|Delta L*| P95=4.647`，超过 `3.0` 门；
- 逐码中值最大偏差 `4.118 L*`，超过 `2.0` 门；
- 合格颜色、灰阶和明度层级仍全部为 `0`。

主报告：

`.test-output/hardware/MF1750_STABLE_CODE0_LUMA_LATIN_20260901_V3/`
`l3-l4-same-exposure-m4-controller-local-lightness-repeat-v2.json`

文件 SHA-256：
`c008fc1ec20fbc0db2e49153a1716af89c918445239b540f15eb517c6a69b4ae`。

该结果否定的是“在同一区域重复写相同最终目标仍保留历史明度”。它没有否定：一次构色后，
通过 PTLW 局部窗口让后续波形避开该区域，从而长期保留该光学终态。因此下一门应先测试
HOLD，不应继续对候选像素重复 target。

## V1 备选诊断主固件动作

已离线封印 fresh、固定输入、无运行时 payload 的 `LIGHTNESS_HOLD_FUNCTION_CHAIN_V1`。它只
针对 V3 一次性 CS2 REVIEW 信号，是 F1 无命中时的备选机制诊断，不得替代 F1 候选自身的
HOLD 资格。主固件只
包含五个手工独立 action：

| ordinal | 动作 | 传输 | 观察目的 |
|---:|---|---|---|
| 1 | L1 active source code7 | 双控制器完整 packed DTM | 固定源态 |
| 2 | L2 commented middle Latin C0--C7 | 双控制器完整 packed DTM | 写入 8 种历史 |
| 3 | L3 active target code0 | 双控制器完整 packed DTM | 形成一次性明度候选并拍 T0 |
| 4 | H1 active/code5 顶部探针 | 完整 code7 SRAM 预装 + 单次 inclusive PTLW + cropped DTM | 探针显色，同时 HOLD 128 个候选格，拍 T1 |
| 5 | H2 commented/code6 底部探针 | 完整 code7 SRAM 预装 + 单次 inclusive PTLW + cropped DTM | 切换 LUT、保留候选格与 H1，拍 T2 |

H1/H2 沿用已经真屏通过的 clean transport：

```text
完整 code7 SRAM 预装
-> 写一次 inclusive PTLW (0x83, PMODE=1)
-> 只发送窗口 cropped DTM
-> PON -> DRF 0x00 -> POF 0x00
```

不在 PON 后重复 PTLW，不发送 `0x86`，不写未知寄存器，不做 LUT 命令穷举，不切断刷新。
探针使用原 8x8 网格之外的上下白色边带，避免覆盖候选格；具体窗口必须在打包阶段经几何、
字节数、SHA-256、FNV 和非重叠门冻结。

## HOLD 判定

T0、T1、T2 必须使用同一 48MP 相机、同一机位、同一曝光和白平衡。只进行 controller-local
相对分析：

1. 128 个候选格在三个时点均能定位；
2. 内部没有空间抖动、条纹或混杂像素；
3. 候选格底边 `PRESENT=0`；`UNCERTAIN` 只可保留 REVIEW，不可 PASS；
4. T1/T2 相对 T0 的逐格 centred `|Delta L*| P95 <= 3.0`；
5. 每个历史码的中值最大偏差 `<= 2.0 L*`；
6. CS1、CS2 各自计算，不跨控制器平均；
7. H1 在 H2 后保持，且两个探针四边干净。

通过仅表示“一次构色结果可在这两个已知 LUT/PTLW 操作中被保持”，不会自动产生 qualified
灰阶或照片调色板条目。

## 可复现性门

若 HOLD 通过，再从独立 factory-OTP 白锚启动 fresh reconstruction successor，重新执行
L1--L3，而不是在原候选上再刷一次 L3。重建结果按相同 controller、历史码和位置比较：

- 码顺序相关性只作辅助；
- 逐码中值偏差和逐格 centred P95 都必须通过；
- 至少两次从白屏独立重建后，才把 recipe 标为 `REPRODUCIBLE_HELD_CANDIDATE`；
- 三次 fresh run、60 秒、10 分钟和长期保持属于后置可靠性，不阻塞框架验证。

## 白恢复与停止条件

主固件没有内嵌恢复。ordinal 5 后必须使用独立、绑定该终态的 factory-OTP white successor。
恢复后 relay/J2 切到 OFF，并用 48MP retained frame 只做“无明显色块、色斑、粗大条纹或中心
接缝”的相机可见审查；不宣称绝对白点或精密均匀性。

任一 action 出现 BUSY 超时、driver fault、控制器不同步、明显永久边线、异常发热或无法白恢复，
立即停止，不 retry、不 recovery、不自动进入下一 action。

## 后续顺序

1. 先执行 fresh F1 G1--G3 并拍 T0；
2. 若 F1 有候选，J2 OFF 换入只含 H1/H2 的 candidate-specific successor；
3. 执行 H1/H2，拍 T1/T2，裁决 F1 候选 HOLD；
4. 若 F1 无候选，才执行本文五动作 V1 作为 V3 REVIEW 信号诊断；
5. HOLD 命中后执行独立白锚和 fresh-white reconstruction；
6. 形成 controller-specific 明度 recipe并接入照片量化与多 LUT 调度；
7. 最后才扩大更多历史组合和色相枚举。
