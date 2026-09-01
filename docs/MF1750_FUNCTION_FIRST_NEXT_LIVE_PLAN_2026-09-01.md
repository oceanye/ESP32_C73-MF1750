# MF1750 功能优先下一轮真屏计划（2026-09-01）

## 本轮只回答的功能问题

本轮不扩大色相枚举，不做空间抖动，不做 60 秒／10 分钟或多日可靠性。只回答：

1. 16 个位置平衡历史 recipe 中，是否有单像素中性灰或同色相明度分离；
2. 若有，这些候选在切换兼容 LUT、只刷新屏外探针时能否被局部 HOLD；
3. HOLD 后能否从独立 factory-OTP 白锚重新构色，得到相同的 controller-local 结果；
4. 通过者能否进入照片 palette 和 multi-LUT 调度器。

本轮命中明度机制后，优先把同一机制迁移到已有稳定基色，形成各基色的亮／中／暗入口；
不会立即扩大新色相枚举。第三次复现、60 秒／10 分钟及长时可靠性继续后置。

## 当前入口

- 面板：V3 独立 factory-OTP 白恢复后的 retained 白场；
- relay/J2：commanded OFF，`electrical_state_proven=false`；
- ESP32：保留 V3 white successor 固件；
- qualified 新色／灰阶／明度：全部为 0；
- 指定相机：只允许 `48MP USB Camera / VID_32E4:PID_4801`；
- 双目 `VID_1BCF:PID_0B15` 禁止用于本项目证据。

## A. 位置平衡明度机制

使用 fresh `LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3`，只执行核心动作：

该主固件及其独立 factory-OTP white successor 已完成 clean build、独立 audit、目标测试和
SHA-256 清单复核，当前只缺真屏动作证据；离线状态不授予任何灰阶或明度资格。

| 动作 | 内容 | 目的 |
|---:|---|---|
| G1 | active C7 source | 固定源态 |
| G2 | commented C0–C7 position-balanced middle | 形成 16 种历史 recipe |
| G3 | active C3/C7 mixed target | 形成待筛查终态 |

每个 controller 内每种 recipe 有 4 个位置副本，共 128 个格。G4 虽在冻结固件中保留为旧式
显式诊断，但本轮不执行；V3 L4 已证明原位 identical-target repeat 会压缩历史差异。

G3 后立即使用相同曝光／白平衡的 48MP 帧做 controller-local 粗筛。必须同时通过：

- 单格内部无条纹、网点或空间混色；
- 四边干净，尤其底边无黑线；
- 同 recipe 的 4 个位置副本稳定；
- controller 内达到中性灰或同色相 `Delta L*` 门；
- CS1/CS2 不合并、不互相充当副本。

专用离线分析器已经完成：它自动量取双侧 8×8、共 128 格，并对每侧 16 recipe 的 4 个位置
副本分别筛查。允许在固定机位下复用已封存 Latin V3 的 homography；若相机实例、后端、分辨率、
mount 或任一请求／实际设置不同则 fail closed，必须重新完成几何绑定。

若无候选：不执行 G4、不进入 HOLD，直接使用独立白 successor 收尾，再转向已知兼容 profile
端点或有界 R20 phase family。仍不扩大色相组合。

## B. 候选专用局部 HOLD

`POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1` 及其独立 factory-OTP white successor
已完成 clean build、独立 audit 与定向测试。H1/H2 探针已移到每个 controller 的上／下白带，
保留全部 128 个 G3 候选格；当前仍等待精确 G3 COMPLETE，故 live source gate 尚未开放。

若 G3 有候选：

1. 保留 G3 光学终态；
2. relay/J2 OFF；
3. app-only 换入 `POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1`；
4. 不重跑 G1–G3，不覆盖候选格；
5. H1 只刷新顶部探针，active/code5；
6. H2 只刷新底部探针，commented/code6，并保留顶部探针；
7. 分别拍摄 T0=G3、T1=H1、T2=H2。

H1/H2 均使用已经真屏通过的 clean transport：

```text
full code7 SRAM preload
-> one inclusive PTLW per controller
-> cropped uniform DTM
-> PON -> DRF 0x00 -> POF 0x00
```

禁止 post-PON PTLW、`0x86`、未知命令、刷新中断和自动串联。候选网格与上下探针严格不重叠。

