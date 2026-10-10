# SPD1657 runtime-waveform 目标完成度审计

日期：`2026-08-12 +08:00`

## 1. 当前总判定

```text
STRICT SAME-VERSION MODE-1 ABI  : NO-GO
EMPIRICAL H3 CODE/RELEASE PATH  : CONDITIONAL GO
C-FIRST PHYSICAL ATTRIBUTION    : 0/4
```

这个判定把三件不同的事分开：

1. 已经从厂家交付物恢复出的直接事实；
2. 由相邻版本和多个独立工件共同支持、但仍不能称为同版 ABI 的 H3 假设；
3. 已封装为 fail-closed release、仍必须由用户在现场逐项授权的真屏实验。

本报告不输出 raw waveform、customer key 或可变电气参数，也不授权任何硬件动作。
用户已在同一现场状态完整确认 `J2=OFF`、ESP32 USB、屏幕干净全白、3.3 V/CV、exact
`25.0°C`、四项监测/物理切断以及“自上次白屏后未刷新、未改接线”，并授权 app-only 刷入。
matched V8 C 的刷写与独立回读均 PASS，但新 boot 的正式 diagnostic 在第一个 GET 因
`/version.profile` 缺失而 fail-closed；0 POST、0 claim、0 driver call、0 可见刷新。该真实 firmware
contract 已在 V10 修复，V9 无效 JSON 在离线阶段被拦截、从未刷入。随后 ESP32 USB/COM8 消失；
当前设备最后已知为 V8，V10 尚未刷入，仍禁止打开 J2。历史/V8 diagnostic 不能复用。

## 2. 目标逐项完成度

