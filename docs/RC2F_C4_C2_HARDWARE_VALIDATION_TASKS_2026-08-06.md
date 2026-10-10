# RC2F / C4 / C2 上机验证任务包（2026-08-06）

> 历史任务包：RC2F 已执行的内容和证据继续有效，但不再作为 2026-08-07 晚间
> 操作指令。当前使用
> [`MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md`](MF1750_RC2G_EVENING_HARDWARE_CAMPAIGN_2026-08-07.md)。
> 若下文存在“每次成功刷新之间例行断电”的旧表述，以新策略为准：成功且 safe-finish、
> GPIO、电气和温度均正常时可保持持续监督上电；刷写/重启、异常或会话结束时才切断。

状态：`RC2F MAP BASELINE COMPLETE / G1-S1 DRF INCIDENT RECOVERED / DEVICE POWER OFF / NEW ACTION NOT AUTHORIZED`

本文件把“满足安全门禁后可以上机验证的候选”与“仍缺软件或测量输入的路线图任务”分开。
它不构成刷写、上电、HTTP 刷新或连续测试授权。真正开始时，每个可见刷新任务仍需
用户当次确认；一次确认只覆盖一个明确任务，不自动覆盖后续任务。

## 0. 2026-08-06 实际执行结果

- RC2F 固件按第 2 节精确 bytes/SHA 刷写，Wi-Fi、网页、PSRAM、1 MHz、mapping 和
  non-displaying ingress 通过；
- 固定 `map-orient-v1` 基准在 job1/op1 完整通过；
- 首个独立 G1/S1 `area-weighted-ordered-8x8` 候选在 job2/op2 的 DRF 60010 ms
  超时，POF cleanup 30005 ms 未闭环；用户实体断电，授权永久消费，算法结论
  `inconclusive`；
- 冷却和证据审查后，固定 MAP recovery job3/op3 以 181/21700/140/5 ms 完成
  PON/DRF/POF/post-PSR，总时长 34178 ms；真屏、电流、温度、TP1 与断电 GPIO 通过；
- 当前 J2-P1 保持断开。以上不授权 T4/T5 重跑、下一算法、R1 扫频或正式 C2/C4 刷新。

## 1. 软件完成度结论

不能笼统地说“全部软件任务已完成”。当前状态为：

| 工作包 | 软件状态 | 现在能否上机 | 剩余工作 |
|---|---|---|---|
| D0 / C1 | 完成；RC2C 已正式验收，RC2F 固定 MAP 基准与事故恢复已通过 | 已执行完毕，当前断电 | 高负载事故根因另行隔离，不重跑已消费 recovery |
| C2 六色量化 | 核心算法、schema v2、严格 palette 门禁完成 | 否（本轮） | 冻结测量/聚合合同、D65/2° 六色测量、生成 calibrated palette、真屏评价 |
| C4 应用/Web | 主机应用、浏览器 UI、HTTP adapter、一次性 arm、job/report 校验及 local-abort 隔离锁完成 | 部分 | 真实浏览器/设备 E2E；正式刷新依赖 calibrated palette |
| 设备/系统加固 | 监督式调试所需基础路由完成 | 部分 | 设备端认证/TLS、远端 cancel、持久 job/latch、分块上传、通用严格 frame 输入及自动证据采集仍未实现 |
| C5 CI | RC2F 构建通过；事故恢复加固工作树 394 项 unittest、仓库合同、compileall 与 JS syntax 通过 | 不涉及硬件 | 当前 394 项仍待 Python 3.12/远端 CI 和正式 report 刷新 |
| G1 色域映射 | 显示器模拟完成；首个 ordered 真屏候选 DRF 超时、结论不确定；固定 MAP 恢复通过；v2 永远 offline | 否（下一 run 未授权） | 先做低空间频率负载诊断设计与根因隔离，再补 measured profile/qualification |
| C3 转移优化 | 保守区域/统计规划器完成；优化器未实现 | 否 | 可信旧帧状态、6×6 实测矩阵、优化器实现 |
| N0–N6 网络随机照片 | 仅 TODO 与安全边界完成 | 否 | 数据源、下载/去重/持久历史、认证投递、调度实现 |
| R1 SPI 扫频 | 离线 schema v2 分析器完成 | **否** | 固件缺少受限 `map_orient_v1_sweep` action；当前禁止测试 >1 MHz |
| R2 快速波形/局刷 | 研究边界和控制器中立规划器完成 | 否 | SPD1657B/OTP 一手资料；取得前禁止实装 |
| EC0–EC9 扩色 | 离线 schema、台账、固定资产和模拟工具已完成一部分 | 否 | 隔离实验固件、安全链、测量资格及逐阶段授权；EC8 仍 HARD BLOCKED |
| S1 空间半色调 | 经典软件基线完成；首个高空间频率 ordered run 在 DRF 超时，不能判算法 PASS/FAIL | 否（下一 run 未授权） | 低空间频率对照、每色实测核、相机闭环、独立真屏 qualification |
| H0 | Git 源码/证据归档已生成但仍是 partial | 不涉及硬件 | 找回 RC2C 精确二进制、持久异机副本、授权后 tag |
| H1/H2 | H1 只读分析完成；H2 未设计 | 仅可测量 H1 输入 | 电流/温升/轨波形/机械输入；之后再决定 H2 |

