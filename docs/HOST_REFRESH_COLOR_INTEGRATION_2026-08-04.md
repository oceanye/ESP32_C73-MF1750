# 主机快速刷新与色彩流水线集成（2026-08-04）

集成分支：`integration/host-fast-refresh-ci-color`

该分支基于 `main` 的 D0 基线 `3033da0`，汇总以下可独立审查的工作包：

| 工作包 | 分支 | 关键提交 | 作用 |
|---|---|---|---|
| C1 | `feature/host-frame-core` | `cb0a03f` | 规范 1024x600 4bpp 帧、双控制器拆分与 fixtures |
| R1/R2 | `research/fast-refresh` | `b03b7e1` | SPI 扫频分析、证据门禁与控制器中立的局部更新规划 |
| C5 | `feature/host-ci` | `c59a1f2` | 冻结契约、主机回归与云端 PlatformIO 编译 |
| C2 | `feature/color-dither` | `7cc015e` | RGB/RGBA 六色量化、确定性抖动、预览与报告 |

集成合并点为 `42773d4`。本地执行：

```powershell
python tools\check_repo_contract.py --output repo-contract-report.json
python -m unittest discover -s tests -v
python -m compileall -q host tests tools
git diff --check
```

结果：仓库契约通过；`Ran 64 tests in 10.220s`；`OK`；全部 exit code 0。

此分支没有修改 `src/epd_driver.*`、硬件设计或冻结生产文件，也没有刷写或
连接实物。CI/PlatformIO 成功仅代表主机契约和固件编译成功，始终不是硬件
验收。快速波形/局刷仍受 SPD1657B 与面板 OTP 厂商资料门禁约束；色彩效果仍
需要家中使用实测 D65/2deg 六色 Lab 色板并进行实屏主观验收。

家中整合时可直接审查该分支，也可按表中顺序逐个合并工作包。`main` 未由本机
自动更新。
