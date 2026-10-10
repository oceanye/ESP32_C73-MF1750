# MF1750 阶段三测试总结与跨 profile 局部 HOLD 计划

日期：`2026-08-24`  
状态：`CROSS-PROFILE PARTIAL-HOLD LIVE 5/5 COMPLETE / FIXED A→B→A COEXISTENCE PRELIMINARY PASS / EDGE QUALITY OPEN`

## 1. 结论先行

今天取得了两个互补但尚未合并的结果：

1. **同一 runtime-LUT profile 内的局部累积 HOLD 初步通过。** 黑、蓝、绿三个不相交矩形可以依次局部刷新；刷新后一区域时，已完成区域没有跟随闪烁，最终三色同时保留。
2. **全屏 A→B 跨 profile 历史依赖为阳性。** A profile 建立的源行历史在切换到 B profile 并写入目标列后，没有全部塌缩为八条均匀目标色带；红/粉、黄绿/橄榄等区域仍能看到源历史分段。再执行一次完全相同的 B target 刷新后，部分分段仍可见。

尚未完成的关键门槛是：**先用 A profile 在区域 A 取色，再切换到 B profile，只刷新区域 B，同时让区域 A 真正 HOLD。** 今天的跨 profile 矩阵是全屏刷新，不能替代这项验证。

因此目前不能声称：

- 已发现或标定 `64`、`128` 或 `256` 种新颜色；
- 已证明任意像素、任意颜色或任意 LUT 都能局部保持；
- 已证明两套完整独立 R20 LUT 可以自由叠加；
- 已经具备 256 色照片渲染能力。

今天支持的工程判断是：**继续构建“跨 profile 切换＋局部 HOLD”路线有明确实验价值。**

## 2. 今天的安全收尾

- AB campaign 最后一项白恢复在设备侧 `COMPLETE`，`campaign_complete=true`、`next_ordinal=6`。
- 操作者确认今天测试结束，并在刷白后关闭上游电源。
- USB 继电器 COM14 / channel 1 已收到 `OFF`，随后独立 `query` 返回 `commanded_state=OFF`。
- 继电器没有独立负载侧电压反馈，因此 `electrical_state_proven=false` 按原样保留；上游断电由操作者报告补充。
- 今天收口后不再访问面板、不刷写、不复位、不发刷新请求；只做离线代码、构建和文档。

## 3. 同 profile 局部 HOLD：repeat-PTLW V3

### 3.1 固件与协议

- build：`MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_2026-08-23`
- boot：`679f614b3864b874`
- BIN：`796496 bytes`
- BIN SHA-256：`81a0e6ac8a106a10338cf7045b185b17d11fa913ce0949893ff6de31cea57da4`
- ELF：`13285792 bytes`
- ELF SHA-256：`e93a57248db0220a528015f78b18a2e5c273866a3e33725649e8d983cd6256a8`
- profile：`LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535`
- PTLW：命令 `0x83`、9-byte 参数、`PMODE=1`、包含式终点 `xe=x+w-1 / ye=y+h-1`
- 局部动作：cropped DTM；PON BUSY 后再次发送 PTLW，再进入 DRF/POF

### 3.2 五个动作

| 顺序 | 动作 | 设备结果 | 人工观察 |
|---:|---|---|---|
| 1 | factory-OTP 全屏白健康锚 | PASS，约 35.014 s | 全白正常 |
| 2 | code3 暗色 PATCH-A | PASS，约 41.969 s | 黑/深色矩形出现，外围白 |
| 3 | code5 蓝色 PATCH-B | PASS，约 41.970 s | 只新增蓝区；原黑区没有跟随刷新 |
| 4 | code6 绿色 PATCH-C | PASS，约 41.970 s | 只新增绿区；原黑、蓝均保持 |
| 5 | factory-OTP 全屏白恢复 | PASS，约 35.013 s | 全白正常、三块清除 |

五个 action 均为 exactly one driver call；PON/DRF/POF BUSY 均出现，`sequence_ok=true`，安全终态 BUSY=1 且 CS/RST 拉低；没有 retry、recovery 或 autochain。

### 3.3 已知缺陷和结论边界

- 黑色矩形底边可见等间距黑白齿状边；蓝、绿底边也不完全干净且间距不规则。
- 该缺陷不否定“旧区域没有跟随下一局部动作刷新”的核心观察，但说明边缘质量仍未达到照片渲染要求。
- 本轮只证明三个固定窗口、三个指定码、同一 profile、这一次动作序列下的保持；不能外推为通用 HOLD。

