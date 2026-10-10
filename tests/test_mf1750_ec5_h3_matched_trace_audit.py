from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_ec5_h3_matched_trace_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
TREATMENT_RELEASE = (
    REPO_ROOT / ".test-output/hardware/"
    "MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/WF20_25-release.json"
)
CONTROL_BUILD = (
    REPO_ROOT / ".pio/build-h3-matched-no-r20-r21-wf20-25/"
    "ec5_h3_matched_no_r20_r21_wf20_25"
)
CONTROL_ELF = CONTROL_BUILD / "firmware.elf"
CONTROL_BIN = CONTROL_BUILD / "firmware.bin"
CONTROL_SOURCE = REPO_ROOT / "src/ec5_h3_matched_control_main.cpp"


def _audit() -> dict:
    return audit.audit_pair(
        treatment_release_file=TREATMENT_RELEASE,
        control_elf_file=CONTROL_ELF,
        control_binary_file=CONTROL_BIN,
        control_transaction_source_file=CONTROL_SOURCE,
    )


class Mf1750Ec5H3MatchedTraceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = _audit()

    def test_exact_artifact_identities_are_bound(self) -> None:
        report = self.report
        self.assertEqual(report["kind"], audit.KIND)
        self.assertTrue(report["valid"])
        self.assertEqual(report["profile_id"], "WF20_25")
        identity = report["identity"]
        self.assertEqual(
            identity["treatment_release"]["release_id"],
            "52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e",
        )
        self.assertEqual(
            identity["treatment_elf"]["sha256"],
            "63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df",
        )
        self.assertEqual(
            identity["control_elf"]["sha256"],
            "27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41",
        )
        self.assertEqual(
            identity["control_binary"]["sha256"],
            "f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e",
        )
        self.assertEqual(len(report["audit_id"]), 64)
        self.assertEqual(len(audit.validate_seal(report)), 64)

    def test_compiled_payload_symbols_match_except_for_treatment_only_luts(
        self,
    ) -> None:
        payloads = self.report["compiled_payload_symbols"]
        expected = {
            "runtime_psr": "5fe9",
            "power": "0f002334323a",
            "pll": "02",
            "tres": "02000258",
            "e9": "01",
        }
        for role, value in expected.items():
            self.assertEqual(payloads[role]["value_hex"], value)
            self.assertTrue(payloads[role]["treatment_control_exact_equal"])
            self.assertIn("control_symbol", payloads[role])
        self.assertEqual(payloads["r20"]["bytes"], 799)
        self.assertEqual(payloads["r20"]["sha256"], audit.EXPECTED_R20_SHA256)
        self.assertEqual(payloads["r21"]["bytes"], 704)
        self.assertEqual(payloads["r21"]["sha256"], audit.EXPECTED_R21_SHA256)
        self.assertTrue(payloads["r21"]["all_ff"])
        self.assertTrue(all(not row["raw_bytes_emitted"] for row in payloads.values()))

    def test_compiled_command_call_surface_is_typed_not_a_bin_scan(self) -> None:
        surface = self.report["compiled_call_surface"]
        self.assertEqual(
            surface["treatment_global_commands"],
            [
                {"command": "0x00", "data_bytes": 2},
                {"command": "0x01", "data_bytes": 6},
                {"command": "0x30", "data_bytes": 1},
                {"command": "0x61", "data_bytes": 4},
            ],
        )
        self.assertEqual(
            surface["treatment_per_controller_template"],
            [
                {"command": "0xE9", "data_bytes": 1},
                {"command": "0x20", "data_bytes": 799},
                {"command": "0x21", "data_bytes": 704},
            ],
        )
        self.assertEqual(surface["treatment_upload_controller_order"], ["CS1", "CS2"])
        self.assertEqual(
            [item["command"] for item in surface["control_direct_commands"]],
            ["0x00", "0x01", "0x30", "0x61", "0xE9", "0xE9"],
        )
        self.assertEqual(surface["control_R20_R21_compiled_command_calls"], 0)
        self.assertEqual(surface["control_R20_R21_payload_symbols"], 0)
        self.assertEqual(surface["dtm_controller_order"], ["CS1", "CS2"])
        self.assertEqual(surface["effective_idle_gates_each"], 3)
        self.assertTrue(surface["treatment_payload_writer_has_256_byte_yield_cadence"])
        self.assertFalse(surface["control_payload_writer_has_yield"])
        self.assertFalse(surface["whole_BIN_opcode_scan_performed"])

    def test_all_compiled_common_panel_helpers_normalize_equal(self) -> None:
        common = self.report["compiled_common_functions"]
        self.assertTrue(common["all_normalized_equal"])
        self.assertEqual(len(common["functions"]), 12)
        self.assertEqual(set(common["functions"]), set(audit.COMMON_FUNCTION_PATTERNS))
        self.assertEqual(
            common["aggregate_sha256"],
            "5df9ebab27c557c72d1fbeceae7242c35dabeae5ed6b7e38fb10ae4d1baf98a1",
        )
        for item in common["functions"].values():
            self.assertTrue(item["normalized_equal"])
            self.assertEqual(len(item["normalized_instruction_sha256"]), 64)
            self.assertFalse(item["raw_disassembly_emitted"])

    def test_strip_exact_four_typed_upload_spans_equals_control(self) -> None:
        trace = self.report["normalized_trace"]
        self.assertTrue(trace["strip_exact_four_upload_spans_equals_control"])
        self.assertEqual(trace["removed_upload_span_count"], 4)
        self.assertEqual(
            [
                (row["controller"], row["command"], row["data_bytes"])
                for row in trace["removed_upload_spans"]
            ],
            [
                ("CS1", "0x20", 799),
                ("CS1", "0x21", 704),
                ("CS2", "0x20", 799),
                ("CS2", "0x21", 704),
            ],
        )
        stripped = [
            row
            for row in trace["treatment_events"]
            if not row.get("treatment_only_upload_span")
        ]
        self.assertEqual(stripped, trace["control_events"])
        self.assertEqual(
            trace["stripped_treatment_trace_sha256"],
            trace["control_trace_sha256"],
        )

    def test_transitive_dependencies_build_objects_and_toolchain_are_hashed(
        self,
    ) -> None:
        manifests = self.report["transitive_build_manifest"]
        self.assertGreaterEqual(
            manifests["treatment"]["transitive_dependency_count"], 200
        )
        self.assertGreaterEqual(
            manifests["control"]["transitive_dependency_count"], 200
        )
        for role in ("treatment", "control"):
            manifest = manifests[role]
            self.assertEqual(len(manifest["transitive_dependency_manifest_sha256"]), 64)
            self.assertEqual(len(manifest["build_input_manifest_sha256"]), 64)
            self.assertEqual(len(manifest["toolchain_manifest_sha256"]), 64)
            self.assertGreaterEqual(len(manifest["repo_local_dependencies"]), 6)
            self.assertFalse(manifest["dependency_contents_emitted"])
            self.assertFalse(manifest["map_or_object_contents_emitted"])
            self.assertTrue(
                any(
                    row["path_id"].endswith("epd_driver.cpp")
                    for row in manifest["repo_local_dependencies"]
                )
            )

    def test_causal_interpretation_is_bounded_and_never_live_authorizes(self) -> None:
        scope = self.report["scope"]
        self.assertTrue(scope["offline_read_only"])
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertFalse(scope["firmware_written_or_flashed"])
        self.assertFalse(scope["visible_refresh_requested"])
        causal = self.report["causal_scope"]
        self.assertFalse(causal["strict_payload_only_control"])
        self.assertFalse(causal["time_matched_control"])
        self.assertFalse(causal["dummy_or_empty_R20_R21_writes_in_control"])
        self.assertEqual(causal["treatment_only_SPI_bytes_per_controller"], 1_505)
        self.assertEqual(
            causal["treatment_only_selected_CS_transitions_per_controller"], 3_010
        )
        self.assertEqual(causal["treatment_only_source_yields_per_controller"], 5)
        self.assertEqual(
            causal["T_equals_C_classification"],
            "NO_DETECTABLE_INCREMENTAL_EFFECT",
        )
        self.assertFalse(causal["T_not_equal_C_proves_799_704_ABI"])
        self.assertFalse(causal["T_not_equal_C_distinguishes_R20_from_R21"])
        self.assertFalse(self.report["execution_eligible_after_this_audit_alone"])
        self.assertFalse(self.report["live_authorized"])

    def test_integrity_or_control_elf_mutation_fails_closed(self) -> None:
        changed = deepcopy(self.report)
        changed["causal_scope"]["time_matched_control"] = True
        with self.assertRaisesRegex(audit.MatchedTraceAuditError, "integrity"):
            audit.validate_seal(changed)

        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "control.elf"
            shutil.copyfile(CONTROL_ELF, copied)
            payload = bytearray(copied.read_bytes())
            payload[-1] ^= 0x01
            copied.write_bytes(payload)
            with self.assertRaisesRegex(
                audit.MatchedTraceAuditError, "control compiled identity"
            ):
                audit.audit_pair(
                    treatment_release_file=TREATMENT_RELEASE,
                    control_elf_file=copied,
                    control_binary_file=CONTROL_BIN,
                    control_transaction_source_file=CONTROL_SOURCE,
                )

    def test_cli_emits_metadata_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_ec5_h3_matched_trace_audit",
                "--treatment-release",
                str(TREATMENT_RELEASE),
                "--control-elf",
                str(CONTROL_ELF),
                "--control-binary",
                str(CONTROL_BIN),
                "--control-transaction-source",
                str(CONTROL_SOURCE),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertFalse(report["scope"]["raw_payload_or_disassembly_emitted"])
        self.assertNotIn('"raw_disassembly":', completed.stdout)
        self.assertNotIn("waveform_bytes", completed.stdout)


if __name__ == "__main__":
    unittest.main()
