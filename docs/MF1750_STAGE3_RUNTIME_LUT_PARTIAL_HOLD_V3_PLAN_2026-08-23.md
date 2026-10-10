# MF1750 阶段三：L535 同盘局部 HOLD V3 计划

## 1. 现场事实与纠正

- V1：L535 下 code 3 全屏显示为黑，动作完成后停止；它不能作为白底。
- V2：L535 下 code 1 显示为一侧黑、一侧白/浅色；这证明 CS1 的 active-535 与
  CS2 的 commented-535 不是共享码位颜色表，code 1 不能作为公共白底。
- 既有 16 大纯场照片按固件固定顺序回查后，code 7 是两控制器共同白色的最强候选；
  code 3/5/6 分别是两侧都较一致的黑/蓝/绿候选。除 code 3 和 code 1 的本轮直接
  全屏事实外，其余仍属于照片与布局联合推断，必须由下一轮真屏逐项确认。

因此，旧的“同一码在两个控制器上颜色相同”假设作废。后续所有 runtime-LUT 测试都必须
显式保存 `CS1 profile + code` 与 `CS2 profile + code`，不能只记录一个全局 code 名称。

## 2. V3 固定动作

| 顺序 | 动作 | 固定传输码 | 人工停止门 |
|---:|---|---:|---|
| 1 | 全屏共同白候选 | code 7 / code 7 | 必须确认左右均为干净白 |
| 2 | 局部 A 黑块 | code 3 / code 3 | A 两侧均黑，窗口外仍白 |
| 3 | 局部 B 蓝块，保持 A | code 5 / code 5 | A 不变、B 两侧均蓝、窗口外白 |
| 4 | 局部 C 绿块，保持 A+B | code 6 / code 6 | A/B 不变、C 两侧均绿、窗口外白 |
| 5 | 全屏共同白恢复 | code 7 / code 7 | 全部色块和边界可清除 |

几何仍固定为每控制器三个互不相交的 `160×120` 窗口，PTLW=`0x83`、包含式终点、
PMODE=1、SPI=1 MHz。每次调用只允许一个 ARM、一个 EXECUTE、一个 driver；无 retry、
recovery、autochain、相机自动判定或跨调色盘切换。

回场时采用短决策链，不再盲目连续枚举：

1. 驱动板保持断电，app-only 刷入 V3；独立校验 BIN 后只做 GET-only virgin diagnostic。
2. 接通驱动板后只执行 ordinal 1。若人工确认左右均为干净白，才依次释放 A、B、C；
   每次只需要报告“新块颜色 / 旧块是否保持 / 白底与边缘是否正常”。
3. ordinal 1 若不是双白，立即停止 V3，不执行 A；切断驱动板后改刷独立 factory-OTP
   containment，恢复白屏后再离线修订左右 code 映射。
4. A、B 或 C 任一步出现旧块灰化、消失、串色或边缘异常，停止剩余 PATCH，直接执行本组
   ordinal 5 白恢复；若它不能清净，再切换独立 containment。

因此，一次顺利回场最多需要五次人工观察；首个白门失败时只需一次 V3 观察加一次独立恢复
观察。V3 的目的只回答“同一套 L535 调色盘内，PTLW 是否能可靠保持旧 ROI”，不在这一轮
同时搜索新色，也不把一次失败扩展成大规模 LUT 枚举。

## 3. 通过与停止条件

V3 ordinal 1 不得到双白即整组停止，后续局部动作不释放。若双白通过：

1. 每个 PATCH 后先检查窗口内颜色，再检查所有旧窗口是否保持，最后检查窗口外白底。
2. 任何旧色块褪色、灰化、偏色，或外围/底侧出现灰边与黑白间隔线，立即停止同盘 HOLD。
3. 只有 A→B→C 全部保持且白恢复可清除，才把 same-palette HOLD 记为 PASS。
4. same-palette HOLD PASS 后才生成 cross-palette 两窗口计划；在此之前不宣称可叠加到
   16 色、256 色或任意照片色深。

若 ordinal 1 的 code 7 不是双白，或 ordinal 5 不能清除全部色块，停止 V3 后改用独立
factory-OTP white containment；不得重试 V3 当前动作。containment 使用 fresh NVS
`rlphv3cw`、独立 action，只有一个白恢复动作，不含 runtime LUT、partial、raw ingress、
retry、recovery chain 或 autochain。它已离线构建和绑定，但不会自动执行。

## 4. 后续搜索结构

