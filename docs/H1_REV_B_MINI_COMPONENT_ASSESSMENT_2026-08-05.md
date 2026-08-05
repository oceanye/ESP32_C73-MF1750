# H1 Rev B-mini：器件与系统架构初步评估

文档日期：2026-08-05

状态：`PRELIMINARY / MEASUREMENT PENDING`

工作包：H1 Rev B-mini 面积、BOM 与一体化架构分析

评估源码基线：`3dfd477`

Hardware tested in this review: `NO`

Rev A1 ECO authorized: `NO`

Rev B BOM frozen: `NO`

## 1. 本轮新增需求

Rev B-mini 在缩小 L1/L2 和相关功率器件之外，新增以下明确设计输入：

1. 在新板上集成 ESP32-S3，比较裸 SoC、官方射频模组和带 USB 的完整小板；
2. 增加 microSD/TF 卡槽，用于本地图片、网络图片缓存和后续随机照片队列；
3. 增加 USB/电池电源模块，并验证 ESP32 与电子纸驱动是否可以共用 3.3 V；
4. 评估“USB 给 ESP32 开发板供电，再由开发板 3V3 引脚给驱动板 J2-1
   供电”的受控实验，但不预设它能成为量产电源方案。

本文件记录架构结论和设计门禁，不启动 Rev B 原理图/PCB，也不构成上电、
刷写 COM8、电子纸刷新或器件采购授权。

## 2. 决策摘要

当前推荐的 Rev B-mini 首版架构候选是：

- 主控使用 `ESP32-S3-WROOM-1-N8R8` 官方射频模组，以邮票孔/底部焊盘直接
  SMT 到主板；
- 不在第一版使用裸 ESP32-S3 SoC，也不把现有 DevKitC-1 整板焊到产品板；
- 若 WROOM 的机械包络仍过大，第二步评估 `ESP32-S3-PICO-1-N8R8` SiP；
  它保留 N8R8 内存但需要自研 RF/天线，不与首版混为同一风险等级；
- 主板自己实现 USB-C、ESD、BOOT/RESET、电池 power-path、3.3 V 稳压和
  电子纸电源开关；
- 增加独立 microSD/TF 卡槽，第一版优先使用与电子纸隔离的独立 SPI 总线；
- 候选电源架构由统一 3.3 V 稳压器分支供 ESP32、TF 卡和驱动板；容量与
  瞬态可行性仍须由 T-PWR-A 和叠加负载实测确认；
- 驱动板 3.3 V 分支必须经过软件可控、默认关闭、具有限流/软启动能力的
  load switch，对应固件 `EPD_PIN_SWC`；
- “从开发板 3V3 引脚带驱动板”只做诊断试验，不作为当前推荐原理图。
- 应用是低频刷新的相框，当前不升级 ESP32-P4；S3 负责联网、TF 缓存、
  帧校验和刷新，高质量量化优先由浏览器/服务器完成。

若优先目标是最快获得一块低数量工程样，而不是 BOM、厚度和电源架构最优，
可建立 `XIAO ESP32-S3 Plus` 邮票孔完整小板的对照版本。它不是当前默认的
首选架构候选。

## 3. ESP32 集成层级比较

“ESP32 芯片”“ESP32 模组”和“带 USB 小板”是三个不同层级：

| 层级 | 典型方案 | 已集成内容 | 优点 | 主要代价 | 当前结论 |
|---|---|---|---|---|---|
| 裸 SoC | ESP32-S3 QFN | MCU；部分具体变体可有封装内 Flash/PSRAM | 理论占用最小、引脚最自由 | 必须先冻结 SoC 变体，并为其未集成的 Flash/PSRAM 设计外部器件；仍需晶振、RF 匹配、天线、供电、USB 和 EMC/RF 验证 | 首版不采用 |
| SiP | ESP32-S3-PICO-1-N8R8 | MCU、8 MB Flash、8 MB OPI PSRAM、40 MHz 晶振 | 约 7×7 mm，保留当前 N8R8 内存且明显小于 WROOM | 仍需 RF 匹配、50 Ω 天线、USB/供电和整机 EMC/RF 验证；LGA 返修难 | **激进小型化候选** |
| 官方射频模组 | ESP32-S3-WROOM-1-N8R8 | MCU、8 MB Flash、8 MB OPI PSRAM、晶振、RF/天线 | 延续当前已验证内存配置，GPIO 足，RF 风险低于裸芯片 | 主板仍需 USB-C、稳压、BOOT/RESET；板载天线需要净空 | **首选架构候选** |
| 完整 USB 小板 | XIAO ESP32-S3 Plus 等 | MCU、Flash/PSRAM、USB-C、板载稳压/充电及按键 | 原型最快，可整板邮票孔焊接 | 重复器件、连接器和 PCB；高度/机械受限；电源路径不完全受控 | 工程样对照 |
| 现有大开发板 | ESP32-S3-DevKitC-1 N8R8 | WROOM、USB 转串口/原生 USB、稳压、排针 | 调试证据最完整 | 尺寸大且不是产品级邮票孔子板 | 仅保留台架 |

