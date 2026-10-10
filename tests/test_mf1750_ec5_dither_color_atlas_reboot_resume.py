from __future__ import annotations

# Imported pytest fixtures intentionally share names with test parameters.
# ruff: noqa: F401, F811

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from tests import test_mf1750_ec5_dither_color_atlas_physical_once as base
from tests.test_mf1750_ec5_dither_color_atlas_physical_once import (
    offline_contract as offline_contract_fixture,
    synthetic_files,
)
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign
from tools import mf1750_ec5_dither_color_atlas_reboot_resume as resume
from tools import mf1750_ec5_dither_color_atlas_physical_once as physical


@pytest.fixture(autouse=True)
def restore_physical_bindings() -> Any:
    """Keep recovery-only monkeypatches from leaking into another test."""

    bindings = physical._ENGINE_BINDINGS  # noqa: SLF001
    prior_gate = physical._dither_prior_gate  # noqa: SLF001
    authorization = physical.required_authorization
    yield
    physical._ENGINE_BINDINGS = bindings  # noqa: SLF001
    physical._dither_prior_gate = prior_gate  # noqa: SLF001
    physical.required_authorization = authorization


def _identities(path: Path) -> tuple[str, str]:
    payload = path.read_bytes()
    root = json.loads(payload.decode("utf-8"))
    return campaign.sha256(payload), str(root["integrity"]["canonical_sha256"])


