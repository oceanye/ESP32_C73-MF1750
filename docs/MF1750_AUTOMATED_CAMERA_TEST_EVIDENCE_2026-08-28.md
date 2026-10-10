# MF1750 自动相机闭环测试与证据记录

日期：`2026-08-28`

## 目标

后续真屏测试不再依赖操作者肉眼裁决。每个可见动作仍保持“一次调用只执行一个 ordinal”，动作结束后由固定 USB 相机拍照，程序完成粗筛或格间差异分析，并把原始机器结果、照片、分析结论和证据边界汇总为可检查的 Markdown 报告。

自动化不会改变已经冻结的固件、action ID、claim、顺序门或单动作 runner，也不会增加隐式重试、恢复、刷写、复位、继电器切换或自动串联。

相机身份已冻结为 `48MP USB Camera / VID_32E4:PID_4801`。`USB Camera /
VID_1BCF:PID_0B15` 是另一台双目设备，明确排除。正式 live capture 在打开前以
FFmpeg DirectShow exact alternative name 唯一解析实际目标，再由同次枚举导出 OpenCV
index；调用方文本与 index 不能选择设备，任何缺失、重复、不一致或枚举漂移均
fail-closed。详细边界见 `README camera.md`。

## 每个动作必须留下的证据

1. 固件、campaign、contract、boot nonce、ordinal、action ID 与 descriptor ID。
2. 原始 action JSON、claim JSON 及各自的文件 SHA-256；保留 action 内置 canonical integrity。
3. ARM／EXECUTE／GET 数量、visible refresh 数量、driver call 数量、PON／DRF／POF／total 时长和安全收尾 GPIO。
4. 一张动作后的原始 JPEG，以及配套不可覆盖的 capture sidecar：相机身份、DirectShow/MJPG、请求与实际分辨率、曝光／白平衡／焦点、预热帧、采集时间、图像尺寸、质量指标和 SHA-256。
5. 自动视觉结论、置信度、实际覆盖范围和限制。协议 PASS、可见区域 PASS 与全屏视觉 PASS 必须分开记录。
6. 从上述不可变证据派生的 session index 和 `SESSION_REPORT.md`。派生报告可原子重建，但不得修改 action、claim、照片或 capture sidecar。

## 自动视觉裁决规则

- 相机明确看见重复、对应位置一致的候选差异时，可记录 `CANDIDATE_DETECTED`，并给出位置和数值依据。
- 完整覆盖整屏且图像质量合格时，才允许记录 `NO_VISIBLE_DIFFERENCE_FULL_PANEL`。
- 机位只覆盖部分屏幕、过曝、失焦、遮挡或几何配准不足时，必须记录 `INCONCLUSIVE`；不得把“未在可见区域发现”写成“64 个 recipe 均无差异”。
- `INCONCLUSIVE` 只会暂停后续动作，不会要求操作者肉眼判断，也不会自动重试已经消费的 action。
- 当前机位为斜视、部分入镜，只适合白屏及明显大色块粗判；若用于 8×8 明度矩阵，没有强阳性候选时预计会得到 `INCONCLUSIVE`。
- **配方离群筛选与色族观察是两个不同结论。** 完整看见并成功配准两侧 8×8 网格时，可在相机相对色空间内判断是否存在超出平滑空间趋势、且左右对应的独立离群配方；该判断不等于全屏视觉 PASS，也不等于绝对颜色标定。
- `NO_OBVIOUS_PAIRED_CELL_OUTLIER_BEYOND_SMOOTH_SPATIAL_TREND` 只表示本次没有可单独释放到动作级 repeat 的孤立配方。它不能改写为“没有扩展颜色”：Action 4 照片中已经观察到橄榄绿、粉、玫红和赭橙等扩展外观色族；断电复拍又证明这些外观与结构继续保留，但仍没有独立刷新 repeat、位置置换或绝对色标，因此不得计为合格新颜色。

## 当前红／粉 V2 会话

身份：

- contract：`1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c`
- boot nonce：`1ffa520a2537168d`
- firmware BIN：`801936 bytes / e50acc57e0ef98953f1e40695eba17ae03a3df85b25941eacf332bad78c084fe`
- device：`http://192.168.1.11`

当前进度：