因此，本轮上机范围只包含：

1. RC2F 的无刷新预检和正式 1 MHz MAP 最小回归；100 kHz 只作可选诊断；
2. RC2F 设备内置网页在 J2-1 断电状态的交互/预览检查；当前不从该页面刷新；
3. C2/T7 本轮只保留未来任务设计；测量合同冻结前不执行 pilot 或正式刷新；
4. calibrated palette、C4 frozen tree 和其余门禁完成前，C4 普通图片刷新保持 BLOCKED。

## 2. 固定候选身份

本任务包只适用于以下当前候选：

```text
Git HEAD at preparation: 172840c091bd963633860b5dfde6f327d30ab665
Firmware build tag:
MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05
Driver API: MF1750_R16_CASCADE_V3
firmware.bin bytes: 811056
firmware.bin SHA-256:
AE5261AA2E679B4AEA11C9C4C2CE5D12BD561EC72748828ECC5BA570A03A4A20
Default SPI: 1000000 Hz
CS1 mapping: 0,0,0,0
CS2 mapping: 1,0,0,0
MAP_ORIENT_V1 full FNV-1a: 2634290221 / 0x9D04142D
CS1 DTM FNV-1a: 4066915037 / 0xF26832DD
CS2 DTM FNV-1a: 4263092213 / 0xFE199FF5
```

若重新构建后的二进制大小或 SHA-256 不同，停止刷写并先审查差异。不得仅因 build
tag 字符串相同就把不同字节视为同一候选。`firmware.bin` 可能包含本地 Wi-Fi 配置，
只记录大小与 hash，不把二进制复制进 Git、公开报告或无保护共享目录。

RC2F 是新候选，不能继承 RC2C 的实机结论。当前无法重新刷回“精确已验收 RC2C”：
其 796272 字节原始二进制缺失、重编 hash 不匹配，而且当前主机工具 allowlist 只接受
RC2F。因而本任务是 RC2F 的独立回归，不是 RC2C 复现。

另外，2026-08-06 的 C4 local-abort quarantine 修正和本任务包目前仍在未提交工作树；
HEAD `172840c` 不包含这些最新主机变更。T0–T5 的固件文件相对 HEAD 未改，可按上述
固件身份冻结；执行 T8 前必须先把 C4 变更审查并形成明确 commit，不能用模糊 dirty
状态形成正式应用层硬件证据。

## 3. 全程硬件边界与停止条件

开始前必须确认：

- Rev A1 保持 R15 拆除、R16=0 Ω；R15/R16 禁同时安装；
- J2-9 确实接 GPIO10；CS1=GPIO7、CS2=GPIO10；
- FPC 方向和接触面正确，禁止带电插拔；所有逻辑均为 3.3 V；
- ESP32 USB 与 J2-1 面板 3.3 V 可独立通断；物理切断 J2-1 的手段在手边；
- 外部链路具备 OVP/OCP/硬件限流、默认断开的 J2-1 开关、实体切断和输入电流监测；
  实体切断先在假负载验证切断、残压和人工复位；
- TP1 目标为 3.30 V；整个 job 必须满足 `Vmeas-U95≥2.4 V` 且
  `Vmeas+U95≤3.6 V`；
- OVP、OCP、硬件限流和输入绝对停止阈值必须形成带版本和审查人的数值 profile，并
  先用假负载验证。此前 D0 的 1 A 最高 ceiling 不得提高，但 1 A 不是已证明的安全
  额定值，不能仅凭“设为 1 A”签署 GO；进入 CC 或超过已批准阈值即停止；
- 使用可信隔离网络：设备不得暴露到公网或不受控 LAN，不做端口转发，现场只有记录
  在案的测试主机可访问。设备端目前没有认证/TLS，隐藏 IP 不是安全措施；
- 每次可见刷新之间 J2-1 断电至少 10 秒；下一次上电前确认温度恢复；
- 串口、PSU 状态、输入电流和关键温度能够同时观察；不会因拍照或操作浏览器而失去监控。

每个可见 run 必须有两个不能合并的当次授权：先在断电预检和 profile hash 核对后，
授权仅为该 run 接通 J2-1；上电后确认 TP1/CV/current/temperature、设备 idle 和精确
build/action/frame/mapping 均正确，再取得第二次授权，且第二次只允许一个精确 POST。
上电授权不等于 POST 授权，任务级或前一 run 的授权均不得复用。

任一条件出现立即停止，不自动重试：

- PSU 离开 CV、进入 CC/OVP/OCP，ESP32 重启或 USB 断连；
- PON/DRF/POF 任一阶段未在 250 ms 内观察到 BUSY；job/report/hash/operation 不匹配；
- 任一点实测达到 45℃时不再开始新 job；面板
  `Tmeas+U95+sensor_lag_margin≥50℃`、超过已批准器件温限或出现快速热点时立即硬件切断；
- 异响、异味、烟、弧光、裂纹、永久色斑、左右半屏异常恶化时立即实体急停并隔离；
- 网络在 `/api/frame` 提交后中断：禁止再次 POST，先查 `/api/job` 和 immutable report；
- 日志、测量或照片证据丢失；该 run 作废并停止后续。

断电后，接触、改线或重上电前确认 TP1/J2-1 `≤0.10 V` 持续 `≥5 s`。扩展颜色、
未知码或高压测量还必须
满足独立安全门；本文件不能替代该门禁。

