# ESP32_C73 后续 TODO 与多 AI 协作计划（2026-08-04）

## 0. 进度快照（2026-08-04 更新）

| 工作包 | 状态 | 远端分支 / 提交 | 剩余硬件门禁 |
|---|---|---|---|
| C1 主机帧核心 | 已完成 | `feature/host-frame-core` / `cb0a03f` | MAP_ORIENT_V1 实屏方向复核 |
| C2 六色量化与抖动 | 主机代码已完成 | `feature/color-dither` / `7cc015e` | 实测 D65/2deg 六色色板与主观验收 |
| C3 转移感知优化 | 参数规划器已在 R1/R2 提供，完整优化器待办 | 尚未建立独立 C3 分支 | 6x6 转移实测矩阵 |
| C4 应用 API/Web UI | 待办 | 尚未建立独立 C4 分支 | 普通图片端到端实刷 |
| C5 CI 与回归门禁 | 已完成 | `feature/host-ci` / `c59a1f2` | 无；CI 不等于硬件通过 |
| R1 SPI 扫频工具 | 离线部分已完成 | `research/fast-refresh` / `b03b7e1` | 家中 1/2/4/8/10 MHz 冷启动扫频 |
| R2 快速波形/局刷研究 | 证据边界与规划器已完成 | `research/fast-refresh` / `b03b7e1` | SPD1657B/OTP 厂商资料，取得前禁止实装 |

完整代码集成候选为 `integration/host-fast-refresh-ci-color`，代码与集成说明点
`aa006c4` 已通过 64 项联合回归和 GitHub Actions 的主机门禁/PlatformIO
release 编译。详情见 `docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`。
`main` 仍保持 `3033da0`，本机未进行硬件测试或自动合并主线。

## 1. 目的与当前优先级

本计划制定时的唯一主任务是完成并验收 MF-1750 Rev A1 驱动层。当前已经建立
`main` 基线，主机侧 C1/C2/C5 与 R1/R2 离线工作已按上方快照完成；MAP_ORIENT、
SPI 扫频、实测色板和任何快速波形仍由家中硬件环境验收。剩余 TODO 不得修改
已冻结的 Rev A1 生产文件，也不得绕过硬件/厂商资料门禁。

后续可把不依赖实物的代码工作交给其他 AI。其他 AI 只提交独立分支或补丁、
测试输出和移交说明；最终代码审查、实机验证和 Git 合并由当前硬件环境的
集成负责人完成。

## 2. 永久保护边界

以下内容禁止其他 AI 修改、重生成、重命名或覆盖：

- `hardware/mf1750_production_v1/production/`；
- 所有带 `revA1_Q1FIX` 名称的 Gerber、BOM、CPL；
- Rev A1 已下单文件的大小与 SHA256 记录；
- 当前驱动定版完成前的 `src/epd_driver.cpp`、`src/epd_driver.h`、
  `src/epd_config.h`；
- R15/R16、MF-1750 高压拓扑和 GPIO 基线，除非实测形成明确 ECO 证据。

任何 PCB 新设计只能放入新的修订目录，例如：

```text
hardware/mf1750_revB_mini/
```

不得把 Rev B 文件写回 `mf1750_production_v1`。

## 3. 环境与角色划分

### 3.1 集成负责人（具有当前硬件环境）

独占执行：

- ESP32-S3 COM8 刷写与串口复位；
- 驱动板 J2-1 上断电操作；
- 实屏方向、颜色、中缝、残影和温升判断；
- SPI 实机扫频；
- 3.3 V 电流、高压轨和示波器测量；
- `src/epd_driver.*` 的最终修改；
- 最终 Git 基线、审查、合并和发布标记。

### 3.2 无硬件 AI

适合执行：

- 纯主机图像算法；
- 确定性帧生成、哈希和映射单元测试；
- Web/API 应用层；
- PC 端上传、日志分析和测试报告工具；
- CI、静态分析和文档；
- PCB/BOM 的只读面积与器件候选研究；
- 官方资料、论文和专利的证据整理。

不得宣称实屏通过，不得调用 `/api/frame`，不得刷写 COM8，也不得根据
SPD1656 猜测 SPD1657B 的高压/LUT/局刷寄存器。

## 4. Git 前置状态与集成策略

