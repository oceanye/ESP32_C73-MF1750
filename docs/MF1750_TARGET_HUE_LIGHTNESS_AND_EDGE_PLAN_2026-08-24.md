# MF1750 目标有效色相、明度筛选与局刷边缘修正计划

日期：`2026-08-24`  
现场状态：`LIVE TESTS CLOSED / PANEL RETAINS BLUE 8×8 MATRIX / RELAY OFF / UPSTREAM STATE NOT INDEPENDENTLY PROVEN`  
本轮范围：离线代码、构建、测试和上机编排；不访问继电器、ESP32、设备网络或面板。

## 1. 结论

后续照片路线不再把“LUT code”直接当颜色，而以完整物理配方记录：

```text
logical_hue_id
+ controller
+ source_profile/source_code
+ middle_profile/middle_code（如有）
+ target_profile/target_code
+ target_repeat_count
+ partial/HOLD sequence
```

目标分两层：

1. V1 先建立 `13` 个照片有效色相族、合计 `84` 个首轮明度目标；
2. 路线成立后再向 `256` 个经标定、可重复、可局部共存的颜色槽扩展。

`84/256` 都是调色板结构目标，不是当前已经得到的颜色数。当前硬证据仍是：

- 7 个已重复肉眼区分的基础视觉组：黑、白、黄、红、Blue-1、Blue-2、绿；
- 单一 controller/profile 最多直接寻址 8 个 transport code；
- AB 每控制器有 64 个历史配方候选，但不等于 64 个唯一颜色；
- 尚无 24 色卡条件下的 canonical Lab/DeltaE00 唯一色计数。

## 2. 目标有效色相目录 V1

| ID | 优先级 | 目标色相族 | 当前种子 | 首轮明度级 | 256色长期槽位 |
|---|---:|---|---|---:|---:|
| N | P0 | 中性白—灰—黑 | 白、暗色端点；中间灰待找 | 8 | 32 |
| R | P0 | 红 | 已有红；CS2 active/code0 候选 | 6 | 16 |
| RO | P0 | 红橙／珊瑚／鲑粉 | CS2 active/code2、AB红粉分段 | 8 | 18 |
| O | P0 | 橙／肤色／米肤／棕 | CS2 code1/4、CS1 code3 | 8 | 32 |
| Y | P0 | 黄／金黄／赭黄 | 已有黄；CS1 code2 | 6 | 16 |
| YG | P1 | 黄绿／橄榄 | CS1 code0/2/4、AB黄绿分段 | 8 | 16 |
| G | P0 | 绿 | 已有绿；runtime code6 | 6 | 20 |
| T | P1 | 蓝绿／青绿／teal | runtime code6邻域 | 6 | 16 |
| C | P2 | 青／天蓝 | 当前为目标缺口 | 4 | 12 |
| B | P0 | 蓝 | Blue-1/Blue-2；runtime code5 | 8 | 28 |
| I | P1 | 靛／深蓝紫 | CS2 code3、CS1 code1 | 6 | 14 |
| V | P2 | 紫／紫罗兰 | 弱候选，尚未独立标定 | 4 | 12 |
| M | P1 | 酒红／洋红／玫红 | 大纯场与AB候选 | 6 | 18 |

首轮明度级合计 `84`；长期色相槽合计 `250`，另保留 `6` 个照片自适应槽，总计 `256`。
长期槽位是一个色相族内部的“明度 × 彩度 × 轻微色相子簇”总配额，不表示 N/O 各自能够
形成32级纯明度；首轮84项才是本阶段的明度搜索结构。
机器可读目录由 `tools/mf1750_target_hue_catalog.py` 生成；所有未测量名称仍保持
`candidate/search-seed`，不会被代码自动升级为合格颜色。

### 2.1 当前 L535 active-global 种子映射

| controller | code0 | code1 | code2 | code3 | code4 | code5 | code6 | code7 |
|---|---|---|---|---|---|---|---|---|
| CS1 | 橄榄黄绿 | 深紫灰 | 黄橄榄 | 深紫棕 | 浅黄绿 | 蓝 | 绿青 | 白 |
| CS2 | 红 | 米肤/淡粉 | 鲑粉 | 深蓝紫 | 棕橙 | 蓝 | 绿青 | 白 |

