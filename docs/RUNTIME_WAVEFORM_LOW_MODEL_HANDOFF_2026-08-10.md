# Runtime waveform 扩色：低级模型接续手册

文档日期：`2026-08-10`  
唯一总状态入口：`docs/STATUS_HANDOFF.md`  
适用范围：清空聊天上下文后，由较低级别模型继续完成确定性的离线代码、测试和文档工作

## 0. 先读结论

- 用户已明确确认 **J2/驱动板电源断开**；面板停在干净全白，ESP32 可保留 USB，但本阶段
  不访问串口、设备 IP，不上传固件，不触发刷新，不写 LUT。
- 当前 OTP profile 的 8 个 3-bit transport symbol 已全部真屏测试：形成 **7 个视觉组**，
  `code 4` 与 `code 7` 肉眼等色；六码初态也没有把二者分裂成新的历史态颜色。
- 想得到更多无抖动颜色，下一条有效路线是 **多个经批准的 runtime waveform profile**，
  不是继续重复现有 OTP 的 `0x4/0x7`。
- STM32 静态库反编译已恢复 `loadWF` 的真实返回 ABI、544-byte 解包入口及四次写命令；
  但随包 842-byte 文件只与一个不兼容的 `800+2+40` candidate layout 自洽，未提供配对
  loader/权威格式；现有 glue 又只选 master CS。
  当前仍没有可用于双控制器 3-bit 面板的匹配 loader/payload。
- 用户转述厂家说明：可“通过蓝牙传输设置亮度和对比度”。所给代码只证明 UART1 命令 5
  可下发 535-byte legacy waveform、命令 7 读取 VCOM、命令 8 改一个未校验的 raw VCOM
  byte；没有 BLE/GATT/App 实现，也没有独立 brightness/contrast 命令。蓝牙透明桥、App
  图像预处理、profile 选择/上传和电气参数控制目前均须视为待区分假设。
- 因此当前判定是 `SOFTWARE ENVELOPE READY / LIVE_RUNTIME_LUT_HARD_BLOCKED`。

当前软件进度：

| 子项 | 状态 | 下一动作 |
|---|---|---|
| P0a 自报合同熔断 | `DONE` | `execution_ready=false` 恒成立；dummy/伪装 opcode 回归已通过 |
| P0b 深证据与精确序列合同 | `DONE` | byte-backed evidence validator、空生产格式注册表和 test-only exact sequence 合同完成 |
| P1 零 I/O execution-plan | `DONE` | canonical manifest + immutable payload + P0 evidence 编译；生产默认 `BLOCKED_FORMAT_NOT_REGISTERED` |
| P2 默认 BLOCKED transport mock | `DONE` | host-only、compile gate=false、mock sink only；未加入 PlatformIO build |
| P3 12-action campaign/preview | `DONE` | 12 declarations/9 files/0 materialized/0 BIN；bundle 已冻结并深验 |
| P4 全回归与最终 handoff | `DONE` | final 145 passed/1 skipped；双环境 build SUCCESS；P4 evidence 已冻结 |
| 厂家样例深审计/STM32 反编译 | `DONE` | 两目录完整枚举，关键源/工程/库及 7 个 MAP 深审；真实 loader ABI、UART 5/7/8 控制面、版本断层、master-only glue 与 18 项 compatibility findings 已冻结 |

P4 历史冻结结果：P0--P3 runtime-waveform 专项 `57/57 PASS`；加入当时的 STM32 audit、
repo contract 和 EC5 recovery/compiled-identity 相邻回归后为 `145 passed, 1 skipped`。
本次 post-P4 厂家深审新增审计聚焦 `8/8 PASS`，相关定向联合回归 `95/95 PASS`；不把两次
快照简单相加。Ruff 与 py_compile PASS。默认与 recovery 环境均纯构建成功，未 upload。完整 P4 记录见
`RUNTIME_WAVEFORM_SOFTWARE_ENVELOPE_P4_2026-08-10.json`。

## 1. 清空上下文后的固定启动命令

只执行只读或离线命令：

```powershell
Get-Content docs/STATUS_HANDOFF.md -TotalCount 140
Get-Content docs/RUNTIME_WAVEFORM_LOW_MODEL_HANDOFF_2026-08-10.md
git status --short
python tools/mf1750_stm32_waveform_audit.py
python -m pytest -q tests/test_runtime_waveform_contract.py tests/test_mf1750_stm32_waveform_audit.py
```

