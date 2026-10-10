# N2P RC2G 固定执行合同 V2

本合同把冻结的 N2P 自然照片四算法 campaign 接到受监督真屏执行路径，但不改写原始离线 manifest。原始 manifest 仍保持 `hardware_ready=false`；新增的 V2 supplement 只补齐 runner、P0 claim、同 cell primer 绑定、视觉评分和相机观察能力。离线 describe 也始终返回 `hardware_ready=false`，只有现场逐项确认并提交某一 action 的精确授权后，runner 才会消费 claim 并联网。

冻结身份：

- 原始 manifest canonical SHA-256：`976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b`
- 原始 manifest whole-file SHA-256：`d7d55f62f6e2392d42dd8d65ea5cd5d7c0c5179b4cd51b9109666b420a21d687`
- P0 campaign canonical SHA-256：`f23476c4c887057877e3f3f6c9315813bb761f6da57996b9eea538584a545cdb`
- V2 supplement canonical SHA-256：`29cdb6ccb75d320d3b1e1fa6ea544f88196b16ca38d1f34ec84343afdc787099`
- V2 supplement whole-file SHA-256：`f1d22bc22a0487bb0cd31b6be7d0c80ccb8f3ae2a86b60c88a8a11ec312865af`
- 视觉评分合同 SHA-256：`7e2aa7e7ac9f85271e2b18101546f5a82b35966d21e93f0037449ef3762076a9`
- 相机/人工观察合同 SHA-256：`6e274ff0b3eb2ae35706e43e516b8a765eaaa280b062cecb6ddf06952f29901c`
- 四 cell 离线 analyzer/ranking 合同 SHA-256：`3638e26f80c8e0a9da81760c3ca3d177d7a43591a813f030446100ec87fb7a86`

## 八个唯一动作

CLI 的 `--action` 只能选择：

1. `q1-map-primer`
2. `q1-target`
3. `q2-map-primer`
4. `q2-target`
5. `q3-map-primer`
6. `q3-target`
7. `q4-map-primer`
8. `q4-target`

CLI 不提供 candidate、frame、frame hash、manifest hash、prior/target job ID 或 operation ID override。每个 cell 是独立 session：ESP32 fresh boot/job0 → 本 cell MAP primer/job1-op1 → 本 cell target/job2-op2。普通 target 阶段不要求再次断开 J2；它要求 MAP 已人工判定忠实、ESP32 自 primer 后未重启，而且实时设备仍精确保留该 primer 的 job1/op1 证据。

## 执行顺序

先做 describe；它可以在缺 profile 或缺 primer result 时运行，只会列 blocker，不创建授权、claim 或网络请求：

```powershell
python tools/g1_s1_rc2g_n2_photo_campaign_once.py `
  --action q1-map-primer `
  --describe-only `
  --limit-profile C:\path\reviewed-limit-profile.json `
  --evaluated-at 2026-08-08T12:00:00+08:00
```

现场 live 参数还需结果目录、ESP32 URL、起始温度、精确 action 授权串和所有物理确认。授权串不由离线 describe 发放；describe 只给出它应匹配的 SHA-256。live 开始时，runner 在第一条网络请求之前原子创建 P0 全局 claim：

`.test-output/hardware/.visible_refresh_fixed_action_claims_v1/<action_identity_sha256>.json`

claim 一旦存在，动作永久消费。claim 后任意失败均为 `UNKNOWN_DO_NOT_RETRY`；最多一条 `POST /api/frame`，没有第二次 POST、自动 retry 或 recovery。协议成功只生成 `N2P-ACTION-EVIDENCE.json`，仍需人工观察 finalizer 才会生成 `P0-ACTION-RESULT.json`：

```powershell
python tools/g1_s1_rc2g_n2_photo_campaign_once.py `
  --finalize-observation `
  --result-dir C:\path\action-result `
  --observation-file C:\path\operator-observation.json
