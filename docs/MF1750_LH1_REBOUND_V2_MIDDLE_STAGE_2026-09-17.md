# LH1 V2：SOURCE 复核后的一次 MIDDLE 测试

本页冻结本批范围；实时状态以 `STATUS_HANDOFF.md` 顶部和本次原始证据为准。
用户“目前是白色，重新刷入”“继续”的操作意图延续到一次新 MIDDLE 阶段；
已有继电器/真屏授权有效。现场证据未满足时，不创建可执行 release。

## 已核实的起点

- SOURCE ordinal 1 是全屏 C7、active/active profile 的基线。它没有输出明度梯度；
  看见白色不能据此判明度算法失败，也不要求仅因白色而重新刷白。
- 原始执行器发生过早查询超时。严格离线终态复核通过，原 transport FAIL_STOP 保留。
  设备 SOURCE 已消耗、cursor=2；当时没有创建宿主永久 claim，不补造过去的 claim。
- 本次重新枚举和只读四 GET 确认 boot `7274e005c8833ca1` 仍在、READY/cursor2、
  driver 累计1。继电器独立查询 OFF。这些是带时刻的观察，不能无限期继承。
- 不重刷当前应用。app-only 重启会破坏当前同 boot 链；若 boot 已变，停止续链。

## 固定动作

| 项目 | 本批值 |
|---|---|
| package | `.test-output/offline/LH1_REBOUND_20260916_V2_R1` |
| contract | `021c35abd47f6caa52b11cec98b73a79f11c585bdbc1ed976c2dde868bc5259e` |
| BIN | `9fba6008358e5be1c766edf18fc362caae3bb33554550b2a03147d2d9efe7614` |
| ELF | `0ce109accf39ccb27035a2a5dd7db0a07c579f3c522b4266c0b9b548ffb88898` |
| MIDDLE action / ordinal | `f43b48e9dbc73b30e22d228a39d0f941960ade60e515050c9561ff623a7a4042` / 2 |
| frame | `297b30361ab0afa88bc47f8b5acf3835974610fb39aee2efaba3b6d9e9b610bd` |
| profile | 两个控制器均为合同内完整 commented tuple；不修改任何字节 |
| 源态 → 目标态 | `LH1_SOURCE` → `LH1_MIDDLE`，位置平衡 M0…M7 矩阵 |
| 设备 NVS | `lh1reb_v2 / cur_lh1r / boot_lh1r`，旧命名空间保留 |
| 链 run_id | `LH1_REBOUND_V2_SOURCE_20260916`；固件要求阶段间保持相同 |
| 本次证据 run_id | `LH1_REBOUND_CONTINUE_20260917_V1` |
| 次数 | 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh，结束即停 |

唯一宿主入口为 `tools/mf1750_lh1_rebound_v2_middle_once.py`。旧 SOURCE 执行器已封存并
禁用两个 mutation 入口。新宿主永久 claim 的路径由 contract+ordinal 派生，写在 ARM
之前；异常后不删除，不以换目录、换 boot 或换 runner 获得重试额度。

## 现场顺序和停止条件

1. 获取指定 `VID_32E4:PID_4801` 当前源态原图、sidecar、完整四边观察。
   09-17 首张照片模糊遮挡；调整后第二张主体可见，但底边中央仍被支架遮住，原图保留。
   这两张不能冒称通过完整四边审查。人工“白色”原文与照片分别记录。
2. 用当次枚举唯一 COM/relay 身份和当次邻居候选建立 exact IPv4↔MAC，不写死旧端口。
   维持原 MCU boot；源态 report 必须仍是 exact SOURCE COMPLETE/cursor2/累计driver1。
3. relay ON 一次并独立查询，fresh 四 GET 要求同 boot、READY、raw BUSY=1。
   电气仍按用户指令仅记录，`electrical_state_proven=false` 不改成实测通过。
4. 结构化新阶段 review 绑定 SOURCE 原始报告、有效光学 review、本次 action、boot，
   摘要必须不同于白源摘要。不得用裸照片哈希或再次使用白源摘要代替阶段 review。
5. 校验固件、帧、源码依赖、native 报告、release 和 freshness，永久 claim 后仅发一次
   ARM、一次 EXECUTE。任何 ACK/身份/HTTP 异常立即 STOP，不重发。
6. EXECUTE 后等待65秒再首次 GET。等待拆成30+30+5秒，仅为宿主时序；不是波形参数。
   最多30次只读状态轮询、间隔2秒，单个请求65秒超时，不自动网络重试。
7. 正常终态必须同 boot、cursor3、累计 ARM/EXECUTE/driver 各2、本action driver1，
   CS1/CS2 FNV、profile、BUSY、safe_finish 和GPIO全部通过。
   正常完成和收尾条件通过后才控制 relay OFF 并独立查询。
   BUSY或终态不明时不盲目断电、复位、刷写或刷白。
8. 保存原始HTTP、BUSY阶段报告、照片和人工观察后停止。没有自动 TARGET ordinal3。

旧 P2 白、LH1 SOURCE R5 白和旧 FAULT770 R4 白的8个BIN/ELF已核对匹配封印，但它们
不接纳当前V2 MIDDLE源态。它们仅列为历史材料，不能充当可执行恢复方案。
如需恢复，必须另建与实际终态/故障绑定的独立 successor 并单独放行；本runner没有恢复入口。

## 光学和资格边界

128个逻辑ROI沿用package的 `observations.blank.json`：CS1/CS2分别、每配方TL/TR/BL/BR
四位置。图像坐标和透视映射必须由本次实际机位绑定；相机左右不擅自等同CS1/CS2。
同态定量分析至少10张照片/ROI，中央60%测量区域；缺少有效覆盖或噪声证据只作诊断。

相机请求 MJPG 4000×3000/15fps、focus79、exposure-6、WB4600，记录实际读回。
RAW、ISO和硬件触发按后端能力写false；温度、controller revision未测写null。
电源模块显示的温度不是panel温度。波形内部phase全部写OPAQUE。

阈值保持 `MF1750_LIGHTNESS_TEST_V1_20260911`：彩度C*>8；同色相链Δh≤5°、
ΔL*≥2和ΔE00≥3；位置门P95 |ΔL*|≤3、ΔE76≤5；噪声门由N≥10的MAD/CI95决定。
这些是实验离线筛选标准，不是厂商规格，也不是固件准入门。ΔE76与ΔE00分开使用。
当前图像只支持camera-relative Lab；不声称经过标定。

MIDDLE出现多种颜色仅证明中间配方矩阵形成。要筛同色相明度，仍须独立判读后释放
TARGET，把不同历史映射到同一目标码，再比较四位置和双controller。
以后依次进行HOLD、独立fresh重建、保持和匹配，才可能获得资格；本批qualified保持0。
白恢复清除候选是正常恢复，不能据此判瞬态。

## 本次证据入口

`.test-output/hardware/LH1_REBOUND_CONTINUE_20260917_V1/`：
`offline/source-reconciliation-v2.json`、`offline/white-applicability.json`、
`readonly/result.json`、原始照片/sidecar、`offline/middle-release-pending.json`。
pending release的 `live_release=false`，不能用于执行。

native R1编译失败是桌面fixture两份Arduino定义冲突；R2识别出version/manifest无boot；
失败日志保留。修正后的R5实际generated main的8份响应通过当前host校验，仍为桌面合成驱动，
不等于真实BUSY/光学证据。宿主负例和一次性事务测试另存日志。