当前安全台账仍把外部急停验证和绝对电流门标为未完成。因此当前默认
`VISIBLE_REFRESH_GO=NO-GO`。只有急停在代表性假负载下至少三次通过，电压/电流/
温度测量链资格可追溯，并且数值 limit profile 经审查后才能改为 GO。仅把任意数值
填进记录表不构成放行；放行前只允许 T0、T2 的 J2-1 断电刷写及 T3 无刷新检查，
T4–T8 一律 NO-GO。

## 4. 会话目录与记录模板

在同一 PowerShell 窗口建立被 Git 忽略的会话目录：

```powershell
$TestRoot = ".test-output\hardware\RC2F_$(Get-Date -Format yyyyMMdd_HHmmss)"
$PioExe = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
New-Item -ItemType Directory -Path $TestRoot | Out-Null
Copy-Item templates\MF1750_RC2F_HARDWARE_SESSION_TEMPLATE.md `
  (Join-Path $TestRoot "SESSION.md")
Copy-Item templates\MF1750_RC2F_HARDWARE_SESSION_TEMPLATE.md `
  (Join-Path $TestRoot "SESSION-TEMPLATE-SOURCE.md")
Copy-Item templates\MF1750_VISIBLE_REFRESH_LIMIT_PROFILE_TEMPLATE.md `
  (Join-Path $TestRoot "LIMIT-PROFILE.md")
Copy-Item docs\RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md `
  (Join-Path $TestRoot "RUNBOOK.md")
git rev-parse HEAD | Set-Content -Encoding utf8 (Join-Path $TestRoot "git-head.txt")
git status --short | Set-Content -Encoding utf8 (Join-Path $TestRoot "git-status.txt")
Get-FileHash -Algorithm SHA256 `
  docs\RC2F_C4_C2_HARDWARE_VALIDATION_TASKS_2026-08-06.md, `
  templates\MF1750_RC2F_HARDWARE_SESSION_TEMPLATE.md, `
  templates\MF1750_VISIBLE_REFRESH_LIMIT_PROFILE_TEMPLATE.md `
  | Select-Object Path,Hash | ConvertTo-Json `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "procedure-source-sha256.json")
```

不要把设备 IP、Wi-Fi SSID/密码或应用 token 写入需要提交/共享的报告。

## 5. T0：离线候选冻结（无设备 I/O）

状态：`READY`。

```powershell
python -m unittest discover -s tests -t . -q `
  2>&1 | Tee-Object -FilePath (Join-Path $TestRoot "T0-unittest.log")
if ($LASTEXITCODE -ne 0) { throw "T0 STOP: unittest failed" }
python tools\check_repo_contract.py --output (Join-Path $TestRoot "T0-contract.json")
if ($LASTEXITCODE -ne 0) { throw "T0 STOP: repository contract failed" }
& $PioExe run -e esp32-s3-devkitc-1 `
  2>&1 | Tee-Object -FilePath (Join-Path $TestRoot "T0-platformio-build.log")
if ($LASTEXITCODE -ne 0) { throw "T0 STOP: PlatformIO build failed" }
$Firmware = ".pio\build\esp32-s3-devkitc-1\firmware.bin"
(Get-Item -LiteralPath $Firmware).Length `
  | Set-Content -Encoding ascii (Join-Path $TestRoot "T0-firmware-size.txt")
(Get-FileHash -LiteralPath $Firmware -Algorithm SHA256).Hash `
  | Set-Content -Encoding ascii (Join-Path $TestRoot "T0-firmware-sha256.txt")
python tools\mf1750_frame_tool.py --pattern map-orient-v1 `
  --controller-mapping 0,0,0,0 `
  --controller-mapping 1,0,0,0 `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T0-map-offline.json")
if ($LASTEXITCODE -ne 0) { throw "T0 STOP: offline MAP verification failed" }
```

通过条件：全部 discovered tests 通过（本文准备时为 366 项；事故恢复加固后为 394 项）、repository contract
`passed=true`、构建成功、二进制身份
与第 2 节完全一致、离线 MAP report 为 `offline_verified=true`。任何不一致先停在 T0。

## 6. T1：物理与电气预检（仍不刷写、不刷新）

状态：`READY FOR MANUAL CHECK`。

在 `SESSION.md` 中逐项记录：

先填写并审查同一会话目录中的 `LIMIT-PROFILE.md`；该文件的空白默认值全部是 NO-GO，
不能通过删除 `TBD` 或把表格中的 `NO-GO` 改字样来代替证据。

1. 板号/面板序列号、R15/R16、FPC、J2 引脚和公共 GND；
2. J2-1 断电及 TP1 电压；
3. 经审查的 limit profile ID/版本/审查人，电压、OVP/OCP、硬件限流、输入绝对停止
   阈值，以及假负载至少三次急停结果；
4. 电压/电流/温度测量链资格、U95、温度传感器滞后余量，以及环境温度和
   Q1/Q2/L1/L2、控制器区、面板测点；
5. COM8 只连接 ESP32，驱动板 J2-1 保持断电。
6. 隔离网络边界、测试主机身份、现场无其他客户端且无公网/端口转发。

项目 1、2、5 以及“无外部反向供电”无法确认时不得进入 T2。项目 3、4 未完成时，
`VISIBLE_REFRESH_GO=NO-GO`，但不阻止保持 J2-1 断电的 T2/T3。

