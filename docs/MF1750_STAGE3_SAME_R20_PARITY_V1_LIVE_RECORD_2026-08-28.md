# MF1750 阶段三 same-R20 parity V1 真屏记录

日期：`2026-08-28`  
最终状态：`STOPPED AT BATCH1 ORDINAL 1 / CAMERA-RELATIVE REPEAT MISMATCH CANDIDATE`  
当前现场：`RELAY COMMANDED OFF / INDEPENDENT WHITE CONTAINMENT SEALED / WHITE BASELINE BLOCKED BY UNDEREXPOSURE / ELECTRICAL STATE NOT PROVEN`

## 1. 结论先行

G-1 固定相机几何、Hub2 relay rebind 和 G0 factory-OTP 白场，都已完成并通过各自的
预定门。Batch1 V1 固件写入、J2-OFF 诊断和 ordinal 1 AA 动作的协议层也通过：它在
同一 boot 中恰好调用一次 driver，产生一次 visible refresh，无 timeout 或 driver failure。

但 AA atlas 左右配对相机门没有通过。在一张同步原图和三张 relay commanded OFF 后的
保留复拍组成的四帧中，
code1 和 code2 的左右 camera-relative CIE76 均为 `4/4` 帧超过 `6.6031868` 探索门限。
按预定 fail-closed 规则，Batch1 V1 已在 ordinal 1 终止；ordinals 2–4 未执行且禁止执行。

这个结果不等于“已证明两个控制器或两半屏硬件不一致”。它只是固定相机、未经绝对标定且
未消除左右位置/照明偏差的重复候选。本次不认定新颜色，不认定绝对色差，也不认定 SPI 总线
实收数据已完成逻辑分析仪级验证。

## 2. 现场边界与 relay rebind

操作者在 `2026-08-28` 明确确认：继电器实体未变，CH1 的 `COM1→NO1` 接线未变。
rebind 只接受 USB location 由 `Port_#0004.Hub_#0001` 到 `Port_#0004.Hub_#0002` 的变化；
以下字段保持不变：

- model：`ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z`；
- VID/PID：`1A86:7523`；
- PnP instance：`USB\VID_1A86&PID_7523\5&230B5917&0&4`；
- port：`COM14`；
- serial：`ABSENT-CH340-NO-ISERIAL`；
- channel/contact：`1 / COM1-NO1`。

rebind seal：
`.test-output/hardware/MF17506_RELAY_REBIND_20260828_HUB2/relay-rebind-seal.json`  
文件 SHA-256：`c92aba1f6676a7d204fcffa5f5ed6112a14a58e4ecc7cf2959ff4bce8906ab94`。

该 seal 只是身份重绑与 commanded-state 证据；继电器无负载侧电压/电流回读，所以始终保留
`electrical_state_proven=false`。

## 3. G-1 固定相机与几何锚

G-1 在不刷屏、不动继电器的条件下封存。相机身份和设置为：

- camera：`48MP-USB-CAMERA-VID32E4-PID4801`；
- instance：`USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000`；
- mount：`MF1750-G1-PREVIEW-20260828-A`；
- `4000×3000 / MJPG / 15 fps`；
- focus=`79`，exposure=`-3`，white balance=`4600`，手动设置。

几何分析得到 `128/128` 格 support、`128/128` homography inliers、RMSE=`1.1362767 px`、
P95=`1.7799213 px`；它只是固定相机下的几何/P0 锚。

| G-1 文件 | 文件 SHA-256 |
|---|---|
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/g1-locked-full-panel-p0-20260828.jpg` | `0f2486edfc18be990545fcc4f1fdc2ed5c87df7a8f034929493f3c6eb01b0f3f` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/g1-locked-full-panel-p0-20260828.capture.json` | `15576558059402b74c506af015a5ae328605dc5824630f7d378784e5ad7e85cb` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/g1-locked-full-panel-p0-20260828.grid-analysis.json` | `b60a2f5f66fe72334cde472306291a3bc69555ede083e6d59a03eb97284517a1` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/g1-locked-full-panel-p0-20260828.anchor.json` | `2f585718d431f489f3d7c8224e4a9f2a1b7a03d7b0f1e8496bf44b13f466df64` |

## 4. G0 factory-OTP 白场与时间重复噪声

G0 使用独立 V3 successor，没有重试旧 V2 的不可覆盖 diagnostic FAIL：

