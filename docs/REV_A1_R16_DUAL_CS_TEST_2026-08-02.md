# MF-1750 Rev A1 R16 独立片选测试（2026-08-02）

## 进入条件

- R15 已拆除，R16 安装 0 Ω；两者禁止同时导通。
- J2-9 接 ESP32-S3 GPIO10。
- J2-1 由外部 3.3 V 供电，限流 1 A；ESP32 只由 USB 供电并与驱动板共地。
- FPC 只能在 J2-1 与 ESP32 USB 都断开时插拔。
- 当前固件标识：`REV_A1_R16_DUAL_CS_TRACE_2026-08-02`。

## 无高压静态验证

驱动板接好 FPC 后冷启动，但不要运行刷新测试。依次调用：

```powershell
curl.exe -X POST http://<IP>/api/diagnostic/cs-high
curl.exe -X POST http://<IP>/api/diagnostic/cs-low
curl.exe -X POST http://<IP>/api/diagnostic/cs2-low
curl.exe -X POST http://<IP>/api/diagnostic/release
```

示波器地夹只接 TP2：

| 接口 | TP8（主片选） | TP9（从片选） |
| --- | --- | --- |
| `cs-high` | 约 3.3 V | 约 3.3 V |
| `cs-low` | 约 0 V | 约 3.3 V |
| `cs2-low` | 约 3.3 V | 约 0 V |
| `release` | 约 3.3 V | 约 3.3 V |

若任一组合不符合，不得启动刷新。该测试中 SCK、DC、MOSI 固定为低电平，
不会发送命令或启动高压。

## 独立半屏矩阵

每项之间必须断开 J2-1 至少 10 秒，再重新上电。SPI 固定 100 kHz；两颗
SPD1657 同时复位并广播初始化为各自 512x600，随后分别上传 153600 字节，
最后广播 PON/DRF/POF 以保持级联波形同步。

1. 主片白、从片黑：

   ```powershell
   curl.exe -X POST http://<IP>/api/diagnostic/dual-white-black-slow
   ```

2. 主片黑、从片白：

   ```powershell
   curl.exe -X POST http://<IP>/api/diagnostic/dual-black-white-slow
   ```

3. 两片都白：

   ```powershell
   curl.exe -X POST http://<IP>/api/diagnostic/dual-white-white-slow
   ```

若前两项的黑白位置随 CS1/CS2 交换，独立片选和半帧映射成立；若白色仍为
行间隔但黑色正确，则问题进一步收敛到白色像素/波形初始化，而不是第二片选。
若两个独立片选仍不能分别改变两半，则需要 Ink Cubic 提供
`MF-17506-M009F-T` 的专用双 SPD1657 主从初始化与级联寄存器设置。

## 2026-08-02 实测结果

### 静态片选

- 待机：TP8=3.3 V，TP9=3.3 V。
- 仅主片选有效：TP8=0 V，TP9=3.3 V。
- 仅从片选有效：TP8=3.3 V，TP9=0 V。
- 结论：GPIO7/TP8 与 GPIO10/J2-9/TP9 均可独立控制，R16 路径成立。

### 动态互换

1. 主片白、从片黑：A 闪烁后为黑白行间隔，B 闪烁后为浅黑色。
2. 主片黑、从片白：A 闪烁后为黑色，B 闪烁后为淡灰色，但没有达到纯白。
3. 主片白、从片白：A 闪烁后为黑白行间隔，B 闪烁后为淡黑色。B 在刷新
   过程中曾短暂停留在接近纯白的状态，随后被后续刷新相位重新驱暗。
4. 前两次均全程 CV、温度正常，没有 L1/L2 异常升温；第三次上电前供电与
   温度检查正常，测试中未报告电源或温升异常。

黑白数据交换后 A/B 的最终表现也随之改变，证明两路 DTM 数据已分别送达
两颗控制器。当前剩余问题不是 R16 或 CS2 未生效，而是专用面板初始化、白色
波形/颜色状态，或双芯片级联参数仍不匹配。

第二次测试的固件记录为：

```json
{"sequence_ok":true,"wait_timeout":false,"total_ms":58932,"cs1_upload_ms":14879,"cs2_upload_ms":14880,"last_wait_stage":"post-display PSR","timeout_stage":"none"}
```

因此不能把测试期间 HTTP 暂时不可达解释为 BUSY 超时；控制器序列实际正常
结束。应单独排查高压刷新期间的 Wi-Fi/供电噪声或网络可达性。

第三次双白测试的记录为：

```json
{"sequence_ok":true,"wait_timeout":false,"total_ms":58922,"cs1_upload_ms":14879,"cs2_upload_ms":14879,"last_wait_stage":"post-display PSR","timeout_stage":"none"}
```

B 能在刷新中间阶段接近纯白，证明白色数据能够到达且像素具有变白能力；最终
又变暗则把问题进一步收敛到后续驱动相位、面板专用 PSR/PWR/BTST/温度/级联
初始化参数，而不是 `0x11` 白色色码、SPI 数据完整性或第二片选。没有
`MF-17506-M009F-T` 专用参数时，不应盲目枚举高压/波形寄存器。
