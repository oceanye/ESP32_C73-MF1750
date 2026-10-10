# MF1750 阶段三 Same-R20 4×8 V2 真屏记录

日期：`2026-08-28`  
最终分类：`POSITION_DEPENDENT_INCONCLUSIVE`  
最终现场：`SCREEN CLEAN WHITE / RELAY COMMANDED+QUERY OFF / ELECTRICAL STATE NOT PROVEN`

## 1. 结论先行

Same-R20 4×8 V2 的部署、J2-OFF 诊断和唯一 atlas 动作在协议层完整通过。
左右控制器在固件和设备 report 中使用相同 active R20/R21 及 DTM payload。

但相机分析在 controller 对比之前就触发了位置一致性失败：同一 transport code 在
同侧四个位置的最大离散 P95 为 `43.8646 ΔE76`，高于 `6.6032` 门限。因此：

- 不得声称 controller parity 已证明；
- 不得声称 controller mismatch 已证明；
- 不得声称 SPI 总线实收数据或电气链路等价；
- 不得声称已发现或排除新的稳定颜色。

正确结论是：协议动作通过，但颜色证据受位置／照明／光学梯度混杂，故为
`POSITION_DEPENDENT_INCONCLUSIVE`。

## 2. 锁定现场与相机参数

- relay：`COM14 / channel 1 / COM1→NO1`；
- relay identity：`ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z / 1A86:7523`；
- PnP：`USB\VID_1A86&PID_7523\5&230B5917&0&4`；
- USB location：`Port_#0004.Hub_#0002`；
- camera：`48MP-USB-CAMERA-VID32E4-PID4801`；
- camera instance：`USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000`；
- mount：`MF1750-G1-PREVIEW-20260828-A`；
- capture：`4000×3000 / MJPG / 15 fps / focus 79 / exposure -6 / manual WB 4600`。

现场灯打开后，原 exposure=`-3` 严重过曝，因此经显式 probe 将本批正式对比固定为
`-6`。三张前置白和三张 atlas 的 requested/effective tuple 完全一致。顶部中央仍有
镜面反光，所以不做绝对色度结论。

## 3. 前置白场基线

独立 AA-abort factory-OTP white 已在早先的唯一动作中 `complete_pass`。继电器回读 OFF 后，
用 exposure=`-6` 连续拍摄三张正式白场照片。三帧 panel median 均为 `72.941 L*`，
时间噪声 P95=`0.0 ΔE76`，低于 `6.6031868 ΔE76` 门限。早先欠曝、过曝及校准 probe
只作诊断，未进入这份正式分析。

三张白场照片 SHA-256：

1. `150143556ec9aff3439fb6534a3057db8b3a2fc97f42a54c1e816d004a3b13b4`；
2. `a2f030bf2634d11c5c9d1a2779778234d10e11309c884a5a9f86ecbb8a1e88bd`；
3. `d91800d70c927e90e32d24c9ff3c3b9d54e1cf5033651f0d1969074ae3f9f26f`。

## 4. V2 部署与唯一 atlas 动作

- BIN：`798560 bytes / f6472a407bea4fa2abc6547f329959b0795e86b932118892634f8f48dca38dd8`；
- ELF：`13285392 bytes / 834f89b7cc854508622d74940e8c9266e774a4919980151ed2ff0dbd4f073ed6`；
- app-only flash/verify：PASS，只写 `0x10000`，不动 bootloader/partition table/NVS；
- J2-OFF diagnostic：`4 GET / 0 POST / 0 claim / 0 visible refresh`；
- boot：`f2eeb7703ab4694c`；
- action：`2eef95155b78ee27b13e5971c40618106779495c80e0e3ef833eb2484f420476`；
- outcome：`complete_pass / COMPLETE`；
- driver/visible refresh：`1 / 1`；
- PON/DRF/POF：`260 / 33911 / 151 ms`；
- total driver：`46612 ms`；
- failure/timeout：`none / none`。

两侧 R20/R21 哈希、完整 DTM payload 和 DTM FNV 均一致；这是 firmware/device-report payload identity，
不是逻辑分析仪取得的 SPI bus trace。该 action/claim 已永久消费，不得重放。

## 5. 位置平衡分析

三张 relay-OFF retained atlas 均通过曝光和几何门，每帧左右合计 `64` 格有效。
白场时间噪声 P95=`0.0`。但位置一致性门失败：

| code | CS1 四位置离散 P95 | CS2 四位置离散 P95 |
|---:|---:|---:|
| 0 | 2.979 | 22.565 |
| 1 | 2.397 | 24.615 |
| 2 | 8.108 | 20.244 |
| 3 | 43.865 | 28.636 |
| 4 | 17.610 | 23.573 |
| 5 | 13.719 | 14.703 |
| 6 | 21.876 | 19.256 |
| 7 | 7.891 | 27.112 |

门限为 `6.6032 ΔE76`，最大值为 `43.8646`。controller comparison 的 common offset=`2.4827`、
maximum interaction=`33.0592`、normalized LR=`34.2067`、raw LR=`61.7867` 均只能作诊断。
由于前序位置门已失败，这些字段不能被用来声称 controller parity 或 mismatch。

