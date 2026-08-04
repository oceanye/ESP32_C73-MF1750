# MF-1750 基础驱动与 API 参考

本文是 Rev A1/R16 基础驱动的当前统一接口说明。历史排查过程、制造证据和完整
实测记录分别保留在原有文档中；新代码应以本文、`src/epd_driver.h` 和实际路由为准。

## 1. 发布状态与适用范围

| 项目 | 当前值 |
|---|---|
| 源码候选 build | `MF1750_DRIVER_RC2E_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_TRANSFORM_2026-08-04` |
| 最近断电运行验证 build | `MF1750_DRIVER_RC2D_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_2026-08-04`；Wi-Fi、网页、PSRAM、映射通过，未刷新面板 |
| 最近实机验收 build | `MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04` |
| C++ Driver API | `MF1750_R16_CASCADE_V3` |
| RC2E `firmware.bin` | 807728 字节；SHA-256 `90247EC7A53FF8FBD186C53B435FD6EBDDFCE47B90AE0046D984141C87EC9705`；尚未刷写验收 |
| 硬件 | MF-1750 Rev A1，R15 拆除、R16=0 Ω |
| 控制器 | 双 SPD1657B，revision `0x04` |
| 面板 | 1024x600，双 512x600 控制器 |
| 默认刷新 SPI | 1,000,000 Hz |
| 实机范围 | 100 kHz MAP_ORIENT_V1 与正式 1 MHz 完整帧通过 |

基础驱动 D0 已完成：初始化、双片选级联、`CCSET(0xE0)=0x01`、六色 4bpp
整帧、控制器映射、PON/DRF/POF BUSY 门禁、失败安全断电、任务状态和不可变
诊断报告均已落地并实机验证。

以下内容不属于已验收基础 API：高于 1 MHz 的 SPI 扫频、快速/局部波形、LUT、
局刷、灰阶、未校准普通图片真屏、设备端认证和远端取消。公开的
`epdDisplayFrameAtFrequency()` 只代表驱动可接受显式频率；除 100 kHz 与 1 MHz
外，不代表该频率已经获得硬件发布资格。

## 2. 规范帧合同

| 字段 | 合同 |
|---|---|
| 尺寸 | 精确 `1024x600` |
| 字节数 | 精确 `307200` |
| 排列 | top-left、逐行、无行填充 |
| 像素 | 4bpp；偶数 x 在高 nibble，奇数 x 在低 nibble |
| CS1 | `source_half=0, flip_x=0, flip_y=0, nibble_swap=0` |
| CS2 | `source_half=1, flip_x=0, flip_y=0, nibble_swap=0` |

物理颜色码：

| 码 | 颜色 |
|---:|---|
| `0x0` | 黑 |
| `0x1` | 白 |
| `0x2` | 黄 |
| `0x3` | 红 |
| `0x5` | 蓝 |
| `0x6` | 绿 |

`0x4` 和 `0x7..0xF` 非法。HTTP raw handler 会在复制完整帧和排队前逐 nibble
拒绝非法码；公开 C++ 显示入口还会在初始化、DTM、PON 之前再次完整验证。

## 3. C++ 驱动 API

头文件：`src/epd_driver.h`。

### 3.1 生命周期与显示

```cpp
void epdBegin();
int epdReadBusy();
bool epdDisplayFrame(const uint8_t *frame, size_t len);
bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz);
bool epdClearWhite();
bool epdClearBlack();
```

- `epdBegin()`：配置 GPIO，并把所有面板侧输出保持为低；它不会自动刷新。
- `epdReadBusy()`：读取原始 BUSY_N 电平。面板供电且空闲时实测为 1；面板断电时
  可能为 0，不能脱离供电状态单独解释。
- `epdDisplayFrame()`：使用已验收的默认 1 MHz，要求非空指针和精确 307200
  字节；只有完整初始化、两半 DTM、PON、DRF、POF 和最终安全收尾都成功才返回
  `true`。
- `epdDisplayFrameAtFrequency()`：合同同上，并要求 `spiHz > 0`。高于 1 MHz
  属于实验调用，必须另做逐级硬件验收。
- `epdClearWhite()` / `epdClearBlack()`：维护诊断用整屏纯色刷新，不是应用渲染
  API；应用应始终生成规范完整帧。

