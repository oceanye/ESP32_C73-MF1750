# E6 彩屏全彩路线调研与我们当前的进展（2026-09-19）

本页汇总：行业对 E Ink Spectra 6（E6）全彩的方案与评价、ACeP 与剂量轴两条
"中间态"路线的机制对比、以及本项目在这块 E6 面板上的实测进展。
实时状态仍以 `STATUS_HANDOFF.md` 顶部为准；本页不授权任何现场动作。

## 1. 行业对 E6 的"全彩"方案：空间抖动，没有第二条部署路线

- E6/Spectra 6 每像素**物理上只能显示 6 基色之一**（黑/白/红/黄/蓝/绿）。
  "Vivid Full Color""6.5 万色""百万色"均为把抖动模拟色计入的营销话术。
  依据：[InkJoy 的 Spectra 6 色域深拆](https://www.einkframe.com/2025/11/26/spectra-6-color-gamut-part1/)。
- 行业统一部署做法：目标色 → 各基色概率权重 → 有序抖动/蓝噪声/误差扩散。
  Samsung 的"250 万色"即按 14×14 像素区 ≈176 概率级推算（同上文）。
- 面板厂商配套同路线：[Good Display 的 E-paper Dithering Tool 把 RGB 图抖动成 6 色点阵](https://ecksteinimg.de/Photo/GD02009/EN-ESP32-133C02.pdf?_t=1768965681)；
  本仓库厂商示例 `参考资料/E6_73_sample code_V1.2_20250116/E6_73.c` 只有单色刷图
  函数，注释原文 "Reserve for dither image in future"——厂商自身无波形级多色方案。
- E6 的产品定位是海报/零售标牌（印刷质感替代），不是 LCD 级照片：
  [E Ink NRF 2025 公告](https://finance.yahoo.com/news/e-ink-showcase-spectra-6-130000249.html)。

## 2. 真正做过"全彩"的电子纸路线（对照用）

| 技术 | 机制 | 颜色能力 | 行业评价 |
|---|---|---|---|
| ACeP / Gallery 3 | 4 颜料（CMYW）单次序列内分层 + 停驻 | 号称约 5 万色（[IEEE Spectrum](https://spectrum.ieee.org/how-e-ink-developed-full-color-epaper)） | 已量产（2022 末起，reMarkable Paper Pro 等）；刷新 30s→最快约 500ms–1.5s（[实测](https://jackscogito.blogspot.com/2025/05/hands-on-review-of-remarkable-paper-pro.html)）；色域 E Ink 最大但慢、贵、寡淡（[对比综述](https://www.mygica.com/e-ink-color-technologies/)） |
| Kaleido 3 | 黑白墨水 + RGB 滤光片 | 4096 色 | 便宜普及但对比度/亮度代价大，与本屏无关 |
| Spectra 6 Plus (2024) | Oxide TFT | 仍 6 基色 | 刷新 25s→7s、分辨率提升，**不增加颜色**（[报道](https://einkopedia.com/e-ink-unveils-spectra-6-plus-display-offers-better-refresh-rate-and-resolution/)） |

关键事实：ACeP 的"粒子停在不同层级"是**厂商内部驱动能力，不开放为通用
明度旋钮**——产品仍从固定每像素色集合取色 + 抖动；多级停驻从未作为标准化
能力下放到 Spectra 系列（[InkJoy 同注](https://www.einkframe.com/2025/11/26/spectra-6-color-gamut-part1/)）。

## 3. ACeP 逻辑 vs 剂量轴逻辑（机制对比）

| | ACeP | 剂量轴（P3，本项目候选） |
|---|---|---|
| 控制变量 | 脉冲形状（模拟量，一次序列内） | 同一脉冲的重复次数（离散整数） |
| 色域来源 | 多颜料分层混色（CMY over W） | 单一色相态的密度/深度 |
| 中间态地位 | 设计好的稳定终点（一步到位） | 每步从"被记住的起点"出发（历史依赖） |
| 失效模式 | 慢（秒级到 30s/帧） | 落点随上一步状态漂移 |

**行业对历史依赖的评价**：历史依赖是电泳显示的教科书级难题——
"EPDs suffer from a severe history dependence during grayscale switching,
which results in annoying ghost images"
（[残像与波形设计研究](https://www.researchgate.net/publication/346358764_A_Convolutional_Neural_Network_for_Ghost_Image_Recognition_and_Waveform_Design_of_Electrophoretic_Displays)）。
行业里多次刷新是**消除**记忆效应的矫正手段
（[降残像驱动专利](https://patents.google.com/patent/US20180286318A1/en)），
而不是灰度发生器。因此行业对剂量轴的预期与本项目实测一致：
累积误差与状态漂移是主要风险，需要判决性实测而非推理。

## 4. 本项目在这块 E6 上的实测进展（全部真屏、证据封存）

1. **唯一验证的多级机制**：从白直驱 + 同族相邻码——红族 3 级明度阶梯
   （L\* 29.8→39.8→47.8，色相差 <5°，四位置一致，噪声远小于级距）。
2. **从白色谱 v0**：8 个 from-white commented 端点全部实测入库
   （红 3、蓝靛 1、棕 1、青 1、白 1），码空间已穷尽。产出
   `.test-output/offline/FROM_WHITE_SPECTRUM_20260918_V1/`（自封报告 + 阶梯色卡）。
3. **负面机制结论**：active code3 是历史无关暗吸引子（L\*≈14.7，收敛破坏色相）；
   active 白目标不能把彩色格刷白；commented 从彩色态出发（MAP）大多收敛暗态。
4. **XOR-3 发现（本项目独有）**：active-C7 白与 commented-C7 白视觉相同，
   但 LUT 表头电压+PLL 字节不同（电气不等价），面板"记得白的来历"，
   码轴随起点漂移（逐帧 20/20 拟合成立，几何/帧内容假设均证伪）。
   这是 Spectra 6 层面历史依赖的定量化实证，机制（控制器译码 vs 面板记忆）
   离线不可判。报告 `.test-output/offline/LH2_XOR3_MECHANISM_20260918_V1/`。
5. **诚实修正**：暗光 session 的"中性灰 4 级"已被较亮复测证伪（实为带色相深色，
   C\* 9.3–17.8）；对账 `.test-output/offline/LH2_MAP_SESSION_RECONCILE_20260919_V1/`。
6. **MAP 中间态现状**：物理存在（如红历史+code2 的中间档），但受码轴漂移与
   照明影响，尚不能升级为可靠阶梯。当前可信级数：红 2–3、棕 1–2（门边界）、
   蓝靛 1、青 1、白 1。
7. **工程就绪**：LH3 白 successor 全链离线建成（`.test-output/offline/LH3_SOURCE_WHITE_20260918_R1/`，
   编译 + native 审计 + runner 全过），是任何下一现场链的前置；
   剂量链设计原则已定（每级帧内嵌"新鲜白历史+码 0..7"码轴标定条、白参照列、
   链位深度作自变量）。qualified 全程保持 0/256，无过度宣称。

## 5. 我们在行业地图上的位置与路线判断

- **行业主干**（固定调色板 + 空间抖动）：本项目已有全套管线
  （`host/halftone_optimization`、`gamut_mapping`、dither atlas 工具链），
  缺的是实测调色板成员——正在逐链补齐。
- **行业研究前线**（历史依赖/记忆效应管理）：本项目用 MAP 与 XOR-3 在
  Spectra 6 上独立复现并定量化了该现象。
- **ACeP 式开放多级**：行业自身也未产品化；剂量轴对我们是一次
  **低成本判决性实验**——成，则每色多几级；败，则回到行业主干，无损失。

## 6. 下一步（与 STATUS_HANDOFF 一致）

1. 白天真日光重拍 MAP（0 刷新；照明需达 9-17 亮场 0.85 门）；
2. 白天放行 LH3 剂量判决链（LH3 白已就绪；主链按 §4.7 设计原则另建）；
3. 每个验证过的态喂给实测调色板 → 抖动管线（gamut mapping 用实测 Lab，
   不用标称 RGB）。
