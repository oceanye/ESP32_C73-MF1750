#!/usr/bin/env python3
"""Fail-closed host for fresh T4 matched-swap successor V4."""

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

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_once as mechanics,
)


class T4MatchedSwapSuccessorV4RunnerError(RuntimeError):
    """Raised before stale or mismatched V4 I/O could occur."""


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V4"
    )


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_claims"
    )


def _source_route_leaked(serialized: str) -> bool:
    predecessors = (
        "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v2",
        "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1",
        "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v2",
        "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v3",
    )
    return pack.CONFIG.base_route not in serialized or any(
        route in serialized for route in predecessors
    )


def _bind_wire_action(host: Any) -> None:
    report_action = pack.build_report()["actions"][0]
    wire_actions = deepcopy(host.base.runner.ACTIONS)
    if len(wire_actions) != 1:
        raise T4MatchedSwapSuccessorV4RunnerError("T4 V4 wire action count differs")
    wire_actions[0]["round"] = report_action["round"]
    wire_actions[0]["prior_static_action_id"] = report_action[
        "prior_static_action_id"
    ]
    wire_actions[0]["boot_admission"] = deepcopy(report_action["boot_admission"])
    host.base.runner.ACTIONS = tuple(wire_actions)
    host.base.runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in wire_actions
    )
    host.base.runner.ACTION_IDS = tuple(item["action_id"] for item in wire_actions)