每次显示操作结束后，SPI 被停止，SCK/MOSI/DC/RST/CS1/CS2 被拉低，避免 ESP32
仍由 USB 供电而面板 J2-1 断电时发生反向供电。

### 3.2 无副作用验证

```cpp
bool epdIsSupportedColorCode(uint8_t color);
bool epdValidateFrameColors(const uint8_t *frame, size_t len,
                            size_t *invalidPixel = nullptr,
                            uint8_t *invalidCode = nullptr);
```

两者都不访问面板。`epdValidateFrameColors()` 只检查传入的 `len` 字节颜色码；调用
显示 API 时仍必须独立满足 `len == 307200`。失败时可返回第一个非法像素的线性
索引与非法 nibble。

### 3.3 操作报告

```cpp
const EpdOperationReport &epdGetLastOperationReport();
```

报告是驱动内最后一次 result-bearing 操作的当前快照；下一次操作会覆盖它。直接
C++ 调用方若要长期保留证据，应立即复制结构体。HTTP wrapper 只在 job 完成后把
新报告复制成不可变 JSON，因此后续 REV 或诊断不能给旧 job 换贴报告。

重要字段：

| 字段组 | 含义 |
|---|---|
| `operationId` | 本次 MCU 启动内非零 u32 序号；重启后可重新从 1 开始 |
| `valid/running/sequenceOk` | 报告有效性、进行状态和最终序列结果 |
| `waitTimedOut/timeoutStage` | BUSY 等待超时及首次失败阶段 |
| `busyAssertionMissing/busyMissingStage` | 必须阶段在 250 ms 内没有 BUSY assertion |
| `pon/drf/pofBusySeen` | 三个正式高压阶段必须全部为 true |
| `postPsrBusySeen` | POF 后 PSR 的信息证据；允许为 false |
| `inputFrameFnv1a` | 规范输入帧哈希 |
| `cs1DtmFnv1a/cs2DtmFnv1a` | 应用物理映射后的两路 DTM 哈希 |
| `*UploadMs/*WaitMs/totalMs` | 上传、各 BUSY 阶段和总耗时 |

POF 后 PSR 写入不会在当前实板再次拉低 BUSY，因此该阶段只要求最终 idle 和等待
证据；PON、DRF、POF 仍严格要求 BUSY assertion，缺失时 fail closed。

## 4. ESP32 HTTP API

### 4.1 安全与调用规则

当前 ESP32 HTTP 服务没有认证和 TLS，只能运行在可信、隔离的调试网络。不要把它
直接暴露到互联网。正式应用优先使用主机 `HttpDeviceAdapter`，因为它限制路由、
绑定 artifact/mapping、执行一次性 arm，并核对 job 与 diagnostic；这些主机保护
并不等于设备端认证。

设备同一时间只允许一个 EPD job。`202` 只表示已排队，不表示显示成功。调用方必须：

1. GET version 并核对 build/API/尺寸/SPI/PSRAM/mapping；
2. POST 精确规范帧并保存返回的 `job_id` 与 FNV-1a；
3. 轮询相同 job 到 `completed` 或 `failed`；
4. GET immutable diagnostic，并核对 build/API/job/operation/hash/BUSY；
5. 最后由人确认画面、电源和温度。

网络超时后不得盲目重发 `/api/frame`。先查询 `/api/job` 和
`/api/diagnostic/report`；RC2E/V3 没有远端 cancel API。

### 4.2 稳定的应用协议路由

| Method | Route | 作用 | 面板 I/O |
|---|---|---|---|
| GET | `/api/version` | build、API、帧、SPI、mapping、PSRAM 预检 | 无 |
| POST | `/api/diagnostic/frame-ingress` | raw 帧长度/颜色/哈希/PSRAM 验证 | 无 |
| POST | `/api/frame` | 验证并排队一次正式 1 MHz 整帧刷新 | 有 |
| GET | `/api/job` | 当前/最后 job 状态 | 无 |
| GET | `/api/diagnostic/report` | 最后一个完成 job 的不可变 schema v2 报告 | 无 |

主机应用 adapter 的设备路由 allowlist 只包含以上五项。

另外两个可安全用于 D0 复核、但不在应用 adapter allowlist 内的接口：

