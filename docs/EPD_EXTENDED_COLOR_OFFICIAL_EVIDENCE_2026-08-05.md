# MF-17506 扩展颜色：A 阶段官方证据报告

日期：2026-08-05

阶段：A — 官方资料与证据调研

状态：`COMPLETED`（存在会阻断危险实验的重大未知项）

分支：`research/extended-color-20260805`

审查起点：`3dfd4776b749660a5462f27b80d0055f23f0c47e`

Hardware tested: `NO`

机器可读矩阵：`research/extended_color/evidence_matrix.json`

## 1. 结论

现有允许证据足以支持以下结论：

- 本机 `MF-17506-M009F-T` 是 7.50 英寸、1024×600、`3-bit E6` 的六状态有源矩阵电泳显示模组，参考设计使用两颗 SPD1657B，显示 IC 集成 SRAM、LUT、内部温度传感器和片上 OTP waveform。
- E Ink 和 Solomon 的官方平台资料与正式论文共同表明，SPD1657 面向 Spectra 6；Spectra 6 使用红、黄、蓝、白四种粒子，在 Microcup 中形成白、黑、红、黄、蓝、绿六个主状态。因此，把本机识别为 Spectra 6 家族是高置信推论，但当前没有精确到该面板 film lot/墨水批次的 E Ink 证书。
- 当前正常刷新路径与使用片上 OTP waveform 一致；但 OTP ID、版本、CRC、批次绑定、温区和读回方式均未知。
- 0x4、0x7、0x8～0xF、LUT 主机接口、0x86 的完整定义、window/old-frame/partial、精确 Sparkle/Ripple 兼容性、内部温度读法、高压范围以及连续刷新/寿命限制都没有足够证据。

所以 A 阶段对后续工作的裁决是：

- 对 B/C 的仓库检查、主机生成器、schema、分析器、模拟测试和安全门禁文档：`GO`。
- 对任何上电、刷新、刷写或硬件测量：仍须逐项用户授权，A 阶段本身不授权。
- 对未知码硬件探针：`NO-GO`，直到隔离入口、审查、hash 和单独硬件授权齐全。
- 对 LUT、phase、波形、PLL、高压和电压扫描：`HARD BLOCKED`。

## 2. 四级证据规则

| 级别 | 定义 | 可用于什么 | 不可用于什么 |
|---|---|---|---|
| D | 精确 `MF-17506-M009F-T` 厂商规格或针对该精确硬件的受控资料 | 确认型号、几何、已写明的硬件能力和明示限值 | 补写规格没有提供的命令、波形或电压 |
| P | 官方平台/兄弟面板/相邻控制器资料、官方代码、正式论文 | 解释平台能力，提出向厂商索取的资料和安全门禁 | 逐寄存器移植，生成本机可执行参数 |
| I | 由 D/P 交叉支持的推论 | 技术路线判断和非执行性假设 | 解锁命令、未知码、LUT、波形或电压 |
| U | 允许来源不能确定 | 明确阻断条件；在 JSON 中记为 `null` | 以空字符串、经验值、专利值或相邻芯片值填充 |

专利仅可解释原理。SPD1656 仅是相邻控制器资料，严禁移植 PartialRAM、LUT unlock、frame-rate、temperature、voltage 或 waveform 命令到 SPD1657B。

## 3. 必须纠正的样例代码证据边界

`参考资料/E6_73_sample code_V1.2_20250116/` 不是 MF-17506 的精确驱动包，必须定为 P 级相邻 Spectra 6 平台证据：

- `E6_73.c:126-130` 写入 TRES `0x0320 × 0x01E0`，即 800×480。
- `E6_73.c:167,214,259,307,354,401` 的每个纯色 DTM 都发送 192000 B；4bpp 下正好是 800×480，而本机正式帧是 1024×600、307200 B，并由两颗 SPD1657B 分担。
- `E6_73.c:141-153` 的 0x86 helper、`E6_73.c:184-204` 及其他颜色函数的 DRF/POF/VDD-cut 流程，均只能说明该相邻样例怎么做。
- `Version_Descriptions.txt:3` 只说明 V1.2 在每个 display function 后增加 VDD-cut sequence。

因此不能把样例中的初始化、PWR/BTST/POFS/PLL/PWS/T_VDCS 数据、0x86 或关断时序称为 MF-17506/SPD1657B rev `0x04` 的逐寄存器直接证据，也不能从中移植新参数。

## 4. 来源目录

### 4.1 精确面板直接证据

本地厂商规格：`参考资料/MF-1750..1).pdf`，Ink Cubic，revision A1，2026-02-28。

