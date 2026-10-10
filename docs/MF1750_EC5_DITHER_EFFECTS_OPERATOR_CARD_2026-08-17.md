# MF1750 EC5 像素抖动扩展现场操作卡

适用范围：核心 10 次筛选的第 9/10 次已经 committed PASS，并且第 10 次已人工确认恢复为干净
factory-OTP 白屏后，选择额外执行“渐变→白→综合图→白”四次。此卡不构成 live 授权。

## 当前冻结身份

- staged release：
  `.test-output/offline/MF1750_EC5_DITHER_EFFECTS_EXTENSION_STAGED_RELEASE_20260818_V2/dither-effects-extension-staged-release.json`
- application BIN：同目录 `firmware.bin`，789,088 bytes，SHA-256
  `031c31badfcdde9067e7aeeee4e3fdd811f1955c169f92699d7b1604a59a66b1`
- ELF：同目录 `firmware.elf`，13,251,496 bytes，SHA-256
  `a6a1c488f26414c8ed6debcaea928fbcfc424da656067fb65464acf9172ef93d`
- 固件合同：`5efc7fabcde9d4a96e36eb8f8702b705d9cafc916999a7c5f3f3eb48f6720fe4`
- 新增顺序：
  1. `OTP_DITHER_PAIR_GRADIENTS`
  2. `OTP_WHITE_AFTER_GRADIENTS`
  3. `OTP_DITHER_EFFECTS_CHART`
  4. `OTP_WHITE_AFTER_EFFECTS`

## A. 核心第 10 次结束后的纯离线封装

以下三件输入必须来自刚完成的核心第 10 次，而不是样例、旧白屏或手工 JSON：

- dither-atlas ordinal 2 result；
- 对该 result 的 finalized manual observation，且 `full_clean_white=true`；
- 原 dither-atlas permanent claim registry。

在一个新的、原先不存在的输出路径运行：

```powershell
python tools\mf1750_ec5_dither_effects_extension_campaign.py finalize-real `
  --staged-release .test-output\offline\MF1750_EC5_DITHER_EFFECTS_EXTENSION_STAGED_RELEASE_20260818_V2\dither-effects-extension-staged-release.json `
  --anchor-result <CORE_ACTION_10_RESULT.json> `
  --anchor-observation <CORE_ACTION_10_OBSERVATION.json> `
  --anchor-claim-registry <DITHER_ATLAS_CLAIM_REGISTRY> `
  --output <NEW_DITHER_EFFECTS_REAL_RELEASE.json>
```

随后独立深验：

```powershell
python tools\mf1750_ec5_dither_effects_extension_campaign.py validate-real `
  --release <NEW_DITHER_EFFECTS_REAL_RELEASE.json>
```

只有输出同时为 `execution_eligible=true`、`live_authorized=false`、
`visible_refresh_authorized_by_release=0` 才是正确状态。失败不得手改 JSON；停在核心白屏。

## B. 唯一一次扩展固件切换

1. 人员在场，J2 物理 OFF；屏幕仍为核心第 10 次干净白屏。
2. 重新实测并报告：ESP32 USB、3.3 V CV、精确温度、1.0 A 限流、面板电流、监测和物理切断。
3. 另开 app-only flash 授权，只写上述 exact application BIN；不擦 NVS、bootloader 或分区表。
4. 写后读取相同 application 范围并核对 exact SHA-256。
5. fresh boot 后保持 J2 OFF，不 reset、不再次 flash。
6. 对当时明确选择的候选 URL 仅运行一次 `diagnose-j2-off`；它读取
   `version→manifest→status→report`，不得请求可见刷新。

诊断命令形状：

```powershell
python tools\mf1750_ec5_dither_effects_extension_physical_once.py `
  --release <NEW_DITHER_EFFECTS_REAL_RELEASE.json> diagnose-j2-off `
  --base-url <FRESH_EXPLICITLY_SELECTED_BASE_URL> `
  --evidence <NEW_J2_OFF_DIAGNOSTIC.json> `
  --claim-registry <NEW_EXTENSION_CLAIM_REGISTRY> `
  --confirm-j2-off
