from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_once as once
from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_pack as pack


def test_dry_validate_binds_artifacts_without_network() -> None:
    value = once.host.dry_validate()
    assert value["verified"] is True
    assert value["network"] == {"get": 0, "post": 0}
    assert value["hardware_accessed"] is False
    assert value["contract_id"] == pack.CONTRACT_ID
    assert value["descriptor_ids"] == list(pack.DESCRIPTOR_IDS)
    assert value["action_ids"] == list(pack.ACTION_IDS)
    assert all(
        item["verified"] is True for item in value["artifact_binding_status"].values()
    )


def test_describe_exposes_true_tuple_switch_and_live_block() -> None:
    value = once.describe()
    assert value["action_order"] == list(pack.ROLES)
    transport = value["fixed_transport"]
    assert transport["runtime_lut_partial_ordinals"] == [1, 2, 3]
    assert transport["candidate_codes"] == [0, 0, 2]
    assert transport["candidate_codes_are_not_colour_names"] is True
    assert transport["complete_tuple_sequence"] == [
        "active",
        "commented",
        "active",
    ]
    assert transport["both_controllers_receive_same_tuple_per_action"] is True
    assert transport["historical_global_header_only_cross_lut"] is False
    assert value["batch1_evidence_gate"]["required"] is True
    assert value["batch1_evidence_gate"]["batch1_contract_frozen"] is True
    assert value["live_authorized"] is False


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    [
        (1, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (2, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (3, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (4, {"dtm_bytes": 307_200, "lut_bytes": 0, "ptlw_writes": 0}),
    ],
)
def test_action_stage_counts_are_exact(ordinal: int, expected: dict[str, int]) -> None:
    value = once._expected_action_stage_counts(ordinal)  # noqa: SLF001
    for key, wanted in expected.items():
        assert value[key] == wanted
    assert value["pon"] == value["drf"] == value["pof"] == 1
    assert value["command_0x86"] == 0
    assert value["visible_refresh_requests"] == 1


def test_run_without_batch1_evidence_fails_before_request_or_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched = False

    def forbidden_request(*_args: object, **_kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(once.base.runner, "_request", forbidden_request)
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.base.runner.RecheckError, match="Batch-1"):
        once.run_once(
            "http://192.0.2.1",
            1,
            batch1_evidence=None,
            claims=claims,
            output=output,
            confirm_j2_on=True,
        )
    assert touched is False
    assert not claims.exists()
    assert not output.exists()


def test_unsealed_batch1_evidence_blocks_before_network_or_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched = False

    def forbidden_request(*_args: object, **_kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(once.base.runner, "_request", forbidden_request)
    evidence = tmp_path / "batch1.json"
    evidence.write_text("{}", encoding="utf-8")
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.base.runner.RecheckError, match="canonical seal"):
        once.run_once(
            "http://192.0.2.1",
            1,
            batch1_evidence=evidence,
            claims=claims,
            output=output,
            confirm_j2_on=True,
        )
    assert touched is False
    assert not claims.exists()
    assert not output.exists()


def test_missing_or_invalid_batch2_blocks_before_network_or_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched = False

    def forbidden_request(*_args: object, **_kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(once.base.runner, "_request", forbidden_request)
    monkeypatch.setattr(
        once,
        "_load_batch1_evidence",
        lambda _path: ({}, "1" * 64),
    )
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.base.runner.RecheckError, match="Batch-2"):
        once.run_once(
            "http://192.0.2.1",
            1,
            batch1_evidence=tmp_path / "batch1.json",
            batch2_evidence=None,
            claims=claims,
            output=output,
            confirm_j2_on=True,
        )
    assert touched is False
    assert not claims.exists()
    assert not output.exists()

    def invalid_batch2(_path: Path) -> object:
        raise once.base.runner.RecheckError("Batch-2 terminal white differs")

    monkeypatch.setattr(once, "_load_batch2_evidence", invalid_batch2)
    with pytest.raises(once.base.runner.RecheckError, match="Batch-2"):
        once.run_once(
            "http://192.0.2.1",
            1,
            batch1_evidence=tmp_path / "batch1.json",
            batch2_evidence=tmp_path / "batch2.json",
            claims=claims,
            output=output,
            confirm_j2_on=True,
        )
    assert touched is False
    assert not claims.exists()
    assert not output.exists()


def test_sealed_batch1_bundle_binds_all_four_outputs_and_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = {
        "schema_version": 1,
        "kind": once.BATCH1_EVIDENCE_KIND,
        "campaign_id": once.BATCH1_CAMPAIGN_ID,
        "contract_schema": once.BATCH1_CONTRACT_SCHEMA,
        "contract_id": once.BATCH1_CONTRACT_ID,
        "action_ids": list(once.BATCH1_ACTION_IDS),
        "active_global_tuple_id": once.BATCH1_ACTIVE_GLOBAL_TUPLE_ID,
        "commented_global_tuple_id": once.BATCH1_COMMENTED_GLOBAL_TUPLE_ID,
        "outcome": "PASS",
        "active_same_r20_both_controllers": True,
        "commented_same_r20_both_controllers": True,
        "aa_left_right_parity_pass": True,
        "cc_left_right_parity_pass": True,
        "terminal_factory_white_clean_pass": True,
        "candidate_transport_codes_authorized": [0, 0, 2],
        "candidate_codes_are_not_colour_names": True,
        "terminal_factory_white_is_latest_bound_batch1_capture": True,
        "clean_white_visual_outcomes": {
            "ordinal_2": "PASS",
            "ordinal_4": "PASS",
        },
        "automatic_analysis": {
            "active_same_side": "PASS",
            "active_cross_side": "PASS",
            "commented_same_side": "PASS",
            "commented_cross_side": "PASS",
        },
        "action_results": [
            {
                "ordinal": ordinal,
                "action_id": action_id,
                "output_name": output_name,
                "output_sha256": f"{ordinal:064x}",
                "outcome": "complete_pass",
            }
            for ordinal, (action_id, output_name) in enumerate(
                zip(
                    once.BATCH1_ACTION_IDS,
                    once.BATCH1_ACTION_OUTPUTS,
                    strict=True,
                ),
                1,
            )
        ],
    }
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
    }
    camera_signature = {
        "camera_id": "camera-1",
        "instance_id": "instance-1",
        "index": 0,
        "backend": "DSHOW",
        "mount_id": "mount-1",
        "requested_settings": settings,
        "effective_settings": settings,
    }
    value["capture_evidence_complete"] = True
    value["repeat_noise_evidence_complete"] = True
    value["repeat_noise_baseline"] = {
        "path": "repeat-noise.json",
        "file_sha256": "5" * 64,
        "canonical_integrity_sha256": "6" * 64,
        "baseline_id": "7" * 64,
        "reference_geometry_sha256": "8" * 64,
        "capture_count": 3,
        "repeat_noise_p95_de76": 1.0,
        "camera_signature": camera_signature,
    }
    value["camera_lock"] = {
        **camera_signature,
        "photo_width": 1920,
        "photo_height": 1080,
        "boot_nonce": "batch1-boot",
        "manual_controls_required": {
            "autofocus": 0.0,
            "auto_exposure": 0.25,
            "auto_white_balance": 0.0,
        },
        "same_signature_all_four_captures": True,
        "strictly_increasing_capture_times": True,
    }
    photo_hashes = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
    value["capture_bindings"] = [
        {
            "ordinal": ordinal,
            "path": f"capture-{ordinal}.json",
            "sidecar_file_sha256": f"{ordinal + 10:064x}",
            "canonical_integrity_sha256": f"{ordinal + 20:064x}",
            "capture_id": f"{ordinal + 30:064x}",
            "captured_at": f"2026-08-28T10:0{ordinal}:00+08:00",
            "action_id": action_id,
            "descriptor_id": f"{ordinal + 40:064x}",
            "action_result_sha256": f"{ordinal:064x}",
            "photo_sha256": photo_hashes[ordinal - 1],
            "capture_binding": "live_synchronized",
            "coverage_scope": "full_panel",
        }
        for ordinal, action_id in enumerate(once.BATCH1_ACTION_IDS, 1)
    ]
    value["analysis_bindings"] = {
        name: {
            "path": f"{name}.json",
            "file_sha256": f"{index + 50:064x}",
            "canonical_integrity_sha256": f"{index + 60:064x}",
            "source_photo_sha256": photo_hashes[index],
            "reference_geometry_sha256": "8" * 64,
            "repeat_noise_p95_de76": 1.0,
            **(
                {"interpretation": "panel geometry and eight paired codes passed"}
                if name in {"aa_atlas", "cc_atlas"}
                else {}
            ),
        }
        for index, name in enumerate(
            ("aa_atlas", "white_after_aa", "cc_atlas", "white_after_cc")
        )
    }
    value["aa_cc_comparison"] = {
        "path": "aa-cc-comparison.json",
        "file_sha256": "9" * 64,
        "canonical_integrity_sha256": "a" * 64,
        "comparison_id": "b" * 64,
        "classification_state": "NO_RESOLVED_AA_TO_CC_EFFECT",
        "classification_counts": {
            "R20_LINKED_EXPLORATORY_EFFECT": 0,
            "NO_RESOLVED_EFFECT": 8,
            "CONTROLLER_INCONSISTENT": 0,
        },
        "absolute_colour_proven": False,
        "qualified_new_colour": False,
    }
    value["evidence_boundaries"] = {
        "camera_relative_de76_not_calibrated_de00": True,
        "compiled_payload_identity_not_bus_capture": True,
        "every_analysis_photo_bound_to_live_synchronized_action_capture": True,
        "full_panel_camera_coverage_required": True,
        "manual_camera_controls_and_mount_locked_across_batch": True,
        "analysis_threshold_bound_to_sealed_repeat_noise_report": True,
        "aa_cc_comparison_is_exploratory_not_causal": True,
        "external_refresh_after_last_bound_capture_not_proven": True,
        "candidate_codes_are_transport_codes_only": True,
        "no_absolute_colour_or_new_colour_claim": True,
        "device_io_performed_by_bundle_builder": False,
    }
    value["output_write_contract"] = "O_EXCL"
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(once.base.runner._canonical(value)).hexdigest(),
    }
    path = tmp_path / "batch1-bundle.json"
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    observed, file_sha256 = once._load_batch1_evidence(path)  # noqa: SLF001
    assert observed["contract_id"] == once.BATCH1_CONTRACT_ID
    assert len(observed["action_results"]) == 4
    assert file_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()

    batch2_path = tmp_path / "batch2-bundle.json"
    batch2_binding = {
        "input_file": str(batch2_path.resolve()),
        "file_sha256": "c" * 64,
        "canonical_integrity_sha256": "d" * 64,
        "bundle_id": "e" * 64,
        "campaign_identity": {"campaign_boot_nonce": "batch2-boot"},
        "terminal_white_prerequisite": {
            "prerequisite_id": "f" * 64,
            "eligible": True,
            "patch_count": 60,
            "classification_state": ("PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"),
            "reference_geometry_sha256": "8" * 64,
            "repeat_noise_p95_de76": 1.0,
        },
        "shared_camera_lock": camera_signature,
        "shared_analysis_bindings": {
            "repeat_noise_baseline": deepcopy(value["repeat_noise_baseline"]),
            "reference_geometry_sha256": "8" * 64,
            "repeat_noise_p95_de76": 1.0,
        },
    }
    monkeypatch.setattr(
        once,
        "_load_batch2_evidence",
        lambda _path: ({}, deepcopy(batch2_binding)),
    )

    def fake_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        assert once._ACTIVE_BATCH1_EVIDENCE_BINDING is not None  # noqa: SLF001
        assert once._ACTIVE_BATCH2_EVIDENCE_BINDING is not None  # noqa: SLF001
        return {
            "batch1_evidence_binding": deepcopy(
                once._ACTIVE_BATCH1_EVIDENCE_BINDING  # noqa: SLF001
            ),
            "batch2_evidence_binding": deepcopy(
                once._ACTIVE_BATCH2_EVIDENCE_BINDING  # noqa: SLF001
            ),
        }

    monkeypatch.setattr(once, "_BASE_RUN_ONCE", fake_run)
    result = once.run_once(
        "http://192.0.2.1",
        1,
        batch1_evidence=path,
        batch2_evidence=batch2_path,
        claims=tmp_path / "claims",
        output=tmp_path / "result.json",
        confirm_j2_on=True,
    )
    assert result["batch1_evidence_binding"]["requirements_id"] == (
        pack.BATCH1_EVIDENCE_REQUIREMENTS_ID
    )
    assert result["batch2_evidence_binding"]["bundle_id"] == "e" * 64
    assert once._ACTIVE_BATCH1_EVIDENCE_BINDING is None  # noqa: SLF001
    assert once._ACTIVE_BATCH2_EVIDENCE_BINDING is None  # noqa: SLF001


def test_mutation_headers_bind_batch1_requirements_id() -> None:
    action = once.base.runner.ACTIONS[0]
    value = once._headers(action, "boot-nonce", once.base.runner.ARM_INTENT)
    assert value["X-EC5-Batch1-Evidence-Requirements-Id"] == (
        pack.BATCH1_EVIDENCE_REQUIREMENTS_ID
    )


def test_routes_claims_nvs_and_ids_are_isolated() -> None:
    runner = once.base.runner
    assert set(runner.ENDPOINTS) == {
        "version",
        "manifest",
        "status",
        "report",
        "arm",
        "execute",
    }
    assert all(pack.ENDPOINT_BASE in route for route in runner.ENDPOINTS.values())
    assert runner.NVS_NAMESPACE == "tr20ph_v1"
    assert runner.NVS_KEY == "cursor_tr20ph1"
    assert "true_r20_partial_hold_v1_claims" in str(runner.DEFAULT_CLAIMS)
    assert runner.CONTRACT_ID == pack.CONTRACT_ID
    assert runner.ACTION_IDS == pack.ACTION_IDS
