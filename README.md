# ESP32-S3 + E2802 Cascade eInk 调试工程

## 当前现场与开发状态（2026-08-08）

> 本节只作快速入口；任何后续变化、数量、测试批次和文件哈希均以
> [`docs/STATUS_HANDOFF.md`](docs/STATUS_HANDOFF.md) 为唯一事实源。

- 驱动板/J2 电源已关闭，ESP32 单独保持供电；当前未消费的可见刷新授权为 `0`，没有
  设备访问、刷写或面板动作在进行。
- RC2G 的 N0/N1 已放行真屏 action 为 `4/4`，均已闭环；对应 fixed claims 已永久消费，
  不得重跑。
- N2--N8 的 physical production-live 软件入口、深绑定、单次执行/finalizer/analyzer 均已落地，
  软件闭环为 `7/7`；对应旧 UNBOUND/self-sealed/legacy public live 入口在 claim/联网前
  fail closed。真屏阶段仍只有 N0/N1 完成；最终状态必须读取 STATUS。
- 各阶段的实际 process-policy/供应商限额、每 action 最新 usage/profile review、测量资产和授权
  尚未形成。软件入口
  就绪不等于硬件放行；reviewed limit/runtime、仪器、供应商数据、panel/build/
  prior 绑定和逐 action 授权等外部门禁仍阻断对应真屏任务；晚间顺序见
  [`docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)。

## 当前交接入口

- **唯一当前状态页（完成数、剩余数、目的、下一步）：[`docs/STATUS_HANDOFF.md`](docs/STATUS_HANDOFF.md)**
- **N2--N8 晚间逐项真屏任务板：[`docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)**
- 阶段一制造与固件交接：[`docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`](docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md)
- 阶段二 ESP32/电池整合设计输入：[`docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`](docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md)
- Rev B-mini ESP32/TF/电源与器件初评：[`docs/H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md`](docs/H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md)
- Rev B-mini L1/L2 小型化详细评估：[`docs/REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md`](docs/REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md)
- Rev A1 R16 级联整屏实测：[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)
- 基础驱动与 API 参考：[`docs/MF1750_DRIVER_API.md`](docs/MF1750_DRIVER_API.md)
- H0 Rev A1/RC2C 归档状态：[`docs/H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md`](docs/H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md)
- RC2F/C4/C2 分阶段上机任务包：[`docs/RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md`](docs/RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md)
- Spectra 6 色域映射高级 AI Handoff：[`docs/G1_SPECTRA6_GAMUT_MAPPING_HANDOFF_2026-08-05.md`](docs/G1_SPECTRA6_GAMUT_MAPPING_HANDOFF_2026-08-05.md)
- 重叠感知空间半色调研究：[`docs/S1_OVERLAP_AWARE_HALFTONE_RESEARCH_2026-08-06.md`](docs/S1_OVERLAP_AWARE_HALFTONE_RESEARCH_2026-08-06.md)
- G1/S1 混色与显示器模拟交接：[`docs/G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md`](docs/G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md)
- G1/S1 晚些真屏验证任务：[`docs/G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md`](docs/G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md)
- RC2G 白天开发与晚间逐项真屏 Campaign：[`docs/MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](docs/MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)
- 网络照片与随机刷新 TODO：[`docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md`](docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md)
- 扩展颜色/亮度技术可行性结论：[`docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`](docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md)
- 扩展颜色/亮度后续测试 TODO：[`docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)
- C3 转移感知优化器离线交接：[`docs/C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md`](docs/C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md)
- 扩展颜色远端成果集成审查：[`docs/EXTENDED_COLOR_INTEGRATION_REVIEW_2026-08-05.md`](docs/EXTENDED_COLOR_INTEGRATION_REVIEW_2026-08-05.md)
- 主机快速刷新、CI 与六色流水线总集成：[`docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`](docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md)
- 多 AI TODO 与 Git 集成计划：[`docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`](docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md)
- 新对话启动提示：[`docs/NEXT_SESSION_PROMPT.md`](docs/NEXT_SESSION_PROMPT.md)
- 1210 电容焊盘复核：[`docs/REV_A1_1210_PAD_AUDIT.md`](docs/REV_A1_1210_PAD_AUDIT.md)
- Rev A1 最终生产检查：[`hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md`](hardware/mf1750_production_v1/production/FINAL_PREFLIGHT_revA1.md)

