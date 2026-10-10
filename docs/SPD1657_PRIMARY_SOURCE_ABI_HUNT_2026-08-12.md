# SPD1657 / ED2208 runtime-waveform 一手公开资料检索冻结报告

初始冻结日期：2026-08-12（Asia/Shanghai）；相邻控制器与 SPD1657 产品身份增量：2026-08-13

## 1. 结论

截至冻结时点，没有找到可公开核验的一手资料，能够把下列候选合同绑定到 SPD1657、SPD1657A、SPD1657B、E2802 或 ED2208：

- `0x20` 后跟 799 bytes；
- `0x21` 后跟 704 bytes；
- 每温度槽 2508 bytes；
- runtime-LUT 的温区选择、校验和、版本、提交/生效过程；
- 双控制器同时装载、失败回滚、掉电恢复和 BUSY/超时合同；
- 新增 3-bit 色码与具体 LUT 状态、相位、电压之间的映射。

公开资料能够证明“3-bit/八个主色”和“同一像素内通过粒子分层得到混合色”在物理和产品架构上可行；它们不能证明上述候选二进制 ABI，也不能提供可移植的电压、相位或 payload 数值。

最强的相邻控制器证据 SPD1656 反而给出明确的不兼容边界：在该器件中，`0x20` 是 220-byte LUTC，`0x21` 是 260-byte LUTB。不能因命令号相同，把 SPD1656 的字段或长度移植到 SPD1657/B。

因此，候选 ABI 目前只能标记为“来自本地样例/逆向的实验候选”，不能标记为“厂家已证实合同”。
需要同时纠正另一种过强否定：公开的一手展会页面现在确实存在 SPD1657 产品身份；缺失的是
datasheet/command/LUT ABI，而不是型号公开存在性。

## 2. 证据矩阵

