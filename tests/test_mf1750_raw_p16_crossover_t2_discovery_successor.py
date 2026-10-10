from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_build as builder
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_once as once
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_authority_is_exact_screening_only_and_not_formal() -> None:
    value = pack.validate_coarse_authority()
    assert hashlib.sha256(pack.COARSE_AUTHORITY_PATH.read_bytes()).hexdigest() == (
        pack.COARSE_AUTHORITY_FILE_SHA256
    )
    assert value["eligible_for_t2_discovery"] is True
    assert value["screening_only"] is True
    assert value["formal_gate_evaluated"] is False
    assert value["formal_advance_to_t2_permitted"] is False
    assert value["qualified_colour_count"] == 0
    assert value["integrity"]["sha256"] == pack.COARSE_AUTHORITY_CANONICAL_SHA256


def test_authority_tamper_fails_closed(tmp_path: Path) -> None:
    value = json.loads(pack.COARSE_AUTHORITY_PATH.read_text(encoding="utf-8"))
    value["eligible_for_t2_discovery"] = False
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(pack.DiscoveryPackError, match="byte count|SHA-256"):
        pack.validate_coarse_authority(path)


def test_successor_reuses_exact_t2_ca_frame_dtm_and_waveform() -> None:
    successor = pack.build_report()
    source = legacy.build_report("t2-ca")
    action = successor["actions"][0]
    old_action = source["actions"][0]
    assert action["frame"] == old_action["frame"]
    assert action["cs1_dtm"] == old_action["cs1_dtm"]
    assert action["cs2_dtm"] == old_action["cs2_dtm"]
    assert action["waveform_binding"] == old_action["waveform_binding"]
    assert (
        action["global_header"],
        action["waveform_binding"]["cs1"]["name"],
        action["waveform_binding"]["cs2"]["name"],
    ) == ("commented", "commented", "active")


def test_successor_identity_and_safety_boundaries_are_fresh() -> None:
    successor = pack.build_report()
    source = legacy.build_report("t2-ca")
    contract = successor["contract"]
    action = successor["actions"][0]
    assert contract["campaign_id"] != source["contract"]["campaign_id"]
    assert contract["test_id"] != source["contract"]["test_id"]
    assert contract["base_route"] != source["contract"]["base_route"]
    assert contract["nvs_namespace"] != source["contract"]["nvs_namespace"]
    assert successor["contract_id"] != source["contract_id"]
    assert action["descriptor_id"] != source["actions"][0]["descriptor_id"]
    assert action["action_id"] != source["actions"][0]["action_id"]
    assert contract["action_count"] == 1
    assert contract["screening_only"] is True
    assert contract["discovery_only"] is True
    assert contract["formal_gate_evaluated"] is False
    assert contract["formal_advance_to_t2_permitted"] is False
    assert contract["qualified_colours"] == 0
    assert contract["retry"] is False
    assert contract["recovery"] is False
    assert contract["automatic_chaining"] is False
    assert len(contract["nvs_namespace"]) <= 15


def test_dry_validation_and_reviewed_artifacts_pass_without_io() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["authority_verified"] is True
    assert value["artifacts_verified"] is True
    assert value["same_frame_dtm_and_ca_waveform_as_reviewed_t2"] is True
    assert value["network_requests"] == 0
    assert value["relay_accessed"] is False
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_prebuild_does_not_require_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("prebuild touched an artifact")

    monkeypatch.setattr(once, "_verify_artifacts", forbidden)
    value = once.dry_validate(verify_artifacts=False)
    assert value["result"] == "PASS"
    assert value["artifacts_verified"] is False


def test_configured_host_uses_only_successor_identity() -> None:
    host = once.configure()
    report = pack.build_report()
    runner = host.base.runner
    assert runner.CAMPAIGN_ID == pack.CONFIG.campaign_id
    assert runner.CONTRACT_ID == report["contract_id"]
    assert runner.NVS_NAMESPACE == pack.CONFIG.nvs_namespace
    assert runner.NVS_KEY == pack.CONFIG.nvs_key
    assert runner.ACTION_IDS == (report["actions"][0]["action_id"],)
    assert runner.ENDPOINTS["execute"] == f"{pack.CONFIG.base_route}/execute"
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V1"
    )


