from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_same_r20_parity_v1_once as once
from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_four_independent_ordinals_are_frozen_in_required_order() -> None:
    report = pack.build_report()
    assert [item["ordinal"] for item in report["actions"]] == [1, 2, 3, 4]
    assert [item["role"] for item in report["actions"]] == list(pack.ROLES)
    assert [item["global_header"] for item in report["actions"]] == [
        "active",
        None,
        "commented",
        None,
    ]
    assert report["contract"]["one_visible_refresh_per_action"] is True
    assert report["contract"]["automatic_chaining"] is False
    assert report["contract"]["retry"] is False
    assert report["contract"]["recovery"] is False


def test_2x4_code_layout_is_identical_on_both_controllers() -> None:
    frame = pack.atlas_frame()
    assert len(frame) == 307_200
    assert pack.controller_stream(frame, 0) == pack.controller_stream(frame, 1)
    row_bytes = pack.base.WIDTH // 2
    for code in range(8):
        row, column = divmod(code, 4)
        x, y, width, height = pack._cell_bounds(row, column)  # noqa: SLF001
        assert (x, y, width, height) == (
            40 + column * 116,
            120 + row * 160,
            96,
            120,
        )
        for controller in (0, 1):
            global_x = controller * 512 + x
            sample = frame[y * row_bytes + global_x // 2]
            assert sample == (code << 4) | code


@pytest.mark.parametrize("name", ("active", "commented"))
def test_each_runtime_profile_binds_same_r20_and_r21_to_both_sides(name: str) -> None:
    profile = pack.profile(name)
    assert profile["cs1"] == profile["cs2"]
    assert profile["controller_payloads_byte_identical"] is True
    assert profile["cs1"]["r20_prefix_bytes"] == 535
    assert profile["cs1"]["r21_bytes"] == 704
    assert profile["cs1"]["r21_sha256"] == pack.base.R21_SHA256
    for key in (
        "global_header_sha256",
        "runtime_psr_sha256",
        "power_payload_sha256",
        "pll_payload_sha256",
        "tres_sha256",
        "hidden_enable_sha256",
        "global_tuple_id",
    ):
        assert len(profile[key]) == 64


def test_active_and_commented_are_distinct_complete_tuples() -> None:
    active = pack.profile("active")
    commented = pack.profile("commented")
    assert active["global_tuple_id"] != commented["global_tuple_id"]
    assert active["global_header_sha256"] != commented["global_header_sha256"]
    assert active["power_payload_sha256"] != commented["power_payload_sha256"]
    assert active["pll_payload_sha256"] != commented["pll_payload_sha256"]
    assert active["cs1"]["r20_prefix_sha256"] != commented["cs1"]["r20_prefix_sha256"]
    assert active["cs1"]["r21_sha256"] == commented["cs1"]["r21_sha256"]


def test_aa_and_cc_use_same_dtm_but_different_symmetric_waveforms() -> None:
    first, _, third, _ = pack.build_report()["actions"]
    assert first["frame"] == third["frame"]
    assert first["cs1_dtm"] == first["cs2_dtm"]
    assert third["cs1_dtm"] == third["cs2_dtm"]
    assert first["cs1_dtm"] == third["cs1_dtm"]
    assert first["global_tuple_id"] != third["global_tuple_id"]
    assert first["waveform_binding"]["cs1"] == first["waveform_binding"]["cs2"]
    assert third["waveform_binding"]["cs1"] == third["waveform_binding"]["cs2"]


def test_white_actions_are_factory_otp_0x11_and_not_runtime_payloads() -> None:
    actions = pack.build_report()["actions"]
    for item in (actions[1], actions[3]):
        assert item["palette_source"] == "FACTORY_OTP"
        assert item["global_header"] is None
        assert item["waveform_binding"] is None
        assert item["frame"]["sha256"] == (
            "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
        )
        assert item["frame"]["histogram"] == [0, 614_400, 0, 0, 0, 0, 0, 0]


def test_external_v3_white_anchor_is_exact_and_not_a_resume() -> None:
    binding = pack.build_report()["contract"]["external_white_anchor"]
    assert binding == pack.EXTERNAL_WHITE_ANCHOR
    assert binding["required_outcome"] == "complete_pass"
    assert binding["required_clean_white_visual_gate"] is True
    assert binding["resume_source_campaign"] is False
    assert binding["contract_id"] == (
        "1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227"
    )


def test_runner_refuses_ordinal1_before_network_when_v3_anchor_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    monkeypatch.setattr(once, "_verify_local_artifacts", lambda: None)
    binding = dict(pack.EXTERNAL_WHITE_ANCHOR)
    binding["evidence_path"] = str(tmp_path / "missing-anchor.json")
    monkeypatch.setattr(pack, "EXTERNAL_WHITE_ANCHOR", binding)
    with pytest.raises(
        once.base.runner.RecheckError, match="anchor evidence is missing"
    ):
        once.run_once(
            "http://192.168.1.7",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "action.json",
            requester=requester,
        )
    assert calls == []


def test_offline_pack_and_dry_validate_have_zero_hardware_effects() -> None:
    report = pack.build_report()
    for key in (
        "hardware_accessed",
        "device_network_accessed",
        "serial_or_com_accessed",
        "relay_accessed",
        "firmware_flashed",
        "display_refreshed",
    ):
        assert report[key] is False
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["controller_dtm_byte_identical"] is True
    assert value["automatic_chaining"] is False
    assert value["retry"] is False
    assert value["recovery"] is False


def test_compiled_artifacts_are_bound_by_size_and_sha256() -> None:
    once._verify_local_artifacts()  # noqa: SLF001
    for name, size, digest in (
        ("firmware.bin", once.FIRMWARE_BYTES, once.FIRMWARE_SHA256),
        ("firmware.elf", once.ELF_BYTES, once.ELF_SHA256),
    ):
        data = (once.BUILD_DIR / name).read_bytes()
        assert len(data) == size
        assert hashlib.sha256(data).hexdigest() == digest


def test_cpp_identity_and_main_bind_python_contract_and_actions() -> None:
    report = pack.build_report()
    identity = (ROOT / "src/ec5_runtime_lut_same_r20_parity_v1_identity.inc").read_text(
        encoding="utf-8"
    )
    config = (
        ROOT / "src/ec5_runtime_lut_same_r20_parity_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    main = (ROOT / "src/ec5_runtime_lut_same_r20_parity_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    assert report["contract_id"] in identity
    for item in report["actions"]:
        assert item["descriptor_id"] in config
        assert item["action_id"] in config
    for name in ("active", "commented"):
        profile = report["contract"]["profiles"][name]
        for key in (
            "global_header_sha256",
            "power_payload_sha256",
            "pll_payload_sha256",
            "global_tuple_id",
        ):
            assert profile[key] in main
        assert profile["cs1"]["r20_prefix_sha256"] in main
        assert profile["cs1"]["r21_sha256"] in main


def test_driver_uploads_one_selected_profile_to_both_controllers() -> None:
    source = (ROOT / "src/ec5_runtime_lut_same_r20_parity_v1_driver.inc").read_text(
        encoding="utf-8"
    )
    assert "phUploadRuntimeLutToController(false, useCommentedGlobal)" in source
    assert "phUploadRuntimeLutToController(true, useCommentedGlobal)" in source
    assert "if (useCommentedProfile)" in source
    assert (
        "if (secondController)"
        not in source[
            source.index("bool phUploadRuntimeLutToController") : source.index(
                "void phApplyWindow"
            )
        ]
    )
    assert "row * ph::kGridColumns + column" in source


def test_runner_paths_and_outputs_are_isolated_and_fixed() -> None:
    assert once.base.runner.DEFAULT_CLAIMS.name == ".mf1750_same_r20_parity_v1_claims"
    assert once.base.runner.DEFAULT_OUTPUT.name == "MF1750_SAME_R20_PARITY_20260828_V1"
    assert once.ACTION_OUTPUT_NAMES == {
        1: "action-01-active-active-atlas.json",
        2: "action-02-factory-otp-white-after-aa.json",
        3: "action-03-commented-commented-atlas.json",
        4: "action-04-factory-otp-white-after-cc.json",
    }
    assert once.pack.NVS_NAMESPACE == "sr20p_v1"
    assert once.pack.NVS_KEY == "cursor_srp1"
    assert once.pack.NVS_BOOT_KEY == "boot_srp1"
    assert all(
        path.startswith(pack.BASE_ROUTE) for path in once.base.runner.ENDPOINTS.values()
    )


def test_firmware_source_has_four_actions_and_no_autochain_or_retry() -> None:
    source = (ROOT / "src/ec5_runtime_lut_same_r20_parity_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    assert "static constexpr uint8_t kActionCount = 4;" in source
    assert '\\"automatic_chaining\\":false' in source
    assert '\\"retry\\":false' in source
    assert '\\"recovery\\":false' in source
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery" in source
    assert "epdDisplayCompiledChromaGrid" in source
