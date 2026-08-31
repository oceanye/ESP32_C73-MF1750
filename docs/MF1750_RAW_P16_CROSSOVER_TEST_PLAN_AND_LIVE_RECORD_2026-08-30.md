# MF1750 RAW-P16 跨 Profile 判因计划与实测台账

日期：`2026-08-30`
当前状态：`T1正式门FAIL / discovery-only T2 V2人工粗发现完成 / W3白收容PASS / T3+W4离线就绪未上机 / 候选未资格化`
当前面板：`clean factory-OTP white retained`
当前 J2：`commanded/query OFF；electrical_state_proven=false`

## 1. 文档用途

本文同时承担三项职责：

1. 记录 RAW-P16 从计划、固件身份、真屏动作、照片、分析到安全收尾的完整过程；
2. 固定下一轮 `AC↔CA` 跨 profile 判因实验，防止临场改变布局、阈值或结论口径；
3. 作为阶段性 GitHub 同步入口。原始照片和硬件 evidence 保留在本地
   `.test-output/`，仓库同步工具、测试、计划、结论及原始文件 SHA-256。

本文不是颜色标定报告。没有绝对色卡／光谱测量、独立重复和跨位置复现之前，任何结果都只能
称为相机相对候选，不能称为稳定新色、可用调色板色或灰阶。

后续自动流程采用“粗筛门”和“精确资格门”分层；粗筛结果只用于减少上机搜索空间，不能替代
资格门或颜色标定。

## 2. 固定设备与安全边界

- ESP32-S3：`COM8`，MAC=`a4:cb:8f:d9:fc:d4`，本轮设备地址=`192.168.1.11`；
- J2 继电器：`COM14 / channel 1 / Hub2`，精确重绑 seal SHA-256=
  `c92aba1f6676a7d204fcffa5f5ed6112a14a58e4ecc7cf2959ff4bce8906ab94`；
- 唯一允许的相机：`48MP USB Camera / VID_32E4:PID_4801`；
- 明确排除：`VID_1BCF:PID_0B15` 双目相机；
- 正式采集使用 DirectShow exact device path，在打开前、取帧中和取帧后复核身份；
- 固定采集参数：`4000×3000 / MJPG / 15 fps / AF=0 / focus=79 / AE=0.25 /
  exposure=-6 / AWB=0 / WB=4600 / warmup=5`；
- 继电器只有命令与查询反馈，没有下游电压／电流测量，因此所有 OFF 结论都保留
  `electrical_state_proven=false`；
- 每个真屏 campaign 使用 fresh identity、fresh NVS、一次性 action 和 no-retry /
  no-recovery / no-autochain。白场收容不得复用已消费 action。
- 继电器 ON 后 raw BUSY 准入电平可能延迟建立。relay ON receipt 或固定等待时间不等于
  action admission；必须先只读确认当前固件合同规定的 raw `BUSY=1`，才可 claim/ARM/EXECUTE。
  准入电平未建立时必须保护性 OFF，不得用动作尝试替代诊断。

## 3. 已完成：mixed-R20 RAW-P16 直接端点画廊

### 3.1 实际画面与波形

本轮主图不是 same-R20。两侧有意装载不同 R20 profile：

| 控制器 | R20 profile | 画面布局 |
|---|---|---|
| CS1 | `active535`，简称 A | 每侧 `4行×2列`，row-major code `0..7` |
| CS2 | `commented535`，简称 C | 每侧 `4行×2列`，row-major code `0..7` |

固定行映射为 `[C0,C1] / [C2,C3] / [C4,C5] / [C6,C7]`。因此本轮左右差异只能证明
“A 与 C 在当前左右物理位置下得到不同外观”，不能证明“同一波形在左右控制器上不一致”。

主 action：

- campaign：`EC5_RAW_P16_ENDPOINT_GALLERY_V1`；
- action ID：`9f5b84a12ac93c85898d2e843db6a5a4d174daa6ce0f18ffd8da974737f0a088`；
- contract ID：`f9b1f6b8052322bedc6b702cb895425e7c3dc5e2d1b7d9ae6e68edaa1ffc409d`；
- 结果：`complete_pass / COMPLETE / 1 driver call / 1 visible refresh`；
- 无 timeout、retry、recovery 或 autochain。

### 3.2 三张正式日光照片

三张照片都在 J2 OFF、面板保持 RAW-P16 atlas 时取得；相机身份与固定参数完全一致。

| 序号 | 本地文件 | 字节数 | JPEG SHA-256 |
|---:|---|---:|---|
| 1 | `camera-raw-p16-daylight-20260830-01.jpg` | 1,510,739 | `2b851b9d9677052d4b9b86493407671931c6409cfc30ef4d7895357bf7fd05a3` |
| 2 | `camera-raw-p16-daylight-20260830-02.jpg` | 815,310 | `0c6f0e4b53bf99fa7fbd1525b1edd4b31db0178bb554ef3053b54e29bc6d2027` |
| 3 | `camera-raw-p16-daylight-20260830-03.jpg` | 804,323 | `2eeac0b77c62cb2360afc81940d7ec555f3990e5d1f90b08fcdf4b5cf2bf6efe` |

这些照片不提交 GitHub；SHA-256 用来把文档结论绑定到本地原始 evidence。

### 3.3 专用照片分析

新增分析器：`tools/mf1750_raw_p16_retained_atlas_photo_analyzer.py`。它只接受当前
`4行×2列/控制器` 的 RAW-P16 布局，从当前照片重新拟合几何，不复用旧 same-R20 G1
homography。三帧都检测到 14 个格点，几何门通过：

| 照片 | 重投影 RMSE | analysis JSON SHA-256 |
|---:|---:|---|
| 01 | 1.071 px | `c03a746bc18c40694148841f5c3641d2c6347d7bfcf0a77d0befbc1b96c380c7` |
| 02 | 1.600 px | `b087f783b9d69a51aae0abe00ee79c866330e484675b71a447b78aa1f967077d` |
| 03 | 1.155 px | `375e58571eff6f1aa7c7d9e6c3b5302df3fee41ff4fde10cff491edff8cb2c9b` |

三帧对各 code 的 camera-relative CIEDE2000 范围如下：

