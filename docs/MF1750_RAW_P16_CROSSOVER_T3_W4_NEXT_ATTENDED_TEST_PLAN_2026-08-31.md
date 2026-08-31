# MF1750 T3/W4 下一次有人值守测试计划

> **2026-08-31 13:38 替代说明：** 本文的 full-panel V3 路线已因固定机位局部 ROI 选择和
> T3 V1 首 GET 终态失败而停止。未产生 claim、POST 或刷新，relay 最后复核 OFF。下一执行入口为
> `docs/MF1750_RAW_P16_CROSSOVER_T3_PARTIAL_DUAL_3X8_RECOVERY_PLAN_2026-08-31.md`，不重用 V1。

状态：`OFFLINE READY / NOT EXECUTED`

## 1. 当前起点

- 操作者已经离场；本轮只允许离线代码、测试和文档工作。
- 最新 exact-bound relay query 为 channel1 commanded `OFF`，但仍不是负载侧电气证明。
- 屏幕按双稳态继承 W3 干净白；T3/W4 均未安装、未 claim、未执行。
- 正式 W3 相机 attempt 尚未消耗。
- 2026-08-31 06:01 的 setup-only 照片没有拍到面板且严重欠曝；它只证明当时机位不合格，
  不能作为 W3 白参考或任何正式角点来源。
- 从操作者本次离场、进入本轮离线修订后，不再访问相机、继电器、COM、ESP32 网络，不刷写、
  不复位、不刷新屏幕；06:01 setup-only 相机与 05:59 relay query 作为更早的历史事实保留，
  继承状态不会因本文或离线测试而改变。

## 2. 下一次测试的核心目标

### 2.1 首要目标：判定颜色差异跟随波形 profile 还是跟随物理半屏

已完成的 T2/CA 人工粗观察为：

- CS1/commented535(C)：橄榄、黑、绿、白、浅黄、蓝、黄、黑；
- CS2/active535(A)：红、粉、绿、白、棕、蓝、深粉、深蓝。

下一次 T3 只交换完整 A/C profile：CS1=A、CS2=C，frame、DTM、编码和位置平衡布局保持冻结。
已经封存的 T2/CA 人工基线可作人眼 screening 参考，但没有 T2 同机位相机照片。因此：

- 相机单独能够赚取 64 格几何、四副本一致性、三帧稳定性和画面瑕疵结论；
- **相机单独不能**判定 profile-following 或 physical-side-following，无真实 T3 人工 seed 时
  最高为 `HUMAN_CAMERA_SCREEN_REVIEW`；
- 要回答首要问题，必须把当前 T3 的真实 16 个 controller/code 人眼标签封存，再与已绑定的
  T2/CA 人工基线比较。标签可在 atlas 保留时观察，也可从这三张 exact JPEG 事后填写；不得
  由算法猜测色名。

满足上述证据后，预期决策分支为：

1. 若 T3 的 A 组外观跟随到 CS1、C 组外观跟随到 CS2，并且每个 code 的四副本及三张照片
   都稳定，则获得“profile-following 候选”证据；下一阶段可围绕有效色相做重复与明度细化。
2. 若外观仍固定在原物理左右半屏，则优先调查双 controller、数据路径、公共模拟条件或面板
   左右差异，不能把它解释为 LUT 调色盘差异。
3. 若同组四副本或三帧不稳定，则说明位置／照明／残留或历史态尚未隔离，停止颜色命名和
   色数估计，先修复重复性。

这仍是相机辅助的人眼粗筛，不是绝对色标定；本次完成后 `qualified_colour_count` 仍保持 0，除非
以后在固定照明、24 色卡和人工复核下另行通过正式资格门。

### 2.2 次要目标：确认画面质量

- 两侧各 `4×8`、合计 64 格完整；
- 每个 controller/code 四副本至少 3 个有效；
- 三帧中每组至少 2 帧有效；
- 检查底边黑线、水平／垂直条纹、中心接缝、残留、裁切、失焦和曝光异常；
- 最后必须由 W4 恢复为干净全白并使 relay commanded `OFF`。

## 3. 修正后的采集原则

原采集器要求在拍照前填写“该照片四角”，存在时序循环。当前正式版已统一改为两阶段：

```text
acquire
  -> 相机打开前永久消耗本次 O_EXCL attempt
  -> 只拍一张并封存 JPEG、sidecar、action snapshot 和哈希
  -> 不接收角点，不给出 accepted 结论

admit
  -> 人工或查看工具只从上述同一张原始 JPEG 读取 TL/TR/BR/BL
  -> 不再打开相机
  -> 执行几何、64 格、白场/atlas、跨帧漂移和亮度门
  -> O_EXCL 写入 ACCEPTED 或 REJECTED 结果
```

禁止：用历史照片角点、setup-only 照片角点或另一帧角点冒充正式照片自己的四角；禁止覆盖
claim/result；禁止自动 retry、fallback 或 autochain。