```

该 GET 也需要当时的 fresh 只读 authority；不能继承旧 `.7` 选择或旧诊断授权。

## C. 四次可见 action

每次都先运行 `describe --ordinal N` 取得当次 exact authorization，再由操作者逐字确认。runner
先永久 claim，最多发送一次 bodyless `/arm` 和一次 bodyless `/execute`。不得把四次合成一个授权。

| Ordinal | 画面 | 必需前证据 | 完成后的人工重点 | 白屏停点 |
|---:|---|---|---|---|
| 1 | 七组连续双色渐变 | real release + 同 boot J2-OFF diagnostic | 单调性、banding、颗粒、左右一致；20–30 cm 与约 1 m 照片 | 否 |
| 2 | 白恢复 | ordinal 1 result + observation | 全屏干净白、渐变无残留 | 是 |
| 3 | 综合效果图 | ordinal 2 result + clean-white observation | 暖/冷场、灰阶、六码色块、1/2/4/8 px、左右一致 | 否 |
| 4 | 最终白恢复 | ordinal 3 result + observation | 全屏干净白、综合图无残留 | 是/终点 |

Ordinal 1 的 `run` 形状：

```powershell
python tools\mf1750_ec5_dither_effects_extension_physical_once.py `
  --release <NEW_DITHER_EFFECTS_REAL_RELEASE.json> run `
  --base-url <SAME_SELECTED_BASE_URL> --ordinal 1 `
  --authorize <EXACT_ORDINAL_1_AUTHORIZATION> `
  --result <NEW_ORDINAL_1_RESULT.json> `
  --claim-registry <NEW_EXTENSION_CLAIM_REGISTRY> `
  --j2-off-diagnostic <NEW_J2_OFF_DIAGNOSTIC.json> `
  --confirm-no-intervening-visible-refresh --confirm-j2-on `
  --confirm-electrical-normal --temperature-c <CURRENT_TEMPERATURE_C>
```

Ordinal 2–4 用各自 ordinal、authorization 和新 result 路径，将 `--j2-off-diagnostic` 替换为紧邻
前一项的 `--prior-result` 与 `--prior-observation`。四次必须保持同一个 boot nonce、同一固件、无
中间 reset/reflash/refresh。

每次 result PASS 后先生成观察模板并完整观察，再 finalization：

```powershell
python tools\mf1750_ec5_dither_effects_extension_physical_once.py `
  --release <NEW_DITHER_EFFECTS_REAL_RELEASE.json> observation-template --ordinal <N>

python tools\mf1750_ec5_dither_effects_extension_physical_once.py `
  --release <NEW_DITHER_EFFECTS_REAL_RELEASE.json> finalize-observation `
  --result <ORDINAL_N_RESULT.json> --observation <NEW_ORDINAL_N_OBSERVATION.json> `
  --claim-registry <NEW_EXTENSION_CLAIM_REGISTRY> `
  --operator-report <VERBATIM_OBSERVATION> --temperature-c <CURRENT_TEMPERATURE_C> `
  --confirm-reference-preview-checked --confirm-display-matches-reference `
  --confirm-no-unexpected-residual --confirm-electrical-normal `
  --confirm-esp32-no-restart
```

Ordinal 2/4 还必须添加 `--confirm-clean-white`。未完成 observation finalization，不得进入下一项。

## D. 立即停止条件

以下任一发生即物理切断 J2、保留当前屏幕和证据，并永久停止该分支：过流、异常温升、供电异常、
BUSY/driver fault、ESP32 重启、HTTP/claim/result 不确定、画面严重异常或操作者无法确认前态。不得
retry、fallback、自动白恢复、换 URL、reset 后续跑或重放已 claim 的 ordinal。
