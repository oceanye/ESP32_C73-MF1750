from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_H3_C_FIRST_DIAGNOSTIC_RECOVERY_PLAN_20260814_V1"
    / "WF20_25-plan.json"
)
STAGE_A_RECEIPT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260815_V10_RECOVERY_V1"
    / "stage-a-partial-boot-control-receipt.json"
)


@pytest.fixture(scope="module")
def blueprint_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("stage-b-facade")
    blueprint_path = root / "blueprint.json"
    blueprint = facade.materialize_blueprint(
        plan_file=PLAN,
        stage_a_receipt_file=STAGE_A_RECEIPT,
        blueprint_file=blueprint_path,
    )
    return blueprint, root


class ValidPayloads:
    def __init__(self) -> None:
        self.context = physical.load_release(
            REPO_ROOT
            / ".test-output"
            / "hardware"
            / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10"
            / "WF20_25-release.json"
        )
        self.ordinal = 1
        self.boot_nonce = "0123456789abcdef"

    @property
    def action(self) -> Mapping[str, Any]:
        return self.context.action(self.ordinal)

    @property
    def binding(self) -> Mapping[str, Any]:
        return self.context.binding(self.ordinal)

    def identity(self) -> dict[str, Any]:
        return facade._expected_identity(self.context, self.ordinal)  # noqa: SLF001

    def version(self) -> dict[str, Any]:
        return facade._expected_version_surface(  # noqa: SLF001
            self.context, self.ordinal
        )

    def manifest(self) -> dict[str, Any]:
        return facade._expected_manifest_surface(  # noqa: SLF001
            self.context, self.ordinal
        )

    def status(self) -> dict[str, Any]:
        return facade._expected_status_surface(  # noqa: SLF001
            self.context,
            boot_nonce=self.boot_nonce,
            busy=1,
            ordinal=self.ordinal,
        )

    def report(self) -> dict[str, Any]:
        return facade._expected_report_surface(  # noqa: SLF001
            self.context, self.ordinal
        )

    @staticmethod
    def raw(value: Mapping[str, Any]) -> bytes:
        return contract.canonical_json_bytes(value)

    def script(
        self, blueprint: Mapping[str, Any]
    ) -> list[tuple[str, facade.ScriptedFakeResponse]]:
        bodies = (self.version(), self.manifest(), self.status(), self.report())
        requests = blueprint["read_only_state_machine"]["ordered_requests"]
        return [
            (
                str(request["absolute_url"]),
                facade.ScriptedFakeResponse(status=200, body=self.raw(body)),
            )
            for request, body in zip(requests, bodies, strict=True)
        ]


