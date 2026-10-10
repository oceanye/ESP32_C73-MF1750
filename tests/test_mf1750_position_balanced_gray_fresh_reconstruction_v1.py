from __future__ import annotations

from pathlib import Path

import pytest

from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_audit as audit,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_codegen as codegen,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_once as runner,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as pack,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_codegen as white_codegen,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_once as white_runner,
)
from tools import (
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_pack as white_pack,
)


@pytest.fixture(scope="module")
def first_report() -> dict:
    return pack.first_pack.build_report()


@pytest.fixture(scope="module")
def template() -> dict:
    return pack.template_report()


def test_three_optical_actions_are_exact_f1_v3_g1_g2_g3_bytes(
    template: dict, first_report: dict
) -> None:
    assert len(template["actions"]) == 3
    assert template["contract"]["required_ordinals"] == [1, 2, 3]
    assert template["contract"]["g4_present"] is False
    for reconstructed, original in zip(
        template["actions"], first_report["actions"][:3], strict=True
    ):
        assert reconstructed["frame"] == original["frame"]
        assert reconstructed["cs1_dtm"] == original["cs1_dtm"]
        assert reconstructed["cs2_dtm"] == original["cs2_dtm"]
        assert reconstructed["effective_driver_profile"] == original[
            "effective_driver_profile"
        ]


def test_campaign_identity_is_new_and_g4_cannot_be_selected(
    template: dict, first_report: dict
) -> None:
    assert pack.CAMPAIGN_ID != pack.first_pack.CAMPAIGN_ID
    assert pack.BASE_ROUTE != pack.first_pack.CONFIG.base_route
    assert pack.NVS_NAMESPACE != pack.first_pack.NVS_NAMESPACE
    assert pack.NVS_KEY != pack.first_pack.NVS_KEY
    assert pack.NVS_BOOT_KEY != pack.first_pack.NVS_BOOT_KEY
    assert set(runner.ACTION_OUTPUTS) == {1, 2, 3}
    for reconstructed, original in zip(
        template["actions"], first_report["actions"][:3], strict=True
    ):
        assert reconstructed["descriptor_id"] != original["descriptor_id"]
        assert reconstructed["action_id"] != original["action_id"]
    assert first_report["actions"][3]["action_id"] not in str(template)


def test_predecessor_package_is_exact_while_live_evidence_is_not_guessed() -> None:
    assert pack.source_package_is_sealed() is True
    assert pack.source_authority_is_sealed() is False
    assert pack.first_construction_reference_is_sealed() is False
    assert pack.SOURCE_PACKAGE_BINDING == {
        "campaign_id": (
            "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_"
            "FACTORY_OTP_WHITE_SUCCESSOR_V1"
        ),
        "contract_id": "79ac7bae08b912cdcbf3d959029d56c740407275ef70c91de738b8205dcaa433",
        "descriptor_id": "c8492ebc83abd0a1721abfd4ae001f405bb21e0e1d87ae1ae20fb076f6be41c6",
        "action_id": "934330c22eb1057c7595c5db6711bfcbc7647291e56f5bd8acd059aa6a65e21d",
        "firmware_bin_bytes": 787632,
        "firmware_bin_sha256": "7fe34992e9f0060d5b164d5c6f761ad38b755446854bd4bd22a65e52716a769b",
        "firmware_elf_bytes": 13214432,
        "firmware_elf_sha256": "1d16602e13fe29d9c025c6da78ea6ff3e10d0bc8a4d38139f1ab541ca3a0f33e",
    }
    for binding in (*pack.SOURCE_BINDINGS.values(), *pack.FIRST_CONSTRUCTION_BINDINGS.values()):
        assert binding["path"] is None
        assert binding["bytes"] is None
        assert binding["file_sha256"] is None
    report = pack.build_report()
    assert report["contract_id"] == (
        "5d76fda3bf199d29538ec0c6555db4a294b6b11ffb5805613805b4f759b7d132"
    )
    with pytest.raises(pack.FreshReconstructionV1PackError):
        pack.validate_live_execution_gate()