- contract：`1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227`；
- BIN：`789200 bytes / 3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb`；
- ELF：`13215844 bytes / 2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797`；
- app-only flash/verify：PASS；
- J2-OFF diagnostic：`4 GET / 0 POST / 0 visible refresh`，PASS；
- boot nonce：`ff476515e2b82e97`；
- factory-OTP white：`complete_pass`，`1` driver call / `1` visible refresh，无 retry/recovery/autochain。

白场后在相机、焦点、曝光、白平衡和安装不变的条件下拍三帧，没有增加刷新。白场视觉审查
verdict=`PASS`、confidence=`high`：旧 128 格、彩色块、轮廓、底边黑线及离散残留未见。
相机画面仍有轻微灰/粉空间色偏，因此这是全屏干净白健康门，不是绝对白点认证。

三帧产生的 factory-white 时间 repeat-noise 基线为：

- baseline ID：`ceade72ca367c82fafd7746c26066b745399e37ab196410eda64f38cebcc6174`；
- sample count：`180`；
- median camera-relative CIE76：`1.1764706`；
- P95：`2.2010623`；
- maximum：`2.7452381`；
- classification：`LOCKED_CAMERA_FACTORY_WHITE_REPEAT_NOISE_BASELINE`；
- `absolute_white_proven=false`，`calibrated_de00_proven=false`。

| G0 主证据 | 文件 SHA-256 |
|---|---|
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_SUCCESSOR_20260828_V3/app-only-single-boot-flash.json` | `e78092887caa53d4996ed171c72c9a99d98526b8d570c3c4005015c791faa911` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_SUCCESSOR_20260828_V3/j2-off-diagnostic.json` | `b3a442b55e6a4d1a5bb61995365b70c4d1305adaeb1ce23ac50ee698c9c88da5` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_SUCCESSOR_20260828_V3/action-01-factory-otp-white.json` | `bf1db8dfa8336e9aa44724dbba6a875d40740f06f14b1871154565dac898df47` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_SUCCESSOR_20260828_V3/g0-factory-white-repeat-noise.json` | `2d860017b2affca4fd82ea384549a6b0f9f0facbcc7219406abd977ad983e63a` |
| `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_SUCCESSOR_20260828_V3/camera-action-01.analysis.json` | `a12a0d1a37b1217a28275f37847ee4657908457404eab0ba6dd2cac838a36e87` |

三张白场原图 SHA-256 依次为：

1. `f2e072862f65d1371d6509ab1990f7e80e6b142d7c76340282d2bf91cc6a88c0`；
2. `6f8b6e70cf3ecbb3137d3571ca75c4c4b65baa3e7d850ad939b716a3014e8625`；
3. `2ecfe56c3d66bb68eef672916f417ee51fe5f95137c2b58e8f7ea33598b20b37`。

## 5. Batch1 V1 部署与 ordinal 1 协议结果

Batch1 固定身份：

- campaign：`EC5_SAME_R20_PARITY_2X4_V1`；
- contract：`718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8`；
- BIN：`801712 bytes / d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f`；
- ELF：`13299408 bytes / bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6`；
- offline build report：`docs/MF1750_SAME_R20_PARITY_V1_OFFLINE_BUILD_2026-08-28.json`，
  文件 SHA-256=`b0c6cdb7f152ef5de86d46496a266efebb4b56c2f9d3e35ce0ca40c57e3d1067`。

J2 commanded OFF 条件下，对 COM8 仅写入 app partition `0x10000`，write 后内建 hash 验证和
独立 verify 均 PASS；不改 bootloader/partition table/NVS。flash helper 之后只启动应用一次。
fresh J2-OFF diagnostic 为 `4 GET / 0 POST / 0 claim / 0 visible refresh`，boot nonce=
`347fc2a51e1a00de`。

ordinal 1 固定动作：

- role：`SAME_R20_ACTIVE_ACTIVE_ATLAS`；
- action ID：`7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4`；
- descriptor ID：`246de22c2a8f450752a960230bd88de7a62ce42300c7f6401bbb562d07ef76ba`；
- frame SHA-256：`79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6`；
- outcome：`complete_pass`；
- driver calls：`1` for action / `1` total；
- visible refreshes：`1`；
- PON/DRF/POF：`261 / 33911 / 151 ms`；
- total driver time：`46580 ms`；
- timeout/failure：`none / none`。

