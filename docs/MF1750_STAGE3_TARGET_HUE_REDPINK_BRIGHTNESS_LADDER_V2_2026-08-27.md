# MF1750 目标色相／明度候选阶梯 successor V2（红／粉线索批）

日期：`2026-08-27`  
离线冻结状态：`OFFLINE BUILD READY / NOT FLASHED BY THIS RECORD / NOT RUN BY THIS RECORD / 0 QUALIFIED LEVELS`

## 1. 为什么必须是 successor V2

V1 的持久化 same-boot 门已按设计把二次 boot 永久锁死。V2 不是 V1 的恢复、清键或续跑；它使用全新的 build/test/campaign/contract/action/descriptor、NVS namespace/key/boot-key、route、host claim 与 output root，从 fresh V2 NVS 开始。V1 的 fault、cursor 或 boot nonce 不能授权或阻断 fresh V2。

V2 仍然是单一 application boot campaign：第一次 V2 application boot 会写入 `boot_rpb2`，任何后续 V2 boot 都必须在 `epdBegin`、ARM、EXECUTE 和 dispatch 前 fail-closed。不得通过 direct exact POST、清 NVS、重刷后续跑或任何 host 绕过来恢复。

## 2. 目标 transport code 与科学载荷

本批继续固定 active-global transport `code0`，依据与 V1 完全相同且没有重新猜测：

- target-hue catalog `94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8` 把 CS2 active `code0` 约束为最可信的直接红 endpoint 候选；
- CS1 同一 transport code 仍只能称为橄榄／黄绿候选，不声明两个控制器颜色等价，也不声明共享红／粉色相；
- factory-OTP atlas 的 `code3` 红／粉证据不能外推到 runtime L535；active `code1`／`code2` 仍是未标定 search seed；
- runtime `code7` 只叫未合格 separator/background transport code，绝不叫白。

两个控制器使用相同、不镜像的 controller-local `8×8` grid：列为 active source `0..7`，行为 commented middle `0..7`，target 固定 active `code0`。每侧 64 recipes，共 128 个物理观察、64 个唯一 recipes；没有空间抖动、像素混色、局部刷新或 recipe 镜像。

