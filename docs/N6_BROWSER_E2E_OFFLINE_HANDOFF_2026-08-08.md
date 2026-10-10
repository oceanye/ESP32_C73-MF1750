# N6 浏览器 E2E 离线移交（2026-08-08）

状态：`PHASE 3 PHYSICAL PRODUCTION SOFTWARE READY / NOT HARDWARE-EXECUTED / FORMAL INPUTS BLOCKED`

## 2026-08-08 Phase 3 当前叠加层

本叠加层取代下方 Phase 2 的 operator 入口，但保留下方内容作为离线浏览器历史证据。当前唯一
production physical operator 是 `tools/mf1750_n6_physical_once.py`，提供
`describe/materialize/serve/finalize/validate`；旧 `tools/mf1750_n6_visible_once.py serve`
已在 claim/联网前永久硬阻断，不得执行。

Phase 3 新增并通过：

- actual panel/RC2G firmware、四类真实 evidence HMAC、deep authority/usage/review/key、三 exact
  token、actual-clock freshness 与 `max(materialized, authority)` schedule gate；
- 从 N5 physical plan、全部 raw observations、标准表、仪器资格、finalized strict-RC2G bundle、
  result dirs 和 reviewer key 全量重建 physical palette aggregate；core-only/self-resealed 输入拒绝；
- 仓库全局 claim-before-network、exact one-shot HTTP driver、最多一条 frame POST；receipt 与 commit
  sidecar 在 HTTP 成功响应前同步耐久落盘；claim 后异常生成 durable UNKNOWN receipt 或固定
  per-claim incident，incident 与 finalize/普通 validate 排他；
- 真实 Chromium physical E2E：四 preview、三 token、claim 先于首个 fake-device request、唯一
  POST、matching job/report、receipt/commit、reload/duplicate/cross-origin/no-recovery 全闭环。

最终聚焦结果为：physical core `12/12`（5 subtests）、operator CLI `7/7`（14 subtests）、真实
Chromium physical E2E `1/1`，Ruff/compile PASS。全部设备请求均指向 loopback fake；零真实 claim、
零 ESP32/面板 I/O、零刷写。精确命令与参数只使用晚间任务板第 8 节和
`python tools/mf1750_n6_physical_once.py <subcommand> --help`；CLI 不接受 caller 提供的时间或计数。

软件闭环不构成硬件资格。真实 N5 measured outputs、formal reviews、limit/runtime、prior PASS、
现场 observation 与逐 action 外部授权未齐时，只能运行 `describe`，不能运行 `serve`。

本阶段已建立真实 Chromium E2E、临时回环应用服务、临时回环假设备，以及与 P0
fixed-action/claim declaration 相连的 N6 离线 manifest/describe，并在 Phase 2 补齐 formal
materializer、真实浏览器一次性执行层、协议回执、人工 finalizer 和深 validator。整个测试未访问
真实 ESP32、串口、GPIO 或外网；只在临时目录对回环 fake device 创建测试 claim，未创建生产
claim、未生成真实授权，也未调用 recovery。

## Phase 2 历史完成结论（operator 入口已被 Phase 3 取代）

N6 后续代码可在白天连续准备完，晚间不需要边测边补 runner。已完成的正式执行表面为：

- `host/application/n6_visible_execution.py`：严格 formal materialization、固定 runtime envelope、
  external authorization/runtime observation 深校验、workspace-global atomic claim、至多一条
  `/api/frame` POST、matching terminal job/report 闭环、UNKNOWN 封口、人工观察 finalizer 和
  finalized bundle validator；
- `app/server.py` + `web/app.js`：真实浏览器必须重新选择 exact source，经 `convert-v2` 后实际
  取回 `source/mapped/final/model` 四张 hash-bound preview，再通过 token、same-origin、local-only
  preflight 和一次性 arm；reload 不能清除已消费 claim 或重新获得提交资格；
