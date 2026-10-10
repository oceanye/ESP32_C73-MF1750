from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tests import test_mf1750_same_r20_aa_abort_white_v1 as v1_test
from tools import mf1750_same_r20_aa_abort_white_v1b_successor_once as once
from tools import mf1750_same_r20_aa_abort_white_v1b_successor_pack as pack


def _malformed_wire(value: Mapping[str, Any]) -> bytes:
    reordered = {
        key: item
        for key, item in value.items()
        if key
        not in (
            "relay_off_receipt_is_command_query_not_load_voltage_proof",
            "profile_id",
        )
    }
    reordered["relay_off_receipt_is_command_query_not_load_voltage_proof"] = value[
        "relay_off_receipt_is_command_query_not_load_voltage_proof"
    ]
    reordered["profile_id"] = value["profile_id"]
    normalized = json.dumps(
        reordered,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert normalized.count(pack.CORRECTED_IDENTITY_MARKER) == 1
    return normalized.replace(
        pack.CORRECTED_IDENTITY_MARKER, pack.MALFORMED_IDENTITY_MARKER, 1
    )


class EvidencedFake:
    def __init__(self, *, busy: int, expected_claim: Path | None = None) -> None:
        self.base = v1_test.FakeDevice(busy=busy, expected_claim=expected_claim)

    @property
    def calls(self) -> list[tuple[str, str]]:
        return self.base.calls

    def __call__(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        status, value = self.base(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )
        raw = _malformed_wire(value)
        return status, once._decode_exact_malformed_identity_payload(  # noqa: SLF001
            raw,
            method=method,
            path=path,
            response_headers={"content-type": "application/json"},
        )


def _patch_fixed_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path, Path]:
    diagnostic = tmp_path / "v1b" / "j2-off-diagnostic.json"
    action = tmp_path / "v1" / "action-01-factory-otp-white.json"
    claims = tmp_path / "claims"
    claim = claims / f"{pack.v1_pack.ACTION_ID}.json"
    monkeypatch.setattr(once, "SUCCESSOR_DIAGNOSTIC_OUTPUT", diagnostic)
    monkeypatch.setattr(once, "ACTION_OUTPUT", action)
    monkeypatch.setattr(once, "DEFAULT_CLAIMS", claims)
    monkeypatch.setattr(pack, "ACTION_OUTPUT", action)
    monkeypatch.setattr(pack, "CLAIMS_ROOT", claims)
    monkeypatch.setattr(pack, "CLAIM_FILE", claim)
    return diagnostic, action, claims


def test_dry_validate_binds_failed_attempt_flash_and_unique_bin_defect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fixed_paths(monkeypatch, tmp_path)
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["network_requests"] == 0
    assert value["firmware_flashed"] is False
    assert (
        value["predecessor_failed_diagnostic_sha256"] == pack.FAILED_DIAGNOSTIC_SHA256
    )
    assert value["predecessor_flash_evidence_sha256"] == pack.FLASH_SHA256
    assert value["artifact_binding"]["malformed_identity_marker_count"] == 1
    assert value["artifact_binding"]["corrected_identity_marker_count"] == 0


def test_exact_decoder_accepts_only_unique_bad_marker_and_records_raw() -> None:
    raw = _malformed_wire(v1_test._version())  # noqa: SLF001
    value = once._decode_exact_malformed_identity_payload(  # noqa: SLF001
        raw, method="GET", path="/version"
    )
    once._validate_normalization_evidence(value)  # noqa: SLF001
    evidence = value[once.NORMALIZATION_EVIDENCE_KEY]
    assert evidence["malformed_marker_offset"] == raw.find(
        pack.MALFORMED_IDENTITY_MARKER
    )
    assert evidence["raw_body_bytes"] == len(raw)
    assert evidence["normalized_body_bytes"] == len(raw) - 1


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        pack.MALFORMED_IDENTITY_MARKER * 2,
        pack.MALFORMED_IDENTITY_MARKER + pack.CORRECTED_IDENTITY_MARKER,
        pack.MALFORMED_IDENTITY_MARKER + b"not-json",
        pack.MALFORMED_IDENTITY_MARKER + b"\xff",
    ],
)
def test_exact_decoder_fails_closed_for_zero_two_corrected_or_other_damage(
    payload: bytes,
) -> None:
    with pytest.raises(once.ContainmentError):
        once._decode_exact_malformed_identity_payload(  # noqa: SLF001
            payload, method="GET", path="/version"
        )