这些名称来自未标定照片。code5/6/7 跨控制器较一致；code0/1/2/4 明显依赖控制器；
code3 只确认均属暗色，未证明相同。照片渲染必须允许 CS1、CS2 为同一逻辑色使用不同配方。

## 3. 局刷底边异常：先定位，后修正

### 3.1 已知事实

- repeat-PTLW V3 中黑、蓝、绿可依次局部累积，旧区域没有随新区域闪烁；
- 三个色块都出现一侧齿线/不直，黑色最明显；
- exact SPD1657A 本地手册的窗口终点是包含式 `ye=y+h-1`；
- 相邻 Gx 参考实现存在 `ye=y+h` 的 controller workaround；两份证据冲突；
- 面板以竖向放置拍摄，操作者所称“物理底边”尚未被证明等于逻辑 Y-end。

因此不能直接把 `y+h` 称为修复。它只能作为受控实验比较项。

### 3.2 PTLW Y-end crossover A/B

固定同一个 controller-local ROI、同一个 code5、同样的120行/9600-byte DTM和相同刷新时序：

| ordinal | 动作 | CS1 | CS2 |
|---:|---|---|---|
| 1 | factory-OTP white health anchor | 全屏白 | 全屏白 |
| 2 | treatment A，同一 ROI | `ye=y+h-1` | `ye=y+h` |
| 3 | factory-OTP white crossover reset | 全屏白 | 全屏白 |
| 4 | treatment B，同一 ROI | `ye=y+h` | `ye=y+h-1` |
| 5 | factory-OTP white recovery | 全屏白 | 全屏白 |

这是 controller-swapped crossover：每个控制器都在独立白基线后分别经历两种端点方案，
避免把不同 Y 位置和累积历史混进结论。`y+h` 一侧声明121行窗口但仍发送120行 DTM，
只复现实验性相邻参考，不视为安全等价。

人工必须记录：FPC方向、物理异常边、可映射时的逻辑边、CS1/CS2差异。只有异常在两轮
互换中都跟随端点方案，才支持端点根因。若异常固定跟随物理方向或控制器，则 Y-end 被否证，
下一项转为逻辑轴定位和白色 halo/guard，而不是继续扩大 `y+h` 使用范围。

任何中途异常都不得跳过严格 ordinal。J2 OFF 后换刷独立 fresh-identity factory-OTP white
containment，再执行唯一白恢复。

### 3.3 已封版的 Endpoint A/B 离线产物

- 主固件 BIN：`796864 bytes / 5c3392684e50545d6f8ac03727d13bcd96ddf1f90cd2cede1ffa1435495404e8`；
- 主固件 ELF：`13290228 bytes / 1ce6bb2db9868c590748dbe5ce46fafaaf4147cdc8092b6b16935489744963d8`；
- 独立白收容 BIN：`786416 bytes / 7580b95291b329e832b543168e84d52fa2b2ba838e90a779323870f3b124102d`；
- 独立白收容 ELF：`13214068 bytes / 2c069827c6e2d4615b48be8fb4f94029edf8d36718fd99fd20be42d996648af8`；
- 主入口、Endpoint 收容、Brightness 收容和既有 cross-profile 收容已经拆成独立
  translation unit 与 build directory。既有 cross-profile 收容精确恢复为封存的
  `af13dcd2...c9fd53 / 28716453...5775`，没有重绑历史哈希。

这里的“离线就绪”仅表示可重建、可绑定和可执行合同通过；底边是否由 endpoint 引起，
仍必须由上述真屏 crossover 判定。

## 4. 首个同色相明度筛选：Blue 64-recipe V1

Blue 先行，因为 active/code5 是当前跨 CS1/CS2 最可靠的共同蓝色端点。该固件不是64个
已知明度，而是64个三步历史候选：

```text
active source code 0..7
→ commented middle code 0..7
→ active target code5
→ identical active target code5 repeat
```

- 每控制器 `8×8=64` 个内部纯码色块；
- 两控制器使用完全相同的格位和配方，合计128个观察格仍只代表64条 recipe；
- 每格 `52×58 px`，水平/垂直白缝分别 `8 px`；只评价色块中央，不评价白缝与边界；
- 无空间抖动；每个像素在每个阶段只接收一个 transport code；
- 全屏 global refresh，不宣称 partial/local HOLD；
- source/middle code 数字不代表亮度顺序，必须在测量后按 L* 重排；
- 固件初始 `qualified_brightness_levels=0`。

