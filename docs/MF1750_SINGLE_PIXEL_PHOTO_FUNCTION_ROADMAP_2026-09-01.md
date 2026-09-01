# MF1750 单像素静态照片功能路线（2026-09-01）

## 目标与边界

当前目标不是继续最大化“看起来不同”的色块数量，而是先建立一条可重复、可组合、可恢复的
静态照片显示链：

1. 已稳定基色；
2. 同一色相的真实明度层级或中性灰阶；
3. 一次构色后能被局部 HOLD，且可从独立白锚重新构色；
4. 两套或多套已知兼容 LUT 能按顺序共存；
5. 把每个可用颜色表示为 controller-specific recipe；
6. 将照片像素映射为 recipe，并生成可审计的刷新计划。

空间抖动、交错条纹和网点只属于空间混色，不计作单像素颜色。CS1 与 CS2 是两个独立的物理
颜色系统；左右差异不能互相充当副本，也不能拼成明度阶梯。

### 256 色／10 阶的冻结口径

最终研究目标现明确为 `256` 个总逻辑槽位，而不是 `256×10`：

```text
16 个中性色槽
+ 12 个彩色色相族 × 2 条彩度/轻微色相子轨 × 10 个明度档
= 256 个单像素逻辑颜色槽
```

十二个彩色色相族为 `R/RO/O/Y/YG/G/T/C/B/I/V/M`。十阶是每条彩度／子色相轨的目标纵轴，
不是当前能力声明；实际按 `3阶→5阶→10阶` 递进。全屏色数必须由 CS1/CS2 两套独立 recipe
经过显式跨 controller 光学匹配后计数，不能相加，也不能把同名 slot 的集合交集当作匹配证据。
完整口径和替代方法见 `MF1750_256_COLOR_10_LIGHTNESS_TARGET_AND_ADJUSTED_SEARCH_2026-09-01.md`。

## 功能路径与当前状态

| 门 | 功能 | 当前状态 | 通过后进入 |
|---|---|---|---|
| F0 | 原厂 OTP 白基线与恢复 | V3 独立白 successor COMPLETE，camera-visible review 有限 PASS，relay OFF | fresh successor source gate |
| F1 | 位置平衡灰阶／明度机制 | fresh V3 主固件与独立白 successor 已离线封印并审计 PASS；等待下一真屏 | F3 |
| F2 | 稳定基色色相明度 Latin 筛查 | V3 L1–L4 COMPLETE；一次性 CS2 信号存在但 identical-target 后坍缩，0 qualified；白恢复完成 | 作为 REVIEW 级 HOLD 诊断备选 |
| F3 | 从白锚重新构色复现 | 比较器、独立 reconstruction G1–G3 主固件及其白 successor 均已离线封印；等待 live 证据 | F4 |
| F4 | 局部 HOLD 与跨 LUT 共存 | 基础黑／蓝／绿局部累积已通过；候选专用 HOLD 主固件、独立白 successor 及 T0/T1/T2 比较器均完成，等待精确 G3 COMPLETE | F5 |
| F5 | 可用 recipe 调色板 | 等待 F1/F3/F4 | F6 |
| F6 | 照片逐像素映射与调度 | 离线调度器已实现；硬件调色板仍为 0 | 照片真屏 |
| F7 | 固定照片执行 bundle | 离线导出器已实现；等待 F5/F6 的合格输入 | 固件 codegen／静态照片真屏 |

F2/V3 已完整执行 L1–L4，并由自己的独立 factory-OTP white successor 重建当前白锚。完全
同曝光的 L3/L4 比较确认：CS2 一次性历史码跨度从 `7.059 L*` 收敛到 `2.157 L*`，因此不能
把原位 identical-target repeat 当作历史 recipe 的稳定性门。当前 qualified 新色、灰阶和明度
层级仍均为 `0`。

旧 F1/V2 仍绑定已经消费的 W11，禁止直接执行。下一真屏必须使用新的 campaign/contract/NVS/
claim 身份，精确绑定 V3 白恢复、48MP retained review 和 relay-OFF 证据。

## 明度／灰阶判定

第一轮只回答机制问题，不扩大新色相：

- F1：固定源态、位置平衡的历史配方、混合目标态，搜索中性灰或同色相 L* 分离；
- F2：固定一个已稳定目标码，用 Latin 排列的中间历史搜索同色相明度差异；
- 每个 recipe 在每个 controller 内有多个空间副本；
- 必须同时满足单像素纯色、边界干净、位置重复稳定、`|Delta L*| >= 8`、色相角差不超过 `10 deg`；
- 摄像头只做相对粗筛，结果保持 `COARSE_LIGHTNESS_CANDIDATE`，不会自动授予 qualified 色彩。

