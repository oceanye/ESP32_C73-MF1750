# MF1750 全帧基准 / PTLW 局刷 A/B 与 8×2 标定门

日期：2026-08-25  
状态：**V1/V1B LIVE SEALED；A/B处理未执行；V1B在PON超时后FAULT；屏幕目前全白，relay OFF；仅允许离线取证。**

> 2026-08-25 20:02更新：本页第4节是已经中止的原始五动作计划，不再是可直接执行的
> 操作卡。原V1只完成ordinal1白健康锚；V1B fresh ordinal1在PON阶段超时。两个campaign
> 均不得重试、清NVS后伪装fresh或跳ordinal继续。

## 1. 目的

既有 Endpoint 与上下 guard 处理都未清除蓝块底边连续黑线。guard 两种方向的人工观察
结果相同，因此不再继续调整 guard 宽度。本轮只比较 SRAM 寻址运输方式：

- A：完整控制器 DTM，不发送 PTLW；
- B：先写完整 code7 预装帧，不刷新，再发送一次包含式 PTLW 和窗口内 code5 DTM；
- A/B 的最终控制器 SRAM、逻辑像素、运行时 L535 profile、刷新序列和可见蓝块完全相同。

这不是直接宣称修复，而是用最少变量判断黑线属于 PTLW/PMODE/有限窗口路径，还是属于
运行时波形/目标边缘本身。

## 2. 从两个 STM 参考工程保留的内容

本轮综合采用了参考工程中已经可证的结构，不直接移植未知整套初始化：

- 双控制器分别写入 DTM；
- 两个控制器共同执行 `PON → DRF(0x00) → POF(0x00)`；
- PTLW 使用 9-byte 包含式坐标，`xe=x+w-1`、`ye=y+h-1`；
- 局部 DTM 只发送窗口对应的 9600 bytes，不增加首尾填充字节。

运行时 action-stage 不额外发送 CDI、BTST2、PON 后重复 PTLW或 `0x86`。这句话只限定
处理阶段；沿用的现行 `epdPrepareCascade()` 初始化仍包含既有 CDI/BTST2 配置，factory-OTP
白动作也沿用共享 BTST2 刷新路径。

## 3. 冻结画面与传输

两控制器本地窗口均为：

```text
x = 176..335
y = 240..359
width = 160
height = 120
target code = 5
outside/prestage code = 7
PTLW = 00 B0 01 4F 00 F0 01 67 01
```

| 项目 | A：全帧基准 | B：PTLW 局刷 |
|---|---:|---:|
| code7 预装、无刷新 | 153600 B/controller | 153600 B/controller |
| PTLW 次数 | 0 | 1/controller |
| 目标 DTM | 完整复合帧 153600 B/controller | code5 crop 9600 B/controller |
| 合并传输流 | 307200 B/controller | 163200 B/controller |
| 最终逻辑画面 | 相同 | 相同 |
| 可见刷新 | `PON→DRF00→POF00` | `PON→DRF00→POF00` |

逻辑帧 SHA-256：
`c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576`。

## 4. 原固定真屏顺序（已冻结）

以下表格保留最初设计意图和未完成的A/B变量控制。它不再授权任何动作；新批次必须使用
新的identity、NVS namespace/key和claim目录，并通过第8节的新门。

| ordinal | 动作 | 需要人工观察 |
|---:|---|---|
| 1 | factory-OTP 白健康基线 | 全白是否干净 |
| 2 | A：完整 DTM 蓝块 | 两侧蓝块四边，尤其底边是否连续黑线/齿线 |
| 3 | factory-OTP 白交叉复位 | A 是否完全清除 |
| 4 | B：PTLW 局刷同一蓝块 | 与 A 同口径观察，外围白区是否受扰 |
| 5 | factory-OTP 白恢复 | 蓝块和边线是否完全清除 |

每个动作各自只有一次 ARM、一次 EXECUTE、一次 driver call 和一次可见刷新；无 retry、
autochain 或自动恢复。异常时停止并断开驱动板电源，不跳过 ordinal 直接调用主序列末尾白屏。
既有独立 factory-OTP 白收容产物只作为故障后另行恢复手段。

## 5. A/B 裁决

| A | B | 结论与下一步 |
|---|---|---|
| 干净 | 有线 | PTLW/PMODE/有限窗口路径是主要嫌疑；下一项才做全控制器 PTLW + 完整 DTM 的 C 组 |
| 有线 | 有线 | 更支持运行时波形或目标边缘问题；停止继续微调 PTLW 端点/guard |
| 有线 | 干净 | 更支持完整复合 DTM 重驱外围导致边线 |
| 干净 | 干净 | 获得参考最小局刷候选；先重复 B，再进入正式标定 |

离线构建成功并不等于黑线已经解决。

## 6. 何时正式做 8×2 标定

可以标定，但必须先满足：

1. B 在左右控制器上都无连续黑线、齿线、灰边或窗外漂移；
2. factory-OTP 白能完整清除；
3. 从 fresh white 开始的 `B → white` 至少连续重复 3 轮，协议、BUSY和视觉都一致；
4. 后一次非重叠局刷不会改变前一次已保持区域。

通过后建立 `2 controller/profile × code 0..7 = 16` 个**名义槽位**。每个槽位分别记录：

