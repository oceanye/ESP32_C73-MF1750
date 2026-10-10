#!/usr/bin/env python3
"""Rebind the dither Atlas start gate to the post-C23 clean-white containment.

The frozen dither firmware, frame identities, action IDs, NVS namespace,
one-shot transport, claims, and Atlas-to-white ordinal-2 gate are unchanged.
Only ordinal 1's stale August-10 matrix-white predecessor is superseded by the
exact finalized standalone clean-white containment produced after the C23 DRF
fault.  A fresh same-boot J2-OFF diagnostic and a live no-intervening-refresh
confirmation remain mandatory.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat
import sys
from typing import Any, Final, Mapping, Sequence


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_physical_once as engine  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_physical_once as physical  # noqa: E402


RELEASE_FILE: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1"
    / "dither-color-atlas-real-release.json"
)
CONTAINMENT_DIR: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C23_FAULT_WHITE_CONTAINMENT_VISIBLE_20260817_V1"
)
FINAL_FILE: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C23_FAULT_WHITE_CONTAINMENT_FINAL_20260818_V1"
    / "c23-fault-containment-final.json"
)
RESULT_FILE: Final = CONTAINMENT_DIR / "white-containment-once-result.json"
OBSERVATION_FILE: Final = CONTAINMENT_DIR / "white-containment-manual-observation.json"
CLAIM_FILE: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_empirical_h3_claims"
    / "WF23_25-02-4acae8345b3084657c50f1babc1a5fc3f91898e0b5c64ee6be67459d730c9856.json"
)

EXPECTED_RELEASE_FILE_SHA256: Final = (
    "ec3e2d873badadef615b06b6a30948738ef80a4c4c3e31cbe24344454a037612"
)
EXPECTED_RELEASE_CANONICAL_SHA256: Final = (
    "68c5ffd09a9a46644e59493a985d21c2a035c5e21aba3324355ebd2eab5df7fe"
)
EXPECTED_ATLAS_ACTION_ID: Final = (
    "ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c"
)
EXPECTED_WHITE_ACTION_ID: Final = (
    "35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3"
)
EXPECTED_CONTAINMENT_ACTION_ID: Final = (
    "4acae8345b3084657c50f1babc1a5fc3f91898e0b5c64ee6be67459d730c9856"
)
EXPECTED_CONTAINMENT_RELEASE_ID: Final = (
    "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4"
)

# file SHA-256, canonical SHA-256
BOUND_IDENTITIES: Final = {
    "final": (
        FINAL_FILE,
        "877dab531f864cb128491d887138457d4acf2c02fe97a0228c402faa5b5880ed",
        "956958a614b445f84597fd79eeb8d405335f346739def22bc96c94b50d1c43be",
    ),
    "result": (
        RESULT_FILE,
        "13028eae8caa53a17d1ffdad447fbf7b2c3fc8bc7f966784bc11b9809f4dbe98",
        "d3c550d190b5486b188a1fe2a06d38528dad54b8e495499facf139ec6cb5cd44",
    ),
    "observation": (
        OBSERVATION_FILE,
        "ca29ad5e45f922fe8abd6ed2e428e80b88956d1488044a94d52ad3245ba68a35",
        "920778f541aa3c0c62c3b36ba7933251af5b8be53dc49d5320bc5dc513477db1",
    ),
    "claim": (
        CLAIM_FILE,
        "0a5944881b618f75400204451fbb59a85e48c9952f6a23cc6c89aa7d382d707b",
        "9b99a9fe8210cb707cd74c3e561422084d962e69332b17520998f96c38b19b17",
    ),
}

_ORIGINAL_PRIOR_GATE = physical._dither_prior_gate  # noqa: SLF001
_ORIGINAL_DESCRIBE = physical._dither_describe  # noqa: SLF001
_ORIGINAL_VALIDATE_VERSION = engine._validate_version  # noqa: SLF001
_ORIGINAL_VALIDATE_MANIFEST = engine._validate_manifest  # noqa: SLF001


def _expected_nvs_contract() -> dict[str, Any]:
    return {
        "namespace": "mf1750_dca",
        "key": "cursor_v1",
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 3,
    }


def _expected_static_device_anchor() -> dict[str, Any]:
    """Return the firmware's immutable historical anchor declaration."""

    return {
        "campaign_id": "EC5_OTP_TRANSITION_MATRIX_CAMPAIGN_V1",
        "ordinal": 3,
        "role": "OTP_WHITE_RECOVERY",
        "action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
        "result_sha256": campaign.EXPECTED_MATRIX_RESULT_FILE_SHA256,
        "observation_sha256": campaign.EXPECTED_MATRIX_OBSERVATION_FILE_SHA256,
        "claim_sha256": campaign.EXPECTED_MATRIX_CLAIM_FILE_SHA256,
        "validated_by_device": False,
        "required_host_gate_for_ordinal_1": True,
    }