| 目标项 | 当前证据等级 | 已证明内容 | 仍缺的直接证据 / 不能声称的内容 |
|---|---|---|---|
| 两份厂家 waveform 身份 | **直接证明** | `WF20_25` 与 `WF23_25` 是两份内容不同、身份冻结的真实厂家 wrapper；各自有独立 ciphertext、wrapped-key 和明文 hash | 文件名数字没有公开语义；不能称为温区、亮度档或 K0/K1 |
| 800-byte envelope | **直接证明** | 两份 wrapper 均解出 800 bytes；结构均精确满足 `7 + 9*(8*11) + 1 zero outer byte`；候选 `799→800` 与已知 `535→544` 都恰为各自长度的最小 16-byte AES block roundup | 共同对齐只与 AES zero-fill 相容；outer byte 作用仍未知，不能命名为 padding/sentinel/terminator/checksum；没有同版本、已链接的 mode-1 loader 把 envelope 绑定到当前控制器命令 |
| 535-byte mode-0 路径 | **直接证明** | ArmCC retained object 的 relocation、DWARF 和 CFG 证明 decode 544、逻辑 `WF_SIZE=535`，并向 `0x20` 原序发送前 535 bytes；line program 把完整 active `loadWF` 映射到 `987..1023`、final row `1020`，四个 writer calls 为 `1001..1004`。candidate writer 逐 byte 原序输出，没有补码/record parser；交付 GBK 源码又把 exact `i=0..534` 循环与“循环次数根据不同的芯片规格有所不同”绑定在同一行 | 注释只证明源码作者没有把 535 描述成跨芯片通用常量；这是 mode-0 build，且 provider 未进入七份 final，仍未点名 mode-1、799/800、controller revision 或双控 sink。`935..986` 的 52-line gap 不能恢复 preprocessor-elided source |
| 799-byte mode-1 候选 | **跨版本直接证明 / 同版本待证** | 2020 IAR E2801/E2802 的 active upload 机器码证明 `0x20, dataBuff+4, 799`；官方 XLIB 又直接声明 `dataBuff[2560]`、generic loader `void(uint16,uint8*,uint16)`；800/799 与 544/535 的最小 AES roundup 关系又被两份 wrapper 独立支持；两对象共有 retained `DATA0[1503]` 又精确等于 `first799 + FF*704` | AES alignment 不证明 logical-length 或 outer-byte 语义；完整 type inventory 没有 799-byte named subobject，DATA0/DATA1 的 internal relocation reference counts 均为 0；当前 2025/2026 ArmCC 仍无配对 mode-1 loader，H3 仍是跨版本推断 |
| 704-byte `0x21` | **旧代直接证明 / 当前待证** | 当前 ArmCC mode-0 有独立 `LUT1_DATA[704]`；旧 IAR active upload 逐字节循环生成 704 个 `FF`；retained DATA0 后 704 bytes 与之 byte-identical | 没有当前同版 mode-1 loader 证明 H3 的 `0x21/704*FF`；retained `DATA0/DATA1` 均不是 active source，且 `DATA1[704]` 不等于 FF704 |
| 2508-byte温区 slot | **旧代直接证明** | E2801/E2802 均在 30 个 slot 中以固定 selector 25 选择 `lower <= 25 < upper` 的条目，再读 2508 bytes | 2508 是旧存储容器，不是当前 800-byte wrapper ABI；也不能替代实时温度或面板/FPL 匹配 |
| category 几何 | **legacy 坐标标签直接证明 / mode-1 标签未知** | mode-1 body 为 `9 categories × 8 groups × 11 bytes`；同一 `EDP_init.c` 的 commented/active 两张完整 535-byte 表都逐条标出六类各 `GROUP1..8`；active initializer 又由 `edp_init.o` 的 ELF32 `wf_data[535]` 与 MAP 固定，`EPD_initial` 则原序转发当时 mutable global 的 535 bytes | linked UART case-5 路径可清空并替换 `wf_data`，因此 initializer 内容在每次 upload 时未被证明；`GROUP` 是 source-labeled slot，不等于 chronological phase；inactive 表作用未知且未编译，不能提升为 runtime candidate；legacy 标签与 DATA0 无完整行或 mask 匹配，不能命名 mode-1 category 或 controller bank |
| 11-byte record | **边界直接证明 / 多类相邻字段投影完成 / 本地字段未知** | 两张 legacy source table 的 48 个边界均有直接 GROUP 标签；WF20/WF23 的 11 个列索引均至少一处变化。SPD1656 官方 R20/VCOM 精确给出 `20×(RP+2-byte packed LVL+8-byte TP)`；SSD1680A、SSD1683/1683A 又独立证明 Solomon 家族存在 8 groups，但真实每 LUT group 是 `RP+4×(VS|TP)+2 SR=7 bytes`、waveform command 为 `0x32/227`；Philips Apollo 则只提供异厂 11-byte instruction | 没有一份相邻资料同时匹配本地 group count、record width、command role 与 payload length。SPD1656 raw/complement 穷举不唯一；SSD1680A 的五种连续 7-byte offset 在位域层面全部可解析且每 record 余 4 bytes；SSD1681 与 SSD1683 对同名 RP/SR 的 zero 语义还相反。把 4 phases 扩成 8 phases 只是未发表算术猜想。不能命名本地 RP/LVL/VS/TP/SR、phase 数、电平、时长或 `FF`/zero 语义 |
| PWR/PLL header | **两条 mode-0 路径分别直接证明** | retained ArmCC `loadWF` 机器数据流把 decoded `[0:5]` 接在 literal `0x0F` 后写入 PWR，并把 `[6]` 写入 PLL；另一本地 compiled/linked `EPD_initial` C 路径在 literal `0x07,0x00` 后只把 `wf_data[1..4]` 送 PWR，byte 0 无独立 scalar use，byte 5/6 的 struct assignment 均无后续 named use且专用 VCOM/PLL 使用另一 global/literal | 两条 mode-0 绑定本身不同，不能混成单一 header ABI；移植到 mode-1、双控及当前面板/FPL 仍未证明。legacy `wf_data[5]` 的 VCOM comment label 不能移植为 candidate `plain[5]` 的字段名 |
| PSR/LUT_EN/隐藏 `E9` | **经验拼接** | factory 双控 PSR、单控 runtime PSR/`E9`、SPD1657A bit definition 分别有来源，最小位级候选为 `5F,69 -> 5F,E9` | 没有一条同版路径或 capture 同时证明 PSR、`E9`、PWR/PLL、R20/R21 的值、顺序和 BUSY 语义 |
| 双控制器装载 | **实验发送端实现完成 / exact as-built 仍未证明** | 当前 matched V10/runtime V7 所绑定的固件固定 `CS1 -> CS2`，同一 profile、长度和 hash；exact MF1750 规格直接写明 `1024×600 / two SPD1657`、pin4=`SL_CSB`、pin31=`CSB`；legacy IAR/final D43 各只落到一个 fixed CSB software endpoint。SSD2677 公开相邻双芯的 M/S# 与模拟电源/同步互连 | single software endpoint 不证明物理单控或双控广播；相邻 adapter 只有 J4 闭合时才条件性 `CS→SL_CSB` fanout，且 pin4 存在 `FPL_VCOM` symbol 与 `SL_CSB` net 冲突、J4 实物状态未知；SSD2677 也不公开 exact SPI/CS transaction。没有同代 800→799→exact 双控 sink，接受/失败原子性/回滚均未闭合 |
| 最终 IAR provider/link chain | **最终 D43 直接证明 / named runtime upload NOT_FOUND** | 官方 XLIB 直接解 absolute D43；其 2002 个 addressed bytes 与 TI-TXT addressed image 全同，188/188 CALLA 机器目标通过；`main→E6_73::EPD_Init/六 display`，E2801/E2802 非 final；GPIO 机器码证明 physical DC low、SDA 第九位分 command/data 的 9-bit 3-wire SPI 及单一 `P6.3` CS endpoint | final 为 `800×480/192000 packed bytes`、内嵌 V1.1 lineage，不是 exact MF1750 geometry 或 V1.2 rebuild；exact final 无 named upload 不证明芯片、其他 build、剥离/间接路径从不存在 runtime LUT |
| runtime→factory 恢复 | **独立 recovery 实现完成 / 物理闭环待证** | 已有不含 runtime payload 的独立 factory-OTP white 固件、独立 NVS/action 和 fail-closed host gate | 尚未在一次真实 runtime treatment 后验证 OTP white 能恢复；没有 post-runtime readback 或厂家恢复时序 |
| 公开一手资料 | **当前检索范围完成** | SPD1657 的 Solomon/COMPUTEX 页面现直接闭合 `800×600 active-matrix Spectra 6` 产品身份；SPD1656、SSD1680A、SSD1681、SSD1683/1683A、SSD2677、ED2208、Good Display、Waveshare 双控样例、E Ink Ripple 和相关专利均已逐项固定边界。SSD2677 证明 2024 同厂 color/programmable-waveform/cascade 手册仍可不公开 runtime ABI；EPM-100 与 ED2208-DOA 提供相邻 runtime/update 正证据 | 产品身份不是 datasheet。所有相邻控制器都不能移植命令/字段/电压；ED2208 手册不公开 `.eink` 格式。仍未找到 SPD1657/B `799/704/2508` ABI、双控提交/恢复或 `WFxx_yy` 命名规范；negative finding 不是不存在证明 |
| 新版 XLIB/UBROF11 | **observed dialect 已恢复 / 原件 native parse 未取得** | no-offset differential 覆盖 `3 delivered + 29 public` 个 exact MSP430 UBROF11 objects、选择 139 条 E2 records；namespace/interrupt alias/machine graph 交叉一致，32/32 原件复现旧 XLIB E2 边界，32/32 临时 E2-elided projections 可列 EXTERNAL/ENTRY | field roles 与 grammar 仍是 inferred observed dialect，不是官方通用 UBROF11 grammar；projection 不是原件 native parse、object replacement 或 link/flash input。仍须合法取得并固定官方 `xlib.exe>=6.3.4.78` 直接复核原件 tables |
| 官方 ESP32E6 binary | **静态审计完成** | 三 app 的 identity、host dither、共有 typed E6 init/display、六 tag→4-bit packing、SD-card SPI 与面板 bitbang 分离均已固定 | typed graph 仍无 `0x20/0x21`、704/2508、双控或 brightness/contrast register；其余 raw 数值不得作为 typed command 使用 |
| GDEP073E01 code4 冲突 | **第三方候选 / 厂家未交付** | GxEPD2 v1.6.0+ 有意标注并发送 `code4=orange`；厂家 2024 源码与 2026 binary 在六码集合、geometry/frame 与 init trace 上逐项一致 | Good Display 产品、规格、Image2LCD、源码和 binary 均只交付 `{0,1,2,3,5,6}`；`7` 仅为 header `Clean`；one-CS adjacent implementation 不可移植到 MF、不可命名 category |
| `79661.csv` / JD79661AA | **decoded-row + datasheet 审计完成 / transaction 未恢复** | 12722 行身份固定；全部已知 535/704/799/800/1503-byte reference 的 every contiguous MOSI window exact match 均为 0；12-byte fragment 精确定位到完整 `0x03` 与 `0x06` groups。官方 PDF 的 PSR 只证明 register-LUT 概念，p.64 两个示例图均出现同一 `LUT0 (20h)` marker | 正式 30-command 表没有 `0x20/0x21/E9`，没有 payload 长度/格式；抓包缺 SCLK/CS/D-C/controller，不能恢复 transaction、证明 exact panel/generator 或移植到 SPD1657 |
| legacy LUT helper ABI | **机器 ABI/发送数据流直接证明 / 当前代待证** | E2801/E2802 的 const/mutable helper 均为同一 32-byte `R12=cmd,R13=ptr,R14=count` sender；逐指令循环只做 byte load、SPI write、pointer/count increment，没有 NOT/XOR/RBIT/REV、11/88 stride、值比较或 early stop；const 零已观察消费者且不绑定 DATA0/DATA1 | 只证明 MCU 发送侧原序固定长度转发；controller 内部 complement/decode 未知，仍不是当前 ArmCC 800-byte loader、双控接受或电气合同 |
| 可复现工具和报告 | **当前证据范围完成** | 在 wrapper/DWARF/GPIO/record/E2 链上再新增 34-object/7-AXF command-sink inventory、IAR XLIB type/local/ref inventory，以及四份 SSD1681/1683/1683A/2677 whole-file/page-text identity 的 adjacent-family metadata audit；连同 DATA0/helper/arithmetic/provider/温区/category/invariant/79661/JD79661/GxEPD2/source↔binary/release 审计形成可复核链 | 工具能证明交付物和固定 public corpus 内的事实，不能补出预处理阶段已删除的 mode-1 分支、官方通用 E2 grammar、11-byte decoder、exact as-built J4 状态或 NDA 资料 |
| 真屏因果判别 | **未执行** | 两套 profile 的 runtime/recovery 加 matched C/C-white 共六份映像已封存；首轮只按 C、C-white、WF20 T、T-white 四项执行 | 当前为 `0/4`；没有真屏结果时不能声称 R20/R21 被接受、颜色增加或恢复成功 |

