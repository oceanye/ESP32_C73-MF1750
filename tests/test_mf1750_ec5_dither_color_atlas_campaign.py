from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools import mf1750_ec5_dither_color_atlas as offline_bundle
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign
from tools import mf1750_ec5_dither_color_atlas_contract as contract


FROZEN_CONTRACT_ID = "4bc11030bf72426d4ddeb4cf7469f7053889f8547404e2e0c1335ebb4c77105c"
FROZEN_DESCRIPTOR_IDS = (
    "2a32f5a5769d74459d80d9e5ee7ad5b9103c898437a91176bef090ce1d6b9ddc",
    "a9a9b40129ffd5c005466ef3976e2c5171b9eb9d2e1bb94fabb756fb50bf0757",
)
FROZEN_ACTION_IDS = (
    "ef6458113f5f8d9bbbaf3d62dfbd1e4160b732b4bdbcdc4375097ef3013b0a2c",
    "35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3",
)
FROZEN_FRAME_AND_DTM_SHA256 = (
    (
        "3b65803a558e91ad2112a75b158a1b696666c015829ce9fd0bce401ba96a44b7",
        "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
        "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
    ),
    (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    ),
)
PANEL = {
    "board_id": "ESP32-C73",
    "model": "MF1750-C73",
    "pcb_revision": "rev-a1",
    "serial": "MF750M009T6420/1582643AGY44",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(campaign.canonical_json_bytes(value))


def _write_sealed(path: Path, unsigned: dict[str, Any]) -> dict[str, Any]:
    root = campaign._seal(unsigned)  # noqa: SLF001
    _write_json(path, root)
    return root


def _identity_artifacts() -> tuple[bytes, bytes]:
    identity_payload = b"\0".join(
        item.encode("ascii")
        for item in campaign._identity_needles()  # noqa: SLF001
    )
    elf = b"\x7fELF" + b"fixture-elf\0" + identity_payload
    binary = bytearray(b"\0" * 208)
    binary[0] = 0xE9
    binary[32:36] = bytes.fromhex("3254cdab")
    binary[176:208] = hashlib.sha256(elf).digest()
    binary.extend(b"fixture-bin\0")
    binary.extend(identity_payload)
    return bytes(binary), elf


def _patch_frozen_reference(
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    path: Path,
    root: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        campaign,
        f"EXPECTED_MATRIX_{name}_FILE_SHA256",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        campaign,
        f"EXPECTED_MATRIX_{name}_CANONICAL_SHA256",
        root["integrity"]["canonical_sha256"],
    )


def _prepare_real_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    campaign_file = tmp_path / "campaign.json"
    campaign.generate_campaign(campaign_file)

    atlas_bundle = tmp_path / "offline-atlas"
    offline_bundle.build_bundle(atlas_bundle)

    binary, elf = _identity_artifacts()
    binary_file = tmp_path / "firmware.bin"
    elf_file = tmp_path / "firmware.elf"
    binary_file.write_bytes(binary)
    elf_file.write_bytes(elf)

    panel_file = tmp_path / "panel.json"
    _write_json(panel_file, PANEL)
    assert hashlib.sha256(panel_file.read_bytes()).hexdigest() == (
        campaign.EXPECTED_MATRIX_PANEL_FILE_SHA256
    )

    matrix_release_file = tmp_path / "matrix-release.json"
    matrix_result_file = tmp_path / "matrix-result.json"
    matrix_observation_file = tmp_path / "matrix-observation.json"
    matrix_release_root = _write_sealed(
        matrix_release_file,
        {"schema_version": 1, "kind": "fixture-matrix-release"},
    )
    matrix_result_root = _write_sealed(
        matrix_result_file,
        {"schema_version": 1, "kind": "fixture-matrix-result"},
    )
    matrix_observation_root = _write_sealed(
        matrix_observation_file,
        {"schema_version": 1, "kind": "fixture-matrix-observation"},
    )

    claim_registry = tmp_path / "matrix-claims"
    claim_registry.mkdir()
    claim_file = claim_registry / f"{campaign.FIRST_PREDECESSOR_ACTION_ID}.json"
    claim_root = _write_sealed(
        claim_file,
        {"schema_version": 1, "kind": "fixture-matrix-claim"},
    )
    claim_reference = {
        "file": str(claim_file.resolve()),
        "bytes": len(claim_file.read_bytes()),
        "file_sha256": hashlib.sha256(claim_file.read_bytes()).hexdigest(),
        "integrity_sha256": claim_root["integrity"]["canonical_sha256"],
        "state": "permanently_claimed_before_first_arm_post",
    }
    result = {
        "ordinal": 3,
        "outcome": "complete_pass",
        "state": "authorization_permanently_consumed_do_not_rerun",
        "action": {
            "action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
            "role": "OTP_WHITE_RECOVERY",
        },
        "claim": claim_reference,
        "preflight": {"boot_nonce": campaign.EXPECTED_MATRIX_BOOT_NONCE},
    }
    observation = {
        "ordinal": 3,
        "sequence_gate_pass": True,
        "automatic_next_action_authorized": False,
        "retry_authorized": False,
        "recovery_authorized": False,
        "visual": {
            "full_clean_white": True,
            "no_unexpected_residual": True,
        },
        "supervised": {
            "electrical_normal": True,
            "esp32_did_not_restart": True,
        },
    }
    context = SimpleNamespace(
        release_root={
            "panel": PANEL,
            "panel_file": {"file_sha256": campaign.EXPECTED_MATRIX_PANEL_FILE_SHA256},
        }
    )
    monkeypatch.setattr(campaign.matrix_once, "load_release", lambda _path: context)
    monkeypatch.setattr(
        campaign.matrix_once,
        "validate_result",
        lambda _context, _path, **_kwargs: deepcopy(result),
    )
    monkeypatch.setattr(
        campaign.matrix_once,
        "validate_observation",
        lambda _context, _path, **_kwargs: deepcopy(observation),
    )
    _patch_frozen_reference(
        monkeypatch,
        name="RELEASE",
        path=matrix_release_file,
        root=matrix_release_root,
    )
    _patch_frozen_reference(
        monkeypatch,
        name="RESULT",
        path=matrix_result_file,
        root=matrix_result_root,
    )
    _patch_frozen_reference(
        monkeypatch,
        name="OBSERVATION",
        path=matrix_observation_file,
        root=matrix_observation_root,
    )
    _patch_frozen_reference(
        monkeypatch,
        name="CLAIM",
        path=claim_file,
        root=claim_root,
    )
    return {
        "campaign_file": campaign_file,
        "firmware_binary": binary_file,
        "firmware_elf": elf_file,
        "panel_file": panel_file,
        "offline_bundle_dir": atlas_bundle,
        "matrix_release_file": matrix_release_file,
        "anchor_result_file": matrix_result_file,
        "anchor_observation_file": matrix_observation_file,
        "anchor_claim_registry": claim_registry,
        "output_file": tmp_path / "release.json",
    }


def test_two_actions_have_frozen_chain_frames_and_identical_half_streams() -> None:
    contract.validate_contract()
    root = campaign.build_campaign()
    actions = root["actions"]

    assert root["firmware_contract_id"] == FROZEN_CONTRACT_ID
    assert root["firmware_contract"]["contract_id"] == FROZEN_CONTRACT_ID
    assert root["first_predecessor_action_id"] == (campaign.FIRST_PREDECESSOR_ACTION_ID)
    assert root["action_count"] == 2
    assert [action["ordinal"] for action in actions] == [1, 2]
    assert [action["role"] for action in actions] == list(contract.ROLES)
    assert tuple(action["descriptor_id"] for action in actions) == (
        FROZEN_DESCRIPTOR_IDS
    )
    assert tuple(action["action_id"] for action in actions) == FROZEN_ACTION_IDS

    for index, (action, frozen_hashes) in enumerate(
        zip(actions, FROZEN_FRAME_AND_DTM_SHA256, strict=True)
    ):
        expected_internal_prior = None if index == 0 else FROZEN_ACTION_IDS[0]
        assert (
            action["action_identity_preimage"]["prior_static_action_id"]
            == expected_internal_prior
        )
        frame = action["frame"]["frame"]
        controllers = frame["controllers"]
        assert frame["bytes"] == 307_200
        assert [item["controller"] for item in controllers] == ["CS1", "CS2"]
        assert [item["source_half"] for item in controllers] == [0, 1]
        assert [item["bytes"] for item in controllers] == [153_600, 153_600]
        assert (
            frame["sha256"],
            controllers[0]["sha256"],
            controllers[1]["sha256"],
        ) == frozen_hashes
        assert controllers[0]["sha256"] == controllers[1]["sha256"]
        assert action["frame_sha256"] == frame["sha256"]
        assert action["cs1_dtm_sha256"] == controllers[0]["sha256"]
        assert action["cs2_dtm_sha256"] == controllers[1]["sha256"]

    assert actions[0]["frame"]["spatial_dithering"] is True
    assert actions[1]["frame"]["spatial_dithering"] is False


def test_campaign_has_new_device_identity_and_no_runtime_or_electrical_writes() -> None:
    root = campaign.build_campaign()
    firmware_contract = root["firmware_contract"]

    assert root["kind"] == campaign.CAMPAIGN_KIND
    assert root["classification"] == contract.CLASSIFICATION
    assert root["nvs_contract"] == {
        "namespace": "mf1750_dca",
        "key": "cursor_v1",
        "ordinal_base": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 3,
        "phase_encoding": ["READY", "ARMED", "CONSUMED", "FAULT"],
    }
    assert root["device_contract"]["endpoints"] == campaign.ENDPOINTS
    assert all(
        endpoint.startswith("/api/ec5/dither-color-atlas/")
        for endpoint in campaign.ENDPOINTS.values()
    )
    assert root["classification_contract"] == {
        "profile_source": "factory_otp",
        "runtime_lut_or_waveform_changed": False,
        "spatial_dither_color_comparison": True,
        "single_pixel_multi_pigment_claim": False,
        "physical_colour_claim": False,
        "device_accessed_by_this_compiler": False,
        "visible_refresh_authorized_by_this_compiler": False,
    }
    assert firmware_contract["profile_source"] == "factory_otp"
    assert firmware_contract["custom_lut_or_waveform"] is False
    assert firmware_contract["runtime_lut_write"] is False
    assert firmware_contract["electrical_parameter_write"] is False
    assert firmware_contract["raw_frame_ingress"] is False
    assert firmware_contract["startup_refresh"] is False


def test_compile_validate_and_describe_are_deterministic_and_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first_file = tmp_path / "first.json"
    second_file = tmp_path / "second.json"
    first = campaign.generate_campaign(first_file)
    second = campaign.generate_campaign(second_file)

    assert first == second == campaign.build_campaign()
    assert first_file.read_bytes() == second_file.read_bytes()
    assert campaign.validate_campaign(first_file)["actions"] == first["actions"]
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="overwrite"):
        campaign.generate_campaign(first_file)

    assert campaign.main(["validate", "--campaign", str(first_file)]) == 0
    validate_output = json.loads(capsys.readouterr().out)
    assert validate_output["action_count"] == 2
    assert campaign.main(["describe", "--ordinal", "1"]) == 0
    described = json.loads(capsys.readouterr().out)
    assert described["external_predecessor_required"] is True
    assert described["visible_refresh_authorized"] is False
    assert described["action"]["action_id"] == FROZEN_ACTION_IDS[0]
    assert campaign.main(["describe", "--ordinal", "3"]) == 2
    assert "outside campaign" in capsys.readouterr().err

    tampered = deepcopy(first)
    tampered["actions"][0]["frame"]["runtime_lut_write"] = True
    _write_json(tmp_path / "tampered.json", tampered)
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="integrity"):
        campaign.validate_campaign(tmp_path / "tampered.json")

    tampered.pop("integrity")
    _write_json(
        tmp_path / "resealed-tampered.json",
        campaign._seal(tampered),  # noqa: SLF001
    )
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="differs"):
        campaign.validate_campaign(tmp_path / "resealed-tampered.json")


