# MF1750 RAW-P16 端点画廊与 LUMA-GRAY-V1 中性明度搜索计划

日期：`2026-08-28`
状态：`OFFLINE_READY / BUILT / NOT_FLASHED / NOT LIVE-EXECUTED`
硬件访问：`false`
空间抖动：`false`

## 1. 目的与结论边界

本计划把下一轮工作拆成两个独立 campaign：

1. `RAW-P16-V1`：一次展示当前 mixed-R20（CS1 active535／CS2 commented535）下两侧的
   `code0..7`，供人工建立
   原始端点照片和颜色词；
2. `LUMA-GRAY-V1`：用 `32` 条白／暗端点历史配方搜索中性灰和可重复明度候选，每条配方
   在同一控制器内放置四个空间副本。

两项都只使用单像素 transport code，不使用网点、条纹、棋盘格或其他空间混色。`P16` 的
含义是 `2 controllers × 8 raw endpoints`，不是16个唯一颜色，也不是16个合格色。`LUMA 32`
的含义是32条待筛历史配方，不是32级灰阶。

本文记录离线实现和上机编排。本次实现期间未访问 ESP32、设备网络、COM、继电器、相机或
面板，不刷写、不复位、不刷新真屏。固件、runner、contract、NVS identity 和文件哈希均由
fresh campaign 生成并完成离线绑定，未引用或复用已经消费的历史 campaign。

## 2. 当前证据基线

### 2.1 已知颜色与调色板边界

- 既有重复肉眼证据支持7个基础视觉组：黑、白、黄、红、Blue-1、Blue-2、绿；
- 单一 controller/profile 只直接寻址8个 transport code；不同 controller 的同一数字 code
  不一定是同一物理颜色；
- 目标 H13 是照片用途的13个色相族目录：`N/R/RO/O/Y/YG/G/T/C/B/I/V/M`；它是搜索和
  归档框架，不表示13族均已有独立、稳定端点；
- 当前没有 canonical Lab/DeltaE00 唯一色计数，也没有证据支持已经得到84色或256色。

### 2.2 已有明度结论

| 证据 | 当前结论 | 本计划中的用途 |
|---|---|---|
| `BLUE-BRIGHTNESS-64-V1` | 64条历史配方完成主筛；最终蓝色矩阵未观察到稳定差异，合格蓝色明度=`0` | 不重复把64条蓝历史当灰阶；只把“历史可能影响中间态”保留为搜索线索 |
| 红／粉 V2 | 相机看到结构化 L* 与红／粉外观带，但同配方四位置效应尚未排除；`qualified_brightness_level=false` | P16只展示直接端点；LUMA必须先过四位置一致门 |
| 黄／橄榄 V1/V2线索 | 出现黄绿／橄榄外观与结构化亮度，但尚未取得合格明度 | 不把橄榄深浅写入正式 palette |
| factory-OTP 8×8历史矩阵 | 观察到历史依赖亮度，例如旧红到新码的部分格更深；未形成已排序、可重复的梯度 | 证明继续搜明度有价值，但32条配方的编号不代表亮度顺序 |
| 中性灰 | 白、黑端点之外，中间中性灰合格数=`0` | `LUMA-GRAY-V1`从零开始；所有结果初始均为 candidate |

## 3. RAW-P16-V1：直接端点画廊

### 3.1 固定 profile 与原始标识

P16 固定使用当前已观察的 **mixed-R20** 组合：CS1 装载 active535，CS2 装载
commented535。它不是 same-R20，不能把两侧解释为“同一R20在两个控制器上的复现”。每个
端点的权威名字必须是：

```text
RAW-P16/MIXED-R20/<controller>/C<code>
```

例如 `RAW-P16/MIXED-R20/CS1/C0`。中文颜色词只能放在 `observed_appearance` 字段，不能替代
controller/profile/code 标识。

### 3.2 16个端点与 H13 搜索映射

