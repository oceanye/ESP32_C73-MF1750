#!/usr/bin/env python3
"""Run one factory-OTP spatial-dither atlas action at a time.

This adapter reuses the audited COLOR_LAB HTTP/state engine while rebinding it
to the two-action dither-atlas campaign.  Importing or describing this module
does not access a device.  Until the six exact clean-build identities below are
sealed, every release-dependent entry point fails before a requester can run.
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
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_contract as contract  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_contract as matrix_contract  # noqa: E402


DEVICE_KIND_PREFIX = "mf1750-ec5-dither-color-atlas"
CLAIM_KIND = f"{DEVICE_KIND_PREFIX}-permanent-host-claim"
RESULT_KIND = f"{DEVICE_KIND_PREFIX}-physical-once-result"
OBSERVATION_KIND = f"{DEVICE_KIND_PREFIX}-manual-observation"
J2_OFF_DIAGNOSTIC_KIND = f"{DEVICE_KIND_PREFIX}-j2-off-diagnostic"
RECONCILIATION_KIND = f"{DEVICE_KIND_PREFIX}-late-terminal-readback-reconciliation"
OBSERVATION_TEMPLATE_KIND = f"{DEVICE_KIND_PREFIX}-observation-template"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-dither-color-atlas-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_dither_color_atlas_claims"
)

# Frozen together from the staged clean-build release.  The gate below also
# verifies exact 64-lowercase-hex form before replaying every referenced file.
EXPECTED_CAMPAIGN_FILE_SHA256: str | None = (
    "37b20c82524bd72d411f15c62dbe5afd4dcebae8c60419d69d75b270093c9707"
)
EXPECTED_CAMPAIGN_CANONICAL_SHA256: str | None = (
    "eecb1a55b367bac60cccb91910a2bb9b0c3666fc5c489f43b2143560ff545708"
)
EXPECTED_RELEASE_FILE_SHA256: str | None = (
    "ec3e2d873badadef615b06b6a30948738ef80a4c4c3e31cbe24344454a037612"
)
EXPECTED_RELEASE_CANONICAL_SHA256: str | None = (
    "68c5ffd09a9a46644e59493a985d21c2a035c5e21aba3324355ebd2eab5df7fe"
)
EXPECTED_FIRMWARE_BINARY_SHA256: str | None = (
    "49f39718e1160be021565fb6b941d71b997ebf91a2abcb73879df3dd06a6e7d4"
)
EXPECTED_FIRMWARE_ELF_SHA256: str | None = (
    "f865d6e52dac827b06cdac5a011222dbf77fa5e30b5453950545845c2cf6fb16"
)

EXPECTED_ANCHOR_RELEASE_FILE_SHA256 = campaign.EXPECTED_MATRIX_RELEASE_FILE_SHA256
EXPECTED_ANCHOR_RELEASE_CANONICAL_SHA256 = (
    campaign.EXPECTED_MATRIX_RELEASE_CANONICAL_SHA256
)
EXPECTED_ANCHOR_RESULT_FILE_SHA256 = campaign.EXPECTED_MATRIX_RESULT_FILE_SHA256
EXPECTED_ANCHOR_RESULT_CANONICAL_SHA256 = (
    campaign.EXPECTED_MATRIX_RESULT_CANONICAL_SHA256
)
EXPECTED_ANCHOR_OBSERVATION_FILE_SHA256 = (
    campaign.EXPECTED_MATRIX_OBSERVATION_FILE_SHA256
)
EXPECTED_ANCHOR_OBSERVATION_CANONICAL_SHA256 = (
    campaign.EXPECTED_MATRIX_OBSERVATION_CANONICAL_SHA256
)
EXPECTED_ANCHOR_CLAIM_FILE_SHA256 = campaign.EXPECTED_MATRIX_CLAIM_FILE_SHA256
EXPECTED_ANCHOR_CLAIM_CANONICAL_SHA256 = campaign.EXPECTED_MATRIX_CLAIM_CANONICAL_SHA256

DitherColorAtlasPhysicalError = engine.ColorLabPhysicalError
ReleaseContext = engine.ReleaseContext
Preflight = engine.Preflight
Requester = engine.Requester
http_request = engine.http_request

_ENGINE_LOCK = engine._ENGINE_BINDING_LOCK
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class _EngineCampaignFacade:
    """Expose dither campaign names expected by the audited generic engine."""

    ColorLabCampaignError = campaign.DitherColorAtlasCampaignError

    def __getattr__(self, name: str) -> Any:
        return getattr(campaign, name)


_ENGINE_CAMPAIGN = _EngineCampaignFacade()


def _dither_safety_snapshot(context: ReleaseContext) -> dict[str, Any]:
    """Replace the COLOR_LAB-only U07 registry guard with dither invariants."""

    safety = context.release_root.get("safety")
    if not isinstance(safety, Mapping) or {
        "profile_source": safety.get("profile_source"),
        "spatial_dithering_only": safety.get("spatial_dithering_only"),
        "runtime_lut_or_waveform_write": safety.get("runtime_lut_or_waveform_write"),
        "electrical_parameter_write": safety.get("electrical_parameter_write"),
        "automatic_chaining": safety.get("automatic_chaining"),
        "automatic_retry": safety.get("automatic_retry"),
        "automatic_recovery": safety.get("automatic_recovery"),
    } != {
        "profile_source": "factory_otp",
        "spatial_dithering_only": True,
        "runtime_lut_or_waveform_write": False,
        "electrical_parameter_write": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }:
        raise DitherColorAtlasPhysicalError(
            "dither release no-runtime-LUT safety snapshot differs"
        )
    return {
        "kind": "factory-otp-spatial-dither-no-runtime-lut-safety-snapshot",
        "release_file_sha256": context.release_file_sha256,
        "profile_source": "factory_otp",
        "spatial_dithering_only": True,
        "runtime_lut_or_waveform_write": False,
        "electrical_parameter_write": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _anchor_reference_matches(
    value: Any, *, file_sha256: str, canonical_sha256: str
) -> bool:
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


def _dither_prior_gate(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_observation_file: Path | None,
    claim_registry: Path,
    confirm_no_intervening_visible_refresh: bool,
    j2_off_diagnostic_file: Path | None,
) -> dict[str, Any]:
    """Require the matrix white anchor, then exact Atlas result/observation."""

    if not confirm_no_intervening_visible_refresh:
        raise DitherColorAtlasPhysicalError(
            f"ordinal {ordinal} requires live no-intervening-refresh confirmation"
        )
    if ordinal == 1:
        if prior_result_file is not None or prior_observation_file is not None:
            raise DitherColorAtlasPhysicalError(
                "ordinal 1 accepts only the release-bound matrix ordinal3 clean white"
            )
        if j2_off_diagnostic_file is None:
            raise DitherColorAtlasPhysicalError(
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
            or anchor.get("kind")
            != "exact_finalized_otp_transition_matrix_ordinal3_white"
            or anchor.get("action_id") != campaign.FIRST_PREDECESSOR_ACTION_ID
            or anchor.get("ordinal") != 3
            or anchor.get("role") != "OTP_WHITE_RECOVERY"
            or anchor.get("required_previous_boot_nonce")
            != campaign.EXPECTED_MATRIX_BOOT_NONCE
            or anchor.get("latest_visible_state") != "clean_full_white_factory_otp"
            or anchor.get("clean_white_confirmed") is not True
            or anchor.get("manual_no_intervening_refresh_confirmation_required")
            is not True
            or not _anchor_reference_matches(
                anchor.get("matrix_release"),
                file_sha256=EXPECTED_ANCHOR_RELEASE_FILE_SHA256,
                canonical_sha256=EXPECTED_ANCHOR_RELEASE_CANONICAL_SHA256,
            )
            or not _anchor_reference_matches(
                anchor.get("result"),
                file_sha256=EXPECTED_ANCHOR_RESULT_FILE_SHA256,
                canonical_sha256=EXPECTED_ANCHOR_RESULT_CANONICAL_SHA256,
            )
            or not _anchor_reference_matches(
                anchor.get("observation"),
                file_sha256=EXPECTED_ANCHOR_OBSERVATION_FILE_SHA256,
                canonical_sha256=EXPECTED_ANCHOR_OBSERVATION_CANONICAL_SHA256,
            )
            or not _anchor_reference_matches(
                anchor.get("claim"),
                file_sha256=EXPECTED_ANCHOR_CLAIM_FILE_SHA256,
                canonical_sha256=EXPECTED_ANCHOR_CLAIM_CANONICAL_SHA256,
            )
        ):
            raise DitherColorAtlasPhysicalError(
                "release-bound matrix ordinal3 clean-white evidence differs"
            )
        return {
            "kind": (
                "exact_finalized_matrix_ordinal3_clean_white_and_"
                "same_boot_j2_off_diagnostic"
            ),
            "predecessor_action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
            "anchor_result_file_sha256": EXPECTED_ANCHOR_RESULT_FILE_SHA256,
            "anchor_observation_file_sha256": (EXPECTED_ANCHOR_OBSERVATION_FILE_SHA256),
            "anchor_claim_file_sha256": EXPECTED_ANCHOR_CLAIM_FILE_SHA256,
            "latest_visible_state": "clean_full_white_factory_otp",
            "j2_off_diagnostic": engine._file_reference(  # noqa: SLF001
                j2_off_diagnostic_file, label="J2-off diagnostic evidence"
            ),
            "required_same_boot_nonce": diagnostic["boot_nonce"],
            "live_no_intervening_visible_refresh_confirmed": True,
        }

    if ordinal != 2:
        raise DitherColorAtlasPhysicalError("dither atlas ordinal is outside 1..2")
    if j2_off_diagnostic_file is not None:
        raise DitherColorAtlasPhysicalError(
            "J2-off diagnostic evidence is accepted only for ordinal 1"
        )
    if prior_result_file is None or prior_observation_file is None:
        raise DitherColorAtlasPhysicalError(
            "ordinal 2 requires the exact Atlas result and manual observation"
        )
    prior_result = engine.validate_result(
        context, prior_result_file, claim_registry=claim_registry
    )
    atlas = context.actions[0]
    if (
        prior_result.get("ordinal") != 1
        or prior_result.get("outcome") != "complete_pass"
        or prior_result.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
        or prior_result.get("action", {}).get("action_id") != atlas["action_id"]
        or prior_result.get("action", {}).get("role") != contract.ROLE_ATLAS
    ):
        raise DitherColorAtlasPhysicalError(
            "prior result is not the exact completed Atlas action"
        )
    prior_observation = engine.validate_observation(
        context,
        prior_observation_file,
        result_file=prior_result_file,
        claim_registry=claim_registry,
    )
    if (
        prior_observation.get("ordinal") != 1
        or prior_observation.get("kind") != OBSERVATION_KIND
        or prior_observation.get("action", {}).get("action_id") != atlas["action_id"]
        or prior_observation.get("sequence_gate_pass") is not True
        or prior_observation.get("automatic_next_action_authorized") is not False
        or prior_observation.get("retry_authorized") is not False
        or prior_observation.get("recovery_authorized") is not False
    ):
        raise DitherColorAtlasPhysicalError(
            "prior manual Atlas observation does not unlock white recovery"
        )
    return {
        "kind": "exact_atlas_result_and_manual_observation_same_boot",
        "prior_ordinal": 1,
        "result": engine._file_reference(  # noqa: SLF001
            prior_result_file, label="prior dither Atlas result"
        ),
        "observation": engine._file_reference(  # noqa: SLF001
            prior_observation_file, label="prior manual Atlas observation"
        ),
        "required_same_boot_nonce": prior_result["preflight"]["boot_nonce"],
        "live_no_intervening_visible_refresh_confirmed": True,
    }


def _dither_describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    return {
        "release_execution_eligible": context.execution_eligible,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "authorization": campaign.required_authorization(action),
        "requires_j2_off_diagnostic": ordinal == 1,
        "requires_release_bound_matrix_ordinal3_clean_white": ordinal == 1,
        "requires_exact_atlas_result_and_manual_observation": ordinal == 2,
        "same_boot_and_no_intervening_refresh_required": True,
        "factory_otp_profile": True,
        "spatial_dithering_only": ordinal == 1,
        "runtime_lut_or_waveform_changed": False,
        "safe_to_pause_after_observation": True,
        "white_recovery_is_separately_authorized": ordinal == 1,
        "automatic_white_recovery": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _bundle_asset(
    context: ReleaseContext, name: str, *, label: str
) -> tuple[Path, bytes]:
    bundle = context.release_root.get("offline_atlas_bundle")
    if not isinstance(bundle, Mapping) or not isinstance(bundle.get("bundle"), str):
        raise DitherColorAtlasPhysicalError(
            "release-bound offline Atlas bundle differs"
        )
    try:
        directory = Path(str(bundle["bundle"])).resolve(strict=True)
        asset = (directory / name).resolve(strict=True)
    except OSError as error:
        raise DitherColorAtlasPhysicalError(
            f"release-bound {label} cannot be resolved: {error}"
        ) from error
    if asset.parent != directory:
        raise DitherColorAtlasPhysicalError(f"release-bound {label} escaped bundle")
    payload = engine._read(asset, label=label)  # noqa: SLF001
    return asset, payload


def _dither_observation_template(
    context: ReleaseContext, ordinal: int
) -> dict[str, Any]:
    action = engine._action(context, ordinal)  # noqa: SLF001
    role = str(action["role"])
    common = [
        "display_matches_expected_layout_or_target",
        "no_unexpected_residual_or_damage",
        "electrical_normal",
        "temperature_c_10_to_45",
        "esp32_did_not_restart",
    ]
    root: dict[str, Any] = {
        "schema_version": engine.SCHEMA_VERSION,
        "kind": OBSERVATION_TEMPLATE_KIND,
        "action": engine._action_reference(context, ordinal),  # noqa: SLF001
        "common_checks": common,
        "one_operator_reply_may_cover_all_fields": True,
        "factory_otp_profile": True,
        "spatial_mixing_only": role == contract.ROLE_ATLAS,
        "runtime_lut_or_waveform_change_claimed": False,
        "single_pixel_new_colour_state_claimed": False,
        "visible_refresh_authorized": False,
        "automatic_white_recovery_authorized": False,
        "automatic_next_action_authorized": False,
        "retry_authorized": False,
        "recovery_authorized": False,
    }
    if role == contract.ROLE_ATLAS:
        preview_file, preview_payload = _bundle_asset(
            context, "strict-preview.png", label="strict Atlas PNG preview"
        )
        root["preview"] = {
            "file": str(preview_file),
            "bytes": len(preview_payload),
            "sha256": campaign.sha256(preview_payload),
            "media_type": "image/png",
            "notice": (
                "layout/code-placement preview only; it does not predict the "
                "reflective colour seen on the panel"
            ),
        }
        root["role_observation_fields"] = {
            "screen_matches_strict_preview_geometry": None,
            "white_gaps_and_edges_clean": None,
            "left_right_controller_halves_match": None,
            "rows_0_to_6": [
                {
                    "display_row": row,
                    "near_view_20_to_30_cm_pattern_visible_by_column": [
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                    "mid_view_about_1_m_three_mixes_visually_ordered": None,
                    "middle_patch_looks_like_distinct_hue": None,
                    "operator_colour_words": "",
                }
                for row in range(7)
            ],
        }
    elif role == contract.ROLE_WHITE:
        target_file, target_payload = _bundle_asset(
            context, "white.frame.bin", label="white target frame payload"
        )
        expected = contract.ROLE_IDENTITIES[contract.ROLE_WHITE]["frame"]
        if (
            len(target_payload) != expected["bytes"]
            or campaign.sha256(target_payload) != expected["sha256"]
        ):
            raise DitherColorAtlasPhysicalError(
                "white target frame differs from the frozen action identity"
            )
        root["target_payload"] = {
            "file": str(target_file),
            "bytes": len(target_payload),
            "sha256": campaign.sha256(target_payload),
            "encoding": "canonical-row-major-two-4bit-codes-per-byte",
            "notice": (
                "target frame payload identity only; this binary is not an image "
                "preview and must not be rendered as one"
            ),
        }
        root["role_observation_fields"] = {
            "full_screen_clean_white": None,
            "all_atlas_cells_removed": None,
            "residual_or_outline_present": None,
            "residual_location_if_any": "",
        }
    else:
        raise DitherColorAtlasPhysicalError("unknown dither Atlas role")
    return root


_ENGINE_BINDINGS: Mapping[str, Any] = {
    "campaign": _ENGINE_CAMPAIGN,
    "contract": contract,
    "DEVICE_KIND_PREFIX": DEVICE_KIND_PREFIX,
    "CLAIM_KIND": CLAIM_KIND,
    "RESULT_KIND": RESULT_KIND,
    "OBSERVATION_KIND": OBSERVATION_KIND,
    "J2_OFF_DIAGNOSTIC_KIND": J2_OFF_DIAGNOSTIC_KIND,
    "RECONCILIATION_KIND": RECONCILIATION_KIND,
    "OBSERVATION_TEMPLATE_KIND": OBSERVATION_TEMPLATE_KIND,
    "CLAIM_REGISTRY_ID": CLAIM_REGISTRY_ID,
    "DEFAULT_CLAIM_REGISTRY": DEFAULT_CLAIM_REGISTRY,
    "_formal_u07_snapshot": _dither_safety_snapshot,
    "_prior_gate": _dither_prior_gate,
    "describe": _dither_describe,
    "observation_template": _dither_observation_template,
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


def _sealed_hashes() -> dict[str, str]:
    values = {
        "campaign file": EXPECTED_CAMPAIGN_FILE_SHA256,
        "campaign canonical": EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "release file": EXPECTED_RELEASE_FILE_SHA256,
        "release canonical": EXPECTED_RELEASE_CANONICAL_SHA256,
        "firmware binary": EXPECTED_FIRMWARE_BINARY_SHA256,
        "firmware ELF": EXPECTED_FIRMWARE_ELF_SHA256,
    }
    unsealed = [
        label
        for label, value in values.items()
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
    ]
    if unsealed:
        raise DitherColorAtlasPhysicalError(
            "physical runner is hard-blocked: clean-build hashes remain explicitly "
            f"unsealed ({', '.join(unsealed)})"
        )
    return {label: str(value) for label, value in values.items()}


def _exact_release_gate(context: ReleaseContext) -> None:
    expected = _sealed_hashes()
    try:
        checked = campaign.validate_materialized_release(context.release_file)
    except campaign.DitherColorAtlasCampaignError as error:
        raise DitherColorAtlasPhysicalError(
            f"dither color-atlas release validation failed: {error}"
        ) from error

    compiled = context.release_root.get("compiled_campaign")
    anchor = context.release_root.get("predecessor_binding")
    safety = context.release_root.get("safety")
    expected_action_ids = {
        str(item["hardware_action_id"]) for item in contract.DESCRIPTORS
    }
    matrix_action_ids = {
        str(item["hardware_action_id"]) for item in matrix_contract.DESCRIPTORS
    }
    if (
        checked.get("file_sha256") != expected["release file"]
        or checked.get("canonical_sha256") != expected["release canonical"]
        or checked.get("firmware_binary_sha256") != expected["firmware binary"]
        or checked.get("firmware_elf_sha256") != expected["firmware ELF"]
        or checked.get("evidence_mode") != campaign.REAL_MODE
        or checked.get("execution_eligible") is not True
        or context.release_file_sha256 != expected["release file"]
        or context.release_canonical_sha256 != expected["release canonical"]
        or context.execution_eligible is not True
        or context.release_root.get("execution_eligible") is not True
        or not _sealed_mapping_matches(
            context.release_root, expected["release canonical"]
        )
        or not _sealed_mapping_matches(
            context.campaign_root, expected["campaign canonical"]
        )
        or tuple(context.actions) != tuple(context.campaign_root.get("actions", ()))
        or not isinstance(compiled, Mapping)
        or compiled.get("file_sha256") != expected["campaign file"]
        or compiled.get("canonical_sha256") != expected["campaign canonical"]
        or not isinstance(anchor, Mapping)
        or anchor.get("kind") != "exact_finalized_otp_transition_matrix_ordinal3_white"
        or anchor.get("action_id") != campaign.FIRST_PREDECESSOR_ACTION_ID
        or anchor.get("ordinal") != 3
        or anchor.get("role") != "OTP_WHITE_RECOVERY"
        or anchor.get("latest_visible_state") != "clean_full_white_factory_otp"
        or anchor.get("clean_white_confirmed") is not True
        or not _anchor_reference_matches(
            anchor.get("matrix_release"),
            file_sha256=EXPECTED_ANCHOR_RELEASE_FILE_SHA256,
            canonical_sha256=EXPECTED_ANCHOR_RELEASE_CANONICAL_SHA256,
        )
        or not _anchor_reference_matches(
            anchor.get("result"),
            file_sha256=EXPECTED_ANCHOR_RESULT_FILE_SHA256,
            canonical_sha256=EXPECTED_ANCHOR_RESULT_CANONICAL_SHA256,
        )
        or not _anchor_reference_matches(
            anchor.get("observation"),
            file_sha256=EXPECTED_ANCHOR_OBSERVATION_FILE_SHA256,
            canonical_sha256=EXPECTED_ANCHOR_OBSERVATION_CANONICAL_SHA256,
        )
        or not _anchor_reference_matches(
            anchor.get("claim"),
            file_sha256=EXPECTED_ANCHOR_CLAIM_FILE_SHA256,
            canonical_sha256=EXPECTED_ANCHOR_CLAIM_CANONICAL_SHA256,
        )
        or not isinstance(safety, Mapping)
        or safety.get("profile_source") != "factory_otp"
        or safety.get("spatial_dithering_only") is not True
        or safety.get("runtime_lut_or_waveform_write") is not False
        or safety.get("electrical_parameter_write") is not False
        or safety.get("automatic_chaining") is not False
        or safety.get("automatic_retry") is not False
        or safety.get("automatic_recovery") is not False
        or {str(item["action_id"]) for item in context.actions} != expected_action_ids
        or expected_action_ids & matrix_action_ids
        or (contract.NVS_NAMESPACE, contract.NVS_KEY)
        == (matrix_contract.NVS_NAMESPACE, matrix_contract.NVS_KEY)
    ):
        raise DitherColorAtlasPhysicalError(
            "exact dither color-atlas release gate differs"
        )


def load_release(release_file: Path) -> ReleaseContext:
    """Load dither release without COLOR_LAB's inapplicable U07 field."""

    _sealed_hashes()
    try:
        checked = campaign.validate_materialized_release(release_file)
        release_payload = campaign._read_regular(  # noqa: SLF001
            release_file, label="dither color-atlas release"
        )
        release_root = campaign._decode(  # noqa: SLF001
            release_payload, label="dither color-atlas release"
        )
        campaign_file = Path(str(release_root["compiled_campaign"]["file"]))
        campaign_payload = campaign._read_regular(  # noqa: SLF001
            campaign_file, label="dither color-atlas campaign"
        )
        campaign_root = campaign._decode(  # noqa: SLF001
            campaign_payload, label="dither color-atlas campaign"
        )
    except (campaign.DitherColorAtlasCampaignError, KeyError, TypeError) as error:
        raise DitherColorAtlasPhysicalError(
            f"dither color-atlas release validation failed: {error}"
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
        return deepcopy(_dither_describe(context, ordinal))


def observation_template(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    _exact_release_gate(context)
    with _bound_engine():
        return deepcopy(_dither_observation_template(context, ordinal))


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
                context,
                args.evidence,
                claim_registry=args.claim_registry,
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
    except DitherColorAtlasPhysicalError as error:
        print(f"EC5 dither color-atlas physical error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if (
        args.command == "run"
        and isinstance(output, Mapping)
        and output.get("outcome") != "complete_pass"
    ):
        # The permanent claim has already been consumed.  Emit the sealed
        # evidence, then signal operators/automation that this is not success.
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
