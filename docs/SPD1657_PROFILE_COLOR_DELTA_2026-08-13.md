# SPD1657 WF20/WF23 色彩实验差异定位

日期：`2026-08-13`  
判定：`STRUCTURAL DELTA PROVEN / COLOR CATEGORY AND FIELD ABI NOT PROVEN / NO HYBRID`

## 结论先行

后续真屏实验只把**同一 atlas 位置的色相或颜色类别变化**作为扩色线索。单纯明暗变化不算新颜色，
但仍单独记录亮度、饱和度、均匀性和残影。

`WF20_25` 与 `WF23_25` 不能直接做“只改变 LUT body”的真屏对比。两份完整厂家 profile 不仅有
`353` 个 11-byte body 坐标不同，7-byte prefix 的坐标 `1..4` 也不同；当前 empirical H3 构造会
把这些 prefix 坐标送入 PWR payload。PLL 来源坐标相同，构造的 `704×FF` R21 也相同，但这不足以
消除 PWR 混杂。

因此正确设计是两组各自闭合的 C/T 对照：

1. `C20`：使用 WF20 自身 header 的 factory init/PWR/PLL/PSR/TRES/E9，但不发 R20/R21；
   `T20`：完整、身份固定的 WF20 empirical H3。
2. `C23`：使用 WF23 自身 header 的同类 no-R20/R21 对照；`T23`：完整、身份固定的 WF23
   empirical H3。
3. 先分别比较 `T20-C20` 与 `T23-C23` 的逐格色相变化，再比较两组 effect；不直接把
   `T20-T23` 归因于 body 或某个结构块。

当前 `C20/T20` 软件包已存在并通过离线密封复核；`C23` 尚不存在。不能把 WF20 header 与 WF23
body 拼接，也不能替换单个 block/record。任何这种 hybrid 都会脱离厂家完整 profile 身份，且
没有同版 parser、checksum、block 独立性、双控接受或 panel/FPL 资格证据。

## 身份与精确差异

两份 profile 均由 identity-pinned 厂家 wrapper 在内存中解码，结构均为：

```text
7-byte opaque prefix + 9 blocks × 8 records × 11 bytes + 1-byte suffix = 800 bytes
```

| 区域 | 相同坐标 | 不同坐标 | 可安全表述 |
|---|---:|---:|---|
| 完整 800 bytes | 443 | 357 | 两份完整 profile 的 byte-level delta |
| prefix 7 bytes | 3 | 4 | 变化坐标为 1、2、3、4；不命名亮度/对比度 |
| body 792 bytes | 439 | 353 | 只称 9×8×11 结构差异 |
| suffix 1 byte | 1 | 0 | pair-level invariant；不命名 terminator |
| 72 个对位 records | 24 个完全相同 | 48 个有变化 | record 只作 11-byte 边界 |

WF20 decoded SHA-256：
`1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f`

WF23 decoded SHA-256：
`95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8`

## 九个结构块

下表索引严格为**零基** `block_index=0..8`。`block 5` 指第六块，`block 8` 指第九块；不得把自然
语言“第 5/8 块”混进结论。

| 零基 block | 不同 byte 坐标 / 88 | 有变化 records / 8 | bit Hamming | unsigned-byte L1 |
|---:|---:|---:|---:|---:|
| 0 | 36 | 6 | 74 | 3109 |
| 1 | 43 | 6 | 109 | 3486 |
| 2 | 48 | 6 | 105 | 3912 |
| 3 | 59 | 7 | 124 | 4941 |
| 4 | 55 | 8 | 117 | 3583 |
| 5 | 0 | 0 | 0 | 0 |
| 6 | 52 | 7 | 107 | 3232 |
| 7 | 60 | 8 | 108 | 4496 |
| 8 | 0 | 0 | 0 | 0 |

零基 block 5/8 在 WF20/WF23 中四者逐字节完全相同，均为同一个 88-byte uniform block，SHA-256：
`fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0`。报告不输出 uniform byte
值。这个事实不能升级成“空 category”“相同颜色”“no-op”或“termination”。

零基 block 7 只在 positional byte mismatch 指标上以 `60/88` 唯一最高，且只比 block 3 多一个
坐标。按 bit Hamming 和 L1，最高均是 block 3；按变化 record 数，block 4 与 block 7 并列。
所以不能笼统称 block 7“差异最大”，更不能称其负责某种颜色。

## 仍未恢复的语义

本次只闭合 profile-pair 的结构差异，不闭合下列 ABI：

- 九个 block 是否对应颜色 category、其顺序及像素码映射；
- 11-byte record 是否对应 phase group；
- 11 个 byte column 中的 polarity、repeat、duration、voltage 或 state-repeat；
- 全 uniform block、suffix 或 `FF` 的控制器语义；
- R20/R21 分工、controller-side 解码以及双控制器是否都接受 payload；
- `WF20_25`、`WF23_25` 文件名数字的温区、色彩档或电气语义。

SPD1656 的 `20×11-byte` 只属于公开 R20/VCOM，而其颜色 LUT 是 `20×13-byte`；SSD1683/1683A
虽有 8 groups，却是 `7-byte/group`。这些相邻资料不能拼成当前 `8×11` ABI。

## 真屏推进判定

近期只执行现有 `C20 → C20-white → T20 → T20-white` 四阶段矩形 atlas，对每个位置记录：

- 原始颜色词与是否出现新色相；
- 明暗与饱和度（只作伴随量，不计作新颜色）；
- 均匀性、边界、白边污染、残影；
- 温度、电流、电压、ESP32 重启和其他异常。

`C23/T23` 只有在为 WF23 建立独立固件身份、独立 no-R20/R21 C、独立 recovery、contract、action
ID、NVS namespace、release、trace、compiled-identity 和完整回归后才可进入现场。不得复用 WF20
的 C 结果冒充 WF23 对照。

## 可复现证据

- 工具：`tools/mf1750_spd1657_profile_color_delta.py`
  - 20123 bytes
  - SHA-256 `efe2171ad8edfcfb01ada5bb64d7128ccc18ecd96d78e3f0f3d4cbaf56fa5f73`
- 测试：`tests/test_mf1750_spd1657_profile_color_delta.py`
  - 9875 bytes
  - SHA-256 `2e61d19b66b2ea1440ed15afa5e2a4cd35baafeb1761a53c96062f08df2fcffe`
- 权威 JSON：`.test-output/offline/mf1750_spd1657_profile_color_delta_20260813.json`
  - 99087 bytes
  - file SHA-256 `755b99d62c57e57462bb716d72acb3029665a3faadba7b8af2b4007e5f735de7`
  - canonical SHA-256 `9b4b341244200ed8ce83d4bf1d40a8bbfa19ef33598f1470faad56d20ea9fd1e`
- 新工具与既有 invariant 工具联合：`11 passed in 0.51s`
- 复跑完整 matched trace 测试时发现唯一陈旧断言仍期待 V8 C BIN/ELF；只更新测试期望为 V10
  `f0ce5e7a...218e` / `27d23a21...d41`，没有修改 V10 密封的 firmware/host source。trace + 两项
  profile 工具联合：`20 passed in 4.05s`。
- Ruff check、Ruff format check：PASS。

报告与测试不输出 raw waveform、不生成或修改 runtime payload；本里程碑没有访问硬件、COM、设备
网络，没有刷写、刷新、token 或 claim。
