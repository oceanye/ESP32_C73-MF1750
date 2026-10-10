# MF1750 目标黄／橄榄色历史明度候选阶梯 V1

日期：`2026-08-26`  
状态：`OFFLINE BUILD READY / NOT FLASHED / NOT RUN / QUALIFIED=0`

## 1. 目标 transport code 的证据裁决

本批固定选择 active global-header 下的 transport `code2`。这个选择不是从颜色名猜出，
而是以下现有证据的最窄交集：

- `host/extended_color/mf1750_target_hues.py` 的机器目录把 `Y` 的唯一 direct seed 固定为
  `CS1 / active / code2 / 黄/橄榄黄 / visual-candidate`；目录 catalog ID 为
  `94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`；
- `docs/MF1750_TARGET_HUE_LIGHTNESS_AND_EDGE_PLAN_2026-08-24.md` 的目标表把 `Y` 写成
  “已有黄；CS1 code2”，active 映射表又把 CS1/code2 写成“黄橄榄”；
- `docs/MF1750_STAGE3_RUNTIME_LUT_PARTIAL_HOLD_V3_PLAN_2026-08-23.md` 保存的 atlas
  观察映射同样是 CS1/code2“黄/橄榄黄”，而 CS2/code2 是“鲑粉”；
- `docs/STATUS_HANDOFF.md` 锁定同一 catalog ID、`0 QUALIFIED COLOURS` 证据边界和
  操作者离场期间禁止设备网络、COM、刷写、复位、刷新、继电器动作的现场约束。

因此 code0/code4 只保留为更宽的 `YG` 黄绿／橄榄候选，不替代唯一 `Y` direct seed。
同一个 code2 在 CS2 的 provisional appearance 是鲑粉，故本批明确固定
`controller_color_equivalence_claimed=false`。本批名称“黄／橄榄”只描述选种目标，
不声称两控制器同色，也不声称经过色度标定或已取得合格黄色。

## 2. 固定 8×8 配方

每个控制器承载完全相同的 64 个 recipe；两侧是 128 个物理观察，不是 128 个唯一颜色：

- controller-local grid：`8行 × 8列`，origin `x=20, y=40`；
- cell：`52×58 px`，gutter：`8×8 px`，两侧不镜像；
- 列 `0..7`：active source code `0..7`；
- 行 `0..7`：commented middle code `0..7`；
- target 与独立 target repeat：active code `2`；
- 每格内部为单一 transport code；没有空间抖动、像素混色或 partial/window refresh；
- runtime code7 只作未资格化 separator/background，不把它称为白色；
- `qualified_brightness_levels=0`，只生成历史明度候选。

第 `r` 行第 `c` 列的 recipe 为：

`active source(c) → commented middle(r) → active target(2) → active target(2) repeat`

完整 frame、双 controller DTM、histogram、FNV、SHA、64 recipe 和 contract 由
`tools/mf1750_runtime_lut_hue_brightness_yellow_olive_v1_pack.py` 确定性生成。

## 3. 六个严格动作与失败收容

| ordinal | profile / frame | 用途 |
|---:|---|---|
| 1 | factory-OTP / full white `0x11` | 白场健康锚 |
| 2 | active / source columns | source `0..7` 列 |
| 3 | commented / middle rows | middle `0..7` 行 |
| 4 | active / fixed target code2 | 首次目标候选观察 |
| 5 | active / identical target code2 | 独立 repeat 动作 |
| 6 | factory-OTP / full white `0x11` | 正常白恢复 |

主 campaign 使用专属 NVS namespace `rlhyob_v1`、cursor key `cursor_yob1`、write-once
boot-binding key `boot_yob1`、专属 route
`/api/ec5/target-hue-yellow-olive-brightness-v1/`、六个新 descriptor/action 和永久 claims。
fresh setup 在安装网络 route 前把硬件随机的 64-bit 当前 boot nonce 写入 `boot_yob1`；仅当
cursor key absent 且 READY/ordinal1 时允许首次写入。已有 binding 必须与当前 boot 精确相等；
否则 setup 在 `epdBegin()` 前 fault-lock。ARM、EXECUTE、dispatch 又分别在任何 cursor mutation
或 driver call 前复验。因此完成 ordinal1 后的重启、改刷收容再改回主固件、binding 缺失或
篡改都不能用 direct exact POST 续跑。ARM、EXECUTE、dispatch 和 host preflight 同时只接受
raw `BUSY=1`。每个动作只允许一个 ARM、一个 EXECUTE、一个 driver call；无 retry、recovery、
autochain、NVS clear route 或 raw frame ingress。

