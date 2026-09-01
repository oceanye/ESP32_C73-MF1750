# MF1750 256 色／10 阶明度目标与调整后的搜索路线

日期：`2026-09-01`

状态：`OFFLINE TARGET/PLAN ONLY`

现场边界：本轮没有访问相机、ESP32、COM、设备网络、继电器或面板；最后记录仍为
`relay/J2 commanded OFF`，负载侧电气状态没有独立证明。

## 1. 目标的准确含义

目标可以写成：

> 最终建立 **256 个可寻址、可复现、可局部共存的单像素逻辑颜色槽**；主要彩色色相／彩度轨
> 各争取 **10 个肉眼与测量均可分的明度层级**。

这不是 `256 色 × 10 阶 = 2560`，也不表示面板现在已经具备 256 色或 10 阶明度。建议的目标
网格为：

```text
16 个中性色槽
+ 12 个彩色色相族 × 2 条彩度/轻微色相子轨 × 10 个明度档
= 256 个总槽位
```

十二个彩色色相族沿用照片目录：`R / RO / O / Y / YG / G / T / C / B / I / V / M`。
这个网格只是工程目标，不是物理能力声明；某一高彩度色相若没有足够的 L* 范围，不能降低
区分门槛硬凑 10 阶，缺口应由另一条彩度／子色相轨补位，或诚实停在 3、5、8 阶。

当前资格真值不变：

```text
qualified new colours = 0
qualified neutral gray levels = 0
qualified lightness levels = 0
```

已多次肉眼区分的七个基础视觉组是搜索种子，不等于已完成完整仪器资格化的 7 个最终槽位。

## 2. 为什么原方法降级

`STABLE_CODE0_LUMA_LATIN_V3` 的 L3 一次性历史信号在 CS2 的中值 L* 跨度为 `7.059`；
同一 target 原位重复后的 L4 只剩 `2.157`，保留率约 `30.56%`。因此：

- `source → middle → target → identical target repeat` 不能作为主明度发生器；
- L3 的一次性差异不能直接计为稳定明度；
- 后续若使用历史配方，必须采用“构色后局部 HOLD → 独立原厂白 → fresh reconstruction”，
  不能再用原位 repeat 代替复现。

## 3. 调整后的方法优先级

### P1：已知兼容完整 profile 的直接 endpoint 三阶复核

现有 T3 partial-camera 报告中，`CS1 + active complete profile` 的三个单码终态出现一条值得
优先复核的暖色候选链：

| code | camera-relative L* | hue angle（约） |
|---:|---:|---:|
| C0 | 31.17 | 13.2° |
| C6 | 50.53 | 15.4° |
| C1 | 68.25 | 23.0° |

相邻 L* 差约为 `19.37 / 17.72`，总色相角跨度约 `9.8°`。这些值来自相机相对白参考和 partial
ROI，只能叫 `THREE_LEVEL_ENDPOINT_CANDIDATE`；它们尚未通过全屏、双 controller、fresh
reconstruction、HOLD 或正式色卡门。

最小复核矩阵对每个 controller 使用 `4×8` 位置平衡布局：

```text
0 1 2 3 4 5 6 7
4 5 6 7 0 1 2 3
1 2 3 4 5 6 7 0
5 6 7 0 1 2 3 4
```

两侧必须装载各自字节完整、已知兼容的 profile tuple；CS1、CS2 分开分析，不跨侧平均。
首轮只判断 C0/C6/C1 在各自 controller 内是否形成纯色、净边、位置稳定的暗／中／亮三级。
不做原位 target repeat。命中后立即转入局部 HOLD 和独立白锚 fresh reconstruction；未命中则
转 P2。

### P2：两套完整已知 profile 的 endpoint 地图

从互相独立的 factory-OTP 白锚分别执行完整 A、C profile 的八码位置平衡 atlas：

```text
白锚 → A profile 8-code atlas → 独立白恢复
白锚 → C profile 8-code atlas → 独立白恢复
```

搜索空间为每 controller `2 profiles × 8 codes = 16` 个直接终态入口。只允许完整
`header + R20 + R21` tuple；不得混合 header/body、替换单 block 或插值 WF20/WF23。跨 profile
同码的大差异先记作调色盘 endpoint，只有色相近且 L* 单调的组合才进入明度族。

### P3：不修改 LUT 的完整刷新剂量阶梯

固定已验证完整 profile 和 source/target，用已经验证的 inclusive PTLW + HOLD 传输，让不同条带
接受不同次数的**完整、正常结束** target 刷新。先粗测 `1 / 2 / 4 / 7 / 10` 次；只有出现单调、
纯色、可重建的 L* 变化才细化成 10 阶。

该方法不截断 BUSY、不切断刷新、不猜 R20 字段；但上午 L3→L4 已说明部分状态会快速收敛，
因此它排在直接 endpoint 之后。完整 10 阶约需 source 1 次、逐层 target 最多 10 次、白恢复 1 次，
不能在未证明 3/5 阶单调前直接执行整套。

### P4：有界 R20 phase family（继续阻断）

当前资料尚未把 `8×11` record 可靠解释为时间相位，也没有证明 11 字节内哪个字段仅控制时长／
重复而不涉及极性、电平或电压。取得配对 loader 字段表、可信公开资料或总线证据之前，不生成
真屏 R20 明度枚举固件。

明确禁止：未知命令扫描、VCOM/PWR/PLL/高压 header 修改、WF20/WF23 任意拼接／插值、删减
11-byte GROUP 冒充相位、套用其他芯片 `0x32 LUT`、BUSY 中途断电或机械继电器截断。

## 4. 分阶段验收

不要把 256 直接作为下一轮上机承诺。发布台阶固定为：

1. `M0`：一个 controller-local 色相轨获得明显的 3 阶暗／中／亮；
2. `M1`：三级通过局部 HOLD、独立白锚重建和白恢复，并在另一 controller 得到光学匹配配方；
3. `M2`：同一轨扩为 5 阶，建立首个有限照片调色板；
4. `M3`：同一轨争取 10 阶；若物理跨度不足则冻结实际 5/8 阶；
5. `M4`：全屏匹配调色板依次扩为 `16 → 32 → 64 → 128 → 256` 个槽位；
6. `M5`：256-slot atlas／固定照片从 fresh white 起点完成三次重建、保持和白恢复后，才允许称
   “全屏 256 个可用单像素色”。

每个逻辑槽都必须分别保存 `R_CS1` 与 `R_CS2` 两套 recipe。两侧 recipe 可以不同，但必须有
显式的跨 controller 光学匹配证据。色数按匹配后的共同槽计数，不能把 CS1 和 CS2 相加，也不能
把同名 slot 的集合交集自动当成已经匹配。

空间抖动、网点、条纹和相邻像素混色永不增加单像素 256 色计数；它们以后只能作为已合格
palette 之上的渲染选项。

## 5. 下一真屏的最短目标

下一轮不追求十阶，也不继续大量新色枚举。先为 P1 建立 fresh one-shot 固件与独立 factory-OTP
white successor，只做一次位置平衡 endpoint atlas；先回答“暖色 C0/C6/C1 是否真有稳定三级”。
若通过，当轮下一功能门是 HOLD；若不通过，直接白恢复并转 P2。可靠性第三次重复与
`5/60/600 s` 长时保持继续后置，但不会因此提前授予正式资格。
