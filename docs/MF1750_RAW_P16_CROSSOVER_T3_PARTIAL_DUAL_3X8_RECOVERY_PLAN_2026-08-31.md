# MF1750 RAW-P16 T3 固定机位局部双侧 3x8 筛查与恢复计划

> 状态：`T3 V2 COMPLETE / PARTIAL CAMERA REVIEW SEALED / W4 WHITE COMPLETE / RELAY OFF`
>
> 结果更新时间：`2026-08-31 16:56 +08:00`

## 1. 当前现场状态

- 48MP 相机机位固定，左右两半屏同时可见；正式证据范围只覆盖双侧 top `3x8`，右下、底边和
  第四行仍不可用。
- T3 V1 的 `1 GET / 0 POST / 0 claim / 0 ARM / 0 EXECUTE / 0 refresh` 失败仍是不可重放的历史
  终态；fresh T3 V2 已使用全新 route/campaign/action/NVS/output 完成。
- T3 V2 action `73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5`
  已 `complete_pass / COMPLETE`，恰好 `1 driver / 1 visible refresh`，无 retry/recovery/autochain。
  action evidence：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2/action-01-position-balanced-atlas.json`，
  bytes/file/canonical SHA-256=`64782 / e7ba8d10f5428372e0462835274cfdebeef5f19d0b8ab354fdcdfadf534a4ec3 /
  4070a4381d7641f98bef0c84ed2fc2f885a5795ba43599f62812d9e4918c2b4e`。
- action 后 relay COM14/channel1 已保护性断开并独立回读为 `commanded_state=OFF /
  off_gate_passed=true`；`electrical_state_proven=false`。receipt：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2/relay-post-action-protective-off.json`，
  bytes/file/canonical SHA-256=`1807 / 009bce63d8d0b86de7bd6083a1d5c39656a64f1d1f77a4135fd7a8e0c3d428a2 /
  e566c2dee32a24b5a2f8c990c1bb7b653e5c40fa5fca806f1abbe27836874397`。这是 W4 执行前的
  中间态：当时屏幕按双稳态保留 T3 V2 atlas；该画面随后已被唯一 W4 白恢复替换。
- W3 partial 白参考 1 帧与 T3 partial atlas 3 帧均已 `PARTIAL_ACCEPTED` 并封存；离线局部
  profile/code 判读已深重放通过并终态为 `PARTIAL_CAMERA_SCREEN_REVIEW`。随后独立 W4 V2
  factory-OTP white 已完成且 relay 已保护性 OFF。当前保留画面在锁定 48MP 相机帧中未见
  atlas 色块，但该帧按合同只声明 partial/retained/INCONCLUSIVE，不是 full-white seal。

### 1.1 V1 地址拒绝根因与 V2 入口（历史与已完成）

- 失败时使用的 `192.168.1.7` 已由 Windows 本机地址表证明属于主机自身，不能再作为 ESP32
  候选；因此 `WinError 10061` 不能解释成目标固件拒绝了正确地址。
- 被动邻居表把精确 ESP32 MAC `A4-CB-8F-D9-FC-D4` 映射到 `192.168.1.11`，但状态是
  `STALE`。它只缩小下一次搜索到一个候选，不证明在线、新 boot、当前 app 或 HTTP listener。
- 被动封存 evidence：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2_PREP/passive-ipv4-mac-candidate-binding.json`，
  bytes/SHA-256=`2850 / 4c2fe6c04c90119a776099a187340fa91f8e7cb0b92482ada232af201ebe8fd8`；
  `fresh_binding_passed=false`，且 `ping/http/device-api/mutation/refresh=0`。
- 新工具 `tools/mf1750_exact_ipv4_mac_binding_once.py` 只接受一个 literal IPv4，先拒绝任何本机
  地址；未来只有显式选择 active 模式时才发一次 ICMP，并要求 post-probe exact MAC 与新鲜
  neighbour state。它不做 DNS、网段扫描、fallback、HTTP 或设备 API；任何失败都写入新的
  O_EXCL terminal output，不得删除重跑。当前离线测试为 `7 passed`。
- 上述 successor 路径后来按顺序完成：relay OFF -> V2 app-only write/verify/single boot ->
  对唯一 `.11` 候选执行一次 active exact-MAC gate -> V2 四 GET -> raw `BUSY=1` -> 单次 action。
  active binding evidence 位于
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2/active-ipv4-mac-binding-once.json`，
  bytes/file/canonical SHA-256=`3425 / a99c16d5110a6e1822b3ab43aed89365ad3fbb12657183537ce967989fd89920 /
  3a34b238a4aba731bd65ebed38cf16f33277e340579252a2d5de279155173e36`。这份一次性绑定不授权未来
  复用该地址；`.7` 仍必须被本机地址门拒绝。

