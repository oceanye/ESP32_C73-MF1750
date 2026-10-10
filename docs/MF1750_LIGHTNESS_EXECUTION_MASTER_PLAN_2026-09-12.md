# MF1750 单像素明度实验：统一执行计划

计划版本：`MF1750_LIGHTNESS_MASTER_V1_20260912`。本文件规定执行顺序；`STATUS_HANDOFF.md` 顶部记录实际完成位置。最新用户指令优先；旧 runbook、旧报告和旧合同保留为历史证据，不能自行成为下一动作的放行依据。

## 2026-09-13 操作者修订与本轮终点

最新明确指令“电气信息正常，不用作为控制项，可以直接进入刷新”优先于下文历史电气门。电气信息改为记录项，缺外测不再阻断；`electrical_state_proven=false`保持真实，不伪造仪器/实测值。其余身份、同boot诊断、NVS/claim及1次动作限制保留。

本轮已完成LH1 SOURCE ordinal1一次，原轮询连接reset保留FAIL_STOP，随后只读获得同boot COMPLETE并严格核验PASS，relay已OFF，qualified0。唯一入口为STATUS顶部及`LH1_SOURCE_FIELD_20260913_V3/session-outcome.json`；历史W0未执行等状态均以最新状态覆盖。禁止重跑SOURCE或因改目录/runner产生新额度。下一MIDDLE/恢复须独立封印和放行。

## 1. 目标与定义

- 总目标：`16 neutral + 12 hue families × 2 tracks × 10 lightness ranks = 256` 个单像素逻辑槽；当前 `qualified=0`。
- 本阶段优先彩色**同色相明度**。明度以规定照明下的 L* 描述；不研究背光调光。没有背光不意味着没有反射光亮度，彩色屏也可以出现低彩度/中性状态；本项目将其另列 neutral 分支，不混入彩色等级。
- `3 → 5 → 10` 是每个 hue family/track 的不同明度等级数量。照片数、位置副本数、fresh 重建次数、刷新次数、两侧 controller 数都不能凑等级。
- 一个候选配方在可分辨的均匀 patch 内对每个像素执行相同状态转移。patch 是单像素状态的测量代理；不使用空间抖动、邻像素混色或不同 controller 拼接构色。相机不能逐物理像素分辨时必须保留这一限制。
- 两个 controller 分别筛选、分别验证，最后再匹配。单侧成功、一次 P2 COMPLETE、单张照片或一个端点都不是稳定槽位资格。

## 2. 固定研究依据与适用边界

主要资料为 `参考资料/SPD1657B_1.1.pdf`，44 页，正文 Rev 1.1 / Sep 2024，SHA-256 `7f867e165f4662aa525ba7f4e9d3413b0dc8f2ae3f3ae63d5c4a4023c5f0e41a`。完整解释见 [资料分析](MF1750_SPD1657B_V11_DATASHEET_REVIEW_2026-09-10.md) 和 [综合对照](MF1750_SPD1657B_V11_COMPLETE_ANALYSIS_AND_LIGHTNESS_TEST_PLAN_2026-09-11.md)。

| 已知事实 | 执行约束 |
|---|---|
| 3-bit KPixel 经 DDX 映射到 Gray 0…7（p25、28） | Gray 是索引名称，不承诺中性灰、等间隔 L* 或八个稳定等级 |
| R30 有名义 25/32/43/50/65/75/85/100 Hz（p26） | 仅解释已有编码；没有当前获准的 PLL 扫描集合 |
| LUT_EN、PWR、VDCS、末帧和温度语义部分已知（p18–33） | 芯片范围不等于 MF1750 面板安全范围；请求值和测量值分开 |
| 级联 slave 共用 master 时钟及高压（p15） | 不把 CS1/CS2 当作独立调频/调压器 |
| PTLW 窗口内外 gate 都扫描（p31） | 不由窗口或 code 7 推断 HOLD/零驱动 |
| 浮空后下一操作须等完全放电（p36） | relay OFF、POF 命令或固定等待时间均不能独自证明电气条件 |
| 当前 PDF 未给 R20/R21、11-byte phase/repeat ABI | 内部 phase=`OPAQUE`；不猜 RESET/SHAKE/DRIVE 字段，不扫描保留命令，不写 OTP |