| code | 三帧 ΔE00 范围 | 当前筛选标签 | 本轮用途 |
|---:|---:|---|---|
| 0 | 4.33–4.53 | 边缘差异 | 内部控制 |
| 1 | 3.80–4.14 | 边缘差异 | 内部控制 |
| 2 | 2.46–2.75 | 本批无明显差异 | 内部控制 |
| 3 | 43.16–43.45 | 明显候选 | 优先复核 |
| 4 | 8.56–9.13 | 明显候选、暗色 guard | 保护性复核 |
| 5 | 53.00–53.49 | 明显候选、本批最大 | 最高优先复核 |
| 6 | 19.79–20.19 | 明显候选 | 优先复核 |
| 7 | 48.77–49.37 | 明显候选 | 优先复核 |

这里的 ΔE00 由相机 JPEG 按 sRGB→Lab 推导，只用于相对筛选。当前固定结论仍为：

```text
qualified_colour_count = 0
qualified_new_colour = false
absolute_colour_proven = false
repeatable_colour_proven = false
stable_colour_proven = false
```

肉眼／相机可见的棕橙、粉红／洋红、浅绿／橄榄、紫色等外观均保留为候选族，不进入正式
palette。

## 4. 已完成：独立 factory-OTP 白场收容

RAW-P16 拍照后，使用独立 containment 固件关闭本轮画廊：

- firmware BIN SHA-256：
  `8c33085d0c9e0f03d651ad82a99a6336275f881fe9eb9e296cf526b5f80503c1`；
- contract ID：`1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14`；
- action ID：`12a146d8ad678165e1061fda3e7569743e28d663ee349b46ee900196b95d8cd6`；
- J2-OFF 诊断：`4 GET / 0 POST / 0 claim / fresh NVS / BUSY=0`；
- action：`complete_pass / COMPLETE / 1 driver call / 1 visible refresh`；
- PON/DRF/POF：`180 / 22521 / 141 ms`；
- action 文件 SHA-256：
  `22cb9455af83c29be4f9835218f8d3ae48302bb3b4ebfbb2f349e023b7eea690`；
- action canonical SHA-256：
  `7f787d594ec9b4eb57defc71da643cbb2fd7bea135ed3fad4251797ec5da66bf`；
- action 后 relay OFF query receipt SHA-256：
  `3c1376690142fdfa7996f49c00bdc916908c9fd90d7e8eedbbf56ba0f23a75eb`。

正式 post-white 照片：

- 文件：`camera-post-white-daylight-20260830-01.jpg`；
- 字节数：`1,325,904`；
- JPEG SHA-256：
  `ec2d22235f61d37fc7c10900ee626a77a30daddfde101da418aa8ce2ba012157`；
- capture sidecar SHA-256：
  `a40c3660b86c2fbba43218ba71f0eb2f9ff2cb14c485ff25cb7346fd4814b99a`；
- 视觉分析：`PASS / confidence=medium`，analysis ID=
  `fc8a577e150024f9c09a278ec8a21d4ba03d3cc3e740281f565c1536434ea890`；
- analysis 文件 SHA-256：
  `1e2274e08b200406a01e1f34ea1cdd45de7e3b59d960e021aca49713c26702d2`。

可见活动区为干净白，未见旧 atlas 色块、格边、色斑或固定横纵线。照片存在环境阴影和蓝偏，
所以本结论只证明“可见残留清除”，不证明绝对白点或色度值。

## 5. 下一轮：AC↔CA 位置平衡判因

### 5.0 离线就绪状态

已完成六个互相独立的镜像：`T1 AC / W1 / T2 CA / W2 / 可选 T3 AC-repeat /
W3 final`。六者具有独立 campaign、contract、action、NVS 和 claim/output root，不会自动
串联；T1/T2/T3 的 packed frame 及两侧 DTM byte-identical。当前冻结的 atlas contract 为：

- T1 AC：`6ea93bbd9be1d75e12bc6656614ac335faeb97aa1079ff04733b8babe7a247d7`；
- T2 CA：`ddcde0da8f5fec1b73924131a9a3e92fbee632430a041a72c56eea8a32b9d3cf`；
- T3 AC-repeat：`60f27623af8527f240173e457060ba008e61083f985e2b4a6ad4914a1f3705a0`。

独立复核已关闭现场执行安全门：atlas action 必须显式收到 J2-ON 确认；mutation 只接受 literal
private/local IPv4 并使用 no-proxy/no-redirect requester。主线程在原始工作树复跑：六镜像
`SUCCESS`，本地 build bootstrap postflight `artifacts_verified=true`，相关综合测试
`111 passed`，Ruff check/format PASS。全过程没有访问硬件、设备网络、COM、继电器或相机，
也没有 flash、reset 或 display refresh。

随后独立 short-path clean-checkout 审计纠正了“可复现”口径：source preflight 与六镜像编译
均 PASS，但 12 个精确 BIN/ELF 哈希 FAIL。ELF 嵌入绝对 checkout path，ignored 本地 Wi-Fi
配置也影响镜像；即使使用同一未披露的本地配置，T1 BIN 仍有 65 bytes 因嵌入 identity／
checksum 不同。共享 foundation 还混入多项历史 campaign，并存在依赖／测试闭包和 vendor LUT
再分发边界。因此该段离线封存时仅为 `LOCAL_OFFLINE_READY / NOT LIVE-EXECUTED`。随后 T1 与 W1
已按本文 5.1A–5.1C 实际执行并永久消费；T2/W2/T3/W3 仍未执行。GitHub 代码提交继续
`NO-GO`；已发布的计划和证据文档不等价于代码可复现性声明。

详细命令、身份与哈希见：

- `docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_RUNBOOK_2026-08-30.md`；
- `docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_OFFLINE_BUILD_REPORT_2026-08-30.md`；
- `docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt`；
- `docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_REPRODUCIBILITY_FILESET_2026-08-30.md`。

历史 same-R20 V2 的 frozen-artifact replay 单测因本地旧镜像与历史冻结哈希不同而被明确排除；
这不是 fresh crossover 逻辑失败，但也意味着本文不宣称全仓库测试全部通过。

### 5.1 核心问题

需要把 profile 效应与物理左右、固定位置、照明梯度和历史状态拆开。下一轮不直接继续枚举新
波形，而是先回答：同一个 R20 profile 换到另一控制器后，候选外观是否跟随 profile。

### 5.1A T1 AC 真屏实时记录（2026-08-30 13:34）

T1 已从“离线就绪”推进为“唯一真屏 action 已完成且永久消费”。本次没有自动进入 W1、T2
或任何后续动作：

- frozen BIN SHA-256=`86ec547ae7e4f0b8d74a383efa48d14346f20275c8b9452e13274c9f0496c800`；
- J2-OFF app-only flash/verify=`PASS`，flash evidence SHA-256=
  `eec952a0e5897bb100105ec907a69828495992faeecf356ce90a915596b80305`；
