# TODO：网络照片源与随机刷新流水线

状态：`PENDING / 未授权执行`

本文件只建立后续工作包，不启动网络下载、不连接照片服务、不调用 ESP32 刷新
接口，也不改变已经验收的 RC2C/V3 基础驱动。开始任何阶段前由用户重新确认范围、
数据源、运行环境和硬件上电条件。

## 1. 目标

建立一个可审计的照片调度服务，从用户指定的网络位置读取候选照片，安全下载、
解码、裁剪、六色量化并随机选择，再通过现有 MF-1750 正式上传协议刷新屏幕。

推荐把网络访问、图片解码、随机历史和任务调度放在长期在线的电脑、NAS 或树莓派
上；ESP32 继续只负责经过验证的规范帧接收、job 执行和 diagnostic report。第一版
不在 ESP32 固件中直接实现 HTTPS、云相册 SDK、JPEG/PNG 解码或定时器。

Rev B-mini 已新增 microSD/TF 卡硬件需求。TF 首先作为设备端图片/规范帧缓存、
离线播放队列和诊断记录存储，不自动把第一版网络下载与复杂图片解码迁入 ESP32。
硬件边界见
[`H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md`](H1_REV_B_MINI_COMPONENT_ASSESSMENT_2026-08-05.md)。

用户场景为低频刷新相框。当前算力结论是不升级 ESP32-P4：优先把现有
`host.color_pipeline` 封装为可审计的量化服务 API，ESP32-S3 负责下载、
验证、TF 缓存和刷新。本地量化只做离线后备，先在 S3 上基准测试；P4 仅在
完全离线大图/视觉任务且 S3 有实测失败证据时重新评审。

```text
HTTP(S) 图库 / NAS / 相册服务
              ↓
     照片源适配与安全下载
              ↓
     随机选择、去重与持久历史
              ↓
  1024x600 规范化、六色量化、预览
              ↓
 allow → preflight → ingress → one-shot arm
              ↓
 /api/frame → /api/job → immutable diagnostic
              ↓
          MF-1750 实屏
```

## 2. 当前可复用基线

- ESP32 Wi-Fi STA、DHCP 和 AP fallback 已存在；当前调试地址由串口输出决定。
- 设备已支持精确 307200 字节 `/api/frame`、单 job 锁、job 轮询和 schema v2
  immutable diagnostic。
- RC2C/V3 的 100 kHz MAP 和正式 1 MHz 整帧已实机通过。
- 主机已有 RGB/RGBA 规范化、contain/cover/stretch、六色量化、抖动、预览和
  `HttpDeviceAdapter` 安全状态机。
- 默认 reference palette 未校准，只允许离线预览；正式普通图片上传仍需带完整
  provenance 的 calibrated palette。
- ESP32 设备 API 当前没有认证、TLS、远端 cancel 或持久 job 历史。
- `EPD_PIN_SWC=-1`，当前软件不能自动切换 J2-1 面板电源。
- 当前 Rev A1/DevKit 台架没有 TF 卡；Rev B 只记录了独立 SPI 的推荐输入，
  尚未冻结卡座、GPIO、文件系统或缓存协议。

统一接口合同见 [`MF1750_DRIVER_API.md`](MF1750_DRIVER_API.md)。

## 3. 执行前需要用户确定

以下项目保持 `TBD`，不得由实现者擅自假定：

1. 照片来源：HTTP(S) JSON 清单、WebDAV、NAS 本地挂载目录、SMB、Immich、
   Google Photos 或其他服务。
2. 调度主机：Windows PC、树莓派、NAS 容器或其他长期在线设备。
3. 更新周期和允许时段，例如每 30 分钟、每天固定时间或仅人工触发。
4. 随机规则：完全随机、按相册权重、多少张内不重复、是否允许同一照片不同裁剪。
5. 图片过滤：格式、最大文件大小、最小分辨率、横竖图策略、人物/日期/标签条件。
6. 面板供电方式：J2-1 长期供电、人工上电，或新增受控电源开关硬件。
7. calibrated palette 的测量文件和正式授权人。
8. 局域网安全要求：固定 DHCP、mDNS、设备 token、HTTPS reverse proxy、VLAN。
9. TF 用途：仅缓存已处理帧，还是也保存原图；目标容量、文件系统、卡检测和
   拔卡策略。

