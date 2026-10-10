from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_final_d43_provider_chain_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


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


class Mf1750IarFinalD43ParserTests(unittest.TestCase):
    def test_compressed_direct_call_reuses_the_last_explicit_target(self) -> None:
        payload = b"""\
##############################################################################
#     IAR Universal Librarian V6.1.3.56              12/Aug/2026  06:00:00   #
##############################################################################
    t_scoped_name        N0001: NAME     'caller'
    t_scoped_name        N0002: NAME     'callee'
    t_beg_pgm            REV=0A CPA=03 LAN=10 30/Oct/2023 'fixture'
    t_symbol_def2        PUBLIC_REL (0001) 0000A000 N0001"caller" [0068]
    t_symbol_def2        PUBLIC_REL (0001) 0000A008 N0002"callee" [0068]
    t_org                (01) 0000A000
    t_call_frame_info    extra: 4 bytes DATA COMMON=0 TOT=0x8 FUNC= N0001"caller"
            direct_call N0002
          1 @0x0 Direct call([7:1-2])
            set_step_kind 4
          2 @0x4 Direct call([8:1-2])
    t_abs_var            B01308A0
                         B01308A0
    t_org                (01) 0000A008
    t_call_frame_info    extra: 4 bytes DATA COMMON=0 TOT=0x2 FUNC= N0002"callee"
    t_abs_var            1001
    t_end                CRC=0000
"""
        parsed = audit.parse_xlib_object_code(payload)
        self.assertEqual(len(parsed["calls"]), 2)
        self.assertEqual(
            [row["target"] for row in parsed["calls"]], ["callee", "callee"]
        )
        self.assertEqual([row["address"] for row in parsed["calls"]], [0xA000, 0xA004])
        self.assertEqual(len(parsed["memory"]), 10)
        audit._validate_direct_call_machine_bytes(parsed)

    def test_ti_txt_rejects_trailing_tokens(self) -> None:
        with self.assertRaisesRegex(audit.FinalD43AuditError, "after terminator"):
            audit._parse_ti_txt(b"@A000\n00\nq\n00\n")

    def test_xlib_identity_mismatch_fails_before_decode(self) -> None:
        xlib = _available_xlib()
        if xlib is None:
            self.skipTest("the identity-pinned official XLIB is not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "xlib.exe"
            shutil.copyfile(xlib, copied)
            payload = bytearray(copied.read_bytes())
            payload[-1] ^= 1
            copied.write_bytes(payload)
            with self.assertRaisesRegex(audit.FinalD43AuditError, "SHA-256 mismatch"):
                audit._pin_xlib(copied)


@unittest.skipUnless(
    _available_xlib() is not None,
    "the identity-pinned official XLIB is not available",
)
class Mf1750IarFinalD43IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_xlib()
        assert cls.xlib is not None
        cls.report = audit.build_report(cls.xlib)

    def test_exact_delivered_artifact_and_tool_identities_are_pinned(self) -> None:
        identity = self.report["identity"]
        self.assertEqual(
            identity["xlib"]["sha256"],
            "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
        )
        expected = {
            "C2_Example.ewp": "409e32ff9ecb6714efea2fd2478ce6fbf1821f55984989f01760d456bdb79582",
            "C2_Example.dep": "8b59303fa9d7a0b1ce453b117009ef4b468e1cac81e8a615e30ea026aa7dbaeb",
            "Debug/Exe/C2_Example.d43": "56e915d88b4b26ca29baaea766015e43d8f9ba222095650f9a1bebbe6c3906c0",
            "Debug/Exe/C2_Example.txt": "593194d980f66852223a47493f788ea671335f47b4f1b5c9880d83b9a04ddb49",
            "Debug/Obj/DELAY.r43": "82eaf1f5ae2ee28f7df7dafb7e9ecf8b46731d7f98784a4731d9b49f638c96da",
            "Debug/Obj/E6_73.r43": "0f4d22c6d07f79d9ededffd50f155dc96d802b0e90bf908c30f2b85f1714ee2f",
            "Debug/Obj/main.r43": "76ada9c8846226457ef74537a345ca1e057e8c11abc1002423424dfffd2640f4",
            "Debug/Obj/E2801.r43": "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3",
            "Debug/Obj/E2802.r43": "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        }
        self.assertEqual(
            {
                name: row["sha256"]
                for name, row in identity["delivered_artifacts"].items()
            },
            expected,
        )

    def test_d43_absolute_records_reconstruct_the_ti_txt_exactly(self) -> None:
        decoded = self.report["absolute_D43_decode"]
        self.assertEqual(decoded["official_tool_operation"], "LIST-OBJECT-CODE")
        self.assertEqual(decoded["returncode"], 0)
        self.assertEqual(decoded["decoded_module_count"], 31)
        self.assertEqual(decoded["scoped_name_count"], 248)
        self.assertEqual(decoded["public_code_symbol_count"], 25)
        self.assertEqual(decoded["call_frame_count"], 19)
        self.assertEqual(decoded["direct_call_count"], 188)
        self.assertTrue(decoded["all_direct_calls_machine_target_validated"])

        equivalence = self.report["D43_TI_TXT_exact_equivalence"]
        self.assertEqual(equivalence["D43_decoded_t_org_01_count"], 25)
        self.assertEqual(equivalence["D43_decoded_t_abs_var_count"], 62)
        self.assertEqual(equivalence["total_unique_bytes"], 2002)
        self.assertEqual(equivalence["byte_mismatch_count"], 0)
        self.assertTrue(equivalence["byte_for_byte_equal"])
        self.assertEqual(
            equivalence["concatenated_data_sha256"],
            "47ad1e653f8e161ce5a63f2dbf2a4dc6a8ed5181e7745384e142bab8869bf897",
        )
        self.assertEqual(
            [row["sha256"] for row in equivalence["segments"]],
            [
                "16f858edd1708583332f20679a4c6fc8e3d86a0f63edd2f2e1abd19efd2110fb",
                "eaf132c40462dd25ee5be6c7944953c92f544953f110bb3a6630b9cb34f13e17",
            ],
        )

    def test_main_and_current_e6_provider_chain_is_exact(self) -> None:
        chain = self.report["final_provider_and_call_chain"]
        self.assertEqual(chain["resolved_current_EPD_Init_provider"], "E6_73")
        self.assertEqual(chain["resolved_current_display_provider"], "E6_73")
        self.assertIsNone(chain["resolved_current_runtime_upload_provider"])
        self.assertEqual(len(chain["main_direct_calls"]), 18)
        self.assertEqual(chain["main_direct_calls"][3]["call_site"], "0xA208")
        self.assertEqual(chain["main_direct_calls"][4]["target"], "EPD_Init")
        self.assertEqual(chain["EPD_Init_direct_call_count"], 51)
        self.assertEqual(
            chain["EPD_Init_target_counts"],
            {
                "SPI_COMMAND": 13,
                "SPI_DATA": 35,
                "check_busy_high": 1,
                "delay": 1,
                "reset": 1,
            },
        )
        for name in audit.DISPLAY_FUNCTIONS:
            self.assertEqual(
                chain["display_target_counts"][name],
                {"SPI_COMMAND": 5, "SPI_DATA": 7, "check_busy_high": 3},
            )
        self.assertFalse(chain["Upload_Temperature_LUT_scoped_name_present"])
        self.assertFalse(chain["Upload_Temperature_LUT_direct_call_present"])

    def test_legacy_upload_edges_are_exact_but_not_final_providers(self) -> None:
        dependency = self.report["project_and_dependency_chain"]
        self.assertEqual(
            dependency["DEP_direct_project_r43_inputs"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertFalse(dependency["E2801_or_E2802_is_direct_input"])
        modules = self.report["absolute_D43_decode"]["decoded_module_names"]
        self.assertNotIn("E2801", modules)
        self.assertNotIn("E2802", modules)

        legacy = self.report["separate_legacy_candidates"]
        self.assertEqual(legacy["E2801.r43"]["EPD_Init_section_id"], "0x2E")
        self.assertEqual(legacy["E2802.r43"]["EPD_Init_section_id"], "0x2D")
        for name in ("E2801.r43", "E2802.r43"):
            self.assertEqual(legacy[name]["Upload_Temperature_LUT_section_id"], "0x1E")
            self.assertEqual(legacy[name]["local_upload_edge_count"], 7)
            self.assertFalse(legacy[name]["EPD_Init_calls_upload"])
        self.assertFalse(
            self.report["adjudication"]["legacy_upload_edges_are_in_final"]
        )

    def test_transport_uses_one_fixed_software_csb_endpoint(self) -> None:
        endpoint = self.report["fixed_software_controller_endpoint"]
        self.assertEqual(endpoint["decoded_absolute_register_address"], "0x0243")
        self.assertEqual(endpoint["decoded_CSB_bit_mask"], "0x08")
        self.assertEqual(
            endpoint["verdict"], "ONE_FIXED_CSB_SOFTWARE_ENDPOINT_IN_CURRENT_FINAL"
        )
        for name in ("SPI_DATA", "SPI_COMMAND"):
            row = endpoint["transport_functions"][name]
            self.assertEqual(row["fixed_CSB_low_instruction_offset"], 4)
            self.assertEqual(row["fixed_CSB_high_instruction_offset"], 110)
            self.assertEqual(row["fixed_CSB_low_write_count"], 1)
            self.assertEqual(row["fixed_CSB_high_write_count"], 1)
        self.assertFalse(endpoint["physical_controller_identity_or_fanout_proven"])
        self.assertFalse(endpoint["dual_controller_load_or_commit_semantics_proven"])

    def test_lineage_and_safety_boundaries_are_not_collapsed(self) -> None:
        decoded = self.report["absolute_D43_decode"]
        self.assertEqual(
            decoded["embedded_source_lineage"], "E6_73_sample code_V1.1_20231030"
        )
        self.assertEqual(
            decoded["delivered_workspace_directory_lineage"],
            "E6_73_sample code_V1.2_20250116",
        )
        self.assertFalse(decoded["is_claimed_as_a_V1_2_rebuild"])
        scope = self.report["scope"]
        self.assertTrue(scope["offline_read_only"])
        for name in (
            "hardware_accessed",
            "serial_or_COM_accessed",
            "device_network_accessed",
            "firmware_written_or_flashed",
            "reset_requested",
            "visible_refresh_requested",
            "physical_action_token_or_claim_created",
            "raw_D43_or_object_bytes_emitted",
            "raw_LUT_or_waveform_emitted",
        ):
            self.assertFalse(scope[name])

    def test_canonical_report_is_stable(self) -> None:
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "51a646c74d76ba3f10e6c56e6a59c232724b2d9f7e0a0040ec18f40f60908976",
        )

    def test_cli_emits_metadata_only_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_final_d43_provider_chain_audit",
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
        self.assertNotIn('"object_bytes":', serialized)
        self.assertNotIn('"waveform_bytes":', serialized)


if __name__ == "__main__":
    unittest.main()
