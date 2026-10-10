# MF1750 第二代波形架构与 T2000 边界审计

日期：`2026-08-13`

本报告只回答架构归属和证据能否迁移。它不生成 runtime LUT、固件、授权或真屏动作，
也不把公开产品宣传中的 `3-bit`、`八主色` 与本地 `800-byte` 载荷自动绑定。

可复跑入口：

```powershell
python tools\mf1750_second_generation_waveform_architecture_audit.py --compact
python -m pytest tests\test_mf1750_second_generation_waveform_architecture_audit.py -q
```

冻结报告：
`.test-output/offline/mf1750_second_generation_waveform_architecture_audit_20260813.json`

## 结论

1. **T2000 是真实的独立 TCON ASIC。** E Ink 与 Himax 的共同一手资料将它明确描述为
   彩色电子纸 timing-controller ASIC。它接收 MIPI-DSI、USB 3.0 或 SPI 数据/控制，执行
   色彩算法、温度补偿并控制驱动电压的时序和持续时间，再输出 mLVDS/TTL。因此它属于
   显示控制 PCB 上的硅芯片，不属于电子墨水膜或粒子层。
2. **外置 PCB 路线已经有实物级先例。** OKRA 的第三方板卡资料展示了 T2000、
   ESP32-S3、SiP memory、电子纸高压电源、OCP/OVP 与温度监测位于同一外置 TCON 板；
   目标是大尺寸 mini-LVDS 面板。这证明“外置板实现”可行，但不等于裸芯片资料、原理图、
   固件或波形包已经公开。
3. **当前 MF-17506 不是该接口拓扑。** 厂商规格把当前 7.5 英寸、1024×600、3-bit E6
   模组描述为 SPI 接口、on-chip OTP waveform，并在机械图标注 `SPD1657*2ea`，参考电路
   使用 `SPD1657B`。其集成项含 source/gate、timing、DC-DC、SRAM、LUT 与 VCOM。因此
   文档化路径是 `ESP32/SPI → 双 SPD1657B 集成模组`，不是
   `T2000 → mini-LVDS/TTL 裸面板`。没有任何公开证据支持把 T2000 插在当前 SPI 链路中。
4. **第二代混色架构是真实产品路线，但不是本地 ABI 说明。** E Ink 2025 公告把 Ripple
   转场与新增混色 waveform 分开叙述；后者结合升级到 3-bit 的芯片系统声称八个主色，并
   点名 Solomon Systech 等兼容芯片供应商；另外又说 standalone T2000 能进一步扩色并
   点名 cyan、light green、orange。公告没有点名 SPD1657、E2802、命令、载荷长度、
   category、phase 或电气字段，两段颜色陈述也不得自行相加。
5. **本地结构仍只有几何证据。** WF20/WF23 均为
   `7 + 9×8×11 + 1 = 800`；经验 H3 取前 799 字节作为 R20 候选，并另行构造 704 个
   `FF` 作为 R21。`9` 个结构块不能据此命名成八色、`1+8` 类别、phase 或电平字段；
   构造的 704-byte R21 也不是 vendor profile 自带字节。
6. **旧 E2802 library 仍没有闭合 mode-1。** 固定库只直接出现
   `E5_3Bit_Mode 0`、`WF_DeCode_SIZE 544`、`WF_SIZE 535`；没有
   `E5_3Bit_Mode 1`。因此任何无类型的十进制 `800` 偶合都不能升级为 mode-1/800-byte
   loader 证据。

## 证据矩阵

| 来源 | 直接证明 | 没有证明 |
|---|---|---|
| E Ink/Himax 2024 T2000 | 独立 TCON、色彩算法、温补、电压时序、MIPI/USB/SPI 输入、mLVDS/TTL 输出、LPDDR | 裸芯片采购、引脚/寄存器、波形 ABI、当前 7.5 英寸屏兼容 |
| Himax 2026 T2000 | 已用于 E Ink 新控制架构；TTL/mini-LVDS、USB/SPI/I2C；刷新与下一帧准备并行 | SPD1657/E2802 或本地 799/704 合同 |
| E Ink 2025 第二代波形 | 现有粒子参与混色；3-bit compatible chipset + 新波形；八主色产品声明；Solomon 属生态 | 颜色码、category 顺序、11-byte 字段、波形载荷或安全电气值 |
| OKRA T2000 板 | 外置 TCON 板工程路径存在；板载 MCU/memory/EPD power/protection | 一手 T2000 datasheet、开源 bare-chip design、当前 MF17506 适配 |
| MF-17506 厂商规格 | 双 SPD1657/SPD1657B、SPI、集成功能与 OTP waveform | T2000 存在、mini-LVDS/TTL 接口、第二代波形资格 |
| WF20/WF23 + E2802 库 | 800-byte 几何、799 候选段、704 构造段、mode-0 535/544 markers | mode-1 loader、category/phase/电气字段、双控提交/回滚与 OTP 恢复 |

官方 T2000 两份资料以及 E Ink 第二代公告中，对以下精确候选词的固定扫描结果均为
未命中：`SPD1657`、`E2802`、`WF20_25`、`WF23_25`、`799-byte`、`704-byte`、
`535-byte`、`1503-byte`、`2508-byte`、`0x20`、`0x21`。这只是当前固定来源的
negative finding，不是资料永远不存在的证明。

## 两条后续路径

当前屏路线继续保持：

- 只使用完整、身份固定的 WF20/WF23；不拼接 block/record，不给 11-byte 字段命名；
- 先完成各 profile 的 header-matched control，再比较同 profile 的 control/treatment；
- 继续寻找同代 SPD1657/E2802 loader/parser、单字段变化 profile、双 CS logic capture 与
  runtime-to-OTP 恢复合同。

T2000 路线应独立立项：

- 优先采购厂商支持的 T2000 TCON 板、明确兼容的 raw mini-LVDS/TTL Spectra 面板，以及
  panel-specific waveform/SDK/license；
- 不以当前双 SPD1657 SPI 模组作为 T2000 输出目标；
- 在得到 T2000 datasheet、参考原理图、BOM、供电时序、固件和波形授权以前，不先做
  裸 QFN104 PCB。

## 固定身份与验证

- report file SHA-256：
  `3bad6cddf94c9874f3d2ab13ac7cd663fd474c47ddd524a22a2f9e75c4cfa7bf`
- report canonical SHA-256：
  `aaee09b1ecea72e4efec76d6b5a6bddc2509cc3ad13c1ba911c672198742de42`
- 聚焦回归：`8 passed`
- Ruff check：PASS；Ruff format check：PASS；`py_compile`：PASS
- 全程没有访问硬件、串口、COM8 或设备网络，没有写固件、刷新屏幕或生成授权。

