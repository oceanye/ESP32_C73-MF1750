# MF1750 自动化真屏会话记录

- 派生时间：`2026-08-28T07:57:03.437+08:00`
- 自动结论：**INCONCLUSIVE**（置信度 `low`）
- 当前门：`CAMERA_REPOSITION_OR_AUTOMATED_RECAPTURE_GATE`
- 进度：`4/6` actions，`4` captures，`4` analyses
- 本报告不依赖人工判断生成；相机局部入镜或低置信度只允许 `INCONCLUSIVE`。
- `human_observation_required=false`；后续视觉门由全屏相机复拍与自动判读闭合。

## 身份与范围

| 字段 | 值 |
|---|---|
| `campaign_id` | `EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2` |
| `test_id` | `EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V2` |
| `contract_id` | `1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c` |
| `build_tag` | `MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_SINGLE_APP_BOOT_FLASH_VERIFY_V2_2026-08-27` |
| `firmware_sha256` | `e50acc57e0ef98953f1e40695eba17ae03a3df85b25941eacf332bad78c084fe` |
| `boot_nonce` | `1ffa520a2537168d` |

## 部署与诊断流程

| 阶段 | outcome | 文件 | SHA-256 |
|---|---|---|---|
| `single_app_boot_flash` | `app_only_write_verify_single_boot_pass` | `app-only-single-boot-flash.json` | `83997e6915c5fd75c2f0d16acb30b40429e331978b7bcb6894a7becac459b468` |
| `j2_off_diagnostic` | `j2_off_diagnostic_pass` | `j2-off-diagnostic.json` | `43b25b3c36625ae22cda2374e969fb8e713232bdc1ae0732b16b820abeb81b5a` |

## 动作总表

| ordinal | role | palette/header | machine | capture | analysis | 自动结论 |
|---:|---|---|---|---|---|---|
| 1 | `FACTORY_OTP_WHITE_HEALTH_ANCHOR` | `FACTORY_OTP/-` | `complete_pass` | `CAPTURED` | `ANALYZED` | **INCONCLUSIVE** |
| 2 | `REDPINK_SOURCE_GRID_ACTIVE` | `L535_RUNTIME/active` | `complete_pass` | `CAPTURED` | `ANALYZED` | **INCONCLUSIVE** |
| 3 | `REDPINK_MIDDLE_GRID_COMMENTED` | `L535_RUNTIME/commented` | `complete_pass` | `CAPTURED` | `ANALYZED` | **INCONCLUSIVE** |
| 4 | `REDPINK_FIXED_TARGET_ACTIVE_CODE0` | `L535_RUNTIME/active` | `complete_pass` | `CAPTURED` | `ANALYZED` | **INCONCLUSIVE** |
| 5 | `REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0` | `L535_RUNTIME/active` | `NOT_EXECUTED` | `MISSING` | `MISSING` | **INCONCLUSIVE** |
| 6 | `FACTORY_OTP_WHITE_RECOVERY` | `FACTORY_OTP/-` | `NOT_EXECUTED` | `MISSING` | `MISSING` | **INCONCLUSIVE** |

## Action 01 — `FACTORY_OTP_WHITE_HEALTH_ANCHOR`