def _patch_paths(
    monkeypatch: pytest.MonkeyPatch,
    context: Any,
    registry: Path,
    atlas_result: Path,
    atlas_observation: Path,
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    atlas_claim = registry / f"{resume.ATLAS_ACTION_ID}.json"
    release_file, release_canonical = _identities(context.release_file)
    result_file, result_canonical = _identities(atlas_result)
    observation_file, observation_canonical = _identities(atlas_observation)
    claim_file, claim_canonical = _identities(atlas_claim)
    output = tmp_path / "reboot-resume"
    output.mkdir()
    diagnostic = output / "j2-off-diagnostic.json"
    authority = output / "reboot-resume-authority.json"
    white_result = output / "ordinal-02-white-result.json"
    white_observation = output / "ordinal-02-white-observation.json"

    values = {
        "RELEASE_FILE": context.release_file,
        "ATLAS_RESULT_FILE": atlas_result,
        "ATLAS_OBSERVATION_FILE": atlas_observation,
        "ATLAS_CLAIM_FILE": atlas_claim,
        "CLAIM_REGISTRY": registry,
        "WHITE_CLAIM_FILE": registry / f"{resume.WHITE_ACTION_ID}.json",
        "OUTPUT_DIR": output,
        "DEFAULT_DIAGNOSTIC_FILE": diagnostic,
        "DEFAULT_AUTHORITY_FILE": authority,
        "DEFAULT_RESULT_FILE": white_result,
        "DEFAULT_OBSERVATION_FILE": white_observation,
        "EXPECTED_RELEASE_FILE_SHA256": release_file,
        "EXPECTED_RELEASE_CANONICAL_SHA256": release_canonical,
        "EXPECTED_ATLAS_RESULT_FILE_SHA256": result_file,
        "EXPECTED_ATLAS_RESULT_CANONICAL_SHA256": result_canonical,
        "EXPECTED_ATLAS_OBSERVATION_FILE_SHA256": observation_file,
        "EXPECTED_ATLAS_OBSERVATION_CANONICAL_SHA256": observation_canonical,
        "EXPECTED_ATLAS_CLAIM_FILE_SHA256": claim_file,
        "EXPECTED_ATLAS_CLAIM_CANONICAL_SHA256": claim_canonical,
        "EXPECTED_ATLAS_BOOT_NONCE": base.BOOT_NONCE_A,
    }
    for name, value in values.items():
        monkeypatch.setattr(resume, name, value)
    monkeypatch.setattr(
        resume.entry, "validate_containment_evidence", lambda: "fixture"
    )
    monkeypatch.setattr(resume.entry, "install_overrides", lambda: None)
    monkeypatch.setattr(resume, "_ACTIVE_AUTHORITY_ROOT", None)
    monkeypatch.setattr(resume, "_ACTIVE_AUTHORITY_FILE", None)
    return diagnostic, authority, white_result


def _reboot_at_cursor_two(device: base.StrictDitherFakeDevice) -> None:
    device.boot_nonce = base.BOOT_NONCE_B
    device.next_ordinal = 2
    device.phase = 0
    device.key_present = True
    device.arm_request_count = 0
    device.execute_request_count = 0
    device.total_driver_call_count = 0
    device.last_completed_ordinal = None
    device.driver_powered = False


def _prepare(
    context: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[base.StrictDitherFakeDevice, Path, Path, Path, Path]:
    device, registry, atlas_result, atlas_observation = base._complete_atlas(
        context, tmp_path
    )
    _reboot_at_cursor_two(device)
    diagnostic, authority, white_result = _patch_paths(
        monkeypatch,
        context,
        registry,
        atlas_result,
        atlas_observation,
        tmp_path,
    )
    resume.install_overrides()
    return device, registry, diagnostic, authority, white_result


def _capture_and_authorize(
    context: Any,
    device: base.StrictDitherFakeDevice,
    diagnostic: Path,
    authority: Path,
) -> None:
    captured = resume.capture_j2_off_diagnostic(
        context,
        base.BASE_URL,
        diagnostic_file=diagnostic,
        current_a=0.0,
        temperature_c=25.0,
        confirm_j2_off=True,
        confirm_atlas_visible=True,
        confirm_no_abnormality=True,
        confirm_no_intervening_visible_refresh=True,
        requester=device,
    )
    assert captured["boot_nonce"] == base.BOOT_NONCE_B
    assert captured["volatile_counts"] == {
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
    }
    assert captured["preflight_report"]["terminal_state"] == "NOT_EXECUTED"
    assert (
        resume.validate_j2_off_diagnostic(
            context, diagnostic, require_white_unclaimed=True
        )
        == captured
    )
    built = resume.build_authority(context, diagnostic, authority)
    assert built["execution_authorized"] is False
    assert (
        resume.validate_authority(context, authority, require_white_unclaimed=True)
        == built
    )


def test_reboot_resume_white_e2e_uses_one_new_boot_action(
    offline_contract_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = offline_contract_fixture
    device, registry, diagnostic, authority, white_result = _prepare(
        context, tmp_path, monkeypatch
    )
    calls_before_capture = len(device.calls)
    _capture_and_authorize(context, device, diagnostic, authority)
    capture_calls = device.calls[calls_before_capture:]
    assert len(capture_calls) == 4
    assert all(item["method"] == "GET" for item in capture_calls)
    assert not (registry / f"{resume.WHITE_ACTION_ID}.json").exists()

    device.driver_powered = True
    result = resume.run_once(
        context,
        base.BASE_URL,
        authority_file=authority,
        result_file=white_result,
        temperature_c=25.0,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        confirm_atlas_visible=True,
        confirm_no_intervening_visible_refresh=True,
        requester=device,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass", result["error"]
    assert result["preflight"]["boot_nonce"] == base.BOOT_NONCE_B
    assert result["prior_gate"]["previous_atlas_boot_nonce"] == base.BOOT_NONCE_A
    assert result["prior_gate"]["required_same_boot_nonce"] == base.BOOT_NONCE_B
    assert result["device"]["terminal_report"]["total_driver_call_count"] == 1
    assert resume.validate_result(context, authority, white_result) == result
    assert device.driver_action_ordinals == [1, 2]
    assert device.next_ordinal == 3
    assert len(list(registry.glob("*.json"))) == 2


@pytest.mark.parametrize("drift", ["boot", "counter"])
def test_live_drift_stops_before_white_claim_or_post(
    offline_contract_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    context = offline_contract_fixture
    device, registry, diagnostic, authority, white_result = _prepare(
        context, tmp_path, monkeypatch
    )
    _capture_and_authorize(context, device, diagnostic, authority)
    if drift == "boot":
        device.boot_nonce = "1111111111111111"
    else:
        device.arm_request_count = 1
    device.driver_powered = True
    calls_before = len(device.calls)
    with pytest.raises(resume.RebootResumeError):
        resume.run_once(
            context,
            base.BASE_URL,
            authority_file=authority,
            result_file=white_result,
            temperature_c=25.0,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            confirm_atlas_visible=True,
            confirm_no_intervening_visible_refresh=True,
            requester=device,
            poll_count=1,
            poll_interval_seconds=0,
            sleeper=lambda _seconds: None,
        )
    new_calls = device.calls[calls_before:]
    assert new_calls
    assert all(item["method"] == "GET" for item in new_calls)
    assert not (registry / f"{resume.WHITE_ACTION_ID}.json").exists()
    assert not white_result.exists()


def test_diagnostic_flags_fail_before_network(
    offline_contract_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = offline_contract_fixture
    device, _registry, diagnostic, _authority, _white_result = _prepare(
        context, tmp_path, monkeypatch
    )
    calls_before = deepcopy(device.calls)
    with pytest.raises(resume.RebootResumeError, match="all.*confirmations"):
        resume.capture_j2_off_diagnostic(
            context,
            base.BASE_URL,
            diagnostic_file=diagnostic,
            current_a=0.0,
            temperature_c=25.0,
            confirm_j2_off=True,
            confirm_atlas_visible=False,
            confirm_no_abnormality=True,
            confirm_no_intervening_visible_refresh=True,
            requester=device,
        )
    assert device.calls == calls_before
    assert not diagnostic.exists()


def test_authority_rejects_adapter_identity_change(
    offline_contract_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = offline_contract_fixture
    device, _registry, diagnostic, authority, _white_result = _prepare(
        context, tmp_path, monkeypatch
    )
    _capture_and_authorize(context, device, diagnostic, authority)
    changed_source = tmp_path / "changed-adapter.py"
    changed_source.write_text("# changed\n", encoding="utf-8")
    monkeypatch.setattr(resume, "SOURCE_FILE", changed_source)
    with pytest.raises(resume.RebootResumeError, match="authority semantics"):
        resume.validate_authority(context, authority, require_white_unclaimed=True)
