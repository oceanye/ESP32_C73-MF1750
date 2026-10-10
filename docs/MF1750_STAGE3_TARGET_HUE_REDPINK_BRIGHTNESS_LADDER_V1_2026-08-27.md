# MF1750 目标色相／明度候选阶梯 V1（红／粉线索批）

日期：`2026-08-27`  
状态：`OFFLINE BUILD READY / NOT FLASHED / NOT RUN / 0 QUALIFIED LEVELS`

## 1. 目标码裁决

本批固定 active-global transport `code0`，但不把它写成两个控制器共享的“红／粉色”：

- `host/extended_color/mf1750_target_hues.py:59-68` 把 R 的直接 endpoint 候选明确绑定到 `CS2 + active + code0`，视觉名为红；
- `docs/STATUS_HANDOFF.md:15` 只确认现阶段基础视觉组中有红，catalog ID 为 `94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`，没有合格粉色；
- `docs/MF1750_TARGET_HUE_LIGHTNESS_AND_EDGE_PLAN_2026-08-24.md:59-65` 记录 active `code0` 在 CS2 为红候选、在 CS1 为橄榄黄绿候选，并明确 code0 强依赖控制器；
- active `code1` 浅粉和 `code2` 鲑粉在 catalog 中只是 search seed／未标定多候选，不能优先于直接红 endpoint；
- `host/dither_color_atlas.py:40-55,98-104` 的 code3 红和 code3+code1 浅粉只属于 factory-OTP 空间抖动 atlas，不能外推到 runtime-L535 transport，也不符合本批“无空间抖动”。

因此选择 `code0` 是证据约束的最可信选择，不是猜测。可获得的目标声明仅为：CS2 红色直接 endpoint 视觉候选；CS1 同码橄榄／黄绿视觉候选。`controller_color_equivalence_claimed=false`、`shared_red_or_pink_hue_claimed=false`、`qualified_brightness_levels=0`。

runtime `code7` 只叫未合格的 separator/background transport code。它不叫白，也不承担健康锚或恢复；动作 1 和 6 均使用 factory-OTP `0x11` packed white frame。

## 2. 64 个固定配方

两个控制器使用完全相同、不镜像的 controller-local `8×8` 网格，每侧 64 格、总计 128 个物理观察，但只有 64 个唯一 recipe：

- 列 `0..7`：active source code `0..7`；
- 行 `0..7`：commented middle code `0..7`；
- 固定 target：active `code0`；
- 第 `r` 行第 `c` 列：`active source(c) -> commented middle(r) -> active target(0)`；
- 每格内部为单一 transport code，没有像素抖动、空间混色、镜像或局部刷新；
- code7 gutter 只用于定位，gutter／边缘不是测量区域。

确定性完整配方由以下命令离线输出：

`python tools/mf1750_runtime_lut_hue_brightness_redpink_v1_pack.py`

## 3. 六个严格动作

| ordinal | palette / profile | frame role |
|---:|---|---|
| 1 | factory-OTP | white health anchor (`0x11`) |
| 2 | runtime-L535 active | source columns `0..7` |
| 3 | runtime-L535 commented | middle rows `0..7` |
| 4 | runtime-L535 active | fixed target `code0` |
| 5 | runtime-L535 active | identical target `code0` repeat |
| 6 | factory-OTP | white recovery (`0x11`) |

动作 4 后采用快速人工门：

- 若 64 格内部没有明确肉眼差异，立即封存主 campaign，不 ARM 动作 5，也不 ARM 动作 6；人工确认 J2／relay OFF 后，改刷本交付的 fresh red/pink containment 并只执行其一次 factory-OTP white。containment 完成后不得回到主 campaign 续跑，直接转下一目标；
- 只有动作 4 明确命中差异，才允许重新作出人工决定并 ARM 动作 5 repeat；host 对 ordinal 5 额外强制 `--confirm-visible-candidate-after-ordinal4`，缺少该确认会在任何设备请求前拒绝。动作 5 复核被接受且仍在同一 boot 后，才允许动作 6 主流程 factory-OTP white recovery。

