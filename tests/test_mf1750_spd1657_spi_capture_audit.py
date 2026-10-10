from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_spd1657_spi_capture_audit as audit
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CAPTURE = b"fixture raw logic-analyzer container\x00\x01"
RAW_SHA256 = hashlib.sha256(RAW_CAPTURE).hexdigest()


def _transaction_payloads(
    profile_id: str, hypothesis_id: str
) -> list[tuple[tuple[str, ...], int, bytes]]:
    material = profile_pack.load_profile(profile_id)
    hypothesis = audit._hypotheses(profile_id)[hypothesis_id]
    frame = atlas.build_frame("atlas")
    cs1_dtm = atlas.controller_stream(frame, 0)
    cs2_dtm = atlas.controller_stream(frame, 1)
    both = ("CS1", "CS2")
    cs1 = ("CS1",)
    cs2 = ("CS2",)
    return [
        (both, 0xAA, bytes.fromhex("495520080918")),
        (both, 0x01, b"\x3f"),
        (both, 0x00, bytes.fromhex("5f69")),
        (both, 0x05, bytes.fromhex("401f1f2c")),
        (both, 0x08, bytes.fromhex("6f1f1f22")),
        (both, 0x06, bytes.fromhex("6f1f1717")),
        (both, 0x03, bytes.fromhex("00540044")),
        (both, 0x60, bytes.fromhex("0200")),
        (both, 0x30, b"\x08"),
        (both, 0x50, b"\x3f"),
        (both, 0x61, bytes.fromhex("02000258")),
        (both, 0xE3, b"\x2f"),
        (both, 0x84, b"\x01"),
        (cs1, 0xE0, b"\x01"),
        (cs2, 0xE0, b"\x01"),
        (both, 0x00, bytes.fromhex("5fe9")),
        (both, 0x01, material.power_payload),
        (both, 0x30, material.pll_payload),
        (both, 0x61, bytes.fromhex("02000258")),
        (cs1, 0xE9, b"\x01"),
        (cs1, 0x20, hypothesis.r20),
        (cs1, 0x21, hypothesis.r21),
        (cs2, 0xE9, b"\x01"),
        (cs2, 0x20, hypothesis.r20),
        (cs2, 0x21, hypothesis.r21),
        (cs1, 0x10, cs1_dtm),
        (cs2, 0x10, cs2_dtm),
        (both, 0x04, b""),
        (both, 0x06, bytes.fromhex("6f1f1749")),
        (both, 0x12, b"\x00"),
        (both, 0x02, b"\x00"),
        (both, 0x00, bytes.fromhex("4f6e")),
    ]


def _document_from_transactions(
    transactions: list[tuple[tuple[str, ...], int, bytes]],
) -> dict[str, object]:
    runs: list[dict[str, object]] = []
    frame_index = 0
    time_ns = 100

    def append(controllers: tuple[str, ...], dc_level: int, payload: bytes) -> None:
        nonlocal frame_index, time_ns
        count = len(payload)
        runs.append(
            {
                "controllers": list(controllers),
                "dc_level": dc_level,
                "end_ns": time_ns + max(1, count) * 8_000,
                "first_frame": frame_index,
                "last_frame": frame_index + count - 1,
                "mosi_hex": payload.hex(),
                "start_ns": time_ns,
            }
        )
        frame_index += count
        time_ns += max(1, count) * 8_000 + 1

    for controllers, command, payload in transactions:
        append(controllers, 0, bytes((command,)))
        if payload:
            append(controllers, 1, payload)
    return {
        "decoder_contract": {
            "bit_order": "MSB_FIRST",
            "clock_mode": 0,
            "cs_active_level": 0,
            "dc_command_level": 0,
            "dc_data_level": 1,
            "protocol": "SPI",
            "word_bits": 8,
        },
        "kind": audit.INPUT_KIND,
        "provenance": {
            "decoder_name": "test-byte-frame-normalizer",
            "decoder_version": "1.0",
            "raw_capture_bytes": len(RAW_CAPTURE),
            "raw_capture_sha256": RAW_SHA256,
        },
        "runs": runs,
        "schema_version": audit.SCHEMA_VERSION,
    }


