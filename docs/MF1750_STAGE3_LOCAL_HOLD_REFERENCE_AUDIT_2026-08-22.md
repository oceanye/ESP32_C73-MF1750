# MF1750 Stage-III 局部 HOLD 参考审查与集中测试手册

日期：2026-08-22  
状态：精确芯片手册、厂商样例、相邻面板实现与当前代码已完成交叉审查；
`y-inclusive` 修正版已离线构建，尚未刷写、尚未真屏验证

## 1. 结论

已经取得 Solomon Systech `SPD1657A Rev 1.0 (Aug 2021)` 数据手册，因而
`0x83/PTLW` 不再只是从相邻屏样例推测的实验 ABI。手册明确给出 9-byte 参数结构：
10-bit 水平起点、10-bit 水平终点、10-bit 垂直起点、10-bit 垂直终点和 PMODE；
终点是包含式地址，PMODE=1 才启用 partial。

对当前实现的结论是：双控制器结构、ROI DTM 长度、3-bit packed pixel 编码、同步
PON/DRF/POF 和 master BUSY 路径基本正确；原 live 变体唯一已经证实的窗口编码错误是
`y_end=y+h`，应改为 `y+h-1`。现有 `accumulate-symmetric-y-inclusive` 已恰好实现该修正。

但 PTLW 的含义是“局部 RAM/源地址窗口”，并不等于“窗口外电泳颜料完全不受电场”。
精确手册同时说明 partial 时窗口内外 gate 都会扫描，因此先前实屏得到的
**local addressing PASS / universal pigment HOLD FAIL** 仍然成立。Blue-2 褪灰不能用
多一行端点解释，必须作为波形/颜料状态保持问题单独资格化。

首轮只回答一个问题：在同一套原厂 OTP 波形下，依次刷新矩形 A、B、C 时，窗口外以及先前窗口能否保持不动。若能，才说明“先取色、再局部改写另一批像素”的基础机制成立。它不会在一次刷新中给 32/64 个区域装载不同 LUT；提升来自多次局部刷新后状态的累积。

## 2. 证据分级

| 等级 | 证据 | 能证明 | 不能证明 |
|---|---|---|---|
| A1：精确控制器数据手册 | `tmp/SPD1657A_Rev1.0.pdf`，44页，SHA-256=`29F9C4E2E9CBD6D1AAA4622DF4D2ECAC8A51A205701A616A96104D03659B89D0` | 0x83 的9-byte ABI、包含式端点、PMODE、800×600、cascade、DTM像素布局和 partial gate 行为 | 不能证明 MF1750 面板的颜料在窗口外对任意 OTP 波形均保持不变 |
| A2：本地 exact-chip 厂商样例 | `参考资料/REG-API-oqc(1)(1)/REG-API-oqc/Sample Code/E28xx.h` 标题为 `E2802-SPD1657_OTP.h`，定义 `DTM=0x10`、`DRF=0x12`、`LUT0=0x20`、`LUT1=0x21`、`PTLW=0x83`；`E28xx.c` 使用两颗512×600控制器 | 本板双控制器初始化、独立 DTM、共同 PON/DRF/POF 的结构与命令存在 | 样例本身没有调用 PTLW，不能单独证明局部窗口参数 |
| A：本屏现有驱动 | 已验证全屏路径采用双控制器、各 512×600、packed 4-bpp DTM、原厂 OTP PON/DRF/POF | 可以沿用已验证的电气、映射、刷新和恢复路径 | 不证明局部刷新窗口端点语义 |
| B：相邻 7.3-inch Spectra 6 官方样例 | Good Display 的 800×480 GDEP073E01 指定区域样例使用 `0x83 + 9-byte rectangle`、`x+w-1/y+h-1`、裁剪 DTM、原厂 OTP PON/DRF/POF | 独立支持精确手册的包含式端点和总体交易顺序 | 它的分辨率和板级连接不是 MF1750；其 DTM 后多发的一个 `0x00` 与精确手册冲突，不能照抄 |
| B：独立实现交叉核对 | GxEPD2 对 GDEP073E01 使用 0x83、裁剪 DTM，并在 DTM 前及 DRF 前重复 PTLW | 支持 PTLW 寄存器保持、裁剪 DTM 和同步刷新这一总体架构 | 其 `ye=y+h` 明示为该控制器/面板的 one-more workaround，与精确 SPD1657A 手册及厂商样例冲突，不能覆盖精确合同 |
| C：相邻控制器 | 本地 `Solomon-SPD1656.pdf` 有窗口/PartialRAM/LUTC 说明；Good Display 的 SSD2680A 资料也把 0x83 标为 Partial Window | 说明 Solomon 相邻族存在“窗口外由 LUT 条目决定”的架构 | SPD1656/SSD2680A 的命令布局、LUT 长度与 SPD1657 不同，禁止直接移植寄存器或 LUT 表 |

