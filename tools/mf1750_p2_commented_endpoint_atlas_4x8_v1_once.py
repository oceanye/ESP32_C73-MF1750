#!/usr/bin/env python3
"""Fail-closed one-shot host for the fresh P2 commented/commented atlas."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import ipaddress
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib import parse as urllib_parse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402


_TEMPLATE_PATH = Path(__file__).with_name(
    "mf1750_p1_active_endpoint_atlas_4x8_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_p2_commented_endpoint_atlas_4x8_v1_private_template",
    _TEMPLATE_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load frozen one-shot template: {_TEMPLATE_PATH}")
template = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(template)


REPORT = pack.build_report()
template.pack = pack
template.REPORT = REPORT
template.ARTIFACTS = pack.ARTIFACTS
template.BUILD_DIR = pack.BUILD_DIR
base = template.base
host = template.host
v1 = template.v1
host.pack = pack
host.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = pack.ARTIFACTS["firmware.bin"]["sha256"]
base.runner.FIRMWARE_BYTES = pack.ARTIFACTS["firmware.bin"]["bytes"]
base.runner.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_P2_COMMENTED_ENDPOINT_ATLAS_NOT_HARDWARE_AUTHORIZATION"
base.runner.EXECUTE_INTENT = "EXECUTE_ONE_ARMED_P2_COMMENTED_ENDPOINT_ATLAS_ONCE"
base.runner.ACTIONS = template._runner_actions()  # noqa: SLF001
base.runner.DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in base.runner.ACTIONS)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = REPO_ROOT / ".test-output/hardware/.mf1750_p2_commented_endpoint_atlas_4x8_v1_claims"
base.runner.DEFAULT_OUTPUT = REPO_ROOT / ".test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1"
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
RUN_ADMISSION_OUTPUT = base.runner.DEFAULT_OUTPUT / "action-01-live-admission.json"
ACTION_OUTPUTS = {1: base.runner.DEFAULT_OUTPUT / "action-01-commented-complete-position-balanced-4x8-endpoint-atlas.json"}
RETAINED_CLEAN_WHITE_REVIEW = (
    base.runner.DEFAULT_OUTPUT
    / "source-p1-white-successor-retained-clean-white-review-20260904.json"
)
template.DIAGNOSTIC_OUTPUT = DIAGNOSTIC_OUTPUT
template.RUN_ADMISSION_OUTPUT = RUN_ADMISSION_OUTPUT
template.ACTION_OUTPUTS = ACTION_OUTPUTS

_p1_validate_capabilities = template._validate_capabilities  # noqa: SLF001
_p1_validate_version = template._validate_version  # noqa: SLF001
_p1_validate_manifest = template._validate_manifest  # noqa: SLF001
_p1_validate_ready_status = template._validate_ready_status  # noqa: SLF001
_p1_validate_complete_report = template._validate_complete_report  # noqa: SLF001
_p1_validate_prior_terminal_report = template._validate_prior_terminal_report  # noqa: SLF001
_p1_validate_fresh_no_execute_report = getattr(
    v1, "_validate_fresh_no_execute_report", None
)


# The P1 template historically bound live traffic to one old DHCP address.
# P2 deliberately does not inherit that address: a fresh binding record is the
# authority for the current private IPv4.  The MAC is the one stable hardware
# identity that remains fixed for this campaign.
EXPECTED_DEVICE_MAC = "A4-CB-8F-D9-FC-D4"
_MAC_RE = re.compile(r"^[0-9A-F]{2}(?:-[0-9A-F]{2}){5}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{16}$")
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_FRESH_NEIGHBOUR_STATES = frozenset(
    {"REACHABLE", "DELAY", "PROBE", "PERMANENT"}
)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("P2 manifest root differs")
    adjusted = deepcopy(value)
    layout = adjusted.get("history_layout")
    if (
        not isinstance(layout, dict)
        or "commented_global_tuple_id" not in layout
        or "active_global_tuple_id" in layout
    ):
        raise base.runner.RecheckError(
            "P2 manifest requires exactly one commented_global_tuple_id"
        )
    layout["active_global_tuple_id"] = layout.pop("commented_global_tuple_id")
    _p1_validate_manifest(adjusted)
    profile = pack.commented_profile()
    if value.get("profile_source") != (
        "legacy_complete_535_commented_symmetric_controller_tuple"
    ):
        raise base.runner.RecheckError("P2 commented profile source differs")
    # ``global_header`` is present in some firmware surfaces (and absent from
    # the version surface), but when emitted it must never identify the active
    # tuple.  The action and waveform records are mandatory identity anchors.
    if value.get("global_header") not in (None, "commented"):
        # These fields are emitted by the P2 firmware and make an active
        # profile accidentally masquerading as a commented one impossible.
        raise base.runner.RecheckError("P2 commented profile identity differs")
    actions = value.get("actions")
    if not isinstance(actions, list) or len(actions) != 1:
        raise base.runner.RecheckError("P2 manifest action surface differs")
    action = actions[0]
    if (
        not isinstance(action, Mapping)
        or action.get("global_header") != "commented"
        or action.get("profile_id") != profile["id"]
        or action.get("global_tuple_id") != profile["global_tuple_id"]
        or action.get("waveform_binding") != profile
    ):
        raise base.runner.RecheckError("P2 manifest commented action identity differs")


template._validate_manifest = _validate_manifest  # noqa: SLF001

SOURCE_WHITE_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/"
    "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_20260901_V2"
)
SOURCE_WHITE_CLAIM_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/"
    ".mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v2_claims"
)
SOURCE_WHITE_CAMPAIGN_ID = (
    "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_WHITE_CONTRACT_ID = (
    "403dc7e4c0efab105eddbe3039c32f1b563494cc866410046f3038fec2bf09ab"
)
SOURCE_WHITE_DESCRIPTOR_ID = (
    "4e921326c729bb66d744237662abe63604648834b68d4e82085c4284edb2cf9c"
)
SOURCE_WHITE_ACTION_ID = (
    "b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc"
)
SOURCE_WHITE_BOOT_NONCE = "4d7868e0c07e8cb7"
SOURCE_WHITE_FIRMWARE_SHA256 = (
    "4f67f065993dfce3f6ffaeb2b5afb5a89f82c4563c9ad83b79c505311af24ef3"
)
SOURCE_WHITE_ELF_SHA256 = (
    "cc3f9131b8b92e41e6b73c973b270837beed19a86b22cdc6f72f0107dd8d642e"
)
SOURCE_P1_ACTION_ID = (
    "7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526"
)
SOURCE_BINDINGS: dict[str, dict[str, Any]] = {
    "white_result": {
        "path": SOURCE_WHITE_ROOT / "action-01-factory-otp-white.json",
        "bytes": 38_142,
        "file_sha256": (
            "9e678853e4259a245c69194d99ca959c7af31169b3a9153bae858a6614c3a030"
        ),
        "canonical_sha256": (
            "25ac33be96a2e243ce866fcfd277d9094ac6790dae77380bce913a00227784a9"
        ),
    },
    "white_claim": {
        "path": SOURCE_WHITE_CLAIM_ROOT / f"{SOURCE_WHITE_ACTION_ID}.json",
        "bytes": 3_967,
        "file_sha256": (
            "83263373f394ac1d222ceaccd8a4e38edfbfd473ac2d4d5fcef3d3f44c78d666"
        ),
        "canonical_sha256": (
            "93401458684fd67ec6b9a0f866f3b60abc4d24f5b857f2583f81fb187e605579"
        ),
    },
    "source_gate": {
        "path": SOURCE_WHITE_ROOT / "source-terminal-gate.json",
        "bytes": 2_537,
        "file_sha256": (
            "4f225c5d5965ce90fba0981e864e44e462214e93822ccd8e73159ccfadbc84d0"
        ),
        "canonical_sha256": (
            "ab039cb0622c747de2786b04e2b10678caa2a770e9208f8783e73815cac2e841"
        ),
    },
    "relay_off": {
        "path": SOURCE_WHITE_ROOT / "relay-post-white-off-20260901-210454819.json",
        "bytes": 1_802,
        "file_sha256": (
            "b978d1416c1f5d8f8e534384d848006869ff629fd7715b9c1342206b7dab8618"
        ),
        "canonical_sha256": (
            "b2eb110ff7f87ba4c4d96e3f1e73c55e6c2644f741301e705756e8e39d0a46fd"
        ),
    },
}


def _read_source_binding(name: str) -> dict[str, Any]:
    binding = SOURCE_BINDINGS[name]
    return template._read_exact_json(  # noqa: SLF001
        Path(binding["path"]),
        byte_count=int(binding["bytes"]),
        file_sha256=str(binding["file_sha256"]),
        canonical_sha256=str(binding["canonical_sha256"]),
        label=f"P2-C latest P1 white {name}",
    )


def _source_file_evidence(name: str) -> dict[str, Any]:
    binding = SOURCE_BINDINGS[name]
    return {
        "path": template._repo_relative(Path(binding["path"])),  # noqa: SLF001
        "bytes": binding["bytes"],
        "file_sha256": binding["file_sha256"],
        "canonical_sha256": binding["canonical_sha256"],
    }


def validate_source_white_authority() -> dict[str, Any]:
    """Deeply bind the latest completed P1 white result, claim, and relay OFF."""

    result = _read_source_binding("white_result")
    claim = _read_source_binding("white_claim")
    gate = _read_source_binding("source_gate")
    relay = _read_source_binding("relay_off")
    action = result.get("action")
    terminal = result.get("terminal_report")
    driver = terminal.get("driver") if isinstance(terminal, Mapping) else None
    safe = driver.get("busy_trace", {}).get("safe_finish") if isinstance(driver, Mapping) else None
    expected_action = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "descriptor_id": SOURCE_WHITE_DESCRIPTOR_ID,
        "action_id": SOURCE_WHITE_ACTION_ID,
        "frame_sha256": "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "cs1_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "cs2_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    }
    if (
        result.get("kind")
        != "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-v1-result"
        or result.get("outcome") != "complete_pass"
        or result.get("firmware_sha256") != SOURCE_WHITE_FIRMWARE_SHA256
        or result.get("running_app_elf_sha256") != SOURCE_WHITE_ELF_SHA256
        or result.get("boot_nonce") != SOURCE_WHITE_BOOT_NONCE
        or action != expected_action
        or result.get("visible_refreshes") != 1
        or result.get("no_retry") is not True
        or result.get("no_recovery") is not True
        or result.get("no_autochain") is not True
        or result.get("claim_state") != "permanently_consumed_by_this_invocation"
        or Path(str(result.get("claim_file", ""))).resolve()
        != Path(SOURCE_BINDINGS["white_claim"]["path"]).resolve()
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("valid") is not True
        or terminal.get("result") is not True
        or terminal.get("campaign_id") != SOURCE_WHITE_CAMPAIGN_ID
        or terminal.get("contract_id") != SOURCE_WHITE_CONTRACT_ID
        or terminal.get("descriptor_id", SOURCE_WHITE_DESCRIPTOR_ID)
        != SOURCE_WHITE_DESCRIPTOR_ID
        or terminal.get("action_id") != SOURCE_WHITE_ACTION_ID
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("campaign_complete") is not True
        or not isinstance(driver, Mapping)
        or driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("busy_assertion_missing") is not False
        or driver.get("pre_command_idle_failure") is not False
        or driver.get("pon_busy_seen") is not True
        or driver.get("drf_busy_seen") is not True
        or driver.get("pof_busy_seen") is not True
        or not isinstance(safe, Mapping)
        or safe.get("busy_before_pins_low") != 1
        or safe.get("busy_after_pins_low") != 1
        or safe.get("busy_after_5ms") != 1
    ):
        raise base.runner.RecheckError("latest P1 white COMPLETE evidence differs")
    if (
        claim.get("kind")
        != "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-v1-claim"
        or claim.get("action") != expected_action
        or claim.get("boot_nonce") != SOURCE_WHITE_BOOT_NONCE
        or claim.get("firmware_sha256") != SOURCE_WHITE_FIRMWARE_SHA256
        or claim.get("running_app_elf_sha256") != SOURCE_WHITE_ELF_SHA256
        or claim.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or claim.get("write_contract") != "O_EXCL"
        or claim.get("no_retry") is not True
        or claim.get("no_recovery") is not True
        or claim.get("no_autochain") is not True
        or claim.get("preflight", {}).get("fresh_nvs") is not True
        or claim.get("preflight", {}).get("get") != 4
        or claim.get("preflight", {}).get("post") != 0
    ):
        raise base.runner.RecheckError("latest P1 white permanent claim differs")
    selected = gate.get("selected_source_terminal_evidence")
    if (
        gate.get("kind")
        != "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-v2-host-source-gate"
        or gate.get("white_campaign_id") != SOURCE_WHITE_CAMPAIGN_ID
        or gate.get("white_contract_id") != SOURCE_WHITE_CONTRACT_ID
        or gate.get("white_descriptor_id") != SOURCE_WHITE_DESCRIPTOR_ID
        or gate.get("white_action_id") != SOURCE_WHITE_ACTION_ID
        or gate.get("write_contract") != "O_EXCL"
        or gate.get("no_retry") is not True
        or gate.get("no_recovery") is not True
        or gate.get("no_autochain") is not True
        or not isinstance(selected, Mapping)
        or selected.get("terminal_state") != "COMPLETE"
        or selected.get("action_id") != SOURCE_P1_ACTION_ID
        or selected.get("verified") is not True
    ):
        raise base.runner.RecheckError("latest P1 white source gate differs")
    if (
        relay.get("kind") != "mf17506-zave-relay-exact-bound-switch-receipt"
        or relay.get("channel") != 1
        or relay.get("contact_path") != "COM1-NO1"
        or relay.get("target_state") != "OFF"
        or relay.get("commanded_state") != "OFF"
        or relay.get("target_gate_passed") is not True
        or relay.get("off_gate_passed") is not True
        or relay.get("contact_switch_performed") is not True
        or relay.get("automatic_retry_performed") is not False
        or relay.get("automatic_recovery_performed") is not False
        or relay.get("electrical_state_proven") is not False
    ):
        raise base.runner.RecheckError("latest P1 white relay-OFF receipt differs")
    return {
        "kind": "mf1750-p2-latest-p1-white-successor-machine-authority-v1",
        "sealed": True,
        "state": "LATEST_P1_WHITE_COMPLETE_CLAIM_AND_RELAY_OFF_DEEPLY_VALIDATED",
        "source_campaign_id": SOURCE_WHITE_CAMPAIGN_ID,
        "source_contract_id": SOURCE_WHITE_CONTRACT_ID,
        "source_descriptor_id": SOURCE_WHITE_DESCRIPTOR_ID,
        "source_action_id": SOURCE_WHITE_ACTION_ID,
        "source_boot_nonce": SOURCE_WHITE_BOOT_NONCE,
        "source_firmware_sha256": SOURCE_WHITE_FIRMWARE_SHA256,
        "source_elf_sha256": SOURCE_WHITE_ELF_SHA256,
        "source_p1_action_id": SOURCE_P1_ACTION_ID,
        "files": {name: _source_file_evidence(name) for name in SOURCE_BINDINGS},
        "relay_off_commanded_and_queried": True,
        "electrical_state_proven": False,
        "retained_clean_white_review_required": True,
        "retained_action_to_review_continuity_claimed": False,
        "network_accessed": False,
        "hardware_accessed": False,
    }


def _review_module() -> Any:
    """Load the strong recorder lazily to avoid its intentional import cycle."""

    try:
        return importlib.import_module("tools.mf1750_p2_retained_clean_white_human_review")
    except ImportError as error:
        raise base.runner.RecheckError(
            "strong retained-clean-white recorder is unavailable"
        ) from error


def _review_binding(value: Mapping[str, Any], path: Path) -> dict[str, Any]:
    resolved = _resolve_repo_file(path, label="retained-white review")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise base.runner.RecheckError(
            "retained-white review cannot be read"
        ) from error
    integrity = value.get("integrity")
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or not isinstance(integrity.get("sha256"), str)
        or _SHA256_RE.fullmatch(str(integrity.get("sha256"))) is None
    ):
        raise base.runner.RecheckError("retained-white review integrity is absent")
    # The recorder has already replayed the canonical seal; retain both names
    # used by older evidence consumers so the admission is self-describing.
    canonical_sha256 = str(integrity["sha256"])
    return {
        "path": _repo_relative_dynamic(resolved),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": canonical_sha256,
        "canonical_sha256": canonical_sha256,
        "review_id": value.get("review_id"),
    }


def validate_retained_clean_white_review(
    path: Path = RETAINED_CLEAN_WHITE_REVIEW,
) -> dict[str, Any]:
    """Consume the independent strong recorder; never synthesize a review."""

    resolved = Path(path).resolve()
    if resolved != RETAINED_CLEAN_WHITE_REVIEW.resolve():
        raise base.runner.RecheckError("retained-clean-white review path differs")
    if not resolved.is_file() or resolved.is_symlink():
        raise base.runner.RecheckError("current retained-clean-white review is missing")
    reviewer = _review_module()
    try:
        value = reviewer.validate_review(resolved)
    except Exception as error:  # recorder deliberately exposes one safe error boundary
        raise base.runner.RecheckError(
            f"current retained-clean-white review failed deep validation: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("retained-clean-white review root differs")
    visual = value.get("visual_observation")
    boundaries = value.get("evidence_boundaries")
    offline = value.get("offline_execution")
    source = validate_source_white_authority()
    if (
        value.get("kind") != "mf1750-p2-retained-clean-white-human-review-v1"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or not isinstance(visual, Mapping)
        or visual.get("full_screen_clean_white_confirmed") is not True
        or visual.get("no_visible_colour_block_border_stain_or_fixed_line_confirmed")
        is not True
        or visual.get("admission_scope")
        != "CURRENT_RETAINED_FULL_SCREEN_VISUAL_PRECONDITION_ONLY"
        or not isinstance(boundaries, Mapping)
        or boundaries.get("retained_action_to_observation_continuity_proven") is not False
        or boundaries.get("no_intervening_visible_refresh_proven") is not False
        or boundaries.get("electrical_state_proven") is not False
        or boundaries.get("conversation_assertion_only") is not True
        or boundaries.get("cryptographic_operator_identity_proven") is not False
        or boundaries.get("camera_evidence_claimed") is not False
        or not isinstance(offline, Mapping)
        or dict(offline) != dict(getattr(reviewer, "OFFLINE_EXECUTION", {}))
    ):
        raise base.runner.RecheckError("retained-clean-white review scope differs")
    binding = value.get("machine_authority_binding")
    if not isinstance(binding, Mapping):
        raise base.runner.RecheckError("retained-clean-white source binding missing")
    if dict(binding) != dict({
        key: source[key]
        for key in (
            "kind",
            "state",
            "source_campaign_id",
            "source_contract_id",
            "source_descriptor_id",
            "source_action_id",
            "source_boot_nonce",
            "source_firmware_sha256",
            "source_elf_sha256",
            "source_p1_action_id",
            "files",
            "relay_off_commanded_and_queried",
            "electrical_state_proven",
        )
    }):
        raise base.runner.RecheckError("retained-clean-white source authority differs")
    expected_files = source["files"]
    bound_files = binding.get("files")
    if not isinstance(bound_files, Mapping):
        raise base.runner.RecheckError("retained-clean-white source file binding missing")
    for name in SOURCE_BINDINGS:
        item = bound_files.get(name)
        if not isinstance(item, Mapping) or dict(item) != dict(expected_files[name]):
            raise base.runner.RecheckError(
                f"retained-clean-white source binding differs for {name}"
            )
    return {
        "verified": True,
        **_review_binding(value, resolved),
        "observer": value["raw_operator_observation"]["operator_id"],
        "recorded_at": value["recorded_at"],
        "current_visible_state": "FULL_SCREEN_CLEAN_WHITE",
        "continuity_proven": False,
        "visible_refreshes": 0,
    }


def _verify_local_artifacts() -> dict[str, Any]:
    try:
        return pack.validate_artifacts()
    except (OSError, ValueError) as error:
        raise base.runner.RecheckError(str(error)) from error


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    _p1_validate_capabilities(value)
    for key in (
        "complete_profile_tuple",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
        "full_screen_global_refresh",
        "fresh_one_shot_endpoint_atlas",
        "position_balanced_atlas",
    ):
        if value.get(key) is not True:
            raise base.runner.RecheckError(f"P2 capability {key} differs")
    for key in (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "history_sequence",
        "identical_target_repeat",
        "main_campaign_resume_after_containment",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(f"P2 forbidden capability {key} differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _p1_validate_version(value)
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("profile_source")
        != "legacy_complete_535_commented_symmetric_controller_tuple"
    ):
        raise base.runner.RecheckError("P2 version layout identity differs")


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if ordinal != 1 or expected_busy not in (0, 1) or value.get("busy") != expected_busy:
        raise base.runner.RecheckError("P2 ready ordinal/BUSY admission differs")
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=expected_busy
    )
    for key in ("arm_request_count", "execute_request_count", "total_driver_call_count"):
        if value.get(key) != 0:
            raise base.runner.RecheckError(f"P2 fresh ready {key} differs")
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
        or value.get("reboot_resume_allowed") is not False
        or value.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError("P2 same-boot binding differs")
    return nonce


def _validate_fresh_report(value: Mapping[str, Any], boot_nonce: str) -> None:
    validator = _p1_validate_fresh_no_execute_report
    if not callable(validator):
        raise base.runner.RecheckError("fresh report validator missing")
    validator(value, boot_nonce)
    if value.get("kind") != (
        "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-report"
    ):
        raise base.runner.RecheckError("P2 fresh report identity differs")


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal != 1:
        raise base.runner.RecheckError("P2 COMPLETE ordinal differs")
    _p1_validate_complete_report(value, ordinal, boot_nonce)
    if (
        value.get("role") != base.runner.ACTIONS[0]["role"]
        or value.get("kind")
        != "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-report"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != REPORT["contract_id"]
    ):
        raise base.runner.RecheckError("P2 COMPLETE role differs")


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    del value, ordinal, boot_nonce
    raise base.runner.RecheckError("P2 fresh one-shot has no prior ordinal")


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    if ordinal != 1 or expected_busy not in (0, 1):
        raise base.runner.RecheckError("P2 ordinal/BUSY preflight differs")
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url, ordinal, expected_busy=expected_busy, requester=requester
    )
    _validate_fresh_report(report, boot_nonce)
    return boot_nonce, transcript, report


# Rebind every dynamic validation point.  The imported P1 facade stores
# function objects in four layers; replacing only its public symbol is unsafe.
for _module in (template, host, base, base.runner, v1):
    _module._validate_capabilities = _validate_capabilities  # type: ignore[attr-defined]
    _module._validate_version = _validate_version  # type: ignore[attr-defined]
    _module._validate_manifest = _validate_manifest  # type: ignore[attr-defined]
    _module._validate_ready_status = _validate_ready_status  # type: ignore[attr-defined]
    _module._validate_complete_report = _validate_complete_report  # type: ignore[attr-defined]
    _module._validate_prior_terminal_report = _validate_prior_terminal_report  # type: ignore[attr-defined]
    _module._preflight = _preflight  # type: ignore[attr-defined]
    # Some nested facades call this symbol directly for the first fresh
    # report.  Rebinding it closes the remaining active-profile escape hatch.
    _module._validate_fresh_no_execute_report = _validate_fresh_report  # type: ignore[attr-defined]
host._require_firmware_binding = lambda: _verify_local_artifacts()  # type: ignore[attr-defined]
base.runner._origin = template._private_origin  # noqa: SLF001
base.runner._http_request = template._direct_http_request  # noqa: SLF001
template.validate_source_white_authority = validate_source_white_authority


def _canonical(value: Any) -> bytes:
    """Use the exact JSON canonicalization shared by all P2 evidence seals."""

    return pack.canonical_json(value)


def _resolve_repo_file(value: Path | str, *, label: str) -> Path:
    """Resolve an evidence path while forbidding escapes and symlinks."""

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(REPO_ROOT.resolve())
    except (OSError, ValueError) as error:
        raise base.runner.RecheckError(
            f"{label} must remain inside the repository"
        ) from error
    try:
        stat_result = candidate.lstat()
    except OSError as error:
        raise base.runner.RecheckError(f"{label} is missing or unsafe") from error
    if not candidate.is_file() or candidate.is_symlink() or not stat_result:
        raise base.runner.RecheckError(f"{label} is missing or unsafe")
    return resolved


def _repo_relative_dynamic(path: Path) -> str:
    """Repository-relative spelling using this facade's current root."""

    try:
        return Path(path).resolve().relative_to(Path(REPO_ROOT).resolve()).as_posix()
    except ValueError as error:
        raise base.runner.RecheckError(
            f"P2 evidence path must remain inside the repository: {path}"
        ) from error