当前工作区的 `.git` 目录为空，不是可用仓库。驱动实屏验收前不建立多人
分支，避免把未定版驱动当成基线。

驱动验收后由集成负责人执行：

1. 对 Rev A1 冻结文件重新计算并核对 manifest；
2. 建立初始 Git 仓库和 `.gitignore`；
3. 提交只包含已验收驱动、工具、文档和原有硬件文件的 baseline commit；
4. 创建受保护标签，例如 `mf1750-driver-v1.0-hw-verified`；
5. 其他 AI 必须基于该 commit SHA 建分支，不得基于聊天中间状态开发；
6. 每个分支只负责一个工作包，最终由集成负责人逐个 cherry-pick 或 merge。

建议分支名：

```text
feature/host-frame-core
feature/color-dither
feature/transition-aware-optimizer
feature/application-api-ui
feature/host-ci
research/fast-refresh
analysis/revb-mini
```

## 5. 工作包总览

| ID | 工作包 | 无硬件 AI 可完成 | 依赖 | 最终硬件门禁 |
|---|---|---|---|---|
| D0 | 驱动 v1.0 定版 | 否，只读复审可委托 | 当前任务 | 两次实屏验收 |
| C1 | 主机帧格式核心与 fixtures | 是 | D0 API/格式冻结 | 无 |
| C2 | 六色量化与空间抖动 | 是 | C1 | 实屏颜色主观验收 |
| C3 | 转移感知抖动优化器 | 是，先做参数化代码 | C1/C2 | 6x6 实测矩阵 |
| C4 | 应用 API/Web UI | 是 | D0/C1 | 一次普通图片端到端刷新 |
| C5 | CI、静态检查和回归测试 | 是 | D0/C1 | 无 |
| R1 | SPI 高速传帧测试工具 | 是，工具部分 | D0 | 实机扫频 |
| R2 | 快速波形/局刷证据研究 | 是，仅研究 | 厂商资料 | 未取得资料前禁止实装 |
| H0 | Rev A1 阶段备份 | 否，集成负责人执行 | D0 后 | 校验 archive hash |
| H1 | Rev B-mini 面积/BOM 分析 | 是，只读 | H0 | 器件与热/电流实测审查 |
| H2 | Rev B-mini 原理图/PCB | 可协助代码生成 | 用户输入+H1 | ERC/DRC/实物评审 |

## 6. D0：当前驱动 v1.0 定版

负责人：当前集成负责人。其他 AI 只能只读复审。

验收内容：

- R16 独立片选，GPIO7=CS1、GPIO10=CS2；
- 两颗 SPD1657B 分别写 `CCSET(0xE0)=0x01`；
- 每颗 TRES=512x600；
- 输入帧固定为 1024x600、4bpp、row-major；
- 偶数 x 在高 nibble、奇数 x 在低 nibble；
- 驱动层独占 source-half、flip-X、flip-Y、nibble-swap 映射；
- CS1/CS2 实际 DTM 流分别计算 FNV-1a；
- PON/DRF/POF/BUSY 超时返回到调用方；
- 刷新结束后 SPI 释放且所有面板侧输出保持低电平；
- 应用只需包含 `epd_driver.h`，诊断接口隔离到 `epd_diagnostics.h`。

必须通过的 fixtures：

| Fixture | Full FNV-1a | CS1 FNV-1a | CS2 FNV-1a |
|---|---:|---:|---:|
| global-v-bars | `0x908478A5` | `0x61BCF1C5` | `0xA3446735` |
| global-h-bars | `0x7DD055C5` | `0x855679C5` | `0x855679C5` |
| MAP_ORIENT_V1 | `0x9D04142D` | `0xF26832DD` | `0xFE199FF5` |

当前已实测 global-v-bars 完整六色正确且中缝清晰。剩余两次验收为
MAP_ORIENT_V1 低速方向检查和同帧 1 MHz 正式上传。

## 7. C1：主机帧格式核心与 fixtures

建议文件所有权：

```text
host/epd_frame/
tests/fixtures/
tests/test_frame_contract.py
```

不得修改 `src/`。

交付：