在线参考：

- https://www.good-display.com/product/533.html
- https://www.good-display.com/companyfile/1908.html
- https://drive.google.com/file/d/1U1hq4dhr821CVItF9kOPBJRxhkNMd6Rb/view
- https://github.com/frankalicious/E1002_partial_update
- https://www.good-display.com/product/392.html
- https://github.com/ZinggJM/GxEPD2/blob/master/src/epd7c/GxEPD2_730c_GDEP073E01.cpp

## 3. 固定实现

八个固件均固定为 3.3 V 逻辑、SPI mode 0、MSB first、1 MHz，沿用原厂 OTP 双控制器同步全局刷新。0x83 参数、矩形、颜色码和动作顺序均编译期封闭；不存在原始坐标、原始帧、原始 LUT 或任意命令入口。

精确芯片窗口合同应固定为：

```text
x_start, x_end=x+width-1, y_start, y_end=y+height-1, PMODE=1
```

每个控制器使用自己的 0..511 x 坐标；两个 CS 始终先写入匹配窗口，再同步刷新。首轮不做单 CS 刷新。
原 `accumulate`、`vmirror`、`symmetric-v2` 和 `Blue-1` 变体保留了相邻 GxEPD2 的
`y+h` workaround，仅作为历史对照，不再作为正确 SPD1657A 合同。所有新局部刷新实现
都应从 `y-inclusive` 路径派生。

| 变体 | 目的 | 固件 BIN |
|---|---|---|
| `accumulate` | 两个不相交窗口，再在 A 内嵌套覆盖 C；验证 A/B 是否被 HOLD | 788,080 bytes / `b59b8da904a62049e14a133b5d6ecf8d60d86d0a8b11aa815096ff6373e50eba` |
| `edges` | 左边界、右边界、靠下安全边界；验证几何和端点 | 788,048 bytes / `7729107335a98f4746be8e6ba72f815aa4efdf45a70d5b261fd1c6320a9c4542` |
| `cs-split` | 同一窗口给 CS1/CS2 不同颜色；验证双控独立数据且同步保持 | 788,256 bytes / `9a74b75816bfe05667f5f929054e42afb311073c7425803b2c4a70063aee6889` |
| `accumulate-vmirror` | CS1 使用原 y，CS2 垂直镜像；两个控制器分别写入 0x83，用于区分环境梯度与 gate/scan 位置效应 | 788,176 bytes / `5af06182af1bc372495c668a2594b8d7011ae6d8b4ba7948a6eb23f381948cc7` |
| `accumulate-symmetric-v2` | CS1/CS2 使用完全相同的 y，但仍分别写入 0x83；仅移除垂直镜像变量 | 788,176 bytes / `f0b949500e8ee67c9a51d2f874d257fe338570138a39e857c16dbad581817e69` |
| `accumulate-symmetric-y-inclusive` | 正确包含式端点；PATCH_B=code5/经验 Blue-2 | 788,224 bytes / `503519a1b9a9a66f1b845b5da8ef0d83b03e923ba747596e8ef311e6cb73fdd9` |
| `accumulate-symmetric-blue1` | 历史几何对照：旧 `y+h`，PATCH_B=code4；不作为最终颜色比较 | 788,176 bytes / `0ef453400cf78c9a7fb2de2a26283670de218e834994da2a2f5f4de7fe1a1769` |
| `accumulate-symmetric-y-inclusive-blue1` | 正确包含式端点；PATCH_B=code4，供 code4/code5 严格比较 | 788,256 bytes / `64a6102e53abaf010ad0ea7b5679c62fc17e627251a8a649b8d0540779dda71a` |

上表是加入刷新后 HTTP listener 恢复逻辑后的最新**离线产物**。真机当前仍是旧 symmetric-v2 `788,080 bytes / 24c73a9...0385e`，不能把上表的新 symmetric-v2 identity 冒充为已刷入。

每个变体固定五个动作：

