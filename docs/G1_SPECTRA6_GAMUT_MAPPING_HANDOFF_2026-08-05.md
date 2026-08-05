# G1 Spectra 6 抖动前色域映射与照片优化 Handoff（2026-08-05）

状态：`READY FOR REMOTE AI / SOFTWARE-ONLY / HARDWARE CALIBRATION BLOCKED`

> 本工作包的目标不是再增加一种抖动算法，而是在现有 C2 六色量化之前加入
> 可审计、可复现、由面板 profile 驱动的亮度与色域映射。没有合格的实测
> artifact 时，可以完成代码、schema、实验预览和离线测试，但不得声称颜色已经
> 实屏校准，也不得解锁正式整屏上传。

## 0. 工作包元数据

```text
Work package ID: G1
Authoring baseline: local main 0dfdbd7
Execution baseline: 以集成负责人提供的、包含本 Handoff 的精确 commit 为准
Suggested branch: feature/spectra6-gamut-mapping
Primary execution environment: host/server; no hardware required
Hardware tested: NO
Target panel contract: 1024x600, 4bpp, 307200 bytes
Legal physical codes: 0=black, 1=white, 2=yellow, 3=red, 5=blue, 6=green
Canonical colour engine: host/color_pipeline
Formal-colour blocker: controlled D65/2deg panel and mixture measurements
```

远程 AI 开始工作时必须先记录：

```powershell
git rev-parse HEAD
git status --short --branch
```

若当前提交不包含本文件，或工作区存在会与本工作包重叠的未知修改，应停止并向
集成负责人报告，不得自行换一个旧基线继续实现。未跟踪的 `.test-output/` 属于
现有工作区内容，不得读取、删除、清理或提交。

## 1. 背景与结论

