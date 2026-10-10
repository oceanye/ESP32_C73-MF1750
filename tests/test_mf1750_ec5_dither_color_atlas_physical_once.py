from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from tests import test_mf1750_ec5_color_lab_physical_e2e_independent as color_e2e
from tools import mf1750_ec5_color_lab_physical_once as engine
from tools import mf1750_ec5_color_lab_recovery_physical_once as recovery_physical
from tools import mf1750_ec5_dither_color_atlas as offline_bundle
from tools import mf1750_ec5_dither_color_atlas_campaign as campaign
from tools import mf1750_ec5_dither_color_atlas_contract as contract
from tools import mf1750_ec5_dither_color_atlas_physical_once as physical
from tools import mf1750_ec5_otp_transition_matrix_physical_once as matrix_physical


BASE_URL = color_e2e.BASE_URL
BOOT_NONCE_A = color_e2e.BOOT_NONCE_A
BOOT_NONCE_B = color_e2e.BOOT_NONCE_B
ROOT = Path(__file__).resolve().parents[1]
REAL_RELEASE = (
    ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1"
    / "dither-color-atlas-real-release.json"
)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["integrity"] = {
        "canonical_sha256": campaign.sha256(value),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return result


def _identity(kind: str) -> dict[str, Any]:
    suffix = kind.rsplit("-", 1)[-1]
    return {
        "schema_version": contract.TOP_SCHEMA_VERSION,
        "kind": f"{physical.DEVICE_KIND_PREFIX}-{suffix}",
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }


def _nvs_contract() -> dict[str, Any]:
    return {
        "namespace": contract.NVS_NAMESPACE,
        "key": contract.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": campaign.ACTION_COUNT + 1,
    }


class StrictDitherFakeDevice(color_e2e.StrictFakeDevice):
    """Stateful fake device rebound to the two-action dither contract."""

    def _status(self) -> dict[str, Any]:
        root = super()._status()
        if self.phase == 0:
            complete = self.next_ordinal == campaign.ACTION_COUNT + 1
            root["state"] = "complete" if complete else "ready"
            root["campaign_complete"] = complete
        return root


@pytest.fixture(scope="module")
def synthetic_files(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, Any]]:
    """Create deterministic offline files; no requester or device is touched."""

    root = tmp_path_factory.mktemp("dither-physical-release")
    bundle_dir = root / "offline-bundle"
    bundle = offline_bundle.build_bundle(bundle_dir)

    campaign_root = campaign.build_campaign()
    campaign_file = root / "campaign.json"
    campaign_payload = campaign.canonical_json_bytes(campaign_root)
    campaign_file.write_bytes(campaign_payload)

    binary_file = root / "firmware.bin"
    elf_file = root / "firmware.elf"
    binary_payload = b"synthetic-dither-atlas-binary"
    elf_payload = b"\x7fELFsynthetic-dither-atlas-elf"
    binary_file.write_bytes(binary_payload)
    elf_file.write_bytes(elf_payload)

    def reference(
        label: str, file_sha256: str, canonical_sha256: str
    ) -> dict[str, Any]:
        return {
            "file": str(root / f"matrix-{label}.json"),
            "bytes": 1,
            "file_sha256": file_sha256,
            "integrity_sha256": canonical_sha256,
        }

    anchor = {
        "kind": "exact_finalized_otp_transition_matrix_ordinal3_white",
        "action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
        "ordinal": 3,
        "role": "OTP_WHITE_RECOVERY",
        "matrix_release": reference(
            "release",
            campaign.EXPECTED_MATRIX_RELEASE_FILE_SHA256,
            campaign.EXPECTED_MATRIX_RELEASE_CANONICAL_SHA256,
        ),
        "result": reference(
            "result",
            campaign.EXPECTED_MATRIX_RESULT_FILE_SHA256,
            campaign.EXPECTED_MATRIX_RESULT_CANONICAL_SHA256,
        ),
        "observation": reference(
            "observation",
            campaign.EXPECTED_MATRIX_OBSERVATION_FILE_SHA256,
            campaign.EXPECTED_MATRIX_OBSERVATION_CANONICAL_SHA256,
        ),
        "claim": reference(
            "claim",
            campaign.EXPECTED_MATRIX_CLAIM_FILE_SHA256,
            campaign.EXPECTED_MATRIX_CLAIM_CANONICAL_SHA256,
        ),
        "claim_registry": {
            "directory": str(root / "matrix-claims"),
            "registry_id": "workspace-mf1750-ec5-otp-transition-matrix-claims-v1",
        },
        "panel": {
            "board_id": "synthetic-board",
            "model": "E6-73",
            "pcb_revision": "synthetic",
            "serial": "synthetic-panel",
        },
        "panel_file_sha256": campaign.EXPECTED_MATRIX_PANEL_FILE_SHA256,
        "required_previous_boot_nonce": campaign.EXPECTED_MATRIX_BOOT_NONCE,
        "latest_visible_state": "clean_full_white_factory_otp",
        "clean_white_confirmed": True,
        "manual_no_intervening_refresh_confirmation_required": True,
    }
    compiled = {
        "file": str(campaign_file.resolve()),
        "bytes": len(campaign_payload),
        "file_sha256": campaign.sha256(campaign_payload),
        "canonical_sha256": campaign_root["integrity"]["canonical_sha256"],
        "action_count": campaign.ACTION_COUNT,
        "first_safe_stop_ordinal": campaign.FIRST_SAFE_STOP_ORDINAL,
    }
    binary_sha = campaign.sha256(binary_payload)
    elf_sha = campaign.sha256(elf_payload)
    release_root = _seal(
        {
            "schema_version": campaign.SCHEMA_VERSION,
            "kind": campaign.RELEASE_KIND,
            "evidence_mode": campaign.REAL_MODE,
            "compiled_campaign": compiled,
            "firmware": {
                "binary": {
                    "file": str(binary_file.resolve()),
                    "bytes": len(binary_payload),
                    "sha256": binary_sha,
                },
                "elf": {
                    "file": str(elf_file.resolve()),
                    "bytes": len(elf_payload),
                    "sha256": elf_sha,
                },
                "binary_elf_link": {"exact_match": True},
            },
            "offline_atlas_bundle": bundle,
            "panel": anchor["panel"],
            "panel_file": {
                "file": str(root / "panel.json"),
                "file_sha256": campaign.EXPECTED_MATRIX_PANEL_FILE_SHA256,
            },
            "predecessor_binding": anchor,
            "execution_eligible": True,
            "safety": {
                "profile_source": "factory_otp",
                "spatial_dithering_only": True,
                "runtime_lut_or_waveform_write": False,
                "electrical_parameter_write": False,
                "new_nvs_namespace_and_key": True,
                "global_nvs_clear": False,
                "wifi_credentials_preserved": True,
                "automatic_chaining": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "one_exact_human_authorization_required_per_action": True,
                "same_boot_and_no_intervening_refresh_required": True,
                "materializer_device_access_performed": False,
                "materializer_network_requests": 0,
                "materializer_visible_refreshes": 0,
                "visible_refresh_authorized_by_release": 0,
            },
            "state": (
                "REAL_FACTORY_OTP_DITHER_COLOR_ATLAS_RELEASE_READY_FOR_"
                "J2_OFF_PREFLIGHT_ONLY"
            ),
        }
    )
    release_file = root / "release.json"
    release_payload = campaign.canonical_json_bytes(release_root)
    release_file.write_bytes(release_payload)
    checked = {
        "file": str(release_file.resolve()),
        "bytes": len(release_payload),
        "file_sha256": campaign.sha256(release_payload),
        "canonical_sha256": release_root["integrity"]["canonical_sha256"],
        "execution_eligible": True,
        "evidence_mode": campaign.REAL_MODE,
        "action_count": campaign.ACTION_COUNT,
        "firmware_binary_sha256": binary_sha,
        "firmware_elf_sha256": elf_sha,
        "predecessor_action_id": campaign.FIRST_PREDECESSOR_ACTION_ID,
        "visible_refresh_authorized_by_release": 0,
    }
    return release_file, checked