当前状态：`MF1750 REV A1` 已完成加工与基础驱动 D0 实机验收。生产冻结文件
仍为带 `revA1_Q1FIX` 名称的 Gerber、BOM、CPL，禁止重新生成或覆盖。
H0 已生成基于 Git 对象的源码/证据归档和 SHA-256 清单，但精确验收二进制仍缺失，
且尚未完成异机持久副本；硬件验收 tag 未获明确授权，不能宣称 H0 已最终封版。

## 历史累计结论（起于 2026-08-04；不作为当前状态入口）

> 本节保留已经发生的硬件与软件证据，段内的“当前”“下一步”和回归计数只代表各自记录
> 时点；与顶部摘要或 STATUS 冲突时，一律以 STATUS 为准。

- 当前硬件为 R15 拆除、R16 0 Ω 安装、GPIO10 独立控制 `SL_CSB`。
- 两颗 SPD1657B 的 revision 均稳定读为 `0x04`。
- 向两颗控制器分别写 `CCSET(0xE0)=0x01` 后，左右半屏可独立显示纯色，
  并已实测完整 1024x600 连续六色色条。
- 从左到右白/黑/红/黄/蓝/绿正确，中央红/黄中缝清晰；正式分帧为每行
  512 字节，CS1 取前 256 字节、CS2 取后 256 字节。
- ESP32-S3 已由 esptool 与运行时共同确认约 8 MB OPI PSRAM；307200 字节
  规范帧的主机、设备生成器和非刷新 ingress 哈希均已通过。
- 当前源码候选固件为
  `MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07`
  / driver API V3；它在 RC2F 上增加 PON/DRF/POF 命令前 idle、新 BUSY 边沿和
  safe-finish/final GPIO 证据。build 为 815664 字节、SHA-256 `9DF897…0CD772`，已于
  2026-08-07 精确刷入；MAP job1 与 macro4 job2 的协议、nominal timing、电气和
  frame fidelity 均通过。该 exact-action 范围不自动继承为其他算法资格。
  HTTP ingress 与公开驱动 API 都会在任何面板 I/O 前拒绝
  `0x4/0x7..0xF` 非法像素码；PON/DRF/POF 未观察到 BUSY 会 fail closed，
  POF 后的 PSR 寄存器写入保留等待证据但不要求额外 BUSY assertion；诊断报告
  以匹配的 operation ID 与产生它的 job/build 绑定。
- RC2C/V3 已用同一 MAP_ORIENT_V1 完成 100 kHz 协议复验和正式 1 MHz
  `/api/frame` 实屏验收；方向、中缝、颜色、完整/双 DTM 哈希、PON/DRF/POF
  BUSY、电源、温度及断电安全状态均正确。1 MHz 总耗时 34.187 秒，其中两半
  DTM 上传各 2.444 秒、DRF 约 21.7 秒。
- 主机 PSRAM 预检修正点 `2b19f75` 的 203 项回归、repository contract、
  PlatformIO build 与 GitHub CI run `30917129233` 全部通过；验收记录提交
  `fd548e3` 的 CI run `30918209821` 也通过。RC2C 实测 `firmware.bin` 为
  796272 字节、SHA-256 `F763FE…F45C475B`；RC2D 为 803120 字节、SHA-256
  `AE7427…943DAD`，
  在重新实屏验收前不得与 RC2C 的硬件证据混用。当前无 Rev A1 硬件 ECO 证据。