- 第一级：为每个 LUT profile 分别建立 8 个码位的左右控制器映射表。
- 第二级：只选择两控制器颜色一致的码位做同盘局部保持矩阵。
- 第三级：用已保持 ROI 作为锚点，切换第二套完整 LUT 后只写新 ROI，验证跨盘保持。
- 第四级：跨盘保持重复通过后，才考虑多轮调色盘堆叠与照片量化；每一轮都必须保留
  独立白恢复路径。

未知命令、0x86、LUT 任意字节穷举、VCOM/高压扫描、刷新中切电和 SPI sweep 继续禁止。

## 5. 当前离场状态

操作者已关闭上游电源。V3 只允许离线生成、构建、哈希绑定和测试；不得访问继电器、
ESP32 网络、COM/串口，不得刷写、复位或刷新屏幕。下次回场后从“确认电源/J2 OFF，
app-only 刷 V3，独立 verify，GET-only virgin diagnostic”开始。

离线产物：

- V3 BIN：793,360 bytes，SHA-256
  `52a46202c2897450f5356d026e64e647880e35a3f523f1bab9f9db61fda1649e`。
- V3 containment BIN：785,936 bytes，SHA-256
  `33f7fb6cd330f30acd305067d08b11449c6dc921566e18466121c6518856a569`；
  ELF：13,213,772 bytes，SHA-256
  `224e5b57cdc5099c6ed7ce569d40b436ecd278ed49f958ae922cb5fd6ef1005d`。
- V1/V2/V3、containment 与历史 535 reference matrix 联合回归：25 passed；Ruff、
  py_compile、V3/containment 两个 runner `describe` 均通过。

## 6. 2026-08-23 真屏结果与后续修订

- V3 ordinal 1 已唯一执行并在设备端 COMPLETE，但人工观察仍为“左黑右白”。因此
  `code7/code7` 共同白假设被否证，V3 ordinal 2–5 全部冻结，不得重放或越过。
- 独立 factory-OTP containment 在修正“旧 WF23 claim”主机门后，严格绑定本次 V3
  ordinal 1 的永久 claim 与 COMPLETE result；随后唯一恢复动作成功，人工确认“白了”。
- 收尾时 relay channel 1 commanded OFF，屏幕保持全白；没有后续可见刷新。
- V3 result/claim SHA=`d27e617f...0791f`/`887489b7...f0fd`；containment
  diagnostic/result/claim SHA=`d7fe4072...ebf6`/`57392a20...33bd`/
  `4c1147d7...9212`；人工 observation SHA=`1883d2d3...bef5`。
- 下一轮不再尝试左右共用同一码。先离线生成 `CS1 profile/code` 与 `CS2 profile/code`
  独立映射固件；只有找到可验证的双白组合，才重新建立新的 A/B/C HOLD campaign。

## 7. 控制器独立码位映射 V1

为消除“左右控制器同码同色”的错误前提，新增一次性
`EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_20260823_V1` 映射图。它仍使用已封存的
L535 active/commented 完整表、SPI 1 MHz 与 factory full-screen 全局刷新；不启用 partial、
dither、未知命令、刷新中断电、retry、recovery 或 autochain。

- CS1 的 8 个大纯场按逻辑顺序显示 code `0,1,2,3,4,5,6,7`。
- CS2 的 8 个大纯场按逻辑顺序显示 code `7,6,5,4,3,2,1,0`，便于照片中区分控制器与码位。
- 两侧均为 `2×4`、每格 `128×300`；一次刷新同时取得 16 个 `控制器/profile/code→颜色` 结果。
- 该图只建立映射，不证明 HOLD，也不从照片颜色名反推寄存器含义。

固件使用独立 translation unit、identity、NVS 与永久 action，避免修改历史 reference 产物：

- BIN：797,616 bytes，SHA-256
  `c72f7e110c675c11f182e5129ffbe47d7682df7666fd4be8e6626fd9d991a055`。
- ELF：13,268,252 bytes，SHA-256
  `2e70784b0353a2aa9044232023ab977e5aaa92677185b553f9fe63b9c48036a7`。
- build tag=`MF1750_EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_V1_2026-08-23`，
  NVS=`ccmaplga1`，唯一 action=`de90b4c2...f51612e`。
- 新映射与历史 reference 定向测试 `10 passed`；Ruff、py_compile、runner `describe` 通过。