| Locator | 直接支持的事实 |
|---|---|
| PDF p.1 | 精确型号 `MF-17506-M009F-T`、module `M009F-T` |
| PDF p.4 | 7.50 英寸、1024×600、3-bit E6；IC 集成 SRAM、LUT、内部温度传感器、片上 OTP waveform |
| PDF p.5 | 参考模组结构为两颗 SPD1657 |
| PDF pp.6-7 | BUSY 行为；VCOM、VPC、VGL、VPH、VSH、VSL、VGH 等轨名 |
| PDF p.10 | 参考电路 BOM 明确标注 SPD1657B |
| PDF p.11 | VCI absolute maximum、VDD 2.4/3.0/3.6 V、环境说明；电气/光学只在 Ink Cubic 指定控制器和 waveform 下保证 |
| PDF pp.13-14 | SPI timing；命令表要求另查 SPD1657B datasheet |
| PDF p.15 | 黑/白/红/黄/蓝/绿六个光学状态；每天更新建议和长期红色后的黑白清屏提示 |
| PDF p.19 | 可靠性资格试验条件；它们不是运行冷却规则 |

### 4.2 官方平台、芯片厂和正式论文

| ID | 级别 | 来源 | 能支持的结论 | 边界 |
|---|---|---|---|---|
| P1 | P | 本地 E Ink `E6_73_sample code V1.2` | 800×480/192000 B 平台样例的六色字节、全帧流程、0x86 壳函数、VDD-cut 示例 | 不是 MF-17506 精确驱动包 |
| P2 | P | [E Ink Spectra 6](https://www.eink.com/brand/detail/Spectra6) | Spectra 6 平台和 Sparkle 局部闪烁能力 | 不证明当前控制器/OTP 支持 Sparkle |
| P3 | P | [E Ink 技术说明](https://cn.eink.com/tech/detail/How_it_works) | Spectra 6 四粒子、六主色平台原理 | 无本机码表或命令 |
| P4 | P | [COMPUTEX 官方 SPD1657 产品页](https://www.computextaipei.com.tw/en/product/CBA4659B8C39B7F72BDDBEB61C4033B7A51D2AFD55BCA758/info.html) | SPD1657 为 800 source × 600 gate、面向 Spectra 6 | 不是 SPD1657B rev 0x04 datasheet |
| P5 | P | [Solomon bistable 产品目录](https://www.solomon-systech.com/product-category/bistable-display) | 当前公开目录和 datasheet 申请渠道 | 目录未列出不能解释寄存器 |
| P6 | P | [E Ink 7.3 英寸兄弟模组](https://shopkits.eink.com/en/product/detail/7.3%27%27Spectra6ePaperDisplay) | 兄弟模组片上 RAM、OTP waveform 和项目匹配 support files | 800×480 兄弟模组资料不可移植 |
| P7 | P | [IDW 2023：Color Electrophoretic Displays](https://confit.atlas.jp/guide/event-img/idw2023/EP1-01/public/pdf_archive?type=in) | Spectra 6 四粒子物理和 W/K/R/Y/B/G 六状态 | 论文电压/时间不是本机参数 |
| P8 | P | [SID 2025：高分辨率 Spectra 6](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-4.pdf) | Microcup 粒子极性和不同背板研究条件 | 不同背板的电压/频率不得移植 |
| P9 | P | [SID 2025 Spectra 6 平台论文](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-1.pdf) | 红/黄/蓝/白粒子形成六个主状态 | 不定义本机编码或命令 |
| P10 | P | [E Ink Ripple 官方公告](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays) | Ripple 是新 waveform architecture，依赖升级 compatible chipset，可把平台扩到八主色 | 未点名 SPD1657/B 或 MF-17506 |
| P11 | P | `参考资料/Solomon-SPD1656.pdf` | 相邻 640×480 3-bit 控制器概念 | 禁止移植所有命令和参数 |
| P12 | P，原理限定 | [US20250239231A1](https://patents.google.com/patent/US20250239231A1/en) | old/new transition 和边界处理的一般原理 | 专利不得产生可执行参数 |

## 5. A 阶段证据矩阵

### 5.1 墨水体系

等级：`D + P -> I`

直接证据只写明本机为 3-bit E6 和六个光学状态，没有写 Spectra 6 商标或粒子配方。Solomon 官方 SPD1657 产品定位、E Ink 平台资料和正式论文共同支持“本机属于 Spectra 6 家族”的高置信推论。Spectra 6 平台的四粒子为红、黄、蓝、白，形成白、黑、红、黄、蓝、绿状态。

仍未知并记为 `null`：精确 film lot certificate、墨水批次、粒子配方版本。

### 5.2 SPD1657B rev 0x04 完整 datasheet

等级：`U`，阻断项。

精确面板规格 p.14 明确把命令定义转介给 SPD1657B datasheet。官方公开资料检索只找到 SPD1657 产品定位，没有找到覆盖 SPD1657B rev `0x04` 的完整命令文档。

以下均为 `null`：完整 datasheet URL、rev `0x04` 命令定义、reset values、reserved-bit 规则、cascade readback 规则。

### 5.3 3-bit 码表、0x4 和 0x7

等级：已知六码为 `P`，两个空位为 `U`。

800×480 官方相邻样例使用：

| index | 样例字节 | 样例颜色 |
|---:|---:|---|
| `0x0` | `0x00` | 黑 |
| `0x1` | `0x11` | 白 |
| `0x2` | `0x22` | 黄 |
| `0x3` | `0x33` | 红 |
| `0x4` | `null` | 未定义 |
| `0x5` | `0x55` | 蓝 |
| `0x6` | `0x66` | 绿 |
| `0x7` | `null` | 未定义 |

这与已冻结的项目正式映射一致，但不能替代精确 MF-17506 厂商码表。0x4 和 0x7 不能称为新颜色、alias、保持态或保留值。正式 API 必须继续拒绝它们。

### 5.4 0x8～0xF 的 bit3

等级：`U`，阻断项。

精确规格只声明 3-bit E6；相邻样例所有 nibble 的 bit3 都为 0。没有允许证据证明 bit3 被忽略、映射到低三位、被保留或被禁止。

`bit3_ignored`、`aliases_low_three_bits`、`bit3_reserved_or_forbidden` 和所有 0x8～0xF 语义均为 `null`。在得到厂商定义前不得执行 H 阶段。

### 5.5 OTP waveform

等级：片上存储为 `D`；当前刷新使用它为 `I`；manifest 为 `U`。

精确面板规格明确 waveform 存在片上 OTP。相邻样例触发 DRF 而不上传 LUT，兄弟模组官方页也强调项目匹配的 OTP/support files。因此正常刷新使用本机片上 OTP 是有充分支持的解释，但 `DRF 0x00` 的精确数据语义仍需 SPD1657B 文档。

以下为 `null`：OTP ID、版本、CRC/hash、lot binding、温区、温区选择规则和读回能力。

### 5.6 LUT 上传、选择和读回

等级：硬件块存在为 `D`；主机接口为 `U`。

规格称 IC 集成 LUT，但没有说明 LUT 是否可由主机上传、选择或读回；相邻样例也没有 LUT payload。硬件含 LUT 不等于开放 LUT 编程接口。

上传命令、unlock、slot、readback、格式、phase count 和电压字段编码全部为 `null`。SPD1656 的 LUT 流程严禁移植。

### 5.7 0x86 Interlace

等级：`P` 且不可执行。

相邻样例 `E6_73.c:141-153` 只提供 `0x86,0x01` 和 `0x86,0x00`，并注明当前不用、为未来 dither image 保留、依赖 dithering area。它没有给出区域编码、波形依赖、old-frame 要求或安全限制。

SPD1657B rev `0x04` 的完整定义仍为 `null`；当前不得调用 0x86。

### 5.8 window、old-frame、partial

等级：`U`，阻断项。

精确规格没有命令详情，相邻样例只有全帧 DTM/PON/DRF/POF。专利可支持“局刷可能需要 old/new transition 和边界处理”的原理，但不能提供命令、RAM 格式、窗口坐标、波形或 cleanup 参数。

window command、old-frame RAM/format、partial waveform、border rule 和 cleanup count 全部为 `null`。

### 5.9 Sparkle

等级：平台能力为 `P`；本机能力为 `U`。

E Ink 官方 Spectra 6 页面公开 Sparkle partial-image flashing effect。没有证据证明 MF-17506、SPD1657B rev `0x04` 或当前 OTP 包支持它，也没有本机 command/support package。

### 5.10 Ripple

等级：平台架构为 `P`；本机能力为 `U`。

E Ink 2025 官方公告把 Ripple 描述为第二代 waveform architecture，并明确结合升级 compatible chipset system；公告没有点名 SPD1657/B 或 MF-17506。当前不得宣称或启用 Ripple。

### 5.11 内部温度读取

等级：传感器存在为 `D`；读法为 `U`。

精确规格确认内部温度传感器，并说和数字温度传感器通信时 BUSY 有效。相邻样例仅定义 `T_VDCS=0x84` 并写 `0x01`，没有温度读取流程，不能从名称推断 API。

read command、长度、raw format、摄氏度换算、校准、精度和 waveform 温区映射全为 `null`。在厂商接口到位前使用外部已校准温度探头。

### 5.12 VCOM/VGH/VGL/VSH/VSL

等级：逻辑供电和轨名为 `D`；高压数值为 `U`。

精确规格给出 VDD 2.4 V minimum、3.0 V typical、3.6 V maximum，VCI absolute maximum 为 -0.5～3.6 V，并说明 VCOM 已在面板 IC 中设定。它只列出 VCOM/VGH/VGL/VSH/VSL/VPH/VPC/PREVGL 等轨名，没有给出这些轨的 nominal、容差或 absolute maximum。

参考电路 25 V 电容额定值不是轨工作限值；正式论文中的平台/实验电压和不同 oxide-TFT backplane 数据也不是本机参数。所有高压轨范围保持 `null`，电压修改保持 `HARD BLOCKED`。

### 5.13 恢复、冷却、最大连续刷新和寿命

等级：局部建议为 `D`，相邻关断序列为 `P`，正式运行限值为 `U`。

精确规格提供的有限直接信息：

- 建议每天更新一次；这不是已证明的硬最大值。
- 红色长时间显示后，建议增加黑白清屏周期以改善效果；没有给出次数。
- 在低于 45%RH 或高于 70%RH 条件下，不保证 5 年 pixel display quality。
- 可靠性试验使用 150 s 状态保持，并在试验后于 20～25°C 放置 2 h。它们是资格试验步骤，不能转写为运行冷却时间。

相邻 V1.2 样例展示 POF、等待 BUSY、至少 10 ms、等待 6 s、PSR `0x4F 0x6E`、等待 BUSY、等待 1 s、再由样例硬件切 VDD。它只能作为向厂商核对和保持保守关断基线的 P 级证据；当前 `EPD_PIN_SWC=-1` 也不能物理切断 J2-1。

精确恢复序列、minimum cooldown、最大连续刷新、每日最大次数、强制清屏次数、rated cycles、retention lifetime 和 partial/Sparkle endurance 全为 `null`。因此禁止自动连续刷新和无人值守耐久测试。

## 6. 仍须向厂商索取的受控资料

1. 明确覆盖 rev `0x04` 的 SPD1657B 完整 datasheet 和 command supplement。
2. 当前 MF-17506-M009F-T 的 OTP manifest：ID、版本、CRC/hash、lot binding、温区及选择规则。
3. 精确 3-bit 全码表，包含 0x4、0x7 和 bit3/reserved-bit 规则。
4. LUT upload/select/readback 能力声明；若支持，需格式、合法范围和 readback；若不支持，需明确否定声明。
5. 0x86 的语义、区域编码、前置条件和安全限制。
6. window、old-frame、partial、Sparkle、Ripple 的精确兼容矩阵和支持包。
7. 内部温度读取命令、格式、换算、校准、精度和 waveform 温区映射。
8. VCOM/VGH/VGL/VSH/VSL/VPH/VPC/PREVGL 的 nominal、tolerance、absolute limits 和测量条件。
9. 厂商要求的 recovery/cleanup、cooling、maximum consecutive refresh、retention 和 rated-cycle 限制。

## 7. 安全结论与 go/no-go

| 项目 | 决策 | 原因 |
|---|---|---|
| 继续 B/C 非硬件工作 | `GO` | 不需要危险假设，可继续主机工具、schema、模拟测试和门禁文档 |
| D/E 原厂六色硬件基线 | `NO-GO`，等待明确硬件授权和测量门禁 | A 阶段没有上电/刷新授权 |
| F 未知码实验设计和模拟 | `GO`，仅设计；实现前停审 | 正式 API/guard 必须保持不变 |
| G 0x4/0x7 硬件探针 | `NO-GO` | 需 F 审查、build/hash、刷写和指定帧逐项授权 |
| H bit3 alias | `NO-GO` | bit3 行为完全未知，且需 G 报告后再次授权 |
| I LUT/phase/电压 | `HARD BLOCKED` | 缺精确 datasheet、OTP、接口、限值、联锁和厂商寿命要求 |

## 8. 阶段执行记录

实际执行：

- 完整审阅本地 MF-17506 厂商规格。
- 审阅 E Ink E6_73 V1.2 样例，并按其 800×480、192000 B 几何将其降级为相邻平台证据。
- 检索并审阅 E Ink/Solomon 官方网页、官方产品资料和正式论文。
- 建立 D/P/I/U 四级矩阵；所有未知可执行值均在 JSON 中写为 `null`。

未执行：

- 未上电，未刷写 COM8，未调用刷新 HTTP 接口。
- 未发送任何 SPI 测试命令。
- 未修改 LUT、waveform、timing、PLL 或任何电压。
- 未做硬件测量、自动重试或连续刷新。

授权记录：A 阶段为只读工作，无需也未请求硬件授权。

Git：未提交、未推送；commit/build/binary/frame/DTM hash 对本只读阶段均为 `null`。

原始硬件数据：无。异常与恢复结果：`null`。Hardware tested: `NO`。
