from __future__ import annotations

import copy
import hashlib
from typing import Any

from host.runtime_waveform import contracts, evidence, format_registry


CREATED_AT = "2026-08-10T09:00:00+08:00"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_complete_evidence_fixture() -> dict[str, Any]:
    cs1 = bytes(range(256)) * 3
    cs2 = bytes(reversed(range(256))) * 3
    artifacts: dict[str, bytes] = {
        "reference_artifact": b"test-only-reference-artifact-v1",
        "panel_identity_document": b"test-only-panel-identity-v1",
        "controller_revision_document": b"test-only-controller-revision-v1",
        "format_document": b"test-only-decoded-3bit-format-v1",
        "loader_source": b"test-only-portable-loader-source-v1",
        "electrical_approval": b"test-only-electrical-approval-v1",
        "known_good_profile": b"test-only-known-good-profile-v1",
        "white_recovery_contract": b"test-only-white-recovery-contract-v1",
        "vendor_review": b"test-only-independent-review-v1",
        "command_parameter_0": b"\x01",
        "command_parameter_2": b"\x01",
    }
    candidate = contracts.build_reference_blocked_candidate(created_at=CREATED_AT)
    candidate["profile_id"] = "test-only-reviewed-dual-controller-3bit-v1"
    candidate["panel"]["batch_id"] = "test-only-reviewed-batch"
    candidate["panel"]["controller_revision"] = "test-only-revision"
    candidate["payload"] = {
        "representation": "plaintext_decoded_3bit_lut",
        "format_id": "test-only-reviewed-3bit-layout-v1",
        "format_document_sha256": _sha(artifacts["format_document"]),
        "controller_payloads": [
            {"controller": "CS1", "bytes": len(cs1), "sha256": _sha(cs1)},
            {"controller": "CS2", "bytes": len(cs2), "sha256": _sha(cs2)},
        ],
    }
    candidate["electrical"] = {
        "temperature_min_c": 20.0,
        "temperature_max_c": 25.0,
        "vcom_mv": -2000.0,
        "vgh_mv": 20_000.0,
        "vgl_mv": -20_000.0,
        "vsh_mv": 15_000.0,
        "vsl_mv": -15_000.0,
        "frame_rate_hz": 50.0,
        "phase_timing_documented": True,
    }
    candidate["provenance"] = {
        "reference_artifact_sha256": _sha(artifacts["reference_artifact"]),
        "source_payload_sha256": _sha(cs1 + cs2),
        "loader_source_sha256": _sha(artifacts["loader_source"]),
        "vendor_or_panel_owner_review_id": "test-reviewer-001",
        "source_is_current_panel_3bit": True,
    }
    candidate["recovery"] = {
        "known_good_profile_sha256": _sha(artifacts["known_good_profile"]),
        "white_recovery_contract_sha256": _sha(
            artifacts["white_recovery_contract"]
        ),
        "restore_otp_mode_without_programming": True,
        "validated_on_sacrificial_panel": True,
    }
    candidate["qualification_gates"] = {
        name: True for name in contracts.GATE_NAMES
    }

    registration = {
        "schema_version": format_registry.FORMAT_REGISTRATION_SCHEMA_VERSION,
        "kind": format_registry.FORMAT_REGISTRATION_KIND,
        "registration_id": "test-only-registration-v1",
        "format_id": candidate["payload"]["format_id"],
        "format_document_sha256": candidate["payload"][
            "format_document_sha256"
        ],
        "loader_source_sha256": candidate["provenance"]["loader_source_sha256"],
        "reviewer_id": candidate["provenance"][
            "vendor_or_panel_owner_review_id"
        ],
        "review_artifact_sha256": _sha(artifacts["vendor_review"]),
        "steps": [
            {
                "index": 0,
                "controller_target": "CS1",
                "opcode": 0xE9,
                "parameter_source": "literal_parameter",
                "parameter_length": 1,
                "literal_parameter_sha256": _sha(
                    artifacts["command_parameter_0"]
                ),
                "predecessor_index": None,
            },
            {
                "index": 1,
                "controller_target": "CS1",
                "opcode": 0x20,
                "parameter_source": "controller_payload",
                "parameter_length": len(cs1),
                "literal_parameter_sha256": None,
                "predecessor_index": 0,
            },
            {
                "index": 2,
                "controller_target": "CS2",
                "opcode": 0xE9,
                "parameter_source": "literal_parameter",
                "parameter_length": 1,
                "literal_parameter_sha256": _sha(
                    artifacts["command_parameter_2"]
                ),
                "predecessor_index": 1,
            },
            {
                "index": 3,
                "controller_target": "CS2",
                "opcode": 0x20,
                "parameter_source": "controller_payload",
                "parameter_length": len(cs2),
                "literal_parameter_sha256": None,
                "predecessor_index": 2,
            },
        ],
    }
    artifacts["format_registration"] = contracts.canonical_json_bytes(registration)
    bundle = {
        "schema_version": evidence.EVIDENCE_SCHEMA_VERSION,
        "kind": evidence.EVIDENCE_BUNDLE_KIND,
        "candidate_manifest_sha256": _sha(
            contracts.canonical_json_bytes(candidate)
        ),
        "reviewer_id": candidate["provenance"][
            "vendor_or_panel_owner_review_id"
        ],
        "panel_binding": {
            key: candidate["panel"][key]
            for key in evidence._PANEL_BINDING_KEYS  # noqa: SLF001
        },
        "electrical_binding": copy.deepcopy(candidate["electrical"]),
        "recovery_binding": copy.deepcopy(candidate["recovery"]),
        "artifact_records": [
            {"role": role, "bytes": len(payload), "sha256": _sha(payload)}
            for role, payload in sorted(artifacts.items())
        ],
        "format_registration_sha256": _sha(
            contracts.canonical_json_bytes(registration)
        ),
        "hardware_execution_eligible": False,
        "visible_refresh_authorized": False,
    }
    return {
        "candidate": candidate,
        "candidate_manifest_bytes": contracts.canonical_json_bytes(candidate),
        "controller_payload_bytes": {"CS1": cs1, "CS2": cs2},
        "registration": registration,
        "registry": {candidate["payload"]["format_id"]: registration},
        "artifacts": artifacts,
        "bundle": bundle,
    }


def rebind_bundle_to_candidate(fixture: dict[str, Any]) -> None:
    candidate = fixture["candidate"]
    fixture["candidate_manifest_bytes"] = contracts.canonical_json_bytes(candidate)
    fixture["bundle"]["candidate_manifest_sha256"] = _sha(
        fixture["candidate_manifest_bytes"]
    )


def refresh_registration_artifact(fixture: dict[str, Any]) -> None:
    registration = fixture["registration"]
    payload = contracts.canonical_json_bytes(registration)
    fixture["registry"] = {registration["format_id"]: registration}
    fixture["artifacts"]["format_registration"] = payload
    fixture["bundle"]["format_registration_sha256"] = _sha(payload)
    for record in fixture["bundle"]["artifact_records"]:
        if record["role"] == "format_registration":
            record["bytes"] = len(payload)
            record["sha256"] = _sha(payload)
            break