公共初始化 PWR=`3F` 单参数、PLL=`08`，runtime 六参数 PWR 首字节=`0F` 与资料之间仍有模式适用性差异。保留来源和实际写序，不为“符合资料”直接改值。BTST Phase A/B/C 属于升压软启动，不能当作像素波形阶段。

## 3. 当前状态与材料成熟度

2026-09-12 本次已采集：指定相机 1 张原图、COM 枚举、1 次 exact IPv4↔MAC 探测、relay 状态查询 1 次、白 successor 的 4 次只读 GET。无 relay 切换、刷写、复位、ARM、EXECUTE、driver 或可见刷新。

- 画面可见部分仍彩色；大部分屏幕在镜头外，不能证明全屏状态。原 sidecar 的 `full_panel` 是采集请求，已由独立 visual review 纠正为部分覆盖；原文件不重写。
- 当次 relay query=`OFF`，`electrical_state_proven=false`；未获得外部负载侧/共地测量。
- 当次设备只读报告为旧 white successor、READY、NOT_EXECUTED、cursor=1、NVS key absent。boot/IP/COM 只对本次记录有效，后续不得抄成固定身份。
- 旧 white successor 的诊断漏报 `source_main_offline_build_file_sha256`，是固件 JSON 身份输出缺陷；不能删掉主机校验字段绕过。新修复产物须通过**实际 JSON 解析与原严格验证器**，编译成功或字符串计数不等于修复成功。

| 材料 | 已完成 | 不能据此宣称 |
|---|---|---|
| P2 原始 ordinal 1 | 已有历史 COMPLETE、action/status、照片和封印 | 可再次运行 P2，或已形成稳定明度 |
| 旧 white BIN `acf27e…79277` | 文件封印与历史未执行证据可核对 | 当前 live identity 校验通过 |
| white identity 修复 LH4 | 隔离编译、完整 identityJson 原生运行、严格 JSON 解析、原 host identity 验证及负例拒绝已通过 | 已有完成封印的现场 runner，或可以新 claims 目录绕过旧动作 |
| LH1 R3 算法/固件 | 三帧、128 ROI、原生与 Python 离线验证，`live_ready=false` | 已有可运行的现场 host/diagnostic/资格门 |
| 明度分析器 | `create / review-p2 / analyze`；四位置与同色相链筛选 | 自动完成 HOLD、fresh、retention、双 controller 或资格审核 |

**重要依赖：** LH1 R3 的 `SOURCE_WHITE` 固定旧 white BIN/action 身份。white 修复 BIN 改变后，即使沿用同一 NVS namespace/key，也不能直接把 LH1 R3 当成已匹配的新链。须独立封印新 LH1 source 绑定、现场 runner 和实际 white terminal/clean-white review；旧包完整保留。设备防重放 NVS 和历史 claims 则必须保留并核查，不清零、不以目录变化重放。

LH4 BIN SHA=`dc93c95a956eecf7d9cb753e5fb82ea16e5f2142694a8fcd22157481570d2de6`，ELF SHA=`ff3793efde294bf981f3b1932799fdc574917fe33c0f1d15bf636367c5aba067`。独立复核：[root-review.json](../.test-output/offline/MF1750_WHITE_LH4_ROOT_REVIEW_20260912_V1/root-review.json)。原 host 拒绝错误 source report hash、source contract 和 running ELF 的负例仍通过；LH2/LH3 的真实 JSON 无效，保留为 INVALID，不可刷写。当前 adapter 只有离线验证能力，不能替代新现场 runner 的完整 preflight/claim/terminal 合同。

## 4. 本轮授权边界与唯一入口

