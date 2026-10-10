# MF1750 彩色明度测试 V1

测试编号与判据版本：`MF1750_LIGHTNESS_TEST_V1_20260911`。

本测试包实际提供离线建包、空白记录检查和光学等级链分析命令，另能对现有 P2 原始证据重新判读。现场固件和恢复动作仍需解决资料/实现差异及 fresh source 绑定；本工具没有设备访问或刷新入口。

## 1. 测什么

目标是同一色相、同一 track 的单像素明度；首先判定是否有 **3 个不同等级**，再按相同判据扩到 5、10。四位置副本、每状态 10 张照片、三次独立 fresh 重建都不增加等级数量。256 槽总目标仍是 `16 neutral + 12 hue families × 2 tracks × 10 ranks`，本轮优先彩色轴。

均匀色块内每个像素使用同一配方，以相机能分辨的色块作为单像素状态代理，不做抖动或邻像素平均构色。camera-relative Lab 与经过标定的 Lab 必须分开数据集；只有标定证据哈希并不足以自动取得光学资格。

## 2. 两条测试路线

### A：位置平衡历史配方筛选

复用现有 V3 的 `recipe_map()`，保持其真实的 controller-local ROI 和 CS2 180°语义置换，生成 **128 个测量槽**：

`CS1/CS2 × 16 recipes × 4 quadrants`。

每个 controller 是 8×8 色块阵列。16 个配方为：

`active C7 source → commented M0…M7 → active T3 或 T7`。

T3、T7 分成两个比较组，每组八个候选配方；不能跨组、跨 controller、跨照明或跨温度拼出明度阶。相同 target code 也不自动证明同色相，仍需测量色相角。

因此当前矩阵最多给同一target提供8个候选，适合先筛3/5阶；要检验10阶必须另外建立至少两个不同配方及独立证据，不能重复现有配方凑数。通用分析器支持最多16个候选/比较组，但本包没有伪造额外配方。

这条路线的 source、middle、target 对应 **三个独立可见动作**，每步必须单独停止审查，不能装成“一次刷新测试”。建立 fresh white 的独立恢复动作另计。旧 V3 的 G4 identical-target repeat 不列入本轮必需动作，也不能充当 HOLD。

现成 V3 runner 绑定历史 white successor，不能从当前 P2 彩色 atlas 直接启动。测试包重用几何和分析对象，没有重用历史 white/boot 身份，也没有给旧 runner 发放行令。

### B：固定完整 LUT 的帧率影响

新资料已解释 PLL：active 的02为名义43 Hz，commented的03为名义50 Hz。但两套现有 tuple 同时改变 LUT 和电压，不是帧率单变量对照。**本包没有选定 PLL 扫描值，没有生成新波形或固件。**

本轮已把差异追溯到本地来源：

| 差异 | 本地来源 | 本次判定 |
|---|---|---|
| runtime PWR 固定首字节0F | `MF1750_VENDOR_SAMPLE_DEEP_AUDIT_2026-08-10.md` 的 loader 写入序列表：R01/6 = 固定0F + decoded[0..4] | 来源可追溯；与新资料 A[5:4]=11 的语义差异未解决，不能直接改3F |
| 公共 PLL=08 | `参考资料/REG-API-oqc(1)(1)/REG-API-oqc/Sample Code/E28xx.c` 的 epdInitial 同样写R30/08；`User/EDP_init.c` 也出现该值 | 是原样例已有行为；不证明08是标准25 Hz，更不证明可扫所有FR编码 |
| OTP PWR 单参数3F | E28xx.c 的 epdInitial 同样只写R01/3F | 来源可追溯；公开六参数形式与扩展/OTP模式的关系仍待实证 |

公共源码先扩展初始化，再写 PSR/PWR/PLL；P2 generated driver 随后设 MCU LUT 模式、六参数PWR、PLL=03、TRES和R20/R21，最后PON/DRF/POF。当前没有只针对这些位的受控总线/电源对照，故不把源代码出处当作安全证明。

帧率路线前提：解释上述模式差异，确认最后生效的频率、master/slave共享时钟和电源作用范围，以及同一LUT/电压组合的面板适用性。之后再另建单变量、独立起始态、有界动作合同；本次分析器只支持一个相机/状态集合，不能直接合并不同帧率run。

## 3. 当前已实现的判读

先检查数据身份/协议和图像审查，再计算每 controller、每比较组内的四位置和同色相等级链。输入为空、缺测量或温度等绑定缺失时返回 `HOLD_FOR_EVIDENCE`；协议明确FAIL时返回 `FAIL_STOP`。文件损坏、重复位置、NaN、错误相机等非法输入以 `FAIL_STOP` 拒绝。

冻结判据如下。其数值沿用 P2 candidate-separation-v1、position/cross-controller-v1 的相应界限；新加入四象限逐对检查和整条链同色相检查，因此用新版本，不能覆盖旧 P2 报告。

