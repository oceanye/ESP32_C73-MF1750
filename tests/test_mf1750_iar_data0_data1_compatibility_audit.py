from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_iar_data0_data1_compatibility_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _official_tool(filename: str, environment_name: str) -> Path | None:
    configured = os.environ.get(environment_name)
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
            / filename
        )
    return next((path for path in candidates if path.is_file()), None)


AVAILABLE_XLINK = _official_tool("xlink.exe", "MF1750_IAR_XLINK_PATH")
AVAILABLE_XLIB = _official_tool("xlib.exe", "MF1750_IAR_XLIB_PATH")


class Mf1750IarDataContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = audit.build_content_comparison()

    def test_exact_799_plus_704_content_geometry_is_metadata_only(self) -> None:
        content = self.content["content"]
        first = content["DATA0_first_799"]
        self.assertEqual(first["bytes"], 799)
        self.assertEqual(
            first["sha256"],
            "9317dfc98fef531e0196b06ba2bce5d6bf9212a135b6fb677678949ac742338e",
        )
        self.assertEqual(first["boundary_equation"], "799 = 7 + 9*88")
        self.assertEqual(first["geometry"]["record_count"], 9)
        self.assertEqual(first["geometry"]["non_all_ff_record_indices"], list(range(6)))
        self.assertEqual(first["geometry"]["all_ff_record_indices"], [6, 7, 8])

        second = content["DATA0_last_704"]
        generated = content["runtime_generated_FF704"]
        self.assertEqual(second["bytes"], 704)
        self.assertEqual(second["sha256"], audit.FF_704_SHA256)
        self.assertTrue(second["all_ff"])
        self.assertEqual(second["geometry"]["record_count"], 8)
        self.assertEqual(second["geometry"]["all_ff_record_indices"], list(range(8)))
        self.assertEqual(second["sha256"], generated["sha256"])
        self.assertFalse(second["raw_bytes_emitted"])

    def test_data1_is_distinct_and_both_objects_retain_identical_arrays(self) -> None:
        identity = self.content["cross_object_content_identity"]
        self.assertFalse(identity["whole_object_bytes_equal"])
        self.assertTrue(identity["DATA0_bytes_equal"])
        self.assertTrue(identity["DATA1_bytes_equal"])

        data1 = self.content["content"]["DATA1_whole"]
        self.assertEqual(data1["bytes"], 704)
        self.assertEqual(
            data1["sha256"],
            "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
        )
        self.assertEqual(data1["geometry"]["non_all_ff_record_indices"], list(range(5)))
        self.assertEqual(data1["geometry"]["all_ff_record_indices"], [5, 6, 7])
        equalities = self.content["equality_matrix"]
        self.assertTrue(equalities["DATA0_last704_equals_runtime_generated_FF704"])
        self.assertFalse(equalities["DATA1_equals_runtime_generated_FF704"])


@unittest.skipUnless(
    AVAILABLE_XLINK is not None and AVAILABLE_XLIB is not None,
    "the identity-pinned official XLINK/XLIB pair is not available",
)
class Mf1750IarDataOfficialToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_XLIB is not None
        cls.report = audit.build_report(AVAILABLE_XLINK, AVAILABLE_XLIB)

    def test_official_tools_bind_arrays_and_find_no_natural_references(self) -> None:
        for name, expected_parts, expected_roots, expected_code in (
            ("E2801", 51, 48, 5_604),
            ("E2802", 50, 47, 6_228),
        ):
            evidence = self.report["object_tool_evidence"][name]
            identity = evidence["array_identity_link"]
            self.assertEqual(identity["segment_part_count"], expected_parts)
            self.assertEqual(identity["natural_reference_sites"], [])
            self.assertTrue(identity["only_ref_by_is_synthetic_force_root"])
            self.assertEqual(identity["bindings"]["DATA0"]["segment_part"], 20)
            self.assertEqual(identity["bindings"]["DATA0"]["span"]["bytes"], 1_503)
            self.assertEqual(identity["bindings"]["DATA1"]["segment_part"], 21)
            self.assertEqual(identity["bindings"]["DATA1"]["span"]["bytes"], 704)

            reachable = evidence["all_other_public_roots_link"]
            self.assertEqual(reachable["forced_public_root_count"], expected_roots)
            self.assertEqual(reachable["natural_reference_sites"], [])
            self.assertFalse(reachable["DATA0"]["needed"])
            self.assertFalse(reachable["DATA1"]["needed"])
            self.assertEqual(reachable["memory_summary"]["code_bytes"], expected_code)
            self.assertEqual(
                {
                    (row["segment"], row["segment_part"])
                    for row in reachable["not_needed_segment_parts"]
                },
                {("CSTACK", 7), ("DATA16_C", 20), ("DATA16_C", 21)},
            )

    def test_lineage_and_active_upload_classification_stay_bounded(self) -> None:
        lineage = self.report["producer_and_configuration_lineage"]
        self.assertTrue(lineage["same_compiler_version"])
        self.assertFalse(lineage["whole_objects_byte_identical"])
        self.assertFalse(lineage["module_dates_identical"])
        self.assertEqual(lineage["PUBLIC_set_difference_E2801_minus_E2802"], ["for_AX"])
        self.assertFalse(lineage["current_Debug_E2801_or_E2802_directly_linked"])
        for row in lineage["objects"].values():
            self.assertFalse(row["final_d43_direct_project_input"])

        adjudication = self.report["upload_source_adjudication"]
        self.assertTrue(
            adjudication["DATA0_last704_exactly_matches_active_generated_FF704"]
        )
        self.assertFalse(
            adjudication["DATA0_internal_799_symbol_or_subobject_boundary_declared"]
        )
        self.assertFalse(adjudication["DATA0_or_DATA1_used_by_active_upload"])
        boundaries = self.report["evidence_boundaries"]
        self.assertFalse(boundaries["category_phase_or_electrical_fields_proven"])
        self.assertFalse(boundaries["authorizes_live_hardware_action"])

    def test_report_identity_is_deterministic_and_metadata_only(self) -> None:
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "5d28d9d575f8b5da8c21b3fcdfbc08c1520c62b61852b214607c25a90bccf123",
        )
        serialized = json.dumps(self.report, sort_keys=True)
        for forbidden in (
            '"object_bytes"',
            '"lut_bytes"',
            '"waveform_bytes"',
            '"payload_bytes"',
            '"live_payload"',
        ):
            self.assertNotIn(forbidden, serialized.lower())
        scope = self.report["scope"]
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM8_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertEqual(scope["visible_refreshes"], 0)

    def test_cli_emits_the_same_non_authorizing_report(self) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_XLIB is not None
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_data0_data1_compatibility_audit",
                "--xlink",
                str(AVAILABLE_XLINK),
                "--xlib",
                str(AVAILABLE_XLIB),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertEqual(
            report["integrity"]["canonical_sha256"],
            self.report["integrity"]["canonical_sha256"],
        )
        self.assertFalse(report["evidence_boundaries"]["generates_live_payload"])


if __name__ == "__main__":
    unittest.main()
