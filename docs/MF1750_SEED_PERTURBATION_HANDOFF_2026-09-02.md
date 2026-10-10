# MF-1750 下一会话交接：P1 收口与 seed + perturbation 路线

最后更新：`2026-09-02 09:56 +08:00`

## 0.1 2026-09-02 09:56 离线 seed + perturbation 审计 V2 结果（最新）

已完成一个严格 fail-closed 的离线最小实现：

- 源码：`host/runtime_waveform/seed_perturbation.py`；CLI：
  `tools/mf1750_seed_perturbation_audit.py`；定向测试：
  `tests/test_runtime_waveform_seed_perturbation.py`。
- sealed 报告 V2：`docs/MF1750_SEED_PERTURBATION_OFFLINE_AUDIT_2026-09-02_V2.json`；文件
  SHA-256=`b2b4e9b6e318ed7c565c1d9b385ee751a3e58b87b4a7a987347c83af530dfe00`，canonical
  SHA-256=`a2a29d7dc5f52133db3be355e87f9143476c32db7829fb52c2c1ddcdd81945b4`。此前无 `_V2` 的
  同名报告保留为不可覆盖的旧 schema 快照，不作为当前验证入口。
- 默认结果：`OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI`、6 个 controller-local seed
  （CS1/CS2×C0/C1/C6）、`candidate_count=0`；没有生成 payload、firmware include、runner 或
  任何 live artifact。报告同时绑定已有 HOLD feasibility audit（9 项语义证明缺失）。
- 当前代码只有空的 reviewed-safe-axis allowlist；任意自报 `semantics_proven/safe_for_live`
  或任意 hash 都不能解锁候选。将来若有独立、身份固定的正向证明，M=1 上限为每 controller
  `3 seed×3 value=9`（两 controller 共18）条 metadata，仍 `live_eligible=false`，并要求四位置
  副本、单像素、无抖动、完整 BUSY。
- 报告的 I/O 证明为 `device_io=false/network_io=false/serial_or_com_io=false/
  visible_refreshes=0`；schema/audit 已生成，manifest 仅 metadata，runner/pack/NVS/identity/
  BIN/ELF/frame/DTM/contract/descriptor/action/live firmware 均 `NOT_GENERATED_BLOCKED`。
- 验证：seed 定向 `10 passed`；runtime-waveform + static-photo 相关 21 文件 `197 passed`；
  Ruff、py_compile、import/CLI smoke、repo-contract `30 passed`。没有访问硬件、网络、COM、继电器、
  相机或屏幕，也没有 commit/push。

这不改变现场门：白 successor 后仍缺 retained clean-white 的人工/48MP 视觉证据，`electrical_state_proven=false`，
所以 live 继续 NO-GO。补完 Gate 0 后，若安全 perturbation ABI 仍未被独立证明，下一条是 P2 两套已有完整
profile 的 8-code endpoint atlas，而不是 seed 固件或未知 LUT 写入。

## 1. 使用方式

- 建议开启一个**新会话**，不需要删除本会话或清理仓库；新会话仍使用同一工作区。
- 新会话先完整读取 `docs/STATUS_HANDOFF.md`，再读取本文。状态冲突时，以
  `docs/STATUS_HANDOFF.md` 的最新节和原始 evidence 为准。
- 本文后半部给出一段可直接复制的完整提示词。
- 本次整理只读证据并修改文档；没有访问设备网络、COM、相机或继电器，没有刷写、复位或刷新。

## 2. 当前现场与软件终态

### 2.1 最新已完成真屏 action

P1 完整 active-profile endpoint atlas 已完成：

- campaign：`EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1`
- action：`7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526`
- contract：`d36450e7cf69ad2e5e612f9df5b5abe0d33a036f9c3198a79a9e0e97a89a59f2`
- descriptor：`14a1b108c74e8898a1e5cc235ff93fdc8b315aebc45fc4682481a6aa915187d2`
- result file：
  `.test-output/hardware/MF1750_P1_COMPLETE_ACTIVE_ENDPOINT_20260901_V1/action-01-active-complete-position-balanced-4x8-endpoint-atlas.json`
- result file SHA-256：
  `dffb561044aa8103048fe535cdf10e1deebabd94e884740968f14083a3c80f72`
