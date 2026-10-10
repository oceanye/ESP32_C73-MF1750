"""Offline-only N6 browser E2E campaign declarations.

This module deliberately compiles data only.  It has no HTTP client, serial or
GPIO access, firmware uploader, claim writer, authorization generator, retry,
or recovery implementation.  The current G1/S1 ``convert-v2`` artifact is an
offline soft proof and therefore cannot become executable through this module.

The P0 visible-refresh contract remains the authority for the exact frame,
controller DTM streams, one-POST action identity, and workspace-global claim
*declaration*.  N6 adds the browser artifact/qualification evidence and a
fail-closed outcome matrix around that immutable P0 action.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from host.epd_frame import (
    ControllerMapping,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    controller_stream,
    fnv1a,
)
from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    LIMIT_PROFILE_KIND,
    CampaignContractError,
    ResultState,
    build_fixed_action_declaration,
    build_result_record,
    build_session_contract,
    canonical_json_bytes,
    describe_action_offline,
    seal_campaign_contract,
    seal_limit_profile,
    validate_action_description,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
    workspace_global_claim_declaration,
)

from .pipeline import (
    APPLICATION_SIMULATION_REPORT_VERSION,
    ApplicationArtifact,
    ApplicationError,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-n6-browser-e2e-offline-manifest"
DESCRIPTION_KIND = "mf1750-n6-browser-e2e-offline-description"
MANIFEST_HASH_SCOPE = (
    "entire N6 manifest excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
DESCRIPTION_HASH_SCOPE = (
    "entire N6 description excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)

DEFAULT_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))

_OFFLINE_CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_ready": False,
    "hardware_execution_authorized": False,
    "authorization_created": False,
    "claim_created": False,
    "network_io_performed": False,
    "device_io_performed": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
}

_P0_CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}

BROWSER_E2E_SCENARIOS = (
    {
        "id": "original_file_convert_v2_four_previews",
        "scope": "real_chromium_loopback_offline",
        "required_assertion": "original bytes, source SHA, four preview hashes, and DOM images match",
    },
    {
        "id": "contain_and_cover_geometry",
        "scope": "real_chromium_loopback_offline",
        "required_assertion": "server normalization evidence and visible source preview differ as declared",
    },
    {
        "id": "offline_preview_default_and_unqualified_artifact",
        "scope": "real_chromium_loopback_offline",
        "required_assertion": "formal upload, arm, and refresh remain closed",
    },
    {
        "id": "arm_expiry_double_click_and_reload",
        "scope": "real_chromium_loopback_offline",
        "required_assertion": "no qualified arm is minted, reload invalidates invisible state, and no frame POST occurs",
    },
    {
        "id": "stale_preview_and_artifact",
        "scope": "real_chromium_loopback_offline",
        "required_assertion": "old report-bound preview URLs fail closed",
    },
    {
        "id": "token_host_and_origin",
        "scope": "real_chromium_loopback_security",
        "required_assertion": "missing or wrong token and cross-origin mutation are rejected",
    },
    {
        "id": "post_submit_visible_abnormalities",
        "scope": "offline_policy_until_measured_artifact_gate",
        "required_assertion": "202-only, wrong job/report, or unknown network outcome cannot authorize a second POST or recovery",
    },
)

VISIBLE_ABNORMALITY_SCENARIOS = (
    "http_202_without_matching_terminal_job_and_report",
    "wrong_job_identity_state_or_frame_hash",
    "wrong_diagnostic_job_operation_mapping_or_dtm_hash",
    "network_outcome_unknown_after_frame_post",
    "browser_reload_after_submission_before_matching_evidence",
)

_VISIBLE_ABNORMALITY_POLICY = {
    "scenario_ids": list(VISIBLE_ABNORMALITY_SCENARIOS),
    "terminal_state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
    "maximum_total_frame_posts": 1,
    "second_frame_post_authorized": False,
    "additional_frame_post_count": 0,
    "retry_authorized": False,
    "recovery_authorized": False,
    "automatic_recovery_request_count": 0,
}

_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "campaign_id",
        "source_artifact",
        "qualification",
        "p0_campaign",
        "p0_action_identity_sha256",
        "p0_claim_declaration",
        "draft_limit_profile",
        "browser_e2e_scenarios",
        "visible_abnormality_policy",
        "classification",
        "integrity",
    }
)
_DESCRIPTION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "mode",
        "manifest_canonical_sha256",
        "campaign_id",
        "action_identity_sha256",
        "claim_declaration",
        "p0_action_description",
        "qualification",
        "contract_ready",
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "actual_frame_post_request_count",
        "actual_recovery_request_count",
        "maximum_frame_posts_if_future_executor_is_separately_authorized",
        "second_frame_post_authorized",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
        "blockers",
        "integrity",
    }
)


class N6BrowserCampaignError(ValueError):
    """Raised when an N6 offline declaration does not fail closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise N6BrowserCampaignError(f"value is not canonical JSON data: {error}") from error