| ordinal | 角色 | 机器状态 | 照片状态 | 自动视觉状态 |
|---:|---|---|---|---|
| 1 | factory-OTP white anchor | `complete_pass` | 1920×1080 旧照片已绑定；`retrospective_unproven` | 入镜区域呈白；不能证明同步或整屏 |
| 2 | active source columns | `complete_pass` | 同步 1920×1080 照片与 sidecar 已固定 | 两组 8 行网格清晰；列内基本一致；全屏仍不确定 |
| 3 | commented middle rows | `complete_pass` | 同步 1920×1080 照片与 sidecar 已固定 | 两组 8×8 可见；中间行展开、底行保留；未见缺格或明显异常线 |
| 4 | active code0 64 candidates | `complete_pass` | 同步照片与 grid analysis 已固定；另有一张断电保持复拍及 retrospective sidecar | 128/128 格可解释；无孤立离群 recipe；两次照片均保留控制器专属橄榄／黄绿与红／粉色族及结构化明度层级 |
| 5 | candidate repeat | 按无候选分支禁止执行 | 无 | Action 4 没有独立离群配方；不得调用或重试 |
| 6 | main 内 factory-OTP white recovery | 按无候选分支禁止执行 | 无 | 不得把独立 fresh containment 冒充 main ordinal 6 |

Action 1 的照片是在结果落盘约 106 秒后另行拍摄，因此只能标记为 `retrospective_unproven`，不能伪装成同步拍照证据。Action 2 起已使用正式同步拍照流程。所有相机 capture sidecar 在拍照前只能预置 `INCONCLUSIVE/low/none`；照片落盘后再由独立、绑定照片 SHA-256 的 AI／算法分析记录给出观察与候选结论，避免事后改写原始采集证据。

### Action 4 自动分流结果

- action JSON：`action-04-redpink-64-candidates.json`，`40501 bytes`，SHA-256 `757810a060881d2c1628e7723afa25da20354bc787381c2befb35ba9e4a8b2b2`。
- 照片：`camera-action-04.jpg`，`1920×1080`，`517318 bytes`，SHA-256 `955e0a28b329d3ed40093441c750f9a3c4677d29d8f570fd3b7a0de4afd0430b`；capture sidecar SHA-256 `c2c65b91ed41c5698fbc835899ba8283942ef74d7f1ac4a68a042708b37bac57`。
- grid analysis：`camera-action-04.grid-analysis.json`，`327079 bytes`，文件 SHA-256 `62b11453e727326750e13de0ab3788000650114a3b8ef385f9832cece3aa724e`，canonical integrity `48ad08093c4ccb4fd9109ce4bd808a8a4146504348e30271dd9dd1524f9547aa`。
- 几何证据为 128/128 格 contour support、128/128 homography inliers、RMSE `0.572 px`。CS1 的相机相对 ΔE76 median／p95／max／threshold 为 `2.138/4.610/4.825/6.611`，CS2 为 `2.352/4.787/5.821/7.654`；两侧单格明显离群数和配对 recipe 明显离群数均为 `0`。
- 因此本次只作出“没有超出平滑空间趋势的独立左右配对 recipe”结论，主序列按冻结快速门封存，ordinal 5、6 不执行。照片中橄榄绿、粉、玫红和赭橙等色族仍作为真实观察保留；断电复拍提供了持久性线索，但在没有独立刷新 repeat、空间置换和绝对色标前，`qualified new colour = 0`。
- 外围面板没有完整入镜，所以 full-panel 结论继续是 `INCONCLUSIVE`；这与上述相机相对网格候选筛选结论不冲突，也不要求操作者补做肉眼判断。

### Action 4 断电保持复拍与明度结构

- 在 COM14/channel 1 commanded OFF 后，未触发任何新刷新，直接采集
  `camera-action-04-poweroff-repeat-01.jpg`（`1920×1080`，SHA-256
  `86b0038a280307ab43e3d27f1585f63e4059005154204993fa9ea145a4ee045d`）。
- 权威时序绑定为
  `camera-action-04-poweroff-repeat-01.retrospective.capture.json`（`3738 bytes`，SHA-256
  `0470a5f69a14132b4ac1ee82cfa4002903264a790791ab1314d1b9d4a0906d50`，
  `capture_binding=retrospective_unproven`）。最初采集命令生成的
  `camera-action-04-poweroff-repeat-01.capture.json` 错标为 `live_synchronized`；该不可变文件只作为
  错误记录保留，不用于时序证明。
- 复拍 grid analysis 为 `camera-action-04-poweroff-repeat-01.grid-analysis.json`（SHA-256
  `95241372c620d2874898290e50f9eae518d29fc7b7265abf487892dd68797756`），再次取得
  `128/128` contour support 与 homography inliers。CS1 的相机相对色相约 `50–70°`、L* 范围
  `55.7–72.5`；CS2 色相约 `340–356°`、L* 范围 `31.8–51.0`。
- 原图／复拍 L* 曲线相关性为 CS1 row=`0.998217`、column=`0.645152`，CS2
  row=`0.870076`、column=`0.896651`。这证明结构不是一次刷新闪烁噪声；但两次照片使用同一
  物理格位，仍属于 `STRUCTURED_EFFECT_POSITION_CONFOUNDED`。下一轮必须把 recipe 置换到不同
  位置，只有差异跟随 recipe 而非位置时，才能升级为可重复明度候选。
