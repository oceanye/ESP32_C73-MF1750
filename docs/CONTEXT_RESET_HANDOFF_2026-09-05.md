# ESP32_C73 上下文重置交接

更新时间：`2026-09-17 07:28 +0800`。先读STATUS顶部；本段覆盖下面历史入口。

## 当前入口：同boot SOURCE保留，MIDDLE离线通过；等待完整底边相机证据

本轮0刷新/0POST/0刷写/0复位/0继电器切换；4GET确认boot `7274e005c8833ca1`、READY/cursor2、累计driver1，relay查询OFF。SOURCE是全屏C7基线，白色不代表明度失败。原宿主超时FAIL_STOP保留；严格终态复核PASS；原宿主未创建claim，不补造。旧SOURCE runner已封存禁用。

新MIDDLE一次性runner已通过8份实际generated native响应校验、38 tests、Ruff；native驱动仍合成。8个历史主/白BIN/ELF哈希匹配，但旧白不适配当前V2。现有固件无需重刷；同boot不得被复位破坏。qualified=0/256。

用户调整相机后主体白场可见，但底边中央被支架挡住，光学HOLD；已请求露出底边。下一唯一动作是指定VID32E4:PID4801只读复拍，通过后fresh绑定同boot和relayON前置，使用当前明确继续测试的授权，仅MIDDLE ordinal2一次后停审。当前pending release为false，未创建MIDDLE claim；不能执行TARGET或白恢复。

[本轮完整结果](../.test-output/hardware/LH1_REBOUND_CONTINUE_20260917_V1/session-outcome.json) · [本轮固定测试规则](MF1750_LH1_REBOUND_V2_MIDDLE_STAGE_2026-09-17.md)

以下为历史交接，冲突以本段、STATUS顶部和原始证据为准。

更新时间：`2026-09-16 00:00 +0800`。当前状态以 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部为准。

## 2026-09-16 00:00 +0800 V2 SOURCE ordinal 1 真屏协议完成，停在光学判读

- V2 app-only 写入/verify PASS；fresh COM8、MAC、IP/MAC 和指定相机均重新绑定。
- 实际完成 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh；boot=`7274e005c8833ca1`，COMPLETE/cursor2，relay OFF。
- 相机回拍被遮挡，光学证据无效；qualified=`0/256`。禁止 ordinal2、重试或刷白。
- 原始目录：`.test-output/hardware/LH1_REBOUND_20260916_V2/LIVE_RUN_R4/`；唯一入口是人工观察并补充整屏光学证据。

## 2026-09-15 21:10 +0800 重新插拔后代码复核发现现场前 HOLD

- 当前电源断开；本轮没有 COM、网络、继电器、相机或设备访问。
- 已修正 host ordinal1 source-review digest 门禁，必须绑定 R4 `close-review-v5.json` SHA=`3bbf1bfffe29bf51eca3f1d876161c4fdd37ec792b9175b250549aa88ed72f84`；23 项相关回归测试通过。
- 现场前仍需补齐：旧 fault namespace 的 native 运行时不变断言，以及 `FRESH_P2_FACTORY_WHITE`/`source_white_observed:false` 与当前 retained clean-white source 的合同语义核对。当前 `qualified=0/256`。
- 在重新插拔后的 retained clean-white 未得到明确确认前，不访问设备。确认后才进入 fresh 枚举和前置诊断。

## 2026-09-14 20:56 +0800 R4 rebound native/host 离线门通过，等待 fresh 设备绑定

- R4 rebound native 审计 PASS：29 protocol cases；另有三帧与 30 条 tuple upload 的逐字节报告。host validator 4 项测试 PASS，均无设备访问、刷写或刷新。
- 新命名空间、R4 白 source anchor 和旧 fault 保留已核对；`qualified=0/256`，`live_ready=false`。
- 下一唯一入口：fresh COM/IP/MAC/boot/camera 绑定后，仅允许 ordinal 1 一次并立即停审；当前白终态不动，禁止 ordinal 2、重试或复用旧 MIDDLE。

## 2026-09-14 20:40 +0800 R4 重绑定 LH1 候选包离线编译通过；仍未现场放行

- 已从本次 R4 白终态生成隔离的 `LH1_REBOUND_20260914_R4` 候选包：contract=`e708592a61a3b90a276cd2b8756bf4fd4ee7583dbc0fbcc729e79adf1fdfadf0`，BIN SHA=`292d66cc6f0b0979d2ef5f4b962c65215ca53de1d7120f5e66ec01a7dfade594`，ELF SHA=`f448d642bf9cd06963a3021e9d8d5fa388c94b659ff1a31c06ad9a16838d9912`。
- 候选固件编译 PASS（PlatformIO，Flash 使用约24%）；源码检查确认新 `lhist_lh1_rebound_v1/cur_lh1_rebound/boot_lh1_rebound`，旧 `lhist_v1/cur_lh1/boot_lh1` 未编译进入；source gate 改为本次 `lh1srcw_v1/used_lh1sw1=2`。旧 R1/R2/R3 编译失败候选均保留，不覆盖。
- native protocol audit 尚未完成，新的 host runner 尚未完成，故 `live_ready=false`；没有刷写、设备访问或刷新。qualified=`0/256`。
- 审计入口：[`audit-v2.json`](../.test-output/offline/LH1_POSTWHITE_LIGHTNESS_CHAIN_AUDIT_20260914_V1/audit-v2.json)；候选包：`.test-output/offline/LH1_REBOUND_20260914_R4/`；准备脚本：[`mf1750_lh1_rebound_chain_v1_prepare.py`](../tools/mf1750_lh1_rebound_chain_v1_prepare.py)。
- **下一唯一入口：** 对 R4 候选执行 native 协议审计并实现/审计对应 host runner；两者通过后才重新建立 COM/IP/MAC/boot，最多执行 source ordinal1 一次并停审。当前白终态保持不动。

