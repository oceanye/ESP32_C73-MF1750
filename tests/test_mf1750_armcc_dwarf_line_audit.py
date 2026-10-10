from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools import mf1750_armcc_dwarf_line_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CANONICAL_SHA256 = (
    "33de97f33fb0484ebbe9ced7298a4dd5e6829008001e342bde9d5b776b643574"
)
EXPECTED_FILE_SHA256 = (
    "1963084f1b69ab584093739b393c6c8849e67bc54892d5d5418154f39aead926"
)


def test_all_main_source_line_units_bind_exactly_once() -> None:
    report = audit.build_report()
    inventory = report["line_program_inventory"]
    assert inventory["all_structurally_valid_units"] == 31
    assert inventory["main_source_units"] == 24
    assert inventory["main_source_empty_units"] == 1
    assert inventory["main_source_function_units"] == 23
    assert inventory["all_function_units_uniquely_bound"] is True
    bindings = inventory["function_bindings"]
    assert len(bindings) == 23
    assert len({row["function"] for row in bindings}) == 23
    for row in bindings:
        assert row["function_bytes"] == row["line_unit"]["address_end"]
        assert 0 <= row["declaration_to_first_mapped_line_delta"] <= 5
        assert (
            row["dwarf_decl_line"] + row["declaration_to_first_mapped_line_delta"]
            == row["line_unit"]["first_row_source_line"]
        )
        assert (
            row["line_unit"]["minimum_source_line"]
            <= row["line_unit"]["maximum_source_line"]
        )
        assert row["line_unit"]["end_sequence_count"] >= 1
        assert row["line_unit"]["raw_line_program_or_source_text_emitted"] is False


def test_loadwf_call_coordinates_are_recovered_without_source_text_claim() -> None:
    report = audit.build_report()
    row = report["loadWF_source_coordinate_recovery"]
    assert row["line_unit_member_offset"] == 0x5C58
    assert row["function_bytes"] == 136
    assert row["declaration_line"] == 987
    assert row["first_row_mapped_line"] == 987
    assert row["final_row_mapped_line"] == 1020
    assert row["minimum_mapped_line"] == 987
    assert row["maximum_mapped_line"] == 1023
    assert row["end_sequence_address"] == 136
    assert row["four_writeEPD_calls_are_on_consecutive_source_lines_1001_to_1004"]
    calls = row["call_instruction_source_lines"]
    assert [
        (item["callee"], item["source_line_interval_assignment"]) for item in calls
    ] == [
        ("strlen", 990),
        ("test_decrypt_cbc_check_key", 990),
        ("writeEPD", 1001),
        ("writeEPD", 1002),
        ("writeEPD", 1003),
        ("writeEPD", 1004),
    ]
    assert row["source_line_gap_immediately_before_loadWF"] == [935, 986]
    assert row["gap_line_count"] == 52
    assert row["gap_contents_recovered"] is False


def test_adjudication_stays_bounded_to_active_mode0_coordinates() -> None:
    decision = audit.build_report()["adjudication"]
    assert decision["active_mode0_source_coordinates_recovered"] is True
    assert decision["original_source_text_recovered"] is False
    assert decision["preprocessor_inactive_source_recovered"] is False
    assert decision["source_gap_proves_mode1_branch"] is False
    assert decision["same_build_mode1_loader_recovered"] is False
    assert decision["H3_evidence_grade_changed"] is False


def test_report_is_metadata_only_deterministic_and_cli_reproducible(
    tmp_path: Path,
) -> None:
    report = audit.build_report()
    assert report["schema_version"] == 1
    assert report["integrity"]["canonical_sha256"] == EXPECTED_CANONICAL_SHA256
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        '"source_text"',
        '"raw_line_program"',
        '"key_bytes"',
        '"plaintext_bytes"',
        '"waveform_bytes"',
        '"payload_bytes"',
        '"authorization_token"',
    ):
        assert forbidden not in serialized

    output = tmp_path / "dwarf-line.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.mf1750_armcc_dwarf_line_audit",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_checked_in_report_and_safety_contract() -> None:
    path = (
        REPO_ROOT / ".test-output/offline/mf1750_armcc_dwarf_line_audit_20260812.json"
    )
    assert path.is_file()
    payload = path.read_bytes()
    report = audit.build_report()
    assert json.loads(payload.decode("utf-8")) == report
    assert payload.endswith(b"\n")
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_FILE_SHA256
    assert report["safety"] == {
        "offline_only": True,
        "hardware_accessed": False,
        "serial_or_COM8_accessed": False,
        "device_network_accessed": False,
        "firmware_or_flash_written": False,
        "display_refresh_attempted": False,
        "authorization_token_generated_or_claimed": False,
        "vendor_evidence_modified": False,
    }