- 一个无第三方依赖或依赖明确的 Python 库；
- pack/unpack 4bpp；
- full-frame 与逐行 CS1/CS2 拆分；
- source-half/flip-X/flip-Y/nibble-swap 的参考实现；
- 三个 fixture 的生成器、像素计数和 FNV 校验；
- 对全部 16 种单控制器映射组合逐字节比较字节级与像素级实现；
- 错误尺寸、奇数宽度、非法色码和截断数据测试。

验收命令必须由 AI 在移交中给出，且返回码为 0。

## 8. C2：六色量化与空间抖动

建议文件所有权：

```text
host/color_pipeline/
tests/test_color_pipeline.py
```

输入：RGB/RGBA 图像。输出：规范 307200 字节 4bpp 帧。不得直接访问 GPIO、
HTTP 刷新接口或修改驱动。

第一阶段实现：

- sRGB -> 线性 RGB -> CIE Lab；
- 可配置的六色实测 Lab 调色板；
- 最近色量化，建议使用 CIEDE2000；
- Floyd-Steinberg、Atkinson 和有序蓝噪声/阈值矩阵至少两种抖动；
- 白底保护、透明度合成、边缘保真和文本模式；
- 固定随机种子，确保相同输入产生完全相同 raw 与哈希；
- 输出预览 PNG 和 palette 使用率报告。

无实屏时只能使用参数文件中的颜色，不得把显示器 sRGB 常量声称为面板校准值。

## 9. C3：转移感知抖动与“最快近似颜色”

该算法有实现价值，但必须正确理解目标：在当前固定全局 DRF 波形下，改变
空间配色不会缩短 BUSY 的固定波形时长；它能优先减少昂贵颜色转移、变化
像素、能耗、闪烁或残影。只有厂商提供 transition-specific/partial waveform
后，转移代价才可能直接对应刷新时间。

建议文件所有权：

```text
host/transition_optimizer/
schemas/epd_transition_profile.schema.json
tests/test_transition_optimizer.py
```

参数文件至少包括：

- 六个物理颜色的实测 Lab；
- 6x6 当前色 -> 下一色的光学误差；
- 6x6 峰值电流、能量、稳定时间、残影评分；
- 温度、波形版本、面板序列号和测量日期；
- 未测值必须为 null，禁止自动补造。

推荐目标函数：

```text
J = alpha * perceptual_error_CIEDE2000
  + beta  * transition_cost(current, candidate)
  + gamma * changed_pixel_penalty
  + delta * spatial_artifact_penalty
```

实现可采用“带状态代价的误差扩散”：对每个像素的六个候选色同时计算
感知误差与当前色转移代价，选择最小项，再扩散颜色误差。若多个局部颜色比例
可得到相似综合色，优先选择总转移代价最低的组合。

必须提供：

- `beta=gamma=delta=0` 时退化为普通颜色量化的测试；
- 空转移矩阵时明确拒绝或退化，不得伪造成本；
- 旧帧未知时的保守模式；
- 输出 6x6 transition histogram，供硬件实测回填；
- 画质/代价 Pareto 曲线，而不是宣称单一参数始终最佳。

## 10. C4：应用层 API 与 Web UI

建议文件所有权：

```text
app/
web/
src/application_adapter.*
```

除新增薄适配层外，不得修改 `epd_driver.*`。

应用团队只调用：

```cpp
bool epdDisplayFrame(const uint8_t *frame, size_t len);
const EpdOperationReport &epdGetLastOperationReport();
```

要求：

- 上传精确 307200 字节且 Content-Type 为 `application/octet-stream`；
- HTTP 202 只代表排队，必须轮询最终 job 状态；
- UI 在异常/断网时恢复按钮；
- 禁止连续刷新覆盖未完成任务；
- 显示 full hash、CS1/CS2 DTM hash、BUSY 超时阶段和耗时；
- 应用不得直接发送 CCSET/PON/DRF/POF；
- 应用不得自行拆左右半帧或补偿镜像。

## 11. C5：CI 与回归门禁

建议交付：

- PlatformIO release build；
- Python 主机测试；
- 检查 `EPD_ENABLE_TEST_PATTERN=0`；
- 检查生产冻结文件 SHA256 不变；
- 检查 `/api/frame` 的长度/Content-Type/二进制零字节路径；
- 检查三个 fixture 哈希；
- 检查公共头 `epd_driver.h` 不重新暴露 legacy 单控制器函数；
- 生成机器可读测试报告。