```text
1 全屏原厂白基线
2 PATCH_A
3 PATCH_B，并观察 A 是否保持
4 PATCH_C，并观察 A/B 或未覆盖部分是否保持
5 独立全屏原厂白恢复
```

关键文件：

- `tools/mf1750_partial_hold_matrix.py`
- `src/ec5_partial_hold_driver.inc`
- `src/ec5_partial_hold_identity.inc`
- `src/ec5_partial_hold_epd_driver.cpp`
- `src/ec5_partial_hold_main.cpp`
- `platformio.partial_hold_matrix.ini`
- `tools/mf1750_partial_hold_once.py`

## 4. 集中真屏顺序

只先测试 `accumulate`。返回现场后必须 fresh 确认 J2=OFF，才允许 app-only flash、独立 verify 和 GET-only identity/READY；这些都不授权打开 J2 或刷新。

每个 action 都需要独立诊断、永久 claim、一次 ARM、一次 EXECUTE，并在人工观察门停止。运行器不会刷固件、不会控制继电器、不会 retry、不会 recovery、不会 autochain。

判定：

- `PASS-HOLD`：A 后背景不变；B 后 A 基本不变；C 后 B 和 A 的未覆盖部分基本不变；左右控制器行为一致；最后能恢复干净白。
- `FAIL-HOLD`：窗口外发生明显重驱、先前窗口被重置/改色、左右不同步、边界越界、BUSY 异常或无法白屏恢复。
- `INCONCLUSIVE`：只有轻微明暗/残影，肉眼不能区分真正 HOLD 与弱全局驱动。

只有 `accumulate=PASS-HOLD` 才释放 `edges`；只有边界行为正常才释放 `cs-split`。任一失败即停止局部路径，不把后续 LUT 叠加建立在未证实的 HOLD 上。

## 5. 安全边界

- 不使用 0x86；本地相邻样例把它用于 dither area，不是局部刷新合同。
- 不写 OTP/NVM，不扫 0x00..0xFF，不改 VCOM/高压，不做电压或 SPI sweep。
- 不在刷新中切电，不使用机械继电器做波形截断。
- 不把局部窗口成功等同于局部 LUT 成功。首轮只有 factory-OTP HOLD。
- 每个变体以独立全屏原厂白恢复收口；疑似永久偏色、固定线条、异常 BUSY、限流或发热立即物理断开并停止。

## 6. 离线验证结果

- 八个 PlatformIO 环境均构建成功。
- HOLD fixture/runner 合并回归：`15 passed`。
- `py_compile`：PASS。
- Ruff：PASS。
- 首轮离线准备过程：0 relay、0 device-network、0 COM/serial、0 flash/reset、0 visible refresh；后续真屏动作见第7–8节。

## 7. accumulate-vmirror 真屏结果与原因判定

`white → PATCH_A(红) → PATCH_B(蓝) → PATCH_C(红内嵌绿)` 的实测结果是：

- white 全屏干净；
- A 的两个红格上下镜像，背景保持全白；
- B 后原红格保留，两个控制器各新增一蓝格；
- C 能在红格内准确新增绿色，但窗口外旧蓝格被改写：CS1/左侧变灰，CS2/右侧呈渐变。

离线复核排除了简单的帧几何错误：B 为 `x=304..463`，C 为 `x=80..175`，二者不重叠；C 的裁剪 DTM 为每控制器 `96×80/2=3840` bytes，实测 FNV/SHA 与固定身份一致；预期累积帧在 C 后仍包含蓝色 code5。

因此最强解释是：0x83 的窗口定址和裁剪 RAM 写入有效，但随后仍调用普通原厂 OTP 全局刷新序列；窗口外并非对所有颜料状态都是理想零场。白色和已有红色在本轮基本保持，而蓝色对后续波形更敏感。左右差异又与镜像后的高/低 gate 位置一致，支持 scan 位置/时相历史效应，不支持环境光作为主因。

工程裁决为 **local addressing partial pass / universal pigment HOLD fail**。当前路径不能用作任意颜色多调色盘叠加的基础；仍可以通过固定“旧颜色 × gate 位置”的资格化 atlas，查找可靠保持的受限状态集。

## 8. accumulate-symmetric-v2 单变量对照

该变体的 CS1/CS2 矩形坐标完全一致，两者仍各自收到独立 0x83 命令，因此相对 vmirror 只移除“CS2 垂直镜像”一个变量。

真屏结果：