证据目录：

`.test-output/hardware/MF1750_RUNTIME_LUT_REPEAT_PTLW_20260824_V3/`

动作文件 SHA-256：

- action 1：`cf3b5cc4ebfd3742d400fedd1b7b1df518643e5d7b93e15065569a31a1966ed9`
- action 2：`95331a28ad59994a245fa3063aba78f8a0518467a00093c42ba95f023206c7f4`
- action 3：`584b2a22d3d758de880b07280c90a9629043fb97b64f46289a4f53bd84a53b65`
- action 4：`b208595a1a4eb01f452671cbb79c5ddbfa5f2fc576469c65b1bfec248a46fc47`
- action 5：`d3aa68dbfd966f3dbbe49eb812e379b0691228e33d4703d0c7c8f701805ec4ff`

照片：

- 黑块近照：`photos/2e60839d469ed252e3a3b76711a08c7e.png`，198938 bytes，SHA-256 `0230792a1197c38c51950cb0d0e12dc3e31d91bd0d80558518311955e6451888`
- 黑/蓝累计画面：`photos/64dfbefac0f0ded3d18c2084eb76d8db.jpg`，3676061 bytes，SHA-256 `c115d02150afb608df5f4cb84f627cd24561fdec07348202920cbd804e577a3e`

## 4. A→B 全屏跨 profile 8×8 历史矩阵

### 4.1 上机前修复

原 AB/BA 固件在 J2 OFF 自检阶段被 `compiled_fixture_self_check_failed` 安全拦截，面板没有收到 I/O。根因是 AB/BA 构建错误地使用 uniform/window DTM identity，而实际 fixture 是 packed controller DTM。

修复后：

- AB BIN：`793840 bytes`
- AB BIN SHA-256：`e56649be80b67602d6b1da46e6a0ca1f6ff295e1fa601e9d1b9291902f4573ca`
- AB ELF：`13268060 bytes`
- AB ELF SHA-256：`21acf287ec2c6504418813878decb20dabb6e398e0e2929a7ba806ddbe6f8939`
- BA BIN（仅离线、未上机）：`793824 bytes`
- BA BIN SHA-256：`fc328a5bbb7d723b6b1e4ccc0cacec6c574041f4b67b9dd84c7351fcf18bc646`
- BA ELF SHA-256：`6320735405e07b1ce1f0d8ae39485b8d34b154f7c72be6c75b0793da5e206328`
- regression、定向测试和 Ruff 通过；AB/BA 均重新构建通过。

### 4.2 五个动作与结果

- boot：`315e5dd117432501`
- J2-OFF diagnostic：fixture PASS、NVS fresh、`next_ordinal=1`、0 driver、0 visible refresh

| 顺序 | 动作 | 设备结果 | 可见用途 |
|---:|---|---|---|
| 1 | active profile runtime 白基线 | PASS，46.593 s | 建立统一白底 |
| 2 | active profile 的 8 个 source rows | PASS，46.613 s | 每半屏建立八行源历史 |
| 3 | 切换 commented profile，写 8 个 target columns | PASS，41.894 s | 每半屏形成 8×8=64 个历史格 |
| 4 | 完全相同的 commented target 再刷一次 | PASS，41.882 s | 检查状态是否被第二次目标刷新抹平 |
| 5 | active profile runtime 白恢复 | PASS，46.603 s | 清除矩阵，回到白屏 |

每个控制器有 64 个历史格，两控制器合计 128 个观察格。每格使用单一 3-bit transport code，不是空间抖动。

照片显示：

- target matrix 没有整体塌缩为八条完全均匀的目标色带；
- 红/粉与黄绿/橄榄等区域保留明显的 source-row 分段；
- 完全相同的 target repeat 后，部分分段仍可见；
- 因为照片未经色卡标定、存在斜拍和环境光影响，不能从照片可靠计数“互不相同的单像素颜色”。

这支持 `A→B cross-profile history dependence` 和“部分候选状态在一次相同 target 重刷后仍可见”，但不等于跨 profile 局部 HOLD。

### 4.3 “跨 LUT”的精确含义

本轮常用简称是“跨 LUT”，更精确的技术描述是 **active/commented global-header profile 切换**：

- A：`LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535`
- B：`LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535`
- CS1 的 535-byte R20 前缀始终为 active 版本；
- CS2 的 535-byte R20 前缀始终为 commented 版本；
- R21 固定。

