from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_once as once
from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_single_position_balanced_action_and_external_white_boundary() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert len(report["actions"]) == 1
    assert contract["action_count"] == 1
    assert contract["factory_otp_white_ordinals"] == []
    assert contract["runtime_lut_ordinals"] == [1]
    assert contract["external_containment"] == {
        "outside_campaign": True,
        "factory_otp_white_before_required": True,
        "factory_otp_white_after_required": True,
        "off_white_photos_before_atlas_required": 3,
        "off_retained_atlas_photos_required": 3,
        "post_white_clean_visual_gate_required": True,
        "white_actions_in_campaign": 0,
    }
    assert contract["automatic_chaining"] is False
    assert contract["retry"] is False
    assert contract["recovery"] is False


def test_each_code_occupies_four_positions_and_both_dtm_streams_match() -> None:
    flat = [code for row in pack.CODE_ROWS for code in row]
    assert {code: flat.count(code) for code in range(8)} == {
        code: 4 for code in range(8)
    }
    frame = pack.atlas_frame()
    assert len(frame) == 307_200
    assert pack.controller_stream(frame, 0) == pack.controller_stream(frame, 1)
    row_bytes = pack.base.WIDTH // 2
    for controller in range(2):
        for row, codes in enumerate(pack.CODE_ROWS):
            for column, code in enumerate(codes):
                x, y, width, height = pack.cell_bounds(row, column)
                assert width == 52 and height == 100
                global_x = controller * 512 + x
                assert frame[y * row_bytes + global_x // 2] == (code << 4) | code


def test_active_tuple_and_payloads_are_controller_symmetric() -> None:
    report = pack.build_report()
    profile = report["contract"]["profile"]
    action = report["actions"][0]
    assert profile["cs1"] == profile["cs2"]
    assert profile["controller_payloads_byte_identical"] is True
    assert action["cs1_dtm"] == action["cs2_dtm"]
    assert action["frame"]["histogram"] == [
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        323_200,
    ]


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
            "http://192.168.1.11",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "action.json",
            requester=requester,
        )
    assert calls == []


def test_offline_dry_validate_and_artifact_binding() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["cells_per_controller"] == 32
    assert value["samples_per_code_per_controller"] == 12
    once._verify_local_artifacts()  # noqa: SLF001
    for name, size, digest in (
        ("firmware.bin", once.FIRMWARE_BYTES, once.FIRMWARE_SHA256),
        ("firmware.elf", once.ELF_BYTES, once.ELF_SHA256),
    ):
        payload = (once.BUILD_DIR / name).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_cpp_sources_bind_frozen_contract_action_and_geometry() -> None:
    report = pack.build_report()
    identity = (
        ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_main_config.inc"
    ).read_text(encoding="utf-8")
    driver = (ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_driver.inc").read_text(
        encoding="utf-8"
    )
    assert report["contract_id"] in identity
    assert report["actions"][0]["descriptor_id"] in config
    assert report["actions"][0]["action_id"] in config
    assert "ph::kCodeRows[row][column]" in driver
    assert "ph::kGridYByRow[row]" in driver
    assert "static constexpr uint8_t kActionCount = 1;" in (
        ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_main.cpp"
    ).read_text(encoding="utf-8")