HOLD 只在 T0/T1/T2 中候选格 controller-local 差异保持、H1 在 H2 后保持、探针四边干净时
通过。通过不自动授予颜色资格。

T0/T1/T2 离线比较器已经完成并通过定向测试。它冻结三份 action/descriptor/firmware 身份、
48MP 相机实例和设置、可见格集合与探针几何；只有同一 controller、同一 recipe 的四副本完整时
才给 REVIEW。探针不在画面内时 directional cross-LUT 固定为
`UNTESTED_PROBES_NOT_VISIBLE`，qualified 计数始终为 0。

## C. 从白锚重新构色

HOLD 通过后：

1. 执行独立 factory-OTP 白恢复；
2. 相机可见检查无明显旧格、色斑、粗大条纹或中心接缝；
3. J2 OFF，app-only 换入独立 `POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1`；它使用与
   A 的 G1–G3 逐字节相同的光学帧，但 campaign/contract/NVS/claim/action 身份全部新建；
4. 从 fresh 白锚只执行 reconstruction G1–G3；旧 F1 action 不得重放，也不得通过清空 NVS 复用；
5. 按相同 controller、recipe、位置比较第一次和第二次 construction；
6. 两次 fresh construction 均通过后，记录为 `REPRODUCIBLE_HELD_CANDIDATE`；
7. 使用 reconstruction 自己绑定的独立 factory-OTP white successor 收尾；
8. 第三次 fresh run、60 秒／10 分钟及长期保持后置。

独立 reconstruction 主固件与其 R3-only factory-OTP white successor 已完成 clean build、审计
和 SHA 清单封印：main contract=`5d76fda3bf199d29538ec0c6555db4a294b6b11ffb5805613805b4f759b7d132`、
BIN=`9b8493903baa1c656cf387481a52f217293d2f2ccedb09afebd2cdeda400f2a3`；white successor
contract=`648be46177390b2640e619d23324b68ebb59c431b731c4c03e4e2973c5550318`、
BIN=`e78cd7b18d8c020d09f1fc554cd4f0f2063cfcd8c3b590391ed637b0260bba45`。这些身份仍等待上述
live 前置证据，不构成自动执行许可。

比较器允许全 128 格或固定机位的合规 partial-camera 输入：两次可见格集合必须完全一致；只对
同一 controller、同一 recipe 且四个位置副本均可见的项目给出 REVIEW PASS/FAIL，缺少任一副本
固定标记 `UNTESTED_MISSING_REPLICAS`。相机比较仍不自动产生 qualified 颜色／灰阶／明度。

历史 recipe 的复现证据必须是 fresh-white reconstruction；原位 identical-target repeat 不得替代。

## D. 照片功能接入

只有完成 A+B+C 的 recipe 才能写入 controller-specific palette inventory。随后才允许：

- 为 CS1 和 CS2 分别量化照片像素；
- 生成按 LUT profile 分组的 source/middle/target pass；
- 对非当前 profile 像素填入该 controller 已资格化的 HOLD code；
- 检查后一个 LUT 对所有前序 LUT 的 directional retention evidence；
- 输出可审计的照片刷新计划。

在首次明度机制通过后，D 之前插入一个“稳定基色明度族推广”步骤：保持 source/middle/history
机制与位置平衡设计不变，只替换已知稳定 target endpoint，并分别对 CS1/CS2 重做粗筛、HOLD 与
fresh-white reconstruction。它属于功能泛化，不属于新增色相搜索。

上述顺序现由 `host.static_photo.function_first_orchestrator` 作为离线状态机强制执行。一个完成
六门的明度族即可开放其自己的有限 palette 子集，不必等待所有基色；但任何未通过的族都会被
排除。下游固定顺序为：qualified palette inventory → 照片逐像素映射 → multi-LUT HOLD schedule
→ 独立 source-white authority → fixed-photo execution bundle。任一前置缺失时，后续 artifact
会 fail closed；不会生成硬件动作或 live authority。

## 停止条件

任一 action 出现 BUSY timeout、driver fault、控制器明显不同步、固定边线、候选区被意外重刷、
异常发热或白恢复失败，立即停止；不 retry、不 fallback、不 recovery、不 autochain。主固件与每个
white successor 均使用独立 campaign/NVS/claim，已消费 action 禁止重放。