def _integrity(payload: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        "canonical_sha256_scope": scope,
    }


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise N6BrowserCampaignError(f"{label} must be 64 lowercase hex digits")
    return value


def _exact_mapping(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise N6BrowserCampaignError(f"{label} fields differ from the N6 contract")
    return value


def _mapping_record(mapping: ControllerMapping) -> dict[str, Any]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def p0_frame_from_artifact(
    artifact: ApplicationArtifact,
    mappings: Sequence[ControllerMapping] = DEFAULT_MAPPINGS,
) -> dict[str, Any]:
    """Compile the exact P0 frame/DTM identity without performing I/O."""

    try:
        snapshot = artifact.validated_snapshot()
    except (ApplicationError, AttributeError, TypeError) as error:
        raise N6BrowserCampaignError(f"application artifact is invalid: {error}") from error
    selected = tuple(mappings)
    if selected != DEFAULT_MAPPINGS:
        raise N6BrowserCampaignError(
            "N6 browser action requires frozen CS1=left and CS2=right mappings"
        )
    controllers = []
    for name, mapping in zip(("CS1", "CS2"), selected):
        dtm = controller_stream(snapshot.frame, mapping)
        controllers.append(
            {
                "controller": name,
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(dtm),
                "dtm_sha256": hashlib.sha256(dtm).hexdigest(),
                "dtm_fnv1a": f"0x{fnv1a(dtm):08X}",
            }
        )
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "bits_per_pixel": 4,
        "bytes": len(snapshot.frame),
        "sha256": hashlib.sha256(snapshot.frame).hexdigest(),
        "fnv1a": f"0x{fnv1a(snapshot.frame):08X}",
        "controllers": controllers,
    }