操作者本轮已说“现在可以真屏测试”，并在此前明确授权由助手控制继电器、先刷白再判定。这足以继续必要离线修复、只读前置和条件满足后的**一次独立白恢复**，无需反复询问同一权限；授权不替代相机覆盖、电气读数或协议证据。

当前唯一现场动作入口是 `W0：白恢复`。先前屏幕已是彩色，不能要求操作者把它描述成 retained clean-white；必须通过独立恢复建立白源。W0 完成后立即停止判读，不能自动进入 LH1、P2 重跑、HOLD、ordinal 2 或第二次白恢复。

```text
OFFLINE_REPAIR_AND_SEAL
  → CURRENT_CAMERA_AND_ELECTRICAL_EVIDENCE
  → FRESH_DEVICE_BINDING
  → APP_ONLY_FLASH_AND_VERIFY
  → POST_FLASH_SAME_BOOT_J2_OFF_DIAGNOSTIC
  → VERIFIED_J2_ON_AND_IDLE_HIGH
  → ONE_WHITE_ARM_EXECUTE
  → TERMINAL_AND_WHITE_OPTICAL_REVIEW
  → STOP

独立下一批：NEW_LH1_SOURCE_BINDING_AND_RUNNER
  → SOURCE ordinal 1 → STOP_AND_REVIEW
  → MIDDLE ordinal 2 → STOP_AND_REVIEW
  → TARGET ordinal 3 → STOP_AND_REVIEW
  → SCREEN → HOLD → 3 FRESH RECONSTRUCTIONS → RETENTION → CONTROLLER MATCH
```

箭头表示前置依赖，不是自动连续执行授权。新的 mutation 必须有已记录的具体 action、有效前态和当前批次放行；相机静置采集本身不是可见刷新。

## 5. 每批通用前置

1. 读 STATUS 顶部和本计划，核对上轮是否有未决 BUSY、FAULT、CONSUMED、身份异常或恢复失败；有则先分析，不重发。
2. 保存 git 状态，保护用户修改；不 cleanup/reset、覆盖生产目录、`git add -A`、commit、push。输出使用新路径/O_EXCL，旧证据只读。
3. 复核 action/contract/descriptor/profile、BIN/ELF、实际编译源码、runner 及其依赖哈希。不能只核对 main.cpp 包装文件而漏掉它 include 的 driver。
4. fresh 枚举 COM 和相机；只从本次来源取得 IP 候选并建立 exact IPv4↔MAC；复位/刷写后重新取得正在运行固件的 boot 和身份。保留原始枚举，不把同名端口当永久身份。
5. 独立核对 relay 型号、VID/PID、PnP instance、USB location、channel、COM1-NO1；查询仅记录 commanded state。外部测量应包括仪器、测点、相对 GND、时刻、供电/放电读数与依据；未知写 null。没有外部证据时不把 `electrical_state_proven` 改成 true。
6. 相机只用 `VID_32E4:PID_4801`。整屏及四边入镜、无遮挡，光源/机位稳定；请求设置与实际读回分列。身份正确但只拍到部分屏，仍不能通过全屏光学门。
7. 记录温度来源、raw、解码值和采集时刻。TSC 会触发 BUSY；当前 J2-OFF 四 GET 不能偷偷加入 TSC。无受控温度采集接口时缺值不能伪造，不能用室温估计冒充传感器实测。
8. 预先固定 ROI、阈值版本、输出目录、一次性 identity、超时/轮询策略及停止动作。协议超时采用封印 runner 合同；不临场延长、自动重试或用重启排除错误。

## 6. W0：一次白恢复的具体流程

