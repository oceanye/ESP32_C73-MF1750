# R1/R2 快速刷新研究移交（2026-08-04）

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
Known limitations: 当前固件没有 2/4/8/10 MHz 参数化诊断入口；SPD1657B command datasheet、0x86 定义与匹配 Sparkle/partial waveform 仍缺失；partial planner 只生成控制器中立的数据，不生成 SPI 命令。
Risks requiring integrator review: 20 MHz 是面板接口上限而非板级保证；任何波形/局刷实验必须等待厂商资料；不得删除 E Ink V1.2 的显示后 power-cut 序列。
Suggested merge order: D0 baseline -> C1 -> R1 offline tooling；R2 文档可独立合并，任何未来 src 实验另开分支审查。
```

## 远端与集成状态（2026-08-04 更新）

- `research/fast-refresh` 已推送，工作包头提交为 `b03b7e1`；
- 已合入 `integration/host-fast-refresh-ci-color`，代码合并点 `42773d4`，
  集成说明点 `aa006c4`；
- 集成分支本地 `Ran 64 tests in 10.220s`，GitHub Actions
  [run 30862770816](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862770816)
  的主机门禁与 PlatformIO release 编译均成功；
- 上述结果仍为 `Hardware tested: NO`。SPI 实机扫频、快速波形和局刷没有因此
  自动解锁。

## 家中集成负责人下一步

1. 先完成 D0 的 MAP_ORIENT_V1 方向检查和 1 MHz 正常图片验收；
2. 审查 `docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md` 的证据矩阵与排除路线；
3. 在独立硬件诊断分支新增受限的 `2/4/8/10 MHz` MAP_ORIENT_V1 入口，不改默认 1 MHz；
4. 使用 `tools/mf1750_refresh_analyzer.py` 生成和填充扫频记录；
5. 10 MHz 全部通过且逻辑分析仪时序通过后，才单独评审 20 MHz；
6. 向 InkCubic/E Ink/Solomon 索取 SPD1657B、`0x86`、Sparkle/partial/fast mode 资料；
7. 未取得资料前不开始未知命令或波形实验。
