# MF1750 波形研究下一阶段交接（2026-10-10）

> 入口约定：状态权威仍以 [`STATUS_HANDOFF.md`](STATUS_HANDOFF.md) 顶部最新条目为准；
> 本文是**波形研究主线的阶段性收口与下一阶段路线图**，供下一个会话/协作者快速接手。

## 1. 背景与核心目标

用户目标：**全彩色谱**——每种颜色可调出 10 级以上明度。路线演进：
OTP 直寻址（证伪：非 stock，绿不可寻址）→ **L535 全彩路线**（调色板+gamut+抖动 demo 上屏，
用户 9-26 裁定）→ **波形方案重启**（挖掘不同色彩的中间态，10-09 裁定）→ 本交接。

## 2. 当前状态快照（2026-10-10 晚）

- **屏上**：VSH_LADDER 批条纹帧（7200mV 档，双稳态保留）；此前 GEO_PROBE 标定帧已被覆盖，照片全部存档
- **MCU**：生产 RC2G 固件 `ba59c3d6111a15c3426eddedf63188bf323083fdca24dec98939835b43dacdc3`（verify pass），NVS 未动
- **电气**：relay（Zave CH340 双路板，COM14，通道 1=面板电源）OFF；J2 由用户现场管理（每次刷写须 J2-off，刷新须 J2-on）
- **台架**：10-09 起被移动过两次，照片校正四边形已重推导（见 §6）；**勿再动面板/相机**
- **qualified 刷新终身计数**：0/256 保持

## 3. 本轮（10-09 晚 → 10-10）波形挖掘弧：四个批次

| 批次 | 刷新 | 结论 | manifest canonical |
|---|---|---|---|
| `L535_DAYLIGHT_ACCEPT_20261009_V1` | 0 | 日光级照明（ratio 1.032）下**绿偏暗异常复现**（L*29.8 vs 标定 47.3，与 10-07 灯光 29.4 逐数字一致）；白锚归一化不救；鉴别实验=真自然日光 | `f8683a489e7fb78a…` |
| `CMAP_V2_LIVE_20261009_V1`（MAP-v2） | 3 | 8×8 全有向（历史，目标）扫描；端点一致性 ΔE00 20.7 触发降级；14 候选留档；**转换截断**物理发现（白历史行全停 L*51-66） | `2435da193107d738…` |
| `GEO_PROBE_20261009_V1` | 2 | **探针帧几何解出**：upright + 物理整体下移一行（底参照条卷顶部），（历史,目标）标签=设计标签；强化判据重判 14 候选 → **NEW_INTERMEDIATE=0**（紫罗兰候选=码 1 别名，码轴漂移证据） | `f526fc49242ade35…` |
| `VSH_LADDER_20261009_V1` | 6 | vsh_lv 阶梯：**干净臂 6600↔7200mV 八码零移动（ΔE00≤0.66）**；6000 臂白清污染作废（drf 32661 慢 50% + 藏青残留场）；stock active 表=6000mV 钉死 | `c6e85404f45ed4f0…` |

全部门证、照片、分析脚本、判决 JSON 在 `.test-output/hardware/<批次>/`（本地，不入 git）。

## 4. 总结论（如实）

**stock 波形物理内，这块板的颜色=6 个端点，没有更多可挖的。** 杠杆穷尽表：

| 杠杆 | 结果 | 证据 |
|---|---|---|
| OTP 8 码直寻址 | 6 色可用；绿不可寻址；码 2/5 别名白 | 9-25 两批硬测量 |
| 转换中间态（MAP-v2 64 有向对） | 无新独立色；终点全落既有端点集（含跨码别名） | CMAP+GEO 重判 |
| 电压阶梯（vsh_lv 6000/6600/7200mV） | 安全区零移动 | VSH_LADDER |
| 剂量轴 / 同压重复保明度 / 多目标历史 / WF20/23 混合 / HOLD 码 等 | 证伪（14 项清单） | STATUS_HANDOFF 证伪节 |

**唯一已验证的"多明度"路径 = 空间抖动混色**（L535 demo 的渐变就是这么渲染的）。
物理线索留档：转换截断表明白→暗驱动存在中间亮度态且短期稳定（衰减 <0.5 L*/373s），
但 stock LUT 没有任何转换把它们钉成可达端点。

## 5. 下一阶段入口（按建议优先级）

1. **抖动色谱巩固（主线，推荐）**：以 calibrated 调色板 `host/color_pipeline/palettes/mf1750_l535_measured_v1.json`
   为基，做 6 色 × N 级明度的抖动色卡帧（离线 0 刷新可先生成预览）→ 真屏标定每级实测 Lab →
   迭代出"每色 10+ 级"的可查色谱。这条不依赖任何新波形物理。
