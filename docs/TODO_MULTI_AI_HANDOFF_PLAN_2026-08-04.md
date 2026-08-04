# ESP32_C73 后续 TODO 与多 AI 协作计划（2026-08-04）

## 0. 进度快照（2026-08-04 集成复审）

| 工作包 | 当前状态 | 已合入来源 | 剩余门禁 |
|---|---|---|---|
| D0 驱动定版 | RC2C/V3 的 100 kHz 协议复验与正式 1 MHz MAP 真屏均通过 | 本地集成加固+真屏证据 | 已关闭；更高频率不属于 D0 |
| C1 主机帧核心 | 软件、fixtures、严格上传/结果核验和 D0 真屏物理映射完成 | `feature/host-frame-core` / `cb0a03f` + 本地加固 | 无 D0 剩余门禁 |
| C2 六色量化与抖动 | 算法、schema v2、来源与整屏授权边界完成 | `feature/color-dither` / `7cc015e` + 本地加固 | 实测 D65/2deg 六色色板与真屏主观验收 |
| C3 转移感知优化 | 保守区域/转移统计规划器完成；完整优化器未开始 | `research/fast-refresh` / `b03b7e1` | 可信旧帧状态和 6x6 实测转移矩阵 |
| C4 应用 API/Web UI | 应用 API/Web UI、HTTP adapter 与一次性硬件授权的软件合同完成 | 本地集成加固 | 设备端认证方案、普通图片端到端实刷 |
| C5 CI 与回归门禁 | 203 项回归、合同、PlatformIO 与主线 CI run 30917129233 通过 | `feature/host-ci` / `c59a1f2` + 本地加固 | 后续变更继续逐提交运行；CI 不替代硬件结论 |
| R1 SPI 扫频 | 严格离线分析器完成；参数化固件 action 未实现 | `research/fast-refresh` / `b03b7e1` + 本地加固 | 独立诊断固件及 1/2/4/8/10 MHz 冷启动扫频 |
| R2 快速波形/局刷 | 证据边界与控制器中立规划器完成 | `research/fast-refresh` / `b03b7e1` | SPD1657B/面板 OTP 厂商资料；取得前禁止实装 |
| H0 阶段备份 | Git/冻结文件基线已建立；D0 已通过但硬件 v1.0 快照未封版 | RC1/冻结基线 `3033da0` | 生成 archive/hash；tag 需用户明确授权 |
| H1/H2 Rev B-mini | TODO，未开始设计 | 无 | 先完成 H0，并由用户确认模块、电池、USB-C、天线、机械约束 |