## 4. 下一次有人值守的固定流程

### G0：取景与光照门，不消耗正式名额

1. 操作者把 48MP 相机对准屏幕，完整显示有效区和四个外角，避免遮挡与强反光。
2. 保持 J2 OFF；exact-bound query 必须仍为 OFF。
3. DirectShow 必须唯一命中 `48MP USB Camera / VID_32E4:PID_4801`，并明确排除
   `VID_1BCF:PID_0B15`。
4. 使用固定档取得 setup-only 画面：`MJPG 4000×3000@15 / focus79 / exposure=-6 /
   WB4600 / warmup8`。
5. setup-only 最多两次；它不属于五张正式照片、不能导入正式 bundle，也不能提供正式四角。
6. 只有整屏完整、未裁切、面板区域可辨且光照可用才进入 G1，否则保持 OFF 并停止。

### G1：正式 W3 白参考

1. `acquire --slot w3-white-reference`：claim 后只拍一张，不需要预填 corners。
2. 查看该 exact JPEG，在未缩放原图上读取活动显示区 `TL/TR/BR/BL`。
3. `admit`：对同一 JPEG 做 64 格投影和白参考门；全部有效位置要求 `L* >= 25`。
4. 最多两个正式 W3 attempts；失败不自动使用第二次，必须检查原因并明确继续。

命令骨架（变量只在现场绑定 exact action result 后填写）：

```powershell
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py setup-view `
  --output-root $camRoot --action-result $w3Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py acquire `
  --slot w3-white-reference --output-root $camRoot --action-result $w3Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py admit `
  --slot w3-white-reference --attempt <CLI返回值> --output-root $camRoot `
  --panel-corners '<TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy>'
```

### G2：唯一 T3 atlas 刷新

1. J2 OFF 下 app-only 写入 T3 并独立 verify。helper 的准确启动语义是
   `write --before default_reset --after no_reset`，随后
   `verify --before no_reset --after hard_reset`；这产生一次验证后的应用启动。禁止的是额外／人工
   reset，不能把 helper 自带的 reset 错记为 0。
2. fresh J2-OFF 诊断必须为 `4 GET / 0 POST / 0 claim / 0 refresh`。
3. relay ON 后执行冻结 `run`。raw `BUSY=1` 门位于 runner 内：exact 4 GET 之后、任何
   claim/ARM/POST 之前；当前没有“BUSY 通过后再暂停”的独立子命令。
4. 仅允许 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`；retry/recovery/autochain=0。
5. 无论成功或 fault，随后均保护性 relay OFF；fault 时停止，不重试。

### G3：T3 三帧封存与粗筛

1. 在 atlas 双稳态保留且 relay OFF 时，分别执行三组 `acquire -> admit`。
2. 为取得三张 accepted 照片，总 attempt 上限为 5；每张各自从自己的 JPEG 取得四角。
3. 白参考和三张 atlas 必须保持同一 exact camera path、mount、requested/effective settings、
   4000×3000 尺寸；对应角跨帧最大漂移 `30 px`。
4. 四帧 bundle 深验和 O_EXCL seal 通过后才开放 W4。相机分类本身不阻塞安全刷白。
5. 自动粗门：四副本 max `DeltaE00 <=8` PASS、`(8,12]` REVIEW、`>12` FAIL；三帧中心
   max `DeltaE76 <=3` PASS、`(3,6]` REVIEW、`>6` FAIL。低信心最高为 REVIEW。

每张 atlas 必须完整执行 `acquire -> 查看该 JPEG -> admit` 后，才允许取得下一张；不能先拍三张
再统一填角。全部 accepted 后执行 `seal`。相机报告若没有真实 T3 human seed，只能输出 REVIEW；
此时可先完成 W4 安全收容，但 profile-vs-side 结论保持 `NOT_EARNED`。

### G4：独立 W4 白收容

1. 明确从已封存 T3 恢复执行；不得由 T3 自动串联。
2. J2 OFF 下 app-only 写入 W4、独立 verify、fresh 4-GET 诊断；沿用 G2 的同一 helper reset
   序列：`default_reset -> write/no_reset -> verify/hard_reset`，额外／人工 reset=0。
3. relay ON 后由冻结 `run-white` 在 claim/POST 前检查当前 W4 raw `BUSY=1`。
4. 只执行一次 factory-OTP white，随后 relay OFF。
5. 使用 W4 专属两阶段 wrapper 拍末端白：最多 2 attempts，`acquire -> admit -> seal`，
   检查白场、残留和几何；不得由通用相机命令绕过预算。只有
   `full_screen_white_gate.passed=true` 且 classification=`PASS` 才 accepted 且可 seal；
   `REVIEW/FAIL` 都是终态 rejected，可在剩余总预算内人工明确取得 attempt 2。
   两次均未 PASS 时保持 OFF，由操作者明确确认白屏，不能把“文件已封存”冒充“白屏通过”。

W4 命令骨架：

```powershell
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py acquire `
  --output-root $w4CamRoot --action-result $w4Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py admit `
  --output-root $w4CamRoot --attempt <CLI返回值> `
  --panel-corners '<TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy>'
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py seal `
  --output-root $w4CamRoot
