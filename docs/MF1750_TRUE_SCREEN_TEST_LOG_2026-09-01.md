# MF1750 真屏测试日志（2026-09-01）

最后更新：`2026-09-01 10:55 +08:00`

> 本页只记录 2026-09-01 已发生并有文件证据或操作者原话支持的事实。相机结论均为
> camera-relative / human-primary 筛查，不是绝对颜色标定，也不把当前照片提升为稳定新色资格。
> 继电器回执只能证明命令与查询状态，不能证明继电器下游的实际电压。

## 1. 当日结论摘要

- T4 V4 被主机 runner 在任何设备网络请求、claim、ARM、EXECUTE 或 driver 调用之前拒绝；
  后续只读 reconciliation 将其封存为 `NOT_EXECUTED`。V4 永久禁止重试，W9 干净白屏状态在
  该次拒绝后仍有效。
- fresh T4 V5 使用与 V4 相同的目标 payload，修正首轮 fresh report 校验后完成一次且仅一次
  真屏 action：`COMPLETE / result=true / 1 driver / 1 visible refresh`，driver 总时长
  `46.632 s`。没有 retry、recovery 或 autochain。
- V5 action 后继电器已执行保护性 OFF 并独立查询通过。当前屏幕按双稳态保留 V5 atlas。
- 48MP 相机取得一张 exact `VID_32E4:PID_4801` retained JPEG。照片中左右各 `4×8` 色块均
  可见；左侧以黄绿／橄榄、蓝绿和深色为主，右侧以红／粉、橙棕、蓝及深色为主，左右色彩
  结构差异明显。用户随后确认：`没错，你看的是对的。继续推进`。
- W11 已在 `J2 OFF` 下完成 app-only 写入、exact IPv4/MAC 绑定和 fresh diagnostic；
  继电器 ON 受权后，唯一 factory-OTP white action 以 `COMPLETE / 1 driver /
  1 visible refresh` 终止，driver 总时长 `35.023 s`，随后已保护性 OFF。
- W11 后续已由唯一项目相机 `48MP USB Camera / VID_32E4:PID_4801` 完成全屏留存；严格
  camera-visible review 未见 V5 `4×8` 彩块、明显色斑、横竖条或中心接缝异常。该结论只证明
  本帧的可见干净白屏 containment，不证明绝对白点、精密空间均匀度或不存在微弱残留。
- 后续功能主线转向稳定色的明度／灰阶机制；更多色相枚举与重复可靠性长测后置。
- 明度首选分支 `STABLE_CODE0_LUMA_LATIN_V3` 已消除离线审计阻断，专项
  `26 passed / 93.32 s`、Ruff、主／白 dry-validation、clean rebuild 和独立复审均 PASS。
- V3 已在同一 boot `46ae55ad22b2a55e` 完成 L1→L2→L3→L4：每个 action 均为
  `COMPLETE / result=true / 1 driver / 1 visible refresh`，无 retry/recovery/autochain。
  L4 为与 L3 完全相同的 active/code0 target；同曝光 `-4` 复核显示 CS2 历史明度跨度从
  `7.059 L*` 收敛到 `2.157 L*`，故 identical-target repeat 稳定门 FAIL。
- V3 独立 factory-OTP white successor 随后唯一执行 COMPLETE；48MP 白屏 review 在
  “无明显旧色块／色斑／粗大条纹／中心接缝”范围 PASS。继电器最后已命令并独立查询 OFF，
  面板保留白场；回执没有下游电压反馈，故 `electrical_state_proven=false`。
- 当前仍为 `0` 个 qualified 新色、`0` 个 qualified 灰阶和 `0` 个 qualified 明度层级。
  下一功能门改为 fresh-bound 位置平衡明度机制；其候选必须经局部 HOLD 和从独立白锚重新构色，
  不再用会坍缩历史状态的原位 identical-target repeat 作为历史配方资格门。

## 2. T4 V4：主机拒绝与只读封存

V4 固定身份：

| 项目 | 值 |
|---|---|
| contract | `3a1c254d2beb0f06deb43781b1e3d9c5e94795c3a1354756c4b1a3ed12824150` |
| descriptor | `3c1ec52d3bc09ac0fde195d8b467e1b844357c3d5bdbc6ce0ea685962242d6d1` |
| action | `c778bc7ccd90fdb2f93abef2aef10ba05d48603bfe790e6f9b6b97dd34b9f154` |
| BIN | `806416 bytes / 2b7ed3e0b1da3cd44bdd89450857911ea62dfdcc6d54a9d4dc94d77005f17a42` |
| ELF | `13304784 bytes / 0c04ef30f5b7b41336040c9adc6a5c329433875696c49f4c75946f1ca0b9264d` |

