# MF-1750 厂家样例深审计与 LUT/波形扩色推进计划

文档日期：`2026-08-10`  
状态：`OFFLINE EVIDENCE COMPLETE / LIVE RUNTIME-LUT HARD BLOCKED`  
现场状态：按用户最后确认，`J2 OFF`，屏幕保持干净全白  
硬件访问：`NO`；未访问 COM8、设备网络、面板、OTP、刷写或刷新接口

## 1. 本轮结论

用户指定的两个厂家目录已经完整枚举；与 LUT、电源、双控和链接有关的关键源文件、工程、
静态库及全部 7 个 MAP 已逐项深审。STM32 静态库也完成了可复现的离线 Thumb 反汇编。
结果比原来的“存在 runtime LUT 迹象”更具体，但也找到了一个决定性的版本断层：

1. `E6_73_sample code_V1.2_20250116` 是 MSP430、EL073 Version-2、单 CS、
   `800×480`、固色 DTM loop 与 4-bpp packing 一致的六色样例；它不是当前
   `MF-17506-M009F-T`、
   `1024×600`、双 SPD1657B 的 runtime-LUT 合同。
2. `REG-API-oqc` 的库内 `loadWF` 已还原：成功时依次调用外部
   `writeEPD(0x01, 6)`、`writeEPD(0x30, 1)`、`writeEPD(0x20, 535)`、
   `writeEPD(0x21, 704)`；机器码有 `0x00/0xE1/0xE2` 三个返回分支（其中 `0xE2`
   无正常 helper-return producer），而厂家头文件错误声明为 `void`。
3. 当前库固定按 **544-byte 密文 + 2-byte 大端键长 + 包装键**读取输入；随包
   `WF20_25` 的 842-byte 数组在 offset 544 给出键长 5157，字段必然越界。该数组在
   offset 800 才出现自洽的 `800 + 2 + 40` 尾部，所以它只能归类为**与当前 loader
   不兼容的 candidate layout**；没有配对 loader，不能提升为权威 ABI 或有效 waveform，
   也不能因日期猜成“旧版”。
4. `loadWF` 不接收 controller/CS 参数。随包 `writeEPD` glue 最终落到只操作
   `E_Paper_CS` 的 legacy writer；`spiChipSelect=MAS_SLA` 在所给 C/H 中没有定义，且
   该 Sample main 不是 Keil 工程入口。因此当前资料没有形成双控制器 LUT 加载路径。
5. 厂家进一步说明“通过蓝牙传输，可以设置亮度和对比度”。本包能证明 STM32 侧存在一套
   UART 帧协议，命令 5/7/8 分别涉及 535-byte waveform、VCOM 读取和一个未校验的 raw
   VCOM byte；但没有 BLE stack、GATT 合同、无线 App 或 brightness/contrast 命令。
   因此最强可证结论只是“蓝牙端可能在外部桥接/生成这些 UART 数据”，不能把 VCOM 或
   waveform upload 擅自命名为已批准的亮度/对比度接口。光学上的“亮度”仍应定义为受控
   照明下的 `L* / reflectance`，同时记录 `a*、b*、chroma`，不能按 LCD 背光亮度理解。

结论仍是：代码侧的解析、门禁和实验编排可以继续；当前没有可信的上屏 payload，也没有
今晚可执行的 runtime-LUT 倒计时。

## 2. 两套样例的适用边界

| 证据 | 已确认 | 可以借鉴 | 禁止移植/推断 |
|---|---|---|---|
| E6_73 V1.2 | EL073 V2、800×480、MSP430、单 CS；固色 loop 与 4-bpp packing 一致 | 单次刷新后 `POF`、等待、管脚拉低和 VDD cut 的“关断意图” | 通用像素格式、全部寄存器值、电压、颜色码、BUSY 时序、双控、LUT 格式 |
| REG Sample Code | E2802/SPD1657、标注为 E5 3-bit 的命名、双片各 512×600 的 OTP 初始化骨架 | 控制器架构、命令存在性、半屏分工 | Sample main 可构建性、`MAS_SLA` 广播、当前包已链接/已运行 |
| REG `wf_data[535]` | 选中 MAP 对应的历史 build 曾链接 E5 2-bit、四目标色、master-only RAM LUT 路径；当前 source 更新于 MAP 后 | `0x20` RAM LUT 机制存在性 | 当前源码构建状态、当前六色 3-bit payload、蓝/绿/额外色、双控安全路径 |
| REG `loadWF` library | 真实 ABI、返回码、四次写命令/长度、544-byte 解包门 | 离线重写解析器和 fail-closed validator | Xtensa 可直接链接、LUT1 含义、面板/膜批兼容性 |
| `WF20_25[842]` | E5 2-bit 标签；尾部与 `800+2+40` candidate layout 自洽 | 版本不匹配测试夹具 | 把 candidate 当权威 ABI/有效 waveform、传入当前 544-byte loader、直接写 `0x20/0x21`、用作真屏 payload |

