# C4A 应用层与 Web UI 移交（2026-08-04）

```text
Work package ID: C4A
Baseline commit SHA: 1b90be5e5d8baa9c4354d05c655efc703e1bf66c
Branch name: feature/application-api-ui
Objective: 提供默认离线、硬件无关的 RGB/RGBA 规范化、既有 C2 六色量化、规范帧复核、可审计报告、设备适配器和轻量 Web UI 骨架。
Files changed: app/__init__.py; app/server.py; host/application/README.md; host/application/__init__.py; host/application/device.py; host/application/images.py; host/application/pipeline.py; host/application/session.py; tests/test_application_device.py; tests/test_application_pipeline.py; tests/test_application_server.py; tests/test_application_web.py; web/app.js; web/index.html; web/styles.css; docs/C4_APPLICATION_HANDOFF_2026-08-04.md
Files intentionally not changed: hardware/mf1750_production_v1/production/ 及全部制造文件；src/epd_driver.cpp；src/epd_driver.h；src/epd_config.h；src/main.cpp；platformio.ini；tools/mf1750_frame_tool.py；MF-1750 初始化/CCSET/高压/BUSY/PON/DRF/POF/PSR；R15/R16/GPIO/controller mapping；快速波形、LUT、局刷和 SPI 扫频代码；Wi-Fi 凭据、token 和真实图片。
Architecture: host/application/images.py 提供无第三方依赖的 RGB/RGBA RasterImage 适配和 contain/cover/stretch 规范化，Pillow 仅是惰性可选解码器；pipeline.py 只调用 host.color_pipeline.quantize_panel_image，并在输出前重新调用 host.epd_frame.validate_frame；device.py 定义 DeviceAdapter、默认 OfflineAdapter 和显式 HttpDeviceAdapter，后者直接复用 mf1750_frame_tool 的 RC2B/V2 version、frame、job、diagnostic 严格校验；session.py 管理 UI 刷新锁、终态、网络恢复和本地中止；app/server.py 是仅允许 loopback 的标准库服务；web/ 是无构建链 HTML/CSS/JavaScript UI。
Security boundaries: 默认 OfflineAdapter 没有网络请求能力；HTTP adapter 需要启动时同时提供 --enable-device/--device-url、UI 显式 allow、当前不可变 artifact/mapping 的 version preflight、120 秒一次性精确 arm 和正式 calibrated C2 v2 报告；bind 与每次 enqueue 都重建并完整校验 frame/report/authorization identity；只允许 GET /api/version、POST /api/diagnostic/frame-ingress、POST /api/frame、GET /api/job、GET /api/diagnostic/report 的固定设备 method/route 组合；URL 中的凭据、额外路径、query 和 fragment 被拒绝；loopback Web API 每次启动生成高熵 token，只通过打印 URL 的 fragment 交给浏览器，严格校验 numeric Host、same-origin Origin 与 Sec-Fetch-Site，所有 application API 需要 token；legacy white/black/test/solid 与任意路径不能到达 requester；未校准 reference palette 只能生成明确标记的 offline preview；HTTP 202、completed job 和 diagnostic report 是三个独立门禁；远端取消明确为 unsupported；本地中止不声称取消设备；所有报告固定 hardware_tested:false。
Assumptions: 输入 RasterImage 是 top-left row-major、紧密 8-bit IEC sRGB RGB 或 straight-alpha RGBA；透明像素继续由 C2 在线性光合成到白底；浏览器上传的原文件 SHA256 是浏览器声明值，服务端实际量化的规范化 RGBA 另有本地计算 hash；正式上传 palette 必须保留 C2 schema v2 的 calibrated provenance；设备协议保持精确 RC2B build tag、MF1750_R16_CASCADE_V2 API 和现有 frame tool 契约；物理 mapping 只作为显式预期值交给现有工具核对，不修改应用帧。
Commands run: git fetch origin --prune; git fetch origin main; git -c http.version=HTTP/1.1 -c http.curloptResolve=+github.com:443:140.82.116.3 fetch origin main; git rev-parse origin/main; git switch -c feature/application-api-ui 1b90be5e5d8baa9c4354d05c655efc703e1bf66c; Get-Content -Raw -Encoding UTF8 <全部指定文档>; python -m unittest discover -s tests -p "test_application_*.py" -v; python tools/run_host_tests.py --output host-test-report.json --force; python tools/check_repo_contract.py --output repo-contract-report.json; python tools/validate_ci_reports.py; python -m compileall -q host app tests tools; node --check web/app.js; python -m app.server --help; git diff --check
Exact test output / exit codes: 首次基线 fetch 因 GitHub 中国边缘连接失败（Empty reply / connection reset，exit 1），改用可达 GitHub 边缘解析后 fetch 成功（exit 0），origin/main=1b90be5e5d8baa9c4354d05c655efc703e1bf66c；开发期首次 C4A 专项为 Ran 19 tests in 11.021s、FAILED (failures=1, errors=8)、exit 1，原因是适配器 requester 签名和一项 UI 文案断言；初始骨架修复后为 22 项/全仓 174 项；安全复审加固后的最终结果为 C4A 专项 48/48、全仓 200/200，均 OK、exit 0；repository contract passed=true、hardware_tested=false、6 组检查通过，保留一条既有 manifest warning、exit 0；machine report validator、compileall、node --check、git diff --check 和 app.server --help 均 exit 0。
Tests not run because environment was missing: 未运行 Playwright/Selenium 等真实浏览器自动化：当前仓库没有浏览器自动化 harness，系统也没有 playwright 命令；若集成环境已有依赖和测试配置，理论命令为 npx playwright test，按任务要求本次未安装或搭建。未运行 PlatformIO：系统没有 platformio 命令，且本工作包未修改 firmware/platformio.ini；理论命令为 platformio run，按任务要求未安装。Pillow 在当前环境可用，optional Pillow synthetic PNG decode 测试已执行通过，因此不属于缺失项。
Hardware tested: NO
Known limitations: 默认 reference-srgb-v1 calibrated=false，因此默认 UI 只生成离线预览且刷新按钮不会获得正式上传授权；纯 Python CIEDE2000 整屏照片可能耗时数十秒；浏览器 Canvas 负责图片解码/EXIF 和生成规范 RGBA，其原文件 hash 是客户端声明，跨浏览器像素解码一致性尚无自动化证明；Python core 的 synthetic raster 路径是确定性的；HTTP adapter 为避免弱化判断直接调用 mf1750_frame_tool 的内部严格校验函数，未来工具重构需同步审查；RC2B/V2 没有远端 cancel 路由；job/recovery 状态只保存在当前 Python 进程，服务异常重启后不能自动恢复在途远端 job，因而必须先人工核对设备状态，不能直接重新提交；请求体有 1 秒 inactivity timeout，但没有跨多个慢分片的总连接期限；loopback token 只保护本地应用会话，ESP32 固件 API 本身仍无认证，因此设备仍只应位于可信隔离网络；palette canonical hash 与 calibration artifact SHA256 是审计指纹而非签名或 trust store；未做真实浏览器交互、设备 HTTP、真屏、BUSY、电流、CV 或温度验证。
Risks requiring integrator review: 重点复核 measured palette 的 calibration artifact 与 calibrated 标记，防止错误色表获得上传授权；复核 final D0 controller mappings 并由用户显式填写，应用层没有也不得补偿镜像/翻转/nibble；mf1750_frame_tool 私有校验函数属于有意复用但有维护耦合；设备端当前无应用认证，正式发布前仍需 token/一次性 device-side arm 或关闭危险 legacy 路由；浏览器端原图 hash 的声明边界、Canvas 解码一致性和大图性能需要集成环境浏览器测试；任何 protocol_verified 仍必须保留 screen/CV/current/temperature 人工门禁。
Suggested merge order: 当前 baseline 已含 C1/C5/C2 与 RC2B 软件候选；先审查并合入 C4A 的纯应用代码，D0 真屏与 H0 封存完成前保持设备功能禁用；之后再由集成负责人用 calibrated palette 和受控设备环境执行 C4/C2 端到端验收。不得由本分支推进 C3、R1/R2、H0 或 Rev B。
Final commit SHA: 该字段所在文件提交后 SHA 才能确定，无法在同一 Git commit 内自引用；以 feature/application-api-ui 远端 branch tip 为准，精确 SHA 同时写在本次最终回复中。
```