- `tools/mf1750_n6_visible_once.py`：`describe / materialize / serve / finalize / validate` 五个
  子命令。没有 direct-run、retry、recover 或 cancel；production claim 根固定为仓库根，CLI
  不能通过替代 workspace 绕过全局 claim；
- `finalize` 与 `validate` 除了深验 receipt/bundle，还重新读取 P0 registry 中真实 claim 的完整
  bytes 和 SHA-256；错 root、缺 claim 或 claim 字节变化全部 fail closed；
- claim exclusive-create 已发生而 write/fsync durability 不明时，生成结构完整、可深验的
  `0 POST / UNKNOWN_DO_NOT_RETRY` receipt，driver 保持 0 调用，UI/status 不会因简化 receipt
  崩溃。该 claim 永久消费，不允许再试。

这表示 **N6 软件就绪**，不表示 N6 真屏 action 已就绪。正式 live 仍缺 N5 complete measured
palette/profile、真实照片 formal artifact review、reviewed runtime/limit、immutable prior PASS、
现场 runtime observation 和当次 external one-visible authorization。上述任一项不能由测试
fixture、配置布尔值或占位 hash 替代。

## Phase 2 固定执行语义

1. `describe` 缺项时返回明确 blockers，缺失 evidence identity 保持 `null`；固定为 0 claim、
   0 authorization、0 network/device I/O。
2. `materialize` 只接受 36/36 complete calibrated measured palette aggregate、完整
   `measured_mixtures / measured_point_cloud_v1` profile、approved exact artifact/runtime reviews、
   当前有效的 reviewed limit profile 和 whole-file-bound prior PASS。物化本身仍不授权硬件。
3. `serve` 是唯一 live 入口。启动 UI 不接触设备；浏览器完成 source/convert/four-preview/
   token/origin/local-preflight/arm 后，enqueue 才进入执行器。
4. 执行器在任何 device GET/POST 前先 exclusive-create 仓库全局 claim；之后才允许固定协议。
   202 只是接收，不是完成；必须取得同一 job/op/frame/mapping/DTM 的 terminal job 和 diagnostic。
5. 全 action 最大 `POST /api/frame = 1`。错 job/report、timeout、网络结果不明、证据 durability
   不明都终止为 `UNKNOWN_DO_NOT_RETRY`；没有第二 POST、自动 retry/recovery 或换目录重跑。
6. 协议成功只到 `PROTOCOL_VERIFIED_PENDING_MANUAL`。操作员必须按真屏 preview、MAP fidelity、
   方向/中缝/残影、电气、电流、温度、ESP32 restart 和 J2 状态提交真实观察，finalizer 才能
   生成终态 PASS/FAIL bundle。UNKNOWN 不允许人工提升为 PASS/FAIL。

## Phase 2 CLI 历史模板（BLOCKED，不执行）

