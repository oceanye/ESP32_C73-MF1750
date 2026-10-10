#!/usr/bin/env python3
"""Frozen N8 execution identities and deep finalized-bundle validation.

The historical N8 compiler remains the only source of the fifteen P0 action
and frame identities.  A separately supplied, reviewed runtime manifest may
bind a real panel, evidence assets, supplier temperature bins, and a current
limit profile, but it may not change the frozen schedule or any action/frame
identity.

This module performs no filesystem, network, serial, GPIO, reset, flashing, or
power-control operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional

from host.epd_frame import ControllerMapping, controller_stream, fnv1a, generate_fixture, validate_frame
from host.visible_refresh_campaign import (
    CLAIM_REGISTRY_ID,
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
    evaluate_limit_profile,
    result_file_sha256,
    validate_limit_profile,
    validate_result_record,
)
from tools import g1_s1_n8_carryover_campaign as campaign
from tools import g1_s1_rc2g_map_baseline_once as _map
from tools import g1_s1_rc2g_quality_refresh_once as _quality
from tools import g1_s1_rc2g_n2_photo_campaign as n2


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-g1-s1-n8-fixed-execution-contract"
CONTRACT_ID = "g1-s1-n8-fixed-execution-v1"
RUNNER_KIND = "mf1750-g1-s1-rc2g-n8-fixed-action-runner"
CLAIM_KIND = "mf1750-visible-refresh-fixed-action-consumed-claim"
LOCK_KIND = "mf1750-g1-s1-rc2g-n8-fixed-action-lock"
EVIDENCE_KIND = "mf1750-g1-s1-rc2g-n8-action-evidence"
OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n8-action-observation"
FINALIZATION_KIND = "mf1750-g1-s1-rc2g-n8-action-finalization"
BUNDLE_KIND = "mf1750-g1-s1-rc2g-n8-finalized-action-bundle"

LOCK_FILENAME = "ATTEMPT-LOCK.json"
MANIFEST_FILENAME = "N8-RUNTIME-MANIFEST.json"
PROFILE_FILENAME = "REVIEWED-LIMIT-PROFILE.json"
EVIDENCE_FILENAME = "N8-ACTION-EVIDENCE.json"
OBSERVATION_FILENAME = "N8-ACTION-OBSERVATION.json"
FINALIZATION_FILENAME = "N8-ACTION-FINALIZATION.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
BUNDLE_FILENAME = "N8-FINALIZED-ACTION-BUNDLE.json"
CAMERA_CAPTURE_FILENAME = "N8-CAMERA-CAPTURE.bin"

AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N8_FIXED_ACTION__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
CONTRACT_HASH_SCOPE = (
    "entire N8 fixed execution contract excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)

EXPECTED_SOURCE_MANIFEST_CANONICAL_SHA256 = (
    "0914e9a63cc18593b27b1f51cf86e7a29a4c65a17b0427b5d4717ee745b8ba91"
)
EXPECTED_SOURCE_MANIFEST_FILE_SHA256 = (
    "5d42dd01036512b836e286bb7c2f0735df36523b1434b84eb12bbba471c1e4ab"
)
EXPECTED_CONTRACT_CANONICAL_SHA256: Optional[str] = (
    "51efc4a3d298813956a0dbc380032aaeac460c23a52981f4f2ffd1690eda976e"
)
EXPECTED_CONTRACT_FILE_SHA256: Optional[str] = (
    "fd3ea6e182cbc06c0d247c8051a4213d1459559f4a8926d704131fd81d6d5fbf"
)

FIXED_ACTION_SHA256S = {
    "n8-aba-q1-q4-q1-map": "07d5084547a1fb66c12f2a47b8bea583f4ba66ebc67f0141ab07d1c647d2ee2a",
    "n8-aba-q1-q4-q1-a1": "a561fa612d3fb259b3fd58eb810b6c2eaf66d158e1b234ccaa99e7a2e1fcb1ea",
    "n8-aba-q1-q4-q1-b": "42abc25af4444c712cc5a31281d078701011bfd471e930b5237ece53b1b1238c",
    "n8-aba-q1-q4-q1-a2": "ff7bff47b4957469ed68b05c88d53da70c26bf60ffc7b93a026c173aa532de04",
    "n8-warm-q1-q2-q3-q4-map": "07a55c73bee44059300ba321c07b55f48252d90eccdeb41c22789e150d39c209",
    "n8-warm-q1-q2-q3-q4-w1": "25df2ad988a27e3683cb56c5d7b4a2ce91547fa80ef3577ba1b93647cc68c64b",
    "n8-warm-q1-q2-q3-q4-w2": "1be47a54c5c84e07cdf1128a6dda92328e147bdfbd152f40fd7aeefc3bd9b502",
    "n8-warm-q1-q2-q3-q4-w3": "63a1f18f5eb4ea851cb0df29f64f6b9bfcbdccc545cbab76887028d850014eac",
    "n8-warm-q1-q2-q3-q4-w4": "01341243d31f0c476061844c73d0b366e87e58d219b291b13c8d20f948933496",
    "n8-temperature-low-q4-map": "56f77ae6bcf2df3671a2d8f77d0577ed0663221ddbd8a2810d4c8f8b6ec72bcd",
    "n8-temperature-low-q4-target": "421ee6d9fd805bef0f77383682cf9468d21240af7285c1fbb07cfd657288a251",
    "n8-temperature-nominal-q4-map": "ae3cfed4996d848c379d8984bf0f5d9327c6da924bbb337404a95afcbd8bd226",
    "n8-temperature-nominal-q4-target": "75fbd55c08cf2cf5bb110b946cd7a600b351260965db4917b6fa72b1292d3553",
    "n8-temperature-high-q4-map": "a6cebc64bb7cac3426b7902042d1a139ed3ff48c8d5138c7cbeb798a59a0b578",
    "n8-temperature-high-q4-target": "22db68185e453191242e509139ec16aa65e1179385a1ce7bb4b0f459dab53d2d",
}
FIXED_ACTION_KEYS = tuple(FIXED_ACTION_SHA256S)
_BUNDLE_RECORDS = (
    "manifest",
    "claim",
    "lock",
    "profile",
    "evidence",
    "observation",
    "finalization",
    "result",
)
_TIMING_FIELDS = {
    "queue_delay_ms",
    "job_duration_ms",
    "driver_total_ms",
    "cs1_upload_ms",
    "cs2_upload_ms",
    "pon_ms",
    "drf_ms",
    "pof_ms",
    "post_psr_ms",
}


class N8ExecutionContractError(ValueError):
    """Frozen N8 execution or evidence identity failed closed."""


@dataclass(frozen=True)
class N8ActionSnapshot:
    key: str
    sequence_id: str
    ordinal: int
    role: str
    frame_source_id: str
    power_mode: str
    temperature_bin_id: Optional[str]
    campaign: Mapping[str, Any]
    action: Mapping[str, Any]
    frame: bytes
    reference_preview: Mapping[str, Any]


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8ExecutionContractError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": CONTRACT_HASH_SCOPE,
    }


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise N8ExecutionContractError(
            f"{label} keys changed; missing={sorted(keys - actual)}, extra={sorted(actual - keys)}"
        )
    return value


def _require_sha256(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        suffix = " or null" if nullable else ""
        raise N8ExecutionContractError(f"{label} must be 64 lowercase hex digits{suffix}")
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N8ExecutionContractError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise N8ExecutionContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N8ExecutionContractError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N8ExecutionContractError(f"{label} is above {maximum}")
    return result


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise N8ExecutionContractError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N8ExecutionContractError(f"{label} is not RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N8ExecutionContractError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def _source_manifest() -> Mapping[str, Any]:
    root = campaign.validate_n8_manifest(campaign.compile_n8_manifest())
    if (
        root["integrity"]["canonical_sha256"]
        != EXPECTED_SOURCE_MANIFEST_CANONICAL_SHA256
        or _sha256(root) != EXPECTED_SOURCE_MANIFEST_FILE_SHA256
    ):
        raise N8ExecutionContractError("frozen N8 source manifest identity changed")
    return root


def _action_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions = {
        action["action_identity_sha256"]: action
        for action in manifest["p0_campaign"]["actions"]
    }
    rows: list[dict[str, Any]] = []
    for sequence in manifest["sequences"]:
        for record in sequence["actions"]:
            action_sha = record["action_identity_sha256"]
            action = actions[action_sha]
            rows.append(
                {
                    "action_key": action["identity"]["action_id"],
                    "action_identity_sha256": action_sha,
                    "sequence_id": sequence["sequence_id"],
                    "ordinal": record["ordinal"],
                    "role": record["role"],
                    "frame_source_id": record["frame_source_id"],
                    "frame": _snapshot(action["identity"]["frame"]),
                    "prior_action_identity_sha256": action["identity"]["prior"][
                        "action_identity_sha256"
                    ] if action["identity"]["prior"] is not None else None,
                    "power_mode": sequence["power_mode"],
                    "temperature_bin_id": sequence["temperature_bin_id"],
                }
            )
    return rows


def _unsigned_contract() -> dict[str, Any]:
    source = _source_manifest()
    rows = _action_rows(source)
    actual = {row["action_key"]: row["action_identity_sha256"] for row in rows}
    if actual != FIXED_ACTION_SHA256S:
        raise N8ExecutionContractError("the fifteen frozen action identities changed")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": CONTRACT_ID,
        "campaign_id": campaign.CAMPAIGN_ID,
        "source_manifest": {
            "kind": campaign.MANIFEST_KIND,
            "canonical_sha256": EXPECTED_SOURCE_MANIFEST_CANONICAL_SHA256,
            "file_sha256": EXPECTED_SOURCE_MANIFEST_FILE_SHA256,
        },
        "fixed_actions": rows,
        "counts": {
            "sequences": 5,
            "visible_actions": 15,
            "session_roots": 5,
            "dependent_finalized_pass_whole_file_bindings": 10,
        },
        "power_semantics": {
            "controller_fresh_boot_sequences": [
                campaign.N8_SEQUENCE_IDS[0],
                campaign.N8_SEQUENCE_IDS[2],
                campaign.N8_SEQUENCE_IDS[3],
                campaign.N8_SEQUENCE_IDS[4],
            ],
            "supervised_continuous_sequences": [campaign.N8_SEQUENCE_IDS[1]],
            "warm_session_requires_controller_fresh_boot": False,
            "warm_root_dynamic_first_action_baseline": True,
            "warm_root_requires_controller_idle_no_inflight_confirmation": True,
            "warm_root_result_job_and_operation_ids": "record-live-positive-next-u32",
            "j2_may_remain_on_during_nominal_sequence": True,
            "dependent_action_forbids_controller_reboot": True,
            "dependent_action_forbids_j2_disconnect": True,
            "dependent_action_forbids_panel_power_cycle": True,
            "dependent_action_forbids_other_visible_refresh": True,
            "runner_controls_power_or_reset": False,
        },
        "protocol_contract": {
            "method": "POST",
            "endpoint": "/api/frame",
            "maximum_post_requests_per_claim": 1,
            "claims_are_workspace_global_and_permanent": True,
            "claim_committed_before_any_network_io": True,
            "automatic_retry": False,
            "automatic_recovery": False,
            "post_claim_error_state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
            "dependent_job_and_operation_ids": "strict-next-nonzero-u32",
            "dependent_live_prior_must_equal_stored_prior_job_and_diagnostic": True,
        },
        "evidence_contract": {
            "records": list(_BUNDLE_RECORDS),
            "all_record_whole_file_sha256_required": True,
            "prior_bundle_whole_file_sha256_required": True,
            "prior_finalization_whole_file_sha256_required": True,
            "prior_result_whole_file_sha256_required": True,
            "external_panel_location_temperature_required": True,
            "internal_or_swc_temperature_inference_forbidden": True,
            "raw_fixed_camera_capture_required": True,
            "fixed_camera_assets_must_match_runtime_manifest": True,
            "manual_finalization_required": True,
            "visual_electrical_thermal_continuity_assessed_separately": True,
        },
        "analysis_contract": {
            "qualification_state": "NOT_QUALIFIED",
            "descriptive_only": True,
            "population_inference_allowed": False,
            "causal_threshold_conclusion_allowed": False,
            "p95_p99_for_n_less_than_10": False,
        },
        "classification": {
            "offline_compiled": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }


@lru_cache(maxsize=1)
def _compiled_contract() -> Mapping[str, Any]:
    unsigned = _unsigned_contract()
    return {**unsigned, "integrity": _integrity(unsigned)}


def compile_n8_execution_contract() -> dict[str, Any]:
    root = _snapshot(_compiled_contract())
    validate_n8_execution_contract(root)
    return root


def validate_n8_execution_contract(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = _compiled_contract()
    root = _snapshot(value)
    if root != expected:
        raise N8ExecutionContractError("N8 fixed execution contract changed")
    canonical = root["integrity"]["canonical_sha256"]
    file_sha = _sha256(root)
    if EXPECTED_CONTRACT_CANONICAL_SHA256 is not None and canonical != EXPECTED_CONTRACT_CANONICAL_SHA256:
        raise N8ExecutionContractError("N8 execution contract canonical identity changed")
    if EXPECTED_CONTRACT_FILE_SHA256 is not None and file_sha != EXPECTED_CONTRACT_FILE_SHA256:
        raise N8ExecutionContractError("N8 execution contract whole-file identity changed")
    return root


def execution_contract_file_sha256(value: Mapping[str, Any]) -> str:
    return _sha256(validate_n8_execution_contract(value))


def _runtime_frozen_projection(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _action_rows(manifest)


def validate_n8_runtime_manifest(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept reviewed runtime bindings only when frozen science is unchanged."""

    try:
        root = campaign.validate_n8_manifest(value)
        profile = validate_limit_profile(root["limit_profile"])
    except (campaign.N8CampaignError, CampaignContractError) as error:
        raise N8ExecutionContractError(f"N8 runtime manifest is invalid: {error}") from error
    source = _source_manifest()
    if (
        root["source_n2"] != source["source_n2"]
        or root["frames"] != source["frames"]
        or root["power_semantics"] != source["power_semantics"]
        or root["dependency_contract"] != source["dependency_contract"]
        or root["analysis_contract"] != source["analysis_contract"]
        or _runtime_frozen_projection(root) != _runtime_frozen_projection(source)
    ):
        raise N8ExecutionContractError("runtime manifest changed frozen N8 science or actions")
    if str(root["panel"].get("serial", "")).startswith("UNBOUND-"):
        raise N8ExecutionContractError("runtime panel instance is unbound")
    if profile["panel"] != root["panel"] or profile["firmware"] != root["firmware"]:
        raise N8ExecutionContractError("runtime profile panel/firmware binding changed")
    if profile["review"]["approved"] is not True:
        raise N8ExecutionContractError("runtime limit profile is not reviewed")
    expected_allowlist = {
        action["action_identity_sha256"] for action in root["p0_campaign"]["actions"]
    }
    actual_allowlist = {
        item.get("action_identity_sha256") for item in profile["action_allowlist"]
    }
    if actual_allowlist != expected_allowlist or len(profile["action_allowlist"]) != 15:
        raise N8ExecutionContractError("runtime profile does not allowlist exactly 15 N8 actions")
    blockers = [
        *campaign._binding_blockers(
            panel=root["panel"], firmware=root["firmware"], profile=profile,
            bindings=root["binding_registry"],
        ),
        *campaign._measurement_blockers(root["measurement_registry"]),
        *campaign._temperature_bin_blockers(root["temperature_bin_plan"]),
    ]
    if blockers:
        raise N8ExecutionContractError("runtime manifest is incomplete: " + ", ".join(blockers))
    return root