固定六动作：

| ordinal | 动作 | 人工用途 |
|---:|---|---|
| 1 | active runtime-code7 visual-white baseline | 确认白底；不是factory-OTP收容 |
| 2 | active source grid | 建立8种source历史 |
| 3 | commented middle grid | 形成64条两步历史 |
| 4 | active fixed target code5 | 首次筛选同蓝色相的明度候选 |
| 5 | identical active target code5 repeat | 检查候选是否收敛、漂移或保持 |
| 6 | active runtime-code7 visual-white recovery | 正常流程白收尾 |

重点人工门在 ordinal 4/5。若出现故障、严重异常或决定提前停止，不能从严格顺序越过到
ordinal 6；应 J2 OFF 后使用独立 fresh factory-OTP containment 白恢复。

机器目录 `offline_screening_batches/BLUE-BRIGHTNESS-64-V1` 已绑定 clean-build
主固件 contract `3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7`
及 BIN SHA-256 `afc978e1b9ed3ccd240302a8848c2bcc4f8727f68ec70c52b026934116a93d56`。
早停不再复用可能已消费的 cross-profile containment；改绑 brightness 专属
`rlhbcw_v1/used_hbcw1`、contract
`ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865`、
BIN SHA-256 `82e49e994570c9fb43ccbd7a7faa59adb55f5290d663aae2eee305250bcea12f`。
绑定后的 target-hue catalog ID 为
`94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`。

## 5. 明度资格规则

一个配方只有同时通过以下条件，才从“历史候选”升级为“有效明度”：

1. 色块内部均匀，为单像素纯码状态，无条纹、交错或空间抖动；
2. 边缘完整；局刷底边异常解决前只能筛选，不能正式入照片 palette；
3. 同一色相内，实测 CIE L* 单调；明显色相漂移者转入另一个色相族；
4. 高彩度色探索门暂用色相角偏差不大于10度、相邻绝对DeltaL*不小于8；
5. 中性灰不依赖不稳定的 hue angle，改看 L*、C* 与色偏；
6. 统一白基线下重复3次，并补5 s、60 s、600 s保持；
7. target repeat 后仍属于同一颜色组；
8. 不相交局刷和必要的 profile 切换后不灰化、不变色；
9. CS1/CS2找到相近配方，否则标记 controller-specific；
10. factory-OTP white 最终恢复干净。

拍摄使用固定机位、固定照明、固定手动曝光/白平衡；24色色卡与面板同平面。色卡照片可做
实验性相对筛选；没有分光测色仪时不宣称 canonical Lab/DeltaE00。

### 5.1 候选收集与资格派生工具

已新增离线 collector，将当前 catalog 与 Blue 64-recipe pack 固定绑定：

```powershell
python tools/mf1750_hue_observation_collector.py generate --pretty --output observations.json
python tools/mf1750_hue_observation_collector.py validate observations.json --pretty
python tools/mf1750_hue_observation_collector.py summary observations.json --pretty
```

每条 recipe 分别记录 CS1/CS2、target-repeat 前后、均匀性、颜色词、5/60/600 s、可选 Lab、
三次独立 run、明度关系、局部 HOLD 与 factory-white 恢复证据。输入不能直接写
`qualified=true`；资格由验证器派生。缺少 Lab、三次独立重复、HOLD 或白恢复证据时都保持
不合格；即使 recipe 通过全部门，也仍不自动宣称它代表一个“唯一颜色”。空模板固定为
`64 candidates / 0 qualified / unique-colour count unknown`。

## 6. 原定最短真屏路线（已被第8节实测更新取代）

1. `CROSS-PROFILE + LOCAL-HOLD V1` 已完成固定三窗口初步验证；
2. `BLUE-BRIGHTNESS-64-V1` 已完成主筛选，结果为0个肉眼蓝色明度候选；
3. 其 runtime-code7 收尾未使蓝矩阵变白，因此下次唯一首项改为专属 fresh factory-OTP white containment；
4. 只有人工确认干净白后，才能进入 R/RO/Y/YG/G/T 多目标色明度/历史批次；
5. `EDGE-YEND-AB-V1`、3次重复、5/60/600 s 和色卡评估后置，但候选入照片 palette 前仍必须通过。