- canonical integrity：
  `d759ac0b16d4326015ec189f55adbcddd74177add302f3ac65bf60f254f9aa60`
- firmware BIN SHA-256：
  `f5c83b357c1db3dd065669e36d0ac9a09edfe47c720fadecad98c196a81652ed`
- boot nonce：`1f7cd896fb74e3b2`
- terminal：`COMPLETE / result=true / valid=true`
- exactly `1 driver call / 1 visible refresh`，无 retry、recovery、autochain。
- SPI `1 MHz`；总时长 `46631 ms`，PON/DRF/POF/post-PSR =
  `260/33931/151/5 ms`。
- profile：`LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535`；两 controller payload
  byte-identical。
- R20：command `0x20`、535 bytes、SHA-256
  `716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b`。
- R21：command `0x21`、704 bytes、SHA-256
  `24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f`。

人工观察文件：

`.test-output/hardware/MF1750_P1_COMPLETE_ACTIVE_ENDPOINT_20260901_V1/human-observation-p1-endpoint-v1.json`

其文件 SHA-256 为
`4f34b240c54a6898fe9733122db3c12dac097d385240fdca0ba9895de5c071a9`。结论是：

- C0 = 浅橄榄绿，C6 = 绿色，C1 = 黑色；
- 每个码的四个位置副本一致；左右同位一致；
- **不支持**“C0/C6/C1 是同色相三明度阶”；
- `qualified_new_colours=0`，`qualified_lightness_levels=0`；
- 浅橄榄绿仍只是 candidate，需 fresh-white reconstruction 和色卡/光学证据才能升级。

P1 只证明完整 profile endpoint 的位置/controller 重复性。它不是局部刷新、局部 HOLD、跨 LUT
共存、历史序列或明度资格证明。

### 2.2 独立白恢复与继电器终态

P1 的独立 factory-OTP white successor 已完成：

- result file：
  `.test-output/hardware/MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_20260901_V2/action-01-factory-otp-white.json`
- file SHA-256：
  `9e678853e4259a245c69194d99ca959c7af31169b3a9153bae858a6614c3a030`
- action：`b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc`
- terminal：`COMPLETE / result=true / valid=true`
- exactly `1 driver call / 1 visible refresh`；总时长 `35013 ms`，
  PON/DRF/POF/post-PSR = `180/22521/140/5 ms`。
- profile：factory OTP `WF23_25`；firmware SHA-256：
  `4f67f065993dfce3f6ffaeb2b5afb5a89f82c4563c9ad83b79c505311af24ef3`；
  boot nonce：`4d7868e0c07e8cb7`。

随后 COM14、channel 1、`COM1-NO1` 已 commanded OFF 且 query OFF：

- receipt：
  `.test-output/hardware/MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_20260901_V2/relay-post-white-off-20260901-210454819.json`
- receipt file SHA-256：
  `b978d1416c1f5d8f8e534384d848006869ff629fd7715b9c1342206b7dab8618`
- receipt canonical SHA-256：
  `b2eb110ff7f87ba4c4d96e3f1e73c55e6c2644f741301e705756e8e39d0a46fd`
- `electrical_state_proven=false`；继电器回执不能证明下游电压。

因此默认现场只能描述为：relay/J2 **last commanded OFF**，ESP32 预计仍保留 white-successor
固件，面板预计保留白场。白 action 后没有单独的人工/48MP clean-white review，所以在任何下一次
可见 action 前，必须先在**不刷新**条件下补一条“全屏干净白、无色块/边框/色斑残留”的视觉证据。

### 2.3 固定设备映射

- ESP32 USB：历史为 `COM8`，但每次必须重新枚举，不可把历史 COM 当当前证明。
- 继电器：`COM14`，channel 1，`COM1-NO1`；仍须按封印的 exact-bound identity 复核。
- 网络：最新历史候选为 `192.168.1.11`，MAC `A4-CB-8F-D9-FC-D4`；新 campaign 必须 fresh
  discovery 并重建 exact IPv4↔MAC binding，旧 IP 不构成设备身份。
- 相机：只允许本项目 48MP USB camera `VID_32E4:PID_4801`；不要使用双目
  `VID_1BCF:PID_0B15`。

## 3. 已证明与未证明

已证明：

