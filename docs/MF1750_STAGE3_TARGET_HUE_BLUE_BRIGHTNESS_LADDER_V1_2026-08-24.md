# MF1750 目标色相／明度候选阶梯 V1（蓝色首批）

日期：`2026-08-24`  
状态：`LIVE 6/6 PROTOCOL COMPLETE / BLUE BRIGHTNESS DIFFERENCE NOT FOUND / RUNTIME-WHITE VISUAL FAIL / RELAY OFF`

## 1. 目标与证据边界

本批只筛选**同一目标蓝色色相的历史明度候选**，不把候选称为已经确认的明度等级：

- 目标：active global-header 下 transport `code5`；现有真屏证据把 CS1/CS2 都暂记为高置信蓝色，但未做色度标定；
- 每个控制器承载相同的 `8×8=64` 个 recipe，两侧是物理重复观察，不是 128 种颜色；
- 每格内部始终写同一个 transport code；没有空间抖动、像素混色或相邻色条融合；
- `qualified_brightness_levels=0`，只有真屏重复、色卡测量和稳定性检查后才能增加；
- CS1/CS2 输出颜色相等尚未获得色度证据，manifest 固定 `controller_color_equivalence_claimed=false`；
- 本批使用全屏 packed frame 与全局刷新，不测试也不声称局部 HOLD；局部刷新底边缺陷是独立门槛。

## 2. 配方映射

两控制器均使用相同 controller-local 坐标，不镜像：

- grid：`8行 × 8列`；
- local origin：`x=20, y=40`；
- cell：`52×58 px`；
- gutter：`8×8 px`；
- 列 `0..7`：active source code `0..7`；
- 行 `0..7`：commented middle code `0..7`；
- 所有格 target：active code `5`；
- target repeat：active code `5` 再执行一次。

第 `r` 行第 `c` 列 recipe：

`active source(c) → commented middle(r) → active target(5) → active target(5) repeat`

因此每一行的 8 个相邻方格具有同一 middle／target，source history 从 `0` 连续到 `7`，便于肉眼横向比较。完整的 64 recipe、两个 controller record、ROI、profile、source/middle/target code 和 `repeat_count=2` 均由：

`python tools/mf1750_runtime_lut_hue_brightness_blue_v1_pack.py`

确定性输出。

白缝只作为定位分隔，不属于测量区域。边界粒子可能受白缝历史影响，因此只观察每格内部，不用 gutter、边缘或相邻条带混合结果判断明度。

## 3. 六个严格动作

| ordinal | profile / frame | 用途 |
|---:|---|---|
| 1 | active / runtime-code7 visual-white | 视觉白基线；不是 factory-OTP 白声明 |
| 2 | active / source columns | 每行相邻八格建立 source `0..7` |
| 3 | commented / middle rows | 每行写入固定 middle `0..7` |
| 4 | active / fixed target code5 | 首次观察 64 个蓝色历史候选 |
| 5 | active / identical target code5 repeat | 检查候选是否被相同 target 重刷抹平 |
| 6 | active / runtime-code7 visual-white | 正常流程白恢复 |

每次调用只允许一个 ordinal、一个 ARM、一个 EXECUTE、一个 driver call；NVS namespace/key 为 `rlhbb_v1/cursor_hbb1`，terminal next ordinal 为 `7`。ARM、EXECUTE 和 dispatch 三处固件均要求 raw `BUSY=1`；host preflight 对六项也只接受 `BUSY=1`。PON/DRF/POF BUSY、正等待时间、frame/DTM FNV、safe-finish BUSY 和 GPIO 必须全部匹配。

如果 action 4 或 5 人工判断失败，不允许跳到 action 6。应停止当前 campaign，app-only 改刷已封装的独立 fresh-identity factory-OTP 白收容固件：

- config：`platformio.runtime_lut_hue_brightness_blue_v1_white_containment.ini`
- runner：`tools/mf1750_runtime_lut_hue_brightness_blue_v1_white_containment_once.py`
- identity / NVS：`EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT`，`rlhbcw_v1/used_hbcw1`
- BIN：`786448 bytes`
- BIN SHA-256：`82e49e994570c9fb43ccbd7a7faa59adb55f5290d663aae2eee305250bcea12f`
- ELF：`13214100 bytes`
- ELF SHA-256：`d1e895623fac56586cc6029d84644580dbbf76369ba6dd09badb7ac89e616250`
- contract ID：`ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865`

