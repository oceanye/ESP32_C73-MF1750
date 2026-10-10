# MF-1750 RC2G 白天开发与晚间真屏 Campaign

状态日期：2026-08-07。白天阶段不访问 ESP32、COM8、设备 HTTP 或面板；当前
J2-P1 保持物理断开。当前汇总优先查看 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md)；本文是
晚间逐项执行的主 runbook，旧 RC2F 任务包只作历史证据。

## 0. 2026-08-07 晚间执行结果

N0 核心会话已完成，最终 J2-P1 已由用户实体断开：

- 精确 RC2G binary 已刷入并由 esptool 校验；build/API/PSRAM/mapping/fresh job0 通过。
- MAP job1/op1：total/PON/DRF/POF/post-PSR = `35006/180/22511/141/5 ms`；
  协议、BUSY edge、GPIO、电气和用户报告的画面忠实度全部通过。
- macro4 job2/op2：`35017/181/22521/141/5 ms`；协议、BUSY edge、GPIO和电气通过，
  用户确认与 strict preview 完全一致，因此 frame fidelity PASS；候选画质主观评价为差。
- 昨晚 RC2F macro4 job5 的 `89049/37110/39621 ms` 异常在本次 RC2G 序列中未复现；
  这不等于已定位旧异常根因。
- 断开 J2 后 raw GPIO 为 BUSY/RST/CS1/CS2=`0/0/0/0`；post-RST BUSY 只作信息证据。
- 证据目录：
  `.test-output/hardware/RC2G_MAP_BASELINE_20260807_200637/` 与
  `.test-output/hardware/G1S1_MACRO4_REDISPLAY_20260807_201203/`。

随后独立完成 N1 low-balanced 成对 pilot：

- N1 MAP primer job1/op1：单 POST，`35016/180/22521/141/5 ms`，协议、电气和 MAP
  忠实度通过；result SHA-256
  `93d57feed9565344e20d10016977be8fc4754fbec09619316e96a8efed71f26a`。
- N1 low-balanced job2/op2：单 POST，`35016/180/22521/141/5 ms`，协议、电气和
  strict-preview 忠实度通过；result SHA-256
  `0297015a4e6ad04a85435e7fe10cc3c75678be9811c76f82695da3d11ed37e0e`。
- 两张之间 ESP32 未重启、J2 未断开；用户确认目标画面与严格预览一模一样，观察完成后
  已物理断开 J2。证据目录为
  `.test-output/hardware/RC2G_N1_LOW_BALANCED_MAP_PRIMER_20260807_215617/` 与
  `.test-output/hardware/RC2G_N1_LOW_BALANCED_PILOT_20260807_220545/`。
- 一次 target `/api/job` 只读轮询曾超时，随后读取同一 job2 成功；帧 POST 没有重试或
  recovery。现场结论由用户观察支持，本轮未留存固定曝光真屏照片。

N0+N1 共完成四个 RC2G exact action；Q1--Q4、其他 2×2 cell 和其他可见刷新仍无授权。

## 1. 当前结论

主机算法和显示器模拟的软件路径已经实现：五条 C2/legacy 基线、一条 legacy blue-noise
对照，以及 `area-weighted-ordered-8x8`、`area-weighted-blue-noise`、
`multicolor-dbs`、`overlap-aware-dbs` 四条 G1/S1 混色/优化路径。四阶段
source/mapped/final/model 预览、六码帧、hash 绑定和离线深验证都存在。

这不等于整个系统已经完成。RC2G 的 N0 与 N1 exact action 已验收，但 Q1--Q4 真屏、
算法公平比较、D65/2° measured palette、混色色块和每色光学核仍未完成。网络认证、
远端 cancel、持久 job 历史、参数化扫频、快速波形、随机照片流水线和 Rev B 也仍是独立
后续任务。

昨晚 macro4 job5 的裁决是：精确 job5/op5、frame/DTM hash 和完整序列成立；但
PON=37110 ms、DRF=39621 ms、total=89049 ms 明显偏离约
181/21700/34170 ms 的已知正常基线。用户报告真屏与 strict preview 一致，因此
`frame fidelity=PASS`；“不是一张好画面”属于算法/候选画质关注，不是错屏证据。
该 attempt 和旧授权永久消费，算法仍不合格、不重跑旧 action。

## 2. 白天放行包（已完成）

- RC2G build：
  `MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07`
