# MF1750 EC5 H3 C-first 条件式上机排程

日期：`2026-08-16`

状态：`P0+P1 OFFLINE RUNNER REVIEW COMPLETE / SCHEDULABLE / NOT AT EXECUTION GATE / ZERO VISIBLE AUTHORITY`

本页只安排顺序、依赖和硬停止点，不构成任何设备操作授权。创建本页时保持：

- `J2=OFF`；
- 不访问设备网络、COM 或 USB；
- 不 reset、flash、refresh、rewire 或切换 profile；
- 不生成 live authority、authorization token 或 claim；
- 不复用已永久消费的 Phase-A V2 attempt。

用户给出的当前边界是：`可排程、未到执行门`。

## P0 离线完成记录（2026-08-16 09:40 +08:00）

- 新工具：`tools/mf1750_ec5_h3_c_first_stage_b_phase_b_offline_gate.py`，47899 bytes，
  SHA-256=`45282e7f9363583b1ddfa5804350ebd464034502c45e0abad99226ecc953d41b`。
- 新测试：`tests/test_mf1750_ec5_h3_c_first_stage_b_phase_b_offline_gate.py`，15343 bytes，
  SHA-256=`1116e4c25126bb209bd2f50b3bb88755ec13127aed864e2e452ae19b020d1155`；
  最终 `9 passed in 206.05s`，Ruff check/format 与 `py_compile` PASS。
- offline gate：
  `.test-output/offline/MF1750_EC5_H3_C_FIRST_PHASE_B_OFFLINE_GATE_20260816_V1/WF20_25-phase-b-offline-gate.json`，
  12144 bytes，file/ID/canonical=`30e131843d8953d3d9fb958241e49d605d2f4fc198a29cced3ea62fa1a9f6617` /
  `72008beee82f167e461c4d9d87eec068e1aa35a0485425322a5776da7b7f5b82` /
  `45c3f986780f373c0ea13996209044d5ba7de638d85e61ee95476abb2af65a50`；build 与独立 validate
  均返回 `valid=true / execution_ready=false / live_authorized=false / device_io=false`。
- synthetic success：同目录 `WF20_25-success.phase-b-fake-only.json`，15781 bytes，
  file/canonical=`955735357a7458276da6678acee17a6eda415b68b0d218683f3391aff9febd8f` /
  `d2ce9300dbf1fbe0bfd9f2242f4b153e06ba4b7815a8382289b4460d3ca9263a`；仅内存模拟
  `manifest→status→report` 三次 GET，`network_requests=0 / device_io=false /
  success_authorizes_visible_action=false`。
- Phase-A committed `/version` 2448-byte entity 已从 sealed receipt lossless replay，body/canonical
  SHA=`f83519943cafabc2035ff5d4d33b4c918925a2652d4116b133d52be7c3795870` /
  `33ea4e0033485a05032993b278d4b0db9701cf378314ea8f0334654ea5b17e80`；Phase-B 不重复 `/version`。
- planned Phase-B live root、registry、terminal receipt 与 finalization temp 均不存在；没有 production
  authority、challenge、authorization phrase、claim、socket 或设备 I/O。

## P1 runner/envelope 离线完成记录（2026-08-17 07:10 +08:00）

- 新 runner：`tools/mf1750_ec5_h3_c_first_stage_b_phase_b_live_once.py`，111836 bytes，
  SHA-256=`bc3c653962b7c68c79c8419809f293e0ac8857fd2057dcb5ac5056413ac1c8d3`。
- 新测试：`tests/test_mf1750_ec5_h3_c_first_stage_b_phase_b_live_once.py`，12452 bytes，
  SHA-256=`c914d7bc3673a0e50a5c1e09a7ad26e47209593b0f08e97da870837926436338`；
  最终 `7 passed in 145.34s`，Ruff check/format 与 `py_compile` PASS。