def test_validate_rejects_duplicate_keys_non_regular_and_symlink(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError, match="duplicate JSON key"
    ):
        campaign.validate_campaign(duplicate)

    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError,
        match="regular non-symlink file",
    ):
        campaign.validate_campaign(directory)

    target = tmp_path / "campaign.json"
    campaign.generate_campaign(target)
    link = tmp_path / "campaign-link.json"
    try:
        link.symlink_to(target.name)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError,
        match="regular non-symlink file",
    ):
        campaign.validate_campaign(link)


def test_materializer_does_not_emit_without_firmware_or_anchor(tmp_path: Path) -> None:
    campaign_file = tmp_path / "campaign.json"
    campaign.generate_campaign(campaign_file)
    output = tmp_path / "must-not-exist.json"
    missing = tmp_path / "missing"
    arguments = {
        "campaign_file": campaign_file,
        "firmware_binary": missing,
        "firmware_elf": missing,
        "panel_file": missing,
        "offline_bundle_dir": missing,
        "matrix_release_file": missing,
        "anchor_result_file": missing,
        "anchor_observation_file": missing,
        "anchor_claim_registry": missing,
        "output_file": output,
    }
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError,
        match="could not read dither color-atlas firmware binary",
    ):
        campaign.materialize_real_release(**arguments)
    assert not output.exists()

    binary, elf = _identity_artifacts()
    arguments["firmware_binary"] = tmp_path / "firmware.bin"
    arguments["firmware_elf"] = tmp_path / "firmware.elf"
    arguments["firmware_binary"].write_bytes(binary)
    arguments["firmware_elf"].write_bytes(elf)
    arguments["panel_file"] = tmp_path / "panel.json"
    _write_json(arguments["panel_file"], PANEL)
    with pytest.raises(RuntimeError):
        campaign.materialize_real_release(**arguments)
    assert not output.exists()