## 2026-09-14 20:26 +0800 白终态后离线明度链审计完成；旧链全部拒绝复用

- 白恢复的人工+相机确认已绑定为当前 source anchor：R4 contract=`8746bf27…20eb7f3`、white action=`60e078ff…6a026fad966`、BIN=`ee59e69d…3afd61e2`、ELF=`0352e7f1…d9378402`，white COMPLETE/cursor=2，qualified=`0/256`。
- 对旧 `LH1_LH4_20260912_R1`、fault-white/MIDDLE 及现有 HOLD function-chain 做了离线核对：旧 LH1 仍绑定历史 P2 white action；fault-white 只能 containment；HOLD function-chain 的算法/身份 dry validation PASS 但 source authority 是历史白源、`live_authorized` 不成立。它们都不能直接进入现场。
- 新链要求已封存：保留旧 `lhist_v1/cur_lh1=770` 与 `boot_lh1=30a9e5989873f4e0`，不得清除/覆盖；使用全新 `lhist_lh1_rebound_v1/cur_lh1_rebound/boot_lh1_rebound`，初始 cursor=1；source gate 绑定本次 R4 white `lh1srcw_v1/used_lh1sw1=2` 和当前白场证据。
- 离线审计证据：[`audit.json`](../.test-output/offline/LH1_POSTWHITE_LIGHTNESS_CHAIN_AUDIT_20260914_V1/audit.json)。硬件访问=0、mutation=0。当前门 `HOLD_OFFLINE_PREP`，下一唯一动作是生成并原生审计新 rebound LH1 source ordinal1 runner/package；完成前不访问设备。

## 2026-09-14 20:19 +0800 用户与相机共同确认白场通过；白恢复收口，明度链未启动

- 用户确认“我肉眼看干净净白，电气正常”；指定 `VID_32E4:PID_4801` 相机新拍全屏，整块面板均匀白场，未见色块、固定边框、网格或固定线。记录为 `PASS_WHITE_RESTORED_HUMAN_AND_CAMERA`。
- 白恢复实际计数保持：1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh；终态 COMPLETE、cursor=2；relay 最终 OFF；没有 ordinal2、没有 mutation retry、没有主流程 resume。qualified=`0/256`。
- 电源照片同时记录 3.31 V、CV、0.000 A；这是现场记录，不把它当作厂商规格。相机仍是 camera-relative，未标定 Lab，未计算 ΔE76/ΔE00，白场通过不等于明度候选通过。
- 收口证据：[`close-review-v5.json`](../.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/close-review-v5.json)、[`postwhite-optical-review-v4.json`](../.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/postwhite-optical-review-v4.json)。
- **下一唯一入口：** 离线建立新的明度 source/target 链并重新绑定控制器、source state、profile、frame/action、温度与 ROI；现场执行前不得在已完成的 white successor 上继续发动作。明度资格仍为 0。

## 2026-09-14 20:14 +0800 R4 白恢复完成；真屏白场 PASS，停在人工确认，未进入明度

- 用户确认电源为 CV、3.3 V；重新建立 fresh IPv4↔MAC、指定相机和现场前置后，powered idle 读取 `BUSY=1`、`state=ready`、`phase=0`、`cursor=1`，同一 R4 boot=`1b3d3c465436fd75`，ARM/EXEC/driver 计数为0。
- 实际完成独立故障白恢复：**1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh**，终态 `COMPLETE`、cursor=`2`；随后 relay exact-bound OFF。没有 ordinal2、没有 mutation 重试、没有主流程恢复。white 一次性 claim 已按设计永久消耗。
- 后恢复指定 `VID_32E4:PID_4801` 相机显示整块矩形屏幕均匀白场，未见色块、固定边框、网格或固定线；画面同时记录电源 `3.31 V / CV / 0.000 A`。这是 camera-relative 光学筛选，未标定 Lab、未计算 ΔE、未授予明度资格；等待现场人工确认。光学 `HOLD_FOR_HUMAN_CONFIRMATION`，qualified=`0/256`。
- 完整结果：[`close-review-v4.json`](../.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/close-review-v4.json)；原始执行目录 `live-reopen-v2/`，照片 `postwhite-v3.jpg` 与 sidecar，终态 relay OFF。当前屏幕应保持白恢复终态。
- **下一唯一入口：** 用户确认白场干净后，重新建立 fresh source/target 状态并另起明度链；白恢复本身不能直接授予颜色或明度资格，不自动执行 ordinal2，不复用旧 MIDDLE 失败链。

## 2026-09-14 07:40 +0800 用户确认 CV/3.3 V 后复查；BUSY 仍为 0，未发送白恢复