## C4A 安全加固复审

对初始远端提交 `653a5ba507b6f0fa66eb17b7902a32100ee7e7c4` 的对抗复审发现并已修复以下问题：

- `ApplicationArtifact` 现在使用无别名 bytes/JSON 快照与 slots；bind 和每次 enqueue 都从当前字段重建安全快照，完整复核 C2 schema v2、quantization report integrity、palette canonical hash、measurement/artifact provenance、formal purpose、帧 SHA256/FNV-1a 和授权字段。低层属性改写也不能把 reference preview 变成正式上传。
- artifact identity 固定包含 frame SHA256、FNV-1a、307200 字节长度和 application report SHA256；替换或清除 artifact 会撤销 preflight、arm、job、diagnostic 与旧 protocol evidence。
- preflight、mapping 和 firmware version 被移入 120 秒 one-shot arm；任何 enqueue 尝试都会消费它。job 与 diagnostic 使用内部深拷贝并重新核对私有 job ID/frame hash；最终报告保留完整 preflight、原始 BUSY/timing 诊断和正式 verified scope。
- loopback Web 服务每次启动生成 URL-safe 高熵 token，并只在打印 URL 的 fragment 中交付；API 严格校验 numeric Host、token、same-origin Origin/Sec-Fetch-Site，禁止 query，副作用 job/report 已改为 POST，并拒绝 iframe 嵌入。
- 请求体读取有短超时且不占设备操作锁；图像量化在锁外执行，generation epoch 防止失效后的旧转换覆盖新状态。status 在可用时持同一操作锁形成线性快照，慢设备占锁时则立即返回 fail-closed 状态；UI 自动等候操作完成。UI 在文件/fit/dither/palette/text/white 变化时撤销旧 artifact，页面重载会清除无可见预览的 inactive artifact，并只按服务端状态恢复 queued/running/completed_pending_report/network_error。