## 2. 局部证据模式

新模式 ID：`PARTIAL_DUAL_3X8_TOP_ROWS_V1`。现有 full-panel 模式保持原样，不放宽其语义。

```text
CS1: logical rows 0,1,2 x all 8 columns = 24 cells
CS2: logical rows 0,1,2 x all 8 columns = 24 cells
per frame = 48 cells
per controller/profile/code = 3 spatial replicates
three retained frames = 9 samples per controller/profile/code
```

当前 setup-only JPEG 投影的预览 block quads：

```text
CS1 ~= [(826,536),(1911,528),(1959,1328),(783,1368)]
CS2 ~= [(1999,527),(3006,520),(3140,1287),(2055,1324)]
```

这些数值最初只用于证明方案可行；随后 W3 白参考和三张 T3 的四次 admission 各自把同一组
数值明确绑定到各自 exact sealed JPEG。数值相同不允许未来照片复用；任何新 JPEG 仍必须在
admission 时绑定该图自身的 CS1/CS2 block quad。

## 3. 强制门

- capture sidecar 必须为 `partial_panel`，`full_panel_visible=false`、
  `full_panel_uncropped=false`。
- 两侧必须同时包含 rows `0..2` 和全部 8 列；缺侧、缺 code 或 controller 左右顺序错误均拒绝。
- 两个 quad 必须凸、不重叠、在 `4000x3000` 内，CS1 位于 CS2 左侧。
- 48 个投影 cell 必须全部在图内，最小投影边长 `>=24 px`。
- W3 的 48 个局部白样本全部 `L* >=25`。
- 白参考与三张 T3 的全部两两比较必须同时满足 8 个对应 block 角点最大漂移 `<=15 px`、
  RMS 漂移 `<=8 px`；任一超限即拒绝，不放宽为 REVIEW。
- exact camera path、mount、requested/effective settings 和尺寸必须全等；三张 T3 的
  capture ID、JPEG hash 和时间必须不同。
- 左右白场存在明显亮度偏差，每个 cell 仅能使用同侧同位置 W3 白基线做平场归一化。

## 4. 证据权限

可输出：

- 局部 48 格几何和三副本／三帧稳定性；
- 各 controller/profile/code 的同侧白归一化中心与左右 DeltaE 筛查；
- 选定 ROI 内的条纹、残留、失焦和裁切粗检。

不可输出：

- 64 格或四空间副本 PASS；
- 底边、第四行、全屏 seam 或屏外异常 PASS；
- full-panel/full-white camera seal；
- 绝对色值、qualified colour 或正式 profile-following 结论。

所有超出范围的项目必须写为 `NOT_EVALUATED_OUTSIDE_SELECTED_ROI`；没有新 partial human
schema 时，profile-vs-side 仍为 `NOT_EARNED`。

### 4.1 已封存的 partial 结果

- W3 white attempt 1 与 T3 attempts 1/2/3 均完成独立 `acquire -> admit`，结果均为
  `accepted=true / outcome=PARTIAL_ACCEPTED / offline_only_admission=true`；admit 阶段
  `camera_invocations_during_admit=0 / hardware_io_performed_during_admit=false`。
- 三张 T3 JPEG bytes/SHA-256：
  `942848 / b0aa9633fe48e7dda5d919550e2f9746488671214d36b936a650ff720b894385`、
  `937416 / 0f55a7c4741f3240f8a47e2bbc083213a1c916ba7505ad90996578665c72fccc`、
  `936503 / 49a003d78afcf11c26fcb4c9306cab129f9babb05a1c19954000a2029ee8a152`。
  三帧相机 instance/mount/settings/`4000x3000` 全等，capture ID、JPEG hash 与时间各不相同。
- 全部白参考/T3 两两几何记录为 `max=0 px / RMS=0 px`，在 `15 px / 8 px` 硬门内；该事实
  只覆盖每帧双侧 48 个 selected cells，不覆盖 row 3、底边或 full panel。
