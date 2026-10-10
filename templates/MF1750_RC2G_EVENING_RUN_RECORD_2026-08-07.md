# MF-1750 RC2G 晚间真屏记录

本表一份对应一次受监督会话。自动报告不代替人工电气和画面判断；人工画面判断必须
把“设备忠实度”和“算法画质”分开记录。

## A. 会话身份

| 字段 | 记录 |
|---|---|
| 日期、开始/结束时间 | |
| 操作者 | |
| 面板/驱动板 | MF-1750 Rev A1；R15 拆除；R16=0 Ω |
| ESP32 端口/IP | |
| 固件 build tag | |
| `firmware.bin` bytes / SHA-256 | |
| 室温/光线 | |
| 相机、距离、曝光、白平衡、焦点 | |
| 会话前保留画面照片 | |
| 最终 J2-P1 状态 | |

## B. 开场门禁

- [ ] J2-P1 在刷写/ESP32 重启期间物理断开。
- [ ] R15、R16、FPC、公共地和接线没有变化。
- [ ] 电源设为 3.3 V、CV、限流 1.00 A；物理开关可立即切断。
- [ ] RC2G binary bytes/hash 与离线构建记录完全一致。
- [ ] 断屏电源启动后 build/API/PSRAM/mapping 正确。
- [ ] fresh boot 为 job0/idle，且没有 completed diagnostic。
- [ ] 接通 J2-P1 后 3.3 V、CV、空闲电流、温度、声音和气味正常。

任一项失败：不要消费一次性刷新 claim；保持或恢复 J2-P1 断开并记录原因。

## C. 每个可见刷新

复制本节，每个 run 填一份。

### Run __：________________

| 身份/证据 | 记录 |
|---|---|
| 目的 | |
| campaign / cell ID（若适用） | |
| 候选目录/fixture | |
| candidate-risk 审计（edges / half imbalance / 放行结论） | |
| 对照 preview | |
| result directory | |
| attempt ID / claim SHA-256 | |
| 预期 prior job/op/frame FNV | |
| 预期 prior frame SHA / CS1、CS2 DTM FNV | |
| 预期 target job/op/frame SHA/FNV | |
| 预期 CS1/CS2 DTM FNV | |
| 实际 job/op/frame/DTM | |
| PON / DRF / POF / post-PSR / total ms | |
| BUSY idle-before-command/new-edge | PON: / DRF: / POF: |
| safe-finish 前 BUSY / 最终 BUSY | |
| 最终 RST / CS1 / CS2 | |
| network/report 状态 | |
| 刷新前/后照片文件 | |

电气观察：

| 时点 | 3.3 V | CV/CC | 电流 | L1/L2/板上温度或触感 | 异味/异声 |
|---|---:|---|---:|---|---|
| 刷新前空闲 | | | | | |
| PON/刷新期间峰值 | | | | | |
| safe-finish 后 | | | | | |
| 稳定观察 60 s 后 | | | | | |

设备忠实度（驱动/传输维度）：

- [ ] 全屏都被新画面覆盖，无旧图残留区或半屏漏刷。
- [ ] 左右方向、镜像、裁切、中央中缝与 preview 一致。
- [ ] 六个物理颜色位置正确，无错码或大片异常色。
- [ ] 细线/标尺/边框或测试图特征完整。
- [ ] `frame fidelity = PASS`。

若任一项失败，`frame fidelity = FAIL`；不要用“算法不好看”代替错屏描述。请写明
区域、形状、颜色和照片编号：

```text

```

算法画质（仅质量候选填写）：

| 指标 | 1 很差 | 2 | 3 | 4 | 5 很好 | 备注/区域 |
|---|:---:|:---:|:---:|:---:|:---:|---|
| 内容辨识 | | | | | | |
| 大尺度色调/色偏 | | | | | | |
| 渐变与断层 | | | | | | |
| 颗粒/块感/聚簇 | | | | | | |
| 条纹/周期纹理 | | | | | | |
| 边缘、细线和文字 | | | | | | |
| 中性灰 | | | | | | |
| 总体主观画质 | | | | | | |

允许出现 `frame fidelity=PASS` 且 `algorithm quality=POOR`；这表示驱动忠实显示了
不理想的算法输出，不是驱动故障。

本 run 裁决：

- [ ] `PASS_FOR_THIS_EXACT_RUN`：协议、timing、电气、忠实度均通过；算法画质另记。
- [ ] `STOP_QUALITY_ONLY`：协议/电气/忠实度通过，但画质不值得继续。
- [ ] `UNKNOWN_DO_NOT_RETRY`：网络/报告/证据不明或 runner 已 fail closed。
- [ ] `FAIL_CUT_POWER`：电气、时序或错屏异常，已实体断电。

裁决说明：

```text

```

## D. 会话收尾

- [ ] 所有 result/lock/raw job/raw diagnostic/raw GPIO 已保存。
- [ ] 若为算法比较，确认该候选从预注册的同一 MAP prior 开始，未与其他候选连续播放。
- [ ] 固定相机照片已按 run 编号保存，未自动曝光/白平衡漂移。
- [ ] 每个 evidence directory 已生成并复核 SHA256SUMS。
- [ ] 已记录最终空闲电流和温度。
- [ ] 监督会话结束时 J2-P1 已实体断开。
- [ ] 未对任何 unknown/failed attempt 自动重发或 recovery。

会话总裁决与下一步：

```text

```
