# MF-1750 扩展颜色远端成果集成审查

日期：2026-08-05

结论：`MERGED LOCALLY WITH HARDENING / HARDWARE NOT TESTED`

远端来源：`origin/research/extended-color-20260805`，审查时远端头为
`600b9a319da08c6632a5852d3e9bd3ce9e5cbdee`。该分支已通过非快进合并提交
`73607a2` 合入本地 `main`；本审查后的合同和安全加固另随本地后续提交保存。
没有推送 `main`，也没有刷写、串口、网络或面板 I/O。

## 1. 合并判断

远端成果应当合并，因为它补齐了后续扩展颜色实验所需的离线基础：

- 官方证据矩阵和 A～J 阶段账本；
- 固定、可哈希的 `0x4`/`0x7` 小区域未知码测试帧；
- 空的 6×6 状态转换 profile 和机器记录合同；
- 六种合法物理颜色的 2×2/4×4 面积混色模拟；
- 光学、电气、事件、恢复和资产清单的数据结构及测试。

但原远端成果不应原样作为硬件测试依据。本地集成时进一步做了 fail-closed
加固：输出帧必须同时生成身份 sidecar；拒绝覆盖、目录穿越、Windows 设备路径、
网络盘和受保护目录；硬件记录必须绑定授权、时间、哈希和证据；完整事件要求唯一、
有序、全部通过的安全链；未取得经批准的绝对电气限制前，`electrical complete`
在 schema 和语义层都不可达。

## 2. 对当前图片效果的影响

当前照片显示效果**没有直接改变**。这次合并没有修改：

- `host/color_pipeline` 的照片量化、色域映射或误差扩散算法；
- Web 页面中的原图/预览/上传流程；
- `src/` 固件、驱动波形、时序或高压参数；
- `hardware/` 和 `platformio.ini`。

新增的面积混色只能离线枚举六色空间配比并生成合法帧，是未来 G1 色域映射的研究
输入。默认参考调色板没有真屏 D65/2° 测量绑定，因此输出只能称为模拟；即使提供
palette，当前 v2 合同也会显式保持 `hardware_formal_qualified=false`。不能据此宣称
风景照片、肤色、天空或暗部已经在真屏上改善。

## 3. 已验证内容

集成和加固后已完成：

- Python 3.10：全仓 286/286 测试通过；
- Python 3.12：全仓 286/286 测试通过，19 项因该解释器缺少可选 `jsonschema`
  依赖而跳过；
- 扩展颜色 record/profile 定向测试 34/34 通过；
- `compileall`、全部 extended-color Draft 2020-12 schema 自校验、
  repository contract、`node --check web/app.js` 和 `git diff --check` 通过；
- PlatformIO `esp32-s3-devkitc-1` build 通过，RAM 45,568/327,680 bytes，
  flash 810,685/3,342,336 bytes；固件源码未变化；
- 远端研究分支 CI 的主机测试和固件构建通过。

以上均为软件/构建验证，`Hardware tested: NO`。

## 4. 用户可立即执行的软件测试

在仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q host app tests tools
python tools/check_repo_contract.py --output "$env:TEMP\mf1750-repo-contract.json"
node --check web/app.js
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e esp32-s3-devkitc-1
```

仅观察面积混色排序，不创建文件：

```powershell
python tools/mf1750_area_mix.py --target-srgb 80 170 190 `
  --allow-uncalibrated-simulation --tile-side 4 --limit 8
```

在自行创建的空目录内生成离线 `0x4` 固定图和身份报告：

```powershell
New-Item -ItemType Directory -Path "$env:TEMP\mf1750-ec-fixture" -Force
python tools/mf1750_extended_color.py --pattern unknown-0x4 --repetition 1 `
  --output "$env:TEMP\mf1750-ec-fixture\unknown-0x4.bin" `
  --report-output "$env:TEMP\mf1750-ec-fixture\unknown-0x4.json"
```

该命令只创建离线文件，不上传、不刷新。输出采用排他创建；再次运行同一路径应拒绝
覆盖。不得把生成的未知码 `.bin` 交给正式 `/api/frame`，正式 API 继续拒绝
`0x4/0x7..0xF`。

## 5. 后续硬件测试顺序

目前可安排的是 EC0～EC4，而不是直接显示未知码：

1. EC0 冻结 panel、PCB、控制器 revision、固件二进制和 OTP 身份；
2. EC1 资格化示波器、差分探头、电流/温度和 D65/2° 45/0 光学测量链；
3. EC2 测六色原厂电气与 Lab 基线；
4. EC3 为 B/W/B/W 恢复候选补齐逐步 POF、J2-1 断电、轨道释放、温度、冷却、
   最大尝试次数和恢复判据，资格化后才可使用；
5. EC4 执行 6×6 转换矩阵；
6. 只有 EC0～EC4 出口通过，并再次取得单次明确授权，才考虑隔离入口执行
   `0x4`，恢复确认后再单独考虑 `0x7`。

未知码测试不得通过生产 Web/API 入口执行，不得自动重试，也不得同时放大面积。
LUT、内部 phase、电压幅值、VCOM、`0x8～0xF` 和耐久循环仍保持硬阻断。

## 6. 已知残余限制

- 授权范围和证据哈希目前仍是未签名的本地记录；若以后面对不可信操作者或跨机器
  证据链，需要签名授权日志或 bundle validator，实际打开并重算所有引用文件。
- 路径检查适用于可信、单操作者的离线工作目录。同权限恶意进程仍可能通过精确的
  并发 symlink 置换制造校验到打开之间的竞态；对抗性环境应改用已打开句柄完成
  校验、读取、哈希和最终路径核验。
- 若仪器故障且完全没有产生 trace，当前 `hardware_tested=true` 的 electrical
  invalid 合同仍无法表达“零产物故障”；应先作为人工异常记录保留，后续再定义
  专用最小合同。

详细硬件门禁和待办见
[`TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md`](TODO_EPD_EXTENDED_COLOR_TESTS_2026-08-05.md)。
