from __future__ import annotations

import hashlib
import inspect
import unittest

from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_ubrof11_e2_grammar_audit as audit
from tools import mf1750_iar_ubrof11_e2_projection_audit as projection


EXPECTED_CANONICAL_SHA256 = (
    "d265097c3215da0cad256b185e9f061534d702b3c298e32b2cfc451850aac565"
)


def _scoped_name_record(name: str, trailing_reference: int) -> bytes:
    encoded = name.encode("ascii")
    body = (
        b"\x01\x00\x00\x00"
        + bytes([len(encoded)])
        + encoded
        + trailing_reference.to_bytes(4, "big")
    )
    return b"\xcd\x00\x00\x00" + bytes([len(body)]) + body


class Mf1750IarUbrof11E2GrammarUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.object_dir = graph.DEFAULT_IAR_ROOT / graph.OBJECT_DIR_REL

    def test_complete_scoped_name_sequence_retains_interrupt_alias(self) -> None:
        payload = _scoped_name_record(
            "Timer0_A0_ISR", 0xFFFFFFFF
        ) + _scoped_name_record("??INTVEC 90", 0)
        names = audit.parse_namespace1_scoped_names(payload)
        self.assertEqual([row["index"] for row in names], [0, 1])
        self.assertEqual(
            [row["name"] for row in names], ["Timer0_A0_ISR", "??INTVEC 90"]
        )
        self.assertTrue(names[0]["is_unbound"])
        self.assertFalse(names[1]["is_unbound"])
        self.assertEqual(names[1]["trailing_reference"], 0)

    def test_interrupt_function_form_and_path_forms_decode(self) -> None:
        body = (
            b"\x01\x09interrupt"
            + (0).to_bytes(4, "big")
            + b"\x01\x02"
            + b"\x00\x04"
            + b"\x01\x06"
            + (1).to_bytes(4, "big")
            + b"\x00"
        )
        result = audit.parse_function_payload(body)
        self.assertEqual(result["root_categories"], ["interrupt"])
        self.assertEqual(result["caller_index"], 0)
        self.assertEqual(result["stack_vector_width"], 1)
        self.assertEqual([row["path_kind"] for row in result["paths"]], [0, 1])
        self.assertEqual(result["paths"][0]["stack_byte_vector"], [4])
        self.assertEqual(result["paths"][1]["callee_index"], 1)

    def test_function_parser_fails_closed_on_unobserved_variants(self) -> None:
        with self.assertRaisesRegex(audit.E2GrammarAuditError, "path kind 2"):
            audit.parse_function_payload(b"\x00\x00\x00\x00\x00\x01\x01\x02\x04")
        with self.assertRaisesRegex(audit.E2GrammarAuditError, "nonzero.*tail"):
            audit.parse_function_payload(
                b"\x00\x00\x00\x00\x00\x01\x01\x01\x04\x00\x00\x00\x00\x01"
            )
        with self.assertRaisesRegex(audit.E2GrammarAuditError, "trailing bytes"):
            audit.parse_stack_catalog_payload(b"\x02\x01\x06CSTACK\x00")

    def test_no_offset_scanner_rediscovers_exact_delivered_spans(self) -> None:
        selected_records = 0
        normal_functions = 0
        catalogs = 0
        for name, expected in projection.EXPECTED_OBJECTS.items():
            payload = (self.object_dir / name).read_bytes()
            scan = audit.scan_observed_e2_records(payload)
            spans = [
                (row["file_offset_int"], row["end_offset_int"])
                for row in scan["records"]
            ]
            expected_spans = [
                (offset, offset + length) for offset, length, _ in expected["spans"]
            ]
            self.assertEqual(spans, expected_spans)
            projected = audit._projection_bytes(payload, scan["records"])  # noqa: SLF001
            self.assertEqual(
                hashlib.sha256(projected).hexdigest(), expected["projection_sha256"]
            )
            selected_records += len(scan["records"])
            normal_functions += sum(
                row["record_class"] == "FUNCTION_NO_ROOT_CATEGORY"
                for row in scan["records"]
            )
            catalogs += sum(
                row["record_class"] == "STACK_CATALOG" for row in scan["records"]
            )
        self.assertEqual((selected_records, normal_functions, catalogs), (25, 22, 3))

    def test_scanner_implementation_has_no_delivered_offset_allowlist(self) -> None:
        source = inspect.getsource(audit.scan_observed_e2_records)
        self.assertNotIn("EXPECTED_OBJECTS", source)
        self.assertNotIn("spans", source)
        self.assertIn("for offset, value in enumerate", source)

    def test_module_contract_states_the_evidence_boundary(self) -> None:
        documentation = " ".join((audit.__doc__ or "").split())
        self.assertIn("not a native parse", documentation)
        self.assertIn("narrower than an official UBROF11 parser", documentation)
        self.assertIn("No hardware", documentation)


