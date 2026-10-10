# EC5 COLOR_LAB 单次刷入现场测试卡

日期：2026-08-10  
面板：MF-17506-M009F-T / `MF750M009T6420/1582643AGY44`  
目标：一次刷入，同一 boot 内连续验证直接八码与无抖动历史依赖色；正常动作之间不
reflash、不按 RESET、不切 J2。

冻结自包含包：
`.test-output/hardware/MF1750_EC5_COLOR_LAB_REAL_COMPARE_BOUND_20260809_V2_SELF_CONTAINED/`

- `firmware.bin`：791152 bytes，SHA-256
  `b67c160178ddc8a93b89161f710a4da6f570ce0c8a4822100429fcfbb7261c78`；
- `firmware.elf`：13253412 bytes，SHA-256
  `2e772bc65ca2971d18412981a5d7f33030885113fc10acd37df68680ba7a4956`；
- release：file SHA-256 `9121a5e244fb67923ccb6791cf4f20fbf3c840f46b8dc437fad36c43e93752d2`，
  canonical SHA-256 `190aee5f791b86abe8b19a02286e09f791efb25d48fe856eb385386de32c2132`；
- BIN app descriptor 内嵌 ELF SHA 与上述 ELF 精确一致。旧 V1 bundle 已标记 superseded，
  不得用于刷写或执行。

## 开始前

1. 当前已知状态应为 J2 OFF，屏幕保留 U04/U05 四块对照；ESP32 USB 状态现场确认。
2. 复核 3.3 V、CV、限流 1.0 A、空闲电流、温度和物理切断开关。
3. J2 OFF 时只刷一次冻结 COLOR_LAB BIN，并完成写后 digest、BIN↔ELF、固件 API、23
   action manifest、NVS virgin 和 GPIO 只读诊断；此阶段不得刷新。
4. 接通 J2 后复核 BUSY=1、RST/CS1/CS2=0。此后正常 action 之间保持 J2 接通。

## 高价值发现闭环（ordinal 1–5）

| # | 画面 | 现场核对 | 正常后续 |
|---:|---|---|---|
| 1 | WHITE | 当前四个蓝块完全消失、全屏白、无轮廓/残影 | 直接到 2 |
| 2 | U07 isolated | 左右各一个 64×64 块；左右一致、均匀、边缘清晰；记录主观颜色及与 U04/U05 的差异 | 直接到 3；5 min 可选 |
| 3 | WHITE | U07 两块完全清除，全屏白 | 直接到 4 |
| 4 | ATLAS 0–7 | 16 块（每码跨双 controller 各一次）；按外观归组，记录 U04/U07 是否与既有六码重合 | 直接到 5 |
| 5 | WHITE checkpoint | atlas 全部清除、全屏白 | 可在此暂停，或继续 6 |

atlas 本轮是 `non-blind descriptive`：preview 已被离线打开，不能冒充严格盲评。它仍可用
于双控制器一致性、alias 和直接可区分状态数量的技术判断。

## 无抖动历史依赖闭环（ordinal 6–11）

| # | 画面 | 现场核对 |
|---:|---|---|
| 6 | U04 six-state primer | 两侧六个小块位置/颜色一致，几何正常 |
| 7 | U04 target from six | 六个位置全部写 U04；观察是否因白/黑/红/黄/蓝/绿前态形成可重复的不同明暗或色调 |
| 8 | WHITE | 所有 U04 小块清除 |
| 9 | U07 six-state primer | 与 #6 同布局、同 MAP 忠实度 |
| 10 | U07 target from six | 六个位置全部写 U07；观察前态依赖、左右一致性和旧态轮廓 |
| 11 | WHITE checkpoint | 全屏干净白；完成第一轮 |

若 #7/#10 没有有意义差异，可在 #11 结束。若出现明确且左右一致的候选，再在同一固件
继续 round 2（#12–17）和 round 3（#18–23）验证重复性；无需重新编译或刷机。

## 每个 action 的最小回报

- 与参考几何是否一致；左右 controller 是否一致；
- 色调/明暗分组、均匀度、边缘、旧画面残留；
- 温度、电气是否正常、ESP32 是否重启；
- 出现异常时立即物理断开 J2，并停止后续 ordinal；禁止自动重试/恢复。

## 参考预览（先观察真屏，再按需打开）

- U07 isolated：`.test-output/hardware/MF1750_EC5_STAGE_A_PREVIEWS_OFFLINE_20260809_V1/U07/u07_pilot.preview.png`
- 八码 atlas：`.test-output/hardware/MF1750_EC5_EIGHTCODE_ATLAS_OFFLINE_20260809_V2_CORRECTED_PREVIEW/eightcode-atlas.preview.png`
- U04 primer/target：`.test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U04/u04_primer.preview.png`、`u04_target.preview.png`
- U07 primer/target：`.test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1/assets/U07/u07_primer.preview.png`、`u07_target.preview.png`

preview 中 U04/U07 使用定位伪色，不预测真屏实际色调；真屏几何与 raw/frame identity 才是
严格比较对象。

## 时间预算

- #1–5：约 3 min 纯刷新时间；
- #1–11：约 6.5 min 纯刷新时间；
- #1–23：约 13.5 min 纯刷新时间；
- 人工观察时间另计，30 min 保持观察默认不要求，若跳过则只得短期技术结论。
