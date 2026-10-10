from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_pack as source,
)
from tools import (
    mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_successor_v5_white_v1_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_successor_v5_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_successor_v5_white_v1_pack as w11,
)


def _offline_source(monkeypatch: pytest.MonkeyPatch, *, sealed: bool = True) -> None:
    monkeypatch.setattr(source, "dry_validate", lambda: {"result": "PASS"})
    monkeypatch.setattr(source, "artifacts_are_sealed", lambda: sealed)


def test_pack_binds_exact_sealed_v5_and_final_successor_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _offline_source(monkeypatch)
    value = w11.dry_validate()
    source_report = source.build_report()
    source_action = source_report["actions"][0]

    assert value["result"] == "PASS"
    assert value["source_artifacts_sealed"] is True
    assert value["successor_identity_finalized"] is True
    assert value["ready_to_build"] is True
    assert value["ready_for_live"] is False
    assert value["ready_for_source_terminal_evidence"] is True
    assert value["compiled_identity_source"]["identity_state"] == "FINAL_V5_BOUND_IDENTITY"
    assert value["compiled_identity_source"]["contract_id"] == value["contract_id"]
    assert value["compiled_identity_source"]["descriptor_id"] == value["descriptor_id"]
    assert value["compiled_identity_source"]["action_id"] == value["action_id"]
    assert value["source"]["contract_id"] == source_report["contract_id"]
    assert value["source"]["descriptor_id"] == source_action["descriptor_id"]
    assert value["source"]["action_id"] == source_action["action_id"]
    assert value["source"]["firmware"] == source.ARTIFACTS[source.STAGE]


def test_w11_artifacts_are_sealed_and_match_isolated_build() -> None:
    assert w11.WHITE_ARTIFACTS[w11.STAGE] == {
        "bin_bytes": 787_504,
        "bin_sha256": "e10d4ba6063e885ca4ce1669b343ba9ece6451dc24cbdefafd16732ffa140f3e",
        "elf_bytes": 13_215_012,
        "elf_sha256": "79969668905ef8ad15f809436cb573fd847d9dc6436deff40be138e36fba8273",
    }
    assert w11.artifacts_are_sealed() is True
    expected = w11.WHITE_ARTIFACTS[w11.STAGE]
    firmware_bin, firmware_elf = w11.white_artifact_paths()
    for path, prefix in ((firmware_bin, "bin"), (firmware_elf, "elf")):
        payload = path.read_bytes()
        assert len(payload) == expected[f"{prefix}_bytes"]
        assert hashlib.sha256(payload).hexdigest() == expected[f"{prefix}_sha256"]
        assert payload.count(w11.build_white_report()["contract_id"].encode("ascii")) == 1
        assert payload.count(w11.build_white_report()["action"]["descriptor_id"].encode("ascii")) == 2
        assert payload.count(w11.build_white_report()["action"]["action_id"].encode("ascii")) == 1


def test_unique_stage_route_nvs_environment_output_and_claim_roots() -> None:
    assert w11.STAGE == (
        "w11-after-t4-active-header-ca-r20-swap-confirmation-successor-v5-white-v1"
    )
    assert w11.CONFIG.base_route == (
        "/api/ec5/raw-p16-crossover-w11-after-t4-active-header-ca-r20-"
        "swap-confirmation-successor-v5-white-v1"
    )
    assert w11.CONFIG.environment == "ec5_p16_w11t4ca5_w1"
    assert w11.CONFIG.build_root == "b-w11t4ca5-w1"
    assert w11.CONFIG.nvs_namespace == "p16w11t4ca5v1"
    assert w11.CONFIG.nvs_key == "used_w11t4ca5"
    assert len(w11.CONFIG.nvs_namespace) <= 15
    assert len(w11.CONFIG.nvs_key) <= 15
    assert "W11_" in once._output_root().name  # noqa: SLF001
    assert "successor_v5_white_v1_claims" in once._claim_root().name  # noqa: SLF001
    assert "W10" not in str(once._output_root())  # noqa: SLF001
    assert "successor_v4" not in str(once._claim_root())  # noqa: SLF001


