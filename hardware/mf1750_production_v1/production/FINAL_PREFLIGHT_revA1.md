# MF-1750 Rev A1 下单前冻结检查

检查日期：2026-07-13

## 结论

Rev A1 未发现新的生产阻断项，可用于受控首板。下单时只使用：

- `Gerber_mf1750_revA1_Q1FIX.zip`
- `BOM_mf1750_revA1_Q1FIX.csv`
- `CPL_mf1750_revA1_Q1FIX.csv`

不要复用嘉立创页面中修正前已经解析的文件。

## 修正与验证

- Q1 SI1308EDL：pad 1=GDRH/G，pad 2=RESEH/S，pad 3=SW_H/D。
- D2 负压泵：pad 1/K=GND，pad 2/A=NEG_PUMP_H；CPL 180°。
- ERC：0 error，0 warning。
- DRC：0 violation，0 unconnected，0 schematic parity error。
- BOM/CPL：各 46 个相同位号，全部 Top；R16 DNP。
- Manifest：所有生产文件大小和 SHA256 校验通过。
- 固件：PlatformIO ESP32-S3 release build 成功。

## 嘉立创预览

- D1、D2 阴极色带朝右；D3、D4 阴极色带朝左。
- Q1：一个脚在上、两个脚在下，pin 1 在左下。
- Q2：两个脚在左、一个脚在右，pin 1 在左上。
- J1 pin 1 在顶视左侧，排线从板顶边进入。

## 仿真边界

SPD1657 的闭环驱动波形和 SPICE 模型未公开，现有资料不能可靠模拟高压
启动、环路稳定性和温升。已完成静态拓扑、额定值、网络、布局和制造数据
检查；首板仍必须限流上电，实测 VPH、PREVGH、PREVGL、VPC 和 Q1 温升。