- 基础驱动 D0 已定版；普通图片与 Web UI 的软件合同已合入，但 calibrated palette
  真屏色彩、设备端认证、更高 SPI 扫频、快速波形和局刷仍是独立后续工作，不能
  由本次硬件通过自动提升状态。
- G1/S1 主机端显示器模拟基线已实现：严格 profile/hash、抖动前 tone/gamut
  mapping、三种 rendering intent、2×2/4×4 六色面积配方、真正的 void-and-cluster
  蓝噪声、六码面积 Bayer/蓝噪声、多色 DBS 和重叠感知多尺度 DBS，统一进入 10 算法、
  四阶段软预览页面。v2 artifact 固定为 `offline/formal=false`；没有 D65/2° 六色与
  混色色块实测、独立光学核及硬件 qualification 时，不得上传或声称真屏改善。
  独立受监督实验中，首个高负载 `area-weighted-ordered-8x8` 候选的精确帧与双 DTM
  hash 虽匹配，但 job2/op2 在 DRF 60010 ms 超时，POF cleanup 30005 ms 仍未闭环；
  用户实体断电，算法评价保持 `inconclusive`，授权永久消费。固定 MAP job3/op3
  随后以正常约 21.7 s DRF 恢复通过并再次断电。
- 低空间诊断 bundle 位于
  `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/`；manifest
  原始文件 SHA-256 为 `07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d`，
  frame SHA-256/FNV-1a 为
  `ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65` / `0xA9641618`，
  CS1/CS2 DTM FNV-1a 为
  `0xCB085C03` / `0x9ABD749A`。当时 J2-P1 已在持续监督会话中接通；non-displaying
  ingress 返回 `epd_action=none`、未刷新且 job 不变；随后
  attempt `38352ce6bc564530917c43099fe8d20a` 的 job4/op4 以
  PON/DRF/POF/post-PSR `181/21690/140/5 ms`、总时长 34169 ms 完成。用户确认真屏与
  `strict-final.png` 一致，3.3 V CV、电流、温度和 GPIO idle 正常；J2-P1 在继续受监督
  会话中保持接通。裁定仅为 `NOMINAL_DIAGNOSTIC_PASS`：全局终态直方图和全局 6×6
  转移计数各自都不是单独充分原因，空间频率与半屏负载仍未分离。row-major MAP-mask
  分配本来就不保留源图语义，画面难看不计画质；job2 仍为 `inconclusive`，根因未关闭，
  不产生任何算法 qualification。
- 后续 macro4 job5/op5 的 frame/双 DTM hash 与完整 sequence 精确匹配，但
  PON/DRF/total 为 `37110/39621/89049 ms`，明显偏离已知 nominal；用户确认画面与
  strict preview 一致，所以 `frame fidelity=PASS`，但主观画质差、4×4 块感明显。
  该次只能裁定 exact operation 成立、timing 异常、算法资格不成立；旧 claim 永久消费。
  证据裁决与 SHA 清单保存在
  `.test-output/hardware/G1S1_MACRO4_QUALITY_RUN1_20260807_004650/`。
- RC2G 已完成四次受控真屏 action：N0 的冷启动 MAP job1/op1 与 macro4 job2/op2，以及
  N1 的独立 MAP primer job1/op1 与 low-balanced job2/op2。四次的协议、frame/DTM hash、
  BUSY edge、安全 GPIO、电气和用户报告的 strict-preview 忠实度均通过；每个 fixed claim
  均已永久消费，禁止重跑。通用 runner 完成仍只代表单次协议和取证路径就绪；Q1--Q4
  自然图候选、四个独立 session 和八个 P0 action/claim declaration 已完成离线风险审计、
  深验证与冻结；physical-bound materializer、逐 action usage/profile 深绑定、one-shot/
  finalizer 与 tie-safe 四格总评器也已完成，但实际 policy 值、现场 panel/binding 文件、
  每 action approval 和授权均未形成，仍不能执行。旧 UNBOUND runner/claim 永久禁用。2×2 V2
  仍 `strict_metric_orthogonality_proven=false/upload_authorized=false`；N4 V3 已把五项预注册
  指标做到跨因素 exact 正交，固定 runner/finalizer/analyzer 也已完成，但 hardware/limit
  仍 blocked。N1 只提升 exact
  `low-balanced` action 为探索性 safety/fidelity PASS，不提升 bundle 或其他三格。
  RC2G MAP 为 `35006/180/22511/141/5 ms`，macro4 为
  `35017/181/22521/141/5 ms`（total/PON/DRF/POF/post-PSR）；macro4 忠实显示但
  主观画质差。旧时序异常未复现、根因未关闭。当前 J2-P1 已断开。
