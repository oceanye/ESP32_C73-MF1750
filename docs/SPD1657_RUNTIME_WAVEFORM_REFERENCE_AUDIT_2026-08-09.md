# SPD1657 / E2802 运行时波形参考工程审计

文档日期：2026-08-09

审计对象：`参考资料/REG-API-oqc(1)(1)/REG-API-oqc/`

硬件访问：`NO`；未访问 ESP32、COM8、面板或刷新 API

> **2026-08-10 深审计补遗：** ARMCC/ORC 库已完成可复现的离线 Thumb 反汇编，
> 本文中“`loadWF` ABI/842-byte wrapper 尚无法确认”的旧边界已被更精确证据替代。
> `loadWF` 实际返回 `uint8_t`，成功写序列为 `0x01/6 → 0x30/1 → 0x20/535 →
> 0x21/704`；当前 loader 固定采用 544-byte 解包 ABI，而随包 `WF20_25[842]`
> 只与一个不兼容的 `800+2+40` candidate layout 自洽；没有配对 loader，不能提升为
> 权威 ABI 或有效 waveform。随包 glue 最终只操作 master CS，双控加载
> 仍未成立。另纳入 E6_73 V1.2 审计。用户后续转述厂家称可经蓝牙设置亮度/对比度；
> 样例目前只证明 115200 8N1 UART 的 cmd5 waveform、cmd7 VCOM read 和 cmd8 raw
> VCOM set，没有 BLE/GATT/App 或 brightness/contrast 映射，不能把 raw VCOM 当作安全
> 亮度旋钮。完整新结论见
> `MF1750_VENDOR_SAMPLE_DEEP_AUDIT_2026-08-10.md`；若与本文冲突，以补遗和新文档为准。

## 1. 结论

新增工程推翻了“SPD1657/E2802 只能使用片上 OTP、没有运行时 LUT 入口”这一过强
判断。源码给出了明确的 MCU LUT 模式、CRC bypass 和 `0x20` LUT 写入路径；配套库
也明确导出 `loadWF` 和 `LUT1_DATA`。库名包含 `3bits`，但对象实际记录的编译宏为
`E5_3Bit_Mode=0`，在缺少源码时不能断言 3-bit 分支已经启用。

但它尚不能直接移植到当前 ESP32 或真屏：

- 可读的 535-byte `wf_data` 是 E5 **2-bit**、四目标色表，不含可确认的蓝/绿 3-bit
  扩展表；
- `WF20_25.h` 是 842-byte 加密/校验封装，不是可直接写入寄存器的明文 LUT；
- `loadWF` 只提供 Cortex-M3/ArmCC 二进制库，没有可移植到 Xtensa ESP32 的源码；
- OQC 最后产物没有调用或链接加密库的 `loadWF`，但确实保留了另一条可由 UART
  更新的 535-byte 2-bit 明文 LUT 路径；该路径只选择 master CS，不能当成当前双控
  3-bit 安全实现；
- 2-bit 与 3-bit 样例对 `0x2/0x3` 的红黄命名互相冲突；
- 当前 `User/main.c` 比最后一个 M009F-T map/AXF 更新，已有产物不能证明当前源码可构建
  或可运行；
- 包内包含永久 OTP 编程代码和数据，绝不能进入当前实验路径。

因此状态应改为：

> 运行时 LUT **机制证据已获得**；当前屏匹配的 3-bit 波形格式、载荷、色码语义、
> 电压/温区和 ESP32 可移植实现仍未闭环。允许继续离线解析和实现 fail-closed
> 适配层，不允许据此刷入任意 LUT 或执行 OTP 编程。

## 2. 对象身份与可追溯哈希

