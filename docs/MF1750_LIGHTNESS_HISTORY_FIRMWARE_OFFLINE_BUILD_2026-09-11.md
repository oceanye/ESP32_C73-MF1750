# MF1750 明度历史测试固件：离线封印

更新时间：2026-09-11 06:38 +08:00。此记录只覆盖算法、固件编译和桌面证据，不代表已刷写或已刷新真屏。

## 已实现

`host/static_photo/lightness_history.py` 生成固定 1024×600、4bpp 帧：`SOURCE(active/C7) → MIDDLE(commented/M0…M7) → TARGET(active/T3 或 T7)`。16 条配方在 CS1、CS2 各有四个物理象限副本，共 128 个 controller-local 测量槽。每一步是一个完整全屏帧和一次独立 visible refresh；`[3, 5, 10]` 只表示待筛的等级数，不是重复次数。帧生成不含抖动、邻像素混色或白色/重复动作。

`tools/mf1750_lightness_history_firmware.py` 从哈希固定的 V3 主固件和驱动模板生成独立 PlatformIO 工程。它只允许三个 ordinal，启动不刷新；每步必须 bodyless ARM→EXECUTE，EXECUTE 先持久化 CONSUMED，再排队一个 driver 调用。游标、boot nonce、run_id、source-review、prior-review 和 action/profile/frame/controller-frame 哈希均绑定；重复、跳号、旧 boot、BUSY 非空闲、游标改变、驱动诊断不完整、白源缺失或 NVS 写入失败会停止并锁定。source white 只读检查独立 successor 的 `p2catwsv1/used_p2cw1=2`，该值不是光学或电气证据。内部波形 phase 继续写 `OPAQUE`。

每个 action 的 CS1/CS2 使用同一完整 tuple：ordinal 1/3 为 active/active（AA），ordinal 2 为 commented/commented（CC）。固件没有复用旧 V3 的 CS1 active、CS2 commented 非对称 dispatch，也没有把公开资料中的未证实电压、PLL 或 R20 字段改写进控制器。

## 封印产物

- 算法：[lightness_history.py](../host/static_photo/lightness_history.py)
- 生成器：[mf1750_lightness_history_firmware.py](../tools/mf1750_lightness_history_firmware.py)
- 最终包：[LH1_20260911_R3](../.test-output/offline/LH1_20260911_R3)
- 合同 ID：`b63695f21ca56f3dbb45998ad3c88c790b5eed121513fa188c26b40a237990ac`
- BIN：`build/lh1/firmware.bin`，SHA-256 `369c952a970fc1d9313602ffb4dd10ceac6534a486c399bf30bf40d2b0de00d1`
- ELF：`build/lh1/firmware.elf`，SHA-256 `84f4191fcb212ef4de2c1e14571f7d6b96f91429e81d481640fc5f3e3eeceb4a`
- 编译日志和 `build-report.json` 已绑定 manifest；输入模板变化会使包复核失败。
- [native-audit.json](../.test-output/offline/LH1_NATIVE_20260911_R3/native-audit.json)，SHA-256 `38799db0552d5ae8c48cbe75f1c589a7e94e203115843dd1704506b5f04bd97c`。

## 验证结果

Python 回归 `49 passed`（光学判读、合同、ROI/象限、身份绑定和不可覆盖封印）。C++ 桌面双测试通过 29 个状态机场景：正常三步、只读 route、重启、重复 ARM/EXECUTE、评审变更、白源丢失、游标篡改、BUSY、NVS/驱动故障和未知 mutation。三张 C++ 帧与 Python 帧逐字节相同；30 条 global/profile/controller 写入记录与 active/commented 合同哈希相同。所有这些均为 offline，设备访问和 visible refresh 均为 0。

## 现场边界

当前屏幕仍按最后现场记录为 2×4×8 彩色，relay 最后 OFF，`electrical_state_proven=false`，现场 NO-GO。此包 `live_ready=false`、`qualified_count=0`。它不能证明明度等级、稳定保持、fresh-white 重建、位置可重复性或双 controller 光学匹配。

下一次唯一入口：先完成当前条件下独立 P2-C white successor 的实际恢复并取得 fresh clean-white 与电气证据；然后重新枚举并建立当次 IPv4↔MAC、COM 和 boot 身份，刷写本包后重新取得同 boot 的 J2-OFF diagnostic。取得明确现场放行后，最多执行 ordinal 1 的 ARM/EXECUTE/driver/visible refresh，立即停住判读；不得自动执行 ordinal 2、重试或白恢复。