该收容入口具有 brightness 专属 build/test/campaign、descriptor、action、
NVS、route 与永久 claim；不复用此前 cross-profile HOLD 的 `af13…` 镜像，
因此不受其可能已消费的 NVS/claim 影响。它不依赖本 campaign NVS，也不会
越序重放已消费动作；ARM、EXECUTE、dispatch 同样只接受 raw `BUSY=1`。

## 4. 离线产物

- PlatformIO config：`platformio.runtime_lut_hue_brightness_blue_v1.ini`
- identity：`src/ec5_runtime_lut_hue_brightness_blue_v1_identity.inc`
- device config：`src/ec5_runtime_lut_hue_brightness_blue_v1_main_config.inc`
- pack：`tools/mf1750_runtime_lut_hue_brightness_blue_v1_pack.py`
- one-shot runner：`tools/mf1750_runtime_lut_hue_brightness_blue_v1_once.py`
- tests：`tests/test_mf1750_runtime_lut_hue_brightness_blue_v1.py`
- containment pack：`tools/mf1750_runtime_lut_hue_brightness_blue_v1_white_containment_pack.py`
- containment tests：`tests/test_mf1750_runtime_lut_hue_brightness_blue_v1_white_containment.py`

最终 clean build：

- BIN：`795376 bytes`
- BIN SHA-256：`afc978e1b9ed3ccd240302a8848c2bcc4f8727f68ec70c52b026934116a93d56`
- ELF：`13280776 bytes`
- ELF SHA-256：`d1cddb1ce07aa427f24b188a43390117dcf806321b6fe4f5aed87520fc3ee8e7`
- contract ID：`3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7`
- target-hue catalog ID：`94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`

验证：目标色相目录、本批定向、专属收容、endpoint 隔离与共享 cross-palette regression 共 `95 passed`；Ruff、format check、`py_compile`、direct `describe`（含仓库外 CWD）均通过。整个开发过程未访问设备网络、COM、继电器、ESP32 或屏幕，未刷写、复位或刷新。

## 5. 真屏判读与后续

action 4 先比较每一行的八个内部色块：只记录“更深／更浅／偏色／无差异／不均匀”，不立即编号为明度等级。action 5 再检查差异是否保持。左右相同 recipe 必须分别记录；两侧都重复出现且色相仍在蓝色容差内，才进入色卡测量和 3 次重复。

候选证据统一写入 `tools/mf1750_hue_observation_collector.py` 生成的绑定模板；该工具只从
完整证据派生 qualification，操作者不能直接写入 qualified 标志。空模板保持64候选、0合格，
通过配方数也不会自动换算成唯一颜色数。

蓝色通过后，下一批优先复制相同结构到 active `code6` 绿／蓝绿色。active `code0/1/2/4` 的 CS1/CS2 provisional hue 明显不同，后续必须按 controller 分开定义目标色相，不能把同 code 当成同一颜色。

## 6. 2026-08-24 真屏结果

### 6.1 现场身份与协议结果

- 主 BIN 在 J2 OFF 下只写入 app `0x10000`；写入内置 hash 与独立 `verify_flash` 均 PASS；
- ESP32-S3 MAC：`a4:cb:8f:d9:fc:d4`；boot nonce：`7de23beca3837011`；
- J2-OFF 四个只读 GET 确认 build/contract 正确、NVS key absent、`next_ordinal=1`、
  `0 ARM / 0 EXECUTE / 0 driver`；
- ordinal 1–6 均为同一 boot、exactly one ARM/EXECUTE/driver，设备端
  `COMPLETE`，最终 `campaign_complete=true / next_ordinal=7`；
- 六项都没有 retry、fallback、recovery 或 autochain。

证据目录：

`.test-output/hardware/MF1750_TARGET_HUE_BLUE_BRIGHTNESS_LIVE_20260824_V1/`

结果文件 SHA-256：

