# MF1750 RAW-P16 profile-following 人眼盲填卡

用途：观察一次 fresh AC atlas，回答颜色是随 profile 交换，还是留在物理控制器侧。此卡只形成受限的人眼 screening；不做绝对色标定，也不形成 formal colour gate。

## 先封存、后揭盲

观察员在原始表封存前不得查看 CA 颜色记录、预测表或比较结果。当前起点已经是 W3 clean white，J2 为 OFF；后续只需两次 visible refresh：一次 fresh AC atlas，随后一次独立 factory-white。不要再刷前置 white。

atlas action 显示 COMPLETE 且画面稳定后，先写肉眼词，再做一致性与瑕疵检查。不要为了贴近既有名称而改词。

## 固定布局

四行 code 顺序如下；每个 code 在每侧恰有四个副本：

```text
0 1 2 3 4 5 6 7
6 7 0 1 2 3 4 5
5 4 7 6 1 0 3 2
3 2 5 4 7 6 1 0
```

只需填写 16 个词：

```text
左 / CS1 (A): code0 ____ code1 ____ code2 ____ code3 ____
                code4 ____ code5 ____ code6 ____ code7 ____

右 / CS2 (C): code0 ____ code1 ____ code2 ____ code3 ____
                code4 ____ code5 ____ code6 ____ code7 ____
```

逐侧确认：

- 8 个 code 的四副本是否全部同词：`是 / 否`
- 8 个 code 是否全部稳定：`是 / 否`
- 若任一答案为“否”，停止使用紧凑表，改填 64-cell 展开表；不得用一个词覆盖不一致副本。
- controls code 2、3、5：左右是否分别同词：`是 / 否`；另写原话说明。

瑕疵逐项填写 `有 / 无` 并保留原话：整体边缘异常、底边异常、横条纹、竖条纹、残留/鬼影、闪烁/不稳定。底边情况写入 `edge_anomaly` 原话；不要省略。

监督字段逐项实填：观察员/监督员、action COMPLETE 已核对、全程监督、期间无 visible refresh、环境光/视角/画面稳定、四副本已核对、电气状态、ESP32 是否重启、观察时 J2 状态。未知写 `null`/`UNKNOWN`，不得猜测；未知会关闭 full-supervision gate，但不会改写原始词。

## 紧凑 JSON 模板

两个 `code_labels_verbatim` 数组都严格按 code 0..7 填八个肉眼词。若选择逐 code 确认，把总确认改为 `null`，并在对应 `*_by_code` 填八个布尔值。

```json
{
  "schema_version": 1,
  "kind": "mf1750-raw-p16-crossover-profile-following-human-compact-input-v1",
  "stage": "t3-ac-profile-following-successor-v1",
  "observed_at": "2026-08-30T21:00:00+08:00",
  "operator": {
    "operator_id": "FILL",
    "operator_verbatim": "FILL"
  },
  "supervision": {
    "supervisor_id": "FILL",
    "continuous_supervision": true,
    "action_complete_reviewed": true,
    "no_intervening_visible_refresh": true,
    "ambient_light_stable": true,
    "viewing_angle_stable": true,
    "display_stable_through_observation": true,
    "four_replicates_checked": true,
    "electrical_state_normal": true,
    "esp32_restart_observed": false,
    "j2_state_during_observation": "ON",
    "supervision_verbatim": "FILL"
  },
  "controls_verbatim": "FILL",
  "artifacts": {
    "edge_anomaly": {"observed": false, "operator_verbatim": "FILL INCLUDING BOTTOM EDGE"},
    "horizontal_stripe": {"observed": false, "operator_verbatim": "FILL"},
    "vertical_stripe": {"observed": false, "operator_verbatim": "FILL"},
    "residual_or_ghosting": {"observed": false, "operator_verbatim": "FILL"},
    "flicker_or_instability": {"observed": false, "operator_verbatim": "FILL"}
  },
  "controllers": {
    "CS1": {
      "code_labels_verbatim": ["FILL0", "FILL1", "FILL2", "FILL3", "FILL4", "FILL5", "FILL6", "FILL7"],
      "all_four_replicates_consistent": true,
      "four_replicates_consistent_by_code": null,
      "all_labels_stable": true,
      "stable_by_code": null
    },
    "CS2": {
      "code_labels_verbatim": ["FILL0", "FILL1", "FILL2", "FILL3", "FILL4", "FILL5", "FILL6", "FILL7"],
      "all_four_replicates_consistent": true,
      "four_replicates_consistent_by_code": null,
      "all_labels_stable": true,
      "stable_by_code": null
    }
  }
}
```

## 离线封存与比较

紧凑输入由工具按固定四行布局展开成 64 cells；封存文件同时保留原始紧凑输入和展开规则。所有输出均为 O_EXCL，已存在就拒绝覆盖。

```powershell
python tools/mf1750_raw_p16_crossover_profile_following_human_observation.py seal `
  --stage t3-ac-profile-following-successor-v1 `
  --action-result <fresh-T3-action-result.json> `
  --input <compact-ac-input.json> `
  --output <fresh-AC-human-observation.json>

python tools/mf1750_raw_p16_crossover_profile_following_human_observation.py compare `
  --ca-observation .test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/human-observation-ca-v2-v1.json `
  --ac-observation <fresh-AC-human-observation.json> `
  --output <ca-vs-ac-human-screen.json>
```

原始 AC 封存完成后才可揭盲并运行比较。最后执行独立 white；另行原样记录 white 观察并关闭 J2。本卡不授权 ARM、EXECUTE、继电器、刷写或任何硬件访问。