ordinal4 是快速人工门：若没有明确的**同行／同 target** 差异，立即封存主 campaign，ordinal5
和 ordinal6 都不执行；relay OFF 后另刷 fresh containment 白恢复，再转下一目标。只有
ordinal4 出现明确候选且操作者显式确认，runner 才释放 ordinal5 repeat；ordinal5 接受后才可
执行 ordinal6 主白恢复。

若目标或 repeat 人工失败，停止主 campaign；不允许借 ordinal 6 越序恢复。独立
factory-OTP 白收容入口使用全新的 build/test/campaign/contract/NVS/route/action/claim：

- config：`platformio.runtime_lut_hue_brightness_yellow_olive_v1_white_containment.ini`
- NVS：`rlhyocw_v1/used_yocw1`
- contract：`fbedf22afbe6129e2824b9726f8be16f8b949c77cf02eb49d9707166d1ec095b`
- action：`ac05c0d290e91a33e92f3eccb00bce68d35b6852bae813dfabbb6950d485d45b`
- BIN：`786544 bytes`，SHA-256
  `80dfebbd0f609203d1b4f7f9784389815bf0f54d8e3efb4b5fa42febc0b61ec1`
- ELF：`13214132 bytes`，SHA-256
  `4e846aca492bac6dc2d460c87aeb46a76eba97fc292fc5dde8536b73f84ee8e8`

该入口不依赖主 campaign NVS，也不允许收容后恢复主序列。收容使用另一 namespace，不会
删除 `rlhyob_v1/boot_yob1`；因此收容后改回主固件的新 boot 会由设备端 binding 门锁死，而
不只是依赖 host runner 的顺序判断。

## 4. 可刷离线产物

主固件 clean build：

- config：`platformio.runtime_lut_hue_brightness_yellow_olive_v1.ini`
- build environment：`ec5_runtime_lut_hue_brightness_yellow_olive_v1`
- contract ID：`47cff189c5719306693af8c0fe6cec7f6ae42ea7b9c3f82bfba94eecd0484899`
- BIN：`802208 bytes`，SHA-256
  `7e45f52dcafdea3c5f9962631a8c1b13bc0390131e3bebc0f5accecd8c5a8563`
- ELF：`13299612 bytes`，SHA-256
  `5a8fabd61f3230d640323873f29b055acb0eef5197769efded3ce114f0615ae5`
- linker map：`12038615 bytes`，SHA-256
  `2263e918a5b53789737bbae7ae418da692534b797b793da2f974db3b5e9b01e2`

关键源码冻结哈希：

| 文件 | SHA-256 |
|---|---|
| `platformio.runtime_lut_hue_brightness_yellow_olive_v1.ini` | `afa14f5696ad1619c6c0455750027b596881b2cbd20c462c0d57346f2fab9482` |
| `src/ec5_runtime_lut_hue_brightness_yellow_olive_v1_identity.inc` | `f8a987ef5d1ccfdf1051f04d72a2666506b98ce5493a252483a1abc87ab13604` |
| `src/ec5_runtime_lut_hue_brightness_yellow_olive_v1_main_config.inc` | `721cf9a7fd1aba127500e9fe35ba7f2cfa88f0af081827deff4899d53f53d9a7` |
| `src/ec5_runtime_lut_hue_brightness_yellow_olive_v1_program.inc` | `87dd994cc6aadbc923968c5f2f87ce3c82788acae55cbd69b176c7dce2c518a3` |
| `src/ec5_runtime_lut_hue_brightness_yellow_olive_v1_driver.inc` | `9e374ae96f7ef838b231008c6641b32a5117e1e68dc75be4c131dc2352fcf6ce` |
| `tools/mf1750_runtime_lut_hue_brightness_yellow_olive_v1_pack.py` | `7b9abff99ee3c86653ecc769dd46ddadf95425eb99b42b523703023804f323e1` |
| `tools/mf1750_runtime_lut_hue_brightness_yellow_olive_v1_once.py` | `e2ba1e3c5839e6c656772e7a3e613fbc92e7fd274b68af79e6c46176c8c45629` |

设备用 `esp_ota_get_app_description().app_elf_sha256` 回报真实运行 ELF identity；clean BIN 的
app descriptor 嵌入值与上述 ELF 文件 SHA 精确一致，host 对每个 version/manifest/status/report
都要求 exact match。依赖边界单独记录在
`MF1750_RUNTIME_LUT_HUE_BRIGHTNESS_YELLOW_OLIVE_V1_DEPENDENCY_BOUNDARY_2026-08-27.json`：
列出 clean build 实际解析的平台、framework、工具链、库根和完整 linker map 的哈希。设备不
回报完整依赖清单，本包也不虚构未物化的完整 transitive source/build-host SBOM。