| 原始端点 | 当前照片／肉眼词 | H13搜索族 | 证据与限制 |
|---|---|---|---|
| CS1/C0 | 橄榄／黄绿 | YG，次级Y | 未标定视觉候选 |
| CS1/C1 | 深紫灰 | I/V，次级N-dark | 暗色且带色偏；不能称中性灰 |
| CS1/C2 | 黄／黄橄榄 | Y，边界YG | 未标定视觉候选 |
| CS1/C3 | 深紫棕／近黑 | O/V/N-dark | 多族歧义；不能称黑或灰的独立明度 |
| CS1/C4 | 浅黄绿 | YG | 未标定视觉候选 |
| CS1/C5 | 蓝 | B | 跨控制器较一致的高置信端点 |
| CS1/C6 | 绿／蓝绿 | G；T搜索种子 | G较有证据，T尚无独立配方 |
| CS1/C7 | 视觉白方向 | N-white搜索种子 | runtime code7不是factory-OTP white，也不是恢复动作 |
| CS2/C0 | 红 | R；M边界种子 | R直接候选；不能由肉眼红自动升级为M |
| CS2/C1 | 米肤／淡粉 | O/RO；M搜索种子 | O、RO、M之间有歧义 |
| CS2/C2 | 鲑粉 | RO；M搜索种子 | RO/M之间有歧义 |
| CS2/C3 | 深蓝紫／近黑 | I/N-dark，次级V | 暗色且带色偏；不能称中性灰 |
| CS2/C4 | 棕橙 | O | 未标定视觉候选 |
| CS2/C5 | 蓝 | B | 跨控制器较一致的高置信端点 |
| CS2/C6 | 绿／蓝绿 | G；T搜索种子 | G较有证据，T尚无独立配方 |
| CS2/C7 | 视觉白方向 | N-white搜索种子 | runtime code7不是factory-OTP white，也不是恢复动作 |

映射结论：

- `C`（青／天蓝）当前没有独立直接配方，只能把 code5/code6 邻域作为后续搜索种子；
- `T` 与 `G` 共用 code6 邻域，尚不能证明存在独立 teal 端点；
- `M` 与 CS2 的红／淡粉／鲑粉端点重叠，尚不能证明独立洋红端点；
- `V` 只有暗色视觉候选，也不能视为已标定紫色；
- 因此 P16 不能宣称覆盖完整 H13，更不能从16个格子推出16个唯一颜色。

### 3.3 画面与操作

画面采用每个控制器半屏 `2列×4行` 的大纯色格：四行依次为
`[C0,C1] / [C2,C3] / [C4,C5] / [C6,C7]`，CS1/CS2 使用相同逻辑排布。色块之间只留
runtime code7 背景缝，不画黑色边框，不在色块内写文字；坐标、controller 和 code 由外部
manifest 与照片 overlay 标注。runtime code7 只表示该 mixed-R20 下的视觉白方向，不能称为
factory-white。这样优先保留均匀纯场并减少底边、文字和空间混色对颜色词的干扰。

P16 使用三套相互独立、各自一次性的固件身份：

| 顺序 | 独立固件 | 唯一可见动作 | 目的 |
|---:|---|---|---|
| 1 | pre-white anchor | factory-OTP white | 取得 fresh 干净白拍摄基线 |
| 2 | RAW-P16 main | mixed-R20 2×4 endpoint gallery | 从统一白历史得到16个直接端点并停留供观察 |
| 3 | post-white containment | factory-OTP white | 独立清除画廊并关闭测试闭环 |

三套固件具有不同的 campaign ID、contract、BIN/ELF 和 NVS namespace/key，任何一套都不会
自动调用下一套；主画廊固件自身恰好只有一个可见动作。

P16 V1 不自动执行 identical repeat。若后续要检查端点收敛，应建立 fresh identity 的 P16-R2，
在新的白基线后单独比较首次与重复结果，不能把重复后的颜色冒充“白→端点”的直接结果。
P16结束后若要继续 LUMA，先切换到独立 fresh factory-OTP white containment，人工或相机确认
干净白，再开始另一个 campaign；不得从 P16 自动串到 LUMA。

### 3.4 观察记录

P16 至少保存：