- 用户确认当前电源为 CV、3.3 V。按规则重新建立 fresh IPv4↔MAC，并重新采集指定 VID_32E4:PID_4801 相机；旧绑定/旧相机证据未复用。
- relay ON 后 fresh 4GET 仍返回 `state=ready, phase=0, cursor=1, busy=0, rst=0, cs=0, cs2=0`。因此 R4 固件的 idle-high 前置仍失败，**ARM=0、EXECUTE=0、driver=0、visible refresh=0**。已 relay OFF 并独立确认 OFF。
- 这证明“CV/3.3 V”本身没有让控制器看到 BUSY 高电平；不能把电源模式当作 panel 已上电或 BUSY 链路正常的证明。物理原因未判定，不能绕过保护。
- 当前判定仍为 **FAIL_STOP（BUSY 前置）**，光学 `HOLD_FOR_EVIDENCE`，qualified=`0/256`。本次只读停止证据：[`powered-idle-stop-v2.json`](../.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/powered-idle-stop.json)。
- 下一唯一动作：检查继电器 ON 后屏端实际供电路径/共地及 BUSY 线连续性，确认控制器确实能读到 idle-high，再重新 fresh 4GET；不清 NVS、不重刷、不发送 ARM/EXECUTE。

## 2026-09-14 00:38 +0800 当前唯一入口：R4已刷入，白恢复尚未刷新；relay OFF

已按用户在场授权实际刷入独立 FAULT770 white R4，BIN `ee59e69d…53afd61e2`、新boot `1b3d3c465436fd75`，app-only/verify/单次启动及本boot J2-OFF 4GET PASS。继电器ON后11.425秒BUSY仍0，前置STOP，**ARM/EXEC/driver/refresh均0，white claim未创建**；最终relay OFF。原主FAULT770/boot `30a9e5989873f4e0` 保留；旧SOURCE white R5不适用该fault，禁止据历史条目执行R5。

当前屏幕未刷新，相机近全暗不能判白；等待用户现场电源输出/CV-LVP/电压观察以定位BUSY0。电气仍只记录，操作授权已经存在，不重复询问；不能绕过固件busy-idle-high必要条件。总体 `FAIL_STOP`、光学 `HOLD_FOR_EVIDENCE`、qualified=`0/256`。

唯一下一入口：[本轮完整结果](../.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/session-outcome.json)。外部状态有证据/变化后，fresh绑定并检查当前R4同boot，必要前置通过才执行一次独立white，随后停审；不得自动再ON、默认重刷、清claim/NVS或继续旧MIDDLE。以下全部为历史条目。

## 当前唯一入口：MIDDLE ordinal 2 已停止，设备 fault，等待独立恢复放行

已按用户授权进入真屏：继电器 ON 一次，MIDDLE 仅 1 次 ARM；因错误复用 SOURCE 白源 review，固件 review gate 返回 HTTP 400 `prior_review_cannot_reuse_white` 并进入 `fault_locked`，未 EXECUTE、未 driver、未 visible refresh。随后继电器 OFF 一次并查询确认 OFF；post-fault 相机只读仍为白场。证据目录：`.test-output/hardware/LH1_SOURCE_FIELD_20260913_V3/MIDDLE_ORD2_20260913_V1/`，结果 `session-outcome.json`，qualified=`0/256`。禁止重发 MIDDLE mutation；下一步只能离线生成独立新阶段 review、复核已修正 runner（Build-Tag 从 contract 读取）及独立白 successor R5，然后单独获得恢复现场放行。

## 当前唯一入口：SOURCE1 一次完成后的停止复核

已实际 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`。新 boot=`30a9e5989873f4e0`；第一轮询在45秒撞上同步driver约45.354秒完成及HTTP监听重启，连接reset；原STOP和永久claim保留。独立2次只读GET取得同boot COMPLETE，严格终态PASS；没有重发mutation或伪造原result。最后relay OFF；屏幕近白主体、深边框，尚无明度等级，qualified=`0/256`。

用户明确电气信息只作记录，`electrical_state_proven=false`不再作为本轮控制门，不重复索取电气许可。主BIN/ELF保持LH1_LH4_R1；独立white R5已实际编译/native30场景73JSON PASS，R4原PASS说法已纠正为FAIL_SYNTAX。R5本轮没有执行。

唯一下一入口：[session-outcome.json](../.test-output/hardware/LH1_SOURCE_FIELD_20260913_V3/session-outcome.json)及同目录terminal-reconciliation/transport-analysis。先离线审查补取终态的接纳规则、下一阶段轮询和runner；不得重放SOURCE、清claim/NVS、自动MIDDLE或白恢复。当前source cursor2；后续MIDDLE需同原boot、完整prior review和独立放行，ESP32重启后不能续链。

以下为历史短交接，冲突时以本段及STATUS顶部为准。

更新时间：`2026-09-13 08:47 +08:00`  
当前唯一入口：先读 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部；本条只提供短交接。

## 2026-09-13 08:40 R4 白 successor 与继电器身份更新

R1 白 successor 原生严格审计发现 `profile_id` 重复键，保留为失败证据；隔离 R4 已修复并编译、原生协议审计 PASS（无重复键，正负场景通过），但桌面驱动是合成桩，尚无现场恢复或光学资格。正确 SOURCE1 profile 已通过离线适用性复核。继电器本轮 COM14/CH1 fresh 查询为 OFF；相机重新采集当前白场 1 张（VID_32E4:PID_4801，只读）；用户报告 J2=3.3 V 已记录，测点、GND、仪器和时刻未绑定，`electrical_state_proven=false`。本轮 0 flash / 0 refresh / 0 ARM / 0 EXECUTE，qualified=0。

下一唯一入口：补齐可追溯 J2 外部电气读数并重新 fresh 绑定 ESP32 COM、IPv4↔MAC、boot；刷写后取同 boot J2-OFF diagnostic，前置通过后仅运行 SOURCE ordinal 1 一次并立即停审。

## 2026-09-12 23:28 离线 LH1/LH4 与当前白采集更新

LH1/LH4 R1 包已编译并通过 78 项 host 回归、原生协议审计；新 SOURCE1 runner 只允许 ordinal 1，尚未访问设备。SOURCE1 后独立白候选已编译，但 native audit 明确 host gate 尚缺（MIDDLE/TARGET/FAULT 排斥），`live_ready=false`。指定相机只读 1 次：主体白场可见、右边界未入镜，current-white review=`HOLD_FOR_EVIDENCE`；relay 最后 OFF，`electrical_state_proven=false`，qualified=0。下一唯一入口：四边全入镜复拍、补实际外部电气读数、完成后测白 host gate，再 fresh COM/IP/MAC/boot 与刷写后同 boot J2-OFF；此前不 ARM/EXECUTE。

## 2026-09-12 21:30 W0 已完成，明度需先重新绑定 LH1

最新白恢复 LH4 已完成并由操作者确认“全白，ok”；协议 PASS、relay 最终 OFF，W0 execution review canonical SHA=`2bef73c1340be23cbd9e06a971ecce88f7dd1a79569cb9cf4b6bb5ac5f519179`。本轮只完成一次白 visible refresh，`qualified=0`。旧 LH1 R3 仍绑定旧白 BIN，不能直接启动；唯一下一入口为离线生成新 LH4 source-runner 后，重新做 fresh boot/J2-OFF，再执行 SOURCE ordinal 1 并停审。


## 2026-09-12 08:15 当前唯一明度入口

以 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部及 [`MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md`](MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md) 为准。LH4 白修复 host 的离线完整复核已通过（8 tests、实际 delegate、历史 source gate、旧身份负例；review SHA=`ae54b311d291c04c768a78839cba133737213d6f8b26335f87898bd1c7ac620b`），但现场未刷写/未刷新。当前最后已知屏幕为局部相机中的彩色画面，relay OFF、电气状态未证明，`qualified=0`；用户已允许一次 W0 白恢复并可观察，需先补整屏光学及外部 J2 电气证据。

[`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部最新条目，再回查本文件引用的原始证据。