若发现候选，不再在原候选像素上重复 target：

- 先用已验证的 clean PTLW transport 在候选区域外更新探针，确认候选区被 HOLD；
- 再执行独立 factory-OTP 白恢复，取得新的白锚；
- 从该白锚用新 campaign/contract/NVS/claim/action 身份重新执行逐字节相同的
  source→middle→target 构色链；旧动作不得重放或通过清 NVS 复用；
- 与第一次结果按 controller、recipe、位置比较，并用 reconstruction 自己的独立白 successor 收尾；
- 至少两次 fresh-white construction 一致后，才能获得复现证据；三次及长时保持后置；
- 没有命中时，不进入大规模色相穷举，先完成下一种有界明度机制。

历史配方无命中后的有限后备顺序现调整为：已知兼容完整 profile 的直接 endpoint 三阶复核 →
两套完整 profile 的 endpoint 地图 → 不修改 LUT、每次 BUSY 正常结束的局部完整刷新剂量梯级。
现有 T3 partial-camera 数据中的 `CS1 active C0/C6/C1` 分别约为
`L*=31.17/50.53/68.25`、总色相角跨度约 `9.8°`，是首个三阶复核候选，但仍为 camera-relative
REVIEW、`qualified=0`。R20 record 字段和极性未解析，所以有界 R20 phase family 继续
`OFFLINE BLOCKED`；禁止 hybrid profile、任意字节插值、未知命令穷举和 BUSY 中断。

## 功能优先的展开顺序

这里把“拓展能力”与“枚举更多色相”严格分开。F1 先寻找一种能够稳定改变同一单像素终态
明度的机制；只要机制命中，就优先把它参数化并迁移到已经稳定的各个基色，而不是继续扩大
新色相搜索：

1. 对一个目标基色证明亮／中／暗至少两个可分层级；
2. 对候选层级证明局部 HOLD，不重画已经形成的像素；
3. 从独立白锚重新构造同一层级，证明功能复现；
4. 用相同机制依次覆盖现有稳定基色，形成 controller-specific 明度族；
5. 再验证不同 LUT/profile 的方向性保持，允许多个明度族共存；
6. 接入调色板、逐像素 recipe 映射和静态照片刷新计划；
7. 将封存计划生成为固定编译帧和逐动作照片固件，并配独立白 successor；
8. 上述主链跑通后，才恢复新色相枚举和长时可靠性。

因此，下一阶段的成果指标不是“又找到多少种看起来不同的色块”，而是能否新增
`LIGHTNESS_CONTROL`、`LOCAL_HOLD`、`FRESH_RECONSTRUCTION`、`CROSS_LUT_RETENTION` 和
`PHOTO_MAPPING` 这些可组合能力。第一轮只要求功能可重复两次；第三次复现与长时间保持仍后置，
不会阻塞框架闭环，但也不会因此提前授予生产级资格。

各明度族独立过门：只要有一族完成全部六门，就可作为受限调色板子集进入离线照片调度；
尚未通过的基色会被明确排除，不必等待所有稳定基色都完成，也不得用已通过的一族替代另一族的
证据。这样优先证明端到端功能，同时保留后续逐色扩充空间。

## 软件链

- `host.static_photo.lightness_screen`：按 controller/profile/target 建组，对空间副本、纯色、边界、
  L* 与色相进行 fail-closed 粗筛。不同 controller 或不同 profile 永不合并，输出中的 qualified
  计数固定为 0。
- `tools.mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_photo_analyzer`：只接受
  `VID_32E4:PID_4801` 的 live-synchronized、设置锁定帧，自动拟合双侧 8×8 网格，输出 128 格
  Lab、四边缺陷与每侧 16 recipe × 4 副本的粗筛结果；可复用 sealed Latin V3 的固定机位
  homography，但相机实例、后端、4000×3000、mount 和请求／实际设置必须完全一致。
- `host.static_photo.controller_palette_inventory`：显式区分 direct-target 的
  `identical-target-repeat` 与历史配方的 `fresh-white-reconstruction`；历史明度不得用前者代替后者。
- `host.static_photo.multi_lut_hold_schedule`：只有 recipe、复现、局部 HOLD、白恢复和跨 profile
  保持能力都已有资格时，才生成 source/middle/target 帧；其余像素必须使用该 profile 已验证的
  HOLD code。
