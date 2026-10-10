# MF1750 同 R20 位置平衡 4×8 V2 真屏流程

日期：`2026-08-28`  
离线状态：`BUILD PASS / LIVE NOT EXECUTED BY THIS PREPARATION`  
campaign：`EC5_SAME_R20_PARITY_4X8_V2`

## 1. 这次只回答什么

V1 的 2×4 单位置左右配对容易把固定相机照明梯度、视角和面板空间差异混入
controller 差异。V2 在两个控制器内写入字节完全相同的 4×8 atlas，每个 transport
code 在每侧占四个分散位置；三张断电保持照片因此给出每个 `code/controller` 的 12
个样本。

V2 campaign 只有一个 action、一个 driver call、一次全屏可见刷新。factory-OTP white
前置和后置均属于独立 containment campaign，不在 V2 action table 中，不允许 V2 自动
刷白、重试、恢复或链式执行。

本批不会证明绝对颜色，不会证明 SPI 总线实际发送字节，也不会证明电气意义上的双控制器
完全等价。

## 2. 固定 atlas

每个 512×600 controller 的布局均为：

```text
x = 20 + 60*c, c=0..7
y = [44, 180, 316, 452]
cell = 52×100
gap = 8×36
background = code 7
border = none

row0 = 0 1 2 3 4 5 6 7
row1 = 6 7 0 1 2 3 4 5
row2 = 5 4 7 6 1 0 3 2
row3 = 3 2 5 4 7 6 1 0
```

- frame SHA-256：
  `1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23`
- 每侧 DTM SHA-256：
  `2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb`
- active/active 完整 tuple ID：
  `4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820`

## 3. 冻结身份与固件

- contract：
  `9e70a54e0ed1c3756357b2f3026e5651a7d1246294da6915397573b9b897a1ff`
- descriptor：
  `7f668842d3d4fca179049b309c298d0ff2d359c6bdd26550704e6929f1108cda`
- action：
  `2eef95155b78ee27b13e5971c40618106779495c80e0e3ef833eb2484f420476`
- NVS：`sr20p4v2 / cursor_s4v2 / boot_s4v2`
- API：`/api/ec5/same-r20-parity-4x8-v2/*`
- BIN：`798560 bytes`，
  `f6472a407bea4fa2abc6547f329959b0795e86b932118892634f8f48dca38dd8`
- ELF：`13285392 bytes`，
  `834f89b7cc854508622d74940e8c9266e774a4919980151ed2ff0dbd4f073ed6`

## 4. 真屏顺序

下面每一项必须由主控显式释放；没有 retry、fallback、recovery 或 autochain。

1. 用一个独立、fresh 的 factory-OTP-white containment 固件执行前置白屏。不得把已经
   消耗的旧 ordinal 当成新白屏动作。
2. 继电器命令 OFF 并查询确认；保存 exact-bound OFF receipt。
3. 相机锁定 G1 的同一 camera/mount/settings，拍三张 `OFF white`，每张都保存照片与
   `.capture.json`。必须使用 `capture-retained`，其 sidecar 的
   `capture_binding` 必须精确为 `locked_retained_retrospective`；普通
   `live_synchronized`、`retrospective_unproven` 或混合 binding 均不能封包。
4. J2 保持 OFF，app-only flash V2；按项目既有 single-app-boot flash/verify 合同，
   不增加 reset/chip-id/monitor。
5. J2 OFF 下运行四个 GET diagnostic：

```powershell
python tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py diagnose-j2-off `
  --base-url http://192.168.1.11 --confirm-j2-off
```

6. 主控确认前置白屏和三张 OFF white 已完成后，打开 J2，只执行唯一 atlas：

```powershell
python tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py run `
  --base-url http://192.168.1.11 --ordinal 1 `
  --confirm-j2-on --confirm-external-pre-white
