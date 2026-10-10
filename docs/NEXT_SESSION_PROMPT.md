# 下一阶段新对话启动提示

## 2026-08-08 当前覆盖说明

下方长提示保留历史背景，但其中按日期记录的 build、计数和“下一步”不得当成当前状态。
新会话必须首先读取唯一当前状态入口 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md)，再读
[`MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)。
当前事实是：

- 用户已关闭驱动板/J2 电源，ESP32 单独保持供电；没有未消费的可见刷新授权，也没有
  设备访问或面板动作正在进行。
- 当前实测 build 是 RC2G/V3；815664 bytes，SHA-256
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`。
- RC2G 已完成四个 exact action：N0 MAP job1/op1、N0 macro4 job2/op2、N1 MAP primer
  job1/op1、N1 low-balanced job2/op2。四者协议、电气和 frame fidelity 均通过；macro4
  主观画质差，N1 几何诊断图不参与自然图画质排名。
- N1 primer result SHA-256 为
  `93d57feed9565344e20d10016977be8fc4754fbec09619316e96a8efed71f26a`；target result
  SHA-256 为 `0297015a4e6ad04a85435e7fe10cc3c75678be9811c76f82695da3d11ed37e0e`。
  用户确认 target 与严格预览一模一样、电气正常、ESP32 全程未重启；两张之间 J2 未断开，
  观察后 J2 已断开。target 有一次只读 job poll 超时，但帧 POST 只有一次、无 recovery。
- N1 两个 fixed claims 已永久消费，不得通过新目录、重启、换 primer SHA 或复用授权重跑。
- 当前滚动计划 N0--N8 的真屏阶段仍为 N0/N1 完成，RC2G 已放行范围内的可见 action 为
  `4/4`；未来刷新量、剩余阶段和目的必须直接读取 STATUS，不再在本提示维护易过时下限。
- N2--N8 physical production-live 软件入口已全部闭环（`7/7`）；相应旧
  UNBOUND/self-sealed/legacy public live 入口在 claim/联网前 fail closed。任何软件完成项
  都不自动提升硬件资格，最终状态只看 STATUS。
- 各阶段实际 process-policy/供应商限额、每 action 最新 usage/profile review、测量资产和授权
  尚未形成。operator
  就绪不代表真屏放行：reviewed limit authority/runtime、measured profile、仪器、
  panel/build/prior 绑定及逐 action 用户授权等外部门禁仍生效。继续采用“白天完成代码和
  离线证据，晚上按任务板逐项授权上机”的分工。
- 2×2 V2 仍 offline-only、非严格正交且 `upload_authorized=false`；N1 只提升 exact
  low-balanced safety/fidelity，不授权另外三格或严格因果归因。
- 既有回归计数只作历史记录；当前全仓验证批次、构建结果和文件哈希均以
  `STATUS_HANDOFF.md` 为准，本文不猜测最终数字。

复制以下内容到清空后的新对话：

> 请先完整阅读工作区中的
> `docs/STATUS_HANDOFF.md`、
> `docs/MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`、
> 根目录 `README.md`、
> `docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`、
> `docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`、
> `docs/H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md`、
> `docs/REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md`、
> `docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`、
> `docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`、
> `docs/MF1750_DRIVER_API.md`、
> `docs/H0_REV_A1_RC2C_ARCHIVE_STATUS_2026-08-06.md`、
> `docs/H0_REV_A1_RC2C_ARCHIVE_MANIFEST_2026-08-06.json`、
> `docs/RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md`、
> `docs/G1_S1_MONITOR_SIMULATION_HANDOFF_2026-08-06.md`、
> `docs/G1_S1_REAL_PANEL_VALIDATION_TASKS_2026-08-06.md`、
> `docs/S1_OVERLAP_AWARE_HALFTONE_RESEARCH_2026-08-06.md`、
> `templates/MF1750_RC2F_HARDWARE_SESSION_TEMPLATE.md`、
> `templates/MF1750_VISIBLE_REFRESH_LIMIT_PROFILE_TEMPLATE.md`、
> `docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md`、
> `docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`、
> `docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`、
> `docs/C1_HOST_FRAME_HANDOFF_2026-08-04.md`、
> `docs/C4_APPLICATION_HANDOFF_2026-08-04.md`、
> `docs/C5_HOST_CI_HANDOFF_2026-08-04.md`、
> `docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`、
> `docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md` 和
> `docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md`。
> MF-1750 Rev A1 已于 2026-07-13 提交嘉立创，生产文件被冻结，禁止重新生成、
> 覆盖或把 Rev B 文件写回该目录。当前首板已拆 R15、装 R16=0 Ω：GPIO7=CS1、
> GPIO10=CS2；两颗 SPD1657B revision 均为 0x04，分别写 CCSET(0xE0)=0x01 后，
> 100 kHz 完整 1024x600 六色色条、颜色顺序和中缝已经实屏通过。
>
> 当前现场为驱动板/J2 断电、ESP32 单独供电，未消费可见刷新授权为 `0`；不要访问设备、
> 刷写或触发面板动作。当前实测 build、binary identity 和最新软件验证批次只从 STATUS
> 读取，不得用下方历史 RC2C/RC2F 记录覆盖。
> N0/N1 已放行真屏 action 为 `4/4`。N2--N8 physical production-live 软件入口
> 已全部闭环（`7/7`），相应旧 UNBOUND/self-sealed/legacy public live 入口在 claim/联网前
> fail closed。实际 process-policy/供应商限额、
> 每 action usage/profile approval、测量资产和授权未形成。
> 外部 measured/reviewed inputs、limit authority、仪器和逐 action 授权未齐时，所有 live
> runner 均停在 describe，软件完成不得提升为硬件通过。
> 最近完成实机验收的 RC2C/V3 已在 100 kHz 与正式 1 MHz
> 显示完全正确的 MAP_ORIENT_V1，并确认 PON/DRF/POF BUSY、完整/双 DTM 哈希、
> 电源、温度与断电安全状态；实测同时证明
> POF 后 PSR 写寄存器不会再次拉低 BUSY，RC2C/V3 因而把该采样改为信息证据。
> 它保留非法六色色码的双层拒绝，并把
> diagnostic report 以匹配 operation ID 的不可变快照与产生它的 job/build 绑定，
> 未观察到正式阶段 BUSY 会 fail closed。主机修正点 `2b19f75` 已通过 repository
> contract、203 项全仓 unittest、PlatformIO build 和 GitHub CI run `30917129233`；
> D0 实测详见级联整屏验证文档。N0 收尾快照为 532 项 unittest 通过；N1 runner 加入后
> 当时的 556 项 unittest 也全部通过。最新全仓数量必须从 STATUS 读取。纯软件、离线生成
> 和本地验证不要求切断 J2-P1，但不得借此访问设备；未经我明确确认，不得刷写 COM8、
> 访问设备 HTTP 刷新接口或要求改变电源状态。受监督硬件 run 正常到达 safe-finish 且
> GPIO idle 后可在同一监督会话中保持上电；异常或监督会话结束时必须实体断电。
> H0 的 RC2C 固定 Git 对象源码/证据 archive、SHA256 manifest 已生成，但实测
> `firmware.bin` 的精确字节仍缺失，暂存集合尚未验证异机持久副本；不得用重编译
> 近似产物替代。下一步先补齐这两项，再由用户明确指定 tag 名称和目标后创建硬件
> 验收 tag。随后在独立
> 硬件诊断分支按 1/2/4/8/10 MHz 冷启动扫频，使用仓库分析器记录 DTM hash、
> BUSY、CV、温升和画面。10 MHz 全部门禁通过前不测试 20 MHz。不得根据
> SPD1656 猜测 SPD1657B LUT/局刷命令；取得厂商资料前不改波形、高压或
> power-cut 序列。N7 独立最小 sweep 固件、1/2/4/8/10 MHz fixed runner/finalizer/analyzer
> 已实现，但尚未刷入或真屏执行；离线分析器、六色抖动预览或 CI 通过均不等于真屏验收。
> 主机色彩管线已经强制绑定
> `0黑/1白/2黄/3红/5蓝/6绿` 并默认拒绝未校准整屏输出；仍须回填受控
> D65/2deg 六色 Lab 色板，再比较真屏抖动效果。
> G1/S1 显示器模拟基线现已完成：10 条路径包括 C2 基线、legacy nearest-two
> 蓝噪声对照、六码面积 Bayer/蓝噪声、多色 DBS 和重叠感知 DBS；v2 页面显示
> source/mapped/final/model 四张 hash 绑定预览。该路径永远
> `offline_verified=true/formal_upload_authorized=false`，不得把软预览 PNG 或 synthetic
> profile 直接送往设备。首个冻结 `area-weighted-ordered-8x8` 候选经独立单次授权
> 执行后，job2/op2 在 DRF 60010 ms 超时，POF cleanup 30005 ms 仍未闭环；帧和双
> DTM hash 精确匹配，用户实体断电，原授权永久消费，算法评价保持 `inconclusive`。
> 随后固定 MAP recovery job3/op3 以 181/21700/140/5 ms 完成
> PON/DRF/POF/post-PSR，真屏显示、电流、温度、TP1 和断电 GPIO 均通过。
> 低空间诊断 bundle
> `.test-output/hardware/G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430/` 的 manifest
> 原始 SHA-256 为 `07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d`，
> frame SHA-256/FNV-1a 为 `ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65`
> / `0xA9641618`，CS1/CS2 DTM FNV-1a 为 `0xCB085C03` / `0x9ABD749A`；当时 J2-P1 已在
> 持续监督会话中接通，non-displaying ingress 返回 `epd_action=none`、未刷新且 job 不变。
> attempt `38352ce6bc564530917c43099fe8d20a`
> 在 `.test-output/hardware/G1S1_LOW_SPATIAL_DIAGNOSTIC_RUN1_20260806_232200/` 完成
> job4/op4，PON/DRF/POF/post-PSR `181/21690/140/5 ms`、总时长 34169 ms。用户确认真屏
> 与 strict preview 一致，3.3 V CV、电流、温度和 GPIO idle 正常；J2-P1 在继续监督会话
> 中保持接通。裁定 `NOMINAL_DIAGNOSTIC_PASS` 只说明全局终态直方图和全局 6×6 计数
> 不是各自单独充分原因；空间频率和半屏负载尚未分离。row-major MAP-mask 图案不保留
> 源图语义，难看不计画质。job2 仍 `inconclusive`、根因未关闭、无算法 qualification。
> 下一步只做源图保真的质量轨离线预览并补 measured profile、每色光学核与独立
> qualification gate；当前没有下一次可见刷新授权。
> 扩展颜色/亮度可行性与 TODO 已记录，状态为 `PENDING / NOT STARTED`；用户未
> 明确排期前，不建立未知码实验固件、不刷 COM8、不调用刷新 API。若启动，先做
> 资料和测量系统、六色基线、恢复 pilot 与 6×6 转换矩阵，再单独审批小面积
> `0x4/0x7`；`0x8..0xF` 只作为后置 bit3 alias 测试。正式 `/api/frame` 的六色
> guard 不得放宽，LUT/内部 phase/高压仍受 SPD1657B/OTP 一手资料硬门禁。
>
> C4/N6 应用层软件合同、本地中止隔离锁和真实 Chromium formal E2E 已完成；远端 job
> 可能继续时必须保持新提交锁定，进程重启前人工核对设备 idle 与安全收尾。后续仍待的是
> 外部门齐全后的受控可见设备验收、C2/N5 真屏测色和 N7 扫频。通用
> `VISIBLE_REFRESH_GO` 仍默认 NO-GO；本次已消费的
> 候选、固定 MAP recovery 和低空间诊断的单次授权都是受监督例外，不得复用或推广：急停三次
> 假负载验证、电压/电流/温度测量链和经审查的数值 limit profile 未补齐前，只执行
> T0、经授权的 J2-1 断电 T2 和 T3 无刷新检查；T5 只允许在门禁补齐后单次执行。
> T6 内置页可见刷新、T7 pilot/正式数据和 T8 继续 BLOCKED。Rev B-mini
> H1 第一轮已经记录，但没有启动原理图/PCB：当前建议以
> `ESP32-S3-WROOM-1-N8R8` 邮票孔射频模组作为首选架构候选，保留 8 MB Flash/
> 8 MB OPI PSRAM；裸 SoC 不用于首版，XIAO ESP32-S3 Plus 只作为快速工程样
> 对照。若 WROOM 仍不能满足机械尺寸，可评估约 7×7 mm 的
> `ESP32-S3-PICO-1-N8R8` SiP，但必须接受 4 层、RF/天线和 EMC 验证。
> 用户场景是低频刷新相框，当前不升级 ESP32-P4：浏览器/服务器 API 承担
> 高质量确定性量化，S3 负责联网、TF 缓存、hash/签名/色码验证和刷新；
> 本地基础量化仅作离线后备。P4 只有在完全离线大图/视觉任务且 S3 有实测
> 不达标证据时才重开选型。
> 增加板边 TF 卡槽，首版优先独立 SPI；EPD 3.3 V 经过软件可控 load
> switch。产品电源采用一颗有足够瞬态能力的 3.3 V buck-boost 分支供 ESP32、
> TF 和 EPD，而不是默认从开发板 3V3 引脚供驱动板。DevKit 3V3→J2-1 仅可在
> 用户当次授权、断开外部 J2-1 电源并完成电流/跌落/温升监测后作诊断。
> L1/L2 初评建议先验证 15 µH 高性能 5030，4040 仅作测流后的实验；不得在
> 未测峰值/RMS和温升前冻结更小器件或修改 Rev A1。Rev B 继续集成 USB-C
> 烧录/供电、单节锂电充电、power-path 和 3.3 V buck-boost，默认沿用已验证
> 的双独立片选 GPIO 与 MF-1750 高压拓扑。H2 前还需用户确认模组/XIAO 分支、
> TF 机械、电池尺寸容量、USB-C 功能、天线、目标板尺寸和是否允许 4 层。
