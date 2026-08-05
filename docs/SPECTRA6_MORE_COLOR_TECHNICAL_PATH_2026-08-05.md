# MF-1750 / Spectra 6 更多颜色技术路径

日期：2026-08-05（Asia/Shanghai）
状态：`COMPLETED`（非硬件技术路径与离线工具范围）
Hardware tested：`NO`

本文回答两个不同问题：

1. 能否用当前六个正式颜色码得到更多**视觉颜色**？可以，使用空间抖动或面积混色。
2. 能否用波形得到更多**单像素独立状态**？现有论文与 E Ink 后续公告共同支持这种
   物理可能性；但当前 `MF-17506-M009F-T + SPD1657B rev 0x04
   + OTP` 的兼容性和安全参数没有直接证据，因此仍是 `HARD BLOCKED`。

这两个结论不矛盾。“full color”不等于“每个像素有大量稳定编码”。

## 1. 对用户所引页面文字的核对

用户提供的文字称 Spectra 6 使用白、红、黄、蓝带电粒子产生六种主色，并用
dithering 形成饱和全彩图像。完全相同的英文措辞可在转售页面找到，但本项目不把
转售页作为直接证据；权威的等价证据是：

- [E Ink 2024 Annual Report，PDF p.78](https://kr.eink.com/upload/2025_04_28/51_20250428155204i9ls2kL8C5.pdf)
  说明白、红、黄、蓝四种带电彩墨形成黑、白、红、黄、蓝、绿六色，并由高级混色
  算法呈现丰富颜色。
- [E Ink 作者 IDW 2023《Color Electrophoretic Displays》](https://confit.atlas.jp/guide/event-img/idw2023/EP1-01/public/pdf_archive?type=in)
  的摘要和 §2.3 明确列出每像素六个设备色；论文称高级驱动能得到更多混合光学输出，
  但量产方案选择六个设备色，再由 dithering 管理其他颜色。论文没有证明额外输出是
  稳定、可寻址、可保持的 palette state。
- [SID 2025《Color Electrophoretic Display for Outdoor Signage》](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-1.pdf)
  的引言回顾 Spectra 6 六状态经抖动形成全彩图像；该文主体是另一平台，不能移植其中
  的中间粒子状态机制。

因此，这段页面介绍准确支持“六主色 + 空间混色”的近期工程路线；它不提供第七色
编码、LUT、相位、电压或 SPD1657B 命令。

## 2. 四级证据判断

| 等级 | 当前证据 | 可得结论 | 不可得结论 |
|---|---|---|---|
| D：直接证据 | 精确 MF-17506 规格：3-bit E6、六状态、片上 OTP、双 SPD1657/B | 本机正式六色、几何、控制器拓扑和 OTP 边界 | 规格未写 Spectra 6 商标，也未给额外状态或波形接口 |
| P：平台证据 | E Ink 年报、IDW/SID 论文、兄弟模组、2025 官方公告 | Spectra 6 四粒子、量产六设备色、空间抖动；官方已另行公布新混色波形架构 | 不证明额外输出是当前硬件可寻址的稳定状态 |
| I：推论 | E6/六状态/SPD1657 交叉吻合；论文物理与后续公告交叉支持 | 本机属于 Spectra 6 家族为高置信推论；额外单像素态只有物理可行性推论 | 不能据此生成寄存器、LUT、码表、电压或时序 |
| U：未知 | 精确 film lot、SPD1657B 资料、OTP manifest、Ripple 与新混色架构支持包均缺失 | 必须向厂商索取 | `0x4/0x7/bit3`、新颜色及波形参数保持 `null` |

## 3. 三类“更多颜色”

### 3.1 更多视觉颜色：当前安全路线

每个像素仍只写正式码 `0/1/2/3/5/6`，观察者在一定距离把邻近像素的反射光学混合。
仓库已有 `host/color_pipeline/`，支持最近色、Floyd–Steinberg、Atkinson、Bayer 8×8
和确定性 hashed-threshold。它适合普通图片量化和保边缘输出。

本轮新增 `tools/mf1750_area_mix.py`，用于可测色块和固定面积配方：

- 2×2 tile 有 126 种六色整数配比；4×4 tile 有 20,349 种；
- 在 CIE XYZ 域做面积平均，禁止直接线性平均 Lab；
- 使用 CIEDE2000 对目标 Lab 排名；
- 配方像素数严格守恒，并以确定性 Bayer 顺序分散；
- 为每个候选生成 1024×600、4bpp、307200 B 的正式六码帧身份、frame SHA-256
  以及 CS1/CS2 DTM SHA-256/FNV-1a；
- 报告冻结 `xyz-area-v1` 模型、`bayer-threshold-interval-v1` 布局、完整 palette、
  tile/hash scope 和所选帧绑定；语义 validator 会重算真实 top-N、预测、tile、frame
  及双 DTM 身份，拒绝被篡改或与声明不一致的报告；
- 默认要求具有测量来源和 SHA-256 的 D65/2° 校准色板；未校准参考色板必须显式使用
  `--allow-uncalibrated-simulation`，报告强制写明预测不是实测；
- `--frame-output` 必须同时提供报告 sidecar；报告先以 exclusive-create 写入，随后才写帧，
  两者都不覆盖已有文件；
- 不包含 HTTP、串口、设备 URL、刷新、固件、LUT、波形或电压入口；输出和 palette 路径
  主动拒绝 `.test-output/`、冻结生产目录、Windows DOS 设备名、UNC/device namespace、
  NTFS ADS 和映射网络盘。

面积混合报告从 schema v2 起使用 `frame_contract_compatible`，它只表示输出满足
1024×600、4bpp 和正式六码的字节合同，不表示已经校准、安全批准、获得硬件授权或
经过设备测试。v1 的 `formal_api_compatible` 已弃用；v2 schema 仅保留该名字用于迁移
识别并明确拒绝实际出现，消费者必须按 `schema_version` 解析。

即使 palette schema v2 写有 `calibrated=true` 和 measurement hash，它仍未绑定精确
panel/batch、firmware/waveform、环境、几何、backing 与可验证原始 artifact。因而当前
area-mix 报告固定 `hardware_formal_qualified=false`；只有未来引入并验证覆盖上述字段的
characterization profile 后，才能在新的版本化合同中重新评审硬件正式资格。

示例（仅离线分析，不写文件、不连接设备）：

```powershell
python tools/mf1750_area_mix.py `
  --palette path\to\measured-palette.json `
  --target-srgb 0 180 190 `
  --tile-side 4 `
  --limit 8
```

20,349 是配比组合数，不代表 20,349 个肉眼可分辨颜色。实际色域仍受六个实测主色的
凸包限制；不同配比可能视觉等同。4×4 固定 tile 还会带来颗粒、摩尔纹和约 256×150
的宏观色块尺度，普通图像应同时比较误差扩散方案。

为避免异常数值导致非有限计算，工具的计算输入契约限定 `L*=0..100`、
`a*/b*=-200..200` 且全部有限；这只是分析器的 fail-closed 边界，不是面板色域或测量
不确定度声明。

### 3.2 更多单像素颜色：官方新混色波形架构

[E Ink 2025 官方公告](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)
先把 Ripple 描述为波浪式图像转场效果，随后以“In addition to E Ink Ripple”另行介绍
利用现有粒子增强混色的新 waveform architecture。公开文字没有说明两者的实现关系，
本项目因此不把 Ripple 与新混色架构等同。

新混色架构的“升级 3-bit chipset system”配置称可扩到八个主色，另一 T2000 配置称
可增加 cyan、light green、orange。它们是公告中的不同系统配置，不应把“八色”和
“六色加三色”自行合并，也不应猜测新增颜色对应 `0x4`、`0x7` 或 bit3。

公告列出 Fitipower、Solomon Systech、Himax、Novatek、IST、UltraChip 六家兼容芯片
供应商；Solomon 只是其中之一，公告没有给出任何具体 Solomon 型号，更没有点名
SPD1657/B、revision 或 MF-17506。当前 OTP 因而继续只按已验证六色使用。

### 3.3 自定义研究波形：当前禁止执行

IDW 论文展示驱动与粒子分层会改变光学输出，也展示错误分层可形成非目标颜色；结合
2025 官方新混色架构，额外单像素态的物理可行性属于 `I` 级推论。一次出现漂亮颜色
只说明瞬时态，不证明它是稳定、可寻址、可保持的 palette state，更不证明 old→new
一致性、温区、左右控制器一致性、恢复能力或寿命。

在 SPD1657B rev 0x04 完整资料、当前 OTP 包、正式 LUT 接口、厂商电压/时间/恢复/寿命
限值、测量夹具、硬联锁、牺牲屏和黄金参考屏全部到位前，不生成、不上传、不选择任何
自定义 LUT/phase，也不修改 PLL、PWR、BTST、POFS、PWS、VCOM 或高压。

## 4. 离线优化和以后实测的正确模型

当前工具采用“实测 Lab → XYZ → 面积平均 → Lab/ΔE00”的一阶模型。它适合筛选候选，
但还没有模拟面板散射、边缘场、观察距离、排列相位、旧帧历史或控制器差异。后续应：

1. 用 D 阶段六色光谱反射率和 Lab 建立真实 palette；
2. 生成面积配比和误差扩散对照图；
3. 固定照明、45/0 几何和 RAW 条件，测实际混色 Lab，而不是把预测写成实测；
4. 用实测残差拟合光谱/Neugebauer 或其他经验证模型；
5. E 阶段数据可用后，把 old→new 转换成本、能量、残影和温升加入联合目标；在此以前
   相关项必须为 `null`，不得虚构权重。

## 5. 向厂商索取的最短清单

1. MF-17506-M009F-T 的精确 Spectra 6/film lot 认证和代际；
2. SPD1657B rev 0x04 完整 datasheet 与 command supplement；
3. 当前 OTP waveform ID、版本、CRC/hash、批次和温区；
4. MF-17506 + SPD1657B rev 0x04 + 当前 OTP 对 Ripple 转场的兼容声明和支持包；
5. 同一硬件组合对新混色 waveform architecture 的独立兼容声明；仅在确认兼容后，
   索取具体芯片型号、实际主色数量、完整码表、reserved/bit3 规则、支持包和回滚方式；
6. Ripple 与新混色架构的实现关系声明；
7. LUT upload/select/readback 的明确支持或不支持声明；
8. old/new、温度选择、VCOM/Source 定义以及恢复、冷却、连续刷新和寿命限制。

## 6. Go / no-go

| 工作 | 决策 |
|---|---|
| 正式六码的离线图片抖动、面积混色、schema、hash 和模拟测试 | `GO` |
| 用实测六色 palette 重新优化 | `GO`，但取得实测数据前仅能准备工具 |
| 把 `0x4/0x7/bit3` 当作 cyan/orange/light-green | `NO-GO` |
| 在当前 OTP 上宣称或启用 Ripple 或新混色波形架构 | `NO-GO` |
| LUT、phase、波形、时序或电压修改 | `HARD BLOCKED` |
| 上电、刷写 COM8 或发送任何指定帧 | 本文不授权，仍须逐项询问用户 |

本轮未上电、未刷写、未调用刷新接口、未发送帧、未访问 COM8、未修改固件或正式颜色
guard。原始硬件数据路径与 SHA-256：`null`；异常与恢复结果：不适用。
