# MF1750 / SPD1657B Rev 1.1 完整分析与明度测试计划

2026-09-12：资料分析继续保留；具体执行顺序、授权边界、后续人工审查阈值与防偏离要求以 [统一执行计划](MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md) 为准。本文件中的 PLL/剂量/电压组合仅为研究建议，不是当前已封印现场扫描集合。

日期：2026-09-11  
资料：`参考资料/SPD1657B_1.1.pdf`，44 页，Solomon Systech **Advance Information**，Rev 1.1 / Sep 2024。  
资料 SHA-256：`7f867e165f4662aa525ba7f4e9d3413b0dc8f2ae3f3ae63d5c4a4023c5f0e41a`。

本文件是离线分析和现场测试入口。资料没有给出 MF1750 墨水专用 LUT、内部 phase 编码或稳定明度规格，因此不把任何寄存器范围直接变成现场参数，也不把 `Gray 0..7` 叫作已验证的八级明度。

## 结论先行

SPD1657B 没有一个可直接写入的“亮度”寄存器。对本项目的明度，优先级应为：

1. **完整 waveform/LUT 的状态转移**（最可能决定最终反射态）；
2. **3-bit KPixel 的离散目标索引**（只定义 0..7 的驱动/波形索引）；
3. 在固定 LUT 下研究全局帧率、温度和历史剂量的影响；
4. 最后才审查 source 电压、VCOM 和收尾选项，而且每次只允许一个受控变量。

芯片资料的 8 个 source 输出电平是 `VSH、VSH_LV、VSH_LV2、GND、VSL_LV、VSL_LV2、VSL、floating`（第 5 页），它们是电气驱动级，不等于光学 L*。当前目标仍是同色相单像素的明度等级，首先证明 3 级，再扩展 5、10；重复刷新次数不计入等级数量。

## 资料中可以直接采用的语义

| 资料位置 | 明确内容 | 对 MF1750 测试的用法 |
|---|---|---|
| 第 5、14 页 | 3-bit/pixel；片上 RAM、LUT、OTP；source 八级输出；最高帧率 100 Hz | KPixel 只能生成候选索引；必须用照片验证明度和色相 |
| 第 18、25 页 | PSR 的 P_mode 选择 2/3 bpp；DTM 在 3-bit 下每两个像素编码，至少写 1 字节后才能 DRF；DDX 决定 code 与 Gray 索引正反映射 | 记录实际 code、DDX、发送字节数；不把 code 数值当作 L* 顺序 |
| 第 18 页 | `LUT_EN=0` 复位自动加载有效 OTP；`LUT_EN=1` 不自动加载，PON/DRF 模拟设置随 MCU | factory-OTP 与 runtime-MCU 必须分开建档、分开验收 |
| 第 20–21 页 | PWR 定义 VGH/VGL 档位及 VSH/VSL、LV、LV2 的名义范围和 100 mV 步进 | 只做请求值与实测值对照；不把范围当成安全明度旋钮 |
| 第 26 页 | R30 FR 编码：25/32/43/50/65/75/85/100 Hz，默认 43 Hz | 允许离线解释既有 `02`/`03`；现场只能在完整 profile 固定后做单变量比较 |
| 第 26–27 页 | 内/外温度源，内温 0.5 °C 步进；TSC/TSE 操作期间 BUSY 为低 | 温度 raw、解码值、来源和 BUSY 必须同一记录；没有接口就保留 null |
| 第 28 页 | CDI 同时含 DDX、VBD 和 VCOM-data interval | 固定 DDX/VBD/CDI；VBD 示例不证明像素 HOLD |
| 第 30–32 页 | VCOM sensing 2/4/8/16 点、5/10/15/20 s；VDCS 为 -0.1 到 -4 V | 仅作 VCOM/电气健康研究，不作为明度调节首选 |
| 第 31 页 | PTLW 设定窗口，但窗口外 gate 仍扫描 | 不能由局部窗口宣称窗口外零电场或 HOLD |
| 第 35–36 页 | PON→DRF；LUT_EN=0 加载约 20 ms、LUT_EN=1 小于 1 ms；POF 后需等待放电 | 把 PON/DRF/POF BUSY 边沿、末帧和放电等待纳入协议门 |
| 第 15 页 | 级联 slave 不启用自己的振荡器、升压和稳压，全部来自 master | CS1/CS2 不能预设为独立时钟/电压变量；光学上仍分别验收 |
| 第 16–17 页 | BUSY 低时写命令不可用；参数必须完整；未列命令/参数保留；仅正常上电后有效 | 任何一条不满足即停止，不猜 R20/R21 或 phase 字节 |

第 2 页修订记录显示 Rev 1.1 只改变芯片托盘尺寸；第 44 页仍为免责声明。该 PDF 没有公开 R20/R21 的 LUT payload、11-byte phase 格式、重复次数编码、类别布局、MF1750 温区 LUT 或 DC balance 容限。

