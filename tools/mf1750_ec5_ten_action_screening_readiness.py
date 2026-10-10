#!/usr/bin/env python3
"""Compile/validate the offline five-pair MF1750 color-screening schedule.

The schedule binds four deep-validated C/T releases and the factory-OTP
dither release into ten visible actions: five color screens and five explicit
white recoveries.  It does not create a live authorization, claim, network
client, upload command, or hardware action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_dither_color_atlas_campaign as dither
from tools import mf1750_ec5_h3_c23_matched_control_release as c23_release
from tools import mf1750_ec5_h3_matched_control_release as c20_release
from tools import mf1750_ec5_runtime_lut_release as treatment_release


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-five-pair-ten-action-color-screening-readiness"
MAX_JSON_BYTES: Final = 16_000_000


class TenActionReadinessError(ValueError):
    """The ten-action offline schedule failed a release or integrity gate."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TenActionReadinessError("value is not canonical JSON") from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise TenActionReadinessError(f"{label} must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > MAX_JSON_BYTES:
            raise TenActionReadinessError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise TenActionReadinessError(f"could not read {label}: {error}") from error
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
        raise TenActionReadinessError(f"{label} changed while read")
    return candidate.resolve(strict=True), payload


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise TenActionReadinessError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise TenActionReadinessError(f"{label} root must be an object")
    return value


def _record(path: Path, payload: bytes, summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "deep_validation": deepcopy(dict(summary)),
    }