- runner review：
  `.test-output/offline/MF1750_EC5_H3_C_FIRST_PHASE_B_LIVE_RUNNER_REVIEW_20260817_V1/WF20_25-runner-review.json`，
  4461 bytes，file/ID/canonical=`07718d1271e984f5dfca58d270b25eff2de185e281b89cfb32f45ad790f4fd6f` /
  `d2c2f034aeff5366d9b094aafd7aaf6b142644cda066144da91c0619fe672f05` /
  `cd8f7f6815c8f71516c0dd89326533537b6110394c52e1f4ed81de6269877bd4`；深验返回
  `valid=true / execution_ready=false / live_authorized=false / device_io=false`。
- 固定 `.7:80 manifest→status→report` 三个新连接；每段 raw HTTP + exact V10 验证 PASS 才开下一段。
  registry O_EXCL、durable output checkpoint 均先于首个 socket；终态走 distinct O_EXCL temp 与同卷
  atomic replace。process-control exception 保留 indeterminate checkpoint，永久不重试。
- 用户的笼统“授权完整给你”反例在 registry/socket 前 fail-closed。production authority、envelope、
  copyable token、planned registry/terminal/temp 仍全部不存在；没有设备或网络 I/O。

P0/P1 已完成 predecessor、三端点、raw evidence、live transport、registry-first、terminalization 与
pre/post-attempt replay。HWA-0 仍被新的 fresh 现场门、随后独立逐字授权以及在任何可见动作前对
未证明 identity/fresh boot 的明确处置阻断；production authority/envelope 只能在 fresh 门内离线物化。

## 当前可排入计划的冻结对象

| 对象 | 已准备状态 | 尚未取得的执行条件 |
|---|---|---|
| C / matched-control V10 | 应用区最后独立 verify PASS；本轮唯一 `/version` GET 得到 exact V10 protocol-response conformance | responder/device identity、trusted IP、fresh boot、active slot 均未证明；完整 J2-OFF diagnostic、J2-ON 电气确认、可见 action exact authorization 均未取得 |
| C-white / matched-control V10 | BIN/ELF 已随 authoritative V10 release 离线封存 | J2-OFF 刷写与 verify、fresh diagnostic、J2-ON 电气确认及独立白恢复授权均未取得 |
| T / WF20 runtime V7 | BIN/ELF 与 C-first facade 已离线封存 | C-leg 必须先完整封存；J2-OFF 刷写与 verify、fresh diagnostic、风险接受、J2-ON 电气确认及独立可见授权均未取得 |
| T-white / WF20 recovery V7 | BIN/ELF 已离线封存 | T 成功证据、J2-OFF 刷写与 verify、fresh diagnostic、J2-ON 电气确认及独立白恢复授权均未取得 |

当前四项真屏进度仍为 `C 0/1 / C-white 0/1 / T 0/1 / T-white 0/1`；未消费的可见刷新授权和 claim 均为 `0`。

## 条件式顺序

```text
P0  离线 Phase-B 合同与门禁审计
 ↓  仅在另行 fresh 现场门 + byte-exact authority 后才能越过
HWA-0  J2-OFF 只读 diagnostic（具体 endpoint/次数由新合同冻结）
 ↓ PASS + 独立可见授权；任何失败均终止
HWA-1  C 单次 atlas
 ↓ 人工观察完整落盘；J2 OFF
HWA-2  C-white 独立刷写/诊断/单次白恢复
 ↓ 干净全白 + 电气正常 + J2 OFF
I0  离线 finalize C-leg、平衡、证据复核
 ↓ 全部 PASS 后才允许准备 T 门
HWB-1  T 独立刷写/诊断/单次 atlas
 ↓ 人工观察完整落盘；J2 OFF
HWB-2  T-white 独立刷写/诊断/单次白恢复
 ↓ 干净全白 + 电气正常 + J2 OFF
I1  离线 finalize pair
```

`HWA` 与 `HWB` 是两个独立上机窗口，不能预先合并授权。即使安排在同一天，也必须在 `I0` 完成后重新取得 T 侧 fresh gate；不得把 C 侧现场状态、boot、diagnostic、token 或 claim 继承给 T。

## 窗口 P0：离线工作（本轮合同层已完成）

