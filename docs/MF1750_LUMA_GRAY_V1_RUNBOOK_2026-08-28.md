# MF1750 LUMA-GRAY-V1 离线固件与真屏执行手册

状态：`OFFLINE_READY / BUILT / NOT_FLASHED / NOT_RUN_ON_PANEL`

本批次只筛选“相机相对的灰阶/明度候选”，不宣称已获得中性灰，也不宣称已标定任何灰阶。当前资格计数固定为：

- `qualified_gray_levels = 0`
- `qualified_brightness_levels = 0`
- `true_neutral_gray_claimed = false`

## 1. 为什么没有使用 factory-OTP 黑/白逐格源态

现有可审计接口只能证明 factory-OTP 全屏刷新，不能证明同一刷新中可给 64 个格子分别写入 factory-OTP 黑/白源态。因此本固件没有虚构这一能力。

本次采用可严格重现的近似：

- 源锚 A：active-L535 transport code 3；
- 源锚 B：active-L535 transport code 7；
- 二者只是 transport anchor，不能命名为黑或白；
- middle：commented-L535 code 0…7；
- page 1 target：active-L535 code 3；
- page 2 target：active-L535 code 7。

所以搜索空间为 `2 source anchors × 8 middle codes × 2 targets = 32 recipes`。

## 2. 位置平衡布局

每页 16 个 recipe；每个控制器 8×8 共 64 格。每个 recipe 在每个控制器中重复 4 次，并分布于四个象限。CS1、CS2 必须分别评估；禁止把左右控制器当作额外重复或假设同码同色。

没有空间抖动、没有像素混色、没有 PTLW/局刷、没有局部 HOLD。本批次是全屏 packed-frame history screening。

## 3. 固定动作顺序

1. `FACTORY_OTP_WHITE_HEALTH_ANCHOR`
2. `PAGE1_ACTIVE_SOURCE_ANCHORS_3_7`
3. `PAGE1_COMMENTED_MIDDLE_CODES_0_7`
4. `PAGE1_ACTIVE_TARGET_CODE3`（page 1 观察/拍照点）
5. `FACTORY_OTP_WHITE_PAGE_SEPARATOR`
6. `PAGE2_ACTIVE_SOURCE_ANCHORS_3_7`
7. `PAGE2_COMMENTED_MIDDLE_CODES_0_7`
8. `PAGE2_ACTIVE_TARGET_CODE7`（page 2 观察/拍照点）

每个动作都是独立 ARM + EXECUTE；禁止自动串联、重试、跳号或复位后续跑。主固件不含最终白屏动作。动作 8 后，或中途停止/异常后，只能使用独立 fresh-identity containment 固件白屏；containment 后禁止继续主批次。

## 4. 候选与资格门槛

机器合同冻结如下：

- 每个 recipe / controller 必须有 4/4 有效格；
- 同 recipe 位置离散：P95 `ΔE76 ≤ 6.6032`；
- 没有同平面中性色卡时，只能称 `camera-relative gray candidate`；
- 灰候选：相对色卡 neutral-locus 的 `ab distance ≤ 8`，至少 3/4 重复通过，且 `L* ∈ [15,85]`；
- 相邻候选需 `ΔL* ≥ 8`；
- 本批次不自动授予资格。

后续资格批次另需：neutral distance `≤ 5`、target-repeat `ΔE76 ≤ 6.6032`、3 次 fresh run，并在 5/60/600 秒拍照。

## 5. 固件与哈希

主固件环境：`platformio.runtime_lut_luma_gray_v1.ini`

- BIN：`.pio/build-runtime-lut-luma-gray-v1/ec5_runtime_lut_luma_gray_v1/firmware.bin`
- bytes：`801712`
- SHA-256：`fbdbb9e7cca723c8ac2b39992c2b01792cd8bff9888e5d8a10d511602777b9b2`
- ELF bytes：`13296684`
- ELF SHA-256：`2df06b6da6070b12e23550eb9b81d68d7fd9b38c33a28b04a859491cd93ad8cc`
- contract ID：`db671c68cc1141231cbb0baf5f0667e6cdc292095af7b4f3cf9c3d5001d1b260`

独立白屏 containment 环境：`platformio.runtime_lut_luma_gray_v1_white_containment.ini`

- BIN：`.pio/build-runtime-lut-luma-gray-v1-white-containment/ec5_runtime_lut_luma_gray_v1_white_containment/firmware.bin`
- bytes：`786944`
- SHA-256：`9c428924e225ef1dea6b04be7508745190ed5cda0a1bc8d12bf10146addfd6b6`
- ELF bytes：`13214240`
- ELF SHA-256：`fc2024e559d9477b3bb29bb915b9645fac2836ec7516894fc1b1cd771caddeff`
- containment contract ID：`d75573f6413dd861411147047c3784e0560de44241017eafc3cf46c274b99736`

## 6. 离线复核命令

```powershell
python tools/mf1750_runtime_lut_luma_gray_v1_once.py dry-validate
python tools/mf1750_runtime_lut_luma_gray_v1_white_containment_once.py dry-validate
python -m pytest -q tests/test_mf1750_runtime_lut_luma_gray_v1.py
```

重新构建：

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -c platformio.runtime_lut_luma_gray_v1.ini
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -c platformio.runtime_lut_luma_gray_v1_white_containment.ini
```

重新构建后 BIN/ELF 哈希会变化；必须先更新 runner 的绑定并重新跑测试，不能直接沿用本手册哈希。

## 7. 真屏 one-action runner

runner 不刷机、不复位、不控制继电器，只消费一个已刷入固件的动作：

```powershell
python tools/mf1750_runtime_lut_luma_gray_v1_once.py run `
  --base-url http://192.168.1.7 `
  --ordinal 1 `
  --confirm-j2-on `
  --output .test-output/hardware/MF1750_LUMA_GRAY_V1/action-01.json
```

其后严格按 2…8，每次使用新的 `--output`。动作 4 和 8 是正式相机采集点；动作 1、5 是 factory-OTP 白锚/分隔。

最终白屏必须切换到独立 containment 固件，再使用：

```powershell
python tools/mf1750_runtime_lut_luma_gray_v1_white_containment_once.py describe
```

正式执行 containment 前仍需对 fresh 固件身份、fresh NVS claim、J2 状态和当前屏幕状态进行单独确认；不得把主批次的 claim/cursor 当作 containment 授权。