| 对象 | SHA-256 | 说明 |
|---|---|---|
| 原始 ZIP | `c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead` | 17,297,740 bytes |
| `User/EDP_init.c` | `1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5` | 可读 535-byte 2-bit LUT 路径 |
| active `wf_data` 535-byte initializer | `716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b` | 仅冻结内容身份，不在审计输出中展开原始值 |
| `User/main.c` | `ecf13ad33af9dd51e982d3af2daaceb4d74a296618a8c513a06e136f3583387b` | 2026-06-02，晚于所有 M009F-T 输出 |
| `Sample Code/E28xx.c` | `7a7601f5baecdda5cfb8cd32780c878fff52c1bd44fe8551114e277976d6c2b3` | E2802/SPD1657 OTP 与 3-bit 显示样例 |
| `Sample Code/E28xx.h` | `829974a41a1c3c79588941aa28c8fec39fdd07beb1b41c062c75379e29615c47` | 声明 `loadWF`，但返回类型有矛盾 |
| `Sample Code/WF20_25.h` | `0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821` | E5 2-bit、842-byte 封装 |
| `lib/eload_3bits_M3_E2802_20251229.lib` | `f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b` | Arm Cortex-M3/ArmCC 静态库 |
| `Projects/MDK-ARM/atk_f103.uvprojx` | `2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8` | OQC 工程清单 |
| `Output/jiaxian-M009F-T_OQC_YX.map` | `f7b10f233ce26930293105ba7949b2963217f0c189e76d18b70be31207ce48dd` | 2026-05-29，最新 M009F-T map |
| 对应 AXF | `b346a46c67281f51dfc674010acba5621f83e1d9632da9d3b0abd34941154e44` | 早于当前 `User/main.c` |

该目录是多个时期、多个用途文件的集合，不应把目录名或文件共存本身当成兼容性证明。

## 3. 与当前 M009F-T 的一致证据

`User/LCDConfig.h` 将整屏配置为 `1024×600`；`Sample Code/E28xx.c` 为每颗控制器
设置 `512×600`，并向 master/slave 两片分别发送半帧。工程输出名包含
`M009F-T`。这些与当前 MF-17506-M009F-T、双 SPD1657B、1024×600 架构一致。

该一致性只证明参考价值较高，不证明其中每个波形文件都属于当前面板批次或当前 OTP。

## 4. 运行时 LUT 的直接证据

### 4.1 可读 2-bit 明文路径

`User/EDP_init.c`：

- line 12 定义 `wf_data[535]`；
- active initializer 为 `7 + 6 × 8 × 11 = 535` bytes；
- 六类依次为 VCOM、Black、White、Yellow、Red、Power，每类八组、每组 11 bytes；
- line 1223 写 `0xE9 = 0x01`；
- line 1227 向 `0x20` 发 LUT 命令；
- line 1228 精确发送全部 535 bytes。

同文件的四色组合函数以 `0x00/0x55/0xAA/0xFF` 表示 2-bit 黑/白/黄/红，说明这是
四目标色路径，不是完整六色 3-bit 表。该文件自身也不完全一致：独立白屏函数写
`0x11`，而四色组合中的均匀白写 `0x55`；因此必须按具体显示路径审计，不能只看函数名。

`User/UartDataDeal.c:98-108` 还允许串口命令把 535 bytes 替换到 RAM 中；但该函数
忽略传入长度并固定 `memcpy(..., 535)`，不能原样复用为安全接口。

最新 YX map 证明 `Uart_save_wf_data`、`wf_data`、`EPD_initial` 和调用它的四色显示
入口实际在 AXF 中，不只是未链接源码。可是 `EPD_initial()`、`EPD_WriteCMD()` 和
`EPD_WriteDATA()` 只拉低 `E_Paper_CS`，没有同步选择 `E_Paper_SLAVE_CS`；因此该
2-bit 调试路径不是当前双控 3-bit 刷新的可直接替代品。

这条已链接路径还有三项直接阻断：

- 表头的 `V1..V4/VCOM/Frame` 六项都会保存，但初始化只使用 `V1..V4`；VCOM 来自另一
  个全局值，PLL/Frame 仍是硬编码，表头与实际电气配置可能不一致；
- master-only 路径却按 `1024×600` 写 TRES，既没有拆成每颗 `512×600`，也没有设置
  双控 CCSET；
- `Uart_save_wf_data()` 接收 `buff_len` 却完全不检查，固定复制 535 bytes，不能作为
  安全的运行时输入接口；
- `EPD_Check_Busy()` 使用无超时 `while(1)`，BUSY 异常时没有失败收尾合同。

### 4.2 MCU LUT 模式