- action 1：`84712ebf346381ea05bbe49cc067eb446caf73ed6edcad52bd893f6a30c3b6a3`
- action 2：`83006157baa013338b30710bdc899ab25bc6e9bc9df04da85e73c1fa81a622d6`
- action 3：`938a82d90dcaf0876f703a48c2b619f1cbb4b16e165cd39a74f5a06fba32540d`
- action 4：`65e10c34ed76a5f7c2796318a667b58310c442513db113ff83b8206a2dd082c1`
- action 5：`03ddb890747ce2066c786a5cce942527e55c1f1624497f7624d3d5670a056aeb`
- action 6：`7802f005ef1a3cb387bbdbb60df9bd73bfcfcc03f021d4b52ae21d1fc6a34116`

### 6.2 人工观察与裁决

- action 1：实验 runtime-LUT code7 白基线为干净白；
- action 3：在最后一次彩色中间矩阵中，操作者看到部分颜色存在深浅差异；当时未逐格定位，
  因而只保留为“其他目标色值得继续筛选”的线索，不形成配方候选；
- action 4：最终统一落到 active/code5 蓝后，左右 8×8 对应一致，矩阵内部未见深浅差异；
- action 5：相同蓝 target 再刷一次后仍一致，没有格子变深、变浅或偏灰；
- action 6：设备和 BUSY 证据均为 PASS，但操作者确认画面仍完整保留蓝色矩阵，未变白。

action 1 与 action 6 的 frame、双 DTM 与 FNV 完全相同；action 4 与 action 5 也完全
相同。六项 PON/DRF/POF、BUSY、mapping、safe-finish 和双控制器均正常，且 action 3
的 commented profile DRF 时间与 active actions 明显不同。当前最强解释不是漏传、越序或
单控制器故障，而是：**runtime-LUT code7 被错误赋予了“主动白恢复”的光学语义。**
它从既有白态执行时可能近似 identity/HOLD，因此 action 1 看起来仍白；从 code5 蓝态执行时
也近似 HOLD，所以 action 6 保留完整蓝格。该解释仍需由下次 factory-OTP white 成功恢复
进一步支持，当前不提升为芯片通用结论。

因此本批裁决为：

- `64 recipes screened / 0 visible blue-brightness candidates / 0 qualified levels`；
- 不能把 action 3 的瞬时或中间态差异计为蓝色明度，也不能据此增加唯一颜色数量；
- runtime code7 在白基线上可以显示白，但不足以从该蓝矩阵可靠恢复白色；
- action 6 必须记为 `PROTOCOL PASS / VISUAL RECOVERY FAIL`，不能用 campaign complete
  冒充 clean-white 物理收尾。
- action 3 的差异若只发生在不同行，可能只是不同 commented code 的普通颜色差异；只有
  同一行内（相同 final middle code、不同 source 列）仍有差异，才构成历史明度候选。

### 6.3 安全停点与下一步

操作者准备离场后，继电器 COM14/channel1 已执行 OFF，随后独立 query 再次返回
`commanded_state=OFF`；继电器没有负载侧反馈，故仍保留
`electrical_state_proven=false`。面板按双稳态保留蓝色矩阵；没有继续刷新或刷写。

下次真屏的第一项不是继续色彩枚举，而是：

1. 保持 J2 OFF；
2. app-only 写入并独立校验本文件第3节绑定的 brightness 专属 factory-OTP containment；
3. 做 fresh identity/NVS/0-driver 只读核对；
4. J2 ON 后只执行唯一 factory-OTP 白动作；
5. 人工确认蓝矩阵全部清除并得到干净白；
6. 立即 J2 OFF，再开始其他目标色固件。

后续发现优先级改为：先复现并定位 action 3 暗示的目标色相关明度效应，优先测试
红／粉、黄／橄榄与绿／青绿。新批次必须把 target 矩阵本身设为强制拍照/人工门，先逐行
比较同 target 的八个 source-history 格，再执行 identical target repeat；不得追加一个会把
差异压平的统一 active/code5。所有正常收尾改用 factory-OTP white，不再把 runtime code7
命名为 white recovery。只有出现肉眼同行差异的目标色才进入坐标记录、重复性、
5/60/600 s 与色卡测量。蓝色本批不安排高成本可靠性复测。
