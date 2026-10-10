from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
import urllib.request

import pytest

from tests.ec5_unknown_probe_fixture import make_inputs, write_json
from tools import mf1750_ec5_unknown_probe_campaign as campaign


def _paths(inputs: dict[str, object]) -> tuple[Path, Path, Path]:
    return (
        inputs["panel_path"],
        inputs["build_path"],
        inputs["firmware_path"],
    )


def test_compile_materializes_only_fixed_u04_white_single_action(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    value = inputs["campaign"]

    assert len(value["actions"]) == 1
    action = value["actions"][0]
    assert action["test_id"] == campaign.TEST_ID
    assert action["candidate_code"] == 0x4
    assert action["intended_initial_code"] == 0x1
    assert action["repetition"] == 1
    assert action["maximum_execute_attempts"] == 1
    assert action["execution_route_materialized"] is False
    assert action["hardware_execution_authorized"] is False
    assert action["frame_identity"]["frame_sha256"] == campaign.U04_FRAME_SHA256
    assert action["frame_identity"]["cs1_dtm_sha256"] == campaign.U04_DTM_SHA256
    assert action["frame_identity"]["cs2_dtm_sha256"] == campaign.U04_DTM_SHA256
    assert action["frame_identity"]["generator_agreement"] is True
    assert value["pilot_contract"]["u07_fixture_or_action_present"] is False
    assert value["pilot_contract"]["other_initial_states_materialized"] is False
    assert value["pilot_contract"]["repeat_campaign_materialized"] is False
    assert value["pilot_contract"]["hold_study_materialized"] is False
    assert value["classification"]["qualification_state"] == "NOT_QUALIFIED"
    serialized = campaign.canonical_json_bytes(value).decode("utf-8")
    assert campaign.U07_DESIGN_IDENTITY["frame_sha256"] not in serialized
    assert campaign.validate_campaign(value, *_paths(inputs)) == value


def test_manifest_and_actual_panel_build_binary_are_bound(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    value = inputs["campaign"]
    binding = value["physical_binding"]
    fixture = value["fixture_manifest"]

    assert binding["panel"] == inputs["panel"]
    assert binding["build_sidecar"] == inputs["build"]
    assert binding["firmware_binary_sha256"] == inputs["build"]["binary_sha256"]
    assert fixture["manifest_payload_sha256"] == inputs["build"][
        "manifest_payload_sha256"
    ]
    assert "binary_sha256" not in fixture["payload"]
    assert fixture["payload"]["unknown_pixels"] == 8192
    assert fixture["payload"]["known_white_pixels"] == 606208
    assert fixture["payload"]["roi_cs1"]["x0"] == 224
    assert fixture["payload"]["roi_cs2"]["x0"] == 736


def test_u07_is_described_as_separate_and_not_materialized() -> None:
    value = campaign.describe_design_separation()

    assert value["shared_binary_allowed"] is False
    assert value["u07_action_materialized"] is False
    assert value["u07"]["candidate_id"] == "U07"
    assert value["u07"]["materialization_state"] == (
        "DEFERRED_SEPARATE_BUILD_REVIEW_AND_AUTHORIZATION"
    )
    assert value["hardware_execution_authorized"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("candidate_id", "U07"), ("candidate_code", 7)],
)
def test_u04_compiler_rejects_u07_build_identity(
    tmp_path: Path, field: str, replacement: object
) -> None:
    inputs = make_inputs(tmp_path)
    build = copy.deepcopy(inputs["build"])
    build[field] = replacement
    build_path = tmp_path / "u07-build.json"
    write_json(build_path, build)

    with pytest.raises(campaign.EC5CampaignError, match="only the isolated U04"):
        campaign.compile_campaign(
            inputs["panel_path"], build_path, inputs["firmware_path"]
        )


def test_u04_compiler_rejects_mixed_candidate_binary_declaration(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    build = copy.deepcopy(inputs["build"])
    build["isolation"]["embedded_candidate_codes"] = [4, 7]
    build["isolation"]["candidate_fixture_count"] = 2
    build["isolation"]["contains_u07_fixture"] = True
    build_path = tmp_path / "mixed-build.json"
    write_json(build_path, build)

    with pytest.raises(campaign.EC5CampaignError, match="U04-only"):
        campaign.compile_campaign(
            inputs["panel_path"], build_path, inputs["firmware_path"]
        )


def test_actual_firmware_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    inputs["firmware_path"].write_bytes(b"different-firmware-bytes")

    with pytest.raises(campaign.EC5CampaignError, match="actual firmware bytes"):
        campaign.compile_campaign(*_paths(inputs))


def test_manifest_payload_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    build = copy.deepcopy(inputs["build"])
    build["manifest_payload_sha256"] = "f" * 64
    build_path = tmp_path / "wrong-manifest.json"
    write_json(build_path, build)

    with pytest.raises(campaign.EC5CampaignError, match="manifest payload digest"):
        campaign.compile_campaign(
            inputs["panel_path"], build_path, inputs["firmware_path"]
        )


def test_resealed_campaign_tamper_is_rejected_by_full_replay(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    altered = copy.deepcopy(inputs["campaign"])
    action = altered["actions"][0]
    action["frame_identity"]["frame_sha256"] = "f" * 64
    action_unsigned = dict(action)
    action_unsigned.pop("action_identity_sha256")
    action["action_identity_sha256"] = campaign.sha256(action_unsigned)
    unsigned = dict(altered)
    unsigned.pop("integrity")
    altered["integrity"] = {
        "canonical_sha256": campaign.sha256(unsigned),
        "canonical_sha256_scope": campaign.HASH_SCOPE,
    }

    with pytest.raises(campaign.EC5CampaignError, match="frozen fixture"):
        campaign.validate_campaign(altered, *_paths(inputs))


def test_compiler_performs_no_socket_or_url_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = make_inputs(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external I/O is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    value = campaign.compile_campaign(*_paths(inputs))

    assert value["classification"]["network_io_performed"] is False
    assert value["classification"]["device_io_performed"] is False
    assert value["classification"]["serial_io_performed"] is False
    assert value["classification"]["refresh_performed"] is False


def test_cli_refuses_forbidden_device_style_options() -> None:
    with pytest.raises(SystemExit):
        campaign.parse_args(["compile", "--url", "http://device.invalid"])
    with pytest.raises(SystemExit):
        campaign.parse_args(["compile", "--candidate-code", "7"])
    with pytest.raises(SystemExit):
        campaign.parse_args(["compile", "--retry", "1"])


def test_publish_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "campaign.json"
    campaign.publish_new_json(output, {"first": True}, label="test output")

    with pytest.raises(campaign.EC5CampaignError, match="could not publish"):
        campaign.publish_new_json(output, {"second": True}, label="test output")


def test_strict_json_rejects_duplicate_and_noncanonical_input(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"model":"A","model":"B"}', encoding="utf-8")
    with pytest.raises(campaign.EC5CampaignError, match="duplicate key"):
        campaign.read_strict_json(duplicate, label="duplicate")

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps({"b": 2, "a": 1}, indent=2), encoding="utf-8")
    with pytest.raises(campaign.EC5CampaignError, match="canonical JSON"):
        campaign.read_strict_json(noncanonical, label="noncanonical")
