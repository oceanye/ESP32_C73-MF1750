# MF1750 阶段三：局部刷新样例审查与晚间离线批次

## 1. 结论

本地样例中确实存在会被 `loop()` 实际调用的局部刷新代码，不只是注释或未引用函数。
它证明的范围是：SPD1657A/GDEP073E01 相邻方案支持用 `0x83` 设置 RAM 窗口，然后以
`0x10` 写裁剪后的图像数据并触发一次全局扫描。它不证明窗口外像素获得零电场 HOLD，
也不证明相邻单控制器样例可以不经修正直接复制到当前 1024×600 双控制器板。

## 2. 样例中的实际路径

`tmp/E1002_partial_update/src/GDEP073E01.ino` 的执行路径为：

1. `EPD_PartialWindow()` 在第 81 行定义。
2. 第 85–96 行发送 `0x83` 和 9-byte 窗口；终点按
   `x+width-1 / y+height-1` 计算，PMODE=`0x01`。
3. 第 100 行发送 DTM `0x10`，第 103–118 行只写窗口大小的 4-bpp 数据。
4. 第 122–133 行执行 `PON → BTST2 → DRF → POF`。
5. 第 184–196 行的主循环先 `EPD_init()`，再实际调用两次局部更新，随后
   `EPD_sleep()`；不是未使用的演示函数。

另一个相邻实现 `tmp/GxEPD2_730c_GDEP073E01.cpp` 的
`_setPartialRamArea()` 同样发送 `0x83`，但把 `y_end` 写成 `y+h` 并标注
“controller issue (one more)”。SPD1657A Rev1.0 命令表给出的 PTLW 是包含式终点，
因此当前板的严格基线继续使用 `y+h-1`；`y+h` 只保留为相邻库的差异性线索。

## 3. 不能照抄的一个字节

相邻 `.ino` 在 `0x10` 后先额外写一个 `0x00`，注释称其为像素格式。SPD1657A 手册的
DTM 定义没有独立格式前缀：命令后紧跟像素数据。因此该 `0x00` 应视为窗口的第一个
像素数据字节；照抄会令后续裁剪 payload 发生一字节偏移。当前 V4 的 DTM 路径不发送这个
额外前缀。

## 4. 为什么“局部地址成功”仍可能使旧颜色变灰

SPD1657A PTLW 说明明确写出：partial window 内外的 Gate 都会扫描。`0x83` 限定的是
后续 RAM 写入区域，不等价于窗口外 Source/Gate 波形为零。于是已经观察到的行为并不矛盾：

- 新的红/绿局部块可以出现在正确坐标，说明窗口寻址有效；
- 旧蓝块在下一次 DRF 后逐渐变灰，说明窗口外仍受扫描，而其 SRAM 码位或当前 LUT 下的
  波形没有形成稳定 HOLD；
- 外围灰边与底侧黑白间隔也更像全局扫描/边界状态，而不是简单坐标覆盖。

当前工程结论仍是 `partial addressing PASS / universal HOLD FAIL`。还不能据此宣称能够通过
多轮局部刷新叠加到 16 色、256 色或照片级多调色盘。

## 5. 晚间三路线批次

### A. V4：严格 PTLW 单变量复核

- 全白基线与恢复：实测可工作的 packed full-frame code7。
- 三个局部动作：code3 暗、code5 蓝、code6 绿。
- `0x83` 为包含式终点，双控制器分别下发，裁剪 DTM，无额外 `0x00`。
- 目的：确认修正白底传输后，真正的 PTLW 是否仍导致旧 ROI 漂移。
- BIN：793,728 bytes；SHA-256
  `e3315ba1a337e041c156728693c4db92c9463ef195296ebaef351b7c07e5ad9c`。

### B. V5：累计整帧重绘控制组

