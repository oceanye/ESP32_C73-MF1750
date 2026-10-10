# MF1750 Stage-III 参考优先 LUT 搜索空间

状态：`OFFLINE ANALYSIS + BUILT CANDIDATES / NOT LIVE-AUTHORIZED`

## 1. 结论

理论上的 LUT byte 空间近似无限，不能穷举；可执行的工程搜索空间必须由已知完整表和公开结构逐层扩展。

当前可直接排程的是：

- 本地 exact-chip 资料中的2份完整535-byte表形成2个屏幕级参考候选；
- 原有8个屏幕级 pure-field 候选；
- 合计10个 treatment、每屏16个端点，共160个端点观察；
- 每个 treatment 均绑定独立 factory-OTP white recovery，最多20次可见刷新。

这不是160种独立 waveform，也不代表最多能得到160种新色。一次全局刷新中，每个控制器仍只有一套 waveform，像素通过3-bit code 0..7选取该表内的八个入口。

## 2. 证据分层

### A. exact-chip 本地资料

`参考资料/REG-API-oqc(1)(1)/REG-API-oqc/Sample Code/E28xx.h` 标题为 `E2802-SPD1657_OTP.h`，给出 R20/LUT0=`0x20`、R21/LUT1=`0x21`、PTLW=`0x83`。

`参考资料/REG-API-oqc(1)(1)/REG-API-oqc/User/EDP_init.c` 含两份完整535-byte表：

- 活动表 SHA-256：`716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`；
- 注释表 SHA-256：`2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26`。

两表均为7-byte header，后跟 `VCOM/Black/White/Yellow/Red/Power × 8 groups × 11 bytes`。活动表是最高证据候选；注释表虽完整，但用途、面板批次和温区未知。

### B. 相近 Solomon SPD1656 公开资料

本地 `参考资料/Solomon-SPD1656.pdf` 只作为结构边界：

- 3-bit RAM code 000..111 对应 LUT0..LUT7；
- waveform 由 repeat/time phase 组组成，TP=0可跳过；
- 提供 FullRAM/PartialRAM 和 window 结构；
- 其 LUT0/VCOM 与 LUT1..8 有公开长度。

这些信息支持优先测试 code 0..7、成组相位和未来 HOLD/window 假设，但不证明 SPD1657 使用相同寄存器地址、字节长度或电压编码。

### C. 相近面板和官方公开资料

Good Display 的相近 E6 面板公开指定区域样例，证明同一产品生态存在 partial/specified-area 实现路径；E Ink 官方第二代 waveform 资料表明升级的3-bit芯片/波形可将 Spectra 6 扩展到八个 primary colors。它们是方向证据，不是本板 ABI 或可直接使用的 payload。

### D. 专利

公开专利中存在 seed waveform、短扰动和分阶段粒子混合方案。它们只能指导逻辑分析仪到位后的波形分类和光学闭环，不用于生成当前 SPD1657 寄存器或 LUT 数据。

## 3. 理论搜索空间

如果把每个字节都视为独立自由变量：

- 535-byte 表：`256^535 ≈ 10^1288.4`；
- 799-byte 容器：`256^799 ≈ 10^1924.4`。

这说明 byte-level 穷举不可能，而且绝大多数向量都可能是无效或危险配置。

即使只在两份完整表之间做组合：

- 按6个颜色/电源 category 二选一：`2^6 = 64`；
- 按48条11-byte record 二选一：`2^48 ≈ 2.81×10^14`。

对现有799-byte WF20/WF23 body，若按9个大 block 二选一也有 `2^9=512`，按72条11-byte record 二选一则约 `2^72≈4.72×10^21`。

这些只是数学上界，不是测试计划。没有字段 ABI、直流平衡和电压语义证明时，不进行 category/record/byte 拼接。

## 4. 实际分层枚举

| 层级 | 内容 | treatment屏 | 端点 | 状态 |
|---|---|---:|---:|---|
| Tier A | 两份完整 legacy 535 表，两个共享 header 对照 | 2 | 32 | 已构建，第一优先 |
| Tier B | M0 与已实测 H3 控制 | 4 | 64 | 已构建，按需 |
| Tier C | H1/H2 结构拆分假设 | 4 | 64 | 已构建，最后 |
| Tier D | category/record mutation | 未定 | 未定 | 禁止，等待 ABI/逻辑分析 |
| Tier E | byte mutation/未知命令盲扫 | 不适用 | 不适用 | 永久不作为当前路线 |

若只追求尽快发现新色：先 HOLD `accumulate`，然后 Tier A；Tier A 无新均匀色再进入 M0。H3 可作已知控制，H1/H2 最后。只要命中疑似均匀稳定新色，就停止广搜，转左右互换、重复性、白恢复和色卡标定。

## 5. 与局部 HOLD 的关系

HOLD 是未来叠加多套调色盘的先决条件，但不能把“窗口内像素数据不同”误称为“窗口独立 waveform”。当前只先验证 factory-OTP 下局部写入/保持是否成立。HOLD 未真屏证明前，不把 partial/window 与 runtime LUT 合并。

逻辑分析仪不是 Tier A 的执行前置，但它是继续进入字段拼接、相位缩短和电压级解释的重要证据工具。没有逻辑分析仪时仍可测试完整候选；不能据此宣称已理解 LUT 格式。

## 6. 固定禁区

- 不枚举3-bit之外的 code 8..15；
- 不套用 SSD1681/SSD1675B/UC8179/GD7965 命令；
- 不做 `0x00..0xFF` 命令扫描；
- 不写 OTP/NVM；
- 不扫 VCOM/高压寄存器；
- 不在刷新中断电；
- 不把相近芯片的 R20/R21 长度或 window 地址当作 SPD1657 事实。
