# SPD1657 / E2802 STM32 runtime-waveform 逆向增量

日期：`2026-08-11`  
结论：`STRICT SAME-VERSION MODE-1 ABI: NO-GO / EMPIRICAL H3 CODE-SCHEMA: CONDITIONAL GO / C-FIRST PHYSICAL: 0/4`

## 1. 直接结论

当前目标中已经找到两份**很可能是真实多色内容的厂家波形候选**：`WF20_25[842]` 和此前
漏检的 extensionless `WF23_25[876]`。两者都不是随机误解密，也不是 dither 资源；它们
各自独立满足同一 `800-byte ciphertext + key envelope` 家族，解密后又都精确满足
`7+9*(8*11)+1 trailing zero`；末字节只是 record 之外、作用未知的 outer suffix，不能命名为
padding、sentinel 或 checksum。两份 plaintext 只在 `443/800` 个位置相同，说明这是两套真实不同的
vendor profile，而不是同一数组的改名或复制。

新增的 wrapper-alignment 审计把长度关系进一步限定为：`535→544` 与候选 `799→800`
分别只是各自长度的**最小 16-byte AES block roundup**。已知 mode-0 loader 只向 `0x20`
转发解密区的前 535 bytes；两份 mode-1 候选的第 800 byte 都为 zero 且落在
`7+9×8×11=799` 几何之外。这个共同形状与 AES zero-fill 相容，却仍不证明该 byte 是
encryption padding、controller terminator、sentinel 或 checksum；没有同 build mode-1
loader/generator 时，其作用保持 `UNRESOLVED_AES_BLOCK_ALIGNMENT_COMPATIBLE`。

但“找到多色波形内容”不等于“已经有可直接使用的 runtime profile”。当前随包库是固定
`E5_3Bit_Mode=0 / decode=544 / WF_SIZE=535` 构建，已经由 CROF relocation 和 DWARF
正式证明其 `0x21/704` 数据来自独立的全 `FF` `LUT1_DATA`。新完成的 2020 IAR
E2801/E2802 对象逆向则分别证明旧 runtime 路径实际发送
`0x20/799 + 0x21/704*FF`；它与候选的
`800=799+1 trailing outer byte`、当前 mode-0 的 `544-byte decoded block / 535-byte logical
payload` 长度关系高度吻合，使 H3 成为目前最强
假设。进一步的官方 XLINK + TI MSP430 objdump 复核又证明这两份 legacy loader 的 slot
比较 selector 都被编译为固定 `25`，不是由实测温度动态决定。可是它们不是当前 SPD1657/ArmCC 的配对
mode-1 build，所以仍不能把跨代旁证冒充直接证明。

真屏是本目标的最终终点。当前首个可见动作不是直接 runtime K0，而是同配置、同 atlas、仅
删除 R20/R21 的 C 对照；只有 `C → 独立白恢复` 完整 finalized，才可在相同 0.1°C 温度下进入
`vendor K0 treatment → 独立白恢复`。严格证据路线仍要求 mode-1 ABI、双控、初始化、温区和
恢复合同全部闭合；用户若明确接受牺牲屏经验路线，也只允许使用下文 7.3 冻结的单一 H3
假设，并把所有跨版本拼接显式写进授权材料。新增 profile 把未来目标从“是否有第二套波形”
推进为“在同一受控实验温度分别验证 vendor K0”，但没有补出同版本 loader 或厂家温度资格，不能把经验固件冒充厂家
已验证序列。

本轮没有访问硬件、COM8、串口或设备网络，没有刷写、刷新、读取/写入 OTP 或下发 LUT。
解密只在进程内完成；审计输出不含 customer key、raw plaintext 或 live payload。

## 2. 厂家证据身份与 800-byte 包装

厂家原始 ZIP：`参考资料/REG-API-oqc(1)(1).zip`，大小 `17297740`，SHA-256：
`c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead`。
关键源文件和静态库与 ZIP 条目逐 byte 相同，因此双 CS source、842-byte 样例和库版本差异
均来自厂家交付物，不是 workspace 后改。

候选：`参考资料/REG-API-oqc(1)(1)/REG-API-oqc/Sample Code/WF20_25.h`。
initializer SHA-256：
`97efcac1cbc6604a52b942a00b13df349530e152fd28063ed9eda94a36e2dcc5`。

包装得到直接验证：

```text
[0..799]   800-byte AES-256-CBC ciphertext
[800..801] big-endian key length 0x0028
[802..841] 40-byte wrapped key
```

`wrapped_key[i] XOR wrapper[i]` 精确恢复随包 `E28xx.c` 的 customer key。库算法是
`AES key=SHA256(key)`、`IV=MD5(key)`。解密 plaintext 的 SHA-256 为
`1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f`，并精确满足：

```text
7-byte header + 9 * (8 groups * 11 bytes) + 1 trailing zero outer suffix = 800
```

| 区间 | 长度 | SHA-256 |
|---|---:|---|
| plain `[0:535]` | 535 | `54a6fe90594630b58fb50a5f7903f8590eb56a2fc2ec1ccb8f084dd9c30612d1` |
| plain `[535:799]` | 264 | `fab67d0aa34204ef0f7581a9e32e5979ef25323333a43a03f2499b4da482108a` |
| plain `[0:799]` | 799 | `3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26` |

`align16(535)=544`、`799=535+3*88`、`align16(799)=800`。其中前后两个等式只直接证明
各自是最小 AES block roundup；`799` 又是跨版本 H3 候选的逻辑长度，不能仅凭对齐关系称为
当前 source 的另一编译模式。这些等式既不能命名 outer byte，也不能单独决定 mode-1 的
`0x20/0x21` 长度和组装方式。

### 2.1 隐藏的第二份 `WF23_25`

厂家 ZIP 和展开目录都包含一个无扩展名文件
`Projects/MDK-ARM/12`。其文本头明确声明：`WF23_25.h`、E Ink Holdings、
`E5 2-bit`、日期 `2025-12-26 14:48`、`SIZE 876`。文件本体与 ZIP 条目逐 byte 相同：

| 对象 | bytes | SHA-256 |
|---|---:|---|
| source/header | 5776 | `c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d` |
| initializer wrapper | 876 | `d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4` |
| decoded plaintext | 800 | `95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8` |
| decoded `[0:799]` | 799 | `2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb` |
| decoded `[0:535]` | 535 | `a0e80080a710e68e4fed64d5640bb3d48ce20ef07c577e66e8566f6c3d119226` |

它的封装不是未知格式，而是精确的：

```text
[0..799]   800-byte AES-256-CBC ciphertext
[800..801] big-endian key length 0x004A
[802..875] 74-byte wrapped key
```

同样执行 `wrapped_key[i] XOR wrapper[i]` 会得到 74 个可打印 ASCII byte；以其
`SHA256/MD5` 派生 AES key/IV 后，解密结果再次精确得到 `7+9*88+1 trailing outer zero`；
末字节作用仍未知。正式工具只冻结
recovered-key hash，不输出 key 或 plaintext bytes。全 workspace 和原 ZIP 除 wrapper 自身外
都没有该完整 key 的明文副本。

两份 profile 的 category 5/8 都是全 `FF`，category 0--4/6/7 都有活动数据；但活动 group
分布、header 和其余 category 内容显著不同。`WF23_25` 与 `WF20_25` 仅 category 5/8
逐 byte 相同，PLL 请求相同，power 请求不同。这是第二份可复验 vendor profile 的强证据，
仍不证明 category→色码的唯一映射。

工程关系也被收紧：`atk_f103.uvprojx` 没有列入 `WF23_25`；
`atk_f103.uvguix.Administrator` 只证明该路径曾作为编辑器文档打开。现有 AXF/MAP 没有
`WF23_25`、`loadWF` 或可达的 800-byte loader，所以它不能冒充已链接/已运行 profile。

### 2.2 decoded header 的电气含义

当前 ArmCC `loadWF` 的 relocation/dataflow 直接证明 `PWR 0x01` 接收
`0x0F + plain[0:5]`，`PLL 0x30` 接收 `plain[6]`。SPD1657A Rev 1.0 手册 P21--22 又给出
PWR 字段公式，因此现在可把两个 decoded header 转成**请求值元数据**，而无需发布 raw byte：

| profile | VGH/VGL | VSH/VSL full | VSH_LV | VSL_LV | VSH_LV2 | VSL_LV2 |
|---|---:|---:|---:|---:|---:|---:|
| `WF20_25` | `+20/-20 V` | `+15/-15 V` | `+6.5 V` | `-8.2 V` | `+8.0 V` | `-8.8 V` |
| `WF23_25` | `+20/-20 V` | `+15/-15 V` | `+7.2 V` | `-8.4 V` | `+8.2 V` | `-9.8 V` |

两者四个 intermediate source code 都在手册公开的 `0x00--0x78` 编码范围，并处在
`VGH/VGL` 向内 2 V 的窗口内；这只说明寄存器请求没有触发手册所述边界 remap。它**不证明**
当前 FPL/膜批、面板绝对额定值、温区或 VCOM 组合允许这些值，也不把任何 profile 提升为
live-approved。两份 `plain[6]` 相同，按手册 P27 的 `PLL.FR[2:0]` 都请求 `43 Hz`；
legacy C 表的 `wf_data[5]` 被 source comment 标成 VCOM；这只命名该张 legacy 表的坐标，
不能倒推另一条 ArmCC wrapper 的 `plain[5]` 也是 VCOM。在后者的 retained `loadWF` 机器
数据流中，decoded `[5]` 没有专用 PWR、PLL 或 VCOM 寄存器写，但仍位于 opaque
`0x20/in[0:535]` 载荷内并随整段发出，所以也不能表述成“该 byte 未写”。

新增的 caller/loader 边界审计进一步固定了长度合同缺口：sample `main.c` 从 wrapper 的
bytes 4--5 取得 big-endian `COUNTER`，只对 `dataBuff[6:6+COUNTER]` 做 8-bit 加和校验，随后
仅把 `&dataBuff[6]` 指针传给 `loadWF`，没有传递或再次核对长度。ArmCC `loadWF` 固定复制
544 bytes并读取 offsets 544/545；旧 UART helper 虽接收 `buff_len`，函数体仍固定复制 535 bytes。
这条 UART 路径不是 dead source：交付 MAP 精确连出 `startup vector -> USART1_IRQHandler ->
USART1_receiveDataNnalyse -> Uart_save_wf_data -> wf_data`，源码 case 5 又证明传入
`&USART1_RData[6]`。helper 先清空 mutable `wf_data`，再复制固定 535 bytes；它自身不调用
`EPD_initial` 或 `0x20`，但它排除了“compiled initializer 在每次 upload 时仍是 runtime contents”。
这证明 pointer-only ABI 中缺少 caller-bound gate，但由于 sample main 未链接、`receiveData`
是空 stub 且真实 `dataBuff` 容量未交付，只能称 **contract gap**，不能升级成已证明 OOB 或可利用漏洞。

## 3. category 语义纠偏与三个 mode-1 假设

`User/EDP_init.c` 实际保留了两张完整的 535-byte source table：一张已整体注释掉，另一张是
当前 active initializer。两张表都在源码中逐条标出相同的 6 个 category 和每类
`GROUP1..GROUP8`，因此给出了比“全 FF 行对齐”更强的**源码坐标标签**：

| 区间 | 厂家注释 |
|---|---|
| `[0:7]` | `VGHL,VSHL_0,VSH_1,VSL_1,VSHL_1,VCOM,PLL` |
| `[7:95]` | VCOM，8 groups |
| `[95:183]` | Black，8 groups |
| `[183:271]` | White，8 groups |
| `[271:359]` | Yellow，8 groups |
| `[359:447]` | Red，8 groups |
| `[447:535]` | Power，8 groups |

这三层证据必须分开。commented 表位于 lines `13..61`，重建 SHA-256
`2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26`；它在当前 translation
unit 中不活动、在 `edp_init.o` 中没有完整表命中，作用未知，不能提升为 runtime candidate。
active 表位于 lines `63..111`，SHA-256
`716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`；它在交付
`edp_init.o` 的 ELF32 `.data` 中由 `wf_data` symbol 精确绑定 535 bytes，交付 MAP 又只有一条
把 535-byte `wf_data` 归到 `edp_init.o(.data)` 的 symbol row。最后，交付 C 源静态数据流明确
先写 command
`0x20`，再按索引原序发送当时 mutable `wf_data[0..534]` 的全部内容。这证明的是
comment label、compiled/linked initializer 和 delivered-C static forwarding 三个分开层级；由于上述
linked UART replacement 路径存在，它不证明 initializer bytes 是每次 upload 的 runtime contents，
也不证明该硬件路径曾运行或 controller-side decode。
两表同坐标有 `389/535` bytes 不同、零条同坐标完整 record 相同，因此也不能把 inactive 表
当成 active 表的简单副本或已批准替代物。

因此，800-byte 候选的零基 category `5` 虽然恰为全 `FF`，却处于 legacy `Power`
位置，不能唯一改称 pixel code `4`。早先的“category0=VCOM、category1..8=code0..7”
只能算 H1 的一种解释，现已撤回“高置信唯一映射”的表述。

在旧 IAR 对象闭环前，H1/H2 都假定 mode-1 仍向 `0x20` 写 535 bytes，只争论新增
264 bytes 怎样进入 `0x21`。旧对象给出了第三种、现在更强的解释：mode-1 改变的是
`WF_SIZE`，整个 799-byte 逻辑 payload 都进入 `0x20`，`0x21` 仍为固定全 `FF`。

| 假设 | `0x20` | `0x21` | 评价 |
|---|---|---|---|
| H1 重叠八行 | `plain[0:535]`，SHA `54a6fe90...12d1` | `plain[95:799]`，704 bytes，SHA `050f12e9...15ac`；行状态 active×4, FF, active×2, FF | 连续八行视图，但把 legacy Power 位置解释为 code4，并重复 440 bytes |
| H2 扩展 bank | `plain[0:535]`，同上 | `FF*440 + plain[535:799]`，704 bytes，SHA `27c4b947...1789`；只激活 rows 5/6 | 与 mode0 全 FF bank、样例 code5/6 相容，但需要一次 440-byte 补齐/拷贝 |
| **H3 完整 799** | **`plain[0:799]`，799 bytes，SHA `3cab2e29...ca26`** | **704×`FF`，SHA `24acee29...63f`** | **与旧 E2802 的实际 upload 序列、800/799 envelope/逻辑长度和 544/535 mode0 长度关系同时相容；当前首选** |

同一 H3 construction 应用于第二份 `WF23_25` 时，`0x20` 候选为 799 bytes、SHA
`2eeae0e8...88fb`，`0x21` 仍是同一个 704×`FF`。第二份独立 800-byte profile 显著增强
“800 是 mode-1 envelope、799 是逻辑 upload 长度”的结构解释；它仍然不能替代同版
mode-1 loader 对 `0x20/0x21` 的直接绑定。

H3 的新证据会把真屏实验优先级从 H2 改为 H3，但没有消除证据边界：旧对象来自 2020 年
IAR/MSP430 交付，当前库来自 2025 年 ArmCC/Cortex-M3，两个 wrapper 又来自
2025-12/2026-01；这些证据跨版本。没有当前配对的 mode-1 source/binary 或厂家 SPI capture，
H3 仍不能升格为已批准
真屏 payload，H1/H2 也不能被逻辑排除。

新增五路 category-alignment 审计又排除了“靠顺序或相似度补标签”的捷径。legacy 六个厂家
标签行与 IAR `DATA0` 前六行之间没有任何 88-byte 完整行匹配，也没有同序 `FF` mask 匹配；
顺序分配总 byte-Hamming cost 为 `312`，而全局最小为 `301` 且有 `30` 个等价最优解。
`DATA1` 相对九行对象的 offset 0/1 结果也互相冲突，没有任何非全 `FF` 完整行匹配。因此
`DATA0/DATA1` 的相邻 section、ordinal 或最近距离都不能给出 category→VCOM/颜色/Power 映射。

legacy VCOM row0 与 WF20/WF23 row0 确有唯一一簇相同的“非全 `FF`”11-byte record；但该
record 实际为 `10/11` bytes=`FF`、只有 1 个非 FF byte 和 2 个 distinct values，并在各 row0
尾部重复。它最多是低信息的 filler-compatible 弱线索，**不支持把 row0 提升为 VCOM
candidate**。报告
`.test-output/offline/mf1750_spd1657_category_alignment_audit_20260812.json` 的
file/canonical SHA-256 为 `f232446b0e014264b0452cd47331e0376487251b4b99ba85fe4fb658ee5b2ed4` /
`572a86bcbcdccb9aa17e4114b34cfef7b348f2492ee0154e43085db482780445`。

plain `[0:535]` 只由当前 mode-0 binary 直接证明；把它保持为 mode-1 长度不再是首选。
它也不等于历史 `wf_data[535]`：后者 SHA-256 为
`716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`，仅
`223/535` 个位置相等，不能称作本屏 OTP-equivalent baseline。

### 3.1 11-byte 只能证明为 group/record，不能命名为 phase

新增 metadata-only 审计把两份候选和两张 legacy source table 逐 byte、逐 category、逐 group
固定下来。两张 legacy 表的 48 个 record boundary 都由源码直接写成
`<category>-GROUP<1..8>`；但 `GROUP` 只是 source author 的槽位标签，源码没有把它定义为按时间
执行的 chronological phase，更没有命名 record 内 11 个 byte。下表的 legacy 统计只把
compiled/linked active initializer 当作静态 dataset，不宣称它是每次 runtime upload contents；
commented 表保持 role unknown，不列作 runtime 对照：

同一份 identity-pinned GBK 源码还把 `for(i=0;i<535;i++)` 与注释“循环次数根据不同的芯片规格
有所不同”绑定在同一行；schema-3 审计同时将相邻 source dataflow 收紧为
`EPD_WriteCMD(0x20) → i=0..534 → EPD_WriteDATA(wf_data[i])`，中间没有另一条源码语句。
这直接证明源码作者没有把 535 描述成跨芯片通用常量，但不证明 mode-1 必为 799/800、目标
controller revision 或双控 sink；H3 证据等级不因此改变。

| 载荷 | body 几何 | `FF` byte | 全 `FF` group |
|---|---:|---:|---:|
| WF20_25 | `9×8×11=792` | 518 | 34 |
| WF23_25 | `9×8×11=792` | 425 | 22 |
| legacy 535 | `6×8×11=528` | 198 | 8 |

WF20/WF23 的 body 只有 `439/792` 个位置相同；逐 category 差异数为
`[36,43,48,59,55,0,52,60,0]`，所以 category 5/8 在两份 profile 中稳定为全 `FF`，
其余 category 则确实随 profile 改变。当前 ArmCC adapter 逐 byte、指针递增地原序转发
library 给出的 pointer/length；旧 IAR loader 也支持 ordered opaque forwarding。两者都没有
把 11-byte 内部字段解码成电平、持续时间或重复次数。

进一步的 identity-pinned invariant 统计把“相同”与“可命名字段”明确分开：两份 800-byte
profile 为 `443 equal / 357 different`；去掉 7-byte header 后为 `439/353`，只有 `24/72`
条 11-byte record 完全相同，另有 175 个相同位置落在并非整体相同的 record 内。11 个 record
列索引都至少在一个位置发生变化，所以没有任何一列能凭这两个样本升级成全局常量或特定
phase/electrical 字段。IAR `DATA1[704]` 与 ArmCC 全 `FF` `LUT1_DATA[704]` 也只有
`420 equal / 284 different`、29 条 record 全同；这只是跨代结构对齐。报告
`.test-output/offline/mf1750_spd1657_waveform_invariant_stats_20260812.json` 的
file/canonical SHA-256 为 `84ac8584...c7f1` / `eb2c391b...8978`，且不输出 raw byte values。