@pytest.fixture
def offline_contract(
    synthetic_files: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> physical.ReleaseContext:
    release_file, checked = synthetic_files
    release_sha = checked["file_sha256"]

    def cached_release_validation(path: Path) -> dict[str, Any]:
        resolved = Path(path).resolve(strict=True)
        if (
            resolved != release_file.resolve()
            or campaign.sha256(resolved.read_bytes()) != release_sha
        ):
            raise campaign.DitherColorAtlasCampaignError(
                "offline red-team cache refuses a different release"
            )
        return deepcopy(checked)

    monkeypatch.setattr(
        campaign, "validate_materialized_release", cached_release_validation
    )
    monkeypatch.setattr(
        physical,
        "EXPECTED_CAMPAIGN_FILE_SHA256",
        campaign.sha256(
            Path(
                campaign._decode(  # noqa: SLF001
                    release_file.read_bytes(), label="synthetic release"
                )["compiled_campaign"]["file"]
            ).read_bytes()
        ),
    )
    release_root = campaign._decode(  # noqa: SLF001
        release_file.read_bytes(), label="synthetic release"
    )
    monkeypatch.setattr(
        physical,
        "EXPECTED_CAMPAIGN_CANONICAL_SHA256",
        release_root["compiled_campaign"]["canonical_sha256"],
    )
    monkeypatch.setattr(
        physical, "EXPECTED_RELEASE_FILE_SHA256", checked["file_sha256"]
    )
    monkeypatch.setattr(
        physical,
        "EXPECTED_RELEASE_CANONICAL_SHA256",
        checked["canonical_sha256"],
    )
    monkeypatch.setattr(
        physical,
        "EXPECTED_FIRMWARE_BINARY_SHA256",
        checked["firmware_binary_sha256"],
    )
    monkeypatch.setattr(
        physical,
        "EXPECTED_FIRMWARE_ELF_SHA256",
        checked["firmware_elf_sha256"],
    )
    monkeypatch.setattr(color_e2e, "campaign", campaign)
    monkeypatch.setattr(color_e2e, "contract", contract)
    monkeypatch.setattr(color_e2e, "physical", engine)
    monkeypatch.setattr(color_e2e, "_identity", _identity)
    monkeypatch.setattr(color_e2e, "_nvs_contract", _nvs_contract)
    return physical.load_release(release_file)


def _diagnose(
    context: physical.ReleaseContext,
    device: StrictDitherFakeDevice,
    registry: Path,
    evidence_file: Path,
) -> dict[str, Any]:
    device.driver_powered = False
    diagnostic = physical.diagnose_j2_off(
        context,
        BASE_URL,
        evidence_file=evidence_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    assert (
        physical.validate_j2_off_diagnostic(
            context, evidence_file, claim_registry=registry
        )
        == diagnostic
    )
    assert diagnostic["network"] == {"get_requests": 4, "post_requests": 0}
    assert diagnostic["snapshot"]["status"]["busy"] == 0
    assert diagnostic["formal_u07_claim_absence"]["kind"].startswith(
        "factory-otp-spatial-dither"
    )
    assert not registry.exists()
    return diagnostic


def _run(
    context: physical.ReleaseContext,
    device: StrictDitherFakeDevice,
    registry: Path,
    ordinal: int,
    result_file: Path,
    *,
    diagnostic_file: Path | None = None,
    prior_result_file: Path | None = None,
    prior_observation_file: Path | None = None,
    confirm_no_refresh: bool = True,
) -> dict[str, Any]:
    device.driver_powered = True
    return physical.run_once(
        context,
        BASE_URL,
        ordinal,
        authorization=physical.required_authorization(context, ordinal),
        result_file=result_file,
        claim_registry=registry,
        prior_result_file=prior_result_file,
        prior_observation_file=prior_observation_file,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=confirm_no_refresh,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=device,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )


def _observe(
    context: physical.ReleaseContext,
    registry: Path,
    ordinal: int,
    result_file: Path,
    observation_file: Path,
) -> dict[str, Any]:
    role = str(context.actions[ordinal - 1]["role"])
    observation = physical.finalize_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=registry,
        operator_report=(
            "seven by five dither atlas inspected on both halves"
            if role == contract.ROLE_ATLAS
            else "full clean white recovery confirmed"
        ),
        temperature_c=37.0,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=role == contract.ROLE_WHITE,
        confirm_map_fidelity=role == contract.ROLE_ATLAS,
    )
    assert (
        physical.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=registry,
        )
        == observation
    )
    return observation


