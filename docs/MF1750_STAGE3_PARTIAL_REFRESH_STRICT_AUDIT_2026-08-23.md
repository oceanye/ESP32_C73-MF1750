# MF1750 Stage III 局部刷新严格复审

日期：2026-08-23  
状态：资料、样例、相邻实现、当前 V4 和主机规划器均已离线复审；未访问继电器、
设备网络、COM/串口，未刷写、复位或刷新真屏

## 1. 最终裁决

局部刷新必须拆成四件不同的事：

1. **局部 RAM 写入**：`PTLW 0x83 → DTM 0x10 → cropped pixels`，只改变 SRAM 的一个矩形。
2. **局部地址刷新**：DRF 前保留 `PMODE=1` 的单个矩形，使当前 DRF 使用该窗口。
3. **窗口外颜料 HOLD**：窗口外即使没有新 DTM，仍会参加 gate scan；是否不变取决于
   LUT、VCOM、旧颜料状态和位置，不能由 `0x83` 推导。
4. **快速局刷**：相邻 GDEP073E01 虽公开支持 partial update，但当前实现明确
   `hasFastPartialUpdate=false`，partial/full 均按 15000 ms 等待。局部的价值是状态累积，
   不是缩短 Spectra 6 波形。

本屏实测已经证明第 1、2 项的地址路径有效，但 Blue-1/Blue-2 在后续刷新中灰化，故第 3 项
只能判为 `universal HOLD FAIL`。这不否定局部 RAM，也不等于所有旧状态都必然失效。

## 2. 精确芯片硬要求

| 项目 | 必须满足的合同 | 当前 V4 |
|---|---|---|
| 命令可用期 | 正常上电序列后有效；`BUSY_N=0` 时禁止写命令 | PON/DRF/POF 前均要求 idle，随后等待 busy→idle |
| Pixel mode | PSR.A[4]=1，即 3-bit/pixel | `PSR={0x5F,0xE9}`，满足 |
| PTLW | `0x83` 后必须完整写满 9 bytes | 固定 9 bytes |
| 矩形 | `HRST<=HRED`、`VRST<=VRED`，端点为地址值 | 固定 `x+w-1/y+h-1` |
| Partial enable | PTLW 最后一字节 `PMODE=1` | 固定 1 |
| DTM | `0x10` 后直接是像素流；不得虚构格式前缀 | 无前缀 |
| 3-bit packing | 每字节两个像素，每 nibble 为 `0+3-bit code` | `width*height/2` bytes |
| DRF | DTM 完成后发 `0x12,0x00` | 满足 |
| Border | CDI 控制边框和数据极性；相邻实现局刷用 `0xFF` 浮空边框 | partial 前固定 `0x50,0xFF` |
| 上下电 | PON→DRF→POF，均保留 timeout 和失败安全收尾 | 满足 |
| 禁止项 | `0x90/0x91` 是 OTP 编程，`0x92` 是 OTP 读取；`0x86` 不属于 PTLW 合同 | V4 无这些发射入口 |

手册还明确：POF 只关闭模拟驱动，寄存器和 SRAM 在 VDD 未断时保留。因此可以先用
DTM-only 预装若干 RAM 区域，再执行一次 DRF；但硬复位或物理断电后的 SRAM 连续性不能
靠这条说明外推。

## 3. 对齐要求的严格边界

- **已证明**：当前 3-bit/nibble 数据一字节承载两个像素，所以 native ROI 最安全的最低
  合同是 `x` 偶数、`width` 偶数。
- GxEPD2 的普通 bitmap API 要求 8-pixel 对齐，是其 1-bpp 输入位图按字节打包导致；
  `writeNative()` 自身只向外扩为 2-pixel 对齐，不能把 8-pixel 当成芯片硬要求。
- SPD1657A 第18页命令表看似把水平地址低两位写成 0，但第32页又给出完整 10-bit 地址，
  默认 HRED=`0x31F=799`，厂商样例和 GxEPD2 也都发送原始包含式终点。这是手册内部
  不一致。当前固定窗口恰好采用 4-pixel 粒度，可继续保守使用；但“所有 PTLW 都必须
  4-pixel 对齐”尚不能写成已证明结论。
- TRES 要求水平分辨率为 4 的倍数，只约束控制器分辨率，不能自动外推成窗口对齐规则。

## 4. 仍可使用的局部方法

### A. 单矩形 cropped-DTM + partial DRF

这是当前 V4 路径：每颗控制器各有一个 PTLW 矩形和一段裁剪 DTM，然后两颗同步 DRF。
一颗控制器在一次 DRF 时只有一个当前窗口；双控板最多同时保留两个控制器矩形。

### B. RAM staging 与显示刷新分离

先用一个或多个 `PTLW→DTM` 只改 SRAM，不执行 DRF；所有 staging 完成后，再设最终窗口并
执行一次 DRF。GxEPD2 的公开 API 也把 `writeNative()` 和 `refresh(x,y,w,h)` 分开。

用途：

- 一次预装多块数据；
- 把一个大矩形内部安排成 32/64 个不同 code 的子区；
- 减少 SPI 数据，不减少显色波形时长。

限制：PTLW 只有一个矩形寄存器，不支持一次 DRF 的 32/64 个独立窗口列表。多个不相邻
子区必须使用一个包围矩形，且其中间像素也属于本次扫描窗口。

### C. 多窗口 RAM staging + 一次全屏 DRF

相邻 GxEPD2 源码存在逐条设置 PTLW、分别写 DTM，最后调用全屏 `refresh()` 的结构。这能
证明多个 RAM 窗口可以在 DRF 前累积，但最终是全屏扫描，不是多窗口 HOLD。

