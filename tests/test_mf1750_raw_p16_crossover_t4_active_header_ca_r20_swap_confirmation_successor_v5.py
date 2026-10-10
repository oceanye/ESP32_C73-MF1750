from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_SURFACE_KEYS = (
    "t4_v3_terminal_fault",
    "w9_permanent_claim",
    "w9_post_white_protective_off",
    "operator_gnd_assertion",
    "t4_v4_host_runner_rejection",
)
PAYLOAD_KEYS = (
    "frame",
    "cs1_dtm",
    "cs2_dtm",
    "waveform_binding",
    "profile_id",
    "global_header",
    "global_tuple_id",
    "round",
)


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return pack.build_report()


@pytest.fixture(scope="module")
def host() -> Any:
    if not pack.rejection_binding_is_sealed():
        pytest.skip("V4 host-runner rejection authority is not sealed yet")
    return once.configure()


def _authority_surface() -> dict[str, Any]:
    return {
        "t4_v3_terminal_fault": pack.v3_terminal_fault_binding(),
        "w9_permanent_claim": pack.completed_w9_white_claim_binding(),
        "w9_post_white_protective_off": pack.w9_post_off_binding(),
        "operator_gnd_assertion": deepcopy(pack.OPERATOR_GND_ASSERTION),
        "t4_v4_host_runner_rejection": pack.v4_host_runner_rejection_binding(),
    }


def _write_integrity_json(path: Path, value: dict[str, Any]) -> None:
    body = deepcopy(value)
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(pack.canonical_json(body)).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_v5_has_exactly_19_unique_tombstones_and_is_itself_fresh(
    report: dict[str, Any],
) -> None:
    registry = pack.non_reusable_action_ids()
    action = report["actions"][0]

    assert len(registry) == 19
    assert len(set(registry)) == 19
    assert registry[-1] == pack.V4_ACTION_ID
    assert report["contract"]["non_reusable_action_ids"] == list(registry)
    assert action["action_id"] not in registry
    assert action["supersedes_rejected_unconsumed_v4_action_id"] == pack.V4_ACTION_ID


def test_v5_payload_is_byte_semantically_identical_to_v4(
    report: dict[str, Any],
) -> None:
    action = report["actions"][0]
    predecessor = pack.v4.build_report()["actions"][0]
    result = pack.dry_validate(verify_authorities=False)

    assert result["result"] == "PASS"
    assert result["experimental_payload_byte_identical_to_v4"] is True
    for key in PAYLOAD_KEYS:
        assert action[key] == predecessor[key], key
    assert action["descriptor_id"] != predecessor["descriptor_id"]
    assert action["action_id"] != predecessor["action_id"]


def test_v5_fresh_identity_route_nvs_outputs_claims_and_selector(
    report: dict[str, Any], host: Any
) -> None:
    action = report["actions"][0]
    predecessor = pack.v4.build_report()
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_identity.inc"
    ).read_text(encoding="utf-8")
    identity_joined = re.sub(r'"\s*"', "", identity)
    selector = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    ini = (ROOT / builder.CONFIG).read_text(encoding="utf-8")

    for value in (
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        pack.CONFIG.campaign_id,
        pack.CONFIG.build_tag,
        pack.CONFIG.test_id,
        pack.CONFIG.nvs_namespace,
        pack.CONFIG.nvs_key,
        pack.CONFIG.nvs_boot_key,
        pack.CONFIG.base_route,
    ):
        assert value in identity_joined or value in main_config, value

    assert report["contract_id"] != predecessor["contract_id"]
    assert pack.CONFIG.campaign_id != predecessor["contract"]["campaign_id"]
    assert pack.CONFIG.nvs_namespace == "p16t4ca_v5"
    assert pack.CONFIG.nvs_key == "cur_t4ca5"
    assert pack.CONFIG.nvs_boot_key == "boot_t4ca5"
    assert (
        max(
            len(pack.CONFIG.nvs_namespace),
            len(pack.CONFIG.nvs_key),
            len(pack.CONFIG.nvs_boot_key),
        )
        <= 15
    )
    assert "successor_v5_identity.inc" in selector
    assert (
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
        "SUCCESSOR_V5_BUILD=1"
    ) in ini
    assert "build_dir = .pio/b-t4ca5" in ini
    assert "[env:ec5_p16_t4ca5]" in ini
    assert "upload" not in ini.lower()
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_20260901_V5"
    )
    assert str(host.DEFAULT_CLAIMS).endswith(
        ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v5_claims"
    )
    assert host.DIAGNOSTIC_OUTPUT == host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
    assert host.ACTION_OUTPUTS[1] == (
        host.DEFAULT_OUTPUT / "action-01-position-balanced-atlas.json"
    )
    assert host.base.runner.ENDPOINTS == {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }


def test_v5_wire_action_projection_exactly_matches_configured_live_host(
    report: dict[str, Any], host: Any
) -> None:
    projected = once.expected_wire_action()
    configured = dict(host.base.runner.ACTIONS[0])

    assert projected == configured
    assert projected != report["actions"][0]
    assert set(projected) == {
        "ordinal",
        "role",
        "branch",
        "profile_id",
        "palette_source",
        "global_header",
        "global_tuple_id",
        "waveform_binding",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
        "transport_code_histogram",
        "driver_entry",
        "descriptor_id",
        "action_id",
        "round",
        "prior_static_action_id",
        "boot_admission",
    }
    assert projected["action_id"] == report["actions"][0]["action_id"]
    assert projected["descriptor_id"] == report["actions"][0]["descriptor_id"]


def test_v5_permanent_claim_validator_accepts_only_real_producer_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire_action = once.expected_wire_action()
    claim = {
        "schema_version": 1,
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v5-permanent-claim"
        ),
        "created_at": "2026-09-01T00:00:00.000+00:00",
        "firmware_sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        "boot_nonce": "0123456789abcdef",
        "action": wire_action,
        "state": "claimed_before_first_mutation",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": "0" * 64,
        },
    }
    monkeypatch.setattr(once, "_read_integrity_json", lambda *_args, **_kwargs: claim)
    assert once._validate_permanent_claim(wire_action) == claim  # noqa: SLF001

    wrong_state = deepcopy(claim)
    wrong_state["state"] = "permanently_claimed_after_j2_on_preflight_before_first_arm"
    monkeypatch.setattr(
        once, "_read_integrity_json", lambda *_args, **_kwargs: wrong_state
    )
    with pytest.raises(
        once.T4MatchedSwapSuccessorV5RunnerError,
        match="permanent claim semantics differ",
    ):
        once._validate_permanent_claim(wire_action)  # noqa: SLF001

    extra_field = deepcopy(claim)
    extra_field["write_contract"] = "O_EXCL"
    monkeypatch.setattr(
        once, "_read_integrity_json", lambda *_args, **_kwargs: extra_field
    )
    with pytest.raises(
        once.T4MatchedSwapSuccessorV5RunnerError,
        match="permanent claim semantics differ",
    ):
        once._validate_permanent_claim(wire_action)  # noqa: SLF001


def test_v5_four_authorities_are_on_both_device_surfaces_and_deep_checked(
    host: Any,
) -> None:
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    main = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main.cpp"
    ).read_text(encoding="utf-8")
    surface = _authority_surface()

    for key in AUTHORITY_SURFACE_KEYS:
        assert main_config.count(f'"{key}"') == 1
    assert main.count("kExternalWhiteAnchorJson") == 2
    assert "versionJson" in main and "manifestJson" in main

    once._validate_v5_authority_surface(host, surface)  # noqa: SLF001
    for key in AUTHORITY_SURFACE_KEYS:
        malformed = deepcopy(surface)
        malformed.pop(key)
        with pytest.raises(
            host.base.runner.RecheckError,
            match=f"authority surface {key}",
        ):
            once._validate_v5_authority_surface(host, malformed)  # noqa: SLF001