## 3. 当前最强且仍有边界的 H3 解释

```text
800-byte decoded envelope
  logical R20 payload = decoded[0:799]
  trailing outer byte = decoded[799] == 0   # role unknown
  R21 payload         = FF * 704
```

H3 成为首选，不是因为文件名或颜色猜测，而是同时满足：

- 两个不同 profile 都具有相同 800/799 envelope 几何；
- 现行 mode-0 有 `544-byte decoded block -> 535-byte logical payload` 的长度关系；
- 旧 IAR E2801/E2802 的 active upload 直接执行 `R20/799 + R21/704*FF`；
- 两个不同 IAR 对象共有的 initialized `DATA0[1503]` 精确为 `first799 + FF*704`，但无自然引用；
- 当前 matched V10/runtime V7 发送端可以对两个 CS 的 command、length 和 payload hash 作精确审计。

这里的 `544=ceil(535/16)*16` 与 `800=ceil(799/16)*16` 只证明最小 AES block roundup；
它们不证明 `decoded[799]` 的作用，也不把跨版本 `799` 自动提升为当前 loader 的逻辑长度。
它仍没有跨过版本边界。C/T 真屏差异至多证明“加入组合 R20/R21 stream 产生增量可见效应”，
不会单独证明控制器按预期解析了 799/704，也不会解出 category 或 11-byte 字段。