- J2-OFF diagnostic=`PASS`，boot=`17c47ed59ccb4a8b`，`4 GET / 0 POST / 0 claim /
  0 refresh`，diagnostic SHA-256=
  `226a99f3b88c1f1d138dd490ca8d721565a4c3de960ac26cc40b6cb52ef170f6`；
- action=`73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72`，
  `complete_pass / COMPLETE / 1 driver / 1 visible refresh`；
- PON/DRF/POF=`260/33921/151 ms`，driver total=`46622 ms`，无 timeout、retry、
  recovery 或 autochain；
- action 文件 SHA-256=
  `483b7ebd97367327a1a81a1826e76b228d3b9c9f850e8e809c5a0ca5faf34e09`；
- action 后 exact-bound relay query=`OFF / off_gate_passed=true`，receipt SHA-256=
  `c929e8eaa5adb54a6a0691962c4b09e89cd2ff5aad56c37da2fd5f7887e92cbf`，
  `electrical_state_proven=false`。

执行前另取一张 48MP retained white 机位／质量探针；相机 exact VID/PID 和所有固定设置通过，
JPEG/sidecar SHA-256=`48804b36...62c0d / fb396b0e...a24e`。照片整屏可见，但环境偏暗且左下
阴影明显，故只作 pre-white 连续性与机位证据，不作绝对色标定。当前面板在 J2 OFF 下保留
T1 atlas。`13:39` 三张正式 retained capture 已完成，文件绑定如下：

| 帧 | JPEG bytes / SHA-256 | sidecar bytes / SHA-256 |
|---:|---|---|
| 01 | `1413323 / 409a15c7c6a1af2709cf5c7e076e0a0d02cafa54aac9edc3fe827c67c46c1ce6` | `5276 / 8e16fdf00bebde85415529f8659e997e5ecfd912944d463f76db9b101a7063c9` |
| 02 | `1400857 / d20f806edeb5e20556d566f5d1de1ffe1acd0de6197ac1dceffc8f537a7c401a` | `5273 / b2e5633e178b3089d8c2239dcb5e356311882ead3192d92d9ac8db46dd66d9e8` |
| 03 | `1398316 / bd7e013ce63ae4f3ec4a2807e9791d3fc3d8a4b8aa7e005003efb4bf2b3fe3b1` | `5270 / 217f2345aa217c3d769eada1e899d78c5f956f5febfa9257df97638e91dd693b` |

三帧均锁定 48MP exact DirectShow path 和固定设置，设置写入／前后 readback／深校验通过，
read failures=`0`；整屏和色块可见，但环境偏暗，所以只能作同批 camera-relative 比较。专用
分析必须先决定流程分支：PASS 才允许 `W1→T2`；FAIL 仍必须做 W1 安全白收容，但禁止 T2/T3。
尚未产生任何合格新色、profile-following 或 controller parity 结论。

### 5.1B T1 三帧分析与位置门（2026-08-30 13:44–14:02）

专用分析器严格绑定 T1 campaign/contract/action、packed-frame SHA、双 DTM、48MP sidecar 和当前
照片四角；每帧输出 `64` 个格、每个 controller/code 四个位置。几何门均 PASS：panel area
fraction=`0.1991`，minimum projected cell side=`96.49 px`，全部 cell 在照片内。逐帧 analysis：

| 帧 | analysis bytes / SHA-256 |
|---:|---|
| 01 | `115994 / 77fdc1f1b82fec3837834c2243c22f4b10e5a75782392a6a3a9895f22ed292ec` |
| 02 | `116013 / 1e49d46a68b744df2d4f9b2752ada149a06b225a95b998eac3ddf9dde841bb48` |
| 03 | `116013 / 6e0d7fe41125e21e51709eb055bff86a112288838c8b205532a65e8a80159145` |

三帧使用同一 camera-lock，时间漂移很小；但同 code 四个位置的聚合门失败。固定门限为
`6.6031868158 ΔE76`，五个失败组如下：

| controller/code | consistency maximum ΔE76 |
|---|---:|
| CS1/code1 | 7.158026 |
| CS1/code2 | 8.963159 |
| CS1/code3 | 27.224901 |
| CS2/code3 | 6.655854 |
| CS2/code5 | 7.393698 |

正式结果为 `FAIL_T1_POSITION_TEMPORAL_PREFLIGHT / POSITION_DEPENDENT_INCONCLUSIVE`。
首版 O_EXCL 报告文件 SHA-256=`15cde97b902f9f1b123a898d18f85e0457b459e4c71a184a2ecba21fc2cb3d66`
保留不变；它曾把 W1 安全收容与 T2 推进合成一个字段。v2 通过 source path、file SHA 和旧 canonical
integrity 显式 supersede，文件 SHA-256=
`18856952b913768cc4c946daae1039ac37096ac5f0baa0b360bf48921c0aebc4`，canonical=
`619efdec2af37254a2a183a6212b96ec32b4733efa35e9236ff28b9872bc0005`，并固定：

```text
w1_containment_required = true
advance_to_t2_permitted = false
diagnostic_reason = POSITION_DEPENDENT_INCONCLUSIVE
qualified_colour_count = 0
```

只读局部白参考诊断进一步发现：失败点大多落在左下阴影。按每格上下白缝作局部线性 RGB 参考后，
五个明显位置候选的三帧中位 max ΔE00 从约 `5.96/5.95/24.95/7.13/6.20` 降至
`2.38/3.94/4.53/1.97/2.71`；其中四组与局部照明相关性很强，CS1/code2 仍保留 borderline
残差。该计算仅为 non-qualifying illumination diagnostic，不能翻转原始门。正式复核必须改善
均匀补光，并以 fresh campaign 重拍后重新通过未经自动放宽的原始门。

### 5.1C W1 白场安全收容（2026-08-30 14:07–14:20）

T1 FAIL 只阻止 T2，不阻止 W1 白场清理。W1 执行结果：

- BIN SHA-256=`4dc8e0333b9a37839af18cca0c76ad36d94bd621b6cbc7510b8d775dfd3e2b81`；
- relay pre-flash exact query=`OFF`；app-only write/verify PASS，flash evidence SHA-256=
  `beb0c07cca4699b547cf4fe0b172f67ee3483cc35d9b34c49a1a1566abc213ab`；
- fresh J2-OFF diagnostic PASS，boot=`89243ae1014aa53d`，`4 GET / 0 POST / 0 claim /
  0 refresh`，文件 SHA-256=`10c0629dce6065f0ac8292de6145e34193e2b0f74c602848d254be81b96b627b`；
