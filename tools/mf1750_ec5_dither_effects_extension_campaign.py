#!/usr/bin/env python3
"""Build and seal the four-action factory-OTP dither-effects extension.

All commands in this module are offline.  The staged release binds the exact
campaign, firmware, panel, and test bundle but remains execution-ineligible.
Only ``finalize-real`` can create an execution-eligible release, and it first
replays the future completed dither-atlas ordinal-2 white result, observation,
and permanent claim.  Even the finalized release authorizes zero refreshes;
the physical runner still requires a fresh diagnostic and one exact human
authorization per action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_dither_color_atlas_campaign as common  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_physical_once as atlas_once  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_compiled_identity as compiled_gate  # noqa: E402
from tools import mf1750_ec5_dither_effects_extension_contract as contract  # noqa: E402
from tools import mf1750_ec5_dither_effects_suite as offline_bundle  # noqa: E402


SCHEMA_VERSION = 1
CAMPAIGN_KIND = "mf1750-ec5-dither-effects-extension-compiled-campaign"
STAGED_RELEASE_KIND = "mf1750-ec5-dither-effects-extension-staged-release"
RELEASE_KIND = "mf1750-ec5-dither-effects-extension-materialized-release"
STAGED_MODE = "OFFLINE_ARTIFACTS_BOUND_PREDECESSOR_EVIDENCE_PENDING"
REAL_MODE = "REAL_DITHER_ATLAS_ORDINAL2_WHITE_ANCHOR_VALIDATED"
ACTION_COUNT = 4
CAMPAIGN_ROUNDS = 1
WHITE_CHECKPOINT_ORDINALS = (2, 4)
RECOMMENDED_SAFE_STOP_ORDINALS = (2, 4)
FIRST_SAFE_STOP_ORDINAL = 2
FIRST_COMPLETE_ROUND_STOP_ORDINAL = 4
FIRST_FULL_ROUND_STOP_ORDINAL = 4
FIRST_PREDECESSOR_ACTION_ID = contract.PREDECESSOR_ACTION_ID
EXPECTED_PANEL_FILE_SHA256 = (
    "8d0f6202282c16cfb32246812f50aecc964f5acfd643b65b049672a43cc03b05"
)
EXPECTED_ATLAS_RELEASE_FILE_SHA256 = (
    "ec3e2d873badadef615b06b6a30948738ef80a4c4c3e31cbe24344454a037612"
)
EXPECTED_ATLAS_RELEASE_CANONICAL_SHA256 = (
    "68c5ffd09a9a46644e59493a985d21c2a035c5e21aba3324355ebd2eab5df7fe"
)
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
ENDPOINTS = {
    "version": "/api/ec5/dither-effects-extension/version",
    "manifest": "/api/ec5/dither-effects-extension/manifest",
    "status": "/api/ec5/dither-effects-extension/status",
    "report": "/api/ec5/dither-effects-extension/report",
    "arm": "/api/ec5/dither-effects-extension/arm",
    "execute": "/api/ec5/dither-effects-extension/execute",
}
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_DITHER_EFFECTS_EXTENSION_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_FACTORY_OTP_DITHER_EFFECTS_EXTENSION_ACTION_ONCE"
MUTATION_HEADERS = (
    "X-EC5-Build-Tag",
    "X-EC5-Test-Id",
    "X-EC5-Campaign-Id",
    "X-EC5-Action-Id",
    "X-EC5-Ordinal",
    "X-EC5-Descriptor-Id",
    "X-EC5-Boot-Nonce",
    "X-EC5-Intent",
    "X-EC5-Arm-Nonce",
)


class DitherEffectsExtensionCampaignError(RuntimeError):
    """An immutable campaign, release, artifact, or predecessor check failed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DitherEffectsExtensionCampaignError(
            f"value is not canonical JSON: {error}"
        ) from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def _read_regular(path: Path, *, label: str, maximum: int = 32_000_000) -> bytes:
    try:
        return common._read_regular(path, label=label, maximum=maximum)  # noqa: SLF001
    except common.DitherColorAtlasCampaignError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        return common._decode(payload, label=label)  # noqa: SLF001
    except common.DitherColorAtlasCampaignError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    try:
        return common._write_new(path, value)  # noqa: SLF001
    except common.DitherColorAtlasCampaignError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return root


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise DitherEffectsExtensionCampaignError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise DitherEffectsExtensionCampaignError(f"{label} integrity differs")
    return str(integrity["canonical_sha256"])


