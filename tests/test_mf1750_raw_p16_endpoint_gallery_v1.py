from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from urllib import request as urllib_request

import pytest

from tools import mf1750_raw_p16_endpoint_gallery_v1_once as once
from tools import mf1750_raw_p16_endpoint_gallery_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _pixel(frame: bytes, x: int, y: int) -> int:
    packed = frame[y * (pack.base.WIDTH // 2) + x // 2]
    return (packed >> 4) & 0x0F if x % 2 == 0 else packed & 0x0F


def test_fresh_single_action_contract_and_evidence_boundary() -> None:
    report = pack.build_report(verify_artifacts=True)
    contract = report["contract"]
    action = report["actions"][0]
    assert report["contract_id"] == pack.build_report()["contract_id"]
    assert contract["action_count"] == 1
    assert action["role"] == "RAW_P16_ACTIVE_ENDPOINT_GALLERY"
    assert action["palette_source"] == "L535_RUNTIME"
    assert contract["endpoint_observations"] == 16
    assert contract["unique_colours_claimed"] == 0
    assert contract["qualified_colours"] == 0
    assert contract["colour_family_labels"] == "UNQUALIFIED_OBSERVATION_ONLY"
    assert contract["classification_ambiguity"] == [
        "cyan_teal",
        "violet_magenta",
        "brown_orange",
    ]
    assert contract["runtime_code7_is_factory_white"] is False
    assert contract["automatic_chaining"] is False
    assert contract["retry"] is False
    assert contract["recovery"] is False


def test_each_controller_has_eight_pure_endpoint_cells_without_dither() -> None:
    frame = pack.atlas_frame()
    assert len(frame) == 307_200
    assert pack.controller_stream(frame, 0) == pack.controller_stream(frame, 1)
    assert pack.identity(frame)["sha256"] == (
        "46e86cf0ca6c537aaf694dda7eaf599a39992e0eac004858e413b6821bff94d9"
    )
    assert pack.base.histogram(frame) == [
        38_400,
        38_400,
        38_400,
        38_400,
        38_400,
        38_400,
        38_400,
        345_600,
    ]
    for controller in (0, 1):
        observed: list[int] = []
        for row, codes in enumerate(pack.CODE_ROWS):
            for column, code in enumerate(codes):
                x, y, width, height = pack.cell_bounds(row, column)
                x += controller * pack.base.CONTROLLER_WIDTH
                samples = {
                    _pixel(frame, x + 1, y + 1),
                    _pixel(frame, x + width // 2, y + height // 2),
                    _pixel(frame, x + width - 2, y + height - 2),
                }
                assert samples == {code}
                observed.append(code)
        assert observed == list(range(8))
    assert pack.build_report()["contract"]["geometry"]["spatial_dither"] is False


def test_mixed_r20_tuple_is_frozen_in_pack_and_isolated_driver() -> None:
    report = pack.build_report()
    profile = report["contract"]["profile"]
    driver = (ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_driver.inc").read_text(
        encoding="utf-8"
    )
    assert profile["id"] == "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
    assert profile["global_header"] == "active"
    assert profile["cs1_r20_prefix_sha256"] == pack.ACTIVE_R20_SHA256
    assert profile["cs2_r20_prefix_sha256"] == pack.COMMENTED_R20_SHA256
    assert profile["controller_r20_payloads_byte_identical"] is False
    assert "phUploadRuntimeLutToController(false, false)" in driver
    assert "phUploadRuntimeLutToController(true, true)" in driver
    assert "phUploadRuntimeLutToController(true, useCommentedGlobal)" not in driver


def test_factory_white_is_external_and_has_fresh_independent_containment() -> None:
    contract = pack.build_report()["contract"]
    assert contract["external_factory_otp_white_precondition"] == {
        "required": True,
        "clean_white_operator_or_camera_gate": True,
        "runtime_code7_accepted_as_white_anchor": False,
        "outside_campaign": True,
        "campaign_id": pack.PRE_WHITE_CAMPAIGN_ID,
        "contract_id": pack.PRE_WHITE_CONTRACT_ID,
        "factory_otp_white_only": True,
        "independent_nvs_namespace": pack.PRE_WHITE_NVS_NAMESPACE,
        "automatic": False,
    }
    assert contract["post_gallery_containment"] == {
        "outside_campaign": True,
        "campaign_id": pack.CONTAINMENT_CAMPAIGN_ID,
        "contract_id": pack.CONTAINMENT_CONTRACT_ID,
        "independent_nvs_namespace": pack.CONTAINMENT_NVS_NAMESPACE,
        "factory_otp_white_only": True,
        "automatic": False,
    }
    assert pack.CONTAINMENT_NVS_NAMESPACE != pack.NVS_NAMESPACE


def test_main_is_rebound_only_to_successor_prewhite_v1b() -> None:
    report = pack.build_report()
    precondition = report["contract"]["external_factory_otp_white_precondition"]
    assert pack.PRE_WHITE_CAMPAIGN_ID == (
        "EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B"
    )
    assert pack.PRE_WHITE_CONTRACT_ID == (
        "d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61"
    )
    assert pack.PRE_WHITE_NVS_NAMESPACE == "rp16gpw_v1b"
    assert precondition["campaign_id"] == pack.PRE_WHITE_CAMPAIGN_ID
    assert precondition["contract_id"] == pack.PRE_WHITE_CONTRACT_ID
    assert precondition["independent_nvs_namespace"] == pack.PRE_WHITE_NVS_NAMESPACE
    assert report["contract_id"] == (
        "f9b1f6b8052322bedc6b702cb895425e7c3dc5e2d1b7d9ae6e68edaa1ffc409d"
    )
    assert report["supersedes_offline_unflashed_main_artifact"] == (
        pack.SUPERSEDED_UNFLASHED_MAIN
    )
    assert pack.SUPERSEDED_UNFLASHED_MAIN["status"] == (
        "OFFLINE_SUPERSEDED_NEVER_FLASHED"
    )
    assert report["actions"][0]["action_id"] == (
        "9f5b84a12ac93c85898d2e843db6a5a4d174daa6ce0f18ffd8da974737f0a088"
    )
    assert report["contract"]["post_gallery_containment"]["campaign_id"] == (
        "EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1"
    )


def test_diagnostic_transport_remains_direct_no_proxy_and_no_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_handlers: list[object] = []

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"{}"

    def build_opener(*handlers: object) -> SimpleNamespace:
        captured_handlers.extend(handlers)
        return SimpleNamespace(open=lambda *_args, **_kwargs: Response())

    monkeypatch.setattr(once.urllib_request, "build_opener", build_opener)
    status, value = once._diagnostic_http_request(  # noqa: SLF001
        "http://192.168.1.7",
        "/api/ec5/raw-p16-endpoint-gallery-v1/version",
        method="GET",
        headers=None,
        timeout=1.0,
    )
    assert status == 200
    assert value == {}
    proxy_handlers = [
        handler
        for handler in captured_handlers
        if isinstance(handler, urllib_request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert any(isinstance(handler, once._NoRedirect) for handler in captured_handlers)
    assert (
        once._NoRedirect().redirect_request(
            None, None, 302, "found", {}, "http://192.168.1.8"
        )
        is None
    )
    assert once._diagnostic_origin("http://192.168.1.7:80") == ("http://192.168.1.7:80")
    with pytest.raises(once.base.runner.RecheckError):
        once._diagnostic_origin("http://device.local")


def test_runner_dry_validation_and_artifact_hashes_are_offline() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["cells_per_controller"] == 8
    assert value["endpoint_observations_total"] == 16
    assert value["unique_colours_claimed"] == 0
    assert value["controller_r20_payloads_byte_identical"] is False
    once._verify_local_artifacts()  # noqa: SLF001
    for name, size, digest in (
        ("firmware.bin", once.FIRMWARE_BYTES, once.FIRMWARE_SHA256),
        ("firmware.elf", once.ELF_BYTES, once.ELF_SHA256),
    ):
        payload = (once.BUILD_DIR / name).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_compiled_elf_contains_only_the_successor_prewhite_binding() -> None:
    payload = (once.BUILD_DIR / "firmware.elf").read_bytes()
    for value in (
        pack.build_report()["contract_id"],
        pack.PRE_WHITE_CAMPAIGN_ID,
        pack.PRE_WHITE_CONTRACT_ID,
        pack.PRE_WHITE_NVS_NAMESPACE,
    ):
        assert value.encode() in payload
    for superseded in (
        "c8ae63b7ab46fb2a22fc245fd8f4f2b810ea54ecf19cc71758dc3703aca2196c",
        "5d4d608449f078e8cedb2a781baccc9d0ee9105aefd980bb5ef1f4275f16185c",
    ):
        assert superseded.encode() not in payload


def test_runner_refuses_unconfirmed_external_prewhite_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    monkeypatch.setattr(once, "_verify_local_artifacts", lambda: None)
    with pytest.raises(once.base.runner.RecheckError, match="pre-white"):
        once.run_once(
            "http://192.168.1.7",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "action.json",
            requester=requester,
        )
    assert calls == []


def test_cpp_identity_config_and_platformio_are_isolated_and_bound() -> None:
    report = pack.build_report()
    identity = (ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_identity.inc").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_main_config.inc").read_text(
        encoding="utf-8"
    )
    platformio = (ROOT / "platformio.raw_p16_endpoint_gallery_v1.ini").read_text(
        encoding="utf-8"
    )
    assert report["contract_id"] in identity
    assert report["actions"][0]["descriptor_id"] in identity
    assert report["actions"][0]["action_id"] in identity
    assert 'controller_r20_payloads_byte_identical\\":false' in config
    assert pack.ACTIVE_R20_SHA256 in config
    assert pack.COMMENTED_R20_SHA256 in config
    assert "+<ec5_raw_p16_endpoint_gallery_v1_epd_driver.cpp>" in platformio
    assert "+<ec5_raw_p16_endpoint_gallery_v1_main.cpp>" in platformio