- 固定曝光、固定白平衡、固定照明下的全屏照片和原始文件 SHA-256；
- 24色色卡与面板同平面时的校正照片；没有色卡或分光测量时只写 camera-relative；
- 每格中央 ROI 的均匀性、相对 Lab/L*/C*、颜色词和是否有条纹／网点；
- CS1/CS2 同 code 是否近似、明显不同或无法判断；
- 5 s 观察。60 s/600 s、三次独立重复和长期保持属于后续资格工作，可在发现有价值端点后补做。

命名只允许以下层级：

1. 权威原始名：`RAW-P16/MIXED-R20/CSx/Cn`；
2. 观察名：例如“相机相对橄榄方向”；
3. H13用途：例如 `family_candidate=YG`；
4. 资格状态：P16 V1固定为 `raw_endpoint_observed` 或 `candidate`，不能写
   `qualified_unique_colour`、`qualified_brightness_level` 或 canonical 色名。

## 4. LUMA-GRAY-V1：32条中性明度历史配方

### 4.1 搜索空间

每条 recipe 在相同 controller 内执行保守的 active→commented→active 历史链，并写成：

```text
R(s,m,t) = active source C<s> -> commented middle C<m> -> active target C<t>
```

V1 固定 `s∈{C3,C7}`、`m=C0..C7`、`t∈{C3,C7}`，因此共有：

```text
2 active source anchors × 8 commented middle codes × 2 active targets = 32 recipes
```

分为两个页面，每页16条；Page-T3先执行，Page-T7后执行：

| 页面 | active target | 16条recipe | 目的 |
|---|---|---|---|
| Page-T3 | C3 | `R(3,m,3)`与`R(7,m,3)`，`m=0..7` | 搜索偏暗端的历史明度与色偏 |
| Page-T7 | C7 | `R(3,m,7)`与`R(7,m,7)`，`m=0..7` | 搜索偏亮端的残余明度与色偏 |

active source C3/C7 只是两个 runtime transport anchors：C3 在 CS1/CS2 上分别可能偏紫棕和
深蓝紫，C7也只是已有视觉白方向。它们都不是 factory-OTP黑／白，配方名、manifest和结论中
不得把 C3 命名为“黑”、把 C7 命名为“白”。commented middle C0..C7 只承担历史激励，不把其
中间画面颜色直接当最终LUMA结果。选择这两个source/target anchors只是在首轮限制搜索空间；
任何带明显色偏的最终结果直接转入 I/V/O 等色相候选或淘汰，不算灰阶。active C7也不能取代
factory-OTP white containment。

### 4.2 四位置重复布局

每个 controller 半屏使用 `8×8=64` 个纯色格。每页16条 recipe，每条出现4次，因此每页
每控制器刚好64个观察格；CS1和CS2共有128个观察格，但仍只代表16条数字 recipe 的两组
controller-specific物理结果。

令页面内 recipe index 为 `i=source_index×8+middle_code`，其中 C3 的 `source_index=0`、
C7 的 `source_index=1`；再令 `a=floor(i/4)`、`b=i mod 4`。四个副本固定放在：

```text
Q0: (a,     b)
Q1: (b,     7-a)
Q2: (7-b,   a)
Q3: (7-a,   7-b)
```

这样每条 recipe 在四个象限各出现一次，并以旋转位置打散行、列、边缘和照明趋势。CS2采用
相对屏幕中心线镜像后的同构布局；manifest必须同时输出逻辑格位和物理像素 ROI。只采样每格
中央区域，排除至少10%边缘和白缝。四位置一致性不通过时，结果记为
`POSITION_DEPENDENT_INCONCLUSIVE`，不能选择其中看起来最好的一格作为颜色配方。

### 4.3 固定动作序列

历史配方的 source、middle、target 各自都是一次可见刷新，不能在记录中合并成“一次刷新”。
主固件建议固定八个 ordinal：

