# MF1750 T3 相机辅助与 W4 白收容执行卡

> **2026-08-31 13:38 状态更新：** 本 full-panel V3 卡作为历史冻结路线保留。操作者已改选
> 固定机位的双侧局部 `3x8` 筛查；T3 V1 app 已写入且 verify PASS，但首个 J2-OFF
> `/version` GET 连接被拒绝，以 `0 POST / 0 claim / 0 refresh` 停止，relay 复核 OFF。
> 当前执行入口改为
> `docs/MF1750_RAW_P16_CROSSOVER_T3_PARTIAL_DUAL_3X8_RECOVERY_PLAN_2026-08-31.md`；不得重放本卡的
> V1 diagnostic/action。

状态：`OFFLINE READY / NOT EXECUTED`
V3 离线冻结：`2026-08-31 09:00 +08:00`

## 1. 目标、非目标与当前起点

下一次有人值守时只允许两次可见刷新：一次 T3 `AC` profile-swap atlas，一次专属 W4
factory-OTP white。48MP 相机负责整屏几何、四副本一致性、三帧稳定性和明显边缘／条纹／残留
粗筛，不负责绝对颜色、正式色数、灰阶标定或调色板资格。

当前只继承 2026-08-31 06:03 的现场证据：relay commanded `OFF`，但负载侧电气状态未证明；
屏幕按双稳态保留 W3 干净白；正式 W3 相机 attempt=0；T3/W4 未安装、未 claim、未执行。
06:01 setup-only 图未拍到屏且欠曝，只是历史失败预检，不能作角点或白参考。

从操作者本次离场后的 V3 修订起，全部代码、测试和封存均为离线操作；没有新增相机、relay、
COM、ESP32 网络、flash、reset 或 display refresh。

## 2. 精确绑定

| 项目 | contract | action | BIN SHA-256 |
|---|---|---|---|
| T3 atlas | `714ddf2e...78c8` | `db009936...6e9e` | `05c00d71...5760` |
| W4 white | `7edf2e19...7d52` | `e621ea9a...c55b` | `9f3ab672...bf7` |

W4 只接受上述 T3 的 campaign/contract/descriptor/action 四元组。两者均是 fresh 一次性动作，
`retry=0 / recovery=0 / autochain=0`。

相机只允许：

```text
48MP USB Camera / VID_32E4:PID_4801
DirectShow exact-path 双重枚举
MJPG 4000x3000 @ 15 fps
autofocus=0, focus=79
auto exposure=0.25, exposure=-6
auto white balance=0, WB=4600
warmup=8
```

明确排除双目 `VID_1BCF:PID_0B15`；OpenCV index 不是身份。白参考、三张 atlas 与末端白图必须
保持同一 exact camera path、mount、requested/effective settings 和 4000x3000 geometry。

## 3. 两阶段照片状态机

每张正式照片必须按以下顺序：

```text
acquire
  -> 开相机前 O_EXCL 永久 claim
  -> 不接收 corners
  -> 只取得一张并封存 JPEG/sidecar/action snapshot/哈希

查看这张 exact 原始 JPEG，取得它自己的 TL/TR/BR/BL

admit
  -> 不打开相机
  -> 解析 corners 前 O_EXCL admission claim
  -> 几何与像素门
  -> terminal ACCEPTED 或 REJECTED
```

成功 acquisition 未取得 terminal admit 前，禁止下一次 acquire。角点错误或 gate failure 会永久
消耗该 admission，不能换角重审。旧 `capture` 命令已 fail-closed 禁用。setup-only 有独立最多
2 次预算，`formal_evidence=false`，不能进入 bundle 或提供正式角点。

## 4. 下一次有人值守的固定流程

### G0：物理取景门

1. 操作者把 48MP 相机对准屏幕，使整个活动区和四角完整入镜；补光均匀、避免反光。
2. 确认继承现场仍安全，执行 fresh exact-bound relay query；必须 commanded `OFF`。
3. 固定 `$mount`，用 `setup-view` 最多两次。未完整入镜或照度不足就保持 OFF 并停止。