- N1 low-balanced 探索性 pilot 已闭环：primer result SHA-256 为
  `93d57feed9565344e20d10016977be8fc4754fbec09619316e96a8efed71f26a`；target result
  SHA-256 为 `0297015a4e6ad04a85435e7fe10cc3c75678be9811c76f82695da3d11ed37e0e`。
  用户确认目标真屏与 `low-balanced.strict-final.png` 一模一样、电气正常、ESP32 全程
  未重启，随后已物理断开 J2-P1。该图不评价自然图画质，也不放行 Q1--Q4。N2 四个
  自然图离线候选及 `MAP→候选` campaign 已于 2026-08-08 冻结。N2--N8 离线算法/计划
  包为 7/7；后来真实 preflight 重新打开 production live 深绑定修复。N2--N8 的
  physical production-live 软件链现均已闭环（`7/7`）。不能把软件完成写成硬件放行。
  真屏完成状态以 STATUS 为准。N6 已完成新的 physical operator CLI、N5 raw observation
  全量重算门、耐久 receipt/incident 边界和真实 Chromium physical E2E；这些软件完成项均不绕过 measured
  inputs、reviewed limits/runtime、仪器和逐 action 授权等外部门禁。C3 参数化转移感知
  优化器也已实现，但等待 N5 实测 profile 才能正式运行；仍没有新的可见刷新授权。
- N0/N1 阶段曾分别留下多批回归、repository contract、compileall、JavaScript syntax、
  diff check 与 PlatformIO build 通过记录。这些数字是历史快照，不是当前全仓最终计数；
  最新验证批次与哈希只看 STATUS。

## 2026-08-05 扩展颜色与亮度可行性结论

- 面板规格写明 `3-bit E6`，当前应用帧则是 4bpp packed 容器；4bpp 不代表存在
  16 个独立颜色。正式有效码仍只有 `0/1/2/3/5/6`。
- 若未来由用户逐阶段授权，第一轮最大范围仅限于原厂初始化和片上 OTP waveform
  不变的六色基线、恢复流程、`6×6` 转换矩阵，以及受控的小面积 `0x4/0x7`
  数字编码探针。
- 正式 `/api/frame` 继续拒绝 `0x4/0x7..0xF`。未来未知码只能通过默认关闭、
  固定图案、哈希锁定、一次性授权的隔离实验入口执行，不能放宽生产颜色校验。
- 当前 Rev A1 不是可编程 TCON：没有已知 LUT upload、内部 phase、局刷窗口、
  温度读取或独立高压控制接口。取得 SPD1657B rev `0x04`、当前 OTP 和厂商安全
  资料前，禁止猜寄存器、改 LUT/相位/高压或移植 SPD1656 命令。
- 当前没有软件可控 J2-1、PGOOD、板载电流/温度/高压联锁，因此未知码、耐久和
  waveform 实验均处于 `PENDING/BLOCKED`，等待用户逐阶段安排和授权。