| ordinal | 可见动作 | 判读边界 |
|---:|---|---|
| 1 | factory-OTP white health anchor | 必须确认干净白；不是候选页 |
| 2 | Page-T3 active source C3/C7 pattern | 只建立两个runtime source anchor历史，不判黑／白或灰阶 |
| 3 | Page-T3 commented middle C0..C7 pattern | 只建立commented middle历史，不判灰阶 |
| 4 | Page-T3 active target C3 | 拍摄16条×四位置的偏暗端候选 |
| 5 | factory-OTP white inter-page reset | 必须回到干净白；不能把它当最终独立收容 |
| 6 | Page-T7 active source C3/C7 pattern | 只建立两个runtime source anchor历史，不判黑／白或灰阶 |
| 7 | Page-T7 commented middle C0..C7 pattern | 只建立commented middle历史，不判灰阶 |
| 8 | Page-T7 active target C7 | 拍摄16条×四位置的偏亮端候选并封存主campaign |

V1 不做 target repeat，也不自动进入下一波形。先用四位置门排除空间伪差；只有出现中性且
位置一致的候选，才为命中配方建立 fresh V2，补 identical target repeat、三次独立刷新、
5/60/600 s 保持与局部 HOLD 共存验证。任一页面无差异只代表该页面阴性，不得据此跳过另
一页面；若出现安全异常则必须立即停止整个 campaign。

主campaign无论成功、阴性或早停，最终白恢复都使用独立 fresh identity 的 factory-OTP
white containment。收容必须有自己的 NVS namespace/key、contract、BIN/ELF 和 runner，
不依赖主campaign状态，不重用已经消费的 claim，也不被主程序自动调用。只有 containment
完成并确认全屏干净白，才允许记录测试闭环。

## 5. 中性与明度判定门

以下是 V1 的预注册工程筛选门，不是测色仪认证标准。拍摄必须固定机位、照明、曝光和白平衡，
24色色卡与面板同平面；校正不足时只能输出 `camera_relative_candidate`。

### 5.1 单格与四位置门

每条 recipe 在每个 controller 上分别判定：

1. 四格 `4/4` 均有效且为单码纯场，无网点、水平交错、条纹、黑底线、灰边或破损边；
2. 同一 recipe 四位置的相机相对颜色离散 P95 `DeltaE76 <= 6.6032`；
3. 任一门失败，recipe只能记 `position-dependent`、`non-uniform` 或 `edge-failed`，不能进入
   中性门。该阈值是本项目由锁定相机白场重复噪声导出的工程门，不是测色仪认证门。

### 5.2 中性门

以同一照片中的灰卡／色卡中性轴和 action 1 factory-white 建立相机色偏校正。V1 候选门要求
相对 neutral-locus 的 `ab distance <= 8`，至少 `3/4` 个位置副本通过，同时
`L* in [15,85]`。若只能进行相对校正，结果必须标成 `camera_relative_gray_candidate`；暗部
因相机噪声导致置信区间跨过阈值时判 `INCONCLUSIVE`，不按通过处理。C3端点的紫、蓝或棕
色偏若超门，只能归入相应H13色相族，不能为了凑灰阶放宽阈值。

### 5.3 明度级门

通过中性门后才讨论灰阶级：

- 候选 L* 必须位于同批白端与暗端之间，并与任一已保留相邻级满足 `absolute DeltaL* >= 8`；
- 配方编号、source code、middle code和target code均不代表亮度顺序；按实测 L* 重新排序；
- 同一 L* 带内若颜色差主要来自色偏，不计为新的中性明度；
- V1最多输出“位置平衡的中性明度候选”。正式 `qualified_brightness_level` 另要求相对中性
  距离 `<=5`、三次独立 fresh run、5/60/600 s保持、target repeat 的
  `DeltaE76 <= 6.6032`、局部HOLD后不变色以及最终白恢复；
- 当前正式中性灰数量继续保持 `0`，直到全部资格证据闭合。

## 6. 停止条件与安全收容

出现任一情况立即停止当前主campaign，不重试当前 action，不 fallback、不 recovery、
不 autochain，并转入 J2 OFF 与独立收容流程：

- 电源进入限流，或电流、温度、气味、声音、发热出现异常；
- BUSY时长超过同类健康基线的2倍，BUSY没有按合同进入／退出，或左右控制器严重不同步；
- 固定横线、纵线、全屏灰边、中心接缝异常、大片永久偏色或任一控制器缺失；
- 四位置格子出现持续条纹、空间抖动、黑底线或边缘污染，且factory-white inter-page reset
  不能清理；
