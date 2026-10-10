from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from tests.test_mf1750_ec5_white_recovery_once import FakeRC2G, PANEL
from tools import mf1750_ec5_compare_white_identity as identity
from tools import mf1750_ec5_compare_white_recovery_once as runner
from tools import mf1750_ec5_white_recovery_once as white


HARDWARE = runner.REPO_ROOT / ".test-output" / "hardware"
COMPARE_RELEASE = (
    HARDWARE
    / "MF1750_EC5_U04_U05_COMPARE_RELEASE_OFFLINE_20260809_V2"
    / "release-manifest.json"
)
COMPARE_SESSION = (
    HARDWARE / "MF1750_EC5_U04_U05_COMPARE_PHYSICAL_SESSION_20260809_2300"
)
COMPARE_RESULT = COMPARE_SESSION / "u04-u05-compare-result.json"
COMPARE_OBSERVATION = COMPARE_SESSION / "u04-u05-blind-manual-observation.json"
COMPARE_CLAIMS = HARDWARE / ".mf1750_ec5_u04_u05_compare_claims"
PANEL_FILE = (
    HARDWARE
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "inputs"
    / "physical-panel.json"
)
RC2G_BINARY = (
    HARDWARE
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "q1-map-primer-result"
    / "FIRMWARE.bin"
)

FAKE_BINDING = {
    "compare_action_id": identity.COMPARE_ACTION_ID,
    "manual_observation": {"observed_at": "2026-08-09T15:19:09Z"},
    "ready_for_separately_authorized_white_recovery": True,
}


def _panel(tmp_path: Path) -> Path:
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(PANEL), encoding="utf-8")
    return path


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "flash_gate_file": tmp_path / "flash-gate.json",
        "preflight_file": tmp_path / "preflight.json",
        "result_file": tmp_path / "result.json",
        "compare_release_file": tmp_path / "unused-release.json",
        "compare_result_file": tmp_path / "unused-result.json",
        "compare_claim_registry": tmp_path / "unused-compare-claims",
        "compare_observation_file": tmp_path / "unused-observation.json",
        "panel_file": _panel(tmp_path),
        "rc2g_binary_file": RC2G_BINARY,
        "claim_registry": tmp_path / "compare-white-claims",
        "formal_white_claim_registry": tmp_path / "formal-white-claims",
    }


def _install_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "load_compare_binding",
        lambda **_kwargs: SimpleNamespace(binding=FAKE_BINDING),
    )


def _prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    requester: Callable[..., tuple[int, str]] | None = None,
) -> tuple[dict[str, Path], FakeRC2G]:
    _install_binding(monkeypatch)
    paths = _paths(tmp_path)
    fake = FakeRC2G()
    active = requester or fake
    runner.create_j2_off_flash_gate(
        **{
            key: value
            for key, value in paths.items()
            if key not in {"flash_gate_file", "preflight_file", "result_file"}
        },
        evidence_file=paths["flash_gate_file"],
        confirm_j2_off=True,
    )
    runner.create_j2_on_preflight(
        base_url="http://192.0.2.1",
        **{key: value for key, value in paths.items() if key != "result_file" and key != "preflight_file"},
        evidence_file=paths["preflight_file"],
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        requester=active,
    )
    return paths, fake


def _validation(paths: dict[str, Path]) -> dict[str, Path]:
    return {
        key: value
        for key, value in paths.items()
        if key != "result_file"
    }


def test_frozen_identity_and_authoritative_white_bytes() -> None:
    assert identity.action_id() == identity.FROZEN_ACTION_ID
    assert identity.FROZEN_ACTION_ID not in identity.FORMAL_WHITE_ACTION_IDS.values()
    assert len(set(identity.FORMAL_WHITE_ACTION_IDS.values())) == 3
    assert runner.required_authorization().endswith("__NO_RETRY_NO_RECOVERY")
    assert identity.FROZEN_ACTION_ID.upper() in runner.required_authorization()
    assert white.WHITE_FRAME == b"\x11" * 307_200
    assert identity.WHITE_FRAME_SHA256 == white.WHITE_FRAME_SHA256
    assert identity.WHITE_FRAME_FNV1A == white.WHITE_FRAME_FNV1A
    assert identity.WHITE_DTM_FNV1A == white.WHITE_DTM_FNV1A
    assert runner._rc2g(RC2G_BINARY)["sha256"] == identity.RC2G_BINARY_SHA256