- `host.static_photo.v3_lightness_workflow`：把相机粗筛严格转换为
  `HOLD → 独立白锚 → fresh reconstruction → 最终白恢复` 的非自动执行计划。
- `host.static_photo.position_balanced_hold_compare`：精确比较 T0=G3、T1=H1、T2=H2；分别检查
  候选格保持、H1 探针在 H2 后保持、H2 探针出现和四边纯色，并输出 same-profile HOLD 与
  directional cross-LUT REVIEW。缺探针或缺四副本时固定为未测试，不会自动生成 passed evidence。
- `host.static_photo.fresh_reconstruction_compare`：比较两个不同 campaign/action 的独立 G3；
  要求三阶段 frame 与双 controller DTM 光学 payload 同构、48MP 设置和可见格集合一致。支持
  全 128 格或合规 partial-camera；只有四副本齐全的 recipe 可得到 REVIEW，缺失固定为
  `UNTESTED_MISSING_REPLICAS`，qualified 计数始终为 0。
- `host.static_photo.lightness_family_plan`：把首个已证明机制迁移到已有稳定 endpoint，按每侧、
  每基色生成 C0–C7、四副本位置平衡批次；各族独立过六门，允许只把 READY 子集交给照片调度。
- 现有照片映射层只能消费 qualified recipe；候选 recipe 不得直接用于照片真屏。
- 最终照片执行层采用固定编译帧、显式 one-shot action 和独立白 successor，不开放运行时 raw
  frame 或动态 LUT/payload 入口；其输入必须绑定 F6 调度 SHA-256。
- `host.static_photo.fixed_photo_execution` 已能把 sealed schedule 导出为每 pass 固定 `.bin`、
  descriptor/action identity、codegen 元数据、canonical manifest 与 `SHA256SUMS.txt`；它只生成
  离线 bundle，不生成 live authority，也不虚构尚未存在的独立白 successor 身份。
- `host.static_photo.function_first_orchestrator` 把上述能力门串成确定性状态机：没有
  `PALETTE_READY` 明度族时禁止生成照片下游工件；一旦某个族通过，仅开放该族的有限 palette
  子集，随后依次要求 palette inventory → 照片像素映射 → multi-LUT HOLD schedule → source-white
  authority → fixed-photo bundle。扩大色相和长时可靠性在整条照片功能链之前保持后置。

上述 static-photo 框架回归当前为 `112 passed`；功能路径 JSON 为 `15 passed`；F1、候选 HOLD、
fresh reconstruction 关键链合并复验为 `85 passed`。F1／HOLD／reconstruction 独立审计均 PASS，
对应 `31 / 24 / 24` 项 SHA-256 清单逐项复核通过。这些测试只证明离线合同、固件身份与算法行为，
不等于真屏颜色或硬件可靠性已经通过。

## 上机最短路径

1. 已完成：V3 L1→L4、同曝光 48MP 比较、独立原厂白恢复、相机可见检查与 relay OFF；
2. 已完成离线：16-recipe 位置平衡明度机制已重新绑定到最新白锚，独立构建、runner 审计和
   自身 factory-OTP white successor 均已通过；
3. 下一真屏：source→position-balanced middle→mixed target，拍摄并只作 controller-local 粗筛；
4. 只有命中单像素纯色、边界、位置和 `Delta L*` 门的 recipe 才进入局部 HOLD；
5. HOLD 通过后，独立刷白，并从白锚重新构色至少一次形成第二次 construction；
6. reconstruction 固件固定为 campaign `EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1`、
   contract `5d76fda3bf199d29538ec0c6555db4a294b6b11ffb5805613805b4f759b7d132`，主 BIN
   `9b8493903baa1c656cf387481a52f217293d2f2ccedb09afebd2cdeda400f2a3`；其独立白 successor BIN
   `e78cd7b18d8c020d09f1fc554cd4f0f2063cfcd8c3b590391ed637b0260bba45`；
7. 两次 fresh construction 一致后接入 controller-specific palette 与 multi-LUT 调度；
8. 明度机制仍阴性时，才进入已知兼容 profile／有界 R20 phase family，不做未知命令穷举。

## 后置工作

以下项目不会丢弃，但不阻塞当前功能框架：更多色相枚举、第三次 fresh-run 资格化、60 秒／10 分钟
保持、24 小时稳定性、精密色卡标定和批量可靠性统计。