def _action_and_binding(
    root: Mapping[str, Any], ordinal: int
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    actions = [
        item
        for item in root["profile_contract"]["actions"]
        if item.get("ordinal") == ordinal
    ]
    bindings = [
        item
        for item in root["action_artifact_bindings"]
        if item.get("ordinal") == ordinal
    ]
    if len(actions) != 1 or len(bindings) != 1:
        raise TenActionReadinessError(
            f"release has no unique action/binding ordinal {ordinal}"
        )
    return actions[0], bindings[0]


def _release_action(
    *,
    visible_ordinal: int,
    pair_id: str,
    pair_position: str,
    branch: str,
    profile_id: str,
    release_key: str,
    root: Mapping[str, Any],
    release_action_ordinal: int,
    requires_completed_visible_ordinals: Sequence[int],
) -> dict[str, Any]:
    action, binding = _action_and_binding(root, release_action_ordinal)
    is_white = pair_position == "WHITE_RECOVERY"
    return {
        "visible_ordinal": visible_ordinal,
        "pair_id": pair_id,
        "pair_position": pair_position,
        "branch": branch,
        "profile_id": profile_id,
        "release_key": release_key,
        "release_id": root["release_id"],
        "release_action_ordinal": release_action_ordinal,
        "role": action["role"],
        "hardware_action_id": action["hardware_action_id"],
        "transaction_descriptor_sha256": action["transaction_descriptor_sha256"],
        "firmware_binary_sha256": binding["firmware_binary_sha256"],
        "firmware_elf_sha256": binding["firmware_elf_sha256"],
        "visible_class": "WHITE_RECOVERY" if is_white else "COLOR_SCREEN",
        "candidate_new_color_evaluation_allowed": not is_white,
        "requires_completed_visible_ordinals": list(
            requires_completed_visible_ordinals
        ),
        "separate_app_only_flash_with_j2_off_required": True,
        "fresh_j2_off_diagnostic_required": True,
        "independent_exact_live_authorization_required": True,
        "permanent_claim_before_mutation_required": True,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _dither_actions(
    release_path: Path,
    release_root: Mapping[str, Any],
    release_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    compiled = release_root.get("compiled_campaign")
    if not isinstance(compiled, Mapping):
        raise TenActionReadinessError("dither compiled campaign binding is absent")
    campaign_path, campaign_payload = _read_regular(
        Path(str(compiled.get("file"))), label="dither compiled campaign"
    )
    campaign = _decode(campaign_payload, label="dither compiled campaign")
    actions = campaign.get("actions")
    firmware = release_root.get("firmware")
    if (
        not isinstance(actions, list)
        or len(actions) != 2
        or not isinstance(firmware, Mapping)
    ):
        raise TenActionReadinessError("dither action/firmware set differs")
    if [item.get("ordinal") for item in actions] != [1, 2]:
        raise TenActionReadinessError("dither action order differs")
    binary = firmware["binary"]
    elf = firmware["elf"]
    result: list[dict[str, Any]] = []
    for visible_ordinal, action, position, dependencies in (
        (9, actions[0], "COLOR", list(range(1, 9))),
        (10, actions[1], "WHITE_RECOVERY", [9]),
    ):
        is_white = position == "WHITE_RECOVERY"
        result.append(
            {
                "visible_ordinal": visible_ordinal,
                "pair_id": "P5_FACTORY_OTP_DITHER",
                "pair_position": position,
                "branch": "FACTORY_OTP_SPATIAL_DITHER",
                "profile_id": "FACTORY_OTP",
                "release_key": "factory_otp_dither",
                "release_id": release_summary["canonical_sha256"],
                "release_action_ordinal": action["ordinal"],
                "role": action["role"],
                "hardware_action_id": action["action_id"],
                "transaction_descriptor_sha256": action["descriptor_id"],
                "firmware_binary_sha256": binary["sha256"],
                "firmware_elf_sha256": elf["sha256"],
                "compiled_campaign_file": str(campaign_path),
                "compiled_campaign_file_sha256": sha256(campaign_payload),
                "visible_class": "WHITE_RECOVERY" if is_white else "COLOR_SCREEN",
                "candidate_new_color_evaluation_allowed": not is_white,
                "electrophoretic_primary_color_claim_allowed": False,
                "requires_completed_visible_ordinals": dependencies,
                "separate_app_only_flash_with_j2_off_required": True,
                "fresh_j2_off_diagnostic_required": True,
                "independent_exact_live_authorization_required": True,
                "permanent_claim_before_mutation_required": True,
                "automatic_advance": False,
                "automatic_retry": False,
                "automatic_recovery": False,
            }
        )
    return result


def build_readiness(
    *,
    c20_control_file: Path,
    c20_treatment_file: Path,
    c23_control_file: Path,
    c23_treatment_file: Path,
    dither_release_file: Path,
) -> dict[str, Any]:
    """Deep-validate all five pairs and compile the non-live schedule."""

    try:
        c20_control_path, c20_control_payload = _read_regular(
            c20_control_file, label="C20 control release"
        )
        c20_control_root = c20_release.load_release(c20_control_path)
        c20_control_summary = c20_release.validate_release(c20_control_root)
        c20_treatment_path, c20_treatment_payload = _read_regular(
            c20_treatment_file, label="T20 treatment release"
        )
        c20_treatment_root = treatment_release.load_release(c20_treatment_path)
        c20_treatment_summary = treatment_release.validate_release(c20_treatment_root)
        c23_control_path, c23_control_payload = _read_regular(
            c23_control_file, label="C23 control release"
        )
        c23_control_root = c23_release.load_release(c23_control_path)
        c23_control_summary = c23_release.validate_release(c23_control_root)
        c23_treatment_path, c23_treatment_payload = _read_regular(
            c23_treatment_file, label="T23 treatment release"
        )
        c23_treatment_root = treatment_release.load_release(c23_treatment_path)
        c23_treatment_summary = treatment_release.validate_release(c23_treatment_root)
        dither_path, dither_payload = _read_regular(
            dither_release_file, label="factory-OTP dither release"
        )
        dither_summary = dither.validate_materialized_release(dither_path)
        dither_root = _decode(dither_payload, label="factory-OTP dither release")
    except (
        c20_release.MatchedControlReleaseError,
        c23_release.MatchedControlReleaseError,
        treatment_release.RuntimeLutReleaseError,
        dither.DitherColorAtlasCampaignError,
    ) as error:
        raise TenActionReadinessError(
            f"one screening release failed deep validation: {error}"
        ) from error
    if (
        c20_control_root["profile_id"] != "WF20_25"
        or c20_treatment_root["profile_id"] != "WF20_25"
        or c23_control_root["profile_id"] != "WF23_25"
        or c23_treatment_root["profile_id"] != "WF23_25"
        or c20_control_root["pinned_treatment_release"]["release_id"]
        != c20_treatment_root["release_id"]
        or c23_control_root["pinned_treatment_release"]["release_id"]
        != c23_treatment_root["release_id"]
    ):
        raise TenActionReadinessError("matched C/T release pairing differs")

    releases = {
        "c20_control": _record(
            c20_control_path, c20_control_payload, c20_control_summary
        ),
        "t20_treatment": _record(
            c20_treatment_path, c20_treatment_payload, c20_treatment_summary
        ),
        "c23_control": _record(
            c23_control_path, c23_control_payload, c23_control_summary
        ),
        "t23_treatment": _record(
            c23_treatment_path, c23_treatment_payload, c23_treatment_summary
        ),
        "factory_otp_dither": _record(
            dither_path, dither_payload, {"valid": True, **dither_summary}
        ),
    }
    actions = [
        _release_action(
            visible_ordinal=1,
            pair_id="P1_WF20_CONTROL",
            pair_position="COLOR",
            branch="C20_NO_R20_R21",
            profile_id="WF20_25",
            release_key="c20_control",
            root=c20_control_root,
            release_action_ordinal=1,
            requires_completed_visible_ordinals=(),
        ),
        _release_action(
            visible_ordinal=2,
            pair_id="P1_WF20_CONTROL",
            pair_position="WHITE_RECOVERY",
            branch="C20_NO_R20_R21",
            profile_id="WF20_25",
            release_key="c20_control",
            root=c20_control_root,
            release_action_ordinal=2,
            requires_completed_visible_ordinals=(1,),
        ),
        _release_action(
            visible_ordinal=3,
            pair_id="P2_WF20_TREATMENT",
            pair_position="COLOR",
            branch="T20_R20_R21",
            profile_id="WF20_25",
            release_key="t20_treatment",
            root=c20_treatment_root,
            release_action_ordinal=1,
            requires_completed_visible_ordinals=(1, 2),
        ),
        _release_action(
            visible_ordinal=4,
            pair_id="P2_WF20_TREATMENT",
            pair_position="WHITE_RECOVERY",
            branch="T20_R20_R21",
            profile_id="WF20_25",
            release_key="t20_treatment",
            root=c20_treatment_root,
            release_action_ordinal=2,
            requires_completed_visible_ordinals=(3,),
        ),
        _release_action(
            visible_ordinal=5,
            pair_id="P3_WF23_CONTROL",
            pair_position="COLOR",
            branch="C23_NO_R20_R21",
            profile_id="WF23_25",
            release_key="c23_control",
            root=c23_control_root,
            release_action_ordinal=1,
            requires_completed_visible_ordinals=tuple(range(1, 5)),
        ),
        _release_action(
            visible_ordinal=6,
            pair_id="P3_WF23_CONTROL",
            pair_position="WHITE_RECOVERY",
            branch="C23_NO_R20_R21",
            profile_id="WF23_25",
            release_key="c23_control",
            root=c23_control_root,
            release_action_ordinal=2,
            requires_completed_visible_ordinals=(5,),
        ),
        _release_action(
            visible_ordinal=7,
            pair_id="P4_WF23_TREATMENT",
            pair_position="COLOR",
            branch="T23_R20_R21",
            profile_id="WF23_25",
            release_key="t23_treatment",
            root=c23_treatment_root,
            release_action_ordinal=1,
            requires_completed_visible_ordinals=(5, 6),
        ),
        _release_action(
            visible_ordinal=8,
            pair_id="P4_WF23_TREATMENT",
            pair_position="WHITE_RECOVERY",
            branch="T23_R20_R21",
            profile_id="WF23_25",
            release_key="t23_treatment",
            root=c23_treatment_root,
            release_action_ordinal=2,
            requires_completed_visible_ordinals=(7,),
        ),
        *_dither_actions(dither_path, dither_root, dither_summary),
    ]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": "OFFLINE_SCHEDULABLE_NOT_AT_EXECUTION_GATE",
        "release_set": releases,
        "schedule": {
            "pair_count": 5,
            "visible_action_count": 10,
            "color_screen_count": 5,
            "white_recovery_count": 5,
            "same_evening_scheduling_allowed": True,
            "single_automatic_batch_allowed": False,
            "actions": actions,
        },
        "onsite_entry_gate": {
            "operator_physically_present_required": True,
            "current_installed_c20_phase_b_read_only_diagnostic_committed_pass_required": True,
            "fresh_complete_electrical_and_temperature_gate_required": True,
            "j2_stays_off_during_every_app_only_flash_and_diagnostic": True,
            "j2_may_be_opened_only_for_one_separately_authorized_visible_action": True,
            "clean_white_and_j2_off_required_between_pairs": True,
            "current_user_report": {
                "j2": "DISCONNECTED",
                "operator_at_hardware": False,
                "independently_verified": False,
            },
        },
        "stop_policy": {
            "any_protocol_or_identity_mismatch": "STOP_NO_RETRY",
            "any_current_or_temperature_anomaly": "PHYSICAL_CUTOFF_AND_STOP",
            "any_unclean_white_recovery": "STOP_BEFORE_NEXT_PAIR",
            "any_unknown_or_unfinalized_result": "STOP_NO_FALLBACK",
            "automatic_next_pair": False,
        },
        "screening_decision": {
            "same_profile_comparisons": ["T20_MINUS_C20", "T23_MINUS_C23"],
            "direct_t20_minus_t23_body_only_attribution_allowed": False,
            "brightness_only_counts_as_candidate_new_color": False,
            "dither_perceptual_mix_counts_as_new_electrophoretic_primary": False,
            "candidate_requires": [
                "same_atlas_position_hue_or_color_class_change",
                "no_electrical_or_temperature_anomaly",
                "clean_white_recovery_after_candidate",
                "recorded_fixed-view observation",
            ],
            "ten_action_screening_can_confirm_new_color": False,
            "ten_action_screening_can_select_candidate_for_verification": True,
            "candidate_followup": {
                "separate_fresh_gate_and_authorization_required": True,
                "automatic_chain_into_qualification": False,
                "first": "WINNING_PATH_REPEATABILITY",
                "second": "FIXED_CAPTURE_AND_COLORIMETRY",
                "then_if_still_positive": [
                    "ROOT_CAUSE_CONTROLS",
                    "GHOSTING_AND_WHITE_RECOVERY",
                    "TEMPERATURE_AND_SPI_ROBUSTNESS",
                ],
                "run_all_137_plus_qualification_actions_immediately": False,
            },
        },
        "offline_state": {
            "all_release_deep_validations_passed": True,
            "execution_gate_reached": False,
            "live_authorized": False,
            "authorizations_created": 0,
            "claims_created": 0,
            "network_requests": 0,
            "serial_or_com_accesses": 0,
            "firmware_uploads": 0,
            "j2_changes": 0,
            "visible_refreshes": 0,
        },
    }
    unsigned["readiness_id"] = sha256(unsigned)
    return {
        **unsigned,
        "integrity": {
            "algorithm": "sha256",
            "scope": "entire object excluding integrity; canonical UTF-8 JSON",
            "canonical_sha256": sha256(unsigned),
        },
    }


def validate_readiness(root: Mapping[str, Any]) -> dict[str, Any]:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise TenActionReadinessError("readiness integrity is absent")
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    canonical = sha256(unsigned)
    if (
        integrity.get("algorithm") != "sha256"
        or integrity.get("scope")
        != "entire object excluding integrity; canonical UTF-8 JSON"
        or integrity.get("canonical_sha256") != canonical
    ):
        raise TenActionReadinessError("readiness canonical integrity differs")
    body = {key: value for key, value in unsigned.items() if key != "readiness_id"}
    if unsigned.get("readiness_id") != sha256(body):
        raise TenActionReadinessError("readiness ID differs")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise TenActionReadinessError("readiness schema/kind differs")
    releases = root.get("release_set")
    if not isinstance(releases, Mapping) or set(releases) != {
        "c20_control",
        "t20_treatment",
        "c23_control",
        "t23_treatment",
        "factory_otp_dither",
    }:
        raise TenActionReadinessError("readiness release set differs")
    rebuilt = build_readiness(
        c20_control_file=Path(str(releases["c20_control"]["path"])),
        c20_treatment_file=Path(str(releases["t20_treatment"]["path"])),
        c23_control_file=Path(str(releases["c23_control"]["path"])),
        c23_treatment_file=Path(str(releases["t23_treatment"]["path"])),
        dither_release_file=Path(str(releases["factory_otp_dither"]["path"])),
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(root):
        raise TenActionReadinessError(
            "readiness differs from deterministic deep reconstruction"
        )
    actions = root["schedule"]["actions"]
    if (
        [item["visible_ordinal"] for item in actions] != list(range(1, 11))
        or len({item["hardware_action_id"] for item in actions}) != 10
        or sum(item["visible_class"] == "COLOR_SCREEN" for item in actions) != 5
        or sum(item["visible_class"] == "WHITE_RECOVERY" for item in actions) != 5
    ):
        raise TenActionReadinessError("ten-action inventory differs")
    return {
        "valid": True,
        "readiness_id": root["readiness_id"],
        "canonical_sha256": canonical,
        "pair_count": 5,
        "visible_action_count": 10,
        "color_screen_count": 5,
        "white_recovery_count": 5,
        "same_evening_scheduling_allowed": True,
        "execution_gate_reached": False,
        "live_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refreshes": 0,
    }


def _load(path: Path) -> dict[str, Any]:
    _, payload = _read_regular(path, label="ten-action readiness")
    return dict(_decode(payload, label="ten-action readiness"))


def _write_new(path: Path, root: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(root) + b"\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise TenActionReadinessError("readiness output already exists") from error
    except OSError as error:
        raise TenActionReadinessError(f"could not write readiness: {error}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("materialize", allow_abbrev=False)
    build.add_argument("--c20-control", type=Path, required=True)
    build.add_argument("--c20-treatment", type=Path, required=True)
    build.add_argument("--c23-control", type=Path, required=True)
    build.add_argument("--c23-treatment", type=Path, required=True)
    build.add_argument("--dither-release", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("validate", allow_abbrev=False)
    check.add_argument("--readiness", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "materialize":
            root = build_readiness(
                c20_control_file=args.c20_control,
                c20_treatment_file=args.c20_treatment,
                c23_control_file=args.c23_control,
                c23_treatment_file=args.c23_treatment,
                dither_release_file=args.dither_release,
            )
            report = validate_readiness(root)
            _write_new(args.output, root)
            report["readiness_file"] = str(args.output.resolve())
        else:
            report = validate_readiness(_load(args.readiness))
    except (TenActionReadinessError, KeyError, TypeError) as error:
        print(f"ten-action readiness error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