@lru_cache(maxsize=1)
def _loaded_frames() -> Mapping[str, tuple[bytes, Mapping[str, Any]]]:
    frames: dict[str, tuple[bytes, Mapping[str, Any]]] = {}
    map_frame = generate_fixture(n2.MAP_FIXTURE)
    frames["MAP"] = (
        map_frame,
        {"kind": "map_fixture_frame", "workspace_relative_file": None, "sha256": _sha256(map_frame)},
    )
    for spec in n2.CELL_SPECS:
        loaded = n2._load_fixed_cell(spec)
        frames[spec.cell_id] = (
            loaded.frame,
            {
                "kind": "n2p_strict_final_png",
                "workspace_relative_file": str((spec.directory / "final.png").relative_to(n2.REPO_ROOT)).replace("\\", "/"),
                "sha256": spec.final_preview_sha256,
            },
        )
    return frames


def load_n8_action_snapshot(action_key: str) -> N8ActionSnapshot:
    if action_key not in FIXED_ACTION_SHA256S:
        raise N8ExecutionContractError("action key is not one of 15 frozen N8 actions")
    source = _source_manifest()
    row = next(item for item in _action_rows(source) if item["action_key"] == action_key)
    action = next(
        item for item in source["p0_campaign"]["actions"]
        if item["action_identity_sha256"] == row["action_identity_sha256"]
    )
    frame, preview = _loaded_frames()[row["frame_source_id"]]
    validate_frame(frame)
    frame_record = action["identity"]["frame"]
    controllers = []
    for record in frame_record["controllers"]:
        mapping = record["mapping"]
        stream = controller_stream(frame, ControllerMapping(**mapping))
        controllers.append((_sha256(stream), f"0x{fnv1a(stream):08X}"))
    if (
        _sha256(frame) != frame_record["sha256"]
        or f"0x{fnv1a(frame):08X}" != frame_record["fnv1a"]
        or controllers != [
            (record["dtm_sha256"], record["dtm_fnv1a"])
            for record in frame_record["controllers"]
        ]
    ):
        raise N8ExecutionContractError("frozen N8 frame/controller identity changed")
    return N8ActionSnapshot(
        key=action_key,
        sequence_id=row["sequence_id"],
        ordinal=row["ordinal"],
        role=row["role"],
        frame_source_id=row["frame_source_id"],
        power_mode=row["power_mode"],
        temperature_bin_id=row["temperature_bin_id"],
        campaign=source["p0_campaign"],
        action=action,
        frame=frame,
        reference_preview=preview,
    )


