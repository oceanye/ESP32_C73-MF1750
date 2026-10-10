from __future__ import annotations

import copy
from pathlib import Path
import socket
import urllib.request

import pytest

from tests.ec5_unknown_probe_fixture import make_inputs, write_json
from tools import mf1750_ec5_unknown_probe_analyzer as analyzer
from tools import mf1750_ec5_unknown_probe_campaign as campaign


def _paths(inputs: dict[str, object]) -> tuple[Path, Path, Path, Path, Path]:
    return (
        inputs["campaign_path"],
        inputs["panel_path"],
        inputs["build_path"],
        inputs["firmware_path"],
        inputs["observation_path"],
    )


def _rewrite_observation(inputs: dict[str, object], value: object) -> None:
    write_json(inputs["observation_path"], value)


def test_valid_manual_observation_is_descriptive_and_never_qualified(
    tmp_path: Path,
) -> None:
    inputs = make_inputs(tmp_path)
    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["verdict"] == {
        "code": "DESCRIPTIVE_OBSERVATION_RECORDED",
        "reasons": [],
        "descriptive_only": True,
        "qualification_state": "NOT_QUALIFIED",
    }
    assert value["campaign_binding"]["frame_sha256"] == campaign.U04_FRAME_SHA256
    assert value["campaign_binding"]["cs1_dtm_sha256"] == campaign.U04_DTM_SHA256
    assert value["campaign_binding"]["cs2_dtm_sha256"] == campaign.U04_DTM_SHA256
    assert value["roi_summary"]["classifications_match"] is True
    assert value["hold_summary"]["duration_seconds"] == 600.0
    assert value["safety_review"]["all_recorded_checks_pass"] is True
    classification = value["classification"]
    assert classification["manual_hardware_observation_recorded"] is True
    assert classification["hardware_io_performed_by_analyzer"] is False
    assert classification["unknown_code_safe_claimed"] is False
    assert classification["physical_color_alias_claimed"] is False
    assert classification["waveform_modification_claimed"] is False
    assert classification["production_qualification_claimed"] is False
    assert classification["qualification_state"] == "NOT_QUALIFIED"
    assert all(
        gate is False
        for name, gate in value["progression_gate"].items()
        if name.endswith("_authorized")
    )