- action ID：`5b49a9dd08873f820e319cc4f25a3f1e7f361ff472240f7b0976fc3d7b629c82`
- descriptor ID：`a15984ff9d49a9f582f66e6b531ece72cceecc1a5da4d05114a29cd8728595d6`
- frame SHA-256：`91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`
- 执行状态：`COMPLETE`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`post_capture_analysis`
- 机器文件：`action-01-factory-otp-white-anchor.json`（`38430` bytes，SHA-256 `1d2c9c9bb507f2c696ce0e104dbc0429a1814d4dbbc14fae54bc56de80a3757c`）
- 网络计数：GET `5` / ARM POST `1` / EXECUTE POST `1`
- driver / visible refresh：`1` / `1`
- driver 时序：PON `181` ms，DRF `22521` ms，POF `141` ms，总计 `35014` ms
- 安全约束：no-retry `True`，no-recovery `True`，no-autochain `True`
- safe-finish：`{"busy_after_5ms": 1, "busy_after_pins_low": 1, "busy_before_pins_low": 1, "final_gpio": {"busy": 1, "cs": 0, "cs2": 0, "rst": 0}}`
- capture sidecar：`camera-action-01.capture.json`（SHA-256 `e3195e6900db2c1757567a3ec182b668db4990248e0a0bec6a7bf820fd0c4513`）
- 覆盖范围：`partial_panel`；full-panel-visible `False`；uncropped `False`
- 相机判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `low`
- 限制：retrospective_timestamp_only_not_immediate_capture_proof; partial_oblique_view_not_full_panel_proof; partial_or_low_confidence_capture_cannot_prove_full_panel
- 照片：`camera-after-action-01-white.jpg`；`1920×1080`；`256034` bytes；SHA-256 `5c5451c831e28a2557bb6e6e2991c871952a244af126fca759f75de4f8476a15`

![Action 01 capture](<../.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/camera-after-action-01-white.jpg>)
- analysis sidecar：`camera-action-01.analysis.json`（SHA-256 `2ca07a1647c97b9592051f9ad1bed2e6f17bccb36f9016fee5706bf3cd1e8cf2`）
- 分析源：`codex_visual_review`；模型/算法：`codex-gpt5-visual-review-v1`
- Post-analysis 判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `low`，candidate `None`
- observations：visible-screen-region-appears-uniform-white-with-no-obvious-colour-blocks-or-lines
- analysis limitations：retrospective-capture-not-synchronized-to-action; panel-bottom-and-full-boundary-not-visible; camera-rgb-not-colour-calibrated; partial_or_low_confidence_analysis_cannot_prove_full_panel

## Action 02 — `REDPINK_SOURCE_GRID_ACTIVE`

- action ID：`571c2123a04183e6b844056c98d8f09f8868bbfabbe4df1ad6e2f0dc2cc6cd0d`
- descriptor ID：`f8be9c4b7a116bba02550a52d7d487129d21191d146b74daed2dd96753e5a997`
- frame SHA-256：`fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853`
- 执行状态：`COMPLETE`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`post_capture_analysis`
- 机器文件：`action-02-source-columns.json`（`40461` bytes，SHA-256 `bd1274c240570a0d6af7fb39c2b64bc6474dae47263f092bac659cf8fa2462bf`）
- 网络计数：GET `5` / ARM POST `1` / EXECUTE POST `1`
- driver / visible refresh：`1` / `1`
- driver 时序：PON `261` ms，DRF `33921` ms，POF `151` ms，总计 `46604` ms
- 安全约束：no-retry `True`，no-recovery `True`，no-autochain `True`
- safe-finish：`{"busy_after_5ms": 1, "busy_after_pins_low": 1, "busy_before_pins_low": 1, "final_gpio": {"busy": 1, "cs": 0, "cs2": 0, "rst": 0}}`
- capture sidecar：`camera-action-02.capture.json`（SHA-256 `3398ba967e61155e53e290bc1f394a96610855815621428beed83a662a786ffe`）
- 覆盖范围：`partial_panel`；full-panel-visible `False`；uncropped `False`
- 相机判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `low`
- 限制：partial_view_not_full_panel_proof; partial_or_low_confidence_capture_cannot_prove_full_panel
- 照片：`camera-action-02.jpg`；`1920×1080`；`373113` bytes；SHA-256 `41328eea7bef3972039057dda59dfe447f4e0dbe2126e8bdec98ebd5b668e2d7`

![Action 02 capture](<../.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/camera-action-02.jpg>)
- analysis sidecar：`camera-action-02.analysis.json`（SHA-256 `9e5ffd42e862a5fa94519decb5ab1407542798658893af16e9526d6317d2f5d6`）
- 分析源：`codex_visual_review`；模型/算法：`codex-gpt5-visual-review-v1`
- Post-analysis 判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `medium`，candidate `None`
- observations：both-grid-groups-and-all-eight-rows-visible; colours-are-broadly-consistent-down-each-source-column; no-missing-cell-or-obvious-grid-line-anomaly-in-visible-roi
- analysis limitations：panel-boundary-not-fully-visible; camera-rgb-not-colour-calibrated; partial_or_low_confidence_analysis_cannot_prove_full_panel

