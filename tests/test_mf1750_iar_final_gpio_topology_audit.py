from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_iar_final_gpio_topology_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CANONICAL_SHA256 = (
    "94c4fbaed8617cf137af674e472088fc06bfcf2e834778b9dbb5be0993bc8a4c"
)
EXPECTED_REPORT_FILE_SHA256 = (
    "f371fa3f52364ce7b696ce265c2441dd05d847ffd8e17bc30bbc009bdf2fc859"
)


def _available_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
    candidates = [] if configured is None else [Path(configured)]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Temp"
            / "iar_ew430_6201_xlink_only"
            / "component_430_xlink_common"
            / "430"
            / "bin"
            / "xlib.exe"
        )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


class Mf1750FinalGpioBoundedDecoderTests(unittest.TestCase):
    def test_immediate_and_constant_generator_R12_forms(self) -> None:
        fixtures = {
            bytes.fromhex("7C40AA00"): 0xAA,
            bytes.fromhex("3C4010A4"): 42_000,
            bytes.fromhex("00004C43"): 0,
            bytes.fromhex("00005C43"): 1,
            bytes.fromhex("00006C43"): 2,
            bytes.fromhex("00006C42"): 4,
            bytes.fromhex("00007C42"): 8,
        }
        for payload, expected in fixtures.items():
            with self.subTest(payload=payload.hex()):
                memory = {0x1000 + index: value for index, value in enumerate(payload)}
                self.assertEqual(audit._decode_call_arg_u16(memory, 0x1004), expected)

    def test_u8_decoder_rejects_a_word_argument(self) -> None:
        payload = bytes.fromhex("3C4010A4")
        memory = {0x1000 + index: value for index, value in enumerate(payload)}
        with self.assertRaisesRegex(audit.FinalGpioTopologyAuditError, "not u8"):
            audit._decode_call_arg_u8(memory, 0x1004)