| 步骤 | 执行动作 | 必须留下的证据/判定 |
|---|---|---|
| W0.1 | 完成 white JSON 修复的隔离生成、编译、真实 JSON 解析、host 验证和审计 | 新 BIN/ELF 与 runner 精确绑定；原 source/driver/NVS/claims 保存；错误候选标 INVALID |
| W0.2 | 当前全屏照片、relay OFF 查询、外部电气证据、fresh COM/IP↔MAC | 缺任一物理前置为 HOLD_FOR_EVIDENCE，不刷写/接通/刷新 |
| W0.3 | 仅写 app `0x10000`，verify 后按工具合同启动一次 | 不写 bootloader/partition/NVS；保存写入/verify 原始输出，失败停止 |
| W0.4 | **刷写后**重新读新固件身份，执行同 boot J2-OFF diagnostic | 恰好 4 GET、0 POST、0 claim、0 driver、0 refresh；字段及新 ELF 匹配；J2-OFF 合同 raw BUSY=0 |
| W0.5 | 核对共地、电气条件；只按已绑定 channel 接通；读取执行前状态 | relay ON 的命令/独立查询与外部证据分列；run 前重新 4 GET，要求同 boot 且 raw BUSY=1 空闲高电平 |
| W0.6 | 固定 white action：1 ARM、1 EXECUTE | 原子防重放 claim、NVS、source terminal 精确匹配；不换目录或清 cursor 重试 |
| W0.7 | 等待正常 BUSY/终态，保留 status 时间线 | 1 driver / 1 visible refresh；COMPLETE/result/valid、身份和计数全通过。网络不确定时不重发 mutation |
| W0.8 | 采集整屏照片和人工/视觉观察，按封印收尾合同处理 relay | 接点 OFF 只能在正常完成及收尾条件已满足后进行；不是自动刷白，也不是放电实证 |
| W0.9 | 停住，分别作协议与光学 review | 白场不得有残留色块、旧格、边框污染、色斑或固定线；缺全屏证据为 HOLD，明显异常为 FAIL_STOP |

W0 只建立新的白源，不产生明度资格。原白 successor 使用 factory OTP/WF23_25 完整路径；修复不得顺带修改 PLL、PWR、LUT、VCOM、分辨率或初始化。W0 成功后不可自动开始 LH1。

### 6.1 固定工具与调用边界

| 用途 | 实际工具/入口 | 本轮约束 |
|---|---|---|
| LH4 离线验证 | `python -m tools.mf1750_p2_white_lh4_once dry-validate` | 不访问设备；PASS 仅说明离线范围 |
| app-only 写入 | `tools.mf1750_app_only_single_boot_flash.py` | 新枚举 port、新输出；BIN 为本计划 LH4 hash；write 后 no_reset，verify 后一次 hard_reset；不写 NVS |
| 刷写后诊断 | `python -m tools.mf1750_p2_white_lh4_once diagnose-j2-off` | 必须显式传本次 base-url、exact binding、固定 source terminal 和真实 J2-OFF 确认 |
| 一次白恢复 | 同模块 `run` | 仅 W0.1–W0.5 全通过后；J2-ON/共地确认来自证据；不把命令行 flag 当测量 |
| relay 绑定/查询 | `tools.mf17506_stage23.relay_rebind` | 使用本次精确 PnP/USB location/COM；不直接复用历史 COM14 |
| relay 切换 | `tools.mf17506_stage23.relay_exact_bound_switch` | 使用本次 rebind seal；一条反馈命令及一条独立查询，无自动重试 |
| retained 当前画面 | `tools.mf1750_camera_capture_evidence.py capture-retained` | exact VID/PID；不把历史 action anchor 当持续身份实证 |
| 当前 action 后照片 | 同模块 `capture` | 绑定本次 terminal；覆盖范围仍须实际视觉复核 |
| 离线明度分析 | `python -m tools.mf1750_lightness_test analyze --input <已封存观测> --output <新文件>` | 输入真实 ROI/噪声/标定来源；输出不授予资格 |

LH4 runner 固定输出为 `.test-output/hardware/MF1750_P2_WHITE_LH4_20260912_V1`；诊断和 action 路径由 runner 派生，执行前必须不存在相应输出。它与当前只读证据目录不同。原永久 claims 目录仍为 `.test-output/hardware/.mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_claims`；white action=`677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19`，NVS=`p2catwsv1/used_p2cw1`。新固件哈希不是新的刷新额度。

