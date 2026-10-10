from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from typing import Any

import pytest

from tools import mf1750_ec5_color_lab_physical_once as legacy_engine
from tools import mf1750_ec5_color_lab_recovery_campaign as campaign
from tools import mf1750_ec5_color_lab_recovery_contract as contract
from tools import mf1750_ec5_color_lab_recovery_physical_once as recovery


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = (
    ROOT
    / ".test-output/hardware/"
    "MF1750_EC5_COLOR_LAB_RECOVERY_REAL_COMPARE_BOUND_20260810_"
    "V3_SELF_CONTAINED"
)
RELEASE = BUNDLE / "color-lab-recovery-real-release.json"
BUNDLE_MANIFEST = BUNDLE / "bundle-manifest.json"


def _legacy_fake_module() -> Any:
    path = ROOT / "tests/test_mf1750_ec5_color_lab_physical_once.py"
    spec = importlib.util.spec_from_file_location("_color_lab_fake_fixture", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load fake-device fixture")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _recovery_fake_device(
    context: recovery.ReleaseContext, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, Any]:
    fixture = _legacy_fake_module()
    monkeypatch.setattr(fixture, "campaign", campaign)
    monkeypatch.setattr(fixture, "contract", contract)
    fixture_identity = fixture._identity

    def recovery_identity(kind: str) -> dict[str, Any]:
        return fixture_identity(
            kind.replace(
                "mf1750-ec5-color-lab-",
                "mf1750-ec5-color-lab-recovery-",
            )
        )

    monkeypatch.setattr(fixture, "_identity", recovery_identity)
    return fixture, fixture.FakeDevice(context)


