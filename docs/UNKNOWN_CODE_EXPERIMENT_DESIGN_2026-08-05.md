# MF-1750 `0x4/0x7` 未知编码隔离实验设计

文档日期：2026-08-05

阶段：F（未知编码实验准备）

设计状态：`READY FOR REVIEW`

实现状态：`BLOCKED / NOT IMPLEMENTED`

Hardware tested: `NO`

用户授权记录：无固件实现、COM8 刷写、上电或未知码刷新授权。

适用基线：MF-17506-M009F-T、1024×600、4bpp packed、双 SPD1657B revision
`0x04`、MF1750 Rev A1、R15 已拆、R16=0 Ω、CS1=GPIO7、CS2=GPIO10。

相关门禁：

- [`EXTENDED_COLOR_MEASUREMENT_SAFETY_GATE_2026-08-05.md`](EXTENDED_COLOR_MEASUREMENT_SAFETY_GATE_2026-08-05.md)
- [`EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`](EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md)
- [`TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)
- [`MF1750_DRIVER_API.md`](MF1750_DRIVER_API.md)

## 1. 目的和非目标

本文件只设计一个能验证 `0x4`、随后单独验证 `0x7` 的固定小面积黑盒探针。它不
实现任何固件，不授权硬件动作，也不说明未知码安全或有效。

非目标：

- 不放宽正式 `/api/frame`、HTTP ingress 或公共 C++ 颜色 guard；
- 不接受任意未知码 raw frame；
- 不测试 `0x8～0xF`；
- 不调用未知 SPI 命令；
- 不修改初始化、CCSET、PWR、BTST、POFS、PLL、PWS、VCOM 或任何高压参数；
- 不上传或选择 LUT，不改变 phase、时间、温度模式或 OTP waveform；
- 不实现 partial/window；小 ROI 仍使用完整 DTM 和全屏 DRF；
- 不提供循环、定时、自动重试或无人值守运行；
- 不把主机确认参数当成设备端权限控制。

## 2. 不可变生产边界

正式颜色码继续只有：

```text
0黑、1白、2黄、3红、5蓝、6绿
```

必须保持：

- [ ] 正式 `/api/frame` 对 `0x4/0x7..0xF` 的拒绝完全不变；
- [ ] `epdValidateFrameColors()` 和公共 `epdDisplayFrame*` 的六色 guard 完全不变；
- [ ] release build 默认禁用实验功能，实验路由不存在或固定返回 404；
- [ ] 实验入口不覆盖或替代正式 API；
- [ ] 生产 build tag、driver API 和正式诊断语义不继承实验结果；
- [ ] 实验 build 仍使用已经批准的厂家初始化和片上 OTP waveform；
- [ ] 现有冻结生产目录和 PCB 文件不修改。

在当前授权下不得修改 `src/`。未来若用户批准实现，也不能复制另一套初始化/高压
代码来绕过公共 guard；应先单独审查一个编译期隔离、只接受固定 fixture enum 的
私有驱动入口。任何必要的 `src/epd_driver.*` 修改仍需用户明确授权。

## 3. 风险边界

未知码是数据值，不是未知 SPI 命令，但仍可能：

- 选择保留 OTP 状态；
- 保持旧态或 alias 到已知颜色；
- 产生不稳定中间态、漂移或难恢复残影；
- 在两颗控制器上行为不一致；
- 触发与已知码不同的外部电流、轨包络、BUSY 或温升。

未知像素面积受控不等于电气局刷。控制器仍执行完整 PON/DRF/POF，因此电源、
高压、BUSY、温度和实体断电门禁必须按全屏刷新配置。

## 4. 固定布局 `EC5_MIRROR64_CENTER_V1`

坐标采用左上原点、半开区间，偶数 x 位于 packed byte 的高 nibble。

| 区域 | 坐标 | 控制器 |
|---|---|---|
| unknown ROI 1 | `x=[224,288), y=[268,332)` | CS1 / 左半屏 |
| unknown ROI 2 | `x=[736,800), y=[268,332)` | CS2 / 右半屏 |
| reserved guard 1 | `x=[192,320), y=[236,364)` | CS1 |
| reserved guard 2 | `x=[704,832), y=[236,364)` | CS2 |

规则：

- unknown ROI 均为精确 `64×64`；
- 两个 ROI 关于全屏竖直中线镜像；
- guard 外框相对 ROI 每侧保留 32 px；
- guard ring、全屏其余区域均为已知白 `0x1`；
- 活动区内无文字、编号或黑色锚点；定位标记放在面板活动区外的光学夹具上；
- 测色光斑中心分别为 `(255.5,299.5)` 和 `(767.5,299.5)`；
- 测色光斑实际直径不超过 5 mm；
- RAW 空间分析另使用内缩 ROI，避免把边界像素混入中心颜色判断。

物理尺寸按标称像素间距 `0.160×0.162 mm`：每个未知 ROI 约为
`10.24×10.368 mm`。

### 4.1 面积核算

```text
full_pixels            = 1024 × 600 = 614400
one_unknown_roi        = 64 × 64 = 4096
two_unknown_rois       = 8192
one_roi/full           = 0.6666667%
two_rois/full          = 1.3333333%
one_roi/controllerhalf = 4096 / (512×600) = 1.3333333%
known_white_pixels     = 606208
unknown_packed_bytes   = 8192 / 2 = 4096
unknown_bytes_per_dtm  = 2048
```

所以“左右各一个 `64×64`、未知总面积 `1.333%`”数学一致。每块 ROI 是全屏
`0.667%`，不是两块合计 `0.667%`。

## 5. 哈希草案

以下值按第 4 节坐标、背景 `0x1`、默认 mapping
`CS1=(0,0,0,0) / CS2=(1,0,0,0)`、偶数 x 高 nibble 在内存中计算。

这些是设计草案。实现前必须由两个独立生成路径逐 byte 比较，并用正式主机工具和
固件内部生成器重新冻结；未复核前不得进入执行 allowlist。

| candidate | full SHA-256 | full FNV-1a |
|---|---|---:|
| `0x4` | `5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e` | `0x68533DC5` |
| `0x7` | `d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e` | `0xA1C5ADC5` |

| candidate | CS1 DTM SHA-256 | CS2 DTM SHA-256 | DTM FNV-1a |
|---|---|---|---:|
| `0x4` | `a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00` | `a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00` | `0x15B7EDC5` |
| `0x7` | `2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac` | `2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac` | `0x97F125C5` |

左右 DTM 相同是本布局和当前无翻转 mapping 下的预期结果。SHA-256 是执行
allowlist 身份；FNV-1a 只用于与现有 diagnostic 字段兼容，不能替代 SHA-256。

## 6. 独立 build 策略

推荐一个候选一个 binary：

```text
release build: experiment disabled, no unknown fixture
U04 build:     only candidate 0x4 fixture exists
U07 build:     only candidate 0x7 fixture exists
```

要求：

- [ ] 默认宏为关闭，例如 `MF1750_ENABLE_UNKNOWN_PROBE=0`；
- [ ] candidate 不得由 HTTP、串口或配置文件动态指定；
- [ ] U04 binary 不包含 U07 fixture 或 0x7 action；
- [ ] 完成全部 0x4、恢复和报告评审后，用户重新授权才可构建/刷写 U07；
- [ ] 每个 binary 具有不同 build tag、binary SHA-256 和 manifest SHA-256；
- [ ] 实验 build 不能继承正式 release 的硬件通过状态；
- [ ] 实验宏、route、fixture 和私有入口均由 release 静态检查证明不存在；
- [ ] 当前任务不创建这些 build，不修改固件。

把 0x4 和 0x7 放进同一 binary 后只靠 UI 隐藏不合格，因为它不能形成阶段间的
重新授权门。

## 7. 固定 fixture manifest

每个可执行 test ID 必须在 binary 构建时进入不可变 allowlist。嵌入 binary 的
fixture manifest payload 至少包含：

```text
schema_version, layout_id, test_id, candidate_code,
intended_initial_code, sequence_class, repetition,
width, height, frame_bytes, pixel_packing,
roi_cs1, roi_cs2, guard_cs1, guard_cs2,
known_white_pixels, unknown_pixels, color_histogram,
frame_sha256, frame_fnv1a,
cs1_dtm_sha256, cs1_dtm_fnv1a,
cs2_dtm_sha256, cs2_dtm_fnv1a,
mapping_cs1, mapping_cs2,
firmware_commit, build_tag, config_sha256,
driver_baseline_commit, command_sequence_digest,
otp_mode, created_at, review_id
```

`binary_sha256` 不得放进其自身所哈希 binary 内的 manifest payload，否则形成
不可满足的自引用。冻结身份分两层：

1. `manifest_payload_sha256 = SHA256(JCS(payload))`，其中 `JCS` 是 RFC 8785 JSON
   Canonicalization Scheme；payload 不含自身 digest 或 binary digest；
2. 构建完成后生成只读外部 build sidecar，绑定 `build_tag`、`firmware_commit`、
   `config_sha256`、`binary_sha256` 和 `manifest_payload_sha256`。

设备只信任编译期嵌入的 payload 及其预期 `manifest_payload_sha256`；主机在 arm 前
同时校验设备报告的 digest、外部 sidecar 和实际 binary SHA-256。不得用一个未定义
canonical scope 的 `manifest_sha256` 字段，也不得在 hash 时临时排除未列明字段。

初始态顺序固定为：

```text
白 0x1 → 黑 0x0 → 红 0x3 → 黄 0x2 → 蓝 0x5 → 绿 0x6
```

test ID 示例：

```text
EC5-U04-I01-P01-L64M1
EC5-U04-I00-P01-L64M1
EC5-U04-I03-P01-L64M1
EC5-U04-I02-P01-L64M1
EC5-U04-I05-P01-L64M1
EC5-U04-I06-P01-L64M1
```

`test_id` 是固定且一次使用的 fixture 身份；`run_id`/`job_id` 由设备产生，二者
不能混为同一个字段。重复轮次使用新的、预先列举的 test ID，禁止运行时自由拼接。

## 8. 设备内部生成与自校验

实验入口只能让设备根据编译期 fixture 生成目标帧。不得：

- 接收 raw frame；
- 接收 candidate code；
- 接收 ROI、面积、背景色、mapping 或 packing 参数；
- 读取可写文件系统中的替代 fixture；
- 调用正式 `/api/frame` 绕过颜色 guard。

在任何初始化或面板 GPIO 动作前，设备内部必须：

1. 生成精确 307200 字节 frame；
2. 逐像素验证只有 `0x1` 和该 binary 唯一候选码；
3. 验证白/未知像素计数；
4. 验证未知像素只位于两个固定 ROI；
5. 验证 full SHA-256；
6. 采用冻结 mapping 生成两半 DTM；
7. 验证双 DTM SHA-256；
8. 验证 build/config/manifest/command sequence 身份；
9. 任一不符时在 EPD I/O 前失败，并永久消费该次 arm/test ID。

不得只用 FNV-1a 通过自检，也不得把 hash mismatch 后重新生成/重试视为安全恢复。

## 9. 一次性 arm 和实验接口合同

当前设备 HTTP 服务无认证和 TLS。实验只能在可信隔离网络中运行，并优先使用本地
串口或实体按钮完成设备侧 arm。主机现有一次性 arm 只保护正式六色应用链，不能
替代实验设备侧 arm。

概念上的实验接口只能支持：

- 读取 experiment version/manifest/status，不进行 EPD I/O；
- 对精确 test ID 建立一次性 arm；
- 提交一次无 frame body 的固定 fixture job；
- 查询同一 job；
- 读取不可变 report；
- 在人工评审后进入固定已知码恢复流程。

arm 必须绑定：

```text
boot_nonce, test_id, build_tag, binary_sha256, manifest_payload_sha256,
frame_sha256, cs1_dtm_sha256, cs2_dtm_sha256,
mapping, cold_start_evidence_id, measurement_setup_sha256,
user_authorization_id, expires_at
```

建议 TTL 为 60 秒。提交请求到达时先原子消费 arm，再检查任何调用方字段。以下
情况都不得恢复或复用 arm：

- body/Content-Type 错误；
- stale boot nonce；
- test ID、mapping 或 hash 不匹配；
- TTL 过期；
- 本地生成/自检失败；
- HTTP 响应丢失；
- MCU reset；
- job 排队失败。

每个 test ID 的 consumed 状态持久化，重启后仍拒绝；不得提供网络
`reset-consumed`。网络超时后只能查询 status/job/report，禁止再次 POST。

从进入 `ARMED` 起直到 `RECOVERY_CONFIRMED` 后转入 `LOCKED`，实验状态机必须持有
全局 EPD refresh lock。除该 test ID 的一次 fixture execute 和随后经人工授权的
固定恢复 job 外，正式 `/api/frame`、legacy route、启动刷新、定时器以及其他客户端
的已知六色 job 全部 fail closed。实现可以在实验 build 中静态移除这些刷新 route，
也可以由单一全局仲裁器拒绝它们；仅保持正式颜色 guard 不变并不足以满足此门禁。

## 10. 状态机

```text
DISABLED
  └─ experimental binary verified
      → COLD_START_UNCONFIRMED
        └─ external evidence + user authorization
            → ARMED(ttl, boot_nonce, test_id)
              └─ any execute attempt atomically consumes arm
                  → CONSUMED
                    → QUEUED
                      → RUNNING
                        → TERMINAL_REVIEW_REQUIRED
                          └─ electrical/visual review passes
                              → RECOVERY_AUTHORIZED
                                → RECOVERY_RUNNING
                                  → RECOVERY_REVIEW_REQUIRED
                                    └─ optical/electrical recovery passes
                                        → RECOVERY_CONFIRMED
                                          → LOCKED
```

任一异常转入 `FAULT_LOCKED`。`FAULT_LOCKED` 只允许读状态、下载已有 report 和
执行人工授权的安全处置；不得再次 arm 或自动发起恢复。

每个冷启动最多一个未知 fixture job。boot、timer、Wi-Fi reconnect、浏览器刷新或
HTTP retry 都不能触发 job。

## 11. 冷启动证据

面板 J2-1 与 ESP32 USB 可以独立供电，且 MCU 没有 TP1 sense，所以 ESP32 reboot
不能证明面板冷启动。每个 experiment run 必须绑定外部记录：

- [ ] 前一个 job 已完成 POF 和正式安全收尾；
- [ ] 用户已人工切断 J2-1；
- [ ] TP1 `≤0.10 V` 持续至少 5 秒；
- [ ] 若探头仍连接，TP3/TP5/TP6 已进入释放门；
- [ ] J2-1 已断开至少 10 秒；
- [ ] FPC 未带电插拔；
- [ ] 探头连接和测量系统 hash 未改变；
- [ ] 用户另行允许上电；
- [ ] 用户确认电源 CV、限流、急停、温度和仪器正常；
- [ ] 用户允许发送该精确 test ID；
- [ ] 设备报告新的 boot nonce，且本冷启动还没有 EPD job。

软件只能保存这些证据，不能把人工确认伪装成物理传感器测量。

## 12. 单次执行顺序

### 12.1 建立初始态

初始颜色使用正式六色 API 和精确已知帧，在之前单独授权的 job 中建立。建立后：

- 保存 initial frame、双 DTM、job/report hash；
- 在固定时点测量实际初始 Lab；
- 保存 RAW、均匀性、电流、轨和温度；
- POF、切断 J2-1、确认 TP1，再等待下一次冷启动。

未知 fixture 入口不负责生成初始态，否则会破坏“一次 job”的语义。

### 12.2 未知 fixture job

1. 核对 U04/U07 精确 binary、build、manifest 和 test ID；
2. 完成第 11 节冷启动证据；
3. 读取 version/manifest/status，仅做只读预检；
4. 核对仪器通道、量程、触发、急停和原始数据目录；
5. 用户明确授权该 test ID；
6. 设备侧一次性 arm；
7. 只提交一次固定 fixture execute；
8. 不管 HTTP 响应是否到达，都禁止再次提交；
9. 查询同一 job 到 terminal，并读取不可变 report；
10. 人工确认画面、电流、BUSY、轨、温度及有无异常；
11. 电气审查通过后才请求恢复授权；
12. 恢复通过后 POF、断 J2-1、确认 TP1。

首次只允许 `0x4`、白色实测初始态和一次运行。不得由该结果自动扩大到其他初始态、
重复、保持或 `0x7`。

## 13. 不可变实验报告

report 至少绑定：

```text
schema_version, test_id, run_id, job_id, operation_id, boot_nonce,
firmware_commit, git_dirty, build_tag, binary_sha256,
manifest_payload_sha256, config_sha256, command_sequence_digest,
layout_id, candidate_code, intended_initial_code,
measured_initial_measurement_id,
frame_sha256, frame_fnv1a,
cs1_dtm_sha256, cs1_dtm_fnv1a,
cs2_dtm_sha256, cs2_dtm_fnv1a,
white_pixel_count, unknown_pixel_count,
arm_created_at, arm_consumed_at, arm_expired,
job_queued_at, job_started_at, job_finished_at,
pon_busy_seen, drf_busy_seen, pof_busy_seen,
pon_ms, drf_ms, pof_ms, timeout_stage, busy_missing_stage,
safe_finish, reset_during_job, no_retry,
measurement_setup_sha256, cold_start_evidence_id,
user_authorization_id, terminal_state
```

网络、REV 查询或后续恢复不能覆盖未知 job 的报告。恢复使用新的 job/report，并由
`probe_test_id` 显式关联。

## 14. 异常、恢复与阶段推进

### 14.1 立即停止

以下任一出现时进入 `FAULT_LOCKED`，触发 POF（若仍安全）和外部 J2-1 切断：

- 永久色斑、快速恶化残影或面板裂纹；
- 左右控制器行为明显不一致且继续恶化；
- BUSY assertion 缺失、timeout 或 MCU reset；
- 电流、能量、温度或任一轨越过绝对/相对门；
- PSU 离开 CV、OVP/OCP/急停动作；
- 探头断开、仪器饱和、数据/hash/日志证据丢失；
- 异响、异味、冒烟、弧光或不可解释热点。

异常后禁止自动重试，也禁止为了“清掉画面”自动刷新四次。先断电和评审；只有安全
负责人和用户重新授权后才能执行恢复。

### 14.2 恢复

无电气异常且用户授权时，执行一次固定：

```text
原厂全黑 → 原厂全白 → 原厂全黑 → 原厂全白
```

每一步仍是已知码、精确 hash 的独立 job；不能由未知 fixture job 内部自动连刷。
一套序列最多执行一次。最终白色必须通过测量安全门文档的 Lab、RAW、均匀性、
电流、轨、BUSY、温度和断电判据。

恢复失败时：

- 隔离该面板并保存原始证据；
- 停止本 candidate 的后续初始态和重复；
- 禁止进入 0x7 或 bit3 alias；
- 不再自动清屏。

### 14.3 0x4 到 0x7

`0x4` 必须按白、黑、红、黄、蓝、绿逐态通过，每态间恢复可靠；pilot 通过后才可
另行申请增加到最多 10 次重复，重复通过后才可申请 1 h/24 h 保持。

完成 `0x4` 报告后必须停止。只有用户再次批准、独立 U07 build 完成代码审查、
release guard 回归、binary/frame/双 DTM hash 冻结，并重新授予 COM8 刷写、上电和
精确 test ID 刷新授权后，才可开始 `0x7`。

不得从 F/G 自动进入 `0x8～0xF` bit3 alias 阶段。

## 15. 离线负例和合同测试

实现获批后，至少需要以下不访问硬件的测试：

### 15.1 生产边界

- [ ] release build 中实验宏为 0；
- [ ] release binary 不含实验 route、fixture 字符串或 unknown action；
- [ ] 正式 `/api/frame` 继续拒绝 `0x4/0x7..0xF`；
- [ ] 公共 C++ validator/display 继续拒绝未知码；
- [ ] release build 的正式六色正例保持通过。

### 15.2 fixture

- [ ] 两个生成器逐 byte 相等；
- [ ] frame 精确 307200 字节；
- [ ] 只有白和当前 binary 唯一候选码；
- [ ] 白 `606208` px、未知 `8192` px；
- [ ] 未知像素只在两个固定 ROI；
- [ ] full/CS1/CS2 SHA-256 与 manifest 一致；
- [ ] 默认 mapping 下双 DTM 相等；
- [ ] 单 bit、单坐标、nibble、mapping 或面积变化均使 SHA 门禁失败；
- [ ] U04 build 无法引用 U07 fixture，反之亦然。

### 15.3 arm/job

- [ ] 无 arm、过期 arm、stale nonce、错误 test ID 均拒绝；
- [ ] 任一 execute 尝试先消费 arm；
- [ ] 请求体、hash、自检或排队失败后 arm 不能复用；
- [ ] 同一 test ID 重启后仍不可复用；
- [ ] 从 `ARMED` 到 `RECOVERY_CONFIRMED` 全程持有全局 EPD refresh lock；
- [ ] 正式/legacy/启动/定时刷新及其他客户端六色 job 均 fail closed；
- [ ] queued/running job 时拒绝第二 job；
- [ ] HTTP timeout 后没有自动 POST；
- [ ] boot、timer、Wi-Fi reconnect 不产生 job；
- [ ] MCU reset 转入 `FAULT_LOCKED`；
- [ ] immutable report 与 test/job/operation/build/hash 精确绑定。

### 15.4 恢复和失败安全

- [ ] 未完成人工 review 时不能进入 recovery；
- [ ] 电气异常时不能自动恢复；
- [ ] recovery 最多一套且每步为固定已知码 job；
- [ ] 恢复失败锁死下一 test ID；
- [ ] 日志、探头或测量 setup hash 缺失时 fail closed；
- [ ] 模拟 PON/DRF/POF BUSY 异常时无自动重试。

## 16. 实现前审查门

以下全部满足后，才可向用户请求实现实验固件：

- [ ] EC0～EC4 已完成，D 原厂六色和恢复资格可靠；
- [ ] C 阶段测量系统、安全链和所有绝对门已 GO；
- [ ] 有专用牺牲屏，黄金参考屏不执行未知码；
- [ ] 第 4 节 layout 和第 5 节 hash 已独立复核；
- [ ] 私有 fixture-only 驱动入口设计完成，不放宽正式 guard；
- [ ] release/U04/U07 build 分离和静态门禁设计通过；
- [ ] 一次性 arm、持久 consumed、reset/network fault 行为通过模拟测试；
- [ ] 用户明确批准是否实现；
- [ ] 若实现需要修改 `src/epd_driver.*`，用户明确批准该精确范围。

实现完成后仍不得自动执行硬件。COM8 刷写、断电、上电、电源确认、指定 test ID、
刷新后确认、恢复和最终断电均是独立授权门。

## 17. 当前状态

| 项目 | 状态 |
|---|---|
| F 离线设计草案 | READY FOR USER REVIEW；NOT USER-APPROVED |
| 固定 ROI/面积 | DESIGN FROZEN；待实现前复核 |
| hash | OFFLINE VERIFIED；待实验 build 再复核 |
| 实验固件 | NOT IMPLEMENTED / BLOCKED |
| release guard 修改 | NONE |
| 正式 API 修改 | NONE |
| `src/` 修改 | NONE |
| Hardware tested | NO |
| 刷写/上电/刷新授权 | NONE |
| 下一步 | 用户审查；不进入实现或硬件 |

本文件的完成只表示离线安全设计可以评审，不表示 C、D、G 或任何硬件门已经通过。