```

7. 刷新完成后命令继电器 OFF 并查询确认；保存新的 OFF receipt。屏幕保持 atlas，拍三张
   `OFF retained atlas`，同样使用 `capture-retained`。两组三帧必须绑定各自的
   pre-white/V2 action，且满足 `action result created_at <= exact OFF receipt queried_at
   <= capture started_at <= frame_retrieved_at <= completed_at`；两组必须使用完全相同的
   camera instance、mount、requested settings 和稳定的 effective settings。
8. 运行分析器并生成不可覆盖结果：

```powershell
python tools/mf1750_same_r20_position_balanced_4x8_analyzer.py `
  --g1-analysis .test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/g1-locked-full-panel-p0-20260828.grid-analysis.json `
  --white-photo <white-1.jpg> --white-photo <white-2.jpg> --white-photo <white-3.jpg> `
  --atlas-photo <atlas-1.jpg> --atlas-photo <atlas-2.jpg> --atlas-photo <atlas-3.jpg> `
  --output <position-balanced-analysis.json>
```

9. 无论分析分类如何，最后都必须用另一个独立、fresh 的 factory-OTP-white
   containment action 刷白，并取得 clean-white `PASS` 视觉门。V2 不负责这次刷新。
10. 用 `mf1750_same_r20_position_balanced_4x8_evidence_bundle.py` 绑定前后 white、两份
    OFF receipt、六份照片/sidecar、V2 action、分析结果和后置 clean-white 门。
    后置 clean-white 分析必须以文件 SHA、canonical integrity、action ID 和 capture
    sidecar 明确绑定该次 post-white action；仅有 `PASS` 文本不足以封包。

## 5. 固定判定算法

阈值不随结果自动放宽：

```text
prior white temporal noise P95 = 2.2010622719387043 ΔE76
T = max(4, 3 × prior P95) = 6.603186815816113 ΔE76
```

分析先把每格转换为 camera-relative Lab；从相邻四个无边框背景 strip 得到 local
background；再减去相同位置三张 OFF white 的 local-contrast residual。每个
`code/controller` 用 12 个归一化样本求中心，并用四个位置的三帧中位数检查位置离散。

fail-closed 顺序：

1. 六帧任一 rectified panel 中位亮度低于固定 `L*=25`，或三张 atlas 任一帧的
   `P95-P05` 亮度范围低于固定 `12 L*`：
   `LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID`。这两个门限不从候选照片重算；其保守依据为
   已锁定 G0 三帧最低 panel median `67.8431 L*`、G1 panel median `54.1176 L*` 和
   G1 `P95-P05=42.7451 L*`；
2. 新 OFF white 时序 P95 超过 `T`，或几何/背景无效：
   `WHITE_BASELINE_OR_GEOMETRY_INVALID`；
3. 任一 code/controller 的四位置离散 P95 超过 `T`：
   `POSITION_DEPENDENT_INCONCLUSIVE`；
4. 去除跨 code 共同 side offset 后，任一 code×controller interaction 超过 `T`：
   `CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE`；
5. interaction 均通过但共同 side offset 超过 `T`：
   `RELATIVE_PALETTE_PARITY_PASS_SIDE_OFFSET_INCONCLUSIVE`；
6. 原始左右有超阈值，而归一化 interaction/common offset 均通过：
   `POSITION_OR_ILLUMINATION_DOMINATED`；
7. raw、normalized、interaction 和 common offset 均通过：
   `CAMERA_RELATIVE_PARITY_CANDIDATE`。

所有分类仍是 camera-relative；名称中的 `PASS` 或 `CANDIDATE` 不能改写成绝对色或电气
认证。

## 6. 离线复核命令

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run `
  -c platformio.runtime_lut_same_r20_parity_4x8_v2.ini -t clean
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run `
  -c platformio.runtime_lut_same_r20_parity_4x8_v2.ini

python tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py dry-validate

python -m pytest -q `
  tests/test_mf1750_runtime_lut_same_r20_parity_4x8_v2.py `
  tests/test_mf1750_same_r20_position_balanced_4x8_analyzer.py `
  tests/test_mf1750_same_r20_position_balanced_4x8_evidence_bundle.py
```

本次离线准备结果：clean build `PASS`、dry validate `PASS`、focused pytest
`14 passed`、Ruff check/format `PASS`、`py_compile PASS`；准备过程未访问设备、网络、
COM、继电器，未 flash/reset/refresh。
