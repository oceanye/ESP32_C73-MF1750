from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np
import pytest

from tools import mf1750_factory_white_repeat_noise_report as noise


DIMENSIONS = (1600, 600)


def _settings() -> tuple[dict[str, object], dict[str, object]]:
    requested: dict[str, object] = {
        "fourcc": "MJPG",
        "frame_width": DIMENSIONS[0],
        "frame_height": DIMENSIONS[1],
        "fps": 30.0,
        "autofocus": 0.0,
        "focus": 12.0,
        "auto_exposure": 0.25,
        "exposure": -6.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
        "brightness": None,
        "contrast": None,
        "saturation": None,
        "hue": None,
    }
    effective: dict[str, object] = {
        "fourcc": "MJPG",
        "frame_width": DIMENSIONS[0],
        "frame_height": DIMENSIONS[1],
        "fps": 30.0,
        "autofocus": 0,
        "focus": 12,
        "auto_exposure": 0.25,
        "exposure": -6,
        "auto_white_balance": 0,
        "white_balance_temperature": 4600,
        "brightness": 0,
        "contrast": 32,
        "saturation": 64,
        "hue": 0,
    }
    return requested, effective


def _root(index: int, photo_name: str, photo_sha256: str) -> dict[str, object]:
    requested, effective = _settings()
    return {
        "capture_binding": "live_synchronized",
        "campaign_id": "FACTORY_WHITE_CAMPAIGN",
        "test_id": "FACTORY-WHITE-TEST",
        "contract_id": "1" * 64,
        "firmware_sha256": "2" * 64,
        "boot_nonce": "boot-one",
        "ordinal": 1,
        "action_id": "3" * 64,
        "descriptor_id": "4" * 64,
        "role": "FACTORY_OTP_WHITE_BASELINE",
        "frame_sha256": "5" * 64,
        "capture_id": f"capture-{index}",
        "captured_at": f"2026-08-28T10:00:0{index}+08:00",
        "action_result": {
            "file_sha256": "6" * 64,
            "visible_refreshes": 1,
        },
        "camera": {
            "camera_id": "mf1750-camera",
            "instance_id": "usb-instance-one",
            "index": 0,
            "backend": "DSHOW",
            "requested_settings": requested,
            "effective_settings_before_frame": effective,
            "effective_settings_after_frame": deepcopy(effective),
        },
        "photo": {
            "path": photo_name,
            "sha256": photo_sha256,
            "width": DIMENSIONS[0],
            "height": DIMENSIONS[1],
        },
        "coverage": {
            "scope": "full_panel",
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "locked-mount-one",
        },
        "integrity": {"sha256": f"{index:064x}"},
    }


def _install_valid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    values: tuple[int, ...] = (220, 222, 224),
) -> tuple[Path, list[Path], dict[Path, dict[str, object]]]:
    reference = tmp_path / "reference.json"
    reference.write_bytes(b"reference-grid")
    roots: dict[Path, dict[str, object]] = {}
    images: dict[Path, np.ndarray] = {}
    sidecars: list[Path] = []
    for index, value in enumerate(values, 1):
        photo = tmp_path / f"white-{index}.jpg"
        payload = f"photo-{index}-{value}".encode()
        photo.write_bytes(payload)
        sidecar = tmp_path / f"white-{index}.capture.json"
        sidecar.write_text(f'{{"sidecar":{index}}}\n', encoding="utf-8")
        roots[sidecar] = _root(index, photo.name, hashlib.sha256(payload).hexdigest())
        images[photo] = np.full(
            (DIMENSIONS[1], DIMENSIONS[0], 3), value, dtype=np.uint8
        )
        sidecars.append(sidecar)

    monkeypatch.setattr(
        noise.camera,
        "validate_capture_evidence",
        lambda path: deepcopy(roots[Path(path)]),
    )
    monkeypatch.setattr(
        noise.static_gate,
        "_load_reference",
        lambda _path: (
            b"reference-grid",
            {"integrity": {"sha256": "a" * 64}},
            np.eye(3, dtype=np.float64),
            DIMENSIONS,
        ),
    )
    monkeypatch.setattr(noise.common, "_verify_integrity", lambda _root: "a" * 64)

    def decode(path: Path, dimensions: tuple[int, int], *, label: str):
        assert dimensions == DIMENSIONS
        assert label
        resolved = Path(path)
        return resolved.read_bytes(), images[resolved]

    monkeypatch.setattr(noise.static_gate, "_decode", decode)
    monkeypatch.setattr(noise.static_gate, "_rectify", lambda image, _h: image)
    return reference, sidecars, roots