| 证据 | 直接支持 | 不支持 / 不得推断 | 移植边界 |
|---|---|---|---|
| [Solomon Systech SPD1656 Rev 1.1 datasheet](https://www.waveshare.com/w/upload/b/bf/SPD1656_1.1.pdf)，2020-01，SHA-256 `1F3F5DB0600EE6E8133A4C31F9A3F59C1B5BFCC1A916BE98AE848EC64581DE07` | 640×480、3-bit/pixel、LUT0–LUT7、级联、10 个温度段；pp. 13/15/17/27--29 明确 `0x20`=VCOM `20×11=220`，每组为 `RP + 2-byte packed 8×2-bit LVL + 8-byte TP`，`RP=0` 为 End、`TP=0` 为 skip；`0x21`--`0x28` color 为 `20×13=260`，XON 又为 `20×10=200` | 本地 active raw 的 documented RP byte 在 328 records 中从未为 0；取反后虽出现零尾，但 11-offset 穷举中 byte0 与 byte6 并列，且没有 controller-side complement 证据。不支持 SPD1657/B 的 799/704/2508 或沿用字段、电压码 | 仅为相邻 SPD1656；精确布局用于形成可反驳假设，同时否定“命令号或个别宽度相同即可移植” |
| [Solomon Systech SSD1680A Rev 0.20 datasheet](https://v4.cecdn.yun300.cn/100001_1909185148/SSD1680A.pdf)，2020-02，SHA-256 `92CCB43DBCB847707FF907DE9989EA18214C968F3584B7493E7460D9268A43BC` | pp.14--15/29 直接定义四个 LUT、每 LUT 8 groups、每 group 4 phases；每组 `RP + 4×(VS|TP) + SR_AB + SR_CD = 7 bytes`，每 LUT 56 bytes；`0x32` 接收四 LUT+FR+XON 共 227 bytes，完整 WS 为 233 bytes | 本地虽同为 8 groups，但每 record 是 11 bytes；本地候选 sink 是 `0x20/799` 与 `0x21/704`，而 SSD1680A 的 `0x20`/`0x21` 分别是 Master Activation/Display Update Control。五种连续 7-byte 对齐在位域上都可解析，不能识别 offset 或补码 | 只支持“8 groups 在相邻 Solomon 架构中真实存在”；不支持把 4 phases 擅自扩成 8 phases，也不得移植 RP/VS/TP/SR、零值、电压、时序或命令 |
| [Solomon Systech SSD1683 Rev 1.0](https://files.seeedstudio.com/wiki/Other_Display/42-epaper/IC%20Driver%20SSD1683%20Datasheet.PDF)，2021-01，3931534 bytes，SHA-256 `77C188BA55B1B81129F8C0557F845FDE25CA97D73EE86ED1BA907EA87A0B5E9C`；[SSD1683A Rev 1.1](https://support.newhavendisplay.com/hc/en-us/article_attachments/41742409400983)，2023-03，2880342 bytes，SHA-256 `7946B986783B7C4FEBA2D388290BF6D36EC20D83F43EFFB538B85B8D4CAB7585` | 两版均直接定义 3-color `4 LUT×8 groups×4 phases`，每 LUT/group 为 `RP+4×packed(VS\|TP)+SR_AB+SR_CD=7 bytes`；R32 接收 227 bytes。`RP=0/SR=0` 为 skip；`0x20/0x21` 为 Master Activation/Display Update Control | 不是 11 bytes/group，不支持 8 phases；全文无 799/704/1503/2508。更新到 2023 的相邻公开架构仍未出现目标布局 | 扩充 8-group 反证的代际覆盖；不移植命令、字段或零值语义 |
| [Solomon Systech SSD1681 Rev 1.1](https://support.newhavendisplay.com/hc/en-us/article_attachments/41742572114967)，2021-04，2783721 bytes，SHA-256 `DA23B888CDC9B7F7FE1ECD2C2F500ADD5683B00C4C4116465CC78DEB530D07DD` | `12 groups×4 phases`，R32 为 153 bytes、完整 WS 159 bytes；同名 `RP=0/SR=0` 表示执行一次 | 与 SSD1683 的 skip 语义相反；不能用相邻同族字段名推断本地 `00/FF` | 直接证明同厂相邻器件的零值语义会变化，字段名相同也不能迁移 |
| [Solomon Systech SSD2677 Rev 1.0](https://files.waveshare.com/wiki/common/SSD2677_1.0.pdf)，2024-03，1066162 bytes，SHA-256 `A2245BBAEF593B14FC1CA9C42EA6DFCFB1EF6799A966246B5F23388B0F49CE2A` | 960×680 color/E5 Spectra3100 SE、2 bpp、programmable waveform、6 KB OTP；公开双芯 cascade 的 M/S# 与模拟电源/同步互连 | command table 不公开 runtime LUT write，未列命令/参数标为 reserved；`LUT_EN` 只说明 reset 时 OTP 自动装载。无 799/704/1503/2508/535、11 bytes 或 8 phases | 证明 2024 同厂彩色器件可以公开 programmable-waveform/cascade 架构而不公开 waveform ABI；不得反推 SPD1657 payload 或 CS transaction |
| [Solomon Systech bistable-display 产品分类](https://www.solomon-systech.com/zh-hant/product-category/bistable-display) | 公开目录可确认 SPD1656 产品能力 | 当前目录未列 SPD1657，不能据此证明 SPD1657 不存在，也没有 SPD1657 ABI | 目录级证据，不是寄存器规范 |
| [COMPUTEX 官方展品页：SPD1657](https://www.computextaipei.com.tw/en/product/CBA4659B8C39B7F72BDDBEB61C4033B7A51D2AFD55BCA758/info.html) | Solomon Systech 自填 company/model；标题为 `800 Source x 600 Gate E Ink Spectra 6 Color ePaper Display`，描述支持 800×600 active-matrix Spectra 6；页面修改日期 2026-05-29 | 无命令、寄存器、payload、温区、双控或恢复协议 | 直接闭合型号与产品定位；不能把官网当前目录未列出升级为“SPD1657 未公开/不存在” |
| [Touch Taiwan 官方展品页：SPD1657(E2802)](https://www.touchtaiwan.com/visitorProductDetail.asp?no=180553) | 提供 SPD1657 与 E2802 的公开名称关联 | 页面描述很少且无 ABI，不能扩展成 SPD1657B 合同 | 只用于名称关联 |
| [E Ink ED2208-GCA / EL073TF1 specification](https://files.seeedstudio.com/wiki/Other_Display/7.3-E6-color/7.3_E6_eInk_%20Display_%20module_%20Datasheet.pdf)，SHA-256 `9D6288C82EA836CF7699153D814CCEB0EBFFFBBC02D369D9DEFA3A47063926E3` | 800×480、六色、片上 RAM、OTP waveform、外部温度传感器；公开命令表含 `02/04/07/10/12` | 公开表未定义 `0x20/0x21`；“未公开”不是“不存在”的证明，也不能证明 799/704/2508 | 精确到 ED2208-GCA 面板公开接口子集；不等于完整芯片 NDA 规范 |
| [Good Display GDEP073E01 specification](https://www.good-display.com/companyfile/1507.html)，下载件 SHA-256 `205D39D249DBEB4E60C54E2DFB8E712B3B01AAB8C97BD9F4F1F83CD699985470` | p. 4：六色取决于 associated LUT、波形在片上 OTP；pp. 9–10：公开命令仅 `02/04/07/10/12`；p. 13：功耗测试使用 associated 25°C waveform，且特性只由配套控制器/波形保证 | 没有 runtime-LUT 上传 ABI；“25°C waveform”不定义 `WF20_25` 等文件名语法 | 模组供应商资料；支持“25°C 是一个波形测试条件”，不支持文件名解释 |
| [Good Display GDEP073E01 ESP32 sample](https://www.good-display.com/companyfile/1435.html) 与 [STM32 sample](https://www.good-display.com/companyfile/1436.html) | 提供 OTP 初始化、整帧 `0x10` 写入、`0x12` 刷新；代码另有 fast-init 参数组 | 没有以命令方式发送 `0x20/0x21`，没有 LUT payload；源码中的 `0x20` 是 `0xAA` 解锁数据或分辨率数据，不能误报为 command | 单控制器 GDEP073E01 邻接样例；其 magic init 数值不得直接移植到 MF-17506 双控板 |
| [Good Display 2025 specified-area sample](https://www.good-display.com/companyfile/1908.html) 与 [2026 partial-refresh sample](https://www.good-display.com/companyfile/2037.html) | 样例新增 `0x83` 窗口范围与局部区域写入尝试 | 没有 runtime-LUT；`0x83` 的注释/参数没有芯片数据手册交叉证明；局刷不等于 LUT 运行时装载 | 官方托管但无控制器归属和 ABI 规范，不能作为 SPD1657/B 权威寄存器依据 |
| [GxEPD2 GDEP073E01 固定源码](https://github.com/ZinggJM/GxEPD2/blob/de82887e77a78528ea386e68bba2cb0291d2c319/src/epd7c/GxEPD2_730c_GDEP073E01.cpp) 与 [v1.6.0 修复提交](https://github.com/ZinggJM/GxEPD2/commit/9e71db5) | 第三方库从 v1.6.0 起有意把 native code `4` 标作 orange；v1.6.9 的 14-event init 与 Good Display 三份官方 binary 精确一致 | 官方产品、规格、2024 源码和 2026 binary 均只交付 `{0,1,2,3,5,6}` 六码；code 4 没有厂家定义；源码又明确写 controller unknown | 仅为 800×480、one-CS API 的 exact-panel 冲突线索；不得移植到 MF-17506、不得命名 mode-1 category，也不证明物理单控制器合同 |
| [Good Display Image2LCD V1.1](https://v4.cecdn.yun300.cn/100001_1909185148/Image2LCD%20Software%20Bitmap%20Conversion%20Instructions%20V1.1.pdf)，SHA-256 `580247D82AC0CF49E2F68A0E8911AE2BD813977B696C8082CDFB922888504E81` | 明确区分 six-color（无 orange）和 seven-color（含 orange），并把 GDEP073E01 列为 six-color | 没有 native nibble 4 定义，更没有 runtime-LUT ABI | 厂家图像转换资料，可约束 palette 口径，不能定义控制器内部未交付色码 |
| [Good Display 托管 JD79661AA V1.0.4](https://v4.cecdn.yun300.cn/100001_1909185148/JD79661AA%20V1.0.4_20230720%20spec.pdf)，3386370 bytes，SHA-256 `FC18052E01FE9D0ABA00E15C9C87919659B44D0D2132F8D538BC2045BAC67625` | 4-color 邻接控制器公开资料；PSR 说明 `LUT_EN=1` 选 register LUT、0 选 MTP；p.64 的 Example 1/2 两个时序图均标出同一 `LUT0 (20h)` | 30 项正式 SPI 表没有 `0x20/0x21/E9`；图示不给 register-write 参数长度、payload 格式或 LUT1；PDF 内部 title 仍为旧 `EK79029DS` | 只能证明 JD79661 文档公开子集存在未展开的 register-LUT 概念；不能移植为 SPD1657/E2802 的 799/704 ABI |
| [Waveshare 官方 13.3-inch E6 dual-controller code（固定 commit）](https://github.com/waveshareteam/e-Paper/blob/7523aeaff09219e66478ef1603f0cc6618a48377/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/c/lib/e-Paper/EPD_13in3e.c) | 独立 master/slave CS、双方收帧/刷新/上下电、master-only 模拟电源配置；公开色码含 0/1/2/3/5/6 | 无 `0x20/0x21` runtime-LUT、无候选 payload、无失败回滚；BUSY 循环本身无超时 | 证明一种相邻双控拓扑，不证明 MF-17506/SPD1657B 的装载顺序 |
| [E Ink Ripple / second-generation waveform 官方新闻稿](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)，2025-03-27 | 新 waveform architecture + 升级 3-bit chipset 将 Spectra 6 扩展到八个主色；Solomon 等厂商提供兼容芯片 | 无芯片型号绑定、命令号、payload 格式、温区或恢复合同；不能猜测色码 `0x4/0x7` | 产品架构级正证据，不是 ABI 证据 |
| [E Ink 作者论文 “Color Electrophoretic Displays”, IDW 2023](https://confit.atlas.jp/guide/event-img/idw2023/EP1-01/public/pdf_archive?type=in) | Spectra 6 每像素有六个基础光学状态；green 由两类粒子在观察侧混合，blue/black 依赖精确分层；更多混色可由高级驱动算法产生，商业六色系统仍常用 dithering 补色 | 不给控制器命令、完整相位时序、lot-specific waveform 或可移植电压值 | 证明 in-pixel mix 的物理可行性；不能直接生成安全 runtime LUT |
| E Ink 相关公开专利：[US20250191547A1](https://patents.google.com/patent/US20250191547A1/en)、[US20250201206A1](https://patents.google.com/patent/US20250201206A1/en)、[US20240402562A1](https://patents.google.com/patent/US20240402562A1/en)、[WO2022251218A1](https://patents.google.com/patent/WO2022251218A1/en) | 多粒子分层、波形与中间光学状态的技术路径 | 无 SPD1657/B 命令 ABI；专利实施例数值不是具体量产面板的安全参数 | 仅用于方案空间，不用于直接上屏参数 |
| [Philips Apollo LUT 专利 US20070085819A1](https://patents.google.com/patent/US20070085819A1/en) | 一项特定 Apollo ASIC 设计明确给出 11-byte frame instruction：前 8 bytes 为 32 个 2-bit voltage selectors，后 3 bytes 为 row time、inter-frame delay、frame count | 只证明另一个控制器存在 11-byte 记录；本地 raw/complement 数据均不能完整满足该专利的字面示例，不能据此给本地 11 个字段命名 | exact-width adjacent clue；不得移植字段、码值或 `FF FF` 语义 |
| E Ink LUT 建立专利 [TW201321879A](https://patents.google.com/patent/TW201321879A/en) / US9196200B2 | 给出一种 compact example：2-bit voltage、4-bit duration、约 90 bytes/temperature interval | 没有定义 11-byte GROUP record；与本地 88-byte category 数值接近不等于格式相同 | 只作编码方案空间线索，不用于解释本地字段 |
| [Good Display GDEW0154M09 V2.0 specification](https://www.e-paper-display.com/GDEW0154M09%20V2.0%20Specificationb92d.pdf?fileId=944&flag=all&id=51626c48-6583-407b-b60a-216032d33f35&method=picker&v=2.zip)，观测下载件 SHA-256 `F127343DB2B48A56215D253F7CB871892C882A744D540B9EC86FD75E458F8C88` | 相邻器件同样使用 8 GROUP，但 group frame-rate 位于独立 R25H 的 M/N 字段，R26H 另选 LUT states | 不支持本地 11-byte record 内任何 timing/drive field；恰好构成“GROUP 标签不能定位字段”的反例 | 相邻结构反证，不是 SPD1657/E2802 ABI |
| [Zephyr ED2208-GCA upstream driver](https://github.com/zephyrproject-rtos/zephyr/blob/1eb22813169081bfaa0a2c2e9739a90ab5dca0c3/drivers/display/display_ed2208_gca.c) | 公开实现使用已知 OTP 初始化/刷新并采用超时和 active-low BUSY 语义 | 没有 `0x20/0x21` command；文件中的 `0x20` 只作为解锁序列数据 | 不是 E Ink/Solomon 一手规范，仅作为公开实现的邻接 negative evidence |

SSD1681/1683/1683A/2677 四份本地 PDF 又由
`tools/mf1750_solomon_adjacent_family_audit.py` 独立固定 whole-file identity、page count、16 页
normalized text hash 与 required anchors。metadata-only 报告为
`.test-output/offline/mf1750_solomon_adjacent_family_audit_20260813.json`，13631 bytes，
file/canonical SHA-256=`94e46efb414a2ca8358e659b4458e6c308b4f5a8111caeed8b0f7779b05a9999` /
`c090d25412b609524495217e41a7ffaf7e911314b932486bce40cb614e8da8f2`；它不输出 PDF 全文、
waveform bytes 或可执行载荷，也不授权硬件实验。

## 3. 候选合同判定

| 候选项 | 公开一手证据状态 | 当前标签 |
|---|---|---|
| SPD1657/B `0x20` + 799 bytes | 未找到；SPD1656 的同号命令明确为 220 bytes | `unknown / experimental candidate` |
| SPD1657/B `0x21` + 704 bytes | 未找到；SPD1656 的同号命令明确为 260 bytes | `unknown / experimental candidate` |
| 2508-byte temperature slot | 未找到公开格式说明 | `unknown / local reverse candidate` |
| 10 temperature slots | SPD1656 有 10 段，但无 SPD1657/B 继承证据 | `adjacent-only; no portability` |
| 3-bit / eight primary colors | E Ink 官方证实架构能力 | `architecture-confirmed; ABI-unknown` |
| 色码 `0x4`、`0x7` 的具体颜色 | 厂家资料未定义 `0x4`，只把 `0x7` 用作 clean；GxEPD2 v1.6.0+ 的 `4=orange` 是与厂家六色交付冲突的第三方 adjacent-panel 标签 | `unknown; third-party conflict is non-portable` |
| 双控制器 load/commit/recovery | Waveshare 只证明相邻双 CS 刷新拓扑 | `topology-adjacent; ABI-unknown` |
| voltage/LUT byte correspondence | 本地 535-byte 源码只直接标出 7-byte header、6 category 和每类 GROUP1..GROUP8；仅 header bytes 1..4 另有 PWR 绑定，11-byte record 内部字段仍未命名 | `lot/profile-specific; adjacent formats are non-portable; do not guess` |

## 4. `WFxx_yy` 命名语义

精确检索 `WF00_05.h`、`WF20_25.h`、`WF23_25.h`、`WF24_24`、`WF25_25` 和 `WF Tunning Tool AP`，并限定 E Ink、Solomon、GitHub、Gitee 等公开来源后，没有找到厂家发布的文件命名规则。

本地供应样例提供的事实仅为：

- `WF20_25.h`：文件头写有 E Ink Holdings Inc.、2026-01-06、version 1.0、`SIZE 842`；SHA-256 `0DD568CCA1D18CDD475A9EF5C7B7B2B56F11DC5ABEEEB5D478B28F7BCB65E821`；没有温区语义说明。
- 编译对象中保留 `WF23_25.h` 文件名和 E Ink/date/version 字符串；对象 SHA-256 `C75D23A0F290DEB8416619028284C53726BD399921A2DC0FFE043BEF7F227C5D`；没有命名规则。
- 样例还引用但未附带 `WF00_05.h`、`WF25_25`，另有 `WF24_24[5]` 的注释；这些引用不足以证明两个数字是闭区间、中心温度、profile ID 或生成批次。
- Good Display 规范 p. 13 只证明存在“associated 25°C waveform”这一测试条件，仍不能把文件名拆成温度上下界。

结论：`WF20_25`、`WF23_25` 必须作为 opaque profile identifiers。其适用温度和面板兼容性均为 unknown。

必须区分两种表述：

- **Unknown**：厂家没有公开说明文件名语义或合格温区。
- **Experimental guard**：主机侧若只在测得恰好 25.0°C、重新诊断且操作者重新确认后允许一次相邻 legacy-selector 实验，这是保守实验控制，不是厂家 qualification，也不是对文件名的解释。

## 5. Good Display 官方下载件静态核验

全部下载到系统临时目录，未复制进项目、未连接设备、未访问串口、未刷写。

| 页面 / 文件 | 页面日期 | 下载件 SHA-256 | 静态结论 |
|---|---:|---|---|
| [ESP32 sample](https://www.good-display.com/companyfile/1435.html) | 2024-03-04 | `3C0136E7BFC45925D134F3DD550813FAAC4DC7FD2023DAA382DB88649099A430` | 源码；OTP 初始化/整刷/fast-init，无 runtime LUT |
| [STM32 sample](https://www.good-display.com/companyfile/1436.html) | 2024-03-04 | `2491EF5FD8D70E568F1FDD454C6A52EAD4DEBD64DCBA0C49DEBB5447B474308E` | 源码与构建物；命令流与 ESP32 同类，无 runtime LUT |
| [GDEP073E01 specification](https://www.good-display.com/companyfile/1507.html) | 2024-05-14 | `205D39D249DBEB4E60C54E2DFB8E712B3B01AAB8C97BD9F4F1F83CD699985470` | 24 页模组规范；公开命令表无 LUT upload |
| [Specified-area sample](https://www.good-display.com/companyfile/1908.html) | 2025-08-25 | `1A344C7F9CBEBC1A1EFC0C828A47AC3E08F8F2756C7EE9DDD74264489B799FE1` | `0x83` 区域写入尝试，无 LUT upload |
| [Partial-refresh sample](https://www.good-display.com/companyfile/2037.html) | 2026-03-30 | `2D34AF51AC6D8392F80F55894D3D7C3B8B93BA78DAFEBA6CBDF542E3F210C95A` | 在旧包基础上继续修改并附加 OTP read 尝试；无 LUT upload，不能作为完整芯片规范 |
| [ESP32E6-E01 firmware](https://www.good-display.com/companyfile/2071.html) | 2026-06-04 | `8EAFF3E3A68DA354C6AD1FC62A1D6B6EE2144DF64198AB35A544E5A96F868A96` | ZIP 仅含 Wi-Fi/USB/SD 三个 `.bin`，无源码或 ABI 文档 |

局刷包的存在只说明模组供应商公开托管了一个区域更新尝试。它不能补足 `0x20/0x21`、799/704、2508-byte slot、双控提交或恢复合同。

对最后一项三个 binary 的后续 cross-image 指令审计，已恢复共有 E6 OTP init、typed
command/data helper、800×480 的 192000-byte packed display、WiFi/USB 六 tag→4-bit code
nibble packing，以及 SD BMP success→init→display 的业务可达链。它还把 SD-card
GPIO21/13/47/48 SPI 与面板 GPIO12/11 bitbang 明确分开。这个增量纠正了初轮“面板路径
unknown”的分析边界，但恢复出的 typed command 集合仍无 `0x20/0x21`，也无 704/2508-byte
runtime payload 或双控，因此不改变本报告的 ABI negative finding。可复现报告为
`.test-output/offline/good_display_esp32e6_cross_image_panel_audit_20260812.json`。

另一个固定提交的第三方交叉审计比较 GxEPD2 v1.5.9、v1.6.9 与上述官方 binary。v1.5.9
的 GDEP073E01 映射曾把 yellow/orange/red/blue/green 依次写成 `5/6/4/3/2`；v1.6.0 的
release 明称修复 native mapping，v1.6.0 源码（25918 bytes，SHA-256
`33af38449ce8fcf6c0afd06b3d832dd6a2670256bd76fabf14df699c6ff8a45b`）及 v1.6.9 都把
orange 标为 code `4`。但 Good Display 的产品页、规格、Image2LCD V1.1、2024 官方源码与
2026 binary 均只承诺/发送六码 `0/1/2/3/5/6`，没有 code 4。这是可复现的
`GDEP073E01_CODE4_ORANGE` **冲突假设**，不是厂家合同；更不能覆盖 MF-17506 真屏已观察到的
`code4 ≡ code7` 或据此命名任何 mode-1 category。审计报告
`.test-output/offline/gxepd2_gdep073e01_source_audit_20260812.json` 的 file/canonical SHA-256
为 `8fb4638154ec6bc6ea94827a04abcfac5b3bd5777eddb1a8047de6e3d9d786d2` /
`89d0a0fb4028e68ba5e3b7e2658e5b0a6fd4965b42f102ae569f410b10fce87a`；其中 one-CS、无
runtime upload 和 OTP refresh 都只描述这份固定邻接实现，不是 MF-17506 物理合同。

为避免仅凭源码注释下结论，官方 2024 ESP32 ZIP 又做了独立 source↔2026 binary 合同审计。
ZIP（191983 bytes，SHA-256 `3c0136e7bfc45925d134f3dd550813faac4dc7fd2023daa382db88649099a430`）
中的 header、`Color_get`、六码纯色函数和 384000-tag image 与三份 binary 的 typed 结果在
native code set 上逐项一致，都是 `[0,1,2,3,5,6]`；`7` 仅为 `Clean` symbol，未进入 converter、
image、纯色 demo 或 binary code set。源码/binary 的输入 tag 集不同，说明 tag 是各自转换格式，
不能误当 native code。metadata-only 报告
`.test-output/offline/good_display_gdep073e01_source_binary_contract_audit_20260812.json` 的
file/canonical SHA-256 为 `03d8d3406cf4b428dd07280d619bfd3928c8ecf6bc8c5da19e732e474c178415` /
`fdab7df75d064ea3a584d2cfa4e124dfd39c7979221e88b74d4a96401cfb5446`。

JD79661AA 的 78-page 官方 PDF 则把 `79661.csv` 的邻接线索进一步限定：正式 register table
共 30 项，不含 `0x20/0x21/E9`；p.64 的两个 example timing diagram 均标有同一个
`LUT0 (20h)`，没有参数长度或格式；`0x21` 的出现只是 voltage-code 值，`E9` 全文为 0。
第 62 页只公开 6144-byte MTP 及其中 5600-byte compressed-LUT 区，不能据此推出 register-LUT
payload。GxEPD2 43-byte init
的 15 个 command groups 中只有 8 个 opcode 在正式表，且其中 7 个参数数量精确一致；手册不能
独立支持整条第三方 init。schema-2 报告
`.test-output/offline/jd79661aa_datasheet_cross_audit_v2_20260812.json` 的 file/canonical SHA-256
为 `327628422c989f719e9e0e8aa5a2225be0718b93cc6bfd52fa05dbcfd85043ac` /
`a82433e1db1941c6937d064a657b8889b98ea589227ae696858045d9ae8b34ef`；下载器现只接受三个
固定 HTTPS URL、拒绝全部 redirect，并在读取前要求 final URL exact match 与 HTTP 200。它只
约束 JD79661 adjacent family，不改变 SPD1657 ABI negative finding。

IAR E2 边界现在必须按两层表述。

第一层是**已恢复的 exact-corpus observed dialect**，不再只是三份对象的 exact-offset
projection。无偏移扫描器在 32 个 identity-pinned MSP430 UBROF11 对象（3 份交付物 + 29 份
公开第三方对象）中解释了 139 条 E2 records，其中包含先前三对象语料没有覆盖的 9 条
`interrupt` root records；107 个 caller-name references、126 个 direct-callee references 全部
解析，9/9 interrupt roots 均有 `??INTVEC` alias，交付对象的 caller/callee sets 又与独立 machine
relocation graph 相符。固定的旧官方 XLIB 6.1.3.56 对 32/32 未修改原件均复现
`Unknown tag: E2`，对仅在临时目录移除已识别 E2 records 并重算 CRC 的 32/32 projections 则均能
列出 ENTRY/EXTERNAL。由此可复现地支持“本批 MSP430 对象共享一种 observed E2 dialect”，但
projection differential 仍不是原件的 native parse，更不是可链接、可刷写的替代对象。

29 份公开对象只按 metadata 使用，并固定到三个 GitHub commit：

- `andersonethan44/RemoteControlledCar` commit
  `eb4e81be84cbd0fb889a587a1423420c86175278`，19 objects，object-manifest SHA-256
  `8b6e569972f77e0fdce0125cf60d4f4ebbe9d936c737dd53b24c2570024cbe69`；
- `hrishikeshkarande/MSP430G2453_IAR_Quantum_Leap` commit
  `82c5d7e29f6250a89d35913df9cf4d8ac4cd38f1`，6 objects，object-manifest SHA-256
  `e9db62eb68188fda956abfc82a9de8f86f3f718cce1d837dfabc4f0008942ba8`；
- `kevinbird61/2015-MSP430-IAR` commit
  `e5b45ca63c21b469ddd2b830e994f4bd4d0d4dc1`，4 objects，object-manifest SHA-256
  `5e5bab1f6a8d10c22471bd2ea89ed097ab13b788c993501928e22138a4b7b7e7`。

29-object corpus-manifest SHA-256 为
`8a0708b799e8065634a3d611ab2978c6fc82d6829cc8efef28d04bf6f241957a`。三个固定 commit 均未找到
`LICENSE`/`COPYING`，因此不推断许可；报告只发布对象 metadata/hash，不再分发公开对象字节。

第二层仍是**未解除的官方 grammar / native-original 缺口**。恢复出的
`E2 + length + payload` framing、function/path/catalog 字段名称和角色均为 observed-corpus inference；
语料全是 MSP430、全都只有 `CSTACK`，没有多 stack、其他 root category/path kind、非零高位 name
reference 或非零 direct-call tail，因此不能外推成官方通用 UBROF11 E2 grammar。IAR
[MSP430 XLINK manual](https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/infocenter/xman.ENU.html)
只说明 UBROF11 新增 stack-usage 信息；官方
[XLINK release notes](https://updates.iar.com/FileStore/STANDARD/001/000/590/ew/doc/infocenter/xlink.ENU.html)
只证明 stack-usage analysis 始于 6.2.0.62、EW25659 的 `Unknown tag:E2` 在 6.3.4.78 修复，以及
UBROF11.0.1 interrupt stack-usage 另有 6.3.1.71 修复历史，并不公开 byte grammar。2005 年的
[UBROF record-tag note](https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/UBROFRecordTags.pdf)
早于 UBROF11，也不给 E2 bytes。八个显式本地根的可读范围仍只找到已固定身份的 XLIB
6.1.3.56；没有合法取得并固定身份的 `xlib.exe >= 6.3.4.78`，所以 32 个未修改原件都还没有
新版 XLIB native parse。

完整 observed-dialect 报告为
`.test-output/offline/mf1750_iar_ubrof11_e2_grammar_audit_20260812.json`，canonical SHA-256
`d265097c3215da0cad256b185e9f061534d702b3c298e32b2cfc451850aac565`。availability 与旧
projection 报告仍保留为先前阶段证据；最小缺件仍是合法取得、固定身份的官方
`xlib.exe >= 6.3.4.78`，直接复核未修改原件的 tables。

11-byte record 语义也新增了一层本地直接证据，但没有跨过字段解释边界。交付
`EDP_init.c` 同时包含两张完整 535-byte 表，几何均为 7-byte header + 6 categories × 8
`GROUP` × 11 bytes，源码直接标出全部 48 个 category/GROUP 坐标。活动 initializer 在 `edp_init.o`
中与 `wf_data` 535-byte symbol 绑定、由交付 MAP 链接，交付 C 又在 `0x20` 后按序转发
**当时 global `wf_data` 中的**全部 535 bytes；
该 GBK 源码在 exact `for(i=0;i<535;i++)` 同行还直接注明“循环次数根据不同的芯片规格有所不同”。
这只固定源码作者把 535 视为芯片规格相关，而不是所有芯片的通用常量；它没有点名 mode-1、
SPD1657 revision，也没有给出 799/800 或双控制器目的端。
注释表在当前 translation unit 中不活动、完整字节不在该对象中，其用途未知，不能提升为 runtime
candidate。在这条交付 C / active `wf_data` 路径内，header bytes 1..4 在 PWR `0x01`
的 literal `0x07,0x00` 之后按序发送，但 byte 0 仅被 opaque forwarding；byte 5/6 虽分别注释为
VCOM/PLL 并赋给 struct field，却没有由该字段驱动专用 VCOM/PLL command 的证据。这些
legacy source 坐标名不能移植为另一条 ArmCC wrapper `plain[]` 路径的 header ABI。
源码把每条记录称为 `GROUP1..GROUP8`，并未证明 GROUP 是时间相位，更未命名 11 个内部字段。
另一个明确的 linked UART 路径会在 case 5 中调用 `Uart_save_wf_data`，先清空该 mutable global，
再无视形参 `buff_len` 而固定复制 `WF_DATA_LENGTH=535`。该 helper 本身不调用 `EPD_initial`
或 `0x20`，但它证明“compiled initializer 就是每次 upload 的 runtime contents”不成立；
前述 source dataflow 只能绑定当时 global contents 的原序转发。

公开资料只提供四个相邻比较面：Philips Apollo 专利的一种特定 11-byte instruction、E Ink
compact example 的 2-bit voltage + 4-bit duration、Good Display 另一控制器的 8-group 外置
R25H/R26H timing/state 结构，以及 SPD1656 的 VCOM 20×11 / color 20×13。它们分别提供
exact-width、编码方案、GROUP 术语反例和严格 geometry conflict；没有一个能把本地 record 的
duration/repeat、drive/polarity、voltage level、`FF` 或 chronological-phase 语义绑定出来，也不能
解释 mode-1 的 9 categories 或 DATA0/DATA1 配对。可复现报告为
`.test-output/offline/mf1750_spd1657_record_semantics_audit_v3_20260812.json`，canonical SHA-256
`12954f599d9c76a8c0d87dbe3270e1b39e206aceb64dce740333fb3647350316`；四类相邻格式均不得移植到
本地字段、payload 生成或上屏参数。

retained Arm ELF/AXF 的全量 command-sink inventory 又把旧 STM32 边界固定到 executable
层：34 个 `.o` 中唯一带立即数 `0x20` 的业务调用是 `edp_init.o::EPD_initial →
EPD_WriteCMD`，同函数有 `535`；七份最终 AXF 中六份保留这条路径，全部落到旧单-CS helper。
没有立即数 `0x21` command-sink，也没有与 payload/load 绑定的 `704/799/800/1503/2508`
常量；双控 helper 与这条 R20/535 路径没有调用绑定。报告
`.test-output/offline/mf1750_armcc_exec_sink_inventory_audit_20260812.json` 的 file/canonical
SHA-256 为 `0f1befae7fd64a729e79e970f46bc085813057282034fc8cabb662b656593412` /
`07e7a78fa01489e4eec0ae231a832cc74ad2b26cc6a9ddf4a8dc326e1d2a4e50`。这项 negative
finding 不否认其他版本可能存在 mode-1 loader，但排除了把本批 final AXF 当作同版双控证明。

官方 XLIB `LIST-OBJECT-CODE` 则直接补上 legacy IAR 的类型层。E2801/E2802 原件均声明
`DATA0 = const unsigned char[1503]`、`DATA1 = const unsigned char[704]`、
`dataBuff = unsigned char[2560]`；`EPD_Load_LUT` 的类型为
`void(uint16, uint8*, uint16)`，`ReadData` 为
`void(uint8, uint16, uint8*, uint16)`。完整 internal `t_push_rel` 扫描中 DATA0/DATA1
对应 sections 的引用数仍为 0。报告
`.test-output/offline/mf1750_iar_xlib_type_symbol_audit_20260812.json` 的 file/canonical
SHA-256 为 `608f54b06f12d9e393c6a3760b1ff3fc351db6ebd547e99f625754874fc5cd4a` /
`2e777a28642c683c0c131a025525a531f969b86734048b0dd79e435718c7f4b3`。这些类型直接证明
legacy 容器容量和 generic sender ABI，但对象中没有 799-byte named subobject，也没有
11/88/category/phase/voltage 类型，不能补写当前 800-byte wrapper 或内部字段。

公开的 runtime-waveform 相邻合同也出现了一个有用的工程反例。E Ink 下载站托管的
[EPM-100 USB Programming Guide](https://shopkits.eink.com/en/download/0223020711rk338873/Content%20transfer%20programming%20guide.pdf)
明确区分 WBF buffer、`0x003B` parse/apply、HRDY/status、volatile 生效、温度映射与独立电压
设置；[ED2208-DOA 用户手册](https://shopkits.eink.com/en/download/0224112222me459948/User%20Manual_4%27%27%20Spectra%206%20ePaper%20Display%20%28ED2208-DOA%29.pdf)
又证明 exact 400×600 kit 可写 `Initial Data (.eink)`，但没有公开容器或命令 ABI。详细边界见
`docs/EINK_ADJACENT_RUNTIME_WAVEFORM_CONTRACT_2026-08-12.md`。二者支持“运行时换波形在工程上
存在”，同时反证仅看到 opaque sender 不能声称 parser/commit/temperature/recovery 已闭合；
EPM-100 的命令号和电压示例不得移植。

本地 arithmetic 与 final-D43 审计又分别缩小了结构和最终 provider 边界，但它们是厂家交付物
的本地逆向，不是公开 SPD1657 ABI，因此不改变本报告的公开一手 negative finding。

### 5.1 固定第三方源码与索引增量（不进入厂家 ABI 证据）

本轮又在 `2026-08-12 +08:00` 固定并分类以下公开工件：

- [Modos-Labs/Glider README](https://raw.githubusercontent.com/Modos-Labs/Glider/ed94ef7fd95a42cfdcdaf5e5da1dcdd709122763/README.md)
  与 [Spectra-6 translator](https://raw.githubusercontent.com/Modos-Labs/Glider/ed94ef7fd95a42cfdcdaf5e5da1dcdd709122763/utils/waveform_translate/translate.py)，
  commit `ed94ef7fd95a42cfdcdaf5e5da1dcdd709122763`，文件 SHA-256 分别为
  `b30060802903d41948e452f3315700fa4f15fa25bdb59713a3754a9f6e9ad956` /
  `636398b4bf7e7966e0f3198cc54c9e70ab0b045b5d255fb8fc285172fcf97cf0`。它公开的是裸屏、
  外置 TCON/IWF 的 Spectra-6 状态编码翻译；仓库明确不是 E Ink 背书，且没有 SPD1657/E2802、
  `0x20/0x21`、799/704、`WFxx_yy` 或双 CS loader，不能转成 COG SPI runtime ABI。
- [codeart1st 社区 gist](https://gist.githubusercontent.com/codeart1st/dfa41e6426388dc929c719c4913297e3/raw/7d45eaa2389146ba1b582c8b94dccbf97995c93b/GDEP073E01-EL073TF1U5.md)，
  revision `7d45eaa2389146ba1b582c8b94dccbf97995c93b`，353209 bytes，SHA-256
  `fe360eb11ffdd4109fa11a168a17c1b524ad7910cca6fe9f42523264d90ae025`。它只是社区
  ED2208-GCA/OTP dump 自述；目标标识符与长度声明均未命中，字面 `799/704` 只出现在 OTP
  dump 地址文本而非长度，write table 也无 `0x20/0x21`，且没有测量、逻辑抓包或 runtime
  uploader。其 raw OTP 不进入本项目输出。
- Sourcegraph 的同名 `Upload_Temperature_LUT` / `EPD_Load_LUT` 命中落在固定的
  [IOsonata ED037TC1](https://raw.githubusercontent.com/IOsonata/IOsonata/483c00dbe3cbdd14b033c0399b34bbfdf998cef6/ARM/Nordic/nRF52/nRF52840/exemples/EInkDisplayDemo/src/ED037TC1.c)
  和 [zephray AC057TC1](https://raw.githubusercontent.com/zephray/driving-lcds/bf0a5c129f6dd3f654957116ad62a5b4d52e87bd/ac057tc1/epd.c)
  等旧屏通用源码；它们不是目标控制器，反而证明函数名本身不能作为 provider/ABI 身份。
- [COSCUP 2026 议程](https://coscup.org/2026/en/session/9KULK9/)所列讲者 GitHub 账号下的
  [tas-epd-lib](https://raw.githubusercontent.com/meteorTriangle/tas-epd-lib/14ea077109f2bef85081e7d64270493e585a9d18/readme.md)
  固定 commit `14ea077109f2bef85081e7d64270493e585a9d18`，README SHA-256
  `e1d1e6fa2f98ade9befc15897802ab47334572e1691764a8ec4f4df741109665`；支持列表是
  SSD1680/JD79661 等小屏，repo-wide 目标 regexp 为 0；议程未直接链接该仓库，两者关联仅为
  讲者账号归属上的推断，且该仓库只属于相邻生态而非 SPD1657 证据。

本轮 exact web/code-index 查询覆盖 `E5_3Bit_Mode`、`WF_DeCode_SIZE`、
`Upload_Temperature_LUT`、`EPD_Load_LUT`、`WF20_25`、`WF23_25`、`WF_SIZE 799`、
`0x031F/0x02C0`、`0x20 799 + 0x21 704`、`eload_3bits_M3_E2802`、`WF Tunning Tool AP`、
SPD1657/A/B、E2802/ED2208 及中英文 datasheet/LUT 组合；Sourcegraph 查询均显式使用
`context:global archived:yes fork:yes count:100 timeout:10s`。结果只回到既有展会身份、相邻
源码或作者自述，没有新增目标 ABI。部分 Sourcegraph 查询有 shard-limit caveat；GitHub 匿名
code search 要求登录且 REST 受 shared-IP rate limit，grep.app 遇到 checkpoint，Google Patents
端点本轮返回 503。因此结论严格是“在上述固定范围未找到”，不是互联网或厂家内部不存在证明。

## 6. 搜索边界与 negative finding

已覆盖：

- Solomon Systech 官方产品目录、公开 SPD1656 datasheet，以及 SSD1680A/SSD1681/SSD1683/
  SSD1683A/SSD2677 相邻控制器手册；
- E Ink 官方产品、新闻稿、用户手册、论文和公开专利，包括 compact LUT 建立示例；
- Philips Apollo 11-byte LUT instruction 专利；
- COMPUTEX / Touch Taiwan 官方展品信息；COMPUTEX 2026 页面已直接闭合 SPD1657 的
  `800×600 active-matrix Spectra 6` 产品身份，但不含技术 ABI；
- Good Display 官方 GDEP073E01 规范、STM32/ESP32/局刷/固件下载，以及相邻
  GDEW0154M09 的 8-group R25H/R26H 结构；
- Good Display Image2LCD 六色/七色指南，以及 GxEPD2 三个版本的固定提交源码；
- Good Display 托管 JD79661AA V1.0.4 controller PDF 与其 GxEPD2 exact-panel 实现；
- IAR 官方 XLINK release notes、MSP430 XLINK manual、EW430 update/SUA 页面、MSP430
  evaluation 注册边界与 TI SLAC050 匿名公开版本，以及 2005 UBROF record-tag note；
- 三个固定 GitHub commit 的 29 份第三方 MSP430 UBROF11 对象；逐对象固定 path、Git blob、
  SHA-256 和 manifest，并记录三个 commit 均未找到 LICENSE/COPYING、未推断许可；
- Waveshare 官方双控制器 E6 样例；
- Zephyr upstream ED2208 驱动；
- E Ink 下载站托管的 EPM-100 WBF update/temperature contract 与 4-inch ED2208-DOA
  `Initial Data (.eink)` 用户手册，以及 M5Stack PaperColor exact-panel one-CS 实现；
- 固定 Glider translator、社区 ED2208 gist、IOsonata/zephray/tas-epd-lib 相邻源码；
- 公开网页、Sourcegraph、GitHub/Gitee 精确文件名与命令组合检索，并逐项记录索引边界。

没有找到：

- SPD1657/SPD1657A/SPD1657B 的公开寄存器 datasheet；
- `0x20 799`、`0x21 704`、`2508` 与这些芯片型号同时出现的一手资料；
- E2802/ED2208 的 runtime-LUT payload layout；
- 能把本地 8×11 GROUP records 的 11 个内部 bytes 绑定为 phase、duration/repeat、drive/polarity、
  voltage level 或 `FF` 控制语义的同控制器资料；
- 双控制器 runtime-LUT 原子提交和失败恢复规范；
- `WFxx_yy` 文件名语法或对应温区 qualification。
- 无需注册/SUA、可匿名取得且已固定身份的官方 `xlib.exe >= 6.3.4.78`；projection 不解除
  native-original 缺口；observed MSP430 dialect 也不等于官方通用 E2 grammar。

明确排除：论坛转述、未经验证的博客命令表、Files=0/仓库仍称 forthcoming 的作者自述，以及
声称来自 NDA/泄露文档却无可核验工件的内容。它们不进入证据链。

## 7. 后续获得“可上屏合同”所缺的最小厂家资料

至少需要以下任一权威来源：

1. 精确芯片 revision 对应的 command/register specification；
2. 由厂家签发、带 panel lot / FPL / waveform version 的 runtime waveform binary specification；
3. 双控制器 master/slave load、commit、BUSY、掉电和失败恢复时序；
4. payload 长度、slot 数、温度边界、校验和/版本、VCOM/source voltage 对应关系；
5. 八个输入码到光学目标状态的映射及其合格温度范围。

在这些资料缺失时，公开一手资料最多支持继续做 fail-closed、一次一授权、可物理切断的实验；不支持把逆向候选升级为生产合同或自动链式扫描。
