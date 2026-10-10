# N5 光谱、六码测量与 6×6 转换离线交接（2026-08-08）

状态：`DAYTIME SOFTWARE PHASE 3 COMPLETE / PRODUCTION CLI + STRICT RC2G READY / EXTERNAL EVIDENCE BLOCKED`。

本阶段完成离线编译、数值积分、证据聚合、固定 P0 声明、生产 CLI 和严格 RC2G 协议门禁。开发/
测试期间没有访问
ESP32、串口、GPIO 或外网；没有创建 claim 或授权；没有 POST 帧；没有执行 recovery；
没有放宽 `0x4/0x7` 或任何未知码。本文也不构成任何一次上机授权。

## 1. 已完成的软件结果

### 1.1 D65/2° 严格光谱积分

[`host/extended_color/spectral.py`](../host/extended_color/spectral.py) 已冻结：

- 波长单位只能为 `nm`，范围固定 `360..830 nm`，间隔只接受 `1 nm` 或 `5 nm`；
- D65 SPD 与 CIE 1931 2° CMF 必须由调用方提供原始 CSV bytes；项目不内置、猜测或
  插值标准表；
- 两个原表必须有 CIE 主来源 HTTPS URI、原文件 SHA-256、列顺序和人工 review artifact；
- 编译时逐字节复核两个原文件 SHA-256，禁止插值和外推；
- 数值算法固定为均匀网格复合梯形积分，`k=100/∫D65*ybar*dλ`，XYZ 为 `Y100`，
  Lab 为 CIE 1976、使用表内重算的 D65 white；
- 全反射必须重现冻结 D65/2° white tolerance；光谱必须与表完全同格、有限并在 `[0,1]`；
- 每份 reflectance 绑定 raw spectrum、measurement record 和 instrument qualification SHA；
  最终 report 可从表和 reflectance 完整重算，任一字段或 hash 改动都拒绝。

`integrate_numeric_grid_unqualified()` 只用于数学测试，结果明确为
`authority_qualified=false`，不能进入 measured palette/profile 聚合。

### 1.2 正式 palette 聚合

[`host/extended_color/aggregation.py`](../host/extended_color/aggregation.py) 只有
`mf1750-n5-formal-palette-measurement-plan` 可以生成 `calibrated=true`：

- 先执行不计入正式样本的 `vertical-pilot → horizontal-pilot`；
- 正式顺序固定为
  `v01 → h01 → v02 → h02 → v03 → h03`；
- 每个正式 run 只有 6 个预注册 ROI，全部有效读数必须落在 POF BUSY_N 低→高后的
  `55..65 s`，实际时间必须按预注册测量顺序严格递增；
- 总原始观察为 `6 codes × 2 orientations × 3 runs = 36`；每个 code 有 6 个观察；
- 不是 72 个观察。冻结 `global-v-bars` 中每个颜色只存在于一个 controller；竖向 ROI
  取实际颜色所在半屏，横向 ROI 取相反 controller，最终每个颜色累计
  `CS1=3 / CS2=3`，方向权重和 controller 权重均为 0.5；另一半不是该颜色，不能伪作
  第二个样本；
- pilot 不计入 `n=3`；缺任何一项不插值、不删点，整份 palette 拒收；离群点只报告，
  不得临场删除；
- 先对每方向的 3 个正式 run 求均值，再按两个方向各 0.5 聚合；逐色检查方向偏差、
  U95 和 Gage R&R；阈值、判定跨度及采集窗口可行性必须有外部 review artifact；
- raw spectrum/measurement identity 不能跨 slot 重放；panel、firmware、waveform、
  environment、table、instrument 和 action/result 路由必须完全一致；
- 任一 blocker 存在时 `palette=null`，仅改 `measured/calibrated` 标志不能通过 validator。

### 1.3 正式 6×6 transition 聚合

单次 72-ROI initial→target atlas 明确为 `descriptive-pilot-only`，永远不能生成 measured
transition profile。正式计划固定为：

- pilot 每 pair 2 次，`12` 次可见动作，全部排除在正式 `n` 外；
- 正式 5 repeats；每 repeat 为
  `black → white → black → white → initial → target`，共 6 次动作；