主 evidence：

| Batch1 文件 | 文件 SHA-256 |
|---|---|
| `.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/app-only-single-boot-flash.json` | `084fb55abe1bec9fd23d643d2ea665bed6f2b52b83a4b2ae61a21363485f8847` |
| `.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/j2-off-diagnostic.json` | `d88497a9cd31237e686583d154df7d35635e8d576e964dfe4f12c2a58ef8d373` |
| `.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/action-01-active-active-atlas.json` | `80a6e7172967e15a87756a2d9c3478a821b357ed2d8d39845e9d5bf15dfef751` |

## 6. firmware/source parity 审阅及边界

执行 action 的自述字段给出：

- `controller_payloads_byte_identical=true`；
- CS1/CS2 R20-535 SHA-256 均为
  `716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`；
- CS1/CS2 R21-704 SHA-256 均为
  `24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`；
- CS1/CS2 DTM FNV-1a 均为 `2716343749`；
- profile 均为 `LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535`。

静态源码审阅另外确认：

- `src/epd_config.h:37` 起定义单一 canonical 1024×600 frame，CS1=左半、CS2=右半，
  无 flip 或 nibble swap；
- `src/epd_driver.cpp:1213` 起只由通用 stream 函数选择 controller source half，并计算
  DTM FNV；
- `src/ec5_runtime_lut_same_r20_parity_v1_driver.inc:279` 起广播同一 global PWR/PLL/TRES；
- 同文件 `:303` 起的 controller upload 函数仅以 `secondController` 选择 CS，而
  active/commented profile 选择是同一参数；
- 同文件 `:350` 起对两控制器构建相同 2×4 code atlas；
- 同文件 `:777` 和 `:781` 先后以同一 `useCommentedGlobal` 参数上传 CS1 与 CS2。

因此，本记录可以声称 **firmware/source parity PASS**，即编译来源、两侧 payload 身份、
调用分支与 DTM 身份对称。这是审阅结论加 action 自述，不是独立 sealed bus trace。
逻辑分析仪未到位，所以不能声称两条 CS 在物理 SPI 总线上逐字节收到了相同内容；也不能
排除 CS 电气路径、controller silicon、面板半屏、供电或光学位置差异。

## 7. AA 相机证据

图面为每个控制器同一个 `2×4` atlas，code 顺序为第一行 `0,1,2,3`，第二行
`4,5,6,7`；两侧 DTM 字节一致。原始同步照片：
`.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/camera-action-01-aa.jpg`，
SHA-256=`46e4c6e3855857be2b795b64e064ecfba11f973a9a93017478a29e574be55863`。

单帧几何门 PASS：`14` 个对比格，最低要求 `8`，所有内部 patch valid fraction=`1.0`。
原始帧的 8 个左右配对 CIE76 依次为：

`6.6214, 10.4459, 10.6046, 9.1553, 2.2361, 3.9415, 3.6792, 4.5233`。

原始单帧只能发出候选，不能排除照明或 JPEG/相机噪声。因此在 relay commanded OFF 后，
使用相同锁定相机连拍三张 `locked_retained_retrospective` 照片，没有新的刷新。三张照片
SHA-256 分别是：

1. `16ff03396c9c59b91c6b5f4273bc2eb0bfd4aaa8b097647dd9d25052e6db43ac`；
2. `0067d14acb81f16cf750fd832d02cbec7e7e890aa014327cc34c65764dfdd8de`；
3. `928112fbb4b7afb6524b7b845f06a982e58f07a7138b06e7b612a85b72fc79bb`。

四帧 report：
`.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/aa-four-frame-retained-repeat-report.json`  
文件 SHA-256：`172f3570e33701c9cf10a8d9f3c4fbb4c146e8fa8ee26d6f5a3e2f369809b67d`  
canonical integrity：`665f204c878303a3a0d5fc8de85545dc679a776a8e2eee420747ca887ed7ac02`。

门限为 `max(4.0, 3.0 × 2.2010623)=6.6031868`；至少 `3/4` 帧超门才是 repeat-majority。