### 2.1 E6_73 的具体发现

- `E6_73.c` 的 TRES 是 `0x0320 × 0x01E0 = 800×480`。
- 每色写 `192000 = 800×480/2` bytes；白/黑/黄/红/蓝/绿依次为
  `0x11/0x00/0x22/0x33/0x55/0x66`。这些固色 loop 与每 byte 两个相同 4-bit
  nibble 的 packing 一致，但不单独证明通用像素顺序或其他 controller 格式。
- V1.2 在六个显示函数末尾都增加：等待 6 s、PSR `0x4F 0x6E`、等待 1 s、
  CS/RST/SDA low、`SWC_L` 切 VDD。
- 但 `main.c` 只调用一次 `EPD_Init()`，随后连续调用七次显示；第一次显示已经切断
  VDD，后续没有 `SWC_H` 或重新初始化。因此 V1.2 的连续七色主程序内部不自洽，不能
  当作已验证循环时序。
- 注释里的 `dual reset` 是两次 reset pulse，不是双控制器；全树只有一个 `CSB`。
- 本样例没有 `loadWF`、LUT0/LUT1 或 brightness/lightness API。

两套样例还存在直接色码反证：E6_73 把 `0x22/0x33` 命名为黄/红，而标注为 E5 3-bit
的 REG `E28xx.c` 把 code `2/3` 命名为红/黄。跨样例复制色码不成立。

### 2.2 REG-API 不是一个一致的“可直接编译示例”

- `Sample Code/E28xx.*` 标注 E5 3-bit / E2802-SPD1657；Sample main 的标题却是
  E6 13 inch；`WF20_25.h` 又标注 E5 2-bit。
- Keil project 实际入口是 `User/main.c`，不是 `Sample Code/main.c`。
- Sample main 引用本包 C/H 中不存在的 `WF00_05.h`、`LOAD_SW`、`setPinCsAll`、
  `spiChipSelect`、`MAS_SLA` 和 `initEPD`。原始 ZIP 也没有 `WF00_05.h`。
- 七个随包 MAP 均没有 `loadWF`，并全部移除 `EPD_initial_noOTP` 与 `EPD_Write_LUT`；
  已有 AXF/HEX 不能证明加密 loader 曾被链接或执行。

## 3. `loadWF` 二进制合同

### 3.1 身份与函数边界

| 对象 | 位置/长度 | SHA-256 |
|---|---:|---|
| library | 65082 bytes | `f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b` |
| ar member `eload_20250305b1.o` | archive `0x1A2`，64664 bytes | `92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d` |
| ArmCC captured code/data/comment prefix | archive `0x1DE`，`0x1453` bytes | `2918a3da3a82a15e168fff6587aa545ad6eb0d093ee345040a3a17272429b252` |
| `loadWF` | archive `0x692`，`0x88` bytes | `98f37782e3257d4bf841d7e6b30f2d58f947b580134031ff6680903dddf0a1ff` |
| `test_decrypt_cbc_check_key` | archive `0x134A`，`0xCC` bytes | `ba955f2bf76c68bcc859707e68edae7b3a51884f4da695975a0841376d0219b2` |

对象 magic 为 `F7 4F 52 43`，编译 banner 为 ARM Compiler 5.06 update 3 build 300，
并带 `__EVAL`。它不是标准 ELF。复核方法是解析 Unix ar、定位 ORC code/data stream，按
ArmCC debug size 与 Thumb prologue/epilogue 确定函数边界，再把原始代码 byte-for-byte
包入临时 ARMNT COFF 供本机 `dumpbin` 反汇编。CROF relocation 没有被伪造；反汇编中
未解析的 call/literal 明确保留为未解析状态。