source terminal 固定为历史 P2 ordinal 1：`.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/action-01-commented-complete-position-balanced-4x8-endpoint-atlas.json`。运行前须通过原文件及完整 lineage 校验，不能复制一个 COMPLETE 字段自造 source。IP、COM、boot 不写成可直接重放的固定命令。

W0 批次固定沿用 runner 的 `poll_seconds=65.0`、`poll_count=20` 和 HTTP/固件超时合同；具体请求/超时以被哈希绑定的宿主依赖为准。轮询等待不是再次 EXECUTE；网络错误或超时不提高轮询额度、不重发 mutation。宿主轮询并不等于示波器测得的连续 BUSY 波形：status 能观测到的时间点与固件阶段时间分列，缺少边沿实测时明确标注限制。

整屏白场、外部电气、温度可比性、人工生命周期及资格审查仍是证据审查职责；当前 runner 没有实现这些自动软件门。新输出路径防覆盖、hash/lineage、协议/NVS/claim 检查不能代替它们。

## 7. LH1：固定完整 profile 的历史配方测试

必须先新建与实际 W0 修复版 terminal/BIN/action 匹配的 source 合同和现场 runner，具备 post-flash 同 boot J2-OFF 诊断、bodyless ARM/EXECUTE、持久化防重放及逐步 review 绑定。当前旧 R3 只提供离线实现，不允许用几个裸 HTTP POST 代替正式 runner。

几何保持 `CS1/CS2 × 16 recipes × TL/TR/BL/BR = 128` 测量 ROI；controller-local 坐标和 CS2 180°映射用算法生成，不凭照片左右猜。两比较组是 TARGET_C3、TARGET_C7，每组 8 种 MIDDLE 配方；不同组不拼成等级链。

| 独立动作 | 固定内容 | 本步结束后 |
|---|---|---|
| S1 / ordinal 1 | 两 controller 使用 active tuple，SOURCE=C7 | 协议、源态、全屏照片通过后停；本步不能得出历史配方明度结果 |
| S2 / ordinal 2 | 两 controller 使用 commented tuple，MIDDLE=M0…M7 的位置平衡矩阵 | 绑定 S1 同链 prior review，完整证据通过后停 |
| S3 / ordinal 3 | 两 controller 使用 active tuple，TARGET=T3 或 T7，16 个配方固定在生成 ROI | 绑定 S2，完整证据通过后停，再离线分析 |

每一步均为 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh。两 controller 一次整屏更新不是两次可见刷新；三个动作也不能记为“一次刷新测试”。fresh white 另计 1 次。

同态每 ROI 至少 10 张照片。照片可共享整屏采集，但 ROI 物理位置不能重复，也不能把连续照片当四位置。每 target 只有 8 种不同配方，因此可筛 3/5 级；要测 10 级必须增加至少两种不同且有根据的配方，不能复拍凑数。

## 8. 光学采集与判定规则

采集固定参考档为 MJPG 4000×3000 @ 15 fps、focus=79、exposure=-6、WB=4600，autofocus/auto-WB 关闭、请求 auto-exposure=0.25；只有在本次实际读回和稳定性满足时才作为本次档。光源或机位变化需新 setup_id、新基线；不能为达到阈值临时调曝光再混合前后数据。完整 JPEG/视频、请求与读回、失败帧/预热帧、host 时刻全部保存。

不支持的 RAW/ISO/硬件触发或时间戳如实标 false/null 并注明“本采集后端未暴露”或实际能力证据；不能据 JPEG 推造 RAW。未经色卡/光谱或其他可追溯标定的 Lab 写 `camera-relative`；标定 Lab 独立数据集，不能仅凭文件名/哈希改名为 calibrated。

ROI 在看结果前固定：每个均匀 patch 中央 60%，另留全屏四边、分界和背景对照 ROI。保存图像像素坐标、controller-local 坐标、四象限标签、透视映射及排除区。原图不裁掉边缘后冒称全屏；展示图与原始定量输入分开。

### 8.1 已实现的筛选判据

