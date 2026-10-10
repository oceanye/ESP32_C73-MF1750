# MF1750 E6 明度波形探索证据报告

日期：`2026-09-05`  
适用对象：MF1750 1024×600、双 `SPD1657B rev 0x04`、当前 E6/P2-C 实验线  
状态：`OFFLINE_ANALYSIS_COMPLETE / LIVE_NO-GO / qualified=0`

这份报告回答一个问题：在当前彩色反射式电子纸上，怎样探索“同一色相的明度”，而不是把背光亮度、灰度轴或空间混色误当成明度。所有外部资料只用于说明可能的物理机制和数据模型；它们没有提供当前 `SPD1657B rev 0x04` 的可写 ABI，也没有授权把外部参数写进当前控制器。

## 1. 术语和验收对象

- **明度**：同一色相、同一 track 内的感知明暗层级。本项目目前用相机 JPEG 推导的 camera-relative CIE Lab `L*` 做相对指标，同时约束 `a*/b*` 和色相角不能漂移。它不是绝对反射率，也不是厂商规格。
- **灰度**：接近中性轴的无彩色序列，是明度的特殊子集。它不是当前首要实验对象；当前首要对象是彩色端点之间是否存在可重复的明度差。
- **亮度/发光亮度**：当前面板无背光，不能按 LCD 的背光亮度调节来定义目标。若以后测量绝对反射亮度，需要独立光度/反射率仪器；本轮没有这种仪器。
- **单像素明度槽**：必须由单像素、无抖动、无邻域混色的稳定终态支持。一次性过渡态、历史残留、局部条纹和空间抖动不计入 256 槽。

## 2. 当前本地证据给出的边界

### 已有事实

