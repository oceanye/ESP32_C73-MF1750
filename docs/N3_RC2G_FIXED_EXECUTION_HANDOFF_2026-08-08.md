# N3 RC2G 固定执行层交接（2026-08-08）

## 当前结论

N3 的白天代码准备已完成到固定执行层：exact-plan compiler、一次性 runner、人工
observation finalizer、深 bundle verifier 与只接受深 bundle 的 analyzer 已连通。
当前仍是“软件就绪、真屏未执行”，不代表重复性、顺序效应、画质或硬件已经合格。

本次开发没有访问串口、ESP32、J2 或真屏，没有刷写、重启、联网到设备、创建真实
claim，也没有生成或消费现场授权。

## 决策边界与数量

N3A 的冻结 source 是决策树，不是一条 72-action 可执行 campaign。固定编译器强制：

1. 对 N2P 的 8 个 finalized action 目录重新执行深 analyzer；
2. 四个 primer/target 链、视觉/电气/温度门全部 PASS；
3. 只接受唯一 winner；tie、null 或任一 gate FAIL 均拒绝；
4. 操作者再明确选择 repeat-2、repeat-3 或 repeat-4；
5. 最终 plan 只含一个 winner × 一个 repeat template，即 4、6 或 8 actions。

N3B 不依赖 N2 winner，固定为四个 Williams blocks：16 个独立 session，每个 session
恰好 `own MAP → target`，共 32 actions。四个 block 必须完整执行；上一张 target 不作为
下一张 prior，直接 target carryover 仍留给 N8。

因此 N3 的最低真屏量是 N3A repeat-2 的 4 actions，加 N3B 的 32 actions，共 36 次。
不得把 N3A 的 12 个候选 template 或 72 actions 串播。

## 冻结身份

- source N3A canonical SHA-256：`3bf68ebea4a647b27387adf94fd9a04765a34dad564b7786068a60e21df2d42f`
- source N3A whole-file SHA-256：`9de5648c06aaf1d87c4187a49a5bfe9a6da6dae52e9439f7736c71ec10c5f75d`
- source N3B canonical SHA-256：`bae2a6e874ed45e04e9d42051f1d06e788c3f81f26e98acc33b69fc15ae02483`
- source N3B whole-file SHA-256：`c6e1d79227ba87ba5f0dc2dddce055e82235d6b3806c5911710ec428a2832996`
- 默认、缺测量资产的 N3B exact plan canonical SHA-256：`1fdb1d32513383a34bfd589fe3ef3953619545b335a5078d8342755865f65de0`
- 默认、缺测量资产的 N3B exact plan whole-file SHA-256：`9bbcaddb27b1c4ddc22c898cc38872b3f07935b292710e95098f61c045fcdec8`

默认 N3B plan 只用于复验计划身份和 describe blocker，因 10 个测量资产仍为 null，绝不
可上机。补入已审核资产后会生成新的 sealed plan SHA，但 32 个 source action/frame/job/
prior identity 必须保持冻结不变。N3A plan SHA 必须等 N2 唯一 winner 与 repeat 选择后才
能产生，白天不能预造。

## 工具与证据文件

- source planning/compiler：`tools/g1_s1_n3_campaign.py`
- exact-plan contract + deep bundle verifier：`tools/g1_s1_n3_execution_contract.py`
- exact-plan CLI compiler：`tools/g1_s1_n3_compile_exact_plan.py`
- once runner/finalizer：`tools/g1_s1_rc2g_n3_once.py`
- deep-bundle-only analyzer：`tools/g1_s1_n3_analyzer.py`
- test-only bundle fixture：`tests/n3_bundle_fixture.py`

每个 action 固定产生：

- `ATTEMPT-LOCK.json`
- `REVIEWED-LIMIT-PROFILE.json`
- `N3-ACTION-EVIDENCE.json`
- `N3-ACTION-OBSERVATION.json`
- `N3-ACTION-FINALIZATION.json`
- `P0-ACTION-RESULT.json`
- target 必须另有 `N3-CAMERA-CAPTURE.bin`
- target finalizer 另生成 `N3-SESSION-OBSERVATION.json`

Target 同时绑定自己 MAP 的 result 和 finalization canonical whole-file SHA-256。Analyzer
只接收 `{map_bundle, target_bundle}` 对，并重新验证 plan、claim、lock、profile、RC2G raw
protocol、人工观察、相机字节、finalization 和 result；没有 loose result/observation 输入。

## 供电与 session 语义

- Runner 永远不控制 J2、物理开关、ESP32 EN、刷机或配置。
- 每个 session 的 MAP 前必须建立 controller fresh boot/job0。
- 普通 N3 session 不要求 J2 cycle；J2 可在 session 之间保持接通。
- 同一 session 的 MAP→target 之间禁止 ESP32 重启、J2 断开、panel power cycle 和任何
  其他可见刷新。
- 只在整场结束、任何异常、刷写固件或改变配置前切断驱动板电源。
- 任一 action 的 workspace-global claim 在第一条网络请求前永久提交；最多一次
  `POST /api/frame`。Claim 后失败是 `UNKNOWN_DO_NOT_RETRY`，没有 retry/recovery。

## Exact plan 编译模板

测量资产 JSON 必须由 `build_measurement_asset_registry()` 产生并补齐以下 10 个非 null
SHA：clock、温度 sensor/calibration/location、camera body/lens/mount/config/crop、照明。

N3B：

```powershell
python tools/g1_s1_n3_compile_exact_plan.py `
  --study n3b `
  --measurement-assets C:\reviewed\N3-MEASUREMENT-ASSETS.json `
  --output C:\plans\N3B-EXACT-PLAN.json