用户提供的文章[《只靠抖动是不够的》](https://www.einkframe.com/2025/12/11/spectra-6-gamut-mapping-zh/)
提出了正确的工程顺序：先将源图映射到 Spectra 6 实际可表现的亮度和综合色域，
再把连续目标颜色转成六种物理像素的空间分布。只更换 Floyd–Steinberg、Atkinson、
Stucki 或 JJN，主要改变纹理和误差传播，不能单独解决过暗、过曝、肤色偏差、
绿色层次断裂或饱和区域细节丢失。

该文章只能作为技术方向，不能作为规格书、测量数据或可复现算法来源。它没有公开：

- 面板六色 XYZ/Lab 或光谱反射率；
- 照明、观察者、测量几何、面板批次和温度；
- 色域边界、黑白点、映射函数、LUT 或优化目标；
- “绿＋黄”等混色比例的求解方法；
- 抖动参数、测试集、真屏 RAW、Delta E 结果或显著性数据。

因此不得从文章插图反推坐标，不得复制一个固定“绿＋黄”规则，也不得把 ISFR
宣传效果写成项目已经验证的结论。ICC 同样指出，照片向较小输出色域映射时通常
需要感知渲染，并且对比度、细节、色相和饱和度之间不存在唯一最优取舍：

- [ICC profile 与 rendering intent 说明](https://www.color.org/iccprofile.xalter)；
- [ICC.1:2022](https://www.color.org/specifications/ICC.1-2022-05.pdf)；
- [E Ink Spectra 6 官方发布说明](https://www.eink.com/news/detail/E-Ink-Launches-E-Ink-Spectra-6-a-Revolutionary-New-Color-ePaper-for-Paper-Sign-Replacement)。

## 2. 当前仓库事实

### 2.1 已有能力

- `host/color_pipeline/color.py` 已实现 IEC sRGB 传递函数、线性 RGB、D65 XYZ、
  D65/2° Lab 和 CIEDE2000；
- `host/color_pipeline/pipeline.py` 已有最近色、serpentine Floyd–Steinberg、
  Atkinson、Bayer 8x8 和确定性 hashed threshold；
- C2 已有透明像素线性光白底合成、白色保护、边缘保护、文本模式、规范帧打包、
  预览 PNG、颜色使用率、输入/帧 hash 和确定性报告；
- `host/color_pipeline/palette.py` 的 palette schema v2 已绑定物理色码、D65/2°、
  measurement ID、artifact SHA256 和 canonical hash；
- `host/application/pipeline.py` 已经对未校准 palette、正式上传用途、报告身份和
  frame hash 执行 fail-closed 校验；
- 主机 Web/API、离线预览和设备适配层已经存在；
- 当前使用场景是低频刷新照片相框，复杂图片处理应优先放在 host/server，
  ESP32-S3 只接收确定性最终帧并缓存，不为本工作包升级 ESP32-P4。

### 2.2 当前关键缺口

1. `host/color_pipeline/palettes/reference_srgb_v1.json` 明确是
   `calibrated=false`、`calibration=null` 的数学 sRGB 锚点，不是 MF-1750
   真屏测量；
2. 当前主机路径把规范化图像直接送入最近色/误差扩散，没有独立的 pre-dither
   tone/gamut mapping；
3. 当前报告没有 gamut profile、rendering intent、映射算法版本、映射强度、
   out-of-gamut 比例、亮度/色度压缩量和 mapped-raster 身份；
4. `src/main.cpp` 的设备内嵌网页仍硬编码另一套近似 RGB palette、RGB 欧氏距离和
   固定 gamma/饱和度处理，与主机 Lab/CIEDE2000 管线并不等价；
5. 当前 ordered 模式用最近两色的距离比例作概率，这不是六色面积混合权重求解；
6. hashed threshold 明确不是 blue noise；
7. 浏览器规范化路径不能可靠保留原图 ICC/宽色域 provenance，部分 host fallback
   缩放质量也不适合作为正式照片路径；
8. 当前预览是代码色的显示器模拟，不是环境光下真屏的物理复现。

## 3. 必须区分的五层概念

实现者不得把以下概念混为一谈：

1. **Palette calibration**：测量六个物理纯色色块，得到带条件和 provenance 的
   XYZ/Lab；
2. **Gamut characterization**：测量典型双色/多色面积混合及图案，建立实际可达
   综合色点集或模型；
3. **Gamut mapping**：将源图连续颜色和亮度压缩到目标模型内；
4. **Halftoning/dithering**：把映射后的连续目标实现为六种物理像素的空间分布；
5. **Soft proof**：在普通显示器上模拟最终代码流的观感，只能作为近似预览。

六个纯色色点可以支持一个 `experimental linear-XYZ convex model`，但不能据此
宣称已经掌握真实空间混色色域。Lab、Delta E 或 CIE 1931 `xy` 中的几何距离也
不能直接当作物理混色比例。

## 4. 本工作包目标

高级 AI 应完成所有不依赖真屏测量的软件工作，而不是只提交调研报告：

1. 设计并实现独立、可关闭的 pre-dither gamut mapping 层；
2. 定义严格的 gamut profile/schema、provenance、canonical hash 和授权门禁；
3. 以 `host/color_pipeline` 为唯一 canonical colour engine；
4. 支持至少三种版本化 rendering preset；
5. 保持旧 C2 行为可选择且 byte-for-byte 回归稳定；
6. 把新映射身份纳入 application artifact、报告和正式用途校验；
7. 在 host Web UI 提供原图、映射后连续预览、最终六色预览的对照；
8. 生成未来实测所需的离线纯色/混色色卡和 manifest，但不调用设备；
9. 提供单元、性质、golden、集成、消融和性能测试；
10. 输出完整的设计决策、已知限制和未来硬件标定输入格式。

## 5. 授权范围与永久保护边界

### 5.1 允许修改

在确有需要且保持职责清晰时，可修改或新增：

```text
host/color_pipeline/
host/application/
app/
web/
tests/
tools/                         # 仅离线色卡/测量 artifact 工具
docs/
README.md
```

### 5.2 默认禁止修改或执行

- 不修改 `src/`，尤其不得把第三套 gamut/palette 算法复制到 `src/main.cpp`；
- 不修改 `hardware/`，特别是 `hardware/mf1750_production_v1/production/`；
- 不改变 GPIO、R15/R16、CS1/CS2、色码、左右映射、扫描方向或 nibble packing；
- 不修改 SPD1657B LUT、波形、电压、时钟或 BUSY 门禁；
- 不刷写 COM8，不访问设备 `/api/frame`，不触发任何真屏刷新；
- 不下载网络照片，不调用相册服务，不加入非确定性的在线推理依赖；
- 不直接提交或推送 `main`，不创建硬件 tag；
- 不清理用户已有未跟踪文件或无关 dirty worktree；
- 不把软件 CI、预览 PNG 或模拟 Delta E 写成 `Hardware tested: YES`。

如实现必须修改 `src/`、设备协议、正式上传授权模型的基本语义或引入强制第三方
运行时依赖，应先停下，在 Handoff 中提出独立设计变更请求，不能自行扩大范围。

## 6. 目标架构

```text
原始文件 + embedded ICC/EXIF
            ↓
可信解码、方向修正、source-profile 记录
            ↓
高质量裁剪/旋转/缩放到 1024x600
            ↓
规范 working raster（显式 sRGB/linear-light 合同）
            ↓
黑白点与亮度范围映射
            ↓
pre-dither gamut mapping + rendering intent
            ↓
连续 mapped target + canonical identity
            ↓
六色面积权重/候选选择
            ↓
确定性 halftoning/dithering
            ↓
合法色码 → 307200-byte 4bpp frame
            ↓
从最终 code stream 反渲染 preview + 完整 report
```

核心库继续接受已经规范化的 `RasterImage`，不得让颜色核心隐式依赖浏览器。
原始文件 ICC/EXIF 的读取应位于 application/decode adapter；核心不强制依赖 Pillow
或 LittleCMS。若环境不能可靠转换 embedded ICC，必须明确 fail closed 或记录由
调用者显式授权的 sRGB assumption，不能静默丢弃 profile 后声称颜色可复现。

## 7. Gamut profile 合同

应新增独立于 palette schema v2 的 gamut profile。它引用 palette 的 canonical
SHA256，不复制或重新定义六个物理色码。具体 JSON 形状可在 ADR 中确定，但至少要
严格包含：

- schema version、profile ID、profile version、pipeline compatibility；
- underlying palette ID 和 canonical SHA256；
- model kind，例如 `linear_xyz_convex_v1`、`measured_point_cloud_v1`；
- characterization level，例如 `reference`、`measured_primaries`、
  `measured_mixtures`；
- illuminant、observer、measurement geometry、backing、instrument；
- panel model、panel ID/batch、firmware commit、waveform version；
- temperature、humidity和测量日期；缺失值必须显式为 null，不得猜测；
- measurement ID、原始 artifact SHA256 和数据单位；
- pure-colour/mixture sample 引用、空间 mask ID、面积比例；
- rendering presets 的版本化参数；
- canonical serialization scope 和 canonical SHA256；
- 信任说明：hash 只是审计指纹，不是签名或 trust store。

严格要求：

- 未知字段、错误类型、NaN、inf、越界值、重复样本、非法比例、hash 不符全部拒绝；
- `reference-srgb-v1` 永远不得被改成 calibrated；
- 示例 profile 必须命名并标记为 `synthetic/uncalibrated/experimental`；
- profile 的正式资格必须由 provenance 和既有 palette 门禁推导，不能靠一个容易
  篡改的 `formal=true` 布尔值获得；
- 启用 mapping 的正式用途必须同时具备合格的 calibrated palette 和对应的
  characterized gamut profile；panel/batch、palette hash、firmware/waveform、
  温度区间及所使用的 halftone pattern 必须与测量 artifact 匹配；
- 新门禁只能附加在现有 calibrated palette、frame、hash 和 authorization 门禁之上，
  不能替换或削弱它们；
- 缺少 mixture measurement 时，模型必须在报告中明确标为 approximation。

## 8. 算法要求

### 8.1 兼容与关闭路径

- 增加明确的 `mapping=none/legacy` 路径；
- mapping 关闭时，现有 C2 fixtures、frame bytes、preview 和 hash 必须保持不变；
- 在没有显式 profile/intent 时不得悄悄改变默认正式输出；
- uncalibrated profile 只能用于受控小图或明确的 offline preview。

### 8.2 第一版可交付模型

第一版应实现一个参数化、可替换的保守模型，而不是冒充最终物理模型：

1. 将输入和面板数据放入明确记录的 XYZ/Lab/linear-light 空间；
2. 使用单调、连续的 tone curve 把源亮度映射到 profile 黑白点范围；
3. 保持 neutral axis，避免中性灰被无故染色；
4. 对超出近似目标色域的颜色进行平滑压缩，而不是逐通道硬裁剪；
5. 明确处理 hue、L*、chroma 的权重及取舍；
6. out-of-gamut 结果必须落入所声明的近似模型范围；
7. in-gamut identity/soft-compression 行为由 rendering intent 明确定义；
8. 所有随机过程必须有显式 seed；相同输入合同必须生成逐字节相同的帧。

允许用六个实测纯色的 XYZ 面积凸域作为第一版 approximation，但命名、报告和 UI
必须显示其限制。不得只在二维 `xy` 马蹄图中压缩，也不得把 Delta E 距离比例当作
物理面积比例。

### 8.3 Rendering presets

至少提供以下三个版本化 preset，名称可在实现中规范化：

- `faithful`：优先色相和综合色差，保守处理已经可达的颜色；
- `photographic`：优先整体层次、肤色、阴影/高光细节和自然照片观感；
- `vivid`：允许牺牲部分色差，优先饱和度和视觉冲击，但仍必须保持亮度有界。

另保留明确的 `artist/palette-exact` 设计入口：已经由艺术家指定为物理六色代码的
内容不得再次经过感知映射。第一版可以只完成合同和测试，不得用 RGB 近似猜测
“艺术家已经指定色码”。

“纯绿用绿＋黄”只能成为某个 profile/preset 求解出的可解释结果，不能硬编码为
全局规则。

### 8.4 六色混合与抖动

- 第一版可以复用当前 deterministic error diffusion，但必须先应用独立 gamut map；
- 应设计非负、权重和为 1 的六色面积权重接口，目标函数至少区分综合色差、L*、
  hue/chroma 和颗粒/颜色数量正则；
- ordered/blue-noise 路径不能继续用“最近两色 Delta E 距离比”冒充最优混合；
- 当前 hashed threshold 不得重命名为 blue noise；只有具有可验证频谱/掩模来源的
  实现才可标记为 blue noise；
- 新增真实蓝噪声或多色权重求解可以作为第二提交，但 schema 和测试接口应在第一版
  留出兼容扩展点；
- 文本、边缘和受保护白色不得因新误差传播而退化。

## 9. Canonical identity 与报告

改变 report 合同时必须显式升级 schema，并同步所有 validator；不得在 schema v2
下静默增加语义不同的字段。新报告至少记录：

- 原文件 SHA256（若 application 层持有）、规范 raster SHA256；
- source ICC/profile ID/hash、profile assumption、decoder 和 EXIF handling；
- resampler、fit/crop/rotation 及其参数；
- gamut profile ID/version/canonical SHA256/characterization level；
- mapping algorithm/version、rendering intent、强度和所有有效参数；
- 输入 out-of-gamut 像素数/比例及判定模型；
- tone/chroma 压缩统计、clipping/fallback 统计；
- mapped continuous raster 的规范身份与 hash；
- dither、seed、edge/white/text 选项；
- palette ID/hash、六色使用率、最终 frame SHA256/FNV；
- `hardware_tested:false` 和 soft-proof 限制声明。

mapped raster 的规范编码、舍入规则和 hash scope 必须在 ADR 中固定。不能对未规范化
的 Python 浮点对象直接做不稳定序列化。相同 source bytes、规范化 raster、palette、
gamut profile、options 和 seed 必须得到相同的 307200-byte frame、preview、report
身份和 hash。

## 10. Host API 与 Web UI

生产方向是 host/server 单一颜色引擎，UI 不得复制一份 JavaScript palette、LUT 或
混色求解器。UI 应通过同一服务获得 artifact，或只渲染服务返回的 mapped preview
和最终 code-stream preview。

最低 UI 要求：

- 保留原图拖动、缩放、旋转和 fit/crop；
- 显示“原图”“映射后连续目标”“最终六色代码”三种可切换或并排预览；
- 可选择 profile、rendering preset、mapping strength 和 dither；
- 显示 profile ID/version、校准状态、算法版本和 simulation 警告；
- profile 或选项变化后立即撤销旧 artifact/上传授权；
- 未校准 profile 下，正式上传继续禁用；
- 最终六色预览必须从实际 code stream 反渲染，不能走旁路重新量化；
- 预览继续按照 1024x600、163.84x97.20 mm 和非方像素几何显示；
- 不得把显示器 soft proof 称作真屏色差或真实环境光效果。

本工作包默认不修改设备内嵌 `src/main.cpp` 页面。应在设计中给出后续收敛方案：
设备页面只负责上传原图到 canonical server，或接收 server 已生成的 artifact；不得
长期维护第三套颜色实现。

## 11. 离线标定图与未来测量输入

远程 AI 应实现或设计一个**只生成文件、不连接设备**的标定图工具。它至少支持：

- 六个物理纯色色块；
- 15 组无序双色组合；
- 可配置面积比例，例如 25%、50%、75%；
- 多种明确命名的空间 mask/pattern；
- 黑白阶梯、关键绿黄/红黄/蓝绿/白色混合、综合色卡；
- 可配置的多色样本，以及与拟合样本分离的 validation/holdout 样本；
- 规范 1024x600/4bpp、合法色码、frame hash、pattern ID 和 manifest；
- 固定 seed 和可复现输出；
- 不使用文字区域中的非法颜色，不依赖设备扫描方向补偿。

未来由具有硬件环境的集成负责人逐帧授权显示和测量。测量 artifact 至少绑定：

```text
panel model / panel ID / batch
firmware commit / waveform version
temperature / humidity
illuminant / observer / geometry / backing
instrument / calibration date
patch ID / mask ID / area ratios
initial colour / recovery sequence / settle time
XYZ / Lab / optional spectral reflectance
repeat count / uniformity / uncertainty
raw file SHA256 / operator / timestamp
```

在这些数据返回之前，AI 应完成 schema、parser、synthetic fixtures 和 fail-closed
行为，不得因缺少硬件数据而停摆，也不得编造数据填空。

## 12. 测试与消融要求

### 12.1 单元与性质测试

至少覆盖：

- profile/schema 的正常、缺字段、未知字段、非法类型、NaN/inf、hash 不符；
- tone curve 单调性、端点、黑白点、neutral-axis 保持；
- in-gamut identity 或指定 soft-compression 行为；
- out-of-gamut 有界映射；
- hue/L*/chroma 取舍的固定 synthetic cases；
- 透明合成、白色保护、文本、边缘和极端输入；
- mapping 关闭时旧 golden hash 完全不变；
- 相同输入的跨运行逐字节确定性；
- frame 长度、packing、合法色码和 preview/frame 一致；
- uncalibrated profile 正式用途 fail closed；
- application artifact/validator 无法通过字段篡改获得授权。

### 12.2 消融矩阵

必须固定同一输入、palette 和 dither，至少比较：

```text
legacy mapping + legacy dither
new mapping    + same legacy dither
new mapping    + alternate dither
```

先证明收益来自 gamut mapping，再讨论抖动差异。不得用不同裁剪、不同 gamma、
不同 palette 和不同 dither 的两张主观图片宣称 mapping 有效。

在无真屏 profile 时，指标只能用于 synthetic/model-space 回归，不能写成真实面板
Delta E。应报告 out-of-gamut ratio、色调压缩量、六色使用率、结构/边缘统计、运行
时间和峰值内存，并明确哪些指标是模型内指标。

### 12.3 性能

记录 1024x600 整帧在当前机器的运行时间和峰值内存。相框是低频刷新场景，不为
追求毫秒级速度牺牲确定性或颜色质量；但不得引入明显的逐像素高分配或无界求解。
第一版给出基线与瓶颈，必要时用版本化 3D LUT/缓存优化，并验证优化前后帧一致。
mapping-off 不应出现有意义的性能回退；mapping-on 若相对旧流程超过约 2 倍，应在
Handoff 中量化原因、给出优化结果，或明确请求集成负责人接受该取舍。

### 12.4 回归命令

至少运行并记录实际退出码和测试计数：

```powershell
python -m unittest tests.test_color_pipeline -v
python -m unittest discover -s tests -v
python -m compileall -q host app tests tools
python tools/check_repo_contract.py --output <temporary-path>/repo-contract-report.json
node --check web/app.js                 # 若修改 web/app.js
git diff --check
```

报告文件写入新建的系统临时目录，不覆盖仓库中的现有机器报告，不使用或清理当前
`.test-output/`。本工作包不修改 firmware，因而 PlatformIO 不是必需验收；若实现者
意外修改了 `src/` 或 `platformio.ini`，视为范围违规，而不是通过编译即可接受。

## 13. 分阶段交付

### G1-A：只读审计与 ADR

- 完整阅读本 Handoff、C2/C4 Handoff、palette/pipeline/application 合同；
- 输出当前数据流、两套颜色实现差异、拟修改文件和兼容策略；
- 冻结 terminology、profile schema、mapped-raster identity 和 report 版本策略。

### G1-B：核心 profile 与 gamut mapper

- 实现严格 profile parser/hash/provenance；
- 实现 `none/legacy` 和至少一个 experimental mapper；
- 实现三个 rendering presets；
- 保留 C2 golden bytes，增加性质与错误路径测试。

### G1-C：应用合同、原图规范化与 UI

- 将 gamut identity 纳入 application artifact 和 validator；
- 明确 ICC/EXIF/resampler provenance；
- UI 使用 canonical server 输出，提供三阶段预览和 fail-closed 警告；
- 不修改设备固件或调用设备。

### G1-D：混色、色卡与消融

- 提供六色面积权重接口和可审计目标函数；
- 生成离线纯色/混色色卡与 manifest；
- 完成映射前后消融、性能报告和示例预览；
- 所有示例继续标记 synthetic/uncalibrated。

### G1-H：未来硬件标定与真屏验收

该阶段不属于远程 AI 当前授权。由集成负责人取得用户逐阶段授权后执行测量、回填
profile、真屏 A/B、RAW/测色、主观观察和正式上传门禁评审。远程 AI 只能提供分析
工具和数据导入，不得声称 G1-H 已完成。

真屏阶段必须先测量仪器噪声和面板重复性，再冻结 validation 阈值和 holdout 数据。
可把重复显示 Delta E00、holdout median/P95、灰阶 L* 单调性、肤色/高光/阴影、
颗粒度、残影和恢复能力作为指标；任何具体阈值都只能在基线噪声可知后确认，不能
查看候选结果后事后放宽。

## 14. 完成定义

远程 AI 的软件工作只有同时满足以下条件才可移交：

- canonical host pipeline 有独立、可关闭、版本化的 gamut mapping；
- legacy-off 路径逐字节兼容；
- reference palette 仍为 uncalibrated，未出现伪造 measurement；
- gamut profile 有严格 schema、provenance、hash 和附加 fail-closed 门禁；
- 三个 rendering presets 有明确行为与测试；
- UI 不复制第三套量化算法，预览来自 canonical artifact/code stream；
- mapped raster、frame、preview 和 report 可复现且身份绑定；
- 消融矩阵证明测试方法能分离 mapping 与 dither；
- 离线标定图工具不访问硬件且输出可追溯 manifest；
- 全仓回归、repository contract、compileall、Web 语法和 `git diff --check` 通过；
- 冻结生产目录、驱动、色码、mapping 和用户未跟踪文件没有变化；
- Handoff 写明 `Hardware tested: NO`、尚缺的真实测量以及不能声称的结论；
- 所有修改只提交到独立 feature branch；未获授权不 push、不合并 main。

移交报告必须包含：

```text
Branch name
Baseline commit SHA
Final commit SHA(s)
Files changed
Files intentionally not changed
Architecture and schema decisions
Commands run
Exact test counts / outputs / exit codes
Benchmark environment and results
Hardware tested: NO
Known limitations
Remaining calibration artifacts
Risks requiring integrator review
Suggested merge order
```

## 15. 可直接复制给高级 AI 的完整提示词

```text
你现在是本项目的高级色彩科学、图像算法和安全流水线工程师。请在
ESP32_C73 仓库内完成 G1“Spectra 6 抖动前色域映射与照片优化”工作包。
不要只调研，也不要只增加一种抖动；请完成所有不依赖真实面板测量的软件工作，
并在缺少实测数据处保持严格 fail-closed。

开始前：
1. 完整阅读 docs/G1_SPECTRA6_GAMUT_MAPPING_HANDOFF_2026-08-05.md，不得只读摘要。
2. 完整阅读：
   - docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md
   - docs/C4_APPLICATION_HANDOFF_2026-08-04.md
   - docs/TODO_NETWORK_RANDOM_PHOTO_PIPELINE.md
   - host/color_pipeline/README.md
   - host/color_pipeline/color.py
   - host/color_pipeline/palette.py
   - host/color_pipeline/pipeline.py
   - host/color_pipeline/palettes/reference_srgb_v1.json
   - host/application/pipeline.py
   - app/server.py
   - web/index.html、web/app.js
   - src/main.cpp 中现有网页颜色算法（只读对照）
3. 运行并记录 git rev-parse HEAD、git status --short --branch。
4. 确认当前提交包含 G1 Handoff；从集成负责人指定的精确基线创建
   feature/spectra6-gamut-mapping。不要直接在 main 工作，不要自行换旧基线。
5. 保留所有用户已有修改和未跟踪文件；不要读取、删除、清理或提交 .test-output/。

已知硬合同：
- 面板 1024x600、4bpp、精确 307200 bytes。
- 合法物理色码只有 {0,1,2,3,5,6}，分别为黑、白、黄、红、蓝、绿。
- host/color_pipeline 是唯一 canonical colour engine。
- reference_srgb_v1.json 明确 calibrated=false/calibration=null，它不是面板测量。
- 当前没有合格的 MF-1750 六色或混色色块实测 artifact。
- 设备网页存在另一套硬编码 RGB 算法，但本工作包默认禁止修改 src/；不要复制第三套实现。
- 当前场景为低频照片相框，处理放 host/server；不需要 ESP32-P4。

核心任务：
A0. 先做只读审计，输出数据流、现有门禁、两套算法差异、拟修改文件和 ADR；
    之后继续实施，不要停在分析。
A1. 定义严格的 gamut profile/schema。它必须引用 palette canonical hash，记录
    model kind、characterization level、测量条件、panel/firmware/waveform/temperature、
    measurement artifact/hash、mixture samples、preset 参数和自身 canonical hash。
    缺失数据显式 null；类型、有限值、未知字段和 hash 全部 fail closed。
A2. 在现有 C2 quantization 前实现独立、可关闭、版本化的 gamut mapper：
    - mapping=none/legacy 必须保持旧 frame/preview/hash byte-for-byte；
    - 单调黑白点/亮度映射、neutral-axis 保持、平滑 chroma/gamut compression；
    - 至少 faithful、photographic、vivid 三种 preset；
    - 第一版可用六色 XYZ 凸域作为明确标注的 experimental approximation；
    - 不得只在 CIE xy 二维图处理，不得用 Delta E 距离直接当混色比例；
    - 不能硬编码“绿色=绿+黄”。
A3. 设计/实现非负且权重和为 1 的六色面积混合接口；第一版可继续复用现有
    deterministic diffusion，但必须在映射之后。当前 hashed threshold 不得冒充
    blue noise。若实现真正蓝噪声，必须记录掩模来源、版本、seed 和确定性测试。
A4. 将 gamut identity 纳入 application artifact、report 和 validator。改变 report
    语义时显式升级 schema；记录 source ICC assumption、decoder/resampler、profile
    ID/hash、algorithm/version/intent/params、out-of-gamut ratio、tone/chroma 统计、
    mapped-raster hash、palette/frame/preview identity 和 hardware_tested:false。
A5. 原始文件 ICC/EXIF 处理放 application adapter，核心继续接受规范 RasterImage。
    如果不能可靠转换 embedded ICC，必须 fail closed 或记录显式 sRGB assumption，
    不能静默丢弃。保持依赖可选且有清晰 fallback；不要无审查增加强制依赖。
A6. 更新 host Web UI：保留拖动/缩放/旋转，显示原图、映射后连续目标、最终六色
    code-stream preview；提供 profile、preset、strength、dither 控件和显著的
    uncalibrated/simulation 警告。UI 必须消费 canonical server artifact，不得复制
    palette/LUT/gamut 算法。选项变化立即撤销旧 artifact；未校准时正式上传仍禁用。
A7. 提供只生成文件、不连接设备的标定图工具：六个纯色、15 组双色、可配置
    25/50/75% 面积比例、多种 pattern、固定 seed、规范帧/hash/manifest。只生成
    offline artifacts，不调用 /api/frame。
A8. 提供单元、性质、golden、集成、消融和性能测试。消融必须固定同一输入、
    palette 和 dither，比较 legacy mapping 与 new mapping，再单独比较 dither。
    没有真屏 profile 时，Delta E 只能称为 model-space/synthetic 指标。

强制安全边界：
- 文章《只靠抖动是不够的》只作为方向，不能作为坐标、LUT、混色比例或规格来源。
- 绝不把 reference-srgb-v1 改成 calibrated，不补造 Lab/XYZ/测量 hash。
- 缺少 mixture measurements 时，只能 experimental/offline preview，不能声称真实色域。
- 新门禁只能叠加在 calibrated palette、provenance、尺寸、合法色码和 hash 门禁之上。
- 最终 gamut mapping、dither 和 packing 必须确定性、版本化；AI 只可用于上游选图/
  裁剪，而且必须冻结 bbox、模型版本和规范 raster hash。本工作包不引入在线 AI。
- 不修改 src/、hardware/、GPIO、驱动、波形、电压、mapping 或 packing。
- 不刷 COM8、不访问设备、不推送图片、不运行真屏测试。
- 不 push main、不创建 tag；只在 feature branch 提交，push 需另行授权。
- 所有预览显著标为 simulation；所有报告保持 Hardware tested: NO。

最低验收：
- mapping off 保持现有 golden bytes/hash；
- profile 错误、NaN/inf、hash 不符、未校准正式用途全部拒绝；
- tone curve 单调、neutral 保持、out-of-gamut 映射有界；
- 相同 source/raster/palette/gamut/options/seed 逐字节输出相同 307200-byte frame；
- 输出只含合法色码，preview 从最终 code stream 反渲染；
- application 字段篡改不能绕过授权；
- 同 dither 的 mapping 前后消融和整帧 benchmark 完成；
- 全仓现有测试和新增测试全部通过；冻结生产目录与用户文件无变化。

至少执行并报告实际计数、输出和退出码：
python -m unittest tests.test_color_pipeline -v
python -m unittest discover -s tests -v
python -m compileall -q host app tests tools
python tools/check_repo_contract.py --output <新的系统临时目录>/repo-contract-report.json
node --check web/app.js（若修改）
git diff --check

不要覆盖仓库已有 host-test-report.json、repo-contract-report.json，也不要使用或清理
.test-output/。不需要运行 PlatformIO，因为本工作包禁止改 firmware。

完成后在独立 feature branch 提交，并给出完整移交报告：branch、baseline/final SHA、
文件清单、架构与 schema 决策、全部命令和精确结果、benchmark、Hardware tested:NO、
已知限制、仍缺的实测 artifact、集成风险和建议 merge 顺序。不要把软件或模拟结果
描述成真屏改进，也不要等待硬件时编造数据；能安全完成的接口、代码、fixture、
schema 和测试先全部完成。
```