- action=`f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5`，
  `complete_pass / COMPLETE / 1 driver / 1 visible refresh`；
- PON/DRF/POF=`180/22521/141 ms`、driver total=`35013 ms`，无 timeout、retry、recovery、
  autochain；action file/canonical SHA-256=`d0a936c2...fb57 / dd7f1fb2...d253`；
- 最终 exact-bound relay OFF receipt SHA-256=
  `3095af42f93f1b953a1b92eb6cea782e58def95e669464a5df4ae11bade71c7d`，仍只证明命令／查询状态，
  `electrical_state_proven=false`。

正式 48MP 白场照片=`564113 bytes / 4e07791e227bee276266574c64c4b5afaa017b09e5b57181bda79c2f310bf37d`；
sidecar=`5091 bytes / d855422f0717ef3a427ef006d5a2185f36ad18f55cf437fe665885a61e7cccfd`。
独立 O_EXCL 视觉分析=`PASS / confidence=medium`，analysis ID=`9324718e...395b`、文件 SHA-256=
`3c294dd75e186cdbc1407a8eb91a7429d7b637d30dd14cba9c1526258ca469e4`。活动区为干净白场，
原 4×8 色块、轮廓、条纹、底边异常、中心接缝及孤立色斑均未见。因画面欠曝且左下有明显阴影，
该门只证明可见残留清除，不证明绝对白点或空间均匀度。

正式 action 前有两次 pre-claim 安全拒绝：一次误把 OFF-only exact query 用于 ON 状态，另一次传入
了不合法的 `poll_seconds=1`。两次均在 ARM/EXECUTE/action output 前终止，`0 claim / 0 refresh`，
且保护脚本均立即 OFF；随后才用冻结默认 `poll_seconds=65` 执行上述唯一 W1 action。该记录不计为
W1 action retry。

### 5.1D 白平场粗筛回放（2026-08-30 15:44）

按“普通环境光只作粗筛”的新口径，新增独立离线工具，用 W1 factory-OTP 白图按 T1 每帧
homography 在相同逻辑位置重采样并平场。工具深校验三张 T1 analysis 及其 photo/sidecar/action、
W1 post-capture analysis 及其绑定，并要求四次 capture 的 48MP instance、mount、请求设置、
frame 前后实际设置和 `4000x3000` 尺寸完全相同。

左下阴影使 W1 中 `CS1-R3-C0-CODE3` 的参考 `L*=5.28725`、`CS1-R3-C1-CODE2` 的参考
`L*=17.898226`，低于冻结门 `25`，因此这两个位置在三帧中均剔除；对应组仍有三位置，不构成
整组失败。回放结果：

```text
state = PASS_COARSE_SCREEN
groups = 16 PASS / 0 REVIEW / 0 FAIL
maximum_position_de00 = 5.384516695
maximum_temporal_center_de76 = 0.533904711
eligible_for_t2_discovery = true
formal_gate_evaluated = false
formal_advance_to_t2_permitted = false
qualified_colour_count = 0
```

O_EXCL 报告=`T1.white-normalized-coarse-screen-v1.json`，bytes=`293550`，文件 SHA-256=
`4abbcf56bfb390e8cfb394f67eb8d6209fc35d845d1b096b096234973f4f50ea`，canonical=
`3b080f2288c45f0ac5cdba9023b90a4f320d4b514bedece2372b72cf6b39d8ad`。主线程将新工具／测试与
原 strict analyzer/comparator 联合复验为 `46 passed`，Ruff check/format 与 py_compile PASS。

该 PASS 仅证明现有照片足以进行宽色桶发现，不翻转 5.1B 的 formal FAIL，也不授权执行原 T2。
后续可以基于该报告新建 discovery-only T2 successor；出现粗候选后，再把少量命中送入人工观察
或受控照明下的正式资格门。

### 5.1E fresh T2 discovery successor V2 真屏人工粗发现（2026-08-30 20:18）

V1 的欠曝证据不能完成自动粗比较，因此没有放宽 `L*>=25` 门，而是使用全新
campaign/contract/action/NVS 的 V2。V2 仍是 discovery-only，不属于正式资格门。

- action=`c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f`；
- outcome=`complete_pass / COMPLETE / 1 driver / 1 visible refresh`；
- driver total=`41913 ms`，PON/DRF/POF=`261/29211/150 ms`；
- 每侧 `4×8` 位置平衡 atlas，无 retry/recovery/autochain；
- action evidence/file SHA-256=
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/action-01-position-balanced-atlas.json /
  490df32422ec362f20c09e40d60d1e86e3f8bb46e9820f624004a4f07d08a989`。

action 前的失败全部在 mutation 之前终止。初版 V2 host adapter 仍绑定 V1 的
baseline-role 和 action round；修正为 V2 role/round 后 fresh J2-OFF diagnostic PASS。之后两次
relay ON 准入读到 raw `BUSY=0`，均在 claim/ARM/EXECUTE 之前保护性 OFF。上述路径均为
`0 POST / 0 claim / 0 visible refresh`，是设置诊断，不是 action retry。V2 host 适配器已增加
真实形状 version/manifest 正负 wire-validator 回归；联合 V2 定向回归=`32 passed`，
Ruff 和 py_compile PASS。

人工第一行颜色词为：

```text
CS1 / C = [橄榄, 黑, 绿, 白, 浅黄, 蓝, 黄, 黑]
CS2 / A = [红, 粉, 绿, 白, 棕, 蓝, 深粉, 深蓝]
```

同一侧四行呈相同颜色集合、不同排列，保留观察期间外观稳定。这里的“橄榄、粉、深粉、
棕、深蓝”等均为人工宽色词，不是色卡值或相机量化结果，不得据此声明新单像素颜料、
绝对颜色、正式灰阶、跨位置一致或可用调色板。当前仍固定：

```text
screening_only = true
formal_gate_evaluated = false
qualified_colour_count = 0
original_t2_or_t3_executed = false
```

### 5.1F W3 独立 factory-OTP 白收容（2026-08-30 20:42–20:43）

W3 精确绑定上述 T2 V2 身份和 action：

- action=`b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9`；
- outcome=`complete_pass / COMPLETE / 1 driver / 1 visible refresh`；
- driver total=`35014 ms`，PON/DRF/POF=`180/22521/140 ms`；
- 无 timeout/retry/recovery/autochain；
- action evidence/file SHA-256=
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/action-01-factory-otp-white.json /
  445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef`。

