# LH1 V2：MIDDLE 复核后的一次 TARGET 测试

本页冻结本批范围；实时状态以 `STATUS_HANDOFF.md` 顶部和本次原始证据为准。
用户“持续推进测试”“每种颜色是否可调出多级明度”的操作意图延续到一次 TARGET 阶段；
既有真屏/继电器授权有效。现场证据未满足时，不创建可执行 release。

## 已核实的起点

- SOURCE ordinal1（全屏 C7 基线）与 MIDDLE ordinal2（位置平衡 M0…M7 矩阵）均已 COMPLETE：
  同 boot=`7274e005c8833ca1`、cursor=3、next_ordinal=3、累计 driver=2。MIDDLE 永久 claim
  （contract+ordinal2）已消耗，禁止重放；SOURCE 不得重放。
- MIDDLE 协议终态经宿主严格复核 PASS；离线 128 ROI 分析 V1/V2 完成：
  CS1 得 2 级同色相链（M0→M2，L*≈29.7→40.2）；CS2 右边缘受阴影限制。
  右半质量已经用户人工判定与左侧一致，几何质量门按记录放宽（光学阈值未动）。
- 用户确认左右两半物理排布差 180°，与解出的 identity/identity 图像映射自洽。
- 不重刷当前应用。app-only 重启会破坏当前同 boot 链；若 boot 已变，停止续链。

## 固定动作

| 项目 | 本批值 |
|---|---|
| package | `.test-output/offline/LH1_REBOUND_20260916_V2_R1` |
| contract | `021c35abd47f6caa52b11cec98b73a79f11c585bdbc1ed976c2dde868bc5259e` |
| BIN | `9fba6008358e5be1c766edf18fc362caae3bb33554550b2a03147d2d9efe7614` |
| ELF | `0ce109accf39ccb27035a2a5dd7db0a07c579f3c522b4266c0b9b548ffb88898` |
| TARGET action / ordinal | `31489f8f4696fbbd386b7e1de53326cde614c9c644b962d0b0b9645da6105632` / 3 |
| frame sha256 | `82f40036c115b3…`（以 contract.json 为准） |
| frame histogram | `[0,0,0,133120,0,0,0,481280]`：T3 组 64 格 code3 可见；T7 组 code7=白不可见 |
| profile | 两个控制器均为合同内完整 active tuple；不修改任何字节 |
| 源态 → 目标态 | `LH1_MIDDLE` → `LH1_TARGET`，不同历史映射到同一目标码 |
| 设备 NVS | `lh1reb_v2 / cur_lh1r / boot_lh1r`，旧命名空间保留 |
| 链 run_id | `LH1_REBOUND_V2_SOURCE_20260916`；固件要求阶段间保持相同 |
| 本次证据 run_id | `LH1_REBOUND_TARGET_20260917_V1` |
| 次数 | 1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh，结束即停 |

唯一宿主入口为 `tools/mf1750_lh1_rebound_v2_target_once.py`。新宿主永久 claim 的路径由
contract+ordinal3 派生，写在 ARM 之前；异常后不删除，不以换目录、换 boot 或换 runner
获得重试额度。合同只有 3 个 action，TARGET 后 campaign_complete=true，没有下一个 action。

## 现场顺序和停止条件

1. 获取指定 `VID_32E4:PID_4801` 当前 retained MIDDLE 矩阵原图、sidecar、完整四边观察。
   继电器保持 OFF、不刷新。该照片构成 fresh MIDDLE 矩阵光学 review。
2. 用当次枚举唯一 COM/relay 身份和当次邻居候选建立 exact IPv4↔MAC，不写死旧端口。
   维持原 MCU boot；fresh 只读四 GET 必须仍是同 boot、READY、cursor3、累计 driver2。
3. relay ON 一次并独立查询。电气仍按用户指令仅记录，`electrical_state_proven=false`
   不改成实测通过。
