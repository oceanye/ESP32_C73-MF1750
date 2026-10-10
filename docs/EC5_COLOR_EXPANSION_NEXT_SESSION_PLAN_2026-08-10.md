# EC5 下一轮无抖动扩色与单次刷入测试计划

文档日期：2026-08-10  
面板：MF-17506-M009F-T / `MF750M009T6420/1582643AGY44`  
当前硬件：J2 OFF；屏幕保留 U04-vs-U05 四块对照  
状态：`SOFTWARE/SELF-CONTAINED V2 RELEASE READY / NOT HARDWARE EXECUTED`

唯一执行包：
`.test-output/hardware/MF1750_EC5_COLOR_LAB_REAL_COMPARE_BOUND_20260809_V2_SELF_CONTAINED/`。
其中 `firmware.bin` SHA-256=`b67c160178ddc8a93b89161f710a4da6f570ce0c8a4822100429fcfbb7261c78`，
real release canonical SHA-256=`190aee5f791b86abe8b19a02286e09f791efb25d48fe856eb385386de32c2132`。
旧 V1 包已 superseded，并由 campaign/physical validator 强制拒绝。

## 1. 已得到的颜色结论

当前原生 OTP、单次 3-bit target、无抖动条件下：

- 正式六码仍为 `0x0/0x1/0x2/0x3/0x5/0x6`；
- `0x4`（U04）已经两次上屏，约 5 min 稳定并通过一次白恢复；
- U04-vs-U05 双控制器对角交叉盲测给出一致的 `U04 darker than U05`，强度 2/4、
  清晰可辨，色块均匀、边缘清晰、白底干净；35°C、电气正常、ESP32 未重启；
- 因此当前有 **7 个可目视区分的直接状态**。U04 可称深蓝候选，不能称已经量产
  资格化的第七色；
- `0x7`（U07）尚未真屏，可能贡献第 8 个直接状态，也可能是 alias 或不稳定状态。

八码只是一个 waveform profile 内 3-bit target symbol 的上限，不是面板物理色彩上限。
虚拟颜色可由 `waveform profile × target code × primer/history sequence` 定义；跨 profile
或跨 sequence 的颜色通常需要多次刷新，不能自动等同于同一帧可任意共存的调色板通道。

## 2. 单次刷入的 EC5_COLOR_LAB 路线

下一轮优先使用一个固定多 action 固件，断电刷入一次后，在同一 boot/NVS campaign 内
逐项推进。固件只能包含编译期冻结帧，不开放 raw frame、任意码、网络上传、自动刷新、
自动 retry 或自动 recovery。

固件冻结了 23 个有序 action。前 11 个构成完整的发现闭环，后 12 个是在**同一固件、
同一 boot**内可选执行的重复性轮次，不需要重新刷机、RESET 或切 J2：

| ordinal | 固定 action | 目的 | 正常后续 |
|---:|---|---|---|
| 1 | white-after-compare | 由 COLOR_LAB 自身清除当前 U04/U05 四块并建立最新白前态 | 人工确认全白后到 2 |
| 2 | U07 isolated pilot | 白底、左右各 64×64 的 `0x7`，判断即时外观 | 可选观察约 5 min |
| 3 | after-U07 white | 验证 U07 可恢复并重新建立白前态 | 白 PASS 后到 4 |
| 4 | eight-code atlas | `0x0..0x7` 等面积、双控制器/位置反平衡同屏比较 | 描述性分组并与已知码对照 |
| 5 | after-atlas white | 检查八码 atlas 残影并清屏 | 白 PASS 后到 6 |
| 6 | six-primer | 白/黑/黄/红/蓝/绿六初态 ROI | 与 7 必须相邻 |
| 7 | U04 from six primers | 判断 U04 是否受初态影响并出现可重复明暗/色调 | 观察后到 8 |
| 8 | after-U04-transition white | 检查恢复 | PASS 后到 9 |
| 9 | six-primer | 为 U07 建立同一组六初态 | 与 10 必须相邻 |
| 10 | U07 from six primers | 判断 U07 是否有序列依赖色阶 | 观察后到 11 |
| 11 | final white | 最终恢复并结束 session | 人工白屏闭环 |

可选重复性轮次：

| ordinal | 固定 action | 目的 |
|---:|---|---|
| 12–14 | round 2：six-primer → U04 target → white | 检查 U04 序列外观能否重复 |
| 15–17 | round 2：six-primer → U07 target → white | 检查 U07 序列外观能否重复 |
| 18–20 | round 3：six-primer → U04 target → white | 第三次重复，排除偶然差异 |
| 21–23 | round 3：six-primer → U07 target → white | 第三次重复并最终白恢复 |

每个 action 仍必须：