- 远端 `research/extended-color-20260805` 的官方证据矩阵、测量记录合同、固定
  `0x4/0x7` 离线图、6×6 transition scaffold 和六码面积混色模拟已经完成本地集成
  审查；这些工具不含设备 I/O，仍固定为 `Hardware tested: NO`。合并不代表未知码、
  新颜色、恢复流程或真实混色色域已经通过实屏验证。

完整证据、公式修订、测量门禁和第一轮十个问题见扩色可行性文档；可执行任务、
依赖和停止条件见扩色测试 TODO。两份文档都不构成上电、COM8 刷写或刷新授权。

## 2026-08-05 Rev B-mini 第一轮架构结论

- H1 已记录 ESP32、TF、共用 3.3 V 与 L1/L2 小型化评估；原理图、PCB 和 BOM
  尚未冻结，也没有修改 Rev A1。
- 当前首选架构候选是 `ESP32-S3-WROOM-1-N8R8` 邮票孔射频模组，保留已验证
  的 8 MB Flash/8 MB OPI PSRAM；裸 SoC 不用于首版，XIAO ESP32-S3 Plus
  只作为快速工程样对照。若 WROOM 仍不能满足机械尺寸，再评估约 7×7 mm 的
  `ESP32-S3-PICO-1-N8R8` SiP，但它需要自研 RF/天线和 EMC 验证。
- 应用是低频刷新相框，当前不升级 ESP32-P4：高质量量化由现有浏览器或后续
  服务器 API 执行，S3 负责联网、TF 缓存、严格帧校验和刷新；本地基础量化只
  作为后备。P4 需额外网络协处理器，只有 S3 实测不达标才重开选型。
- TF 首版优先独立 SPI；当前电子纸驱动的双向 GPIO11 和断电片选状态使共享
  SPI 不是无条件接线替换。
- 产品架构建议由一颗有足够瞬态能力的 3.3 V 主稳压器分支供 ESP32、TF 和
  EPD，EPD 分支经过软件可控 load switch。当前 DevKit 3V3 → J2-1 只能另行
  授权做诊断，不是量产电源结论。
- L1/L2 第一轮以 15 µH 高性能 5030 为候选基线；4040 只作测流后的实验选项，
  器件与布局均未冻结。

## 构建与仓库边界

固件使用 PlatformIO。首次克隆后先复制 Wi-Fi 配置模板；真实凭据文件不会进入
Git：

```powershell
Copy-Item src\wifi_secrets.example.h src\wifi_secrets.h
platformio run
```

当前固件优先连接 `wifi_secrets.h` 配置的现有 Wi-Fi，并由路由器 DHCP 分配地址；
串口启动日志会打印 `WiFi STA IP`。只有 STA 在超时内连接失败时才回退到设备热点，
因此不要把历史示例中的 `192.168.4.1` 当成固定调试地址。

`hardware/mf1750_production_v1/production/` 内带 `revA1_Q1FIX` 名称的冻结生产
文件属于版本基线，禁止重新生成或覆盖。工作区可另外保留 EPDiy 与 Seeed Wiki
的第三方镜像、EDA 日志和调试截图；这些体积较大且可重新获取，已由 `.gitignore`
排除，不属于本项目的可交付源文件。

驱动 API 的输入边界是规范的 `1024x600`、4bpp 六色像素帧。完整字库、文字
排版、图像缩放、抖动和颜色量化属于后期渲染/应用层；不得耦合进
`epd_driver`。诊断层可以保留少量固定测试图元，但不承担通用字体渲染。

当前实验固件的 HTTP 控制接口没有应用层认证，只能放在可信、隔离的调试网络。纯软件、
离线生成和本地验证不要求切断 J2-1，但也不得因此访问设备；受监督硬件 run 成功到达
POF/safe-finish 且 GPIO idle 后，可在同一持续监督会话中保持上电，异常状态或监督会话
结束时必须实体断电，无人看管时同样保持 J2-1 断电。正式应用版必须增加 token/一次性
arm，或在 release 构建中关闭 legacy/危险诊断路由，不能把主机 CLI 的确认参数当成
设备端权限控制。