2. **绿码日光鉴别（0 刷新，任意日光窗口）**：屏留绿块帧或复用 demo 帧重拍，判定绿端点 L*47.3
   是日光真值还是 09-25 瞬态；若瞬态→绿端点重标定。
3. **6000mV 干净臂补测（2 刷，低优先）**：科学完备性；预期与 stock 历史行为一致。
4. **异色历史 4 刷批**（MAP 设计文档开放问题②）：预期价值有限，排在抖动主线之后。
5. **厂商函证 + MISO 转接板（硬件 backlog）**：隐藏命令 0xE9/0x20/0x21 语义、LUT RAM 寻址、
   demo 类密帧 180° vs 网格类 upright 的统一解释。

## 6. 操作要点（新会话必读）

- **刷新预算制**：每批声明预算，失败即停不重发；证据目录 O_EXCL；manifest 自封
  （`integrity.sha256 = sha256(json.dumps(manifest_without_integrity, sort_keys=True, separators=(',',':'), ensure_ascii=True))`）
- **照明硬门**：ROI(0.36,0.23,0.78,0.57) P95 vs 参照 157.0
  （`.test-output/hardware/LH1_REBOUND_TARGET_20260917_V1/post-target.jpg`），窗口 [0.85,1.3]，无 --force
- **照片校正四边形（台架第二次移动后）**：`[(0.2917,0.177),(0.7972,0.2062),(0.7909,0.5202),(0.2908,0.5264)]`；
  若台架再动，用 SIFT 单应从历史锚帧重映射（脚本模式见 GEO_PROBE/L535_DAYLIGHT_ACCEPT 批）
- **几何标定帧设计教训**：用全宽条纹，勿用小方块角标（转换欠驱动会毁掉小面积标记）
- **刷写铁律**：relay OFF + J2-off + 钉 bin sha256 + 版本预检 tag；刷写工具
  `mf1750_app_only_single_boot_flash.py`；生产与 L535 变体（v1 `cb25e57c…`/v2 `e1b6b754…`）复位安全
- **campaign 固件禁令**：LH/PAL1 类刷后首次启动=campaign boot，之后任何复位永久砖 NVS——本主线不用
- **长期断电首刷**：先通电静置 ~20 分钟（9 天断电致 DRF 60s 超时的实证）
- **相机**：VID_32E4:PID_4801，MJPG 4000×3000/f15/focus79/exposure-6/WB4600，
  工具 `tools/mf1750_lh1_camera_capture.py`，anchor `.test-output/hardware/LH2_DRIVE_MAP_20260918_V1/observation-anchor-post-map.json`
- **设备绑定**：192.168.1.5 ↔ MAC A4-CB-8F-D9-FC-D4（DHCP 会漂移，用
  `mf1750_exact_ipv4_mac_binding_once.py` 实证后再动手）
- **GitHub 推送**：直连 SSL 失败时用 `git -c http.proxy=http://127.0.0.1:17890 push`

## 7. 固件/工具资产指针

- L535 帧路径变体：v1 `cb25e57c424ad7c9…`（tag `MF1750_L535_FRAME_V1_20260926`）、
  v2 `e1b6b754…`；vsh 阶梯三档：6000 `561db2b2…` / 6600 `748c4037…` / 7200 `8561dbd0…`
  （离线包 `.test-output/offline/VSH_LADDER_FW_20261010_V1/` manifest `6b68720e…`）
- 波形表生成器：`host/runtime_waveform/l535_table_builder.py`（默认输出==reference 535B 逐字节，
  表头 6 旋钮 mV 编码）；格式注册 `SPD1657_R20_L535_GEOMETRY_V1`
- MAP-v2 离线包：`.test-output/offline/CMAP_V2_20261009_R1/`（manifest `2e3b966c…`）
- 设计文档：[`MF1750_L535_FRAME_PATH_DESIGN_2026-09-26.md`](MF1750_L535_FRAME_PATH_DESIGN_2026-09-26.md)、
  [`MF1750_COLOR_INTERMEDIATE_MAP_V2_DESIGN_20261009.md`](MF1750_COLOR_INTERMEDIATE_MAP_V2_DESIGN_20261009.md)

## 8. 回归基线

- `python tools/run_host_tests.py --output host-test-report.json --force`（约 43 分钟；
  唯一已知 error=8 月残骸 `tests/test_mf1750_pending_live_runner_transport.py`，不修）
- `python tools/check_repo_contract.py`（须 passed: True）
- 最近实测：frame_tool+waveform+cmap 78 passed + 52 subtests；contract 干净
