# N8 残影、warm 与温度分档固定执行交接（2026-08-08）

## 当前结论

N8 白天可完成的软件执行层已经落盘：固定 5 个 session、15 个可见 action、10 个紧邻
前序 finalized PASS 依赖，具备 describe、永久 claim、单次 POST、协议深验证、人工
finalize、递归 bundle 验证和只接收深验 bundle 的 analyzer。所有离线回归使用脚本化 HTTP
和 test-only 证据，未访问 ESP32、未刷机、未复位、未控制 J2，也未创建真实 claim 或真实
授权。

晚上不需要再等代码逐点编写；需要的是先用真实供应商限制、panel/firmware binding 和测量
资产编译一份 reviewed runtime manifest，然后按本文件固定顺序逐项上机。任何 action 都不会
自动前进，必须由操作员单独 describe、确认、授权、run、观察和 finalize。

所有结果，包括 15/15 PASS 的完整链，始终是：

- `qualification_state = NOT_QUALIFIED`
- `hardware_qualified = false`
- `algorithm_qualified = false`
- descriptive only，不允许由单次 ABA 或每温区一次 session 得出总体/因果合格结论。

## 冻结身份

- source N8 manifest canonical SHA-256：
  `0914e9a63cc18593b27b1f51cf86e7a29a4c65a17b0427b5d4717ee745b8ba91`
- source N8 manifest whole-file SHA-256：
  `5d42dd01036512b836e286bb7c2f0735df36523b1434b84eb12bbba471c1e4ab`
- source nested P0 campaign canonical SHA-256：
  `fb24ab9bc840f4af22047b062326b472fa8a9402281bd8059cc44afb4025caa6`
- N8 fixed execution contract canonical SHA-256：
  `51efc4a3d298813956a0dbc380032aaeac460c23a52981f4f2ffd1690eda976e`
- N8 fixed execution contract whole-file SHA-256：
  `fd3ea6e182cbc06c0d247c8051a4213d1459559f4a8926d704131fd81d6d5fbf`
- upstream N2P manifest canonical SHA-256：
  `976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b`
- upstream natural-photo input SHA-256：
  `04034fbc1836791e0d1370d70d1871f174407b877ca24563f6cb0cf97a63eb07`

Runtime manifest 可以补入真实 panel serial、测量资产、温区和 reviewed limit profile；执行
validator 会把它投影回上述 source，禁止修改 15 个 action、frame、顺序、prior、power mode、
N2P 来源或分析语义。

## 固定 session 与 J2 语义

| session | action 顺序 | controller 语义 | J2 语义 | 目的 |
|---|---|---|---|---|
| `n8-aba-q1-q4-q1` | MAP → Q1(A1) → Q4(B) → Q1(A2) | MAP 前 fresh boot；之后不得重启 | nominal chain 可一直接通，动作间不得断开 | 直接 A→B→A carryover |
| `n8-warm-q1-q2-q3-q4` | MAP → Q1 → Q2 → Q3 → Q4 | **supervised continuous，不要求/不允许人为引入重启** | nominal chain 可一直接通，动作间不得断开 | warm 连续显示 |
| `n8-temperature-low-q4` | MAP → Q4 | MAP 前 fresh boot | nominal chain 可一直接通 | 厂商定义低温档 |
| `n8-temperature-nominal-q4` | MAP → Q4 | MAP 前 fresh boot | nominal chain 可一直接通 | 厂商定义常温档 |
| `n8-temperature-high-q4` | MAP → Q4 | MAP 前 fresh boot | nominal chain 可一直接通 | 厂商定义高温档 |

关键澄清：controller fresh boot 不是 panel/J2 power cycle。正常系统与画质测试不需要每步
切断驱动电源。runner 完全不控制电源或复位；J2 可在一个 nominal session 中保持接通。
依赖 action 要求人工确认从前一 action 后没有 ESP32 reboot、J2 disconnect、panel power
cycle 或其他可见刷新。异常、固件/配置变更或整个 campaign 结束时的物理处置由操作员安全
流程决定，不是 runner 的隐藏动作。

