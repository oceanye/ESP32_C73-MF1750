# C5 CI 与回归门禁移交（2026-08-04）

```text
Work package ID: C5
Baseline commit SHA: cb0a03f (C1), based on main 3033da0
Branch name: feature/host-ci
Objective: 自动检查主机帧、冻结生产文件、固件静态契约与 PlatformIO release build。
Files changed: .github/workflows/ci.yml, tools/check_repo_contract.py, tests/test_repo_contract.py, docs/C5_HOST_CI_HANDOFF_2026-08-04.md
Files intentionally not changed: src/, hardware/, platformio.ini, frozen production files
Assumptions: GitHub-hosted ubuntu runner；Python 3.12；PlatformIO 按官方 GitHub Actions 集成方式安装。
Commands run: python tools/check_repo_contract.py; python -m unittest discover -s tests -v; python -m compileall -q host tools tests; git diff --check
Exact test output / exit codes: repository contract passed=true; 23 tests; Ran 23 tests in 8.606s; OK; exit code 0
Hardware tested: NO
Known limitations: 本机按要求未安装 PlatformIO，固件构建由 GitHub runner 首次验证；静态上传契约检查不能替代设备端 HTTP 集成测试；制造 manifest 中 PCB下单与首板检查.md 的记录早于 baseline 3033da0，检查器同时锁定旧 manifest 元数据与当前 baseline blob，并报告 warning。
Risks requiring integrator review: actions/checkout@v6 和 setup-python@v6 要求较新的 Actions runner；PlatformIO 平台依赖尚未锁定版本。
Suggested merge order: D0 baseline -> C1 -> C5
```

工作流将“编译通过”和“硬件通过”明确分开；固件 job 名称包含
`hardware not tested`，机器报告也固定输出 `hardware_tested: false`。