def _selected_profile(
    report: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    simulation = report.get("simulation_report")
    mapping_report: Mapping[str, Any] | None = None
    if isinstance(simulation, Mapping):
        mapping_section = simulation.get("mapping")
        if isinstance(mapping_section, Mapping) and isinstance(
            mapping_section.get("report"), Mapping
        ):
            mapping_report = mapping_section["report"]
    profile = None if mapping_report is None else mapping_report.get("profile")
    if not isinstance(profile, Mapping):
        return {
            "id": None,
            "canonical_sha256": None,
            "characterization_level": None,
            "hardware_formal_qualified": False,
        }
    profile_id = profile.get("id")
    profile_sha = profile.get("canonical_sha256")
    configured = None
    configured_profiles = config.get("gamut_profiles")
    if isinstance(configured_profiles, list):
        configured = next(
            (
                item
                for item in configured_profiles
                if isinstance(item, Mapping) and item.get("id") == profile_id
            ),
            None,
        )
    configured_match = bool(
        isinstance(configured, Mapping)
        and configured.get("canonical_sha256") == profile_sha
        and configured.get("characterization_level")
        == profile.get("characterization_level")
    )
    return {
        "id": profile_id,
        "canonical_sha256": profile_sha,
        "characterization_level": profile.get("characterization_level"),
        "hardware_formal_qualified": bool(
            configured_match
            and configured.get("hardware_formal_qualified") is True
            and profile.get("characterization_level") == "measured_mixtures"
        ),
    }


def _artifact_and_qualification(
    artifact: ApplicationArtifact, config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = artifact.validated_snapshot()
    report = snapshot.report
    if report.get("version") != APPLICATION_SIMULATION_REPORT_VERSION or not isinstance(
        report.get("previews"), Mapping
    ):
        raise N6BrowserCampaignError(
            "N6 browser campaign requires a convert-v2 four-preview simulation artifact"
        )
    previews = report["previews"]
    if set(previews) != {"source", "mapped", "final", "model"}:
        raise N6BrowserCampaignError("N6 artifact must bind all four preview stages")
    config_palette = config.get("palette")
    report_palette = report.get("palette_provenance")
    if not isinstance(config_palette, Mapping) or not isinstance(report_palette, Mapping):
        raise N6BrowserCampaignError("palette provenance is missing")
    report_palette_id = report_palette.get("id", report_palette.get("palette_id"))
    if (
        report_palette_id != config_palette.get("id")
        or report_palette.get("canonical_sha256")
        != config_palette.get("canonical_sha256")
    ):
        raise N6BrowserCampaignError("artifact palette differs from application config")
    palette = {
        "id": report_palette_id,
        "canonical_sha256": report_palette.get("canonical_sha256"),
        "calibrated": report_palette.get("calibrated") is True,
        "measurement_bound": bool(
            isinstance(config_palette.get("calibration"), Mapping)
            and config_palette["calibration"].get("measurement_id")
            and config_palette["calibration"].get("artifact_sha256")
        ),
    }
    profile = _selected_profile(report, config)
    formal_eligibility = config.get("formal_eligibility")
    runtime_formal_eligible = bool(
        isinstance(formal_eligibility, Mapping)
        and formal_eligibility.get("eligible") is True
    )
    blockers: list[str] = []
    if not (palette["calibrated"] and palette["measurement_bound"]):
        blockers.append("measured_palette_missing_or_unqualified")
    if not profile["hardware_formal_qualified"]:
        blockers.append("measured_gamut_profile_missing_or_unqualified")
    if report.get("formal_upload_authorized") is not True:
        blockers.append("artifact_not_formally_upload_authorized")
    if not runtime_formal_eligible:
        blockers.append("runtime_formal_eligibility_closed")
    qualification = {
        "palette": palette,
        "gamut_profile": profile,
        "runtime_formal_eligible": runtime_formal_eligible,
        "measured_inputs_ready": not any(
            blocker
            in {
                "measured_palette_missing_or_unqualified",
                "measured_gamut_profile_missing_or_unqualified",
            }
            for blocker in blockers
        ),
        "artifact_formally_upload_authorized": report.get(
            "formal_upload_authorized"
        )
        is True,
        "hardware_ready": False,
        "blockers": blockers,
    }
    simulation = report["simulation_report"]
    mapping_report = simulation["mapping"]["report"]
    normalization = report.get("normalization")
    if not isinstance(normalization, Mapping):
        raise N6BrowserCampaignError("artifact normalization evidence is missing")
    source_artifact = {
        "artifact_identity": snapshot.identity,
        "input": {
            "sha256": report["input"].get("sha256"),
            "media_type": report["input"].get("media_type"),
        },
        "geometry": {
            "fit": normalization.get("fit"),
            "rotation_degrees": normalization.get("explicit_rotation_degrees"),
        },
        "palette": palette,
        "gamut_profile": profile,
        "mapping_algorithm": mapping_report.get("mapper", {}).get("algorithm"),
        "halftone_algorithm": simulation.get("halftone", {}).get("algorithm"),
        "previews": _snapshot(previews),
        "purpose": report.get("purpose"),
        "offline_verified": report.get("offline_verified") is True,
        "formal_upload_authorized": report.get("formal_upload_authorized") is True,
        "hardware_tested": report.get("hardware_tested") is True,
    }
    return source_artifact, qualification


def _draft_limit_profile(
    *, panel: Mapping[str, Any], firmware: Mapping[str, Any], action: Mapping[str, Any]
) -> dict[str, Any]:
    identity = action["identity"]
    return seal_limit_profile(
        {
            "schema_version": 1,
            "kind": LIMIT_PROFILE_KIND,
            "profile_id": "n6-browser-e2e-unreviewed-draft",
            "profile_version": "1.0.0",
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "action_allowlist": [
                {
                    "action_id": identity["action_id"],
                    "action_identity_sha256": action["action_identity_sha256"],
                    "method": "POST",
                    "endpoint": "/api/frame",
                    "frame_sha256": identity["frame"]["sha256"],
                    "maximum_uses": 1,
                }
            ],
            "limits": {
                "maximum_campaign_visible_refreshes": None,
                "maximum_session_visible_refreshes": None,
                "maximum_consecutive_visible_refreshes": None,
                "minimum_interval_seconds": None,
                "minimum_cooldown_seconds": None,
                "minimum_start_temperature_c": None,
                "maximum_start_temperature_c": None,
                "maximum_post_refresh_temperature_c": None,
            },
            "usage": {
                "cumulative_visible_refresh_count": None,
                "session_visible_refresh_count": None,
                "consecutive_visible_refresh_count": None,
                "last_visible_refresh_completed_at": None,
                "snapshot_at": None,
                "evidence_sha256": None,
            },
            "validity": {"valid_from": None, "expires_at": None},
            "review": {
                "approved": False,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_artifact_sha256": None,
            },
        }
    )


def build_n6_offline_manifest(
    artifact: ApplicationArtifact,
    application_config: Mapping[str, Any],
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    campaign_id: str = "n6-browser-e2e-v1",
    session_id: str = "n6-browser-session-1",
    cell_id: str = "n6-browser-cell-1",
    action_id: str = "n6-browser-frozen-photo-1",
) -> dict[str, Any]:
    """Build a deterministic N6 manifest and P0 declaration with zero I/O."""

    if not isinstance(application_config, Mapping):
        raise N6BrowserCampaignError("application_config must be an object")
    source_artifact, qualification = _artifact_and_qualification(
        artifact, application_config
    )
    frame = p0_frame_from_artifact(artifact)
    action = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id=action_id,
        phase="browser-e2e-single-visible-target",
        frame=frame,
    )
    session = build_session_contract(
        session_id=session_id,
        cell_id=cell_id,
        power_mode="controller_fresh_boot",
        planned_cooldown_seconds=0,
        final_power_off_required=False,
        action_identity_sha256s=[action["action_identity_sha256"]],
    )
    campaign = seal_campaign_contract(
        {
            "schema_version": 1,
            "kind": CAMPAIGN_KIND,
            "campaign_id": campaign_id,
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "actions": [action],
            "sessions": [session],
            "classification": _snapshot(_P0_CLASSIFICATION),
        }
    )
    claim = workspace_global_claim_declaration(action["action_identity_sha256"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "campaign_id": campaign_id,
        "source_artifact": source_artifact,
        "qualification": qualification,
        "p0_campaign": campaign,
        "p0_action_identity_sha256": action["action_identity_sha256"],
        "p0_claim_declaration": claim,
        "draft_limit_profile": _draft_limit_profile(
            panel=panel, firmware=firmware, action=action
        ),
        "browser_e2e_scenarios": _snapshot(BROWSER_E2E_SCENARIOS),
        "visible_abnormality_policy": _snapshot(_VISIBLE_ABNORMALITY_POLICY),
        "classification": _snapshot(_OFFLINE_CLASSIFICATION),
    }
    manifest = _snapshot(payload)
    manifest["integrity"] = _integrity(manifest, MANIFEST_HASH_SCOPE)
    validate_n6_offline_manifest(manifest)
    return manifest


def validate_n6_offline_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact_mapping(manifest, _MANIFEST_KEYS, "N6 manifest")
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != MANIFEST_KIND:
        raise N6BrowserCampaignError("N6 manifest kind or version is invalid")
    campaign = validate_campaign_contract(root["p0_campaign"])
    if root["campaign_id"] != campaign["campaign_id"]:
        raise N6BrowserCampaignError("N6/P0 campaign identity differs")
    if len(campaign["actions"]) != 1 or len(campaign["sessions"]) != 1:
        raise N6BrowserCampaignError("N6 phase-1 manifest must contain one fixed action")
    action = campaign["actions"][0]
    action_sha = _sha256(
        root["p0_action_identity_sha256"], "N6 P0 action identity"
    )
    if action_sha != action["action_identity_sha256"]:
        raise N6BrowserCampaignError("N6 P0 action identity differs from campaign")
    expected_claim = workspace_global_claim_declaration(action_sha)
    if root["p0_claim_declaration"] != expected_claim or action["claim"] != expected_claim:
        raise N6BrowserCampaignError("N6 claim is not the P0 declaration")
    profile = validate_limit_profile(root["draft_limit_profile"])
    if profile["review"]["approved"] is not False:
        raise N6BrowserCampaignError("N6 draft limit profile must remain unapproved")

    artifact = root["source_artifact"]
    if not isinstance(artifact, Mapping):
        raise N6BrowserCampaignError("N6 source artifact must be an object")
    artifact_identity = artifact.get("artifact_identity")
    if not isinstance(artifact_identity, Mapping):
        raise N6BrowserCampaignError("N6 artifact identity is missing")
    frame = action["identity"]["frame"]
    if (
        artifact_identity.get("frame_sha256") != frame["sha256"]
        or artifact_identity.get("frame_bytes") != FRAME_BYTES
        or artifact_identity.get("frame_fnv1a")
        != int(frame["fnv1a"][2:], 16)
    ):
        raise N6BrowserCampaignError("N6 artifact and P0 frame identities differ")
    if (
        artifact.get("purpose") != "offline_preview"
        or artifact.get("offline_verified") is not True
        or artifact.get("formal_upload_authorized") is not False
        or artifact.get("hardware_tested") is not False
    ):
        raise N6BrowserCampaignError(
            "N6 phase-1 artifact must remain offline-only and hardware-untested"
        )
    previews = artifact.get("previews")
    if not isinstance(previews, Mapping) or set(previews) != {
        "source",
        "mapped",
        "final",
        "model",
    }:
        raise N6BrowserCampaignError("N6 artifact does not bind four previews")
    for stage, metadata in previews.items():
        if not isinstance(metadata, Mapping):
            raise N6BrowserCampaignError(f"N6 {stage} preview metadata is invalid")
        _sha256(metadata.get("sha256"), f"N6 {stage} preview SHA-256")

    qualification = root["qualification"]
    if not isinstance(qualification, Mapping):
        raise N6BrowserCampaignError("N6 qualification must be an object")
    blockers = qualification.get("blockers")
    if not isinstance(blockers, list) or not blockers:
        raise N6BrowserCampaignError("N6 phase-1 qualification must retain blockers")
    if (
        qualification.get("hardware_ready") is not False
        or qualification.get("artifact_formally_upload_authorized") is not False
    ):
        raise N6BrowserCampaignError("N6 qualification attempted to authorize hardware")
    palette = qualification.get("palette")
    gamut_profile = qualification.get("gamut_profile")
    if not isinstance(palette, Mapping) or not isinstance(gamut_profile, Mapping):
        raise N6BrowserCampaignError("N6 measured-input qualification is invalid")
    palette_ready = bool(
        palette.get("calibrated") is True and palette.get("measurement_bound") is True
    )
    profile_ready = gamut_profile.get("hardware_formal_qualified") is True
    expected_measured_ready = palette_ready and profile_ready
    if qualification.get("measured_inputs_ready") is not expected_measured_ready:
        raise N6BrowserCampaignError("N6 measured-input readiness is inconsistent")
    palette_blocked = "measured_palette_missing_or_unqualified" in blockers
    profile_blocked = "measured_gamut_profile_missing_or_unqualified" in blockers
    if palette_blocked == palette_ready or profile_blocked == profile_ready:
        raise N6BrowserCampaignError(
            "N6 measured palette/profile blockers are inconsistent"
        )
    if root["browser_e2e_scenarios"] != list(BROWSER_E2E_SCENARIOS):
        raise N6BrowserCampaignError("N6 browser E2E matrix changed")
    if root["visible_abnormality_policy"] != _VISIBLE_ABNORMALITY_POLICY:
        raise N6BrowserCampaignError("N6 visible-abnormality policy changed")
    if root["classification"] != _OFFLINE_CLASSIFICATION:
        raise N6BrowserCampaignError("N6 offline classification changed")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, MANIFEST_HASH_SCOPE):
        raise N6BrowserCampaignError("N6 manifest canonical integrity is invalid")
    return root


def describe_n6_action_offline(
    manifest: Mapping[str, Any], *, evaluated_at: str
) -> dict[str, Any]:
    """Describe the current N6 action without creating a claim or authorization."""

    root = validate_n6_offline_manifest(manifest)
    p0_description = describe_action_offline(
        root["p0_campaign"],
        action_identity_sha256=root["p0_action_identity_sha256"],
        limit_profile=root["draft_limit_profile"],
        evaluated_at=evaluated_at,
    )
    blockers = list(
        dict.fromkeys(
            [
                *root["qualification"]["blockers"],
                *p0_description["blockers"],
            ]
        )
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "campaign_id": root["campaign_id"],
        "action_identity_sha256": root["p0_action_identity_sha256"],
        "claim_declaration": _snapshot(root["p0_claim_declaration"]),
        "p0_action_description": p0_description,
        "qualification": _snapshot(root["qualification"]),
        "contract_ready": False,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "actual_frame_post_request_count": 0,
        "actual_recovery_request_count": 0,
        "maximum_frame_posts_if_future_executor_is_separately_authorized": 1,
        "second_frame_post_authorized": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
    }
    description = _snapshot(payload)
    description["integrity"] = _integrity(description, DESCRIPTION_HASH_SCOPE)
    validate_n6_action_description(description, manifest=root)
    return description


def validate_n6_action_description(
    description: Mapping[str, Any], *, manifest: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    root = _exact_mapping(description, _DESCRIPTION_KEYS, "N6 description")
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != DESCRIPTION_KIND
        or root["mode"] != "describe-only"
    ):
        raise N6BrowserCampaignError("N6 description kind, version, or mode is invalid")
    _sha256(root["manifest_canonical_sha256"], "N6 manifest identity")
    action_sha = _sha256(root["action_identity_sha256"], "N6 action identity")
    if root["claim_declaration"] != workspace_global_claim_declaration(action_sha):
        raise N6BrowserCampaignError("N6 description claim declaration is invalid")
    validate_action_description(root["p0_action_description"])
    if root["p0_action_description"]["action"]["action_identity_sha256"] != action_sha:
        raise N6BrowserCampaignError("N6/P0 description action identity differs")
    false_fields = (
        "contract_ready",
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "second_frame_post_authorized",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
    )
    if any(root[field] is not False for field in false_fields):
        raise N6BrowserCampaignError("N6 description must remain non-executable")
    if (
        root["actual_frame_post_request_count"] != 0
        or root["actual_recovery_request_count"] != 0
        or root["maximum_frame_posts_if_future_executor_is_separately_authorized"]
        != 1
    ):
        raise N6BrowserCampaignError("N6 offline request counters are invalid")
    if not isinstance(root["blockers"], list) or not root["blockers"]:
        raise N6BrowserCampaignError("N6 description must retain explicit blockers")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, DESCRIPTION_HASH_SCOPE):
        raise N6BrowserCampaignError("N6 description canonical integrity is invalid")
    if manifest is not None:
        manifest_root = validate_n6_offline_manifest(manifest)
        if (
            root["manifest_canonical_sha256"]
            != manifest_root["integrity"]["canonical_sha256"]
            or root["campaign_id"] != manifest_root["campaign_id"]
            or action_sha != manifest_root["p0_action_identity_sha256"]
            or root["qualification"] != manifest_root["qualification"]
        ):
            raise N6BrowserCampaignError("N6 description is not bound to the manifest")
    return root