1. P2-C ordinal 1 已严格完成 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`。相机能稳定定位 64 个 ROI，当前低曝光采集无高光裁切，说明测量链可以继续用于相对明度筛选。
2. 端点颜色是可见的；但端点可见不等于明度族。当前 optical report 的 CS1 四位置门只通过 code `2/3/5`，CS2 八码初步门通过，CS1/CS2 的跨控制器匹配也未通过。
3. CS1、CS2 都出现 code `1↔7` 的 camera-relative 同色相明度候选，但证据只有一次 action，尚未通过 HOLD、独立 fresh-white reconstruction 或重复链，因此仍为 candidate。
4. 历史 `STABLE_CODE0_LUMA_LATIN_V3` 的 CS2 `L*` 跨度曾为 `7.059`，同一 target 原位重复后只剩 `2.157`，保留率 `30.56%`；controller-local centred `|ΔL*| P95=4.647`。这否定了“原位重复同一 target 会保留明度”的机制，但没有否定“一次构色后避开候选区的 HOLD”。
5. 当前 HOLD 代码审计为 `BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE`；不能把局部 HOLD 当成已可用的明度发生器。

### 本地可操作机制

| 机制 | 能改变什么 | 当前证据 | 结论 |
|---|---|---|---|
| 完整、已知兼容 profile 的不同 endpoint | 终态粒子分布，可能同时改变色相和彩度/明度 | P2-C 端点图；`1↔7` 为候选 | 当前最低风险、最应优先验证 |
| `source → middle → target` 历史构色 | 利用粒子历史产生一次性光学差异 | V3 有一次性 `L*` 跨度 | 只能作为 candidate，必须接 HOLD 和 fresh 重建 |
| 固定完整 profile 的 target 刷新剂量 | 可能改变有效驱动冲量 `V×t` | 计划中有 `1/2/4/7/10` 阶梯 | 可做有界诊断，先证 3 阶再扩展 |
| 已知 profile 下局部 HOLD/避开候选区 | 保存已经生成的终态 | HOLD 链路已离线设计 | 是保持机制，不是明度生成机制；现场电气门仍未通过 |
| 直接编辑 R20/R21 phase/record | 可能改变相位或时间 | `799/704` 结构只完成几何绑定 | 字段语义未知，继续阻断 |
| 改 VCOM、高压、PLL、header | 可能改变电场或全局驱动 | 没有当前芯片安全合同 | 禁止 |
| 空间抖动/条纹/邻像素混色 | 视觉平均色 | 现有工具支持渲染实验 | 不增加单像素明度资格，后置 |

## 3. 参考项目和其他芯片 waveform 的可迁移结论

### E Ink Spectra 6 / Ripple 官方资料

E Ink 公开资料把 Spectra 6 的基础显示描述为黑、白、红、黄、蓝、绿六色；2025 年 Ripple/第二代 waveform 的 3-bit、八原生色和 T2000 扩展属于新的 waveform 架构与兼容芯片组合。[Spectra 6 品牌页](https://www.eink.com/brand/detail/Spectra6)；[Ripple 与第二代 waveform 公告](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)。

可迁移的是：颜色数量和明度细节取决于“墨水粒子 + waveform + 兼容 TCON/驱动芯片”的组合，而不是像素数据码本身。不可迁移的是：3-bit 编码、Ripple 波形、T2000 行为和任何公开宣传的新增颜色，不能证明当前两颗 `SPD1657B rev 0x04` 支持相同 ABI。

### EPM-100 runtime WBF 合同

E Ink/Digital View 的 EPM-100 资料展示了成熟 runtime-waveform 系统的完整闭环：把完整 WBF 装入专用 buffer，提交解析命令，等待 ready，再按温度选择映射 waveform；源/VCOM 电压是独立参数。它还区分易失 waveform 更新、温度 override 和持久化路径。[EPM-100 USB Programming Guide](https://shopkits.eink.com/en/download/0223020711rk338873/Content%20transfer%20programming%20guide.pdf)。

这对当前项目的价值是定义“证据应该长什么样”：payload 接收、解析完成、温度映射、状态返回和电压设置必须分别有证据。它不能提供当前 `0x20/0x21`、`799/704` 或 11-byte record 的字段解释，因此不能移植命令号、长度或电压。

### ED2208-DOA / `.eink` Initial Data

ED2208-DOA 用户手册和 PaperColor 资料证明某些同类彩色模块有厂家 `Initial Data (.eink)` 写入路径，但没有公开容器格式、LUT record、温区表、命令 ABI 或 runtime 语义。它证明“厂家校准数据可能存在”，不能证明 `.eink` 等同于当前面板的 runtime LUT。[ED2208-DOA User Manual](https://shopkits.eink.com/en/download/0224112222me459948/User%20Manual_4%27%27%20Spectra%206%20ePaper%20Display%20%28ED2208-DOA%29.pdf)；[M5Stack PaperColor](https://docs.m5stack.com/en/core/PaperColor)。

### 开源 Spectra/邻芯片项目

- `Modos-Labs/Glider` 的公开说明指出 Spectra 6 的 WBF 可以按目标灰度组织 waveform，并提供 e6 翻译工具；这说明“目标终态对应 waveform”是合理数据模型，但它不是当前控制器的 loader 或 profile 证明。[Glider waveform notes](https://github.com/Modos-Labs/Glider)。
- `A223D/colourEpaperWaveshare` 对 SPD1656 彩色模块记录了 4-bit 像素码和 7 色/未公开第 8 码的实际传输方式。它能帮助理解“像素 code 只选择目标入口”；它不能说明 code 代表明度，更不能移植到 SPD1657B。[SPD1656 colour e-paper guide](https://github.com/A223D/colourEpaperWaveshare)。
- 单色/三色控制器的开源 LUT 项目（例如 SSD1677 guide）通常把 LUT 拆成电平、VCOM pattern、phase timing、重复次数和电压控制字段；它们说明明度常通过粒子运动的时间/冲量获得，但这些字段属于另一个 controller ABI。[SSD1677 custom LUT guide](https://github.com/open-x4-epaper/community-sdk/blob/main/libs/display/EInkDisplay/doc/SSD1677_GUIDE.md)。

### 论文给出的物理机制

公开研究对电泳显示的共识是：灰阶/明度来自带电粒子在微胶囊中的空间分布；电压极性、脉冲持续时间、激活阶段、参考极限状态和写入阶段共同决定最终反射状态。常见流程是 erase/reset → activation → write，且需要 DC balance 和统一参考态，否则同一目标会因历史不同而漂移。[Driving Waveform Design Based on Optimized Particle Activation](https://pmc.ncbi.nlm.nih.gov/articles/PMC7281290/)；[Driving Waveform Design Based on Driving Process Fusion](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2021.723106/full)；[High-Frequency Voltage for Three-Color EPD](https://pmc.ncbi.nlm.nih.gov/articles/PMC8777687/)。

这些论文支持三条探索原则：

1. 明度实验必须固定 source/target 历史或从 fresh white/reference state 开始；
2. “驱动冲量”可能由电压、时长、重复次数共同形成，不能只看 frame code；
3. 一个一次性的中间状态不能直接计为稳定等级，必须经过 fresh reconstruction、保持和位置重复。

论文中的具体毫秒数、电压值、相位数量不能写入当前控制器。当前项目只借鉴机制和判读方法。

## 4. 针对当前芯片的明度探索排序

### A. 首选：完整 endpoint 的 controller-local 明度链

先固定一条候选色相/track，在同一 controller 内比较完整 profile 的终态，不改 LUT、不改电压、不改未知字段。P2-C 的 code `1↔7` 只能作为待复核 candidate，跨 controller 匹配未通过。2026-09-06 勘误：缺边缘的几何拟合输入是 code 5；code 7 是布局 background transport code，不可将这两项混称或授予白色资格。历史 P1 的 C0/C6/C1 暖色链和 fresh-bound history mechanism 可作为候选，但都必须重新绑定 fresh white 和当前相机设置。

验收顺序：

1. 每个 controller 各自做位置平衡 4×8 atlas；
2. 对每个 code 计算 ROI 内 `L* / a* / b*`、色相角、位置离散度；
3. 只保留色相漂移小且 `L*` 单调的 code 组；
4. 先证明 3 阶，再扩展 5 阶，最后才讨论 10 阶；
5. 每个候选都进入局部 HOLD 和独立 fresh-white reconstruction。

这条路径回答的是“当前已知波形端点能否提供彩色明度层级”，信息量最高，风险最低。

### B. 次选：完整 target 的剂量阶梯

对已经通过 A 的单色相 profile，只改变完整、正常结束的 target 刷新次数，粗测 `1/2/4/7/10`。每次从相同 source/reference 开始，保持温度、曝光、机位和 frame 固定。只有出现单调、可分辨、可重建的 `L*` 变化，才细化为 3/5/10 档。

V3 的同 target repeat 已说明“重复刷新”会快速收敛，因此剂量阶梯不能在同一终态上盲目叠加；每一级必须有明确 source/reference 和独立 action 身份。

### C. 必需的保持链，但不当作生成器

一旦 A 或 B 得到候选，先验证构色后避开候选区的局部 HOLD 是否保持 `L*` 和色相。HOLD 通过只说明“终态能被保存”，不能直接授予明度资格。当前 HOLD 的电气状态证据门仍是阻断项。

### D. 暂停：R20 phase family / runtime LUT 编辑

当前 `R20/799`、`R21/704` 的结构和发送长度已部分绑定，但没有证据说明 11-byte record 中哪一字段只控制 phase duration、repeat 或冲量；也没有证明 header、VCOM、PLL、高压字段可安全修改。没有同代 loader/parser、单变量厂家 profile 差分或完整总线接受证据前，不生成 byte-level 明度枚举固件。

### E. 明确排除：邻芯片电压、VCOM 和公开专利数值

它们可作为物理背景，不能作为当前芯片控制器参数。把论文或 SSD1677/EPM-100 的电压、命令、时序直接写入当前板，会同时破坏 waveform 身份、DC balance 和安全恢复链。

## 5. 下一轮应产生的可审查结果

离线阶段先生成以下材料，不访问设备：

- `controller × hue-track × code` 的 endpoint inventory 模板；
- 3→5→10 明度状态机，明确 `candidate → stable-3 → stable-5 → stable-10 → cross-controller matched`；
- 每个候选的 fresh-white、HOLD、fresh reconstruction、5/60/600 s 保持证据槽位；
- 统一相机-relative Lab 报告，分开记录 `ΔL*`、`ΔE76`、`ΔE00`、色相角和位置离散；
- 供应商问题清单：精确 `SPD1657B rev 0x04 + MF-17506` 的 waveform 文件、温区表、3-bit/Ripple/T2000 兼容性、controller-local recipe、Initial Data/WBF/runtime ABI；
- 对所有外部数值加 `NON_PORTABLE_REFERENCE_ONLY` 标记。

现场仍必须从 retained clean white、fresh COM/IP/MAC/boot 和同 boot J2-OFF diagnostic 开始；当前 P2-C ordinal 1 的 live mutation 放行已经结束，不能继承本轮身份。

## 6. 当前判定

当前最有希望的是“完整已知 profile 的彩色 endpoint → controller-local 3 阶明度筛选 → HOLD → fresh reconstruction”。历史构色只能作为候选来源，剂量阶梯是第二路线，R20/LUT/电压编辑仍然阻断。

这与当前观测一致：屏幕已有多种颜色，但尚未证明稳定的彩色明度族；`qualified=0` 保持不变。下一步应围绕明度证据闭环收缩实验，而不是继续扩大颜色枚举。