Warm root 保留冻结的 `supervised_continuous` 科学语义。其首个 MAP 使用
`dynamic_first_action_baseline`：操作员确认 controller idle/no in-flight，runner 读取 live
job/diagnostic/GPIO。live baseline 可以是 job0/op0，也可以是任意有效的非零已完成 job/op；
MAP 结果必须是各自的 next-nonzero-u32，并把实际 job/op、raw job、raw diagnostic 固化为
后续 Q1 的物理 prior。代码不会把 warm root 强制改成 job1/op1，也不会要求重启。

默认 N8 没有 `panel_cold_cycle`。panel-cold 要求不同的 reviewed profile、正的实测 panel-off
时间和重新编译的不同 P0 session，不能拿普通 controller reboot 冒充。

## 15 个固定 action 顺序

Runner 的 `--action` 只接受下列 key，不能从命令行覆盖 frame、SHA、job/op 或 prior。

### 1. A→B→A（4）

1. `n8-aba-q1-q4-q1-map`  
   `07d5084547a1fb66c12f2a47b8bea583f4ba66ebc67f0141ab07d1c647d2ee2a`
2. `n8-aba-q1-q4-q1-a1`  
   `a561fa612d3fb259b3fd58eb810b6c2eaf66d158e1b234ccaa99e7a2e1fcb1ea`
3. `n8-aba-q1-q4-q1-b`  
   `42abc25af4444c712cc5a31281d078701011bfd471e930b5237ece53b1b1238c`
4. `n8-aba-q1-q4-q1-a2`  
   `ff7bff47b4957469ed68b05c88d53da70c26bf60ffc7b93a026c173aa532de04`

### 2. Warm sequential（5）

1. `n8-warm-q1-q2-q3-q4-map`  
   `07a55c73bee44059300ba321c07b55f48252d90eccdeb41c22789e150d39c209`
2. `n8-warm-q1-q2-q3-q4-w1`  
   `25df2ad988a27e3683cb56c5d7b4a2ce91547fa80ef3577ba1b93647cc68c64b`
3. `n8-warm-q1-q2-q3-q4-w2`  
   `1be47a54c5c84e07cdf1128a6dda92328e147bdfbd152f40fd7aeefc3bd9b502`
4. `n8-warm-q1-q2-q3-q4-w3`  
   `63a1f18f5eb4ea851cb0df29f64f6b9bfcbdccc545cbab76887028d850014eac`
5. `n8-warm-q1-q2-q3-q4-w4`  
   `01341243d31f0c476061844c73d0b366e87e58d219b291b13c8d20f948933496`

### 3. Temperature low（2）

1. `n8-temperature-low-q4-map`  
   `56f77ae6bcf2df3671a2d8f77d0577ed0663221ddbd8a2810d4c8f8b6ec72bcd`
2. `n8-temperature-low-q4-target`  
   `421ee6d9fd805bef0f77383682cf9468d21240af7285c1fbb07cfd657288a251`

### 4. Temperature nominal（2）

1. `n8-temperature-nominal-q4-map`  
   `ae3cfed4996d848c379d8984bf0f5d9327c6da924bbb337404a95afcbd8bd226`
2. `n8-temperature-nominal-q4-target`  
   `75fbd55c08cf2cf5bb110b946cd7a600b351260965db4917b6fa72b1292d3553`

### 5. Temperature high（2）

1. `n8-temperature-high-q4-map`  
   `a6cebc64bb7cac3426b7902042d1a139ed3ff48c8d5138c7cbeb798a59a0b578`
2. `n8-temperature-high-q4-target`  
   `22db68185e453191242e509139ec16aa65e1179385a1ce7bb4b0f459dab53d2d`

以上 hash 是 action identity，不是本次真实授权。每个 action 的精确确认字符串由
`required_authorization_confirmation(action_key)` 离线确定；真实 claim/授权只能在对应
晚间 action 的人工门控通过后使用一次。

## 固定执行与证据链

