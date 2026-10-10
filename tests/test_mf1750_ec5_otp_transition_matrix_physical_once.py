from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
from pathlib import Path
import re
from typing import Any, Mapping

import pytest

from tests import test_mf1750_ec5_color_lab_physical_e2e_independent as color_e2e
from tools import mf1750_ec5_color_lab_physical_once as engine
from tools import mf1750_ec5_otp_transition_matrix_campaign as campaign
from tools import mf1750_ec5_otp_transition_matrix_contract as contract
from tools import mf1750_ec5_otp_transition_matrix_physical_once as physical


ROOT = Path(__file__).resolve().parents[1]
RELEASE = (
    ROOT
    / ".test-output/hardware/"
    "MF1750_EC5_OTP_TRANSITION_MATRIX_RELEASE_OFFLINE_20260810_V1/"
    "otp-transition-matrix-real-release.json"
)
MAIN = ROOT / "src/ec5_otp_transition_matrix_main.cpp"
BASE_URL = color_e2e.BASE_URL
BOOT_NONCE_A = color_e2e.BOOT_NONCE_A
BOOT_NONCE_B = color_e2e.BOOT_NONCE_B


def _identity(kind: str) -> dict[str, Any]:
    suffix = kind.rsplit("-", 1)[-1]
    return {
        "schema_version": contract.TOP_SCHEMA_VERSION,
        "kind": f"{physical.DEVICE_KIND_PREFIX}-{suffix}",
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }


def _nvs_contract() -> dict[str, Any]:
    return {
        "namespace": contract.NVS_NAMESPACE,
        "key": contract.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": campaign.ACTION_COUNT + 1,
    }


class StrictOtpFakeDevice(color_e2e.StrictFakeDevice):
    """The mature COLOR_LAB fake rebound to the three-action OTP contract."""

    def _status(self) -> dict[str, Any]:
        root = super()._status()
        if self.phase == 0:
            complete = self.next_ordinal == campaign.ACTION_COUNT + 1
            root["state"] = "complete" if complete else "ready"
            root["campaign_complete"] = complete
        return root


@pytest.fixture(scope="module")
def frozen_release() -> tuple[physical.ReleaseContext, dict[str, Any]]:
    """Replay the immutable release once; later calls use the verified snapshot."""

    checked = campaign.validate_materialized_release(RELEASE)
    release_payload = RELEASE.read_bytes()
    release_root = campaign._decode(  # noqa: SLF001
        release_payload, label="frozen OTP release"
    )
    campaign_file = Path(str(release_root["compiled_campaign"]["file"]))
    campaign_root = campaign._decode(  # noqa: SLF001
        campaign_file.read_bytes(), label="frozen OTP campaign"
    )
    context = physical.ReleaseContext(
        release_file=RELEASE.resolve(),
        release_root=release_root,
        release_file_sha256=campaign.sha256(release_payload),
        release_canonical_sha256=str(checked["canonical_sha256"]),
        campaign_file=campaign_file.resolve(),
        campaign_root=campaign_root,
        actions=tuple(deepcopy(campaign_root["actions"])),
        execution_eligible=True,
        formal_u07_registry=Path(
            str(release_root["formal_u07_claim_absence"]["registry"])
        ).resolve(),
    )
    physical._exact_release_gate(context)  # noqa: SLF001
    return context, checked