- 完整 active/active L535 profile 能以一轮正常 BUSY 刷新显示 position-balanced 4×8 atlas；
- C0/C6/C1 在四位置和左右 controller 上具有肉眼位置重复性；
- 独立 WF23_25 factory-OTP white action 机器终态成功；
- 继电器曾完成 OFF command/query。

未证明：

- 新的合格单像素颜色或同色相明度阶；
- white successor 后的人工 clean-white 视觉门；
- 任意局部 HOLD、窗口更新或跨 LUT 颜色共存；
- SPD1657 的 R20/R21 record 字段、相位、极性或电压语义；
- 公开邻近 E6 波形与本面板/驱动板 ABI 兼容；
- 当前实际 J2、电压、电流、温度、GND、COM/IP/MAC 状态。

## 4. 公开 E6 资料能迁移的内容与边界

### 4.1 可作为算法参考

1. E Ink/IDW Spectra 6 论文说明六种 native pixel state；蓝色构色需要一个中间负向阶段，论文
   示例最佳约 `-8 V`、范围约 `-3..-14 V`，整刷约 12 秒、最大电压 15 V：
   <https://confit.atlas.jp/guide/event-img/idw2023/EP1-01/public/pdf_archive?type=in>
2. Modos Glider 公开 `lut[src][dst][frame]` 的 E6 软件模型，并在转换脚本中提供 WBF state
   mapping `0→0, 2→1, 5→2, 6→3, 8→4, 10→5, 12→6`：
   <https://github.com/Modos-Labs/Glider> 与
   <https://github.com/Modos-Labs/Glider/blob/main/utils/waveform_translate/translate.py>。
   仓库没有可直接用于本机的完整 E6 WBF/IWF 表。
3. E Ink 专利 `US20250191547A1` 给出 seed waveform + short perturbation 的搜索思想，候选空间
   可写为 `N×V^M`：<https://patents.google.com/patent/US20250191547A1/en>。
4. E Ink 2025 Ripple 宣称第二代 waveform + 升级 3-bit chipset 可提供 8 个 primary colours；
   这不能证明 SPD1657 兼容：
   <https://www.eink.com/news/detail/E-Ink-Ripple-Second-Generation-Waveform-Architecture-E%20Ink-Spectra-Displays>。

### 4.2 禁止直接迁移

- 不把论文中的 `-8 V` 直接写入硬件；
- 不移植其他控制器的寄存器、LUT 地址或高压配置；
- 不把 Glider 的软件 state index 当作本机 transport code；
- 不猜测本机 11-byte record 的字段含义；
- 不做未知命令扫描、任意 R20/R21 byte 插值、header/body hybrid、VCOM sweep、BUSY 中断或
  中途断电。

## 5. 下一步执行顺序

### Gate 0：先补白视觉闭环

在不刷新、不复位、不刷写的条件下，由人工或锁定的 48MP 相机确认 retained screen：

- 全屏干净白；
- 无 P1 色块、边框、色斑、横/竖线、底边间隔线或中心接缝异常；
- 记录相机 VID、分辨率、曝光/白平衡、原图和 sidecar；光照不足只记 `INCONCLUSIVE`。

只有 Gate 0 PASS，才可进入新的 live campaign。

### Gate 1：离线 seed + perturbation 可行性

先建立语义工具和 sealed contract，不直接上屏：

1. 从仓库已经验证的**完整** profile/code endpoint 建 controller-local seed inventory；CS1/CS2
   分开，P1 C0/C6/C1 只标 candidate seed。
2. 审计现有完整 profile 数据，确认是否存在一个已知、可解释、不会碰未知高压字段的
   time/frame perturbation 维度。
3. 若不能证明安全可控的 perturbation 维度，状态必须是
   `OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI`，不得生成可执行 live firmware；转入 Gate 1B。
4. 若能够证明，第一轮只允许 `M=1`、小规模、完整 BUSY 的候选：3 个 seed × 3 个已知合法
   perturbation = 每 controller 9 个候选；每候选 4 个位置副本、单像素实色、无抖动，两 controller
   第一轮使用相同 payload。
5. 每个 action 恰好 1 driver/1 visible refresh，无 retry/recovery/autochain；主 action 后是独立
   factory-OTP white successor。所有 BIN/ELF/frame/DTM/contract/action/NVS 都必须封印并测试。

### Gate 1B：安全回退路线

如果 Gate 1 无安全 ABI，下一真屏使用 P2 完整 profile endpoint map，而不是猜字段：

