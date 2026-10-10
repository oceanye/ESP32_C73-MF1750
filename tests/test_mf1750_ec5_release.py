from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_ec5_compiled_identity as compiled
from tools import mf1750_ec5_release as release


REPO_ROOT = Path(__file__).resolve().parents[1]


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _fixture_elf(
    candidate: int,
    *,
    frame_override: bytes | None = None,
    dtm_override: bytes | None = None,
) -> bytes:
    expected = compiled.generated_identity(candidate)
    frame = frame_override if frame_override is not None else expected["frame_sha256"]
    dtm = dtm_override if dtm_override is not None else expected["dtm_sha256"]
    assert isinstance(frame, bytes) and isinstance(dtm, bytes)

    section_names = b"\0.shstrtab\0.strtab\0.symtab\0.flash.rodata\0"
    section_name_offsets = {
        name: section_names.index(name.encode())
        for name in (".shstrtab", ".strtab", ".symtab", ".flash.rodata")
    }
    symbol_names = (
        b"\0" + compiled.FRAME_SYMBOL.encode() + b"\0"
        + compiled.DTM_SYMBOL.encode() + b"\0"
    )
    frame_name = symbol_names.index(compiled.FRAME_SYMBOL.encode())
    dtm_name = symbol_names.index(compiled.DTM_SYMBOL.encode())
    rodata = frame + dtm
    rodata_address = 0x3C000000
    local_object = (compiled.STB_LOCAL << 4) | compiled.STT_OBJECT
    symbols = b"".join(
        (
            compiled.SYMBOL_ENTRY.pack(0, 0, 0, 0, 0, 0),
            compiled.SYMBOL_ENTRY.pack(
                frame_name, rodata_address, len(frame), local_object, 0, 4
            ),
            compiled.SYMBOL_ENTRY.pack(
                dtm_name,
                rodata_address + len(frame),
                len(dtm),
                local_object,
                0,
                4,
            ),
        )
    )

    image = bytearray(b"\0" * compiled.ELF_HEADER.size)
    offsets: dict[str, int] = {}
    for name, payload in (
        (".shstrtab", section_names),
        (".strtab", symbol_names),
        (".symtab", symbols),
        (".flash.rodata", rodata),
    ):
        image.extend(b"\0" * (_align(len(image)) - len(image)))
        offsets[name] = len(image)
        image.extend(payload)
    image.extend(b"\0" * (_align(len(image)) - len(image)))
    section_offset = len(image)
    image.extend(compiled.SECTION_HEADER.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    image.extend(
        compiled.SECTION_HEADER.pack(
            section_name_offsets[".shstrtab"],
            compiled.SHT_STRTAB,
            0,
            0,
            offsets[".shstrtab"],
            len(section_names),
            0,
            0,
            1,
            0,
        )
    )
    image.extend(
        compiled.SECTION_HEADER.pack(
            section_name_offsets[".strtab"],
            compiled.SHT_STRTAB,
            0,
            0,
            offsets[".strtab"],
            len(symbol_names),
            0,
            0,
            1,
            0,
        )
    )
    image.extend(
        compiled.SECTION_HEADER.pack(
            section_name_offsets[".symtab"],
            compiled.SHT_SYMTAB,
            0,
            0,
            offsets[".symtab"],
            len(symbols),
            2,
            3,
            4,
            compiled.SYMBOL_ENTRY.size,
        )
    )
    image.extend(
        compiled.SECTION_HEADER.pack(
            section_name_offsets[".flash.rodata"],
            1,
            2,
            rodata_address,
            offsets[".flash.rodata"],
            len(rodata),
            0,
            0,
            4,
            0,
        )
    )
    ident = (
        compiled.ELF_MAGIC
        + bytes((compiled.ELFCLASS32, compiled.ELFDATA2LSB, 1))
        + b"\0" * 9
    )
    image[: compiled.ELF_HEADER.size] = compiled.ELF_HEADER.pack(
        ident,
        2,
        compiled.EM_XTENSA,
        1,
        0,
        0,
        section_offset,
        0,
        compiled.ELF_HEADER.size,
        0,
        0,
        compiled.SECTION_HEADER.size,
        5,
        1,
    )
    return bytes(image)


def _firmware(candidate_id: str) -> bytes:
    variant = release.VARIANTS[candidate_id]
    nvs = variant["nvs_contract"]
    tokens = (
        variant["build_tag"],
        variant["test_id"],
        variant["action_id"],
        variant["frame_sha256"],
        variant["dtm_sha256"],
        variant["identity_revision"],
        variant["device_api_version"],
        nvs["legacy"]["namespace"],
        nvs["legacy"]["key"],
        nvs["active"]["namespace"],
        nvs["active"]["key"],
    )
    return b"ESP32-FIXTURE\0" + b"\0".join(
        str(token).encode("ascii") for token in tokens
    ) + b"\0END"


def _inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path, Path]:
    panel = tmp_path / "panel.json"
    panel.write_text(
        json.dumps(
            {
                "board_id": "ESP32-C73",
                "model": "MF1750-C73",
                "pcb_revision": "rev-a1",
                "serial": "MF750M009T6420/1582643AGY44",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    u04 = tmp_path / "u04.bin"
    u07 = tmp_path / "u07.bin"
    u04_elf = tmp_path / "u04.elf"
    u07_elf = tmp_path / "u07.elf"
    u04.write_bytes(_firmware("U04"))
    u07.write_bytes(_firmware("U07"))
    u04_elf.write_bytes(_fixture_elf(4))
    u07_elf.write_bytes(_fixture_elf(7))
    monkeypatch.setattr(
        release,
        "_source_snapshot",
        lambda: {
            "git_head": "a" * 40,
            "git_dirty": True,
            "git_status_sha256": release.sha256(b" M source\n"),
            "git_status_line_count": 1,
            "relevant_sources": [
                {
                    "path": path,
                    "bytes": (release.REPO_ROOT / path).stat().st_size,
                    "sha256": release.sha256(
                        (release.REPO_ROOT / path).read_bytes()
                    ),
                }
                for path in release.SOURCE_PATHS
            ],
        },
    )
    return panel, u04, u07, u04_elf, u07_elf


def _build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], dict[str, dict[str, bytes]]]:
    panel, u04, u07, u04_elf, u07_elf = _inputs(tmp_path, monkeypatch)
    return release.build_release(
        panel_file=panel,
        u04_binary=u04,
        u07_binary=u07,
        u04_elf=u04_elf,
        u07_elf=u07_elf,
        created_at="2026-08-09T10:00:00+08:00",
    )


def _publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    manifest, artifacts = _build(tmp_path, monkeypatch)
    bundle = tmp_path / "bundle"
    release.publish_release(bundle, manifest, artifacts)
    return bundle


def _reseal(path: Path, value: dict[str, object]) -> None:
    unsigned = copy.deepcopy(value)
    unsigned.pop("integrity")
    value["integrity"] = {
        "canonical_sha256": release.sha256(unsigned),
        "scope": release.HASH_SCOPE,
    }
    path.write_bytes(release.canonical_json_bytes(value))


def test_build_binds_v2_identities_incident_and_compiled_elf_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    manifest = release.validate_release(bundle)

    assert manifest["schema_version"] == 2
    assert manifest["identity_revision"] == "corrected-v2"
    assert manifest["source_snapshot"]["git_dirty"] is True
    assert manifest["incident_lineage"] == release.INCIDENT_LINEAGE
    assert manifest["incident_lineage"] == {
        "v1_release_canonical_sha256": (
            "adedbbdfe7ccacb3705149282689db46407261e834298c2b5c77dd285eb6d7dd"
        ),
        "v1_u04_action_id": (
            "bf2fcbcb29a35cf0a7915c67b48468aca26f7a35aef20e9ff68c9d60a37d0df5"
        ),
        "v1_u04_result_file_sha256": (
            "e1bf5659d6357dd5055fb7de8b447a9e23a07de9808a07a8e35687394ffdc954"
        ),
        "v1_u04_post_stop_readback_file_sha256": (
            "69e8009f8f63785d37e3ee82b0567f46a2ed9e503b8f5217bc6124eb4a8928e0"
        ),
        "v1_u04_forensic_supplement_canonical_sha256": (
            "30c27f69d952766bc158000267dac187eab5fa69e6b32b932f392f4a2ddc9b50"
        ),
        "v1_u04_forensic_supplement_file_sha256": (
            "660eac73d4d4b45c4ff98620106abceb89baa58e6d518d7fde410c140a0ec73e"
        ),
        "v1_host_claim_sha256": (
            "66b3d2c3ac0e01570346239bab9c759635fbc0125bc5a88a05bc90eacc37ce37"
        ),
        "v1_quarantine_marker_file_sha256": (
            "1ee694a037aae19e0bd7c8efda48dfc768c85131743472cf662b84039a7d0c3d"
        ),
        "display_sequence_started": False,
    }
    assert manifest["incident_lineage"]["display_sequence_started"] is False
    assert manifest["compiled_identity_report"]["valid"] is True
    assert manifest["compiled_identity_report"]["offline"] is True
    assert manifest["compiled_identity_report"]["device_io_performed"] is False
    assert set(manifest["variants"]) == {"U04", "U07"}
    for candidate in ("U04", "U07"):
        variant = manifest["variants"][candidate]
        assert variant["identity_revision"] == "corrected-v2"
        assert variant["device_api_version"] == "MF1750_EC5_DEVICE_V3"
        assert variant["top_schema_version"] == 3
        assert variant["driver_evidence_schema_version"] == 2
        assert release.identity.derive_action_id(
            variant["action_identity_preimage"]
        ) == variant["action_id"]
        assert variant["nvs_contract"]["legacy"]["read_only"] is True
        assert variant["nvs_contract"]["active"]["expected_present"] is False
        assert (bundle / variant["firmware"]["file"]).is_file()
        assert (bundle / variant["elf"]["file"]).is_file()
        report = manifest["compiled_identity_report"]["variants"][candidate]
        assert report["elf_sha256"] == variant["elf"]["sha256"]
        assert report["elf_bytes"] == variant["elf"]["bytes"]
    assert manifest["device_contract"]["arm_required"] is True
    assert manifest["device_contract"]["retry_allowed"] is False
    assert manifest["device_contract"] == {
        "device_api_version": "MF1750_EC5_DEVICE_V3",
        "top_schema_version": 3,
        "driver_evidence_schema_version": 2,
        "identity_revision": "corrected-v2",
        "read_routes": [
            "/api/ec5/version",
            "/api/ec5/manifest",
            "/api/ec5/status",
            "/api/ec5/report",
        ],
        "arm_route": "/api/ec5/arm",
        "execute_route": "/api/ec5/execute",
        "arm_intent": (
            "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
        ),
        "execute_intent": (
            "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
        ),
        "persistent_claim": True,
        "arm_required": True,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "retry_allowed": False,
        "recovery_included": False,
        "j2_off_get_only_diagnostic_required_before_claim": True,
        "diagnostic_get_requests": 4,
        "diagnostic_post_requests": 0,
        "same_boot_nonce_required_for_visible_run": True,
        "legacy_nvs_never_written_or_cleared": True,
        "raw_frame_ingress": False,
        "startup_refresh": False,
    }
    for source in (
        "tools/mf1750_ec5_compiled_identity.py",
        "tools/mf1750_ec5_physical_once.py",
        "tools/mf1750_ec5_release.py",
        "tools/mf1750_ec5_stage_a_v2_identity.py",
    ):
        assert source in release.SOURCE_PATHS
    assert manifest["safety"]["hardware_authorized"] is False
    assert not (bundle / release.QUARANTINE_MARKER).exists()


def test_build_manifest_does_not_alias_frozen_validation_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _ = _build(tmp_path, monkeypatch)
    manifest["device_contract"]["retry_allowed"] = True
    manifest["incident_lineage"]["display_sequence_started"] = True
    manifest["safety"]["hardware_authorized"] = True
    assert release.DEVICE_CONTRACT["retry_allowed"] is False
    assert release.INCIDENT_LINEAGE["display_sequence_started"] is False
    assert release.SAFETY["hardware_authorized"] is False


def test_binary_tamper_fails_deep_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    (bundle / "firmware-u04.bin").write_bytes(b"tampered")
    with pytest.raises(release.EC5ReleaseError, match="firmware bytes differ"):
        release.validate_release(bundle)


def test_elf_tamper_fails_deep_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    path = bundle / "firmware-u04.elf"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(release.EC5ReleaseError, match="ELF bytes differ"):
        release.validate_release(bundle)


def test_wrong_compiled_runtime_digest_fails_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, u04, u07, u04_elf, u07_elf = _inputs(tmp_path, monkeypatch)
    wrong = bytes.fromhex(
        "a8056cdd450f70709ec75a0a0400dfbfb1f06000ae596420902156bec7bab00d"
    )
    u04_elf.write_bytes(_fixture_elf(4, dtm_override=wrong))
    with pytest.raises(release.EC5ReleaseError, match="compiled ELF identity gate"):
        release.build_release(
            panel_file=panel,
            u04_binary=u04,
            u07_binary=u07,
            u04_elf=u04_elf,
            u07_elf=u07_elf,
            created_at="2026-08-09T10:00:00+08:00",
        )


def test_resealed_candidate_cross_contamination_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, u04, u07, u04_elf, u07_elf = _inputs(tmp_path, monkeypatch)
    u04.write_bytes(_firmware("U04") + _firmware("U07"))
    with pytest.raises(release.EC5ReleaseError, match="other candidate identity"):
        release.build_release(
            panel_file=panel,
            u04_binary=u04,
            u07_binary=u07,
            u04_elf=u04_elf,
            u07_elf=u07_elf,
            created_at="2026-08-09T10:00:00+08:00",
        )


def test_quarantined_v1_token_is_rejected_from_new_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, u04, u07, u04_elf, u07_elf = _inputs(tmp_path, monkeypatch)
    u04.write_bytes(
        _firmware("U04") + b"\0" + release.identity.V1_BINARY_IDENTITY_TOKENS[0].encode()
    )
    with pytest.raises(release.EC5ReleaseError, match="quarantined V1 identity"):
        release.build_release(
            panel_file=panel,
            u04_binary=u04,
            u07_binary=u07,
            u04_elf=u04_elf,
            u07_elf=u07_elf,
            created_at="2026-08-09T10:00:00+08:00",
        )


def test_resealed_incident_lineage_tamper_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    path = bundle / "release-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["incident_lineage"]["display_sequence_started"] = True
    _reseal(path, value)
    with pytest.raises(release.EC5ReleaseError, match="incident lineage differs"):
        release.validate_release(bundle)


def test_resealed_compiled_report_tamper_fails_elf_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    path = bundle / "release-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["compiled_identity_report"]["variants"]["U04"]["symbols"][
        "dtm_sha256"
    ]["vma"] = "0x00000000"
    _reseal(path, value)
    with pytest.raises(release.EC5ReleaseError, match="compiled identity report differs"):
        release.validate_release(bundle)