封存证据：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V4/action-01-host-runner-rejection-reconciled.json`
- bytes / file SHA-256 / canonical SHA-256：
  `28704 / 650576fa5506f6afe039296262c8bd76e15f73fb3d54aa4675507f36808114bb /
  f4ed665890c9aed8ce8b70b56c8bffb97de4bd47a22ab2c6c8be1fd7141c2049`
- 终态：`outcome=not_executed_reconciled_read_only`、`terminal_state=NOT_EXECUTED`、
  `v4_action_must_not_be_retried=true`。
- 原 host run 在首个网络请求前拒绝；action result 与永久 claim 在拒绝前后均不存在。只读
  reconciliation 后来使用 `2 GET / 0 POST` 读取同一 boot 的状态，这两次 GET 不是 V4 action
  的 ARM／EXECUTE 流程。
- 设备计数保持 `0 ARM / 0 EXECUTE / 0 mutation / 0 driver / 0 visible refresh`，状态仍为
  `READY`，boot nonce=`d0c12cfdbb56810a`。
- 证据明确记录 `w9_clean_white_remains_valid=true`。拒绝的具体 host exception 文本没有被
  该 reconciliation 证据作密码学声明，因此本页不补写推测原因。

## 3. T4 V5：固件、身份和一次真屏 COMPLETE

V5 固定身份与构建产物：

| 项目 | 值 |
|---|---|
| stage | `t4-active-header-ca-r20-swap-confirmation-successor-v5` |
| contract | `60a66dfecc7d221e2c91fc98476d77b7c95b5956d59222b2145352e08a82fe6e` |
| descriptor | `143846332e6a83514330e43c4866efa7c05e5fb9d0b648ec600699704db331d0` |
| action | `218107d78d9e21d05b5be0b3ea59e4403313d18ea2c062a0fbf90155915f9676` |
| BIN | `807712 bytes / 6302ae6c2ea234ea842dc281611b383cf746213d9d8790c7d8933be187b00672` |
| ELF | `13305072 bytes / 4c069dc14105a0f28093f2fa15288ca820dc0ff10b754cc87dfa7a3b7b970808` |
| frame | `1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23` |
| profile | `LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535` |

V5 绑定 `global_header=active`；CS1 使用 commented 535-byte R20 prefix，CS2 使用 active
535-byte R20 prefix，二者共用相同 R21。V4 action 已加入 non-reusable tombstone，V5 authority
由 W9 白屏、T4 V3 FAULT 与 V4 host-rejection reconciliation 共同约束。

真屏 action 证据：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V5/action-01-position-balanced-atlas.json`
- bytes / file SHA-256 / canonical SHA-256：
  `62064 / e905857cd5a079d9def483d03a1f1a509582b41cfe8cdc08c460d416b9556475 /
  c0aca35f60012f1cca8aca4d3d7a6c440a724f44a3b848fa93941df8a041f5ed`
- boot nonce=`56c6ddc11cfcac01`；终态为 `complete_pass / COMPLETE / result=true /
  campaign_complete=true`。
- 精确计数为 `5 GET + 1 ARM POST + 1 EXECUTE POST`、`1 driver`、`1 visible refresh`；
  `driver_call_count_for_action=1`、`total_driver_call_count=1`。
- driver `valid=true / sequence_ok=true / wait_timeout=false / failure_stage=none /
  failure_code=0`；PON/DRF/POF=`260 / 33931 / 150 ms`，总时长=`46632 ms`。
- `no_retry=true / no_recovery=true / no_autochain=true`。永久 claim 已在首次 mutation 前创建，
  V5 action 已消费，不得重放。

## 4. V5 action 后保护性 OFF