阈值版本固定为 `MF1750_LIGHTNESS_TEST_V1_20260911`，来自 `host/static_photo/lightness_test.py`；仅离线筛选，不是现场 admission 或厂商规格。

| 指标 | 判据 |
|---|---|
| 彩色轴 | C* > 8；其余转 neutral 待测，不能硬算色相 |
| 等级分离 | 按 L* 排序，每相邻/全链配对 ΔL*≥2、ΔE00≥3、色相差≤5° |
| 位置一致 | 四位置相对分量中位数的 P95 abs(ΔL*)≤3、ΔE76≤5 |
| 噪声 | 每 ROI N≥10；L* 与 ΔE00 各自用 max(5×MAD, CI95 半宽)；配对取两 ROI 对应门较大者 |
| 四位置配对 | 中位数及每个对应象限都须同方向，并通过色相、分离和各自噪声门 |
| 全链色相 | 所有成员两两检查，不能只有相邻色相差合格却逐级漂移 |

ΔE76 的位置门不能替代 ΔE00 的等级分离门。不能在看到结果后将 5° 改成 5.1°，或在 5/10 级阶段降低门槛。新数值必须新版本、说明理由，并对原始数据并列重算；保留旧失败结果。

### 8.2 后续生命周期的预定人工审查判据

另用 `MF1750_LIFECYCLE_REVIEW_V1_20260912`；这是本计划冻结的**实验人工审查合同**，数值整理自旧重复/HOLD 门并加逐 ROI/时间点检查。尚无自动验收器，不能声称软件已执行这些门。

| 测试 | 预定审查规则 |
|---|---|
| 局部 HOLD/邻域干扰 | 目标保护 ROI 与对照 ROI 均有前后证据；每个保护 ROI abs(ΔL*)≤2、ΔE76≤5、彩色色相漂移≤5°；完整链仍须满足8.1；ΔE00只另列报告，不拿其值与ΔE76门比较 |
| 独立 fresh 重建 | discovery 之后再作3条独立 fresh-white→SOURCE→MIDDLE→TARGET 链，每条新 run_id/合法一次性identity；方向/等级顺序100%一致；同配方对应 ROI 跨链 abs(ΔL*)≤2、ΔE76≤4、色相差≤5°，各条链独立通过8.1 |
| 静置保持 | T0定义为合同正常终态/settle后首次有效图像；T0及目标5/60/600秒都实际记录采集时刻及偏差，每组N≥10；每ROI对T0 abs(ΔL*)≤2、ΔE76≤5、色相漂移≤5°，等级链不塌缩；缺时间点或超出预先在批次卡注明的窗口为HOLD，不补造样本 |
| 双controller匹配 | 两侧先各自通过全部阶段；同recipe/rank对应四位置 abs(ΔL*)≤3、ΔE76≤5、色相差≤5°；每对都检查，不以左右合计代替 |

光源/曝光/温度条件不一致时，先判证据不可比，不强行归因为颗粒瞬态。neutral 单独需要中性容差/测量噪声判据，当前未冻结，不能用本彩色色相门给16个 neutral槽资格。

## 9. 后续实验和升级条件

**验收顺序固定：** 身份/协议 → 图像有效 → 四位置端点差异 → 同色相明度候选 → HOLD → 三条独立 fresh 重建 → 保持 → 两 controller 匹配 → 资格人工复核。只读静置观察可以提前做，但不能跳过前置来授予资格。

- HOLD：须有专门封印的邻域动作、保护ROI和对照，不用全FF、code7、PTLW或relay OFF冒充已知HOLD。当前9项语义证明缺失时，不生成猜测LUT；可继续分析已有完整profile实测，但不能称已证明零驱动。
- 三条fresh链中每个 white/source/middle/target 都是独立可见动作，分别记账和停审。旧白恢复的一次性 NVS/claim 不允许循环使用；后续恢复必须另建合法 successor 合同，保留全部消费状态。
- retention 期间 0 display refresh；“再次写同样target”是新驱动，不能算静置保持。
- 白恢复消除候选是正常行为，不能单独判瞬态。只有静置漂移、邻域干扰或 fresh 重建失败等实际证据才可支持不稳定结论；缺证据不是失败测量。
- stable-3 的三个等级全部完成生命周期后才扩5；5级完成后才扩10。12 hue families和2 tracks需要按实测定义，不把T3/T7名字直接等同于两个合格track。
- qualified统计按逻辑槽去重；明确记录 lab space 和适用环境。自动筛选输出始终不能直接增数；未完成两侧和生命周期时仍为0。