## Action 03 — `REDPINK_MIDDLE_GRID_COMMENTED`

- action ID：`fe222580dd4910e6655ecf7376e8d243d46af724674b20c88adef28d9547eba8`
- descriptor ID：`500e3afbb4121920136a5f8bfe1a7a55efb76373fcd7c226afa4a4c4d2f82fe6`
- frame SHA-256：`5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3`
- 执行状态：`COMPLETE`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`post_capture_analysis`
- 机器文件：`action-03-middle-rows.json`（`40489` bytes，SHA-256 `069dcea883ab5f0794538e79de6290052a8dbfa32ca34f9750b12005770587d4`）
- 网络计数：GET `5` / ARM POST `1` / EXECUTE POST `1`
- driver / visible refresh：`1` / `1`
- driver 时序：PON `260` ms，DRF `29201` ms，POF `151` ms，总计 `41884` ms
- 安全约束：no-retry `True`，no-recovery `True`，no-autochain `True`
- safe-finish：`{"busy_after_5ms": 1, "busy_after_pins_low": 1, "busy_before_pins_low": 1, "final_gpio": {"busy": 1, "cs": 0, "cs2": 0, "rst": 0}}`
- capture sidecar：`camera-action-03.capture.json`（SHA-256 `1f82ea99d3938d8c48519f66f3944dbc93384ce2f7267f643a51b3c0acf05147`）
- 覆盖范围：`partial_panel`；full-panel-visible `False`；uncropped `False`
- 相机判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `low`
- 限制：partial_view_not_full_panel_proof; partial_or_low_confidence_capture_cannot_prove_full_panel
- 照片：`camera-action-03.jpg`；`1920×1080`；`401660` bytes；SHA-256 `6277ec2ddd45b2cbdd3a1cecea84cc7af68f9efd69e0c722cf884383dc302644`

![Action 03 capture](<../.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/camera-action-03.jpg>)
- analysis sidecar：`camera-action-03.analysis.json`（SHA-256 `1512f368445690b4137aaa403e35f07468fcb92ed9c14001b1302c110af18fb9`）
- 分析源：`codex_visual_review`；模型/算法：`codex-gpt5-visual-review-v1`
- Post-analysis 判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `medium`，candidate `None`
- observations：both-eight-by-eight-grid-groups-visible; middle-row-colours-span-horizontally-and-bottom-row-retains-source-columns; no-missing-cell-or-obvious-grid-line-anomaly-in-visible-roi
- analysis limitations：panel-boundary-not-fully-visible; camera-rgb-not-colour-calibrated; partial_or_low_confidence_analysis_cannot_prove_full_panel

## Action 04 — `REDPINK_FIXED_TARGET_ACTIVE_CODE0`

- action ID：`b7498932338a3165b6339acfe8ab675e77eac925487d3da7436bb92b6baff826`
- descriptor ID：`77d9f6a4e2022fc3afb341379f6cdc2e9381706367d8bfbf13edba7758ed4809`
- frame SHA-256：`9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4`
- 执行状态：`COMPLETE`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`post_capture_analysis`
- 机器文件：`action-04-redpink-64-candidates.json`（`40501` bytes，SHA-256 `757810a060881d2c1628e7723afa25da20354bc787381c2befb35ba9e4a8b2b2`）
- 网络计数：GET `5` / ARM POST `1` / EXECUTE POST `1`
- driver / visible refresh：`1` / `1`
- driver 时序：PON `261` ms，DRF `33911` ms，POF `151` ms，总计 `46593` ms
- 安全约束：no-retry `True`，no-recovery `True`，no-autochain `True`
- safe-finish：`{"busy_after_5ms": 1, "busy_after_pins_low": 1, "busy_before_pins_low": 1, "final_gpio": {"busy": 1, "cs": 0, "cs2": 0, "rst": 0}}`
- capture sidecar：`camera-action-04.capture.json`（SHA-256 `c2c65b91ed41c5698fbc835899ba8283942ef74d7f1ac4a68a042708b37bac57`）
- 覆盖范围：`partial_panel`；full-panel-visible `False`；uncropped `False`
- 相机判读：supplied `INCONCLUSIVE` → effective `INCONCLUSIVE`，confidence `low`
- 限制：full-panel-boundary-not-visible; partial_or_low_confidence_capture_cannot_prove_full_panel
- 照片：`camera-action-04.jpg`；`1920×1080`；`517318` bytes；SHA-256 `955e0a28b329d3ed40093441c750f9a3c4677d29d8f570fd3b7a0de4afd0430b`