## 2026-07-13 可生产 PCB 状态

项目现在包含一块面向 MF-1750 / M009F-T（7.5 英寸、1024 x 600、
双 SPD1657）的完整级联驱动转接板 `MF1750 REV A1`：

- 生产目录：`hardware/mf1750_production_v1/production/`
- 嘉立创 PCB：`Gerber_mf1750_revA1_Q1FIX.zip`
- 嘉立创 SMT：`BOM_mf1750_revA1_Q1FIX.csv` +
  `CPL_mf1750_revA1_Q1FIX.csv`
- KiCad 源文件：`hardware/mf1750_production_v1/`
- 下单和首板检查：`production/PCB下单与首板检查.md`

这块板替代不兼容的 DESPI-C73 50pin 屏接口，并包含 MF-1750 A1 参考
电路所需的升压、负压和电荷泵网络。它不是 ESP32 主控板，也不含板载
3.3 V 稳压器；J2 需要外接 ESP32-S3 和稳定的 3.3 V 电源。

默认装配 R15，把 `CSB` 与 `SL_CSB` 相连，按 E2802 cascade 参考板的
单 CS 方式工作。需要独立第二片选时，先拆 R15，再装 R16，并将 J2-9
连接到 GPIO10；两者禁止同时安装。J2 前 8 脚沿用现有 DESPI-C73 顺序。

最终自动检查结果：ERC 0、DRC 0、未连接焊盘 0、原理图/PCB 一致性
错误 0。以上只能证明设计文件内部一致，首板仍必须核对屏尾 pin 1 与
接触面、嘉立创贴装方向，并在接屏前限流测量各高压电源轨。

Rev A1 已按器件数据手册修正 Q1 为 `1=G、2=S、3=D`，并把负压泵
D2 修正为 `K=GND、A=NEG_PUMP_H`；下单时只使用带 `revA1_Q1FIX`
名称的三个文件，避免与修正前上传记录混淆。

当前工程基于你提供的 `E6_73_sample code_V1.2_20250116` 和 `InkCubic_ E2802_cascade 电子纸E6转接板.pdf` 调整。

## 2026-06-10 验证记录（历史，已被 Rev A1/R16 结果取代）

> 本节及其后的 C73 接口排查是历史记录，用于解释为什么制作 Rev A1。
> 本段记录当时按 R15 共片选与 `EPD_PIN_CS2=-1` 排查的过程；当前首板已经
> 拆 R15、装 R16=0 Ω，并以 GPIO7/GPIO10 独立控制两颗 SPD1657B。不得把下述
> 旧 C73/R15 结论当成当前接线。

本轮软件/硬件联合测试结论：

- 当前 ESP32 + DESPI-C73 接线可以稳定驱动左半屏 `512x600`。
- `/api/bars-512x600` 测试结果：左侧通高显示完整 `白/黑/红/黄/蓝/绿` 六色条，说明当前 SPI、颜色编码、4bpp 像素格式、初始化和刷新流程对左半屏是正确的。
- `/api/bars-800x480` 测试结果：左侧显示 `白/黑/红/黄`，黄色略窄，底部出现通长肉色条。原因是 `800x480` 只覆盖 480 行，物理屏高为 600，底部 `120` 行未被刷新，保留残影/中间态。
- `/api/bars` 当前按 `1024x600` 发送 `307200` 字节，全屏会进入刷新流程，但最终仍主要只有左半屏出现渐变/残影，不能形成完整六色条。
- 3-wire 9-bit SPI 已测试，`PON/DRF/POF` 的 BUSY 立即返回，面板没有进入正常约 21 秒刷新流程；当前接线应继续使用 4-wire SPI + DC。
- 因此，“调整分辨率”只能解释并修正左半屏显示格式，不能在当前 DESPI-C73 硬件上单独解决右半屏不显示。

当前明确结论：