每个 action 在 claim 前完成 runtime manifest、profile、温度、prior bundle、confirmations
和精确确认字符串检查。claim 是 workspace-global、以 action SHA 命名、永久消费且在任何
网络请求前原子提交。claim 后：

- allowlist 只有 GET version/job/diagnostic/status 和一个 `POST /api/frame`；
- POST attempt/issued 均必须恰好为 1；
- POST 冲突、超时、响应丢失或任意不确定异常均写 `UNKNOWN_DO_NOT_RETRY`；
- 不存在 retry、recovery、cancel、reset、serial 或 power-control 路径；
- 同一 action 的 claim 不能删除、覆盖或重新消费。

10 个非根 action 递归嵌入并同时绑定紧邻 prior 的：

1. finalized bundle whole-file SHA-256；
2. finalization whole-file SHA-256；
3. P0 result whole-file SHA-256，且 result 必须是 `PASS`；
4. live prior raw job/diagnostic 必须逐字段等于 stored prior；
5. target job/op 必须分别是 prior 的 next-nonzero-u32。

人工 finalizer 要求一份单独 operator observation 和真实 fixed-camera capture 文件。它将
原始 capture bytes 原样复制并核对 SHA/图像解码，强制相机 body/lens/mount、固定曝光、
crop/ROI、illumination 与 runtime manifest 一致；同时强制外置 panel-location 温度传感器、
校准、测点、U95，电表和 clock 资产一致。内部 ESP32 温度和 SWC temperature 不可用且禁止
推断 panel 温度。

每个 result 目录最终包含：

- `N8-RUNTIME-MANIFEST.json`
- `REVIEWED-LIMIT-PROFILE.json`
- `ATTEMPT-LOCK.json`
- `N8-ACTION-EVIDENCE.json`
- `N8-ACTION-OBSERVATION.json`
- `N8-ACTION-FINALIZATION.json`
- `P0-ACTION-RESULT.json`
- `N8-CAMERA-CAPTURE.bin`
- `N8-FINALIZED-ACTION-BUNDLE.json`
- 非根 action 另有 `N8-PRIOR-FINALIZED-ACTION-BUNDLE.json`

## CLI 模板

工具路径：

- compile/schedule：`tools/g1_s1_n8_carryover_campaign.py`
- frozen execution/deep validator：`tools/g1_s1_n8_execution_contract.py`
- describe/run/finalize：`tools/g1_s1_rc2g_n8_once.py`
- deep-bundle analyzer：`tools/g1_s1_n8_analyzer.py`

下列均为模板，`<...>` 必须换成当晚已审核的真实值。不要在白天预先运行 run 模式。

### Describe（零 claim、零网络）

```powershell
python tools/g1_s1_rc2g_n8_once.py `
  --action <ACTION_KEY> `
  --describe-only `
  --runtime-manifest <N8_RUNTIME_MANIFEST.json> `
  --evaluated-at <RFC3339>
```

非根 action 追加：

```powershell
  --prior-bundle <PREVIOUS_RESULT_DIR/N8-FINALIZED-ACTION-BUNDLE.json>
```

### Run common 参数

```powershell
python tools/g1_s1_rc2g_n8_once.py `
  --action <ACTION_KEY> `
  --runtime-manifest <N8_RUNTIME_MANIFEST.json> `
  --evaluated-at <RFC3339> `
  --result-dir <NEW_EMPTY_RESULT_DIR> `
  --base-url <ESP32_BASE_URL> `
  --authorization-confirmation <EXACT_ONE_ACTION_CONFIRMATION> `
  --start-external-temperature-c <MEASURED_PANEL_LOCATION_C> `
  --confirm-reviewed-panel-and-build `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-external-temperature-instrument-verified `
  --confirm-fixed-camera-ready
```

Fresh-root MAP 再追加：

```powershell
  --confirm-controller-fresh-boot
```

Warm dynamic-root MAP 再追加（不能追加 fresh-boot flag）：

```powershell
  --confirm-controller-idle-no-inflight-job `
  --confirm-supervised-continuous-session-start