| Method | Route | 作用 |
|---|---|---|
| GET | `/api/diagnostic/status` | 读取 `busy/rst/cs/cs2` 原始电平 |
| POST | `/api/diagnostic/map-orient-v1-generate` | 在 PSRAM 生成并校验规范 MAP；返回 `epd_action:"none"` |

### 4.3 Version 预检

```http
GET /api/version
```

成功返回 `200 text/plain`：

```text
MF1750_DRIVER_RC2E_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_TRANSFORM_2026-08-04
Panel: 1024x600
Driver API: MF1750_R16_CASCADE_V3
Frame bytes: 307200
Refresh SPI Hz: 1000000
CS1 Mapping: 0,0,0,0
CS2 Mapping: 1,0,0,0
PSRAM bytes: <managed SPIRAM heap bytes>
Free PSRAM: <current free bytes>
```

`PSRAM bytes` 是 Arduino 受管 SPIRAM 堆，不是封装物理容量。N8R8 实机可能比
8 MiB 少报几 KiB；正式主机门禁只允许最多 64 KiB 的管理开销，并继续要求至少
一帧可用空间。

### 4.4 Raw 帧验证和正式刷新

两个入口都要求：

```http
Content-Type: application/octet-stream
Content-Length: 307200
```

body 是第 2 节规范的 307200 字节二进制帧，不能使用 multipart、base64 或 JSON。

非刷新验证：

```http
POST /api/diagnostic/frame-ingress
```

成功返回 `200`：

```json
{"ok":true,"bytes":307200,"fnv1a":2634290221,"free_psram":8060000,"epd_action":"none"}
```

正式刷新：

```http
POST /api/frame
```

成功排队返回 `202`：

```json
{"ok":true,"bytes":307200,"fnv1a":2634290221,"free_psram":8060000,"job_id":1}
```

### 4.5 设备内置照片工具网页

`GET /` 返回完全在浏览器内运行的照片工具，不会把原始图片上传到 ESP32。选择
一次原图后可反复切换以下六色处理方式：

- `none`：无抖动，形成平滑但细节较少的色块；
- `floyd-steinberg`：误差扩散，细节最多、颗粒也最密；
- `atkinson`：较轻的误差扩散，作为默认照片模式；
- `ordered-bayer-8x8`：固定 8x8 网点，输出可复现但可能出现规则纹理。

网页并排显示缩放/裁剪后的原图与“实际六色上传预览”。照片优化会用固定 gamma
提亮暗部并轻微降低饱和度；关闭后使用解码后的 sRGB 像素。所有模式都使用
`0/1/2/3/5/6` 六个物理码，同时由同一次颜色选择生成预览像素和 4bpp 帧，避免
原图预览与实际上传不一致。

原图构图画布支持鼠标和触摸指针拖动；鼠标滚轮或 `50%..400%` 滑杆缩放；左右
按钮按 90° 旋转；重置按钮恢复 `100%/0°/居中`。旋转后的 contain/cover 基准按
旋转外接框重新计算。拖动期间只更新原图构图，松开后量化；连续缩放使用短防抖，
停止操作后才生成六色预览。任何构图变化都会立即作废旧 `packed` 帧并禁用上传，
直到新预览及其 FNV-1a 生成完成。

切换裁剪、照片优化或抖动模式只在浏览器中重新计算，绝不访问 `/api/frame`。
只有点击“上传并刷新”才提交当前 `packed` 帧；网页必须核对设备响应的 `bytes`
与 FNV-1a 后才轮询对应 job。该内置工具使用固定 reference RGB 色板，仍属于方便
调试的近似照片模式，不替代带 provenance 的 calibrated host pipeline。

### 4.6 Job 状态

```http
GET /api/job
```

```json
{
  "job_id": 1,
  "action": "uploaded_frame",
  "state": "completed",
  "result": true,
  "queued_at_ms": 24256,
  "started_at_ms": 24261,
  "finished_at_ms": 58449,
  "frame_fnv1a": 2634290221
}
```

`state` 为 `idle|queued|running|completed|failed`。未产生结果时 `result` 为
`null`。三个时间戳是本次启动内的 u32 `millis()`，可能回绕；job id 也是本次启动
内序号，MCU 重启后可以重新从 1 开始。

