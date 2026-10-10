# N4 V3 RC2G 固定执行交接（2026-08-08）

## 当前结论

N4 V3 的白天代码准备已完成：四个 2×2 cell 各有独立的 `MAP-primer job1/op1 → target job2/op2`，共 8 个且仅 8 个可选动作。执行器、观察 finalizer、深证据 verifier 和离线 analyzer 已连通。当前结论仍是“软件就绪、真屏未执行”，不代表硬件、画质、算法或因果关系已经合格。

本交接不创建现场授权、不创建真实 claim、不访问 ESP32，也不执行可见刷新。

## 冻结身份

- V3 manifest canonical SHA-256：`3f4852af1151d5c56db1d7c540f3c131ae6c05de1dce8db625864b2900d0e6d7`
- V3 manifest whole-file SHA-256：`17a820d84cb24fe0950a9653d6f6831104e0d872f7167c47f262c18fad559bfb`
- V3 proof canonical SHA-256：`9566f7198b5fa2ed26b3cc386a9faa23a8a99ff7bace604e164eb7b159b87be5`
- V3 proof whole-file SHA-256：`3b1a41fc2b772adf12286a7ae41745ef074a50b401e377597041fc38081115ef`
- 历史 source P0 canonical SHA-256：`bc436f52fd561f669bac3d67dc45c55f8daaf886867fc79399351d2004ef96ab`
- 现场 execution P0 canonical SHA-256：`458d3cd4ba2137f5993a34c491a0465fe0d32ef05d65888a063163bdb8416b4f`
- shared execution contract canonical SHA-256：`fc91f32ede1a9fbe073279e07e20fc7271bf715aae3c2ef953ed45e53874f2f0`
- shared execution contract whole-file SHA-256：`d088f72159baa0b18e57bef9c0a2d052b285aa713a5dc4a966843417303f88e0`
- analyzer contract canonical SHA-256：`b370748008844dc5ece026ed44b4dda124da8f0f6c62caed70656bc118e4dae8`
- analyzer contract whole-file SHA-256：`d0d467348e7d60cc7f9ccbcf2eb1f58b027e5551a12e7f13c023d29e91ad98cb`

历史 source P0 的四个 session 都写有 `final_power_off_required=true`。新的 execution P0 仅将这四个 session 字段改为 `false` 并重封 session/campaign integrity；8 个 action、frame、DTM、job、prior、manifest 和 proof 身份均未改变。

## 8 个唯一 CLI action

| 顺序 | CLI action | action identity SHA-256 |
|---:|---|---|
| 1 | `low-balanced-map-primer` | `7f1841c72a6e544f2828cd1ae4565296162a0f21b179965a6e5e913cd2113485` |
| 2 | `low-balanced-target` | `761e7bdb89974d4d8be3fe866e7b85bc9d1a36a219d85c75a9ba7144a032e4e4` |
| 3 | `low-unbalanced-map-primer` | `0ae3e936cd7a692fa0eaa916ca315f0b41f2f14247bab5cc2b4dd14693949998` |
| 4 | `low-unbalanced-target` | `6574c0df52aa340e60a282ee36890afd76aaa6cfd1ebf1b47467d3b8ce6e92ec` |
| 5 | `high-balanced-map-primer` | `e9f6f834f92cfd52c583cb4f1f82293d35a41cc132f17ea73ec1fb42ded711c4` |
| 6 | `high-balanced-target` | `7e73464258ee2da1eac834c43f3bbbc9cfc6179f480f9f625495528a226d125b` |
| 7 | `high-unbalanced-map-primer` | `65557023127297794dd7e9fd6882d08d702343f4db78fc47f19efd141a5cefad` |
| 8 | `high-unbalanced-target` | `644a2ffd624e9482a8162c7e0d25039fb046b3deec39c66965bfbaa5f0499e05` |

CLI 没有 frame、frame hash、manifest、proof、job ID、operation ID 或自定义 action override。

## 真屏核对图

总览：

- `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/contact-sheet.png`

四个 target 的逐张严格预览：

- `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/low-balanced.strict-final.png`
- `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/low-unbalanced.strict-final.png`
- `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/high-balanced.strict-final.png`
- `.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/high-unbalanced.strict-final.png`

MAP-primer 是既有冻结 `map-orient-v1`，frame SHA-256 为 `1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36`。

## 供电与连续性规则