现有 `MF1750_SPD1657_HOLD_CODE_FEASIBILITY_AUDIT_2026-09-02.json` 的 9 项 HOLD 证明义务仍是硬阻断：R20/R21 精确 ABI、3-bit 到 LUT 的映射、record 时序与 repeat 语义、符号电压/极性、全 FF/00 语义、差分零定义、charge balance、CS1/CS2 公共绑定、MF-17506 FPL 安全边界。任一项未补齐时，`hold_code=null`，不得由全 FF、相同 transport code、光学端点或 relay OFF 宣称 HOLD。

## 与当前实现的边界

已核对的现有 tuple 仅作历史事实保存：

| profile | PWR payload | PLL | 文档解释 |
|---|---|---:|---|
| active/P1 | `0F 00 1E 78 20 1E` | `02` | 名义 43 Hz；请求的 LV 电压不能当实测值 |
| commented/P2-C | `0F 00 24 78 27 20` | `03` | 名义 50 Hz；同时改变了 LUT/电压，不能归因于帧率 |

公共初始化仍出现 PWR=`3F` 单字节和 PLL=`08`，runtime 六参数 PWR 首字节为 `0F`；这与公开六参数 PWR 和 FR[2:0] 域存在待解释差异。`R20/R21` 的真实扩展合同及内部 phase 继续记为 `OPAQUE`。不得为了“符合资料”直接把 runtime `0F` 改成 `3F`，也不得把 `08` 强行解释成 25 Hz。

当前相机只读证据（2026-09-11 08:19 +08）显示屏上仍有明显彩色色块，判定为**仍彩色**；采集本身的自动 verdict 仍是 `INCONCLUSIVE/low`，因为它是 retained-state 观察，不能声称与某次历史 action 连续：

- 照片：[current-frame.jpg](../.test-output/hardware/MF1750_CAMERA_CURRENT_STATE_20260911_V1/current-frame.jpg)，SHA-256 `e5ee7650c6d5ae74de15f880e32839e1d5586cb43e6cadfdfb5c3f90fbd02578`；
- sidecar：[current-frame.capture.json](../.test-output/hardware/MF1750_CAMERA_CURRENT_STATE_20260911_V1/current-frame.capture.json)，SHA-256 `86bd77534b25818010420254b5b71bf629e8e2d95f4f06bf7721d969a53b7286`；
- 相机身份为 `48MP USB Camera`、`VID_32E4:PID_4801`、DSHOW，4000×3000 MJPG @ 15 fps；硬件时间戳不支持，记录为 null；
- 本次没有 relay、SPI、复位、刷写或可见刷新；`qualified=0`。

## 测试阶段和执行顺序

### G0：资料、身份和离线封印

确认 PDF、主固件、独立 white successor、runner、合同、一次性 identity、输出目录的文件和哈希。执行 `tools/mf1750_lightness_test.py create`、native audit 和已有 Python 测试；生成新目录，使用 O_EXCL，不覆盖旧证据。

**通过条件：** 每个待测 action 都能绑定 panel、CS1/CS2、controller revision、boot、profile、source/target、firmware/action/frame hash、run_id。缺项保持 `HOLD_FOR_EVIDENCE`。

### G1：协议和电气基线（先于光学）

在现场放行后重新枚举 COM、精确绑定 IPv4↔MAC；相机重新枚举并只接受 `VID_32E4:PID_4801`。对已封印 profile 做只读或合同允许的诊断，记录：

- PSR、PWR、PLL、CDI、TRES、LUT_EN、DDX/VBD/FOPT/VCMZ/TIEG/NORG/VC_LUTZ 的最终写入顺序；
- 接口/拓扑：SPI 3/4-wire、dual/quad、BS[1:0]、M/S# master/slave、slave BUSY 是否可用；级联 slave 的时钟和高压来源必须明确写入记录；
- 每条命令的 opcode、D/C、完整参数、BUSY 前后状态、原始 status 和 BUSY 时间线；
- PON、DRF、POF 的持续时间，LUT 加载等待和浮空后的实际放电起止；relay OFF 不替代放电证据；
- CS1/CS2 的 master/slave 时钟和高压共用关系；若没有读回能力，明确标记 unknown，不推断。

BUSY 期间不发 mutation；协议异常、身份漂移、固定线或状态不明立即 `FAIL_STOP`。

### G2：固定 profile 的 3 级同色相筛选

每个 controller 独立完成 `fresh clean-white → source → middle → target`。先使用完整已知 profile，不改 LUT、电压、PLL 或 VCOM。每个状态四位置副本（TL/TR/BL/BR），每个 ROI 至少 10 张同态照片；温度、光源、曝光、焦距和 ROI 固定。

判读数据分成 camera-relative Lab 与 calibrated Lab 两套，不能混合：

- 彩色轴：`C* > 8`；低彩度进入 neutral 分支；
- 相邻及全链：`ΔL* ≥ 2`、`ΔE00 ≥ 3`、色相差 `≤ 5°`；
- 位置离散：四位置中位数的 P95 `abs(ΔL*) ≤ 3` 且 `ΔE76 ≤ 5`；
- 差异必须超过 `max(5×MAD, CI95 半宽)`；ΔE76 与 ΔE00 不互换阈值。