def test_sealed_offline_codegen_keeps_live_execution_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "generated"
    monkeypatch.setattr(codegen, "OUTPUT_ROOT", output)
    monkeypatch.setattr(codegen, "REPO_ROOT", tmp_path)
    generated = codegen.generate()
    assert generated["result"] == "PASS"
    assert len(generated["generated"]) == 4
    assert all((output / name).is_file() for name in generated["generated"])
    validation = runner.dry_validate(require_sealed=False)
    assert validation["result"] == "OFFLINE_IDENTITY_PASS_LIVE_EXECUTION_BLOCKED"
    assert validation["offline_predecessor_package_sealed"] is True
    assert validation["live_execution_gate_passed"] is False
    assert validation["g4_accepted"] is False


def test_generated_template_has_three_actions_and_frozen_transport(
    template: dict, first_report: dict
) -> None:
    sources = codegen.render_sources(template)
    main = sources[codegen.MAIN_NAME].decode()
    config = sources[codegen.CONFIG_NAME].decode()
    driver = sources[codegen.DRIVER_NAME].decode()
    assert "static constexpr uint8_t kActionCount = 3;" in main
    assert codegen.NEW_BUILD_MACRO in main
    assert codegen.OLD_BUILD_MACRO not in main
    assert config.count("PBGFR1_ACTION(") == 4  # macro definition plus three rows
    assert first_report["actions"][3]["action_id"] not in config
    assert '\\"g4_present\\":false' in config
    assert "ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_epd_driver.cpp" in driver


def test_reconstruction_contract_keeps_zero_qualified_until_comparison(
    template: dict
) -> None:
    contract = template["contract"]
    assert contract["same_geometry_and_camera_settings_as_first_construction_required"] is True
    assert contract["comparison_scope"] == "CONTROLLER_LOCAL_RECIPE_AND_POSITION_MATCHED"
    assert contract["qualified_colors"] == 0
    assert contract["qualified_gray_levels"] == 0
    assert contract["qualified_brightness_levels"] == 0
    assert contract["retry"] is False
    assert contract["fallback"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_independent_white_successor_is_r3_complete_only() -> None:
    report = white_pack.template_report()
    contract = report["contract"]
    assert contract["accepted_source_ordinals"] == [3]
    assert contract["accepted_source_complete_actions"][0]["role"] == "G3_ACTIVE_C3_C7_TARGET"
    assert contract["source_fault_not_accepted"] is True
    assert contract["source_early_stop_not_accepted"] is True
    assert contract["main_campaign_resume_after_containment"] is False
    assert white_pack.CAMPAIGN_ID != pack.CAMPAIGN_ID
    assert white_pack.NVS_NAMESPACE != pack.NVS_NAMESPACE
    assert white_pack.BASE_ROUTE != pack.BASE_ROUTE
    validation = white_runner.dry_validate()
    assert validation["accepted_source_ordinals"] == [3]
    assert validation["result"] == (
        "OFFLINE_IDENTITY_PASS_RECONSTRUCTION_R3_LIVE_GATE_PENDING"
    )


def test_white_codegen_rewrites_old_h2_surface_to_r3_only() -> None:
    sources = white_codegen.render_sources(white_pack.template_report())
    main = sources[white_codegen.MAIN_NAME].decode()
    identity = sources[white_codegen.IDENTITY_NAME].decode()
    assert '\\"accepted_source_complete_ordinals\\":[3]' in main
    assert '\\"accepted_source_complete_ordinals\\":[5]' not in main
    assert "source_main_completed_r3_only" in main
    assert "source_main_completed_h2_only" not in main
    assert white_codegen.NEW_MACRO in main
    assert "RECONSTRUCTION_R3_COMPLETE" in identity


def test_offline_audit_reports_explicit_blocking_gates() -> None:
    result = audit.audit()
    assert result["result"] == "PASS_OFFLINE_SEALED_LIVE_EXECUTION_GATED"
    assert result["main_action_count"] == 3
    assert result["g4_present_or_accepted"] is False
    assert result["source_hold_white_predecessor_package_sealed"] is True
    assert result["main_artifacts_sealed"] is True
    assert result["white_successor_artifacts_sealed"] is True
    assert result["white_successor_accepted_source_ordinals"] == [3]
    assert result["qualified_gray_levels"] == 0
    assert "SECOND_CONSTRUCTION_SAME_GEOMETRY_AND_CAMERA_SETTINGS_COMPARISON" in result[
        "blocking_gates"
    ]