- fresh factory-OTP white；
- 已知完整 profile A 的 8-code position-balanced 4×8 atlas，一次完整刷新；
- 人工/48MP 粗筛；
- 独立 factory-OTP white；
- 再 fresh white 后，另一个已有完整兼容 profile 的 8-code atlas；
- 两 controller 分开分析，每码四副本；无候选即白收尾，不做 repeat。

### Gate 2：候选升级

只有出现无条纹/网点/空间交错、四边干净、四副本一致的候选，才依次执行：

1. 独立白收容；
2. 从 fresh white 完整 reconstruction；
3. 再次 fresh reconstruction；
4. 同一候选的局部 HOLD `T0/T1/T2` 探针；
5. 跨 LUT 保持；
6. 色卡/光学测量与 controller-local 命名；
7. 通过后才加入静态照片 palette。

明度按 `3→5→10` 逐级证明；建议粗筛 `|ΔL*|≥8` 且同色相角差 `≤10°`，但相机粗筛只能给
`REVIEW`，不能自动给 `qualified`。

## 6. 停止条件

任一即停止且不自动重试：限流/掉压；BUSY 缺失或超过同 profile 基线约 2 倍；PON/DRF/POF/PSR
顺序异常；SPI/HTTP/claim/ordinal/NVS/哈希不一致；左右异常分叉；固定横线/竖线/底边间隔线；
白恢复失败；异常声、味、发热或 FPC/COG 热点；用户停止、离开或断电。恢复只能是独立、精确
绑定的 factory-OTP white successor。

## 7. 每轮必须记录

每个 attempt 使用不可覆盖的新目录，保存 preflight、授权原文及 hash、identity/IP↔MAC binding、
contract/descriptor/action、BIN/ELF/frame/DTM SHA-256、NVS/claim、HTTP transcript、BUSY/timing、
relay command/query、48MP 原图与 sidecar、人工观察、verdict、white successor 和最终 OFF。每次软件
里程碑、真屏 action、人工裁决或安全收尾都更新 `docs/STATUS_HANDOFF.md` 和当天真屏日志。

工作区有大量用户脏改；只使用显式文件白名单，禁止 `git add -A`、reset、checkout 或覆盖他人改动。
本交接没有授权 commit/push。

## 8. 可直接复制到新会话的完整提示词

