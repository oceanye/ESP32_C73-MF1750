from __future__ import annotations

from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_runtime_lut_compiled_identity as compiled
from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools import mf1750_ec5_runtime_lut_release as release


LEGACY_UNBOUND_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260811"
)
LEGACY_FALSE_ACCEPTANCE_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260811_V2"
)
LEGACY_TRUNCATED_ELF_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260811_V3"
)
LEGACY_APPARENT_TEMPERATURE_BAND_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260811_V4"
)
LEGACY_STALE_COMPILED_DESCRIPTOR_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V5"
)
LEGACY_COMPILED_IDENTITY_COVERAGE_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V6"
)
REAL_RELEASE_DIR = (
    contract.REPO_ROOT
    / ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7"
)
REAL_RELEASE_IDENTITIES = {
    "WF20_25": {
        "release_id": "52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e",
        "canonical_sha256": (
            "91a498788b074c0d8619e666df0e8c96fc8868e6c9fbee024b97ad8ad183d92e"
        ),
        "host_execution_bundle_sha256": (
            "3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0"
        ),
        "runtime_binary_sha256": (
            "53d3abf2319761f282c518ebd6fd606f8efdfe0b1a869a1dcf61c04adbdecc06"
        ),
        "runtime_elf_sha256": (
            "63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df"
        ),
        "recovery_binary_sha256": (
            "6a50b2bf287f3d6fd688c9cdfa2052ddc7db3d86c2f2ac9157585cdafd0766d2"
        ),
        "recovery_elf_sha256": (
            "0c8c82c35b46c69742f27a28c6fdce0ac2d003b3b0dd8a8b7b80152a608d9924"
        ),
    },
    "WF23_25": {
        "release_id": "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4",
        "canonical_sha256": (
            "0f5dfeb8359abea5d0d4b5b800958737f161f78ca81ec3515877920fcd759b7a"
        ),
        "host_execution_bundle_sha256": (
            "3e33b58e44fa1de42f268d5af0865ac347a65425c3bbcbf4fc859470feaa37c0"
        ),
        "runtime_binary_sha256": (
            "6eb9115ef143142de801c96fe31c8b9898455f550a52a85c51cfa7a2026698e2"
        ),
        "runtime_elf_sha256": (
            "d385b01ffcee182d9614d9462489c44628990a576c54979cc9254c8fc3824aa1"
        ),
        "recovery_binary_sha256": (
            "2712984d39f1c295841a4b9994c72ee13f6c6935e514ce918648cce2a6159e7c"
        ),
        "recovery_elf_sha256": (
            "9c3587285d2b4748ca1594dffbc0848dd394d48c74bd205d6d7ce90699bd3939"
        ),
    },
}


def _binary_for(elf: bytes) -> bytes:
    binary = bytearray(256)
    binary[0] = 0xE9
    binary[
        compiled.APP_DESCRIPTOR_OFFSET : compiled.APP_DESCRIPTOR_OFFSET
        + len(compiled.APP_DESCRIPTOR_MAGIC)
    ] = compiled.APP_DESCRIPTOR_MAGIC
    digest = hashlib.sha256(elf).digest()
    binary[
        compiled.EMBEDDED_ELF_SHA256_OFFSET : compiled.EMBEDDED_ELF_SHA256_OFFSET
        + len(digest)
    ] = digest
    return bytes(binary)


def _write_image(
    root: Path, profile_id: str, role: str
) -> tuple[Path, Path, Path, Path | None]:
    root.mkdir(parents=True, exist_ok=True)
    suffix = "runtime" if role == contract.ROLE_RUNTIME else "white"
    marker = contract.compiled_descriptor_marker(profile_id, role)
    if role == contract.ROLE_RUNTIME:
        required = compiled._runtime_required_ascii(profile_id)  # noqa: SLF001
        include = (
            contract.REPO_ROOT / contract.profile_row(profile_id)["generated_include"]
        )
        source_text = f'{marker}\n#include "{include.name}"\n'
    else:
        required = compiled._recovery_required_ascii(profile_id)  # noqa: SLF001
        include = None
        source_text = f"{marker}\nfactory OTP only\n"
    # Ordinary identity strings may repeat. Only the dedicated full marker is
    # required to be unique.
    ordinary = [item for item in required if item != marker]
    elf = b"\x7fELF\0" + b"\0".join(
        item.encode("ascii") for item in (marker, *ordinary, *ordinary)
    )
    elf_file = root / f"{profile_id}-{suffix}.elf"
    binary_file = root / f"{profile_id}-{suffix}.bin"
    source_file = root / f"{profile_id}-{suffix}.cpp"
    elf_file.write_bytes(elf)
    binary_file.write_bytes(_binary_for(elf))
    source_file.write_text(source_text, encoding="utf-8")
    return elf_file, binary_file, source_file, include


def _release_root(tmp_path: Path, profile_id: str) -> Mapping[str, Any]:
    runtime = _write_image(tmp_path, profile_id, contract.ROLE_RUNTIME)
    recovery = _write_image(tmp_path, profile_id, contract.ROLE_WHITE)
    assert runtime[3] is not None
    return release.materialize_release(
        profile_id,
        runtime_elf=runtime[0],
        runtime_binary=runtime[1],
        runtime_source=runtime[2],
        generated_include=runtime[3],
        recovery_elf=recovery[0],
        recovery_binary=recovery[1],
        recovery_source=recovery[2],
    )


def _isolated_host_execution_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    source_root = tmp_path / "host-execution-sources"
    for relative_path in release.HOST_EXECUTION_SOURCE_RELATIVE_PATHS:
        source = contract.REPO_ROOT / Path(relative_path)
        target = source_root / Path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    monkeypatch.setattr(release, "HOST_EXECUTION_SOURCE_ROOT", source_root)
    return source_root