def _complete_atlas(
    context: physical.ReleaseContext, tmp_path: Path
) -> tuple[StrictDitherFakeDevice, Path, Path, Path]:
    registry = tmp_path / "claims"
    device = StrictDitherFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)
    result_file = tmp_path / "atlas-result.json"
    result = _run(
        context,
        device,
        registry,
        1,
        result_file,
        diagnostic_file=diagnostic_file,
    )
    assert result["outcome"] == "complete_pass", result["error"]
    observation_file = tmp_path / "atlas-observation.json"
    _observe(context, registry, 1, result_file, observation_file)
    return device, registry, result_file, observation_file


def test_unsealed_hashes_fail_closed_before_requester(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "EXPECTED_CAMPAIGN_FILE_SHA256",
        "EXPECTED_CAMPAIGN_CANONICAL_SHA256",
        "EXPECTED_RELEASE_FILE_SHA256",
        "EXPECTED_RELEASE_CANONICAL_SHA256",
        "EXPECTED_FIRMWARE_BINARY_SHA256",
        "EXPECTED_FIRMWARE_ELF_SHA256",
    ):
        monkeypatch.setattr(physical, name, None)
    context = physical.ReleaseContext(
        release_file=tmp_path / "missing-release.json",
        release_root={},
        release_file_sha256="0" * 64,
        release_canonical_sha256="0" * 64,
        campaign_file=tmp_path / "missing-campaign.json",
        campaign_root={},
        actions=(),
        execution_eligible=False,
        formal_u07_registry=None,
    )
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("unsealed release must fail before requester")

    with pytest.raises(
        physical.DitherColorAtlasPhysicalError, match="explicitly unsealed"
    ):
        physical.preflight(context, BASE_URL, 1, requester=requester)
    assert called is False