def _audit_document(
    profile_id: str = "WF20_25",
    hypothesis_id: str = "H3_full_799_r20_ff_r21",
) -> tuple[dict[str, object], dict[str, object]]:
    document = _document_from_transactions(
        _transaction_payloads(profile_id, hypothesis_id)
    )
    report = audit.audit_capture_document(
        document,
        profile_id=profile_id,
        raw_capture_sha256=RAW_SHA256,
        raw_capture_bytes=len(RAW_CAPTURE),
    )
    return document, report


class Spd1657SpiCaptureAuditTests(unittest.TestCase):
    def test_h3_full_capture_passes_for_both_profiles(self) -> None:
        for profile_id in ("WF20_25", "WF23_25"):
            with self.subTest(profile_id=profile_id):
                _, report = _audit_document(profile_id)
                self.assertTrue(report["valid"])
                self.assertEqual(report["capture_geometry"]["transaction_count"], 32)
                self.assertEqual(
                    report["waveform_classification"]["hypothesis_id"],
                    "H3_full_799_r20_ff_r21",
                )
                self.assertTrue(
                    report["waveform_classification"][
                        "matches_frozen_empirical_h3_runtime_contract"
                    ]
                )
                self.assertTrue(
                    report["initialization_and_refresh"]["exact_full_success_sequence"]
                )
                self.assertFalse(
                    report["evidence_limits"]["controller_acceptance_proven"]
                )
                self.assertFalse(report["safety"]["hardware_accessed"])
                self.assertFalse(report["safety"]["raw_parameter_bytes_emitted"])

    def test_h1_and_h2_are_classified_without_being_promoted_to_h3(self) -> None:
        for hypothesis_id in (
            "H1_overlapping_eight_rows",
            "H2_extension_slots_5_to_7",
        ):
            with self.subTest(hypothesis_id=hypothesis_id):
                _, report = _audit_document("WF23_25", hypothesis_id)
                self.assertEqual(
                    report["waveform_classification"]["hypothesis_id"],
                    hypothesis_id,
                )
                self.assertFalse(
                    report["waveform_classification"][
                        "matches_frozen_empirical_h3_runtime_contract"
                    ]
                )

    def test_rejects_mixed_or_missing_secondary_controller_lut(self) -> None:
        transactions = _transaction_payloads("WF20_25", "H3_full_799_r20_ff_r21")
        h2 = audit._hypotheses("WF20_25")["H2_extension_slots_5_to_7"]
        mixed = list(transactions)
        mixed[24] = (("CS2",), 0x21, h2.r21)
        with self.assertRaisesRegex(
            audit.SpiCaptureAuditError, "CS1 and CS2 received different LUT"
        ):
            audit.audit_capture_document(
                _document_from_transactions(mixed),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

        missing = list(transactions)
        del missing[22:25]
        with self.assertRaises(audit.SpiCaptureAuditError):
            audit.audit_capture_document(
                _document_from_transactions(missing),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

    def test_rejects_swapped_order_truncation_and_extra_opcode(self) -> None:
        transactions = _transaction_payloads("WF20_25", "H3_full_799_r20_ff_r21")
        swapped = list(transactions)
        swapped[19:25] = swapped[22:25] + swapped[19:22]
        with self.assertRaises(audit.SpiCaptureAuditError):
            audit.audit_capture_document(
                _document_from_transactions(swapped),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

        truncated = list(transactions[:-1])
        with self.assertRaisesRegex(audit.SpiCaptureAuditError, "transaction count"):
            audit.audit_capture_document(
                _document_from_transactions(truncated),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

        extra = list(transactions) + [(("CS1",), 0x70, b"")]
        with self.assertRaisesRegex(audit.SpiCaptureAuditError, "transaction count"):
            audit.audit_capture_document(
                _document_from_transactions(extra),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

    def test_rejects_forbidden_otp_program_commands_before_count_check(self) -> None:
        transactions = _transaction_payloads("WF20_25", "H3_full_799_r20_ff_r21") + [
            (("CS1",), 0x90, b"\x00")
        ]
        with self.assertRaisesRegex(audit.SpiCaptureAuditError, "forbidden OTP"):
            audit.audit_capture_document(
                _document_from_transactions(transactions),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

    def test_rejects_dc_controller_frame_and_time_boundary_corruption(self) -> None:
        base, _ = _audit_document()
        mutations: list[tuple[str, dict[str, object]]] = []

        dc = deepcopy(base)
        dc["runs"][1]["dc_level"] = 0
        mutations.append(("command run", dc))

        controller = deepcopy(base)
        controller["runs"][1]["controllers"] = ["CS2"]
        mutations.append(("changes controller", controller))

        frame = deepcopy(base)
        frame["runs"][2]["first_frame"] += 1
        mutations.append(("not contiguous", frame))

        timing = deepcopy(base)
        timing["runs"][2]["start_ns"] = timing["runs"][1]["end_ns"]
        mutations.append(("timestamp", timing))

        for message, document in mutations:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(audit.SpiCaptureAuditError, message),
            ):
                audit.audit_capture_document(
                    document,
                    profile_id="WF20_25",
                    raw_capture_sha256=RAW_SHA256,
                    raw_capture_bytes=len(RAW_CAPTURE),
                )

    def test_rejects_altered_dtm_wrong_profile_and_raw_capture_mismatch(self) -> None:
        transactions = _transaction_payloads("WF20_25", "H3_full_799_r20_ff_r21")
        altered = list(transactions)
        target, command, payload = altered[25]
        altered[25] = (target, command, bytes((payload[0] ^ 1,)) + payload[1:])
        with self.assertRaisesRegex(audit.SpiCaptureAuditError, "atlas_dtm_cs1"):
            audit.audit_capture_document(
                _document_from_transactions(altered),
                profile_id="WF20_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

        document = _document_from_transactions(transactions)
        with self.assertRaises(audit.SpiCaptureAuditError):
            audit.audit_capture_document(
                document,
                profile_id="WF23_25",
                raw_capture_sha256=RAW_SHA256,
                raw_capture_bytes=len(RAW_CAPTURE),
            )
        with self.assertRaisesRegex(audit.SpiCaptureAuditError, "raw capture SHA"):
            audit.audit_capture_document(
                document,
                profile_id="WF20_25",
                raw_capture_sha256="0" * 64,
                raw_capture_bytes=len(RAW_CAPTURE),
            )

    def test_cli_binds_files_rejects_duplicate_keys_and_emits_metadata_only(
        self,
    ) -> None:
        document, _ = _audit_document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture_path = root / "decoded.json"
            raw_path = root / "capture.sal"
            capture_path.write_text(
                json.dumps(document, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            raw_path.write_bytes(RAW_CAPTURE)
            command = [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_spi_capture_audit",
                "--capture",
                str(capture_path),
                "--raw-capture",
                str(raw_path),
                "--profile",
                "WF20_25",
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertTrue(report["valid"])
            self.assertEqual(
                report["capture_identity"]["decoded_capture_sha256"],
                hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            )
            material = profile_pack.load_profile("WF20_25")
            self.assertNotIn(material.r20.hex(), completed.stdout)
            self.assertNotIn(material.plaintext.hex(), completed.stdout)

            duplicate_path = root / "duplicate.json"
            duplicate_path.write_text('{"kind":"a","kind":"b"}', encoding="utf-8")
            rejected = subprocess.run(
                [
                    *command[:4],
                    str(duplicate_path),
                    *command[5:],
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("duplicate JSON key", rejected.stdout)


if __name__ == "__main__":
    unittest.main()
