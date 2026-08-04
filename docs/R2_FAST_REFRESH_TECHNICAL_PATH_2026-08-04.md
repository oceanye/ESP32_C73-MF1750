# MF-1750 快速刷新技术路径（阶段 1，2026-08-04）

## 1. 当前结论

快速刷新的工作必须分成两条互不混淆的路径：

1. **缩短主机上传时间**：沿用当前 OTP 波形，只提高 SPI DTM 传输速度。这条路径风险低、
   可直接量化，但不能缩短 `DRF` 的固定显色时间。
2. **缩短或局部执行显色波形**：需要 SPD1657B 与当前 MF-1750 OTP 波形的正式接口。
   这是把约 21.7 秒 `DRF BUSY` 明显压低的唯一主路径，但目前缺少必要的一手资料，
   禁止猜寄存器、改高压或移植 SPD1656 命令。

阶段 1 没有修改 `src/`、没有访问硬件，也不宣称快速刷新已经实屏通过。

## 2. 已确认的直接证据

### 2.1 当前面板与接口

`参考资料/MF-1750..1).pdf` 给出的直接信息：

- MF-17506-M009F-T 是 `1024x600`、3-bit E6 全显示面板；
- 面板集成 SRAM、LUT、温度传感器，波形存储在片上 OTP；
- SPI 写时钟周期最小 50 ns，因此面板接口的理论写上限是 20 MHz；
- 命令表明确要求参考 SPD1657B datasheet，但该 datasheet 当前不在仓库；
- 电气/光学性能只在 InkCubic 提供的控制器与匹配波形下保证；
- 规格建议正常环境下每日更新一次，并提示长期红色显示后增加黑白清屏有助于恢复效果。

因此，20 MHz 是接口上限，不是整机立即可用频率。ESP32 GPIO 翻转、逐字节 CS、
排线完整性和双控制器一致性仍需实测。

### 2.2 配套 E Ink 样例

随附 `E6_73_sample code_V1.2_20250116` 只有完整帧
`DTM -> PON -> DRF -> POF` 流程。V1.2 在每次显示后新增 6 秒等待、PSR 设置、
1 秒等待和 VDD cut；该安全收尾不得为了“看起来更快”而删除。

样例中存在命令 `0x86`：

```c
// Not use now. Reserve for dither image in future
// It depends on dithering area on image
void Enable_Interlace() { SPI_COMMAND(0x86); SPI_DATA(0x01); }
```

这是当前资料里距离区域性行为最近的入口，但注释没有定义：

- 区域从哪里配置；
- Interlace 是空间采样、扫描交错、闪烁效果还是部分波形；
- 支持哪些颜色转移；
- 是否减少 BUSY 时间；
- 是否要求不同 OTP 波形。

在取得命令定义前，`0x86` 只能列为供应商问题，不能进入固件实验。

### 2.3 Spectra 6 平台能力

E Ink 官方说明 Spectra 6 可产生 `Sparkle` 局部图像闪烁效果：