def test_frozen_real_release_load_describe_and_four_get_fake_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Replay the staged release, then substitute only the HTTP requester."""

    checked = campaign.validate_materialized_release(REAL_RELEASE)
    release_sha = checked["file_sha256"]

    def verified_release_cache(path: Path) -> dict[str, Any]:
        resolved = Path(path).resolve(strict=True)
        if (
            resolved != REAL_RELEASE.resolve()
            or campaign.sha256(resolved.read_bytes()) != release_sha
        ):
            raise campaign.DitherColorAtlasCampaignError(
                "verified real-release cache refuses changed bytes"
            )
        return deepcopy(checked)

    # The line above performs the full nested matrix-result replay once.  Cache
    # only that exact byte identity so load/describe/preflight test adapter
    # behavior without repeating the same ~40 s immutable predecessor audit.
    monkeypatch.setattr(
        campaign, "validate_materialized_release", verified_release_cache
    )
    monkeypatch.setattr(color_e2e, "campaign", campaign)
    monkeypatch.setattr(color_e2e, "contract", contract)
    monkeypatch.setattr(color_e2e, "physical", engine)
    monkeypatch.setattr(color_e2e, "_identity", _identity)
    monkeypatch.setattr(color_e2e, "_nvs_contract", _nvs_contract)

    context = physical.load_release(REAL_RELEASE)
    assert context.release_file_sha256 == physical.EXPECTED_RELEASE_FILE_SHA256
    assert context.release_canonical_sha256 == (
        physical.EXPECTED_RELEASE_CANONICAL_SHA256
    )
    assert [item["role"] for item in context.actions] == list(contract.ROLES)
    assert physical.describe(context, 1)["spatial_dithering_only"] is True
    assert physical.describe(context, 2)["automatic_white_recovery"] is False

    device = StrictDitherFakeDevice(context, tmp_path / "claims")
    device.driver_powered = True
    snapshot = physical.preflight(context, BASE_URL, 1, requester=device)
    assert snapshot.boot_nonce == BOOT_NONCE_A
    assert [call["method"] for call in device.calls] == ["GET"] * 4
    assert [call["path"] for call in device.calls] == [
        campaign.ENDPOINTS[name] for name in ("version", "manifest", "status", "report")
    ]
    assert not (tmp_path / "claims").exists()


def test_templates_bind_png_preview_and_binary_target_without_confusion(
    offline_contract: physical.ReleaseContext,
) -> None:
    atlas = physical.observation_template(offline_contract, 1)
    white = physical.observation_template(offline_contract, 2)

    assert atlas["preview"]["file"].endswith("strict-preview.png")
    assert atlas["preview"]["media_type"] == "image/png"
    assert "target_payload" not in atlas
    assert len(atlas["role_observation_fields"]["rows_0_to_6"]) == 7
    assert white["target_payload"]["file"].endswith("white.frame.bin")
    assert (
        white["target_payload"]["sha256"]
        == contract.ROLE_IDENTITIES[contract.ROLE_WHITE]["frame"]["sha256"]
    )
    assert "not an image preview" in white["target_payload"]["notice"]
    assert "preview" not in white
    assert atlas["automatic_white_recovery_authorized"] is False
    assert white["automatic_next_action_authorized"] is False


def test_full_two_action_fake_e2e_is_separate_one_shot_same_boot(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    registry = tmp_path / "claims"
    device = StrictDitherFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)

    atlas_result_file = tmp_path / "atlas-result.json"
    atlas_result = _run(
        context,
        device,
        registry,
        1,
        atlas_result_file,
        diagnostic_file=diagnostic_file,
    )
    assert atlas_result["outcome"] == "complete_pass", atlas_result["error"]
    assert device.driver_action_ordinals == [1]
    assert device.next_ordinal == 2
    assert atlas_result["prior_gate"]["kind"].startswith(
        "exact_finalized_matrix_ordinal3_clean_white"
    )
    atlas_observation_file = tmp_path / "atlas-observation.json"
    atlas_observation = _observe(
        context, registry, 1, atlas_result_file, atlas_observation_file
    )
    assert atlas_observation["visual"]["map_fidelity_pass"] is True

    white_result_file = tmp_path / "white-result.json"
    white_result = _run(
        context,
        device,
        registry,
        2,
        white_result_file,
        prior_result_file=atlas_result_file,
        prior_observation_file=atlas_observation_file,
    )
    assert white_result["outcome"] == "complete_pass", white_result["error"]
    assert white_result["prior_gate"]["kind"] == (
        "exact_atlas_result_and_manual_observation_same_boot"
    )
    assert white_result["prior_gate"]["required_same_boot_nonce"] == BOOT_NONCE_A
    white_observation = _observe(
        context,
        registry,
        2,
        white_result_file,
        tmp_path / "white-observation.json",
    )

    assert white_observation["visual"]["full_clean_white"] is True
    assert device.driver_action_ordinals == [1, 2]
    assert device.next_ordinal == 3
    assert device._status()["campaign_complete"] is True
    assert len(list(registry.glob("*.json"))) == 2
    assert sum(call["method"] == "POST" for call in device.calls) == 4
    assert sum(call["method"] == "GET" for call in device.calls) == 18
    assert physical.required_authorization(
        context, 1
    ) != physical.required_authorization(context, 2)


def test_missing_observation_and_no_refresh_fail_before_network_or_claim(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    device, registry, atlas_result, atlas_observation = _complete_atlas(
        context, tmp_path
    )
    calls_before = deepcopy(device.calls)

    with pytest.raises(
        physical.DitherColorAtlasPhysicalError, match="exact Atlas result"
    ):
        _run(context, device, registry, 2, tmp_path / "missing-prior.json")
    assert device.calls == calls_before
    assert not (tmp_path / "missing-prior.json").exists()

    with pytest.raises(
        physical.DitherColorAtlasPhysicalError, match="no-intervening-refresh"
    ):
        _run(
            context,
            device,
            registry,
            2,
            tmp_path / "no-refresh-confirmation.json",
            prior_result_file=atlas_result,
            prior_observation_file=atlas_observation,
            confirm_no_refresh=False,
        )
    assert device.calls == calls_before
    assert len(list(registry.glob("*.json"))) == 1


def test_reboot_after_j2_diagnostic_fails_before_claim_or_post(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    registry = tmp_path / "claims"
    device = StrictDitherFakeDevice(context, registry)
    diagnostic_file = tmp_path / "j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)
    device.reboot_before_first_action(BOOT_NONCE_B)
    calls_before = len(device.calls)

    with pytest.raises(
        physical.DitherColorAtlasPhysicalError, match="boot nonce differs"
    ):
        _run(
            context,
            device,
            registry,
            1,
            tmp_path / "must-not-exist.json",
            diagnostic_file=diagnostic_file,
        )
    new_calls = device.calls[calls_before:]
    assert len(new_calls) == 4
    assert all(call["method"] == "GET" for call in new_calls)
    assert not registry.exists()
    assert device.claim_seen_before_arm == []


def test_anchor_tamper_and_duplicate_claim_fail_before_requester(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    tampered = deepcopy(context.release_root)
    tampered["predecessor_binding"]["observation"]["file_sha256"] = "0" * 64
    tampered_context = replace(context, release_root=tampered)
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("tampered anchor must fail before requester")

    with pytest.raises(
        physical.DitherColorAtlasPhysicalError,
        match="exact dither color-atlas release gate differs",
    ):
        physical.run_once(
            tampered_context,
            BASE_URL,
            1,
            authorization=campaign.required_authorization(context.actions[0]),
            result_file=tmp_path / "tampered.json",
            claim_registry=tmp_path / "claims",
            j2_off_diagnostic_file=tmp_path / "unused.json",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=requester,
        )
    assert called is False

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    device, registry, _result, _observation = _complete_atlas(context, duplicate_root)
    calls_before = deepcopy(device.calls)
    with pytest.raises(
        physical.DitherColorAtlasPhysicalError, match="claim.*already exists"
    ):
        _run(
            context,
            device,
            registry,
            1,
            tmp_path / "duplicate-result.json",
            diagnostic_file=tmp_path / "duplicate" / "j2-off.json",
        )
    assert device.calls == calls_before


def test_engine_globals_restore_and_runtime_lut_surface_is_absent(
    offline_contract: physical.ReleaseContext, tmp_path: Path
) -> None:
    context = offline_contract
    before = {
        name: getattr(engine, name)
        for name in physical._ENGINE_BINDINGS  # noqa: SLF001
    }
    with pytest.raises(physical.DitherColorAtlasPhysicalError):
        physical.run_once(
            context,
            BASE_URL,
            2,
            authorization=physical.required_authorization(context, 2),
            result_file=tmp_path / "never-created.json",
            claim_registry=tmp_path / "claims",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("requester must not run")
            ),
        )
    assert {
        name: getattr(engine, name)
        for name in physical._ENGINE_BINDINGS  # noqa: SLF001
    } == before

    for ordinal in (1, 2):
        description = physical.describe(context, ordinal)
        assert description["factory_otp_profile"] is True
        assert description["runtime_lut_or_waveform_changed"] is False
        assert description["automatic_chaining"] is False
    assert physical.CLAIM_REGISTRY_ID.endswith("dither-color-atlas-claims-v1")
    assert physical.DEFAULT_CLAIM_REGISTRY.name == (
        ".mf1750_ec5_dither_color_atlas_claims"
    )
    assert not set(inspect.signature(physical.run_once).parameters) & {
        "profile",
        "runtime_profile",
        "runtime_lut",
        "lut_payload",
        "waveform",
    }
    assert all("runtime" not in endpoint for endpoint in campaign.ENDPOINTS.values())


@pytest.mark.parametrize(
    ("outer", "inner", "outer_raises"),
    (
        pytest.param(physical, matrix_physical, False, id="dither-to-matrix"),
        pytest.param(matrix_physical, physical, True, id="matrix-to-dither-error"),
        pytest.param(
            recovery_physical,
            physical,
            True,
            id="recovery-to-dither-error",
        ),
    ),
)
def test_cross_facade_shared_lock_blocks_and_restores_engine_identity(
    outer: Any, inner: Any, outer_raises: bool
) -> None:
    """No facade may observe or restore another facade's engine bindings."""

    assert physical._ENGINE_LOCK is engine._ENGINE_BINDING_LOCK  # noqa: SLF001
    assert matrix_physical._ENGINE_LOCK is engine._ENGINE_BINDING_LOCK  # noqa: SLF001
    assert recovery_physical._ENGINE_LOCK is engine._ENGINE_BINDING_LOCK  # noqa: SLF001

    binding_names = set(outer._ENGINE_BINDINGS) | set(  # noqa: SLF001
        inner._ENGINE_BINDINGS  # noqa: SLF001
    )
    baseline = {name: getattr(engine, name) for name in binding_names}
    outer_entered = threading.Event()
    inner_attempting = threading.Event()
    inner_entered = threading.Event()
    release_outer = threading.Event()
    expected_outer_error_seen = threading.Event()
    errors: list[BaseException] = []

    class ExpectedOuterExit(RuntimeError):
        pass

    def outer_worker() -> None:
        try:
            with outer._bound_engine():  # noqa: SLF001
                assert (
                    engine.campaign
                    is outer._ENGINE_BINDINGS[  # noqa: SLF001
                        "campaign"
                    ]
                )
                outer_entered.set()
                if not release_outer.wait(5):
                    raise AssertionError("test did not release outer facade")
                if outer_raises:
                    raise ExpectedOuterExit("exercise context-manager finally")
        except ExpectedOuterExit:
            expected_outer_error_seen.set()
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    def inner_worker() -> None:
        try:
            if not outer_entered.wait(5):
                raise AssertionError("outer facade never acquired shared lock")
            inner_attempting.set()
            with inner._bound_engine():  # noqa: SLF001
                inner_entered.set()
                assert (
                    engine.campaign
                    is inner._ENGINE_BINDINGS[  # noqa: SLF001
                        "campaign"
                    ]
                )
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    outer_thread = threading.Thread(target=outer_worker, daemon=True)
    inner_thread = threading.Thread(target=inner_worker, daemon=True)
    outer_thread.start()
    assert outer_entered.wait(5)
    inner_thread.start()
    assert inner_attempting.wait(5)
    assert inner_entered.wait(0.15) is False
    assert engine.campaign is outer._ENGINE_BINDINGS["campaign"]  # noqa: SLF001

    release_outer.set()
    outer_thread.join(5)
    inner_thread.join(5)
    assert not outer_thread.is_alive()
    assert not inner_thread.is_alive()
    assert inner_entered.is_set()
    assert expected_outer_error_seen.is_set() is outer_raises
    assert errors == []
    assert {name: getattr(engine, name) for name in binding_names} == baseline


def test_run_cli_emits_unknown_evidence_then_returns_dedicated_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = SimpleNamespace(
        command="run",
        release=Path("unused-release.json"),
        base_url=BASE_URL,
        ordinal=1,
        authorize="unused-authorization",
        result=Path("unused-result.json"),
        claim_registry=Path("unused-claims"),
        prior_result=None,
        prior_observation=None,
        j2_off_diagnostic=Path("unused-diagnostic.json"),
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        poll_count=1,
        poll_interval_seconds=0.0,
    )
    monkeypatch.setattr(physical, "_parse_args", lambda _argv: args)
    monkeypatch.setattr(physical, "load_release", lambda _path: object())
    monkeypatch.setattr(
        physical,
        "run_once",
        lambda *_args, **_kwargs: {
            "outcome": "unknown_do_not_retry_or_recover",
            "state": "authorization_permanently_consumed_do_not_rerun",
        },
    )

    assert physical.main([]) == 3
    assert '"outcome": "unknown_do_not_retry_or_recover"' in capsys.readouterr().out
