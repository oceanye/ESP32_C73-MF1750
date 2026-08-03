# C1 主机帧格式核心移交（2026-08-04）

```text
Work package ID: C1
Baseline commit SHA: 3033da0
Branch name: feature/host-frame-core
Objective: 提供无第三方依赖的规范 1024x600 4bpp 主机帧核心、fixtures 与回归测试。
Files changed: host/epd_frame/, host/__init__.py, tests/, docs/C1_HOST_FRAME_HANDOFF_2026-08-04.md
Files intentionally not changed: src/, hardware/, platformio.ini, 冻结生产文件
Assumptions: 应用帧保持 row-major；偶数 x 为高 nibble；物理色码为 0/1/2/3/5/6。
Commands run: python -m unittest discover -s tests -v; git diff --check
Exact test output / exit codes: 18 tests; Ran 18 tests in 8.793s; OK; exit code 0
Hardware tested: NO
Known limitations: 本包只验证字节契约与参考映射，不宣称屏幕方向、颜色或刷新通过。
Risks requiring integrator review: MAP_ORIENT_V1 实屏验收后，需确认固件中的最终 CS1/CS2 flip-Y 配置。
Suggested merge order: D0 baseline -> C1 -> C5
```

## 验收命令

在仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
```

测试覆盖：

- 4bpp pack/unpack 与偶数/奇数 x 的 nibble 顺序；
- full-frame 按行拆分 CS1/CS2；
- source-half、flip-X、flip-Y、nibble-swap 全部 16 种组合；
- `global-v-bars`、`global-h-bars`、`MAP_ORIENT_V1` 的完整帧与双 DTM FNV-1a；
- MAP_ORIENT_V1 六色像素计数；
- 奇数宽度、控制器宽度、非法色码、像素数量和截断数据错误路径。