def _reference(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read_regular(path, label=label)
    root = _decode(payload, label=label)
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": _validate_seal(root, label=label),
    }


def _frame_identity(role: str) -> dict[str, Any]:
    identity = contract.ROLE_IDENTITIES[role]
    return {
        "layout_id": contract.LAYOUT_ID,
        "frame": {
            "bytes": identity["frame"]["bytes"],
            "sha256": identity["frame"]["sha256"],
            "fnv1a": identity["frame"]["fnv1a_hex"],
            "encoding": "canonical-row-major-two-4bit-codes-per-byte",
            "controllers": [
                {
                    "controller": "CS1",
                    "source_half": 0,
                    "bytes": identity["cs1_dtm"]["bytes"],
                    "sha256": identity["cs1_dtm"]["sha256"],
                    "fnv1a": identity["cs1_dtm"]["fnv1a_hex"],
                },
                {
                    "controller": "CS2",
                    "source_half": 1,
                    "bytes": identity["cs2_dtm"]["bytes"],
                    "sha256": identity["cs2_dtm"]["sha256"],
                    "fnv1a": identity["cs2_dtm"]["fnv1a_hex"],
                },
            ],
        },
        "profile_source": "factory_otp",
        "runtime_lut_write": False,
        "spatial_dithering": role
        in (contract.ROLE_PAIR_GRADIENTS, contract.ROLE_EFFECTS_CHART),
        "single_pixel_multi_pigment_claim": False,
        "physical_colour_claim": False,
    }


def build_actions() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for descriptor in contract.DESCRIPTORS:
        action = deepcopy(dict(descriptor))
        action["action_id"] = action["hardware_action_id"]
        action["frame"] = _frame_identity(str(action["role"]))
        actions.append(action)
    return actions


def build_campaign() -> dict[str, Any]:
    manifest = contract.campaign_manifest()
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CAMPAIGN_KIND,
            "identity_revision": contract.IDENTITY_REVISION,
            "classification": contract.CLASSIFICATION,
            "build_tag": contract.BUILD_TAG,
            "test_id": contract.TEST_ID,
            "device_api_version": contract.DEVICE_API_VERSION,
            "campaign_id": contract.CAMPAIGN_ID,
            "firmware_contract_id": manifest["contract_id"],
            "firmware_contract": manifest,
            "device_schema_version": contract.TOP_SCHEMA_VERSION,
            "driver_evidence_schema_version": contract.DRIVER_EVIDENCE_SCHEMA_VERSION,
            "first_predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
            "first_predecessor_kind": (
                "exact_finalized_dither_atlas_ordinal2_factory_otp_white"
            ),
            "action_count": ACTION_COUNT,
            "campaign_rounds": CAMPAIGN_ROUNDS,
            "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
            "white_checkpoint_ordinals": list(WHITE_CHECKPOINT_ORDINALS),
            "recommended_safe_stop_ordinals": list(RECOMMENDED_SAFE_STOP_ORDINALS),
            "first_complete_round_stop_ordinal": FIRST_COMPLETE_ROUND_STOP_ORDINAL,
            "nvs_contract": {
                "namespace": contract.NVS_NAMESPACE,
                "key": contract.NVS_KEY,
                "ordinal_base": 1,
                "initial_next_ordinal": 1,
                "terminal_next_ordinal": ACTION_COUNT + 1,
                "phase_encoding": ["READY", "ARMED", "CONSUMED", "FAULT"],
            },
            "device_contract": {
                "endpoints": ENDPOINTS,
                "mutation_headers": list(MUTATION_HEADERS),
                "arm_intent": ARM_INTENT,
                "execute_intent": EXECUTE_INTENT,
                "maximum_arm_posts_per_action": 1,
                "maximum_execute_posts_per_action": 1,
                "automatic_chaining": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "startup_refresh": False,
                "raw_frame_ingress": False,
                "same_firmware_without_reset_or_reflash": True,
            },
            "actions": build_actions(),
            "classification_contract": {
                "profile_source": "factory_otp",
                "runtime_lut_or_waveform_changed": False,
                "spatial_dither_effects": True,
                "single_pixel_multi_pigment_claim": False,
                "physical_colour_claim": False,
                "device_accessed_by_this_compiler": False,
                "visible_refresh_authorized_by_this_compiler": False,
            },
        }
    )


