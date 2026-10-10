from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_ubrof11_e2_projection_audit as audit


EXPECTED_CANONICAL_SHA256 = (
    "15647b3c522d298ff8e2fa2782835c0d7b97577fdf02bed5b4cec9fed726683c"
)


def _available_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        / "Temp/iar_ew430_6201_xlink_only/component_430_xlink_common/430/bin/xlib.exe"
    )
    for path in candidates:
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if (
            len(payload) == 550_912
            and hashlib.sha256(payload).hexdigest()
            == "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284"
        ):
            return path.resolve()
    return None


class Mf1750IarUbrof11E2ProjectionUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.object_dir = graph.DEFAULT_IAR_ROOT / graph.OBJECT_DIR_REL

    def test_comparative_crc_matches_all_29_pinned_objects(self) -> None:
        result = audit.validate_all_delivered_crcs(graph.DEFAULT_IAR_ROOT)
        self.assertEqual(result["objects_checked"], 29)
        self.assertEqual(result["objects_matching"], 29)
        self.assertTrue(result["all_29_match"])
        self.assertEqual(len(result["crc_manifest_sha256"]), 64)

    def test_exact_projection_identities_and_record_totals(self) -> None:
        total_records = 0
        total_function_records = 0
        total_elided = 0
        for name, expected in audit.EXPECTED_OBJECTS.items():
            original = (self.object_dir / name).read_bytes()
            projected, metadata = audit.project_exact_object(name, original)
            self.assertEqual(original[1], 11)
            self.assertEqual(projected[1], 11)
            self.assertEqual(len(original), expected["size_bytes"])
            self.assertEqual(len(projected), expected["projection_size_bytes"])
            self.assertEqual(
                hashlib.sha256(projected).hexdigest(),
                expected["projection_sha256"],
            )
            self.assertEqual(metadata["projection_crc"], expected["projection_crc"])
            self.assertEqual(
                projected.count(0xE2), expected["false_e2_bytes_remaining"]
            )
            self.assertTrue(metadata["original_UBROF_version_retained"])
            self.assertFalse(metadata["original_object_modified"])
            total_records += metadata["selected_record_count"]
            total_function_records += metadata[
                "inferred_function_associated_record_count"
            ]
            total_elided += metadata["bytes_elided"]

        self.assertEqual(total_records, 25)
        self.assertEqual(total_function_records, 22)
        self.assertEqual(total_elided, 592)

    def test_function_e2_name_references_resolve_to_expected_landmarks(self) -> None:
        rows: dict[str, list[str]] = {}
        for name in audit.EXPECTED_OBJECTS:
            payload = (self.object_dir / name).read_bytes()
            _, metadata = audit.project_exact_object(name, payload)
            rows[name] = metadata["referenced_function_names"]

        self.assertEqual(rows["DELAY.r43"], ["delay"])
        self.assertIn("EPD_Init", rows["E6_73.r43"])
        self.assertIn("EPD_Display_Blue", rows["E6_73.r43"])
        self.assertEqual(
            rows["main.r43"],
            ["SetVcoreUp", "SetClockSystem_25MHz", "main"],
        )

    def test_projection_fails_closed_on_any_identity_change(self) -> None:
        name = "DELAY.r43"
        original = bytearray((self.object_dir / name).read_bytes())
        original[0x6A8] ^= 1
        with self.assertRaisesRegex(audit.E2ProjectionAuditError, "identity changed"):
            audit.project_exact_object(name, bytes(original))

    def test_crc_validation_rejects_corruption(self) -> None:
        original = bytearray((self.object_dir / "DELAY.r43").read_bytes())
        original[100] ^= 1
        with self.assertRaisesRegex(audit.E2ProjectionAuditError, "CRC mismatch"):
            audit._validate_crc(bytes(original), "fixture")  # noqa: SLF001

    def test_report_contract_does_not_promote_projection_to_native_parse(self) -> None:
        self.assertIn("E2", audit.__doc__ or "")
        self.assertIn("not a native parse", audit.__doc__ or "")
        self.assertIn("bounded search", audit.__doc__ or "")
        self.assertIn("does not claim", audit.__doc__ or "")
        self.assertEqual(
            audit.MSPGCC_RCS_MEMBER_IDENTITY["extracted_revision_sha256"],
            "0a9466c28aac12030f8e4152becc0225593f2838de302bc7aac95a4bd98d4cb2",
        )