`User/main.c:54-117` 的未调用函数 `EPD_initial_noOTP()` 明确注释 PSR 的 MCU LUT
选择位，并写 `0xE9=0x01` 绕过已 OTP 面板的 CRC。它说明模式选择存在，但函数把
加密封装 `WF20_25` 的前几个字节直接当电源参数使用，且从未调用 `loadWF`，所以该
函数不能视为有效的 3-bit 实现。

### 4.3 加密加载库与未证实的 3-bit 分支

静态库是标准 ar archive，唯一代码成员为 `eload_20250305b1.o`。对象内直接可见：

- `E5_3Bit_Mode 0`；该值的语义没有随包提供；
- `WF_SIZE 535`、`WF_DeCode_SIZE 544`；
- `loadWF`、`LUT1_DATA`；
- AES-CBC、MD5、SHA-256 与 key/waveform success 状态符号；
- 编译源文件名 `eload_20250305b1.c`，但该源码未随包提供。

后续深反汇编已确认库会验证/解密固定 544 bytes，并在成功时写 535-byte LUT0 与
704-byte `LUT1_DATA`；但宏值 `0` 的语义、LUT1 内容/字段、面板适配性仍未知。842-byte
输入在当前 ABI 的 offset 544 产生越界键长 5157，已明确判定为不兼容，而不再只是
“不能证明可用”。

## 5. 当前 OQC 产物实际做了什么

`atk_f103.uvprojx` 同时列入 `User/EDP_init.c`、`Sample Code/E28xx.c` 和静态库，
但最新 `jiaxian-M009F-T_OQC_YX.map` 才是实际产物证据：

- `epdInitial` 来自 `e28xx.o`；
- 启动图调用 `Display_Picture`，其局部 `EPD_initial()` 调用被注释，因而沿用前述
  3-bit OTP 初始化；
- `EPD_initial_noOTP` 被移除；
- 包含 `WF20_25` 的 842-byte `.constdata` 被移除；
- `User/EDP_init.c` 的 `EPD_initial`、535-byte `wf_data`、`Uart_save_wf_data` 和
  四色显示入口仍被链接，可由 OQC UART 命令走另一条 2-bit/master-only 路径；
- image symbol/memory map 中没有 `loadWF`；
- 库统计只列 Arm C runtime，未拉入 `eload_3bits...lib` 的成员。

所以最后 M009F-T 产物的**启动显示**使用片上 OTP，未使用加密 `loadWF`；同时它
保留了一条独立的 2-bit UART runtime LUT 调试通路。两者不能合称为一个已经完成的
3-bit REG-API 实现。
此外最后 M009F-T 输出时间为 2026-05-29 或更早，而 `User/main.c` 为 2026-06-02；
输出不能作为当前源码的编译证明。

## 6. 已确认的内部矛盾

| 项目 | 路径 A | 路径 B | 结论 |
|---|---|---|---|
| 色码 `0x2/0x3` | `User/EDP_init.c`：黄/红 | `Sample Code/E28xx.c`：红/黄 | 包内冲突；以当前真屏已验证映射为准，不照搬样例名 |
| waveform 位宽 | `WF20_25.h`：E5 2-bit | library 名含 3bits，但对象宏为 `E5_3Bit_Mode=0` | 3-bit 分支是否启用未知；需要源码解释 2→3-bit 扩展和 `LUT1_DATA` |
| `loadWF` 返回类型 | header 声明 `void` | binary/callers 实际为 `uint8_t`，返回 `0/E1/E2` | 头文件错误，真实 ABI 已冻结 |
| wrapper ABI | current loader 固定 544-byte 解包 | `WF20_25` 自洽尾部在 offset 800 | 明确不兼容；不能称为旧版或直接加载 |
| 双控加载 | `loadWF` 无 CS 参数 | 随包 `writeEPD` 最终只操作 master CS | `MAS_SLA` 无定义，广播未成立 |
| 当前源与产物 | `User/main.c` 2026-06-02 | 最新 M009F-T 输出 2026-05-29 | 产物陈旧 |
| MCU LUT 示例 | 直接索引 `WF20_25` | 文件内容呈加密封装且库含解密逻辑 | 未调用示例不能执行 |
| 2-bit 白色填充 | 独立白屏函数写 `0x11` | 四色组合均匀白写 `0x55` | 同文件内部冲突，禁止把单函数字面量当正式色码合同 |
| 535-byte 表头 | 保存 `V1..V4/VCOM/Frame` | 实际只应用 `V1..V4`，VCOM/PLL 另取值 | 波形与电气参数没有闭环 |
| 双控几何 | TRES 写全屏 `1024×600` | LUT/命令只选择 master、无 CCSET | 不能移植到当前双控刷新链 |