`9×8×11` 对“VCOM + 8 个 target category、每个 target 有 8 个 source group”是 B 级结构
支持；若额外采用顺序映射，category 5/8 才会条件性落到 code 4/7，这与六色和既有 OTP
`4≡7` 观察相容。但 legacy mode-0 的 category 5 被厂家明确标为 `Power`，同版本 mode-1
loader 又缺失，因此上述映射只能是 C 级交叉一致性，不能升格为唯一 ABI。

SPD1656 也不能补这个缺口，但它现在提供了一个更精确、可穷举反驳的相邻布局。identity-pinned
Rev 1.1 手册 pp. 13/15/17/27--29 直接定义其 R20/LUTC 是 **VCOM** table：
`20 groups × 11 bytes = 220 bytes`；每组按零基 offset 为 `RP[0] + packed 2-bit
LVL[1:2] + TP1..TP8[3:10]`，`RP=0` 表示 `No Repeat, End of LUT`，`TP=0` 表示
phase skip。相同芯片的 R21--R28 color LUT 则是 `20×13=260`，R29/XON 又是
`20×10=200`。这与本地 R20 候选 `7+6×8×11=535` / `7+9×8×11=799`、R21 候选
704，以及所有非 VCOM category 也采用八条 11-byte GROUP 的结构形成直接几何和命令角色冲突。

