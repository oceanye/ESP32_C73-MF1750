# MF1750 EC5 H3 C-first 真屏操作卡

日期：`2026-08-13`  
状态：`V10 OFFLINE READY / DEVICE V8 DIAGNOSTIC-REJECTED / PHYSICAL 0 OF 4 / LIVE AUTHORIZED FALSE`

> `2026-08-14` 当前恢复入口已转到
> `docs/MF1750_EC5_H3_V10_TIMEOUT_RECOVERY_OPERATOR_CARD_2026-08-14.md`。本卡继续保留四阶段
> 总顺序，但其旧设备/端口/刷写状态不得用于当前操作。

## 当前硬停止

用户已在同一现场状态完整确认下面这条门禁，并明确授权刷入：

`J2=OFF；ESP32 USB已连接；屏幕=干净全白；3.3V/CV正常；当前温度=25.0°C；限流/电流/温度监测及物理切断=就绪；自上次白屏后未刷新、未改接线`

随后在 J2 OFF 下仅把 matched V8 C 写入应用区并完成独立 `verify_flash`；该 boot 没有启动刷新。
正式 diagnostic 先收集完 `version/manifest/status/report` 四次 GET，随后才因设备 `/version`
缺失 `profile` 字段而在本地校验中 fail-closed；未产生 POST、claim、driver call 或可见刷新。
根因已在真实固件 JSON 生成函数中修复并形成 matched V10；V9 中间
产物的 JSON 拼接错误在离线测试中发现，未刷入。其后 ESP32 USB/COM8 消失，当前仅见蓝牙
COM9--COM12。因此当前硬停止是：保持 J2 OFF，只重新枚举 ESP32 USB；在芯片 MAC
`a4:cb:8f:d9:fc:d4` 重新匹配前，不刷 V10、不访问设备网络、不生成 token/claim。

端口恢复后，首个动作只允许 app-only 刷 matched V10 C、独立回读校验，再生成该次 boot、该固件
和该温度下的 fresh `4 GET / 0 POST` diagnostic。只有 diagnostic 完整 PASS 后才会通知用户打开
J2；可见 C atlas 仍须 J2 ON 实时电气复核和独立 one-shot authorization，不得自动承接。

## 权威输入

- C/C-white matched release：
  `.test-output/hardware/MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10/WF20_25-release.json`
  - release ID `1cf8307c8906fa3057509c7a4a15bd79156751aa6b27c3f158435fbaa1049e36`
  - canonical SHA-256 `5616bd495c9faf0983c3d361d5d3bea57837c5f5d8a498805cca940ca595b00e`
  - file SHA-256 `a716dac890b3e272144365f51ae1167f6306d4830d841b11d00610ebb2b0698b`
  - host bundle `888ab013b6d3bb4ee8b2b2a87fdc348cb5ac2ce9265396ea5a39c70179416a3c`
  - contract ID `25267914e74b249cc4bd1cc821437ea700a3c41a75140d82862c86357b3a63fe`
  - trace audit ID/canonical `e2ebf082f779f4f61095b81dada2109c714c46e14ccc7020e43538e5492107f3` / `185d111e437de55d33df2fda6c647f33267ed7e571e73374dd22f2f3ed6b877b`
  - C BIN/ELF `f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e` / `27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41`
  - C-white BIN/ELF `6ab18de07ffbf0ad56dbd6861957a42ea15c6cce9e435f790e74df1050cfa51d` / `6aba1ecb5eb339494c20cf51c56137f61d5568a596f644a7862b951cb45ed147`
- T/T-white release：
  `.test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/WF20_25-release.json`
  - release ID `52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e`
  - canonical SHA-256 `91a498788b074c0d8619e666df0e8c96fc8868e6c9fbee024b97ad8ad183d92e`
  - file SHA-256 `323edaf20ddc60e1302b7df7217320ddb19c2c3ab47cad14409888469ec4809e`
  - host bundle `3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0`
  - T BIN/ELF `53d3abf2319761f282c518ebd6fd606f8efdfe0b1a869a1dcf61c04adbdecc06` / `63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df`
  - T-white BIN/ELF `6a50b2bf287f3d6fd688c9cdfa2052ddc7db3d86c2f2ac9157585cdafd0766d2` / `0c8c82c35b46c69742f27a28c6fdce0ac2d003b3b0dd8a8b7b80152a608d9924`
- C-first treatment 入口：`tools/mf1750_ec5_h3_c_first_treatment_once.py`
- 四阶段证据 finalizer：`tools/mf1750_ec5_h3_matched_pair_evidence.py`