def build_n8_protocol_contract(
    snapshot: N8ActionSnapshot,
    *,
    prior_job_id: int,
    prior_operation_id: int,
    target_job_id: Optional[int] = None,
    target_operation_id: Optional[int] = None,
) -> _quality._RunContract:
    if snapshot.ordinal == 1:
        prior_frame = snapshot.action["identity"]["frame"]
    else:
        prior_sha = snapshot.action["identity"]["prior"][
            "action_identity_sha256"
        ]
        prior_matches = [
            action
            for action in snapshot.campaign["actions"]
            if action["action_identity_sha256"] == prior_sha
        ]
        if len(prior_matches) != 1:
            raise N8ExecutionContractError(
                "N8 protocol prior action is not unique in the campaign"
            )
        prior_frame = prior_matches[0]["identity"]["frame"]
    frame_record = snapshot.action["identity"]["frame"]
    candidate = _quality._CandidateSnapshot(
        directory=Path("."), manifest={"kind": "n8-runtime-frame", "action_key": snapshot.key},
        manifest_bytes=b"", manifest_file_sha256=EXPECTED_SOURCE_MANIFEST_FILE_SHA256,
        manifest_canonical_sha256=EXPECTED_SOURCE_MANIFEST_CANONICAL_SHA256,
        algorithm=snapshot.frame_source_id, frame=snapshot.frame,
        frame_sha256=frame_record["sha256"], frame_fnv1a=int(frame_record["fnv1a"], 16),
        controllers=tuple(frame_record["controllers"]),
    )
    return _quality._RunContract(
        snapshot=candidate,
        expected_prior_job_id=prior_job_id,
        expected_prior_operation_id=prior_operation_id,
        expected_prior_frame_sha256=prior_frame["sha256"],
        expected_prior_frame_fnv1a=int(prior_frame["fnv1a"], 16),
        expected_prior_cs1_dtm_fnv1a=int(prior_frame["controllers"][0]["dtm_fnv1a"], 16),
        expected_prior_cs2_dtm_fnv1a=int(prior_frame["controllers"][1]["dtm_fnv1a"], 16),
        expected_target_job_id=(
            _quality._next_nonzero_u32(prior_job_id) if target_job_id is None else target_job_id
        ),
        expected_target_operation_id=(
            _quality._next_nonzero_u32(prior_operation_id)
            if target_operation_id is None else target_operation_id
        ),
        action_identity=snapshot.action["identity"],
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        required_authorization_confirmation="bound-by-n8-runner",
    )


def _record_and_sha(bundle: Mapping[str, Any], name: str) -> tuple[Mapping[str, Any], str]:
    record = bundle[name]
    if not isinstance(record, Mapping):
        raise N8ExecutionContractError(f"bundle {name} must be an object")
    declared = _require_sha256(bundle[f"{name}_file_sha256"], label=f"bundle {name} SHA")
    actual = _sha256(record)
    if declared != actual:
        raise N8ExecutionContractError(f"bundle {name} whole-file SHA does not match")
    return record, actual


def _validate_dynamic_preflight(value: Any) -> tuple[int, int]:
    root = _exact(
        value,
        label="N8 dynamic first-action baseline",
        keys={"version", "job_raw", "diagnostic_raw", "gpio_status_raw", "controller_idle_no_inflight_confirmed"},
    )
    try:
        _quality._validate_version(root["version"], label="N8 warm dynamic baseline")
        gpio = _quality._validate_gpio_snapshot(root["gpio_status_raw"], label="N8 warm dynamic baseline GPIO")
    except _quality.Rc2gQualityRefreshError as error:
        raise N8ExecutionContractError(str(error)) from error
    if gpio != root["gpio_status_raw"] or root["controller_idle_no_inflight_confirmed"] is not True:
        raise N8ExecutionContractError("warm dynamic baseline is not confirmed idle")
    job = _exact(
        root["job_raw"], label="N8 warm baseline job",
        keys={"job_id", "action", "state", "result", "queued_at_ms", "started_at_ms", "finished_at_ms", "frame_fnv1a"},
    )
    job_id = job["job_id"]
    if type(job_id) is not int or not 0 <= job_id <= 0xFFFFFFFF or job["state"] not in {"idle", "completed"}:
        raise N8ExecutionContractError("warm baseline job is invalid or in flight")
    diagnostic = root["diagnostic_raw"]
    if job_id == 0:
        if job != {"job_id": 0, "action": "none", "state": "idle", "result": None, "queued_at_ms": 0, "started_at_ms": 0, "finished_at_ms": 0, "frame_fnv1a": 0} or diagnostic != {"schema_version": 2, "valid": False, "error": "no_completed_job_report"}:
            raise N8ExecutionContractError("warm zero baseline is not strict idle state")
        return 0, 0
    if job["state"] != "completed" or job["result"] is not True or not isinstance(diagnostic, Mapping):
        raise N8ExecutionContractError("warm nonzero baseline is not a completed idle job")
    operation_id = diagnostic.get("operation_id")
    if (
        type(operation_id) is not int or not 1 <= operation_id <= 0xFFFFFFFF
        or diagnostic.get("job_id") != job_id
        or diagnostic.get("job_operation_id") != operation_id
        or diagnostic.get("valid") is not True
        or diagnostic.get("running") is not False
        or diagnostic.get("sequence_ok") is not True
        or diagnostic.get("wait_timeout") is not False
        or diagnostic.get("busy_assertion_missing") is not False
        or diagnostic.get("mapping_applied") is not True
        or diagnostic.get("pon_busy_seen") is not True
        or diagnostic.get("drf_busy_seen") is not True
        or diagnostic.get("pof_busy_seen") is not True
        or diagnostic.get("firmware_build_tag") != _quality.EXPECTED_BUILD_TAG
        or diagnostic.get("driver_api_version") != _quality.EXPECTED_DRIVER_API
        or diagnostic.get("spi_hz") != _quality.EXPECTED_REFRESH_SPI_HZ
        or diagnostic.get("job_action") != "uploaded_frame"
        or diagnostic.get("job_state") != "completed"
        or diagnostic.get("job_result") is not True
        or diagnostic.get("timeout_stage") != "none"
        or diagnostic.get("busy_missing_stage") != "none"
    ):
        raise N8ExecutionContractError("warm nonzero baseline diagnostic identity is invalid")
    try:
        _quality._validate_timing(job, diagnostic, label="N8 warm baseline")
        wait_ms = {
            stage: int(diagnostic[f"{stage}_ms"])
            for stage in ("pon", "drf", "pof", "post_psr")
        }
        normalized_trace = _quality._validate_busy_trace(diagnostic, wait_ms)
        _quality._validate_normalized_busy_trace(
            normalized_trace, label="N8 warm baseline"
        )
    except (_quality.Rc2gQualityRefreshError, _quality.FrameToolError, KeyError, TypeError, ValueError) as error:
        raise N8ExecutionContractError(str(error)) from error
    return job_id, operation_id