def generate_campaign(output_file: Path) -> dict[str, Any]:
    root = build_campaign()
    _write_new(output_file, root)
    return root


def validate_campaign(manifest_file: Path) -> dict[str, Any]:
    payload = _read_regular(manifest_file, label="dither-effects campaign")
    root = _decode(payload, label="dither-effects campaign")
    canonical = _validate_seal(root, label="dither-effects campaign")
    if dict(root) != build_campaign():
        raise DitherEffectsExtensionCampaignError(
            "compiled dither-effects campaign differs"
        )
    return {
        "file": str(Path(manifest_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "action_count": ACTION_COUNT,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "actions": deepcopy(root["actions"]),
    }


def _panel(path: Path) -> dict[str, str]:
    try:
        return common._panel(path)  # noqa: SLF001
    except common.DitherColorAtlasCampaignError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error


def _artifact(path: Path, *, label: str, maximum: int) -> dict[str, Any]:
    payload = _read_regular(path, label=label, maximum=maximum)
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "sha256": sha256(payload),
    }


def _validate_artifact(value: Any, *, label: str, maximum: int) -> bytes:
    if not isinstance(value, Mapping) or set(value) != {"file", "bytes", "sha256"}:
        raise DitherEffectsExtensionCampaignError(f"{label} reference differs")
    payload = _read_regular(Path(str(value["file"])), label=label, maximum=maximum)
    if value["bytes"] != len(payload) or value["sha256"] != sha256(payload):
        raise DitherEffectsExtensionCampaignError(f"{label} bytes differ")
    return payload


def _bundle(path: Path) -> dict[str, Any]:
    try:
        checked = offline_bundle.validate_bundle(path)
    except offline_bundle.DitherEffectsBundleError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error
    if (
        checked.get("hardware_tested") is not False
        or checked.get("visible_refresh_authorized") is not False
        or checked.get("device_io_performed") is not False
    ):
        raise DitherEffectsExtensionCampaignError("extension bundle safety differs")
    return deepcopy(dict(checked))


def _atlas_release_reference(path: Path, panel: Mapping[str, str]) -> dict[str, Any]:
    try:
        checked = common.validate_materialized_release(path)
    except common.DitherColorAtlasCampaignError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error
    if (
        checked.get("file_sha256") != EXPECTED_ATLAS_RELEASE_FILE_SHA256
        or checked.get("canonical_sha256") != EXPECTED_ATLAS_RELEASE_CANONICAL_SHA256
        or checked.get("predecessor_action_id") == FIRST_PREDECESSOR_ACTION_ID
    ):
        raise DitherEffectsExtensionCampaignError(
            "dither-atlas release identity differs"
        )
    payload = _read_regular(path, label="dither-atlas release")
    root = _decode(payload, label="dither-atlas release")
    if root.get("panel") != panel:
        raise DitherEffectsExtensionCampaignError("panel differs from atlas release")
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": str(root["integrity"]["canonical_sha256"]),
    }


def _safety() -> dict[str, Any]:
    return {
        "profile_source": "factory_otp",
        "spatial_dithering_only": True,
        "runtime_lut_or_waveform_write": False,
        "electrical_parameter_write": False,
        "new_nvs_namespace_and_key": True,
        "global_nvs_clear": False,
        "wifi_credentials_preserved": True,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "one_exact_human_authorization_required_per_action": True,
        "same_boot_and_no_intervening_refresh_required": True,
        "materializer_device_access_performed": False,
        "materializer_network_requests": 0,
        "materializer_visible_refreshes": 0,
        "visible_refresh_authorized_by_release": 0,
    }


