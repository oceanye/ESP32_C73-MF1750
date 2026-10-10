from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_h3_matched_control_compiled_identity as compiled
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical
from tools import mf1750_ec5_h3_matched_control_release as release
from tools import mf1750_ec5_h3_c_first_treatment_once as c_first_treatment
from tools import mf1750_ec5_h3_matched_pair_evidence as pair
from tools import mf1750_ec5_runtime_lut_contract as h3_contract
from tools import mf1750_ec5_runtime_lut_physical_once as h3_physical
from tools import mf1750_ec5_runtime_lut_release as h3_release


REPO_ROOT = Path(__file__).resolve().parents[1]
TREATMENT_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V1 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V1"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V2 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V2"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V3 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V3"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V4 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V4"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V5 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V5"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V6 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V6"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V7 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V7"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V8 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260812_V8"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V9 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V9"
    / "WF20_25-release.json"
)
MATCHED_RELEASE_V10 = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10"
    / "WF20_25-release.json"
)
EXPECTED_CURRENT_RELEASE_ID = (
    "1cf8307c8906fa3057509c7a4a15bd79156751aa6b27c3f158435fbaa1049e36"
)
EXPECTED_CURRENT_CANONICAL_SHA256 = (
    "5616bd495c9faf0983c3d361d5d3bea57837c5f5d8a498805cca940ca595b00e"
)
EXPECTED_CURRENT_HOST_BUNDLE_SHA256 = (
    "888ab013b6d3bb4ee8b2b2a87fdc348cb5ac2ce9265396ea5a39c70179416a3c"
)
EXPECTED_CURRENT_C_FIRST_SOURCE_SHA256 = (
    "a3bf2fb5d0cf18632e74deed51de322daa88c100e33e2bb54fd0cd6905ae3287"
)


def _real_image(role: str) -> tuple[Path, Path, Path]:
    if role == contract.ROLE_CONTROL:
        root = (
            REPO_ROOT
            / ".pio"
            / "build-h3-matched-no-r20-r21-wf20-25"
            / "ec5_h3_matched_no_r20_r21_wf20_25"
        )
        source = REPO_ROOT / "src" / "ec5_h3_matched_control_main.cpp"
    else:
        root = (
            REPO_ROOT
            / ".pio"
            / "build-h3-matched-control-otp-white-wf20-25"
            / "ec5_h3_matched_control_otp_white_wf20_25"
        )
        source = REPO_ROOT / "src" / "ec5_h3_matched_control_otp_white_main.cpp"
    return root / "firmware.elf", root / "firmware.bin", source


def _materialize_release() -> Mapping[str, Any]:
    control = _real_image(contract.ROLE_CONTROL)
    recovery = _real_image(contract.ROLE_WHITE)
    return release.materialize_release(
        treatment_release_file=TREATMENT_RELEASE,
        control_elf=control[0],
        control_binary=control[1],
        control_source=control[2],
        recovery_elf=recovery[0],
        recovery_binary=recovery[1],
        recovery_source=recovery[2],
    )


@pytest.fixture(scope="module")
def release_root() -> Mapping[str, Any]:
    return _materialize_release()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contract.canonical_json_bytes(value) + b"\n")


def _write_synthetic_image(root: Path, role: str) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    required = compiled._required_ascii(contract.PROFILE_ID, role)  # noqa: SLF001
    source_payload = ("\n".join(required) + "\n").encode("ascii")
    source = root / f"{role}.cpp"
    source.write_bytes(source_payload)
    elf_payload = b"\x7fELF\x00" + b"\x00".join(
        item.encode("ascii") for item in required
    )
    elf = root / f"{role}.elf"
    elf.write_bytes(elf_payload)
    binary_payload = bytearray(256)
    binary_payload[0] = 0xE9
    binary_payload[32:36] = bytes.fromhex("3254cdab")
    binary_payload[176:208] = hashlib.sha256(elf_payload).digest()
    binary = root / f"{role}.bin"
    binary.write_bytes(binary_payload)
    return elf, binary, source