- factory-OTP white health anchor不是全屏干净白；
- 任何主固件 identity、源码哈希、BIN哈希、boot、action ordinal、claim或runner绑定不一致；
- 操作者离场、监测不可用或物理切断不再就绪。

颜色“没有差异”不是安全故障：该页记阴性后按固定顺序继续。颜色“看起来新”也不允许自动
升级或自动追加动作：先保存照片与receipt，按上述门离线分析，再决定是否另建fresh复核固件。

独立收容只执行唯一 factory-OTP white。收容成功的最低闭环是：机器 COMPLETE、恰好一次
visible refresh、人工或相机确认全屏干净白、无候选色／边框／色斑残留，然后继电器 commanded
OFF并独立query OFF。无负载侧传感时仍保留 `electrical_state_proven=false`。

## 7. 实现文件与构建绑定

以下值来自 `2026-08-28` 最终构建后的独立 SHA-256 复核。重新构建后必须重新绑定，不能继续
沿用本表。完整源文件、runner 和命令分别见
`docs/MF1750_RAW_P16_ENDPOINT_GALLERY_V1_RUNBOOK.md` 与
`docs/MF1750_LUMA_GRAY_V1_RUNBOOK_2026-08-28.md`。

| campaign | 项目 | 路径／值 | bytes | SHA-256 / ID | 状态 |
|---|---|---|---:|---|---|
| P16 pre-white V1B | env／runner | `platformio.raw_p16_endpoint_gallery_pre_white_anchor_v1b.ini`；`tools/mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_once.py` | — | contract `d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61`；NVS `rp16gpw_v1b/used_p16pb` | OFFLINE READY |
| P16 pre-white V1B | BIN | `.pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1b/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b/firmware.bin` | 786704 | `54f7e6f588a35730add6a5edd16e7e4b375e273d467d717277ec0a4cde413bc6` | VERIFIED |
| P16 pre-white V1B | ELF | `.pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1b/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b/firmware.elf` | 13214676 | `70101044f9207eb8df43ee8e719158f3d8441be058bf172980681e195fa5d5a7` | VERIFIED |
| RAW-P16 main | env／runner | `platformio.raw_p16_endpoint_gallery_v1.ini`；`tools/mf1750_raw_p16_endpoint_gallery_v1_once.py` | — | contract `f9b1f6b8052322bedc6b702cb895425e7c3dc5e2d1b7d9ae6e68edaa1ffc409d`；NVS `rp16g_v1/cursor_p16g/boot_p16g` | OFFLINE READY / V1B-PRE BOUND |
| RAW-P16 main | BIN | `.pio/build-raw-p16-endpoint-gallery-v1/ec5_raw_p16_endpoint_gallery_v1/firmware.bin` | 797712 | `1cd68a43b8398e76636ebc80123e13aecb4edc6db4d0e7d927e7bcfc84680bef` | VERIFIED |
| RAW-P16 main | ELF | `.pio/build-raw-p16-endpoint-gallery-v1/ec5_raw_p16_endpoint_gallery_v1/firmware.elf` | 13282824 | `a1d1ad39460ba494f981b20a5d4f169792e2956749611a58b8b6037e2a639b4d` | VERIFIED |
| P16 post-white | env／runner | `platformio.raw_p16_endpoint_gallery_v1_white_containment.ini`；`tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_once.py` | — | contract `1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14`；NVS `rp16gw_v1/used_p16w` | OFFLINE READY |
| P16 post-white | BIN／ELF | `.pio/build-raw-p16-endpoint-gallery-v1-white-containment/.../firmware.{bin,elf}` | 786448／13214304 | `8c33085d0c9e0f03d651ad82a99a6336275f881fe9eb9e296cf526b5f80503c1`／`b65a4562b987de7adabe1d561504f1cf9c1b91d41b676ace32fd7adf81ab3a2a` | VERIFIED |
| LUMA-GRAY main | env／runner | `platformio.runtime_lut_luma_gray_v1.ini`；`tools/mf1750_runtime_lut_luma_gray_v1_once.py` | — | contract `db671c68cc1141231cbb0baf5f0667e6cdc292095af7b4f3cf9c3d5001d1b260`；NVS `rllg_v1/cursor_lg1/boot_lg1` | OFFLINE READY |
| LUMA-GRAY main | BIN／ELF | `.pio/build-runtime-lut-luma-gray-v1/.../firmware.{bin,elf}` | 801712／13296684 | `fbdbb9e7cca723c8ac2b39992c2b01792cd8bff9888e5d8a10d511602777b9b2`／`2df06b6da6070b12e23550eb9b81d68d7fd9b38c33a28b04a859491cd93ad8cc` | VERIFIED |
| LUMA containment | env／runner | `platformio.runtime_lut_luma_gray_v1_white_containment.ini`；`tools/mf1750_runtime_lut_luma_gray_v1_white_containment_once.py` | — | contract `d75573f6413dd861411147047c3784e0560de44241017eafc3cf46c274b99736`；NVS `rllgw_v1/used_lgw1` | OFFLINE READY |
| LUMA containment | BIN／ELF | `.pio/build-runtime-lut-luma-gray-v1-white-containment/.../firmware.{bin,elf}` | 786944／13214240 | `9c428924e225ef1dea6b04be7508745190ed5cda0a1bc8d12bf10146addfd6b6`／`fc2024e559d9477b3bb29bb915b9645fac2836ec7516894fc1b1cd771caddeff` | VERIFIED |

