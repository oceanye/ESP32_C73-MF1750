# EC5 无抖动扩色晚间真屏测试计划

文档日期：2026-08-09  
适用面板：MF-17506-M009F-T，1024×600，双 SPD1657B  
状态：`INCIDENT HOLD / A1 PASS / U04 A2 CONSUMED PRE-I/O FAULT / J2 OFF`

> 2026-08-09 20:30 事故修订：Stage A V1 U04 driver 的冻结 DTM SHA-256 byte array
> 抄写错误，使 A2 在任何面板 I/O 前必然退出。V1 release 已隔离；A2 action/claim 已消费且
> 不得重跑。A3/A4/A5 与 Stage B 全部锁定，直至新代码、新 action/release、J2-OFF 内存诊断
> 和独立评审全部通过。本修订优先于下方白天冻结状态。

白天进度（`2026-08-09 09:22 +08:00`）：

- Stage A 设备 arm/execute、NVS 持久锁、host 单次 claim/review gate 和冻结 release 已完成；
  真屏 `0/5`；
- Stage B 六初态×双 DTM 镜像无抖动资产、U04/U07 九步状态机和冻结 release 已完成；
  真屏每个获批候选 `0/9`；
- 六环境 clean build、隔离扫描、release 深验和联合聚焦回归
  `193 passed, 59 subtests passed`；今晚无需等待临时代码开发；
- 全仓诊断暴露的可变 `.pio` RC2G 路径与 N7 handoff 精确文案两个根因均已修复；
  原受影响宽覆盖 `60 passed, 67 subtests passed`，N7/仓库合同/任务板 `46 passed`，
  最终设计哈希 campaign/analyzer `27 passed`；当前无已知失败路径；
