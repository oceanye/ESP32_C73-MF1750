# N4 V3 真屏执行证据与离线分析交接（2026-08-08）

## 结论

N4 V3 的执行合同、单次 runner 证据链和 2×2 离线分析器已经接通。分析器不接受一份可在
离线环境随手构造的 `PASS` result 作为真屏证据；每格必须同时提供本格 MAP 和 target 的完整
finalized runner bundle，并通过共享 validator 深验后，才能生成 cell observation。

分析器本身没有 HTTP、串口/GPIO、claim 写入、授权生成、retry、recovery 或可见刷新路径。
它验证的是 runner 记录链及其内部一致性，不独立证明照片、仪表或人工判断的物理真实性；因此
完整四格仍固定为 `NOT_QUALIFIED`，不能形成硬件资格或因果结论。

## 冻结身份

- N4 V3 shared execution contract canonical / whole-file SHA-256：
  `fc91f32ede1a9fbe073279e07e20fc7271bf715aae3c2ef953ed45e53874f2f0` /
  `d088f72159baa0b18e57bef9c0a2d052b285aa713a5dc4a966843417303f88e0`
- N4 V3 analysis contract canonical / whole-file SHA-256：
  `b370748008844dc5ece026ed44b4dda124da8f0f6c62caed70656bc118e4dae8` /
  `d0d467348e7d60cc7f9ccbcf2eb1f58b027e5551a12e7f13c023d29e91ad98cb`
- 历史 V3 source P0 campaign canonical / whole-file SHA-256：
  `bc436f52fd561f669bac3d67dc45c55f8daaf886867fc79399351d2004ef96ab` /
  `7a1a2fe807912f410e382079ec5d02866d59466157c06b3bebb4f2b6d53aca28`
- N4 execution P0 campaign canonical / whole-file SHA-256：
  `458d3cd4ba2137f5993a34c491a0465fe0d32ef05d65888a063163bdb8416b4f` /
  `28f6b0fae4918486242b5b0c5f8d5846bf1de9c2a8195346d5df3aca22cf4f70`
- V3 source manifest canonical / file SHA-256：
  `3f4852af1151d5c56db1d7c540f3c131ae6c05de1dce8db625864b2900d0e6d7` /
  `17a820d84cb24fe0950a9653d6f6831104e0d872f7167c47f262c18fad559bfb`
- V3 proof canonical / file SHA-256：
  `9566f7198b5fa2ed26b3cc386a9faa23a8a99ff7bace604e164eb7b159b87be5` /
  `3b1a41fc2b772adf12286a7ae41745ef074a50b401e377597041fc38081115ef`

`frozen_contract_bytes()` 会重建并验证共享 execution contract，核对历史/执行 P0、八个 action、
四个 session、frame、strict preview、电源语义、证据合同，并执行 canonical JSON 往返和
whole-file hash 校验。

## J2 电源语义的最终裁决

历史 `g1_s1_root_cause_2x2_v3.py` 编译出的四个 source session 均为
`final_power_off_required=true`。该字段是早期保守的 session 收尾约束，不是本 2×2 设计的
科学必要条件。历史合同保持不改，执行时使用单独冻结的 supplement：

- manifest、proof、四张 frame、preview 和八个 action identity 完全不变；
- 只重建四个 session envelope，并设 `final_power_off_required=false`；
- 每格开始仍必须是 ESP32/controller fresh boot；
- 每格必须先刷本格 MAP primer，再连续执行 target；
- 同格 MAP→target 之间禁止 ESP32 reboot、panel power cycle、J2 断开或其他可见刷新；
- nominal cell 之间 J2 可以持续接通，无需逐格断电；
- 整轮完成、异常，或刷机/改配置前必须断开 J2；runner 不控制物理 J2。

因此晚间 nominal 四格可以连续进行，不再把无科学必要的逐格断电加入人工步骤。

## 四格与固定 action

| 顺序 | Cell | 因素 A：空间频率 | 因素 B：左右负载 | MAP action | Target action |
|---|---|---|---|---|---|
| 1 | low-balanced | low | balanced | `7f1841c72a6e544f2828cd1ae4565296162a0f21b179965a6e5e913cd2113485` | `761e7bdb89974d4d8be3fe866e7b85bc9d1a36a219d85c75a9ba7144a032e4e4` |
| 2 | low-unbalanced | low | unbalanced | `0ae3e936cd7a692fa0eaa916ca315f0b41f2f14247bab5cc2b4dd14693949998` | `6574c0df52aa340e60a282ee36890afd76aaa6cfd1ebf1b47467d3b8ce6e92ec` |
| 3 | high-balanced | high | balanced | `e9f6f834f92cfd52c583cb4f1f82293d35a41cc132f17ea73ec1fb42ded711c4` | `7e73464258ee2da1eac834c43f3bbbc9cfc6179f480f9f625495528a226d125b` |
| 4 | high-unbalanced | high | unbalanced | `65557023127297794dd7e9fd6882d08d702343f4db78fc47f19efd141a5cefad` | `644a2ffd624e9482a8162c7e0d25039fb046b3deec39c66965bfbaa5f0499e05` |