def test_blueprint_is_v2_and_supersedes_non_authorizing_v1_with_exact_sources(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, _ = blueprint_bundle
    superseded = blueprint["supersedes"]
    exact = blueprint["exact_response_surface_validation"]
    sources = exact["source_bindings"]

    assert blueprint["schema_version"] == 2
    assert blueprint["kind"].endswith("-v2")
    assert blueprint["classification"] == facade.CLASSIFICATION
    assert superseded["prior_schema_version"] == 1
    assert superseded["prior_kind"].endswith("-v1")
    assert superseded["prior_artifact_was_live_authorization"] is False
    assert superseded["prior_artifact_is_eligible_as_live_authority_base"] is False
    assert sources["v10_control_main"]["sha256"] == (
        facade.EXPECTED_CONTROL_MAIN_SHA256
    )
    assert sources["v10_shared_http_envelope"]["sha256"] == (
        facade.EXPECTED_ONCE_MAIN_SHA256
    )
    assert sources["v10_control_driver_constants"]["sha256"] == (
        facade.EXPECTED_CONTROL_DRIVER_SHA256
    )
    reference = exact["reference_only_inputs"]["wf20_25_generated_profile"]
    assert reference["sha256"] == facade.EXPECTED_REFERENCE_PROFILE_SHA256
    assert reference["role"] == (
        "REFERENCE_NOT_COMPILED_INTO_CONTROL_NOT_RESPONSE_SOURCE_PROOF"
    )
    assert exact["single_raw_decode_and_validate_api"] == (
        "decode_and_validate_v10_response_bytes"
    )
    assert exact["raw_response_size_max_bytes"] == facade.MAX_JSON_BYTES

    live_receipt = blueprint["future_live_artifact_contracts"]["terminal_live_receipt"]
    assert live_receipt["attempt_recorded_before_transport_send"] is True
    assert live_receipt["per_endpoint_required_fields"] == [
        "ordinal",
        "method",
        "path",
        "absolute_url",
        "attempted",
        "response_received",
        "http_status",
        "raw_body_bytes",
        "raw_body_sha256",
        "strict_parsed_canonical_sha256",
        "validation_outcome",
    ]
    assert live_receipt["raw_body_length_and_sha256_required_if_received"] is True
    assert (
        live_receipt["strict_parsed_canonical_sha256_required_if_decode_succeeds"]
        is True
    )
    assert live_receipt["transport_exception_wire_emission_classification"] == (
        "UNKNOWN"
    )
    assert live_receipt["transport_exception_peer_receipt_classification"] == (
        "UNKNOWN"
    )
    assert (
        live_receipt["transport_exception_must_not_claim_exact_get_reached_device"]
        is True
    )


def test_blueprint_keeps_partial_stage_a_and_all_live_authority_blocked(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, _ = blueprint_bundle
    partial = blueprint["stage_a_partial_receipt_binding"]
    boundary = blueprint["authority_boundary"]

    assert partial["classification"] == (
        "PARTIAL_BOOT_CONTROL_RECEIPT_NOT_STAGE_A_COMPLETE"
    )
    assert partial["stage_a_intent_satisfied"] is False
    assert partial["active_application_boot_proven"] is False
    assert partial["active_v10_proven"] is False
    assert partial["candidate_ip_proven"] is False
    assert partial["stage_b_authorization_derivable_from_receipt"] is False
    assert boundary["partial_receipt_is_stage_a_completion"] is False
    assert boundary["existing_plan_stage_order_is_satisfied"] is False
    assert boundary["explicit_superseding_contract_required"] is True
    assert boundary["blueprint_is_that_superseding_contract"] is False
    assert boundary["copyable_authorization_token_emitted"] is False
    assert boundary["live_execution_entry_point_present"] is False
    assert boundary["execution_ready"] is False
    assert boundary["live_authorized"] is False


def test_candidate_is_single_untrusted_origin_until_exact_version_validation(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, _ = blueprint_bundle
    policy = blueprint["candidate_origin_policy"]
    machine = blueprint["read_only_state_machine"]

    assert policy["operator_selected_candidate_base_url"] == "http://192.168.1.7"
    assert policy["arp_cache_is_identity_proof"] is False
    assert policy["candidate_origin_trusted_before_version"] is False
    assert policy["network_scan_allowed"] is False
    assert policy["fallback_origin_allowed"] is False
    assert policy["redirect_allowed"] is False
    assert policy["first_exact_version_may_unlock_remaining_get_budget"] is True
    assert (
        policy["unlock_requires_source_pinned_exact_v10_version_validator_success"]
        is True
    )
    assert policy["successful_version_validation_classification"] == (
        "V10_PROTOCOL_RESPONSE_CONFORMANCE"
    )
    for key in (
        "responder_or_device_identity_proven",
        "trusted_ip_binding_proven",
        "fresh_post_reset_application_boot_proven",
        "active_application_proven",
        "active_ota_slot_proven",
        "firmware_at_0x10000_is_running_proven",
    ):
        assert policy[key] is False
    assert policy["unlock_policy_requires_explicit_superseding_contract"] is True
    assert [
        item["path"].rsplit("/", 1)[-1] for item in machine["ordered_requests"]
    ] == [
        "version",
        "manifest",
        "status",
        "report",
    ]
    assert {
        item["absolute_url"].split("/api/", 1)[0]
        for item in machine["ordered_requests"]
    } == {"http://192.168.1.7"}


def test_real_source_shaped_exact_surfaces_have_frozen_key_counts() -> None:
    payloads = ValidPayloads()
    version = payloads.version()
    manifest = payloads.manifest()
    status = payloads.status()
    report = payloads.report()

    assert len(payloads.identity()) == 12
    assert len(version) == 24
    assert len(version["profile"]) == 28
    assert len(manifest) == 51
    assert len(manifest["actions"][0]) == 7
    assert all(len(item) == 3 for item in manifest["unproven_risks"])
    assert len(manifest["matched_sequence"]) == 14
    assert len(manifest["nvs_contract"]) == 7
    assert len(status) == 36
    assert len(report) == 34
    phantom_legacy_profile_fields = {
        "control_design",
        "strict_payload_only_control",
        "time_matched_control",
        "dummy_clocks_inserted",
        "empty_r20_or_r21_commands_inserted",
    }
    assert phantom_legacy_profile_fields.isdisjoint(version["profile"])

    for name, body in (
        ("version", version),
        ("manifest", manifest),
        ("status", status),
        ("report", report),
    ):
        facade.validate_v10_response_surface(name, body, payloads.context)

    enriched = deepcopy(version)
    for key in phantom_legacy_profile_fields:
        enriched["profile"][key] = False
    with pytest.raises(facade.StageBFacadeContractError, match="extra="):
        facade.validate_v10_response_surface("version", enriched, payloads.context)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    (
        ("classification", "WRONG_CLASSIFICATION"),
        ("live_authorized", True),
        ("identity_revision", "wrong-revision"),
        ("command_audit_marker", "wrong-command-audit"),
        ("profile_id", "WRONG_PROFILE"),
    ),
)
def test_exact_version_rejects_wrong_ignored_critical_root_fields(
    field: str, bad_value: object
) -> None:
    payloads = ValidPayloads()
    value = payloads.version()
    value[field] = bad_value

    with pytest.raises(facade.StageBFacadeContractError, match=field):
        facade.validate_v10_response_surface("version", value, payloads.context)


def test_exact_version_rejects_missing_extra_nested_and_bool_as_int() -> None:
    payloads = ValidPayloads()

    missing = payloads.version()
    del missing["classification"]
    with pytest.raises(
        facade.StageBFacadeContractError, match="missing=.*classification"
    ):
        facade.validate_v10_response_surface("version", missing, payloads.context)

    extra = payloads.version()
    extra["unexpected"] = False
    with pytest.raises(facade.StageBFacadeContractError, match="extra=.*unexpected"):
        facade.validate_v10_response_surface("version", extra, payloads.context)

    nested = payloads.version()
    nested["profile"]["unexpected"] = False
    with pytest.raises(facade.StageBFacadeContractError, match="profile.*extra"):
        facade.validate_v10_response_surface("version", nested, payloads.context)

    wrong_type = payloads.version()
    wrong_type["action_count"] = True
    with pytest.raises(facade.StageBFacadeContractError, match="JSON type"):
        facade.validate_v10_response_surface("version", wrong_type, payloads.context)

    status_bool = payloads.status()
    status_bool["busy"] = True
    with pytest.raises(facade.StageBFacadeContractError, match="busy"):
        facade.validate_v10_response_surface("status", status_bool, payloads.context)


@pytest.mark.parametrize(
    "payload",
    (
        b'{"value":1,"value":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":1} trailing',
        b"[]",
        b'\xff{"value":1}',
    ),
)
def test_strict_json_decoder_rejects_duplicate_nan_trailing_root_and_utf8(
    payload: bytes,
) -> None:
    with pytest.raises(facade.StageBFacadeContractError):
        facade._decode_json(payload, label="test response")  # noqa: SLF001


def test_single_raw_decode_and_validate_boundary_enforces_size_and_exact_surface() -> (
    None
):
    payloads = ValidPayloads()
    decoded, nonce = facade.decode_and_validate_v10_response_bytes(
        "version", payloads.raw(payloads.version()), payloads.context
    )
    assert decoded == payloads.version()
    assert nonce is None

    with pytest.raises(facade.StageBFacadeContractError, match="raw bytes"):
        facade.decode_and_validate_v10_response_bytes(  # type: ignore[arg-type]
            "version", payloads.version(), payloads.context
        )
    with pytest.raises(facade.StageBFacadeContractError, match="size"):
        facade.decode_and_validate_v10_response_bytes("version", b"", payloads.context)
    with pytest.raises(facade.StageBFacadeContractError, match="size"):
        facade.decode_and_validate_v10_response_bytes(
            "version", b" " * (facade.MAX_JSON_BYTES + 1), payloads.context
        )


def test_blueprint_round_trip_is_exclusive_and_resealed_tamper_fails(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, root = blueprint_bundle
    summary = facade.validate_blueprint(blueprint)
    assert summary["valid"] is True
    assert summary["execution_ready"] is False
    assert summary["live_authorized"] is False
    assert summary["candidate_origin_trusted_before_version"] is False
    assert summary["device_io_performed_by_validator"] is False

    output = root / "written-blueprint.json"
    rewritten = facade.materialize_blueprint(
        plan_file=PLAN,
        stage_a_receipt_file=STAGE_A_RECEIPT,
        blueprint_file=output,
    )
    facade.write_new_blueprint(output, rewritten)
    assert output.read_bytes() == contract.canonical_json_bytes(rewritten) + b"\n"
    with pytest.raises(facade.StageBFacadeContractError, match="already exists"):
        facade.write_new_blueprint(output, rewritten)

    tampered = deepcopy(blueprint)
    tampered["authority_boundary"]["existing_plan_stage_order_is_satisfied"] = True
    tampered = facade._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    with pytest.raises(facade.StageBFacadeContractError, match="reconstruction"):
        facade.validate_blueprint(tampered)


def test_fake_success_is_four_bodyless_gets_with_immediate_frozen_validation(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, root = blueprint_bundle
    payloads = ValidPayloads()
    requester = facade.ScriptedFakeRequester(payloads.script(blueprint))
    output = root / "success.fake-only.json"

    result = facade.run_scripted_fake_only(
        blueprint, requester=requester, fake_output=output
    )

    assert result["state"] == "COMPLETE_FAKE_ONLY_VALIDATION"
    assert result["classification"] == facade.FAKE_RESULT_CLASSIFICATION
    assert result["requests_attempted"] == 4
    assert result["validated_response_names"] == [
        "version",
        "manifest",
        "status",
        "report",
    ]
    assert result["validation_acknowledgements"] == [
        item["absolute_url"]
        for item in blueprint["read_only_state_machine"]["ordered_requests"]
    ]
    assert result["validation_stack_outcomes"] == [
        {
            "ordinal": 1,
            "response_name": "version",
            "validator_stack": [
                "raw_size_and_strict_json_decoder",
                "source_pinned_exact_surface_validator",
            ],
            "legacy_version_subset_invoked": False,
            "outcome": "PASS",
        },
        *[
            {
                "ordinal": ordinal,
                "response_name": name,
                "validator_stack": [
                    "raw_size_and_strict_json_decoder",
                    "frozen_subset_validator",
                    "source_pinned_exact_surface_validator",
                ],
                "legacy_version_subset_invoked": False,
                "outcome": "PASS",
            }
            for ordinal, name in enumerate(("manifest", "status", "report"), start=2)
        ],
    ]
    assert result["version_protocol_conformance_simulated"] is True
    assert result["version_validation_classification"] == (
        "V10_PROTOCOL_RESPONSE_CONFORMANCE"
    )
    assert result["version_validation_is_responder_or_device_identity_proof"] is False
    assert result["version_validation_is_trusted_ip_proof"] is False
    assert result["version_validation_is_fresh_boot_or_active_app_proof"] is False
    assert result["boot_nonce"] == payloads.boot_nonce
    assert all(call["method"] == "GET" for call in result["request_log"])
    assert all(call["body"] is None for call in result["request_log"])
    assert result["post_requests"] == 0
    assert result["claims"] == 0
    assert result["client_persistent_flash_or_nvs_mutation_requests"] == 0
    assert result["client_diagnostic_api_mutation_requests"] == 0
    assert result["client_visible_refresh_requests"] == 0
    assert result["network_requests"] == 0
    assert result["device_io_performed"] is False
    assert output.read_bytes() == contract.canonical_json_bytes(result) + b"\n"
    live_output = Path(blueprint["one_shot_output_contract"]["planned_live_output"])
    assert not live_output.exists()


def test_invalid_version_stops_after_one_get_and_permanently_consumes_fake_output(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, root = blueprint_bundle
    payloads = ValidPayloads()
    bad = payloads.version()
    bad["profile"]["profile_id"] = "NOT_V10_WF20_25"
    script = payloads.script(blueprint)
    script[0] = (
        script[0][0],
        facade.ScriptedFakeResponse(200, payloads.raw(bad)),
    )
    requester = facade.ScriptedFakeRequester(script)
    output = root / "bad-version.fake-only.json"

    result = facade.run_scripted_fake_only(
        blueprint, requester=requester, fake_output=output
    )

    assert result["state"] == "TERMINAL_FAKE_ONLY_FAILURE"
    assert result["outcome"] == "TERMINAL_FAKE_ONLY_FAILURE_NO_RETRY"
    assert result["failed_endpoint"].endswith("/version")
    assert result["requests_attempted"] == 1
    assert result["validated_response_names"] == []
    assert result["validation_acknowledgements"] == []
    assert result["version_protocol_conformance_simulated"] is False
    assert result["retry_allowed"] is False

    unused_requester = facade.ScriptedFakeRequester(payloads.script(blueprint))
    with pytest.raises(facade.StageBFacadeContractError, match="no retry"):
        facade.run_scripted_fake_only(
            blueprint, requester=unused_requester, fake_output=output
        )
    assert unused_requester.calls == []


def test_invalid_manifest_stops_after_version_then_manifest(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, root = blueprint_bundle
    payloads = ValidPayloads()
    bad = payloads.manifest()
    bad["automatic_recovery"] = True
    script = payloads.script(blueprint)
    script[1] = (
        script[1][0],
        facade.ScriptedFakeResponse(200, payloads.raw(bad)),
    )
    requester = facade.ScriptedFakeRequester(script)

    result = facade.run_scripted_fake_only(
        blueprint,
        requester=requester,
        fake_output=root / "bad-manifest.fake-only.json",
    )

    assert result["state"] == "TERMINAL_FAKE_ONLY_FAILURE"
    assert result["failed_endpoint"].endswith("/manifest")
    assert result["requests_attempted"] == 2
    assert result["validated_response_names"] == ["version"]
    assert len(result["validation_acknowledgements"]) == 1
    assert result["version_protocol_conformance_simulated"] is True
    assert [call["absolute_url"].rsplit("/", 1)[-1] for call in requester.calls] == [
        "version",
        "manifest",
    ]


@pytest.mark.parametrize(
    ("failed_index", "expected_validated"),
    (
        (0, []),
        (1, ["version"]),
        (2, ["version", "manifest"]),
        (3, ["version", "manifest", "status"]),
    ),
)
def test_raw_decode_failure_at_each_endpoint_permanently_stops_before_next_get(
    blueprint_bundle: tuple[dict[str, Any], Path],
    failed_index: int,
    expected_validated: list[str],
) -> None:
    blueprint, root = blueprint_bundle
    payloads = ValidPayloads()
    script = payloads.script(blueprint)
    script[failed_index] = (
        script[failed_index][0],
        facade.ScriptedFakeResponse(200, b'{"duplicate":1,"duplicate":2}'),
    )
    requester = facade.ScriptedFakeRequester(script)
    endpoint_name = facade.ENDPOINT_NAMES[failed_index]

    result = facade.run_scripted_fake_only(
        blueprint,
        requester=requester,
        fake_output=root / f"raw-decode-{endpoint_name}.fake-only.json",
    )

    assert result["state"] == "TERMINAL_FAKE_ONLY_FAILURE"
    assert result["failed_endpoint"].endswith(f"/{endpoint_name}")
    assert result["requests_attempted"] == failed_index + 1
    assert result["validated_response_names"] == expected_validated
    assert len(result["validation_acknowledgements"]) == failed_index
    assert len(result["validation_stack_outcomes"]) == failed_index + 1
    assert result["validation_stack_outcomes"][-1]["outcome"] == ("FAILED_TERMINAL")
    assert result["version_protocol_conformance_simulated"] is (failed_index > 0)
    assert [call["absolute_url"].rsplit("/", 1)[-1] for call in requester.calls] == [
        *facade.ENDPOINT_NAMES[: failed_index + 1]
    ]


def test_fake_runner_rejects_arbitrary_callable_and_live_output(
    blueprint_bundle: tuple[dict[str, Any], Path],
) -> None:
    blueprint, root = blueprint_bundle

    class CallableRequester:
        def __call__(self, *_: object, **__: object) -> object:
            raise AssertionError("must never be called")

    with pytest.raises(facade.StageBFacadeContractError, match="exact.*type"):
        facade.run_scripted_fake_only(  # type: ignore[arg-type]
            blueprint,
            requester=CallableRequester(),
            fake_output=root / "callable.fake-only.json",
        )
    assert not (root / "callable.fake-only.json").exists()

    requester = facade.ScriptedFakeRequester(ValidPayloads().script(blueprint))
    live_output = Path(blueprint["one_shot_output_contract"]["planned_live_output"])
    with pytest.raises(facade.StageBFacadeContractError, match="planned live output"):
        facade.run_scripted_fake_only(
            blueprint, requester=requester, fake_output=live_output
        )
    assert requester.calls == []
    assert not live_output.exists()


def test_blueprint_source_has_no_live_transport_or_cli_surface() -> None:
    source = Path(facade.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        str(node.module).split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imported_roots.isdisjoint(
        {"urllib", "requests", "httpx", "socket", "serial", "subprocess"}
    )
    assert "AUTHORIZE_" not in source
    assert 'http_client_implemented": False' in source
    parser = facade._parser()  # noqa: SLF001
    subparsers = [
        action
        for action in parser._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    ]
    assert len(subparsers) == 1
    assert set(subparsers[0].choices) == {"build", "validate"}
    assert json.loads(
        contract.canonical_json_bytes(
            {"device_network_accessed": False, "device_io_performed": False}
        )
    ) == {"device_io_performed": False, "device_network_accessed": False}