- 两图的正式色族摘要为 `camera-action-04.colour-family-summary.json`（`53347 bytes`，文件
  SHA-256 `deebdb7779e684f79a2a586544885f50073e50496c2b4de1c17730de6dfc6073`，canonical integrity
  `c0bed599658e3447ebc8386d32c2d1abe972e0150ddfa046c130c4911b9b3455`）。确定性 Lab 聚类把 CS1
  记为 `yellow-olive-direction` 的 2 个探索外观带（silhouette `0.577534`），CS2 记为
  `red-pink-direction` 的 3 个探索外观带（`0.600880`）。这些带只用于规划置换复核，
  `cluster count is not colour count`；正式状态仍为 `UNPROVEN_REPEAT_POSITION_CONFOUNDED`，
  `qualified_new_colour=false`、`qualified_brightness_level=false`。

## Fresh 白屏收容状态

- Action 4 后 COM14/channel 1 已 commanded OFF 并独立 query 为 OFF；J2 保持 OFF。继电器没有负载侧电压反馈，故 `electrical_state_proven=false`。屏幕在断电后按双稳态保留 Action 4 网格，不能写成已恢复白屏。
- fresh containment application 已完成 app-only 写入与独立 verify：`app-only-single-boot-flash.json` 为 `7038 bytes`，SHA-256 `bfbd6799ca0bc16d81f67ee55addc137244452fb2d732364465b80e804572023`，outcome=`app_only_write_verify_single_boot_pass`。写入的 BIN 为 `787232 bytes`，SHA-256 `161e7c60f03d85aa4a50d4a9f03de927acdb99f6507c696f57500d95d7aee4ce`。
- 随后的 J2-OFF diagnostic 在任何 mutation 前 fail-closed：`j2-off-diagnostic.json` 为 `16291 bytes`，SHA-256 `67f906ce5821b3227ee5b03f74cb4ea81e96138e7eb3a333654972b768c916a7`，outcome=`j2_off_diagnostic_failed_no_claim`，错误为 `ContainmentConsumedError: version classification differs`。
- 不一致是 host pack 常量 `FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD` 与 firmware 返回值 `FACTORY_OTP_WHITE_REDPINK_BRIGHTNESS_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD` 不同；四个 GET 已读取到 fresh READY／next ordinal 1、boot nonce `d3816c27d6a7af52` 和正确 running ELF SHA。
- 本次 diagnostic 严格为 `GET=4 / POST=0 / permanent claim=0 / visible refresh=0`，factory-OTP white action 尚未执行。该 O_EXCL 失败记录不得覆盖或重试；在离线修复并形成新的、可审计的收容执行路径前，J2 必须保持 OFF，主 V2 也不得恢复。

## 报告检查原则

最终检查时，以 action／claim／capture sidecar／照片的不可变文件与 SHA-256 为权威；Markdown 是便于阅读的派生视图。若 Markdown 与原始 JSON 冲突，应以通过完整性校验的原始证据为准，并重新生成 Markdown。

## 2026-08-28 日终自动化收口

- G-1 全屏几何锚、Hub2 relay 窄 rebind、同机位锁定参数拍摄、照片 SHA 绑定、
  离线视觉裁决、一次性 action 和 finally-OFF 收尾已组成可运行的闭环。
- Same-R20 4×8 V2 六帧正式照片在相同 `4000×3000 / focus 79 / exposure -6 /
  WB 4600` 下完成。曝光质量和几何门 PASS，但同 code 四位置离散门 FAIL，因此最终为
  `POSITION_DEPENDENT_INCONCLUSIVE`；不认定 controller parity/mismatch，不认定新的稳定颜色。
- 日内照片中观察到的橄榄绿、粉、玫红、赭橙等仍是有价值的“扩展外观色族”线索，
  但未通过 recipe 位置解混、repeat 和绝对色标，故 `qualified new colour = 0`。
- 最终独立 factory-OTP white 完整通过；同机位 post-white 分析 PASS，旧 atlas、色块、
  条纹、中心接缝和边缘残留均未见。COM14/channel 1 已 exact-bound query OFF，
  `electrical_state_proven=false` 仍保留。
- 权威日终包为
  `.test-output/hardware/MF1750_SAME_R20_PARITY_4X8_20260828_V2/evidence-bundle-v2.json`，
  bundle ID=`417e70cc38fa7c656ebeedaf371d2204cd6eea5eb72c77ceb7664ecf5ce5f71c`。它深度绑定前置白、
  atlas、后置白和三份独立 OFF receipt 的 identity/rebind 及时序。完整结论见
  `docs/MF1750_STAGE3_SAME_R20_PARITY_4X8_V2_LIVE_RECORD_2026-08-28.md`。
