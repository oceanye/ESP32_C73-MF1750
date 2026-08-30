# MF1750 RAW-P16 跨 Profile 判因计划与实测台账

日期：`2026-08-30`
当前状态：`RAW-P16 已拍照分析 / 独立白场收容已完成 / AC↔CA 六镜像离线就绪、尚未上机`
当前面板：`factory-OTP white retained`
当前 J2：`commanded/query OFF`

## 1. 文档用途

本文同时承担三项职责：

1. 记录 RAW-P16 从计划、固件身份、真屏动作、照片、分析到安全收尾的完整过程；
2. 固定下一轮 `AC↔CA` 跨 profile 判因实验，防止临场改变布局、阈值或结论口径；
3. 作为阶段性 GitHub 同步入口。原始照片和硬件 evidence 保留在本地
   `.test-output/`，仓库同步工具、测试、计划、结论及原始文件 SHA-256。

本文不是颜色标定报告。没有绝对色卡／光谱测量、独立重复和跨位置复现之前，任何结果都只能
称为相机相对候选，不能称为稳定新色、可用调色板色或灰阶。

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

独立复核已关闭三项提交前阻断：atlas action 必须显式收到 J2-ON 确认；mutation 只接受 literal
private/local IPv4 并使用 no-proxy/no-redirect requester；clean checkout 采用 artifact-free
preflight→六镜像 compile-only build→12 个 BIN/ELF 哈希核验。主线程最终复跑结果：六镜像
`SUCCESS`，build bootstrap postflight `artifacts_verified=true`，相关综合测试 `111 passed`，
Ruff check/format PASS。全过程没有访问硬件、设备网络、COM、继电器或相机，也没有 flash、
reset 或 display refresh。

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

### 5.2 固定顺序

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

### 5.3 位置平衡画面

- 每侧 `4×8=32` 个纯色格；
- code0..7 每个在每侧出现四次，四个副本分散到不同上／下、内／外位置；
- T1、T2、T3 的 DTM、逻辑布局、格尺寸、间距和相机参数完全相同；
- 不使用空间抖动、网点、条纹或像素混色；
- code3、5、6、7 为重点，code4 为暗色 guard，code0、1、2 为内部控制；
- 先拍整屏，再由固定 overlay 给出 controller/profile/code/replicate，屏内不画文字。

### 5.4 判定门

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

AC↔CA 完成后，从通过的同一色相族中选择至少三个候选，要求：

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
4. **照片／人工观察后**：保留原始措辞和相机分析，明确区分 observed、candidate、qualified；
5. **安全收尾后**：记录独立白场和 relay OFF，不以继电器命令冒充下游电气证明；
6. **阶段门关闭时**：更新 `docs/STATUS_HANDOFF.md`，只暂存本阶段相关文件，检查 staged diff，
   运行对应测试后 commit 并 push `origin/main`；
7. **原始 evidence**：默认不上传大体积照片／串口取证，只在 GitHub 文档中写文件名、字节数、
   SHA-256 和本地路径。需要公开复核时再建立经过筛选的独立 evidence release。

GitHub 提交必须是可验证的阶段快照，不把未完成实验写成完成，不混入 PCB、应用层或其他 campaign
的无关脏改动。