W3 首次 relay ON 后 raw `BUSY=0`，因此只做保护性 OFF，没有 claim/POST/refresh。再次 ON 后
经只读查询明确得到 `BUSY=1`，才执行上述唯一 W3 action；该过程同样不计 action retry。

操作者确认最终全屏干净白。随后 exact-bound relay OFF/query OFF；最终 receipt SHA-256=
`febbab71fcbca53130179424775caf6245990d6098f4fab8a1478474b537bae1`。
当前屏幕双稳态保留干净白，`electrical_state_proven=false`。

现场同时确认：继电器 ON 后 raw BUSY 准入电平可能延迟建立。后续流程必须在 ON 后只读轮询，
确认 raw `BUSY=1` 后才允许 claim/ARM/EXECUTE；relay ON receipt 或固定等待时间均不能替代
该门。

### 5.1G T3 A/C profile-following successor 与 W4 收容离线就绪（2026-08-30 22:02）

用户选择下一轮由肉眼作为主判据；48MP 相机不再是决策门，只可选留档。因此新
T3 不复用旧 `t3-ac-repeat` campaign，而使用 fresh campaign/contract/descriptor/action/route/
NVS/claim/output。旧 T3 CLI 已在 configure/request/claim 前 tombstone，不能从受支持的命令行路径
被误执行。

T3 可见载荷冻结为：

```text
global header = active
CS1 / 左侧 = active535 (A)
CS2 / 右侧 = commented535 (C)
round = 3
frame / CS1 DTM / CS2 DTM = 与 T2 V2 byte-identical
required camera frames = 0
visible refresh count = 1
retry / recovery / autochain = 0 / 0 / 0
```

T3 最终封存：

| 项 | 精确值 |
|---|---|
| contract | `714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19` |
| descriptor | `52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9` |
| action | `db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104` |
| route | `/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v1` |
| NVS | `p16t3pf_v1 / cur_t3pf1 / boot_t3pf1` |
| BIN | `805232 / 05c00d71a163ecfc22d0d333404ac8967eaa06b929003ce0c28dda7499615760` |
| ELF | `13299376 / 89d20faec2d5bde42915a5fe30515c917f722ca06777b016a75c38020e83a56e` |

T3 后的 W4 是独立 factory-OTP white，只接受上表 T3 的 exact source quartet：

| 项 | 精确值 |
|---|---|
| contract | `7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52` |
| descriptor | `398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45` |
| action | `e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b` |
| route | `/api/ec5/raw-p16-crossover-w4-after-t3-ac-profile-following-successor-white-v1` |
| NVS | `p16w4pf_v1 / used_w4pf1` |
| BIN | `787248 / 9f3ab672c214cdf128a01a51b2803d5a586f72fab1cad065373eead30ee63bf7` |
| ELF | `13214976 / 16b37334ef8142ad33a8856dcf2850f751a8cf80489152766b8dc0602e278118` |

W4 为单动作、fresh route/NVS/claim/output、无 retry/recovery/autochain；T3 不会自动调用 W4。
两个 PlatformIO 环境都只有 compile-only 配置，无 upload command。

人工证据链同步完成：

- 既有 CA V2 人工词以 O_EXCL 封存为
  `human-observation-ca-v2-v1.json`，bytes=`39377`，file/canonical SHA-256=
  `8e1a93bdd15c24bb808a698633ab4495edb1c1f94fb8249934420caca4a27921 /
  60510bc2e1cd5e9b7809a193574284a0ae63b44ec4f2a8416ac05f2c997d81e4`。已报告的四副本
  一致事实保留；未报告字段显式为 `null/UNKNOWN/NOT_REPORTED`，所以 formal
  `comparison_ready=false`。工具可另行输出受限的 `HUMAN_SCREEN_*` 判因，不会把它写成 formal
  gate 或绝对色标定。
- W3 原话“白屏，干净”封存为 `human-clean-white-authority-v1.json`，bytes=`4072`，
  file/canonical SHA-256=
  `5f5ff9d0c6bc023c461038e17fbc92b0fda5b475d52019bf736b91d745d5582b /
  2fceccd9cac4af23ffc0d27f7d14a546920d586cc0efd72f0799037cdb5b614f`。它双绑定 W3 action 和最终
  relay-OFF receipt，并明确 `OFF receipt` 不证明负载侧电气状态。
- 未来 AC 正常只需填左/右各 code0..7 共 16 个肉眼词，并显式确认各 code 四副本
  一致且稳定。工具才会按冻结布局展开 64 cells；任一回答为否时必须转 64-cell
  展开表，不允许用单词覆盖不一致副本。工具保留原始紧凑输入、展开规则、canonical
  integrity、deep recomputation 与 O_EXCL。盲填卡为
  `docs/MF1750-RAW-P16-PROFILE-FOLLOWING-HUMAN-OBSERVATION-CARD.md`。

实际上机顺序现冻结为：

```text
当前 W3 clean white + J2 OFF
→ J2 OFF 下 app-only 写入/验证 T3
→ fresh J2-OFF 4-GET diagnostic（0 POST/0 claim/0 refresh）
→ relay ON，只读等待 raw BUSY=1
→ 唯一 T3 action（1 visible refresh）
→ 先盲填、O_EXCL 封存，再揭盲比较
→ relay OFF，J2 OFF 下 app-only 写入/验证 W4
→ fresh J2-OFF 4-GET diagnostic（0 POST/0 claim/0 refresh）
→ relay ON，只读等待 raw BUSY=1
→ 唯一 W4 white（1 visible refresh）
→ 肉眼确认干净白后 relay OFF
```

由于现有 W3 已是 exact-bound clean-white 起点，不再额外执行一次前置白；因而下一轮计划总共
只有 2 次 visible refresh。任意身份、artifact、W3 authority、BUSY 准入或 wire manifest 不一致都在
claim/ARM/EXECUTE 前 fail-closed。本节全部为离线工作：未 flash、reset、访问设备网络/COM/
继电器或刷新屏幕。

最终离线验证：两固件 compile-only 和 artifact postflight PASS；T3/W4 `dry_validate`
均返回 `PASS / artifacts_verified=true`；CA/W3 人工 authority 深验 PASS。主线对本轮相关测试
复跑=`52 passed`；其中独立 closure=`7 passed`，覆盖双固件假设备 J2-OFF
`4 GET / 0 POST / 0 claim / 0 refresh / O_EXCL`、fresh 身份隔离、旧 T3 tombstone、
wire 正负门、W4 exact source quartet 与无 upload surface。Ruff check/format 和 py_compile
均 PASS。