`describe` 是零网络、零可见刷新路径；真正 `run` 仍要求现场身份、artifact、NVS、BUSY、
顺序和永久 claim 全部精确通过。本轮仅进行了本地文件生成、clean build、哈希和 fake-device
测试；未访问设备 IP、串口、继电器或真屏，未刷写、复位、上电或刷新。

## 5. 现场证据边界

此文件不是现场执行授权。将来只有操作者在场、明确恢复现场权限并完成 J2/电气门后，
才可从 ordinal 1 开始。action 4/5 应逐行比较相同 middle/target 下八个 source-history
方格的内部区域；两控制器分别记录，不合并颜色名。ordinal4 若没有明确同行差异，快速门立即
走 negative early seal，不为“再看一次”执行 repeat。任何肉眼差异仍只是候选，需独立重复、
5/60/600 s、色卡/Lab、稳定性、HOLD、边缘质量和 factory-white 恢复门，才能提升资格。

## 6. 明日上机严格顺序

今晚保持冻结，不做任何 I/O。明日只有操作者回到现场并重新明确授权后，才按下列顺序逐项
推进；每一项都可单独停止，不从文档推导隐式授权：

1. 操作者确认 J2 断开、继电器/电源处于安全状态；先离线重验主 BIN/ELF 大小、SHA、
   contract 和 `describe` artifact binding。
2. 保持 J2 OFF，只把主 `firmware.bin` 写入 app offset `0x10000`；不擦 bootloader、
   partition table 或 NVS。完成写入内建 hash 和独立 verify，观察值必须等于本文件第4节。
3. 仍保持 J2 OFF，只读取得 version/manifest/status/report 四个 endpoint；要求 exact
   build/test/campaign/contract/route、running ELF SHA、fresh `rlhyob_v1/cursor_yob1` cursor
   key absent、`boot_yob1` present 且 matches-current、READY/next ordinal 1、0 ARM/EXECUTE/
   driver/visible refresh、GPIO 全低。任何不一致都在 0 POST/0 claim 处停止。此 boot 此后
   不得重启；重启不是可恢复事件。
4. 操作者确认 J2 ON、电压/限流/电流/温度正常后，才为 ordinal 1 单独授权。runner 必须先
   重做 exact 四 GET 和 raw `BUSY=1`，再永久 claim，且只执行一个 ARM、一个 EXECUTE、
   一个 factory-OTP white driver。人工确认健康白场后停止。
5. 分别单独授权 ordinal 2 和 3；每项都要求 same boot、前项 COMPLETE、raw `BUSY=1` 和
   exact frame/双 DTM/FNV。ordinal 2 后记录 source 列，ordinal 3 后记录 middle 行；不自动
   进入 target。
6. 单独授权 ordinal 4。刷新完成立即拍摄并逐行比较左右各自 8 个方格内部；先保存 target
   首次态，不把差异命名为明度等级，也不执行 ordinal 5 直到人工记录完成。
7. 若 ordinal 4 **没有明确同行／同 target 差异**：立即封存主 campaign，不执行 ordinal5，
   也不执行 ordinal6；relay OFF 后走 fresh containment 白恢复，再转下一目标。若 ordinal4
   有明确候选，记录坐标后使用 `--confirm-visible-candidate-after-ordinal4` 显式释放 ordinal5，
   保存 repeat 照片并裁决“保持／收敛／偏色／不均匀／无差异”。
8. 若 ordinal 1--5 存在 visual/terminal failure，或 ordinal4 走 negative early seal：立即
   J2 OFF，不 retry、不越序、不 resume
   主 campaign。只有另行明确授权后，才 app-only 改刷第3节绑定的独立白收容固件，先做
   fresh J2-OFF 4 GET/0 POST/0 claim，再 J2 ON 执行其唯一 factory-white action；收容后主
   campaign 永久停止，设备端 `boot_yob1` 也禁止改刷回来续跑。
9. 只有 ordinal5 明确接受后，才单独授权 ordinal6 factory-OTP white recovery。人工确认
   全屏干净白且无矩阵残留，随后 J2 OFF、继电器 OFF，并以独立状态查询闭合；软件 relay
   状态不冒充负载侧电压测量。

六个主 action ID 依次为：

1. `479f3cd677ac2c3b65fa9950fad622533b9c678bb0d7146394b0bf78aed83c52`
2. `012f89ef6a8194cdcbff17720a833861825d7d9655f517c2da92e86d91caea29`
3. `1d307a7c22bf54340d90ec3eaee548040933b899c159480898a4d96dbf494f4a`
4. `7cfe7a0c92411656fa0ba0f1f512393818ab86e750ec71f4e2adaee0fff6d0fa`
5. `9fe8f7f1c271e4003e04ec42de0e2e27f623d0185bb942271d769ebe49cb180a`
6. `f2695ebfec6ed1e887ae5561696fe81591f6908454e0268df2b069d4826fa585`