class FakeDevice:
    def __init__(
        self,
        context: physical.ReleaseContext,
        ordinal: int,
        *,
        claim_required: Path | None = None,
        fail_first: bool = False,
    ) -> None:
        self.context = context
        self.ordinal = ordinal
        self.claim_required = claim_required
        self.fail_first = fail_first
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
        return physical._identity_expected(  # noqa: SLF001
            self.context, self.ordinal
        )

    def _version(self) -> dict[str, Any]:
        policy = self.action["temperature_policy"]
        if self.ordinal == 1:
            minimum, maximum = self.context.root["profile_contract"][
                "vendor_filename_numeric_tokens"
            ]
        else:
            minimum, maximum = policy["allowed_record_range_c"]
        electrical = self.context.root["profile_contract"][
            "requested_electrical_metadata"
        ]
        recovery_policy = (
            {
                "requested_gate_positive_mv": electrical["gate_positive_mv"],
                "requested_gate_negative_mv": electrical["gate_negative_mv"],
                "requested_full_source_positive_mv": electrical[
                    "full_source_positive_mv"
                ],
                "requested_full_source_negative_mv": electrical[
                    "full_source_negative_mv"
                ],
                "requested_vsh_lv_mv": electrical["intermediate_source_mv"]["vsh_lv"],
                "requested_vsl_lv_mv": electrical["intermediate_source_mv"]["vsl_lv"],
                "requested_vsh_lv2_mv": electrical["intermediate_source_mv"]["vsh_lv2"],
                "requested_vsl_lv2_mv": electrical["intermediate_source_mv"]["vsl_lv2"],
                "requested_frame_rate_hz": electrical["frame_rate_hz"],
                "electrical_values_source": "generated_include_metadata",
                "panel_or_fpl_limits_proven": False,
                "h3_header_binding_proven": False,
            }
            if self.ordinal == 1
            else {
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
            "profile": {
                "profile_id": self.context.profile_id,
                "compiled_profile_count": 1,
                "auto_selected": False,
                "apparent_temperature_min_c": int(minimum),
                "apparent_temperature_max_c": int(maximum),
                **recovery_policy,
            },
            "action_count": 1,
            "startup_refresh": False,
            "raw_ingress": False,
            "retry": False,
            "automatic_chaining": False,
            "profile_switch": False,
        }

    def _manifest(self) -> dict[str, Any]:
        return {
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
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "raw_lut_ingress": False,
            "electrical_parameter_ingress": False,
            "timing_parameter_ingress": False,
            "retry": False,
            "automatic_chaining": False,
            "profile_switch": False,
            "vcom_write": False,
            "vcom_sweep": False,
            "unproven_assumptions": [
                {"id": f"U{index}", "status": "unproven"} for index in range(1, 8)
            ],
        }

    def _status(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-status",
            **self._identity(),
            "profile_id": self.context.profile_id,
            "boot_nonce": self.boot_nonce,
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
            "busy": 1,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        }

    def _report(self) -> dict[str, Any]:
        common = {
            "schema_version": 1,
            "kind": f"{self.binding['kind_prefix']}-report",
            **self._identity(),
            "result": self.executed,
            "driver_called": self.executed,
            "driver_call_count_for_action": 1 if self.executed else 0,
            "no_retry": True,
        }
        if not self.executed:
            return {**common, "terminal_state": "NOT_EXECUTED"}
        atlas_role = "atlas" if self.ordinal == 1 else "white"
        driver = {
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "post_psr_busy_seen": False,
            "pre_command_idle_failure": False,
            "input_fnv1a": contract.atlas.FROZEN_IDENTITIES[atlas_role]["frame"][1],
            "cs1_dtm_fnv1a": contract.atlas.FROZEN_IDENTITIES[atlas_role]["cs1"][1],
            "cs2_dtm_fnv1a": contract.atlas.FROZEN_IDENTITIES[atlas_role]["cs2"][1],
            "busy_trace": {
                "idle_level": 1,
                "post_psr": {
                    "pre_command_idle_ok": True,
                    "wait_exit_level": 1,
                    "assertion_after_idle": False,
                },
                "safe_finish": {
                    "busy_before_pins_low": 1,
                    "busy_after_pins_low": 1,
                    "busy_after_5ms": 1,
                },
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
        return {
            **common,
            "ordinal": self.ordinal,
            "action_id": self.action["hardware_action_id"],
            "terminal_state": "COMPLETE",
            "driver": driver,
        }

    def __call__(
        self, method: str, endpoint: str, headers: Mapping[str, str]
    ) -> physical.HttpResponse:
        if self.claim_required is not None:
            assert self.claim_required.is_file(), "network preceded host claim"
        self.calls.append((method, endpoint, dict(headers)))
        if self.fail_first:
            raise OSError("synthetic network loss")
        leaf = endpoint.rsplit("/", 1)[-1]
        if method == "GET":
            payloads = {
                "version": self._version(),
                "manifest": self._manifest(),
                "status": self._status(),
                "report": self._report(),
            }
            return physical.HttpResponse(200, payloads[leaf])
        assert headers.get("Content-Type") is None
        if leaf == "arm":
            assert "X-EC5-Arm-Nonce" not in headers
            return physical.HttpResponse(
                201,
                {
                    "accepted": True,
                    "armed": True,
                    **self._identity(),
                    "ordinal": self.ordinal,
                    "action_id": self.action["hardware_action_id"],
                    "boot_nonce": self.boot_nonce,
                    "arm_nonce": self.arm_nonce,
                },
            )
        assert leaf == "execute"
        lowered = {key.lower(): value for key, value in headers.items()}
        assert lowered["x-ec5-arm-nonce"] == self.arm_nonce
        self.executed = True
        return physical.HttpResponse(
            202,
            {
                "accepted": True,
                "job_id": self.ordinal,
                **self._identity(),
                "action_id": self.action["hardware_action_id"],
                "execute_consumed": True,
                "no_retry": True,
            },
        )


def _diagnose(
    context: physical.ReleaseContext, ordinal: int
) -> tuple[dict[str, Any], FakeDevice, str]:
    temperature = "25.0"
    fake = FakeDevice(context, ordinal)
    diagnostic = physical.diagnose_j2_off(
        context,
        ordinal,
        operator_temperature_c=temperature,
        operator_screen_state=(
            physical.SCREEN_INITIAL if ordinal == 1 else physical.SCREEN_RECOVERY
        ),
        operator_j2_state="OFF",
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        requester=fake,
    )
    return diagnostic, fake, temperature


@pytest.mark.parametrize("ordinal", (1, 2))
@pytest.mark.parametrize("prefix_chars", (16, 32, 63))
def test_j2_off_diagnostic_rejects_truncated_running_elf_sha256(
    tmp_path: Path, ordinal: int, prefix_chars: int
) -> None:
    context = physical.context_from_root(_release_root(tmp_path, "WF20_25"))
    fake = FakeDevice(context, ordinal)

    def truncated_identity_device(
        method: str, endpoint: str, headers: Mapping[str, str]
    ) -> physical.HttpResponse:
        response = fake(method, endpoint, headers)
        if endpoint.endswith("/version"):
            body = dict(response.body)
            full_digest = body["running_app_elf_sha256"]
            assert isinstance(full_digest, str) and len(full_digest) == 64
            body["running_app_elf_sha256"] = full_digest[:prefix_chars]
            return physical.HttpResponse(response.status, body)
        return response

    with pytest.raises(
        physical.PhysicalOnceError,
        match="version running_app_elf_sha256 identity differs",
    ):
        physical.diagnose_j2_off(
            context,
            ordinal,
            operator_temperature_c="25.0" if ordinal == 1 else "24.0",
            operator_screen_state=(
                physical.SCREEN_INITIAL if ordinal == 1 else physical.SCREEN_RECOVERY
            ),
            operator_j2_state="OFF",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            requester=truncated_identity_device,
        )
    assert fake.calls
    assert all(method == "GET" for method, _endpoint, _headers in fake.calls)


def test_contract_freezes_two_separate_images_u1_u7_and_exact_wait_order() -> None:
    for profile_id in contract.PROFILES:
        root = contract.validate_contract(profile_id)
        row = contract.profile_row(profile_id)
        assert (
            root["vendor_filename_numeric_tokens"]
            == row["vendor_filename_numeric_tokens"]
        )
        assert root["temperature_filename_semantics_proven"] is False
        assert root["experimental_fixed_temperature_guard_c"] == [25.0, 25.0]
        assert root["temperature_compatibility_qualified"] is False
        runtime_policy = next(
            action["temperature_policy"]
            for action in root["actions"]
            if action["ordinal"] == 1
        )
        assert runtime_policy["allowed_c"] == [25.0, 25.0]
        assert runtime_policy["vendor_filename_band_claim"] is False
        separation = root["firmware_separation"]
        assert separation["binary_count"] == 2
        assert separation["runtime_binary_contains_recovery"] is False
        assert separation["recovery_binary_contains_runtime_payload"] is False
        assert (
            separation["runtime_nvs_namespace"] != separation["recovery_nvs_namespace"]
        )
        assert [
            item["id"] for item in root["assumption_acceptance"]["assumptions"]
        ] == [f"U{index}" for index in range(1, 8)]
        sequence = contract.transaction_descriptor(profile_id, contract.ROLE_RUNTIME)[
            "command_contract"
        ]
        assert sequence["global_to_both_exact_order"] == [
            "PSR_5FE9",
            "PWR_FROM_SELECTED_HEADER",
            "IDLE_GATE_AFTER_PWR",
            "PLL_FROM_SELECTED_HEADER",
            "TRES_512X600",
        ]
        assert sequence["per_controller_exact_order"] == [
            "E9_01",
            "IDLE_GATE_AFTER_E9",
            "R20_799",
            "R21_704FF",
        ]
        assert sequence["idle_gate_failure_stops_all_later_commands"] is True


def test_compiled_identity_uses_unique_descriptor_not_binary_opcode_absence(
    tmp_path: Path,
) -> None:
    runtime = _write_image(tmp_path, "WF20_25", contract.ROLE_RUNTIME)
    report = compiled.validate_image(
        "WF20_25",
        contract.ROLE_RUNTIME,
        elf_file=runtime[0],
        binary_file=runtime[1],
        transaction_source_file=runtime[2],
        generated_include_file=runtime[3],
    )
    scope = report["opcode_verification_scope"]
    assert scope["whole_binary_opcode_absence_scan_performed"] is False
    assert scope["arbitrary_payload_byte_values_allowed"] is True

    elf = runtime[0].read_bytes()
    marker = contract.compiled_descriptor_marker(
        "WF20_25", contract.ROLE_RUNTIME
    ).encode("ascii")
    duplicated = elf + b"\0" + marker
    runtime[0].write_bytes(duplicated)
    runtime[1].write_bytes(_binary_for(duplicated))
    with pytest.raises(compiled.RuntimeLutCompiledIdentityError, match="occurrence"):
        compiled.validate_image(
            "WF20_25",
            contract.ROLE_RUNTIME,
            elf_file=runtime[0],
            binary_file=runtime[1],
            transaction_source_file=runtime[2],
            generated_include_file=runtime[3],
        )


@pytest.mark.parametrize(
    "identity_kind",
    ("contract_id", "runtime_action_id", "recovery_action_id"),
)
def test_compiled_identity_requires_current_contract_and_action_ids(
    tmp_path: Path, identity_kind: str
) -> None:
    profile_id = "WF20_25"
    root = contract.validate_contract(profile_id)
    actions = {item["role"]: item for item in root["actions"]}
    required_identity = {
        "contract_id": root["contract_id"],
        "runtime_action_id": actions[contract.ROLE_RUNTIME]["hardware_action_id"],
        "recovery_action_id": actions[contract.ROLE_WHITE]["hardware_action_id"],
    }[identity_kind].encode("ascii")
    runtime = _write_image(tmp_path, profile_id, contract.ROLE_RUNTIME)
    elf = runtime[0].read_bytes()
    assert required_identity in elf
    without_identity = elf.replace(required_identity, b"x" * len(required_identity))
    assert required_identity not in without_identity
    runtime[0].write_bytes(without_identity)
    runtime[1].write_bytes(_binary_for(without_identity))

    with pytest.raises(
        compiled.RuntimeLutCompiledIdentityError,
        match="dedicated identity .* is absent",
    ):
        compiled.validate_image(
            profile_id,
            contract.ROLE_RUNTIME,
            elf_file=runtime[0],
            binary_file=runtime[1],
            transaction_source_file=runtime[2],
            generated_include_file=runtime[3],
        )


@pytest.mark.parametrize(
    "identity_kind",
    ("contract_id", "recovery_action_id"),
)
def test_recovery_compiled_identity_requires_current_contract_and_action_ids(
    tmp_path: Path, identity_kind: str
) -> None:
    profile_id = "WF20_25"
    root = contract.validate_contract(profile_id)
    recovery_action = next(
        item for item in root["actions"] if item["role"] == contract.ROLE_WHITE
    )
    required_identity = {
        "contract_id": root["contract_id"],
        "recovery_action_id": recovery_action["hardware_action_id"],
    }[identity_kind].encode("ascii")
    recovery = _write_image(tmp_path, profile_id, contract.ROLE_WHITE)
    elf = recovery[0].read_bytes()
    assert required_identity in elf
    without_identity = elf.replace(required_identity, b"x" * len(required_identity))
    assert required_identity not in without_identity
    recovery[0].write_bytes(without_identity)
    recovery[1].write_bytes(_binary_for(without_identity))

    with pytest.raises(
        compiled.RuntimeLutCompiledIdentityError,
        match="dedicated identity .* is absent",
    ):
        compiled.validate_image(
            profile_id,
            contract.ROLE_WHITE,
            elf_file=recovery[0],
            binary_file=recovery[1],
            transaction_source_file=recovery[2],
        )


def test_materializer_records_unaccepted_live_prerequisites_only(
    tmp_path: Path,
) -> None:
    root = _release_root(tmp_path, "WF20_25")
    assert "operator_build_acceptance" not in root
    prerequisites = root["live_authorization_prerequisites"]
    risks = prerequisites["risk_declaration"]
    prior = prerequisites["operator_reported_prior_reference"]
    assert prerequisites["accepted_at_materialization"] is False
    assert prerequisites["live_authorized"] is False
    assert prerequisites["fresh_j2_off_diagnostic_required"] is True
    assert prerequisites["diagnostic_bound_authorization_v2_required"] is True
    assert risks["accepted_at_materialization"] is False
    assert risks["acceptance_is_proof"] is False
    assert risks["required_exact_phrase"] == contract.EMPIRICAL_ACCEPTANCE_PHRASE
    assert (
        risks["u1_u7_contract_canonical_sha256"]
        == root["profile_contract"]["assumption_acceptance"]["canonical_sha256"]
    )
    assert [item["id"] for item in risks["unproven_assumptions"]] == [
        f"U{index}" for index in range(1, 8)
    ]
    assert prior["prior_state_id"] == contract.PRIOR_STATE_ID
    assert prior["accepted_at_materialization"] is False
    assert prior["is_fresh_j2_off_diagnostic"] is False
    assert prior["satisfies_live_diagnostic_gate"] is False

    tampered = deepcopy(root)
    tampered["live_authorization_prerequisites"]["accepted_at_materialization"] = True
    tampered = release._seal(  # noqa: SLF001 - adversarial release fixture
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    with pytest.raises(
        release.RuntimeLutReleaseError, match="must not record materialization-time"
    ):
        release.validate_release(tampered)


def test_materialize_cli_exposes_no_acceptance_or_prior_assertion_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        release.main(["materialize", "--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--accept-u1-u7" not in help_text
    assert "--accept-current-prior" not in help_text


def test_two_profile_releases_are_distinct_and_deep_validate(tmp_path: Path) -> None:
    roots = {
        profile_id: _release_root(tmp_path / profile_id, profile_id)
        for profile_id in contract.PROFILES
    }
    reports = {key: release.validate_release(value) for key, value in roots.items()}
    assert reports["WF20_25"]["release_id"] != reports["WF23_25"]["release_id"]
    for profile_id, root in roots.items():
        assert root["profile_id"] == profile_id
        bindings = root["action_artifact_bindings"]
        assert (
            bindings[0]["firmware_binary_sha256"]
            != bindings[1]["firmware_binary_sha256"]
        )
        assert bindings[0]["environment"] != bindings[1]["environment"]
        assert bindings[0]["nvs_namespace"] != bindings[1]["nvs_namespace"]


def test_release_binds_exact_host_execution_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = _isolated_host_execution_sources(tmp_path, monkeypatch)
    root = _release_root(tmp_path / "build", "WF20_25")
    report = release.validate_release(root)
    bundle = root["host_execution_bundle"]
    assert report["host_execution_bundle_sha256"] == bundle["canonical_sha256"]
    assert [item["relative_path"] for item in bundle["files"]] == list(
        release.HOST_EXECUTION_SOURCE_RELATIVE_PATHS
    )
    for item in bundle["files"]:
        payload = (source_root / Path(item["relative_path"])).read_bytes()
        assert item["bytes"] == len(payload)
        assert item["sha256"] == contract.sha256(payload)
    unsigned = {
        key: value for key, value in bundle.items() if key != "canonical_sha256"
    }
    assert bundle["canonical_sha256"] == contract.sha256(unsigned)


def test_deep_release_validation_rejects_host_source_byte_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = _isolated_host_execution_sources(tmp_path, monkeypatch)
    root = _release_root(tmp_path / "build", "WF20_25")
    target = source_root / release.HOST_EXECUTION_SOURCE_RELATIVE_PATHS[0]
    target.write_bytes(target.read_bytes() + b"\n# synthetic source tamper\n")
    with pytest.raises(release.RuntimeLutReleaseError, match="source bundle differs"):
        release.validate_release(root)
    runtime_files = root["compiled_images"]["runtime"]["firmware"]
    recovery_files = root["compiled_images"]["factory_otp_white"]["firmware"]
    rematerialized = release.materialize_release(
        "WF20_25",
        runtime_elf=Path(runtime_files["elf"]["path"]),
        runtime_binary=Path(runtime_files["binary"]["path"]),
        runtime_source=Path(runtime_files["transaction_source"]["path"]),
        generated_include=Path(runtime_files["generated_include"]["path"]),
        recovery_elf=Path(recovery_files["elf"]["path"]),
        recovery_binary=Path(recovery_files["binary"]["path"]),
        recovery_source=Path(recovery_files["transaction_source"]["path"]),
    )
    assert rematerialized["release_id"] != root["release_id"]
    assert (
        rematerialized["host_execution_bundle"]["canonical_sha256"]
        != root["host_execution_bundle"]["canonical_sha256"]
    )


def test_deep_release_validation_rejects_host_source_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = _isolated_host_execution_sources(tmp_path, monkeypatch)
    root = _release_root(tmp_path / "build", "WF20_25")
    target = source_root / release.HOST_EXECUTION_SOURCE_RELATIVE_PATHS[0]
    replacement = source_root / "physical-once-replacement.py"
    replacement.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(replacement)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"file symlinks are unavailable: {error}")
    with pytest.raises(release.RuntimeLutReleaseError, match="contains a symlink"):
        release.validate_release(root)


def test_fake_device_two_actions_are_separate_claimed_bodyless_once(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF23_25"))
    registry = tmp_path / "claims"

    diagnostic1, diagnostic_fake1, temperature = _diagnose(context, 1)
    assert [method for method, _endpoint, _headers in diagnostic_fake1.calls] == [
        "GET"
    ] * 4
    assert diagnostic1["j2_is_device_measured"] is False
    claim1 = physical._claim_path(context, 1, registry)  # noqa: SLF001
    run_fake1 = FakeDevice(context, 1, claim_required=claim1)
    result1 = physical.run_once(
        context,
        1,
        operator_temperature_c=temperature,
        operator_j2_state="ON",
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        authorization=physical.required_authorization(
            context, 1, temperature, diagnostic1
        ),
        diagnostic=diagnostic1,
        requester=run_fake1,
        claim_registry=registry,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )
    assert result1["arm_posts"] == result1["execute_posts"] == 1
    posts1 = [item for item in run_fake1.calls if item[0] == "POST"]
    assert [item[1].rsplit("/", 1)[-1] for item in posts1] == ["arm", "execute"]
    assert not physical._claim_path(context, 2, registry).exists()  # noqa: SLF001

    diagnostic2, _diagnostic_fake2, _ = _diagnose(context, 2)
    claim2 = physical._claim_path(context, 2, registry)  # noqa: SLF001
    run_fake2 = FakeDevice(context, 2, claim_required=claim2)
    token2 = physical.required_authorization(context, 2, temperature, diagnostic2)
    assert token2 != physical.required_authorization(
        context, 1, temperature, diagnostic1
    )
    result2 = physical.run_once(
        context,
        2,
        operator_temperature_c=temperature,
        operator_j2_state="ON",
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        authorization=token2,
        diagnostic=diagnostic2,
        requester=run_fake2,
        claim_registry=registry,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )
    assert result2["role"] == contract.ROLE_WHITE
    assert [item[0] for item in run_fake2.calls].count("POST") == 2


def test_temperature_token_and_tamper_fail_before_claim_or_network(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    diagnostic, _fake, temperature = _diagnose(context, 1)
    registry = tmp_path / "claims"
    never = FakeDevice(context, 1)
    with pytest.raises(physical.PhysicalOnceError, match="outside"):
        physical.run_once(
            context,
            1,
            operator_temperature_c="37.0",
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization="bad",
            diagnostic=diagnostic,
            requester=never,
            claim_registry=registry,
        )
    with pytest.raises(physical.PhysicalOnceError, match="authorization"):
        physical.run_once(
            context,
            1,
            operator_temperature_c=temperature,
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization="bad",
            diagnostic=diagnostic,
            requester=never,
            claim_registry=registry,
        )
    assert never.calls == []
    assert not registry.exists()
    current_token = physical.required_authorization(context, 1, temperature, diagnostic)
    diagnostic_binding = (
        f"__DIAGNOSTIC_{diagnostic['integrity']['canonical_sha256'].upper()}"
        f"__BOOT_NONCE_{diagnostic['boot_nonce'].upper()}"
    )
    legacy_unbound_token = current_token.replace(
        "AUTHORIZE_V2_", "AUTHORIZE_", 1
    ).replace(diagnostic_binding, "", 1)
    with pytest.raises(physical.PhysicalOnceError, match="authorization"):
        physical.run_once(
            context,
            1,
            operator_temperature_c=temperature,
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=legacy_unbound_token,
            diagnostic=diagnostic,
            requester=never,
            claim_registry=registry,
        )
    assert never.calls == []
    assert not registry.exists()
    recovery_fake = FakeDevice(context, 2)
    recovery_diagnostic = physical.diagnose_j2_off(
        context,
        2,
        operator_temperature_c="37.0",
        operator_screen_state=physical.SCREEN_RECOVERY,
        operator_j2_state="OFF",
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        requester=recovery_fake,
    )
    recovery_token = physical.required_authorization(
        context, 2, "37.0", recovery_diagnostic
    )
    assert "TEMP_C_37P0" in recovery_token
    with pytest.raises(physical.PhysicalOnceError, match="observed-ceiling"):
        physical.required_authorization(context, 2, "37.1", recovery_diagnostic)


def test_authorization_v2_binds_exact_sealed_diagnostic_and_boot_nonce(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    diagnostic, fake, temperature = _diagnose(context, 1)
    fake.calls.clear()
    registry = tmp_path / "claims"
    report = physical.offline_authorization(
        context,
        1,
        selected_profile_id="WF20_25",
        operator_temperature_c=temperature,
        empirical_acceptance=contract.EMPIRICAL_ACCEPTANCE_PHRASE,
        operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
        diagnostic=diagnostic,
        claim_registry=registry,
    )
    token = report["authorization_token"]
    diagnostic_sha = diagnostic["integrity"]["canonical_sha256"]
    assert token.startswith("AUTHORIZE_V2_ONE_VISIBLE_EC5_WF20_25_")
    assert f"__DIAGNOSTIC_{diagnostic_sha.upper()}" in token
    assert f"__BOOT_NONCE_{diagnostic['boot_nonce'].upper()}" in token
    assert report["u1_u7"] == list(contract.U1_U7)
    assert report["u1_u7_exact_phrase"] == contract.EMPIRICAL_ACCEPTANCE_PHRASE
    assert report["operator_monitoring_confirmation"] == (
        contract.OPERATOR_MONITORING_CONFIRMATION
    )
    assert report["acceptance_is_proof"] is False
    assert report["offline"] is True
    assert report["live_authorized"] is False
    assert report["claims_created"] is False
    assert report["network_requests"] == report["post_requests"] == 0
    assert fake.calls == []
    assert not registry.exists()

    other_unsigned = {
        key: value for key, value in diagnostic.items() if key != "integrity"
    }
    other_unsigned["boot_nonce"] = "1111111111111111"
    other_diagnostic = physical._seal(other_unsigned)  # noqa: SLF001
    other_token = physical.required_authorization(
        context, 1, temperature, other_diagnostic
    )
    assert other_token != token
    with pytest.raises(physical.PhysicalOnceError, match="integrity"):
        physical.required_authorization(
            context,
            1,
            temperature,
            {**diagnostic, "boot_nonce": "2222222222222222"},
        )


def test_offline_authorize_cli_requires_exact_inputs_and_never_claims_or_networks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _release_root(tmp_path / "build", "WF23_25")
    context = physical.context_from_root(root)
    release_file = tmp_path / "release.json"
    diagnostic_file = tmp_path / "diagnostic.json"
    registry = tmp_path / "claims"
    release.write_new_release(release_file, root)
    diagnostic, fake, temperature = _diagnose(context, 1)
    diagnostic_file.write_bytes(contract.canonical_json_bytes(diagnostic) + b"\n")
    fake.calls.clear()

    def forbid_requester(_base_url: str, _timeout_s: float) -> physical.Requester:
        raise AssertionError("offline authorize attempted to construct HTTP requester")

    monkeypatch.setattr(physical, "_http_requester", forbid_requester)
    code = physical.main(
        [
            "authorize",
            "--release",
            str(release_file),
            "--profile",
            "WF23_25",
            "--ordinal",
            "1",
            "--temperature-c",
            temperature,
            "--diagnostic",
            str(diagnostic_file),
            "--claim-registry",
            str(registry),
            "--accept-u1-u7",
            contract.EMPIRICAL_ACCEPTANCE_PHRASE,
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
        ]
    )
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["authorization_token"] == physical.required_authorization(
        context, 1, temperature, diagnostic
    )
    assert fake.calls == []
    assert not registry.exists()


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"selected_profile_id": "WF23_25"}, "selected profile"),
        ({"empirical_acceptance": "accepted"}, "U1-U7"),
        ({"operator_monitoring_state": "ready"}, "monitoring"),
    ),
)
def test_offline_authorize_rejects_inexact_operator_inputs_without_side_effects(
    tmp_path: Path,
    override: Mapping[str, str],
    message: str,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    diagnostic, fake, temperature = _diagnose(context, 1)
    fake.calls.clear()
    registry = tmp_path / "claims"
    kwargs: dict[str, Any] = {
        "selected_profile_id": "WF20_25",
        "operator_temperature_c": temperature,
        "empirical_acceptance": contract.EMPIRICAL_ACCEPTANCE_PHRASE,
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "diagnostic": diagnostic,
        "claim_registry": registry,
        **override,
    }
    with pytest.raises(physical.PhysicalOnceError, match=message):
        physical.offline_authorization(context, 1, **kwargs)
    assert fake.calls == []
    assert not registry.exists()


def test_recovery_offline_authorize_requires_exact_runtime_claim(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF23_25"))
    registry = tmp_path / "claims"
    runtime_diagnostic, _runtime_fake, temperature = _diagnose(context, 1)
    recovery_diagnostic, recovery_fake, _ = _diagnose(context, 2)
    recovery_fake.calls.clear()
    kwargs = {
        "selected_profile_id": "WF23_25",
        "operator_temperature_c": temperature,
        "empirical_acceptance": contract.EMPIRICAL_ACCEPTANCE_PHRASE,
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "diagnostic": recovery_diagnostic,
        "claim_registry": registry,
    }
    with pytest.raises(physical.PhysicalOnceError, match="prior runtime"):
        physical.offline_authorization(context, 2, **kwargs)  # type: ignore[arg-type]
    assert not registry.exists()
    runtime_token = physical.required_authorization(
        context, 1, temperature, runtime_diagnostic
    )
    physical._create_claim(  # noqa: SLF001
        context,
        1,
        temperature=temperature,
        authorization=runtime_token,
        diagnostic=runtime_diagnostic,
        registry=registry,
    )
    report = physical.offline_authorization(
        context,
        2,
        **kwargs,  # type: ignore[arg-type]
    )
    assert report["ordinal"] == 2
    assert recovery_fake.calls == []


def test_network_failure_occurs_after_claim_and_is_permanent_no_retry(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    diagnostic, _fake, temperature = _diagnose(context, 1)
    registry = tmp_path / "claims"
    claim = physical._claim_path(context, 1, registry)  # noqa: SLF001
    failing = FakeDevice(context, 1, claim_required=claim, fail_first=True)
    kwargs = {
        "operator_temperature_c": temperature,
        "operator_j2_state": "ON",
        "operator_monitoring_state": contract.OPERATOR_MONITORING_CONFIRMATION,
        "authorization": physical.required_authorization(
            context, 1, temperature, diagnostic
        ),
        "diagnostic": diagnostic,
        "requester": failing,
        "claim_registry": registry,
        "poll_interval_seconds": 0,
    }
    with pytest.raises(physical.PhysicalOnceUnknown, match="claim consumed"):
        physical.run_once(context, 1, **kwargs)  # type: ignore[arg-type]
    assert claim.is_file()
    call_count = len(failing.calls)
    with pytest.raises(physical.PhysicalOnceError, match="already has"):
        physical.run_once(context, 1, **kwargs)  # type: ignore[arg-type]
    assert len(failing.calls) == call_count


def test_j2_off_preflight_fails_closed_on_each_low_output_gpio_drift(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    fake = FakeDevice(context, 1)
    status = fake._status()  # noqa: SLF001 - exact fake preflight contract
    assert (
        physical._expect_status(  # noqa: SLF001
            status, context, 1, boot_nonce=None
        )
        == fake.boot_nonce
    )
    for gpio in ("sck", "dc", "mosi"):
        tampered = fake._status()  # noqa: SLF001
        tampered[gpio] = 1
        with pytest.raises(physical.PhysicalOnceError, match="virgin ready state"):
            physical._expect_status(  # noqa: SLF001
                tampered, context, 1, boot_nonce=None
            )


def test_terminal_driver_evidence_fails_closed_on_busy_gpio_or_dtm_drift(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    fake = FakeDevice(context, 1)
    fake.executed = True
    report = fake._report()  # noqa: SLF001 - exact fake terminal contract
    assert physical._terminal_report(report, context, 1) is True  # noqa: SLF001
    for path, replacement in (
        (("driver", "sequence_ok"), False),
        (("driver", "pon_busy_seen"), False),
        (("driver", "cs2_dtm_fnv1a"), 0),
        (("driver", "busy_trace", "post_psr", "pre_command_idle_ok"), False),
        (("driver", "busy_trace", "final_gpio", "cs2"), 1),
        (("driver", "busy_trace", "final_gpio", "sck"), 1),
        (("driver", "busy_trace", "final_gpio", "dc"), 1),
        (("driver", "busy_trace", "final_gpio", "mosi"), 1),
    ):
        tampered = fake._report()  # noqa: SLF001
        target: dict[str, Any] = tampered
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
        with pytest.raises(physical.PhysicalOnceUnknown):
            physical._terminal_report(tampered, context, 1)  # noqa: SLF001


def test_recovery_requires_runtime_claim_and_describe_is_offline(
    tmp_path: Path,
) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF23_25"))
    summary = physical.describe(context)
    assert summary["network_requests"] == summary["post_requests"] == 0
    assert summary["claims_created"] is False
    diagnostic, fake, temperature = _diagnose(context, 2)
    with pytest.raises(physical.PhysicalOnceError, match="prior runtime"):
        physical.run_once(
            context,
            2,
            operator_temperature_c=temperature,
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=physical.required_authorization(
                context, 2, temperature, diagnostic
            ),
            diagnostic=diagnostic,
            requester=fake,
            claim_registry=tmp_path / "claims",
        )


def test_real_urllib_post_is_bodyless_and_ignores_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            length_text = self.headers.get("Content-Length")
            length = int(length_text or "0")
            observed.update(
                {
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type"),
                    "transfer_encoding": self.headers.get("Transfer-Encoding"),
                    "content_length": length_text,
                    "body": self.rfile.read(length),
                }
            )
            payload = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
        requester = physical._http_requester(  # noqa: SLF001
            f"http://127.0.0.1:{server.server_port}", 2.0
        )
        response = requester("POST", "/arm", {"X-EC5-Intent": "test"})
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2.0)
    assert response.status == 200
    assert observed == {
        "path": "/arm",
        "content_type": None,
        "transfer_encoding": None,
        "content_length": "0",
        "body": b"",
    }


@pytest.mark.parametrize(
    "base_url",
    (
        "http://192.168.1.14:bad",
        "http://192.168.1.14:99999",
        "http://192.168.1.14:0",
        "http://192.168.1.14:",
        "http://192.168.1.14:/",
    ),
)
def test_http_requester_rejects_invalid_port_before_opener_or_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
) -> None:
    opener_calls = 0

    def forbidden_opener(*_args: object, **_kwargs: object) -> object:
        nonlocal opener_calls
        opener_calls += 1
        raise AssertionError("invalid transport reached opener construction")

    monkeypatch.setattr(physical.urlrequest, "build_opener", forbidden_opener)
    with pytest.raises(physical.PhysicalOnceError, match="port"):
        physical._http_requester(base_url, 5.0)  # noqa: SLF001
    assert opener_calls == 0
    assert not (tmp_path / "claims").exists()


@pytest.mark.parametrize("timeout", (-1.0, 0.0, float("nan"), float("inf"), True))
def test_http_requester_rejects_invalid_timeout_before_opener_or_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timeout: object,
) -> None:
    opener_calls = 0

    def forbidden_opener(*_args: object, **_kwargs: object) -> object:
        nonlocal opener_calls
        opener_calls += 1
        raise AssertionError("invalid transport reached opener construction")

    monkeypatch.setattr(physical.urlrequest, "build_opener", forbidden_opener)
    with pytest.raises(physical.PhysicalOnceError, match="timeout"):
        physical._http_requester(  # type: ignore[arg-type]  # noqa: SLF001
            "http://192.168.1.14", timeout
        )
    assert opener_calls == 0
    assert not (tmp_path / "claims").exists()


@pytest.mark.parametrize(
    ("base_url", "timeout"),
    (
        ("http://192.168.1.14:bad", "5.0"),
        ("http://192.168.1.14", "-1"),
    ),
)
def test_run_cli_rejects_transport_before_claim_or_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base_url: str,
    timeout: str,
) -> None:
    root = _release_root(tmp_path / "build", "WF20_25")
    context = physical.context_from_root(root)
    release_file = tmp_path / "release.json"
    diagnostic_file = tmp_path / "diagnostic.json"
    result_file = tmp_path / "result.json"
    registry = tmp_path / "claims"
    release.write_new_release(release_file, root)
    diagnostic, fake, temperature = _diagnose(context, 1)
    diagnostic_file.write_bytes(contract.canonical_json_bytes(diagnostic) + b"\n")
    fake.calls.clear()
    code = physical.main(
        [
            "run",
            "--release",
            str(release_file),
            "--ordinal",
            "1",
            "--temperature-c",
            temperature,
            "--confirm-j2",
            "ON",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--authorization",
            physical.required_authorization(context, 1, temperature, diagnostic),
            "--diagnostic",
            str(diagnostic_file),
            "--base-url",
            base_url,
            "--timeout-s",
            timeout,
            "--claim-registry",
            str(registry),
            "--output",
            str(result_file),
        ]
    )
    assert code == 2
    assert "runtime-LUT physical-once error" in capsys.readouterr().err
    assert fake.calls == []
    assert not registry.exists()
    assert not result_file.exists()


def test_output_reservation_is_exclusive_held_and_detects_identity_drift(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence" / "result.json"
    reservation = physical._reserve_output(  # noqa: SLF001
        output,
        label="test result",
        binding={"release_id": "a" * 64, "ordinal": 1},
    )
    try:
        initial = json.loads(output.read_text(encoding="utf-8"))
        assert initial["state"] == "PRECLAIM_RESERVED"
        assert initial["created_before_claim"] is True
        assert initial["created_before_network"] is True
        with pytest.raises(physical.PhysicalOnceError, match="already exists"):
            physical._reserve_output(  # noqa: SLF001
                output,
                label="test result",
                binding={"release_id": "a" * 64, "ordinal": 1},
            )
        original_identity = reservation.identity
        reservation.identity = (original_identity[0], original_identity[1] + 1)
        with pytest.raises(physical.PhysicalOnceError, match="identity changed"):
            reservation.finalize(physical._seal({"terminal": True}))  # noqa: SLF001
        assert json.loads(output.read_text(encoding="utf-8")) == initial
    finally:
        reservation.close()


def test_output_reservation_rejects_parent_file_symlinks_and_unwritable_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("x", encoding="ascii")
    with pytest.raises(physical.PhysicalOnceError, match="not a directory"):
        physical._reserve_output(  # noqa: SLF001
            parent_file / "result.json", label="test result", binding={}
        )

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError:
        pass
    else:
        with pytest.raises(physical.PhysicalOnceError, match="symlink"):
            physical._reserve_output(  # noqa: SLF001
                linked_parent / "result.json", label="test result", binding={}
            )

    denied = tmp_path / "denied.json"
    original_open = Path.open

    def deny_target(path: Path, *args: object, **kwargs: object) -> Any:
        if Path(path) == denied:
            raise PermissionError("synthetic read-only destination")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_target)
    with pytest.raises(physical.PhysicalOnceError, match="could not reserve"):
        physical._reserve_output(  # noqa: SLF001
            denied, label="test result", binding={}
        )


def test_diagnose_cli_reserves_output_before_first_get_and_finalizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _release_root(tmp_path / "build", "WF20_25")
    context = physical.context_from_root(root)
    release_file = tmp_path / "release.json"
    output = tmp_path / "diagnostic.json"
    release.write_new_release(release_file, root)
    fake = FakeDevice(context, 1)

    def requester(
        method: str, endpoint: str, headers: Mapping[str, str]
    ) -> physical.HttpResponse:
        reserved = json.loads(output.read_text(encoding="utf-8"))
        assert reserved["state"] == "PRECLAIM_RESERVED"
        return fake(method, endpoint, headers)

    monkeypatch.setattr(
        physical, "_http_requester", lambda _base_url, _timeout_s: requester
    )
    code = physical.main(
        [
            "diagnose",
            "--release",
            str(release_file),
            "--ordinal",
            "1",
            "--temperature-c",
            "25.0",
            "--screen-state",
            physical.SCREEN_INITIAL,
            "--confirm-j2",
            "OFF",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--base-url",
            "http://192.168.1.14",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    assert len(fake.calls) == 4
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["kind"] == physical.DIAGNOSTIC_KIND
    assert json.loads(capsys.readouterr().out) == stored


def test_run_cli_reserves_before_claim_and_get_then_finalizes_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _release_root(tmp_path / "build", "WF23_25")
    context = physical.context_from_root(root)
    release_file = tmp_path / "release.json"
    diagnostic_file = tmp_path / "diagnostic.json"
    result_file = tmp_path / "result.json"
    registry = tmp_path / "claims"
    release.write_new_release(release_file, root)
    diagnostic, _diagnostic_fake, temperature = _diagnose(context, 1)
    diagnostic_file.write_bytes(contract.canonical_json_bytes(diagnostic) + b"\n")
    claim = physical._claim_path(context, 1, registry)  # noqa: SLF001
    fake = FakeDevice(context, 1, claim_required=claim)

    def requester(
        method: str, endpoint: str, headers: Mapping[str, str]
    ) -> physical.HttpResponse:
        reserved = json.loads(result_file.read_text(encoding="utf-8"))
        assert reserved["state"] == "PRECLAIM_RESERVED"
        return fake(method, endpoint, headers)

    monkeypatch.setattr(
        physical, "_http_requester", lambda _base_url, _timeout_s: requester
    )
    monkeypatch.setattr(physical, "POST_EXECUTE_SETTLE_SECONDS", 0.0)
    code = physical.main(
        [
            "run",
            "--release",
            str(release_file),
            "--ordinal",
            "1",
            "--temperature-c",
            temperature,
            "--confirm-j2",
            "ON",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--authorization",
            physical.required_authorization(context, 1, temperature, diagnostic),
            "--diagnostic",
            str(diagnostic_file),
            "--base-url",
            "http://192.168.1.14",
            "--claim-registry",
            str(registry),
            "--poll-interval-seconds",
            "0",
            "--output",
            str(result_file),
        ]
    )
    assert code == 0
    assert claim.is_file()
    stored = json.loads(result_file.read_text(encoding="utf-8"))
    assert stored["kind"] == physical.RESULT_KIND
    assert stored["outcome"] == "success"
    assert json.loads(capsys.readouterr().out) == stored
    assert [item[0] for item in fake.calls].count("POST") == 2


def test_cli_failure_finalizes_reserved_attempt_without_hiding_claim_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _release_root(tmp_path / "build", "WF20_25")
    context = physical.context_from_root(root)
    release_file = tmp_path / "release.json"
    diagnostic_file = tmp_path / "diagnostic.json"
    result_file = tmp_path / "result.json"
    registry = tmp_path / "claims"
    release.write_new_release(release_file, root)
    diagnostic, _diagnostic_fake, temperature = _diagnose(context, 1)
    diagnostic_file.write_bytes(contract.canonical_json_bytes(diagnostic) + b"\n")
    claim = physical._claim_path(context, 1, registry)  # noqa: SLF001
    fake = FakeDevice(context, 1, claim_required=claim, fail_first=True)
    monkeypatch.setattr(physical, "_http_requester", lambda _base_url, _timeout_s: fake)
    code = physical.main(
        [
            "run",
            "--release",
            str(release_file),
            "--ordinal",
            "1",
            "--temperature-c",
            temperature,
            "--confirm-j2",
            "ON",
            "--confirm-monitors",
            contract.OPERATOR_MONITORING_CONFIRMATION,
            "--authorization",
            physical.required_authorization(context, 1, temperature, diagnostic),
            "--diagnostic",
            str(diagnostic_file),
            "--base-url",
            "http://192.168.1.14",
            "--claim-registry",
            str(registry),
            "--output",
            str(result_file),
        ]
    )
    assert code == 3
    assert claim.is_file()
    stored = json.loads(result_file.read_text(encoding="utf-8"))
    assert stored["kind"] == physical.OUTPUT_ATTEMPT_KIND
    assert stored["state"] == "TERMINAL_UNKNOWN_CLAIM_MAY_BE_CONSUMED"
    assert stored["retry_allowed"] is False
    assert "outcome UNKNOWN" in capsys.readouterr().err


def test_real_urllib_redirect_is_not_followed() -> None:
    redirected_requests = 0

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            nonlocal redirected_requests
            redirected_requests += 1
            payload = b'{"unexpected":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Redirector(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            payload = b'{"redirect":true}'
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{destination.server_port}/leak"
            )
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    redirector = ThreadingHTTPServer(("127.0.0.1", 0), Redirector)
    workers = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (destination, redirector)
    ]
    for worker in workers:
        worker.start()
    try:
        requester = physical._http_requester(  # noqa: SLF001
            f"http://127.0.0.1:{redirector.server_port}", 2.0
        )
        response = requester("GET", "/version", {"X-EC5-Action-Id": "secret"})
    finally:
        destination.shutdown()
        redirector.shutdown()
        destination.server_close()
        redirector.server_close()
        for worker in workers:
            worker.join(timeout=2.0)
    assert response.status == 302
    assert redirected_requests == 0
    with pytest.raises(physical.PhysicalOnceError, match="literal IPv4"):
        physical._http_requester("http://localhost", 1.0)  # noqa: SLF001
    with pytest.raises(physical.PhysicalOnceError, match="private"):
        physical._http_requester("http://8.8.8.8", 1.0)  # noqa: SLF001


def test_delayed_real_http_report_retries_get_only_never_post(tmp_path: Path) -> None:
    context = physical.context_from_root(_release_root(tmp_path / "build", "WF20_25"))
    registry = tmp_path / "claims"
    claim = physical._claim_path(context, 1, registry)  # noqa: SLF001
    fake = FakeDevice(context, 1)
    delayed_reports = 0

    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str) -> None:
            nonlocal delayed_reports
            response = fake(method, self.path, dict(self.headers.items()))
            if method == "GET" and self.path.endswith("/report") and fake.executed:
                delayed_reports += 1
                if delayed_reports == 1:
                    # Longer than the client timeout: this models the ESP32
                    # WebServer being unavailable during a blocking refresh.
                    threading.Event().wait(0.6)
            payload = contract.canonical_json_bytes(response.body)
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            self._serve("POST")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        requester = physical._http_requester(  # noqa: SLF001
            f"http://127.0.0.1:{server.server_port}", 0.2
        )
        diagnostic = physical.diagnose_j2_off(
            context,
            1,
            operator_temperature_c="25.0",
            operator_screen_state=physical.SCREEN_INITIAL,
            operator_j2_state="OFF",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            requester=requester,
        )
        fake.claim_required = claim
        result = physical.run_once(
            context,
            1,
            operator_temperature_c="25.0",
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=physical.required_authorization(
                context, 1, "25.0", diagnostic
            ),
            diagnostic=diagnostic,
            requester=requester,
            claim_registry=registry,
            poll_count=4,
            poll_interval_seconds=0,
            sleeper=lambda _seconds: None,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2.0)
    transcript = [(method, endpoint) for method, endpoint, _headers in fake.calls]
    assert transcript.count(("POST", f"{fake.binding['base_route']}/arm")) == 1
    assert transcript.count(("POST", f"{fake.binding['base_route']}/execute")) == 1
    assert result["terminal_report_read_errors"] == 1
    assert result["terminal_report_get_requests"] == 2


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_legacy_release_without_host_execution_bundle_is_non_executable(
    profile_id: str,
) -> None:
    release_file = LEGACY_UNBOUND_RELEASE_DIR / f"{profile_id}-release.json"
    if not release_file.is_file():
        pytest.skip("legacy unbound release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError, match="host execution source bundle is absent"
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_v2_release_with_materialization_acceptance_field_is_non_executable(
    profile_id: str,
) -> None:
    release_file = LEGACY_FALSE_ACCEPTANCE_RELEASE_DIR / f"{profile_id}-release.json"
    if not release_file.is_file():
        pytest.skip("superseded V2 release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError,
        match="live authorization prerequisites are absent",
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_v3_release_with_sdk_truncated_running_elf_contract_is_superseded(
    profile_id: str,
) -> None:
    release_file = LEGACY_TRUNCATED_ELF_RELEASE_DIR / f"{profile_id}-release.json"
    if not release_file.is_file():
        pytest.skip("superseded V3 release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError,
        match="host execution source bundle differs",
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_v4_release_with_unproven_filename_band_semantics_is_superseded(
    profile_id: str,
) -> None:
    release_file = (
        LEGACY_APPARENT_TEMPERATURE_BAND_RELEASE_DIR / f"{profile_id}-release.json"
    )
    if not release_file.is_file():
        pytest.skip("superseded V4 release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError,
        match="host execution source bundle differs",
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_v5_release_with_stale_compiled_descriptor_is_superseded(
    profile_id: str,
) -> None:
    release_file = (
        LEGACY_STALE_COMPILED_DESCRIPTOR_RELEASE_DIR / f"{profile_id}-release.json"
    )
    if not release_file.is_file():
        pytest.skip("superseded V5 release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError,
        match="host execution source bundle differs",
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_v6_release_before_compiled_identity_coverage_fix_is_superseded(
    profile_id: str,
) -> None:
    release_file = (
        LEGACY_COMPILED_IDENTITY_COVERAGE_RELEASE_DIR / f"{profile_id}-release.json"
    )
    if not release_file.is_file():
        pytest.skip("superseded V6 release is not present")
    with pytest.raises(
        release.RuntimeLutReleaseError,
        match="host execution source bundle differs",
    ):
        release.load_release(release_file)


@pytest.mark.parametrize("profile_id", contract.PROFILES)
def test_current_real_release_artifacts_and_both_api_roles_pass_when_present(
    tmp_path: Path, profile_id: str
) -> None:
    release_file = REAL_RELEASE_DIR / f"{profile_id}-release.json"
    if not release_file.is_file():
        pytest.skip("current real materialized release is not present")
    context = physical.load_release(release_file)
    report = release.validate_release(context.root)
    expected = REAL_RELEASE_IDENTITIES[profile_id]
    for key, value in expected.items():
        assert report[key] == value
    assert physical.describe(context)["network_requests"] == 0

    registry = tmp_path / "claims"
    temperature = "25.0"
    for ordinal in (1, 2):
        diagnostic, diagnostic_fake, _ = _diagnose(context, ordinal)
        assert [item[0] for item in diagnostic_fake.calls] == ["GET"] * 4
        claim = physical._claim_path(context, ordinal, registry)  # noqa: SLF001
        run_fake = FakeDevice(context, ordinal, claim_required=claim)
        result = physical.run_once(
            context,
            ordinal,
            operator_temperature_c=temperature,
            operator_j2_state="ON",
            operator_monitoring_state=contract.OPERATOR_MONITORING_CONFIRMATION,
            authorization=physical.required_authorization(
                context, ordinal, temperature, diagnostic
            ),
            diagnostic=diagnostic,
            requester=run_fake,
            claim_registry=registry,
            poll_interval_seconds=0,
            sleeper=lambda _seconds: None,
        )
        assert result["outcome"] == "success"
        assert [item[0] for item in run_fake.calls].count("POST") == 2