runner 不会自动派发、重试、恢复或串联。主 cursor 不存在跳转；动作 6 必须看到同 boot 的动作 5 `COMPLETE`。

每次执行只允许一个 ordinal、一个 ARM、一个 EXECUTE 和一个 driver call。host 在发出任何设备请求前先校验本地 BIN/ELF；六个 ordinal 的 host preflight 与固件 ARM、EXECUTE、DISPATCH 三道门都只接受 raw `BUSY=1`。

固件在 fresh `cursor_rpb1` 尚不存在且 READY/ordinal 1 时，把第一次 campaign boot nonce 以 uint64 写入独立键 `boot_rpb1` 并回读。setup、ARM、EXECUTE、DISPATCH 都要求当前 boot 与该持久值 exact 相同；重启、复位、断电或执行 containment 后再回主固件，都会在任何 cursor 写入和 driver 调用前 `FaultLocked`。这堵住了绕过 host 的 direct exact POST resume；六个 action descriptor/action ID 也已因该 device-enforced boot admission 全部轮换。

## 4. 隔离身份

- build tag：`MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_SAME_BOOT_V1_2026-08-27`
- test ID：`EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V1`
- campaign：`EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V1`
- contract ID：`df7ecdc4ef3d443766045e7c242cbb9109cb3f3f6415ad926c70babf7f000278`
- NVS：`rlhbrp_v1/{cursor_rpb1,boot_rpb1}`
- claims：`.test-output/hardware/.mf1750_target_hue_redpink_brightness_v1_claims`
- output：`.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V1`
- routes：`/api/ec5/target-hue-redpink-brightness-v1/{version,manifest,status,report,arm,execute}`
- ARM intent：`ARM_ONE_FIXED_REDPINK_HUE_BRIGHTNESS_CANDIDATE_ACTION`
- EXECUTE intent：`EXECUTE_ARMED_REDPINK_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE`

这些标识、route、NVS 和永久 claim 均不复用 Blue campaign。

专属 containment 也使用全新身份：campaign `EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT`、contract `10867bcecf8da5a4e716bd34547d437c7a426a3b4318a64a1bce3c1963c79020`、NVS `rlhrpcw_v1/used_rpcw1`、route `/api/ec5/target-hue-redpink-brightness-v1/white-containment/*`、action `3f51f507d3d7f739cf66100177223d34aca3b6cfea1d027ca84cf5eb82d94f54`。它单向 exact 绑定上述主 contract，并声明 `main_campaign_resume_after_containment=false`；主 contract 只声明分支目标 campaign，不反向嵌入 containment contract，以避免循环身份依赖。

## 5. 可刷离线产物与验证

- config：`platformio.runtime_lut_hue_brightness_redpink_v1.ini`
- identity：`src/ec5_runtime_lut_hue_brightness_redpink_v1_identity.inc`
- firmware config：`src/ec5_runtime_lut_hue_brightness_redpink_v1_main_config.inc`
- firmware main：`src/ec5_runtime_lut_hue_brightness_redpink_v1_main.cpp`
- isolated driver：`src/ec5_runtime_lut_hue_brightness_redpink_v1_driver.inc`
- driver wrapper：`src/ec5_runtime_lut_hue_brightness_redpink_v1_epd_driver.cpp`
- pack：`tools/mf1750_runtime_lut_hue_brightness_redpink_v1_pack.py`
- one-action runner：`tools/mf1750_runtime_lut_hue_brightness_redpink_v1_once.py`
- focused tests：`tests/test_mf1750_runtime_lut_hue_brightness_redpink_v1.py`
- machine build record：`docs/MF1750_RUNTIME_LUT_HUE_BRIGHTNESS_REDPINK_V1_OFFLINE_BUILD_2026-08-27.json`
- containment config：`platformio.runtime_lut_hue_brightness_redpink_v1_white_containment.ini`
- containment identity／main：`src/ec5_runtime_lut_hue_brightness_redpink_v1_white_containment_{identity.inc,main.cpp}`
- containment pack／runner：`tools/mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_{pack,once}.py`
- containment tests：`tests/test_mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment.py`
- containment machine record：`docs/MF1750_RUNTIME_LUT_HUE_BRIGHTNESS_REDPINK_V1_WHITE_CONTAINMENT_OFFLINE_BUILD_2026-08-27.json`

