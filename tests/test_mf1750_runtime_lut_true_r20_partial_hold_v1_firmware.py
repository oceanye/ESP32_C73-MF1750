from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "platformio.runtime_lut_true_r20_partial_hold_v1.ini"
IDENTITY = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_identity.inc"
CONFIG = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_main_config.inc"
DRIVER = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_driver.inc"
PROGRAM = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_program.inc"
QUALIFIER = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_qualifier.inc"
MAIN = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_main.cpp"
EPD_DRIVER = ROOT / "src/ec5_runtime_lut_true_r20_partial_hold_v1_epd_driver.cpp"
ONCE = ROOT / "tools/mf1750_runtime_lut_true_r20_partial_hold_v1_once.py"
BUILD_DIR = (
    ROOT
    / ".pio/build-runtime-lut-true-r20-partial-hold-v1"
    / "ec5_runtime_lut_true_r20_partial_hold_v1"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    left = source.index(start)
    return source[left : source.index(end, left)]


def _literal(source: str, name: str) -> object:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal {name}")


def test_isolated_build_has_no_upload_configuration() -> None:
    source = _text(INI)
    assert "default_envs = ec5_runtime_lut_true_r20_partial_hold_v1" in source
    assert "build-runtime-lut-true-r20-partial-hold-v1" in source
    assert "-<*>" in source
    assert "+<ec5_runtime_lut_true_r20_partial_hold_v1_main.cpp>" in source
    assert "+<ec5_runtime_lut_true_r20_partial_hold_v1_epd_driver.cpp>" in source
    assert "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_BUILD=1" in source
    assert "upload_port" not in source
    assert "upload_protocol" not in source


def test_four_action_contract_is_unique_and_candidate_only() -> None:
    report = pack.build_report()
    assert report["contract_id"] == pack.CONTRACT_ID
    assert len(report["actions"]) == 4
    assert [item["role"] for item in report["actions"]] == list(pack.ROLES)
    assert report["contract"]["profile_sequence"] == [
        "active",
        "commented",
        "active",
        None,
    ]
    assert report["contract"]["runtime_transport_codes"] == [0, 0, 2]
    assert report["contract"]["candidate_codes_are_not_colour_names"] is True
    assert report["contract"]["external_factory_white_anchor_required"] is True
    assert report["contract"]["factory_otp_white_recovery_ordinal"] == 4
    assert report["contract"]["autochain"] is False
    assert report["contract"]["retry"] is False
    assert report["contract"]["automatic_recovery"] is False


def test_batch1_prerequisite_is_frozen_without_claiming_colour_names() -> None:
    requirement = pack.BATCH1_EVIDENCE_REQUIREMENTS
    assert requirement["campaign_id"] == "EC5_SAME_R20_PARITY_2X4_V1"
    assert requirement["contract_id"] == (
        "718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8"
    )
    assert [item["action_id"] for item in requirement["required_actions"]] == [
        "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4",
        "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816",
        "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381",
        "711ba3e2310347645f6734537041959eb6f6dd419d26882bdc4264ad66fdc717",
    ]
    assert requirement["candidate_mapping_status"] == (
        "FROZEN_CANDIDATES_PENDING_BATCH1_EVIDENCE"
    )
    assert requirement["forbid_position_or_colour_name_inference"] is True
    for action in requirement["required_actions"]:
        assert action["capture_binding"] == "live_synchronized"
        assert action["coverage_scope"] == "full_panel"
        assert action["full_panel_visible_required"] is True
        assert action["full_panel_uncropped_required"] is True
        assert action["action_result_file_sha256_required"] is True
        assert action["action_result_canonical_integrity_sha256_required"] is True
        assert action["photo_file_sha256_required"] is True
        assert action["capture_sidecar_file_sha256_required"] is True
        assert action["capture_sidecar_binds_action_result_sha256"] is True
        assert action["capture_sidecar_binds_photo_sha256"] is True
        assert "capture_sidecar_binds_repeat_noise_report_sha256" not in action
    capture = requirement["fixed_capture_contract"]
    assert capture["capture_count"] == 4
    assert capture["all_captures_live_synchronized"] is True
    assert capture["all_captures_full_panel"] is True
    assert capture["camera_identity_tuple_fields_required"] == [
        "camera_id",
        "instance_id",
        "index",
        "backend",
    ]
    assert capture["camera_identity_tuple_all_fields_present_required"] is True
    assert capture["same_camera_identity_tuple_across_all_actions"] is True
    assert capture["same_camera_signature_across_all_actions"] is True
    assert capture["same_mount_id_across_all_actions"] is True
    assert "camera_identity_sha256_required" not in capture
    assert "same_camera_identity_sha256_across_all_actions" not in capture
    assert "mount_asset_sha256_required" not in capture
    assert "same_mount_asset_sha256_across_all_actions" not in capture
    assert capture["camera_or_mount_move_between_actions_forbidden"] is True
    assert capture["manual_controls"] == {
        "auto_exposure": False,
        "auto_white_balance": False,
        "autofocus": False,
        "manual_exposure_value_required": True,
        "manual_white_balance_value_required": True,
        "manual_focus_value_required": True,
        "control_readback_required": True,
        "same_control_readbacks_across_all_actions": True,
    }
    noise = requirement["repeat_noise_report_contract"]
    assert noise["required"] is True
    assert noise["report_binds_camera_signature"] is True
    assert noise["report_binds_mount_id"] is True
    assert (
        noise["camera_signature_and_mount_id_must_exactly_match_all_four_captures"]
        is True
    )
    assert "report_binds_camera_identity_sha256" not in noise
    assert "report_binds_mount_asset_sha256" not in noise
    assert noise["top_level_evidence_bundle_binds_report_file_sha256"] is True
    assert noise["all_four_analysis_repeat_noise_p95_values_equal_report"] is True
    assert noise["capture_sidecars_do_not_bind_repeat_noise_report"] is True
    assert noise["analysis_reports_requiring_exact_repeat_noise_p95_match"] == [
        "aa_atlas",
        "white_after_aa",
        "cc_atlas",
        "white_after_cc",
    ]


def test_true_r20_wrappers_include_only_dedicated_implementation_copies() -> None:
    main = _text(MAIN)
    epd_driver = _text(EPD_DRIVER)
    assert '"ec5_runtime_lut_true_r20_partial_hold_v1_program.inc"' in main
    assert '"ec5_runtime_lut_true_r20_partial_hold_v1_driver.inc"' in epd_driver
    assert '"ec5_runtime_lut_true_r20_partial_hold_v1_qualifier.inc"' in epd_driver


def test_each_runtime_action_binds_full_tuple_and_same_hash_to_both_cs() -> None:
    report = pack.build_report()
    runtime = report["actions"][:3]
    assert [item["tuple_name"] for item in runtime] == [
        "active",
        "commented",
        "active",
    ]
    for item in runtime:
        profile = pack.PROFILES[item["tuple_name"]]
        assert item["complete_tuple"] == profile
        assert item["cs1_tuple_sha256"] == profile["tuple_sha256"]
        assert item["cs2_tuple_sha256"] == profile["tuple_sha256"]
        assert set(profile) == {
            "name",
            "global_header_sha256",
            "power_command",
            "power_bytes",
            "power_sha256",
            "pll_command",
            "pll_bytes",
            "pll_sha256",
            "r20_command",
            "r20_prefix_bytes",
            "r20_prefix_sha256",
            "r21_command",
            "r21_bytes",
            "r21_sha256",
            "tuple_sha256",
        }
    assert pack.PROFILE_ACTIVE["tuple_sha256"] != pack.PROFILE_COMMENTED["tuple_sha256"]


def test_clean_ptlw_transport_and_three_disjoint_windows_are_exact() -> None:
    runtime = pack.build_report()["actions"][:3]
    assert [item["ptlw_payload_hex"] for item in runtime] == [
        "003000cf004000b701",
        "013001cf00f0016701",
        "003000cf01a0021701",
    ]
    assert [item["ptlw_writes_per_controller"] for item in runtime] == [1, 1, 1]
    assert [item["prestage_dtm"]["bytes"] for item in runtime] == [153_600] * 3
    assert [item["target_dtm"]["bytes"] for item in runtime] == [9_600] * 3
    assert pack.PRELOAD_DTM_SHA256 == (
        "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd"
    )


def test_driver_true_branch_selects_same_complete_r20_for_both_controllers() -> None:
    source = _text(DRIVER)
    upload = _slice(
        source,
        "bool phUploadRuntimeLutToController(",
        "void phApplyWindow(",
    )
    assert "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_BUILD" in upload
    assert "if (useCommentedTuple)" in upload
    assert "ph_lut::commented::kR20Payload" in upload
    assert "ph_lut::commented::kR21Payload" in upload
    assert "ph_lut::active::kR20Payload" in upload
    assert "ph_lut::active::kR21Payload" in upload
    display = _slice(
        source,
        "bool epdDisplayCompiledChromaGrid(",
        "const uint32_t cs1PreloadStarted",
    )
    assert "const bool useCommentedGlobal = role == EpdChromaGridRole::Mid;" in display
    assert "phUploadRuntimeLutToController(false, useCommentedGlobal)" in display
    assert "phUploadRuntimeLutToController(true, useCommentedGlobal)" in display


def test_runtime_branch_is_full_code7_then_one_crop_and_pon_drf00_pof00() -> None:
    source = _text(DRIVER)
    runtime = _slice(
        source,
        "const uint32_t cs1PreloadStarted = millis();",
        "const bool ok = phRefreshTreatmentsIdentically();",
    )
    assert (
        runtime.count("phStreamUniformDtm(\n      false, ph::kFullControllerDtmBytes")
        == 1
    )
    assert (
        runtime.count("phStreamUniformDtm(\n      true, ph::kFullControllerDtmBytes")
        == 1
    )
    assert "const bool fullframe = false;" in runtime
    assert runtime.count("phWritePartialWindow(window, actionIndex") == 2
    refresh = _slice(source, "bool phRefreshTreatmentsIdentically()", "}  // namespace")
    assert refresh.count("epdCommand(PON);") == 1
    assert refresh.count("epdCommand(DRF);") == 1
    assert refresh.count("epdCommand(POF);") == 1
    assert refresh.count("epdData(0x00);") == 2
    for forbidden in ("CDI", "BTST2", "0x86", "phWritePartialWindow"):
        assert forbidden not in refresh


def test_firmware_contract_is_four_ordinals_and_requires_batch1_header() -> None:
    program = _text(PROGRAM)
    config = _text(CONFIG)
    assert "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_BUILD" in program
    assert "static constexpr uint8_t kActionCount = 4;" in program
    assert '"[1,2,3,4]"' in program
    assert "X-EC5-Batch1-Evidence-Requirements-Id" in config
    assert "batch1_evidence_requirements_id_missing_or_mismatch" in program
    assert 'external_anchor_required\\":true' in program
    assert 'factory_otp_recovery_ordinal\\":4' in program
    assert "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_BUILD" in _text(QUALIFIER)


def test_identity_embeds_contract_actions_tuple_hashes_and_forbidden_features() -> None:
    combined = _text(IDENTITY) + _text(CONFIG)
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.CONTRACT_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
        pack.PROFILE_ACTIVE["tuple_sha256"],
        pack.PROFILE_COMMENTED["tuple_sha256"],
        *pack.DESCRIPTOR_IDS,
        *pack.ACTION_IDS,
    ):
        assert value in combined
    for token in (
        "kHistoricalGlobalHeaderOnlyCrossLut = false",
        "kCompleteTupleSwitchedPerAction = true",
        "kSameTupleBothControllersPerAction = true",
        "kCandidateCodesRequireBatch1Evidence = true",
        "kRepeatPtlwAfterPonBusy = false",
        "kActionStageCdi = false",
        "kActionStageBtst2 = false",
        "kCommand0x86Reachable = false",
    ):
        assert token in combined


def test_clean_build_artifacts_match_runner_and_embed_release_ids() -> None:
    once = _text(ONCE)
    binary = BUILD_DIR / "firmware.bin"
    elf_path = BUILD_DIR / "firmware.elf"
    expected_bin_bytes = _literal(once, "FIRMWARE_BIN_BYTES")
    expected_bin_sha = _literal(once, "FIRMWARE_BIN_SHA256")
    expected_elf_bytes = _literal(once, "FIRMWARE_ELF_BYTES")
    expected_elf_sha = _literal(once, "FIRMWARE_ELF_SHA256")
    assert binary.stat().st_size == expected_bin_bytes
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected_bin_sha
    elf = elf_path.read_bytes()
    assert len(elf) == expected_elf_bytes
    assert hashlib.sha256(elf).hexdigest() == expected_elf_sha
    for value in (
        pack.CONTRACT_ID,
        pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
        *pack.DESCRIPTOR_IDS,
        *pack.ACTION_IDS,
    ):
        assert value.encode("ascii") in elf