def test_successor_diagnostic_is_exactly_four_get_zero_post_o_excl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic, _, _ = _patch_fixed_paths(monkeypatch, tmp_path)
    predecessor_before = pack.FAILED_DIAGNOSTIC_FILE.read_bytes()
    fake = EvidencedFake(busy=0)
    result = once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=fake,
    )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert result["outcome"] == "j2_off_diagnostic_pass"
    assert result["network"] == {"get": 4, "post": 0}
    assert result["permanent_claims_created"] == 0
    assert result["visible_refreshes"] == 0
    assert result["successor_id"] == pack.SUCCESSOR_ID
    assert pack.FAILED_DIAGNOSTIC_FILE.read_bytes() == predecessor_before
    with pytest.raises(once.ContainmentError, match="refusing to overwrite"):
        once.diagnose_j2_off(
            "http://192.168.1.11",
            output=diagnostic,
            confirm_j2_off=True,
            requester=EvidencedFake(busy=0),
        )


def test_run_accepts_only_successor_same_boot_and_reuses_v1_action_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic, action, claims = _patch_fixed_paths(monkeypatch, tmp_path)
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=EvidencedFake(busy=0),
    )
    claim = claims / f"{pack.v1_pack.ACTION_ID}.json"
    fake = EvidencedFake(busy=1, expected_claim=claim)
    result = once.run_once(
        "http://192.168.1.11",
        claims=claims,
        output=action,
        confirm_j2_on=True,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
        ("GET", "report"),
    ]
    assert result["outcome"] == "complete_pass"
    assert result["action"]["action_id"] == pack.v1_pack.ACTION_ID
    assert claim.is_file()


def test_missing_or_failed_successor_blocks_run_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _diagnostic, action, claims = _patch_fixed_paths(monkeypatch, tmp_path)
    calls: list[str] = []

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        calls.append("network")
        raise AssertionError("network must not be reached")

    with pytest.raises(once.ContainmentError):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=action,
            confirm_j2_on=True,
            requester=requester,
        )
    assert calls == []


def test_run_rejects_injected_corrected_mapping_without_raw_evidence_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic, action, claims = _patch_fixed_paths(monkeypatch, tmp_path)
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=EvidencedFake(busy=0),
    )
    plain = v1_test.FakeDevice(busy=1)
    with pytest.raises(
        once.ContainmentError, match="normalization evidence is missing"
    ):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=action,
            confirm_j2_on=True,
            requester=plain,
        )
    assert plain.calls == [("GET", "version")]
    assert not (claims / f"{pack.v1_pack.ACTION_ID}.json").exists()
    result = json.loads(action.read_text(encoding="utf-8"))
    assert result["network"] == {"get": 1, "post": 0}
    assert result["claim_state"] == "not_created"


def test_same_boot_nonce_drift_blocks_before_claim_and_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic, action, claims = _patch_fixed_paths(monkeypatch, tmp_path)
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=EvidencedFake(busy=0),
    )
    fake = EvidencedFake(busy=1)
    original = fake.base

    def drifted(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        status, value = original(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )
        value = dict(value)
        if path.endswith("/status"):
            value["boot_nonce"] = "1111111111111111"
        raw = _malformed_wire(value)
        return status, once._decode_exact_malformed_identity_payload(  # noqa: SLF001
            raw, method=method, path=path
        )

    with pytest.raises(once.ContainmentError, match="boot nonce differs"):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=action,
            confirm_j2_on=True,
            requester=drifted,
        )
    assert original.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert not (claims / f"{pack.v1_pack.ACTION_ID}.json").exists()


def test_fixed_successor_diagnostic_and_shared_v1_action_paths(
    tmp_path: Path,
) -> None:
    with pytest.raises(once.ContainmentError, match="diagnostic output is fixed"):
        once.diagnose_j2_off(
            "http://192.168.1.11",
            output=tmp_path / "wrong.json",
            confirm_j2_off=True,
            requester=EvidencedFake(busy=0),
        )
    assert once.ACTION_OUTPUT == pack.V1_ROOT / "action-01-factory-otp-white.json"
    assert once.DEFAULT_CLAIMS == pack.CLAIMS_ROOT


def test_predecessor_failed_evidence_hash_tamper_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "failed.json"
    data = bytearray(pack.FAILED_DIAGNOSTIC_FILE.read_bytes())
    data[-2] ^= 1
    tampered.write_bytes(data)
    monkeypatch.setattr(pack, "FAILED_DIAGNOSTIC_FILE", tampered)
    with pytest.raises(ValueError, match="file binding differs"):
        pack.validate_predecessor_evidence(require_unexecuted=True)