### 9.1 结果分支与下一批选择

| 当前结果 | 下一项具体工作 | 能否直接继续刷新 |
|---|---|---|
| W0 协议异常或全屏白场异常 | 封存异常；复核运行身份、BUSY 和已消费状态，再单独设计适用 successor | 不能重跑 W0 或直接进入 LH1 |
| 图像不可比、覆盖/噪声样本不足 | 补采当前静置态并保留机位/曝光变化；不能补回已不存在的前态 | 可做已授权只读采集；依赖前态的链需另批重建 |
| 四位置差异方向不一致 | 用既有四位置数据排查位置、透视/ROI、光照和 controller 映射；修改几何需新合同 | 不能把中位数差异直接算等级 |
| 有可重复端点差异，但色相门失败 | 记录色彩端点候选，分析下一组 source/middle 历史配方 | 不能放宽色相门或称同色相明度 |
| 不足3个同色相等级 | 保留2级或单端点诊断；离线选择信息量更高的历史配方，或按第10节补足单变量依据 | 新动作须新批次；不能用照片/重复次数凑3 |
| 3级筛选通过 | 封印该链专用 HOLD、独立 fresh successor 与保持采集方案 | 此时 qualified 仍为0；没有这些实现时继续离线准备 |
| HOLD/fresh/保持测得漂移或重建失败 | 按实际失败类型记录；分析邻域干扰、温度/光照或历史依赖，保留失败配方 | 不用白恢复清除结果推断瞬态；不立即加驱动量重试 |
| 两侧各自稳定但匹配失败 | 分别保留侧内候选，研究两侧对应配方的光学匹配 | 不把两侧混合平均后授予统一槽位 |
| stable-3或stable-5全链通过 | 新批次增加不同配方，保持原阈值，重做扩展链的全对检查及生命周期 | 只有已审查的原槽可保留资格，新成员不能自动继承 |

## 10. 暂不进入现场的探索分支

这些是离线研究清单，不是当前action allowlist，也没有预授权参数值：

1. 固定完整LUT的PLL单变量：先解释最后生效写入、PWR模式和级联时钟，确认面板适用的有界组合。43/50Hz来自两个不同完整tuple，互换本身是新实验；不能直接扫描25…100Hz。
2. 同target累计驱动次数：必须单独定义有限动作数/恢复方案并重新封印，不能把建议的1/2/4/7/10当已批准序列；次数不等于等级。
3. source电压、VCOM、末帧：先建立电气实测和安全范围，再选择单变量；不同时改电压+频率+LUT以求“更亮”。
4. R20/R21内部phase编辑、未知HOLD码、专利参数移植、OTP编程、保留指令扫描：当前禁止。论文/专利/开源工程只用于假设和结构对照；取得官方支持不是唯一研究出口。

## 11. 证据目录、判决与停止

每批独立目录，建议结构：

可复制的空白记录模板：[MF1750_LIGHTNESS_BATCH_RECORD_TEMPLATE_2026-09-12.json](MF1750_LIGHTNESS_BATCH_RECORD_TEMPLATE_2026-09-12.json)。它没有实测值和现场授权；所有未知项保留 null，不能把模板当已通过 evidence。