class FakeDevice:
    def __init__(self, context: physical.ReleaseContext, ordinal: int) -> None:
        self.context = context
        self.ordinal = ordinal
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.executed = False
        self.boot_nonce = "0123456789abcdef"
        self.arm_nonce = "fedcba9876543210"

    @property
    def action(self) -> Mapping[str, Any]:
        return self.context.action(self.ordinal)

    @property
    def binding(self) -> Mapping[str, Any]:
        return self.context.binding(self.ordinal)

    def _identity(self) -> dict[str, Any]:
        return physical._identity_expected(self.context, self.ordinal)  # noqa: SLF001

    def _version(self) -> dict[str, Any]:
        policy = self.action["temperature_policy"]
        interval = (
            self.context.root["profile_contract"]["vendor_filename_numeric_tokens"]
            if self.ordinal == 1
            else policy["allowed_record_range_c"]
        )
        profile: dict[str, Any] = {
            "profile_id": self.context.profile_id,
            "compiled_profile_count": 1,
            "auto_selected": False,
            "apparent_temperature_min_c": int(interval[0]),
            "apparent_temperature_max_c": int(interval[1]),
        }
        if self.ordinal == 1:
            electrical = contract.profile_row()["requested_electrical_metadata"]
            profile.update(
                {
                    "requested_gate_positive_mv": electrical["gate_positive_mv"],
                    "requested_gate_negative_mv": electrical["gate_negative_mv"],
                    "requested_full_source_positive_mv": electrical[
                        "full_source_positive_mv"
                    ],
                    "requested_full_source_negative_mv": electrical[
                        "full_source_negative_mv"
                    ],
                    "requested_vsh_lv_mv": electrical["intermediate_source_mv"][
                        "vsh_lv"
                    ],
                    "requested_vsl_lv_mv": electrical["intermediate_source_mv"][
                        "vsl_lv"
                    ],
                    "requested_vsh_lv2_mv": electrical["intermediate_source_mv"][
                        "vsh_lv2"
                    ],
                    "requested_vsl_lv2_mv": electrical["intermediate_source_mv"][
                        "vsl_lv2"
                    ],
                    "requested_frame_rate_hz": electrical["frame_rate_hz"],
                    "panel_or_fpl_limits_proven": False,
                    "electrical_values_source": "matched_wf20_25_constants",
                    "r20_command_writes": 0,
                    "r21_command_writes": 0,
                    "r20_payload_bytes": 0,
                    "r21_payload_bytes": 0,
                    "control_design": contract.CONTROL_DESIGN,
                    "strict_payload_only_control": False,
                    "time_matched_control": False,
                    "dummy_clocks_inserted": False,
                    "empty_r20_or_r21_commands_inserted": False,
                }
            )
        else:
            profile.update(
                {
                    "temperature_policy": (
                        "factory_otp_existing_observed_ceiling_not_vendor_band"
                    ),
                    "temperature_limit_is_safety_qualification": False,
                }
            )
        return {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-version",
            **self._identity(),
            "profile": profile,
            "action_count": 1,
            "startup_refresh": False,
            "raw_ingress": False,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
            "profile_switch": False,
        }

    def _manifest(self) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-manifest",
            **self._identity(),
            "actions": [
                {
                    "ordinal": self.ordinal,
                    "role": self.action["role"],
                    "descriptor_id": self.action["transaction_descriptor_sha256"],
                    "action_id": self.action["hardware_action_id"],
                    "frame_sha256": self.action["payload_identity"]["frame_sha256"],
                    "cs1_dtm_sha256": self.action["payload_identity"]["cs1_dtm_sha256"],
                    "cs2_dtm_sha256": self.action["payload_identity"]["cs2_dtm_sha256"],
                }
            ],
            "action_count": 1,
            "one_driver_call_per_action": True,
            "unproven_risks": [
                {"id": f"C{index}", "status": "unproven"} for index in range(1, 9)
            ],
        }
        for key in (
            "startup_refresh",
            "raw_frame_ingress",
            "raw_lut_ingress",
            "electrical_parameter_ingress",
            "timing_parameter_ingress",
            "retry",
            "automatic_chaining",
            "automatic_recovery",
            "profile_switch",
            "vcom_write",
            "vcom_sweep",
        ):
            value[key] = False
        if self.ordinal == 1:
            value.update(
                {
                    "r20_command_writes": 0,
                    "r21_command_writes": 0,
                    "r20_payload_bytes": 0,
                    "r21_payload_bytes": 0,
                    "control_design": contract.CONTROL_DESIGN,
                    "strict_payload_only_control": False,
                    "time_matched_control": False,
                    "dummy_clocks_inserted": False,
                    "empty_r20_or_r21_commands_inserted": False,
                    "per_controller_removed_spi_bytes_and_edges": 1505,
                    "per_controller_removed_cooperative_yields": 5,
                }
            )
        return value

    def _status(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-status",
            **self._identity(),
            "boot_nonce": self.boot_nonce,
            "profile_id": self.context.profile_id,
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "cursor_raw": self.ordinal,
            "next_ordinal": self.ordinal,
            "campaign_complete": False,
            "fixture_self_check_passed": True,
            "cursor_valid": True,
            "persistent_key_present": False,
            "execute_pending": False,
            "arm_request_count": 0,
            "execute_request_count": 0,
            "total_driver_call_count": 0,
            "gpio_initialized": True,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
            "busy": 1,
        }

    def _report(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-report",
            **self._identity(),
            "terminal_state": "COMPLETE" if self.executed else "NOT_EXECUTED",
            "result": self.executed,
            "driver_called": self.executed,
            "driver_call_count_for_action": 1 if self.executed else 0,
            "no_retry": True,
        }
        if self.executed:
            atlas_role = "atlas" if self.ordinal == 1 else "white"
            driver: dict[str, Any] = {
                "valid": True,
                "running": False,
                "sequence_ok": True,
                "wait_timeout": False,
                "busy_assertion_missing": False,
                "mapping_applied": True,
                "pon_busy_seen": True,
                "drf_busy_seen": True,
                "pof_busy_seen": True,
                "pre_command_idle_failure": False,
                "input_fnv1a": physical.atlas.FROZEN_IDENTITIES[atlas_role]["frame"][1],
                "cs1_dtm_fnv1a": physical.atlas.FROZEN_IDENTITIES[atlas_role]["cs1"][1],
                "cs2_dtm_fnv1a": physical.atlas.FROZEN_IDENTITIES[atlas_role]["cs2"][1],
                "busy_trace": {
                    "idle_level": 1,
                    "post_psr": {"pre_command_idle_ok": True, "wait_exit_level": 1},
                    "safe_finish": {"busy_after_pins_low": 1, "busy_after_5ms": 1},
                    "final_gpio": {
                        "busy": 1,
                        "rst": 0,
                        "cs": 0,
                        "cs2": 0,
                        "sck": 0,
                        "dc": 0,
                        "mosi": 0,
                    },
                },
            }
            if self.ordinal == 1:
                driver.update(
                    {
                        "matched_no_r20_r21_control": True,
                        "r20_command_writes": 0,
                        "r21_command_writes": 0,
                        "r20_payload_bytes": 0,
                        "r21_payload_bytes": 0,
                        "control_design": contract.CONTROL_DESIGN,
                        "strict_payload_only_control": False,
                        "time_matched_control": False,
                        "dummy_clocks_inserted": False,
                        "empty_r20_or_r21_commands_inserted": False,
                        "per_controller_removed_spi_bytes_and_edges": 1505,
                        "per_controller_removed_cooperative_yields": 5,
                    }
                )
            else:
                driver.update(
                    {
                        "factory_otp_white": True,
                        "matched_no_r20_r21_control": False,
                    }
                )
            value.update(
                {
                    "ordinal": self.ordinal,
                    "action_id": self.action["hardware_action_id"],
                    "driver": driver,
                }
            )
        return value

    def __call__(
        self, method: str, endpoint: str, headers: Mapping[str, str]
    ) -> physical.HttpResponse:
        self.calls.append((method, endpoint, dict(headers)))
        suffix = endpoint.rsplit("/", 1)[-1]
        if method == "GET":
            return physical.HttpResponse(
                200,
                {
                    "version": self._version,
                    "manifest": self._manifest,
                    "status": self._status,
                    "report": self._report,
                }[suffix](),
            )
        if suffix == "arm":
            return physical.HttpResponse(
                201,
                {
                    **self._identity(),
                    "accepted": True,
                    "armed": True,
                    "ordinal": self.ordinal,
                    "action_id": self.action["hardware_action_id"],
                    "boot_nonce": self.boot_nonce,
                    "arm_nonce": self.arm_nonce,
                },
            )
        assert suffix == "execute"
        self.executed = True
        return physical.HttpResponse(
            202,
            {
                **self._identity(),
                "accepted": True,
                "job_id": self.ordinal,
                "action_id": self.action["hardware_action_id"],
                "execute_consumed": True,
                "no_retry": True,
            },
        )


