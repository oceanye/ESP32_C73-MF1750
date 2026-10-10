from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_pack as t4_v1,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as t4_v2,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as t4,
)
from tools import (
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as w5,
)
from tools import (
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack as w6,
)
from tools import (
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_pack as w7,
)


ROOT = Path(__file__).resolve().parents[1]


def _complete_source_result() -> dict[str, object]:
    report = t4.build_report()
    action = deepcopy(report["actions"][0])
    terminal = {
        "ordinal": 1,
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "contract_id": report["contract_id"],
        "campaign_id": report["contract"]["campaign_id"],
        "role": action["role"],
        "round": action["round"],
        "profile_id": action["profile_id"],
        "global_header": action["global_header"],
        "terminal_state": "COMPLETE",
        "result": True,
        "campaign_complete": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
    }
    value: dict[str, object] = {
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-result"
        ),
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "action": action,
        "terminal_report": terminal,
    }
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": w7.sha256_bytes(w7.canonical_json(value)),
    }
    return value


def test_w7_exactly_binds_t4_v3_and_requires_complete_action() -> None:
    report = w7.build_white_report()
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
    completion = bound["completion_requirement"]
    assert completion == {
        "evidence_file_required_before_live_white": True,
        "ordinal": 1,
        "action_id": source_action["action_id"],
        "terminal_state": "COMPLETE",
        "result": True,
        "campaign_complete": True,
        "visible_refreshes": 1,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
    }
    assert report["contract"]["action_count"] == 1
    assert report["contract"]["one_visible_refresh_per_action"] is True
    assert report["contract"]["factory_otp_white_only"] is True
    assert report["contract"]["runtime_payload"] is False
    assert report["contract"]["startup_refresh"] is False


def test_w7_rejects_v1_v2_failures_and_obsolete_w5_w6() -> None:
    report = w7.build_white_report()
    failures = (
        report["contract"]["source"]["v1_diagnostic_failure_authority"],
        report["contract"]["source"]["v2_diagnostic_failure_authority"],
    )
    assert report["contract"]["rejected_failed_source_action_ids"] == [
        item["action_id"] for item in failures
    ]
    for failure in failures:
        assert failure["outcome"] == "j2_off_diagnostic_failed_no_claim"
        assert failure["get"] == 4
        assert failure["post"] == 0
        assert failure["visible_refreshes"] == 0
        assert failure["driver_calls"] == 0
        assert failure["terminal_state"] == "NOT_EXECUTED"
        assert failure["action_id"] in t4.non_reusable_action_ids()
    assert report["contract"]["rejected_obsolete_white_action_ids"] == [
        w5.build_white_report()["action"]["action_id"],
        w6.build_white_report()["action"]["action_id"],
    ]
    assert report["contract"]["obsolete_white_execution_forbidden"] is True


def test_w7_identity_route_nvs_claims_and_output_are_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = w7.build_white_report()
    own_identity = {
        "contract_id": report["contract_id"],
        "descriptor_id": report["action"]["descriptor_id"],
        "action_id": report["action"]["action_id"],
        "campaign_id": report["contract"]["campaign_id"],
        "test_id": report["contract"]["test_id"],
        "base_route": report["contract"]["base_route"],
        "nvs_namespace": report["contract"]["nvs_namespace"],
    }
    for predecessor in (t4_v1.build_report(), t4_v2.build_report(), t4.build_report()):
        prior_action = predecessor["actions"][0]
        prior_identity = {
            "contract_id": predecessor["contract_id"],
            "descriptor_id": prior_action["descriptor_id"],
            "action_id": prior_action["action_id"],
            "campaign_id": predecessor["contract"]["campaign_id"],
            "test_id": predecessor["contract"]["test_id"],
            "base_route": predecessor["contract"]["base_route"],
            "nvs_namespace": predecessor["contract"]["nvs_namespace"],
        }
        assert all(own_identity[key] != prior_identity[key] for key in own_identity)
    for prior in (w5.build_white_report(), w6.build_white_report()):
        assert report["contract_id"] != prior["contract_id"]
        assert report["action"]["descriptor_id"] != prior["action"]["descriptor_id"]
        assert report["action"]["action_id"] != prior["action"]["action_id"]
        assert report["contract"]["campaign_id"] != prior["contract"]["campaign_id"]
        assert report["contract"]["base_route"] != prior["contract"]["base_route"]
        assert report["contract"]["nvs_namespace"] != prior["contract"]["nvs_namespace"]
    assert w7.CONFIG.nvs_namespace == "p16w7t4ca3_v1"
    assert w7.CONFIG.nvs_key == "used_w7t4ca3"
    assert w7.CONFIG.environment == "ec5_p16_w7t4ca3_w1"
    assert w7.CONFIG.build_root == "b-w7t4ca3-w1"
    monkeypatch.setattr(t4, "dry_validate", lambda: {"result": "PASS"})
    validation = once.dry_validate(verify_artifacts=False)
    assert validation["result"] == "PASS"
    assert validation["source_complete_evidence_required_before_any_live_device_request"]
    assert validation["network_requests"] == 0
    assert validation["relay_accessed"] is False
    assert all(
        endpoint.startswith(w7.CONFIG.base_route + "/")
        for endpoint in validation["endpoint_set"].values()
    )