- white 基线通过；PATCH1 后两红格同位；
- PATCH2 后操作者确认“红蓝 ok”；
- PATCH3 后 Blue-2 逐渐隐去并最终呈灰；
- 红绿边界靠下侧的白缝不连续且不等距，其余三边的白缝等距。

PATCH_B 的固定传输码是 `5`。C20/C23 已经真屏确认映射 `0..7 = 黑/白/黄/红/Blue-1/Blue-2/绿/Blue-1`，因此本轮褪灰的是第7种独立颜色 **Blue-2**，不是 Blue-1。

对称结果排除了“CS2 镜像坐标计算错误”作为 Blue-2 褪灰的主因；vmirror 中原 y 位置变灰、镜像 y 位置呈渐变，而 symmetric 中两者都处于原 y 位置并同样变灰，反而进一步支持 y/gate 位置影响褪色外观。

单一下边异常与原实现的 `y_end=y+h` 精确吻合。现已取得 SPD1657A 手册，包含式终点
不是待猜测的候选而是确定合同：应使用 `y+h-1`。下一步仍只上机验证现成
`y-inclusive`，因为真屏必须确认手册合同在该板级实现上也恢复下边界；不得同时改颜色、
CDI、初始化或刷新序列。

## 9. 离场期间完成的单变量解决方案

操作者离场后只进行了离线工作，未访问继电器、设备网络、COM/串口，也未刷写、复位或刷新真屏。

### 9.1 下边界合同对照

`accumulate-symmetric-y-inclusive` 保留 symmetric-v2 的矩形、颜色、动作顺序和双 CS 对称布局，仅把发送到 0x83 的 y 终点从 `y+h` 改成 `y+h-1`。这已经是精确手册要求的正确编码；真屏动作只验证边界恢复，不承担 Blue-2 HOLD 结论。

### 9.2 Blue-1 保持对照

`accumulate-symmetric-blue1` 保留原 `y+h`、全部几何与动作顺序，仅把 PATCH_B 从 code5/Blue-2 改为 code4/Blue-1。它用来回答 Blue-2 褪灰是该颜料状态特有的后续波形敏感性，还是所有蓝色都会发生；不承担端点结论。

### 9.3 长刷新后的主机可达性

既有固件在约35秒同步刷新期间阻塞主循环，导致 HTTP listener 在动作完成后失去可达性。新 partial-HOLD 固件在动作报告落盘后显式重启 listener，runner 也把首次终态轮询下限固定为40秒，避免在阻塞窗口内制造陈旧连接。该改动已通过源码合同和离线 runner 测试，但必须等下一次真屏动作才能判定 live PASS。

### 9.4 返回后的集中顺序

1. 操作者返回后 fresh 确认现场；J2 保持 OFF 时仅刷入 `y-inclusive`、独立 verify、GET-only identity/READY。
2. 接通 J2 后依次执行 `white→red A→Blue-2 B→green C→white recovery`，每步停在人工观察门；重点看下边白缝是否恢复连续，且照常记录 Blue-2 是否褪灰。
3. 完整白恢复并重新 J2 OFF 后，才刷入 `y-inclusive-blue1` 变体，再执行同样五步；重点比较 PATCH_C 后 code4 与先前 code5 的保持情况。
4. 两组最多10次可见动作；无新动作会在操作者离场期间启动，也不会自动串行、retry 或 recovery。

若第一组直接出现越界、固定线条、异常 BUSY、异常电流/发热或无法恢复白屏，立即停止，不释放第二组。若 `y+h-1` 修复边界而 Blue-2 仍褪灰，则几何与颜料 HOLD 可被清楚拆分；若 Blue-1 能保持而 Blue-2 不能，则后续多调色盘叠加只能先限定在已逐项资格化的状态集合内。

## 10. 当前局部刷新代码逐项审查