### 4.7 Immutable diagnostic

```http
GET /api/diagnostic/report
```

启动后尚无完成报告时返回：

```json
{"schema_version":2,"valid":false,"error":"no_completed_job_report"}
```

完成后响应把以下身份和驱动字段绑定在同一个不可变 JSON 中：

- `firmware_build_tag`、`driver_api_version`；
- `job_id/action/state/result`、`job_operation_id`、三个 job 时间戳；
- `operation_id`、`valid/running/sequence_ok`；
- `wait_timeout`、`busy_assertion_missing`、`timeout_stage`、
  `busy_missing_stage`；
- `pon/drf/pof/post_psr_busy_seen` 与对应 `*_ms`；
- `spi_hz`、完整帧/CS1/CS2 FNV-1a；
- 两路 mapping 和安全收尾的最后等待阶段。

正式成功至少要求：job completed/result=true，两个 operation id 相同且非零，
`sequence_ok=true`，PON/DRF/POF BUSY 为 true，无 timeout/missing stage，SPI/mapping
和三个哈希与提交内容一致，`last_wait_stage="post-display PSR"`。

### 4.8 HTTP 错误

| 状态 | 典型 error | 含义 |
|---:|---|---|
| 400 | `frame_size_mismatch` | Content-Length/raw 总长度不等于 307200 |
| 400 | `unsupported_color_code` | 含非法 nibble；同时返回 `invalid_pixel/code` |
| 400 | `frame_too_large` / `upload_aborted` | raw 上传越界或中止 |
| 409 | `epd_action_pending` | 已有 queued/running job |
| 415 | `content_type_must_be_application_octet_stream` | 不是 raw octet-stream |
| 500 | `map_generation_failed` | 规范 MAP 生成/自校验失败 |
| 404 | `Not found` | 未注册路由 |

PSRAM 分配失败通过 400 `frame_buffer_allocation_failed` 返回。错误响应不会把帧排队。

## 5. 维护诊断路由

以下路由继续存在于 RC2E 固件，但不属于稳定应用 API，也不在
`HttpDeviceAdapter` allowlist 中。它们可能切换 GPIO、复位控制器、启动高压或
显示历史非规范尺寸；只有在面板供电条件、冷启动间隔和人工授权明确时才可调用。

无高压/引脚维护：

- `POST /api/diagnostic/revisions`
- `POST /api/diagnostic/reset`
- `POST /api/diagnostic/cs-high`
- `POST /api/diagnostic/cs-low`
- `POST /api/diagnostic/cs2-low`
- `POST /api/diagnostic/release`

历史/固定图刷新：

- `POST /api/test`
- `POST /api/black`
- `POST /api/white`
- `POST /api/bars`
- `POST /api/halves-wb`
- `POST /api/bars-800x480`
- `POST /api/white-800x480`
- `POST /api/black-800x480`
- `POST /api/bars-512x600`
- `POST /api/white-512x600`
- `POST /api/black-512x600`
- `POST /api/bars-swap`
- `POST /api/bars-h`
- `POST /api/bars-8bpp`
- `POST /api/bars-cs2-test`

100 kHz 定向诊断：

- `POST /api/diagnostic/white-512-slow`
- `POST /api/diagnostic/black-512-slow`
- `POST /api/diagnostic/white-800-slow`
- `POST /api/diagnostic/white-1024-short-slow`
- `POST /api/diagnostic/white-512-long-slow`
- `POST /api/diagnostic/white-1024-full-slow`
- `POST /api/diagnostic/cs1-bars-isolated`
- `POST /api/diagnostic/cascade-white-black-slow`
- `POST /api/diagnostic/cascade-black-white-slow`
- `POST /api/diagnostic/cascade-dual-bars-slow`
- `POST /api/diagnostic/cascade-global-bars-slow`
- `POST /api/diagnostic/cascade-global-horizontal-bars-slow`
- `POST /api/diagnostic/map-orient-v1-slow`
- `POST /api/diagnostic/dual-white-black-slow`
- `POST /api/diagnostic/dual-black-white-slow`
- `POST /api/diagnostic/dual-white-white-slow`

上述刷新路由通常返回 `202` 与嵌套 `job`；必须继续查询 job/report，不能把排队响应
当作显示成功。部分旧探针没有完整 result/report 语义，只保留用于历史溯源。