预期：

- STM32 audit 返回 `compatibility_ready=false`，这是当前正确结果，不是测试失败；
- pytest 全部通过；
- 工作区很脏且有大量用户文件，禁止 reset、checkout、clean 或删除；
- 若 `STATUS_HANDOFF` 与本文冲突，以时间较新的 `STATUS_HANDOFF` 和原始 evidence 为准。

## 2. 证据边界

已经证明：

- 当前 ESP32 的双控制器 OTP 骨架可靠：每控制器 `512x600`、CS1/CS2 分别 DTM，
  两片分别设置 `CCSET 0xE0=0x01`，BOTH 执行 PON/DRF/POF，并有 BUSY timeout 和
  safe-finish。主要证据在 `src/epd_driver.cpp:541,847,1042,1193` 附近。
- STM32 2-bit 路径会设置 MCU-LUT 模式并向 `0x20` 写 535 bytes；其随包 writer
  只选择 master CS，TRES 又使用整屏 `1024x600`，没有形成可移植的双控实现。
- 对 ArmCC/CROF 静态库的可复现 Thumb 反汇编证明：真实 ABI 是
  `uint8_t loadWF(const uint8_t *)`，返回 `0/E1/E2`；成功时依次写 `0x01/6`、
  `0x30/1`、`0x20/535`、`0x21/704`。该 Cortex-M3 库不能链接到 ESP32，且这些长度
  仍不能证明字段语义、双控 segment 或当前面板兼容性。
- REG 的 UART 帧以 `41 41` 开头，带大端长度、command/subtype、CRC-16 和 `0D` 结尾；
  command 5/7/8 分别进入 waveform upload、VCOM read、raw VCOM set。SET 主循环只 ACK，
  raw byte 无范围/单位，后来仅可能在 legacy master-only 初始化中以 `vcom | 0x80` 生效。

尚未证明，禁止推断：

- 当前面板/批次的 plaintext decoded 3-bit LUT 及 `0x20/0x21` 精确分段；
- 842-byte 样例所需的权威 800-byte 数据段语义、兼容 loader/ABI 和同版发布配对；
- VCOM、VGH/VGL、VSH/VSL、PLL/frame/phase 的寄存器换算与批准范围；
- RAM LUT 后如何确定地恢复 OTP 模式，以及 reset 是否足够；
- LUT 是否可以广播、是否可读回、两片控制器是否必须相同载荷。
- 厂家蓝牙模块/App 的 GATT 或透明串口合同，以及 brightness/contrast UI 值究竟映射到
  host 图像处理、waveform/profile 还是 VCOM/其他寄存器；尤其没有证据批准 raw VCOM 扫描。

## 3. 低级模型可以连续完成的工作

严格按顺序执行；每一阶段完成后先更新 `docs/STATUS_HANDOFF.md`，再进入下一阶段。

### P0：加固离线资格合同

目标：任何自报布尔、dummy payload 或无害命名的危险 opcode 都不能产生
`execution_ready=true`。

要求：

1. 明确区分 `offline_contract_complete` 与 `hardware_execution_eligible`；在独立 evidence
   bundle validator 完成前，后者及 `visible_refresh_authorized` 必须恒为 false。
2. candidate 必须绑定 panel batch、controller revision、reviewer、双 payload identity、
   format document、loader source、批准电气参数和恢复证据；缺一项即稳定 blocker。
3. 操作计划使用 exact opcode allowlist、参数长度、顺序和 controller target；不能仅按
   `name/purpose` 文本过滤。未知 opcode 和任何 OTP/nonvolatile opcode必须拒绝。
4. 当前不知道的 3-bit format 不得注册；不得用 535/842/544 猜一个格式 ID。
5. CLI 的 `require-ready` 在当前证据下必须返回非零。

验收：

```powershell
python -m pytest -q tests/test_runtime_waveform_contract.py
python -m ruff check host/runtime_waveform tools/mf1750_runtime_waveform_contract.py tests/test_runtime_waveform_contract.py
python -m py_compile host/runtime_waveform/contracts.py host/runtime_waveform/virtual_palette.py tools/mf1750_runtime_waveform_contract.py
```