### D. Warm session

当前 V4 每个外部 action 都重新 `epdPrepareCascade()`，而 GxEPD2 可以在一次初始化后连续
`writeNative→refresh(window)`。可建立单一受控 session：初始化一次，连续执行 A/B/C，最后
统一 POF。它能排除“每步 reset/re-init”变量并保留 SRAM；不能消除窗口外 gate scan。

### E. LUT 定义的 HOLD code

这是一条与 PTLW 硬件屏蔽不同、值得优先准备的路线：在自定义 LUT 中保留一个 code，使其
各相位对像素产生零或平衡净驱动。一次颜色完成后，先用 DTM-only 把该区域的 SRAM 标签改为
HOLD code（不 DRF），再给新区域写 active code，随后运行下一套 LUT。

它的优势是即使窗口外 gate 继续扫描，旧区域也可以由 LUT 本身获得“无净迁移”保护；它是
多调色盘叠加更可信的基础。限制是当前公开资料没有提供可直接宣称正确的 HOLD 波形，必须
从已恢复的 R20/R21 格式和受控候选中实验验证，且每个旧颜料状态都要资格化。

### F. 受限状态保持矩阵

在 generic HOLD 失败后，仍可测 `旧颜色状态 × 后续 LUT/patch × gate 位置`。如果白、红、绿
等子集稳定，而两种蓝不稳定，则照片渲染可以先只允许已验证子集叠加；不得称为任意 256 色。

## 5. 一个 DRF 能承载多少“不同东西”

| 维度 | 一次 DRF 的上限/含义 |
|---|---|
| PTLW 窗口 | 每控制器一个矩形；双控最多两个矩形 |
| 子区域数量 | 矩形内部可放很多子区，但共享同一 LUT、同一相位时序 |
| 像素 code | 当前 3-bit 模式每控制器最多 8 个 code |
| LUT profile | 每控制器一份全局表；双控可各装不同表，但每半屏仍只有一份 |
| 跨调色盘共存 | 需要连续多次 DRF，并证明旧状态 HOLD，或实现/验证 LUT HOLD code |

因此“一次显示 32/64 个候选”可以用于同一 LUT 下的 code/历史/位置 atlas；不能让 32/64
区域各自运行不同波形。搜索不同波形时，仍然是一颗控制器一套 LUT，但可以把另一半作为
独立 profile/对照。

## 6. 还存在的单变量冲突

1. **Y 终点**：精确手册和指定区域样例为 `y+h-1`；当前 GxEPD2 为 GDEP073E01 特设
   `y+h` one-more。MF1750 真屏的 `y+h` 已出现底侧间隔异常，所以主线固定 `y+h-1`；
   `y+h` 只作有限诊断。
2. **CDI**：全屏常用 `0x3F`，相邻库局刷用 `0xFF` 浮空边框。V4 已用 `0xFF`；若仍有
   外围灰边，只做 `0x3F/0xFF` 单变量 A/B，不同时改端点/LUT。
3. **重复 PTLW**：精确手册不要求 DRF 前再写一次；GxEPD2 的写 RAM 和 refresh 两阶段会
   各设一次。可作为交易顺序 A/B，但不能和 warm-session 同轮混测。
4. **reset/re-init**：Good Display 改编样例每步重初始化，GxEPD2 则支持持续会话；这是当前
   尚未实屏隔离的主要变量。
5. **窗口外扫描**：手册已明确窗口内外 gate 都扫描；没有公开的“窗口外 gate 不扫”开关。
   PSR 的 FOPT/VCMZ/NORG/VC_LUTZ 只描述波形结束和 VCOM 收尾，不得冒充局部 HOLD 开关。

## 7. 当前代码审查结果

V4 已满足：3-bit PSR、9-byte PTLW、PMODE=1、包含式端点、even-x/even-width、精确
`width*height/2`、无 DTM 前缀、CDI 0xFF、双 CS 独立窗口、同步刷新、1 MHz、BUSY 门和
超时、安全 POF，以及禁止 0x86/0x90/0x91/0x92。

本轮没有改动固件，因此既有 V4 BIN identity 保持不变。新增源码审计会固定：

- GxEPD2 相邻面板 `hasPartialUpdate/usePartialUpdate=true`；
- `hasFastPartialUpdate=false`；
- partial/full timeout 都是 15000 ms；
- `writeNative` 在 DTM 后直接开始像素传输；
- region refresh 使用 PON、PTLW、CDI 0xFF、DRF；
- 本地 V4 的严格 wire contract 与危险命令不可达性。

离线结果：GxEPD2 audit `5 passed`，V4 strict contract `6 passed`，Ruff PASS。

## 8. 后续测试优先级

1. `V5 cumulative full-frame` 作为“新颜色能否本身共存”的阴性/阳性控制。
2. `V4 strict PTLW` 仅回答 runtime LUT 下窗口外是否保持。
3. 若仍褪色，执行 **warm-session** 单变量版本，排除 reset/re-init。
4. 再做 `CDI 0x3F/0xFF` 与“DRF 前重复 PTLW”两个单变量，不混改。
5. 与上述并行离线准备 **LUT HOLD-code** 候选；只有零/平衡驱动候选被实屏证明后，才进入
   多调色盘逐层叠加。
6. V6 AB/BA 用于跨调色盘历史矩阵，但它不是 partial/HOLD 证明。

未经上述证明，不把局部寻址成功写成“256 色叠加已成立”。
