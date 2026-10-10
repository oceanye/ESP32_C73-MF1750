from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import stat
from unittest import mock

import pytest

from tools import mf1750_ec5_otp_transition_matrix_contract as contract
from tools import mf1750_ec5_otp_transition_matrix_physical_once as physical
from tools import mf1750_ec5_otp_transition_matrix_release as release


BUNDLE = (
    release.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_OTP_TRANSITION_MATRIX_RELEASE_OFFLINE_20260810_V1"
)


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    return json.loads((BUNDLE / release.MANIFEST_FILE).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_payloads() -> dict[str, bytes]:
    return {name: (BUNDLE / name).read_bytes() for name in release.SOURCE_FILES}


def test_checked_in_bundle_replays_release_validator_and_app_descriptor() -> None:
    original_validator = release.campaign.validate_materialized_release
    original_link = release._binary_elf_link
    with (
        mock.patch.object(
            release.campaign,
            "validate_materialized_release",
            wraps=original_validator,
        ) as validator,
        mock.patch.object(release, "_binary_elf_link", wraps=original_link) as link,
    ):
        report = release.validate_bundle(BUNDLE)

    validator.assert_called_once_with(BUNDLE.resolve() / release.RELEASE_FILE)
    link.assert_called_once()
    assert report["action_count"] == 3
    assert report["profile_source"] == "factory_otp"
    assert report["runtime_lut_or_waveform_write"] is False
    assert report["visible_refresh_authorizations"] == 0


def test_manifest_is_canonical_and_bundle_whitelist_is_exact(
    manifest: dict[str, object],
) -> None:
    payload = (BUNDLE / release.MANIFEST_FILE).read_bytes()
    assert payload == release.canonical_json_bytes(manifest)
    assert {entry.name for entry in BUNDLE.iterdir()} == set(release.EXACT_FILES)
    assert manifest["bundle_layout"] == {
        "exact_files": list(release.EXACT_FILES),
        "additional_entries_allowed": False,
        "symlinks_allowed": False,
        "execution_paths": "exact bundle-local regular files",
        "operator_previews_embedded": False,
    }
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    assert integrity == {
        "canonical_sha256": release.sha256(unsigned),
        "scope": release.HASH_SCOPE,
    }


def test_all_four_execution_artifacts_are_bundle_local_regular_files(
    manifest: dict[str, object],
) -> None:
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    assert {record["file"] for record in artifacts.values()} == set(
        release.SOURCE_FILES
    )
    for filename in release.SOURCE_FILES:
        path = BUNDLE / filename
        metadata = path.lstat()
        assert stat.S_ISREG(metadata.st_mode)
        assert not stat.S_ISLNK(metadata.st_mode)
        assert path.resolve(strict=True).parent == BUNDLE.resolve(strict=True)

    authority = manifest["execution_authority"]
    assert isinstance(authority, dict)
    assert authority["file"] == release.RELEASE_FILE
    assert authority["visible_refresh_authorizations"] == 0
    assert authority["runner_frozen_identity"] == release._runner_frozen_identity()


def test_release_execution_references_are_exactly_bundle_local() -> None:
    root = release._decode_json(
        (BUNDLE / release.RELEASE_FILE).read_bytes(), label="test release"
    )
    release._validate_execution_paths(root, BUNDLE.resolve())
    references = (
        root["compiled_campaign"]["file"],
        root["firmware"]["binary"]["file"],
        root["firmware"]["elf"]["file"],
    )
    assert {Path(value).resolve(strict=True).parent for value in references} == {
        BUNDLE.resolve(strict=True)
    }


def test_external_execution_authority_path_is_rejected(tmp_path: Path) -> None:
    root = deepcopy(
        release._decode_json(
            (BUNDLE / release.RELEASE_FILE).read_bytes(), label="test release"
        )
    )
    external = tmp_path / release.CAMPAIGN_FILE
    external.write_bytes((BUNDLE / release.CAMPAIGN_FILE).read_bytes())
    root["compiled_campaign"]["file"] = str(external.resolve())
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="exact file inside this bundle",
    ):
        release._validate_execution_paths(root, BUNDLE.resolve())


@pytest.mark.parametrize(
    ("filename", "record_name"),
    (
        (release.CAMPAIGN_FILE, "compiled_campaign"),
        (release.RELEASE_FILE, "materialized_release"),
        (release.FIRMWARE_BINARY_FILE, "firmware_binary"),
        (release.FIRMWARE_ELF_FILE, "firmware_elf"),
    ),
)
def test_any_execution_artifact_byte_replacement_is_rejected(
    manifest: dict[str, object],
    source_payloads: dict[str, bytes],
    filename: str,
    record_name: str,
) -> None:
    changed = dict(source_payloads)
    mutable = bytearray(changed[filename])
    mutable[-1] ^= 0x01
    changed[filename] = bytes(mutable)
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match=rf"{record_name} artifact bytes or SHA-256 differ",
    ):
        release._verify_manifest_artifacts(manifest, changed)


def test_bin_to_elf_descriptor_tamper_is_rejected(
    source_payloads: dict[str, bytes],
) -> None:
    binary = bytearray(source_payloads[release.FIRMWARE_BINARY_FILE])
    binary[176] ^= 0x01
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="does not bind the bundled ELF",
    ):
        release._binary_elf_link(
            bytes(binary), source_payloads[release.FIRMWARE_ELF_FILE]
        )