### 3.1 为什么优先 WROOM-1-N8R8

当前实物已确认是 N8R8，固件配置为 OPI PSRAM，完整帧固定为
`1024 × 600 × 4 bpp = 307,200` 字节；Web 上传入口还明确要求从 PSRAM
分配完整帧。因此 N8R8 是“已被本项目验证”的内存基线，而不是只根据数据手册
选择。

Espressif 当前官方资料给出的关键事实为：

- `ESP32-S3-WROOM-1-N8R8`：8 MB Quad SPI Flash、8 MB Octal SPI PSRAM，
  模组本体约 `18.0 × 25.5 × 3.1 mm`；
- `ESP32-S3-MINI-1-N8`：8 MB Flash、无 PSRAM；
- `ESP32-S3-MINI-1-N4R2`：4 MB Flash、2 MB Quad PSRAM，
  模组约 `15.4 × 20.5 × 2.4 mm`。
- `ESP32-S3-PICO-1-N8R8`：8 MB Flash、8 MB Octal SPI PSRAM 和 40 MHz
  晶振集成在约 `7 × 7 mm` LGA SiP 中，但不包含可直接照搬的板载天线。

MINI-1-N4R2 有进一步缩小的可能，但 2 MB PSRAM 尚未经过当前网页上传、
图像预览、TF 缓存和并发任务的内存压力验证。它只作为第二阶段“固件流式化后”
的候选。MINI-1-N8 没有 PSRAM，不作为当前等效替换。

N8R8 模组的官方推荐环境温度上限低于无 PSRAM/2 MB PSRAM 的部分型号，
H2 还应把封闭外壳内的最坏温度纳入模组选型，不能只按内存和面积冻结。

PICO-1-N8R8 是比裸 SoC 更合理的极限缩板路线，因为它保留本项目已验证的
Flash/PSRAM 容量并减少外部高速存储布线；但它仍属于自研 RF 产品，不具备
WROOM 模组直接提供的天线与模组级设计简化。只有确认具备 4 层板、阻抗控制、
RF/EMC 验证和 LGA 装配能力后，才把它提升为 H2 基线。

官方资料：

