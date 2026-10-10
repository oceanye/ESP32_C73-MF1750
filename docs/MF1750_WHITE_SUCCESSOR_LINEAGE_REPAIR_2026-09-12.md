# P2-C white successor 身份输出修复：离线记录

执行计划：[MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md](MF1750_LIGHTNESS_EXECUTION_MASTER_PLAN_2026-09-12.md)。本文件不替代现场 admission。

## 2026-09-12 host seal update

The repaired LH4 candidate now has a separate host entry point. Its protocol environment remains `ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1`; `lhr4` is only the isolated PlatformIO build environment. The host checks the LH4 BIN/ELF, repaired source/report, original claims directory and NVS namespace/key, and the 59 workspace inputs used by the isolated build. It rejects the old white BIN/ELF, alternate claims/output directories, and missing source/binding/diagnostic evidence before any delegate or network request.

Root review evidence is [`host-root-review.json`](../.test-output/offline/MF1750_WHITE_LH4_HOST_ROOT_REVIEW_20260912_V1/host-root-review.json), canonical SHA-256 `ae54b311d291c04c768a78839cba133737213d6f8b26335f87898bd1c7ac620b`. It records 8 targeted tests, a complete delegate identity check, historical P2 source deep validation, four rejected identity mutations, 59 loaded/dependency source files, and `network_requests=0`, `flash=0`, `visible_refreshes=0`.

This is still an offline material PASS. It does not establish relay electrical state, a retained clean-white screen, a fresh post-flash boot, or a visible white refresh. The only live action currently authorized is the one W0 white recovery in the master plan, and it remains stopped until the physical gates are evidenced.

## 根因

原白固件的 `identityJson()` 未输出 `source_main_offline_build_file_sha256`。该常量虽存在于 identity.inc，但字段不在 HTTP 身份 JSON 中。原主机逐字段检查因此拒绝，不能把它当作 IP/COM/boot 故障，也不能靠再次运行同一旧固件解决。

## 最终隔离候选 LH4

- 生成器：`tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_lineage_repair.py`。
- 生成源码：`.pio/g_lhr4/`；配置：`platformio.lhr4.ini`；没有覆盖原 `platformio.ini` 或原白固件。
- BIN：`.pio/br_lhr4/lhr4/firmware.bin`，SHA-256=`dc93c95a956eecf7d9cb753e5fb82ea16e5f2142694a8fcd22157481570d2de6`。
- ELF：`.pio/br_lhr4/lhr4/firmware.elf`，SHA-256=`ff3793efde294bf981f3b1932799fdc574917fe33c0f1d15bf636367c5aba067`。
- 编译清单：`.test-output/offline/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_LINEAGE_REPAIR_20260912_LH4/lineage-repair-offline-build.json`。

相对固定的原 generated main，唯一功能改动为补充缺失的 source report hash JSON 字段。driver 包装文件和 identity.inc 字节不变；frame/profile、contract/action/descriptor、原 NVS namespace/key、启动不刷新和防重放机制不改。新 BIN/ELF 身份必须由新宿主适配独立绑定，不能要求旧 host 接受未知 ELF。

生成器拒绝覆盖已存在的 build-report 目录；只读重入检查原固定输入以及 main/driver/identity/config 全部字节。原 source/white 报告及原始 action/claim 均保留。

## 验证与失败候选

根代理独立复核目录：`.test-output/offline/MF1750_WHITE_LH4_ROOT_REVIEW_20260912_V1/`。

1. 从旧版、LH2、LH3、LH4 的真实 main/identity 中抽取完整 `identityJson()` 与字符串常量，以 MSVC 编译、运行原生测试；保存 `.cpp/.exe`、编译输出和原始 JSON。
2. JSON 解析拒绝重复键。旧版可解析但缺字段；LH2/LH3 可编译却 JSON 无效，均保留为 INVALID；LH4 通过。
3. LH4 的 JSON 删除唯一新增 hash 字段后，与旧 JSON 逐键逐值相同（25→26 keys）。
4. 用私有 pack 副本绑定 LH4 实际 BIN/ELF，调用原严格 host identity 验证器通过；错误 source report hash、source contract 和 running ELF 三个负例仍被拒绝。
5. 原 P2 主固件、原 white、LH1 R3、LH4 共8个实际 BIN/ELF 哈希匹配；记录 `.test-output/hardware/MF1750_LIVE_REENTRY_20260912_V1/artifact-review.json`。
6. 原 P2/white host 和 app-only 工具回归 36 passed；新工具 Ruff 检查通过。

以上证明的是离线修复范围及身份校验，不证明当前电气条件或白刷新成功。中间文件中的 PASS 只能按各自范围解释，LH2/LH3 的候选地位以 INVALID 和根复核结果为准。

## 后续边界

相同 white action 的原永久 claims、原 source claim 和设备 NVS 必须保留并核查，不能用新 claims 目录或清 cursor 重放。LH1 R3 的 source white hash 固定为旧 BIN，因此 W0 修复版恢复后仍须独立重绑定 LH1 source/runner，不能只看 NVS=2。

本轮设备仍运行此前旧白固件；没有刷写 LH4，没有新的 ARM/EXECUTE/driver/visible refresh。当前缺少整屏相机覆盖与外部电气实测，现场保持 HOLD_FOR_EVIDENCE。完整流程与唯一下一入口见统一执行计划及 STATUS 顶部。

## W0 field result 2026-09-12

The LH4 application-only write and verify passed at `0x10000`, followed by one hard reset. A fresh post-flash J2-OFF diagnostic passed on boot `2f4d25eff2a04b6d` with four GETs, zero POSTs, BUSY=0, and the LH4 ELF hash. After one relay ON command and independent ON query, the fixed white action completed with exactly one ARM, one EXECUTE, one driver call, and one visible refresh. The relay was returned OFF. The operator then confirmed `全白，ok`; the camera photo is auxiliary and its edge occlusion remains recorded. W0 is `PASS_PREREQUISITE_ONLY`, with no lightness qualification.

The complete execution review is [`execution-review.json`](../.test-output/hardware/MF1750_WHITE_RECOVERY_20260912_W0_LH4_V1/execution-review.json), canonical SHA-256 `2bef73c1340be23cbd9e06a971ecce88f7dd1a79569cb9cf4b6bb5ac5f519179`. The next lightness action requires an independently sealed LH1 runner bound to this LH4 white identity; the existing LH1 R3 source binding remains incompatible.