def _private_origin(value: str) -> str:
    """Return a normalized literal-private-IPv4 HTTP origin.

    The old P1 helper hard-coded ``192.168.1.11``.  P2 intentionally derives
    the host from the fresh binding record, while retaining strict origin
    syntax and forbidding hostnames, credentials, paths, queries, fragments,
    and public addresses.
    """

    if not isinstance(value, str):
        raise base.runner.RecheckError("base URL must be an exact private IPv4 origin")
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise base.runner.RecheckError("base URL port differs") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (port is not None and port != 80)
    ):
        raise base.runner.RecheckError(
            "base URL must be a plain HTTP private-IPv4 origin"
        )
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError as error:
        raise base.runner.RecheckError(
            "base URL must use a literal private IPv4"
        ) from error
    if not _is_usable_private_ipv4(address):
        raise base.runner.RecheckError(
            "base URL must use a literal private IPv4"
        )
    normalized_host = str(address)
    # Omit an explicit default port so all equivalent spellings bind to one
    # canonical origin.  The campaign contract is explicitly HTTP port 80.
    netloc = normalized_host
    return f"http://{netloc}"


def _normalise_mac(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().upper().replace(":", "-")
    return candidate if _MAC_RE.fullmatch(candidate) else None


def _valid_timestamp(value: Any) -> datetime | None:
    """Parse a timezone-qualified RFC3339/ISO-8601 timestamp."""

    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _valid_ipv4(value: Any) -> ipaddress.IPv4Address | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, ipaddress.IPv4Address) else None