- 正式动作 `5×6=30`，正式 raw ROI observations
  `36 pairs × 5 repeats × 2 controllers = 360`；
- 每个 repeat 的 CS1/CS2 是成对 ROI，不是两个独立 repeat。因此每个 cell 的 primary
  统计先把 CS1/CS2 聚成一个 repeat 值，再以 `n=5` 报告；P95/P99 必须为 null，报告
  maximum observed 和 U95；
- raw controller `n=10` 只保留为 `paired_controller_diagnostics`，明确禁止报告 population
  P95/P99；
- profile 每 cell 的 `sample_count=5`，每个样本对应一个有两侧原始证据绑定的正式 repeat；
- 缺 360 项中任一项、raw spectrum/measurement replay、跨 panel/build/waveform/environment、
  recovery 失败或任一 result 不是 PASS，均保持 `measured_profile=null` 和全 null scaffold。

## 2. Atlas 和共享 P0

[`tools/mf1750_n5_measurement_campaign.py`](../tools/mf1750_n5_measurement_campaign.py)
生成 12 个离线 asset：

| atlas | 数量 | 用途 | 正式测量资格 |
|---|---:|---|---|
| 六个 solid physical code | 6 | 纯色描述/点测候选 | 不能单独生成 calibrated palette |
| mix atlas | 3 | 15 对无序颜色 × 3 比例 × 3 period | 64×48 只是 pixel ROI；未绑定 mm/孔径时 blocked |
| edge/kernel atlas | 1 | camera ESF/PSF/edge imaging | 单点 Lab 不得称 optical kernel |
| transition initial/target | 2 | 单轮 6×6 描述 atlas | descriptive only |

所有 target atlas 只含正式物理码 `0/1/2/3/5/6`，六码 histogram 总和必须等于
`1024×600`；mix、kernel 和 transition controller halves 镜像；所有测量 ROI 都不能跨
`x=512` seam。

默认共享 P0 有 `11 sessions / 22 actions`：六码 solid、3 个 mix、1 个 kernel 均为
`MAP→target`，transition 为已知 `initial→target`。全部是
`supervised_continuous`，不要求 controller reboot 或 J2 cycle，J2 可保持接通。

正式 palette 只有传入 reviewed panel-cold profile 才物化到同一个 P0，额外
`8 sessions / 9 actions`（首个 pilot 前另有一个 MAP primer）。每个正式 run 是独立
panel-cold session；profile 未审查时模板存在但动作不物化。

正式 transition 只有同时传入 exact reviewed recovery profile 与 reviewed power profile
才物化，额外 `7 sessions / 42 actions`：2 个 pilot sessions 共 12 actions，5 个 formal
sessions 共 30 actions。每个 session 在开始前只做一次已审 panel-cold start，轮内 6 个
动作期间 J2 保持接通，target 后要求人工断开 J2。不能误解成 42 次 J2 cycle。

42 个动作均已由通用 materializer 生成固定 frame/action identities。每轮内每个动作只依赖
紧邻前一动作的 PASS，并要求运行时绑定前一 result 和 action-finalization 的 whole-file
SHA；任一缺失/非 PASS 使剩余动作不合格，禁止 retry 和额外 recovery。

### 2.1 固定执行与 finalized evidence gate

[`host/extended_color/execution.py`](../host/extended_color/execution.py) 和
[`tools/mf1750_n5_fixed_execution.py`](../tools/mf1750_n5_fixed_execution.py) 已把三类计划接到
同一个执行合同：`descriptive`、`formal_palette`、`formal_transition`。

- `compile_execution_contract()`、`describe_fixed_action()` 和 CLI 的 `list/describe` 都是纯函数/
  只读路径；不生成 authorization、不创建 claim、不进行网络或设备 I/O；
- `mf1750_n5_measurement_campaign compile --profile ... --output ...` 只接受外部完整 reviewed
  production profile，必须物化 `73 actions / 26 sessions`；输出使用同目录临时文件、`fsync` 和
  exclusive hard-link 原子发布，目标已存在或并发竞争时拒绝，绝不覆盖，落盘后重新深校验；