1. 以已提交且独立深验 PASS 的 Phase-A V2 terminal receipt 为唯一 predecessor。
2. 为后续只读 diagnostic 定义新的独立 authority、attempt、registry 和 terminal-receipt 合同。
3. 精确冻结 endpoint、顺序、最大 GET 数、raw-response 留存、exact-response replay 和 terminal failure 语义。
4. 强制 `0 POST / 0 body / 0 claim / 0 mutation / 0 visible refresh`，并禁止 retry、fallback、recovery 和 autochain。
5. 先完成 synthetic/fake transport 与篡改回归；production live artifact、copyable token 和 socket 均不得在本窗口产生。
6. 离线审计通过后，只能向用户展示下一道 fresh 现场门；不能自动进入 HWA-0。

Phase-A 的成功分类仅为 `TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE`。P0 不得把它升级为设备身份、可信 IP、fresh boot、active OTA slot、Stage A satisfied 或 Stage B authorization。

## 上机窗口 HWA：C 与 C-white

### HWA-0：只读诊断

- 初始保持 J2 OFF，不先重复刷写 V10 C，也不 reset。
- 必须先有 P0 的离线合同 PASS、fresh 现场完整确认和独立 byte-exact live authorization。
- 任一响应、身份字段、boot/profile/manifest/status/report 或证据写入异常均 terminal；不换地址、不换 output、不重试。
- 只读诊断通过也不自动授权打开 J2 或显示 C。

### HWA-1：C

- 仅在新的可见 action 门明确开放后，由用户手动打开 J2，并实时复核 3.3 V、限流、电流和 exact `25.0°C`。
- C 必须使用 authoritative matched-control V10，不发送 R20/R21；只允许一次 atlas action。
- action 后立即保存协议、电流、温度和逐位置人工观察，再手动关闭 J2。

### HWA-2：C-white

- 先确认 J2 OFF，再另行授权 app-only 刷入 V10 C-white 并独立 verify；不得自动承接 HWA-1。
- fresh diagnostic、J2-ON 电气确认和白恢复 authorization 三者均独立取得。
- 完成条件是全屏干净白、无 atlas/格线/轮廓/色斑残留、电气正常，最终 J2 OFF。

## 中间硬隔离 I0

必须离线完成 C result、claim、diagnostic、人工观察与 C-white 恢复证据的完整重放和 finalization。只有全部 PASS，且 T 的目标温度能与 finalized C 精确匹配到 `0.1°C`，才允许准备 HWB。I0 期间不接触设备。

## 上机窗口 HWB：T 与 T-white

### HWB-1：T

- J2 OFF 下另行授权 app-only 刷入 pinned WF20 runtime V7 并独立 verify。
- fresh diagnostic、风险短语、J2-ON 实时电气确认和 exact visible authorization 必须分别满足。
- 只从 C-first treatment facade 执行一次 H3 atlas；不得调用旧通用 runner 绕过 lineage。
- 完成后保存逐位置色相、明暗、饱和度、均匀性和残影记录，再关闭 J2。

### HWB-2：T-white

- J2 OFF 下另行授权刷入 pinned WF20 recovery V7 并独立 verify。
- fresh diagnostic、J2-ON 电气确认和独立白恢复 authorization 均不可继承。
- 完成条件是全屏干净白、无残留、电气正常，最终 J2 OFF。

## 所有窗口共用的硬停止

出现任一项立即停止并保持或恢复到物理 J2 OFF；只封存已有证据，不自动 recovery：

- 现场条件不完整、改变或超时；
- USB/COM/boot/IP/固件/release/action/manifest/status/report 任一身份不匹配；
- 电流、温度、BUSY、声音、气味、ESP32 状态或画面出现异常；
- output、registry、receipt、claim 已存在或 validator 失败；
- 网络超时、部分响应、UNKNOWN、命令非零退出或持久化状态不确定；
- 前一阶段人工观察或白恢复证据未完整落盘。

排程不等于授权。每次 GET、刷写、J2-ON 和可见 action 都必须在到达对应门时单独展示精确边界，并由用户另行确认。