远端完整集成分支 `integration/host-fast-refresh-ci-color` 的最新点为 `dd711c9`，
[GitHub Actions run 30863009577](https://github.com/oceanye/ESP32_C73-MF1750/actions/runs/30863009577)
成功。本机已经 fetch、独立复现 64 项原始回归，并把该分支快进合入本地
`main`；冻结生产目录没有变化。`dd711c9` 本身仍是 RC1/V1；随后在本地集成的
RC2B/V2、主机工具、颜色与契约加固已通过当时的本地回归、repository contract、
`compileall` 和 PlatformIO clean build；随后 RC2B 真屏发现 post-PSR 假门禁，
RC2C/V3 随后完成 100 kHz 与正式 1 MHz MAP_ORIENT_V1 真屏验收；主机修正点
`2b19f75` 的 203 项回归、PlatformIO 与 GitHub CI run `30917129233` 全部通过。
真屏结论只来自同次 job/report 与用户对画面、电源、温度的确认，不能由 CI 替代。

## 1. 目的与当前优先级

MF-1750 Rev A1 驱动层 D0 已完成验收。后续执行顺序为：

1. 保持 D0 的提交、CI、真屏和安全收尾证据可追溯；
2. 固化 H0 驱动快照与 hash；硬件验收标签仍需用户明确授权；
3. 再移交应用团队；
4. C2 色板、R1 扫频和 C4 应用验收分开执行，不能互相冒充通过；
5. C3 等待实测转移矩阵，R2 等待厂商资料，H1/H2 等待用户输入。

剩余 TODO 不得修改已冻结的 Rev A1 生产文件，也不得绕过硬件或厂商资料门禁。

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

## 4. Git 当前状态与集成策略

工作区已经是可用 Git 仓库，`origin` 指向私有 GitHub 仓库。Rev A1 驱动 RC1、
硬件源文件和冻结生产清单的基线为 `3033da0`；C1/C2/C5/R1/R2 的远端集成点为
`dd711c9`，现已合入本地 `main`。RC2C/V3 已完成协议与 1 MHz 真屏验收；
`mf1750-driver-v1.0-hw-verified` 标签仍只在用户明确授权创建 tag 后发布，不能仅由
软件、文档或 CI 自动创建。

后续规则：

1. 每次提交和推送前运行 repository contract，冻结目录的文件集合、manifest
   基线指纹和二进制 hash 必须全部通过；
2. 每个新工作包基于已推送的明确 commit SHA 建分支，不得基于聊天中间状态；
3. 其他 AI 不直接刷写、调用设备刷新接口或推送 `main`；
4. 集成负责人审查授权路径、测试和 handoff 后才合并；
5. D0 真屏验收完成后另建只读快照和硬件验收标签；
6. 应用、算法或 CI 通过不得提前创建硬件 v1.0 标签。

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
| D0 | 驱动 v1.0 定版 | 否，只读复审可委托 | 当前任务 | PSRAM 日志、MAP_ORIENT_V1、1 MHz 规范帧 |
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
- PON/DRF/POF 均先观察 BUSY assertion 再等待 idle；缺 assertion 或超时都返回
  失败并执行安全收尾；POF 后的 PSR 写入记录等待与 BUSY 采样，但不要求再次
  assertion；
- result-bearing job 只发布匹配非零 u32 operation ID 的不可变完整报告快照；
- 刷新结束后 SPI 释放且所有面板侧输出保持低电平；
- 应用只需包含 `epd_driver.h`，诊断接口隔离到 `epd_diagnostics.h`。

必须通过的 fixtures：

| Fixture | Full FNV-1a | CS1 FNV-1a | CS2 FNV-1a |
|---|---:|---:|---:|
| global-v-bars | `0x908478A5` | `0x61BCF1C5` | `0xA3446735` |
| global-h-bars | `0x7DD055C5` | `0x855679C5` | `0x855679C5` |
| MAP_ORIENT_V1 | `0x9D04142D` | `0xF26832DD` | `0xFE199FF5` |

当前已实测 global-v-bars 完整六色正确且中缝清晰；RC2B/V2 的 100 kHz
MAP_ORIENT_V1 方向、颜色、中缝、哈希和 PON/DRF/POF BUSY 也已通过，但其
post-PSR 严格 BUSY 门禁造成软件假失败。剩余验收为 RC2C/V3 重新刷入后的低速
协议复验，以及通过正式 1 MHz `/api/frame` 链路发送同一个规范帧。

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

当前实现会在 CI artifact `host-contract-reports` 中同时保存
`host-test-report.json` 与 `repo-contract-report.json`；二者都固定声明
`hardware_tested:false`。

CI 只能编译和主机测试，不能把“编译通过”标记成“硬件通过”。

## 12. R1/R2：高速刷新研究边界

### R1：SPI 传帧加速

无硬件 AI 可实现参数化测试脚本和日志分析器；集成负责人实测 1/2/4/8/10
MHz，只有官方时序明确且前述档位均稳定后才考虑更高频率。每个频率必须冷启动，
使用同一 MAP_ORIENT_V1，核对两个 DTM hash、屏幕、CV、温升和 BUSY。

SPI 加速只缩短 DTM 上传，不缩短固定 DRF 波形。当前 100 kHz 实测两半上传各约
14.9 秒，而显色 BUSY 约 21.7 秒；1 MHz 的线性估算约为每半 1.5 秒，但 RC2C
规范帧 1 MHz 尚未完成真屏验收，不能把估算写成既成结果。

### R2：快速波形/局刷

只允许做证据研究。交付必须区分：

- MF-1750/SPD1657B 的直接证据；
- SPD1656 或其他控制器的旁证；
- E Ink 新一代 Ripple/T2000 等不兼容平台的信息。

未取得 MF-1750 厂商提供的 SPD1657B datasheet、专用 LUT、温度表和局刷流程
前，禁止枚举 LUT、改变高压、缩短相位或移植 SPD1656 PartialRAM 命令。

## 13. H0/H1/H2：PCB 小型化 TODO

### H0 阶段备份

当前私有 Git 基线和冻结生产 manifest 已构成阶段性可追溯备份，但还不是
“硬件 v1.0 已验收”快照。D0 通过后由集成负责人创建只读 archive、SHA256
manifest 和硬件标签。快照至少包含：

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
6. 对涉及固件的分支，仅在用户明确确认后、J2-1 断电时刷写，并做
   GPIO/PSRAM/HTTP 安全检查；
7. 只有确实需要的变更才安排冷启动实屏测试；
8. 合并后再运行完整回归并记录 commit SHA；
9. 应用层、算法层通过不自动提升驱动/硬件版本号；
10. 任何 LUT、高压、局刷或 PCB 变更必须单独审查，不能混入应用 PR。

现有 C1/C2/C5 与 R1/R2 离线代码已经进入集成线，D0 软件与真屏门禁均已完成；
下一步封存 H0。之后优先移交 C4 应用层；C2
真屏色彩验收和 R1 扫频可独立推进。C3 必须等待可信 6x6 转移矩阵，R2 必须等待
厂商资料，H1/H2 必须等待用户确认 Rev B 输入。任何后续工作不得反向修改已验收
驱动，除非形成独立且有证据支持的新硬件/固件版本。
