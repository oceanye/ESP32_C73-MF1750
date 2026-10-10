# MF1750 DevKitC Rev B2 — 嘉立创下单与 SMT 交付说明

## 三个上传文件

1. PCB/Gerber 栏只上传 `upload/JLCPCB_PCB_MF1750_DEVKITC_B2_4L.zip`。
2. BOM 栏只上传 `upload/JLCPCB_BOM_MF1750_DEVKITC_B2_SMT.csv`。
3. CPL/坐标栏只上传 `upload/JLCPCB_CPL_MF1750_DEVKITC_B2_SMT.csv`。

`JLCPCB_SUPPORT_MF1750_DEVKITC_B2.zip`、`support/` 与 `MF1750_DEVKITC_B2_KICAD_SOURCE.zip` 是审计/装配支持资料，
不要上传到上述三个自动解析栏。

## PCB 下单参数

- 单板 `65 x 60.5 mm`，FR-4，4 层，成品厚度 1.6 mm。
- 指定嘉立创 `JLC04161H-7628` 叠层：L1/L4 外铜 1 oz，L2/L3 内铜 0.5 oz；
  本设计不声明受控阻抗。
- 层用途：L1=器件/信号/局部功率，L2=连续 GND，L3=3V3/EPD_3V3/V_B，
  L4=信号与回流。
- 绿色阻焊、白色丝印；表面处理固定为 `ENIG (1U)`，不得在下单时临时
  改为 HASL。J1 是 0.50 mm pitch FPC，本选择用于保持细间距焊盘平整度。
- PTH/NPTH 必须分开解析；本包为 PTH 121 孔、NPTH 2 孔。
- 上传的 Gerber/BOM/CPL 都是单板数据。若由嘉立创拼板，选择
  `Single Piece, please help me repeat the data`，不得选 `Complete File`。
- PCBA 下单要求嘉立创添加至少 5 mm 工艺边、fiducials 和 tooling holes；
  不要缩放或改写 65 x 60.5 mm 功能板框。
- **功能边距短板已经移除：**板级审计按每个 FIT SMT 的 F.Fab 本体测量，
  到成品功能 Edge.Cuts 的最小距离为 3.55 mm（C0 左侧），高于 2.5 mm
  本地基线；Courtyard 最小值 2.995 mm。即使作分析用途的 0.4 mm 向内
  工艺余量，本体仍为 3.15 mm、Courtyard 为 2.595 mm。因此没有需要
  厂家特批的器件本体边距偏离，外部工程边距例外状态为 NOT_APPLICABLE。
- 这不替代首板机械核对：J1/FPC 出线与分板、J3 侧向插接、J2 孔径和
  Z 包络、DevKitC 天线与新增 FR4/keepout、机壳/安装仍为实物 hold。

## SMT 合同

- 单面 Top SMT：46 个 FIT 位号，16 个唯一 LCSC 料号；BOM 与 CPL 位号集相同。
- `R16=FIT`、`R15=DNP`，禁止同时安装。钢网已移除 R15 两个开口，保留 R16。
- J2、J3 不在 SMT BOM/CPL：按 `support/BOM_MANUAL_THT.csv` 手工装配。
- J2 当前 PCB 为 0.80 mm finished holes。候选 `C7500786` 是 1x22、2.54 mm、
  8.5 mm 高、3.2 mm 尾针的波峰焊母座；在确认尾针截面能穿过 0.80 mm 成品孔、
  两排 22.86 mm 间距与 DevKit Z 包络前，不得让嘉立创代装 J2。

## 上传后必须人工确认

- 逐件核对 J1 pin1、D1-D4 阴极、Q1/Q2 pin1 与
  `support/ORIENTATION_CHECKLIST.csv`/装配图一致。
- 确认系统显示 R16 贴装、R15 不贴；所有 46 个 BOM/CPL 位号均成功匹配。
- 重新核对 LCSC 型号、封装、库存与 Basic/Extended 状态；库存是下单时状态，
  不能由本地导出包保证。
- 预览确认两个内层未交换：L2=GND，L3=电源。
- 本地 ERC/DRC 是前置检查，不是嘉立创 DFM/CAM 通过证明。必须再完成
  PCBA DFM、CAM 生产稿和贴装预览审批，特别检查丝印/阻焊裁剪。
- 选择“确认生产稿/Confirm production file”，人工看完厂家 CAM 后再批准生产。

## 官方下单口径

- KiCad BOM/CPL：https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad
- PCBA 条款：https://jlcpcb.com/help/article/terms-and-conditions-of-jlcpcb-assembly-service
- 工艺边/fiducials：https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order
- 拼板 BOM/CPL 选项：https://jlcpcb.com/help/article/common-bom-and-cpl-matching-issues-and-explanations
- 表面处理：https://jlcpcb.com/help/article/jlcpcb-surface-finish

## 首板限制

这是本地证据已通过、可进入上传审核的工程首板加工包，不是已经完成厂家或实物
资格认证的量产放行。在线 Gerber/CAM、BOM/CPL 解析、库存、旋转/极性仍为 PENDING。
收到板后仍需
执行：裸板短路/连续性检查；先不插屏限流上电；核对全部 MF-1750 电源轨、纹波与
温升；确认 R16 实装/R15 空位；最后才接 FPC 和屏幕。双电源域 GPIO 没有 Ioff
隔离，继续遵守 USB 先上、J3 后上；J3 先断、USB 后拔，J3 关闭时 GPIO 高阻。

机器审计摘要：`{"board_outline_mm": [65.0, 60.5], "drill_tools_and_counts": {"NPTH": {"2.5": 2}, "PTH": {"0.3": 75, "0.75": 2, "0.8": 44}}, "files": {"mf1750_devkitc_b2_pcba_margin-B_Cu.gbl": "bottom copper / L4", "mf1750_devkitc_b2_pcba_margin-B_Mask.gbs": "bottom solder mask", "mf1750_devkitc_b2_pcba_margin-Bottom Silkscreen.gbo": "bottom silkscreen", "mf1750_devkitc_b2_pcba_margin-Edge_Cuts.gm1": "single board outline", "mf1750_devkitc_b2_pcba_margin-F_Cu.gtl": "top copper / L1", "mf1750_devkitc_b2_pcba_margin-F_Mask.gts": "top solder mask", "mf1750_devkitc_b2_pcba_margin-F_Paste.gtp": "top paste; R15 removed", "mf1750_devkitc_b2_pcba_margin-In1_Cu.g1": "ground plane / L2", "mf1750_devkitc_b2_pcba_margin-In2_Cu.g2": "power routing / L3", "mf1750_devkitc_b2_pcba_margin-NPTH.drl": "non-plated drill", "mf1750_devkitc_b2_pcba_margin-PTH.drl": "plated drill", "mf1750_devkitc_b2_pcba_margin-Top Silkscreen.gto": "top silkscreen"}, "paste_r15_present": false, "paste_r16_present": true, "top_paste_flashes": 144}`