matched-control V1--V9 与 runtime V1--V6 均因后续 identity/host source 或 firmware contract
变化而 fail-closed，禁止使用；当前组合是 matched V10 + treatment/recovery V7。旧通用 runtime runner 仍可被流程外直接
调用；操作纪律要求 stage 3 只从 C-first treatment 入口进入，但这不是物理或密码学强制。
V5 已修正文件名温度语义，但 runtime/recovery firmware 仍内嵌旧 contract/action IDs；V6
修正这些固件身份并离线重编译六份映像。随后 compiled identity gate 加固为 ELF 必须包含
当前 contract/action IDs（runtime 还须包含配对 recovery action ID），因此 V6 又因 host source
drift 失效，runtime 与 matched 当时以同一批已修正 BIN/ELF 重封为 V7。随后只修正 C-first 与
matched-release CLI 中误写的旧 `V4` 帮助文字；由于帮助源也属于 host bundle，matched V7 必须
fail-closed，并在**不改变 C/C-white BIN/ELF、contract 或 treatment V7**的条件下重封为 matched
  V8。V8 后来真实刷入时暴露 `/version.profile` 缺失；V9 的首次修复又形成无效 JSON，均已
  superseded。V10 把真实 C++ JSON 合同测试与正确 `profile` 对象一并密封。该链条是 firmware/API
合同修复；V8 的刷写/回读本身成功，但 diagnostic 明确失败，绝不能计作 C 阶段或可见硬件失败。
设备当前最后已知为 V8 C BIN `e70fc3b3...62bb`；V10 尚未刷入，USB/COM8 尚未重新枚举。因此
不能复用 V8 boot/diagnostic；必须从 J2 OFF 重新识别 exact MAC、刷 V10 C 应用区并 verify 开始。

finalizer 对每份 claim 只读取、校验一次，并从同一已验证内存对象绑定 diagnostic canonical。
C-first facade 在 delegate 前再次核对原 treatment release bytes，制作并深验私有逐字节相同
snapshot，再把 snapshot 路径交给 frozen runner。它拒绝原路径在 preclaim 后被替换，但不能
物理阻止有权限的并发进程篡改临时 snapshot；现场仍要求专用受控进程与工作目录。

`WF20_25` 中的 `20/25` 只按 opaque 厂家文件名数字记录；没有一手资料证明它表示
`20–25°C`。当前 C 与 T 的 runtime action 仅允许 fresh observation 精确为 `25.0°C`，依据是
相邻 2020 E2801/E2802 loader 的固定 selector `25`。这是保守的实验护栏，不是厂家温区、
面板/FPL/膜批资格或安全证明；recovery 温度仍只作受监测的现场记录。

## 唯一顺序

```text
0. 等待用户 fresh 确认：J2 OFF、ESP32 USB、干净全白、3.3 V/CV、exact 25.0°C、
   限流/电流/温度监测与物理切断均就绪，且自上次白屏后未刷新、未改接线
1. C：J2 OFF 仅刷 matched no-R20/R21 V10 应用区并 verify → fresh 4 GET / 0 POST
   diagnostic → J2 ON 实时电气确认 → 另行 exact authorization → 单次 atlas → J2 OFF
2. C-white：J2 OFF 刷独立 factory-OTP white → fresh diagnostic → J2 ON 实时电气确认 → exact
   authorization → 单次白恢复 → J2 OFF
3. 断开 J2、完成平衡；离线 finalize C-leg，并物化 non-authorizing treatment gate
4. T：J2 OFF 刷 pinned WF20 V7 runtime → fresh diagnostic → J2 ON 实时电气确认 → exact
   authorization → 经 C-first facade 单次 H3 atlas → J2 OFF
5. T-white：J2 OFF 刷 pinned WF20 V7 recovery → fresh diagnostic → J2 ON 实时电气确认 → exact
   authorization → 单次白恢复 → J2 OFF
6. J2 OFF；离线 finalize pair
```

每个可见 action 都是独立固件、fresh diagnostic、authorization、永久 claim 和一次 invocation。
不得批量授权，不得自动串播；刷写、接线改变和每次 recovery 前先断开 J2。

## 四项可见动作

| 阶段 | 固件身份 | 作用 | 完成条件 |
|---|---|---|---|
| C | BIN `f0ce5e7a...218e` / ELF `27d23a21...d41` | 与 T 保持 factory init、PSR/PWR/PLL/TRES、E9、atlas 和双控顺序，但不发送 R20/R21 | protocol success + 人工画面/电气/温度记录 |
| C-white | BIN `6ab18de0...51d` / ELF `6aba1ecb...147` | 独立 factory-OTP 全白恢复 | 全屏干净白、无残留、电气正常、J2 最终 OFF |
| T | BIN `53d3abf2...cc06` / ELF `63add1a2...91df` | pinned WF20 empirical H3，发送 R20/799 + R21/704×FF | protocol success + 同模板人工画面/电气/温度记录 |
| T-white | BIN `6a50b2bf...66d2` / ELF `0c8c82c3...9924` | 独立 factory-OTP 全白恢复 | 全屏干净白、无残留、电气正常、J2 最终 OFF |