- Driver API：`MF1750_R16_CASCADE_V3`
- 本地 `firmware.bin`：815664 bytes；SHA-256
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`
- 构建记录：[`RC2G_BUSYEDGE_OFFLINE_BUILD_2026-08-07.json`](RC2G_BUSYEDGE_OFFLINE_BUILD_2026-08-07.json)
- RC2G 新证据：PON/DRF/POF 命令前 idle、命令后新 BUSY assertion、返回 idle、
  safe-finish 前后 BUSY 和最终 BUSY/RST/CS1/CS2。
- 冷启动 MAP job1/op1 一次性 runner：`tools/g1_s1_rc2g_map_baseline_once.py`。
- 独立 macro4 job2/op2 重显 runner：`tools/g1_s1_macro4_redisplay_once.py`。
- 通用 RC2G 质量候选单次 runner：`tools/g1_s1_rc2g_quality_refresh_once.py`；它只说明
  单次 claim/协议/取证路径已经实现，不构成 Q1--Q4 的真屏放行。
- N1 专属两阶段 runner：
  `tools/g1_s1_rc2g_n1_low_balanced_map_primer_once.py` 与
  `tools/g1_s1_rc2g_low_balanced_pilot_once.py`。两者的软件聚焦/联合检查与 N1 真屏均已
  通过；primer/target fixed claims 已永久消费。该完成状态不放行 Q1--Q4。
- 昨晚证据裁决与 SHA 清单：
  `.test-output/hardware/G1S1_MACRO4_QUALITY_RUN1_20260807_004650/`。
- 2×2 V2 离线审计：
  `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2/`；它明确
  `strict_metric_orthogonality_proven=false`、`upload_authorized=false`。该 bundle 本身仍
  无上传能力；第 5 节新增的 N1 target runner 只是对 byte-identical `low-balanced` 的
  单一 exact-action override，其他三格仍无刷新 runner 或授权。

N0 收尾时的全仓 532 项 unittest、repository contract、Python compile、JavaScript
syntax、PlatformIO build 和 diff check 全部通过；重构建后的 binary 字节数/hash 与本节
固定值一致。N1 执行前全仓回归为 556 项通过；最终 request-audit 修正后的四组聚焦测试
为 56/56 PASS，本轮最终全仓回归为 558/558 PASS；repository contract、compileall、
JavaScript syntax、diff check 与 PlatformIO build 也通过。任何后续刷写前仍须现场再次
计算 binary hash；不一致就
停在软件阶段。

## 3. 电源规则

1. 纯软件、预览、文件 hash、GET 型检查不要求反复切断 J2-P1。
2. 刷写或重启 ESP32 时 J2-P1 保持断开，避免启动期间 GPIO 未受控。
3. RC2G 断屏电源启动检查通过后，只接通一次 J2-P1。
4. 成功 run 已到 safe-finish、RST/CS1/CS2 低且电气/温度正常时，可在持续人工监督下
   保持 J2-P1 接通；下一张帧仍需新的精确授权，但无需例行断电。
5. 网络状态不明、timing 超界、hash/report 不符、错屏、CC/限流、掉出 CV、异常温升、
   异味/异声、ESP32 重启或会话结束时，立即实体断开 J2-P1。
6. RST 已拉低后的 BUSY 原始值可为 0 或 1；只要 trace 已证明 safe-finish 前 BUSY idle，
   单独的 post-RST `busy=0` 不是故障或断电理由。

## 4. 晚间核心会话：最多两次可见刷新（已完成）

今晚核心目标是先验收 RC2G 的证据链，再回答 macro4 时序能否正常重复。不要把根因 2×2
或四条质量算法直接追加到同一核心会话。

### H0：固定拍摄与物理开场

J2-P1 保持断开。人工确认：R15 拆除、R16=0 Ω、FPC/公共地/接线无变化；电源为
3.3 V、CV、限流 1.00 A；物理开关可立即切断。相机正对有效区，固定距离、焦点、
曝光、白平衡，关闭 HDR/夜景/自动滤镜；先拍当前保留画面。

失败条件：接线变化、公共地不确定、电源模式不对、急停不可用。失败时不刷写。

### H1：J2 断开状态刷入 RC2G

先复核：

```powershell
$expected = "9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772"
$actual = (Get-FileHash -Algorithm SHA256 `
  .pio\build\esp32-s3-devkitc-1\firmware.bin).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "RC2G firmware hash mismatch: $actual" }
```

用户明确允许刷写后，才执行：

```powershell
C:\Users\Ye\.platformio\penv\Scripts\platformio.exe run `
  -t upload --upload-port COM8
```

刷写后 J2 仍断开。核对串口/HTTP build、API、1024×600、1 MHz、PSRAM、mapping；
必须是 job0/action none/state idle、无 completed diagnostic、RST/CS1/CS2 低。此阶段不做
frame ingress，也不调用任何刷新 endpoint。

失败条件：binary/hash/build 不同、刷写失败、重启循环、job 非 0、已有 completed report、
mapping/PSRAM/API 不符。保持 J2 断开并停止。

### H2：接通一次 J2-P1

用户接通后报告：3.3 V、CV、空闲电流（既有参考约 0.001 A）、温度、声音、气味均正常，
并确认物理开关可随时切断。通过后继续保持监督，不在正常软件步骤之间反复断电。

### E1：RC2G MAP job1/op1 基线

预期身份：

| 项目 | 固定值 |
|---|---|
| Preview | [MAP_ORIENT_V1_reference.png](../.test-output/MAP_ORIENT_V1_reference.png) |
| frame SHA-256 | `1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36` |
| frame FNV-1a | `0x9D04142D` |
| CS1/CS2 DTM FNV-1a | `0xF26832DD` / `0xFE199FF5` |
| target | job1 / operation1 |

精确授权字符串：

```text
AUTHORIZE_ONE_VISIBLE_RC2G_COLD_BOOT_MAP_ORIENT_V1_BASELINE_JOB1_OP1__NO_RETRY_NO_RECOVERY
```

结果目录必须是不存在的新目录：

```powershell
$deviceUrl = "http://DEVICE-IP"
$mapResult = ".test-output\hardware\RC2G_MAP_BASELINE_$(Get-Date -Format yyyyMMdd_HHmmss)"
python tools\g1_s1_rc2g_map_baseline_once.py `
  --result-dir $mapResult --url $deviceUrl `
  --confirm "AUTHORIZE_ONE_VISIBLE_RC2G_COLD_BOOT_MAP_ORIENT_V1_BASELINE_JOB1_OP1__NO_RETRY_NO_RECOVERY" `
  --confirm-rc2g-flashed-fresh-boot `
  --confirm-j2-powered-supervised `
  --confirm-supply-and-temperature-normal `
  --confirm-single-visible-refresh
```

自动 nominal gate：total/job 28000–45000 ms；两半上传各 1500–5000 ms；
PON 50–2000 ms；DRF 18000–26000 ms；POF 50–1000 ms；post-PSR 0–100 ms。
PON/DRF/POF 都必须是 idle-before-command 后的新 BUSY edge，最终 RST/CS1/CS2=0。

人工对照 MAP：整屏完全覆盖；左右方向/位置一致；中央多色竖线、中缝和横向黑/红标尺
正确；六色边框、四角块和细线栅格完整；无镜像、交换、裁切、错色、半屏缺失或旧图区域。

E1 任一自动、电气或人工项失败：实体断开 J2-P1，整晚停止；该 claim 永久消费，不重试、
不 recovery、不进入 E2。

### E2：macro4 job2/op2 独立重显

只在 E1 全部通过且 ESP32 未重启、J2 未断开的前提下执行。

| 项目 | 固定值 |
|---|---|
| Strict preview | [macro4 strict-final.png](../.test-output/hardware/G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807/strict-final.png) |
| Source target | [macro4 source.png](../.test-output/hardware/G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807/source.png) |
| frame SHA-256 | `1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d` |
| frame FNV-1a | `0x092C9775` |
| CS1/CS2 DTM FNV-1a | `0x3F1601D5` / `0x52ECC935` |
| prior / target | MAP job1/op1 → macro4 job2/op2 |

精确授权字符串：

```text
AUTHORIZE_ONE_VISIBLE_REDISPLAY_OF_FROZEN_G1S1_MACRO4_FRAME_AFTER_NOMINAL_REBOOT_MAP_JOB1__NO_RETRY_NO_RECOVERY
```

```powershell
$macroResult = ".test-output\hardware\G1S1_MACRO4_REDISPLAY_$(Get-Date -Format yyyyMMdd_HHmmss)"
python tools\g1_s1_macro4_redisplay_once.py `
  --result-dir $macroResult --url $deviceUrl `
  --confirm "AUTHORIZE_ONE_VISIBLE_REDISPLAY_OF_FROZEN_G1S1_MACRO4_FRAME_AFTER_NOMINAL_REBOOT_MAP_JOB1__NO_RETRY_NO_RECOVERY" `
  --confirm-j2-powered-supervised `
  --confirm-supply-and-temperature-normal `
  --confirm-visual-quality-concern-redisplay
```

门限与 E1 相同。runner 还会再次读取并保存 raw diagnostic/status；昨晚 37110 ms PON、
39621 ms DRF、89049 ms total 一类结果会 fail closed 为 `unknown_do_not_retry`。

人工评价必须拆成两栏：

- 设备忠实度：与 strict preview 的区域、方向、中缝、六码位置一致；无 MAP 残留、漏刷、
  镜像、错位或错码。
- 算法画质：内容辨识、4×4 块感、渐变、色偏、颗粒/聚簇、周期条纹、边缘和细节。

`frame fidelity=PASS` 且 `algorithm quality=POOR` 是允许且有意义的结论：它说明显示器
忠实显示了一个不理想的宏像素候选，不是驱动故障。

E2 出现 unknown、timing 超界、报告/hash 不符、电气异常或错屏：立即断电，不重发。
若仅画质差而协议、电气、忠实度全部正常，可正常结束观察，不必把它升级为电气事故。

### H3：会话收尾

记录 safe-finish 后和稳定 60 秒后的电流/温度，拍固定曝光照片；无论通过与否，监督会话
结束时实体断开 J2-P1。保存 attempt lock、result、raw job、raw diagnostic、raw GPIO、
照片和人工裁决，并为每个结果目录生成/复核 SHA256SUMS。使用
[`MF1750_RC2G_EVENING_RUN_RECORD_2026-08-07.md`](../templates/MF1750_RC2G_EVENING_RUN_RECORD_2026-08-07.md)
记录。

## 5. N1 low-balanced 探索性真屏（已完成）

N1 只验证 RC2G 在一个已知低空间频率、左右半屏负载平衡的固定 raster 上能否保持
nominal 协议、电气和画面忠实度。它不是自然图、不是混色算法画质候选，也不构成
2×2 严格因果实验。N1 最多两次可见刷新：独立 MAP primer job1/op1，随后仅在其自动
证据、人工 MAP 忠实度和电气门全部通过时执行固定 low-balanced job2/op2。N1 明确禁止
Q1--Q4、其他 2×2 cell、自动连播、retry 或 recovery。

执行结果：primer job1/op1 与 target job2/op2 均通过自动协议、电气和人工画面门；目标与
本节固定 strict preview 一模一样，ESP32 全程未重启，两次刷新之间 J2 未断开，最终 J2
已由用户物理断开。两个 fixed claim 均永久消费，以下命令仅保留为已执行过程记录，禁止
再次运行。

### N1-0：断电 fresh reboot 与固定现场

开始时 J2-P1 必须物理断开；不要重刷已经验收的 RC2G binary。保持与 N0 相同的接线、
3.3 V CV、1.00 A 限流和固定相机条件，在 J2 断开时 fresh reboot ESP32。在调用 runner
前先用独立只读现场预检核对当前 RC2G build/API/PSRAM/mapping、job0/action none/state
idle、无 completed diagnostic，且 RST/CS1/CS2 为低。此时任一项不符就保持 J2 断开、
不调用 runner，因而不消费 primer claim。runner 启动后会先永久 claim，再执行权威的
fresh-state 复核；若这次复核失败，结果是 `unknown_do_not_retry` 且 claim 已永久消费。

通过后由用户接通一次 J2-P1，并确认 3.3 V、CV、空闲电流、温度、声音和气味正常，
物理开关可立即切断。正常的 MAP 与 low-balanced 两张之间不例行断电；ESP32 重启、
任何异常或监督会话结束时才实体断开。

### N1-1：固定 MAP primer job1/op1

本阶段只能使用
`tools/g1_s1_rc2g_n1_low_balanced_map_primer_once.py`。它是 N1 专属的 workspace-global
fixed action，不是已消费 N0 baseline claim 的复用或改目录重跑；它自身明确
`follow_up_low_balanced_refresh_authorized=false`，MAP 成功也不会自动授权第二张。

| 项目 | 固定值 |
|---|---|
| action ID | `rc2g-n1-low-balanced-pilot-cold-boot-map-primer-job1-op1-once-v1` |
| action identity SHA-256 | `6354b456bc71033fa4ef96ebc8ff972e8d1e45f0f27403977c99bdee4cc20660` |
| authorization SHA-256 | `403d0c52a6c34ce8dee1226bd5422f8c5df586ea6dc2c09a0b812d14746aeb7d` |
| Preview | [MAP_ORIENT_V1_reference.png](../.test-output/MAP_ORIENT_V1_reference.png) |
| frame SHA-256 / FNV-1a | `1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36` / `0x9D04142D` |
| CS1/CS2 DTM FNV-1a | `0xF26832DD` / `0xFE199FF5` |
| initial / target | fresh job0/no report → job1/op1 |

精确授权字符串：

```text
AUTHORIZE_ONE_VISIBLE_RC2G_N1_LOW_BALANCED_PILOT_COLD_BOOT_MAP_PRIMER_JOB1_OP1__NO_RETRY_NO_RECOVERY
```

结果目录必须是不存在的新目录：

```powershell
$deviceUrl = "http://DEVICE-IP"
$n1MapResult = ".test-output\hardware\RC2G_N1_LOW_BALANCED_MAP_PRIMER_$(Get-Date -Format yyyyMMdd_HHmmss)"
python tools\g1_s1_rc2g_n1_low_balanced_map_primer_once.py `
  --result-dir $n1MapResult --url $deviceUrl `
  --confirm "AUTHORIZE_ONE_VISIBLE_RC2G_N1_LOW_BALANCED_PILOT_COLD_BOOT_MAP_PRIMER_JOB1_OP1__NO_RETRY_NO_RECOVERY" `
  --confirm-rc2g-flashed-fresh-boot `
  --confirm-j2-powered-supervised `
  --confirm-supply-and-temperature-normal `
  --confirm-single-visible-primer-refresh
```

runner 强制单 POST、job1/op1、RC2G nominal timing、PON/DRF/POF idle-before-command/new
BUSY edge、raw job/diagnostic/GPIO 和最终 RST/CS1/CS2 低。claim 创建后任何 exception 都
是 `unknown_do_not_retry`；只能保存只读补抓证据，不能重发。

### N1-2：MAP 人工放行门

自动结果为 `protocol_verified_manual_observation_required` 后仍不得立即执行第二张。人工
先对照 MAP preview 检查整屏覆盖、方向/位置、中央竖线与中缝、标尺、六码边框、四角块
和细线栅格；同时重新确认 3.3 V、CV、电流和温度正常。把 MAP 照片、结果文件和人工
`frame fidelity=PASS` 裁决冻结并计算 SHA-256。

MAP 的自动证据、人工忠实度或电气任一失败：立即实体断开 J2-P1，N1 结束；primer
claim 永久消费，不运行 low-balanced。只有三者全 PASS，且 ESP32 未重启、J2 未断开，
才可为固定 job2/op2 另行生成和取得精确授权。

### N1-3：固定 low-balanced job2/op2

目标固定为 2×2 V2 中唯一的 `low-balanced` raster；其身份用于探索性低风险 pilot：

| 项目 | 固定值 |
|---|---|
| Bundle | `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2/` |
| Strict preview | [low-balanced.strict-final.png](../.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2/low-balanced.strict-final.png) |
| strict preview SHA-256 | `39c10018dda091bb5af0ebad26b006c1c5e7c3374096de086e7cc8debcc42205` |
| V2 manifest file SHA-256 | `b25efedae7d3ff5947c7b5c546879b6fbce44f67ae59d410581b4d745e8db055` |
| frame SHA-256 / FNV-1a | `ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65` / `0xA9641618` |
| CS1/CS2 DTM FNV-1a | `0xCB085C03` / `0x9ABD749A` |
| 四邻域异色边 / 最大半屏单色计数差 | `29565` / `1` |
| exact prior / target | 本次已人工通过的 N1 MAP job1/op1 → low-balanced job2/op2 |
| target fixed action ID / claim filename | `rc2g-n1-low-balanced-pilot-after-map-primer-job2-op2-once-v1` |
| target claim registry ID | `workspace-g1-s1-rc2g-quality-refresh-registry-v1` |

目标 runner `tools/g1_s1_rc2g_low_balanced_pilot_once.py` 已完成软件聚焦/联合检查和
本次 exact 硬件执行。它没有 candidate、campaign、job 或 registry override；target action
identity 绑定真实 primer result SHA，因此授权串不能在 primer 前预生成。永久 claim 使用
上述固定文件名，而不是 action SHA、primer SHA 或 result directory；更换这些输入不能
形成第二个授权分区。

MAP 自动证据、人工忠实度和电气门全部 PASS 后，且 ESP32 未重启、J2 始终保持本次监督
接通，先计算 exact primer result SHA：

```powershell
$n1PrimerResult = Join-Path $n1MapResult "N1-LOW-BALANCED-MAP-PRIMER-RESULT.json"
$n1PrimerResultSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $n1PrimerResult).Hash.ToLowerInvariant()
```

随后只做离线描述；该命令不创建 claim、不访问设备，也不刷新面板：

```powershell
python tools\g1_s1_rc2g_low_balanced_pilot_once.py `
  --primer-result $n1PrimerResult `
  --primer-result-sha256 $n1PrimerResultSha `
  --describe-only
```

`--describe-only` 必须深验证：primer result 文件名/路径/hash、对应永久 primer claim、
fresh job0/no-report、completed MAP network/job/diagnostic/GPIO、单 POST request audit、完整
2×2 V2，以及 low-balanced 与旧成功 low-spatial frame 的逐字节同一性。输出必须显示
`device_io_performed=false`、`claim_created=false`、上述 fixed action/claim filename、
同一 primer result SHA、strict-preview SHA、动态 `action_identity_sha256` 和动态
`required_authorization_confirmation`。授权格式为
`AUTHORIZE_ONE_VISIBLE_RC2G_QUALITY_REFRESH__ACTION_<本次动态ACTION-SHA大写>__NO_RETRY_NO_RECOVERY`；
不得猜测、截短、复用其他 run 的字符串，也不得把 describe 输出自动直接传给执行命令。

用户检查完整 describe 输出并对其中 exact action 单独明确授权后，才把授权原文填写到
下方变量。结果目录必须不存在；占位文本绝不能作为授权执行：

```powershell
$n1TargetAuthorization = "<用户刚刚明确授权的 required_authorization_confirmation 原文>"
$n1TargetResult = ".test-output\hardware\RC2G_N1_LOW_BALANCED_PILOT_$(Get-Date -Format yyyyMMdd_HHmmss)"
python tools\g1_s1_rc2g_low_balanced_pilot_once.py `
  --primer-result $n1PrimerResult `
  --primer-result-sha256 $n1PrimerResultSha `
  --result-dir $n1TargetResult --url $deviceUrl `
  --confirm $n1TargetAuthorization `
  --confirm-j2-powered-supervised `
  --confirm-supply-and-temperature-normal `
  --confirm-primer-visual-pass `
  --confirm-no-esp32-reboot-since-primer `
  --confirm-no-j2-disconnect-since-primer `
  --confirm-reviewed-low-balanced-strict-preview
```

正常执行会在任何设备请求前以固定文件名永久 claim，然后重新读取 live version、job1、
diagnostic 和 GPIO。stored primer 与 live prior 不是只比较 job/op：stored result/claim、
MAP frame SHA/FNV、两路 DTM、完整 raw job 和完整 raw diagnostic 都先逐字段冻结；live raw
job 与 raw diagnostic 必须分别与 stored `completed_map_evidence` 完全相等，build/API/
mapping 和低电平输出也必须通过。`--confirm-no-esp32-reboot-since-primer` 是额外人工确认，
`--confirm-no-j2-disconnect-since-primer` 则独立确认 MAP 与 target 之间 J2 一直保持本次
监督接通；两者都不能代替上述机器门禁。若 live prior 不同，target POST 为零，但已是
`unknown_do_not_retry` 且固定 target claim 永久消费；立即断电，不得用新 primer SHA、
新目录或重启绕过。

真屏人工判断只对照 `low-balanced.strict-final.png`：方向、左右均衡、中缝、图案区域
和六码位置必须忠实，无 MAP 残留、半屏漏刷、镜像、错位或错码。该 raster 不保留自然
图语义；块感、难看、无法辨认照片都不是算法画质结论，不填写自然图总体画质排名。

target 的自动证据、timing、电气或忠实度任一异常：立即断开 J2-P1，不重试、不 recovery、
不进入 Q1--Q4。若全部通过，记录 safe-finish 后和稳定 60 秒后的电流/温度及固定曝光
照片，然后在监督会话结束时实体断开 J2-P1。通过也只产生
`experimental low-balanced RC2G fidelity/safety pilot`，不证明 2×2 因果、不提升任何
混色算法资格，也不授权 Q1--Q4。

## 6. 后续质量 A/B Campaign（执行器完成，硬件放行仍阻塞）

这部分是完整测试矩阵的一部分，但不与今晚核心会话混跑。通用 runner 已实现：离线
`--describe-only`、每 action 独立 claim、明确 prior/target job/op/frame/DTM、单 POST、
严格 timing/BUSY/GPIO gate 和异常证据保全。它不是候选负载放行器；现有 bundle 的
`upload_authorized=false` 也没有因此自动改变。

prior action 会冻结 frame SHA-256、frame FNV-1a 和两路 DTM FNV-1a；设备报告可严格
复核的是 FNV/DTM，frame SHA-256 只属于离线 action 身份，因为当前固件不报告 SHA-256。

| 顺序 | 算法 | Manifest SHA-256 | Frame FNV-1a | 四邻域异色边 | 最大半屏单色计数差 | 主要观察 |
|---:|---|---|---|---:|---:|---|
| Q1 | Atkinson | `ae882e6c7cd032a8315e15a1deb2a77abee025711acb55b5ec22b0fe91a4f32b` | `0xFAC8E693` | 446055 | 54368 | 细节、误差扩散纹理、灰阶 |
| Q2 | 面积加权蓝噪声 | `69244cebe2e37c0d26404b85b9d89471cd95d492a9599481e5f34968c3159a48` | `0xB932966C` | 484089 | 49650 | 低频色偏、噪声均匀性、渐变 |
| Q3 | 多色 DBS | `9eb946ddb91093d654071d55f9fa0f3f890497f368c3cbd7222ea19213f1db3e` | `0xCA448751` | 636046 | 54473 | 边缘、局部损失、周期纹理 |
| Q4 | 重叠感知 DBS | `c7fc66c6cb879997c5a5b34d8b8234c2abbca691a80c29f44c7e212548ebd062` | `0x5CD8EEDF` | 636073 | 54460 | 与 Q3 的实屏差异、模型残差 |

对照值：已通过的 low-balanced 为 29565/1，macro4 为 126996/48160，旧异常 ordered
为 504453/49656。边数和半屏计数不是电能或故障因果阈值，但足以说明 Q1--Q4 不应因
runner 完成就直接连播，尤其 Q3/Q4 的空间复杂度高于旧异常帧。

公平比较必须把每个候选拆成独立 session：`fresh boot -> 同一 MAP job1 -> 单一候选
job2 -> 收尾断电`。禁止 Q1→Q2→Q3→Q4 连续播放，因为 prior、残影和温度历史都会变化。
现有 RC2G baseline 的固定 claim 只服务今晚首次验收，不能靠换目录重复消费；因此后续
还需先冻结不可伪造的 campaign manifest/cell ID，并为每个 cell 建立独立 MAP-primer
授权。该编排器完成前，不生成 Q1--Q4 的真屏授权串，也不执行通用 runner。

同一固定相机条件下比较 source/mapped/final/model 与真屏照片。没有 measured palette/
光学核时只能形成 `experimental subjective result`，不能宣布算法正式胜出。原
`area-weighted-ordered-8x8` 事故帧不再直接重跑。

## 7. 根因 2×2 与其他工况

2×2 V2 只证明四格共享全局六码直方图和全局 6×6 转移矩阵，并分别操纵高/低空间频率
与平衡/不平衡半屏负载；edge/seam 仍有残余协变量，不能严格因果归因。只有
`low-balanced` 与已测 job4 是同一 raster；`failed_ordered` 只是约束来源，不等于新
`high-unbalanced` raster。每个 cell 还必须从同一个可见 MAP prior 开始，因此现在禁止
连续播放。第 5 节 N1 是唯一 narrow exception，只允许 `low-balanced` 做探索性
safety/fidelity pilot；它不放行其他三格，也不能把当前 V2 升级为严格因果实验。

以下工况各自需要独立 runbook，不混入 RC2G 两帧核心会话：

- 冷启动与成功后的 warm sequential refresh；
- 固定 MAP 恢复/残影转移；
- 环境温度分档与重复性；
- SPI 1/2/4/8/10 MHz 扫频；
- 真实浏览器 C4 E2E；
- D65/2° 色块、混色比例、相机 RAW 或分光测量；
- 未知码、快速/局部波形、耐久和故障注入。

未经对应门禁，不做带电中途断电、未知码、波形/高压修改或自动连刷。

## 8. 完整日夜滚动测试计划

| 阶段 | 何时可做 | 目标与固定 prior | 白天需准备 | 晚间可见动作 | 放行/停止结论 |
|---|---|---|---|---|---|
| D0/N0：RC2G 核心 | 2026-08-07 已完成 | fresh job0→MAP；MAP→macro4 | 本文第 2 节全部放行项 | 已完成 2 次 | 两帧证据链/忠实度通过；macro4 画质差；旧时序异常根因未关闭 |
| D1/N1：low-balanced 安全 pilot | 2026-08-07 已完成 | fresh job0→N1 MAP；该 MAP→low-balanced | 专属 primer/target、动态绑定和 evidence 已闭环；聚焦 56 项通过 | 已完成 MAP+low-balanced 两张 | exact action 的 experimental safety/忠实度 PASS；不作自然图画质或 2×2 因果结论 |
| D2/N2：自然图质量 A/B | N1 nominal 条件已满足；等待独立 cell 编排与风险冻结 | 同一源图、参数、MAP prior | 固定相机/裁切/顺序，冻结四算法与对照 | 每晚 MAP+1 个算法 | 得到主观排序；无 measured profile 不作正式 qualification |
| D3/N3：重复性/排序效应 | 厂商刷新与冷却限制明确后 | 同一 MAP prior、预注册顺序 | 重复次数、随机顺序、冷却和累计上限 | 小批次重复 | 评价温度/时序/画面漂移；未定上限前禁止耐久连刷 |
| D4/N4：根因 2×2 | 新 bundle/runner 通过审计后 | 每个 cell 都从 MAP 开始 | 消除 edge/seam 协变量或降级为探索性；cell runner | 低平衡→低不平衡→高平衡→高不平衡，分 session | 首次异常停止；不能用现 V2 作严格因果结论 |
| D5/N5：六色测量 | 测量链具备后 | 预注册恢复画面与 dwell | D65/2°、RAW/分光、ROI、色块/混色/光学核 runner | 单色、混色比例、核测量 | 形成 measured palette/profile；人工只判错码/色斑 |
| D6/N6：浏览器 E2E | measured-artifact gate 完成后 | 声明 exact prior | one-shot arm、有限 deadline、浏览器自动化 | 单一冻结照片 | preview/裁切/真屏/错误状态端到端一致 |
| D7/N7：SPI 扫频 | 参数化诊断固件完成后 | 每档 fresh MAP | 1/2/4/8/10 MHz action、证据 schema | 每档一次，频率递增 | 首个失败即止；每次重启前 J2 断开 |
| D8/N8：残影/温度/warm/soak | 厂商限制和 scheduler 完成后 | 明确 A→B→A 或 warm prior | 历史绑定、温度分档、刷新上限 | 受限序列 | 评价残影和稳定性；禁止无人值守刷新 |

未知颜色码、LUT/波形/高压修改、局部/快速刷新、带电故障注入和无人值守随机照片刷新
保持 hard-blocked，直到厂商资料、隔离硬件、安全联锁、认证与持久 job 历史全部具备。

每天白天的固定闭环是：导入昨晚 evidence→核对 SHA→分别裁决协议、电气、忠实度和
画质→只修复被证据支持的问题→离线回归/build→冻结当晚 action。每天晚上只执行已冻结
且已通过白天 gate 的行，不在硬件旁临时生成候选或扩大测试范围。

## 9. 统一停止条件

任一条件发生即停止当前及后续 run，必要时实体断电：

- 电源进入 CC/限流、退出 CV、3.3 V 明显跌落或电流未回到稳定水平；
- L1/L2/驱动器/ESP32 快速升温、异味、异声或外观异常；
- ESP32 重启、job/op 不连续、frame/DTM/build/API/mapping 不匹配；
- pre-command idle 失败、缺少新 BUSY edge、timeout、timing 超出 nominal gate；
- safe-finish 前 BUSY 未 idle，或最终 RST/CS1/CS2 非低；
- 网络结果不明、证据写入失败、runner 返回 unknown；
- 半屏漏刷、错位、镜像、错色、旧图未覆盖或与 strict preview 不一致。

任何 claim 一经创建即永久消费。禁止通过更换目录、重启脚本或网络重发来规避；只读
补抓证据不属于 retry。画质主观不佳但忠实度、电气、timing 都正常时，记录为质量结论，
不伪装成驱动故障。