def test_binary_elf_link_requires_real_formats_and_exact_hash() -> None:
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="does not bind"):
        campaign._binary_elf_link(b"not-a-bin", b"not-an-elf")  # noqa: SLF001

    binary, elf = _identity_artifacts()
    assert campaign._binary_elf_link(binary, elf)["exact_match"] is True  # noqa: SLF001
    tampered = bytearray(binary)
    tampered[176] ^= 1
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="does not bind"):
        campaign._binary_elf_link(bytes(tampered), elf)  # noqa: SLF001


def test_materialize_real_and_validate_release_replay_all_bound_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = _prepare_real_fixture(tmp_path, monkeypatch)
    release = campaign.materialize_real_release(**arguments)
    checked = campaign.validate_materialized_release(arguments["output_file"])

    assert release["kind"] == campaign.RELEASE_KIND
    assert release["evidence_mode"] == campaign.REAL_MODE
    assert release["execution_eligible"] is True
    assert release["predecessor_binding"]["action_id"] == (
        campaign.FIRST_PREDECESSOR_ACTION_ID
    )
    assert release["predecessor_binding"]["ordinal"] == 3
    assert release["predecessor_binding"]["clean_white_confirmed"] is True
    assert release["panel"] == PANEL
    assert release["offline_atlas_bundle"]["roi_count"] == 70
    assert checked["action_count"] == 2
    assert checked["execution_eligible"] is True
    assert checked["visible_refresh_authorized_by_release"] == 0
    assert checked["predecessor_action_id"] == (campaign.FIRST_PREDECESSOR_ACTION_ID)

    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="overwrite"):
        campaign.materialize_real_release(**arguments)


