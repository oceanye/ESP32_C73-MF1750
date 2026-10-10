# MF-1750 可见刷新数值门模板

状态：`DRAFT / VISIBLE_REFRESH_NO_GO`

> 本模板不提供器件安全额定值，也不构成上电或刷新授权。任何 `TBD`、缺失资格证据、
> 未签审查或超出 allowlist 的 action 都使 `VISIBLE_REFRESH_GO=NO-GO`。历史 1 A ceiling
> 不是已证明的安全额定值，不能直接抄作批准值。

## 1. Profile 身份与适用范围

| 字段 | 值 |
|---|---|
| profile_id / version | TBD |
| 创建时间 / 时区 | Asia/Shanghai |
| 板号 / 面板型号与序列号 | TBD |
| R15 / R16 | R15 removed / R16 0 Ω：待确认 |
| firmware build tag / binary SHA-256 | TBD |
| driver API / CS mappings | TBD |
| 允许 action / endpoint / fixture hashes | TBD |
| 明确排除的 action | T6 内置页刷新、R1 >1 MHz、未知码、LUT/waveform/partial/high-voltage |
| 隔离网络与唯一测试主机 | TBD |
| 依据的原理图/BOM/器件资料/既有实测 artifact | TBD |

## 2. 测量链资格

| 链路 | asset/model/serial | 校准证书/有效期 | 带宽/采样 | U95 / lag | 资格 artifact SHA-256 | 结果 |
|---|---|---|---|---|---|---|
| TP1 电压 | | | | | | NO-GO |
| 输入电流 | | | | | | NO-GO |
| 面板温度 | | | | | | NO-GO |
| Q1/Q2/L1/L2/控制器温度 | | | | | | NO-GO |
| 时间/BUSY | | | | | | NO-GO |

## 3. 数值门与动作

| 项目 | 冻结规则/值 | 触发动作 | 来源/审查说明 |
|---|---|---|---|
| TP1 target | 3.30 V | 偏离 profile 即停 | panel evidence |
| TP1 low | `Vmeas - U95 < 2.4 V` | 安全时 POF，实体切断 J2-1 | panel operating range |
| TP1 high | `Vmeas + U95 > 3.6 V` | 立即实体切断 | panel maximum |
| PSU OVP setting | TBD V | 保护动作后锁存/人工复位 | 必须计入 overshoot 与 U95 |
| PSU OCP setting | TBD A | 立即实体切断 | hardware review required |
| Hardware current limit | TBD A | 进入 CC 即停止 | hardware review required |
| Input-current absolute stop | TBD A / bandwidth TBD | 立即实体切断 | manufacturer/hardware review required |
| New-job temperature warning | 任一点实测 `≥45℃` | 不开始新 job | frozen process gate |
| Panel hard cut | `Tmeas + U95 + lag ≥50℃` | 立即实体切断 | panel operating limit |
| Component hard cut | TBD | 立即实体切断 | ratings/assembly review required |
| BUSY assertion | PON/DRF/POF 在 250 ms 内出现 | 缺失即 fail closed，无重试 | current driver contract |
| Job deadline | 180 s | 实体切断，只读恢复，不重 POST | current host contract |
| Power-off proof | TP1 `≤0.10 V` 持续 `≥5 s` | 未满足不得接触/重上电 | frozen process gate |

## 4. 假负载急停资格

锁存切断必须默认安全、不会自动复位；每次记录触发方式、切断时间、残压曲线和人工复位。

| run | 代表性负载/设定 | 触发 | 切断时间 | TP1 残压达到并保持 `≤0.10 V` | 自动复位 | raw artifact SHA-256 | 结果 |
|---|---|---|---|---|---|---|---|
| 1 | | | | | 必须 NO | | FAIL |
| 2 | | | | | 必须 NO | | FAIL |
| 3 | | | | | 必须 NO | | FAIL |

## 5. Action allowlist 决定

| task/action | exact endpoint / hashes | 决定 | 附加条件 |
|---|---|---|---|
| T5 1 MHz MAP | `/api/frame`; `0x9D04142D/0xF26832DD/0xFE199FF5` | NO-GO | 每次独立用户授权 |
| T4 100 kHz MAP | `/api/diagnostic/map-orient-v1-slow`; 同上 | NO-GO | 默认跳过；单独授权 |
| T7 experimental/formal bars | vertical/horizontal 固定 hashes | BLOCKED | 测量合同与新版 runbook 前不得执行 |
| T6 built-in page refresh | device page `/api/frame` | BLOCKED | 缺 one-shot arm/deadline |
| T8 calibrated C4 | host app `/api/frame` | BLOCKED | calibrated palette 与 C4 frozen tree |

## 6. 审查与放行

```text
All TBD fields resolved: YES / NO
All measurement chains qualified: YES / NO
Emergency dummy-load trials 3/3 PASS: YES / NO
Network isolation verified: YES / NO
Action allowlist exact and minimal: YES / NO
Hardware reviewer / time / evidence:
Safety reviewer / time / evidence:
Profile decision: VISIBLE_REFRESH_GO / VISIBLE_REFRESH_NO_GO
```

即使 profile 决定为 GO，每个可见 refresh run 仍须先取得“仅 J2-1 上电”授权；上电后
确认电压/CV/current/temperature/idle 与精确 task/action/frame/build/mapping，再取得
只允许一个 POST 的第二次授权。本 profile 不提供批量或后续 run 的自动授权。