T1 必须分别给出两个结论：`FLASH_AND_NO_REFRESH_GO` 与 `VISIBLE_REFRESH_GO`。前者只需
确认 J2-1 可靠断开且无反向供电；后者还必须引用已审查的数值 limit profile、合格的
电压/电流/温度测量链、三次急停证据和隔离网络记录。任一数值仍为 TBD/PENDING 时
只能签 NO-GO。

Reviewer 完成 `LIMIT-PROFILE.md` 后、首次可见上电前冻结其字节身份：

```powershell
$LimitProfilePath = Join-Path $TestRoot "LIMIT-PROFILE.md"
$LimitProfileShaPath = Join-Path $TestRoot "LIMIT-PROFILE.sha256"
$ApprovedLimitProfileSha256 = `
  (Get-FileHash -Algorithm SHA256 -LiteralPath $LimitProfilePath).Hash.ToLowerInvariant()
$ApprovedLimitProfileSha256 `
  | Set-Content -Encoding ascii -LiteralPath $LimitProfileShaPath
Set-ItemProperty -LiteralPath $LimitProfilePath -Name IsReadOnly -Value $true
```

把该 hash 写入 `SESSION.md` 的 T1b 和 reviewer 记录。每个可见 run 的上电授权前、精确
POST 授权前都重新执行以下核对，并把 hash 写入该 run；任一次不匹配就 NO-GO。需要
修改 profile 时必须结束本会话、递增 profile 版本并重新审查，不能原地解锁修改：

```powershell
$ApprovedLimitProfileSha256 = `
  (Get-Content -Raw -LiteralPath $LimitProfileShaPath).Trim().ToLowerInvariant()
$CurrentLimitProfileSha256 = `
  (Get-FileHash -Algorithm SHA256 -LiteralPath $LimitProfilePath).Hash.ToLowerInvariant()
if ($CurrentLimitProfileSha256 -ne $ApprovedLimitProfileSha256) {
  throw "VISIBLE REFRESH STOP: limit profile hash changed"
}
```

## 7. T2：J2-1 断电刷入 RC2F 与启动记录

状态：`READY / REQUIRES EXPLICIT FLASH CONFIRMATION`。

只有用户在当次会话确认 T1 通过并授权刷写后执行：

```powershell
$Firmware = ".pio\build\esp32-s3-devkitc-1\firmware.bin"
$ExpectedFirmwareBytes = 811056
$ExpectedFirmwareSha256 = `
  "AE5261AA2E679B4AEA11C9C4C2CE5D12BD561EC72748828ECC5BA570A03A4A20"