每个固件都必须在 J2 OFF 下 app-only flash、独立 verify 和只读 diagnostic；每个可见动作
都要求 host preflight 与 firmware ARM/EXECUTE/DISPATCH 三处 raw BUSY=1，恰好一个driver，
无retry、fallback、recovery或autochain。只有需要人判断边缘/颜色时才停在人工门。

## 7. 本轮离线验证结论

- 四个新环境均经独立 clean build：Endpoint A/B 主/收容、Blue brightness 主/收容；
- catalog、collector、Blue、Endpoint、cross-profile 与封存 repeat-PTLW V3 联合回归
  `147 passed`；
- Ruff、format、`py_compile` 与仓库外工作目录的 runner `describe` 均通过；
- catalog ID：`94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`；
- 全程没有访问设备网络、COM、继电器或真屏，没有刷写、复位或刷新。

因此当前可直接进入上机前置流程，但不能提前宣告：已经获得84/256色、已经获得64级蓝色，
或已经修复底边。Blue V1 是首个可上机 pilot；其他色相要在它验证测量与收集流程后，
按 controller-specific 端点复制模板并各自封版。

## 8. 2026-08-24 真屏更新与路线调整

发现优先的两项主测试已经完成：

- cross-profile＋local-HOLD 固定 A→B→A 三窗口链通过：蓝、绿、黑顺序共存，旧区未观察到
  闪烁，最终 factory-OTP 白恢复干净；底边间隔线仍未解决；
- Blue brightness 64-recipe V1 的 actions 1–6 设备协议全部通过，但 action 4/5 最终蓝色
  矩阵左右一致、内部无肉眼深浅差异，因此保持 `0 visible candidates / 0 qualified levels`；
- 操作者在 action 3 彩色中间矩阵看到过深浅差异，说明明度搜索仍有价值，但该线索尚未定位
  到格位，必须在红／粉、黄／橄榄、绿／青绿等目标色专用批次重新捕获；
- Blue action 6 的 runtime-code7 白动作协议 PASS，却没有改变蓝矩阵，故正常白收尾视觉 FAIL。

当前面板保留蓝矩阵，relay 已 commanded OFF 且独立 query OFF。下次顺序改为：

1. brightness 专属 fresh factory-OTP containment 恢复并人工确认干净白；
2. 构造高信息密度的多目标色明度筛选，优先 R/RO/Y/YG/G/T；
3. 只对出现肉眼差异的目标色记录格位并做一次 immediate repeat；
4. 重复3次、5/60/600 s、24色色卡与 Lab 统一后置；
5. Endpoint A/B 底边诊断仍保留，但不阻塞纯色候选发现；任何候选在进入照片 palette 前
   仍必须补过边缘、局部 HOLD 和 factory-white 恢复门。

## 9. 多目标历史筛选 V1 已离线封版

为了不再为每个色相单独临时改固件，已把 active→commented 和
commented→active 两个方向合并为一个严格九动作 campaign：

| ordinal | 动作 | 用途 |
|---:|---|---|
| 1 | factory-OTP white health anchor | 建立真正白基线 |
| 2 | AB active source columns | 列0…7写入 source history |
| 3 | AB commented target rows | 行0…7写入 target，得到64条 AB recipe |
| 4 | AB identical target repeat | 观察同 target 重复后历史差异是否保留 |
| 5 | factory-OTP white direction separator | 清空 AB 历史，隔离 BA |
| 6 | BA commented source columns | 反向列0…7写入 source history |
| 7 | BA active target rows | 反向行0…7写入 target，得到64条 BA recipe |
| 8 | BA identical target repeat | 观察反向同 target 重复保持 |
| 9 | factory-OTP white recovery | 正常收尾 |

这一批的搜索量是 `64 AB + 64 BA = 128` 条有方向 recipe。两个控制器在
对应位置给出256个配对观察，但 CS1/CS2 的L535绑定并不相同，所以不把它们
写成“同波形重复”，也不把未测的格子数写成“256种颜色”。同一行的8格共享
相同target code，只改变source history，便于肉眼快速判断有无深浅/色相差异。

主campaign是全屏global refresh历史筛选，不含partial、局部HOLD、空间抖动、
`0x83/0x86`、未知命令或刷新中切电。runtime code7 只标记为
`unqualified separator/background transport code`，不再用作白恢复。ordinal 1/5/9
都独立分派到 factory-OTP white，跳过 runtime R20/R21 设置。