## 4. 工作包与顺序

### N0：配置与来源合同

- 定义不含明文凭据的配置 schema；秘密只从本地文件、系统凭据或环境注入。
- 定义 `PhotoSource` 接口，返回稳定 source id、候选 id、URL/路径和可选元数据。
- 第一版只实现一个用户选定来源；其他来源作为独立 adapter，不混入核心逻辑。
- 配置默认离线，未显式启用时不得发起任何网络请求。

验收：schema 有严格类型/未知字段拒绝测试；示例配置不包含真实地址、token 或照片。

### N0.5：量化服务 API 合同

抖动前色域映射、gamut profile、rendering intent、mapped-raster identity、
canonical Web 预览和软件/硬件门禁统一服从
[`G1_SPECTRA6_GAMUT_MAPPING_HANDOFF_2026-08-05.md`](G1_SPECTRA6_GAMUT_MAPPING_HANDOFF_2026-08-05.md)。
N0.5 不得在网络服务内另写一套 palette、tone map 或抖动算法。

- 服务器可接收原图，或接收 allowlist 内的 source ID；不让 ESP32 把任意 URL
  交给服务器，避免 SSRF。
- 智能裁剪/主体识别可以使用 AI；最终六色 palette mapping、抖动和打包必须
  使用版本化、确定性管线。
- 结果绑定 source SHA256、frame SHA256、palette ID/hash、算法/参数版本、
  `1024x600`、`307200` 字节和允许色码 `0/1/2/3/5/6`。
- manifest 和 frame 使用签名/HMAC 或等效认证；ESP32 仍执行长度、色码和
  hash 验证，验证后才原子写入 TF。
- 网络失败时回退到 TF 中已验证缓存；不得盲目重发旧请求或刷新未验帧。

验收：同输入/同版本输出确定；篡改帧、错 palette、错尺寸、非法色码、过期签名、
重复 job 和服务超时全部 fail closed。

### N1：安全下载与缓存

- 对远程来源使用 host allowlist；限制协议、端口、重定向、超时和最大响应体。
- 校验 MIME、文件签名和解码后尺寸，拒绝 HTML、压缩炸弹、超大图及部分下载。
- 每个原文件计算 SHA-256；缓存使用内容寻址，不以远端文件名直接拼接路径。
- 对私有/本地地址访问做显式策略，避免配置或重定向形成 SSRF。
- 下载失败只隔离该候选，不得触发旧帧重发或设备刷新。
- 缓存后端先定义与介质无关的内容寻址接口；首版主机磁盘实现通过后，才增加
  Rev B TF 后端，禁止两个后端产生不同的内容身份或重复选择语义。

验收：正常、超时、截断、错误 MIME、重定向、重复内容和恶意路径均有测试。

### N2：随机选择与历史

- 用持久数据库或原子 JSON 保存候选 id、内容 SHA、最近显示时间和失败状态。
- 支持可配置 no-repeat window，默认避免立即重复。
- 选择结果记录 source id、candidate id、content SHA、时间、规则版本和随机种子/证据。
- 只有成功完成设备 job、diagnostic 和人工/策略门禁后才计为“已显示”。
- 进程重启后不能遗忘在途任务并盲目选取下一张。

验收：固定种子可复现；空图库、单图图库、全部隔离、历史损坏和并发调度 fail closed。

### N3：图片准备流水线

- 复用 `host.application` 和 `host.color_pipeline`，不复制另一套颜色码或 mapping。
- 解码后统一为 straight-alpha RGBA，透明像素在线性光空间合成到白底。
- 支持 contain/cover/stretch，输出精确 1024x600、307200 字节和合法六色码。
- 保存原图 SHA、规范 RGBA SHA、帧 SHA/FNV、palette provenance、选项和预览 PNG。
- 若启用 G1，另保存 gamut profile/algorithm/intent/hash、mapped-raster hash、
  out-of-gamut 与 tone/chroma 压缩统计；相同合同必须产生逐字节相同的帧。