后续完整 DWARF 函数盘点纠正了该包装边界：`0x1453` 是当时捕获的 code/data/comment 前缀，
不是纯 executable 长度。末函数 `xtime` 在 stream `0x1408` 结束，随后 4 bytes 对齐，
`.comment` 从 `0x140C` 开始；真实 executable `[0,0x1408)` 的 SHA-256 为
`51d7e843c3a1a95601c16c895a91f96ae182146d5560ee377502c111832e1f7c`。

### 3.2 真正 ABI

`loadWF` 的真实原型等价于：

```c
uint8_t loadWF(const uint8_t *wrapper);
```

以下返回码与 `writeEPD` 映射现在由 public symbols、已解析 CROF relocation、DWARF 和
Thumb dataflow 直接绑定。返回值：

- `0x00`：key 精确匹配、crypto 调用返回且四次 `writeEPD` 已调用；不证明 plaintext 有效或
  控制器接受写入；
- `0xE1`：正常可达的 key 比较失败；
- `0xE2`：机器分支存在，但 helper 的正常单线程返回不会产生所需的
  `(key_success,wf_success)=(1,0)`；**不得称为 waveform validation failure**。

helper 在 key 失败时返回 `(0,0)`；匹配后依次执行 SHA-256、MD5、AES，并在这些无 status
检查的调用直线返回后置为 `(1,1)`。它没有 plaintext magic、结构、padding、MAC/认证或
完整性验证。因此 `wf_success` 表示“解密调用已返回”，不是“waveform 已验证”；并发改写或
内存破坏等模型外状态才可能使 `0xE2` 被观察到。两个失败分支都不会调用 `writeEPD`。

成功写序列：

| 顺序 | command | 长度 | 来源 |
|---:|---:|---:|---|
| 1 | `0x01` | 6 | 固定首 byte `0x0F` + decoded `[0..4]` |
| 2 | `0x30` | 1 | decoded `[6]` |
| 3 | `0x20` | 535 | decoded global buffer |
| 4 | `0x21` | 704 | library-resident `LUT1_DATA` |

函数内部没有 controller/CS target、BUSY polling、reset、PON/DRF/POF、OTP 恢复或
白恢复。它只负责 key 比较、解密和调用外部 writer，不验证 waveform，也不是完整显示事务。

### 3.3 包装结构

内部检查函数执行的可确认流程：

1. 固定复制/处理 `0x220 = 544` bytes；
2. 从输入 offset `544/545` 读取 two-byte big-endian wrapped-key length；
3. 从 offset `546` 复制该字段，并与输入前缀逐 byte XOR；
4. 与 source customer key 做精确长度/内容比较；
5. 通过后以 key 的 SHA-256 作为 AES-256 key，以 MD5 作为 CBC IV；
6. 原地解密固定 544 bytes。

函数没有总输入长度参数，也没有可见的 wrapped-key bounds check。DWARF 证明 `iniKey` 和
`ciniKey` 各为 75 bytes，但 helper 在比较前已经按不受限长度复制、XOR，并执行
`iniKey[len]=0`，没有先证明 `len <= 74`。对 842-byte 包得到 length 5157，所以不只是
“显示结果未知”，而是 ABI 层已经不安全。

原始 customer key 和解密 waveform bytes 均未写入正式报告、JSON 或反汇编产物。正式
审计只输出长度、SHA 与结构谓词。

### 3.4 `LUT1_DATA` 的证据边界

目前可直接确认：

- 它是库内 public symbol；
- `loadWF` 直接把它作为 `0x21` 的 704-byte 数据源；
- 它不是由 caller 的 wrapper 在 `loadWF` 内生成；
- 它位于 member `[0x1B54,0x1E14)`，704 bytes 全为 `FF`，SHA-256 为
  `24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`。

不能确认：C 声明是否 `const`、`FF` 的控制器语义、字段布局、phase/color-code 语义、
是否跨面板/膜批通用。不能把全 `FF` 擅自称为 no-op，也禁止据 704 这个长度猜测格式。

## 4. “明暗/亮度可调”的正确解释

E Ink 官方说明电子纸是反射式显示、没有背光，环境光越强看起来越亮。因此本项目的
“亮度”应以受控照明下的 `CIELAB L*` 或反射率定义，不是 PWM/backlight level。

