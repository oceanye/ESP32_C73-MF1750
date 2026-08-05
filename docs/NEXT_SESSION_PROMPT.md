# 下一阶段新对话启动提示

复制以下内容到清空后的新对话：

> 请先完整阅读工作区中的
> 根目录 `README.md`、
> `docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`、
> `docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`、
> `docs/H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md`、
> `docs/REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md`、
> `docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`、
> `docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`、
> `docs/MF1750_DRIVER_API.md`、
> `docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md`、
> `docs/EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md`、
> `docs/TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`、
> `docs/C1_HOST_FRAME_HANDOFF_2026-08-04.md`、
> `docs/C5_HOST_CI_HANDOFF_2026-08-04.md`、
> `docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`、
> `docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md` 和
> `docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md`。
> MF-1750 Rev A1 已于 2026-07-13 提交嘉立创，生产文件被冻结，禁止重新生成、
> 覆盖或把 Rev B 文件写回该目录。当前首板已拆 R15、装 R16=0 Ω：GPIO7=CS1、
> GPIO10=CS2；两颗 SPD1657B revision 均为 0x04，分别写 CCSET(0xE0)=0x01 后，
> 100 kHz 完整 1024x600 六色色条、颜色顺序和中缝已经实屏通过。
>
> 当前源码候选 build tag 为
> `MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05`，
> driver API 为 `MF1750_R16_CASCADE_V3`；RC2F 在 RC2E 交互构图上增加
> `163.84×97.20 mm` 有效区、`0.160×0.162 mm` 非正方形像素和 158 PPI 预览，
> 尚未刷写。RC2D 已完成断电刷写与 Wi-Fi/网页运行验证，
> 但没有在该 build 上执行面板刷新。
> 最近完成实机验收的 RC2C/V3 已在 100 kHz 与正式 1 MHz
> 显示完全正确的 MAP_ORIENT_V1，并确认 PON/DRF/POF BUSY、完整/双 DTM 哈希、
> 电源、温度与断电安全状态；实测同时证明
> POF 后 PSR 写寄存器不会再次拉低 BUSY，RC2C/V3 因而把该采样改为信息证据。
> 它保留非法六色色码的双层拒绝，并把
> diagnostic report 以匹配 operation ID 的不可变快照与产生它的 job/build 绑定，
> 未观察到正式阶段 BUSY 会 fail closed。主机修正点 `2b19f75` 已通过 repository
> contract、203 项全仓 unittest、PlatformIO build 和 GitHub CI run `30917129233`；
> D0 实测详见级联整屏验证文档。默认认为驱动板断电，未经我明确确认，不得刷写
> COM8、访问设备 HTTP 刷新接口或要求上电。
> 下一步先生成 H0 只读 archive、SHA256 manifest，并由用户明确授权后创建硬件
> 验收 tag。随后在独立
> 硬件诊断分支按 1/2/4/8/10 MHz 冷启动扫频，使用仓库分析器记录 DTM hash、
> BUSY、CV、温升和画面。10 MHz 全部门禁通过前不测试 20 MHz。不得根据
> SPD1656 猜测 SPD1657B LUT/局刷命令；取得厂商资料前不改波形、高压或
> power-cut 序列。当前固件没有参数化 sweep action；离线分析器、六色抖动预览或
> CI 通过均不等于真屏验收。主机色彩管线已经强制绑定
> `0黑/1白/2黄/3红/5蓝/6绿` 并默认拒绝未校准整屏输出；仍须回填受控
> D65/2deg 六色 Lab 色板，再比较真屏抖动效果。
> 扩展颜色/亮度可行性与 TODO 已记录，状态为 `PENDING / NOT STARTED`；用户未
> 明确排期前，不建立未知码实验固件、不刷 COM8、不调用刷新 API。若启动，先做
> 资料和测量系统、六色基线、恢复 pilot 与 6×6 转换矩阵，再单独审批小面积
> `0x4/0x7`；`0x8..0xF` 只作为后置 bit3 alias 测试。正式 `/api/frame` 的六色
> guard 不得放宽，LUT/内部 phase/高压仍受 SPD1657B/OTP 一手资料硬门禁。
>
> H0 完成后优先移交 C4 应用层；C2 真屏色彩和 R1 扫频可独立推进。Rev B-mini
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