def materialize_staged_release(
    *,
    campaign_file: Path,
    firmware_binary: Path,
    firmware_elf: Path,
    panel_file: Path,
    offline_bundle_dir: Path,
    atlas_release_file: Path,
    output_file: Path,
) -> dict[str, Any]:
    checked_campaign = validate_campaign(campaign_file)
    try:
        compiled = compiled_gate.validate_artifacts(firmware_elf, firmware_binary)
    except compiled_gate.DitherEffectsExtensionCompiledIdentityError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error
    binary = _artifact(
        firmware_binary, label="extension firmware BIN", maximum=4_000_000
    )
    elf = _artifact(firmware_elf, label="extension firmware ELF", maximum=32_000_000)
    panel_payload = _read_regular(panel_file, label="live panel identity")
    if sha256(panel_payload) != EXPECTED_PANEL_FILE_SHA256:
        raise DitherEffectsExtensionCampaignError("live panel identity file differs")
    panel = _panel(panel_file)
    bundle = _bundle(offline_bundle_dir)
    atlas_release = _atlas_release_reference(atlas_release_file, panel)
    root = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": STAGED_RELEASE_KIND,
            "evidence_mode": STAGED_MODE,
            "compiled_campaign": {
                key: checked_campaign[key]
                for key in (
                    "file",
                    "bytes",
                    "file_sha256",
                    "canonical_sha256",
                    "action_count",
                    "first_safe_stop_ordinal",
                )
            },
            "firmware": {"binary": binary, "elf": elf},
            "compiled_identity": compiled,
            "offline_effects_bundle": bundle,
            "panel": panel,
            "panel_file": {
                "file": str(Path(panel_file).resolve()),
                "file_sha256": sha256(panel_payload),
            },
            "predecessor_requirement": {
                "kind": "future_finalized_dither_atlas_ordinal2_clean_white",
                "atlas_release": atlas_release,
                "campaign_id": contract.PREDECESSOR_CAMPAIGN_ID,
                "ordinal": contract.PREDECESSOR_ORDINAL,
                "role": contract.PREDECESSOR_ROLE,
                "action_id": FIRST_PREDECESSOR_ACTION_ID,
                "result_required": True,
                "manual_observation_required": True,
                "permanent_claim_required": True,
                "clean_white_required": True,
                "status": "PENDING_FUTURE_VISIBLE_ACTION_EVIDENCE",
            },
            "execution_eligible": False,
            "live_authorized": False,
            "safety": _safety(),
            "state": (
                "OFFLINE_DITHER_EFFECTS_EXTENSION_READY_AWAITING_"
                "DITHER_ATLAS_ORDINAL2_WHITE_EVIDENCE"
            ),
        }
    )
    _write_new(output_file, root)
    validate_staged_release(output_file)
    return root