三张 atlas 照片 SHA-256：

1. `16418ce2cf40eeafe98a713c3bcd3e0e76c9decc875b54c77d2923d0081f9c67`；
2. `272aa9e591d7eb419bfeb4aed95005d36e27b099bdfe39a1b047d15db8dc7fb2`；
3. `e670f8d0d3530cf5f9143c2cfe90debaa69a659beae1ca7323c91f408f6c178b`。

## 6. 独立白收容与最终状态

独立 Guard factory-OTP white containment 的 BIN SHA-256 为
`41fbf8a5c60f749ef1321a1397552c0e84696aae7975c5571d1b8b085cd9667d`。app-only flash/verify 和 fresh
J2-OFF 诊断 PASS；同 boot=`0ccd16ae6cd35a01` 完成唯一 factory-white action：

- action：`ff0c34170da3d20660e35dc79a57107ff42123979f38f488b9609b1292a9ba0b`；
- outcome：`complete_pass / COMPLETE`；
- driver/visible refresh：`1 / 1`；
- PON/DRF/POF：`180 / 21701 / 141 ms`；
- no retry/recovery/autochain。

finally 关断后，exact-bound relay query 在 `2026-08-28T20:44:47.749+08:00` 返回 CH1 commanded
`OFF`。该 receipt 文件 SHA-256 为
`982f3b302d12da01d27f4b4c1f303dd668cb30fe42608e1d095ae784b1cbd1b4`，但继电器没有负载侧传感器，
所以 `electrical_state_proven=false`。

相机在同一 mount 和 exposure=`-6` 下拍摄最终白屏。原图审阅为 PASS：全屏干净白，
旧 4×8 atlas、彩色区块、条纹、中心接缝或边缘残留均未见。顶部中央镜面反光使绝对色度不可用，
但不遮挡这次 clean-white 检查。

## 7. 主证据哈希

| 证据 | 文件 SHA-256 | canonical integrity |
|---|---|---|
| V2 flash | `4abdd21caf911760fe3a88ec5e52dfa2afd096f479b0c08278065b136046760a` | `2aacd3633ab36d16ceeddaf0051b32bb0aabdbd3c0589bbc03f24f8bac22dcc5` |
| V2 diagnostic | `8510fac9c56d83255f5069a963ebd6abb4a7b18314c868c5a00b4707b01b5679` | `b2a6945923318a4a89989b075e484650347196b6f89043ebdece0712e714ecdc` |
| V2 atlas action | `102eb9b0816bc0c6676ab042fa0750963cff183b97f2abcc50350a2810df17a0` | `46afe463155f1a7c808232ba597ced1317701b682c5a1e4007cb417d77a5f052` |
| 位置分析 | `6cf9e68658fe1f1ed350feb4390a28991f4f77d2a5b9b945e35fc8ffae84c038` | `bcac63210ec5ef2fef137392d1fc263bd504092b7513a41b7b212dc4b816c959` |
| 后置白 action | `c37b8bb53b0ed69ede485260f8e1c34cfcabd988c5dd2a830ea74a9995a3f5f2` | `ea6257805002ee6beac69687e7c9dab3249b6ca4ced8863800c97da814283d0e` |
| 后置白照片 | `041638ff9a79910aae00df8bee0439250a80d0b7624a87a9cad1b1fd1ef71827` | — |
| clean-white 分析 | `efd0885c36c87ee09072c19d13f636f5f9baf272871a382dac8098979c8a7345` | `01e40202521917a097e46ebc65f598baef50366d14aec370e1617308a09528de` |
| evidence bundle V2 | `7aeb2a7f6099a95ee87912abe3ee0806c8ef49793fb366709eaecc82b25ce9db` | `0513038490ee33b9f692dc4485da2504ef6fb7daeccf3a53e22954f9b5607112` |

evidence bundle ID：
`417e70cc38fa7c656ebeedaf371d2204cd6eea5eb72c77ceb7664ecf5ce5f71c`。V2 包额外深度绑定了后置白动作之后、
相机拍摄之前的 exact-bound OFF receipt，并验证三份 OFF receipt 的 relay identity/rebind 一致性与
时间顺序。早先生成的 `evidence-bundle.json` 保留为不可覆盖的过渡记录，权威包为
`evidence-bundle-v2.json`。

## 8. 后续方向

V2 的直接后继不是重放该 action，而是先改善光学与位置可识别性：

1. 将环形或柔性光源移到镜面反射之外，在屏幕平面建立均匀照明；
2. 使用 24 色卡／中性灰卡建立位置与白平衡校正，不再只依靠三张白场时间噪声；
3. 用比当前更大的单色 ROI，或用一次可识别的位置交换专项，先分离位置效应；
4. 只对通过位置门的候选做左右对比、repeat、持久性和 24 色卡标定；
5. 逻辑分析仪到位后，再用 bus trace 将 firmware payload identity 升级为总线实收证据。

在以上条件改善前，本次可作为自动化流程和 fail-closed 判据的成功验收，不能作为颜色规格表。
