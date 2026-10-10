# MF1750 阶段三：同 R20、配方置换与真正跨 R20 局部 HOLD

日期：`2026-08-28`  
状态：`OFFLINE IMPLEMENTATION FROZEN / LIVE NOT EXECUTED`  
可见刷新预算：`13` 次（G-1 为零刷新）

## 1. 本轮要回答的三个问题

1. 两个控制器在接收相同完整 R20 tuple、相同 R21、相同 DTM 和相同刷新时序时，
   同一码的屏上结果是否一致；
2. Red/Pink V2 Action 4 的差异跟随 `source -> middle -> target` 配方，还是跟随固定物理位置；
3. active/commented 两套完整 R20 tuple 真正轮换后，先前完成的局部区域能否 HOLD，
   从而让两套调色盘的结果共存。

既有 clean cross-LUT HOLD V2 证明了固定窗口传输与局部保持可以无底边黑线工作，
但它只切换了广播 PWR/PLL global header；CS1/CS2 的 R20 仍分别固定为
active/commented。因此旧结果不能写成“已证明完整 R20 轮换共存”。

## 2. 证据边界

本计划分三层证据，不能混写：

- **传输身份层**：编译期 payload、固件、动作序号、PTLW/DTM、请求及结果哈希；
- **相机相对测量层**：同一固定机位和曝光下的 ROI Lab、CIE76 距离、相关性、面积和边缘变化；
- **颜色资格层**：未来使用同平面色卡、重复刷新和持久性数据进行校准后，才可命名和计数。

当前自动工具输出的是固定相机条件下的相对 CIE76，不是已校准 CIEDE2000。24 色卡不参与
本轮实时放行门；它保留给后续绝对颜色资格和命名。code0..7 仅是传输码，不是颜色名。

## 3. G-1：锁定相机、全屏几何和现存 P0（零刷新）

G-1 必须发生在 G0 白恢复之前，利用屏幕当前保留的 Red/Pink V2 Action 4 双 8x8 网格：

1. 相机完整、无裁切地包含整块面板，固定支架；
2. 固定分辨率、焦点、曝光、白平衡，记录请求值和设备实际回读值；
3. 拍摄至少一张当前 P0 原图；
4. 建立全屏 homography、128 格几何和 64 个配方映射；
5. 以不可覆盖 canonical JSON 封存照片 SHA-256、相机 tuple、安装身份和几何身份。

工具：`tools/mf1750_g1_locked_full_panel_p0_geometry_anchor.py`。证据种类：
`mf1750-g1-locked-full-panel-p0-geometry-anchor`。

G-1 只形成回溯性几何/P0 锚，不声称颜色校准、波形因果或真实局部刷新。它不访问 ESP32、
继电器或屏幕，也不产生可见刷新。

## 4. G0：独立 V3 factory-OTP 白锚（1 次刷新）

旧 V2 white containment 已留下不可覆盖的 J2-OFF diagnostic FAIL；不得重试、覆写或把后续
输出塞回旧 claim。唯一入口是独立 V3 successor：

- contract：`1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227`
- BIN：`789200 bytes`
- BIN SHA-256：`3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb`
- ELF：`13215844 bytes`
- ELF SHA-256：`2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797`

J2 OFF 下只做 app-only flash、独立 verify 和 fresh 四 GET diagnostic；随后按明确动作序号只执行
一次 factory-OTP white。白屏必须全屏干净，否则本 campaign 结束，不进入批次 1。

白态在相机完全不动的条件下拍至少三张同动作照片，不增加刷新，用于生成 sealed repeat-noise
report。G-1 的相机、安装和几何身份必须延续到后续所有 evidence。

## 5. 批次 1：同 R20 双控制器复核（4 次刷新）

固件环境：`runtime_lut_same_r20_parity_v1`  
contract：`718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8`

| 次序 | 动作 | 目的 |
|---:|---|---|
| 1 | AA atlas：两侧都装载完整 active-535 R20/R21 tuple | active 条件下 code0..7 左右一致性 |
| 2 | factory-OTP white | 清除 AA 历史 |
| 3 | CC atlas：两侧都装载完整 commented-535 R20/R21 tuple | commented 条件下 code0..7 左右一致性 |
| 4 | factory-OTP white | 清除并建立批次 2 白锚 |

动作 ID 依次为：

1. `7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4`
2. `f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816`
3. `e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381`
4. `711ba3e2310347645f6734537041959eb6f6dd419d26882bdc4264ad66fdc717`

自动门：

- atlas 左右 CIE76 p95 不超过 `max(4, 3 x white_repeat_noise_p95)`；
- 白恢复 p95 使用同一门，最大值还必须不超过 `max(8, 1.5 x threshold)`；
- AA/CC 对比按码输出 `R20_LINKED_EXPLORATORY_EFFECT`、`NO_RESOLVED_EFFECT` 或
  `CONTROLLER_INCONSISTENT`。

其中第一种状态名为既有 schema 的兼容名称，严格含义是“完整 tuple 变化相关的探索性效应”；
它不单独证明 R20 字节因果，也不证明新颜色或总线逐字节等同。证据由
`tools/mf1750_same_r20_parity_evidence_bundle.py` 封存。

## 6. 批次 2：配方—位置置换（4 次刷新）

固件环境：`runtime_lut_recipe_position_permutation_v1`  
contract：`5c628ccd1755718a6cc7aa0163523122f083bd51085f356ce75c23ea62d4dda2`

| 次序 | 动作 | 映射 |
|---:|---|---|
| 1 | source | `source=(column+3) mod 8` |
| 2 | middle | `middle=7-row` |
| 3 | target | 全部写 code0，形成置换后的 64 配方矩阵 |
| 4 | factory-OTP white | 建立批次 3 白锚 |