```

## 评分和电气分离

MAP primer 逐项判断方向、标签、中缝、六色、残影和参考画面一致性。target 对以下六项各打 1–5 分：细节、色调、渐变、纹理、伪影、源图忠实度。PASS 要求每项至少 3 分、总分至少 21（均值至少 3.5），同时几何和无旧画面残留通过。

电气记录独立于视觉分数：3.3 V、CV、电流、温度、无异味/异响/热点/压降、ESP32 未重启、物理切断可用均需单独确认。电气正常不能提高视觉分；电气失败会使 action 总体 FAIL，但不会篡改原视觉分数。

观察时间必须是带时区 RFC3339，不能早于协议完成时间，也不能比 finalizer 当前时间超前 15 分钟以上。post-refresh 温度必须不超过 reviewed profile 上限。

相机对单 action 判定是可选的。若声明拍照，finalizer 会拒绝 leaf/祖先 symlink 或 Windows reparse point，读取真实本地图片，核对字节 SHA-256、解码格式和尺寸，并复制为 `N2P-CAMERA-CAPTURE.bin`。单张或缺失照片都不能建立 Q1–Q4 相机可比性；只有四个 target 都有同一相机、固定曝光/白平衡/焦点、固定机位和灯光下的已验证照片时，才可进行相机横向比较。人工真屏评分仍是 action verdict 的依据。

## 现场仍需填写/提供

- 经审核并 canonical-seal 的 limit profile：必须精确匹配冻结 panel/build、包含全部八个 action allowlist、最新 usage evidence、有效期、温度、间隔和次数上限。
- 本次起始温度，以及观察后的温度。
- 当前 3.3 V、CV、电流、温度和物理切断能力确认。
- primer：ESP32 fresh boot/job0 确认；完成后 MAP 六项人工判断。
- target：同 cell canonical PASS primer result 路径、MAP 忠实度确认、ESP32 未重启确认。
- observer ID、带时区观察时间、观察距离、稳定灯光、六项评分；如拍照，再填固定相机 ID、图片路径和 SHA-256。
- 每个 action 单独、明确、一次性的授权确认。不要预先生成或批量复用授权。

## 四 cell 离线汇总与 N3 分支输入

八个 action 都完成 finalization 后，使用固定的八个目录参数运行：

```powershell
python tools/g1_s1_rc2g_n2_photo_campaign_analyzer.py `
  --q1-map-primer-dir C:\results\q1-map-primer `
  --q1-target-dir C:\results\q1-target `
  --q2-map-primer-dir C:\results\q2-map-primer `
  --q2-target-dir C:\results\q2-target `
  --q3-map-primer-dir C:\results\q3-map-primer `
  --q3-target-dir C:\results\q3-target `
  --q4-map-primer-dir C:\results\q4-map-primer `
  --q4-target-dir C:\results\q4-target `
  --output C:\results\N2P-FOUR-CELL-ANALYSIS.json
```

analyzer 会重新验证八条 result/evidence/observation/finalization/profile/claim 链，按六项整数总分降序。最高总分相同即明确输出 tie，`selected_winner=null`，不使用维度顺序或 cell 编号暗中破同分。只有四个 primer MAP PASS、四个 target 及视觉/电气/温度门均 PASS、且最高总分唯一时，才输出带独立 `winner_identity_sha256` 的 winner。

这个 winner 的严格含义仅是 `N3_branch_selection_only`：范围是这一次冻结 N2P campaign、每算法一个候选、每 target 一次人工观察。它不是算法资格认证，不支持总体/群体推断，也不证明某算法普遍优于其他算法。相机可比性独立报告，不影响基于人工评分的分支选择。

专项测试：

```powershell
python -m pytest tests/test_g1_s1_rc2g_n2_photo_campaign_once.py -q
python -m pytest tests/test_g1_s1_rc2g_n2_photo_campaign_analyzer.py -q
python -m pytest tests/test_repo_contract.py -q
```
