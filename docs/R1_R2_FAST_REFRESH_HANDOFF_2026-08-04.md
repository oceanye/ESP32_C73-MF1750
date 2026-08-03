# R1/R2 快速刷新研究移交（2026-08-04）

```text
Work package ID: R1 (offline tooling) / R2 (evidence research)
Baseline commit SHA: 3033da0
Branch name: research/fast-refresh
Objective: 建立 MF-1750 快速刷新一手证据边界、SPI 扫频门禁和离线日志分析工具。
Files changed: docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md, docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md, research/fast_refresh/, tools/mf1750_refresh_analyzer.py, tests/test_refresh_analyzer.py
Files intentionally not changed: src/, hardware/, platformio.ini, 冻结生产文件
Assumptions: 当前规范 fixture/hash 与 main 3033da0 一致；SPI 测试使用独立冷启动；面板规格 50 ns 写周期仅作为接口理论上限。
Commands run: python -m unittest discover -s tests -v; python tools/mf1750_refresh_analyzer.py plan | python -m json.tool; python -m json.tool research/fast_refresh/evidence_matrix.json; git diff --check
Exact test output / exit codes: 11 tests; Ran 11 tests in 0.001s; OK; exit code 0; generated plan/evidence JSON valid
Hardware tested: NO
Known limitations: 当前固件没有 2/4/8/10 MHz 参数化诊断入口；SPD1657B command datasheet、0x86 定义与匹配 Sparkle/partial waveform 仍缺失。
Risks requiring integrator review: 20 MHz 是面板接口上限而非板级保证；任何波形/局刷实验必须等待厂商资料；不得删除 E Ink V1.2 的显示后 power-cut 序列。
Suggested merge order: D0 baseline -> C1 -> R1 offline tooling；R2 文档可独立合并，任何未来 src 实验另开分支审查。
```

## 家中集成负责人下一步

1. 先完成 D0 的 MAP_ORIENT_V1 方向检查和 1 MHz 正常图片验收；
2. 审查 `docs/R2_FAST_REFRESH_TECHNICAL_PATH_2026-08-04.md` 的证据矩阵与排除路线；
3. 在独立硬件诊断分支新增受限的 `2/4/8/10 MHz` MAP_ORIENT_V1 入口，不改默认 1 MHz；
4. 使用 `tools/mf1750_refresh_analyzer.py` 生成和填充扫频记录；
5. 10 MHz 全部通过且逻辑分析仪时序通过后，才单独评审 20 MHz；
6. 向 InkCubic/E Ink/Solomon 索取 SPD1657B、`0x86`、Sparkle/partial/fast mode 资料；
7. 未取得资料前不开始未知命令或波形实验。