def build_n6_visible_abnormality_result(
    manifest: Mapping[str, Any],
    *,
    scenario_id: str,
    completed_at: str,
    evidence_manifest_sha256: str,
    observed_frame_post_count: int,
) -> dict[str, Any]:
    """Build a terminal UNKNOWN record; never retry, recover, or create a claim."""

    root = validate_n6_offline_manifest(manifest)
    if scenario_id not in VISIBLE_ABNORMALITY_SCENARIOS:
        raise N6BrowserCampaignError("unknown N6 visible-abnormality scenario")
    if type(observed_frame_post_count) is not int or observed_frame_post_count not in {
        0,
        1,
    }:
        raise N6BrowserCampaignError("observed frame POST count must be zero or one")
    result = build_result_record(
        action_identity_sha256=root["p0_action_identity_sha256"],
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=completed_at,
        evidence_manifest_sha256=evidence_manifest_sha256,
        post_request_count=observed_frame_post_count,
        details=(
            f"N6 visible abnormality {scenario_id}; terminal unknown; "
            "no second POST and no recovery"
        ),
    )
    validate_result_record(result)
    return result


__all__ = [
    "BROWSER_E2E_SCENARIOS",
    "DEFAULT_MAPPINGS",
    "DESCRIPTION_HASH_SCOPE",
    "DESCRIPTION_KIND",
    "MANIFEST_HASH_SCOPE",
    "MANIFEST_KIND",
    "N6BrowserCampaignError",
    "SCHEMA_VERSION",
    "VISIBLE_ABNORMALITY_SCENARIOS",
    "build_n6_offline_manifest",
    "build_n6_visible_abnormality_result",
    "describe_n6_action_offline",
    "p0_frame_from_artifact",
    "validate_n6_action_description",
    "validate_n6_offline_manifest",
]
