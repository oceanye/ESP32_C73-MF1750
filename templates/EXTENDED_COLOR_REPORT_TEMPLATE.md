# MF-1750 扩展颜色测试报告模板

> 本模板只记录证据，不构成上电、刷写、刷新、未知码、LUT 或电压实验授权。

## 1. 报告身份

| 字段 | 值 |
|---|---|
| Report ID | `TBD` |
| Stage | `D / E / G / H / I` |
| Test ID | `TBD` |
| Run ID | `TBD` |
| Date / timezone | `TBD / Asia/Shanghai` |
| Operator / reviewer | `TBD / TBD` |
| Git commit / branch | `TBD / TBD` |
| Firmware build tag | `TBD` |
| Binary SHA256 | `null` |
| Hardware tested | `NO` |
| Overall result | `NOT RUN / PASS / FAIL / ABORTED / FAULT LOCKED` |

## 2. 范围与授权

- 本次实际执行：`TBD`
- 明确未执行：`TBD`
- 刷写 COM8 授权 ID / 时间：`null / null`
- 断电确认 ID / 时间：`null / null`
- 上电授权 ID / 时间：`null / null`
- 电源正常确认 ID / 时间：`null / null`
- 指定帧发送授权 ID / 时间：`null / null`
- 刷新后画面、电流、温度确认 ID / 时间：`null / null`
- 最终断电及 TP1 接近 0 V 确认 ID / 时间：`null / null`

没有当前对话中的明确授权时，以上字段必须保持 `null`，不得用计划、旧授权或推断填充。

## 3. 被测件与固定配置

| 字段 | 值 |
|---|---|
| Panel model / serial | `MF-17506-M009F-T / null` |
| Resolution / packing | `1024x600 / 4bpp packed / 307200 bytes` |
| Controller | `2 x SPD1657B rev 0x04` |
| PCB / straps | `MF1750 Rev A1 / R15 removed / R16=0 ohm` |
| CS mapping | `CS1=(0,0,0,0); CS2=(1,0,0,0)` |
| SWC | `EPD_PIN_SWC=-1; no physical J2-1 cut-off` |
| Waveform | `on-chip OTP; ID/version/temperature bin unknown` |

## 4. 帧与数据身份

| 项目 | 字节数 | SHA256 | FNV-1a |
|---|---:|---|---|
| Application frame | `307200` | `null` | `null` |
| CS1 DTM | `153600` | `null` | `null` |
| CS2 DTM | `153600` | `null` | `null` |

- ROI layout/version：`TBD`
- ROI machine-readable file / SHA256：`null / null`
- Asset manifest / SHA256：`null / null`
- Run JSON / SHA256：`null / null`
- Optical JSON / SHA256：`null / null`
- Electrical JSON / SHA256：`null / null`
- Event/recovery JSON / SHA256：`null / null`
- 原始 RAW、示波器、测色、热像、环境数据路径与 SHA256：见 asset manifest；未采集项必须为 `null`。

## 5. 测量系统资格

- 仪器清单、序号、固件、校准证书及到期日：`TBD`
- 量程、采样率、带宽、探头倍率、deskew、测点图：`TBD`
- 45/0、illuminant、observer、孔径、照度、CCT：`TBD`
- RAW 相机/镜头/曝光/ISO/焦距/白平衡/距离：`TBD`
- 光学、电气、温度和几何 R&R / U95：`TBD`
- 实体急停、硬件限流、默认断开的 J2-1 锁存开关假负载验证：`TBD`
- C 阶段资格结论：`NO-GO`，直至所有必填项和绝对阈值齐备。

## 6. 时序、电气与热结果

| 指标 | 基线下界/上界 | 实测 | U95 | 结论 |
|---|---|---|---|---|
| PON BUSY / ms | `null / null` | `null` | `null` | `NOT MEASURED` |
| DRF BUSY / ms | `null / null` | `null` | `null` | `NOT MEASURED` |
| POF BUSY / ms | `null / null` | `null` | `null` | `NOT MEASURED` |
| Peak input current / A | `null / null` | `null` | `null` | `NOT MEASURED` |
| Energy / J | `null / null` | `null` | `null` | `NOT MEASURED` |
| TP1 minimum / V | `2.4 / 3.6 supply envelope` | `null` | `null` | `NOT MEASURED` |
| TP3 VPH / V | `null / null` | `null` | `null` | `BLOCKED` |
| TP5 PREVGL / V | `null / null` | `null` | `null` | `BLOCKED` |
| TP6 VPC / V | `null / null` | `null` | `null` | `BLOCKED` |
| Panel maximum / degC | `<50 including uncertainty/margin` | `null` | `null` | `NOT MEASURED` |

不得把 `sum(V*t)` 称为电流或电荷。未知的 SPD1657B 高压允许范围必须保持 `null`。

## 7. 光学与转换结果

- 光学 t0：`POF BUSY_N low-to-high + 60 +/- 5 s`
- 初始 Lab：`null`
- 最终 Lab：`null`
- Delta E00 / 均匀性 / 残影：`null / null / null`
- CS1/CS2 差异：`null`
- 空间位置差异：`null`
- 1 min / 10 min / 1 h / 24 h / 72 h 保持：`null / null / null / null / null`
- 6x6 transition profile 路径 / SHA256：`null / null`

所有未测值必须为 `null`，不得用目标色、模拟值或视觉印象替代测量值。

## 8. 异常、停止与恢复

- 异常：`NONE OBSERVED / TBD`
- 停止阈值触发：`null`
- 自动重试次数：`0`
- 恢复是否另行授权：`NO / authorization ID=null`
- 恢复序列：`black-white-black-white`（未授权时不执行）
- 恢复结果：`NOT RUN`
- 最终 J2-1 断电：`null`
- TP1 `<=0.10 V` 持续至少 5 s：`null`

电气、温度、高压或 BUSY 异常后不得把恢复理解为自动追加刷新；先急停/断电并评审。

## 9. 命令与退出码

| 时间 | 命令 | Exit code | 说明 |
|---|---|---:|---|
| `TBD` | `TBD` | `TBD` | `TBD` |

## 10. Go / No-Go 与签核

- 本阶段结论：`NO-GO`
- 允许的下一步：`仅离线分析 / TBD`
- 仍需的资料、设备或用户授权：`TBD`
- 执行人签核：`TBD`
- 安全审查：`TBD`
- 独立复核：`TBD`