## 2026-09-11 08:24 相机判定与 SPD1657B Rev 1.1 综合计划

相机只读采集严格命中 `48MP USB Camera / VID_32E4:PID_4801`，照片显示当前屏幕仍为 2×4×8 彩色 atlas；无 relay、SPI、复位、刷写或可见刷新。照片 SHA=`e5ee7650c6d5ae74de15f880e32839e1d5586cb43e6cadfdfb5c3f90fbd02578`，sidecar SHA=`86bd77534b25818010420254b5b71bf629e8e2d95f4f06bf7721d969a53b7286`，retained capture 自动 verdict=`INCONCLUSIVE/low`。已完成 [`MF1750_SPD1657B_V11_COMPLETE_ANALYSIS_AND_LIGHTNESS_TEST_PLAN_2026-09-11.md`](MF1750_SPD1657B_V11_COMPLETE_ANALYSIS_AND_LIGHTNESS_TEST_PLAN_2026-09-11.md)：先协议/电气门，再固定 profile 的 3 级同色相筛选、HOLD、fresh 重建、5/60/600 s 保持，最后才做 PLL/剂量/电压单变量和 5→10 扩展；`qualified=0`。下一唯一入口仍是离线修复 white successor source-main lineage FAIL_STOP。

## 2026-09-11 07:55 白恢复 FAIL_STOP；未产生可见白刷新

重新插拔后枚举 ESP32 COM8，并从串口读到本次实际地址 `192.168.1.4`；fresh exact binding 与 MAC `A4-CB-8F-D9-FC-D4` 通过。继电器 COM14 查询 OFF。已执行一次白 successor app-only 写入/verify/hard reset，BIN 哈希匹配；新 boot J2-OFF 只读 GET=4、POST=0，但 source lineage 校验报 `source_main_offline_build_file_sha256 differs`，因此未 ARM/EXECUTE/driver/visible refresh。证据：`.test-output/hardware/MF1750_WHITE_RECOVERY_20260911_V3/app-only-single-boot-flash.json` SHA=`bd25020cb8c471c6f671530ff5eec803349b9685f8402220371a3b8db1abcac4`；诊断 SHA=`a028bb0b8f772d6d8d6b5f97a02e8a8b6beaa635579d9eb698f23161049cd252`。当前屏幕仍为2×4×8彩色、relay最后OFF、electrical_state_proven=false；下一入口是离线修复 source 封印绑定后重新生成匹配 successor，不得跳过 lineage 校验。

## 2026-09-11 07:05 白恢复前置再次 FAIL_STOP

按操作者要求进入白恢复前置，仅对 `192.168.1.11` 做一次 ICMP/ARP 探测；返回 `192.168.1.6: Destination host unreachable` 且无 ARP 条目，未形成目标 MAC=`A4-CB-8F-D9-FC-D4` 的 exact binding。未发送 HTTP，未切 relay，未刷写、复位或刷新。证据 `.test-output/hardware/MF1750_WHITE_RECOVERY_20260911_V2/live-stop-no-exact-device-binding.json`，SHA-256=`6d3a2c992465b93d143c812d4db80885f33acd1798e6458ecb8d1c67c81020a1`。当前屏幕仍为2×4×8彩色、relay最后OFF、electrical_state_proven=false；下一入口是网络恢复后重新做 fresh exact binding。

## 2026-09-11 06:38 明度算法/固件离线完成