def test_v5_gnd_confirmation_is_a_required_cli_and_runtime_gate(
    host: Any,
) -> None:
    with pytest.raises(SystemExit):
        once._parse_args(  # noqa: SLF001
            [
                "run",
                "--base-url",
                "http://192.0.2.1",
                "--confirm-j2-on",
                "--confirm-external-pre-white",
            ]
        )

    network_called = False

    def forbidden_request(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal network_called
        network_called = True
        return 200, {}

    with pytest.raises(
        once.T4MatchedSwapSuccessorV5RunnerError,
        match="GND-normal confirmation",
    ):
        host.run_once(
            "http://192.0.2.1",
            1,
            confirm_gnd_normal=False,
            requester=forbidden_request,
        )
    assert network_called is False


def test_v5_real_host_accepts_fresh_diagnostic_rejects_tampering_and_keeps_prior_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    report: dict[str, Any],
) -> None:
    production_source = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_once.py"
    ).read_text(encoding="utf-8")
    assert "_validate_prior_terminal_report" not in production_source
    assert production_source.count("_validate_initial_not_executed_report(") == 3

    monkeypatch.setattr(once, "_output_root", lambda: tmp_path)
    monkeypatch.setattr(pack, "validate_authorities", lambda: {})
    fixed_rejection = deepcopy(
        report["actions"][0]["v4_host_runner_rejection_authority"]
    )
    monkeypatch.setattr(
        pack,
        "v4_host_runner_rejection_binding",
        lambda *, require_sealed=True: deepcopy(fixed_rejection),
    )
    base_url = "http://192.0.2.1"
    diagnostic_path = tmp_path / "j2-off-diagnostic.json"
    real_host = once.configure()

    # Version/manifest/ready validation is orthogonal to this regression.  Keep
    # the real configured host and its real nested virgin-report validator,
    # while reducing the synthetic fixture to the exact failing boundary.
    monkeypatch.setattr(real_host, "_validate_version", lambda _value: None)
    monkeypatch.setattr(real_host, "_validate_manifest", lambda _value: None)

    def validate_ready(
        value: Mapping[str, Any], ordinal: int, *, expected_busy: int
    ) -> str:
        assert ordinal == 1
        assert expected_busy == 0
        return str(value["boot_nonce"])

    monkeypatch.setattr(real_host, "_validate_ready_status", validate_ready)
    with pytest.raises(
        once.T4MatchedSwapSuccessorV5RunnerError,
        match="missing or unsafe",
    ):
        once._validate_j2_off_diagnostic_evidence(real_host, base_url)  # noqa: SLF001

    runner = real_host.base.runner
    fresh_report = {
        "kind": f"{runner.DEVICE_KIND_PREFIX}-report",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
        "boot_nonce": "boot-v5",
        "valid": False,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "phase": 0,
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }

    responses = [
        {"endpoint": "version"},
        {"endpoint": "manifest"},
        {"boot_nonce": "boot-v5", "endpoint": "status"},
        fresh_report,
    ]
    value: dict[str, Any] = {
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v5-j2-off-diagnostic"
        ),
        "outcome": "j2_off_diagnostic_pass",
        "j2_confirmed_off": True,
        "artifact_preflight_completed_before_network": True,
        "fresh_cursor_key_absent": True,
        "campaign_boot_key_present_and_current": True,
        "next_ordinal": 1,
        "network": {"get": 4, "post": 0},
        "permanent_claims_created": 0,
        "visible_refreshes": 0,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "output_write_contract": "O_EXCL",
        "base_url": base_url,
        "build_tag": pack.CONFIG.build_tag,
        "campaign_id": pack.CONFIG.campaign_id,
        "contract_id": report["contract_id"],
        "test_id": pack.CONFIG.test_id,
        "local_artifact_binding": {
            "bound": True,
            "bin": {
                "bytes": pack.ARTIFACTS[pack.STAGE]["bin_bytes"],
                "sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
            },
            "elf": {
                "bytes": pack.ARTIFACTS[pack.STAGE]["elf_bytes"],
                "sha256": pack.ARTIFACTS[pack.STAGE]["elf_sha256"],
            },
        },
        "boot_nonce": "boot-v5",
        "status": responses[2],
        "report": responses[3],
        "transcript": [
            {
                "method": "GET",
                "endpoint": endpoint,
                "status": 200,
                "response": response,
            }
            for endpoint, response in zip(
                ("version", "manifest", "status", "report"),
                responses,
                strict=True,
            )
        ],
    }
    _write_integrity_json(diagnostic_path, value)
    validated = once._validate_j2_off_diagnostic_evidence(  # noqa: SLF001
        real_host, base_url
    )
    assert validated["boot_nonce"] == "boot-v5"
    assert validated["network"] == {"get": 4, "post": 0}

    # The shared same-R20 prior-terminal guard remains intentionally strict:
    # ordinal one has no prior action and must never be normalized as one.
    with pytest.raises(
        real_host.base.runner.RecheckError,
        match="same-R20 4x8 parity has no prior ordinal",
    ):
        real_host._validate_prior_terminal_report(  # noqa: SLF001
            fresh_report, 1, "boot-v5"
        )

    corruptions = (
        ("terminal_state", "COMPLETE"),
        ("valid", True),
        ("driver_called", True),
        ("driver_call_count_for_action", 1),
        ("total_driver_call_count", 1),
        ("next_ordinal", 2),
        ("boot_nonce", "other-boot"),
    )
    for field, bad in corruptions:
        malformed = deepcopy(value)
        malformed.pop("integrity", None)
        malformed_report = malformed["transcript"][3]["response"]
        malformed_report[field] = bad
        malformed["report"] = deepcopy(malformed_report)
        _write_integrity_json(diagnostic_path, malformed)
        with pytest.raises(real_host.base.runner.RecheckError):
            once._validate_j2_off_diagnostic_evidence(  # noqa: SLF001
                real_host, base_url
            )


