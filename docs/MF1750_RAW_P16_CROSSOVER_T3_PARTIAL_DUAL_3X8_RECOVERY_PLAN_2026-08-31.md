# MF1750 RAW-P16 T3 固定机位局部双侧 3x8 筛查与恢复计划

> 状态：`PARTIAL ROI ACCEPTED / T3 V1 DIAGNOSTIC FAILED BEFORE CLAIM / ZERO VISIBLE REFRESH`
>
> 冻结时间：`2026-08-31 13:38 +08:00`

## 1. 当前现场状态

- 48MP 相机机位固定，左右两半屏同时可见；右下和底边不可用。
- relay COM14/channel1 最后独立 query 为 commanded `OFF`，不代表负载侧电气实测。
- 屏幕没有执行 T3，仍按双稳态保留 W3 clean white。
- ESP32 app-only 已写入并验证 T3 V1，但其首个 J2-OFF `/version` GET 连接被拒绝。
- V1 计数：`1 GET / 0 POST / 0 claim / 0 ARM / 0 EXECUTE / 0 refresh`。V1 diagnostic/action
  不得重放。

## 2. 局部证据模式

新模式 ID：`PARTIAL_DUAL_3X8_TOP_ROWS_V1`。现有 full-panel 模式保持原样，不放宽其语义。

```text
CS1: logical rows 0,1,2 x all 8 columns = 24 cells
CS2: logical rows 0,1,2 x all 8 columns = 24 cells
per frame = 48 cells
per controller/profile/code = 3 spatial replicates
three retained frames = 9 samples per controller/profile/code
```

当前 setup-only JPEG 投影的预览 block quads：

```text
CS1 ~= [(826,536),(1911,528),(1959,1328),(783,1368)]
CS2 ~= [(1999,527),(3006,520),(3140,1287),(2055,1324)]
```

这些坐标只用来证明方案可行，不是正式角点。每张 sealed JPEG 必须在 admission 时绑定
该图自身的 CS1/CS2 block quad。

## 3. 强制门

- capture sidecar 必须为 `partial_panel`，`full_panel_visible=false`、
  `full_panel_uncropped=false`。
- 两侧必须同时包含 rows `0..2` 和全部 8 列；缺侧、缺 code 或 controller 左右顺序错误均拒绝。
- 两个 quad 必须凸、不重叠、在 `4000x3000` 内，CS1 位于 CS2 左侧。
- 48 个投影 cell 必须全部在图内，最小投影边长 `>=20 px`。
- W3 的 48 个局部白样本全部 `L* >=25`。
- 白参考与三张 T3 之间 8 个对应 block 角点最大漂移 `<=30 px`；`<=12 px` PASS，
  `(12,30] px` REVIEW。
- exact camera path、mount、requested/effective settings 和尺寸必须全等；三张 T3 的
  capture ID、JPEG hash 和时间必须不同。
- 左右白场存在明显亮度偏差，每个 cell 仅能使用同侧同位置 W3 白基线做平场归一化。

## 4. 证据权限

可输出：

- 局部 48 格几何和三副本／三帧稳定性；
- 各 controller/profile/code 的同侧白归一化中心与左右 DeltaE 筛查；
- 选定 ROI 内的条纹、残留、失焦和裁切粗检。

不可输出：

- 64 格或四空间副本 PASS；
- 底边、第四行、全屏 seam 或屏外异常 PASS；
- full-panel/full-white camera seal；
- 绝对色值、qualified colour 或正式 profile-following 结论。

所有超出范围的项目必须写为 `NOT_EVALUATED_OUTSIDE_SELECTED_ROI`；没有新 partial human
schema 时，profile-vs-side 仍为 `NOT_EARNED`。

## 5. 下一次流程

1. relay 保持 OFF，以独立只读路线确定 ESP32 的 exact endpoint；不重试 V1 diagnostic。
2. 生成并审核 fresh T3 successor：保持同一 atlas/profile，但换新 route/campaign/action/NVS/output。
3. 在 relay OFF 下 app-only 写入，独立 verify，执行 fresh 4 GET。
4. 诊断全通过后才 relay ON；在 claim/POST 前检查 raw `BUSY=1`。
5. 只执行 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`，然后 relay OFF。
6. 顺序拍取三张 partial T3 retained frame，每张完成 `acquire -> admit` 后才拍下一张。
7. 离线产生 48-cell 稳定性／profile-code 筛查；不把它升级成正式颜色结论。
8. 独立安装并执行 W4 factory-OTP white，然后 relay OFF。partial 白图只作安全粗检；
   若要 full-white seal，仍需合格全屏证据或人工明确确认。

## 6. 停止条件

任一诊断、BUSY、claim、action 或 relay 门失败，立即命令／保持 relay OFF，不重试、不恢复、
不自动串联下一可见动作。未完成 T3 不得把 W4 记作“末端恢复”；本次因首 GET 失败已
满足停止条件。
