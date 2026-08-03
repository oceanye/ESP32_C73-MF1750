# MF-1750 Rev A1 R16 级联整屏验证（2026-08-04）

## 1. 当前硬件与冻结边界

- Rev A1 已生产完成；制造目录及带 `revA1_Q1FIX` 名称的 Gerber/BOM/CPL
  继续冻结，不重新生成或覆盖。
- R15 已拆除，R16 已安装 0 Ω；J2-9 接 ESP32-S3 GPIO10。
- CS1：GPIO7 -> J2-5/TP8；CS2：GPIO10 -> J2-9/TP9。
- ESP32 实物由 esptool 识别为带 8 MB OPI PSRAM 的 N8R8 型号；正式帧缓冲
  为 1024x600x4bpp = 307200 字节。

## 2. 已确认的软件/控制器事实

1. 两颗控制器分别执行两次 `REV(0x70)` 读取，均稳定返回
   `[0x01,0x01,0x04]`，revision 字段均为 `0x04`。
2. 真正 CS1-only 刷新能正确显示白、黑、红、黄、蓝、绿六色色条。
3. 不写 CCSET 时，虽然 CS1/CS2 数据可以分别送达，最终波形会把白色重新
   驱暗；这不是 R16、CS2、白色色码或 SPI 数据缺失。
4. 分别向两颗控制器写 `CCSET(0xE0)=0x01` 后：
   - CS1 白 / CS2 黑正确；
   - CS1 黑 / CS2 白正确；
   - 两半分别显示六色色条正确。
5. 因此 `CCSET bit0` 的级联使能是当前实际 SPD1657B/MF-1750 组合的必需
   初始化；结论来自实屏单变量试验，SPD1656 文档只作为字段旁证。

## 3. 2026-08-04 全局连续六色色条结果

测试接口：

```text
POST /api/diagnostic/cascade-global-bars-slow
```

条件：每颗控制器 TRES=512x600；先分别写 CCSET=0x01，再逐行发送左右
153600 字节，最后双选执行 PON/DRF/POF；SPI=100 kHz。

软件记录：

```json
{
  "valid": true,
  "running": false,
  "sequence_ok": true,
  "wait_timeout": false,
  "total_ms": 59037,
  "cs1_upload_ms": 14902,
  "cs2_upload_ms": 14901,
  "last_wait_stage": "post-display PSR",
  "timeout_stage": "none"
}
```

实屏记录：

- 完整屏幕六色均正确；
- 从左到右顺序为白、黑、红、黄、蓝、绿；
- 中央 `x=511/512` 的红/黄交界清晰；
- 测试结束后已断开 J2-1。

判定：CS1 对应物理左半，CS2 对应物理右半；两半没有交换或水平镜像，
逐行左右分帧正确，中缝没有缺列、重复或明显错位。R16 路径与 CCSET 初始化
已经实现完整 1024x600，不需要据此对 Rev A1 做硬件 ECO。

## 4. 下一张唯一必要的诊断图：MAP_ORIENT_V1

`MAP_ORIENT_V1` 是直接生成、未经 canvas 缩放或抗锯齿的白底 1024x600
4bpp 原始帧。它在一次刷新中同时检查：

- 最外侧五个 4 px 同心环：黑、红、黄、蓝、绿，用于判断有效区裁切；
- 每个 512x600 半屏的四个 80x80 方向块，分别带 1/2/3/4 个黑刻度，
  用于唯一判断水平/垂直翻转；
- CS1 红底一条黑线、CS2 蓝底两条白线的身份块；
- 每半屏各一组带锚点的 `0x01` 与 `0x10` 相邻像素探针，用于判断 nibble
  相位；该区域应拍正面微距原图；
- `x=[492,532)` 的十条非对称 4 px 中缝标尺；
- 一条 144x8 黑色跨缝桥和一条 112x12 红色跨缝桥，用于检查缺列、重复、
  错行和上下翻转。

方向块的物理左上/右上/左下/右下刻度数判据：

| 刻度顺序 | 映射 |
|---|---|
| `1/2/3/4` | 不翻转 |
| `2/1/4/3` | 水平翻转 |
| `3/4/1/2` | 垂直翻转 |
| `4/3/2/1` | 水平+垂直翻转 |

确定性校验值：

| 数据 | 字节 | FNV-1a |
|---|---:|---:|
| 完整 MAP_ORIENT_V1 | 307200 | `0x9D04142D` / 2634290221 |
| 默认映射下 CS1 DTM | 153600 | `0xF26832DD` / 4066915037 |
| 默认映射下 CS2 DTM | 153600 | `0xFE199FF5` / 4263092213 |

固件生成后会先自校验完整帧哈希；不相等时拒绝刷新。主机工具同样独立生成
并验证三个哈希：

```powershell
python tools\mf1750_frame_tool.py --pattern map-orient-v1
```

生成器还检查六色像素计数 `39536/425808/29280/47072/0/44192/28512`，
并让字节级映射算法与独立像素级参考在 source-half、flip-X、flip-Y、
nibble-swap 的全部 16 种组合下逐字节比较。

## 5. 用户回来后的最小测试顺序

每次可见刷新之间，J2-1 必须断电至少 10 秒；FPC 禁止带电插拔。

1. 驱动板保持断电，刷入测试套件；确认启动日志识别约 8 MB PSRAM，且
   `/api/diagnostic/status` 中 RST/CS1/CS2 均为 0。
2. 驱动板仍断电，只检查二进制入口，不刷新：

   ```powershell
   python tools\mf1750_frame_tool.py --pattern map-orient-v1 --url http://192.168.1.14
   ```

   必须返回 `bytes=307200`、`fnv1a=2634290221`。
   也可直接让设备侧 C++ 生成器自检（同样不会调用 EPD）：

   ```text
   POST /api/diagnostic/map-orient-v1-generate
   ```

   必须返回 `epd_action=none`，且 `fnv1a` 与 `expected_fnv1a` 均为
   `2634290221`。
3. 冷启动并确认 3.3 V / 1 A、CV、无升温后，只运行一次：

   ```text
   POST /api/diagnostic/map-orient-v1-slow
   ```

   四角、上下方向和黑/红跨缝桥必须与第 4 节一致；任务状态见
   `GET /api/job`，驱动时序见 `GET /api/diagnostic/report`。
4. MAP_ORIENT_V1 通过后，再冷启动一次，从网页上传一张普通图片。这一步使用正式
   1 MHz `/api/frame` 链路，验证浏览器量化、PSRAM、逐行拆分和刷新闭环。

若 MAP_ORIENT_V1 正确，不再重复旧 800x480、512x600、无 CCSET 纯色或 nibble-swap
矩阵；这些接口只保留为历史诊断，不作为正式驱动验收依据。

## 6. 固件安全改动

- 上电不自动刷新；面板未供电时所有面板侧 GPIO 保持低电平。
- `/api/frame` 只接受 `application/octet-stream` 和精确 307200 字节。
- 修复 WebServer 将 multipart 与 raw 共用回调时可能解引用空 raw 指针的问题。
- 单任务锁防止连续点击覆盖待执行动作；每项返回 job id，`/api/job` 区分
  queued/running/completed/failed。
- 网页等待最终任务状态，异常时也会恢复按钮，不再把 HTTP 202 当成刷新成功。
- 当前串口端口更新为 COM8；本轮代码只离线构建，用户确认前不刷写。