def _is_usable_private_ipv4(value: Any) -> bool:
    """Accept only a real RFC1918 host address for the LAN binding.

    ``ipaddress`` marks several special-purpose ranges as ``private`` too;
    those are not valid device endpoints.  Keep the exclusion explicit so a
    loopback, link-local, multicast, reserved, or unspecified address can
    never become an origin or a binding candidate.
    """

    address = value if isinstance(value, ipaddress.IPv4Address) else _valid_ipv4(value)
    if address is None or not any(address in network for network in _RFC1918_NETWORKS):
        return False
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _read_json_no_duplicates(payload: bytes, *, label: str) -> dict[str, Any]:
    class _DuplicateKey(ValueError):
        pass

    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise _DuplicateKey(key)
            result[key] = item
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey) as error:
        raise base.runner.RecheckError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise base.runner.RecheckError(f"{label} root differs")
    return value


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    candidate = _resolve_repo_file(path, label=label)
    try:
        payload = candidate.read_bytes()
    except OSError as error:
        raise base.runner.RecheckError(f"{label} cannot be read") from error
    if len(payload) > 16 * 1024 * 1024:
        raise base.runner.RecheckError(f"{label} is too large")
    value = _read_json_no_duplicates(payload, label=label)
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    expected = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }
    if integrity != expected:
        raise base.runner.RecheckError(f"{label} canonical integrity differs")
    return value