- controller/profile、code、前态与刷新路径；
- 边界完整性、块内均匀性、重复漂移；
- 5 s、60 s、600 s 颜色与保持；
- 后续非重叠 patch 后的保留情况；
- factory-OTP 白清除结果；
- 24 色卡条件下的 Lab/ΔE。

16 个名义槽不等于 16 种独立颜色。左右或不同 code 的实测颜色必须按 Lab/ΔE 去重；只有
通过边缘、重复、保持和恢复门的槽位才能进入照片调色板。

## 7. 离线产物

- PlatformIO 环境：`ec5_runtime_lut_ptlw_fullframe_ab_v1`
- contract：`9e7414f483174cc74fa8adca9c1c2ea4c23c3250f84882969f34e87efb25a8fa`
- BIN：799408 B，SHA-256
  `6e42e3b08ec8053a3efea3e4f12d334dc246abb99576454188136391fa1130fb`
- ELF：13301880 B，SHA-256
  `b64d7216ff240df3a736542418cf263c0112bc03469388798e19c1fb34dcc405`
- 专项测试：12 passed；Ruff、`py_compile`、runner `describe`与 BIN/ELF 双绑定通过。

详细构建证据见
`docs/MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_OFFLINE_BUILD_2026-08-25.json`。

## 8. 真屏结果、故障边界与后续释放门

### 8.1 原V1

- BIN/ELF：`799408/6e42e3b0...30fb`、`13301880/b64d7216...c405`；
- boot：`35d91cbde71348d6`；
- ordinal1 factory-white成功，PON/DRF/POF=`180/22521/141 ms`，操作者确认干净白色；
- POF安全收尾后RST/CS/CS2保持低，raw BUSY稍后降为0。旧门把该状态拒绝为不可执行，
  因而ordinal2在0 claim/0 POST/0 refresh前停止；V1封存；
- A和B都没有执行，不能根据V1判断底边根因。

### 8.2 V1B

V1B增加RAM-only同boot late-POF资格，只允许上一动作完整成功且safe-finish证据满足时接纳
后续raw BUSY=0。final BIN/ELF与contract为：

- BIN：800224 B，`48fb0397948385feb2a0b155dca22bbb741e346df1a0edd7871c8765bd7181c3`；
- ELF：13303904 B，`a0b20e1a44847693027b7dfca9276d3e9ba1befbd89f735c07a8986db3885d8d`；
- contract：`e6e8802a3fd93f1f867c20f1e2013dc4ade410881b2ade46d1e1fb60d9821cb5`；
- boot：`59f89f6255ec54ae`。

fresh ordinal1在reset和pre-command idle均通过后发送PON；BUSY已拉忙，但`60010 ms`未回
空闲，DRF未开始。cleanup后safe-finish BUSY为1且RST/CS/CS2为0，设备持久化FAULT。
GET-only salvage确认1 ARM/1 EXECUTE/1 driver，无retry/recovery/autochain。操作者先后确认
“干净，白色”和“目前全白”，随后relay commanded OFF并独立query OFF。该人工观察只说明
最终画面无可见污染，不能把PON超时改判为成功刷新。

关键证据：

- `MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_20260825_V1B_FRESH2/action-01-salvage.json`
  SHA=`7780ed0de2cd5874cf7c197c58d5b4f395bf612d538807b5029656acc795c851`；
- fault observation SHA=`c2409bc3fdc197244132bb4241974c755bf664bd274c320f621f60d08467b9f5`；
- claim SHA=`48d20ff91098dabc4c4978026cdec087a90f38d4da7deafdbc750aeb8fc045c7`。

### 8.3 V1C readiness结论

不存在“不发送PON即可可靠证明下一次PON会完成”的门。raw BUSY、reset-idle和稳定revision
读取最多证明数字复位/SPI路径；V1B已经直接证明这些条件可以全部成立，而PON仍超时。
因此没有生成可见刷新V1C固件或runner。纯离线fail-closed审计产物为：

- `.test-output/offline/MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1C_READINESS_20260825.json`；
- SHA-256=`64d8fafc71bd4c422a98792eafe3e2cbecc6978ed76d5ca8addca027c2c6daaf`；
- `mode=DIAGNOSTIC_ONLY`、`visible_action_allowed=false`；
- 它重新验证V1/V1B evidence integrity与exact identity，并确认两次input/DTM FNV、
  1 MHz SPI、`2444/2444 ms`上传及三份核心驱动源码完全一致；
- 定向回归`25 passed`，Ruff和`py_compile`通过。

下一次真屏前必须先确认负载侧3.3 V/GND/电流，而非只看继电器上游电压。若仍要把PON
健康检查放到可见action持久消费之前，只能另立并单独审查受监督的`PON→BUSY完成→POF`
无DRF电源资格探针，或改变持久化顺序；两者都真实发送PON，不属于no-PON诊断。完成该审查
前，不释放新的live action。

辅助相关性证据也支持该门：按近期runtime-LUT根目录action JSON的固定筛选口径，初始
raw BUSY=1的35项全部成功，PON均为`180–261 ms`；raw BUSY=0的3个独立attempt全部在
PON=`60010 ms`超时且未进入DRF。它不能单独证明是供电压降、GND/触点还是控制器冷启动
状态，但足以否定继续放行raw0。
