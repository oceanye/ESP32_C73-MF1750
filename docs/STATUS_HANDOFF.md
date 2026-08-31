# ESP32_C73 当前状态交接

> **唯一当前状态入口。** 历史 handoff、TODO 和 runbook 保留证据与过程，但凡状态冲突，
> 先以本页为准并回查原始 evidence。以后每完成一个软件里程碑、一次真屏 action、一次人工
> 裁决或一次安全收尾，都必须在宣告完成前同步更新本页。

最后更新：`2026-08-31 09:15 +08:00`

## 2026-08-31 09:15 T3/W4 两阶段取证 V3 离线就绪，等待下次有人值守（最高优先级）

- 操作者已离场并明确今天后续只做离线代码。本节从该离场点起严格保持 0 camera/relay/COM/
  ESP32-network/flash/reset/visible-refresh；不改写 05:59 relay query 与 06:01 setup-only 相机的
  更早历史事实。当前只继承：relay commanded `OFF`、`electrical_state_proven=false`、屏幕按
  双稳态保留 W3 clean white；正式 W3 camera attempt=0，T3/W4 仍未安装、claim 或执行。
- T3 capture pack 已消除“照片存在前预填本帧四角”的循环：`acquire` 在开相机前 O_EXCL claim，
  不接收 corners，只封存一张 JPEG/sidecar/action snapshot；随后纯离线 `admit` 在解析这张
  exact JPEG 的 corners 前先 O_EXCL admission claim，再写 terminal ACCEPTED/REJECTED。成功
  acquisition 未 terminal admit 前禁止下一次 acquire；错误角点、gate failure 与旧 `capture`
  路径均 fail-closed，不得改角重审、自动 retry/fallback/autochain。setup-only 独立最多 2 次，
  `formal_evidence=false`。
- W4 post-white wrapper 采用同一两阶段结构，并补齐 canonical claim/acquisition/admission/
  evidence 路径和哈希深重放；两类重签篡改负测均被拒绝。只有
  `full_screen_white_gate.passed=true` 且 classification=`PASS` 才 ACCEPTED/seal；REVIEW/FAIL
  保留分类但 terminal REJECTED，同一 attempt 不可重 admit，只能在最多 2 次总预算内显式拍
  attempt 2。若两次均未 PASS，只能由操作者明确确认 clean white，人工 fallback 不生成 seal。
- 相机权限边界已收紧：camera-only 只赚取 64 格几何、四副本、三帧稳定性与底边／条纹／残留
  粗筛；没有真实 T3 human seed 时最高 `HUMAN_CAMERA_SCREEN_REVIEW`，profile-vs-side=
  `NOT_EARNED`。要回答主问题，必须把当前 T3 左右各 code0..7 共 16 个真实人眼词与四副本稳定
  确认封存，再与 exact T2/CA human reference 比较；没有 seed 仍可先执行独立 W4 安全收容。
- T3/W4 app-only helper 的 reset 语义已如实写入计划：write 使用
  `--before default_reset --after no_reset`，verify 使用 `--before no_reset --after hard_reset`，
  应用只启动一次；额外／人工 reset=0。两次 visible action 的 raw `BUSY=1` 门仍位于各自冻结
  runner 的 exact 4 GET 之后、任何 claim/ARM/POST 之前，retry/recovery/autochain=0。
- current V3 已 O_EXCL 封存：
  `.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V3.json`，
  bytes/SHA-256=`36734 / 4c3c1d2ff056a28506fd335ee9576167e7b627d679b2c03d4c854a2b9f95a212`，
  canonical integrity=`88510a3090d62dd2950fca0c0768d28001c5e5bf957ac97ec01525f52b04bed7`，
  14 steps。V1/V2 作为历史保留；V2 已不能通过当前 deterministic rebuild，不得继续作为 current。
- 最终工具 SHA-256：T3 capture pack=
  `4b8de02588c4fbf4f73914129118f019080d6231347b97831fe9df9f3f91d6ca`；W4 wrapper=
  `c2c9c5c8cb11867d04d98d51849a080163a379354fdb3c510fb11a8cc2af9024`；daylight plan source=
  `c3582a7f7d9db5a409c62460fe0f417a990e6af471f24e9252c058c3d944245b`。联合离线回归=
  `174 passed / 696.69 s`；格式化后 plan `9 passed / 90.75 s`、W4 `17 passed / 244.27 s`；
  format check、Ruff、py_compile PASS，全部使用 fake/synthetic evidence。
- 当前执行卡为
  `docs/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_RUNBOOK_2026-08-31.md`，详细计划为
  `docs/MF1750_RAW_P16_CROSSOVER_T3_W4_NEXT_ATTENDED_TEST_PLAN_2026-08-31.md`。下次只需操作者在场、
  相机完整对准且光照可用；先 setup-only，不消耗正式名额。正常预计 15–25 分钟；仅在取景失败、
  camera REVIEW、主问题需要 16 个词或末端白异常时暂停人工判断。

## 2026-08-31 06:03 日间 48MP 几何预检停止：面板未入镜、固定档严重欠曝（最高优先级）

- 操作者授权天亮后试拍。本轮先完成 exact-bound relay 只读查询；COM14/channel1 返回
  commanded `OFF`、`off_gate_passed=true`、`electrical_state_proven=false`。receipt 位于
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_CAMERA_DAYLIGHT_V1/relay-pre-white-query-20260831-055924388.json`。
- DirectShow 枚举唯一命中 `48MP USB Camera / VID_32E4:PID_4801`；双目
  `USB Camera / VID_1BCF:PID_0B15` 与 OBS Virtual Camera 均未被选用。
- 因正式 capture pack 必须在开相机前先取得角点并永久 claim，而仓库尚无适用于当前画面的
  本帧角点采集入口，先取得一张明确标为 setup-only、非核心证据的 exact-camera 预检帧。
  JPEG=`camera-t3-daylight-setup-white-20260831-060144.jpg`，bytes/SHA-256=
  `366555 / 2ac5fce31b4929efefaa3cd4951e0c52b690366d775e856d653f10a030966ad4`；
  sidecar 深验 PASS，bytes/SHA-256=
  `5352 / caf5cab00fcd4a79f5009279d023fb20e02bea7bdf53d6ff2f972218a84517b8`。
- 预检图没有包含面板，镜头朝向桌椅区域；固定正式档 `4000×3000 / exposure=-6 / focus79 /
  WB4600` 下 mean RGB=`[5.464085, 7.100415, 10.886859]`，RGB 低端裁切比例分别约
  `77.18% / 66.35% / 51.76%`，不具备角点、白参考或颜色粗筛资格。
- 因此正式 W3 capture attempt **尚未消耗**；capture-contract/claims/results 均不存在。
  T3/W4 action 也均未安装、未 claim、未执行。J2 保持 commanded OFF，屏幕仍保留 W3 白，
  本轮没有 flash、reset、ESP32 网络请求或 display refresh。
- 下一步只需操作者把 48MP 镜头重新对准屏幕，使整个有效显示区完整入镜，并保证日光或补光足够；
  回复“相机已对准、屏幕完整入镜、光线已开”后，先重新做 setup-only 预检。预检通过前不得
  消耗正式 W3 名额或进入 T3。

## 2026-08-31 05:45 T3 日间 48MP 辅助粗筛与 W4 状态门离线就绪（最高优先级）

- 操作者已准备休息；本轮严格只做离线代码与计划。继承现场状态不变：J2
  commanded/query `OFF`、屏幕保留 W3 干净白、`electrical_state_proven=false`。截止本节没有
  访问相机、设备网络、COM 或继电器，也没有 flash、reset、rewire 或 display refresh。
- T3/W4 冻结固件和两次 visible-refresh 预算不变。新增日间辅助路线使用唯一允许的
  `48MP USB Camera / VID_32E4:PID_4801`；明确排除双目 `VID_1BCF:PID_0B15`。本轮统一采用
  `README camera.md` 的正式静拍档：`MJPG 4000×3000@15 / focus79 / exposure=-6 /
  WB4600`；fresh-V2 的 `exposure=-3` 不得混入。
- 明日顺序冻结为：当前 W3 白场断电拍 1 张 → T3 app-only 写入/验证和 4-GET 诊断 → relay
  ON 后只读 raw `BUSY=1` → 唯一 T3 刷新 → relay OFF → 最多 5 次取得并 O_EXCL 封存 3 张
  atlas → 只有四帧原始证据深验通过才允许安装 W4 → 唯一 W4 白恢复 → relay OFF → 末端白图。
  相机分析可以在 W4 后离线完成，分析结论本身不阻止安全刷白。
- 若 5 次内不能取得 3 张合格 atlas，必须保持 relay OFF 并保留双稳态 atlas；不安装 W4，
  等待操作者决定。若原始照片已封存但粗判为 REVIEW/FAIL，则允许按计划执行 W4 containment。
  任一 action/diagnostic/BUSY 门失败均保护性 OFF、无 retry/recovery/autochain。
- 自动输出只允许 `HUMAN_CAMERA_SCREEN_PASS/REVIEW/FAIL`。低照度、几何失败、暖色歧义或低信心
  一律 REVIEW；相机不声明绝对色、稳定新色、正式 profile-following、灰阶或 qualified colour。
  人工观察仍可补充，但不得用占位词补造事实。
- 离线执行卡为
  `docs/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_RUNBOOK_2026-08-31.md`。状态门 V2 已
  O_EXCL 封存为
  `.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V2.json`，
  bytes/SHA-256=`27457 / d3c0d2e12804c459d03872479da91bfce81ebcff039128f7395ebdbb937ef551`；
  初版 V1 保留但被 V2 明确替代。
- 四帧 capture pack 已就绪：
  `tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py`，SHA-256=
  `5608ac7c24fd7fad28d5279cdcafae4bc2fd85ee098d9dd5850d12bf8e0522de`。每次调用最多采一帧，
  相机打开前先永久 O_EXCL claim；白参考最多 2 attempts、T3 三帧总计最多 5 attempts，失败不
  自动 retry/fallback。四张图各用本帧四角，逐帧检查 64 格投影；对应角漂移上限 `30 px`，
  同时严格要求 camera instance/mount/requested/effective settings/尺寸全等。
- camera-only analyzer 已就绪：
  `tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py`，SHA-256=
  `1a75d63fea7a3d32adb431a8083c58b3d1f0e3ccb16b12fddb8b9c8b78d2a40c`。无人工 seed 仍生成完整
  64 格报告，但最高只能 REVIEW 且不生成 compact；只有真实完整 seed 才可综合 PASS 并 O_EXCL
  输出 compact。四副本门=`8/12 ΔE00`、三帧门=`3/6 ΔE76`、白参考 `L*<25 FAIL /
  25–35 REVIEW`，同时检查 controls、底边、条纹、残留与帧对齐。
- 正式 capture allowlist 已精确加入新 W4 的 campaign/test/contract/BIN/action/descriptor/role/
  marker，并修复 `...SUCCESSOR` marker 降级到通用 recovery role 的绕过；11 类近似篡改均被
  fail-closed 拒绝，历史白收容绑定保持不变。
- 主线程最终联合回归=`150 passed / 425.80 s`；格式、Ruff 和 py_compile PASS；计划 V2 深验
  PASS。所有测试均离线，当前现场状态仍为 J2 OFF、W3 干净白保留、无任何新增硬件动作。

## 2026-08-30 22:02 T3 A/C profile-following 人眼判因与 W4 白收容已离线封存，尚未上机（最高优先级）

- 下一轮改为“人眼判别为主，48MP 相机可选且只用于留档”。T3 只做一次 fresh
  `AC` 互换 atlas：`global=active / CS1=active535(A) / CS2=commented535(C) / round=3`；
  frame、双 DTM、`4×8` 位置平衡布局与已完成的 T2 V2 逐字节不变，只互换完整
  A/C tuple。这是人工 screening，不是绝对色标定或 formal colour gate。
- T3 最终身份：contract=
  `714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19`，descriptor=
  `52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9`，action=
  `db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104`。BIN=`805232 /
  05c00d71a163ecfc22d0d333404ac8967eaa06b929003ce0c28dda7499615760`，ELF=`13299376 /
  89d20faec2d5bde42915a5fe30515c917f722ca06777b016a75c38020e83a56e`。路由、NVS、claim 与
  output root 全部 fresh；历史 10 个 action 不可执行，旧 `t3-ac-repeat` CLI 路径已在
  configure/request/claim 之前 tombstone。
- 专属 W4 factory-OTP white 只绑定上述 T3 的 campaign/contract/descriptor/action 四元组。
  W4 contract=`7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52`，
  descriptor=`398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45`，
  action=`e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b`。
  BIN=`787248 / 9f3ab672c214cdf128a01a51b2803d5a586f72fab1cad065373eead30ee63bf7`，
  ELF=`13214976 / 16b37334ef8142ad33a8856dcf2850f751a8cf80489152766b8dc0602e278118`。
  它是单动作、无 retry/recovery/autochain 的独立收容，不会由 T3 自动串联。
- 已将既有 CA 人工事实以 O_EXCL 封存为
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/human-observation-ca-v2-v1.json`：
  bytes=`39377`，file/canonical SHA-256=
  `8e1a93bdd15c24bb808a698633ab4495edb1c1f94fb8249934420caca4a27921 /
  60510bc2e1cd5e9b7809a193574284a0ae63b44ec4f2a8416ac05f2c997d81e4`。已报告的 16 个
  controller/code 组四副本一致；未报告的时间、监督、瑕疵和信心度保留为
  `null/UNKNOWN/NOT_REPORTED`，因此 formal `comparison_ready=false`，没有补造事实。
- W3 操作者原话“白屏，干净”也已与 exact W3 action 和 final relay-OFF receipt 双重绑定：
  `.../MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/human-clean-white-authority-v1.json`，
  bytes=`4072`，file/canonical SHA-256=
  `5f5ff9d0c6bc023c461038e17fbc92b0fda5b475d52019bf736b91d745d5582b /
  2fceccd9cac4af23ffc0d27f7d14a546920d586cc0efd72f0799037cdb5b614f`。该 authority 明确保留
  `relay OFF != 负载侧电气已证明`。
- 现场下一轮只计划 **2 次 visible refresh**：当前 W3 clean-white 起点直接执行一次 T3
  atlas，完成人工盲填后执行一次 W4 white。不额外重刷前置白。正常只需填左/
  CS1(A) 与右/CS2(C) 各 code0..7 共 16 个肉眼词，并确认每 code 四副本一致/
  稳定及无底边、条纹、残留；工具再按冻结布局展开 64 cells。盲填卡见
  `docs/MF1750-RAW-P16-PROFILE-FOLLOWING-HUMAN-OBSERVATION-CARD.md`。
- 两固件 PlatformIO compile-only 与 artifact postflight 均 PASS；主线联合回归=`52 passed`，
  其中新增闭环审计=`7 passed`。它覆盖 fresh 身份/路由/NVS/claim/output 隔离、
  旧 T3 tombstone、真实形状 version/manifest 正负门、T3/W4 两套假设备 J2-OFF
  `4 GET / 0 POST / 0 claim / 0 refresh / O_EXCL`、W4 exact source quartet 和双 INI 无 upload
  surface。Ruff check/format 与 py_compile 均 PASS；T3/W4 `dry_validate` 均为
  `PASS / artifacts_verified=true`，CA/W3 人工 authority 深验也均 PASS。
- 本节截止时只完成离线代码、compile-only、哈希封存和回归；**没有 flash、reset、设备网络/
  COM/继电器访问或 display refresh**。当前物理状态继承上一节：J2 commanded/query OFF，
  屏幕保留干净白，`electrical_state_proven=false`。下次上机仍必须在 relay ON 后先只读确认
  当前固件 raw `BUSY=1`，才允许 claim/ARM/EXECUTE。

## 2026-08-30 20:43 T2 discovery successor V2 人工粗发现完成，W3 白收容 PASS，J2 OFF（最高优先级）

- fresh discovery-only T2 V2 action=
  `c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f`
  已 `complete_pass / COMPLETE`；每侧为 `4×8` 位置平衡 atlas，恰好
  `1 driver / 1 visible refresh`，driver total=`41913 ms`，
  PON/DRF/POF=`261/29211/150 ms`，无 timeout/retry/recovery/autochain。
  action evidence=
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/action-01-position-balanced-atlas.json`，
  bytes=`46464`，file/canonical SHA-256=
  `490df32422ec362f20c09e40d60d1e86e3f8bb46e9820f624004a4f07d08a989 /
  a7fc644e46586a5ebe8a1d447062a0ad6b0db8b8c2121ca61c3d842980e6bbcb`。
- action 前的失败均为 pre-mutation 诊断：初版 V2 host adapter 遗留 V1 baseline-role
  和 action-round 绑定，修正后 fresh J2-OFF diagnostic PASS；随后两次 ON 准入读到
  raw `BUSY=0` 并立即保护性 OFF。这些路径均为 `0 POST / 0 claim / 0 refresh`，
  不计 action retry。host 修正的正负 wire-validator 回归已通过；联合 V2 定向回归=`32 passed`，
  Ruff 和 py_compile PASS。
- 人工观察第一行：
  `CS1/commented535(C)=[橄榄,黑,绿,白,浅黄,蓝,黄,黑]`；
  `CS2/active535(A)=[红,粉,绿,白,棕,蓝,深粉,深蓝]`。
  同一侧四行呈相同的八色集合、顺序不同，保留观察期间外观稳定。
- 上述颜色词只属于人工粗发现。候选尚未在受控照明下完成色卡或 48MP 定量分析，
  未证明绝对色、单像素新颜料、跨位置/跨批重复性、profile-following 或正式调色板资格；
  `qualified_colour_count=0`，原 T1 正式门 FAIL 不翻转，原冻结 T2/T3 仍未执行。
- 精确绑定 T2 V2 的 W3 factory-OTP-white action=
  `b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9`
  已 `complete_pass / COMPLETE / 1 driver / 1 visible refresh`，driver total=`35014 ms`，
  PON/DRF/POF=`180/22521/140 ms`，无 timeout/retry/recovery/autochain。
  action evidence=
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/action-01-factory-otp-white.json`，
  bytes=`29734`，file/canonical SHA-256=
  `445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef /
  624df0db0c082a151f54a051ca45209f4114b67a1643c358269d3efe444d611f`。
  操作者确认最终全屏干净白。
- 本轮发现继电器 ON 后 raw BUSY 准入电平存在建立延迟。以后 relay ON receipt 不能直接
  作为 action admission；只允许先用只读 GET 确认 raw `BUSY=1`，在此之前不得 claim、
  ARM 或 EXECUTE。若准入电平未建立，则保护性 OFF；不得用固定 sleep 或动作尝试代替确认。
- 最终 OFF receipt=
  `.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1/relay-post-action-protective-off-20260830-204303.json`，
  SHA-256=`febbab71fcbca53130179424775caf6245990d6098f4fab8a1478474b537bae1`；
  commanded/query=`OFF`，当前屏幕保留干净白。继电器无下游量测，
  `electrical_state_proven=false`。

## 2026-08-30 15:44 48MP 白平场粗筛已落地并回放 PASS / 仅允许 T2 discovery successor（最高优先级）

- 按用户要求，相机职责已从“精准颜色识别”降为“粗筛／排队”。新增本地独立工具
  `tools/mf1750_raw_p16_crossover_t1_white_normalized_coarse_screen.py`；它不修改原严格
  analyzer/comparator，也不访问相机、网络、COM、继电器或屏幕。
- 粗筛把三张已密封 T1 atlas 的每格 RGB 用同一机位 W1 factory-OTP 白图的同位置 RGB 平场，
  固定公式=`clip(220*T1_RGB/W1_RGB,0,255)`。三张 T1 与 W1 的 48MP instance、mount、请求参数、
  frame 前后实际参数和 `4000x3000` 尺寸必须全等；白参考 `L*<25` 的位置只作无效样本，不拖垮
  其余 `3/4` 位置。
- 现有证据回放结果=`PASS_COARSE_SCREEN`：`16 PASS / 0 REVIEW / 0 FAIL`；左下强阴影对应
  `CS1-R3-C0-CODE3` 与 `CS1-R3-C1-CODE2` 被剔除，其余每组仍满足最少三位置；最大组内
  `ΔE00=5.384516695`，最大三帧中心漂移 `ΔE76=0.533904711`。
- O_EXCL 报告=`T1.white-normalized-coarse-screen-v1.json`，bytes=`293550`，文件 SHA-256=
  `4abbcf56bfb390e8cfb394f67eb8d6209fc35d845d1b096b096234973f4f50ea`，canonical=
  `3b080f2288c45f0ac5cdba9023b90a4f320d4b514bedece2372b72cf6b39d8ad`。
- 结论边界固定为 `eligible_for_t2_discovery=true`，同时保持
  `formal_gate_evaluated=false / formal_advance_to_t2_permitted=false /
  qualified_colour_count=0 / consumed_t1_state_changed=false`。它没有翻转原 T1 formal FAIL，
  也没有执行原已冻结 T2；下一步只能建立 fresh、明确 discovery-only 的 T2 successor。
- 主线程联合回归=`46 passed`；新增两文件 Ruff check/format 和 py_compile PASS。工具与测试仍属
  本地未发布代码，继续受 clean-machine 依赖／确定性生成物闭包约束。
- 本轮只有离线回放与文档更新；当前屏幕仍为 W1 干净白，J2 commanded/query OFF，未发生
  flash、reset、refresh、rewire 或 relay 动作。

## 2026-08-30 14:20 RAW-P16 crossover T1 位置门 FAIL，W1 白收容 PASS，J2 OFF / T2 冻结（最高优先级）

- 本地冻结 T1 BIN=`86ec547ae7e4f0b8d74a383efa48d14346f20275c8b9452e13274c9f0496c800`
  在 J2 commanded OFF 下只写 app `0x10000`，write 后独立 verify PASS；ESP32 仍为
  `COM8 / MAC a4:cb:8f:d9:fc:d4`。flash evidence SHA-256=
  `eec952a0e5897bb100105ec907a69828495992faeecf356ce90a915596b80305`。
- T1 在 `192.168.1.11` 的 fresh J2-OFF diagnostic PASS：boot=
  `17c47ed59ccb4a8b`，`4 GET / 0 POST / 0 claim / 0 visible refresh`，next ordinal=`1`，
  diagnostic SHA-256=`226a99f3b88c1f1d138dd490ca8d721565a4c3de960ac26cc40b6cb52ef170f6`。
- 执行前 48MP exact-bound 白屏质量探针通过相机身份、固定参数与 sidecar 深校验；JPEG/sidecar
  SHA-256=`48804b36...62c0d / fb396b0e...a24e`。整屏可见且仍为白屏方向，但当前画面偏暗、
  左下阴影明显，只能作为 retained pre-white 连续性与机位证据，不能用于绝对色标定。
- 唯一 T1 AC action=`73ff6d58...7c72` 已 `complete_pass / COMPLETE`：恰好 `1` driver、
  `1` visible refresh，PON/DRF/POF=`260/33921/151 ms`，driver total=`46622 ms`，无
  timeout/retry/recovery/autochain。action 文件 SHA-256=
  `483b7ebd97367327a1a81a1826e76b228d3b9c9f850e8e809c5a0ca5faf34e09`；claim 已永久消费，
  T1 不得重跑。
- action 后 relay 已 OFF，exact-bound query=`commanded_state OFF / off_gate_passed=true`，receipt
  SHA-256=`c929e8eaa5adb54a6a0691962c4b09e89cd2ff5aad56c37da2fd5f7887e92cbf`；仍无下游
  量测，`electrical_state_proven=false`。当时面板双稳态保留 T1 AC 位置平衡 atlas。
- `13:39` 已使用唯一允许的 `48MP / VID_32E4:PID_4801` 连续取得三张 T1 retained atlas
  正式帧；三次均为 schema v2、exact DirectShow path、固定 `4000x3000 MJPG / exposure -6 /
  focus79 / WB4600`，全部设置写入与前后 readback 通过、read failures=`0`。JPEG SHA-256=
  `409a15c7...c1ce6 / d20f806e...c401a / bd7e013c...fe3b1`；sidecar SHA-256=
  `8e16fdf0...7063c9 / b2e5633e...6d9e8 / 217f2345...d693b`。照片完整覆盖屏幕，色块清晰；
  环境仍偏暗，因此只能作同批 camera-relative 比较。
- 三张逐帧分析均通过 identity、action、相机、几何和 `64 cells / 16 controller-code groups`
  深校验；analysis JSON SHA-256=`77fdc1f1...92ec / 1e49d46a...bb48 / 6e0d7fe4...9145`。
  三帧同一 camera-lock，跨帧时间漂移很小，但四位置门固定 FAIL。正式 v2 预检报告
  SHA-256=`18856952b913768cc4c946daae1039ac37096ac5f0baa0b360bf48921c0aebc4`，
  canonical=`619efdec...0005`，结论=`POSITION_DEPENDENT_INCONCLUSIVE`、
  `w1_containment_required=true / advance_to_t2_permitted=false`。阈值=`6.6031868 ΔE76`；失败组为
  `CS1/code1=7.1580`、`CS1/code2=8.9632`、`CS1/code3=27.2249`、`CS2/code3=6.6559`、
  `CS2/code5=7.3937`。qualified new colour=`0`，不得宣称 profile-following、controller parity、
  稳定新色或灰阶。
- 首版 O_EXCL 预检 SHA-256=`15cde97b...3d66` 曾把 W1 安全收容与 T2 推进合成一个字段；原文件
  未覆盖、未删除，v2 通过原文件 path/file SHA/canonical 显式 supersede，并纠正为“W1 必须、
  T2 禁止”。
- W1 frozen BIN=`4dc8e0333b9a37839af18cca0c76ad36d94bd621b6cbc7510b8d775dfd3e2b81`
  已在 exact relay-OFF 后 app-only 写入并独立 verify PASS；flash evidence SHA-256=
  `beb0c07cca4699b547cf4fe0b172f67ee3483cc35d9b34c49a1a1566abc213ab`。fresh J2-OFF
  diagnostic=`4 GET / 0 POST / 0 claim / 0 refresh`、boot=`89243ae1014aa53d`，文件 SHA-256=
  `10c0629dce6065f0ac8292de6145e34193e2b0f74c602848d254be81b96b627b`。
- 唯一 W1 action=`f8cf26e3...50a5` 为 `complete_pass / COMPLETE / 1 driver / 1 visible refresh`，
  PON/DRF/POF=`180/22521/141 ms`、driver total=`35013 ms`，无 timeout/retry/recovery/
  autochain。action file/canonical SHA-256=`d0a936c2...fb57 / dd7f1fb2...d253`。保护脚本随后
  relay OFF，最终 exact-bound OFF receipt SHA-256=`3095af42f93f1b953a1b92eb6cea782e58def95e669464a5df4ae11bade71c7d`；
  `electrical_state_proven=false` 保留。
- 指定的 48MP 相机已取得 W1 白场全屏照片；JPEG/sidecar SHA-256=
  `4e07791e...f37d / d855422f...ccfd`。独立 O_EXCL 视觉分析=`PASS / confidence=medium`，
  analysis ID=`9324718e...395b`、文件 SHA-256=`3c294dd7...69e4`：活动区为干净白场，原 4×8
  色块、色斑、轮廓、条纹、底边异常和中心接缝均未见。画面欠曝且左下有明显阴影，因此只证明
  “可见残留清除”，不证明绝对白点或空间均匀度。
- 当前面板保持干净白，J2 commanded/query OFF；T1 action 与 W1 action 均永久消费，禁止重跑。
  下一步先离线固化局部白参考照明诊断并改善补光，再以 fresh identity 重做 T1 资格复核；当前
  T2/T3 不得执行。
- 后续 48MP 自动识别先采用非资格性粗筛：允许普通照明下用同位置白场平场、宽色桶、宽明暗档
  和明显缺陷作候选排队，不再让相机直接承担精准颜色识别。已消费 T1 的正式
  `FAIL_T1_POSITION_TEMPORAL_PREFLIGHT`、`qualified_colour_count=0` 和
  `advance_to_t2_permitted=false` 均保持不变。粗筛全组 PASS 最多只允许建立 fresh、
  discovery-only 的 T2 successor；它不执行原已冻结 T2，也不把候选升级为合格颜色。

## 2026-08-30 12:02 RAW-P16 日光取证、独立刷白和相机白场复核完成（最高优先级）

- 本项目继续只使用 `48MP USB Camera / VID_32E4:PID_4801`，明确排除
  `VID_1BCF:PID_0B15` 双目相机。采集程序已加固为 DirectShow exact path，在打开前、
  取帧时和取帧后均核对身份；今日正式照片均为 schema v2，固定
  `4000×3000 MJPG 15 fps / AF0 focus79 / exposure -6 / AWB0 WB4600`。
- J2 保持 OFF 时，对已保留的 mixed-R20 RAW-P16 atlas 取得三张独立日光帧：
  JPEG SHA-256 依次为 `2b851b9d...05a3 / 0c6f0e4b...2027 / 2eeac0b7...6efe`。
  三张照片仅作本地 evidence，由 `.gitignore` 排除；GitHub 只同步哈希、工具、
  测试和结论。
- 新增专用 `4行×2列/控制器` 分析器，code 严格按 row-major `0..7`，未复用旧
  `2行×4列` same-R20 几何。三帧当前照片独立拟合均为 14 格支持，重投影
  RMSE=`1.071 / 1.600 / 1.155 px`；三帧一致标记左右明显差异候选
  code=`3,4,5,6,7`，code=`0,1` 为边缘差异，code=`2` 本批无明显差异。对应
  analysis JSON 文件 SHA-256=`c03a746b...80c7 / b087f783...77d / 375e5857...2c9b`。
  这些只是相机相对候选，`qualified_colour_count=0`，不证明绝对色、稳定性、
  重复性或新的可用颜色。
- 当前不能把差异表述为“同波形左右不一致”：该 atlas 故意设置
  CS1=`active535(A)`、CS2=`commented535(C)` 两套不同 R20。本批候选必须通过
  `AC↔CA` 交换，才能判断是否跟随 profile 而不是跟随左右物理位置。
- 拍照完成后，独立 post-white containment 在 J2 OFF 下 app-only 写入 COM8 并 verify
  PASS，MAC 两次均为 `a4:cb:8f:d9:fc:d4`；专用 J2-OFF 诊断为
  `4 GET / 0 POST / 0 claim / fresh NVS / BUSY=0`。随后唯一 factory-OTP white action
  `12a146d8...8cd6` 以 `complete_pass / 1 driver / 1 visible refresh` 完成，
  PON/DRF/POF=`180/22521/141 ms`，无 timeout/retry/recovery/autochain。action file/
  canonical SHA-256=`22cb9455...a690 / 7f787d59...66bf`。
- action 后保护脚本已执行 relay OFF，Hub2 exact-bound query 再次返回
  `commanded_state=OFF / off_gate_passed=true`；receipt SHA-256=`3c137669...5eb`。继电器
  没有下游电压/电流反馈，因此 `electrical_state_proven=false`保留。
- 通用相机取证器已新增对本次 RAW-P16 containment 的精确冻结 allowlist；它锁定
  profile/campaign/test/contract/build/action/descriptor/完整 marker，不泛化放行任意 containment。
  相关回归 88 passed，Ruff/format PASS。正式白场 JPEG 已由同一 48MP 固定参数取得，
  SHA-256=`ec2d2223...2157`；独立 O_EXCL 视觉分析为 `PASS / confidence=medium`，
  analysis ID=`fc8a577e...a890`、文件 SHA-256=`1e2274e0...02d2`。全屏可见范围为
  干净白，未见原 atlas 色块、边框、色斑或固定线残留。照明阴影和拍摄蓝偏仍是相机
  环境限制，不宣称绝对白点。
- 下一个真屏判因流程已固定为 fresh `T1 AC → 白 → T2 CA`；只有差异跨左右跟随
  A/C profile 时才进入 `白 → T3 AC-repeat → 最终白`。每侧改用位置平衡 `4×8`
  atlas，每 code 四个分散位置；重点 code=`3,5,6,7`，code4 作 guard，code0–2
  作 internal controls。明度/灰阶仍未解决：先前明度矩阵各列肉眼基本一致，现有
  L* 差异常与色相变化耦合，不能当作可控单像素灰阶。
- 上述 crossover 已完成**原始工作树内**纯离线落地：T1/W1/T2/W2/可选T3/W3 六镜像均
  build SUCCESS，本地 postflight=`artifacts_verified=true`；atlas J2 显式确认门及 literal-
  private-IPv4/no-proxy/no-redirect mutation 门通过独立审查；主线程综合复跑 `111 passed`，
  Ruff check/format PASS。没有访问硬件、设备网络、COM、继电器或相机，也没有 flash/reset/
  refresh；因此真屏状态仅为 `LOCAL_OFFLINE_READY / NOT LIVE-EXECUTED`。
- **12:48 clean-checkout 纠正：GitHub代码提交 NO-GO。** 独立 short-path checkout 覆盖
  文档化46文件后，source preflight与6个镜像编译均PASS，但精确12个BIN/ELF哈希FAIL；ELF
  嵌入绝对checkout path，ignored Wi-Fi本地配置也改变镜像。即便使用同一未披露配置，T1 BIN
  同字节数仍有65 bytes随嵌入identity/checksum变化。拟提交shared foundation又混有多项历史
  campaign、缺少完整条件include/测试/config闭包，并有vendor LUT再分发边界待确认。因此本轮
  只允许已完成的文档里程碑保留在GitHub；代码不得暂存或推送，直到 deterministic build/
  artifact release方案及foundation拆分通过。历史 same-R20旧冻结artifact replay仍明确排除，
  不能宣称全仓库测试全绿。
- 本轮详细证据、决策门和 GitHub 同步规则见
  `docs/MF1750_RAW_P16_CROSSOVER_TEST_PLAN_AND_LIVE_RECORD_2026-08-30.md`。

## 2026-08-28 23:33 RAW-P16 真屏已显示并暂停待白天拍摄（最高优先级）

- V1B pre-white 已在 J2 OFF 下 app-only 写入并独立 verify PASS；唯一 factory-OTP
  white action=`e66d0131...e740e` 以 `complete_pass / 1 driver / 1 visible refresh`
  完成，无 timeout/failure/retry/recovery/autochain。操作者随后确认“全屏干净白、
  无色块或色斑残留”。
- 重绑 V1B 的 RAW-P16 main 在 J2 OFF 下 app-only 写入、独立 verify 和 fresh
  4-GET diagnostic 全部 PASS；diagnostic=`0 POST / 0 claim / 0 refresh`。唯一 gallery
  action=`9f5b84a1...0a088` 以 `complete_pass / 1 driver / 1 visible refresh`完成，
  PON/DRF/POF=`260/33941/151 ms`，无 timeout/failure/retry/recovery/autochain。
- 人工观察：左右不一致；第1行白+绿、第2行蓝色位、第3行黑色位肉眼
  一致，其余对应位明显分化。这与本次固定的 CS1=`active535`、
  CS2=`commented535` 不同 R20 目标一致；当前只是候选端点，不是稳定新色或
  合格色标定。
- 48MP `VID_32E4:PID_4801` 已取得人工补光下的诊断照片；由于强反光、
  过曝且旧 same-R20 分析器是 `2行×4列/控制器`，与本次 `4行×2列/控制器`
  布局不同，该旧分析输出明确作废，不得引用其数值或分类。
- 按操作者要求现在暂停：J2 已 commanded+query OFF，面板双稳态保留 RAW-P16
  atlas；不再拍照、刷固件、复位、刷屏或动继电器。明天白天关闭补光、
  严格绑定 48MP 后重拍正式照片；拍完与人工确认后才执行独立 post-white
  containment。当前 `electrical_state_proven=false`。

## 2026-08-28 23:13 RAW-P16 main改绑fresh pre-white V1B（最高优先级）

- fresh pre-white successor为
  `EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B`，contract=
  `d6c88b8d...32c61`，NVS=`rp16gpw_v1b/used_p16pb`；它尚未刷写或执行。
- RAW-P16 main保持原campaign、NVS、action、`4行×2列/控制器`布局、mixed-R20和post-white来源不变，
  只把外部前置白绑定从已封存V1替换为V1B。新main contract=`f9b1f6b8...c409d`；
  BIN=`797712 / 1cd68a43...80bef`，ELF=`13282824 / a1d1ad39...39b4d`。
- 旧main（contract=`5d4d6084...6185c`，BIN=`6aa3660d...1f75`，ELF=
  `587ae586...914b0`）是**OFFLINE_SUPERSEDED_NEVER_FLASHED**，不得上机。这里的“从未刷写”
  仅指旧main；下方22:51记录的旧pre-white V1 app-only刷写与host预检失败事实不变。
- 本次仅完成离线源码改绑、clean build、哈希重封和测试；没有访问硬件、设备网络、COM、
  继电器或相机，没有刷写、复位或刷新。runner的direct no-proxy、no-redirect和literal-local-IP
  传输门保持并新增回归覆盖。main clean build `SUCCESS`，当前联合回归`160 passed`，相关
  Ruff check／format check、pack和dry-validation均PASS。

## 2026-08-28 23:10 MF1750 相机唯一绑定（最高优先级）

- 本项目唯一允许的采集相机是 `48MP USB Camera / VID_32E4:PID_4801`；
  已锁定实例为 `USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000`。
- `VID_1BCF:PID_0B15` 是另一台双目 USB Camera，明确排除：不得用于 MF1750
  拍摄、识别、自动裁决或故障回退。
- OpenCV `index` 只是当次枚举结果，不是设备身份；正式采集必须先核对
  `VID_32E4:PID_4801`，核对失败则 fail-closed，绝不自动改用双目相机。
- 当前旧采集实现仍只按 OpenCV index 打开设备，`camera_id/instance_id` 是调用方
  文本，并未与实际 PnP 设备做强认证。因此在严格 VID/PID→DirectShow 绑定修复
  完成前，暂停新的自动相机取证；旧 sidecar 不得单独作为物理相机身份证明。

## 2026-08-28 22:51 RAW-P16 pre-white V1 host预检失败并安全封存（最高优先级）

> 本节覆盖下方 `22:03` 的“尚未刷写”软件状态，但不把一次host解析失败改写成面板动作。

- 操作者本轮报告当前屏幕“白色”，并明确J2由助手通过继电器控制；该陈述只记作未绑定的
  视觉起点，不能替代fresh pre-white action。exact-bound relay查询首先证明
  `COM14 / channel1 / Hub2 / commanded OFF`，仍无负载侧电气反馈。
- J2 OFF下，RAW-P16 pre-white V1 BIN `786592 / 29ecaf18...42ad` 已app-only写入COM8并
  独立verify PASS，ESP32 MAC仍为`a4:cb:8f:d9:fc:d4`；运行ELF和contract通过direct
  no-proxy只读`/version`核对。
- relay ON后调用旧pre-white runner；该runner在任何ARM/EXECUTE前的首次GET响应解析处返回
  `device response is not UTF-8 JSON`。随后立即relay OFF。no-proxy只读salvage确认设备仍为
  `READY / phase0 / next1 / persistent_key_absent`，`arm_request_count=0`、
  `execute_request_count=0`、`total_driver_call_count=0`，report=`NOT_EXECUTED`；因此没有取得
  可见刷新或设备mutation证据，RAW-P16 main尚未刷写或执行。
- 根因边界：旧runner使用urllib默认代理；同一设备的direct no-proxy GET返回正确UTF-8 JSON，
  故代理污染是当前最强推断，但未保存代理原始响应，不能升级为逐字节证明。host claim已经
  在首个网络请求前永久创建，V1严禁重试；设备NVS尚未消费不改变host claim的封存事实。
- J2已执行OFF-with-feedback并再次exact-bound query OFF；`electrical_state_proven=false`。
  失败取证见
  `.test-output/hardware/MF1750_RAW_P16_PRE_WHITE_ANCHOR_20260828_V1/runner-failure-salvage.json`。
  下一步只能使用全新campaign/API/NVS/claim/output的no-proxy pre-white successor；在其完成
  并由操作者确认干净白前，不得向P16 main传入external-pre-white确认。

## 2026-08-28 22:03 RAW-P16 与 LUMA-GRAY-V1 已离线就绪（最高优先级）

> 本节是新的**软件／工件状态**，不改写下方 `20:51` 的最后一次真屏证据。本轮没有访问
> ESP32、设备网络、COM、继电器、相机或面板，没有刷写、复位或刷新；因此物理状态未被
> 本轮重新证明，最后可引用的现场状态仍是下方已记录的 commanded/query OFF 与干净白收尾。

- `RAW-P16-V1` 已完成三套相互独立的 fresh campaign：pre-white factory-OTP 白锚、唯一一次
  mixed-R20 端点画廊、post-white factory-OTP containment。主图每个 controller 为 `4行×2列`，
  固定展示 code0..7；CS1 R20=`active535`、CS2 R20=`commented535`，不做抖动或空间混色。
  这代表 `16` 个 controller/code 原始观察位，不代表16个唯一色或合格色；runtime code7也不
  是factory-white。三套 contract 依次为 `c8ae63b7...2196c`、`5d4d6084...6185c`、
  `1d08798b...ce14`；BIN SHA-256依次为 `29ecaf18...42ad`、`6aa3660d...f75`、
  `8c33085d...03c1`。
- `LUMA-GRAY-V1` 已完成：`2 source transport anchors × 8 middle codes × 2 targets = 32`
  条探索配方，分两页；每条配方在每个 controller 上有四个位置平衡副本。它不使用网点、
  PTLW或局部HOLD，也未虚构factory-OTP逐格黑／白源态；active code3/code7仅是未命名的
  runtime transport anchors。主／独立白收容 contract 为 `db671c68...1b260`／
  `d75573f6...9736`，BIN SHA-256为 `fbdbb9e7...7b9b2`／`9c428924...fd6b6`。
- 当前资格边界保持不变：P16 `qualified_colours=0`、`unique_colours_claimed=0`；中性灰和明度
  `qualified_gray_levels=0`、`qualified_brightness_levels=0`、
  `true_neutral_gray_claimed=false`。蓝色旧梯度未见稳定深浅；红／粉、黄／橄榄旧结果仍受
  位置／照明混杂影响。新固件只是把“完整直接端点展示”和“32条位置平衡明度搜索”准备好，
  不能提前宣称已得到稳定新色或灰阶。
- 主线程独立复核：相关新测试与基线回归共 `127 passed`；五套 PlatformIO build 均
  `SUCCESS`；五套 pack／dry-validation 均为 `hardware_accessed=false`、
  `network_requests=0`、`display_refreshed=false`；14个新增 Python／测试文件 Ruff check 与
  format check PASS。额外只读架构审计逐项检查 fresh identity/NVS、mixed-R20、动作角色、
  2×4／32×四位置布局、工件绑定及 no retry/recovery/autochain，结论 PASS、无必须修复项。
- 下一次真屏最短顺序固定为：P16 pre-white → 人工／相机确认干净白 → P16 main拍摄16端点 →
  P16 post-white确认干净白；之后另起 LUMA main，严格执行 ordinal 1..8，仅在4和8采集候选，
  最后用独立LUMA containment白屏。任何固件都不会自动串到下一套。
- 完整身份、哈希与命令见 `docs/MF1750_RAW_P16_ENDPOINT_GALLERY_V1_RUNBOOK.md`、
  `docs/MF1750_LUMA_GRAY_V1_RUNBOOK_2026-08-28.md`；综合颜色边界和资格门见
  `docs/MF1750_RAW_P16_AND_LUMA_GRAY_V1_PLAN_2026-08-28.md`。

## 2026-08-28 20:51 Same-R20 4×8 V2 已完成并白屏收尾（最高优先级）

> 本节覆盖下方 `18:58` 中“等待恢复照明／尚未执行 V2”的旧口径；不改写
> V1、欠曝／过曝探针或其他历史原始 evidence。

- 恢复现场照明后，旧 exposure=`-3` 在当前灯光下严重过曝；正式 V2 六帧比较
  经显式曝光探针固定为 exposure=`-6`。相机实例、机位、`4000×3000 MJPG 15 fps`、
  focus=`79`、手动 WB=`4600` 保持一致；三张前置白与三张 atlas 的 requested/effective
  settings 完全相同。G-1 只继续提供几何 homography，不用于跨曝光绝对颜色比较。
- 独立 AA-abort factory-OTP white 的三张 relay-OFF 正式白场照片通过质量门：
  panel median=`72.941 L*`，白场时间噪声 P95=`0.0 ΔE76`，低于固定门限
  `6.6031868 ΔE76`。先前欠曝、过曝及曝光校准 probe 均只保留为诊断证据，不进入正式分析。
- Same-R20 4×8 V2 的 app-only flash/verify 与 fresh J2-OFF diagnostic 均 PASS；
  diagnostic 为 `4 GET / 0 POST / 0 claim / 0 visible refresh`。同 boot
  `f2eeb7703ab4694c` 下唯一 atlas action
  `2eef95155b78ee27b13e5971c40618106779495c80e0e3ef833eb2484f420476`
  为 `complete_pass / COMPLETE`，恰好 `1` driver call、`1` visible refresh，
  PON/DRF/POF=`260/33911/151 ms`，无 timeout/failure/retry/recovery/autochain。
  该 action/claim 已永久消费，严禁重放。
- action 自述中 CS1/CS2 的 active R20-535、R21-704 SHA、DTM FNV 与完整 payload 均相同。
  这只支持 firmware/device-report payload identity，不是逻辑分析仪 bus trace，
  不能升级为 SPI 接收一致或 controller/panel 电气等价。
- relay commanded OFF 后取得三张 retained atlas；曝光质量、几何和白场时间噪声均 PASS，
  每帧左右合计 `64` 格均有效。但同一 code 的四位置离散最大 P95=
  `43.8646 ΔE76`，远高于门限 `6.6032`，故位置门 FAIL，最终分类固定为
  `POSITION_DEPENDENT_INCONCLUSIVE`。原因仍可能包含显示位置／历史效应、照明反射、
  光学梯度或分析 ROI 混杂；现有证据不能把它归因给某一 controller。
- controller comparison 中的 common offset=`2.4827`、maximum interaction=`33.0592`、
  normalized LR=`34.2067`、raw LR=`61.7867 ΔE76` 仅是诊断字段；由于前序位置门失败，
  不得据此声称 controller mismatch 或 parity。
- 本测试没有绝对色卡标定，也未建立稳定的 recipe→颜色映射；
  `absolute_colour_proven=false`、`controller_bus_capture_proven=false`、
  `electrical_controller_equivalence_proven=false`。正确结论是“没有取得合格新色结论”，
  不是“证明没有新颜色”。
- 独立 Guard factory-OTP white containment 随后以 fresh boot
  `0ccd16ae6cd35a01` 完成唯一白动作，`1` driver call／`1` visible refresh，
  PON/DRF/POF=`180/21701/141 ms`。固定相机 post-white 分析 PASS：全屏干净白，
  旧 4×8 atlas、色块、条纹、中心接缝或边缘残留均未见。最终 exact-bound relay query
  为 commanded `OFF`；继电器无负载侧反馈，故 `electrical_state_proven=false`。
- 正式照片、sidecar、action、位置分析、独立白收容、后置 OFF receipt 及相机白屏 PASS
  已生成 O_EXCL `evidence-bundle-v2.json`；bundle ID=`417e70cc38fa7c656ebeedaf371d2204cd6eea5eb72c77ceb7664ecf5ce5f71c`，
  文件 SHA-256=`7aeb2a7f6099a95ee87912abe3ee0806c8ef49793fb366709eaecc82b25ce9db`。详细文件、哈希和证据边界见
  `docs/MF1750_STAGE3_SAME_R20_PARITY_4X8_V2_LIVE_RECORD_2026-08-28.md`。

## 2026-08-28 18:58 AA-abort 白收容已封存，V2 白基线等待恢复既有照明（最高优先级）

> 本节覆盖下方 `18:20` 中“屏幕保留 AA 2×4 atlas”与尚未执行独立收容的口径；
> 不改写 Batch1 V1 的原始 evidence 或失败裁决。

- 独立 `Same-R20 AA-abort factory-OTP white` 已完成唯一真屏动作并封存：
  outcome=`complete_pass`，terminal=`COMPLETE`，boot=`93d389c6f5323145`，恰好 `1` driver call /
  `1` visible refresh，无 failure/timeout。action 文件 SHA-256=
  `57785a566bccf35a1f404d4e01e5bf9f107df906c3a8f193009d21ee52c66cb7`；该 action/claim
  已永久消费，严禁重放、retry、recovery 或 autochain。
- 动作后继电器已 commanded OFF。`2026-08-28T18:58:04.900+08:00` 的独立
  exact-bound query 再次返回 channel 1 `OFF`，receipt SHA-256=
  `3e081f18831ace5103175b03f214f7f64aea04610dddc2abb4d3b7757ab20e38`。该继电器没有
  负载侧电压/电流反馈，所以只能记 commanded/query OFF，
  `electrical_state_proven=false` 保持不变。面板按双稳态保留本次 factory-OTP 白。
- relay OFF 后的 `camera-white-off-baseline-01` 和软件曝光 `m1` probe 都已留存，
  但两帧严重欠曝：全帧 mean RGB 分别仅为 `16.63/19.29/24.75` 与
  `16.87/19.53/25.06`，三通道低端剪切约 `29.8%–32.4%`。`m1` 虽请求 exposure=`-1`，
  帧前/帧后实际值仍为 `-3`。两帧均为 `INCONCLUSIVE`，只保留为欠曝诊断记录，
  **不进入 V2 任何白场定量基线、空间补偿或颜色裁决**。
- `19:12` 自动照明复查仍欠曝，mean RGB=`15.64/18.52/23.58`；照片/sidecar SHA-256=
  `bec950835b2174f3b994d68dd24e45501714f0655f6a6829204a6e6598c040da` /
  `58b6c1b3007183e6980da2d0d9ab3de8a5cc228ba10fbf5323d57700d4159260`。它同样仅作
  `INCONCLUSIVE / EXCLUDED` 诊断证据；该复查没有触发 flash/reset/refresh/relay 动作。
- 当前唯一下一步是恢复 G-1/G0 时既有照明，保持已锁定相机、镜头、机位与
  `focus 79 / exposure -3 / WB 4600` 不变，重拍三张 relay-OFF 白场基线并通过
  质量门；在此之前不刷写/不执行 Same-R20 4×8 V2，也不为迁就欠曝改动
  锁定相机 tuple。

## 2026-08-28 18:20 Batch1 AA 触发相机门后已终止（最高优先级）

> 本节覆盖下方 `17:35` 中“relay Hub2 rebind 仍阻塞”、G0 未执行以及
> Batch1 未执行的口径；不改写任何原始 evidence。

- 操作者 `2026-08-28` 最新明确确认：继电器实体没有变化，CH1 的
  `COM1→NO1` 接线没有变化。在该声明绑定后，Hub1→Hub2 窄 rebind 已通过：
  除 `usb_location` 由 `Port_#0004.Hub_#0001` 变为 `Port_#0004.Hub_#0002` 外，
  model/VID/PID/PnP/COM/no-iSerial 均不变；`COM14 / channel 1 / COM1→NO1`。seal
  文件 SHA-256=`c92aba1f6676a7d204fcffa5f5ed6112a14a58e4ecc7cf2959ff4bce8906ab94`。
- G0 V3 factory-OTP white 已完成：app-only flash/verify、J2-OFF `4 GET / 0 POST`
  diagnostic 均 PASS，同 boot=`ff476515e2b82e97`下唯一白恢复为 `complete_pass`，
  `1` driver call / `1` visible refresh。固定相机三帧白场 repeat-noise 基线 PASS：
  camera-relative CIE76 P95=`2.2010623`、max=`2.7452381`、baseline ID=
  `ceade72ca367c82fafd7746c26066b745399e37ab196410eda64f38cebcc6174`。全屏白场视觉门
  PASS，旧 128 格、色块、轮廓、底边黑线和离散残留均未见；这仍不是绝对白点
  或已标定色差证明。
- Batch1 same-R20 V1 的 app-only flash/verify 与 fresh J2-OFF diagnostic PASS；同
  boot=`347fc2a51e1a00de`下仅执行 ordinal 1 `SAME_R20_ACTIVE_ACTIVE_ATLAS`。
  协议结果 `complete_pass`，恰好 `1` driver call / `1` visible refresh，PON/DRF/POF=
  `261/33911/151 ms`，无 timeout/failure。执行固件 BIN/ELF=
  `d65fb20b...30977f / bf15d35d...e94b6`，contract=`718d6cf6...63f8`。
- 源码静态审阅与 action 自述均表明：两控制器使用同一 active R20-535
  (`716cc229...6e44b`)、R21-704 (`24acee29...863f`)、相同 atlas DTM，且 action
  回显 `controller_payloads_byte_identical=true`、两侧 DTM FNV 相同。因没有逻辑分析仪
  bus trace，这只是 **firmware/source parity PASS**，不是 SPI 总线逐字节接收证明，
  也不证明两半屏物理链路等同。
- AA 原始同步帧之后，在 relay commanded OFF 的保留画面上又拍了 `3` 张
  `locked_retained_retrospective` 帧；四帧均绑定同一 action/boot/相机/几何。
  正式四帧 report 文件 SHA-256=
  `172f3570e33701c9cf10a8d9f3c4fbb4c146e8fa8ee26d6f5a3e2f369809b67d`；白噪声导出
  探索门限=`6.6031868`。code1 median=`7.9410517`、code2 median=`10.5424026`，
  两者均 `4/4` 帧超门；其余 code 不满足 `3/4` repeat-majority。因而最终只能
  记为 `CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE`，不能声称已证明 controller/hardware
  mismatch，更不能声称新颜色。锁定相机没有消除固定空间照明、透视和半屏
  位置偏差，G0 三白帧只量化时间重复噪声，未做左右位置补偿。
- Batch1 V1 已按 fail-closed 规则在 ordinal 1 终止。ordinal 2–4 **forbidden / not
  executed**；严禁把原计划 ordinal 2 白动作当作 recovery。继电器现为 commanded
  OFF，exact-bound OFF receipt 文件 SHA-256=
  `c523566cf21a518108e27f47ceb7a030d3e19205a0abab0fa283f36461568c35`；
  `electrical_state_proven=false`。屏幕按双稳态保留 AA 2×4 atlas。
- 唯一后继路径改为：独立 `AA-abort factory-OTP white` 收容→relay OFF 下拍取
  新白场基线→独立 same-R20 **4×8 V2** 位置平衡 atlas。V2 在每个控制器内
  让 code0..7 各出现四个位置，用于区分持续半屏效应与位置/照明偏差。任一
  新上机动作均需使用这两个独立 campaign，不得恢复 Batch1 V1。完整记录见
  `docs/MF1750_STAGE3_SAME_R20_PARITY_V1_LIVE_RECORD_2026-08-28.md`。

## 2026-08-28 17:35 G-1 全屏几何/P0 锚定已完成（最高优先级）

> 本节覆盖下方 `17:05` 中“相机机位仍待调整／G-1 尚未完成”的口径；
> 继电器 Hub2 rebind 阻塞仍保持。

- 在不移动当前相机安装的前提下，使用 `4000×3000 / MJPG / 15 fps / focus 79 /
  exposure -3 / WB 4600` 锁定参数完成正式 `capture-retained`。整块面板边界、四角和两组
  8×8 网格均完整入镜；顶部线缆在有效面板之外。
- 浅黄／橄榄格在当前曝光下不适合旧的单一高饱和度轮廓路径，因此网格分析器新增
  Lab 三通道边缘回退及透视友好的固定 8 行聚类；旧照片和旧 JSON 输出保持逐对象一致。
  专项＋下游回归 `30 PASS`，Ruff/format/py_compile PASS。
- 正式 grid analysis 为 `128/128` 格，左右 support=`64/64`，homography inliers=
  `128/128`，RMSE=`1.1362767 px`，P95=`1.7799213 px`，所有格四角及内部采样区均在照片内。
  verdict=`SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT`。
- G-1 anchor 已以 O_EXCL 封存并深度验证通过；它只是回溯性的几何/P0 锚，不证明历史
  Action 连续性、绝对颜色、新颜色或波形因果。四件正式证据为：
  - 照片 `g1-locked-full-panel-p0-20260828.jpg` SHA-256=`0f2486ed...b01b0f3f`；
  - sidecar `g1-locked-full-panel-p0-20260828.capture.json` SHA-256=`15576558...ad7e85cb`；
  - grid `g1-locked-full-panel-p0-20260828.grid-analysis.json` SHA-256=`b60a2f5f...84517a1`；
  - anchor `g1-locked-full-panel-p0-20260828.anchor.json` SHA-256=`2f585718...f466df64`。
- 本节只读取了相机并做离线分析；没有继电器触点动作、设备 HTTP、flash、reset 或
  visible refresh。J2/channel 1 仍只有 commanded `OFF` 证据，`electrical_state_proven=false`。
- G0 的唯一剩余前置是 relay Hub1→Hub2 窄 rebind：操作者必须明确确认“同一实体继电器、
  CH1 仍为 COM1→NO1、接线未改”，然后才能离线 build/validate seal 并做一次 exact-bound OFF
  query。在此之前继续禁止触点 ON。

## 2026-08-28 17:05 G-1 现场预检与双门等待（最高优先级）

> 本节覆盖下方“下一步可直接 G-1/触点控制”的宽泛口径；不改变历史 evidence。

- 操作者授权开始测试后，仅执行了继电器只读 query 和相机预览；没有 ON/OFF 触点命令、设备
  HTTP、flash、reset 或 visible refresh。channel 1 返回 commanded `OFF`，但只证明命令态，
  `electrical_state_proven=false`。
- 本次发现 relay identity 的 model/VID/PID/no-serial/COM/PnP 均不变，USB location 从历史
  `Port_#0004.Hub_#0001` 变为 `Port_#0004.Hub_#0002`。按既有 no-iSerial 合同必须显式 rebind；
  在操作者确认“同一实体继电器、CH1 仍为 COM1→NO1、接线未改”并完成 seal 前禁止 ON。
- 已新增 relay 窄 rebind 工具 `tools/mf17506_stage23/relay_rebind.py`：只允许 usb_location 单字段
  变化，支持双 O_EXCL `capture-current`、离线 build/validate 和 exact-bound query；没有 ON/OFF
  入口。专项＋既有 relay 回归 `40 passed`，Ruff/format/py_compile PASS。`capture-current` 已实际
  完成一次 discover＋一次 CH1 query，0 触点切换、0 retry；证据位于
  `.test-output/hardware/MF17506_RELAY_REBIND_20260828_HUB2/`。
- G-1 预览 02 显示当前机位仅约 96.22% 面板入镜，右下角超出约 55 px，约 125/128 格完整，
  上边界受线缆遮挡；正式 grid analyzer 仅得到 29 个候选并 FAIL。预览不是 G-1 evidence，
  屏幕仍保留原 Action 4 网格，J2 仍保持 OFF。
- 相机 evidence 已新增 `capture-retained`，正确生成
  `locked_retained_retrospective` binding、逐项 `cap.set` 结果和 DSHOW raw 模式归一化；G-1
  继续强制所有设置写入成功、before/after 相同、focus/exposure/WB 与请求相同。专项 `23/23`、
  扩大回归 `81/81`、Ruff/format/py_compile PASS；preview 03 已实机证明十项设置均返回成功。
- 当前仅等待两项物理输入：(1) 相机后移/抬高并清除顶部遮挡，使面板四角及外围留白完整入镜；
  (2) 操作者回传上述同一 relay/CH1 接线确认。完成后重拍正式 retained frame，重新生成与照片
  SHA 绑定的 128-grid analysis，再封存 G-1；G-1 前不刷白。

## 2026-08-28 11:20 阶段三离线实现冻结（最高优先级）

> 本节覆盖下方 `08:45` 中“测试批次尚未实现”、旧“一眼状态”中的 clean-white／人工判色／
> 旧 brightness-next 口径；不改变任何历史原始 evidence。

- 本轮严格纯离线：没有访问设备网络、COM、继电器，没有 flash、reset 或 visible refresh。
  最后可信现场记录仍为继电器/J2 commanded+query OFF；电子纸按双稳态保留 Red/Pink V2
  Action 4 双 8×8 网格，并非 clean white；继电器没有负载侧电压反馈，故
  `electrical_state_proven=false`。
- 现场第一步改为 **G-1 零刷新锚定**：保留当前网格，在整块面板完整入镜、固定支架、手动
  焦点/曝光/白平衡条件下封存新 P0 照片、128 格 homography、camera tuple 和 mount identity。
  G-1 工具已实现并通过 `7/7`；它只证明回溯性几何/P0，不证明颜色、波形或局刷因果。
- G0 V3 white、Batch1 same-R20 parity、Batch2 recipe-position permutation、Batch3
  complete-tuple true-R20 partial HOLD 的固件、runner、照片/视频门和不可覆盖聚合 evidence
  均已完成。唯一顺序为
  `G-1 -> G0 -> B1 -> seal B1 -> B2 -> seal B2 -> B3 -> seal B3`，可见刷新严格为
  `1+4+4+4=13`；没有 retry、fallback、recovery 或 autochain。
- Batch1 BIN/ELF=`801712/d65fb20b...977f`、`13299408/bf15d35d...94b6`，contract=
  `718d6cf6...3f8`；Batch2=`800704/2a671646...9f65`、`13296988/8fe3017f...b70f`，
  contract=`5c628ccd...dda2`；Batch3=`816736/458fff47...a89f`、
  `13371716/8aaefd61...eb8`，contract=`38698de1...eb63`。三套均由 clean build 精确复现。
- G-1、白重复噪声、静态/视频采集、AA/CC 对比、配方置换比较、B1/B2/B3 evidence bundle
  和 B3 双前置验证已经联通；28 个相关测试文件合并为 `317 passed in 43.93s`，18 个新增/
  修改 Python 文件 Ruff、format、py_compile 全 PASS，三个 once runner dry-validate PASS。
- 当前相机指标是固定机位下的相对 Lab/CIE76，不是已校准 ΔE00；24 色卡留给后续绝对颜色
  资格。相机自动分析取代人工判色，但电流/温度监控、异常观察和物理急停仍需现场安全保障。
- 权威计划：`docs/MF1750_STAGE3_TRUE_R20_PARITY_PERMUTATION_HOLD_PLAN_2026-08-28.md`；
  离线上机就绪报告：
  `docs/MF1750_STAGE3_TRUE_R20_PARITY_PERMUTATION_HOLD_OFFLINE_READINESS_2026-08-28.md`。
  下次操作者回场时必须保持 J2 OFF 和当前网格，先完成 G-1，不得先刷白。

## 2026-08-28 08:45 下一阶段离线覆盖状态（最高优先级）

> 本节补充并覆盖下方关于“跨 LUT HOLD”已经成立的宽泛表述；不改变任何历史原始 evidence。

- 独立 Red/Pink V3 factory-OTP white containment successor 已完成纯离线冻结：BIN
  `789200 / 3721b60c...a1cfb`、ELF `13215844 / 2baf26d2...c7797`、contract
  `1618436e...a227`；专项 `18/18`、V3+冻结 V2+flash helper 回归 `45/45`，clean build、
  Ruff、format、py_compile、dry-validate 和 SHA manifest 全 PASS，独立审计无
  Critical/High/Medium 阻断项。它尚未刷写、诊断、claim 或执行；旧 V2 containment 的不可覆盖
  diagnostic FAIL 继续保持，绝不可重试。
- 重新审查驱动后确认：Red/Pink V2 Action 4 的 CS1 始终使用 active-535 R20，CS2 始终使用
  commented-535 R20；左右只共享高级 source/middle/target 码序列，并非同一底层波形。既有
  clean cross-LUT HOLD V2 只切换广播 PWR/PLL global header，两个控制器的 R20 仍各自固定；
  因此应改称“global-header 切换＋局部 HOLD PASS”，不能冒充真正 R20/LUT 轮换共存。
- 下一阶段冻结为最少 13 次可见刷新、三批判别方案：V3 白锚 1 次；AA/CC 同 R20 双控制器
  atlas 与白分隔 4 次；Action 4 source/middle 位置置换与白恢复 4 次；真正
  active→commented→active R20 轮换的三 ROI 局部 HOLD 与白恢复 4 次。详细计划见
  `docs/MF1750_STAGE3_TRUE_R20_PARITY_PERMUTATION_HOLD_PLAN_2026-08-28.md`。
- 当前仅 V3 白收容已离线 ready；三个新测试批次的独立固件、host runner、evidence contract 和
  自动相机判据尚未实现，故当前仍保持 J2 OFF／offline only，不得直接开始真屏动作。

## 2026-08-28 08:10 当前覆盖状态（最高优先级）

> 本节覆盖下方 `07:45` 覆盖段和“一眼状态”历史表中仍写 J2 ON、Action 4 未执行、
> 屏幕 clean white 或等待人工观察的旧口径；原始 evidence 保持不可变。

- 红／粉明度 main V2 已在同一 boot `1ffa520a2537168d` 严格完成 actions 1–4；四项机器结果均为
  `complete_pass`，每项恰好一次 visible refresh。Action 4 无可释放的独立候选，故冻结快速门已经
  封存 main V2，actions 5、6 均 **forbidden / not executed**，不得调用、重试或用独立收容冒充
  main ordinal 6。
- Action 4 同步照片已完整解释左右双 8×8：contour support `128/128`、homography inliers
  `128/128`、RMSE `0.572 px`；CS1／CS2 的 obvious spatial outlier 均为 `0`，obvious paired
  recipe 也为 `0`。其结论严格只是“没有超出平滑空间趋势的孤立左右配对 recipe”，**不否认**
  照片中已经观察到的橄榄绿、粉、玫红、赭橙等扩展外观色族；这些色族尚未稳定绑定到单一
  recipe，也没有 repeat、持久性、绝对色标或 qualified-new-colour 证据。
- Action 4 后 COM14/channel 1 已 commanded OFF 并独立 query 为 OFF；J2 保持 OFF，继电器无
  负载侧电压反馈，故 `electrical_state_proven=false`。电子纸按双稳态保留左右双 8×8 网格，
  当前屏幕不是 clean white。
- `08:07` 在 J2 OFF／断电保持状态下完成一次不触发刷新的相机复拍：照片
  `camera-action-04-poweroff-repeat-01.jpg` SHA-256=`86b0038a280307ab43e3d27f1585f63e4059005154204993fa9ea145a4ee045d`；
  权威 retrospective capture sidecar
  `camera-action-04-poweroff-repeat-01.retrospective.capture.json`
  SHA-256=`0470a5f69a14132b4ac1ee82cfa4002903264a790791ab1314d1b9d4a0906d50`；
  grid analysis SHA-256=`95241372c620d2874898290e50f9eae518d29fc7b7265abf487892dd68797756`。
  复拍仍为 `128/128` support／inliers、双侧 outlier=`0`，证明橄榄绿／粉／玫红／赭橙等宽色族
  外观在断电后继续保留。原图／复拍的相机相对 L* 曲线相关性为：CS1 row=`0.998217`、
  column=`0.645152`，CS2 row=`0.870076`、column=`0.896651`；这是持久结构证据，但同一物理
  布局复拍仍不能把 recipe 效应与位置／照明效应解混。最初同步采集命令还留下一个
  `camera-action-04-poweroff-repeat-01.capture.json`（SHA-256=`9d54a80550959490e86bcfb5d91c5ad6a8ef9fa9b8f973a6e5bb0ca1bffe7018`），
  其 `live_synchronized` 标签不符合复拍时序，故仅保留为不可变错误记录，不作为权威 temporal binding。
  两图派生的 `camera-action-04.colour-family-summary.json` 为 `53347 bytes`，文件 SHA-256=
  `deebdb7779e684f79a2a586544885f50073e50496c2b4de1c17730de6dfc6073`、canonical integrity=
  `c0bed599658e3447ebc8386d32c2d1abe972e0150ddfa046c130c4911b9b3455`；自动识别 CS1 为
  `yellow-olive-direction` 两个探索外观带、CS2 为 `red-pink-direction` 三个探索外观带。外观带
  数量不是颜色数量，最终状态仍为 `UNPROVEN_REPEAT_POSITION_CONFOUNDED`。
- fresh V2 containment application 的 app-only 写入和独立 verify 已 PASS：flash evidence
  SHA-256=`bfbd6799ca0bc16d81f67ee55addc137244452fb2d732364465b80e804572023`。随后 J2-OFF
  diagnose 因 host pack 与 firmware 的 `classification` 常量不一致，在 mutation 前 fail-closed：
  outcome=`j2_off_diagnostic_failed_no_claim`，固定为 `GET=4 / POST=0 / claim=0 /
  visible refresh=0`，diagnostic SHA-256=`67f906ce5821b3227ee5b03f74cb4ea81e96138e7eb3a333654972b768c916a7`。
  该 O_EXCL 失败记录不可覆盖；V2 containment 当前 **BLOCKED**，factory-OTP white action 不得 run。
- 离线审计后，冻结 host pack 已恢复到 SHA-256
  `461a1fd3635070ed52791f5f606ed6801c7fda5f1ea5956a2971e2dd1d29ec8c`；这不改变已经落盘的
  V2 diagnostic FAIL，也不赋予重试权限。下一步仅允许离线建立独立 identity／output root 的
  V3 successor，或离线开展两张相机照片的色族／置换复核；在新的可审计方案完成前保持 J2 OFF，
  不再执行设备网络、COM、relay、flash、reset 或 visible refresh。

## 2026-08-28 当前覆盖更新（优先于下方历史表）

- 现场已由操作者恢复上游 3.3 V，J2 当前保持 ON；ESP32 与红／粉明度 V2 应用保持同一
  boot nonce `1ffa520a2537168d`，设备为 `http://192.168.1.11`。本轮没有刷写、复位或改线。
- 真屏观察门已改为 **USB 相机采集 + AI／算法判读**；不再要求操作者肉眼裁决。当前斜视机位
  只标记 `partial_panel`，因此可记录入镜网格的异常或候选，但不得声称全屏 PASS、64 格
  无差异或合格新颜色。覆盖不足时结果为 `INCONCLUSIVE`，且不触发 retry/autochain。
- 红／粉明度 V2 已严格单步完成 ordinal 1–3，每步恰好一次 visible refresh，机器结果均为
  `complete_pass`。ordinal 1 旧白屏照片已按 `retrospective_unproven` 绑定；ordinal 2、3
  均有同步 1920×1080 JPEG 与不可覆盖 capture sidecar。AI 查看 ordinal 2/3 的完整可见网格，
  未见缺格或明显异常线，但面板边界未完整入镜，故仍为 `INCONCLUSIVE`。
- 当前屏幕保留 ordinal 3 `REDPINK_MIDDLE_GRID_COMMENTED` 网格；ordinal 4 尚未执行。
  派生报告器在 ordinal 3 后遇到一次纯离线签名升级错误，原 action/capture/photo 均已安全
  落盘且不得重做；修复后只允许离线重建报告，再决定是否单独执行 ordinal 4。
- 当前证据入口为
  `docs/MF1750_STAGE3_TARGET_HUE_REDPINK_BRIGHTNESS_V2_LIVE_RECORD_2026-08-28.md`；自动化规则见
  `docs/MF1750_AUTOMATED_CAMERA_TEST_EVIDENCE_2026-08-28.md`。

## 一眼状态

| 项目 | 当前值 |
|---|---|
| 现场安全状态 | **OPERATOR AWAY / RELAY COMMANDED OFF + INDEPENDENT QUERY OFF / SCREEN CLEAN WHITE / OFFLINE ONLY**。2026-08-27跨LUT局部HOLD V2五步闭环并由操作者确认最终“白色，干净”；随后COM14/channel1执行OFF且独立query仍为OFF。操作者已准备睡觉；此后禁止设备网络、COM、刷写、复位、刷新或继电器动作，仅允许离线代码、编译、测试和文档。继电器没有负载侧电压反馈，故`electrical_state_proven=false`。 |
| 现场运行方式 | **SUPERVISED SEMI-AUTOMATIC**：操作者在场时，允许助手使用已绑定继电器并按已明确的测试顺序半自动执行；每个需要判断颜色/画质的可见节点必须停在 `HUMAN_OBSERVATION_GATE` 等待操作者。操作者说要离开后不再开始新动作；若已有刷新进行中，先等其正常终态，再将继电器置 OFF，之后仅做离线工作。禁止隐式 retry/recovery/autochain、未经安排的刷写/复位/改线以及无人值守真屏动作。 |
| 目标色相目录 | **OFFLINE READY / 0 QUALIFIED COLOURS**。已建立13个照片有效色相族，首轮84个明度目标，长期256槽结构为250个“色相×明度×彩度/子簇”槽加6个自适应槽；这些都是搜索与调色板目标，不是已获得颜色。机器目录 catalog ID=`94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8`；现阶段只承认黑、白、黄、红、Blue-1、Blue-2、绿7个肉眼基础组，尚无canonical Lab唯一色计数。 |
| 色相/明度收集工具 | **OFFLINE READY / DERIVED QUALIFICATION ONLY**。`mf1750_hue_observation_collector.py` 可生成、校验和汇总绑定当前catalog与Blue 64-recipe的JSON模板，记录CS1/CS2、target-repeat、5/60/600s、Lab、三次独立run、HOLD和白恢复证据。输入不能直接声明qualified；缺任一门即保持候选，通过后也不自动计为唯一颜色。空模板=`64 candidates / 0 qualified / unique-colour unknown`。 |
| Blue明度首批固件 | **LIVE 6/6 PROTOCOL COMPLETE / 0 VISIBLE BLUE-BRIGHTNESS CANDIDATES / RUNTIME-WHITE VISUAL FAIL / QUALIFIED=0**。每控制器64条历史recipe；action4/5最终蓝矩阵左右一致、内部无肉眼差异。action3彩色中间态曾见深浅差异但未定位，保留为其他目标色线索。action6 runtime-code7 white 协议PASS但蓝矩阵完全保留，不能记clean white。主boot=`7de23beca3837011`，campaign complete/next7；专属fresh factory-OTP收容BIN=`786448/82e49e99...ea12f`仍未消费，是下次唯一首项。 |
| 红/粉明度 V1 | **OFFLINE FROZEN / INDEPENDENT AUDIT PASS / NOT FLASHED / QUALIFIED=0**。active code0为CS2红候选，CS1同码为橄榄/黄绿对照，不声称双控同色。每侧64个均匀单码历史recipe，无抖动/partial；factory-OTP白锚与正常白恢复，另有fresh独立白收容。主contract=`df7ecdc4...0278`，BIN/ELF=`801888/70952827...c07d8`、`13297008/72011ccb...8f8f`；收容contract=`10867bce...9020`，BIN/ELF=`787216/277ee416...d513`、`13214292/a6ea106b...c9db`。设备端持久first-boot nonce，setup/ARM/EXECUTE/dispatch四门同boot fail-closed；ordinal5还需显式“ordinal4见到候选”确认。 |
| 黄/橄榄明度 V1 | **OFFLINE FROZEN / INDEPENDENT AUDIT PASS / NOT FLASHED / QUALIFIED=0**。active code2为CS1黄/橄榄黄候选，CS2同码为鲑粉对照，不声称双控同色。每侧64个均匀单码历史recipe，无抖动/partial；factory-OTP白锚与正常白恢复，另有fresh独立白收容。主contract=`47cff189...4899`，BIN/ELF=`802208/7e45f52d...8563`、`13299612/5a8fabd6...5ae5`；收容BIN/ELF=`786544/80dfebbd...61ec1`、`13214132/4e846aca...e8e8`。同样具备设备端四层same-boot门，并额外在设备身份中绑定运行app ELF SHA。 |
| Blue专属白收容 | **LIVE COMPLETE / CLEAN WHITE CONFIRMED / CONSUMED**。app-only 写入及独立 verify PASS；J2-OFF 4 GET/0 POST/0 claim 诊断通过，随后唯一 factory-OTP white 完成，操作者确认 clean white，再关闭 relay。BIN/ELF=`786448/82e49e99...ea12f`、`13214100/d1e89562...16250`；action=`808d5fb9...838555` 已永久消费。其结果只收容 Blue campaign，不冒充颜色测试证据。 |
| 多目标历史筛选 V1 | **LIVE MAIN 1–8 COMPLETE / ORDINAL9 PRE-MUTATION REJECTED / CAMPAIGN SEALED / INDEPENDENT WHITE CONTAINMENT PASS / 0 QUALIFIED NEW STABLE COLOURS**。AB：source列基线正常；target行照片中的轻微空间差异不能与照明/透视可靠区分，同target repeat后人工确认无明显深浅变化。factory白分隔 clean。BA：source列基本一致；target行出现强纵向源历史色带，但相同target repeat后基本收敛为同行同色，故只证明一次刷新后的显著历史过渡态，不证明稳定跨LUT调色盘或新增合格色。ordinal9 在0 ARM/0 EXECUTE/0 claim/0 refresh前被 raw-ready `BUSY=1` 门拒绝；relay立即OFF，主序列不重试。独立收容 BIN/ELF=`786512/f6e943b3...d9f2`、`13214104/88ee12f6...8180` app-only写入/verify、fresh J2-OFF诊断、唯一factory白均PASS，操作者确认全白后relay OFF。主BIN/ELF=`799552/b1f25c89...cb1e`、`13286676/b48be696...bb216`；contract=`7f653cc9...958da`。 |
| 局刷底边诊断固件 | **FIXED CLEAN TRANSPORT PASS / SIX RECTANGLES CLEAN / GENERAL ROOT CAUSE STILL OPEN**。Endpoint与Guard方向假设均为视觉阴性；后续Fullframe-vs-PTLW V2已证明完整code7 SRAM预装、一次inclusive PTLW、crop DTM、`PON→DRF00→POF00`且PON后不重复PTLW，可让固定蓝ROI四边干净。2026-08-27该传输移植到跨LUT多窗口V2后，蓝、绿、黑共六格底边均无黑线，旧区不闪烁，最终factory白清除。结论仅限已测窗口/码/A→B→A profile链；旧黑线的最小单因仍未完全隔离。 |
| 当前离线验证 | **RED-PINK + YELLOW-OLIVE BRIGHTNESS V1 FROZEN / TWO INDEPENDENT AUDITS PASS / READY FOR FUTURE SUPERVISED J2-OFF PREFLIGHT**。原审计发现的host-only same-boot缺口已在两套device固件中修复；重启、containment后回主或direct exact POST均在driver前fault-lock。主代理对catalog、Blue邻接及两套main+containment最终快照联合复跑=`163 passed`；12文件Ruff/format/py_compile PASS；四个describe均为离线路径。红/粉23项与黄/橄榄25项SHA清单逐项重算0失败，清单自身=`c1668770...3eeb`、`1e660b9b...6271b`。今晚0设备网络/COM/relay/flash/reset/refresh。 |
| 连续性 | C20/T20/C23、dither atlas、照片算法、chroma-history 与 D1-512 历史结论继续保持。repeat-PTLW V3 boot=`679f614b3864b874` 5/5、旧cross-profile partial-HOLD boot=`04f47262e8236ded` 5/5、Blue brightness boot=`7de23beca3837011` 6/6、Endpoint A/B boot=`be596f0f974f95ab` 5/5、Fullframe/PTLW V2 boot=`22a0acda523dc334` 5/5、clean cross-LUT HOLD V2 boot=`9355f29a468dfc35` 5/5，均严格顺序且每action恰好1 ARM/EXECUTE/driver，无retry/recovery/autochain；Blue action6仍只记协议PASS/视觉白恢复FAIL，已由独立白收容闭环。 |
| 未消费的可见刷新边界 | 旧cross-profile partial-HOLD、Blue brightness及白收容、multi-target主序列及白收容、Endpoint、Fullframe/PTLW V2与clean cross-LUT HOLD V2全部已永久消费，不得重放。clean cross-LUT HOLD V2的ordinal1–5和boot=`9355f29a468dfc35` campaign均封口。红/粉与黄/橄榄V1及各自独立白收容均是未刷写、未运行的fresh离线产物；它们不是当前现场授权，操作者离场期间不得刷入。下次只允许先选择一套，经J2-OFF重哈希/app-only写入/独立verify/fresh四GET后，再逐ordinal人工放行。 |
| 当前实测固件 | **CLEAN CROSS-LUT HOLD V2 INSTALLED / CAMPAIGN 5/5 COMPLETE / SCREEN CLEAN WHITE / RELAY OFF**。app-only写COM8 `0x10000`及独立verify PASS；fresh J2-OFF诊断4 GET/0 POST/0 claim/0 refresh，boot=`9355f29a468dfc35`。严格完成factory白→active/code5蓝A→commented/code6绿B保持A→active/code3黑C保持A/B→factory白；五项均机器`complete_pass`、每项1 ARM/1 EXECUTE/1 driver/1 visible refresh，0 retry/recovery/autochain。人工确认蓝/绿/黑共六格左右正确、均无底边黑线，后刷时旧区未闪，最终白色干净。COM14/channel1随后OFF并独立query OFF。 |
| 固件 SHA-256 | 当前已安装clean cross-LUT HOLD V2：BIN=`816656 bytes / 9139c4d243287caba125a87d57a83684bd10647a5107c476b45aab36f7ae060a`，ELF=`13368436 / 683f4578a7e853bb72a704cb465a89546ae4f4f0118fbc59bde30ce74c7015ce`；contract=`d9059cd99c9442fcf5ad4d74c360aaa6f6f18737cd9d090e4fa21b53ad06948b`。五个result SHA=`bc3bdab0...b6e8/d88b1d4a...a562/25eb90ba...c993/1f647111...01c4/7f2d46c0...2261`；人工观察SHA=`9cad3a42...7c77`。 |
| V10 timeout 离线恢复计划 | **V2 EXACT-SURFACE BLUEPRINT PASS / PHASE-A ONE-VERSION TERMINAL SUCCESS / ATTEMPT PERMANENTLY CONSUMED / V10 PROTOCOL RESPONSE CONFORMANCE TRUE / RESPONDER IDENTITY+FRESH BOOT FALSE / PHASE B NOT GENERATED OR EXECUTED / STAGE A NOT SATISFIED**。用户逐字回传本轮 948-byte 授权词后，runner 于 `09:00:43.917 +08:00` 在有效 gate 内先 O_EXCL 物化 registry，再严格执行唯一一次 raw AF_INET GET `http://192.168.1.7:80/api/ec5/h3-matched-control-v2/version`。1 transport/1 write/146 bytes handed/1 complete HTTP response，status 200；response 2540 bytes（header 92、body 2448），body/canonical SHA=`f83519943cafabc2035ff5d4d33b4c918925a2652d4116b133d52be7c3795870`/`33ea4e0033485a05032993b278d4b0db9701cf378314ea8f0334654ea5b17e80`，exact V10 replay PASS。0 POST/body/claim/mutation/visible-refresh/Phase-B request/retry/fallback/recovery/autochain；wire emitted/peer received 仍按合同为 UNKNOWN，kernel TCP retransmission possible。registry 2753 bytes/SHA=`bc81e5772366b3f60a670336be8103ca32a37645c178f0889ebe72ce5f50c56d`；committed receipt 17889 bytes，file/canonical=`cb7c65c4f55069215cd638fac4b401421dd530cdabf263408fd5cc7d5fc57a94`/`75aabab5237bee098046173b72f56fb5293c5b0296e75588d0e92ecc3f119b00`，finalization temp absent；独立深验 `valid=true / terminal_success=true / may_request_separate_phase_b_authority=true / phase_b_generated_or_executed=false` |
| Phase-B P0/P1 历史支线 | V3 在过期前没有留下 registry/terminal/temp，随后被用户选择的直接 app-only 上机流程和多个新 boot 取代；不得恢复或复用旧 authority/token。当前分支的只读身份由 dither boot `027ed5c3c397f64a` 的已封存 diagnostic 提供，离场期间不再发 GET。 |
| WF23 C23/T23 路径 | C23 atlas 已唯一成功并观察为与 C20 相同；原 C23 white action 已 claim 且 DRF BUSY timeout，不能重试。独立 WF23 white containment 已恢复并人工确认 clean white，但严格 C23 control-leg 未 finalization，故 T23 仍不可释放。该路径当前冻结，不影响已完成的独立 dither atlas action。 |
| 十次核心色彩筛选 | 原十项排程不能按旧直线口径闭合：C20/T20 两对已完成，C23 atlas 已观察但原 C23 white 动作永久失败，T23 因严格前置证据不足冻结；独立 containment 不冒充 T23 evidence。dither atlas 的 protocol、三张原图、70-ROI 分析、人工 observation 及独立 ordinal2 white 均已完成。七行空间混色外观为橙/赭黄、浅黄、黄绿/橄榄、紫/靛、棕、青绿/蓝绿、粉红；不证明新单像素颜料色或 waveform/LUT 新色。不得把 containment 或 dither 结果补写成 T23 evidence。 |
| 像素抖动备选分支 | **CURRENT-SOURCE ISOLATION + FIXED BIN/ELF + STAGED RELEASE PASS / ATLAS WHITE PREREQUISITE NOW PRESENT / NOT LIVE-AUTHORIZED**。完整语义仍为 `比例色块→white→七组连续渐变→white→综合效果图→white`；已消费的 atlas 不得重放。扩展专用 BIN/ELF=`031c31ba...66b1`/`a6a1c488...f93d`，V2 staged release file/canonical=`14bc3568...6d5a`/`62fd222e...a03a`。ordinal2 clean-white result+observation+claim 现已存在，但旧 staged release 本身仍为 `execution_eligible=false/live_authorized=false`；若未来继续，须先离线重放并生成新的 real release，再由用户另行选择，不得从当前白屏自动串行。 |
| 阶段二/三新执行计划 | **STAGE II CLOSED / FIXED CROSS-PROFILE A→B→A LOCAL HOLD + CLEAN EDGE PASS / BRIGHTNESS SEARCH NEXT**。clean V2同boot完成factory白→蓝A→绿B保持A→黑C保持A/B→factory白；旧区未闪、六格四边干净、最终白恢复通过。范围仍只限固定窗口、code5/6/3与active→commented→active序列，不外推到任意LUT/窗口或256色照片。下一阶段按目标色分别筛单像素历史明度：红/粉优先，黄/橄榄其次；视觉无差异即结束该目标，有差异才做左右复核/重复/标定。 |
| 当前硬件结论 | 已证明的范围是：(1) same-profile固定三窗口局部保持；(2) active→commented全屏历史依赖；(3) 固定A→B→A global-header切换下蓝/绿/黑三ROI可局部共存，旧区不闪，六格边缘干净，最终factory-white可清除。不能外推到任意LUT/码/窗口、长期保持或256色。Blue 64-recipe最终target/repeat全部肉眼一致，未发现蓝色明度级；其他目标明度尚未上屏。PON相关性仍维持：近期raw BUSY=1样本成功，三个独立raw0 attempt均PON 60.010 s超时，因此fresh admission继续raw0 fail-closed。 |
| 算法结论 | Q1 Atkinson `4/5/5/4/3/5`；Q2 blue-noise `2/1/1/1/1/1` visual FAIL；Q3 multicolor-DBS `4/4/3/4/4/4` PASS；Q4 overlap-aware DBS `4/4/3/4/3/4` PASS。独立同 crop/1:1 三列真屏复核给出 **Q1 > Q3 > Q4**：Q1 斑点更少，Q3 相对 Q4 对比度更强；Q1 成为 engineering preferred candidate，不回写原 N2 gate |
| 艾利尔照片真屏 | 已完成三案：Atkinson（Job/Op 1/1）被判“面部颗粒感太强”；multicolor-DBS 262k（2/2）被判“颗粒感更加严重”；face-smooth B（3/3）被判“效果太差、面部失真”。三次协议均通过但人工视觉均失败，各自授权永久消费，不得重跑。face-smooth B manifest/frame=`d24f6ae7...7519`/`e42b8227...aa21`，attempt=`a3aaba92...57c`。随后标准全白 frame SHA=`91f1ed45...8453d`、FNV=`0x13340DC5` 在 Job/Op 4/4 成功，人工确认无图像/色斑残留。 |
| D1-512 实测闭环 | **APP-ONLY FLASH+VERIFY PASS / 5 OF 5 ACTIONS COMPLETE / PHOTO ANALYSED / J2 OFF**。每半屏 `11×24`、全屏 528 ROI=`512候选+16参考`，固定 `white baseline→source→mid→target→white recovery`；没有 partial、dither、未知 LUT/`0x86`、刷新中切电或 SPI sweep。BIN=`789456 bytes / ffa6e082c3763dc22207a2565b1b47f81014d5fd93b8c5cd1a60636ea362b59b`、boot=`b85f791f320b92ea`。操作者对 target 的原话为“无序的排列，但是似乎没有发现新的颜色”。3024×4032 原图=`3882233 bytes / f3266e53...6957`；透视校正 528-ROI 相机相对分析仅留下 4 个弱候选，全部属于既有蓝色族 target5/7：recipes `493(7→5→5) / 207(3→1→7) / 173(2→5→5) / 13(0→1→5)`。因此本轮 **未确认新色相或新的合格单像素状态**；四项只保留作色卡条件下的窄范围复测。 |
| 当前下一步 | **OFFLINE HOLD UNTIL OPERATOR RETURNS / RED-PINK FIRST, YELLOW-OLIVE SECOND**。保持当前clean cross-LUT固件、干净白屏与relay OFF，不再访问设备。操作者回场后先确认J2 OFF，只刷红/粉冻结BIN并独立verify/fresh四GET；逐步执行白锚→source→middle→target。若ordinal4无明确同行差异，立即封存主序列，禁止ordinal5/6，relay OFF后刷fresh红/粉白收容并转黄/橄榄；若有明确差异，才显式释放ordinal5复核，接受后执行ordinal6白恢复。黄/橄榄完全同一快速门。可靠性、5/60/600 s及色卡标定只对命中候选开展。 |

> `2026-08-26 00:22 +08:00` 操作者恢复上游3.3 V后，relay先独立query为OFF；最终冻结的
> PON/POF no-DRF qualifier V2 BIN=`788736/0af84715...fdec`只写COM8 app `0x10000`，
> esptool写入内建hash及独立`verify_flash`均PASS，未擦bootloader/partition/NVS。J2-OFF
> 4 GET/0 POST诊断exact PASS，boot=`abd7b455cbaf8671`、0 claim/driver/visible；diagnostic=
> `12671 bytes / b57dd415...9b61`。随后relay唯一切ON，V2资格四个REV样本（CS1×2、CS2×2）
> 全部exact=`01 01 04`，5 reset、最终BUSY=1稳定50 ms；同boot唯一1 ARM/1 EXECUTE/
> 1 driver完成PON=`180 ms`→POF=`210 ms`，总driver=`7563 ms`，sequence PASS。0 DTM/DRF/
> LUT/PTLW/0x86/visible-refresh、无retry/recovery/autochain；首次终态report GET遇到一次
> WinError10054，随后仅只读GET取得same-boot COMPLETE，没有重发qualify/ARM/EXECUTE。
> result=`45075 bytes / 7a1bc718...4435`，claim/qualification-attempt/reserve=`1092 /
> e7467daf...4cf6`、`983 / c758ff54...48a4`、`503 / cd2c147c...66e8`。relay随后立即OFF并
> 独立query为OFF。V2与先前V1 attempt均永久消费；本次无可见刷新，白屏现场复核待操作者回传。

> `2026-08-26 06:56 +08:00` 操作者补充原话“屏幕全白干净，无异常”，完成V2资格动作后的
> 人工现场复核；该观察只确认无可见污染，不扩大为DRF或A/B处理证据。relay保持commanded
> OFF。开始离线建立fresh Fullframe-vs-PTLW V2 successor；旧V1/V1B及资格V2均不重放。

> `2026-08-26 07:57 +08:00` fresh Fullframe-vs-PTLW V2 replacement完成离线封印并通过独立
> 红队。唯一contract=`8ca2c5df...7111`、qualifier bundle=`4f10da14...968f`；root独立clean
> build复现BIN=`815600/0433f678...63c4`、ELF=`13362920/17abc695...9b85`。新增18项持久化
> firmware审计，与20项host专项、V1B机械和qualifier V2组合共`73 passed`；Ruff、py_compile、
> dry-validate、describe、ELF新旧identity scan均PASS。独立红队进一步验证future-claim路径
> collision、O_EXCL reservation、current-claim原始SHA、递归prior链、fresh/later BUSY分域、
> four-GET salvage跨surface一致及post-claim异常收据。旧`277370...`/`5770499c...`中间候选
> 从未刷写并永久作废。本节点0硬件/网络/COM/relay访问；现场仍按最后独立query为OFF、人工
> 全白干净无异常记录，且`electrical_state_proven=false`不变。

> `2026-08-26 08:03 +08:00` 精确replacement BIN只写COM8 app `0x10000`，esptool内建hash与
> 独立verify均PASS，同一ESP32-S3 rev0.2/MAC=`a4:cb:8f:d9:fc:d4`；写入前后relay均query
> OFF。J2-OFF 4 GET诊断PASS，boot=`22a0acda523dc334`、fresh key absent/next1、0 POST/claim/
> driver/refresh；diagnostic=`32997 bytes / 8511c438...7213`。随后relay唯一ON，ordinal1
> factory-OTP白恰好1 ARM/1 EXECUTE/1 driver COMPLETE：host/ARM/EXECUTE/DISPATCH BUSY全1，
> qualifier CS1/CS2四样本全`01 01 04`、5 reset、final high 50 ms；driver PON/DRF/POF=
> `181/22521/141 ms`，总`35012 ms`，safe-finish=`1/1/1`，0 retry/recovery/autochain。
> result/claim/reserve=`48566/ffd56224...c8ee`、`3033/69ad91af...5eb6`、`2131/
> 585da7e7...b4fe9`；staging absent。relay立即OFF-with-feedback/query OFF。当前只等待操作者
> 对最终全白、灰边、底边线、中心接缝和其他异常作人工裁决，不得自动释放ordinal2。

> `2026-08-26 08:06 +08:00` 操作者明确“我已经离开，断开继电器，晚上我回去查看”。该回传
> 只建立离场与物理断开安全停点，不冒充ordinal1最终画面的人工PASS。今晚返回前冻结所有
> 设备网络、COM、刷写、复位、刷新和relay动作；ordinal2继续未消费，ordinal1不得重放。

> `2026-08-24 02:00 +08:00` 完成目标色相与首批明度测试离线封版。机器目录固定13个
> 色相族、84个首轮目标及256槽长期结构，catalog=`94eabf2...65fd8`，但合格色仍为0。
> Blue V1 每控制器64条无抖动历史recipe，主BIN=`795376/afc978e1...a93d56`；独立白收容
> BIN=`786448/82e49e99...ea12f`。Endpoint crossover主/收容BIN=`796864/5c339268...
> 404e8`、`786416/7580b952...4102d`，用于诊断而非宣称修复。新增collector以显式Lab、
> 三次重复、5/60/600s、HOLD和白恢复证据派生资格，不能人工直接写qualified。四环境独立
> clean build，联合147 tests、Ruff/format/py_compile、仓库外describe均PASS；三条收容源码
> 已隔离，旧cross收容精确恢复封存af13/287且未重绑。本轮0硬件访问，现场仍保持上游断电、
> relay OFF、屏幕白。

> `2026-08-24 00:52 +08:00` 今天两条阶段三实测已安全收口。第一条 repeat-PTLW V3
> 在同一 active global-header profile 下完成 factory-OTP白→code3暗A→code5蓝B→code6绿C
> →factory-OTP白，5/5 complete，boot=`679f614b3864b874`，BIN=`796496/
> 81a0e6ac...57da4`；后一区域刷新时旧区域未闪烁，最终黑/蓝/绿共存，证明指定窗口和码的
> same-profile local HOLD 初步成立，但色块底边黑白齿/线仍在。第二条修复 packed-DTM fixture
> 自检后，AB 全屏 8×8 cross-profile matrix 5/5 complete，boot=`315e5dd117432501`，BIN=
> `793840/e56649be...573ca`；target matrix 未塌缩成八条均匀色带，红/粉、黄绿/橄榄等源历史
> 分段在 identical target repeat 后部分仍可见。该结果只证明 global-header profile 的全屏历史
> 依赖，不含 PTLW/local HOLD，不计为64/128/256种新色。AB evidence=`.test-output/hardware/
> MF1750_RUNTIME_LUT_CROSS_PALETTE_AB_20260824_V1/`；最终白恢复 device COMPLETE，操作者确认
> 刷白后关闭上游电源；relay COM14/channel1 commanded OFF 并独立 query OFF。下一步为 fresh
> `A局部→B局部并HOLD A→回A局部并HOLD A/B→factory white` 独立固件，详见
> `MF1750_STAGE3_CROSS_PALETTE_LOCAL_HOLD_PLAN_2026-08-24.md`。

> `2026-08-23 08:57 +08:00` V3 common-white 与独立收容闭环。用户开启上游电源后，relay
> query 先确认 channel1 commanded OFF；app-only 刷入 V3 BIN `793360/52a46202...a1649e`，
> 独立 verify PASS。fresh diagnostic=`172f255d...e2d`，boot=`2057fbdab7141c74`，4 GET/
> 0 POST/0 claim/0 refresh。relay ON 后 ordinal1 code7/code7 唯一执行，设备 COMPLETE、
> 1 ARM/1 EXECUTE/1 driver、46,580 ms、无 retry/recovery/autochain；result/claim=
> `d27e617f...0791f`/`887489b7...f0fd`。操作者观察仍为“左黑右白”，故 V3 FAIL，ordinal2–5
> 全冻结。relay OFF 后 app-only 刷入独立 factory-OTP containment BIN
> `785936/33f7fb6c...6a569` 并 verify PASS；首次 run 在0 POST/0 claim/0 refresh前因历史 WF23
> prior-claim门安全拒绝。主机 facade 随后只改为精确绑定本次 V3 claim+COMPLETE result，
> 7项专项及最终联合25 tests、Ruff、py_compile、describe PASS；未改设备固件。fresh diagnostic
> SHA=`d7fe4072...ebf6`，boot=`e9e8d60919f2feeb`；relay ON 后唯一 white action success，
> 1 ARM/1 EXECUTE/1 visible refresh、无retry/recovery/autochain；result/claim=
> `57392a20...33bd`/`4c1147d7...9212`。操作者确认“白了”，observation=`1883d2d3...bef5`；
> relay 随即 commanded OFF，屏幕保持全白。

> `2026-08-23 09:15 +08:00` 在 containment 白屏与 relay OFF 状态下完成控制器独立码位
> 映射 V1 的离线实现。为避免历史 reference 产物漂移，新建独立 main/driver/identity/
> candidate 与 PlatformIO 环境；CS1 依序 code0..7，CS2 反序 code7..0，一次全局刷新输出
> 16个 `controller/profile/code` 大纯场，不含partial/dither/未知命令/retry/recovery/autochain。
> BIN/ELF=`797616/c72f7e11...a055`、`13268252/2e70784b...36a7`；新映射+历史 reference
> 定向10 tests、Ruff、py_compile、describe PASS。当前尚未刷入该固件、没有 mapping refresh；
> 设备仍运行 containment white app，relay OFF，屏幕保持全白。

> `2026-08-23 11:02 +08:00` controller-code-map 已完成真屏与离场安全收口。relay OFF下
> app-only写入 `797616/c72f7e11...a055`，独立verify PASS；fresh diagnostic=`7de8123c...
> f10bfae`、boot=`221840381a8183a6`、4 GET/0 POST/0 claim/0 refresh。relay ON 后唯一 atlas
> action success，1 ARM/1 EXECUTE/1 refresh、无retry/recovery/autochain；result/claim=
> `2bb5fc8b...0bccf`/`7259b19c...d52c`。操作者上传照片 `354874/679e4769...17c2` 后离场；
> 助手检测relay仍ON，立即command OFF并独立query OFF。照片映射为CS1/CS2共享 code5蓝、
> code6绿、code7白；code0/1/2/4明显不同，code3仅同属暗色。observation=`7cb31d67...132e0`。
> 离场后仅完成隔离V4：整屏白改用atlas实测packed-frame传输，局部窗口保持原0x83路径；
> BIN/ELF=`793728/e3315ba1...ad9c`、`13270560/61f1bee8...e09a`，联合33 tests与静态检查
> PASS。V4未刷入/未执行，当前设备仍为map app、relay OFF、屏幕保留映射图。

> `2026-08-23 13:36 +08:00` 完成局部刷新样例深审与晚间多路线离线批次。可执行 `.ino`
> 在每次 partial 前 `EPD_init()`，发送 `0x83` 包含式窗口和裁剪 `0x10` DTM，再执行
> PON/DRF/POF；其 `0x10` 后额外 `0x00` 与 SPD1657A 手册不符，按首像素数据处理，未移植。
> 手册 PTLW 明确窗口内外 gate 都扫描，故已观测“定位正确、旧蓝灰化”继续定性为
> addressing PASS / universal HOLD FAIL。新增V5累计整帧控制：BIN/ELF=`793264/
> fdb9852a...068`、`13266028/36ad9671...11d`；新增V6双向8×8跨盘矩阵，AB BIN/ELF=
> `793936/bb1ce7b7...bd0d`、`13269080/63308d91...cb2d`，BA=`793920/bcfbac65...b371`、
> `13269036/c0087626...a92e`。V4/V5/V6定向联合20 tests、Ruff、format、py_compile、AB/BA
> describe PASS。全程0 relay/device-network/COM/serial/flash/reset/refresh；设备仍为map app，
> relay OFF，屏幕静态保留16-field map。

> `2026-08-23 17:57 +08:00` 完成局部刷新严格补充审查。精确手册再次确认：BUSY_N=0
> 时写命令不可用、PTLW必须完整9-byte且PMODE=1、3-bit DTM在0x10后直接发送每字节两像素、
> POF在VDD不断时保留寄存器和SRAM，以及partial期间窗口内外gate均扫描。另发现第18页水平
> 低两位表述与第32页完整10-bit默认HRED=799相冲突，故只把even-x/even-width列为已证明
> native packing合同，4-pixel粒度保留为保守选择而不冒充硬要求。当前GxEPD2相邻实现明确
> partial可用但不快速，partial/full均15000ms；其writeNative与refresh(window)也证明RAM staging
> 可与可见DRF分离。新增严格审查文档和源码合同回归，Gx audit `5 passed`、V4 `6 passed`、
> Ruff PASS；未改固件BIN，0 relay/device-network/COM/serial/flash/reset/refresh，现场状态不变。

> `2026-08-22 00:05 +08:00` H20/H23 discovery-first 已安全收口。H20 treatment/white
> result canonical=`c1491121...54fd / b4924b29...0426`，人工 `no_new_color`；H23 treatment
> result canonical=`f1c1b212...9cae`，人工观察仍为条纹，刷新过程中疑似短暂橙色只保留为
> transient lead，不记作可用于静态照片的均匀稳定新色，裁决 canonical=`952b9b31...e393`。

> `2026-08-23 07:21 +08:00` L535+PTLW 基线纠错与离场离线收口。V1 code3 ordinal1设备端
> COMPLETE，但操作者观察“全屏幕黑”；V2用新NVS/action改为code1，J2-OFF diagnostic
> virgin PASS，app-only write+独立verify PASS，唯一ordinal1设备端COMPLETE、1 ARM/
> 1 EXECUTE/1 driver、46,589 ms、sequence/mapping/PON/DRF/POF PASS。宿主首个终态GET因
> listener重启收到WinError10054，未重发mutation；relay OFF后GET-only确认READY/next2/
> no-retry/no-recovery。操作者观察“目前是左黑右白”，故V2物理门FAIL、remaining actions
> 全冻结；随后操作者关闭上游电源。combined observation=`.test-output/hardware/
> MF1750_RUNTIME_LUT_PARTIAL_HOLD_BASELINE_OBSERVATIONS_V1_V2_20260823.json`。离线V3据
> 16大纯场布局改用共同白候选code7，并选择跨控制器较一致的code3/5/6作黑/蓝/绿局部块；
> build/绑定完成，并补建fresh-NVS独立factory-OTP containment；最终 containment BIN/ELF=
> `785936/33f7fb6c...6a569`、`13213772/224e5b57...005d`，专用 translation unit 与历史白
> 入口隔离；历史 lga-white BIN 仍精确为 `786016/caa54089...747c`。V1/V2/V3/containment/
> reference 联合24 tests、Ruff、py_compile、两个describe全部PASS。断电后0 relay/network/COM/flash/
> reset/refresh。
> H23 独立 white result canonical=`48a7c49f...0426` 后操作者确认全白，relay 随后 OFF-with-
> feedback/query OFF。操作者现进一步明确断开驱动板电源并离场、ESP32 保持在线，要求批量完成
> 后续离线代码；从此节点起 0 relay/device-network/COM/serial/flash/reset/refresh。

> `2026-08-22 01:10 +08:00` 按“先完成部分 HOLD 离线、再转 LUT”完成两条离线分支。
> exact-chip 本地 `E2802-SPD1657_OTP.h` 只证明 `PTLW=0x83`，参数语义由同款 GDEP073E01
> 官方指定区域样例和固定版本 GxEPD2 交叉支持，仍标为 experimental 而非公开寄存器合同。
> HOLD 三环境均构建 PASS：accumulate/edges/cs-split BIN=`787984/a57dab79...e1dcb`、
> `787952/1c95fe06...519f`、`788160/95ca7ad1...da3b`；相关回归8 passed、Ruff/py_compile PASS。
> LUT pure-field `M0/H1/H2/H3 × H20/H23` 与各自独立白恢复共16环境全部构建 PASS；V2 release
> canonical=`8bef96bf...0da1`，驱动 source binding=`f4bc8467...3272`，pack/runner回归12 passed。
> HOLD+LUT 最终定向统一回归20 passed，Ruff/py_compile PASS。
> 当前仍为0 relay/device-network/COM/serial/flash/reset/refresh；真屏只先从 HOLD accumulate 开始，
> HOLD 证明前不释放“partial + runtime LUT”组合，也不自动串行后续 LUT 候选。

> `2026-08-22 03:12 +08:00` 按用户要求将相近芯片与公开组合纳入“约束证据”，但以 exact-chip
> 本地资料为第一优先。`E2802-SPD1657_OTP.h` 明确 R20/R21/PTLW 地址，legacy `EDP_init.c`
> 提取出活动与完整注释两份535-byte表；活动/注释表 SHA 分别为 `716cc229...e44b`、
> `2cf66c2b...d26`。新增 reference-first 两屏：CS1/CS2 分别保持两份完整表，只切换共享
> active/commented header，code固定0..7；共32端点、2次treatment+2次独立白恢复。实现沿用
> 已验证双控制器安全骨架，并未复刻 legacy 全初始化或启用其他命令。reference 4/4环境构建
> SUCCESS；共享源码更新后原 pure-field 16/16全部重建 SUCCESS；定向联合测试95 passed，
> Ruff/py_compile PASS。reference V4/pure-field V3 release canonical=`895d4954...bba5`/
> `9797abb4...620c`，共享驱动 source=`b7da0a24...9749`。当前准备总量为10个treatment/
> 160端点/10个独立白恢复，理论 byte 空间只记录不穷举；H1/H2降为最后层，未知命令、
> category/record/byte拼接、code8..15、VCOM/高压扫描、刷新中断电继续禁止。本轮全程0 relay/
> device-network/COM/serial/flash/reset/visible refresh；现场断电、全白、ESP32在线的离场状态未改。

> `2026-08-22 07:23 +08:00` 操作者返回、开启上游电源并重新授权助手控制 J2。relay discovery
> 与原 COM14/channel1 identity 完全一致，初始 query OFF。HOLD accumulate BIN=`787984 /
> a57dab79...e1dcb` 仅写 app `0x10000`，write hash 与独立 verify PASS；同一 ESP32-S3 rev0.2/
> MAC=`a4:cb:8f:d9:fc:d4`，未擦其他分区。J2-OFF 四 GET diagnostic strict PASS：boot=
> `f98b7300227fd094`、fixture PASS、key absent、READY/next1、BUSY=0、0 POST/driver；diagnostic
> file SHA=`5b9af69c...7d0a`。随后 relay ON-with-feedback/query ON，只提交 ordinal1 factory-OTP
> white baseline 的唯一 ARM/EXECUTE。同步刷新期间首个 report GET timeout，未重发；25秒后两次
> bodyless只读回查证明 terminal COMPLETE/result=true、1 ARM/1 EXECUTE/1 driver、sequence/
> mapping/PON/DRF/POF PASS、34194 ms、READY/next2。permanent claim SHA=`28de74b4...d1d1`。
> 当前 J2 commanded ON，停在人工白基线观察门；ordinal2尚未释放，0 retry/recovery/autochain。

> `2026-08-22 08:08 +08:00` 原 accumulate PATCH_A 曾使窗口外出现白→浅蓝渐变，
> 因此在 J2 OFF 下新建并仅 app-only 刷入 accumulate-vmirror：CS1 原 y，CS2
> `y′=600-(y+h)`，且 `0x83` 窗口命令改为按控制器分别写入。BIN/ELF=`788096 /
> 8c0ca2bd...bee5c` / `13246972 / 442b2a6b...d0f3`，app write+独立 verify PASS，boot=
> `156caaa71c9b3936`。ordinal1–4 均唯一 COMPLETE：white 全白；PATCH_A 两红格上下镜像、
> 背景全白；PATCH_B 两红格保留且各新增一蓝格；PATCH_C 红格内嵌绿色定址成功，
> 但窗口外旧蓝格在 CS1/左侧变灰、CS2/右侧呈渐变。助手立即 relay OFF。离线核对
> 证明 B/C 矩形不重叠，PATCH_C 每控制器恰写 `96×80/2=3840` bytes，DTM hash/
> sequence/mapping/PON/DRF/POF 均 PASS，预期帧仍含蓝色 code5。因此当前最强判定为：
> 局部定址有效，但普通原厂 OTP 全局刷新中窗口外并非对所有颜料状态都是零场 HOLD；
> 蓝色对后续刷新且对 gate/scan 位置敏感。这是 **addressing partial pass / universal
> HOLD fail**，不是简单坐标覆盖，也不支持环境光作为主因。当前 J2 OFF，ordinal5 白恢复尚未执行。

> `2026-08-22 08:33 +08:00` 为直接检验“镜像计算错误”假设，在 J2 OFF 下新建
> accumulate-symmetric-v2：两控制器使用完全相同的 A/B/C 坐标，同时保留两个 CS
> 分别写入 0x83，使“垂直镜像”成为唯一被移除的变量。五环境 build PASS，定向回归
> `10 passed`、Ruff PASS；新 BIN/ELF=`788080 / 24c73a9a...0385e` / `13247236 /
> 8353a17b...65ae`。relay 二次确认 OFF 后仅 app-only 写入 `0x10000`，write+独立 verify
> PASS；J2-OFF 四 GET diagnostic strict PASS，初始 boot=`83bb2628e78e1ed5`、READY/next1/
> key absent/0 driver/0 refresh。随后 white/PATCH1/PATCH2/PATCH3 均只发送一次 ARM+EXECUTE。
> 每次刷新使 HTTP listener 丢失，所以在屏幕完成且 J2 OFF 后仅复位 ESP32，用持久 NVS
> 递进 `next2→next3→next4→next5` 证明各 action 已完成；没有重发 mutation。操作者在
> PATCH2 确认“红蓝 ok”；PATCH3 后观察到红绿边界靠下侧白缝不连续/不等距，
> 其余三边等距；蓝色逐渐隐去、最终呈灰。PATCH_B 固定传输码为 code5，根据 C20/C23
> 真屏映射它是第7种独立颜色 Blue-2；Blue-1 为 code4，code7 也呈 Blue-1。
> 因此对称对照排除垂直镜像计算错误作为 Blue-2 褪灰主因；下边单边异常则把
> exact-chip 未公开的 y-endpoint/scan-boundary 语义提升为下一个独立候选。最后 relay
> OFF，当前 boot=`87e2503264e8e1a4`、READY/next5，未执行白恢复。

> `2026-08-22 09:05 +08:00` 操作者明确离场并要求先建立离线解决方案，晚些返回后再上机。
> 离场后新增两个完全隔离的单变量环境：`accumulate-symmetric-y-inclusive` 只把 0x83 的
> `y_end` 由 `y+h` 改为 `y+h-1`，PATCH_A/B/C 仍为 red/Blue-2/green；
> `accumulate-symmetric-blue1` 保持原 `y+h` 和全部几何，只把 PATCH_B 从 code5/Blue-2
> 改为 code4/Blue-1。两者各固定 `white→A→B→C→white` 五动作，独立 NVS/identity/
> claim，无 retry/recovery/autochain。针对长时间同步刷新阻塞主循环造成 listener 丢失，
> partial-HOLD 固件现在会在动作报告发布后重启 HTTP listener；runner 同时强制首次终态轮询
> 不早于40秒。该修复仅离线验证，尚未在真机宣称通过。
>
> 七个 partial-HOLD 环境全部离线重建成功；新 `y-inclusive` BIN/ELF=`788208 /
> 65d11932...d58b` / `13247936 / 0b542ab9...308a`，新 `Blue-1` BIN/ELF=`788176 /
> b09dec89...d258` / `13247928 / f0d375ec...a6c5`。共享 HTTP 修复也使其余五个离线产物
> identity 更新，但当前设备仍明确运行旧 symmetric-v2 BIN=`24c73a9...0385e`，没有被刷写。
> matrix+runner 定向回归 `14 passed`，Ruff/py_compile PASS；两个 runner describe 均 exact
> bound。全过程 0 relay/device-network/COM/serial/flash/reset/visible refresh，物理状态仍为
> J2 OFF、保留 PATCH3 静态图、旧 namespace `READY/next5`。

> `2026-08-22 15:33 +08:00` 完成局部刷新实现的精确资料复审，全程0 relay/
> device-network/COM/serial/flash/reset/visible refresh。新增冻结源 `tmp/SPD1657A_Rev1.0.pdf`
> （44页，SHA-256=`29F9C4E2E9CBD6D1AAA4622DF4D2ECAC8A51A205701A616A96104D03659B89D0`）。
> 手册明确 PTLW `0x83` 的 A/B/C/D 为10-bit起止地址、E[0]为PMODE，终点默认799/599
> 证明为包含式；PMODE=0关闭partial，PMODE=1启用partial；partial时窗口内外gate均扫描。
> 与 Good Display 相邻官方样例 `x+w-1/y+h-1` 一致，推翻了从 GxEPD2 相邻面板复制的
> `y+h` one-more workaround。代码审查确认当前双CS、ROI DTM `w*h/2`、3-bit packed pixel、
> common PON/DRF/POF、master BUSY及1MHz骨架正确；无需复制相邻样例在DTM前的可疑额外
> `0x00`。工程结论更新为：`y-inclusive` 是正确几何修正；Blue-2远端褪灰仍是窗口外参与
> gate/VCOM历史导致的状态保持问题，不能由一行越界解释。详细记录见
> `docs/MF1750_STAGE3_LOCAL_HOLD_REFERENCE_AUDIT_2026-08-22.md` 第10–13节。

> `2026-08-22 15:52 +08:00` 补齐最终 code4 对照并完成离线上机准备，0 relay/
> device-network/COM/serial/flash/reset/visible refresh。新增 variant7
> `ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1`，与 code5 variant5 共享正确 `y+h-1`，仅
> PATCH_B 由 code5 改为 code4；独立 NVS=`ph_yinc_b1_v1`、5个不可重放动作、无retry/
> recovery/autochain。同步修正 variant5 HTTP manifest 的 endpoint contract，使执行与声明均为
> `ye=y+h-1`。八环境全量 PlatformIO build SUCCESS；最终定向 pytest=`15 passed`，Ruff/
> py_compile PASS，两组 runner describe 均 exact-bound/live_authorized=false。code5 BIN/ELF=
> `788224 / 503519a1b9a9a66f1b845b5da8ef0d83b03e923ba747596e8ef311e6cb73fdd9` /
> `13247936 / 752becee2bcdf2ceb41a0bfdf711dcc02ec50d92fed2e8c73c275fae4e5a0aea`；
> code4 BIN/ELF=`788256 / 64a6102e53abaf010ad0ea7b5679c62fc17e627251a8a649b8d0540779dda71a` /
> `13247936 / 8f4cf3a4d2186671e344d2b071c95b0b2c50c2d41bd295bc78806769b7edf7a9`。

> `2026-08-22 20:46 +08:00` 操作者返回并授权继电器控制。COM14/channel1 query OFF 后，
> 在J2 OFF下将 code5 y-inclusive BIN=`788224 / 503519a1...fdd9` 仅写入 COM8 ESP32-S3
> app `0x10000`；write内建hash与独立verify digest均PASS，同一rev0.2/MAC。GET-only诊断
> `4 GET/0 POST/0 refresh` PASS：boot=`336cc306eda24ae4`、manifest明确`ye=y+h-1`、
> fixture PASS、key absent、READY/next1、BUSY=0。relay随后ON-with-feedback/query ON，
> ordinal1只发送1 ARM+1 EXECUTE；35,024ms后terminal COMPLETE，mapping/sequence及PON/DRF/
> POF BUSY证据PASS、1 driver、NVS READY/next2、0 retry/recovery/autochain。当前保持J2 ON，
> 停在全白人工观察门；ordinal2尚未释放。

> `2026-08-22 20:51 +08:00` 操作者确认 ordinal1 后屏幕全白。relay query仍为ON，未切换
> J2；ordinal2红色PATCH_A只发送1 ARM+1 EXECUTE，30,464ms后terminal COMPLETE，输入帧/
> 两路ROI DTM hash、mapping/sequence及PON/DRF/POF BUSY证据均PASS、1 driver、NVS
> READY/next3、0 retry/recovery/autochain。当前J2 ON，停在红格、背景与四边白缝人工观察门；
> ordinal3尚未释放。

> `2026-08-22 20:57 +08:00` 操作者确认 ordinal2 显示两个红格后，ordinal3 code5/经验
> Blue-2 PATCH_B 只发送1 ARM+1 EXECUTE，30,465ms后terminal COMPLETE；操作者确认“增加了
> 两个蓝色”，记为局部新增蓝格人工 PASS。随后 ordinal4 绿色 PATCH_C 同样只发送1 ARM+1
> EXECUTE，30,220ms后terminal COMPLETE，输入帧/两路ROI DTM hash、mapping/sequence及
> PON/DRF/POF BUSY证据均PASS、1 driver、NVS READY/next5、0 retry/recovery/autochain。
> ordinal3/4 result file SHA分别=`c1ee69e8...f3d8f5 / d517fc40...7de79f`。当前J2 ON，
> 保留红/蓝/绿累积图，停在ordinal4人工观察门；ordinal5白恢复尚未执行。

> `2026-08-22 21:01 +08:00` 操作者确认 ordinal4 后两个绿色出现；红绿边框下侧为等间距
> 黑白间隔线，但此前的两个 Blue-2 格已变灰。由此确认 ordinal3 的输入确为 code5/经验
> Blue-2，但其状态未跨 ordinal4 全局刷新保持；本组仍为地址局部 PASS、通用颜料 HOLD FAIL。
> 用户要求继续尝试其他颜色，下一动作限定为 ordinal5 全白恢复，再转 code4/Blue-1 对照。

> `2026-08-22 21:02 +08:00` code5 `y-inclusive` ordinal5 全白恢复只发送1 ARM+1 EXECUTE；
> 34,203ms后terminal COMPLETE/campaign_complete=true，输入白帧/两路DTM、mapping/sequence及
> PON/DRF/POF BUSY证据均PASS、1 driver、NVS READY/next6、0 retry/recovery/autochain。
> result=`25593 bytes / 7ea34515...e7b26e`。当前relay/J2仍ON，停在干净白屏人工观察门；
> 尚未切电、刷入或执行code4对照。

> `2026-08-22 21:04 +08:00` 操作者确认 ordinal5 后屏幕全白，code5/y-inclusive 五步组
> protocol+manual闭环。下一步获准转 code4/Blue-1 对照，但仍先执行 relay/J2 OFF、app-only
> flash+独立verify+GET-only fresh diagnostic；未从白恢复自动串接可见动作。

> `2026-08-22 21:06 +08:00` 绑定 COM14/channel1 的 ZAVE-2CH 继电器执行
> OFF-with-feedback，随后独立 query 返回 commanded_state=`OFF`；PnP instance与USB location仍为
> `USB\\VID_1A86&PID_7523\\5&230B5917&0&4 / Port_#0004.Hub_#0001`。code4 对照 BIN/ELF
> 离线复核=`788256 / 64a6102e...da71a` 与 `13247936 / 8f4cf3a4...edf7a9`。尚未刷写。

> `2026-08-22 21:09 +08:00` 在J2 OFF下仅将code4/Blue-1 y-inclusive BIN写入COM8
> ESP32-S3 app `0x10000`；esptool识别同一rev0.2/MAC，write内建hash和独立verify digest
> 均PASS，未写NVS/bootloader/partition。随后4 GET/0 POST/0 visible-refresh diagnostic严格PASS：
> running firmware=`64a6102e...da71a`、boot=`1bf9fce8625e3a52`、fixture PASS、namespace
> key absent、READY/next1、BUSY=0、ARM/EXECUTE/driver=`0/0/0`，manifest明确PATCH_B=code4
> 且`ye=y+h-1`。diagnostic=`14436 bytes / 0509edfb...64d4da`。当前relay/J2仍OFF。

> `2026-08-22 21:12 +08:00` relay执行ON-with-feedback并回读`ON`；code4/Blue-1
> ordinal1全白基线仅发送1 ARM+1 EXECUTE，34,203ms后terminal COMPLETE，白帧/双DTM、
> mapping/sequence及PON/DRF/POF BUSY证据均PASS、1 driver、NVS READY/next2、0 retry/
> recovery/autochain。result=`23888 bytes / aa7cc6e1...ab3524`。当前J2保持ON，停在
> 全白人工观察门；ordinal2尚未释放。

> `2026-08-22 21:13 +08:00` 操作者确认 code4/Blue-1 ordinal1 后屏幕全白，人工基线
> PASS；当前J2保持ON，释放ordinal2两个红格单动作，ordinal3仍不自动串行。

> `2026-08-22 21:14 +08:00` code4/Blue-1 ordinal2两个红格仅发送1 ARM+1 EXECUTE；
> 30,474ms后terminal COMPLETE，输入帧/双DTM、mapping/sequence及PON/DRF/POF BUSY证据
> 均PASS、1 driver、NVS READY/next3、0 retry/recovery/autochain。result=`25844 bytes /
> f6f5a6cc...36b3d1`。当前J2保持ON，停在两红格人工观察门；ordinal3尚未释放。

> `2026-08-22 21:15 +08:00` 操作者确认 code4/Blue-1 ordinal2 后目前为两个红格，人工
> PASS；当前J2保持ON，释放ordinal3两个code4/Blue-1格单动作，ordinal4仍不自动串行。

> `2026-08-22 21:18 +08:00` code4/Blue-1 ordinal3只发送1 ARM+1 EXECUTE；29,646ms后
> terminal COMPLETE，输入帧/双DTM、mapping/sequence及PON/DRF/POF BUSY证据均PASS、
> 1 driver、NVS READY/next4、0 retry/recovery/autochain。result=`25839 bytes /
> 9d7b5dd2...48599e`。操作者确认两个蓝色矩形出现，并注意整块有效画面外围一圈深灰边；
> 灰边记录为窗口门控/全局刷新副作用候选，不认定为可用新色。当前J2保持ON。

> `2026-08-22 21:20 +08:00` code4/Blue-1 ordinal4绿色补丁仅发送1 ARM+1 EXECUTE；
> 29,410ms后terminal COMPLETE，输入帧/双DTM、mapping/sequence及PON/DRF/POF BUSY证据
> 均PASS、1 driver、NVS READY/next5、0 retry/recovery/autochain。result=`25850 bytes /
> dadf3236...3bf774`。当前J2保持ON并保留红/蓝/绿累积图，停在人工观察门；ordinal5白恢复
> 尚未执行。

> `2026-08-22 21:22 +08:00` 操作者确认ordinal4后绿色正常；Blue-1在刷新中先出现，最终
> 变灰渐隐；外围灰边仍在；白缝连续等宽，但底侧仍为间隔黑白。此现象与code5/Blue-2
> 组同向，排除“仅Blue-2码特殊”解释，支持PTLW地址窗口有效但factory-OTP全局波形未实现
> 窗外颜料静态保持。下一动作限定为ordinal5全白恢复。

> `2026-08-22 22:24 +08:00` code4/Blue-1 ordinal5全白恢复仅发送1 ARM+1 EXECUTE；
> 34,194ms后terminal COMPLETE/campaign_complete=true，白帧/双DTM、mapping/sequence及
> PON/DRF/POF BUSY证据均PASS、1 driver、NVS READY/next6、0 retry/recovery/autochain。
> result=`25817 bytes / 03729535...09343b`。当前J2保持ON，停在全白人工观察门。

> `2026-08-22 22:26 +08:00` 操作者确认code4/Blue-1最终恢复后“全白，全部清理了”，
> 封存为全屏白、外围深灰边消失、底侧黑白间隔线消失、全部累积色块清除。至此两组
> 正确包含式端点HOLD对照均protocol+manual闭环；物理结论为local addressing PASS、跨全局
> OTP的universal pigment HOLD FAIL。按既定顺序转入reference-first LUT，先切J2 OFF。

> `2026-08-22 22:27 +08:00` relay执行OFF-with-feedback并回读`OFF`。reference-first V4
> release重新describe校验通过：顺序`L535_ACTIVE_GLOBAL→L535_COMMENTED_GLOBAL`，每屏16个
> 纯场端点、无partial/dither/未知命令/VCOM扫描/中途断电/自动串行。首项treatment BIN/ELF
> 实体复核=`797504 / 7489fccb...aad06`与`13264120 / 5c0064b7...2d148`，均与release精确
> 一致。当前尚未刷写。

> `2026-08-22 22:36 +08:00` J2 OFF下将`L535_ACTIVE_GLOBAL` treatment仅写COM8 app
> `0x10000`，write hash+独立verify PASS。V4 runner首次只读诊断因硬编码旧CS1/CS2=`WF20_25/
> WF23_25`在claim/POST前fail-closed；直接version证明固件实际正确报告`LEGACY_ACTIVE_535/
> LEGACY_COMMENTED_535`。修正reference专用映射与`-128/127`非温区哨兵，新增2项回归，封存
> V5 release canonical=`e2afd212...2cac00`；14 passed、Ruff/py_compile PASS，固件与action ID
> 未改变。V5 fresh diagnostic 4 GET/0 POST/0 mutation PASS：boot=`77195d43ed35f74e`、action=
> `069cd744...55e8a`、25.0°C guard、clean-white/OFF、claim absent、0 visible refresh；evidence=
> `1208 bytes / f9ea60f9...d24dd4`。当前relay/J2仍OFF。

> `2026-08-22 22:42 +08:00` relay ON-with-feedback后，V5旧action只发送一次ARM；固件立即
> HTTP 400并报告`intent_missing_or_mismatch`，runner按no-retry合同停止。随即relay OFF-with-
> feedback并回读`OFF`。只读status/report固定同boot=`77195d43ed35f74e`、`fault_locked`、
> ARM/EXECUTE/driver=`1/0/0`、GPIO全低、BUSY=0、`driver_called=false`；因此没有R20/R21
> 写入、没有面板刷新，操作者刚确认的全白状态未改变。旧action与claim永久消费，不得重试。
> 离线根因已定位为host沿用了H3 empirical ARM/EXECUTE意图，而固件要求PURE_FIELD专用意图；
> 下一步仅修正host合同并轮换完整一次性身份后重建，不对当前fault固件做reset/recovery。

> `2026-08-22 22:55 +08:00` 离线修复闭环：ordinal1现精确绑定PURE_FIELD专用ARM/EXECUTE
> 意图，ordinal2原厂白意图保持不变；首项treatment轮换为build V2、NVS=`pflga2`、action=
> `8288e267...563b3`、descriptor=`88a882dd...d115f`。reference 4/4与原pure-field 16/16
> 环境全部重建SUCCESS；V7/V4 release canonical=`166f50c0...b5b6c82 / 37bb672f...b93f2e`，
> 定向18 passed、Ruff/py_compile PASS。V2 treatment BIN/ELF=`797520 / 83ab21f3...0f63f2`
> 与`13264120 / be62d3b9...f79889`。relay只读query返回commanded OFF；没有设备网络请求、
> flash或visible refresh。V4/V5/V6 reference身份均冻结为历史证据，不得现场执行。

> `2026-08-22 22:57 +08:00` relay/J2 commanded OFF下，将V7首项V2 treatment BIN仅写
> COM8 app `0x10000`；write内建hash与独立verify digest PASS，同一ESP32-S3 rev0.2/MAC。
> fresh diagnostic 4 GET/0 POST/0 claim/0 refresh PASS：boot=`3449e0b3a05da1c7`、action=
> `8288e267...563b3`、descriptor=`88a882dd...d115f`、claim absent、READY、clean-white、
> 25.0°C guard。evidence=`1208 bytes / b29424ab...e19515`。当前仍未接通J2。

> `2026-08-22 23:18 +08:00` relay ON-with-feedback后，V2 treatment只执行1 ARM+1 EXECUTE；
> 设备terminal COMPLETE、campaign_complete、1 driver，R20/R21、frame/双DTM、mapping/sequence、
> PON/DRF/POF与safe-finish均PASS，总driver=46,609ms。原host因沿用旧atlas FNV在终态封存
> 处假阴性，但未重发任何mutation；只读status/report证明FNV=`52FA55C5/8935B9C5/D36139C5`
> 与固件纯场合同一致。relay随即OFF并回读OFF。V10 GET-only reconciliation result=`1850 bytes /
> 50ef7158...ebb89`，claim=`0c16699e...e4576`；19 passed、Ruff/py_compile PASS。
>
> 操作者上传照片后，16个大纯场呈均匀非抖动外观；至少出现橙棕、酒红/粉红、米肤、深靛/
> 紫黑、黄绿等明显超出既有6/7色族的候选。裁决为`suspected_new_color`，decision=`1099 bytes /
> dc18b3a1...56c7`，instrumental absolute-colour qualification仍为false。V10/V5 release canonical=
> `ce88cafa...928aaf / 638a9a45...07967`。按停止规则仅允许独立白恢复，不推进commented或其他
> 未互换候选。局部刷新当前仍为addressing PASS、跨全局waveform universal HOLD FAIL；256色
> 多调色盘叠加尚未成立，下一核心实验为runtime-LUT与PTLW组合。

> `2026-08-22 23:21 +08:00` J2 OFF下将独立white BIN=`786016 / caa54089...83747c`
> 仅写COM8 app `0x10000`，write+独立verify PASS；fresh 4 GET/0 POST diagnostic PASS，boot=
> `ab68673aaece81a0`、claim absent、0 driver，evidence=`1218 bytes / c106d494...aae650`。
> relay随后ON-with-feedback；white action=`c915ca91...d7b4`仅1 ARM+1 EXECUTE，首个terminal
> report即success、1 driver、0 retry/recovery/autochain。result=`1458 bytes / a8f8f04f...a742e7`，
> claim=`25415901...6795bd`。操作者确认“白了”，relay随即OFF-with-feedback并回读OFF。
> 当前clean-white，reference矩阵按suspected-new停止，不执行第二候选。

> `2026-08-21 20:16 +08:00` chroma-history 五步真屏 campaign 完整闭环。J2/继电器由助手在每项
> 可见动作前后按监督模式切换，五项 action 均在同一 boot=`a6fd11c98782cb44` 上 COMPLETE，driver
> total=`5`、每项恰好 one-call、无 retry/recovery/autochain。ordinal1 runner 在同步刷新窗口内终态
> GET 超时，但没有 mutation retry；ordinal2 的首个 report GET 回读 ordinal1 为 COMPLETE/result=true、
> sequence/mapping/PON/DRF/POF PASS、34219 ms，reconciliation=`1690 bytes / ab8e0e4b...a64ff12`。
> ordinal2–5 result SHA 依次=`2c153004...411f57 / 6a597ba1...2e20b / da8c572e...323d2e /
> 4b8d32dc...1c7cbe`。人工观察原文逐项封存：source 每行横向一致；mid 前4列与后4列一致并带
> 操作者“不一定准确”的个别行明暗报告；target 8列=`黄红蓝绿黄红蓝绿`、各行无差异、左右一致、
> 白缝干净等距且无残影；最终 white recovery 被确认全屏干净白、无任何色块/边框/色斑/条纹残留。
> campaign summary=`4638 bytes / f1e6dc04...5b43a37`。最后 relay query 仍为 COM14/channel1 OFF；
> query 不单独证明下游电气状态。当前无下一可见 action。

> `2026-08-21 20:22 +08:00` 操作者明确调整阶段二优先级：60 s/10 min 保持观察可以滞后，先
> 发现新颜色；随后进一步限定为只关注单个像素自身可控的颜色状态，不接受空间抖动形成的视觉
> 混色。新增 discovery-first 补充计划，冻结 D1 为 128 条互不重复的 uniform-per-ROI 三步历史；
> 大色块内部所有像素使用同一时序，只用于放大同态单像素状态。候选可包含新色相或可重复明度/
> 饱和度状态，但即时命中不等于资格化；命中后先镜像和 1/2/4/8 px 同配方桥接，再补延迟、重复
> 与色卡测量。当前只更新离线计划，0 relay/device-network/flash/reset/visible refresh。

> `2026-08-21 20:28 +08:00` 操作者提出补测局部区域刷新，以提高单次样例数。复核精确面板审计、
> 当前驱动和相邻 E6_73 sample：本机当前只有完整双 DTM + 全局 PON/DRF/POF；window、old-frame、
> partial waveform、边界和 cleanup 全为 unknown。相邻样例 `0x86` 明确是未启用的 dither-image
> interlace helper，不是局刷合同；平台 Sparkle 也未绑定本模组。因此未生成或发送任何未知命令，
> 真局刷保持 HARD BLOCKED。作为等效吞吐改进，离线计划改为 D1-512：每半屏11×24、全屏
> 22×24=528 个 ROI，每格40×22 px、横/纵白缝4/2 px且内部同态；其中512格一次
> source→mid→target 并行覆盖全部 8³=512 序列，另有左右共16格 code 参考，仍以标准 white
> baseline/recovery 收口；这不是局刷，但把原需多批的发现样例压缩到 5 次全局可见动作。当前仅
> 文档策划，0 relay/device-network/flash/reset/visible refresh。

> `2026-08-21 20:41 +08:00` 操作者明确关闭 J2/电源并离场，要求先完成离线代码，返回后再继续。
> 四 agent 协同被限定为代码、测试、构建准备和文档，不得在离场期间接触 device/relay/network/
> serial，也不得 flash/reset/refresh。外部参数建议已完成离线裁决：3.3 V、SPI mode0、MSB first、
> BS0/BS1 LOW 接受；BUSY 纠正为 active LOW/idle HIGH；D1-512 固定已验证的1 MHz；真局刷、
> `0x86`/未知 LUT 命令和刷新中切电全部不进入当前实现。离线实现仍在进行中，本文不提前宣告
> 统一回归、PlatformIO build 或固件 identity 已完成。操作者返回后必须先重新确认 J2 OFF，才可
> 安排 app-only 固件刷写和只读身份检查；不得自动上电或自动开始任何可见动作。

> `2026-08-21 20:49 +08:00` D1-512 离线实现、构建和封存已闭合：布局为512候选+16参考，
> 固定5个全屏动作；PlatformIO PASS，专项11 passed、联合兼容26 passed，Ruff/py_compile PASS。
> BIN=`789456 bytes / ffa6e082...62b59b`，ELF=`13250236 bytes / 9f25e5e5...e2d12c`；release
> manifest=`3464 bytes / 4abe4dd3...d213a4`，frame contract=`ddbf5b9b...32d2a`，release
> integrity PASS，runner exact bound。整个离线阶段保持0 device/relay/network/serial/flash/reset/
> refresh。操作者现已回到电脑旁并询问是否上电；已明确要求继续保持J2 OFF，但返回后的物理状态
> 尚未 fresh 确认。因此当前唯一下一门是先收到 `J2=OFF`，再做 app-only flash、独立 verify 和
> GET-only identity/READY 检查；这不是可见刷新授权，不自动打开电源，也不自动开始任何 action。

> `2026-08-21 21:33 +08:00` 操作者开启上游电源并授权助手控制 J2。COM14 exact binding
> 保持 `VID:PID=1A86:7523 / PnP ...&0&4 / Port_#0004.Hub_#0001`；channel1 先 OFF-with-
> feedback 并 query OFF。只向同一 COM8 ESP32-S3/MAC=`a4:cb:8f:d9:fc:d4` 的 app `0x10000`
> 写入 D1-512 BIN=`789456 bytes / ffa6e082...62b59b`，esptool write hash 与独立 verify_flash
> digest 均 PASS；未擦 NVS/bootloader/partition。新 boot=`b85f791f320b92ea` 的四 GET 诊断
> strict PASS：exact identity/manifest、fixture self-check、READY/next1/key absent、ARM/EXECUTE/
> driver=`0/0/0`、0 POST/refresh。随后 channel1 ON-with-feedback；ordinal1 white baseline claim
> 永久消费并只发送一次 ARM+EXECUTE。同步刷新期间首个 report GET timeout，未重发 mutation；
> 25 s 后单独 GET-only report=`COMPLETE/result=true/next2/driver_call_count=1`，sequence/mapping/
> PON/DRF/POF PASS、1 MHz、total 35047 ms。当前 J2 commanded ON，等待人工确认 clean white 和
> 无异常后再决定 ordinal2；没有自动串行。

> `2026-08-21 21:58 +08:00` ordinal2 source、ordinal3 mid、ordinal4 target 均在各自人工门后
> 恰好执行一次并由 GET-only report 证明 COMPLETE；操作者依次观察为锯齿布局、布局改变和无序
> 布局，同色块均未看出明确差异，target 原话为“似乎没有发现新的颜色”。white recovery 前封存
> 3024×4032 原图=`3882233 bytes / f3266e53...6957`。透视配准检出395个色格、307个单应内点、
> RMSE=`2.261 px`；按 controller+target 独立消除平滑照明后，528 ROI 仅余4个相机相对弱偏离点，
> 全部为既有 target5/7 蓝色族，recipes=`493/207/173/13`，故不记作新色或已资格化状态。analysis
> report=`12210 bytes / 7606a0de...93a61`。随后 ordinal5 claim 只消费一次；同步 report GET 在刷新
> 中 timeout，0 mutation retry，等待25 s 后 GET-only 回读 `COMPLETE/result=true/next6/
> campaign_complete=true/driver total=5`，sequence/mapping/PON/DRF/POF PASS、1 MHz、35038 ms。
> COM14/channel1 随后 OFF-with-feedback 且 query OFF；当前等待操作者确认 clean white/无残留/
> 无异常，未发任何后续动作。

> `2026-08-21 22:21 +08:00` 操作者对 ordinal5 white recovery 最终回复“全白”；按原文封存，
> 不把未单独陈述的残留细项或声/味/热字段外推为已确认。observation=`582 bytes /
> 414fc32b...cd663`，绑定 ordinal5 action=`414fc723...2d435` 与 GET-only reconciliation=
> `ca811718...ce4f3`。D1-512 至此 protocol=`5/5`、human gate=`5/5`、target photo analysis
> complete；J2 保持 commanded OFF，0 后续设备请求或可见动作。

> `2026-08-21 22:33 +08:00` 操作者裁决阶段二因完整 8^3 历史筛查仍未见肉眼可分辨的新
> 单像素颜色而直接关闭；色卡、60 s/10 min 与重复资格化不再继续，但只记为不再具有决策意义，
> 不伪记测试通过。逻辑分析仪明确降为写入观测辅助项，不阻断第三阶段。已离线重新构建未独立
> 上屏的 `WF23_25` empirical-H3 treatment 与独立 factory-OTP white recovery；BIN/ELF 四项哈希
> 与 2026-08-12 封存 release 完全相同。新 standalone release file/canonical/release ID=`c06ebabb...
> 6346f3b / 0f5dfeb8...59b7a / 9ea2100e...16f4`，materialize/validate 零设备与零网络 I/O。
> 执行路径只允许完整 vendor-derived profile，不开放 raw payload、未知命令、VCOM/高压/OTP/NVM、
> SPI sweep、刷新中切电、retry/recovery/autochain。当前 J2 仍 commanded OFF，尚未刷写或执行 WF23。

> `2026-08-21 23:07 +08:00` Stage-III standalone WF23 完整闭环。J2 OFF 下 app-only 写入
> treatment BIN=`793776/6eb9115e...98e2`，独立 verify PASS；4 GET diagnostic exact READY、boot=
> `7bd375c5b24dafac`。随后 relay ON，一次 ARM+EXECUTE、terminal success，result/claim SHA=
> `abe3b375...9a820 / 390cc2fe...dc968`，无 retry/recovery/autochain。操作者原话“六色，左右
> 屏幕一致；第二排第一个和第四个是白色”，按固定2×4 atlas 解码为码4/7白，与 WF20 gross
> mapping 相同，无新色。因旧 WF23 recovery identity 已历史消费，新增隔离 source、namespace=
> `s3w23_0821` 与 action=`b6357c9e...6ccf7`；PlatformIO、68 tests、Ruff PASS。J2 OFF 下 app-only
> 写入 fresh white BIN/ELF=`8717cb86...e2e9 / 3d73545a...578f` 并 verify；4 GET virgin READY，
> relay ON 后一次 ARM+EXECUTE terminal success，result/claim=`bcd11a4a...7113b / a0585d1b...
> 35a75`。操作者原话“目前全白”；relay 随后 OFF-with-feedback/query OFF。当前无下一授权动作。

> `2026-08-21 23:36 +08:00` 按操作者“只有出现新颜色才左右复核；没有就直接推下一种”的
> 决策，将 Stage-III 改为 discovery-first。结构审计确认 PWR/PLL/PSR 为全屏共享，R20/R21 可按
> CS1/CS2 分别写入；因此不虚构 16 套独立 LUT，而是一次并行两套 native profile×8码。离线构建
> H20（global WF20 / CS1 WF20-R20 / CS2 WF23-R20）与 H23（global WF23 / 同一 R20 split），
> 各自另有独立 factory-OTP white。treatment BIN/ELF：H20=`315bffd5...a98e /
> 2c2d9f44...3919`，H23=`87bb4ae4...c184 / 89d415f8...c14d`；white BIN/ELF：H20=
> `d042c912...585a / 5d386069...ed55`，H23=`f25f00f5...fc43 / ba2bf9e1...4ff5`。
> 四对 BIN↔ELF app descriptor exact match，PlatformIO 四环境 PASS。新增 one-shot runner 将
> `no_new_color` 绑定为 white→next，将 `suspected_new_color` 绑定为 white→swap，并阻止命中后
> 继续 H23；brightness-only 归入 no-new。focused `8 passed`、Ruff PASS。全程 0 relay/device-
> network/COM/serial/flash/reset/visible refresh；当前设备、J2 OFF 与全白现场状态未改变。

> `2026-08-21 23:42 +08:00` 操作者回复“好的，继续”后，仅推进 H20 上机准备门。
> COM14/channel1 先发 OFF-with-feedback 并 query 为 commanded OFF；固件本地 SHA 与封存
> `315bffd5...a98e` 一致。同一 COM8 ESP32-S3 rev0.2 / MAC=`a4:cb:8f:d9:fc:d4`
> 仅写 app `0x10000`，esptool write 内建 hash 与后续 `verify_flash` 均 PASS，未擦 NVS/
> bootloader/partition。旧端点 `192.168.1.7` 经本机网卡证据证明为 PC 自身；ARP 将
> ESP32 精确 MAC 绑到 `192.168.1.11`。对新地址的唯一次 diagnostic 为 4 GET/0 POST/
> 0 mutation/0 visible refresh，exact BIN/ELF/profile/release 全部 PASS，boot=`c65a94b7ba8178c4`，
> diagnostic canonical SHA=`0f2d948afebf24d2cf7acd2784153167a0725f94d498839fe046a31a047a768a`。
> action=`f0061996...c79b` 仍未 claim/未执行；J2 保持 OFF，停在人工可见动作门。

> `2026-08-21 23:46 +08:00` 操作者明确“开始 H20”。relay channel1 从 query OFF 切换为
> ON-with-feedback 并 query ON；对 H20 action=`f0061996...c79b` 物化唯一 claim，只发
> 1 ARM + 1 EXECUTE。终态为 `success`，visible refresh=`1`，terminal report GET=`1`，
> read error=`0`，无 retry/automatic recovery/automatic chaining/profile switch。result/claim SHA=
> `c14911212e4275e799effd71b81597a09774016c5b7eac5d102e0a02ed1054fd` /
> `256dd56d03964007f410fb0127e07ff76cec1c739174391240d7d596586c923b`。relay 保持 ON，
> 已停在人工颜色观察门；未自动恢复白屏或推进 H23。

> `2026-08-20 23:57 +08:00` 用户确认 `J2=OFF` 后完成 16-block A/A′ focused campaign
> 的离线实现与上机准备。固定动作顺序为 `A-Primer→A-Target→White→A′-Primer→A′-Target→White`，
> 每次独立 ARM/EXECUTE、永久 claim、无 retry/recovery/autochain；A/A′ 用 220×128 大色块覆盖
> source0..7→target4/7 共 16 recipes，Target 后照片时点固定 5/60/600 s。PlatformIO build PASS，
> 相关回归 `5 passed`、Ruff/py_compile PASS。BIN=`789408 bytes / 881cec3f...a2337b9`，ELF=
> `13244048 bytes / 0eb59302...23087`；offline manifest SHA=`b6ca290d...31b7c5`。仅写 app
> `0x10000--0x0d0fff` 并 verify digest matched，未擦其他分区。ESP32 DHCP `.11` 由 exact MAC
> `a4:cb:8f:d9:fc:d4` 绑定；新 boot=`84c5fdc91d8fb787` 的 version/manifest/status/report 四 GET
> 全部严格通过，fixture self-check=true、新 NVS key absent、READY/next1、BUSY=0、0 POST、
> 0 driver call、0 visible refresh。diagnostic=`15836 bytes / 14c3f06d...52c66b`，integrity=
> `79dfa180...2b14bf`。当前保持 J2 OFF，仅待 `J2=ON` 执行 ordinal1。

> `2026-08-21 00:04 +08:00` 用户确认 `J2=ON` 后，focused ordinal1 A-Primer 唯一执行
> COMPLETE/PASS：35.079 s、operation1、one-call、双控 DTM FNV 均=`0xA21BC9C5`，input FNV=
> `0x539AF5C5`，mapping/sequence/PON/DRF/POF 全通过，无 timeout/retry/recovery/autochain；设备
> READY/next2。result=`25197 bytes / 19c9dae8...fdc51`、integrity=`a22179b1...64fcb`，claim=
> `1304 bytes / 2e01d052...727b7`。当前保持 J2 ON、屏幕应显示左右各 8 个 source0..7 大色块；
> 等待人工目视确认后才执行 ordinal2 A-Target。

> `2026-08-21 00:07 +08:00` 操作者确认 A-Primer“8色块，左3和右4同一种蓝色；左右两个
> 分区完全一样”；observation=`754 bytes / 57c2f45e...42578d`，位置措辞原样保存、不擅自推断
> 索引。随后保持当时 J2 ON 发出唯一 ordinal2 A-Target。动作尚在运行时操作者报告准备休息并
> 已关闭 J2；runner 首次 terminal GET timeout 后停止，无重试。其后仅用 2 个 bodyless GET 回读：
> Target 帧及双控 DTM 已上传且 identity matched，但 PON 等待 60.001 s timeout，DRF 未到达
> (`drf_busy_seen=false/drf_ms=0`)，operation2 FAULT、sequence=false、FAULT_LOCKED/next2；因此
> 没有取得 intended A-Target 显示结果，预计屏幕仍为 A-Primer。Target claim=`1343 bytes /
> 7360f331...e2eacf`，fault readback=`1621 bytes / 99270c4a...ae4f0b`。当前 J2 OFF、BUSY=0；
> 0 retry/recovery/autochain/white。明早照片只可作为断电保持/Primer 状态证据，不得记成 Target。

> `2026-08-21 08:17 +08:00` 操作者补充“昨天只看到两条蓝色的线条，被之前的颜色所影响”，
> observation=`829 bytes / 6cc512ce...ddb0d3`。结合驱动证据，当前 firmware 只实现整屏双控
> DTM 与全局 DRF，没有已验证的 partial-window/partial-refresh 路径；既有 8×8 matrix 已经通过
> 一次整屏 frame 内的 64 semantic ROI/controller 达到并行筛查。两条连续蓝线来自 target4/7
> 相邻格无白缝而合并成列，不等同于只刷新了两条线。提出但尚未获准的新方案：8×8 带白缝
> 三步 chroma 网格，并行 `source0..7→mid4/7→target2/3/5/6`，每控制器 64 semantic sequence、
> 左右镜像 128 physical ROI；`white baseline→source→mid→target→white recovery` 共 5 个全屏动作，
> 5/60/600 s 拍照。当前 0 device/network/flash/reset/J2/visible refresh，新方案未生成。

> `2026-08-21 19:23 +08:00` 在继电器保持 OFF 的前提下完成上述 chroma-history 五步方案的
> 离线实现与封装。host 生成 4 个唯一 1024×600 packed-4bpp 固定帧及 5 个 action identity；
> source/mid/target 网格均保留 4 px 白缝，CS1/CS2 做位置镜像，覆盖每控制器 exactly 64 条
> `8×2×4` 语义历史，左右共 128 physical ROI。隔离固件使用新 namespace=`mf1750_cg1`，启动
> 只做 frame/双 DTM SHA+FNV+histogram self-check；无 startup refresh、raw frame、runtime LUT/
> OTP write、clear/reset/retry/recovery/autochain 路由。每个 ordinal 必须先持久化 consumed，再恰好
> 一次 driver call，下一项不会自动执行。PlatformIO build PASS；定向 `8 passed`、Ruff、py_compile、
> runner describe PASS。sealed BIN/ELF=`788544/13242976 bytes`，SHA=`16bd2952...6fd0b`/
> `bfa5f634...067b`；release 目录=`.test-output/offline/MF1750_EC5_CHROMA_GRID_FIRMWARE_V1_20260821/`，
> frame bundle=`.test-output/offline/MF1750_EC5_CHROMA_GRID_V1_20260821/`。本轮没有切换继电器/J2，
> 没有访问 COM8/设备 HTTP，没有刷写、复位、claim、POST 或屏幕刷新。当前仍 OFF；下一门为在场
> 操作者普通确认后仅刷 app `0x10000` 并 verify，再做 4 GET/0 POST 诊断。

> `2026-08-20 13:25 +08:00` 用户提交阶段二/三 v1.0 总体计划，并确认 USB/COM 控制继电器
> 已采购、逻辑分析仪尚未到位。本轮完整读取计划和现有证据后，仅新增非破坏性执行补充
> `docs/MF-17506-M009F-T_阶段二与阶段三落地执行流程.md`，固定 D0/R0–R3/S20/S21/L0/G3/G4
> 分门、继电器 fail-closed 状态机、证据目录、42 pair 的 3+3 镜像批次和三步序列裁剪规则。
> 现有双控 8×8 matrix 只作先导证据；新正式 42 pair 需要 18 个可见动作。343 三步全量为
> 88 个动作，若全部镜像至少 176 个，因此默认只从 H2 命中项生成优先子集。继电器采购不等于
> commissioning；逻辑分析仪缺席及同版 LUT ABI 缺失使阶段三继续 hard-blocked。本轮 0 USB/COM、
> 0 device/network、0 relay、0 flash/reset、0 J2、0 visible refresh、0 LUT write。

> `2026-08-20 14:10 +08:00` 用户确认已采购 24 色卡，并要求先评审测试代码功能与流程、确认后
> 再编码。新增评审草案 `docs/MF-17506-M009F-T_静态照片阶段二代码实施规格.md`：不放宽原六码
> palette，另建历史 recipe palette；优先定量化 16 个 `source 0..7→target 4/7`，用 A/A′ 两批
> `Primer→Target→White` 共 6 个可见动作；增加 1/2/4/8 px 桥接门后才允许照片级组合；静态照片
> 输出四案预览和 Primer/Target 双帧。24 色卡无可靠参考值时只允许 CAMERA_RELATIVE，不冒充
> 计量校准；真实 relay adapter 等 R0。当前是 DESIGN ONLY，实现未开始。本轮 0 USB/COM、
> 0 device/network、0 relay、0 flash/reset、0 J2、0 visible refresh、0 LUT write。

> `2026-08-20 21:46 +08:00` 用户已用“好”确认静态照片代码规格默认选择，随后要求再激发一次
> 观察颜色是否存在差异。P0–P5 首版离线实现完成：`host/static_photo/` 与
> `tools/mf17506_stage23/` 覆盖 24 色卡三档 reference grade、1/3 次 capture、鲁棒线性
> RGB→XYZ/ΔE00/LOO、历史 recipe palette、16 个 source0..7→target4/7 A/A′ 双控固定帧、
> panel-photo analysis、四种照片 quantizer、relay fake/session dry-run 和 Stage-3 hard gate。
> 新定向 `11 passed`，相关旧回归 `75 passed / 94 subtests`；全仓仅跑到约 2% 后因规模主动中止，
> 不记作全仓 PASS。offline root=`.test-output/offline/MF17506_STATIC_PHOTO_STAGE2_OFFLINE_20260820_V1/`，
> 蓝色计划为 16 recipes/6 actions，fake dry-run 终态 `DRY_RUN_SUCCESS_SAFE_OFF`。

> 同轮确认冻结 RC2G `/api/frame` 只接受 0/1/2/3/5/6，无法传输历史码 4/7；因此未连接设备，
> 改为准备隔离 factory-OTP 复测。新增独立 source/config 和新 NVS namespace=`mf1750_otpm8r2`，
> 复用已验证 8×8 Primer/Target/White fixture；新 app BIN=`787856 bytes / 3710ab84...aff13`、
> ELF=`13242424 bytes / cab3fea0...772a5`，PlatformIO build PASS。一次一动作 runner 永久 claim
> before ARM、恰好 1 ARM+1 EXECUTE、只读 poll、无 retry/recovery/autochain；新测试 `3 passed`、
> 与原 firmware contract 合并 `13 passed`、Ruff PASS。原 OTM source/config 恢复为零 diff；当前
> shared driver 漂移使现编原 OTM BIN 不等于 8 月 10 日 archive，此事实不改写旧证据。全程 0
> device/network/COM/USB/flash/reset/J2/visible refresh/LUT write；仍等待 fresh J2-OFF 门和一次
> app-only 临时刷写确认。

> `2026-08-20 22:07 +08:00` 用户按简化门仅确认 `J2 OFF`，并明确其他现场检查自行负责。
> 复核 offline BIN `787856/3710ab84...aff13` 后识别 COM8 为 ESP32-S3 rev0.2/MAC
> `a4:cb:8f:d9:fc:d4`；仅写 app `0x10000--0x0d0fff`，独立 `verify_flash` digest matched，
> 未擦 NVS/bootloader/partition。首次 `.7` 诊断被宿主代理 502 拦截，直连 `.7` 又被拒绝；均
> 0 POST/0 refresh。ARP 随后以 exact ESP32 MAC 定位 fresh DHCP 地址 `.11`；direct/no-proxy
> version→manifest→status→report 四 GET PASS。boot=`27fcf88b6136c68d`，new namespace
> `mf1750_otpm8r2` key absent、READY/next1、ARM/EXECUTE/driver=`0/0/0`、BUSY/RST/CS/CS2
> 全低、report NOT_EXECUTED。diagnostic 12393 bytes/SHA=`b8a249ff...a72e4c`，integrity=
> `e805a250...a9f1d`；runner 已固定 LAN no-proxy，SHA=`7b0f2cc6...886cd`。当前 J2 仍 OFF，
> 0 visible refresh，等待用户只回复 `J2=ON`。

> `2026-08-20 22:08 +08:00` 用户回复 `J2=ON` 后尝试 Primer，但 runner 的四 GET preflight
> 读取同 boot=`27fcf88b6136c68d`、READY/next1、BUSY=0，在任何 claim/POST 前 fail-closed；
> 5 秒后额外 1 次 direct status GET 仍为 BUSY=0。ordinal1 claim/result absent，设备计数仍为
> ARM/EXECUTE/driver=`0/0/0`，0 visible refresh。遵从用户要求，下一次只重新确认 J2，不索取
> 电流、温度或其他字段；BUSY 未高前不执行 mutation。

> `2026-08-20 22:13 +08:00` 用户定位到 GND 脱落并重新插好；随后同 boot BUSY=1。Primer
> 唯一 ARM/EXECUTE 已消费，设备 Web 在约 34 s 同步刷新期间使 runner 首个 report GET 超时，
> 但没有 mutation retry；25 s 后只读 status/report 证明 ordinal1 COMPLETE/result=true、driver
> one-call、sequence/mapping/PON/DRF/POF PASS、next2，用户目视“看到8条色条”。Primer claim
> SHA=`4559a581...3818f`，正式 result 尚待由 terminal readback 补封，不影响设备已完成事实。
> 随即保持 J2 ON 执行唯一 Target，35.043 s 后首个延迟 report GET 即 PASS：operation2、双控
> mapping 与 BUSY 全通过、READY/next3。Target result 23701 bytes/SHA=`1c49d3b5...365d4`、
> integrity=`ce3dc747...8de82`，claim SHA=`b21f2042...a3ce2`。当前两次可见刷新完成，White
> ordinal3 claim absent；等待人工比较后恢复白屏。

> `2026-08-20 22:22 +08:00` 用户观察 Target：“只有第5.8列蓝色方块有变化，可以做更多的测试”。
> 1-based 列 5/8 解码为 target transport code 4/7，与历史 8×8 结论独立复现；其他列按用户报告
> 未变化。该结果证明 factory-OTP 下 history-dependent visible blue/brightness states，可作为进一步
> 标定候选；仍不证明新单像素颜料、runtime LUT 或自定义 waveform。observation SHA=
> `fc4cabdd...3ae9c`。随后按已规划 ordinal3 执行唯一 White，34.217 s、operation3、one-call、
> sequence/mapping/PON/DRF/POF PASS，campaign COMPLETE/next4；result 23634 bytes/SHA=
> `ede48374...b63a9`、integrity=`4722ede0...8d64e`，claim SHA=`3c60e7db...f79e9`。当前 3 次
> visible action 均已消费且不可重跑；等待 J2 OFF 后准备/刷入 16-block A/A′ focused campaign。

> `2026-08-19 00:35 +08:00` 艾利尔照片分支已按用户目视结论关闭。Atkinson、
> multicolor-DBS 262k、face-smooth B 三次 RC2G 上传分别完成 Job/Operation `1/1`、`2/2`、
> `3/3`，协议均通过，但视觉依次被判为面部颗粒强、颗粒更严重、面部失真；这些结果不构成
> 照片质量 PASS。随后在用户明确要求下，仅上传一次 canonical solid-white frame：307,200 bytes、
> 全部 `0x11`、SHA-256=`91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`、
> FNV-1a=`0x13340DC5`。RC2G 报告 Job/Operation `4/4` completed/result=true，双控 DTM
> FNV 均为 `0xB7A855C5`，sequence/BUSY/safe-finish/mapping 均验证通过。操作者随后确认
> `J2=OFF / 全屏干净白 / 人物或色斑残留无 / 声味热异常无`；电流与最高温度栏为空，按
> “未记录”封存。全白动作未刷固件、未复位、未重试。

> `2026-08-18 23:28 +08:00` reboot-resume 窄门完成：新 adapter 46,694 bytes/SHA=
> `bd3e008b...82fb`，定向回归 `5 passed`、Ruff/py_compile PASS。正式 J2-OFF diagnostic
> 18,107 bytes，file/canonical=`c87d6a1b...13ba`/`da160670...0496`；authority 3,233 bytes，
> file/canonical=`c99a5764...c15a`/`5438aacf...5d3f`，state=`OFFLINE_READY_AWAITING_FRESH_J2_ON`、
> `execution_authorized=false/visible_refresh_authorized=0`。diagnostic 与 authority 均在同一进程
> 二次验证相等；white result/claim absent。首次未缓存 CLI 在任何 diagnostic 写盘前人工终止，
> 因此没有额外 GET；正式封存恰好四 GET。

> `2026-08-18 23:32 +08:00` “艾利尔”自然图离线候选闭合：原图 9,426,504 bytes，
> embedded ICC 经 LittleCMS 转 sRGB，5760×3840 center-cover 到 1024×600，Atkinson/edge+
> white protection，六码占比 black/white/yellow/red/blue/green=`27.35/32.10/1.43/18.45/
> 13.03/7.64%`。manifest 16,175 bytes/SHA=`b6331c3a...dd2b`，generic experimental
> once-runner 的完整 candidate snapshot 校验 PASS，authorization registry 与 live result 均 absent；
> 0 device I/O/0 refresh。RC2G 源码当前重新构建产生未封存 `816544/ba59c3d6...cdc3`，明确不用；
> 后续固定引用历史已实测 `815664/9df89715...d772` app BIN。

> `2026-08-15 20:59 +08:00` 用户再次给出当前**部分现场状态**：`J2=OFF / 屏幕全白 /
> 面板电流 0 A`，并明确要求不刷写、不复位、不打开 J2、不刷新屏幕。本条没有重报
> `ESP32 USB / 3.3 V CV / exact 25.0°C / 1.0 A 限流 / 监测与物理切断 /
> Stage-A 后无 reset-flash-refresh-rewire`，也没有 fresh 选择 `.7` 替代 `.14`；因此不得
> 物化 Phase-A authority/live envelope/token，更不构成设备网络、COM 或任何 live action
> 授权。本轮仅完成文件读取、哈希核对和缺项 fail-closed 离线回归，未访问设备或改变现场状态。

> `2026-08-15 21:12 +08:00` 连续第三次 goal 审计确认同一输入边界未变化；现有输入下所有
> 可安全推进的离线门禁与部分声明零副作用证据均已闭合，下一产物必须依赖新的完整 fresh gate
> 和 `.7` 替代选择。Codex goal 已按规则标记为 `blocked`，不是测试或实现失败。恢复时从本页
> “当前下一步”继续；不得继承本轮部分状态、物化 live artifact 或发出请求。

> `2026-08-16 00:57 +08:00` 用户已用一条新消息完整重报 fresh gate 与 exact `.7` selection，
> 上述旧 blocked 条件因此解除。仅离线物化并深验 authority + runner-bound envelope；live attempt
> 仍未消费。当前停在第二条独立 byte-exact 授权边界，截止时间及失败语义以“当前下一步”为准。

> `2026-08-16 01:06 +08:00` 用户仅回复“继续”，不等于 byte-exact 授权；检查时 fresh gate 已过期。
> V1 attempt 从未消费，旧 authority/envelope 保留为 stale evidence，旧授权词永久不可执行。恢复必须
> 使用新的同消息完整现场确认和 `.7` selection，不能继承或拼接 V1。

> `2026-08-16 08:53 +08:00` 用户已重新用一条消息完整确认 `J2 OFF / USB untouched /
> clean white / 3.3 V CV / exact 25.0°C / 1.0 A / 0.000 A / monitoring+cutoff /
> Stage-A 后无 reset-flash-refresh-rewire`，并逐字选择未验证 `.7:80` 候选。V2 authority 与
> runner-bound envelope 已仅离线物化并独立验证；attempt 尚未消费。fresh gate 截止
> `09:03:12.982 +08:00`，当前停在第二条独立 byte-exact 授权边界。

> `2026-08-16 09:00:43 +08:00` 用户在窗口内逐字回传 V2 独立授权词；runner 只执行一次
> `.7:80 /version` GET 并密封 `TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE`。
> 该 attempt 已永久消费且不得重试。结果不证明 responder/device identity、trusted IP、fresh boot
> 或 active slot；0 POST/claim/mutation/visible refresh/Phase B/recovery/autochain，J2 保持 OFF。

> `2026-08-16 09:07 +08:00` 用户明确将当前边界锁定为 `可排程、未到执行门`。已仅离线形成
> C/C-white 与 T/T-white 两个条件式上机窗口及中间硬隔离安排；没有生成 authority/token/claim，
> 没有设备、网络、COM、USB、reset、flash、J2 或 refresh 动作。

> `2026-08-16 09:40 +08:00` Phase-B P0 离线合同闭合：真实 committed Phase-A raw `/version`
> 已从 sealed receipt 重放，剩余状态机固定为 `manifest→status→report`；offline gate 与 synthetic
> fake-only success 均 build/validate PASS。planned live root/registry/terminal/temp 仍全部不存在，
> `execution_ready=false / live_authorized=false`，没有网络或设备 I/O。

> `2026-08-17 07:10 +08:00` Phase-B P1 live runner/envelope 实现与离线 review 闭合：固定 `.7:80`
> 三段 bodyless GET、逐响应放行、registry/output checkpoint 先于 socket、O_EXCL temp 原子终态和
> post-attempt replay；synthetic success/failure/O_EXCL/过期门/笼统授权反例共 `7 passed`。用户的
> “授权完整给你”未被当作 fresh gate 或 exact token；production authority/envelope/token 仍为 0，
> planned registry/terminal/temp 仍不存在，0 socket/device-network/COM/USB/reset/flash/J2/refresh。

> `2026-08-17 07:22 +08:00` 用户 fresh 重报完整现场门与 `.7:80` 选择。首次离线物化因
> PowerShell 7 位小数时间在任何写盘前 fail-closed；规范化同一观测时刻后 authority/envelope
> build，并对 envelope 独立深验 PASS。fresh 截止 `07:28:08.216359 +08:00`；1074-byte exact
> token 尚未收到，planned registry/terminal/temp 仍为 0，0 socket/device-network/COM/USB/reset/
> flash/J2/refresh。

> `2026-08-17 07:33 +08:00` 用户未回传逐字 token，而是询问是否下一步真屏并给出未完成的
> “ESP32 接着，但是 J2…”状态；fresh gate 已过期。只读检查确认 registry/terminal/temp 仍为 0，
> 因此没有 Phase-B 请求。旧 authority/envelope/token 已 stale，不补认、不执行；必须重新 fresh gate，
> 且下一步仍为 J2-OFF read-only diagnostic，不是 visible refresh。

> `2026-08-17 09:15 +08:00` 用户后续明确补全：J2 已物理断开、本人已离开现场，ESP32 USB
> 按前一消息仍连接；要求回场前完成全部离线准备。该声明不是 fresh live gate。此后未访问设备、
> COM/USB 或设备网络，未 reset/flash/打开 J2/refresh；只运行本地 PlatformIO `run`，两份 C23
> BIN/ELF 精确复现既有哈希。

> `2026-08-17 09:15 +08:00` WF23 C23/T23 平行链离线闭合：新增独立 compiled-trace adapter、
> C23 release、一次性 physical facade、C23 control-leg/pair evidence 和 T23 preclaim facade；假设备
> 证明 C23 两个 action 的不同 claim、白屏恢复和 C23 完成后才释放 T23 准备门，合计 `13 passed`。
> 正式 C23 release file/release ID/canonical=`4f8e2d7c...2130a`/`7350ff96...8836b`/
> `122bc606...9459`，明确 `live_authorized=false / visible_refreshes=0`。

> `2026-08-17 09:15 +08:00` 五对十次统一 readiness 已深重放 C20/T20、C23/T23 和 dither 五份
> release，固定 5 彩色+5 白屏及全部依赖/安全停点。artifact file/ID/canonical=`9a2c370b...5bca`/
> `d1d59b64...4d33`/`a64473b2...dafe`，定向 `2 passed`，Ruff/format PASS；结论为
> `same_evening_scheduling_allowed=true` 但 `execution_gate_reached=false/live_authorized=false`。
> 十次筛选只能产生候选；胜出路径必须另开 fresh gate 做重复性与色度，不自动运行 137+ 资格动作。

> `2026-08-17 17:48 +08:00` 用户要求在 waveform 扩色暂不可操作时准备像素抖动备选。
> 已保持现有 dither V1 和十次核心身份不变，新增七组 8×8 ordered 连续双色渐变、暖/冷三色场、
> 中性渐变、六码带框色块和 1/2/4/8 px 细节图；两个 512 px 控制器半屏语义和 mask 相位相同。
> 新离线 bundle 9 files，manifest file/canonical=`30c5b81c...a983`/`78c5397d...0e94`；
> fallback readiness 固定完整 6 次、核心后新增 4 次及安全停点，file/ID/canonical=
> `59f7b8a0...3e45`/`b50c25ee...2b78`/`953ca8dd...e14d`。专用 fixed-frame adapter/release
> 仍是显式 pending gate，旧 RC2G binary 不是 live authorization；本轮 `7 passed`，0 device-network/
> COM/USB/reset/flash/J2/visible refresh。

> `2026-08-17 18:28 +08:00` 抖色扩展 P0 已被 fixed-compiled V2 取代：新增隔离固件只生成
> pair-gradients/effects-chart/white 三种固定帧，并在 panel I/O 前核对 full-frame SHA/FNV/histogram
> 与双 controller DTM SHA/FNV。PlatformIO 仅执行本地 `run`，未 upload；compiled identity 深验
> 四 action、三 fixture、唯一 display、唯一 setup validator 和 BIN↔ELF。专用 campaign、一次性
> physical runner、未来 action10 white evidence finalizer 与 staged release 均已闭合；staged release
> 刻意为不可执行，不能替代尚未发生的核心第 10 次 result/observation/claim。V2 readiness 明确
> `all_current_offline_implementation_work_complete=true`，但 `extension_execution_release_ready=false /
> live_authorized=false`。全程 0 device-network/COM/USB/reset/flash/J2/visible refresh。

> `2026-08-17 21:01 +08:00` 操作者回场后完整重报现场 gate 与 exact `.7:80` selection。首次
> Phase-B authority 准备在任何写盘前发现 V10 release current-source 深重建漂移并 fail-closed；
> authority/envelope/registry/terminal/temp 均未生成，0 device-network/COM/USB/reset/flash/J2/
> visible refresh。根因精确为抖色 extension-only 块向共享 `epd_driver.cpp/.h` 增加 150/1198 bytes；
> 在内存剥离这些 exact unique blocks 后逐字命中旧 SHA，随后共享源已实际恢复为 97275 bytes/
> `386acdd3...2f6c` 与 12284 bytes/`3bbddfe8...2343`。旧 Phase-B P0 gate 再次 43 s 深验
> `valid=true / phase_a_predecessor_committed_success=true / phase_a_raw_version_replayed=true /
> planned_registry_or_receipt_created=false`。中途产生的 V3 facade blueprint（12433 bytes，file/ID/
> canonical=`427b683e...5d55`/`5a7bfd84...c541`/`ed520fc4...4063`）仅为已放弃兼容路线的离线
> artifact，不 supersede 当前 P0 gate，也不构成 authority。因处理超过 600 s，操作者本条 gate
> 已按 TTL 作废，下一步必须重新完整 fresh 重报。

> `2026-08-17 21:15 +08:00` 操作者重新完整 fresh 重报相同现场条件与 exact `.7:80` selection。
> V2 authority/envelope 已仅离线物化并重建验证 PASS；fresh 截止 `21:20:20.059360 +08:00`。
> authority/envelope file SHA=`cbd8a7f3...9aae`/`14ee8c16...bf1d`，ID=`e863a4a3...d621`/
> `93a6328b...f28d`，live attempt=`f0630b1f...3148`，challenge=`6875cf71...8216`。当前停在
> 第二条独立 byte-exact token 边界；registry/terminal/temp 仍为 0，0 socket/device-network/COM/
> USB/reset/flash/J2/visible refresh。

> `2026-08-17 21:20:20 +08:00` V2 token 两次均未 byte-exact 回传：第一次在多个哈希中插入
> 实际空白/换行；第二次缺失 `LIVE_AUTHORITY_FILE_SHA256` 后的 `_` 及 `MUTATION_REQUEST_0`
> 中的 `_0`。均未调用 `execute`，registry/terminal/temp 持续不存在。窗口于
> `21:20:20.059360 +08:00` 到期后 V2 永久 stale；不得自动纠正用户文本、补认或复用。

> `2026-08-17 21:25 +08:00` 操作者第三次完整 fresh 重报后，V3 authority/envelope 通过每项
> 两遍深重建再 O_EXCL 写盘，未运行 `execute`。fresh 截止 `21:31:59.772864 +08:00`；另生成
> 独立 UTF-8/ASCII 1075-byte 单行复制文件，SHA=`2485e73f...3592`，只用于降低聊天复制错误，
> 不等于用户授权。registry/terminal/temp 仍为 0，0 device-network/COM/USB/reset/flash/J2/refresh。

## 紧凑 DevKitC 载板里程碑（2026-08-13）

- 新建独立 Rev B0，保留已验证 Rev A1 不变；板框 `62 x 58 mm`，相对
  `80 x 75 mm` 面积减少约 `40.1%`。
- 集成用户指定的 `ESP32-S3-DevKitC-1 N16R8`，官方 `2 x 22`、`22.86 mm`
  排距；`R16=FIT`、`R15=DNP`，两者禁止同时安装。
- DevKitC 两个 3V3 脚均为独立 NC；USB 只供 MCU。面板域由板边 J3
  `pin1=3V3 / pin2=GND` 输入，经 `R4/R8=FIT` 分配到 `EPD_3V3/V_B`；
  TP1/TP2 只作底面测量点。
- 已完成全板路由、双面 GND、局部但不连续的 3V3 铜缓解、开关电源短回路
  局部加宽、双层天线/板边禁布区、正反面防呆丝印与底面测试点；当前权威 PCB 为
  `hardware/mf1750_devkitc_compact/mf1750_devkitc_compact.kicad_pcb`。
- KiCad 10.0.3 最终结果：`ERC 0/0`、`DRC 0`、`unconnected 0`、
  `schematic parity 0`；报告为同目录 `erc_final.rpt`、`drc_final.rpt`，
  预览为 `preview/final_top.png`、`preview/final_bottom.png`；
  `verification_manifest.json` 只绑定 canonical PCB/SCH/project、BOM、netlist、
  两份报告与两张最终预览，目录内其他路由文件均不是制造输入。
- B0 的 `/3V3`、`/EPD_3V3`、`/V_B` 仍分别存在 `0.20 mm` 载流窄颈，
  3V3 relief 也不是 J3 到 R4/R8 的连续铜母线，因此只闭合为可测工程首板，
  不能声称与 Rev A1 电源完整性等同。
- 首选四层 B1 工程候选已独立闭合于
  `hardware/mf1750_devkitc_b1_single_power_layer/`：保持 `62 x 58 mm`，
  `In1.Cu` 为零走线、单个 full-outline `/GND` zone；采用 solid 连接并增加
  8 个普通 GND 回流过孔后，实际填充为单一连续 `3205.48 mm2` 铜体。
  `In2.Cu` 只承载 `/3V3`、`/EPD_3V3`、`/V_B`，母线宽度
  分别 `0.60/0.60/0.80 mm`，仅 R4.1 到 3V3 母线有一段 `0.50 mm`
  局部颈。15 个供电落孔均为普通 `0.60/0.30 mm` PTH dog-bone，
  无 via-in-pad、盲孔、埋孔或微孔；全板 75 个 via 均为普通贯穿孔。
  最终 `ERC 0/0`、`DRC 0`、`unconnected 0`、`schematic parity 0`，
  天线与四边 keepout 覆盖全部四个铜层；`verification_manifest.json`
  已绑定最终 PCB/SCH/project、报告、netlist、审计、README 与正反面预览。
  B1 仍是 engineering candidate，不是生产资格放行。但嘉立创工程首板
  加工/SMT 数据包已闭合于 `hardware/mf1750_devkitc_b1_jlcpcb/`：`upload/`
  仅含应分别上传的 4 层 Gerber+PTH/NPTH ZIP、46 位 SMT BOM 和 46 位
  CPL；R16 FIT/R15 DNP，顶层钢网 144 个 flash 且不含 R15；J2/J3 保持手焊。
  已固定 `JLC04161H-7628` 1.6 mm 四层叠层、外铜 1 oz/内铜 0.5 oz、
  `ENIG (1U)`；源工程 ZIP 已内置自定义封装并在归档前独立 ERC/DRC/parity
  `0/0/0` 。权威 PCB SHA-256=`d44afcd28056045aa19c875d424b6ad7d9e84712e238ee2340f6d087da62fde3`。
  订单仍有硬停止：J1/C6/C15 器件本体到功能板边约
  `1.47/1.25/2.25 mm`，低于嘉立创一般 PCBA `>=2.5 mm` 条款；必须获得
  嘉立创 PCBA 工程对精确拼板/贴装方案的明确接受，否则停单改版或改手焊。
  J2 精确母座 MPN/0.80 mm 成品孔、N16R8/FPC/J3 Z 包络及 GPIO Ioff 隔离
  仍须首板闭合。
- 为消除 B1 的嘉立创 SMT 功能板边距硬停止，已从冻结 B1 非破坏派生独立
  **B2-4L-PCBA-EDGE**：权威工程目录为
  `hardware/mf1750_devkitc_b2_pcba_margin/`，板框放宽到 `65.0 x 60.5 mm`，
  全板仅刚性平移 `(+0.5,+2.5) mm` 后重建板框、三层 GND zone、四边及天线
  rule-area；61 footprints/629 tracks/75 through vias/8 zones/20 drawings/89 nets、
  网络/线宽、`R16=FIT/R15=DNP` 均保持。最终 PCB SHA-256=
  `462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238`；
  `ERC 0/0`、`DRC 0`、`unconnected 0`、`schematic parity 0`，通用 board audit
  PASS。46 个 FIT SMT 的最小本体/ Courtyard 功能边距分别为 `3.55/2.995 mm`；
  即使另作 `0.4 mm` 向内保守分析仍为 `3.15/2.595 mm`，故原 `<2.5 mm`
  厂家边距例外已移除。
- B2 完整嘉立创工程首板包已闭合于 `hardware/mf1750_devkitc_b2_jlcpcb/`；
  `upload/` 恰有 Gerber ZIP、BOM、CPL 三件。Gerber 为 4 层+双阻焊/丝印+
  Top Paste+Edge+PTH/NPTH，BOM=CPL=FIT SMT=`46`、唯一 LCSC=`16`；R15 的
  两个钢网开口已移除，R16 保留。源码 ZIP 24 项，已在全新目录复跑
  `ERC 0/0`、`DRC/unconnected/parity 0/0/0` 与 board audit PASS，且无
  `.kicad_prl`、lock/cache/backup/tmp；最终 configured package audit `7/7 PASS`。
  最终哈希：Gerber=`f00223f8b603e9ad3941e28e8bae7f60cd6052fcb30cd943e49fbb367efd661a`，
  BOM=`3123da5e7ac49a9b872f19e7ca20d4e8d53bb57414ccabbc8c2301c3f71f81a3`，
  CPL=`6b1e3ceae630601a009c0ae549a6e510e5d1bec5c1ee7bae0e0137b14fbbea5d`，
  source ZIP=`8ea86d987692f5b825e598c384ac9db62d656080dff9a11119862520e4d602cd`，
  support ZIP=`c2bf3e12c54e0d811b2f8aab1d2f273be5d99f94b552eab87f5e7561b8626ea8`，
  MANIFEST=`fc0a8c3a00a56a06e8f98e22ae9b3bdb97d7cc00b70cf4eae0e4d035e082a950`。
  Gate 为 `Local PASS / Online PENDING / External NOT_APPLICABLE`；只允许进入
  嘉立创在线 CAM/BOM/CPL/库存/旋转极性审核，尚不是厂家或量产放行。J1/FPC、
  J3、J2 孔径/Z 包络、天线 RF 与机壳仍是实物首板 hold。旧 B1 嘉立创包已被
  B2 取代，且会被新 ZIP 卫生合同因其中 `.kicad_prl` 正确拒绝，禁止再上传。
- 通用跨项目 skill 已在仓库 `.codex/skills/jlcpcb-kicad-handoff/` 完成，并逐字节
  安装到 `C:/Users/Ye/.codex/skills/jlcpcb-kicad-handoff/`。它覆盖双面 Fab/Courtyard
  功能边距、DNP 钢网派生、BOM/CPL、Gerber/ZIP、MANIFEST/SHA 与本地/在线/外部
  三门分离；15 个包审计反例、4 个 KiCad board-audit 测试、Ruff/format/compile/
  quick_validate 均 PASS。最终包审计器 SHA-256=
  `9baf5d4d042406acb6c8138583a476a1cc3707938f1cd528e24d1a7da55e61fb`。
- B0 仍是工程首板，不是生产放行：下单前必须用用户手中的实际 N16R8
  核对 USB/天线/母座 `>=11 mm` 的 Z 向空间和 J3 插拔；首板仍须限流、
  电流/轨压/温度监测与物理切断，并在插屏前测全套 MF-1750 电源轨。

## 数量口径

| 口径 | 已完成 | 剩余 | 说明 |
|---|---:|---:|---|
| 当前已放行的 RC2G N0+N1 真屏 action | **4/4** | **0** | N0 两张、N1 两张，全部已闭环并断电 |
| 完整滚动计划阶段 N0--N8 | **3/9** | **6** | N0、N1、原始 N2 完成；N3--N8 未完成，补充三列对比单列、不回写原 N2 |
| N2--N8 离线算法/计划包 | **7/7** | **0** | 候选、固定计划、分析/失败分支均已冻结；不等于 production live 安全闭环 |
| N2--N8 production live 软件安全闭环 | **7/7** | **0/7** | 七阶段均具备 physical identity、authenticated deep authority/profile、materialized runtime schedule、actual-clock freshness、operator CLI、claim/single-POST、耐久落盘、finalizer/public deep validator/analyzer；N6 额外从 N5 raw observations/strict finalized bundle 全量重算 palette，并由真实 Chromium 跑通 physical controller |
| N2 自然图离线候选 | **4/4** | **0** | Q1--Q4 均已离线深验证并完成各自 MAP→target 真屏；Q2 target visual FAIL，其余 target PASS |
| N2 固定 action declaration | **8/8** | **0** | 真屏 **8/8 finalized**：7 PASS + 1 visual FAIL；总分析 deep replay 通过，ranking Q1=26、Q3=23、Q4=22、Q2=7；全候选通过门为 false，故无 formal winner |
| N2 补充三列直观对比 | **离线/协议/人工 1/1** | **0** | 同一原始中心 crop、1:1 像素；人工排名 Q1 > Q3 > Q4；37°C、电气/ESP32 正常；独立 action，不改变原 N2 分数或 winner gate |
| N2 Q1--Q4 无显示 ingress | **4/4 PASS** | **0** | 四帧均 307200 bytes、设备 FNV 匹配、`epd_action:none`；job2→job0 已由用户确认的 ESP32 USB 重插解释，跨重插连续性不继承 |
| N3 预制计划 | **16 campaigns / 104 actions** | **0 个已上机** | N3A 12 个胜者×重复数模板共 72 actions；N3B 4 个平衡 block 共 32 actions；实际不得把全部分支串播 |
| N4 V3 离线候选 | **4/4** | **0** | 预注册五项 exact 正交、四格 transition/histogram/changed 严格保持；尚未真屏 |
| N5 冻结测量计划 | **26 sessions / 73 action declarations** | **0 个已上机** | 描述 atlas 11/22；正式 palette 8/9；正式 transition 7/42（pilot 12 + formal 30） |
| N6 真实浏览器 E2E | **离线 3/3 + physical 1/1** | **0 个软件场景** | 默认离线链保持零可见 POST；production physical 链以 loopback fake device 验证四预览、三 token、claim-before-network、唯一 POST、durable receipt/commit、reload/duplicate lock；不等于真屏完成 |
| N7 SPI sweep 真屏 action | **0/5** | **5** | 8 月 8 日冻结 V1 binary/五档 runner 完成；当前源码新 build hash 不同，重冻结前不得替换 V1；尚未刷入或执行 |
| N8 固定离线计划 | **5 sessions / 15 action declarations** | **0 个已上机** | ABA 4、warm 5、三个温区各 2；10 个 dependent action 要求紧邻 PASS result whole-file SHA |
| EC5 Stage A 白初态 U04/U07 | **corrected-v2 U04 COMPLETE_PASS / SHORT-HOLD DESCRIPTIVE PASS / 30-MIN SKIPPED；AFTER-U04 WHITE FINALIZED VISUAL+ELECTRICAL PASS**；V1 canonical `adedbbdf...d7dd` 已隔离，V2 canonical `0c7fd578...42183` | **A1 finalized；U04 协议 PASS + 约 5 min 稳定；A3 白恢复 finalized；Stage A 协议 3/5** | U04 蓝色短期稳定且可被标准白完全清除，无 ROI 轮廓/蓝色残影，电气正常。30 min 未测故 U07 formal gate 仍关闭；需 `0x4 vs 0x5` 直接对照才能判断是否新颜色 |
| EC5 U04-vs-U05 直接对照 | **PROTOCOL COMPLETE_PASS / BLIND MANUAL+ELECTRICAL+THERMAL VERDICT PASS**；release canonical `d871869e...f7fa5` | **对照 1/1；后续白恢复 0/1** | action `70db952b...7d1700`、result canonical=`45c6b502...42b0`/file SHA=`5d1c07fe...423b`、claim SHA=`39c3f1e5...96efc`。盲评强度 2/4 clear，双 controller 均为 U04 深于 U05；色块均匀、边缘清晰、白底干净、电气正常，35°C、ESP32 未重启，饱和度不作判断。最终 observation SHA=`2f45f458...88a6f` |
| EC5 原生 3-bit 直接状态 | **8 个 transport symbols 实测形成 7 个视觉颜色组；码4与码7肉眼等色** | **当前 OTP profile 的 native/history 扩色阶段完成** | corrected atlas 在左右反序双控制器上都得到同一 4≡7 分组，其余六码各自可辨。U04 与 U07 六前态 target 均为一致蓝色、彼此肉眼无区别，未出现历史态颜色/明暗分裂；若要 >7 个实测颜色必须转向不同 waveform profile，而非继续同 profile 重复轮次 |
| Runtime waveform/LUT 扩色 | **STRICT ABI NO-GO / EMPIRICAL H3 CODE-SCHEMA CONDITIONAL GO；V7 双 profile × runtime/recovery sealed；V7 treatment 均未刷入** | **直接 H3 路线暂停；C-first 四阶段真屏 0/4；token/claim/可见授权均 0** | V7 WF20/WF23 release ID=`52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e`/`9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4`，共同 host bundle=`3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0`；WF20 runtime BIN/ELF=`53d3abf2319761f282c518ebd6fd606f8efdfe0b1a869a1dcf61c04adbdecc06`/`63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df`，recovery BIN/ELF=`6a50b2bf287f3d6fd688c9cdfa2052ddc7db3d86c2f2ac9157585cdafd0766d2`/`0c8c82c35b46c69742f27a28c6fdce0ac2d003b3b0dd8a8b7b80152a608d9924`。文件名数字只作 opaque tokens；exact `25.0°C` 仅为 adjacent-legacy experimental guard，不是 vendor band、面板/FPL/膜批资格或安全证明。runtime V1--V6 均 superseded/non-executable；本轮完整初始 gate 已满足并用于 matched C 刷写，但 V8 diagnostic 失败，未进入 visible action |
| H3 C-first matched 因果对照 | **MATCHED V10 FLASH+VERIFY PASS / DIAGNOSTIC TERMINAL PRECLAIM FAILURE / TREATMENT V7 OFFLINE VALID / VISIBLE NOT EXECUTED**；C 不发送 R20/R21，T pin WF20 runtime V7 | **四阶段 0/4：C 0/1、C-white 0/1、T 0/1、T-white 0/1** | authoritative matched V10 release ID/canonical=`1cf8307c8906fa3057509c7a4a15bd79156751aa6b27c3f158435fbaa1049e36`/`5616bd495c9faf0983c3d361d5d3bea57837c5f5d8a498805cca940ca595b00e`，file=`a716dac890b3e272144365f51ae1167f6306d4830d841b11d00610ebb2b0698b`，host=`888ab013b6d3bb4ee8b2b2a87fdc348cb5ac2ce9265396ea5a39c70179416a3c`，contract=`25267914e74b249cc4bd1cc821437ea700a3c41a75140d82862c86357b3a63fe`，trace ID/canonical=`e2ebf082f779f4f61095b81dada2109c714c46e14ccc7020e43538e5492107f3`/`185d111e437de55d33df2fda6c647f33267ed7e571e73374dd22f2f3ed6b877b`；C BIN/ELF=`f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e`/`27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41`，C-white=`6ab18de07ffbf0ad56dbd6861957a42ea15c6cce9e435f790e74df1050cfa51d`/`6aba1ecb5eb339494c20cf51c56137f61d5568a596f644a7862b951cb45ed147`。V8 旧 runner 完成四次 GET 后才因 `/version.profile` 缺失 fail-closed；V9 未刷；V10 app-only 写入/verify PASS 后，该 boot 的 formal diagnostic 在首个 `/version` GET timeout，output-attempt=`fe988279...b95e`、`retry_allowed=false`。0 POST/claim/driver/refresh。C 删除双控合计 3010 SPI bytes/edges 与 10 yields，仍不是 strict time-matched |
| Factory-OTP 8×8 过渡矩阵 | **ordinal1--3 PROTOCOL + MANUAL COMPLETE_PASS；HISTORY-DEPENDENT BRIGHTNESS POSITIVE；WHITE RECOVERY PASS** | **protocol/manual 3/3；剩余可见 action 0** | 左 new-code4/code7 最深均在 old-code3/red 第4行；右对应列在两轴镜像后最深为第5行，其余六列无变化。该结论只证明固定 OTP 下的历史依赖亮度，未报告色相改变。white result canonical/file=`8e0deb15...b717`/`d525173e...635c`；用户确认完全净白、全部消失、电气正常、37°C，observation canonical/file=`5f9f72ac...84c7`/`5d5bf441...8e41` |
| Factory-OTP dither 矩形色卡 | **ATLAS + PHOTO + MANUAL OBSERVATION + REBOOT-RESUME WHITE COMPLETE** | **真屏 2/2：Atlas 1/1，White 1/1** | 每半屏 7 行色对×5 列 `纯A/75:25/50:50/25:75/纯B`，双控 70 ROI；全部仅用正式码 0/1/2/3/5/6，排除 4/7。Atlas action=`ef645811...0a2c` 唯一成功并永久 claim；三张原图、A4 camera-relative 70-ROI 分析和人工近/远观察完成。用户确认七行依次形成橙/赭黄、浅黄、黄绿/橄榄、紫/靛、棕、青绿/蓝绿、粉红的空间混色外观；这只支持空间混色，不证明新单像素颜料或新 waveform/LUT 色。跨 boot 后通过独立 reboot-resume 窄门完成 ordinal2 white；result/observation file SHA=`d963e01d...00a`/`0219712a...488`，人工确认全屏干净白、无残留。 |
| EC5 COLOR_LAB 单次刷入多色 | **V3 ROUND-1 SAFE STOP ordinal1--11 FORMAL PASS** | **真屏/人工/formal 11/23；12 个可选重复 action 未执行** | ordinal4 atlas 得到7组/4≡7；ordinal5/8/11 白恢复均干净；ordinal6→7 U04 与 ordinal9→10 U07 六初态链均 PASS，两个 target 都是均一蓝色、无前态影响且彼此无肉眼差异。全部 action 单 ARM/EXECUTE/driver、同 boot、无重启、无电气异常。ordinal11 result SHA=`ad9c9c78...8aaf`、observation SHA=`79d8e885...14a7`；停在计划内 round-one safe stop |
| Compare-after-white fallback | **OFFLINE FROZEN / ROOT REPLAY PASS**；action `f9d41bfc...ec1f36` | **真屏 0/1** | 独立 archived-RC2G 白恢复，不复用 baseline/after-U04/formal-after-U07 identity；J2-OFF 零 I/O gate、J2-ON 4 GET、claim-before唯一POST、manual white 与 latest-white/U07 绑定。focused 12/12 + adjacent 15/15、Ruff PASS |
| EC5 Stage B 六初态历史依赖 | **SOFTWARE EXECUTION PACKAGE READY / HARDWARE NOT EXECUTED**；release canonical `b500fee2...db04` | **每个获批候选真屏 0/9** | U04/U07 binary=`722b6932...f0fc`/`815ac96e...3c06`；六初态×双 DTM，无抖动；三轮 `primer→target→white`；真实观察/恢复与 Stage A 门均 fail-closed |
| STM32 runtime-waveform 参考审计 | **发送侧与相邻代际边界继续闭合：wrapper/ArmCC/IAR/D43/E2/type/record、SPD1656 全 offset、SSD1680A/1681/1683/1683A/2677、第二代波形/T2000；直接双控 mode-1 初始化与 11-byte 本地字段 ABI 仍未恢复** | **MCU 原序固定长度、SPI `D7→D0` sender 已直接证明；同版 ABI、controller-side decode、物理双控 loader、电气字段与真屏仍待证** | schema-2 IAR helper audit 固定完整 14-instruction sender 与 SPI_DATA machine body：无 NOT/XOR/RBIT/REV、11/88 stride、值比较或 early stop，原 byte 逐项 `D7→D0`，故发送侧不执行补码或 record 解析；controller 内部仍 unknown，报告 file/canonical=`46046593...e0e5`/`01241e9f...9c09`。SPD1656 提供正确 11-byte 宽度但错误的 20-group/VCOM-only 角色；SSD1680A/1683 系列提供正确 8-group 数但真实每 LUT group 为 7 bytes、R32=227，SSD1681/1683 的 RP/SR zero 语义还相反；SSD2677 公开 programmable waveform/cascade 却不公开 runtime ABI。T2000 已由 E Ink/Himax 一手资料固定为 host-input→mLVDS/TTL 的独立 TCON，第三方外置板路线成立；当前模组规格则固定 SPI→双 SPD1657B，不支持 drop-in。第二代公告中的 3-bit/八主色/兼容供应商没有绑定 SPD1657/E2802 或本地 800/799/704/11-byte ABI。adjacent-family report file/canonical=`94e46efb...9999`/`c090d254...a8f2`；second-generation report=`3bad6cdd...a7bf`/`aaee09b1...e42`。继续禁止命名本地 RP/LVL/VS/TP/SR、phase、电平、时长或 `FF`/zero。严格同版 ABI 仍 **NO-GO**，H3 仍 **conditional**，真屏 `0/4` |
| 从 RC2F G1/S1 调查起的历史可见 action | **18** | 不适用 | 独立 Q1/Q3/Q4 三列对比 protocol/人工观察均完成；其余历史口径不变 |
| N2--N8 可量化的未来最低刷新量 | **0** | **至少 137** | 仅为原 N2--N8 口径，不包含新 EC5；N3A 最小 repeat-2=4、N3B=32、N4=8、N5=73、N7=5、N8=15；N6 仍未计入，且均须先过 limit gate |

“剩余 7 阶段”不等于“再刷 7 次”。加入 N3 与 N8 固定预制路线后，原 N2--N8
口径的下限为 137 次（三列补充对比已经执行，不再属于未来动作）。新 EC5 单独计数：
Stage A 是 5 次；Stage B 只在门禁通过后为 9 次/获批候选。N8 的 15 次仍只是描述性小样本，不构成残影/温度资格。N5 的
73 次是已冻结计划上限口径（描述 atlas 22 + 正式 palette 9 + 正式 transition 42），
仍须仪器、供应商限制和 reviewed profiles 齐全才能物化执行；N6 可见 E2E 仍未计数。

## 已完成的 RC2G 真屏 action

| 阶段 | Exact action | Job/op | 自动证据 | 人工结论 | 状态 |
|---|---|---:|---|---|---|
| N0 | cold-boot MAP baseline | 1/1 | 协议、hash、BUSY、GPIO、nominal timing PASS | MAP 忠实度、电气 PASS | `DONE` |
| N0 | macro4 redisplay | 2/2 | 协议、hash、BUSY、GPIO、nominal timing PASS | 与 strict preview 一致；画质差；电气 PASS | `DONE` |
| N1 | low-balanced MAP primer | 1/1 | 单 POST；协议、hash、BUSY、GPIO、35016 ms PASS | MAP 忠实度、电气 PASS | `DONE` |
| N1 | low-balanced target | 2/2 | 单 POST；协议、hash、BUSY、GPIO、35016 ms PASS | 与 strict preview 一模一样；电气 PASS | `DONE` |
| N2 | Q1 Atkinson MAP primer | 1/1 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35026 ms PASS | 与 exact MAP preview 完全一致；36.5°C；电气 PASS；ESP32 未重启 | `DONE` |
| N2 | Q1 Atkinson target | 2/2 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35036 ms PASS | 与 strict preview 一致；`detail/tone/gradient/texture/artifact/fidelity=4/5/5/4/3/5`；37°C；电气 PASS | `DONE` |
| N2 | Q2 blue-noise MAP primer | 1/1 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35014 ms PASS | test image 正常；37°C；电气 PASS；ESP32 未重启 | `DONE` |
| N2 | Q2 area-weighted blue-noise target | 2/2 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35034 ms PASS | 与 strict preview 一致；`2/1/1/1/1/1`，白云黑化/黑颗粒/暗部压黑；37°C；电气 PASS | `DONE / VISUAL FAIL` |
| N2 | Q3 multicolor-DBS MAP primer | 1/1 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35006 ms PASS | test image 正常；37°C；电气 PASS；ESP32 未重启 | `DONE` |
| N2 | Q3 multicolor-DBS target | 2/2 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35037 ms PASS | 与 strict preview 一致；`4/4/3/4/4/4`；无旧残留；37°C；电气 PASS | `DONE` |
| N2 | Q4 overlap-aware-DBS MAP primer | 1/1 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35006 ms PASS | test image 正常；37°C；电气 PASS；ESP32 未重启 | `DONE` |
| N2 | Q4 overlap-aware-DBS target | 2/2 | 单 POST；协议、frame/DTM hash、BUSY、GPIO、35028 ms PASS | 与 strict preview 一致；`4/4/3/4/3/4`；无旧残留；37°C；电气 PASS；ESP32 未重启 | `DONE` |

N1 target 帧 SHA-256 为
`ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65`，预览 SHA-256 为
`39c10018dda091bb5af0ebad26b006c1c5e7c3374096de086e7cc8debcc42205`。这只提升该 exact
action 为 `experimental safety/frame-fidelity PASS`，不提升整机、算法或 2×2 因果资格。

### N2 补充三列对比（独立 action，已完成）

- strict preview：`.test-output/hardware/G1S1_N2_Q134_CENTER_THREE_WAY_20260809_V1/final.png`；
  左 Q1 Atkinson / 中 Q3 multicolor DBS / 右 Q4 overlap-aware DBS；三列均取原始
  `x=344..679, y=0..599`，1:1 像素，无缩放，8 px 白线分隔。
- frame SHA=`f992022a9a4d4993edde259f151c29a991fe1635edc9b574b55e1f76d91bb4aa`，
  FNV=`0xD38160CF`；preview SHA=`a2ad8047b5920295cba411559bb219464fdb4f665959b99da339d320f0c8c87d`。
- 已适配成熟 RC2G quality one-shot：exact prior 为当前 Q4 `job2/op2`，target 为
  `job3/op3`；action identity `add679271cd86c4f52157184b0368b34bbcb978581dbd1f7b3113d057e62b653`。
- action 已唯一消费：`job3/op3`、POST=1、retry=0、recovery=0，协议 PASS；claim 永久锁定，
  禁止重跑。人工结论 Q1 > Q3 > Q4；Q1 斑点更少，Q3 相对 Q4 对比度更强；37°C、
  电气正常、ESP32 正常。独立 observation SHA=`a512f1e4...ee83`。

## 剩余阶段、数量和目的

| 阶段 | 状态 | 预计真屏量 | 目的 | 放行前缺口 |
|---|---|---:|---|---|
| N2 自然图质量 A/B | `PHYSICAL 8/8 FINALIZED / ANALYZED` | **8 次已完成；原计划剩余 0** | Atkinson、面积蓝噪声、多色 DBS、重叠感知 DBS 各自独立 `MAP→候选`；ranking Q1/Q3/Q4/Q2=`26/23/22/7` | 四条 session、电气、温度、profile/authority/usage/claim 深验通过；Q2 visual FAIL 使 formal winner gate 关闭。另 1 次 Q1/Q3/Q4 三列补充对比也已独立完成，Q1 > Q3 > Q4，不属于原 8 次 |
| N3 重复性/顺序效应 | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | **至少 36 次**（N3A repeat-2 4次 + N3B 32次） | 判断同一算法的漂移和会话位置/行政前序效应；直接 target carryover 留给 N8 | N3A 强制重放 exact 8 份 N2 finalized raw evidence+trusted key，repeat-2/3/4 分支具备 physical execution、formal CLI、actual-clock/max-schedule/三 token、claim-before-network/single-POST/耐久 UNKNOWN、MAP→target prior 与 exact analyzer；N3B 32-action Williams 链已闭合。待真实 N2 结果、实物 binding/profile 与逐 action 授权，始终 `NOT_QUALIFIED` |
| N4 根因 2×2 | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | **严格矩阵 8 次** | 分离空间频率与左右半屏负载因素；每格独立 `MAP→cell` | dynamic physical rebind、deep profile、三 token、`max(materialized,authority)` runtime gate、claim/single POST/finalizer 与 exact 4-cell/8-action 2×2 analyzer 全闭合；待实物 binding/profile 与逐 action 授权，始终 `NOT_QUALIFIED` |
| N5 六色测量 | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | **73 次**：描述 22 + palette 9 + transition 42 | 建立 D65/2° measured palette、混色色块、光学核和 6×6 transition profile | physical panel/firmware/science review、deep authority/usage/review/key、actual-clock freshness、runtime max gate、三 token、dependent prior finalized result+strict RC2G+usage continuity、claim/single-POST/durable receipt/finalizer、strict production aggregation 与正式 operator CLI 均闭合；真实仪器/标准表/每 action profile 与授权仍是外部门 |
| N6 浏览器 E2E | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | 每个 formal manifest **1 个 exact action**；campaign 数待 measured gate | 验证真实浏览器预览、arm、唯一 POST、job/report 和错误语义端到端一致 | physical CLI、panel/RC2G、四类 actual-evidence HMAC、deep authority/usage/review/key、三 token、actual-clock/max schedule、claim-before-network/single-POST、同步 durable receipt/commit、fixed per-claim UNKNOWN incident、public validators、N5 raw→aggregate 重算及 Chromium physical E2E 均闭合；仍待真实 measured inputs/reviews/runtime/授权 |
| N7 SPI 扫频 | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | **至少 5 次** | 分别验证 1/2/4/8/10 MHz 的上传、hash、BUSY、时序和电气稳定性 | physical panel/exact N7 firmware/deep profile、150/150 driver-only cold schedule、actual-clock freshness、三 token、claim-before-network、五个 bodyless single-POST、prior/usage 链、finalizer 与 exact 5-result analyzer 全闭合；最终累计 10 MHz，仅 descriptive/`NOT_QUALIFIED`，待实物 inputs 与逐 action 授权 |
| N8 残影/温度/warm/soak | `PRODUCTION-LIVE SOFTWARE CLOSURE PASS / NOT HARDWARE-EXECUTED` | **15 次** | 描述性评价 A→B→A 历史效应、warm 顺序和三个外部温区 | exact 15 actions/5 sessions/15 rotated claims、physical panel/RC2G bytes、deep authority/usage/review/key、三 token、actual-clock freshness、runtime max gate、五条 prior/usage 链、warm dynamic baseline/ESP continuity、claim 后 durable UNKNOWN、正式 CLI/finalizer/exact analyzer 全闭合；始终 `NOT_QUALIFIED`，待真实环境/资产/profile 与逐 action 授权 |

`0x4/0x7` 的 factory-OTP 黑盒路线已经完成并以白屏收尾；当前新增目标是尚未执行的 C-first
四阶段 runtime attribution。旧对象只证明 legacy H3 upload 结构，不证明当前双控 3-bit
payload/loader/参数/安全合同。今晚已由用户暂停全部实物动作；LUT/波形/高压修改、局部/快速
刷新、带电故障注入和无人值守自动刷新继续 hard-blocked。

## 白天开发 / 晚上上机分工

- 白天一次性完成能够脱离硬件的实现：候选、预览、固定 action identity、workspace-global
  claim 合同、runner、结果 schema、失败分支、单元/集成回归、固件构建和逐项测试单。
- 晚上用户只负责：现场电气预检；必要时在 J2 断开状态刷固件；随后接通 J2，逐项给出
  **一次**可见刷新授权；观察画面/电气并回报；从已预制分支中选择下一项。
- 普通系统、协议、画质和重复性测试不要求每次切断 J2；只有刷固件、接线/电源配置改变、
  异常恢复或测试合同明确要求冷启动/断电隔离时才切断。
- 不能提前消费或批量签发可见刷新授权/claim，也不能在没有实测结果时伪造分支结论；
  但各分支的代码和离线证据必须提前备齐，避免现场等待开发。

## 软件状态

- 用户要求后续以“一次刷入、多次固定 action”提高效率；新路线冻结为
  `compare白→U07→白→八码atlas→白→U04六初态→白→U07六初态→白`。每个 action
  仍有独立 claim/授权/prior gate 和持久 ordinal，但正常动作之间不再 reflash、RESET 或
  J2 cycle。详细路线见 `EC5_COLOR_EXPANSION_NEXT_SESSION_PLAN_2026-08-10.md`。
- 自包含执行权威已冻结在
  `.test-output/hardware/MF1750_EC5_COLOR_LAB_REAL_COMPARE_BOUND_20260809_V2_SELF_CONTAINED/`。
  release 每次执行前都 deep replay compiled campaign、13 个 ELF symbol/7 个角色、BIN app
  descriptor 的 ELF SHA、23-action predecessor 链和 bundle 内文件 hash；旧 V1 已加机器可读
  superseded 标志并由 campaign/physical CLI fail-closed 拒绝。host runner 已覆盖 J2-OFF
  4 GET/0 POST 诊断、same-boot、精确 NVS/counter、claim-before-ARM、单 ARM/EXECUTE/driver、
  逐 ordinal 人工观察与无中间刷新证明，并可用 `observation-template --ordinal` 输出简化核对项。
- 新增 `host/runtime_waveform/contracts.py`、`format_registry.py`、`evidence.py` 和
  `tools/mf1750_runtime_waveform_contract.py`，把“软件虚拟通道”定义为
  `waveform profile × 3-bit target × primer/history`，同时明确当前 transport 每个 profile
  只有八码。合同严格拒绝非双控 3-bit、缺 decoded format/payload、缺电气/温区/phase、
  缺 OTP 等价/恢复/牺牲屏/硬切断或含 OTP/nonvolatile 命令的候选；P0b 又要求 evidence
  bundle 中 panel/batch/controller、电气、恢复、review 与全部实际 artifact bytes 深绑定，
  并只接受受信注册表内冻结的逐 CS `0xE9→0x20` 参数长度/SHA/前序。生产注册表当前为空，
  manifest 字段全真仍不能 `offline_contract_complete`。专项 `33 passed`，Ruff、py_compile
  PASS；它没有 hardware/network transport，任何 evaluation 均保持 hardware/refresh false。
- P1 新增 `host/runtime_waveform/execution_plan.py`：输入 manifest 必须逐字等于 canonical JSON，
  再深验 P0 evidence 和受信 registration；输出逐步冻结 controller target、opcode、参数长度/SHA
  及 predecessor identity，不输出任何参数/payload byte，不携带 callback 或授权。当前空生产
  registry 对所有真实候选稳定输出 `BLOCKED_FORMAT_NOT_REGISTERED`；synthetic test registration
  只用于覆盖确定性、篡改、CS 交换、缺段、未知 opcode/顺序和 canonical hash，不构成格式注册。
- P2 新增 `host/runtime_waveform/transport_state_machine.py`，固定 compile gate=false 且只接受带
  明确 marker 的 mock sink；它不导入 GPIO/SPI/serial/HTTP/driver，也未加入任何 PlatformIO
  `build_src_filter`。状态模型从 BLOCKED 出发，仅在测试注入的 P0/P1 synthetic plan 下模拟
  preflight→CS1/CS2 profile identity→双 DTM identity→BOTH refresh→safe finish；任一失败永久
  terminal，不自动 retry、切 profile、恢复或刷新。生产空 registry 仍为零 event BLOCKED。
- P3 新增 `host/runtime_waveform/campaign.py` 与离线 build/validate CLI，固定 12 个 declaration：
  K0/C1/C2 atlas 各自紧跟 OTP 白恢复，ordinal6 为第一 safe stop；C1/C2 各自 8×8
  old→new primer/target 后紧跟 OTP 白恢复，ordinal12 最终停止。输出双控反序/镜像 layout、
  四张 1024×600 pseudocolor、人工记录表、线性 action DAG 与 SHA 清单；所有 profile/payload/
  action materialization identity 均为 null，bundle 不含 BIN/ELF/授权串，0/12 可执行。
- P4 已冻结 `RUNTIME_WAVEFORM_SOFTWARE_ENVELOPE_P4_2026-08-10.json`：P0--P3 专项
  57/57，加入 STM audit/repo contract/EC5 recovery/compiled identity 后最终 145 passed、
  1 skipped；Ruff/py_compile PASS。默认与 EC5 recovery 均只做 PlatformIO build、未 upload；
  recovery 与当前实测 `f8f86fca...e793` 精确一致。两个独立 PlatformIO 配置会互相清理
  `.pio/build`，因此首轮相邻测试曾有 1 个“recovery artifact missing”环境性失败；补建后整组
  52 passed/1 skipped，原失败与修复未隐藏。P0b--P4 未修改 `src/` 或 PlatformIO 配置。
- 新增 STM32/OQC 参考已完成只读深审计：1024×600 双 E2802 与当前架构相符；`0x20`/535-byte
  runtime-LUT 机制真实存在。选中的随包历史 MAP 表明其 build 启动显示仍走 OTP，`loadWF`/
  842-byte 包没有链入；另一路曾链接的 UART LUT 是 2-bit、master-only，并有 VCOM/Frame
  未应用、全屏 TRES/无 CCSET、输入长度未检查、BUSY 无超时和白填充值冲突。当前
  `User/main.c` 更新于 MAP 后，MAP 不能证明当前源码构建状态。结论为
  `compatibility_ready=false`，不得把参考
  payload 直接用于 ESP32 或真屏。审计工具/测试位于
  `tools/mf1750_stm32_waveform_audit.py`、`tests/test_mf1750_stm32_waveform_audit.py`。
- 厂家后续说明“通过蓝牙传输，可设置亮度和对比度”。当前样例实际控制入口是 PA9/PA10、
  115200 8N1 UART；帧含 `41 41`、大端长度、command/subtype、CRC-16、`0D`。cmd5 固定复制
  535-byte waveform，cmd7 读 register `0x81` 的 VCOM，cmd8 仅把 payload 首 byte 写到全局
  `vcom` 并 ACK；没有范围/单位，later apply 只出现在非全路径、master-only legacy init。
  两目录/ZIP/可打印二进制字符串没有 BLE/GATT/SPP/UUID/App 或 brightness/contrast/gamma
  命令，故只能保留 `BLE module/App → UART` 为待证假设。也必须区分 host 图像预处理、
  profile 选择/上传和 VCOM/其他电气写入；未取得逐档 packet/UART/EPD trace 前不解除硬停止。
- EC5 Stage A 已冻结为固定单 action 执行链：U04/U07 编译期隔离，设备侧两步
  `arm→execute`，NVS 持久 `virgin/claimed/consumed/fault`，异常或重启 fail-closed；
  无网络清锁、raw ingress、启动刷新、重试或自动恢复。host 在首个 POST 前原子永久
  claim；U07 深验真实 U04 result、真实主机时间 `0/5/30 min` 观察、原生白恢复和人工
  review。冻结目录为
  `.test-output/hardware/MF1750_EC5_STAGE_A_RELEASE_OFFLINE_20260809_V1`，manifest
  file SHA=`809529097f4e890fabd915f537c3f20acbc87fe09e9320e759117d69a205be39`，
  canonical SHA=`adedbbdfe7ccacb3705149282689db46407261e834298c2b5c77dd285eb6d7dd`；
  U04/U07 binary 均 778000 bytes，SHA 分别为
  `28a7b5585da123e518a43f2c810a19ec09287410d3de3496b379666180f5649e`、
  `60ccfd7213da65c603219b3304e8f255d3124dc39b4827213fbf77302b8afe24`。该 V1 release
  已因 U04 DTM SHA-256 数组抄写错误整体隔离，不得继续上机；当前 A1 真屏 `1/5`
  finalized，A2 尝试已消费但显示序列未启动。
- U04 A2 根因已确定，不再归为笼统 FNV/面板故障：V1 driver 将正确 DTM digest
  `a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00`
  错写为
  `a8056cdd450f70709ec75a0a0400dfbfb1f06000ae596420902156bec7bab00d`，
  因而 `ec5IdentityMatches(cs1Identity)` 必然失败并在 `epdPrepareCascade` 前返回。
  原 result/readback 保持不改；法证补充 canonical SHA=`30c27f69...c9b50`、file SHA=
  `660eac73...c73e`，位于当前 Stage A physical session 的
  `a2-u04-forensic-supplement.json`。原 V1 bundle 保留原样并已隔离，不得再刷入或执行。
- Stage A corrected-v2 已完成离线开发、clean build、发布和深验。新 bundle 为
  `.test-output/hardware/MF1750_EC5_STAGE_A_CORRECTED_V2_RELEASE_OFFLINE_20260809_V1`；
  manifest file SHA=`b8950331e1281b06d867e0ce3ba79a923ea79a0e22e4d62eb2cd07ecbd68b605`，
  canonical SHA=`0c7fd578537177308398e973c794b895f929d16b785b8573e920f8f564b42183`。
  U04 BIN/ELF 为 783600/13219840 bytes，SHA=`f73ea080...a9338b`/`dcb48fe7...c78659`；
  U07 BIN/ELF 为 783600/13219876 bytes，SHA=`a2179d3d...bdfb8`/`b33f803a...724e5`。
  新 action 为 U04 `f03e5352...c8d3`、U07 `8f427d12...6ae`；旧授权不会匹配新身份。
  设备采用 API V3/top schema 3/driver evidence schema 2，legacy `mf1750_ec5` 只读，新状态仅写
  `mf1750_ec5v2`；主机诊断固定为 J2-OFF 4 GET/0 POST/0 claim，后续 `run` 必须在任何
  claim/POST 前重放该证据，并以同 boot nonce 完成 J2-ON 4 GET。全部 EC5 回归
  `159 passed, 7 subtests passed`；Ruff、`py_compile`、compiled ELF identity gate 全通过。
  21:48 在用户确认 J2 OFF 后仅将 U04 写入应用区 `0x10000`，写后 digest verify PASS，
  bootloader/分区表/NVS 均未擦除。随后 J2-OFF 诊断以 boot nonce `38c094c5efd0a69c`
  精确完成 4 GET/0 POST/0 claim，evidence file SHA=`ba458a57...e428e`；当前可见动作仍为 0。
- EC5 Stage B 已实现无抖动的六初态×双 DTM 镜像资产：每半屏六个 `24×24`
  均匀 ROI，初态为白/黑/红/黄/蓝/绿，target 全部写入同一候选码，没有空间混色。
  U04/U07 各自九步、三轮 `primer→target→white`；设备侧持久 ordinal/phase
  和 150 s cooldown，host 必须用 target `0/5/30 min` 真实观察门及 white recovery
  PASS 阻止自动串行。每个获批候选真屏 `0/9`；U07 还必须先通过 Stage A 门。
  Stage B 冻结目录为
  `.test-output/hardware/MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1`，manifest
  file SHA=`db441f6e37215ffc7e8b6a365c3d7424d99fd301162b564a270e5af6bf4e7527`，
  canonical SHA=`b500fee26d57b11b0bf9f8441076dce5982516429794bed49f04f4ae2bcbdb04`；
  U04/U07 binary 均 783888 bytes，SHA 分别为
  `722b69326fb562c7d79b1f10e5993d9f5acb82ca2b7343b63d4a7abb0e1ff0fc`、
  `815ac96e345ebab1f90c0aa1fd5e9f4254f9af09c5ddba2d2ed58c87bcbc3c06`。
- 2026-08-09 根侧完成六环境 clean build，均未上传：production 815664 bytes /
  `611cf5c0d043119f6cf34ddc97b3b5a656d4220993b206804e1b75d43433daf9`；N7 775536 bytes /
  `19e153b24472577191f7a745024ac6dc488206e5da76fe40d57592ebaba32747`；Stage A 与
  Stage B 四个 binary 如上。隔离扫描确认 production/N7 不含 EC5 身份，每个候选只含
  自身身份。production 新 build 不能冒充恢复固件；A1/A3/A5 必须使用昨晚归档且实测的
  815664-byte RC2G `9df897...0cd772`。当前源码新 build 不替代 8 月 8 日冻结 N7 artifact。
- EC5/driver/STM32/旧 campaign 联合聚焦回归为 `193 passed, 59 subtests passed`；相关
  Python Ruff 全部通过，两级 release deep validation 与 U04/U07 离线 `describe` 均为
  0 network / 0 claim。全过程零设备、零串口、零网络、零刷写、零上电/断电控制、零真屏刷新。
- 全仓诊断运行完成到 `998 passed, 593 subtests passed`，同时暴露两个共同根因：旧
  N2/N3/N8 将冻结 RC2G 错指向可变 `.pio` build，N7 handoff 缺失精确冻结句。现已改为
  归档 RC2G `9df897...0cd772` 并恢复 N7 声明；原级联覆盖组随后
  `60 passed, 67 subtests passed`，N7/仓库合同/任务板 `46 passed`，最终设计 SHA 对应
  campaign/analyzer `27 passed`。该历史回归未检测到后来在真机执行路径暴露的 U04
  driver digest 字节数组错误；“当前无已知失败路径”已由 20:30 事故结论明确撤回。
- 10 条确定性显示器模拟/混色路径和四阶段 `source/mapped/final/model` 预览已实现。
- 自然照片候选合同已升为 schema v2：原图字节、MIME、标签、权利声明、fit/rotation、
  归一化 provenance 与各级 SHA 均冻结；绝对路径标签、布尔 schema、源/目录祖先
  symlink/reparse、非本地解析路径和验证模式生成参数全部 fail-closed。旧 synthetic schema v1
  仍可深验证；早期照片 smoke V1 不再是有效 evidence。
- N2 风车自然图 Q1 Atkinson 与 Q2 area-weighted blue-noise 已按同源、同 crop、同 seed、
  同 mapping/profile 生成并深验证。二者相差 `255186/614400` 像素（41.53%），覆盖全部
  160 个 64×60 瓦片，具备离线 A/B 区分度；二者均已完成 MAP→target 真屏，Q1 PASS、
  Q2 visual FAIL，相关 claims 均已永久消费。
- Q3/Q4 根因已修正为可审计的 DBS report schema v2，并把候选工具预算上限与应用层统一到
  1,000,000（默认不变）。262144 evaluations 下两者 proposal trace 完全一致，各为 65431
  proposals、61529 unique primary、11.501% 未锁像素覆盖、160/160 瓦片、左右
  50.38%/49.62%；共同 source/mapped/profile/mask/initializer/seed/budget 全部一致。
- Q3/Q4 双目标交叉裁决 PASS：identity loss `Q3=0.0176701891009463 <
  Q4=0.017727477929818176`；overlap loss `Q4=0.014062116478467735 <
  Q3=0.014088430140269625`；二者自身 loss 都低于共同 initializer。最终差 6530 像素
  （1.063%，左右 3483/3047、覆盖全部 160 瓦片）。二者仍以 evaluation budget 停止，
  只能称 bounded candidates，不称收敛/qualification。
- N2P 自然图 campaign compiler 已完成：深验证四个正式 bundle，冻结 4 个互不串联的
  controller-fresh session、8 个唯一 P0 action identity 与 8 个 workspace-global claim
  declaration；manifest canonical/file SHA-256 为 `976ab0...5c825b` / `d7d55f...21d687`，
  P0 canonical SHA-256 为 `f23476...45cdb`。固定 once runner、人工 observation finalizer、
  同 cell prior/result/claim 深绑定和四格离线总评器已经完成；runner+analyzer 根侧最新
  `19/19 PASS`。总评只在八条链全 PASS 且唯一最高总分时输出 `N3_branch_selection_only`，
  平分不擅自选；相机仅在四个 target 全有同配置已验字节时才 comparable。整个实现阶段
  零真实 claim、零授权、零网络/设备 I/O；现场仍由 reviewed limit/runtime gate 阻断。
- RC2G MAP、macro4、通用质量 action、N1 primer/target 的单次 claim、单 POST、无自动
  retry/recovery、job/op/hash/BUSY/GPIO 取证路径已实现。
- 2026-08-08 N2/Q1--Q4 断屏预检已在 `http://192.168.1.14` 执行：RC2G/API V3/1 MHz/mapping/
  PSRAM identity 精确匹配；MAP 设备生成返回 307200 bytes、`0x9D04142D`、`epd_action:none`；
  四个正式候选 ingress 的本地/设备 FNV 均匹配且返回 `epd_action:none`，零 `/api/frame`、
  零 claim、零刷新。但 Q1 后的只读 GET 仍为历史 job2，Q2--Q4 序列后的 GET 已变成 job0，
  report 为 `no_completed_job_report`，说明区间内发生控制器重启/重新初始化；用户随后确认曾
  重新插拔 ESP32 USB，故归因为明确的人为 session boundary，不推断固件稳定性故障，跨重插
  连续性也不继承。代理未发送 restart、reset 或刷机命令；J2 全程断开且最终 RST/CS1/CS2
  均低。独立 blocker 仍有 `reviewed_limit_profile_missing`；旧 RC2F
  `DRAFT / VISIBLE_REFRESH_NO_GO` 不得冒充 reviewed JSON。
- 自然照片/预算合同新增后聚焦回归 `10/10 PASS`；与原 panel-candidate 回归合计
  `22/22 PASS`。DBS telemetry/application 聚焦 `40/40 PASS`；旧 v1 DBS bundle 仍深验通过。
- P0 共用 visible-refresh campaign 离线底座已实现：limit profile、usage/cooldown/温度、
  session/action、prior result SHA、workspace-global claim declaration 与 describe-only fail-closed；
  新增 `16/16 PASS`，不含执行/网络路径，也未改 N0/N1。
- N4 V3 联合 solver 已在有界确定性预算内使 high/low 各自的 total、左右 internal edge、
  seam、boundary 五项跨 B exact 相等（tolerance 0），同时严格保持 global/half 6×6、六码
  histogram 与 changed。更细的 H/V、半屏 boundary、seam-pair 残差公开，因此只声明
  `selected_metric_orthogonality=true`，全面 strict/causal/hardware/upload 仍为 false。
- N4 V3 固定执行层和因素分析器已闭合：8 个 action 只允许四个独立 MAP→target 链，
  workspace-global claim 必须在网络前原子落盘，每 action 最多一次 POST，禁止自动
  retry/recovery；target 必须引用同格 MAP 的 finalized PASS whole-file SHA。分析器只接收
  claim/lock/profile/protocol/人工观察/finalization/result 深验闭包并派生因素量；同格禁止
  重启或断 J2，nominal 跨格可保持 J2 接通。根侧合并回归 `49/49 PASS`，仍只作
  `EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY / NOT_QUALIFIED`。
- N7 2026-08-08 冻结软件包已完成：其归档 RC2G 为 815664 bytes / `9df897...0cd772`；
  归档最小 N7 binary 为 775536 bytes / `81e905...cb66`，仅含五个固定 sweep POST 与
  version/job/report/status；无 `/api/frame` 或任意频率入口。campaign/once runner/analyzer/
  repo contract 当时合计 `72/72 PASS`，未刷 ESP32、未创建真实 claim/授权。当前源码因
  后续 driver 诊断变更会生成新 hash；旧 V1 archive 不变，二者禁止混用。
- N6 production physical operator 已完成：`describe/materialize/serve/finalize/validate` 无 caller
  时间/计数注入；N5 physical aggregate 必须从全部 raw observations、标准表、仪器资格、strict
  finalized bundle/result dirs/reviewer key 重建并 exact 比对，core-only/self-resealed 输入拒绝。
  claim 固定仓库全局根且先于网络，exact `N6HttpRefreshDriver` 最多一条 frame POST；receipt/commit
  在 HTTP 成功响应前同步耐久落盘，claim 后 `BaseException` 生成 durable UNKNOWN receipt 或固定
  per-claim incident，二者与 finalize/validate 排他。真实 Playwright `1.58.0` / Chromium
  `145.0.7632.6` physical E2E 覆盖四 preview、三 token、matching job/report、reload/duplicate lock。
  最终 core `12/12`（5 subtests）、CLI `7/7`（14 subtests）、Chromium `1/1`、Ruff/compile PASS；
  真实路径仍因 measured palette/profile、formal review/limit/runtime/prior 缺失而关闭，不伪造资格。
- N3 白天固定执行层已完成并绑定正式 natural-photo N2P：N3A 预制 Q1--Q4 四个潜在胜者、
  每支 repeat-2/3/4（12 campaigns、36 sessions、72 actions）；N3B 用固定 seed 的四阶
  Williams 顺序（4 campaigns、16 sessions、32 actions）。104 个 action identity/claim
  filename 全局唯一；每 session 仅 own MAP→target，跨 branch/repeat/block/position replay
  拒绝。默认 controller fresh boot 但 J2 可保持通电；只有带 review SHA 和正 dwell 的
  panel-cold profile 才要求 J2 cycle。分析器对 `n<10` 强制 P95/P99=null，只给 observed
  maximum/mean/range/sample SD 与有证据的 U95。exact compiler 会深验 N2 八目录，只在
  唯一 winner 时物化一个 repeat-2/3/4 分支；tie/null 拒绝，绝不串播 72 actions。
  N3B 固定四个 Williams blocks/32 actions。一次性 runner、人工 finalizer、MAP→target
  result+finalization 双 SHA prior 和 deep-bundle-only analyzer 已闭合；根侧合并 `51/51 PASS`。
- N5 白天测量软件/operator 链已完成：不内置标准样表的外部 CIE D65 SPD / 1931 2°
  CMF 严格积分、正式 palette 36 个 raw observations 和正式 transition 360 个
  raw slots 的防重放聚合已实现。transition 主统计先将 CS1/CS2 配对成 5 个
  repeat aggregates，因 `n=5` 强制 P95/P99=null；raw `n=10` 只作 paired diagnostics。
  冻结默认 manifest canonical/file SHA-256 为 `608ddc...f4c3` / `578d9b...6065`；
  三计划固定执行器可物化 26 sessions/73 actions，原子 claim、最多一次 POST、即时前序
  PASS whole-file SHA、人工测量与 action/session finalization 均已闭合；正式聚合拒绝
  任何未经过 finalized-bundle 深验的合成观察。根侧全 N5 `50/50 PASS`，最终受影响组
  `25/25 PASS`。生产 CLI 已闭合 `list/describe/run/finalize/build-session-bundle/validate`：
  外部 sealed profile→73 actions/26 sessions，same-dir temp+fsync+hard-link exclusive publish，
  回读 canonical/manifest/execution 深验，并发只允许一个 winner，既存文件绝不覆盖。run 在
  首次 GET 前原子占用仓库全局 claim，只允许一次 exact POST；原始 HTTP transcript、字节数、
  hash、顺序与语义均可深回放。PASS 与合法 UNKNOWN 都先持久化 outcome-ready terminal evidence
  再提交最终 action；写盘不确定性转永久 incident，禁止重试。正式测量 PASS 必须槽位完整，
  FAIL 只接受冻结有序前缀且必须记录 notes；FAIL/UNKNOWN 会封锁同计划后续 action。正常
  descriptive/palette 不要求逐 action 断 J2；formal transition 每个六 action session 只冷启一次，
  session 内持续供电，terminal target 后人工断 J2。完整 N5 八模块 `77/77 PASS`，独立复审
  分批 `36/36 + 41/41 PASS`；这仍不代表仪器、profile 或真屏已通过。
- C3 参数化转移感知优化器已完成：`alpha/beta/gamma/delta` 目标、完整实测
  6×6 profile 门、known/unknown old-frame 语义、transition histogram、跨 panel/build/waveform
  `TransitionInputBinding` 和无自动胜者 Pareto 报告已实现。`beta=gamma=delta=0`
  与原 C2 quantizer 帧/码逐字节一致；缺测默认拒绝，显式 fallback 始终不合格。
  纯离线 CLI 还可写出并深验 frame/preview/report/Pareto/manifest 闭包，且无设备、授权、
  claim 或上传入口。专项 `15/15 PASS`、C2/profile 邻接 `48/48 PASS`；当前固定全局
  waveform 下始终禁止 BUSY 缩短声称，输出仍须 N5 实测输入和真屏资格。
- N1 相关四组聚焦回归最新为 `56/56 PASS`。
- 最终全仓回归覆盖当前全部 87 个 `tests/test_*.py`，四个互斥分片零漏项：
  `1018/1018 PASS`、`494 subtests PASS`、0 skipped。A 分片原单进程两次只触发外层工具
  1200/900 s 时限且没有可用汇总，未被冒充 PASS；随后拆为 212+69+53+74 四批全部 exit 0。
  全仓 Ruff、`compileall app/host/tools/tests/hardware`、JS syntax、repository contract 11/11、
  board/repo 41/41、额外 parser/legacy 文档审计 43（9 subtests）、Markdown fences 与
  `git diff --check` 均通过；diff 只有既有 LF→CRLF 提示。测试期间 socket 硬阻断零命中，
  仓库本轮新增真实 claim/incident 为 0。
- 2026-08-08 历史双固件重构建曾精确复现：RC2G `firmware.bin` 815664 bytes / SHA-256
  `9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772`；N7 775536 bytes /
  SHA-256 `81e905d299a0011d2f9617621e20e3262baea42aa9a6360522618bbb2414cb66`。
  这是冻结 artifact 身份，不是 2026-08-09 当前源码 build 身份；当前 hash 见本节顶部。
- 历史 synthetic Q1--Q4 编译器仍保留为测试卡证据；正式自然照片四 cell 已由上述 N2P
  compiler 替代，Q3/Q4 coverage 与双目标交叉风险门通过。固定执行代码已完成，但 8 个
  真屏 action 均未授权/消费，因此“活动代码已实现”仍不等于“真屏测试已完成”。
- N3--N8 文件级 gap audit 与 production software 实现均已完成；hardware-ready 仍受刷新限额、
  仪器、供应商数据、现场环境和逐 action 授权约束。共用 limit/session/action 底座、全部
  physical runner/finalizer/analyzer、N6 浏览器链、N7 最小固件及 N8 supervisor 均已冻结；
  这些完成项没有访问单独供电的 ESP32，也不能替代真实硬件证据。
- N8 固定执行层已完成：15 个 exact action/5 sessions/10 prior dependencies 均由
  workspace-global claim-before-network、最多一次 POST、人工 finalizer 和递归 deep bundle
  validator 约束。Warm 保持 source 的 `supervised_continuous`，不要求重启；首 MAP 读取并
  记录动态 zero/nonzero job/op baseline，后续严格相邻。Analyzer 只接收 finalized bundles，
  复核相机、外置温度、电表、时钟和连续性，始终输出 `NOT_QUALIFIED`；根侧 `32/32 PASS`。
- 统一 N2--N8 晚间任务板已建立：冻结安全总门、逐 action 六步循环、停止条件、正常不逐次
  断 J2 及 N5 cold/N7 每档断屏例外；N2/N4/N5/N7 的真实入口、观察项和分夜建议已列明，
  N3 与 N8 的 exact compile/describe/run/finalize/analyze CLI 及冻结 action 顺序均已补齐，
  全板不再含 TBD/收口中/入口待占位；N6 保持 measured gate。根侧文档与 repository
  contract 最新 `41/41 PASS`，没有预制授权或 claim。
- 全项目离线算法、固定计划、人工 finalizer、结果深验证器和晚间任务板仍为 `7/7 READY`。
  2026-08-08 首次真实 N2 preflight 进一步发现 production live 安全缺口：N2/N4 campaign
  panel serial 仍为 `UNBOUND-N2P-OFFLINE`；N2/N3/N4 共用 limit profile 的 usage/review
  SHA 只验 64 位格式、不读取证据文件，且 allowlist 可只含当前 action 仍 contract-ready。
  因此当时“production operator 7/7”结论曾撤回为“离线计划 7/7、production live 4/7 未受
  此问题影响、3/7 修复中”；这些缺口随后已按本页后续日志全部闭合，当前恢复为 7/7，旧
  unbound live 必须在 claim/network 前 hard-block。网络随机
  照片、R2、未知码/扩色、H2 仍受用户选择、供应商资料、牺牲面板、
  仪器或设计输入阻断；auth/TLS、持久 job/history、remote cancel、chunked upload 属于独立
  发布安全 scope，不应暗中混入本轮真屏测试。

## 当前证据入口

- 总 runbook：[`MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)
- SPD1657 主逆向/目标/公开检索：
  [`SPD1657_STM32_REVERSE_DELTA_2026-08-11.md`](SPD1657_STM32_REVERSE_DELTA_2026-08-11.md)、
  [`SPD1657_GOAL_COMPLETION_AUDIT_2026-08-12.md`](SPD1657_GOAL_COMPLETION_AUDIT_2026-08-12.md)、
  [`SPD1657_PRIMARY_SOURCE_ABI_HUNT_2026-08-12.md`](SPD1657_PRIMARY_SOURCE_ABI_HUNT_2026-08-12.md)
- arithmetic schema2：`../tools/mf1750_spd1657_arithmetic_transform_audit.py`、
  `../tests/test_mf1750_spd1657_arithmetic_transform_audit.py`、
  `../.test-output/offline/mf1750_spd1657_arithmetic_transform_audit_20260812.json`；
  report file/canonical=`73003d11...8a4a`/`b77e5edb...015c`
- UBROF11 E2 projection schema2：`../tools/mf1750_iar_ubrof11_e2_projection_audit.py`、
  `../tests/test_mf1750_iar_ubrof11_e2_projection_audit.py`、
  `../.test-output/offline/mf1750_iar_ubrof11_e2_projection_audit_20260812.json`；
  report file/canonical=`7d3ff40f...36bc`/`15647b3c...683c`
- final D43 provider chain：`../tools/mf1750_iar_final_d43_provider_chain_audit.py`、
  `../tests/test_mf1750_iar_final_d43_provider_chain_audit.py`、
  `../.test-output/offline/mf1750_iar_final_d43_provider_chain_audit_20260812.json`；
  report file/canonical=`7ed8e765...9886`/`51a646c7...8976`
- N0 MAP：`../.test-output/hardware/RC2G_MAP_BASELINE_20260807_200637/`
- N0 macro4：`../.test-output/hardware/G1S1_MACRO4_REDISPLAY_20260807_201203/`
- N1 MAP primer：`../.test-output/hardware/RC2G_N1_LOW_BALANCED_MAP_PRIMER_20260807_215617/`
- N1 low-balanced target：`../.test-output/hardware/RC2G_N1_LOW_BALANCED_PILOT_20260807_220545/`
- N1 人工对照图：
  `../.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2/low-balanced.strict-final.png`
- N2/Q1 断屏设备预检：
  `../.test-output/hardware/RC2G_N2_Q1_NONDISPLAY_PREFLIGHT_20260808_081257/PREFLIGHT.json`
- N2P Q1 Atkinson：
  `../.test-output/hardware/G1S1_N2P_WINDMILL_ATKINSON_OFFLINE_20260807_V2/`
  - frame SHA-256：`7aa33f337903b93ba094265e212909f5986ab48eebb0a2dd352b7571a6ea7c96`
  - manifest canonical SHA-256：`b4db35f2d1318a7bba352b0e501f443db530f8d4137ab9e46930561d8060d584`
- N2P Q2 area-weighted blue-noise：
  `../.test-output/hardware/G1S1_N2P_WINDMILL_BLUE_NOISE_OFFLINE_20260807_V2/`
  - frame SHA-256：`cdd3abf625f09ba759351b80ed358fdf8515fe3d776bdd862ac2e0433ceea4e3`
  - manifest canonical SHA-256：`95243d261338bddd6b718b39a2bbc8f112d8b26a74309f15095542db30f8f151`
- N2P Q3 multicolor DBS 262k：
  `../.test-output/hardware/G1S1_N2P_WINDMILL_MULTICOLOR_DBS_262K_OFFLINE_20260807_V2/`
  - frame SHA-256：`0a9e2da80ced18ad7f7345906a78c53e7b720468c254365a5fc44502576b1a77`
  - manifest canonical SHA-256：`f8535120a430b2b672c968f5a335744a8b5e9c9e02a8d8e96eecbff617021ce1`
- N2P Q4 overlap-aware DBS 262k：
  `../.test-output/hardware/G1S1_N2P_WINDMILL_OVERLAP_DBS_262K_OFFLINE_20260807_V2/`
  - frame SHA-256：`4183b84b40578589938531076eb92845aa53f533c6e29ee5a54986903c7e8f86`
  - manifest canonical SHA-256：`7d2af4ca143f8c3d1dfefa0b9b7845852ef53498706e228b5a8acdc57fa35b5f`
- N2P 四格 campaign：
  `../.test-output/hardware/G1S1_N2P_PHOTO_CAMPAIGN_OFFLINE_20260808_V1/campaign.json`
  - manifest file / canonical SHA-256：`d7d55f62f6e2392d42dd8d65ea5cd5d7c0c5179b4cd51b9109666b420a21d687` /
    `976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b`
  - P0 campaign canonical SHA-256：`f23476c4c887057877e3f3f6c9315813bb761f6da57996b9eea538584a545cdb`
- N2P 固定执行/总评：
  [`N2P_RC2G_FIXED_EXECUTION_V2.md`](N2P_RC2G_FIXED_EXECUTION_V2.md)、
  `../tools/g1_s1_rc2g_n2_photo_campaign_once.py`、
  `../tools/g1_s1_rc2g_n2_photo_campaign_analyzer.py`
  - execution supplement canonical/file SHA-256：`29cdb6ccb75d320d3b1e1fa6ea544f88196b16ca38d1f34ec84343afdc787099` /
    `f1d22bc22a0487bb0cd31b6be7d0c80ccb8f3ae2a86b60c88a8a11ec312865af`
  - scoring / camera / analyzer contract SHA-256：`7e2aa7e7ac9f85271e2b18101546f5a82b35966d21e93f0037449ef3762076a9` /
    `6e274ff0b3eb2ae35706e43e516b8a765eaaa280b062cecb6ddf06952f29901c` /
    `3638e26f80c8e0a9da81760c3ca3d177d7a43591a813f030446100ec87fb7a86`
- N4 V3 2×2 bundle：
  `../.test-output/hardware/G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/`
  - manifest file / canonical SHA-256：`17a820d84cb24fe0950a9653d6f6831104e0d872f7167c47f262c18fad559bfb` /
    `3f4852af1151d5c56db1d7c540f3c131ae6c05de1dce8db625864b2900d0e6d7`
  - proof file / canonical SHA-256：`3b1a41fc2b772adf12286a7ae41745ef074a50b401e377597041fc38081115ef` /
    `9566f7198b5fa2ed26b3cc386a9faa23a8a99ff7bace604e164eb7b159b87be5`
- N4 V3 固定执行/深证据分析：
  [`N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`](N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md)、
  [`N4_V3_RESULT_ANALYZER_OFFLINE_HANDOFF_2026-08-08.md`](N4_V3_RESULT_ANALYZER_OFFLINE_HANDOFF_2026-08-08.md)
  - execution contract / runner / analyzer SHA-256：`8d962f...17d933` / `f24d85...3272e1` /
    `b96d4d...ed7592`；shared execution canonical/file：`fc91f3...74f2f0` / `d088f7...3f88e0`；
    analyzer canonical/file：`b37074...e4dae8` / `d0d467...1ad98cb`；根侧 `49/49 PASS`；零设备 I/O。
- N7 冻结软件包（尚未刷入）：
  `../.test-output/hardware/MF1750_N7_SPI_SWEEP_OFFLINE_20260808_V1/`；campaign file
  SHA-256 `a2191de2060b3ec754300ec2166475afa8647a26ca79be18404a45c0bdc9282a`；
  firmware 775536 bytes，SHA-256
  `81e905d299a0011d2f9617621e20e3262baea42aa9a6360522618bbb2414cb66`。
- N6 physical production/browser 移交：
  [`N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md`](N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md)
  - durable I/O / visible compatibility core / physical core / physical CLI SHA-256：
    `f8b564...a339e` / `ee97a0...e63af` / `40ab9d...7be14` / `15fc0d...e26c7`；
  - physical core / CLI / Chromium E2E：`12/12`（5 subtests）/ `7/7`（14 subtests）/
    `1/1`；独立安全审计 GO；零真实设备/claim/授权。
- N3 离线计划/分析器：`../tools/g1_s1_n3_campaign.py`、`../tools/g1_s1_n3_analyzer.py`
  - N3A manifest canonical/file SHA-256：`3bf68ebea4a647b27387adf94fd9a04765a34dad564b7786068a60e21df2d42f` /
    `9de5648c06aaf1d87c4187a49a5bfe9a6da6dae52e9439f7736c71ec10c5f75d`
  - N3B manifest canonical/file SHA-256：`bae2a6e874ed45e04e9d42051f1d06e788c3f81f26e98acc33b69fc15ae02483` /
    `c6e1d79227ba87ba5f0dc2dddce055e82235d6b3806c5911710ec428a2832996`
  - 固定执行交接：
    [`N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`](N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md)；
    execution / exact compiler / runner / analyzer SHA-256：`e8c1b4...63097b` /
    `0e07c9...b13fe9` / `1482a1...a4a5f1` / `4ca7a5...afe6f9`；默认 asset-blocked
    N3B exact plan canonical/file：`1fdb1d...f65de0` / `9bbcad...fcdec8`；根侧 `51/51 PASS`。
- N5 光谱/测量计划/聚合：
  [`N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md`](N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md)、
  `../host/extended_color/spectral.py`、`../host/extended_color/aggregation.py`、
  `../tools/mf1750_n5_measurement_campaign.py`
  - 默认 manifest canonical/file SHA-256：`608ddc072f433fdce53c126508e2ba7d79ac83f19ee6e13dcd023035c804f4c3` /
    `578d9b0b1438fbb2a8a0df2d9053db961b96bbfa8de5d47cdc42f70b03b06065`
  - 默认 execution contract canonical/file SHA-256：`b14d0e8dd4dff16268e29eb557a5c85b310acc10d59731ba3f9d4accb5bc832c` /
    `c02e9956f14ea9ea92283691d44b3971685cbd19a9670e2508aed36303da93eb`
  - execution / aggregation / CLI SHA-256：`c3dc84...b68db` / `a6aded...e9c26` /
    `631b87...b4f91`；26 sessions / 73 fixed actions；零真实 claim/授权/网络/设备 I/O。
  - campaign / fixed operator / execution core / RC2G protocol SHA-256：
    `4c9b4d...dd2d3` / `715a26...14185` / `32558b...f900f` / `d55d69...a45c`；
    compile/operator/protocol 测试 SHA-256：`15fde3...c1636` / `8d944c...ed13` /
    `84176e...6cc8` / `7bc180...be5b`；完整八模块 `77/77 PASS`，独立复审无 blocker。
- C3 转移感知优化器：
  [`C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md`](C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md)、
  `../host/transition_optimizer/`、`../tools/mf1750_transition_optimize.py`
  - optimizer / CLI / focused-test / repo-contract / handoff file SHA-256：
    `871568...b2f29` / `b15448...eb777` / `7b002d...32c86` / `343ecb...d5a78` /
    `9c70f1...2c62a`；`15/15 PASS`；零设备 I/O。
- N8 离线计划/账本/分析器：
  [`N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md`](N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md)
  - manifest canonical/file SHA-256：`0914e9a63cc18593b27b1f51cf86e7a29a4c65a17b0427b5d4717ee745b8ba91` /
    `5d42dd01036512b836e286bb7c2f0735df36523b1434b84eb12bbba471c1e4ab`
  - nested P0 canonical SHA-256：`fb24ab9bc840f4af22047b062326b472fa8a9402281bd8059cc44afb4025caa6`
  - fixed execution contract canonical/file SHA-256：`51efc4a3...da976e` /
    `fd3ea6e1...6d5fbf`；execution / runner / analyzer SHA-256：`184e73...e4c02` /
    `9276ec...6fa86` / `9a8b8a...2144a`。
  - 5 sessions / 15 actions / 10 dependent result bindings；根侧 combined `32/32 PASS`；零设备 I/O。
- 统一晚间逐项任务板：
  [`MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`](MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md)
  - 根侧 board+repo `41/41 PASS`，额外 parser/legacy 审计合计 `43 PASS`（9 subtests）；
    N2--N8 均有 production physical 软件入口，全板无待收口占位。

## J2-1 自动电源控制候选（尚未实施）

- 当前 Rev A1 仍为外部 3.3 V/1 A 限流电源人工接入 J2-1，`EPD_PIN_SWC=-1`；没有软件可控
  物理切断，也没有刷新峰值电流证据。ESP32、驱动板和外部电源只共地，禁止把外部 3.3 V
  与 DevKit 3V3 并联。
- 最快台架方案：[`TPS22950Q1EVM`](https://www.ti.com/tool/TPS22950Q1EVM) +
  [`INA228` 模块](https://www.adafruit.com/product/5832) + 串联在实际 3.3 V 功率线中的
  常闭自锁急停。若台式电源支持 SCPI/USB/LAN/串口，可先读取并控制 PSU，但不能替代硬件
  急停或用于捕捉短于仪器采样窗口的尖峰。
- 易集成 PCB 候选为 [`TPS22950C`](https://www.ti.com/product/TPS22950) +
  [`INA228`](https://www.ti.com/product/INA228)：外部 EN 下拉保证 ESP32 复位时默认断电，
  电流/电压/功率/能量与 ALERT 可由 I2C 记录。TPS22950C 普通过流主要限流，不等同于
  短路锁存切断。
- 要求过流定时后硬件锁存断电时，候选升级为
  [`TPS259474L`](https://www.ti.com/product/TPS25947) + INA228；QFN 与外围验证更复杂，
  宜先用 [`TPS25947EVM`](https://www.ti.com/tool/TPS25947EVM)。它没有 TPS22950C 的集成
  快速输出放电，必要时另加受控放电路径。
- 最终器件、采样电阻、限流值和过流延时仍未冻结：必须先用已验收画面测 J2 刷新峰值、
  持续时间、3.3 V droop 和能量；INA228 最快转换约 50 µs，首次峰值仍需示波器。关电前
  继续先执行 POF 并把面板侧 GPIO 置低/高阻，实测排除 I/O 反灌。

N1 人工忠实度与电气结论由用户现场观察支持；本轮 evidence 目录没有留存固定曝光的
真屏照片，也没有单独量化刷新后的精确电流值，不应在后续报告中扩写成仪器测量结论。

## 强制更新规则

每个后续任务完成时，在同一轮工作内按以下顺序更新本页：

1. 更新“最后更新”、J2/授权/下一步状态。
2. 更新对应计数，明确采用“阶段”“session”还是“可见 action”口径。
3. 更新阶段表和完成表；不得把软件就绪写成硬件完成。
4. 写入 evidence 路径、exact action、job/op、关键 SHA 和人工裁决。
5. 在下方日志追加一行；历史结论只追加修订，不静默覆盖。

任何代理在本页未同步前，不得向用户宣称相应里程碑已经最终完成。

## 完成日志

| 时间（UTC+8） | 完成项 | 结论 | Evidence |
|---|---|---|---|
| 2026-08-07 20:06 | N0 MAP job1/op1 | 协议/电气/忠实度 PASS | `RC2G_MAP_BASELINE_20260807_200637/` |
| 2026-08-07 20:12 | N0 macro4 job2/op2 | 协议/电气/忠实度 PASS；算法画质差 | `G1S1_MACRO4_REDISPLAY_20260807_201203/` |
| 2026-08-07 21:56 | N1 MAP primer job1/op1 | 协议/电气/MAP 忠实度 PASS | `RC2G_N1_LOW_BALANCED_MAP_PRIMER_20260807_215617/` |
| 2026-08-07 22:06 | N1 low-balanced job2/op2 | 协议/电气/strict-preview 忠实度 PASS | `RC2G_N1_LOW_BALANCED_PILOT_20260807_220545/` |
| 2026-08-07 22:12 | N1 安全收尾 | 用户确认 ESP32 全程未重启，J2 已物理断开 | 同上 `MANUAL-OBSERVATION.json` |
| 2026-08-07 22:27 | N1 软件/证据收尾 | 558/558、合同、语法、diff、build 与 evidence SHA 全 PASS | 本页及两目录 `SHA256SUMS.txt` |
| 2026-08-07 23:16 | 自然照片候选合同 v2 | 新增真实 JPEG/来源/路径/schema 深验证；panel 合计 21/21 PASS | `tools/g1_s1_panel_candidate.py`、`tests/test_g1_s1_panel_candidate_photo_source.py` |
| 2026-08-07 23:19 | N2P Q1/Q2 离线候选 | 两个正式 v2 bundle 深验证；差异 255186 像素；零设备 I/O/零授权 | `G1S1_N2P_WINDMILL_*_OFFLINE_20260807_V2/` |
| 2026-08-07 23:21 | Q3/Q4 DBS 最大预算探针 | 16384 evaluations 仅差 396 像素，防浪费门 FAIL；继续软件根因修正 | `N2P_DBS_BUDGET_PROBE_*`（search-only，不提升为 evidence） |
| 2026-08-07 23:27 | 后续协作方式冻结 | 白天批量完成 N2--N8 可离线开发；晚上仅逐项授权、上机、观察和选择预制分支 | 本页“白天开发 / 晚上上机分工” |
| 2026-08-07 23:28 | 现场安全状态更新 | 用户关闭驱动板/J2 电源，ESP32 保持供电；继续离线回归/编译，不授权面板动作 | 本页“一眼状态” |
| 2026-08-07 23:38 | N3--N8 白天开发 gap audit | 文件级缺口、外部门、动作数量、实施顺序与验收合同已冻结；进入共用底座/N7 实施 | 本页“剩余阶段、数量和目的”及代理审计结论 |
| 2026-08-07 23:50 | DBS telemetry/schema v2 | proposal coverage/trace/左右/瓦片证据与 v1 兼容完成；focused 40/40、candidate 22/22 PASS | `host/halftone_optimization/`、`host/application/simulation.py` |
| 2026-08-07 23:53 | N2P Q3 multicolor DBS 262k | 11.501% coverage、160/160 tiles、deep validation PASS；bounded/non-converged | `G1S1_N2P_WINDMILL_MULTICOLOR_DBS_262K_OFFLINE_20260807_V2/` |
| 2026-08-08 00:00 | N2P Q4 overlap DBS 262k + paired adjudication | 同 proposal trace；双目标对角占优；Q3/Q4 差 6530 pixels；deep validation PASS | `G1S1_N2P_WINDMILL_OVERLAP_DBS_262K_OFFLINE_20260807_V2/` |
| 2026-08-08 00:01 | P0 共用 campaign 离线底座 | limit/session/action/prior/claim declaration fail-closed；16/16 PASS；无执行器/I/O | `host/visible_refresh_campaign/` |
| 2026-08-08 00:22 | N7 白天软件包 | 独立最小固件+5 fixed actions+永久claim+PASS链完成；72/72 PASS；默认RC2G exact不变 | `src/n7_main.cpp`、`tools/mf1750_n7_spi_sweep_*` |
| 2026-08-08 00:25 | N4 V3 离线构造/P0 campaign | 五项预注册指标 exact=0；4 cells/8 actions describe-only；V3 18/18、V2+P0 31/31 PASS | `G1S1_ROOT_CAUSE_2X2_OFFLINE_20260808_V3/` |
| 2026-08-08 00:28 | N7 binary/campaign 冻结 | 独立 bundle 写入并深验证；firmware `81e905...cb66`；零设备 I/O/零 claim/零授权 | `MF1750_N7_SPI_SWEEP_OFFLINE_20260808_V1/` |
| 2026-08-08 00:32 | 现场安全状态复核 | 用户再次确认驱动板/J2 断电、ESP32 单独供电；继续离线开发/编译，不访问设备、不授权面板动作 | 本页“一眼状态” |
| 2026-08-08 00:49 | N2P 自然图四格 campaign 冻结 | 4 sessions/8 actions/8 claim declarations；15/15 PASS；manifest 落盘后深复验；零 claim/授权/I/O | `G1S1_N2P_PHOTO_CAMPAIGN_OFFLINE_20260808_V1/campaign.json` |
| 2026-08-08 00:52 | N6 真实浏览器 E2E 白天阶段 1 | Chromium 3/3 复跑 PASS；fake device 仅 1 GET、0 visible POST/recovery；P0 claim 仅声明 | `N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 00:57 | N3 重复性/顺序效应离线包 | N3A/N3B 共预制 52 sessions/104 actions；自然图来源；15/15 PASS；默认不要求 J2 cycle | `tools/g1_s1_n3_campaign.py`、`tools/g1_s1_n3_analyzer.py` |
| 2026-08-08 01:05 | 双固件纯编译复核 | RC2G `815664/9df897...0cd772`、N7 `775536/81e905...cb66` 精确不变；未连接或刷写 ESP32 | `.pio/build/*/firmware.bin` |
| 2026-08-08 01:19 | 现场安全状态再次复核 | 用户关闭驱动板/J2，仅保留 ESP32 供电；白天继续纯代码、离线测试和编译，不访问/重启/刷写设备，不生成面板授权 | 本页“一眼状态” |
| 2026-08-08 01:37 | N8 描述性离线包 | 5 sessions/15 actions/10 PASS-result 依赖；账本/analyzer 18/18 复跑 PASS；强制 `NOT_QUALIFIED`；零 claim/授权/I/O | `tools/g1_s1_n8_*`、`N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 01:49 | N2 固定执行与四格总评 | 8-action runner/finalizer + tie-safe analyzer 完成；根侧 19/19 PASS；只允许 exact campaign 的 N3 分支选择；零真实 claim/授权/I/O | `tools/g1_s1_rc2g_n2_photo_campaign_once.py`、`tools/g1_s1_rc2g_n2_photo_campaign_analyzer.py`、`N2P_RC2G_FIXED_EXECUTION_V2.md` |
| 2026-08-08 02:00 | 现场安全状态复核 | 用户关闭驱动板/J2，仅保留 ESP32 供电；继续纯离线代码、测试与固件编译，不访问/重启/刷写 ESP32，不生成可见刷新授权 | 本页“一眼状态” |
| 2026-08-08 02:04 | 双固件纯编译再复核 | RC2G `815664/9df897...0cd772`、N7 `775536/81e905...4cb66` 精确不变；只执行 PlatformIO build，零设备 I/O、零刷写 | `.pio/build/*/firmware.bin` |
| 2026-08-08 02:16 | N5 测量合同/计划/聚合阶段 1 | 根侧 40/40 PASS；36 palette raw + 360 transition raw 口径、n=5 主统计与 26 sessions/73 actions 冻结；外部仪器/runner/真屏仍 blocked | `N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md`、`host/extended_color/{spectral,aggregation}.py`、`tools/mf1750_n5_measurement_campaign.py` |
| 2026-08-08 02:24 | C3 参数化转移感知优化器 | 13/13 PASS；普通量化 exact 退化、6×6 实测门、未知旧帧保守模式、跨资产 binding、histogram/Pareto 完成；禁止 BUSY 缩短与硬件资格声称 | `host/transition_optimizer/`、`C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 02:35 | C3 离线产物执行层 | build/validate CLI 与闭包深验完成；专项 15/15、C2/profile 邻接 48/48 PASS；零设备/授权/claim/上传入口 | `tools/mf1750_transition_optimize.py`、`C3_TRANSITION_OPTIMIZER_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 02:52 | N4 V3 固定执行/因素分析闭环 | 8-action runner+人工 finalizer+深证据 2×2 analyzer 完成；根侧 49/49 PASS；同格不重启/不断 J2，跨格 nominal 可持续供电；零真实 claim/授权/I/O | `N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`、`N4_V3_RESULT_ANALYZER_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 03:11 | N5 固定执行/正式聚合闭环 | 22+9+42 actions 的统一 runner/finalizer 与 finalized-bundle 聚合门完成；全 N5 50/50、最终受影响组 25/25 PASS；仍受仪器/供应商/外部 profile 阻断 | `host/extended_color/execution.py`、`tools/mf1750_n5_fixed_execution.py`、`N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 03:21 | N2--N8 晚间逐项任务板骨架 | 安全总门、J2例外、6步循环、停止条件和 N2/N4/N5/N7 具体入口完成；N3/N8 明示不可执行占位；board+repo 30/30 PASS | `MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`、`tests/test_evening_task_board.py` |
| 2026-08-08 03:49 | N3 固定执行/深证据分析闭环 | N3A 唯一 N2 winner×单 repeat 选择门、N3B 32-action Williams、runner/finalizer/analyzer 完成；根侧 51/51 PASS；零真实 claim/授权/I/O | `N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md`、`tools/g1_s1_n3_*`、`tools/g1_s1_rc2g_n3_once.py` |
| 2026-08-08 03:52 | 晚间任务板 N3 入口冻结 | N3 exact compile/describe/run/finalize/analyze 命令替换占位；36/38/40 action 路线与 J2/停止规则完成；board+repo 32/32 PASS | `MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`、`tests/test_evening_task_board.py` |
| 2026-08-08 03:58 | N8 固定执行/深证据分析闭环 | 15 actions/5 sessions/10 prior 链、warm 动态非零 baseline、runner/finalizer/analyzer 完成；根侧 32/32 PASS；始终 NOT_QUALIFIED | `N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md`、`tools/g1_s1_n8_*`、`tools/g1_s1_rc2g_n8_once.py` |
| 2026-08-08 04:03 | 晚间任务板 N8 入口冻结 | 15-action 顺序、runtime API、once/finalizer/analyzer CLI、warm 动态 baseline 与外部测量/J2/停止规则完成；全板无 TBD；board+repo 33/33 PASS | `MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md`、`tests/test_evening_task_board.py` |
| 2026-08-08 04:10 | 全项目软件/系统收尾审计 | 识别 N5/N6 两个 operator 闭环为当前测试链仅余白天代码缺口并立即开工；其余未完成项按外部阻塞或独立发布/产品 scope 分类 | `STATUS_HANDOFF.md`、`N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md`、`N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 04:23 | N5 formal manifest compile CLI | 外部 reviewed profile→73 actions/26 sessions；exclusive atomic publish、既存/并发/duplicate-key/deep validation；根侧 4/4 PASS；零设备/claim/授权 | `tools/mf1750_n5_measurement_campaign.py`、`tests/test_n5_compile_cli.py` |
| 2026-08-08 04:27 | N6 formal 浏览器 operator 闭环 | measured-gated materializer、loopback serve、one-shot browser、唯一 POST、manual finalizer/deep validator 完成；根侧 focused 13/13、board+repo 34/34 PASS | `host/application/n6_visible_execution.py`、`tools/mf1750_n6_visible_once.py`、`N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 05:18 | N5 production operator 最终闭环 | 73 actions/26 sessions 的 strict compile、一次性 RC2G、outcome-ready PASS/UNKNOWN、session bundle/深验证及 J2 语义完成；完整 77/77、独立 36/36+41/41 PASS；零设备/claim/授权 | `tools/mf1750_n5_{measurement_campaign,fixed_execution}.py`、`host/extended_color/{execution,n5_rc2g_protocol}.py`、`N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md` |
| 2026-08-08 05:26 | N2--N8 白天软件包冻结与双固件干净构建 | operator 链 7/7；Ruff/compileall/JS/repository contract/diff 全 PASS；RC2G `815664/9df897...0cd772`、N7 `775536/81e905...cb66` 可复现；未访问或刷写 ESP32 | 本页、统一晚间任务板、`.pio/build/*/firmware.bin` |
| 2026-08-08 07:50 | 最终全仓回归与 Ruff 回归修复 | 首跑发现 `FRAME_BYTES` 公共导出被误删；显式 re-export 后 focused 14/14、完整 874/874 PASS（1224.192 s）；Ruff/compileall/JS/repo contract/docs 39/39/diff/双 binary identity 全 PASS | `host/partial_update/planner.py`、本页、`.pio/build/*/firmware.bin` |
| 2026-08-08 07:50 | J2 自动电源与电参读取候选审计 | 台架首选 TPS22950Q1EVM+INA228+串联急停；最终板候选 TPS22950C+INA228，强锁断候选 TPS259474L+INA228；峰值未测，BOM/限流未冻结，尚未接线 | 本页“J2-1 自动电源控制候选” |
| 2026-08-08 08:12 | N2/Q1 断屏设备预检 | RC2G identity、MAP generate 与 Q1 Atkinson ingress/hash PASS；两次均 `epd_action:none`，job2 不变，零 `/api/frame`/claim/刷新 | `RC2G_N2_Q1_NONDISPLAY_PREFLIGHT_20260808_081257/PREFLIGHT.json` |
| 2026-08-08 08:15 | N2 Q2--Q4 ingress 与重启停止事件 | Q2/Q3/Q4 hash/FNV 均 PASS、`epd_action:none`；最终 job2→job0、report 清空，区间内发生未归因控制器重启；J2 OFF、零可见刷新，停止 POST 等待用户确认 EN/USB/ESP32 电源动作 | 同上 `PREFLIGHT.json` |
| 2026-08-08 08:30 | ESP32 重启事件归因 | 用户确认测试期间重新插拔 ESP32，job2→job0 归因为人为 USB 重插，不作为固件稳定性故障；当前 fresh job0，J2 OFF，跨重插连续性不继承 | 同上 `PREFLIGHT.json` |
| 2026-08-08 08:37 | N2 production live 安全复审 | 证实旧 campaign panel 为 UNBOUND；任意格式正确的 usage/review SHA 与单 action allowlist 可使 profile ready，且 bool 可走向联网。撤回 N2/N3/N4 live-ready，J2 OFF；启动 physical-bound identities/claims 与 evidence-deep profile 修复 | `tools/g1_s1_rc2g_n2_photo_campaign{,_once}.py`、`host/visible_refresh_campaign/contracts.py` |
| 2026-08-08 08:45 | N2 legacy live 立即熔断 | 旧 runner 现在对 `UNBOUND` panel 在结果目录、claim 和网络 I/O 之前硬拒绝；实测错误路径零 claim、零网络。physical-bound 新 campaign/runner 仍在实现，J2 继续 OFF | `tools/g1_s1_rc2g_n2_photo_campaign_once.py` |
| 2026-08-08 09:00 | N2 physical bundle + production profile 底座 | 双文件 bundle 独占发布真实 panel-bound campaign，8 个 action/claim/prior 全部重建；profile 对 firmware/supplier/usage/review/HMAC key 与完整 allowlist 做实际字节深验并向 runner 返回同次 snapshots。N2/N3/N4 旧 live 均已在 claim/网络前熔断；专项 N2 13/13、N3 11/11、N4 12/12（含 16 subtests）、physical/profile 联合回归 PASS；新 N2 runner 尚在实现 | `tools/g1_s1_n2_physical_campaign.py`、`host/visible_refresh_campaign/production_profile.py`、`tools/mf1750_limit_profile.py` |
| 2026-08-08 09:14 | ESP32 USB/Wi-Fi 重新接入复核 | 用户重新插接 ESP32；CH343 枚举为 COM8，`192.168.1.14` 可达，只读 GET 确认 RC2G/API V3/1 MHz、fresh job0/idle、GPIO `busy=0,rst=0,cs=0,cs2=0`。J2 仍按断开处理；零 POST、零 claim、零可见刷新，跨重插连续性不继承 | 本页“一眼状态”；设备只读状态 |
| 2026-08-08 09:23 | exact 本地面板规格复核 | A1 规格书精确对应 `MF-17506-M009F-T` / 1024×600；工作温度 0--50°C，可靠性试验图案 hold 150 s，并定义实物 barcode；文档未给 campaign 最大刷新数、连续次数或冷却额定上限，禁止伪造为 supplier rating。待用户抄录唯一条码；缺失调度字段只能另走明确标注的 reviewed supervised experimental policy | `参考资料/MF-1750..1).pdf`，SHA-256 `c03ef3c3...bed187` |
| 2026-08-08 09:31 | N2 physical one-shot 闭环 | 新 runner 的 describe/run/finalize/validate 已接通 dynamic 8-action、同次 deep profile snapshots、三类 exact token、<=300 s live 门、target 五项连续性、global claim-before-network、单 POST 与 raw protocol/相机/claim/LOCK/finalization/P0 深验；根侧专项 7/7（6 subtests）及 Ruff PASS，零设备 I/O | `tools/g1_s1_rc2g_n2_physical_once.py`、`tests/n2_physical_once_fixture.py`、`tests/test_g1_s1_rc2g_n2_physical_once.py` |
| 2026-08-08 09:31 | N5 outcome transaction 加固 | READY 与独立 outcome commit 改为两阶段；只有 exact receipt+READY+commit 才能人工 finalize，READY 已写但回读失败且 incident 也写失败的极端窗口保持永久不可 finalize；boolean POST counts 双 outcome 路径显式拒绝。扩大 N5 回归 59/59（6 subtests）与 Ruff PASS | `tools/mf1750_n5_fixed_execution.py`、`tests/test_n5_fixed_execution_operator.py` |
| 2026-08-08 09:41 | N2 physical 八项总评闭环 | exactly 8 finalized dirs 逐项调用 public deep validator；同一 physical lineage 下强制 8 份不同的 usage-bound approved profile，campaign count +1、每 session 0→1、last/snapshot 不早于前一结果；四条 MAP→target、claims/attempts/results/priors 防重放，六维 tie-safe winner 仅供 N3 branch，camera comparability 单列。根侧 9/9 + Ruff PASS，零设备 I/O | `tools/g1_s1_rc2g_n2_physical_analyzer.py`、`tests/test_g1_s1_rc2g_n2_physical_analyzer.py` |
| 2026-08-08 09:54 | truthful limit authority 闭环 | 新增 `supervised-experimental-process-policy`，强制 `not_a_supplier_rating`、有人监督、无自动执行/重试/恢复；逐字段 provenance 绑定 exact A1 PDF，次数/间隔/冷却禁止冒充供应商额定，温度 supplier provenance 仅允许 0/50°C；CLI 实际读取并验 PDF bytes 后只生成全 null 未批准模板。legacy supplier shape 兼容；根侧 15/15（18 subtests）+ Ruff PASS，零 approved artifact/设备 I/O | `host/visible_refresh_campaign/{contracts,production_profile}.py`、`tools/mf1750_limit_profile.py`、`tests/test_production_limit_profile.py` |
| 2026-08-08 09:54 | N2 limit-authority 中性化 | N2 confirmation token/claim/analyzer source binding 改用 `LIMIT_AUTHORITY`，CLI 首选 `--limit-authority` 且保留旧 alias；实验政策不再被结果文件或分析字段误标为 supplier。runner 7/7（6 subtests）、analyzer 9/9 与 Ruff PASS | `tools/g1_s1_rc2g_n2_physical_{once,analyzer}.py` |
| 2026-08-08 09:56 | physical schedule 安全复审重新打开 | 发现 N2/N3/N4 的 source campaign 均以 0 声明 target minimum interval / session planned cooldown；正值 supervised process policy 会正确阻断，若把政策也填 0 则失去预期流程门。决定在 physical materialization 时显式输入并冻结 operator-reviewed interval/cooldown，重新派生 action/session/claim；修复与回归前 N2 live 继续 NO-GO | `tools/g1_s1_n2_physical_campaign.py`、`host/visible_refresh_campaign/physical_rebind.py` |
| 2026-08-08 10:02 | ESP32 重新插接后二次只读复核 | CH343 仍稳定枚举为 COM8；只读 GET 再确认 RC2G/API V3/1 MHz、fresh job0/idle 与 GPIO `busy=0,rst=0,cs=0,cs2=0`。未打开串口、未 POST、未 claim、未刷新；J2 继续按断开处理 | 本页“一眼状态”；设备只读状态 |
| 2026-08-08 10:07 | N4 schedule-aware physical 真屏软件闭环 | generic rebind 强制显式 finite interval>0/cooldown>=0，标注 operator-selected、非 supplier rating，并把数值纳入 binding hash、全部 action/session identity 与 claim；N4 MAP/target fake-HTTP、连续性、单 POST、终结、重放、篡改/跨 cell 拒绝 7/7 PASS（178.6 s），generic 7/7 PASS；零设备 I/O | `host/visible_refresh_campaign/physical_rebind.py`、`tools/g1_s1_n4_v3_physical_execution.py`、`tools/g1_s1_rc2g_n4_v3_physical_once.py` |
| 2026-08-08 10:09 | N2 schedule-aware physical 闭环 | materializer 强制显式 interval>0/cooldown>=0，150/150 流程值进入 campaign/operator/profile-draft lineage 并旋转全部 8 identities/claims；supervised non-supplier policy 能升为 production-ready，非法/缺失/bool/NaN/Inf 失败关闭。materializer 13/13、runner 7/7、Ruff/compile PASS；零设备 I/O | `tools/g1_s1_n2_physical_campaign.py`、`tests/test_g1_s1_n2_physical_campaign.py`、`tests/n2_physical_once_fixture.py` |
| 2026-08-08 10:09 | N3A physical exact plan 编译器 | deep N2 physical analysis→唯一 winner、repeat 2/3/4、10 项 measurement assets、150/150 非 supplier schedule、generic rebind 与两文件排他发布完成；tie/null/cross/tamper 失败关闭，专项 7/7（109.9 s）、Ruff/compile PASS；计划本身零 live/device/network/claim/auth | `tools/g1_s1_n3a_physical_plan.py`、`tests/test_g1_s1_n3a_physical_plan.py` |
| 2026-08-08 10:12 | N2 根侧交叉回归重新打开 analyzer fixture | campaign/profile/runner 35 项先通过，但 analyzer 9 项 setup 因测试仍调用旧 `_assemble_manifest` 三参数签名而报错；未发现生产绕过或设备 I/O。已撤回 N2 完成计数，要求 fixture 显式 150/150 后完整重跑 | `tests/test_g1_s1_rc2g_n2_physical_analyzer.py:480` |
| 2026-08-08 10:16 | physical 链独立红队重新打开 N2/N3/N4 | 初审发现 runner 若仅按较小 limit-authority minimum 判断 elapsed，可能早于更大的 materialized operator schedule；另 N3A stored analysis validator 只做自洽复算，尚未证明能抵抗重封 score/ranking/winner。要求 runtime gate 取更严格值且在 claim/network 前失败；N3A 必须从 8 个 finalized result 目录+review key 重建/比对 analysis。PoC 与修复回归进行中 | `tools/g1_s1_rc2g_n2_physical_once.py`、`tools/g1_s1_rc2g_n4_v3_physical_once.py`、`tools/g1_s1_n3a_physical_plan.py` |
| 2026-08-08 10:36 | N2 runtime schedule 防绕过闭环 | target interval 与新 session cooldown 均在 claim/result/network 前按 `max(materialized, authority)` 判断，decision 深绑定 describe/claim/LOCK/evidence 并由 validator 重算；100 s authority 无法绕过 150 s materialized 门，150 s 边界单 POST+finalize PASS。focused 30/30、cross 40/40、Ruff/compile/repo contract/diff PASS；零设备 I/O | `tools/g1_s1_rc2g_n2_physical_once.py`、`tests/test_g1_s1_rc2g_n2_physical_once.py` |
| 2026-08-08 10:36 | N3B schedule-aware physical runner | 32 dynamic actions/16 sessions、150/150 非 supplier schedule、deep profile、三类 exact tokens、freshness、claim-before-network、single POST、MAP→target continuity、finalize/replay/camera/tamper 均闭环；5/5 PASS（162 s）。N3A analysis provenance 仍独立阻断，N3 stage 不计完成 | `tools/g1_s1_n3b_physical_execution.py`、`tools/g1_s1_rc2g_n3b_physical_once.py`、`tests/test_g1_s1_rc2g_n3b_physical_once.py` |
| 2026-08-08 10:36 | N3A forged-winner PoC 确认 | 把真实 analysis 的 Q3/Q4 分数、ranking/tie/winner 和 integrity 一并重封后，旧 validator/plan compiler 接受并把 winner 从 Q4 改成 Q3；全程离线。已要求 compile/read/validate/publish/live 均必须重放 exact 8 finalized results+trusted reviewer key并比对 canonical analysis | `tools/g1_s1_n3a_physical_plan.py`、`tools/g1_s1_rc2g_n2_physical_analyzer.py` |
| 2026-08-08 10:40 | N2 根侧 runtime/analyzer 复跑 | 新 runtime schedule gate 与 150/150 analyzer lineage 在根侧合并复跑 17/17 PASS（6 subtests，79.5 s）；确认低 authority 不能绕过物化调度，未访问设备/网络 | `tests/test_g1_s1_rc2g_n2_physical_once.py`、`tests/test_g1_s1_rc2g_n2_physical_analyzer.py` |
| 2026-08-08 10:45 | N5--N8 deep-authority 扩大复审重新打开 | N5 core `_validate_profile_for_action`、N6 formal/runtime review/profile 与 N8 runtime profile 只做 self-seal/`approved=true` 自洽检查，未验证真实 authority/usage/review bytes+trusted reviewer key；N7 live 无 limit profile 参数。旧 main chains 保留，但 production-live 计数撤回至仅 N2 1/7；零设备 I/O | `host/extended_color/execution.py`、`host/application/n6_visible_execution.py`、`tools/mf1750_n7_spi_sweep_once.py`、`tools/g1_s1_n8_execution_contract.py` |
| 2026-08-08 10:51 | N3A forged-winner provenance 闭环 | 所有 public compile/read/validate/publish/describe API 均强制 exact 8 finalized N2 result dirs+trusted reviewer key，现场调用 physical analyzer/逐目录 public deep validator；embedded/provided analysis 只能与重建 canonical snapshot 完全相同。Q4→Q3 重封 PoC 在 plan 生成前拒绝，8/8 PASS（119.4 s）、Ruff/compile PASS；零 claim/network/device | `tools/g1_s1_n3a_physical_plan.py`、`tests/test_g1_s1_n3a_physical_plan.py` |
| 2026-08-08 10:57 | N7 unsafe legacy live 熔断 | 旧 public `run_n7_sweep_once` 与 CLI `run` 现在在读取 campaign、创建 claim/result 或联网前无条件拒绝；原协议仅保留 private unit-test helper。新增 `panel_cold_driver_only` session 语义，精确表示 J2 cold-cycle 且 ESP32 保持同一 boot；相关 27/27（5 subtests）PASS | `tools/mf1750_n7_spi_sweep_once.py`、`host/visible_refresh_campaign/contracts.py`、`tests/test_mf1750_n7_spi_sweep_once.py` |
| 2026-08-08 11:02 | N8 unsafe legacy live 熔断 | 旧 public `run_n8_fixed_action_once` 与 CLI run 现在在 runtime 输入准备、claim/result 或联网前无条件拒绝；原冻结协议只保留 private offline fixture helper。Ruff/compileall 与 N8 once 专项 11/11 PASS（68.0 s），零设备 I/O | `tools/g1_s1_rc2g_n8_once.py`、`tests/test_g1_s1_rc2g_n8_once.py`、`tests/n8_bundle_fixture.py` |
| 2026-08-08 11:14 | N7 physical materializer | 公共 fixed-action contract 新增仅限 `/api/diagnostic/` 的 bodyless POST 表达；N7 五档均绑定真实 panel 文件、binding-review 实际字节、exact N7 firmware、>=10 s driver-only J2 off 与显式 non-supplier schedule，重建五个 action/claim DAG。跨 panel/review/schedule 全量旋转，placeholder/短冷却/重封/跨文件篡改拒绝；N7+contract 39/39（9 subtests）、Ruff/compile PASS，零设备 I/O | `tools/mf1750_n7_physical_campaign.py`、`tests/test_mf1750_n7_physical_campaign.py`、`host/visible_refresh_campaign/contracts.py` |
| 2026-08-08 11:17 | N3B/N4 physical formal analyzers | N3B exact 32 actions/16 sessions/4 Williams blocks 与 N4 exact 8 actions/4 cells 均逐 action 调 public deep validator，强制统一 plan/panel/firmware/authority/profile、全局 usage 连续性、唯一性与 observation schema；camera 单列，统计始终 descriptive/`NOT_QUALIFIED`。analyzer 4/4、N3B/N4 各一条真实落盘链 1/1+1/1、Ruff/compile PASS；N4 软件安全闭环计数恢复 | `tools/g1_s1_n3b_physical_analyzer.py`、`tools/g1_s1_n4_v3_physical_analyzer.py`、`tests/test_g1_s1_physical_analyzers.py` |
| 2026-08-08 11:43 | N6 production-live physical/browser 闭环 | actual panel/RC2G firmware、四类真实字节 HMAC、deep authority/usage/review/key、三 exact token、300 s actual-clock freshness、runtime max gate、Chromium claim-before-network/single-POST/UNKNOWN 与 public deep receipt/final validator 完成；根侧独立复跑 17/17（2 subtests）、Ruff/compile PASS，零设备 I/O | `host/application/n6_physical_execution.py`、`tests/test_n6_physical_execution.py` |
| 2026-08-08 11:43 | N7 production-live physical runner/analyzer 闭环 | exact 1/2/4/8/10 MHz 五档、5 sessions/5 fresh claims、deep profile、150/150 driver-only cold gate、三 token、single bodyless POST、prior/usage/result 链与 final analyzer 完成；五档不同 authority 文件按同一安全控制 lineage 聚合，最终 10 MHz descriptive PASS/`NOT_QUALIFIED`。根侧 27/27（8 subtests）、Ruff/compile PASS，零设备 I/O | `tools/mf1750_n7_physical_{campaign,once,analyzer}.py`、`tests/test_mf1750_n7_physical_once.py` |
| 2026-08-08 11:50 | N6 root operational audit 重新打开 | physical controller 的 authority/evidence/token/schedule/claim/validator 核通过，但旧 operator CLI 已硬阻断且没有新 physical CLI；claim 后 receipt 尚无生产入口负责排他耐久落盘，真实 Chromium E2E 仍使用 `_LegacyOfflineBrowserController`。为保证晚上不临场写胶水代码，N6 暂不计 production-live 完成，要求新增 physical serve/finalize/validate CLI 与 combined Chromium E2E；零设备 I/O | `host/application/n6_physical_execution.py`、`tools/mf1750_n6_visible_once.py`、`tests/test_n6_visible_browser_e2e.py` |
| 2026-08-08 11:53 | N7 operator CLI 映射复核 | 新增无 I/O 的 CLI 解析回归，逐项覆盖 dependent frequency 的全部 exact confirmations；清理 finalizer 死代码后完整 physical/materializer/common 回归 27/27（8 subtests）PASS | `tools/mf1750_n7_physical_once.py`、`tests/test_mf1750_n7_physical_once.py` |
| 2026-08-08 12:02 | N5 production-live physical/measurement 闭环 | 73-action physical plan 绑定真实 panel/firmware/science approval 与 non-supplier schedule；每 action 深验 authority/usage/review/key、actual clock、三 token，dependent action 额外要求 exact prior finalized transaction+strict RC2G+usage completion 连续；旧 live 入口硬阻断，正式 CLI 无 caller time/attempt 注入，production aggregation 拒绝 core-only synthetic bundle。代理全套 77/77、根侧关键链 23/23、Ruff/compile PASS，零设备 I/O | `tools/mf1750_n5_physical_{campaign,execution}.py`、`host/extended_color/aggregation.py`、`tests/test_n5_physical_{campaign,execution}.py` |
| 2026-08-08 12:07 | N5→N6 cross-stage provenance audit | N5 新 physical aggregate envelope 能在生成时深验 strict bundle，但 N6 physical fixture/入口仍直接接受 core-only `palette_aggregate`；该 core report 可自重封，不能单凭 flags 证明 raw observations 与 physical finalized results。N6 继续 NO-GO，要求携带 N5 physical context/result dirs/reviewer key/raw observations/标准与仪器输入重建并比对 aggregate，拒绝 synthetic core；零设备 I/O | `tools/mf1750_n5_physical_execution.py`、`host/application/n6_physical_execution.py`、`tests/n6_formal_fixture.py` |
| 2026-08-08 12:12 | 核心算法横向回归 | 六色量化、10 路显示器模拟、色域映射、DBS/重叠感知、面积混色、光谱与转移优化独立批次 161/161（157 subtests）PASS；确认剩余缺口属于 production execution/provenance，不是混色算法实现 | `tests/test_{color_pipeline,application_simulation,gamut_mapping,halftone_optimization,transition_optimizer,extended_color,extended_color_mixing,extended_color_spectral}.py` |
| 2026-08-08 12:13 | RC2G/N7 双固件纯编译复核 | PlatformIO 两环境均 SUCCESS；RC2G `815664/9df897...0cd772`、N7 `775536/81e905...4cb66` 精确复现冻结 binary。未 upload、未打开 COM8、未访问 ESP32 | `.pio/build/esp32-s3-devkitc-1*/firmware.bin` |
| 2026-08-08 12:28 | N8 production-live 15-action 闭环 | exact 15 actions/5 sessions/15 claims 全量 physical rebind；实际 panel/firmware、每 action deep profile、三 token、<=300 s、max schedule、五条 prior/usage 链、warm dynamic baseline 与 ESP 连续性闭合。claim 后异常先持久化 evidence+UNKNOWN，claim commit 不确定另留 marker/0-POST UNKNOWN；formal analyzer 拒绝 duplicate/tamper/cross-panel 且始终 `NOT_QUALIFIED`。代理新5+旧33、根侧合并38/38、Ruff/compile PASS，零设备 I/O | `tools/g1_s1_{n8_physical_execution,n8_physical_analyzer,rc2g_n8_physical_once}.py`、`tests/test_g1_s1_n8_physical.py` |
| 2026-08-08 12:42 | N3 production-live 重复性/顺序闭环 | N3A 新增 physical execution/formal CLI/analyzer，从 8 份 N2 raw finalized evidence 深重放唯一 winner，支持 repeat-2/3/4；actual clock、max schedule、三 token、global claim-before-network、single POST、durable UNKNOWN、MAP→target prior 与 tamper/cross-repeat 拒绝闭合。根侧 N3A+legacy+N3B 独立 29/29（27 subtests）、Ruff/compile PASS，零设备 I/O | `tools/g1_s1_{n3a_physical_execution,n3a_physical_analyzer,rc2g_n3a_physical_once}.py`、`tests/test_g1_s1_rc2g_n3a_physical_once.py` |
| 2026-08-08 12:57 | 6/7 当前口径与晚间任务板同步 | README/NEXT/TODO/晚间板/repo contract 统一为 N2/N3/N4/N5/N7/N8 软件闭环、未硬件执行；legacy live 入口均保持 BLOCKED，N6 仍 PENDING 且未编造命令。代理 repo contract 11/11、pytest 41/41、Ruff/compile/diff/Markdown fence 均 PASS，零设备 I/O | `README.md`、`docs/{NEXT_SESSION_PROMPT.md,TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md,MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md}`、`tools/check_repo_contract.py` |
| 2026-08-08 13:59 | N6 production physical/operator 最终闭环；软件总计 7/7 | N5 raw→physical aggregate 全量重放、正式 physical CLI、exact Atomic claim/HTTP driver、同步 durable receipt/commit、fixed per-claim incident、真实 Chromium physical E2E 与 legacy serve 硬阻断闭合；core 12/12（5 subtests）、CLI 7/7（14 subtests）、Chromium 1/1、独立安全审计 GO。零真实 claim、零设备/面板 I/O、未刷固件；仅代表软件闭环 | `host/application/{durable_io,n6_physical_execution,n6_visible_execution}.py`、`tools/mf1750_n6_physical_once.py`、`tests/test_{n6_physical_execution,n6_physical_browser_e2e,mf1750_n6_physical_once}.py` |
| 2026-08-08 14:39 | 全部开发/编译验证封版 | 当前 87 个测试文件四分片 `1018/1018 PASS`、494 subtests、0 skipped；全仓 Ruff/compileall/JS/repo contract/docs/diff 全绿。RC2G 与 N7 双 binary 大小/SHA 精确复现。6 个历史 hardware Python lint 仅作 docstring/import/f-string 机械清理，未运行生成/路由/导出。Registry 审计确认本轮零真实 claim/incident；零 ESP32/面板 I/O、零刷写 | 本页、统一晚间任务板、`.pio/build/esp32-s3-devkitc-1*/firmware.bin` |
| 2026-08-08 21:32 | 今晚零刷新真屏基线 | CH343/COM8 枚举正常；显式绕过主机代理后仅 GET `/api/version`、`/api/job`、`/api/diagnostic/status`、`/api/diagnostic/report`。RC2G/API V3/1 MHz、1024×600、307200 bytes、CS1/CS2 mapping、PSRAM 均吻合；fresh job0 idle、GPIO 全低、report=`no_completed_job_report`。零 POST、零 claim、零刷写、零可见刷新；下一门为真实面板条码 | 设备只读状态、本页“一眼状态” |
| 2026-08-08 21:38 | N2 实物面板绑定 | 按用户抄录条码 `MF750M009T6420/1582643AGY44` 生成 exact canonical panel 与 binding review；以 150 s 最小间隔/150 s session cooldown 物化并深验证 physical bundle。campaign canonical SHA=`ebc528a9...87f5`，8 个 action/claim identity 全部旋转；全局 claim registry 仍为 0，未联网/未授权/未刷新 | `.test-output/hardware/RC2G_N2_PHYSICAL_SESSION_20260808_2132/` |
| 2026-08-08 21:44 | N2 Q1-MAP production preflight | 用户确认监督策略（8/2/2、150/150 s、10--40°C、post<=45°C、无自动重试/恢复）与 37°C/J2 OFF；生成本地 reviewer key、900 s fresh usage、approved profile `df41e1...955ac`，deep validation/describe 均 ready。随后 4 个 GET 严格复核 RC2G fresh job0/GPIO 全低/report invalid，POST=0；三类 token hash 全匹配，claim=0、零可见刷新 | 同一 N2 session `inputs/`；Q1 action `a3042a59...a1e2f` |
| 2026-08-08 21:49 | N2 Q1-MAP 带电执行前门 | 用户接通 J2 并实测 3.29 V、CV、idle 0.001 A、限流 1.0 A、36.5°C、物理开关可立即切断；profile/describe 于 21:48 重新评估 ready。GET-only 复核 job0 idle、RST/CS1/CS2 low、BUSY high（idle informational）、无 completed report，POST=0；claim 仍为 0 | 等待 exact action token 回传 |
| 2026-08-08 21:54 | N2 Q1-MAP 可见协议完成 | 用户逐字授权 action `a3042a59...a1e2f`；runner 原子消费 claim 后恰好一次 `/api/frame` POST。job1/op1 completed，frame SHA=`1deedf...b5c36`、FNV=`0x9D04142D`、双 DTM/mapping/BUSY/sequence/safe-finish 全匹配，总时序 35026 ms；一次 job GET 超时后仅继续读取同一 job，POST 未重发，retry=0。当前 `protocol_verified_observation_pending` | `RC2G_N2_PHYSICAL_SESSION_20260808_2132/q1-map-primer-result/` |
| 2026-08-08 22:04 | N2 Q1-MAP finalized PASS + live-audit validator 修复 | 用户确认 exact MAP 完全一致、电气正常、36.5°C、40 cm、ESP32 未重启；峰值电流诚实记录为未观察。真实 evidence 含 POST 后一次 `/api/job` GET `FrameToolNetworkError`，随后同 job/report 成功；旧 validator 错拒。最小修复仅允许该只读 poll 形态，POST exception/第二 POST/其他端点仍拒绝；专项 1 PASS+4 subtests、Ruff/compile PASS。原证据不改、不重刷，finalized/public deep validate `PASS/valid=true` | Q1 MAP result；`tools/g1_s1_rc2g_n2_physical_once.py` |
| 2026-08-08 22:11 | N2 Q1-target ready | 自动形成 fresh usage（campaign/session/consecutive=1/1/1）、同一已批准策略的 per-action authority/profile/review；production/P0/schedule ready，elapsed=738 s >=150 s。GET-only 复核 live job1/op1、immutable diagnostic 与 GPIO 逐字段等于 finalized MAP prior，POST=0、target claim=0 | 等待简化单次授权；target action `cbf919bf...bd60b4` |
| 2026-08-08 22:15 | N2 Q1 Atkinson target 可见协议完成 | 用户以简化短语确认读数/连续性并授权唯一 target；内部三 token hash 严格匹配后原子消费 claim、恰好一次 `/api/frame` POST。job2/op2 completed，frame SHA=`7aa33f...7c96`、FNV=`0x1110A359`、DTM/mapping/BUSY/sequence/safe-finish PASS，总时序 35036 ms；一次 job GET timeout 后只读同 job 成功，retry=0。当前 observation pending | `RC2G_N2_PHYSICAL_SESSION_20260808_2132/q1-target-result/` |
| 2026-08-08 22:20 | N2 Q1 target finalized PASS | 用户对 exact Atkinson preview 确认画面一致、无旧残留；六维评分 `4/5/5/4/3/5`，其中 artifacts=3 表示仍见中等颗粒；37°C、电气正常、ESP32 未重启。Finalizer 与 public deep validator 均 `PASS/valid=true`，Q1 MAP→target 会话 2/2 闭环 | Q1 target result `83900dde...731f8` |
| 2026-08-08 22:21 | N2 Q2-MAP production ready | 生成 Q2 独立 fresh usage/authority/profile/review；deep describe 确认 production/P0/schedule ready，`elapsed=243 s >= 150 s`，三类 token hash 已冻结，Q2 MAP claim 未创建。本步仅离线读取，零 ESP32 I/O、零刷新 | Q2 MAP action `bd5042ae...6871`；等待 J2 接通状态下按一次 EN |
| 2026-08-08 22:25 | N2 Q2-MAP fresh-boot 门安全停止 | 用户回报 EN 已按/读数正常；严格只读复核仍见 Q1 `job2/op2` completed 及其 immutable report，故在 claim/POST 前 fail-closed。四个 GET 证实固件与 GPIO 正常；零 POST、零 claim、零刷新，Q2 机会未消费 | 等待短按 ESP32 EN/RESET（非 BOOT）后重做 GET-only 复核 |
| 2026-08-08 22:29 | N2 Q2-MAP fresh boot + final preflight PASS | 用户再次按 RESET 后，4 个 GET 严格确认 RC2G/API V3/1 MHz、`job0/idle`、report invalid、RST/CS1/CS2 low；BUSY high 为 J2 带电空闲信息。秒级当前时间 deep describe 再次 production/P0/schedule ready，`elapsed=687>=150 s`；三 token hash 不变、claim=0、POST=0 | 等待 Q2 MAP 唯一简短授权 |
| 2026-08-08 22:32 | N2 Q2-MAP 可见协议完成 | 用户简短授权 Q2 MAP；内部三 token hash exact 匹配后原子消费 claim，恰好一次 `/api/frame` POST。`job1/op1` completed，frame SHA=`1deedf...b5c36`、FNV=`0x9D04142D`、双 DTM/mapping/BUSY/sequence/safe-finish 全 PASS，总时序 35014 ms；一次 job GET timeout 后只读同 job 成功，retry=0 | `q2-map-primer-result/`；当前 observation pending |
| 2026-08-08 22:41 | N2 Q2-MAP finalized PASS + target profile ready | 用户确认 test image 正常、37°C、电气正常、ESP32 未重启；finalizer/public deep validator 均 `PASS/valid=true`，result SHA=`c423708a...599a`。继而生成 usage `3/1/1` 及 Q2 target approved profile；首个有效期过早草稿被本地拒绝，V2 后移 valid-from 并成功 HMAC 签署，全程零设备 I/O/claim | Q2 MAP `DONE`；准备 Q2 target |
| 2026-08-08 22:43 | N2 Q2-target ready | GET-only 将 live `job1/op1`、完整 diagnostic 和 GPIO 与 finalized Q2 MAP 原始证据 exact 比对全等；随后 target deep describe 确认 production/P0/schedule ready，`elapsed=401>=150 s`、三 token hash 冻结、claim=0。本步 4 GET、0 POST、0 刷新 | 等待 Q2 target 简短单次授权 |
| 2026-08-08 22:48 | N2 Q2 blue-noise target 可见协议完成 | 用户确认 MAP/J2/面板/ESP32/无其他刷新连续性并授权 target；三 token exact 匹配后原子消费 claim，恰好一次 POST。`job2/op2` completed，frame SHA=`cdd3abf6...a4e3`、FNV=`0x03D758D9`、双 DTM/mapping/BUSY/sequence/safe-finish PASS，35034 ms；一次 job GET timeout 后只读同 job，retry=0 | `q2-target-result/`；observation pending |
| 2026-08-08 22:49 | N2 Q2 target 画质劣化初判 | 用户报告“比前面差多了，白云多了很多黑色，效果非常差”。根侧直接检查 exact strict preview，其本身已明显包含云层黑颗粒、块状噪声和暗部压黑；若屏/预览一致，则归类为 area-weighted blue-noise 画质失败，不是硬件映射失败 | 待 exact-match、六维分数与电气收尾 |
| 2026-08-08 22:53 | N2 Q2 target finalized visual FAIL | 用户确认屏/预览一致，六维 `detail/tone/gradient/texture/artifact/fidelity=2/1/1/1/1/1`，无旧残留，37°C、电气正常、ESP32 未重启。Finalizer 返回 `state=FAIL/visual_pass=false`，public deep validator `valid=true`，result SHA=`81d0cdc8...b360`；证据闭环有效，算法候选失败，不重试 | Q2 session 2/2 闭环；准备独立 Q3 |
| 2026-08-08 22:57 | N2 Q3-MAP production ready | 生成 usage `4/0/0`、同一监督策略的 per-action authority/profile/review；首次 describe 在 `valid_from` 前数秒被本地时间门拒绝，零 claim/I/O。生效后重新 deep describe PASS：production/P0/schedule ready，`elapsed=321>=150 s`，三 token hash 冻结、claim=0 | Q3 MAP action `954b6099...be1d`；等待 RESET |
| 2026-08-08 22:59 | N2 Q3-MAP fresh boot + final preflight PASS | 用户确认 RESET/读数正常；4 GET 严格确认 RC2G/API V3/1 MHz、`job0/idle`、report invalid、RST/CS1/CS2 low，POST=0。当前时间 deep describe 再次 production/P0/schedule ready，`elapsed=477>=150 s`，三 token hash 不变、claim=0 | 等待 Q3 MAP 唯一简短授权 |
| 2026-08-08 23:13 | N2 Q3-MAP 可见协议完成 | 用户简短授权 Q3 MAP；三 token exact 匹配后原子消费 claim，恰好一次 POST。`job1/op1` completed，frame SHA=`1deedf...b5c36`、FNV=`0x9D04142D`、双 DTM/mapping/BUSY/sequence/safe-finish PASS，35006 ms；一次 job GET timeout 后只读同 job，retry=0 | `q3-map-primer-result/`；observation pending |
| 2026-08-08 23:27 | N2 Q3-MAP finalized PASS + target ready | 用户确认 test image 正常、37°C、电气正常、ESP32 未重启；finalizer/public deep validator `PASS/valid=true`，result SHA=`c52a76e2...b6be`。生成 target usage `5/1/1` 及 approved profile；4 GET 确认 live prior exact 匹配，deep describe `elapsed=228>=150 s`、三 token 冻结、claim=0 | Q3 target 无需 RESET，等待单次授权 |
| 2026-08-08 23:53 | N2 Q3-target stale-profile 安全拒绝 + V2 准备 | 用户已授权并要求继续；运行进程复算旧 token 成功，但 usage snapshot 超过 900 s，在 result/claim/network 前 fail-closed。显式复核 result dir/claim 均不存在。新生成 V2 usage `5/1/1`、authority/profile/review；4 GET 再次确认 live Q3 MAP prior exact，0 POST | 授权未消费；V2 valid-from `23:54` 后继续 |
| 2026-08-08 23:56 | N2 Q3 multicolor-DBS target 可见协议完成 | fresh V2 生效后沿用未消费的同一 action 授权；profile token 重新派生并由 runner 独立验证，然后原子消费 claim、恰好一次 POST。`job2/op2` completed，frame SHA=`0a9e2da8...1a77`、FNV=`0x2647DA34`，DTM/mapping/BUSY/sequence/safe-finish PASS，35037 ms；一次 job GET timeout 后只读同 job，retry=0 | `q3-target-result/`；observation pending |
| 2026-08-09 00:08 | N2 Q3 target finalized PASS + Q4-MAP profile ready | 用户确认屏/预览一致，六维 `4/4/3/4/4/4`，无旧残留，37°C、电气正常、ESP32 未重启；finalizer/public validator `PASS/valid=true`，result SHA=`cf36aa53...6936`。应用用户决定，增加独立 Q1/Q3 左右对比待后续新 campaign。同时生成 Q4 MAP usage `6/0/0` 及 approved profile | Q3 `DONE`；Q4 profile valid-from `00:09` |
| 2026-08-09 00:10 | N2 Q4-MAP production ready | Q4 profile 生效后 deep describe 确认 production/P0/schedule ready，`elapsed=255>=150 s`，三 token hash 冻结、claim=0；全程纯本地，零设备 I/O/刷新 | Q4 MAP action `d9504e16...fbb4`；等待 N2 最后一次 RESET |
| 2026-08-09 00:18 | N2 Q4-MAP fresh boot + final preflight PASS | 用户确认 RESET/读数正常；4 GET 严格确认 RC2G/API V3/1 MHz、`job0/idle`、report invalid、RST/CS1/CS2 low，POST=0。当前时间 deep describe 再次 production/P0/schedule ready，`elapsed=715>=150 s`，三 token hash 不变、claim=0 | 等待 Q4 MAP 唯一简短授权 |
| 2026-08-09 00:20 | N2 Q4-MAP 可见协议完成 | 用户简短授权 Q4 MAP；三 token exact 匹配后原子消费 claim，恰好一次 POST。`job1/op1` completed，frame SHA=`1deedf...b5c36`、FNV=`0x9D04142D`、双 DTM/mapping/BUSY/sequence/safe-finish PASS，35006 ms；一次 job GET timeout 后只读同 job，retry=0 | `q4-map-primer-result/`；observation pending |
| 2026-08-09 00:29 | N2 Q4-MAP finalized PASS + final target ready | 用户确认 test image 正常、37°C、电气正常、ESP32 未重启；finalizer/public validator `PASS/valid=true`，result SHA=`7e80ccaa...d740`。生成 target usage `7/1/1` 及 approved profile；4 GET 确认 live prior exact，deep describe `elapsed=221>=150 s`、三 token 冻结、claim=0 | 仅剩 N2 Q4 target 单次授权 |
| 2026-08-09 00:37 | N2 Q4 overlap-aware target 可见协议完成 | 用户授权 N2 最后 action；三 token exact 匹配后原子消费第 8/8 claim，恰好一次 POST。`job2/op2` completed，frame SHA=`4183b84b...8f86`、FNV=`0x1F67D22D`，DTM/mapping/BUSY/sequence/safe-finish PASS，35028 ms；一次 job GET timeout 后只读同 job，retry=0 | `q4-target-result/`；8/8 visible done，待最后 observation |
| 2026-08-09 00:47 | N2 Q4 target finalized PASS | 用户确认屏/preview 一致，六维 `4/4/3/4/3/4`，无旧残留，37°C、电气正常、ESP32 未重启；finalizer `state=PASS/visual_pass=true`，public deep validator `valid=true`。N2 8/8 全部 finalized：7 PASS + Q2 visual FAIL，全部 claims 永久消费且禁止重跑 | `q4-target-result/`；observation SHA=`634c5a8c...7b90` |
| 2026-08-09 01:03 | Q1/Q3/Q4 三列对比离线资产 | 新工具从三个 frozen frame 的相同中心 `x=344..679`、全高 600 px 取样，按 1:1 像素组成左 Q1/中 Q3/右 Q4，8 px 白线分隔；frame SHA=`f992022a...b4aa`、FNV=`0xD38160CF`、preview SHA=`a2ad8047...c87d`，deep validate/tamper test 2/2 与 Ruff PASS，零设备 I/O | `tools/g1_s1_n2_three_way_comparison.py`；`G1S1_N2_Q134_CENTER_THREE_WAY_20260809_V1/` |
| 2026-08-09 01:12 | N2 analyzer profile-rotation 修复 + 三列 one-shot ready | 真实八项分析揭示旧 analyzer 错把每 action 独立 `profile_id/valid_from` 当成必须相同；修为 safety lineage 稳定且 8 份 profile identity/validity 分别深验，analyzer 10/10、N3 消费端 8/8+15 subtests PASS。generic refresh 同时补齐 photo `source.input` exact-file/TOCTOU 校验，22/22+2 subtests PASS。三列候选 frame 与原组合 byte-identical，describe action `add67927...2b653` 已冻结，claim=0、POST=0 | 等待真实 analyzer 输出与用户单次授权；不复用 N2 8-action campaign |
| 2026-08-09 01:23 | N2 八项真实总分析完成 | 第二处真实差异是每 action 独立签发的 limit authority；修为 authority 文件 SHA 八份唯一，但去除 `policy_id/issued_at/validity` 后的安全合同必须完全一致，并把每份 authority SHA 纳入 chain。analyzer 10/10、N3 消费端 8/8+15 subtests PASS；真实 8 目录 deep replay 成功。ranking Q1/Q3/Q4/Q2=`26/23/22/7`，Q2 visual FAIL 令 `all_target_results_pass=false`，因此 `selected_winner=null`；analysis file SHA=`17c67b2c...af9ec`、canonical SHA=`a1fdbce1...35910` | `RC2G_N2_PHYSICAL_SESSION_20260808_2132/N2-PHYSICAL-ANALYSIS.json`；独立三列对比待授权 |
| 2026-08-09 01:24 | 三列对比执行前只读连续性复核 | 绕过系统代理后仅 GET：RC2G/API V3/1 MHz identity 正确，live 仍为 Q4 `job2/op2` completed、frame FNV=`0x1F67D22D`，report DTM/BUSY/sequence/safe-finish 保持有效，GPIO `busy=1,rst=0,cs=0,cs2=0`。未创建 claim、未 POST、未刷新 | prior 仍满足 action `add67927...2b653`；等待用户确认当前电气读数并逐字授权 |
| 2026-08-09 01:30 | Q1/Q3/Q4 三列对比可见协议完成 | 用户逐字授权 action `add67927...2b653`；runner 沿 Q4 `job2/op2` exact prior 原子消费独立 claim，恰好一次 POST。`job3/op3` completed，frame SHA=`f992022a...b4aa`、FNV=`0xD38160CF`，双 DTM/mapping/BUSY/sequence/safe-finish PASS，总时序 35028 ms；一次 job GET timeout 后仅只读同 job，retry=0。result SHA=`88b02d0b...61e4e` | `G1S1_N2_Q134_CENTER_THREE_WAY_LIVE_20260809_V1/`；manual observation pending |
| 2026-08-09 01:31 | 三列对比人工画质首判 | 用户明确偏好左侧 Q1 Atkinson，理由为“斑点更少”；该同 crop/1:1 直接比较与原 N2 人工总分 Q1 第一一致。尚未补齐本动作温度、电气、ESP32/残留观察，因此只记录 visual preference，不冒充完整 finalized verdict | 左 Q1 当前补充比较 winner；中 Q3/右 Q4 次序可选补充 |
| 2026-08-09 01:38 | 三列补充对比人工闭环 | 用户确认与 strict preview 一致、37°C、电气正常、ESP32 正常；总体左 Q1 最佳（斑点更少），中 Q3 优于右 Q4（对比度更强），最终排名 Q1 > Q3 > Q4。独立 observation 与 verdict 已落盘，original N2 score/winner gate 保持不变，formal algorithm qualification 仍为 false | `G1S1_N2_Q134_CENTER_THREE_WAY_LIVE_20260809_V1/{MANUAL-OBSERVATION,SUPPLEMENTAL-COMPARISON-VERDICT}.json` |
| 2026-08-09 01:44 | 开发优先级转为无抖动单像素扩色 | 用户明确更关注通过 waveform/粒子状态获得更多颜色，可不采用空间抖动；暂停拟议 Q1 N3-Lite。代码/资料复核确认 RC2G 仅发送六码 `0/1/2/3/5/6`，DRF 内部相位由片上 OTP 自主执行，当前无 LUT upload/select/readback 或 phase/电压 API。下一安全判别为隔离 `0x4/0x7` ROI 探针及六初态→候选保持测试；它只能发现现有 OTP 状态，不冒充 waveform 修改。零硬件 I/O、零 claim、零刷新 | `docs/{EPD_EXTENDED_COLOR_FEASIBILITY_2026-08-05.md,UNKNOWN_CODE_EXPERIMENT_DESIGN_2026-08-05.md}`；E Ink 2025 second-generation waveform 官方公告 |
| 2026-08-09 02:13 | 新增 STM32/OQC runtime-waveform 参考审计（历史快照，已由 8 月 10 日深审补遗更新） | 冻结 ZIP/关键源/库/map 哈希；确认 M009F-T 1024×600 双 E2802 架构和 runtime `0x20`/535-byte 机制。最新产物启动仍走 OTP，ARM `loadWF` 未链接；已链接 plaintext 路径为 2-bit/master-only，且 VCOM/Frame 未应用、全屏 TRES/无 CCSET、UART 长度未检查、BUSY 无超时、2-bit 白填充值内部冲突。当时的只读 JSON audit 固定 13 blockers，`compatibility_ready=false`；6/6 PASS，零解密/OTP/密钥输出/硬件 I/O | 后续以 `docs/MF1750_VENDOR_SAMPLE_DEEP_AUDIT_2026-08-10.md` 和本页顶部当前状态为准；原记录见 `docs/SPD1657_RUNTIME_WAVEFORM_REFERENCE_AUDIT_2026-08-09.md` |
| 2026-08-09 02:23 | EC5 隔离 scaffold 与参考链离线收口 | U04/U07 分离固件及正式/N7 共四环境 compile PASS；bin SHA 分别 `4343ebaf...21eb99` / `69aa6310...45fc`，release 无 EC5 ID，U04/U07 只含各自 ID。host campaign 仅能离线物化 U04/白初态/P01，analyzer 始终 `NOT_QUALIFIED`；因 device arm/持久锁/实物 sidecar/recovery 缺失明确为 NOT HARDWARE-READY。STM32+EC5 合并 38/38、Ruff/py_compile PASS；没有上传 COM8、设备/网络访问、claim、授权或刷新 | `src/ec5_unknown_probe_main.cpp`；`tools/mf1750_ec5_unknown_probe_{campaign,analyzer}.py`；`docs/UNKNOWN_CODE_EXPERIMENT_DESIGN_2026-08-05.md` |
| 2026-08-09 02:30 | N7 冻结身份漂移显式收口 + 最终回归 | 当前源码因后续 driver 诊断改动生成 N7 `3d970849...5408e`，不再等于 8 月 8 日冻结 `81e905...cb66`；旧 binary 仍完整保存在 V1 bundle，不静默改写历史 identity。firmware contract 改为优先校验 archive，并强制任何当前 build 漂移必须在 STATUS 完整登记。最终 STM32/EC5/N7/repo 相关 `73/73 PASS`，四环境 compile PASS；零硬件 I/O | `tests/test_mf1750_n7_firmware_contract.py`；`.test-output/hardware/MF1750_N7_SPI_SWEEP_OFFLINE_20260808_V1/firmware.bin` |
| 2026-08-09 08:33 | EC5 Stage A 设备/主机安全链实现 | U04/U07 已具备分离的 `arm→execute`、NVS 跨重启永久锁、claim-before-POST、单 POST、超时只读轮询和 U04 观察/白恢复后的 U07 门；固定晚间路线为 `白→U04→白→U07→白`，真屏 0/5 | release canonical=`adedbbdf...d7dd`；U04/U07=`28a7b558...49e`/`60ccfd72...e24`；runner=`b5aed8f0...164b` |
| 2026-08-09 08:33 | EC5 Stage B 六初态无抖动链实现 | U04/U07 均以白/黑/红/黄/蓝/绿六初态×双 DTM 镜像 ROI 生成 `primer→target→white` 三轮/九步状态机；target 后必须完成 `0/5/30 min` 观察，white PASS 才能下轮，U07 另受 Stage A 门；每候选真屏 0/9 | release canonical=`b500fee2...db04`；U04/U07=`722b6932...f0fc`/`815ac96e...3c06`；runner=`2f38ffca...b1c07` |
| 2026-08-09 08:33 | 白天 EC5 开发硬件边界复核 | 用户不在硬件旁；本轮未访问设备、COM8、网络或电源，未刷写、未 POST、未创建真实 claim，未执行任何可见刷新。当前 J2 状态不推断；最近已知实测设备仍为 RC2G `9df897...0cd772` | 本页“一眼状态”与 EC5 晚间计划 |
| 2026-08-09 09:22 | EC5 两级执行包最终冻结 | 六环境 clean build、候选隔离扫描、Stage A/B release deep validation、两候选离线 describe、预览/资产/runner 哈希复核全部通过；联合聚焦回归 `193 passed, 59 subtests passed`。所有 describe 为 0 network/0 claim，Stage B validate 为 0 hardware actions；真屏仍 Stage A 0/5、Stage B 0/9/候选，授权 0 | `MF1750_EC5_STAGE_A_RELEASE_OFFLINE_20260809_V1`；`MF1750_EC5_SIXSTATE_RELEASE_OFFLINE_20260809_V1`；`EC5_NO_DITHER_EVENING_TEST_PLAN_2026-08-09.md` |
| 2026-08-09 10:14 | EC5 文档/设计哈希与全仓回归收尾 | 四文档交叉审计修正预览 SHA、N2 旧状态、J2 口径和技术 pilot/完整资格边界；设计 SHA=`80bcf141...e9459` 已回绑且 27/27 PASS。全仓诊断发现可变 `.pio` RC2G 路径和 N7 精确文案两个根因，均已修复；受影响宽覆盖 60/60（67 subtests）、N7/contract/board 46/46 PASS，当前无已知失败路径。全过程零硬件/串口/网络/claim/刷新 | `tools/g1_s1_rc2g_n2_photo_campaign.py`；`tools/mf1750_ec5_unknown_probe_campaign.py`；本页与 EC5 晚间计划 |
| 2026-08-09 19:59 | EC5 Stage A A1 现场只读 preflight PASS | 用户接入 ESP32、保持驱动电源关闭；COM8 chip/MAC 识别 PASS，esptool `verify_flash` 证明应用区 815664 bytes 与归档 RC2G `9df897...0cd772` digest exact，未重刷。用户随后开启 J2 并确认一切正常；正式 white baseline preflight 4 GET/0 POST/0 claim，RC2G/API V3/1 MHz、panel、job0、无报告、GPIO safe-idle 全匹配 | A1 action `aace5544...ded7`；真屏 0/5；等待 exact 实时授权 |
| 2026-08-09 20:04 | EC5 Stage A A1 原生白可见协议 PASS | 用户逐字授权 action `aace5544...ded7`；runner 在 POST 前永久消费 global claim，恰好一次 `/api/frame`，`job1/op1 completed`。solid-white frame SHA=`91f1ed45...453d`、双 DTM FNV=`0xB7A855C5`、PON/DRF/POF BUSY、sequence、mapping、safe-finish 全 PASS，total=34996 ms；stored result deep validate PASS，result SHA=`3210ba93...e6e9`，claim SHA=`c4561798...9235` | A1 禁止重跑；协议 1/5，等待人工画面/电气观察 |
| 2026-08-09 20:08 | EC5 Stage A A1 人工观察 finalized PASS | 用户原文“全白无残影，一切正常”，据上一询问逐项记录为全屏白、左右一致、无旧残留、电气/温度正常、ESP32 未重启、物理切断可用；观察文件 SHA=`386bfad4...b44c` | Stage A 真屏 1/5 finalized；下一步必须先关闭 J2 再刷冻结 U04，不自动授权 A2 |
| 2026-08-09 20:12 | EC5 Stage A 冻结 U04 安全刷入 | 用户确认 J2 关闭；GET GPIO `busy=0`，release canonical `adedbbdf...d7dd` 与 U04 778000-byte SHA=`28a7b558...f5649e` 复核 PASS。esptool 仅写应用区 `0x10000`，写后 digest verify PASS；U04 API 自报 exact build/test/action，boot nonce=`8a9e45fe2450fa8d`、ready/phase0、arm=0、execute=0、driver=0、report NOT_EXECUTED | 零可见刷新、零 claim；A2 仍未授权，等待 J2 上电 preflight |
| 2026-08-09 20:14 | EC5 Stage A U04 A2 GET-only preflight PASS | 用户开启 J2 并确认一切正常；首个只读请求被系统代理 502 拒绝、未到设备且零 claim/POST。设置 `NO_PROXY=192.168.1.14` 后正式 runner 4 GET 成功：exact release/panel/build/test/action、boot nonce=`8a9e45fe2450fa8d`、state ready、phase0 全匹配；全局 claim/result 均不存在 | A2 action `bf2fcbcb...d0df5`；授权 0，真屏仍 1/5 |
| 2026-08-09 20:16 | EC5 Stage A U04 A2 停止门触发 | 用户逐字授权 action `bf2fcbcb...d0df5`；global claim 在 mutation 前永久消费，ARM/EXECUTE 各恰好一次，driver call=1、execute consumed、phase2。设备终态 `fault_locked`；40 次只读轮询均报告 `final driver FNV evidence mismatch`，runner 按合同给出 `unknown_do_not_retry_or_recover`，result SHA=`e1bf5659...c954`、claim SHA=`66b3d2c3...ce37` | 已命令立即断 J2、保留 ESP32 USB、不 reset/reflash；A3/U07/Stage B 全锁定 |
| 2026-08-09 20:19 | U04 A2 断电后只读证据收口 | 用户确认 J2 关闭、ESP32 USB 保留；GET status/report 保持同 boot nonce 与 phase2/fault_locked。raw driver evidence 为 operation1、valid=true，但 sequence/mapping=false，input/CS1/CS2 FNV=0，upload/PON/DRF/POF/post-PSR timing 全 0、total=151 ms，证明显示序列未启动；readback SHA=`69e8009f...928e0` | 等待用户确认屏幕/电气/温度/ESP32；仅离线诊断，不恢复、不重试 |
| 2026-08-09 20:30 | U04 A2 确定性根因与法证封存 | release source/binary identity 与两套 fixture 实现逐字重建，确认 driver 的 U04 DTM SHA byte array 半字节错位：compiled=`a805...b00d`、expected=`a805...ab00`，使 CS1 identity check 必然在任何 panel I/O 前失败。原 result/readback/claim 均保持不改，独立 supplement canonical=`30c27f69...c9b50`、file SHA=`660eac73...c73e`；Stage A V1 release 隔离 | `a2-u04-forensic-supplement.json`；等待人工观察；纯离线修复/回归进行中，J2 OFF、无 reset/reflash/retry/recovery |
| 2026-08-09 21:42 | Stage A corrected-v2 离线发布闭环 | 修正 U04 raw DTM digest，新增编译 ELF 符号级 frame/DTM identity gate、typed pre-I/O fault evidence、legacy-read-only/active-only NVS 迁移、J2-OFF 4 GET/0 POST/0 claim 诊断证据及 same-boot run 硬门。U04/U07 clean build、release deep validate、离线 describe 和全部 EC5 回归 `159 passed, 7 subtests passed`，Ruff/py_compile PASS | corrected-v2 release canonical=`0c7fd578...42183`；U04 BIN/ELF=`f73ea080...a9338b`/`dcb48fe7...c78659`；U07=`a2179d3d...bdfb8`/`b33f803a...724e5`。用户已确认 J2 OFF、ESP32 USB 保留；全程未访问或刷入设备，仍等人工观察 |
| 2026-08-09 21:43 | V1 A2 故障后人工观察闭环 | 针对上一轮逐项询问，用户回报“没问题，断电，其他一切正常”；记录为屏幕仍全白无变化、电气/温度正常、ESP32 未重启、J2 OFF、USB 保留。与法证证明 panel I/O 未开始一致 | `a2-post-fault-manual-observation.json`，file SHA=`3ae27651...4d30e`；V1 action 仍永久消费，不追溯为刷新 PASS |
| 2026-08-09 21:49 | corrected-v2 U04 断电刷入与诊断 PASS | J2 OFF 下识别 COM8/ESP32-S3/MAC `a4:cb:8f:d9:fc:d4`；仅写应用区 `0x10000` 的 783600-byte U04 `f73ea080...a9338b`，write hash 与独立 `verify_flash` digest 均 PASS，不擦 NVS。新固件 4 GET 精确确认 API V3/schema3/corrected-v2、legacy phase2/present/read-only、active phase0/absent/virgin、state ready、driver0、report NOT_EXECUTED、GPIO 全低 | boot nonce=`38c094c5efd0a69c`；diagnostic canonical=`79bea8ab...da600`、file SHA=`ba458a57...e428e`；0 POST/0 claim/0 authorization，等待 J2-ON 电气报告 |
| 2026-08-09 22:02 | corrected-v2 U04 J2-ON 只读 preflight PASS | 用户接通 J2 并确认一切正常；4 GET 重验 exact build/test/action、corrected-v2 migration、state ready/phase0/driver0/report NOT_EXECUTED，BUSY=1 且 RST/CS1/CS2=0。boot nonce 仍为 `38c094c5efd0a69c`，与 J2-OFF evidence 一致 | 0 POST/0 claim/0 authorization；可显示唯一 U04 exact 授权，但不预先消费 |
| 2026-08-09 22:07 | corrected-v2 U04 唯一可见协议 PASS | 用户逐字授权 action `f03e5352...c8d3`；runner 重放 J2-OFF evidence 并以同 boot 四 GET 后才创建新 claim，ARM/EXECUTE 各 1 次。driver operation1，input FNV=`0x68533DC5`，双 DTM FNV=`0x15B7EDC5`，upload=2444/2444 ms，PON/DRF/POF=180/21691/141 ms，mapping/sequence/safe-finish PASS，total=34253 ms，failure stage/code=none/0 | outcome=`complete_pass`；result canonical=`c48029af...2d043`、file SHA=`005c2363...ba4b7`，claim SHA=`a9fdb227...d0d3f`；无 retry/recovery，等待人工观察 |
| 2026-08-09 22:11 | U04 即时/约 5 min 短期观察 PASS，30 min 跳过 | 用户确认中央双 64×64 方块位置正确、左右对称、边缘清晰、内部均匀，主观呈蓝色；白背景干净、电气正常。22:11 再看与之前一致。用户明确选择跳过 30 min，记为未测而非 PASS | `u04-operator-observation-through-5min.json`，file SHA=`b8a4ca04...b7b8f`；短期蓝色候选成立，长期稳定/U07 formal review 不成立；下一可选为 after-U04 白恢复 |
| 2026-08-09 22:19 | after-U04 白恢复 RC2G 断电刷入 | 用户确认 J2 OFF；重验归档 RC2G 815664-byte SHA=`9df897...cd772`，仅写应用区 `0x10000`，write hash 与独立 `verify_flash` digest 均 PASS，不擦 NVS。Wi-Fi 恢复后只读确认 exact RC2G build/API/1 MHz、fresh job0 idle、report=`no_completed_job_report`、GPIO BUSY/RST/CS1/CS2 全低 | 5 GET/0 POST/0 claim/0 refresh；屏幕仍保留 U04 蓝色 ROI，等待 J2-ON preflight |
| 2026-08-09 22:21 | after-U04 白恢复 GET-only preflight PASS | 用户接通 J2，确认蓝色双 ROI 仍保持且电气正常；formal runner 4 GET 深验归档 RC2G `9df897...cd772`、fresh job0/report invalid/GPIO BUSY=1 其余全低，并重放 corrected-v2 U04 result `005c2363...ba4b7`、claim `a9fdb227...d0d3f`、panel/release identity 全 PASS | action `f528dcba...7c01`；4 GET/0 POST/0 claim，等待 exact 白恢复授权 |
| 2026-08-09 22:23 | after-U04 唯一白恢复协议 PASS | 用户逐字授权 action `f528dcba...7c01`；runner 重验 fresh RC2G/U04 result+claim/panel/binary 后永久创建白恢复 claim，恰好一次 307200-byte 白帧 POST。job1/operation1 completed，frame SHA=`91f1ed45...453d`、FNV=`0x13340DC5`、双 DTM FNV=`0xB7A855C5`，mapping/sequence/BUSY/safe-finish PASS，total=34194 ms | outcome=`complete_pass`；result canonical=`2986c90e...abf6f`、file SHA=`234b34f6...7fe83`、claim SHA=`51de68b5...62d9`；无 retry/recovery，等待人工白屏/残影观察 |
| 2026-08-09 22:24 | after-U04 白恢复人工视觉/电气 PASS | 用户确认两个蓝色 ROI “完全消失，全屏干净，电气正常”；记录为全屏白、无 ROI 轮廓或蓝色残影、恢复可逆。本次未单独报温度数值/ESP32 重启项，不予补写 | `u04-white-recovery-manual-observation.json`，file SHA=`d809844f...4bf4a`；U04 成为短期稳定、可白恢复的蓝色候选状态，但新颜色资格仍待 `0x5` 对照 |
| 2026-08-09 22:56 | U04-vs-U05 同屏直接对照离线闭环 | Agent Teams 并行完成固件/主机/独立设计审计。首版横排因 `0x4`全外侧/`0x5`全内侧的位置混杂被隔离；最终改为四块 64×64 纵向对角交叉，每码各1×CS1/CS2、1×top/bottom、与全屏中心等距。固定 frame/双 DTM 的 SHA/FNV、三 ELF runtime symbols、新 NVS/action、U04+短观察+白恢复 lineage、J2-OFF 4 GET/same-boot run/单 ARM+EXECUTE 全闭环 | V2 release canonical=`d871869e...f7fa5`、manifest file SHA=`ef7a31ef...d2ee9`；BIN 783216 `d1727353...05266`，ELF 13220820 `dee17857...7c0b7`；action=`70db952b...7d1700`；固件全 EC5 `176 passed, 3 skipped, 7 subtests`，host focused 14 + root 25 PASS，Ruff/py_compile/diff-check PASS；中间 V1 已隔离且从未刷入 |
| 2026-08-09 23:01 | U04-vs-U05 断电刷入与诊断 PASS | 用户确认 J2 OFF；准备刷入前 V2 release 再深验 canonical=`d871869e...f7fa5`，仅写应用区 `0x10000` 的 783216-byte BIN `d1727353...05266`，write hash 与独立 `verify_flash` digest 均 PASS，不擦 NVS。formal diagnostic 精确 4 GET 确认 build/test/action/layout、compiled frame+CS1+CS2 identities、U04 v2 phase2 read-only、compare key absent/phase0/virgin、state ready/driver0/report NOT_EXECUTED/GPIO 全低 | boot nonce=`67a1c3ce7bce9a4b`；diagnostic canonical=`e9b56282...c825`、file SHA=`8abe27a3...201cf`；0 POST/0 claim/0 authorization/0 refresh，等待 J2-ON 电气报告 |
| 2026-08-09 23:08 | U04-vs-U05 J2-ON GET-only preflight PASS | 用户接通 J2 并确认电气正常；release/prerequisite/diagnostic 深重放后，同一 boot nonce=`67a1c3ce7bce9a4b`、exact action/layout、phase0/virgin/ready、driver0、report NOT_EXECUTED、BUSY=1 且 RST/CS1/CS2=0 全匹配。首轮四 GET 已通过协议校验但本地摘要错误读取不存在的 `gpio` 聚合字段而退出；修正为四个标量字段后再执行四 GET并完整回显 PASS | 两轮合计仅 8 GET、0 POST、0 claim、0 refresh；本地摘要 KeyError 发生于全部设备校验之后，不影响设备状态。唯一 action `70db952b...7d1700` 尚待用户逐字授权 |
| 2026-08-09 23:14 | U04-vs-U05 唯一可见协议 COMPLETE_PASS | 用户逐字授权 action `70db952b...7d1700`；runner 重放 J2-OFF diagnostic 并以同 boot 四 GET 后永久 claim，ARM/EXECUTE 各恰好一次。operation1、frame FNV=`0x9A7A3DC5`、CS1/CS2 DTM FNV=`0x65B20DC5/0xD9B20DC5`，mapping/sequence/PON/DRF/POF/safe-finish PASS，total=34375 ms | result canonical=`45c6b502...42b0`、file SHA=`5d1c07fe...423b`、claim SHA=`39c3f1e5...96efc`；2 POST、driver1、retry0/recovery0，stored deep validator PASS，禁止重跑 |
| 2026-08-09 23:15 | U04-vs-U05 对角交叉盲评方向一致 | 用户在未获知代码位置、未看 pseudocolor preview 时报告“四个蓝色：左上右下深一些，左下右上亮一些”。冻结布局解码为左上/右下均 U04、左下/右上均 U05，且两组属于不同控制器 | 两个控制器一致支持 `U04 darker than U05`；位置、上下与 controller 混杂均被交叉布局抵消。当前结论为可目视区分的深蓝候选状态，不冒充重复性/长期稳定/正式新色资格；待补差异强度及安全观察 |
| 2026-08-09 23:19 | U04-vs-U05 盲评人工证据闭环 | 用户补充差异“清晰可辨”（固定为强度 2/4），饱和度难以描述、不作推断；四块颜色均匀、边缘清晰、白底干净，刷新后电气正常。严格记录温度与 ESP32 重启项为 null | `u04-u05-blind-manual-observation.json`，2365 bytes、SHA=`aabba55c...bcb1e`；visual directional gate PASS，分类仅为 `visually_distinguishable_darker_blue_shade_candidate`，repeatability/formal new-color 均 false；必须独立恢复白屏 |
| 2026-08-09 23:22 | U04-vs-U05 人工安全字段补齐 | 用户补报温度 35°C、ESP32 未重启；更新同一 observation 的 supervised safety 字段与第三条 verbatim，未改视觉判读和 protocol result | observation 最终 2401 bytes、SHA=`2f45f458...88a6f`；manual visual/electrical/thermal/continuity 全部 PASS，仍只作深蓝候选结论 |
| 2026-08-09 23:28 | 夜间硬件停止、转入纯离线开发 | 用户明确“准备休息”并确认 J2 已断开。屏幕保留 U04/U05 四块对照；不推断 USB 状态。冻结后续硬件 I/O 与任何可见授权 | 今晚离线目标：独立 compare-white 恢复、最新白前态 U07T V2 重绑接口、八码 atlas、初态转换分支及回归；明日现实直接色目标为已知六码+U04+待测U07，最多 8 个原生代码状态 |
| 2026-08-09 23:40 | 单次刷入多色路线 + waveform 安全合同 V1 | 用户要求减少反复刷机/RESET并询问超过八码的通道/波形路线。冻结 `EC5_COLOR_LAB` ordered multi-action 方向；初版 11-action 发现闭环随后扩展为同固件 23-action/三轮重复。实现双控 3-bit runtime-waveform candidate/evaluation、virtual palette 严格合同、CLI、duplicate-key/TOCTOU/payload/OTP/电气/恢复门 | `test_runtime_waveform_contract.py` 最终 16/16、Ruff、py_compile PASS；零设备/网络/COM8/claim/授权。八码仅为单 profile target symbol 上限；测试证明 12 个虚拟地址需跨 profile/multi-pass，且不推断光学区分 |
| 2026-08-09 23:45 | 独立 compare-after-white fallback 冻结 | 新 action `f9d41bfc...ec1f36` 绑定 compare release/result/claim/final blind observation 与归档 RC2G/权威白帧；独立 claim registry，J2-OFF flash gate 零网络/claim，J2-ON 4 GET/0 POST，run claim-before唯一POST，异常 unknown/no retry/no recovery；输出人工白观察与 latest-white binding | root 复验 focused 12/12、adjacent 15/15、Ruff/identity PASS。identity/runner/doc SHA=`75cfbf58...119f5`/`308952c9...9b546`/`3729d89c...e4b6c`；零硬件/网络/COM8/真实claim/授权 |
| 2026-08-10 00:38 | EC5 COLOR_LAB 自包含 V2 最终冻结 | 将当前 U04/U05 compare 证据直接绑定为 ordinal 1 前态；同一固件/NVS campaign 预置 23 个 action 与 5/11/23 白场停点。V2 内复制精确 BIN/ELF/campaign/release/compiled identity，BIN app descriptor 与 ELF SHA 闭合；V1 由执行器强制拒绝。host 与独立 fake-device E2E 覆盖同 boot 连续 ordinal、claim 顺序、计数漂移、隐式额外 driver、重启和 schema 异常；新增逐 ordinal 简化观察模板 | V2 release canonical=`190aee5f...2132`；BIN 791152 `b67c1601...61c78`、ELF 13253412 `2e772bc6...a4956`；clean rebuild 精确复现；最终联合聚焦回归 **128/128 PASS**（host 最终分组 53 PASS），Ruff/compileall PASS。真屏 0/23，J2 仍 OFF，零设备/网络/COM8/真实 claim/授权 |
| 2026-08-10 06:42 | COLOR_LAB 唯一刷入 + J2-OFF 诊断 PASS | 用户连接 ESP32 并明确 J2 OFF。PnP 确认 CH343/COM8；esptool 识别 ESP32-S3、MAC `a4:cb:8f:d9:fc:d4`。仅写应用区 `0x10000` 的自包含 V2 BIN，不擦 NVS，write hash 与独立 verify digest 均 PASS。固件联网后 formal runner 完成 exact version/manifest/status/report 四 GET | boot nonce=`070b7be93052814d`；ordinal1/next_ordinal1/persistent-key-absent/virgin/ready、ARM/EXECUTE/driver0、report NOT_EXECUTED、GPIO J2-OFF 全低；diagnostic `j2-off-diagnostic.json` 已二次深验。4 formal GET + 1 次旧 `/api/version` 只读 404 探测，0 POST/0 claim/0 authorization/0 visible refresh；等待 J2 ON 电气复核 |
| 2026-08-10 06:44 | COLOR_LAB ordinal 1 J2-ON preflight PASS | 用户按提示回报 3.3V、CV、空闲电流、限流值、温度及物理开关可切断，按 J2 已接通处理；因未含后三项数值，暂不创建 claim。formal preflight 重放 self-contained V2 并完成 version/manifest/status/report 四次只读 GET | boot nonce 仍为 `070b7be93052814d`；23 actions、next_ordinal1/READY、BUSY=1、RST/CS1/CS2=0、report NOT_EXECUTED 全匹配；0 POST/0 claim/0 authorization/0 refresh。等待空闲电流、限流值、温度具体数字 |
| 2026-08-10 06:49 | COLOR_LAB V2 ordinal 1 PRE-DRIVER FAULT | 用户明确 J2 ON、电气正常并补报 36°C，授权直接开始测试。首次本地调用因缺 `no-intervening-refresh` CLI flag 在设备访问/claim 前退出；确认 claim/result 均不存在后补入已知事实。真实 run 的四 GET preflight PASS并先永久 claim，第一次 ARM POST 被设备以 HTTP400 拒绝，host 依合同立即 UNKNOWN/不重试 | 只读 status/report 证实 boot nonce未变、phase3 FAULT、arm1/execute0/driver0、error=`body_or_arguments_forbidden`，故无面板刷新。result SHA=`9bf2a770...c99726`、claim SHA=`b565fe7e...672bba`；根因为 host 对 POST 传 `data=b""` 被 WebServer 当作 body/argument。已请求 J2 OFF，并行制作真正无 body POST + 新 namespace/action identity V3；严禁复用 V2 |
| 2026-08-10 07:04 | V2 故障后 J2 安全断开 + host 根因修复 | 用户明确确认 J2 OFF，ESP32 USB 可保留。host `http_request` 改为显式 POST 且 `data=None`，真实 stdlib HTTPHandler 证明不再产生 Content-Type/Content-Length/body/args；独立测试证明旧 claim/namespace 永久燃尽、新 namespace 可隔离且无需擦 NVS | host focused 40 PASS；独立 8/8、相关联合 51/51、Ruff/py_compile PASS；未访问硬件/网络/claim。等待实际 V3 全身份旋转、clean build、自包含 release 与 exact 回归 |
| 2026-08-10 07:15 | V3 recovery 自包含包刷入 + J2-OFF 只读确认 | V3 全身份旋转包经 bundle validator PASS后，在用户已确认 J2 OFF 下仅写应用区 `0x10000`，不擦 NVS；write hash与独立 verify digest PASS。启动后 ping 与 version/manifest/status/report 四次只读 GET确认实际固件身份和新 namespace | BIN 791616 `f8f86fca...e793`；boot nonce=`07f394f242c27dcb`；23 actions、`mf1750_ec5clr/cursor_r1` key absent/READY/next1、ARM/EXEC/driver0、report NOT_EXECUTED、GPIO全低。0 POST/0 claim/0 authorization/0 refresh；此轮4GET尚为手工摘要，等待V3专用runner正式封存后再上电 |
| 2026-08-10 07:22 | V3 专用 runner + 正式 J2-OFF evidence PASS | 独立 recovery adapter 将成熟 one-shot engine 临时绑定 V3 campaign/contract/device kinds/独立 registry，并在 finally 恢复旧 globals；硬绑定 V2事故 result/claim hashes。fake-device 覆盖完整 ordinal1 与真实 urllib 无body语义。随后对真机 formal diagnose 重放 release/事故/compare并做 exact 4 GET | runner 4/4、Ruff/py_compile PASS；boot仍=`07f394f242c27dcb`，action=`04ace39d...aa95`、WHITE、READY/key absent/GPIO全低；evidence SHA=`9db27ae2...87822`且二次 validator PASS。0 POST/0 claim/0 authorization/0 refresh；可请求 J2 ON |
| 2026-08-10 07:29 | V3 ordinal1 WHITE 唯一刷新设备+人工 PASS | 用户接通 J2 并确认 action 前电气正常、37°C；同 boot J2-ON 4 GET preflight PASS，claim 原先不存在。随后 action `04ace39d...aa95` 仅 ARM/EXECUTE 各 1 次、driver 1 次。显示忙期间首次终态 status GET 超时，原始 result=`unknown_do_not_retry_or_recover` 且永久保留；未重试/未恢复/未再 POST。随后只读 status+report 得到 READY/next2/COMPLETE、GPIO idle、boot不变 | 用户确认全屏干净白色、原四个蓝块完全消失、无残影、电气正常、37°C；设备回读同时证明 ESP32 未重启。当前自动+人工 1/23，等待把只读迟到终态封装为独立 reconciliation/complete result 后生成正式 observation |
| 2026-08-10 07:38 | ordinal1 迟到终态正式对账 + white observation PASS | 新 fail-closed reconciler 严格验证原 UNKNOWN 的 exact 7-record/状态码/claim/boot/headers 后，仅发送 status/report 两次 GET；同 boot 得到 READY next2、累计1/1/1与 COMPLETE report。原 UNKNOWN SHA `27fb3433...9248` 前后不变；derived COMPLETE 与独立 reconciliation 深验证 PASS | complete file SHA=`dd2e9aa...d3e4`、reconciliation file SHA=`f4859774...c75d`；人工 white observation file SHA=`311ab3f7...09a`、sequence gate PASS。0 POST、0 authorization reuse、0 retry/recovery |
| 2026-08-10 07:45 | V3 ordinal2 U07 isolated 唯一刷新 + observation PASS | 以 exact ordinal1 reconciled result+white observation 为 prior，同 boot 内完成 action `0e83b3d...e4fd`；claim-before-network，ARM/EXECUTE/driver 各1，终态 COMPLETE/next3，累计2/2/2。新 bounded read-only polling 容忍显示忙期 GET timeout，mutation 从不重发 | result file SHA=`726d1695...fb31`；用户判定左右两个蓝色肉眼同色、白底干净，电气/温度正常；设备 boot nonce未变。observation file SHA=`ceda776b...a7f7`、validator PASS；当前 formal 2/23 |
| 2026-08-10 07:49 | V3 ordinal3 WHITE recovery 唯一刷新 + observation PASS + J2 OFF | 以 ordinal2 result+observation 为 exact prior，同 boot 完成 action `b5fec9ff...ce3`；ARM/EXECUTE/driver 各1，终态 COMPLETE/next4，累计3/3/3，无重复请求 | result SHA=`b28747e7...8233`；用户确认两个蓝块消失、白屏干净、电气正常；observation SHA=`b3340046...855a`、validator PASS。随后用户明确 J2 已断开；下一项为 0--7 atlas，未 claim/未 POST |
| 2026-08-10 07:55 | V3 ordinal4 balanced 0--7 atlas PASS | 用户重新接通 J2并确认电气正常；action `4a7b6b43...4033` 单次完成、next5。盲分组：左下1≡4、右上1≡4；按双控反序解码，两边独立一致指向 code4≡code7，其余六码均可辨 | 共 **7 个视觉颜色组**；白底/电气正常。result SHA=`b3574ec4...7714`、observation SHA=`4e9baa7c...770b`，formal PASS |
| 2026-08-10 08:00 | V3 ordinal5 WHITE atlas recovery PASS | action `bacf670e...24cc` 单次完成、next6；用户确认全屏完全干净、八码色块全消失、电气正常 | result SHA=`4db7a43c...d308`、observation SHA=`01c5585b...ade9`；round checkpoint PASS |
| 2026-08-10 08:07 | V3 ordinal6 primer → ordinal7 U04 六初态 target PASS | primer 六色清晰，白块与背景自然融合、白底干净；target action `33a1f89f...8cb3` 后左右/上下六码均为一致蓝色，边缘清晰，无可见前态影响 | ordinal6 result/obs SHA=`7afd84ca...5e50`/`48a913bc...f5e7`；ordinal7 result/obs SHA=`03493611...51e4`/`84db9d4b...1d07`。U04 history expansion NEGATIVE，电气/ESP32正常 |
| 2026-08-10 08:12 | V3 ordinal8 WHITE U04 recovery PASS | action `19eb6cc1...3f5` 单次完成、next9；用户确认蓝块完全消失、白屏完全干净、电气正常 | result SHA=`397ef7b8...f7e9`、observation SHA=`b402fbe7...189c`，formal PASS |
| 2026-08-10 08:20 | V3 ordinal9 primer → ordinal10 U07 六初态 target PASS | primer 六色/左右/白底/电气按核对项 `ok`；target action `51c335e1...6a14` 后六位置完全一致，与 U04 蓝色肉眼无区别，无新颜色或明暗分组 | ordinal9 result/obs SHA=`4a1efe76...1f45`/`c43cae28...c969`；ordinal10 result/obs SHA=`70b29d9b...af1f`/`f0644af4...5de7`。U07 history expansion NEGATIVE，当前 profile 保持7视觉组 |
| 2026-08-10 08:24 | V3 ordinal11 WHITE round-one safe stop PASS | action `98881513...e882` 单次完成，终态 READY/next12、累计 ARM/EXECUTE/driver=`11/11/11`、boot nonce全程不变；用户确认所有蓝块消失、电气正常 | result SHA=`ad9c9c78...8aaf`、observation SHA=`79d8e885...14a7`，formal PASS。按 round-one safe stop 停止；ordinal12--23 未 claim/未 POST，默认跳过 |
| 2026-08-10 08:28 | J2 安全断开 + 转入 waveform/LUT 软件阶段 | 用户明确确认 J2 OFF。面板保持 ordinal11 干净全白；冻结当前 11/23 证据与 8码→7视觉组/4≡7、U04/U07 history-negative 结论 | 不访问面板、不刷新、不重启、不刷写、不下发 LUT；并行审计双控3-bit runtime payload/loader、电气与恢复门禁，预制下一次高效率多-profile测试包 |
| 2026-08-10 08:42 | Runtime waveform 三路审计 + fail-closed 合同加固 + clear-context handoff | 驱动审计确认当前 ESP32 只有已验证 OTP 双控骨架、没有 `0xE9/0x20/0x21` loader；STM32 535 B 是 2-bit/master-only，842 B 是不可直写封装。安全红队证明旧离线合同可被 1-byte dummy/自报 gate/伪装 opcode 错判 complete，现已将 `execution_ready` 恒置 false、拆出 `offline_contract_complete`、采用 `0xE9/0x20` 正向 allowlist并增加身份/长度/电气 blocker | 合同专项 21/21、与 STM audit 合并 27/27、加入 repo-contract 最终定向 57/57 PASS，Ruff/py_compile PASS；未访问硬件/串口/网络。新增 `docs/RUNTIME_WAVEFORM_LOW_MODEL_HANDOFF_2026-08-10.md`，固定 P0--P4、12-action 占位 campaign、外部资料门和高级审查停止点；当前 `LIVE NO-GO`、J2 OFF |
| 2026-08-10 09:00 | Runtime waveform P0b 深证据与精确序列合同 | 新增实际 artifact bytes/长度/SHA 深验、candidate→panel/batch/controller/electrical/recovery/reviewer 逐字段绑定，以及只能来自受信注册表的逐 CS exact sequence；生产 `REGISTERED_FORMATS` 固定为空，测试专用 synthetic registration 不能进入生产默认。单边/交换 payload、缺段、篡改、顺序变化与伪装 opcode 全部 fail-closed | runtime-waveform 合同+evidence `33/33 PASS`，Ruff/py_compile PASS；`hardware_execution_eligible=false`、`execution_ready=false`、`visible_refresh_authorized=false` 恒成立。未访问硬件、COM8、串口或网络，未刷写/刷新/授权；J2 仍按用户最后确认保持 OFF，下一里程碑 P1 |
| 2026-08-10 09:04 | Runtime waveform P1 零 I/O execution-plan | 编译器只接受 exact canonical manifest bytes、immutable 双 payload、P0 byte-backed evidence 和 caller-supplied trusted registration；输出只记录 controller/opcode/parameter length+SHA/predecessor，payload/literal bytes、callback、authorization token 均不进入计划。生产空 registry 返回 `BLOCKED_FORMAT_NOT_REGISTERED` 且 steps=[]；未猜测 535/842/544 格式 | P0/P1 专项 `41/41 PASS`，Ruff/py_compile PASS；source SHA=`b030e42e...e19`。未访问硬件、COM8、串口或网络，未刷写/刷新/授权；J2 仍 OFF，下一里程碑 P2 |
| 2026-08-10 09:07 | Runtime waveform P2 compile-disabled/mock-only transport 状态机 | host-only 状态模型固定 compile gate=false、初态 `BLOCKED_NO_REGISTERED_PROFILE`，不在 PlatformIO build 中且只接受 mock sink；synthetic success 轨迹覆盖双 CS profile identity、双 DTM count/hash、BOTH refresh、safe finish。CS1/CS2 mismatch、第二片失败、BUSY/POF timeout、非法重入、重复 execute、fault 后 retry 和 opcode 注入均 terminal，零自动 retry/profile-switch/recovery | P0--P2 专项 `50/50 PASS`，Ruff/py_compile PASS；source SHA=`a8edfe8e...d680`。未访问硬件、COM8、串口或网络，未刷写/刷新/授权；J2 仍 OFF，下一里程碑 P3 |
| 2026-08-10 09:11 | Runtime waveform P3 不可物化 12-action campaign | 冻结 K0/C1/C2 atlas→OTP 白恢复与两组 8×8 old→new primer→target→OTP 白恢复，共 12 declarations、safe stop=6/12；双控 atlas 反序、matrix 镜像且 ROI 无文字。生成 campaign/layout/DAG/人工表/4 pseudocolor/SHA 共 9 files；K0/C1/C2 profile/payload/action hashes 均 null，materialized=0、BIN/ELF=0、authorization=0 | `.test-output/offline/MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1/` 双次 validator PASS；campaign canonical=`44006046...f5d4`、file SHA=`d6bc261a...7080`。P0--P3 专项 `57/57 PASS`、Ruff/py_compile PASS；未访问硬件/COM8/串口/网络，未刷写/刷新/授权；J2 仍 OFF，下一里程碑 P4 |
| 2026-08-10 09:23 | Runtime waveform P4 全回归/双构建/最终 handoff | P0a--P4 全部不依赖外部材料的工作完成；生产 registry=0、compile gate=false、12 actions/0 materialized/0 runtime BIN。最终合并 `145 passed, 1 skipped`，Ruff/py_compile PASS；STM audit 仍 `compatibility_ready=false` 且 hardware/network/serial/decrypt 全 false。默认 current-worktree 两次复现 `815744/7f7468d3...6480`；recovery `791616/f8f86fca...e793` exact。首轮相邻测试的 1 个 missing-artifact 环境失败经补建后整组 52 PASS/1 skip，完整保留 | P4 JSON file SHA=`7cdc248d...96ed`；专项 handoff SHA=`faa1f57d...8327`；placeholder campaign canonical/file=`44006046...f5d4`/`d6bc261a...7080`。未访问硬件、COM8、串口或设备网络，未 upload/刷写/刷新/授权/LUT 下发；J2/屏幕继续按用户最后确认记录为 OFF/干净全白。状态 `SOFTWARE ENVELOPE READY / LIVE HARD BLOCKED` |
| 2026-08-10 12:26 | 两套厂家样例深审计 + STM32 loader 反编译冻结 | 完整枚举指定 E6/REG 目录，并逐项深审关键源/工程/库及全部 7 个 MAP。E6 是单 CS `800x480` EL073，固色 loop 与 4-bpp packing 一致，且 V1.2 连续演示在首次显示切 VDD 后未重新上电；REG 包混合多个代际，Sample main 不是工程入口且缺 `WF00_05.h`/selector 定义。可复现反汇编恢复真实 `loadWF` ABI/返回码/四次写长度；现库采用 544-byte 数据段，而随包 842-byte 文件只与不兼容的 `800+2+40` candidate layout 自洽，缺配对 loader/权威格式，master-only glue 不能证明双控加载 | 正式报告 `docs/MF1750_VENDOR_SAMPLE_DEEP_AUDIT_2026-08-10.md`；审计器 `7/7 PASS`、相关联合 `94/94 PASS`、Ruff/py_compile PASS，17 项 compatibility findings、production registry=0、compile gate=false 不变。用户报告保护设备与牺牲屏具备，但首次上机仍须固定仪器/阈值/责任人且 Gate A/B 先通过。仅有辅助脚本在内存中对 800-byte candidate 做 metadata-only 解码；未接受为 loader plaintext，未写出 raw key/waveform bytes，未生成 live payload。没有访问 COM8、硬件、串口或设备网络，没有刷写、刷新、授权或 LUT 下发；J2/屏幕仍按用户最后确认记录为 OFF/干净全白 |
| 2026-08-10 13:50 | 厂家蓝牙亮度/对比度线索离线冻结 | 用户转述可经蓝牙设置亮度/对比度；本地独立复核确认样例只给 PA9/PA10、115200 8N1 UART 右半链：cmd5 固定 535-byte waveform、cmd7 register `0x81` VCOM read、cmd8 unchecked raw VCOM byte + ACK。430 个文件、ZIP 条目及关键二进制可打印字符串没有 BLE/GATT/SPP/UUID/App 或 brightness/contrast/gamma 映射；7/7 MAP 证明 UART parser/cmd5 被链接，但 loadWF/LUT1_DATA 未拉入。官方相邻产品只证明部分板/整机支持 BLE，官方 App 旁证更符合“host 先处理图像再传输”，均不能外推为当前屏协议 | audit 升为 schema3/18 findings，新增 blocker `bluetooth_brightness_contrast_mapping_unproven`；聚焦 `8/8`、runtime-waveform/repo-contract 联合 `95/95 PASS`，Ruff/py_compile PASS；JSON SHA=`06bfd491...b9bbcb`。蓝牙桥、UI→图像/profile/VCOM 映射仍 HARD BLOCKED；禁止用 cmd8 试扫 VCOM。未访问 COM8、硬件、串口、设备网络，未刷写/刷新/授权/LUT 下发；J2/屏幕仍按最后确认记录为 OFF/干净全白 |
| 2026-08-10 21:00 | Factory-OTP 8×8 old→new 矩阵离线封装 | 为最快验证同一 OTP waveform 下的前态依赖，新建双控镜像矩阵：每片 8×8=64 个 old→new ROI，共 128 格；只有 primer→target→white 三个编译期固定 action。固件沿用已验证 factory-OTP 双控显示路径，不暴露 raw ingress，不写 runtime LUT/VCOM/电气/时序，不启动刷新、自动串播、retry 或 recovery | 已封存 `.test-output/hardware/MF1750_EC5_OTP_TRANSITION_MATRIX_RELEASE_OFFLINE_20260810_V1/`；clean build 两次复现 BIN `787728/cfba6e30...4206`、ELF `13240752/c153549a...577e`。compiled validator 从 ELF 反查三组 descriptor/双 DTM/frame identity、唯一 display direct call 与 BIN↔ELF app descriptor；bundle/release/runner/fake-device 红队均 PASS。新联合 `61/61`，旧 recovery 相邻 `18/18`，Ruff/py_compile PASS。bundle 内 4 个执行权威工件+密封 manifest 齐全；人工 preview 与历史 anchor/panel evidence 仍在本 workspace 外部路径但已锁定 bytes/SHA，因此当前只准在本 workspace 执行。本轮零 COM/串口/设备网络/刷写/claim/授权/刷新；用户“已连接”未证明 J2 OFF，等待明确确认 |
| 2026-08-10 21:16 | OTP matrix app-only 刷入 + 正式 J2-OFF 诊断 PASS | 用户明确确认 J2 断开、仅 ESP32 USB 连接。PnP 绑定 CH343/COM8，esptool 识别 ESP32-S3 rev0.2/MAC `a4:cb:8f:d9:fc:d4`。重验 bundle/compiled identity 后，仅将密封 BIN `787728/cfba6e30...4206` 写入 app `0x10000`（擦写范围 `0x10000--0x0d0fff`），write hash 和独立 `verify_flash` digest 均 PASS；未擦 NVS/bootloader/分区表 | 新固件在 `192.168.1.14` 启动；formal runner 严格 4 GET/0 POST/0 claim 验证 exact build/API/contract/3 actions、factory OTP/no runtime LUT、fixture self-check、NVS key absent、READY/next1、ARM/EXECUTE/driver=`0/0/0`、report NOT_EXECUTED、GPIO 全低。boot nonce=`1a6941119534644a`；evidence `.test-output/hardware/MF1750_EC5_OTP_TRANSITION_MATRIX_LIVE_20260810_V1/j2-off-diagnostic.json` 17363 bytes/SHA=`6838b470bacfda3a6b21c2631bd6d77d70575db06ba93d3cca90efc012b170fa`，二次 validator PASS。0 authorization/0 refresh；诊断后禁止再碰 COM/RESET/USB，等待 J2 ON 实时电气确认 |
| 2026-08-10 22:03 | OTP matrix ordinal1 J2-ON preflight PASS | 用户报告 J2 已接通、3.3 V、电气正常、37°C；结合既有限流/电流监测/物理切断就绪确认，只运行 formal ordinal1 preflight | exact version/manifest/status/report 四次 GET 同 boot nonce=`1a6941119534644a`；READY/next1、key absent、ARM/EXECUTE/driver=`0/0/0`、report NOT_EXECUTED、fixture self-check PASS、BUSY=1、RST/CS1/CS2=0。0 POST/0 claim/0 authorization/0 refresh；等待 action `056e47fe...b27b` 的逐字唯一授权 |
| 2026-08-10 22:08 | OTP matrix ordinal1 primer 唯一刷新 PROTOCOL COMPLETE_PASS | 用户逐字授权 action `056e47fe...b27b`。runner 重放 exact J2-OFF evidence，同 boot 四 GET 通过后先原子永久 claim，再仅 ARM/EXECUTE 各1次；无 retry/recovery/autochain | boot nonce=`1a6941119534644a`，job/op=`1/1`，driver total=34227 ms，1 MHz，frame/CS1/CS2 DTM、mapping/sequence/PON/DRF/POF/safe-finish 均 PASS，终态 READY/next2、累计 ARM/EXECUTE/driver=`1/1/1`。result 33950 bytes，canonical=`78892c360ab7474ab21098215050d4ab4d13480cd1b3385e3ce94a1ce9b61cd6`、file SHA=`68330d0212a1eec061dbfa0141b74307705e8e13629213b76eeb98cd42ed1991`；claim SHA=`a14c8dad1aaa18c74306171a187960c185ebb8db465208891de70c15ce4a9845`。已二次验证 result；当前等待人工 primer 观察，target 未授权/未 claim/未 POST |
| 2026-08-10 22:13 | OTP matrix ordinal1 primer observation PASS | 用户报告左半自上而下“黑-白-黄-红-蓝1-蓝2-绿-蓝3”，右侧反过来；每条色带内部 8 格均匀，边界和白边干净，电气正常，37°C，ESP32 未重启。“蓝1/蓝2/蓝3”依原话作位置标签，不自动推断三色肉眼可分 | observation 2260 bytes，canonical=`93e40ebcccc74541265035bd294450b6dc576ab67db224d4d0e505c3a203c8f0`、file SHA=`b25e3c5273259559fb922d7e84ba72239f6881a97548716771fb463804308a2e`，sequence gate PASS并二次 validator PASS。target action `a95d3c00...0d7c` 未授权/未 claim/未 POST，不自动串播 |
| 2026-08-10 22:18 | OTP matrix ordinal2 target 唯一刷新 PROTOCOL COMPLETE_PASS | 用户逐字授权 action `a95d3c00...0d7c`；runner 深验 ordinal1 result+observation，同 boot 四 GET 后先永久 claim，再仅 ARM/EXECUTE 各1次，无 retry/recovery/autochain | boot nonce=`1a6941119534644a`，job/op=`2/2`，target driver total=34226 ms，1 MHz，frame/CS1/CS2 DTM、mapping/sequence/PON/DRF/POF/safe-finish 均 PASS，终态 READY/next3、累计 ARM/EXECUTE/driver=`2/2/2`。result 36399 bytes，canonical=`311378748869e52731b7cf5fa0dba99977f3d914e4b1e9e36f94d412c9b9b9d3`、file SHA=`6d643520a8afb1c3e1e7b51f8a19704c1b50bf0a71dcc3c27e200c3289e8242c`；claim SHA=`2173abd097c2a96df0c268485ceff18d001437745074f684cccc1d6e11e6f0bf`。result 已二次验证，white 未授权/未 claim/未 POST |
| 2026-08-10 22:21 | OTP matrix target 首个前态依赖亮度阳性线索 | 用户报告“左右顺序反过来；左5-蓝1，左8-蓝3，从上而下有明确不同的亮度分层（虽然不是连续的，最深的在从上往下数第4个）” | 解码为左 new-code4/code7 两列的 old-state-dependent brightness candidate，最深 cell 均指向 old code3/red→new code4/code7。这是同一 factory OTP profile 的历史依赖线索，不是 runtime LUT 改写；在右半两轴镜像位置、其余六列与安全项补齐前不升格为新颜色结论，屏幕保留不恢复白 |
| 2026-08-10 22:38 | OTP matrix ordinal2 target observation + 双控镜像交叉 PASS | 用户补报右半对应第4/第1列同样分层，最深格精确为两轴反序后的自上第5行；其余六列没有变化，边界/白边清晰，电气正常，37°C，ESP32 未重启 | 双控同一语义 cell 一致：old red→new code4/code7 为各自 target 列最深的离散亮度状态；其余六个 target code 未见前态变化。observation 2297 bytes，canonical=`a429ab9e1ff5180a9212036f3789f08abbfd77488cea4e1740847a9c0ffc86b3`、file SHA=`a9c9c06068e29422e2e3a59d7e50cbf6ff9c35bdb69ab5cbb0f73e618d6c6e5a`，sequence gate/validator PASS。结论仅为 factory-OTP 历史依赖亮度，未报告色相变化；white action `54190f82...ae77` 未授权/未 claim/未 POST |
| 2026-08-10 22:51 | OTP matrix ordinal3 white pre-mutation GPIO 硬拒绝 | 用户逐字提交 white action `54190f82...ae77` 授权；runner 在深验 prior chain 后的 read-only preflight 于第3个 status GET 发现 device GPIO 不是精确安全空闲态，未再发 report GET，并在 claim/首个 ARM POST 之前 fail-closed | 本地确认 ordinal3 result 不存在、white claim 不存在；registry 仍仅有 primer/target 两份 exact claim。因此此次为 3 GET/0 POST/0 claim/0 driver/0 refresh，当前矩阵未恢复白。不自动重跑、不复用此授权 |
| 2026-08-10 22:54 | white 失败后 exact 4 GET GPIO 定位 | 用户再次确认 J2 接通、3.3 V、电气正常、37°C、矩阵仍在、USB/RESET 未动。为避免 formal preflight 在 status 失败后丢失摘要，同一次严格仅读取 version/manifest/status/report 各一次，然后用同一 production validator 离线判定 | 4 GET 均 HTTP200；boot=`1a6941119534644a`、READY/next3、ARM/EXECUTE/driver=`2/2/2`、ordinal2 report COMPLETE、fixture/cursor PASS、RST/CS1/CS2=0 全部精确，唯一异常为 `BUSY=0`（J2-ON expected=1）。0 POST/0 claim/0 driver/0 refresh。由于断电电子纸仍保持矩阵，要求在 J2 端而非仅 PSU 面板实测电压+空闲电流，未复位 BUSY 前 white 继续 HARD STOP |
| 2026-08-10 23:05 | GND 重接后 BUSY 恢复 + ordinal3 新 preflight PASS | 用户报告已重新接好 GND，其余电气正常、PSU 为 CV。先严格只读取一次 status，再执行 ordinal3 formal version/manifest/status/report 四 GET | 单 status 与 formal preflight 均确认 boot=`1a6941119534644a`、READY/next3、ARM/EXECUTE/driver=`2/2/2`、ordinal2 COMPLETE、BUSY=1、RST/CS1/CS2=0，故定位为 GND 连接导致的 BUSY 链异常，不是固件重启或 NVS/序列漂移。此过程合计 5 GET/0 POST/0 claim/0 driver/0 refresh；white 仍未消费，等待全新授权 |
| 2026-08-10 23:09 | OTP matrix ordinal3 white 唯一刷新 PROTOCOL COMPLETE_PASS | 用户重新逐字提交 exact white action `54190f82...ae77`；runner 深验 ordinal2 result+observation、同 boot preflight 与当前安全 GPIO 后先永久 claim，再仅 ARM/EXECUTE 各 1 次；没有复用失败授权、没有 retry/recovery/autochain | boot=`1a6941119534644a`，job/op=`3/3`，driver total=34219 ms、1 MHz，white frame/双 DTM、mapping/sequence/PON/DRF/POF/safe-finish 全部 PASS；终态 campaign complete/next4、累计 ARM/EXECUTE/driver=`3/3/3`。result 36275 bytes，canonical=`8e0deb157d58c1677394dd2b3eeb78047c182afb34c8aacf72627fb63cf8b717`、file SHA=`d525173ed358246b6890fcf871a5c3268675f4b9b922d66fdb6911725ecb635c`；claim SHA=`78cbd7d30d0b82476bd227a82fa879cfc1bc749c584a6f5c18500679f1e52e20`，stored validator PASS，禁止重跑 |
| 2026-08-10 23:12 | OTP matrix ordinal3 white 人工观察 finalized PASS | 用户原文“画面完全净白，全部消失，电气正常，温度37”；记录为矩阵/格线/色块全部消失、无异常残留、37°C，且 protocol 证据确认同一 boot/ESP32 未重启 | observation 2018 bytes，canonical=`5f9f72ac1e5cde8fea2e970edfd029a4adc6d2f1a0599d0d51297d4a0df284c7`、file SHA=`5d5bf4414ac8d150e73bde393f438f069ba511f719808723156cf2ba66b68e41`，sequence gate/validator PASS。三步 campaign protocol/manual=`3/3`，剩余可见 action=0；J2 按最后报告仍接通，当前只待物理断开后收尾 |
| 2026-08-10 23:26 | OTP matrix 最终安全收尾：J2 OFF | 用户明确回复“已断开J2”；不再对设备做任何读取、写入、RESET、刷写或刷新 | 最终现场状态固定为 `J2 OFF / 屏幕干净全白`。factory-OTP matrix protocol/manual=`3/3`、white recovery PASS、剩余可见 action=0；本轮硬件计划完成 |
| 2026-08-10 23:56 | Factory-OTP dither 7×5 矩形色卡离线里程碑 | 复现一手案例的七组双色空间混色；每半屏按 `纯A/75:25/50:50/25:75/纯B` 排列 35 格，左右语义与 2×2 局部相位完全相同。固定 Atlas→White 两动作独立固件，frame/双 DTM SHA+FNV+histogram 在任何 panel I/O 前验证；无 raw ingress、runtime LUT/VCOM/电气/时序写、startup refresh、retry/recovery/autochain | offline bundle `.test-output/offline/MF1750_EC5_DITHER_COLOR_ATLAS_OFFLINE_20260810_V1/` 共 7 files，manifest canonical/file=`30360b5b...128f`/`524e7b16...a295`；Atlas frame=`3b65803a...44b7`、双 DTM=`d461f7d2...f8d1`，focused `10/10 PASS`、Ruff/py_compile PASS。独立 PlatformIO 首轮纯 build SUCCESS；未 upload、未访问硬件/COM8/串口/设备网络，J2 仍 OFF。compiled identity/release/physical runner 尚在封装，真屏 0/2 |
| 2026-08-11 00:38 | Factory-OTP dither 正式 release 与一次性 runner 闭合 | 两次 clean build 完全一致并封存 exact BIN/ELF；release 深绑定 2-action campaign、OTP matrix ordinal3 干净白 result/observation/claim、panel evidence 与 Atlas/White 全部 frame/双 DTM identity。一次性 runner 固定 4 GET 后、首个 ARM 前永久 claim，单 ARM/EXECUTE、无 mutation retry/recovery/autochain；DCA/matrix/recovery 三 facade 改为共享 engine `RLock`，跨 facade 阻塞/异常 finally/全局 identity 恢复 3/3 PASS；DCA UNKNOWN 在打印密封证据后返回 exit 3 | release 目录 `.test-output/hardware/MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1/`；campaign canonical/file=`eecb1a55...5708`/`37b20c82...9707`，release canonical/file=`68c5ffd0...f7fe`/`ec3e2d87...7612`，BIN=`787312/49f39718...e7d4`，ELF=`13241104/f865d6e5...fb16`。Dither physical `12/12`、六文件相邻 `62/62`、generic/recovery/matrix physical `33/33`，Ruff check/format、py_compile PASS；独立红队给出带专用进程/固定 claim registry/UNKNOWN 硬停止约束的 GO。没有 upload、设备网络、COM、硬件或刷新；J2 仍按最后确认 OFF，真屏 `0/2` |
| 2026-08-11 18:03 | SPD1657 mode-0 relocation 闭环 + mode-1 映射纠偏 | schema2 离线审计器正式解析 `.reli.loadWF` 13 项 Elf32_Rel、DWARF global/type CU 与 `LUT1_DATA[704]`，证明当前第四写为独立全 FF sym C4，不是 `in+95`。同时由 legacy 535 的 `VCOM/Black/White/Yellow/Red/Power` 标签识别 H1/H2 两个精确 704-byte mode-1 构造，撤回此前唯一 category→pixel 映射；H2 结构上更优但未直接证明。新增审计确认 dormant no-OTP source 为 428×428/master-only 且直接读取 wrapper ciphertext，不能作为配对初始化 | 最终目标明确为一次牺牲屏 vendor-K0 真屏刷新+独立 OTP 白恢复；仍须 mode-1 source/binary 或完整双 CS SPI capture、双控/初始化/面板温区/恢复闭环。`WF20_25` 不得在此前 37°C 使用。审计 `11/11 PASS`、Ruff/py_compile PASS；零硬件/COM/网络/刷写/刷新/LUT，J2/屏幕仍按最后确认 OFF/干净全白 |
| 2026-08-11 18:44 | 旧 IAR/E2802 H3 loader 直接旁证 + 真屏完成条件固化 | 对厂家 `E2802.r43` 的 UBROF section 与唯一机器签名复核，直接恢复 active `Upload_Temperature_LUT`：`0x20/dataBuff+4/0x031F(799)`，随后 `0x21/0x02C0×FF(704)`。该函数内没有 PWR/PSR/PLL/`E9`/refresh/recovery；PWR/PSR/PLL 来自独立 `EPD_Init`，其中全局 `dataBuff[14..17]` 没有证据绑定当前 candidate header，禁止拼接猜测。H3 因此升为当前最强、仍待配对初始化证明的候选；H1/H2 保留为未排除旧假设 | 用户再次明确目标必须上真屏测试；完成门更新为“单次 vendor-K0 矩阵真屏 + 另行授权 factory-OTP 白恢复”，离线逆向或固件 build 不计完成。schema3 聚焦 `12/12`、联合 `77/77`、相邻 dither `54/54`、Ruff/format/py_compile PASS。零硬件/COM/设备网络/刷写/刷新/LUT；现场仍按最后确认 `J2 OFF / 干净全白` |
| 2026-08-11 19:26 | 第二份 vendor profile + AXF/IAR 调用图 + 经验真屏合同冻结 | extensionless `Projects/MDK-ARM/12` 被证明为厂家 `WF23_25[876]`：`800 ciphertext+BE74+74 wrapped key`，decoded 800 仍为 `7+9×88+1 zero`，与 WF20 仅 `443/800` 相同；两者均请求 43 Hz、PWR 中间电压不同。7 个最终 AXF/MAP 证明 5-build 双控 factory trace `9eb1db5d...fd31`，但无 runtime loader；可达 runtime source 仅 master-only `0F,A9/E9/20-535`。IAR 证明 7 个 H3 caller 的显示级 PON/DRF/POF 闭环和 E2801/E2802 PSR 位置漂移，仍无 OTP recovery。正式报告新增严格/牺牲屏双路线，经验路线固定 `5F69→5FE9 + TRES + PWR/PLL + E9 + H3`，逐项标记未证 | 三个 identity-pinned 工具聚焦 `26/26 PASS`，Ruff/format/py_compile PASS；公开资料仍无 `E9/799/704` ABI，Good Display 同代包仅 OTP。用户再次强调真屏为终点；正在离线物化固定 profile/八码 atlas/独立白恢复，不访问硬件、COM8、串口、设备网络，不刷写/刷新。现场仍为 `J2 OFF / 干净全白`，可见授权 0 |
| 2026-08-11 19:32 | 两份 empirical H3 编译期 payload 确定性固化 | 新增显式 profile packer；严格复核厂家 source/wrapper/key envelope/plain/header/H3 identities 后，生成 WF20/WF23 两份独立 C++ include。每份固定 decoded header、PWR/PLL、`0x20/799`、`0x21/704×FF`、温区/电气元数据、hash/static_assert；CLI 必须显式 `--profile`，无默认或自动温区选择，JSON 不输出 key/plain/payload | include SHA 分别 `8009f2c5...b626`、`ee289bc8...b9ff`；逆向/AXF/IAR/packer 联合 `34/34 PASS`，Ruff/format/py_compile PASS。include 明确 `empirical_h3=true/live_authorized=false/no hardware I/O`；仍不解决 PSR/E9/双控/恢复，不构成上屏授权。零硬件/COM/网络/刷写/刷新；J2 OFF/白屏 |
| 2026-08-11 20:22 | Empirical H3 runtime/recovery 四固件离线闭环 | 固定双控顺序与八码镜像 atlas 的 WF20/WF23 runtime 固件、两份无 runtime payload 的 factory-OTP white recovery 固件完成独立 build_dir clean build。device 在任何 `epdBegin` 前用 `esp_ota_get_app_elf_sha256` 自检当前 running ELF；host 再以 app descriptor 证明 BIN↔ELF，并唯一核对 transaction descriptor。主机 one-shot gate 禁系统代理和 redirect，只接受 literal private/loopback/link-local IPv4，ARM/EXECUTE 真正 bodyless且绝不重发；30 s settle 后仅 GET 有界轮询。J2-OFF 诊断强制处女 NVS 与 RST/CS1/CS2/SCK/DC/MOSI 低态；terminal report 强制 PON/DRF/POF BUSY、双 DTM、safe-finish 与 exact 7-key GPIO | 四份 compiled identity 均 `valid=true/offline=true/no I/O`：WF20 runtime BIN/ELF=`d46dbf42...6e21`/`87bb8569...c42b`，WF23 runtime=`37bc212b...e242`/`77246daf...25eb`，WF20 recovery=`a44f3c25...efe1`/`7b7fdac1...3f7a`，WF23 recovery=`80b16131...d395`/`9ac1be24...8c82`。最终 focused host+firmware `29/29 PASS`、逆向 `34/34 PASS`、Ruff/format/py_compile PASS。没有 upload、设备/COM/外网访问、刷写或刷新；J2 OFF/白屏，真屏仍 0/2 |
| 2026-08-11 20:30 | Empirical H3 两 profile 离线 release seal + 最终差分审计 | WF20/WF23 各自封存一份绑定对应 runtime/recovery BIN、ELF、contract、action 与 U1–U7 的 release JSON；两份均明确 `live_authorized:false`。终审发现并修复 firmware 7-key final GPIO 与旧 runner 4-key 判断不一致；virgin status、FakeDevice、terminal exact equality 和 SCK/DC/MOSI 三项变异拒绝已统一。默认 claim registry 不存在，未消费任何 action | WF20 release ID/canonical=`6e51286e...76d`/`16244e40...e93`，WF23=`30e2f448...4f1`/`0f0debce...196`；两份重新 deep-validate `valid=true`。最终只读审计结论 `CODE/SCHEMA GO`、focused `29/29 PASS`、Ruff/format/py_compile PASS。仍须现场唯一 profile、U1–U7、合规温度和 exact token；37°C NO-GO。零硬件/COM/设备网络/upload/刷写/刷新 |
| 2026-08-11 21:05 | Empirical H3 schema3 V3 最终封存 + 11-byte 语义硬边界 | 主机新增 fresh diagnostic-bound 离线 `authorize`、transport preclaim 校验，以及 diagnose/run 在任何 network/claim 前对结果证据做 O_EXCL+fsync 预留并持有同一 handle。release 绑定五份 host 执行源码；纠正旧包伪记录未发生 U1–U7 接受的问题，V3 仅保存 prerequisite 且 `accepted_at_materialization=false`。新增 identity-pinned phase-geometry 工具，证明 `9×8×11` 几何与 ordered opaque forwarding，同时证明 SPD1656 11-byte VCOM ABI/取反假设不能移植 | 唯一权威 V3：WF20 release/canonical=`23a26672...faf9`/`220ab675...5712b`，WF23=`bd782655...6d99`/`5ac9a9b8...0f971`，host bundle=`44db3fc0...8a741`；V1/V2 均 superseded/non-executable。八个定向文件联合 `110/110 PASS`，Ruff/format/py_compile PASS；严格 same-version ABI `NO-GO`、经验 H3 code-schema `CONDITIONAL GO`、physical `0/2`。默认 claim registry 不存在，未生成真实 token；零设备/COM/设备网络/upload/刷写/刷新，J2 OFF/干净白屏 |
| 2026-08-11 21:49 | WF20 V3 app-only 刷入揭示 running-ELF 合同缺陷并硬停止 | 用户明确选择 `WF20_25`、确认 J2 OFF、24.0°C。V3 release/BIN 重验后仅写应用区 `0x10000--0x0d1fff`，write hash 与独立 `verify_flash` 均 PASS；首个 formal version GET 即发现设备只返回 ELF SHA 前 16 hex，而 runner 要求完整 64 hex，立即 terminal preclaim failure | 根因为随 Arduino SDK 固定 `CONFIG_APP_RETRIEVE_LEN_ELF_SHA=16`；固件在 `epdBegin` 前自检失败并未初始化/调用屏幕驱动。共 1 formal GET + 1 人工只读定位 GET、0 POST/0 claim/0 driver/0 refresh；失败 evidence canonical/file=`251564e4...306`/`8fa18663...0a3`，J2 全程 OFF、白屏不变 |
| 2026-08-11 21:55 | running-ELF 全长身份 V4 修复、重刷与 fresh J2-OFF 诊断 PASS | runtime/recovery 改为直接读取 running `esp_app_desc_t.app_elf_sha256[32]` 并编码 64 lowercase hex，避开 SDK 16-char API 截断；WF20 两固件并行 clean build、compiled identity 与新 V4 release 深验后，再次只写应用区并独立 `verify_flash` PASS。formal runner exact version/manifest/status/report 四 GET 验证完整 ELF、处女 NVS/READY/next1、ARM/EXECUTE/driver0、NOT_EXECUTED 与 7-key GPIO 全低 | V4 release ID/canonical=`aad1b07d...8b25`/`021dbdaf...83a9`；runtime BIN/ELF=`a984ad29...c533`/`54e0a588...40f6`，recovery=`3352c580...c2375`/`f7f7c120...3c9b`；boot=`1f9044b9f3720292`，diagnostic canonical/file=`be8014fc...d0ac`/`71d894d8...e8ba`。4 GET/0 POST/0 claim/0 refresh；等待 U1–U7 exact 接受，J2 保持 OFF |
| 2026-08-11 22:02 | 逆向/11-byte/SPI/ELF 红队并行收口 + V4 双 profile 完整封存 | 完成 ArmCC 23-function 全 CFG 与 `0xE2` 正常同步不可达纠偏；完成 Philips/Apollo 11-byte primary-patent metadata 对照，发现 FF 尾记录位置相容但活动 selector `11` 大量存在，禁止移植字段语义；完成 exact dual-CS decoded capture 判定器和 430-file artifact hunt。独立红队逐 ELF 证明四份 V4 都只调用 `esp_ota_get_app_description`、循环编码 32 bytes，runner 无 prefix 容忍；新增 ordinal1/2×16/32/63 截断拒绝 | WF23 V4 release/canonical=`1456ba7a...1ef0`/`d734216c...6094`，runtime/recovery BIN=`496b340e...a686`/`baae7cee...4d7b`；最终 11 文件 `140 passed, 8 subtests passed`，Ruff/format/py_compile/diff-check PASS。未新增硬件 I/O；当前 WF20 V4/J2-OFF/白屏/fresh diagnostic 状态不变，等待 U1–U7 exact 接受 |
| 2026-08-11 22:15 | 目标级完成审计 + IAR 跨对象/公开资料边界收口 | 逐项审计 800-byte ABI、535/704、record、电气、双控、recovery、公开资料、工具与真屏证据；结论仍为 strict ABI NO-GO / empirical H3 CONDITIONAL GO / physical 0/2。29 个 `.r43` 的 debug-symbol/root 追踪未发现任一交付 root 同时串联配对 `EPD_Init` 与 E2802 H3 upload；完整跨对象 relocation 图仍是离线缺口。新核对 Good Display 2026 官方 GDEP073E01 局刷包只含 800×480/单CS/OTP `0x83+0x10` 路径，无 E9/20/21/799/704/recovery；公开索引仍无 direct same-version SPD1657 ABI | 结论不能把结构相容升级为已验证波形，也不能放宽 U1–U7。未改 payload/release、未访问设备/COM/设备网络；当前 WF20 V4/J2-OFF/24°C/fresh diagnostic、0 POST/0 claim/0 refresh 状态不变，等待 exact 接受 |
| 2026-08-11 22:43 | 29-object 调用站点清单/局部图 + 公开来源终审 + 今晚真屏入口保持 | 新工具对 29 个混合 UBROF10/11 对象逐一锁定身份，恢复 1786 条 CALLA/observed-relocation 配对记录（1385 local-section-relative、401 unresolved-provider external-index；20 条 caller section 未映射）；E2801/E2802 各 7 条本地 upload caller，但无 init→upload/共同 local root。9 行只是 producer output inventory；最终 D43 的直接项目 XLINK 输入仅 `DELAY/E6_73/main`，其中无 exact upload symbol/call，最终 d43 无该 marker；`main` external init call 的 E6_73 provider 归属只是多项 pinned 证据支持的推断，正式有界判定 `NOT_FOUND_WITHIN_PINNED_DELIVERED_GRAPH`。官方 UBROF/XLINK 文档、mspgcc UBROF5 与 Bound-T NDA 边界确认当前不能声称通用 parser。公开终审仍无同版完整链；Hackaday alias/silent-fallback/七 recipe 只有互相冲突的作者自述和零原始工件，新增 matched no-R20/R21 阴性对照作为后续归因门 | 新工具 7/7 PASS；最终 12 文件 `147 passed, 8 subtests passed`，另 repo contract `30/30 PASS`；Ruff check/format、py_compile PASS。用户已明确希望今天启动；仍等待逐字 U1–U7 接受，未生成 token/claim，未访问设备、COM8、设备网络，未新增刷写或刷新；WF20 V4/J2 OFF/24°C/fresh diagnostic/白屏/physical 0/2 不变 |
| 2026-08-12 01:44 | 官方 IAR/XLIB 与 temperature-selector 离线证据闭合 | 使用身份固定的官方 XLIB 6.1.3.56 对 29 个厂家对象作只读映射：26 个 UBROF10 的 349/349 external-index call 与官方数组完全一致、零冲突；`DELAY/E6_73/main` 三个 UBROF11 均停在 `Unknown tag:E2`，52 条 call 保持版本边界。一次性 E2 transformed-copy 仅作实验，虽 52/52 一致但不提升为原件官方解析。新 selector 审计以官方 xlink + TI MSP430 GCC 交叉反汇编 E2801/E2802：两者都固定 `25°C`、遍历 30 槽、判定 `lower <= 25 < upper`，命中后读取 2508 bytes，并发送 799 + 704×FF；E2801 的 TSC 返回值未进入 selector，E2802 upload 内无 TSC read | XLIB report file/canonical=`cf487e88...95e7`/`6d17001c...9e31`；temperature report file/canonical=`bc291f1c...f7fd`/`b1a30b56...aed7`。该证据不证明当前 800-byte ABI、provider/transport/物理地址、双控或安全；未访问硬件/COM/设备网络 |
| 2026-08-12 01:44 | 公开一手资料交叉验证完成 | E Ink Ripple 与两份专利支持“四粒子通过波形作像素内混色”、seed+perturbation 和短三段波形这些路线；ED2208 正式规格只确认 OTP waveform、LUT memory 与外部温度传感器，公开命令表没有 0x20/0x21、799/704 或 2508-byte slot。Good Display 官方 BLE 资料表明亮度/对比度/饱和度属于 host RGB 预处理后再做六色 dither，不是 panel runtime-LUT 寄存器；官方 0x83 矩形局刷可供未来小 ROI 受控试验，但仍走 OTP waveform。正式颜色码只有 0/1/2/3/5/6，7=`clean`、4 未定义 | 仍无任何一级来源确认 SPD1657(A) 的 runtime-LUT ABI、0x20/0x21 语义或双控装载合同；专利电压/帧数不可移植。公开检索没有访问设备网络，也未改写 payload/release |
| 2026-08-12 01:44 | C-first V4 最终封存、回归与隔夜硬停止 | matched-control V4 绑定 claim 单次读取、diagnostic canonical 同对象绑定，以及重核/逐字节相同/深验的私有 release snapshot；原 release 路径在 preclaim 后替换会拒绝。权威 release/canonical/host bundle=`1f9c3d7a...4673`/`95fc90dd...7f59`/`425e8bd2...e5a`，file SHA=`bca19992...b21f8`；V1/V2/V3 均 exit 2 fail-closed，原 empirical-H3 V4 身份不变且深验 PASS。最终 C-first host 14/14，其他联合 194 PASS + 8 subtests，总计 208 tests + 8 subtests；Ruff check/format（41 files）、py_compile、Windows GBK ASCII help 全 PASS | 明确保留三项边界：legacy runner 未物理禁用、pair 不能密码学证明 facade 使用、有权限进程仍可篡改临时 snapshot。真屏仍 `0/4`；今晚未访问 COM8/设备网络/硬件，未刷写、RESET、刷新或生成 token/claim；最后人工状态仍 `J2 OFF / 干净全白`，明日必须 fresh diagnostic 与重新授权 |
| 2026-08-12 02:14 | 文件名温度语义纠偏 + 中间 V5 纯软件重封 | 未找到任何厂家或公开一手 `WFxx_yy` 命名规范；撤回 WF20=`20–25°C`、WF23=`23–25°C` 的误读，文件名数字改为 opaque tokens，`temperature_compatibility_qualified=false`。基于相邻 E2801/E2802 固定 selector 25，只保留 exact `25.0°C` 的实验护栏，明确不是 vendor band 或安全资格。V5 当时完成 host 语义修正和 release seal，但后续 firmware-contract test 发现 runtime/recovery source/ELF 仍内嵌旧 contract/action IDs；当时 compiled-image validator 未把这些 ordinary strings 纳入 required-ASCII gate | runtime V5 WF20/WF23 release/canonical=`87e951ac...d7c4`/`bfbc86f4...78d4`、`692b5309...b89db`/`c34a9695...3d70`，host=`c8d753d1...c7c2`；matched V5 release/canonical/file=`ead6f983...c014`/`3192a3dd...4987`/`10e14481...84a5`，host=`ef921d13...ae96`。该里程碑现仅保留为 coverage-gap 证据；runtime/matched V1--V5 全部 fail-closed、不可执行。全过程离线，0 I/O/0 refresh，未刷写 |
| 2026-08-12 02:14 | STM32/ArmCC caller-length ABI 边界加深 | 新审计把 sample transport、ArmCC `loadWF` 与旧 UART helper 连起来：COUNTER 只参与 checksum，调用只传 pointer；loader 固定复制 544 并读 544/545，UART helper 忽略 `buff_len` 固定复制 535。当前只能判定 caller-bound contract gap，因 sample 未链接、receive stub 与真实 buffer capacity 缺失，不能声称已证明 OOB。byte5 结论纠正为“未单独用于 PWR/PLL/VCOM，但仍随 opaque R20/535 发出” | `mf1750_stm32_loadwf_abi_boundary_audit_20260812.json` file/canonical=`e9b37aaa...32e`/`dfd2678a...368`；相邻 42/42 PASS，Ruff/py_compile PASS。800-byte 当前 ArmCC ABI 仍 NO-GO；零硬件/COM/设备网络 |
| 2026-08-12 02:14 | XLIB provider-candidate graph + 一手 ABI 检索冻结 | 官方 ENTRY exact-name join 对 68 caller/index groups 给出 38 唯一候选、6 多候选、24 无候选，但所有跨对象 provider 仍 `proven=false`；main→E2801/E2802 display→upload 仅候选路径，非 final D43 linked root。独立一手检索确认公开 SPD1657/A/B、E2802、ED2208 均无 `0x20/799 + 0x21/704`、2508 slot 或双控提交/恢复合同；SPD1656 同号命令反而是 220/260-byte 强版本边界，`WFxx_yy` 无命名规范 | provider report file/canonical=`9f4ab28c...3221`/`de40c90b...fa66`，graph/XLIB/provider/temp 39/39 PASS；一手报告 `docs/SPD1657_PRIMARY_SOURCE_ABI_HUNT_2026-08-12.md` SHA=`78fbfdc9...452b`。结论仍 strict NO-GO / empirical conditional；无硬件 I/O |
| 2026-08-12 02:35 | V5/V6 identity coverage gap 闭合 + V7 最终离线重封 | V5 的 firmware-contract 失败证明普通 contract/action 字符串未受 compiled identity gate 覆盖；V6 更新 runtime/recovery/C/C-white source identity 并离线重编译全部六份映像；随后 validator 加固为 ELF 必须包含当前 contract ID、当前 action ID，且 runtime 还必须包含配对 recovery action ID。该 host source 变化使 V6 fail-closed，V7 以同一批已修正 BIN/ELF 重新封存。runtime/matched V1--V6 全部 superseded/non-executable | runtime V7 WF20/WF23 release ID=`52553c37...837e`/`9ea2100e...16f4`、host=`3e33b58e...37c0`；matched V7 release/canonical/host=`21bd8e57...7d27`/`c730a0e8...10e7`/`f74a79c7...ed73`、contract=`25267914...3fe`。两类 V7 release 均已离线 deep-validate；文档封版时不把尚待本轮完成的最终定向回归计数冒充既有结果。今晚没有访问 COM8、设备网络或硬件，没有刷写、RESET、刷新或生成 token/claim；当前设备仍为旧 WF20 V4，J2 OFF/白屏 |
| 2026-08-12 02:45 | V7 最终定向回归与静态检查完成 | 主流程重新深验 WF20/WF23 runtime 与 matched-control 三份 release，均返回 `valid=true`、`device_io=false`、`network_io=false`、`visible_refreshes=0`。联合覆盖 release/physical/finalizer、firmware/compiled identity、synthetic ELF 三类 identity 删除或替换、V1--V6 fail-close、ArmCC ABI、E2801/E2802、IAR graph/XLIB/provider、temperature selector、vendor profile/geometry/patent/SPI/artifact | 最终 `234 passed, 8 subtests passed`；Ruff check、Ruff format check（17 个本轮相关 Python 文件）、`py_compile` 与 Windows GBK CLI help 全 PASS。没有访问 COM8、设备网络或硬件，没有刷写、RESET、刷新、POST 或生成 token/claim；真屏仍 `0/4`，当前设备仍旧 WF20 V4，J2 OFF/干净白屏，明日必须 fresh J2-OFF 诊断和用户重新确认 |
| 2026-08-12 03:06 | Waveform invariant 统计 + IAR 实际配置链闭合 | 新统计在不输出 raw waveform 的前提下固定 WF20/WF23 全 800 bytes=`443 equal/357 different`、11-byte body=`439/353`、仅 `24/72` records 全同，且 11 个 record 列位置均至少一处变化；这些只能称 pair-level opaque invariants/dependents。新 IAR 审计证明 EWP 仅声明 `DELAY/E6_73/main`，Debug 实际直接项目对象仍仅三者；E2801/E2802/ED020OC4 都是 orphan candidates，Release 无交付产物。现成 `E6_73.r43/.d43/TI-TXT` 内嵌 V1.1_20231030 lineage，而交付源码是新增 6 处 VDD-cut 的 V1.2_20250116，故不能称 V1.2 rebuild | invariant report file/canonical=`84ac8584...c7f1`/`eb2c391b...8978`，新测 6/6；IAR config report=`b08d5e19...bebf5`/`15576687...da60a`，新测 10/10。加入两项 recovery-ELF identity 红队后主联合回归更新为 `236 passed, 8 subtests passed`；两项新工具均 Ruff/format/py_compile/GBK help PASS。判定仍 `NO_FINAL_LINKED_ROOT_TO_RUNTIME_UPLOAD_IN_DELIVERED_CONFIGURATIONS`；零硬件/COM/设备网络/载荷生成 |
| 2026-08-12 03:24 | Good Display 2026 官方固件深查 + 隔夜最终复核 | 固定官网 ZIP `8eaff3e3...868a96` 与 Wi-Fi/SD/USB 三份完整 ESP32-S3 flash identity。Wi-Fi 只证明六色 palette、四种 host dither 和未发现调用的浏览器 `adjustContrast` 定义；SD instruction-level xref 把唯一恢复的 SPI 初始化绑定为 GPIO `21/47/13/48` 的 SD-card SPI。三 app 均无 SPD1657/ED2208/WFxx/waveform/LUT 业务字符串，本地 E6 init prefix 0 次；raw `20 21`/704/2508 仅 untyped coincidences，799 为 0 次。因此未恢复 panel SPI、runtime-LUT、双控或亮度/对比度寄存器合同 | 正式报告 `docs/GOOD_DISPLAY_ESP32E6_OFFICIAL_FIRMWARE_STATIC_AUDIT_2026-08-12.md`；JSON file/canonical=`47320086...7213`/`cb54e656...1a09`，新测 7/7。最终 23-file 联合回归 `259 passed, 8 subtests passed`；23 个本轮相关 Python 文件 Ruff/format、`py_compile`、GBK help 全 PASS。WF20/WF23 runtime 与 matched V7 再次 deep-validate，均 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。今晚零硬件/COM8/设备网络/刷写/RESET/刷新/POST/token/claim；当前仍旧 WF20 V4、J2 OFF/干净白屏，真屏 0/4 |
| 2026-08-12 03:59 | IAR retained constant、ArmCC residual 与官方 app 面板路径三线收敛 | 官方 XLINK 证明 E2801/E2802 的 initialized `DATA0[1503]` 精确为 `first799 + FF704`，两对象逐字节相同；但全 PUBLIC root 后 part20/21 仍 `NOT NEEDED`、零自然引用，active R20/R21 仍分别来自 `dataBuff+4` 和 FF loop，799 不是 declared subobject。430-file ArmCC residual 审计只找到唯一 mode-0 library/member，Keil DEP/LNP/SCT/MAP/AXF 与 editor/capture 残留均无第二 mode-1 loader。三份官方 ESP32E6 app 则从 typed command/data helper 恢复同一 E6 OTP init、六 tag→4-bit packing、192000-byte display 和 panel transport；SD-card SPI 与 GPIO11/12 panel bitbang 已分离，但 typed graph 仍无 `0x20/0x21`、704/2508 或双控 | 新报告 DATA0 file/canonical=`5d9f76f8...ea5a`/`5d28d9d5...f123`，ArmCC residual=`2e19e229...2171`/`2cac3b63...aa9f`，cross-image=`3f82c21d...7f4b`/`8f6f9399...5854`；新增六文件 Ruff/format/py_compile 与 module-form GBK help PASS。26-test-file 联合回归 `278 passed, 8 subtests passed`；WF20/WF23 runtime 和 matched V7 再次 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。严格结论仍 NO-GO，经验 H3 仍 conditional，真屏 `0/4`。本轮零硬件/COM8/设备网络/刷写/RESET/刷新/POST/token/claim；仍旧 WF20 V4、J2 OFF/干净白屏 |
| 2026-08-12 04:50 | const-helper/category/79661/GxEPD2 四线收敛 + 夜间总回归 | 官方 XLINK/objdump 证明 legacy const/mutable LUT helper 是同一 `R12=cmd,R13=ptr,R14=count` generic sender，const 零已观察消费者且不绑定 DATA0/DATA1。五路 category 审计没有可转移标签；唯一 row0 公共 record 为 `10/11 FF` 的低信息 filler-compatible 片段，不支持 VCOM candidate。`79661.csv` 12722 行 every-window 扫描对全部已知 535/704/799/800/1503-byte payload 的 exact contiguous identity 均为 0，只保留一次性 pinned JD79661 init-fragment compatibility；缺 SCLK/CS/D-C/controller，事务仍不可恢复。GxEPD2 v1.6.0+ 的 `code4=orange` 与 Good Display 产品/规格/Image2LCD/2024 源码/2026 binary 的六码 `{0,1,2,3,5,6}` 冲突，固定为不可移植 adjacent-panel 假设 | const/category/capture/Gx 报告 file/canonical 分别=`c8b74fe3...de7b4`/`f78ee2c6...4baf0`、`f232446b...2ed4`/`572a86bc...0445`、`c6ac5803...b97f`/`9b4b2579...f9f8`、`8fb46381...86d2`/`89d0a0fb...e87a`。独立红队无阻断；29-test-file 联合回归 `304 passed, 22 subtests passed`，63 个相关 Python 文件 Ruff check/`py_compile` PASS，本轮 8 文件 format check、4 个 GBK module-help PASS。WF20/WF23 runtime 与 matched V7 再次 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。仅访问公开固定源码/厂家资料，未访问硬件、COM8 或设备网络，未刷写、RESET、刷新、POST、token/claim；当前仍旧 WF20 V4、J2 OFF/干净白屏，真屏 `0/4` |
| 2026-08-12 04:52 | 文档落盘后最终一致性复核 | 主逆向、目标完成度、公开资料报告和唯一状态入口已同步；再次覆盖 reverse-doc contract、repo contract 与四项新增审计 | focused `75 passed, 14 subtests passed`，新增/修改 8 个 Python 文件 Ruff/format PASS；无硬件、COM8、设备网络、刷写、RESET、刷新、POST、token 或 claim，现场状态与真屏 `0/4` 不变 |
| 2026-08-12 05:44 | 厂家源码/JD/XLIB/目的端四线收敛 + 最终离线回归 | Good Display 2024 源码与 2026 binary 在厂家六码 `{0,1,2,3,5,6}`、800×480 geometry、frame packing 和 init trace 上一致，code4 仍非厂家合同；JD79661AA 正式 30-command 表无 `0x20/0x21/E9`，PSR 只证明 register-LUT 概念，视觉红队纠正 p.64 为两个 example 均有同一 `LUT0 (20h)` marker，仍无长度/格式。schema-2 下载器固定 HTTPS URL、拒绝 redirect。官方新版 XLIB 匿名/本机可读范围未取得，修复下限 6.3.4.78，精确缺件为用户合法取得后的六条只读 LIST。新 destination 审计证明 legacy IAR R20/R21 只落固定 `P6OUT.3`，ArmCC mode-0 candidate 只落主 `PD8`，没有 800→同代799→双控链 | Good/JD/XLIB/destination 报告 file/canonical 分别=`03d8d340...8415`/`fdab7df7...5446`、`32762842...43ac`/`a82433e1...34ef`、`de6cecae...7ea0`/`d8f318b2...f8198`、`bcbf7a3e...8897`/`faedd107...6f17`。最终 33-test-file `332 passed, 22 subtests passed`；累计 71 个相关 Python 文件 Ruff/py_compile PASS，本批 8 文件 format、4 个 GBK module-help PASS。WF20/WF23 runtime 与 matched V7 再次 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。只访问固定公开资料；无硬件、COM8、设备网络、刷写、RESET、刷新、POST、token/claim。当前仍旧 WF20 V4、最后人工状态 `J2 OFF / 干净白屏`，真屏 `0/4`；明日必须 fresh J2-OFF 诊断和重新授权 |
| 2026-08-12 05:45 | 文档落盘后一致性复核 | 主逆向、目标审计、公开一手资料报告与唯一状态入口已同步；当前 primary report SHA=`43993055...dd27` 并由 reverse report exact 引用 | repo/reverse + Good/JD/XLIB/destination focused `76 passed`；没有硬件、COM8、设备网络、刷写、RESET、刷新、POST、token 或 claim，现场状态与真屏 `0/4` 不变 |
| 2026-08-12 06:30 | arithmetic/E2 projection/final-D43 三线闭合 + 公开增量检索 | schema-2 arithmetic 固定 `535/799/800/704/1503` 几何、DATA0/DATA1 无 active bridge，并只作有限 transform/checksum bounded negative；schema-2 E2 projection 在原件不变、25 个 inferred spans/592 bytes 的严格 allowlist 下取得官方 XLIB projection tables 与 52/52 index 一致，原件 native parse 仍待 `xlib>=6.3.4.78`；absolute D43 直接恢复 31 modules/2002 addressed bytes/188 calls，decoded image 与 TI-TXT addressed image 相等、`main→E6_73` provider 直接成立、E2801/E2802 非 final、named runtime upload NOT_FOUND。公开增量仅得到 Glider 外置 TCON/IWF、社区 OTP dump和旧屏同名函数等相邻/阴性证据，无同版 ABI | arithmetic/E2/D43 report file/canonical=`73003d11...8a4a`/`b77e5edb...015c`、`7d3ff40f...36bc`/`15647b3c...683c`、`7ed8e765...9886`/`51a646c7...8976`。最终 36-test-file `365 passed, 22 subtests passed`；新增 6 个 Python 文件 Ruff/format/py_compile、3 个 GBK help PASS；WF20/WF23 runtime 与 matched V7 再次 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。strict same-version ABI 仍 NO-GO、H3 仍 conditional、真屏 `0/4`；无硬件/COM8/设备网络/刷写/RESET/刷新/POST/token/claim，最后人工状态仍 `J2 OFF / 干净全白`，明日必须 fresh diagnostic |
| 2026-08-12 06:43 | 最终文档、公开来源与工件独立红队收口 | 主逆向、目标完成度、公开一手/相邻资料报告和唯一状态入口已同步；公开增量仍没有同版 SPD1657/E2802 799/704-byte 或双控 ABI。primary report 当前 SHA=`3a219b1b8048b80d66d27689e9bf9bf94ecd7fe1f74359f35a5cb3aca2c543a5`，reverse report 已 exact 引用；两轮独立红队均 PASS、无 blocker | 主联合 `365 passed, 22 subtests passed`；最终 focused `74 passed`；三份新 JSON 临时目录逐字节 replay 与 `30 passed`，Ruff/format/py_compile/GBK help PASS；三份 V7 保持 `device_io=false/network_io=false/visible_refreshes=0`。今晚未访问硬件、COM8 或设备网络，未刷写、RESET、刷新、POST、token/claim；仍为旧 WF20 V4、`J2 OFF / 干净全白`、真屏 `0/4`，明日必须 fresh J2-OFF 诊断与用户重新确认 |
| 2026-08-12 07:33 | 五线逆向增量 + 测试入口状态刷新 | 新增可复现 wrapper-alignment、ArmCC-DWARF、final-D43 GPIO/topology、535-byte record-semantics 与 UBROF11 E2 observed-dialect 五项审计：分别收紧 535/544 与 799/800 的 block-alignment 边界、`loadWF` source/call mapping、唯一 software-CS 与未证物理 J4、两份 `7+6×8×11` GROUP 表的 active/link/dataflow 层级，以及 32-object/139-record 的差分 observed grammar。它们仍未证明 outer byte 语义、11-byte phase/电气字段、原件官方 native parse 或精确双控装载 | 用户已询问现在能否测试；matched V8 C/C-white 与 runtime V7 WF20 T/T-white 两份 offline validator 已重新 PASS，但尚无 fresh 现场确认，故没有访问 COM8、硬件或设备网络，没有刷写、RESET、刷新、POST、token/claim。历史 J2-OFF/白屏/24.0°C/boot/diagnostic 均已过期；收到 J2 OFF、USB、干净全白、3.3 V/CV、exact 25.0°C、监测/切断就绪且未刷新/改接线的当前确认后，才允许 J2 OFF 刷 matched V8 C 应用区并 verify，再做 fresh `4 GET / 0 POST` diagnostic；可见 C 仍须另行授权。strict ABI 仍 NO-GO，H3 仍 conditional，真屏 `0/4` |
| 2026-08-12 07:51 | V8 红队、联合回归与发布包复验完成 | matched V8 只改正并密封 host CLI 的陈旧版本文字，C/C-white BIN/ELF 与 matched V7 逐字节相同；旧 matched V7 因 host bundle drift 按预期 fail-closed。独立红队确认代码/文档无旧 matched V7 当前 authority 残留；runtime V7 WF20/WF23 和 matched V8 三份 release 再次 deep-validate | 41 个目标测试文件分四批全部通过：`408 passed, 29 subtests passed`；五个新工具及五个测试 Ruff check/format、`py_compile`、GBK module-help 全 PASS。三份 validator 均为 `valid=true/device_io=false/network_io=false/visible_refreshes=0`。本轮没有访问 COM8、硬件或设备网络，没有刷写、RESET、刷新、POST、token/claim；仍等待 fresh 现场确认，真屏保持 `0/4` |
| 2026-08-12 23:28 | ArmCC/IAR 类型与 executable sink、相邻 runtime 合同及证据红队收敛 | 34-object/7-AXF inventory 把业务 R20 sink 限定为旧 `EPD_initial/535` 单-CS，R21 sink 为 0；官方 XLIB 直接固定 E2801/E2802 的 `DATA0[1503]`、`DATA1[704]`、`dataBuff[2560]`、loader/read ABI 与零 DATA0/DATA1 relocation refs。record-semantics schema-3 又纠正 `wf_data` 为可由 UART case-5 清空/替换的 mutable global，故 compiled initializer 不等于每次上传内容。EPM-100 WBF runtime parse/apply 与 ED2208-DOA `.eink` Initial Data 只提升为 adjacent 正证据，不移植命令、电压或格式 | ArmCC/IAR/record 报告 file/canonical 分别=`0f1befae...9412`/`07e7a78f...4e50`、`608f54b0...cd4a`/`2e777a28...a4e3`、`e2dd4ea1...c4eb`/`12954f59...0316`；focused 分别 6/16/12 PASS，Ruff/format/py_compile/GBK help PASS。用户本轮 fresh 确认 `J2=OFF`、ESP32 USB 已连接、exact `25.0°C`，但屏幕白态、3.3 V/CV、监测/切断与无刷新/改线四项仍待补齐；因此未访问 COM8、设备网络或硬件，未刷写、RESET、刷新、POST、token/claim，真屏仍 `0/4` |
| 2026-08-12 23:30 | 最终 44-file 联合回归 PASS | 首轮 7 项 setup error 已定位为沙箱账户读取既有临时 Git checkout 的 ownership gate；只在测试进程设置 `safe.directory=*`，不修改 global Git 配置，随后按原精确 44-file selection 完整复跑 | `460 passed, 29 subtests passed in 419.76s`、exit 0；另 reverse/repo 文档 focused `44 passed`。未访问硬件、COM8 或设备网络，未刷写、RESET、刷新、POST、token/claim；现场四项 gate 仍待用户补齐，真屏保持 `0/4` |
| 2026-08-12 23:57 | SPD1656 R20/LUTC 精确字段投影与全 offset 反证 | 固定 Rev 1.1 PDF 六页 text hash，直接恢复 VCOM `20×11` 的 `RP+LVL+TP` 布局，并在六个本地 dataset 上穷举 raw/complement 与候选 terminator byte 0--10。active raw 的 documented RP 零数为 `0/328`；complement 虽有 `37/41` byte0 zero suffix、`34/41` whole-zero suffix，但 byte0/6 并列，且 SPD1656 color 是 `20×13`，故不能迁移字段或电气语义 | 新工具/测试/报告 file/canonical=`3be92ff2...8668`/`8434152a...d94f`；新测试 `7 passed`；覆盖 phase/record/arithmetic/category/patent/invariant/reverse/repo 的联合回归 `101 passed`，Ruff/format/py_compile PASS。只保留 active-low/complement 结构假设；无硬件、COM8、设备网络、刷写、RESET、刷新、POST、token/claim。fresh gate 仍只确认 J2 OFF、USB、25.0°C，其余四项待补齐，真屏 `0/4` |
| 2026-08-13 00:14 | SSD1680A 8-group 相邻 ABI 精确映射与五窗口反证 | 固定 Solomon Systech SSD1680A Rev 0.20 PDF 身份及 pp.14/15/25/29 文本 hash，直接恢复每 LUT `8×7`、每组 `RP+4×(VS\|TP)+SR_AB+SR_CD`，四 LUT 后 R32 payload 共 227 bytes、完整 waveform setting 233 bytes；其 `0x20/0x21` 分别是 Master Activation/Display Update Control，和本地候选 sink 角色冲突。对 active 41 categories/328 records 的五个连续 7-byte window 逐一 raw/complement 投影，所有窗口均因位域穷尽而可解析、每 record 均余 4 bytes，故不能识别 offset、补码或本地字段 | PDF SHA=`92ccb43d...a43bc`；新报告 file/canonical=`d26f3f88...61a92`/`513b6dde...dcbe`；新测试 `6 passed`，Ruff/format/py_compile PASS。结论只提升“相邻 Solomon 架构确有 8 groups”，不支持把 4 phases 扩成 8、也不移植 RP/VS/TP/SR、零值、电压、时序或命令。未访问硬件、COM8、设备网络，未刷写、RESET、刷新、POST、token/claim；fresh gate 仍只确认 J2 OFF、USB、25.0°C，其余四项待补齐，真屏 `0/4` |
| 2026-08-13 00:28 | 完整现场门禁、V8 C app-only 刷入与 formal diagnostic 安全拒绝 | 用户在同一现场状态确认 `J2 OFF / USB / 干净全白 / 3.3 V CV / 25.0°C / 1.0 A 限流 / 0.001 A 电流 / 温度监测与物理切断 / 未刷新未改线` 并授权刷入。识别 ESP32-S3 rev0.2/MAC `a4:cb:8f:d9:fc:d4` 后，只将 matched V8 C 写入 `0x10000` 应用区；write hash 与独立 `verify_flash` 793968 bytes PASS，NVS/bootloader/partition 未动。新 boot 明确 no startup refresh/raw ingress/retry/autochain/profile switch | formal diagnostic 的沙箱首次尝试在网络前 WinError 10013；随后获批的 network attempt 依次完成 `version/manifest/status/report` 四次 GET，全部收集后才在本地 `_expect_version()` 因 `device version profile is absent` fail-closed；旧记载“只发第 1 个 GET”已纠正。失败证据 canonical=`501e94c6...f8e5` / `414cc790...f67`；0 POST、0 claim、0 ARM/EXECUTE/driver、0 可见刷新，C 仍 `0/1`。V8 已 superseded，不得复用该 boot/diagnostic |
| 2026-08-13 08:24 | V8 真实 firmware contract 根因闭合与 matched V10 重封 | 根因是 `h3mcVersionJson()` 没有输出 `"profile":h3mcOnceProfileJson()`；FakeDevice fixture 自己构造了正确 JSON，未覆盖真实 C++ 拼接。新增真实 source contract test，并先拦截 V9 首次修复的多余引号；V9 从未刷入。随后 clean rebuild C/C-white 两次，最终 BIN/ELF 分别=`f0ce5e7a...218e`/`27d23a21...d41` 与 `6ab18de0...51d`/`6aba1ecb...147`，compiled identity 均 PASS | authoritative V10 release ID/canonical/file=`1cf8307c...e36`/`5616bd49...b00e`/`a716dac8...698b`，trace ID/canonical=`e2ebf082...07f3`/`185d111e...877b`，host=`888ab013...416a`；firmware contract `9 passed`，host `14/14`，Ruff/format/py_compile PASS，V10/V7 deep validate PASS。V10 尚未刷入；随后 COM8/CH343 消失，只见蓝牙 COM9--COM12。保持 J2 OFF，重枚举并验证 MAC 前不刷写、不访问设备网络、不打开 J2 |
| 2026-08-13 08:44 | IAR sender 与 2021--2024 相邻 Solomon 公开资料增量落盘 | E2801/E2802 `EPD_Load_LUT` 逐指令数据流只做 command、byte load/SPI write、pointer/count increment；没有 complement、11/88 stride、值比较或 early stop，故只证明 MCU 发送侧原序固定长度，controller-side decode 仍 unknown。SSD1683/1683A 继续证明 8-group 实际为 7-byte group/R32-227；SSD1681 与 SSD1683 的 RP/SR zero 语义相反；SSD2677 公开 color/programmable-waveform/cascade 却不公开 runtime LUT ABI。COMPUTEX Solomon 自填页直接闭合 SPD1657 `800×600 active-matrix Spectra 6` 产品身份，不闭合命令/字段 | 四份本地 PDF SHA=`77c188ba...b5e9c`/`7946b986...7585`/`da23b888...07dd`/`a2245bba...ce2a`；主逆向、primary-source 报告、目标审计和操作卡已同步，reverse/repo/firmware/IAR/SPD1656/SSD1680A focused `76 passed in 4.25s`。结论仍 strict same-version ABI NO-GO / empirical H3 conditional；V10 未刷、J2 不得打开、真屏 `0/4` |
| 2026-08-13 08:52 | Solomon adjacent-family 可复现审计闭合 | 新增 `mf1750_solomon_adjacent_family_audit.py`，对 SSD1681/1683/1683A/2677 四份 PDF 固定 whole-file bytes/SHA、page count、16 页 normalized text SHA 与 required anchors；报告只输出 facts/hash/判定，不输出 PDF 全文或 waveform。跨文档直接固定 8-group/7-byte 延伸到 2023、SSD1681↔SSD1683 RP/SR zero 语义冲突，以及 SSD2677 公开 programmable-waveform/cascade 但 command table 不公开 runtime waveform write | tool/test SHA=`fc46ef3c...0602`/`42688dcf...ec30`；报告 13631 bytes，file/canonical=`94e46efb...9999`/`c090d254...a8f2`；新测 `6 passed in 0.83s`，Ruff check/format/py_compile PASS。未访问硬件/COM/设备网络，未生成 payload；V10 仍未刷、J2 禁止打开、真屏 `0/4` |
| 2026-08-13 08:56 | Legacy IAR sender schema-2 机器数据流闭合 | 加固既有 const/mutable helper 审计：四个 root-linked helper 继续共用完整 32-byte/14-instruction body；新增 SPI_DATA 关键指令合同，直接固定 entry byte copy、8-bit sign-test/left-shift 序列化和 `D7→D0` wire order。generic sender 的 loop 只按 caller count，source pointer 每次 +1；无数据值终止、11/88 stride、NOT/XOR/RBIT/REV 或 byte complement | tool/test SHA=`f14059ca...eac5`/`3b79d3a7...bb0f`；schema-2 报告 25392 bytes，file/canonical=`46046593...e0e5`/`01241e9f...9c09`；`11 passed in 2.74s`，Ruff/format/py_compile PASS。结论只到 MCU sender；controller 内部 active-low/complement、FF/zero semantics、当前 800-byte loader 和双控仍 unknown。零硬件/COM/设备网络/payload，V10 未刷、J2 禁止打开、真屏 `0/4` |
| 2026-08-13 09:16 | 真屏优先级收敛到色相 + V10/V7 重新复验 | 用户明确亮度/对比度按 host 图像处理理解，暂不要求硬件控制；VCOM 支线冻结，不做扫描。首轮真屏保持 matched C-first 设计：同一双控 8-code atlas 先在不发送 R20/R21 的 C 下显示并白恢复，再在 WF20 runtime T 下显示并白恢复；只把逐位置色相变化作为新颜色线索，明暗变化单列记录 | matched V10 与 runtime V7 两份 release 再次 `valid=true/device_io=false/network_io=false/visible_refreshes=0`；色彩关键定向回归 `13 passed in 15.28s`。较宽 97-test selection 先前在 240 s 上限前通过 21 项且无失败，但因未完成不计 PASS。端口复查仍只有蓝牙 COM9--COM12，ESP32/COM8 未枚举；V10 未刷、J2 必须保持 OFF、真屏 `0/4` |
| 2026-08-13 09:39 | WF20/WF23 色差结构定位 + 第二 profile 对照边界 | 新 metadata-only 工具把两份 identity-pinned 800-byte profile 精确拆成 `7 + 9×8×11 + 1`：全体 `443 equal/357 different`，prefix 4 处、body 353 处，72 records 中 24 条全同。零基 block positional mismatch=`36/43/48/59/55/0/52/60/0`；block 5/8 四者为同一 uniform 88-byte hash，但不能命名为空 category/terminator；block 7 只在 positional mismatch 上最高，bit-Hamming/L1 最高均为 block 3。由于 prefix 坐标 1--4 同时变化并进入当前 H3 PWR 构造，WF20-T 与 WF23-T 不能直接归因于 body；禁止 hybrid/单 block 修改。正确第二组必须另建 WF23 自身 header-matched C23/T23 平行链，且不得修改会令现有 V10 fail-close 的 WF20 密封源 | 正式报告 `docs/SPD1657_PROFILE_COLOR_DELTA_2026-08-13.md`；JSON file/canonical=`755b99d6...5de7`/`9b4b3412...fd1e`；新工具+既有 invariant `11 passed`。完整 trace 测试复跑发现唯一 V8 hash 陈旧断言，已只更新 test expectation 为 V10 C BIN/ELF，不改密封执行源；trace+两项 profile 联合 `20 passed`，Ruff/format PASS。V10 与 WF20 V7 再次 deep-validate `valid=true/0 I/O/0 refresh`。端口仍仅蓝牙 COM9--COM12；未访问硬件/设备网络、未刷写，J2 保持 OFF、真屏 `0/4` |
| 2026-08-13 10:38 | 第二代波形/T2000 与本地 800-byte ABI 隔离审计 | 固定 E Ink/Himax 2024/2026 T2000、E Ink 2025 第二代波形、OKRA 外置板与 MF-17506 厂规：T2000 是独立 TCON，处于 MIPI/USB/SPI host 与 mLVDS/TTL panel path 之间；外置 PCB 已有第三方实现。当前文档化模组则为 SPI、on-chip OTP、双 SPD1657/SPD1657B，不能把 T2000 当成插入现有 SPI 链的升级件。E Ink 的 3-bit/八主色与 standalone T2000 增色陈述保持分离，且公开来源没有绑定 SPD1657/E2802、0x20/0x21、799/704/535/1503/2508 或 11-byte 字段 | 新工具/测试/报告 `tools/mf1750_second_generation_waveform_architecture_audit.py`、`tests/test_mf1750_second_generation_waveform_architecture_audit.py`、`docs/MF1750_SECOND_GENERATION_WAVEFORM_ARCHITECTURE_AUDIT_2026-08-13.md`；JSON 20103 bytes，file/canonical=`3bad6cdd...a7bf`/`aaee09b1...e42`。聚焦 `8 passed`，Ruff/format/py_compile PASS。只做离线身份/文本/本地 profile/library 审计；无硬件/COM/设备网络/刷写/刷新/payload/token/claim，V10 未刷、J2 继续 OFF、真屏 `0/4` |
| 2026-08-15 09:00 | V10 timeout recovery Stage-A partial receipt 封存 | 用户 fresh 确认 `J2 OFF / USB / clean white / 3.3 V CV / 25.0°C / 1 A limit / 0 A / monitoring+cutoff / no refresh or rewiring`，并授权 intent `4361cbd4...eba7`。只读 PlatformIO 枚举 `COM8 CH343 / VID:PID 1A86:55D3 / serial 5C4C165475`；单次 esptool `chip_id` invocation exit 0，识别 `ESP32-S3 rev0.2 / MAC a4:cb:8f:d9:fc:d4`。命令含 `--before default_reset --after hard_reset`，最后 hard reset 已请求，但底层 reset 次数、post-reset app boot/V10/IP/API 均 unknown；严格 receipt 因此固定 `stage_a_intent_satisfied=false / stage_b_authorization_derivable=false` | transcript 339 bytes/SHA=`d4eefeb970d27fa7e76fc102e80719b48511b509378553be1c5e7f06953d044b`；partial receipt 6347 bytes，file/receipt ID/canonical=`f634ef7e01c412b3f2ee17448cbd939d12b87c8052ba5261e00ff350d2ebae5c`/`b728c367935e54c2d03639f93b95582183225d743b017c21fd9e4f85092900de`/`f82cb3eea5e9b33c8bbabd51b7275004d8ae0e6fee93538bb5f554d6a0678efc`；`5 passed`，Ruff/format/py_compile PASS。未 flash/设备网络/J2/刷新；ARP `.7→MAC` 仅 cache |
| 2026-08-15 09:16 | Stage-B read-only facade 离线蓝图封存 | 新工具 `tools/mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract.py` 与同名测试固定唯一 candidate URL、`version→manifest→status→report` 顺序与 fail-closed 释放语义：ARP `.7` 仅 candidate，未来 superseding contract 只能在首个 `/version` 立即验证 exact V10 成功后释放后三 GET，失败则不继续、不扫描、不 fallback。蓝图明确 partial Stage A 为 false，无 live 入口，`execution_ready=false / live_authorized=false` | artifact `.test-output/offline/MF1750_EC5_H3_C_FIRST_STAGE_B_FACADE_BLUEPRINT_20260815_V1/WF20_25-blueprint.json`，7750 bytes，file SHA/blueprint ID/canonical=`2ea8fa17fdf8639ba9736c1f88471188aa989d60a95e4db96fe9194ce960ceb9`/`1dbdf4af9ba52aeff9786aebcdfdb888c61b4ebae21b69a509664f3aefe1bc77`/`425790cb90c6ce84e72573c8469f8d21f6c1b37c99e1ebdba7dd7e0127258bba`；independent validate exit 0，`8 passed in 74.55s`，Ruff/format/py_compile PASS。未访问硬件/COM/设备网络，J2 保持 OFF，Stage A 未满足，Stage B 未授权 |
| 2026-08-15 09:24 | Stage-B V1 blueprint 红队否证，V2 exact-surface 重建中 | V1 的 fake-only 顺序/O_EXCL 测试本身有效，但不具备 live 证据资格：明文 HTTP `/version` 不能证明响应者就是目标 ESP32/fresh boot/active V10；更关键地，旧 `_expect_version` 仅检查子集、不拒绝 extra keys，并要求 FakeDevice 自行注入、而真实 `h3mcOnceProfileJson()` 根本不输出的 5 个 control 字段；故真实 V10 `/version` 将被必然误拒绝 | V1 artifact/file SHA `2ea8fa17...0ceb9` 已标记 `REDTEAM-SUPERSEDED / NOT FOR LIVE`。V2 必须由 C++ 实际四端点 JSON 产生面定义 exact key/type/value contract，并把通过结论降级为 `V10_PROTOCOL_RESPONSE_CONFORMANCE`。未访问硬件/COM/设备网络，Stage B 仍未授权 |
| 2026-08-15 09:49 | Stage-B V2 exact raw-response 蓝图三重闭合 | 新 V2 以真实 C++ 响应固定 version/manifest/status/virgin report 的 `24/51/36/34` 根键、profile 28 键、matched-sequence 14 键；原始响应必须先通过 size、strict UTF-8、duplicate-key/NaN/trailing/root 检查，再递归校验 exact key/type/value。fake 状态机只在当前响应通过后释放下一 GET，四端点任一解码失败均 terminal/no-retry；未来 live receipt 还必须逐端点保存 raw/canonical hash，并把 transport 异常的 wire emission/peer receipt 标为 unknown | V2 artifact 12433 bytes，file SHA/ID/canonical=`af8150cf...c51ea`/`eeb88d9b...e63a4`/`93e11e94...01fba`；实现与主代理各自 `27 passed`（主代理 `149.75s`），CLI deep-validate、Ruff、format、py_compile、逐值审计和独立 red-team 均 PASS。V1 明确 superseded；V2 仍 `execution_ready=false/live_authorized=false`、无 live CLI，并保留五个硬门。未访问硬件/COM/设备网络；J2 OFF、电流 0 A、真屏 `0/4` |
| 2026-08-15 11:05 | Phase-A offline authority/raw-fake 合同冻结 | 新合同固定 `.7` 只能 fresh 显式替代旧 `.14`、10 min现场门、A-only `/version`、registry-first/output-second O_EXCL、raw body无损封存与V2重放；失败证据按transport/body/header/envelope/exact五阶段互斥，孤立证据与“有效响应伪装失败”均拒绝。所有release/source深验均在reservation/fetch前，fake receipt永久不得进入Phase B | 工具/测试 SHA=`6226da376c...22d5c`/`51a0edb1ea...84d4`；实现、独立红队、主代理分别 `24/24 PASS`（269.05/268.60/260.77 s），Ruff/format/py_compile PASS。未物化authority/token/registry/receipt，无live transport/execute CLI，未访问硬件/COM/设备网络；Stage A仍false，Stage B未授权 |
| 2026-08-15 13:51 | Phase-A one-version live runner 代码/合同冻结 | 新 runner 只暴露固定 `.7:80` 的一次 raw-AF_INET `/version`；生产 CLI 无 host/port/clock/transport 注入。旧offline token不能执行，必须再经runner整文件SHA绑定的live envelope与独立exact token。所有深验在registry前完成；registry不可改写，output先sealed crash checkpoint，终态经bound temp完整重放后原子替换。HTTP status/header/body、Content-Length/Type/Connection、64KiB version cap、partial/overlong/raw/canonical证据及全部可达状态严格重放；成功最多为protocol-response conformance且不自动Phase B | runner/test SHA=`97b73f5e...82f8`/`d13caaae...c7ef`；full `45/45 PASS`（806.31 s）、fast20、single-success、独立quick22、双红队、Ruff/format/py_compile PASS。未物化authority/envelope/token/registry/receipt，未访问硬件/COM/网络；CAS抗特权并发路径替换、解释器完整性与断电持久性明确不证明 |
| 2026-08-15 20:59 | 当前三项现场状态与设备动作冻结续接 | 用户只重报 `J2 OFF / 全白 / 面板 0 A`，并禁止刷写、复位、打开 J2、刷新；其余完整 fresh gate 与 `.7` 替代选择未重报，故严格保持 offline，未物化 authority/envelope/token/registry/receipt | runner/authority/test SHA 与 13:51 handoff 一致；缺断言、错误 locator、错误电流及 10 min gate 定向回归 `3 passed, 21 deselected in 6.65s`。本轮 0 hardware/COM/USB/device-network/reset/flash/J2/refresh |
| 2026-08-15 21:09 | 当前三项部分现场门的 production CLI 零副作用证据闭合 | 新增端到端反例：即使测试显式补入正确 `.7` selection phrase，CLI 仅收到 `J2 OFF / clean white / 0 A` 时仍在 authority 写入前 fail-closed；socket 构造被硬阻断且零命中，authority/registry/receipt 与测试目录内其他文件均为 0 | authority 测试 SHA=`84b0815c...2052`；全量 `25 passed in 283.65s`，Ruff check/format PASS。stdout 113 bytes/SHA=`5b0092f9...765f`，stderr 0 bytes/SHA=`e3b0c442...b855`，路径 `.test-output/offline/MF1750_EC5_H3_PHASE_A_PARTIAL_GATE_AUDIT_20260815_V1/`；production authority/envelope/registry/receipt 扫描 0，0 hardware/COM/USB/device-network/reset/flash/J2/refresh |
| 2026-08-15 21:12 | 连续第三次输入边界审计与 goal 安全阻断 | handoff、Stage A/B、现场三项和未授权状态均未变化；authority/live-envelope/attempt-registry/terminal-receipt 两组扫描均 0。没有新的完整 fresh gate 与 `.7` 替代选择，已无可继续推进且不越权的物化步骤 | Codex goal status=`blocked`，累计 138450 tokens/890 s；阻断不是 FAIL。保持 0 hardware/COM/USB/device-network/reset/flash/J2/refresh；恢复时必须从新完整现场消息开始 |
| 2026-08-16 00:57 | fresh gate 恢复与 Phase-A authority/envelope 离线物化 | 用户同消息完整确认 `J2 OFF / USB untouched / clean white / 3.3 V CV / exact 25.0°C / 1.0 A / 0.000 A / monitoring+cutoff / Stage-A 后无 reset-flash-refresh-rewire`，并逐字选择未验证 `.7` 候选。直接文件入口首次因 `tools` import 在任何解析/写盘前 exit 1；确认目录不存在后改用 `python -m`，authority 与 live envelope 均 build+independent validate PASS | authority/envelope file SHA=`cdb65f52...206a`/`c506f415...bc23`，ID=`068f361b...1e8b`/`8d8be911...4e7a`；gate 截止 `01:02:58.437 +08:00`，授权词 948 bytes/SHA=`85fec329...b484`。registry/receipt/temp 0，socket 0，0 device-network/COM/USB/reset/flash/J2/refresh；等待第二条 exact 授权 |
| 2026-08-16 01:06 | V1 fresh gate 超时安全收尾 | 用户回复“继续”而非 948-byte exact phrase；只读本机时间为 `01:06:59.372 +08:00`，已晚于 `01:02:58.437`。runner 未调用，旧授权不补认、不重试、不换输出 | registry/receipt/temp=`false/false/false`；V1 artifacts 标记 valid-but-stale/non-executable，授权 SHA `85fec329...b484` 不得复用。0 device-network/COM/USB/reset/flash/J2/refresh；下一步回到新完整 gate |
| 2026-08-16 08:56 | fresh gate V2 authority/envelope 离线物化 | 用户在单条消息中完整重报现场门并逐字选择未验证 `.7:80` 候选；V2 authority 与 runner-bound envelope build + independent validate 均 PASS，fresh gate=`08:53:12.982 <= now < 09:03:12.982 +08:00`。本轮 exact token 尚未收到 | authority file/ID=`cadf1e92...1cc4`/`86d0f790...963a`；envelope file/ID=`4863bca3...78c8`/`3378b8e0...18e`；token 948 bytes/SHA=`6ae02383...4a06`。`08:56:37.758` registry/receipt/temp=`false/false/false`；0 socket/device-network/COM/USB/reset/flash/J2/refresh |
| 2026-08-16 09:02 | Phase-A V2 唯一 `/version` GET 终态成功 | 用户在 gate 内逐字授权；registry-first 后仅一次 `.7:80` raw GET，HTTP 200，2448-byte body 经 exact V10 replay PASS。终态严格为 protocol-response conformance，不是 responder/device identity、trusted IP、fresh boot 或 active-slot proof；attempt 永久消费、retry=false | registry 2753 bytes/SHA=`bc81e577...c56d`；receipt 17889 bytes，file/canonical=`cb7c65c4...7a94`/`75aabab5...9b00`，独立深验 valid+committed+success。1 GET/0 POST/body/claim/mutation/refresh/Phase B/recovery/autochain；`may_request_separate_phase_b_authority=true` 但未生成或执行；J2 OFF，真屏 0/4 |
| 2026-08-16 09:07 | C-first 条件式上机排程锁定 | 用户明确当前为 `可排程、未到执行门`；将 C/C-white 与 T/T-white 拆为 HWA/HWB 两个独立窗口，中间强制 C-leg finalization 与平衡，P0 只允许离线 Phase-B 合同审计。每个 GET、刷写、J2-ON 和 visible action 仍须到门后另行授权 | `docs/MF1750_EC5_H3_C_FIRST_HARDWARE_SCHEDULE_2026-08-16.md`；0 authority/token/claim/socket/device-network/COM/USB/reset/flash/J2/refresh，Stage A false、Stage B unauthorized、真屏 0/4 |
| 2026-08-16 09:41 | Phase-B P0 离线合同与 fake state-machine 闭合 | 新 gate 绑定真实 committed Phase-A 四件套并重放 `/version` raw body；只冻结 `manifest→status→report` 三 GET，定义 raw evidence、registry-first、terminal/no-retry 语义，且 CLI 仅 build/validate。synthetic success 只走 exact-type in-memory fake | gate file/ID/canonical=`30e13184...6617`/`72008bee...5b82`/`45c3f986...5a50`；fake file/canonical=`95573535...bd8f`/`d2ce9300...263a`；新测 `9 passed in 206.05s`，Ruff/format/py_compile PASS。planned live root/registry/terminal/temp 0，0 authority/token/claim/socket/network/device I/O；仍为 `可排程、未到执行门` |
| 2026-08-17 07:10 | Phase-B P1 runner/envelope 与一次性终态实现冻结 | 新生产 runner 只接受 fresh authority→runner-bound envelope→later exact token；固定 `.7:80 manifest→status→report` 三个新连接，每段 exact V10 验证通过才释放下一段。registry-first、durable output checkpoint、process-control indeterminate、O_EXCL temp+same-volume atomic replace、post-attempt replay 均实现；笼统中文授权在 registry/socket 前拒绝 | runner/test SHA=`bc3c6539...c8d3`/`c914d7bc...6338`；`7 passed in 145.34s`，Ruff/format/py_compile PASS。review file/ID/canonical=`07718d12...fd6f`/`d2c2f034...2f05`/`cd8f7f68...7bd4`；`execution_ready=false/live_authorized=false/device_io=false`。production authority/envelope/token/registry/terminal/temp 0，0 socket/device-network/COM/USB/reset/flash/J2/refresh |
| 2026-08-17 07:33 | Phase-B fresh gate 过期安全收尾 | `07:22` fresh gate 下只离线生成 authority/envelope；用户未在 `07:28:08` 前回传 exact token，runner 未调用 | stale authority/envelope/token 永久不可执行；registry/terminal/temp 仍 0，0 Phase-B socket/device-network/COM/reset/flash/J2/refresh |
| 2026-08-17 09:15 | 用户离场与硬件冻结 | 用户明确 J2 已物理断开、本人离开现场；ESP32 USB 按前一消息仍连接。转为纯离线准备，旧现场数值不继承为 fresh gate | 后续只有本地编译/文件/假设备动作；0 device-network/COM/USB/reset/flash/J2/refresh，核心真屏 `0/10` |
| 2026-08-17 09:15 | C23/T23 正式离线执行链闭合 | C23/T23 compiled trace、release、C23 one-shot、control-leg/pair gate 与 T23 preclaim facade 完成；两份 C23 固件本地重编译精确复现 | release file/ID/canonical=`4f8e2d7c...2130a`/`7350ff96...8836b`/`122bc606...9459`；C23 合计 `13 passed`，Ruff/format/py_compile PASS；0 I/O/0 refresh，硬件 `0/4` |
| 2026-08-17 09:15 | 五对十次晚间筛选 readiness 闭合 | C20/T20、C23/T23、factory-OTP dither 五对排为 10 个独立 action；5 彩色+5 白屏，动作身份唯一且每对后有安全停点 | readiness file/ID/canonical=`9a2c370b...5bca`/`d1d59b64...4d33`/`a64473b2...dafe`；`2 passed in 112.57s`，Ruff/format PASS。`same_evening_scheduling_allowed=true`，但 `execution_gate_reached=false/live_authorized=false`；候选新色后另做重复性/色度，不自动进入 137+ |
| 2026-08-17 17:48 | factory-OTP 像素抖动备选测试图与上机排程 P0 闭合 | 在既有比例色块+白之后新增七组连续双色渐变+白、综合效果图+白；完整 6 次，若核心 9/10 已 PASS 只新增 4 次。固定帧均只用六码，左右半屏同构，严格 PNG 只作名义几何预览 | bundle manifest file/canonical=`30c5b81c...a983`/`78c5397d...0e94`；readiness file/ID/canonical=`59f7b8a0...3e45`/`b50c25ee...2b78`/`953ca8dd...e14d`；定向 `7 passed in 138.13s`，Ruff/format/py_compile PASS。RC2G `9df89715...cd772` 仅 transport candidate；fixed adapter/release pending，0 authority/claim/device/network/COM/USB/reset/flash/J2/refresh |
| 2026-08-17 18:31 | factory-OTP 抖色扩展 fixed-compiled V2 离线执行链闭合 | 用专用四动作固件替代 P0 RC2G raw-frame 候选；三种固定帧在任何 panel I/O 前核对 full-frame 与双 DTM SHA/FNV/histogram。新增 compiled identity gate、campaign/staged→real finalizer、四 ordinal permanent-claim runner、双白屏角色观察合同和现场操作卡；同一 extension boot 内依次 gradient→white→effects→white，无 retry/recovery/autochain | BIN/ELF=`d6cd95f1...6c4a`/`4ec67c4a...a0f7`；staged release file/canonical=`b09a70a0...b6e9`/`c4858f0d...6c9`；V2 readiness file/ID/canonical=`6697266a...263e`/`5892f342...a56e`/`e83fbc63...2668`；operator card 6226 bytes/SHA=`59f36c12...0d5`。新增 `13 passed`，既有回归 `60 passed, 1 skipped`；staged release 正确 `execution_eligible=false`，等待未来核心 action10 white result/observation/claim。0 device-network/COM/USB/reset/flash/J2/refresh |
| 2026-08-17 21:28 | Phase-B V3 未消费收尾并由用户改走直接上机 | 用户回传 V3 exact token；runner 的宿主命令在 120 s 上限被终止，但只读复核确认 production registry、terminal output 与 temp 均不存在，因此没有可证明或可重放的 Phase-B HTTP attempt。V3 随后过期且不得复用。用户明确要求取消后续长 token 仪式并直接刷写/进入真屏 | V3 authority/envelope file SHA=`56c2237b...7db6`/`77c53251...9d4a`，attempt=`ff7a278c...b046`；Phase-B registry/output/temp=absent，0 已确认 Phase-B GET/POST/claim/refresh。该支线被后续 C20 新 boot 的完整 4-GET diagnostic 取代 |
| 2026-08-17 21:38 | authoritative C20 app-only 刷写、校验与新 boot 诊断 PASS | 在 J2 OFF 下只写 COM8 ESP32-S3 的 `0x10000` app 区；BIN 794080 bytes/SHA=`f0ce5e7a...218e`，write hash 与独立 verify 均 PASS，bootloader/partition/NVS 未写，verify 后仅一次 hard reset。COM8 CH343 serial=`5C4C165475`，ESP32-S3 rev0.2/MAC=`a4:cb:8f:d9:fc:d4`。V1 因 sandbox WinError 10013 在 socket 前失败；V2 被已知 legacy `_expect_version` 假阴性拒绝；V3 只替换该不兼容 version subset 为 source-pinned exact V10 surface，完整 `version→manifest→status→report` PASS | V3 diagnostic 1464 bytes，file/canonical=`ead506e8...6f5e`/`5b25201a...05cf`，boot nonce=`4ef561b45c052cd3`；4 GET/0 POST/0 claim/0 mutation/0 refresh。J2 全程 OFF，屏幕没有收到可见刷新请求 |
| 2026-08-17 21:44 | C20 matched no-R20/R21 atlas 首次真屏动作协议成功，等待人工视觉记录 | 用户 fresh 报告 J2 ON 后 idle=`0.001 A`、25.0°C、初始全白、无异响/异味/发热且物理切断就绪。一次性 runner 在永久 claim 后完成 4 GET preflight、1 ARM POST、1 EXECUTE POST、30 s silent window 与 3 次 report poll（其中 2 次读错误，末次取得 terminal success）；没有 retry/recovery/autochain/profile switch，设备合同记录 exactly 1 visible refresh | result 1588 bytes，file/canonical=`22cad4f7...bbb6`/`2bc73f3d...e18a`；claim 1006 bytes/SHA=`80a91dc0...b544`；action=`a83e82c7...b854` 永久消费、不可重试。已要求操作者记录峰值/结束电流、最高温度、八位置色相与异常后立即 J2 OFF；在该回报前只计 `1/10 protocol-executed`，不计视觉结论或 C-leg 完成 |
| 2026-08-17 21:50 | C20 atlas 人工观察封存 | 用户确认 J2 OFF 后电流=`0.00 A`，最高温度 25°C，无残影/条纹/其他异常；峰值没有实际观察，仅估计约 0.4 A，结束前约 0.01 A，因此峰值字段保持 null、估计值单列。技术码 0..7 依次肉眼为 `黑/白/黄/红/蓝1/蓝2/绿/蓝1`；左右控制器颜色种类一致并沿屏幕中心镜像，码 4 与码 7 同属“蓝1”，共 7 个操作者颜色组，不据此作物理色彩 qualification | observation 2369 bytes，file/canonical=`4fd13aa1...cd2a`/`69557f55...419e`；canonical self-check PASS。C20 atlas 计 `1/10 observed`，仍须独立 C-white 恢复，未授权 retry/autorecovery |
| 2026-08-17 21:55 | C20 factory-OTP white recovery app-only 刷写、校验与 fresh diagnostic PASS | 在 J2 OFF、面板电流 0.00 A 下识别同一 COM8 ESP32-S3/MAC=`a4:cb:8f:d9:fc:d4`；只把 788752-byte recovery BIN/SHA=`6ab18de0...a51d` 写入 `0x10000`，write hash 与独立 verify PASS，随后一次 hard reset。V1 误套 C-atlas exact facade，在 `identity_revision` 本地假阴性停止，0 claim/POST/refresh；源码核对后 V2 使用 recovery-aware frozen validator，完整 4 GET PASS | V2 diagnostic 1455 bytes，file/canonical=`499ea986...307e`/`affee1aa...0692`，boot nonce=`2d6bfabff1f07761`；ordinal2 claim 仍 absent，0 POST/0 mutation/0 refresh。当前 recovery 固件 ready、J2 OFF，屏幕应保持 atlas，等待 fresh J2-ON 电气确认后执行唯一白恢复 |
| 2026-08-17 22:01 | C20 factory-OTP white recovery 单次协议成功，等待人工白屏观察 | 用户确认 J2 ON 后 idle=`0.001 A`、25°C、屏幕保留彩色 atlas、没有任何异响/异味/异常发热且切断就绪。ordinal2 一次性 runner 完成 4 GET preflight、1 ARM、1 EXECUTE、30 s silent window 与首个 report terminal success；0 read error、无 retry/recovery/autochain/profile switch，合同记录 exactly 1 visible refresh | result 1595 bytes，file/canonical=`b0a3d629...d087`/`2bc17145...c3c9`；ordinal2 claim 1013 bytes/SHA=`bf1812b8...2c06`，action=`b2084e70...6235` 永久消费。已要求检查全屏白、atlas/格线/轮廓/色斑残留和电气状态后立即 J2 OFF；人工回报前 C20 pair 计 `2/10 protocol-executed`、仅 atlas 观察完成，C-leg 尚未 finalization |
| 2026-08-17 22:05 | C20 clean-white 观察、control-leg finalization 与 T20 preparation gate PASS | 用户确认 J2 OFF、全屏干净白，atlas 色块/边框/轮廓/色斑残留均无；峰值未观察、结束前 0.001 A、断开后 0.000 A、最高 25°C、无异响/异味/异常发热。白观察封存后，C result/claim/diagnostic 与 C-white result/claim/diagnostic 完整离线重放及独立 validate PASS；随后只生成不授权 live 的 T20 25.0°C preparation gate | white observation 1919 bytes，file/canonical=`8bc58ad5...684f`/`1875ef40...5400`；control-leg 4804 bytes，file/ID/canonical=`a75a0fa9...1db9`/`71af99cb...e7ed`/`e6d16ba7...6b00`；T gate 2226 bytes，file/canonical=`9bcb6254...1be0`/`b26f1e42...cca9`。C20 pair `2/10 observed+finalized` |
| 2026-08-17 22:13 | T20 runtime app-only 刷写、校验与 C-first fresh diagnostic PASS | J2 OFF、屏幕干净白下识别同一 COM8 ESP32-S3/MAC=`a4:cb:8f:d9:fc:d4`；只将 793776-byte runtime BIN/SHA=`53d3abf2...cc06` 写入 `0x10000`，write hash 与独立 verify PASS，随后 hard reset。C-first treatment facade 深验 finalized control-leg、T gate 与 pinned V7 release 后完成 4 GET/0 POST diagnostic | diagnostic 1158 bytes，file/canonical=`0b62a591...c6f0`/`b30901a4...2ff5`，boot nonce=`d3066b888bb691e9`；T20 action claim absent、0 mutation/0 refresh。当前 T20 ready、J2 OFF、全白，等待 fresh J2-ON 电气确认后执行第 3/10 次真屏 |
| 2026-08-17 22:16 | T20 runtime-LUT atlas 单次协议成功，等待人工对照观察 | 用户确认 J2 ON 后 idle=`0.001 A`、25°C、屏幕仍干净全白、无异响/异味/异常发热且切断就绪。C-first facade 深验 gate 后一次性完成 4 GET preflight、1 ARM、1 EXECUTE、30 s silent window 与首个 report terminal success；0 read error、无 retry/recovery/autochain/profile switch，合同记录 exactly 1 visible refresh | result 1354 bytes，file/canonical=`1008ba11...60f9`/`f64be621...69e9`；claim 797 bytes/SHA=`58575fd7...c30a`，action=`aa1deb1e...ad51` 永久消费。已要求记录码 0..7、左右镜像一致性及相对 C20 的色相/明暗/饱和度后立即 J2 OFF；当前 `3/10 protocol-executed`、`2/10 finalized`，T20 视觉结论待回报 |
| 2026-08-17 22:20 | T20 atlas 可见差异观察封存 | 用户确认 J2 OFF、结束前 0.001 A、断开后 0 A、最高 25°C、无残影/条纹/异常；峰值未观察。左右颜色类别一致并中心镜像。相对 C20，原“蓝1”组变白；按 C20 已确认映射即码 4 与码 7 从蓝1变白，因此 T20 码 0..7 记录为 `黑/白/黄/红/白/蓝2/绿/白`，只剩 6 个操作者颜色组 | observation 2450 bytes，file/canonical=`8d1f21a9...2d45`/`19d62139...d290`。结论为 `VISIBLE_DIFFERENCE_RECORDED`、无新色；该差异支持但不单独证明 R20/R21 接收或内部机制。T20 白恢复仍 required |
| 2026-08-17 22:23 | T20 factory-OTP white recovery app-only 刷写、校验与 fresh diagnostic PASS | J2 OFF、0 A、25°C 下识别同一 COM8 ESP32-S3/MAC=`a4:cb:8f:d9:fc:d4`；只将 785888-byte recovery BIN/SHA=`6a50b2bf...66d2` 写入 `0x10000`，write hash 与独立 verify PASS，随后 hard reset。generic empirical-H3 recovery ordinal2 完成 4 GET/0 POST diagnostic | diagnostic 1168 bytes，file/canonical=`fdd1abb5...c7e0`/`1ab8d363...21f5`，boot nonce=`4b62ca226019bb3c`；recovery claim absent、0 mutation/0 refresh。当前 recovery ready、J2 OFF，屏幕保留 T20 atlas，等待 fresh J2-ON 后执行第 4/10 次真屏 |
| 2026-08-17 22:28 | T20 factory-OTP white recovery 单次协议成功，等待人工白屏观察 | 用户确认 J2 ON 后 idle=`0.001 A`、25°C、屏幕保留 T20 atlas、无异响/异味/异常发热且切断就绪。ordinal2 runner 完成 4 GET preflight、1 ARM、1 EXECUTE、30 s silent window 与首个 report terminal success；0 read error、无 retry/recovery/autochain/profile switch，合同记录 exactly 1 visible refresh。宿主工具较晚 yield，但唯一进程正常返回 sealed success，没有重发 | result 1351 bytes，file/canonical=`2fafcaa7...f43b`/`d225e372...22b9`；claim 794 bytes/SHA=`61718f63...583c`，action=`6495a2c5...bd82` 永久消费。已要求检查 clean white 后立即 J2 OFF；当前 `4/10 protocol-executed`、`3/10 observed`，T20 pair finalization 待白屏回报 |
| 2026-08-17 22:43 | C23 matched no-R20/R21 atlas 唯一动作完成但旧宿主终态字段假阴性 | C23 source-shaped facade 完成 4 GET、1 ARM、1 EXECUTE 和 30 s silent window；设备 `/report` 为 `COMPLETE/result=true/driver_call_count=1/no_retry=true`，但固件输出 C23 专用键 `c23_matched_no_r20_r21_control=true`，冻结父校验器仍查 C20 键，故原 output attempt 保守封为 `TERMINAL_UNKNOWN_CLAIM_MAY_BE_CONSUMED`。永久 claim 明确 consumed，动作未重试 | original attempt file/canonical=`49848317...661a`/`667c3432...3a45`；claim SHA=`08b23c7b...53b`。只读 terminal snapshot 4676 bytes/SHA=`7aa659bc...1284` 经 source-shaped exact alias PASS；无额外 mutation/refresh |
| 2026-08-17 22:57 | C23 atlas 人工观察与终态 reconciliation 封存 | 用户确认 J2 OFF、电气正常、无残影；码 0..7=`黑/白/黄/红/蓝1/蓝2/绿/蓝1`，与 C20 未见差异、无新色。观察未重新给出峰值/结束/断开电流或最高温度，保持 null；只继承动作前明确的 0.001 A/25°C。兼容入口增加严格 C23 terminal discriminator alias，在线原始快照离线复验 PASS；另生成带原 UNKNOWN、claim 与 raw report provenance 的 sealed success reconciliation，并由 C23 control-result gate 完整重放 PASS | observation file/canonical=`6061f6d7...acd7`/`1d8301d8...e4e8`；reconciled result file/canonical=`1e702a53...ee76`/`ebd4db40...7819`；compat source SHA=`7af7321f...e83e`，py_compile/Ruff PASS。原结果不改写、action 不重跑 |
| 2026-08-17 23:27 | C23 factory-OTP white recovery app-only 刷写、校验与 fresh diagnostic PASS | 用户已确认 J2 OFF。复核 788656-byte recovery BIN/SHA=`8deba59e...f6edb` 后，仅写 COM8 ESP32-S3/MAC=`a4:cb:8f:d9:fc:d4` 的 app `0x10000`；write hash 与独立 verify digest PASS，NVS/bootloader/partition 未写，verify 后 hard reset。source-shaped facade 对新 boot 完成 4 GET/0 POST diagnostic | diagnostic 1451 bytes，file/canonical=`abb430d9...64e7`/`aadc1a4f...0a76`，boot nonce=`9c63220eb9bd22d2`；ordinal2 claim absent、0 mutation/0 refresh。当前 recovery ready、J2 OFF，atlas 按双稳态应保留但仍待操作者确认；等待 J2 ON 电气确认后执行第 6/10 次真屏 |
| 2026-08-17 23:35 | C23 white recovery DRF BUSY timeout，安全切断并冻结后续 | 在收到“现在请将 J2=ON”的明确指令后，用户回复“当前电流、温度、屏幕仍保留 atlas、无异常”，但未逐字重报 `J2=ON` 或数值；宿主按上下文放行并沿用最近明确 25.0°C。该上下文推断不是物理 J2 证明。ordinal2 唯一 action 完成 4 GET、1 ARM、1 EXECUTE，claim 永久消费。设备真实终态 `FAULT/result=false/driver_operation_failed`：frame/双 DTM identity 与 mapping 正确，PON BUSY 完成 179 ms，但 DRF BUSY 低电平持续 60010 ms 超时；随后 POF cleanup 等待 30005 ms，正式 POF 未到达。safe-finish 在面板针脚拉低 5 ms 后 BUSY 回高，final GPIO 全低 | 用户随后明确确认 J2 OFF，断开前/后电流=`0.001/0 A`、25°C、无异响异味发热，屏幕仍为 C23 彩色码 atlas，白恢复未产生可见效果。status=`fault_locked/phase3`，ARM/EXECUTE/driver 各 1；设备 BUSY 活动不等价于设备测得 J2 状态，故只固定 DRF timeout，不归因其物理根因。result/claim SHA=`1255567a...8d94`/`57c19106...5b68`；raw status/report SHA=`7945af15...45a1`/`42b4803a...8a8`。manual observation file/canonical=`4f2f2b87...cb92`/`674619f4...d4ef`；forensic supplement=`a155e783...4c68`/`5c5eba15...b804`。2 GET-only forensic、0 POST/reset/flash/retry/refresh；C23 leg 不可 finalization，T23 与后续真屏冻结，等待独立恢复决策 |
| 2026-08-17 23:58 | 独立 WF23 白收容动作已在 J2-OFF 下 ready | 用户澄清当前 J2 OFF，并要求到实际刷新门再明确通知接通。选用 pinned WF23 V7 中尚未消费、独立 namespace `otpw_w23_v1` 的 factory-OTP white action=`4acae834...c9856`；新 facade 以 C23 fault output/claim/status/report/manual/supplement 全部 exact hash 代替普通 T23-runtime prior claim，并把 fault evidence ID=`0d9d31d8...bcd0` 加入授权。该动作只作 fault containment，不计 T23 evidence | adapter 11546 bytes/SHA=`f99be12c...3159e`，py_compile/Ruff/format/describe PASS；恢复 BIN/ELF=`2712984d...9e7c`/`9c358728...3939` app-only 写入 COM8 后独立 verify PASS，未擦 NVS/bootloader/partition。fresh 4 GET diagnostic file/canonical=`2e74bb66...ebad`/`bae91b53...1af6`，boot=`2dd068288f26c995`，claim absent、0 POST/refresh。当前已到执行前门，等待操作者逐字 `J2=ON` 与实时数值 |
| 2026-08-18 00:02 | C23 fault 后独立白收容 protocol + 人工观察成功 | 用户逐字确认 `J2=ON / 0.001 A / 25°C / C23 atlas / 无异常 / 切断就绪` 后，standalone WF23 ordinal2 在永久 claim 后完成 4 GET、1 ARM、1 EXECUTE、30 s silent window 和首个 terminal report success；无 retry/autochain/autorecovery。随后用户确认 J2 OFF、全屏干净白、彩色码/边框/色斑残留均无，断开前/后=`0.001/0 A`、最高 25°C、无异响异味发热 | result file/canonical=`13028eae...be98`/`d3c550d1...cd44`；claim SHA=`0a594488...707b`。observation file/canonical=`ca29ad5e...8a35`/`920778f5...7db1`；final containment file/canonical=`877dab53...80ed`/`956958a6...43be`。物理 clean-white baseline 已恢复；原 C23 white fault 保留且严格 C23 control-leg/T23 pair gate 仍不可释放，standalone containment 不冒充 T23 evidence。当前 J2 OFF、0 A、安全白屏 |
| 2026-08-18 07:12 | factory-OTP 像素抖动 atlas 收容重绑定、app-only 刷写与 J2-OFF 诊断 PASS | 旧 dither release 的 2026-08-10 matrix-white 静态锚点已被后续刷新失效，新增窄作用域入口，仅将 ordinal1 live prior gate 重绑到 exact C23-fault standalone clean-white containment；固件、帧、两 action ID、NVS、claim、ARM/EXECUTE 与 ordinal2 Atlas→white gate不变。用户确认 J2 OFF/全白/0 A/25°C/无异常后，仅将 BIN `787312/49f39718...e7d4` 写 app `0x10000`，write hash 与 verify digest PASS，未擦 NVS/bootloader/partition。两次 GET-only 初查分别被宿主代理 502 与旧共享 validator 的 `dither=false` 假阴性拒绝；均 0 POST/claim/refresh。兼容层随后仅对 dither kind 要求 `dither=true/spatial_mixing=true`，递归 foreign context 保留各自 validator | rebind ID=`bb261109...7fa3`；adapter SHA=`c72f1fa5...c926`，py_compile/Ruff/format PASS。正式 direct/no-proxy 4 GET diagnostic file/canonical=`7c057477...1fbd`/`f8c6b6a4...7c3f`，boot=`027ed5c3c397f64a`，READY/next1/key absent、ARM/EXECUTE/driver=`0/0/0`、BUSY=0、claim absent，0 POST/0 refresh。当前 J2 OFF、面板仍为干净白屏；已到 ordinal1 真屏前门，必须先收 fresh J2-ON 电流/温度/无异常/切断确认，不自动执行 |
| 2026-08-18 07:51 | factory-OTP 像素抖动 atlas 单次协议 PASS，照片观察待补，J2 OFF 离场安全停点 | 用户 fresh 确认 J2 ON/0.001 A/25°C/白屏/无异常/切断就绪后，rebound ordinal1 action `ef645811...0a2c` 深验 clean-white containment 与 same-boot diagnostic，先永久 claim，再仅 ARM/EXECUTE 各1次；driver 34302 ms、sequence/mapping/双 DTM/DRF/POF PASS，终态 COMPLETE/READY/next2，同 boot=`027ed5c3c397f64a`，无 retry/recovery/autochain。用户初看报告“有好多颜色有很多颜色”，随后明确 J2 已关闭并离场，详细近/远观察与照片待回；未报告离场时电流/温度/残影等数值，故不推断、不封 final observation，不授权 white | result file/canonical=`056fc4e3...d475`/`348ee350...8c0b`，claim file/canonical=`98ecff5a...ff64`/`d5062873...8738`；独立 offline validate-result PASS。照片卡 `docs/MF1750_EC5_DITHER_ATLAS_PHOTO_CAPTURE_2026-08-18.md` SHA=`b6f6d79d...b520`；70-ROI perspective/photo analyzer SHA=`23233ef9...f9f1`，strict-preview self-test 左右35对 ΔE76=0，专项 `3 passed`、Ruff/format/py_compile PASS。用户离场后 0 device-network/COM/reset/flash/POST/refresh；当前 J2 OFF、atlas 保留，ordinal2 white claim absent。若 ESP32 boot 改变，普通 same-boot white gate不可直接继承，须先报告 |
| 2026-08-18 08:12 | 抖色扩展 current-source 隔离重构与 V3 readiness 离线闭合 | 用户离场并要求先做全部离线工作。新增 extension-only header 与 translation-unit wrapper，让专用构建包含共享驱动 bytes 后再追加扩展，不再修改共享 `epd_driver.cpp/.h`；两份共享文件继续精确命中封存 SHA。PlatformIO 仅 `run`、无 upload；新 BIN/ELF 深验四动作、三帧、唯一 loop display、唯一 setup validator、exact BIN↔ELF 与无 raw/LUT/waveform/retry/recovery endpoint。修正 Xtensa all-offset CALL 字节窗假阳性，仅在合同 caller 函数边界裁决；同时为 effects runner 增加 exact `dither=true/spatial_mixing=true` version/manifest validator，错误 false 值测试拒绝 | 新 BIN/ELF=`031c31ba...66b1`/`a6a1c488...f93d`；V2 staged file/canonical=`14bc3568...6d5a`/`62fd222e...a03a`，`execution_eligible=false/live_authorized=false/refresh_authorized=0`；V3 readiness file/ID/canonical=`5c102d32...7dee`/`8f4a4850...87d6`/`5ce17963...b911`，仍等待 atlas ordinal2 white 三件 evidence；runner SHA=`7f5eed5f...32ff`，operator card SHA=`cd460fb5...6c37`。联合专项 `23 passed, 1 skipped`。全程 0 device-network/COM/USB/reset/flash/J2/visible refresh；J2 按用户最后报告仍 OFF，照片待回。 |
| 2026-08-18 09:09 | A4 相对色彩拍摄登记为今晚 TODO | 用户确认晚间回场后拍摄并上传。照片卡新增明确 checklist：J2 OFF、哑光白 A4 与屏同平面同光照且白区不过曝、全屏+A4与左右近照保持相同相机设置、上传原文件，并补报 USB/reset/flash/refresh/rewire 连续性和电流/温度/异常 | photo card 4646 bytes/SHA=`07c57ae2661fc202b1496a612fd10a2dba22dfb4971ec3c7ad0459d438987ef2`。本次仅文档 TODO，0 device-network/COM/USB/reset/flash/J2/visible refresh；ordinal2 white 仍未授权。 |
| 2026-08-18 09:22 | A4 白纸相对参考分析 schema V2 离线完成 | photo analyzer 新增 source-photo `--white-reference x0,y0,x1,y1`，封存参考区 mean/median RGB、mean/std Lab、高光剪裁比例、相对 neutral gains，以及 70 ROI 的 white-relative Lab offset/ΔE76、RGB ratio 与 neutralized RGB；A4 明确保持 uncalibrated、不得作 absolute-colour qualification。合成画面外 A4 自测给出 70 ROI、左右 35 对 ΔE76=0、reference unclipped/usable | analyzer 23883 bytes/SHA=`3f941d6f6a23926b467129b67f9831757f4f4aea7df8119fd34ca27765cae6dc`；tests SHA=`fbd6e63c...d62c`；photo card 5719 bytes/SHA=`8aac90c5...c091`；selftest report 63711 bytes，file/canonical=`2ec46999...3750`/`3b7664f5...6836`。专项 `7 passed`，py_compile/Ruff check/format PASS。两次扩大聚合回归分别在出现 29/8 个 pass 标记、无 failure 后触及 180/120 s 宿主上限，故不计作完整通过；既有扩展 `23 passed, 1 skipped` 证据不改写。本次 0 device-network/COM/USB/reset/flash/J2/visible refresh；J2 仍按最后报告 OFF。 |
| 2026-08-18 21:16 | 首张真实全屏+A4照片初步 70-ROI 分析完成，正式 observation 仍待补 | 收到 1706×1279 JPEG，92,840 bytes、无 EXIF、带 ICC，按微信压缩预览而非原始相机证据处理；exact source 已复制留存。人工四角配准后 70 框均落在对应色块；A4 reference median RGB=`198/202/205`、任何通道≥250 clipping=`0`，usable relative reference=true。左右两半 14/14 行 endpoint projection 单调；每行四个相邻步共 28 个 camera-relative ΔE76=`6.07–26.80`。可见橙/赭黄、浅黄、黄绿/橄榄、紫/靛、棕、青绿/蓝绿与粉红；这是 spatial-mixing appearance，不证明单像素新颜料或 waveform/LUT 新色。左右 35 对 mean/max ΔE76=`4.2868/10.7674`，单张斜视/非均匀照明/压缩图不能分离 controller 与拍摄几何差异 | source SHA=`550bd3f9...b5df`；report 65672 bytes，file/canonical=`286454ef...888d`/`4f02edd8...bcbd`，integrity rebuild PASS；rectified/annotated SHA=`5090cb36...358d`/`2dc983e4...f020`；photo card 7682 bytes/SHA=`266eb3d4...40e0`。待原始相机文件、左右近照、near/mid operator words、USB/reset/flash/refresh/rewire 与电流/温度/异常字段；ordinal2 white 未释放。本次 0 device-network/COM/USB/reset/flash/J2/visible refresh。 |
| 2026-08-18 21:24 | 三张高分辨率原图/近照完成独立复核，照片证据齐全 | 原图为 Xiaomi 14 rear camera、HDR off、带 ICC/embedded metadata：右近照 3072×4096/6,738,294 bytes/SHA=`d7bce5d5...3f3e`，左近照 3072×4096/9,513,508 bytes/SHA=`9cf8814e...8e36`，全屏+A4 4096×3072/9,269,912 bytes/SHA=`ca74728e...bbde`；均已 exact copy 留存。近照解析两半 columns2–4 周期网点，50% checker-like 与 25/75% complementary sparse/dense texture 存在，无 mixed cell 被意外纯色替代。全屏原图再配准 70 ROI，A4 clipping=0、14/14 projection monotonic、28 adjacent ΔE76=`5.24–24.70`；与首图 projected-B fraction 差 mean/max=`0.0110/0.0601`。左右原图 mean/max ΔE76=`5.0928/13.0315` 仍只作 camera-relative，不能从单一照明归因 controller | V2 report 65647 bytes，file/canonical=`e0efc326...964a`/`251ce9eb...39c0`，integrity rebuild PASS；rectified/annotated=`ba76de3c...b33d`/`1e283bee...2223`，2× rectified=`7a3565a5...14e6`；photo card 10173 bytes/SHA=`2bec55c3...7e3f`。照片 evidence complete，仍待操作者 verbatim 电气/温度/连续性/近远观感后 seal observation；0 device-network/COM/USB/reset/flash/J2/visible refresh。 |
| 2026-08-18 21:55 | dither Atlas 人工 observation 封存，ordinal-2 white 离线前置门 PASS | 用户明确报告 J2 OFF、动作后/当前电流=`0.001/0.00 A`、最高/当前温度=`25/25°C`，自 Atlas 刷新后 ESP32 未重启且 USB/reset/flash/refresh/rewire 均无变化；网格/白缝/边缘/左右同序/约 1 m 七行过渡正常，无残影条纹或声味热异常。七行词为橙/赭黄、浅黄、黄绿/橄榄、紫/靛、棕、青绿/蓝绿、粉红；“第 2/4/6 行近看也看不到网点”逐字保留，与原图解析到像素周期按不同 evidence level 并存。第一次 seal 在任何写入前因 generic primer schema 要求显式 MAP-fidelity 而 fail-closed；基于用户已确认的布局/顺序/边界项补入后新建并回读深验 PASS | observation 2555 bytes，file/canonical=`00fcc331...fb9`/`86b63ab0...6458`，ordinal/action=`1/ef645811...0a2c`，MAP/sequence/electrical/no-restart=true，`physical_colour_qualification_inferred=false`，auto-next/retry/recovery=false。随后 ordinal2 exact prior result+observation offline gate PASS，required boot=`027ed5c3c397f64a`，white action=`35639e1f...eac3` claim absent；未生成/消费 live 授权。photo card 12206 bytes/SHA=`dde1ade0...62d2`。本轮 0 device-network/COM/USB/reset/flash/J2/visible refresh；当前 J2 OFF，下一步为 fresh J2-ON 现场确认。 |
| 2026-08-18 22:55 | ordinal-2 white live gate 发现未察觉 reboot，全部 mutation 前停机 | 用户 fresh 报告 J2 ON/0.001 A/25°C/atlas 保留/无异常/切断就绪。第一次 runner 的首个代理 `/version` GET 返回 502，在 claim 前抛错；result/claim absent。第二次明确 direct/no-proxy runner 完成只读 version/manifest/status 后，因 ready `arm_request_count` 不等于同 boot 预期 1 而在 claim 前 fail-closed。随后仅以三次 direct GET 读取 version/status/report：固件 exact identity 未变，但 boot nonce=`8c1391dabe9d1d31`，NVS `cursor_raw=2 / next_ordinal=2 / key-present / READY`，volatile ARM/EXECUTE/driver=`0/0/0`，report=`NOT_EXECUTED`。这直接推翻旧 boot `027ed5c3c397f64a` 的 ordinary continuation 条件，但也证明白动作尚未开始 | ordinal2 result/claim 均 absent；0 ARM POST、0 EXECUTE POST、0 driver、0 visible refresh、0 flash/reset/COM。不得把 preflight 重新运行称为动作 retry；不存在已消费 mutation。已要求立即 J2 OFF，等待回报后封存新 boot J2-OFF evidence并另审 cursor2 reboot-resume 窄门。photo card 更新为 12508 bytes/SHA=`726eccae...c42c`。当前最后已确认仍是 J2 ON，未收到 OFF 前禁止后续设备请求。 |
| 2026-08-24 00:15 | repeat-PTLW V3 同 profile 局部 HOLD 5/5 闭环 | factory-OTP白→code3暗A→code5蓝B→code6绿C→factory-OTP白全部 complete；后一区域刷新时旧区不闪烁，黑/蓝/绿最终共存。结论限定为三个固定窗口/指定码/same profile；底边齿线仍未解决 | `.test-output/hardware/MF1750_RUNTIME_LUT_REPEAT_PTLW_20260824_V3/`；BIN=`796496/81a0e6ac...57da4`，boot=`679f614b3864b874`，5 action JSON SHA 见当日计划文档 |
| 2026-08-24 00:32 | cross-palette AB packed-DTM fixture 修复与重封 | 修复 AB/BA compiled fixture 误走 uniform/window DTM identity；增加 packed controller DTM regression。AB/BA clean build、定向10 tests及Ruff PASS；BA未上机 | AB BIN/ELF=`793840/e56649be...573ca`、`13268060/21acf287...f8939`；BA=`793824/fc328a5b...bc646`、`13268020/63207354...06328` |
| 2026-08-24 00:47 | A→B 全屏跨 profile 8×8 历史矩阵 5/5 | 每控制器64历史格、全屏128格；target后红/粉、黄绿/橄榄等区域保留source分段，identical target repeat后部分仍可见。支持跨profile历史依赖，不含partial/0x83，不计为64/128/256种新色 | `.test-output/hardware/MF1750_RUNTIME_LUT_CROSS_PALETTE_AB_20260824_V1/`；boot=`315e5dd117432501`；diagnostic+5 action SHA见当日计划文档；三张照片 SHA=`e92a878b...28c1/2890e235...d829/ff19002a...b034` |
| 2026-08-24 00:52 | 当日白恢复与物理收口 | AB ordinal5 device COMPLETE、campaign complete；操作者确认刷白后关闭上游电源。relay COM14/channel1 commanded OFF，独立 query 返回 OFF；无负载侧反馈，`electrical_state_proven=false` 保留。此后仅离线工作 | `action-05-white-recovery.json` SHA=`812c6e4d...6d16`；当日总结与下一步见 `MF1750_STAGE3_CROSS_PALETTE_LOCAL_HOLD_PLAN_2026-08-24.md` |
| 2026-08-24 07:16 | cross-profile partial-HOLD V1 同 boot 5/5 闭环 | factory-OTP白→active/code5蓝A→commented/code6绿B并保持A→active/code3黑C并保持A/B→factory-OTP白全部协议COMPLETE。人工观察：A蓝色正常但底边有间隔线；B绿色出现时A保持且外围白；C黑色出现时蓝绿均未闪；最终三块清除并恢复干净白。可记固定窗口/码/global-header序列下 `A→B` 与 `A→B→A` 局部共存初步PASS，不外推到任意LUT/颜色、256色或照片质量 | boot=`04f47262e8236ded`；BIN=`797152/7f5870b0...79e`；evidence=`MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_LIVE_20260824_V1`；actions SHA=`37a5cc00...b258/0dfa71d3...27e5/f98470ab...60e1/706074f1...a773/0a11c5f3...57ab`；campaign complete/next6，无retry/recovery/autochain |
| 2026-08-24 07:30 | Blue 64-recipe 明度筛选 6/6 协议闭环，视觉阴性且白收尾失败 | 同boot完成runtime白→source列→commented middle行→active/code5 target→同target repeat→runtime白。action4/5人工观察左右矩阵一致、内部无深浅差异，故64配方=`0 visible blue brightness candidates / 0 qualified`；action3彩色中间态曾见深浅差异但未定位，只保留为其他目标色线索。action6设备COMPLETE但操作者确认蓝矩阵原样保留，必须记`PROTOCOL PASS / VISUAL RECOVERY FAIL` | boot=`7de23beca3837011`；BIN=`795376/afc978e1...a93d56`；actions SHA=`84712ebf...b6a3/83006157...22d6/938a82d9...540d/65e10c34...82c1/03ddb890...6aeb/7802f005...4116`；campaign complete/next7；main全部永久消费 |
| 2026-08-24 07:31 | 蓝矩阵保留状态下离场安全停点 | 操作者表示准备离开并要求关闭电源；未再发刷新、刷写或复位。COM14/channel1执行OFF，随后独立query再次返回OFF。面板按双稳态保留蓝矩阵；上游断电没有另行反馈，故不推断；relay无负载反馈，`electrical_state_proven=false`。下次唯一首项为Blue专属fresh factory-OTP containment，人工clean-white后再开展其他目标色 | containment BIN/ELF=`786448/82e49e99...ea12f`、`13214100/d1e89562...16250`，action=`808d5fb9...838555`，claim/output仍absent；现有host runner须先离线补direct/no-proxy、J2-OFF diagnostic与claim时机 |
| 2026-08-24 08:20 | Blue收容runner加固与multi-target V1离线封版 | Blue专属收容runner已完成直连/禁代理重定向、4 GET后claim与单次ARM/EXECUTE约束。新九动作multi-target完成AB+BA各64条历史recipe、target repeat和1/5/9 factory-white分派；另建fresh独立收容。终审无代码阻断；新主+收容49 passed，8相关文件171 passed，Ruff/format/py_compile/describe及产物哈希PASS | 主BIN/ELF=`799552/b1f25c89...cb1e`、`13286676/b48be696...bb216`，contract=`7f653cc9...958da`；独立收容=`786512/f6e943b3...d9f2`、`13214104/88ee12f6...8180`。离场后0设备网络/COM/刷写/复位/刷屏；当前仍relay OFF+蓝矩阵，下次必须先Blue factory-OTP白收容 |
| 2026-08-24 16:57 | B3 WROOM/Power/TF 原理图 parity 清零与 R4 功能布局重建 | TPS63070 `R29=10 kΩ`、本地 `C46/C47=10 µF/0603` 已纳入；F1 PTC 与 U8-U11 USBLC6-2SC6 符号/filter 修正。权威原理图 ERC 0、合同246/246、B2继承655/655；自包含 native parity由9降至0，U1删除canary精确报1项。R3重同步、R4功能布局及机械间距复核完成，B2保护铜/器件零漂移，WROOM全层天线禁布、TF下侧朝外、H3/H4和U4热环路布局通过当前门；正式PCB保持旧R2未覆盖 | SCH=`158e54c1...10bf0`；R3 PCB=`c43446b3...f22fb`（144 DRC/205未连接）；R4 PCB=`349ef014...f2fbf`（确定性重建相同、native parity0、13/13、174 DRC/205未连接）；`r4_functional_placement_report.json`。当前为未布线HOLD，正并行开发TPS63070与BQ/PowerPath关键路由脚本；全程0继电器/J2/COM/刷写/复位/屏幕操作 |
| 2026-08-24 18:29 | B3 R5 U4→BQ/PowerPath→EPD 关键路由链完整 PASS | staging-only 串联器按精确 source SHA 固定三分支；U4/BQ/EPD 各自确定性重建，EPD pads12–18 到 7 网/9 个冻结 B2 anchor connected-set 全 PASS。独立复核发现并修复 U4/BQ 相同 UUID seed 造成的74对重复对象；新 BQ=932/932、最终板=1091/1091 UUID 唯一，链尾唯一门及旧候选负向 canary均PASS。最终 self-contained DRC parity0、fatal扩展集0、37 open（drill12/silk22/starved1/dangling2）、141未连接；board verifier13/13，天线禁布侵入0，正式PCB/R3/R4/原理图/工程哈希均未改变 | final PCB=`3aa2e70d...c73ec`；BQ=`4b0fbc2b...79c89`；chain runner=`f75cf014...b48bb`；audit=`56e802a9...b9b8e`；DRC=`8fb60859...c2c4a`；verifier=`13504138...802a`。状态仅为关键局部 `ROUTED_CANDIDATE / WHOLE-BOARD HOLD`，后续优先 SYS_3V3、MCU/EPD MCU侧、TF、USB 与制造清理；全程0继电器/J2/COM/刷写/复位/屏幕操作 |
| 2026-08-24 20:05 | B3 R6 EPD边界路由关键链独立审计 PASS，整板仍HOLD | staging R6最终板哈希保持 `41fcea36...bcf28`；R4→placement→U4→BQ→EPD 继承链、四阶段各两次复跑、UUID唯一、In1非GND铜为0、B2继承/新增80条精确、天线禁布与verifier13/13均PASS。fresh native DRC parity0、关键fatal 12类全0，但仍有36项findings、其中13项error severity（12 drill_out_of_range+1 starved_thermal）及141未连接，因此只能记critical-route scope verified，不能记整板通过 | audit script=`D75261E6...6B017`；audit=`55495428...0BC7`；verifier=`8F3AAC09...9303`；DRC=`AF735008...4214`。`operation_completed=true / critical_route_scope_verified=true / locally_verified=false / overall HOLD`；未修改正式PCB、原理图或既有builder，未访问硬件。 |
| 2026-08-24 21:12 | multi-target 8×8 AB/BA 历史筛选收口并独立白收容 | 主BIN app-only写入/verify后，同boot完成ordinal1–8，每动作恰好1 ARM/1 EXECUTE/1 visible refresh，无retry/recovery/autochain。AB target同行差异无法与光照可靠区分，repeat后人工确认无明显深浅变化；BA source列基本一致，BA target产生强纵向源历史色带，但identical target repeat后基本收敛为同行同色，故记显著但不稳定的单次历史过渡态，`0 qualified new stable colours`。ordinal9在claim/ARM/EXECUTE/refresh前因raw-ready BUSY门拒绝，主campaign立即封存。relay OFF下写入并verify独立收容BIN，fresh 4 GET诊断PASS；relay ON后唯一factory-OTP white COMPLETE，操作者确认“全白”，随后relay OFF | 主action1–8 SHA=`F4D2B7D8...3431/71EB0253...3904/26ED99F7...1433/72181EB6...E1D0/815C47F8...1C0/8EF943AA...AA3/3D5BF8C2...6E78/04D11CFC...3BBB`；ordinal9拒绝记录=`C3E7EB85...276E`；照片=`8D6699B5...12F/1A87FD36...563/348C56F1...ECB`。收容BIN/ELF=`f6e943b3...d9f2/88ee12f6...8180`，boot=`868a1b56b00b9c0b`，diagnostic/result=`3A185FD4...D2E5/AB28C29C...7129`；当前屏幕全白、COM14/channel1 commanded OFF、`electrical_state_proven=false`。 |
| 2026-08-24 22:19 | Endpoint A/B 底边端点交叉实验5/5收口 | J2-OFF app-only写入 Endpoint A/B BIN 并独立verify PASS；relay ON后同boot严格完成factory白→端点A蓝→factory白→端点互换B蓝→factory白。Action1/3/5人工均确认全白干净；Action2刷新中与最终均见两块蓝色底边连续黑线且两侧一致，Action4互换端点后仍见连续黑线。异常不随`y+h-1`/`y+h`处理交换，故endpoint-only假设不获支持，`y+h`不得作为修复。5项均device COMPLETE、每项1 ARM/1 EXECUTE/1 driver/1 visible refresh、无retry/recovery/autochain；最终campaign complete/next6。随后relay OFF并独立query OFF，屏幕保持干净白 | boot=`be596f0f974f95ab`；actions SHA=`aede1f03...96ac8/652bca8d...f0897/2512c8be...90a0/faf6d1a1...f038/909a550d...9f73`；Action2/4 driver=`41939 ms`、DRF=`33891 ms`完全一致；BIN=`796864/5c339268...404e8`；`electrical_state_proven=false`。下一步离线准备8行guard方向交叉，尚无新的live action。 |
| 2026-08-24 23:05 | GUARD_DIRECTION_AB_V1 主固件与独立白收容离线就绪，尚未上机 | 已建立隔离guard driver/program、fresh identity/NVS/claims、5动作controller crossover、三处raw BUSY=1门和独立factory-OTP white containment。两侧均固定蓝ROI `x=176..335,y=240..359`；BOTTOM=`120行0x55+8行0x77, PTLW y240..367`，TOP=`8行0x77+120行0x55, PTLW y232..359`，每控制器严格128行/10240 B并在PON BUSY后重复同一PTLW。主/收容clean build、Ruff/format/py_compile、foreign-cwd describe、direct/no-proxy `diagnose-j2-off` mock合同及专项`9 passed`；离线工作期间0设备网络/COM/继电器/刷写/复位/刷新 | 主BIN=`797168/db5857e7926828cddb4fd9ac44ac860e275f5323060b7932ed429e2ab8d6e312`，ELF=`13291304/b285190f80318279d1460aefe263265f8fb0576f36f0f294c004a6f50f15a5f4`，contract=`c1ca226b7b5934dfba75daa7f03419c31438246638c86356d480e0abba84590c`；收容BIN=`786544/41fbf8a5c60f749ef1321a1397552c0e84696aae7975c5571d1b8b085cd9667d`，ELF=`13214128/7f4f2b3873fdc04870d3cc8ad5cdf0e971beaa4fc602b8d3688898f842424154`。用户今晚已离场，relay/J2已确认OFF，屏幕干净白；Guard未刷入。明早严格为白→A（CS1 bottom/CS2 top）→白→B（互换）→白，共5次真屏；异常时不跳序，立即OFF并改用独立收容。 |
| 2026-08-24 23:11 | Guard/Endpoint 隔离总验收口 | 独立Guard源不再改动Endpoint共享repeat源；Guard+Endpoint联合定向回归`17 passed`，Ruff与`py_compile` PASS。发现Endpoint封版后共享头增加两枚举reverse-role enum，故以封版时ABI快照在原路径事务式clean build，逐字节命中已执行Endpoint的旧BIN/ELF；随后立即恢复现行共享头并复核reverse-role仍在 | Endpoint BIN=`796864/5c3392684e50545d6f8ac03727d13bcd96ddf1f90cd2cede1ffa1435495404e8`，ELF=`13290228/1ce6bb2db9868c590748dbe5ce46fafaaf4147cdc8092b6b16935489744963d8`；现行共享头SHA=`d1788eb691b3dcaf5bd62a82721de8032f20bbb29e5cf52ff97e7ec4d03e0b6a`。全程0硬件/串口/继电器/设备网络访问；J2继续OFF，Guard仍未刷入。 |
| 2026-08-25 人工回填 | Guard Direction 方向假设未获支持 | 操作者后续完成上下guard两方向肉眼观察：两种处理均仍见连续黑色底线，两侧一致，方向互换没有带来干净边；最终factory-OTP白恢复干净并关闭驱动板电源。因本次未在此处绑定独立live protocol/claim哈希，只记人工视觉阴性，不追认为完整机器闭环；旧Guard不再重放，也不做`8→4→2→1`细化 | 结论：端点与单侧guard都不是可接受修复；当前面板用户报告全白、驱动板电源OFF，`electrical_state_proven=false` |
| 2026-08-25 18:50 | Fullframe-vs-PTLW A/B 离线固件封版 | 综合现有STM参考，将两处理收敛为相同L535、相同code7完整SRAM预装、相同code5 ROI、相同最终SRAM及相同`PON→DRF00→POF00`action-stage刷新；A只发完整复合DTM且无PTLW，B只发一次包含式PTLW与9600-byte crop。固件对preload、target component及preload||target combined流做SHA/FNV fail-closed门；factory白动作保留共享BTST2，runtime action-stage不额外写CDI/BTST2/PON后PTLW/0x86/填充字节。clean build、专项12 passed、Ruff、py_compile、foreign-cwd describe和BIN/ELF绑定PASS；0设备网络/COM/继电器/刷写/复位/刷新 | contract=`9e7414f483174cc74fa8adca9c1c2ea4c23c3250f84882969f34e87efb25a8fa`；BIN=`799408/6e42e3b08ec8053a3efea3e4f12d334dc246abb99576454188136391fa1130fb`；ELF=`13301880/b64d7216ff240df3a736542418cf263c0112bc03469388798e19c1fb34dcc405`；runbook=`MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_RUNBOOK_2026-08-25.md` |
| 2026-08-25 19:29 | Fullframe/PTLW 原V1 factory-white健康锚成功，但后续raw-BUSY门死锁并封存 | app-only写入/verify与fresh J2-OFF 4 GET诊断通过；relay ON后ordinal1 factory-OTP white恰好1 ARM/1 EXECUTE/1 driver并COMPLETE，PON/DRF/POF=`180/22521/141 ms`、total=`35012 ms`，操作者确认干净白色。POF后安全收尾将RST/CS/CS2拉低，稍后raw BUSY由1降为0；旧固件和runner把该安全保持态误作不可执行，ordinal2在0 claim/0 POST/0 refresh前停止。relay off/on也未令raw BUSY变高，故原V1封存，不重试、不绕门 | boot=`35d91cbde71348d6`；action1=`7ce176c1a08075a63d994ac0b9182bddbf6ba430b91a35191ecb10b6dc75dde0`；claim=`21882cb18fa6df3520ca9ea74d8dd6efa8d44141f8576ba23146995a3725e8b7`；diagnostic=`fd91d1d2c7e994c99cc671d83ce335616ee83f3868bb8c8780243db85d3b30fc`。A/B treatment均未执行。 |
| 2026-08-25 19:58 | V1B fresh factory-white在PON超时，fault锁定并完成白屏/relay OFF安全收口 | V1B用RAM-only同boot late-POF资格修正后，final app-only写入与独立verify PASS；fresh J2-OFF诊断4 GET/0 POST/0 claim。relay ON后ordinal1在explicit fresh-low门下唯一执行：reset/pre-command idle通过、双DTM上传完成、PON BUSY已出现，但`60010 ms`未回空闲；未进入DRF，cleanup POF后safe-finish三次BUSY均为1，设备持久化FAULT。runner终端读取失败后只做4 GET salvage，确认1 ARM/1 EXECUTE/1 driver，action永久消费且不得retry。操作者随后确认屏幕“干净，白色”，并再次确认“目前全白”；COM14/channel1执行OFF并独立query OFF。该观察不能把失败动作改判为成功刷新，只证明最终画面未见污染 | BIN/ELF=`800224/48fb0397948385feb2a0b155dca22bbb741e346df1a0edd7871c8765bd7181c3`、`13303904/a0b20e1a44847693027b7dfca9276d3e9ba1befbd89f735c07a8986db3885d8d`；contract=`e6e8802a3fd93f1f867c20f1e2013dc4ade410881b2ade46d1e1fb60d9821cb5`；boot=`59f89f6255ec54ae`；diagnostic/action/salvage/claim/observation SHA=`7b05f46f...e35f/a5f8bf1a...f09d6/7780ed0d...c851/48d20ff9...45c7/c2409bc3...b9f5`。当前`electrical_state_proven=false`，只允许离线取证与新identity设计。 |
| 2026-08-25 20:14 | V1C no-PON readiness审计fail-closed并加固完成 | 源码与V1/V1B实测联合证明：raw BUSY高、reset-idle完成、双controller revision稳定都不经过PON高压路径，不能证明PON可完成；V1B正是这些数字门通过而PON 60.010 s超时的反例。审计重新计算并验证V1 success/V1B salvage canonical integrity，精确绑定firmware/contract/build/boot/action/descriptor；两次driver的input与双DTM FNV、SPI=`1 MHz`、CS1/CS2 upload=`2444/2444 ms`完全一致，三份核心驱动源码仍逐字命中原V1 offline manifest。该一致性只排除已知driver/source/payload差异，不证明瞬态电气状态。未生成V1C可见固件或runner，决定`visible_action_allowed=false`、V1B ordinal1不得retry。若继续，只能单独审查会真实发送PON但不发DRF的`PON→busy-idle→POF`资格探针，或重排持久化时机 | tool=`tools/mf1750_runtime_lut_ptlw_fullframe_ab_v1c_readiness.py`；artifact=`.test-output/offline/MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1C_READINESS_20260825.json`，SHA=`64d8fafc71bd4c422a98792eafe3e2cbecc6978ed76d5ca8addca027c2c6daaf`；fullframe联合定向`25 passed`，Ruff、`py_compile` PASS；0 COM/网络/继电器/刷写/复位/刷新。 |
| 2026-08-25 20:16 | 近期runtime-LUT raw BUSY/PON相关性只读聚合完成 | 筛选`.test-output/hardware/`下一级`MF1750_RUNTIME_LUT_*`目录根部`action-*.json`，成功样本要求`outcome=complete_pass`、首个status BUSY=1、terminal result=true且timeout=none；共35项、8个campaign，全部成功，PON分布=`180 ms×8 / 181×2 / 259×1 / 260×18 / 261×6`。独立raw0 attempt按salvage去重后恰为3项：Repeat-PTLW V1 boot=`ebe0ef3c433fadf2`、V2 boot=`73575a44e0405073`、Fullframe V1B boot=`59f89f6255ec54ae`；三项均PON BUSY seen、pre-command idle未失败、PON=`60010 ms`、DRF未到、safe-finish=`1/1/1`。只记强相关，不冒充因果证明 | 结论：raw0不得再作为fresh action admission；下一现场先核验继电器下游驱动板输入3.3 V/GND及PON启轨压降/限流。0硬件访问、0文件修改型设备动作。 |
| 2026-08-25 23:39 | PON/POF no-DRF资格V1在PON前安全拒绝并封存 | 用户重新开启继电器上游电源。relay query保持OFF；最终BIN仅写COM8 app `0x10000`，write内建hash与独立verify均PASS，同一ESP32-S3 rev0.2/MAC=`a4:cb:8f:d9:fc:d4`。fresh boot=`11d42b6997869774`完成J2-OFF 4 GET/0 POST诊断后短暂relay ON；唯一QUALIFY只执行reset+REV，CS1=`01 01 04`×2、CS2=`00 00 00`×2，在`cs2_revision_trivial`处FAULT。PON/POF/DRF/DTM/LUT/PTLW/0x86/visible refresh全部0；arm/execute/probe/driver均0。relay立即OFF并query OFF；GET-only salvage以attempt+reserve为锚写终态receipt，永久claim保持absent，V1不得retry | BIN/ELF=`786816/fda829c0...accc`、`13111404/2d21c7d3...2efb`；diagnostic=`11311/e24fd61a...2d37`，attempt=`900/305bd857...53a1`，reserve=`503/a4b7465c...c629`，salvage=`21309/f5870ba7...cce24`。历史已验证REV路径每样本前reset；当前转为全新V2 per-sample-reset离线实现，旧V1 NVS/marker不清除。 |
| 2026-08-26 19:04 | B3 WROOM/Power/TF PCB 推进至统一 R8d staging 基线 | 从 R7 hygiene（13项已知DRC、141未连接）开始，十条 EPD MCU 侧网络布通后降至128；随后以严格单网白名单依次加入 `/USB_INPUT_VALID_N`、`/DCDC_PG`、`/PWR_INT_N`，未连接数依次 `128→127→126→125`。边缘访问版将 SW1–SW5 与 USB-C 转向左侧、TF 与 J6 朝下，并重建精确八条 `/USB_VBUS` 源铜；最终 `125→123` 只来自 J5 四个 GND 焊盘接入平面（`GND:-2`），未虚构 VBUS 改善。R8d fresh KiCad 10.0.3 审计为 DRC13（12个WROOM 0.20 mm热焊盘钻孔+1个保护区 `/EPD_SW_3V3` dangling）、native parity0、verifier13/13、双构建字节一致，B2/天线禁布/In1 GND与全部祖先铜几何保全 | unified PCB=`9a0f1e30...2403`，builder=`bae5045e...8e2`，report=`5d405700...ef6`。`/DCDC_EN` 首次候选虽使 `125→122`，但新增2 short+2 track-not-centered+1 starved-thermal，已 fail-closed 且未合并；JLC04161H-7628 层叠API探针亦因 KiCad API 不能可靠写入精确结构而 fail-closed、未生成候选。正式 PCB 仍保持旧 R2，整板继续 HOLD；下一步为重布 `/DCDC_EN`、`/PS_HOLD`、改善 J6/C49 手焊间距，再处理精确层叠/USB阻抗、TF/电源余网及WROOM热焊盘制造门。本轮0硬件/COM/继电器/网络/刷写/复位/屏幕操作。 |
| 2026-08-26 23:29 | Fullframe-vs-PTLW V2 5/5 真屏闭环，固定局刷底边首次干净 | 先前独立 PON/POF no-DRF V2 资格探针已 COMPLETE；本固件同一 boot=`22a0acda523dc334` 严格完成 factory白→A完整复合DTM/无PTLW→factory白→B单次inclusive PTLW+9600-byte crop→factory白。五项均恰好1 ARM/1 EXECUTE/1 driver/1 visible refresh、双控REV=`01 01 04`×4、PON/DRF/POF均完成，无timeout/retry/recovery/autochain。人工观察：A与B均为左右各一蓝色矩形、外围干净白、左右一致且底部没有黑线；中间与最终白均干净，最终无残留。由此否定“PTLW本身必然产生黑线”，并证明当前`完整code7预装→一次inclusive PTLW→只写crop code5→PON/DRF/POF，PON后不重复PTLW`对该固定窗口/码/profile可得到干净四边；旧黑线的具体差异仍未完全隔离，不外推到任意窗口、任意色或跨LUT叠加 | BIN=`815600/0433f678...863c4`；actions SHA=`ffd56224...9c8ee/e551ce03...04b15/4fffa5e3...e68b5/9e300279...1b93/db9527a7...ed3f`；manual observation=`16cade9d11e5c8ecaa8158e6cf109640c55fa52f724348cb5bd1b6a19375b4ac`。ESP32 DHCP从旧候选变为`192.168.1.11`，ARP MAC仍精确匹配`a4:cb:8f:d9:fc:d4`；未刷写、未复位。最终COM14/channel1 commanded OFF且独立query OFF，`electrical_state_proven=false`。下一真屏应把该干净传输移植到多窗口cross-LUT HOLD，复测蓝/绿/黑共存和全部四边；通过后才进入8×2色盘正式标定。 |
| 2026-08-27 00:11 | clean cross-LUT HOLD V2 五步真屏闭环，固定跨盘共存与六格干净边通过 | app-only写入/verify与fresh J2-OFF诊断通过后，同boot=`9355f29a468dfc35`严格执行factory白→active/code5蓝A→commented/code6绿B保持A→active/code3黑C保持A/B→factory白。五项机器均`complete_pass`，每项恰好1 ARM/1 EXECUTE/1 driver/1 visible refresh，0 retry/recovery/autochain。操作者逐项确认：“全白干净”；“蓝色，左右正确，没有黑线”；“绿色ok，四个都没有黑线，原来的蓝色没有闪烁”；“黑色ok，六个都没有黑线，原来的蓝绿色没有闪烁”；“白色，干净”。因此固定A→B→A跨profile局部HOLD、蓝/绿/黑共存、旧区不闪及六格干净边均PASS；不外推到任意盘/码/窗口/长期保持或256色。随后COM14/channel1 commanded OFF且独立query OFF，操作者离场，转为严格离线 | BIN/ELF=`816656/9139c4d2...060a`、`13368436/683f4578...15ce`；contract=`d9059cd9...948b`；actions SHA=`bc3bdab0...b6e8/d88b1d4a...a562/25eb90ba...c993/1f647111...01c4/7f2d46c0...2261`；manual observation=`9cad3a42f6cd6d48093e749ccb0fd23d7c354df7510d3ab33aa11d76b12e7c77`。下一步仅离线冻结红/粉、黄/橄榄明度候选；操作者返回前0设备动作。 |
| 2026-08-27 01:04 | 红/粉与黄/橄榄历史明度V1离线冻结，same-boot审计阻断闭合 | 两套均为每侧8×8=64个均匀单码历史recipe、无空间抖动/partial，六步为factory白锚→active source列→commented middle行→固定active target→显式候选后才允许repeat→factory白；并各有fresh独立白收容。独立审计发现初版same-boot仅由host实施、device重启后可direct POST续跑，故初版合同/IDs/产物全部作废；最终版以专属NVS持久first-boot nonce，在setup/ARM/EXECUTE/dispatch四处driver前fail-closed，重启或containment后不能回主。快速门固定为ordinal4无差异即封存并改刷containment，只有命中才ordinal5复核。两条独立审计最终PASS；主代理最终联合`163 passed`、Ruff/format/py_compile PASS、四describe离线、两份SHA清单逐项0失败。全程0设备网络/COM/relay/flash/reset/refresh，现场仍relay OFF、屏幕干净白 | 红/粉主BIN/ELF=`801888/70952827...c07d8`、`13297008/72011ccb...8f8f`，收容=`787216/277ee416...d513`、`13214292/a6ea106b...c9db`，contract=`df7ecdc4...0278`；黄/橄榄主=`802208/7e45f52d...8563`、`13299612/5a8fabd6...5ae5`，收容=`786544/80dfebbd...61ec1`、`13214132/4e846aca...e8e8`，contract=`47cff189...4899`；SHA清单=`c1668770...3eeb/1e660b9b...6271b`。 |
