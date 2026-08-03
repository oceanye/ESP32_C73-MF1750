# 嘉立创导入说明

当前工程有两个用途不同的版本：

- `hardware/mf1750_full_driver_kicad/`：KiCad 完整工程，包含未布线的初始摆件 PCB。
- `hardware/jlc_ai_import/`：给嘉立创 AI 布局/布线使用的导入包，不包含未布线 PCB。

## 为什么嘉立创报连接性错误

`mf1750_full_driver.kicad_pcb` 是未布线的摆件草稿。KiCad 报告里显示的是
`133 unconnected pads`，意思是还有 133 个飞线连接等待布线。

嘉立创导入后把这些飞线当作连接性错误列出，例如：

- `EPD_3V3`: R4/R6/R7/C3/TP4 还没有铜线连接。
- `SW_H`: L1/Q1/D1/C4 还没有铜线连接。
- `V_B`: C0/C22/C23/L1/R8/Q2/TP3 还没有铜线连接。

这不是原理图连接错误，而是“还没有布线”。

本次已修正 PCB 生成脚本里的两个兼容性问题：

- PCB footprint 已使用 KiCad 标准 `库名:封装名`，例如 `Resistor_SMD:R_0603_1608Metric`。
- 每个复制出来的 footprint 内部 UUID 都已重新生成，避免 KiCad/JLC 把不同元件的焊盘/图元误判为相关对象。
- 所有 78 个元件实例都已显式写入 `Footprint`，并额外镜像为中文 `封装` 属性。
- 本地符号库模板的默认 `Footprint` 也不再为空，避免嘉立创把模板或内部 `$2Ixx` 实例报为“缺少封装属性”。

重新校验结果：

- KiCad ERC: `0 Errors / 0 Warnings`。
- KiCad DRC: `0 DRC violations`，只剩 `133 unconnected pads`，也就是未布线飞线。
- KiCad XML 网表: `78` 个元件，`0` 个缺少 footprint。

如果还看到 `2026-06-08 16:03:38` 的 `$2Ixx 缺少“封装”属性` 错误，说明导入的仍是旧包或嘉立创缓存。请删除嘉立创中的旧导入任务/旧工程，重新上传最新的 `hardware/jlc_ai_import.zip`。

## 推荐导入流程

1. 上传 `hardware/jlc_ai_import/` 目录里的文件，或上传 `hardware/jlc_ai_import.zip`。
2. 在嘉立创里先从原理图/网表生成 PCB。
3. 再使用嘉立创 AI 布局/布线。
4. AI 完成后重点人工检查 `J1` FPC 接触面、`D1-D4` 极性、`Q1/Q2` 管脚、`L1/L2` 高压回路长度。

## 不建议的流程

不要直接把 `mf1750_full_driver.kicad_pcb` 当作已完成 PCB 导入后跑规则检查。
这个 PCB 只是 KiCad 里的摆件参考，未布线状态下必然有连接性错误。

## 关键文件

- `mf1750_full_driver.kicad_sch`
- `mf1750_full_driver.kicad_pro`
- `mf1750_local.kicad_sym`
- `sym-lib-table`
- `mf1750_full_driver.net`
- `mf1750_full_driver.xml`
- `bom_reference.csv`
