# C5 CI 与回归门禁移交（2026-08-04）

> 下列代码块保存 `feature/host-ci` 原始工作包在 `c59a1f2` 时的历史移交，
> 其中“本机未安装 PlatformIO”、Action v6 和平台未锁定均不是当前状态；当前
> 集成加固与复现结果见后续章节。

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

首次 Linux runner 揭示 manifest 保存的原始 CRLF 指纹与 Git LF checkout 的差异。
检查器现只接受内容相同的 raw/LF/CRLF 三种换行形式，并有双向回归测试；冻结生产
目录未被修改。修正后的 integration run `30860930400` 中 host contract/tests 与
PlatformIO release build 均通过。

## CI 可复现性加固（2026-08-04）

成功的 integration run `30860930400` 实际使用 CPython `3.12.13`、PlatformIO
Core `6.1.19` 与 `platformio/espressif32` `7.0.1`；工作流和
`platformio.ini` 现锁定这些已通过版本。GitHub runner 标签从
`ubuntu-latest` 收窄为 `ubuntu-24.04`。

通过 GitHub REST API 的各仓库 `releases/latest` 与 tag ref 核验后，官方 Action
固定到完整且签名验证有效的 commit SHA，并保留版本注释：

- `actions/checkout` `v7.0.1`：`3d3c42e5aac5ba805825da76410c181273ba90b1`
- `actions/setup-python` `v7.0.0`：`5fda3b95a4ea91299a34e894583c3862153e4b97`
- `actions/cache` `v6.1.0`：`55cc8345863c7cc4c66a329aec7e433d2d1c52a9`
- `actions/upload-artifact` `v7.0.1`：`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`

Repository contract 与 host regression tests 均设置为记录原始 outcome 后继续，确保
contract 失败时测试仍会尽量执行并产生完整诊断；末尾 `Enforce host gates` 会在任一
结果不成功时保持整个 job 失败。Checkout 同时关闭持久化凭据。

主机测试现在由标准库脚本 `tools/run_host_tests.py` 执行，并生成
`host-test-report.json`：记录通过状态、测试/失败/错误/跳过计数、Python 版本和
耗时，固定声明 `hardware_tested:false`，不采集环境变量。CI 的
`host-contract-reports` artifact 始终同时上传该报告与
`repo-contract-report.json`；输出文件已存在时需显式 `--force`，冻结生产目录、
symlink 和 hard-link alias 均被拒绝。

集成复审还固定了 `manufacturing_manifest.json` 自身的基线指纹，并要求冻结目录的
实际文件集合与 manifest 加 manifest 本身完全一致；因此不能通过同时修改 manifest、
替换展开后的制造文件或塞入未登记文件来绕过冻结检查。文本文件仍只对 Git checkout
的 LF/CRLF 等价形式做规范化，ZIP 等二进制文件永不做换行归一化。

当前集成工作树验证结果：repository contract 通过，152 项 unittest 全部通过，
`compileall` 与 `git diff --check` 通过；PlatformIO Core `6.1.19` 按锁定的
Espressif32 `7.0.1` clean build 成功（RAM 45,568 / 327,680 bytes，Flash
795,901 / 3,342,336 bytes）。这些数字对应本轮最终本地候选；发布仍须由最终
推送 SHA 的 GitHub-hosted runner 重新验证，不能套用旧集成提交的 CI 结论。
编译成功不能证明 OPI PSRAM 已在实机启动，也不代表硬件通过。

主机测试 runner 额外采用 fail-closed 语义：零测试、全测试跳过以及 discovery/
runner 抛出的 `SystemExit` 都必须生成失败报告并返回非零。CI 还会独立解析两份
机器报告，要求 kind/schema 正确、至少一项测试真正执行、所有 repository check
通过且 `hardware_tested:false`；仅有 step outcome、缺失报告或格式错误均不能
通过最终门禁。
