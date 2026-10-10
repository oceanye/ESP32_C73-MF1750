# MF1750 E6 明度波形机制研究与当前芯片探索边界

日期：`2026-09-05`  
适用对象：`MF-17506-M009F-T`、1024×600、双 `SPD1657B rev 0x04`、3-bit E6 参考架构  
状态：`OFFLINE RESEARCH / NO NEW LIVE ACTION`

本文把公开论文、E Ink/Spectra 平台说明、相邻控制器开源驱动和本地参考工程放在同一证据矩阵中。外部参数只用于解释机理和设计离线筛选，不能直接变成当前控制器的命令、LUT、phase、波形或电压参数。

## 1. 先固定明度的物理含义

本面板是反射式电泳显示。静态画面不靠背光发光，而是改变带电粒子相对于观察面的分布来改变反射光；因此当前实验的“明度”应记录为同一色相轨道内的相对反射明暗，主指标是同一相机设置下的 `L*`（camera-relative Lab），不是背光亮度，也不是绝对 `cd/m²`。有条件时再以分光/亮度计建立标定反射率。

外部 Spectra 6 资料说明红、黄、蓝、白粒子经过组合形成黑、白、红、黄、蓝、绿六个基本状态，并用 dithering 形成更丰富的图像；这支持“六个原生端点 + 波形/渲染扩展”的平台模型，不支持把任意中间照片颜色直接当作稳定单像素状态。

## 2. 来源与证据等级

等级沿用项目的 `D/P/I/U`：`D` 为当前精确面板直接证据，`P` 为官方平台、兄弟器件、论文或开源驱动，`I` 为交叉证据支持的机理推论，`U` 为尚不能确定的当前芯片接口。只有 D 级或本项目真屏闭环证据才能改变当前芯片的可执行合同。

