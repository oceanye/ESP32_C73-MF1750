# 下一阶段新对话启动提示

复制以下内容到清空后的新对话：

> 请先完整阅读工作区中的
> 根目录 `README.md`、
> `docs/STAGE1_REV_A1_HANDOFF_2026-07-13.md`、
> `docs/STAGE2_ESP32_BATTERY_INTEGRATION_BRIEF.md`、
> `docs/TODO_MULTI_AI_HANDOFF_PLAN_2026-08-04.md`、
> `docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`、
> `docs/C1_HOST_FRAME_HANDOFF_2026-08-04.md`、
> `docs/C5_HOST_CI_HANDOFF_2026-08-04.md`、
> `docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`、
> `docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md` 和
> `docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md`。
> MF-1750 Rev A1 已于 2026-07-13 提交嘉立创，生产文件被冻结，禁止重新生成、
> 覆盖或把 Rev B 文件写回该目录。当前首板已拆 R15、装 R16=0 Ω：GPIO7=CS1、
> GPIO10=CS2；两颗 SPD1657B revision 均为 0x04，分别写 CCSET(0xE0)=0x01 后，
> 100 kHz 完整 1024x600 六色色条、颜色顺序和中缝已经实屏通过。
>
> 当前待重新刷入候选的 build tag 为
> `MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04`，
> driver API 为 `MF1750_R16_CASCADE_V3`。RC2B/V2 已在 100 kHz 显示完全正确的
> MAP_ORIENT_V1，并确认 PON/DRF/POF BUSY 与完整/双 DTM 哈希；实测同时证明
> POF 后 PSR 写寄存器不会再次拉低 BUSY，RC2C/V3 因而把该采样改为信息证据。
> 它保留非法六色色码的双层拒绝，并把
> diagnostic report 以匹配 operation ID 的不可变快照与产生它的 job/build 绑定，
> 未观察到正式阶段 BUSY 会 fail closed。先核对最终 `origin/main` SHA、
> repository contract、152 项全仓 unittest、锁定 PlatformIO build 和对应 GitHub CI；
> 这些软件结果不等于硬件验收。默认认为驱动板断电，未经我明确确认，不得刷写
> COM8、访问设备 HTTP 刷新接口或要求上电。
> 经授权后依次确认启动日志约 8 MB OPI PSRAM、低速 MAP_ORIENT_V1 方向，以及
> 通过正式 1 MHz `/api/frame` 发送同一个 MAP_ORIENT_V1；完成 D0 后先生成 H0
> 只读 archive、SHA256 manifest 和硬件验收 tag。随后在独立
> 硬件诊断分支按 1/2/4/8/10 MHz 冷启动扫频，使用仓库分析器记录 DTM hash、
> BUSY、CV、温升和画面。10 MHz 全部门禁通过前不测试 20 MHz。不得根据
> SPD1656 猜测 SPD1657B LUT/局刷命令；取得厂商资料前不改波形、高压或
> power-cut 序列。当前固件没有参数化 sweep action；离线分析器、六色抖动预览或
> CI 通过均不等于真屏验收。主机色彩管线已经强制绑定
> `0黑/1白/2黄/3红/5蓝/6绿` 并默认拒绝未校准整屏输出；仍须回填受控
> D65/2deg 六色 Lab 色板，再比较真屏抖动效果。
>
> H0 完成后优先移交 C4 应用层；C2 真屏色彩和 R1 扫频可独立推进。再继续 Rev B：
> 集成 ESP32-S3、USB-C 烧录/供电、单节锂电充电、
> power-path 和 3.3 V buck-boost。Rev B 默认沿用已验证的双独立片选 GPIO 与
> MF-1750 高压拓扑；任何 ECO 必须有首板实测依据。开始设计前先和我确认 ESP32
> 模块/PSRAM、电池尺寸容量、USB-C 功能、天线和机械约束。