def test_v5_run_rejects_a_boot_change_after_fixed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, Any],
) -> None:
    class RecheckError(RuntimeError):
        pass

    action = deepcopy(report["actions"][0])
    fixed_rejection = deepcopy(action["v4_host_runner_rejection_authority"])
    monkeypatch.setattr(
        pack,
        "v4_host_runner_rejection_binding",
        lambda *, require_sealed=True: deepcopy(fixed_rejection),
    )
    runner = SimpleNamespace(ACTIONS=(action,), RecheckError=RecheckError)
    base = SimpleNamespace(runner=runner)
    fake = SimpleNamespace(
        v3=SimpleNamespace(),
        base=base,
        _validate_version=lambda _value: None,
        _validate_manifest=lambda _value: None,
        _diagnostic_http_request=lambda *_args, **_kwargs: (
            200,
            {"boot_nonce": "boot-v5"},
        ),
    )

    def original_run_once(
        _base_url: str,
        _ordinal: int,
        *,
        requester: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        requester("GET", "status")
        return {"unexpected": "same-boot gate did not run"}

    fake.run_once = original_run_once
    monkeypatch.setattr(once.mechanics, "configure", lambda: fake)
    monkeypatch.setattr(
        once,
        "_validate_j2_off_diagnostic_evidence",
        lambda _host, _base_url: {"boot_nonce": "boot-v5"},
    )
    configured = once.configure()

    with pytest.raises(RecheckError, match="boot nonce differs"):
        configured.run_once(
            "http://192.0.2.1",
            1,
            confirm_gnd_normal=True,
            requester=lambda *_args, **_kwargs: (
                200,
                {"boot_nonce": "different-boot"},
            ),
        )


def test_v5_artifacts_match_when_sealed_and_builder_is_compile_only() -> None:
    source = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_build.py"
    ).read_text(encoding="utf-8")
    assert '"run", "-c", CONFIG' in source
    assert "upload" not in source.lower()

    if not pack.artifacts_are_sealed():
        pytest.skip("isolated V5 artifacts are not sealed yet")

    report = pack.build_report()
    identities = (
        pack.CONFIG.campaign_id,
        report["contract_id"],
        report["actions"][0]["descriptor_id"],
        report["actions"][0]["action_id"],
        pack.ARM_INTENT,
        pack.EXECUTE_INTENT,
    )
    value = once.dry_validate()
    assert value["artifacts_verified"] is True
    expected = pack.ARTIFACTS[pack.STAGE]
    for path, kind in zip(pack.artifact_paths(), ("bin", "elf"), strict=True):
        payload = path.read_bytes()
        assert len(payload) == expected[f"{kind}_bytes"]
        assert hashlib.sha256(payload).hexdigest() == expected[f"{kind}_sha256"]
        for identity in identities:
            assert identity.encode("ascii") in payload, (kind, identity)
