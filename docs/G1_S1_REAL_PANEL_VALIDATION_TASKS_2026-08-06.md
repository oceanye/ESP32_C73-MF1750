# G1 / S1 真屏验证任务（2026-08-06）

> 2026-08-07 更新：本文件保留 job2–job5 历史和长期 qualification 路线。本次
> RC2G 核心顺序已按
> [`MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)
> 执行完成：RC2G MAP job1 与 macro4 job2 均 nominal，frame fidelity 均通过；macro4
> 主观画质仍差。旧 RC2F 异常未复现但根因未关闭。其余四算法与 2×2 没有刷新授权。

状态：`RC2G MAP+MACRO4 EXACT ACTIONS PASS / MACRO4 QUALITY POOR / PREVIOUS TIMING ROOT CAUSE OPEN / FORMAL QUALIFICATION BLOCKED`

用户已在 2026-08-06 晚间监督完成固定 MAP 基准的单次真屏刷新，并在画面确认后断开
J2-P1（文档其他位置记为 J2-1）。随后在 J2-P1 断开时完成首个 G1/S1 候选的
non-displaying ingress，设备明确返回 `epd_action=none`。该候选之后取得独立单次授权并
执行真屏，但 job2 在 DRF 阶段超时，fail-safe POF cleanup 也未观察到 BUSY 回 idle；
用户立即实体断电。候选帧与双 DTM hash 均精确匹配，因此算法视觉结论保持
`inconclusive`，不得记为通过，也不得重试该授权。

冷却、TP1 放电和证据冻结后，另建的一次性固定 MAP 恢复 job3 完整通过。随后又以新的
两阶段授权执行低空间根因诊断 job4/op4；协议、画面、电流、温度和 GPIO idle 均正常，
裁定为 `NOMINAL_DIAGNOSTIC_PASS`。该成功 run 到达 POF/safe-finish 后，J2-P1 在继续
受监督会话中保持接通；这不是下一次刷新授权。纯软件测试不要求为了测试而切断 J2-P1，
但不得访问设备；硬件异常或监督会话结束时必须实体断电。当前没有任何下一次可见刷新
授权。本文件记录后续逐 run 任务和停止条件。所有硬件通用门禁以
[`RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md`](RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md)
为准；冲突时取更严格者。

## 0. 当前阻塞结论

显示器 v2 artifact 固定为 `offline/formal=false`，不能直接 enqueue 到真屏。真屏阶段
必须建立独立的 measured/qualified G1/S1 artifact gate，并绑定：

- calibrated 六色 palette 与混色 profile hash；
- 面板/驱动板、固件 build、mapping、波形与环境温度；
- 对应算法、intent、strength、seed、预算和保护选项；
- 真实输出 frame hash、设备 job、operation report 与安全收尾证据。

在该 gate 实现并审查通过前，只能做 T0–T2 和另行冻结、逐次授权的 experimental-only
诊断；已经消费的 job2、job3、job4 授权均不得复用。不能把下载的软预览 PNG 当作设备帧
上传，当前也没有新的可见刷新授权。

### 0.1 本次真屏事故、恢复与低空间诊断裁定

- `area-weighted-ordered-8x8` 候选：job2/op2，完整帧 FNV `0x657DB1B5`，双 DTM
  `0x43E97823` / `0xE8FA6243`；PON 180 ms 后 DRF 等待 60010 ms 超时，随后
  POF cleanup 再等待 30005 ms 仍未闭环。原 claim 和机器结果永久保留为
  `unknown_do_not_retry`；算法评价为 `inconclusive`；
- 固定 `map-orient-v1` 恢复：job3/op3，完整帧 FNV `0x9D04142D`，双 DTM
  `0xF26832DD` / `0xFE199FF5`；PON/DRF/POF/post-PSR 为
  181/21700/140/5 ms，总时长 34178 ms，协议与人工画面均通过；
- 恢复记录位于
  `.test-output/hardware/MAP_RECOVERY_AFTER_G1S1_RUN1_20260806/`，其中
  `RECOVERY-ADJUDICATION.json` 明确保持 `formal=false`、`hardware_qualified=false`；
- 恢复通过只证明已知 MAP 路径恢复正常，不能关闭高负载候选的 DRF/POF cleanup 根因，
  也不能自动授权下一算法；
- 低空间诊断 bundle：
  `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/`。manifest
  原始文件 SHA-256 为 `07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d`；
  frame SHA-256/FNV-1a 为
  `ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65` / `0xA9641618`，
  CS1/CS2 DTM FNV-1a 为 `0xCB085C03` / `0x9ABD749A`。当时 J2-P1 已在持续监督会话中
  接通；non-displaying ingress 返回 `epd_action=none`、没有刷新，设备 action/job
  保持不变；
- 可见诊断证据位于
  `.test-output/hardware/G1S1_LOW_SPATIAL_DIAGNOSTIC_RUN1_20260806_232200/`，attempt ID
  `38352ce6bc564530917c43099fe8d20a`。job4/op4 completed，PON/DRF/POF/post-PSR 为
  `181/21690/140/5 ms`，总时长 34169 ms；画面与 strict preview 一致，3.3 V CV、
  电流、温度和 GPIO idle 正常，J2-P1 在继续受监督会话中保持接通；
- 裁定 `NOMINAL_DIAGNOSTIC_PASS` 只支持全局终态直方图和全局 6×6 转移计数各自都不是
  单独充分原因。诊断同时降低控制器内部空间频率并平衡半屏负载，单次结果没有分离二者；
  row-major MAP-mask 分配不保留源图语义，画面难看是设计使然，不计画质；
- job2 算法评价继续为 `inconclusive`，DRF/POF cleanup 根因未关闭；job4 不产生 mixing
  algorithm qualification、formal/hardware qualification 或下一次可见刷新授权。

## T0：软件与候选冻结（现在可做，无设备 I/O）

1. 记录 Git HEAD、dirty status、Python/Pillow 版本和本任务文件 SHA-256；
2. 运行全仓 unittest、repository contract、JavaScript syntax check；
3. 用固定输入生成 10 算法软预览，保存原图 hash、profile hash、options、seed、预算、
   report hash、frame hash 和四张 preview hash；
4. 固定首轮对比算法：`atkinson`、`area-weighted-ordered-8x8`、
   `area-weighted-blue-noise`、`multicolor-dbs`、`overlap-aware-dbs`；
5. 若源码、profile、算法参数或任何 hash 改变，生成新的候选 ID，不复用旧证据。

建议固定四类输入：中性灰阶/肤色渐变、六色与混色色块、自然照片、细线文字与边缘图。
同一组 A/B 必须使用同一服务端归一化源、fit/rotation、intent、strength 和保护选项。

## T1：测量输入与模型资格（BLOCKED，等待仪器/采样）

1. 在 D65/2° 或有完整光源/几何记录的条件下测量白、黑、黄、红、蓝、绿纯色色块；
2. 按 2×2 起步、必要时扩展 4×4，测量覆盖二色和关键多色比例的混色色块；
3. 对每色独立估计光学扩散/串色核；无独立核时只能标 `experimental`；
4. 建立机器可读 profile，记录原始测量文件、仪器、校准、环境、聚合规则和 canonical hash；
5. 留出未参与拟合的 hold-out 色块，检查颜色误差、亮度偏差和模型残差。

没有分光测色仪时，可按现有安全门允许相机/RAW 相对标定，但结论必须保持
`experimental`，不得升级为正式 Lab profile。

## T2：ESP32/设备准备与面板电源边界（设备操作需用户当次明确授权）

纯软件测试、离线 bundle 生成和深验证不需要切断 J2-1，也不得访问设备。若要刷写 ESP32
或执行设备端无刷新检查，则严格执行 RC2F 任务包的 T0–T3：先确认 J2-1 实测断电且无
反向供电，冻结 firmware.bin 大小/hash，再只做 Wi-Fi/版本/状态/无刷新页面检查。此阶段
禁止调用任何刷新 endpoint，也不因“刷写成功”推断面板安全或色彩正确。

若 J2-1、TP1、公共地、R15/R16、FPC 或固件身份有任一不确定，立即停止。

## T3：建立独立真屏 artifact gate（软件任务，尚未实现）

新增路径不得修改 v2 的 offline 语义。它应当：

1. 只接受 allowlist 中、带原始测量 provenance 的 calibrated profile；
2. 把算法输出的 exact 307200-byte frame 与全部 G1/S1 子报告交叉绑定；
3. 默认不授权上传；qualification reviewer 对明确候选签署后才生成一次性 formal identity；
4. 复用 C4 preflight、短时 arm、单次 enqueue、job/report correlation 和 local-abort quarantine；
5. 任何 profile/panel/build/options/frame hash 变化立即撤销资格；
6. 自动化测试证明 synthetic profile、软预览 PNG、重签报告和陈旧 artifact 都无法上传。

T3 代码、测试和审查未完成前，T4–T6 保持 `BLOCKED`。

### T3X：受监督、非正式的一次性实验路径（已实现）

T3 的 measured/formal gate 仍未实现、仍为 `BLOCKED`。为在用户现场监督下执行候选和
根因诊断，新增了与正式路径完全分离的 experimental-only 路径：

- `tools/g1_s1_panel_candidate.py`：只离线生成固定 1024×600 同图候选；严格绑定 frame、
  四张预览、完整 simulation report、synthetic profile、算法参数以及固定 CS1/CS2 DTM
  hash。生成器没有屏幕刷新能力；冻结包只有在完整磁盘深验后才能选择执行
  `/api/diagnostic/frame-ingress`，且必须得到 `epd_action=none`；
- `tools/g1_s1_experimental_refresh.py`：只接受完整 offline candidate 和与
  `manifest.json` 文件字节完全匹配的 SHA-256 授权；任何网络前先原子写入不可复用的
  workspace 授权 claim 和 `ATTEMPT-LOCK.json`。claim 以 manifest 文件 SHA-256 为唯一
  身份，不能通过更换 result directory 重用；每个授权最多调用一次 `POST /api/frame`，
  网络结果不明或后续本地失败也禁止重发；
- 该路径的 candidate、lock 和 result 永远保持 `formal=false`、
  `hardware_qualified=false`、`hardware_tested=false`。人工真屏观察写入独立实验结果，
  不能回写或提升现有 v2/formal 资格字段。
- `tools/g1_s1_low_spatial_diagnostic.py`：只离线生成和深验证固定低空间诊断 bundle；
  `tools/g1_s1_low_spatial_diagnostic_refresh_once.py`：只接受该精确 bundle 和一次性授权。
  两者不改变任何混色算法 qualification，已消费的 job4 attempt 不得重试。

当前首个冻结候选：

```text
algorithm: area-weighted-ordered-8x8
seed: 1296445751
frame bytes: 307200
frame SHA-256: 28ce21501a93c667b81bf474e9811100c8d5ebb7116359e82ee081cebde07e25
frame FNV-1a: 0x657DB1B5
CS1 DTM FNV-1a: 0x43E97823
CS2 DTM FNV-1a: 0xE8FA6243
manifest file SHA-256: 88702d79b71ff1c901bd71f2315c3c0e7aeae8c31945f322d6be5f13c8ce272a
simulation report SHA-256: b8e822af02ca6c332a077052d78d5f2b9def81385b204016976551dbe214053a
ingress: PASS / epd_action=none / refresh job unchanged
visible attempt: job2 failed / DRF timeout / POF cleanup timeout
authorization: permanently consumed / do not retry
algorithm evaluation: inconclusive
```

低空间诊断冻结身份与结果：

```text
bundle: G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430
manifest raw SHA-256: 07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d
frame SHA-256 / FNV-1a: ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65 / 0xA9641618
CS1 / CS2 DTM FNV-1a: 0xCB085C03 / 0x9ABD749A
ingress: PASS / epd_action=none / action and job unchanged
run: G1S1_LOW_SPATIAL_DIAGNOSTIC_RUN1_20260806_232200
attempt: 38352ce6bc564530917c43099fe8d20a
visible attempt: job4/op4 completed / total 34169 ms
adjudication: NOMINAL_DIAGNOSTIC_PASS / no algorithm qualification / no next visible authorization
```

软件验证：2026-08-07 当前工作树最终全仓 532 项测试通过；固定 MAP recovery、低空间 generator/runner、
candidate/experimental-runner/frame-tool 聚焦测试均通过；repository contract、Python
compile、JavaScript syntax 和 diff check 通过。上述只放行已执行的一次受监督实验与一次
固定 MAP 恢复及低空间诊断，不解除 T3 formal gate。

## T4：单次真屏 A/B（条件满足后逐 run 授权）

当前 T4 仍因 job2 的 DRF/POF cleanup 事故暂停。不得直接按下列算法顺序继续，也不得把
MAP 恢复或低空间诊断成功解释成“可以承受任意高负载帧”。低空间诊断是“降低内部空间
频率 + 平衡半屏负载”的联合干预，只排除了全局终态直方图和全局 6×6 转移计数各自作为
单独充分原因；它没有分离空间频率与半屏负载，也没有关闭根因。

下一步只做源图保真的质量轨离线预览。若继续根因隔离，应另行设计保持每半屏转移分配的
空间重排或“高/低空间频率 × 平衡/不平衡半屏负载”对照；离线设计和审查均不构成上电、
设备访问或刷新授权。当前没有下一次可见刷新授权。

每次只选择一个固定输入和一个算法。若该硬件会话从断电状态开始，接通 J2-1 仍需用户
当次确认，再为精确冻结帧取得一次可见刷新授权；若设备已处于持续监督会话，且上一 run
已经 safe-finish/GPIO idle、电气和温度正常，则 J2-1 可以保持接通，下一 run 无需重复
“接通电源”授权，只需为该精确冻结帧取得一次新的可见刷新授权。帧授权不能跨 run 复用；
纯软件阶段和每个成功 run 之间都不要求周期性断电。建议顺序：

1. `atkinson` 作为参考；
2. `area-weighted-ordered-8x8`；
3. `area-weighted-blue-noise`；
4. `multicolor-dbs`；
5. `overlap-aware-dbs`。

每个 run 记录：候选 ID、源/profile/options/report/frame hash、面板与 build 身份、环境温度、
TP1/CV/电流/关键温度、完整 BUSY 时序、job ID、operation ID、完整/CS1/CS2 DTM hash、
刷新前后 RAW/照片及安全收尾。成功 run 到达 POF/safe-finish、确认 GPIO idle 且电流/温度
正常后，可在同一持续监督会话中保持 J2-1 接通以观察；这不授权下一次提交。发生任何异常
或监督会话结束时必须实体断电并等待冷却；不自动连续提交，不因网络超时重发。

## T5：评价与选择

在相同裁切、曝光、白平衡和观察几何下比较：

- hold-out 色块的 ΔE00、L*、chroma、hue 偏差；
- 灰阶中性、肤色、渐变断层和彩色颗粒；
- 3×3/7×7/15×15 尺度的低频色偏；
- 横纵/对角条纹、周期峰、同色聚簇、边缘串色与文字清晰度；
- monitor `model` 与实拍结果的残差。

先判断 profile/observation model 是否可信，再比较算法；不能用一个失配模型下的模拟分数
直接宣布算法胜出。没有合格测量链时只记录主观/experimental 结果。

## T6：通过条件与停止条件

某条算法只有同时满足以下条件，才可记录为“该候选真屏通过”：

- exact profile/panel/build/options/frame 身份完整；
- 设备 job、operation report、BUSY 和 DTM hashes 全部匹配；
- 电气、温度、画面、safe-finish/GPIO idle 和该 run 约定的最终电源状态均通过；
- 对照与候选使用同一测试合同，测量数据可追溯；
- 结论只限定到这组 profile、面板、波形、温度和算法参数。

出现 CC/OVP/OCP、ESP32 重启、异常热点/气味/声音、BUSY 缺失、hash/report 不匹配、
网络不明状态、永久色斑或证据丢失时立即实体断电并停止，不自动重试。任何一次通过都不
自动授权下一次刷新，也不证明相机闭环、快速波形、扩展颜色或其他研究路线完成。