下一次真屏流程固定为：relay OFF 下 app-only flash 与独立 verify → GET-only virgin
diagnostic → relay ON → 唯一 atlas action → 停在人工照片/颜色判读门 → 独立 factory-OTP
white containment → relay OFF。只有人工映射完成后才计算控制器专用双白与后续 HOLD 候选；
不得提前宣称新 HOLD campaign 已可执行。

## 8. 映射真屏结果与 packed-white V4

控制器码位图已唯一执行：设备端 `1 ARM / 1 EXECUTE / 1 visible refresh`，无 retry、
recovery 或 autochain。操作者离场前上传 810×1440 照片；照片 SHA-256 为
`679e47694956c3ead0146b6115ac4e21ffc56d0315172bd508fdf67a94c517c2`，人工观察记录
SHA-256 为 `7cb31d67236ac34116a84fc6caec9f9bc2153ab906d8d16bf6899c7d839132e0`。
离场后 relay channel 1 已切为 OFF 并再次回读 OFF，未执行原计划中的 containment 白恢复，
屏幕静态保留映射图。

按照片 FPC 在右、顺时针旋转到逻辑横屏后，当前相对颜色映射为：

| code | CS1 active-535 | CS2 commented-535 | 跨控制器结论 |
|---:|---|---|---|
| 0 | 橄榄/黄绿 | 红 | 明显不同 |
| 1 | 深紫灰 | 浅棕/浅粉 | 明显不同 |
| 2 | 黄/橄榄黄 | 鲑粉 | 明显不同 |
| 3 | 深紫棕 | 深蓝紫 | 都属暗色，但未证明同色 |
| 4 | 浅黄绿 | 棕橙 | 明显不同 |
| 5 | 蓝 | 蓝 | 高置信同色 |
| 6 | 绿/蓝绿 | 绿/蓝绿 | 高置信同色 |
| 7 | 白 | 白 | 高置信同色 |

上述颜色名来自未标定照片，只能作为相对类别；不替代 24 色卡/Lab 标定，也不证明新颜料色。
但它足以否证“所有 code 左右同义”，并同时证明本 profile 下 code7 在 packed-frame atlas
路径中可令两控制器呈白。因此 V3 的“左黑右白”不能再解释为 code7 本身没有共同白，优先
定位为旧 full-controller uniform-DTM 路径与已实测 packed-frame 路径之间的执行差异。

据此已完成隔离的 V4 固件：

- ordinal 1/5：code7 整屏白，改用 atlas 已实测的
  `epdStreamPackedFrameController`；
- ordinal 2–4：保持原单变量局部路径，依次为 code3 暗块、code5 蓝块、code6 绿块，
  仍用 `0x83` 包含式窗口与 cropped uniform DTM；
- fresh NVS=`rlph_l535a_v4`，5 个新 action，无 retry/recovery/autochain；
- BIN=`793728 / e3315ba1a337e041c156728693c4db92c9463ef195296ebaef351b7c07e5ad9c`；
  ELF=`13270560 / 61f1bee81e6c5aa5afdba86b092c20631915807da71fdad9e920bbff5c0ee09a`；
- mapping/reference/V1–V4/containment 联合 `33 passed`，Ruff、py_compile、V4 runner
  `describe` 全部通过。

V4 尚未刷入或执行。下次操作者回场后，先在 relay OFF 下 app-only flash+verify 和 GET-only
诊断；只执行 ordinal 1。若 packed code7 为干净全白，才释放暗→蓝→绿三个局部保持动作；
任一步旧块变化或背景异常即停止并转独立 factory-OTP containment。若 ordinal 1 仍不是双白，
V4 立即失败，后续动作全部冻结。

## 9. 样例复核与多路线离线批次

本地 GDEP073E01 样例已确认包含实际执行的局部刷新：`0x83` 9-byte 包含式窗口、
裁剪 `0x10` DTM、PON/DRF/POF，且主循环在每次局部动作前重新 `EPD_init()`。但样例在
DTM 后额外写入的 `0x00` 并非 SPD1657A 手册定义的格式前缀，不能照抄；手册还明确说明
窗口内外 Gate 均扫描，所以 partial addressing 不等于窗口外零场 HOLD。

今晚准备的路线已扩充为：V4 严格 PTLW、V5 无 PTLW 的累计整帧控制组，以及 V6 AB/BA
双向 8×8 跨调色盘历史矩阵。完整语义、固件哈希和执行顺序见
`docs/MF1750_STAGE3_PARTIAL_SAMPLE_AUDIT_AND_EVENING_BATCH_2026-08-23.md`。