```text
整屏物理分辨率：1024 x 600
当前可驱动区域：左半屏 512 x 600
当前可用片选：CSB
缺失关键控制：SL_CSB / CS2
```

要实现完整 `1024x600`，仍需要把 MF-1750 pin 4 `SL_CSB` 引到 ESP32 的第二片选 GPIO，并在软件中分别向两颗控制器写入两个 `512x600` 半帧。现有 DESPI-C73 的 50pin pin 4 在图纸中不是 `SL_CSB`，不能直接当作第二片选使用。

关键结论：

- 当前面板整屏分辨率按你确认配置为 `1024x600`。
- `MF-1750..1).pdf` 的面板说明包含 `0.5T + SPD1657 * 2ea` 和 `7.50" TFT; 1024 X 600 DOTS`，因此这块屏本身就是双驱动/双半屏结构。
- `MF-1750` 的 50pin FPC 定义里，pin 4 是 `SL_CSB`，pin 31 是 `CSB`。当前只刷一半屏，最可能就是只驱动了 `CSB`，而 `SL_CSB` 没有被 MCU 控制。
- `DESPI-C73-SCH-20251014.pdf` 的 P2 8pin 只引出 `3V3/GND/SDI/SCLK/CS/D-C/RES/BUSY`，没有第二片选；它的 P1 50pin 里 pin 4 标为 `VDD`，不是 `SL_CSB`，因此不能把 DESPI-C73 的 P1 当作 MF-1750 的完全匹配接口。
- 参考资料里的级联转接板是 `E2802 cascade`，PDF 明确标注 `4-wire SPI(Default)`。
- E2802 转接板 PDF 的主接口能看到 `3V3/SDI/SCLK/CS/D/C/RES/BUSY`，原理图内部还能看到 `SL_CSB`、`BS0`、`BS1`；其中 `BS0/BS1` 被拉到 `VDD`，说明无需单独接 `BS`。
- 只显示长边一半不是屏幕坏，而是级联屏只驱动了其中一颗 E2802。
- 工程现在按两颗控制器处理：每颗 E2802 的 `TRES` 为 `512x600`，整屏为两个 `512x600` 半屏拼接。

## 图纸比对结论

`MF-1750` 屏的关键 FPC 引脚：

| Pin | Signal | 作用 |
| --- | --- | --- |
| 4 | `SL_CSB` | Slave chip select，第二片/级联片选 |
| 26 | `BS0` | 低电平为 4-wire SPI，高电平为 3-wire 9-bit SPI |
| 27 | `BS1` | 低电平参考 `BS0`，高电平为 standard/dual/quad 4-wire SPI |
| 28 | `RST_N` | 复位 |
| 29 | `BUSY_N` | 忙信号 |
| 30 | `DC` | Data/Command |
| 31 | `CSB` | 主片选 |
| 32 | `SCL` | SPI 时钟 |
| 33 | `SI0` | SPI 数据输入 |

`DESPI-C73` 的 P2 8pin 接口只适合单片选 SPI：

| P2 Pin | Signal |
| --- | --- |
| 1 | `3V3` |
| 2 | `GND` |
| 3 | `SDI` |
| 4 | `SCLK` |
| 5 | `CS` |
| 6 | `D/C` |
| 7 | `RES` |
| 8 | `BUSY` |

危险点：`DESPI-C73` 的 P1 pin 4 在图纸中接 `VDD`，而 `MF-1750` 的 pin 4 是 `SL_CSB`。如果直接把 ESP32 GPIO 接到这个点，GPIO 拉低时可能短接电源。要驱动全屏，必须使用真正把 `SL_CSB` 引出的 E2802 cascade 转接板焊盘/排针，或改板前先断开 `P1 pin 4 -> VDD` 的连接。

## 当前接线（Rev A1 / R16 双独立片选）

