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
Exact test output / exit codes: initial C5 commit bbad4a4: repository contract passed=true; 23 tests; Ran 23 tests in 8.606s; OK; cross-platform fix c59a1f2 adds the LF/CRLF regression and passes 24 branch tests; exit code 0
Hardware tested: NO
Known limitations: 本机按要求未安装 PlatformIO，固件构建已由 GitHub runner 验证；静态上传契约检查不能替代设备端 HTTP 集成测试；制造 manifest 中 PCB下单与首板检查.md 的记录早于 baseline 3033da0，检查器同时锁定旧 manifest 元数据与当前 baseline blob，并报告 warning。
Risks requiring integrator review: actions/checkout@v6 和 setup-python@v6 要求较新的 Actions runner；PlatformIO 平台依赖尚未锁定版本。
Suggested merge order: D0 baseline -> C1 -> C5
```

工作流将“编译通过”和“硬件通过”明确分开；固件 job 名称包含
`hardware not tested`，机器报告也固定输出 `hardware_tested: false`。

## 远端验证（2026-08-04 更新）

- 最终 C5 分支：`feature/host-ci` @ `c59a1f2`；
- 跨平台修复将文本指纹限定为原始/LF/CRLF 等价形式，二进制冻结文件仍要求
  精确字节匹配；
- C5 分支 [Actions run 30860921228](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30860921228)
  成功；
- 完整集成 [Actions run 30862770816](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30862770816)
  成功。两者都只代表主机回归与固件编译成功。
