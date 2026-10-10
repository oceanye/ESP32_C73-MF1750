from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_armcc_exec_sink_inventory_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ArmccExecSinkInventoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_exact_object_and_axf_corpora_are_identity_pinned(self) -> None:
        corpus = self.report["corpus"]
        objects = corpus["retained_objects"]
        self.assertEqual(objects["file_count"], 34)
        self.assertEqual(objects["total_bytes"], 30_054_060)
        self.assertEqual(
            objects["canonical_manifest_sha256"],
            "3c17874f2a26e831ebc0a9431ac92e4a27690912a510ee3318f082607fa8b4c7",
        )
        self.assertEqual(objects["files"][0]["path"], "Output/comm.o")
        self.assertEqual(objects["files"][-1]["path"], "Output/usart.o")
        self.assertEqual(
            next(
                row["sha256"]
                for row in objects["files"]
                if row["path"] == "Output/edp_init.o"
            ),
            "6854348d4b2dd797974d5d0c00fe806cf519a9a12271f54a9e4e81be864dac76",
        )

        axfs = corpus["final_axfs"]
        self.assertEqual(axfs["file_count"], 7)
        self.assertEqual(axfs["total_bytes"], 7_491_660)
        self.assertEqual(
            axfs["canonical_manifest_sha256"],
            "faeeed732911e95e54b6843a4b8141095f24b031c9b8c11e0dc60b8afefd2f5c",
        )
        self.assertEqual(
            next(
                row["sha256"]
                for row in axfs["files"]
                if row["path"] == "Output/jiaxian-M009F-T_OQC_YX.axf"
            ),
            "b346a46c67281f51dfc674010acba5621f83e1d9632da9d3b0abd34941154e44",
        )
        self.assertEqual(corpus["selection_rule"], "Output/*.o plus Output/*.axf only")
        self.assertFalse(corpus["prebuilt_CROF_archive_member_in_scope"])

    def test_all_retained_executable_sections_have_only_three_semantic_535_sites(
        self,
    ) -> None:
        aggregate = self.report["retained_objects"]["aggregate"]
        self.assertEqual(aggregate["executable_section_count"], 725)
        self.assertEqual(aggregate["executable_section_bytes"], 65_462)
        self.assertEqual(aggregate["function_symbol_count"], 734)
        self.assertEqual(
            aggregate["semantic_constant_counts"],
            {"535": 3, "704": 0, "799": 0, "800": 0, "1503": 0, "2508": 0},
        )
        sites = aggregate["semantic_constant_sites"]
        self.assertEqual(
            [
                (row["path"], row["function"], row["destination_register"])
                for row in sites
            ],
            [
                ("Output/edp_init.o", "EPD_initial", "r0"),
                ("Output/uartdatadeal.o", "Uart_save_wf_data", "r1"),
                ("Output/uartdatadeal.o", "Uart_save_wf_data", "r2"),
            ],
        )
        self.assertTrue(
            all(row["evidence"] == "decoded_thumb_MOVW_immediate" for row in sites)
        )
        self.assertEqual(
            aggregate["raw_rejected_counts"],
            {"535": 0, "704": 2, "799": 7, "800": 0, "1503": 0, "2508": 0},
        )
        raw = aggregate["raw_rejected_sites"]
        self.assertEqual(
            {row["containing_function"] for row in raw if row["value"] == 704},
            {"UART_SetConfig"},
        )
        self.assertTrue(all(not row["accepted_as_semantic_constant"] for row in raw))

    def test_object_r20_is_one_relocation_bound_single_sink_call(self) -> None:
        calls = self.report["retained_objects"]["aggregate"]["command_calls"]
        self.assertEqual(calls["direct_call_count"], 215)
        self.assertEqual(
            calls["direct_calls_by_sink"],
            {
                "EPD_WriteCMD": 63,
                "EPD_WriteCMD_PreSelected": 5,
                "EPD_WriteCMD_ToBoth": 41,
                "EPD_WriteCMD_ToMaster": 7,
                "EPD_WriteCMD_ToSlave": 7,
                "sendSPICommand": 92,
            },
        )
        boundary = self.report["runtime_loader_boundary"]
        self.assertEqual(len(boundary["object_r20_calls"]), 1)
        call = boundary["object_r20_calls"][0]
        self.assertEqual(call["path"], "Output/edp_init.o")
        self.assertEqual(call["caller"], "EPD_initial")
        self.assertEqual(call["sink"], "EPD_WriteCMD")
        self.assertEqual(call["section_offset"], 380)
        self.assertEqual(call["r0_immediate"]["value"], 0x20)
        self.assertEqual(
            call["binding"],
            "SHT_REL_symbol_plus_R_ARM_THM_CALL_or_JUMP24",
        )
        self.assertEqual(boundary["object_r21_calls"], [])
        self.assertFalse(boundary["r20_to_dual_command_sink_found"])
        self.assertEqual(len(boundary["object_r20_535_same_function_bindings"]), 1)
        association = boundary["object_r20_535_same_function_bindings"][0]
        self.assertEqual(association["function"], "EPD_initial")
        self.assertEqual(
            association["association_strength"], "same_exact_STT_FUNC_only"
        )
        self.assertFalse(association["direct_loop_dataflow_claimed_by_this_inventory"])

    def test_final_axf_call_counts_and_six_r20_sites_are_exact(self) -> None:
        files = self.report["final_axfs"]["files"]
        self.assertEqual(
            [
                (Path(row["path"]).name, row["command_calls"]["direct_call_count"])
                for row in files
            ],
            [
                ("jiaxian-M009F-T_OQC_GX-手动.axf", 75),
                ("jiaxian-M009F-T_OQC_GX.axf", 51),
                ("jiaxian-M009F-T_OQC_GX自动.axf", 75),
                ("jiaxian-M009F-T_OQC_YX.axf", 63),
                ("jiaxian-M032F_OQC_CJ.axf", 72),
                ("jiaxian-M032F_OQC_GX.axf", 75),
                ("WF-79667-168X384.axf", 66),
            ],
        )
        boundary = self.report["runtime_loader_boundary"]
        r20 = boundary["axf_r20_calls"]
        self.assertEqual(len(r20), 6)
        self.assertEqual({row["caller"] for row in r20}, {"EPD_initial"})
        self.assertEqual({row["sink"] for row in r20}, {"EPD_WriteCMD"})
        self.assertNotIn(
            "Output/jiaxian-M009F-T_OQC_GX.axf",
            {row["path"] for row in r20},
        )
        self.assertEqual(boundary["axf_r21_calls"], [])
        self.assertTrue(boundary["all_r20_targets_are_legacy_single_sink"])
        self.assertEqual(len(boundary["axf_r20_535_same_function_bindings"]), 6)

        aggregate = self.report["final_axfs"]["aggregate"]
        self.assertEqual(
            aggregate["semantic_constant_counts"],
            {"535": 20, "704": 0, "799": 0, "800": 0, "1503": 0, "2508": 0},
        )
        self.assertEqual(
            aggregate["raw_rejected_counts"],
            {"535": 0, "704": 14, "799": 14, "800": 14, "1503": 0, "2508": 0},
        )
        raw_800_functions = {
            row["containing_function"]
            for row in aggregate["raw_rejected_sites"]
            if row["value"] == 800
        }
        self.assertEqual(raw_800_functions, {"_ll_ushift_r"})

    def test_thumb_immediate_decoder_and_adjacency_boundary(self) -> None:
        # F240 2017 is MOVW r0,#0x217 (535) in little-endian halfword order.
        self.assertEqual(audit._decode_movw(0xF240, 0x2017), (0, 535))
        adjacent = struct.pack("<H", 0x2020) + b"\x00\xf0\x00\xf8"
        self.assertEqual(audit._direct_r0_immediate(adjacent, 2)["value"], 0x20)
        separated = struct.pack("<HH", 0x2020, 0xBF00) + b"\x00\xf0\x00\xf8"
        self.assertIsNone(audit._direct_r0_immediate(separated, 4))
        self.assertIsNone(audit._decode_movw(0x02C0, 0x0000))

    def test_adjudication_integrity_cli_and_safety(self) -> None:
        report = dict(self.report)
        canonical = report.pop("report_canonical_sha256")
        self.assertEqual(
            canonical, hashlib.sha256(_canonical_bytes(report)).hexdigest()
        )
        self.assertEqual(
            self.report["adjudication"]["verdict"],
            "MODE0_R20_535_ONLY_IN_RETAINED_ARM_ELF_RUNTIME_PATH",
        )
        self.assertFalse(
            self.report["runtime_loader_boundary"][
                "strict_same_build_799_or_800_semantic_constant_found"
            ]
        )
        self.assertFalse(
            self.report["runtime_loader_boundary"][
                "same_build_dual_destination_runtime_loader_proven"
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/mf1750_armcc_exec_sink_inventory_audit.py",
                    "--output",
                    str(output),
                    "--compact",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            cli_report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(cli_report["report_canonical_sha256"], canonical)

        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)


if __name__ == "__main__":
    unittest.main()