$PreUploadFile = Get-Item -LiteralPath $Firmware
$PreUploadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Firmware).Hash
if ($PreUploadFile.Length -ne $ExpectedFirmwareBytes -or `
    $PreUploadHash -ne $ExpectedFirmwareSha256) {
  throw "T2 STOP: pre-upload firmware identity mismatch"
}
& $PioExe run -e esp32-s3-devkitc-1 -t upload --upload-port COM8 `
  2>&1 | Tee-Object -FilePath (Join-Path $TestRoot "T2-upload.log")
if ($LASTEXITCODE -ne 0) { throw "T2 STOP: upload failed; keep J2-1 off" }
$PostUploadFile = Get-Item -LiteralPath $Firmware
$PostUploadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Firmware).Hash
if ($PostUploadFile.Length -ne $ExpectedFirmwareBytes -or `
    $PostUploadHash -ne $ExpectedFirmwareSha256) {
  throw "T2 STOP: upload target rebuilt different bytes; keep J2-1 off"
}
$PostUploadHash | Set-Content -Encoding ascii `
  (Join-Path $TestRoot "T2-uploaded-local-bin-sha256.txt")
# 在第二个 PowerShell 窗口运行，并把 $TestRoot 设为同一个会话目录：
& $PioExe device monitor -d . -e esp32-s3-devkitc-1 `
  --port COM8 --baud 115200 --no-reconnect `
  2>&1 | Tee-Object -FilePath (Join-Path $TestRoot "T2-serial.log")
```

看到完整启动身份、约 8 MiB PSRAM、Wi-Fi STA IP 或明确 AP fallback 后，建议让这个
monitor 窗口持续运行到 T5 结束，T3–T5 在第一个窗口操作。不要在两次 refresh 之间
反复开关 monitor。打开 monitor 可能通过 USB 控制线复位 ESP32，应把该次复位和新的
启动日志视为 T2 的一部分；若中途重开 monitor，应重新从 J2-1 断电状态建立会话。
通过条件：刷写工具校验成功且 upload 前后本地 binary identity 不变；启动无循环重启、
build 和约 8 MiB PSRAM 正确；上电不自动刷新；J2-1 仍断电时面板侧输出保持低。
Driver API、1 MHz 和 mapping 由 T3 的 `/api/version` 判定，不从串口日志推断。

## 8. T3：设备无刷新协议检查

状态：`READY / DEVICE NETWORK ONLY / J2-1 OFF`。

```powershell
$DeviceUrl = "http://<串口实际打印的设备IP>"
$env:NO_PROXY = "*"
$env:no_proxy = "*"
$VersionResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/version"
$VersionResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-version.txt")
$StatusResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/diagnostic/status"
$StatusResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-status-power-off.json")
$GenerateResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  -Method Post "$DeviceUrl/api/diagnostic/map-orient-v1-generate"
$GenerateResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-device-map-generate.json")
$T3IngressStderr = Join-Path $TestRoot "T3-host-ingress.stderr.log"
python tools\mf1750_frame_tool.py --pattern map-orient-v1 --url $DeviceUrl `
  2> $T3IngressStderr `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-host-ingress.json")
if ($LASTEXITCODE -ne 0) { throw "T3 STOP: host ingress verification failed" }
$JobBeforeBrowserResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/job"
$JobBeforeBrowserResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-job-before-browser.json")
```

以上不会调用面板刷新。通过条件：build/API/1 MHz/PSRAM/mapping 与第 2 节一致；
设备生成器和主机 ingress 都返回 307200 字节及 FNV-1a `2634290221`；断电状态
`rst/cs/cs2=0`。面板断电时 BUSY 可能为 0，不能单独作为故障判断。

此时可以打开 RC2F 设备首页，仅测试选图、拖动、缩放、旋转、四种抖动预览、物理
宽高比和像素网格；**不要点击“上传并刷新”或“MAP_ORIENT_V1 驱动验收”**。两者都会
直接触发刷新，且设备页没有 one-shot arm。保存浏览器/OS 版本、DevTools Network
记录和截图；记录中不得出现 `/api/frame` 或 `/api/diagnostic/map-orient-v1-slow` POST。
关闭页面后再运行：

```powershell
$JobAfterBrowserResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/job"
$JobAfterBrowserResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T3-job-after-browser.json")
$JobBefore = $JobBeforeBrowserResponse.Content | ConvertFrom-Json
$JobAfter = $JobAfterBrowserResponse.Content | ConvertFrom-Json
if ($JobBefore.job_id -ne $JobAfter.job_id -or `
    $JobBefore.state -ne $JobAfter.state -or `
    $JobBefore.action -ne $JobAfter.action) {
  throw "T3 STOP: browser preview changed device job state"
}
```

## 9. T4：可选 RC2F 100 kHz MAP_ORIENT_V1 诊断

状态：`OPTIONAL / NOT IN MINIMUM RC2F PLAN / REQUIRES VISIBLE_REFRESH_GO AND NEW CONFIRMATION`。

RC2F 的固件驱动路径相对 RC2C 未改，且 100 kHz 会延长高压活动时间；最小 RC2F
回归默认跳过 T4，直接在新授权下执行 T5 的正式 1 MHz MAP。只有需要复核低速方向，
或 T5 之前由集成负责人明确要求时，才单独执行本节；不得把它当作 R1 sweep 证据。

前置：T0–T3 全部通过；J2-1 已断电至少 10 秒；用户先单独授权本 run 上电。上电后
重新确认 3.3 V、CV、限流、温度、画面监控、物理切断和精确 frame，再取得只允许
下面一个 POST 的第二次授权：

```powershell
$ApprovedLimitProfileSha256 = `
  (Get-Content -Raw -LiteralPath (Join-Path $TestRoot "LIMIT-PROFILE.sha256")).Trim().ToLowerInvariant()
$CurrentLimitProfileSha256 = `
  (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $TestRoot "LIMIT-PROFILE.md")).Hash.ToLowerInvariant()
if ($CurrentLimitProfileSha256 -ne $ApprovedLimitProfileSha256) {
  throw "T4 STOP: limit profile hash changed"
}
$QueuedResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  -Method Post "$DeviceUrl/api/diagnostic/map-orient-v1-slow"
$QueuedResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T4-queued.json")
$Queued = $QueuedResponse.Content | ConvertFrom-Json
$ExpectedJobId = $Queued.job.job_id
if ($null -eq $ExpectedJobId -or [long]$ExpectedJobId -lt 1) {
  throw "T4 STOP: enqueue response has no valid job_id; cut J2-1 and do not POST again"
}
$Deadline = [DateTimeOffset]::UtcNow.AddSeconds(180)
do {
  Start-Sleep -Seconds 1
  $JobResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
    "$DeviceUrl/api/job"
  $Job = $JobResponse.Content | ConvertFrom-Json
  if ($Job.job_id -ne $ExpectedJobId) {
    throw "T4 STOP: /api/job identity changed; cut J2-1 and do not POST again"
  }
  if ([DateTimeOffset]::UtcNow -ge $Deadline) {
    throw "T4 STOP: job poll exceeded 180 s; cut J2-1 and do not POST again"
  }
} while ($Job.state -eq "queued" -or $Job.state -eq "running")
$JobResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T4-job-final.json")
if ($Job.state -ne "completed" -or $Job.result -ne $true) {
  throw "T4 STOP: non-success terminal job; cut J2-1 before any further read"
}
$ReportResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/diagnostic/report"
$ReportResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T4-diagnostic.json")
```

任一 HTTP 异常、总超时或身份变化都应立即实体切断 J2-1；随后只读查询并保存
job/report，绝不再次 POST。通过条件：

- job 为相同 `job_id`、action=`map_orient_v1_slow`、`completed/result=true`；
- report 的 build/API/job/operation、完整帧及双 DTM hash 均匹配；
- PON/DRF/POF BUSY 为 true，post-PSR BUSY 只作信息证据；最终安全收尾有效；
- 四角/上下/左右方向、六码、中央黑红跨缝桥与中缝全部正确；
- PSU 保持 CV，无异常电流、温升、声响、气味或永久色斑。

保存正面照片、PSU/温度记录和串口日志，然后切断 J2-1。下一任务前至少断电 10 秒。

## 10. T5：RC2F 正式 1 MHz `/api/frame` 回归

状态：`CONDITIONAL / ONE VISIBLE REFRESH / REQUIRES VISIBLE_REFRESH_GO AND NEW CONFIRMATION`。

最小计划在 T3 通过、`VISIBLE_REFRESH_GO` 签署后直接执行；若可选 T4 已执行，则必须
在 T4 完整通过后重新断电、冷却并取得新授权。命令为：

```powershell
$ApprovedLimitProfileSha256 = `
  (Get-Content -Raw -LiteralPath (Join-Path $TestRoot "LIMIT-PROFILE.sha256")).Trim().ToLowerInvariant()
$CurrentLimitProfileSha256 = `
  (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $TestRoot "LIMIT-PROFILE.md")).Hash.ToLowerInvariant()