```

任意非根 action 再追加：

```powershell
  --prior-bundle <PREVIOUS_RESULT_DIR/N8-FINALIZED-ACTION-BUNDLE.json> `
  --confirm-prior-screen-fidelity-pass `
  --confirm-esp32-not-restarted-between-actions `
  --confirm-no-j2-disconnect-between-actions `
  --confirm-no-panel-power-cycle-between-actions `
  --confirm-no-other-visible-refresh-between-actions
```

### Finalize（不产生第二次刷新）

```powershell
python tools/g1_s1_rc2g_n8_once.py `
  --action <SAME_ACTION_KEY> `
  --finalize `
  --result-dir <SAME_RESULT_DIR> `
  --operator-observation <OPERATOR_OBSERVATION.json>
```

### Analyze（只读 finalized bundle；零设备 I/O）

```powershell
python tools/g1_s1_n8_analyzer.py `
  --bundle <BUNDLE_01.json> `
  --bundle <BUNDLE_02.json> `
  --bundle <...repeat in any order for available unique actions...>
```

Analyzer 会按 frozen sequence/ordinal 重排，但拒绝 duplicate/replay、非连续 prefix、异常后
动作、断裂 prior SHA、相机 capture/capture-evidence 重放或测量资产变化。ABA 只比较同一
固定曝光/crop 下 A1 与 A2，B 明确是 A2 的直接显示历史，MAP 只是 primer。

## 上机前硬 blocker

代码已经完成，但真实 runtime manifest 不能用 test-only 值。至少还要由用户/供应商证据
提供并审核：

- 厂商累计/session/consecutive 最大 visible refresh 次数；
- minimum interval、session cooldown；
- start temperature 最低/最高值、post/session maximum temperature；
- supplier limit document SHA 与 reviewer/review artifact；
- 实物 panel serial 和 panel-instance binding SHA；
- 当前 exact firmware build binding SHA；
- 外置温度 sensor、calibration、panel measurement location、U95 与证据 SHA；
- fixed camera body/lens/mount/exposure/crop/illumination 资产 SHA；
- electrical meter 与 timing clock 资产 SHA；
- 厂商定义且互不重叠的 low/nominal/high 温区；
- 每个 action 前更新后的 profile usage snapshot；
- 当次外置温度、3.3 V/CV/电流/温度/物理 cutoff、相机就绪和 action-specific 人工确认；
- 非根 action 的紧邻 prior finalized PASS bundle。

缺少任一项，describe 必须保持 blocked。不得用默认 unbound manifest、内部温度、估算温区、
伪造 supplier limit 或 test fixture 上机。

## 验证结果

专项命令：

```powershell
python -m unittest `
  tests.test_g1_s1_n8_campaign `
  tests.test_g1_s1_rc2g_n8_once `
  tests.test_g1_s1_n8_analyzer -v

python -m ruff check `
  tools/g1_s1_n8_carryover_campaign.py `
  tools/g1_s1_n8_execution_contract.py `
  tools/g1_s1_rc2g_n8_once.py `
  tools/g1_s1_n8_analyzer.py `
  tests/n8_bundle_fixture.py `
  tests/test_g1_s1_n8_campaign.py `
  tests/test_g1_s1_rc2g_n8_once.py `
  tests/test_g1_s1_n8_analyzer.py

python -m compileall -q `
  tools/g1_s1_n8_carryover_campaign.py `
  tools/g1_s1_n8_execution_contract.py `
  tools/g1_s1_rc2g_n8_once.py `
  tools/g1_s1_n8_analyzer.py `
  tests/n8_bundle_fixture.py `
  tests/test_g1_s1_n8_campaign.py `
  tests/test_g1_s1_rc2g_n8_once.py `
  tests/test_g1_s1_n8_analyzer.py
```

截至本交接：campaign 11/11、fixed runner 10/10、deep-bundle analyzer 11/11，合计
**32/32 PASS**。15 个 action 至少一次完整走过 production runner + mock HTTP + manual
finalizer + recursive deep validator；测试耗时已通过 module-level canonical chain cache 和
canonical-byte replay cache 收敛，tamper 会因 bytes 改变而重新验证，不会复用旧结论。
