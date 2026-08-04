# C1 主机帧格式核心移交（2026-08-04）

> 下列代码块是 `cb0a03f` 原始 C1 分支的 18-test 历史移交；当前集成
> 加固与联合回归结果见文末，所有结果都不代表硬件验收。

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

## 集成收口补充

`EXPECTED_FIXTURE_HASHES` 的三项顺序明确为完整帧、逻辑左半、逻辑右半；
`FixtureReport` 使用 `logical_left_fnv1a` / `logical_right_fnv1a`，不再把默认
拆分误称为物理 CS1/CS2。帧工具直接复用本包，并对设备刷新执行当前 RC2C/V3/PSRAM
预检、202 job 终态与哈希核对、diagnostic job 关联、显式 mapping 后的双 DTM
哈希核对，以及 BUSY/安全收尾检查。全部网络测试均为 mock，不包含硬件访问。

刷新操作不允许沿用设备自报 mapping 作为期望值：调用方必须显式提供两项
`--controller-mapping`，严格按 CS1、CS2 顺序排列；未提供 mapping 的模式仅限
离线报告和不触发 EPD 的 ingress。工具会先使用规范 `validate_frame` 完整检查
长度与全部色码，失败时不解析 URL、也不发出网络请求。刷新预检还要求
`/api/version` 提供 `Refresh SPI Hz: 1000000`，以及格式为
`source_half,flip_x,flip_y,nibble_swap`（四项均为 0/1）的 `CS1 Mapping` 和
`CS2 Mapping`；三者任一缺失或与显式期望不符，都在 `/api/frame` POST 前终止。
刷新结束后仍会再次独立核对 diagnostic mapping 与双 DTM 哈希。

正式 PASS 还要求 ingress 响应显式包含 `epd_action:"none"`。刷新 diagnostic
必须提供 `pon_ms`、`drf_ms`、`pof_ms`、`post_psr_ms` 及对应四项
`*_busy_seen` 采样；PON/DRF/POF 必须为 `true`，POF 后 PSR 寄存器写入的采样
仅作信息证据并允许为 `false`。其中 `drf_ms` 必须处于 10000..60000 ms，
`last_wait_ms` 必须等于 `post_psr_ms`，且 `total_ms` 不得短于两次 controller
upload 与四段记录等待的耗时总和。仅有 `sequence_ok` 或最终阶段名称不构成 PASS。

所有工具 JSON 均显式声明 `hardware_tested:false`。离线自检使用
`offline_verified`，网络链路使用 `protocol_verified`，并通过 `verified_scope`
列出实际证明范围，不再使用可能被误解为硬件验收的无范围 `verified`。刷新报告
同时列出仍需人工确认的完整屏幕视觉结果、电源 CV/电流与 L1/L2 温度；协议 PASS
不能替代这些实物观察。

已完成 `/api/job` 的 `queued_at_ms`、`started_at_ms`、`finished_at_ms` 必须为
按队列、开始、完成顺序推进的 u32 时间戳（支持正常 `millis()` 回绕）；diagnostic
wrapper 中对应的 `job_queued_at_ms`、`job_started_at_ms`、`job_finished_at_ms`
还必须与该 completed job 精确相等，防止复用旧报告。schema v2 同时要求非零
u32 `operation_id`；job wrapper 的 `job_operation_id` 也独立要求为非零 u32，
任一字段缺失、为布尔值、0、负数或越界都不能进入协议 PASS，随后两者还必须
精确一致；同时
`busy_assertion_missing` 必须为 `false`、`busy_missing_stage` 必须为 `none`。

刷新 build gate 使用工具内的完整标签精确 allowlist，不接受前缀、后缀或
`NOCOLORGUARD` 等 substring 伪匹配；失败仍止于 version GET。畸形 IPv6/URL
解析错误统一包装为 `FrameToolError`。输出保护除路径检查外，还会在 `--force`
前使用 `samefile` 拒绝冻结生产目录中任一文件的 hard-link alias。

2026-08-04 RC2B 真屏证明 MAP_ORIENT_V1、PON/DRF/POF BUSY 与双 DTM 哈希
正确，同时证明 POF 后的 PSR 写入不会再次 assert BUSY。精确 allowlist 已提升为
`MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04`，
driver API 为 `MF1750_R16_CASCADE_V3`。主机工具协议报告仍只使用
`protocol_verified`，不会把 mock 或协议检查冒充完整硬件验收。