if ($CurrentLimitProfileSha256 -ne $ApprovedLimitProfileSha256) {
  throw "T5 STOP: limit profile hash changed"
}
$T5Stderr = Join-Path $TestRoot "T5-map-1mhz.stderr.log"
python tools\mf1750_frame_tool.py --pattern map-orient-v1 `
  --url $DeviceUrl --refresh --confirm-cold-start `
  --controller-mapping 0,0,0,0 `
  --controller-mapping 1,0,0,0 --job-timeout 180 `
  2> $T5Stderr `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T5-map-1mhz.json")
if ($LASTEXITCODE -ne 0) {
  throw "T5 STOP: tool/report verification failed; cut J2-1 and do not resubmit"
}
```

通过条件：工具返回 `network.protocol_verified=true`，且 version、job、operation、
输入/双 DTM hash、mapping、PON/DRF/POF BUSY、timing 和 safe-finish 全部闭环；人工画面、电源和
温度必须满足第 3 节共同门禁。工具中的 `hardware_tested=false` 是正确边界，人工结果记录在
`SESSION.md`，不能手改工具 JSON。

第一次授权只允许为 `T5` 接通 J2-1；上电观测全部通过后的第二次授权必须绑定端点
`/api/frame`、本任务的三个固定 FNV-1a、RC2F build/API/binary SHA、两组 mapping 和
profile SHA。只说“可以刷新”不够。工具超时或协议校验失败时先实体切断 J2-1，再
只读保存 job/report；禁止因未看到最终响应而重发。

完成后立即断开 J2-1，保存断电后的 raw status，并确认 TP1 `≤0.10 V` 持续 `≥5 s`：

```powershell
$PowerOffStatusResponse = Invoke-WebRequest -NoProxy -UseBasicParsing -TimeoutSec 20 `
  "$DeviceUrl/api/diagnostic/status"
$PowerOffStatusResponse.Content `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T5-status-power-off.json")
```

## 11. T6：RC2F 设备内置网页照片预览；刷新暂缓

状态：`PREVIEW READY WITH J2-1 OFF / BUILT-IN PAGE VISIBLE REFRESH BLOCKED`。

在 J2-1 断电状态可以：

1. 选择一张无敏感内容的固定图片，记录原文件大小与 SHA-256；
2. 验证拖动、缩放、90°旋转、重置、物理宽高比、1×/2×/4×像素检查；
3. 对 Atkinson、Floyd–Steinberg、无抖动和 8×8 ordered 只生成预览并截图；
4. 冻结一种构图和一种抖动模式，记录页面显示的 packed FNV-1a，其他参数不再变化。

当前不要用内置页执行照片刷新。该页没有认证、one-shot arm 或远端 cancel，
`waitForJob()`/fetch 没有有限总 deadline，且 job 结束后按钮会重新启用；另一个 MAP
按钮也能直接触发 100 kHz 刷新。因此它不能把单次人工授权可靠绑定到不可变 frame，
也不能在网络异常时 fail closed。T6 可见刷新应等这些设备 UI/系统缺口修复并回归后
重新设计任务。即使未来补齐，该页仍使用未校准 reference RGB 色表，不能作为 C2 色准
或 C4 calibrated E2E 证据。

## 12. T7：C2 六色 D65/2° 测量

状态：`BLOCKED THIS RUNBOOK / FUTURE TASK DESIGN ONLY`。

若只有 RAW 相机、灰卡和固定光源，可做相对 `experimental` 观察，但**不得**生成
`calibrated=true` palette。正式 C2 输入需要合格的分光测色链、D65/2°结果、固定
45/0 几何、原始光谱/仪器文件、校准和环境元数据。

本任务包不授权下面的 pilot 命令。它们只是为下一版任务保留的已核对草案；只有先冻结
测量/聚合合同、重新审查安全 profile 并生成新 runbook 后才能执行，不能在本文件上把
`BLOCKED` 手改成 GO。

在 T5 通过后，且具备 `VISIBLE_REFRESH_GO`、合格仪器链和逐 run 授权时，才可先用一次
竖条作为 experimental pilot。授权必须绑定方向、run ID、三个固定 FNV-1a、RC2F
identity/mapping 和已知旧画面。竖条从左到右为白、黑、红、黄、蓝、绿，
应在每条中心附近取样，避开边缘和 x=512 中缝：