def _validate_protocol(
    evidence: Mapping[str, Any],
    snapshot: N8ActionSnapshot,
    prior: Optional[Mapping[str, Any]],
    *,
    protocol_contract_builder: Any = build_n8_protocol_contract,
) -> tuple[int, int]:
    protocol = _exact(
        evidence["protocol_evidence"], label="N8 protocol evidence",
        keys={"preflight_mode", "preflight", "network_report", "target_job_raw", "target_diagnostic_raw", "target_diagnostic_validated", "post_refresh_gpio_status_raw", "completed_action"},
    )
    if snapshot.ordinal == 1 and snapshot.power_mode == "controller_fresh_boot":
        if protocol["preflight_mode"] != "controller_fresh_boot":
            raise N8ExecutionContractError("fresh-root preflight mode changed")
        fresh = protocol["preflight"]
        try:
            _map._validate_version(fresh["version"], label="N8 stored fresh boot")
            if fresh["job_raw"] != {"job_id": 0, "action": "none", "state": "idle", "result": None, "queued_at_ms": 0, "started_at_ms": 0, "finished_at_ms": 0, "frame_fnv1a": 0} or fresh["diagnostic_raw"] != {"schema_version": 2, "valid": False, "error": "no_completed_job_report"}:
                raise N8ExecutionContractError("fresh root is not job0/operation0")
            _map._validate_gpio_snapshot(fresh["gpio_status_raw"], label="N8 stored fresh GPIO")
        except (_map.Rc2gMapBaselineError, KeyError, TypeError) as error:
            raise N8ExecutionContractError(f"fresh-root replay failed: {error}") from error
        prior_job, prior_operation = 0, 0
    elif snapshot.ordinal == 1:
        if protocol["preflight_mode"] != "dynamic_first_action_baseline":
            raise N8ExecutionContractError("warm root lost its dynamic baseline")
        prior_job, prior_operation = _validate_dynamic_preflight(protocol["preflight"])
    else:
        if protocol["preflight_mode"] != "exact_finalized_prior" or prior is None:
            raise N8ExecutionContractError("dependent action lacks exact finalized prior")
        prior_completed = prior["evidence"]["protocol_evidence"]["completed_action"]
        prior_job = prior_completed["job_id"]
        prior_operation = prior_completed["operation_id"]
        run_contract = protocol_contract_builder(
            snapshot, prior_job_id=prior_job, prior_operation_id=prior_operation
        )
        live = protocol["preflight"]
        if (
            live.get("job") != prior_completed["job_raw"]
            or live.get("diagnostic_raw") != prior_completed["diagnostic_raw"]
            or live.get("expected_identity") != snapshot.action["identity"]["prior"]
        ):
            raise N8ExecutionContractError("dependent live prior differs from stored prior")
        try:
            trace = _quality._validate_prior_raw_diagnostic(
                live["diagnostic_raw"], live["job"], run_contract
            )
            if live.get("nested_busy_trace") != trace:
                raise N8ExecutionContractError("dependent prior BUSY trace changed")
            raw_gpio = _quality._validate_gpio_snapshot(live["gpio"]["raw"], label="N8 prior GPIO")
            if _quality._gpio_evidence(raw_gpio) != live["gpio"]:
                raise N8ExecutionContractError("dependent prior GPIO evidence changed")
            _quality._validate_version(live["version"], label="N8 dependent prior")
        except (_quality.Rc2gQualityRefreshError, KeyError, TypeError) as error:
            raise N8ExecutionContractError(f"dependent prior replay failed: {error}") from error
    run_contract = protocol_contract_builder(
        snapshot, prior_job_id=prior_job, prior_operation_id=prior_operation
    )
    try:
        _quality._validate_network_report(protocol["network_report"], run_contract)
        if protocol["target_job_raw"] != protocol["network_report"].get("job"):
            raise N8ExecutionContractError("target immutable job changed")
        normalized = _quality._validate_target_raw_diagnostic(
            protocol["target_diagnostic_raw"], protocol["network_report"], run_contract
        )
        if normalized != protocol["target_diagnostic_validated"]:
            raise N8ExecutionContractError("target diagnostic derived evidence changed")
        gpio = _quality._validate_gpio_snapshot(
            protocol["post_refresh_gpio_status_raw"], label="N8 target GPIO"
        )
        if gpio != protocol["post_refresh_gpio_status_raw"]:
            raise N8ExecutionContractError("target GPIO normalization changed")
    except (_quality.Rc2gQualityRefreshError, KeyError, TypeError) as error:
        raise N8ExecutionContractError(f"target protocol replay failed: {error}") from error
    completed = _exact(
        protocol["completed_action"], label="N8 completed action",
        keys={"job_id", "operation_id", "frame_sha256", "frame_fnv1a", "job_raw", "diagnostic_raw"},
    )
    if completed != {
        "job_id": run_contract.expected_target_job_id,
        "operation_id": run_contract.expected_target_operation_id,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "frame_fnv1a": snapshot.action["identity"]["frame"]["fnv1a"],
        "job_raw": protocol["target_job_raw"],
        "diagnostic_raw": protocol["target_diagnostic_raw"],
    }:
        raise N8ExecutionContractError("completed action identity changed")
    return run_contract.expected_target_job_id, run_contract.expected_target_operation_id