### 5.1H 日间 48MP 辅助粗筛与 W4 收容闭环（2026-08-31 01:18，离线就绪）

保持 5.1G 的两次可见刷新、T3/W4 identity 和 human-primary 正式边界不变；另加一条可在日间
执行的 camera-only 辅助路线。相机只允许 `48MP USB Camera / VID_32E4:PID_4801`，固定
`MJPG 4000×3000@15 / focus79 / exposure=-6 / WB4600`；双目 `1BCF:0B15` 与 V2
`exposure=-3` 均禁止。

现场顺序冻结为：

```text
W3 clean white + relay OFF
→ 1 white capture
→ app-only T3 + 4 GET diagnostic + relay ON + raw BUSY=1
→ exactly one T3 visible refresh
→ relay OFF
→ capture 3 retained atlas frames (at most 5 attempts total)
→ deep-seal the four-frame bundle
→ separately resume app-only W4 + 4 GET + relay ON + raw BUSY=1
→ exactly one W4 white refresh
→ relay OFF + independent post-white frame
→ offline camera screen
```

四帧原始证据封存是 W4 的先决门；相机分析结论不是 W4 安全白收容的先决门。若 5 次内不能
得到 3 张有效 atlas，保持 OFF、保留 atlas 并暂停；若照片已封存但分析为 REVIEW/FAIL，仍可
执行 W4 收容。camera attempt 与 display-action retry 严格分开，后者始终为 0。

采集包每次调用至多打开相机一次，并在打开前永久消耗 O_EXCL attempt；白参考最多 2 次、
atlas 最多 5 次。每帧独立提供当前 `TL/TR/BR/BL`，逐帧验证凸四边形、活动区、64 格投影，
跨帧对应角最大漂移固定 `30 px`；相机 instance、mount、请求/实际设置与尺寸仍必须全等。

分析器以 W3 白参考归一化三张 T3：检查 64 格、每 controller/code 四副本、三帧时间稳定、
controls `2/3/5`、底边、水平/垂直条纹、残留和对齐。四副本 max `ΔE00 <=8 / 8–12 /
>12` 分别 PASS/REVIEW/FAIL；三帧 max `ΔE76 <=3 / 3–6 / >6`；白参考 `L*<25` FAIL，
`25–35` REVIEW。自动结论只为 `HUMAN_CAMERA_SCREEN_PASS/REVIEW/FAIL`。无人工 seed 时仍可
输出完整报告，但最高 REVIEW；不能用 placeholder 生成 compact，也不声明绝对色、正式
profile-following、灰阶或 qualified colour。

W4 已加入相机工具的精确 frozen allowlist，并关闭 `...SUCCESSOR` marker 降级为宽泛 recovery
role 的绕过。离线状态门 V2=`27457 bytes /
d3c0d2e12804c459d03872479da91bfce81ebcff039128f7395ebdbb937ef551`；capture pack SHA=
`5608ac7c24fd7fad28d5279cdcafae4bc2fd85ee098d9dd5850d12bf8e0522de`；analyzer SHA=
`1a75d63fea7a3d32adb431a8083c58b3d1f0e3ccb16b12fddb8b9c8b78d2a40c`。最终联合回归
`150 passed / 425.80 s`，Ruff/format/py_compile 和计划深验均 PASS。该节全程离线，J2
仍 OFF，屏幕仍为 W3 干净白，没有访问相机、设备网络、COM 或继电器，没有 flash/reset/
refresh/rewire。

### 5.1I 日间相机 setup-only 预检失败并安全停止（2026-08-31 06:03）

exact relay 只读查询为 channel1 commanded `OFF`；DirectShow 唯一识别目标 48MP
`VID_32E4:PID_4801`，没有选择双目 `VID_1BCF:PID_0B15`。由于正式 capture pack 在相机打开前
即要求角点并永久 claim，先按 setup-only、非核心证据边界拍一张固定正式档预检图。

预检 JPEG=`camera-t3-daylight-setup-white-20260831-060144.jpg`，`366555 bytes`，SHA-256=
`2ac5fce31b4929efefaa3cd4951e0c52b690366d775e856d653f10a030966ad4`；capture sidecar
深验 PASS，`5352 bytes`，SHA-256=
`caf5cab00fcd4a79f5009279d023fb20e02bea7bdf53d6ff2f972218a84517b8`。画面没有面板，且
mean RGB 仅 `[5.464085, 7.100415, 10.886859]`，无法取得本次四角或合格白参考。按日间执行卡
立即停止：正式 W3 attempt 未消耗，T3/W4 未安装、未 claim、未执行，J2 保持 OFF，0 次可见
刷新。待操作者重新对准 48MP 镜头并补足照明后，从 setup-only 几何预检重新开始。

### 5.1J 两阶段 capture、W4 PASS-only 与 daylight V3 离线收口（2026-08-31 09:15）

操作者离场并要求今天后续只做离线代码。保留 5.1I 的 05:59 relay query 和 06:01 setup-only
相机历史；从本次修订开始没有新增 camera/relay/COM/ESP32-network/flash/reset/visible-refresh。
现场状态仅继承为 commanded OFF、W3 clean white、`electrical_state_proven=false`；未重新量测。
正式 W3 attempt 仍为 0，T3/W4 仍未安装、claim 或执行。

旧正式采集接口的“拍照前必须知道该照片四角”时序循环已消除。T3 capture pack 现在严格为：

```text
acquire: claim-before-camera -> one immutable JPEG/sidecar/action snapshot, no corners
admit: admission-claim-before-corner-parse -> same-JPEG geometry/gates -> terminal result
```

成功 acquisition 未 terminal admit 前禁止下一次 acquire；错误角点或 gate failure 永久消耗该
admission，不能换角重审。legacy `capture` 在任何写入／相机调用前 fail-closed；setup-only 使用
独立最多两次账本且永不进入正式 bundle。W3 最多 2 attempts；T3 为取得三张 accepted 图最多
5 attempts，必须逐张 `acquire -> admit` 后才拍下一张。

W4 post-white wrapper 同步改为两阶段，并对 canonical attempt claim、acquisition、admission、
evidence path/action snapshot 的 bytes/hash/integrity 全链深重放；两类重签篡改测试均拒绝。只有
`full_screen_white_gate.passed=true` 且 classification=`PASS` 才 terminal ACCEPTED 并允许
seal；REVIEW/FAIL 保留分类但 terminal REJECTED，只能显式消耗剩余的 attempt 2。人工确认白屏
可作安全 fallback，但不能虚构 camera seal。

