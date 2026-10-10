# G1 / S1 混色与显示器模拟交接（2026-08-06）

> 2026-08-07 更新：10 条软件路径与四阶段预览仍是当前基线。macro4 job5 的真屏
> 忠实度与 strict preview 一致，但候选本身画质差且时序异常，不能提升算法资格。
> RC2G 已完成冷启动 MAP job1 与独立 macro4 job2：二者协议/timing/忠实度通过，
> macro4 候选画质仍为差；旧 RC2F 时序异常未复现但根因未关闭。完整证据和后续计划见
> [`MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)。
> 2×2 V2 是 offline audit only；严格指标正交未证明、无上传/刷新授权。

状态：`SOFTWARE MONITOR BASELINE COMPLETE / RC2G MAP+MACRO4 EXACT ACTIONS PASS / MACRO4 QUALITY POOR / ROOT CAUSE + FORMAL QUALIFICATION BLOCKED`

本交接覆盖 G1 抖动前色域映射、六码面积混色、S1 空间半色调优化，以及它们在
C4 浏览器应用中的离线软打样。它不构成刷写、上电、面板刷新或真屏色彩合格结论。

## 1. 当前完成范围

应用统一暴露 10 条确定性算法路径：

| 组别 | 算法 ID | 当前实现 |
|---|---|---|
| C2 基线 | `none` | 最近六色，不抖动 |
| C2 基线 | `floyd-steinberg` | Floyd–Steinberg 误差扩散 |
| C2 基线 | `atkinson` | Atkinson 误差扩散 |
| C2 基线 | `ordered-bayer-8x8` | legacy nearest-two Bayer 8×8 |
| C2 基线 | `hashed-threshold` | legacy seeded nearest-two threshold |
| S1 对照 | `blue-noise` | 真正 void-and-cluster 阈值，但仍是 legacy nearest-two 配比 |
| G1/S1 | `area-weighted-ordered-8x8` | 六码面积权重 + Bayer inverse-CDF 分配 |
| G1/S1 | `area-weighted-blue-noise` | 六码面积权重 + 六路去相关蓝噪声 |
| G1/S1 | `multicolor-dbs` | 六色 DBS + identity observation model |
| G1/S1 | `overlap-aware-dbs` | 六色多尺度 DBS + 重叠 Gaussian observation model |

其中 legacy Bayer、hashed threshold 和 standalone blue-noise 都明确标记为
`nearest-two` 对照，不能被解释成六码面积混色。后四条才是当前 G1/S1 主路径。

G1 软件核心还包括：

- 严格 profile schema、canonical SHA-256 和 synthetic reference profile；
- `relative-colorimetric`、`perceptual`、`saturation` 三种 rendering intent，及
  `faithful`、`photographic`、`vivid` UI 别名；
- tone mapping 与 XYZ 三维凸域压缩；
- `none`/`legacy` 字节兼容路径和 Q16 映射身份；
- 确定性的 2×2、4×4 六色面积配方求解器。

S1 软件核心还包括：

- 确定性 void-and-cluster rank tile；
- 3×3、7×7、15×15 重叠感知损失；
- 单像素 recolour、邻域 swap、纹理/方向/周期/聚类惩罚；
- evaluation、accepted、stagnation、time 与 cooperative cancel 预算；
- 白色、文字和边缘保护约束，且约束 mask/hash/count 写入并校验报告。

## 2. 显示器模拟链路

`python -u -m app.server` 启动仅绑定 loopback 的应用。v2 路径接收原始 PNG、JPEG
或 WebP，由服务端校验 MIME 与原始 SHA-256，处理 EXIF/ICC、显式旋转和 LANCZOS
归一化，然后发布四张由 report hash 绑定的 PNG：

1. `source`：服务端解码并归一化后的源图；
2. `mapped`：连续色调 G1 映射目标；
3. `final`：从实际 6-code 输出流重新渲染的最终六色图；
4. `model`：经过当前重叠观察模型后的模拟效果。

浏览器会重新计算四张 PNG 的 SHA-256 后才显示。页面按 163.84×97.20 mm 有效区
模拟 1024×600 面板的非正方形像素比例。

所有 v2 artifact 永远保持：

```text
offline_verified=true
formal_upload_authorized=false
protocol_verified=false
hardware_tested=false
```

因此 v2 页面不会启用 arm/refresh；离线结果不能靠修改标签升级成真屏产物。

## 3. 验证证据

- `python -m unittest discover -s tests`：2026-08-07 当前工作树最终 532 项通过；
- G1/S1/simulation 定向套件：68 项通过；
- C2 定向套件：29 项通过；
- application pipeline/server/web 定向套件：31 项通过；
- 1024×600 白场整屏软件 smoke：
  - `area-weighted-ordered-8x8`：5.719 s；
  - `area-weighted-blue-noise`：6.035 s；
  - 两者均为 307200-byte 合法 frame，仅含物理六色码，frame SHA-256 为
    `91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`；
- 真实 1024×600 v2 application artifact 封装测试通过，四张预览均存在并被报告绑定；
- 初始软件实现阶段未访问 ESP32；随后在独立受监督硬件会话中完成固定 MAP 基准单次
  刷新，用户确认画面完整、温度正常，并在断电后报告电流 0.001 A；
- 首个 `area-weighted-ordered-8x8` 候选先在 J2-P1 断开时完成 non-displaying ingress，
  随后经两阶段授权执行唯一一次真屏刷新。帧和双 DTM hash 精确匹配，但 job2/op2 在
  DRF 60010 ms 超时，fail-safe POF cleanup 再等待 30005 ms 仍未闭环；用户实体断电。
  原授权永久消费并保持 `unknown_do_not_retry`，算法视觉评价为 `inconclusive`；
- 独立固定 MAP 恢复 runner 在联网前绑定 job2 事故四文件、固定 MAP SHA/FNV、mapping
  和 workspace 全局 claim。job3/op3 的 PON/DRF/POF/post-PSR 为
  181/21700/140/5 ms，总时长 34178 ms，协议和真屏人工观察通过；用户随后断开
  J2-P1，TP1、电流、温度和断电 GPIO 闭环正常；
- 随后的低空间诊断 bundle 为
  `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/`，manifest
  原始文件 SHA-256 为 `07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d`。
  frame SHA-256/FNV-1a 为
  `ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65` / `0xA9641618`，
  CS1/CS2 DTM FNV-1a 为 `0xCB085C03` / `0x9ABD749A`；当时 J2-P1 已在持续监督会话中
  接通，non-displaying ingress 明确为 `epd_action=none`、未刷新且 job 不变；
- 一次性 attempt `38352ce6bc564530917c43099fe8d20a` 的证据位于
  `.test-output/hardware/G1S1_LOW_SPATIAL_DIAGNOSTIC_RUN1_20260806_232200/`。job4/op4
  completed，PON/DRF/POF/post-PSR 为 `181/21690/140/5 ms`，总时长 34169 ms；用户确认
  画面与 `strict-final.png` 完全一致，3.3 V CV、电流、温度及 GPIO idle 正常。成功操作
  到达 POF/safe-finish 后，J2-P1 在继续受监督会话中保持接通；
- 最终裁定为 `NOMINAL_DIAGNOSTIC_PASS`，只支持“全屏终态直方图”和“全局 6×6 转移
  计数”各自都不是 job2 故障的单独充分原因。该帧同时降低控制器内部空间频率并重分配
  半屏负载，一次结果不能分离二者。它按 row-major 对 MAP mask 分块，不保留源图语义；
  画面难看是诊断设计结果，画质评价为不适用；
- experimental runner 与 recovery runner 都不能通过更换结果目录重复消费授权，也不会
  改写 v2 的 `offline/formal=false` 语义。恢复通过不构成失败候选通过、根因关闭或
  measured/formal qualification。低空间诊断通过同样不改变 job2 的 `inconclusive`、
  不关闭根因、不产生算法 qualification，也不授权下一次可见刷新。

纯软件测试、离线 bundle 生成和深验证不要求为了测试而切断 J2-P1；它们不得访问设备。
受监督硬件 run 正常完成且确认 safe-finish/GPIO idle 后，可在同一持续监督会话中保持上电；
发生异常或监督会话结束时才必须实体断电，无人看管仍保持断电。

白场 smoke 不是照片性能基准。高唯一色照片会增加面积权重缓存和纯 Python DBS
耗时；DBS 的默认 UI 搜索预算上限为 16384 次 evaluation。

## 4. 主要实现入口

- `host/gamut_mapping/`：profile、mapper、面积混色与 G1 预览；
- `host/halftone_optimization/`：ordered/blue-noise/DBS/观察模型；
- `host/application/simulation.py`：10 算法统一入口与强报告校验；
- `host/application/pipeline.py`：v2 offline artifact；
- `app/server.py`：原图转换、状态锁和预览发布；
- `web/`：浏览器控制与四阶段预览；
- `tests/test_gamut_mapping.py`、`tests/test_halftone_optimization.py`、
  `tests/test_application_simulation.py`：核心回归。
- `tools/g1_s1_experimental_refresh.py`：已消费候选的非正式单次真屏入口；不得重试；
- `tools/mf1750_map_recovery_once.py`：已消费的固定 MAP 事故恢复入口；不得重试；
- `tools/g1_s1_low_spatial_diagnostic.py`：低空间、全局转移匹配诊断 bundle 的离线生成与
  深验证入口；
- `tools/g1_s1_low_spatial_diagnostic_refresh_once.py`：已消费的低空间诊断一次性真屏入口；
  不得重试；
- `.test-output/hardware/G1S1_AWORDERED_RUN1_20260806_212715/` 与
  `.test-output/hardware/MAP_RECOVERY_AFTER_G1S1_RUN1_20260806/`：失败与恢复证据。
- `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/` 与
  `.test-output/hardware/G1S1_LOW_SPATIAL_DIAGNOSTIC_RUN1_20260806_232200/`：低空间
  bundle 与 `NOMINAL_DIAGNOSTIC_PASS` 证据。

## 5. 尚未完成、不得误报的范围

- D65/2° 实测六色色板、混色色块及其受信 profile；
- 每种颜料/颜色独立的实测光学扩散核；当前默认是未标定共用 Gaussian；
- 非线性 mixture-sample 拟合；当前面积求解仍是线性 XYZ 近似；
- 真屏 G1/S1 formal qualification 与独立上传 gate；
- job2 高负载候选触发 DRF/POF cleanup 超时的根因仍未关闭；低空间诊断已经 nominal
  通过，但空间频率和半屏负载是联合干预，尚未彼此分离；
- 下一步只进入源图保真的离线画质候选与预览轨；当前没有下一次可见刷新授权，也不能把
  低空间诊断的难看画面计入任何混色算法评价；
- 相机/RAW 闭环、实拍误差项、模板替换、可微/PyTorch/GPU 路线；
- 面板、波形、温度与 transition-history 的联合模型。

晚些真屏测试按
[`G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md`](G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md)
执行，并同时遵守既有 RC2F/C4/C2 硬件任务包。只有真实测量和一次性硬件门禁通过后，
才能把某个具体 profile/算法/面板组合提升为硬件证据。