- 回执：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V5/relay-post-action-protective-off.json`
- bytes / file SHA-256 / canonical SHA-256：
  `1798 / 88323cc0231283fd0e14ccb5edd13ffbfff6dae0d9cef1203b3a7a9a65235ad8 /
  67b426bad610c366a4d30cb38b0cf7b9042645bfc31988ae753a052ba5a1a0aa`
- COM14/channel1、`COM1-NO1`：`commanded_state=OFF / target_state=OFF /
  off_gate_passed=true / contact_switch_performed=true`；有一次独立查询，无 retry/recovery。
- `electrical_state_proven=false`：该回执没有负载侧电压或电流反馈，不能据此声称物理零电压。

## 5. 48MP retained 照片与人工观察

相机只使用项目绑定的 `48MP USB Camera / VID_32E4:PID_4801`，没有使用双目
`VID_1BCF:PID_0B15`。本帧采用 DirectShow、MJPG `4000×3000 @ 15 fps`、AF=0、focus=79、
AE=0.25、exposure=-6、AWB=0、WB=4600，warmup 8 帧；全部设置写入返回成功，前后 effective
readback 稳定，read failures=0。

| 工件 | 路径 | bytes | SHA-256 |
|---|---|---:|---|
| 原图 | `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V5/retained-camera-atlas-v5-attempt-01.jpg` | 751132 | `45e8777f9b78e65cafa6947a816a51f1f01e54eb4d7a6a0d3b717a73a0f864f5` |
| capture sidecar | `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V5/retained-camera-atlas-v5-attempt-01.capture.json` | 5488 | `6ae97fadc4bf5230841834fa2da9d776801142211c21cfbdc3d94ccd81821c89` |

sidecar canonical SHA-256=`01703962a5cd132d8b008e5d10cd471a828a0f0fbd93cb4f10ec621cd3a591a0`，
capture binding=`locked_retained_retrospective`，scope=`partial_panel`，自动 verdict=`INCONCLUSIVE`。
因此照片只证明该时刻拍到的 retained 外观，不独立证明与历史 action 的物理连续性，也不能用于
绝对色彩资格认定。

本张原图的有限观察：

- 左右两个 controller 区域各有 `4×8` 色块，均在画面中可见。
- 左侧整体偏黄绿／橄榄、蓝绿和深色；右侧整体偏红／粉、橙棕、蓝和深色，左右差异明显。
- 这与 V5 的 CS1-commented / CS2-active 非对称 profile 方向相容，但仅凭本张照片不能判定
  “颜色随 profile 还是随物理侧”，也不能宣布新稳定颜色数量。
- 向用户描述上述 `左右各4×8` 及左右色族差异，并询问现场是否一致、右侧橙／粉是否稳定后，
  用户原话确认：`没错，你看的是对的。继续推进`。该确认不外推到未询问的边缘质量、同码副本
  一致性或绝对色名。
- 用户随后明确授权后续由 48MP 相机进行判断与按既定门控继续操作；该授权不放宽一次性
  action、J2/GND、no-retry 或 fail-closed 约束。

## 6. W11 白恢复：唯一 action COMPLETE

W11 固定身份和构建产物：

| 项目 | 值 |
|---|---|
| contract | `52aa5c78ba61abef70327a3e86df368668857e8d99e67c59c406371f757ba85f` |
| descriptor | `076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411` |
| action | `80a9fd85ff4b93ce365b699f1caa8d7835cbeeeaf738194f70cccc0f7500b595` |
| BIN | `787504 bytes / e10d4ba6063e885ca4ce1669b343ba9ece6451dc24cbdefafd16732ffa140f3e` |
| ELF | `13215012 bytes / 79969668905ef8ad15f809436cb573fd847d9dc6436deff40be138e36fba8273` |

写入与网络绑定：

- `J2 OFF` 下 app-only `0x10000` 写入、verify 与单次 hard reset PASS：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/app-only-single-boot-flash.json`
  （`6721 bytes / af1e0ef6f5b478c29bd9318e2aebf7c533dc5b01b341c7a79d9e6877049f8d66`）。
- exact IPv4/MAC 绑定 PASS：单一候选 `192.168.1.11 ↔ A4-CB-8F-D9-FC-D4`，只发一次 ICMP，
  `0 HTTP / 0 mutation / 0 visible refresh`：
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/exact-ipv4-mac-binding.json`
  （`3450 bytes / 63bf332d2c79a97eedd183dc6d42cae4fcc975e481a2920d975680d56e1b5f17`）。

source validator 事件按时间记录如下：

1. W11 首次准备进入 source terminal gate 时被 fail-closed 阻断，exact error 为
   `T4 V5 terminal lineage or one-driver semantics differ`。阻断发生在 W11 device diagnostic、
   ARM 或 EXECUTE 之前，没有产生 W11 claim、driver 或可见刷新。
2. 离线修正 V5 terminal validator 后，固定 V5 COMPLETE 文件、永久 claim、firmware、完整
   transcript、boot/nonce/header 以及 `1 driver / 1 visible refresh` 语义的深重放已经 PASS；
   W11 `_validate_source_terminal_evidence()` 当前返回 `verified=true /
   source_terminal_state=COMPLETE / source_success_claimed=true`。
3. 修正后才进入下列 fresh diagnostic 和唯一真屏 action；上述首次阻断没有被
   追认为执行成功。

`J2 OFF` diagnostic：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/j2-off-diagnostic.json`
- bytes / file SHA-256 / canonical SHA-256：
  `15475 / d6166e9204ec6a141809691e69c1f6b0e26a86f811bc4d3e50743ec837aaf7fe /
  e1c5d3ba9a69ccbb754908d8bc687ca26e73111509934f29c7b51e530af9ac27`
- boot nonce=`f0af01ca643a826a`；`fresh_nvs=true`，终态 `NOT_EXECUTED`，精确计数为
  `4 GET / 0 POST / 0 claim / 0 driver / 0 visible refresh`。

继电器 ON 授权回执：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/relay-pre-action-on.json`
- bytes / file SHA-256 / canonical SHA-256：
  `1885 / 84e3c78f1d22129790627a1533a6fbe4fd272d2ed38b6fdc761dde557b12dbe9 /
  03523d675d62d4c99e37d6af23793d9c01e6800b8547fd321a623817350c996f`
- COM14/channel1、`COM1-NO1`：`commanded_state=ON / target_state=ON /
  target_gate_passed=true / contact_switch_performed=true`。授权 ID 为
  `USER_FULL_CAMERA_AND_OPERATION_AUTHORIZATION_20260901`。回执同样不证明下游实测电压。

W11 唯一 factory-OTP white action：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/action-01-factory-otp-white.json`
- bytes / file SHA-256 / canonical SHA-256：
  `30937 / e48ee37c34e6984f15656267e8d915a8552b210f8dd465610ca1c438ee79c3b0 /
  42271e6b8d705366be1decf070b5a9d0fb1515f5b9136ebc1e33a79a33401a11`
