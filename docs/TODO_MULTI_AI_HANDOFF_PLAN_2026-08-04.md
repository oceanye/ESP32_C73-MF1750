# ESP32_C73 后续 TODO 与多 AI 协作计划（2026-08-04）

> **文档性质：历史规划与协作记录。** 当前完成数、剩余数、现场状态和下一步唯一以
> [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 为准；晚间逐项执行只看
> [`MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)。
> 下文所有 2026-08-04 至 2026-08-07 的“当前”“未实现”“下一步”和测试计数均保留为
> 当时记录，不能覆盖此叠加层。

## 2026-08-08 当前叠加层

- 驱动板/J2 电源已关闭，ESP32 单独保持供电；未消费的可见刷新授权为 `0`，当前没有
  设备访问、刷写或面板动作。
- N0/N1 已放行 RC2G 真屏 action 为 `4/4`，fixed claims 均已永久消费。
- N2--N8 physical production-live 软件入口已全部闭环（`7/7`）；对应旧
  UNBOUND/self-sealed/legacy public live 入口在 claim/联网前 fail closed。各阶段实际
  policy/供应商限额、每 action usage/profile approval、测量资产和
  授权未形成；真屏阶段仍只有 N0/N1 完成，最终验证只看 STATUS。
- N6 已完成 physical operator CLI、N5 raw→aggregate 全量重算、耐久 receipt/incident 边界和
  真实 Chromium physical E2E；N7 独立最小
  sweep 固件、physical campaign、五档 one-shot/finalizer/analyzer 已实现。旧文中的“真实浏览器
  未测”“R1 固件 action 未实现”已失效。
- 软件完成不构成硬件授权。reviewed limit/runtime、measured profiles、供应商数据、仪器、
  panel/build/prior 绑定及逐 action 授权等外部门禁仍阻断对应真屏任务。

## 2026-08-07 历史增量（已被上方叠加层取代）

- RC2G/V3 BUSY-edge 固件 815664 bytes、SHA-256
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772` 已精确刷入。
  MAP job1 与 macro4 job2 的协议、nominal timing、BUSY edge、GPIO、电气和 frame
  fidelity 已通过；该范围不自动提升其他帧或算法资格。
- 昨晚 macro4 job5/op5 exact frame/DTM/sequence 成立，但 PON/DRF/total
  `37110/39621/89049 ms` 异常；用户确认与 preview 一致，故忠实度 PASS、主观画质
  POOR/未定位。旧 claim 永久消费，算法不合格。
- RC2G 冷启动 MAP job1/op1 与独立 macro4 job2/op2 runner 已实现：网络前永久
  claim、单 POST、无重试/恢复、严格 nominal timing、BUSY edge 与 raw 证据保全。
- 本次 MAP 为 `35006/180/22511/141/5 ms`，macro4 为
  `35017/181/22521/141/5 ms`（total/PON/DRF/POF/post-PSR）；macro4 与 strict preview
  一致但主观画质差。旧 RC2F 时序异常未复现，根因仍未关闭；J2-P1 已断开。
- 四算法通用 RC2G 单次 runner 已实现，支持离线 action 描述、冻结 prior/target 身份、
  单 POST 和 fail-closed 取证；但自然图候选的空间复杂度接近或高于旧异常帧，且尚缺
  相同 MAP prior 的 campaign-cell 编排，因此没有真屏放行，不能连续 Q1→Q4。
- 根因 2×2 V2 只完成离线交叉设计审计；edge/seam 有残余协变量，
  `strict_metric_orthogonality_proven=false`，无上传/刷新 runner，不能真屏。
- 当前执行入口为
  [`MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)。
  成功 run 之间不例行断电；刷写/重启、异常或会话结束才实体切断 J2-P1。


## 0. 历史进度快照（2026-08-06 集成复审）

| 工作包 | 当前状态 | 已合入来源 | 剩余门禁 |
|---|---|---|---|
| D0 驱动定版 | RC2C/V3 的 100 kHz 协议复验与正式 1 MHz MAP 真屏均通过 | 本地集成加固+真屏证据 | 已关闭；更高频率不属于 D0 |
| C1 主机帧核心 | 软件、fixtures、严格上传/结果核验和 D0 真屏物理映射完成 | `feature/host-frame-core` / `cb0a03f` + 本地加固 | 无 D0 剩余门禁 |
| C2 六色量化与抖动 | 算法、schema v2、来源与整屏授权边界完成 | `feature/color-dither` / `7cc015e` + 本地加固 | 实测 D65/2deg 六色色板与真屏主观验收 |
| G1 抖动前色域映射 | 软件显示器基线完成；首个高负载 ordered 候选仍 inconclusive；固定 MAP 恢复和低空间诊断 job4/op4 均通过 | `host/gamut_mapping/` + `docs/G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md` | 低空间结果只排除全局直方图/全局 6×6 计数各自为单独充分原因；继续离线画质轨、分离空间频率与半屏负载，并补 D65/2° 实测及 qualification |
| C3 转移感知优化 | 参数化误差扩散、缺测 fail-closed、旧帧保守模式、6×6 histogram 与 Pareto 分析已完成 | `host/transition_optimizer/` + `docs/C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md` | 实测 palette/6×6 profile、同 panel/build/waveform binding 与真屏 A/B |
| EC0-EC9 扩展颜色/亮度 | 可行性审查与分阶段 TODO 已冻结；A/B/F/J 离线设计、七份 schema、面积混色与资产清单工具已合入本地 main（`73607a2` + 加固 `be859be`）；硬件测试未开始 | `docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md` + `docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md` + `docs/EXTENDED_COLOR_STAGE_LEDGER_2026-08-05.md` | 测色/电气仪器、恢复 pilot、隔离诊断入口、用户逐阶段授权；F 实验固件实现等用户审查设计文档后授权；LUT/电压继续等待 SPD1657B/OTP 资料 |
| C4 应用 API/Web UI | 应用 API/Web UI、HTTP adapter、一次性硬件授权与本地中止隔离锁完成；v2 已集成 10 算法、原图服务端解码和四阶段离线预览；后续 N6 formal 链已完成真实 Chromium E2E | 本地集成加固 + N6 formal operator | 设备端认证及外部门齐全后的受控可见设备验收；G1/S1 v2 保持 offline，真屏需独立 qualification gate |
| C5 CI 与回归门禁 | 扩展颜色合并时 286 项曾在 Python 3.10/3.12 通过；较早 host report 为 291 项；2026-08-07 当前工作树 532 项 unittest、repository contract、compileall、JS syntax、diff check 与 PlatformIO build 均通过 | `feature/host-ci` / `c59a1f2` + 本地加固 | 当前 532 项尚待 Python 3.12/远端 CI 和正式 report 刷新；CI 不替代硬件结论 |
| N0-N6 网络随机照片 | 待执行；已建立来源、下载、随机、量化、投递、调度与无人值守门禁 | `docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md` | 用户确认数据源、调度主机、周期、电源方式和 calibrated palette |
| R1/N7 SPI 扫频 | 独立最小固件、physical campaign、1/2/4/8/10 MHz production one-shot、finalizer/analyzer 已实现；legacy public live 已硬阻断，硬件未开始 | N7 白天 physical 软件包 | reviewed limit、刷机许可、SCLK/电气/温度证据及五档真屏执行 |
| R2 快速波形/局刷 | 证据边界与控制器中立规划器完成 | `research/fast-refresh` / `b03b7e1` | SPD1657B/面板 OTP 厂商资料；取得前禁止实装 |
| H0 阶段备份 | 已从精确 Git 对象生成 RC2C 源码/证据 ZIP、manifest 与 SHA256SUMS；仍非最终封版 | `docs/H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md` | 找回实测 `firmware.bin` 精确字节；验证异机持久副本；tag 需用户明确授权 |
| H1 Rev B-mini 分析 | ESP32/TF/电源架构及 L1/L2 第一轮只读评估已记录；器件未冻结 | `docs/H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md` + L1/L2 附录 | 定量电流、SW/高压波形、温升、机械与产品输入 |
| H2 Rev B-mini 设计 | 未开始原理图或 PCB | 无 | H0、H1 测量门禁和用户确认后才能启动 |
| 设备端功能缺口 | HTTP API 无认证/TLS、无远端 cancel、无持久 job 历史；HTTP 分块上传未实现（整帧依赖 PSRAM 一次性分配）；MCU 端 JPEG/PNG 解码与本地量化无正式路径 | `docs/MF1750_DRIVER_API.md` §8 + `docs/C4_APPLICATION_HANDOFF_2026-08-04.md` | 正式发布与无人值守运行前必须解决设备端认证；分块上传是 MINI-1-N4R2 小 PSRAM 评估前提；其余无正式排期 |
| S1 重叠感知空间半色调研究 | 经典软件基线完成；低空间/平衡半屏联合诊断 `NOMINAL_DIAGNOSTIC_PASS`，但不评价画质、不改变 job2 inconclusive | `host/halftone_optimization/` + `docs/G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md` | 离线源图保真质量 A/B；以额外对照分离空间频率与半屏负载；实测光学核、相机闭环和真屏 qualification |

远端完整集成分支 `integration/host-fast-refresh-ci-color` 的最新点为 `dd711c9`，
[GitHub Actions run 30863009577](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30863009577)
成功。本机已经 fetch、独立复现 64 项原始回归，并把该分支快进合入本地
`main`；冻结生产目录没有变化。`dd711c9` 本身仍是 RC1/V1；随后在本地集成的
RC2B/V2、主机工具、颜色与契约加固已通过当时的本地回归、repository contract、
`compileall` 和 PlatformIO clean build；随后 RC2B 真屏发现 post-PSR 假门禁，
RC2C/V3 随后完成 100 kHz 与正式 1 MHz MAP_ORIENT_V1 真屏验收；主机修正点
`2b19f75` 的 203 项回归、PlatformIO 与 GitHub CI run `30917129233` 全部通过。
真屏结论只来自同次 job/report 与用户对画面、电源、温度的确认，不能由 CI 替代。

2026-08-05 复审补充：扩展颜色研究分支（含面积混色、资产清单、阶段台账与 G1 移交文档）
已合入本地 main（`73607a2` + 加固 `be859be`），合并后全仓 286 项 unittest 在 Python
3.10/3.12 下通过；此前本地 main 领先 `origin/main` 7 个提交未推送，本次快照更新随提交
一并推送，推送后须以 `origin/main` 新 SHA 的 CI 为准。当前源码候选 build tag 为 RC2F
（`MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05`），
已完成 clean build，并已在断电门禁下刷写，随后执行受监督固定 MAP、候选、恢复和低空间
诊断；当前设备仍运行 RC2F/V3。低空间成功 run 在继续受监督会话中保持 J2-P1 接通；这
不是下一刷新授权，异常或会话结束时仍须实体断电。纯软件测试、离线生成和深验证不要求
改变 J2-P1 状态，也不得因此访问设备。`host-test-report.json` 与
`repo-contract-report.json` 已于 2026-08-06
刷新为本地 Python 3.10 的 291 项通过和正向冻结契约证据，并通过
`python tools/validate_ci_reports.py`；该 291 项正式 report 已是较早快照，当前 532 项
工作树仍须由 Python 3.12/远端 CI 复跑并刷新正式 report。

2026-08-06 上机准备补充：已建立
[`RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md`](RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md)，
把 RC2F T0–T5 驱动回归、设备网页断电预览、C2 测色和 calibrated C4 E2E 分阶段
隔离；内置网页可见刷新因缺 one-shot arm/有限 deadline 继续 BLOCKED，C2 正式数据也
等待测量合同；当前 runbook 中 T7 pilot 也不执行。R1 >1 MHz、未知码、waveform/局刷
继续保持软件或资料 blocker，未混入测试单。

2026-08-06 G1/S1 补充：显示器模拟的软件基线和 canonical v2 UI 已完成，统一提供
10 条算法路径和 source/mapped/final/model 四张 hash 绑定预览；当前全仓 532 项 unittest
通过。v2 仍永久 `offline/formal=false`，不访问设备，也不能直接转成
真屏上传。首个 `area-weighted-ordered-8x8` 真屏候选 job2/op2 在 DRF 60010 ms 超时，
POF cleanup 30005 ms 仍未闭环；其授权永久消费、算法评价 inconclusive。固定 MAP
recovery job3/op3 随后完整通过并完成 TP1/电流/温度/断电 GPIO 闭环。之后冻结的低空间
bundle `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/` 在
J2-P1 已接通的持续监督会话中先以 `epd_action=none`、未刷新且 job 不变通过
non-displaying ingress，再由 attempt `38352ce6bc564530917c43099fe8d20a`
执行 job4/op4；PON/DRF/POF/post-PSR 为 181/21690/140/5 ms，总时长 34169 ms，真屏与
strict preview 一致，3.3 V CV、电流、温度和 GPIO idle 正常。裁定
`NOMINAL_DIAGNOSTIC_PASS` 仅支持全局终态直方图/全局 6×6 转移计数不是各自单独充分原因；
空间频率与半屏负载仍未分离。row-major MAP-mask 画面不保留源图语义，不作画质评价；
job2 仍 inconclusive、根因未关闭、无算法 qualification 和下一可见授权。完整证据见
[`G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md`](G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md)，
晚些硬件工作拆分见
[`G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md`](G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md)。

## 1. 目的与当前优先级

MF-1750 Rev A1 驱动层 D0 已完成验收。后续执行顺序为：

1. 保持 D0 的提交、CI、真屏和安全收尾证据可追溯；
2. 补齐 H0 的精确验收二进制与持久副本；源码/证据 archive、manifest、hash 已生成，
   硬件验收标签仍需用户明确授权；
3. C4/N6 应用软件、本地中止隔离锁与真实 Chromium formal E2E 已完成；后续只在外部门
   齐全后执行受控可见设备验收；
4. C2 色板、R1 扫频和 C4 应用验收分开执行，不能互相冒充通过；
5. G1/S1 的 mapper、面积混色、经典半色调/DBS 和 canonical v2 UI 已完成；首个高负载
   真屏候选发生 DRF/POF cleanup 事故而结论不确定，固定 MAP 恢复和低空间联合诊断已通过。
   下一步仅做源图保真的离线质量预览，并另行设计可分离空间频率/半屏负载的因果对照；
   在根因隔离、六色/混色色块与光学核实测及独立 qualification gate 完成前，不继续
   下一算法真屏；
6. C3 参数化代码已完成，正式运行等待实测 palette/6×6 转移矩阵与跨资产 binding；R2 等待厂商资料；H1 已有第一轮结论但仍等待测量，
   H2 等待 H0/H1 门禁和用户输入。
7. EC0-EC9 已登记但不自动执行、不抢占 H0；用户排期后从资料、测量系统、六色
   基线和恢复 pilot 开始，不能直接跳到未知码、LUT 或高压实验。

剩余 TODO 不得修改已冻结的 Rev A1 生产文件，也不得绕过硬件或厂商资料门禁。

后续可把不依赖实物的代码工作交给其他 AI。其他 AI 只提交独立分支或补丁、
测试输出和移交说明；最终代码审查、实机验证和 Git 合并由当前硬件环境的
集成负责人完成。

## 2. 永久保护边界

以下内容禁止其他 AI 修改、重生成、重命名或覆盖：

- `hardware/mf1750_production_v1/production/`；
- 所有带 `revA1_Q1FIX` 名称的 Gerber、BOM、CPL；
- Rev A1 已下单文件的大小与 SHA256 记录；
- 当前驱动定版完成前的 `src/epd_driver.cpp`、`src/epd_driver.h`、
  `src/epd_config.h`；
- R15/R16、MF-1750 高压拓扑和 GPIO 基线，除非实测形成明确 ECO 证据。

任何 PCB 新设计只能放入新的修订目录，例如：

```text
hardware/mf1750_revB_mini/
```

不得把 Rev B 文件写回 `mf1750_production_v1`。

## 3. 环境与角色划分

### 3.1 集成负责人（具有当前硬件环境）

独占执行：

- ESP32-S3 COM8 刷写与串口复位；
- 驱动板 J2-1 上断电操作；
- 实屏方向、颜色、中缝、残影和温升判断；
- SPI 实机扫频；
- 3.3 V 电流、高压轨和示波器测量；
- `src/epd_driver.*` 的最终修改；
- 最终 Git 基线、审查、合并和发布标记。

### 3.2 无硬件 AI

适合执行：

- 纯主机图像算法；
- 确定性帧生成、哈希和映射单元测试；
- Web/API 应用层；
- PC 端上传、日志分析和测试报告工具；
- CI、静态分析和文档；
- PCB/BOM 的只读面积与器件候选研究；
- 官方资料、论文和专利的证据整理。

不得宣称实屏通过，不得调用 `/api/frame`，不得刷写 COM8，也不得根据
SPD1656 猜测 SPD1657B 的高压/LUT/局刷寄存器。

## 4. Git 当前状态与集成策略

工作区已经是可用 Git 仓库，`origin` 指向私有 GitHub 仓库。Rev A1 驱动 RC1、
硬件源文件和冻结生产清单的基线为 `3033da0`；C1/C2/C5/R1/R2 的远端集成点为
`dd711c9`，现已合入本地 `main`。RC2C/V3 已完成协议与 1 MHz 真屏验收；
`mf1750-driver-v1.0-hw-verified` 标签仍只在用户明确授权创建 tag 后发布，不能仅由
软件、文档或 CI 自动创建。

后续规则：

1. 每次提交和推送前运行 repository contract，冻结目录的文件集合、manifest
   基线指纹和二进制 hash 必须全部通过；
2. 每个新工作包基于已推送的明确 commit SHA 建分支，不得基于聊天中间状态；
3. 其他 AI 不直接刷写、调用设备刷新接口或推送 `main`；
4. 集成负责人审查授权路径、测试和 handoff 后才合并；
5. D0 真屏验收完成后另建只读快照和硬件验收标签；
6. 应用、算法或 CI 通过不得提前创建硬件 v1.0 标签。

建议分支名：

```text
feature/host-frame-core
feature/color-dither
feature/spectra6-gamut-mapping
feature/transition-aware-optimizer
feature/application-api-ui
feature/host-ci
research/fast-refresh
analysis/revb-mini
```

## 5. 工作包总览

| ID | 工作包 | 无硬件 AI 可完成 | 依赖 | 最终硬件门禁 |
|---|---|---|---|---|
| D0 | 驱动 v1.0 定版 | 否，只读复审可委托 | 当前任务 | PSRAM 日志、MAP_ORIENT_V1、1 MHz 规范帧 |
| C1 | 主机帧格式核心与 fixtures | 是 | D0 API/格式冻结 | 无 |
| C2 | 六色量化与空间抖动 | 是 | C1 | 实屏颜色主观验收 |
| G1 | 抖动前色域映射与照片优化 | 是，除真屏标定 | C2/C4 | 六色及混色测量、真屏 A/B |
| C3 | 转移感知抖动优化器 | 是，先做参数化代码 | C1/C2 | 6x6 实测矩阵 |
| C4 | 应用 API/Web UI | 是 | D0/C1 | 一次普通图片端到端刷新 |
| C5 | CI、静态检查和回归测试 | 是 | D0/C1 | 无 |
| R1 | SPI 高速传帧测试工具 | 是，工具部分 | D0 | 实机扫频 |
| R2 | 快速波形/局刷证据研究 | 是，仅研究 | 厂商资料 | 未取得资料前禁止实装 |
| H0 | Rev A1 阶段备份 | 否，集成负责人执行 | D0 后 | 找回精确验收二进制、验证持久副本；tag 需明确授权 |
| H1 | Rev B-mini 面积/BOM 分析 | 是，只读 | H0 | 器件与热/电流实测审查 |
| H2 | Rev B-mini 原理图/PCB | 可协助代码生成 | 用户输入+H1 | ERC/DRC/实物评审 |

## 6. D0：当前驱动 v1.0 定版

负责人：当前集成负责人。其他 AI 只能只读复审。

验收内容：

- R16 独立片选，GPIO7=CS1、GPIO10=CS2；
- 两颗 SPD1657B 分别写 `CCSET(0xE0)=0x01`；
- 每颗 TRES=512x600；
- 输入帧固定为 1024x600、4bpp、row-major；
- 偶数 x 在高 nibble、奇数 x 在低 nibble；
- 驱动层独占 source-half、flip-X、flip-Y、nibble-swap 映射；
- CS1/CS2 实际 DTM 流分别计算 FNV-1a；
- PON/DRF/POF 均先观察 BUSY assertion 再等待 idle；缺 assertion 或超时都返回
  失败并执行安全收尾；POF 后的 PSR 写入记录等待与 BUSY 采样，但不要求再次
  assertion；
- result-bearing job 只发布匹配非零 u32 operation ID 的不可变完整报告快照；
- 刷新结束后 SPI 释放且所有面板侧输出保持低电平；
- 应用只需包含 `epd_driver.h`，诊断接口隔离到 `epd_diagnostics.h`。

必须通过的 fixtures：

| Fixture | Full FNV-1a | CS1 FNV-1a | CS2 FNV-1a |
|---|---:|---:|---:|
| global-v-bars | `0x908478A5` | `0x61BCF1C5` | `0xA3446735` |
| global-h-bars | `0x7DD055C5` | `0x855679C5` | `0x855679C5` |
| MAP_ORIENT_V1 | `0x9D04142D` | `0xF26832DD` | `0xFE199FF5` |

当前已实测 global-v-bars 完整六色正确且中缝清晰；RC2B/V2 的 100 kHz
MAP_ORIENT_V1 方向、颜色、中缝、哈希和 PON/DRF/POF BUSY 也已通过，但其
post-PSR 严格 BUSY 门禁造成软件假失败。剩余验收为 RC2C/V3 重新刷入后的低速
协议复验，以及通过正式 1 MHz `/api/frame` 链路发送同一个规范帧。

## 7. C1：主机帧格式核心与 fixtures

建议文件所有权：

```text
host/epd_frame/
tests/fixtures/
tests/test_frame_contract.py
```

不得修改 `src/`。

交付：

- 一个无第三方依赖或依赖明确的 Python 库；
- pack/unpack 4bpp；
- full-frame 与逐行 CS1/CS2 拆分；
- source-half/flip-X/flip-Y/nibble-swap 的参考实现；
- 三个 fixture 的生成器、像素计数和 FNV 校验；
- 对全部 16 种单控制器映射组合逐字节比较字节级与像素级实现；
- 错误尺寸、奇数宽度、非法色码和截断数据测试。

验收命令必须由 AI 在移交中给出，且返回码为 0。

## 8. C2：六色量化与空间抖动

建议文件所有权：

```text
host/color_pipeline/
tests/test_color_pipeline.py
```

输入：RGB/RGBA 图像。输出：规范 307200 字节 4bpp 帧。不得直接访问 GPIO、
HTTP 刷新接口或修改驱动。

第一阶段实现：

- sRGB -> 线性 RGB -> CIE Lab；
- 可配置的六色实测 Lab 调色板；
- 最近色量化，建议使用 CIEDE2000；
- Floyd-Steinberg、Atkinson 和有序蓝噪声/阈值矩阵至少两种抖动；
- 白底保护、透明度合成、边缘保真和文本模式；
- 固定随机种子，确保相同输入产生完全相同 raw 与哈希；
- 输出预览 PNG 和 palette 使用率报告。

无实屏时只能使用参数文件中的颜色，不得把显示器 sRGB 常量声称为面板校准值。

## 9. C3：转移感知抖动与“最快近似颜色”

2026-08-08 状态修订：下述参数化算法代码已在
[`host/transition_optimizer/`](../host/transition_optimizer/) 完成，包括普通量化逐字节退化、
完整实测 6×6 profile 门、旧帧未知保守模式、transition histogram、跨面板 binding 和
Pareto 报告。详见 [`C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md`](C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md)。
代码完成不改变实测 profile/真屏资格门，也不允许对当前固定全局 waveform 宣称缩短 BUSY。

该算法有实现价值，但必须正确理解目标：在当前固定全局 DRF 波形下，改变
空间配色不会缩短 BUSY 的固定波形时长；它能优先减少昂贵颜色转移、变化
像素、能耗、闪烁或残影。只有厂商提供 transition-specific/partial waveform
后，转移代价才可能直接对应刷新时间。

建议文件所有权：

```text
host/transition_optimizer/
schemas/epd_transition_profile.schema.json
tests/test_transition_optimizer.py
```

参数文件至少包括：

- 六个物理颜色的实测 Lab；
- 6x6 当前色 -> 下一色的光学误差；
- 6x6 峰值电流、能量、稳定时间、残影评分；
- 温度、波形版本、面板序列号和测量日期；
- 未测值必须为 null，禁止自动补造。

推荐目标函数：

```text
J = alpha * perceptual_error_CIEDE2000
  + beta  * transition_cost(current, candidate)
  + gamma * changed_pixel_penalty
  + delta * spatial_artifact_penalty
```

实现可采用“带状态代价的误差扩散”：对每个像素的六个候选色同时计算
感知误差与当前色转移代价，选择最小项，再扩散颜色误差。若多个局部颜色比例
可得到相似综合色，优先选择总转移代价最低的组合。

必须提供：

- `beta=gamma=delta=0` 时退化为普通颜色量化的测试；
- 空转移矩阵时明确拒绝或退化，不得伪造成本；
- 旧帧未知时的保守模式；
- 输出 6x6 transition histogram，供硬件实测回填；
- 画质/代价 Pareto 曲线，而不是宣称单一参数始终最佳。

## 10. C4：应用层 API 与 Web UI

建议文件所有权：

```text
app/
web/
src/application_adapter.*
```

除新增薄适配层外，不得修改 `epd_driver.*`。

应用团队只调用：

```cpp
bool epdDisplayFrame(const uint8_t *frame, size_t len);
const EpdOperationReport &epdGetLastOperationReport();
```

要求：

- 上传精确 307200 字节且 Content-Type 为 `application/octet-stream`；
- HTTP 202 只代表排队，必须轮询最终 job 状态；
- UI 在异常/断网时恢复按钮；
- 禁止连续刷新覆盖未完成任务；
- 本地中止不得冒充远端 cancel；提交结果不明或 safe-finish 证据未闭环时必须继续
  锁住新提交，进程重启前人工确认设备 idle 与安全收尾；
- 显示 full hash、CS1/CS2 DTM hash、BUSY 超时阶段和耗时；
- 应用不得直接发送 CCSET/PON/DRF/POF；
- 应用不得自行拆左右半帧或补偿镜像。

## 11. C5：CI 与回归门禁

建议交付：

- PlatformIO release build；
- Python 主机测试；
- 检查 `EPD_ENABLE_TEST_PATTERN=0`；
- 检查生产冻结文件 SHA256 不变；
- 检查 `/api/frame` 的长度/Content-Type/二进制零字节路径；
- 检查三个 fixture 哈希；
- 检查公共头 `epd_driver.h` 不重新暴露 legacy 单控制器函数；
- 生成机器可读测试报告。

当前实现会在 CI artifact `host-contract-reports` 中同时保存
`host-test-report.json` 与 `repo-contract-report.json`；二者都固定声明
`hardware_tested:false`。

CI 只能编译和主机测试，不能把“编译通过”标记成“硬件通过”。

## 12. R1/R2：高速刷新研究边界

### R1：SPI 传帧加速

2026-08-08 状态修订：N7 独立最小固件、physical-bound campaign、1/2/4/8/10 MHz 五个
production action、一次性 runner、finalizer 和 analyzer 已完成；旧 self-sealed public live
入口已在 claim/联网前硬阻断，不再是“固件 action 未实现”。它们尚未刷入或真屏
执行，仍须 reviewed limits、刷机许可、SCLK/电气/温度测量链和逐 action 授权。每个频率
按冻结合同冷断屏，使用同一 MAP_ORIENT_V1，核对两个 DTM hash、屏幕、CV、温升和 BUSY；
只有前述档位均稳定后才考虑更高频率。

SPI 加速只缩短 DTM 上传，不缩短固定 DRF 波形。RC2C 100 kHz 实测两半上传各约
14.9 秒，而显色 BUSY 约 21.7 秒；RC2C 与 RC2F 的固定 MAP 1 MHz 真屏均已完成，
RC2F recovery 实测两半上传各 2.440 秒、DRF 21.700 秒。该结果只覆盖 1 MHz 固定 MAP，
不能外推到 2/4/8/10 MHz，也不能解释高负载候选的 DRF/POF cleanup 超时。

### R2：快速波形/局刷

只允许做证据研究。交付必须区分：

- MF-1750/SPD1657B 的直接证据；
- SPD1656 或其他控制器的旁证；
- E Ink 新一代 Ripple/T2000 等不兼容平台的信息。

未取得 MF-1750 厂商提供的 SPD1657B datasheet、专用 LUT、温度表和局刷流程
前，禁止枚举 LUT、改变高压、缩短相位或移植 SPD1656 PartialRAM 命令。

扩展颜色与亮度研究不放宽上述边界。其当前可行性、`3-bit E6` 与 4bpp 容器的
区分、小面积编码探针和硬件联锁要求见
[`EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`](EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md)
及 [`TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)。

## 13. H0/H1/H2：PCB 小型化 TODO

### H0 阶段备份

当前私有 Git 基线和冻结生产 manifest 已构成阶段性可追溯备份。2026-08-06 已从
精确 Git 对象生成源码/证据 archive、机器可读 manifest 和 SHA256SUMS，详见
[`H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md`](H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md)。
由于验收时 `firmware.bin` 的精确字节尚未找回、暂存集合尚未验证异机持久副本，且
硬件 tag 未获用户明确授权，因此仍不能称为“硬件 v1.0 已验收”最终快照。完整快照至少包含：

- `hardware/mf1750_production_v1/`；
- 驱动 v1.0 源码与固件 build tag；
- 首板实测记录和交接文档；
- 生产冻结文件原 SHA256；
- 新快照 archive 的 SHA256。

### H1 Rev B-mini 分析

第一轮结论已记录：

- [`H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md`](H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md)：
  ESP32 集成层级、TF、共用 3.3 V、受控供电实验和 H2 输入；
- [`REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md`](REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md)：
  15 µH 5030/4040 候选、相关功率器件和 A/B 样板门禁。

当前推荐 WROOM-1-N8R8 作为首选架构候选、XIAO Plus 只作工程样对照；
PICO-1-N8R8 作为 WROOM 包络无法满足时的激进小型化候选，需 4 层/RF 门禁。
低频相框不升级 ESP32-P4；高质量量化走浏览器/服务器 API，S3 负责 TF 缓存、
验证与刷新，本地基础量化只作后备。
TF 首版使用独立 SPI，EPD 3.3 V 经软件可控 load switch。L1/L2 首轮优先
高性能 5030，4040 仅在测流后实验。以上均未冻结器件或布局。

H1 仍需完成：

- L1/L2 峰值电流、阶段 RMS、SW_H/SW_C 波形和定量温升；
- ESP32 Wi-Fi、TF 读写、EPD 刷新及三者叠加的 3.3 V 电流与瞬态跌落；
- VPH/PREVGL/VPC 等高压轨、纹波、建立/释放和 MLCC 实际偏压；
- WROOM 与可选 XIAO Plus 样板的 GPIO、电源、天线和机械复审；
- 5030/4040 候选样板 A/B 与其余高压功率器件审查。

不得仅按封装更小就判定等效，尤其是 L1/L2、电荷泵电容、二极管、MOSFET
和高压间距。

Rev A1 已经是 2 层板；Rev B-mini 是否继续 2 层的核心问题是集成 ESP32、
USB 差分、电池 buck-boost/充电器与电子纸高压开关噪声后的回流、EMI、散热和
天线净空，而不是“能否画出两层走线”。

### H2 开始设计前必须由用户确认

- 首版是否采用 WROOM-1-N8R8 候选，是否另做 XIAO Plus 工程样；
- 若 WROOM 过大，是否接受 PICO-1-N8R8 所需的 4 层和 RF/EMC 验证；
- 是否接受“服务器高质量量化 + S3 本地后备”；P4 当前不进入首版；
- 板载天线或外置天线版本；
- TF 卡口位置/方向、card-detect、目标容量和文件系统；
- 独立 TF SPI 与 EPD load switch 的 GPIO 分配；
- 电池容量、最大长宽厚、保护板、接口和 NTC；
- USB-C 是否同时充电、供电和原生烧录；
- 最大 PCB 长宽、目标总厚度、安装孔、FPC/USB/开关位置；
- 是否允许 4 层作为面积/EMI 对照方案；
- 刷新峰值电流、L1/L2 实测温升以及 Wi-Fi/TF/刷新叠加电源预算。

## 14. 每个 AI 的强制移交格式

每个工作包最终必须提交：

```text
Work package ID:
Baseline commit SHA:
Branch name:
Objective:
Files changed:
Files intentionally not changed:
Assumptions:
Commands run:
Exact test output / exit codes:
Hardware tested: NO
Known limitations:
Risks requiring integrator review:
Suggested merge order:
```

不得只交一段说明而没有可复现命令，也不得把网络搜索摘要当成代码验收。

## 15. 最终合并门禁

集成负责人按以下顺序审查：

1. 确认分支基线 SHA 正确且只修改授权路径；
2. 审查算法和错误路径；
3. 本机重新运行全部测试，不采信复制的“通过”文字；
4. PlatformIO clean build；
5. 核对冻结生产文件 hash；
6. 对涉及固件的分支，仅在用户明确确认后、J2-1 断电时刷写，并做
   GPIO/PSRAM/HTTP 安全检查；
7. 只有确实需要的变更才安排冷启动实屏测试；
8. 合并后再运行完整回归并记录 commit SHA；
9. 应用层、算法层通过不自动提升驱动/硬件版本号；
10. 任何 LUT、高压、局刷或 PCB 变更必须单独审查，不能混入应用 PR。

现有 C1/C2/C3/C4/C5 与 N2--N8 离线算法/计划工作已完成；N2--N8 physical
production-live 软件链已全部闭环（`7/7`），相应旧 UNBOUND/self-sealed/legacy public live
入口已硬阻断。实际 policy/供应商限额、每 action usage/profile
approval、测量资产和授权尚未形成，软件完成不得当作 live 放行；最终状态只看 STATUS。
N6 真屏验收、H0、R2、H1/H2 仍按各自证据门推进。
任何后续工作不得反向修改已验收驱动，除非形成独立且有证据支持的新硬件/固件版本。