| 来源 | 关键事实 | 对当前 MF1750 的用途 | 等级/边界 |
|---|---|---|---|
| [本地 MF-17506 规格与官方证据矩阵](EPD_EXTENDED_COLOR_OFFICIAL_EVIDENCE_2026-08-05.md) | 3-bit E6、双 SPD1657B、片上 LUT/温度传感器/OTP waveform；公开资料没有完整 rev 0x04 ABI | 固定当前硬件身份与未知项 | D；命令/LUT/phase 仍 U |
| [E Ink Spectra 6 品牌页](https://www.eink.com/brand/detail/Spectra6) | Spectra 6 平台、典型对比度约 30:1、0–50°C、Sparkle 能力 | 说明平台范围，不能证明本片支持 Sparkle | P |
| [SID Digest 92-1：Color Electrophoretic Display for Outdoor Signage](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-1.pdf) | Spectra 6 的红/黄/蓝/白粒子在 Microcup 中形成六色，并以 dithering 组成全彩图像；EPD 反射环境光，静态保持不刷新不耗能 | 解释六端点和反射式明度的物理背景 | P；论文平台不等于本片 ABI |
| [E Ink Ripple/Second-Generation Waveform Architecture](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays) | 新架构与升级芯片可把 Spectra 6 扩到八原生色；T2000 配置另加 cyan/light green/orange；Spectra 3100 Plus 另有四级灰度描述 | 证明“波形架构可改变可寻址色/灰度”，同时证明不能把新架构能力映射到当前 SPD1657B | P；当前兼容性 U，禁止移植 |
| [Kim et al., Electronics Letters 2014, DOI 10.1049/el.2014.3671](https://ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/el.2014.3671) | 传统波形含 erase/reset/white/write；3 个电平的脉宽调制可得 8 灰阶；加入两个电平后实验得到 165 个灰阶；DC balance 与历史/时序敏感 | 支持“明度来自受控时序/脉宽和历史，而不只是 code 数值”的探索假设 | P；不同面板，不能带入电压/帧数 |
| [Luo et al., Micromachines 2024](https://www.mdpi.com/2072-666X/15/9/1076) | 以白作为稳定参考，分 erase、activation、write；以 0.7/0.5/0.3/0.1 四反射级验证；论文用 15 ms 子帧并以光电响应选择阶段时间 | 提供“白锚 → 受控 target 写入 → 光学排序”的实验结构 | P；90/180 ms 等数值不适用于本片 |
| [三色 EPD 波形设计论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8622660/) | 粒子速度随电压与流体阻力变化；白/黑粒子相对电极距离决定反射明度；红色由另一电压序列选择 | 支持把同色相明度看作粒子位置/反射率状态 | P；不是四粒子 Spectra 6 |
| [Kim et al. 红色饱和度波形论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC7915761/) | erase/activation/target 波形和粒子历史会改变色彩纯度与 ghosting | 提醒同一目标色的明度/色相必须绑定 source history 与保持时间 | P；不得抽取本片参数 |
| [Adafruit/ESP-IDF UC8179 开源驱动](https://components.espressif.com/components/cleishm/idfxx_epaper_uc8179/versions/1.0.0/readme) | 相邻 UC8179 玻璃可选 factory OTP 的 4-level gray；gray4 仅 full refresh；切换 waveform 会 reset；需硬件验证 OTP 是否存在 | 说明“OTP 灰阶库 + full refresh 约束”是常见架构，验证思路可借鉴 | P；不是 SPD1657B |
| [ESPHome/parkghost 开源驱动](https://github.com/parkghost/esphome-epaper) | 对 UC8179 gray4 显式使用 0/85/170/255 四个 luma level；某 LUT 版本的 light gray 会接近 white | 说明 host 端可按 luma 排序，但软件映射不是物理灰阶证明 | P；不能写入当前面板 |
| [US20250239231A1](https://patents.google.com/patent/US20250239231A1/en) | 波形由多帧正/负脉冲组成；old/new 图像、邻域变化和局部更新影响 ghosting | 支持当前坚持 fresh-white、old/new/history 绑定和局部保持审查 | P；专利不提供当前可执行参数 |
| 本地 `E6_73.c` 参考工程 | 800×480 相邻样例以 `0x00/11/22/33/55/66` 表示六个颜色端点，使用 DRF/POF/OTP 路径；0x86 注释为未来 dithering 保留 | 证明相邻 E6 平台有“端点码 + 完整刷新”模型 | P；不是 1024×600 当前固件 |
| 本地 `REG-API-oqc` 深审计 | 有 535-byte 明文 2-bit runtime LUT 路径，也有加密/不兼容的 E2802 3-bit loader 线索；双控、当前批次和 payload ABI 未闭合 | 证明运行时 LUT 机制可能存在，不能证明当前 SPD1657B 3-bit 可安全加载 | P/U；当前仍禁止刷 LUT |

## 3. 这些资料共同支持的明度机制

### A. 同色相 endpoint 之间的反射差异

当前最安全的第一层是使用已知兼容完整 profile 的直接 endpoint，固定 source/target 合同，只比较同一 controller 内不同 code 的终态。候选必须满足：纯场、四位置一致、`L*` 单调、色相角变化小。跨 CS1/CS2 不合并平均，因为两颗控制器的 profile/光学响应可能不同。

### B. source → middle → target 历史配方

论文与本地历史实验都表明，电泳粒子的终态依赖先前位置和脉冲历史。可离线表示为 `R(source, middle, target)`，但 recipe 编号不代表明度顺序。当前探索应从 factory-OTP white 锚开始，固定一个目标色相，筛选少量 source/middle 历史配方，并在四个空间副本上比较 `L*`、色相和纯度。

这类结果必须经过独立 fresh-white 重建；原位 identical-target repeat 不能替代 fresh reconstruction，因为本项目已有历史链在重复后明度跨度塌缩的证据。

### C. 完整刷新剂量/重复次数

部分论文通过脉宽或帧数改变反射率，说明“完整、正常结束的重复 target 刷新”可以作为低风险候选机制。但它排在 endpoint 与 history recipe 之后：当前尚未证明重复次数与 `L*` 单调，更不能把重复次数写成 3→5→10 明度等级。必须先做小阶梯、每阶独立拍摄、白锚和保持检查。

### D. runtime LUT / phase

运行时 LUT 能够从平台层面改变波形和可用状态，但当前 SPD1657B rev 0x04 的 3-bit ABI、LUT 格式、温区、phase 极性和双控制器加载均未闭合。它只能作为离线解析和供应商索取资料方向；在获得精确 payload/loader 证据前不生成真屏 LUT。

### E. waveform interruption 的中间态

专利和论文说明粒子在脉冲序列中会经过中间位置，因此理论上可能出现中间反射率。当前项目没有独立电源切断、精确 phase 解释或恢复保障；该路线风险最高，保持 `HARD BLOCKED`，不能用 BUSY 中断、继电器截断或任意删 phase 探索。

### F. 空间 dithering

Spectra 6 平台确实用 dithering 组成更丰富的图像，但那是空间混色/渲染能力，不是单像素明度槽。当前 256 槽目标只统计单像素逻辑状态；空间抖动不得增加 qualified 数量。

## 4. 针对当前 MF1750 的推荐顺序

1. **先建 controller-local 明度轴**：从 retained clean-white 出发，选择经新 fresh-white gate 确认的同色相 endpoint/history 候选，复核当前 P2 code `1↔7`。`1↔7` 仍只是 camera-relative candidate，尚无跨 CS 匹配和独立重建。2026-09-06 勘误：P2 optical V2 的缺边缘拟合输入为 **code 5**；code 7 是布局的 background transport code，二者不能混称，也不能由此授予任一码白色资格。
2. **只使用完整已知 profile**：不混接 header/body，不插值 R20/WF20/WF23，不修改 VCOM、PLL、高压或温区字段。
3. **优先 history recipe，而不是立即改 LUT**：对 source/middle/target 进行小规模、固定顺序的完整刷新；每条 recipe 的四位置必须同时保留，按实测 `L*` 排序。
4. **命中后先 HOLD，再 fresh reconstruction**：候选形成后不覆盖候选区，先做局部保持/邻域干扰观察，再用独立 factory-OTP white 重新构建至少两次。
5. **再试完整刷新剂量阶梯**：仅当 history recipe 没有足够明度分离时，探索 `1/2/4/7/10` 次完整 target 刷新；这只是实验序列，不把次数当等级。
6. **精确 runtime LUT 的证据门**：需要当前 SPD1657B rev 0x04 的可信字段/loader 证据、对应面板 waveform 身份、温区、电气边界、双控加载和恢复方式。证据可以来自可审计的同代源码、配对文件差分和本项目实测总线/电气闭环；官方支持不是唯一出路。证据未闭合前不直接移植公开参数，不生成任意字节扫描。

## 5. 判读和停止条件

- 当前使用 `camera-relative Lab L*`；有色相轨道同时检查 `a*/b*`、色相角和 `ΔE76/ΔE00`，不得混阈值。
- 当前项目的 `|ΔL*| ≥ 8`、色相角差 `≤10°`、四位置 P95 `ΔE76 ≤ 6.6032` 等，只是实验筛选门，不是厂商规格。
- 缺少四位置、fresh-white、HOLD、保持或白恢复证据时，状态保持 `candidate`，`qualified=0`。
- 任意协议/状态不明、BUSY 异常、固定线/边缘污染、白恢复失败或身份漂移，立即 `FAIL_STOP`；不重发 mutation、不在 BUSY 中复位/刷白。

## 6. 当前结论

公开资料支持的最可信路线是：**固定色相端点 → source/middle/target 历史配方形成不同反射状态 → 光学排序与四位置筛选 → local HOLD → 独立 fresh-white 重建 → 再扩到 3→5→10 明度等级**。资料不支持把当前面板直接当作已有 10 级明度，也不支持把 E Ink 2025 新波形的八色/灰度能力写入 SPD1657B。

当前实验应继续把“明度”作为核心目标；灰度仅作为中性轴的特殊子集，彩色明度候选优先于中性灰搜索。当前 `qualified_lightness_levels=0` 仍保持不变。