def test_corrected_bundle_with_quarantine_marker_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    (bundle / release.QUARANTINE_MARKER).write_text("must not be here", encoding="utf-8")
    with pytest.raises(release.EC5ReleaseError, match="must not contain"):
        release.validate_release(bundle)


def test_manifest_tamper_fails_safety_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    path = bundle / "release-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["safety"]["hardware_authorized"] = True
    path.write_bytes(release.canonical_json_bytes(value))
    with pytest.raises(release.EC5ReleaseError, match="safety declaration"):
        release.validate_release(bundle)


def test_publish_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, artifacts = _build(tmp_path, monkeypatch)
    bundle = tmp_path / "bundle"
    release.publish_release(bundle, manifest, artifacts)
    with pytest.raises(release.EC5ReleaseError, match="could not publish"):
        release.publish_release(bundle, manifest, artifacts)


def test_relevant_source_drift_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _publish(tmp_path, monkeypatch)
    path = bundle / "release-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["source_snapshot"]["relevant_sources"][0]["sha256"] = "f" * 64
    _reseal(path, value)
    with pytest.raises(release.EC5ReleaseError, match="differs from release"):
        release.validate_release(bundle)


def test_cli_build_requires_and_copies_both_elfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, u04, u07, u04_elf, u07_elf = _inputs(tmp_path, monkeypatch)
    output = tmp_path / "cli-bundle"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/mf1750_ec5_release.py"),
            "build",
            "--panel",
            str(panel),
            "--u04-binary",
            str(u04),
            "--u07-binary",
            str(u07),
            "--u04-elf",
            str(u04_elf),
            "--u07-elf",
            str(u07_elf),
            "--output",
            str(output),
            "--created-at",
            "2026-08-09T10:00:00+08:00",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output / "firmware-u04.elf").read_bytes() == u04_elf.read_bytes()
    assert (output / "firmware-u07.elf").read_bytes() == u07_elf.read_bytes()
