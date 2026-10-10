from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_stable_code0_luma_latin_v3_white_successor_v1_once as once
from tools import mf1750_stable_code0_luma_latin_v3_white_successor_v1_pack as pack


def test_white_successor_is_sealed_and_factory_otp_only() -> None:
    report = pack.build_report(verify_artifacts=True)
    checked = pack.dry_validate(verify_artifacts=True)
    assert checked["result"] == "PASS"
    assert report["contract"]["accepted_source_ordinals"] == [3, 4]
    assert report["contract"]["factory_otp"] is True
    assert report["contract"]["runtime_lut_write"] is False
    assert report["contract"]["one_visible_refresh"] is True
    assert report["contract"]["autochain"] is False


def test_white_device_has_one_exact_otp_call_and_no_runtime_lut() -> None:
    source = (
        pack.REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_white_successor_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert source.count("epdDisplayCompiledFactoryOtpWhiteRecovery();") == 1
    assert "epdDisplayCompiledChromaGrid" not in source
    assert "runtime_lut" not in source.lower()
    assert "accepted_source_complete_ordinals" in source
    assert "[3,4]" in source


def test_white_run_rejects_missing_physical_assertions_before_request() -> None:
    touched = False

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("requester must not be reached")

    with pytest.raises(once.WhiteSuccessorV1Error, match="J2-ON"):
        once.run_once(
            "http://127.0.0.1",
            source_terminal_evidence=Path("unused"),
            confirm_j2_on=False,
            confirm_gnd_normal=True,
            requester=requester,
        )
    with pytest.raises(once.WhiteSuccessorV1Error, match="GND-normal"):
        once.run_once(
            "http://127.0.0.1",
            source_terminal_evidence=Path("unused"),
            confirm_j2_on=True,
            confirm_gnd_normal=False,
            requester=requester,
        )
    assert touched is False


def test_source_gate_is_fixed_and_o_excl() -> None:
    text = Path(once.__file__).read_text(encoding="utf-8")
    assert "selected_source_terminal_evidence" in text
    assert '"write_contract": "O_EXCL"' in text
    assert "source_once.validate_terminal_evidence(candidate)" in text
    assert "_validate_source_receipt(source)" in text


def test_recomputed_integrity_cannot_hide_source_receipt_schema_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = {"verified": True, "ordinal": 3}
    changed = {
        "schema_version": 2,
        "kind": "mf1750-stable-code0-luma-latin-v3-white-successor-v1-source-gate",
        "created_at": "2026-09-01T00:00:00.000+00:00",
        "white_campaign_id": pack.CAMPAIGN_ID,
        "white_contract_id": pack.CONTRACT_ID,
        "white_descriptor_id": pack.DESCRIPTOR_ID,
        "white_action_id": pack.ACTION_ID,
        "selected_source_terminal_evidence": source,
        "state": "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST",
        "write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    sealed = {
        **changed,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": hashlib.sha256(once.host._base._canonical(changed)).hexdigest(),
        },
    }
    path = tmp_path / "source-gate.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    monkeypatch.setattr(once, "SOURCE_GATE_OUTPUT", path)
    with pytest.raises(once.WhiteSuccessorV1Error, match="receipt differs"):
        once._validate_source_receipt(source)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("outcome", "tampered"),
        ("firmware_sha256", "0" * 64),
        ("running_app_elf_sha256", "0" * 64),
        ("fresh_nvs", False),
        ("busy", 1),
        ("report_terminal_state", "COMPLETE"),
        ("artifact_preflight_completed_before_network", False),
        ("visible_refreshes", 1),
        ("output_write_contract", "overwrite"),
        ("no_retry", False),
    ],
)
def test_recomputed_integrity_cannot_hide_diagnostic_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    tampered: object,
) -> None:
    source = {
        "verified": True,
        "terminal_state": "COMPLETE",
        "ordinal": 3,
        "path": "fixed-source.json",
        "bytes": 1,
        "file_sha256": "1" * 64,
        "canonical_integrity_sha256": "2" * 64,
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "descriptor_id": pack.build_report()["contract"][
            "accepted_source_complete_actions"
        ][0]["descriptor_id"],
        "action_id": pack.build_report()["contract"][
            "accepted_source_complete_actions"
        ][0]["action_id"],
        "boot_nonce": "0123456789abcdef",
        "claim": {
            "path": "fixed-claim.json",
            "bytes": 1,
            "file_sha256": "3" * 64,
            "canonical_integrity_sha256": "4" * 64,
        },
        "optional_l4_explicitly_confirmed": False,
    }
    boot = "fedcba9876543210"
    names = ("version", "manifest", "status", "report")
    bodies = [{}, {}, {"boot_nonce": boot}, {}]
    transcript = [
        {
            "method": "GET",
            "endpoint": name,
            "path": once.host.ENDPOINTS[name],
            "headers": {},
            "status": 200,
            "body": body,
        }
        for name, body in zip(names, bodies, strict=True)
    ]
    body = {
        "schema_version": 1,
        "kind": once.host.DIAGNOSTIC_KIND,
        **once._dynamic_source_binding(source),
        "created_at": "2026-09-01T00:00:00.000+00:00",
        "outcome": "j2_off_diagnostic_pass",
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "running_app_elf_sha256": pack.FIRMWARE_ELF_SHA256,
        "boot_nonce": boot,
        "action": once.REPORT["action"],
        "j2_confirmed_off": True,
        "fresh_nvs": True,
        "busy": 0,
        "report_terminal_state": "NOT_EXECUTED",
        "report": bodies[3],
        "artifact_preflight_completed_before_network": True,
        "base_url": "http://127.0.0.1",
        "transport": {
            "mode": "direct_private_literal_ipv4_http",
            "proxy": False,
            "redirect": False,
        },
        "permanent_claims_created": 0,
        "claims_directory_accessed": False,
        "network": {"get": 4, "post": 0},
        "transcript": transcript,
        "visible_refreshes": 0,
        "output_write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    changed = deepcopy(body)
    changed[field] = tampered
    canonical = once.host._base._canonical(changed)
    sealed = {
        **changed,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": hashlib.sha256(canonical).hexdigest(),
        },
    }
    path = tmp_path / "diagnostic.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    monkeypatch.setattr(once.host, "DIAGNOSTIC_OUTPUT", path)
    monkeypatch.setattr(
        once.host, "_validate_version", lambda value: pack.FIRMWARE_ELF_SHA256
    )
    monkeypatch.setattr(once.host._base, "_validate_manifest", lambda *args: None)
    monkeypatch.setattr(
        once.host,
        "_validate_fresh_status",
        lambda *args, **kwargs: boot,
    )
    monkeypatch.setattr(once.host._base, "_validate_fresh_report", lambda *args: None)
    with pytest.raises(once.WhiteSuccessorV1Error, match="envelope differs"):
        once._validate_diagnostic("http://127.0.0.1", source)