- 拥有独立 action ID、host claim 和逐次用户授权；
- 在首个 POST 前验证前一 result/claim/manual observation；
- 最多一次 ARM、一次 EXECUTE、一次 driver call；
- 将 ordinal 跨重启永久保存，禁止跳步、倒退、重跑或清锁；
- 异常时停在当前 ordinal 并 fail-closed，不自动清屏。

这会消除每个颜色之间的重新刷机、RESET 和 J2 cycle。J2 只在初次刷固件、接线改变、
明确冷启动要求或异常停止时切断；正常动作之间可保持接通。

独立 archived-RC2G compare-after-white 仍保留为高可信 fallback，但不属于正常主路线。
正常主路线直接重放当前 U04/U05 compare result/claim/人工观察，由 ordinal 1 的编译期固定
白帧完成恢复，因此整轮只需刷入 COLOR_LAB 一次；只有新固件离线身份或现场预检失败时才
停机评估 fallback，不能自动切换。

## 3. 下一轮优先级与颜色数量目标

### 第一优先：直接颜色

- 现实目标：验证 U07 是否成为第 8 个直接可寻址状态；
- 八码 atlas 用于一次画面内判断 U04/U07 是否与既有六码视觉重合；
- 若 U07 alias 到已有颜色，直接颜色数保持 7，不把代码数量冒充颜色数量。
- 当前 atlas 的 pseudocolor preview 已在离线审查中打开过，而且 U07 isolated 位于它之前，
  因此本轮明确按 **non-blind descriptive atlas** 记录，不冒充严格盲评；若后续需要独立盲证据，
  另建未提前公开映射的 secret-permutation V2。

### 第二优先：序列颜色

- 六初态→U04/U07 用同一批 ROI 同时观察多个 transition；
- 第一轮目标是筛出 **2–4 个有规律的候选外观**，不是立即新增 2–4 个正式颜色；
- 只有左右一致、重复轮一致、保持稳定并可白恢复的 transition 才能升级为序列色候选；
- 旧态轮廓、漂移或不可恢复状态归为残影，不计入颜色数。

### 第三优先：runtime waveform/LUT

长期扩色不受单一 profile 八码限制。同一 target code 可在不同已校准 waveform 下对应
不同粒子状态，或通过设计 transition/no-op 在多 pass 中形成更大虚拟调色板。但当前不具备
安全上屏条件：

- STM32 参考的可读 535-byte 路径是 2-bit、master-only；
- 842-byte 文件是封装载荷，decoded 3-bit 格式与 loader 源码缺失；
- VCOM、VGH/VGL、VSH/VSL、frame/phase、温区与色码语义未闭合；
- 双控制器 payload、cascade 几何、BUSY timeout 和恢复合同未闭合。

已新增 `host/runtime_waveform/` 与
`tools/mf1750_runtime_waveform_contract.py`，它们只做离线候选身份和资格判定，明确禁止
OTP/nonvolatile 操作，并要求双控制器 3-bit plaintext payload、格式文档、电气参数、温区、
已知 OTP 等价基线、独立恢复、牺牲屏和电源保护全部通过。即使离线合同完整，也不构成
可见刷新授权。

第一阶段 waveform 工程目标可设为 10–12 个稳定、可测量状态，随后再评估 16 色；这是
开发目标而非当前面板承诺。真正上屏前需要当前批次的 3-bit plaintext waveform/格式或
可移植 `loadWF` 源码，并优先在牺牲屏验证。

## 4. 明日测试节奏

驱动单次完整刷新约 34–35 s。若只做即时观察，前 5 个高价值 action 的纯刷新时间约
3 min，前 11 个完整发现闭环约 6.5 min，全部 23 个（含三轮重复）约 13.5 min；实际
时间由人工观察决定。软件已经把全部 23 项预置在同一个 BIN 中，现场不再等待编译。
推荐分层停止：

1. 最短闭环：ordinal 1–3，得到 U07 即时外观和白恢复；
2. 高价值闭环：继续 ordinal 4–5，得到八码同屏结论；
3. 探索闭环：继续 ordinal 6–11，筛选初态依赖候选；
4. 只有发现值得复核的差异时才继续 12–23；否则可在 ordinal 11 的白场结束；
5. 任一白恢复、电气、温度、BUSY、ESP32 或左右一致性失败，立即停止后续 ordinal。

30 min 观察可按用户决定跳过，但必须记录为 SKIPPED；跳过后只能得到技术/短期结论，
不能获得正式稳定性资格。约 5 min 观察推荐保留，可减少把快速漂移误判为颜色的风险。

## 5. 今晚边界

- J2 已由用户断开；不推断 ESP32 USB 状态；
- 只允许本地源文件、asset、preview、manifest、固件 clean build、ELF identity 和测试；
- 禁止访问设备 IP、COM8、esptool upload/verify、真实 claim、授权、POST 或可见刷新；
- 明日所有 exact action 必须在当前硬件状态和 release 深验后才生成给用户。