def validate_staged_release(release_file: Path) -> dict[str, Any]:
    payload = _read_regular(release_file, label="staged extension release")
    root = _decode(payload, label="staged extension release")
    canonical = _validate_seal(root, label="staged extension release")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != STAGED_RELEASE_KIND
        or root.get("evidence_mode") != STAGED_MODE
        or root.get("execution_eligible") is not False
        or root.get("live_authorized") is not False
        or root.get("safety") != _safety()
    ):
        raise DitherEffectsExtensionCampaignError("staged release identity differs")
    compiled_ref = root.get("compiled_campaign")
    if not isinstance(compiled_ref, Mapping):
        raise DitherEffectsExtensionCampaignError("campaign reference is absent")
    checked_campaign = validate_campaign(Path(str(compiled_ref.get("file"))))
    expected_campaign = {
        key: checked_campaign[key]
        for key in (
            "file",
            "bytes",
            "file_sha256",
            "canonical_sha256",
            "action_count",
            "first_safe_stop_ordinal",
        )
    }
    if dict(compiled_ref) != expected_campaign:
        raise DitherEffectsExtensionCampaignError("campaign reference differs")
    firmware = root.get("firmware")
    if not isinstance(firmware, Mapping) or set(firmware) != {"binary", "elf"}:
        raise DitherEffectsExtensionCampaignError("firmware references differ")
    binary = _validate_artifact(
        firmware["binary"], label="extension firmware BIN", maximum=4_000_000
    )
    elf = _validate_artifact(
        firmware["elf"], label="extension firmware ELF", maximum=32_000_000
    )
    try:
        replayed_compiled = compiled_gate.validate_artifacts(
            Path(str(firmware["elf"]["file"])),
            Path(str(firmware["binary"]["file"])),
        )
    except compiled_gate.DitherEffectsExtensionCompiledIdentityError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error
    if root.get("compiled_identity") != replayed_compiled:
        raise DitherEffectsExtensionCampaignError("compiled identity differs")
    if (
        len(binary) != firmware["binary"]["bytes"]
        or len(elf) != firmware["elf"]["bytes"]
    ):
        raise DitherEffectsExtensionCampaignError("firmware length replay differs")
    bundle = root.get("offline_effects_bundle")
    if not isinstance(bundle, Mapping) or bundle.get("bundle") is None:
        raise DitherEffectsExtensionCampaignError("offline bundle is absent")
    if dict(bundle) != _bundle(Path(str(bundle["bundle"]))):
        raise DitherEffectsExtensionCampaignError("offline bundle differs")
    panel_file = root.get("panel_file")
    if not isinstance(panel_file, Mapping) or set(panel_file) != {
        "file",
        "file_sha256",
    }:
        raise DitherEffectsExtensionCampaignError("panel reference differs")
    panel_path = Path(str(panel_file["file"]))
    panel_payload = _read_regular(panel_path, label="live panel identity")
    if (
        panel_file["file_sha256"] != sha256(panel_payload)
        or panel_file["file_sha256"] != EXPECTED_PANEL_FILE_SHA256
        or root.get("panel") != _panel(panel_path)
    ):
        raise DitherEffectsExtensionCampaignError("panel identity differs")
    predecessor = root.get("predecessor_requirement")
    if not isinstance(predecessor, Mapping):
        raise DitherEffectsExtensionCampaignError("predecessor requirement absent")
    expected_atlas = _atlas_release_reference(
        Path(str(predecessor.get("atlas_release", {}).get("file"))),
        root["panel"],
    )
    if predecessor != {
        "kind": "future_finalized_dither_atlas_ordinal2_clean_white",
        "atlas_release": expected_atlas,
        "campaign_id": contract.PREDECESSOR_CAMPAIGN_ID,
        "ordinal": contract.PREDECESSOR_ORDINAL,
        "role": contract.PREDECESSOR_ROLE,
        "action_id": FIRST_PREDECESSOR_ACTION_ID,
        "result_required": True,
        "manual_observation_required": True,
        "permanent_claim_required": True,
        "clean_white_required": True,
        "status": "PENDING_FUTURE_VISIBLE_ACTION_EVIDENCE",
    }:
        raise DitherEffectsExtensionCampaignError("predecessor requirement differs")
    return {
        "file": str(Path(release_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "execution_eligible": False,
        "live_authorized": False,
        "action_count": ACTION_COUNT,
        "firmware_binary_sha256": sha256(binary),
        "firmware_elf_sha256": sha256(elf),
        "predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "predecessor_evidence_pending": True,
        "visible_refresh_authorized_by_release": 0,
    }


def _predecessor_binding(
    *,
    staged: Mapping[str, Any],
    result_file: Path,
    observation_file: Path,
    claim_registry: Path,
) -> dict[str, Any]:
    requirement = staged["predecessor_requirement"]
    atlas_release = Path(str(requirement["atlas_release"]["file"]))
    try:
        context = atlas_once.load_release(atlas_release)
        result = atlas_once.validate_result(
            context, result_file, claim_registry=claim_registry
        )
        observation = atlas_once.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )
    except atlas_once.DitherColorAtlasPhysicalError as error:
        raise DitherEffectsExtensionCampaignError(str(error)) from error
    if (
        result.get("ordinal") != contract.PREDECESSOR_ORDINAL
        or result.get("outcome") != "complete_pass"
        or result.get("state") != "authorization_permanently_consumed_do_not_rerun"
        or result.get("action", {}).get("action_id") != FIRST_PREDECESSOR_ACTION_ID
        or result.get("action", {}).get("role") != contract.PREDECESSOR_ROLE
        or observation.get("ordinal") != contract.PREDECESSOR_ORDINAL
        or observation.get("sequence_gate_pass") is not True
        or observation.get("visual", {}).get("full_clean_white") is not True
        or observation.get("visual", {}).get("no_unexpected_residual") is not True
    ):
        raise DitherEffectsExtensionCampaignError(
            "dither-atlas ordinal2 predecessor is not finalized clean white"
        )
    claim = result.get("claim")
    if not isinstance(claim, Mapping) or not isinstance(claim.get("file"), str):
        raise DitherEffectsExtensionCampaignError("predecessor claim is absent")
    claim_payload = _read_regular(Path(str(claim["file"])), label="atlas white claim")
    if claim.get("file_sha256") != sha256(claim_payload):
        raise DitherEffectsExtensionCampaignError("predecessor claim bytes differ")
    return {
        "kind": "exact_finalized_dither_atlas_ordinal2_clean_white",
        "atlas_release": deepcopy(dict(requirement["atlas_release"])),
        "result": _reference(result_file, label="atlas white result"),
        "observation": _reference(observation_file, label="atlas white observation"),
        "claim": deepcopy(dict(claim)),
        "claim_registry": {
            "directory": str(Path(claim_registry).resolve()),
            "registry_id": atlas_once.CLAIM_REGISTRY_ID,
        },
        "campaign_id": contract.PREDECESSOR_CAMPAIGN_ID,
        "ordinal": contract.PREDECESSOR_ORDINAL,
        "role": contract.PREDECESSOR_ROLE,
        "action_id": FIRST_PREDECESSOR_ACTION_ID,
        "required_previous_boot_nonce": result["preflight"]["boot_nonce"],
        "latest_visible_state": "clean_full_white_factory_otp",
        "clean_white_confirmed": True,
        "manual_no_intervening_refresh_confirmation_required": True,
        "panel": deepcopy(dict(staged["panel"])),
    }


def materialize_real_release(
    *,
    staged_release_file: Path,
    anchor_result_file: Path,
    anchor_observation_file: Path,
    anchor_claim_registry: Path,
    output_file: Path,
) -> dict[str, Any]:
    validate_staged_release(staged_release_file)
    staged_payload = _read_regular(
        staged_release_file, label="staged extension release"
    )
    staged = _decode(staged_payload, label="staged extension release")
    predecessor = _predecessor_binding(
        staged=staged,
        result_file=anchor_result_file,
        observation_file=anchor_observation_file,
        claim_registry=anchor_claim_registry,
    )
    root = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RELEASE_KIND,
            "evidence_mode": REAL_MODE,
            "staged_release": _reference(
                staged_release_file, label="staged extension release"
            ),
            "compiled_campaign": deepcopy(dict(staged["compiled_campaign"])),
            "firmware": deepcopy(dict(staged["firmware"])),
            "compiled_identity": deepcopy(dict(staged["compiled_identity"])),
            "offline_effects_bundle": deepcopy(dict(staged["offline_effects_bundle"])),
            "panel": deepcopy(dict(staged["panel"])),
            "panel_file": deepcopy(dict(staged["panel_file"])),
            "predecessor_binding": predecessor,
            "execution_eligible": True,
            "live_authorized": False,
            "safety": _safety(),
            "state": (
                "REAL_FACTORY_OTP_DITHER_EFFECTS_EXTENSION_RELEASE_READY_"
                "FOR_J2_OFF_PREFLIGHT_ONLY"
            ),
        }
    )
    _write_new(output_file, root)
    validate_materialized_release(output_file)
    return root


