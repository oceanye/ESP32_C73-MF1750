# EC5 矩形抖动扩色卡操作与判读卡（2026-08-10）

## 当前边界

- 当前现场状态：`J2 OFF / 屏幕干净全白`。
- 本实验只使用已验证的 factory-OTP 原生码
  `{0=黑, 1=白, 2=黄, 3=红, 5=蓝, 6=绿}`；不使用 `4/7`。
- 每个物理像素仍只有一个原生色码。实验测试的是相邻像素的**空间混色**，不测试
  单像素多粒子混合，也不写 runtime LUT、VCOM、电压、相位或刷新时序。
- 第一动作只显示固定 Atlas；人工观察完成后，第二动作 White 必须重新 preflight、
  重新逐字授权。没有自动连刷、retry 或 recovery。
- 物理 runner 必须在一个专用、非并发的 DCA Python 进程中运行，并始终使用同一 claim
  registry；不得删除、搬移或换路径绕过 claim，也不得在同一进程并发调用旧 COLOR_LAB、
  matrix 或 recovery runner。

## 屏幕布局

左右两个 512×600 控制器各显示完全相同的 `7 行 × 5 列` 色卡，局部 2×2 图案的
方向和相位也相同。每行从左到右固定为：

`纯 A | 75%A+25%B | 50%A+50%B | 25%A+75%B | 纯 B`

50/50 格是原文章的一像素 A/B 棋盘格；25/75 格使用同一个 2×2 Bayer 阈值块。
每个矩形为 84×68 px，图案在矩形左上角独立重置，格间白沟为 10 px。

| 行（自上而下） | A + B | 文章中的观感假设 |
|---:|---|---|
| 1 | 红 + 黄 | 橙 |
| 2 | 黄 + 白 | 浅黄 |
| 3 | 绿 + 黄 | 青柠/黄绿 |
| 4 | 红 + 蓝 | 紫 |
| 5 | 红 + 绿 | 棕 |
| 6 | 绿 + 蓝 | 青/天蓝 |
| 7 | 红 + 白 | 浅粉 |

上述名称只是待检验的观感提示。现场应优先记录“红+蓝 50/50”等配方和自己的颜色
描述，不能因预期名称而判定通过。

## 固定离线身份

- Atlas frame SHA-256：
  `3b65803a558e91ad2112a75b158a1b696666c015829ce9fd0bce401ba96a44b7`
- Atlas CS1/CS2 DTM SHA-256（两者逐字节相同）：
  `d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1`
- White frame SHA-256：
  `91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d`
- 离线 bundle：
  `.test-output/offline/MF1750_EC5_DITHER_COLOR_ATLAS_OFFLINE_20260810_V1/`
- bundle manifest canonical/file SHA-256：
  `30360b5b460becd95fa2a4f028c3eace79a6ca9acd43d3e72a7c237e2995128f` /
  `524e7b16802315d2a50f6ffc2fb8b43d5c0add42540e3c7929925db7f70ca295`

正式 staged release：

- 目录：
  `.test-output/hardware/MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1/`
- campaign file/canonical SHA-256：
  `37b20c82524bd72d411f15c62dbe5afd4dcebae8c60419d69d75b270093c9707` /
  `eecb1a55b367bac60cccb91910a2bb9b0c3666fc5c489f43b2143560ff545708`
- release file/canonical SHA-256：
  `ec3e2d873badadef615b06b6a30948738ef80a4c4c3e31cbe24344454a037612` /
  `68c5ffd09a9a46644e59493a985d21c2a035c5e21aba3324355ebd2eab5df7fe`
- firmware BIN：`787312` bytes，SHA-256
  `49f39718e1160be021565fb6b941d71b997ebf91a2abcb73879df3dd06a6e7d4`
- firmware ELF：`13241104` bytes，SHA-256
  `f865d6e52dac827b06cdac5a011222dbf77fa5e30b5453950545845c2cf6fb16`
- Atlas action：
  `ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c`
- White action：
  `35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3`

该 release 自身授权的可见刷新数仍为 `0`；上述 action ID 只是固定身份，不能代替
刷写前门、J2-OFF 诊断、J2-ON 实时读数及每次动作的独立人工授权。

严格预览只是原生码位置图，不预测反射式真屏颜色。参考方法来自
[MyEmbeddedStuff 原实验](https://myembeddedstuff.com/e-ink-spectra-6-color)及
[Adafruit 摘要](https://blog.adafruit.com/2026/01/05/beyond-6-colors-exploring-dithering-on-spectra-6-color-e-ink-displays/)。

## Atlas 刷新后的最短回报格式

先报告公共项：

```text
左右布局是否一致；白沟/边界是否干净；是否有旧残留；
电气是否正常；温度__°C；ESP32 是否重启。
```

然后每行可使用：

```text
行N A+B：75/25=__；50/50=__；25/75=__；
三档是否从A到B单调；左右是否一致；约1米是否融合；
20–30厘米是否能看出A/B网点；是否有条纹/摩尔纹。
```

快速分类：

- `A`：与纯 A 同组；
- `B`：与纯 B 同组；
- `M`：正常观察距离下与两端均不同的表观混色；
- `G`：只见颗粒/网点，没有融合；
- `?`：不确定。

应将色相和明暗分开描述。最后把 21 个混合格按肉眼同色归组，剔除与六个纯色端点
同组者；左右不一致的候选也不计入“新增表观色组”。即使新增组为 0，协议仍可为
`PROTOCOL PASS / VISUAL NEGATIVE`。

## 硬停止

- 刷入前 J2 必须保持断开；只允许 exact app-only binary，写后 digest 必须通过。
- J2 接通后必须为 3.3 V、CV、电流/温度正常、BUSY=1、RST/CS1/CS2=0，物理切断可用。
- 任一身份、NVS cursor、GPIO、BUSY、帧/DTM、单 driver 调用或序列检查不符：
  `0 claim / 0 mutation`，不刷新。
- runner 是“4 个只读 GET 后、首次 ARM 前永久 claim”，即 claim-before-mutation；不能只看
  CLI 退出码。只有 result 为 `complete_pass`、ARM/EXECUTE/driver=`1/1/1`、终态证据完整且
  `validate-result` PASS，才可封存人工 observation。
- 执行中 PSU 转 CC、压降/过流、异常升温、异味/噪声、ESP32 重启、单侧缺画或越界：
  立即物理断开 J2，保留 UNKNOWN；不 retry，不自动白恢复。
- 任意 timeout、异常、UNKNOWN 或结果文件缺失同样立即断开 J2；保留原 claim/result，禁止
  retry、reconcile、ordinal2。传输异常时旧审计字段可能只计收到响应的 POST，因此不得把
  `arm_posts=0` 或 `execute_posts=0` 解读为请求肯定未发出。
- Atlas 人工观察与安全项均完成后，White 才能获得一份新的单动作授权；White 完成并
  确认全屏干净白后再断开 J2。
