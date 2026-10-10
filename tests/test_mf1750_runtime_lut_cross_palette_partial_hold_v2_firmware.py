from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v1_pack as v1
from tools import mf1750_runtime_lut_cross_palette_partial_hold_v2_pack as pack
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as fullframe


ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "platformio.runtime_lut_cross_palette_partial_hold_v2.ini"
IDENTITY = ROOT / "src/ec5_runtime_lut_cross_palette_partial_hold_v2_identity.inc"
CONFIG = ROOT / "src/ec5_runtime_lut_cross_palette_partial_hold_v2_main_config.inc"
DRIVER = ROOT / "src/ec5_runtime_lut_cross_palette_partial_hold_v2_driver.inc"
PROGRAM = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_program.inc"
ONCE = ROOT / "tools/mf1750_runtime_lut_cross_palette_partial_hold_v2_once.py"
BUILD_DIR = (
    ROOT
    / ".pio/build-runtime-lut-cross-palette-partial-hold-v2"
    / "ec5_runtime_lut_cross_palette_partial_hold_v2"
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


def test_isolated_build_has_new_sources_and_no_upload_configuration() -> None:
    source = _text(INI)
    assert "default_envs = ec5_runtime_lut_cross_palette_partial_hold_v2" in source
    assert "build_dir = .pio/build-runtime-lut-cross-palette-partial-hold-v2" in source
    assert "-<*>" in source
    assert "+<ec5_runtime_lut_cross_palette_partial_hold_v2_main.cpp>" in source
    assert "+<ec5_runtime_lut_cross_palette_partial_hold_v2_epd_driver.cpp>" in source
    assert "MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_BUILD=1" in source
    assert "upload_port" not in source
    assert "upload_protocol" not in source


def test_frozen_five_action_contract_is_new_and_exact() -> None:
    report = pack.build_report()
    assert report["contract_id"] == pack.CONTRACT_ID
    assert tuple(item["descriptor_id"] for item in report["actions"]) == pack.DESCRIPTOR_IDS
    assert tuple(item["action_id"] for item in report["actions"]) == pack.ACTION_IDS
    assert [item["role"] for item in report["actions"]] == list(pack.ROLES)
    assert report["contract"]["profile_sequence"] == [
        None,
        "active",
        "commented",
        "active",
        None,
    ]
    assert report["contract"]["runtime_transport_codes"] == [5, 6, 3]
    assert pack.CONTRACT_ID not in (v1.CONTRACT_ID, fullframe.CONTRACT_ID)
    assert set(pack.ACTION_IDS).isdisjoint(v1.ACTION_IDS)
    assert set(pack.ACTION_IDS).isdisjoint(fullframe.ACTION_IDS)


def test_clean_runtime_transport_identities_and_inclusive_windows_are_exact() -> None:
    runtime = pack.build_report()["actions"][1:4]
    assert [item["ptlw_payload_hex"] for item in runtime] == [
        "003000cf004000b701",
        "013001cf00f0016701",
        "003000cf01a0021701",
    ]
    assert [item["ptlw_writes_per_controller"] for item in runtime] == [1, 1, 1]
    assert [item["prestage_dtm"]["bytes"] for item in runtime] == [153_600] * 3
    assert [item["target_dtm"]["bytes"] for item in runtime] == [9_600] * 3
    assert [item["target_dtm"]["sha256"] for item in runtime] == list(
        pack.TARGET_DTM_SHA256
    )
    assert [item["cs1_dtm"]["sha256"] for item in runtime] == list(
        pack.COMBINED_DTM_SHA256
    )
    assert pack.PRELOAD_DTM_SHA256 == fullframe.PRELOAD_DTM_SHA256


def test_driver_runtime_branch_is_always_crop_after_full_code7_prestage() -> None:
    source = _text(DRIVER)
    runtime = _slice(
        source,
        "const uint32_t cs1PreloadStarted = millis();",
        "const bool ok = phRefreshTreatmentsIdentically();",
    )
    assert runtime.count("phStreamUniformDtm(\n      false, ph::kFullControllerDtmBytes") == 1
    assert runtime.count("phStreamUniformDtm(\n      true, ph::kFullControllerDtmBytes") == 1
    assert "const bool fullframe = false;" in runtime
    assert runtime.count("phWritePartialWindow(window, actionIndex") == 2
    assert "ph::kCroppedDtmBytes" in runtime
    assert "phSecondSettingAndRefreshRepeatPtlw" not in runtime


def test_runtime_refresh_is_only_pon_drf00_pof00_with_no_repeat_ptlw() -> None:
    refresh = _slice(
        _text(DRIVER),
        "bool phRefreshTreatmentsIdentically()",
        "}  // namespace",
    )
    assert refresh.count("epdCommand(PON);") == 1
    assert refresh.count("epdCommand(DRF);") == 1
    assert refresh.count("epdCommand(POF);") == 1
    assert refresh.count("epdData(0x00);") == 2
    for forbidden in ("CDI", "BTST2", "0x86", "phWritePartialWindow"):
        assert forbidden not in refresh


def test_identity_and_manifest_freeze_forbidden_features_and_new_state() -> None:
    combined = _text(IDENTITY) + _text(CONFIG)
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.CONTRACT_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.DEVICE_API_VERSION,
        *pack.DESCRIPTOR_IDS,
        *pack.ACTION_IDS,
        *pack.TARGET_DTM_SHA256,
        *pack.COMBINED_DTM_SHA256,
    ):
        assert value in combined
    for token in (
        "kRepeatPtlwAfterPonBusy = false",
        "kActionStageCdi = false",
        "kActionStageBtst2 = false",
        "kCommand0x86Reachable = false",
        '\\"runtime_treatment_repeat_ptlw_after_pon_busy\\":false',
        '\\"runtime_treatment_action_stage_cdi\\":false',
        '\\"runtime_treatment_action_stage_btst2\\":false',
        '\\"command_0x86\\":false',
    ):
        assert token in combined


def test_program_reports_exact_runtime_action_command_counts() -> None:
    body = _slice(
        _text(PROGRAM),
        "String successfulActionStageCommandCountsJson(",
        "void publishNoExecuteReport()",
    )
    assert "MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_BUILD" in body
    assert "action.ordinal >= 2U && action.ordinal <= 4U" in body
    assert "dtmBytes = 326400UL;" in body
    assert "lutBytes = 2478UL;" in body
    assert "ptlwWrites = 2U;" in body
    assert '"command_0x86":0' in body.replace("\\\"", '"')


def test_clean_build_artifacts_match_runner_and_embed_release_ids() -> None:
    once = _text(ONCE)
    binary = BUILD_DIR / "firmware.bin"
    elf_path = BUILD_DIR / "firmware.elf"
    expected_bin_bytes = _literal(once, "FIRMWARE_BIN_BYTES")
    expected_bin_sha = _literal(once, "FIRMWARE_BIN_SHA256")
    expected_elf_bytes = _literal(once, "FIRMWARE_ELF_BYTES")
    expected_elf_sha = _literal(once, "FIRMWARE_ELF_SHA256")
    assert binary.stat().st_size == expected_bin_bytes == 816_656
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected_bin_sha
    elf = elf_path.read_bytes()
    assert len(elf) == expected_elf_bytes == 13_368_436
    assert hashlib.sha256(elf).hexdigest() == expected_elf_sha
    for value in (pack.CONTRACT_ID, *pack.DESCRIPTOR_IDS, *pack.ACTION_IDS):
        assert value.encode("ascii") in elf