```powershell
$camRoot = '.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_CAMERA_DAYLIGHT_V1'
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py setup-view `
  --output-root $camRoot --action-result $w3Action --mount-id $mount
```

### G1：正式 W3 白参考

```powershell
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py acquire `
  --slot w3-white-reference --output-root $camRoot --action-result $w3Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py admit `
  --slot w3-white-reference --attempt <CLI返回值> --output-root $camRoot `
  --panel-corners '<TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy>'
```

W3 最多 2 次 formal attempts；任何第二次都必须人工明确继续，不自动 retry。64 个有效位置均须
`L* >= 25`。

### G2：唯一 T3 atlas

1. relay/J2 commanded OFF 下以单启动 helper 写入并独立 verify T3：
   `write --before default_reset --after no_reset`，随后
   `verify --before no_reset --after hard_reset`。应用只启动一次，额外／人工 reset=0。
2. fresh 诊断固定 `4 GET / 0 POST / 0 claim / 0 refresh`。
3. relay ON 后冻结 runner 在 exact 4 GET 之后、任何 claim/ARM/POST 之前检查 raw `BUSY=1`。
   `BUSY=0` 在 mutation 前失败；没有 BUSY 后独立暂停子命令。
4. 只允许 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`。无论 complete 或 fault，随后
   保护性 relay OFF；fault 不重试。

### G3：三张 T3 与粗筛

在 atlas 双稳态保留且 relay OFF 时，逐张执行：

```powershell
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py acquire `
  --slot t3-retained-atlas --output-root $camRoot --action-result $t3Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py admit `
  --slot t3-retained-atlas --attempt <CLI返回值> --output-root $camRoot `
  --panel-corners '<本张JPEG自己的TL/TR/BR/BL>'
```

取得三张 accepted atlas 的总预算为 5 attempts；每张必须 admit 终态后再拍下一张。四帧通过
deep replay 后：

```powershell
python -B tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py seal `
  --output-root $camRoot
```

相机粗门检查 64 格、每 controller/code 四副本、三帧、controls 2/3/5、底边、条纹、残留、
接缝、裁切和曝光。组内 `DeltaE00 <=8` PASS、`(8,12]` REVIEW、`>12` FAIL；三帧中心
`DeltaE76 <=3` PASS、`(3,6]` REVIEW、`>6` FAIL；对应角漂移不得超过 30 px。

相机单独只能赚取稳定性和质量结论。没有真实 T3 human seed 时最高为
`HUMAN_CAMERA_SCREEN_REVIEW`，profile-vs-side=`NOT_EARNED`。若要在本轮回答首要问题，需填写
左右各 code0..7 共 16 个真实词、确认四副本稳定，再与已绑定的 T2/CA 人工基线比较。若暂不
填写，仍可继续 W4 安全收容，主问题保持 pending。

### G4：独立 W4 白收容

1. 只有四帧 T3 bundle 已 seal 才安装 W4；相机颜色分类本身不阻塞安全刷白。
2. relay/J2 commanded OFF 下沿用 G2 同一 app-only reset 序列写入并 verify W4；fresh 4 GET。
3. relay ON 后 runner 在 claim/POST 前检查 W4 raw `BUSY=1`，只执行一次 factory-OTP white；
   随后 relay OFF。
4. 使用 W4 专属 wrapper，最多 2 attempts：

```powershell
$w4CamRoot = '.test-output/hardware/MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_CAMERA_DAYLIGHT_V1'
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py acquire `
  --output-root $w4CamRoot --action-result $w4Action --mount-id $mount
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py admit `
  --output-root $w4CamRoot --attempt <CLI返回值> `
  --panel-corners '<本张JPEG自己的TL/TR/BR/BL>'
python -B tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py seal `
  --output-root $w4CamRoot