def validate_exact_ipv4_mac_binding(path: Path, base_url: str) -> dict[str, Any]:
    """Validate one fresh, exact IPv4-to-device-MAC binding without I/O."""

    resolved = _resolve_repo_file(path, label="P2 exact IPv4/MAC binding")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise base.runner.RecheckError("P2 exact IPv4/MAC binding cannot be read") from error
    value = _read_json_no_duplicates(payload, label="P2 exact IPv4/MAC binding")
    expected_keys = {
        "active_probe",
        "active_probe_authorized",
        "binding_passed",
        "candidate_count",
        "candidate_ipv4",
        "device_api_requests",
        "device_application_identity_proven",
        "expected_mac",
        "fallback",
        "finished_at",
        "fresh_binding_passed",
        "http_requests",
        "integrity",
        "kind",
        "local_ipv4",
        "mutation_requests",
        "neighbour_entries",
        "network_layer_mac_binding_observed",
        "observed_state",
        "outcome",
        "output_contract",
        "output_file",
        "retry",
        "scan",
        "schema_version",
        "single_candidate_confirmed",
        "started_at",
        "visible_refresh_requests",
    }
    if set(value) != expected_keys:
        raise base.runner.RecheckError("P2 exact IPv4/MAC binding fields differ")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    expected_integrity = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }
    if integrity != expected_integrity:
        raise base.runner.RecheckError("P2 exact IPv4/MAC binding integrity differs")
    if not isinstance(integrity, Mapping) or not isinstance(
        integrity.get("sha256"), str
    ) or _SHA256_RE.fullmatch(integrity["sha256"]) is None:
        raise base.runner.RecheckError("P2 exact IPv4/MAC binding integrity differs")
    origin = _private_origin(base_url)
    origin_host = urllib_parse.urlsplit(origin).hostname
    candidate = value.get("candidate_ipv4")
    try:
        candidate_ip = ipaddress.ip_address(str(candidate))
    except ValueError as error:
        raise base.runner.RecheckError("P2 binding candidate IPv4 differs") from error
    if (
        not _is_usable_private_ipv4(candidate_ip)
        or str(candidate_ip) != origin_host
    ):
        raise base.runner.RecheckError(
            "P2 binding candidate does not match the private origin"
        )
    expected_mac = _normalise_mac(value.get("expected_mac"))
    if expected_mac != EXPECTED_DEVICE_MAC:
        raise base.runner.RecheckError("P2 binding expected MAC differs")
    neighbours = value.get("neighbour_entries")
    local_ipv4 = value.get("local_ipv4")
    probe = value.get("active_probe")
    probe_keys = {
        "attempts",
        "kind",
        "returncode",
        "stderr_bytes",
        "stderr_sha256",
        "stderr_utf8",
        "stdout_bytes",
        "stdout_sha256",
        "stdout_utf8",
    }
    neighbour_keys = {"IPAddress", "LinkLayerAddress", "State", "ifIndex"}
    local_keys = {"IPAddress", "InterfaceAlias", "InterfaceIndex", "PrefixLength"}
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "mf1750-exact-ipv4-mac-binding-attempt-v1"
        or value.get("active_probe_authorized") is not True
        or value.get("single_candidate_confirmed") is not True
        or value.get("candidate_count") != 1
        or value.get("binding_passed") is not True
        or value.get("fresh_binding_passed") is not True
        or value.get("network_layer_mac_binding_observed") is not True
        or value.get("device_application_identity_proven") is not False
        or value.get("outcome") != "active_exact_mac_binding_pass"
        or value.get("http_requests") != 0
        or value.get("device_api_requests") != 0
        or value.get("mutation_requests") != 0
        or value.get("visible_refresh_requests") != 0
        or value.get("retry") is not False
        or value.get("fallback") is not False
        or value.get("scan") is not False
        or value.get("output_contract") != "O_EXCL_TERMINAL"
        or value.get("observed_state") not in _FRESH_NEIGHBOUR_STATES
        or not isinstance(probe, Mapping)
        or set(probe) != probe_keys
        or probe.get("kind") != "one_icmp_echo_to_exact_literal_ipv4"
        or probe.get("attempts") != 1
        or probe.get("returncode") != 0
        or not isinstance(probe.get("stderr_utf8"), str)
        or not isinstance(probe.get("stdout_utf8"), str)
        or probe.get("stderr_bytes") != len(probe["stderr_utf8"].encode("utf-8"))
        or probe.get("stdout_bytes") != len(probe["stdout_utf8"].encode("utf-8"))
        or not isinstance(probe.get("stderr_sha256"), str)
        or _SHA256_RE.fullmatch(probe["stderr_sha256"]) is None
        or not isinstance(probe.get("stdout_sha256"), str)
        or _SHA256_RE.fullmatch(probe["stdout_sha256"]) is None
        or hashlib.sha256(probe["stderr_utf8"].encode("utf-8")).hexdigest()
        != probe["stderr_sha256"]
        or hashlib.sha256(probe["stdout_utf8"].encode("utf-8")).hexdigest()
        != probe["stdout_sha256"]
        or not isinstance(neighbours, list)
        or len(neighbours) != 1
        or not isinstance(neighbours[0], Mapping)
        or set(neighbours[0]) != neighbour_keys
        or str(neighbours[0].get("IPAddress")) != str(candidate_ip)
        or _normalise_mac(neighbours[0].get("LinkLayerAddress")) != EXPECTED_DEVICE_MAC
        or not isinstance(neighbours[0].get("State"), int)
        or isinstance(neighbours[0].get("State"), bool)
        or not 0 <= neighbours[0]["State"] <= 255
        or not isinstance(neighbours[0].get("ifIndex"), int)
        or isinstance(neighbours[0].get("ifIndex"), bool)
        or neighbours[0]["ifIndex"] < 1
        or not isinstance(local_ipv4, list)
        or not local_ipv4
        or any(
            not isinstance(item, Mapping)
            or set(item) != local_keys
            or not isinstance(item.get("IPAddress"), str)
            or _valid_ipv4(item["IPAddress"]) is None
            or not isinstance(item.get("InterfaceAlias"), str)
            or not item["InterfaceAlias"].strip()
            or not isinstance(item.get("InterfaceIndex"), int)
            or isinstance(item["InterfaceIndex"], bool)
            or item["InterfaceIndex"] < 1
            or not isinstance(item.get("PrefixLength"), int)
            or isinstance(item["PrefixLength"], bool)
            or not 0 <= item["PrefixLength"] <= 32
            for item in local_ipv4
        )
        or len({item["IPAddress"] for item in local_ipv4}) != len(local_ipv4)
    ):
        raise base.runner.RecheckError("P2 exact IPv4/MAC binding semantics differ")
    probe_text = str(probe.get("stdout_utf8", ""))
    if str(candidate_ip) not in probe_text:
        raise base.runner.RecheckError("P2 active probe is not bound to candidate IPv4")
    if not isinstance(value.get("output_file"), str) or not value["output_file"]:
        raise base.runner.RecheckError("P2 binding output path differs")
    try:
        output_file_candidate = Path(value["output_file"])
        if not output_file_candidate.is_absolute():
            output_file_candidate = REPO_ROOT / output_file_candidate
        output_file = output_file_candidate.resolve()
    except OSError as error:
        raise base.runner.RecheckError("P2 binding output path differs") from error
    if output_file != resolved:
        raise base.runner.RecheckError("P2 binding output path differs")
    started = _valid_timestamp(value.get("started_at"))
    finished = _valid_timestamp(value.get("finished_at"))
    if started is None or finished is None or finished < started:
        raise base.runner.RecheckError("P2 binding timestamps differ")
    return {
        "path": _repo_relative_dynamic(resolved),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": integrity["sha256"],
        "canonical_sha256": integrity["sha256"],
        "candidate_ipv4": str(candidate_ip),
        "expected_mac": EXPECTED_DEVICE_MAC,
        "outcome": "active_exact_mac_binding_pass",
        "fresh_binding_passed": True,
        "device_application_identity_proven": False,
        "device_api_requests": 0,
        "mutation_requests": 0,
        "visible_refresh_requests": 0,
    }