既有 N1 low-balanced 结果不能替代 N4 第一格；每格必须使用上表自己的 MAP 和 target。

## 每个 action 的深验证证据链

Analyzer 接收的 bundle 包含并重算以下 canonical whole-file SHA：

- workspace-global consumed claim；
- `ATTEMPT-LOCK.json`；
- `REVIEWED-LIMIT-PROFILE.json`；
- `N4-V3-ACTION-EVIDENCE.json`；
- `N4-V3-ACTION-OBSERVATION.json`；
- `N4-V3-ACTION-FINALIZATION.json`；
- `P0-ACTION-RESULT.json`。

共享 validator 复核 action/cell/phase/frame/preview、claim-before-network 确认、授权确认 hash、
reviewed profile、最多一次 `POST /api/frame`、请求 frame hash、MAP 与 target 原始 protocol/
diagnostic/GPIO 证据、视觉/电气/温度/连续性派生 verdict、finalization，以及
`result.evidence_manifest_sha256 → finalization`。Target 的 claim、protocol、finalization 必须同时
绑定本格 MAP 的 exact result SHA 和 finalization SHA；跨格 prior、同步篡改、缺文件和 replay
均 fail closed。

生产接口为：

```python
build_n4_v3_cell_observation(
    analysis_contract,
    cell_id="low-balanced",
    map_bundle=validated_runner_map_bundle,
    target_bundle=validated_runner_target_bundle,
)
```

单独的 result mapping、另填一套 visual/electrical 数字，均不是该接口的合法输入。Analyzer 从
两份已验证 action observation 唯一派生本格视觉、电气、温度和连续性记录，并把两份 raw bundle
嵌入 cell observation，保证以后验证 report 时可以再次深验，不只信任一个布尔标志。

## 标准化观察与跨格可比性

支持 `standardized-manual` 和 `fixed-camera`。固定相机方式必须有 capture SHA、固定曝光 profile、
可解码格式和尺寸；人工方式不得冒充相机证据。四格计算前还要求：

- observation kind、视觉 protocol、observer/camera asset、固定曝光和 ROI 一致；
- meter、clock、温度 sensor、calibration 和 U95 合同一致；
- 每格视觉证据、MAP/target 温度证据以及相机 capture（如有）各自唯一；
- 同格 MAP/target 的观察设备一致，但各 action 的 capture 和温度证据不得复用。

任一方法漂移或 evidence replay 都在 2×2 算术前拒绝。

## 预注册 2×2 输出

每个视觉或电气 outcome 分别输出以下字段：

- `cell_values`；
- `spatial_frequency_main_effect_high_minus_low`；
- `half_load_main_effect_unbalanced_minus_balanced`；
- `interaction_effect_coded_level_means`；
- `interaction_difference_of_differences`；
- `interaction_scaling_check`。

视觉 outcomes 为 fidelity、ghosting、artifact severity；电气 outcomes 为 MAP/target 峰值电流、
MAP/target job duration、session max temperature 和 target voltage droop。两组保持分离，
`visual_electrical_joint_conclusion=null`。

每格只有 `n=1`、总计 `n=4`。即使八个可见 action 的证据链全部通过，也只输出
`EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY`，并固定：

- `qualification_state=NOT_QUALIFIED`；
- P95/P99 为 `null`；
- 不允许总体推断、因果归因、视觉/电气/硬件资格结论。

任一 target result/视觉/电气/温度/连续性异常均转为 `UNKNOWN_DO_NOT_RETRY`，停止剩余 cell，
不计算 2×2，也不自动 retry/recovery。无异常时必须恰好收齐四格；缺格不插值。

## 文件与验证

- 共享 execution contract 与 bundle validator：`tools/g1_s1_n4_v3_execution_contract.py`
- 单次生产 runner/finalizer：`tools/g1_s1_rc2g_n4_v3_once.py`
- 分析合同、cell observation 和 2×2 analyzer：`tools/g1_s1_n4_v3_analyzer.py`
- 共用 test-only 深链 fixture：`tests/n4_v3_bundle_fixture.py`
- analyzer 专项：`tests/test_g1_s1_n4_v3_analyzer.py`

验证命令：

```powershell
python -m unittest tests.test_g1_s1_n4_v3_analyzer -v
python -m ruff check tools/g1_s1_n4_v3_analyzer.py tests/test_g1_s1_n4_v3_analyzer.py
python -m compileall -q tools/g1_s1_n4_v3_analyzer.py tests/test_g1_s1_n4_v3_analyzer.py
python tools/check_repo_contract.py
```

Analyzer 专项当前为 **13/13 PASS**。测试 bundle 由 mock HTTP 和 test-only operator observation
生成，不代表真实真屏已完成，也不代表供应商极限或硬件资格。