| code | 四帧 CIE76 | median | 超门帧 | 分类 |
|---:|---|---:|---:|---|
| 0 | `6.6214 / 4.9533 / 4.9533 / 4.7472` | `4.9533` | `1/4` | 未解析到可重复 mismatch |
| 1 | `10.4459 / 8.5707 / 7.3114 / 7.3114` | `7.9411` | `4/4` | repeat mismatch candidate |
| 2 | `10.6046 / 10.5424 / 10.5424 / 10.5424` | `10.5424` | `4/4` | repeat mismatch candidate |
| 3 | `9.1553 / 3.3964 / 3.3964 / 4.8513` | `4.1239` | `1/4` | 未解析到可重复 mismatch |
| 4 | `2.2361 / 2.1483 / 2.1483 / 2.0381` | `2.1483` | `0/4` | 未解析到可重复 mismatch |
| 5 | `3.9415 / 3.8127 / 3.0881 / 3.0881` | `3.4504` | `0/4` | 未解析到可重复 mismatch |
| 6 | `3.6792 / 3.8526 / 3.5406 / 3.5406` | `3.6099` | `0/4` | 未解析到可重复 mismatch |
| 7 | `4.5233 / 5.1365 / 5.7779 / 5.1365` | `5.1365` | `0/4` | 未解析到可重复 mismatch |

四帧的最终状态为 `CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE`，并显式保留：

- `controller_mismatch_proven=false`；
- `hardware_mismatch_proven=false`；
- `controller_equivalence_proven=false`；
- `absolute_colour_proven=false`；
- `qualified_new_colour=false`。

## 8. 照明/位置混杂的解释边界

G0 的三帧白场噪声是同一空间 patch 在不同时间的变化，它用于限定 camera/JPEG 时间噪声。
它没有建立“左侧同一 code 位置”与“右侧同一 code 位置”的空间照明补偿模型。相机固定也不意味半屏
照明、视角、盖板反射和光学灰阶完全对称。

因此，code1/2 的稳定左右差异支持“必须停止 V1 并解混”，但不支持在本记录中进一步判定：

- 差异必然由 controller silicon 造成；
- 差异必然由物理总线发送/接收不一致造成；
- 差异是新的稳定颜色；
- 两半屏的所有 code 都不等价。

## 9. 停止裁决与当前屏状态

原 V1 计划的后续动作是 ordinal 2 白、ordinal 3 CC atlas、ordinal 4 白。由于 ordinal 1 相机门失败，
三项全部为 **forbidden / not executed**。尤其不得使用 ordinal 2 作 recovery，否则会继续消费已终止
campaign 的正常序列，违反原定“失败后独立 containment”边界。

四帧复核后，COM14/channel 1 已是 commanded OFF，并生成 exact-bound OFF query receipt：
`.test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1/relay-channel1-off-post-aa-repeats.json`，
文件 SHA-256=`c523566cf21a518108e27f47ceb7a030d3e19205a0abab0fa283f36461568c35`。

receipt 记录 `off_gate_passed=true`、`contact_switch_performed=false`、`electrical_state_proven=false`。
电子纸双稳态保留 AA 2×4 atlas，这不与 relay commanded OFF 矛盾。

## 10. 后继唯一路径

下一次现场不恢复 Batch1 V1，而是三个彼此隔离的步骤：

1. 使用独立 `Same-R20 AA-abort factory-OTP white` campaign 做唯一白收容；
2. relay commanded OFF 后，在新白态上重拍固定相机白场，作为与新位置格对应的空间参考；
3. 使用独立 `same-R20 4×8 V2` 只执行一次 position-balanced AA atlas。

V2 在每个控制器内放置 `4×8=32` 格，code0..7 各出现四次，且两侧使用相同 code
布局、同一 active tuple 和字节一致 DTM。它的目标是检查差异是否随半屏持续，还是随行/列/照明
位置变化；它不是颜色资格测试。相关离线入口为：

- `tools/mf1750_same_r20_aa_abort_white_v1_once.py`；
- `tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py`；
- `tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_pack.py`。

任一动作都必须先完成独立的固件冻结、app-only flash/verify、fresh J2-OFF diagnostic 和不可覆盖
claim；不允许 retry、recovery、fallback 或 autochain。只有 V2 解混结果足以解释 AA 差异后，才能
决定是否重新设计 CC 比较；本 V1 不再执行。

## 11. 证据语义约束

- 本记录没有证明或命名新颜色。
- CIE76 是固定相机的相对值，不是色卡标定后的 CIEDE2000。
- 三张 retained 复拍证明相机重复看到同一保留画面上的差异，不独立证明中间没有任何
  物理事件；该时序由 action binding、capture sidecar 和外部 relay receipt 共同限定。
