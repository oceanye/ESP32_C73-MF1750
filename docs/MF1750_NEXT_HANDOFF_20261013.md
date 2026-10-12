# MF1750 下一阶段波形研究交接

日期：2026-10-13
当前基线：main@1aa7dec
项目：ESP32-S3 + 双 SPD1657B / MF-1750 E6 彩色屏

## 结论

项目已从任意猜测波形转为单变量、可复现、带停止条件的波形研究。当前没有证据证明获得了稳定、可寻址的新中间色；藏青和灰米只能作为波形失配、驱动裕度或过渡态证据。后续坚持直接波形激活，不用抖动替代波形能力。

## main@1aa7dec

该提交增加 WF A1/B1 隔离实验路径、生成器、独立驱动 TU、PlatformIO 环境和文档。

A1：只改 PLL，0x02 到 0x03；R20/PWR 其余内容保持 active 基线。
B1：只改 VSH_LV2，约 6200 到 6900 mV；R20 与 PWR 对应字段成对变化，PLL 保持 0x02。

生成器和编译期断言保证：A1 的 R20 PLL 字段等于 runtime 0x30 payload；B1 的 R20 电压字段等于 PWR 镜像；record 区域不漂移。A1/B1 当前仍是 NOT_QUALIFIED_AWAITING_PASSIVE_CAPTURE，不能直接刷屏。

## 已确认事实

1. 生产 OTP 路径可恢复白场，DRF 约 21671 到 21691 ms。
2. L535 active 路径重复出现藏青场，DRF 约 32651 到 32661 ms，约为 OTP 的 1.51 倍；首要判断是 active LUT/路径失配，而非面板完全损坏。
3. active/commented 表约 63/88 字节不同；active White group 6/7 为 FF no-op，commented 表有内容。表头存在 VSH_LV、VSL、PLL 差异；byte 5 是 VCOM 槽，不能直接当 gate。
4. VSH_LV 有响应但不稳定：6000 mV 藏青，6600 mV 灰米，7200 mV 曾在另一时段恢复白。必须同一 session、同一起始态重做阶梯。

## 阻断项

- A1/B1 没有逻辑分析仪被动捕获，不能确认 PLL 写入次数、最后值和完整顺序。
- 相机曾出画、取景漂移和过曝；旧照片不能混入新批次。
- 1aa7dec 页面状态检查为 1/2，需先查明失败项。
- 旧 handoff 分支已与 main 分叉，不能继续当最新基线。

## 下一步

阶段 A：从 main@1aa7dec 建新分支；重复生成 A1/B1；编译两个环境；运行 contract、frame-tool、runtime-waveform 测试；固定生产/A1/B1 的 bin、R20、PWR、PLL SHA-256；查明 GitHub 失败检查。

阶段 B：在不刷新面板的条件下捕获生产 OTP、A1、B1 的 SCLK、MOSI、CS1、CS2、DC、RES、BUSY，以及 PSR、PWR、PLL/0x30、TRES、0xE9、R20、R21 和 PON/DRF/POF 时序。没有被动捕获，不进入 A1/B1 真屏。

阶段 C：固定相机和面板；四角全部入画；重新钉四边形；固定曝光、灯光和照明 ratio；通过 P0 前置门。

阶段 D：OTP 白清基线 -> L535 active 白清复现 -> VSH 6600 -> VSH 7200 -> A1 PLL -> B1 VSH_LV2。每次只改一个变量，命中藏青、DRF 超门、BUSY 异常或光学门失败即停止。

## 中间态判定

必须使用固定大色块或单色阵列，不用抖动；同一起始态至少重复两次；记录 t0、60 秒、300 秒的 Lab、色度、均匀性和 DRF；门限必须预注册；不能依赖鬼影、残影、曝光变化或失败清场；必须与有效码 0/1/2/3/5/6 形成稳定可重复色差。单次灰米、藏青或慢 DRF 不计为新颜色。

## 禁止事项与决策

不猜 0xE9/0x20/0x21；不把 WF20/WF23 opaque profile 塞进 535B；不先改 0x14、R21 或未知像素码；不放宽生产 API 对 0x4/0x7..0xF 的拒绝；不用抖动掩盖波形不稳定。

若 7200 在同一 session 稳定恢复白，继续 VSH 多级直接色块；若 7200 仍不稳定，停止升压，转 active/commented LUT、隐藏命令和厂商资料差分；若 OTP 也失败，优先判断面板全局状态。若 A1 只改变 DRF 而不产生稳定色阶，PLL 不是主轴；B1 只有在可重复改善时才扩展小阶梯。

本交接不构成上电、刷写或刷新授权。