def test_left_right_color_mismatch_remains_descriptive_only(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["roi_observations"][0]["classification"] = "red-like"
    observation["roi_observations"][1]["classification"] = "yellow-like"
    _rewrite_observation(inputs, observation)

    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["verdict"]["code"] == "DESCRIPTIVE_OBSERVATION_RECORDED"
    assert value["roi_summary"]["classifications_match"] is False
    assert value["classification"]["physical_color_alias_claimed"] is False
    assert value["progression_gate"]["u07_build_or_action_authorized"] is False


@pytest.mark.parametrize("classification", ["mixed-or-unstable", "not-observed"])
def test_unresolved_roi_is_descriptive_inconclusive(
    tmp_path: Path, classification: str
) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["roi_observations"][0]["classification"] = classification
    observation["roi_observations"][0]["stable_for_entire_observation"] = False
    _rewrite_observation(inputs, observation)

    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["verdict"]["code"] == "DESCRIPTIVE_INCONCLUSIVE"
    assert value["verdict"]["qualification_state"] == "NOT_QUALIFIED"
    assert value["progression_gate"]["u04_repeats_authorized"] is False


def test_electrical_stop_condition_yields_stop_and_no_interpretation(
    tmp_path: Path,
) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["electrical"]["psu_mode"] = "CC"
    observation["electrical"]["current_within_reviewed_gate"] = False
    observation["electrical"]["abnormal_event_observed"] = True
    _rewrite_observation(inputs, observation)

    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["verdict"]["code"] == "DESCRIPTIVE_STOP_AND_REVIEW"
    assert "psu_in_cv" in value["verdict"]["reasons"]
    assert "current_within_reviewed_gate" in value["verdict"]["reasons"]
    assert value["roi_summary"]["descriptive_interpretation"] is None
    assert value["progression_gate"]["do_not_retry_this_test_id"] is True
    assert value["progression_gate"]["automatic_recovery_authorized"] is False


def test_temperature_and_visual_anomaly_yield_stop(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["temperature"]["within_reviewed_gate"] = False
    observation["temperature"]["unexplained_hotspot"] = True
    observation["anomaly_review"]["visual_damage_or_crack"] = True
    _rewrite_observation(inputs, observation)

    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["verdict"]["code"] == "DESCRIPTIVE_STOP_AND_REVIEW"
    assert value["classification"]["unknown_code_safe_claimed"] is False
    assert value["progression_gate"]["u04_other_initial_states_authorized"] is False


def test_observation_requires_exact_hold_duration(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["hold"]["duration_seconds"] = 599.0
    _rewrite_observation(inputs, observation)

    with pytest.raises(analyzer.EC5AnalyzerError, match="hold duration"):
        analyzer.analyze_observation(*_paths(inputs))


def test_observation_rejects_contradictory_esp_continuity(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["esp_continuity"]["boot_id_after"] = "boot-20260809-002"
    _rewrite_observation(inputs, observation)

    with pytest.raises(analyzer.EC5AnalyzerError, match="contradict"):
        analyzer.analyze_observation(*_paths(inputs))


def test_observation_rejects_campaign_or_build_lineage_tamper(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["lineage"]["build_sidecar_sha256"] = "f" * 64
    _rewrite_observation(inputs, observation)

    with pytest.raises(analyzer.EC5AnalyzerError, match="differs from campaign"):
        analyzer.analyze_observation(*_paths(inputs))


def test_observation_rejects_extra_fields(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    observation = copy.deepcopy(inputs["observation"])
    observation["claimed_safe_color"] = "red"
    _rewrite_observation(inputs, observation)

    with pytest.raises(analyzer.EC5AnalyzerError, match="fields differ"):
        analyzer.analyze_observation(*_paths(inputs))


def test_resealed_forbidden_qualification_claim_is_rejected(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    value = analyzer.analyze_observation(*_paths(inputs))
    altered = copy.deepcopy(value)
    altered["classification"]["physical_color_alias_claimed"] = True
    unsigned = dict(altered)
    unsigned.pop("integrity")
    altered["integrity"] = {
        "canonical_sha256": campaign.sha256(unsigned),
        "canonical_sha256_scope": analyzer.HASH_SCOPE,
    }

    with pytest.raises(analyzer.EC5AnalyzerError, match="descriptive-only boundary"):
        analyzer.validate_analysis(altered, *_paths(inputs))


def test_analysis_replay_rejects_resealed_content_tamper(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    value = analyzer.analyze_observation(*_paths(inputs))
    altered = copy.deepcopy(value)
    altered["roi_summary"]["classifications_match"] = False
    unsigned = dict(altered)
    unsigned.pop("integrity")
    altered["integrity"] = {
        "canonical_sha256": campaign.sha256(unsigned),
        "canonical_sha256_scope": analyzer.HASH_SCOPE,
    }

    with pytest.raises(analyzer.EC5AnalyzerError, match="actual evidence"):
        analyzer.validate_analysis(altered, *_paths(inputs))


def test_analyzer_performs_no_socket_or_url_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = make_inputs(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external I/O is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    value = analyzer.analyze_observation(*_paths(inputs))

    assert value["classification"]["network_io_performed_by_analyzer"] is False
    assert value["classification"]["serial_io_performed_by_analyzer"] is False


def test_analyzer_cli_has_no_device_or_claim_controls() -> None:
    with pytest.raises(SystemExit):
        analyzer.parse_args(["analyze", "--url", "http://device.invalid"])
    with pytest.raises(SystemExit):
        analyzer.parse_args(["analyze", "--arm", "token"])
    with pytest.raises(SystemExit):
        analyzer.parse_args(["analyze", "--recover"])