```

N3A 只有 N2 深 analyzer 已能选出唯一 winner 后才允许运行；以下八个目录都必须是
canonical finalized bundle：

```powershell
python tools/g1_s1_n3_compile_exact_plan.py `
  --study n3a `
  --repeat-count 2 `
  --measurement-assets C:\reviewed\N3-MEASUREMENT-ASSETS.json `
  --n2-q1-map-primer-dir C:\n2\q1-map-primer `
  --n2-q1-target-dir C:\n2\q1-target `
  --n2-q2-map-primer-dir C:\n2\q2-map-primer `
  --n2-q2-target-dir C:\n2\q2-target `
  --n2-q3-map-primer-dir C:\n2\q3-map-primer `
  --n2-q3-target-dir C:\n2\q3-target `
  --n2-q4-map-primer-dir C:\n2\q4-map-primer `
  --n2-q4-target-dir C:\n2\q4-target `
  --output C:\plans\N3A-EXACT-PLAN.json
```

## Describe / run / finalize / analyze 模板

先用 exact plan 中列出的 action key 做 describe。N3B 第一条 route 的 key 是
`n3b-b1-p1-q1-map` / `n3b-b1-p1-q1-target`；后续 key 必须从 plan 的
`selected_routes` 读取，不能手填 frame/hash/job：

```powershell
python tools/g1_s1_rc2g_n3_once.py `
  --plan-file C:\plans\N3B-EXACT-PLAN.json `
  --action n3b-b1-p1-q1-map `
  --describe-only `
  --limit-profile C:\reviewed\N3B-BLOCK1-LIMIT-PROFILE.json `
  --evaluated-at 2026-08-08T20:00:00+08:00
```

Live MAP 还需 result dir、URL、start temperature、五项公共确认、fresh boot 确认和现场
逐 action 精确授权串。授权串不在白天 handoff 中生成：

```powershell
python tools/g1_s1_rc2g_n3_once.py `
  --plan-file C:\plans\N3B-EXACT-PLAN.json `
  --action n3b-b1-p1-q1-map `
  --limit-profile C:\reviewed\N3B-BLOCK1-LIMIT-PROFILE.json `
  --evaluated-at 2026-08-08T20:00:00+08:00 `
  --result-dir C:\results\n3b-b1-p1-q1-map `
  --url http://DEVICE `
  --start-temperature-c 25 `
  --confirm '<现场逐action精确授权串>' `
  --confirm-reviewed-panel-build-and-exact-plan `
  --confirm-registered-measurement-assets-present `
  --confirm-supervised-supply-cv-current-normal `
  --confirm-physical-cutoff-available `
  --confirm-single-visible-refresh `
  --confirm-controller-fresh-boot
```

MAP 协议完成后先提交 canonical operator observation，再 finalization。Target run/finish
都必须传同一 session 的 MAP `P0-ACTION-RESULT.json`，并确认中间连续性；target observation
必须提供已注册固定相机的图片和 SHA-256：

```powershell
python tools/g1_s1_rc2g_n3_once.py `
  --plan-file C:\plans\N3B-EXACT-PLAN.json `
  --finalize-observation `
  --result-dir C:\results\n3b-b1-p1-q1-target `
  --observation-file C:\observations\n3b-b1-p1-q1-target.json `
  --primer-result C:\results\n3b-b1-p1-q1-map\P0-ACTION-RESULT.json
```

Analyzer 每个 `--session` 参数依次给 MAP result 和 target result；N3A 传 2/3/4 组，N3B
必须传 16 组：

```powershell
python tools/g1_s1_n3_analyzer.py `
  --plan-file C:\plans\N3B-EXACT-PLAN.json `
  --session C:\results\b1p1-map\P0-ACTION-RESULT.json C:\results\b1p1-target\P0-ACTION-RESULT.json `
  --session C:\results\b1p2-map\P0-ACTION-RESULT.json C:\results\b1p2-target\P0-ACTION-RESULT.json `
  --output C:\results\N3B-ANALYSIS.json
```

## 尚未满足的硬 blocker

- N3A：N2P 8 条 finalized 深链及唯一 winner 尚未形成；repeat 选择也未发生。
- N3A/N3B：10 个测量资产必须完整注册并人工审核，target 固定相机 capture 必须存在。
- 每个 P0 campaign/block 需与 exact panel/build/action allowlist 匹配的 reviewed limit
  profile、最新 usage、有效期、温度、次数、间隔和 cooldown。
- 晚间需逐 action 现场确认 3.3 V、CV、电流、温度、物理切断能力、fresh boot 或
  MAP→target 连续性，并逐 action 明确授权。

## 白天复验

```powershell
python -m unittest tests.test_g1_s1_n3_campaign tests.test_g1_s1_rc2g_n3_once tests.test_g1_s1_n3_analyzer tests.test_repo_contract -v
python -m ruff check tools/g1_s1_n3_campaign.py tools/g1_s1_n3_execution_contract.py tools/g1_s1_n3_compile_exact_plan.py tools/g1_s1_rc2g_n3_once.py tools/g1_s1_n3_analyzer.py tests/n3_bundle_fixture.py tests/test_g1_s1_rc2g_n3_once.py tests/test_g1_s1_n3_analyzer.py
python tools/check_repo_contract.py
```

2026-08-08 最终合并回归为 `51/51 PASS`（130.609 s）；ruff 与 repository contract
通过。该结果只证明离线软件合同，不包含任何真屏或硬件结论。