- 本轮零设备/网络/串口/刷写/上电/真屏刷新。不推断当前 J2；最近已知
  实测固件仍是 RC2G
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`。

## 1. 目标与当前边界

本轮只研究“一个像素由一个码直接得到的颜色状态”，不使用误差扩散、蓝噪声、网点、
空间混色或其他抖动。所有测量微区内部均为完全相同的像素码。

今晚先利用控制器现有 OTP waveform，把保留码 `0x4`、`0x7` 当作黑盒候选进行小面积
探测。它只能回答“当前 OTP 是否已经给这两个码留下可重复的光学状态”，不能证明已经
修改 waveform，也不能替代 runtime-LUT 实验。

新增 STM32 资料已经证明 E2802/SPD1657 有 runtime-LUT 机制，但当前参考路径仍是
2-bit、master-only，且缺少可用于 ESP32 的完整 3-bit payload/loader/安全合同。因此：

- 本计划不上传、选择或修改 LUT；
- 不修改 phase、VCOM、PWR、BTST、PLL、温度模式或任何高压参数；
- 不测试 `0x8～0xF`；
- 不把 `0x4/0x7` 的结果宣传为自定义波形产生的新颜色；
- 本文件不授权刷机、上电、POST、可见刷新、重试或恢复。

## 2. 白天代码交付门

以下各项必须在晚上连接硬件前全部完成并形成可复核产物；任一未完成则当晚只做离线
审查，不执行未知码刷新。

- [x] release build 继续拒绝未知码，且不包含 EC5 route/test ID；
- [x] U04、U07 使用相互隔离的 binary，候选码编译期固定，不能由 HTTP/串口传入；
- [x] 固件无启动刷新、定时刷新、自动 retry、自动 recovery 或 raw-frame ingress；
- [x] 阶段 A 固定为五个显式、单次消费 action，不允许循环或跳步；
- [x] U07 host 执行前必须验证 U04 `0/5/30 min` review 和白色恢复 PASS；
- [x] 阶段 B 的六初态布局、左右镜像坐标、frame SHA-256 和双 DTM SHA-256 已冻结；
- [x] 每个 target/primer/white action 均有唯一 test ID、binary identity 和一次性消费状态；
- [x] 一次性消费状态跨 ESP32 重启保持；网络超时后只允许查询同一 job，禁止第二次 POST；
- [x] 固件执行前自行验证 1024×600、4bpp、左右 mapping、像素直方图、ROI 和所有 hash；
- [x] 每个 job 报告 PON/DRF/POF、BUSY、safe-finish、frame/DTM hash、boot nonce 和 reset 状态；
- [x] 白色恢复是单独的已知码 action，不由未知 target 自动触发；
- [x] 正式、N7、Stage A U04/U07、Stage B U04/U07 的最终 clean build 和聚焦测试通过，
      binary SHA-256/release sidecar/预览已冻结；
- [x] Stage A/Stage B physical-once runner 与 release 的最终文件 SHA、只读命令、深验结果和
      回归数已回填；
- [x] 操作者 runbook 只接受 exact action，不存在“再试一次”入口；
- [x] 根侧最终审查确认软件执行产物可供今晚实物 preflight；这不等于硬件已通过或已授权。

### 2.1 冻结产物身份

| 产物 | 冻结身份 |
|---|---|
| Stage A release | **QUARANTINED / DO NOT FLASH OR EXECUTE**：`.test-output/hardware/MF1750_EC5_STAGE_A_RELEASE_OFFLINE_20260809_V1`；manifest file SHA=`809529097f4e890fabd915f537c3f20acbc87fe09e9320e759117d69a205be39`；canonical SHA=`adedbbdfe7ccacb3705149282689db46407261e834298c2b5c77dd285eb6d7dd` |
| Stage A U04 | **DEFECTIVE / CONSUMED**：`firmware-u04.bin`，778000 bytes，SHA=`28a7b5585da123e518a43f2c810a19ec09287410d3de3496b379666180f5649e`；DTM SHA array 错误，显示序列未启动 |
| Stage A U07 | **LOCKED WITH QUARANTINED V1 BUNDLE**：`firmware-u07.bin`，778000 bytes，SHA=`60ccfd7213da65c603219b3304e8f255d3124dc39b4827213fbf77302b8afe24`；不得单独绕过新 release/review 使用 |
| Stage B release | `.test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1`；manifest file SHA=`db441f6e37215ffc7e8b6a365c3d7424d99fd301162b564a270e5af6bf4e7527`；canonical SHA=`b500fee26d57b11b0bf9f8441076dce5982516429794bed49f04f4ae2bcbdb04` |
| Stage B U04 | `firmware-sixstate-u04.bin`，783888 bytes，SHA=`722b69326fb562c7d79b1f10e5993d9f5acb82ca2b7343b63d4a7abb0e1ff0fc` |
| Stage B U07 | `firmware-sixstate-u07.bin`，783888 bytes，SHA=`815ac96e345ebab1f90c0aa1fd5e9f4254f9af09c5ddba2d2ed58c87bcbc3c06` |

Stage A 的 A1/A3/A5 只能使用昨晚实际验证并归档的原生 RC2G：

`.test-output/hardware/RC2G_N2_PHYSICAL_SESSION_20260808_2132/q1-map-primer-result/FIRMWARE.bin`

它是 815664 bytes，SHA=
`9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`。今天从当前源码
clean-build 的 production binary 虽同为 815664 bytes，但 SHA 为
`611cf5c0d043119f6cf34ddc97b3b5a656d4220993b206804e1b75d43433daf9`，**不得**替代上述
已实测 RC2G 恢复固件。

执行工具 SHA：

- Stage A physical-once=`b5aed8f07ad733b272187d4ec56186a915b5d6220b2fbe7a3e6540d8a7c9164b`；
- white recovery=`5fa32570a152a890d2fc1415e8133617b6933d30e26adacabb1d475f561bbd60`；
- Stage A release=`4b8dbbc2f50968ba98ff1351449c65197080ebec489e532f65b2cd00287b96ba`；
- Stage A preview generator=`f9086a1b02551f5de5b64d655d43c569d78e1b744b6ddfc88671ca4e4c1c678f`；
- Stage B physical-once=`2f38cffad222220dd8a781a2003689b32d3c9c683c18125e15adfee0c7db1c07`；
- Stage B release=`58159cc0a5dc0882578a5e60ad26c846b38e3ab9fa8c673028ec228baa188bb9`；
- Stage B asset generator=`1ada425f643c198419a18675c194270ceb707f0f49c2efc4717236d621799486`。

### 2.2 预览与只读复核

- Stage A U04：`.test-output/hardware/MF1750_EC5_STAGE_A_PREVIEWS_OFFLINE_20260809_V1/U04/u04_pilot.preview.png`，SHA=`c79cdf3d46279f21e93f1d20e121b7856c35ec662d6b131f56ce4527c1bae16a`；
- Stage A U07：`.test-output/hardware/MF1750_EC5_STAGE_A_PREVIEWS_OFFLINE_20260809_V1/U07/u07_pilot.preview.png`，SHA=`0ced70cc79202179b8cf8336489d84c0f88b37367722bb431edec7dad721670d`；
- Stage B U04：release 下 `assets/U04/u04_primer.preview.png`（SHA=`c40da3c0d352c74c71777d780c52d83eba366001fa22778afe5fe281b8ba8206`）和 `u04_target.preview.png`（SHA=`e27dc0c925fce257b3d7735a1af509f0e11820ef673e36d3c05cb533604cdb66`）；
- Stage B U07：release 下 `assets/U07/u07_primer.preview.png`（同 primer SHA）和 `u07_target.preview.png`（SHA=`2edfc383cdc90726ae14feb273de4910bb469ddf66d0e69ba14f2a10b5f1c2aa`）。

Stage A 预览中的彩色标记只用于指出候选码位置，不预测真屏物理颜色。Stage B target
预览同样是码位可视化；是否得到新颜色只能由真屏观察回答。

以下命令只做本地深验或描述，不访问设备、不创建 claim、不产生授权：

```powershell
python tools\mf1750_ec5_release.py validate --bundle .test-output\hardware\MF1750_EC5_STAGE_A_RELEASE_OFFLINE_20260809_V1
python tools\mf1750_ec5_physical_once.py describe --release .test-output\hardware\MF1750_EC5_STAGE_A_RELEASE_OFFLINE_20260809_V1\release-manifest.json --candidate U04 --source-root . --panel .test-output\hardware\RC2G_N2_PHYSICAL_SESSION_20260808_2132\inputs\physical-panel.json
python tools\mf1750_ec5_sixstate_release.py validate --release .test-output\hardware\MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1\release-manifest.json --panel .test-output\hardware\RC2G_N2_PHYSICAL_SESSION_20260808_2132\inputs\physical-panel.json --source-root .
```

实际 flash、GET preflight 和单次 run 命令由当晚根据当前端口、设备回读、result/claim 路径
逐项生成；runbook 不预先生成可消费授权，也不提供批量执行入口。

## 3. 晚间共同前置检查

开始前由用户在硬件旁人工确认并记录：

- 面板条码与本 session 绑定一致，FPC 和 CS1/CS2 接线未变；
- TP1/输入为 3.3 V 目标，电源处于 CV，限流值与已审查配置一致；
- 空闲电流、面板/控制器/驱动器温度正常，实体开关能立即切断 J2；
- ESP32 新 boot、当前无未完成 job，无浏览器、脚本或其他客户端能触发刷新；
- 固件、manifest、frame、双 DTM、预览的 exact identity 全部匹配；
- 固定观察距离、照明、相机曝光/白平衡和左右 ROI 取景不变；
- 用户针对下一条 exact action 单独授权；未授权时只允许只读 preflight。

沿用上一轮有人监督的实用过程门时，起始温度采用 10～40℃、刷新后不高于 45℃；这
只是已评审的实验过程门，不是供应商额定值。输入电流没有从规格书得到独立绝对上限，
所以必须同时与已知白色刷新包络比较，缺采集或仪器 overrange 时立即停止。

## 4. J2 电源规则

正常、已授权且报告为 safe-finish 的连续刷新之间，**不要求每次断开 J2**。J2 可以在
primer、target、计划内 white 和 `0/5/30 min` 观察期间保持接通；保持观察期间面板没有
刷新动作。

以下情况必须断开 J2：

- 刷写或更换 U04/U07/其他实验固件；
- 插拔 FPC、改变探头、接线或测量配置；
- BUSY、供电、温度、ESP32、画面或日志触发停止门；
- 需要建立明确冷启动边界，或晚间 session 结束。

断开后如需触碰硬件，应按现有安全门核对 TP1 和高压轨释放。ESP32 USB 供电与 J2
面板驱动电源不是同一件事，按 EN/RESET 不能证明面板已经断电。

## 5. 阶段 A：白初态小面积候选筛选

布局固定使用白色背景以及左右控制器镜像的 `64×64` 均匀 ROI；候选像素总面积为
8192 px，即全屏约 1.333%。ROI 中不能包含文字、边框、渐变或抖动。

成功路径最少、也默认恰好执行五次可见刷新：

| 次序 | 可见 action | 刷新后工作 | 推进条件 |
|---:|---|---|---|
| A1 | RC2G 原生白色 primer | 核对全屏白、左右一致、电气和 BUSY 基线 | 正常才到 A2 |
| A2 | U04 target | 记录即时画面，并在 `0/5/30 min` 无刷新观察 | 无停止门才到 A3 |
| A3 | RC2G 原生白色恢复 | 核对 ROI、左右半屏和全屏是否恢复 | 完成 U04 review gate |
| A4 | U07 target | 仅在第 6 节放行后执行；同样做 `0/5/30 min` 无刷新观察 | 无停止门才到 A5 |
| A5 | RC2G 原生白色恢复 | 核对最终恢复并结束阶段 A | 不自动进入阶段 B |

Stage A 有两段 30 分钟无刷新观察，预计总时长约 75～90 分钟。A1→A2→A3→A4→A5
每步都更换固件，因此换固件时必须断 J2；同一步的刷新、观察和证据记录期间不需要反复断电。

规则：

- 每个 action 只有一次 POST；HTTP/读取超时不得重发，只查询原 job；
- A1/A3/A5 使用已知六色 guard 内的 RC2G `solid-white`；A2/A4 分别使用隔离
  U04/U07 binary。更换固件前必须断开 J2，但正常观察期不需为了“软件步骤”额外断电；
- `t=0` 以该次 POF/BUSY terminal 时刻为基准，记录实际拍摄秒数；
- `t=0`、5 min、30 min 使用同一相机、照明和取景，观察期间禁止任何刷新；
- A2 或 A4 后若出现电气、热、BUSY、MCU 或快速恶化画面异常，不得为了清屏自动执行
  A3/A5；先停止并物理切断 J2，再决定是否存在安全的人工处置；
- 若只出现稳定但并非新颜色的 alias，仍按事实记录，不把它算作失败重试理由。

## 6. U07 条件放行

U07 不是 U04 的自动下一步。只有以下条件全部成立，才可准备并请求一条新的 U07
授权：

- [ ] U04 恰好执行一次，job/report/hash/BUSY/safe-finish 完整；
- [ ] U04 的 `0/5/30 min` 观察完整，期间没有额外刷新；
- [ ] 输入电气、轨、温度均在已批准门内，ESP32 未重启；
- [ ] 左右 ROI 行为没有危险性不一致或持续恶化；
- [ ] A3 白色恢复通过，没有不可接受旧画面残留或新增永久色斑；
- [ ] U04 observation 和 reviewer 结论已经保存；
- [ ] J2 已断开，U07 exact binary/sidecar 已重新核对并安全刷入；
- [ ] U07 新 boot 的零刷新 preflight 通过；
- [ ] 用户针对 A4 exact action 给出新的、尚未消费的明确授权。

任何一项不满足，U07 保持锁定。本计划不允许 U04 的授权覆盖 U07。

## 7. 阶段 B：六初态历史依赖测试

阶段 B 只针对阶段 A 中“视觉上区别于六码或呈现有规律历史依赖、且可安全恢复”的候选。
它不是阶段 A 完成后的自动动作，须重新评审、选择已有冻结候选包并重新授权。
Stage B U07 还必须验证 Stage A U07 target 的 `0/5/30 min` 观察和 A5 白色恢复 PASS；
Stage B U04 的通过不能替代这一门。

每个半屏放置六个小型均匀初态 ROI，右半屏与左半屏镜像，共十二个 ROI。六种初态顺序
固定为：

```text
白 0x1 → 黑 0x0 → 红 0x3 → 黄 0x2 → 蓝 0x5 → 绿 0x6
```

同一个 ROI 内只能有一种原生码；target 帧把十二个 ROI 全部改为同一个候选码。禁止
通过 ROI 内邻接不同颜色来制造视觉混色。

每个候选执行三轮，每轮固定三次刷新：

```text
六初态 primer → candidate target → 原生白色恢复
```

因此每个候选为 `3 refresh/round × 3 rounds = 9` 次可见刷新；两个候选都获批时上限为
18 次。每轮 candidate target 后均做 `0/5/30 min` 无刷新观察，完成 30 min 观察并通过
停止门后才允许执行该轮白色恢复。轮间不得自动串行，下一轮必须基于上一轮完整记录。

Stage B 同一候选的九个 action 已在同一固件中，可连续按 ordinal 推进，不需每步重新
刷机或按 RESET；正常 safe-finish 后 J2 可保持接通。每候选有三段 30 分钟观察，预计
总时长约 100～120 分钟，可分晚完成，但不能跳过持久状态和上一轮证据门。

三轮中使用相同布局和光学设置，但使用不同、预先冻结且一次性消费的 test ID。任一轮
恢复失败，就停止该候选剩余轮次和另一个候选，不补跑缺失次数。

## 8. 每次必须记录的证据

### 刷新前

- action/test ID、candidate、round、binary/manifest/frame/DTM SHA-256；
- 当前 boot nonce、上一 job/op、当前画面身份；
- TP1/输入电压、CV/CC 状态、空闲电流、限流设置、温度；
- J2 状态、实体开关可切断、ESP32 是否发生过重启；
- 本次用户授权 ID 和时间。

### 刷新期间及结束

- 唯一 POST 及 claim 已先消费；
- PON/DRF/POF BUSY 是否出现、持续时间、timeout/missing 状态；
- 输入峰值/平均值/能量和轨包络；无法观察的字段明确记为“未测”，不能填正常；
- safe-finish、job/op、frame/DTM hash、reset-during-job；
- 刷新后最高温度、电源是否仍为 CV、ESP32 是否重启。

### 光学观察

- 左/右每个 ROI 在 `0/5/30 min` 的固定设置照片或 RAW；
- 左右是否一致、颜色是否接近某个原生色、均匀度、边缘残留、斑点、漂移/褪色；
- 白色恢复后的旧画面残留和永久色斑；
- 无测色仪时只能给出“视觉候选”，不能记录为定量新颜色资格。

## 9. 停止门

出现以下任一项，立即停止后续 action；电气/热/MCU/BUSY 异常时直接物理切断 J2：

- PSU 离开 CV，发生 OCP/OVP/急停，电流或轨显著越过已知刷新包络；
- 起始温度不在本 session 批准范围，刷新后温度超过 45℃或出现异常快速温升/热点；
- PON/DRF/POF 的 BUSY 缺失、顺序异常、timeout 或无法形成 safe-finish；
- ESP32 重启、boot nonce 改变、job/report/hash 不一致或出现第二次 POST；
- 左右控制器出现明显且继续恶化的不一致；
- 快速加重残影、永久色斑、裂纹、异响、异味、冒烟或弧光；
- `0/5/30 min` 证据缺失、相机/电表/温度/日志链失效；
- 白色恢复失败或恢复后仍有不可接受的旧态轮廓。

停止后禁止自动 retry、自动补测或自动清屏。安全处置和任何恢复必须另行人工评审与授权。

## 10. 结果分类

| 分类 | 判据 | 结论口径 |
|---|---|---|
| 可寻址新色候选 | 六初态都收敛到同一非原生颜色；左右、三轮一致；30 min 稳定；白色可恢复 | 候选码本身可能选择稳定状态；仍需测色和更长保持资格 |
| 序列依赖色候选 | 最终颜色随六初态而不同，但每种初态在左右、三轮中可重复，30 min 稳定且可恢复 | 可作为“初态→target”序列颜色，不能称为单码唯一颜色 |
| 原生色 alias | 各初态稳定收敛到现有黑/白/红/黄/蓝/绿之一 | 控制器别名，不增加颜色种类 |
| 残影/非稳定中间态 | 旧态轮廓混入、随时间明显漂移、左右或三轮不一致、恢复困难 | 不计为新增颜色，停止扩大测试 |

核心区别是“可重复且可恢复”。仅看起来多了一种色、但依赖不可控残留或持续漂移的结果，
只能归为残影，不能作为调色板成员。

## 11. 授权与执行记录

下表按晚上实际动作逐项填写；未填写的行不构成授权。

| action | exact test/action ID | 用户授权 ID/原文 | 时间 | 状态 |
|---|---|---|---|---|
| A1 white primer | `aace554437b5377138825a473dbb0be1591fc472424c446d77e148bae9eeded7` | `AUTHORIZE_ONE_VISIBLE_RC2G_EC5_SOLID_WHITE_BASELINE__ACTION_AACE554437B5377138825A473DBB0BE1591FC472424C446D77E148BAE9EEDED7__NO_RETRY_NO_RECOVERY` | `2026-08-09 20:02 +08:00` | `DONE / FINALIZED PASS` |
| A2 U04 target | `bf2fcbcb29a35cf0a7915c67b48468aca26f7a35aef20e9ff68c9d60a37d0df5` | `AUTHORIZE_ONE_VISIBLE_EC5_U04__ACTION_BF2FCBCB29A35CF0A7915C67B48468ACA26F7A35AEF20E9FF68C9D60A37D0DF5__NO_RETRY_NO_RECOVERY` | `2026-08-09 20:15 +08:00` | `CONSUMED / FAULT_LOCKED / CONFIRMED FIRMWARE DIGEST DEFECT / DISPLAY SEQUENCE NOT STARTED / NO RETRY` |
| A3 white recovery |  |  |  | `NOT AUTHORIZED` |
| A4 U07 target |  |  |  | `LOCKED / NOT AUTHORIZED` |
| A5 white recovery |  |  |  | `LOCKED / NOT AUTHORIZED` |

阶段 B 的每个 primer、target、white 都必须在实际 campaign 中生成独立行；本文件不预填
test ID，也不提供批量授权。今晚只有在白天代码门全部关闭、硬件 preflight 通过并收到
对应 exact action 的实时授权后，才可执行该一项。