测试必须覆盖：1-byte dummy、空 commands、危险 opcode 配无害名称、单控制器、hash/长度
不匹配、null reviewer/batch/revision、零电气值、未知 format，以及“字段完整但仍不可硬件执行”。

### P1：实现零 I/O execution-plan 编译器

目标：先把未来 loader 的输入收敛为可测试的不可变命令计划，不触碰 Arduino/GPIO/SPI。

建议文件：`host/runtime_waveform/execution_plan.py` 和
`tests/test_runtime_waveform_execution_plan.py`。

固定行为：

- 输入只能来自通过 P0 的 canonical manifest 和作为 immutable bytes 读取的 CS1/CS2 payload；
- 未注册 format 一律返回 `BLOCKED_FORMAT_NOT_REGISTERED`；当前仓库应没有注册 format；
- 输出记录每一步的 controller target、opcode、payload length/SHA 和 predecessor identity；
- 任何 payload byte 都不得出现在日志/JSON，只输出长度和 SHA-256；
- 计划不得包含 GPIO/SPI/HTTP/serial callback，也不得产生 authorization token；
- 为将来保留的设计顺序只能表示为约束，不能冒充已批准寄存器序列。

测试：重复输入确定性、任一字段篡改、CS1/CS2 交换、缺段、未知 opcode、顺序改变、
单边失败模型和 canonical hash。当前所有真实候选仍应 fail-closed。

### P2：实现编译期禁用的 transport 状态机骨架

只有 P0/P1 全通过后执行。该阶段仍不得增加可运行的 LUT profile。

固定边界：

- 新骨架不加入任何现有 PlatformIO environment 的 `build_src_filter`；
- 默认构建和 EC5 recovery 构建的 binary identity/行为不得改变；
- transport 只接受 mock sink；不得调用 `epdCommand`、`epdData`、GPIO、SPI 或网络；
- 初始状态恒为 `BLOCKED_NO_REGISTERED_PROFILE`；
- 预留的状态顺序为：preflight identity → 两片 profile plan → CS1/CS2 count/hash →
  DTM count/hash → BOTH refresh → safe finish；这是软件状态模型，不是硬件放行；
- 任一错误只能进入 terminal fault，不自动 retry、切 profile、恢复或刷新。

必须做 mock 测试：双 CS 成功轨迹、CS1/CS2 payload/hash/length mismatch、第二片失败、
BUSY timeout、POF timeout、非法重入、重复 execute、错误后重试和 opcode 注入。

### P3：预制多 profile campaign，但保持不可物化

生成 manifest、布局、pseudocolor preview、人工记录表和 action DAG；在真实 profile 缺失时
所有 action 标记 `materialized=false`、`visible_refresh_authorized=false`，不得生成可刷 BIN。

首轮冻结为 12 个 action：

| 序号 | 动作 | 目的 |
|---:|---|---|
| 1–2 | K0（OTP 等价 runtime）八码 atlas → OTP 白恢复 | 证明 loader/profile 基线等价与恢复 |
| 3–4 | C1 八码 atlas → OTP 白恢复 | 一次同屏筛 C1 的直接颜色 |
| 5–6 | C2 八码 atlas → OTP 白恢复 | 一次同屏筛 C2；此处为第一 safe stop |
| 7–9 | C1 `8x8 old→new` primer → target → OTP 白恢复 | 两张矩阵覆盖 64 个 transition |
| 10–12 | C2 同构矩阵 → target → OTP 白恢复 | 筛选历史依赖；最终恢复 |

约束：无抖动；每个 atlas 同屏包含 8 个 transport code；CS1/CS2 镜像/反序以发现单边或
位置效应；矩阵 ROI 不放文字；每个动作单 ARM/单 EXECUTE/单 driver call；无自动重试或
恢复。K0/C1/C2 均为占位身份，不得伪造 payload/hash。

目标口径：先寻找 `10–12` 个稳定可测状态，再决定是否探索 16 色；这是研究目标，不是
颜色数量承诺。不同 profile 的颜色通常不能在一次刷新中任意共存，必须报告 profile switch
或 multi-pass 成本。

### P4：回归、构建与 handoff

在仍无外部 profile 时，只允许：