因此不能把 A/B 描述为两套完全独立、所有 R20 内容都不同的完整 LUT。

证据目录：

`.test-output/hardware/MF1750_RUNTIME_LUT_CROSS_PALETTE_AB_20260824_V1/`

文件 SHA-256：

- J2-OFF diagnostic：`89801212d5225b58177c0e1f4f68647138eb80d2f5aceb27525229be18dcae3e`
- action 1：`4d095eb907fc9f5d2c0481d00d8e450407a02e4c00116426dcd81f133ff306c5`
- action 2：`3b093470a35a6e51dca5e81b093ae731f78dfb059d99656b013a8349ddeb11f2`
- action 3：`e713e0c7fe97a2678a807594bcd9e1703f57353902a47e8b60def26850f6e6d2`
- action 4：`92c1e929e76777b1ba41f3cd9f408a60715e3604a36f972ec05ccfc6b5377f8a`
- action 5：`812c6e4d6c2159d8003e49b7fbf6bbe3141bcccc499c0027a3b22dc46eb46d16`

照片：

- source rows：`photos/47092276b32b8bd1a29892d914574a5b.jpg`，146615 bytes，SHA-256 `e92a878bb18d3ed0cbdd3d709bdb55100db19df42c1daf6786ff53831a3328c1`
- target matrix：`photos/92bb33a7ae7ccbfe9b69a4ee8f097986.jpg`，159282 bytes，SHA-256 `2890e23553cccaec48d5c3ce202fd8099c5438ec1387461866317b94b889d829`
- identical target repeat：`photos/91a7d4da88375f04218f5edcbe99aa0c.jpg`，81762 bytes，SHA-256 `ff19002aa7d0620228eda36a13e5417f0bd9fcb97d1db2b7d415de66248db034`

## 5. 明天：跨 profile＋局部 HOLD 独立测试

### 5.1 测试目标

将今天两个阳性结果合并：

1. A profile 只刷新 ROI-A；
2. 切换 B profile，只刷新不相交 ROI-B；
3. 检查 ROI-A 是否保持；
4. 再切回 A profile，只刷新 ROI-C；
5. 检查 ROI-A 与 ROI-B 是否同时保持。

### 5.2 固定五动作

| 顺序 | profile / 颜色码 | 窗口 | 需要人工判断的核心问题 |
|---:|---|---|---|
| 1 | factory-OTP white | 全屏 | 是否全屏干净白；否则停止 |
| 2 | A / code5（高置信蓝） | A=`(48,64,160,120)` | 只出现 A，窗口外保持白 |
| 3 | B / code6（预期绿/蓝绿，B profile 实际色待观察） | B=`(304,240,160,120)` | B 出现时，A 是否不闪烁、不灰化、不变色 |
| 4 | A / code3（暗色） | C=`(48,416,160,120)` | C 出现时，A 与 B 是否同时保持 |
| 5 | factory-OTP white | 全屏 | 三块是否全部清除，回到干净白 |

CS1/CS2 使用相同坐标，不做镜像；SPI 保持 `1 MHz`。局部动作继续使用已实测的 9-byte PTLW、包含式终点、cropped DTM、PON 后 repeat-PTLW 和 CDI=`0xFF`。

### 5.3 固件隔离和安全合同

新固件必须使用独立的：

- build tag、test/campaign/contract ID；
- NVS namespace/key；
- action/descriptor ID；
- host claims 与 evidence 目录；
- HTTP routes 或严格 identity discriminator。

每个可见动作必须：

- J2 OFF 下 app-only 刷入并独立 verify；不写 bootloader、partition 或 NVS；
- fresh boot 做只读 diagnostic，确认 fixture、固件 identity、fresh NVS 和零 driver；
- 在 ARM、EXECUTE 和 driver dispatch 三处都要求 raw BUSY=1；host preflight 同样要求 BUSY=1；
- exactly one ARM、one EXECUTE、one driver call；
- PON/DRF/POF 均观察到 BUSY，mapping/sequence/frame identity 正确；
- 安全终态 BUSY=1、CS/RST 低；
- 无 retry、fallback、recovery、autochain；
- 每步停在 `HUMAN_OBSERVATION_GATE`，不自动进入下一项。

动作 3 是核心门：

