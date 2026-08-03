# 下一阶段新对话启动提示

复制以下内容到清空后的新对话：

> 请先完整阅读工作区中的
> 根目录 `README.md`、
> `docs/REV_A1_R16_CASCADE_FULLFRAME_TEST_2026-08-04.md`、
> `docs/HOST_REFRESH_COLOR_INTEGRATION_2026-08-04.md`、
> `docs/R1_R2_FAST_REFRESH_HANDOFF_2026-08-04.md` 和
> `docs/C2_COLOR_DITHER_HANDOFF_2026-08-04.md`。
> Rev A1 生产文件已经冻结，禁止重新生成或覆盖。`main` 仍为 `3033da0`；
> 无硬件电脑完成的代码候选位于
> `integration/host-fast-refresh-ci-color`，代码与说明点 `aa006c4` 已通过
> 64 项联合回归和 GitHub Actions，但这不是硬件验收。
>
> 家中下一步先完成 MAP_ORIENT_V1 与普通图片 1 MHz 实屏验收，再在独立
> 硬件诊断分支按 1/2/4/8/10 MHz 冷启动扫频，使用仓库分析器记录 DTM hash、
> BUSY、CV、温升和画面。10 MHz 全部门禁通过前不测试 20 MHz。不得根据
> SPD1656 猜测 SPD1657B LUT/局刷命令；取得厂商资料前不改波形、高压或
> power-cut 序列。色彩验收前先回填受控 D65/2deg 六色 Lab 色板。
> 硬件结果确认后再决定逐工作包合并或审查完整集成分支，不直接自动更新
> `main`。