- 与 diagnostic 同 boot nonce=`f0af01ca643a826a`；终态为 `complete_pass / COMPLETE /
  result=true / campaign_complete=true`。
- 精确计数为 `5 GET + 1 ARM POST + 1 EXECUTE POST`、`1 driver`、`1 visible refresh`；
  `driver_call_count_for_action=1`、`total_driver_call_count=1`。
- driver `valid=true / sequence_ok=true / wait_timeout=false / failure_stage=none /
  failure_code=0`；PON/DRF/POF/post-PSR=`180 / 22530 / 140 / 5 ms`，总时长=`35023 ms`。
- `no_retry=true / no_recovery=true / no_autochain=true`。永久 claim 在首次 mutation 前创建，
  W11 action 已消费，不得重放。

action 后保护性 OFF：

- 文件：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/relay-post-action-protective-off.json`
- bytes / file SHA-256 / canonical SHA-256：
  `1798 / d5ef48f419ef7977d4d30c52033ba6fb06820c227d625321f9c8bedbe437e486 /
  bdf099a39053af84deb8aca7d842cb83b8373da151ea3271b242b3039fccc09e`
- `commanded_state=OFF / target_state=OFF / off_gate_passed=true /
  contact_switch_performed=true`；无 retry/recovery。`electrical_state_proven=false`，因此仍不外推
  为下游物理零电压。

post-white 视觉状态：

- generic capture-marker validator 初次按设计 fail-closed；随后仅增加与 W11 完整冻结身份逐字段
  匹配的 allowlist tuple，未放宽通用 marker 规则。相关相机工具回归为 `91 passed`，Ruff 与
  `py_compile` 均通过。
- JPEG：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/post-white-retained-camera-attempt-01.jpg`
  （`638038 bytes`，SHA-256
  `0dc805e0014d0092e7d032b467eccd2d11490cec97ea6b280594fa25550d7816`）。