明度历史算法和独立三动作固件已封印在 [`LH1_20260911_R3`](../.test-output/offline/LH1_20260911_R3)，合同 ID=`b63695f21ca56f3dbb45998ad3c88c790b5eed121513fa188c26b40a237990ac`；BIN SHA=`369c952a970fc1d9313602ffb4dd10ceac6534a486c399bf30bf40d2b0de00d1`，ELF SHA=`84f4191fcb212ef4de2c1e14571f7d6b96f91429e81d481640fc5f3e3eeceb4a`。算法为 SOURCE(active/C7)→MIDDLE(commented/M0…M7)→TARGET(active/T3/T7)，16配方×两控制器×四象限；等级数3/5/10与刷新次数分离。PlatformIO、49项 Python 回归、29个 C++ 协议场景、3帧逐字节比对和30条双控制器 tuple 写入均 PASS。全程无设备访问/刷新，`qualified=0`。

固件启动不刷新，三步分别 ARM/EXECUTE，游标和 boot/run/review/profile/frame 哈希不一致即锁定；white successor 的 NVS 值只作必要前置，不是光学或电气证明。现场最后仍为2×4×8彩色、relay OFF、electrical_state_proven=false、NO-GO。下一次只从 fresh white 和当次 exact IPv4↔MAC/COM/boot 绑定开始；刷写后先取同 boot J2-OFF diagnostic，获放行后最多执行 ordinal 1 一次并停住。

## 2026-09-11 02:49 white successor 前置停止

操作者要求从当前彩色 atlas 刷白。本轮重新枚举 relay 得到当前 `COM14 / USB\\VID_1A86&PID_7523\\5&230B5917&0&4 / Port_#0004.Hub_#0001`，只读 OFF；未继承历史 Hub_#0002。对白 successor 只做一次 fresh `192.168.1.11` ICMP 探测，超时且 ARP 为全零，没有 exact IPv4↔MAC 绑定，所以 `FAIL_STOP`，没有 relay command、flash、reset 或 visible refresh。证据见 `.test-output/hardware/MF1750_WHITE_RECOVERY_20260911_V1/live-stop-no-exact-device-binding.json`；下一入口是恢复当前 ESP32 网络后重新建立 binding，再从 relay OFF 开始。

## 2026-09-11 02:36 明度测试已建立；先读本条及STATUS顶部

已实现 [`MF1750_LIGHTNESS_TEST_V1_2026-09-11.md`](MF1750_LIGHTNESS_TEST_V1_2026-09-11.md) 对应的离线CLI `tools/mf1750_lightness_test.py`，支持create/review-p2/analyze；31 tests和Ruff通过。最终包 `.test-output/offline/MF1750_LIGHTNESS_TEST_20260911_V1_R3/` 含128格空白测量、三动作原始记录、3/5/10生命周期证据槽与冻结判据。路线C7→M0…7→T3/T7，三次独立可见动作逐次审查；每target只有8配方，10阶须另增不同配方。照片/位置/fresh重建次数不能算等级。

新判据ΔL*≥2、ΔE00≥3、hue≤5°，四位置P95 |ΔL*|≤3和ΔE76≤5，要求所有象限与整条链通过；这是新离线实验口径，不覆盖旧L*≥8粗筛或现场门禁。HOLD、fresh-white重建、保持、双controller匹配和资格审核尚未通过，qualified=0。

P2历史42文件哈希全部匹配并重判：两侧无通过的三阶链；CS1 code1/7位置依赖，CS2 code1↔7确有中位数ΔL*=12.575659，但TR hue=5.031439°略超实验5°，保留边界候选，不说完全没有明度差异。报告 `.test-output/offline/MF1750_LIGHTNESS_TEST_P2_REVIEW_20260911_V1_R3/p2-screen-report.json`。闭环 [`execution-review.json`](../.test-output/offline/MF1750_LIGHTNESS_TEST_20260911_V1_R3/execution-review.json)，canonical SHA=`87e140ef6d1e09ca77394e2e24c2ae96864621f94da6b0bc34d4e9f1c321f355`，绑定主/白10项产物复核和实际验证输出；不宣称旧主source seal整体PASS。

本轮0设备访问/0刷新，屏幕仅最后报告2×4×8彩色，relay仅最后OFF、electrical_state_proven=false、现场NO-GO。下一次唯一入口为新测试说明第6节/R3包：PWR=0F、PLL=08、OTP单参数PWR来源已追到本地样例/loader，模式适用性仍需离线审查，再封印适用于当前彩色source的独立white恢复入口。离线已授权；未获新现场恢复放行。不得直接运行旧V3、继承white/COM/IP/boot或自动刷白；刷写后必须新boot同次J2-OFF diagnostic。

## 2026-09-10 20:56 SPD1657B Rev 1.1 资料增量审查：帧率语义明确，LUT phase 仍 OPAQUE

已完成新增 SPD1657B_1.1.pdf 的本地审查，详见 [`MF1750_SPD1657B_V11_DATASHEET_REVIEW_2026-09-10.md`](MF1750_SPD1657B_V11_DATASHEET_REVIEW_2026-09-10.md)。芯片REV与历史0x04相容；R30解释 active/P1的02为名义43 Hz、commented/P2的03为名义50 Hz，但LUT与电压也变了，不能宣称帧率已产生明度。R20/R21内部格式仍缺失，Gray索引不等于明度等级，PTLW不是零电场HOLD证明。