| Rev A1 J2 | 信号 | ESP32-S3 |
| ---: | --- | --- |
| 1 | `3V3` | 稳定 3.3 V；用于驱动板上/断电 |
| 2 | `GND` | `GND` |
| 3 | `SI0/MOSI` | `GPIO11` |
| 4 | `SCL/SCK` | `GPIO12` |
| 5 | `CSB` / CS1 | `GPIO7` |
| 6 | `DC` | `GPIO6` |
| 7 | `RST_N` | `GPIO5` |
| 8 | `BUSY_N` | `GPIO4` |
| 9 | `SL_CSB` / CS2 | `GPIO10` |
| 10 | `GND` | `GND` |

当前实板必须保持 R15 拆除、R16=0 Ω；R15 与 R16 禁止同时安装。FPC 禁止
带电插拔，所有逻辑信号均为 3.3 V。旧 C73、单 CS、R15 共片选和
`EPD_PIN_CS2=-1` 只属于前期排查记录，不能作为当前接线执行。

## 当前测试入口与边界

固件优先接入 `wifi_secrets.h` 配置的现有 Wi-Fi，实际 URL 以串口打印的
`WiFi STA IP` 为准；`192.168.4.1` 仅是 STA 失败后的 AP 回退地址，不是固定
调试地址。RC2C/V3 已完成 D0 正式验收；RC2F/V3 已完成受监督固定 MAP 基准、高负载
事故、固定 MAP 恢复、低空间诊断和 macro4 job5。RC2G/V3 已完成精确 MAP job1 与
macro4 job2 受监督验证；macro4 忠实度通过但画质差，旧时序异常根因未关闭。
当前现场为驱动板/J2 断电、ESP32 单独供电，且没有常驻可见刷新授权；晚间每个 exact action 都必须由用户当次授权并由独立 claim
永久消费。纯软件测试不要求改变 J2-P1 状态，但未经用户重新明确确认，不刷写 COM8、
不访问设备或任何会触发刷新的 HTTP 路由。晚间执行见
[`N2--N8 晚间逐项真屏任务板`](docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)。

RC2F 当前固件的设备首页提供照片工具模式：选择一次原图后，可在 Atkinson、
Floyd–Steinberg、无抖动和 8x8 有序抖动间切换，同时对比原图构图与实际六色
上传预览；可在原图画布拖动、滚轮/滑杆缩放、按 90° 旋转并重置构图。照片优化、
裁剪、构图和处理方式的变化只在浏览器本地重算，点击“上传并刷新”
后才提交当前帧。该网页仍使用未校准 reference RGB 色板，属于便捷实验入口，不
替代 calibrated host pipeline。

右侧六色预览按 M009F-T A1 规格书的 `163.84×97.20 mm` 有效区、
`0.160×0.162 mm` 像素间距和约 158 PPI 校正显示比例，不再假定像素为正方形；
像素检查支持适应窗口及 1×/2×/4×倍率，并可叠加像素边界。浏览器显示器的毫米
尺寸不保证物理 1:1，且 reference RGB 色板仍不是实屏测色结果。

D0 的唯一正式实屏顺序和命令见
[`docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`](docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)：
该顺序已经完成。正式调用方法与响应结构见
[`docs/MF1750_DRIVER_API.md`](docs/MF1750_DRIVER_API.md)；历史 `/api/white`、
`/api/black`、`/api/test` 和半屏上传流程只用于诊断溯源，不属于稳定应用 API。

## 2026-06-10 当时的已知限制（不要作为当前状态）

- 当时使用的 ESP32-S3 没检测到 PSRAM，无法一次性分配 `307200` 字节全屏帧缓冲；
  当前 esptool 与 RC2B 运行时均已确认约 8 MB OPI PSRAM，因此该历史限制已解除。
- 当时的图片入口只上传 `512x600` 半屏；当前 Rev A1/R16 已改为规范
  `1024x600`、307200 字节完整帧入口。
- E6 全彩 eInk 刷新需要几十秒，`DRF` 阶段 BUSY 拉低约 20 秒是正常现象。
