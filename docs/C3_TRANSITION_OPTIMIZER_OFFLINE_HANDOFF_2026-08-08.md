# C3 转移感知优化器离线交接（2026-08-08）

状态：`PARAMETRIC SOFTWARE COMPLETE / MEASURED INPUT + HARDWARE VALIDATION BLOCKED`。

本阶段只增加主机端确定性算法、报告和回归。没有访问 ESP32、HTTP、串口或面板，没有
生成 claim/授权，也没有改变 RC2G/N7 固件。实现入口为
[`host/transition_optimizer/`](../host/transition_optimizer/)，测试为
[`tests/test_transition_optimizer.py`](../tests/test_transition_optimizer.py)。纯离线入口为
[`tools/mf1750_transition_optimize.py`](../tools/mf1750_transition_optimize.py)，只接受本地文件，
没有设备地址、授权、claim、上传或刷新参数。

## 1. 已实现目标

目标函数严格记录为：

```text
J = alpha * CIEDE2000 感知误差
  + beta  * 归一化实测转移代价
  + gamma * 变化像素惩罚
  + delta * 已选择相邻同码的空间聚集惩罚
```

- `alpha` 控制源图颜色保真；
- `beta` 使用 6×6 实测 profile 中的光学误差、峰值电流、能量、BUSY、残影、温升和
  recovery failure，各分量先在同一 profile 内归一化，再按显式 component weights 合成；
- `gamma` 倾向保留已知旧码，减少 changed pixels；
- `delta` 是局部空间正则项，越大越惩罚与已选左/上邻居重复，不被写成普适画质改进；
- Floyd–Steinberg 与 Atkinson 两条状态感知误差扩散路径均可使用，tie 固定按物理码排序。

`beta=gamma=delta=0` 时直接调用原 C2 quantizer，frame/codes 逐字节完全退化为普通量化，
没有复制另一套基线算法。每个结果包含六码 counts、known-old 时的完整 6×6 transition
histogram、感知/转移/changed/spatial 四类观测量、frame SHA/FNV 和 canonical integrity。

## 2. 缺数据与旧帧未知语义

- 默认缺任何 transition profile 或 profile 未覆盖 36 格即拒绝；未测值不会被零填或插值。
- 调用方可以显式选择 `perceptual-only-unqualified`；此时逐字节走普通量化，并在报告中
  保留 fallback 和 `formal_input_eligible=false`，不得伪称用了转移代价。
- 旧帧未知默认拒绝 `beta/gamma`；显式 `conservative-worst-case` 时，每个候选取六种旧码中
  最大实测成本，transition histogram 与 changed count 保持 null，不伪造旧状态。
- 非物理码、错长度、非有限/负权重、非误差扩散 state-aware 模式全部 fail closed。

## 3. 防止跨面板拼接

`calibrated=true` palette 本身不含 panel serial，因此不能仅凭该标志与任意 transition
profile 拼接。`formal_input_eligible=true` 必须同时满足：

1. palette 已校准且有 calibration artifact；
2. transition profile 36/36 全实测；
3. old frame 逐像素已知；
4. `TransitionInputBinding` 的 palette canonical/calibration、profile canonical、panel serial、
   firmware binary、waveform 和人工 review artifact 全部匹配。

任何 binding 不一致直接拒绝；未提供 binding 仍可做离线描述分析，但 formal input gate 为
false。即使 formal inputs 齐全，`optimizer_output_hardware_qualified` 仍固定为 false，必须另做
真屏 A/B 和电气/残影裁决。

## 4. Pareto 而非单参数神话

`build_pareto_report()` 对调用方显式给出的权重网格逐项运行，比较感知误差、归一化转移
代价、changed ratio 和空间惩罚，列出全部 non-dominated points。报告固定
`selection=null`、`single_best_claimed=false`；最终权重只能由预注册规则或人工裁决选择。

当前 RC2G 使用固定全局 DRF waveform。即使 profile 的 `busy_ms_mean` 有差异，代码也固定
`busy_time_reduction_claim_allowed=false`：这里只能优化能量、变化量、闪烁/残影等代理，
不能声称缩短固定 BUSY。只有未来获得并验证 transition-specific/partial waveform 后，才可
另立合同研究刷新时间。

## 5. 当前验证与剩余门禁

聚焦回归覆盖普通量化逐字节退化、缺 profile 拒绝/显式降级、完整 6×6、known/unknown
old frame、高 change cost、histogram、跨 panel binding、重封安全标志和 Pareto 无自动胜者。
离线工具可闭包写出 `frame.bin`、`preview.png`、`report.json`、可选 `pareto.json` 和
`manifest.json`，并从磁盘重新读取、逐项校验尺寸、哈希、canonical integrity 与交叉引用；
`validate` 子命令只做深验证，不执行网络或设备操作。

本轮根侧专项结果为 `15/15 PASS`；与既有 C2/profile 邻接回归合计 `48/48 PASS`，Ruff、
compileall 和 diff check 通过。

剩余不是算法代码缺口，而是 N5 外部门：实测 D65/2° palette、完整 6×6 transition profile、
同 panel/build/waveform reviewed binding，以及后续逐项真屏、电气、相机和残影验证。取得这些
数据前，C3 只能输出离线候选和 Pareto 证据。
