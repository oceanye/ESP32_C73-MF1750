# 48MP UVC USB 相机使用说明

> **MF1750项目设备绑定：**只允许使用 `48MP USB Camera`（`VID_32E4:PID_4801`）。
> `VID_1BCF:PID_0B15` 是另一台双目USB Camera，明确排除，不得用于本项目的拍摄、识别或
> 自动判定。OpenCV索引可能随枚举顺序变化，正式采集必须同时核对VID/PID，不能只凭index。

## 设备信息

| 项目 | 值 |
|------|-----|
| 设备名 | 48MP USB Camera |
| USB ID | VID_32E4 & PID_4801 |
| 系统接口 | 仅视频接口（MI_00），无 HID 控制接口 |
| 当前枚举位置 | 目标当前为 0；双目当前为 1；OBS 当前为 2。三者均不得作为固定身份 |
| 当前 PnP instance | `USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000` |
| 当前 DirectShow alternative name | `@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global` |

## MF1750 正式采集的身份门

`tools/mf1750_camera_capture_evidence.py` 不再把调用方提供的名称、实例号或
OpenCV index 当作身份。每次正式 live capture 都必须：

1. 在打开视频流前调用 FFmpeg 的 DirectShow 枚举，解析带 USB VID/PID 的 exact
   alternative name；
2. 恰好找到一台 `VID_32E4:PID_4801`，且 friendly name 为 `48MP USB Camera`；
3. 明确拒绝调用方声称的 `VID_1BCF:PID_0B15` 双目设备、任何其他身份及 index 不一致；
4. 由该次枚举结果导出 OpenCV DirectShow index；打开前和取帧后重新枚举，路径或顺序
   漂移即失败并删除未完成输出；
5. capture sidecar 记录枚举得到的 exact alternative name，而不是调用方填写的文本。

新生成的正式 capture sidecar 为 schema v2；校验器仍可读取历史 schema v1，但 v1 没有
本身份门，不能被追溯升级成“已认证实际相机”的证据。

当前 MF1750 固定采集档为 `MJPG 4000×3000 @ 15 fps`、autofocus `0`、focus
`79`、auto exposure `0.25`、exposure `-6`、auto white balance `0`、white balance
temperature `4600`。正式包装器要求每个已请求的 DirectShow 属性写入都返回成功；任一
写入失败不会降级到自动参数或另一分辨率。

边界：OpenCV 的 DirectShow API 只能按 index 打开，不能返回已打开 filter 的 PnP
alternative name。因此当前是“同一 DirectShow VideoInputDeviceCategory 的前后双重枚举 +
唯一 VID/PID + exact path + DSHOW backend”分层证明，不是相机硬件签名。任一层不能证明时
严格 fail-closed；不存在 index fallback。正式包装器也不再暴露 camera ID、instance 或
index 覆盖参数。

## 支持的分辨率（DirectShow 探测结果）

| 格式 | 分辨率 / 帧率 |
|------|---------------|
| MJPEG | 3840x2160 @30fps、1920x1080 @30fps、1280x720 @30fps、4000x3000 @15fps、8000x6000 @5fps |
| YUYV422 | 1920x1080 @10fps、800x600 @25fps、640x480 @20fps |

高分辨率必须设置 `MJPG` FOURCC，否则会回落到 640x480。超高分辨率（4000x3000、8000x6000）帧率低，只适合静拍。

## 快速使用（Python + OpenCV）

环境依赖：`opencv-python-headless`、`numpy`。

### 拍照

```python
import cv2

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

# 预热若干帧，等自动曝光/自动对焦稳定
for _ in range(10):
    ok, frame = cap.read()
if ok:
    cv2.imwrite("photo.jpg", frame)
cap.release()
```

### 相机可控属性

标准 UVC 属性（通过 `cap.get/set` 访问）：

| 属性 | OpenCV 常量 | 说明 |
|------|-------------|------|
| 亮度 | `CAP_PROP_BRIGHTNESS` | 当前 32 |
| 对比度 | `CAP_PROP_CONTRAST` | 当前 34 |
| 饱和度 | `CAP_PROP_SATURATION` | 当前 32 |
| 色调 | `CAP_PROP_HUE` | 当前 32 |
| 曝光 | `CAP_PROP_EXPOSURE` | 当前 -5 |
| 自动对焦 | `CAP_PROP_AUTOFOCUS` | 支持，默认开启（1） |
| 焦距 | `CAP_PROP_FOCUS` | 自动对焦时持续变化 |
| 自动白平衡 | `CAP_PROP_AUTO_WB` | 默认开启 |

### 手动对焦（锁定焦点）

```python
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)   # 关闭自动对焦
cap.set(cv2.CAP_PROP_FOCUS, 90)      # 手动设焦距，适合固定距离拍摄
```

### 手动曝光（画面过亮/过暗时）

```python
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # DSHOW 约定：0.25 = 手动
cap.set(cv2.CAP_PROP_EXPOSURE, -8)
```

## LED 补光灯

- 补光灯**不能通过软件控制**：标准 UVC 协议无 LED 控制项，设备也没有枚举出 HID 接口或已知的厂商扩展单元。
- 请使用**机身上的物理按键**开关补光。

## 注意事项

- 示例中的 index 0 只适合临时人工调试。正式 MF1750 证据采集必须走上述身份门，不能把
  当前 index 记成永久绑定。
- 拍照前建议先丢弃 5~10 帧（预热），否则可能拿到黑帧或对焦/曝光未稳定的画面。
- 相机被占用时其他程序无法打开，脚本结束务必 `cap.release()`。
- 如需实时预览窗口，需将 `opencv-python-headless` 换成 `opencv-python`。