最终 clean build：

- BIN：`801888 bytes`
- BIN SHA-256：`70952827edbc6685b3acbbb2dc5b554319cccbbef77dd7c5992a6ba3a63c07d8`
- ELF：`13297008 bytes`
- ELF SHA-256：`72011ccb3c4c6f0079f203076d903588a7cfe11fa29a58aec47279c9eb38f8f8`

专属 containment 最终 clean build：

- BIN：`787216 bytes`
- BIN SHA-256：`277ee4168dbc0034889dd620d1dbe1931bac32b3260abe98a695df09d1c3d513`
- ELF：`13214292 bytes`
- ELF SHA-256：`a6ea106b99c3a91e0e3362ea6110b05070e45869ef6d3d8cf76de3a3dec0c9db`

验证结果：两套 clean PlatformIO build 均成功；主专项 `47 passed`，containment 专项 `17 passed`，主＋containment＋target-hue catalog＋Blue 相邻联合回归 `112 passed`；Ruff check／format check与 py_compile 通过。两套 runner 的 `describe` 和 `dry-validate` 均为 `network_requests=0`、`visible_refreshes=0`，dry 均返回 `PASS` 且 exact 校验本地 BIN/ELF。本次只做离线文件、编译与 host 测试；未访问设备网络、串口／COM、继电器或真屏，未刷写、复位、上电或刷新。

## 6. 明日上机顺序（仅操作者在场后）

1. 先确认操作者已经回到现场，J2／屏侧电源保持 OFF；重新运行主与 containment 两套离线 `dry-validate`，逐字核对本文件的四个 BIN/ELF 大小与 SHA-256。
2. 只将冻结的 application BIN 写入 app offset `0x10000`；不写 bootloader、partition table 或 NVS。写后单独执行 flash verify，结果必须与冻结 BIN 一致。
3. J2 仍 OFF，只读获取 version／manifest／status／report：必须命中本批 build/campaign/contract、全新的 `rlhbrp_v1/{cursor_rpb1,boot_rpb1}`、完整 transport/boot-admission action 字段、fresh `next_ordinal=1`、`campaign_boot_matches_current=true`、0 ARM／0 EXECUTE／0 driver。任一差异立即停止，不开 J2。
4. 操作者确认可观察且 raw BUSY 为 1 后才开 J2。逐个执行动作 1 至 4；每项只允许一次 ARM、一次 EXECUTE、一次 driver call，等严格 `COMPLETE` 后停在人工观察门并拍照。动作 1 必须人工确认 factory-OTP clean white；动作 4 逐行比较相同 target 下八个 source-history 内部区域。
5. 动作 4 观察完成后立即分流。若没有明确肉眼差异：封存主 campaign，绝不 ARM 5／6；关闭 J2／relay 并独立确认 OFF，写入专属 containment BIN，先以 J2 OFF 完成四个只读 fresh preflight，再由操作者开 J2，只执行 containment 的一次 ARM＋EXECUTE factory-OTP white；确认 clean white 后再次 OFF，转下一目标，绝不回刷主固件续跑。
6. 只有动作 4 明确命中，才保持同一 boot 并单独决定动作 5；ordinal 5 命令必须显式带 `--confirm-visible-candidate-after-ordinal4`，重新核对 ordinal／action ID 后只执行一次，比较 repeat 是否抹平、保持或改变差异。只有动作 5 同 boot 严格 `COMPLETE` 且复核被接受后，才能执行动作 6 factory-OTP white recovery并人工确认 clean white。
7. 任意重启、复位、断电、boot-binding 差异、BUSY 异常或动作失败都封存主 campaign；不得 direct POST resume、清 NVS、自动串联、retry、fallback 或补刷。最后关闭 J2／继电器并独立确认 OFF，归档每个 action 的结果、照片、boot nonce、action ID、严格 BUSY／FNV／GPIO 证据。