E Ink 的公开专利说明，彩色电泳显示可以通过 time-dependent waveform 和 scaling factor
改变 primary color 的 hue、saturation、luminance；另一份驱动专利还说明 DC balance 与
shaking 会影响 color brightness/purity，并警告长期非零平均电场会降低寿命。这支持厂家
口头信息的物理可行性，但**不证明这些专利的具体比例、电压或波形可用于本面板**。

E Ink 2025 年 Ripple 公告还明确提到新 waveform architecture 配合升级到 3-bit 的芯片
可扩展 Spectra 6 色彩。它证明路线存在，不证明当前 SPD1657B rev、当前膜批或当前 842-byte
文件已具备该路线。

### 4.1 厂家“蓝牙调亮度/对比度”线索的本地代码落点

对两套样例的非通用库源码、工程文件和随包应用资产做大小写无关检索后，没有找到
`Bluetooth`、`BLE`、`GATT`、characteristic、brightness、contrast 或 gamma 控制实现，
也没有 `.apk`/`.ipa`。REG 工程提供的是 UART1 接收端：

- `Drivers/SYSTEM/usart/usart.c:29-90` 配置 PA9/PA10、115200 baud、8 data bits、
  1 stop bit、no parity；样例没有蓝牙模块型号、AT 配置、HCI/SPP 或 UUID；
- `Drivers/SYSTEM/usart/usart.c:151-203` 识别 `41 41` 帧头、offset 2--3 的大端总长度、
  offset 4/5 的 command/subtype、offset 6 起的 payload、CRC-16 和末尾 `0D`；
- command 5 把 payload 交给 `Uart_save_wf_data()`；后者在
  `User/UartDataDeal.c:98-108` 忽略传入的 `buff_len` 并固定复制 535 bytes；
- command 7 触发 `get_vcom()`，`User/EDP_init.c:1091-1135` 从控制器寄存器 `0x81`
  读取一个 byte；
- command 8 直接执行 `vcom = USART1_RData[6]`，没有单位、范围、批次或温区检查。
  `User/main.c:292-303` 的 SET 分支只回 ACK，`EPD_setting.VCOM = vcom` 还是注释；
  legacy `EPD_initial()` 稍后才在 `User/EDP_init.c:1221` 写 `vcom | 0x80`，且该路径只选
  master CS，也不是所有显示入口都会重新初始化。
- 7 个 MAP 都保留 UART parser 与 `Uart_save_wf_data`，所以这不是纯粹未链接的死源码；
  但 7 个 MAP/AXF 都没有拉入 `loadWF/LUT1_DATA`，两条 loader 路径仍不能混为一谈。
- `Sample Code/main.h:16-21` 的调波工具命令只有 firmware、loadWF、set/get VCOM 和
  testPattern；`Sample Code/main.c:159-307` 注明 USB CDC/WF Tuning Tool。该移植接口同样
  没有 brightness/contrast，也不能因为有 receive/send stub 就称为 BLE。

由此得到的工作假设是 `App/蓝牙模块 →（可能透明转发）→ UART → STM32`，但样例只提供
箭头右半段，**没有证明蓝牙就是透明串口桥**。厂家界面里的“亮度/对比度”至少可能是：

1. App 在发送图像前做 tone/contrast preprocessing，面板波形完全不变；
2. App 选择或上传不同的 vendor waveform/profile；
3. App 改变 VCOM 或其他驱动参数；
4. 由上述多项组合得到的产品级档位。

只有同一 App 操作前后的 GATT/蓝牙包、STM32 UART 帧、profile identity 和控制器写 trace
能区分这些情况。当前 command 8 的 raw byte 没有安全边界，禁止把它用作试探性
brightness knob；源码也没有独立 contrast 命令。

官方相邻产品也只能帮助划分边界：E Ink Vision 驱动板页面写明其 ESP32 板支持 BLE，
但没有公开 GATT/亮度/对比度语义；E Ink 官方 `E Ink BT Solution` App 的说明则明确是把
“处理后的影像”通过蓝牙传到其列出的其他 EPD 产品。这支持“BLE 可能只是传输层、视觉调整
可能先在 host 完成”的解释，但不是当前 MF-17506/SPD1657B 的协议证据。E Ink Spectra 6
页面所列典型对比度约 30:1 是光学性能指标，不是可调命令或滑杆范围。

