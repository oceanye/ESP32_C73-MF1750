# MF1750 G3 候选专用局部 HOLD successor V1（2026-09-01）

## 目的与资格边界

本包只验证 `LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3` 的 G3 候选是否能在后续
局部刷新中保持。它不是新色相搜索，不重跑 G1–G3，也不授予颜色、灰阶或明度资格。
当前 `qualified_hold_colours=0`、`qualified_gray_levels=0`。

源门固定为：

- campaign `EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3`；
- contract `a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88`；
- G3 ordinal 3、action `f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee`；
- G4 结果必须不存在；只要 G4 文件出现，本包在任何设备请求前 fail closed。

离线封印时 G3 live evidence 尚未产生，因此 source gate 状态为
`PENDING_EXACT_G3_COMPLETE`；这不允许提前上机执行 H1/H2。

## 固件与动作

主固件只暴露两个手动动作，无 boot auto action、retry、fallback、recovery 或 autochain：

| 动作 | controller-local 窗口 | 目标码 | global header | 保留目标 |
|---|---|---:|---|---|
| H1 | `x=64..383, y=8..31` | C5 | active | G3 全部 128 格 |
| H2 | `x=64..383, y=568..591` | C6 | commented | G3 全部 128 格及 H1 |

G3 网格为 local `x=68..443, y=64..535`。两个探针均位于网格外的上／下白带，
互不重叠，且 `x+width=384<400`，不会覆盖 recipe 0/1 或其他候选副本。

每个 controller 的固定 transport 为：

```text
full code7 DTM preload (153600 bytes, no refresh)
-> one inclusive PTLW 0x83
-> cropped uniform DTM (3840 bytes)
-> PON
-> DRF 0x00
-> POF 0x00
```

H1/H2 的 PTLW payload 分别为 `0040017f0008001f01` 与
`0040017f0238024f01`。禁止 post-PON PTLW、CDI、BTST2、`0x86`、运行时坐标／
目标码输入、自动连锁及同一 action 重试。

## 最短真屏顺序

1. 完成 V3 G1→G2→G3；不得执行 G4。
2. 保持 G3 光学终态，J2 OFF，app-only 刷入本主固件。
3. runner 深验精确 G3 COMPLETE 及 G4 缺失，再由人工触发 H1。
4. 拍摄 T1；确认 128 个候选格未被重画、顶部探针边界干净。
5. 人工触发 H2；拍摄 T2；确认候选仍保持、H1 仍保持、底部探针边界干净。
6. 默认以 H2 COMPLETE 为源，J2 OFF 后 app-only 刷入独立 factory-OTP white
   successor；其白动作仍需人工触发，绝不自动恢复。
7. 若人工在 H1 后明确停止，white runner 只有带
   `--confirm-explicit-h1-stop` 才接受 H1 COMPLETE；默认路径拒绝 H1。

HOLD PASS 只表示 camera-relative 的候选保持证据可进入 fresh-white reconstruction；
不表示绝对白点、面板均匀性、controller 等色、灰阶或明度已经资格化。

## 封印身份

- 主 contract：`329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229`
- H1 action：`366e5e3f337ec2cbe713f906af0f79a083e531de836e80b9b38066c7951255f5`
- H2 action：`ba7557595d9780f8ef0354abf0083b43735b5a642411aa63ce08a247f40e253c`
- white contract：`79ac7bae08b912cdcbf3d959029d56c740407275ef70c91de738b8205dcaa433`
- white action：`934330c22eb1057c7595c5db6711bfcbc7647291e56f5bd8acd059aa6a65e21d`

旧 `LIGHTNESS_HOLD_FUNCTION_CHAIN_V1` 五动作固件只保留为 fallback diagnostic，不是本
候选专用路径的执行固件，也不得替代 G3 精确 source gate。
