from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib import request as urllib_request

import pytest

from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_pack as old
from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_once as once
from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_pack as pre


ROOT = Path(__file__).resolve().parents[1]


def test_successor_identity_and_every_consumable_namespace_are_fresh() -> None:
    report = pre.build_report(verify_artifacts=True)
    old_report = old.build_report(verify_artifacts=False)
    assert report["contract_id"] == pre.CONTRACT_ID
    assert pre._canonical_sha256(pre.contract()) == pre.CONTRACT_ID
    assert pre._canonical_sha256(pre.action_basis()) == pre.ACTION_ID
    assert pre._canonical_sha256(pre.descriptor_basis()) == pre.DESCRIPTOR_ID
    assert pre.CAMPAIGN_ID != old.CAMPAIGN_ID
    assert pre.TEST_ID != old.TEST_ID
    assert pre.BUILD_TAG != old.BUILD_TAG
    assert pre.ENVIRONMENT != old.ENVIRONMENT
    assert pre.BASE_ROUTE != old.BASE_ROUTE
    assert pre.NVS_NAMESPACE != old.NVS_NAMESPACE
    assert pre.NVS_KEY != old.NVS_KEY
    assert pre.CONTRACT_ID != old.CONTRACT_ID
    assert pre.ACTION_ID != old.ACTION_ID
    assert pre.DESCRIPTOR_ID != old.DESCRIPTOR_ID
    assert once.base.DEFAULT_CLAIMS != (
        ROOT / ".test-output/hardware/.mf1750_raw_p16_pre_white_anchor_v1_claims"
    )
    assert "v1b" in str(once.base.DEFAULT_CLAIMS).lower()
    assert "V1B" in str(once.base.DEFAULT_OUTPUT)
    assert report["contract"] != old_report["contract"]


def test_successor_is_exactly_one_factory_otp_white_action() -> None:
    report = pre.build_report(verify_artifacts=True)
    contract = report["contract"]
    assert report["action"] == {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR_SUCCESSOR_V1B",
        "descriptor_id": pre.DESCRIPTOR_ID,
        "action_id": pre.ACTION_ID,
        "purpose": "successor_pre_gallery_factory_otp_white_anchor",
        "frame_sha256": pre.FRAME_SHA256,
        "cs1_dtm_sha256": pre.DTM_SHA256,
        "cs2_dtm_sha256": pre.DTM_SHA256,
    }
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_successor_artifacts_are_exactly_bound() -> None:
    report = pre.build_report(verify_artifacts=True)
    for key, path, size, digest in (
        (
            "firmware_bin",
            pre.FIRMWARE_BIN,
            pre.FIRMWARE_BIN_BYTES,
            pre.FIRMWARE_BIN_SHA256,
        ),
        (
            "firmware_elf",
            pre.FIRMWARE_ELF,
            pre.FIRMWARE_ELF_BYTES,
            pre.FIRMWARE_ELF_SHA256,
        ),
    ):
        payload = path.read_bytes()
        assert report["artifact_binding_status"][key]["verified"] is True
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_successor_firmware_source_and_route_are_isolated() -> None:
    main = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b_main.cpp"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_program.inc"
    ).read_text(encoding="utf-8")
    identity = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b_identity.inc"
    ).read_text(encoding="utf-8")
    platformio = (
        ROOT / "platformio.raw_p16_endpoint_gallery_pre_white_anchor_v1b.ini"
    ).read_text(encoding="utf-8")
    assert "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_program.inc" in main
    assert pre.CONTRACT_ID in identity
    assert pre.ACTION_ID in identity
    assert pre.DESCRIPTOR_ID in identity
    assert pre.BASE_ROUTE in program
    assert pre.NVS_KEY in program
    assert "MF1750_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B=1" in platformio
    assert "+<ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b_main.cpp>" in platformio
    assert program.count("epdDisplayCompiledFactoryOtpWhiteRecovery();") == 1


def test_successor_runner_is_direct_no_proxy_and_never_follows_redirects() -> None:
    assert isinstance(once._NO_PROXY_HANDLER, urllib_request.ProxyHandler)
    assert once._NO_PROXY_HANDLER.proxies == {}
    assert not any(
        isinstance(handler, urllib_request.ProxyHandler) and bool(handler.proxies)
        for handler in once._DIRECT_OPENER.handlers
    )
    rejector = once._RejectRedirects()
    assert (
        rejector.redirect_request(None, None, 302, "found", {}, "http://other") is None
    )
    value = once.describe()
    assert value["transport"] == {
        "proxy_use": False,
        "redirect_follow": False,
        "direct_http_only": True,
        "origin_policy": (
            "HTTP_LOCAL_IPV4_LITERAL_PORT_80_NO_USERINFO_PATH_QUERY_FRAGMENT"
        ),
    }
    assert value["artifact_validation_before_claim"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0


@pytest.mark.parametrize(
    "origin",
    (
        "https://192.168.1.11",
        "http://device.local",
        "http://8.8.8.8",
        "http://user@192.168.1.11",
        "http://192.168.1.11/api",
        "http://192.168.1.11?x=1",
        "http://192.168.1.11#fragment",
        "http://192.168.1.11:81",
    ),
)
def test_direct_origin_rejects_nonlocal_or_ambiguous_origins(origin: str) -> None:
    with pytest.raises(once.base.ContainmentError):
        once._validate_direct_origin(origin)


@pytest.mark.parametrize(
    ("origin", "normalized"),
    (
        ("http://192.168.1.11", "http://192.168.1.11"),
        ("http://192.168.1.11/", "http://192.168.1.11"),
        ("http://192.168.1.11:80", "http://192.168.1.11:80"),
    ),
)
def test_direct_origin_accepts_expected_local_ipv4(
    origin: str, normalized: str
) -> None:
    assert once._validate_direct_origin(origin) == normalized


def test_artifact_validation_precedes_claim_and_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"network": 0}

    def invalid_artifacts(*, verify_artifacts: bool = True) -> dict[str, object]:
        assert verify_artifacts is True
        raise ValueError("injected local artifact mismatch")

    def requester(*args: object, **kwargs: object) -> tuple[int, dict[str, object]]:
        del args, kwargs
        calls["network"] += 1
        return 500, {}

    monkeypatch.setattr(pre, "build_report", invalid_artifacts)
    claims = tmp_path / "fresh-v1b-claims"
    with pytest.raises(ValueError, match="local artifact mismatch"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=tmp_path / "result.json",
            requester=requester,
        )
    assert calls["network"] == 0
    assert not claims.exists()


def test_dry_validate_is_local_and_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert once.main(["dry-validate"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["dry_validation"] == "PASS"
    assert value["artifact_validation_before_claim"] is True
    assert value["artifact_binding_status"]["firmware_bin"]["verified"] is True
    assert value["artifact_binding_status"]["firmware_elf"]["verified"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