证据权限同时收紧：camera-only 只回答 64 格几何、四副本、三帧稳定性和画面瑕疵；无真实
T3 human seed 时最高为 `HUMAN_CAMERA_SCREEN_REVIEW`，profile-vs-side=`NOT_EARNED`。要判定
profile-following 或 physical-side-following，必须封存当前 T3 的左右各 code0..7 共 16 个
真实人眼词并确认四副本稳定，再与已绑定 T2/CA human reference 比较。缺 seed 不阻塞独立 W4
安全收容，但主问题保持 pending，`qualified_colour_count=0`。

T3/W4 app-only helper 的真实 reset 序列也已进入 V3：write 为
`--before default_reset --after no_reset`，verify 为 `--before no_reset --after hard_reset`，应用
只启动一次；额外／人工 reset=0。每个 runner 的 raw `BUSY=1` 门仍位于 exact 4 GET 后、任何
claim/ARM/POST 前；两次 visible action 均 retry/recovery/autochain=0。

O_EXCL V3 状态门为
`.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V3.json`，
`36734 bytes / SHA-256 4c3c1d2ff056a28506fd335ee9576167e7b627d679b2c03d4c854a2b9f95a212`，
canonical integrity=`88510a3090d62dd2950fca0c0768d28001c5e5bf957ac97ec01525f52b04bed7`，
共 14 steps。旧 V1/V2 不覆盖、只作历史；V2 已不能通过当前 deterministic rebuild。

最终 SHA-256：T3 capture pack=
`4b8de02588c4fbf4f73914129118f019080d6231347b97831fe9df9f3f91d6ca`，W4 wrapper=
`c2c9c5c8cb11867d04d98d51849a080163a379354fdb3c510fb11a8cc2af9024`，daylight plan source=
`c3582a7f7d9db5a409c62460fe0f417a990e6af471f24e9252c058c3d944245b`。联合离线回归
`174 passed / 696.69 s`；格式化后 plan `9 passed / 90.75 s`、W4 `17 passed / 244.27 s`；
format check、Ruff、py_compile PASS，全部为 fake/synthetic evidence。

### 5.2 固定顺序

> 本节保留历史正式资格路线；它不覆盖 5.1J 当前 successor 的两阶段 T3/W4 现场流程。

```text
T1: fresh white -> AC 位置平衡 atlas -> 固定相机拍照
    -> 独立 factory-OTP white -> 相机确认干净白
T2: fresh white -> CA 位置平衡 atlas -> 固定相机拍照
    -> 独立 factory-OTP white -> 相机确认干净白

仅当差异跨左右跟随 A/C profile：
T3: fresh white -> AC-repeat -> 固定相机拍照
    -> 最终独立 factory-OTP white -> relay OFF
```

`AC` 表示 CS1=A、CS2=C；`CA` 表示 CS1=C、CS2=A。T1、T2、T3 必须使用 fresh
campaign、fresh NVS、独立一次性 action 和独立收容，不复用已消费凭证。

正式资格分支仍固定为：

```text
T1 position gate FAIL -> mandatory W1 white containment PASS -> STOP
```

原 T2/T3 正式资格动作仍禁止且未执行。5.1D 只另行释放了 fresh、discovery-only successor；
其 V2 人工粗发现和 W3 安全收容见 5.1E–5.1F，不翻转上述正式分支，也不产生合格颜色。
已消费的 T1/W1/T2-successor-V2/W3 不得重跑，也不得用局部白参考诊断翻转原始 gate。

### 5.3 位置平衡画面

- 每侧 `4×8=32` 个纯色格；
- code0..7 每个在每侧出现四次，四个副本分散到不同上／下、内／外位置；
- T1、T2、T3 的 DTM、逻辑布局、格尺寸、间距和相机参数完全相同；
- 不使用空间抖动、网点、条纹或像素混色；
- code3、5、6、7 为重点，code4 为暗色 guard，code0、1、2 为内部控制；
- 先拍整屏，再由固定 overlay 给出 controller/profile/code/replicate，屏内不画文字。

### 5.4A 自动粗筛门（仅用于发现与排队）

48MP 相机在普通环境光下只承担几何确认、明显外观差异筛选、边界／条纹／残留检查和证据留档，
不承担绝对色值、精细 ΔE、灰阶等级或正式 palette 标定。允许画面存在缓慢照明梯度，但不允许
活动区被遮挡、严重失焦、明显过曝／欠曝或 ROI 几何失败。

粗筛优先使用同一机位、同一设置下的 factory-OTP 白场作同位置平场：

```text
RGB_norm = clip(220 * RGB_candidate / RGB_white_reference)
```

邻近白缝归一可作为同帧交叉检查。自动机只分宽色桶，不输出精确色名：暗／黑、中性／白、
暖色（红粉橙棕）、黄／橄榄、绿、青／蓝绿、蓝／靛紫；明度另分五个宽档。固定门如下：

- 白参考格 `L* < 25` 时该位置无效并剔除，不让强阴影拖垮整组；
- 每个 controller/code 每帧至少 `3/4` 有效位置，三帧至少 `2/3` 有效；
- 每组主色桶至少 `3/4` 一致；有色组 circular hue 跨度 `<=35°` 为 PASS、`35–60°` 为 REVIEW、
  `>60°` 为 FAIL；
- 同位置白平场后的组内最大 `ΔE00 <=8` 为 PASS、`8–12` 为 REVIEW、`>12` 为 FAIL；
- 三帧组中心漂移 `ΔE76 <=3` 为 PASS、`3–6` 为 REVIEW、`>6` 为 FAIL；
- 同 profile 左右复核时，每 code 至少 `3/4` 同位置匹配、全画面至少 `28/32` 匹配；T1 的
  AC 两侧 profile 不同，因此不得套用该左右一致门；
- 相对已知七色 controls，最近控制 `ΔE00 <=8` 记已知近似，`8–15` 交人工复核；只有 `>15`、
  跨宽色桶／明度桶且同时通过位置与时间门，才能记粗候选；
- 只出现明暗变化时记录为 `NEW_SHADE_CANDIDATE`，不称为新色相；
- 若原始差异明显但白平场后下降至少 `50%`，记 `LIGHTING_SUSPECT`，不记真实位置差异。

