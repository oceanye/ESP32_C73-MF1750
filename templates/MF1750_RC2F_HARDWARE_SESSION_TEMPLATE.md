# MF-1750 RC2F 上机记录模板

> 从 `docs/RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md` 复制使用。
> 本模板不构成硬件动作授权。原始 JSON/log/照片放在同一 `.test-output` 会话目录。

## 会话身份

| 字段 | 记录 |
|---|---|
| session_id | |
| 日期/时区 | Asia/Shanghai |
| 操作者 | |
| Git HEAD | |
| `git status --short` 文件 | `git-status.txt` |
| runbook/template SHA-256 | `procedure-source-sha256.json` |
| C4 主机 commit/tree（仅 T8） | |
| 板号/硬件版本 | MF1750 Rev A1 |
| 面板型号/序列号 | |
| R15/R16 | R15 removed / R16 0 Ω：待确认 |
| ESP32/COM | ESP32-S3 / COM8：待确认 |
| firmware build tag | RC2F：待设备回读 |
| firmware.bin 字节/SHA-256 | |
| driver API | V3：待设备回读 |
| 设备 URL | 不写入共享版；本地记录位置： |
| 测试主机 / OS / 浏览器版本 | |
| 隔离网络边界 / 允许客户端 | |

## 仪器与安全

| 项目 | 型号/设定/校准/结果 |
|---|---|
| J2-1 电源电压 / U95 | 目标 3.30 V；实测：；U95： |
| J2-1 独立断开与刷写前残压 | 断开方式：；实测： V |
| limit profile ID/版本/SHA-256/审查人 | |
| OVP 设定/假负载验证 | |
| OCP/硬件限流/输入绝对停止阈值 | |
| 物理切断/急停假负载验证 | run 1：；run 2：；run 3：；锁存/人工复位： |
| 输入电流测量链/资格/U95/带宽 | |
| TP1 断电测量 | `≤0.10 V` 持续： s |
| 温度测量链/测点/U95/lag margin | |
| 光学仪器/几何（若使用） | |
| 环境温湿度 | |
| FPC/接线/R15-R16 复核 | |

## 任务门禁

| 任务 | authorization ID/time/exact scope | 前置通过 | 结果 | stop reason / 备注 |
|---|---|---|---|---|
| T0 离线冻结 | 不需要硬件授权 | | | |
| T1 物理预检 | | | | |
| T1a `FLASH_AND_NO_REFRESH_GO` | | | GO / NO-GO | |
| T1b `VISIBLE_REFRESH_GO` | | | GO / NO-GO | |
| T2 断电刷写 | | | | |
| T3 无刷新协议 | | | | |
| T4 可选 100 kHz MAP | | | NOT RUN / PASS / FAIL | |
| T5 1 MHz MAP | | | | |
| T6 网页预览 / 刷新 BLOCKED | | | PREVIEW ONLY | |
| T7 六色 pilot / formal BLOCKED | | | BLOCKED | |
| T8 C4 calibrated E2E | | | | |

## 每次可见刷新记录

复制本节，每个 run 单独填写。

| 字段 | 记录 |
|---|---|
| task/run ID | |
| J2-1 上电 authorization ID / 时间 / 授权人 / 精确范围 | |
| 精确 POST authorization ID / 时间 / 授权人 / endpoint+frame | |
| `VISIBLE_REFRESH_GO` profile ID/version/SHA-256/reviewer | |
| fixture / orientation / cold-start run | |
| 开始/结束时间 | |
| 刷新前 J2-1 断电秒数 | |
| 刷新前环境/板/面板温度 | |
| firmware build/API/binary SHA-256 | |
| endpoint / exact action / frame pattern | |
| CS1/CS2 mapping | |
| 输入文件 SHA-256（如有） | |
| packed frame SHA-256（如有） | |
| full FNV-1a | |
| CS1/CS2 DTM FNV-1a | |
| job_id / action / state / result | |
| operation_id | |
| one-shot arm / 手工单击限制证据 | |
| PON/DRF/POF/post-PSR BUSY | |
| sequence_ok / timeout_stage / BUSY 缺失字段 | |
| upload/stage/total timing | |
| PSU CV/CC、Vmin/Vmax、上下门 U95 PASS、Ipeak/Imean/U95（强制） | |
| Q1/Q2/L1/L2/控制器/面板最高温度 | |
| 方向/中缝/六码/残影 | |
| 异响/异味/热点 | |
| JSON/log/电气/温度 raw artifact 路径与 SHA-256 | |
| 照片/RAW 路径与 SHA-256 | |
| 人工结论 | PASS / FAIL / INVALID / STOPPED |
| stop reason | |
| J2-1 断电时间与 TP1 最终电压 | `≤0.10 V` 持续： s |

## C2 光学测量附表

只有正式分光测色结果才可用于 calibrated palette；相机结果必须标 `experimental`。
横条、竖条的每个独立冷启动 run 各复制一份本表；同一画面内的重复读数不等同于
独立刷新重复性。

```text
fixture/orientation:
cold-start run ID:
pilot/formal:
known previous frame/pattern/hash:
per-run authorization ID/time:
POF completed at:
J2-1 power-off at:
optical t0 anchor: POF BUSY_N low-to-high + 60 +/- 5 s
measurement order:
```

| code/name | 测点/顺序 | POF 后读数时刻/s | L* | a* | b* | repeats/SD | raw spectrum SHA-256 |
|---|---|---|---:|---:|---:|---|---|
| 0 black | | | | | | | |
| 1 white | | | | | | | |
| 2 yellow | | | | | | | |
| 3 red | | | | | | | |
| 5 blue | | | | | | | |
| 6 green | | | | | | | |

```text
Illuminant/result integration: D65
Observer: 2deg
Geometry: 45/0
Instrument asset ID/model/serial/firmware/aperture:
Calibration certificate ID/date/expiry:
Standard white tile certificate:
Same-day white/dark check:
Fixture R&R artifact/SHA-256:
Light source/lux/CCT:
Stabilization time:
Raw measurement artifact SHA-256:
measurement_id:
canonical artifact regular-file path/bytes:
canonical bundle/manifest rule version:
aggregation/rule version and reviewer:
U95 and qualification result:
```

## 会话证据收尾

```text
Artifact manifest path: ARTIFACT-MANIFEST.json
Detached manifest hash path: ARTIFACT-MANIFEST.sha256
Manifest covers SESSION, raw HTTP, JSON, logs, photos, electrical and temperature artifacts: YES / NO
Durable second-copy destination/media ID:
Post-copy detached attestation planned path:
SESSION freeze timestamp before manifest:
```

## 最终结论

```text
RC2F minimum regression (T0-T3 + T5): PASS / FAIL / INCOMPLETE
Optional T4 100 kHz diagnostic: PASS / FAIL / NOT RUN
RC2F built-in page preview: PASS / FAIL / NOT RUN
RC2F built-in page visible refresh: BLOCKED / NOT RUN
C2 experimental pilot: PASS / FAIL / NOT RUN
C2 calibrated palette ready: YES / NO / BLOCKED
C4 calibrated image E2E: PASS / FAIL / BLOCKED / NOT RUN
Hardware tested scope:
Excluded claims:
Remaining blockers:
```