## 4. 剩余工作如何收敛

### 4.1 本轮完成的纯软件收敛

1. IAR `DATA0[1503]` 已由官方 XLINK 固定 extent，并精确切分为
   `first799 + FF*704`；E2801/E2802 数组逐字节一致。两完整对象闭包均为零自然引用，
   delivered Debug 不链接它们，因此只提升为 initialized-constant/结构旁证。
2. 三个 Good Display ESP32E6 app 已恢复共同的 typed E6 init/display 和 panel transport；
   typed graph 内仍无 runtime-LUT，初轮“panel path unknown”已更新但 ABI 判定不变。
3. ArmCC residual 审计已闭合 430 个 pinned 文件、唯一 library/member、Keil
   DEP/LNP/SCT/MAP/AXF 和 editor/capture 残留；未发现第二个 loader 或 mode-1 配置入口。
4. `EPD_Load_LUT_const` 已证明只是未消费的 generic pointer sender，不是 DATA0/DATA1
   selector；active legacy upload 只调用 mutable helper。
5. category 对齐已排除 ordinal/nearest-distance/FF-mask 标签转移；row0 公共 record 已降级为
   `10/11 FF` 的 filler-compatible 弱线索。
6. `79661.csv` 已完成 every-window exact identity 与 timing/JD79661 fragment 审计；仍不能恢复
   transaction。GxEPD2 的 `code4=orange` 已与厂家六码资料并列为不可移植冲突假设。
