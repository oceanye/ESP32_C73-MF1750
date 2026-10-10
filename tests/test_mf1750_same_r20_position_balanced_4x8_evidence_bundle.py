from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_same_r20_position_balanced_4x8_evidence_bundle as bundle


def _relay_receipt(path: Path, *, state: str = "OFF") -> None:
    value = {
        "schema_version": 1,
        "kind": "mf17506-zave-relay-exact-bound-query-receipt",
        "rebind": {
            "path": "relay-rebind.json",
            "bytes": 1234,
            "sha256": "1" * 64,
            "rebind_id": "mf17506-relay-rebind-test",
            "canonical_sha256": "2" * 64,
        },
        "expected_identity": {
            "model": "ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z",
            "vid": "1A86",
            "pid": "7523",
            "serial_number": "ABSENT-CH340-NO-ISERIAL",
            "port": "COM14",
            "pnp_instance_id": "USB\\VID_1A86&PID_7523\\test",
            "usb_location": "Port_#0004.Hub_#0002",
        },
        "channel": 1,
        "commanded_state": state,
        "off_gate_passed": state == "OFF",
        "automatic_retry_performed": False,
        "contact_switch_performed": False,
        "on_authorized": False,
        "output_write_contract": "O_EXCL",
        "electrical_state_proven": False,
        "queried_at": f"2026-08-28T18:00:{path.stem[-2:] if path.stem[-2:].isdigit() else '00'}+08:00",
    }
    value["integrity"] = {
        "algorithm": "sha256",
        "canonical_sha256": bundle._sha(bundle._canonical(value)),  # noqa: SLF001
        "scope": "entire document excluding integrity",
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def test_exact_off_receipt_is_bound_but_not_electrical_proof(tmp_path: Path) -> None:
    path = tmp_path / "off.json"
    _relay_receipt(path)
    result = bundle._verify_relay_receipt(path, label="test")  # noqa: SLF001
    assert result["commanded_state"] == "OFF"
    assert result["electrical_state_proven"] is False


def test_on_receipt_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "on.json"
    _relay_receipt(path, state="ON")
    with pytest.raises(bundle.PositionBalancedBundleError, match="not an exact OFF"):
        bundle._verify_relay_receipt(path, label="test")  # noqa: SLF001


def test_three_off_receipts_require_same_binding_and_distinct_bytes(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"receipt-{index:02d}.json" for index in range(3)]
    for path in paths:
        _relay_receipt(path)
    receipts = [
        bundle._verify_relay_receipt(path, label="test")  # noqa: SLF001
        for path in paths
    ]

    bundle._validate_shared_relay_receipts(receipts)  # noqa: SLF001

    with pytest.raises(bundle.PositionBalancedBundleError, match="distinct"):
        bundle._validate_shared_relay_receipts(  # noqa: SLF001
            (receipts[0], receipts[1], receipts[1])
        )

    wrong_identity = dict(receipts[2])
    wrong_identity["expected_identity"] = {
        **receipts[2]["expected_identity"],
        "port": "COM99",
    }
    with pytest.raises(bundle.PositionBalancedBundleError, match="same relay"):
        bundle._validate_shared_relay_receipts(  # noqa: SLF001
            (receipts[0], receipts[1], wrong_identity)
        )


def test_post_white_off_receipt_is_between_action_and_capture() -> None:
    post_white = {"created_at": "2026-08-28T18:00:00+08:00"}
    clean = {
        "capture_started_at": "2026-08-28T18:00:20+08:00",
        "capture_completed_at": "2026-08-28T18:00:25+08:00",
    }

    bundle._validate_post_white_off_chronology(  # noqa: SLF001
        post_white=post_white,
        post_white_off={"queried_at": "2026-08-28T18:00:10+08:00"},
        clean=clean,
    )

    for invalid_time in (
        "2026-08-28T17:59:59+08:00",
        "2026-08-28T18:00:21+08:00",
    ):
        with pytest.raises(bundle.PositionBalancedBundleError, match="must follow"):
            bundle._validate_post_white_off_chronology(  # noqa: SLF001
                post_white=post_white,
                post_white_off={"queried_at": invalid_time},
                clean=clean,
            )


def test_bundle_output_is_o_excl(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    bundle.write_new(path, {"one": 1})
    with pytest.raises(bundle.PositionBalancedBundleError, match="already exists"):
        bundle.write_new(path, {"two": 2})


def _action_identity(tmp_path: Path) -> dict[str, Any]:
    action = tmp_path / "action.json"
    action.write_bytes(b"bound-action")
    return {
        "path": action.as_posix(),
        "file_sha256": bundle._sha(b"bound-action"),  # noqa: SLF001
        "canonical_integrity_sha256": "c" * 64,
        "campaign_id": "campaign",
        "test_id": "test",
        "contract_id": "3" * 64,
        "firmware_sha256": "4" * 64,
        "boot_nonce": "boot",
        "ordinal": 1,
        "action_id": "5" * 64,
        "descriptor_id": "6" * 64,
        "role": "ROLE",
        "frame_sha256": "7" * 64,
        "created_at": "2026-08-28T18:00:00+08:00",
    }


def _fake_capture_set(
    tmp_path: Path,
    *,
    action: dict[str, Any],
    binding: str = bundle.camera.BINDING_LOCKED_RETAINED,
    action_id: str | None = None,
) -> tuple[list[Path], list[Path], dict[Path, dict[str, Any]]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    captures: list[Path] = []
    photos: list[Path] = []
    roots: dict[Path, dict[str, Any]] = {}
    for index in range(3):
        capture = tmp_path / f"capture-{index}.json"
        photo = tmp_path / f"photo-{index}.jpg"
        capture.write_text("{}", encoding="utf-8")
        photo_payload = f"photo-{index}".encode()
        photo.write_bytes(photo_payload)
        instant = f"2026-08-28T18:01:0{index}+08:00"
        root: dict[str, Any] = {
            "kind": "mf1750-camera-capture-evidence",
            "capture_binding": binding,
            "output_write_contract": "O_EXCL",
            "capture_id": f"capture-{index}",
            "campaign_id": action["campaign_id"],
            "test_id": action["test_id"],
            "contract_id": action["contract_id"],
            "firmware_sha256": action["firmware_sha256"],
            "boot_nonce": action["boot_nonce"],
            "ordinal": action["ordinal"],
            "action_id": action_id or action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "role": action["role"],
            "frame_sha256": action["frame_sha256"],
            "action_result": {"file_sha256": action["file_sha256"]},
            "photo": {
                "path": photo.name,
                "sha256": bundle._sha(photo_payload),  # noqa: SLF001
            },
            "coverage": {
                "scope": bundle.camera.COVERAGE_FULL,
                "full_panel_visible": True,
                "full_panel_uncropped": True,
                "mount_id": "locked-mount",
            },
            "camera": {
                "camera_id": "camera",
                "instance_id": "instance",
                "index": 0,
                "backend": "DSHOW",
                "requested_settings": {"exposure": -3},
                "effective_settings_before_frame": {"exposure": -3},
                "effective_settings_after_frame": {"exposure": -3},
            },
            "capture_timing": {
                "started_at": instant,
                "frame_retrieved_at": instant,
                "completed_at": instant,
            },
        }
        captures.append(capture)
        photos.append(photo)
        roots[capture] = root
    return captures, photos, roots


def test_locked_retained_set_binds_action_and_prior_off_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _action_identity(tmp_path)
    captures, photos, roots = _fake_capture_set(tmp_path, action=action)
    monkeypatch.setattr(
        bundle.camera, "validate_capture_evidence", lambda path: roots[Path(path)]
    )
    receipt = {
        "queried_at": "2026-08-28T18:00:30+08:00",
        "canonical_sha256": "8" * 64,
    }

    records, setup, first, last = bundle._validate_capture_set(  # noqa: SLF001
        captures,
        photos,
        label="test",
        expected_action=action,
        off_receipt=receipt,
    )

    assert len(records) == 3
    assert all(
        item["capture_binding"] == bundle.camera.BINDING_LOCKED_RETAINED
        for item in records
    )
    assert setup["camera_instance_id"] == "instance"
    assert first < last


def test_live_binding_is_not_relaxed_for_off_capture_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _action_identity(tmp_path)
    captures, photos, roots = _fake_capture_set(
        tmp_path, action=action, binding=bundle.camera.BINDING_LIVE
    )
    monkeypatch.setattr(
        bundle.camera, "validate_capture_evidence", lambda path: roots[Path(path)]
    )
    with pytest.raises(bundle.PositionBalancedBundleError, match="capture 1 differs"):
        bundle._validate_capture_set(  # noqa: SLF001
            captures,
            photos,
            label="test",
            expected_action=action,
            off_receipt={
                "queried_at": "2026-08-28T18:00:30+08:00",
                "canonical_sha256": "8" * 64,
            },
        )


def test_capture_set_rejects_wrong_action_or_late_off_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _action_identity(tmp_path)
    captures, photos, roots = _fake_capture_set(
        tmp_path, action=action, action_id="9" * 64
    )
    monkeypatch.setattr(
        bundle.camera, "validate_capture_evidence", lambda path: roots[Path(path)]
    )
    with pytest.raises(bundle.PositionBalancedBundleError, match="action_id differs"):
        bundle._validate_capture_set(  # noqa: SLF001
            captures,
            photos,
            label="test",
            expected_action=action,
            off_receipt={
                "queried_at": "2026-08-28T18:00:30+08:00",
                "canonical_sha256": "8" * 64,
            },
        )

    captures, photos, roots = _fake_capture_set(tmp_path / "late", action=action)
    monkeypatch.setattr(
        bundle.camera, "validate_capture_evidence", lambda path: roots[Path(path)]
    )
    with pytest.raises(bundle.PositionBalancedBundleError, match="not after"):
        bundle._validate_capture_set(  # noqa: SLF001
            captures,
            photos,
            label="test",
            expected_action=action,
            off_receipt={
                "queried_at": "2026-08-28T18:02:00+08:00",
                "canonical_sha256": "8" * 64,
            },
        )