该模板是整批证据索引，不是 `analyze` 的直接输入。分析数据先由 `python -m tools.mf1750_lightness_test create --output-dir <全新离线目录>` 生成对应 ROI 的空白 observations，再逐项填入已封存测量。`requested_levels` 明确取3/5/10，W0 不适用；与照片数、fresh 次数分开。分析数据顶层 `threshold_version/data_origin/lab_space`、`identity`、`camera`、`evidence_files` 及每 ROI 的 `lab/noise/quality_pass/measurement_evidence_sha256` 均按生成格式填写；`FIELD_DERIVED` 只用于实际真屏派生数据。批次卡的 `analysis_dataset.path/sha256` 绑定此文件，不能将 null 模板或 TEST_FIXTURE 当实测。SOURCE/MIDDLE/TARGET 每步分别记录 ordinal、role、middle_state 与 prior action/review；三步不能挤成一条无法追溯的 action。

```text
run_id/
  batch-card.json             # 当前计划/阈值/动作/最大计数/授权原文引用
  identity/                  # COM、MAC/IP、camera、firmware、boot、source hashes
  electrical/                # relay command/query 与外部测量分别保存
  action-NN/                 # ARM/EXECUTE/status/report 原始body和时间线
  capture/                   # 原JPEG/视频、sidecar、相机能力、ROI、光源温度
  observations/              # 操作者原文、视觉判断，不改写成机器测量
  analysis/                  # Lab空间、ΔE76/00各字段、噪声、四位置与双侧结果
  review.json                # PASS/HOLD_FOR_EVIDENCE/FAIL_STOP、下一唯一动作
  SHA256SUMS.json             # 原始与派生文件分别绑定；封存后只追加新版本
```

每条结果至少绑定：panel、CS1/CS2、controller revision、boot、profile及其范围、source/target、action/firmware/frame hash、test_phase、waveform_phase=OPAQUE、温度、相机请求/读回、ROI、run_id。未知为null并给原因；不从上一轮自动补齐。

| 判决 | 含义与下一步 |
|---|---|
| PASS | 只表示明确写出的本层检查通过；例如编译PASS不等于协议PASS，协议PASS不等于光学或资格PASS |
| HOLD_FOR_EVIDENCE | 缺电测、整屏图、温度、同态样本、后续阶段或可比性；补证前不执行依赖动作，不伪填 |
| FAIL_STOP | 协议/身份异常、hash不匹配、重放、busy超时/未知、明确错误写序或真屏异常；停止mutation并保存原始证据 |

协议异常时不重发ARM/EXECUTE，不在BUSY中盲目reset/刷写/刷白。是否能安全断开relay依据已核对的电气/紧急处置条件，不能用临时“恢复”掩盖未知状态。正常收尾只执行批次卡列明的动作。

每轮报告实际 GET/POST、ARM/EXECUTE、driver/visible refresh、relay查询/切换、flash/reset、照片数；给原始路径、判决、qualified及依据、下一唯一动作/前提/授权状态。最后更新STATUS顶部和短交接，不改旧结论。

## 12. 防偏离检查表与当前下一步

下一执行者必须逐项回答“是”后才触发对应mutation：

- 正在执行STATUS指定的唯一下一动作，而非按历史目录挑一个runner？
- 本次action与计划、实际固件及一次性identity匹配，且旧NVS/claim未被绕过？
- source是实际证据支持的当前状态；若进入LH1，修复版white与LH1源合同已正确重绑定？
- 相机是指定VID/PID并实际整屏覆盖，电气证据来自测量而非命令确认？
- 若刷过app，诊断确实来自刷写后的运行固件同boot？
- J2-OFF BUSY=0诊断与ON后BUSY=1执行门分别满足？
- 计数只允许本次1/1/1/1，结束后有明确停止点？
- 内部phase仍OPAQUE，阈值/ROI未因结果临时调整，资格没有提前增加？

当前 LH4 的编译/真实JSON/host identity 离线审计已完成；下一项是封印绑定 LH4 的完整 white 现场 runner，保留原消费边界。并行补齐整屏相机与外部电测，之后才可按 W0 一次恢复并停住验白。没有这些证据，不执行新的 P2 或 LH1，不开始 PLL/剂量/电压试验。
