# MF1750 阶段三批次 1：同 R20 双控制器对照 V1

日期：`2026-08-28`  
状态：`OFFLINE BUILD PASS / LIVE NOT EXECUTED / NO DEVICE I/O IN PREPARATION`

## 1. 目的

本 campaign 只回答一个问题：当 CS1 与 CS2 收到编译绑定的同一套完整 runtime
tuple、同一份 DTM 和相同的刷新流程时，同一个 transport code 是否得到一致的可见结果。

四个 ordinal 固定为：

1. `AA atlas`：active global/PWR/PLL，CS1 与 CS2 均使用 active R20 前 535
   bytes 和 active R21；
2. factory-OTP white；
3. `CC atlas`：commented global/PWR/PLL，CS1 与 CS2 均使用 commented R20 前
   535 bytes 和 commented R21；
4. factory-OTP white。

每个 ordinal 只有一个 driver call 和一次可见刷新。每次必须单独 ARM、单独 EXECUTE、
单独生成不可覆盖 claim/output。固件和 runner 均不提供 retry、recovery、skip 或
autochain。

## 2. 图面与 DTM

每个控制器内使用完全相同的 `2 x 4` code atlas：

- 本地 `x0=40, y0=120`；
- cell `96 x 120`；
- `gap_x=20, gap_y=40`；
- 第一行 `0,1,2,3`，第二行 `4,5,6,7`；
- CS2 不镜像；
- atlas frame SHA-256：
  `79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6`；
- 每侧 DTM SHA-256：
  `f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da`。

## 3. 完整波形绑定

AA tuple：

- tuple ID：`4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820`；
- global header：`48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8`；
- PWR：`f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2`；
- PLL：`dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986`；
- CS1/CS2 R20-535：
  `716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`；
- CS1/CS2 R21-704：
  `24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`。

CC tuple：

- tuple ID：`1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038`；
- global header：`473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f`；
- PWR：`e571c5cf13938b4f4e12b7152ef5ac7d4970ca1d7fd5aa5568b3bf5ab5b208c9`；
- PLL：`084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5`；
- CS1/CS2 R20-535：
  `2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26`；
- CS1/CS2 R21-704：同 AA。

这证明的是固件编译来源与发送分支绑定相同；逻辑分析仪到位前，不能写成“已从总线抓取并
逐字节验证”。

## 4. 身份与产物

- campaign：`EC5_SAME_R20_PARITY_2X4_V1`；
- contract：`718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8`；
- BIN：`801712 bytes`，
  `d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f`；
- ELF：`13299408 bytes`，
  `bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6`；
- NVS：`sr20p_v1 / cursor_srp1 / boot_srp1`；
- API：`/api/ec5/same-r20-parity-v1/*`。

## 5. 前置门

ordinal 1 之前，runner 要求独立 V3 factory-white successor 的不可覆盖
`complete_pass` 输出，且精确校验其 campaign/contract/action/BIN/ELF。自动化主控还必须
另行确认相机白屏门通过；runner 中的 `required_clean_white_visual_gate=true` 不能代替视觉
证据。

刷入新 app 后，在 J2 OFF 下只允许四个 GET diagnostic：

```powershell
python tools/mf1750_runtime_lut_same_r20_parity_v1_once.py diagnose-j2-off `
  --base-url http://192.168.1.7 --confirm-j2-off
```

未通过不得打开 J2，不得创建 action claim。

## 6. 四次单动作执行

每次只运行一条；上一动作协议证据与相机门通过后，主控才显式调用下一条：

```powershell
python tools/mf1750_runtime_lut_same_r20_parity_v1_once.py run --base-url http://192.168.1.7 --ordinal 1 --confirm-j2-on
python tools/mf1750_runtime_lut_same_r20_parity_v1_once.py run --base-url http://192.168.1.7 --ordinal 2 --confirm-j2-on
python tools/mf1750_runtime_lut_same_r20_parity_v1_once.py run --base-url http://192.168.1.7 --ordinal 3 --confirm-j2-on
python tools/mf1750_runtime_lut_same_r20_parity_v1_once.py run --base-url http://192.168.1.7 --ordinal 4 --confirm-j2-on
```

固定输出：

- `action-01-active-active-atlas.json`；
- `action-02-factory-otp-white-after-aa.json`；
- `action-03-commented-commented-atlas.json`；
- `action-04-factory-otp-white-after-cc.json`。

## 7. 判定边界

相机分析对每个 code 做 CS1/CS2 左右配对。AA 或 CC 内若左右仍稳定分裂，则优先检查
控制器、映射、电气或面板半屏差异；不得把差异继续归因于不同 R20。AA、CC 各自左右一致，
且 AA 与 CC 显著不同，才支持“结果跟随 R20 tuple”。本批不认证新颜色，不证明 HOLD，
不证明局部刷新，也不证明 256 色能力。

## 8. 离线验证

- PlatformIO clean build：PASS；
- 专项 pytest：`15 passed`；
- Ruff check/format：PASS；
- `py_compile`：PASS；
- runner `dry-validate`：PASS；
- 本次准备过程：`0` 网络请求、`0` 串口/COM、`0` 继电器、`0` flash/reset、
  `0` visible refresh。
