# MF1750 阶段三 R20/PERMUTATION/HOLD 离线上机就绪报告

日期：`2026-08-28`  
结论：`LIVE PREPARED / NOT LIVE EXECUTED`  
本轮硬件动作：`0`（未访问设备网络、COM、继电器，未 flash/reset/refresh）

## 1. 下一次现场入口

下一步不是刷白，而是 **G-1 零刷新相机锚定**。保留当前屏上 Red/Pink V2 Action 4
双 8x8 网格和 J2 OFF；把整块面板完整收入固定相机画面，锁定焦点、曝光、白平衡后，先封存
P0 照片与 128 格 homography。G-1 完成后才进入 G0 白恢复。

已知最后安全状态：继电器/J2 为 OFF；屏幕凭双稳态保留 Action 4 网格；由于本轮没有现场读取，
`electrical_state_proven=false`。不得把屏上图像当作供电状态证明。

## 2. 固件冻结身份

| 组件 | contract | BIN bytes / SHA-256 | ELF bytes / SHA-256 |
|---|---|---|---|
| G0 V3 factory white successor | `1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227` | `789200` / `3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb` | `13215844` / `2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797` |
| Batch1 same-R20 parity | `718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8` | `801712` / `d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f` | `13299408` / `bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6` |
| Batch2 recipe permutation | `5c628ccd1755718a6cc7aa0163523122f083bd51085f356ce75c23ea62d4dda2` | `800704` / `2a671646d73ee32d3c19184b4d3d2a02d8ab6b374fd11445d88baa66c05a9f65` | `13296988` / `8fe3017fba40875cb059b0a8b1be3dc4b925fb7a93180f48a4f7374d27adb70f` |
| Batch3 true-R20 partial HOLD | `38698de14b6a2a7a96e072d4de025cb0708ae167b81c348f6c4337dc3654eb63` | `816736` / `458fff47291319e9ec4cf5ceec2ef855551a82792d765055400bceb2c9d6a89f` | `13371716` / `8aaefd61977fea24e17c3b716efbfbf7b93a546eed386887c713ceeb43085eb8` |

构建产物位于各自隔离的 `.pio/build-runtime-lut-*` 目录。三套新固件均执行过 clean build，
产物大小和 SHA-256 与冻结文档完全一致。

Batch3 四个 descriptor SHA-256：

1. `4d317d9f0a96a85c8ba30fb52c3661d47fa7b7de3dcc7ef35fccd7dbd869e8a5`
2. `07e0cdff9718da18f7dbfa084ce41b7af7b0b7a0c9591ca57453b962984f055e`
3. `000f0991160242f035fee116b37342597b79f38d41cd2011e50cab40ce94aa14`
4. `b86d3418fe0edda32b960b67eb56439ee7a0c392c40349eb0a9d960ab4365c20`

## 3. 已完成的证据链

### G-1 与相机

- `tools/mf1750_g1_locked_full_panel_p0_geometry_anchor.py`
- `tools/mf1750_camera_capture_evidence.py`
- `tools/mf1750_camera_video_capture_evidence.py`
- `tools/mf1750_factory_white_repeat_noise_report.py`

G-1 工具 SHA-256：
`98cc0113b02b036bdf57fdfbf523f7d4124bf6be51fb7f86d47c1f98691b314b`。

G-1 深度验证全屏无裁切、camera tuple/mount、AF/AE/AWB 请求与实际回读、Action 4 照片、
homography、128 cell/64 recipe 映射，并以 O_EXCL canonical JSON 落盘。

### Batch1

- runner/pack：`tools/mf1750_runtime_lut_same_r20_parity_v1_once.py`、
  `tools/mf1750_runtime_lut_same_r20_parity_v1_pack.py`
- atlas 分析：`tools/mf1750_same_r20_atlas_photo_analyzer.py`
- AA/CC 比较：`tools/mf1750_same_r20_aa_cc_paired_comparison.py`
- 聚合证据：`tools/mf1750_same_r20_parity_evidence_bundle.py`
- Batch3 所需的 Batch1 evidence requirements ID：
  `51ded712517377821322a83eb1264afd7a69c08678c9a69a2c3b7f6d697ae547`

### Batch2

- runner/pack：`tools/mf1750_runtime_lut_recipe_position_permutation_v1_once.py`、
  `tools/mf1750_runtime_lut_recipe_position_permutation_v1_pack.py`
- 图像分析/比较：`tools/mf1750_redpink_permuted_grid_photo_analyzer.py`、
  `tools/mf1750_redpink_recipe_permutation_comparison.py`
- 聚合证据：`tools/mf1750_recipe_position_permutation_evidence_bundle.py`
- Batch3 前置校验：`tools/mf1750_recipe_position_permutation_batch3_prerequisite.py`

Batch2 聚合工具会同时绑定 G-1、P0、P1、四个 action、四张 action 照片、终态 60-patch white、
相机签名、mount、repeat-noise 和 geometry，不允许用人工颜色描述替代缺失证据。

### Batch3

- runner/pack：`tools/mf1750_runtime_lut_true_r20_partial_hold_v1_once.py`、
  `tools/mf1750_runtime_lut_true_r20_partial_hold_v1_pack.py`
- 静态门：`tools/mf1750_true_r20_hold_photo_gate.py`
- 视频门：`tools/mf1750_true_r20_hold_video_gate.py`
- 聚合证据：`tools/mf1750_true_r20_partial_hold_evidence_bundle.py`

Batch3 runner 在第一次网络或 claim 之前强制读取并深度验证 Batch1 与 Batch2 sealed evidence，
并把 Batch2 身份写入 action result。视频 sidecar 记录时长、预卷、帧数、相机实际设置和文件哈希。

## 4. 自动化边界

实现的是“证据驱动的逐动作执行”，不是无人值守 autochain：

- 每个 action 必须显式选择 ordinal；
- J2 OFF 下执行 app-only flash、独立 verify、fresh 四 GET diagnostic；
- 只有前一 action 的 protocol 和 camera gate 都通过，才允许显式释放下一 action；
- output 使用不可覆盖创建，禁止 retry、fallback、recovery 和覆写；
- 相机可独立完成颜色/边缘筛查，不再需要人肉眼判色；
- 电流、温度、异响/异味/发热和物理急停仍需现场安全保障。

## 5. 离线验证记录

- 相关 28 个 test files：`317 passed in 43.93s`；
- 18 个新增/修改 Python 文件：Ruff check PASS；
- Ruff format check PASS；
- py_compile PASS；
- three once-runner dry-validate PASS；
- G-1 专项：`7 passed`；
- clean firmware rebuild：三个新环境 PASS；冻结 V2 回归重建亦保持原 BIN/ELF SHA-256；
- 本轮验证未访问网络、COM、继电器或真屏。

## 6. 现场执行清单

1. 保持 J2 OFF 和当前 Action 4 图面；固定相机并完成 G-1；
2. 确认 3.3 V、1.0 A 限流、25 °C 附近、监测与物理切断就绪；
3. 执行 G0 V3，并在同一白动作拍至少三张噪声样本；
4. 按 `B1-1..4` 执行并 seal Batch1；
5. 按 `B2-1..4` 执行并 seal Batch2；
6. 只有 Batch1/2 prerequisite PASS 后，按 `B3-1..4` 执行并 seal Batch3；
7. 任一失败立即 J2 OFF，停止 campaign；恢复必须另开独立 containment，不能消费计划内下一动作。

完整语义、门限和停止条件见
`docs/MF1750_STAGE3_TRUE_R20_PARITY_PERMUTATION_HOLD_PLAN_2026-08-28.md`。