动作 ID 依次为：

1. `afd5f9834cedb536ee50b62fd80f1a1b038786f8512e9594c34a515ba280cd00`
2. `c75a829ed8116c228913525fff87db5fac41e127dc45013ee86386e9ee65dcbf`
3. `8a9a17c4e69b20278b513965cde248e1e6036dceee8943e269ed0693d216b4c9`
4. `4d4b247bc8d398462102b3d8cabd1bf29970bda89cfb3d8f05b368f628000a99`

对每个控制器分别计算 L*/a*/b* 三个有效分量的 Pearson 相关，并取有效分量均值：

- recipe correlation `>= 0.80`；
- recipe correlation - physical-position correlation `>= 0.25`。

Pearson 对整体 offset/scale 不敏感，所以通过只可称为 `recipe-linked exploratory candidate`，
颜色标签保持 `UNASSIGNED`；失败则表示当前数据不足以区分 recipe 与位置。证据工具
`tools/mf1750_recipe_position_permutation_evidence_bundle.py` 强制绑定 G-1、四动作、四照片、
P1 分析、P0/P1 对比、终态 60-patch 白门以及同一相机/噪声/几何身份。

## 7. 批次 3：完整 tuple 轮换＋真正局部 HOLD（4 次刷新）

固件环境：`runtime_lut_true_r20_partial_hold_v1`  
contract：`38698de14b6a2a7a96e072d4de025cb0708ae167b81c348f6c4337dc3654eb63`

批次 3 runner 在任何网络、claim 或设备动作前必须同时验证：

- 批次 1 sealed evidence；
- 批次 2 sealed evidence；
- 二者的相机、噪声、几何和 campaign 连续性。

| 次序 | 完整 tuple / ROI | 传输码 | HOLD 对象 |
|---:|---|---:|---|
| 1 | active，A=`(48,64,160,120)` | code0 | 无 |
| 2 | commented，B=`(304,240,160,120)` | code0 | A |
| 3 | active，C=`(48,416,160,120)` | code2 | A、B |
| 4 | factory-OTP white | white | 清除 A/B/C |

动作 ID 依次为：

1. `9dde1d9805c5c08880a7cce3be4844faacdafe3e250de1a8dc8b2bbda8a17a48`
2. `cef8f2bb0ddd3ec96c2929a754b22a403fcb38e34ff7278ef2fb4c83ea1ea29f`
3. `ef7996a165effed3fff26dc1595b6a484f3abab06ed73ae4e9faeaeb72a56444`
4. `fd50aee18578d0d91a542471728883b9c3a2df24f0ed35d2298dfda71bbcd6bf`

静态照片门检查：旧 ROI 动作前后、当前新增 ROI 相对白锚、左右配对、两块背景以及底边相对
异常。它没有宣称逐像素不变、完整轮廓等同、中心接缝资格或绝对颜色资格。

视频门要求每动作至少 25 秒、至少 10 帧预卷，并覆盖被保护 ROI 与背景；A/WHITE 动作虽无
旧 ROI，也仍必须满足时长与背景检查。最终白态另走独立 60-patch 门。聚合证据工具
`tools/mf1750_true_r20_partial_hold_evidence_bundle.py` 绑定四动作、四组前后照片、四段视频、
静态/视频门、最终白门以及批次 1/2 证据。

全部通过后只允许写：

`complete-tuple switching with three-ROI local coexistence preliminary PASS`

仍不得外推到任意 LUT、任意码、任意窗口、256 色照片能力或长期稳定性。

## 8. 唯一执行顺序与刷新预算

`G-1 -> G0 -> Batch1 -> seal B1 -> Batch2 -> seal B2 -> Batch3 -> seal B3`

- G-1：0 次刷新；
- G0：1 次刷新；
- Batch1：4 次刷新；
- Batch2：4 次刷新；
- Batch3：4 次刷新；
- 合计：`13` 次可见刷新。

同一白态可拍多张重复噪声照片，不增加刷新。每个动作都是显式 ordinal、独立 ARM/EXECUTE、
独立 claim 和不可覆盖 evidence；没有 retry、fallback、recovery 或 autochain。相机自动分析取代
人工颜色裁决，但现场安全观察、电流/温度监控和物理切断仍不能无人值守。

## 9. 故障和收容规则

出现任一项立即停止当前 campaign，并将 J2 置 OFF：

- 电源限流、异常电流/温升、异响、异味或发热；
- BUSY timeout、阶段缺失或持续时间超过同类基线 2 倍；
- 左右失步、全局灰化、固定横纵线、中心接缝或底边黑线异常；
- 被保护 ROI 闪烁、明显灰化、变色或面积/边缘门失败；
- identity、payload、frame、PTLW、DTM、claim、相机或 evidence 完整性失败。

失败后不得把计划中的“下一次白动作”当作自动恢复并继续消费同一 campaign。需要恢复时，必须
另建、验证并显式授权一个独立 containment；没有隐式补救，也不覆盖已封存输出。

## 10. 离线实现与验证结论

- 三套固件均已 clean build，BIN/ELF 与冻结身份完全一致；
- G-1、白重复噪声、照片/视频采集、AA/CC 比较、Batch1/2/3 evidence bundle 和 Batch3
  双前置校验均已实现；
- 18 个新增/修改文件通过 Ruff check、Ruff format check 和 py_compile；
- 28 个相关测试文件合并运行：`317 passed in 43.93s`；
- 三个 once runner 的 dry-validate 全部通过；离线验证没有访问硬件或网络。

详细构件、固件 SHA-256 和现场前置检查见：
`docs/MF1750_STAGE3_TRUE_R20_PARITY_PERMUTATION_HOLD_OFFLINE_READINESS_2026-08-28.md`。