以上全部是 synthetic/mock/loopback 验证，不构成真实 ESP32、屏幕、电源或温度验收。

## 最终复现结果

最终提交前在仓库根目录执行：

```powershell
python -m unittest discover -s tests -p "test_application_*.py" -v
python tools/run_host_tests.py --output host-test-report.json --force
python tools/check_repo_contract.py --output repo-contract-report.json
python tools/validate_ci_reports.py
python -m compileall -q host app tests tools
node --check web/app.js
git diff --check
```

结果：C4A 专项 `Ran 48 tests`、`OK`、exit 0；全仓机器报告
`tests_run=200`、`tests_executed=200`、`failures=0`、`errors=0`、
`skipped=0`、`passed=true`、`hardware_tested=false`；其余命令均 exit 0。

新增测试全部使用 synthetic raster 或内存 scripted requester。测试中的
`http://device.invalid` 只作为被注入 requester 的不解析字符串；没有打开 socket、
访问局域网或调用真实 `/api/frame`。最终精确计数与退出码在提交前最后一次运行后
记录到本节及最终回复。

## 操作边界

默认启动：

```powershell
python -m app.server
```

只创建 `OfflineAdapter`。即使显式启用 HTTP adapter，进程启动也不发送请求：

```powershell
python -m app.server --enable-device --device-url http://DEVICE-IP
```

必须打开服务打印的完整 `http://numeric-loopback:port/#token=...` URL；fragment
不会发送给 HTTP 服务，页面会把 token 保存到同源 `sessionStorage` 后从地址栏移除。
随后仍必须在 UI 中先允许连接，再填写两项 mapping、通过 preflight、输入精确
`ARM MF1750 REFRESH` 并执行一次性 arm。未校准 palette 不会启用刷新。HTTP 202
后 UI 保持锁定，只有 matching completed job 和 matching diagnostic operation
全部验证后才显示 `protocol_verified`；`hardware_tested` 永远保持 `NO`。