- 跑全部新增 Python 测试、Ruff、py_compile；
- 构建现有默认/EC5 recovery 环境，证明未引入回归；
- 冻结测试输出、源文件 SHA、测试计数和 blockers；
- 更新 `STATUS_HANDOFF` 为 `SOFTWARE ENVELOPE READY / LIVE HARD BLOCKED`。

不要创建名称中含 `runtime-waveform-live` 的 PlatformIO 环境，不要生成授权串，不要连接
COM8，不要读取设备状态。现有真屏固件和 NVS ordinal 不得改变。

## 4. 必须停止并交回高级审查的条件

出现下列任一情况，低级模型不得继续自行判断：

- 新增 `loadWF` 源码、ESP32 库、plaintext LUT、格式文档或供应商参数；
- 新增蓝牙 App/固件、GATT 定义、packet capture，或厂家对 brightness/contrast 的映射说明；
- 需要决定 `0x20/0x21` 长度、分段、controller target 或寄存器顺序；
- 需要选择/换算 VCOM、VGH/VGL、VSH/VSL、PLL、frame、phase 或温区；
- 有人要求解除 compile gate、生成可刷 runtime-LUT BIN、访问 COM8/设备 IP或真屏；
- 需要判断 OTP 等价、恢复资格、readback 等价或 sacrificial-panel 安全性；
- 测试失败涉及现有 ESP32 OTP 驱动、BUSY 或 safe-finish 行为。

交回时报告：变更文件、命令与完整退出码、失败测试、当前 blocker、未执行的硬件动作，
并保持 J2 状态不作推断或控制。

## 5. 解除硬阻断所需外部输入

至少需要以下全部内容，并由高级模型/人工独立审查：

1. 当前 panel serial、batch、两片 controller revision 与匹配声明；
2. 当前 M009/温区的 plaintext decoded 3-bit profile，或可移植 `loadWF` 源码/ESP32 ABI；
3. `0x20/0x21` 的字段、精确长度、目标 CS、顺序和完整格式文档；
4. VCOM、各高压轨、PLL/frame/phase、温区及允许偏差；
5. K0 OTP-equivalent runtime profile 和逐字节/光学/电气等价验证方法；
6. runtime→OTP 恢复语义、已验证恢复 profile、白恢复合同和最大尝试次数；
7. readback 或等价完整性证据；若无 readback，必须有发送计数/hash与供应商认可的替代门；
8. 牺牲屏、硬件限流、实时电流/温度监测和物理硬切断条件；用户已报告器材具备，
   但首次上机前仍须记录设备身份、校准/采样方式、告警/切断阈值和操作责任人；
9. 蓝牙模块/整机/官方 App 型号和版本、GATT UUID/属性/分包/ACK（或透明串口明确合同），
   以及只改变 brightness/contrast 单一档位时的蓝牙包、对应 UART 帧和最终 EPD write trace；
10. brightness/contrast 的单位、范围、默认值、持久化、生效时点、readback、光学验收定义，
    及其与 host preprocessing、profile/file SHA、waveform scale 或寄存器的精确映射；
11. vendor/panel-owner review identity 与独立 reviewer 结论。

外部材料不齐时，没有“预计多久上屏”的可信倒计时；只能报告代码阶段完成度和明确 blocker。

## 6. 完成定义

低级模型的本轮任务在以下条件同时满足时完成：

- P0–P4 中所有不依赖外部材料的项目完成；
- 所有新增测试通过，现有相关回归通过；
- 任何路径都不能把当前 535-byte、842-byte 或 dummy payload 升级为 hardware-ready；
- 没有设备访问、刷写、刷新或授权消费；
- `docs/STATUS_HANDOFF.md` 已更新，清楚列出已完成项、外部 blocker 和下一条唯一入口。

此后状态应是：**代码执行封套和测试计划已备好；收到真实 3-bit 资料后先回高级审查，
审查通过才进入可刷固件实现与真屏计划。**

## 7. 2026-08-10 P4 最终接续状态

- P0a--P4 所有不依赖外部材料的工作已经完成；唯一当前状态仍以 `STATUS_HANDOFF.md` 为准。
- 生产 `REGISTERED_FORMATS` 为空；compile gate=false；K0/C1/C2 均无 profile/payload hash；
  12 个 action 全部 `materialized=false`、`visible_refresh_authorized=false`。