C 并非 strict time-matched：相对 T，每控制器少 1505 个 SPI bytes/edges 和 5 次 cooperative
yield，双控合计少 3010 bytes/edges 与 10 yields。C/T 差异只能归为组合 R20/R21 command
stream 的增量效应；不能进一步证明 opcode、payload、时长、LUT ABI 或安全接受性。

## 必须先落盘的人工观察

每次 action 完成后、进入下一次刷写或 recovery 前，先按同一模板记录原话；不能只填写
`PASS`，也不能根据预期替用户命名颜色：

| 项目 | C 与 T atlas | C-white 与 T-white |
|---|---|---|
| 方向/位置 | 左右半屏实际顺序、上下 8 条/8 格对应位置；如镜像，逐项写清 | 全屏与四边白边 |
| 可见结果 | 每个位置的原始颜色词、相对明暗、是否与相邻位置可辨 | 是否完全净白，atlas、格线、轮廓或色斑是否全部消失 |
| 质量 | 每格内部均匀性、边界清晰度、白边污染、闪烁或异常纹理 | 均匀性、残影、边缘污染 |
| 安全 | action 前后温度到 `0.1°C`、电压/限流/电流是否正常、ESP32 是否重启、BUSY/声音/气味等异常 | 同左，另记最终 J2 已断开 |
| 证据 | 若拍照，保存原图路径、bytes 与 SHA-256；无照片就明确记 `未拍照` | 同左 |

T 完成后必须再逐位置比较 C/T，并把差异拆成色相、明暗、饱和度、均匀性和残影五项；只允许
选择 `VISIBLE_DIFFERENCE_RECORDED` 或 `NO_DETECTABLE_DIFFERENCE_RECORDED` 之一。现有 pair
finalizer 中的固定 observation phrase 只是“详细记录已经另行完成”的操作员声明，本身不保存
上述逐格内容；因此详细记录及其 hash 是当前必须人工保持的证据边界，不能把 fixed phrase
误称为完整视觉证据。

## 每次 action 的硬停止

出现任一项即停止，不生成或复用授权，不发送 POST：

- J2-OFF diagnostic 不是在该次刷入、当前 boot 和当前温度下新生成；
- boot nonce、BIN/ELF、release、action、manifest、GPIO、NVS virgin/ordinal 或 BUSY 不匹配；
- J2 位置、3.3 V、限流、电流、温度或物理切断没有由用户实时确认；
- C/T runtime action 的 fresh 温度不是 exact `25.0°C`，或 T 与已 finalized C 温度不能精确
  匹配到 `0.1°C`；不得把文件名数字解释成可放宽的温区；
- 前一 recovery 未得到干净全白，或结果/claim/diagnostic/人工观察未完整落盘；
- ESP32 重启、连接变化、电流异常、温升异常、BUSY 异常、边界污染或任何意外画面；
- output/claim 文件已存在、命令返回 UNKNOWN、超时或任一 validator 失败。

任何失败都禁止 retry、自动 recovery、autochain、profile switch 或绕过 facade。先物理切断 J2，
保存现有证据，再重新判断是否需要一份新的、另行授权的 recovery。

## 需要用户逐字确认的两个风险入口

- C：`ACCEPT_C1_C8_C_FIRST_NO_R20_R21_CONTROL__ATTRIBUTION_NOT_PROVEN`
- T：`ACCEPT_U1_U7_EMPIRICAL_CROSS_VERSION_RISK__NO_PANEL_FPL_PROOF`

这些短语只表示用户理解对应风险，不是波形有效性、面板资格或安全证明。实际 token 只能在各自
fresh diagnostic 后离线派生，并仍固定 `live_authorized=false`；真正执行还需要 J2-ON 的实时
电气确认和 exact action authorization。

## 当前开始前的只读复核

本次已重新运行 C/C-white matched V10 与 WF20 T/T-white runtime V7 两份 offline validator，二者均返回
`valid=true`；该复核没有设备 I/O、网络 I/O 或可见刷新。它只证明本地软件合同与密封身份，
不是面板、FPL、波形或温度安全资格，也不替代收到当前现场确认后的 fresh diagnostic。

```powershell
python -m tools.mf1750_ec5_h3_matched_control_release validate `
  --release .test-output\hardware\MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10\WF20_25-release.json

python -m tools.mf1750_ec5_runtime_lut_release validate `
  --release .test-output\hardware\MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7\WF20_25-release.json

python -m tools.mf1750_ec5_h3_c_first_treatment_once -h
```

这些命令只验证本地文件，不访问设备。通过它们仍不授权刷写或可见刷新。