- `execute_fixed_action_once()` 只接受调用方提供的 reviewed limit profile、外部授权、session
  start、runtime gates、精确 frame 和显式 transport；它不能自动推进到下一动作；
- `mf1750_n5_fixed_execution.py` 已提供生产 `run/finalize/build-session-bundle/validate` CLI。
  `run` 要求外部完整 manifest、逐 action authorization、session-start、runtime gates、固定
  workspace-global claim root、全新 result dir 和 URL；生产 CLI 将 claim root 固定到仓库
  `REPO_ROOT` 且不提供覆盖参数（仅测试 API 可注入临时 root），严格 adapter 复用 N2/N4 的 RC2G
  version/job/diagnostic/GPIO/BUSY/timing validators，生产代码不导入 test fixture；
- claim 在任何 transport 调用前以 exclusive-create 写入 workspace-global registry；同一 action
  的第二次 claim 永久拒绝；POST route/body 被审计，每 action 最多且 PASS 时恰好一次 POST；
- protocol receipt 之后必须独占发布且只允许一种 outcome-ready：PASS 使用
  `N5-PROTOCOL-PASS-READY.json`，core-validated UNKNOWN 使用
  `N5-PROTOCOL-TERMINAL-READY.json`；缺失、两者并存或与 receipt/claim 漂移均禁止 finalize；
- protocol receipt、manual observation、action finalization、P0 result、session finalization 和最终
  bundle 分层保存并以 whole-file SHA 相互绑定；未知 POST 结果为
  `UNKNOWN_DO_NOT_RETRY`，只能保持 UNKNOWN 终态，不得升级、自动 retry/recovery；
- `validate_finalized_bundle()` 是纯深校验器。正式 palette/transition aggregation 必须同时提供
  通过该校验的 normal finalized bundle，且每个 observation 必须精确对应其目标 action 的
  authorization、PASS result 和 measurement slot；手工拼接的“PASS”不能进入正式聚合；
- 人工记录的 `measurement_pass=true` 必须按冻结顺序完整绑定该 action 的全部 measurement
  slots，即使 visual/electrical/thermal 另有失败也不能省略；`measurement_pass=false` 只允许
  冻结有序前缀（可为空），非前缀、重复、缺项伪 PASS 均拒绝；任一人工 gate 失败必须写明 notes；
- formal transition 每 repeat 只接受一次 panel-cold session start，六个动作期间 J2 必须保持
  接通，正常完整 target 后记录一次人工 J2 cut；任何 plan class 的终态 FAIL/UNKNOWN 也必须
  当场人工切断 J2 并记录 `abnormal_terminal`，同时使同 plan class 的所有后续动作 ineligible。

生产 CLI 保持不可变证据分层：`N5-PROTOCOL-RECEIPT.json`、与 receipt/claim 精确绑定的唯一
outcome-ready、外部人工 measurement payload 经 `finalize` 密封后的 manual observation/action
finalization/P0 result、finalized action item、最终 `N5-FINALIZED-ACTION-COMMIT.json`，以及
dependency-closed session bundle。non-root action 必须同时绑定紧邻前一项 result 与 finalization
的 whole-file SHA；finalizer 会回读 workspace-global 磁盘 claim，bundle validator 会逐 action
重放严格 device evidence。错误 job/report/transport 均为永久
`UNKNOWN_DO_NOT_RETRY`，不会自动 advance/retry/recovery。
claim 消费后的 receipt 发布或磁盘 claim 复核若失败，也不会退回普通可重跑错误：CLI 返回
terminal `UNKNOWN_DO_NOT_RETRY`，尽最大努力独占写入事故记录；即使事故记录介质同时失败，
退出码仍为 3 且 claim 继续按永久消费处理；这种 `N5-CLAIM-COMMIT-UNKNOWN.json` 事故目录永久
禁止 finalize/bundle。正常或 core-validated UNKNOWN 的 finalization 先发布 action item，再按相同
字节补齐 manual/finalization/result 派生视图，最后才发布 `N5-FINALIZED-ACTION-COMMIT.json`
关闭事务；它绑定 outcome-ready、item 和三个视图的 whole-file SHA。中途失败可幂等恢复补齐，
但任何既有字节漂移都拒绝。bundle loader 同时要求 receipt、正确 ready、item 和最终 commit；
bundle builder 还会拒绝未知、多余或重复的 J2-cut session id，不会静默忽略。

