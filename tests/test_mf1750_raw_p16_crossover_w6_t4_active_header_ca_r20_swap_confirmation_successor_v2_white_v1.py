from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as t4,
)
from tools import (
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as w5,
)
from tools import (
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack as w6,
)


ROOT = Path(__file__).resolve().parents[1]


def test_w6_exactly_binds_t4_four_tuple_and_one_white_action() -> None:
    report = w6.build_white_report()
    source = t4.build_report()
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
    bound = report["contract"]["source"]
    assert bound["stage"] == t4.STAGE
    assert bound["round"] == 4
    assert bound["global_header"] == "active"
    assert bound["profile_id"] == (
        "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
    )
    assert bound["waveform_binding"]["cs1"]["name"] == "commented"
    assert bound["waveform_binding"]["cs2"]["name"] == "active"
    assert bound["frame_sha256"] == source_action["frame"]["sha256"]
    assert bound["v1_diagnostic_failure_authority"] == source["contract"][
        "v1_diagnostic_failure_authority"
    ]
    failure = bound["v1_diagnostic_failure_authority"]
    assert failure["outcome"] == "j2_off_diagnostic_failed_no_claim"
    assert failure["get"] == 4
    assert failure["post"] == 0
    assert failure["permanent_claims_created"] == 0
    assert failure["visible_refreshes"] == 0
    assert failure["driver_calls"] == 0
    assert failure["terminal_state"] == "NOT_EXECUTED"
    assert failure["safe_to_supersede_without_containment"] is True
    contract = report["contract"]
    assert contract["profile_id"] == "WF23_25"
    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_w6_identity_route_nvs_claims_and_output_are_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = w6.build_white_report()
    prior = w5.build_white_report()
    assert report["contract_id"] != prior["contract_id"]
    assert report["action"]["descriptor_id"] != prior["action"]["descriptor_id"]
    assert report["action"]["action_id"] != prior["action"]["action_id"]
    assert report["contract"]["campaign_id"] != prior["contract"]["campaign_id"]
    assert report["contract"]["base_route"] != prior["contract"]["base_route"]
    assert report["contract"]["nvs_namespace"] != prior["contract"]["nvs_namespace"]
    assert report["action"]["action_id"] not in t4.non_reusable_action_ids()
    assert w6.CONFIG.nvs_namespace == "p16w6t4ca2_v1"
    assert w6.CONFIG.nvs_key == "used_w6t4ca2"
    assert w6.CONFIG.environment == "ec5_p16_w6t4ca2_w1"
    assert w6.CONFIG.build_root == "b-w6t4ca2-w1"
    assert w6.CONFIG.base_route == (
        "/api/ec5/raw-p16-crossover-w6-after-t4-active-header-ca-r20-swap-"
        "confirmation-successor-v2-white-v1"
    )
    monkeypatch.setattr(t4, "dry_validate", lambda: {"result": "PASS"})
    validation = once.dry_validate(verify_artifacts=False)
    assert validation["result"] == "PASS"
    assert validation["source_t4_campaign_contract_descriptor_action_exact"] is True
    assert validation["source_t4_v1_failed_no_claim_diagnostic_exact"] is True
    assert validation["network_requests"] == 0
    assert validation["relay_accessed"] is False
    assert all(
        endpoint.startswith(w6.CONFIG.base_route + "/")
        for endpoint in validation["endpoint_set"].values()
    )
    assert (
        "W6_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE"
        in validation["output_root"]
    )
    assert (
        "w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_claims"
        in (validation["claim_root"])
    )


def test_w6_rejects_near_miss_t4_profile_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = deepcopy(t4.build_report())
    report["actions"][0]["waveform_binding"]["cs1"]["name"] = "active"
    monkeypatch.setattr(w6.source, "build_report", lambda: deepcopy(report))
    with pytest.raises(w6.W6PackError, match="source or V1 failure binding differs"):
        w6.dry_validate(verify_source=False)


def test_w6_cpp_ini_and_identity_bind_exact_report() -> None:
    report = w6.build_white_report()
    identity = (
        ROOT
        / (
            "src/ec5_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v2_white_v1_identity.inc"
        )
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT
        / (
            "platformio.raw_p16_crossover_w6_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v2_white_v1.ini"
        )
    ).read_text(encoding="utf-8")
    for value in (
        w6.CONFIG.campaign_id,
        w6.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_campaign_id"],
        report["action"]["source_contract_id"],
        report["action"]["source_descriptor_id"],
        report["action"]["source_action_id"],
        w6.marker(),
    ):
        assert value in identity
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert (
            "w6-after-t4-active-header-ca-r20-swap-confirmation-successor-v2-white-v1/" + endpoint
            in program
        )
    selector = (
        "MF1750_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_V2_WHITE_V1_BUILD"
    )
    assert selector in program
    assert f"{selector}=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


def test_w6_contains_no_hard_coded_device_ip() -> None:
    paths = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack.py",
        ROOT
        / "tools/mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_once.py",
        ROOT
        / "platformio.raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1.ini",
    )
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "192.168." not in serialized
    with pytest.raises(SystemExit):
        once._parse_args(["diagnose-white-j2-off", "--confirm-j2-off"])  # noqa: SLF001


@pytest.mark.parametrize(
    "arguments",
    (
        [
            "diagnose-white-j2-off",
            "--base-url",
            "http://not-used.invalid",
            "--confirm-j2-off",
        ],
        [
            "run-white",
            "--base-url",
            "http://not-used.invalid",
            "--confirm-j2-on",
        ],
    ),
)
def test_w6_live_cli_stops_at_unsealed_artifacts_before_device_request(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    events: list[str] = []
    host = once._configure_white()  # noqa: SLF001

    def forbidden(*_args: object, **_kwargs: object) -> None:
        events.append("device")
        raise AssertionError("device path must not run")

    monkeypatch.setattr(host, "diagnose_j2_off", forbidden)
    monkeypatch.setattr(host, "run_once", forbidden)
    monkeypatch.setattr(once, "_configure_white", lambda: host)
    monkeypatch.setattr(w6, "artifacts_are_sealed", lambda: False)
    assert once.main(arguments) == 2
    assert events == []


def test_w6_artifact_binding_matches_files_after_seal() -> None:
    if not w6.artifacts_are_sealed():
        pytest.skip("isolated W6 artifacts not sealed yet")
    validation = once.dry_validate()
    assert validation["artifacts_verified"] is True
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]
    report = w6.build_white_report()
    firmware_bin, firmware_elf = w6.white_artifact_paths()
    binary = firmware_bin.read_bytes()
    elf = firmware_elf.read_bytes()
    for value in (
        w6.CONFIG.campaign_id,
        w6.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_contract_id"],
        w6.marker(),
    ):
        encoded = value.encode("ascii")
        assert encoded in binary
        assert encoded in elf


def test_w6_builder_issues_one_compile_only_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []
    monkeypatch.setattr(build, "prebuild_validate", lambda: {"result": "PASS"})
    monkeypatch.setattr(
        build.runner,
        "dry_validate",
        lambda **_kwargs: {"result": "PASS", "artifacts_verified": True},
    )
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda command, **kwargs: (
            commands.append(command),
            environments.append(kwargs["env"]),
        ),
    )
    result = build.build(pio=pio)
    assert result["result"] == "PASS"
    assert commands == [[str(pio.resolve()), "run", "-c", build.CONFIG]]
    assert "upload" not in commands[0]
    assert environments[0]["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] == "no"
    assert environments[0]["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] == "0"