CI 只能编译和主机测试，不能把“编译通过”标记成“硬件通过”。

## 12. R1/R2：高速刷新研究边界

### R1：SPI 传帧加速

无硬件 AI 可实现参数化测试脚本和日志分析器；集成负责人实测 1/2/4/8/10
MHz，只有官方时序明确且前述档位均稳定后才考虑更高频率。每个频率必须冷启动，
使用同一 MAP_ORIENT_V1，核对两个 DTM hash、屏幕、CV、温升和 BUSY。

SPI 加速只缩短 DTM 上传，不缩短固定 DRF 波形。当前 100 kHz 两半上传各约
14.9 秒，而显色 BUSY 约 21.7 秒；正常 1 MHz 已把上传降到次要部分。

### R2：快速波形/局刷

只允许做证据研究。交付必须区分：

- MF-1750/SPD1657B 的直接证据；
- SPD1656 或其他控制器的旁证；
- E Ink 新一代 Ripple/T2000 等不兼容平台的信息。

未取得 MF-1750 厂商提供的 SPD1657B datasheet、专用 LUT、温度表和局刷流程
前，禁止枚举 LUT、改变高压、缩短相位或移植 SPD1656 PartialRAM 命令。

## 13. H0/H1/H2：PCB 小型化 TODO

### H0 阶段备份

驱动定版后由集成负责人创建只读快照和 SHA256 manifest。快照至少包含：

- `hardware/mf1750_production_v1/`；
- 驱动 v1.0 源码与固件 build tag；
- 首板实测记录和交接文档；
- 生产冻结文件原 SHA256；
- 新快照 archive 的 SHA256。

### H1 Rev B-mini 分析

其他 AI 可只读统计器件面积、封装、高度、耐压、额定/饱和电流和布局占用，
并提出候选表。不得仅按封装更小就判定等效，尤其是 L1/L2、电荷泵电容、
二极管、MOSFET 和高压间距。

Rev A1 已经是 2 层板；Rev B-mini 是否继续 2 层的核心问题是集成 ESP32、
USB 差分、电池 buck-boost/充电器与电子纸高压开关噪声后的回流、EMI、散热和
天线净空，而不是“能否画出两层走线”。

### H2 开始设计前必须由用户确认

- ESP32-S3 模块、Flash/PSRAM；
- 电池容量、最大长宽厚、保护板、接口和 NTC；
- USB-C 是否同时充电、供电和原生烧录；
- 板载或外置天线；
- 最大 PCB 长宽、目标总厚度、安装孔、FPC/USB/开关位置；
- 是否允许 4 层作为面积/EMI 对照方案；
- 刷新峰值电流和 L1/L2 实测温升。

## 14. 每个 AI 的强制移交格式

每个工作包最终必须提交：

```text
Work package ID:
Baseline commit SHA:
Branch name:
Objective:
Files changed:
Files intentionally not changed:
Assumptions:
Commands run:
Exact test output / exit codes:
Hardware tested: NO
Known limitations:
Risks requiring integrator review:
Suggested merge order:
```

不得只交一段说明而没有可复现命令，也不得把网络搜索摘要当成代码验收。

## 15. 最终合并门禁

集成负责人按以下顺序审查：

1. 确认分支基线 SHA 正确且只修改授权路径；
2. 审查算法和错误路径；
3. 本机重新运行全部测试，不采信复制的“通过”文字；
4. PlatformIO clean build；
5. 核对冻结生产文件 hash；
6. 对涉及固件的分支，在 J2-1 断电时刷写并做 GPIO/PSRAM/HTTP 安全检查；
7. 只有确实需要的变更才安排冷启动实屏测试；
8. 合并后再运行完整回归并记录 commit SHA；
9. 应用层、算法层通过不自动提升驱动/硬件版本号；
10. 任何 LUT、高压、局刷或 PCB 变更必须单独审查，不能混入应用 PR。

推荐合并顺序：D0 baseline -> C1 -> C5 -> C2 -> C3 -> C4。R1/R2 与 H 系列
保持独立，不阻塞应用层开发，也不得反向修改已验收驱动，除非形成新的硬件版本。