已封存PDF哈希、原文提取、关键页渲染、源码对照和10项主/white产物匹配，证据：`.test-output/offline/MF1750_SPD1657B_V11_DATASHEET_REVIEW_20260910_V1/datasheet-review-evidence.json`，canonical SHA=`aef9c9afb1daf06541dadf61626e16382561ec2bee382455e8ea979dc1ab2874`。新发现 runtime PWR=0F固定位、公共PLL=08、OTP PWR参数数量的文档/实现差异，下一次先做它们的定点离线来源与顺序审查；white successor也需纳入，不能只拿旧文件seal代替语义核查。未改任何固件或合同，未实现新软件门禁。

本轮设备访问/刷新=0，qualified=0。屏幕/relay今天未观察或查询，最后为2×4×8彩色/OFF，electrical_state_proven=false，现场NO-GO。资料研究不授权白恢复，不重复要求彩色atlas提供clean-white确认。

## 2026-09-07 00:40 离线继续核对

已重新核对四份 retained/reentry 证据和 P2 action/固件封印；独立记录为 [`offline-continuation-verification-20260907.json`](../.test-output/offline/MF1750_P2_RETAINED_ATLAS_REENTRY_20260906_V1/offline-continuation-verification-20260907.json)，canonical SHA=`715ac4665a0046c88efaff77e391f761db853c4bc8dd5234dc1b33d555f5e66b`。针对性回归 `30 passed`，Ruff PASS。全程没有 COM、网络、相机、relay、刷写、复位或刷新；屏幕仍是 2×4×8 彩色 atlas，relay 最后 OFF，`electrical_state_proven=false`，`qualified=0`。下一入口仍是等待明确放行一次独立 P2 white successor 恢复。

## 2026-09-06 08:36 当前彩色 atlas 与恢复入口

操作者明确报告 **“当前是2x4x8 彩色”**。这是 retained atlas，不是白屏；不能要求操作者在未恢复时提供 clean-white 确认。今天没有设备访问，relay 仅最后记录 OFF、`electrical_state_proven=false`，刷新=0、`qualified=0`。下一步是单独放行 **P2-C white successor 一次恢复**，不是直接执行历史 V2/V3 明度固件。恢复放行尚未取得；布局观察不构成恢复授权。

前置材料位于 `.test-output/offline/MF1750_P2_RETAINED_ATLAS_REENTRY_20260906_V1/`。离线深校验发现并修正 host 对 HTTP 的误判（原来全要求200；封印固件是 GET200/ARM201/EXECUTE202）；原始日志不变，深校验通过，30 tests PASS。旧 source seal 因 host 哈希变更仍不匹配，使用独立 `host-http-status-validator-amendment.json` 明确记录这项修正；其 file SHA=`e14403616703c12280bf77d8585fe8fdca1e7d92db9d5d9bca5abe38a92b9c9e`。其余 authority sources、主/白固件和合同一致，white 独立 audit PASS。详细恢复顺序与哈希见 STATUS 顶部；写入之后必须新 boot 的 J2-OFF diagnostic，不能复用上轮诊断。恢复后停住做白屏审查，不自动继续明度。

## 2026-09-05 15:26 明度 waveform 离线研究入口

本轮新增两份不访问硬件的研究材料：[`MF1750_LIGHTNESS_WAVEFORM_RESEARCH_2026-09-05.md`](MF1750_LIGHTNESS_WAVEFORM_RESEARCH_2026-09-05.md) 汇总本地证据、公开论文、E Ink/相邻芯片资料；[`MF1750_LIGHTNESS_WAVEFORM_EXPLORATION_2026-09-05.md`](MF1750_LIGHTNESS_WAVEFORM_EXPLORATION_2026-09-05.md) 固化当前芯片的明度机制排序。当前首要目标是彩色同色相明度，灰度只作为中性轴特殊子集。最有信息量的下一步离线入口是 source/middle recipe 的 Latin/四象限置换与位置解混；不能把已有行效应直接叫明度。完整 endpoint、history recipe、HOLD、fresh-white reconstruction、剂量阶梯按顺序推进；runtime LUT/R20/VCOM/电压/中断继续阻断。现场仍保留 P2-C atlas，relay OFF、`electrical_state_proven=false`、`NO-GO`、`qualified=0`。
相关离线回归已通过 `25 passed`；没有生成新固件或访问现场。

## 2026-09-05 15:50 离线合同复核入口

V2/V3 position-balanced runner、V2 独立 white successor 和 red/pink recipe permutation 的 `dry-validate` 均 PASS；均为 offline-only，没有 COM、网络、相机、relay、刷写、刷新或 claim 消费。下一次明度现场若获单独放行，只能从 fresh white 和新 session 身份开始；候选矩阵为 `C7 source → M0…M7 middle → T3/T7 target`，每 controller 16 recipes×4 positions，先筛 3 阶，再 HOLD 和 fresh-white reconstruction。当前屏幕/relay/资格状态不变。

## 2026-09-05 12:45 P2-C 真屏结果短入口