新增 `tools/mf1750_spd1656_lutc_projection_audit.py` 固定 PDF 身份及六页 normalized-text hash，
并对六份本地 dataset 的 raw/bitwise-complement 两种视图、11 个候选 terminator byte offset
逐一穷举。排除 inactive commented table 后，raw 投影的 328 条 record 在 documented byte0 上
`RP=0` 为 **0**，即 41/41 category 均没有 SPD1656 字面终止符；取反后出现 147 个候选零、
37/41 category 具有 byte0 零后缀、34/41 进一步具有 whole-zero record suffix，但仍有 4 类
没有候选零、3 类在首个候选零后还有非零 record。更重要的是 whole-zero suffix 最大值在
byte offset **0 与 6 并列**，所以统计本身不能唯一识别 RP。固定 commit 的第三方
[`read_flash.m`](https://github.com/ts-manuel/Understanding-ACeP-Tecnology/blob/01356147a9a5e10c1599908d636b4776277766a3/matlab/read_flash.m)
也只把 raw flash slice 交给 parser，而本地交付 writer 同样原样逐 byte 发送；没有同版 controller
decoder 证明内部取反。

因此“取反后 `FF→0`”现在可提升为一个明确可检验的 **active-low/complemented structured
encoding hypothesis**，但仍不能移植 SPD1656 的 RP/LVL/TP、电平码或 phase 数。严格措辞继续
固定为 **11-byte group/record**；字段、电平、时长、`FF`/zero 含义、complement decoder 与唯一
category→pixel 映射全部仍为未证。metadata-only 报告
`.test-output/offline/mf1750_spd1656_lutc_projection_audit_20260812.json` 的 file/canonical
SHA-256 为 `3be92ff2aa01f16b7fab9042be7ae982e61c1d2bdb5f027005e780ad00798668` /
`8434152a38e713c76292854998fe3c5cc038a5922528803b9dba69f387c6d94f`；不输出 raw record，
不生成 payload，也不授权真屏。

另一个更接近本地 **group 数**、但不接近本地 ABI 的相邻 Solomon 器件是
[SSD1680A Rev 0.20](https://v4.cecdn.yun300.cn/100001_1909185148/SSD1680A.pdf)。本地固定
PDF 为 `1257063` bytes、SHA-256
`92ccb43dbcb847707ff907de9989ea18214c968f3584b7493e7460d9268a43bc`。其 pp.14--15/25/29
直接定义四个 LUT（LUTC/LUTR/LUTW/LUTB），每个 LUT 有 8 groups、每组 4 phases；每个
group 的真实布局不是 11 bytes，而是 **7 bytes**：`RP + 4×(VS[7:6]|TP[5:0]) + SR_AB +
SR_CD`。所以每 LUT 为 `8×7=56` bytes，四 LUT 共 224 bytes，再加 FR 与两个 XON bytes，
由 command `0x32` 一次接收 **227 bytes**；完整 waveform setting 连同 EOPT/VGH/VSH1/VSH2/
VSL/VCOM 为 233 bytes。相同手册中的 `0x20` 是 Master Activation，`0x21` 是两参数的
Display Update Control 1，不是 waveform payload。

新增 `tools/mf1750_ssd1680a_8group_projection_audit.py` 固定上述四页 normalized-text hash，
并把相邻 7-byte 布局在本地 11-byte record 的所有五个连续窗口、raw/complement 两种视图上
逐一投影。由于 2-bit VS 与 6-bit TP 恰好耗尽任意 byte，所有 `5×2` 个窗口都能在位域层面
“合法”，因此不能据此识别起始 offset、raw/complement 或字段。每条本地 record 仍有 4 bytes
无法由 SSD1680A 解释。把 SSD1680A 的 4 phases 人为扩成 `1 RP + 8×(VS|TP) + 2 SR = 11`
只是算术猜想；未找到“8 phases 但仍只有两个 SR”的控制器资料，若继续按一对 phases 一个
SR 的对称规则，反而应为 13 bytes。故它只证明“8 groups 是 Solomon 家族中真实存在的结构”，
不能命名本地 RP/VS/TP/SR、不能移植零值/电压/时序或 command。metadata-only 报告
`.test-output/offline/mf1750_ssd1680a_8group_projection_audit_20260813.json` 的 file/canonical
SHA-256 为 `d26f3f88c45b2f565d3d80e43d029e2d0695c8910f0bb3233f9fce2cbae61a92` /
`513b6ddeedcf3933af8577eb79fc28f73253f5cde94a92e1f2abe21fd5a3dcbe`；同样不输出 raw
record、不生成 payload，也不授权真屏。

因此目前三条 11-byte 解释仍互不闭合：SPD1656 VCOM 给出准确的
`RP+packed-LVL+TP` 宽度但错在 `20 groups` 与 color/command 角色；SSD1680A 给出准确的
`8 groups` 但真实组宽是 7、命令是 `0x32`；Philips Apollo 给出 11-byte instruction，但厂商、
控制器和字段体系均不同。把三者的“8 groups”和“11 bytes”拼在一起不是 ABI 证据。

legacy header 也不能反向补齐这些字段。active `wf_data` 的 header bytes `1..4` 在交付 C 中
另行绑定到 PWR `0x01`；byte `0` 只有注释 `VGHL` 和 opaque `0x20` 转发，byte `5` 虽注释并
赋给 `EPD_setting.VCOM`、byte `6` 虽注释 `PLL` 却赋给 `EPD_setting.Frame`，但这两个字段在
固定的 21 份 User C/H corpus 中都没有后续 named non-assignment use，专用 `0x82`/`0x30`
又分别使用独立 global/literal。故 record 内部的 drive/polarity、duration/repeat、voltage level、
`FF` 语义，以及 mode-1 九 category 与 `DATA0/DATA1` 的关系仍全部未知。

### 3.2 算术、变换与 checksum 的有界否定

新增 schema-2 算术/变换审计精确固定：

```text
535  = 7 + 6*8*11
799  = 7 + 9*8*11
800  = 799 + 1
704  = 8*8*11
1503 = 799 + 704 = 7 + 17*8*11
```

其中 `704=8*8*11` 只是一种 metadata-only 分段，不能赋予 LUT category、寄存器或控制器
语义。`DATA0` 精确等于 `first799+FF704`，但对象没有声明 799-byte symbol/subobject
boundary；`DATA1` 与 legacy535、DATA0-first799、WF20、WF23 均没有共同的非全 `FF`
11-byte record，DATA0-first799 与 DATA1 也没有共同的非平凡 FF-mask row。因此当前内容没有
给出 category/order bridge。

在明确列出的 identity、整段 complement、任意 row/record permutation、record 内反转后
permutation、uniform XOR 和 uniform mod-256 addition 这组有限变换中，WF20-first799、
WF23-first799 与 DATA0-first799 两两都无 exact transform。该筛查不穷尽其他编码，也不产生
新 waveform。两份末尾 zero 均不等于此前 799 bytes 的 sum、two's-complement sum、
one's-complement sum 或 XOR；所有 active record 也不存在同一 byte position 普遍满足这四类
简单 check-byte 关系。这只排除所测简单家族，不排除 CRC、MAC 或其他完整性编码。

各 row 都呈 active prefix + 可选全 `FF` suffix；跨全部数据没有 active record 以 `FF FF`
开头，record byte0 也未观察到 zero。它与 fixed-width padding 相容，但既不能把 `FF` 命名为
terminator，也不能把 byte0 或任何其他 byte 命名为 repeat/duration。WF20/WF23 七字节 header
只在 index 1--4 不同，0/5/6 相同；本工具只计算这些 header 坐标差异，ArmCC loader binding
和公开手册映射来自既有 identity-pinned 审计，并非本工具重新证明。报告
`.test-output/offline/mf1750_spd1657_arithmetic_transform_audit_20260812.json` 的
file/canonical SHA-256 为 `73003d115b2386d601826eaa4f704f3e2a3b45075030f75696906ff8a7dc8a4a` /
`b77e5edbc169257cc56cb3af25085a358b7a43aa433432117cce29ae40a8015c`；分析只在内存恢复既有
两份 800-byte plaintext，不输出或落盘 key/plaintext/waveform，也不生成 include、firmware
或可刷 payload。

### 3.3 Philips 11-byte frame instruction 是结构线索，不是 SPD1657 ABI

新增 primary-patent 对照固定了
[`US20070085819A1`](https://patents.google.com/patent/US20070085819A1/en)
（同族 `WO2005038765A1`）paragraph 0037/0048--0051 的 particular design。其对象是
Philips Apollo ASIC：一个 frame instruction 为 11 bytes；byte 0--7 按高位优先容纳
32 个 2-bit voltage selector，示例只给出 `00=0 V`、`01=+15 V`、`10=-15 V`，没有给
`11` 赋义；byte 8/9/10 分别是 display row time、相邻 frame delay、frame count。序列末尾
**可以**用 `FF FF` 指示，sequence field 中单个 `FF` 则进入 hardware-shaking escape；超过
三种 driver voltage 时 record 还可以加长。研究时取得的 13-page PDF 为 `1095324` bytes，
SHA-256 `7596c486fccf3e58ab84a6241993272feee8e06b91ab4f49eaba404713f46cbe`；离线工具不再联网。

把该布局原样投影到本地已证明的 11-byte 边界，得到：

| 候选 | 非全 `FF` record | 其中 selector=`11` | 活动 record 以 `FF FF` 开头 | 活动 record 以单 `FF` 开头 | byte 8--10 全 `FF` 的活动 record | category 内无 boundary `FF FF` |
|---|---:|---:|---:|---:|---:|---|
| WF20_25 | 38 | 887 | 0 | 5 | 7 | `[0]` |
| WF23_25 | 50 | 1176 | 0 | 2 | 7 | `[0,4,7]` |
| legacy 535 | 40 | 892 | 0 | 3 | 5 | `[0]` |

三个候选的全 `FF` record 都只出现在各自 category 尾部，且 boundary `FF FF` 后都没有再出现
活动 record。这一排列同时与 fixed-width filler 和可选尾部 terminator 相容；当前数据不能在
两者之间裁决。部分 category 根本没有 boundary `FF FF`，专利把 terminator 写成 optional，
而且本地 category 并未证明等于一条 Apollo display sequence。

更关键的反证边界是：即使按 filler 假设排除全 `FF` 尾记录，三份候选的 32-selector 投影仍大量出现专利
三电平示例未定义的 code `11`；若逐字采用该示例，就无法完整解码本地活动 record。byte
8/9/10 的值分布也只能作为位置统计，因为专利没有给可移植的单位/范围，本地 loader 又没有
字段解析。Apollo 的 four-gray/even-odd 32-waveform 设计与 SPD1657/E2802 的 3-bit、
`9×8×11` 候选几何并非同一已证 controller ABI。结论保持：**宽度相同与尾部 `FF` 对齐只提升
结构假设的可检验性，不允许命名字段、赋电压/时长、改造 LUT 或据此授权真屏刷新。**

## 4. 当前 ArmCC mode-0 loader 的形式化闭环

库：`lib/eload_3bits_M3_E2802_20251229.lib`，SHA-256：
`f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b`。
对象 `eload_20250305b1.o` SHA-256：
`92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d`。

编译合同：

```text
WF_DeCode_SIZE = 544
WF_SIZE        = 535
E5_3Bit_Mode   = 0
```

因此直接把 842-byte wrapper 交给该库时，它会在 offset `544` 读到伪 key length
`5157`，随后越界；两者明确不兼容。

ArmCC ORC 的 `.reli.loadWF` payload 已按标准 `Elf32_Rel` 对解析：member
`[0xAB4C,0xABB4)`，13 项/104 bytes，SHA-256
`2fa51656a10d7bf3ddf161c3ac5d74010429f1fbfa2aa08be430ea0cbaa93eae`。
关键 relocation 为：

```text
+0x56/+0x60/+0x6C/+0x78 -> sym F0 writeEPD, ARM_THM_CALL
+0x94 -> sym C0 pwr_d, ARM_ABS32
+0x98 -> sym BC in, ARM_ABS32
+0x9C -> sym C1 pll_d, ARM_ABS32
+0xA0 -> sym C4 LUT1_DATA, ARM_ABS32
```

DWARF v3 独立绑定出 `in[544]`、`pwr_d[6]`、`pll_d[1]` 和
`LUT1_DATA[704]`（type DIE `0x2A9`，upper bound `703`）。代码中第四次写之前的 Thumb
literal load 精确指向 `+0xA0/sym C4`，随后 `writeEPD(0x21, LUT1_DATA, 704)`；它不是
`in+95`，也没有 mode 分支。

成功序列正式收敛为：

```text
0x01 /   6 bytes = 0x0F + decoded[0..4]
0x30 /   1 byte  = decoded[6]
0x20 / 535 bytes = decoded[0..534]
0x21 / 704 bytes = independent LUT1_DATA
```

`LUT1_DATA` 位于 member `[0x1B54,0x1E14)`，为 704 个 `FF`，SHA-256：
`24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`。
这证明当前 build 的独立 `LUT1_DATA` 为全 `FF`、没有非 `FF` 扩展内容；它是否表示
disabled/no-op 仍未知，不能从这些字节擅自推断控制器语义。

#### `loadWF` CFG、解密门与代码边界纠偏

对同一对象的完整 DWARF/relocation/Thumb 复核得到 23 个函数。`loadWF` 的纯指令区为
code-stream `[0x4B4,0x53C)`（136 bytes），控制流图有 6 个基本块、7 条边、0 个回边。
它先调用 `strlen` 和 `test_decrypt_cbc_check_key`，然后只检查两个 global flag：

新增的 DWARF v3 line-program 独立审计在 member 中找到 31 个 structurally valid line units；
其中主源码的 24 个 units 是 1 个 empty unit 加 23 个 function units，23/23 都由函数 byte extent
与 declaration/first-row 坐标唯一绑定。`loadWF` 的 mapped line 范围是 `987..1023`，final row
回到 line `1020`；`strlen` 和 decrypt helper call 都落在 line `990`，四个 `writeEPD` call
依次落在 lines `1001..1004`。上一函数结束于 line `934`，所以 `935..986` 是 52-line 空档；
line table 只能证明这些活动机器指令的坐标，不能恢复 comment、blank line 或预处理删除的正文，
更不能据此宣称该空档包含 mode-1 branch。

```text
key_success == 0  -> return 0xE1（0 次 writeEPD）
key_success != 0 && wf_success == 0 -> return 0xE2（0 次 writeEPD）
otherwise -> 发出上述四次 writeEPD，return 0x00
```

必须注意：helper 的正常单线程路径只会在 key 比较失败时返回 `(key_success,wf_success)=(0,0)`，
或在比较成功、SHA-256/MD5/AES 调用直线返回后置为 `(1,1)`。它没有 plaintext magic、结构、
padding、MAC/认证或完整性检查，AES callee 也没有被检查的 status。因此 `wf_success` 只表示
解密调用已经返回，不表示 waveform 有效；`0xE2` 分支在机器码中真实存在，但 helper 的正常
同步返回不能产生 `(1,0)`，**不得把 `0xE2` 标为 waveform validation failure**。只有并发改写、
内存破坏等模型外状态才可能使该分支被观察到。同理，`0x00` 只证明 key 匹配、crypto 调用返回、
四次 writer 已发起，不证明 plaintext 有效或控制器接受写入；writer 的返回/效果也未被检查。

输入边界同样没有闭合：helper 没有 caller 总长度参数；它在比较前就从 wrapper 的
`[544:546]` 读大端长度，把 `wrapper+546` 复制到 DWARF 证明各为 75 bytes 的 `iniKey/ciniKey`，
执行 XOR 并写 `iniKey[len]=0`，却没有先证明 `len <= 74`。这是一条直接内存安全负证据，
不是 waveform 格式猜测。

最后，旧 COFF 包装曾把 code/data/comment 前缀 `[0,0x1453)` 整段交给反汇编器，不能把
`0x1453` 当成 executable end。23 个 DWARF 函数中的末函数 `xtime` 在 stream `0x1408`
结束，随后只有 4 bytes 对齐，`.comment` 从 `0x140C` 开始；真实 executable 区间为
`[0,0x1408)`，SHA-256
`51d7e843c3a1a95601c16c895a91f96ae182146d5560ee377502c111832e1f7c`。这一纠偏不改变上面
`loadWF` 和 helper 的独立函数 hash/边界。metadata-only 复核入口为
`python -m tools.mf1750_armcc_loadwf_deep_audit`，不会输出 raw key 或 plaintext。

### 4.1 workspace/归档/Git 全量 mode-1 搜寻

只读扫描覆盖 `16676` 个文件、30 个归档容器、600 个 ZIP 条目、唯一 7z 的 66 个文件、
121 个相关 `.lib/.o/.axf/.elf/.crf/.r43/.d43` 产物、7 份 Keil MAP/AXF、Git 全部
646 个 blob 和 5 个 unreachable commit。没有发现 `E5_3Bit_Mode=1`、
`WF_DeCode_SIZE=800`、匹配版 `LUT1_DATA` 或第二份 loader。

新增的 identity-pinned 厂家工件盘点把其中两个最相关目录精确闭合为 `430` 个文件：STM32
目录 `364 files / 82,180,051 bytes / manifest 5855f190...020d`，IAR 目录
`66 files / 5,631,058 bytes / manifest d2d52e3d...257a`。STM32 ZIP `c8174a...9ead`
在把 `14` 个 legacy 名字从 ZIP 的 CP437 显示还原为 GBK 后，与全部 `364` 个解压文件逐字节
相同；IAR 7z `8f326e89...b2ee` 的 `66` 个文件只证明 name/size 与解压树一致，因为 member
被加密且没有密码，**不得宣称 archive member bytes 相同**。精确编译标记
`E5_3Bit_Mode 1 / WF_DeCode_SIZE 800或809 / WF_SIZE 799` 均为 `0` 命中。

IAR `Debug/Obj` 交付了 `29` 个 `.r43`。`C2_Example.dep` 的 output file table 提到其中 9 个
项目对象，但该表是 producer output 库存，不是链接成员表；最终 D43 的 `inputs/XLINK` 关系只直接
选择 `DELAY.r43`、`E6_73.r43`、`main.r43`，另加一个 toolkit `dl430xlsfn.r43`。
`E2801/E2802.r43` 既不在 9 个项目 output 行中，也不是最终 D43 的直接输入，因而 H3 仍是
跨版本孤立旁证；这不证明它们从未被其他历史 build 链接。三个 backup 还分别引用缺失的
`WF25_25`，当前 sample main 引用缺失的 `WF00_05`；都没有留下可恢复的配对 profile 定义或
mode-1 object。

这次对 extensionless 文件的补扫发现了 `Projects/MDK-ARM/12` 中的 `WF23_25`，所以早先
“没有第二份 waveform”的口径已经纠正；“没有第二份 loader”仍成立。该文件只在 Keil
editor state 中出现，不在 `.uvprojx`，现有 7 个 AXF/MAP 也没有其 symbol、wrapper 或
可达 load call。

唯一 loader 库只有一个 member。7 份厂家 MAP 均为 `loadWF=0 / eload=0 / WF20_25=1`：
工程虽然在 LNP 中列出库，最终 AXF 没有链接 `loadWF`。mode-1 若位于 `#if` 的另一分支，
已经在预处理阶段被删除；反编译不能恢复从未进入对象的指令、常量、变量或 relocation。

针对 ArmCC/mode-1 残留的最后一轮 identity-pinned 审计又把配置边界收紧。Keil
`Output/atk_f103_USART.dep` 只描述 `target=USART`、36 个 file records、2001 个 includes；
项目 defines 为 `STM32F103xE/STM32F10X_HD/USE_HAL_DRIVER/__UVISION_VERSION=533`。
唯一 `.lib` 记录没有 compiler flags，也没有 loader `.c`，所以这些项目宏不能重编译或选择
预编译库内部的另一分支。对 430 个 pinned 文件按 ASCII、UTF-16LE/BE 和 uvguix hex-Data
扫描，仍只有同一个库分别一次命中 `E5_3Bit_Mode=0`、`WF_DeCode_SIZE=544`、
`WF_SIZE=535`，没有 `1/800/799` 绑定。

库闭包也只有一个 ar container、一个 `eload_20250305b1.o` member 和一个名为 `loadWF`
的 public symbol；7 个 LNP 的 35 项输入完全相同，7 个 SCT byte-identical，14 个 MAP/AXF
没有 library/member/loadWF/mode marker。uvguix 中 `REG-API-FOG`、
`WF-JD79661-128X296` 外部工程路径未随交付物出现；`79661.csv` 的 704/799/800/1503 都只是
连续 `Packet ID`，并无 CS、D/C 或 controller 列，不能升级成 transaction length。
有界判定为 `NO_ADDITIONAL_MODE1_ARMCC_ARTIFACT_IN_PINNED_DELIVERY`；加密 7z 的 member
bytes 和范围外未公开工件仍未被排除。

对 `79661.csv` 本身的 identity-pinned 审计固定了 `12722` 个 canonical decoded rows、
MOSI/MISO 与时间序列。对捕获 MOSI 的每一个可能连续窗口，逐一比对全部已知
535/704/799/800/1503-byte references，**exact contiguous identity 均为 0**；这只排除已知
载荷以原样连续 MOSI 出现，不能排除未知载荷、交错发送或捕获始末之外的操作。按大于 100 us
间隙条件切分得到 16 段，长度为
`57,7,2,2,6321,4,2,543,3,1024,1024,1024,1024,1024,657,4`，没有一段等于上述 payload
或 command+payload 长度；时间 gap 仍不是已证明的 CS transaction boundary。

一次明确获准的固定 GitHub commit 只读交叉还发现：首个 57-byte timing run 与 GxEPD2
GDEY0213F51/JD79661 初始化有 10/15 个 source groups 的 byte-pattern 命中，43-byte 扁平
初始化的最长公共子序列为 33 bytes，并有一段 12-byte/12-distinct-values 的精确连续片段。
JD79661AA 手册交叉把该片段进一步定位为完整的未公开 `0x03 + 3 data` 组，紧接完整且正式
定义的 `0x06/BTST + 7 data` 组；只有后 8 bytes 有正式表语义。它支持
**JD79661 init-fragment compatibility**，但完整初始化不匹配，公开面板为 128×250、
editor residue 为 128×296，且 CSV 缺 SCLK/CS/D-C/controller 列，所以不能证明具体面板、
exact generator、command/data role、单/双控制器或完整事务。报告
`.test-output/offline/mf1750_79661_capture_semantics_audit_20260812.json` 的 file/canonical
SHA-256 为 `c6ac5803f044608bf01de57f6acdfb20695dbf80fa840357bac948fd5024b97f` /
`9b4b257996b888512862285d1d02cae5819263077de4e85c3ce97ea25c49f9f8`；离线生成时没有重新
联网验证那份公共源码身份。

最初聚焦的两个相邻遗留对象之一为
`E6_73_sample code_V1.2_20250116/.../Debug/Obj/E2802.r43`，SHA-256
`19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce`。它包含
`EPD_Load_LUT`、`EPD_Load_LUT_const`、`Upload_Temperature_LUT`、`LUT0=0x20`、
`LUT1=0x21` 和 `Temperature_LUT_Counter=2508`，但不含 AES/842/loadWF，也不被当前
IAR 工程引用。它已完成独立 UBROF 逆向，结果如下；仍不能替代当前 mode-1 loader。

### 4.2 旧 IAR/E2802 的 `799 + 704*FF` 直接旁证

对象大小 `328062` bytes。identity-pinned helper 对 UBROF section record 和全文件唯一机器
签名做直接验证，恢复 `Upload_Temperature_LUT` 的实际发送序列：

```text
EPD_Load_LUT(0x20, dataBuff + 4, 0x031F)  -> 799 bytes
SPI command 0x21
repeat 0x02C0 times: SPI data 0xFF       -> 704 bytes
```

对应唯一签名包括：`0x17EA7` 的 `0x031F/dataBuff+4`、`0x17F8E` 的 `0x20/call`、
`0x18174` 的 `0x21/call`、`0x18426` 的 `0xFF/data call` 和 `0x1860E` 的
`compare 0x02C0/loop`。这不是从字符串或保留数组猜出来的。

边界也已逐指令收紧：`Upload_Temperature_LUT` 函数内只有上述两条 LUT 写入，没有
`0x01`/PWR、`0x00`/PSR、`0x30`/PLL、隐藏命令 `E9h`、PON、DRF、POF、BUSY wait、reset
或恢复调用。PWR/PSR/PLL 属于独立的 `EPD_Init`，其可证数据流为：

```text
0x01 PWR <- global dataBuff[18..23]
V_mode <- global dataBuff[14]
0x00 PSR <- (V_mode == 1 ? dataBuff[16] | 0x20 : dataBuff[16] & 0xDF), dataBuff[17]
...
Dyna_PLL <- global dataBuff[15]
0x30 PLL <- (Dyna_PLL == 1 ? dataBuff[42] | 0x08 : dataBuff[42] & 0xF7)
```

这些都是全局参数表的绝对索引，不是 upload 的 `dataBuff+4` LUT payload 索引；对象也没有
给出调用者如何预装该表、何时把 `EPD_Init` 与 upload 组合的闭环。因此旧对象不能证明把
当前 candidate `plain[0:7]` 拼成 PWR/PSR/PLL，更不能裁决 PSR 插入点或完整 runtime 顺序。

对象还保留两个未被该 active upload 引用的常量：

| 常量 | UBROF section/位置 | 结构 | SHA-256 | 结论 |
|---|---|---|---|---|
| `DATA0` | `0x14` / marker `0x53D0` | 精确为 `first799 + FF*704`；first799=`7+9*88`，rows 0–5 非 FF、6–8 全 FF | `eafe51e7...8bc5`；first799=`9317dfc9...338e`；last704=`24acee29...63f` | 直接初始化常量和 H3 结构旁证；不是 active source |
| `DATA1` | `0x15` / marker `0x5F94` | 704=`8*88`；前五行 active、后三行全 FF | `6dbd5a23...5e6a` | 保留常量，不是 active `0x21` 数据源 |

官方 XLINK 进一步把 E2801/E2802 两对象的 `DATA0/DATA1` 精确绑定到 `DATA16_C`
part 20/21，extent 分别为 1503/704；两对象的两个数组逐字节相同，但整对象的 size、SHA、
CRC、日期和 producer lineage 不同。对“除 DATA0/DATA1 外的全部 PUBLIC”做根化链接时，
其他非栈段均进入输出，part20/21 仍为 `NOT NEEDED`；单独根化数组时唯一 `REF BY` 是合成的
`?ABS_ENTRY_MOD`。所以两个完整对象闭包中的自然引用站点均为 0，交付 Debug 又不链接这两个
对象。`799` 也是对 bytes 的精确兼容性切分，不是对象声明的子对象边界。

这个结果不再只是 `1503=799+704` 的算术巧合：保留的直接初始化常量确实精确含一个
first799，后接与 active upload 动态生成载荷 byte-identical 的 `FF*704`。但 active
`0x20` 仍来自 `dataBuff+4`，active `0x21` 仍来自立即数循环，而不是 DATA0/DATA1。
它增强 H3 结构旁证，不证明 2025/2026 SPD1657 build 保持同 ABI，不证明 default role、
category/phase/electrical 语义、双控或 runtime→OTP 恢复；H3 仍是“首选待证假设”，不是 live GO。

`EPD_Load_LUT_const` 也已用官方 XLINK + pinned objdump 独立闭合。E2801/E2802 中
`EPD_Load_LUT_const` 与普通 `EPD_Load_LUT` 的四份 root-linked 实现都是同一个 32-byte
机器体（SHA-256 `28dcd417...11966`）：`R12=command byte`、`R13=source pointer`、
`R14=unsigned byte count`；先调用 `SPI_COMMAND`，再 pretest count 并逐 byte 调用
`SPI_DATA`，count=0 时不发 data。两 helper 的机器路径完全相同，`const` 只保留在源级名字，
不是 DATA0/DATA1 selector。root-only link 中两个数组均 `NOT NEEDED`；把其余全部 PUBLIC
根化时 const helper 在两对象仍 `NOT NEEDED`，而 mutable helper 都被 active
`Upload_Temperature_LUT` 自然保留。29-object/1786 paired-call scan 的 const consumer 为 0；
三个 UBROF11 EXTERNAL 表仍受旧 XLIB 的 E2 版本边界。当前 schema-2 报告
`.test-output/offline/mf1750_iar_load_lut_const_abi_audit_v2_20260813.json` 的 file/canonical
SHA-256 为 `46046593a43e453e1d7845f91f1e4cae895ab00125483d1f362efcfa5380e0e5` /
`01241e9f6ac31f20d06f99ee2e61431a4e2124509772545fd3e43fa485479c09`。它在原四个
root-only link/consumer 证据上新增完整 sender 与 SPI_DATA bit-serialization 判定；排除发送侧
隐藏常量选择、补码和 record parser，但不提升当前 800-byte ABI、controller decode、双控或电气安全。

对 generic sender 的逐指令数据流复核又把“发送侧是否解码”收紧为直接否定。E2801/E2802
两份 `EPD_Load_LUT` 都只执行 `command→SPI_COMMAND`，随后循环
`LDR.B [pointer]→SPI_DATA→pointer++→count++`，以无符号 count 比较结束；没有
`NOT/XOR/RBIT/REV`、11/88-byte stride、值比较或 early terminator。E2801 的参数/循环关键
记录位于对象偏移 `0x1B3B5/0x1B66A/0x1B742/0x1B92F`，E2802 对应
`0x16529/0x167CC/0x1689B/0x16A76`；caller 仍固定传 `dataBuff+4,799`。ArmCC retained
`loadWF` 也直接调用 `writeEPD(0x20,input,0x217)`，candidate writer 按 pointer 原序输出，
但该 provider 没有进入七份 final MAP。因而可直接证明的是 **MCU 发送侧固定长度、原序、无补码、
无 record parser**；不能据此裁决控制器内部是否存在 active-low/complement decode，也不能把
`FF` 命名为 terminator。该边界与 SPD1656 complement 投影的统计相容性必须分开。

IAR 调用图又把“upload 本体”和“完整显示流程”分开：`EPD_Init` 与
`Upload_Temperature_LUT` 互不调用，本对象中也没有 `EPD_Init` 的根调用者；七个可识别的
White/Black/Yellow/Red/line_4bit/Dot/Dot_4bit 显示函数都在 DRF 前调用 upload，并分别闭合
`PON → DRF(0) → POF(0)` 与 BUSY wait。这证明显示级电源闭环，不证明 reset、PSR 回滚、
factory OTP 或白屏恢复闭环。

进一步把 upload callsite 追到物理发送 helper 后，双控缺口反而更清楚。E2801/E2802 的 active
`R20/799` 与 generated `R21/704×FF` 最终都进入 byte-identical `SPI_COMMAND/SPI_DATA`；
root-linked helper 机器体和 GPIO anchors 固定为低有效 `P6OUT.3`（address `0x0243`、mask
`0x08`），没有 controller/CS 参数、mutable selector read 或第二条 CS 写入。它证明的是一个
固定 CS 路径，**不证明该脚物理接到哪一颗 controller**。ArmCC mode-0 的唯一 source-resolution
candidate 则是 `loadWF→writeEPD→sendSPICommand/sendSPIData→E_Paper_CS=PD8`；独立的
`PD11/ToBoth` API 虽存在，却没有接入 `writeEPD/loadWF`，且七份交付 MAP 都 omit `loadWF`
并 remove `writeEPD`。因此现有交付物没有闭合任一 `800-byte wrapper→同代 799-byte callsite`
或 `800-byte wrapper→dual-controller sink`；当前 matched V10/runtime V7 的双 CS 顺序仍是实验发送端实现，不是厂家
loader 恢复。

对交付的 29 个 `.r43` 又完成了 identity-pinned 调用站点清单/局部图：26 个对象是 UBROF10，
`DELAY.r43`、`E6_73.r43`、`main.r43` 是 UBROF11；逐文件版本门控后共恢复 `1786` 条与
CALLA debug-source 成对的 observed relocation 记录，其中 `1385` 条为 local-section-relative、
`401` 条为尚未解出 provider 的 external-index，另有 `20` 条不能把 caller 映射到已声明 section。
`E2801.r43`、`E2802.r43` 各有 7 条本地 display→`Upload_Temperature_LUT` 直接边，但两者均无
`EPD_Init→Upload_Temperature_LUT`，也无本地 root 同时可达 init 与 upload。

随后按 XML 语义重解析 `C2_Example.dep`，撤回此前把 output table 的 9 个项目 `.r43` 行都称为
“当前链接对象”的说法。最终 D43 的 root XLINK input IDs 精确映射为
`lnk430f5502.xcl`、`multiplier32.xcl`、`DELAY.r43`、`E6_73.r43`、`main.r43` 与
`dl430xlsfn.r43`；其中直接项目对象只有 `DELAY/E6_73/main` 三个，`E2801/E2802` 都不是该
配置的直接 XLINK 输入。

现在又对 identity-pinned `Debug/Exe/C2_Example.d43` 直接执行官方 XLIB 6.1.3.56
`LIST-OBJECT-CODE`，没有重链接。解析得到 31 个 module、25 个 public code symbol、19 个
call frame 和 188 条 direct call，并逐条用 CALLA 机器字节验证目标。最终 provider 因此成为
直接证据：`main` 在 `0xA20C` 调用 `E6_73::EPD_Init`，并调用同属 `E6_73` 的六个 display
routine；`delay` 属于 `DELAY`。`EPD_Init` 的 51 条直接调用精确分解为 `SPI_DATA=35`、
`SPI_COMMAND=13`、`reset/check_busy_high/delay` 各 1；六个 display routine 各为
`SPI_DATA=7`、`SPI_COMMAND=5`、`check_busy_high=3`。

D43 的 25 个 `t_org (01)` 与 62 个 `t_abs_var` 重构 2002 unique bytes；它与同一 Debug
extra output TI-TXT 的 `A000` 2000-byte 段及 `FFFE` reset-vector 2-byte 段逐地址、逐 byte
相等，故 TI-TXT 不是另一条 runtime final。该 final 的 31 个 module 不含 E2801/E2802，且无
`Upload_Temperature_LUT` scoped name、direct call 或 raw marker，精确判定为
`current_final_named_runtime_upload_path=NOT_FOUND`。E2801/E2802 各七条 display→upload 边
仍只属于各自本地 legacy candidate；`ED020OC4` 的孤立同名 definition 也不是 final provider。
final 内嵌 source lineage 为 `E6_73_sample code_V1.1_20231030`，不能称交付目录
`V1.2_20250116` 源码的重建。final 的 `SPI_COMMAND/SPI_DATA` 都只操作固定 `P6OUT.3`
（absolute `0x0243`、mask `0x08`）这一软件 CSB endpoint；这既不证明物理 controller 数或
扇出，也不给出双控 load/commit 语义。exact final 中没有 named upload，不能扩写为芯片能力、
其他构建、剥离/间接路径或厂家历史上从不存在 runtime LUT。

对同一 final D43 的 GPIO/transport 机器审计又固定：SDA=`P4.6`、SCL=`P4.7`，physical
DC=`P5.0` 初始化后保持 low，command/data 由 SDA 上的第九 bit `0/1` 区分，因此是 software
9-bit 3-wire SPI；唯一软件 CS 仍是 `P6.3`，RST/BUSY/SWC 分别为 `P6.1/P6.2/P6.0`，没有
第二个 CS 或 CCSET enable。六个 display function 都循环发送 192000 packed bytes，TRES 为
`800×480`；所以该 final 不是 exact MF1750 `1024×600` 的 geometry，也不能从 single software
endpoint 推出物理上只有一颗 controller 或已经对两颗广播。

随后从 TI 官方 `slac050ba.zip` 静态解包出 EW430 6.20.1 的原版
`xlib.exe` 6.1.3.56（`550912` bytes，SHA-256
`ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284`）；没有运行
autorun/setup，也没有安装工具链。它能直接解析全部 26 个 UBROF10 对象。把 XLIB 输出的有序
`EXTERNAL` 表逐项接到上述 `0x5D` external-index 后，共复核 `349/349` 条调用，符号不一致为
`0`。因此这 349 条不再只靠 debug-source 中的人类可读名字；`E2801/E2802` 的 index `3`
均由官方 XLIB 独立确认为 `ReadData`。两对象各有 11 个 external，entry 分别为 50/49 个，
且都直接列出 `EPD_Init` 与 `Upload_Temperature_LUT`；唯一 entry 差异是 E2801 多 `for_AX`。

同一旧 XLIB 对 `DELAY/E6_73/main` 三个 UBROF11 对象均明确返回
`Error [14]: Unknown tag: E2`，所以这三份绝不能解释为零 external/entry。IAR 7.21.1 的官方
[XLINK release notes](https://netstorage.iar.com/FileStore/STANDARD/001/000/603/ew/doc/infocenter/xlink.ENU.html)
说明 stack-usage analysis 到 6.2.0.62 才加入，并在 EW25659 中明确记录 XLIB 读取含
stack-usage 信息的 UBROF 时会报 `Unknown tag: E2`，修复版本为 6.3.4.78。当前 6.1.3.56
早于该功能和修复；三份原件的 native EXTERNAL/ENTRY 表因此保持**工具版本边界**，不能冒充
由旧 XLIB 原生解析。下面的 projection 已把其中 52 条 external-index 作独立一致性核对，但
用 6.3.4.78 或更新版 XLIB 直接解析原件仍是待办。

为把“找新版工具”从开放式搜索改成精确缺件，新增了官方/本机 XLIB availability 审计。八个
显式本地根的可读范围只找到 identity-pinned 6.1.3.56，`>=6.3.4.78` 候选为 0；七个不可读
目录点被显式记录，所以结论严格是 readable-scope negative，不声称全盘不存在。IAR 官方
release notes 固定 EW25659 修复版本为 6.3.4.78；EW430 6.40.1 standard/baseline 匿名页都要求
有效 SUA 且 download anchor 无 href，当前 MSP430 8.10 evaluation 进入注册/许可表单；审计只
GET、没有提交表单或凭据。TI 匿名 SLAC050 仍只提供 IAR 6.20.1。报告
`.test-output/offline/mf1750_iar_ubrof11_xlib_availability_audit_20260812.json` 的
file/canonical SHA-256 为 `de6cecae3f63558328d1a32ef199e4e96bfaf0c4b0827759b7ef616c87c37ea0` /
`d8f318b2062e6a37cc6c0bcf8e72c41bdc79e5e54204fe0e17f6600c185f8198`。精确最小缺口因此是：
合法取得官方 `xlib.exe >=6.3.4.78`，固定 size/SHA/file version/provenance 后，在 ASCII 临时
副本上只读执行 `3 objects × (LIST-EXTERNALS, LIST-ENTRIES)`；目标现在是原件 native-table
复核并消除投影假设，而不是声称 52 indices 尚未经过任何核对。

新的 schema-2 UBROF11 审计保持三份原件不变，只对 exact-hash 对象按 exact-offset allowlist
在临时副本移除 25 个推定 E2 spans、共 592 bytes：22 个推定 function-associated record、
3 个推定 stack-catalog record；保持 UBROF11 major version并重算 module CRC。所有 E2 分类和
`E2 + one-byte payload length + payload` framing 均明确为 inferred，不是 general scanner、
UBROF parser 或 link/flash input。第三方 experimental mspgcc UBROF5 decoder 中的 CRC 算法
在交付 29/29 对象上匹配，但它不是 IAR specification。

旧官方 XLIB 对三个 projection 列出的 `EXTERNAL/ENTRY` 数分别为 DELAY `4/3`、E6_73
`5/25`、main `13/26`；全部 52 条 paired external-index call 零冲突。main index `0..8`
精确为 `spi_9b_init/delay/EPD_Init/White/Black/Red/Yellow/Blue/Green`。原件仍原生报
`Unknown tag:E2`；本次引用的 IAR release notes 与 2005 record-tag note 都没有给出 byte-level
E2 grammar。因此严格措辞是“官方 XLIB 在 deterministic projection 上列出的表”，不是原件
native parse。报告
`.test-output/offline/mf1750_iar_ubrof11_e2_projection_audit_20260812.json` 的
file/canonical SHA-256 为 `7d3ff40fac47295c68f55044935201cdc9867e10f803be4117ac293baf4936bc` /
`15647b3c522d298ff8e2fa2782835c0d7b97577fdf02bed5b4cec9fed726683c`。

在此基础上，新的 no-offset differential scanner 把覆盖从三个 delivered object 扩到
`3 delivered + 29` 个 commit/blob/SHA 固定的 public third-party MSP430 UBROF11 object。
在这 32 个 exact object 中共选择 139 条 observed E2 record；98 条 function record 无 root
category、9 条带 `interrupt` root，另有 32 条 `CSTACK` catalog，9/9 interrupt root 都有
`??INTVEC` alias backreference。全部 107 个 caller name reference 和 126 个 direct-callee
name reference 都在各自 namespace 中解析，delivered object 的 caller/callee 集与独立
machine-relocation graph 零冲突。32/32 原件在固定旧 XLIB 都复现 `Unknown tag:E2`；只在临时
副本删除 scanner 选中的 E2 record 并重算 CRC 后，32/32 projection 的
`LIST-EXTERNALS/LIST-ENTRIES` 才能解析。

这使 `E2 + payload_length_u8 + payload` 及当前 corpus 中的 function/catalog 结构成为可复现的
**observed MSP430 dialect**，并补到先前 exact-offset corpus 没有覆盖的 interrupt-root case；
它仍不是官方通用 UBROF11 grammar，field name/role 仍是 inferred，也没有获得任何原件的新版
XLIB native parse。官方 XLINK history 只证明 UBROF11 增加 stack usage、EW25659 在
`6.3.4.78` 修复 `Unknown tag:E2`，并未公开 byte grammar。public corpus 的三个 pinned commit
也均未发现 LICENSE/COPYING，报告只保存 metadata，不推定许可、不再分发 object bytes。
这些 projection 绝不能作为 object replacement、link 或 flash input。

所以当前有两层不同的负证据：对 exact final D43，named runtime-upload path 直接为
`NOT_FOUND`；对三个原始 UBROF11，可由 projection 证明符号表/52 个调用索引自洽，但 native
tables 仍受旧工具 E2 边界。两者都不能改写成“芯片或厂家从未存在配对流程”。

相邻 `E2801.r43`（`315632` bytes，SHA-256
`404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3`）现已另做独立、
identity-pinned UBROF10 证明。其 `Upload_Temperature_LUT` 先执行
`0x40 → BUSY-high → SPI_GET_DATA`，再以 `ReadData(selected_address, dataBuff, 2508)` 写入
`dataBuff`。后续官方 XLIB type table 已直接把该符号声明为 `unsigned char[2560]`；因此容量现在
是对象类型元数据的直接证据，不再只是 backing-section extent 推断。
该调用的 `0x5D/0x03` 是 external symbol index，不是本地 section ID。
随后在函数内部按 `V_mode` 写 PSR=`0x00`，数据为
`dataBuff[2] | 0x20` 或 `dataBuff[2] & 0xDF`，最后执行
`EPD_Load_LUT(0x20, dataBuff+4, 0x031F)` 与 `0x21/0x02C0×FF`。它也有 7 条本地
display→upload 直接边，且 `EPD_Init` 与 upload 互不直调。关键机器记录分别固定在
`0x1BED1`、`0x1D20B`、`0x1D96D/0x1DF0D`、`0x1E0FE`、`0x1E1EE`、`0x1E3E6`
和 `0x1E8AD`；工具只输出元数据/哈希，不输出 LUT bytes。

对这两件 UBROF10 原件还新增了独立的 linked-disassembly 审计：使用同一官方
`xlink.exe 6.1.3.56` 在临时 ASCII 目录做单对象链接，把未交付 provider 仅定义为固定的
dummy external 地址，再使用 TI 官方 MSP430 GCC 7.3.2.154 的 `msp430-elf-objdump` 解码。
这些 synthetic linked address 只用于分析，**不是原始对象地址、外部存储物理地址或 SPI
transport 证明**。精确结果为：

- E2801 与 E2802 都执行 `MOV #25,R9`，温区 selector 固定为 25；
- E2801 先发送 TSC `0x40`、等待 BUSY 并调用 `SPI_GET_DATA`，但返回值留在 R12，未复制到
  selector R9；E2802 的 upload 函数根本不读 TSC；
- 两者都遍历 `i=0..29`，对逻辑地址 `0x1000 + i*0x1000` 先读 2 bytes，并在首个
  `lower <= 25 < upper` 的 slot 停止；30 个 slot 均不匹配则返回 status 1，不做 bulk upload；
- 匹配后从同一逻辑地址读 `2508` bytes。E2801 只在 upload 内使用 byte 2 生成单字节 PSR，
  byte 3 未用，`dataBuff+4` 的 799 bytes 送到 LUT0；E2802 在 upload 内不使用 byte 2/3；
  两者的 LUT1 704 个 `FF` 都由循环生成，不来自这 2508 bytes。

函数级锚点也固定：E2801 synthetic range `0x1002e..0x10129`、252 bytes、SHA-256
`bbf72104...e697`；E2802 为 `0x10020..0x100df`、192 bytes、SHA-256
`73486fe3...46dc`。这纠正了一个重要边界：legacy 的 2508-byte temperature slot 是旧存储
容器，不能直接证明当前 800-byte wrapper ABI；旧 loader 的文件名/slot 选择也不能充当实时
面板温度资格。

`E2802.r43` 的对应读取也已按同一 ABI 纠正为
`ReadData(selected_address, dataBuff, 2508)`。文件偏移 `0x17CCF` 的 relocation 只能证明
operator=`0x5D`、external-index=`0x03`、addend=`0`；它不能把 `0x03` 解释成本地 section，
而伴随的官方 XLIB EXTERNAL 表现已独立证明该 index→`ReadData` 绑定。该绑定仍不能证明
provider 对象、实现位置或物理 transport。官方 XLIB `LIST-OBJECT-CODE` 的后续类型审计已补出
独立符号大小：两对象均为 `dataBuff = unsigned char[2560]`；它仍不证明读取 provider、存储
地址语义或 transport。

同一类型审计还直接固定 `DATA0 = const unsigned char[1503]`、
`DATA1 = const unsigned char[704]`、`EPD_Load_LUT = void(uint16,uint8*,uint16)` 与
`ReadData = void(uint8,uint16,uint8*,uint16)`。完整 internal `t_push_rel` inventory 中
DATA0/DATA1 的 section reference counts 均为 0，与全 PUBLIC root 链接中的 `NOT NEEDED`
相互独立一致。对象完整 array-dimension inventory 没有 799-byte subobject，也没有
11/88/category/phase/voltage 类型，因此类型信息闭合了 legacy 容器与 generic sender ABI，
没有闭合当前 800-byte wrapper 或 799-byte body 字段。metadata-only 报告
`.test-output/offline/mf1750_iar_xlib_type_symbol_audit_20260812.json` 的 file/canonical
SHA-256 为 `608f54b06f12d9e393c6a3760b1ff3fc351db6ebd547e99f625754874fc5cd4a` /
`2e777a28642c683c0c131a025525a531f969b86734048b0dd79e435718c7f4b3`。

Source Browser 旁证同样保持有界：`C2_Example.pbw` 是 3187-record JSON，只含
`EPD_Init` 的 1 条 definition 与 2 条重复 declaration，没有 upload/`ReadData`/`EPD_Load_LUT`
记录，也没有 caller/reference/edge 字段；它不能补出 init→upload 可达性。孤立的
`E2801.pbi` 只保留原始工程路径与编译选项（MSP430F5502、small data、`-Ol`，并关闭
CSE/unroll/inline/code-motion/TBAA）；`C2_Example.pbd.linf` 仅聚合
`DELAY/E6_73/main.pbi`，没有聚合该 E2801 working file，且其绝对路径 lineage 与 `.pbw`
不一致。因此这些 browse 文件可作来源/编译配置旁证，不能恢复缺失源码正文或最终链接成员。

对 workspace/project/DEP 的独立配置链审计又补上两个版本边界。`C2_Example.ewp` 的 Debug
和 Release 都只声明共享源 `DELAY.C/E6_73.c/main.c`；Debug 实际生成链的 direct project
inputs 仍只对应这三件对象，`C2_Example.txt` 只是同一次 XLINK 的额外 TI-TXT 表示，并非
alternate runtime final。Release 的 DEP output 为空、目录和产物均不存在；本地 7 个 `.xcl`
都是 Source Browser 参数，不是隐藏 linker response。更关键的是，现成 `E6_73.r43` 的
producer 路径明确嵌入 `E6_73_sample code_V1.1_20231030`，而交付 `E6_73.c`/version note
是 V1.2_20250116 且新增 6 处 display VDD-cut。因此现成 `.d43/.txt` 只能称
`V1.1 object lineage`，不能冒充 V1.2 源码重编译。配置报告
`.test-output/offline/mf1750_iar_project_config_chain_audit_20260812.json` 的
file/canonical SHA-256 为 `b08d5e19...bebf5` / `15576687...da60a`；有界判定为
`NO_FINAL_LINKED_ROOT_TO_RUNTIME_UPLOAD_IN_DELIVERED_CONFIGURATIONS`。

E2801 与 E2802 还各自嵌入完全相同 SHA 的 `DATA0=1503`、`DATA1=704` 常量，但两份 active
upload 都从运行时 `dataBuff` 取 `0x20`，且直接发送的 `0x21` 是循环生成的全 `FF`；常量相同
不能提升为它们被 active upload 选中的证据。真正关键的版本漂移是：E2801 把 PSR 放在 upload
内部，E2802 则把 PSR 只留在独立 `EPD_Init`。两者都会对旧 PSR 数据执行
`OR 0x20 / AND 0xDF`，但 SPD1657A 手册把当前 2/3-bit `P_mode` 定义在首个 PSR byte 的
bit4；因此旧代码的 bit5 `V_mode` 绝不能重命名为 SPD1657 3-bit 证据，也不能用于决定当前
PSR 插入点。

### 4.3 最终 AXF 的双控 factory 路径与可达 runtime 路径并不相交

对全部 7 对最终 AXF/MAP 的 identity-pinned 重建确认：其中 5 个 M009/M032 build 共享同一
双控 factory init，22 个事务的规范 trace SHA-256 为
`9eb1db5d22278d66a5483c38833b20f7ef0cffa3065b16c01d31841346b7fd31`。所有写入均为
`ToBoth`，PSR=`5F,69`、每控制器 TRES=`512×600`、E0=`01`；trace 中没有
`E9/0x20/0x21`。所有最终 MAP 又都明确移除了 `EPD_initial_noOTP`，最终 AXF/MAP 也没有
`loadWF`、`WF23_25`、`LUT1_DATA`、`E5_3Bit_Mode=1`、decode800 或 WF_SIZE799 指纹。

另一方面，当前 source/linked call graph 的普通显示入口可达 `EPD_initial`；该函数是另一条
固定 mode-0 路径：generic master-only writer、PSR=`0F,A9`、PWR/PLL/TRES、隐藏
`E9=01`，最后只写 `0x20/wf_data[535]`，没有 `E0` 或 `0x21`。因此目前交付物里存在的是：

```text
双控 factory:  ToBoth + 5F,69 + E0 + no runtime LUT
单控 runtime:  master-only + 0F,A9 + E9 + 0x20/535 + no 0x21
旧代 H3 upload: no paired init + 0x20/799 + 0x21/704*FF
```

没有任何一条已链接路径同时具备 `ToBoth + 5F,E9 + E9 + 799 + 704`。把三行拼成真屏
序列是可审计的牺牲屏经验假设，不是反编译恢复出的原函数。

## 5. 双控制器与板级证据

厂家 `User/EDP_init.c` 确实含 `ToMaster/ToSlave/ToBoth` primitive，初始化路径也有
ToBoth 调用。静态库 debug 是按另一个 `../eink_code/E28xx.h` 编译，包含
`MASTER_0=0x00`、`SLAVE_1..7`、`MAS_SLA=0x10` 和 `spiChipSelect`。但是交付的
`Sample Code/E28xx.h` 没有这些声明，交付的 `writeEPD()` 也不读取 `spiChipSelect`，最终
落到 legacy master-only writer。`loadWF` 自身没有 controller/CS 参数、BUSY、reset、
PON/DRF/POF、readback 或 recovery。

交付物中唯一 `EPD_initial_noOTP()` 也不能补上这个缺口。它是未被调用的 dormant source，
固定 `Source=Gate=428`，使用 generic master-only writer，并把 encrypted wrapper
`WF20_25[1/2/3/4/6]` 直接当寄存器值，而不是使用解密后的 header。它虽然出现
`PSR=0x0F,0x89` 和 `0xE9=0x01`，但不是当前双控面板的配对初始化。

相对地，`Sample Code/E28xx.c::epdInitial()` 会 reset、使用 ToBoth、设置
`PSR=0x5F,0x69` 和 `TRES=512x600`。这使“reset 后重新执行 factory init”成为恢复候选，
但没有 post-runtime 状态/readback 或真实恢复 capture，仍不能称为确定的 OTP 恢复合同。

SPD1657A 手册的 PSR 位表进一步证明：`5F,69` 是 3-bit + `LUT_EN=0`（OTP），而 dormant
`0F,89` 是 2-bit + `LUT_EN=1`（MCU），且还同时改变 RES/FOPT，绝不能整体复制到当前
双控面板。保持 factory 其余位不变时，最小位级推导是 `PSR=5F,E9`；但这是 **PSR 的第二
数据字节**，不是隐藏的 **命令 `E9h`**。后者完全未出现在公开手册，只在 dormant source
中以 `CMD E9h / DATA 01h` 和“已 OTP panel 用 MCU LUT 时绕过 CRC”的注释出现。其必要性、
双控发送顺序和 reset 后状态均未知，所以该位级推导仍不是配对 runtime 初始化。

级联板原理图：
`参考资料/55-00300-04736-N-InkCubic_ E2802_cascade 电子纸E6转接板.pdf`，SHA-256：
`c3f8f563b1222260224f5d76798052237acaec157e5cb78aca488ec12a30abe3`。
exact MF1750 规格另行直接写明 `1024×600 / two SPD1657`，并把 panel pin `4` 定义为
`SL_CSB`、pin `31` 定义为 `CSB`。相邻 adapter 的 J1 对外只给一个 `CS`；J4 两针分别连接
`CS` 和 `SL_CSB`，只有 J4 电气闭合时，该单一路径才会条件性 fan out 到 CSB/SL_CSB。
但 adapter 图纸的 U1 graphical symbol 把 pin 4 画成 `FPL_VCOM`，同一 pin 又经 R10 `0 Ω`
落在名为 `SL_CSB` 的 net；pin 5 才画成 `NC`。这个 `FPL_VCOM ↔ SL_CSB` symbol/net 冲突
不能被静默解释掉，J4 的实物 population/continuity 也未知，且该相邻图纸未证明就是当前 exact
board。因此当前只能判 `CONDITIONAL_FANOUT_PATH_SHOWN / exact as-built NOT_PROVEN`；single
software CS、jumper option 和 panel 双控制器规格三者都不能替代 exact board 的 continuity
evidence 或覆盖 CS/SL_CSB/SCL/SDA/RST/BUSY 的逻辑分析。

## 6. 公开资料交叉验证

- [Touch Taiwan 的 SPD1657/E2802 页面](https://www.touchtaiwan.com/visitorProductDetail.asp?no=180553)
  和 [COMPUTEX Solomon 展品页](https://www.computextaipei.com.tw/en/product/CBA4659B8C39B7F72BDDBEB61C4033B7A51D2AFD55BCA758/info.html)
  只确认 SPD1657/E2802、800×600 与 Spectra 6 身份，不公开 LUT ABI。后者由 Solomon
  Systech 自填，明确 model=`SPD1657`、`800 Source x 600 Gate`、active-matrix Spectra 6，页面
  修改日期为 2026-05-29；这纠正了“公开资料完全没有 SPD1657”的旧表述，但不补 register、
  payload、双控或电气合同。Solomon 当前公开产品目录未列该型号，只能说明目录滞后或不完整。
- 第三方公开的 [SPD1657A Rev 1.0 手册](https://drive.google.com/file/d/1U1hq4dhr821CVItF9kOPBJRxhkNMd6Rb/view)
  （`1869383` bytes，SHA-256
  `29f9c4e2e9cbd6d1aaa4622df4d2ecac8a51a205701a616a96104d03659b89d0`）确认
  P17/P19/P20/P26/P29 确认 `PSR.A[4]=P_mode`、`PSR.B[7]=LUT_EN`、3-bit
  `Gray0..Gray7` 和 `CDI.DDX` 映射。它支持 3-bit 八类结构与 reset 时 OTP/MCU 选择；但命令表
  从 `0x17` 跳到 `0x30`，省略 `0x20/0x21`、隐藏命令 `E9h`、长度和 byte layout，因此
  不能裁决 H1/H2/H3，也不能据此生成 payload。
  P21--22 还公开 `PWR.VGPN/VSPL/VSNL/VSPL2/VSNL2` 的电压公式，P27 公开
  `PLL.FR[2:0]` 的帧率表，使两份 decoded header 可转为上文的请求电压与 `43 Hz`；手册仍
  没有面板/FPL/膜批资格，不能把“编码范围内”误写成“上屏安全”。
- Solomon 官方的 [bistable driver 选型表](https://www.solomon-systech.com/wp-content/themes/solomon-systech/documents/product-catalogs/bistable-display-driver-ic.pdf)
  公开列出 SPD1656 为 `640×480 / 3-bit / cascade / programmable waveform / external flash`，
  但没有 SPD1657 条目；这只能建立相邻架构先验，不能否定未公开/定制 SPD1657。
- 本地 [SPD1656 Rev 1.1 手册](../参考资料/Solomon-SPD1656.pdf)（`2339387` bytes，
  SHA-256 `1f3f5db0600ee6e8133a4c31f9a3f59c1b5bfcc1a916be98ae848ec64581de07`；
  [公开镜像](https://files.waveshare.com/upload/b/bf/SPD1656_1.1.pdf)）进一步固定：
  `0x20=20×11=220 bytes`、`0x21=20×13=260 bytes`，与本地 `535/704` 明确不兼容；
  相同 opcode 不能推导相同载荷格式。其公开表还把 `0x21--0x28` 定义为八份独立 color LUT，
  把 `RP=00` 定义为 no-repeat/end，并明确双芯片 master/slave cascade 与 PSR `LUT_SEL=0`
  取外部 flash、`1` 取 register。后两项只支持“相邻芯片存在双控和回到 flash 的概念路径”，
  不证明 SPD1657 的 CS 顺序或 runtime→OTP recovery。它也说明“所有地址 alias 同一 SRAM”
  和“00 表示重复 256 次”都必须取得同版 wire capture 才能采信。
- 同一 SPD1656 手册的 `0x82` 是量化的 `VCOM_DC` 电压设置（-0.10 到 -4.00 V、50 mV 步进），
  不是名为 brightness/contrast 的命令。结合厂家 STM32 包中 cmd8 只缓存 payload 首 byte、且
  没有完整同版 apply 路径，当前仍不能把厂家所说“蓝牙亮度/对比度”翻译成可安全写入的
  SPD1657 register；必须先取得 App/UART/SPI 同步抓包或厂家协议定义。
- 同厂 [SSD1683 Rev 1.0](https://files.seeedstudio.com/wiki/Other_Display/42-epaper/IC%20Driver%20SSD1683%20Datasheet.PDF)
  （3931534 bytes，SHA-256 `77c188ba55b1b81129f8c0557f845fde25ca97d73ee86ed1ba907ea87a0b5e9c`）
  与 [SSD1683A Rev 1.1](https://support.newhavendisplay.com/hc/en-us/article_attachments/41742409400983)
  （2880342 bytes，SHA-256 `7946b986783b7c4feba2d388290bf6d36ec20d83f43effb538b85b8d4cab7585`）
  都直接定义 3-color 的 `4 LUT×8 groups`，但真实每 LUT/group 是
  `RP + 4×packed(VS|TP) + SR_AB + SR_CD = 7 bytes`，MCU waveform 写入为 `0x32/227 bytes`；
  `0x20/0x21` 分别仍是 Master Activation/Display Update Control。它们既否定“8 groups 自然推出
  8 phases/11 bytes”，也把 8-group 证据推进到 2023，全文仍无 799/704/1503/2508。
- [SSD1681 Rev 1.1](https://support.newhavendisplay.com/hc/en-us/article_attachments/41742572114967)
  （2783721 bytes，SHA-256 `da23b888cdc9b7f7fe1ecd2c2f500add5683b00c4c4116465cc78deb530d07dd`）
  则使用 `12 groups×4 phases`、`0x32/153 bytes`，并把 `RP=0/SR=0` 解释为执行一次；SSD1683
  把同名零值解释为 skip。相邻同族同名字段的零值语义都不稳定，不能迁移到本地 `FF/00`。
- 2024 年同厂彩色 [SSD2677 Rev 1.0](https://files.waveshare.com/wiki/common/SSD2677_1.0.pdf)
  （1066162 bytes，SHA-256 `a2245bbaef593b14fc1ca9c42ea6dfcfb1ef6799a966246b5f23388b0f49ce2a`）
  明确支持 960×680、programmable waveform、6 KB OTP 和双芯 cascade；master/slave 的模拟电源
  与多条电气网连接也被公开。但 command table 不公开 runtime LUT write，且声明未列命令/参数为
  reserved；`LUT_EN` 只控制 reset 时 OTP 自动装载。它证明较新同厂彩色控制器仍可把 waveform
  ABI 留在公开手册之外，不能反推 SPD1657 的 command、CS transaction 或 payload 字段。
- 公开 SPD1656 逆向代码 [`lutv2wave.m`](https://github.com/ts-manuel/Understanding-ACeP-Tecnology/blob/master/matlab/lutv2wave.m)
  和 [`lutc2wave.m`](https://github.com/ts-manuel/Understanding-ACeP-Tecnology/blob/master/matlab/lutc2wave.m)
  同样复现 220/260 体系，只能作反证和概念旁证。
- [E Ink Spectra 6 官方说明](https://tw.eink.com/news/detail/WFBDK3OBM6) 和
  [WO2023034683A1](https://patents.google.com/patent/WO2023034683A1/en) 支持四粒子在同一像素
  形成蓝、绿、橙等混合色；[WO2022094384A1](https://patents.google.com/patent/WO2022094384A1/en)
  支持候选波形、光学测量闭环和 DC-balance 约束。它们都没有 E2802 byte layout，
  专利电压/时长不能直接移植。
- E Ink 2025 年公开申请
  [US20250191547A1](https://patents.google.com/patent/US20250191547A1/en) 给出了一条比空间
  dither 更直接的后续路线：先以少量 prior-state-independent seed waveform 得到基础色，再在
  每个 seed 后附加很短的 perturbation waveform，并对每个组合做真实光学测量。其示例是
  `8` 个 seed、`7` 档电压、约 `127` 帧 seed 和两层各 `3` 帧 perturbation；`8×343²`
  是组合搜索空间，不是已保证互异的颜色数。该专利直接支持“同一像素的波形混色/扰动色”
  路线和分区并行筛选，但这些数字属于其示例，**不是 SPD1657/E2802 的寄存器或 11-byte ABI**，
  不能据此猜写电压、时长或 group 字段。它反而强化了当前证据原则：先恢复可控 seed/profile，
  再用色度计/光谱仪闭环测量单变量 perturbation，不能把粒子层级或组合数直接当成颜色数。
- [US20220262323A1](https://patents.google.com/patent/US20220262323A1/en) 把新波形求解写成
  从初态、目标色和显示响应模型反推 `V(t)` 的受限优化问题；
  [US11620959B2](https://patents.google.com/patent/US11620959B2/en) 则说明四粒子 push-pull
  波形的极性先后、脉冲长度和至少五档电压共同决定颜色。两者可指导取得真实测量后的优化器，
  但同样不提供 SPD1657 byte layout，也不能替代面板/FPL/温度资格。
- [Seengreat 六色示例源码包](https://seengreat.com/upload/file/2024/141/demo_codes_6-color.rar)
  （`24673098` bytes，SHA-256
  `fbd93e11768e5629e15834cba9b4d58dde2744ffe0d62b54f9be1bd11b07566c`）、七个公开
  GDEP073E01/Spectra 6 仓库和 [photoink](https://github.com/protivinsky/photoink) 当前提交
  都只走标准 OTP init/DTM/DRF，没有 `0x20/0x21` runtime-LUT source 或 SPI capture。
- [Good Display GDEP073E01 官方 STM32 包](https://www.good-display.com/companyfile/1436.html)
  及 [2026 官方 ESP32 局刷包](https://www.good-display.com/companyfile/2037.html)（直链 ZIP
  SHA-256 `2d34af51ac6d8392f80f55894d3d7c3b8b93ba78dafeba6cbdf542e3f210c95a`）
  在硬复位后按 `CMDH 0xAA→PWRR→PSR=5F,69` 初始化；这直接不支持“PSR 必须是 reset 后
  第一条命令且无例外”的普遍表述。局刷走 `0x83` 窗口、`0x10` DTM、PON/DRF/POF，
  公开源码中没有 `E9`、作为命令的 `0x20/0x21`、799/704、双 CS 或 runtime loader。
  [GDEP073E01 产品页](https://www.good-display.com/product/533.html) 本身还是 800×480、IC=`NC`，
  所以不能移植为当前 1024×600 双 SPD1657 ABI。官方
  [GDEP133C02 ESP32 包](https://www.good-display.com/companyfile/2046.html)（ZIP SHA-256
  `a683485a58c6159f7788ab4339c91d902bce8f21089203a9d877a5669afb1f96`）提供双 CS 并广播
  普通初始化，但产品未把 IC 标成 SPD1657，源码也无 `E9/799/704/ROTP` 指纹；所以只能证明
  相邻 Spectra 6 的多 CS 常规写法，不能证明当前双 E2802 runtime upload。
- Good Display 2026-06-04 官方
  [ESP32E6-E01 Wi-Fi/USB/SD 固件](https://www.good-display.com/companyfile/2071.html)
  又完成了三份 ESP32-S3 app 的 cross-image instruction-level 静态审计。Wi-Fi app 直接证明六色 palette
  与 Floyd/Atkinson/Stucki/JJN host dither；`adjustContrast` 只在浏览器 JavaScript 定义处
  出现一次且未发现调用，`brightness` 缺失，不能解释为 panel register。新增的 typed
  command/data xref 从三个 app 都恢复出相同 E6 OTP init；WiFi/USB 的 384000-byte tag
  映射/4-bit nibble pack 和 WiFi/SD 的 192000-byte packed display 也已闭合。SD-card SPI
  GPIO `21/13/47/48` 与 SD 面板 GPIO12/11 MSB-first bitbang 是两条不同路径；WiFi/USB
  面板 writer 只保守称 `SPIClass::transfer(uint8_t)` source-shape match。

  这纠正了“未恢复 panel SPI/packing”的旧边界，但不改变 runtime 结论：恢复出的 typed
  init/display command 集合没有 `0x20/0x21`，没有 704/2508-byte runtime-LUT 或双控；raw
  `20 21`、704、2508 命中仍只是 untyped coincidence，LE32 799 为 0。详见
  `docs/GOOD_DISPLAY_ESP32E6_OFFICIAL_FIRMWARE_STATIC_AUDIT_2026-08-12.md`；它也没有恢复
  panel brightness/contrast register 合同。
- Seeed 官方文件服务器上的 E Ink
  [ED2208-GCA / EL073TF1 tentative specification v0.1](https://files.seeedstudio.com/wiki/Other_Display/7.3-E6-color/7.3_E6_eInk_%20Display_%20module_%20Datasheet.pdf)
  明确写出 framebuffer、lookup-table memory、waveform 存于 on-chip OTP，以及由 I2C master
  读取外部温度传感器。其公开应用命令表只有 `0x02/0x04/0x07/0x10/0x12`，没有
  `0x20/0x21`，serial mode 还标为 write-only；这证明公开用户合同未给 runtime-LUT ABI，不能
  据二级资料的 read-ID 或 alias 主张放行。但该表不是芯片全集：Good Display/Seeed 官方源码
  又实际使用 `0x83/0xAA/BTST/PLL/TCON` 等表外命令，且 tentative 表的 `0x12,01` 与两家代码
  的 `0x12,00` 冲突。因此“表中没有 0x20/0x21”只能称 **未公开**，不能证明硬件不存在。
  规格还限定其电气/光学指标只在 E Ink 提供的 controller + waveform 下保证；列出的
  `VGH/VGL≈±20 V`、`VSH/VSL≈±15 V` 是工作特性，不是可试扫授权。
- E Ink 下载站托管的
  [EPM-100 USB Programming Guide](https://shopkits.eink.com/en/download/0223020711rk338873/Content%20transfer%20programming%20guide.pdf)
  明确给出相邻外置 TCON 的完整 runtime 路径：WBF 先进入 buffer，再由命令解析并更新当前
  waveform；更新为 volatile，完成状态由 HRDY/status 报告，温度映射与电压参数又是独立合同。
  这证明运行时换波形在工程上真实存在，同时也说明仅找到 opaque sender 不足以证明 parser、
  commit、温区和电气字段。EPM-100 的命令号、WBF 格式和电压值均不得移植到 SPD1657。
- E Ink 的
  [ED2208-DOA 用户手册](https://shopkits.eink.com/en/download/0224112222me459948/User%20Manual_4%27%27%20Spectra%206%20ePaper%20Display%20%28ED2208-DOA%29.pdf)
  证明 exact 400×600 Spectra 6 kit 可由 Flash Burner 写入 `Initial Data (.eink)` 并重启生效；
  但手册没有公开 `.eink` 容器、命令、record、电气或恢复语义。M5Stack 官方
  [PaperColor 文档](https://docs.m5stack.com/en/core/PaperColor)确认同一 ED2208-DOA/EL040EF1
  面板的量产 one-CS 六色刷新路径，却同样没有 runtime-LUT API；因此它不能证明本机双控制器
  `800/799/704` 装载合同。
- E Ink 官方 [Ripple 公告](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)
  直接确认 Spectra 通过新波形加强同一像素内的粒子混合，Spectra 6 配合 3-bit 处理可到八原色，
  后续 T2000 还增加青/浅绿/橙；这证明“非 dither 真混色”是现实产品路线，但公告没有点名
  SPD1657、命令、LUT、电压或 payload 格式。
- E Ink 2025 年另一申请
  [US20250201206A1](https://patents.google.com/patent/US20250201206A1/en) 给出白态起步的短三段
  四粒子混色 waveform，目标响应可低于 300/250 ms。它与前述 seed+perturbation 专利共同
  支持后续“基础 seed + 短扰动 + 光学闭环”路线；其中电压、帧数和时长均为专利示例，不是
  SPD1657/ED2208 可复制参数，也没有 `0x20/0x21/799/704/2508` ABI。
- Good Display 官方 [BLE 工具说明](https://www.good-display.com/news/208.html) 链接的
  [Web Bluetooth 实现](https://e-paper-display.com/ble.html) 把 brightness 定义为 RGB 乘法、
  contrast 定义为围绕 128 的通道缩放、saturation 定义为相对 RGB 均值缩放，然后才做六色
  最近色与 Floyd–Steinberg；BLE 只发送处理后的像素，没有面板 brightness/contrast/LUT
  命令。公开页面当前甚至没有暴露这些 slider，调用保持默认 1。因此厂家“蓝牙可调亮度/
  对比度”最强公开解释是 host 图像预处理，不是 STM32 或显示控制器物理寄存器。
- Good Display 2025/2026 GDEP073E01 官方局刷源码固定 `0x83 + 9-byte rectangle`，再以
  `0x10` 发送窗口内 4-bpp 数据并执行 PON/DRF/POF。它可支持未来把 OTP seed/dither 的观察
  限定在牺牲区，但没有 runtime LUT；若 LUT 是全局状态，也不能据此在同一次 refresh 中给
  多个分区并行加载不同 LUT。
- 同一官方 GDEP073E01 代码只定义 code `0/1/2/3/5/6=黑/白/黄/红/蓝/绿`，把 `7` 命名为
  `clean`，完全未定义 code 4。因此历史三条“蓝”位置中只有 code 5 是正式蓝；code 4/7 必须
  继续标为 `undocumented-4/clean-7` 候选状态，不能当成两个已确认新基色。
- 固定提交的 [GxEPD2 GDEP073E01 源码](https://github.com/ZinggJM/GxEPD2/blob/de82887e77a78528ea386e68bba2cb0291d2c319/src/epd7c/GxEPD2_730c_GDEP073E01.cpp)
  从 v1.6.0 起有意把 native code 4 标作 orange；但 v1.5.9 的映射曾错误，且 Good Display
  当前产品页、规格、Image2LCD V1.1、2024 源码和 2026 binary 全部仍只交付六码并绕开
  code 4。该库还把 controller 标成 unknown，只有 one-CS API，且无 `0x20/0x21/E9` 或
  799/704/2508-byte runtime ABI。因此 `4=orange` 只是 exact adjacent-panel 的第三方冲突
  假设，不得覆盖 MF 真屏观察、命名 mode-1 category 或生成 payload。
- Good Display 托管的 [JD79661AA V1.0.4 PDF](https://v4.cecdn.yun300.cn/100001_1909185148/JD79661AA%20V1.0.4_20230720%20spec.pdf)
  公开 `PSR.LUT_EN=1` 选择 register LUT、0 选择 MTP；p.64 的 Example 1/2 两个 timing
  diagram 都标出同一个 `LUT0 (20h)`。但 30 项正式 SPI register table 没有
  `0x20/0x21/E9`，图示也不给 `0x20`
  parameter length/payload format，`0x21` 只出现在 voltage-code table，`E9` 全文没有出现。
  PDF 内部 title 还保留旧 `EK79029DS`，虽 Good Display URL/正文均为 JD79661AA；p.62 的
  5600-byte compressed-LUT MTP 区也不能推出 register-LUT payload。它说明相邻
  控制器确有未展开的 register-LUT 概念，却不能恢复 `799/704` ABI，更不能移植到 SPD1657。
- SPD1657A 手册还把 `0x90/0x91` 定义为 OTP 编程路径。任何经验测试都必须静态拒绝这两个
  opcode；`0x92` 的 OTP/SRAM 读取实验也不属于首轮 runtime-LUT 动作。
- SPD1657A Rev 1.0 手册把 Chip Revision Register 定义为 `0x70`，公开命令表无 `0xCD`；
  因此第三方以“`0xCD→0x04`”识别 SPD1657A 的说法没有同版手册支持。
- [Hackaday SPD1657A 实验日志](https://hackaday.io/project/205770/logs?sort=oldest) 声称
  `0x21--0x28` alias 同一 SRAM、无效/空 SRAM LUT 会静默回退隐藏八码 palette、相同 waveform
  配合不同 DTM code 可调强度，并得到 7--8 个基础色。它只能列为低等级、未验证线索：项目
  `Files=0`，正文称 repository link 尚待发布，作者公开
  [GitHub](https://github.com/roob123) 为 0 repositories；所引
  `PHASE7_PART3_LOG.md`、recipe、reference 文件、固件、抓包、原始照片均不可得。作者在
  [2026-05-03 的公开讨论](https://hackaday.io/project/179058-understanding-acep-tecnology)
  又曾明确称 LUT 上传没有实际写入，温补得到的 100+ 色不稳定且方法有缺陷；5 月 24 日结论
  的反转没有可审计中间证据。它不能放行或否定 H1/H2/H3。
- 上述 silent-fallback 主张暴露出首轮 H3 的关键归因混杂：当前 action 同时改变 PSR、
  PWR/PLL、TRES 和 `E9`。即使 atlas 出现八码或亮度层，也不能单凭画面证明 R20/R21 被采用。
  后续最强阴性对照必须保持相同 factory init、PSR/PWR/PLL/TRES、逐 CS `E9=01`、BUSY gate、
  CS 顺序、DTM、PON/DRF/POF 与收尾，只删除 CS1/CS2 各自完整的
  `R20+799 data`、`R21+704 data` 四个 typed event span；不能把 factory-OTP atlas 当成该
  control，也不能用 raw BIN 扫描代替 command/data/CS trace 比较。若 H3 与 control 相同，
  只能判 `NO_DETECTABLE_INCREMENTAL_EFFECT`，仍兼容 hidden fallback、ignored write、
  accepted-but-same、stale SRAM 或测量不敏感；若不同，也只证明组合 R20/R21 command stream
  有增量可见效应，不证明 799/704 ABI 被正确解析，更不能区分 R20 与 R21。该对照是独立
  action，不自动串联到当前 matched V10/runtime V7 路线。
- IAR 官方 [UBROF Record Types](https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/UBROFRecordTags.pdf)
  （`50874` bytes，SHA-256
  `8bbe9bddec98f52d0d75224d68a25fa784215a86634d1c1ba3dbd6d2fc15b801`）只列语义记录名，
  不公开 binary tag、字段布局、长度编码、external ID 或目标 relocation 语义，不能据此实现
  通用 UBROF10/11 parser。官方
  [XLINK/XLIB Reference Guide](https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/xlink.ENU.pdf)
  （`1128938` bytes，SHA-256
  `e8df5be0f3af7910d1055224bbc62b1102286c5c4d9779f996cc7c7a34946cd2`）给出
  `LIST-ALL-SYMBOLS/ENTRIES/EXTERNALS/MODULES/SEGMENTS/OBJECT-CODE`。现已从 TI 官方包静态取得
  6.1.3.56 并完成 26 个 UBROF10 的 EXTERNAL/ENTRY 复核；原二进制只在临时目录，仓库仅保留
  exact identity、命令合同与 metadata-only 结果，不复制 IAR 可执行文件或 raw object dump。
- IAR 7.21.1 官方
  [XLINK version history](https://netstorage.iar.com/FileStore/STANDARD/001/000/603/ew/doc/infocenter/xlink.ENU.html)
  给出的 XLINK 版本是 6.6.2.104，并明确记录 EW25659：含 stack-usage 信息的 UBROF 会使
  较旧 XLIB 报 `Unknown tag: E2`，6.3.4.78 修复。它说明当前三份 UBROF11 的失败边界，仍不是
  binary layout 规范。当前 [IAR MSP430 14 天试用](https://www.iar.com/embedded-development-tools/free-trials)
  是合法的注册/许可路线，但未找到无需注册授权、可自由再分发的 standalone XLIB>=6.3.4.78；
  不绕过 SUA 或使用泄漏包。官方
  [MSP430 assembler release notes](https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/infocenter/a430.ENU.html)
  显示 `CALL_GRAPH_ROOT`、`CFI FUNCALL/TAILCALL/INDIRECTCALL/NOCALLS` 到 6.30.1 才加入，
  因而不能假定 IAR 5.30 生成的 E2802 UBROF10 含这些记录。官方
  [UBROF→ELF migration guide](https://updates.iar.com/filestore/standard/001/001/960/ew/doc/EW_MigrationFromUBROF.pdf)
  （`336469` bytes，SHA-256
  `5cc1d37201695f5f67a4c7622918c1d4e381b45553d5263b85df718e297e7fb5`）也只证明 UBROF
  是 IAR 私有 legacy 格式，不能补出 record encoding。
- TI 官方 [MSP430 GCC 6.1.0.0 下载页](https://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/6_1_0_0/index_FDS.html)
  提供本次使用的 `msp430-gcc-7.3.2.154_win64.7z`；归档 `19602448` bytes、SHA-256
  `b49c53f716069b6ce6bc1c7cd913dc5d938fc9081c57519b139091126eeb6ef0`，其中
  `msp430-elf-objdump.exe` `993964` bytes、SHA-256
  `9ff1039e992f653dd9e26d4322e33a4d820234d8d6d674674082e4592e80cacb`。它只解码由
  identity-pinned XLINK 临时生成的 Intel HEX，不解析 UBROF，也不证明 dummy external 的实现。
- 开源替代也没有补齐格式：mspgcc historical `ubrof.c`（commit
  `7c4e8e30c4a53cbfc10a97ecfd09f2f934a3c0c7`，文件 SHA-256
  `ff076c25bd7b05e6456101c0f9d2bdd2a9aad3244679e3851f522091495dd369`）仅为作者明确标作
  experimental 的 UBROF5 decoder；[Bound-T 下载包](https://bound-t.com/download/) 的公开版
  只有 `Supported=False` dummy package，真实 UBROF reader 受 IAR NDA 限制。故本项目工具只称
  “identity-pinned local evidence audit”，不声称通用解析器或完整符号链接图。

对 `WF_DeCode_SIZE 544`、`E5_3Bit_Mode`、`WF20_25.h`、`WF23_25.h`、
`LUT1_DATA 704`、`eload_3bits`、`800+2+40/74` 等精确指纹的公开索引检索没有相关命中。这只能表述为
“未在已索引公开资料发现”，不能证明互联网或厂家内部不存在。

## 7. 真屏 GO 条件与最小动作

### 7.1 必须取得的直接证据

满足以下二选一：

1. 配对的 `E5_3Bit_Mode=1` loader/source/binary，并形式化证明 decode=`800`、
   `WF_SIZE` 及 `0x20/0x21` 的精确长度/数据源（特别是 H3=`799+704*FF` 是否成立）、
   `0x01/0x30` header；或
2. 厂家已知正确系统加载同一 wrapper 的完整逻辑分析 capture，覆盖两个 CS、DC、MOSI、
   四条命令、完整长度与 payload hash。

同时还必须闭合：

- 两个 E2802 在 refresh 前均收到相同 K0 profile，且顺序/失败语义明确；
- MCU-LUT 所需 PSR/`0xE9`/初始化模式明确；
- 候选与当前面板料号、膜批和温区匹配；
- MCU-LUT → factory OTP 的确定恢复序列、状态确认和白恢复；
- profile、电气/温度限制、review 与一次性授权均进入现有 fail-closed gate。

没有厂家或公开一手资料定义 `WF20_25`、`WF23_25`、`WF00_05`、`WF24_24`、`WF25_25`
中数字的语义；loader/project selector 也不解析这些文件名。故 `20/25`、`23/25` 现在只记录为
**opaque vendor filename numeric tokens**，不能再写成 `20–25°C` 或 `23–25°C` 温区。相邻
2020 E2801/E2802 只证明各自 slot selector 固定为整数 `25`；当前 host 因此把首轮条件收紧为
exact `25.0°C` 的实验护栏，同时明确 `vendor_temperature_band_claim=false`、
`temperature_compatibility_qualified=false`。这个护栏不是厂家资格、面板/FPL/膜批匹配证明，
也不允许复用任何历史温度。当前仍无证据决定谁是 K0；禁止仅凭文件名、日期、发现顺序或
“较新”标签选 profile，两套 profile 必须是独立 action，绝不在一次刷新中自动切换。

### 7.2 第一个真屏动作

当前唯一顺序已改为 C-first，旧“先 K0、再生成 C1”路线 **superseded**：

1. J2 OFF 下重验 matched-control 与 pinned treatment releases，再刷 C 固件并生成 fresh
   `4 GET/0 POST` diagnostic；
2. J2 ON 实时确认牺牲屏、3.3 V、限流、电流、温度和物理切断，逐字授权后只执行一次
   no-R20/R21 atlas；
3. J2 OFF，另刷并独立授权 factory-OTP 白恢复；确认全屏干净白、电气正常后再断开和平衡；
4. 离线 finalize C-leg 并生成 non-authorizing treatment gate；T 必须精确匹配 C 的 0.1°C；
5. J2 OFF 刷 pinned K0 treatment，fresh diagnostic 后从 C-first facade 进入，J2 ON 实时复核并
   只执行一次 H3 atlas；
6. J2 OFF，另刷并独立授权 T-white；确认干净全白后最终 J2 OFF，再离线 finalize pair。

四项均不 retry、不 autochain、不自动换 profile。首轮不扫多个 waveform；C/T 只比较组合
R20/R21 command stream 是否产生增量可见效应，不能把差异直接提升为 799/704 ABI 接受证明。

### 7.3 用户明确接受时的牺牲屏经验合同

若无法取得 7.1 的配对 loader/capture，而用户明确选择以牺牲屏推进，则首轮只允许冻结以下
**一套**经验拼接，不允许现场改参数：

1. 从已验证的双控 factory init 起步，保持 3-bit/分辨率位，仅把 PSR 的 `LUT_EN` 从
   `5F,69` 位级改为 `5F,E9`；随后重新发送每控制器 `TRES=512×600`；
2. decoded PWR/PLL 等全局配置使用同面板的 `ToBoth` 骨架；隐藏 `E9=01`、
   `0x20/plain[0:799]`、`0x21/704×FF` 则固定按 `CS1→CS2` 分别发送同一 profile。该顺序只
   提供发送端分段/hash 归因，不声称单根 BUSY 能证明从控接收；
3. runtime 固件只包含一个固定 profile、一个固定八码矩形 atlas 和一个 action，不接受 raw
   frame/LUT、电压、时序、profile 或 SPI 参数，不自动选择 WF20/WF23；
4. 首轮 profile 必须由用户在授权中点名；文件名数字不得解释为温区。当前只允许在 fresh
   observation 精确为 `25.0°C` 时通过实验护栏，而且这不构成温度资格；两份候选不得在一次
   上电或一次授权中连播；
5. 只刷新一次；无 retry、fallback、auto-chain、第二 profile 或隐式 recovery。任一 BUSY、
   电流、温度、供电或 ESP32 状态异常立即物理切断；
6. 白恢复使用**另一份不含 runtime payload 的独立固件、独立 NVS 和新的授权**。无论 runtime
   report 是 PASS 还是 fault，都先物理切断 J2，再在 J2-OFF 下刷 recovery；重新接通后只执行
   硬复位、已真屏验证的 `PSR=5F,69` factory init 和固定全白刷新，最后断开 J2；
7. 编译期和 ELF 审计必须反查真实 profile/799/704/frame/双 DTM identity，并从 command
   emitter/固定 transaction descriptor 证明命令路径不允许 `0x90/0x91`。不能对整个 BIN 做
   原始 byte absence 判断，因为 LUT 数据本身可以包含任意 byte。

exact one-shot 授权必须逐项接受以下七个未证假设；缺一项即保持 `LIVE NO-GO`：

- **U1**：`5F,69→5F,E9` 只是保持其余 factory 位的手册级推导；双控 mode-1 值与插入点
  没有 capture；
- **U2**：把 mode-0 的 `header→PWR/PLL` 绑定用于 800-byte mode-1，并在 factory init 后
  覆写 PWR/PLL，其相对顺序没有配对证明；
- **U3**：`E9=01` 是公开手册缺失的隐藏命令，来自另一条 2-bit MCU 路径；它对 H3、双控及
  BUSY 的语义没有直接证明；
- **U4**：H3=`0x20/799+0x21/704×FF` 只由 2020 IAR/E2801/E2802 直接证明，对 2025/2026
  SPD1657 属跨版本推断；
- **U5**：固定 `CS1→CS2`、无 LUT readback，发送端 hash 不等于两颗芯片已接受；单根 BUSY
  也不能证明 slave 状态；
- **U6**：文件名数字的温度语义、profile 与当前 panel/FPL/膜批的温度匹配均未证明；必须
  fresh 实测并只在 exact `25.0°C` 实验护栏下推进。`plain[5]` 会随 opaque R20 发出，但不得
  把它另行解释、应用或扫描为 VCOM 参数；
- **U7**：post-POF cleanup 与 runtime→factory-OTP recovery 都是从已验证 factory 路径外推，
  不是 runtime capture 闭环。

## 8. 可复现工具与当前验证

- 公开一手 ABI 检索冻结报告：`docs/SPD1657_PRIMARY_SOURCE_ABI_HUNT_2026-08-12.md`，
  当前 SHA-256 `8a1b56b0097c00861eb5cd14eebec6228b0ace042c58d2e3c3ac2cfb3977efa3`；它把
  SPD1657/A/B、E2802、ED2208 与相邻 SPD1656/SSD168x/SSD2677/Good Display 的正负证据分开，并明确
  `WFxx_yy` 命名语义未知、exact `25.0°C` 仅为本项目实验护栏；
- Solomon 相邻家族 metadata-only 审计：
  `tools/mf1750_solomon_adjacent_family_audit.py`（SHA-256
  `fc46ef3c7a3071ad10092d5126e68b856db370f4e66ef912f6692f1187d20602`）；对四份本地
  SSD1681/SSD1683/SSD1683A/SSD2677 PDF 固定 whole-file identity、page count、16 页 normalized
  text hash 与 required anchors，不输出全文。报告
  `.test-output/offline/mf1750_solomon_adjacent_family_audit_20260813.json`（13631 bytes），
  file/canonical SHA-256=`94e46efb414a2ca8358e659b4458e6c308b4f5a8111caeed8b0f7779b05a9999` /
  `c090d25412b609524495217e41a7ffaf7e911314b932486bce40cb614e8da8f2`；它直接固化
  8-group/7-byte 延伸到 2023、SSD1681↔SSD1683 同名 RP/SR zero 语义冲突，以及 SSD2677
  “公开 programmable waveform/cascade、未公开 runtime write ABI”的边界，不能移植字段或电气值；
- Good Display 官方 2026 ESP32E6 固件静态审计：
  `tools/good_display_esp32e6_firmware_audit.py`、
  `docs/GOOD_DISPLAY_ESP32E6_OFFICIAL_FIRMWARE_STATIC_AUDIT_2026-08-12.md`；固定官网 ZIP、
  三份完整 flash/app/partition/segment identity、host dither strings、SD SPI 的有界 Xtensa
  xref 与 untyped constant counts。JSON
  `.test-output/offline/good_display_esp32e6_firmware_audit_20260812.json`，72095 bytes，
  file/canonical SHA-256=`47320086015dd6c6ceb37c9a1ad92759bf1b4ea8f26791b28ebb8d0ffb327213` /
  `cb54e65648731ed1c02221747dc559be58dc898f5f4efd126c94b53371851a09`；
- Good Display cross-image 面板路径审计：
  `tools/good_display_esp32e6_cross_image_panel_audit.py`；固定三份 derived ELF 与原 app
  segment byte identity、Xtensa function/raw/normalized hashes、typed command/data helpers、
  E6 init、tag→4-bit packing、packed display caller 和 SD-card/panel 两套 transport 边界。
  报告 `.test-output/offline/good_display_esp32e6_cross_image_panel_audit_20260812.json`，
  27378 bytes，file/canonical SHA-256=`3f82c21dca0d59f4c35bd8a390dbea26497dd29b3fb6e502a2ba2c95f1bd7f4b` /
  `8f6f9399a80e6f9fd02ef351437aa368a53e8b058d48f7d9b586c789016e5854`；
- Good Display 2024 source↔2026 binary 六色合同审计：
  `tools/good_display_gdep073e01_source_binary_contract_audit.py`；固定厂商 ZIP、六个成员、
  header/Color_get/PIC_display/六码纯色/image tag histogram 与 cross-image JSON，证明两代官方
  路径 native code set 都是 `[0,1,2,3,5,6]`，并区分 converter input tag 与 native code。
  报告 file/canonical SHA-256=`03d8d3406cf4b428dd07280d619bfd3928c8ecf6bc8c5da19e732e474c178415` /
  `fdab7df75d064ea3a584d2cfa4e124dfd39c7979221e88b74d4a96401cfb5446`；
- 主审计工具：`tools/mf1750_spd1657_reverse_delta.py`，schema `4`；
- AES wrapper/alignment 边界审计：`tools/mf1750_spd1657_wrapper_alignment_audit.py`
  （12245 bytes，SHA-256
  `33cc7e2acd75d2270cac6a102ebce79ef5640ab1d47175d280d8665674518d06`）；报告
  `.test-output/offline/mf1750_spd1657_wrapper_alignment_audit_20260812.json`（5874 bytes），
  file/canonical SHA-256=`0795b79ee6c29a1d987c233c311a124e81c72bbd04e2f17b3d4d15b6eb643534` /
  `69832c37a0cb043078401955bc834dbca60de9c3550bb2b7a7bd8047e36ca7c8`；它只证明两组最小
  AES block roundup，并把 outer-byte role 和同版 mode-1 loader 保持为 unresolved；
- ArmCC DWARF line-program 审计：`tools/mf1750_armcc_dwarf_line_audit.py`
  （20121 bytes，SHA-256
  `aa15d6fbeb31dcf394578d1e50570e76854286f0e876379ed60d93aa968c0192`）；报告
  `.test-output/offline/mf1750_armcc_dwarf_line_audit_20260812.json`（36586 bytes），
  file/canonical SHA-256=`1963084f1b69ab584093739b393c6c8849e67bc54892d5d5418154f39aead926` /
  `33de97f33fb0484ebbe9ced7298a4dd5e6829008001e342bde9d5b776b643574`；
- final D43 GPIO/transport/panel-topology 审计：
  `tools/mf1750_iar_final_gpio_topology_audit.py`（39284 bytes，SHA-256
  `3948518f214b123fcfe7602c9d3622fc2c77c2262d40b3938d7f5ef4ba99c6ff`）；报告
  `.test-output/offline/mf1750_iar_final_gpio_topology_audit_20260812.json`（23686 bytes），
  file/canonical SHA-256=`f371fa3f52364ce7b696ce265c2441dd05d847ffd8e17bc30bbc009bdf2fc859` /
  `94c4fbaed8617cf137af674e472088fc06bfcf2e834778b9dbb5be0993bc8a4c`；
- 535/704/799 record/source-semantics 审计：
  `tools/mf1750_spd1657_record_semantics_audit.py`（68129 bytes，SHA-256
  `4a99f09255cbd5894aca2f94074ee3dcba34ac8f38d3c82bbe8a05546bdd9136`）；schema-3 报告
  `.test-output/offline/mf1750_spd1657_record_semantics_audit_v3_20260812.json`（48760 bytes），
  file/canonical SHA-256=`e2dd4ea1b8866873fd82781a43cc1c37fe3e1e8c3807b6390272ba682e53c4eb` /
  `12954f599d9c76a8c0d87dbe3270e1b39e206aceb64dce740333fb3647350316`；它不输出 raw record，
  并把 GBK 芯片规格注释与同一 `EPD_initial` 内紧邻的
  `0x20 -> i=0..534 -> wf_data[i]` 三元组绑定纳入回归，并显式保留 linked UART
  replacement 导致 initializer-at-runtime 未证；它不把该注释、source `GROUP`、
  相邻专利或统计规律提升为 mode-1 长度或 phase/electrical field；
- UBROF11 E2 observed-dialect/differential 审计：
  `tools/mf1750_iar_ubrof11_e2_grammar_audit.py`（49407 bytes，SHA-256
  `cff3ad7661efd6338d4b64980ac2d91766c48197c737e0fdfa1a8abb10fce548`）；报告
  `.test-output/offline/mf1750_iar_ubrof11_e2_grammar_audit_20260812.json`（178104 bytes），
  file/canonical SHA-256=`c5184dc13eef1666415aca5b58c3cdb23ad3ab519b00c2ba7093f25a323c7862` /
  `d265097c3215da0cad256b185e9f061534d702b3c298e32b2cfc451850aac565`；32/32 projection
  differential 不冒充官方 grammar、原件 native parse、link 或 flash input；
- ArmCC retained-object 全 CFG/解密状态证明器：
  `tools/mf1750_armcc_loadwf_deep_audit.py`；固定 23 个函数、真实 executable/comment 边界、
  `loadWF` CFG、helper flags、四次写入与严格 negative findings，且不输出 raw key/plaintext；
- ArmCC mode-1 residual 审计：`tools/mf1750_armcc_mode1_residual_audit.py`；固定两棵厂家树、
  STM32 byte-exact ZIP/IAR 加密 7z 边界、Keil DEP/LNP/SCT/MAP/AXF、唯一 ar/member/public
  symbol、uvguix 外部路径和 SPI-analyzer Packet ID 语义。报告
  `.test-output/offline/mf1750_armcc_mode1_residual_audit_20260812.json`，18468 bytes，
  file/canonical SHA-256=`2e19e2299d95674643bf357b6647fdd8cded226bb20f9b7e7288b7b641862171` /
  `2cac3b635b9a20baa1bada3dd9f7ce8db9cce1e3109dff31d25591d4dcc3aa9f`；
- ArmCC retained executable/command-sink 全量审计：
  `tools/mf1750_armcc_exec_sink_inventory_audit.py`；固定 34 个 retained `.o` 与 7 个 final AXF，
  对 MOVW size constants、BL command sinks 与 symbol/function ranges 做 instruction-level 归因。
  唯一 object-level immediate R20 是 `edp_init.o::EPD_initial → EPD_WriteCMD` 并同函数含
  535；六份 AXF 保留该旧单-CS路径。立即数 R21 command sink 为 0；raw 704/799/800
  coincidences 均落在 UART/NVIC/shift helpers，未与 loader/payload 绑定；双控 helper 与 R20
  path 不相交。报告
  `.test-output/offline/mf1750_armcc_exec_sink_inventory_audit_20260812.json` 的 file/canonical
  SHA-256=`0f1befae7fd64a729e79e970f46bc085813057282034fc8cabb662b656593412` /
  `07e7a78fa01489e4eec0ae231a832cc74ad2b26cc6a9ddf4a8dc326e1d2a4e50`；
- STM32 caller/loader ABI 边界审计器：
  `tools/mf1750_stm32_loadwf_abi_boundary_audit.py`；同时固定 sample main、ArmCC member 与旧
  UART helper 的 length/dataflow，区分 COUNTER checksum、pointer-only 调用、固定 544/535
  访问和未知真实 buffer capacity。metadata-only 报告为
  `.test-output/offline/mf1750_stm32_loadwf_abi_boundary_audit_20260812.json`，12952 bytes，
  file/canonical SHA-256=`e9b37aaaff6bcf322d6ab2fcff5ef3ca192fa11734a5afa6ba00d269dabad32e` /
  `dfd2678a9f28706a653ee7610559beb1f66cd173693640f2ffbfd4f100ca6368`；
- IAR UBROF 独立证明器：`tools/e2802_r43_lut_proof.py` 与
  `tools/e2801_r43_lut_proof.py`；后者独立固定 E2801 的 TSC-read、PSR-in-upload、799/704、
  相同 DATA0/DATA1 hashes 与 7 个 display callers，但不能把 TSC-read 误写成动态 selector；
- IAR DATA0/DATA1 兼容性/可达性审计：
  `tools/mf1750_iar_data0_data1_compatibility_audit.py`；以官方 XLINK 固定 part20/21 extent、
  两对象逐字节一致性、`first799+FF704` 精确切分、全部其他 PUBLIC root 的 `NOT NEEDED`
  结果和零自然引用；明确不把该切分升级为 declared subobject 或 active upload source。报告
  `.test-output/offline/mf1750_iar_data0_data1_compatibility_audit_20260812.json`，22501 bytes，
  file/canonical SHA-256=`5d9f76f8057af336c9662e9e0f8d4e7f66cea0ef08651bfde67516160418ea5a` /
  `5d28d9d575f8b5da8c21b3fcdfbc08c1520c62b61852b214607c25a90bccf123`；
- IAR XLIB type/local-symbol/relocation inventory：
  `tools/mf1750_iar_xlib_type_symbol_audit.py`；只对 E2801/E2802 临时副本调用 identity-pinned
  官方 XLIB 6.1.3.56 `LIST-OBJECT-CODE`，直接固定 DATA0/DATA1/dataBuff 数组类型、selected
  function signatures、`Upload_Temperature_LUT` locals/source ranges，以及全部 `t_push_rel`
  对 DATA0/DATA1 sections 的零引用。报告不输出 object code 或 waveform bytes；
  `.test-output/offline/mf1750_iar_xlib_type_symbol_audit_20260812.json` 的 file/canonical
  SHA-256=`608f54b06f12d9e393c6a3760b1ff3fc351db6ebd547e99f625754874fc5cd4a` /
  `2e777a28642c683c0c131a025525a531f969b86734048b0dd79e435718c7f4b3`；
- 535/799/800/704/1503 算术、有限变换和 checksum 有界审计：
  `tools/mf1750_spd1657_arithmetic_transform_audit.py`；schema 2 明确披露既有 wrapper 只在内存
  解密，不输出或落盘 raw key/plaintext/waveform，也不生成可刷载荷；固定精确长度等式、
  DATA0/DATA1 无 active-record/FF-mask bridge、所测有限变换和简单 checksum 家族均未命中，
  同时保留 CRC/MAC/其他编码及全部字段语义为 unknown。报告 file/canonical SHA-256=
  `73003d115b2386d601826eaa4f704f3e2a3b45075030f75696906ff8a7dc8a4a` /
  `b77e5edbc169257cc56cb3af25085a358b7a43aa433432117cce29ae40a8015c`；
- IAR LUT helper ABI/dataflow 审计：`tools/mf1750_iar_load_lut_const_abi_audit.py`（schema 2，
  SHA-256 `f14059ca4511a1547c6144630cf52ce1ffba56b3f03446e350c90bada465eac5`）；以四个
  root-only synthetic links 和全对象 consumer scan 固定 `R12/R13/R14` 三参数 ABI、const/mutable
  机器体相同、DATA0/DATA1 不绑定及 const 零已观察消费者；又固定 complete 14-instruction sender、
  SPI_DATA 完整 machine-body hash、8-bit `D7→D0` 序列化和无发送侧 complement/record terminator。
  schema-2 报告 25392 bytes，file/canonical SHA-256=
  `46046593a43e453e1d7845f91f1e4cae895ab00125483d1f362efcfa5380e0e5` /
  `01241e9f6ac31f20d06f99ee2e61431a4e2124509772545fd3e43fa485479c09`；
- LUT callsite/controller-destination 审计：`tools/mf1750_lut_callsite_destination_audit.py`；
  对 E2801/E2802 分别 root-link、固定完整 helper hash/GPIO anchors，并把 ArmCC project/source/
  7 MAP resolution 与独立 `ToBoth` API 分开。报告只输出 hashes/lengths/bounded facts，不输出
  object code、disassembly 或 waveform。报告 file/canonical SHA-256=
  `bcbf7a3ec557809ab933d633079b25368107741d6fdc3f93e478215639298897` /
  `faedd107ad47723f0afdbe46ae072fc0fd8ae016271e7808b10a743f37196f17`；
- IAR legacy 温度选择器 linked-disassembly 审计：
  `tools/mf1750_iar_temperature_selector_audit.py`；要求显式提供 exact XLINK 与 TI objdump，在
  临时 ASCII 目录用固定 dummy externals 重建两个函数，校验 Intel HEX checksum/无重叠、完整
  address-byte/function/disassembly hash 与目标语义，报告不输出 raw code/disassembly/payload。
  metadata-only 报告为
  `.test-output/offline/mf1750_iar_temperature_selector_audit_20260812.json`，9701 bytes，
  file/canonical SHA-256=`bc291f1ccff644f8d86ca2888730b03096ade9e3afccfc126914e6ce1360f7fd` /
  `b1a30b5699a1b60231593b9c25547076f5d96c32db7f163fb25b7e10b4f1aed7`；
- IAR 29-object identity-pinned 调用站点清单/局部图：
  `tools/mf1750_iar_r43_cross_object_graph.py`；逐文件门控混合 UBROF10/11，只把与 CALLA
  debug-source 成对的 observed `0x5D/0x5E` relocation 纳入站点证据，并明确拒绝把名字字符串或依赖成员
  当成 PUBLIC/EXTERN/可达调用；schema 2 另按 XML 精确区分 output table 与 final-D43
  `inputs/XLINK`，直接项目输入固定为 `DELAY/E6_73/main`；
- 官方 XLIB external-index 交叉审计：
  `tools/mf1750_iar_xlib_external_index_audit.py`；要求显式提供 exact 6.1.3.56 `xlib.exe`，先验证
  size/SHA，再把 29 个已固定身份对象逐份复制到临时 ASCII 路径，只调用只读的
  `LIST-EXTERNALS/LIST-ENTRIES`。26 个 UBROF10 的 349 条 external-index 全部零冲突；三个
  UBROF11 的 52 条明确保持 E2/version-boundary。metadata-only 报告为
  `.test-output/offline/mf1750_iar_xlib_external_index_audit_20260812.json`，file/canonical SHA-256=
  `cf487e8845d33ca255be9fabc977e926cc30d0b054b0546005f09ec876b295e7` /
  `6d17001cb79a9c09e367704f2f3945c120ef81d6e358b5ad4af5a4519d579e31`；
- IAR UBROF11 XLIB 可用性审计：`tools/mf1750_iar_ubrof11_xlib_availability_audit.py`；只扫描
  显式本地根、只执行已固定身份的官方旧 XLIB，并对 IAR/TI 官方 allowlist 只做 HTTPS GET，
  不安装、不提交注册、不猜保护 URL、不运行未知 binary。它把 6.3.4.78 修复下限、匿名下载
  边界和六条未来只读 LIST 命令物化为机器可复核缺件。报告 file/canonical SHA-256=
  `de6cecae3f63558328d1a32ef199e4e96bfaf0c4b0827759b7ef616c87c37ea0` /
  `d8f318b2062e6a37cc6c0bcf8e72c41bdc79e5e54204fe0e17f6600c185f8198`；
- IAR UBROF11 E2 exact-offset projection 审计：
  `tools/mf1750_iar_ubrof11_e2_projection_audit.py`；schema 2 保持原件不变，在临时副本按固定
  allowlist 移除 25 个 inferred E2 spans、重算 CRC，再由官方旧 XLIB 列 projection 的
  EXTERNAL/ENTRY。52/52 paired indices 一致，但 projection 明确不是 native parse、通用 parser
  或 link/flash input；引用的两份官方资料范围内未找到 byte-level E2 grammar，不作全局不存在
  断言。报告 file/canonical SHA-256=
  `7d3ff40fac47295c68f55044935201cdc9867e10f803be4117ac293baf4936bc` /
  `15647b3c522d298ff8e2fa2782835c0d7b97577fdf02bed5b4cec9fed726683c`；
- XLIB provider-candidate graph：`tools/mf1750_iar_xlib_provider_graph.py`；以官方 ENTRY 名称对
  68 个 caller/index groups 做 exact-name join，但所有跨对象结果仍固定
  `provider_object_proven=false`。38 groups/43 sites 只有一个库存候选，6/7 有多个候选，
  24/351 无候选；main→E2801/E2802 display→upload 只能构造候选路径，不是最终 D43 linked
  root chain。报告
  `.test-output/offline/mf1750_iar_xlib_provider_graph_20260812.json`，180610 bytes，
  file/canonical SHA-256=`9f4ab28cc4abb96fcd55b7f3e287014a64eb2d30089cd433fee0046ab0e23221` /
  `de40c90bedf91c0b518923e3e0718e46e28f444b473397db6cb7f7aca43bfa66`；
- 最终 D43 provider/call-chain 审计：
  `tools/mf1750_iar_final_d43_provider_chain_audit.py`；直接用 identity-pinned 官方 XLIB 对 absolute
  D43 执行 `LIST-OBJECT-CODE`，重构 2002 个 addressed bytes 并与 TI-TXT addressed image
  完全相等，验证 188/188 条 CALLA
  机器目标，直接固定 `main→E6_73::EPD_Init/六 display`、E2801/E2802 非 final 及
  `current_final_named_runtime_upload_path=NOT_FOUND`。单个 fixed CSB software endpoint 不被
  解释成物理单控或双控语义，V1.1 object lineage 不被称为 V1.2 rebuild。报告 file/canonical
  SHA-256=`7ed8e7655757710e824f28af4c477dcfc78a997e02e00c6123e315c5a5409886` /
  `51a646c74d76ba3f10e6c56e6a59c232724b2d9f7e0a0040ec18f40f60908976`；
- IAR project/config/generated-chain 审计：`tools/mf1750_iar_project_config_chain_audit.py`；
  同时核对 EWP、DEP、direct inputs、TI-TXT、Release 空链、Source Browser `.xcl` 与 producer
  source lineage，明确把 V1.1 object final 与 V1.2 delivered source 分开。报告
  `.test-output/offline/mf1750_iar_project_config_chain_audit_20260812.json`，24290 bytes，
  file/canonical SHA-256=`b08d5e19f56a989fcbd08eebce5ecdbe1b3900d98915ac76a7a6702f406bebf5` /
  `15576687497416c400b3d880d35674f02badef8becaef4b3782a4f597a5da60a`；
- 最终 AXF/init linkage 证明器：`tools/mf1750_final_axf_init_linkage_audit.py`；
- 厂家工件/归档/provenance 全量盘点器：`tools/mf1750_vendor_artifact_hunt.py`；默认 compact
  报告固定两棵目录、ZIP/7z 边界、loader linkage、backup/editor residue 与 `.r43`
  dependency 分类；schema 2 复用同一 XML 语义，不再把 9 个 output-table 行误称为 linked；
  追加 `--include-file-manifests` 输出全部 `430` 条 path/size/SHA-256；
- 显式 profile 离线固化器：`tools/mf1750_spd1657_vendor_profile_pack.py`；生成
  `src/generated/spd1657_wf20_25_empirical_h3.inc` 与
  `src/generated/spd1657_wf23_25_empirical_h3.inc`，只允许命令行点名单一 profile；
- 11-byte metadata-only 几何审计器：
  `tools/mf1750_spd1657_phase_geometry_audit.py`；只输出统计、hash 与证据等级，不输出
  raw waveform，也不生成 payload；
- 跨 profile opaque invariant 统计器：
  `tools/mf1750_spd1657_waveform_invariant_stats.py`；固定 WF20/WF23/legacy 535/IAR 704/
  ArmCC 704 身份，只输出 byte/record equality、entropy 与边界判定，不输出 raw waveform、
  不给位置赋 phase/electrical 语义。报告
  `.test-output/offline/mf1750_spd1657_waveform_invariant_stats_20260812.json`，295597 bytes，
  file/canonical SHA-256=`84ac8584453949a321719d108c0b0aaf2e54246d31eddc885f5c287fb638c7f1` /
  `eb2c391bcfcd1b5d5b6b0af39b84467353bfc1ce5a48abb2684e34c6df6e8978`；
- category/record alignment 审计：`tools/mf1750_spd1657_category_alignment_audit.py`；固定
  legacy 厂家标签、IAR DATA0/DATA1 与 WF20/WF23 的完整行、11-byte record、FF-mask、offset
  和 Hamming assignment，明确把公共 row0 record 降级为 `10/11 FF` 的低信息 filler-compatible
  线索。报告 file/canonical SHA-256=`f232446b0e014264b0452cd47331e0376487251b4b99ba85fe4fb658ee5b2ed4` /
  `572a86bcbcdccb9aa17e4114b34cfef7b348f2492ee0154e43085db482780445`；
- Philips 11-byte primary-patent 对照器：
  `tools/mf1750_spd1657_patent_11byte_audit.py`；固定专利 PDF/事实合同与三份本地候选身份，
  只输出 selector/timing/terminator 元数据，并明确拒绝把 Apollo 字段语义移植为 SPD1657 ABI；
- 双 CS SPI capture 判定器：`tools/mf1750_spd1657_spi_capture_audit.py`。它要求显式 profile、
  原始逻辑分析文件及与其 SHA-256 绑定的严格 decoded-byte-run JSON，重建 D/C command/data
  边界，并核对完整 `factory init → 双 E0 → runtime config → CS1/CS2 LUT → 双 DTM →
  PON/DRF/POF` 事务。它能无歧义分类 H1/H2/H3，拒绝缺片、混合 profile、乱序、截断、
  额外 opcode、DTM 变异及 `0x90/0x91`，输出仍只有长度/hash。由于它不重新解码原始逻辑边沿，
  最终结论只证明 decoded wire sequence identity，不证明控制器内部接受或单 BUSY 下的从控状态；
- `79661.csv` decoded-row 审计：`tools/mf1750_79661_capture_semantics_audit.py`；逐一扫描全部
  已知载荷的所有连续 MOSI windows，并将 timing-only segmentation、一次性 pinned JD79661
  public-source fragment cross-check 与缺失 CS/D-C/SCLK/controller 的不可观测性分开。报告
  file/canonical SHA-256=`c6ac5803f044608bf01de57f6acdfb20695dbf80fa840357bac948fd5024b97f` /
  `9b4b257996b888512862285d1d02cae5819263077de4e85c3ce97ea25c49f9f8`；
- JD79661AA datasheet/source/capture 对照：`tools/jd79661aa_datasheet_cross_audit.py`；固定
  78-page PDF、全文/关键页提取 hash、正式 30-command table、GxEPD2 15-group init 与抓包
  12-byte fragment 定位，且将 p.64 `LUT0 (20h)` 图示与未公开 ABI 分开。schema-2 下载路径
  只接受三个 fixed HTTPS URL、拒绝 redirect，并在读取前复核 final URL/HTTP 200。报告
  `.test-output/offline/jd79661aa_datasheet_cross_audit_v2_20260812.json`，
  file/canonical=`327628422c989f719e9e0e8aa5a2225be0718b93cc6bfd52fa05dbcfd85043ac` /
  `a82433e1db1941c6937d064a657b8889b98ea589227ae696858045d9ae8b34ef`；
- GxEPD2 GDEP073E01 固定源码审计：`tools/gxepd2_gdep073e01_source_audit.py`；比较 v1.5.9/
  v1.6.9 的 mapping、14-event init、one-CS header、`0x83` partial implementation 和全部 typed
  commands，并以 SHA/kind/schema/safety 固定 Good Display cross-image 输入。报告 file/canonical=
  `8fb4638154ec6bc6ea94827a04abcfac5b3bd5777eddb1a8047de6e3d9d786d2` /
  `89d0a0fb4028e68ba5e3b7e2658e5b0a6fd4965b42f102ae569f410b10fce87a`；
- 单元测试：`tests/test_mf1750_spd1657_reverse_delta.py`、
  `tests/test_good_display_esp32e6_firmware_audit.py`、
  `tests/test_good_display_esp32e6_cross_image_panel_audit.py`、
  `tests/test_good_display_gdep073e01_source_binary_contract_audit.py`、
  `tests/test_jd79661aa_datasheet_cross_audit.py`、
  `tests/test_mf1750_final_axf_init_linkage_audit.py`、`tests/test_e2802_r43_lut_proof.py`、
  `tests/test_e2801_r43_lut_proof.py`、
  `tests/test_mf1750_spd1657_vendor_profile_pack.py`、
  `tests/test_mf1750_spd1657_phase_geometry_audit.py`、
  `tests/test_mf1750_spd1657_patent_11byte_audit.py`、
  `tests/test_mf1750_armcc_loadwf_deep_audit.py`、
  `tests/test_mf1750_armcc_mode1_residual_audit.py`、
  `tests/test_mf1750_stm32_loadwf_abi_boundary_audit.py`、
  `tests/test_mf1750_spd1657_spi_capture_audit.py`、
  `tests/test_mf1750_vendor_artifact_hunt.py`、
  `tests/test_mf1750_iar_r43_cross_object_graph.py`、
  `tests/test_mf1750_iar_xlib_external_index_audit.py`、
  `tests/test_mf1750_iar_ubrof11_xlib_availability_audit.py`、
  `tests/test_mf1750_iar_xlib_provider_graph.py`、
  `tests/test_mf1750_iar_temperature_selector_audit.py`、
  `tests/test_mf1750_iar_project_config_chain_audit.py`、
  `tests/test_mf1750_iar_data0_data1_compatibility_audit.py`、
  `tests/test_mf1750_iar_load_lut_const_abi_audit.py`、
  `tests/test_mf1750_lut_callsite_destination_audit.py`、
  `tests/test_mf1750_spd1657_arithmetic_transform_audit.py`、
  `tests/test_mf1750_iar_ubrof11_e2_projection_audit.py`、
  `tests/test_mf1750_iar_final_d43_provider_chain_audit.py`、
  `tests/test_mf1750_spd1657_category_alignment_audit.py`、
  `tests/test_mf1750_79661_capture_semantics_audit.py`、
  `tests/test_gxepd2_gdep073e01_source_audit.py`、
  `tests/test_mf1750_spd1657_waveform_invariant_stats.py`；
- 历史 12 文件基线为 `147 passed, 8 subtests passed`。V7 与首批后续审计封存后，
  23-file 联合定向回归为 `259 passed, 8 subtests passed`；再加入 DATA0/DATA1、ArmCC
  residual 和 Good Display cross-image 三项审计后，最新 26-test-file 回归为
  `278 passed, 8 subtests passed`。再加入 const-helper、category、GxEPD2 与 79661 四项审计后，
  29-test-file 联合回归为 `304 passed, 22 subtests passed`；继续加入 Good source↔binary、
  JD79661AA schema-2、UBROF11 XLIB availability 与 LUT destination 四项后，33-test-file
  联合回归为 `332 passed, 22 subtests passed`。再加入 arithmetic schema-2、E2 projection 和
  final-D43 provider-chain 三项后，最终 36-test-file 联合回归为
  `365 passed, 22 subtests passed`。累计 77 个相关 Python 文件 Ruff check 与 `py_compile`
  PASS；本批新增 6 个 Python 文件 Ruff/format/py_compile PASS，3 个新工具 Windows GBK
  module-form CLI help PASS。三份 V7 release 又独立 deep-validate 为
  `valid=true/device_io=false/network_io=false/visible_refreshes=0`。

审计工具会冻结 ZIP/PDF/library/object 身份，在内存解密候选，解析 targeted CROF relocation、
DWARF array types、H1/H2/H3、IAR UBROF 唯一机器签名、双控 glue、原理图和 OTP payload
关系，并已为三个假设生成仅含 command/length/hash 的双控 mock SPI trace；输出只有 hash、长度和
判定。主审计仍固定 `runtime_profile_ready=false`、`visible_runtime_test_authorized=false`。
独立固化器只在明确 `--profile` 时生成编译期 H3 数组，并在输出中固定
`empirical_h3=true/live_authorized=false/profile_auto_selected=false`；生成文件本身不含硬件、
刷写、刷新或授权路径。

## 9. Empirical H3 四固件离线执行闭环

在不提升 U1--U7 证据等级的前提下，牺牲屏经验路线已经实现为四份互不覆盖的专用构建：

- `platformio.runtime_lut_wf20_25.ini`：WF20 固定八码镜像 atlas，单 runtime action；
- `platformio.runtime_lut_wf23_25.ini`：WF23 固定八码镜像 atlas，单 runtime action；
- `platformio.otp_white_wf20_25.ini`：无 runtime payload 的 factory-OTP white recovery；
- `platformio.otp_white_wf23_25.ini`：无 runtime payload 的 factory-OTP white recovery。

runtime 路径在任何 panel command 前验证 profile/header/PWR/PLL/R20/R21、frame 和双 DTM
identity；全局命令固定为 `ToBoth: PSR5FE9→PWR→idle→PLL→TRES512×600`，仅
`E9→idle→R20/799→R21/704×FF` 按 `CS1→CS2` 逐颗发送。无 raw ingress、retry、
autochain、profile switch、VCOM 写/扫或 `0x90/0x91` OTP-program emission。recovery 使用
独立 main、NVS namespace 和授权，只执行已验证的 factory-OTP init 与固定全白 action。

V3 首次断电上机暴露了一个未被静态测试覆盖的 SDK 现实：随 Arduino framework 固定的
`CONFIG_APP_RETRIEVE_LEN_ELF_SHA=16` 会让 `esp_ota_get_app_elf_sha256` 即使收到 65-byte
缓冲区也只返回 16 个 hex。固件在 `epdBegin` 前正确 fail-closed，因而没有触发屏幕，但 V3
不能执行。V4 改为调用 `esp_ota_get_app_description()`，直接把 running
`esp_app_desc_t.app_elf_sha256[32]` 编码成严格 64 位 lowercase hex；host 同时核对 BIN app
descriptor 内嵌 ELF SHA、所选 ELF、唯一
transaction descriptor 及 release contract。主机执行器的离线 `authorize` 只在一份刚生成且
密封的 J2-OFF diagnostic 之后接受用户逐字重输 U1--U7 phrase；V2 token 同时绑定 diagnostic
canonical SHA 和 boot nonce，但该离线输出仍固定 `live_authorized=false`、不建 claim、不访问
网络。`diagnose` 和 `run` 在任何 GET/claim 前先用 `O_EXCL+fsync` 预占结果文件并保持同一 handle
到终态；transport 的 literal IPv4、port 和 timeout 也在 claim 前验证。`run` 随后先永久 claim，
再各只允许一次真正 bodyless ARM/EXECUTE；系统代理被显式禁用、redirect 被拒绝、origin 只
接受 literal private/loopback/link-local IPv4 的 plain HTTP。刷新期间 ESP WebServer 可能阻塞，
因此固定 settle 后只允许有界 GET report polling；timeout/reset 只产生 poll miss 或最终
UNKNOWN，绝不重发 POST。

四份 clean build 及 compiled identity 最终结果：

| Profile/role | BIN SHA-256 | ELF SHA-256 |
|---|---|---|
| WF20 runtime | `53d3abf2319761f282c518ebd6fd606f8efdfe0b1a869a1dcf61c04adbdecc06` | `63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df` |
| WF23 runtime | `6eb9115ef143142de801c96fe31c8b9898455f550a52a85c51cfa7a2026698e2` | `d385b01ffcee182d9614d9462489c44628990a576c54979cc9254c8fc3824aa1` |
| WF20 OTP white | `6a50b2bf287f3d6fd688c9cdfa2052ddc7db3d86c2f2ac9157585cdafd0766d2` | `0c8c82c35b46c69742f27a28c6fdce0ac2d003b3b0dd8a8b7b80152a608d9924` |
| WF23 OTP white | `2712984d39f1c295841a4b9994c72ee13f6c6935e514ce918648cce2a6159e7c` | `9c3587285d2b4748ca1594dffbc0848dd394d48c74bd205d6d7ce90699bd3939` |

当前唯一权威 release 是 schema 3 的 V7 目录：
`.test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/`。两份均已重新
deep-validate：

- WF20：release ID `52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e`，
  canonical SHA-256 `91a498788b074c0d8619e666df0e8c96fc8868e6c9fbee024b97ad8ad183d92e`，
  release file SHA-256 `323edaf20ddc60e1302b7df7217320ddb19c2c3ab47cad14409888469ec4809e`；
- WF23：release ID `9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4`，
  canonical SHA-256 `0f5dfeb8359abea5d0d4b5b800958737f161f78ca81ec3515877920fcd759b7a`，
  release file SHA-256 `c06ebabb7096ba848d9635c02609f86f0cc97302ae83cade3b315b6ab6346f3b`。

V7 共同绑定 host execution bundle canonical SHA-256
`3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0`。bundle 对每个可改变
校验或执行语义的仓库源码保存 canonical relative path、bytes 和实际 SHA-256，并在 deep
validation 时重新读取实际 bytes、拒绝 symlink/越界/读取中漂移：

| Host source | Bytes | SHA-256 |
|---|---:|---|
| `tools/mf1750_ec5_runtime_lut_physical_once.py` | 62522 | `f2f8ab28d8d0898d36a0f4d2c13d6342700383c79a814750eb6dd4c91215cb2f` |
| `tools/mf1750_ec5_runtime_lut_release.py` | 21063 | `18454d9064fb6b2e2d7c03ed4de39b525ee3de8efa1c235daa9309a81f8ee32b` |
| `tools/mf1750_ec5_runtime_lut_contract.py` | 20860 | `3dee62ff1d41a24846404cf81f626a3d70863beb9979c639afaa810c7d628177` |
| `tools/mf1750_ec5_runtime_lut_compiled_identity.py` | 13508 | `389cf3694a451a96b9fcc1af8bcf7da4f01f58b2313b5209d7a1f816568402c3` |
| `tools/mf1750_ec5_eightcode_atlas.py` | 19427 | `382c39468f78cf3509bd5deface6b62ca57f7da0f7ba29f5dd7e1137b48fc803` |

V7 materialize 不接收 U1--U7 acceptance 或 prior-state acceptance 参数；release 只记录
`live_authorization_prerequisites` 风险声明，明确 `accepted_at_materialization=false`、
`acceptance_is_proof=false`、`live_authorized=false`。既有 J2-OFF/白屏只作为 operator-reported
frozen reference，明确不是 fresh diagnostic，也不满足 live gate。真正的逐字接受只发生在
新鲜 diagnostic 后的 `physical_once authorize`，且 runtime 与 recovery 必须分别授权。

以下六代历史目录只保留证据，均为 **superseded / non-executable**：

- `...RELEASES_20260811/`（V1）：未绑定 host executor source；
- `...RELEASES_20260811_V2/`：虽绑定 source，但错误写入了未实际发生的
  `operator_build_acceptance`；schema 3 validator 会因缺少纯 prerequisite 对象而拒绝。
- `...RELEASES_20260811_V3/`：running-ELF 设备自证错误假定 SDK 会返回 64 hex；首次 J2-OFF
  诊断在首个 version GET fail-closed，未进入 `epdBegin`，随后被 V4 取代。
- `...RELEASES_20260811_V4/`：running-ELF 修复有效，但 host 曾把 profile 文件名数字误作温区；
  V5 改为 opaque filename tokens + exact `25.0°C` 实验护栏后，V4 因 host bundle drift
  fail-closed；
- `...RELEASES_20260812_V5/`：host 温度语义已纠正，但 runtime/recovery source 中仍内嵌旧
  contract/action IDs。release compiled-image validator 当时未把这些 ordinary strings 纳入
  required-ASCII gate，后续独立 firmware-contract test 发现不一致并拒绝继续；V6 更新四份
  source identity、重新编译并重新 seal。该事件是 validator coverage gap，不是硬件失败。
- `...RELEASES_20260812_V6/`：固件 identity 已修正；随后 compiled-image validator 又被加强为
  必须在 ELF 中找到当前 contract ID、当前 action ID，以及 runtime 对应的 recovery action ID。
  V7 只更新 host bundle/release seal，沿用 V6 的已修正 BIN/ELF；V6 因 validator source drift
  fail-closed。

权威离线复核必须使用 module 入口，不能直接运行脚本路径：

```powershell
python -m tools.mf1750_ec5_runtime_lut_release validate --release .test-output\hardware\MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7\WF20_25-release.json
python -m tools.mf1750_ec5_runtime_lut_release validate --release .test-output\hardware\MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7\WF23_25-release.json
```

最终差分审计还统一了 firmware、FakeDevice 与 runner 的 exact 7-key GPIO 合同：virgin status
要求 `RST/CS1/CS2/SCK/DC/MOSI=0`、BUSY 只作 0/1 有效性检查；terminal 要求 BUSY=1 且
其余六项全为 0，并对三个新增 GPIO 各自加入变异拒绝测试。

加入 29-object graph 时，12 个定向文件联合为 `147 passed, 8 subtests passed`；后续新增审计与
C-first 回归见下节和最终交接状态。release/runner/firmware 验证没有访问设备、COM 或设备网络；
公开检索只用于公开技术资料。用户此前选择 `WF20_25`、确认 J2 OFF 与 24.0°C；旧 V4 runtime
曾仅写应用区并由独立 `verify_flash` 验证，当时的 J2-OFF diagnostic exact `4 GET/0 POST` PASS。
V7 runtime 因内嵌新 contract/action identity 而有不同 BIN/ELF，当前仍未刷入；当前设备上的
旧映像为 superseded，不能用 V7 release/diagnostic 冒充验证。
这些温度与 diagnostic 现在都只作历史证据，不能复用于下一次现场动作。

## 10. C-first matched control 与当前现场门禁

为了让下一轮真屏结果能回答“颜色变化是否由 R20/R21 组合流带来”，经验路线已经从直接 H3
改成固定四阶段：

```text
1. C：相同 factory init / 5F,E9 / PWR / PLL / TRES / E9 / atlas，但不发送 R20/R21
2. 独立 factory-OTP white recovery，断开并平衡
3. T：pinned V7 empirical-H3 atlas，发送 R20/799 + R21/704*FF
4. 独立 factory-OTP white recovery，最终 J2 OFF
```

C 不是严格 time-matched control：每控制器删除了 2 个 command spans、1505 个 SPI bytes/edges
和 5 次 cooperative yield，双控合计删除 3010 bytes/edges 与 10 次 yield；没有插入 dummy clock
或 empty R20/R21。因此若 C/T 不同，正式归因只能是“组合 R20/R21 command stream 的增量可见
效应”，仍不能分离 opcode、payload、时长，也不能证明 LUT ABI 或安全接受性。

当前权威 matched-control release 为
`.test-output/hardware/MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10/WF20_25-release.json`：

- release ID `1cf8307c8906fa3057509c7a4a15bd79156751aa6b27c3f158435fbaa1049e36`，
  canonical SHA-256 `5616bd495c9faf0983c3d361d5d3bea57837c5f5d8a498805cca940ca595b00e`，
  release file SHA-256 `a716dac890b3e272144365f51ae1167f6306d4830d841b11d00610ebb2b0698b`；
- host execution bundle SHA-256
  `888ab013b6d3bb4ee8b2b2a87fdc348cb5ac2ce9265396ea5a39c70179416a3c`；
- matched contract ID
  `25267914e74b249cc4bd1cc821437ea700a3c41a75140d82862c86357b3a63fe`；
- compiled trace audit ID/canonical=`e2ebf082f779f4f61095b81dada2109c714c46e14ccc7020e43538e5492107f3`/
  `185d111e437de55d33df2fda6c647f33267ed7e571e73374dd22f2f3ed6b877b`；
- C BIN/ELF=`f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e`/
  `27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41`；
  C-recovery BIN/ELF=`6ab18de07ffbf0ad56dbd6861957a42ea15c6cce9e435f790e74df1050cfa51d`/
  `6aba1ecb5eb339494c20cf51c56137f61d5568a596f644a7862b951cb45ed147`；
- treatment pin 仍为 runtime V7 release ID `52553c37...837e`、runtime BIN/ELF=
  `53d3abf2...cc06`/`63add1a2...91df`。V10 已离线 deep-validate，但尚未刷入。

pair evidence 现要求四阶段各自的成功 result/永久 claim；C 与 T 两腿又分别重放各自 fresh
diagnostic，并核对 result boot nonce 与 claim 中的 diagnostic canonical SHA。stage-3 的 intended/
approved façade 在 token、claim、HTTP requester 之前深验 finalized C-leg、treatment gate、精确
0.1°C 温度、matched V10/runtime V7 release 与 compiled action identity；不会重试、自动恢复或串播。旧通用
runtime runner 仍可在流程外直接调用，façade 不能物理禁用它，最终 pair evidence 也
不能密码学证明 T 必经 façade；这条 process boundary 已在 release 与证据中显式固定为 false。

matched V10 保留了两个 host-side TOCTOU 防线：control/treatment finalizer 对 claim 文件只读取一次，
并从同一已验证内存对象绑定 diagnostic canonical；C-first facade 在 preclaim 验证后重新核对
原 treatment release bytes，以 `O_EXCL+fsync` 建立逐字节相同的私有 snapshot，字节比较并深验
后才把 snapshot 路径交给 frozen runner。原路径在验证后被替换会 fail-closed。该机制仍不能物理
阻止有权限的并发进程篡改临时 snapshot，也没有禁用旧通用 runtime runner，因此现场仍须专用受控
进程和操作纪律，不能宣称入口具有物理或密码学唯一性。

先前 matched-control V1--V9 都因 host source bundle、pinned treatment、firmware identity 或
真实 device JSON contract 变化而在 deep validation 中 fail-closed，现为
**superseded / non-executable**。V2 的最后一次
4-byte 漂移来自把 Windows
GBK 终端无法编码的 `façade` 帮助文本改成 ASCII `facade`；V3 随后因 claim/facade TOCTOU
修复而失效；V4 后因文件名温度语义纠偏而失效，V5 又被 firmware-contract test 发现内嵌
runtime identity 过期；V6 修正固件后又因 compiled-identity validator 加强而失效，由 V7
重新封存；随后 C-first 与 matched-release CLI 中残留的旧 `V4` 帮助文字被改为不易过期的
“pinned release”，host source bundle 因此改变，matched V7 fail-closed。matched V8 重封该
host-source 修正，并于 2026-08-13 在 J2 OFF 下 app-only 刷入 C；write hash 与独立回读均 PASS，
新 boot 明确无 startup refresh。随后正式 diagnostic 第一项 GET 因 `/version` 缺少 `profile`
而终止，0 POST、0 claim、0 driver call、0 visible refresh。V9 的首次补丁又多出引号，离线测试
捕获后从未刷入。V10 修正 JSON 并增加对真实 C++ 拼接的 contract test，重新构建 C/C-white、
重封 release；当前 `visible_refreshes=0`、`live_authorized=false`，四阶段仍为 `0/4`。

V4 封存时的历史基线是 `208 tests + 8 subtests`。V7 封存后并加入后续审计，主流程联合覆盖
release/physical/finalizer、firmware/compiled identity、三类 synthetic ELF identity 删除或替换、
V1--V6 fail-close、ArmCC ABI、E2801/E2802、vendor/geometry/patent/SPI/artifact，以及
IAR graph/XLIB/provider/temperature selector/config chain、waveform invariant、官方 ESP32E6
固件/source↔binary、const-helper/category/GxEPD2/79661 capture/JD datasheet、XLIB availability、
LUT destination、arithmetic/E2 projection/final-D43 provider chain；最终为
`365 passed, 22 subtests passed`。累计 77 个相关 Python 文件 Ruff check/`py_compile` PASS；
本批新增 6 个文件 format check、3 个新工具 Windows GBK CLI help PASS。该数字是 V8 前的历史
基线；后续新增审计与 V8--V10 的回归见 `docs/STATUS_HANDOFF.md`。当前 runtime V7 与 matched
V10 均保持 `valid=true`、release 自述 `device_io=false/network_io=false/visible_refreshes=0`；
这不抹去上段已经单独记录的 V8 app-only 刷写事实。

用户已完整确认 `J2=OFF / ESP32 USB / 干净全白 / 3.3 V CV / exact 25.0°C / 四项监测与物理
切断 / 未刷新未改线`，该确认只授权了上述 V8 app-only 刷写流程。V8 diagnostic 失败后 ESP32
USB/COM8 消失，当前只枚举蓝牙 COM9--COM12；V10 尚未刷入。下一步必须保持 J2 OFF，只重新
枚举 ESP32 USB，验证 MAC `a4:cb:8f:d9:fc:d4` 后 app-only 刷 V10、独立回读，并重新生成
绑定 V10/current boot 的 `4 GET / 0 POST` diagnostic。完整 PASS 前不得打开 J2；PASS 后也只会
请求 J2 ON 实时电气复核，四个可见 action 仍各需新的 one-shot 授权，计数保持 `0/4`。