def test_build_report_seals_three_capture_60_patch_pairwise_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, _ = _install_valid_inputs(tmp_path, monkeypatch)

    report = noise.build_report(reference, sidecars)

    assert report["kind"] == noise.KIND
    assert report["layout"]["patch_count"] == 60
    assert report["capture_contract"]["capture_count"] == 3
    assert report["capture_contract"]["pair_count"] == 3
    assert len(report["lab_samples"]) == 180
    assert len(report["photo_pair_distributions"]) == 3
    assert len(report["patch_distributions"]) == 60
    distribution = report["summary"]["distribution_de76"]
    assert distribution["sample_count"] == 180
    assert report["summary"]["repeat_noise_p95_de76"] == distribution["p95"]
    assert distribution["p95"] > 0
    unsigned = deepcopy(report)
    integrity = unsigned.pop("integrity")
    assert integrity == {
        "algorithm": noise.INTEGRITY_ALGORITHM,
        "sha256": noise._sha256_bytes(noise._canonical_json(unsigned)),
    }
    assert (
        report["evidence_boundaries"][
            "device_camera_network_serial_relay_io_performed_by_reporter"
        ]
        is False
    )
    normalization = report["capture_contract"]["locked_camera_and_mount"][
        "manual_mode_readback_normalization"
    ]
    assert normalization["policy"] == "DSHOW_DRIVER_SPECIFIC_RAW_ENUM_V1"
    assert normalization["driver_specific_normalization_used"] is False


def test_accepts_only_known_dshow_manual_raw_readback_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    for root in roots.values():
        before = root["camera"]["effective_settings_before_frame"]
        after = root["camera"]["effective_settings_after_frame"]
        before["autofocus"] = 2
        before["auto_exposure"] = -1
        after["autofocus"] = 2
        after["auto_exposure"] = -1

    report = noise.build_report(reference, sidecars)

    normalization = report["capture_contract"]["locked_camera_and_mount"][
        "manual_mode_readback_normalization"
    ]
    assert normalization == {
        "policy": "DSHOW_DRIVER_SPECIFIC_RAW_ENUM_V1",
        "backend": "DSHOW",
        "effective_raw_values": {
            "autofocus": 2.0,
            "auto_exposure": -1.0,
            "auto_white_balance": 0.0,
        },
        "accepted_raw_values": {
            "autofocus": [0.0, 2.0],
            "auto_exposure": [-1.0, 0.25],
            "auto_white_balance": [0.0],
        },
        "normalized_manual_state": {
            "autofocus": True,
            "auto_exposure": True,
            "auto_white_balance": True,
        },
        "driver_specific_normalization_used": True,
    }


def test_rejects_dshow_raw_values_for_unknown_backend_or_wrong_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    for root in roots.values():
        root["camera"]["backend"] = "MSMF"
        root["camera"]["effective_settings_before_frame"]["autofocus"] = 2
        root["camera"]["effective_settings_after_frame"]["autofocus"] = 2
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="not an accepted MSMF manual-mode encoding",
    ):
        noise.build_report(reference, sidecars)

    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    for root in roots.values():
        root["camera"]["requested_settings"]["auto_exposure"] = 0.0
        root["camera"]["effective_settings_before_frame"]["auto_exposure"] = -1
        root["camera"]["effective_settings_after_frame"]["auto_exposure"] = -1
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="auto_exposure must equal the locked manual request 0.25",
    ):
        noise.build_report(reference, sidecars)