| 项目 | 当前实现 | 审查结论 |
|---|---|---|
| 双控制器拓扑 | 两颗控制器各512×600；窗口和 DTM 分 CS 写入，PON/DRF/POF 共同发送，master BUSY 判定 | 与 exact-chip 样例和手册 cascade 结构一致 |
| PTLW 命令 | `0x83`，完整发送9个参数 | 正确；命令只在全部参数写完后生效 |
| X 终点 | `x+w-1` | 正确 |
| Y 终点 | 历史 live 为 `y+h`；`y-inclusive` 为 `y+h-1` | 历史值多一行；`y-inclusive` 正确 |
| PMODE | 固定1 | 正确；0会关闭 partial，禁止把 mode0 当作“只扫窗口”候选 |
| DTM 像素布局 | 每字节两个3-bit像素，nibble中高位为0，ROI发送 `w*h/2` bytes | 与手册一致；当前代码没有厂商相邻样例里可疑的额外 `0x00`，这是正确选择 |
| 窗口与 DTM 次序 | PTLW 后立即写该控制器的裁剪 DTM，再共同刷新 | 有效；精确手册未要求 DRF 前重复 PTLW |
| CDI | partial 前使用 `0xFF` | DDX仍为非反相，border为HIZ；与样例常见 `0x3F` 有差异，但不应与端点修正同时改 |
| 每动作重新初始化 | `epdPrepareCascade(1MHz)` 后执行 | Good Display 指定区域样例也每次 reset/init，不能据此解释 Blue-2 褪灰 |
| SPI | 固定1MHz，mode0，MSB first | 低于手册上限，适合作为固定基线；当前阶段不做频率扫描 |
| 窗口合法性 | 目前只强制 x/width 为偶数，且历史边界判断偏保守 | 当前固定窗口安全；后续代码宜把 x/width 固定为4像素粒度，并按包含式终点允许 `y+h<=600` |

## 11. 为什么“地址局部”不等于“颜料 HOLD”

PTLW 限制的是被写入的源数据范围，但手册明确 partial 期间窗口内外 gate 都参与扫描。
这意味着窗口外没有新 DTM 数据，不代表其像素承受的 VCOM/公共驱动历史为零。不同颜料
状态对后续全局 gate 扫描的敏感度可以不同，因此当前实测组合完全自洽：

- 红格、白背景和新绿格能保持清楚，证明矩形地址与裁剪数据确实工作；
- 下边白缝少一行/不等距，符合 `y+h` 多覆盖一行；
- 与 C 窗口远离的 Blue-2 逐渐变灰，不可能由这一行越界直接覆盖；
- 左右对称布局仍出现 Blue-2 衰退，排除了镜像坐标错误为主因。

所以修正端点后，局部路径的工程目标不是立即宣布“任意8/16色可以叠加”，而是建立
“旧状态在后续局部刷新中能否保留”的资格表。只有经验证可保持的状态子集，才能用于
多轮调色盘叠加。

## 12. 不混变量的下一轮真屏顺序

1. 只测试已经构建的 `accumulate-symmetric-y-inclusive`：
   `white → red → code5/经验 Blue-2 → green → white`。首要判据是下边白缝是否与另三边等距；
   Blue-2 是否继续褪灰只作并行记录。
2. 第一组完整白恢复并断电后，另行测试已经完成并绑定的
   `accumulate-symmetric-y-inclusive-blue1`。历史 `accumulate-symmetric-blue1` 仍保留错误
   `y+h`，不再用于最终颜色比较。
3. 若 code4/code5 至少有一个能跨后续刷新稳定保持，再构建原厂六状态 retention matrix：
   逐项检查“旧状态 × 新patch状态”，不先动 runtime LUT。
4. 只有存在稳定保持子集，才把阶段三 LUT 新调色盘加入局部叠加；否则局部地址虽成立，
   多调色盘累积路线仍不可用。
5. 若端点正确后仍需查交易差异，按顺序做单变量 A/B：`CDI 0x3F vs 0xFF`、
   `DRF前是否重复PTLW`、exact-chip 初始化与当前已验证初始化。每轮只改一项。

颜色名称仍需谨慎：本项目实屏经验把 code5 称为 Blue-2、code4 称为 Blue-1；相邻厂商
六色样例把 code5 作为其 delivered blue，却没有为本板证明 code4 的正式名称。因此代码、
日志和资格表应始终同时记录数值 code，颜色词只作为观察标签。

## 13. 明确拒绝从样例照抄的内容

- 不复制 Good Display 相邻样例在 DTM 后多发的额外 `0x00`；精确手册规定 DTM 后直接是像素流。
- 不复制 GxEPD2 的 `y+h` one-more workaround；它与精确手册和厂商相邻样例的包含式终点冲突。
- 不把 PMODE=0 作为另一种局部扫描；它会关闭 partial。
- 不把单次 PTLW 成功外推为窗口外零电场或任意颜色 HOLD。
- 不在本轮同时更改 LUT、CDI、BTST2、初始化顺序、SPI 或电源时序。