def _late_terminal_timeout_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[recovery.ReleaseContext, Any, Path, Path]:
    context = recovery.load_release(RELEASE)
    _fixture, device = _recovery_fake_device(context, monkeypatch)
    registry = tmp_path / "recovery-claims"
    diagnostic_file = tmp_path / "j2-off-diagnostic.json"
    recovery.diagnose_j2_off(
        context,
        "http://offline-recovery-device",
        evidence_file=diagnostic_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    run_requests = 0
    run_trace: list[tuple[str, str]] = []

    def timeout_after_execute(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Any,
        timeout: float,
    ) -> Any:
        nonlocal run_requests
        run_requests += 1
        run_trace.append((method, path))
        if run_requests == 8:
            assert method == "GET"
            assert path.endswith("/status")
            raise recovery.ColorLabRecoveryPhysicalError(
                f"GET {path} failed: simulated timeout"
            )
        return device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )

    source_file = tmp_path / "ordinal-01-unknown-result.json"
    source = recovery.run_once(
        context,
        "http://offline-recovery-device",
        1,
        authorization=recovery.required_authorization(context, 1),
        result_file=source_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=timeout_after_execute,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert source["outcome"] == "unknown_do_not_retry_or_recover", run_trace
    assert source["network"] == {
        "get_requests": 5,
        "arm_posts": 1,
        "execute_posts": 1,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }
    assert len(source["transcript"]) == 7
    return context, device, registry, source_file


def test_exact_bundle_release_incident_and_isolation_gate() -> None:
    checked = recovery.validate_bundle(BUNDLE_MANIFEST)
    context = recovery.load_release(RELEASE)
    assert checked["file_sha256"] == recovery.EXPECTED_BUNDLE_FILE_SHA256
    assert checked["release_file_sha256"] == recovery.EXPECTED_RELEASE_FILE_SHA256
    assert checked["action_count"] == 23
    assert context.release_root["recovery_boundary"]["incident_result"][
        "file_sha256"
    ] == recovery.EXPECTED_INCIDENT_RESULT_SHA256
    assert context.release_root["recovery_boundary"]["permanent_claim"][
        "file_sha256"
    ] == recovery.EXPECTED_INCIDENT_CLAIM_SHA256
    assert contract.NVS_NAMESPACE == "mf1750_ec5clr"
    assert contract.NVS_KEY == "cursor_r1"
    assert recovery.DEFAULT_CLAIM_REGISTRY.name == (
        ".mf1750_ec5_color_lab_recovery_claims"
    )


def test_ordinal1_fake_device_full_recovery_host_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _legacy_fake_module()
    monkeypatch.setattr(fixture, "campaign", campaign)
    monkeypatch.setattr(fixture, "contract", contract)
    fixture_identity = fixture._identity

    def recovery_identity(kind: str) -> dict[str, Any]:
        return fixture_identity(
            kind.replace(
                "mf1750-ec5-color-lab-",
                "mf1750-ec5-color-lab-recovery-",
            )
        )

    monkeypatch.setattr(fixture, "_identity", recovery_identity)
    context = recovery.load_release(RELEASE)
    device = fixture.FakeDevice(context)
    registry = tmp_path / "recovery-claims"
    diagnostic_file = tmp_path / "j2-off-diagnostic.json"
    claim_file = registry / f"{context.actions[0]['action_id']}.json"

    def claimed_device(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("method") == "POST":
            assert claim_file.is_file(), "permanent claim must precede first POST"
        return device(*args, **kwargs)

    before = (
        legacy_engine.campaign,
        legacy_engine.contract,
        legacy_engine.CLAIM_KIND,
        legacy_engine.DEFAULT_CLAIM_REGISTRY,
    )
    diagnostic = recovery.diagnose_j2_off(
        context,
        "http://offline-recovery-device",
        evidence_file=diagnostic_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=claimed_device,
    )
    after_diagnostic = (
        legacy_engine.campaign,
        legacy_engine.contract,
        legacy_engine.CLAIM_KIND,
        legacy_engine.DEFAULT_CLAIM_REGISTRY,
    )
    assert after_diagnostic == before
    assert diagnostic["kind"] == recovery.J2_OFF_DIAGNOSTIC_KIND
    assert diagnostic["network"] == {"get_requests": 4, "post_requests": 0}
    assert diagnostic["boot_nonce"] == fixture.BOOT_NONCE
    assert not registry.exists()

    device.busy = 1
    result_file = tmp_path / "ordinal-01-result.json"
    result = recovery.run_once(
        context,
        "http://offline-recovery-device",
        1,
        authorization=recovery.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=claimed_device,
        sleeper=lambda _seconds: None,
    )
    assert result["kind"] == recovery.RESULT_KIND
    assert result["outcome"] == "complete_pass", result["error"]
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert result["preflight"]["boot_nonce"] == diagnostic["boot_nonce"]
    assert result["device"]["terminal_status"]["total_driver_call_count"] == 1
    assert recovery.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "complete_pass"

    claim = campaign._decode(claim_file.read_bytes(), label="test recovery claim")
    assert claim["kind"] == recovery.CLAIM_KIND
    assert claim["registry_id"] == recovery.CLAIM_REGISTRY_ID
    assert claim["automatic_retry"] is False
    assert claim["automatic_recovery"] is False
    posts = [entry for entry in result["transcript"] if entry["method"] == "POST"]
    assert [entry["path"] for entry in posts] == [
        campaign.ENDPOINTS["arm"],
        campaign.ENDPOINTS["execute"],
    ]
    assert posts[0]["headers"]["X-EC5-Intent"] == campaign.ARM_INTENT
    assert posts[1]["headers"]["X-EC5-Intent"] == campaign.EXECUTE_INTENT

    observation_file = tmp_path / "ordinal-01-observation.json"
    observation = recovery.finalize_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=registry,
        operator_report="offline fake recovery white frame matched reference",
        temperature_c=37.0,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=True,
    )
    assert observation["kind"] == recovery.OBSERVATION_KIND
    assert recovery.validate_observation(
        context,
        observation_file,
        result_file=result_file,
        claim_registry=registry,
    )["sequence_gate_pass"] is True
    assert (
        legacy_engine.campaign,
        legacy_engine.contract,
        legacy_engine.CLAIM_KIND,
        legacy_engine.DEFAULT_CLAIM_REGISTRY,
    ) == before


def test_tampered_incident_gate_fails_before_request_or_claim(
    tmp_path: Path,
) -> None:
    context = recovery.load_release(RELEASE)
    root = deepcopy(dict(context.release_root))
    root["recovery_boundary"]["incident_result"]["file_sha256"] = "0" * 64
    tampered = recovery.ReleaseContext(
        release_file=context.release_file,
        release_root=root,
        release_file_sha256=context.release_file_sha256,
        release_canonical_sha256=context.release_canonical_sha256,
        campaign_file=context.campaign_file,
        campaign_root=context.campaign_root,
        actions=context.actions,
        execution_eligible=context.execution_eligible,
        formal_u07_registry=context.formal_u07_registry,
    )
    with pytest.raises(
        recovery.ColorLabRecoveryPhysicalError,
        match="incident/claim binding differs",
    ):
        recovery.diagnose_j2_off(
            tampered,
            "http://must-not-be-called",
            evidence_file=tmp_path / "diagnostic.json",
            claim_registry=tmp_path / "claims",
            confirm_j2_off=True,
            requester=lambda *_args, **_kwargs: pytest.fail("requester called"),
        )
    assert not (tmp_path / "claims").exists()


def test_recovery_http_post_is_bodyless_after_urllib_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Parent:
        addheaders: list[tuple[str, str]] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        @staticmethod
        def getcode() -> int:
            return 200

        @staticmethod
        def read(_maximum: int) -> bytes:
            return b'{"accepted":true}'

    def fake_urlopen(request: Any, *, timeout: float) -> Response:
        handler = legacy_engine.urllib.request.HTTPHandler()
        handler.parent = Parent()
        processed = handler.do_request_(request)
        captured["method"] = processed.get_method()
        captured["data"] = processed.data
        captured["headers"] = {
            key.lower(): value for key, value in processed.header_items()
        }
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(legacy_engine.urllib.request, "urlopen", fake_urlopen)
    status, _response = recovery.http_request(
        "http://offline-recovery-device",
        campaign.ENDPOINTS["arm"],
        method="POST",
        headers={"X-EC5-Intent": campaign.ARM_INTENT},
        timeout=3.0,
    )
    assert status == 200
    assert captured["method"] == "POST"
    assert captured["data"] is None
    assert "content-length" not in captured["headers"]
    assert "content-type" not in captured["headers"]


def test_late_terminal_reconciliation_is_two_gets_and_seals_both_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, device, registry, source_file = _late_terminal_timeout_result(
        tmp_path, monkeypatch
    )
    source_payload = source_file.read_bytes()
    calls_before = len(device.calls)
    result_file = tmp_path / "ordinal-01-reconciled-result.json"
    evidence_file = tmp_path / "ordinal-01-reconciliation.json"

    def get_only(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["method"] == "GET", "reconciliation must never send POST"
        return device(*args, **kwargs)

    operation = recovery.reconcile_result(
        context,
        "http://offline-recovery-device",
        source_result_file=source_file,
        result_file=result_file,
        reconciliation_file=evidence_file,
        claim_registry=registry,
        requester=get_only,
    )
    result = operation["result"]
    assert source_file.read_bytes() == source_payload
    assert result["outcome"] == "complete_pass"
    assert result["error"] is None
    assert result["network"]["get_requests"] == 7
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert result["device"]["terminal_status"]["next_ordinal"] == 2
    assert result["device"]["terminal_report"]["terminal_state"] == "COMPLETE"
    assert result["reconciliation"]["mutation_requests_sent"] == 0
    assert result["reconciliation"]["source_result_not_modified"] is True
    assert recovery.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "complete_pass"
    evidence = recovery.validate_reconciliation(
        context, evidence_file, claim_registry=registry
    )
    assert evidence == operation["reconciliation_evidence"]
    assert evidence["derived_complete_result"]["file"] == str(
        result_file.resolve()
    )
    new_calls = device.calls[calls_before:]
    assert [(method, path) for method, path, _headers in new_calls] == [
        ("GET", campaign.ENDPOINTS["status"]),
        ("GET", campaign.ENDPOINTS["report"]),
    ]

    observation_file = tmp_path / "ordinal-01-observation.json"
    observation = recovery.finalize_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=registry,
        operator_report=(
            "full screen clean white; prior four blue patches absent; no residual"
        ),
        temperature_c=37.0,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=True,
    )
    assert observation["sequence_gate_pass"] is True


@pytest.mark.parametrize("drift", ["boot_nonce", "report_action"])
def test_late_terminal_reconciliation_fails_closed_on_terminal_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    context, device, registry, source_file = _late_terminal_timeout_result(
        tmp_path, monkeypatch
    )
    if drift == "boot_nonce":
        device.boot_nonce = "1111111111111111"
    else:
        device.last_report["action_id"] = "0" * 64
    source_payload = source_file.read_bytes()
    result_file = tmp_path / "must-not-exist-result.json"
    evidence_file = tmp_path / "must-not-exist-reconciliation.json"
    methods: list[str] = []

    def get_only(*args: Any, **kwargs: Any) -> Any:
        methods.append(kwargs["method"])
        assert kwargs["method"] == "GET"
        return device(*args, **kwargs)

    with pytest.raises(recovery.ColorLabRecoveryPhysicalError):
        recovery.reconcile_result(
            context,
            "http://offline-recovery-device",
            source_result_file=source_file,
            result_file=result_file,
            reconciliation_file=evidence_file,
            claim_registry=registry,
            requester=get_only,
        )
    assert methods == (["GET"] if drift == "boot_nonce" else ["GET", "GET"])
    assert source_file.read_bytes() == source_payload
    assert not result_file.exists()
    assert not evidence_file.exists()


def test_late_terminal_reconciliation_rejects_source_prefix_before_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _device, registry, source_file = _late_terminal_timeout_result(
        tmp_path, monkeypatch
    )
    source = campaign._decode(
        source_file.read_bytes(), label="test late-terminal source"
    )
    unsigned = deepcopy(dict(source))
    unsigned.pop("integrity")
    unsigned["transcript"][4], unsigned["transcript"][5] = (
        unsigned["transcript"][5],
        unsigned["transcript"][4],
    )
    tampered_file = tmp_path / "validly-sealed-wrong-prefix.json"
    tampered_file.write_bytes(
        campaign.canonical_json_bytes(legacy_engine._seal(unsigned))
    )
    requested = False

    def forbidden_request(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal requested
        requested = True
        pytest.fail("source gate must reject before any request")

    with pytest.raises(
        recovery.ColorLabRecoveryPhysicalError,
        match="exact late-timeout prefix",
    ):
        recovery.reconcile_result(
            context,
            "http://must-not-be-called",
            source_result_file=tampered_file,
            result_file=tmp_path / "must-not-exist-result.json",
            reconciliation_file=tmp_path / "must-not-exist-reconciliation.json",
            claim_registry=registry,
            requester=forbidden_request,
        )
    assert requested is False
