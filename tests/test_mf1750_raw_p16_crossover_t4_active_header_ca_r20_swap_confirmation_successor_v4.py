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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_SURFACE_KEYS = (
    "t4_v3_terminal_fault",
    "w9_permanent_claim",
    "w9_post_white_protective_off",
    "operator_gnd_assertion",
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
    return once.configure()


def _authority_surface() -> dict[str, Any]:
    return {
        "t4_v3_terminal_fault": pack.v3_terminal_fault_binding(),
        "w9_permanent_claim": pack.completed_w9_white_claim_binding(),
        "w9_post_white_protective_off": pack.w9_post_off_binding(),
        "operator_gnd_assertion": deepcopy(pack.OPERATOR_GND_ASSERTION),
    }


def _write_integrity_json(path: Path, value: dict[str, Any]) -> None:
    body = deepcopy(value)
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(pack.canonical_json(body)).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_v4_has_exactly_18_unique_tombstones_and_is_itself_fresh(
    report: dict[str, Any],
) -> None:
    registry = pack.non_reusable_action_ids()
    action = report["actions"][0]

    assert len(registry) == 18
    assert len(set(registry)) == 18
    assert registry[-3:] == (pack.V3_ACTION_ID, pack.W8_ACTION_ID, pack.W9_ACTION_ID)
    assert report["contract"]["non_reusable_action_ids"] == list(registry)
    assert action["action_id"] not in registry
    assert action["supersedes_failed_faulted_v3_action_id"] == pack.V3_ACTION_ID


def test_v4_payload_is_byte_semantically_identical_to_v3(
    report: dict[str, Any],
) -> None:
    action = report["actions"][0]
    predecessor = pack.v3.build_report()["actions"][0]
    result = pack.dry_validate()

    assert result["result"] == "PASS"
    assert result["experimental_payload_byte_identical_to_v3"] is True
    for key in PAYLOAD_KEYS:
        assert action[key] == predecessor[key], key
    assert action["descriptor_id"] != predecessor["descriptor_id"]
    assert action["action_id"] != predecessor["action_id"]


def test_v4_fresh_identity_route_nvs_outputs_claims_and_selector(
    report: dict[str, Any], host: Any
) -> None:
    action = report["actions"][0]
    predecessor = pack.v3.build_report()
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_identity.inc"
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
    assert pack.CONFIG.nvs_namespace == "p16t4ca_v4"
    assert pack.CONFIG.nvs_key == "cur_t4ca4"
    assert pack.CONFIG.nvs_boot_key == "boot_t4ca4"
    assert (
        max(
            len(pack.CONFIG.nvs_namespace),
            len(pack.CONFIG.nvs_key),
            len(pack.CONFIG.nvs_boot_key),
        )
        <= 15
    )
    assert "successor_v4_identity.inc" in selector
    assert (
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
        "SUCCESSOR_V4_BUILD=1"
    ) in ini
    assert "build_dir = .pio/b-t4ca4" in ini
    assert "[env:ec5_p16_t4ca4]" in ini
    assert "upload" not in ini.lower()
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_20260901_V4"
    )
    assert str(host.DEFAULT_CLAIMS).endswith(
        ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v4_claims"
    )
    assert host.DIAGNOSTIC_OUTPUT == host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
    assert host.ACTION_OUTPUTS[1] == (
        host.DEFAULT_OUTPUT / "action-01-position-balanced-atlas.json"
    )
    assert host.base.runner.ENDPOINTS == {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }


def test_v4_four_authorities_are_on_both_device_surfaces_and_deep_checked(
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

    once._validate_v4_authority_surface(host, surface)  # noqa: SLF001
    for key in AUTHORITY_SURFACE_KEYS:
        malformed = deepcopy(surface)
        malformed.pop(key)
        with pytest.raises(
            host.base.runner.RecheckError,
            match=f"authority surface {key}",
        ):
            once._validate_v4_authority_surface(host, malformed)  # noqa: SLF001


def test_v4_gnd_confirmation_is_a_required_cli_and_runtime_gate(
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
        once.T4MatchedSwapSuccessorV4RunnerError,
        match="GND-normal confirmation",
    ):
        host.run_once(
            "http://192.0.2.1",
            1,
            confirm_gnd_normal=False,
            requester=forbidden_request,
        )
    assert network_called is False


def test_v4_fixed_j2_off_diagnostic_requires_exact_four_gets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    report: dict[str, Any],
) -> None:
    monkeypatch.setattr(once, "_output_root", lambda: tmp_path)
    base_url = "http://192.0.2.1"
    diagnostic_path = tmp_path / "j2-off-diagnostic.json"

    class DiagnosticHost:
        def _validate_version(self, _value: Mapping[str, Any]) -> None:
            return None

        def _validate_manifest(self, _value: Mapping[str, Any]) -> None:
            return None

        def _validate_ready_status(
            self,
            value: Mapping[str, Any],
            ordinal: int,
            *,
            expected_busy: int,
        ) -> str:
            assert ordinal == 1 and expected_busy == 0
            return str(value["boot_nonce"])

        def _validate_prior_terminal_report(
            self,
            _value: Mapping[str, Any],
            ordinal: int,
            boot_nonce: str,
        ) -> None:
            assert ordinal == 1 and boot_nonce == "boot-v4"

    fake_host = DiagnosticHost()
    with pytest.raises(
        once.T4MatchedSwapSuccessorV4RunnerError,
        match="missing or unsafe",
    ):
        once._validate_j2_off_diagnostic_evidence(fake_host, base_url)  # noqa: SLF001

    responses = [
        {"endpoint": "version"},
        {"endpoint": "manifest"},
        {"boot_nonce": "boot-v4", "endpoint": "status"},
        {"boot_nonce": "boot-v4", "endpoint": "report"},
    ]
    value: dict[str, Any] = {
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v4-j2-off-diagnostic"
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
        "boot_nonce": "boot-v4",
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
        fake_host, base_url
    )
    assert validated["boot_nonce"] == "boot-v4"
    assert validated["network"] == {"get": 4, "post": 0}


def test_v4_run_rejects_a_boot_change_after_fixed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, Any],
) -> None:
    class RecheckError(RuntimeError):
        pass

    action = deepcopy(report["actions"][0])
    runner = SimpleNamespace(ACTIONS=(action,), RecheckError=RecheckError)
    base = SimpleNamespace(runner=runner)
    fake = SimpleNamespace(
        v3=SimpleNamespace(),
        base=base,
        _validate_version=lambda _value: None,
        _validate_manifest=lambda _value: None,
        _diagnostic_http_request=lambda *_args, **_kwargs: (
            200,
            {"boot_nonce": "boot-v4"},
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
        lambda _host, _base_url: {"boot_nonce": "boot-v4"},
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


def test_v4_artifacts_match_when_sealed_and_builder_is_compile_only() -> None:
    source = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_build.py"
    ).read_text(encoding="utf-8")
    assert '"run", "-c", CONFIG' in source
    assert "upload" not in source.lower()

    if not pack.artifacts_are_sealed():
        pytest.skip("isolated V4 artifacts are not sealed yet")

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
