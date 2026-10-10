from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1_pack as legacy
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_once as once
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as pack


BOOT = "0123456789abcdef"


def _identity(kind: str) -> dict[str, Any]:
    runner = once.base.runner
    return {
        "kind": f"{runner.DEVICE_KIND_PREFIX}-{kind}",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


def _capabilities() -> dict[str, bool]:
    return {
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "factory_otp_white_actions": True,
        "same_palette_hold_probe": False,
        "cross_palette_hold_probe": False,
        "ptlw_fullframe_ab_probe": True,
        "runtime_code7_full_dtm_prestage": True,
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "busy_qualified_arm_execute_dispatch": True,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "external_anchor_required": False,
        "anchor_established_by_firmware": True,
        "one_visible_refresh_required": True,
        "runtime_code7_action_reachable": False,
        "factory_otp_recovery_ordinal": 5,
    }


def _version() -> dict[str, Any]:
    runner = once.base.runner
    return {
        **_identity("version"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "action_count": 5,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "per_action_readiness_qualification_required": True,
        "three_gate_busy_admission_evidence_required": True,
        "qualifier_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        **{
            key: False
            for key in (
                "automatic_execute",
                "automatic_chaining",
                "startup_refresh",
                "raw_frame_ingress",
                "electrical_parameter_write",
                "dither",
                "spatial_mixing",
                "retry",
                "recovery",
            )
        },
        "nvs_contract": {
            "namespace": runner.NVS_NAMESPACE,
            "key": runner.NVS_KEY,
            "terminal_next_ordinal": 6,
            "initial_key_present": False,
            "initial_value": 1,
            "initial_next_ordinal": 1,
        },
        "baseline_contract": _baseline(),
        **_capabilities(),
    }


def _manifest() -> dict[str, Any]:
    profile = once.REPORT["contract"]["profile"]
    return {
        **_identity("manifest"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "automatic_chaining": False,
        "startup_refresh": False,
        "retry": False,
        "recovery": False,
        "baseline_contract": _baseline(),
        "per_action_readiness_qualification": (
            once._expected_qualification_contract()  # noqa: SLF001
        ),
        "busy_admission_contract": deepcopy(pack.BUSY_ADMISSION_CONTRACT),
        "history_layout": {
            "factory_otp_anchor_ordinal": 1,
            "factory_otp_reset_ordinal": 3,
            "factory_otp_recovery_ordinal": 5,
            "runtime_transport_codes": [5, 7],
            "ptlw_command": 0x83,
            "ptlw_payload_bytes": 9,
            "ptlw_mode": 1,
            "ptlw_payload_hex": "00b0014f00f0016701",
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "window": {
                "x": 176,
                "y": 240,
                "width": 160,
                "height": 120,
                "cs1_code": 5,
                "cs2_code": 5,
            },
            "runtime_code7_full_dtm_prestage": True,
            "runtime_code7_prestage_no_refresh": True,
            "runtime_code7_prestage_bytes_per_controller": 153_600,
            "runtime_code7_prestage_sha256": pack.PRELOAD_DTM_SHA256,
            "treatment_a": {
                "ordinal": 2,
                "ptlw": False,
                "dtm_transport": "FULL_CONTROLLER_COMPOSITE_NO_PTLW",
                "target_dtm_bytes_per_controller": 153_600,
                "target_dtm_sha256": pack.FULL_COMPOSITE_DTM_SHA256,
                "combined_dtm_bytes_per_controller": 307_200,
                "combined_dtm_sha256": pack.TREATMENT_A_COMBINED_DTM_SHA256,
            },
            "treatment_b": {
                "ordinal": 4,
                "ptlw": True,
                "ptlw_writes_per_controller": 1,
                "dtm_transport": "INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW",
                "target_dtm_bytes_per_controller": 9_600,
                "target_dtm_sha256": pack.CROPPED_DTM_SHA256,
                "combined_dtm_bytes_per_controller": 163_200,
                "combined_dtm_sha256": pack.TREATMENT_B_COMBINED_DTM_SHA256,
            },
            "same_final_controller_sram": True,
            "same_logical_frame": True,
            "logical_frame_sha256": pack.LOGICAL_FRAME_SHA256,
            "logical_frame_histogram": [0, 0, 0, 0, 0, 38_400, 0, 576_000],
            "common_refresh_sequence": [
                "PON_BUSY_COMPLETE_60S_GATE",
                "DRF_00_BUSY_COMPLETE_60S_GATE",
                "POF_00_BUSY_COMPLETE_60S_GATE",
            ],
            "fresh_white_before_each_treatment": True,
            "runtime_treatment_action_stage_cdi": False,
            "runtime_treatment_action_stage_btst2": False,
            "runtime_treatment_repeat_ptlw_after_pon_busy": False,
            "command_0x86": False,
            "extra_dtm_prefix_or_suffix_byte": False,
            "busy_idle_level_required": 1,
            "ordinal_1_raw_levels_accepted": [1],
            "fresh_low_admission_forbidden": True,
            "j2_off_raw0_allowed_only_on_read_only_get_diagnostic": True,
            "later_ordinal_raw_levels_accepted": [0, 1],
            "late_low_is_never_treated_as_idle": True,
            "late_low_requires_same_boot_prior_complete": True,
            "late_low_requires_prior_safe_finish_high": True,
            "late_low_requires_ram_only_firmware_eligibility": True,
            "late_pof_sleep_low_eligible_boot_default": False,
            "late_pof_sleep_low_eligible_consumed_before_qualification": True,
            "per_action_revision_qualifier_required": True,
            "unqualified_busy_zero_accepted": False,
            **profile,
        },
        **_capabilities(),
    }


def _zero_readiness() -> dict[str, Any]:
    return {
        "valid": False,
        "qualified": False,
        "operation_id": 0,
        "ordinal": 0,
        "entry_busy": 255,
        "final_busy": 255,
        "final_gpio": {
            "rst": 255,
            "cs1": 255,
            "cs2": 255,
            "sck": 255,
            "dc": 255,
            "mosi": 255,
        },
        "final_high_stable_ms": 0,
        "reset_count": 0,
        "revision_read_count": 0,
        "revision_command_trace": [0, 0, 0, 0],
        "total_ms": 0,
        "cs1": {
            "sample1": {"idle": False, "bytes": [0, 0, 0]},
            "sample2": {"idle": False, "bytes": [0, 0, 0]},
            "stable": False,
            "nontrivial": False,
            "exact_010104": False,
        },
        "cs2": {
            "sample1": {"idle": False, "bytes": [0, 0, 0]},
            "sample2": {"idle": False, "bytes": [0, 0, 0]},
            "stable": False,
            "nontrivial": False,
            "exact_010104": False,
        },
        "all_revision_samples_exact_010104": False,
        "failure_stage": "none",
    }


def _zero_busy_admission() -> dict[str, Any]:
    return {
        "ordinal": 0,
        "arm": deepcopy(once._UNCAPTURED_BUSY_GATE),  # noqa: SLF001
        "execute": deepcopy(once._UNCAPTURED_BUSY_GATE),  # noqa: SLF001
        "dispatch": deepcopy(once._UNCAPTURED_BUSY_GATE),  # noqa: SLF001
    }


def _busy_admission(
    ordinal: int, raw_busy: int, *, captured_through: str = "dispatch"
) -> dict[str, Any]:
    if ordinal == 1:
        gate = {
            "captured": True,
            "raw_busy": 1,
            "allowed": True,
            "raw1_direct": True,
            "raw0_same_boot_prior_complete_ram_eligibility_used": False,
            "late_pof_sleep_low_eligible_before_gate": False,
        }
    elif raw_busy == 1:
        gate = {
            "captured": True,
            "raw_busy": 1,
            "allowed": True,
            "raw1_direct": True,
            "raw0_same_boot_prior_complete_ram_eligibility_used": False,
            "late_pof_sleep_low_eligible_before_gate": True,
        }
    else:
        gate = {
            "captured": True,
            "raw_busy": 0,
            "allowed": True,
            "raw1_direct": False,
            "raw0_same_boot_prior_complete_ram_eligibility_used": True,
            "late_pof_sleep_low_eligible_before_gate": True,
        }
    names = ("arm", "execute", "dispatch")
    limit = names.index(captured_through)
    return {
        "ordinal": ordinal,
        **{
            name: deepcopy(gate if index <= limit else once._UNCAPTURED_BUSY_GATE)  # noqa: SLF001
            for index, name in enumerate(names)
        },
    }


def _readiness(ordinal: int, admission_busy: int) -> dict[str, Any]:
    side = {
        "sample1": {"idle": True, "bytes": [1, 1, 4]},
        "sample2": {"idle": True, "bytes": [1, 1, 4]},
        "stable": True,
        "nontrivial": True,
        "exact_010104": True,
    }
    return {
        "valid": True,
        "qualified": True,
        "operation_id": ordinal,
        "ordinal": ordinal,
        "entry_busy": admission_busy,
        "final_busy": 1,
        "final_gpio": {"rst": 1, "cs1": 1, "cs2": 1, "sck": 0, "dc": 0, "mosi": 0},
        "final_high_stable_ms": 50,
        "reset_count": 5,
        "revision_read_count": 4,
        "revision_command_trace": [112, 112, 112, 112],
        "total_ms": 700,
        "cs1": deepcopy(side),
        "cs2": deepcopy(side),
        "all_revision_samples_exact_010104": True,
        "failure_stage": "none",
    }


def _fresh_report() -> dict[str, Any]:
    return {
        **_identity("report"),
        "boot_nonce": BOOT,
        "valid": False,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "qualification_call_count_for_action": 0,
        "total_qualification_call_count": 0,
        "late_pof_sleep_low_eligible": False,
        "busy_admission": _zero_busy_admission(),
        "readiness": _zero_readiness(),
        "phase": 0,
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }


def _complete_report(ordinal: int, admission_busy: int) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    source = once.REPORT["actions"][ordinal - 1]
    return {
        **_identity("report"),
        "boot_nonce": BOOT,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": ordinal,
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 5,
        "no_retry": True,
        "no_recovery": True,
        "qualification_called": True,
        "qualification_call_count_for_action": 1,
        "total_qualification_call_count": ordinal,
        "late_pof_sleep_low_eligible": ordinal < 5,
        "busy_admission": _busy_admission(ordinal, admission_busy),
        "readiness": _readiness(ordinal, admission_busy),
        "action_stage_command_counts": once._expected_action_stage_counts(  # noqa: SLF001
            ordinal
        ),
        "driver": {
            "operation_id": ordinal,
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "spi_hz": 1_000_000,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "pon_ms": 200,
            "drf_ms": 33_000,
            "pof_ms": 200,
            "input_fnv1a": source["frame"]["fnv1a"],
            "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
            "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }


def _failed_readiness(ordinal: int, admission_busy: int) -> dict[str, Any]:
    value = _readiness(ordinal, admission_busy)
    value.update(
        {
            "qualified": False,
            "final_busy": 0,
            "final_gpio": {"rst": 0, "cs1": 0, "cs2": 0, "sck": 0, "dc": 0, "mosi": 0},
            "failure_stage": "cs2_revision_trivial",
        }
    )
    value["cs2"]["nontrivial"] = False
    value["cs2"]["exact_010104"] = False
    value["all_revision_samples_exact_010104"] = False
    return value


def _fault_report(ordinal: int, admission_busy: int) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    return {
        **_identity("report"),
        "boot_nonce": BOOT,
        "valid": True,
        "terminal_state": "FAULT",
        "result": False,
        "error": "per_action_readiness_qualification_failed",
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": ordinal,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": ordinal - 1,
        "qualification_called": True,
        "qualification_call_count_for_action": 1,
        "total_qualification_call_count": ordinal,
        "late_pof_sleep_low_eligible": False,
        "busy_admission": _busy_admission(ordinal, admission_busy),
        "readiness": _failed_readiness(ordinal, admission_busy),
        "action_stage_command_counts": deepcopy(once._ZERO_ACTION_STAGE_COUNTS),  # noqa: SLF001
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": ordinal,
        "no_retry": True,
        "no_recovery": True,
    }


class FakeDevice:
    def __init__(self, ordinal: int, *, busy: int, fault: bool = False) -> None:
        self.ordinal = ordinal
        self.busy = busy
        self.fault = fault
        self.executed = False
        self.calls: list[tuple[str, str]] = []
        self.expected_claim: Path | None = None
        self.tamper_gate: str | None = None

    def status(self) -> dict[str, Any]:
        if self.executed and self.fault:
            action = once.base.runner.ACTIONS[self.ordinal - 1]
            return {
                **_identity("status"),
                "boot_nonce": BOOT,
                "state": "fault_locked",
                "phase": 3,
                "phase_name": "FAULT",
                "cursor_raw": (3 << 8) | self.ordinal,
                "next_ordinal": self.ordinal,
                "current_action": dict(action),
                "campaign_complete": False,
                "fixture_self_check_passed": True,
                "cursor_valid": True,
                "persistent_key_present": True,
                "execute_pending": False,
                "gpio_initialized": True,
                "busy": 0,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
                "arm_request_count": self.ordinal,
                "execute_request_count": self.ordinal,
                "total_driver_call_count": self.ordinal - 1,
                "qualification_pending": False,
                "qualification_running": False,
                "qualification_call_count_for_action": 1,
                "total_qualification_call_count": self.ordinal,
                "late_pof_sleep_low_eligible": False,
                "busy_admission": _busy_admission(self.ordinal, self.busy),
                "readiness": _failed_readiness(self.ordinal, self.busy),
            }
        prior = self.ordinal - 1
        return {
            **_identity("status"),
            "boot_nonce": BOOT,
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "cursor_raw": self.ordinal,
            "next_ordinal": self.ordinal,
            "current_action": None,
            "campaign_complete": False,
            "fixture_self_check_passed": True,
            "cursor_valid": True,
            "gpio_initialized": True,
            "busy": self.busy,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "execute_pending": False,
            "persistent_key_present": self.ordinal != 1,
            "arm_request_count": prior,
            "execute_request_count": prior,
            "total_driver_call_count": prior,
            "qualification_pending": False,
            "qualification_running": False,
            "qualification_call_count_for_action": 0 if self.ordinal == 1 else 1,
            "total_qualification_call_count": prior,
            "late_pof_sleep_low_eligible": self.ordinal > 1,
            "busy_admission": _zero_busy_admission()
            if self.ordinal == 1
            else _busy_admission(
                prior, 1 if prior == 1 else 0
            ),
            "readiness": _zero_readiness()
            if self.ordinal == 1
            else _readiness(prior, 1 if prior == 1 else 0),
        }

    def report(self) -> dict[str, Any]:
        if self.executed:
            if self.fault:
                return _fault_report(self.ordinal, self.busy)
            value = _complete_report(self.ordinal, self.busy)
            if self.tamper_gate == "dispatch":
                value["busy_admission"]["dispatch"]["allowed"] = False
            return value
        if self.ordinal == 1:
            return _fresh_report()
        return _complete_report(
            self.ordinal - 1,
            1 if self.ordinal - 1 == 1 else 0,
        )

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert timeout > 0
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if method == "GET":
            assert headers is None
            values = {
                "version": _version(),
                "manifest": _manifest(),
                "status": self.status(),
                "report": self.report(),
            }
            return 200, values[name]
        assert method == "POST"
        assert headers is not None
        if self.expected_claim is not None:
            claim = json.loads(self.expected_claim.read_text(encoding="utf-8"))
            assert claim["qualifier_v2_prerequisite_bundle_id"] == (
                pack.QUALIFIER_V2_BUNDLE_ID
            )
            assert claim["admission_raw_busy"] == self.busy
        action = once.base.runner.ACTIONS[self.ordinal - 1]
        if name == "arm":
            response = {
                "accepted": True,
                "armed": True,
                "action_id": action["action_id"],
                "boot_nonce": BOOT,
                "arm_nonce": "fedcba9876543210",
                "busy_admission": _busy_admission(
                    self.ordinal, self.busy, captured_through="arm"
                ),
            }
            if self.tamper_gate == "arm":
                response["busy_admission"]["arm"]["allowed"] = False
            return 201, response
        if name == "execute":
            self.executed = True
            response = {
                "accepted": True,
                "execute_consumed": True,
                "action_id": action["action_id"],
                "boot_nonce": BOOT,
                "busy_admission": _busy_admission(
                    self.ordinal, self.busy, captured_through="execute"
                ),
            }
            if self.tamper_gate == "execute":
                response["busy_admission"]["execute"]["allowed"] = False
            return 202, response
        raise AssertionError(name)


def test_pack_rotates_every_identity_and_freezes_supersession() -> None:
    current = pack.build_report()
    old = legacy.build_report()
    assert current["contract_id"] == pack.CONTRACT_ID
    assert pack.CONTRACT_ID not in {
        pack.MECHANICAL_SOURCE_V1_CONTRACT_ID,
        pack.MECHANICAL_SOURCE_V1B_CONTRACT_ID,
    }
    assert set(pack.ACTION_IDS).isdisjoint(
        item["action_id"] for item in old["actions"]
    )
    assert current["contract"]["supersedes_campaign_contract_ids"] == [
        pack.MECHANICAL_SOURCE_V1_CONTRACT_ID,
        pack.MECHANICAL_SOURCE_V1B_CONTRACT_ID,
    ]
    assert current["contract"]["qualifier_v2_prerequisite_bundle_id"] == (
        pack.QUALIFIER_V2_BUNDLE_ID
    )


def test_dry_validate_binds_artifacts_and_all_prerequisite_files() -> None:
    value = once.dry_validate()
    assert value["verified"] is True
    assert value["network"] == {"get": 0, "post": 0}
    assert len(value["qualifier_v2_prerequisite"]["observed_sha256"]) == 7
    assert all(
        item["verified"] is True
        for item in value["artifact_binding_status"].values()
    )


def test_tampered_prerequisite_canonical_binding_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prerequisite = deepcopy(pack.QUALIFIER_V2_PREREQUISITE)
    prerequisite["evidence"]["result"]["canonical_sha256"] = "0" * 64
    monkeypatch.setattr(pack, "QUALIFIER_V2_PREREQUISITE", prerequisite)
    monkeypatch.setattr(
        pack,
        "QUALIFIER_V2_BUNDLE_ID",
        hashlib.sha256(pack.identity.canonical(prerequisite)).hexdigest(),
    )
    with pytest.raises(once.base.runner.RecheckError, match="canonical SHA"):
        once.qualifier_prerequisite_status()


def test_fresh_raw0_rejected_before_claim_or_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=0)
    claims = tmp_path / "claims"
    with pytest.raises(once.base.runner.RecheckError, match="raw BUSY=1"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "bad.json",
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    assert not claims.exists()
    assert all(method == "GET" for method, _ in fake.calls)


def test_later_raw0_without_local_prior_is_rejected_before_network(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(2, busy=0)
    with pytest.raises(once.base.runner.RecheckError, match="prior-result"):
        once.run_once(
            "http://192.0.2.1",
            2,
            claims=tmp_path / "claims",
            output=tmp_path / "bad.json",
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    assert fake.calls == []


@pytest.mark.parametrize("tamper_gate", ["arm", "execute"])
def test_mutation_response_busy_gate_tamper_is_consumed_and_sealed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_gate: str,
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=1)
    fake.tamper_gate = tamper_gate
    output = tmp_path / f"{tamper_gate}-fault.json"
    with pytest.raises(once.base.runner.RecheckError, match="must not be retried"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=output,
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["claim_state"] == "permanently_consumed"
    assert evidence["claim_file_sha256"] == hashlib.sha256(
        Path(evidence["claim_file"]).read_bytes()
    ).hexdigest()
    posts = [name for method, name in fake.calls if method == "POST"]
    assert posts == (["arm"] if tamper_gate == "arm" else ["arm", "execute"])


def test_terminal_dispatch_busy_gate_tamper_is_consumed_and_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=1)
    fake.tamper_gate = "dispatch"
    output = tmp_path / "dispatch-fault.json"
    with pytest.raises(once.base.runner.RecheckError, match="strict V3 validation"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=output,
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "terminal_complete_rejected"
    assert evidence["action_must_not_be_retried"] is True


def test_ordinal1_then_ordinal2_raw0_binds_claim_result_and_entry_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    claims = tmp_path / "claims"
    first = FakeDevice(1, busy=1)
    first.expected_claim = claims / f"{pack.ACTION_IDS[0]}.json"
    first_output = tmp_path / "first.json"
    result1 = once.run_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=first_output,
        confirm_j2_on=True,
        requester=first,
        poll_seconds=65,
        poll_count=1,
    )
    assert result1["admission_raw_busy"] == 1
    assert result1["claim_file_sha256"] == hashlib.sha256(
        first.expected_claim.read_bytes()
    ).hexdigest()
    assert result1["claim_integrity"] == json.loads(
        first.expected_claim.read_text(encoding="utf-8")
    )["integrity"]
    assert Path(result1["output_reservation"]["reservation_file"]).is_file()

    second = FakeDevice(2, busy=0)
    second.expected_claim = claims / f"{pack.ACTION_IDS[1]}.json"
    second_output = tmp_path / "second.json"
    result2 = once.run_once(
        "http://192.0.2.1",
        2,
        claims=claims,
        output=second_output,
        prior_result=first_output,
        confirm_j2_on=True,
        requester=second,
        poll_seconds=65,
        poll_count=1,
    )
    assert result2["admission_raw_busy"] == 0
    assert result2["terminal_report"]["readiness"]["entry_busy"] == 0
    assert result2["qualification_entry_busy"] == 0
    assert result2["prior_local_evidence"]["prior_result_sha256"] == (
        hashlib.sha256(first_output.read_bytes()).hexdigest()
    )
    claim2 = json.loads(second.expected_claim.read_text(encoding="utf-8"))
    assert claim2["prior_local_evidence"]["prior_claim_sha256"] == (
        hashlib.sha256(first.expected_claim.read_bytes()).hexdigest()
    )
    assert [name for method, name in second.calls if method == "POST"] == [
        "arm",
        "execute",
    ]


def test_qualifier_entry_busy_is_independent_from_preflight_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=1)
    original = fake.report

    def independent_report() -> dict[str, Any]:
        value = original()
        if fake.executed:
            value["readiness"]["entry_busy"] = 0
        return value

    monkeypatch.setattr(fake, "report", independent_report)
    result = once.run_once(
        "http://192.0.2.1",
        1,
        claims=tmp_path / "claims",
        output=tmp_path / "independent.json",
        confirm_j2_on=True,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
    )
    assert result["admission_raw_busy"] == 1
    assert result["qualification_entry_busy"] == 0
    assert result["terminal_report"]["readiness"]["entry_busy"] == 0


def test_qualification_fault_salvage_is_four_gets_zero_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=1, fault=True)
    claims = tmp_path / "claims"
    consumed = tmp_path / "consumed.json"
    with pytest.raises(once.base.runner.RecheckError, match="terminal FAULT"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=consumed,
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    posts_before = sum(method == "POST" for method, _ in fake.calls)
    salvage = once.salvage_fault_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=tmp_path / "salvage.json",
        confirm_j2_off=True,
        requester=fake,
    )
    assert salvage["network"] == {"get": 4, "post": 0}
    assert sum(method == "POST" for method, _ in fake.calls) == posts_before == 2
    assert salvage["terminal_report"]["driver_called"] is False
    assert salvage["terminal_report"]["action_stage_command_counts"] == (
        once._ZERO_ACTION_STAGE_COUNTS  # noqa: SLF001
    )
    consumed_value = json.loads(consumed.read_text(encoding="utf-8"))
    assert consumed_value["claim_file_sha256"] == salvage["claim_file_sha256"]
    assert consumed_value["output_reservation"] != salvage["output_reservation"]


def test_later_fault_salvage_requires_and_validates_prior_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    claims = tmp_path / "claims"
    first = FakeDevice(1, busy=1)
    first_result = tmp_path / "first.json"
    once.run_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=first_result,
        confirm_j2_on=True,
        requester=first,
        poll_seconds=65,
        poll_count=1,
    )
    second = FakeDevice(2, busy=0, fault=True)
    with pytest.raises(once.base.runner.RecheckError, match="terminal FAULT"):
        once.run_once(
            "http://192.0.2.1",
            2,
            claims=claims,
            output=tmp_path / "second-fault.json",
            prior_result=first_result,
            confirm_j2_on=True,
            requester=second,
            poll_seconds=65,
            poll_count=1,
        )
    calls_before = len(second.calls)
    with pytest.raises(once.base.runner.RecheckError, match="prior-result"):
        once.salvage_fault_once(
            "http://192.0.2.1",
            2,
            claims=claims,
            output=tmp_path / "missing-prior.json",
            confirm_j2_off=True,
            requester=second,
        )
    assert len(second.calls) == calls_before
    value = once.salvage_fault_once(
        "http://192.0.2.1",
        2,
        claims=claims,
        output=tmp_path / "second-salvage.json",
        prior_result=first_result,
        confirm_j2_off=True,
        requester=second,
    )
    assert value["network"] == {"get": 4, "post": 0}
    assert value["prior_local_evidence"]["prior_result_sha256"] == hashlib.sha256(
        first_result.read_bytes()
    ).hexdigest()


def test_fault_salvage_rejects_status_report_surface_mismatch_with_zero_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1, busy=1, fault=True)
    claims = tmp_path / "claims"
    with pytest.raises(once.base.runner.RecheckError, match="terminal FAULT"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "consumed.json",
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    original_status = fake.status

    def mismatched_status() -> dict[str, Any]:
        value = original_status()
        value["readiness"]["entry_busy"] = 0
        return value

    monkeypatch.setattr(fake, "status", mismatched_status)
    posts_before = sum(method == "POST" for method, _ in fake.calls)
    output = tmp_path / "rejected-salvage.json"
    with pytest.raises(once.base.runner.RecheckError, match="readiness differs"):
        once.salvage_fault_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert sum(method == "POST" for method, _ in fake.calls) == posts_before
    assert not output.exists()
    assert once._reservation_path(output).is_file()  # noqa: SLF001


def test_output_aliasing_a_future_claim_is_rejected_before_device_request(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    future_claim = claims / f"{pack.ACTION_IDS[1]}.json"
    fake = FakeDevice(1, busy=1)
    with pytest.raises(once.base.runner.RecheckError, match="alias collision"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=future_claim,
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    assert fake.calls == []
    assert not future_claim.exists()
    assert not once._reservation_path(future_claim).exists()  # noqa: SLF001


@pytest.mark.parametrize("poll_seconds", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_poll_seconds_is_rejected_before_device_request(
    tmp_path: Path, poll_seconds: float
) -> None:
    fake = FakeDevice(1, busy=1)
    with pytest.raises(once.base.runner.RecheckError, match="finite poll_seconds"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "never.json",
            confirm_j2_on=True,
            requester=fake,
            poll_seconds=poll_seconds,
            poll_count=1,
        )
    assert fake.calls == []


def test_dry_validate_false_has_nonzero_cli_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(once, "dry_validate", lambda: {"verified": False})
    assert once.main(["dry-validate"]) == 2
    assert json.loads(capsys.readouterr().out)["verified"] is False


def test_same_process_device_access_is_nonreentrant(tmp_path: Path) -> None:
    assert once._DEVICE_ACCESS_GUARD.acquire(blocking=False)  # noqa: SLF001
    try:
        with pytest.raises(once.base.runner.RecheckError, match="operation is active"):
            once.diagnose_j2_off(
                "http://192.0.2.1",
                output=tmp_path / "never.json",
                confirm_j2_off=True,
                requester=FakeDevice(1, busy=0),
            )
    finally:
        once._DEVICE_ACCESS_GUARD.release()  # noqa: SLF001


def test_describe_exposes_no_retry_and_read_only_salvage() -> None:
    value = once.describe()
    assert value["preflight_busy_contract"]["fresh_ordinal_1_live"] == (
        "RAW_BUSY_1_ONLY"
    )
    assert value["fault_salvage"]["method"] == "FOUR_GETS_ONLY"
    assert value["automatic_retry"] is False
    assert value["automatic_recovery"] is False
    assert value["automatic_chaining"] is False
