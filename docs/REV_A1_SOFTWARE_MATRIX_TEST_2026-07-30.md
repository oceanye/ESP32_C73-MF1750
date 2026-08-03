# MF-1750 Rev A1 软件驱动测试矩阵（2026-07-30）

## 目标与边界

- 保持 Rev A1 硬件、R15 共片选和冻结生产文件不变。
- 先排除 SPI 速度、初始化分辨率、发送字节数、BUSY 时序和非冷启动状态。
- 每次只执行一个完整刷新测试，不连续点击接口。
- 固件标识：`REV_A1_SOFTWARE_MATRIX_DIAG_2026-08-02`。

## 已确认的软件事实

1. Rev A1 的 BS0、BS1 都为低电平，选择 4-wire SPI；现有 GPIO6 作为 DC
   的连接与屏规格一致。
2. SPI Mode 0、MSB first、命令/参数序列与 `E6_73_sample code_V1.2_20250116`
   一致。
3. 原始样例固定使用 `TRES=800x480`、发送 `192000` 字节，而且软件模拟
   SPI 明显慢于当前固件的 1 MHz。
4. MF-1750 是 `1024x600`、双 SPD1657；现有资料没有给出这块屏专用的
   主从控制器初始化代码。
5. Rev A1 没有 `SWC` 负载开关。执行软件 POF 后屏的 3.3 V 仍存在，所以
   每个矩阵测试必须手动给 J2-1 冷启动，不能只复位 ESP32。

## 安全供电

- ESP32：只由 USB 供电。
- 驱动板 J2-1：外部稳压 3.3 V，限流 1 A。
- ESP32 GND 与驱动板 J2-2/J2-10 共地。
- 不再把 ESP32 的 3V3 接到 J2-1。
- 若电源进入 CC、实际电压明显下降、出现快速升温或异响，立即断开 J2-1。

## 冷启动定义

每个完整刷新测试前：

1. 断开 J2-1。
2. 等待至少 10 秒，并确认 TP1 对 TP2 接近 0 V。
3. 保持 ESP32 USB 和串口监视器连接。
4. 重新接通 J2-1，确认电源为 CV 3.3 V。
5. 只调用一个测试接口，等待串口出现 `EPD action finished`。

## 第零步：R15 静态片选测试（不启动高压）

将 `<IP>` 替换为 ESP32 串口打印的局域网地址。

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/cs-high
curl.exe -X POST http://<IP>/api/diagnostic/cs-low
curl.exe -X POST http://<IP>/api/diagnostic/release
```

每条命令执行后分别测量：

| 状态 | TP8（CSB） | TP9（SL_CSB） | 预期 |
| --- | --- | --- | --- |
| `cs-high` | 约 3.3 V | 约 3.3 V | 两点一致 |
| `cs-low` | 约 0 V | 约 0 V | 两点一致 |
| `release` | 约 3.3 V | 约 3.3 V | 两点一致 |

如果 TP8 正常而 TP9不跟随，才说明 R15 或相关铜线存在硬件问题。

## 完整刷新测试顺序

### A. 低速 512x600 白屏

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/white-512-slow
```

- SPI：100 kHz
- TRES：512x600
- DTM：153600 字节 `0x11`

这是当前 R15 共片选最关键的基线。若两半都得到一致纯白，优先判断此前
1 MHz 或非冷启动导致数据接收异常。

### B. 低速 512x600 黑屏

必须先重新冷启动。

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/black-512-slow
```

- SPI：100 kHz
- TRES：512x600
- DTM：153600 字节 `0x00`

白、黑两次都一致，才能继续测试颜色和整帧。

### C. 原样例参数对照

必须先重新冷启动。

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/white-800-slow
```

- SPI：100 kHz
- TRES：800x480
- DTM：192000 字节 `0x11`

该测试只用于验证原样例参数能否被 Rev A1/当前屏稳定接收，不代表最终
正确分辨率。

### D. 仅在 A～C 无法解释结果时使用的字节数矩阵

`1024x600` 地址空间，但只发送一个 `512x600` 半帧：

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/white-1024-short-slow
```

`512x600` 地址空间，但发送完整 `1024x600` 字节数：

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/white-512-long-slow
```

这两项用于判断双控制器级联是否根据 TRES 或 DTM 字节数分配数据，不应
在 A～C 之前随意执行。

### E. 逻辑整屏地址与完整帧组合

必须先重新冷启动。

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/white-1024-full-slow
```

- SPI：100 kHz
- TRES：1024x600
- DTM：307200 字节 `0x11`

这是 D 项交叉矩阵缺少的最后一格，用于判断两颗控制器是否只在逻辑整屏
地址与完整帧长度同时匹配时正确分配数据。

## 2026-08-02 首板实测记录

| 测试 | 软件结果 | A 半屏 | B 半屏 | 其他现象 |
| --- | --- | --- | --- | --- |
| 512x600 / 153600 / 白 | PASS_SEQUENCE | 黑白行间隔 | 黑 | 两半均闪烁 |
| 512x600 / 153600 / 黑 | PASS_SEQUENCE | 全黑 | 均匀灰 | 两半均闪烁 |
| 800x480 / 192000 / 白 | PASS_SEQUENCE | 黑白行间隔 | 深灰 | FPC 侧宽深色条带、外围约 1 mm 白圈 |
| 1024x600 / 153600 / 白 | PASS_SEQUENCE | 深到浅渐变 | 淡色 | FPC 侧宽淡色条带、外围约 1 mm 白圈 |
| 512x600 / 307200 / 白 | PASS_SEQUENCE | 黑白行间隔 | 深灰 | 无宽条带、外围约 1 mm 白圈 |
| 1024x600 / 307200 / 白 | PASS_SEQUENCE | 深到浅渐变 | 淡灰 | 两半仍不一致、未得到纯白 |

六次测试均为 3.3 V / 1 A 限流供电，全程 CV，L1/L2 无明显升温。静态
片选测试中 TP8 与 TP9 均能同步达到约 3.36 V 和 0 V；仅复位后 TP10
从 0 V 变为约 3.3 V。完整刷新期间数据上传、PON、DRF、POF 和 BUSY
时序均正常，低速 SPI 仍无法得到整屏纯色。

## 串口必须记录的字段

- 固件标识和 IP 地址。
- 每次测试的 `TRES`、`bytes`、`fill`、`SPI`。
- reset、PON、DRF、POF 的耗时和 `busy_seen`。
- `PASS_SEQUENCE` 或 `FAILED_SEQUENCE`。
- 电源是否一直 CV、峰值/稳定电流。
- A/B 两半最终颜色、渐变方向、边缘约 1 mm 区域是否闪烁。

## 判定逻辑

- TP8/TP9 静态不一致：R15/铜线问题，停止软件矩阵。
- 100 kHz 正常、1 MHz 异常：SPI 信号完整性或频率问题，仍可通过降低
  速度继续使用 Rev A1。
- 512x600 的白和黑两半一致：R15 共片选可以工作，继续修正分辨率/数据
  分配。
- 所有低速纯色测试仍表现为两半固定不同，但 TP8/TP9 完全同步：
  更可能是 MF-1750 主从控制器需要不同初始化或独立 CS2，不再把问题
  归因于像素编码。
- BUSY 从未出现有效工作区间，或任一步超时：优先检查命令接收、复位和
  BUSY 极性，不继续连续刷新。