def test_release_rejects_resealed_policy_tamper_and_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = _prepare_real_fixture(tmp_path, monkeypatch)
    release = campaign.materialize_real_release(**arguments)

    tampered = deepcopy(release)
    tampered.pop("integrity")
    tampered["safety"]["automatic_retry"] = True
    tampered_file = tmp_path / "resealed-policy-tamper.json"
    _write_json(tampered_file, campaign._seal(tampered))  # noqa: SLF001
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="safety contract"):
        campaign.validate_materialized_release(tampered_file)

    arguments["firmware_binary"].write_bytes(
        arguments["firmware_binary"].read_bytes() + b"tamper"
    )
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="bytes differ"):
        campaign.validate_materialized_release(arguments["output_file"])


def test_materializer_rejects_anchor_identity_and_panel_drift_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = _prepare_real_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(campaign, "EXPECTED_MATRIX_RESULT_FILE_SHA256", "0" * 64)
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError,
        match="result frozen identity differs",
    ):
        campaign.materialize_real_release(**arguments)
    assert not arguments["output_file"].exists()

    monkeypatch.undo()
    panel_drift_root = tmp_path / "panel-drift"
    panel_drift_root.mkdir()
    arguments = _prepare_real_fixture(panel_drift_root, monkeypatch)
    _write_json(
        arguments["panel_file"],
        {**PANEL, "serial": "A-DIFFERENT-PANEL"},
    )
    with pytest.raises(
        campaign.DitherColorAtlasCampaignError,
        match="current panel file",
    ):
        campaign.materialize_real_release(**arguments)
    assert not arguments["output_file"].exists()