## 6. 推荐主机入口

只生成、验证规范 MAP：

```powershell
python tools\mf1750_frame_tool.py --pattern map-orient-v1
```

连接设备但不刷新：

```powershell
python tools\mf1750_frame_tool.py --pattern map-orient-v1 `
  --url http://DEVICE-IP
```

正式刷新需要冷启动确认和两项显式 mapping：

```powershell
python tools\mf1750_frame_tool.py --pattern map-orient-v1 `
  --url http://DEVICE-IP --refresh --confirm-cold-start `
  --controller-mapping 0,0,0,0 `
  --controller-mapping 1,0,0,0
```

工具输出中的 `hardware_tested:false` 表示机器不能替代人的实屏、电源和温度确认，
不表示本文记录的 D0 硬件验收不存在。

## 7. Loopback 应用 API

启动默认离线 UI：

```powershell
python -m app.server
```

显式启用设备 adapter：

```powershell
python -m app.server --enable-device --device-url http://DEVICE-IP
```

服务只允许 numeric loopback 地址。每次启动生成高熵 token，打印在 URL fragment；
浏览器随后把它移入同源 `sessionStorage`。所有 `/application/*` 请求必须带
`X-Application-Token`，POST 还必须有匹配的 `Origin`，并拒绝 query string。

读取路由：

| Method | Route | 作用 |
|---|---|---|
| GET | `/application/config` | 面板、palette、dither、fit、adapter 配置 |
| GET | `/application/status` | artifact、arm、job、锁和恢复状态 |
| GET | `/application/report` | 当前应用 artifact/report |

变更路由：

| Method | Route | 请求 |
|---|---|---|
| POST | `/application/convert` | 精确 2457600 字节 normalized RGBA octet-stream |
| POST | `/application/artifact/invalidate` | JSON object |
| POST | `/application/device/allow` | `{"allow":true}` |
| POST | `/application/device/preflight` | mapping JSON |
| POST | `/application/device/ingress` | `{}` |
| POST | `/application/device/arm` | `{"confirmation":"ARM MF1750 REFRESH"}` |
| POST | `/application/device/enqueue` | mapping JSON |
| POST | `/application/device/job` | `{}` |
| POST | `/application/device/report` | `{}` |
| POST | `/application/device/recover` | `{}` |
| POST | `/application/device/local-abort` | `{}` |
| POST | `/application/device/cancel` | `{}`；RC2E/V3 明确返回 unsupported |

mapping JSON：

```json
{"cs1":[0,0,0,0],"cs2":[1,0,0,0]}
```

`/application/convert` 的必需 Content-Type 是 `application/octet-stream`；浏览器还会
发送 `X-Input-SHA256`、`X-Input-Media-Type`、`X-Fit-Policy`、`X-Dither-Mode`、
`X-Text-Mode` 和 `X-White-Protection`。默认 reference palette 未校准，只能生成
明确标记的离线预览；只有带完整 provenance 的 calibrated palette 才可能获得正式
上传授权。

普通变更成功响应为 `{"ok":true,"result":...}`；错误统一包含
`ok=false/error/detail/hardware_tested=false`。应用层的 `hardware_tested` 永远为
false，最终物理验收必须在应用报告之外人工记录。

## 8. 已知边界与版本策略

- RC2C/V3 是底层驱动已实测的不可变固件身份；RC2D/V3 增加设备内置网页照片
  工具，RC2E/V3 再增加构图变换。每个版本必须以独立 build、构建指纹和刷写复验
  记录管理，不能继承 RC2C 的固件哈希。
- 任何改变初始化、CCSET、mapping、颜色码、PON/DRF/POF/PSR、BUSY 门禁或
  面板 GPIO 安全状态的变更，都必须提升 build/API 并重新实机验收。
- 当前设备 API 无认证、无 TLS、无 cancel、无持久 job 历史。
- H0 archive/hash 与硬件验收 tag 是发布封存工作；创建 tag 前仍需用户明确授权。
- 网络照片源、随机选择与定时刷新按
  [`TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md`](TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md)
  分阶段执行；当前尚未实现，也不得直接在 ESP32 上猜测式扩展。
- 完整实测数据见 `docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`。
