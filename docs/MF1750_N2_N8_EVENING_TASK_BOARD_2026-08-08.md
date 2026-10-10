# MF-1750 N2--N8 晚间逐项真屏任务板（2026-08-08）

状态：`N2--N8 PHYSICAL PRODUCTION SOFTWARE READY (7/7) / NOT HARDWARE-EXECUTED / NO HARDWARE AUTHORIZATION / NO CLAIM`。

> **2026-08-08 N2 安全覆盖：** 旧 N2 campaign 的 panel serial 是
> `UNBOUND-N2P-OFFLINE`；旧 runner/identity/claim 永久不可执行。N2 现已有 physical
> materializer、neutral limit-authority 深验证、逐 action production profile 审批链、physical
> one-shot/finalizer/analyzer，且全部保持 fail-closed。N3--N8 的同类 production-live
> physical 入口也已落地；对应旧 UNBOUND/self-sealed/legacy public live 路径均不得执行。
> 软件闭环不等于现场放行：真实 panel 文件、binding review、操作员选择的 process-policy
> 数值、最新 usage、每 action profile/review、测量资产和逐 action 用户授权尚未形成，本文也
> 不生成它们。软件完成总计 `7/7`；本覆盖不改变任何外部门禁。

本任务板把白天已完成的软件包整理成晚间逐项执行顺序。当前事实仍以
[`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 为唯一状态入口；本文不更新现场状态、不生成可见刷新
授权、不创建 claim，也不表示任何 action 已执行。每个真实 action 完成后仍须按 STATUS 的
强制规则逐项更新状态和 evidence。

## 1. 先看结论

离线算法/计划无需再等待；production live 状态必须区分：

- **N2**：physical-bound 8-action materializer、逐 action profile/usage 深绑定、one-shot、人工
  finalizer 和四格 analyzer 已完成；旧 UNBOUND 入口永久禁用，真实 policy/profile/授权未形成；
- **N3**：N3A/N3B physical plan/execution、one-shot/finalizer 和 analyzer 已完成；旧 public
  live 已硬阻断；N3A 真屏仍须 N2 唯一 winner；
- **N4**：8 个 physical-bound action、production profile、one-shot/finalizer 和 physical analyzer
  已完成；旧 public live 入口已硬阻断；
- **N5**：三类计划的 73 个 action physical materializer、production single-action runner、人工
  finalizer、session bundle 和聚合校验已完成；旧 self-sealed live 入口已硬阻断；正式测量是否
  能做取决于外部仪器、标准表和 reviewed profiles；
- **N6**：production physical CLI、N5 raw observation 全量重算、固定 action incident、同步耐久
  receipt/commit 与真实 Chromium physical E2E 已完成；旧 `mf1750_n6_visible_once serve` 永久禁用；
- **N7**：专用固件、physical campaign、5 个 physical-bound 固定频率 action、one-shot/
  finalizer/analyzer 已完成；旧 public live 入口已硬阻断；
- **N8**：5 个 session、15 个 physical-bound 固定 action、production profile、一次性 runner、
  人工 finalizer、递归 deep-bundle verifier 和 physical analyzer 已完成；live 仍取决于 reviewed
  runtime
  manifest、外部测温/相机/电表资产和逐 action 门控。

已就绪阶段的物理文件入口：

- `tools/g1_s1_n2_physical_campaign.py`、`tools/mf1750_limit_profile.py`、
  `tools/g1_s1_rc2g_n2_physical_once.py`、
  `tools/g1_s1_rc2g_n2_physical_analyzer.py`；
- `tools/g1_s1_n3a_physical_plan.py`、`tools/g1_s1_n3a_physical_execution.py`、
  `tools/g1_s1_rc2g_n3a_physical_once.py`、`tools/g1_s1_n3a_physical_analyzer.py`、
  `tools/g1_s1_n3b_physical_execution.py`、`tools/g1_s1_rc2g_n3b_physical_once.py`、
  `tools/g1_s1_n3b_physical_analyzer.py`；
- `tools/g1_s1_rc2g_n4_v3_physical_once.py`、
  `tools/g1_s1_n4_v3_physical_analyzer.py`；
- `tools/mf1750_n5_physical_campaign.py`、`tools/mf1750_n5_physical_execution.py`；
- `host/application/n6_physical_execution.py`、`tools/mf1750_n6_physical_once.py`；
- `tools/mf1750_n7_physical_campaign.py`、`tools/mf1750_n7_physical_once.py`、
  `tools/mf1750_n7_physical_analyzer.py`；
- `tools/g1_s1_n8_physical_execution.py`、`tools/g1_s1_rc2g_n8_physical_once.py`、
  `tools/g1_s1_n8_physical_analyzer.py`。

仍有上游正式外部产物未闭环的阶段是：

- **N2**：实际 supervised experimental process-policy 数值仍待用户/流程负责人选择；每个
  action 的最新 usage、draft、review artifact、approved profile 和一次性授权均不存在；
- **N6**：软件入口已闭环；可见模式仍必须等待 N5 的 complete measured palette/profile、formal
  artifact review、reviewed limit/runtime、真实 prior PASS、现场 runtime 和逐 action 外部授权；
  测试 fixture 不能替代这些输入；

没有 canonical reviewed limit authority（供应商限额，或明确标为非供应商额定值的受监督
实验流程 policy）、最新 usage/温度证据和逐 action 用户授权时，
**所有 runner 都只能 describe，不能执行**。不得为了“连续测试”批量预签授权或绕过 claim。

## 2. 总任务板

| 阶段 | 目的 | 冻结数量 | 软件入口 | 今晚前置外部输入 | 当前裁决 |
|---|---|---:|---|---|---|
| N2 | 四种自然图算法真屏 A/B 与 N3 winner 选择 | 4 sessions / 8 actions | physical materializer/profile approval/once/finalizer/analyzer ready；legacy permanently disabled | 用户选择的真实 limit authority、每 action 最新 usage/profile review、现场 gates、逐 action 授权 | 软件 ready；当前外部门未形成、无 live 授权 |
| N3A | winner 重复性 | repeat-2/3/4 对应 4/6/8 actions，只选一支 | physical plan/once/finalizer/analyzer ready；legacy live blocked | N2 唯一 winner、reviewed profile、10 项资产、runtime gates、逐 action 授权 | 软件 ready；尚未真屏执行 |
| N3B | Williams 顺序/位置效应 | 4 blocks / 32 actions | physical plan API/once/finalizer/analyzer ready；legacy live blocked | reviewed profile、10 项资产、逐 block gates、逐 action 授权 | 软件 ready；尚未真屏执行 |
| N4 | 空间频率×左右负载严格 2×2 描述 | 4 sessions / 8 actions | physical once/finalizer/analyzer ready；legacy live blocked | physical campaign、deep-verified production profile、现场 gates | 软件 ready；外部门齐全后逐项授权 |
| N5-D | 六色、混色、kernel、transition atlas 描述 | 11 sessions / 22 actions | physical campaign/describe/run/finalize/session-bundle/validate ready；legacy live blocked | supplier limit、panel/build/waveform/environment、逐 action 授权和观察资产 | 外部门齐全即可；不需改算法 |
| N5-P | D65/2° measured palette | 8 sessions / 9 actions，36 raw observations | 同一 physical production CLI 与 aggregation ready | 合格 45/0 分光仪、CIE 原表、校准/R&R、ROI/孔径、阈值/窗口 review、cold profile | 当前外部测量链未齐，不执行 |
| N5-T | measured 6×6 transition profile | 7 sessions / 42 actions，360 raw observations | 同一 physical production CLI 与 aggregation ready | N5-P 全部输入、exact B/W/B/W recovery 与 power profiles、温控/同步测量 | 当前外部测量链未齐，不执行 |
| N6 | 浏览器可见链端到端 | 每个 formal manifest 仅 1 个 exact action | physical describe/materialize/serve/finalize/validate ready；legacy serve blocked | measured palette/profile、artifact/runtime/limit reviews、prior PASS、现场 runtime、逐 action 授权 | 软件 ready；外部门齐全后逐项授权 |
| N7 | 1/2/4/8/10 MHz SPI 稳定性 | 5 actions | physical campaign/once/finalizer/analyzer ready；legacy live blocked | 专用固件刷入许可、每档冷断屏、示波器/串口/电气/温度证据、campaign 限额批准 | 独立专场；输入齐全可执行 |
| N8 | A→B→A、warm 与三温区描述 | 5 sessions / 15 actions | physical execution/once/finalizer/analyzer ready；legacy live blocked | reviewed supplier limits/温区、panel/build、相机/外部测温/电表/clock 资产、逐 action 授权 | 软件入口已冻结；外部门齐全后逐项执行 |

数量是计划口径，不是一次晚间必须完成的刷新预算。每晚能做多少只能由当时 reviewed limit
profile 的 cumulative/session/consecutive limits、interval、cooldown 和温度门决定。

## 3. 全场安全总门

### 3.1 开场前一次性确认

在任何 live 命令、claim 或 POST 之前，逐项确认：

1. 先读 STATUS，确认现场 J2、ESP32、固件和已消费 claims 的真实当前状态；
2. R15 拆除、R16=`0 Ω`、FPC/公共地/接线未变化；不带电插拔 FPC；
3. 面板电源 `3.3 V / CV / 1.00 A 限流`，空闲电流和温度正常；物理开关可立即切断 J2；
4. 当前 firmware build/API/binary SHA 与该阶段冻结身份精确一致；不一致则停在软件检查；
5. reviewed limit profile 精确绑定本 panel/build/action allowlist，usage snapshot 最新，处于有效期，
   间隔、cooldown、次数和起止温度均有余量；
6. action 的 frame、preview、prior result、job/op 和结果目录由 describe 唯一确定；结果目录必须
   是现有安全父目录下尚不存在的新目录；
7. 相机、示波器、分光仪、温度计、电表等本阶段必需设备已经固定、校准、armed，并有各自
   evidence identity；
8. 操作员在场，能观察电流、CV、温度、声音、气味和画面，物理 J2 开关随手可断；
9. 一次只选一个 exact action。describe 输出经人工核对后，用户再单独给出当次一次性确认；
   不预生成、不批量签发、不跨 action 复用。

任一项不满足：保持/切换到 J2 断开状态，停止在 describe，不创建 claim。

### 3.2 正常供电语义

- 离线 describe、预览、hash、文件验证和 analyzer 不访问设备，**不要求断 J2**。
- RC2G 的 N2、N3 默认计划、N4、N5 descriptive 和 N8 默认 session 在正常 safe-finish 后可
  由人工持续监督并保持 J2 接通；下一张仍需新的 exact action 授权，但不需要例行断电。
- `controller fresh boot` 不等同于 `panel cold cycle`。以各 runner/session 的冻结 power mode
  为准，不能自行把普通 session 改成冷启动，也不能伪称发生过 panel cold cycle。
- 同一 `MAP→target` 链之间通常明确禁止 ESP32 reboot、J2 disconnect、panel power cycle 和
  其他可见刷新；为“保险”断电反而会破坏该 action 的连续性资格。
- 只有以下情况切断 J2：刷写固件；改变接线/供电配置；session 合同明确要求 panel-cold；
  N7 每档规定的至少 10 秒断屏；N5 formal transition 每轮 target 后；任何异常；整晚收尾。
- Runner 不控制 J2、物理开关、EN 或刷机；这些状态只能由现场人工真实确认。

### 3.3 每个 action 的固定六步

1. **Describe**：只读核对身份、帧、profile、usage、prior 和 blocker；不得把 describe 当授权。
2. **人工复核**：打开 strict preview，核对现场状态、测量设备和本次结果路径。
3. **单次授权**：用户只授权这一个 exact action；再运行一次 live command。
4. **协议证据**：runner 先原子消费 workspace-global claim，再允许最多一条可见 POST；不自动
   advance、retry 或 recovery。
5. **人工观察/finalize**：保存画面、电气、温度和所需仪器证据，由独立 finalizer 生成结果。
6. **继续门**：只有深验证的 canonical PASS whole-file result 才能成为紧邻后继的 prior。

### 3.4 全场停止条件

出现任一情况立即停止当前和所有后续 action，实体断开 J2，并保存已有证据：

- 电源进入 CC/限流、退出 CV、3.3 V 明显跌落或电流未回到稳定水平；
- L1/L2、驱动器、面板或 ESP32 快速升温、热点、异味、异声或外观异常；
- ESP32 意外重启，job/op 不连续，firmware/frame/DTM/API/mapping/hash 不符；
- pre-command idle、新 BUSY edge、timing、safe-finish 或最终 RST/CS1/CS2 gate 失败；
- 网络结果不明、证据写入失败、runner 返回 `UNKNOWN_DO_NOT_RETRY`；
- 半屏漏刷、错位、镜像、错色、旧图未覆盖或与 strict preview 不一致；
- 相机/示波器/分光/温度/电表丢触发、overrange、身份或时间绑定失效；
- 任一 action final verdict 非 PASS，或下一 action 的 exact prior whole-file SHA 无法建立。

claim 一经创建即永久消费。禁止换目录、重启脚本、重发 POST 或“恢复一下再试”；只读补抓
允许的证据不属于重试。主观画质差但 frame fidelity、电气和 timing 正常时，记录为画质结论，
不要伪报为驱动故障。

## 4. N2：自然图四算法，8 个 action

### 4.1 目的、顺序和供电

顺序固定为：

1. `q1-map-primer → q1-target`（Atkinson）；
2. `q2-map-primer → q2-target`（area-weighted blue-noise）；
3. `q3-map-primer → q3-target`（multicolor DBS 262k）；
4. `q4-map-primer → q4-target`（overlap-aware DBS 262k）。

每个 cell 是独立 controller-fresh session；同 cell MAP→target 之间 J2 保持接通、ESP32 不重启、
不插入其他刷新。nominal cell 之间不因纯软件或观察而例行断 J2。八条深链全部 PASS 后才运行
四格 analyzer；唯一最高分只作为 `N3_branch_selection_only`，平分时不擅自选 winner。

真屏对照入口和评分合同见
[`N2P_RC2G_FIXED_EXECUTION_V2.md`](N2P_RC2G_FIXED_EXECUTION_V2.md)。

### 4.2 精确命令模板

下列 `$...` 均须由现场真实文件或本轮工具输出填写；本文没有填入 panel、policy、usage、
审批或授权。先把冻结 offline candidates 物化为一个 physical bundle。两个调度值都必须由
用户/流程负责人显式选择，并与随后 reviewed limit authority 相容：
`$MinimumIntervalSeconds` 必须 finite 且 `>0`，`$PlannedCooldownSeconds` 必须 finite 且
`>=0`。它们写入 manifest 的 `operator_process_schedule`，是操作员流程调度而不是供应商额定值；
两值会绑定 operator manifest、campaign、
8 个全新 action identity 和 claim。不得把 A1 PDF 中的可靠性试验 hold 时间自动抄成运行
interval/cooldown。

```powershell
python -m tools.g1_s1_n2_physical_campaign compile `
  --source-manifest $FrozenN2SourceManifest `
  --panel-file $PhysicalPanelJson `
  --binding-review-artifact $PanelBindingReviewArtifact `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --output-dir $NewN2PhysicalBundleDir

python -m tools.g1_s1_n2_physical_campaign validate `
  --bundle-dir $N2PhysicalBundleDir `
  --source-manifest $FrozenN2SourceManifest `
  --panel-file $PhysicalPanelJson `
  --binding-review-artifact $PanelBindingReviewArtifact
```

Limit authority 使用中性入口 `--limit-authority`。若没有供应商给出的完整 campaign/process
限额，只能由用户/流程负责人建立明确标注 `not_a_supplier_rating=true` 的 supervised
experimental process policy。下列命令仅从精确 A1 PDF 生成**故意不完整且不可审批**的模板；
所有次数、interval、cooldown、有效期、usage 最大年龄及逐字段 provenance 仍须人工选择和
复核。模板本身不放行任何 action。

```powershell
python -m tools.mf1750_limit_profile policy-template `
  --issuer $PolicyIssuer `
  --policy-id $PolicyId `
  --issued-at $PolicyIssuedAt `
  --panel-model $PanelModel `
  --source-document $ExactMf1750A1Pdf `
  --output $IncompletePolicyTemplateJson
```

**每个 action 之前都必须重新取得最新 usage evidence，并重新生成、审核、验证该 action 的
profile snapshot。** 八个 action 不得复用旧 usage、profile 文件或 review artifact；profile
lineage/完整 8-action allowlist 保持一致，但每 action 的 profile version、usage、review 和文件
identity 都应刷新。实际 authority 值仍待用户，因此以下只给变量模板：

```powershell
python -m tools.mf1750_limit_profile draft `
  --campaign $N2PhysicalCampaignJson `
  --firmware-binary $ExactFirmwareBinary `
  --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshPerActionUsageEvidenceJson `
  --profile-id $N2ProfileLineageId `
  --profile-version $PerActionProfileVersion `
  --output $NewPerActionDraftProfileJson

python -m tools.mf1750_limit_profile approve `
  --campaign $N2PhysicalCampaignJson `
  --firmware-binary $ExactFirmwareBinary `
  --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshPerActionUsageEvidenceJson `
  --draft-profile $NewPerActionDraftProfileJson `
  --reviewer-id $ProfileReviewerId `
  --reviewed-at $ProfileReviewedAt `
  --review-key $TrustedProfileReviewKey `
  --review-artifact-output $NewPerActionProfileReviewJson `
  --output $NewPerActionApprovedProfileJson

python -m tools.mf1750_limit_profile validate `
  --campaign $N2PhysicalCampaignJson `
  --firmware-binary $ExactFirmwareBinary `
  --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshPerActionUsageEvidenceJson `
  --profile $NewPerActionApprovedProfileJson `
  --review-artifact $NewPerActionProfileReviewJson `
  --review-key $TrustedProfileReviewKey `
  --evaluated-at $ImmediatePreActionEvaluatedAt
```

MAP 的 describe 不带 `--primer-result-dir`；target 必须带同 cell 已 finalized 且深验证 PASS 的
primer 目录。describe 只产生本 action 所需的 exact confirmation 内容，不创建 claim、不联网、
不授权。下例中的 `$N2Action` 每次只能取一个固定 action：

```powershell
python -m tools.g1_s1_rc2g_n2_physical_once describe `
  --action $N2Action `
  --bundle-dir $N2PhysicalBundleDir `
  --source-manifest $FrozenN2SourceManifest `
  --panel-file $PhysicalPanelJson `
  --binding-review-artifact $PanelBindingReviewArtifact `
  --profile $NewPerActionApprovedProfileJson `
  --firmware-binary $ExactFirmwareBinary `
  --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshPerActionUsageEvidenceJson `
  --profile-review-artifact $NewPerActionProfileReviewJson `
  --reviewer-key $TrustedProfileReviewKey `
  --evaluated-at $ImmediatePreActionEvaluatedAt
```

target describe 在上式追加：

```powershell
--primer-result-dir $SameCellFinalizedPrimerResultDir
```

只有最新 validate/describe 都通过、现场复核完成且用户只授权当前 exact action 后，才可运行
一次 `run`。MAP 使用 `--confirm-controller-fresh-boot`；target 不重启、不反复断 J2，并追加
下方五个 continuity confirmations。确认字符串必须逐字取自本次 describe，本文不预制。

```powershell
python -m tools.g1_s1_rc2g_n2_physical_once run `
  --action $N2Action `
  --bundle-dir $N2PhysicalBundleDir `
  --source-manifest $FrozenN2SourceManifest `
  --panel-file $PhysicalPanelJson `
  --binding-review-artifact $PanelBindingReviewArtifact `
  --profile $NewPerActionApprovedProfileJson `
  --firmware-binary $ExactFirmwareBinary `
  --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshPerActionUsageEvidenceJson `
  --profile-review-artifact $NewPerActionProfileReviewJson `
  --reviewer-key $TrustedProfileReviewKey `
  --evaluated-at $ImmediatePreActionEvaluatedAt `
  --result-dir $NewActionResultDir `
  --url $Esp32Url `
  --confirm-action $UserOneActionConfirmation `
  --confirm-panel-build $ExactPanelBuildConfirmation `
  --confirm-profile $ExactPerActionProfileConfirmation `
  --start-temperature-c $StartTemperatureC `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-controller-fresh-boot
```

target run 删除 MAP 专用的 `--confirm-controller-fresh-boot`，并追加：

```powershell
--primer-result-dir $SameCellFinalizedPrimerResultDir `
--confirm-map-fidelity-from-primer `
--confirm-esp32-not-restarted-since-primer `
--confirm-no-j2-disconnect-since-primer `
--confirm-no-panel-power-cycle-since-primer `
--confirm-no-other-visible-refresh-since-primer
```

同一 MAP→target 正常链不需要、也不允许为了“保险”反复断 J2；运行时有效门取
`max(operator schedule, reviewed authority minimum)`，间隔不足必须在 claim 与联网之前拒绝；
并在 target 前刷新 usage/profile approval。每个协议结果都由独立人工观察文件完成
finalization，再用深 validator 检查：

```powershell
python -m tools.g1_s1_rc2g_n2_physical_once finalize `
  --result-dir $ExistingActionResultDir `
  --observation-file $OperatorObservationJson `
  --reviewer-key $TrustedProfileReviewKey

python -m tools.g1_s1_rc2g_n2_physical_once validate `
  --result-dir $ExistingActionResultDir `
  --reviewer-key $TrustedProfileReviewKey `
  --require-finalized
```

四格完成后运行：

```powershell
python -m tools.g1_s1_rc2g_n2_physical_analyzer `
  --q1-map-primer-dir $Q1MapDir --q1-target-dir $Q1TargetDir `
  --q2-map-primer-dir $Q2MapDir --q2-target-dir $Q2TargetDir `
  --q3-map-primer-dir $Q3MapDir --q3-target-dir $Q3TargetDir `
  --q4-map-primer-dir $Q4MapDir --q4-target-dir $Q4TargetDir `
  --reviewer-key $TrustedProfileReviewKey `
  --output $N2AnalysisJson
```

### 4.3 人工观察与完成条件

- MAP：全屏、方向、标签、中缝、六码、残影、参考图忠实度；
- target：细节、色调、渐变、纹理、伪影、源图忠实度各 1--5 分，并独立记录几何/残影；
- 每张独立记录 3.3 V、CV、空闲/峰值电流、温度、声音/气味、ESP32 reboot 和物理切断；
- 固定相机是横向相机比较的必要条件，但不是单 action 人工 verdict 的替代品；
- 八个 finalized bundle 必须形成单调递增的 usage progression，且使用八组互不复用的 approved
  profile、review artifact 和 usage 文件；稳定的是同一 profile lineage/authority/limits，
  不是旧 profile bytes；
- 任一 cell MAP 非 PASS，则不执行其 target；任一 action 异常则整场停止。

## 5. N3：重复性与顺序效应（固定执行层已冻结）

> **当前覆盖：N3 physical production-live 软件入口已完成（总任务 7/7 中的一项）。** N3A/N3B
> 均已有 physical plan/execution、one-shot/finalizer 和 physical analyzer；这只表示软件完成，
> 尚未执行 N3 真屏。旧 `tools/g1_s1_rc2g_n3_once.py` public live 已硬阻断。

### 5.1 冻结计划

- N3A：只运行 N2 analyzer 的唯一 winner；用户只选 repeat-2/3/4 中一个模板，对应
  2/3/4 sessions、4/6/8 actions；不得把 Q1--Q4 十二个预制分支全部串播。
- N3B：不依赖 N2 winner；固定四阶 Williams 顺序，4 blocks、16 sessions、32 actions。
- 最低路线是 N3A repeat-2 的 4 actions 加 N3B 的 32 actions，共 **36 actions**。
- 每 session controller fresh；默认不要求 panel cold，J2 可保持接通。每个 MAP→target 之间
  禁止 reboot、J2 disconnect、panel cycle 或其他刷新。

### 5.2 不能提前执行的门

N3A 必须已有 N2 八条 finalized 深验证链、唯一 winner 和用户 repeat 选择；N3A/N3B 都必须
已有 10 项非空且审核过的测量资产、逐 P0 campaign/block reviewed limit profile、最新 usage、
有效期/温度/次数/间隔/cooldown 余量，以及逐 action 人工授权。Target 还必须取得与注册信息
一致的固定相机 capture。任一项缺失，只能做编译器允许的离线计划检查或 describe，不能 live。

Production physical 入口为：

- N3A plan/execution：`tools/g1_s1_n3a_physical_plan.py`、
  `tools/g1_s1_n3a_physical_execution.py`；
- N3A once/analyzer：`tools/g1_s1_rc2g_n3a_physical_once.py`、
  `tools/g1_s1_n3a_physical_analyzer.py`；
- N3B plan/execution：`tools/g1_s1_n3b_physical_execution.py`；
- N3B once/analyzer：`tools/g1_s1_rc2g_n3b_physical_once.py`、
  `tools/g1_s1_n3b_physical_analyzer.py`。

冻结 hashes、证据文件结构和完整 blocker 见
[`N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`](N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md)。

### 5.3 Exact compile / describe / run / finalize / analyze

N3A 使用实际 physical compiler CLI；每次公开读取都会重放八个 N2 physical finalized result：

```powershell
python -m tools.g1_s1_n3a_physical_plan compile `
  --n2-analysis $N2PhysicalAnalysis --physical-operator-manifest $N3PhysicalOperatorManifest `
  --binding-review-artifact $N3BindingReview --repeat-count $N3ARepeatCount `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --measurement-assets $ReviewedN3MeasurementAssets --output-dir $N3APhysicalPlanDir `
  --q1-map-primer-dir $Q1MapDir --q1-target-dir $Q1TargetDir `
  --q2-map-primer-dir $Q2MapDir --q2-target-dir $Q2TargetDir `
  --q3-map-primer-dir $Q3MapDir --q3-target-dir $Q3TargetDir `
  --q4-map-primer-dir $Q4MapDir --q4-target-dir $Q4TargetDir `
  --reviewer-key $TrustedN2ReviewerKey
```

N3B 没有 standalone plan compiler CLI；使用已落地的
`compile_n3b_physical_execution_context()` / `validate_n3b_physical_execution_context()` API
生成并深验 32-action plan，不能手改 JSON。两支的 production operator 分别是：

```powershell
# N3A / N3B 各自先 describe；两者参数面由实际 --help 冻结
python -m tools.g1_s1_rc2g_n3a_physical_once --action $N3AAction --describe-only `
  --physical-plan $N3APhysicalPlan --binding-review-artifact $N3BindingReview `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --n2-reviewer-key $TrustedN2ReviewerKey --profile-reviewer-key $TrustedReviewerKey

python -m tools.g1_s1_rc2g_n3b_physical_once --action $N3BAction --describe-only `
  --physical-plan $N3BPhysicalPlan --binding-review-artifact $N3BindingReview `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds --reviewer-key $TrustedReviewerKey
```

Live 时在对应命令上逐字重复 physical plan/review/schedule，并增加 production profile、physical
campaign、exact firmware、limit authority、fresh usage、profile review、evaluated-at、result dir、
URL、describe 输出的三条 exact confirmation 和实际电气/连续性 confirmations。Finalization 用同一
module 的 `--finalize-observation`，重放用 `--validate-result`；N3A 分析使用
`tools/g1_s1_n3a_physical_analyzer.py`，N3B 分析使用
`analyze_n3b_physical_result_files()`。所有报告固定为描述性 `NOT_QUALIFIED`。

以下旧 exact-plan/fixed runner 命令只保留历史字段关系，**全部是 BLOCKED legacy reference，
不得执行**。

先从已审核的 10 项测量资产编译 canonical exact plan。N3A 的八个 N2 目录必须指向 finalized
bundle；`$N3ARepeatCount` 只能由用户选择为 `2`、`3` 或 `4`。编译器会重新运行 N2 深
analyzer，并拒绝 tie、null、任一 gate FAIL 或非唯一 winner。N3B 固定编译为四个 Williams
blocks；不得修改 plan 中的 action、frame、job、prior 或顺序。

```powershell
# N3A：只会物化 unique winner × one repeat template
# BLOCKED legacy reference: tools.g1_s1_n3_compile_exact_plan `
  --study n3a --repeat-count $N3ARepeatCount `
  --measurement-assets $ReviewedN3MeasurementAssets `
  --n2-q1-map-primer-dir $Q1MapDir --n2-q1-target-dir $Q1TargetDir `
  --n2-q2-map-primer-dir $Q2MapDir --n2-q2-target-dir $Q2TargetDir `
  --n2-q3-map-primer-dir $Q3MapDir --n2-q3-target-dir $Q3TargetDir `
  --n2-q4-map-primer-dir $Q4MapDir --n2-q4-target-dir $Q4TargetDir `
  --output $N3AExactPlan

# N3B：固定 4 blocks / 16 routes / 32 actions
# BLOCKED legacy reference: tools.g1_s1_n3_compile_exact_plan `
  --study n3b `
  --measurement-assets $ReviewedN3MeasurementAssets `
  --output $N3BExactPlan
```

`$N3ExactPlan`、`$N3MapAction` 和 `$N3TargetAction` 必须直接来自上述 plan；不得手填 frame、
hash、manifest、job/op 或 prior。每个 live action 前先 describe。Target describe 必须绑定同一
session 已 finalized 的 MAP whole-file result：

```powershell
# MAP describe；纯只读
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan `
  --action $N3MapAction --describe-only `
  --limit-profile $ReviewedN3LimitProfile `
  --evaluated-at $EvaluatedAt

# Target describe；仍为纯只读，但必须深验紧邻 MAP prior
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan `
  --action $N3TargetAction --describe-only `
  --limit-profile $ReviewedN3LimitProfile `
  --evaluated-at $EvaluatedAt `
  --primer-result $SameSessionMapResult
```

用户只在核对当次 describe、strict preview、现场电气/温度和空结果目录后，提供这个 action
的一次性 `$UserOneActionConfirmation`。MAP live 必须确认 controller fresh boot；runner 随后
先全局原子 claim，再允许最多一次 `POST /api/frame`：

```powershell
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan `
  --action $N3MapAction `
  --limit-profile $ReviewedN3LimitProfile `
  --evaluated-at $EvaluatedAt `
  --result-dir $NewMapResultDir --url $Esp32Url `
  --start-temperature-c $StartTemperatureC `
  --confirm $UserOneActionConfirmation `
  --confirm-reviewed-panel-build-and-exact-plan `
  --confirm-registered-measurement-assets-present `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-controller-fresh-boot
```

MAP 协议完成后先提交人工观察并 finalize；只有 finalized PASS 才能成为同一 session target 的
prior。Target live 必须保持 MAP 后连续性，并使用新的逐 action 授权：

```powershell
# MAP manual finalization；不访问设备、不创建 claim
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan --finalize-observation `
  --result-dir $ExistingMapResultDir `
  --observation-file $MapOperatorObservationJson

# Target live；与 MAP 之间不得重启、断 J2、panel cycle 或插入其他刷新
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan `
  --action $N3TargetAction `
  --limit-profile $ReviewedN3LimitProfile `
  --evaluated-at $EvaluatedAt `
  --primer-result $SameSessionMapResult `
  --result-dir $NewTargetResultDir --url $Esp32Url `
  --start-temperature-c $StartTemperatureC `
  --confirm $UserOneActionConfirmation `
  --confirm-reviewed-panel-build-and-exact-plan `
  --confirm-registered-measurement-assets-present `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-map-fidelity-from-primer `
  --confirm-esp32-not-restarted-since-primer `
  --confirm-no-j2-disconnect-since-primer `
  --confirm-no-panel-power-cycle-since-primer `
  --confirm-no-other-visible-refresh-since-primer

# Target observation JSON 必须绑定注册相机 capture 文件及其 SHA-256
# BLOCKED legacy reference: tools.g1_s1_rc2g_n3_once `
  --plan-file $N3ExactPlan --finalize-observation `
  --result-dir $ExistingTargetResultDir `
  --observation-file $TargetOperatorObservationJson `
  --primer-result $SameSessionMapResult
```

Analyzer 只接受 exact plan 与 finalized MAP/target deep-bundle pairs。每条 route 重复一次
`--session`：N3A 必须正好 2/3/4 组，N3B 必须正好 16 组；不能传 loose observation/result。

```powershell
# BLOCKED legacy reference: tools.g1_s1_n3_analyzer `
  --plan-file $N3ExactPlan `
  --session $Session1MapResult $Session1TargetResult `
  --session $Session2MapResult $Session2TargetResult `
  --output $N3AnalysisJson
```

### 5.4 数量、供电、继续与停止规则

- N3A repeat-2/3/4 分别为 4/6/8 actions；加上固定 N3B 32 actions 后，总量分别是
  **36/38/40 actions**。永远不运行未选中的 N3A template，更不能串行执行 72 个候选 actions。
- 每条 route 是独立 `own MAP→target` session。每个 MAP 前 controller fresh boot/job0；普通
  session 不要求 panel cold，nominal session 之间 J2 可持续接通，不需要例行断电。
- 同一 MAP→target 内 J2 必须保持接通；ESP32 不得 reboot，panel 不得 cycle，不得插入其他
  visible refresh。Runner 不控制 J2、EN、刷机或物理开关，所有供电事实由现场人工确认。
- MAP 未 finalized PASS、exact prior result/finalization hash 不匹配、固定相机证据缺失，或任一
  视觉/电气/温度/连续性 gate 非 PASS：停止该 session 和后续 N3 action，不创建下一 claim。
- 出现第 3.4 节任一异常立即切断 J2。Claim 后发生网络/协议/证据失败时状态固定为
  `UNKNOWN_DO_NOT_RETRY`；不得换目录、重启 runner、再次 POST 或做 recovery。
- N3B 的有效研究结果要求四个 block 全部完整；提前停止只能记为 incomplete，不能据此宣称
  顺序/位置效应通过。Analyzer 输出是描述性证据，不是硬件、寿命或因果 qualification。

## 6. N4：根因 2×2，8 个 action

> **当前覆盖：N4 physical production 软件入口已完成。** 只使用
> `tools/g1_s1_rc2g_n4_v3_physical_once.py`；旧 `tools/g1_s1_rc2g_n4_v3_once.py` 的 public
> live API 已在 claim/联网前硬阻断，不得调用。

### 6.1 目的、顺序和供电

固定顺序为：

1. `low-balanced-map-primer → low-balanced-target`；
2. `low-unbalanced-map-primer → low-unbalanced-target`；
3. `high-balanced-map-primer → high-balanced-target`；
4. `high-unbalanced-map-primer → high-unbalanced-target`。

每格从 controller fresh job0 开始；同格 MAP→target 绝不重启、不断 J2、不做 panel cycle、
不插入其他刷新。nominal cell 之间 J2 可保持接通。逐张预览位于
`.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/`，完整规则见
[`N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`](N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md)。

### 6.2 精确命令模板

```powershell
# describe
python -m tools.g1_s1_rc2g_n4_v3_physical_once `
  --action low-balanced-map-primer --describe-only `
  --limit-profile $LimitProfile --evaluated-at $EvaluatedAt

# live MAP
python -m tools.g1_s1_rc2g_n4_v3_physical_once `
  --action low-balanced-map-primer `
  --limit-profile $LimitProfile --evaluated-at $EvaluatedAt `
  --result-dir $NewResultDir --url $Esp32Url `
  --confirm $UserOneActionConfirmation `
  --start-temperature-c $StartTemperatureC `
  --confirm-panel-build $N4PanelBuildConfirmation `
  --confirm-profile $N4ProfileConfirmation `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-controller-fresh-boot

# describe/live target 需增加同格 prior 和四项连续性确认
--primer-result $SameCellPrimerResult `
--confirm-map-fidelity-from-primer `
--confirm-esp32-not-restarted-since-primer `
--confirm-no-j2-disconnect-since-primer `
--confirm-no-panel-power-cycle-since-primer `
--confirm-no-other-visible-refresh-since-primer

# 人工观察 finalization
python -m tools.g1_s1_rc2g_n4_v3_physical_once `
  --finalize-observation `
  --result-dir $ExistingActionResultDir `
  --observation-file $OperatorObservationJson
```

Target finalizer 同时生成 cell observation；4 格 analyzer 使用
`tools.g1_s1_n4_v3_analyzer.py` 的 `compile_n4_v3_analysis_contract()`、
`build_n4_v3_cell_observation()`、`analyze_n4_v3()` 和 `validate_n4_v3_report()` 深验 API。
上述 describe/live 命令还必须传入同一组 `--rebind-manifest`、`--physical-campaign`、
`--physical-anchor-campaign`、`--binding-review-artifact`、interval/cooldown、exact firmware、
limit authority、fresh usage、profile review 和 trusted reviewer key；实际执行不得省略。
旧 analyzer 只保留离线合同背景。Production 分析使用
`tools/g1_s1_n4_v3_physical_analyzer.py` 的 `analyze_n4_v3_physical_result_files()` 和
`validate_n4_v3_physical_analysis_report()`；当前没有单独 CLI，晚间不需要重新开发算法。

### 6.3 人工观察与完成条件

MAP 仍判断全屏/方向/中缝/六码/残影；target 对照各自 `strict-final.png`，记录 fidelity、
ghosting、artifact severity、方向和拼缝，并分开保存 timing、电气、温度和连续性。四格完整
PASS 只产生 `EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY / NOT_QUALIFIED`，不能升级为因果资格。

## 7. N5：六色、混色、光学核与 6×6 transition

完整合同见
[`N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md`](N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md)。

### 7.1 编译、只读入口与逐动作执行接口

Production 入口仅为 `tools/mf1750_n5_physical_campaign.py` 与
`tools/mf1750_n5_physical_execution.py`。必须先以真实 compile profile、source manifest、physical
anchor、exact firmware、science review/approval、trusted reviewer key 和操作员选择的
interval/cooldown 编译 physical plan：

```powershell
python -m tools.mf1750_n5_physical_campaign compile `
  --compile-profile $N5CompileProfile --source-manifest $N5SourceManifest `
  --physical-anchor $N5PhysicalAnchor --firmware-binary $ExactRc2gFirmwareBinary `
  --science-review-evidence $N5ScienceReviewEvidence `
  --science-review-approval $N5ScienceReviewApproval --reviewer-key $N5ScienceReviewerKey `
  --namespace $N5Namespace --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds --output $N5PhysicalPlan

# 每个 action 先 describe；这里的省略号代表上方编译输入及同一 schedule，实际不得省略
python -m tools.mf1750_n5_physical_execution describe `
  --physical-plan $N5PhysicalPlan --compile-profile $N5CompileProfile `
  --source-manifest $N5SourceManifest --physical-anchor $N5PhysicalAnchor `
  --firmware-binary $ExactRc2gFirmwareBinary `
  --science-review-evidence $N5ScienceReviewEvidence `
  --science-review-approval $N5ScienceReviewApproval `
  --science-reviewer-key $N5ScienceReviewerKey --namespace $N5Namespace `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --profile $N5ProductionProfile --physical-campaign $N5PhysicalCampaign `
  --limit-authority $ReviewedLimitAuthorityJson --usage-evidence $FreshN5UsageEvidence `
  --profile-review $N5ProfileReview --profile-reviewer-key $TrustedReviewerKey `
  --action $FrozenN5ActionKey

# live：逐字重复 describe 的 deep inputs，并追加本 action 的一次性输入
python -m tools.mf1750_n5_physical_execution run `
  --physical-plan $N5PhysicalPlan --compile-profile $N5CompileProfile `
  --source-manifest $N5SourceManifest --physical-anchor $N5PhysicalAnchor `
  --firmware-binary $ExactRc2gFirmwareBinary `
  --science-review-evidence $N5ScienceReviewEvidence `
  --science-review-approval $N5ScienceReviewApproval `
  --science-reviewer-key $N5ScienceReviewerKey --namespace $N5Namespace `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --profile $N5ProductionProfile --physical-campaign $N5PhysicalCampaign `
  --limit-authority $ReviewedLimitAuthorityJson --usage-evidence $FreshN5UsageEvidence `
  --profile-review $N5ProfileReview --profile-reviewer-key $TrustedReviewerKey `
  --action $FrozenN5ActionKey --authorization $ExternalOneActionAuthorization `
  --session-start $SessionStartObservation --result-dir $NewActionResultDir `
  --url $Esp32Url --action-token $N5ActionToken --panel-plan-token $N5PanelPlanToken `
  --profile-token $N5ProfileToken --start-temperature-c $StartTemperatureC `
  --confirm-supply-cv-current-normal --confirm-j2-on --confirm-physical-cutoff-available

# non-root action 还必须追加紧邻前序；二选一，不能伪造 loose prior
--prior-bundle $ImmediatePriorFinalizedBundle
--prior-result-dir $ImmediatePriorResultDirectory

# finalize / session bundle / replay validation 均为离线；每条命令仍重复同一 physical context
python -m tools.mf1750_n5_physical_execution finalize `
  --physical-plan $N5PhysicalPlan --result-dir $ActionResultDir `
  --manual-observation $ManualMeasurementPayload --profile-reviewer-key $TrustedReviewerKey

python -m tools.mf1750_n5_physical_execution build-session-bundle `
  --physical-plan $N5PhysicalPlan --result-dir $ActionResultDir `
  --session-start $SessionStartObservation --profile-reviewer-key $TrustedReviewerKey `
  --finalized-at $FinalizedAt --output $NewSessionBundle

python -m tools.mf1750_n5_physical_execution validate-bundle `
  --physical-plan $N5PhysicalPlan --bundle $SessionBundle --result-dir $ActionResultDir `
  --profile-reviewer-key $TrustedReviewerKey
```

上述 finalize/build/validate 示例为便于阅读省略了 compile/source/anchor/firmware/science-review/
namespace/interval/cooldown 参数；真实 CLI 会把缺少任一项直接拒绝。以下旧 fixed CLI 仅保留
历史字段关系，public live 已硬阻断，**任何命令都不得执行**：

```powershell
# 用外部完整 reviewed profile 生成唯一 73-action / 26-session manifest。
# --output 必须不存在；并发发布也只允许一个 winner，绝不覆盖。
python -m tools.mf1750_n5_measurement_campaign compile `
  --profile $N5ProductionCompileProfile `
  --output $ReviewedMaterializedManifest

# 默认 22-action 清单；纯只读
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution list

# 默认 descriptive action；纯 describe
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution describe `
  --action n5-solid-code-0-map-primer `
  --limit-profile $LimitProfile --evaluated-at $EvaluatedAt

# 正式 materialized manifest；全局 --manifest 必须放在子命令前
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution `
  --manifest $ReviewedMaterializedManifest `
  describe --action $FrozenN5ActionKey `
  --limit-profile $LimitProfile --evaluated-at $EvaluatedAt `
  --prior-bundle $ImmediatePriorFinalizedBundle

# 唯一 live 入口；每次只消费一个 action claim，claim 在首个 GET 前创建。
# root action 不传 --prior-bundle；non-root 必须传紧邻前一 finalized item/bundle。
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution `
  --manifest $ReviewedMaterializedManifest `
  run --action $FrozenN5ActionKey `
  --limit-profile $LimitProfile `
  --profile-evaluated-at $ProfileEvaluatedAt `
  --authorization $ExternalOneActionAuthorization `
  --session-start $SessionStartObservation `
  --runtime-gates $RuntimeGates `
  --prior-bundle $ImmediatePriorFinalizedItem `
  --attempt-id $AttemptId --claimed-at $ClaimedAt `
  --protocol-completed-at $ProtocolCompletedAt `
  --result-dir $NewActionResultDir --url $Esp32Url

# 协议、人工测量、action finalization 分开；人工文件必须是 unsigned payload。
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution `
  --manifest $ReviewedMaterializedManifest `
  finalize --result-dir $ActionResultDir `
  --manual-observation $ManualMeasurementPayload `
  --completed-at $CompletedAt

# 一个或多个 --action-item / --session-start；正常 formal-transition 完整 target 或任意异常终态
# session 都必须传对应 cut id；正常 descriptive/palette session 不传。
# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution `
  --manifest $ReviewedMaterializedManifest `
  build-session-bundle --action-item $FinalizedActionItem `
  --session-start $SessionStartObservation --finalized-at $FinalizedAt `
  --j2-cut-session-id $CompletedFormalTransitionSessionId `
  --output $NewSessionBundle

# BLOCKED legacy reference: tools.mf1750_n5_fixed_execution `
  --manifest $ReviewedMaterializedManifest `
  validate --bundle $SessionBundle
```

Physical campaign compiler 与 `describe` 不生成 authorization、claim 或访问设备。Physical `run`
是唯一 production live CLI：只接受深验证 physical plan/campaign、reviewed authority/profile/
usage/session-start、逐 action authorization、固定 claim root、全新 result dir 和 URL；严格复用
RC2G N2/N4 的 version、job、
diagnostic、GPIO、BUSY/timing validators。成功必须恰好一次 `POST /api/frame`。job/report/transport
任一不一致均写成 `UNKNOWN_DO_NOT_RETRY`，claim 永久保留，不自动推进、重试或 recovery。
`finalize/build-session-bundle/validate-bundle` 都是离线证据步骤；finalizer 还会重新核对磁盘中的真实 claim。
测试 fixture 只允许用于离线测试，不得制造现场 evidence。真实输入未齐时停在 describe。
生产 CLI 的 claim root 固定为仓库 `REPO_ROOT`，不暴露路径覆盖项；测试函数才允许注入临时 root，
因此不能通过换目录为同一 action 创建第二套 claim registry。

`run` 发布 receipt 后必须恰有一个不可变 outcome-ready：PASS 为
`N5-PROTOCOL-PASS-READY.json`，core-validated UNKNOWN 为
`N5-PROTOCOL-TERMINAL-READY.json`。UNKNOWN 可以由人工终态密封，但只能保持 UNKNOWN；claim 后
receipt/claim/ready 发布事故写 `N5-CLAIM-COMMIT-UNKNOWN.json`，该目录永久禁止 finalize/bundle。
finalize 先发布 action item 和三个派生视图，最后发布绑定全部 whole-file SHA 的
`N5-FINALIZED-ACTION-COMMIT.json`；bundle loader 缺 receipt、正确 ready、item 或最终 commit
任一项都拒绝。正式测量 `measurement_pass=true` 必须按冻结顺序绑定全部 slots；false 只允许
有序前缀（可为空），非前缀或伪完整 PASS 均拒绝，aggregation 仍只接受完整 overall PASS。

### 7.2 三段供电与观察

- **N5-D descriptive，22 actions**：11 个连续 `primer→target` session；J2 nominal 可保持接通。
  观察六码 solid、3 个 mix atlas、edge/kernel、transition atlas 的画面、电气、温度和资产。
- **N5-P formal palette，9 actions**：1 个初始 MAP primer、2 pilots、6 formal runs；每个正式
  run 是独立 reviewed panel-cold session。每 formal target 后在 POF+55..65 s 内按预注册顺序
  完成 6 个 ROI，总计 36 raw observations。
- **N5-T formal transition，42 actions**：2 pilot + 5 formal sessions；每 session 开始只做一次
  reviewed panel-cold，随后 `black→white→black→white→initial→target` 六个动作期间 J2 保持
  接通，target 完成后才人工切断 J2；总计 360 raw observations。不是 42 次冷启动。

上述是 nominal 流程；任意 N5-D/P/T action 进入 FAIL/UNKNOWN 时都应在该终态 action 后立即
人工切断 J2、记录 `abnormal_terminal`，并停止同 plan class 的所有后续 action，不能等到 formal
target。正常 descriptive/palette PASS 不要求逐 session 切断。

N5-P/T 在合格 45/0 分光仪、CIE D65/2° 原表、校准/R&R、ROI/孔径、真实 environment、
supplier limits、recovery/power profiles 和阈值 review 未齐前均不可执行。N5-D 也仍需 supplier
limit 和现场逐 action 授权。

## 8. N6：真实浏览器可见链

完整实现与测试边界见
[`N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md`](N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md)。

N6 physical production core 位于 `host/application/n6_physical_execution.py`，operator 已完成，
唯一入口是 `tools/mf1750_n6_physical_once.py`。旧 `tools/mf1750_n6_visible_once.py serve` 在 claim/联网前
永久硬阻断。新 CLI 没有 `evaluated/claimed/completed/materialized/finalized` 时间参数，也没有
POST/retry 计数注入口；live 判定只用进程实际 UTC 时钟。

先按 `python tools/mf1750_n6_physical_once.py --help` 和各子命令 `--help` 核对当前解析器。
下列公共参数数组必须全部指向当晚的真实、已审查文件；`--n5-result-dir` 与
`--n5-palette-observation` 各重复传入冻结计划要求的全部文件，不能用测试 fixture 或 core-only
aggregate 代替：

```powershell
$N6DeepArgs = @(
  '--offline-manifest', $N6OfflineManifest,
  '--physical-anchor', $N6PhysicalAnchor,
  '--binding-review-evidence', $N6BindingReviewEvidence,
  '--minimum-interval-seconds', $N6MinimumIntervalSeconds,
  '--planned-cooldown-seconds', $N6PlannedCooldownSeconds,
  '--palette-aggregate', $N5PhysicalPaletteAggregate,
  '--gamut-profile', $MeasuredGamutProfile,
  '--prior-result', $ImmutablePriorPass,
  '--n5-physical-plan', $N5PhysicalPlan,
  '--n5-compile-profile', $N5CompileProfile,
  '--n5-source-manifest', $N5SourceManifest,
  '--n5-physical-anchor', $N5PhysicalAnchor,
  '--n5-firmware-binary', $N5FirmwareBinary,
  '--n5-science-review-evidence', $N5ScienceReviewEvidence,
  '--n5-science-review-approval', $N5ScienceReviewApproval,
  '--n5-science-reviewer-key', $N5ScienceReviewerKey,
  '--n5-namespace', $N5Namespace,
  '--n5-minimum-interval-seconds', $N5MinimumIntervalSeconds,
  '--n5-planned-cooldown-seconds', $N5PlannedCooldownSeconds,
  '--n5-finalized-bundle', $N5FinalizedBundle,
  '--n5-profile-reviewer-key', $N5ProfileReviewerKey,
  '--n5-standard-table', $N5StandardTable,
  '--n5-instrument-qualification', $N5InstrumentQualification,
  '--profile', $N6ApprovedProfile,
  '--physical-campaign', $N6PhysicalCampaign,
  '--firmware-binary', $RC2GFirmwareBinary,
  '--limit-authority', $N6LimitAuthority,
  '--usage-evidence', $N6UsageEvidence,
  '--profile-review', $N6ProfileReview,
  '--profile-reviewer-key', $N6ProfileReviewerKey,
  '--formal-review-envelope', $N6FormalReviewEnvelope,
  '--runtime-review-envelope', $N6RuntimeReviewEnvelope,
  '--formal-review-evidence', $N6FormalReviewEvidence,
  '--runtime-review-evidence', $N6RuntimeReviewEvidence,
  '--trusted-reviewer-key', $N6TrustedReviewerKey
)
foreach ($path in $N5ResultDirs) { $N6DeepArgs += @('--n5-result-dir', $path) }
foreach ($path in $N5PaletteObservations) {
  $N6DeepArgs += @('--n5-palette-observation', $path)
}

$N6RuntimeArgs = @(
  '--authorization-envelope', $N6ExternalAuthorization,
  '--runtime-observation-envelope', $N6LiveRuntimeObservation,
  '--authorization-evidence', $N6AuthorizationEvidence,
  '--runtime-observation-evidence', $N6RuntimeObservationEvidence,
  '--runtime-trusted-reviewer-key', $N6RuntimeTrustedReviewerKey
)

# 1. 零 claim/零网络/零设备 I/O 的深检查；有 blocker 时保持关闭
python tools/mf1750_n6_physical_once.py describe @N6DeepArgs

# 2. 静态门齐全后物化一个新 manifest；输出文件必须尚不存在
python tools/mf1750_n6_physical_once.py materialize @N6DeepArgs `
  --output $NewN6PhysicalManifest

# 3. 唯一 live 入口；本命令必须逐 action 获得用户授权后才可执行
python tools/mf1750_n6_physical_once.py serve @N6DeepArgs @N6RuntimeArgs `
  --manifest $NewN6PhysicalManifest `
  --device-url $Esp32Url `
  --attempt-id $UniqueAttemptId `
  --bind 127.0.0.1 --port 8765 `
  --receipt-output $NewN6PhysicalReceipt `
  --receipt-commit-output $NewN6ReceiptCommit `
  --confirm-serve `
    'SERVE_ONE_N6_PHYSICAL_ACTION__CLAIM_BEFORE_NETWORK__NO_RETRY_NO_RECOVERY'

# 4. 协议成功后才提交真实人工观察；UNKNOWN receipt 不接受 observation 提升
python tools/mf1750_n6_physical_once.py finalize @N6DeepArgs @N6RuntimeArgs `
  --manifest $NewN6PhysicalManifest `
  --receipt $NewN6PhysicalReceipt `
  --receipt-commit $NewN6ReceiptCommit `
  --observation $OperatorObservation `
  --output $NewN6FinalizedBundle

# 5. 纯离线深验实际 receipt、commit、仓库全局 claim 与 finalized bundle
python tools/mf1750_n6_physical_once.py validate @N6DeepArgs @N6RuntimeArgs `
  --manifest $NewN6PhysicalManifest `
  --receipt $NewN6PhysicalReceipt `
  --receipt-commit $NewN6ReceiptCommit `
  --bundle $NewN6FinalizedBundle

# 若生成固定 per-claim UNKNOWN incident，只能独占执行 incident replay，不能 finalize/retry
python tools/mf1750_n6_physical_once.py validate @N6DeepArgs `
  --manifest $NewN6PhysicalManifest `
  --incident $N6FixedPerClaimIncident `
  --incident-receipt-output $NewN6PhysicalReceipt `
  --incident-receipt-commit-output $NewN6ReceiptCommit
```

浏览器必须重新选择 exact source，经 `/convert-v2` 取回 `source/mapped/final/model` 四张
hash-bound preview，再完成三 exact token、same-origin、local preflight 和一次性 arm。enqueue
先原子 claim，之后整个 action最多一条 `POST /api/frame`；202 不是完成，必须闭合 matching
terminal job 和 diagnostic。错 job/report、网络不明、进程中断或落盘不明一律终态
`UNKNOWN_DO_NOT_RETRY`，没有第二 POST、retry、cancel 或 recovery。receipt 与 commit 必须在 HTTP
成功响应前同步耐久落盘；任一 fixed per-claim incident 存在时，finalize/普通 validate 必须拒绝。

软件入口完成不消除外部门。真实 complete N5 measured palette/profile、formal review、reviewed
runtime/limit、prior PASS、现场 runtime observation 和单 action 外部授权尚未形成时，只运行
`describe`，不得执行 `serve`。

## 9. N7：专用固件 SPI sweep，5 个 action

### 9.1 专场边界

N7 使用独立最小固件，不与 RC2G 的 N2/N4/N5/N8 同一连续固件会话混跑。刷入 N7 前必须
J2 断开；只刷一次。固件必须为 775536 bytes，SHA-256
`81e905d299a0011d2f9617621e20e3262baea42aa9a6360522618bbb2414cb66`。

频率严格为 `1→2→4→8→10 MHz`。**这是普通“不逐次断 J2”规则的明确例外**：每个频率前
J2 都必须断开至少 10 秒，再接通并执行一次 MAP；从 2 MHz 起 ESP32 必须保持同一 boot，
只断面板 J2，不按 EN。只有前一档 finalized PASS 才可 describe/执行后一档；首个 FAIL 或
UNKNOWN 立即结束 sweep。示波器 SCLK、串口 job、timing、电气、温度和画面证据缺一不可。

### 9.2 精确命令模板

只使用 physical campaign/runner；以下是 production CLI 的实际参数面：

```powershell
python -m tools.mf1750_n7_physical_campaign `
  --source-campaign-dir $N7SourceCampaignDir --panel $N7PhysicalPanel `
  --binding-review $N7BindingReview --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds --output $N7PhysicalBundle

# 1 MHz describe；后续档追加 --predecessor-result-dir $PreviousN7ResultDir
python -m tools.mf1750_n7_physical_once describe `
  --physical-bundle $N7PhysicalBundle --source-campaign-dir $N7SourceCampaignDir `
  --panel $N7PhysicalPanel --binding-review $N7BindingReview `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --profile $N7ProductionProfile --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshN7UsageEvidence --profile-review $N7ProfileReview `
  --reviewer-key $TrustedReviewerKey --frequency-hz 1000000

# live；同一组 deep inputs 不得省略
python -m tools.mf1750_n7_physical_once run $NewN7ResultDir `
  --physical-bundle $N7PhysicalBundle --source-campaign-dir $N7SourceCampaignDir `
  --panel $N7PhysicalPanel --binding-review $N7BindingReview `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --profile $N7ProductionProfile --limit-authority $ReviewedLimitAuthorityJson `
  --usage-evidence $FreshN7UsageEvidence --profile-review $N7ProfileReview `
  --reviewer-key $TrustedReviewerKey --frequency-hz 1000000 --url $Esp32Url `
  --authorization-confirmation $UserOneActionConfirmation `
  --panel-confirmation $N7PanelConfirmation --profile-confirmation $N7ProfileConfirmation `
  --panel-power-off-seconds $MeasuredPanelPowerOffSeconds `
  --start-temperature-c $StartTemperatureC `
  --confirm-j2-driver-power-off-for-measured-interval `
  --confirm-n7-firmware-flashed-with-j2-off-and-fresh-boot `
  --confirm-physical-cutoff-available --confirm-physical-panel-identity-verified `
  --confirm-scope-capture-armed --confirm-single-visible-action `
  --confirm-supply-cv-current-temperature-normal

# 2/4/8/10 MHz 追加 exact 前档目录和连续性门
--predecessor-result-dir $PreviousN7ResultDir `
--confirm-esp32-not-restarted-since-previous-frequency `
--confirm-no-other-visible-refresh-since-previous-frequency `
--confirm-previous-screen-fidelity-pass

python -m tools.mf1750_n7_physical_once finalize $NewN7ResultDir `
  --reviewer-key $TrustedReviewerKey --serial-log $SerialLog `
  --scope-evidence $ScopeEvidence --timing-evidence $TimingEvidence `
  --measured-sclk-hz $MeasuredSclkHz --supply-voltage-v $MeasuredSupplyV `
  --current-limit-a $CurrentLimitA --peak-current-a $PeakCurrentA `
  --max-temperature-c $MaxTemperatureC `
  --visual-pass --cv-pass --thermal-pass --acoustic-pass --sclk-pass --timing-pass `
  --notes $OperatorNotes

python -m tools.mf1750_n7_physical_once validate $NewN7ResultDir `
  --reviewer-key $TrustedReviewerKey

python -m tools.mf1750_n7_physical_analyzer `
  --reviewer-key $TrustedReviewerKey `
  $N7Result1MHz $N7Result2MHz $N7Result4MHz $N7Result8MHz $N7Result10MHz
```

下面旧 self-sealed runner 只保留历史字段对照，public live 已硬阻断，**全部不执行**：

```powershell
$CampaignDir = '.test-output/hardware/MF1750_N7_SPI_SWEEP_OFFLINE_20260808_V1'

# 1 MHz describe；后续档必须增加 --predecessor-result
# BLOCKED legacy reference: tools.mf1750_n7_spi_sweep_once describe $CampaignDir `
  --frequency-hz 1000000

# live；$UserOneActionConfirmation 只能来自用户对本次 describe 的单独确认
# BLOCKED legacy reference: tools.mf1750_n7_spi_sweep_once run `
  $CampaignDir $NewResultDir `
  --frequency-hz 1000000 `
  --url $Esp32Url `
  --authorized-campaign-sha256 a2191de2060b3ec754300ec2166475afa8647a26ca79be18404a45c0bdc9282a `
  --confirm $UserOneActionConfirmation `
  --confirm-n7-firmware-flashed `
  --confirm-panel-power-off-at-least-10s `
  --confirm-supply-and-temperature-normal `
  --confirm-scope-capture-armed `
  --confirm-single-visible-action

# 2/4/8/10 MHz describe 和 run 都增加 exact 前档 final result；run 还增加 boot 连续性确认
--predecessor-result $PreviousN7FinalResult `
--confirm-esp32-not-rebooted

# live result 完成后独立 finalization
# BLOCKED legacy reference: tools.mf1750_n7_spi_sweep_once finalize `
  $CampaignDir $N7LiveResult `
  --serial-log $SerialLog --scope-evidence $ScopeEvidence `
  --timing-evidence $TimingEvidence `
  --measured-sclk-hz $MeasuredSclkHz `
  --power-off-s $MeasuredPowerOffSeconds `
  --supply-voltage-v $MeasuredSupplyV `
  --current-limit-a $CurrentLimitA `
  --peak-current-a $PeakCurrentA `
  --max-temperature-c $MaxTemperatureC `
  --visual-pass --cv-pass --thermal-pass --acoustic-pass --timing-pass `
  --notes $OperatorNotes
```

最后一行的 PASS/FAIL flags 必须来自真实观察和证据；不得预填。Physical finalizer 输出
`N7-PHYSICAL-FINAL.json`，只有深验证的 PASS 才允许进入下一频率；五档齐全后只交给
`tools/mf1750_n7_physical_analyzer.py`，结论仍为描述性 `NOT_QUALIFIED`。

N7 完成或停止后先断 J2；若后续返回 RC2G，必须在 J2 断开时重新刷入并复核 RC2G exact
binary，然后把它当作新的固件会话，不能沿用 N7 的 job/prior。

## 10. N8：carryover、warm 与温区（固定执行层已冻结）

### 10.1 十五个 action 的 canonical 顺序

完整 N8 是 5 sessions / 15 actions，其中 10 个 non-root action 必须递归绑定紧邻前序
finalized PASS bundle、finalization 和 P0 result 的 whole-file SHA-256。Runner 的
`--action` 是下列 15 项的闭集，不能覆盖 frame、SHA、job/op、prior、power mode 或顺序。

| 全局序号 | session | action key | 角色与直接前序 |
|---:|---|---|---|
| 1 | ABA | `n8-aba-q1-q4-q1-map` | fresh-root MAP |
| 2 | ABA | `n8-aba-q1-q4-q1-a1` | Q1(A1)，prior=MAP |
| 3 | ABA | `n8-aba-q1-q4-q1-b` | Q4(B)，prior=A1 |
| 4 | ABA | `n8-aba-q1-q4-q1-a2` | Q1(A2)，prior=B |
| 5 | warm | `n8-warm-q1-q2-q3-q4-map` | dynamic-root MAP |
| 6 | warm | `n8-warm-q1-q2-q3-q4-w1` | Q1，prior=MAP |
| 7 | warm | `n8-warm-q1-q2-q3-q4-w2` | Q2，prior=Q1 |
| 8 | warm | `n8-warm-q1-q2-q3-q4-w3` | Q3，prior=Q2 |
| 9 | warm | `n8-warm-q1-q2-q3-q4-w4` | Q4，prior=Q3 |
| 10 | temperature-low | `n8-temperature-low-q4-map` | fresh-root MAP |
| 11 | temperature-low | `n8-temperature-low-q4-target` | Q4，prior=MAP |
| 12 | temperature-nominal | `n8-temperature-nominal-q4-map` | fresh-root MAP |
| 13 | temperature-nominal | `n8-temperature-nominal-q4-target` | Q4，prior=MAP |
| 14 | temperature-high | `n8-temperature-high-q4-map` | fresh-root MAP |
| 15 | temperature-high | `n8-temperature-high-q4-target` | Q4，prior=MAP |

可按用户选择把不同 session 分夜执行，但每个 session 内只能从 root 开始、按表中连续 prefix
前进；完整 N8 结论需要 15 项全部完成。Analyzer 会按冻结 sequence/ordinal 重排输入，并拒绝
duplicate/replay、断裂 prefix、异常后的动作或 prior/capture/asset 重放。

### 10.2 Runtime manifest 与真实入口

固定文件为：

- physical execution/runtime compiler API：`tools/g1_s1_n8_physical_execution.py`；
- describe/run/finalize/validate CLI：`tools/g1_s1_rc2g_n8_physical_once.py`；
- exactly-15-result physical analyzer CLI：`tools/g1_s1_n8_physical_analyzer.py`。

Physical runtime 刻意没有 standalone compiler CLI，这不是缺失入口。现场输入齐备后，由代理
使用 `compile_n8_physical_execution_context()`、`compile_n8_physical_runtime_manifest()` 和
`validate_n8_physical_runtime_manifest()`，把冻结合同重新绑定真实 panel、exact firmware、reviewed
authority、fresh usage、温度/相机/电表/clock、interval/cooldown 和受信 reviewer；canonical JSON
必须原样落盘。不得手改 JSON、自动读取/猜测供应商值或使用默认 unbound/test manifest 上机。

真实 manifest 至少绑定 supplier limit document/review artifact、panel serial/instance、exact
firmware build、外置温度 sensor/calibration/panel-location/U95、固定 camera
body/lens/mount/exposure/crop/illumination、电表、clock，以及互不重叠的 supplier
low/nominal/high 温区。ESP32 内部温度与 SWC temperature 不可用，也不得据此推断 panel 温度。

冻结 hashes、证据结构和完整 blocker 见
[`N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md`](N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md)。

### 10.3 Describe / run / finalize / analyze CLI

每个 action 先 describe；root 不带 prior，non-root 必须增加紧邻前序的 finalized physical result：

```powershell
# root describe；零 claim、零网络
python -m tools.g1_s1_rc2g_n8_physical_once `
  --action $N8Action `
  --describe-only `
  --physical-contract $N8PhysicalContract `
  --physical-campaign $N8PhysicalCampaign `
  --binding-review-artifact $N8BindingReview `
  --evaluated-at $EvaluatedAt

# non-root describe 追加；必须是紧邻前序 finalized physical result directory
--prior-result $ImmediatePriorResultDirectory
```

每条 describe/live 还必须传同一组 interval/cooldown、production profile、exact firmware、limit
authority、fresh usage、profile review 和 trusted reviewer key；下方为避免重复未逐行展开，实际
CLI 不允许省略。只有 describe 无 blocker、结果目录尚不存在、外置 panel-location 温度已实测、固定相机 ready，
且用户只授权本 action 后才运行。以下是所有 action 的 common live CLI；随后必须按 root 类型或
non-root 类型追加对应 flags：

```powershell
python -m tools.g1_s1_rc2g_n8_physical_once `
  --action $N8Action `
  --physical-contract $N8PhysicalContract `
  --physical-campaign $N8PhysicalCampaign `
  --binding-review-artifact $N8BindingReview `
  --evaluated-at $EvaluatedAt `
  --result-dir $NewN8ResultDir `
  --base-url $Esp32Url `
  --authorization-confirmation $UserOneActionConfirmation `
  --start-external-temperature-c $MeasuredPanelLocationTemperatureC `
  --confirm-reviewed-panel-and-build `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-external-temperature-instrument-verified `
  --confirm-fixed-camera-ready

# ABA MAP 与三个 temperature MAP：只给 fresh-root flag
--confirm-controller-fresh-boot

# warm MAP：只给以下两项，严禁给 fresh-root flag
--confirm-controller-idle-no-inflight-job `
--confirm-supervised-continuous-session-start

# 任意 non-root：追加 exact prior 和五项连续性确认
--prior-result $ImmediatePriorResultDirectory `
--confirm-prior-screen-fidelity-pass `
--confirm-esp32-not-restarted-between-actions `
--confirm-no-j2-disconnect-between-actions `
--confirm-no-panel-power-cycle-between-actions `
--confirm-no-other-visible-refresh-between-actions
```

每次协议完成后都需独立 operator observation 和真实 fixed-camera capture，再执行 finalizer；
finalizer 不访问设备、不创建 claim，也不产生第二次可见刷新：

```powershell
python -m tools.g1_s1_rc2g_n8_physical_once `
  --action $SameN8Action `
  --finalize `
  --result-dir $SameN8ResultDir `
  --operator-observation $N8OperatorObservationJson
```

Observation 必须记录外置 panel-location 起止/最高温度、3.3 V/CV、idle/peak current、画面、
连续性和相机 capture 路径/SHA，并与 runtime manifest 的 sensor/calibration/location/U95、
camera/exposure/crop/illumination、电表和 clock identity 完全一致。Finalizer 原样复制并解码
capture bytes；缺失、身份变化或重放均失败关闭。

Analyzer 只接受 production-format finalized result directory，没有 loose photo/temperature/electrical
输入；每个已完成的 unique action 重复一次 `--result-directory`：

```powershell
python -m tools.g1_s1_n8_physical_analyzer `
  --physical-contract $N8PhysicalContract --physical-campaign $N8PhysicalCampaign `
  --binding-review-artifact $N8BindingReview `
  --minimum-interval-seconds $MinimumIntervalSeconds `
  --planned-cooldown-seconds $PlannedCooldownSeconds `
  --reviewer-key $TrustedReviewerKey `
  --result-directory $N8ResultDirectory01 `
  --result-directory $N8ResultDirectory02 `
  --result-directory $N8ResultDirectory03
```

完整 campaign 分析必须提交恰好 15 个 result directory。即使 15/15 PASS，输出仍固定为
`qualification_state = NOT_QUALIFIED`、`hardware_qualified = false`、
`algorithm_qualified = false`；单次 ABA 和每温区一次 observation 只允许描述，不得升级为总体、
因果、寿命或温度资格。

### 10.4 Warm dynamic baseline、J2 与停止规则

- ABA 和三个 temperature session 只在 root MAP 前要求 controller fresh boot；这不是
  panel/J2 power cycle。默认 N8 没有 `panel_cold_cycle`，不得用 controller reboot 冒充。
- Warm root 是冻结的 `supervised_continuous` / `dynamic_first_action_baseline`：不要求且不允许
  人为引入 controller reboot。操作员只确认 idle/no in-flight，runner 读取 live completed
  baseline；它可以是 job0/op0，也可以是任意有效非零 job/op，Warm MAP 必须成为其
  next-nonzero-u32，并把实际 raw job/diagnostic 固化为 Q1 的物理 prior。
- 任一 session 的 root→末项之间 J2 保持接通；dependent action 之间禁止 ESP32 reboot、J2
  disconnect、panel cycle 或其他 visible refresh。正常完成一个 nominal session 不强制断 J2，
  runner 永不控制 J2、EN、刷机、reset 或物理开关。
- 每个 non-root 只有紧邻前序 finalized PASS，且 live raw job/diagnostic 与 stored prior 完全一致，
  才能继续；target job/op 必须是 prior 的 next-nonzero-u32。不得跨 session 借 prior。
- 任一 finalized FAIL、外置温度/相机/电气/连续性异常，或第 3.4 节任一停止条件，立即停止剩余
  action，不创建下一 claim，并由现场人工按异常流程切断 J2、保存证据。
- Claim 在第一条网络请求前永久消费；最多一次 `POST /api/frame`。Claim 后 timeout、冲突、
  响应丢失或证据异常统一为 `UNKNOWN_DO_NOT_RETRY`，停止剩余 action；不得 retry、recovery、
  换目录、重启脚本或补发 POST。

## 11. 推荐分夜执行顺序

不要把“软件已完成”误解为一晚串播至少 145 次。建议按外部许可拆为：

1. **RC2G 质量夜**：先 N2；八条全部 PASS 后离线选出 N3 winner。若 limit 仍有余量，可另开
   N4 专场；没有余量就正常收尾，不临场扩限。
2. **N3 重复/顺序夜**：exact plan、N2 unique winner、repeat 选择和全部外部门就绪后，先
   N3A，再决定是否进入 N3B；不跑未选择的 N3A 分支。
3. **N5 仪器夜**：先做仪器 qualification 和外部资料审查；随后 descriptive、palette、
   transition 分段执行。缺仪器或标准证据时不要用肉眼替代正式测量。
4. **N7 扫频夜**：独立刷 N7 固件，按五档冷断屏递增；首败即止；结束后断 J2。
5. **N8 环境夜**：reviewed runtime manifest 与全部外部门齐备、用户选定 session 后，按冻结
   CLI 在固定相机和外置 panel-location 温度条件下执行；不同温区不靠室温猜测。
6. **N6 可见 E2E**：只在 N5 measured 输出和 formal gate 已闭环后排期。

每晚安全收尾：等待当前 action 完成或进入 terminal unknown/fail，确认无第二 POST，保存并
hash evidence；人工断开 J2，确认电流/温度正常，再按 STATUS 规则更新数量、结果路径、exact
action、job/op、SHA、人工裁决和完成日志。

## 12. 白天离线复验

以下命令不访问 ESP32、不创建真实 claim 或授权：

```powershell
python -m pytest `
  tests/test_g1_s1_n2_physical_campaign.py `
  tests/test_production_limit_profile.py `
  tests/test_g1_s1_rc2g_n2_physical_once.py `
  tests/test_g1_s1_rc2g_n2_physical_analyzer.py `
  tests/test_g1_s1_n3a_physical_plan.py `
  tests/test_g1_s1_rc2g_n3a_physical_once.py `
  tests/test_g1_s1_rc2g_n3b_physical_once.py `
  tests/test_n3_n4_physical_rebind.py `
  tests/test_g1_s1_physical_analyzers.py `
  tests/test_n5_physical_campaign.py `
  tests/test_n5_physical_execution.py `
  tests/test_mf1750_n7_physical_campaign.py `
  tests/test_mf1750_n7_physical_once.py -q

python -m pytest `
  tests/test_g1_s1_n8_physical.py -q

python -m pytest `
  tests/test_n6_physical_execution.py -q

python -m pytest tests/test_repo_contract.py tests/test_evening_task_board.py -q
python tools/check_repo_contract.py
git diff --check -- docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md `
  tests/test_evening_task_board.py
```

这些检查只证明任务板引用和软件合同自洽，不构成硬件 PASS，也不会改变 STATUS。