这些是本项目实验判据，不是厂商规格。Gray 名称只保存为 source code/索引标签，等级按实测 L* 排序。

### G3：HOLD、fresh 重建和保持

对 G2 通过的候选，单独封印 local-HOLD/邻域动作；PTLW 窗口外仍扫描 gate，必须实测目标 ROI 与对照 ROI 的变化。然后至少三条独立 fresh-white 重建链，检查等级顺序、色相和分离幅度。

静置采集 5 s、60 s、600 s，期间不刷新；记录 L*、a*、b*、ΔE00 和温度漂移。白恢复清除候选是正常恢复，不据此判定瞬态；瞬态只能由静置漂移、邻域刷新干扰或 fresh 重建失败判定。

### G4：帧率、剂量和电压的单变量研究

只有 G2/G3 通过后才进入。每次只改变一项，并从独立 fresh-white 开始：

1. **PLL**：固定完整 LUT、PWR、VCOM、温度、source/target，先比较 R30=`02`（名义 43 Hz）和 R30=`03`（名义 50 Hz）；25/32/65/75/85/100 Hz 仅在另行安全合同批准后考虑。记录 DRF BUSY 时长和光学结果。
2. **刷新剂量**：固定波形，比较 1/2/4/7/10 次完整 target action。次数不是 3/5/10 明度等级，不能用重复刷新凑等级。
3. **电压/VCOM**：仅在电源实测和独立 successor 可追溯时进行；每次只改一个已知字段，记录请求值、读回值和外部 rail 测量。任何未解释 PWR 模式差异都阻断现场写入。

### G5：5 级和 10 级扩展、双 controller 匹配

3 级先分别通过 G2/G3，才增加候选配方到 5 级；5 级通过后才讨论 10 级。每一级都要保持全链色相约束和噪声门。CS1、CS2 分别通过后，逐槽比较两边：`abs(ΔL*) ≤ 3`、`ΔE76 ≤ 5`、色相差 `≤ 5°`。任一 controller 未独立通过，不能用另一边补齐资格。

## 现场动作计数和停止条件

每一条 source/middle/target/fresh-white/HOLD/retention action 单独编号和封存。一次现场放行最多 `1 ARM / 1 EXECUTE / 1 driver / 1 visible refresh`，执行后立即停住判读；不自动 ordinal 递增、不重试、不盲目刷白。协议异常或 BUSY 状态不明时停止，不在 BUSY 中复位或重发 mutation。

以下任一项直接 `FAIL_STOP`：相机身份不是 VID_32E4:PID_4801、枚举路径前后漂移、COM/IP/MAC/boot 不匹配、BUSY 违反合同、参数不完整、固定线/边框/色斑污染、照片缺失或 ROI 重叠、action/frame hash 不匹配、未知扩展字节被猜测写入。

以下情况为 `HOLD_FOR_EVIDENCE`：只有单次端点差异、缺少四位置或 fresh 链、温度/相机能力未如实记录、只有 camera-relative 数据却声称 calibrated、只有 Gray 索引而没有 L* 与色相证据、白恢复或 lineage 尚未闭合。

只有 G0–G5 全部通过，才登记稳定明度等级；在此之前 `qualified=0`。P2 单次完成只能产生诊断结论。

## 每次记录的最小字段

```json
{
  "identity": {"panel": null, "controller": "CS1|CS2", "revision": null, "boot": null,
    "profile_id": null, "run_id": null, "firmware_sha256": null},
  "state": {"source": null, "target": null, "pixel_code": null, "gray_index_label": null,
    "test_phase": "SCREEN|HOLD|FRESH|RETENTION|OPAQUE"},
  "protocol": {"command_trace": [], "busy_timeline": [], "visible_refreshes": null,
    "frame_rate_nominal_hz": null, "frame_rate_measured_drf_ms": null},
  "optical": {"camera_id": "USB_VID_32E4_PID_4801", "raw_supported": null,
    "iso_supported": null, "hardware_trigger_supported": null, "roi": [],
    "camera_relative_lab": [], "calibrated_lab": []},
  "environment": {"temperature_raw": null, "temperature_c": null,
    "temperature_source": null, "relay": null, "electrical_state_proven": false},
  "evidence": {"action_json": null, "status_json": null, "photo_jpeg": null,
    "sidecar_json": null, "action_sha256": null, "frame_sha256": null},
  "judgement": {"verdict": "PASS|HOLD_FOR_EVIDENCE|FAIL_STOP", "qualified_count": 0,
    "reason": null}
}
```

本计划对应的离线入口仍是：

```powershell
python tools/mf1750_lightness_test.py create --output-dir <new-output-dir>
python tools/mf1750_lightness_test.py analyze --input <real-observation.json> --output <new-report.json>
```

不得用合成数值、旧 boot、旧相机身份或历史温度填充 FIELD_DERIVED。当前唯一现场前置仍是解决 white successor 的 source-main lineage FAIL_STOP，并重新取得同 boot 的 J2-OFF 诊断；在此之前不开始明度 action。