旧RAW-P16 main（contract `5d4d6084...6185c`，BIN `6aa3660d...1f75`，ELF
`587ae586...914b0`）仅为离线工件，**从未刷写，现已superseded**；它绑定已封存的V1前置白，
不得用于上机。主campaign/NVS/action/layout/mixed-R20和post-white来源在V1B重绑定中均未改变。

离线复核结果：V1B重绑定后的联合回归为`160 passed`；五套 PlatformIO 环境均 `SUCCESS`；
五套 pack／dry-validation 均在
`hardware_accessed=false`、`network_requests=0`、`display_refreshed=false` 下通过；相关
Python／测试文件的 Ruff check 与 format check 均通过；本轮涉及的main pack／runner／测试
再次通过Ruff check与format check。

实现必须具备：fresh identity/NVS；app-only flash和独立verify；J2-OFF只读诊断；严格ordinal；
每个action恰好一次ARM、EXECUTE、driver和visible refresh；raw BUSY前置门；无retry、fallback、
recovery、autochain；照片、分析sidecar、人工观察与receipt的SHA-256证据绑定。主固件与独立收容
必须是不同identity，且不能因主固件重启而重新获得执行资格。

## 8. 推荐上机顺序

在上述工件绑定与离线检查通过后，最短真屏顺序为：

1. J2 OFF下写入并独立verify `RAW-P16 pre-white anchor V1B`，完成只读诊断；J2 ON唯一刷白并
   拍摄干净白基线，随后J2 OFF；
2. J2 OFF下写入并独立verify `RAW-P16 main`；J2 ON唯一显示P16并拍照，随后J2 OFF；
3. J2 OFF下写入并独立verify `RAW-P16 post-white containment`；J2 ON唯一刷白并确认干净，
   随后J2 OFF；
4. 离线检查P16照片与坐标映射；这一步只产出端点观察名，不等待正式资格；
5. J2 OFF下写入并独立verify `LUMA-GRAY-V1`，完成只读诊断；
6. J2 ON，严格执行ordinal 1–8，只在ordinal 4和8拍摄并判候选；
7. J2 OFF，换刷LUMA独立白收容；J2 ON唯一刷白并确认闭环；最终J2 OFF；
8. 离线按四位置门→中性门→明度级门排序。没有命中就记录0，不从照片主观挑选；有命中则
   为少量候选建立fresh V2复核，不复用V1主固件。

本文件记录的固件、合同、哈希与离线回归全部闭合后，状态可升级为
`OFFLINE_READY / NOT_FLASHED / NOT LIVE-EXECUTED`；它仍不是任何一次真屏动作的现场授权。
