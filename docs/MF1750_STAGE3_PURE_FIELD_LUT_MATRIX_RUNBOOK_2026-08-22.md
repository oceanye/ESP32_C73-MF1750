# MF1750 Stage-III 纯场 LUT 集中测试手册

状态：`OFFLINE BUILT / REFERENCE-FIRST / NOT LIVE-AUTHORIZED`

本手册只安排离线已经构建并封存的候选。当前现场仍是驱动板断电、全白、ESP32 在线且操作者离场；本轮没有操作继电器、设备网络、COM/串口、刷写、复位或刷新。

## 1. 证据优先级

后续不再把所有结构猜测视为同等候选，固定按以下顺序：

1. 本项目 exact-chip 资料中实际出现过的完整 535-byte SPD1657/E2802 表；
2. 已有实测路径及其最小结构对照；
3. 相近 Solomon 三位像素码/LUT 结构只用于约束搜索，不复制地址、长度或电压参数；
4. 无 ABI 依据的 byte mutation、寄存器盲扫和未知命令保持禁止。

本地 exact-chip 样例包含两份完整 535-byte 表：一份为活动 `wf_data`，另一份为完整但被注释的表。后者只能称“完整 legacy 候选”，不能声称其具体面板批次、温区或用途已经确认。

## 2. 第一优先：legacy 535 完整表

每个 treatment 一屏同时显示：

- CS1：完整活动 535-byte 表，像素码 0..7；
- CS2：完整注释 535-byte 表，像素码 0..7；
- 总计 16 个同态纯色端点；
- 128×300 px 纯色区，无白缝、边框或空间抖动。

候选如下：

| 序号 | 候选 | 共享全局头 | CS1 / CS2 |
|---:|---|---|---|
| 1 | L535_ACTIVE_GLOBAL | 活动表 header 的 PWR/PLL | 活动完整535 / 注释完整535 |
| 2 | L535_COMMENTED_GLOBAL | 注释表 header 的 PWR/PLL | 活动完整535 / 注释完整535 |

两个 treatment 共 32 个端点，另有两个独立 factory-OTP white recovery，最多四次可见刷新。这是两个“一屏两控制器对照”的 waveform 组合，不是 32 套独立调色盘。

实现仍沿用本项目已验证的双控制器安全骨架：写入所选共享 PWR/PLL、`E9`、R20 前535字节，并给 R21 发送704字节 `FF`。它没有照搬 legacy 工程完整初始化序列，也没有启用该工程里的其他命令。因此这是“完整表 payload 的受控参考实验”，不是对 legacy 工程行为的逐指令复刻。

## 3. 第二优先：原 pure-field 矩阵

每个 treatment 同样给出 CS1/CS2 各8个像素码，总计16个端点。

| 序号 | 候选 | R20/R21 payload 假设 | 全局头 |
|---:|---|---|---|
| 1 | M0_H20 | R20=源首535，R21=FF×704 | WF20 |
| 2 | M0_H23 | 同上 | WF23 |
| 3 | H1_H20 | R20=源首535，R21=源[95:799] | WF20 |
| 4 | H1_H23 | 同上 | WF23 |
| 5 | H2_H20 | R20=源首535，R21=FF×440+源尾264 | WF20 |
| 6 | H2_H23 | 同上 | WF23 |
| 7 | H3_H20 | R20=完整799，R21=FF×704 | WF20 |
| 8 | H3_H23 | 同上 | WF23 |

H3 与已经上屏且未发现稳定新色的路径最接近，可作为控制或跳过。M0 比 H1/H2 更接近本地 legacy 535+FF 写法，优先于 H1/H2。H1/H2 是结构性拆分假设，证据最低，固定最后执行。

## 4. 已封存固件与 release

共同文件：

- 驱动：`src/ec5_dual_r20_h20_driver.inc`
- 一次性运行器：`tools/mf1750_pure_field_matrix_once.py`

reference-first 分支：

- 配置：`platformio.reference_535_matrix.ini`
- 候选：`src/ec5_reference_field_candidate.inc`
- 生成器：`tools/mf1750_spd1657_legacy_reference_include.py`
- 生成 include：`src/generated/spd1657_legacy_535_reference.inc`
- release：`.test-output/offline/MF1750_STAGE3_REFERENCE_535_MATRIX_20260822_V10/release.json`
- release canonical SHA-256：`ce88cafa4e56159a722c48327f006dac0d726419487a31b28f157b3a60928aaf`
- generated include SHA-256：`cb40342fb212e232d1cfe789f60ccba9823bb0e35148f5cf916681e0c8991881`

原 pure-field 分支：

- 配置：`platformio.pure_field_matrix.ini`
- 候选：`src/ec5_pure_field_candidate.inc`
- 打包器：`tools/mf1750_pure_field_matrix_pack.py`
- release：`.test-output/offline/MF1750_STAGE3_PURE_FIELD_MATRIX_20260822_V5/release.json`
- release canonical SHA-256：`638a9a45020079aab7cb173012da6ebf9558231cefacd9a5e356640692407967`

当前共享核心驱动 source SHA-256：`b7da0a241781559a9faba490a31f73346b0ef00b31a08374829ec17403dd9749`。

总计已经离线准备：

- 10 个 treatment 屏幕；
- 10 个独立白恢复；
- 160 个端点观察；
- 最多20次可见刷新。

“160端点”只表示观察位置数；本批共有10个屏幕级候选，每个控制器在一次刷新中仍只共享一套 waveform。