- O_EXCL sealed bundle：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_CAMERA_PARTIAL_DUAL_3X8_V1/partial-capture-bundle.json`，
  bytes/file/canonical SHA-256=`29748 / e02c213b27415bfa2d2dc7dcdf761a60d9c855a15ab917e0a763e7c6b8efed8b /
  57da5577b83522c2b790c48b34dc1a3c247b7a349475092f2db8f581ccafd88b`；其 frozen capture
  contract=`6494 / 18f0d644af399bd22180737f8ca3df0a9a2ea3f1a9e6eb7a36009fee525044d1 /
  ca82f1b7f0174c9d7d5dbcee45e4bf95597f1b47f43518b37adfb7b8831b9cc2`。
- bundle 明确保留 `formal_full_panel_evidence=false / profile_following_decision_earned=false /
  qualified_colour_count=0 / w4_post_white_full_screen_seal_earned=false`；它不是 W4 white seal。

### 4.2 局部 profile/code 筛查与 W4 收容结果

- `partial-profile-camera-screen.json` 已生成并通过独立 `validate-partial` 深重放；
  bytes/file/canonical SHA-256=`270928 /
  6376c4bfedad01edfe898fb3c3126e7c22089b3644bbe9d128aee44712489d51 /
  e8a840ad491e855d068acc8665606195fdced6ea749d0c022183a2bef486a39e`。终态为
  `PARTIAL_CAMERA_SCREEN_REVIEW / machine_confidence=HIGH`：48 组空间三副本最大 ΔE00=`5.587931`
  为 PASS；三帧时序最大 ΔE76=`4.211125`、水平带最大 ΔE00=`4.323357`、单 cell residual
  maximum ΔE00=`5.566369` 落入 REVIEW；三帧相位对齐和控制码 2/3/5 均 PASS。
- 相机相对的 active-vs-commented code 差异 ΔE00：code0=`56.325990`、code1=`55.459843`、
  code4=`42.058774`、code6=`50.389034`，显示明显跨 profile 差异；code2=`2.000122`、
  code3=`0.836058`、code5=`1.269330` 为控制一致，code7=`10.824445` 为较小差异。它们仅是
  `CAMERA_RELATIVE_DESCRIPTIVE_ONLY`，不命名绝对颜色，也不产生 qualified colour。
- W4 V2 app-only write/verify/single boot、fresh exact-IP/MAC binding、J2-OFF 四 GET 与 raw BUSY
  门均通过；action `7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4`
  已 `complete_pass / COMPLETE / campaign_complete=true`，恰好 `1 ARM / 1 EXECUTE / 1 driver /
  1 visible refresh`，driver total=`35022 ms`、PON/DRF/POF=`180/22531/140 ms`，无
  retry/recovery/autochain。action evidence bytes/file/canonical SHA-256=`30300 /
  11196c4cc5dade801d99b647e08fcccee02521acfbe0d3785c77d05a4697fb98 /
  74ff3af94ebb4c2f58270d7cd9672a359b2e21332149a8a422feaa3967fd753d`。
- action 后 COM14/channel1 已独立 `commanded_state=OFF / off_gate_passed=true`；receipt
  bytes/file/canonical SHA-256=`1807 /
  f5d53a3c2374fbce9758a81dd75da869a2b56f021877c16d27296d7a8fe3f46e /
  f7d734ff497accb411b65c45a66a2f0c7523419623da4f2e85670fca679f42ed`，且仍无负载侧反馈，
  `electrical_state_proven=false`。
- relay OFF 后 exact 48MP retained frame 已 O_EXCL 封存并深验：JPEG=`658852 /
  2808039da93adfe44a27104576af003c164a61db266ff823d33fe7a548e5cb56`，sidecar
  bytes/file/canonical SHA-256=`5458 /
  8a88f4aafdca7e529b97286cb480e86076ea03da6eccd848a4ff3ee1122d3f38 /
  83372788f20fe4c0845f3c1f42f52142f078cb3a05e02ae37e800848ab7baa61`。帧中未见 atlas
  色块；但因暗光、遮挡且 capture scope 明确为 partial，它只能作安全粗检，不能升级成正式
  full-panel clean-white seal。

## 5. 执行进度与下一步

1. 原流程的 endpoint 绑定、fresh V2 app-only 写入/验证、四 GET、raw `BUSY=1`、单次
   ARM/EXECUTE/driver/visible refresh、保护性 OFF 与三次 `acquire -> admit` 均已完成。
2. sealed partial bundle 与局部 profile-code 判读均已生成；判读为 REVIEW，但已经确认哪些 code
   对跨 profile 敏感。不得升级为 formal profile-following 或 qualified-colour 结论。
3. W4 factory-OTP white 已完成并保护性 OFF；partial retained 白图只作安全粗检。若需要正式
   full-white seal，仍需合格全屏证据或人工明确确认。下一轮不再重放 T3/W4 action。

## 6. 停止条件

任一诊断、BUSY、claim、action 或 relay 门失败，立即命令／保持 relay OFF，不重试、不恢复、
不自动串联下一可见动作。V1 首 GET 失败的历史终态未被重试；fresh T3 V2 与独立 W4 V2 均已
一次性完成。当前停止边界为 W4 后 relay `commanded OFF`、屏幕按双稳态保留白场、partial retained
白图已封存；没有合格全屏证据或人工明确确认前，仍不得记作 formal full-white seal。