默认 describe-only execution contract 固定为 `22 actions / 11 sessions`：

- canonical SHA-256：`b14d0e8dd4dff16268e29eb557a5c85b310acc10d59731ba3f9d4accb5bc832c`
- canonical whole-file SHA-256：`c02e9956f14ea9ea92283691d44b3971685cbd19a9670e2508aed36303da93eb`

传入所有真实且已审外部 profile 后，合同可一次物化为 `73 actions / 26 sessions`，即
`22 descriptive + 9 formal_palette + 42 formal_transition`。项目不会为缺失的 supplier limits、
recovery/power profile、仪器/标准表证据或 action authorization 猜值；缺失时保持
`describe-only / hardware_ready=false`。

## 3. 两种“光源”不能混用

- 分光 reflectance 的正式输出 illuminant 是数值计算中的 CIE D65，observer 是 CIE 1931
  2°，几何是 45/0；不要求把外部灯称为 D65。
- camera spatial/ESF/PSF/均匀性使用独立 RAW imaging 合同，外部光源目标
  `5000±100 K`，并要求固定 RAW、曝光、白平衡和几何。该相机链不能生成
  `calibrated=true` palette。

## 4. 当前外部门

下列任一缺失时 `hardware_ready=false`；不能通过改布尔标志放行：

1. 实际 panel model/serial/board/PCB 与固件 commit/build/binary/driver API；
2. waveform identity、当次温湿度和 environment record；
3. 外部权威 CIE D65 SPD 与 CIE 1931 2° CMF 原表、各自 SHA 和人工 review；
4. 合格 45/0 分光仪、序号/配置、有效校准证书、孔径、fixture review、至少
   10 stationary + 10 repositioned、至少 2 sessions 的 repeatability/R&R evidence；
5. pixel pitch、ROI 实际 mm 和 instrument aperture fit review；
6. reviewed supplier limit profile、usage counters/contract 和 temperature measurement chain；
7. palette 方向偏差/U95/acceptance-span 阈值与“6 个读数可落 55..65s”的可行性 review；
8. EC4 在六码已知初态均通过的 exact B/W/B/W recovery profile，以及每 repeat 起止供电
   profile；
9. 每个固定 action 的当次 preflight、唯一授权、claim 和人工继续决定。

项目没有内置标准表，也没有 supplier threshold；这些值不能由软件猜测。

## 5. 晚间执行时不需要再写代码的路线

白天阶段已预制下面三个层级、严格 compiler 和统一生产执行器，晚间只做
“绑定真实外部证据→逐项授权→观察/测量→保存结果”：

1. **描述 atlas**：默认 11 sessions/22 actions，可逐 session 验证 solid、mix、kernel 和
   transition atlas；普通 session 不需要每次断 J2。
2. **正式 palette**：外部门齐全后，用 reviewed cold profile 重新编译同一 P0，依次执行
   2 pilots + 6 formal runs；每 run 后保存 6 份 raw spectrum、measurement record、
   result/camera/environment SHA，再进入下一 run。
3. **正式 transition**：recovery/power profile 通过后，同一 materializer 直接产生
   2 pilot + 5 formal sessions；每 session 人工逐动作继续，6 个动作完成后断 J2并审证；
   五个正式 repeat 全部通过后，360 observations 才能聚合 profile。