```powershell
$T7VStderr = Join-Path $TestRoot "T7-v-pilot-01.stderr.log"
python tools\mf1750_frame_tool.py --pattern global-v-bars `
  --url $DeviceUrl --refresh --confirm-cold-start `
  --controller-mapping 0,0,0,0 `
  --controller-mapping 1,0,0,0 --job-timeout 180 `
  2> $T7VStderr `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T7-v-pilot-01.json")
if ($LASTEXITCODE -ne 0) {
  throw "T7 STOP: vertical fixture failed; cut J2-1 and do not resubmit"
}
```

对物理码 `0黑/1白/2黄/3红/5蓝/6绿` 分别记录读数、Lab D65/2°、
重复性、测点位置、孔径、45/0 几何、仪器/校准、光源、环境、静置时间及原始文件
SHA-256。不要测边缘或中缝。测完断电并保存安全收尾证据。

一次显示内的多次仪器读数只能检查读数重复性，不能代表冷启动/刷新重复性。正式
calibrated palette 还要求横条和竖条两个冻结 fixture 各至少三次独立冷启动 run；
横条从上到下同样为白、黑、红、黄、蓝、绿。先做每种方向一个 pilot，任一失败即停；
pilot 不计入正式 `n=3`。pilot 通过后，每个新增 run 都要重新断电、预检和逐次授权：

```powershell
$T7HStderr = Join-Path $TestRoot "T7-h-pilot-01.stderr.log"
python tools\mf1750_frame_tool.py --pattern global-h-bars `
  --url $DeviceUrl --refresh --confirm-cold-start `
  --controller-mapping 0,0,0,0 `
  --controller-mapping 1,0,0,0 --job-timeout 180 `
  2> $T7HStderr `
  | Set-Content -Encoding utf8 (Join-Path $TestRoot "T7-h-pilot-01.json")
if ($LASTEXITCODE -ne 0) {
  throw "T7 STOP: horizontal fixture failed; cut J2-1 and do not resubmit"
}
```

正式 run 必须把方向和独立 run 编号写进新文件名（例如 `T7-v-formal-01.json`），禁止覆盖
pilot 或前一 run 的 JSON、串口日志、仪器原始文件和照片。

电子纸断电不会清除旧画面，不能把“冷启动”当成已知初态。若未来解锁正式采集，先
执行不计数的 `v-pilot → h-pilot`，再预注册并严格按
`v-formal-01 → h-formal-01 → v-formal-02 → h-formal-02 → v-formal-03 → h-formal-03`
交替，使每个正式 run 的旧画面都是已记录的相反方向 fixture；前一 run 未通过时不得
继续。每次 run 仍是一次独立可见刷新和一次独立授权。

竖条 full/CS1/CS2 FNV-1a 为 `0x908478A5/0x61BCF1C5/0xA3446735`；横条为
`0x7DD055C5/0x855679C5/0x855679C5`。正式 optical t0 锚定为 POF BUSY_N 低→高后
`60±5 s`，不是“断电后约一分钟”；J2-1 切断时刻另记。若串行仪器不能让六个 ROI
的有效读数都落在该窗口，T7 只能标为 experimental，不能生成 calibrated palette。
正式执行前还必须冻结测量顺序、每个读数相对 POF 的实际时间戳和不得临场删点的规则。

当前尚未冻结多 run 到六个 Lab 的分析合同，因此正式采集和 `calibrated=true` 仍是
BLOCKED。合同至少要预注册 ROI/方向/controller 权重、run 内与 run 间分层统计、聚合
方法、离群值/缺失值规则、方向偏差阈值、R&R/U95/拒收门，以及从每条原始光谱到最终
Lab 的可复算路径。只有该合同和仪器/标准板/证书/当日校验均审查通过，且所有原始
artifact 与会话证据有统一 SHA-256 manifest 后，才复制
`host/color_pipeline/palettes/reference_srgb_v1.json` 的 schema v2 形状，替换六个
Lab，设置新的 `palette_id/source/notes`、`calibrated=true`，并填写原始 artifact 的
`measurement_id` 与 SHA-256。不能只改 `calibrated` 标志。

## 13. T8：C4 主机应用 calibrated 普通图片 E2E

状态：`HARD BLOCKED / CURRENT V2 UI IS OFFLINE-ONLY`。

当前 `web/app.js` 只调用 `/application/convert-v2`，而
`prepare_simulation_artifact()` 无条件生成
`formal_upload_authorized=false`。即使通过 `--palette` 加载 measured palette，v2 页面
也不会变成 formal，arm/refresh 仍不可达；不得通过改报告字段或绕过 session validator
来执行 T8。旧 `/application/convert` 仍保留 calibrated C2 formal API，但当前 canonical
UI 不调用它，也不覆盖 G1/S1 子报告和四阶段预览，因此不能代替本任务。

解除本 blocker 前必须另行实现并审查独立的 measured/qualified G1/S1 artifact gate：

1. `calibration.artifact_sha256` 指向测量合同定义的一个 canonical 普通文件；多文件证据
   必须先定义可复现 bundle/manifest，不能直接 hash 目录；