7. Good Display 2024 源码与 2026 binary 已在六码集合、800×480 geometry、384000→192000
   packing 和 init trace 上交叉固定；不把此范围扩大解释成完整控制器/波形一致。
8. JD79661AA schema-2 审计把 PSR register-LUT、p.64 `LUT0 (20h)` marker、正式命令表和
   capture fragment 分开；网络路径只允许 fixed HTTPS GET 且拒绝 redirect。
9. 新版 XLIB 搜索已收敛为精确外部缺件：官方 `xlib.exe >=6.3.4.78` 的合法来源、身份固定及
   六条只读 LIST；未提交注册/许可，也未运行未知 binary。E2 differential 又覆盖 32 个 exact
   MSP430 UBROF11 objects、139 条 observed records 和 32/32 temporary projections；仍不冒充
   官方通用 grammar 或原件 native parse。
10. LUT callsite/destination 审计把 legacy IAR 与 ArmCC loader 的末端 CS 数据流闭合为两个
    单主控路径；现有 `ToBoth` API 与 loader 断开，七份 MAP 也都移除了 `writeEPD/loadWF`。
11. schema-2 arithmetic 审计固定全部长度等式，并以 bounded negative 排除所测简单
    transform/checksum、DATA0↔DATA1 active bridge；没有因此命名 category/phase/electrical 字段。
12. final D43 直接解码闭合 `main→E6_73` provider、D43 decoded image↔TI-TXT addressed-image
    byte identity、9-bit 3-wire transport 与单一软件 CSB endpoint；再与 exact MF1750 双
    SPD1657 规格和相邻 adapter J4 条件 fanout 分开，as-built topology 保持未证。
13. wrapper-alignment 审计把 `535→544/799→800` 限定为最小 AES block roundup；未命名 outer
    byte，也未提升 H3 evidence grade。
14. DWARF line-program 审计把 23/23 active functions 唯一绑定，并固定 `loadWF` lines
    `987..1023`、final row `1020`、writer calls `1001..1004`；52-line gap 不作 source recovery。
15. record-semantics schema-3 审计把两张 source-labeled 535 table、active ELF `wf_data`、MAP 与
    同一 `EPD_initial` 内紧邻的 `0x20 -> i=0..534 -> wf_data[i]` 三元组分层固定；
    循环同一行的 GBK 注释直接说明循环次数
    随芯片规格而异，但不提供 mode-1 的 799/800 长度。新增 linked UART mutation
    层明确阻止把 compiled initializer 提升为每次 runtime upload contents；`GROUP` 不作 phase，
    11-byte 字段和 inactive 表作用保持未知。