![Action 04 capture](<../.test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2/camera-action-04.jpg>)
- analysis sidecar：`camera-action-04.analysis.json`（SHA-256 `ee4a832b1f5c68f61b0e05877d0d5849ade3553cf64bc0c8ff2c5cebf0cc0d2f`）
- 分析源：`offline_grid_analyzer_and_codex_review`；模型/算法：`mf1750-redpink-v2-grid-spatial-trend-v1`
- Post-analysis 判读：supplied `FAIL` → effective `INCONCLUSIVE`，confidence `high`，candidate `False`
- observations：all-128-cells-sampled-homography-128-of-128-inliers-rmse-0.572px; cs1-de76-median-2.138-p95-4.610-max-4.825-threshold-6.611-outliers-0; cs2-de76-median-2.352-p95-4.787-max-5.821-threshold-7.654-outliers-0; no-obvious-paired-cell-outlier-beyond-smooth-spatial-trend; grid-analysis-json-sha256-62b11453e727326750e13de0ab3788000650114a3b8ef385f9832cece3aa724e
- analysis limitations：camera-relative-not-absolute-colour; panel-outer-boundary-not-fully-visible; no-repeat-or-persistence-evidence; not-proof-of-new-physical-hue-or-qualified-brightness-level; partial_or_low_confidence_analysis_cannot_prove_full_panel

## Action 05 — `REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0`

- action ID：`190f8ce1746d91ad3a0f0ebc609c48b987990e8536c417c6a1bbbc0e797e030d`
- descriptor ID：`328b6d307450fc85d311ccb9ceeb332f44ce90297c5f2e6fc9f49a61a5c71608`
- frame SHA-256：`9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4`
- 执行状态：`NOT_EXECUTED`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`not_executed`
- 机器证据：尚未执行。

## Action 06 — `FACTORY_OTP_WHITE_RECOVERY`

- action ID：`755e6efe5b621dd4f4165d8d5e440eb55688afb489f36edafb8583b18f5a29e4`
- descriptor ID：`f7f1e36f9c8135501a6f9181ed44faf438beac9312d299e23ee69fc5fc6827c0`
- frame SHA-256：`91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`
- 执行状态：`NOT_EXECUTED`
- 自动结论：**INCONCLUSIVE**
- 结论来源：`not_executed`
- 机器证据：尚未执行。

## 自动结论、限制与下一门

自动结论为 **INCONCLUSIVE**；不声明合格新颜色。

- `campaign_actions_incomplete`
- `one_or_more_captures_cannot_support_full_panel_analysis`
- `one_or_more_post_capture_analyses_are_inconclusive`
- `no_automatic_full_panel_pass_claim`

下一门：`CAMERA_REPOSITION_OR_AUTOMATED_RECAPTURE_GATE`。本报告不会触发刷新、retry、recovery 或 autochain。

## 证据边界与复核

- protocol PASS 不等于视觉 PASS。
- partial-panel 照片不等于全屏证据。
- 未标定相机 RGB 不等于 Lab／绝对颜色测量。
- 本报告为源 action/capture/post-analysis JSON 的纯离线派生视图。

复核命令：

```powershell
python -B tools/mf1750_live_session_report.py validate --campaign-dir <CAMPAIGN_DIR>
```