def test_real_completed_compare_evidence_deep_replays_offline() -> None:
    context = runner.load_compare_binding(
        compare_release_file=COMPARE_RELEASE,
        compare_result_file=COMPARE_RESULT,
        compare_claim_registry=COMPARE_CLAIMS,
        compare_observation_file=COMPARE_OBSERVATION,
        panel_file=PANEL_FILE,
    )
    assert context.binding["compare_action_id"] == identity.COMPARE_ACTION_ID
    assert context.binding["result"]["outcome"] == "complete_pass"
    assert context.binding["manual_observation"]["difference_strength_scale_0_to_4"] == 2
    assert context.binding["ready_for_separately_authorized_white_recovery"] is True


def test_tampered_archived_observation_is_rejected(tmp_path: Path) -> None:
    value = json.loads(COMPARE_OBSERVATION.read_text(encoding="utf-8"))
    value["conclusion"]["clean_white_recovery_after_comparison_required"] = False
    tampered = tmp_path / "tampered-observation.json"
    tampered.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(runner.CompareWhiteError, match="observation file hash"):
        runner.load_compare_binding(
            compare_release_file=COMPARE_RELEASE,
            compare_result_file=COMPARE_RESULT,
            compare_claim_registry=COMPARE_CLAIMS,
            compare_observation_file=tampered,
            panel_file=PANEL_FILE,
        )


def test_j2_off_gate_is_zero_io_zero_claim_and_registry_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_binding(monkeypatch)
    paths = _paths(tmp_path)
    call_args = {
        key: value
        for key, value in paths.items()
        if key not in {"flash_gate_file", "preflight_file", "result_file"}
    }
    with pytest.raises(runner.CompareWhiteError, match="explicit confirmation"):
        runner.create_j2_off_flash_gate(
            **call_args,
            evidence_file=paths["flash_gate_file"],
            confirm_j2_off=False,
        )
    assert not paths["claim_registry"].exists()
    gate = runner.create_j2_off_flash_gate(
        **call_args,
        evidence_file=paths["flash_gate_file"],
        confirm_j2_off=True,
    )
    assert gate["network_requests"] == 0
    assert gate["device_io_performed_by_this_tool"] is False
    assert gate["claim_created"] is False
    assert not paths["claim_registry"].exists()
    assert gate["independent_claim_registry"] != gate["formal_white_claim_snapshot"]["registry"]


def test_registry_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_binding(monkeypatch)
    paths = _paths(tmp_path)
    with pytest.raises(runner.CompareWhiteError, match="registries must differ"):
        runner.create_j2_off_flash_gate(
            compare_release_file=paths["compare_release_file"],
            compare_result_file=paths["compare_result_file"],
            compare_claim_registry=paths["compare_claim_registry"],
            compare_observation_file=paths["compare_observation_file"],
            panel_file=paths["panel_file"],
            rc2g_binary_file=paths["rc2g_binary_file"],
            claim_registry=paths["formal_white_claim_registry"],
            formal_white_claim_registry=paths["formal_white_claim_registry"],
            evidence_file=paths["flash_gate_file"],
            confirm_j2_off=True,
        )