命令模板已同步到
[`MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)
第 8 节。关键边界如下：

```powershell
# BLOCKED historical reference：旧 CLI 只保留证据回放背景
# tools.mf1750_n6_visible_once describe `
  --offline-manifest $N6OfflineManifest --evaluated-at $EvaluatedAt

# BLOCKED historical reference：旧 serve 永久禁用
# tools.mf1750_n6_visible_once serve `
  --manifest $N6FormalManifest `
  --authorization $N6ExternalAuthorization `
  --runtime-observation $N6RuntimeObservation `
  --device-url $Esp32Url --attempt-id $UniqueAttemptId `
  --bind 127.0.0.1 --port 8765 `
  --receipt-output $NewProtocolReceipt `
  --confirm 'ARM MF1750 REFRESH'
```

runtime observation 内的 `application_origin` 必须精确为实际 loopback origin。runner 不打印
device URL；只打印带随机 token fragment 的本地 UI URL。receipt 一出现即独占持久化；操作员
在 UI 看到 protocol evidence 或 UNKNOWN 后按 Ctrl+C 结束服务。所有 evidence 输出路径必须是
现有父目录下尚不存在的新文件。

## Phase 2 测试证据

Focused 合并回归为 `13/13 PASS`：

- core formal materialization/claim/protocol/finalizer：9；
- CLI describe/materialize/claim-bound finalize：3；
- 真实 Chromium formal browser chain：1。

Chromium 用例实际经过选图、`convert-v2`、四 preview、allow/local preflight、one-shot arm、唯一
一次 fake-device frame POST、job/report 深闭环、跨源 403、reload 后重复提交 409；最终 fake
device 计数严格为 version GET 1、frame POST 1、job GET 1、diagnostic GET 1、第二 POST 0、
recovery 0、外部请求 0。所有 claim 都在临时 workspace，测试结束随临时目录删除。

Phase 2 synthetic structural fixture（**仅测试，不得上机**）身份为：

| 身份 | SHA-256 |
|---|---|
| offline manifest canonical | `42225c0c762ee0c75e2fb097445124a6581d92e5c2a8b98ed44860b42256f35c` |
| formal manifest canonical | `67e5323ca2d87238e23fc0a4df174a57ed815a58ad9083dac22cdd6c9c555110` |
| formal manifest canonical file | `682d67bdce166a4f56bd5042105fc21910ee69931cd14ed518ba1a9952327879` |
| P0 action | `b4573e67d71ffcced513b49bca5b42262321830925130637f7e34667e45f592f` |
| source PNG | `de011323ba1d1f684810ad67f9883662077ecdf3af5f87b6a331e9335938542c` |
| application report | `829bd9ead8d3fd6ab9c3b5206d6125140ddfb315bc66b186f389ddeb2349e4a6` |
| frame | `aa466ba62acc76f6f93d71351b64f7c50b11005c25e8bc057f522755298c0c09` |

这组身份只证明结构和绑定可复现，绝不是 measured hardware evidence、review 或 authorization。

## 已实跑的浏览器范围

本机环境为 Playwright Python `1.58.0`、Chrome for Testing
`145.0.7632.6`（headless）。真实浏览器执行了以下路径：

- 原始 PNG 通过文件控件上传；浏览器请求体与原文件逐字节一致；
- `/application/convert-v2` 的 preparation 固定为 `purpose=offline_preview`，并由
  服务端重新核对 source SHA-256；
- `source/mapped/final/model` 四张 report-hash-bound PNG 全部下载，浏览器逐张验证
  SHA-256，并显示为 1024×600 的 blob 图像；
- 同一宽图先执行 `contain`，确认上下白边；再执行 `cover`，确认裁切后无白边，且旧
  report 的 preview URL 返回 fail-closed；
- 当前 reference palette 与无 measured gamut profile 的 artifact 始终为
  `offline_verified=true`、`formal_upload_authorized=false`、
  `hardware_tested=false`；
- 显式 allow 后只允许一次 `/api/version` preflight；arm 与 refresh 控件继续禁用；
- 在假设备预装 `202+错 job/report` 与 `network unknown` 两组响应时，对禁用的刷新控件
  双击、推进测试时钟超过 120 秒以及页面 reload 均没有产生 `/api/frame`；reload 会
  清除页面不可见的旧 artifact/arm 状态；
- 无 token、错 token、跨 Origin POST 均返回 403；浏览器路由哨兵确认没有外部请求。

本次完整浏览器用例的设备侧精确计数为：

| 请求 | 次数 | 结论 |
|---|---:|---|
| `GET /api/version` | 1 | 仅在用户显式 allow + preflight 后发生 |
| 首个 `POST /api/frame` | 0 | formal gate 在可见动作前关闭 |
| 第二个 `POST /api/frame` | 0 | 未授权、未发生 |
| `GET /api/job` | 0 | 无已提交 job |
| `GET /api/diagnostic/report` | 0 | 无已提交 job |
| recovery 请求 | 0 | N6 不授权 recovery |
| 外部网络请求 | 0 | 浏览器只允许精确应用回环 origin |

因此，`202`、错 job、错 diagnostic 和 POST 后网络结果不明目前不是“已在浏览器中制造
过真刷新”的结论，而是被正式资格门禁挡住的未来故障注入项。测试没有为进入这些路径
伪造 calibrated/measured provenance。底层 adapter 的 202、错 job/report、网络不明、
arm expiry 与重复提交状态机仍由既有 scripted tests 覆盖。

## N6 manifest / describe

`host.application.n6_browser_campaign` 提供纯离线 API：

- `p0_frame_from_artifact()`：从完整重验证的 `ApplicationArtifact` 冻结 frame SHA/FNV、
  CS1/CS2 mapping 与两路 DTM SHA/FNV；
- `build_n6_offline_manifest()`：建立单 action P0 campaign、未评审 limit profile、浏览器
  矩阵及 workspace-global claim declaration；
- `describe_n6_action_offline()`：只返回 `describe-only` 数据，固定
  `hardware_ready=false`、`hardware_execution_authorized=false`、
  `claim_created=false`、实际 POST/recovery 均为 0；
- `build_n6_visible_abnormality_result()`：若未来已单独授权的首次 POST 出现可见结果不明，
  只允许生成终态 `UNKNOWN_DO_NOT_RETRY`；总 frame POST 只能为 0 或 1，禁止第二 POST、
  retry 和 recovery。

当前 deterministic browser harness fixture（不是硬件候选）的冻结身份为：

| 身份 | SHA-256 |
|---|---|
| source PNG | `c24576bbede29c221b8d5eee7948f95bcf2280a62555d0b75fc3a32ba7a8a9a7` |
| cover frame | `fdcd6f096b050cae9dfe36e026fb04e4880696126230023493d5bb792980af18` |
| application report | `c2240a8ff5e9145e55d297d65498a37528b4507cc14b2e41db32d0dffcd8f494` |
| N6 manifest | `809a0c279d956b643d25315dd775c60612018a458f3ea42fc7283a034f91aeb1` |
| P0 action | `698439c7958ee602e14a2705985e0ad250da4f8d827cf1683ea7c32e12648533` |
| N6 description | `d7e2e84841542f52b83637c6a618d283351e1ffe1c6e8d6f3d2f98c11a04c2ad` |

对应 claim 仅为声明：

```text
.test-output/hardware/.visible_refresh_fixed_action_claims_v1/
698439c7958ee602e14a2705985e0ad250da4f8d827cf1683ea7c32e12648533.json
```

该文件未创建。manifest 不包含 confirmation、token 或可执行授权串。

## 当前硬件阻塞项

当前 describe 明确保留：

- `measured_palette_missing_or_unqualified`；
- `measured_gamut_profile_missing_or_unqualified`；
- `artifact_not_formally_upload_authorized`；
- `runtime_formal_eligibility_closed`；
- limit profile 的刷新次数、间隔、冷却、温度、usage、有效期和 reviewer 均未冻结；
- 当前电气/温度/用户在场及 exact one-shot authorization 未评估。

在这些条件关闭前，N6 不存在可执行真屏 action。后续取得 measured palette/profile 后，
应冻结一张真实照片及其 exact prior，补齐并人工评审 limit profile，再建立独立的受监督
硬件阶段；不得把本 harness fixture 或 claim declaration 当成上机授权。

## 回归命令

```powershell
python -B -m unittest tests.test_n6_visible_execution -v
python -B -m unittest tests.test_n6_visible_once -v
python -B -m unittest tests.test_n6_visible_browser_e2e -v
python -B -m unittest tests.test_application_browser_e2e -v
python -B -m unittest tests.test_application_device -v
python -B -m unittest tests.test_application_server tests.test_application_web -v
python -B -m unittest tests.test_visible_refresh_campaign_contract -v
```

这些命令全部是本地软件测试，不需要改变 J2-P1 状态。
