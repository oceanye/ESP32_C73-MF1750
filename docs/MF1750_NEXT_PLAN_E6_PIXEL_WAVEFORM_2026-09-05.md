# MF1750 E6 像素级多色波形后续计划

更新时间：`2026-09-05`  
适用硬件：MF1750 1024×600 双控制器、两颗 `SPD1657B rev 0x04`  
当前状态：`NO-GO`；`relay/J2=commanded OFF`；`electrical_state_proven=false`

本计划承接 [`CONTEXT_RESET_HANDOFF_2026-09-05.md`](CONTEXT_RESET_HANDOFF_2026-09-05.md)
和 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部条目。它只定义后续工作，不授权本次访问设备。

按 phase、controller、source/target 和光学反馈执行的详细闭环见
[`MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md`](MF1750_PHASE_CONTROLLER_CLOSED_LOOP_TEST_PLAN_2026-09-05.md)。

## 结论先行

当前已经证明的是：已知 profile 的端点可以被单次刷新、按位置和控制器重复观察；尚未证明稳定的新颜色、同色相明度、HOLD 或任何 256 槽资格。P1 仍为 `qualified_new_colours=0`、`qualified_lightness_levels=0`。

后续证据建议同时记录两个字段：`platform_native_states=6`（公开 Spectra 6 平台口径）和
`experimentally_qualified_single_pixel_states=0..N`（本面板实际通过的单像素槽）。后者只能由
本项目的证据状态机递增；混合色、一次性过渡态和空间抖动不得填入其中。

公开资料进一步收紧了边界：E Ink 的 Spectra 6 采用四粒子系统，产品页面把基本显示描述为黑、白、红、黄、蓝、绿六色；官方资料没有公布 SPD1657B 的 WBF/IWF/LUT 或寄存器 ABI。2025 年 E Ink 所说的 3-bit、八原生色和灰阶扩展，绑定于新的 Ripple 波形架构和兼容芯片/T2000，不能推断为现有 SPD1657B 可用。因而“10 个单像素明度等级”仍是待证假设，不是屏幕规格。

## 下一次现场动作（唯一允许序列）

1. 操作者在不刷新、不复位、不刷写的条件下确认 retained screen：全屏干净白；无色块、边框、色斑、固定线和明显旧网格。任一项失败，立即停止，不访问设备。
2. 重新枚举设备，建立本次 session 的 exact `IPv4↔MAC` 绑定；旧 IP、旧 COM 和旧 boot 身份不得继承。相机如需使用，只允许项目指定的 `VID_32E4:PID_4801` 48MP 设备。
3. 在同一 boot 完成 J2-OFF diagnostic：目标 `4 GET / 0 POST / 0 claim / 0 driver / 0 visible refresh`，并保存原始 status timeline。`commanded OFF` 或 query OFF 不能单独升级为 `electrical_state_proven=true`。
4. 操作者单独明确放行 **P2-C ordinal 1**。只写入并 verify 已封印的主固件，执行一次 action，随后停止；不执行 ordinal 2，不自动刷白，不 retry、不 auto-chain。
5. 现场只做观察和证据归档。P2-C 的判读问题限定为：每个位置/控制器的端点外观、位置重复性、左右同位一致性和边缘污染；不得把动作完成写成颜色、明度或 256 槽通过。

## P2-C 结果包的固定内容

每次现场 action 必须把以下对象绑定到同一 manifest：

- action JSON、GET-only status、raw BUSY/status timeline；
- firmware BIN/ELF、contract、descriptor、action 的 SHA-256；
- 48MP JPEG 原图、曝光、白平衡、焦距/机位、光源与温度；
- ROI 坐标和每个 `controller × position × endpoint` 的人工观察原文；
- 若有测量，记录 `L* / a* / b*`、`ΔL*`、`ΔE00`、色相角差、位置内离散度和跨控制器差异；
- `electrical_state_proven` 的来源。缺少任一关键绑定时，资格保持为 0。

