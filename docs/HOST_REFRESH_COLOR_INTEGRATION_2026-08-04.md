# 主机快速刷新与色彩流水线集成（2026-08-04）

集成分支：`integration/host-fast-refresh-ci-color`

该分支基于 `main` 的 D0 基线 `3033da0`，汇总以下可独立审查的工作包：

| 工作包 | 分支 | 关键提交 | 作用 |
|---|---|---|---|
| C1 | `feature/host-frame-core` | `cb0a03f` | 规范 1024x600 4bpp 帧、双控制器拆分与 fixtures |
| R1/R2 | `research/fast-refresh` | `b03b7e1` | SPI 扫频分析、证据门禁与控制器中立的局部更新规划 |
| C5 | `feature/host-ci` | `c59a1f2` | 冻结契约、主机回归与云端 PlatformIO 编译 |
| C2 | `feature/color-dither` | `7cc015e` | RGB/RGBA 六色量化、确定性抖动、预览与报告 |

最初的代码集成合并点为 `42773d4`。该快照执行：

```powershell
python tools\check_repo_contract.py --output repo-contract-report.json
python -m unittest discover -s tests -v
python -m compileall -q host tests tools
git diff --check
```

结果：仓库契约通过；`Ran 64 tests in 10.220s`；`OK`；全部 exit code 0。
这是 `42773d4/aa006c4` 的历史结果，不是后续本地加固的测试计数。

远端代码与说明点 `aa006c4` 已推送；对应
[GitHub Actions run 30862770816](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862770816)
已完成且结论为 `success`。其中 “Host tests and frozen contracts” 与
“PlatformIO release build (hardware not tested)” 两个 job 均通过。

远端分支的最新文档同步点为 `dd711c9`；
[GitHub Actions run 30863009577](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30863009577)
同样成功。本机已将 `dd711c9` 快进合入本地 `main`，并在其上继续进行 RC2B、
帧上传工具、抖动安全契约和 CI/冻结门禁加固。本轮最终本地候选已通过 152 项
回归、repository contract、机器可读测试报告和锁定工具链 clean build；复审开始
时 `origin/main` 仍为 `3033da0`。发布必须核对最终推送 SHA 对应的新 `main` CI，
不能套用上述旧 run。

远端 `dd711c9` 分支本身没有修改 `src/epd_driver.*`；随后的本地 RC2B 集成修改了
驱动源码，但没有修改硬件设计或冻结生产文件，也没有刷写或连接实物。
CI/PlatformIO 成功仅代表主机契约和固件编译成功，始终不是硬件
验收。快速波形/局刷仍受 SPD1657B 与面板 OTP 厂商资料门禁约束；色彩效果仍
需要家中使用实测 D65/2deg 六色 Lab 色板并进行实屏主观验收。

该分支现已由本机审查并合入本地 `main`。主线发布、RC2B 刷写和真屏验收是三个
独立动作：最终推送 SHA 的 CI 仍需单独核对，只有用户明确确认后才安排硬件动作。
