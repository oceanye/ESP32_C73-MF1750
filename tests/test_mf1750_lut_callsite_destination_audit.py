from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

from tools import mf1750_lut_callsite_destination_audit as audit


def _available_xlink() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLINK_PATH")
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
            / "xlink.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


def _available_objdump() -> Path | None:
    configured = os.environ.get("MF1750_MSP430_OBJDUMP_PATH")
    candidates = [] if configured is None else [Path(configured)]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Temp"
            / "msp430-gcc-7.3.2.154-win64-extracted"
            / "msp430-gcc-7.3.2.154_win64"
            / "bin"
            / "msp430-elf-objdump.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


AVAILABLE_XLINK = _available_xlink()
AVAILABLE_OBJDUMP = _available_objdump()


class Mf1750LutCallsiteDestinationParserTests(unittest.TestCase):
    def test_comment_stripping_excludes_false_function_and_call_tokens(self) -> None:
        source = """
        // void writeEPD(void) { loadWF(fake); }
        /* loadWF(other); */
        void writeEPD(void) {
            sendSPICommand(0x20);
        }
        """
        clean = audit._strip_c_comments(source)
        self.assertNotIn("loadWF", clean)
        self.assertEqual(clean.count("writeEPD"), 1)
        self.assertIn("sendSPICommand(0x20)", audit._function_body(source, "writeEPD"))

    def test_function_body_balances_nested_braces(self) -> None:
        source = """
        unsigned char loadWF(unsigned char const *in) {
            if (*in) {
                while (*in) { ++in; }
            }
            return 0;
        }
        void next_function(void) { forbidden(); }
        """
        body = audit._function_body(source, "loadWF")
        self.assertIn("while (*in) { ++in; }", body)
        self.assertNotIn("forbidden", body)

    def test_unclosed_function_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            audit.LutCallsiteDestinationAuditError,
            "cannot bound function writeEPD",
        ):
            audit._function_body("void writeEPD(void) { if (1) { }", "writeEPD")