_XLIB = audit._discover_xlib()  # noqa: SLF001
_PUBLIC_CHECKOUTS = audit.discover_public_checkouts()


@unittest.skipUnless(
    _XLIB is not None and _PUBLIC_CHECKOUTS is not None,
    "identity-pinned XLIB and three local public checkouts are required",
)
class Mf1750IarUbrof11E2GrammarIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert _XLIB is not None
        assert _PUBLIC_CHECKOUTS is not None
        cls.report = audit.build_report(_XLIB, _PUBLIC_CHECKOUTS)

    def test_delivered_public_and_overall_grammar_counts_are_separate(self) -> None:
        coverage = self.report["coverage"]
        delivered = coverage["delivered"]
        public = coverage["public"]
        overall = coverage["overall"]
        self.assertEqual(
            (
                delivered["object_count"],
                delivered["function_no_root_category_count"],
                delivered["function_interrupt_root_count"],
                delivered["stack_catalog_count"],
                delivered["selected_record_count"],
            ),
            (3, 22, 0, 3, 25),
        )
        self.assertEqual(
            (
                public["object_count"],
                public["function_no_root_category_count"],
                public["function_interrupt_root_count"],
                public["stack_catalog_count"],
                public["selected_record_count"],
            ),
            (29, 76, 9, 29, 114),
        )
        self.assertEqual(
            (
                overall["object_count"],
                overall["function_no_root_category_count"],
                overall["function_interrupt_root_count"],
                overall["stack_catalog_count"],
                overall["selected_record_count"],
            ),
            (32, 98, 9, 32, 139),
        )
        self.assertEqual(overall["terminal_path_count"], 56)
        self.assertEqual(overall["direct_callee_path_count"], 126)
        self.assertEqual(overall["raw_E2_byte_count"], 227)
        self.assertEqual(overall["rejected_incidental_E2_count"], 88)
        self.assertEqual(
            overall["stack_byte_value_histogram"],
            {"0": 9, "2": 3, "4": 114, "6": 29, "8": 23, "10": 2, "12": 2},
        )

    def test_all_32_old_xlib_differentials_are_explicit(self) -> None:
        rows = list(self.report["delivered_objects"].values()) + list(
            self.report["public_corpus"]["objects"]
        )
        self.assertEqual(len(rows), 32)
        for row in rows:
            differential = row["official_XLIB_differential"]
            self.assertEqual(
                differential["unmodified_original"]["LIST_EXTERNALS_status"],
                "UNSUPPORTED_STACK_USAGE_TAG_E2",
            )
            self.assertEqual(
                differential["unmodified_original"]["LIST_ENTRIES_status"],
                "UNSUPPORTED_STACK_USAGE_TAG_E2",
            )
            self.assertEqual(
                differential["temporary_projection"]["LIST_EXTERNALS_status"],
                "PARSED",
            )
            self.assertEqual(
                differential["temporary_projection"]["LIST_ENTRIES_status"],
                "PARSED",
            )
        self.assertTrue(
            self.report["coverage"]["all_32_originals_reproduce_known_XLIB_E2_boundary"]
        )
        self.assertTrue(
            self.report["coverage"]["all_32_temporary_projections_parse_in_pinned_XLIB"]
        )

    def test_public_repositories_are_commit_blob_and_license_bounded(self) -> None:
        repos = self.report["public_corpus"]["repos"]
        self.assertEqual(set(repos), set(audit.PUBLIC_REPOS))
        self.assertEqual(
            self.report["public_corpus"]["corpus_manifest_sha256"],
            audit.EXPECTED_PUBLIC_CORPUS_MANIFEST_SHA256,
        )
        for slug, expected in audit.PUBLIC_REPOS.items():
            row = repos[slug]
            self.assertEqual(row["commit"], expected["commit"])
            self.assertEqual(
                row["object_manifest_sha256"], expected["object_manifest_sha256"]
            )
            self.assertEqual(row["object_count"], expected["expected_UBROF11_objects"])
            self.assertFalse(row["license_file_found_at_pinned_commit"])
            self.assertFalse(row["license_inferred"])
            for obj in row["objects"]:
                self.assertRegex(obj["git_blob_sha1"], r"^[0-9a-f]{40}$")
                self.assertRegex(obj["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(obj["path"].casefold().endswith(".r43"))
            if expected.get("anchor"):
                self.assertEqual(row["anchor"]["path"], expected["anchor"]["path"])
                self.assertEqual(
                    row["anchor"]["git_blob_sha1"],
                    expected["anchor"]["git_blob_sha1"],
                )
                self.assertEqual(row["anchor"]["sha256"], expected["anchor"]["sha256"])

    def test_interrupt_aliases_and_public_source_cross_check(self) -> None:
        aliases: list[str] = []
        for obj in self.report["public_corpus"]["objects"]:
            for record in obj["record_manifest"]:
                if record["record_class"] == "FUNCTION_INTERRUPT_ROOT":
                    aliases.extend(record["interrupt_vector_aliases"])
        self.assertEqual(len(aliases), 9)
        self.assertTrue(all(value.startswith("??INTVEC ") for value in aliases))
        source = self.report["public_corpus"]["source_cross_check"]
        self.assertTrue(source["sets_match"])
        self.assertEqual(
            source["E2_main_direct_callee_set"], ["DelayTenths", "led_tra"]
        )
        self.assertTrue(source["E2_led_tra_terminal_path_only"])

    def test_machine_graph_is_an_independent_set_check_not_a_count_equation(
        self,
    ) -> None:
        cross = self.report["delivered_machine_graph_cross_check"]
        self.assertEqual(cross["mapped_caller_sets_checked"], 14)
        self.assertEqual(cross["mapped_caller_set_mismatches"], 0)
        self.assertEqual(cross["object_callee_unions_checked"], 3)
        self.assertEqual(cross["object_callee_union_mismatches"], 0)
        self.assertTrue(cross["machine_CALLA_relocation_edges_are_not_E2_path_count"])

    def test_adjudication_does_not_promote_projection_or_observed_dialect(self) -> None:
        result = self.report["adjudication"]
        self.assertTrue(result["observed_exact_corpus_dialect_recovered"])
        self.assertFalse(result["official_general_UBROF11_E2_grammar_recovered"])
        self.assertFalse(result["fixed_or_newer_XLIB_native_original_parse_obtained"])
        self.assertFalse(
            result["unmodified_objects_natively_parsed_by_pinned_old_XLIB"]
        )
        self.assertFalse(result["projection_may_be_described_as_original_object_parse"])
        self.assertFalse(result["safe_link_flash_or_object_replacement_use"])
        self.assertTrue(
            self.report["coverage"]["projection_parse_is_not_native_original_parse"]
        )
        official = self.report["official_public_evidence"]
        self.assertFalse(
            official["XLINK_release_notes"]["byte_level_E2_grammar_published_there"]
        )
        self.assertFalse(
            official["MSP430_XLINK_manual_update"][
                "byte_level_E2_grammar_published_there"
            ]
        )

    def test_report_identity_metadata_and_hardware_inert_scope(self) -> None:
        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        self.assertEqual(integrity["canonical_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(audit._canonical_bytes(without_integrity)).hexdigest(),  # noqa: SLF001
        )
        scope = self.report["scope"]
        self.assertTrue(scope["pure_software"])
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertFalse(scope["firmware_written_or_flashed"])
        self.assertFalse(scope["visible_refresh_requested"])
        self.assertFalse(scope["original_objects_modified"])
        self.assertFalse(scope["persistent_projection_written"])
        self.assertFalse(scope["raw_object_bytes_emitted"])
        for row in list(self.report["delivered_objects"].values()) + list(
            self.report["public_corpus"]["objects"]
        ):
            self.assertNotIn("payload", row)
            self.assertNotIn("projection", row)
            self.assertNotIn("scan", row)


if __name__ == "__main__":
    unittest.main()
