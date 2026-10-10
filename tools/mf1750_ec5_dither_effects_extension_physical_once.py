#!/usr/bin/env python3
"""Run one fixed factory-OTP dither-effects action at a time.

The audited COLOR_LAB HTTP/state engine is rebound to the four-action effects
campaign.  A staged release is never accepted.  A real release must first bind
the completed dither-atlas ordinal-2 white result, observation, and permanent
claim.  Every action then needs its own exact authorization; no code path
retries, recovers, or advances to another visible action.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_physical_once as engine  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_contract as atlas_contract  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_contract as contract  # noqa: E402


DEVICE_KIND_PREFIX = "mf1750-ec5-dither-effects-extension"
CLAIM_KIND = f"{DEVICE_KIND_PREFIX}-permanent-host-claim"
RESULT_KIND = f"{DEVICE_KIND_PREFIX}-physical-once-result"
OBSERVATION_KIND = f"{DEVICE_KIND_PREFIX}-manual-observation"
J2_OFF_DIAGNOSTIC_KIND = f"{DEVICE_KIND_PREFIX}-j2-off-diagnostic"
RECONCILIATION_KIND = f"{DEVICE_KIND_PREFIX}-late-terminal-readback-reconciliation"
OBSERVATION_TEMPLATE_KIND = f"{DEVICE_KIND_PREFIX}-observation-template"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-dither-effects-extension-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_dither_effects_extension_claims"
)

EXPECTED_CAMPAIGN_FILE_SHA256 = (
    "63337e78041336929884268461fb24a3d4da236518242125a5c3b4727ba600c2"
)
EXPECTED_CAMPAIGN_CANONICAL_SHA256 = (
    "cf77aa3d098757eda8209a11bf20a6359c00be2f524e816408a3bc1bb850bf4e"
)
EXPECTED_STAGED_RELEASE_FILE_SHA256 = (
    "14bc3568891b359a8a37c5adfb4911aff6ae37dfc5e44a0ca1efae01e04f6d5a"
)
EXPECTED_STAGED_RELEASE_CANONICAL_SHA256 = (
    "62fd222ea3d026da27b8fbbc5d69c87e91ab5a366ca275d7b7c5423b86a3a03a"
)
EXPECTED_FIRMWARE_BINARY_SHA256 = (
    "031c31badfcdde9067e7aeeee4e3fdd811f1955c169f92699d7b1604a59a66b1"
)
EXPECTED_FIRMWARE_ELF_SHA256 = (
    "a6a1c488f26414c8ed6debcaea928fbcfc424da656067fb65464acf9172ef93d"
)

DitherEffectsExtensionPhysicalError = engine.ColorLabPhysicalError
ReleaseContext = engine.ReleaseContext
Preflight = engine.Preflight
Requester = engine.Requester
http_request = engine.http_request

_ENGINE_LOCK = engine._ENGINE_BINDING_LOCK
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class _EngineCampaignFacade:
    ColorLabCampaignError = campaign.DitherEffectsExtensionCampaignError

    def __getattr__(self, name: str) -> Any:
        return getattr(campaign, name)


class _EngineContractFacade:
    ROLE_WHITE = contract.ROLE_WHITE_AFTER_GRADIENTS
    WHITE_ROLES = (
        contract.ROLE_WHITE_AFTER_GRADIENTS,
        contract.ROLE_WHITE_AFTER_EFFECTS,
    )
    ROLE_ATLAS = contract.ROLE_PAIR_GRADIENTS
    ROLE_U04_PRIMER = "UNUSED_DITHER_EFFECTS_U04_PRIMER"
    ROLE_U04_TARGET = "UNUSED_DITHER_EFFECTS_U04_TARGET"
    ROLE_U07_PRIMER = "UNUSED_DITHER_EFFECTS_U07_PRIMER"
    ROLE_U07_TARGET = "UNUSED_DITHER_EFFECTS_U07_TARGET"
    ROLE_U07_ISOLATED = "UNUSED_DITHER_EFFECTS_U07_ISOLATED"

    def __getattr__(self, name: str) -> Any:
        return getattr(contract, name)


_ENGINE_CAMPAIGN = _EngineCampaignFacade()
_ENGINE_CONTRACT = _EngineContractFacade()
_ORIGINAL_VALIDATE_VERSION = engine._validate_version  # noqa: SLF001
_ORIGINAL_VALIDATE_MANIFEST = engine._validate_manifest  # noqa: SLF001


def _expected_nvs_contract() -> dict[str, Any]:
    return {
        "namespace": contract.NVS_NAMESPACE,
        "key": contract.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 5,
    }


def _expected_static_device_anchor() -> dict[str, Any]:
    return {
        "campaign_id": contract.PREDECESSOR_CAMPAIGN_ID,
        "ordinal": contract.PREDECESSOR_ORDINAL,
        "role": contract.PREDECESSOR_ROLE,
        "action_id": contract.PREDECESSOR_ACTION_ID,
        "evidence_bound_at_release_materialization": True,
        "validated_by_device": False,
        "required_host_gate_for_ordinal_1": True,
    }


def _effects_validate_version(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("kind") != (
        f"{DEVICE_KIND_PREFIX}-version"
    ):
        return _ORIGINAL_VALIDATE_VERSION(value)
    root = engine._identity(  # noqa: SLF001
        value,
        kind=f"{DEVICE_KIND_PREFIX}-version",
        label="device dither-effects version",
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
    engine._keys(  # noqa: SLF001
        root, required, label="device dither-effects version"
    )
    if (
        root["classification"] != contract.CLASSIFICATION
        or root["layout_id"] != contract.LAYOUT_ID
        or root["driver_api_version"] != "MF1750_R16_CASCADE_V3"
        or root["profile_source"] != "factory_otp"
        or root["action_count"] != campaign.ACTION_COUNT
        or root["nvs_contract"] != _expected_nvs_contract()
        or root["external_clean_white_anchor"] != _expected_static_device_anchor()
    ):
        raise DitherEffectsExtensionPhysicalError(
            "device dither-effects version identity differs"
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
        raise DitherEffectsExtensionPhysicalError(
            "device dither-effects version false safety fields differ"
        )
    if root["dither"] is not True or root["spatial_mixing"] is not True:
        raise DitherEffectsExtensionPhysicalError(
            "device dither-effects version spatial-mixing fields differ"
        )
    return root


def _effects_validate_manifest(
    value: Any, actions: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("kind") != (
        f"{DEVICE_KIND_PREFIX}-manifest"
    ):
        return _ORIGINAL_VALIDATE_MANIFEST(value, actions)
    root = engine._identity(  # noqa: SLF001
        value,
        kind=f"{DEVICE_KIND_PREFIX}-manifest",
        label="device dither-effects manifest",
    )
    expected_layout = {
        "controller_count": 2,
        "controller_halves_semantically_identical": True,
        "controller_pattern_phase_identical": True,
        "mask": "bayer-8x8-rank-0-to-63",
        "mixture_resolution_units": 64,
        "appearance_names_are_hypotheses": True,
        "pair_gradients": {
            "rows": 7,
            "x0_local": 24,
            "width": 464,
            "y0": 14,
            "row_height": 72,
            "row_gap": 10,
        },
        "effects_chart": {
            "warm_trifield": True,
            "cool_trifield": True,
            "neutral_ramp": True,
            "native_blocks": 6,
            "detail_widths_pixels": [1, 2, 4, 8],
        },
    }
    expected_actions = [
        engine._device_action(action)
        for action in actions  # noqa: SLF001
    ]
    if (
        root.get("classification") != contract.CLASSIFICATION
        or root.get("layout_id") != contract.LAYOUT_ID
        or root.get("profile_source") != "factory_otp"
        or root.get("action_count") != campaign.ACTION_COUNT
        or root.get("round_count") != 1
        or root.get("actions") != expected_actions
        or root.get("nvs_contract") != _expected_nvs_contract()
        or root.get("dither_layout") != expected_layout
        or root.get("external_clean_white_anchor") != _expected_static_device_anchor()
    ):
        raise DitherEffectsExtensionPhysicalError(
            "device dither-effects manifest identity differs"
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
        raise DitherEffectsExtensionPhysicalError(
            "device dither-effects manifest safety fields differ"
        )
    return root


def _effects_safety_snapshot(context: ReleaseContext) -> dict[str, Any]:
    safety = context.release_root.get("safety")
    wanted = {
        "profile_source": "factory_otp",
        "spatial_dithering_only": True,
        "runtime_lut_or_waveform_write": False,
        "electrical_parameter_write": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    if (
        not isinstance(safety, Mapping)
        or {key: safety.get(key) for key in wanted} != wanted
    ):
        raise DitherEffectsExtensionPhysicalError(
            "dither-effects no-runtime-LUT safety snapshot differs"
        )
    return {
        "kind": "factory-otp-spatial-dither-effects-no-runtime-lut-snapshot",
        "release_file_sha256": context.release_file_sha256,
        **wanted,
    }


def _reference_matches(value: Any, *, file_sha256: str, canonical_sha256: str) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("file_sha256") == file_sha256
        and value.get("integrity_sha256") == canonical_sha256
    )


def _sealed_mapping_matches(value: Any, canonical_sha256: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping) or dict(integrity) != {
        "canonical_sha256": canonical_sha256,
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }:
        return False
    unsigned = dict(value)
    unsigned.pop("integrity")
    return campaign.sha256(unsigned) == canonical_sha256


def _effects_prior_gate(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    if not confirm_no_intervening_visible_refresh:
        raise DitherEffectsExtensionPhysicalError(
            f"ordinal {ordinal} requires live no-intervening-refresh confirmation"
        )
    if ordinal == 1:
        if prior_result_file is not None or prior_observation_file is not None:
            raise DitherEffectsExtensionPhysicalError(
                "ordinal 1 accepts only the release-bound atlas white anchor"
            )
        if j2_off_diagnostic_file is None:
            raise DitherEffectsExtensionPhysicalError(
                "ordinal 1 requires same-boot J2-off diagnostic evidence"
            )
        diagnostic = engine.validate_j2_off_diagnostic(
            context,
            j2_off_diagnostic_file,
            claim_registry=claim_registry,
        )
        anchor = context.release_root.get("predecessor_binding")
        if (
            not isinstance(anchor, Mapping)
            or anchor.get("kind") != "exact_finalized_dither_atlas_ordinal2_clean_white"
            or anchor.get("campaign_id") != contract.PREDECESSOR_CAMPAIGN_ID
            or anchor.get("ordinal") != contract.PREDECESSOR_ORDINAL
            or anchor.get("role") != contract.PREDECESSOR_ROLE
            or anchor.get("action_id") != contract.PREDECESSOR_ACTION_ID
            or anchor.get("latest_visible_state") != "clean_full_white_factory_otp"
            or anchor.get("clean_white_confirmed") is not True
            or anchor.get("manual_no_intervening_refresh_confirmation_required")
            is not True
        ):
            raise DitherEffectsExtensionPhysicalError(
                "release-bound atlas ordinal2 clean-white evidence differs"
            )
        return {
            "kind": (
                "exact_finalized_atlas_ordinal2_clean_white_and_"
                "same_boot_j2_off_diagnostic"
            ),
            "predecessor_action_id": contract.PREDECESSOR_ACTION_ID,
            "anchor_result_file_sha256": anchor["result"]["file_sha256"],
            "anchor_observation_file_sha256": anchor["observation"]["file_sha256"],
            "anchor_claim_file_sha256": anchor["claim"]["file_sha256"],
            "latest_visible_state": "clean_full_white_factory_otp",
            "j2_off_diagnostic": engine._file_reference(  # noqa: SLF001
                j2_off_diagnostic_file, label="J2-off diagnostic evidence"
            ),
            "required_same_boot_nonce": diagnostic["boot_nonce"],
            "live_no_intervening_visible_refresh_confirmed": True,
        }

    if not 2 <= ordinal <= campaign.ACTION_COUNT:
        raise DitherEffectsExtensionPhysicalError(
            "dither-effects ordinal is outside 1..4"
        )
    if j2_off_diagnostic_file is not None:
        raise DitherEffectsExtensionPhysicalError(
            "J2-off diagnostic evidence is accepted only for ordinal 1"
        )
    if prior_result_file is None or prior_observation_file is None:
        raise DitherEffectsExtensionPhysicalError(
            f"ordinal {ordinal} requires exact prior result and observation"
        )
    prior_result = engine.validate_result(
        context, prior_result_file, claim_registry=claim_registry
    )
    previous = context.actions[ordinal - 2]
    if (
        prior_result.get("ordinal") != ordinal - 1
        or prior_result.get("outcome") != "complete_pass"
        or prior_result.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
        or prior_result.get("action", {}).get("action_id") != previous["action_id"]
        or prior_result.get("action", {}).get("role") != previous["role"]
    ):
        raise DitherEffectsExtensionPhysicalError(
            "prior result is not the exact preceding extension action"
        )
    prior_observation = engine.validate_observation(
        context,
        prior_observation_file,
        result_file=prior_result_file,
        claim_registry=claim_registry,
    )
    if (
        prior_observation.get("ordinal") != ordinal - 1
        or prior_observation.get("kind") != OBSERVATION_KIND
        or prior_observation.get("action", {}).get("action_id") != previous["action_id"]
        or prior_observation.get("sequence_gate_pass") is not True
        or prior_observation.get("automatic_next_action_authorized") is not False
        or prior_observation.get("retry_authorized") is not False
        or prior_observation.get("recovery_authorized") is not False
    ):
        raise DitherEffectsExtensionPhysicalError(
            "prior manual observation does not unlock the next action"
        )
    if (
        previous["role"] in _ENGINE_CONTRACT.WHITE_ROLES
        and prior_observation.get("visual", {}).get("full_clean_white") is not True
    ):
        raise DitherEffectsExtensionPhysicalError(
            "prior white recovery was not finalized as clean white"
        )
    return {
        "kind": "exact_previous_result_and_manual_observation_same_boot",
        "prior_ordinal": ordinal - 1,
        "prior_action_id": previous["action_id"],
        "result": engine._file_reference(  # noqa: SLF001
            prior_result_file, label="prior dither-effects result"
        ),
        "observation": engine._file_reference(  # noqa: SLF001
            prior_observation_file, label="prior dither-effects observation"
        ),
        "required_same_boot_nonce": prior_result["preflight"]["boot_nonce"],
        "live_no_intervening_visible_refresh_confirmed": True,
    }


def _effects_describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    role = str(action["role"])
    is_white = role in _ENGINE_CONTRACT.WHITE_ROLES
    return {
        "release_execution_eligible": context.execution_eligible,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "authorization": campaign.required_authorization(action),
        "requires_j2_off_diagnostic": ordinal == 1,
        "requires_release_bound_atlas_ordinal2_clean_white": ordinal == 1,
        "requires_exact_previous_result_and_observation": ordinal > 1,
        "same_boot_and_no_intervening_refresh_required": True,
        "factory_otp_profile": True,
        "spatial_dithering_only": not is_white,
        "runtime_lut_or_waveform_changed": False,
        "safe_to_pause_after_observation": ordinal in (2, 4),
        "white_checkpoint_after_observation": is_white,
        "automatic_white_recovery": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _bundle_asset(
    context: ReleaseContext, name: str, *, label: str
) -> tuple[Path, bytes]:
    bundle = context.release_root.get("offline_effects_bundle")
    if not isinstance(bundle, Mapping) or not isinstance(bundle.get("bundle"), str):
        raise DitherEffectsExtensionPhysicalError(
            "release-bound offline effects bundle differs"
        )
    try:
        directory = Path(str(bundle["bundle"])).resolve(strict=True)
        asset = (directory / name).resolve(strict=True)
    except OSError as error:
        raise DitherEffectsExtensionPhysicalError(
            f"release-bound {label} cannot be resolved: {error}"
        ) from error
    if asset.parent != directory:
        raise DitherEffectsExtensionPhysicalError(
            f"release-bound {label} escaped bundle"
        )
    return asset, engine._read(asset, label=label)  # noqa: SLF001


def _effects_observation_template(
    context: ReleaseContext, ordinal: int
) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    role = str(action["role"])
    is_white = role in _ENGINE_CONTRACT.WHITE_ROLES
    root: dict[str, Any] = {
        "schema_version": engine.SCHEMA_VERSION,
        "kind": OBSERVATION_TEMPLATE_KIND,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "common_checks": [
            "display_matches_expected_layout_or_target",
            "left_right_controller_halves_match",
            "no_unexpected_residual_or_damage",
            "electrical_normal",
            "temperature_c_10_to_45",
            "esp32_did_not_restart",
        ],
        "one_operator_reply_may_cover_all_fields": True,
        "factory_otp_profile": True,
        "spatial_mixing_only": not is_white,
        "runtime_lut_or_waveform_change_claimed": False,
        "single_pixel_new_colour_state_claimed": False,
        "visible_refresh_authorized": False,
        "automatic_next_action_authorized": False,
        "retry_authorized": False,
        "recovery_authorized": False,
    }
    if role == contract.ROLE_PAIR_GRADIENTS:
        preview, payload = _bundle_asset(
            context,
            "pair-gradients-strict-preview.png",
            label="pair-gradients strict preview",
        )
        root["preview"] = {
            "file": str(preview),
            "bytes": len(payload),
            "sha256": campaign.sha256(payload),
            "notice": "geometry/code preview only; not a panel colour prediction",
        }
        root["role_observation_fields"] = {
            "seven_gradients_visually_monotonic": None,
            "visible_band_count_by_row_0_to_6": [None] * 7,
            "near_view_pattern_or_grain_by_row_0_to_6": [""] * 7,
            "mid_view_mixed_colour_words_by_row_0_to_6": [""] * 7,
            "left_right_halves_match": None,
        }
    elif role == contract.ROLE_EFFECTS_CHART:
        preview, payload = _bundle_asset(
            context,
            "effects-chart-strict-preview.png",
            label="effects-chart strict preview",
        )
        root["preview"] = {
            "file": str(preview),
            "bytes": len(payload),
            "sha256": campaign.sha256(payload),
            "notice": "geometry/code preview only; not a panel colour prediction",
        }
        root["role_observation_fields"] = {
            "warm_trifield_continuous": None,
            "cool_trifield_continuous": None,
            "neutral_ramp_monotonic_and_neutral": None,
            "six_native_blocks_uniform": None,
            "smallest_clear_feature_width_pixels": None,
            "feature_widths_1_2_4_8_px_notes": "",
            "left_right_halves_match": None,
        }
    elif is_white:
        target, payload = _bundle_asset(
            context, "white.frame.bin", label="white target frame"
        )
        identity = contract.ROLE_IDENTITIES[role]["frame"]
        if (
            len(payload) != identity["bytes"]
            or campaign.sha256(payload) != identity["sha256"]
        ):
            raise DitherEffectsExtensionPhysicalError(
                "white target differs from frozen action identity"
            )
        root["target_payload"] = {
            "file": str(target),
            "bytes": len(payload),
            "sha256": campaign.sha256(payload),
            "notice": "identity payload only; not an image preview",
        }
        root["role_observation_fields"] = {
            "full_screen_clean_white": None,
            "previous_target_fully_removed": None,
            "residual_or_outline_present": None,
            "residual_location_if_any": "",
        }
    else:
        raise DitherEffectsExtensionPhysicalError("unknown dither-effects role")
    return root


_ENGINE_BINDINGS: Mapping[str, Any] = {
    "campaign": _ENGINE_CAMPAIGN,
    "contract": _ENGINE_CONTRACT,
    "DEVICE_KIND_PREFIX": DEVICE_KIND_PREFIX,
    "CLAIM_KIND": CLAIM_KIND,
    "RESULT_KIND": RESULT_KIND,
    "OBSERVATION_KIND": OBSERVATION_KIND,
    "J2_OFF_DIAGNOSTIC_KIND": J2_OFF_DIAGNOSTIC_KIND,
    "RECONCILIATION_KIND": RECONCILIATION_KIND,
    "OBSERVATION_TEMPLATE_KIND": OBSERVATION_TEMPLATE_KIND,
    "CLAIM_REGISTRY_ID": CLAIM_REGISTRY_ID,
    "DEFAULT_CLAIM_REGISTRY": DEFAULT_CLAIM_REGISTRY,
    "_formal_u07_snapshot": _effects_safety_snapshot,
    "_prior_gate": _effects_prior_gate,
    "_validate_version": _effects_validate_version,
    "_validate_manifest": _effects_validate_manifest,
    "describe": _effects_describe,
    "observation_template": _effects_observation_template,
}


@contextmanager
def _bound_engine() -> Iterator[None]:
    with _ENGINE_LOCK:
        previous = {name: getattr(engine, name) for name in _ENGINE_BINDINGS}
        for name, value in _ENGINE_BINDINGS.items():
            setattr(engine, name, value)
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(engine, name, value)


def _stable_hashes() -> dict[str, str]:
    values = {
        "campaign file": EXPECTED_CAMPAIGN_FILE_SHA256,
        "campaign canonical": EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "staged release file": EXPECTED_STAGED_RELEASE_FILE_SHA256,
        "staged release canonical": EXPECTED_STAGED_RELEASE_CANONICAL_SHA256,
        "firmware binary": EXPECTED_FIRMWARE_BINARY_SHA256,
        "firmware ELF": EXPECTED_FIRMWARE_ELF_SHA256,
    }
    if any(_SHA256_RE.fullmatch(value) is None for value in values.values()):
        raise DitherEffectsExtensionPhysicalError(
            "physical runner is hard-blocked by an unsealed stable identity"
        )
    return values


def _exact_release_gate(context: ReleaseContext) -> None:
    expected = _stable_hashes()
    try:
        checked = campaign.validate_materialized_release(context.release_file)
    except campaign.DitherEffectsExtensionCampaignError as error:
        raise DitherEffectsExtensionPhysicalError(
            f"dither-effects release validation failed: {error}"
        ) from error
    compiled = context.release_root.get("compiled_campaign")
    staged = context.release_root.get("staged_release")
    anchor = context.release_root.get("predecessor_binding")
    safety = context.release_root.get("safety")
    expected_action_ids = {
        str(item["hardware_action_id"]) for item in contract.DESCRIPTORS
    }
    atlas_action_ids = {
        str(item["hardware_action_id"]) for item in atlas_contract.DESCRIPTORS
    }
    if (
        checked.get("execution_eligible") is not True
        or checked.get("evidence_mode") != campaign.REAL_MODE
        or checked.get("firmware_binary_sha256") != expected["firmware binary"]
        or checked.get("firmware_elf_sha256") != expected["firmware ELF"]
        or checked.get("staged_release_file_sha256") != expected["staged release file"]
        or context.execution_eligible is not True
        or context.release_root.get("execution_eligible") is not True
        or context.release_root.get("live_authorized") is not False
        or context.release_file_sha256 != checked.get("file_sha256")
        or context.release_canonical_sha256 != checked.get("canonical_sha256")
        or not _sealed_mapping_matches(
            context.release_root, context.release_canonical_sha256
        )
        or not _sealed_mapping_matches(
            context.campaign_root, expected["campaign canonical"]
        )
        or tuple(context.actions) != tuple(context.campaign_root.get("actions", ()))
        or not isinstance(compiled, Mapping)
        or compiled.get("file_sha256") != expected["campaign file"]
        or compiled.get("canonical_sha256") != expected["campaign canonical"]
        or not _reference_matches(
            staged,
            file_sha256=expected["staged release file"],
            canonical_sha256=expected["staged release canonical"],
        )
        or not isinstance(anchor, Mapping)
        or anchor.get("kind") != "exact_finalized_dither_atlas_ordinal2_clean_white"
        or anchor.get("action_id") != contract.PREDECESSOR_ACTION_ID
        or anchor.get("ordinal") != contract.PREDECESSOR_ORDINAL
        or anchor.get("role") != contract.PREDECESSOR_ROLE
        or anchor.get("latest_visible_state") != "clean_full_white_factory_otp"
        or anchor.get("clean_white_confirmed") is not True
        or not isinstance(safety, Mapping)
        or safety != campaign._safety()  # noqa: SLF001
        or {str(item["action_id"]) for item in context.actions} != expected_action_ids
        or expected_action_ids & atlas_action_ids
        or (contract.NVS_NAMESPACE, contract.NVS_KEY)
        == (atlas_contract.NVS_NAMESPACE, atlas_contract.NVS_KEY)
    ):
        raise DitherEffectsExtensionPhysicalError(
            "exact dither-effects extension release gate differs"
        )


def load_release(release_file: Path) -> ReleaseContext:
    _stable_hashes()
    try:
        checked = campaign.validate_materialized_release(release_file)
        release_payload = campaign._read_regular(  # noqa: SLF001
            release_file, label="dither-effects real release"
        )
        release_root = campaign._decode(  # noqa: SLF001
            release_payload, label="dither-effects real release"
        )
        campaign_file = Path(str(release_root["compiled_campaign"]["file"]))
        campaign_payload = campaign._read_regular(  # noqa: SLF001
            campaign_file, label="dither-effects campaign"
        )
        campaign_root = campaign._decode(  # noqa: SLF001
            campaign_payload, label="dither-effects campaign"
        )
    except (
        campaign.DitherEffectsExtensionCampaignError,
        KeyError,
        TypeError,
    ) as error:
        raise DitherEffectsExtensionPhysicalError(
            f"dither-effects release validation failed: {error}"
        ) from error
    context = ReleaseContext(
        release_file=Path(release_file).resolve(),
        release_root=release_root,
        release_file_sha256=campaign.sha256(release_payload),
        release_canonical_sha256=str(checked["canonical_sha256"]),
        campaign_file=campaign_file.resolve(),
        campaign_root=campaign_root,
        actions=tuple(deepcopy(campaign_root["actions"])),
        execution_eligible=bool(checked["execution_eligible"]),
        formal_u07_registry=None,
    )
    _exact_release_gate(context)
    return context


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    _exact_release_gate(context)
    with _bound_engine():
        return campaign.required_authorization(
            engine._action(context, ordinal)  # noqa: SLF001
        )


def describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return deepcopy(_effects_describe(context, ordinal))


def observation_template(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return deepcopy(_effects_observation_template(context, ordinal))


def preflight(
    context: ReleaseContext, base_url: str, ordinal: int, **kwargs: Any
) -> Preflight:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.preflight(context, base_url, ordinal, **kwargs)


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    evidence_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.diagnose_j2_off(
            context,
            base_url,
            evidence_file=evidence_file,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_j2_off_diagnostic(
    context: ReleaseContext,
    evidence_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_j2_off_diagnostic(
            context, evidence_file, claim_registry=claim_registry
        )


def run_once(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.run_once(
            context,
            base_url,
            ordinal,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_result(
            context, result_file, claim_registry=claim_registry
        )


def reconcile_result(
    context: ReleaseContext,
    base_url: str,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.reconcile_result(
            context,
            base_url,
            claim_registry=claim_registry,
            **kwargs,
        )


def validate_reconciliation(
    context: ReleaseContext,
    reconciliation_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_reconciliation(
            context,
            reconciliation_file,
            claim_registry=claim_registry,
        )


def finalize_observation(
    context: ReleaseContext,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    **kwargs: Any,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.seal_observation(context, claim_registry=claim_registry, **kwargs)


seal_observation = finalize_observation


def validate_observation(
    context: ReleaseContext,
    observation_file: Path,
    *,
    result_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return engine.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )


def _parse_args(argv: Sequence[str] | None) -> Any:
    with _bound_engine():
        return engine.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        context = load_release(args.release)
        if args.command == "describe":
            output = describe(context, args.ordinal)
        elif args.command == "observation-template":
            output = observation_template(context, args.ordinal)
        elif args.command == "preflight":
            output = preflight(context, args.base_url, args.ordinal).as_dict()
        elif args.command == "diagnose-j2-off":
            output = diagnose_j2_off(
                context,
                args.base_url,
                evidence_file=args.evidence,
                claim_registry=args.claim_registry,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "validate-j2-off":
            output = validate_j2_off_diagnostic(
                context, args.evidence, claim_registry=args.claim_registry
            )
        elif args.command == "run":
            output = run_once(
                context,
                args.base_url,
                args.ordinal,
                authorization=args.authorize,
                result_file=args.result,
                claim_registry=args.claim_registry,
                prior_result_file=args.prior_result,
                prior_observation_file=args.prior_observation,
                j2_off_diagnostic_file=args.j2_off_diagnostic,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                temperature_c=args.temperature_c,
                poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        elif args.command == "validate-result":
            output = validate_result(
                context, args.result, claim_registry=args.claim_registry
            )
        elif args.command == "reconcile-result":
            output = reconcile_result(
                context,
                args.base_url,
                source_result_file=args.source_result,
                result_file=args.result,
                reconciliation_file=args.reconciliation,
                claim_registry=args.claim_registry,
                timeout=args.timeout,
            )
        elif args.command == "validate-reconciliation":
            output = validate_reconciliation(
                context,
                args.reconciliation,
                claim_registry=args.claim_registry,
            )
        elif args.command == "validate-observation":
            output = validate_observation(
                context,
                args.observation,
                result_file=args.result,
                claim_registry=args.claim_registry,
            )
        else:
            output = finalize_observation(
                context,
                result_file=args.result,
                observation_file=args.observation,
                claim_registry=args.claim_registry,
                operator_report=args.operator_report,
                temperature_c=args.temperature_c,
                confirm_reference_preview_checked=(
                    args.confirm_reference_preview_checked
                ),
                confirm_display_matches_reference=(
                    args.confirm_display_matches_reference
                ),
                confirm_no_unexpected_residual=args.confirm_no_unexpected_residual,
                confirm_electrical_normal=args.confirm_electrical_normal,
                confirm_esp32_no_restart=args.confirm_esp32_no_restart,
                confirm_clean_white=args.confirm_clean_white,
                confirm_map_fidelity=args.confirm_map_fidelity,
            )
    except DitherEffectsExtensionPhysicalError as error:
        print(f"EC5 dither-effects physical error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if (
        args.command == "run"
        and isinstance(output, Mapping)
        and output.get("outcome") != "complete_pass"
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
