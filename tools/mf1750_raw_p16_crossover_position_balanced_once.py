#!/usr/bin/env python3
"""Fail-closed host for fresh RAW-P16 crossover and white campaigns.

No command in this runner flashes firmware, resets the ESP32, controls J2,
retries, recovers, or chains to another action.  The two J2-OFF diagnostic
commands perform four GETs without a claim or refresh.  ``run-atlas`` and
``run-white`` each consume exactly one independently bound action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_raw_p16_crossover_position_balanced_pack as pack  # noqa: E402


class CrossoverError(RuntimeError):
    """Raised before an unverified or stale crossover action can run."""


LEGACY_T3_TOMBSTONED_STAGE = "t3-ac-repeat"
LEGACY_T3_TOMBSTONED_ACTION_ID = (
    "4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a"
)


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load isolated host mechanics: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _atlas_claim_root(cfg: pack.StageConfig) -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / f".mf1750_raw_p16_crossover_{cfg.suffix.lower()}_claims"
    )


def _white_claim_root(cfg: pack.WhiteConfig) -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / f".mf1750_raw_p16_crossover_{cfg.suffix.lower()}_white_claims"
    )


def _artifact_binding(stage: pack.Stage) -> dict[str, Any]:
    values = pack.ARTIFACTS[stage]
    firmware_bin, firmware_elf = pack.artifact_paths(stage)
    return {
        "bin": {
            "path": firmware_bin,
            "bytes": values["bin_bytes"],
            "sha256": values["bin_sha256"],
        },
        "elf": {
            "path": firmware_elf,
            "bytes": values["elf_bytes"],
            "sha256": values["elf_sha256"],
        },
    }


def _white_artifact_binding(stage: pack.WhiteStage) -> dict[str, Any]:
    values = pack.WHITE_ARTIFACTS[stage]
    firmware_bin, firmware_elf = pack.white_artifact_paths(stage)
    return {
        "bin": {
            "path": firmware_bin,
            "bytes": values["bin_bytes"],
            "sha256": values["bin_sha256"],
        },
        "elf": {
            "path": firmware_elf,
            "bytes": values["elf_bytes"],
            "sha256": values["elf_sha256"],
        },
    }


def _verify_binding(binding: Mapping[str, Mapping[str, Any]]) -> None:
    for name in ("bin", "elf"):
        item = binding[name]
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise CrossoverError(f"reviewed {name} artifact is missing: {path}")
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise CrossoverError(f"reviewed {name} artifact identity differs: {path}")


def _pack_adapter(stage: pack.Stage) -> SimpleNamespace:
    cfg = pack.STAGES[stage]
    report = pack.build_report(stage)
    return SimpleNamespace(
        VARIANT_KEY=cfg.variant_key,
        BUILD_TAG=cfg.build_tag,
        TEST_ID=cfg.test_id,
        CAMPAIGN_ID=cfg.campaign_id,
        NVS_NAMESPACE=cfg.nvs_namespace,
        NVS_KEY=cfg.nvs_key,
        NVS_BOOT_KEY=cfg.nvs_boot_key,
        DEVICE_API_VERSION=pack.DEVICE_API_VERSION,
        IDENTITY_REVISION=pack.IDENTITY_REVISION,
        CLASSIFICATION=pack.CLASSIFICATION,
        BASE_ROUTE=cfg.base_route,
        CODE_ROWS=pack.CODE_ROWS,
        GRID_Y_BY_ROW=pack.GRID_Y_BY_ROW,
        build_report=lambda: deepcopy(report),
    )


def _validate_capabilities(host: Any, value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "crossover_r20_position_balanced_probe",
        "position_balanced_atlas",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
    )
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_r20_controller_parity_probe",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
        "colour_qualification",
        "main_campaign_resume_after_containment",
    )
    if any(value.get(key) is not True for key in required_true):
        raise host.base.runner.RecheckError("crossover capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise host.base.runner.RecheckError(
            "crossover forbidden capability contract differs"
        )


def _validate_manifest(
    host: Any,
    adapter: SimpleNamespace,
    report: Mapping[str, Any],
    value: Mapping[str, Any],
) -> None:
    host.base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    expected = {
        "layout_id": adapter.VARIANT_KEY,
        "actions": list(host.base.runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": report["contract"]["external_containment"],
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise host.base.runner.RecheckError(f"crossover manifest {key} differs")
    layout = value.get("history_layout", {})
    expected_layout = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(pack.GRID_Y_BY_ROW),
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 552,
        "cell_width": 52,
        "cell_height": 100,
        "gap_x": 8,
        "gap_y": 36,
        "background_code": 7,
        "border": False,
        "same_layout_both_controllers": True,
        "controller_dtm_byte_identical": True,
        "controller_r20_payloads_byte_identical": False,
        "cs2_position_mirrored": False,
        "spatial_dither": False,
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "one_visible_refresh_per_action": True,
        "samples_per_code_per_controller_per_frame": 4,
        "primary_codes": [3, 5, 6, 7],
        "guard_codes": [4],
        "control_codes": [0, 1, 2],
        "qualified_colours": 0,
        "colour_equivalence_claimed": False,
        "controller_bus_capture_claimed": False,
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise host.base.runner.RecheckError(
                f"crossover history layout {key} differs"
            )
    _validate_capabilities(host, value)


def _configure_atlas(stage: pack.Stage) -> Any:
    cfg = pack.STAGES[stage]
    report = pack.build_report(stage)
    adapter = _pack_adapter(stage)
    host = _load_module(
        REPO_ROOT / "tools/mf1750_runtime_lut_same_r20_parity_4x8_v2_once.py",
        f"_mf1750_p16x_{cfg.suffix.lower()}_host",
    )
    binding = _artifact_binding(stage)
    host.pack = adapter
    host.REPORT = report
    host.v3.pack = adapter
    host.v3.REPORT = report
    host.base.pack = adapter
    host.base._REPORT = report  # noqa: SLF001
    host.base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0  # noqa: SLF001
    runner = host.base.runner
    runner.BUILD_TAG = cfg.build_tag
    runner.TEST_ID = cfg.test_id
    runner.CAMPAIGN_ID = cfg.campaign_id
    runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
    runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
    runner.CONTRACT_ID = report["contract_id"]
    runner.CLASSIFICATION = pack.CLASSIFICATION
    runner.DEVICE_KIND_PREFIX = f"mf1750-ec5-{cfg.route_slug}"
    runner.EVIDENCE_KIND_PREFIX = f"mf1750-ec5-{cfg.route_slug}"
    runner.NVS_NAMESPACE = cfg.nvs_namespace
    runner.NVS_KEY = cfg.nvs_key
    host.FIRMWARE_BYTES = int(binding["bin"]["bytes"])
    host.FIRMWARE_SHA256 = str(binding["bin"]["sha256"])
    host.ELF_BYTES = int(binding["elf"]["bytes"])
    host.ELF_SHA256 = str(binding["elf"]["sha256"])
    host.BUILD_DIR = Path(binding["bin"]["path"]).parent
    runner.FIRMWARE_BYTES = host.FIRMWARE_BYTES
    runner.FIRMWARE_SHA256 = host.FIRMWARE_SHA256
    runner.ENDPOINTS = {
        name: f"{cfg.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    runner.ARM_INTENT = pack.ARM_INTENT
    runner.EXECUTE_INTENT = pack.EXECUTE_INTENT
    actions = deepcopy(host._actions())  # noqa: SLF001
    runner.ACTIONS = actions
    runner.DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in actions)
    runner.ACTION_IDS = tuple(item["action_id"] for item in actions)
    runner.DEFAULT_CLAIMS = _atlas_claim_root(cfg)
    runner.DEFAULT_OUTPUT = (
        REPO_ROOT
        / ".test-output/hardware"
        / f"MF1750_RAW_P16_CROSSOVER_{cfg.suffix}_20260830_V1"
    )
    host.DIAGNOSTIC_OUTPUT = runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
    host.ACTION_OUTPUTS = {
        1: runner.DEFAULT_OUTPUT / "action-01-position-balanced-atlas.json"
    }

    def capabilities(value: Mapping[str, Any]) -> None:
        _validate_capabilities(host, value)

    def manifest(value: Mapping[str, Any]) -> None:
        _validate_manifest(host, adapter, report, value)

    host._validate_capabilities = capabilities
    host._validate_manifest = manifest
    host.v3._validate_capabilities = capabilities
    host.v3._validate_manifest = manifest
    host.base._validate_capabilities = capabilities
    host.base._validate_manifest = manifest
    runner._validate_manifest = manifest
    # Existing version/ready/preflight validators are reusable after the
    # immutable globals above have been rebound.
    host.v3._validate_version = host._validate_version  # noqa: SLF001
    host.v3._validate_ready_status = host._validate_ready_status  # noqa: SLF001
    host.v3._preflight = host._preflight  # noqa: SLF001
    host.base._validate_version = host._validate_version  # noqa: SLF001
    host.base._validate_ready_status = host._validate_ready_status  # noqa: SLF001
    host.base._preflight = host._preflight  # noqa: SLF001
    runner._validate_version = host._validate_version  # noqa: SLF001
    runner._validate_ready_status = host._validate_ready_status  # noqa: SLF001
    runner._preflight = host._preflight  # noqa: SLF001

    original_run_once = host.run_once

    def guarded_run_once(
        base_url: str,
        ordinal: int,
        *,
        confirm_j2_on: bool = False,
        requester: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if confirm_j2_on is not True:
            raise host.base.runner.RecheckError(
                "crossover atlas run requires explicit J2-ON confirmation"
            )
        origin = host._diagnostic_origin(base_url)  # noqa: SLF001
        selected_requester = requester or host._diagnostic_http_request  # noqa: SLF001
        return original_run_once(
            origin,
            ordinal,
            requester=selected_requester,
            **kwargs,
        )

    host.run_once = guarded_run_once
    return host


def _white_adapter(stage: pack.WhiteStage) -> SimpleNamespace:
    cfg = pack.WHITES[stage]
    report = pack.build_white_report(stage)
    action = report["action"]
    binding = _white_artifact_binding(stage)
    marker = (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        f"ROLE=OTP_WHITE_RAW_P16_CROSSOVER_{cfg.suffix.split('_')[0]}|"
        f"SHA256={action['descriptor_id']}"
    )

    def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
        if verify_artifacts:
            _verify_binding(binding)
        return deepcopy(report)

    return SimpleNamespace(
        BUILD_TAG=cfg.build_tag,
        TEST_ID=cfg.test_id,
        CAMPAIGN_ID=cfg.campaign_id,
        SOURCE_CAMPAIGN_ID=report["contract"]["source_campaign_id"],
        ENVIRONMENT=cfg.environment,
        PROFILE_ID="WF23_25",
        CONTRACT_ID=report["contract_id"],
        NVS_NAMESPACE=cfg.nvs_namespace,
        NVS_KEY=cfg.nvs_key,
        BASE_ROUTE=cfg.base_route,
        DEVICE_API_VERSION="MF1750_EC5_RAW_P16_CROSSOVER_WHITE_CONTAINMENT_DEVICE_V1",
        IDENTITY_REVISION="raw-p16-crossover-white-containment-v1",
        CLASSIFICATION=(
            "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_CONTAINMENT_"
            "ONE_ACTION_NO_RUNTIME_PAYLOAD"
        ),
        DESCRIPTOR_ID=action["descriptor_id"],
        ACTION_ID=action["action_id"],
        DESCRIPTOR_MARKER=marker,
        FRAME_SHA256=pack.FACTORY_WHITE_FRAME_SHA256,
        DTM_SHA256=pack.FACTORY_WHITE_DTM_SHA256,
        FRAME_FNV1A=pack.FACTORY_WHITE_FRAME_FNV1A,
        DTM_FNV1A=pack.FACTORY_WHITE_DTM_FNV1A,
        FIRMWARE_BIN=Path(binding["bin"]["path"]),
        FIRMWARE_ELF=Path(binding["elf"]["path"]),
        FIRMWARE_BIN_BYTES=binding["bin"]["bytes"],
        FIRMWARE_BIN_SHA256=binding["bin"]["sha256"],
        FIRMWARE_ELF_BYTES=binding["elf"]["bytes"],
        FIRMWARE_ELF_SHA256=binding["elf"]["sha256"],
        ARM_INTENT=pack.WHITE_ARM_INTENT,
        EXECUTE_INTENT=pack.WHITE_EXECUTE_INTENT,
        CLAIM_KIND=f"mf1750-raw-p16-crossover-{cfg.suffix.lower()}-white-claim",
        RESULT_KIND=f"mf1750-raw-p16-crossover-{cfg.suffix.lower()}-white-result",
        build_report=build_report,
    )


def _configure_white(stage: pack.WhiteStage) -> Any:
    cfg = pack.WHITES[stage]
    adapter = _white_adapter(stage)
    host = _load_module(
        REPO_ROOT
        / "tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_once.py",
        f"_mf1750_p16x_{cfg.suffix.lower()}_white_host",
    )
    report = adapter.build_report(verify_artifacts=False)
    action = report["action"]
    endpoints = {
        name: f"{cfg.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    host.pack = adapter
    host.REPORT = report
    host.ACTION = action
    host.ENDPOINTS = endpoints
    host.base.pack = adapter
    host.base.REPORT = report
    host.base.ACTION = action
    host.base.ENDPOINTS = endpoints
    host.base._base.pack = adapter  # noqa: SLF001
    host.base._base.REPORT = report  # noqa: SLF001
    host.base._base.ACTION = action  # noqa: SLF001
    host.base._base.ENDPOINTS = endpoints  # noqa: SLF001
    claim_root = _white_claim_root(cfg)
    output_root = (
        REPO_ROOT
        / ".test-output/hardware"
        / f"MF1750_RAW_P16_CROSSOVER_{cfg.suffix}_WHITE_20260830_V1"
    )
    host.DEFAULT_CLAIMS = claim_root
    host.DEFAULT_OUTPUT = output_root
    host.DIAGNOSTIC_OUTPUT = output_root / "j2-off-diagnostic.json"
    host.base.DEFAULT_CLAIMS = claim_root
    host.base.DEFAULT_OUTPUT = output_root
    host.base.DIAGNOSTIC_OUTPUT = host.DIAGNOSTIC_OUTPUT
    host.base.DIAGNOSTIC_KIND = (
        f"mf1750-raw-p16-crossover-{cfg.suffix.lower()}-white-j2-off-diagnostic"
    )
    host.base.ATTEMPT_KIND = (
        f"mf1750-raw-p16-crossover-{cfg.suffix.lower()}-white-attempt"
    )
    return host


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    atlas_reports = {stage: pack.build_report(stage) for stage in pack.STAGES}
    white_reports = {stage: pack.build_white_report(stage) for stage in pack.WHITES}
    if verify_artifacts:
        for stage in pack.STAGES:
            _verify_binding(_artifact_binding(stage))
        for stage in pack.WHITES:
            _verify_binding(_white_artifact_binding(stage))
    frames = [report["actions"][0]["frame"] for report in atlas_reports.values()]
    cs1 = [report["actions"][0]["cs1_dtm"] for report in atlas_reports.values()]
    cs2 = [report["actions"][0]["cs2_dtm"] for report in atlas_reports.values()]
    if not (frames[0] == frames[1] == frames[2]):
        raise CrossoverError("T1/T2/T3 packed frames differ")
    if not (cs1[0] == cs1[1] == cs1[2] == cs2[0] == cs2[1] == cs2[2]):
        raise CrossoverError("T1/T2/T3 controller DTM streams differ")
    namespaces = [
        *(cfg.nvs_namespace for cfg in pack.STAGES.values()),
        *(cfg.nvs_namespace for cfg in pack.WHITES.values()),
    ]
    if len(namespaces) != len(set(namespaces)):
        raise CrossoverError("fresh campaign NVS namespaces overlap")
    action_ids = [
        *(report["actions"][0]["action_id"] for report in atlas_reports.values()),
        *(report["action"]["action_id"] for report in white_reports.values()),
    ]
    if len(action_ids) != len(set(action_ids)):
        raise CrossoverError("fresh campaign action identities overlap")
    claim_roots = [
        *(_atlas_claim_root(cfg) for cfg in pack.STAGES.values()),
        *(_white_claim_root(cfg) for cfg in pack.WHITES.values()),
    ]
    if len(claim_roots) != len(set(claim_roots)):
        raise CrossoverError("fresh campaign claim roots overlap")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-position-balanced-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "atlas_contract_ids": {
            stage: report["contract_id"] for stage, report in atlas_reports.items()
        },
        "white_contract_ids": {
            stage: report["contract_id"] for stage, report in white_reports.items()
        },
        "identical_frame_and_dtm_across_t1_t2_t3": True,
        "fresh_nvs_namespace_count": len(namespaces),
        "fresh_action_id_count": len(action_ids),
        "fresh_claim_root_count": len(claim_roots),
        "primary_codes": [3, 5, 6, 7],
        "guard_codes": [4],
        "control_codes": [0, 1, 2],
        "no_autochain": True,
        "no_retry": True,
        "no_recovery": True,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-atlas-j2-off", allow_abbrev=False)
    diag.add_argument("--stage", choices=tuple(pack.STAGES), required=True)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument("--timeout", type=float, default=10.0)
    white_diag = sub.add_parser("diagnose-white-j2-off", allow_abbrev=False)
    white_diag.add_argument("--stage", choices=tuple(pack.WHITES), required=True)
    white_diag.add_argument("--base-url", required=True)
    white_diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    white_diag.add_argument("--timeout", type=float, default=10.0)
    atlas = sub.add_parser("run-atlas", allow_abbrev=False)
    atlas.add_argument("--stage", choices=tuple(pack.STAGES), required=True)
    atlas.add_argument("--base-url", required=True)
    atlas.add_argument("--confirm-j2-on", action="store_true", required=True)
    atlas.add_argument(
        "--confirm-external-pre-white", action="store_true", required=True
    )
    atlas.add_argument("--poll-seconds", type=float, default=65.0)
    atlas.add_argument("--poll-count", type=int, default=60)
    white = sub.add_parser("run-white", allow_abbrev=False)
    white.add_argument("--stage", choices=tuple(pack.WHITES), required=True)
    white.add_argument("--base-url", required=True)
    white.add_argument("--confirm-j2-on", action="store_true", required=True)
    white.add_argument("--poll-seconds", type=float, default=65.0)
    white.add_argument("--poll-count", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = pack.campaign_matrix()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-atlas-j2-off":
            host = _configure_atlas(args.stage)
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        elif args.command == "diagnose-white-j2-off":
            host = _configure_white(args.stage)
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        elif args.command == "run-atlas":
            if args.stage == LEGACY_T3_TOMBSTONED_STAGE:
                raise CrossoverError(
                    "legacy T3 AC-repeat action is tombstoned before request/claim; "
                    "use a fresh profile-following successor"
                )
            host = _configure_atlas(args.stage)
            value = host.run_once(
                args.base_url,
                1,
                claims=host.base.runner.DEFAULT_CLAIMS,
                output=host.ACTION_OUTPUTS[1],
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                confirm_j2_on=args.confirm_j2_on,
                confirm_external_pre_white=args.confirm_external_pre_white,
            )
        else:
            host = _configure_white(args.stage)
            value = host.run_once(
                args.base_url,
                claims=host.base.DEFAULT_CLAIMS,
                output=host.base.DEFAULT_OUTPUT / "action-01-factory-otp-white.json",
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (CrossoverError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 crossover error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