当前 ESP32 的 `0黑/1白/2黄/3红/5蓝/6绿` 已经由 MAP 和真屏验证，不因参考代码
中的函数命名而改变。

## 7. 对“无抖动更多颜色”的实际意义

新增资料使路线从“完全不知道能否上传 LUT”前进到“知道控制器存在 runtime LUT
机制”。真正获得更多单像素颜色仍至少需要：

1. 当前 M009F-T/批次/温区匹配的 3-bit waveform 包或可读明文；
2. 与当前 library 匹配的 wrapper、`eload_20250305b1.c`、官方格式说明或
   ESP32/Xtensa 版本库；
3. `LUT1_DATA`、`0x20/0x21`、PSR mode、544-byte decoded layout 和双控 CS/order
   的字段定义；
4. 六个已知码和 `0x4/0x7` 在该 waveform 下的明确语义；
5. VCOM、VGH/VGL、VSH/VSL、frame/phase 与温区的批准范围；
6. 原厂 waveform 的等价复现、恢复、残影、电荷剂量、电流和温升基线；
7. 专用牺牲屏和可观测的硬件保护链。

535-byte 2-bit 表可以证明“相位表可调”，但不能单凭四个 target code 同时提供六色
加新增颜色。最有希望的缺口是库内 `LUT1_DATA` 和 3-bit 扩展格式，而不是盲目修改
现有 535 bytes。

## 8. 开发与测试门

### 可立即离线推进

- 建立只读结构/哈希审计工具；
- 为 runtime waveform 设计独立、默认关闭、无 OTP opcode 的数据模型和 validator；
- 定义 3-bit 包必须携带的 panel、controller revision、温区、电压、色码和 SHA 身份；
- 保留 `0x4/0x7` 固定 ROI 探针，用它判断**现有 OTP**是否已有额外状态；
- 准备六初态转换矩阵与光学/电气记录格式。

### 仍禁止

- 把 `WF20_25[1..6]` 直接作为电压/PLL 参数；
- 把 842-byte 加密封装直接写到 `0x20`；
- 把可读 2-bit `wf_data` 当成当前六色 3-bit waveform；
- 猜测 `LUT1_DATA`、`0x21` 或 decoded 544-byte 格式；
- 复制或调用任何 OTP program/APG/PGM 流程；
- 在当前面板上扫描电压、VCOM、phase 或任意 LUT；
- 因参考包存在而宣称 ESP32 runtime waveform 已实现或已安全。

## 9. 下一项所需外部资料

优先向代码提供方索取以下任一组即可显著解除阻断：

- `eload_20250305b1.c` + 与当前 `.lib` 对应的 `E28xx.h`；或
- ESP32/Xtensa 可链接的 `loadWF` 库及完整 ABI；或
- Waveform Tuning Tool 导出的 plaintext decoded 544-byte 文件及字段说明；
- 当前 M009F-T、当前批次、20–25°C 的 3-bit waveform 身份和色码表。

在获得之前，STM32 工程用于寄存器与架构证据，不作为上屏 payload 来源。

## 10. 可复现离线审计

只读工具：`tools/mf1750_stm32_waveform_audit.py`。它仅输出文件身份、结构、链接和
合同冲突，不解密 waveform、不输出原始 LUT/客户密钥、不读取 OTP，也不访问串口、
网络或硬件。

```powershell
python tools/mf1750_stm32_waveform_audit.py `
  --root '参考资料/REG-API-oqc(1)(1)/REG-API-oqc'
python -m pytest tests/test_mf1750_stm32_waveform_audit.py -q
```

2026-08-10 深审计后当前结果仍为 `compatibility_ready=false`，兼容/安全 blocker 从
13 项增至 18 项，聚焦测试 `8 passed`。这表示真实 ABI、版本不匹配以及蓝牙/亮度/对比度
映射缺失的证据边界已冻结，不表示
runtime waveform 已可执行。
