from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_once as once
from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_pack as pre
from tools import mf1750_raw_p16_endpoint_gallery_v1_pack as gallery
from tools import mf1750_raw_p16_endpoint_gallery_v1_white_containment_pack as post


ROOT = Path(__file__).resolve().parents[1]


def test_pre_white_identity_is_fresh_and_closes_into_gallery() -> None:
    report = pre.build_report(verify_artifacts=True)
    gallery_report = gallery.build_report(verify_artifacts=False)
    contract = report["contract"]
    assert report["contract_id"] == pre.CONTRACT_ID
    assert pre._canonical_sha256(pre.contract()) == pre.CONTRACT_ID
    assert pre._canonical_sha256(pre.action_basis()) == pre.ACTION_ID
    assert pre._canonical_sha256(pre.descriptor_basis()) == pre.DESCRIPTOR_ID
    assert contract["purpose"] == "pre_gallery_factory_otp_white_anchor"
    assert contract["target_campaign_id"] == gallery.CAMPAIGN_ID
    assert pre.TARGET_CAMPAIGN_ID == gallery.CAMPAIGN_ID
    assert len({pre.CAMPAIGN_ID, gallery.CAMPAIGN_ID, post.CAMPAIGN_ID}) == 3
    assert len({pre.CONTRACT_ID, gallery_report["contract_id"], post.CONTRACT_ID}) == 3
    assert (
        len({pre.ACTION_ID, gallery_report["actions"][0]["action_id"], post.ACTION_ID})
        == 3
    )
    assert (
        len(
            {
                pre.DESCRIPTOR_ID,
                gallery_report["actions"][0]["descriptor_id"],
                post.DESCRIPTOR_ID,
            }
        )
        == 3
    )
    assert len({pre.NVS_NAMESPACE, gallery.NVS_NAMESPACE, post.NVS_NAMESPACE}) == 3


def test_pre_white_is_one_factory_otp_action_without_runtime_payload() -> None:
    report = pre.build_report(verify_artifacts=True)
    contract = report["contract"]
    action = report["action"]
    assert action == {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR",
        "descriptor_id": pre.DESCRIPTOR_ID,
        "action_id": pre.ACTION_ID,
        "purpose": "pre_gallery_factory_otp_white_anchor",
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


def test_pre_white_artifacts_are_bound_to_the_build() -> None:
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


def test_pre_white_source_and_platform_are_isolated() -> None:
    main = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_main.cpp"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_program.inc"
    ).read_text(encoding="utf-8")
    identity = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_identity.inc"
    ).read_text(encoding="utf-8")
    platformio = (
        ROOT / "platformio.raw_p16_endpoint_gallery_pre_white_anchor_v1.ini"
    ).read_text(encoding="utf-8")
    assert "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_program.inc" in main
    assert "white_containment_program" not in main
    assert pre.CONTRACT_ID in identity
    assert pre.ACTION_ID in identity
    assert pre.DESCRIPTOR_ID in identity
    assert pre.TARGET_CAMPAIGN_ID in identity
    assert "MF1750_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR" in platformio
    assert "+<ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1_main.cpp>" in platformio
    assert "+<ec5_raw_p16_endpoint_gallery_v1_main.cpp>" not in platformio
    assert (
        "+<ec5_raw_p16_endpoint_gallery_v1_white_containment_main.cpp>"
        not in platformio
    )
    assert "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR" in program
    assert "pre_gallery_factory_otp_white_anchor" in program
    assert program.count("epdDisplayCompiledFactoryOtpWhiteRecovery();") == 1
    assert '\\"runtime_payload_present\\":false' in program


def test_pre_white_runner_describe_is_offline_and_has_unique_outputs() -> None:
    value = once.describe()
    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["purpose"] == "pre_gallery_factory_otp_white_anchor"
    assert value["target_campaign_id"] == gallery.CAMPAIGN_ID
    assert value["contract"]["factory_otp_white_only"] is True
    assert "pre_white_anchor" in str(once.base.DEFAULT_CLAIMS)
    assert "PRE_WHITE_ANCHOR" in str(once.base.DEFAULT_OUTPUT)