def test_runner_guards_fail_before_request(tmp_path: Path) -> None:
    host = once.configure()
    calls: list[object] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    with pytest.raises(host.base.runner.RecheckError, match="J2-ON"):
        host.run_once(
            "http://192.168.1.11",
            1,
            claims=tmp_path / "claims-a",
            output=tmp_path / "a.json",
            requester=requester,
            confirm_external_pre_white=True,
        )
    with pytest.raises(host.base.runner.RecheckError, match="pre-white"):
        host.run_once(
            "http://192.168.1.11",
            1,
            claims=tmp_path / "claims-b",
            output=tmp_path / "b.json",
            requester=requester,
            confirm_j2_on=True,
            confirm_external_pre_white=False,
        )
    assert calls == []


def test_discovery_boundary_rejects_missing_or_formal_claim() -> None:
    host = once.configure()
    valid = {
        "coarse_discovery_authority": pack.coarse_authority_binding(),
        "coarse_discovery_only": True,
        "formal_gate_evaluated": False,
        "formal_advance_to_t2_permitted": False,
    }
    once._validate_discovery_boundary(host, valid)  # noqa: SLF001
    for update in (
        {"coarse_discovery_authority": {}},
        {"coarse_discovery_only": False},
        {"formal_gate_evaluated": True},
        {"formal_advance_to_t2_permitted": True},
    ):
        candidate = deepcopy(valid)
        candidate.update(update)
        with pytest.raises(host.base.runner.RecheckError):
            once._validate_discovery_boundary(host, candidate)  # noqa: SLF001


def test_cpp_is_mechanically_equivalent_except_identity_adapter() -> None:
    old_main = (ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_main.cpp").read_text(
        encoding="utf-8"
    )
    new_main = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main.cpp"
    ).read_text(encoding="utf-8")
    new_main = "\n".join(new_main.splitlines()[2:]) + "\n"
    normalized_main = new_main.replace(
        "MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_BUILD",
        "MF1750_RAW_P16_CROSSOVER_POSBAL_BUILD",
    ).replace(
        "ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc",
        "ec5_raw_p16_crossover_position_balanced_main_config.inc",
    )
    assert normalized_main.rstrip() == old_main.rstrip()

    old_driver = (
        ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_driver.inc"
    ).read_text(encoding="utf-8")
    new_driver = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_driver.inc"
    ).read_text(encoding="utf-8")
    new_driver = "\n".join(new_driver.splitlines()[3:]) + "\n"
    normalized_driver = (
        new_driver.replace(
            "MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_BUILD",
            "MF1750_RAW_P16_CROSSOVER_POSBAL_BUILD",
        )
        .replace(
            "ec5_raw_p16_crossover_t2_discovery_successor_identity.inc",
            "ec5_raw_p16_crossover_position_balanced_identity.inc",
        )
        .replace(
            "mf1750_raw_p16_crossover_t2_discovery_successor",
            "mf1750_raw_p16_crossover_position_balanced_current",
        )
    )
    assert normalized_driver.rstrip() == old_driver.rstrip()


def test_cpp_and_ini_bind_final_identity_and_no_upload_target() -> None:
    report = pack.build_report()
    identity = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "platformio.raw_p16_crossover_t2_ca_coarse_discovery_successor_v1.ini"
    ).read_text(encoding="utf-8")
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    for value in (
        report["contract_id"],
        report["actions"][0]["descriptor_id"],
        report["actions"][0]["action_id"],
        pack.CONFIG.campaign_id,
        pack.CONFIG.test_id,
        pack.CONFIG.base_route,
        pack.CONFIG.nvs_namespace,
    ):
        assert value in identity or value in main_config
    assert pack.COARSE_AUTHORITY_FILE_SHA256 in main_config
    assert pack.COARSE_AUTHORITY_CANONICAL_SHA256 in main_config
    assert "upload_protocol" not in config
    assert "upload_command" not in config
    assert "EPD_ENABLE_TEST_PATTERN=0" in config


def test_build_bootstrap_is_one_compile_only_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []
    validations: list[bool] = []

    def validate(
        *, verify_authority: bool = True, verify_artifacts: bool = True
    ) -> dict[str, object]:
        assert verify_authority is True
        validations.append(verify_artifacts)
        return {"result": "PASS", "artifacts_verified": verify_artifacts}

    def run(command: list[str], **_kwargs: object) -> None:
        commands.append(command)

    monkeypatch.setattr(builder.runner, "dry_validate", validate)
    monkeypatch.setattr(builder.subprocess, "run", run)
    value = builder.build(pio=pio)
    assert value["result"] == "PASS"
    assert validations == [False, True]
    assert len(commands) == 1
    assert commands[0][1:3] == ["run", "-c"]
    assert "upload" not in commands[0]