16. ArmCC executable inventory 固定 34 个 retained `.o` 和 7 个 final AXF：唯一业务 R20
    command-sink 是旧 `EPD_initial/535` 单-CS路径，R21 sink 为 0，704/799/800 的 raw
    coincidences 均未绑定 payload；没有同版双控 runtime loader。
17. IAR XLIB type inventory 直接固定 E2801/E2802 的 `DATA0[1503]`、`DATA1[704]`、
    `dataBuff[2560]`、selected sender/read signatures 和 upload locals；DATA0/DATA1 internal
    relocation refs 均为 0，完整 array dimensions 没有 799/11/88 typed object。
18. EPM-100 WBF 与 ED2208-DOA `.eink` Initial Data 被单独固定为 adjacent runtime/update
    正证据，同时明确其 parser/ready/temperature/electrical contract 不能移植为 SPD1657 ABI。
19. schema-3 record-semantics focused `12 passed`，ArmCC inventory `6 passed`，IAR type +
    DATA0 compatibility `16 passed`；对应 Ruff check/format、`py_compile` 与 GBK help 均通过。
    精确 44-file 联合选择集在仅对当前进程设置 `safe.directory=*` 后最终为
    `460 passed, 29 subtests passed in 419.76s`、exit 0；未修改 global Git 配置。首轮 7 项
    setup error 已证实仅为沙箱账户读取既有临时 Git checkout 的 ownership gate，不是断言失败。
20. E2801/E2802 generic sender 的逐指令数据流已固定为固定长度原序转发；发送侧无补码、字段解析
    或 terminator，但 controller-side decode 继续 unknown，故 complement 统计不能升级为 ABI。
21. SSD1683/1683A 把 8-group/7-byte/R32-227 反例延伸到 2023；SSD1681 证明同族同名 RP/SR
    的零值语义并不稳定；SSD2677 则证明 2024 同厂 color/cascade/programmable-waveform 产品仍可
    不公开 runtime LUT command。COMPUTEX 页面闭合 SPD1657 产品身份，不闭合任何技术字段。
    新 `mf1750_solomon_adjacent_family_audit.py` 把四份 PDF whole-file/page-text identity、跨文档冲突
    与 non-portability adjudication 固化为 deterministic metadata-only JSON；focused `6 passed`，
    Ruff check/format 与 `py_compile` 通过。

### 4.2 仅靠现有离线材料大概率无法再闭合的项目

- 当前同版 `E5_3Bit_Mode=1` loader；
- category→色码和 11-byte 内部字段语义；
- 当前面板/FPL/膜批的温区及电气资格；
- 两颗控制器的接受、失败原子性和回滚；
- runtime 后 factory-OTP 恢复的真实效果。

这些项目需要至少一种新证据：配对源/对象、厂家寄存器与 waveform 文档、已知正确系统的双 CS 逻辑分析 capture，或按既定 C-first 顺序取得的受控真屏结果。

## 5. 下一次现场动作的唯一顺序

```text
C        matched no-R20/R21 atlas
  -> C-white  independent factory-OTP white
  -> T        pinned WF20 H3 atlas
  -> T-white  independent factory-OTP white
```

每一步都是独立固件、fresh J2-OFF diagnostic、实时电气/温度确认和新的 one-shot 授权；
不 retry、不 autochain、不自动恢复、不在同次授权切换 profile。C 未完整 finalized 或白恢复失败，
都不得进入 T。完整初始门禁曾满足，V8 C 已在 J2 OFF 下 app-only 刷入并回读 PASS；但第一项
diagnostic GET 暴露 `/version.profile` 缺失后安全停止，未进入可见 C。V10 已修复、重建、重封并
离线 deep-validate，尚未刷入；当前 ESP32 USB/COM8 未枚举。因此四项仍为 `0/4`。下一步只能
保持 J2 OFF、重新识别 MAC `a4:cb:8f:d9:fc:d4`，刷 V10 C 应用区、独立回读并生成绑定 V10/current
boot 的 fresh `4 GET / 0 POST` diagnostic；完整 PASS 前不得打开 J2，也不生成可见 token/claim。