完整命令和变量顺序已集中在
[`MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)
的 N5 章节。`list/describe` 与 compiler 无参数默认路径仍为零副作用；只有显式 `run` 会触发
claim 和设备 I/O。

如果设备或仪器时间窗口、外部 profile 或安全证据不能满足合同，晚间任务停在 blocker；
不需要临时改代码，也不得降级标成正式 measured/calibrated。

## 6. 验证与冻结身份

N5 专项覆盖：白/黑/中性数学、错误 grid/nonfinite/range、表/原光谱/manifest tamper、
跨 panel、slot/replay、instrument flag promotion、36-observation calibrated palette 正路径、
360-observation formal transition 正路径、缺样/重放、n=5 primary 与 paired-controller
统计、P0 数量/供电语义、零 socket I/O 和 unknown-code guard。

冻结默认 manifest 身份（以最终代码常量和测试为准）：

- canonical SHA-256：`608ddc072f433fdce53c126508e2ba7d79ac83f19ee6e13dcd023035c804f4c3`
- canonical whole-file SHA-256：`578d9b0b1438fbb2a8a0df2d9053db961b96bbfa8de5d47cdc42f70b03b06065`

Phase 1 本地验证：

- N5 专项：`40 passed`；
- 既有 extended-color/color-pipeline 回归：`105 passed, 260 subtests passed`；
- N3 邻接回归：`15 passed`；
- repo contract（既有 + N5）：`29 passed`；
- 本次 9 个 Python source/test 文件 `ruff` 全通过，5 个 source 文件 `py_compile` 全通过。

各命令有少量重复覆盖（例如 N5 repo-contract 同时出现在专项和 repo-contract 命令），因此
不把这些数字相加伪报“唯一测试总数”。本文未修改 `docs/STATUS_HANDOFF.md`。

Phase 2 最终验证：

- fixed execution + finalized aggregation gate：`20 passed`；
- N5 campaign/spectral/repo-contract 邻接：`30 passed`；
- extended-color 全回归：`96 passed, 218 subtests passed`；
- visible-refresh/N3 邻接：`31 passed, 5 subtests passed`；
- repo contract：`30 passed`；
- Phase 2 修改文件 `ruff` 和 `py_compile` 全通过。

这些命令有重复覆盖，不能相加伪报唯一总数。测试只使用内存 transport 和临时 claim 目录，
不代表任何真实硬件动作、真实授权或真实 claim。

Phase 3 生产 CLI / strict adapter 冻结验证（2026-08-08）：

- focused compile/fixed/operator/RC2G + aggregation：`47 tests in 167.733s`，零失败；
- N5 完整八模块（compile CLI、fixed core/operator、RC2G、campaign、N5 repo-contract、
  spectral、aggregation）：`77 tests in 183.140s`，零失败；
- evening-task-board + N5 repo-contract：`13 tests in 6.101s`，零失败；
- 9 个修改 Python 文件的 `ruff check` 与 `py_compile` 全通过；相关代码/测试/两份文档当前均为
  untracked，已另做逐文件行尾空白扫描并通过；所有验证均为离线/localhost，不构成真屏或现场电气 PASS。

Phase 3 冻结 whole-file SHA-256：

- `tools/mf1750_n5_measurement_campaign.py`：`4c9b4db7bdad8a0491b5e49af01652f5268df7e72fd995d10b53af64a0fdd2d3`
- `tools/mf1750_n5_fixed_execution.py`：`715a269033383410ef4eda391adb66db2d0a62a06811d21421d2b4d0f4a14185`
- `host/extended_color/execution.py`：`32558bdad1fced5d91c5922b799ad48c5ba2d8ae6896c4ad60b124f5141f900f`
- `host/extended_color/n5_rc2g_protocol.py`：`d55d69589f8441241f15fe9bd4c0fd093da82717ae1c67ad24ffe2940363a45c`
- `tests/n5_execution_fixture.py`：`d9d8c0fb0b894067beb577e8f8a7f7e9da66f9faebaeccbd20aab009f91af96d`
- `tests/test_n5_compile_cli.py`：`15fde3a4b9ea321624be864864493fb8e24256b5d575bb9cac9e1b5454ac1636`
- `tests/test_n5_fixed_execution.py`：`8d944ca85aeb23ca600006fee41d8d0ca347fa04e8ee1212b37c183b4b13ed13`
- `tests/test_n5_fixed_execution_operator.py`：`84176edf4fdba596ff225fbd9a2c6621c42c6bb08f2cd8b0e6946d97d5eb6cc8`
- `tests/test_n5_rc2g_protocol.py`：`7bc18052ea2ccaf5a4710f438f717bb8e1a4dacc60b7397635e66269a3e5be5b`
- `docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`：`2c6e9cbfd85078770b405ede64fbe96a05ec0f4c5cbaeed62f1dc35ad4c4d0ac`