def _dither_validate_version(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("kind") != (
        f"{physical.DEVICE_KIND_PREFIX}-version"
    ):
        return _ORIGINAL_VALIDATE_VERSION(value)
    root = engine._identity(  # noqa: SLF001
        value,
        kind=f"{physical.DEVICE_KIND_PREFIX}-version",
        label="device version",
    )
    required = {
        "classification",
        "layout_id",
        "driver_api_version",
        "profile_source",
        "action_count",
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "runtime_lut_write",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "single_pixel_multi_pigment_claim",
        "physical_colour_claim",
        "retry",
        "recovery",
        "nvs_contract",
        "external_clean_white_anchor",
    }
    engine._keys(root, required, label="device dither version")  # noqa: SLF001
    if (
        root["classification"] != physical.contract.CLASSIFICATION
        or root["layout_id"] != physical.contract.LAYOUT_ID
        or root["driver_api_version"] != "MF1750_R16_CASCADE_V3"
        or root["profile_source"] != "factory_otp"
        or root["action_count"] != campaign.ACTION_COUNT
        or root["nvs_contract"] != _expected_nvs_contract()
        or root["external_clean_white_anchor"] != _expected_static_device_anchor()
    ):
        raise physical.DitherColorAtlasPhysicalError(
            "device dither version identity differs"
        )
    false_fields = (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "runtime_lut_write",
        "electrical_parameter_write",
        "single_pixel_multi_pigment_claim",
        "physical_colour_claim",
        "retry",
        "recovery",
    )
    if any(root[key] is not False for key in false_fields):
        raise physical.DitherColorAtlasPhysicalError(
            "device dither version false safety fields differ"
        )
    if root["dither"] is not True or root["spatial_mixing"] is not True:
        raise physical.DitherColorAtlasPhysicalError(
            "device dither version spatial-mixing fields differ"
        )
    return root


def _dither_validate_manifest(
    value: Any, actions: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("kind") != (
        f"{physical.DEVICE_KIND_PREFIX}-manifest"
    ):
        return _ORIGINAL_VALIDATE_MANIFEST(value, actions)
    root = engine._identity(  # noqa: SLF001
        value,
        kind=f"{physical.DEVICE_KIND_PREFIX}-manifest",
        label="device manifest",
    )
    device_actions = root.get("actions")
    expected_layout = {
        "controller_count": 2,
        "rows": 7,
        "columns": 5,
        "rois_per_controller": 35,
        "roi_count": 70,
        "controller_halves_semantically_identical": True,
        "controller_pattern_phase_identical": True,
        "mask": "bayer-2x2-quarter-area",
        "middle_column": "one-pixel-50-50-checkerboard",
        "appearance_names_are_hypotheses": True,
        "grid_x0_local": 26,
        "grid_x1_local": 486,
        "grid_y0": 34,
        "grid_y1": 570,
        "cell_width": 84,
        "cell_height": 68,
        "column_gap": 10,
        "row_gap": 10,
    }
    expected_actions = [engine._device_action(action) for action in actions]  # noqa: SLF001
    if (
        root.get("classification") != physical.contract.CLASSIFICATION
        or root.get("layout_id") != physical.contract.LAYOUT_ID
        or root.get("profile_source") != "factory_otp"
        or root.get("action_count") != campaign.ACTION_COUNT
        or root.get("round_count") != 1
        or device_actions != expected_actions
        or root.get("nvs_contract") != _expected_nvs_contract()
        or root.get("dither_layout") != expected_layout
        or root.get("external_clean_white_anchor") != _expected_static_device_anchor()
    ):
        raise physical.DitherColorAtlasPhysicalError(
            "device dither manifest identity differs"
        )
    false_fields = (
        "custom_lut_or_waveform",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "runtime_lut_write",
        "electrical_parameter_write",
        "single_pixel_multi_pigment_claim",
        "physical_colour_claim",
        "retry",
        "recovery",
    )
    true_fields = (
        "factory_otp",
        "synchronous_both_controllers",
        "one_driver_call_per_action",
        "dither",
        "spatial_mixing",
    )
    if any(root.get(key) is not False for key in false_fields) or any(
        root.get(key) is not True for key in true_fields
    ):
        raise physical.DitherColorAtlasPhysicalError(
            "device dither manifest safety fields differ"
        )
    return root


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _strict_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise physical.DitherColorAtlasPhysicalError(
                f"{label} must be a regular non-symlink"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise physical.DitherColorAtlasPhysicalError(
            f"{label} cannot be read: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise physical.DitherColorAtlasPhysicalError(f"{label} changed while read")
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise physical.DitherColorAtlasPhysicalError(
            f"{label} is not strict UTF-8 JSON"
        ) from error
    if not isinstance(root, Mapping):
        raise physical.DitherColorAtlasPhysicalError(f"{label} root is not an object")
    return payload, root


def _canonical_sha256(root: Mapping[str, Any], *, label: str) -> str:
    integrity = root.get("integrity")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    expected = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": campaign.sha256(unsigned),
    }
    if not isinstance(integrity, Mapping) or dict(integrity) != expected:
        raise physical.DitherColorAtlasPhysicalError(f"{label} integrity differs")
    return str(integrity["canonical_sha256"])


def validate_containment_evidence() -> str:
    """Deep-check the exact successful clean-white containment evidence."""

    roots: dict[str, Mapping[str, Any]] = {}
    for label, (path, wanted_file, wanted_canonical) in BOUND_IDENTITIES.items():
        payload, root = _strict_json(path, label=label)
        if (
            campaign.sha256(payload) != wanted_file
            or _canonical_sha256(root, label=label) != wanted_canonical
        ):
            raise physical.DitherColorAtlasPhysicalError(
                f"bound containment {label} identity differs"
            )
        roots[label] = root

    final = roots["final"]
    result = roots["result"]
    observation = roots["observation"]
    claim = roots["claim"]
    standalone = final.get("standalone_white_containment")
    boundaries = final.get("evidence_boundaries")
    electrical = observation.get("electrical")
    visual = observation.get("visual")
    classification = observation.get("classification")
    if (
        not isinstance(standalone, Mapping)
        or not isinstance(boundaries, Mapping)
        or not isinstance(electrical, Mapping)
        or not isinstance(visual, Mapping)
        or not isinstance(classification, Mapping)
        or final.get("state")
        != "C23_ATLAS_OBSERVED__PLANNED_WHITE_FAULT__STANDALONE_WHITE_CONTAINMENT_SUCCESS"
        or standalone.get("release_id") != EXPECTED_CONTAINMENT_RELEASE_ID
        or standalone.get("action_id") != EXPECTED_CONTAINMENT_ACTION_ID
        or standalone.get("result_file_sha256") != BOUND_IDENTITIES["result"][1]
        or standalone.get("observation_file_sha256")
        != BOUND_IDENTITIES["observation"][1]
        or standalone.get("protocol_outcome") != "success"
        or standalone.get("operator_outcome") != "FULL_PANEL_CLEAN_WHITE_NO_RESIDUAL"
        or standalone.get("j2_after_observation") != "OFF"
        or standalone.get("current_after_j2_off_a") != 0.0
        or standalone.get("abnormal_sound_smell_or_heating") is not False
        or boundaries.get("clean_white_physical_baseline_reestablished") is not True
        or boundaries.get(
            "independent_campaign_may_recheck_clean_white_as_its_own_precondition"
        )
        is not True
        or boundaries.get("strict_original_c23_t23_pair_gate_releasable") is not False
        or result.get("outcome") != "success"
        or result.get("hardware_action_id") != EXPECTED_CONTAINMENT_ACTION_ID
        or result.get("release_id") != EXPECTED_CONTAINMENT_RELEASE_ID
        or result.get("ordinal") != 2
        or result.get("arm_posts") != 1
        or result.get("execute_posts") != 1
        or result.get("visible_refreshes") != 1
        or result.get("retry_allowed") is not False
        or claim.get("state") != "permanently_consumed_do_not_retry"
        or claim.get("hardware_action_id") != EXPECTED_CONTAINMENT_ACTION_ID
        or observation.get("state") != "FINAL_CLEAN_WHITE_CONTAINMENT_OBSERVED"
        or observation.get("hardware_action_id") != EXPECTED_CONTAINMENT_ACTION_ID
        or electrical.get("j2_after_observation") != "OFF"
        or electrical.get("current_after_j2_off_a") != 0.0
        or electrical.get("abnormal_sound_smell_or_heating") is not False
        or visual.get("screen") != "FULL_PANEL_CLEAN_WHITE"
        or visual.get("c23_colour_code_atlas_residual") is not False
        or visual.get("border_residual") is not False
        or visual.get("colour_spot_residual") is not False
        or classification.get("clean_white_physical_baseline_reestablished") is not True
        or classification.get("counts_as_t23_treatment_or_pair_evidence") is not False
    ):
        raise physical.DitherColorAtlasPhysicalError(
            "clean-white containment evidence semantics differ"
        )

    return campaign.sha256(
        {
            "kind": "c23-fault-clean-white-containment-dither-start-rebind-v1",
            "dither_release_file_sha256": EXPECTED_RELEASE_FILE_SHA256,
            "dither_release_canonical_sha256": EXPECTED_RELEASE_CANONICAL_SHA256,
            "containment_final_file_sha256": BOUND_IDENTITIES["final"][1],
            "containment_final_canonical_sha256": BOUND_IDENTITIES["final"][2],
            "containment_result_file_sha256": BOUND_IDENTITIES["result"][1],
            "containment_observation_file_sha256": BOUND_IDENTITIES["observation"][1],
            "containment_claim_file_sha256": BOUND_IDENTITIES["claim"][1],
            "scope": "ordinal_1_predecessor_only_no_action_or_firmware_identity_change",
        }
    )


def required_authorization(context: physical.ReleaseContext, ordinal: int) -> str:
    # Public runner/describe entries replay the full release gate before this
    # callback.  Avoid an additional multi-megabyte replay here while still
    # refusing a foreign in-memory context.
    is_exact_dither_context = (
        context.release_file_sha256 == EXPECTED_RELEASE_FILE_SHA256
        and context.release_canonical_sha256 == EXPECTED_RELEASE_CANONICAL_SHA256
        and tuple(str(item.get("action_id")) for item in context.actions)
        == (EXPECTED_ATLAS_ACTION_ID, EXPECTED_WHITE_ACTION_ID)
    )
    if not is_exact_dither_context:
        # Release replay recursively validates the historical matrix and its
        # COLOR_LAB-recovery anchor.  Preserve the generic engine callback for
        # those nested foreign contexts instead of leaking the dither token.
        return engine.campaign.required_authorization(  # type: ignore[attr-defined]
            engine._action(context, ordinal)  # noqa: SLF001
        )
    action = engine._action(context, ordinal)  # noqa: SLF001
    base = campaign.required_authorization(action)
    if ordinal != 1:
        return base
    return (
        f"{base}__PREDECESSOR_REBOUND_{validate_containment_evidence().upper()}"
        "__EXACT_C23_FAULT_CONTAINMENT_CLEAN_WHITE"
        "__NOT_T23_EVIDENCE_NO_RETRY_NO_AUTOCHAIN"
    )


def _rebound_prior_gate(
    context: physical.ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    if ordinal != 1:
        return _ORIGINAL_PRIOR_GATE(
            context,
            ordinal,
            prior_result_file=prior_result_file,
            prior_observation_file=prior_observation_file,
            claim_registry=claim_registry,
            confirm_no_intervening_visible_refresh=(
                confirm_no_intervening_visible_refresh
            ),
            j2_off_diagnostic_file=j2_off_diagnostic_file,
        )
    if not confirm_no_intervening_visible_refresh:
        raise physical.DitherColorAtlasPhysicalError(
            "rebound ordinal 1 requires live no-intervening-refresh confirmation"
        )
    if prior_result_file is not None or prior_observation_file is not None:
        raise physical.DitherColorAtlasPhysicalError(
            "rebound ordinal 1 accepts only the exact containment clean-white anchor"
        )
    if j2_off_diagnostic_file is None:
        raise physical.DitherColorAtlasPhysicalError(
            "rebound ordinal 1 requires same-boot J2-off diagnostic evidence"
        )
    if Path(claim_registry).resolve() != physical.DEFAULT_CLAIM_REGISTRY.resolve():
        raise physical.DitherColorAtlasPhysicalError(
            "rebound entry fixes the dither permanent claim registry"
        )
    for action_id in (EXPECTED_ATLAS_ACTION_ID, EXPECTED_WHITE_ACTION_ID):
        if (Path(claim_registry) / f"{action_id}.json").exists():
            raise physical.DitherColorAtlasPhysicalError(
                "rebound dither action is already permanently claimed"
            )
    diagnostic = engine.validate_j2_off_diagnostic(
        context,
        j2_off_diagnostic_file,
        claim_registry=claim_registry,
    )
    binding_id = validate_containment_evidence()
    return {
        "kind": "exact_c23_fault_containment_clean_white_and_same_boot_j2_off_diagnostic",
        "predecessor_action_id": EXPECTED_CONTAINMENT_ACTION_ID,
        "superseded_static_release_predecessor_action_id": (
            campaign.FIRST_PREDECESSOR_ACTION_ID
        ),
        "rebind_id": binding_id,
        "containment_final_file_sha256": BOUND_IDENTITIES["final"][1],
        "containment_result_file_sha256": BOUND_IDENTITIES["result"][1],
        "containment_observation_file_sha256": BOUND_IDENTITIES["observation"][1],
        "containment_claim_file_sha256": BOUND_IDENTITIES["claim"][1],
        "latest_visible_state": "clean_full_white_factory_otp",
        "j2_off_diagnostic": engine._file_reference(  # noqa: SLF001
            j2_off_diagnostic_file, label="rebound J2-off diagnostic evidence"
        ),
        "required_same_boot_nonce": diagnostic["boot_nonce"],
        "live_no_intervening_visible_refresh_confirmed": True,
        "strict_c23_t23_pair_gate_released": False,
    }


def _rebound_describe(context: physical.ReleaseContext, ordinal: int) -> dict[str, Any]:
    root = deepcopy(_ORIGINAL_DESCRIBE(context, ordinal))
    root["authorization"] = required_authorization(context, ordinal)
    if ordinal == 1:
        root["requires_release_bound_matrix_ordinal3_clean_white"] = False
        root["requires_exact_c23_fault_containment_clean_white"] = True
        root["static_release_predecessor_superseded_for_ordinal_1"] = True
        root["predecessor_rebind_id"] = validate_containment_evidence()
        root["strict_c23_t23_pair_gate_released"] = False
    return root


def install_overrides() -> None:
    bindings = dict(physical._ENGINE_BINDINGS)  # noqa: SLF001
    bindings["_prior_gate"] = _rebound_prior_gate
    bindings["required_authorization"] = required_authorization
    bindings["_validate_version"] = _dither_validate_version
    bindings["_validate_manifest"] = _dither_validate_manifest
    bindings["describe"] = _rebound_describe
    physical._ENGINE_BINDINGS = bindings  # noqa: SLF001
    physical._dither_prior_gate = _rebound_prior_gate  # noqa: SLF001
    physical._dither_describe = _rebound_describe  # noqa: SLF001
    physical.required_authorization = required_authorization


def _require_exact_cli_scope(args: Sequence[str]) -> None:
    if "--claim-registry" in args:
        raise physical.DitherColorAtlasPhysicalError(
            "containment-rebound entry fixes the permanent claim registry"
        )
    if "--release" not in args:
        return
    try:
        selected = Path(args[args.index("--release") + 1]).resolve(strict=True)
    except (IndexError, OSError) as error:
        raise physical.DitherColorAtlasPhysicalError(
            "containment-rebound entry requires the exact release file"
        ) from error
    if selected != RELEASE_FILE.resolve(strict=True):
        raise physical.DitherColorAtlasPhysicalError(
            "containment-rebound entry refuses a different release file"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        _require_exact_cli_scope(args)
        validate_containment_evidence()
        install_overrides()
        return physical.main(args)
    except physical.DitherColorAtlasPhysicalError as error:
        print(f"EC5 dither containment-rebind error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