```

仅当 `full_screen_white_gate.passed=true` 且 classification=`PASS` 时才 ACCEPTED 并可 seal。
`REVIEW/FAIL` 保留分类但 terminal REJECTED，同一 attempt 不可重 admit；剩余预算内可人工明确
取得 attempt 2。两次都未 PASS 时保持 OFF，请操作者确认白屏；人工 fallback 不生成 camera seal。

### G5：离线报告

相机报告可在 W4 后生成。若已有真实 T3 seed，则封存 AC human observation 并与 exact T2/CA
reference 比较；否则只输出稳定性／画面质量报告，profile-vs-side 保持 pending。任何结果都不
自动授权下一轮色彩动作，`qualified_colour_count=0`。

## 5. 预期目标与分支

- `PROFILE_FOLLOWING_CANDIDATE`：A 外观跟随到 CS1、C 外观跟随到 CS2，四副本和时间稳定；
- `PHYSICAL_SIDE_FOLLOWING`：外观仍固定于 CS1/CS2，优先调查 controller、数据路径和面板差异；
- `UNSTABLE_OR_CONFOUNDED`：四副本、三帧、光照或边缘门失败，停止颜色命名并修复重复性；
- 未提供 T3 human seed：只完成相机稳定性／质量粗筛，主分支明确 `NOT_EARNED`。

若获得 profile-following 候选，下一阶段才按 code5、7、3、6、4 的信息增益顺序做有效色相、
同色明度和局部 HOLD 复核。不能由本轮直接推断 256 色、灰阶或新增合格颜色数量。

## 6. 停止条件与正常终态

任一情况立即保持或切回 relay OFF，并停止自动流程：

- 相机 exact 身份、固定设置、mount、尺寸或当前照片角点不一致；
- T3 三张 accepted 照片在 5 attempts 内无法取得；
- 任一 diagnostic、BUSY、claim、ARM、EXECUTE 或 driver fault；
- action 不是恰好一次刷新，或出现 retry/recovery/autochain；
- 大面积残留、固定横纵线、异常接缝、底边异常或白恢复异常；
- W4 post-white 未同时通过 full-white hard gate 与 PASS，且没有操作者明确 clean-white 确认。

正常终态：`T3 evidence sealed / W4 action complete / post-white camera PASS 或人工明确 clean-white /
relay commanded OFF / no pending automatic action`。relay receipt 不证明驱动板负载侧真实电压或电流。

## 7. 离线产物与验证

- T3 capture pack：`86010 bytes / 4b8de02588c4fbf4f73914129118f019080d6231347b97831fe9df9f3f91d6ca`；
- W4 wrapper：`70023 bytes / c2c9c5c8cb11867d04d98d51849a080163a379354fdb3c510fb11a8cc2af9024`；
- daylight plan source：`33170 bytes / c3582a7f7d9db5a409c62460fe0f417a990e6af471f24e9252c058c3d944245b`；
- camera analyzer：`72447 bytes / 1a75d63fea7a3d32adb431a8083c58b3d1f0e3ccb16b12fddb8b9c8b78d2a40c`；
- current V3：
  `.test-output/offline/MF1750_RAW_P16_CROSSOVER_T3_CAMERA_W4_DAYLIGHT_PLAN_20260831_V3.json`，
  `36734 bytes / 4c3c1d2ff056a28506fd335ee9576167e7b627d679b2c03d4c854a2b9f95a212`，
  canonical integrity=`88510a3090d62dd2950fca0c0768d28001c5e5bf957ac97ec01525f52b04bed7`。

V1/V2 保留为历史，V2 已被 V3 替代且不能通过当前 deterministic rebuild。联合离线回归
`174 passed / 696.69 s`；格式化后 plan=`9 passed`、W4=`17 passed`；Ruff、format check 和
`py_compile` PASS。所有测试使用 fake/synthetic evidence，没有访问硬件。