```text
继续 MF-1750 / SPD1657 单像素静态照片颜色项目。先不要碰硬件；先完整读取
`docs/STATUS_HANDOFF.md`，然后完整读取
`docs/MF1750_SEED_PERTURBATION_HANDOFF_2026-09-02.md`。状态冲突时，以 STATUS 的最新节和原始
evidence 为准。先只读检查 `git status --short`、相关 diff 与最近提交，保留所有用户脏改；禁止
reset/checkout、`git add -A`、覆盖或删除历史 evidence。

目标是建立可重复、可组合、可恢复的真实单像素颜色链，最终目标为 256 个逻辑颜色槽：16 个
中性槽 + 12 个色相族×2 条子轨×10 个明度档。空间抖动、条纹、网点或左右像素空间混色永远不算
单像素新色；明度按 3→5→10 逐级证明，不能凭视觉印象凑数。

当前已知终态：P1 active endpoint atlas action
`7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526` 已 COMPLETE，1 driver/
1 visible refresh、无 retry/recovery/autochain。人工结果为 C0=浅橄榄绿、C6=绿色、C1=黑色；四位置
副本一致、左右同位一致，但这不是同色相三明度阶，当前仍是 0 qualified new colours / 0
qualified lightness levels。独立 WF23_25 factory-OTP white successor action
`b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc` 机器终态 COMPLETE；随后
COM14 channel1 COM1-NO1 commanded/query OFF，但 `electrical_state_proven=false`。白 action 后缺少
独立人工/48MP clean-white review，所以任何下一次可见 action 之前必须先补这个不刷新的视觉门。

设备映射：ESP32 历史为 COM8、继电器 COM14/channel1/COM1-NO1；每次都重新枚举，历史 COM 不算
当前证明。历史网络候选为 192.168.1.11 / A4-CB-8F-D9-FC-D4，新 campaign 必须 fresh discovery
和 exact IPv4↔MAC binding。相机只能用 48MP `VID_32E4:PID_4801`，不能误用双目
`VID_1BCF:PID_0B15`。

新会话先报告：已读文件、STATUS 最后更新时间、当前 live 是 GO 还是 NO-GO、证据缺口、下一项
纯离线动作。当前已有 sealed 离线结果
`docs/MF1750_SEED_PERTURBATION_OFFLINE_AUDIT_2026-09-02_V2.json`（默认
`OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI`、candidate_count=0）；先独立验证其 canonical/file
hash，再继续任何离线动作。随后优先完成 seed + perturbation 的离线可行性审计与最小实现：从仓库已验证完整
profile/code 建立 controller-local seed inventory；CS1/CS2 分开；不得把 P1 candidate 当 qualified。
只允许使用仓库已有完整 BUSY、已知安全的 profile/code/阶段语义。严禁猜测 11-byte record、直接
套用论文 -8V、移植邻芯片寄存器/LUT、未知命令扫描、任意 R20/R21 byte 插值、header/body hybrid、
VCOM sweep、BUSY 中断或中途断电。

公开资料只作为算法线索：Spectra6 论文提示蓝色需要中间负向阶段；Glider 提供
`lut[src][dst][frame]` 软件模型但没有本机可用的完整 WBF/IWF 表；E Ink 专利
US20250191547A1 给出 seed waveform + short perturbation、候选空间 N×V^M；Ripple 的 8 primary
colours 依赖新 waveform + 3-bit chipset，不能当作 SPD1657 兼容证明。

离线 Gate：先判断现有完整 profile 中是否存在一个已知、可解释、不会改未知高压字段的
time/frame perturbation 维度。若不能证明，明确输出
`OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI`，不生成 live firmware，并转做安全 P2：两套已有完整
profile 各自 fresh-white→8-code position-balanced 4×8 endpoint atlas→独立白。若能够证明，第一轮
只做 M=1：3 个 seed×3 个已知合法 perturbation，每 controller 9 个候选、每候选四位置副本、单像素
实色、无抖动；两 controller 第一轮 payload 相同。每 action 恰好 1 driver/1 visible refresh、正常
完整 BUSY、无 retry/recovery/autochain，并配独立 factory-OTP white successor。

离线完成 manifest/schema/runner/pack/audit、唯一 NVS/ordinal、exact identity、BIN/ELF/frame/DTM/
contract/descriptor/action SHA-256 封印；运行定向及相关全量 pytest、Ruff、py_compile/import smoke、
PlatformIO clean build。离线工具必须证明 device_io=false/network_io=false/visible_refreshes=0。所有
离线准备完成后再向我请求一次明确、有限、列出 action 的 live 确认；不要反复让我填写长口令。

真屏时先补 retained clean-white 视觉闭环。用户只负责确认上游电源/基本安全和必要的人眼颜色判断；
你可在已明确授权的固定 action 内控制继电器和 runner。每次 action 前都 fresh 枚举/bind，不复用旧
IP/claim/NVS，不重放已消费 action，不自动串联未列出的下一 action。相机光线不足则记
INCONCLUSIVE，不猜颜色。只有发现无条纹/网点、四边干净、四副本一致的候选，才依次做独立白、
两次 fresh reconstruction、局部 HOLD T0/T1/T2、跨 LUT 保持和色卡/光学标定；未命中直接记阴性并
白收尾，可靠性/长时保持和大规模色相枚举后置。

停止条件：限流/掉压、BUSY 缺失或超过基线约 2 倍、序列/哈希/identity/NVS/claim 不一致、左右
异常分叉、固定横竖线/底边间隔、白恢复失败、异响异味发热、用户停止/离开/断电。停止后不自动
重试；恢复只能使用独立、精确绑定的 factory-OTP white successor。

每完成软件里程碑、真屏 action、人工判定或安全收尾，立即更新 `docs/STATUS_HANDOFF.md` 和当天
真屏日志，保存不可覆盖的 machine JSON、人读 Markdown、授权、哈希、HTTP transcript、BUSY/timing、
relay receipts、48MP 原图/sidecar、人工观察和白收容证据。未经我另行要求，不 commit/push；若之后
需要同步 GitHub，只提交明确白名单，且若新增 Python 依赖必须更新根 `requirements.txt` 并验证
clean-machine 安装与 smoke/test 命令。
```