- A 在 B 局刷后保持，才能记为 `A→B local coexistence preliminary PASS`；
- A 灰化、消失、面积改变、明显变色或窗口外整体变化，记为 `cross-profile HOLD FAIL`，不执行动作 4；
- 严格 NVS campaign 不允许从 `next_ordinal=4` 跳到 ordinal 5。失败后立即将 J2 置 OFF，app-only 换刷独立 fresh-identity factory-OTP containment，再重新接通 J2 执行唯一白恢复；
- 设备 fault-locked 时同样不得在原 campaign 内越过 fault，也不得重放已消费 action。

动作 4 通过后，才可记为 `A→B→A bidirectional three-ROI coexistence PASS`。即使五步全部通过，也只证明局部叠加路线具备工程可行性，不等于 256 色已经可用。

### 5.4 停止条件

出现任一项立即停止并断开 J2：

- 电源限流、异常电流、异响、异味或发热；
- BUSY 非预期、任一阶段 timeout 或 missing assertion；
- 左右控制器失步；
- 窗口外大面积灰化、固定横/纵线、中心接缝异常；
- 已完成区域明显消失或不可逆偏色；
- 两次独立白收容仍不能恢复。

### 5.5 预计时长

五次可见刷新按今天实测每次约 35–47 秒，纯刷新约 3–4 分钟；加上逐项人工观察、拍照和安全门，预计 `6–10 分钟`。该估算不含首次 app-only 刷机、J2-OFF diagnostic，也不含失败后换刷独立 containment 的时间。

## 6. 2026-08-24 真屏执行结果

本计划已经按固定五动作完成，不再属于“明天待测”。主 BIN
`797152 bytes / 7f5870b065b72d865a42bb90887a160940ccfd572576f2fc6c12d652943cd79e`，
同一 boot nonce=`04f47262e8236ded`，最终
`campaign_complete=true / next_ordinal=6`。五个动作均为 exactly one
ARM/EXECUTE/driver，设备端 `COMPLETE`，无 retry、recovery 或 autochain。

人工观察：

1. factory-OTP 白健康锚：全屏干净白；
2. active/code5 ROI-A：蓝色成立；底边仍有间隔线；
3. commented/code6 ROI-B：绿色成立；原蓝色保持，外围仍白；
4. active/code3 ROI-C：黑/暗色成立；原蓝、绿在刷新过程中均未观察到闪烁；
5. factory-OTP 白恢复：三块全部清除，全屏干净白。

据此可以记录：

- `A→B local coexistence preliminary PASS`；
- `A→B→A bidirectional three-ROI coexistence preliminary PASS`。

准确边界仍是：三个固定窗口、code5→code6→code3、
active→commented→active global-header 序列、单次同 boot。它不证明任意 LUT、任意码、
任意窗口、长期保持、跨重启或256色照片能力；A/B 仍不是两套完整独立 R20 LUT。
底边间隔线限制像素级窗口边界与照片质量，但没有推翻本轮旧区域保持的观察，根因继续开放。

证据目录：

`.test-output/hardware/MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_LIVE_20260824_V1/`

结果文件 SHA-256：

- action 1：`37a5cc00650771feffb8c231ed3869a3c42038da35360787581b1392cff5b258`
- action 2：`0dfa71d32536c10e1cc836ae7bc3ec54c1cd4a4c5ce80e4c0c18b76147a827e5`
- action 3：`f98470ab46d80478530c0d737b05a3e0e8b5d28288f3d4a7452a59b1ebce60e1`
- action 4：`706074f1526bd01232152ef4133e76129b40700ed615ef79ea59d3311fc1a773`
- action 5：`0a11c5f3190695c4099116a0fde378d8c20207519b3509cb6aaae34ff71b57ab`

## 7. 实测后的后续路线

核心动作已经通过，后续按发现优先处理：

1. 先完成当前 Blue campaign 遗留蓝矩阵的独立 factory-OTP 白收容；
2. 用全屏8×8同行比较快速发现 active/commented 两个方向的目标色历史明度候选；
3. 只把肉眼明确、格内均匀且 target repeat 后仍保留的候选送入局部 coexistence 映射；
4. 对 shortlist 再做3次重复、5/60/600 s、色卡与局部 HOLD；
5. Endpoint A/B 和底边几何修复可在候选发现之后执行，但在进入照片 palette 前必须闭合；
6. 多轮 profile stacking 仍保持实验性，不宣称已经具备256色照片渲染能力。

BA 全屏方向仍有参考价值，但后续固件应使用 factory-OTP 白锚和白收尾，不能继续把
runtime code7 当作主动白恢复。
