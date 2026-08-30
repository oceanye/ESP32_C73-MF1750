# MF1750 T3 相机辅助与 W4 白收容日间执行卡

状态：`OFFLINE READY / NOT EXECUTED`
离线冻结时间：`2026-08-31 00:51 +08:00`

## 目标与边界

下一次现场只做两次可见刷新：一次 T3 `AC` profile-following atlas，一次专属 W4
factory-OTP white。48MP 相机用于几何、四副本一致性、三帧稳定性和明显边缘／条纹／残留的
粗筛，不用于绝对颜色、正式色数、灰阶标定或调色板资格。

本卡不授权夜间硬件动作。编制与验证期间保持 J2 `OFF`，没有访问相机、设备网络、COM、
继电器，也没有刷写、复位或刷新屏幕。

## 精确绑定

| 项目 | contract | action | BIN SHA-256 |
|---|---|---|---|
| T3 atlas | `714ddf2e...78c8` | `db009936...6e9e` | `05c00d71...5760` |
| W4 white | `7edf2e19...7d52` | `e621ea9a...c55b` | `9f3ab672...bf7` |

W4 只接受上述 T3 的 campaign/contract/descriptor/action 四元组。两者均为一次性动作，
`retry=0 / recovery=0 / autochain=0`。

相机只允许：

```text
48MP USB Camera
VID_32E4:PID_4801
DirectShow exact-path 双重枚举
MJPG 4000x3000 @ 15 fps
autofocus=0, focus=79
auto exposure=0.25, exposure=-6
auto white balance=0, WB=4600
warmup=8
```

`VID_1BCF:PID_0B15` 双目相机明确排除。OpenCV index 不是身份。fresh-V2 的
`exposure=-3` 档不得混入本轮；白参考、三张 atlas 与末端白图必须完全同档、同机位。

## 明天固定顺序

1. 保持当前 W3 干净白和 J2 `OFF`，用冻结相机档拍 1 张白参考。首次 capture 的
   `mount_id` 冻结到本会话；整屏必须完整、未裁切。
2. J2 `OFF` 下 app-only 写入并独立验证 T3；执行 fresh 4-GET 诊断，必须为
   `0 POST / 0 claim / 0 refresh`。
3. 继电器 ON 后只读确认当前 T3 raw `BUSY=1`。未确认不得 claim/ARM/EXECUTE；
   `BUSY=0` 时保护性 OFF 并停止。
4. 执行唯一 T3 action：恰好 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`。
5. T3 完成后立即继电器 OFF；利用双稳态保留 atlas，在断电状态取得 3 张正式照片。
   为取得 3 张有效帧，最多允许 5 次独立 capture；每次只拍一帧且使用独立 O_EXCL 文件。
6. 深验 1 张白参考、3 张 T3 JPEG/sidecar、相机 exact path、请求与实际设置、尺寸、机位和
   SHA-256。只有四帧原始证据全部封存，才开放 W4；自动分析结果本身不阻塞安全刷白。
7. J2 仍为 `OFF` 时 app-only 写入并验证 W4；fresh 4-GET 诊断后，继电器 ON 并只读确认
   当前 W4 raw `BUSY=1`。
8. 执行唯一 W4 factory-white；完成后继电器 OFF。再拍 1 张末端白图，最多 2 次 capture。
9. 对已封存照片离线分析。正常终态为：W4 干净白保留、继电器 commanded `OFF`；继电器
   回执仍不等于负载侧电气证明。

## 相机粗判

必须重新取得当前照片四角，不能静默复用历史 homography。逻辑画面固定为双侧
`4×8`、合计 64 格；每侧每个 code 有 4 个分散副本。三张 atlas 先按同位置白参考作平场，
再检查：

- 64 格几何完整、两侧各 `4×8`；
- 每个 controller/code 至少 `3/4` 有效副本，至少 `2/3` 有效帧；
- code `2/3/5` controls；
- 三帧中心漂移、组内离散；
- 底边异常、条纹、残留、中心接缝、过曝／欠曝、失焦或几何失败。

固定粗门：组内最大 `ΔE00 <= 8` 为 PASS、`8–12` 为 REVIEW、`>12` 为 FAIL；三帧中心
最大 `ΔE76 <= 3` 为 PASS、`3–6` 为 REVIEW、`>6` 为 FAIL。白参考 `L* < 25` 的位置作
无效样本，不补造数据。

最终只允许：

```text
HUMAN_CAMERA_SCREEN_PASS
HUMAN_CAMERA_SCREEN_REVIEW
HUMAN_CAMERA_SCREEN_FAIL
```

低置信度、光照不稳定、暖色难分或任一自动门不完整，一律 `REVIEW`，需要后续人工判读。
相机不能覆盖操作者观察，也不能产生“已确认新色”“绝对色值”或“合格颜色数量”。

## 失败分支

| 失败点 | 动作 |
|---|---|
| 初始白参考失败 | J2 保持 OFF，白屏保留，停止 |
| T3 诊断或 BUSY 门失败 | 0 mutation；保护性 OFF，停止 |
| T3 action fault | 保护性 OFF；不重试 |
| 5 次内未取得 3 张有效 atlas | 保持 OFF 并保留 atlas；不安装 W4，等待人工决定 |
| 照片已封存但分析为 REVIEW/FAIL | 可按计划执行 W4 安全刷白；分析离线继续 |
| W4 诊断、BUSY 或 action fault | 保护性 OFF；不重试、不自动恢复 |
| 末端白图失败 | 保持 OFF，记录相机失败，请人工确认白屏 |

## 离线产物

- 状态门：`tools/mf1750_raw_p16_crossover_t3_camera_w4_daylight_plan.py`
- 四帧采集包：`tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py`，SHA-256=
  `5608ac7c24fd7fad28d5279cdcafae4bc2fd85ee098d9dd5850d12bf8e0522de`
- 64 格分析器：`tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py`，
  SHA-256=`1a75d63fea7a3d32adb431a8083c58b3d1f0e3ccb16b12fddb8b9c8b78d2a40c`
- 分析器 CLI、输入和判定说明：
  `docs/MF1750_RAW_P16_T3_CAMERA_ASSISTED_OBSERVATION_OFFLINE_READINESS_2026-08-31.md`
- 单元测试：`tests/test_mf1750_raw_p16_crossover_t3_camera_w4_daylight_plan.py`
- 封存计划：
  `.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V2.json`
- 计划文件：`27457 bytes`，SHA-256=
  `d3c0d2e12804c459d03872479da91bfce81ebcff039128f7395ebdbb937ef551`
- 初版 V1 被 V2 替代且保留不覆盖；V2 增加了可变对象隔离、稳定文件 identity 检查、两次
  visible action 各自显式 resume，以及 camera attempt 与 action retry 的严格区分。

后续相机输入生成器、三帧分析器和 capture pack 必须逐项符合本卡；低置信度不能自动升级。

主线程最终联合回归为 `150 passed`；格式、Ruff 和 `py_compile` 均 PASS。所有验证均为离线，
没有因测试运行而打开相机或触发任一硬件动作。