def test_contract_accepts_only_deeply_validated_v5_complete() -> None:
    report = w11.build_white_report()
    contract = report["contract"]
    terminal = contract["source"]["terminal_policy"]

    assert contract["accepted_source_terminal_states"] == ["COMPLETE"]
    assert terminal["accepted_terminal_states"] == ["COMPLETE"]
    assert terminal["complete_requires_result_true"] is True
    assert terminal["driver_call_count_for_action"] == 1
    assert terminal["total_driver_call_count"] == 1
    assert terminal["source_action_permanently_consumed"] is True
    assert contract["source_fault_policy"] == w11.FAULT_POLICY
    assert contract["source_fault_is_not_success"] is True
    assert contract["source_terminal_evidence_required_before_any_live_request"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["runtime_lut_write"] is False


def test_terminal_selector_rejects_fault_and_accepts_only_fixed_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete = tmp_path / "action-01-position-balanced-atlas.json"
    fault = tmp_path / "action-01-terminal-read-only-salvage-reconciled.json"
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {"COMPLETE": complete, "FAULT": fault},
    )

    complete.write_text("{}", encoding="utf-8")
    state, selected = once._select_source_terminal_path()  # noqa: SLF001
    assert state == "COMPLETE"
    assert selected == complete.resolve()

    fault.write_text("{}", encoding="utf-8")
    with pytest.raises(once.W11RunnerError, match=w11.FAULT_POLICY):
        once._select_source_terminal_path()  # noqa: SLF001


def test_real_v5_complete_result_passes_deep_w11_predecessor_gate() -> None:
    paths = once._source_terminal_paths()  # noqa: SLF001
    assert paths["COMPLETE"].is_file()
    assert not paths["FAULT"].exists()
    source_result = json.loads(paths["COMPLETE"].read_text(encoding="utf-8"))
    assert source_result["action"] == once.source_once.expected_wire_action()
    assert source_result["action"] != source.build_report()["actions"][0]

    value = once._validate_source_terminal_evidence(paths["COMPLETE"])  # noqa: SLF001
    assert value["verified"] is True
    assert value["branch"] == "SOURCE_COMPLETE_SUCCESS_BOUND_WHITE"
    assert value["source_terminal_state"] == "COMPLETE"
    assert value["source_success_claimed"] is True
    assert value["driver_call_count_for_action"] == 1
    assert value["action_must_not_be_retried"] is True
    assert value["deep_validation"]["firmware_sha256"] == (
        source.ARTIFACTS[source.STAGE]["bin_sha256"]
    )


def test_final_identity_is_rejected_if_v5_reverts_to_unsealed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _offline_source(monkeypatch, sealed=False)
    with pytest.raises(w11.W11PackError, match="waiting identity kContractId must remain"):
        w11.validate_identity_source()


def test_live_artifact_gate_fails_before_file_or_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        w11,
        "dry_validate",
        lambda: {
            "result": "WAITING_FOR_V5_SEALED_ARTIFACTS",
            "source_artifacts_sealed": False,
            "successor_identity_finalized": False,
            "ready_to_build": False,
        },
    )
    monkeypatch.setattr(
        w11,
        "white_artifact_paths",
        lambda: (_ for _ in ()).throw(AssertionError("artifact path touched")),
    )
    with pytest.raises(once.W11RunnerError, match="source/identity is not finalized"):
        once._verify_artifacts()  # noqa: SLF001


def test_build_refuses_waiting_state_before_platformio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        build,
        "prebuild_validate",
        lambda: {
            "result": "WAITING_FOR_V5_SEALED_ARTIFACTS",
            "ready_to_build": False,
        },
    )
    monkeypatch.setattr(
        build,
        "_platformio_executable",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PlatformIO must not be resolved")
        ),
    )
    with pytest.raises(build.BuildError, match="disabled until V5 artifacts are sealed"):
        build.build()


def test_shared_white_program_has_complete_w11_selector_and_routes() -> None:
    text = (
        w11.REPO_ROOT
        / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    macro = (
        "MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_V5_WHITE_V1_BUILD"
    )
    route = (
        "w11-after-t4-active-header-ca-r20-swap-confirmation-successor-v5-white-v1"
    )
    assert text.count(macro) == 9
    assert text.count(
        "ec5_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_"
        "successor_v5_white_v1_identity.inc"
    ) == 1
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert text.count(f'"{route}/{endpoint}"') == 1
    assert w11.shared_firmware_intents() == {
        "arm": w11.WHITE_ARM_INTENT,
        "execute": w11.WHITE_EXECUTE_INTENT,
    }


def test_isolated_platformio_selector_and_compile_only_builder() -> None:
    ini = (
        w11.REPO_ROOT
        / "platformio.raw_p16_crossover_w11_t4_active_header_ca_r20_"
        "swap_confirmation_successor_v5_white_v1.ini"
    ).read_text(encoding="utf-8")
    assert "default_envs = ec5_p16_w11t4ca5_w1" in ini
    assert "build_dir = .pio/b-w11t4ca5-w1" in ini
    assert (
        "MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_"
        "SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1_BUILD=1"
    ) in ini
    assert "upload" not in Path(build.__file__).read_text(encoding="utf-8").lower()