- [E Ink Spectra 6](https://www.eink.com/brand/detail/Spectra6)
- [E Ink 2024 sustainability report](https://esg.eink.com/en/report/0325092616hg934435/2024%20CORPORATE%20SUSTAINABILITY%20REPORT)

这证明四粒子 Spectra 6 存在受支持的局部动态技术，但没有证明当前
MF-1750、SPD1657B revision `0x04` 和片上 OTP 已包含对应模式。

E Ink 对彩色局刷的研究还说明：局刷需要旧/新状态信息，更新区边界可能受像素间耦合
影响，并需要额外边界处理以降低鬼影。它不是“只少发一些 DTM 字节”即可完成的功能：
[E Ink color partial-update patent](https://patents.google.com/patent/US20250239231A1/en)。

## 3. 可量化的时间预算

每颗控制器接收 `153600` 字节，两颗共 `307200` 字节。仅计算 SPI 数据位，不含
逐字节 CS/GPIO/软件开销：

| SPI | 两颗控制器理论线上时间 | 相对 1 MHz 理论节省 |
|---:|---:|---:|
| 1 MHz | 2457.6 ms | 0 ms |
| 2 MHz | 1228.8 ms | 1228.8 ms |
| 4 MHz | 614.4 ms | 1843.2 ms |
| 8 MHz | 307.2 ms | 2150.4 ms |
| 10 MHz | 245.8 ms | 2211.8 ms |
| 20 MHz | 122.9 ms | 2334.7 ms |

当前实测 100 kHz 时每半约 14.9 秒；按该结果近似线性估算，1 MHz 约为每半
1.5 秒，但尚未完成 1 MHz 实屏验收。因此继续提高 SPI 的实际收益预计约 2–3 秒，
而不是把 20 多秒显色过程变成秒级。工具必须分别
报告 `CS1 upload`、`CS2 upload`、`DRF BUSY` 和总时间，禁止只报总时间后误判来源。

## 4. 分阶段决策门

### G0：冻结基线

先提交并推送最终 `main`、确认对应 GitHub CI，并取得用户明确刷写/上电许可；
随后完成 D0 的 MAP_ORIENT_V1 低速方向验收，再通过正式 1 MHz `/api/frame`
发送同一个 MAP_ORIENT_V1。两个 DTM hash、
颜色、方向、中缝和安全收尾全部通过后，才开始加速实验。

### G1：只加速 DTM

此前实机 RC1 与当前待重刷的 RC2C 都还不能进入 G1：
`/api/diagnostic/map-orient-v1-slow` 固定为 100 kHz；
普通 `/api/frame` 虽可完成 G0 的 1 MHz 验收，却不是可按档选择频率的 MAP 扫频入口。
在独立实验分支提供受限的参数化 action，并让 job、diagnostic、serial 共享 operation
ID/build tag 之前，离线 analyzer 只能作为合同和负例检查器，不得给出现有固件的升频
PASS。

按 `1 -> 2 -> 4 -> 8 -> 10 MHz` 逐级测试。每档必须：

- J2-1 断电至少 10 秒后冷启动；
- 使用同一 MAP_ORIENT_V1；
- full/CS1/CS2 hash 完全一致；
- 记录两个上传时间、PON/DRF/POF BUSY、总时间；
- 保存同一次运行的 firmware build tag、`/api/job`、诊断报告和单次串口日志指纹；
- 用示波器或逻辑分析仪记录实际 SCLK，而不是只信固件请求值；
- 运行前先成功显示一张哈希冻结、与目标不同的已知画面，避免残留的旧 MAP 造成
  “看起来已刷新”的假阳性；
- 人工确认方向、颜色、中缝、噪点和残影；
- 记录 3.3 V、电流/CV、温升和异常声响；
- 任一档失败即停止升频。

扫频门禁使用 schema version 2：串口日志中每个必要 marker 必须恰好出现一次，
job/diagnostic/serial 的 operation ID、build tag 和重叠字段必须一致，且正式 PASS 必须
满足 `valid=true`、`running=false`、
`mapping_applied=true`、`timeout_stage=none`、安全收尾阶段正确。所有人工门禁均可用
显式 `--no-...` 记录失败；失败尝试必须输出 FAIL，不能伪装成 PENDING。

10 MHz 全部通过后，结合逻辑分析仪确认 CS setup/hold、SCLK 高低脉宽和数据建立保持，
才允许单独评审 20 MHz。不能因为规格理论上限为 20 MHz 就跳过中间档。

### G2：取得厂商资料

必须拿到当前 revision/OTP 对应资料，至少回答第 5 节问题。若回答是不支持 Sparkle、
partial 或 fast mode，则 R2 固件路径关闭，转向应用级感知优化或新控制器/新面板方案。

### G3：离线建模

在不访问硬件的前提下实现：

- old-frame/new-frame changed mask；
- update bounding boxes 和可配置边界扩张；
- 6x6 颜色转移直方图；
- partial 次数与强制 full-cleanup 计数器；
- 温度、波形 ID、面板序列号、实测耗时与光学结果记录格式。

只有厂商资料明确数据编码后，这些输出才能映射到控制器命令。

### G4：隔离的实机实验

快速/局刷实现必须在新的实验接口中，默认关闭，并满足：

- 不改变 Rev A1 高压参数；
- 不覆盖现有 full-refresh API；
- 单次、冷启动、可回退；
- BUSY 超时立即 POF 并保持面板侧 GPIO 低；
- 首轮只使用供应商规定的 fixture、温度和转移；
- 每次实验后执行供应商规定的 full cleanup。

## 5. 向 InkCubic / E Ink / Solomon 索取的资料

请针对 **MF-17506-M009F-T、SPD1657B revision 0x04、当前面板批次** 询问：

1. SPD1657B 完整 command datasheet，尤其是 OTP waveform mode select、RAM/window、
   temperature、status、Interlace `0x86`；
2. 当前 OTP waveform 的 ID、版本、温度范围和支持的 display modes；
3. 此面板是否支持 Sparkle、partial image flashing、fast full update 或黑白快速模式；
4. 若支持，提供正式初始化、旧/新帧要求、区域对齐/边界、颜色转移限制和 DRF 参数；
5. `0x86` 的完整数据格式、“dithering area” 的配置命令及其对 BUSY 时间的影响；
6. 最大连续局刷次数、必须执行的 full cleanup、残影/寿命/保修限制；
7. 内置温度传感器读取方法，以及不同温区对应的模式限制；
8. 20 MHz 是否对该 FPC/双 SPD1657B 级联方案有效，是否有额外 CS/SCL 时序限制；
9. 是否存在更新的 `.eink` initial data、OTP image、参考 MCU 源码或 Sparkle demo；
10. Ripple/T2000 是否要求不同控制器或面板批次，当前硬件能否升级。

建议邮件主题：

```text
Request: SPD1657B Rev 0x04 fast/partial refresh documentation for MF-17506-M009F-T
```

## 6. 明确排除的路线

- 不移植 SPD1656 PartialRAM、LUT unlock、波形表、电压或帧率；
- 不枚举 `0x00..0xFF` 命令；
- 不根据 BUSY “看起来正常”判断未知命令安全；
- 不把 Gallery 3、黑白 Carta、Spectra 6 Plus、Ripple/T2000 的速度套到当前面板；
- 不删除 V1.2 的显示后等待与 VDD cut；
- 不把提高 SPI 频率宣传为波形快速刷新。

机器可读的证据与限制见 `research/fast_refresh/evidence_matrix.json`。
