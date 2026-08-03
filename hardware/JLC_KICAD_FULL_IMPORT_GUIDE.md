# 嘉立创 KiCad 完整导入包说明

使用这个包：

- `hardware/jlc_kicad_full_import.zip`

不要把 `hardware/jlc_ai_import.zip` 当作 KiCad 工程导入。那个包不含
`.kicad_pcb`，嘉立创可能只解析原理图，导致封装为空、网络全部独立。

## 推荐导入方式

1. 在嘉立创 EDA 中删除旧工程或旧导入任务，避免缓存旧的 `16:03:38` 文件。
2. 选择导入 KiCad 工程/PCB，而不是只导入原理图。
3. 上传 `hardware/jlc_kicad_full_import.zip`。
4. 导入后检查 PCB 视图，而不是只看原理图视图。
5. 预期结果：器件有封装，PCB 里会有未布线飞线/ratsnest。

## 预期错误

PCB 当前是摆件草稿，没有布铜线，所以嘉立创可能报告很多“未连接”。
这是正常的，表示需要 AI 布线或人工布线。

不正常的情况：

- `10uF/25V/1210` 封装为空。
- 所有器件完全没有网络或飞线。
- 报 `$2Ixx 缺少“封装”属性`。

如果出现这些情况，说明导入的不是当前完整包，或嘉立创没有读取 `.kicad_pcb`。

## 本地校验结果

- KiCad XML: 78 个元件，0 个缺少 footprint。
- 所有元件都有 `Footprint` 和中文 `封装` 属性。
- KiCad ERC: 0 errors / 0 warnings。
- KiCad DRC: 0 violations，只剩 133 个未布线飞线。

## 关键人工检查

- `J1` 50pin FPC 接触面方向必须按实物确认。
- `SL_CSB` 必须从 J1 pin 4 单独接到 ESP32 GPIO。
- `D1-D4` 二极管极性按 `bom_reference.csv` 检查。
- `Q1/Q2` 按 SOT-23 pinout `1=G, 2=S, 3=D` 检查。
- `L1/L2/Q1/Q2/D1-D4/C2/C4/C5/C6` 高压回路要短、粗、紧凑。