## 5. 建议真屏顺序

局部 HOLD 仍先于 LUT，只先运行 `accumulate`。若 HOLD 结果没有造成停止条件，LUT 顺序固定为：

```text
L535_ACTIVE_GLOBAL
→ L535_COMMENTED_GLOBAL
→ M0_H20
→ M0_H23
→ H3 仅按需作控制
→ H1/H2 最后
```

每项严格采用：

```text
app-only flash + independent verify
→ J2-OFF GET-only identity/READY
→ 操作者在场后允许 J2 ON
→ treatment：一次 ARM + 一次 EXECUTE
→ 人工裁决
→ 单独 white 固件 app-only flash + verify
→ white：一次 ARM + 一次 EXECUTE
→ 人工确认干净白
→ 仅在 no_new_color 时进入下一候选
```

裁决规则：

- 均匀、稳定且肉眼明显不属于已有色族：`suspected_new_color`；完成白恢复后停止矩阵，优先做重复和左右互换复核。
- 条纹、交错、边界混色、刷新过程瞬态橙或仅亮度变化：`no_new_color`；白恢复后再推进。
- 不自动串行；摄像头闭环尚未启用。

## 6. 固定安全轴

```text
SPI = 1 MHz
pixel codes = 0..7 only
raw frame ingress = false
raw LUT ingress = false
unknown commands = false
partial/window = false
VCOM/high-voltage write or sweep = false
OTP/NVM write = false
mid-refresh power cut = false
retry/recovery/autochain = false
```

相近 SPD1656 的公开资料表明其3-bit RAM code为0..7并索引八个 LUT，因而代码8..15不进入优先枚举；但其 R20/R21 长度、window 和 PartialRAM 地址不作为 SPD1657 合同。

## 7. 离线验证

- reference 4/4 PlatformIO 环境：SUCCESS；
- 原 pure-field 16/16 环境在共享源码更新后全部重建：SUCCESS；
- generator、reference 固件契约、pack/runner、兼容回归：`95 passed`；
- Ruff：PASS；`py_compile`：PASS；
- 本轮 0 relay/device-network/COM/serial/flash/reset/visible refresh。

## 8. 现场前诊断修订

首次 `L535_ACTIVE_GLOBAL` 上机只读诊断在任何 claim/POST/刷新前发现 host runner 仍把
reference 固件的 CS1/CS2 标签硬编码成旧 `WF20_25/WF23_25`。V5 仅修订验证器：

- reference treatment 必须报告 `CS1=LEGACY_ACTIVE_535`、
  `CS2=LEGACY_COMMENTED_535`；
- 两份535表没有文件名温区语义，version 中的哨兵范围固定核对为 `-128/127`；
- 原 pure-field 候选仍继续要求 `WF20_25/WF23_25`，不放宽；
- 固件 BIN/ELF、动作ID、payload、帧、NVS和电气参数均未改变。

随后V5首次treatment在唯一ARM处由固件以`intent_missing_or_mismatch`拒绝；只读报告证明
`execute=0 / driver=0 / visible refresh=0`，面板仍为干净白。根因是共享host context继承了
旧empirical-H3意图字符串，而pure-field固件要求独立的PURE_FIELD字符串。该失败action与
claim永久封存，绝不重试。

V10最终修订并验证：

- ordinal1绑定`ARM_ONE_FIXED_PURE_FIELD_CANDIDATE_NOT_HARDWARE_AUTHORIZATION`与
  `EXECUTE_ONE_FIXED_PURE_FIELD_CANDIDATE_ONCE`；
- ordinal2仍绑定factory-OTP white专用意图，未被改写；
- `L535_ACTIVE_GLOBAL` treatment轮换为build V2、NVS=`pflga2`、新descriptor/action；
- treatment BIN=`797520 bytes / 83ab21f3...0f63f2`，ELF=`13264120 bytes /
  be62d3b9...f79889`；
- pure-field frame/双DTM FNV改为由当前release上下文显式绑定，避免继承旧atlas数值；
- 增加只读terminal reconciliation，只允许已消费claim、同boot、设备terminal COMPLETE且
  ARM/EXECUTE/driver=`1/1/1`时封存，不能触发第二次mutation；
- reference 4/4与原pure-field 16/16重建SUCCESS，最终定向`19 passed`、Ruff/py_compile PASS。

V4–V9均只保留历史证据，不得继续用于现场runner；V10是封存本轮结果的唯一reference-first release。

## 9. 首个reference-first真屏结果

`L535_ACTIVE_GLOBAL` V2只执行一次ARM+一次EXECUTE；设备端terminal COMPLETE，1 driver，
R20/R21、frame/双DTM、mapping/sequence、PON/DRF/POF与safe-finish均PASS。照片中的16个
128×300大纯场无空间抖动；至少可见橙棕、酒红/粉红、米肤、深靛/紫黑、黄绿等扩展
候选，故裁决为`suspected_new_color`，未作绝对色度资格推断。

随后独立factory-OTP white recovery一次成功，操作者确认“白了”，relay/J2 OFF。按停止规则：

- 不推进`L535_COMMENTED_GLOBAL`或其余未互换候选；
- 优先复现当前active-header调色盘并标定码0..7；
- 将runtime LUT与已验证PTLW地址窗口组合，分别验证同盘局部HOLD和跨盘局部HOLD；
- 当前只证明local addressing PASS，既有factory-OTP测试中的universal HOLD仍FAIL，不能宣称
  已经支持反复局部刷新叠加到256色。