def test_manifest_tamper_and_resealed_policy_forgery_are_rejected(
    manifest: dict[str, object],
) -> None:
    unsealed_tamper = deepcopy(manifest)
    unsealed_tamper["campaign_contract"]["action_count"] = 4
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError, match="canonical seal differs"
    ):
        release._validate_seal(unsealed_tamper)

    forged = deepcopy(manifest)
    forged["safety"]["visible_refresh_authorizations"] = 1
    forged.pop("integrity")
    forged = release._seal(forged)
    release._validate_seal(forged)
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="zero-authorization factory-OTP safety policy differs",
    ):
        release._validate_manifest_policy(forged)


def test_three_action_factory_otp_contract_rejects_runtime_lut_forgery() -> None:
    campaign_root = deepcopy(
        release._decode_json(
            (BUNDLE / release.CAMPAIGN_FILE).read_bytes(), label="test campaign"
        )
    )
    release_root = release._decode_json(
        (BUNDLE / release.RELEASE_FILE).read_bytes(), label="test release"
    )
    campaign_root["classification"]["runtime_lut_or_waveform_changed"] = True
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="factory-OTP, no-runtime-LUT, zero-refresh-authorization",
    ):
        release._validate_safety_contract(
            campaign_root,
            release_root,
            campaign_report={"action_count": 3},
            release_report={
                "action_count": 3,
                "visible_refresh_authorized_by_release": 0,
            },
        )


def test_extra_dangerous_artifact_is_rejected_before_deep_validation(
    tmp_path: Path,
) -> None:
    for filename in release.EXACT_FILES:
        (tmp_path / filename).write_bytes(b"x")
    (tmp_path / "unreviewed-flash-image.bin").write_bytes(b"danger")
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="exact-file whitelist differs",
    ):
        release._exact_entries(tmp_path, include_manifest=True)


def test_symlinked_execution_artifact_is_rejected(tmp_path: Path) -> None:
    target = BUNDLE / release.FIRMWARE_BINARY_FILE
    for filename in release.EXACT_FILES:
        if filename != release.FIRMWARE_BINARY_FILE:
            (tmp_path / filename).write_bytes(b"x")
    try:
        os.symlink(target, tmp_path / release.FIRMWARE_BINARY_FILE)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="regular non-symlink file",
    ):
        release._exact_entries(tmp_path, include_manifest=True)


def test_operator_preview_dependencies_are_exactly_frozen_and_non_symlink(
    manifest: dict[str, object],
) -> None:
    previews = manifest["operator_previews"]
    assert previews == release._operator_preview_records()
    assert set(previews) == set(contract.ROLES)
    for role in contract.ROLES:
        path = Path(previews[role]["file"])
        assert path == Path(physical.PREVIEW_FILES[role])
        metadata = path.lstat()
        assert stat.S_ISREG(metadata.st_mode)
        assert not stat.S_ISLNK(metadata.st_mode)
        assert previews[role]["bytes"] == metadata.st_size
        assert previews[role]["sha256"] == release.sha256(path.read_bytes())


def test_build_never_overwrites_existing_manifest() -> None:
    before = (BUNDLE / release.MANIFEST_FILE).read_bytes()
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError, match="refusing to overwrite"
    ):
        release.build_bundle(BUNDLE)
    assert (BUNDLE / release.MANIFEST_FILE).read_bytes() == before


def test_atomic_creator_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / release.MANIFEST_FILE
    release._write_new(output, {"first": True})
    first = output.read_bytes()
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError, match="refusing to overwrite"
    ):
        release._write_new(output, {"second": True})
    assert output.read_bytes() == first


def test_cli_build_and_validate_dispatch_without_implicit_operations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_manifest = {"integrity": {"canonical_sha256": "a" * 64}}
    fake_report = {
        "action_count": 3,
        "visible_refresh_authorizations": 0,
    }
    with mock.patch.object(release, "build_bundle", return_value=fake_manifest) as build:
        assert release.main(["build", "--bundle", str(BUNDLE)]) == 0
    build.assert_called_once_with(BUNDLE)
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["visible_refresh_authorizations"] == 0

    with mock.patch.object(release, "validate_bundle", return_value=fake_report) as validate:
        assert release.main(["validate", "--bundle", str(BUNDLE)]) == 0
    validate.assert_called_once_with(BUNDLE)
    assert json.loads(capsys.readouterr().out) == fake_report


def test_cli_failure_is_fail_closed(capsys: pytest.CaptureFixture[str]) -> None:
    with mock.patch.object(
        release,
        "validate_bundle",
        side_effect=release.OtpTransitionMatrixReleaseError("test rejection"),
    ):
        assert release.main(["validate", "--bundle", str(BUNDLE)]) == 2
    assert "ERROR: test rejection" in capsys.readouterr().err


def test_copy_helper_does_not_mask_extra_artifacts(tmp_path: Path) -> None:
    copied = tmp_path / "copy"
    copied.mkdir()
    for filename in release.EXACT_FILES:
        shutil.copyfile(BUNDLE / filename, copied / filename)
    (copied / "flash_args").write_text("esptool erase_flash", encoding="utf-8")
    with pytest.raises(
        release.OtpTransitionMatrixReleaseError,
        match="extra=.*flash_args",
    ):
        release.validate_bundle(copied)