@unittest.skipUnless(
    _available_xlib() is not None,
    "identity-pinned official XLIB 6.1.3.56 is not locally available",
)
class Mf1750IarUbrof11E2ProjectionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_xlib()
        assert cls.xlib is not None
        cls.report = audit.build_report(cls.xlib, graph.DEFAULT_IAR_ROOT)

    def test_originals_fail_and_projections_parse(self) -> None:
        expected_counts = {
            "DELAY.r43": (4, 3),
            "E6_73.r43": (5, 25),
            "main.r43": (13, 26),
        }
        for name, (external_count, entry_count) in expected_counts.items():
            row = self.report["objects"][name]
            self.assertEqual(
                row["original_official_XLIB"]["LIST_EXTERNALS_status"],
                "UNSUPPORTED_STACK_USAGE_TAG_E2",
            )
            self.assertEqual(
                row["original_official_XLIB"]["LIST_ENTRIES_status"],
                "UNSUPPORTED_STACK_USAGE_TAG_E2",
            )
            projected = row["official_XLIB_on_projection"]
            self.assertEqual(projected["external_count"], external_count)
            self.assertEqual(projected["entry_count"], entry_count)

    def test_all_52_external_index_calls_match(self) -> None:
        cross = self.report["external_index_cross_check"]
        self.assertEqual(cross["paired_external_index_calls_checked"], 52)
        self.assertEqual(cross["mismatch_count"], 0)
        self.assertTrue(cross["zero_mismatch"])
        main_table = self.report["objects"]["main.r43"]["official_XLIB_on_projection"][
            "external_index_table"
        ]
        self.assertEqual(main_table[2], {"external_index": 2, "symbol": "EPD_Init"})
        self.assertEqual(
            main_table[8], {"external_index": 8, "symbol": "EPD_Display_Green"}
        )

    def test_entry_landmarks_and_evidence_boundary(self) -> None:
        e6_entries = self.report["objects"]["E6_73.r43"]["official_XLIB_on_projection"][
            "entry_table"
        ]
        main_entries = self.report["objects"]["main.r43"][
            "official_XLIB_on_projection"
        ]["entry_table"]
        self.assertIn("EPD_Init", e6_entries)
        self.assertIn("EPD_Display_Blue", e6_entries)
        self.assertIn("main", main_entries)
        adjudication = self.report["adjudication"]
        self.assertTrue(adjudication["projected_symbol_tables_recovered"])
        self.assertFalse(adjudication["unmodified_objects_natively_parsed"])
        self.assertTrue(
            adjudication["projection_metadata_usable_only_with_evidence_label"]
        )
        self.assertFalse(adjudication["native_original_metadata_claim_allowed"])
        self.assertFalse(adjudication["safe_link_flash_or_object_replacement_use"])

    def test_report_is_deterministic_and_hardware_inert(self) -> None:
        second = audit.build_report(self.xlib, graph.DEFAULT_IAR_ROOT)
        self.assertEqual(self.report, second)
        self.assertEqual(self.report["schema_version"], 2)
        method = self.report["projection_method"]
        self.assertFalse(
            method["official_record_level_E2_grammar_found_in_cited_sources"]
        )
        self.assertFalse(method["global_official_E2_grammar_absence_claimed"])
        self.assertIn(
            "global absence is not claimed",
            self.report["remaining_boundary"]["official_E2_grammar_search_scope"],
        )
        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        self.assertEqual(integrity["canonical_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(audit._canonical_bytes(without_integrity)).hexdigest(),  # noqa: SLF001
        )
        scope = self.report["scope"]
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertFalse(scope["firmware_written_or_flashed"])
        self.assertFalse(scope["visible_refresh_requested"])
        self.assertFalse(scope["original_objects_modified"])

    def test_compact_output_is_valid_metadata_only_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            payload = audit._canonical_bytes(self.report) + b"\n"  # noqa: SLF001
            path.write_bytes(payload)
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["kind"], audit.KIND)
        self.assertFalse(loaded["scope"]["raw_object_bytes_emitted"])
        self.assertFalse(loaded["scope"]["raw_waveform_or_LUT_bytes_emitted"])
        self.assertFalse(loaded["scope"]["raw_disassembly_emitted"])


if __name__ == "__main__":
    unittest.main()
