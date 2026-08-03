# 主机帧与快速刷新集成候选（2026-08-04）

> 本文记录 C1 + R1/R2 的早期 37-test 集成快照。包含后续 C5 与 C2、并已
> 通过 64 项联合回归的最新候选见
> [`HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`](HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md)。

```text
Baseline commit SHA: 3033da0
Integration branch: integration/host-fast-refresh
Merged branches: feature/host-frame-core @ cb0a03f; research/fast-refresh @ b03b7e1
Merge commits: 286e022; 18ae8c0
Files intentionally not changed: src/, hardware/, platformio.ini, frozen production files
Command: python -m unittest discover -s tests -v
Exact result: Ran 37 tests in 8.529s; OK; exit code 0
Hardware tested: NO
```

该分支是家中集成候选，不代表 D0、SPI 高频或快速/局部波形已经实屏通过，且未合并
到 `main`。建议家中先验收 `main` 上的 D0，再审查并合并本分支；涉及 `src/` 的
参数化 SPI 诊断和任何厂商支持的快速波形实验应另开硬件分支。