操作者确认 retained 全屏干净白后，本轮重新枚举了 COM/相机，完成 app-only 写入、exact IPv4↔MAC 与**刷写后同 boot** J2-OFF diagnostic。P2-C boot=`035c0421a9d81d40`；只执行 ordinal 1，严格为 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`，结果 COMPLETE，无 retry/recovery/autochain/ordinal 2。action 文件为 `.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/action-01-commented-complete-position-balanced-4x8-endpoint-atlas.json`，文件/canonical SHA-256=`f9c90f64fc096f301a7b66dc44e2902c09bc536aa8f7e9dc228a06fbf58873de / 65b642ce6a17017c918f2fc04f4c25a112429a667f41c76796b47c503d288e41`。

允许的 48MP `VID_32E4:PID_4801` 相机取得 10 帧低裁切白基线和 10 帧 action 保持图；RAW/ISO/硬件触发/温度均未获得。camera-relative 光学报告为 `.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/p2c-ordinal1-optical-report-v2.json`，文件/canonical SHA-256=`f5bdc0baba86eb1ee6e144d84dd0ab3561979856f211b58549d051936b0f7e9e / 7b7216031dc809f495d2173e7c3a856bcc1f306a6f2ad69f683aa061d3a3a5fb`。64-cell ROI 几何 RMSE=`1.432827 px`；CS2 八码的本次四位置初步门全过，CS1 仅 code 2/3/5 过；跨 controller P95 `|ΔL*|/ΔE76/hue=6.138233/9.823282/19.076824°`，未通过。CS1、CS2 都出现 code 1↔7 camera-relative 同色相明度候选，但三条 fresh chain、规范 HOLD、fresh-white 重建和 controller qualification 均缺失。

最终 outcome 为 `.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/p2c-ordinal1-session-outcome-v2.json`，文件/canonical SHA-256=`26381ddf2b7deb8487af4e44c7384257a29d1fd1a636e341781f7c1d9808a7b0 / 99002f74fc0b9dd9c6c3b497a97c68af2ec06be10bd33b248b8fdb2719669f98`，判定 `HOLD_FOR_EVIDENCE`，`qualified=0`。继电器已经 commanded/query `OFF`，`electrical_state_proven=false`；屏幕按双稳态保留 P2-C 4×8 atlas，没有执行 white successor。一次 >2h 照片显示图样仍可见，但环境光变化，不能充当 retention-v1 的定量结果。下一入口只做 CS1 位置依赖及 code 1↔7 的离线复核/新链封印；离线准备已获授权，任何新现场动作则必须 fresh 审查 retained screen 和 COM/IP/MAC/boot，不能继承本轮身份、claim 或放行。

## 2026-09-05 10:00 离线前置复核短入口

P2-C 主固件和独立 factory-OTP white successor 已实际复核：四个 BIN/ELF 文件均存在且 SHA-256 与封印报告一致；主/white 独立 audit、dry-validate 和定向 pytest `26 passed`。本轮没有硬件、COM、网络、relay、相机、刷写、复位或可见刷新，预期 live action 输出目录仍不存在，故没有 terminal evidence 可消费。runner 只开放 ordinal 1，并锁定 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`、无 retry/recovery/autochain；white successor 只接受 ordinal 1 的 COMPLETE。

当前仍为 `NO-GO`：relay/J2 最后记录 commanded `OFF`，`electrical_state_proven=false`，本轮没有 retained clean-white 人工确认，`qualified=0`。下一次唯一入口是先询问并获得本轮确认：“当前屏幕是否在未刷新、未复位、未刷写的情况下，全屏干净白，且无色块、边框、色斑和固定线？”确认前不得访问设备；确认后才重新枚举 COM、建立 exact IPv4↔MAC、完成同 boot J2-OFF diagnostic，并等待单独的 P2-C ordinal 1 放行。

## 当前目标与路线

项目是 ESP32-C73 主机配 MF1750 1024×600 双控制器电子纸。当前产品目标已经冻结为 **256 个总的单像素逻辑调色板槽**，不是 256×10：

`16 neutral + 12 hue families × 2 chroma/sub-hue tracks × 10 lightness ranks = 256`

色相族为 `R/RO/O/Y/YG/G/T/C/B/I/V/M`。每个槽必须由单像素、无空间抖动的证据支持；CS1/CS2 要分别有 recipe 和 controller-local 结果，跨控制器还要有明确的光学匹配证据。十阶按 `3 → 5 → 10` 逐级证明，物理跨度不足时保持未通过。

当前执行顺序已经从“继续枚举更多颜色”改为功能优先：

`稳定基色 → 单像素明度/灰度机制 → 局部 HOLD → 独立 factory-OTP 白屏 fresh reconstruction → 稳定明度族 → controller-specific palette → 照片逐像素映射 → multi-LUT HOLD schedule → fixed-photo bundle`

## 已完成的主要成果

- Rev A1 生产硬件基线已经冻结并曾提交嘉立创；首板使用 `GPIO7=CS1`、`GPIO10=CS2`，两颗 `SPD1657B` revision `0x04`，`CCSET(0xE0)=0x01`。不要重新生成或覆盖 Rev A1 生产目录。
- 主机应用、设备会话、图像处理、单像素静态照片管线、controller-local palette、HOLD/white reconstruction 框架、扩展色安全记录、Web UI、frame tool 和 repository contract 已实现并有离线测试。最近两个已提交软件里程碑是 `082ff62`（function-first static photo pipeline）和 `2d3539b`（256-slot lightness target）。
- P1 `EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1` 已于 2026-09-01 真屏完成：每个 action 仅一次 driver 和一次可见刷新；四位置、双控制器重复性已观察。人工词为 C0 浅橄榄绿、C6 绿色、C1 黑色，但不构成同色相三明度阶，当前 `qualified_new_colours=0`、`qualified_lightness_levels=0`。
- P1 后的独立 factory-OTP white successor 机器完成；但 retained clean-white 的人工/48MP 视觉门没有在本轮建立，且 `electrical_state_proven=false`。
- `STABLE_CODE0_LUMA_LATIN_V3` 的 identical-target repeat 为阴性：CS2 历史 L3 中值跨度约 `7.059 L*`，L4 收敛到约 `2.157 L*`，因此不能把该路径当作稳定明度发生器。
- 纯离线 seed + perturbation 审计 V2 已封印，结论为 `OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI`，`candidate_count=0`；6 个 seed 都是 candidate-only/未合格。现有 HOLD 语义也仍为 `BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE`。因此没有生成 seed live 固件。
- P2-C `EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1` 主固件的 ordinal 1 已按顶部 12:45 条目唯一执行并完成；独立 white successor 仍仅离线封印、未执行。该次 P2-C 结果只获得 endpoint 诊断和 camera-relative code 1↔7 候选，资格仍为 0。