## 资格状态机

每个槽独立维护状态，不允许从端点 atlas 直接跳到明度族或照片映射：

`candidate → stable-3 → stable-5 → stable-10 → cross-controller matched`

进入 `stable-3` 前必须有同一 controller-local recipe 的三个单像素等级、fresh-white 锚、同一光学标定和独立重复；`stable-5`、`stable-10` 依次增加等级并保持单调、可分辨和可重复。跨控制器只有在两侧各自 recipe 通过、且在同一照明/标定下有显式光学匹配证据后才允许合并。缺少测量阈值、HOLD 证据、fresh reconstruction 或白恢复证据时，保持 `qualified=0`。

P2-C 若只重现 C0/C6/C1 一类端点，下一步先建立 controller-local palette inventory；命中端点不等于明度等级。若没有可重复的同色相差异，停止该轴，转入离线 ABI/供应商证据门，而不是继续扩大 ordinal 或任意扰动。

## 两条后续分支

### A. 命中可重复端点差异

先离线生成该端点的 palette inventory 和 slot-admission report；再为候选建立独立 fresh factory-OTP 白锚、构色、局部 HOLD 和第二次 fresh reconstruction。只有完整链条通过，才允许进入 3→5→10 明度里程碑。HOLD 代码目前仍是 `BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE`，不得现场试探。

### B. 没有可重复明度或只有一次性过渡态

将该轴封存为 `candidate_only`，保留 `qualified=0`。并行向 E Ink、Solomon Systech、模块供应商索取本确切 `SPD1657B rev 0x04` 和 MF1750 面板组合的：官方 waveform 文件及授权使用方式、3-bit/Ripple/T2000 兼容性、温度补偿表、亮度/颜色校准数据和 controller-local recipe。拿不到这些证据时，产品路线退回“六个原生色 + 离线照片映射/空间抖动”，不声称单像素 256 槽。

## 明确禁止

继续禁止邻芯片 LUT/寄存器移植、把论文电压直接套到本板、未知命令扫描、任意 byte 插值、header/body hybrid、VCOM sweep、BUSY 中断、复用旧 claim/action、自动白恢复和自动串联下一项。公开的开源 WBF/IWF 格式只能说明数据模型，不能提供本板安全 payload。

## 当前最小离线工作集

在下一次现场前只做：结果 manifest/ROI 模板、资格状态机的 fail-closed 校验、P2-C 报告复核、供应商问题清单和完整性哈希复算。不得因此生成 seed/perturbation 固件，也不得改变当前 NO-GO、relay/J2 或现场授权状态。

## 公开资料（截至 2026-09-05）

- [E Ink Spectra 6 品牌页](https://www.eink.com/brand/detail/Spectra6)：Spectra 6 的公开定位、典型对比度、温度范围和 Sparkle；未提供本板 LUT/寄存器 ABI。
- [E Ink Ripple / Second-Generation Waveform Architecture（2025-03-27）](https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays)：说明 3-bit/八原生色和 T2000 扩展属于新波形架构与兼容芯片，不能移植推断到 SPD1657B。
- [E Ink Spectra 6 Display Kit 页面](https://shopkits.eink.com/en/product/detail/13.3%27%27Spectra6ePaperDisplay)：明确显示颜色取决于 display controller 与 associated waveform file，列出黑/白/红/黄/蓝/绿。
- [SID Digest 92-4（2025）](https://sid.org/Portals/sid/Files/SID-Digest/docs/92-4.pdf)：公开介绍 Spectra 6 四粒子、双稳态和波形驱动物理；不提供 SPD1657B 可直接使用的 payload。
- [Solomon SPD1657 展会页](https://www.computextaipei.com.tw/en/product/CBA4659B8C39B7F72BDDBEB61C4033B7A51D2AFD55BCA758/info.html)：仅确认公开的 SPD1657 产品支持 Spectra 6 和 800×600 规格；它不是本项目双 512 级联组合的 ABI 证明。