需要厂家把“可以调”的条件落成以下受控资料：

1. brightness 的光学定义与验收方式：`L*`、reflectance、目标 `a*/b*/chroma`、照明/仪器；
2. 精确 panel model、FPL/film lot、controller 型号与 revision、温区；
3. waveform/package ID、生成工具版本、文件 SHA、对应 loader source/version；
4. master/slave 是否同 payload、各自长度、CS 顺序、何时切 MCU-LUT mode；
5. decoded `0x01/0x30/0x20/0x21` 字段定义和批准的电气/phase/frame 边界；
6. K0/OTP 等价 runtime profile、readback 或替代完整性证明；
7. runtime→OTP、断电、白恢复和失败恢复步骤，以及最大尝试数、冷却/寿命限制；
8. 可调档位是离散 vendor profiles、waveform scale、target code，还是 host spatial mapping。
9. 蓝牙模块/整机/官方 App 的型号与版本、GATT service/characteristic UUID、读写属性和
   MTU/分包/校验/ACK 合同；若是透明串口桥，提供明确声明和 UART 参数；
10. 至少两档 brightness、两档 contrast 和默认值各自的完整输入/输出 packet capture，及
    对应 UART 帧、profile/file SHA、最终寄存器写 trace、单位/范围/持久化与生效时点。

## 5. 后续如何推进 LUT 波形色

### Gate A：拿到匹配资料，先做离线一致性审查

- 不接受单独的 `.h`、单独的 `.lib` 或口头参数；loader、wrapper、面板批次与格式说明必须
  是同一 release。
- 用当前审计器验证 file SHA、decoded size、key field、双控 segment、命令/长度和禁用
  OTP/nonvolatile opcode。
- 对厂家蓝牙控制另做纯离线差分：固定同一图片，分别只改变 brightness 或 contrast 一档，
  对齐 App 输入、GATT packet、STM32 UART frame 和最终 EPD trace；先判定是 host preprocessing、
  profile selection/upload 还是电气参数变化。不能只凭 UI 标签命名底层语义。
- 只有审查通过的格式才能进入当前为空的 production registry；否则 compile gate 继续 false。

### Gate B：完成 ESP32 解析/传输代码，但仍不接屏

- 将可移植 loader 只接到 mock sink/recording transport，逐 byte 对照厂家 STM32 golden trace。
- 明确 CS1/CS2 每段 payload 和 BOTH-only 命令；所有 BUSY 都有 timeout，失败不 retry。
- 固定 K0、C1、C2 等 profile identity、温区/电气 profile 与 recovery predecessor；构建产物
  仍不得含 OTP program 命令。

### Gate C：牺牲屏单 profile、单 action、有线保护测试

用户已确认具备电源限流、电流监测、温度监测、物理切断设备和牺牲品。这些条件记为
`USER-REPORTED READY`，但还需在现场记录设备身份、校准/采样、阈值和切断责任人。

只有 Gate A/B 全部通过后，才生成一张 exact operator card：先建立 approved OTP/K0 基线，
再执行一个厂家批准的亮度档位/小样 action，记录双控制器 trace、BUSY、峰值/积分电流、温度、
受控光学测量，随后按厂家合同恢复。任何异常立即物理切断并把 action 标记 UNKNOWN，禁止自动
重试或现场临时改参数。

### Gate D：从“亮度档位”扩展到波形色

- 先验证同一已知原色的离散明暗档，而不是一开始搜索未知综合色。
- 每个 profile 做 old→new transition matrix、DC/残影和白恢复验证。
- 只有在跨温区、双控一致性、恢复和寿命审查完成后，才把 profile × 3-bit target 暴露给
  host color mapper；未测状态不进入 palette。

## 6. 当前仍为硬阻断的项目

- 与当前 library 匹配的 wrapper（Sample main 所需 `WF00_05.h` 也缺失）；
- 当前 M009F-T/膜批的真实双控 3-bit payload 与明文格式；
- `LUT1_DATA` 权威定义；
- 双控制器 load/select/order/readback 合同；
- 批准的 VCOM/rails/PLL/frame/phase/温区边界；
- K0 OTP-equivalence、runtime→OTP 与白恢复合同；
- 蓝牙模块/GATT/串口桥合同、官方 App/固件版本和可重放 packet captures；
- brightness/contrast 的编码、单位、范围、默认值、持久化、生效点、readback 以及与光学指标、
  waveform/profile 或寄存器写入的逐档映射；