V2 的六帧、两个控制器的 DTM、LUT、几何和 transport 与 V1 逐字节相同；只有隔离身份和部署合同轮换。离线可复算：

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_pack.py
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py describe
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py dry-validate
```

## 3. 六个严格动作与 ordinal 4 快速门

| ordinal | profile | frame role | 固定输出文件 |
|---:|---|---|---|
| 1 | factory-OTP | white health anchor (`0x11`) | `action-01-factory-otp-white-anchor.json` |
| 2 | runtime-L535 active | source columns `0..7` | `action-02-source-columns.json` |
| 3 | runtime-L535 commented | middle rows `0..7` | `action-03-middle-rows.json` |
| 4 | runtime-L535 active | fixed target `code0` | `action-04-redpink-64-candidates.json` |
| 5 | runtime-L535 active | identical target `code0` repeat | `action-05-redpink-repeat.json` |
| 6 | factory-OTP | white recovery (`0x11`) | `action-06-factory-otp-white-recovery.json` |

动作 4 是强制人工分流点：

- 如果 64 格内部没有明确肉眼差异，立即封存 main V2；不得 ARM ordinal 5，也不得 ARM ordinal 6。J2／relay OFF 后，用 fresh V2 containment 做一次 factory-OTP white，然后转下一目标。containment 后绝不回 main V2 resume。
- 只有 ordinal 4 明确命中，操作者才可在同一 boot 单独决定 ordinal 5；命令必须额外带 `--confirm-visible-candidate-after-ordinal4`。只有 ordinal 5 同 boot 严格完成且复核被接受，才允许 ordinal 6 主流程白恢复。

runner 不自动 dispatch、串联、retry、fallback、恢复或跳 ordinal。每项仅一个 ARM、一个 EXECUTE、一个 driver call；host 和固件 ARM／EXECUTE／dispatch 均要求 raw `BUSY=1`。

## 4. V2 隔离身份

- variant：`L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2`
- build：`MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_SINGLE_APP_BOOT_FLASH_VERIFY_V2_2026-08-27`
- test：`EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V2`
- campaign：`EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2`
- identity revision：`runtime-lut-target-hue-redpink-brightness-factory-white-single-app-boot-flash-verify-v3`
- contract：`1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c`
- NVS：`rlhbrp_v2/{cursor_rpb2,boot_rpb2}`
- routes：`/api/ec5/target-hue-redpink-brightness-v2/{version,manifest,status,report,arm,execute}`
- claims：`.test-output/hardware/.mf1750_target_hue_redpink_brightness_v2_claims`
- output root：`.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2`
- ARM intent：`ARM_ONE_FIXED_REDPINK_V2_HUE_BRIGHTNESS_CANDIDATE_ACTION`
- EXECUTE intent：`EXECUTE_ARMED_REDPINK_V2_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE`

专属 V2 containment：

- build：`MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT_SOURCE_SINGLE_APP_BOOT_V2_2026-08-27`
- test：`EC5-TARGET-HUE-REDPINK-BRIGHTNESS-V2-WHITE-CONTAINMENT`
- campaign：`EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT`
- identity revision：`target-hue-redpink-brightness-v2-white-containment-source-single-app-boot-v3`
- contract：`73f6bb1db45aa5ec570e854067cb2ad29d6994206a8816e1eadfa7fc763c2c92`
- descriptor／action：`befaffcf0dfe1562a0a4f1d54ecb256ba2a357837598a18ef76318c20079f9cc`／`4c0c5e414242832925d864cd89b64f5592b516c70bb6669683645022b265f87b`
- NVS：`rlhrpcw_v2/used_rpcw2`
- route：`/api/ec5/target-hue-redpink-brightness-v2/white-containment/*`
- claims：`.test-output/hardware/.mf1750_target_hue_redpink_brightness_white_containment_v2_claims`
- output root：`.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2`

containment 单向 exact 绑定 main V2 contract 和 `boot_rpb2`，并固定 `main_campaign_resume_after_containment=false`。它不复用 V1 containment。

## 5. 冻结产物

Main V2 clean build：

- BIN：`.pio/build-runtime-lut-hue-brightness-redpink-v2/ec5_runtime_lut_hue_brightness_redpink_v2/firmware.bin`
- BIN：`801936 bytes`，SHA-256 `e50acc57e0ef98953f1e40695eba17ae03a3df85b25941eacf332bad78c084fe`
- ELF：`.pio/build-runtime-lut-hue-brightness-redpink-v2/ec5_runtime_lut_hue_brightness_redpink_v2/firmware.elf`
- ELF：`13297040 bytes`，SHA-256 `925bbcab8b730d245ca569abd46fa3daa25ba16b4befab2788f35989db5fe8fb`

V2 containment clean build：

- BIN：`.pio/build-runtime-lut-hue-brightness-redpink-v2-white-containment/ec5_runtime_lut_hue_brightness_redpink_v2_white_containment/firmware.bin`
- BIN：`787232 bytes`，SHA-256 `161e7c60f03d85aa4a50d4a9f03de927acdb99f6507c696f57500d95d7aee4ce`
- ELF：`.pio/build-runtime-lut-hue-brightness-redpink-v2-white-containment/ec5_runtime_lut_hue_brightness_redpink_v2_white_containment/firmware.elf`
- ELF：`13214292 bytes`，SHA-256 `3d759a03e42b9f6c4c2d18add6f1683432713353cb434cc3e04d506c5ccdea03`

Single-app-boot helper：`tools/mf1750_app_only_single_boot_flash.py`，`12170 bytes`，SHA-256 `529fbe5bf5a70254aaef5a042923d4699e1c27f1b478ef09c79c8f5fd1a1e451`。本机冻结调用链为 PlatformIO Python `3.11.7` 与 esptool `4.11.0`；esptool shim SHA-256 为 `7e6833367b891629474c7717eb1689178377c1b13be286016ef72ee2c4e269a9`。

## 6. 现场绑定字段（必须填写，禁止猜测）

| 字段 | 冻结值／状态 |
|---|---|
| application offset | `0x10000` |
| serial port | `COM8`（由 root 的现场调用给出；本离线记录未访问） |
| main base URL | `UNBOUND_DO_NOT_GUESS` |
| containment base URL | `UNBOUND_DO_NOT_GUESS` |
| URL contract | `http://` + 单个 private／loopback／link-local literal IPv4；无 hostname、userinfo、query、fragment、proxy 或 redirect |
| main flash evidence | `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/app-only-single-boot-flash.json` |
| main J2-OFF diagnostic | `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/j2-off-diagnostic.json` |
| containment flash evidence | `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/app-only-single-boot-flash.json` |
| containment J2-OFF diagnostic | `.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/j2-off-diagnostic.json` |

## 7. Main V2 上机顺序

以下是现场模板，不是本离线记录已执行的声明。J2 必须先 OFF，并由操作者肉眼／仪表确认。

1. 重新跑两条 main 离线命令并核对冻结 BIN／ELF。确认固定 output root 内的 flash、diagnostic、action 文件均不存在；O_EXCL 会拒绝覆盖。
2. 仅用下列 helper 写 application offset `0x10000`。helper 固定 `write_flash --before default_reset --after no_reset`，然后在零次 application boot 的条件下执行 `verify_flash --before no_reset --after hard_reset`；verify 的 hard reset 是第一次也是唯一一次 application boot。

```powershell
python -B tools/mf1750_app_only_single_boot_flash.py --port COM8 --bin .pio/build-runtime-lut-hue-brightness-redpink-v2/ec5_runtime_lut_hue_brightness_redpink_v2/firmware.bin --expected-sha256 e50acc57e0ef98953f1e40695eba17ae03a3df85b25941eacf332bad78c084fe --output .test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/app-only-single-boot-flash.json --python-exe C:\Users\Ye\.platformio\penv\Scripts\python.exe --esptool-script C:\Users\Ye\.platformio\packages\tool-esptoolpy\esptool.py --confirm-j2-off
```

3. 写入与 verify 之间，以及 verify 后到 J2-OFF diagnose 完成前，禁止任何额外 COM open／reconnect、chip-id、monitor、reset、断电或重新刷写。不得写 bootloader、partition table 或 NVS。
4. 把现场核定的 private literal IPv4 origin 记录到上表，然后只执行正式 diagnose；不得省略 `--confirm-j2-off`，不得改变固定输出名。

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py diagnose-j2-off --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --confirm-j2-off
```

成功证据必须完整包含 `version → manifest → status → report` 四个 GET transcript、`GET=4`、`POST=0`、永久 claim `0`、visible refresh `0`、artifact preflight before network、no proxy／redirect 和 `O_EXCL`。必须看到 fresh READY／ordinal 1、GPIO initialized、fixture valid、`campaign_boot_key_present=true`、`campaign_boot_matches_current=true`、0 ARM／EXECUTE／driver。任一错误立即保持 J2 OFF 并封存。

5. Diagnose PASS 后由操作者开 J2。每次只运行一个固定 ordinal，等待其严格 COMPLETE，人工观察并归档固定输出：

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 1 --confirm-j2-on
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 2 --confirm-j2-on
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 3 --confirm-j2-on
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 4 --confirm-j2-on
```

6. 在 ordinal 4 人工分流。无肉眼差异：不要运行下面两条 main 命令。明确命中时，才可在同一 boot 依次人工批准：

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 5 --confirm-j2-on --confirm-visible-candidate-after-ordinal4
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --ordinal 6 --confirm-j2-on
```

任一 reset、断电、boot mismatch、BUSY 异常、identity／ELF mismatch 或动作失败都永久封存本次 main V2；不得 retry 或 resume。

## 8. 无差异分支的 fresh V2 containment

先关闭 J2／relay 并独立确认 OFF。使用同一 narrow helper 写 containment application；这开始一个全新 containment campaign，不能恢复 main：

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py dry-validate
python -B tools/mf1750_app_only_single_boot_flash.py --port COM8 --bin .pio/build-runtime-lut-hue-brightness-redpink-v2-white-containment/ec5_runtime_lut_hue_brightness_redpink_v2_white_containment/firmware.bin --expected-sha256 161e7c60f03d85aa4a50d4a9f03de927acdb99f6507c696f57500d95d7aee4ce --output .test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/app-only-single-boot-flash.json --python-exe C:\Users\Ye\.platformio\penv\Scripts\python.exe --esptool-script C:\Users\Ye\.platformio\packages\tool-esptoolpy\esptool.py --confirm-j2-off
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py diagnose-j2-off --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --confirm-j2-off
```

Containment diagnose 同样必须是完整四 GET、零 POST／claim／visible、artifact-first、no proxy／redirect、O_EXCL。PASS 后才由操作者开 J2，只执行一次：

```powershell
python -B tools/mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py run --base-url <BOUND_PRIVATE_LITERAL_IPV4_BASE_URL> --confirm-j2-on
```

确认 factory-OTP clean white 后关闭 J2／relay，转下一目标。不要回刷 main V2 续跑。

## 9. 离线验证结果

- Main V2 clean PlatformIO build：PASS；focused `63 passed`。
- V2 containment clean PlatformIO build：PASS；focused `21 passed`。
- Single-app-boot helper：`6 passed`。
- V2 main＋containment＋V1 邻接＋target-hue catalog＋Blue 邻接＋helper 联合回归：`206 passed`。
- Ruff format check／Ruff check／py_compile：PASS。
- 两套 runner 的 `describe` 与 `dry-validate`：PASS，均为 `network_requests=0`、`visible_refreshes=0`，并 exact 绑定本地 BIN／ELF。
- Main 独立只读审计：`PASS / conditional LIVE GO`，只覆盖 single-app-boot 部署、J2-OFF diagnose 与 ordinal 1–4；不自动授权 ordinal 5／6 或 containment。

## 10. 离线证据边界

本 V2 准备过程只创建新文件、clean build、读取本地产物并运行 host 测试；`device network=0`、`COM/serial=0`、`relay=0`、`flash=0`、`reset=0`、`visible refresh=0`。本文档不能替代现场生成的 O_EXCL flash、diagnostic、action 和照片证据，也不声明任何候选已合格。