- placeholder bundle：
  `.test-output/offline/MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1/`；
  campaign canonical=`440060467661ee04048f4301bbe263a6c48dc9232c75782083bfbe8957aff5d4`。
- P4 证据：`RUNTIME_WAVEFORM_SOFTWARE_ENVELOPE_P4_2026-08-10.json`。当前 worktree 的默认
  build 两次稳定为 815744 bytes / `7f7468d3...6480`，与 8 月 9 日旧源码期身份不同；本轮未改
  `src/` 或 PlatformIO 配置，且该 build 不替代冻结 RC2G。EC5 recovery 仍精确为
  791616 bytes / `f8f86fca...e793`，与当前实测固件一致。
- 首轮相邻回归曾因两个 PlatformIO 配置复用并清理 `.pio/build`，缺 recovery BIN/ELF 而得到
  1 个环境性失败；补建 recovery、核对 exact SHA 后整组 `52 passed, 1 skipped`，最终合并
  `145 passed, 1 skipped`。原失败和处理均保留在 P4 JSON，没有伪装为首跑通过。
- 安全状态没有变化：没有访问 COM8、串口、设备网络或硬件，没有刷写、刷新、授权消费或
  LUT 下发；J2 与屏幕继续按用户最后确认记录为 OFF / 干净全白。
- 后续唯一软件动作是等待第 5 节全部外部材料；材料到达即触发第 4 节硬停止，先交回高级/人工
  独立审查，不直接实现 live loader，不生成 `runtime-waveform-live` 环境或可刷 BIN。

## 8. 2026-08-10 厂家样例追加深审计

- `E6_73_sample code_V1.2_20250116` 是 MSP430、EL073 V2、单 CS、`800x480`、
  固色 loop 与 4-bpp packing 一致的样例，不是当前 `1024x600` 双 SPD1657B 合同。V1.2 每次显示末尾切
  VDD，但 `main.c` 只初始化一次便连续调用七次显示，后续没有重新上电/初始化；只能借鉴
  单次刷新后的关断意图，不能移植寄存器、颜色码或时序。
- `REG-API-oqc` 混有 E5 3-bit、E6 13-inch 与 E5 2-bit 三套版本信息；Keil 实际入口是
  `User/main.c`，而示例 main 依赖缺失的 `WF00_05.h` 及未定义的 selector/init symbols。
- 当前库按 `544+2+wrapped-key` 读取；随包 `WF20_25[842]` 在 offset 544 得到越界长度
  5157，却在 offset 800 才出现自洽的 40-byte wrapper 字段。因此它是不同且不兼容的
  `800+2+40` candidate layout；没有配对 loader，不能提升为权威 ABI/有效 waveform，
  严禁传入当前 loader，也不得按文件日期猜测新旧关系。
- `loadWF` 没有 controller/CS 参数、BUSY、reset、refresh 或 OTP 恢复；随包
  `writeEPD` 只落到 master CS。当前资料不能证明 LUT 可以广播到双控制器。
- 厂家后续明确为“通过蓝牙传输设置亮度和对比度”。两套样例只给 115200 8N1 UART
  cmd5 waveform、cmd7 VCOM read、cmd8 unchecked raw VCOM set，没有 BLE/GATT/App 或
  brightness/contrast 映射；该信息仍是方向性线索，不是本批次批准档位。亮度应按反射式
  显示的受控照明 `L*`/reflectance 测量并同时记录色度，禁止猜测 VCOM、电压、phase、
  scaling factor，或把对比度 UI 标签当成已知寄存器。
- 深审计报告：`docs/MF1750_VENDOR_SAMPLE_DEEP_AUDIT_2026-08-10.md`；结构化输出：
  `.test-output/offline/stm32_vendor_deep_audit_20260810.json`；可复现逆向证据：
  `.test-output/offline/stm32_reverse_20260810T115353/`。审计器 schema3 聚焦测试 `8 passed`，
  相关定向联合回归 `95 passed`，Ruff、py_compile 与证据自验证均通过；
  `compatibility_ready=false`，18 项 compatibility findings（含 provenance warning）保持。
  辅助脚本仅在内存中解码 800-byte candidate 并保留 hash/谓词；未接受为 loader plaintext，
  未写出 raw key/waveform bytes，也未生成 live payload。
