from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from host.runtime_waveform import seed_perturbation as sp


CREATED_AT = "2026-09-02T01:14:00Z"


def test_default_audit_is_fail_closed_and_has_no_payload() -> None:
    report = sp.build_report(created_at=CREATED_AT)
    checked = sp.validate_report(report)
    assert report["decision"] == sp.DECISION_BLOCKED
    assert report["blocker_codes"] == [sp.DECISION_BLOCKED]
    assert report["candidate_count"] == 0
    assert report["candidate_metadata"] == []
    assert report["output_contract"]["candidate_payload_generated"] is False
    assert report["output_contract"]["candidate_payload_bytes"] == 0
    assert report["safety"]["offline_only"] is True
    assert checked["hardware_execution_eligible"] is False


def test_seed_inventory_is_six_controller_local_unqualified_candidates() -> None:
    seeds = sp.build_seed_inventory()
    assert len(seeds) == 6
    assert {(item["controller"], item["transport_code"]) for item in seeds} == {
        (controller, code) for controller in ("CS1", "CS2") for code in (0, 1, 6)
    }
    assert all(item["candidate_only"] is True for item in seeds)
    assert all(item["qualified"] is False for item in seeds)
    assert all(item["payload_bytes_emitted"] is False for item in seeds)
    assert sp.validate_seed_inventory(seeds) == seeds


def test_unproven_axis_never_enumerates_candidates() -> None:
    seeds = sp.build_seed_inventory()
    axis = {
        "axis_id": "frame-index",
        "axis_kind": "frame",
        "proof_artifact_sha256": "a" * 64,
        "semantics_proven": False,
        "safe_for_live": False,
        "unit": "index",
    }
    assert sp.enumerate_m1_metadata(seeds, axis=axis, values=(1, 2, 3)) == []


def test_unregistered_proven_axis_stays_blocked() -> None:
    axis = {
        "axis_id": "reviewed-time-axis",
        "axis_kind": "time",
        "proof_artifact_sha256": "b" * 64,
        "semantics_proven": True,
        "safe_for_live": True,
        "unit": "ms",
    }
    report = sp.build_report(created_at=CREATED_AT, axis=axis, values=(1, 2, 3))
    assert report["decision"] == sp.DECISION_BLOCKED
    assert report["candidate_count"] == 0
    assert report["candidate_metadata"] == []
    assert report["blocker_codes"] == [sp.DECISION_BLOCKED]
    assert report["output_contract"]["firmware_include_generated"] is False
    sp.validate_report(report)


def test_registered_proven_axis_only_creates_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    proof = "b" * 64
    monkeypatch.setattr(sp, "_REVIEWED_SAFE_AXIS_PROOF_SHA256", frozenset({proof}))
    axis = {
        "axis_id": "reviewed-time-axis",
        "axis_kind": "time",
        "proof_artifact_sha256": proof,
        "semantics_proven": True,
        "safe_for_live": True,
        "unit": "ms",
    }
    report = sp.build_report(created_at=CREATED_AT, axis=axis, values=(1, 2, 3))
    assert report["decision"] == sp.DECISION_METADATA_ONLY
    assert report["candidate_count"] == 18
    assert len(report["candidate_metadata"]) == 18
    assert all(item["payload_bytes_emitted"] is False for item in report["candidate_metadata"])
    assert all(item["live_eligible"] is False for item in report["candidate_metadata"])
    assert all(item["position_replicate_ids"] == ["P0", "P1", "P2", "P3"]
               for item in report["candidate_metadata"])
    sp.validate_report(report)


def test_axis_must_be_a_mapping() -> None:
    with pytest.raises(sp.SeedPerturbationError, match="axis keys"):
        sp.build_report(created_at=CREATED_AT, axis=["not", "an", "object"], values=())


def test_validator_rejects_recomputed_integrity_with_unsafe_candidate() -> None:
    report = sp.build_report(created_at=CREATED_AT)
    report["output_contract"]["firmware_include_generated"] = True
    report["integrity"]["canonical_sha256"] = sp.sha256_hex(
        sp.canonical_json_bytes({key: value for key, value in report.items()
                                 if key != "integrity"})
    )
    with pytest.raises(sp.SeedPerturbationError, match="output"):
        sp.validate_report(report)


def test_axis_requires_exactly_three_finite_values() -> None:
    axis = {
        "axis_id": "reviewed-time-axis",
        "axis_kind": "time",
        "proof_artifact_sha256": "c" * 64,
        "semantics_proven": True,
        "safe_for_live": True,
        "unit": "ms",
    }
    with pytest.raises(sp.SeedPerturbationError, match="exactly three"):
        sp.build_report(created_at=CREATED_AT, axis=axis, values=(1, 2))


def test_report_write_is_create_only(tmp_path: Path) -> None:
    report = sp.build_report(created_at=CREATED_AT)
    path = tmp_path / "audit.json"
    result = sp.write_report(path, report)
    assert result["decision"] == sp.DECISION_BLOCKED
    assert json.loads(path.read_text(encoding="utf-8"))["decision"] == sp.DECISION_BLOCKED
    with pytest.raises(sp.SeedPerturbationError, match="refusing to overwrite"):
        sp.write_report(path, report)


def test_cli_is_offline_and_emits_blocker(tmp_path: Path) -> None:
    output = tmp_path / "cli-audit.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/mf1750_seed_perturbation_audit.py",
            "--created-at",
            CREATED_AT,
            "--output",
            str(output),
            "--compact",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["decision"] == sp.DECISION_BLOCKED
    assert parsed["safety"]["device_network_accessed"] is False
    assert parsed["io_proof"] == {
        "device_io": False,
        "network_io": False,
        "serial_or_com_io": False,
        "visible_refreshes": 0,
    }
    assert output.exists()