冻结产物：

- 主contract：`7f653cc9412d9b90a2c17a471dd54bfe0605c4abad41eeabe76ba1828f1958da`；
- 主BIN：`799552 bytes / b1f25c890e42f681a39e30a628678041eed4b41ff46f97c13d583ed0c592cb1e`；
- 主ELF：`13286676 bytes / b48be6967d1b6dc9d08ad191e7e149e9cfc77ef6cdaaf3fe5e8e62ab592bb216`；
- 独立收容BIN：`786512 bytes / f6e943b302e752ca3dcafaa6ce3c724e3ed9484e03472169d1f88c76b792d9f2`；
- 独立收容ELF：`13214104 bytes / 88ee12f604db97fbe435b5b23897db35f5df33594d1cc2027702fe0a32fd8180`。

新主+收容专项`49 passed`，与Blue、cross-profile、repeat-PTLW V3合并的8文件
回归`171 passed`；Ruff check/format、`py_compile`、pack/runner `describe`和最终产物哈希
复核均PASS。终审无代码阻断，但这只证明已审查的软件分派与产物绑定，
不代表真实SPI总线波形或颜色结果已被逻辑分析仪证明。

下次真屏的不可跳过顺序：

1. 当前蓝矩阵先换刷Blue专属fresh factory-OTP containment，人工确认干净全白；
2. J2 OFF后才换刷multi-target主固件，独立verify和4 GET只读诊断；
3. J2 ON后严格从ordinal1执行，每次只执行一个动作并停在人工观察门；
4. 任一视觉异常或终态失败都立即J2 OFF并永久封存主campaign；
5. 仅允许换刷独立fresh factory-OTP containment收容，一旦使用不得再恢复主顺序。

当前操作者已离场，relay已commanded OFF并独立query OFF，屏幕按双稳态保留
蓝矩阵。离场后未访问设备网络/COM，未刷写、复位或刷新真屏。

## 10. Endpoint A/B 真屏结果与 guard 路线（2026-08-24 22:19）

Endpoint A/B V1 已在同一 boot `be596f0f974f95ab` 严格完成5项：

1. factory-OTP white health anchor：人工确认全白干净；
2. CS1=`y+h-1`、CS2=`y+h`：两块蓝色在刷新中及最终均出现连续黑色底线，
   两侧一致；
3. factory-OTP white crossover reset：人工确认全白；
4. CS1=`y+h`、CS2=`y+h-1`：交换后仍出现连续黑色底线；
5. factory-OTP white recovery：设备 `COMPLETE/campaign_complete`，人工确认全白干净。

五项均恰好1次ARM、1次EXECUTE、1次driver与1次visible refresh，无retry、recovery或
autochain。Action2/4的DTM identity、上传时长和DRF时长一致；底线没有随端点方案跨
controller移动。因此，单纯的`y+h-1`/`y+h`差异和controller映射不是当前最强根因，
实验性的“121行窗口声明+120行DTM”不得进入正式局刷实现。

下一项改为完整发送、长度匹配的 `GUARD_DIRECTION_AB_V1`：保持逻辑蓝色ROI
`x=176..335, y=240..359`不变，每个处理都声明并发送128行/10240 bytes，只交换8行
code7/HOLD保护带的方向；8行优先用于提高首次肉眼判别力：

- `BOTTOM_GUARD_8`：120行code5蓝 + 8行code7 guard，PTLW `y=240..367`；
- `TOP_GUARD_8`：8行code7 guard + 120行code5蓝，PTLW `y=232..359`。

采用controller crossover：白→CS1 bottom/CS2 top→白→CS1 top/CS2 bottom→白。
L535、code5、目标ROI、SPI 1 MHz、CDI `0xFF`、PON后PTLW重锁以及BTST2/DRF/POF
均保持不变。code7只称为依赖factory-white基线的HOLD guard，不宣称主动白恢复。若异常随
“蓝色是否接触PTLW的Y-end”跨controller移动，即支持末端gate/runtime-LUT边界效应；若
命中再按`8→4→2→1`缩窄。若两种方向都不净，再进入双侧guard或全帧同图控制，而不是
继续扩大端点或改变LUT。

