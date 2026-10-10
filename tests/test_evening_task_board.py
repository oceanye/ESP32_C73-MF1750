from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD = REPO_ROOT / "docs" / "MF1750_N2_N8_EVENING_TASK_BOARD_2026-08-08.md"


class EveningTaskBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = BOARD.read_text(encoding="utf-8")

    def section(self, start: str, end: str) -> str:
        return self.text.split(start, 1)[1].split(end, 1)[0]

    def test_board_freezes_counts_power_exceptions_and_software_status(self) -> None:
        for token in (
            "4 sessions / 8 actions",
            "最低路线是 N3A repeat-2 的 4 actions 加 N3B 的 32 actions，共 **36 actions**",
            "**36/38/40 actions**",
            "11 sessions / 22 actions",
            "8 sessions / 9 actions",
            "7 sessions / 42 actions",
            "5 sessions / 15 actions",
            "频率严格为 `1→2→4→8→10 MHz`",
            "正常供电语义",
            "不需要例行断电",
            "PHYSICAL PRODUCTION SOFTWARE READY (7/7)",
            "NOT HARDWARE-EXECUTED",
        ):
            self.assertIn(token, self.text)

    def test_board_names_landed_physical_entrypoints(self) -> None:
        paths = (
            "tools/g1_s1_n2_physical_campaign.py",
            "tools/g1_s1_rc2g_n2_physical_once.py",
            "tools/g1_s1_rc2g_n2_physical_analyzer.py",
            "tools/g1_s1_n3a_physical_plan.py",
            "tools/g1_s1_n3a_physical_execution.py",
            "tools/g1_s1_rc2g_n3a_physical_once.py",
            "tools/g1_s1_n3a_physical_analyzer.py",
            "tools/g1_s1_n3b_physical_execution.py",
            "tools/g1_s1_rc2g_n3b_physical_once.py",
            "tools/g1_s1_n3b_physical_analyzer.py",
            "tools/g1_s1_rc2g_n4_v3_physical_once.py",
            "tools/g1_s1_n4_v3_physical_analyzer.py",
            "tools/mf1750_n5_physical_campaign.py",
            "tools/mf1750_n5_physical_execution.py",
            "host/application/n6_physical_execution.py",
            "tools/mf1750_n6_physical_once.py",
            "tools/mf1750_n7_physical_campaign.py",
            "tools/mf1750_n7_physical_once.py",
            "tools/mf1750_n7_physical_analyzer.py",
            "tools/g1_s1_n8_physical_execution.py",
            "tools/g1_s1_rc2g_n8_physical_once.py",
            "tools/g1_s1_n8_physical_analyzer.py",
        )
        for relative in paths:
            self.assertIn(relative, self.text)
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)

    def test_no_legacy_public_live_command_is_executable_from_board(self) -> None:
        for command in (
            "python -m tools.g1_s1_rc2g_n3_once",
            "python -m tools.g1_s1_rc2g_n4_v3_once",
            "python -m tools.mf1750_n5_fixed_execution",
            "python -m tools.mf1750_n6_visible_once",
            "python -m tools.mf1750_n7_spi_sweep_once",
            "python -m tools.g1_s1_rc2g_n8_once",
            "python -m tools.g1_s1_n8_analyzer",
        ):
            self.assertNotIn(command, self.text)
        self.assertIn("旧 `tools/mf1750_n6_visible_once.py serve`", self.text)

    def test_n2_physical_cli_schedule_and_per_action_approval_are_present(self) -> None:
        section = self.section("## 4. N2", "## 5. N3")
        for token in (
            "python -m tools.g1_s1_n2_physical_campaign compile",
            "--minimum-interval-seconds $MinimumIntervalSeconds",
            "--planned-cooldown-seconds $PlannedCooldownSeconds",
            "operator_process_schedule",
            "not_a_supplier_rating=true",
            "python -m tools.mf1750_limit_profile policy-template",
            "每个 action 之前都必须重新取得最新 usage evidence",
            "python -m tools.g1_s1_rc2g_n2_physical_once describe",
            "python -m tools.g1_s1_rc2g_n2_physical_once run",
            "python -m tools.g1_s1_rc2g_n2_physical_once finalize",
            "python -m tools.g1_s1_rc2g_n2_physical_once validate",
            "python -m tools.g1_s1_rc2g_n2_physical_analyzer",
            "不需要、也不允许为了“保险”反复断 J2",
            "间隔不足必须在 claim 与联网之前拒绝",
        ):
            self.assertIn(token, section)

    def test_n3_physical_production_contract_is_ready_but_not_hardware_run(self) -> None:
        section = self.section("## 5. N3", "## 6. N4")
        for token in (
            "physical production-live 软件入口已完成",
            "尚未执行 N3 真屏",
            "python -m tools.g1_s1_n3a_physical_plan compile",
            "python -m tools.g1_s1_rc2g_n3a_physical_once",
            "python -m tools.g1_s1_rc2g_n3b_physical_once",
            "tools/g1_s1_n3a_physical_analyzer.py",
            "analyze_n3b_physical_result_files()",
            "永远不运行未选中的 N3A template",
            "UNKNOWN_DO_NOT_RETRY",
        ):
            self.assertIn(token, section)

    def test_n4_and_n5_use_physical_production_clis(self) -> None:
        n4 = self.section("## 6. N4", "## 7. N5")
        n5 = self.section("## 7. N5", "## 8. N6")
        for token in (
            "python -m tools.g1_s1_rc2g_n4_v3_physical_once",
            "--confirm-panel-build $N4PanelBuildConfirmation",
            "--confirm-profile $N4ProfileConfirmation",
            "tools/g1_s1_n4_v3_physical_analyzer.py",
        ):
            self.assertIn(token, n4)
        for token in (
            "python -m tools.mf1750_n5_physical_campaign compile",
            "python -m tools.mf1750_n5_physical_execution describe",
            "python -m tools.mf1750_n5_physical_execution run",
            "python -m tools.mf1750_n5_physical_execution finalize",
            "python -m tools.mf1750_n5_physical_execution build-session-bundle",
            "python -m tools.mf1750_n5_physical_execution validate-bundle",
        ):
            self.assertIn(token, n5)

    def test_n6_physical_cli_and_safety_contract_are_frozen(self) -> None:
        section = self.section("## 8. N6", "## 9. N7")
        for token in (
            "host/application/n6_physical_execution.py",
            "tools/mf1750_n6_physical_once.py",
            "python tools/mf1750_n6_physical_once.py describe",
            "python tools/mf1750_n6_physical_once.py materialize",
            "python tools/mf1750_n6_physical_once.py serve",
            "python tools/mf1750_n6_physical_once.py finalize",
            "python tools/mf1750_n6_physical_once.py validate",
            "SERVE_ONE_N6_PHYSICAL_ACTION__CLAIM_BEFORE_NETWORK__NO_RETRY_NO_RECOVERY",
            "--n5-result-dir",
            "--n5-palette-observation",
            "--receipt-commit-output",
            "--incident-receipt-output",
            "UNKNOWN_DO_NOT_RETRY",
        ):
            self.assertIn(token, section)
        self.assertNotIn("python -m tools.mf1750_n6_visible_once serve", section)

    def test_n7_uses_physical_campaign_runner_and_analyzer(self) -> None:
        section = self.section("## 9. N7", "## 10. N8")
        for token in (
            "python -m tools.mf1750_n7_physical_campaign",
            "python -m tools.mf1750_n7_physical_once describe",
            "python -m tools.mf1750_n7_physical_once run",
            "python -m tools.mf1750_n7_physical_once finalize",
            "python -m tools.mf1750_n7_physical_once validate",
            "python -m tools.mf1750_n7_physical_analyzer",
            "N7-PHYSICAL-FINAL.json",
        ):
            self.assertIn(token, section)

    def test_n8_exact_actions_and_physical_cli_are_present(self) -> None:
        section = self.section("## 10. N8", "## 11. 推荐分夜执行顺序")
        action_keys = (
            "n8-aba-q1-q4-q1-map",
            "n8-aba-q1-q4-q1-a1",
            "n8-aba-q1-q4-q1-b",
            "n8-aba-q1-q4-q1-a2",
            "n8-warm-q1-q2-q3-q4-map",
            "n8-warm-q1-q2-q3-q4-w1",
            "n8-warm-q1-q2-q3-q4-w2",
            "n8-warm-q1-q2-q3-q4-w3",
            "n8-warm-q1-q2-q3-q4-w4",
            "n8-temperature-low-q4-map",
            "n8-temperature-low-q4-target",
            "n8-temperature-nominal-q4-map",
            "n8-temperature-nominal-q4-target",
            "n8-temperature-high-q4-map",
            "n8-temperature-high-q4-target",
        )
        positions = [section.index(key) for key in action_keys]
        self.assertEqual(positions, sorted(positions))
        for token in (
            "compile_n8_physical_execution_context()",
            "python -m tools.g1_s1_rc2g_n8_physical_once",
            "--physical-contract $N8PhysicalContract",
            "--prior-result $ImmediatePriorResultDirectory",
            "python -m tools.g1_s1_n8_physical_analyzer",
            "--result-directory $N8ResultDirectory01",
            "dynamic_first_action_baseline",
            "正常完成一个 nominal session 不强制断 J2",
            "UNKNOWN_DO_NOT_RETRY",
        ):
            self.assertIn(token, section)

    def test_board_contains_no_prefabricated_visible_authorization(self) -> None:
        self.assertNotIn("AUTHORIZE_ONE_VISIBLE_", self.text)
        self.assertIn("$UserOneActionConfirmation", self.text)
        self.assertIn("不预生成、不批量签发、不跨 action 复用", self.text)

    def test_document_links_and_status_reference_exist(self) -> None:
        for relative in (
            "docs/STATUS_HANDOFF.md",
            "docs/N2P_RC2G_FIXED_EXECUTION_V2.md",
            "docs/N3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md",
            "docs/N4_V3_RC2G_FIXED_EXECUTION_HANDOFF_2026-08-08.md",
            "docs/N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md",
            "docs/N6_BROWSER_E2E_OFFLINE_HANDOFF_2026-08-08.md",
            "docs/N8_CARRYOVER_WARM_TEMPERATURE_OFFLINE_HANDOFF_2026-08-08.md",
        ):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
            if relative != "docs/STATUS_HANDOFF.md":
                self.assertIn(Path(relative).name, self.text)


if __name__ == "__main__":
    unittest.main()
