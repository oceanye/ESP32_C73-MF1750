import json
import pytest
from tools import mf1750_lh1_camera_capture as m

ALT = r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
DEV = {
    "enumerator": "ffmpeg-dshow-alternative-name-v1",
    "friendly_name": "48MP USB Camera",
    "alternative_name": ALT,
    "pnp_instance_id": "USB\\VID_32E4&PID_4801&MI_00\\6&22675D4E&0&0000",
    "directshow_index": 0,
    "usb_vid": "32E4",
    "usb_pid": "4801",
}


def backend(i, s, w, q):
    assert i == 0
    return b"\xff\xd8\xff\xd9", {
        "backend": "DSHOW",
        "authenticated_device": DEV,
        "set_results": {"fourcc": True},
        "effective_settings_before_frame": {},
        "effective_settings_after_frame": {},
        "warmup_frames_completed": w,
        "read_failures": 0,
        "frame_retrieved_at": "2026-01-01T00:00:00Z",
        "frame_retrieved_at_utc": "2026-01-01T00:00:00Z",
    }


def fake_decode(_):
    return {"width": 1, "height": 1, "mode": "RGB", "format": "JPEG"}


def write_anchor(path):
    value = {"kind": "white-terminal", "action_id": "a", "firmware_sha256": "f"}
    value["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": m._canon(value),
    }
    path.write_text(json.dumps(value))


def test_capture_binds_anchor_and_unknown_coverage(tmp_path, monkeypatch):
    anchor = tmp_path / "white.json"
    write_anchor(anchor)
    monkeypatch.setattr(m, "_decode_jpeg", fake_decode)
    out = m.capture(
        anchor_path=anchor,
        photo_path=tmp_path / "x.jpg",
        sidecar_path=tmp_path / "x.json",
        run_id="LH1-V1",
        device_resolver=lambda: DEV,
        capture_backend=backend,
    )
    assert out["historical_action_anchor"]["file_sha256"]
    assert out["stage"] == "CURRENT_CAMERA_OBSERVATION"
    assert out["coverage"]["full_panel_validity"] == "UNKNOWN"
    assert (
        out["camera"]["usb_vid"] == "32E4" and out["camera"]["raw_supported"] is False
    )
    assert json.loads((tmp_path / "x.json").read_text())["integrity"][
        "sha256"
    ] == m._canon(out)


def test_rejects_non_target_camera(tmp_path, monkeypatch):
    anchor = tmp_path / "a.json"
    write_anchor(anchor)
    bad = dict(DEV, usb_vid="1BCF", usb_pid="0B15")
    with pytest.raises(Exception):
        m.capture(
            anchor_path=anchor,
            photo_path=tmp_path / "p",
            sidecar_path=tmp_path / "s",
            run_id="r",
            camera_id="binocular",
            device_resolver=lambda: bad,
            capture_backend=backend,
        )


def test_rejects_existing_output(tmp_path):
    a = tmp_path / "a.json"
    write_anchor(a)
    p = tmp_path / "p"
    p.write_bytes(b"keep")
    with pytest.raises(Exception):
        m.capture(
            anchor_path=a,
            photo_path=p,
            sidecar_path=tmp_path / "s",
            run_id="r",
            device_resolver=lambda: DEV,
            capture_backend=backend,
        )
    assert p.read_bytes() == b"keep"


def test_failed_capture_preserves_returned_image_and_failure(tmp_path, monkeypatch):
    a = tmp_path / "a.json"
    write_anchor(a)

    def changed_backend(*args):
        payload, record = backend(*args)
        record["backend"] = "FOREIGN"
        return payload, record

    p, s = tmp_path / "p.jpg", tmp_path / "s.json"
    with pytest.raises(m.CameraCaptureEvidenceError, match="not DirectShow"):
        m.capture(
            anchor_path=a,
            photo_path=p,
            sidecar_path=s,
            run_id="r",
            device_resolver=lambda: DEV,
            capture_backend=changed_backend,
        )
    assert p.read_bytes() == b"\xff\xd8\xff\xd9"
    assert json.loads(s.read_text())["usable_optical_evidence"] is False


def test_tampered_anchor_rejected_before_device_resolver(tmp_path):
    a = tmp_path / "a.json"
    write_anchor(a)
    a.write_text(a.read_text().replace('"action_id": "a"', '"action_id": "b"'))
    calls = []
    with pytest.raises(m.CameraCaptureEvidenceError, match="integrity"):
        m.capture(
            anchor_path=a,
            photo_path=tmp_path / "p",
            sidecar_path=tmp_path / "s",
            run_id="r",
            device_resolver=lambda: calls.append(1),
        )
    assert calls == []