- 未校准 palette 只能生成 offline preview，不能获得 formal upload authorization。
- 未校准或仅六点近似的 gamut profile 同样只能生成 offline preview，不能通过
  网络流水线获得正式上传授权。

验收：确定性输出、非法图片拒绝、报告身份绑定、预览与帧一致性测试全部通过。

### N4：设备投递与恢复

- 只通过现有 `HttpDeviceAdapter` 固定 allowlist，不让照片源直接构造设备路径。
- 固定顺序：allow、version preflight、frame ingress、一次性 arm、enqueue、job、report。
- mapping 固定核对 `CS1=[0,0,0,0]`、`CS2=[1,0,0,0]`，不得由照片元数据修改。
- `202` 只记为 queued；只有 matching completed job 和 diagnostic 才是协议成功。
- enqueue 网络结果不明确时先 recover/query，绝不自动二次 POST `/api/frame`。
- RC2C/V3 无远端 cancel；本地停止不能宣称设备任务已取消。

验收：断网、HTTP 202、job failed、旧 job、错 hash、错 operation、重启恢复和重复
提交均有 scripted integration test。

### N5：调度服务

- 支持人工单次运行、dry-run/preview-only 和定时运行；默认 dry-run。
- 单实例锁防止两个调度器同时刷新。
- 设置最短刷新间隔、允许时段、指数退避和每日最大刷新次数。
- 提供只读状态、最近选择、最近成功和明确错误，不在日志中输出凭据或完整 URL query。
- 先实现 host 侧时间与调度，不在 ESP32 中引入 NTP 或 cron。

验收：时间边界、夏令时/时区、重启、锁竞争、退避和最大次数均有确定性测试。

### N6：无人值守安全加固

以下门禁关闭前，只允许有人值守测试：

- 为 ESP32 正式路由增加设备端认证和一次性/短时授权；
- release 构建关闭或隔离 legacy/危险诊断路由；
- 确定稳定寻址方式：DHCP reservation 或 mDNS；
- 明确 J2-1 长期供电是否允许，或增加可验证的受控电源开关；
- 加入启动/掉电/看门狗恢复策略，确保面板侧 GPIO 默认全低；
- 进行至少一次受控长时间 soak test，并审查电源、温升、网络失败和重复刷新次数。

## 5. 分阶段硬件验收

1. `H-NET-0`：只读取照片列表和下载，完全不连接 ESP32。
2. `H-NET-1`：生成预览、帧和报告，不调用设备；人工核对随机与画面构图。
3. `H-NET-2`：J2-1 断电，执行 version 和 frame-ingress，只验证协议。
4. `H-NET-3`：用户明确上电后，只刷新一张冻结照片；核对 job/report/画面/CV/温度。
5. `H-NET-4`：多张照片逐次冷启动或按批准间隔测试，验证 no-repeat 和恢复。
6. `H-NET-5`：完成 N6 后才评审无人值守定时运行。

每个阶段失败都停在当前门禁，不自动推进下一阶段。

## 6. 完成定义

只有以下条件全部满足，网络随机照片功能才能标记完成：

- 用户选定的数据源与调度主机已经实现并记录版本；
- 网络、解码、随机、历史、量化、设备恢复测试全部通过；
- calibrated palette 与正式上传 provenance 完整；
- 每次选择和显示都可由 source id、内容 SHA、frame hash、job id 和 operation id
  追溯；
- 不存在盲目重发、并发刷新或把 HTTP 202 当成功的路径；
- 有人值守的多图实屏、电源与温度验收通过；
- 若启用无人值守，N6 所有安全门禁和 soak test 通过；
- README、API 参考、配置示例、运行手册和故障恢复说明同步更新；
- 对应 `main` 提交的本地回归、PlatformIO 和 GitHub CI 全部成功。

## 7. 明确非目标

- 本工作包不修改 SPD1657B 高压、LUT、PON/DRF/POF/PSR 或快速/局部波形。
- 不把高于 1 MHz 的 SPI 扫频混入网络照片功能。
- 不重新生成或修改 Rev A1 冻结生产文件。
- 不默认抓取互联网随机图片；只访问用户明确配置和授权的数据源。
- 不在未校准色板下声称普通照片达到正式颜色验收。
