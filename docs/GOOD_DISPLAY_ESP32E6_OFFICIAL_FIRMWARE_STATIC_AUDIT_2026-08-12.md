# Good Display ESP32E6-E01 官网固件静态审计（2026-08-12）

## 结论

这份官网固件提供了三类可信的软件证据：WiFi 固件内嵌的六色调色板/抖动网页；三份 app 共有的、已由 typed command/data helper 和业务 caller 绑定的 E6 OTP 初始化/整帧显示路径；以及 SD 卡 SPI 与 SD 面板 GPIO bitbang 的明确分离。它**没有**提供可恢复的 SPD1657/ED2208 runtime-LUT ABI，也没有证明面板侧亮度/对比度寄存器、`0x20`/`0x21` 载荷、`799`/`704`/`2508` 长度语义或双控制器交付路径。

因此，这批固件不能据此构造真屏 runtime-LUT 载荷；所有数值命中继续保持为原始字节巧合，不升级为面板合同。

## 官网来源与身份

Good Display 的[ESP32E6-E01 产品页](https://www.good-display.com/product/586.html)把资源列为 “7.3\" ESP32E6-E01 Driver Board - Firmware Flashing via WiFi/USB/SD”，大小 1.1 MB，时间为 2026-06-04 13:48:00；产品页同时把 50-pin 接口描述为面向 4-inch/7.3-inch Spectra 6。审计使用该资源的[官网资源页](https://www.good-display.com/companyfile/2071.html)下载重定向所得 ZIP。

- ZIP：`7.3in_Firmware_Wifi_USB_SD.zip`
- 字节数：`1,156,950`
- SHA-256：`8eaff3e3a68da354c6ad1fc62a1d6b6ee2144df64198ab35a544e5a96f868a96`
- `GDEP073E01wifi.bin`：`16,777,216` bytes，SHA-256 `df8959b99304d3b6d0b7e560cc4db03a5edb9ffe28640f7428d662285b548508`
- `SD.bin`：`4,194,304` bytes，SHA-256 `86d9da5e0200ccbf0a5ef7a90a1b89bc06b554d591a3a24cdb99d2648672dcf5`
- `usb.bin`：`4,194,304` bytes，SHA-256 `f21bd62bd2171e4fa30c527847b60313dba746cc16eb44a3ecba9e178551cdad`

三个镜像的 ESP 分区表相同，MD5 均为 `98f492a471b542a1572d58e33e614dc8`：`nvs@0x9000`、`otadata@0xe000`、`app0@0x10000/0x300000`、`spiffs@0x310000`、`coredump@0x3f0000`。三个 app 均被解析为 ESP32-S3 镜像，段校验和与附加 SHA-256 均有效。

## 证据分层

### 直接字符串/代码证据

WiFi app 的 DROM 中存在完整网页：

- 标题 `Image Dithering to Epaper`；
- 六色 `REAL_PALETTE` 与六色 `DRIVER_PALETTE`；
- Floyd-Steinberg、Atkinson、Stucki、Jarvis-Judice-Ninke；
- `adjustContrast(imageData, factor)` 名称只出现一次，位置就是函数定义，未发现调用点；`brightness` 不存在。

这证明的是浏览器端图像预处理，不是面板寄存器。尤其不能把 JavaScript 的 contrast 函数解释为控制器亮度/对比度能力。

SD app 直接列出 BMP 到驱动像素码的诊断映射：Black=`0`、White=`1`、Yellow=`2`、Red=`3`、Blue=`5`、Green=`6`。这证明六种基础驱动码，不证明同一像素的粒子混色或 runtime-LUT。

三个 app 的 ASCII 字符串都没有发现 `SPD1657`、`SPD1656`、`ED2208`、`WF20_25`、`WF23_25`、独立 `LUT` token、`waveform`、文本 `0x20`/`0x21`。WiFi 中的 temperature 字符串属于 ESP-IDF 温度传感器框架；`SPI_MASTER`/`I2C_SLAVE` 等同样属于通用框架，不能作为双 EPD 控制器证据。

### 有界指令级证据

在 `SD.bin` 中可复现以下链条：

- DROM `0x3c0401b3`：`Starting SPI initialization...`；
- IROM `0x42000054`：上述字符串指针；
- `0x420024e2`：`l32r a11, 0x42000054`；函数入口 `0x420024dc`；
- `0x420026e8`：`call8 0x420024dc`；
- 同一函数紧邻的四个立即数为 `48, 47, 13, 21`，并与固件诊断字符串 `SCK: GPIO21, MOSI: GPIO47, MISO: GPIO13, CS: GPIO48` 一致；
- 初始化完成后立即引用 `Starting SD card initialization...`。

所以这里恢复到的是 **SD 卡 SPI 初始化**。同一 setup 邻域还在 `0x420026eb` 调用引用 `Scanning available images...` 的函数。该可达性不能外推成面板 SPI、LUT 写入或双控制器选择。

第一轮审计因镜像剥离业务符号而在这里停止。随后新增的 cross-image 审计没有依赖 raw
contiguous-byte 搜索，而是先对每个 app 构造与原始 ESP image segment byte-for-byte 一致的
ELF view，再以 Xtensa 指令、call target、GPIO D/C/select 差分和业务 caller 逐层绑定：

- 三个 app 均恢复出 264-byte、102-instruction 的同一归一化 E6 init；typed trace 均为
  `AA:495520080918, 01:3f, 00:5f69, 03:00540044, 05:401f1f2c,
  06:6f1f1749, 08:6f1f1f22, 30:08, 50:3f, 60:0200, 61:032001e0,
  84:01, E3:2f, 04`；
- command/data helper 分别固定 GPIO2 select，并以 GPIO3 low/high 区分 command/data；三镜像
  归一化 SHA-256 分别相同；
- WiFi/USB 将 384000 个 8-bit grayscale tag 映射
  `{0:0,29:5,76:3,150:6,226:2,255:1}`，首像素进 high nibble、次像素进 low nibble，
  形成 192000-byte 800×480 packed frame；WiFi/SD 的 packed display 归一化机器码相同；
- SD 的 BMP processor 成功分支可达 init 和 packed display；SD 面板 transport 是
  GPIO12 clock/GPIO11 data 的 8-bit MSB-first bitbang，与 GPIO21/13/47/48 的 SD-card SPI
  是两条不同路径；WiFi/USB 面板 wrapper 仅保守归类为剥符号的
  `SPIClass::transfer(uint8_t)` source-shape match。

所以“面板 SPI/call graph 全部 unknown”已被这份更强证据更新。仍然必须保持有界：恢复出的
typed init/display command 集合没有 `0x20` 或 `0x21`，没有 704/2508-byte runtime payload，
也没有双控制器路径；其他 raw constants 继续是未类型化 unknown。

### 原始字节命中（仅负面覆盖）

| app | `20 21` | LE32 `799` | LE32 `704` | LE32 `2508` | contiguous 本地 E6 init 前缀 |
|---|---:|---:|---:|---:|---:|
| WiFi | 136 | 0 | 29 | 2 | 0 |
| SD | 59 | 0 | 7 | 0 | 0 |
| USB | 54 | 0 | 6 | 0 | 0 |

表中的所有命中都只是未类型化字节。init 前缀 raw 命中为 0 不再等于“没有 init”：编译器把
每个字节降成分离的立即数加载和 helper call，cross-image 指令审计已经恢复其 typed trace。
相反，`20 21` 仍广泛出现在程序/数据中；SD-card 代码还使用十进制 `21` 作为 SCK GPIO。
没有 command/data helper、循环边界和业务调用路径，就不能把其余 raw 命中解释为命令
`0x20`/`0x21` 或 LUT 长度。

## 可复现产物

- 工具：`tools/good_display_esp32e6_firmware_audit.py`
- 测试：`tests/test_good_display_esp32e6_firmware_audit.py`
- JSON：`.test-output/offline/good_display_esp32e6_firmware_audit_20260812.json`
- JSON 文件 SHA-256：`47320086015dd6c6ceb37c9a1ad92759bf1b4ea8f26791b28ebb8d0ffb327213`
- JSON canonical SHA-256：`cb54e65648731ed1c02221747dc559be58dc898f5f4efd126c94b53371851a09`

Cross-image 增量：

- 工具：`tools/good_display_esp32e6_cross_image_panel_audit.py`
- 测试：`tests/test_good_display_esp32e6_cross_image_panel_audit.py`
- JSON：`.test-output/offline/good_display_esp32e6_cross_image_panel_audit_20260812.json`
- JSON 文件 SHA-256：`3f82c21dca0d59f4c35bd8a390dbea26497dd29b3fb6e502a2ba2c95f1bd7f4b`
- JSON canonical SHA-256：`8f6f9399a80e6f9fd02ef351437aa368a53e8b058d48f7d9b586c789016e5854`

复现：

```powershell
python tools\good_display_esp32e6_firmware_audit.py `
  --output .test-output\offline\good_display_esp32e6_firmware_audit_20260812.json
python -m pytest -q tests\test_good_display_esp32e6_firmware_audit.py
python -m ruff check tools\good_display_esp32e6_firmware_audit.py tests\test_good_display_esp32e6_firmware_audit.py
python -m ruff format --check tools\good_display_esp32e6_firmware_audit.py tests\test_good_display_esp32e6_firmware_audit.py
python -m py_compile tools\good_display_esp32e6_firmware_audit.py tests\test_good_display_esp32e6_firmware_audit.py
python tools\good_display_esp32e6_cross_image_panel_audit.py `
  --output .test-output\offline\good_display_esp32e6_cross_image_panel_audit_20260812.json
python -m pytest -q tests\test_good_display_esp32e6_cross_image_panel_audit.py
```

本轮仅访问公开互联网和本地文件；未访问硬件、串口/COM、设备网络，未刷写、复位或刷新屏幕，也未生成可执行的真屏载荷。