def test_dangling_claim_symlink_never_counts_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_binding(monkeypatch)
    paths = _paths(tmp_path)
    paths["claim_registry"].mkdir()
    claim_file = paths["claim_registry"] / f"{identity.FROZEN_ACTION_ID}.json"
    try:
        claim_file.symlink_to(tmp_path / "missing-claim.json")
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")
    with pytest.raises(runner.CompareWhiteError, match="regular non-symlink"):
        runner.create_j2_off_flash_gate(
            compare_release_file=paths["compare_release_file"],
            compare_result_file=paths["compare_result_file"],
            compare_claim_registry=paths["compare_claim_registry"],
            compare_observation_file=paths["compare_observation_file"],
            panel_file=paths["panel_file"],
            rc2g_binary_file=paths["rc2g_binary_file"],
            claim_registry=paths["claim_registry"],
            formal_white_claim_registry=paths["formal_white_claim_registry"],
            evidence_file=paths["flash_gate_file"],
            confirm_j2_off=True,
        )


def test_j2_on_preflight_is_exactly_four_gets_zero_post_zero_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, fake = _prepare(tmp_path, monkeypatch)
    assert fake.requests == [
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
    ]
    preflight = runner.validate_j2_on_preflight(
        evidence_file=paths["preflight_file"],
        **{
            key: value
            for key, value in _validation(paths).items()
            if key != "preflight_file"
        },
    )
    assert preflight["get_requests"] == 4
    assert preflight["post_requests"] == 0
    assert not paths["claim_registry"].exists()


def test_wrong_authorization_is_zero_network_and_zero_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _prepare(tmp_path, monkeypatch)
    fake = FakeRC2G()
    with pytest.raises(runner.CompareWhiteError, match="authorization"):
        runner.run_once(
            base_url="http://192.0.2.1",
            authorization="wrong",
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            requester=fake,
            **paths,
        )
    assert fake.requests == []
    assert not paths["claim_registry"].exists()


def test_success_claims_before_one_post_validates_and_blocks_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _prepare(tmp_path, monkeypatch)
    fake = FakeRC2G()
    claim_file = paths["claim_registry"] / f"{identity.FROZEN_ACTION_ID}.json"

    def assert_claim_before_post(*args: Any, **kwargs: Any) -> tuple[int, str]:
        if kwargs["method"] == "POST":
            assert claim_file.is_file()
        return fake(*args, **kwargs)

    result = runner.run_once(
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization(),
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        requester=assert_claim_before_post,
        sleeper=lambda _seconds: None,
        **paths,
    )
    assert result["outcome"] == "complete_pass"
    assert result["network"]["post_requests"] == 1
    assert fake.requests.count(("POST", "/api/frame")) == 1
    validated = runner.validate_result(
        result_file=paths["result_file"],
        **_validation(paths),
    )
    assert validated["outcome"] == "complete_pass"
    assert (
        validated["formal_white_claim_snapshot_before_post"]
        == validated["formal_white_claim_snapshot_after_action"]
    )
    duplicate = FakeRC2G()
    with pytest.raises(runner.CompareWhiteError, match="already claimed"):
        runner.run_once(
            base_url="http://192.0.2.1",
            authorization=runner.required_authorization(),
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            requester=duplicate,
            sleeper=lambda _seconds: None,
            **{**paths, "result_file": tmp_path / "duplicate-result.json"},
        )
    assert duplicate.requests == []


def test_tampered_result_and_claim_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _prepare(tmp_path, monkeypatch)
    runner.run_once(
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization(),
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        requester=FakeRC2G(),
        sleeper=lambda _seconds: None,
        **paths,
    )
    original = paths["result_file"].read_bytes()
    value = json.loads(original)
    value["frame_fnv1a"] = 0
    paths["result_file"].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(runner.CompareWhiteError, match="integrity"):
        runner.validate_result(
            result_file=paths["result_file"],
            **_validation(paths),
        )
    paths["result_file"].write_bytes(original)
    claim_file = paths["claim_registry"] / f"{identity.FROZEN_ACTION_ID}.json"
    claim = json.loads(claim_file.read_text(encoding="utf-8"))
    claim["maximum_frame_posts"] = 2
    claim_file.write_text(json.dumps(claim), encoding="utf-8")
    with pytest.raises(runner.CompareWhiteError, match="integrity"):
        runner.validate_result(
            result_file=paths["result_file"],
            **_validation(paths),
        )