4. 结构化新阶段 review 绑定 MIDDLE 终态 result、在盘 MIDDLE 永久 claim、有效 MIDDLE
   矩阵光学 review 和 MIDDLE 分析 review（V2），摘要必须不同于白源摘要和 MIDDLE 摘要。
5. 校验固件、帧、源码依赖、native 报告、release 和 freshness，永久 claim 后仅发一次
   ARM、一次 EXECUTE。任何 ACK/身份/HTTP 异常立即 STOP，不重发。
6. EXECUTE 后等待65秒再首次 GET。等待拆成30+30+5秒，仅为宿主时序；不是波形参数。
   最多30次只读状态轮询、间隔2秒，单个请求65秒超时，不自动网络重试。
7. 正常终态必须同 boot、state=complete、cursor4、next_ordinal4、累计 ARM/EXECUTE/driver
   各3、本action driver1、campaign_complete=true，CS1/CS2 FNV、profile、BUSY、safe_finish
   和GPIO全部通过。正常完成和收尾条件通过后才控制 relay OFF 并独立查询。
   BUSY或终态不明时不盲目断电、复位、刷写或刷白。
8. 保存原始HTTP、BUSY阶段报告、照片和人工观察后停止。合同无后续 action；不得白恢复。

旧 P2 白、LH1 SOURCE R5 白和旧 FAULT770 R4 白的8个BIN/ELF已核对匹配封印（ordinal3
复审 `offline/white-applicability.json`），但它们不接纳当前V2 TARGET终态。它们仅列为
历史材料，不能充当可执行恢复方案。如需恢复，必须另建与实际终态/故障绑定的独立
successor 并单独放行；本runner没有恢复入口。

## 光学和资格边界

128个逻辑ROI沿用package的 `observations.blank.json`：CS1/CS2分别、每配方TL/TR/BL/BR
四位置。TARGET 后仅 T3 组64格（code3）有色可见，T7 组落在白底不可见；可见性差异本身
是合同设计，不是缺陷。TARGET 的意义是把不同 MIDDLE 历史收敛到同一目标码，用于比较
四位置/双 controller 收敛一致性；必须与 SOURCE/MIDDLE 合链判读。

相机请求 MJPG 4000×3000/15fps、focus79、exposure-6、WB4600，记录实际读回。
RAW、ISO和硬件触发按后端能力写false；温度、controller revision未测写null。
电源模块显示的温度不是panel温度。波形内部phase全部写OPAQUE。

阈值保持 `MF1750_LIGHTNESS_TEST_V1_20260911`：彩度C*>8；同色相链Δh≤5°、
ΔL*≥2和ΔE00≥3；位置门P95 |ΔL*|≤3、ΔE76≤5；噪声门由N≥10的MAD/CI95决定。
几何质量门按用户2026-09-17豁免维持分析V2口径（scatter≤15px）；光学阈值未动。
这些是实验离线筛选标准，不是厂商规格，也不是固件准入门。ΔE76与ΔE00分开使用。
当前图像只支持camera-relative Lab；不声称经过标定。

TARGET 收敛一致只证明历史可收敛，不单独授予明度等级。要筛同色相明度链，仍须
SOURCE/MIDDLE/TARGET 合链判读后依次进行HOLD、独立fresh重建、保持和双controller匹配，
才可能获得资格；本批qualified保持0。白恢复清除候选是正常恢复，不能据此判瞬态。

## 本次证据入口

`.test-output/hardware/LH1_REBOUND_TARGET_20260917_V1/`：
`offline/white-applicability.json`（ordinal3 材料复审，PASS_HASH_CHECK_ONLY）。

native R1（`.test-output/offline/LH1_REBOUND_V2_TARGET_NATIVE_20260917_R1/`）实际
generated main 的8份响应通过当前host校验，仍为桌面合成驱动，不等于真实BUSY/光学证据。
宿主负例和一次性事务测试 `tests/test_mf1750_lh1_rebound_v2_target_once.py` 23 passed。