2. allowlist 只接受受信 measured palette、mixture profile 和每色 observation kernel；
3. exact 307200-byte frame 与全部 G1/S1 子报告、profile/panel/build/options/hash 交叉绑定；
4. synthetic profile、软预览 PNG、重签报告、陈旧 artifact 和 v2 offline artifact 均被
   device enqueue 明确拒绝；
5. 复用 C4 safe ingress、mapping preflight、120 s one-shot arm、matching job/diagnostic
   和 local-abort quarantine；
6. 新 gate 的单元/HTTP 安全测试、代码审查和 frozen host tree 全部通过。

完成以上软件工作、T7 calibrated 测量和 `VISIBLE_REFRESH_GO` 后，必须编写新版 T8
runbook，再按每个 run 的“J2-1 上电授权 + 精确单 POST 授权”执行。当前本节没有可执行
刷新命令。

## 14. 会话证据冻结与耐久副本

正式结论前，先把 `SESSION.md` 全部填完，并停止修改会话文件；随后生成覆盖 raw HTTP、
JSON、串口、照片、仪器、电气、温度和流程副本的 manifest。manifest 和其 detached hash
本身不纳入自引用清单：

```powershell
$ResolvedTestRoot = (Resolve-Path -LiteralPath $TestRoot).Path
$ManifestPath = [IO.Path]::GetFullPath((Join-Path $ResolvedTestRoot "ARTIFACT-MANIFEST.json"))
$ManifestHashPath = [IO.Path]::GetFullPath((Join-Path $ResolvedTestRoot "ARTIFACT-MANIFEST.sha256"))
$Artifacts = Get-ChildItem -LiteralPath $TestRoot -Recurse -File `
  | Where-Object { $_.FullName -ne $ManifestPath -and $_.FullName -ne $ManifestHashPath } `
  | Sort-Object FullName
$ManifestRows = foreach ($Artifact in $Artifacts) {
  [pscustomobject]@{
    path = $Artifact.FullName.Substring($ResolvedTestRoot.Length + 1).Replace('\','/')
    bytes = $Artifact.Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Artifact.FullName).Hash.ToLowerInvariant()
  }
}
$ManifestRows | ConvertTo-Json -Depth 5 `
  | Set-Content -Encoding utf8 -LiteralPath $ManifestPath
(Get-FileHash -Algorithm SHA256 -LiteralPath $ManifestPath).Hash.ToLowerInvariant() `
  | Set-Content -Encoding ascii -LiteralPath $ManifestHashPath
```

此后不要再编辑 `SESSION.md` 或已列入清单的文件。把整个 `$TestRoot` 复制到由用户选定的
独立、受保护且耐久的介质/主机，然后用 `ARTIFACT-MANIFEST.json` 对第二份逐文件重算；
预定复制目标/介质 ID 应在生成 manifest **之前**填进 `SESSION.md`。复制校验完成后另建
detached `DURABLE-COPY-ATTESTATION.json`（记录 manifest SHA、目标、时间和逐文件 PASS），
再为该 attestation 生成 SHA-256 并把二者复制到两端；不要回头修改 `SESSION.md`。未完成
第二份校验时，只能报告“本机会话证据”，不能形成正式硬件结论。

## 15. 当前禁止安排的“实测”

- R1 的 2/4/8/10 MHz：固件 action 尚未实现，离线 analyzer 会正确拒绝当前低速路由；
- 20 MHz：即使未来 1–10 MHz 全过，也要另有官方时序和 timing evidence；
- `0x4/0x7..0xF`：隔离固件、安全链和 EC0–EC4 尚未完成；
- 自定义 LUT、waveform、phase、高压或 SPD1656 命令移植：SPD1657B/OTP 资料硬阻塞；
- partial refresh：当前只有控制器中立规划器，没有可发布 SPI 实现；
- G1/S1 的“真屏验收”：显示器软件基线已完成，但 measured profile/光学核和独立
  qualification gate 尚未建立；C3/N0–N6 仍缺相应软件或输入数据。

若需要把 R1 加入下一次上机，应先单独实现并审查受限 sweep firmware，再由 analyzer
生成 schema v2 计划；不得直接修改 `EPD_SPI_DEFAULT_HZ` 后逐个刷不同固件冒充同一
可审计 sweep action。

## 16. 历史执行顺序（已完成，不构成新授权）

以下是本任务包准备时的计划，保留用于审计。RC2F 固定 MAP 基准和 recovery 已按单次
授权执行完毕；当前 J2-P1 断开，T4/T5 不得依据本节再次执行。

```text
T0 离线冻结
→ T1 人工预检
→ T2 断电刷写
→ T3 无刷新协议/浏览器检查
→ 默认跳过 T4；用户授权 T5 1 MHz 最小回归
→ 仅有明确诊断需要时另行授权 T4 100 kHz
→ T6 只做 J2-1 断电网页预览；当前不从内置页刷新
→ T7 pilot 与正式采集均等待测量合同和新版 runbook
→ calibrated palette 完成前，T8 保持 BLOCKED
→ 每个会话结束执行证据 manifest 与耐久副本校验
```

本次实际已完成 T0–T3、固定 MAP 最小回归、一次 G1/S1 事故 run 和一次固定 MAP
recovery；所有相关授权均已消费。T4 不补跑，T6 可见刷新、T7 全部刷新和 T8 当前都不在
可执行范围；任何相机、既有 pilot 或本次 MAP 恢复数据都不能解锁 T8。