@unittest.skipUnless(
    AVAILABLE_XLINK is not None and AVAILABLE_OBJDUMP is not None,
    "the identity-pinned XLINK and MSP430 objdump are not both available",
)
class Mf1750LutCallsiteDestinationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_OBJDUMP is not None
        cls.report = audit.build_report(AVAILABLE_XLINK, AVAILABLE_OBJDUMP)

    def test_legacy_upload_provenance_and_fixed_destination_are_closed(self) -> None:
        legacy = self.report["legacy_IAR_active_upload_dataflow"]
        for name in ("E2801", "E2802"):
            obj = legacy["objects"][name]
            self.assertEqual(obj["matched_slot_read_bytes"], 2_508)
            self.assertEqual(obj["matched_slot_destination"], "dataBuff")
            self.assertEqual(obj["r20"]["source"], "dataBuff+4")
            self.assertEqual(obj["r20"]["bytes"], 799)
            self.assertEqual(obj["r21"]["source"], "generated 0xFF loop")
            self.assertEqual(obj["r21"]["bytes"], 704)

            linked = legacy["linked_transport_objects"][name]
            destination = linked["destination_binding"]
            self.assertEqual(destination["chip_select_register"], "P6OUT")
            self.assertEqual(destination["chip_select_register_address"], "0x0243")
            self.assertEqual(destination["chip_select_bit"], 3)
            self.assertEqual(destination["chip_select_polarity"], "active-low")
            self.assertFalse(destination["controller_or_chip_select_argument_consumed"])
            self.assertFalse(destination["distinct_second_CS_written"])
            self.assertFalse(destination["physical_controller_identity_proven"])

            self.assertEqual(
                linked["helpers"]["SPI_COMMAND"]["sha256"],
                "119fd295ccd68967e3496cb035e8ba611c5bc1df12b62113ae9cde3686867ada",
            )
            self.assertEqual(
                linked["helpers"]["SPI_DATA"]["sha256"],
                "9972945301c4117f5dfe4de36a4690a15db8a8d6999e92c523f6b2864f5ac546",
            )
            self.assertEqual(
                linked["root_only_link"]["intel_hex_sha256"],
                "c6a664d574b77bff3ddf7c814e86830895cf1f9f0a50acd4c60f41accc094928",
            )

        cross = legacy["cross_object"]
        self.assertTrue(cross["both_uploads_close_to_one_fixed_P6OUT_3_CS_path"])
        self.assertFalse(cross["distinct_master_and_slave_destinations_present"])
        self.assertFalse(cross["current_delivered_IAR_final_links_E2801_or_E2802"])

    def test_armcc_callsite_resolves_only_to_disconnected_single_cs_candidate(
        self,
    ) -> None:
        armcc = self.report["ArmCC_mode0_callsite_and_destination"]
        self.assertFalse(armcc["controller_or_chip_select_argument_present"])
        self.assertFalse(armcc["current_MAP_path_contains_loadWF"])
        self.assertFalse(armcc["dual_ToBoth_API_is_automatically_used_by_loadWF"])

        graph = armcc["source_and_link_graph"]
        self.assertEqual(graph["project_loadWF_C_call_sites"], [])
        self.assertEqual(graph["project_writeEPD_definitions"], ["Sample Code/E28xx.c"])
        self.assertFalse(graph["sample_main_is_project_entry"])
        self.assertFalse(
            graph["delivered_MAP_closure"][
                "source_resolution_candidate_is_linked_final_path"
            ]
        )
        self.assertTrue(graph["delivered_MAP_closure"]["all_seven_omit_loadWF"])
        self.assertTrue(graph["delivered_MAP_closure"]["all_seven_remove_writeEPD"])

        candidate = graph["retained_library_resolution_candidate"]
        self.assertEqual(
            candidate["source_graph_classification"],
            "SINGLE_PRIMARY_CS_CANDIDATE_ONLY",
        )
        self.assertEqual(candidate["terminal_primary_CS_macro"], "E_Paper_CS=PDout(8)")
        self.assertEqual(
            candidate["terminal_slave_CS_macro"], "E_Paper_SLAVE_CS=PDout(11)"
        )
        self.assertFalse(candidate["terminal_slave_CS_used_by_writeEPD_chain"])
        self.assertFalse(candidate["writeEPD_reads_spiChipSelect_global"])

    def test_wrapper_and_field_semantics_remain_unpromoted(self) -> None:
        gap = self.report["800_byte_wrapper_gap"]
        self.assertFalse(gap["same_generation_800_to_799_call_site_found"])
        self.assertFalse(
            gap["same_generation_800_to_dual_controller_destination_found"]
        )
        self.assertFalse(gap["legacy_799_call_site_accepts_current_wrapper_directly"])
        self.assertFalse(gap["current_ArmCC_loader_accepts_800_byte_wrapper"])

        semantics = self.report["field_semantics_boundary"]
        self.assertFalse(semantics["eleven_byte_parser_found_at_any_loader_callsite"])
        self.assertFalse(semantics["category_phase_or_voltage_semantics_promoted"])
        self.assertTrue(semantics["not_bound"]["candidate_800_category_labels"])
        self.assertTrue(semantics["not_bound"]["candidate_800_phase_order_or_duration"])
        self.assertTrue(
            semantics["not_bound"]["distinct_controller_specific_LUT_payloads"]
        )

    def test_report_is_metadata_only_and_canonical_hash_verifies(self) -> None:
        self.assertEqual(self.report["kind"], audit.KIND)
        self.assertEqual(self.report["schema_version"], audit.SCHEMA_VERSION)
        scope = self.report["scope"]
        self.assertTrue(scope["offline_read_only"])
        for key in (
            "hardware_accessed",
            "serial_or_COM_accessed",
            "device_network_accessed",
            "firmware_written_or_flashed",
            "reset_or_refresh_requested",
            "raw_object_code_or_disassembly_emitted",
            "raw_waveform_or_payload_emitted",
        ):
            self.assertFalse(scope[key], key)

        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        observed = hashlib.sha256(
            json.dumps(
                without_integrity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(observed, integrity["canonical_sha256"])
        self.assertFalse(self.report["adjudication"]["authorizes_live_hardware_action"])


if __name__ == "__main__":
    unittest.main()