def _validate_j2_off_diagnostic_evidence(
    host: Any, base_url: str
) -> dict[str, Any]:
    path = _output_root() / "j2-off-diagnostic.json"
    value = _read_integrity_json(path, label="T4 V4 J2-OFF diagnostic")
    report = pack.build_report()
    expected_binding = {
        "bound": True,
        "bin": {
            "bytes": pack.ARTIFACTS[pack.STAGE]["bin_bytes"],
            "sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        },
        "elf": {
            "bytes": pack.ARTIFACTS[pack.STAGE]["elf_bytes"],
            "sha256": pack.ARTIFACTS[pack.STAGE]["elf_sha256"],
        },
    }
    transcript = value.get("transcript")
    expected_calls = [
        ("GET", "version", 200),
        ("GET", "manifest", 200),
        ("GET", "status", 200),
        ("GET", "report", 200),
    ]
    if (
        value.get("kind")
        != (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v4-j2-off-diagnostic"
        )
        or value.get("outcome") != "j2_off_diagnostic_pass"
        or value.get("j2_confirmed_off") is not True
        or value.get("artifact_preflight_completed_before_network") is not True
        or value.get("fresh_cursor_key_absent") is not True
        or value.get("campaign_boot_key_present_and_current") is not True
        or value.get("next_ordinal") != 1
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("permanent_claims_created") != 0
        or value.get("visible_refreshes") != 0
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or value.get("output_write_contract") != "O_EXCL"
        or value.get("base_url") != base_url
        or value.get("build_tag") != pack.CONFIG.build_tag
        or value.get("campaign_id") != pack.CONFIG.campaign_id
        or value.get("contract_id") != report["contract_id"]
        or value.get("test_id") != pack.CONFIG.test_id
        or value.get("local_artifact_binding") != expected_binding
        or not isinstance(transcript, list)
        or [
            (item.get("method"), item.get("endpoint"), item.get("status"))
            for item in transcript
        ]
        != expected_calls
        or any(not isinstance(item.get("response"), Mapping) for item in transcript)
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 J2-OFF diagnostic semantics differ"
        )
    responses = [item["response"] for item in transcript]
    host._validate_version(responses[0])  # noqa: SLF001
    host._validate_manifest(responses[1])  # noqa: SLF001
    boot_nonce = host._validate_ready_status(  # noqa: SLF001
        responses[2], 1, expected_busy=0
    )
    host._validate_prior_terminal_report(  # noqa: SLF001
        responses[3], 1, boot_nonce
    )
    if (
        value.get("boot_nonce") != boot_nonce
        or value.get("status") != responses[2]
        or value.get("report") != responses[3]
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 J2-OFF diagnostic transcript binding differs"
        )
    return value


def _install_v4_mechanics() -> None:
    mechanics.pack = pack
    mechanics._output_root = _output_root  # noqa: SLF001
    mechanics._claim_root = _claim_root  # noqa: SLF001
    mechanics.source_route_leaked = _source_route_leaked
    mechanics._bind_wire_action = _bind_wire_action  # noqa: SLF001


def configure() -> Any:
    """Return an isolated V4 host without hardware or network access."""

    _install_v4_mechanics()
    host = mechanics.configure()
    original_version = host._validate_version  # noqa: SLF001
    original_manifest = host._validate_manifest  # noqa: SLF001

    def validate_version(value: Mapping[str, Any]) -> None:
        original_version(value)
        _validate_v4_authority_surface(host, value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        original_manifest(value)
        _validate_v4_authority_surface(host, value)

    for layer in (host, host.v3, host.base, host.base.runner):
        layer._validate_version = validate_version
        layer._validate_manifest = validate_manifest
    original_run_once = host.run_once

    def run_once(
        base_url: str,
        ordinal: int,
        *,
        confirm_gnd_normal: bool = False,
        requester: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if confirm_gnd_normal is not True:
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 run requires explicit post-reseat GND-normal confirmation"
            )
        diagnostic = _validate_j2_off_diagnostic_evidence(host, base_url)
        expected_boot_nonce = diagnostic["boot_nonce"]
        selected_requester = requester or host._diagnostic_http_request  # noqa: SLF001

        def same_boot_requester(*args: Any, **request_kwargs: Any) -> Any:
            status, response = selected_requester(*args, **request_kwargs)
            observed_boot_nonce = response.get("boot_nonce")
            if (
                observed_boot_nonce is not None
                and observed_boot_nonce != expected_boot_nonce
            ):
                raise host.base.runner.RecheckError(
                    "T4 V4 live response boot nonce differs from J2-OFF diagnostic"
                )
            return status, response

        return original_run_once(
            base_url,
            ordinal,
            requester=same_boot_requester,
            **kwargs,
        )

    host.run_once = run_once
    expected = pack.build_report()["actions"][0]
    observed = list(host.base.runner.ACTIONS)
    if len(observed) != 1 or observed[0].get("boot_admission") != expected.get(
        "boot_admission"
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 explicit-null boot admission differs"
        )
    if observed[0]["action_id"] in pack.non_reusable_action_ids():
        raise T4MatchedSwapSuccessorV4RunnerError(
            "predecessor action became executable"
        )
    if len(pack.non_reusable_action_ids()) != 18:
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 registry must contain 18 tombstones"
        )
    return host


def _validate_v4_authority_surface(host: Any, value: Mapping[str, Any]) -> None:
    exact = {
        "t4_v3_terminal_fault": pack.v3_terminal_fault_binding(),
        "w9_permanent_claim": pack.completed_w9_white_claim_binding(),
        "w9_post_white_protective_off": pack.w9_post_off_binding(),
        "operator_gnd_assertion": deepcopy(pack.OPERATOR_GND_ASSERTION),
    }
    for key, expected in exact.items():
        if value.get(key) != expected:
            raise host.base.runner.RecheckError(
                f"T4 V4 authority surface {key} differs"
            )


def dry_validate(
    *, verify_authorities: bool = True, verify_artifacts: bool = True
) -> dict[str, Any]:
    _install_v4_mechanics()
    value = pack.dry_validate(verify_authorities=verify_authorities)
    if verify_artifacts:
        mechanics._verify_artifacts()  # noqa: SLF001
    host = configure()
    report = pack.build_report()
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-runner-validation-v4"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "default_evidence_root": str(host.DEFAULT_OUTPUT),
        "claim_root": str(host.DEFAULT_CLAIMS),
        "campaign_id": report["contract"]["campaign_id"],
        "predecessor_authorities": deepcopy(pack.validate_authorities()),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "explicit_base_url_required_for_live_cli": True,
        "default_base_url": None,
    }


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise T4MatchedSwapSuccessorV4RunnerError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4MatchedSwapSuccessorV4RunnerError(
            f"{label} is not UTF-8 JSON"
        ) from error
    if not isinstance(value, dict):
        raise T4MatchedSwapSuccessorV4RunnerError(f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if not isinstance(integrity, Mapping):
        raise T4MatchedSwapSuccessorV4RunnerError(f"{label} integrity missing")
    recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if (
        integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or recorded != hashlib.sha256(pack.canonical_json(body)).hexdigest()
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            f"{label} canonical integrity differs"
        )
    return value


def _validate_permanent_claim(expected_action: Mapping[str, Any]) -> dict[str, Any]:
    path = _claim_root() / f"{expected_action['action_id']}.json"
    value = _read_integrity_json(path, label="T4 V4 permanent claim")
    if (
        value.get("kind")
        != (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v4-permanent-claim"
        )
        or value.get("schema_version") != 1
        or value.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or value.get("write_contract") != "O_EXCL"
        or value.get("action") != dict(expected_action)
        or value.get("firmware_sha256")
        != pack.ARTIFACTS[pack.STAGE]["bin_sha256"]
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 permanent claim semantics differ"
        )
    return value


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    """Deep-check one fixed V4 COMPLETE or reconciled-FAULT terminal record."""

    resolved = Path(path).resolve()
    complete_path = (_output_root() / "action-01-position-balanced-atlas.json").resolve()
    fault_path = (
        _output_root() / "action-01-terminal-read-only-salvage-reconciled.json"
    ).resolve()
    if resolved not in (complete_path, fault_path):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "terminal evidence path is not a fixed T4 V4 output"
        )
    value = _read_integrity_json(resolved, label="T4 V4 terminal evidence")
    report = pack.build_report()
    action = report["actions"][0]
    terminal = value.get("terminal_report")
    if (
        value.get("action") != action
        or value.get("firmware_sha256")
        != pack.ARTIFACTS[pack.STAGE]["bin_sha256"]
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or not isinstance(terminal, Mapping)
        or terminal.get("campaign_id") != report["contract"]["campaign_id"]
        or terminal.get("contract_id") != report["contract_id"]
        or terminal.get("descriptor_id") != action["descriptor_id"]
        or terminal.get("action_id") != action["action_id"]
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("no_retry") is not True
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 terminal lineage or one-driver semantics differ"
        )
    claim = _validate_permanent_claim(action)
    expected_claim_path = _claim_root() / f"{action['action_id']}.json"
    expected_terminal_exact = {
        "build_tag": pack.CONFIG.build_tag,
        "test_id": pack.CONFIG.test_id,
        "campaign_id": pack.CONFIG.campaign_id,
        "contract_id": report["contract_id"],
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "ordinal": action["ordinal"],
        "round": action["round"],
        "profile_id": action["profile_id"],
        "palette_source": action["palette_source"],
        "global_header": action["global_header"],
        "global_tuple_id": action["global_tuple_id"],
        "waveform_binding": action["waveform_binding"],
        "driver_entry": "epdDisplayCompiledChromaGrid",
    }
    if (
        any(terminal.get(key) != expected for key, expected in expected_terminal_exact.items())
        or value.get("boot_nonce") != terminal.get("boot_nonce")
        or claim.get("boot_nonce") != terminal.get("boot_nonce")
        or value.get("claim_file") != str(expected_claim_path)
    ):
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 terminal identity, boot, or claim binding differs"
        )
    expected_kind_base = (
        "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
        "swap-confirmation-successor-v4"
    )
    if resolved == complete_path:
        transcript = value.get("transcript")
        expected_calls = [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
            ("POST", "arm", 201),
            ("POST", "execute", 202),
            ("GET", "report", 200),
        ]
        if (
            value.get("kind") != f"{expected_kind_base}-result"
            or value.get("outcome") != "complete_pass"
            or value.get("visible_refreshes") != 1
            or value.get("network") != {"get": 5, "arm_post": 1, "execute_post": 1}
            or not isinstance(transcript, list)
            or [
                (item.get("method"), item.get("endpoint"), item.get("status"))
                for item in transcript
            ]
            != expected_calls
            or terminal.get("terminal_state") != "COMPLETE"
            or terminal.get("result") is not True
            or terminal.get("campaign_complete") is not True
            or terminal.get("next_ordinal") != 2
        ):
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 COMPLETE evidence semantics differ"
            )
        expected_paths = [
            f"{pack.CONFIG.base_route}/{endpoint}"
            for _, endpoint, _ in expected_calls
        ]
        if (
            [item.get("path") for item in transcript] != expected_paths
            or any(not isinstance(item.get("response"), Mapping) for item in transcript)
        ):
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 COMPLETE transcript paths or responses differ"
            )
        responses = [item["response"] for item in transcript]
        validation_host = configure()
        validation_host._validate_version(responses[0])  # noqa: SLF001
        validation_host._validate_manifest(responses[1])  # noqa: SLF001
        replay_boot_nonce = validation_host._validate_ready_status(  # noqa: SLF001
            responses[2], 1, expected_busy=1
        )
        validation_host._validate_prior_terminal_report(  # noqa: SLF001
            responses[3], 1, replay_boot_nonce
        )
        if replay_boot_nonce != terminal.get("boot_nonce"):
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 COMPLETE preflight and terminal boot differ"
            )
        arm_response = responses[4]
        execute_response = responses[5]
        arm_nonce = arm_response.get("arm_nonce")
        identity_exact = {
            "build_tag": pack.CONFIG.build_tag,
            "test_id": pack.CONFIG.test_id,
            "campaign_id": pack.CONFIG.campaign_id,
            "contract_id": report["contract_id"],
            "device_api_version": pack.DEVICE_API_VERSION,
            "identity_revision": pack.IDENTITY_REVISION,
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "boot_nonce": replay_boot_nonce,
        }
        if (
            not isinstance(arm_nonce, str)
            or not arm_nonce
            or arm_response.get("accepted") is not True
            or arm_response.get("armed") is not True
            or arm_response.get("not_hardware_authorization") is not True
            or execute_response.get("accepted") is not True
            or execute_response.get("execute_consumed") is not True
            or execute_response.get("no_retry") is not True
            or execute_response.get("no_recovery") is not True
            or any(
                arm_response.get(key) != expected
                or execute_response.get(key) != expected
                for key, expected in identity_exact.items()
            )
            or responses[6] != terminal
        ):
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 COMPLETE arm, execute, or final report differs"
            )
        arm_headers = transcript[4].get("headers")
        execute_headers = transcript[5].get("headers")
        expected_common_headers = {
            "X-EC5-Action-Id": action["action_id"],
            "X-EC5-Boot-Nonce": replay_boot_nonce,
            "X-EC5-Build-Tag": pack.CONFIG.build_tag,
            "X-EC5-Campaign-Id": pack.CONFIG.campaign_id,
            "X-EC5-Descriptor-Id": action["descriptor_id"],
            "X-EC5-Ordinal": "1",
            "X-EC5-Test-Id": pack.CONFIG.test_id,
        }
        if (
            not isinstance(arm_headers, Mapping)
            or not isinstance(execute_headers, Mapping)
            or any(arm_headers.get(key) != expected for key, expected in expected_common_headers.items())
            or any(execute_headers.get(key) != expected for key, expected in expected_common_headers.items())
            or arm_headers.get("X-EC5-Intent") != pack.ARM_INTENT
            or execute_headers.get("X-EC5-Intent") != pack.EXECUTE_INTENT
            or execute_headers.get("X-EC5-Arm-Nonce") != arm_nonce
        ):
            raise T4MatchedSwapSuccessorV4RunnerError(
                "T4 V4 COMPLETE request headers or nonces differ"
            )
        validation_host.v3._validate_complete_report(  # noqa: SLF001
            terminal, 1, replay_boot_nonce
        )
        state = "COMPLETE"
    else:
        raise T4MatchedSwapSuccessorV4RunnerError(
            "T4 V4 reconciled FAULT evidence is fail-closed until the reviewed "
            "consumed-failure/raw-salvage/reconciliation producer exists"
        )
    return {
        "verified": True,
        "terminal_state": state,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "firmware_sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "action_must_not_be_retried": True,
        "source_success_claimed": state == "COMPLETE",
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument("--timeout", type=float, default=10.0)
    action = sub.add_parser("run", allow_abbrev=False)
    action.add_argument("--base-url", required=True)
    action.add_argument("--confirm-j2-on", action="store_true", required=True)
    action.add_argument(
        "--confirm-gnd-normal", action="store_true", required=True
    )
    action.add_argument(
        "--confirm-external-pre-white", action="store_true", required=True
    )
    action.add_argument("--poll-seconds", type=float, default=65.0)
    action.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            result = pack.build_report()
        elif args.command == "prebuild-validate":
            result = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            result = dry_validate()
        elif args.command == "diagnose-j2-off":
            host = configure()
            result = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            host = configure()
            result = host.run_once(
                args.base_url,
                1,
                claims=host.DEFAULT_CLAIMS,
                output=host.ACTION_OUTPUTS[1],
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_external_pre_white=args.confirm_external_pre_white,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (ValueError, RuntimeError) as error:
        print(f"RAW-P16 T4 matched-swap successor V4 error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
