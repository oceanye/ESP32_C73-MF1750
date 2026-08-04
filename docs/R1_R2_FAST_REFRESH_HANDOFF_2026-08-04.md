# R1/R2 快速刷新研究移交（2026-08-04）

> 下列代码块是 `b03b7e1` 原始研究分支的 19-test 历史移交；后续 schema v2
> 加固与联合回归结果见后文，均未执行实机扫频。

```text
Work package ID: R1 (offline tooling) / R2 (evidence research)
Baseline commit SHA: 3033da0
Branch name: research/fast-refresh
Objective: 建立 MF-1750 快速刷新一手证据边界、SPI 扫频门禁和离线日志分析工具。
Files changed: docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md, docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md, research/fast_refresh/, host/partial_update/, tools/mf1750_refresh_analyzer.py, tools/mf1750_partial_plan.py, tests/test_refresh_analyzer.py, tests/test_partial_update_planner.py
Files intentionally not changed: src/, hardware/, platformio.ini, 冻结生产文件
Assumptions: 当前规范 fixture/hash 与 main 3033da0 一致；SPI 测试使用独立冷启动；面板规格 50 ns 写周期仅作为接口理论上限。
Commands run: python -m unittest discover -s tests -v; python tools/mf1750_refresh_analyzer.py plan | python -m json.tool; python -m json.tool research/fast_refresh/evidence_matrix.json; git diff --check
Exact test output / exit codes: 19 tests; Ran 19 tests in 0.002s; OK; exit code 0; generated plan/evidence JSON valid; full 307200-byte transition plan completed with histogram total 614400
Hardware tested: NO
Known limitations: 当前固件没有统一的 1/2/4/8/10 MHz 参数化 MAP sweep 入口（普通 `/api/frame` 仅能完成 1 MHz G0）；SPD1657B command datasheet、0x86 定义与匹配 Sparkle/partial waveform 仍缺失；partial planner 只生成控制器中立的数据，不生成 SPI 命令。
Risks requiring integrator review: 20 MHz 是面板接口上限而非板级保证；任何波形/局刷实验必须等待厂商资料；不得删除 E Ink V1.2 的显示后 power-cut 序列。
Suggested merge order: D0 baseline -> C1 -> R1 offline tooling；R2 文档可独立合并，任何未来 src 实验另开分支审查。
```

## 远端与集成状态（2026-08-04 更新）

- `research/fast-refresh` 已推送，工作包头提交为 `b03b7e1`；
- R1/R2 代码由 `18ae8c0` 合入集成线；包含 C2 的总集成代码点为 `42773d4`，
  集成说明点为 `aa006c4`；
- 集成分支本地 `Ran 64 tests in 10.220s`，GitHub Actions
  [run 30862770816](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862770816)
  的主机门禁与 PlatformIO release 编译均成功；
- 上述结果仍为 `Hardware tested: NO`。SPI 实机扫频、快速波形和局刷没有因此
  自动解锁。

## 家中集成负责人下一步

1. D0 已完成：约 8 MB OPI PSRAM、100 kHz MAP_ORIENT_V1 和正式 1 MHz
   规范帧均已实机通过；先封存 H0，再评审任何独立加速实验；
2. 审查 `docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md` 的证据矩阵与排除路线；
3. 在独立硬件诊断分支新增受限的参数化 `1/2/4/8/10 MHz` MAP_ORIENT_V1 sweep
   action；现有普通 `/api/frame` 1 MHz 只用于 D0，不冒充该 sweep 入口；
4. 使用 `tools/mf1750_refresh_analyzer.py` 生成和填充扫频记录；
5. 10 MHz 全部通过且逻辑分析仪时序通过后，才单独评审 20 MHz；
6. 向 InkCubic/E Ink/Solomon 索取 SPD1657B、`0x86`、Sparkle/partial/fast mode 资料；
7. 未取得资料前不开始未知命令或波形实验。

## Partial planner 集成加固

后续集成已将 `old_frame` 文件与屏幕真实旧状态分离：仅提供旧帧时，planner
必须输出 `conservative_full_screen`，不得生成推测性的转移矩阵。只有同时提供
最后一次成功显示的 operation ID、该操作的帧 FNV-1a、显式可信标志，并且哈希
与旧帧一致，才会进入 `trusted_transition`：

```powershell
python tools/mf1750_partial_plan.py new.bin `
  --old-frame old.bin `
  --last-success-operation-id <operation-id> `
  --last-success-frame-fnv1a <0x-hash> `
  --trust-last-success
```

默认区域是 `logical_half_regions`，逻辑半屏不会被推定为 CS1/CS2。若集成方已
冻结并审查两个 `ControllerMapping`，可按物理控制器顺序显式追加两次，例如：

```powershell
--frozen-controller-mapping 0,0,0,0 `
--frozen-controller-mapping 1,0,0,0
```

四项依次是 `source_half,flip_x,flip_y,nibble_swap`，均使用 `0/1`。只有显式
提供完整、互为双射的两项映射后，报告才附加物理控制器局部坐标。邻域保护
半径限制为 `0..32`；未知状态走全屏保护路径，真实 changed/unchanged 数量保持
`null`，不会伪称整屏真的发生了变化；全屏已知变化会走快速路径。上述 planner 改动
仍为离线研究代码，未生成 SPD1657B 指令，也没有经过硬件局刷验证。

## 2026-08-04 集成审查修正

扫频记录已升级为 schema version 2：限定单次日志，交叉核对 job/diagnostic/serial，
强制检查 report 状态与安全收尾，记录 PON/DRF/POF/post-PSR、电压、电流、温度和
异响，并支持显式记录失败。该工具仍只处理离线文件，不连接设备，也不代表当前
SPD1657B 已具备快速或局部波形。

最终加固还要求 diagnostic schema/API、job/report 三个 u32 时间戳、driver
`operation_id` 与 wrapper `job_operation_id` 精确绑定，且
`busy_assertion_missing=false`、`busy_missing_stage=none`。PON/DRF/POF BUSY 必须
为 true；POF 后 PSR 的 BUSY 采样允许为 false。四阶段等待与采样仍须同时出现在
串口与 report 中并逐项相等，DRF 保持 10..60 秒。analyzer 专项仍须保持全通过。

实机此前的 RC1/旧 RC2 没有完整的 report/job/build 关联。当前已实测的
`MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04` /
`MF1750_R16_CASCADE_V3` 已把 diagnostic report 绑定到 firmware build、driver API、job
id/action/state/result 和时间戳；RC2C 的正式 1 MHz `/api/frame` 已完成 D0 验收，
但 MAP slow action 仍固定为 100 kHz，且没有独立
参数化 `map_orient_v1_sweep` action。因此 RC2C 仍不能满足 schema v2 的正式升频
证据合同。必须先在隔离硬件诊断分支实现受限 sweep action，并附实测 SCLK 证据，
才允许 analyzer 输出 G1 扫频 PASS。