# The private template and every nested runner consult their module globals at
# call time.  Rebind the origin/transport after defining the P2 implementation
# so no inherited P1 fixed-address helper can be reached accidentally.
template._private_origin = _private_origin  # type: ignore[attr-defined]
base.runner._origin = _private_origin  # noqa: SLF001
template.validate_exact_ipv4_mac_binding = validate_exact_ipv4_mac_binding  # type: ignore[attr-defined]


def _validate_transcript_prefix(
    transcript: Any,
    *,
    boot_nonce: str | None = None,
    terminal: Mapping[str, Any] | None = None,
) -> None:
    if not isinstance(transcript, list) or len(transcript) < 4:
        raise base.runner.RecheckError("P2 transcript is missing")
    expected_prefix = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    if any(not isinstance(item, Mapping) for item in transcript):
        raise base.runner.RecheckError("P2 transcript entry differs")
    if [
        (item.get("method"), item.get("endpoint")) for item in transcript[:4]
    ] != expected_prefix:
        raise base.runner.RecheckError("P2 preflight GET order differs")
    # The sealed P2 firmware acknowledges ARM with 201 and EXECUTE with 202.
    # Only the read endpoints return 200. Check the exact method/status pair
    # instead of treating every transcript entry as a GET response.
    wire_contract = {
        "version": ("GET", 200),
        "manifest": ("GET", 200),
        "status": ("GET", 200),
        "report": ("GET", 200),
        "arm": ("POST", 201),
        "execute": ("POST", 202),
    }
    for item in transcript:
        if (
            item.get("endpoint") not in base.runner.ENDPOINTS
            or item.get("path")
            != base.runner.ENDPOINTS.get(item.get("endpoint"))
            or type(item.get("status")) is not int
            or (item.get("method"), item.get("status"))
            != wire_contract.get(item.get("endpoint"))
            or not isinstance(item.get("response"), Mapping)
            or not isinstance(item.get("headers"), Mapping)
            or any(
                not isinstance(key, str) or not isinstance(val, str)
                for key, val in item["headers"].items()
            )
            or item.get("observation_error") is not None
        ):
            raise base.runner.RecheckError("P2 transcript entry differs")
        if item.get("method") == "GET" and dict(item["headers"]) != {}:
            raise base.runner.RecheckError("P2 GET transcript headers differ")
    if boot_nonce is not None:
        for item in transcript:
            response = item["response"]
            observed = response.get("boot_nonce")
            if item.get("endpoint") not in ("version", "manifest") and (
                not isinstance(observed, str) or observed != boot_nonce
            ):
                raise base.runner.RecheckError("P2 transcript boot differs")
    if terminal is not None and transcript[-1].get("response") != terminal:
        raise base.runner.RecheckError("P2 terminal transcript tail differs")


def diagnose_j2_off(
    base_url: str,
    *,
    exact_ipv4_mac_binding: Path,
    retained_clean_white_review: Path,
    confirm_j2_off: bool,
    output: Path = DIAGNOSTIC_OUTPUT,
    requester: Any = None,
) -> dict[str, Any]:
    if confirm_j2_off is not True:
        raise base.runner.RecheckError("P2 diagnostic requires explicit J2-OFF")
    output = template._fixed_path(output, DIAGNOSTIC_OUTPUT, label="P2 diagnostic output")  # noqa: SLF001
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    origin = _private_origin(base_url)
    # All source/review/binding gates occur before selecting or invoking a requester.
    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    review = validate_retained_clean_white_review(retained_clean_white_review)
    address = validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    selected = requester or template._direct_http_request  # noqa: SLF001
    boot_nonce, transcript, report = _preflight(origin, 1, expected_busy=0, requester=selected)
    evidence = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-j2-off-diagnostic",
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "source_white_authority": source,
            "artifacts": artifacts,
            "retained_clean_white_review": review,
            "exact_ipv4_mac_binding": address,
            "base_url": origin,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "current_clean_white_review_accepted_as_physical_precondition": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "permanent_claims_created": 0,
            "visible_refreshes": 0,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(output, evidence)  # noqa: SLF001
    return evidence


