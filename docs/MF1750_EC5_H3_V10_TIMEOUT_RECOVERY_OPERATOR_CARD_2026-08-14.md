# MF1750 EC5 H3 V10 诊断超时恢复操作卡

日期：`2026-08-14`  
状态：`OFFLINE PLAN ONLY / OLD ATTEMPT TERMINAL / NEW ATTEMPT NOT AUTHORIZED`

本卡只定义下一次诊断怎样重新取得资格；它现在不授权访问 COM、USB、RESET、设备网络、
刷写、J2 或屏幕。C/C-white/T/T-white 的后续顺序仍见
`docs/MF1750_EC5_H3_C_FIRST_OPERATOR_CARD_2026-08-12.md`。

## 已永久终止的 V10 尝试

- authoritative V10 C 已在 J2 OFF 下只写应用区并独立 verify PASS：BIN
  `f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e`，
  794080 bytes，范围 `0x10000--0x0d1fff`；NVS、bootloader、partition 未写，屏幕未刷新。
- 旧诊断输出固定为
  `.test-output/hardware/MF1750_EC5_H3_C_FIRST_LIVE_20260814_V10/c-j2-off-diagnostic.json`：
  1523 bytes，file SHA-256
  `fe9882799f10112adad7b2492dc3cf874afbf2486a7554cdc747b56468c9b95e`，canonical
  `92dfa7882d590489f8ae86d6e574d193b2a66192f4b76d3bb91b8ec050ebab61`。
- 旧尝试在主机发起第一个 `/version` GET 的 opener 调用中超时；调用链没有到达后续
  `manifest/status/report` 三次 GET，也没有证据证明该报文实际到达设备。结果已是
  `TERMINAL_PRECLAIM_FAILURE / retry_allowed=false`，且为 0 POST、0 claim、0 mutation、
  0 driver、0 refresh。
- 该 output、该 boot、该 base URL 和该 attempt 均永久终止。不得换 output 路径重跑、续发后三个
  GET、在另一地址“补测”、自动 recovery、profile switch 或 autochain。

## DHCP 根因线索与证据边界

- V10 源码调用 `WiFi.begin(...)` 后等待 DHCP；没有 `WiFi.config(...)` 静态地址设置。
  因此历史地址 `192.168.1.14` 不是固件合同，也不能在新 boot 后默认沿用。
- 离线审计当时的本机 ARP cache 把精确设备 MAC `a4:cb:8f:d9:fc:d4` 映射到
  `192.168.1.7`。这只是候选：ARP 可陈旧、可被重新分配，也不能证明该地址当前运行已验 V10。
- `.7` 不是授权地址；现在不得 ping、GET、扫描、探测或访问 `.7`、`.14` 或任何其他候选。
- 当前最强解释是旧 `.14` 的 DHCP lease 已变化，但在新的、受控的 identity 响应取得前只能称
  “根因线索”，不能宣称根因已由设备证明。

## 新尝试取得资格的全部条件

以下各项必须同时满足；缺一项即保持离线：

1. 新版本化 recovery plan 必须逐字节绑定上述旧失败 evidence、V10 release、BIN/ELF、设备 MAC，
   并声明旧 attempt 永不重开。
2. 用户另行 fresh 确认 `J2=OFF / 屏幕干净全白 / 3.3 V CV / exact 25.0°C /
   1.0 A 限流 / 当前电流 / 电流与温度监测及物理切断就绪 / 未刷新未改线`。
3. 用户另行明确授权一次新的 boot，以及该 boot 所需的精确 USB/RESET/COM 身份步骤；本卡本身
   不授权这些动作。新 boot 后必须重新匹配 ESP32-S3 和 MAC
   `a4:cb:8f:d9:fc:d4`，不得继承旧 boot identity。
4. 只选择一个 base URL，并先以路由器 DHCP lease 等独立证据把该地址绑定到 exact MAC；旧
   `.14` 和 ARP `.7` 都不能自行升级为最终地址。不得做网段扫描或轮询多个候选。
5. 新尝试使用全新、预先不存在的唯一 output 路径，并在网络前绑定旧失败 evidence 和新 plan；
   不得覆盖或改名复用旧 output。
6. 用户在看到新 plan、exact base URL、new-boot identity 和 exact output 后，另行授权一次诊断。
   授权必须限定为 `version → manifest → status → report` 最多四次只读 GET、0 POST、0 claim、
   0 mutation，且禁止 retry。

已验证的 V10 应用区可以作为新 plan 的候选前提，但“已有 verify PASS”不授权重新刷写；若新
plan 要求 reflash，必须把它列成另一项明确动作并另行授权。默认恢复路径是新 boot 后重新取得
诊断身份，而不是自动重刷。新 boot 的 `/version` 必须精确匹配 V10 release/profile/build；它是
实际启动固件的在线证明。若 bootloader 选择了其他 OTA slot，该校验应直接失败并永久停止，不能
用“app0 已 verify”替代 active-boot 证据。

## 获得未来授权后的唯一诊断边界

新授权只允许向已绑定的单一 base URL 运行一次冻结 runner。runner 最多按固定顺序读取
`version/manifest/status/report`；任一请求超时、非 HTTP 200、JSON/identity/boot/profile/
manifest/status/report 不匹配，均立即形成该新 output 的 terminal failure，不得换地址、换输出或
重试。全过程仍为 J2 OFF，且不得发送 POST、claim、ARM、EXECUTE、driver 或刷新。

即使四次 GET 全部验证 PASS，也只恢复到 `J2-OFF DIAGNOSTIC PASS / VISIBLE NOT AUTHORIZED`。
之后打开 J2、实时电气复核和 C atlas 可见 action 仍分别需要新的人工动作与 one-shot 授权，绝不
从诊断自动承接。

## 历史 V8 事实纠正

V8 的 `device version profile is absent` 不是 GET1 网络失败。冻结 runner 的 `_read_preflight()`
先按顺序收集 `version/manifest/status/report` 四个 GET，随后才调用 `_expect_version()`；所以该
错误表示四个只读响应已经收集，而后在本地校验 `/version.profile` 时 fail-closed。V8 仍然是
terminal、superseded 且不可复用；此纠正只修复请求计数和失败阶段，不恢复任何授权。

## 当前唯一动作

保持 J2 OFF，保存旧 evidence，仅离线构建和验证新 recovery plan。没有新的逐项现场确认、
new-boot 授权和单次诊断授权前：不访问设备、不触碰 USB/COM/RESET、不刷写、不刷新。