| 指标 | 本版实验判据 | 实现范围 |
|---|---|---|
| 空间副本 | TL/TR/BL/BR 各一，标签符合controller-local ROI中心所在象限，物理ROI不重复；照片不能冒充位置副本 | 已实现 |
| 位置离散 | 对四位置分量中位数，P95 `abs(ΔL*) ≤ 3` 且 `ΔE76 ≤ 5` | 已实现 |
| 彩色轴 | C* > 8；低彩度另作 neutral 测试 | 已实现 |
| 明度分离 | 相邻及整条链所有配对，`ΔL* ≥ 2`、`ΔE00 ≥ 3`、色相差≤5° | 已实现 |
| 噪声 | 每ROI至少10张同态照片；L*与ΔE00各用 `max(5×MAD, CI95半宽)`；差异必须超过对应噪声界 | 已实现 |
| 四位置配对 | 中位数通过且每对同象限副本均同方向、通过分离/色相/噪声门 | 已实现；同象限不等于同一个物理ROI |
| 完整等级链 | 所有成员两两满足色相约束，防止相邻色相逐步漂移；按L*排序 | 已实现；不自动授予稳定等级 |
| 双controller匹配 | 各自先通过；同槽 `abs(ΔL*) ≤ 3`、`ΔE76 ≤ 5`、色相差≤5° | 后续独立证据槽，本工具尚不验收 |

所有阈值是**实验判据**，不是厂商规格。L*差、ΔE76、ΔE00不能互换；5/10阶不自动降低门槛。旧 `lightness_screen.py` 的粗筛L*≥8仍是原工具的口径，本工具明确使用上表版本，不修改它。不能把两套阈值的PASS混用。

纯函数只检查结构与派生数值；CLI另外核对原始文件哈希。输入中声明的协议/图像PASS仍来自独立审查，不是本程序新完成的协议认证。因此即使光学三阶通过，最终也保持 `HOLD_FOR_EVIDENCE`、`qualified=0`，等待后续阶段。

## 4. 必需的后续测试

每个controller依次建立：

1. SCREEN：同色相候选3阶及四位置证据。
2. LOCAL HOLD：单独封印/放行邻域动作；保留候选ROI前后变化与未受影响对照。PTLW窗口外仍扫描gate，不能单凭窗口设置证明零驱动。
3. FRESH WHITE RECONSTRUCTION：三条独立fresh-white链重建同一配方，等级顺序和分离幅度可复现。各white/source/middle/target均按独立动作计数。
4. RETENTION：5/60/600秒静置采集，期间不刷新；固定光源、温度和相机设置。保持判读必须另行冻结阈值，本包未擅自定义保持PASS。
5. CROSS CONTROLLER：两边各自通过后逐槽光学匹配。
6. REVIEW：判定者审查后才登记稳定3阶；扩5/10需前一级通过证据。

`lifecycle.blank.json` 为上述证据留槽，全部初始null；它不接受靠填写PASS或自报哈希自动授予资格。白恢复清除候选属于正常恢复。瞬态应由静置漂移、邻域干扰或fresh重建失败判定，不能由刷白后消失判定。

## 5. 实际命令

从仓库根目录运行。所有输出使用新目录或O_EXCL文件，不覆盖旧证据。

```powershell
python tools/mf1750_lightness_test.py create --output-dir .test-output/offline/MF1750_LIGHTNESS_TEST_20260911_V1_R3
python tools/mf1750_lightness_test.py review-p2 --output-dir .test-output/offline/MF1750_LIGHTNESS_TEST_P2_REVIEW_20260911_V1_R3
```

`create` 输出测试计划、判据、128格空白测量表、三动作原始证据记录表、3/5/10后续证据槽、空表判读和SHA manifest。`run-record.blank.json` 为SOURCE/MIDDLE/TARGET分别保留身份、带范围的profile哈希、BUSY、原始action/status、照片、人工观察、派生分析和实际计数；它是待填证据槽，不是新live门禁。`review-p2` 核对封存光学报告、action、20张照片及20份sidecar，再重算四位置和明度链；没有相机或设备操作。

本次最终产物使用R3目录；此前V1及R2目录保留为开发验证证据，不覆盖、不复用。再次建包请另取未存在的新目录。R2补明八候选上限并增加物理ROI重复计数拒绝；R3再补物理象限校验、显式实验阶段与三动作原始证据表；各版使用同一冻结光学阈值。单独端点的candidate_level_count=1不代表通过一级资格。

后续填入一个新的观测文件，保持所有缺失值为null，执行：

```powershell
python tools/mf1750_lightness_test.py analyze --input <新观测JSON路径> --output <未存在的报告JSON路径>
```

FIELD_DERIVED数据必须列出真实存在且哈希匹配的evidence_files，观测必须绑定其中的测量证据。不得用合成示例、已填虚构数值或旧温度/相机身份替代新现场证据。TEST_FIXTURE只允许软件验证，始终零资格。

每轮保存panel、CS1/CS2、revision、boot、profile、source/target、action/firmware/frame哈希、阶段、温度、请求/实际相机设置、ROI和run_id。RAW/ISO/硬件触发能力按本次设备真实情况记录，不支持即false/null。未知内部phase始终OPAQUE。

## 6. 现场状态与下一入口

当前屏幕只依据操作者最后报告为2×4×8彩色atlas；本轮未观察设备，relay最后OFF、electrical_state_proven=false。建立测试不自动授权刷白、重试或后续ordinal。

现场动作前先解决/审查参数模式差异，再检查独立white successor与当前条件；获有界放行后fresh枚举COM/IP/MAC、app-only写入保留NVS、重新获取刷写后同boot J2-OFF diagnostic，再依证据确认电气条件。一次放行最多1 ARM/1 EXECUTE/1 driver/1 visible refresh，随后停住。协议异常或BUSY状态不明时不重发、不盲目复位/刷白。

本包的可立即执行入口是 `create`、`review-p2` 和 `analyze` 的离线命令；没有live子命令。旧现场合同、生产目录和证据保持原样。