收尾后COM14/channel1已commanded OFF并独立query OFF，面板保持干净白；
`electrical_state_proven=false`保持。下一次真屏前必须先完成新identity/NVS、专属claim、
独立white containment、clean build、哈希绑定和离线测试。

## 11. GUARD_DIRECTION_AB_V1 离线封版与明早真屏顺序（2026-08-24 23:05）

第10节所列前置工作现已完成，但尚未刷入设备、尚未执行任何Guard真屏动作。主固件使用
独立的guard driver/program，不再把实验分支并入既有Endpoint V1源码。固定合同如下：

- 目标蓝色ROI始终为`x=176..335, y=240..359`，120行code5；
- `BOTTOM_GUARD_8`窗口为`y=240..367`，DTM顺序为120行`0x55`加8行`0x77`；
- `TOP_GUARD_8`窗口为`y=232..359`，DTM顺序为8行`0x77`加120行`0x55`；
- 两种处理均声明并实际发送128行、10240 bytes/controller，不再使用121行声明配120行DTM；
- CS1和CS2分别发送自己的PTLW，PON BUSY完成后重复相同PTLW；L535、code5、目标ROI、
  SPI 1 MHz、CDI `0xFF`、BTST2/DRF/POF均不变；
- code7仅表示依赖前置factory-white的HOLD guard，不能称为主动白恢复；
- ARM、EXECUTE和DISPATCH都要求raw BUSY=1；无retry、fallback、recovery、autochain或跳序。

冻结产物：

- 主contract：`c1ca226b7b5934dfba75daa7f03419c31438246638c86356d480e0abba84590c`；
- 主BIN：`797168 bytes / db5857e7926828cddb4fd9ac44ac860e275f5323060b7932ed429e2ab8d6e312`；
- 主ELF：`13291304 bytes / b285190f80318279d1460aefe263265f8fb0576f36f0f294c004a6f50f15a5f4`；
- 独立白收容contract：`5f1dd4cd9eff1c1824bab257fb2014665320d6493c64461daecb2ea3d2b56296`；
- 独立白收容BIN：`786544 bytes / 41fbf8a5c60f749ef1321a1397552c0e84696aae7975c5571d1b8b085cd9667d`；
- 独立白收容ELF：`13214128 bytes / 7f4f2b3873fdc04870d3cc8ad5cdf0e971beaa4fc602b8d3688898f842424154`。

离线验收包括主/收容clean build、Ruff check与format、`py_compile`、仓库外工作目录的两套
runner `describe`和专项`9 passed`。主runner和收容runner均提供
`diagnose-j2-off`：只允许direct/no-proxy的version/manifest/status/report四次GET，
不POST、不claim、不刷新；专项测试以mock设备核验了这一网络计数。上述离线工作没有访问
设备网络、COM、继电器或真屏，没有刷写、复位或刷新。

明早主campaign严格执行5个可见动作：

| ordinal | 固定动作 | 人工观察 |
|---:|---|---|
| 1 | factory-OTP white health anchor | 确认全屏干净白、无旧边线或色块 |
| 2 | CS1 bottom-guard-8；CS2 top-guard-8 | 分别记录两侧蓝块上/下边、guard外边及底线位置 |
| 3 | factory-OTP white crossover reset | 确认A处理完全清除并重新建立干净白基线 |
| 4 | CS1 top-guard-8；CS2 bottom-guard-8 | 使用相同观察口径，判断异常是否随guard方向跨controller移动 |
| 5 | factory-OTP white recovery | 确认全屏干净白、无蓝块/guard/边线残留 |

每个partial动作都要记录FPC方向、物理异常边、目标最后一行与guard/窗外白区的关系、
可确定时的逻辑Y方向以及CS1/CS2侧。判据是：若蓝色底边异常只在蓝色接触PTLW Y-end的
`TOP_GUARD_8`侧出现，并在A/B互换时跨controller移动，则支持末端gate/runtime-LUT边界
效应；若`BOTTOM_GUARD_8`让蓝色底边变净而异常转移到guard外边，也支持同类解释。若异常
固定在同一物理侧、同一蓝色底边，或两种guard方向都相同，则本实验不支持方向guard作为
修复，应转入双侧guard或全帧同图控制。只有出现方向性命中，才继续`8→4→2→1`细化。