- 五动作仍为白 → A → A+B → A+B+C → 白。
- 每次都把累计画面作为完整 1024×600 帧重发；从不发送 `0x83`，也不发送裁剪 DTM。
- 目的：区分“窗口外 RAM 未重写”与“L535 波形本身让旧蓝不稳定”。
- 这不是局部 HOLD 成功方案，而是必要的归因控制组。
- BIN：793,264 bytes；SHA-256
  `fdb9852a4414f7a50e09dd6088debc95a92fecf067562504ccdadbac34841068`。
- ELF：13,266,028 bytes；SHA-256
  `36ad9671ce1b07de295e8466acd499b81c6690f9a0183c0c522a87bade91c11d`。

### C. V6：双向 8×8 跨调色盘历史矩阵

两份固件都只做 full-frame global refresh，不发送 PTLW：

- AB：active global header 的 8 条 source 横带 → commented global header 的
  8 条 target 竖带；每控制器一次得到 64 个 source→target 历史格，两控制器共 128 格。
- BA：反向执行 commented → active，再得到 128 格。
- target 图案在同一 target profile 下重复一次，用来判断候选颜色是稳定终态还是继续漂移。
- 两个方向合计 256 个观察格；它们是单像素纯码区域，不使用空间抖动。

固件绑定：

| 方向 | BIN bytes / SHA-256 | ELF bytes / SHA-256 |
|---|---|
| AB | `793936 / bb1ce7b755562957f109cdc45e3100f85fb76d88d18eef2ce17eeff61aa2bd0d` | `13269080 / 63308d912efd5e8968c7d2c4ad7db1864affc9f9c7a55f1d484de7390bd9cb2d` |
| BA | `793920 / bcfbac6528cf2a8d1a5475023b3ab5ee1152de307ee62a483545586576b7b371` | `13269036 / c0087626c937c034c38cf61563b806df956c921b7515adbc1aa02df4f679a92e` |

> **2026-08-24 编译修订（不改写上表的历史工件）：** 上表版本在 J2 OFF 的
> compiled-fixture self-check 中被安全拒绝，未进行面板 I/O。根因是 AB/BA packed
> controller DTM fixture 错误地走了 uniform/window DTM identity 分支。修复并新增回归后，
> 当前 AB BIN/ELF 为 `793840 / e56649be80b67602d6b1da46e6a0ca1f6ff295e1fa601e9d1b9291902f4573ca`
> 与 `13268060 / 21acf287ec2c6504418813878decb20dabb6e398e0e2929a7ba806ddbe6f8939`；
> BA 为 `793824 / fc328a5bbb7d723b6b1e4ccc0cacec6c574041f4b67b9dd84c7351fcf18bc646`
> 与 `13268020 / 6320735405e07b1ce1f0d8ae39485b8d34b154f7c72be6c75b0793da5e206328`。
> 仅修订后的 AB 已上机并完成 5/5；BA 仍仅离线。

## 6. 晚间执行顺序

1. V4 先做：若 A/B/C 均保持且白底/边缘正常，局部 HOLD 才取得新的通过证据。
2. V4 若再现旧蓝灰化，停止其剩余局部动作并做白恢复；随后执行 V5 控制组。
3. V5 若累计整帧稳定，故障重点落在 PTLW 窗口外 SRAM/扫描；若 V5 仍灰化，故障重点落在
   L535 波形/码位稳定性。
4. 完成白恢复后可分别执行 V6 AB 与 BA。只在 source、target、target-repeat 三个可见节点
   需要人工观察；发现均匀新色才做后续照片与左右复核。

每个 runner 固定一次 ARM + 一次 EXECUTE，无 retry、fallback、recovery 或 autochain；
不使用 `0x86`、未知命令、刷新中切电、VCOM/高压或 SPI 扫频。固件编译、精确哈希绑定、
20 项 V4/V5/V6 联合测试、Ruff 与 `py_compile` 均已通过。

## 7. 当前离场状态

截至 `2026-08-23 13:36 +08:00`，上述工作全部为离线代码、构建和校验。没有访问继电器、
设备 HTTP、COM/串口，没有刷写、复位或刷新。现场仍按最后确认保持 relay channel 1 OFF；
ESP32 仍运行 controller-code-map V1，屏幕静态保留 16-field map。