- refresh count、cooldown、连续测试与寿命限制；
- 独立原厂/人工 review。

硬件保护和牺牲屏只降低故障后果，不能替代上述格式与电气证明。

## 7. 可复现产物与验证

正式审计器：`tools/mf1750_stm32_waveform_audit.py`  
测试：`tests/test_mf1750_stm32_waveform_audit.py`  
逆向证据：`.test-output/offline/stm32_reverse_20260810T115353/`  
本轮结构化输出：`.test-output/offline/stm32_vendor_deep_audit_20260810.json`

关键证据文件：

- `REPORT.md` / `report.json`；
- `loadWF.dumpbin.txt`；
- `test_decrypt_cbc_check_key.dumpbin.txt`；
- `capture_disasm.ps1`；
- `wrapper_metadata.json`；
- `verification.json` / `SHA256SUMS.txt`。

本轮正式审计 schema v3 固定 18 项 compatibility findings，聚焦为 `8 passed`；与
runtime-waveform/repo-contract 的 post-P4 定向联合回归为 `95 passed`；Ruff、
`py_compile` 通过。结构化 JSON SHA-256 为
`06bfd4914c58eb9a78ed0dcb1fba8b29cc330543f9e0b6939c5e9cf1a7b9bbcb`。P4 的
`145 passed, 1 skipped`
是 09:21 冻结的历史快照，不把本次用例简单相加成新全量口径。逆向证据自身的重建、JSON、
Ruff、`py_compile` 和结构连续性验证也全部通过。辅助脚本只在内存中对 800-byte candidate
做 AES-CBC 解码以核对结构，并仅保留 hash/谓词；该结果未被接受为 loader plaintext，未写出
raw key/waveform bytes，也未生成 live payload。没有访问硬件、串口、设备网络、OTP、刷写或刷新。

## 8. 一手/官方公开资料

- Solomon SPD1657 的公开展会资料：
  <https://www.computextaipei.com.tw/en/product/CBA4659B8C39B7F72BDDBEB61C4033B7A51D2AFD55BCA758/info.html>
- Touch Taiwan 对 `SPD1657 (E2802)` 的官方展品页：
  <https://www.touchtaiwan.com/visitorProductDetail.asp?no=180553>
- E Ink 7.3-inch Spectra 6 产品页（OTP waveform、display RAM、SPI、温度接口）：
  <https://shopkits.eink.com/en/product/detail/7.3%27%27Spectra6ePaperDisplay>
- E Ink Scarlet/Vision 驱动板产品页（官方页面仅证明这些 ESP32 驱动板支持 BLE，未公开
  brightness/contrast 的 GATT 或底层映射）：
  <https://shopkits.eink.com/en/product/detail/ScarletDrivingBoard>、
  <https://shopkits.eink.com/en/product/detail/VisionDrivingBoard>
- E Ink Holdings 官方 `E Ink BT Solution` App 页面（描述为先处理影像、再经蓝牙传给其
  列出的其他 EPD 产品，不是本面板协议）：
  <https://apps.apple.com/tw/app/e-ink-bt-solution/id1474945368>
- E Ink Spectra 6 官方页面（约 30:1 为 typical contrast ratio 指标，不是控制字段）：
  <https://www.eink.com/brand/detail/Spectra6>
- E Ink Ripple / second-generation 3-bit waveform 公告：
  <https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays>
- E Ink 反射式、无背光说明：<https://www.eink.com/tech/detail/Benefits>
- E Ink/E Ink Corp expanded-palette waveform scaling 专利：
  <https://patents.google.com/patent/US20260065869A1/en>
- E Ink/E Ink Corp DC balance、brightness/purity 驱动专利：
  <https://patents.google.com/patent/US20260094580A1/en>
- ARM Compiler 5.06 `fromelf` 官方手册：
  <https://www.keil.com/support/man/docs/armutil/default.htm>

这些公开资料只能支持控制器别名、一般机制和测量定义；没有公开补齐 SPD1657B rev 0x04
的寄存器合同、当前双控 payload、电气窗口或恢复流程。