```

## 5. 停止条件

出现以下任一情况立即保持或切回 relay OFF，并停止自动流程：

- setup-only 仍未拍到完整面板或照明不足；
- exact 48MP 身份、路径或固定设置不一致；
- 当前照片角点、64 格投影或跨帧漂移失败；
- T3 三张 accepted 照片在 5 attempts 内无法取得；
- 任一 diagnostic、BUSY、claim、ARM、EXECUTE 或 driver fault；
- action 报告出现 retry/recovery/autochain 或可见刷新数不等于 1；
- 大面积残留、固定条纹、异常中心缝或白恢复异常。
- W4 post-white 的 `full_screen_white_gate.passed` 不是 true 或 classification 不是 PASS，且没有
  操作者明确 clean-white 确认。

relay receipt 只证明 commanded/query 状态，不证明驱动板负载侧真实电压或电流。

## 6. 预期产物

- 1 张 accepted W3 white；
- 3 张 accepted T3 atlas 与一个四帧 bundle；
- 64 格 camera-only 报告和 `HUMAN_CAMERA_SCREEN_PASS/REVIEW/FAIL`；
- 若要回答 profile-vs-side：一份真实 T3 human seed、sealed AC observation 和 CA-vs-AC human
  screening comparison；没有这三项时主问题明确保持 pending；
- W4 post-white 为 PASS 时：1 张 accepted 照片与独立 white seal；若两次相机门均未 PASS 而
  采用人工 clean-white fallback，则只记录人工确认和两份 rejected 结果，不虚构 seal；
- T3、W4 各一份 action evidence 和最终 relay OFF receipts；
- 更新 `STATUS_HANDOFF.md`、总测试记录和 GitHub 阶段提交。

正常终态：`W4 action complete / post-white camera PASS 或人工明确 clean-white / relay commanded
OFF / no pending automatic action`。

## 7. 预计现场用时与人工介入点

在相机位置和照明一次通过的情况下，完整流程预计约 15–25 分钟：取景及 W3 白参考约
3–5 分钟，T3 写入／诊断／刷新约 3–6 分钟，三帧封存约 3–6 分钟，W4 写入／白恢复及末端
白图约 4–8 分钟。具体时间以 BUSY 和冻结 runner 的终态为准，不能用固定 sleep 提前判定完成。

正常情况下操作者先完成相机物理对准和照明。机器可自动完成稳定性和瑕疵粗筛；若只想安全
留档并恢复白屏，可不逐格命名。若本次就要回答 profile-vs-side，则需要一次人工观察：左右各
code0..7 共 16 个词，并确认每 code 四副本稳定。出现 REVIEW、暖色歧义或末端白异常时也会暂停。

## 8. 离线实现与封存结果

本轮从操作者离场后的全部实现、格式化、单元测试和计划封存均为离线操作；没有新增相机、
relay、COM、ESP32 网络、flash、reset 或 visible refresh。最终文件为：

- T3 两阶段 capture pack：`86010 bytes / SHA-256
  4b8de02588c4fbf4f73914129118f019080d6231347b97831fe9df9f3f91d6ca`；
- W4 post-white 两阶段 wrapper：`70023 bytes / SHA-256
  c2c9c5c8cb11867d04d98d51849a080163a379354fdb3c510fb11a8cc2af9024`；
- 14 步 daylight plan source：`33170 bytes / SHA-256
  c3582a7f7d9db5a409c62460fe0f417a990e6af471f24e9252c058c3d944245b`；
- camera analyzer：`72447 bytes / SHA-256
  1a75d63fea7a3d32adb431a8083c58b3d1f0e3ccb16b12fddb8b9c8b78d2a40c`；
- O_EXCL V3 plan：
  `.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V3.json`，
  `36734 bytes / SHA-256 4c3c1d2ff056a28506fd335ee9576167e7b627d679b2c03d4c854a2b9f95a212`，
  canonical integrity=`88510a3090d62dd2950fca0c0768d28001c5e5bf957ac97ec01525f52b04bed7`。

旧 V1/V2 继续作为历史保留且不覆盖；V2 已不能通过当前 deterministic rebuild，后续只使用 V3。
联合离线回归 `174 passed / 696.69 s`；格式化后又复验 plan=`9 passed / 90.75 s`、W4 wrapper=
`17 passed / 244.27 s`。六个相关源码／测试文件 `ruff format --check`、Ruff 和三份主工具
`py_compile` 均 PASS。
