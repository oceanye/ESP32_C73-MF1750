# MF-1750 Rev A1 R16 级联整屏验证（2026-08-04）

> 当前待重新刷入候选 build tag 为
> `MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04`，
> driver API 为 `MF1750_R16_CASCADE_V3`。它保留六色帧输入门禁、可审计错误返回和
> diagnostic report 的 job/build 关联；HTTP ingress 和公开
> `epdDisplayFrame*` 都会在初始化、DTM、PON 之前拒绝非法 nibble。RC2B/V2 已
> 完成 100 kHz MAP_ORIENT_V1 真屏；画面、哈希、PON/DRF/POF BUSY 均正确，但
> POF 后 PSR 写入不会再次 assert BUSY，暴露了 RC2B 的软件假失败。RC2C/V3 仅把
> 该 post-PSR 采样改为信息证据；PON/DRF/POF 仍必须在 250 ms 内观察到 BUSY，
> 缺失即 fail closed、安全 POF/SPI stop/面板引脚拉低。正式报告使用匹配的非零 u32
> `job_operation_id` / `operation_id` 不可变快照，后续 REV/诊断不能改贴旧报告。

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

### 3.1 RC2B MAP_ORIENT_V1 首次实机结果与 RC2C 修正

2026-08-04 将主线 SHA `99941690fa2f649fcf10d6df7f67576e01208ec6`
对应的 RC2B/V2 刷入 COM8；GitHub 主线 CI run `30913097544` 已成功。刷写时
J2-1 断电，esptool 确认 ESP32-S3、8 MB embedded PSRAM 且所有写入区块哈希
通过。启动后的版本、映射与状态为 307200 字节、1 MHz、CS1=`0,0,0,0`、
CS2=`1,0,0,0`、约 8 MB PSRAM、面板控制脚低电平。

设备生成器和主机非刷新 ingress 均返回 MAP_ORIENT_V1 FNV-1a
`2634290221`，且明确 `epd_action="none"`。随后在用户确认 3.3 V / 1 A、CV、
L1/L2 正常后，只执行一次 100 kHz `map_orient_v1_slow`。实屏与参考 PNG 完全
一致，用户判定“非常完美”：四角方向、左右身份、nibble 探针、中央标尺和跨缝桥
全部正确。没有记录可用于 R1 的定量峰值电流或最高温度，因此本次只关闭 D0 的
低速视觉映射门禁，不构成扫频电气证据。

RC2B 报告中的有效证据为：

```json
{
  "job_id": 1,
  "operation_id": 1,
  "spi_hz": 100000,
  "input_fnv1a": 2634290221,
  "cs1_dtm_fnv1a": 4066915037,
  "cs2_dtm_fnv1a": 4263092213,
  "cs1_upload_ms": 14895,
  "cs2_upload_ms": 14896,
  "pon_ms": 181,
  "pon_busy_seen": true,
  "drf_ms": 21700,
  "drf_busy_seen": true,
  "pof_ms": 140,
  "pof_busy_seen": true,
  "post_psr_ms": 250,
  "post_psr_busy_seen": false,
  "busy_missing_stage": "post-display PSR"
}
```

画面完成、POF 也有真实 BUSY 后，RC2B 仍因 post-PSR 未再次 assert BUSY 将 job
标记 failed。对比 RC1 与随附样例可见：该步骤是 POF 后等待 6 秒、写 PSR、等待
1 秒并切断接口；RC2B 提交 `514bb4a` 才把原有非严格 idle wait 改成严格
BUSY-then-idle。RC2C/V3 恢复 post-PSR 的非严格 idle/timing 记录，同时继续严格
要求 PON/DRF/POF BUSY、1 秒等待、SPI stop 和所有面板输出拉低。RC2C 必须重新
刷入并得到 completed job/report 后，才进入 1 MHz 正式帧。

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

0. 先完成候选审查、提交、推送并确认最终 `main` CI；取得用户明确刷写/上电
   许可后，才执行以下步骤。
1. 驱动板保持断电，刷入上述精确 RC2C build；确认启动日志识别约 8 MB PSRAM，且
   `/api/diagnostic/status` 中 RST/CS1/CS2 均为 0。
2. 驱动板仍断电，只检查二进制入口，不刷新：

   ```powershell
   python tools\mf1750_frame_tool.py --pattern map-orient-v1 --url http://<device-ip>
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
4. MAP_ORIENT_V1 低速方向通过后，再冷启动一次，用主机工具通过正式 1 MHz
   `/api/frame` 链路发送同一个规范帧。两项 mapping 必须显式提供，工具会在
   POST 前核对固件 build/API/PSRAM/SPI/mapping，随后核对最终 job、四阶段 BUSY
   采样（PON/DRF/POF 必须 assertion，post-PSR 仅作信息证据）和双 DTM hash：

   这里固件的 `PSRAM bytes` 来自 Arduino `ESP.getPsramSize()`，代表受管 SPIRAM
   堆总量而非封装物理容量。N8R8 实机因堆元数据上报约 `8385863` 字节；主机门禁
   因此只允许标称 8 MiB 以下最多 64 KiB 的固定管理开销，并继续独立要求至少
   `307200` 字节可用 PSRAM。低于该下限仍必须在 POST 前失败。

   ```powershell
   python tools\mf1750_frame_tool.py --pattern map-orient-v1 `
     --url http://<device-ip> --refresh --confirm-cold-start `
     --controller-mapping 0,0,0,0 `
     --controller-mapping 1,0,0,0
   ```

   只有工具报告通过且用户确认画面、CV 和温度正常，才完成 D0 的 1 MHz 门禁。
   普通图片、量化与 Web UI 属于 C4/C2 应用验收，不再混入驱动定版结论。

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