@pytest.fixture
def offline_contract(
    frozen_release: tuple[physical.ReleaseContext, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> physical.ReleaseContext:
    context, checked = frozen_release
    expected_release = context.release_file
    expected_sha = context.release_file_sha256

    def cached_release_validation(path: Path) -> dict[str, Any]:
        resolved = Path(path).resolve(strict=True)
        payload = resolved.read_bytes()
        if resolved != expected_release or campaign.sha256(payload) != expected_sha:
            raise campaign.OtpTransitionMatrixCampaignError(
                "offline red-team cache refuses a different release"
            )
        return deepcopy(checked)

    monkeypatch.setattr(
        campaign, "validate_materialized_release", cached_release_validation
    )
    monkeypatch.setattr(color_e2e, "campaign", campaign)
    monkeypatch.setattr(color_e2e, "contract", contract)
    monkeypatch.setattr(color_e2e, "physical", engine)
    monkeypatch.setattr(color_e2e, "_identity", _identity)
    monkeypatch.setattr(color_e2e, "_nvs_contract", _nvs_contract)
    return context


def _diagnose(
    context: physical.ReleaseContext,
    device: StrictOtpFakeDevice,
    registry: Path,
    evidence_file: Path,
) -> dict[str, Any]:
    device.driver_powered = False
    diagnostic = physical.diagnose_j2_off(
        context,
        BASE_URL,
        evidence_file=evidence_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    assert physical.validate_j2_off_diagnostic(
        context, evidence_file, claim_registry=registry
    ) == diagnostic
    assert diagnostic["network"] == {"get_requests": 4, "post_requests": 0}
    assert diagnostic["snapshot"]["status"]["cursor_raw"] == 1
    assert diagnostic["snapshot"]["status"]["busy"] == 0
    assert diagnostic["snapshot"]["status"]["persistent_key_present"] is False
    assert not registry.exists()
    return diagnostic


def _run(
    context: physical.ReleaseContext,
    device: StrictOtpFakeDevice,
    registry: Path,
    ordinal: int,
    result_file: Path,
    *,
    diagnostic_file: Path | None = None,
    prior_result_file: Path | None = None,
    prior_observation_file: Path | None = None,
) -> dict[str, Any]:
    device.driver_powered = True
    return physical.run_once(
        context,
        BASE_URL,
        ordinal,
        authorization=physical.required_authorization(context, ordinal),
        result_file=result_file,
        claim_registry=registry,
        prior_result_file=prior_result_file,
        prior_observation_file=prior_observation_file,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=36.5,
        requester=device,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )


def _observe(
    context: physical.ReleaseContext,
    registry: Path,
    ordinal: int,
    result_file: Path,
    observation_file: Path,
) -> dict[str, Any]:
    role = str(context.actions[ordinal - 1]["role"])
    report = {
        contract.ROLE_PRIMER: "primer: eight old-state rows verified",
        contract.ROLE_TARGET: "target: 64 old-to-new cells inspected",
        contract.ROLE_WHITE: "recovery: full clean white verified",
    }[role]
    observation = physical.finalize_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=registry,
        operator_report=report,
        temperature_c=36.5,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=role == contract.ROLE_WHITE,
        confirm_map_fidelity=role == contract.ROLE_PRIMER,
    )
    assert physical.validate_observation(
        context,
        observation_file,
        result_file=result_file,
        claim_registry=registry,
    ) == observation
    return observation


def _complete_first_action(
    context: physical.ReleaseContext, tmp_path: Path
) -> tuple[StrictOtpFakeDevice, Path, Path, Path]:
    registry = tmp_path / "claims"
    device = StrictOtpFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)
    result_file = tmp_path / "ordinal-1-result.json"
    result = _run(
        context,
        device,
        registry,
        1,
        result_file,
        diagnostic_file=diagnostic_file,
    )
    assert result["outcome"] == "complete_pass", result["error"]
    observation_file = tmp_path / "ordinal-1-observation.json"
    _observe(context, registry, 1, result_file, observation_file)
    return device, registry, result_file, observation_file


def test_full_three_action_offline_e2e_is_one_shot_and_same_boot(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    registry = tmp_path / "claims"
    device = StrictOtpFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)

    results: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    result_files: list[Path] = []
    observation_files: list[Path] = []
    for ordinal in range(1, campaign.ACTION_COUNT + 1):
        result_file = tmp_path / f"ordinal-{ordinal}-result.json"
        observation_file = tmp_path / f"ordinal-{ordinal}-observation.json"
        result = _run(
            context,
            device,
            registry,
            ordinal,
            result_file,
            diagnostic_file=diagnostic_file if ordinal == 1 else None,
            prior_result_file=result_files[-1] if result_files else None,
            prior_observation_file=(
                observation_files[-1] if observation_files else None
            ),
        )
        assert result["outcome"] == "complete_pass", result["error"]
        assert result["preflight"]["boot_nonce"] == BOOT_NONCE_A
        assert result["network"]["get_requests"] == 7
        assert result["network"]["arm_posts"] == 1
        assert result["network"]["execute_posts"] == 1
        assert [
            item["path"]
            for item in result["transcript"]
            if item["method"] == "POST"
        ] == [campaign.ENDPOINTS["arm"], campaign.ENDPOINTS["execute"]]
        assert all(
            "Content-Length" not in item["headers"]
            and "Content-Type" not in item["headers"]
            and "Transfer-Encoding" not in item["headers"]
            for item in result["transcript"]
            if item["method"] == "POST"
        )
        observation = _observe(
            context, registry, ordinal, result_file, observation_file
        )
        results.append(result)
        observations.append(observation)
        result_files.append(result_file)
        observation_files.append(observation_file)

    assert [item["action"]["role"] for item in results] == list(contract.ROLES)
    assert [item["ordinal"] for item in observations] == [1, 2, 3]
    assert observations[0]["visual"]["map_fidelity_pass"] is True
    assert observations[1]["operator_report_verbatim"].startswith("target:")
    assert observations[2]["visual"]["full_clean_white"] is True
    assert all(item["sequence_gate_pass"] is True for item in observations)
    assert results[0]["prior_gate"]["kind"] == (
        "exact_finalized_clean_white_anchor_and_j2_off_diagnostic"
    )
    assert [results[index]["prior_gate"]["prior_ordinal"] for index in (1, 2)] == [
        1,
        2,
    ]
    assert all(
        results[index]["prior_gate"]["required_same_boot_nonce"] == BOOT_NONCE_A
        for index in (1, 2)
    )
    assert device.claim_seen_before_arm == [
        str(action["action_id"]) for action in context.actions
    ]
    assert device.driver_action_ordinals == [1, 2, 3]
    assert device.arm_request_count == 3
    assert device.execute_request_count == 3
    assert device.total_driver_call_count == 3
    assert device.next_ordinal == 4
    assert device.phase == 0
    assert device._status()["campaign_complete"] is True
    assert sum(call["method"] == "GET" for call in device.calls) == 25
    assert sum(call["method"] == "POST" for call in device.calls) == 6
    assert len(list(registry.glob("*.json"))) == 3


def test_missing_prior_wrong_order_and_duplicate_fail_before_network(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    device, registry, result1, observation1 = _complete_first_action(
        context, tmp_path
    )

    calls_before = deepcopy(device.calls)
    with pytest.raises(physical.OtpTransitionMatrixPhysicalError, match="requires result"):
        _run(context, device, registry, 2, tmp_path / "missing-prior.json")
    assert device.calls == calls_before
    assert not (tmp_path / "missing-prior.json").exists()

    with pytest.raises(
        physical.OtpTransitionMatrixPhysicalError, match="exact previous complete"
    ):
        _run(
            context,
            device,
            registry,
            3,
            tmp_path / "wrong-order.json",
            prior_result_file=result1,
            prior_observation_file=observation1,
        )
    assert device.calls == calls_before
    assert not (tmp_path / "wrong-order.json").exists()

    with pytest.raises(physical.OtpTransitionMatrixPhysicalError, match="claim.*exists"):
        _run(
            context,
            device,
            registry,
            1,
            tmp_path / "duplicate.json",
            diagnostic_file=tmp_path / "j2-off.json",
        )
    assert device.calls == calls_before
    assert not (tmp_path / "duplicate.json").exists()


@pytest.mark.parametrize(
    ("drift", "message", "expected_gets"),
    (
        ("reboot", "boot nonce differs", 4),
        ("counter", "cumulative count", 3),
    ),
)
def test_reboot_and_counter_drift_stop_during_gets_before_claim_or_post(
    offline_contract: physical.ReleaseContext,
    tmp_path: Path,
    drift: str,
    message: str,
    expected_gets: int,
) -> None:
    context = offline_contract
    registry = tmp_path / "claims"
    device = StrictOtpFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)
    if drift == "reboot":
        device.reboot_before_first_action(BOOT_NONCE_B)
    else:
        device.extra_ready_arm_count = 1
    device.driver_powered = True
    calls_before = len(device.calls)

    with pytest.raises(physical.OtpTransitionMatrixPhysicalError, match=message):
        _run(
            context,
            device,
            registry,
            1,
            tmp_path / "must-not-exist.json",
            diagnostic_file=diagnostic_file,
        )

    new_calls = device.calls[calls_before:]
    assert len(new_calls) == expected_gets
    assert all(call["method"] == "GET" for call in new_calls)
    assert not registry.exists()
    assert device.claim_seen_before_arm == []
    assert device.driver_action_ordinals == []
    assert not (tmp_path / "must-not-exist.json").exists()


def test_anchor_and_release_tamper_fail_before_request_or_claim(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("tamper must fail before requester")

    anchor_root = deepcopy(context.release_root)
    anchor_root["predecessor_binding"]["result"]["file_sha256"] = "0" * 64
    anchor_context = replace(context, release_root=anchor_root)
    with pytest.raises(
        physical.OtpTransitionMatrixPhysicalError,
        match="exact OTP transition-matrix release gate differs",
    ):
        physical.run_once(
            anchor_context,
            BASE_URL,
            1,
            authorization=campaign.required_authorization(context.actions[0]),
            result_file=tmp_path / "anchor-tamper.json",
            claim_registry=tmp_path / "claims",
            j2_off_diagnostic_file=tmp_path / "unused-diagnostic.json",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=36.5,
            requester=requester,
        )

    tampered_release = tmp_path / RELEASE.name
    tampered_release.write_bytes(context.release_file.read_bytes() + b"\n")
    release_context = replace(
        context,
        release_file=tampered_release.resolve(),
        release_file_sha256=campaign.sha256(tampered_release.read_bytes()),
    )
    with pytest.raises(
        physical.OtpTransitionMatrixPhysicalError,
        match="release validation failed|validation failed|refuses a different release",
    ):
        physical.required_authorization(release_context, 1)
    assert called is False
    assert not (tmp_path / "claims").exists()


def test_engine_globals_are_restored_even_when_bound_call_raises(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    before = {
        name: getattr(engine, name) for name in physical._ENGINE_BINDINGS  # noqa: SLF001
    }
    with pytest.raises(physical.OtpTransitionMatrixPhysicalError):
        physical.run_once(
            context,
            BASE_URL,
            2,
            authorization=physical.required_authorization(context, 2),
            result_file=tmp_path / "never-created.json",
            claim_registry=tmp_path / "claims",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=36.5,
            requester=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("requester must not run")
            ),
        )
    assert {
        name: getattr(engine, name) for name in physical._ENGINE_BINDINGS  # noqa: SLF001
    } == before


def test_runner_and_release_cannot_be_interpreted_as_runtime_lut(
    offline_contract: physical.ReleaseContext,
) -> None:
    context = offline_contract
    manifest = contract.campaign_manifest()
    for ordinal in range(1, campaign.ACTION_COUNT + 1):
        description = physical.describe(context, ordinal)
        assert description["factory_otp_profile"] is True
        assert description["runtime_lut_or_waveform_changed"] is False
    assert context.release_root["safety"]["profile_source"] == "factory_otp"
    assert context.release_root["safety"]["runtime_lut_or_waveform_write"] is False
    assert manifest["profile_source"] == "factory_otp"
    assert manifest["custom_lut_or_waveform"] is False
    assert manifest["runtime_lut_write"] is False
    parameter_names = set(inspect.signature(physical.run_once).parameters)
    assert not parameter_names & {
        "profile",
        "runtime_profile",
        "runtime_lut",
        "lut_payload",
        "waveform",
    }
    assert all("runtime" not in endpoint for endpoint in campaign.ENDPOINTS.values())


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def _json_keys(source: str) -> set[str]:
    return set(re.findall(r'\\"([a-z0-9_]+)\\"\s*:', source))


def test_firmware_mutation_and_terminal_json_match_exact_host_schema() -> None:
    source = MAIN.read_text(encoding="utf-8")
    identity_keys = {
        "build_tag",
        "test_id",
        "campaign_id",
        "device_api_version",
        "identity_revision",
        "contract_id",
    }
    action_keys = {
        "ordinal",
        "descriptor_id",
        "action_id",
        "prior_static_action_id",
        "role",
        "round",
        "branch",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
    }
    assert _json_keys(_between(source, "String identityJson()", "String histogramJson")) == identity_keys
    assert _json_keys(_between(source, "String actionJson", "String versionJson")) == action_keys

    arm_keys = _json_keys(_between(source, "void handleArm()", "void handleExecute()"))
    execute_keys = _json_keys(
        _between(source, "void handleExecute()", "void installRoutes()")
    )
    assert arm_keys | identity_keys == {
        "accepted",
        "armed",
        *identity_keys,
        "classification",
        "ordinal",
        "descriptor_id",
        "action_id",
        "role",
        "round",
        "branch",
        "boot_nonce",
        "arm_nonce",
        "phase",
        "phase_name",
        "not_hardware_authorization",
    }
    assert execute_keys | identity_keys == {
        "accepted",
        "job_id",
        *identity_keys,
        "classification",
        "ordinal",
        "descriptor_id",
        "action_id",
        "role",
        "round",
        "branch",
        "boot_nonce",
        "execute_consumed",
        "phase",
        "phase_name",
        "no_retry",
        "no_recovery",
    }

    terminal = _between(source, "void executePendingAction()", "}  // namespace")
    terminal_keys = _json_keys(terminal)
    assert terminal_keys | identity_keys == {
        "schema_version",
        "kind",
        "valid",
        *identity_keys,
        "classification",
        "boot_nonce",
        "ordinal",
        "descriptor_id",
        "action_id",
        "role",
        "round",
        "branch",
        "job_id",
        "terminal_state",
        "result",
        "driver_called",
        "driver_call_count_for_action",
        "total_driver_call_count",
        "phase",
        "phase_name",
        "next_ordinal",
        "campaign_complete",
        "no_retry",
        "no_recovery",
        "job_queued_at_ms",
        "job_started_at_ms",
        "job_finished_at_ms",
        "driver",
    }
    assert terminal.count(
        "epdDisplayCompiledOtpTransitionMatrix(action->driverRole)"
    ) == 1
    assert "runtime_lut" not in terminal.lower()