上机前仍须在J2 OFF下刷入主BIN、独立verify并运行4 GET诊断；刷入本身不产生可见刷新。
任何partial动作出现协议故障、异常发热、固定线扩大或无法判断的异常时，立即J2 OFF并永久
封存主campaign，不允许跳到其后白动作；需要恢复时换刷fresh独立white containment，最多
增加1次可见factory-OTP白动作。正常路线为5次真屏，异常收容路线最多为`5之前已完成次数+1`，
不把收容动作计作Guard实验结果。

今晚用户已离场，relay/J2已确认OFF，当前屏幕为干净白；Guard主固件尚未刷入。明早从
J2-OFF刷入/verify/诊断门开始，不继承任何尚未发生的live授权或设备身份结论。

## 12. 旧Endpoint证据链的确定性回归（2026-08-24 23:11）

Guard已与Endpoint共享repeat driver/main完全隔离。离线审计确认，Endpoint封版后
`ec5_chroma_grid_epd_driver.h`新增的`ReverseSource/ReverseTarget`枚举会改变重建ELF元数据，
但与已完成Endpoint真屏动作无关。使用封版时枚举ABI快照在原路径事务式clean build后，
旧产物逐字节复现：

- BIN：`796864 bytes / 5c3392684e50545d6f8ac03727d13bcd96ddf1f90cd2cede1ffa1435495404e8`；
- ELF：`13290228 bytes / 1ce6bb2db9868c590748dbe5ce46fafaaf4147cdc8092b6b16935489744963d8`。

共享头随后已恢复为现行版本，SHA-256为
`d1788eb691b3dcaf5bd62a82721de8032f20bbb29e5cf52ff97e7ec4d03e0b6a`，两枚新枚举均保留。
Guard+Endpoint联合回归为`17 passed`，Ruff与`py_compile` PASS。不得直接用现行扩展头
clean-rebuild并覆盖旧Endpoint产物目录；已执行真屏结果仍绑定上述exact封版哈希。

## 13. Guard 视觉阴性后的全帧 / PTLW 单变量 A/B（2026-08-25）

Guard Direction A/B 后续已经由操作者完成肉眼观察：两种guard方向都仍出现相同的连续
黑色底线，最终factory-OTP白可清除。当前没有足够的独立protocol输出把该段追认为完整
机器证据，因此只保留为人工视觉结果；它足以停止继续做`8→4→2→1` guard细化，不用于
宣称修复或生成新颜色。

下一固件改为真正的寻址运输单变量：A与B都先把每个控制器完整预装为code7且不刷新，
随后生成相同的code5蓝色ROI和相同最终SRAM；A不设置PTLW并发送完整153600-byte复合DTM，
B对每个控制器只发送一次包含式9-byte PTLW，再发送9600-byte cropped DTM。两种处理共用
同一L535 profile、同一现行初始化以及同一`PON→DRF00→POF00`处理阶段刷新，不再加入
action-stage CDI/BTST2、PON后PTLW重写、额外DTM字节或`0x86`。现行公共初始化中已有的
CDI/BTST2保持不变，不能把本合同误读为整次transaction完全不含这些初始化命令。

固定真屏序列为白→A→白→B→白。A干净/B有线时才追加“全控制器PTLW+完整DTM”C组；
A/B均有线则转查运行时波形/目标边缘；A有线/B干净则查完整帧外围重驱；两者都干净时，
先将B从fresh white重复3轮。只有B左右均边界干净、3轮重复一致、后续非重叠patch保持且
factory白可清除，才释放正式`2×8=16`名义槽标定。16槽必须逐项测量和去重，不能预先称为
16种独立颜色，也不能外推为任意LUT或256色。

离线封版：contract=`9e7414f483174cc74fa8adca9c1c2ea4c23c3250f84882969f34e87efb25a8fa`；
BIN=`799408/6e42e3b08ec8053a3efea3e4f12d334dc246abb99576454188136391fa1130fb`；
ELF=`13301880/b64d7216ff240df3a736542418cf263c0112bc03469388798e19c1fb34dcc405`。
专项`12 passed`，Ruff、`py_compile`、runner `describe`与双产物绑定均PASS。构建期间未访问
设备网络、COM、继电器或真屏，未刷写、复位或刷新。完整顺序见
`MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_RUNBOOK_2026-08-25.md`。
