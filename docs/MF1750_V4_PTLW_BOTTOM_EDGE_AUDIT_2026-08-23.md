# MF1750 V4 PTLW 底边异常离线审计

日期：2026-08-23  
范围：只读检查 V4 源码、固定 identity、已封存 action 2--4 驱动报告、SPD1657A
Rev 1.0 PTLW/DTM 定义、Good Display 指定区域样例和 GxEPD2 相邻实现。未访问继电器、
设备网络或串口，未刷写、复位或刷新真屏。

## 结论

本轮 A/B/C 已经给出强物理证据：新窗口正确显色，后续局部刷新时旧窗口没有闪烁或
变色，窗口外保持全白。因此应把 **局部 HOLD 本身记为 PASS**。三个色块共同出现的
底边不直属于独立的 **PTLW 末端边界质量问题**，不能倒推 HOLD 失败。

当前没有软件证据支持“少发一行”或“跨行错包”：每个窗口均为 `160 x 120`，每行
`160 / 2 = 80` bytes，实发 `80 x 120 = 9600` bytes；三个 action 的 CS1/CS2 上传耗时
均为 153 ms，固件侧 FNV 与冻结 identity 完全一致。两颗控制器使用相同局部坐标，旧区
保持不动，也反证了左右映射或 CS2 镜像错误。

## 固定几何

| 窗口 | X（含端点） | Y（含端点） | 行字节 | DTM 字节 |
|---|---:|---:|---:|---:|
| A / code3 | 48--207 | 64--183 | 80 | 9600 |
| B / code5 | 304--463 | 240--359 | 80 | 9600 |
| C / code6 | 48--207 | 416--535 | 80 | 9600 |

三个不同 Y 位置都只在 `VRED` 一侧出现异常，最强地指向窗口结束 gate/波形边界，
而不是某个固定 SRAM 行或某个 controller。

## 根因排序

1. **PON 后、DRF 前未重新锁存 PTLW（最高）**。当前 V4 只在 DTM 前写一次 PTLW，
   然后进入共享 `PON -> BTST2 -> DRF`；GxEPD2 的 `refresh(window)` 则在 PON 成功后、
   CDI/DRF 前重新发送同一个 `0x83`。因此不能把“DTM 前再重复一次”冒充这个候选。
   手册未明说 PON 会破坏 PTLW，但当前症状集中在 VRED 边界，优先严格复制这一交易顺序。
2. **PTLW 末端扫描边界/guard-row 不足（中高）**。SPD1657A 明确 partial 时窗口内外
   gate 都扫描；GxEPD2 对相邻 GDEP073E01 另有 `ye=y+h` 的 one-more workaround。
   当前 `ye=y+h-1` 和严格 9600-byte DTM 在数字合同上正确，但未给末端 gate 留过渡行。
   黑、蓝、绿的底边模式不同，也符合 LUT code 在同一个末端边界产生不同光学终态。
3. **runtime LUT 的 partial 边界补偿不足（中低）**。既往 factory-OTP 的正确包含式
   PTLW 也出现过底侧间隔线，故问题不是 L535 独有；但不同 LUT/code 会改变边界外观。
4. **CDI 值本身 / 外框驱动（低）**。V4 已经在 PON 前发送 `CDI 0xFF`，GxEPD2
   则在 PON 后、PTLW 后再次发送同值；`0x3F` 与 `0xFF` 的主要差异是物理 VBD 外边框
   选择。现在外围全白，故 CDI 值不优先解释每个 ROI 的底边，但复制参考交易顺序时仍应
   在 post-PON PTLW 后重申既有 `0xFF`，避免窗口和边框状态在 DRF 前来自不同锁存阶段。
5. **少行、nibble、stride、左右映射或 SPI 丢字节（很低）**。固定长度、偶数 X/宽度、
   双路相同 hash/耗时、三个窗口定位和双侧最终结果均不支持这些解释。

## 最小安全诊断顺序

每个候选必须使用新的隔离 identity/NVS/action，不能修改或重放已经消费的 V4 action。
先由独立 factory-OTP 白恢复建立白底，再逐个单变量测试：

1. `RELOCK_PTLW_AFTER_PON_BEFORE_DRF`：仍用 `x+w-1/y+h-1` 和原 9600-byte DTM；
   两路 DTM 完成后先共同 PON 并等待 BUSY 回到 idle，随后分别给 CS1/CS2 重发完全相同的
   9-byte PTLW，然后按 GxEPD2 的刷新锁存顺序重申既有 `CDI 0xFF`，再沿用当前
   BTST2/DRF。CDI 数值、LUT、端点和像素数据均不改变；受控差异是把同一 PTLW/CDI
   状态在 PON 成功后、DRF 前重新锁存。重复写入若位于 PON 之前，就没有复现 GxEPD2 的
   关键顺序，不能用于裁决这个候选。若需要把因果进一步拆细，可在候选命中后另做一个
   仅重发 PTLW、不重发 CDI 的隔离复核；不应把该复核置于首个参考实现对照之前。
2. `BOTTOM_GUARD_1`：PTLW 改为 `y..y+h`，显式发送 120 行目标色 + 1 行 white code7，
   共 `80 x 121 = 9680` bytes。不能只扩大窗口却少发最后一行，也不能照抄样例中额外的
   `0x00`；后者在 SPD1657A DTM 合同中会被当成像素。
3. `TOP_BOTTOM_GUARD_1`：若单侧 guard 仍有方向性异常，PTLW 改为
   `y-1..y+h`，显式发送 white + 120 行目标色 + white，共 9760 bytes。原色块坐标不变。

只有第一项失败后才进入 guard-row；不要同时改变 CDI、端点、LUT、SPI 或 warm/cold
session。照片应确认异常是在目标色最后一行以内，还是在窗口外第一行；这一区分可直接
判定 guard-row 是否命中。

## 当前代码事实

- `phWritePartialWindowAt()` 使用包含式 `xe=x+w-1`、`ye=y+h-1`、PMODE=1。
- `phStreamUniformDtm()` 在 `0x10` 后直接发送 uniform packed nibbles，无格式前缀。
- 当前实现没有绘制矩形边框；肉眼所称“底边边框”是显色边界，不是 host 图像资产。
- 当前实现只在 DTM/PON 前写 PTLW；PON 成功后到 DRF 之间不重复 PTLW，也没有显式
  guard row。