def test_rejects_unknown_dshow_raw_value_and_automatic_mode_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    for root in roots.values():
        root["camera"]["effective_settings_before_frame"]["auto_exposure"] = 0.75
        root["camera"]["effective_settings_after_frame"]["auto_exposure"] = 0.75
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="not an accepted DSHOW manual-mode encoding",
    ):
        noise.build_report(reference, sidecars)

    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    for root in roots.values():
        root["camera"]["requested_settings"]["autofocus"] = 1.0
        root["camera"]["effective_settings_before_frame"]["autofocus"] = 2
        root["camera"]["effective_settings_after_frame"]["autofocus"] = 2
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="autofocus must explicitly request manual focus",
    ):
        noise.build_report(reference, sidecars)


def test_requires_at_least_three_distinct_sidecars(tmp_path: Path) -> None:
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="at least 3 capture sidecars",
    ):
        noise.build_report(tmp_path / "reference.json", [])
    path = tmp_path / "same.capture.json"
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="sidecar paths must be distinct",
    ):
        noise.build_report(tmp_path / "reference.json", [path, path, path])


def test_rejects_non_live_or_partial_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    roots[sidecars[1]]["capture_binding"] = "retrospective_unproven"

    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="live_synchronized full-panel",
    ):
        noise.build_report(reference, sidecars)


def test_rejects_unlocked_or_drifting_camera_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    roots[sidecars[1]]["camera"]["requested_settings"]["autofocus"] = 1.0

    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="autofocus must explicitly request manual focus",
    ):
        noise.build_report(reference, sidecars)

    roots[sidecars[1]] = _root(
        2,
        "white-2.jpg",
        hashlib.sha256((tmp_path / "white-2.jpg").read_bytes()).hexdigest(),
    )
    roots[sidecars[1]]["camera"]["effective_settings_after_frame"]["focus"] = 13
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="effective settings changed",
    ):
        noise.build_report(reference, sidecars)


def test_rejects_different_action_or_duplicate_photo_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, sidecars, roots = _install_valid_inputs(tmp_path, monkeypatch)
    roots[sidecars[2]]["action_id"] = "7" * 64
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="same factory-white action",
    ):
        noise.build_report(reference, sidecars)

    roots[sidecars[2]] = _root(
        3,
        "white-3.jpg",
        hashlib.sha256((tmp_path / "white-3.jpg").read_bytes()).hexdigest(),
    )
    duplicate = (tmp_path / "white-1.jpg").read_bytes()
    (tmp_path / "white-3.jpg").write_bytes(duplicate)
    roots[sidecars[2]]["photo"]["sha256"] = hashlib.sha256(duplicate).hexdigest()
    with pytest.raises(
        noise.FactoryWhiteRepeatNoiseReportError,
        match="distinct bytes",
    ):
        noise.build_report(reference, sidecars)


def test_main_uses_exclusive_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = {
        "schema_version": 1,
        "kind": noise.KIND,
        "integrity": {
            "algorithm": noise.INTEGRITY_ALGORITHM,
            "sha256": "0" * 64,
        },
    }
    monkeypatch.setattr(noise, "build_report", lambda _reference, _sidecars: report)
    output = tmp_path / "baseline.json"
    arguments = [
        "--reference-grid-analysis",
        str(tmp_path / "reference.json"),
        "--capture-sidecar",
        str(tmp_path / "one.json"),
        "--capture-sidecar",
        str(tmp_path / "two.json"),
        "--capture-sidecar",
        str(tmp_path / "three.json"),
        "--output",
        str(output),
    ]

    assert noise.main(arguments) == 0
    assert output.is_file()
    assert noise.main(arguments) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