def _run_control_leg_inputs(
    tmp_path: Path, root: Mapping[str, Any]
) -> tuple[Path, Path, Path, Path, Path]:
    release_file = tmp_path / "matched-release.json"
    _write_json(release_file, root)
    context = physical.context_from_root(root)
    claims = tmp_path / "control-claims"
    files: list[Path] = []
    for ordinal, screen in (
        (1, physical.SCREEN_INITIAL),
        (2, physical.SCREEN_RECOVERY),
    ):
        device = FakeDevice(context, ordinal)
        diagnostic = physical.diagnose_j2_off(
            context,
            ordinal,
            operator_temperature_c="25.0",
            operator_screen_state=screen,
            operator_j2_state="OFF",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            requester=device,
        )
        diagnostic_file = tmp_path / f"control-diagnostic-{ordinal}.json"
        _write_json(diagnostic_file, diagnostic)
        authorization = physical.offline_authorization(
            context,
            ordinal,
            selected_profile_id=contract.PROFILE_ID,
            operator_temperature_c="25.0",
            control_acceptance=contract.CONTROL_ACCEPTANCE_PHRASE,
            initial_precondition=(
                contract.INITIAL_PRECONDITION_PHRASE if ordinal == 1 else ""
            ),
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            diagnostic=diagnostic,
            claim_registry=claims,
        )
        result = physical.run_once(
            context,
            ordinal,
            operator_temperature_c="25.0",
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=authorization["authorization_token"],
            diagnostic=diagnostic,
            requester=device,
            claim_registry=claims,
            poll_count=1,
            poll_interval_seconds=0,
            sleeper=lambda _: None,
        )
        result_file = tmp_path / f"control-result-{ordinal}.json"
        _write_json(result_file, result)
        files.extend((diagnostic_file, result_file))
    return release_file, files[0], files[1], files[2], files[3]


def _finalize_control_leg(
    tmp_path: Path, root: Mapping[str, Any]
) -> tuple[Path, Mapping[str, Any]]:
    release_file, c_diag, c_result, r_diag, r_result = _run_control_leg_inputs(
        tmp_path, root
    )
    leg = pair.finalize_control_leg(
        matched_release_file=release_file,
        control_diagnostic_file=c_diag,
        control_result_file=c_result,
        recovery_diagnostic_file=r_diag,
        recovery_result_file=r_result,
        control_observation=pair.CONTROL_OBSERVATION,
        recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
        electrical_observation=pair.ELECTRICAL_OBSERVATION,
        balance_observation=pair.BALANCE_OBSERVATION,
        j2_off_observation=pair.J2_OFF_OBSERVATION,
        finalization_phrase=contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
    )
    leg_file = tmp_path / "control-leg.json"
    _write_json(leg_file, leg)
    return leg_file, leg


def _make_h3_result(
    tmp_path: Path,
    h3_root: Mapping[str, Any],
    ordinal: int,
    *,
    outcome: str = "success",
) -> tuple[Path, Path]:
    context = h3_physical.context_from_root(h3_root)
    action = next(
        item
        for item in h3_root["profile_contract"]["actions"]
        if item["ordinal"] == ordinal
    )
    binding = context.binding(ordinal)
    boot_nonce = f"{ordinal}" * 16
    diagnostic = h3_physical._seal(  # noqa: SLF001
        {
            "schema_version": h3_physical.SCHEMA_VERSION,
            "kind": h3_physical.DIAGNOSTIC_KIND,
            "release_id": h3_root["release_id"],
            "profile_id": contract.PROFILE_ID,
            "ordinal": ordinal,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "firmware_binary_sha256": binding["firmware_binary_sha256"],
            "firmware_elf_sha256": binding["firmware_elf_sha256"],
            "transaction_descriptor_sha256": binding["transaction_descriptor_sha256"],
            "boot_nonce": boot_nonce,
            "operator_temperature_c": "25.0",
            "operator_j2_assertion": "OFF",
            "j2_is_device_measured": False,
            "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
            "operator_screen_state": (
                h3_physical.SCREEN_INITIAL
                if ordinal == 1
                else h3_physical.SCREEN_RECOVERY
            ),
            "get_requests": 4,
            "post_requests": 0,
            "claim_created": False,
            "device_mutation_performed": False,
            "visible_refreshes": 0,
        }
    )
    diagnostic_path = tmp_path / f"h3-diagnostic-{ordinal}.json"
    _write_json(diagnostic_path, diagnostic)
    claim = h3_physical._seal(  # noqa: SLF001
        {
            "schema_version": h3_physical.SCHEMA_VERSION,
            "kind": h3_physical.CLAIM_KIND,
            "release_id": h3_root["release_id"],
            "profile_id": contract.PROFILE_ID,
            "ordinal": ordinal,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "operator_temperature_c": "25.0",
            "authorization_sha256": "a" * 64,
            "diagnostic_canonical_sha256": diagnostic["integrity"]["canonical_sha256"],
            "state": "permanently_consumed_do_not_retry",
            "created_before_network": True,
        }
    )
    claim_path = (tmp_path / f"h3-claim-{ordinal}.json").resolve()
    _write_json(claim_path, claim)
    result = h3_physical._seal(  # noqa: SLF001
        {
            "schema_version": h3_physical.SCHEMA_VERSION,
            "kind": h3_physical.RESULT_KIND,
            "release_id": h3_root["release_id"],
            "profile_id": contract.PROFILE_ID,
            "ordinal": ordinal,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "operator_temperature_c": "25.0",
            "operator_j2_assertion": "ON",
            "j2_is_device_measured": False,
            "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
            "boot_nonce": boot_nonce,
            "claim_file": str(claim_path),
            "claim_file_sha256": hashlib.sha256(claim_path.read_bytes()).hexdigest(),
            "preflight_get_requests_after_claim": 4,
            "arm_posts": 1,
            "execute_posts": 1,
            "post_execute_settle_seconds": h3_physical.POST_EXECUTE_SETTLE_SECONDS,
            "terminal_report_get_requests": 1,
            "terminal_report_read_errors": 0,
            "visible_refreshes": 1,
            "outcome": outcome,
            "retry_allowed": False,
            "automatic_chaining_performed": False,
            "automatic_recovery_performed": False,
            "profile_switch_performed": False,
        }
    )
    path = tmp_path / f"h3-result-{ordinal}.json"
    _write_json(path, result)
    return diagnostic_path, path