- relay OFF 是绑定身份的 commanded/query 证据，因无负载侧传感，不是电气断电证明。
- firmware/source parity 不等于 bus parity；bus parity 不等于 controller/panel physical parity。

## 12. AA-abort 白收容与欠曝白基线停点

Batch1 V1 终止后，独立 `EC5_SAME_R20_AA_ABORT_WHITE_V1` 完成了唯一
factory-OTP 白收容。其 action 结果为 `complete_pass / COMPLETE`，boot nonce=
`93d389c6f5323145`，恰好 `1` driver call 和 `1` visible refresh，没有 failure/timeout。
action 证据为：

`.test-output/hardware/MF1750_SAME_R20_AA_ABORT_WHITE_20260828_V1/action-01-factory-otp-white.json`  
文件 SHA-256：`57785a566bccf35a1f404d4e01e5bf9f107df906c3a8f193009d21ee52c66cb7`。

该 action 与 claim 已永久消费并封存；后续不得重放它。动作后已将 COM14/channel 1
置为 commanded OFF，并在 `2026-08-28T18:58:04.900+08:00` 生成新的独立
exact-bound OFF query receipt：

`.test-output/hardware/MF1750_SAME_R20_AA_ABORT_WHITE_20260828_V1/relay-channel1-off-pre-camera-baselines.json`  
文件 SHA-256：`3e081f18831ace5103175b03f214f7f64aea04610dddc2abb4d3b7757ab20e38`。

receipt 仅证明绑定继电器的 commanded/query state 为 OFF，不证明负载端无压；
`electrical_state_proven=false` 保持不变。电子纸以双稳态保留 factory-OTP 白。

随后尝试在 relay commanded OFF 状态下建立 V2 白场空间基线，但现场既有照明
未处于 G-1/G0 拍摄状态，两张画面严重欠曝：

| 照片 | 文件 SHA-256 | mean RGB | RGB 低端剪切 `<=5` | 裁决 |
|---|---|---|---|---|
| `camera-white-off-baseline-01.jpg` | `6dee3450fab6f2a76503a325c44e29a1c9fdff8b55a47fc707aa177a1064fb8c` | `16.63/19.29/24.75` | `31.32%/32.37%/29.77%` | `INCONCLUSIVE / EXCLUDED` |
| `camera-white-off-exposure-probe-m1.jpg` | `2d048206284a40d7792f8d059fd2a52fd2b648021469fd44a868ecddb4ee8876` | `16.87/19.53/25.06` | `31.24%/32.36%/29.76%` | `INCONCLUSIVE / EXCLUDED` |
| `camera-white-off-lighting-recheck-01.jpg` | `bec950835b2174f3b994d68dd24e45501714f0655f6a6829204a6e6598c040da` | `15.64/18.52/23.58` | `31.61%/32.54%/29.94%` | `INCONCLUSIVE / EXCLUDED` |

对应 capture sidecar 文件 SHA-256 分别为
`5069a94e22f16939e2ed4b39b30951632afc01161d901e77b8e4e1370cc067f2` 和
`d68bac7380b6316755f4d37ef8115878dce1f18e6ba91d40ad895af59cedb2d7`；两者均绑定上述
已封存 action/boot/camera/mount，assessment 为 `INCONCLUSIVE`。

`m1` probe 请求将 software exposure 从 `-3` 改为 `-1`，但 DirectShow 返读的帧前和
帧后实际 exposure 都仍为 `-3`；其亮度指标也没有实质改善。因此两帧只作
欠曝诊断记录，**不纳入 Same-R20 4×8 V2 的白场定量基线、位置/照明补偿或任何
颜色裁决**。下一步是恢复 G-1/G0 已有照明，不移动相机、镜头或机位，不改动
`focus 79 / exposure -3 / WB 4600` 锁定 tuple，重拍三张 relay-OFF 白场照片并
通过质量门后，才可部署和执行一次 position-balanced 4×8 V2。

`19:12` 的自动照明复查仍没有恢复亮度；其 sidecar SHA-256 为
`58b6c1b3007183e6980da2d0d9ab3de8a5cc228ba10fbf5323d57700d4159260`。该复查只打开
相机，没有访问设备网络、COM8、继电器控制、flash、reset 或 visible refresh。