- capture sidecar：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/post-white-retained-camera-attempt-01.capture.json`
  （canonical SHA-256
  `b47580dc1aaef3d824205ed3a34c3ebdd6f02dd2c92edd8f67374f4ed57110ac`）。
- 严格目视审查：`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1/post-white-retained-camera-attempt-01.camera-visible-clean-white-review.json`
  （`6352 bytes`；file SHA-256
  `c88d22d8ab241daeccb28e01a722c166fdc07bef50f7c55024ba57204008d9a9`；canonical SHA-256
  `617201f980461d76864be7199f50c5878747ccf777349286ffbe78699da34d7d`）。
- review outcome 为
  `PASS_NO_OBVIOUS_V5_RESIDUAL_OR_GROSS_SCREEN_DEFECT_IN_THIS_RETAINED_FRAME`：全屏活动区可见，
  未见 V5 彩块、明显色块／色斑、明显横竖条或明显中心接缝异常。
- `qualified_colour_count=0`；相机结论不提升为绝对白点、精密均匀度、弱低对比残留排除或
  qualified white/gray。action、照片、sidecar 和 relay-OFF 的文件哈希、字节数及 canonical
  integrity 均已重新核对匹配。

## 7. 后续方向调整：稳定色明度与灰阶优先

- 下一条功能主线聚焦“已稳定色相的明度层级”与“中性灰阶机制”，不再优先扩展更多色相。
- 先用最小灰阶机制鉴别图区分真实稳定阶调、历史态瞬态与空间混色；再对一个已稳定的
  基色执行明度梯度图。
- 更多色相枚举、60 s／10 min／长时间重复与批量可靠性统计后置；这些不影响先完成
  明度／灰阶的机制性判定。
- 功能路径按以下顺序扩展：稳定基色 → 位置平衡的灰阶／明度机制鉴别 → identical-target
  重复确认稳定性 → 局部 HOLD 跨 LUT 共存 → 可用调色板建模 → 静态照片逐像素映射。全过程
  禁止以空间抖动替代单像素颜色；左右控制器分别评价，不把左右差异误记为明度层级。
- 机器可读功能框架已写入 `docs/MF1750_FUNCTION_PATH_FRAMEWORK_2026-09-01.json`，并由
  `tests/test_mf1750_function_path_framework.py` 固定上述优先级、资格计数不膨胀、单像素约束和
  fail-closed 执行门，并锁定本项目唯一相机为 `VID_32E4:PID_4801`。
- 已新增 `host/static_photo/lightness_screen.py` 作为灰阶／明度的通用证据筛选层：它只在同一
  controller、同一 LUT profile、同一 final transport code 内比较配方，要求足够空间副本、
  单像素纯色、干净边界、位置重复稳定、L* 分离且色相漂移受限。CS1/CS2 或不同 profile 永不
  混合；无 identical-target repeat 时只能保留 coarse candidate，自动 qualified 计数恒为 0。
- 已新增 `host/static_photo/multi_lut_hold_schedule.py` 作为照片路径的离线调度骨架：它按
  controller-specific recipe 和 LUT profile 生成 source/middle/target/repeat 帧，其他像素只能
  使用已有资格的 HOLD code；候选色、控制器错配、未验证 HOLD、缺失 profile 或不能保持先前
  profile 时一律拒绝。它不访问硬件，也不授予 live authorization。框架、目录和调度器当前
  联合回归为 `30 passed`，Ruff 通过。
- 两套明度 successor 都从同一份 W11 retained-white 事实分叉，故是备选首项而不是可直接
  串行的两步。任一测试刷新后，另一套若要继续，必须先完成前一套的独立 factory-OTP white
  containment，再把该 fresh 白恢复结果绑定为新的当前白锚；禁止继续仅引用已经被后续刷新
  破坏的旧 W11 现场状态。
- 按用户“稳定颜色后先查灰度／明亮度、更多色相后置”的最新优先级，首选分支改为
  `STABLE_CODE0_LUMA_LATIN_V3`：固定一个稳定 target code，只改变位置平衡的 middle history，
  比通用灰阶 V2 更直接隔离同色相明度机制。V2 保留为 V3 阴性后的备选；两者仍不得从同一份
  W11 白锚直接串行。
- 若历史配方机制阴性，下一层不是回到大规模色相枚举，而是依次考虑：命中后的小范围
  target-repeat 数量阶梯、已知兼容 profile 的 controller-specific 端点明度、经离线极性／fixture
  审核的有界 R20 phase family。波形中断属于高风险后置项；未知寄存器／LUT 命令穷举明确禁止。

## 8. 明度 successor 离线冻结／审计状态

`LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2` 已完成离线冻结，未访问硬件、相机、网络或继电器。
独立专项测试为 `9 passed`，targeted Ruff PASS，主程序和独立白恢复的 `dry-validate` 均 PASS；
owner clean rebuild 与独立复核均得到相同产物：

| V2 产物 | bytes | SHA-256 |
|---|---:|---|
| 主 BIN | 800928 | `decacb3a1b52df9261120e51b6ee68f1632729ac1c51683ecdca067f1dfd5248` |
| 主 ELF | 13297804 | `91dd3d82a9fee8083896eddf12877dd54c9020987c10a5b48af96f71205c6677` |
| 白恢复 BIN | 787440 | `70fc1512945549d3c1321398b846a7d15389bb5dc4661f0a65965b113edca1d7` |
| 白恢复 ELF | 13214356 | `6b750b7ebaa3c19a31912c56576f09be4903101f8f60047f42f8606fa1d8570e` |

V2 主 contract=`b9baafc7b0e4966a23eb1189372e36d690e8df84d8e17f4c8cbc3536be46f019`；
白恢复 contract/descriptor/action=
`330a2e8a685ab399a032233e3a976dd1147e86ce2552574bc8a3a47e0f7fa495 /`
`d51e6302c5336cee29e50be52b344e60334d243ee5e2fbd9bcfdcb82d650ccf5 /`
`e7127fe1c2c3e871578bc17f50c17f4db4d6161e54df0c94c2820d0ba20e71e3`。
G1→G2→G3 为三个显式独立 action；G4 是同目标重复，默认不运行且不能 autochain。V2 具备
live-ready 的离线合同，但它会消费当前 W11 白锚；由于固定稳定颜色明度的 V3 更符合当前首选
目标，暂不执行 V2。

`STABLE_CODE0_LUMA_LATIN_V3` 在初次独立审计中发现的两个 runner 阻断已经修复：

1. W11 无外部刷新源门只用于 diagnostic/L1；L2–L4 现在只接受同 boot、固定
   prior-COMPLETE 链，并禁止外部 refresh/reset/flash；
2. 白恢复 fallback diagnostic 已补齐 firmware/ELF/action/outcome/fresh-NVS/
   artifact-before-network/O_EXCL/no-retry，并对四个 GET 的 method/endpoint/status 做深验和
   重算 canonical 篡改负测。

修复后独立专项为 `26 passed / 93.32 s`，targeted Ruff PASS，主程序与独立白恢复
`dry-validate` 均 PASS，owner clean rebuild 和独立复核的产物一致：

| V3 产物 | bytes | SHA-256 |
|---|---:|---|
| 主 BIN | 799792 | `16f63947918d244e27edd0a7f3d0c3f4ff895fa02cbc26c31461c9d91ea7b737` |
| 主 ELF | 13286636 | `c3e763105daeec2bc610daef2aad7e4b8c138d3c95cf414fa343aa067adcdcdb` |
| 白恢复 BIN | 787248 | `804aadd5a9b82a02a01bc0431750790666d2ba56352d43b3add7f89245dff907` |
| 白恢复 ELF | 13214376 | `2c70314c8b54f012845370bddc56e5bcf8ef1f808a6854776f3105868108630a` |

主 contract=`472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302`；
L1/L2/L3/L4 action 依次为
`83b0e955ff0d88076737e8e13946602c696829bcef159691ce4ef074abfaf62e /`
`c7606fc0d16eed0e7dc9d211441da551579a168d85bcba336c32e724396c2ad8 /`
`185d103527cebf9bd36153ca9d0ba4eb6152c57d39dbf177ecd5a24d6309d4a5 /`
`9ea8538c301c53651ee0270c884caf34ce8d5592ba7ee3e6d4ba2f5a0e7420ec`。白恢复
contract/descriptor/action=
`787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377 /`
`8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0 /`
`7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f`。L4 为人工显式可选
identical-target repeat，永不 autochain。本节的离线状态已由下节真屏证据继续。

## 9. V3 L1→L2→L3 真屏证据与 48MP L3 留存帧

### 9.1 J2-OFF 写入、绑定与 diagnostic

- relay 预查在 COM14/channel1 得到 `commanded_state=OFF / off_gate_passed=true`；
  `.test-output/hardware/MF1750_STABLE_CODE0_LUMA_LATIN_20260901_V3/relay-pre-flash-off-query.json`
  的 bytes/file/canonical SHA-256=`1244 /
  34ceea8c036eb49e4a19d477bda772c3a3c979b84aa65ed5a8d92839d11068a8 /
  127dab4a6b64aba65d9559b554d7e6e6794b3f576095eef21192bdeafabdec0b`。
- J2 OFF 下只写 COM8 application `0x10000`，write hash 与独立 verify 均 PASS，不写
  bootloader/partition/NVS；verify 后仅一次 hard reset。flash evidence bytes/file/canonical
  SHA-256=`6760 / 76678de5ef6fb7900f555a9af9152e77094c8bdbd1135a961dc92ac9c7da013f /
  c90165d76223bd343e3dbe42f2b8e123d14176042696491d2e98a9a6a6e933d0`。
- exact one-shot IPv4/MAC 绑定为 `192.168.1.11 ↔ A4-CB-8F-D9-FC-D4`；只对该单一候选
  发一次 ICMP，`0 HTTP / 0 mutation / 0 visible refresh`。binding evidence
  bytes/file/canonical SHA-256=`3391 /
  78d70fa38a8bb7524c7238f5aba5ec30226c65881e2ef6491ffedbcb8c1fd30d /
  4eb9634322a7a8655d4b1c490bbf1fd174b30563ea085d027f3d47d19714e207`。
- J2-OFF diagnostic 在 boot nonce=`46ae55ad22b2a55e` 得到 fresh NVS、`READY / next=1`、
  `4 GET / 0 POST / 0 driver / 0 visible refresh`，并绑定 W11 COMPLETE 与其 clean-white camera
  review。evidence bytes/file/canonical SHA-256=`26489 /
  4d373b935c78b7141b3416391ca4121a0dd13031c4f5fd2d7f1849af93d208f4 /
  f9dc8a089e1beaa39ef7286de8e3bdfc6d4aa347a74c04d6b17b548a9d94ec51`。
- 随后精确绑定 relay 回执将 COM14/channel1 命令为 `ON`，授权 ID=
  `USER_FULL_CAMERA_AND_OPERATION_AUTHORIZATION_20260901`；bytes/file/canonical SHA-256=
  `1890 / 464aaf0a602d435bad301d4050855eb336dcf91dafe6bd3d444805ecef76bcbe /
  042b147dcb8e8926b35b0a88f28a301f1851656e9364257299f1ee44b2e41509`。回执仍为
  `electrical_state_proven=false`，只证明命令和独立查询结果。

### 9.2 同 boot 的三个显式 action

| ordinal | role | action | 结果 | driver PON/DRF/POF/total (ms) | action file/canonical SHA-256 |
|---:|---|---|---|---|---|
| 1 | `L1_FIXED_ACTIVE_SOURCE_CODE7` | `83b0e955ff0d88076737e8e13946602c696829bcef159691ce4ef074abfaf62e` | `COMPLETE`, next=2 | `260/33940/151/46623` | `49fc4d98421c71dc19eb2b19174b5280e807e9aeb8abf4161bc1d3ddd20d5a7e / afded95e8a710a7de5963f35c664c0b2ea9fd2fa3ef45f8a4ca713d18d00f53f` |
| 2 | `L2_COMMENTED_MIDDLE_LATIN_C0_C7` | `c7606fc0d16eed0e7dc9d211441da551579a168d85bcba336c32e724396c2ad8` | `COMPLETE`, next=3 | `260/29220/151/41901` | `9910de325634c01a971c5cdb59eabd0ec92dc85a05d87d7997291b491795d317 / f9e51b34145db8eb29fce0a58881d5612e8898c4703f8d00f3b5aefd23e617ed` |
| 3 | `L3_FIXED_ACTIVE_TARGET_CODE0` | `185d103527cebf9bd36153ca9d0ba4eb6152c57d39dbf177ecd5a24d6309d4a5` | `COMPLETE`, next=4 | `260/33931/151/46614` | `eaf2dfa261140ee0b67e114070b98bf98de5149207f00b911a313b5d84051533 / f9aad31269e6b2d9dd7302db698580e0d6ddba5eab18cb618c14a71a647ae942` |

三份 action 都在 boot `46ae55ad22b2a55e`，每份恰好 `1 driver / 1 visible refresh`；
L3 后累计 driver=`3`。三者均 `result=true / wait_timeout=false / failure_stage=none /
no_retry=true / no_recovery=true / no_autochain=true`。L3 的 `campaign_complete=false / next_ordinal=4`
是因为 L4 作为显式可选 repeat 仍可被人工选择；这不表示 L1–L3 失败，也不表示 L4
已经执行。

### 9.3 L3 留存相机帧与当前裁决边界

在 L3 COMPLETE 后，仅用项目指定的 `48MP USB Camera / VID_32E4:PID_4801`
拍摄，没有使用双目 `VID_1BCF:PID_0B15`。capture binding=`live_synchronized`，
scope=`full_panel`，画面完整可见；DirectShow/MJPG `4000×3000 @ 15 fps`，AF=0、focus=79、
AE=0.25、exposure=-6、AWB=0、WB=4600，warmup 10 帧，read failures=0。

| 工件 | bytes | SHA-256 |
|---|---:|---|
| `retained-camera-l3-attempt-01.jpg` | 781767 | `9e42a67ab768a4dd024a2b03a964095cd99a9533ef43348d2d5af3238c95c6d5` |
| `retained-camera-l3-attempt-01.capture.json` | 5154 | `7ec85c94db33a819fb31bc9c8d10793b66fbb96659dd19e7df414132c296a6c3` |

sidecar canonical SHA-256=`a049739a398c74541e135abcdb82e25f823a5b9c0128b1088174118a5088cdb1`，
capture time=`2026-09-01T10:01:32.073+08:00`。sidecar 本身明确记录：
`automated_assessment.verdict=INCONCLUSIVE / confidence=low / analysis_source=none /
candidate_detected=null`；因此这张图目前只是 L3 retained 证据，不是新色或明度命中。

拍摄时最后一份精确继电器记录仍是 commanded `ON`，但回执不具备负载侧电压反馈。
截至该拍摄时点：

- L4 尚未执行，只有在 L3 显示 recipe-following、controller-local、位置可重复的候选时
  才值得使用；
- V3 独立 factory-OTP white containment 尚未执行；
- `qualified_new_colours=0 / qualified_neutral_gray_levels=0 /
  qualified_lightness_levels=0`；
- V2 不得继续使用已被 V3 L1 刷新消费的 W11 retained-white 锚。下一分支须等
  V3 自身白恢复完成，再绑定新的当前白锚。

## 10. V3 L4 同曝光复核、独立白恢复与保护性 OFF

本节继续第 9 节的时点快照；第 9 节中的“L4／白恢复尚未执行”只描述当时状态，已由本节取代。

### 10.1 L4 唯一 action COMPLETE

- `action-04-l4-identical-active-target-code0-repeat.json`：
  bytes/file SHA-256=`35439 /
  50d20d6eacb7d477e3310a80057a04d6949a2d2a13885d14d09eaf04cf4fa810`。
- L4 与 L3 使用同一 frozen active/code0 target 和 frame；仍在 boot
  `46ae55ad22b2a55e`，终态 `COMPLETE / campaign_complete=true`，恰好 `1 driver /
  1 visible refresh`，总时长 `46.604 s`。无 timeout、retry、recovery 或 autochain。

### 10.2 完全相同曝光的 controller-local 比较

| 工件 | SHA-256 |
|---|---|
| L3 `retained-camera-l3-attempt-03-exposure-m4.jpg` | `d2c62688a445c75088a87ed40df919948f8e454b3dd998153b1af1dfe5df7f90` |
| L4 `retained-camera-l4-attempt-01-exposure-m4.jpg` | `75a0b898506bedbc85aeea0830220bbe210b9ccc978394769b97f02f4298394e` |
| L3 analysis | `200c449e34c22987a7b14eabc8aac95743fd427c139a0c1fa8b592afa56c5346` |
| L4 paired analysis | `0971345c2e73c49937564aaad1380b548721112a0517ff2f8a0383ccf16eb50b` |
| L3/L4 主比较报告 | `c008fc1ec20fbc0db2e49153a1716af89c918445239b540f15eb517c6a69b4ae` |

两帧 requested/effective-before/effective-after 相机设置均逐字段相等，曝光均为 `-4`。结果：

- CS2 L3 历史码中值跨度=`7.059 L*`，L4=`2.157 L*`，保留率=`30.56%`；
- centred 逐格 `|Delta L*| P95=4.647 > 3.0`；
- 逐码中值最大偏差=`4.118 L* > 2.0`；
- CS1 centred repeat gate 虽通过，但 L3 自身位置重复门失败且跨度只有 `3.725 L* < 4.0`；
- 两侧合计 256 个格底边为 `PRESENT=0 / CLEAR=255 / UNCERTAIN=1`；
- qualified 新色、灰阶和明度层级全部为 `0`。

因此 L3 的 CS2 信号只能保留为“一次构色后的 REVIEW 级历史明度信号”；L4 证明再次写相同
target 会明显压缩该差异。它不否定在 L3 后用 PTLW 局部窗口 HOLD 原区域的路径。

### 10.3 独立 factory-OTP 白恢复与相机可见审查

- action：`.test-output/hardware/MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_20260901_V1/action-01-factory-otp-white.json`
  ，bytes/file/canonical SHA-256=`36987 /
  9ebc3ca4f32ceba8cbb356aece938d28e922e016f875ab10aa082338993b509b /
  555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b`。
- action 为 `COMPLETE / 1 driver / 1 visible refresh / 35.023 s`，无 retry、recovery 或 autochain。
- 白屏 JPEG：`post-white-retained-camera-attempt-01-exposure-m4.jpg`，
  bytes/SHA-256=`1014449 /
  f04bc44ad4e92007f7ffd2a730a28fe602acf18d34b98d2540c5959c7a46d92a`。
- capture sidecar file/canonical SHA-256=
  `479c7451ca87c60cbef614895e3a3866a8415d0f3ccf3ad82668ae321bb459ae /
  7e9f7b6b9edb1e246da06316153e24e846761bc1c02fdf3a02fa5d1384ac7362`。
- clean-white review file/integrity SHA-256=
  `50ce755e3ed04790819c326bbbb1e6a2fdc3c6b587899f02b00da588d5e2d625 /
  7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40`。
  review 只在“无明显旧网格／色斑／粗大横竖条／中心接缝”范围 PASS；光照色偏、反射和透视
  仍不允许绝对白点、精密均匀度或微弱残留声明。

白恢复后 relay 回执 `relay-post-white-off.json` 的 file/canonical SHA-256=
`1fa84d45b7374fce680bdadcde0edb2142adfa408b5511edfa75dd20f0b09626 /
5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400`，COM14/channel1
commanded/query 均为 OFF；没有负载侧电压反馈，`electrical_state_proven=false`。当前面板保留
白场，ESP32 保留白 successor 固件。

### 10.4 下一功能门

下一次上屏不是继续扩大色相，而是 fresh-bound 的 16-recipe 位置平衡灰阶／明度机制。历史
明度候选的资格顺序改为：`单次构色 -> 局部 HOLD -> 独立 OTP 白锚 -> 从白锚重新执行完整构色
-> 最终 OTP 白恢复`。原位 identical-target repeat 只保留为已经完成的坍缩诊断，不再作为这类
历史 recipe 的复现门。更多色相、三次 fresh run、60/600 秒及长期可靠性均后置。

## 11. 12:40 后续功能链离线准备（无新增真屏动作）

本节仅记录离线开发，不改变第 10 节的现场终态：面板保留相机可见白场，relay/J2 的最后记录
仍为 commanded OFF；没有访问硬件、设备网络、COM、相机或继电器，也没有刷写、复位或刷新。

- 候选 HOLD 固件及其独立白 successor 已封印；新增 T0/T1/T2 比较器，能够分别审查 G3 候选
  保持、H1 探针在 H2 后保持、H2 探针出现、四边纯色和四副本完整性。它只输出 REVIEW draft，
  qualified 计数固定为 0。
- 第二次 fresh-white construction 固件及其独立 R3-only factory-OTP white successor 已完成
  clean build 与离线审计；R1/R2/R3 的 optical frame 和双 controller DTM 与首次 G1/G2/G3
  逐字节相同，但 campaign/contract/NVS/action 身份全部独立。
- 照片功能框架已补齐稳定基色明度族、qualified palette、照片逐像素 mapping、multi-LUT HOLD
  schedule、fixed-photo bundle 和功能优先门控器。一个已通过明度族可以先形成有限 palette 子集；
  未通过的族不会被推断或混入。
- 离线复验：static-photo `112 passed`，关键 runtime 合同 `85 passed`，功能框架 `15 passed`；
  F1/HOLD/fresh-reconstruction 审计均 PASS，SHA 清单逐项为 `31/31、24/24、24/24`。

因此下一真屏仍只执行 F1 G1→G2→G3 明度机制筛查。只有 G3 出现 controller-local、单像素纯色、
四边干净、四副本稳定且满足 L*/色相门的候选，才会继续 H1/H2 和 fresh reconstruction；无候选
则独立白恢复后转入有界明度后备机制，不扩大色相穷举。