粗筛只输出 `PASS / REVIEW / FAIL`，并可附加 `LIGHTING_SUSPECT`、`NEW_SHADE_CANDIDATE`、
`BOTTOM_EDGE_ANOMALY`。白场忽略可拟合的平滑照明渐变，只拦截局部色斑、旧网格、固定条纹和
中心接缝。若底边暗覆盖率比上／左／右三边中位数高超过 `15` 个百分点，且最长连续暗段超过
格宽 `50%`，记底边异常。格内网点、条纹、底边线、灰边、接缝或残影存在时，即使外观新颖也
不得记为强候选。

粗筛 PASS 只允许建立 fresh、明确标记为 discovery-only 的 T2 successor，供快速发现；不允许
执行原已冻结 T2，也不产生任何合格颜色。机器结果必须显式保持：

```text
screening_only = true
qualified_colour_count = 0
formal_gate_evaluated = false
formal_advance_to_t2_permitted = false
supersedes_consumed_t1 = false
eligible_for_t2_discovery = <true only when all 16 groups PASS>
```

### 5.4B 精确资格门（原门不变）

候选只有同时通过以下门，才允许从“mixed-R20 外观候选”升级为“profile-following 候选”：

1. 同一 profile、同一 code 的四个分散位置内部一致；
2. A 的结果从 CS1 换到 CS2 后仍接近 A，而不是仍接近原物理侧；
3. C 的结果从 CS2 换到 CS1 后仍接近 C；
4. 两侧的 `A→C` 色差向量方向一致；
5. profile 差异大于同批白场噪声与位置噪声的两倍；
6. 若进入 T3，T3 能复现 T1；
7. 格内为均匀纯色，无网点、条纹、底边黑线、灰边、中心接缝或残影。

若同 code 的四位置离散先失败，本批固定记为 `POSITION_DEPENDENT_INCONCLUSIVE`，不得用左右
平均值掩盖失败。若结果跟随物理侧而不跟随 profile，则优先排查 controller、电气、历史状态和
光学位置，不进入颜色扩展。

## 6. 通过判因后的颜色扩展顺序

只有 AC↔CA 判因通过后才开始新色扩展，并按信息增益排序：

1. code5：本轮 profile 差异最大；
2. code7、code3：强差异且覆盖亮／暗两端；
3. code6：绿色／蓝绿色附近的中等强差异；
4. code4：暗色 guard，用于排除“只是更黑”的假候选；
5. code0–2：继续作对照，除非新 profile 在它们上产生稳定变化。

每个命中先做纯色均匀性与 profile-following 复核，再做最少一次 fresh repeat；只有真正有价值
的命中才补 60 s、10 min 和长期保持。这样把上机次数用于最可能形成独立单像素颜色的区域，
而不是盲目穷举整个巨大波形空间。

## 7. 明度／灰阶当前结论与后续门

明度和中性灰尚未解决：

- 先前蓝色、红粉、黄橄榄矩阵常表现为同列近似一致或色相与 L* 同时变化；
- 目前没有一组配方证明“色相基本不变，只改变亮度”；
- `qualified_gray_levels=0`、`qualified_brightness_levels=0`；
- 空间抖动可形成视觉灰，但不满足本项目“单个像素点颜色控制”的目标。

新的 T1 位置门通过且 AC↔CA 完成后，从通过的同一色相族中选择至少三个候选，要求：

1. 四位置一致；
2. profile 交换后仍复现；
3. 色相角和饱和度变化低于预设门，而 L* 单调变化；
4. fresh repeat 保持顺序；
5. 无边界和残留异常。

未通过这些门时，只称“不同颜色候选”，不能称明度级或灰阶。

## 8. 局部 HOLD 当前边界

既有 fixed-window 试验已证明：在限定矩形内，蓝、绿、黑可以依次加入，旧区域在后续局刷中
保持，白背景可清理；修正后的矩形底边也可做到无黑线。这支持“局部 HOLD／局刷机制存在”及
后续跨 LUT 叠色的工程可行性，但尚未证明：

- 任意 code、任意位置、任意 profile 都能可靠 HOLD；
- 两套调色盘的全部颜色都可无损共存；
- 可通过反复局刷直接得到 256 个独立、稳定的单像素颜色。

因此局部 HOLD 是后续多调色盘叠加的基础能力，不是当前 256 色结论。待 profile 候选通过后，
再把最有价值的 A/C 颜色放入小规模 `A写入→HOLD→C写入→A复查` 测试。

## 9. 停止条件

任一条件出现即停止当前 action，转入独立白场收容或人工物理切断：

- 电源限流、异常电流、异响、异味或异常发热；
- BUSY 时间超过该 campaign 正常值两倍；
- 左右控制器意外不同步并影响最终图；
- 固定横线／纵线、底边黑线、灰边、中心接缝、大面积偏色；
- 两次独立 factory-OTP 白仍不能清除残留；
- runner identity、contract、设备 MAC、继电器绑定或相机 exact path 任一不匹配。

## 10. 渐进记录与 GitHub 同步规则

以后每轮按以下节奏执行：

1. **离线冻结前**：在本文或 successor live record 写目标、非目标、布局、identity、哈希、
   观察字段、资格门和停止门；
2. **离线完成后**：记录构建、静态检查、单元测试、pack/dry-validation，状态只写
   `OFFLINE_READY`；
3. **每个真屏 action 后**：立即记录 action ID、时序、结果、异常、J2 状态和 evidence 哈希；
4. **照片／人工观察后**：同时保留原始观察、粗筛标签和正式资格状态；严禁把粗筛
   `PASS/REVIEW` 写成 `qualified`；
5. **安全收尾后**：记录独立白场和 relay OFF，不以继电器命令冒充下游电气证明；
6. **阶段门关闭时**：更新 `docs/STATUS_HANDOFF.md`，只暂存本阶段相关文件，检查 staged diff，
   运行对应测试后 commit 并 push `origin/main`；
7. **原始 evidence**：默认不上传大体积照片／串口取证，只在 GitHub 文档中写文件名、字节数、
   SHA-256 和本地路径。需要公开复核时再建立经过筛选的独立 evidence release。

GitHub 提交必须是可验证的阶段快照，不把未完成实验写成完成，不混入 PCB、应用层或其他 campaign
的无关脏改动。

本阶段只发布本文、`docs/STATUS_HANDOFF.md` 与
`docs/MF1750-RAW-P16-PROFILE-FOLLOWING-HUMAN-OBSERVATION-CARD.md` 三份跟踪文档。
照片分析器、T1/T2 comparator、runner 修改及其测试继续留在本地：在补齐根级依赖清单、
clean-machine 安装／测试命令、确定性生成物和
完整依赖闭包前，不把它们提交为可复现代码，也不提交 ignored `.pio` 构建产物。