- [ESP32-S3-WROOM-1/WROOM-1U 数据手册](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)；
- [ESP32-S3-MINI-1/MINI-1U 数据手册](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.pdf)；
- [ESP32-S3-PICO-1 系列数据手册](https://documentation.espressif.com/esp32-s3-pico-1_datasheet_en.pdf)；
- [ESP32-S3 SoC 数据手册](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf)；
- [ESP32-S3 硬件设计指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/)。

### 3.2 完整邮票孔 USB 小板何时有价值

Seeed 官方资料显示，XIAO ESP32-S3 系列约为 `21 × 17.8 mm`；常规/Sense
规格表写 11 个 GPIO，Plus 的规格表写 18 个 PWM GPIO/2 路 SPI，而同页
Plus pin map 又列出 D0～D19。该官方页面内部存在计数口径差异，不能把 18
当作已冻结的可用总数。若选择完整小板，应按具体 Plus 板版逐脚审计启动绑带、
电池检测、板载功能和实际引出焊盘。

当前电子纸已占用 BUSY、RST、DC、CS1、CS2、MOSI、SCK 共 7 个控制信号；
TF 卡至少再需要 MISO 和 CS，软件控屏电源还需 1 个 GPIO。普通 XIAO 即使
共享 SPI 也只剩很少余量，不利于电池检测、卡检测、按键和后续调试。

XIAO 系列 Wiki 将板载 3V3 标为稳压输出并写明可抽取 700 mA，但 Plus v1.1
官方原理图中的 SGM6029 又标注 `Imax=600 mA`。应把它视为资料/板版差异，
按实际采购板版、原理图和稳压器丝印采用更保守边界。无论 600 mA 或 700 mA，
都不是“ESP32 正在 Wi-Fi 工作后仍可全部提供给外设”的剩余电流，因此不默认
用 XIAO 3V3 输出承载电子纸与 TF。

官方资料：

- [Seeed XIAO ESP32-S3 系列规格和引脚](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)；
- [XIAO ESP32-S3 Plus v1.1 官方原理图](https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/res/XIAO_ESP32S3_Plus_SCH_PDF.pdf)；
- 仓库既有对照：
  [Seeed XIAO/EE04 参考板评估](../hardware/seeed_xiao_reterminal_epaper_assessment.md)。

### 3.3 相框场景的图像量化算力

用户已明确应用是相框，不会高频刷新。当前正式 1 MHz 整帧实测总时间约
34.2 秒，因此该产品更关注功耗、可靠缓存和无人值守恢复，而不是把单张图片
量化压缩到毫秒级。

当前软件实际已经有两条非 MCU 量化路径：

- 设备网页中的 `quantizeAndPack()` JavaScript 在浏览器端执行，再向 ESP32
  上传精确 307,200 字节帧；
- `host.color_pipeline` 已有最近色、Floyd-Steinberg、Atkinson、Bayer 等
  主机量化和 provenance/校验能力。

ESP32 当前只接收、校验、缓存和显示规范帧；尚没有在 MCU 上解码任意 JPEG/PNG、
缩放并完成高质量六色量化的正式固件路径。

#### 推荐分层

| 层级 | 负责内容 | 当前定位 |
|---|---|---|
| 浏览器/电脑 | 人工选图、拖动/缩放/旋转、即时预览和量化 | 当前已具备 |
| 量化服务器 API | 下载或接收原图、解码、色彩管理、智能裁剪、六色抖动、生成预览和规范帧 | **推荐自动相框主路径** |
| ESP32-S3 N8R8 | Wi-Fi、API 调用、哈希/签名/色码校验、TF 缓存、任务调度和刷新 | **推荐设备职责** |
| ESP32-S3 本地后备 | 读取 TF、基础 JPEG 解码、简单最近色/有序抖动；允许较慢 | 后续可选 |
| ESP32-P4 + 网络协处理器 | 大图本地解码/缩放、复杂 UI、相机或本地视觉任务 | 当前不采用 |

六色量化本质上是确定性的色彩与抖动算法，不要求 AI 模型。AI 服务器可以用于
主体识别、自动裁剪、构图评分或照片筛选，但最终 palette mapping、色码合法性
和输出哈希应由版本化、可复现的确定性管线完成。

#### 为什么当前不需要 ESP32-P4

ESP32-P4 的硬件 JPEG codec 和 PPA 确实能加速 JPEG 解码、缩放、旋转、镜像和
混合，并可配更大的 PSRAM；但 PPA 不等于直接加速本项目的六色色差搜索和误差
扩散。更重要的是，P4 本身不提供本项目所需的一体化 Wi-Fi 路径；Espressif
官方 P4 功能评估板另配 ESP32-C6-MINI-1 承担 Wi-Fi/Bluetooth。对于低频相框，
这会增加第二颗主芯片、供电、通信、固件和 PCB 面积，收益不足以抵消复杂度。

只有出现下列任一条件并由 S3 实测证明不足，才重新评审 P4：

- 必须完全离线处理高分辨率 JPEG/PNG，且量化延迟有明确秒级上限；
- 需要相机、复杂本地 UI、视频/动画或本地视觉 AI；
- S3 的流式/分块实现仍无法满足峰值内存；
- S3 完成一次任务的能耗经实测反而高于 P4 + 网络协处理器方案；
- 产品已接受双芯片、4 层板和更复杂电源。

官方资料：

- [ESP32-P4 数据手册](https://documentation.espressif.com/esp32-p4_datasheet_en.pdf)；
- [ESP32-P4 硬件 JPEG codec](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/peripherals/jpeg.html)；
- [ESP32-P4 Pixel-Processing Accelerator](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/peripherals/ppa.html)；
- [ESP32-P4 官方评估板的 ESP32-C6 网络架构](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html)。

#### 服务器量化 API 最低合同

服务器可接收原图本体，或接收经过 allowlist 限制的照片 source ID/URL。推荐
异步接口：

    POST /v1/epd/quantize
      image 或 source_id
      fit / crop / rotation
      dither_mode
      palette_id + palette_sha256

    GET /v1/epd/jobs/{job_id}
      status
      preview_url
      frame_url
      manifest

结果 manifest 至少绑定：

- `width=1024`、`height=600`、`format=epd6-4bpp`、`bytes=307200`；
- `source_sha256`、`frame_sha256`、palette ID/hash、算法和参数版本；
- 允许色码固定为 `0/1/2/3/5/6`；
- 服务器签名或 HMAC、生成时间、过期时间和可选 preview hash。

ESP32 下载后仍须自己检查长度、色码、hash/签名，原子写入 TF，再允许刷新。
网络失败时先使用 TF 中已验证的旧帧；不得把服务器超时转换成盲目重刷。

## 4. microSD/TF 卡设计

### 4.1 功能定位

TF 卡用于：

- 保存用户上传的原始图片和已量化六色帧；
- 缓存网络位置读取到的照片，避免每次刷新都依赖在线下载；
- 维护随机播放队列、已显示历史和下载失败重试状态；
- 保存配置、标定色板和可导出的诊断记录。

首版采用 3.3 V microSD 卡槽，优先布置在板边，支持无工具插拔。卡检测开关
为推荐项，不是第一版启动硬门禁。

### 4.2 总线建议

当前电子纸固定信号为：

| 信号 | GPIO |
|---|---:|
| BUSY | 4 |
| RST | 5 |
| DC | 6 |
| CS1 | 7 |
| CS2 | 10 |
| MOSI/双向寄存器数据 | 11 |
| SCK | 12 |

Rev B 还需预留：

- `TF_MISO`；
- `TF_MOSI`；
- `TF_SCK`；
- `TF_CS`；
- 可选 `TF_CD`；
- `EPD_PWR_EN`。

第一版推荐 TF 使用独立 SPI host 和独立引脚，理由是：

1. 当前电子纸 REV 等寄存器诊断读取路径会把 GPIO11 临时切换为输入；正常
   整帧刷新不必然执行该动作，但共享会扩展 D0 的 GPIO 方向合同；
2. 刷新完成/断电安全状态会把 EPD 的 SCK、MOSI、CS1、CS2 拉低；
3. microSD 共享 SPI 初始化要求其他设备 CS 保持高；
4. 共享总线会迫使已经实屏验收的 D0 驱动改变片选和断电安全策略。

因此“共享 SCK/MOSI、只新增 TF_MISO/TF_CS”在电气上可研究，但不是首版
无条件连接。若后续为了省 GPIO 共享，必须同时具备：

- EPD 3.3 V 负载开关和无反灌验证；
- TF/EPD 总线互斥和事务锁；
- 上电最先初始化 TF，并在此期间让所有 EPD CS 保持高或让 EPD 物理断电；
- SPI mode、时钟频率和引脚方向的完整恢复；
- TF 读写期间禁止启动刷新，刷新期间禁止文件系统访问；
- 断电/拔卡/写入中断后的文件系统恢复策略。

Espressif 的 SD SPI 资料要求 CMD 和 DAT0-DAT3 具备外部上拉；即使 SPI 模式
没有使用全部数据线，也不应让卡端相应输入悬空。第一版应按卡座和官方参考
设计放置外部上拉、就近去耦/储能电容，并在外露触点侧增加 ESD。精确阻值、
电容值、卡座和引脚在 H2 原理图评审时冻结。

官方资料：

- [ESP32-S3 SD 上拉要求](https://docs.espressif.com/projects/esp-idf/en/release-v4.4/esp32s3/api-reference/peripherals/sd_pullup_requirements.html)；
- [SD 卡与其他 SPI 设备共享总线约束](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32s3/api-reference/peripherals/sdspi_share.html)。

## 5. 3.3 V 电源架构

### 5.1 推荐量产路径

若保留单节锂电，推荐路径为：

    USB-C VBUS
        │
        ├─ ESD / 输入限流
        │
        └─ power-path 充电器 ── SYS ── 3.3 V buck-boost ──┬─ ESP32-S3 模组
                     │                                    ├─ TF 卡分支
    单节锂电池 ──────┘                                    └─ 限流 load switch ── EPD J2-1

这叫“共用一颗 3.3 V 稳压器、分支供电”，不是“由 ESP32 给驱动板供电”。
ESP32-S3 芯片本身不是 3.3 V 电源；开发板上的 `3V3` 只是其板载稳压器的
同一条电源轨。

电源实施要求：

- 3.3 V 主稳压器按 ESP32 Wi-Fi、TF 写卡和 EPD 刷新的叠加最坏瞬态选型；
- 原理图/封装先预留 2 A～3 A 级转换器和相应铜宽/储能能力，最终额定值由
  实测冻结，不把该预留值写成已测需求；
- ESP32、TF、EPD 三个分支各自就近去耦，避免通过细长公共颈部串接；
- EPD 分支具有默认关闭、软启动/限流、反灌隔离和 GPIO 控制；
- 保留 VBUS、BAT、SYS、3V3、EPD_3V3 的电压/电流测点；
- 单节锂电覆盖约 4.2 V 到约 3.0 V，优先 buck-boost；USB-only 版本才可
  单独评估 buck/LDO。

Espressif 对 ESP32-S3 单独供电的通用建议已经是 3.3 V、输出能力不少于
500 mA，并要求电源入口至少 10 µF 及适当去耦。这只覆盖 ESP32 设计入口，
不能覆盖 TF 和电子纸驱动的额外负载。

官方资料：

- [ESP32-S3 原理图/供电检查表](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html)。

### 5.2 为什么当前不能直接批准 DevKit 3V3 → J2-1

现有实机证据是：

- ESP32-S3 DevKitC-1 由 USB 单独供电；
- Rev A1 J2-1 由外部 3.3 V、1 A 限流电源单独供电；
- 两者只共地；
- 完整刷新时外部电源保持 CV，用户确认电源和温度正常。

这组证据没有记录驱动板峰值/平均电流，也没有证明 DevKit 板载 3.3 V 稳压器
有足够余量。Espressif 的 DevKitC-1 文档只规定 USB、5V pin 和 3V3 pin 三种
输入方式必须互斥，没有给出可供外设使用的 3V3 剩余电流。

证据：

- [Rev A1 软件矩阵安全供电](REV_A1_SOFTWARE_MATRIX_TEST_2026-07-30.md)；
- [Rev A1 R16 整屏结果](REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md)；
- [ESP32-S3-DevKitC-1 官方指南](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html)。

所以该连接可以安排成一次受控诊断试验，但通过也只证明“这块具体 DevKit、
这根 USB 线和当前刷新条件可工作”，不能直接冻结 Rev B 电源 BOM。

## 6. 后续电源验证任务

### T-PWR-A：共用外部 3.3 V 主电源

目的：先验证“ESP32 + EPD 可以共用同一条合格 3.3 V 主轨”，不经过开发板
板载稳压器。

前置条件：

- 只使用一个电源入口；如果从 DevKit 3V3 pin 反向供电，则 USB 和 5V 输入
  必须断开；
- 外部 3.3 V 具备可编程限流，分别测 ESP32、EPD 和总电流；
- 保持 Rev A1 J2-1 可快速断开，并先执行无刷新启动。

顺序：

1. ESP32 空闲，不接 EPD；
2. ESP32 连接 Wi-Fi；
3. 接 EPD 逻辑电源但不刷新；
4. 执行一张已验收的单次完整帧；
5. 加入 Wi-Fi 上传与刷新叠加；
6. TF 样板具备后，再加入读卡、写卡与刷新叠加。

### T-PWR-B：USB → 当前 DevKit → 3V3 → J2-1

目的：回答用户提出的直接供电可行性，只作为台架诊断。

前置条件：

- J2-1 的外部 3.3 V 必须物理断开，禁止两个 3.3 V 源并联；
- 使用同一块已识别的 N8R8 DevKitC-1，并记录板卡版本和稳压器丝印；
- 在 DevKit 3V3 到 J2-1 间串入电流测量，示波器同时看 DevKit 3V3 和 J2-1；
- 从已验收的低风险画面开始，不进行未知码、扫频或自定义波形实验。

合格判据至少包括：

- ESP32 无 brownout、USB 断连或复位；
- J2-1 在刷新全过程保持在冻结的 3.3 V 容差内，无不可接受的瞬态跌落；
- DevKit 稳压器、USB 接口、L1/L2 和驱动 IC 温升不超过各自基线；
- PON/DRF/POF BUSY、刷新结果和高压释放与独立供电基线一致；
- 增加 Wi-Fi、TF 负载后仍满足相同门槛。

立即停止条件：

- 3.3 V 低于 ESP32/面板允许范围或出现明显振荡；
- 电源进入限流、ESP32 重启、USB 断连或 TF 掉卡；
- 稳压器、接口、电感或驱动 IC 异常升温；
- BUSY 超时、显示异常或 POF 后高压不能正常释放。

上述试验必须另行得到用户当次上电/接线/刷新授权；本文件不授权执行。

## 7. L1/L2 与其他功率器件结论

L1/L2 的详细候选、面积估算和测量门禁已经独立记录在：

- [Rev B-mini L1/L2 与相关功率器件小型化初步评估](REV_B_MINI_L1_L2_DOWNSIZING_ASSESSMENT_2026-08-05.md)。

当前系统级结论保持一致：

- 第一轮以 15 µH 高性能 5030 为基线；
- 4040 只作为取得峰值/RMS 电流后的实验选项；
- 4020/超薄高 DCR 方案不作为当前生产候选；
- 1210 电容、二极管、采样电阻和 MOSFET 必须按实际轨压、纹波、峰值和温升
  分别审查，不能仅按封装缩小。

## 8. H2 启动前尚未冻结的输入

用户当前已经给出“ESP32 + TF + 电源模块”的功能方向，但仍需在 H2 前冻结：

- 首版主控是否采用首选候选 `ESP32-S3-WROOM-1-N8R8`；
- WROOM 包络若不能满足目标尺寸，是否接受 PICO-1-N8R8 所需的 4 层、
  阻抗控制和 RF/EMC 验证；
- 是否需要同时做 XIAO ESP32-S3 Plus 工程样对照；
- 板载 PCB 天线还是 WROOM-1U 外置天线；
- TF 卡开口方向、是否需要 card-detect、目标卡容量和文件系统；
- 是否必须支持电池、USB 边充边刷、关机和深睡眠；
- 电池容量、最大尺寸、保护、接口和 NTC；
- 最大 PCB 长宽、总厚度、安装孔、FPC/USB/TF/开关的位置；
- 2 层与 4 层 A/B 是否允许；
- ESP32、TF、EPD 的定量峰值/平均电流及叠加瞬态；
- L1/L2 电流、SW 波形、高压轨和定量温升。

在这些输入与测量完成前，不创建 Rev B 生产目录、不冻结 BOM、不修改
`hardware/mf1750_production_v1/` 中任何 Rev A1 文件。

## 9. 下一步建议

1. 保持 Rev A1 冻结，完成 H0 archive/hash；
2. 先编制电流测量计划；用户单独授权上电后，再测 ESP32、EPD、Wi-Fi
   和后续 TF 的独立/叠加负载；
3. 用户单独授权后执行 T-PWR-A；T-PWR-B 只作为可选诊断；
4. 选定 WROOM-1-N8R8 主支路或 XIAO Plus 原型支路；只有机械目标确实
   排除 WROOM 时，才把 PICO-1-N8R8 作为 H2 主支路评审；
5. 完成 GPIO、启动绑带、USB、TF 与 `EPD_PWR_EN` 分配审计；
6. 冻结机械边界和电池输入；
7. 才进入 H2 原理图，并对 5030/4040 电感样板做 A/B。