def test_contract_is_c_first_independent_and_pins_exact_treatment_release() -> None:
    root = contract.validate_contract()
    h3 = h3_contract.validate_contract(contract.PROFILE_ID)
    actions = root["actions"]
    assert root["vendor_filename_numeric_tokens"] == [20, 25]
    assert root["temperature_filename_semantics_proven"] is False
    assert root["experimental_fixed_temperature_guard_c"] == [25.0, 25.0]
    assert root["temperature_compatibility_qualified"] is False
    assert actions[0]["temperature_policy"]["allowed_c"] == [25.0, 25.0]
    assert actions[0]["temperature_policy"]["vendor_filename_band_claim"] is False
    assert root["contract_id"] == (
        "25267914e74b249cc4bd1cc821437ea700a3c41a75140d82862c86357b3a63fe"
    )
    assert [
        stage["pair_ordinal"] for stage in root["c_first_pair_sequence"]["stages"]
    ] == [
        1,
        2,
        3,
        4,
    ]
    assert (
        root["c_first_pair_sequence"][
            "initial_clean_white_is_treatment_finalized_evidence"
        ]
        is False
    )
    assert root["pinned_treatment_reference"]["release_id"] == (
        contract.PINNED_TREATMENT_RELEASE_ID
    )
    assert {item["hardware_action_id"] for item in actions}.isdisjoint(
        item["hardware_action_id"] for item in h3["actions"]
    )
    assert {item["hardware_action_id"] for item in actions}.isdisjoint(
        contract.SUPERSEDED_V1_ACTION_IDS
    )
    assert {item["nvs_namespace"] for item in actions}.isdisjoint(
        contract.SUPERSEDED_V1_NVS_NAMESPACES
    )
    assert (
        actions[0]["temperature_policy"][
            "establishes_pair_temperature_for_later_treatment"
        ]
        is True
    )
    runner = root["runner_policy"]
    assert "claim_before_first_network_request" not in runner
    assert runner["diagnostic_get_requests_before_claim"] == 4
    assert runner["diagnostic_mutation_requests_before_claim"] == 0
    assert runner["claim_before_first_run_invocation_network_request"] is True


def test_compiled_identity_is_v2_and_rejects_r20_source(tmp_path: Path) -> None:
    image = _write_synthetic_image(tmp_path, contract.ROLE_CONTROL)
    validated = compiled.validate_image(
        contract.PROFILE_ID,
        contract.ROLE_CONTROL,
        elf_file=image[0],
        binary_file=image[1],
        transaction_source_file=image[2],
    )
    assert "TX_DESCRIPTOR_V2" in validated["compiled_descriptor_marker"]
    image[2].write_bytes(image[2].read_bytes() + b"send(0x20);\n")
    with pytest.raises(
        compiled.MatchedControlCompiledIdentityError, match="forbidden R20/R21"
    ):
        compiled.validate_image(
            contract.PROFILE_ID,
            contract.ROLE_CONTROL,
            elf_file=image[0],
            binary_file=image[1],
            transaction_source_file=image[2],
        )


def test_real_compiled_images_pin_exact_bin_elf_and_contract_id() -> None:
    expected = {
        contract.ROLE_CONTROL: {
            "elf": "27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41",
            "binary": "f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e",
        },
        contract.ROLE_WHITE: {
            "elf": "6aba1ecb5eb339494c20cf51c56137f61d5568a596f644a7862b951cb45ed147",
            "binary": "6ab18de07ffbf0ad56dbd6861957a42ea15c6cce9e435f790e74df1050cfa51d",
        },
    }
    contract_id = contract.profile_contract()["contract_id"]
    for role, hashes in expected.items():
        elf, binary, source = _real_image(role)
        validated = compiled.validate_image(
            contract.PROFILE_ID,
            role,
            elf_file=elf,
            binary_file=binary,
            transaction_source_file=source,
        )
        assert validated["firmware"]["elf"]["sha256"] == hashes["elf"]
        assert validated["firmware"]["binary"]["sha256"] == hashes["binary"]
        assert validated["firmware"]["binary_elf_link"]["exact_match"] is True
        assert contract_id.encode("ascii") in elf.read_bytes()


def test_release_binds_exact_treatment_and_leaves_live_gates_false(
    release_root: Mapping[str, Any],
) -> None:
    summary = release.validate_release(release_root)
    assert (
        summary["pinned_treatment_release_id"] == contract.PINNED_TREATMENT_RELEASE_ID
    )
    assert release_root["claims_created"] is False
    assert release_root["visible_refreshes"] == 0
    assert release_root["live_authorized"] is False
    assert "prior_finalized_evidence" not in release_root
    assert (
        release_root["live_authorization_prerequisites"][
            "initial_clean_white_is_treatment_finalized_evidence"
        ]
        is False
    )
    trace = release_root["compiled_treatment_control_trace_audit"]
    assert (
        trace["normalized_trace"]["strip_exact_four_upload_spans_equals_control"]
        is True
    )
    assert trace["causal_scope"]["T_equals_C_classification"] == (
        "NO_DETECTABLE_INCREMENTAL_EFFECT"
    )
    operator_layer = release_root["c_first_treatment_operator_layer"]
    assert operator_layer["source_bytes_bound_in_host_execution_bundle"] is True
    assert operator_layer["hard_gates_invocations_made_through_facade"] is True
    assert operator_layer["delegated_release_input"] == (
        "private_byte_identical_snapshot"
    )
    assert operator_layer["original_release_path_reopened_by_delegate"] is False
    assert operator_layer["post_validation_original_path_replacement_rejected"] is True
    assert operator_layer["snapshot_deep_validated_before_delegate"] is True
    assert (
        operator_layer["privileged_concurrent_snapshot_mutation_physically_prevented"]
        is False
    )
    assert operator_layer["legacy_generic_runner_physically_disabled"] is False
    assert operator_layer["final_pair_can_cryptographically_prove_facade_use"] is False