def _validate_diagnostic(
    path: Path,
    base_url: str,
    exact_ipv4_mac_binding: Path,
    retained_clean_white_review: Path,
) -> dict[str, Any]:
    resolved = template._fixed_path(
        path, DIAGNOSTIC_OUTPUT, label="P2 diagnostic output"
    )  # noqa: SLF001
    value = _read_integrity_json(resolved, label="P2 J2-OFF diagnostic")
    origin = _private_origin(base_url)
    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    review = validate_retained_clean_white_review(retained_clean_white_review)
    address = validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    exact = {
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-j2-off-diagnostic",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "source_white_authority": source,
        "artifacts": artifacts,
        "retained_clean_white_review": review,
        "exact_ipv4_mac_binding": address,
        "base_url": origin,
        "j2_confirmed_off": True,
        "current_clean_white_review_accepted_as_physical_precondition": True,
        "next_ordinal": 1,
        "network": {"get": 4, "post": 0},
        "permanent_claims_created": 0,
        "visible_refreshes": 0,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    if any(value.get(key) != wanted for key, wanted in exact.items()):
        raise base.runner.RecheckError("P2 J2-OFF diagnostic semantics differ")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(boot_nonce, str) or _NONCE_RE.fullmatch(boot_nonce) is None:
        raise base.runner.RecheckError("P2 diagnostic boot nonce differs")
    report = value.get("report")
    if not isinstance(report, Mapping):
        raise base.runner.RecheckError("P2 diagnostic report missing")
    _validate_fresh_report(report, boot_nonce)
    transcript = value.get("transcript")
    _validate_transcript_prefix(transcript, boot_nonce=boot_nonce, terminal=report)
    if len(transcript) != 4:
        raise base.runner.RecheckError("P2 diagnostic must contain exactly four GETs")
    _validate_version(transcript[0]["response"])
    _validate_manifest(transcript[1]["response"])
    observed = _validate_ready_status(transcript[2]["response"], 1, expected_busy=0)
    _validate_fresh_report(transcript[3]["response"], observed)
    if observed != boot_nonce:
        raise base.runner.RecheckError("P2 diagnostic preflight boot differs")
    return {
        "verified": True,
        "path": _repo_relative_dynamic(resolved),
        "bytes": resolved.stat().st_size,
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
        "canonical_sha256": value["integrity"]["sha256"],
        "boot_nonce": boot_nonce,
        "base_url": origin,
        "exact_ipv4_mac_binding": address,
        "retained_clean_white_review": review,
        "artifacts": artifacts,
        "transcript": transcript,
        "report": deepcopy(dict(report)),
    }


def _same_boot_requester(expected_boot_nonce: str, requester: Any) -> Any:
    def checked(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = requester(*args, **kwargs)
        if not isinstance(value, Mapping):
            raise base.runner.RecheckError("P2 live response root differs")
        observed = value.get("boot_nonce")
        path = str(args[1]) if len(args) > 1 else ""
        # Version and manifest are immutable identity surfaces and do not carry
        # a boot nonce; every status/report/mutation response must carry the
        # exact diagnostic nonce.
        if path.rsplit("/", 1)[-1] not in ("version", "manifest") and (
            not isinstance(observed, str) or observed != expected_boot_nonce
        ):
            raise base.runner.RecheckError("P2 live boot differs from diagnostic")
        return status, value

    return checked


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    exact_ipv4_mac_binding: Path,
    retained_clean_white_review: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    confirm_j2_on: bool = False,
) -> dict[str, Any]:
    """Run exactly one P2 action after a strong current-white review gate."""

    if confirm_j2_on is not True:
        raise base.runner.RecheckError("P2 run requires explicit J2-ON")
    if ordinal != 1:
        raise base.runner.RecheckError("P2 ordinal must be exactly 1")
    if poll_seconds < 65.0:
        raise base.runner.RecheckError("P2 run requires poll_seconds >= 65")
    if not isinstance(poll_count, int) or isinstance(poll_count, bool) or poll_count < 1:
        raise base.runner.RecheckError("P2 run requires poll_count >= 1")
    origin = _private_origin(base_url)
    claims = template._fixed_path(claims, base.runner.DEFAULT_CLAIMS, label="P2 claims root")  # noqa: SLF001
    output = template._fixed_path(output, ACTION_OUTPUTS[1], label="P2 action output")  # noqa: SLF001
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    expected = base.runner.ACTIONS[0]
    claim_path = (claims / f"{expected['action_id']}.json").resolve()
    if claim_path.exists():
        raise base.runner.RecheckError("P2 permanent action claim already exists")
    # Strong gates and all fixed evidence are evaluated before any GET/claim/POST.
    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    review = validate_retained_clean_white_review(retained_clean_white_review)
    address = validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    diagnostic = _validate_diagnostic(
        DIAGNOSTIC_OUTPUT, origin, exact_ipv4_mac_binding, retained_clean_white_review
    )
    admission = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-live-admission",
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "ordinal": 1,
            "action_id": expected["action_id"],
            "boot_nonce": diagnostic["boot_nonce"],
            "base_url": origin,
            "source_white_authority": source,
            "artifacts": artifacts,
            "retained_clean_white_review": review,
            "exact_ipv4_mac_binding": address,
            "j2_off_diagnostic": {
                key: diagnostic[key]
                for key in (
                    "path",
                    "bytes",
                    "file_sha256",
                    "canonical_integrity_sha256",
                    "canonical_sha256",
                    "boot_nonce",
                )
            },
            "j2_confirmed_on_before_any_live_get_claim_or_post": True,
            "current_clean_white_review_accepted_as_physical_precondition": True,
            "retained_action_to_review_continuity_claimed": False,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "output_write_contract": "O_EXCL",
        }
    )
    base.runner._write_new(RUN_ADMISSION_OUTPUT, admission)  # noqa: SLF001
    selected = requester or template._direct_http_request  # noqa: SLF001
    selected = _same_boot_requester(str(diagnostic["boot_nonce"]), selected)
    return host.run_once(
        origin,
        1,
        claims=claims,
        output=output,
        requester=selected,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def _validate_admission(
    path: Path,
    *,
    base_url: str | None = None,
    exact_ipv4_mac_binding: Path | None = None,
    retained_clean_white_review: Path | None = None,
    boot_nonce: str | None = None,
    action: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay the immutable live-admission seal and all of its dependencies.

    The admission is the authority for the *fresh* binding path and origin.
    Callers may supply expected values as cross-checks, but terminal replay
    never invents a historical address or binding path.
    """

    resolved = template._fixed_path(
        path, RUN_ADMISSION_OUTPUT, label="P2 live admission"
    )  # noqa: SLF001
    value = _read_integrity_json(resolved, label="P2 live admission")
    required_keys = {
        "schema_version",
        "kind",
        "created_at",
        "campaign_id",
        "contract_id",
        "ordinal",
        "action_id",
        "boot_nonce",
        "base_url",
        "source_white_authority",
        "artifacts",
        "retained_clean_white_review",
        "exact_ipv4_mac_binding",
        "j2_off_diagnostic",
        "j2_confirmed_on_before_any_live_get_claim_or_post",
        "current_clean_white_review_accepted_as_physical_precondition",
        "retained_action_to_review_continuity_claimed",
        "no_retry",
        "no_recovery",
        "no_autochain",
        "output_write_contract",
        "integrity",
    }
    if set(value) != required_keys:
        raise base.runner.RecheckError("P2 live admission fields differ")
    stored_origin = _private_origin(str(value.get("base_url")))
    if stored_origin != value.get("base_url"):
        raise base.runner.RecheckError("P2 live admission origin is not canonical")
    if base_url is not None and _private_origin(base_url) != stored_origin:
        raise base.runner.RecheckError("P2 live admission origin differs")
    expected_action = dict(action or base.runner.ACTIONS[0])
    expected_boot = value.get("boot_nonce")
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-p2-commented-endpoint-atlas-4x8-v1-live-admission"
        or not isinstance(value.get("created_at"), str)
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != REPORT["contract_id"]
        or value.get("ordinal") != 1
        or value.get("action_id") != expected_action["action_id"]
        or not isinstance(expected_boot, str)
        or _NONCE_RE.fullmatch(expected_boot) is None
        or (boot_nonce is not None and boot_nonce != expected_boot)
        or value.get("j2_confirmed_on_before_any_live_get_claim_or_post") is not True
        or value.get("current_clean_white_review_accepted_as_physical_precondition")
        is not True
        or value.get("retained_action_to_review_continuity_claimed") is not False
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or value.get("output_write_contract") != "O_EXCL"
    ):
        raise base.runner.RecheckError("P2 live admission semantics differ")

    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    if value.get("source_white_authority") != source:
        raise base.runner.RecheckError("P2 admission source authority differs")
    if value.get("artifacts") != artifacts:
        raise base.runner.RecheckError("P2 admission artifact seal differs")

    stored_binding = value.get("exact_ipv4_mac_binding")
    if not isinstance(stored_binding, Mapping) or not isinstance(
        stored_binding.get("path"), str
    ):
        raise base.runner.RecheckError("P2 admission fresh binding is missing")
    binding_path = _resolve_repo_file(
        stored_binding["path"], label="P2 admission fresh binding"
    )
    if exact_ipv4_mac_binding is not None:
        supplied_binding = _resolve_repo_file(
            exact_ipv4_mac_binding, label="P2 supplied fresh binding"
        )
        if supplied_binding != binding_path:
            raise base.runner.RecheckError("P2 admission fresh binding path differs")
    binding = validate_exact_ipv4_mac_binding(binding_path, stored_origin)
    if dict(stored_binding) != binding:
        raise base.runner.RecheckError("P2 admission fresh binding seal differs")

    stored_review = value.get("retained_clean_white_review")
    if not isinstance(stored_review, Mapping) or not isinstance(
        stored_review.get("path"), str
    ):
        raise base.runner.RecheckError("P2 admission retained review is missing")
    review_path = _resolve_repo_file(
        stored_review["path"], label="P2 admission retained review"
    )
    if review_path != RETAINED_CLEAN_WHITE_REVIEW.resolve():
        raise base.runner.RecheckError("P2 admission retained review path differs")
    if retained_clean_white_review is not None:
        supplied_review = _resolve_repo_file(
            retained_clean_white_review, label="P2 supplied retained review"
        )
        if supplied_review != review_path:
            raise base.runner.RecheckError("P2 admission retained review differs")
    review = validate_retained_clean_white_review(review_path)
    if dict(stored_review) != review:
        raise base.runner.RecheckError("P2 admission retained review seal differs")

    stored_diagnostic = value.get("j2_off_diagnostic")
    if not isinstance(stored_diagnostic, Mapping) or not isinstance(
        stored_diagnostic.get("path"), str
    ):
        raise base.runner.RecheckError("P2 admission diagnostic is missing")
    diagnostic_path = _resolve_repo_file(
        stored_diagnostic["path"], label="P2 admission J2-OFF diagnostic"
    )
    if diagnostic_path != DIAGNOSTIC_OUTPUT.resolve():
        raise base.runner.RecheckError("P2 admission diagnostic path differs")
    diagnostic = _validate_diagnostic(
        diagnostic_path, stored_origin, binding_path, review_path
    )
    diagnostic_binding = {
        key: diagnostic[key]
        for key in (
            "path",
            "bytes",
            "file_sha256",
            "canonical_integrity_sha256",
            "canonical_sha256",
            "boot_nonce",
        )
    }
    if dict(stored_diagnostic) != diagnostic_binding:
        raise base.runner.RecheckError("P2 admission diagnostic seal differs")
    if diagnostic["boot_nonce"] != expected_boot:
        raise base.runner.RecheckError("P2 admission/diagnostic boot differs")
    return {
        "verified": True,
        "path": _repo_relative_dynamic(resolved),
        "bytes": resolved.stat().st_size,
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
        "canonical_sha256": value["integrity"]["sha256"],
        "boot_nonce": expected_boot,
        "base_url": stored_origin,
        "binding_path": _repo_relative_dynamic(binding_path),
        "review_path": _repo_relative_dynamic(review_path),
        "diagnostic_path": _repo_relative_dynamic(diagnostic_path),
        "value": value,
        "binding": binding,
        "review": review,
        "diagnostic": diagnostic,
        "artifacts": artifacts,
        "source_white_authority": source,
    }


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    source = validate_source_white_authority()
    authority_sources = pack.authority_source_hashes()
    authority_seal = pack.authority_source_seal(authority_sources)
    artifacts = _verify_local_artifacts() if verify_artifacts else {
        name: {
            "path": template._repo_relative(Path(binding["path"])),  # noqa: SLF001
            "bytes": binding["bytes"],
            "sha256": binding["sha256"],
        }
        for name, binding in pack.ARTIFACTS.items()
    }
    flat = [code for row in pack.CODE_ROWS for code in row]
    if (
        report["contract_id"] != base.runner.CONTRACT_ID
        or len(actions) != 1
        or tuple(item["role"] for item in actions) != (pack.ROLE,)
        or tuple(item["action_id"] for item in actions) != base.runner.ACTION_IDS
        or contract["action_count"] != 1
        or contract["geometry"]["row_codes"] != [list(row) for row in pack.CODE_ROWS]
        or sorted(flat) != [code for code in range(8) for _ in range(4)]
        or contract["geometry"]["samples_per_code_per_controller_per_frame"] != 4
        or contract["geometry"]["same_layout_both_controllers"] is not True
        or contract["geometry"]["controller_dtm_byte_identical"] is not True
        or actions[0]["cs1_dtm"] != actions[0]["cs2_dtm"]
        or contract["fresh_one_shot"] is not True
        or contract["one_visible_refresh_per_action"] is not True
        or contract["partial_refresh"] is not False
        or contract["local_hold_claimed"] is not False
        or contract["automatic_chaining"] is not False
        or contract["retry"] is not False
        or contract["recovery"] is not False
        or contract["qualified_colours"] != 0
        or contract["qualified_lightness_levels"] != 0
    ):
        raise base.runner.RecheckError("P2 offline one-shot/4x8 invariant differs")
    profile = contract["profile"]
    if (
        profile["name"] != "commented"
        or profile["complete_profile_tuple"] is not True
        or profile["cs1"] != profile["cs2"]
        or profile["controller_payloads_byte_identical"] is not True
        or profile["global_tuple_id"] != actions[0]["global_tuple_id"]
    ):
        raise base.runner.RecheckError("P2 commented complete-profile tuple differs")
    review = None
    review_state = "PENDING_CURRENT_VISUAL_REVIEW"
    if RETAINED_CLEAN_WHITE_REVIEW.exists():
        review = validate_retained_clean_white_review()
        review_state = "VERIFIED"
    return {
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-runner-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "device_requests_made": 0,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": report["contract_id"],
        "action_id": actions[0]["action_id"],
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "samples_per_code_per_controller": 4,
        "controller_dtm_byte_identical": True,
        "complete_commented_profile_both_controllers": True,
        "visible_refreshes_per_action": 1,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "qualified_colours": 0,
        "qualified_lightness_levels": 0,
        "source_white_authority": source,
        "authority_sources": authority_sources,
        "offline_authority_seal": authority_seal,
        "retained_clean_white_review": review,
        "retained_clean_white_review_state": review_state,
        "artifacts": artifacts,
        "artifacts_verified": verify_artifacts,
        "run_live_gates": [
            "confirm_j2_on",
            "latest_p1_white_successor_machine_authority",
            "current_retained_clean_white_review",
            "exact_ipv4_mac_binding",
            "same_boot_j2_off_diagnostic",
        ],
    }


def describe() -> dict[str, Any]:
    value = dry_validate()
    value.update(
        contract=deepcopy(REPORT["contract"]),
        actions_table=deepcopy(base.runner.ACTIONS),
        endpoints=deepcopy(base.runner.ENDPOINTS),
        fixed_outputs={
            "root": template._repo_relative(base.runner.DEFAULT_OUTPUT),  # noqa: SLF001
            "diagnostic": template._repo_relative(DIAGNOSTIC_OUTPUT),  # noqa: SLF001
            "live_admission": template._repo_relative(RUN_ADMISSION_OUTPUT),  # noqa: SLF001
            "action_1": template._repo_relative(ACTION_OUTPUTS[1]),  # noqa: SLF001
            "retained_clean_white_review": template._repo_relative(RETAINED_CLEAN_WHITE_REVIEW),  # noqa: SLF001
            "claims_root": template._repo_relative(base.runner.DEFAULT_CLAIMS),  # noqa: SLF001
        },
        independent_white_successor_required=True,
        current_retained_clean_white_review_required=True,
        fresh_exact_ipv4_binding_required=True,
        fixed_device_binding={
            "base_url_source": "fresh_exact_ipv4_mac_binding",
            "expected_mac": EXPECTED_DEVICE_MAC,
            "private_ipv4_only": True,
            "http_port": 80,
            "active_probe_required": True,
            "single_candidate_required": True,
        },
    )
    return value


def _validate_mutation_response(
    value: Mapping[str, Any],
    *,
    action: Mapping[str, Any],
    boot_nonce: str,
    endpoint: str,
    arm_nonce: str | None = None,
) -> None:
    """Validate identity and state fields returned by ARM/EXECUTE."""

    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"P2 {endpoint} response root differs")
    for key, wanted in {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "contract_id": REPORT["contract_id"],
        "classification": pack.CLASSIFICATION,
        "ordinal": 1,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "boot_nonce": boot_nonce,
    }.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"P2 {endpoint} response {key} differs")
    if endpoint == "arm":
        if (
            value.get("accepted") is not True
            or value.get("armed") is not True
            or value.get("phase") != 1
            or value.get("phase_name") != "ARMED"
            or value.get("not_hardware_authorization") is not True
        ):
            raise base.runner.RecheckError("P2 ARM response semantics differ")
        nonce = value.get("arm_nonce")
        if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
            raise base.runner.RecheckError("P2 ARM nonce differs")
    else:
        if (
            value.get("accepted") is not True
            or value.get("execute_consumed") is not True
            or value.get("phase") != 2
            or value.get("phase_name") != "CONSUMED"
            or value.get("no_retry") is not True
            or value.get("no_recovery") is not True
        ):
            raise base.runner.RecheckError("P2 EXECUTE response semantics differ")
        # Current firmware does not echo arm_nonce in EXECUTE.  If a future
        # build does, it must still equal the nonce used by this request.
        echoed = value.get("arm_nonce")
        if echoed is not None and echoed != arm_nonce:
            raise base.runner.RecheckError("P2 EXECUTE arm nonce differs")


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    """Deeply validate result, admission, diagnostic, binding, wire, claim."""

    # Read the result only after the fixed admission has supplied the current
    # origin/binding.  This is intentionally independent of any historical IP.
    expected = base.runner.ACTIONS[0]
    admission = _validate_admission(
        RUN_ADMISSION_OUTPUT,
        boot_nonce=None,
        action=expected,
    )
    source = admission["source_white_authority"]
    artifacts = admission["artifacts"]
    review = admission["review"]
    diagnostic = admission["diagnostic"]
    resolved = template._fixed_path(
        path, ACTION_OUTPUTS[1], label="P2 terminal output"
    )  # noqa: SLF001
    value = _read_integrity_json(resolved, label="P2 terminal evidence")
    required_result_keys = {
        "schema_version",
        "kind",
        "created_at",
        "firmware_sha256",
        "boot_nonce",
        "action",
        "claim_file",
        "terminal_report",
        "transcript",
        "network",
        "outcome",
        "visible_refreshes",
        "no_retry",
        "no_recovery",
        "no_autochain",
        "integrity",
    }
    optional_result_keys = {
        "base_url",
        "source_white_authority",
        "artifacts",
        "retained_clean_white_review",
        "exact_ipv4_mac_binding",
        "live_admission",
        "j2_off_diagnostic",
    }
    if not required_result_keys.issubset(value) or not set(value).issubset(
        required_result_keys | optional_result_keys
    ):
        raise base.runner.RecheckError("P2 terminal result fields differ")
    boot_nonce = value.get("boot_nonce")
    terminal = value.get("terminal_report")
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-result"
        or not isinstance(value.get("created_at"), str)
        or value.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or boot_nonce != admission["boot_nonce"]
        or value.get("action") != expected
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or not isinstance(terminal, Mapping)
        or not isinstance(boot_nonce, str)
        or _NONCE_RE.fullmatch(boot_nonce) is None
    ):
        raise base.runner.RecheckError("P2 terminal envelope differs")
    if value.get("base_url") is not None and value.get("base_url") != admission["base_url"]:
        raise base.runner.RecheckError("P2 terminal origin differs from admission")
    for key, expected_value in (
        ("source_white_authority", source),
        ("artifacts", artifacts),
        ("retained_clean_white_review", review),
        ("exact_ipv4_mac_binding", admission["binding"]),
    ):
        if key in value and value[key] != expected_value:
            raise base.runner.RecheckError(f"P2 terminal {key} differs from admission")
    _validate_complete_report(terminal, 1, boot_nonce)

    claim_value = value.get("claim_file")
    if not isinstance(claim_value, str):
        raise base.runner.RecheckError("P2 permanent claim path differs")
    claim_path = Path(claim_value)
    if not claim_path.is_absolute():
        claim_path = REPO_ROOT / claim_path
    claim_path = claim_path.resolve()
    expected_claim = (base.runner.DEFAULT_CLAIMS / f"{expected['action_id']}.json").resolve()
    if claim_path != expected_claim or claim_path.is_symlink() or not claim_path.is_file():
        raise base.runner.RecheckError("P2 permanent claim path differs")
    try:
        claim, claim_file_sha256 = v1._load_permanent_claim(  # noqa: SLF001
            claim_path, expected
        )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError("P2 permanent claim deep validation failed") from error
    if claim.get("boot_nonce") != boot_nonce or claim.get("action") != expected:
        raise base.runner.RecheckError("P2 claim identity/boot differs")

    transcript = value.get("transcript")
    _validate_transcript_prefix(transcript, boot_nonce=boot_nonce, terminal=terminal)
    if len(transcript) < 7:
        raise base.runner.RecheckError("P2 terminal transcript missing ARM/EXECUTE")
    expected_prefix = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    if [
        (item.get("method"), item.get("endpoint")) for item in transcript[:6]
    ] != expected_prefix:
        raise base.runner.RecheckError("P2 terminal ARM/EXECUTE order differs")
    if any(
        (item.get("method"), item.get("endpoint")) != ("GET", "report")
        for item in transcript[6:]
    ):
        raise base.runner.RecheckError("P2 terminal post-execute wire differs")
    if value.get("network") != {
        "get": 4 + len(transcript[6:]),
        "arm_post": 1,
        "execute_post": 1,
    }:
        raise base.runner.RecheckError("P2 terminal network counts differ")

    _validate_version(transcript[0]["response"])
    _validate_manifest(transcript[1]["response"])
    observed = _validate_ready_status(
        transcript[2]["response"], 1, expected_busy=1
    )
    _validate_fresh_report(transcript[3]["response"], observed)
    if observed != boot_nonce:
        raise base.runner.RecheckError("P2 terminal preflight boot differs")
    arm = transcript[4]
    execute = transcript[5]
    arm_headers = base.runner._headers(
        expected, boot_nonce, base.runner.ARM_INTENT
    )  # noqa: SLF001
    arm_response = arm["response"]
    _validate_mutation_response(
        arm_response, action=expected, boot_nonce=boot_nonce, endpoint="arm"
    )
    arm_nonce = arm_response["arm_nonce"]
    execute_headers = base.runner._headers(
        expected, boot_nonce, base.runner.EXECUTE_INTENT
    )  # noqa: SLF001
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    execute_response = execute["response"]
    _validate_mutation_response(
        execute_response,
        action=expected,
        boot_nonce=boot_nonce,
        endpoint="execute",
        arm_nonce=arm_nonce,
    )
    if (
        arm.get("headers") != dict(sorted(arm_headers.items()))
        or execute.get("headers") != dict(sorted(execute_headers.items()))
    ):
        raise base.runner.RecheckError("P2 terminal ARM/EXECUTE headers differ")

    # Every post-execute GET must be a same-boot fresh report or strict
    # COMPLETE report; the final one is the report embedded in the result.
    post_reports = transcript[6:]
    for index, item in enumerate(post_reports):
        response = item["response"]
        state = response.get("terminal_state")
        if state == "COMPLETE":
            _validate_complete_report(response, 1, boot_nonce)
        elif state == "NOT_EXECUTED":
            _validate_fresh_report(response, boot_nonce)
        else:
            raise base.runner.RecheckError(
                f"P2 post-execute report {index} state differs"
            )
    if post_reports[-1]["response"] != terminal:
        raise base.runner.RecheckError("P2 terminal report is not final GET report")
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "ordinal": 1,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "visible_refreshes": 1,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "boot_nonce": boot_nonce,
        "claim_path": _repo_relative_dynamic(claim_path),
        "claim_file_sha256": claim_file_sha256,
        "claim_canonical_integrity_sha256": claim["integrity"]["sha256"],
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
        "source_white_authority": source,
        "retained_clean_white_review": review,
        "live_admission": admission,
        "j2_off_diagnostic": diagnostic,
        "artifacts": artifacts,
    }


# The private P1 template remains available for its low-level mechanics, but
# its public entry points must not expose the retired source-v3 or
# no-intervening-refresh boolean bypasses.  Rebind those names to this facade
# after all P2 functions have been defined.
template.diagnose_j2_off = diagnose_j2_off
template.run_once = run_once
template.validate_terminal_evidence = validate_terminal_evidence
template.validate_retained_clean_white_review = validate_retained_clean_white_review
base.runner.diagnose_j2_off = diagnose_j2_off
base.runner.run_once = run_once
base.runner.validate_terminal_evidence = validate_terminal_evidence


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    term = sub.add_parser("validate-terminal-evidence", allow_abbrev=False)
    term.add_argument("--path", type=Path, default=ACTION_OUTPUTS[1])
    diagnostic = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--exact-ipv4-mac-binding", type=Path, required=True)
    diagnostic.add_argument("--retained-clean-white-review", type=Path, required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=(1,), required=True)
    run.add_argument("--exact-ipv4-mac-binding", type=Path, required=True)
    run.add_argument("--retained-clean-white-review", type=Path, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate(verify_artifacts=True)
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                retained_clean_white_review=args.retained_clean_white_review,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "run":
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=base.runner.DEFAULT_CLAIMS,
                output=ACTION_OUTPUTS[1],
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                retained_clean_white_review=args.retained_clean_white_review,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                confirm_j2_on=args.confirm_j2_on,
            )
        else:
            value = validate_terminal_evidence(args.path)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"P2-C runner error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