def _validate_observation(
    value: Mapping[str, Any], *, snapshot: N8ActionSnapshot,
    manifest: Mapping[str, Any], attempt_id: str, profile: Mapping[str, Any]
) -> Mapping[str, Any]:
    root = _exact(
        value, label="N8 stored observation",
        keys={"schema_version", "kind", "attempt_id", "action_key", "action_identity_sha256", "sequence_id", "ordinal", "role", "observed_at", "reference_preview_sha256", "visual", "electrical", "external_temperature", "continuity", "camera", "source_observation_file_sha256", "visual_pass", "electrical_pass", "thermal_pass", "temperature_bin_pass", "continuity_pass", "overall_state", "qualification_state"},
    )
    if (
        root["schema_version"] != SCHEMA_VERSION or root["kind"] != OBSERVATION_KIND
        or root["attempt_id"] != attempt_id or root["action_key"] != snapshot.key
        or root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or root["sequence_id"] != snapshot.sequence_id or root["ordinal"] != snapshot.ordinal
        or root["role"] != snapshot.role or root["reference_preview_sha256"] != snapshot.reference_preview["sha256"]
        or root["qualification_state"] != "NOT_QUALIFIED"
    ):
        raise N8ExecutionContractError("N8 observation binding changed")
    _timestamp(root["observed_at"], label="observation.observed_at")
    _require_sha256(root["source_observation_file_sha256"], label="source observation")
    visual = _exact(
        root["visual"], label="N8 visual",
        keys={"fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions", "ghosting_score", "artifact_severity_score"},
    )
    for field in ("fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions"):
        if type(visual[field]) is not bool:
            raise N8ExecutionContractError(f"visual {field} must be boolean")
    _number(visual["ghosting_score"], label="visual.ghosting_score", minimum=0)
    _number(visual["artifact_severity_score"], label="visual.artifact_severity_score", minimum=0)
    visual_pass = all(visual[field] for field in ("fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions"))

    electrical = _exact(
        root["electrical"], label="N8 electrical",
        keys={"meter_asset_sha256", "clock_asset_sha256", "pre_voltage_v", "pre_idle_current_a", "post_voltage_v", "post_idle_current_a", "peak_current_a", "constant_voltage_mode", "reviewed_limits_pass", "timing_ms"},
    )
    registry = manifest["measurement_registry"]
    if electrical["meter_asset_sha256"] != registry["electrical"]["meter_asset_sha256"] or electrical["clock_asset_sha256"] != registry["timing"]["clock_asset_sha256"]:
        raise N8ExecutionContractError("electrical/timing asset binding changed")
    for field in ("pre_voltage_v", "pre_idle_current_a", "post_voltage_v", "post_idle_current_a", "peak_current_a"):
        _number(electrical[field], label=f"electrical.{field}", minimum=0)
    if type(electrical["constant_voltage_mode"]) is not bool or type(electrical["reviewed_limits_pass"]) is not bool:
        raise N8ExecutionContractError("electrical verdict flags must be boolean")
    timing = _exact(electrical["timing_ms"], label="N8 timing", keys=_TIMING_FIELDS)
    for field, item in timing.items():
        _number(item, label=f"timing.{field}", minimum=0)
    electrical_pass = electrical["constant_voltage_mode"] and electrical["reviewed_limits_pass"]

    thermal = _exact(
        root["external_temperature"], label="N8 external temperature",
        keys={"pre_action_c", "post_action_c", "session_max_c", "uncertainty_u95_c", "sensor_asset_sha256", "calibration_artifact_sha256", "measurement_location_sha256", "measurement_evidence_sha256", "uncertainty_evidence_sha256"},
    )
    pre = _number(thermal["pre_action_c"], label="temperature.pre_action_c")
    post = _number(thermal["post_action_c"], label="temperature.post_action_c")
    maximum = _number(thermal["session_max_c"], label="temperature.session_max_c")
    u95 = _number(thermal["uncertainty_u95_c"], label="temperature.uncertainty_u95_c", minimum=0)
    if maximum < max(pre, post):
        raise N8ExecutionContractError("external session maximum is below a sample")
    external = registry["external_temperature"]
    if any(thermal[field] != external[field] for field in ("sensor_asset_sha256", "calibration_artifact_sha256", "measurement_location_sha256")) or u95 != float(external["uncertainty_u95_c"]):
        raise N8ExecutionContractError("external temperature asset/uncertainty binding changed")
    for field in ("measurement_evidence_sha256", "uncertainty_evidence_sha256"):
        _require_sha256(thermal[field], label=f"temperature.{field}")
    limits = profile["limits"]
    thermal_pass = (
        limits["minimum_start_temperature_c"] <= pre <= limits["maximum_start_temperature_c"]
        and post <= limits["maximum_post_refresh_temperature_c"]
        and maximum <= limits["maximum_post_refresh_temperature_c"]
    )
    temperature_bin_pass = True
    if snapshot.temperature_bin_id is not None:
        bin_record = next(item for item in manifest["temperature_bin_plan"]["bins"] if item["bin_id"] == snapshot.temperature_bin_id)
        temperature_bin_pass = bin_record["minimum_c"] <= pre <= bin_record["maximum_c"]

    if snapshot.ordinal == 1:
        if root["continuity"] is not None:
            raise N8ExecutionContractError("sequence root continuity must be null")
        continuity_pass = True
    else:
        continuity = _exact(
            root["continuity"], label="N8 continuity",
            keys={"controller_reboot_between_actions", "panel_power_cycle_between_actions", "j2_disconnect_between_actions", "other_visible_refresh_between_actions"},
        )
        if any(type(item) is not bool for item in continuity.values()):
            raise N8ExecutionContractError("continuity fields must be boolean")
        continuity_pass = not any(continuity.values())

    camera = _exact(
        root["camera"], label="N8 camera",
        keys={"capture_file_sha256", "capture_evidence_sha256", "body_asset_sha256", "lens_asset_sha256", "mount_asset_sha256", "fixed_exposure_profile_sha256", "crop_asset_sha256", "illumination_asset_sha256", "copied_file", "bytes", "decoded_format", "width", "height"},
    )
    registered_camera = registry["camera"]
    for field in ("body_asset_sha256", "lens_asset_sha256", "mount_asset_sha256", "fixed_exposure_profile_sha256", "crop_asset_sha256", "illumination_asset_sha256"):
        if camera[field] != registered_camera[field]:
            raise N8ExecutionContractError(f"camera {field} binding changed")
    for field in ("capture_file_sha256", "capture_evidence_sha256"):
        _require_sha256(camera[field], label=f"camera.{field}")
    if not isinstance(camera["copied_file"], str) or not camera["copied_file"] or type(camera["bytes"]) is not int or camera["bytes"] < 1 or not isinstance(camera["decoded_format"], str) or not camera["decoded_format"] or type(camera["width"]) is not int or camera["width"] < 1 or type(camera["height"]) is not int or camera["height"] < 1:
        raise N8ExecutionContractError("raw fixed-camera capture metadata is incomplete")

    state = ResultState.PASS.value if visual_pass and electrical_pass and thermal_pass and temperature_bin_pass and continuity_pass else ResultState.FAIL.value
    if (
        root["visual_pass"] is not visual_pass or root["electrical_pass"] is not electrical_pass
        or root["thermal_pass"] is not thermal_pass or root["temperature_bin_pass"] is not temperature_bin_pass
        or root["continuity_pass"] is not continuity_pass or root["overall_state"] != state
    ):
        raise N8ExecutionContractError("N8 observation derived verdict changed")
    return root


def _frozen_contract_snapshot_loader(
    _contract: Mapping[str, Any], action_key: str
) -> N8ActionSnapshot:
    """Default snapshot seam retained for the frozen legacy contract."""

    return load_n8_action_snapshot(action_key)