def test_w7_rejects_near_miss_failure_and_source_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = deepcopy(t4.build_report())
    report["actions"][0]["waveform_binding"]["cs1"]["name"] = "active"
    monkeypatch.setattr(w7.source, "build_report", lambda: deepcopy(report))
    with pytest.raises(w7.W7PackError, match="source or failed-attempt"):
        w7.dry_validate(verify_source=False)


def test_w7_cpp_ini_and_identity_bind_exact_report() -> None:
    report = w7.build_white_report()
    identity = (
        ROOT
        / (
            "src/ec5_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v3_white_v1_identity.inc"
        )
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT
        / (
            "platformio.raw_p16_crossover_w7_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v3_white_v1.ini"
        )
    ).read_text(encoding="utf-8")
    for value in (
        w7.CONFIG.campaign_id,
        w7.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_campaign_id"],
        report["action"]["source_contract_id"],
        report["action"]["source_descriptor_id"],
        report["action"]["source_action_id"],
        w7.marker(),
    ):
        assert value in identity
    route = (
        "w7-after-t4-active-header-ca-r20-swap-confirmation-successor-v3-white-v1"
    )
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f"{route}/{endpoint}" in program
    selector = (
        "MF1750_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_V3_WHITE_V1_BUILD"
    )
    assert selector in program
    assert f"{selector}=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


def test_w7_source_complete_evidence_accepts_only_exact_complete_v3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "t4-v3-action.json"
    value = _complete_source_result()
    evidence.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(once, "_expected_source_complete_evidence", lambda: evidence)
    binding = once._validate_source_complete_evidence()  # noqa: SLF001
    assert binding["verified"] is True
    assert binding["action_id"] == t4.build_report()["actions"][0]["action_id"]
    bad = deepcopy(value)
    bad["terminal_report"]["terminal_state"] = "NOT_EXECUTED"  # type: ignore[index]
    body = deepcopy(bad)
    body.pop("integrity")
    bad["integrity"] = {  # type: ignore[assignment]
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": w7.sha256_bytes(w7.canonical_json(body)),
    }
    evidence.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(once.W7RunnerError, match="complete-pass"):
        once._validate_source_complete_evidence()  # noqa: SLF001


@pytest.mark.parametrize(
    "arguments",
    (
        [
            "diagnose-white-j2-off",
            "--base-url",
            "http://must-not-be-used.invalid",
            "--confirm-j2-off",
        ],
        [
            "run-white",
            "--base-url",
            "http://must-not-be-used.invalid",
            "--confirm-j2-on",
        ],
    ),
)
def test_w7_live_cli_rejects_missing_source_before_host_or_get(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arguments: list[str],
) -> None:
    events: list[str] = []
    missing = tmp_path / "missing-t4-v3-action.json"
    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(once, "_expected_source_complete_evidence", lambda: missing)
    monkeypatch.setattr(once, "_configure_white", lambda: events.append("host"))
    assert once.main(arguments) == 2
    assert events == ["artifacts"]


def test_w7_live_cli_rejects_failed_source_before_host_or_get(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    evidence = tmp_path / "failed-t4-v3-action.json"
    value = _complete_source_result()
    value["outcome"] = "execute_failed"
    unsigned = deepcopy(value)
    unsigned.pop("integrity")
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": w7.sha256_bytes(w7.canonical_json(unsigned)),
    }
    evidence.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(once, "_expected_source_complete_evidence", lambda: evidence)
    monkeypatch.setattr(once, "_configure_white", lambda: events.append("host"))
    assert (
        once.main(
            [
                "diagnose-white-j2-off",
                "--base-url",
                "http://must-not-be-used.invalid",
                "--confirm-j2-off",
            ]
        )
        == 2
    )
    assert events == ["artifacts"]


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
def test_w7_live_cli_stops_at_unsealed_artifacts_before_source_or_device(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    events: list[str] = []
    monkeypatch.setattr(w7, "artifacts_are_sealed", lambda: False)
    monkeypatch.setattr(
        once,
        "_validate_source_complete_evidence",
        lambda *_args, **_kwargs: events.append("source"),
    )
    monkeypatch.setattr(
        once,
        "_configure_white",
        lambda: events.append("device"),
    )
    assert once.main(arguments) == 2
    assert events == []


def test_w7_artifact_binding_matches_files_after_seal() -> None:
    if not w7.artifacts_are_sealed():
        pytest.skip("isolated W7 artifacts not sealed yet")
    validation = once.dry_validate()
    assert validation["artifacts_verified"] is True
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]
    report = w7.build_white_report()
    firmware_bin, firmware_elf = w7.white_artifact_paths()
    binary = firmware_bin.read_bytes()
    elf = firmware_elf.read_bytes()
    for value in (
        w7.CONFIG.campaign_id,
        w7.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_contract_id"],
        w7.marker(),
    ):
        encoded = value.encode("ascii")
        assert encoded in binary
        assert encoded in elf


def test_w7_builder_issues_one_compile_only_command(
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