def test_authorizations_are_unique_and_never_imply_chaining() -> None:
    root = campaign.build_campaign()
    authorizations = [
        campaign.required_authorization(action) for action in root["actions"]
    ]
    assert len(set(authorizations)) == 2
    for ordinal, (action, authorization) in enumerate(
        zip(root["actions"], authorizations, strict=True), start=1
    ):
        assert authorization == (
            "AUTHORIZE_ONE_VISIBLE_EC5_DITHER_ATLAS_"
            f"ORDINAL_{ordinal:02d}__ACTION_{action['action_id'].upper()}"
            "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
        )
        assert action["maximum_arm_posts"] == 1
        assert action["maximum_execute_posts"] == 1
        assert action["retry_allowed"] is False
        assert action["automatic_chaining"] is False
    device = root["device_contract"]
    assert device["automatic_chaining"] is False
    assert device["automatic_retry"] is False
    assert device["automatic_recovery"] is False
    with pytest.raises(campaign.DitherColorAtlasCampaignError, match="malformed"):
        campaign.required_authorization({"ordinal": True, "action_id": "bad"})


def test_current_matrix_ordinal3_white_anchor_replays_when_evidence_is_present() -> (
    None
):
    hardware = campaign.REPO_ROOT / ".test-output" / "hardware"
    matrix_release = (
        hardware
        / "MF1750_EC5_OTP_TRANSITION_MATRIX_RELEASE_OFFLINE_20260810_V1"
        / "otp-transition-matrix-real-release.json"
    )
    live = hardware / "MF1750_EC5_OTP_TRANSITION_MATRIX_LIVE_20260810_V1"
    result = live / "ordinal-03-white-result.json"
    observation = live / "ordinal-03-white-observation.json"
    claims = hardware / ".mf1750_ec5_otp_transition_matrix_claims"
    if not all(path.exists() for path in (matrix_release, result, observation, claims)):
        pytest.skip("current matrix ordinal3 evidence is not present in this workspace")

    binding = campaign._matrix_white_anchor(  # noqa: SLF001
        matrix_release_file=matrix_release,
        result_file=result,
        observation_file=observation,
        claim_registry=claims,
    )
    assert binding["action_id"] == campaign.FIRST_PREDECESSOR_ACTION_ID
    assert binding["result"]["file_sha256"] == (
        campaign.EXPECTED_MATRIX_RESULT_FILE_SHA256
    )
    assert binding["observation"]["file_sha256"] == (
        campaign.EXPECTED_MATRIX_OBSERVATION_FILE_SHA256
    )
    assert binding["claim"]["file_sha256"] == (
        campaign.EXPECTED_MATRIX_CLAIM_FILE_SHA256
    )
    assert binding["clean_white_confirmed"] is True
