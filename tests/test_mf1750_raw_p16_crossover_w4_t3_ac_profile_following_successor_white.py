from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as t3,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3,
)
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as w4,
)


ROOT = Path(__file__).resolve().parents[1]


def test_w4_exactly_binds_t3_four_tuple_and_one_white_action() -> None:
    report = w4.build_white_report()
    source = t3.build_report()
    action = report["action"]
    source_action = source["actions"][0]
    assert {
        "campaign_id": action["source_campaign_id"],
        "contract_id": action["source_contract_id"],
        "descriptor_id": action["source_descriptor_id"],
        "action_id": action["source_action_id"],
    } == {
        "campaign_id": source["contract"]["campaign_id"],
        "contract_id": source["contract_id"],
        "descriptor_id": source_action["descriptor_id"],
        "action_id": source_action["action_id"],
    }
    contract = report["contract"]
    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_w4_identity_route_nvs_claims_and_output_are_fresh() -> None:
    report = w4.build_white_report()
    prior = w3.build_white_report()
    assert report["contract_id"] != prior["contract_id"]
    assert report["action"]["descriptor_id"] != prior["action"]["descriptor_id"]
    assert report["action"]["action_id"] != prior["action"]["action_id"]
    assert report["contract"]["campaign_id"] != prior["contract"]["campaign_id"]
    assert report["contract"]["base_route"] != prior["contract"]["base_route"]
    assert report["contract"]["nvs_namespace"] != prior["contract"]["nvs_namespace"]
    validation = once.dry_validate(verify_artifacts=False)
    assert validation["result"] == "PASS"
    assert validation["source_t3_campaign_contract_descriptor_action_exact"] is True
    assert validation["network_requests"] == 0
    assert validation["relay_accessed"] is False
    assert all(
        endpoint.startswith(w4.CONFIG.base_route + "/")
        for endpoint in validation["endpoint_set"].values()
    )
    assert "W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE" in validation["output_root"]
    assert (
        "w4_t3_ac_profile_following_successor_white_claims" in validation["claim_root"]
    )


def test_w4_cpp_and_ini_bind_exact_pack_identity_and_routes() -> None:
    report = w4.build_white_report()
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_identity.inc"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT
        / "platformio.raw_p16_crossover_w4_t3_ac_profile_following_successor_white_v1.ini"
    ).read_text(encoding="utf-8")
    for value in (
        w4.CONFIG.campaign_id,
        w4.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_campaign_id"],
        report["action"]["source_contract_id"],
        report["action"]["source_descriptor_id"],
        report["action"]["source_action_id"],
        w4.marker(),
    ):
        assert value in identity
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert (
            "w4-after-t3-ac-profile-following-successor-white-v1/" + endpoint in program
        )
    assert (
        "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_BUILD=1"
    ) in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


def test_w4_artifact_binding_matches_files_after_seal() -> None:
    if w4.WHITE_ARTIFACTS[w4.STAGE]["bin_bytes"] == 0:
        pytest.skip("isolated W4 artifacts not sealed yet")
    validation = once.dry_validate()
    assert validation["artifacts_verified"] is True
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_w4_builder_issues_one_compile_only_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []
    monkeypatch.setattr(build, "prebuild_validate", lambda: {"result": "PASS"})
    monkeypatch.setattr(
        build.runner,
        "dry_validate",
        lambda **_kwargs: {"result": "PASS", "artifacts_verified": True},
    )
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )
    result = build.build(pio=pio)
    assert result["result"] == "PASS"
    assert commands == [[str(pio.resolve()), "run", "-c", build.CONFIG]]
    assert "upload" not in commands[0]