@unittest.skipUnless(
    _available_xlib() is not None,
    "the identity-pinned official XLIB is not available",
)
class Mf1750FinalGpioTopologyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_xlib()
        assert cls.xlib is not None
        cls.report = audit.build_report(cls.xlib)

    def test_absolute_final_image_and_all_inputs_are_identity_pinned(self) -> None:
        identity = self.report["identity"]
        self.assertEqual(
            identity["xlib"]["sha256"],
            "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
        )
        self.assertEqual(
            identity["final_D43"]["sha256"],
            "56e915d88b4b26ca29baaea766015e43d8f9ba222095650f9a1bebbe6c3906c0",
        )
        self.assertEqual(
            identity["final_TI_TXT"]["sha256"],
            "593194d980f66852223a47493f788ea671335f47b4f1b5c9880d83b9a04ddb49",
        )
        proof = self.report["absolute_image_proof"]
        self.assertTrue(proof["D43_decoded_image_equals_TI_TXT_addressed_image"])
        self.assertEqual(proof["addressed_byte_count"], 2_002)
        self.assertTrue(proof["all_direct_CALLA_machine_targets_validated"])

    def test_final_machine_gpio_endpoints_and_all_P6_writes_are_exact(self) -> None:
        machine = self.report["final_machine_gpio_contract"]
        self.assertEqual(machine["pin_roles"]["CSB"]["MCU_pin"], "P6.3")
        self.assertEqual(machine["pin_roles"]["RST_N"]["MCU_pin"], "P6.1")
        self.assertEqual(machine["pin_roles"]["BUSY_N"]["MCU_pin"], "P6.2")
        self.assertEqual(machine["pin_roles"]["SWC"]["MCU_pin"], "P6.0")
        self.assertEqual(machine["P6OUT_operand_literal_count"], 12)
        self.assertTrue(machine["all_P6OUT_operand_literals_classified"])

        by_role_level = {
            (row["role"], row["level"]): row["instruction_sites"]
            for row in machine["P6OUT_classified_writes"]
        }
        self.assertEqual(by_role_level[("CSB", "low")], ["0xA56A", "0xA5E6"])
        self.assertEqual(
            by_role_level[("CSB", "high")],
            ["0xA5D4", "0xA650", "0xA772"],
        )
        self.assertEqual(by_role_level[("RST_N", "low")], ["0xA65E", "0xA696"])
        self.assertEqual(by_role_level[("SWC", "low")], ["0xA25C"])
        self.assertFalse(
            machine["transport"]["independent_second_CS_software_endpoint_present"]
        )

    def test_transport_is_exactly_one_endpoint_software_9bit_three_wire(self) -> None:
        transport = self.report["final_machine_gpio_contract"]["transport"]
        self.assertEqual(transport["protocol"], "software_9bit_3wire_SPI")
        self.assertTrue(transport["physical_DC_is_initialized_low_once"])
        self.assertFalse(transport["physical_DC_high_write_present"])
        self.assertTrue(transport["command_or_data_is_ninth_bit_on_SDA"])
        self.assertEqual(
            transport["functions"]["SPI_COMMAND"]["ninth_DC_bit_on_SDA"], 0
        )
        self.assertEqual(transport["functions"]["SPI_DATA"]["ninth_DC_bit_on_SDA"], 1)
        for row in transport["functions"].values():
            self.assertEqual(row["payload_bit_order"], "D7_to_D0")
            self.assertEqual(
                row["CSB_low_site"],
                {
                    "0xA566": "0xA56A",
                    "0xA5E2": "0xA5E6",
                }[row["function_start"]],
            )
            self.assertTrue(row["same_fixed_CSB_endpoint"])

        busy = self.report["final_machine_gpio_contract"]["busy"]
        self.assertEqual(busy["polled_register"], "P6IN/0x0241")
        self.assertEqual(busy["polled_mask"], "0x04")
        self.assertFalse(busy["timeout_or_second_busy_endpoint_present"])
        reset = self.report["final_machine_gpio_contract"]["reset"]
        self.assertEqual(reset["active_low_pulse_count"], 2)
        self.assertEqual(reset["delay_calls_between_edges"], 9)

    def test_final_init_transactions_recover_PWR_PSR_PLL_TRES_without_CCSET(
        self,
    ) -> None:
        contract = self.report["final_machine_command_contract"]
        self.assertEqual(len(contract["EPD_Init_transactions"]), 13)
        self.assertEqual(
            contract["named_register_values"],
            {
                "PWR": {"command": "0x01", "data": ["0x3F"]},
                "PSR": {"command": "0x00", "data": ["0x5F", "0x69"]},
                "PLL": {"command": "0x30", "data": ["0x08"]},
                "TRES": {
                    "command": "0x61",
                    "data": ["0x03", "0x20", "0x01", "0xE0"],
                    "decoded_dimensions": [800, 480],
                },
            },
        )
        self.assertFalse(contract["command_0xE0_CCSET_present"])
        self.assertFalse(contract["command_0x20_runtime_LUT_present"])
        self.assertFalse(contract["command_0x21_runtime_LUT_present"])
        self.assertTrue(contract["raw_0xE0_as_TRES_height_byte_not_a_command"])

    def test_each_display_is_192000_byte_solid_fill_then_common_refresh(self) -> None:
        displays = self.report["final_machine_command_contract"]["display_functions"]
        expected_fills = {
            "EPD_Display_White": "0x11",
            "EPD_Display_Black": "0x00",
            "EPD_Display_Yellow": "0x22",
            "EPD_Display_Red": "0x33",
            "EPD_Display_Blue": "0x55",
            "EPD_Display_Green": "0x66",
        }
        self.assertEqual(
            {name: row["fill_byte"] for name, row in displays.items()}, expected_fills
        )
        for row in displays.values():
            self.assertEqual(row["dynamic_fill_call_count"], 192_000)
            self.assertEqual(row["geometry_implied_by_4bpp_fill_only"], "800x480")
            self.assertEqual(row["post_DTM_sequence"], ["PON", "BTST2", "DRF", "POF"])
            self.assertEqual(row["busy_waits"], 3)
            self.assertFalse(row["per_display_GPIO_power_cut_present"])

    def test_exact_panel_and_adjacent_adapter_are_not_collapsed(self) -> None:
        topology = self.report["panel_and_adapter_topology"]
        panel = topology["exact_MF1750_specification"]
        self.assertEqual(panel["geometry"], "1024x600")
        self.assertEqual(panel["controller_count"], 2)
        self.assertEqual(panel["pins"]["SL_CSB"], 4)
        self.assertEqual(panel["pins"]["CSB"], 31)
        self.assertTrue(panel["TSCL_and_TSDA_require_pullups"])
        self.assertTrue(panel["three_wire_contract"]["DC_tied_low"])

        adapter = topology["adjacent_vendor_E2802_cascade_adapter"]
        self.assertTrue(adapter["external_J1_exposes_one_CS"])
        self.assertTrue(adapter["J4_exposes_CS_and_SL_CSB_as_two_separate_header_pins"])
        self.assertFalse(adapter["J4_bridge_closed_by_copper_in_schematic"])
        self.assertTrue(adapter["J4_can_be_shorted_to_fan_one_CS_out_to_SL_CSB"])
        self.assertTrue(adapter["U1_graphical_pin4_name_is_FPL_VCOM"])
        self.assertTrue(adapter["U1_graphical_pin5_name_is_NC"])
        self.assertTrue(adapter["U1_pin4_symbol_FPL_VCOM_conflicts_with_net_SL_CSB"])
        anchors = adapter["word_coordinate_anchors"]
        self.assertEqual(anchors["U1_pin4_drawn_name"]["text"], "FPL_VCOM")
        self.assertEqual(anchors["U1_pin5_drawn_name"]["text"], "NC")
        self.assertEqual(anchors["U1_pin4_number"]["text"], "4")
        self.assertEqual(anchors["U1_pin5_number"]["text"], "5")
        self.assertTrue(
            adapter["U1_graphical_symbol_conflicts_with_exact_MF_spec_pin4_name"]
        )
        self.assertFalse(adapter["physical_header_population_or_jumper_state_proven"])

        adjudication = self.report["adjudication"]
        self.assertEqual(adjudication["final_D43_software_CS_endpoint_count"], 1)
        self.assertEqual(adjudication["exact_MF1750_physical_controller_count"], 2)
        self.assertEqual(adjudication["J4_current_physical_state"], "UNKNOWN")
        self.assertTrue(
            adjudication["pin4_symbol_FPL_VCOM_vs_net_SL_CSB_conflict_is_blocker"]
        )
        self.assertFalse(adjudication["exact_as_built_dual_controller_fanout_proven"])
        self.assertFalse(
            adjudication["independent_controller_selection_possible_from_final_D43"]
        )
        self.assertEqual(
            adjudication["adjacent_adapter_verdict"],
            "CONDITIONAL_FANOUT_PATH_SHOWN",
        )
        self.assertEqual(adjudication["exact_as_built_board_verdict"], "NOT_PROVEN")

    def test_later_V1_2_source_tail_is_not_promoted_into_V1_1_final(self) -> None:
        lineage = self.report["source_binary_lineage"]
        self.assertEqual(lineage["delivered_tree_version"], "V1.2 20250116")
        self.assertEqual(lineage["final_D43_embedded_source_lineage"], "V1.1 20231030")
        self.assertFalse(lineage["same_build_source_and_final_binary"])
        self.assertEqual(lineage["V1_2_display_tail_count"], 6)
        self.assertFalse(lineage["delay_1s_scoped_name_present_in_final_D43"])
        self.assertFalse(lineage["final_D43_each_display_contains_V1_2_tail"])

    def test_safety_boundaries_and_canonical_report_are_stable(self) -> None:
        scope = self.report["scope"]
        self.assertTrue(scope["offline_read_only"])
        for name, value in scope.items():
            if name != "offline_read_only":
                self.assertFalse(value, name)
        boundaries = self.report["evidence_boundaries"]
        self.assertTrue(
            boundaries["single_software_CS_does_not_prove_single_physical_controller"]
        )
        self.assertTrue(boundaries["single_software_CS_does_not_prove_dual_broadcast"])
        self.assertTrue(
            boundaries["adapter_jumper_option_does_not_prove_as_built_state"]
        )
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            EXPECTED_CANONICAL_SHA256,
        )

    def test_checked_in_report_matches_builder(self) -> None:
        path = (
            REPO_ROOT
            / ".test-output/offline/mf1750_iar_final_gpio_topology_audit_20260812.json"
        )
        payload = path.read_bytes()
        self.assertEqual(json.loads(payload.decode("utf-8")), self.report)
        self.assertTrue(payload.endswith(b"\n"))
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(), EXPECTED_REPORT_FILE_SHA256
        )

    def test_cli_emits_metadata_only_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_final_gpio_topology_audit",
                "--xlib",
                str(self.xlib),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        report = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(report["kind"], audit.KIND)
        serialized = completed.stdout.decode("utf-8")
        self.assertNotIn('"raw_D43_bytes":', serialized)
        self.assertNotIn('"raw_TI_TXT_bytes":', serialized)
        self.assertNotIn('"waveform_bytes":', serialized)
        self.assertNotIn('"LUT_bytes":', serialized)


if __name__ == "__main__":
    unittest.main()