def test_post_action_formal_snapshot_failure_still_seals_unknown_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _prepare(tmp_path, monkeypatch)
    fake = FakeRC2G()
    original = runner._formal_snapshot
    calls = 0

    def fail_fourth(registry: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise runner.CompareWhiteError("injected post-action read failure")
        return original(registry)

    monkeypatch.setattr(runner, "_formal_snapshot", fail_fourth)
    result = runner.run_once(
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization(),
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        requester=fake,
        sleeper=lambda _seconds: None,
        **paths,
    )
    assert calls == 4
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["formal_white_claim_snapshot_after_action"] is None
    assert "injected post-action" in result[
        "formal_white_claim_snapshot_after_action_error"
    ]
    assert paths["result_file"].is_file()
    assert fake.requests.count(("POST", "/api/frame")) == 1
    assert (
        paths["claim_registry"] / f"{identity.FROZEN_ACTION_ID}.json"
    ).is_file()


def test_manual_clean_white_contract_and_u07t_rebind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _prepare(tmp_path, monkeypatch)
    runner.run_once(
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization(),
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        requester=FakeRC2G(),
        sleeper=lambda _seconds: None,
        **paths,
    )
    validation = _validation(paths)
    observation_file = tmp_path / "white-observation.json"
    with pytest.raises(runner.CompareWhiteError, match="all confirmations"):
        runner.create_white_manual_observation(
            result_file=paths["result_file"],
            observation_file=observation_file,
            operator_report="white",
            temperature_c=35.0,
            confirm_full_white=True,
            confirm_compare_patches_gone=False,
            confirm_no_residual=True,
            confirm_electrical_normal=True,
            confirm_esp32_no_restart=True,
            validation_kwargs=validation,
        )
    runner.create_white_manual_observation(
        result_file=paths["result_file"],
        observation_file=observation_file,
        operator_report="全屏干净白色，比较色块完全消失，电气正常。",
        temperature_c=35.0,
        confirm_full_white=True,
        confirm_compare_patches_gone=True,
        confirm_no_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        validation_kwargs=validation,
    )
    observed = runner.validate_white_manual_observation(
        result_file=paths["result_file"],
        observation_file=observation_file,
        validation_kwargs=validation,
    )
    assert observed["eligible_as_u07t_white_predecessor"] is True
    binding = runner.create_u07t_latest_white_binding(
        result_file=paths["result_file"],
        observation_file=observation_file,
        output_file=tmp_path / "u07t-latest-white.json",
        validation_kwargs=validation,
    )
    assert binding["predecessor_action_id"] == identity.FROZEN_ACTION_ID
    assert binding["requires_new_u07t_action_identity"] is True
    assert binding["no_intervening_visible_refresh_requires_live_confirmation"] is True
    binding_file = tmp_path / "u07t-latest-white.json"
    validated = runner.validate_u07t_latest_white_binding(
        result_file=paths["result_file"],
        observation_file=observation_file,
        binding_file=binding_file,
        validation_kwargs=validation,
    )
    assert validated["predecessor_action_id"] == identity.FROZEN_ACTION_ID
    original_binding = binding_file.read_bytes()
    time_tampered = json.loads(original_binding)
    time_tampered.pop("integrity")
    time_tampered["created_at"] = "2020-01-01T00:00:00Z"
    binding_file.write_bytes(
        runner.canonical_json_bytes(runner._seal(time_tampered))
    )
    with pytest.raises(runner.CompareWhiteError, match="predates"):
        runner.validate_u07t_latest_white_binding(
            result_file=paths["result_file"],
            observation_file=observation_file,
            binding_file=binding_file,
            validation_kwargs=validation,
        )
    binding_file.write_bytes(original_binding)
    tampered = json.loads(original_binding)
    tampered["latest_visible_state"] = "unknown"
    binding_file.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(runner.CompareWhiteError, match="integrity"):
        runner.validate_u07t_latest_white_binding(
            result_file=paths["result_file"],
            observation_file=observation_file,
            binding_file=binding_file,
            validation_kwargs=validation,
        )