def _frozen_authorization_confirmation(
    _contract: Mapping[str, Any], snapshot: N8ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def _frozen_manifest_validator(
    manifest: Mapping[str, Any], _profile: Mapping[str, Any]
) -> Mapping[str, Any]:
    return validate_n8_runtime_manifest(manifest)


def _frozen_prior_action_key(
    _contract: Mapping[str, Any], snapshot: N8ActionSnapshot
) -> str:
    prior_sha = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    try:
        return next(key for key, sha in FIXED_ACTION_SHA256S.items() if sha == prior_sha)
    except StopIteration as error:  # pragma: no cover - frozen contract guards this
        raise N8ExecutionContractError("N8 prior action key is missing") from error


def _validate_n8_finalized_action_bundle_uncached(
    contract: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    expected_action_key: Optional[str] = None,
    _contract_validator: Any = validate_n8_execution_contract,
    _snapshot_loader: Any = _frozen_contract_snapshot_loader,
    _contract_file_sha256: Any = execution_contract_file_sha256,
    _authorization_confirmation: Any = _frozen_authorization_confirmation,
    _manifest_validator: Any = _frozen_manifest_validator,
    _protocol_contract_builder: Any = build_n8_protocol_contract,
    _prior_action_key_resolver: Any = _frozen_prior_action_key,
    _runner_kind: str = RUNNER_KIND,
    _record_extra_keys: Optional[
        Mapping[str, set[str] | frozenset[str]]
    ] = None,
    _record_extension_validator: Any = None,
) -> dict[str, Any]:
    """Recursively deep-validate one finalized N8 action and its exact chain.

    Underscored callables are a fail-closed adapter seam for a separately
    validated physical contract.  The public frozen path supplies none of
    them and therefore retains the exact legacy identities and validators.
    """

    fixed = _contract_validator(contract)
    extra_keys = _record_extra_keys or {}
    root = _exact(
        bundle, label="N8 finalized bundle",
        keys={"schema_version", "kind", *(
            item for name in _BUNDLE_RECORDS for item in (name, f"{name}_file_sha256")
        ), "prior_bundle", "prior_bundle_file_sha256", "qualification_state"},
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != BUNDLE_KIND or root["qualification_state"] != "NOT_QUALIFIED":
        raise N8ExecutionContractError("N8 finalized bundle identity/qualification changed")
    records = {name: _record_and_sha(root, name) for name in _BUNDLE_RECORDS}
    manifest, manifest_sha = records["manifest"]
    claim, claim_sha = records["claim"]
    lock, lock_sha = records["lock"]
    profile, profile_sha = records["profile"]
    evidence, evidence_sha = records["evidence"]
    observation, observation_sha = records["observation"]
    finalization, finalization_sha = records["finalization"]
    result, result_sha = records["result"]
    runtime = _manifest_validator(manifest, profile)
    validated_profile = validate_limit_profile(profile)
    if profile != runtime["limit_profile"] or profile_sha != _sha256(runtime["limit_profile"]):
        raise N8ExecutionContractError("bundle profile differs from runtime manifest")

    evidence_root = _exact(
        evidence, label="N8 protocol evidence",
        keys={"schema_version", "kind", "runner_kind", "attempt_id", "recorded_at", "protocol_completed_at", "profile_evaluated_at", "action_key", "action_identity_sha256", "sequence_id", "ordinal", "role", "frame_sha256", "reference_preview", "execution_contract_canonical_sha256", "execution_contract_file_sha256", "runtime_manifest_canonical_sha256", "runtime_manifest_file_sha256", "profile_canonical_sha256", "profile_file_sha256", "claim", "prior_bundle_file_sha256", "prior_finalization_file_sha256", "prior_result_file_sha256", "start_external_temperature_c", "maximum_post_requests", "automatic_retry_count", "retry_allowed", "recovery_performed", "outcome", "protocol_verified", "protocol_evidence", "request_audit", "error", "qualification_state"} | set(extra_keys.get("evidence", ())),
    )
    action_key = evidence_root["action_key"]
    if expected_action_key is not None and action_key != expected_action_key:
        raise N8ExecutionContractError("bundle is not the expected N8 action")
    snapshot = _snapshot_loader(fixed, str(action_key))
    attempt_id = evidence_root["attempt_id"]
    if not isinstance(attempt_id, str) or not attempt_id:
        raise N8ExecutionContractError("attempt_id is invalid")
    recorded = _timestamp(evidence_root["recorded_at"], label="evidence.recorded_at")
    evaluated = _timestamp(evidence_root["profile_evaluated_at"], label="evidence.profile_evaluated_at")
    completed = _timestamp(evidence_root["protocol_completed_at"], label="evidence.protocol_completed_at")
    if evaluated > recorded or completed < recorded:
        raise N8ExecutionContractError("profile/claim/protocol timestamp order changed")
    try:
        decision = evaluate_limit_profile(validated_profile, evaluated_at=evidence_root["profile_evaluated_at"])
    except CampaignContractError as error:
        raise N8ExecutionContractError(f"profile evaluation failed: {error}") from error
    if not decision.hardware_ready:
        raise N8ExecutionContractError("stored profile was not ready at evaluation time")
    if (
        evidence_root["schema_version"] != SCHEMA_VERSION or evidence_root["kind"] != EVIDENCE_KIND
        or evidence_root["runner_kind"] != _runner_kind or evidence_root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or evidence_root["sequence_id"] != snapshot.sequence_id or evidence_root["ordinal"] != snapshot.ordinal or evidence_root["role"] != snapshot.role
        or evidence_root["frame_sha256"] != snapshot.action["identity"]["frame"]["sha256"] or evidence_root["reference_preview"] != snapshot.reference_preview
        or evidence_root["execution_contract_canonical_sha256"] != fixed["integrity"]["canonical_sha256"]
        or evidence_root["execution_contract_file_sha256"] != _contract_file_sha256(fixed)
        or evidence_root["runtime_manifest_canonical_sha256"] != runtime["integrity"]["canonical_sha256"] or evidence_root["runtime_manifest_file_sha256"] != manifest_sha
        or evidence_root["profile_canonical_sha256"] != validated_profile["integrity"]["canonical_sha256"] or evidence_root["profile_file_sha256"] != profile_sha
        or evidence_root["maximum_post_requests"] != 1 or evidence_root["automatic_retry_count"] != 0 or evidence_root["retry_allowed"] is not False or evidence_root["recovery_performed"] is not False
        or evidence_root["outcome"] != "protocol_verified_observation_pending" or evidence_root["protocol_verified"] is not True or evidence_root["error"] is not None or evidence_root["qualification_state"] != "NOT_QUALIFIED"
    ):
        raise N8ExecutionContractError("N8 protocol evidence binding changed")
    start_temp = _number(evidence_root["start_external_temperature_c"], label="start external temperature")
    if not validated_profile["limits"]["minimum_start_temperature_c"] <= start_temp <= validated_profile["limits"]["maximum_start_temperature_c"]:
        raise N8ExecutionContractError("claimed start temperature is outside reviewed limits")

    prior_bundle: Optional[Mapping[str, Any]] = None
    prior_validated: Optional[Mapping[str, Any]] = None
    if snapshot.ordinal == 1:
        if root["prior_bundle"] is not None or root["prior_bundle_file_sha256"] is not None:
            raise N8ExecutionContractError("N8 sequence root unexpectedly binds prior bundle")
    else:
        if not isinstance(root["prior_bundle"], Mapping):
            raise N8ExecutionContractError("dependent N8 action lacks embedded prior bundle")
        prior_bundle = root["prior_bundle"]
        prior_bundle_sha = _sha256(prior_bundle)
        if root["prior_bundle_file_sha256"] != prior_bundle_sha:
            raise N8ExecutionContractError("prior bundle whole-file SHA changed")
        prior_key = _prior_action_key_resolver(fixed, snapshot)
        prior_validated = _validate_n8_finalized_action_bundle_uncached(
            fixed,
            prior_bundle,
            expected_action_key=prior_key,
            _contract_validator=_contract_validator,
            _snapshot_loader=_snapshot_loader,
            _contract_file_sha256=_contract_file_sha256,
            _authorization_confirmation=_authorization_confirmation,
            _manifest_validator=_manifest_validator,
            _protocol_contract_builder=_protocol_contract_builder,
            _prior_action_key_resolver=_prior_action_key_resolver,
            _runner_kind=_runner_kind,
            _record_extra_keys=_record_extra_keys,
            _record_extension_validator=_record_extension_validator,
        )
        if prior_validated["state"] != ResultState.PASS.value:
            raise N8ExecutionContractError("dependent prior finalized bundle is not PASS")

    expected_prior_bundle_sha = _sha256(prior_bundle) if prior_bundle is not None else None
    expected_prior_finalization_sha = prior_validated["finalization_file_sha256"] if prior_validated else None
    expected_prior_result_sha = prior_validated["result_file_sha256"] if prior_validated else None
    for record, label in ((claim, "claim"), (evidence_root, "evidence"), (finalization, "finalization")):
        if (
            record["prior_bundle_file_sha256"] != expected_prior_bundle_sha
            or record["prior_finalization_file_sha256"] != expected_prior_finalization_sha
            or record["prior_result_file_sha256"] != expected_prior_result_sha
        ):
            raise N8ExecutionContractError(f"{label} exact prior whole-file SHA binding changed")

    claim_root = _exact(
        claim, label="N8 claim",
        keys={"schema_version", "kind", "registry_id", "action_key", "action_identity_sha256", "execution_contract_canonical_sha256", "runtime_manifest_file_sha256", "attempt_id", "claimed_at", "state", "authorization_consumed_permanently", "authorization_confirmation_sha256", "profile_canonical_sha256", "profile_file_sha256", "prior_bundle_file_sha256", "prior_finalization_file_sha256", "prior_result_file_sha256", "start_external_temperature_c", "confirmations", "result_directory", "maximum_post_requests", "automatic_retry_authorized", "automatic_recovery_authorized"} | set(extra_keys.get("claim", ())),
    )
    confirmation = _authorization_confirmation(fixed, snapshot)
    expected_confirmation_sha = _sha256(confirmation.encode("ascii"))
    root_specific = (
        {"controller_fresh_boot"} if snapshot.ordinal == 1 and snapshot.power_mode == "controller_fresh_boot"
        else {"controller_idle_no_inflight_job", "supervised_continuous_session_start"} if snapshot.ordinal == 1
        else {"prior_screen_fidelity_pass", "esp32_not_restarted_between_actions", "no_j2_disconnect_between_actions", "no_panel_power_cycle_between_actions", "no_other_visible_refresh_between_actions"}
    )
    confirmations = _exact(
        claim_root["confirmations"], label="N8 confirmations",
        keys={"reviewed_panel_and_build", "supervised_supply_cv_current_normal", "physical_cutoff_available", "single_visible_refresh", "external_temperature_instrument_verified", "fixed_camera_ready", *root_specific},
    )
    if any(type(item) is not bool or item is not True for item in confirmations.values()):
        raise N8ExecutionContractError("all N8 physical confirmations must be true")
    if (
        claim_root["schema_version"] != SCHEMA_VERSION or claim_root["kind"] != CLAIM_KIND or claim_root["registry_id"] != CLAIM_REGISTRY_ID
        or claim_root["action_key"] != action_key or claim_root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or claim_root["execution_contract_canonical_sha256"] != fixed["integrity"]["canonical_sha256"] or claim_root["runtime_manifest_file_sha256"] != manifest_sha
        or claim_root["attempt_id"] != attempt_id or _timestamp(claim_root["claimed_at"], label="claim.claimed_at") != recorded
        or claim_root["state"] != "authorization_permanently_consumed_do_not_rerun" or claim_root["authorization_consumed_permanently"] is not True
        or claim_root["authorization_confirmation_sha256"] != expected_confirmation_sha
        or claim_root["profile_canonical_sha256"] != validated_profile["integrity"]["canonical_sha256"] or claim_root["profile_file_sha256"] != profile_sha
        or float(claim_root["start_external_temperature_c"]) != start_temp or claim_root["maximum_post_requests"] != 1
        or claim_root["automatic_retry_authorized"] is not False or claim_root["automatic_recovery_authorized"] is not False
    ):
        raise N8ExecutionContractError("N8 consumed claim binding changed")
    claim_reference = {"registry_id": CLAIM_REGISTRY_ID, "filename": f"{snapshot.action['action_identity_sha256']}.json", "file_sha256": claim_sha, "attempt_id": attempt_id, "action_identity_sha256": snapshot.action["action_identity_sha256"], "state": "authorization_permanently_consumed_do_not_rerun"}
    if evidence_root["claim"] != claim_reference:
        raise N8ExecutionContractError("N8 claim reference changed")
    lock_root = _exact(
        lock, label="N8 lock",
        keys={"schema_version", "kind", "execution_contract_canonical_sha256", "attempt_id", "action_key", "action_identity_sha256", "claim", "confirmations", "authorization_confirmation_sha256", "state", "automatic_retry_authorized", "automatic_recovery_authorized"} | set(extra_keys.get("lock", ())),
    )
    expected_lock = {"schema_version": SCHEMA_VERSION, "kind": LOCK_KIND, "execution_contract_canonical_sha256": fixed["integrity"]["canonical_sha256"], "attempt_id": attempt_id, "action_key": action_key, "action_identity_sha256": snapshot.action["action_identity_sha256"], "claim": claim_reference, "confirmations": confirmations, "authorization_confirmation_sha256": expected_confirmation_sha, "state": "authorization_permanently_consumed_do_not_rerun", "automatic_retry_authorized": False, "automatic_recovery_authorized": False}
    if any(
        lock_root.get(key) != value for key, value in expected_lock.items()
    ):
        raise N8ExecutionContractError("N8 action lock binding changed")
    audit = _exact(evidence_root["request_audit"], label="N8 request audit", keys={"post_attempt_count", "post_issued_count", "calls"})
    posts = [item for item in audit["calls"] if isinstance(item, Mapping) and item.get("method") == "POST"] if isinstance(audit["calls"], list) else []
    if audit["post_attempt_count"] != 1 or audit["post_issued_count"] != 1 or len(posts) != 1 or posts[0].get("endpoint") != "/api/frame" or posts[0].get("request_sha256") != snapshot.action["identity"]["frame"]["sha256"]:
        raise N8ExecutionContractError("N8 request audit is not exactly one frozen frame POST")
    if any((item.get("method"), item.get("endpoint")) not in {("GET", "/api/version"), ("GET", "/api/job"), ("GET", "/api/diagnostic/report"), ("GET", "/api/diagnostic/status"), ("POST", "/api/frame")} for item in audit["calls"] if isinstance(item, Mapping)):
        raise N8ExecutionContractError("N8 request audit contains a forbidden route")

    _validate_protocol(
        evidence_root,
        snapshot,
        prior_bundle,
        protocol_contract_builder=_protocol_contract_builder,
    )
    observation_root = _validate_observation(
        observation, snapshot=snapshot, manifest=runtime, attempt_id=attempt_id, profile=validated_profile
    )
    if _timestamp(observation_root["observed_at"], label="observation.observed_at") < completed:
        raise N8ExecutionContractError("manual observation predates protocol completion")
    final_root = _exact(
        finalization, label="N8 finalization",
        keys={"schema_version", "kind", "attempt_id", "action_key", "action_identity_sha256", "sequence_id", "ordinal", "state", "manifest_file_sha256", "claim_file_sha256", "lock_file_sha256", "profile_file_sha256", "protocol_evidence_file_sha256", "action_observation_file_sha256", "prior_bundle_file_sha256", "prior_finalization_file_sha256", "prior_result_file_sha256", "visual_pass", "electrical_pass", "thermal_pass", "temperature_bin_pass", "continuity_pass", "camera_capture_file_sha256", "visual_electrical_thermal_continuity_assessed_separately", "automatic_retry_count", "retry_allowed", "recovery_performed", "qualification_state"} | set(extra_keys.get("finalization", ())),
    )
    if (
        final_root["schema_version"] != SCHEMA_VERSION or final_root["kind"] != FINALIZATION_KIND or final_root["attempt_id"] != attempt_id
        or final_root["action_key"] != action_key or final_root["action_identity_sha256"] != snapshot.action["action_identity_sha256"] or final_root["sequence_id"] != snapshot.sequence_id or final_root["ordinal"] != snapshot.ordinal
        or final_root["state"] != observation_root["overall_state"] or final_root["manifest_file_sha256"] != manifest_sha or final_root["claim_file_sha256"] != claim_sha or final_root["lock_file_sha256"] != lock_sha or final_root["profile_file_sha256"] != profile_sha or final_root["protocol_evidence_file_sha256"] != evidence_sha or final_root["action_observation_file_sha256"] != observation_sha
        or final_root["visual_pass"] is not observation_root["visual_pass"] or final_root["electrical_pass"] is not observation_root["electrical_pass"] or final_root["thermal_pass"] is not observation_root["thermal_pass"] or final_root["temperature_bin_pass"] is not observation_root["temperature_bin_pass"] or final_root["continuity_pass"] is not observation_root["continuity_pass"]
        or final_root["camera_capture_file_sha256"] != observation_root["camera"]["capture_file_sha256"] or final_root["visual_electrical_thermal_continuity_assessed_separately"] is not True
        or final_root["automatic_retry_count"] != 0 or final_root["retry_allowed"] is not False or final_root["recovery_performed"] is not False or final_root["qualification_state"] != "NOT_QUALIFIED"
    ):
        raise N8ExecutionContractError("N8 finalization binding changed")
    try:
        result_root = validate_result_record(result)
    except CampaignContractError as error:
        raise N8ExecutionContractError(f"N8 result is invalid: {error}") from error
    if (
        result_file_sha256(result_root) != result_sha or result_root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or result_root["state"] != final_root["state"] or _timestamp(result_root["completed_at"], label="result.completed_at") != _timestamp(observation_root["observed_at"], label="observation.observed_at")
        or result_root["evidence_manifest_sha256"] != finalization_sha or result_root["post_request_count"] != 1
    ):
        raise N8ExecutionContractError("N8 result/finalization binding changed")
    if _record_extension_validator is not None:
        _record_extension_validator(
            fixed,
            snapshot,
            {
                "manifest": manifest,
                "claim": claim_root,
                "lock": lock_root,
                "profile": validated_profile,
                "evidence": evidence_root,
                "observation": observation_root,
                "finalization": final_root,
                "result": result_root,
            },
        )
    return {
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "state": result_root["state"],
        "manifest_file_sha256": manifest_sha,
        "claim_file_sha256": claim_sha,
        "lock_file_sha256": lock_sha,
        "profile_file_sha256": profile_sha,
        "evidence_file_sha256": evidence_sha,
        "observation_file_sha256": observation_sha,
        "finalization_file_sha256": finalization_sha,
        "result_file_sha256": result_sha,
        "prior_bundle_file_sha256": expected_prior_bundle_sha,
        "prior_finalization_file_sha256": expected_prior_finalization_sha,
        "prior_result_file_sha256": expected_prior_result_sha,
        "completed_job_id": evidence_root["protocol_evidence"]["completed_action"]["job_id"],
        "completed_operation_id": evidence_root["protocol_evidence"]["completed_action"]["operation_id"],
        "observation": _snapshot(observation_root),
        "result": _snapshot(result_root),
        "execution_evidence_verified": True,
        "qualification_state": "NOT_QUALIFIED",
    }


@lru_cache(maxsize=256)
def _validate_n8_bundle_payloads(
    contract_payload: bytes,
    bundle_payload: bytes,
    expected_action_key: Optional[str],
) -> Mapping[str, Any]:
    try:
        contract = json.loads(contract_payload.decode("utf-8"))
        bundle = json.loads(bundle_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:  # pragma: no cover
        raise N8ExecutionContractError("cached bundle payload is not canonical JSON") from error
    return _validate_n8_finalized_action_bundle_uncached(
        contract,
        bundle,
        expected_action_key=expected_action_key,
    )


def validate_n8_finalized_action_bundle(
    contract: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    expected_action_key: Optional[str] = None,
    _contract_validator: Any = validate_n8_execution_contract,
    _snapshot_loader: Any = _frozen_contract_snapshot_loader,
    _contract_file_sha256: Any = execution_contract_file_sha256,
    _authorization_confirmation: Any = _frozen_authorization_confirmation,
    _manifest_validator: Any = _frozen_manifest_validator,
    _protocol_contract_builder: Any = build_n8_protocol_contract,
    _prior_action_key_resolver: Any = _frozen_prior_action_key,
    _runner_kind: str = RUNNER_KIND,
    _record_extra_keys: Optional[
        Mapping[str, set[str] | frozenset[str]]
    ] = None,
    _record_extension_validator: Any = None,
) -> dict[str, Any]:
    """Deep-validate one bundle with a byte-keyed immutable replay cache.

    Non-default underscored adapters bypass the legacy-only cache and are
    intended solely for a separately validated physical execution wrapper.
    """

    try:
        contract_payload = canonical_json_bytes(contract)
        bundle_payload = canonical_json_bytes(bundle)
    except CampaignContractError as error:
        raise N8ExecutionContractError(f"bundle cannot be canonicalized: {error}") from error
    adapters_are_frozen = (
        _contract_validator is validate_n8_execution_contract
        and _snapshot_loader is _frozen_contract_snapshot_loader
        and _contract_file_sha256 is execution_contract_file_sha256
        and _authorization_confirmation is _frozen_authorization_confirmation
        and _manifest_validator is _frozen_manifest_validator
        and _protocol_contract_builder is build_n8_protocol_contract
        and _prior_action_key_resolver is _frozen_prior_action_key
        and _runner_kind == RUNNER_KIND
        and _record_extra_keys is None
        and _record_extension_validator is None
    )
    if adapters_are_frozen:
        validated = _validate_n8_bundle_payloads(
            contract_payload,
            bundle_payload,
            expected_action_key,
        )
    else:
        validated = _validate_n8_finalized_action_bundle_uncached(
            contract,
            bundle,
            expected_action_key=expected_action_key,
            _contract_validator=_contract_validator,
            _snapshot_loader=_snapshot_loader,
            _contract_file_sha256=_contract_file_sha256,
            _authorization_confirmation=_authorization_confirmation,
            _manifest_validator=_manifest_validator,
            _protocol_contract_builder=_protocol_contract_builder,
            _prior_action_key_resolver=_prior_action_key_resolver,
            _runner_kind=_runner_kind,
            _record_extra_keys=_record_extra_keys,
            _record_extension_validator=_record_extension_validator,
        )
    return _snapshot(validated)


__all__ = [
    "AUTHORIZATION_PREFIX", "AUTHORIZATION_SUFFIX", "BUNDLE_FILENAME", "BUNDLE_KIND",
    "CAMERA_CAPTURE_FILENAME", "CLAIM_KIND", "CONTRACT_ID", "CONTRACT_KIND",
    "EVIDENCE_FILENAME", "EVIDENCE_KIND", "EXPECTED_CONTRACT_CANONICAL_SHA256",
    "EXPECTED_CONTRACT_FILE_SHA256", "FINALIZATION_FILENAME", "FINALIZATION_KIND",
    "FIXED_ACTION_KEYS", "FIXED_ACTION_SHA256S", "LOCK_FILENAME", "LOCK_KIND",
    "MANIFEST_FILENAME", "N8ActionSnapshot", "N8ExecutionContractError",
    "OBSERVATION_FILENAME", "OBSERVATION_KIND", "P0_RESULT_FILENAME", "PROFILE_FILENAME",
    "RUNNER_KIND", "build_n8_protocol_contract", "compile_n8_execution_contract",
    "execution_contract_file_sha256", "load_n8_action_snapshot",
    "validate_n8_execution_contract", "validate_n8_finalized_action_bundle",
    "validate_n8_runtime_manifest",
]
