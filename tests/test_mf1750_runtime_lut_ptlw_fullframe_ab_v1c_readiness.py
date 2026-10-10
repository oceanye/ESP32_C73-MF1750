from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1c_readiness as v1c


ROOT = Path(__file__).resolve().parents[1]
SALVAGE = (
    ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_20260825_V1B_FRESH2"
    / "action-01-salvage.json"
)
SUCCESS = (
    ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_20260825_V1"
    / "action-01-white-health.json"
)


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _assert_integrity(value: dict[str, object]) -> None:
    integrity = value["integrity"]
    assert isinstance(integrity, dict)
    body = dict(value)
    del body["integrity"]
    assert integrity["sha256"] == hashlib.sha256(_canonical(body)).hexdigest()


def test_describe_is_offline_and_disables_visible_v1c() -> None:
    value = v1c.describe()
    assert value["mode"] == "DIAGNOSTIC_ONLY"
    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["network_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False
    assert value["proof_boundary"] == {
        "reliable_no_pon_gate_identified": False,
        "raw_busy_proves_pon_completion": False,
        "reset_idle_proves_pon_completion": False,
        "stable_revision_reads_prove_pon_completion": False,
        "pon_completion_requires_observing_pon_busy_then_idle": True,
        "visible_action_may_be_consumed_after_no_pon_gate": False,
    }
    assert value["v1c_decision"]["visible_action_runner_enabled"] is False
    _assert_integrity(value)


def test_even_strongest_reset_revision_observation_cannot_qualify_pon() -> None:
    result = v1c.assess_no_pon_observables(
        raw_busy_idle_high=True,
        reset_idle_completed=True,
        cs1_revision_stable=True,
        cs2_revision_stable=True,
    )
    assert result["digital_reset_spi_path_observed"] is True
    assert result["pon_command_sent"] is False
    assert result["pon_completion_qualified"] is False
    assert result["visible_action_allowed"] is False


def test_actual_v1b_salvage_is_reset_only_counterexample() -> None:
    value = v1c.audit_fault(SALVAGE, successful_reference_file=SUCCESS)
    fault = value["v1b_fault"]
    expected_fault = {
        "ordinal": 1,
        "driver_calls": 1,
        "reset_and_precommand_idle_completed": True,
        "pon_busy_asserted": True,
        "pon_idle_completed": False,
        "pon_wait_ms": 60010,
        "drf_reached": False,
        "safe_finish_busy_high_and_panel_outputs_low": True,
        "counterexample": "reset/precommand-idle success did not imply PON completion",
    }
    for key, expected in expected_fault.items():
        assert fault[key] == expected
    assert fault["embedded_integrity"] == {
        "algorithm": "sha256-canonical-json-without-integrity",
        "embedded_sha256": "99ca7fa0739b6e4f2bea0379bc404c43cf79788fbdd94d6dbba4e4bb925e3fc9",
        "recomputed_sha256": "99ca7fa0739b6e4f2bea0379bc404c43cf79788fbdd94d6dbba4e4bb925e3fc9",
        "valid": True,
    }
    assert fault["identity_binding"] == {
        **v1c.V1B_BINDING,
        "action": v1c.SHARED_ACTION_BINDING,
        "exact": True,
    }
    assert fault["driver_path"] == v1c.EXPECTED_DRIVER_PATH
    assert value["successful_reference"]["pon_wait_ms"] == 180
    assert value["successful_reference"]["embedded_integrity"]["valid"] is True
    assert value["successful_reference"]["identity_binding"] == {
        **v1c.V1_BINDING,
        "action": v1c.SHARED_ACTION_BINDING,
        "exact": True,
    }
    comparison = value["driver_path_comparison"]
    assert comparison["v1_success"] == v1c.EXPECTED_DRIVER_PATH
    assert comparison["v1b_pon_timeout"] == v1c.EXPECTED_DRIVER_PATH
    assert all(comparison["field_equality"].values())
    assert comparison["all_payload_fnv_upload_timing_and_spi_equal"] is True
    source_binding = value["original_v1_source_binding"]
    assert source_binding["all_driver_white_shared_sources_match"] is True
    assert tuple(source_binding["sources"]) == v1c.SOURCE_BINDING_PATHS
    assert all(item["match"] for item in source_binding["sources"].values())
    assert value["proof_boundary"]["v1b_is_counterexample_to_reset_only_qualification"] is True
    assert value["proof_boundary"]["visible_action_allowed"] is False
    assert value["proof_boundary"]["driver_source_and_payload_path_delta_identified"] is False
    assert value["proof_boundary"]["transient_or_physical_state_proven"] is False
    assert value["v1c_decision"]["do_not_retry_v1b_ordinal_1"] is True
    _assert_integrity(value)


def _rewrite_integrity(value: dict[str, object]) -> None:
    unsigned = dict(value)
    del unsigned["integrity"]
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(unsigned)).hexdigest(),
    }


def test_tampered_salvage_fails_embedded_integrity_before_semantics(
    tmp_path: Path,
) -> None:
    salvage = json.loads(SALVAGE.read_text(encoding="utf-8"))
    salvage["terminal_report"]["driver"]["pon_ms"] = 60_011
    tampered = tmp_path / "tampered-salvage.json"
    tampered.write_text(json.dumps(salvage), encoding="utf-8")
    with pytest.raises(v1c.V1CReadinessError, match="canonical integrity mismatch"):
        v1c.audit_fault(tampered, successful_reference_file=SUCCESS)


def test_resealed_wrong_success_identity_fails_exact_binding(tmp_path: Path) -> None:
    success = json.loads(SUCCESS.read_text(encoding="utf-8"))
    success["firmware_sha256"] = "0" * 64
    _rewrite_integrity(success)
    tampered = tmp_path / "wrong-success.json"
    tampered.write_text(json.dumps(success), encoding="utf-8")
    with pytest.raises(v1c.V1CReadinessError, match="firmware SHA-256 differs"):
        v1c.audit_fault(SALVAGE, successful_reference_file=tampered)


def test_source_ordering_explains_why_action_was_consumed_first() -> None:
    audit = v1c.describe()["source_audit"]
    assert audit["durable_action_consumed_before_driver_call"] is True
    assert audit["driver_reset_precedes_reset_idle_wait"] is True
    assert audit["precommand_idle_precedes_pon"] is True
    assert audit["pon_busy_then_idle_wait_follows_pon"] is True


def test_module_has_no_device_network_or_relay_imports() -> None:
    source = (
        ROOT
        / "tools"
        / "mf1750_runtime_lut_ptlw_fullframe_ab_v1c_readiness.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "import requests",
        "import serial",
        "urllib.request",
        "mf17506_stage23.relay",
        "exec_command",
    ):
        assert forbidden not in source


def test_cli_writes_sealed_local_audit_without_repo_cwd(tmp_path: Path) -> None:
    output = tmp_path / "v1c-readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.mf1750_runtime_lut_ptlw_fullframe_ab_v1c_readiness",
            "audit-fault",
            "--salvage",
            str(SALVAGE),
            "--successful-reference",
            str(SUCCESS),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = json.loads(completed.stdout)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert stdout == written
    assert written["mode"] == "DIAGNOSTIC_ONLY"
    assert written["proof_boundary"]["visible_action_allowed"] is False
    _assert_integrity(written)