def validate_materialized_release(release_file: Path) -> dict[str, Any]:
    payload = _read_regular(release_file, label="real extension release")
    root = _decode(payload, label="real extension release")
    canonical = _validate_seal(root, label="real extension release")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != RELEASE_KIND
        or root.get("evidence_mode") != REAL_MODE
        or root.get("execution_eligible") is not True
        or root.get("live_authorized") is not False
        or root.get("safety") != _safety()
    ):
        raise DitherEffectsExtensionCampaignError("real release identity differs")
    staged_ref = root.get("staged_release")
    if not isinstance(staged_ref, Mapping) or not isinstance(
        staged_ref.get("file"), str
    ):
        raise DitherEffectsExtensionCampaignError("staged release reference absent")
    checked_staged = validate_staged_release(Path(str(staged_ref["file"])))
    expected_ref = _reference(
        Path(str(staged_ref["file"])), label="staged extension release"
    )
    if dict(staged_ref) != expected_ref:
        raise DitherEffectsExtensionCampaignError("staged release reference differs")
    staged_payload = _read_regular(
        Path(str(staged_ref["file"])), label="staged extension release"
    )
    staged = _decode(staged_payload, label="staged extension release")
    for key in (
        "compiled_campaign",
        "firmware",
        "compiled_identity",
        "offline_effects_bundle",
        "panel",
        "panel_file",
    ):
        if root.get(key) != staged.get(key):
            raise DitherEffectsExtensionCampaignError(f"real release {key} differs")
    predecessor = root.get("predecessor_binding")
    if not isinstance(predecessor, Mapping):
        raise DitherEffectsExtensionCampaignError("predecessor binding absent")
    registry = predecessor.get("claim_registry")
    if not isinstance(registry, Mapping):
        raise DitherEffectsExtensionCampaignError("claim registry binding absent")
    replayed = _predecessor_binding(
        staged=staged,
        result_file=Path(str(predecessor.get("result", {}).get("file"))),
        observation_file=Path(str(predecessor.get("observation", {}).get("file"))),
        claim_registry=Path(str(registry.get("directory"))),
    )
    if dict(predecessor) != replayed:
        raise DitherEffectsExtensionCampaignError("predecessor binding differs")
    firmware = staged["firmware"]
    return {
        "file": str(Path(release_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "execution_eligible": True,
        "live_authorized": False,
        "evidence_mode": REAL_MODE,
        "action_count": ACTION_COUNT,
        "firmware_binary_sha256": firmware["binary"]["sha256"],
        "firmware_elf_sha256": firmware["elf"]["sha256"],
        "predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "staged_release_file_sha256": checked_staged["file_sha256"],
        "visible_refresh_authorized_by_release": 0,
    }


def required_authorization(action: Mapping[str, Any]) -> str:
    ordinal = action.get("ordinal")
    action_id = action.get("action_id")
    if (
        isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or not isinstance(action_id, str)
    ):
        raise DitherEffectsExtensionCampaignError("action is malformed")
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_DITHER_EFFECTS_ORDINAL_{ordinal:02d}__"
        f"ACTION_{action_id.upper()}{AUTHORIZATION_SUFFIX}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-campaign", allow_abbrev=False)
    generate.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate-campaign", allow_abbrev=False)
    validate.add_argument("--campaign", type=Path, required=True)
    staged = commands.add_parser("materialize-staged", allow_abbrev=False)
    staged.add_argument("--campaign", type=Path, required=True)
    staged.add_argument("--firmware-binary", type=Path, required=True)
    staged.add_argument("--firmware-elf", type=Path, required=True)
    staged.add_argument("--panel", type=Path, required=True)
    staged.add_argument("--offline-bundle", type=Path, required=True)
    staged.add_argument("--atlas-release", type=Path, required=True)
    staged.add_argument("--output", type=Path, required=True)
    validate_staged = commands.add_parser("validate-staged", allow_abbrev=False)
    validate_staged.add_argument("--release", type=Path, required=True)
    finalize = commands.add_parser("finalize-real", allow_abbrev=False)
    finalize.add_argument("--staged-release", type=Path, required=True)
    finalize.add_argument("--anchor-result", type=Path, required=True)
    finalize.add_argument("--anchor-observation", type=Path, required=True)
    finalize.add_argument("--anchor-claim-registry", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    validate_real = commands.add_parser("validate-real", allow_abbrev=False)
    validate_real.add_argument("--release", type=Path, required=True)
    auth = commands.add_parser("authorization", allow_abbrev=False)
    auth.add_argument("--ordinal", type=int, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate-campaign":
            root = generate_campaign(args.output)
            output: Any = {
                "file": str(args.output.resolve()),
                "file_sha256": sha256(args.output.read_bytes()),
                "canonical_sha256": root["integrity"]["canonical_sha256"],
            }
        elif args.command == "validate-campaign":
            output = validate_campaign(args.campaign)
        elif args.command == "materialize-staged":
            root = materialize_staged_release(
                campaign_file=args.campaign,
                firmware_binary=args.firmware_binary,
                firmware_elf=args.firmware_elf,
                panel_file=args.panel,
                offline_bundle_dir=args.offline_bundle,
                atlas_release_file=args.atlas_release,
                output_file=args.output,
            )
            output = validate_staged_release(args.output)
        elif args.command == "validate-staged":
            output = validate_staged_release(args.release)
        elif args.command == "finalize-real":
            materialize_real_release(
                staged_release_file=args.staged_release,
                anchor_result_file=args.anchor_result,
                anchor_observation_file=args.anchor_observation,
                anchor_claim_registry=args.anchor_claim_registry,
                output_file=args.output,
            )
            output = validate_materialized_release(args.output)
        elif args.command == "validate-real":
            output = validate_materialized_release(args.release)
        else:
            if not 1 <= args.ordinal <= ACTION_COUNT:
                raise DitherEffectsExtensionCampaignError("ordinal outside 1..4")
            output = required_authorization(build_actions()[args.ordinal - 1])
    except (DitherEffectsExtensionCampaignError, OSError) as error:
        print(f"EC5 dither-effects campaign error: {error}", file=sys.stderr)
        return 2
    if isinstance(output, str):
        print(output)
    else:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
