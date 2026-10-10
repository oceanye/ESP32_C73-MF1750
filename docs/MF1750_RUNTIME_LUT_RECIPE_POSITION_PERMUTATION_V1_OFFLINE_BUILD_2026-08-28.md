# MF1750 Red/Pink recipe 位置置换 P1：离线构建记录

日期：`2026-08-28`  
状态：`OFFLINE BUILD READY / NOT FLASHED / NOT LIVE-AUTHORIZED`

## 1. 目的与边界

本 campaign 用于把已封存 Red/Pink V2 Action 4 的 recipe 效应与固定物理位置、照明和视角
效应分开。它是新的独立 campaign，不重放旧 action，不复用旧 identity、route、NVS、claim
或 output。

冻结 layout/variant：

`L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1`

本固件必须从已经单独验证的全屏干净 factory-OTP 白态开始。白锚不是本 campaign 的第一个
动作，也不会被 runner 自动创建。

## 2. 四个独立动作

每个 ordinal 只允许一次独立 ARM/EXECUTE 和一次可见刷新；没有自动串联、retry、recovery、
skip 或 startup refresh。

| ordinal | 画面 | global header | 固定底层 payload |
|---:|---|---|---|
| 1 | physical column `c` 写 `source=(c+3)%8` | active | CS1 active-535；CS2 commented-535；shared R21 |
| 2 | physical row `r` 写 `middle=7-r` | commented | CS1 active-535；CS2 commented-535；shared R21 |
| 3 | 全部候选格写 fixed target code0 | active | CS1 active-535；CS2 commented-535；shared R21 |
| 4 | factory-OTP full white recovery | factory OTP | 不写 runtime R20/R21 |

global 与 LUT 绑定：

- active global header SHA-256：`48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8`
- commented global header SHA-256：`473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f`
- CS1 active-535 R20 prefix SHA-256：`716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`
- CS2 commented-535 R20 prefix SHA-256：`2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26`
- shared 704-byte R21 SHA-256：`24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`

## 3. P0/P1 映射

离线 pack 与 runner `describe` 同时输出：

- `recipe_map`：64 个唯一 recipe 的 P0 与 P1 坐标；
- `observation_map`：2 个控制器共 128 个观测的 recipe→physical 映射；
- `physical_to_recipe_map`：按相机物理格索引的 128 个 physical→recipe 映射。

双向公式：

- P1 physical→recipe：`source=(column+3)%8`、`middle=7-row`；
- recipe→P1 physical：`column=(source-3)%8`、`row=7-middle`；
- P0 reference：`column=source`、`row=middle`；
- target 固定为 active code0。

这两个变换都是双射，且 64 个 recipe 均不留在原 P0 格位。

## 4. 自动分析输入合同

`analysis_input_contract` 固定要求 128 格 Lab 输入，并分别计算 recipe 对齐相关与物理位置直接
相关。探索门为：

- `recipe correlation >= 0.80`；
- `recipe correlation - physical-position correlation >= 0.25`。

通过结果只允许标为 `RECIPE_LINKED_CANDIDATE_ONLY`，不能在单次置换后认定为合格新颜色。
两侧控制器独立分析，因为本批仍保留 CS1 active-535 / CS2 commented-535 mixed R20，不能据此
主张左右颜色等价。

## 5. 独立状态与输出

- campaign：`EC5_REDPINK_RECIPE_POSITION_PERMUTATION_P1_8X8_ACA_V1`
- NVS namespace：`rppp1`
- cursor：`cursor_rpp1`
- boot binding：`boot_rpp1`
- route prefix：`/api/ec5/redpink-recipe-permutation-v1/`
- claims：`.test-output/hardware/.mf1750_redpink_recipe_position_permutation_v1_claims`
- output：`.test-output/hardware/MF1750_REDPINK_RECIPE_POSITION_PERMUTATION_20260828_V1`
- contract SHA-256：`5c628ccd1755718a6cc7aa0163523122f083bd51085f356ce75c23ea62d4dda2`

固定 action outputs：

1. `action-01-permuted-source-shift3.json`
2. `action-02-permuted-middle-reverse.json`
3. `action-03-permuted-target-code0.json`
4. `action-04-factory-otp-white-recovery.json`

## 6. 构建物

- BIN：`800704 bytes`
- BIN SHA-256：`2a671646d73ee32d3c19184b4d3d2a02d8ab6b374fd11445d88baa66c05a9f65`
- ELF：`13296988 bytes`
- ELF SHA-256：`8fe3017fba40875cb059b0a8b1be3dc4b925fb7a93180f48a4f7374d27adb70f`

纯离线构建命令：

```powershell
C:\Users\Ye\.platformio\penv\Scripts\platformio.exe run `
  -c platformio.runtime_lut_recipe_position_permutation_v1.ini
```

离线检查命令：

```powershell
python tools/mf1750_runtime_lut_recipe_position_permutation_v1_once.py dry-validate
python -m pytest -q tests/test_mf1750_runtime_lut_recipe_position_permutation_v1.py
python -m ruff check tools/mf1750_runtime_lut_recipe_position_permutation_v1_pack.py `
  tools/mf1750_runtime_lut_recipe_position_permutation_v1_once.py `
  tests/test_mf1750_runtime_lut_recipe_position_permutation_v1.py
python -m ruff format --check tools/mf1750_runtime_lut_recipe_position_permutation_v1_pack.py `
  tools/mf1750_runtime_lut_recipe_position_permutation_v1_once.py `
  tests/test_mf1750_runtime_lut_recipe_position_permutation_v1.py
```

ordinal 1 的 runner 还要求显式 `--confirm-external-clean-white`，未确认时会在任何 device
request 前失败关闭。

结果：PlatformIO `SUCCESS`；专项 pytest `18 passed`；Ruff check/format、py_compile、
dry-validate 均通过。

## 7. 本轮硬件声明

本次仅完成文件生成、哈希计算、编译与离线测试。没有访问设备网络、COM/串口、继电器或
J2；没有 flash、reset 或 refresh，也没有创建 live claim/output。