- Runner 从不控制 J2、物理开关、ESP32 EN、刷机或配置。
- 每个 cell 的 MAP-primer 前必须确认 controller fresh boot；可用 ESP32 EN 建立 fresh job0，J2 可保持接通。
- 同一个 cell 的 MAP 到 target 之间禁止 ESP32 重启、面板电源循环、J2 断开和任何其他可见刷新。
- 普通 target 前不要求、也不应为了“保险”断开 J2。
- cell 之间 J2 可以保持接通；进入下一 cell 前仍须建立新的 controller fresh job0。
- 仅在整场 campaign 结束、任何异常、刷写固件或改变配置前切断驱动板电源。

## 每个 cell 的现场顺序

1. 用 `--describe-only` 核对 action/frame/preview/profile/prior blocker；该模式永远不声称硬件 ready，也不创建 claim 或网络 I/O。
2. 确认 3.3 V、CV、空闲电流、温度、接线与物理切断能力正常。
3. 建立 controller fresh job0；只执行该 cell 的 MAP-primer。精确授权字符串应在现场从 `required_authorization_confirmation(action_key)` 取得，本交接不预先生成授权。
4. 对 MAP 做全屏、方向、中心拼缝、六色和无旧图残留观察；记录独立的电气和温度数据，再 finalization。只有 canonical PASS MAP bundle 才可进入 target。
5. J2 保持现状，不按 EN、不重启、不插拔、不做其他刷新；只执行同 cell target。
6. 对照该 cell 的 `strict-final.png`，记录 fidelity、ghosting、artifact severity、方向、拼缝；另行记录电气、温度与 MAP→target 连续性，再 finalization。
7. Target finalizer 同时生成 `N4-V3-CELL-OBSERVATION.json`。Analyzer 只接受内嵌 MAP/target claim、lock、profile、protocol、action observation、finalization 和 P0 result 的两条深链，不接受游离手填结果。
8. 任何异常立即停止剩余 cell，物理断电，保留 `UNKNOWN_DO_NOT_RETRY` 或 FAIL 证据；不得自动重试或恢复。

## 每个 action 的固定文件

- `ATTEMPT-LOCK.json`
- `REVIEWED-LIMIT-PROFILE.json`
- `N4-V3-ACTION-EVIDENCE.json`
- `N4-V3-ACTION-OBSERVATION.json`
- `N4-V3-ACTION-FINALIZATION.json`
- `P0-ACTION-RESULT.json`
- 可选 `N4-V3-CAMERA-CAPTURE.bin`
- Target 额外生成 `N4-V3-CELL-OBSERVATION.json`

P0 result 的 `evidence_manifest_sha256` 必须等于 finalization 的 canonical whole-file SHA-256；target 还必须同时绑定同 cell MAP result 与 MAP finalization 的 whole-file SHA-256。Workspace-global claim 在首个网络请求前提交，每 action 最多一次 `POST /api/frame`；claim 后失败一律 `UNKNOWN_DO_NOT_RETRY`。

## 入口与复验

- Shared contract：`tools/g1_s1_n4_v3_execution_contract.py`
- Once runner/finalizer：`tools/g1_s1_rc2g_n4_v3_once.py`
- Offline analyzer：`tools/g1_s1_n4_v3_analyzer.py`
- Test-only deep bundle fixture：`tests/n4_v3_bundle_fixture.py`
- Focused tests：`tests/test_g1_s1_rc2g_n4_v3_once.py`、`tests/test_g1_s1_n4_v3_analyzer.py`

建议现场前再次执行：

```powershell
python -m unittest tests.test_g1_s1_rc2g_n4_v3_once tests.test_g1_s1_n4_v3_analyzer tests.test_repo_contract -v
python -m ruff check tools/g1_s1_n4_v3_execution_contract.py tools/g1_s1_rc2g_n4_v3_once.py tools/g1_s1_n4_v3_analyzer.py tests/n4_v3_bundle_fixture.py tests/test_g1_s1_rc2g_n4_v3_once.py tests/test_g1_s1_n4_v3_analyzer.py
```

2026-08-08 白天最终离线复验结果：上述两组 N4 测试连同 repository contract 共
`49/49 PASS`（211.940 s）；ruff 与 `python tools/check_repo_contract.py` 均通过。
复验未访问串口、设备网络或真屏，未创建真实 claim，也未生成现场授权。
