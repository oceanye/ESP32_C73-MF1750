#!/usr/bin/env python3
"""Fail-closed host runner for the V2 per-sample-reset PON -> POF probe."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_power_qualifier_pon_pof_no_drf_v2_pack as pack  # noqa: E402


_BASE_PATH = Path(__file__).with_name(
    "mf1750_power_qualifier_pon_pof_no_drf_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_power_qualifier_pon_pof_no_drf_v2_runner_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load isolated V2 runner base")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

KIND_PREFIX = "mf1750-power-qualifier-pon-pof-no-drf-v2"
ENDPOINT_BASE = "/api/ec5/power-qualifier-pon-pof-no-drf-v2"
ENDPOINTS = {
    name: f"{ENDPOINT_BASE}/{name}"
    for name in ("version", "manifest", "status", "report", "qualify", "arm", "execute")
}
QUALIFY_INTENT = "QUALIFY_PER_SAMPLE_RESET_EXACT_DUAL_REVISION_ONCE"
ARM_INTENT = "ARM_ONE_PON_POF_NO_DRF_POWER_PATH_PROBE_V2"
EXECUTE_INTENT = "EXECUTE_ARMED_PON_POF_NO_DRF_POWER_PATH_PROBE_V2_ONCE"
REPORT = pack.build_report()
ACTION = deepcopy(REPORT["actions"][0])

BUILD_DIR = REPO_ROOT / ".pio" / "build-power-qualifier-pon-pof-no-drf-v2" / pack.ENV_NAME
FIRMWARE_BIN = BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = BUILD_DIR / "firmware.elf"
FIRMWARE_BIN_BYTES: int | None = 788_736
FIRMWARE_BIN_SHA256: str | None = (
    "0af84715f1e040883aa270fb365b1bd833e6fbf2192d57c8d06e67b56467fdec"
)
FIRMWARE_ELF_BYTES: int | None = 13_119_644
FIRMWARE_ELF_SHA256: str | None = (
    "5b4149b8952d1d1f5d19d7cac9928aa9cf53f4f16c7a0f94f66ae1b853fb7f4b"
)
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_power_qualifier_pon_pof_no_drf_v2_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_20260825"
)

ALLOWED_COMMAND_PAYLOAD_SEQUENCE = [
    "RESET_CS1_SAMPLE1",
    "REV_CS1_SAMPLE1_70_EXPECT_010104",
    "RESET_CS1_SAMPLE2",
    "REV_CS1_SAMPLE2_70_EXPECT_010104",
    "RESET_CS2_SAMPLE1",
    "REV_CS2_SAMPLE1_70_EXPECT_010104",
    "RESET_CS2_SAMPLE2",
    "REV_CS2_SAMPLE2_70_EXPECT_010104",
    "FINAL_POSTURE_RESET",
    "AA_495520080918",
    "PWR_01_3F",
    "PSR_00_5F69",
    "BTST1_05_401F1F2C",
    "BTST3_08_6F1F1F22",
    "BTST2_06_6F1F1717",
    "POFS_03_00540044",
    "TCON_60_0200",
    "PLL_30_08",
    "CDI_50_3F",
    "TRES_61_02000258",
    "PWS_E3_2F",
    "T_VDCS_84_01",
    "CCSET_CS1_E0_01",
    "CCSET_CS2_E0_01",
    "SELECT_DUAL_BEFORE_PON",
    "PON_04",
    "SELECT_DUAL_BEFORE_POF",
    "POF_02_00",
    "SELECT_DUAL_BEFORE_POST_PSR",
    "PSR_00_4F6E",
]


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base._identity(value, "manifest")  # noqa: SLF001
    exact = {
        "actions": [ACTION],
        "classification": pack.CLASSIFICATION,
        "nvs": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 2,
            "missing_key_is_fresh_only": True,
            "nonterminal_phase_on_boot": "FAULT_NO_RESUME_NO_RETRY",
            "v1_namespace_and_key_must_not_be_erased": True,
        },
        "qualification": {
            "reset_count": 5,
            "reset_before_each_revision_sample": True,
            "final_posture_reset": True,
            "single_variable_change": "PER_SAMPLE_RESET_ONLY",
            "exact_historical_transaction_reproduction": False,
            "legacy_mosi_high_before_reset_restored": False,
            "legacy_post_reset_tail_2us_restored": False,
            "segmented_cs_framing_changed": False,
            "cs1_revision_reads": 2,
            "cs2_revision_reads": 2,
            "expected_revision_bytes": [1, 1, 4],
            "all_four_samples_exact_required": True,
            "same_boot_required": True,
            "qualified_busy_level": 1,
            "qualified_busy_stable_ms": 50,
            "zero_revision_result": (
                "STOP_BEFORE_PON_AND_DEFER_LEGACY_TRANSACTION_TO_V3"
            ),
            "qualified_gpio": {
                "rst": 1,
                "cs1": 1,
                "cs2": 1,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        },
        "probe": {
            "spi_hz": pack.PROBE_SPI_HZ,
            "exactly_one_pon": True,
            "exactly_one_pof": True,
            "pon_count": 1,
            "pof_count": 1,
            "drf_count": 0,
            "dtm_bytes": 0,
            "lut_bytes": 0,
            "ptlw_writes": 0,
            "command_0x86_count": 0,
            "visible_refresh_requests": 0,
            "failure_cleanup_matrix": pack.FAILURE_CLEANUP_MATRIX,
            "post_pof": [
                "DELAY_6000MS",
                "PSR_4F6E",
                "WAIT_IDLE",
                "DELAY_1000MS",
                "PINS_LOW",
            ],
        },
        "forbidden_commands": list(pack.FORBIDDEN_COMMANDS),
        "safety": {
            "startup_action": False,
            "automatic_execute": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "action_count": 1,
        "one_driver_call_per_action": True,
        "probe_sequence": list(pack.PROBE_SEQUENCE),
        "pon_count": 1,
        "pof_count": 1,
        "drf_count": 0,
        "dtm_bytes": 0,
        "lut_bytes": 0,
        "ptlw_writes": 0,
        "visible_refresh_requests": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.QualifierError(f"device V2 manifest {key} differs")
    if value.get("allowed_command_payload_sequence") != ALLOWED_COMMAND_PAYLOAD_SEQUENCE:
        raise base.QualifierError("device V2 allowed command/payload sequence differs")


def _validate_readiness(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise base.QualifierError("qualified V2 readiness evidence is missing")
    exact = {
        "valid": True,
        "qualified": True,
        "final_busy": 1,
        "final_gpio": {
            "rst": 1,
            "cs1": 1,
            "cs2": 1,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "final_high_stable_ms": 50,
        "reset_count": 5,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "failure_stage": "none",
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.QualifierError(f"qualified V2 readiness {key} differs")
    for controller in ("cs1", "cs2"):
        samples = value.get(controller)
        if not isinstance(samples, Mapping):
            raise base.QualifierError(f"qualified V2 readiness {controller} is missing")
        if samples.get("stable") is not True or samples.get("nontrivial") is not True:
            raise base.QualifierError(
                f"qualified V2 readiness {controller} classification differs"
            )
        for sample_name in ("sample1", "sample2"):
            sample = samples.get(sample_name)
            if (
                not isinstance(sample, Mapping)
                or sample.get("idle") is not True
                or sample.get("bytes") != [1, 1, 4]
            ):
                raise base.QualifierError(
                    f"qualified V2 readiness {controller} {sample_name} is not 010104"
                )


_READINESS_FAILURE_STAGES = frozenset(
    {
        "cs2_disabled",
        "revision_session_prepare_failed",
        "cs1_sample1_reset_busy",
        "cs1_sample2_reset_busy",
        "cs2_sample1_reset_busy",
        "cs2_sample2_reset_busy",
        "cs1_revision_unstable",
        "cs2_revision_unstable",
        "cs1_revision_trivial",
        "cs2_revision_trivial",
        "cs1_revision_not_010104",
        "cs2_revision_not_010104",
        "final_reset_busy_not_idle_high",
        "busy_or_gpio_posture_not_qualified",
    }
)


def _validate_fault_revision_sample(value: Any, *, label: str) -> None:
    if not isinstance(value, Mapping) or not isinstance(value.get("idle"), bool):
        raise base.QualifierError(f"qualification-fault {label} sample is malformed")
    raw = value.get("bytes")
    if (
        not isinstance(raw, list)
        or len(raw) != 3
        or any(not isinstance(item, int) or isinstance(item, bool) or not 0 <= item <= 255 for item in raw)
    ):
        raise base.QualifierError(f"qualification-fault {label} bytes are malformed")


def _validate_qualification_fault_status(
    value: Mapping[str, Any], *, boot_nonce: str
) -> None:
    base._identity(value, "status")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "state": "fault_locked",
        "phase": 6,
        "phase_name": "FAULT",
        "next_ordinal": 1,
        "campaign_complete": False,
        "same_boot_qualified": False,
        "qualification_nonce": None,
        "qualified_pin_posture": False,
        "qualify_pending": False,
        "probe_pending": False,
        "qualify_request_count": 1,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "qualifier_call_count": 1,
        "probe_call_count": 0,
        "cursor_raw": 6,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
        "persistent_key_present": True,
        "qualification_consumed": True,
        "qualification_valid": False,
        "total_driver_call_count": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.QualifierError(f"qualification-fault V2 status {key} differs")
    gpio = value.get("gpio")
    if not isinstance(gpio, Mapping) or any(
        gpio.get(pin) != 0 for pin in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        raise base.QualifierError("qualification-fault V2 GPIO is not safely LOW")
    if gpio.get("busy") not in (0, 1):
        raise base.QualifierError("qualification-fault V2 BUSY is malformed")


def _validate_qualification_fault_report(
    value: Mapping[str, Any], *, boot_nonce: str
) -> None:
    base._identity(value, "report")  # noqa: SLF001
    exact = {
        "valid": True,
        "boot_nonce": boot_nonce,
        "terminal_state": "FAULT",
        "result": False,
        "error": "readiness_qualification_failed",
        "qualification_nonce": None,
        "phase": 6,
        "phase_name": "FAULT",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.QualifierError(f"qualification-fault V2 report {key} differs")
    if value.get("driver") is not None or value.get("driver_called") not in (None, False):
        raise base.QualifierError("qualification-fault V2 unexpectedly has driver evidence")

    readiness = value.get("readiness")
    if not isinstance(readiness, Mapping):
        raise base.QualifierError("qualification-fault V2 readiness is missing")
    failure_stage = readiness.get("failure_stage")
    if failure_stage not in _READINESS_FAILURE_STAGES:
        raise base.QualifierError("qualification-fault V2 failure stage is not allowed")
    if readiness.get("valid") is not True or readiness.get("qualified") is not False:
        raise base.QualifierError("qualification-fault V2 readiness result differs")
    if readiness.get("entry_busy") not in (0, 1):
        raise base.QualifierError("qualification-fault V2 entry BUSY is malformed")
    if readiness.get("final_busy") not in (0, 1):
        raise base.QualifierError("qualification-fault V2 final BUSY is malformed")
    if (
        not isinstance(readiness.get("final_high_stable_ms"), int)
        or isinstance(readiness.get("final_high_stable_ms"), bool)
        or not 0 <= readiness["final_high_stable_ms"] <= 50
    ):
        raise base.QualifierError("qualification-fault V2 stable-high duration is malformed")
    final_gpio = readiness.get("final_gpio")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(pin) != 0
        for pin in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        raise base.QualifierError("qualification-fault V2 readiness GPIO is not safely LOW")

    reset_count = readiness.get("reset_count")
    revision_count = readiness.get("revision_read_count")
    if (
        not isinstance(reset_count, int)
        or isinstance(reset_count, bool)
        or not 0 <= reset_count <= 5
        or not isinstance(revision_count, int)
        or isinstance(revision_count, bool)
        or not 0 <= revision_count <= 4
    ):
        raise base.QualifierError("qualification-fault V2 readiness counts are malformed")
    trace = readiness.get("revision_command_trace")
    if trace != [0x70] * revision_count + [0] * (4 - revision_count):
        raise base.QualifierError("qualification-fault V2 revision trace differs")
    expected_progress = {
        "cs2_disabled": (0, 0),
        "revision_session_prepare_failed": (0, 0),
        "cs1_sample1_reset_busy": (1, 0),
        "cs1_sample2_reset_busy": (2, 1),
        "cs2_sample1_reset_busy": (3, 2),
        "cs2_sample2_reset_busy": (4, 3),
    }
    if failure_stage in expected_progress:
        if (reset_count, revision_count) != expected_progress[failure_stage]:
            raise base.QualifierError("qualification-fault V2 progress differs")
    elif (reset_count, revision_count) != (5, 4):
        raise base.QualifierError("qualification-fault V2 completed-read counts differ")
    total_ms = readiness.get("total_ms")
    if (
        not isinstance(total_ms, int)
        or isinstance(total_ms, bool)
        or total_ms < 0
    ):
        raise base.QualifierError("qualification-fault V2 readiness duration is malformed")

    controllers: dict[str, Mapping[str, Any]] = {}
    for controller in ("cs1", "cs2"):
        samples = readiness.get(controller)
        if not isinstance(samples, Mapping):
            raise base.QualifierError(
                f"qualification-fault V2 {controller} evidence is missing"
            )
        if not isinstance(samples.get("stable"), bool) or not isinstance(
            samples.get("nontrivial"), bool
        ) or not isinstance(samples.get("exact_010104"), bool):
            raise base.QualifierError(
                f"qualification-fault V2 {controller} classification is malformed"
            )
        for sample_name in ("sample1", "sample2"):
            _validate_fault_revision_sample(
                samples.get(sample_name), label=f"{controller} {sample_name}"
            )
        controllers[controller] = samples
    if not isinstance(readiness.get("all_revision_samples_exact_010104"), bool):
        raise base.QualifierError("qualification-fault V2 aggregate revision flag is malformed")

    ordered_samples = [
        controllers["cs1"]["sample1"],
        controllers["cs1"]["sample2"],
        controllers["cs2"]["sample1"],
        controllers["cs2"]["sample2"],
    ]
    for index, sample in enumerate(ordered_samples):
        if index < revision_count:
            if sample["idle"] is not True:
                raise base.QualifierError(
                    "qualification-fault V2 completed sample is not idle"
                )
        elif sample != {"idle": False, "bytes": [0, 0, 0]}:
            raise base.QualifierError(
                "qualification-fault V2 unread sample is not zero initialized"
            )

    # When all four reads completed, bind the device's classification fields
    # to the raw samples.  For an early reset/BUSY failure the fields remain
    # their zero-initialized false values and are checked as such.
    if revision_count == 4:
        for controller, samples in controllers.items():
            raw1 = samples["sample1"]
            raw2 = samples["sample2"]
            stable = (
                raw1["idle"] is True
                and raw2["idle"] is True
                and raw1["bytes"] == raw2["bytes"]
            )
            raw = raw2["bytes"]
            nontrivial = raw not in ([0, 0, 0], [255, 255, 255])
            exact = raw1["bytes"] == [1, 1, 4] and raw2["bytes"] == [1, 1, 4]
            if (
                samples["stable"] is not stable
                or samples["nontrivial"] is not nontrivial
                or samples["exact_010104"] is not exact
            ):
                raise base.QualifierError(
                    f"qualification-fault V2 {controller} classification differs"
                )
        aggregate = all(
            controllers[name]["exact_010104"] for name in ("cs1", "cs2")
        )
        if readiness["all_revision_samples_exact_010104"] is not aggregate:
            raise base.QualifierError(
                "qualification-fault V2 aggregate revision flag differs"
            )
        if controllers["cs1"]["stable"] is not True:
            expected_stage = "cs1_revision_unstable"
        elif controllers["cs2"]["stable"] is not True:
            expected_stage = "cs2_revision_unstable"
        elif controllers["cs1"]["nontrivial"] is not True:
            expected_stage = "cs1_revision_trivial"
        elif controllers["cs2"]["nontrivial"] is not True:
            expected_stage = "cs2_revision_trivial"
        elif controllers["cs1"]["exact_010104"] is not True:
            expected_stage = "cs1_revision_not_010104"
        elif controllers["cs2"]["exact_010104"] is not True:
            expected_stage = "cs2_revision_not_010104"
        else:
            expected_stage = failure_stage
            if failure_stage not in {
                "final_reset_busy_not_idle_high",
                "busy_or_gpio_posture_not_qualified",
            }:
                raise base.QualifierError(
                    "qualification-fault V2 post-read failure stage differs"
                )
        if failure_stage != expected_stage:
            raise base.QualifierError(
                "qualification-fault V2 failure classification differs"
            )
    elif any(
        controllers[name][key] is not False
        for name in ("cs1", "cs2")
        for key in ("stable", "nontrivial", "exact_010104")
    ) or readiness["all_revision_samples_exact_010104"] is not False:
        raise base.QualifierError("qualification-fault V2 partial classification differs")

    probe = value.get("probe")
    if not isinstance(probe, Mapping):
        raise base.QualifierError("qualification-fault V2 zero-probe evidence is missing")
    zero_false = (
        "valid",
        "running",
        "sequence_ok",
        "wait_timeout",
        "busy_assertion_missing",
        "pre_command_idle_failure",
        "pon_busy_seen",
        "pof_busy_seen",
        "pon_command_sent",
        "pof_command_sent",
        "post_psr_command_sent",
        "pon_idle_completed",
        "pof_idle_completed",
    )
    if any(probe.get(key) is not False for key in zero_false):
        raise base.QualifierError("qualification fault unexpectedly entered the V2 probe")
    if any(
        probe.get(key) != wanted
        for key, wanted in {
            "operation_id": 0,
            "spi_hz": 0,
            "total_ms": 0,
            "command_trace": [],
            "wire_event_count": 0,
            "wire_fnv1a": 0x811C9DC5,
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "failure_stage": "none",
            "pon_ms": 0,
            "pof_ms": 0,
            "post_psr_ms": 0,
            "pon_assertion_latency_ms": 0,
            "pof_assertion_latency_ms": 0,
            "pon_gate_entry": 0xFF,
            "pof_gate_entry": 0xFF,
        }.items()
    ):
        raise base.QualifierError("qualification-fault V2 zero-probe trace differs")
    if probe.get("command_counts") != {
        "pon": 0,
        "pof": 0,
        "drf": 0,
        "dtm": 0,
        "lut": 0,
        "ptlw": 0,
        "command_0x86": 0,
        "visible_refresh_requests": 0,
    }:
        raise base.QualifierError("qualification-fault V2 command counts are not all zero")
    if probe.get("forbidden_commands") != {
        "drf": False,
        "dtm": False,
        "lut": False,
        "ptlw": False,
        "command_0x86": False,
    }:
        raise base.QualifierError("qualification-fault V2 forbidden-command evidence differs")
    safe_finish = probe.get("safe_finish")
    if not isinstance(safe_finish, Mapping) or safe_finish != {
        "busy_before_pins_low": 0xFF,
        "busy_after_pins_low": 0xFF,
        "busy_after_5ms": 0xFF,
        "final_gpio": {
            "busy": 0xFF,
            "rst": 0xFF,
            "cs1": 0xFF,
            "cs2": 0xFF,
            "sck": 0xFF,
            "dc": 0xFF,
            "mosi": 0xFF,
        },
    }:
        raise base.QualifierError("qualification-fault V2 zero-probe finish differs")


base.pack = pack
base.REPORT = REPORT
base.ACTION = ACTION
base.KIND_PREFIX = KIND_PREFIX
base.ENDPOINT_BASE = ENDPOINT_BASE
base.ENDPOINTS = ENDPOINTS
base.QUALIFY_INTENT = QUALIFY_INTENT
base.ARM_INTENT = ARM_INTENT
base.EXECUTE_INTENT = EXECUTE_INTENT
base.BUILD_DIR = BUILD_DIR
base.FIRMWARE_BIN = FIRMWARE_BIN
base.FIRMWARE_ELF = FIRMWARE_ELF
base.FIRMWARE_BIN_BYTES = FIRMWARE_BIN_BYTES
base.FIRMWARE_BIN_SHA256 = FIRMWARE_BIN_SHA256
base.FIRMWARE_ELF_BYTES = FIRMWARE_ELF_BYTES
base.FIRMWARE_ELF_SHA256 = FIRMWARE_ELF_SHA256
base.DEFAULT_CLAIMS = DEFAULT_CLAIMS
base.DEFAULT_OUTPUT = DEFAULT_OUTPUT
base._validate_manifest = _validate_manifest  # noqa: SLF001
base._validate_readiness = _validate_readiness  # noqa: SLF001
base._validate_qualification_fault_status = (  # noqa: SLF001
    _validate_qualification_fault_status
)
base._validate_qualification_fault_report = (  # noqa: SLF001
    _validate_qualification_fault_report
)

QualifierError = base.QualifierError
Requester = base.Requester


def artifact_binding_status() -> dict[str, dict[str, Any]]:
    return base.artifact_binding_status()


def dry_validate() -> dict[str, Any]:
    return base.dry_validate()


def describe() -> dict[str, Any]:
    value = base.describe()
    value["flow"] = [
        "J2_OFF_FOUR_GET_DIAGNOSTIC",
        "LIVE_FOUR_GET_PREQUALIFICATION",
        "FOUR_PER_SAMPLE_RESET_EXACT_010104_REVISION_READS",
        "FINAL_RESET_AND_BUSY_HIGH_50MS_POSTURE",
        "LIVE_FOUR_GET_QUALIFIED_BUSY1_RECHECK",
        "PERMANENT_LOCAL_CLAIM",
        "ONE_ARM",
        "ONE_EXECUTE_PON_THEN_POF",
    ]
    value["read_only_fault_salvage"].update(
        {
            "scope": "V2_READINESS_QUALIFICATION_FAULT_ONLY",
            "requires_j2_off": True,
            "allowed_failure_stages": sorted(_READINESS_FAILURE_STAGES),
            "raw_four_gets_preserved": True,
            "raw_revision_samples_preserved": True,
            "output_create_mode": "O_EXCL",
        }
    )
    value["residual_differences_from_historical_helper"] = deepcopy(
        REPORT["contract"]["residual_differences_from_historical_helper"]
    )
    return value


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = base._http_request,  # noqa: SLF001
) -> dict[str, Any]:
    return base.diagnose_j2_off(
        base_url,
        output=output,
        confirm_j2_off=confirm_j2_off,
        requester=requester,
    )


def salvage_fault(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = base._http_request,  # noqa: SLF001
) -> dict[str, Any]:
    """Seal one V2 qualification-fault receipt using exactly four GETs."""

    if confirm_j2_off is not True:
        raise QualifierError("fault salvage requires explicit J2-OFF confirmation")
    base._require_artifact_binding()  # noqa: SLF001
    output = Path(output)
    if output.exists():
        raise QualifierError(f"refusing to overwrite final evidence {output}")
    attempt_file = Path(claims) / f"{ACTION['action_id']}.qualification-attempt.json"
    claim_file = Path(claims) / f"{ACTION['action_id']}.json"
    reservation_file = Path(str(output) + ".reserve")
    if claim_file.exists():
        raise QualifierError("qualification-fault salvage requires no permanent ARM claim")
    attempt, attempt_sha256 = base._load_sealed(  # noqa: SLF001
        attempt_file, "qualification attempt"
    )
    reservation, reservation_sha256 = base._load_sealed(  # noqa: SLF001
        reservation_file, "output reservation"
    )
    if (
        attempt.get("kind") != f"{KIND_PREFIX}-qualification-attempt"
        or attempt.get("action") != ACTION
        or attempt.get("firmware_sha256") != base.FIRMWARE_BIN_SHA256
        or attempt.get("state") != "reserved_before_qualify_post"
        or attempt.get("no_automatic_retry") is not True
        or attempt.get("initial_busy") not in (0, 1)
    ):
        raise QualifierError("qualification attempt binding differs")
    boot_nonce = base._nonce(attempt.get("boot_nonce"), "attempt boot nonce")  # noqa: SLF001
    if (
        reservation.get("kind") != f"{KIND_PREFIX}-output-reservation"
        or reservation.get("boot_nonce") != boot_nonce
        or reservation.get("final_output") != str(output.resolve())
    ):
        raise QualifierError("output reservation binding differs")

    transcript: list[dict[str, Any]] = []
    _, _, status, report = base._four_gets(  # noqa: SLF001
        base._origin(base_url), requester, transcript  # noqa: SLF001
    )
    _validate_qualification_fault_status(status, boot_nonce=boot_nonce)
    _validate_qualification_fault_report(report, boot_nonce=boot_nonce)
    readiness = report["readiness"]
    probe = report["probe"]
    evidence = base._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-qualification-fault-salvage",
            "created_at": base._now(),  # noqa: SLF001
            "firmware_sha256": base.FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(ACTION),
            "qualification_attempt_file": str(attempt_file.resolve()),
            "qualification_attempt_file_sha256": attempt_sha256,
            "qualification_attempt_integrity": deepcopy(attempt["integrity"]),
            "output_reservation_file": str(reservation_file.resolve()),
            "output_reservation_file_sha256": reservation_sha256,
            "output_reservation_integrity": deepcopy(reservation["integrity"]),
            "reserved_output_closed_by_o_excl": True,
            "permanent_claim_file": str(claim_file.resolve()),
            "permanent_claim_present": False,
            "claim_semantics": "NOT_CREATED_BECAUSE_QUALIFICATION_FAILED_BEFORE_ARM",
            "status": deepcopy(dict(status)),
            "terminal_report": deepcopy(dict(report)),
            "raw_readiness_failure": {
                "failure_stage": readiness["failure_stage"],
                "entry_busy": readiness["entry_busy"],
                "final_busy": readiness["final_busy"],
                "reset_count": readiness["reset_count"],
                "revision_read_count": readiness["revision_read_count"],
                "revision_command_trace": deepcopy(
                    readiness["revision_command_trace"]
                ),
                "cs1": deepcopy(readiness["cs1"]),
                "cs2": deepcopy(readiness["cs2"]),
            },
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "outcome": "qualification_fault_salvaged_read_only",
            "attempt_state": "PERMANENTLY_CONSUMED_DO_NOT_RETRY_V2",
            "probe_command_counts": deepcopy(probe["command_counts"]),
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "hardware_mutation_requested": False,
        }
    )
    base._write_new(output, evidence)  # noqa: SLF001
    return evidence


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    confirm_j2_on: bool = False,
    requester: Requester = base._http_request,  # noqa: SLF001
    poll_seconds: float = 2.0,
    poll_count: int = base.DEFAULT_POLL_COUNT,
) -> dict[str, Any]:
    return base.run_once(
        base_url,
        claims=claims,
        output=output,
        confirm_j2_on=confirm_j2_on,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnostic = sub.add_parser("diagnose-j2-off")
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, required=True)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--confirm-j2-off", action="store_true", required=True)
    salvage.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=2.0)
    run.add_argument("--poll-count", type=int, default=base.DEFAULT_POLL_COUNT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "salvage-fault":
            value = salvage_fault(
                args.base_url,
                claims=args.claims,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                claims=args.claims,
                output=args.output,
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except QualifierError as error:
        print(f"PON/POF V2 qualifier error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