def test_materialized_v10_binds_current_sources_and_supersedes_v1_through_v9() -> None:
    assert c_first_treatment.__doc__ is not None
    assert c_first_treatment.__doc__.isascii()
    assert "V4" not in c_first_treatment.__doc__
    assert "V4" not in release.__doc__
    assert c_first_treatment._parser().format_help().isascii()  # noqa: SLF001
    root = release.load_release(MATCHED_RELEASE_V10)
    summary = release.validate_release(root)
    assert summary["release_id"] == EXPECTED_CURRENT_RELEASE_ID
    assert summary["canonical_sha256"] == EXPECTED_CURRENT_CANONICAL_SHA256
    assert (
        summary["host_execution_bundle_sha256"] == EXPECTED_CURRENT_HOST_BUNDLE_SHA256
    )
    sources = {
        item["relative_path"]: item["sha256"]
        for item in root["host_execution_bundle"]["files"]
    }
    assert sources["tools/mf1750_ec5_h3_matched_pair_evidence.py"] == (
        "5a0b3378f8b9f0cd6c373b806fec6e5df1523435c9e825fac1d05ca290455dc3"
    )
    assert sources["tools/mf1750_ec5_h3_c_first_treatment_once.py"] == (
        EXPECTED_CURRENT_C_FIRST_SOURCE_SHA256
    )
    assert root["pinned_treatment_release"]["release_id"] == (
        contract.PINNED_TREATMENT_RELEASE_ID
    )
    for superseded in (
        MATCHED_RELEASE_V1,
        MATCHED_RELEASE_V2,
        MATCHED_RELEASE_V3,
        MATCHED_RELEASE_V4,
        MATCHED_RELEASE_V5,
        MATCHED_RELEASE_V6,
        MATCHED_RELEASE_V7,
    ):
        with pytest.raises(release.MatchedControlReleaseError, match="host execution"):
            release.load_release(superseded)
    with pytest.raises(
        release.MatchedControlReleaseError,
        match="deterministic deep reconstruction",
    ):
        release.load_release(MATCHED_RELEASE_V8)
    with pytest.raises(
        release.MatchedControlReleaseError,
        match="deterministic deep reconstruction",
    ):
        release.load_release(MATCHED_RELEASE_V9)


def test_release_rejects_nonexact_treatment_file(tmp_path: Path) -> None:
    altered = tmp_path / "altered-treatment.json"
    altered.write_bytes(TREATMENT_RELEASE.read_bytes() + b" ")
    control = _real_image(contract.ROLE_CONTROL)
    recovery = _real_image(contract.ROLE_WHITE)
    with pytest.raises(release.MatchedControlReleaseError):
        release.materialize_release(
            treatment_release_file=altered,
            control_elf=control[0],
            control_binary=control[1],
            control_source=control[2],
            recovery_elf=recovery[0],
            recovery_binary=recovery[1],
            recovery_source=recovery[2],
        )