## 当前现场与安全边界

当前 live 状态是 `NO-GO`：P2-C ordinal 1 已 COMPLETE，relay/J2 随后 commanded/query `OFF`，但这不是已经证明的电气状态，`electrical_state_proven=false`。面板按双稳态保留 P2-C 4×8 endpoint atlas；没有执行 ordinal 2、重试或 factory-white successor。

没有可直接继承的旧 IP、COM 号或设备身份。不要把旧身份当作当前绑定，也不要使用双目相机 `VID_1BCF:PID_0B15`；如需相机，只允许项目指定的 48MP `VID_32E4:PID_4801`。

以下动作仍禁止：邻芯片 LUT/寄存器移植、论文电压值直接套用、未知命令扫描、任意 byte 插值、header/body hybrid、VCOM sweep、BUSY 中断、自动串联下一项、自动白恢复、复用已消费的 claim/action/授权。

## 下一次工作应如何开始

1. 先离线复核 CS1 code 0/1/4/6/7 的四位置差异和两侧 code 1↔7 明度候选，冻结新的 targeted HOLD/fresh-white reconstruction schema；这项离线工作已获授权，但不得生成或执行未经审计的 mutation。
2. 任何新现场访问前，重新观察当前 retained P2-C atlas；若要改变屏幕，必须为所选的独立 white successor 或新 targeted action 建立单独的 live 放行。不要把本次 ordinal-1 放行扩展到后续动作。
3. 新 live session 必须重新枚举 COM、相机和 boot，建立 exact IPv4↔MAC，并按实际写入顺序取得同 boot diagnostic；不得复用本轮 `COM8/COM14`、`192.168.1.11`、boot、claim 或 action 身份。
4. code 1↔7 只有 camera-relative candidate 身份。至少三条独立 fresh chain、规定的 HOLD/retention、独立 white 重建、CS1/CS2 各自通过及跨 controller 光学匹配完成前，保持 `qualified=0`。

## 重要入口

- 当前唯一状态入口：[`STATUS_HANDOFF.md`](STATUS_HANDOFF.md)
- P2-C 本轮闭环 outcome：`.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/p2c-ordinal1-session-outcome-v2.json`
- P2-C camera-relative 光学报告：`.test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/p2c-ordinal1-optical-report-v2.json`
- seed/perturbation 结论和 Gate 0→2：[`MF1750_SEED_PERTURBATION_HANDOFF_2026-09-02.md`](MF1750_SEED_PERTURBATION_HANDOFF_2026-09-02.md)
- P2-C 离线主报告：[`MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json`](MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json)
- P2-C 独立白恢复离线报告：[`MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_OFFLINE_BUILD_2026-09-03.json`](MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_OFFLINE_BUILD_2026-09-03.json)
- 256 槽与搜索口径：[`MF1750_256_COLOR_10_LIGHTNESS_TARGET_AND_ADJUSTED_SEARCH_2026-09-01.md`](MF1750_256_COLOR_10_LIGHTNESS_TARGET_AND_ADJUSTED_SEARCH_2026-09-01.md)
- 功能优先路线：[`MF1750_SINGLE_PIXEL_PHOTO_FUNCTION_ROADMAP_2026-09-01.md`](MF1750_SINGLE_PIXEL_PHOTO_FUNCTION_ROADMAP_2026-09-01.md)
- 本轮后续执行计划（含最新公开资料边界）：[`MF1750_NEXT_PLAN_E6_PIXEL_WAVEFORM_2026-09-05.md`](MF1750_NEXT_PLAN_E6_PIXEL_WAVEFORM_2026-09-05.md)
- phase/controller 闭环测试计划：[`MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md`](MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md)
- 连续执行与验收运行手册：[`MF1750_CONTINUOUS_EXECUTION_OPERATOR_RUNBOOK_2026-09-05.md`](MF1750_CONTINUOUS_EXECUTION_OPERATOR_RUNBOOK_2026-09-05.md)

恢复上下文后，先运行：

```powershell
Get-Content docs\STATUS_HANDOFF.md -TotalCount 80
Get-Content docs\CONTEXT_RESET_HANDOFF_2026-09-05.md -Raw
git status --short --branch
git log -5 --oneline --decorate
```

当前工作区有大量用户未提交改动和未跟踪证据/工具文件；必须保留并审慎处理，禁止用 `git add -A`、reset 或 checkout 覆盖它们。最近一次状态文档记录的验证包括：P2-C 定向 `26 passed`，seed 定向 `10 passed`，相关 runtime-waveform/static-photo `197 passed`，repository-contract `30 passed`，并通过 Ruff、py_compile、import/CLI smoke；这些数字是最近已记录批次，后续改动后应重新验证。
