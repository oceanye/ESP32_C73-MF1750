from __future__ import annotations

from pathlib import Path
import re
import unittest

from tools import mf1750_ec5_h3_c23_matched_control_contract as contract
from tools import mf1750_ec5_h3_c23_compiled_identity as compiled


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_CONFIG = REPO_ROOT / "platformio.h3_c23_matched_control_wf23_25.ini"
RECOVERY_CONFIG = REPO_ROOT / "platformio.h3_c23_matched_control_otp_white_wf23_25.ini"
CONTROL_HEADER = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_driver.h"
CONTROL_DRIVER = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_driver.inc"
CONTROL_MAIN = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_main.cpp"
RECOVERY_MAIN = REPO_ROOT / "src" / "ec5_h3_c23_matched_control_otp_white_main.cpp"
CONTROL_BUILD = (
    REPO_ROOT
    / ".pio"
    / "build-h3-c23-matched-no-r20-r21-wf23-25"
    / "ec5_h3_c23_matched_no_r20_r21_wf23_25"
)
RECOVERY_BUILD = (
    REPO_ROOT
    / ".pio"
    / "build-h3-c23-matched-control-otp-white-wf23-25"
    / "ec5_h3_c23_matched_control_otp_white_wf23_25"
)


class Mf1750Ec5H3C23MatchedControlContractTests(unittest.TestCase):
    def test_contract_is_wf23_only_and_binds_existing_t23_v7(self) -> None:
        root = contract.validate_contract()
        self.assertEqual(root["profile_id"], "WF23_25")
        self.assertEqual(contract.PROFILES, ("WF23_25",))
        treatment = root["pinned_treatment_reference"]
        self.assertEqual(
            treatment["release_id"],
            "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4",
        )
        self.assertEqual(
            treatment["runtime_binary_sha256"],
            "6eb9115ef143142de801c96fe31c8b9898455f550a52a85c51cfa7a2026698e2",
        )
        self.assertEqual(
            treatment["runtime_elf_sha256"],
            "d385b01ffcee182d9614d9462489c44628990a576c54979cc9254c8fc3824aa1",
        )
        self.assertEqual(
            treatment["generated_include_sha256"],
            "ee289bc89e9f76f936ca5f2dd0c503f8cc8c8d786c01fc26615c33b9251cb9ff",
        )
        with self.assertRaises(contract.C23MatchedControlContractError):
            contract.validate_contract("WF20_25")

    def test_control_deletes_r20_r21_but_is_not_time_matched(self) -> None:
        descriptor = contract.transaction_descriptor(
            contract.PROFILE_ID, contract.ROLE_CONTROL
        )
        command = descriptor["command_contract"]
        self.assertEqual(command["r20_command_writes"], 0)
        self.assertEqual(command["r21_command_writes"], 0)
        self.assertEqual(command["r20_payload_bytes"], 0)
        self.assertEqual(command["r21_payload_bytes"], 0)
        self.assertTrue(command["power_and_pll_equal_selected_t23_header_values"])
        design = descriptor["control_design"]
        self.assertFalse(design["strict_payload_only_control"])
        self.assertFalse(design["time_matched_control"])
        self.assertEqual(
            design["dual_controller_total_removed"],
            {
                "command_spans": 4,
                "spi_bytes_and_edges": 3010,
                "cooperative_yields": 10,
            },
        )

    def test_actions_namespaces_and_treatment_are_isolated(self) -> None:
        root = contract.validate_contract()
        actions = root["actions"]
        self.assertEqual([action["ordinal"] for action in actions], [1, 2])
        self.assertEqual([action["role"] for action in actions], list(contract.ROLES))
        self.assertEqual(len({action["hardware_action_id"] for action in actions}), 2)
        self.assertEqual(
            [action["nvs_namespace"] for action in actions],
            ["h3c23ctl_v1", "h3c23rw_v1"],
        )
        self.assertTrue(all(len(action["nvs_namespace"]) <= 15 for action in actions))
        self.assertFalse(root["execution_eligible"])
        self.assertFalse(root["live_authorized"])
        self.assertEqual(root["visible_refreshes"], 0)

    def test_c20_and_c23_controls_are_distinct(self) -> None:
        from tools import mf1750_ec5_h3_matched_control_contract as c20

        c23 = contract.validate_contract()
        c20_root = c20.validate_contract()
        self.assertNotEqual(c23["contract_id"], c20_root["contract_id"])
        self.assertNotEqual(c23["campaign_id"], c20_root["campaign_id"])
        self.assertTrue(
            {action["hardware_action_id"] for action in c23["actions"]}.isdisjoint(
                action["hardware_action_id"] for action in c20_root["actions"]
            )
        )
        self.assertTrue(
            {action["nvs_namespace"] for action in c23["actions"]}.isdisjoint(
                action["nvs_namespace"] for action in c20_root["actions"]
            )
        )

    def test_configs_compile_only_the_dedicated_sources(self) -> None:
        control = CONTROL_CONFIG.read_text(encoding="utf-8")
        recovery = RECOVERY_CONFIG.read_text(encoding="utf-8")
        self.assertIn("+<ec5_h3_c23_matched_control_driver.cpp>", control)
        self.assertIn("+<ec5_h3_c23_matched_control_main.cpp>", control)
        self.assertNotIn("ec5_h3_matched_control_main.cpp", control)
        self.assertIn("MF1750_H3_C23_MATCHED_CONTROL_PROFILE_WF23_25=1", control)
        self.assertIn("+<ec5_h3_c23_matched_control_otp_white_main.cpp>", recovery)
        self.assertIn("MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1", recovery)
        self.assertIn("MF1750_OTP_WHITE_FOR_PROFILE_WF20_25=0", recovery)

    def test_driver_uses_exact_wf23_header_derived_payloads(self) -> None:
        source = CONTROL_DRIVER.read_text(encoding="utf-8")
        self.assertIn("{0x0F, 0x00, 0x2A,", source)
        self.assertIn("0x36, 0x34, 0x44}", source)
        self.assertIn("{0x00, 0x2A, 0x36, 0x34,", source)
        self.assertIn("0x44, 0x14, 0x02}", source)
        self.assertIn(
            "dcad961ff7dde220b68567cbf3f90ec38f3521c1dbaf63707705f65492145fb4",
            source,
        )
        self.assertNotIn("0x23, 0x34, 0x32, 0x3A", source)
        self.assertNotIn("kR20Payload", source)
        self.assertNotIn("kR21Payload", source)
        self.assertNotIn("spd1657_wf23_25_empirical_h3.inc", source)

    def test_dedicated_sources_embed_exact_contract_markers(self) -> None:
        root = contract.validate_contract()
        sources = {
            contract.ROLE_CONTROL: CONTROL_MAIN.read_text(encoding="utf-8"),
            contract.ROLE_WHITE: RECOVERY_MAIN.read_text(encoding="utf-8"),
        }
        for action in root["actions"]:
            role = action["role"]
            source = sources[role]
            self.assertIn(root["contract_id"], source)
            self.assertIn(action["hardware_action_id"], source)
            self.assertIn(action["transaction_descriptor_sha256"], source)
            self.assertIn(contract.compiled_descriptor_marker("WF23_25", role), source)
            self.assertIn(contract.command_audit_marker("WF23_25", role), source)

    def test_source_gate_excludes_runtime_payload_and_other_fixture_flags(self) -> None:
        header = CONTROL_HEADER.read_text(encoding="utf-8")
        for flag in (
            "MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3",
            "MF1750_RUNTIME_LUT_PROFILE_WF20_25",
            "MF1750_RUNTIME_LUT_PROFILE_WF23_25",
            "MF1750_ENABLE_H3_MATCHED_NO_R20_R21",
            "MF1750_H3_MATCHED_CONTROL_PROFILE_WF20_25",
            "MF1750_ENABLE_H3_C23_MATCHED_WHITE",
        ):
            self.assertIn(flag, header)
        main = CONTROL_MAIN.read_text(encoding="utf-8")
        forbidden = re.compile(
            r"(?i)(?:\b0x0*20\b|\b0x0*21\b|\bkR20\w*|\bkR21\w*|"
            r"\bR20_PAYLOAD\b|\bR21_PAYLOAD\b)"
        )
        marker_lines_removed = re.sub(
            r"\.asciz .*?(?:\\n\"|\n)", "", main, flags=re.DOTALL
        )
        self.assertIsNone(forbidden.search(marker_lines_removed))

    def test_pair_interpretation_preserves_hue_focus_and_no_splicing(self) -> None:
        comparison = contract.validate_contract()["cross_profile_effect_comparison"]
        self.assertTrue(
            comparison["compare_t20_minus_c20_and_t23_minus_c23_separately"]
        )
        self.assertFalse(comparison["direct_t20_minus_t23_is_body_only_attribution"])
        self.assertFalse(comparison["profile_hybrid_or_record_splice_allowed"])
        self.assertEqual(
            comparison["primary_observable"],
            "same_atlas_position_hue_or_color_class_change",
        )
        self.assertFalse(comparison["brightness_only_counts_as_new_color"])

    def test_built_images_deep_validate_with_exact_bin_elf_link(self) -> None:
        cases = (
            (
                contract.ROLE_CONTROL,
                CONTROL_BUILD,
                CONTROL_MAIN,
                "44e7c55c45be3bdae8acf9b6c6d97f62d05c071786fa63fa460f8a7d32a54dfe",
                "788ce46c6f099a4bf8a2b471e3e23f66133bd096f23edfd8d90a5d6ca917d454",
            ),
            (
                contract.ROLE_WHITE,
                RECOVERY_BUILD,
                RECOVERY_MAIN,
                "8deba59ec437adf40414084e8f6d42d44fb74cd65b4ec45b3b87be6ffa8f6edb",
                "8d4dfb8bbc3e8a8317d3621ea678a3297b80c1c14a7203690b69f55c440657b1",
            ),
        )
        for role, build, source, expected_bin, expected_elf in cases:
            report = compiled.validate_image(
                contract.PROFILE_ID,
                role,
                elf_file=build / "firmware.elf",
                binary_file=build / "firmware.bin",
                transaction_source_file=source,
            )
            self.assertTrue(report["valid"])
            self.assertTrue(report["firmware"]["binary_elf_link"]["exact_match"])
            self.assertEqual(report["firmware"]["binary"]["sha256"], expected_bin)
            self.assertEqual(report["firmware"]["elf"]["sha256"], expected_elf)
            self.assertFalse(report["device_io_performed"])
            self.assertFalse(report["network_io_performed"])
            self.assertEqual(report["visible_refreshes"], 0)

    def test_compiled_gate_rejects_control_source_with_runtime_token(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            source = Path(directory) / "control.cpp"
            source.write_bytes(CONTROL_MAIN.read_bytes() + b"\n// kR20Payload\n")
            with self.assertRaisesRegex(
                compiled.C23CompiledIdentityError,
                "forbidden T23 payload marker",
            ):
                compiled.validate_image(
                    contract.PROFILE_ID,
                    contract.ROLE_CONTROL,
                    elf_file=CONTROL_BUILD / "firmware.elf",
                    binary_file=CONTROL_BUILD / "firmware.bin",
                    transaction_source_file=source,
                )


if __name__ == "__main__":
    unittest.main()