def test_control_authorization_requires_live_initial_phrase_but_no_prior_result(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    context = physical.context_from_root(release_root)
    device = FakeDevice(context, 1)
    diagnostic = physical.diagnose_j2_off(
        context,
        1,
        operator_temperature_c="25.0",
        operator_screen_state=physical.SCREEN_INITIAL,
        operator_j2_state="OFF",
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        requester=device,
    )
    assert diagnostic["initial_clean_white_is_treatment_finalized_evidence"] is False
    assert "prior_evidence_id" not in diagnostic
    with pytest.raises(physical.MatchedControlPhysicalError, match="initial C-first"):
        physical.offline_authorization(
            context,
            1,
            selected_profile_id=contract.PROFILE_ID,
            operator_temperature_c="25.0",
            control_acceptance=contract.CONTROL_ACCEPTANCE_PHRASE,
            initial_precondition="",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            diagnostic=diagnostic,
            claim_registry=tmp_path / "claims",
        )
    token = physical.offline_authorization(
        context,
        1,
        selected_profile_id=contract.PROFILE_ID,
        operator_temperature_c="25.0",
        control_acceptance=contract.CONTROL_ACCEPTANCE_PHRASE,
        initial_precondition=contract.INITIAL_PRECONDITION_PHRASE,
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        diagnostic=diagnostic,
        claim_registry=tmp_path / "claims",
    )
    assert token["claims_created"] is False
    assert token["network_requests"] == 0
    assert token["treatment_release_id"] == contract.PINNED_TREATMENT_RELEASE_ID
    assert not (tmp_path / "claims").exists()


def test_control_recovery_is_independent_containment_and_no_autochain(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    _, _, control_result, _, recovery_result = _run_control_leg_inputs(
        tmp_path, release_root
    )
    control_value = pair._read_json(control_result, label="control result")[2]  # noqa: SLF001
    recovery_value = pair._read_json(  # noqa: SLF001
        recovery_result, label="recovery result"
    )[2]
    assert control_value["claim_file"] != recovery_value["claim_file"]
    assert control_value["automatic_chaining_performed"] is False
    assert recovery_value["automatic_recovery_performed"] is False
    assert control_value["hardware_action_id"] != recovery_value["hardware_action_id"]


def test_control_leg_and_temperature_gate_require_both_success_results(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    release_file, c_diag, c_result, r_diag, r_result = _run_control_leg_inputs(
        tmp_path, release_root
    )
    broken = dict(pair._read_json(r_result, label="recovery result")[2])  # noqa: SLF001
    broken["outcome"] = "unknown"
    broken = physical._seal(  # noqa: SLF001
        {key: value for key, value in broken.items() if key != "integrity"}
    )
    broken_file = tmp_path / "broken-recovery.json"
    _write_json(broken_file, broken)
    with pytest.raises(pair.MatchedPairEvidenceError, match="outcome"):
        pair.finalize_control_leg(
            matched_release_file=release_file,
            control_diagnostic_file=c_diag,
            control_result_file=c_result,
            recovery_diagnostic_file=r_diag,
            recovery_result_file=broken_file,
            control_observation=pair.CONTROL_OBSERVATION,
            recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
            electrical_observation=pair.ELECTRICAL_OBSERVATION,
            balance_observation=pair.BALANCE_OBSERVATION,
            j2_off_observation=pair.J2_OFF_OBSERVATION,
            finalization_phrase=contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
        )
    leg = pair.finalize_control_leg(
        matched_release_file=release_file,
        control_diagnostic_file=c_diag,
        control_result_file=c_result,
        recovery_diagnostic_file=r_diag,
        recovery_result_file=r_result,
        control_observation=pair.CONTROL_OBSERVATION,
        recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
        electrical_observation=pair.ELECTRICAL_OBSERVATION,
        balance_observation=pair.BALANCE_OBSERVATION,
        j2_off_observation=pair.J2_OFF_OBSERVATION,
        finalization_phrase=contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
    )
    leg_file = tmp_path / "leg.json"
    _write_json(leg_file, leg)
    assert pair.validate_control_leg(leg)["treatment_live_authorized"] is False
    with pytest.raises(pair.MatchedPairEvidenceError, match="exactly equal"):
        pair.treatment_preparation_gate(
            control_leg_file=leg_file,
            treatment_release_file=TREATMENT_RELEASE,
            operator_temperature_c="25.1",
        )
    gate = pair.treatment_preparation_gate(
        control_leg_file=leg_file,
        treatment_release_file=TREATMENT_RELEASE,
        operator_temperature_c="25.0",
    )
    assert gate["next_pair_stage"] == 3
    assert gate["treatment_live_authorized"] is False
    assert gate["fresh_treatment_j2_off_diagnostic_still_required"] is True


def test_pair_finalizer_requires_all_four_successes_and_limits_claim(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    leg_file, _ = _finalize_control_leg(tmp_path, release_root)
    h3_root = h3_release.load_release(TREATMENT_RELEASE)
    treatment_diagnostic, treatment_result = _make_h3_result(tmp_path, h3_root, 1)
    recovery_diagnostic, treatment_recovery = _make_h3_result(tmp_path, h3_root, 2)
    finalized = pair.finalize_pair(
        control_leg_file=leg_file,
        treatment_release_file=TREATMENT_RELEASE,
        treatment_diagnostic_file=treatment_diagnostic,
        treatment_result_file=treatment_result,
        treatment_recovery_diagnostic_file=recovery_diagnostic,
        treatment_recovery_result_file=treatment_recovery,
        treatment_observation=pair.TREATMENT_OBSERVATION,
        treatment_recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
        electrical_observation=pair.ELECTRICAL_OBSERVATION,
        j2_off_observation=pair.J2_OFF_OBSERVATION,
        pair_order_attestation=pair.PAIR_ORDER_ATTESTATION,
        comparison_outcome="NO_DETECTABLE_DIFFERENCE_RECORDED",
        finalization_phrase=contract.PAIR_FINALIZATION_PHRASE,
    )
    assert finalized["pair_stage_order_completed"] == [1, 2, 3, 4]
    assert finalized["interpretation"] == "NO_DETECTABLE_INCREMENTAL_EFFECT"
    assert finalized["attribution_or_lut_abi_proven"] is False
    assert finalized["treatment_preclaim_facade_use_cryptographically_proven"] is False
    assert finalized["automatic_chaining_performed"] is False
    pair_file = tmp_path / "pair.json"
    _write_json(pair_file, finalized)
    assert pair.validate_pair(pair.load_pair(pair_file))["valid"] is True

    failed_recovery_diagnostic, failed_recovery = _make_h3_result(
        tmp_path / "failed", h3_root, 2, outcome="unknown"
    )
    with pytest.raises(pair.MatchedPairEvidenceError, match="outcome"):
        pair.finalize_pair(
            control_leg_file=leg_file,
            treatment_release_file=TREATMENT_RELEASE,
            treatment_diagnostic_file=treatment_diagnostic,
            treatment_result_file=treatment_result,
            treatment_recovery_diagnostic_file=failed_recovery_diagnostic,
            treatment_recovery_result_file=failed_recovery,
            treatment_observation=pair.TREATMENT_OBSERVATION,
            treatment_recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
            electrical_observation=pair.ELECTRICAL_OBSERVATION,
            j2_off_observation=pair.J2_OFF_OBSERVATION,
            pair_order_attestation=pair.PAIR_ORDER_ATTESTATION,
            comparison_outcome="VISIBLE_DIFFERENCE_RECORDED",
            finalization_phrase=contract.PAIR_FINALIZATION_PHRASE,
        )

    altered_diagnostic = dict(
        pair._read_json(  # noqa: SLF001
            treatment_diagnostic, label="treatment diagnostic"
        )[2]
    )
    altered_diagnostic["boot_nonce"] = "abcdef0123456789"
    altered_diagnostic = h3_physical._seal(  # noqa: SLF001
        {key: value for key, value in altered_diagnostic.items() if key != "integrity"}
    )
    altered_diagnostic_file = tmp_path / "altered-treatment-diagnostic.json"
    _write_json(altered_diagnostic_file, altered_diagnostic)
    altered_result = dict(
        pair._read_json(treatment_result, label="treatment result")[2]  # noqa: SLF001
    )
    altered_result["boot_nonce"] = altered_diagnostic["boot_nonce"]
    altered_result = h3_physical._seal(  # noqa: SLF001
        {key: value for key, value in altered_result.items() if key != "integrity"}
    )
    altered_result_file = tmp_path / "altered-treatment-result.json"
    _write_json(altered_result_file, altered_result)
    with pytest.raises(pair.MatchedPairEvidenceError, match="diagnostic/claim"):
        pair.finalize_pair(
            control_leg_file=leg_file,
            treatment_release_file=TREATMENT_RELEASE,
            treatment_diagnostic_file=altered_diagnostic_file,
            treatment_result_file=altered_result_file,
            treatment_recovery_diagnostic_file=recovery_diagnostic,
            treatment_recovery_result_file=treatment_recovery,
            treatment_observation=pair.TREATMENT_OBSERVATION,
            treatment_recovery_observation=pair.CLEAN_WHITE_OBSERVATION,
            electrical_observation=pair.ELECTRICAL_OBSERVATION,
            j2_off_observation=pair.J2_OFF_OBSERVATION,
            pair_order_attestation=pair.PAIR_ORDER_ATTESTATION,
            comparison_outcome="VISIBLE_DIFFERENCE_RECORDED",
            finalization_phrase=contract.PAIR_FINALIZATION_PHRASE,
        )


def test_finalizers_read_each_claim_once_without_replay_toctou(
    tmp_path: Path,
    release_root: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, control_diagnostic, control_result, _, _ = _run_control_leg_inputs(
        tmp_path / "control", release_root
    )
    control_result_root = pair._read_json(  # noqa: SLF001
        control_result, label="control result"
    )[2]
    control_claim = Path(control_result_root["claim_file"]).resolve()

    treatment_root = h3_release.load_release(TREATMENT_RELEASE)
    treatment_diagnostic, treatment_result = _make_h3_result(
        tmp_path / "treatment", treatment_root, 1
    )
    treatment_result_root = pair._read_json(  # noqa: SLF001
        treatment_result, label="treatment result"
    )[2]
    treatment_claim = Path(treatment_result_root["claim_file"]).resolve()

    targets = {control_claim: 0, treatment_claim: 0}
    original_read_json = pair._read_json  # noqa: SLF001

    def counted_read_json(path: Path, *, label: str) -> tuple[Path, bytes, Any]:
        resolved = Path(path).resolve()
        if resolved in targets:
            targets[resolved] += 1
        return original_read_json(path, label=label)

    monkeypatch.setattr(pair, "_read_json", counted_read_json)
    pair._validate_control_result(  # noqa: SLF001
        physical.context_from_root(release_root),
        ordinal=1,
        diagnostic_file=control_diagnostic,
        result_file=control_result,
    )
    pair._validate_treatment_result(  # noqa: SLF001
        h3_physical.context_from_root(treatment_root),
        ordinal=1,
        diagnostic_file=treatment_diagnostic,
        result_file=treatment_result,
    )
    assert targets == {control_claim: 1, treatment_claim: 1}


def test_pair_operator_cli_publishes_all_three_outputs_exclusively(
    tmp_path: Path,
    release_root: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_file, c_diag, c_result, r_diag, r_result = _run_control_leg_inputs(
        tmp_path, release_root
    )
    fsync_calls: list[int] = []
    real_fsync = pair.os.fsync

    def counted_fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(pair.os, "fsync", counted_fsync)
    control_leg_file = tmp_path / "operator" / "control-leg.json"
    control_args = [
        "finalize-control-leg",
        "--matched-release",
        str(release_file),
        "--control-diagnostic",
        str(c_diag),
        "--control-result",
        str(c_result),
        "--recovery-diagnostic",
        str(r_diag),
        "--recovery-result",
        str(r_result),
        "--control-observation",
        pair.CONTROL_OBSERVATION,
        "--recovery-observation",
        pair.CLEAN_WHITE_OBSERVATION,
        "--electrical-observation",
        pair.ELECTRICAL_OBSERVATION,
        "--balance-observation",
        pair.BALANCE_OBSERVATION,
        "--j2-off-observation",
        pair.J2_OFF_OBSERVATION,
        "--finalization-phrase",
        contract.CONTROL_RECOVERY_FINALIZATION_PHRASE,
        "--output",
        str(control_leg_file),
    ]
    assert pair.main(control_args) == 0
    control_payload = control_leg_file.read_bytes()
    assert pair.validate_control_leg(pair.load_control_leg(control_leg_file))["valid"]
    assert pair.main(control_args) == 2
    assert control_leg_file.read_bytes() == control_payload

    gate_file = tmp_path / "operator" / "treatment-gate.json"
    assert (
        pair.main(
            [
                "treatment-gate",
                "--control-leg",
                str(control_leg_file),
                "--treatment-release",
                str(TREATMENT_RELEASE),
                "--temperature-c",
                "25.0",
                "--output",
                str(gate_file),
            ]
        )
        == 0
    )
    gate_summary = pair.validate_treatment_gate(pair.load_treatment_gate(gate_file))
    assert gate_summary["next_pair_stage"] == 3
    assert gate_summary["treatment_live_authorized"] is False

    h3_root = h3_release.load_release(TREATMENT_RELEASE)
    treatment_diagnostic, treatment_result = _make_h3_result(
        tmp_path / "operator", h3_root, 1
    )
    recovery_diagnostic, treatment_recovery = _make_h3_result(
        tmp_path / "operator", h3_root, 2
    )
    pair_file = tmp_path / "operator" / "pair.json"
    assert (
        pair.main(
            [
                "finalize-pair",
                "--control-leg",
                str(control_leg_file),
                "--treatment-release",
                str(TREATMENT_RELEASE),
                "--treatment-result",
                str(treatment_result),
                "--treatment-diagnostic",
                str(treatment_diagnostic),
                "--treatment-recovery-result",
                str(treatment_recovery),
                "--treatment-recovery-diagnostic",
                str(recovery_diagnostic),
                "--treatment-observation",
                pair.TREATMENT_OBSERVATION,
                "--treatment-recovery-observation",
                pair.CLEAN_WHITE_OBSERVATION,
                "--electrical-observation",
                pair.ELECTRICAL_OBSERVATION,
                "--j2-off-observation",
                pair.J2_OFF_OBSERVATION,
                "--pair-order-attestation",
                pair.PAIR_ORDER_ATTESTATION,
                "--comparison-outcome",
                "NO_DETECTABLE_DIFFERENCE_RECORDED",
                "--finalization-phrase",
                contract.PAIR_FINALIZATION_PHRASE,
                "--output",
                str(pair_file),
            ]
        )
        == 0
    )
    assert pair.validate_pair(pair.load_pair(pair_file))["valid"] is True
    assert fsync_calls
    assert not list((tmp_path / "operator").glob(".*.tmp"))


def test_c_first_facade_validates_before_any_delegated_treatment_entry(
    tmp_path: Path, release_root: Mapping[str, Any]
) -> None:
    control_leg_file, _ = _finalize_control_leg(tmp_path, release_root)
    gate = pair.treatment_preparation_gate(
        control_leg_file=control_leg_file,
        treatment_release_file=TREATMENT_RELEASE,
        operator_temperature_c="25.0",
    )
    gate_file = tmp_path / "treatment-gate.json"
    _write_json(gate_file, gate)
    receipt = c_first_treatment.validate_preclaim_gate(
        treatment_gate_file=gate_file,
        treatment_release_file=TREATMENT_RELEASE,
        operator_temperature_c="25.0",
    )
    assert receipt["validation_completed_before_token"] is True
    assert receipt["validation_completed_before_claim"] is True
    assert receipt["validation_completed_before_network"] is True
    assert receipt["delegated_ordinal"] == 1
    assert receipt["token_derived"] is False
    assert receipt["claim_created"] is False
    assert receipt["network_requests"] == 0
    assert receipt["visible_refreshes"] == 0
    assert receipt["facade_hard_gates_this_delegated_invocation"] is True
    assert receipt["legacy_generic_runner_physically_disabled"] is False
    assert receipt["final_pair_can_cryptographically_prove_facade_use"] is False

    delegated: list[list[str]] = []
    delegated_snapshots: list[Path] = []

    def record_delegate(argv: Any) -> int:
        observed = list(argv)
        snapshot = Path(observed[observed.index("--release") + 1])
        assert snapshot != TREATMENT_RELEASE
        assert snapshot.is_file()
        assert snapshot.read_bytes() == TREATMENT_RELEASE.read_bytes()
        delegated.append(observed)
        delegated_snapshots.append(snapshot)
        return 17

    shared = [
        "--release",
        str(TREATMENT_RELEASE),
        "--treatment-gate",
        str(gate_file),
        "--temperature-c",
        "25.0",
    ]
    command_args = (
        [
            "authorize",
            *shared,
            "--diagnostic",
            str(tmp_path / "not-read-by-delegate.json"),
            "--accept-u1-u7",
            h3_contract.EMPIRICAL_ACCEPTANCE_PHRASE,
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
        ],
        [
            "diagnose",
            *shared,
            "--screen-state",
            h3_physical.SCREEN_INITIAL,
            "--confirm-j2",
            "OFF",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--base-url",
            "http://192.168.4.1",
            "--output",
            str(tmp_path / "diagnostic.json"),
        ],
        [
            "run",
            *shared,
            "--confirm-j2",
            "ON",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--authorization",
            "synthetic-not-used",
            "--diagnostic",
            str(tmp_path / "not-read-by-delegate.json"),
            "--base-url",
            "http://192.168.4.1",
            "--output",
            str(tmp_path / "result.json"),
        ],
    )
    for expected_command, argv in zip(
        ("authorize", "diagnose", "run"), command_args, strict=True
    ):
        assert c_first_treatment.main(argv, delegate=record_delegate) == 17
        observed = delegated[-1]
        assert observed[0] == expected_command
        assert observed[observed.index("--ordinal") + 1] == "1"
        assert "--treatment-gate" not in observed
        assert not delegated_snapshots[-1].exists()

    bad_gate = dict(gate)
    bad_gate["treatment_action_binding"] = {
        **bad_gate["treatment_action_binding"],
        "firmware_binary_sha256": "0" * 64,
    }
    bad_gate = h3_physical._seal(  # noqa: SLF001
        {key: value for key, value in bad_gate.items() if key != "integrity"}
    )
    bad_gate_file = tmp_path / "bad-gate.json"
    _write_json(bad_gate_file, bad_gate)
    calls_before_failure = len(delegated)
    invalid_argv = [
        "authorize",
        "--release",
        str(TREATMENT_RELEASE),
        "--treatment-gate",
        str(bad_gate_file),
        "--temperature-c",
        "25.0",
        "--diagnostic",
        str(tmp_path / "not-read.json"),
        "--accept-u1-u7",
        h3_contract.EMPIRICAL_ACCEPTANCE_PHRASE,
        "--confirm-monitors",
        contract.OPERATOR_MONITORING_CONFIRMATION,
    ]
    assert c_first_treatment.main(invalid_argv, delegate=record_delegate) == 2
    assert len(delegated) == calls_before_failure

    wrong_temperature = list(command_args[2])
    wrong_temperature[wrong_temperature.index("25.0")] = "25.1"
    assert c_first_treatment.main(wrong_temperature, delegate=record_delegate) == 2
    assert len(delegated) == calls_before_failure


def test_c_first_facade_rejects_release_replacement_after_validation(
    tmp_path: Path,
    release_root: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_copy = tmp_path / "treatment-release.json"
    release_copy.write_bytes(TREATMENT_RELEASE.read_bytes())
    control_leg_file, _ = _finalize_control_leg(tmp_path / "control", release_root)
    gate = pair.treatment_preparation_gate(
        control_leg_file=control_leg_file,
        treatment_release_file=release_copy,
        operator_temperature_c="25.0",
    )
    gate_file = tmp_path / "treatment-gate.json"
    _write_json(gate_file, gate)
    original_validate = c_first_treatment.validate_preclaim_gate

    def validate_then_replace(**kwargs: Any) -> dict[str, Any]:
        receipt = original_validate(**kwargs)
        release_copy.write_bytes(b"{}\n")
        return receipt

    monkeypatch.setattr(
        c_first_treatment, "validate_preclaim_gate", validate_then_replace
    )
    delegated: list[list[str]] = []
    result = c_first_treatment.main(
        [
            "authorize",
            "--release",
            str(release_copy),
            "--treatment-gate",
            str(gate_file),
            "--temperature-c",
            "25.0",
            "--diagnostic",
            str(tmp_path / "not-read.json"),
            "--accept-u1-u7",
            h3_contract.EMPIRICAL_ACCEPTANCE_PHRASE,
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
        ],
        delegate=lambda argv: delegated.append(list(argv or ())) or 0,
    )
    assert result == 2
    assert delegated == []
