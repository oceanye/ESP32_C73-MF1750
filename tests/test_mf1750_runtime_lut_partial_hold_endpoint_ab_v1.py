from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools import mf1750_runtime_lut_partial_hold_endpoint_ab_v1_once as once
from tools import mf1750_runtime_lut_partial_hold_endpoint_ab_v1_pack as pack
from tools import (
    mf1750_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_pack as white,
)
from tools import (
    mf1750_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_once as white_once,
)


ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_ab_is_same_roi_fresh_white_crossover() -> None:
    report = pack.build_report()
    actions = report["actions"]
    assert [item["ordinal"] for item in actions] == [1, 2, 3, 4, 5]
    assert [item["palette_source"] for item in actions] == [
        "FACTORY_OTP",
        "L535_RUNTIME",
        "FACTORY_OTP",
        "L535_RUNTIME",
        "FACTORY_OTP",
    ]
    assert [item["role"] for item in actions] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "PATCH_A",
        "FACTORY_OTP_WHITE_CROSSOVER_RESET",
        "PATCH_B",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]
    a, b = actions[1], actions[3]
    assert (
        {key: a["window"][key] for key in ("x", "y", "width", "height")}
        == {key: b["window"][key] for key in ("x", "y", "width", "height")}
        == {"x": 176, "y": 240, "width": 160, "height": 120}
    )
    assert a["ptlw_endpoint_treatment"] == {
        "cs1": "ye=y+h-1",
        "cs2": "ye=y+h",
    }
    assert b["ptlw_endpoint_treatment"] == {
        "cs1": "ye=y+h",
        "cs2": "ye=y+h-1",
    }
    for item in (a, b):
        assert item["dtm_rows_per_controller"] == 120
        assert item["cs1_dtm"]["bytes"] == 9600
        assert item["cs2_dtm"]["bytes"] == 9600
        assert item["cs1_dtm"] == item["cs2_dtm"]
    assert a["frame"] == b["frame"]
    assert report["contract"]["controlled_delta"]["fresh_white_before_each_treatment"]
    assert report["contract"]["controlled_delta"]["crossover_reset_ordinal"] == 3


def test_y_plus_h_is_experimental_not_a_fix_claim() -> None:
    boundary = pack.build_report()["contract"]["evidence_boundary"]
    assert boundary["exact_spd1657a_local_manual_contract"] == "ye=y+h-1"
    assert boundary["adjacent_gx_reference_workaround"] == "ye=y+h"
    assert boundary["sources_conflict"] is True
    assert boundary["predicted_fix"] is False
    assert boundary["physical_bottom_equals_logical_y_end_proven"] is False
    assert "121 PTLW rows" in boundary["declared_vs_stream_mismatch"]
    assert "FPC_DIRECTION" in boundary["observation_must_record"]


def test_compiled_identity_and_role_mapping_are_bounded_to_two_partials() -> None:
    report = pack.build_report()
    identity = (
        ROOT / "src/ec5_runtime_lut_partial_hold_endpoint_ab_v1_identity.inc"
    ).read_text(encoding="utf-8")
    driver = (
        ROOT / "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_partial_hold_endpoint_ab_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    assert report["contract_id"] in identity
    assert "kRoleCount = 2" in identity
    assert "kActionCount = 2" in identity
    for action in (report["actions"][1], report["actions"][3]):
        for key in ("descriptor_id", "action_id"):
            assert action[key] in identity
        assert action["frame"]["sha256"] in identity
    endpoint_role_branch = driver[
        driver.index("bool phRoleValid") : driver.index("size_t phActionIndexForRole")
    ]
    assert "role == EpdChromaGridRole::Source" in endpoint_role_branch
    assert "role == EpdChromaGridRole::Mid" in endpoint_role_branch
    assert "EpdChromaGridRole::Target" not in endpoint_role_branch.split("#elif", 1)[0]
    assert (
        "#if !defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)" in driver
    )
    assert "window.cs1YEndOneMore" in driver
    assert "window.cs2YEndOneMore" in driver
    assert "y + window.height - (yEndOneMore ? 0U : 1U)" in driver
    assert '3, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_CROSSOVER_RESET"' in config
    assert "4, EpdChromaGridRole::Mid, 1" in config
    assert 'adjacent_reference_comparator_is_predicted_fix\\":false' in config
    assert 'physical_bottom_equals_logical_y_end_proven\\":false' in config
    assert 'exact_spd1657a_local_manual_y_end\\":\\"y+h-1' in config
    assert "FPC_DIRECTION" in config


def test_executed_artifact_role_abi_snapshot_is_preserved() -> None:
    legacy_header = (
        ROOT
        / "src/ec5_runtime_lut_partial_hold_endpoint_ab_v1_legacy_chroma_grid_epd_driver.h"
    ).read_text(encoding="utf-8")
    live_header = (ROOT / "src/ec5_chroma_grid_epd_driver.h").read_text(
        encoding="utf-8"
    )
    assert "White = 0" in legacy_header
    assert "Source = 1" in legacy_header
    assert "Mid = 2" in legacy_header
    assert "Target = 3" in legacy_header
    assert "ReverseSource" not in legacy_header
    assert "ReverseTarget" not in legacy_header
    assert "ReverseSource = 4" in live_header
    assert "ReverseTarget = 5" in live_header


def test_main_artifacts_are_exactly_bound() -> None:
    status = once.artifact_binding_status()
    assert status["firmware_bin"]["verified"] is True
    assert status["firmware_elf"]["verified"] is True
    assert once.FIRMWARE_BIN.stat().st_size == once.FIRMWARE_BIN_BYTES
    assert hashlib.sha256(once.FIRMWARE_BIN.read_bytes()).hexdigest() == (
        once.FIRMWARE_BIN_SHA256
    )
    assert once.FIRMWARE_ELF.stat().st_size == once.FIRMWARE_ELF_BYTES
    assert hashlib.sha256(once.FIRMWARE_ELF.read_bytes()).hexdigest() == (
        once.FIRMWARE_ELF_SHA256
    )
    description = once.describe()
    assert description["fixed_transport"]["factory_otp_white_ordinals"] == [1, 3, 5]
    assert description["fixed_transport"]["runtime_lut_partial_ordinals"] == [2, 4]
    assert description["containment_required_after_abnormal_partial_action"]
    assert description["no_ordinal_skip_to_final_white"]


def test_main_source_has_busy_gates_at_arm_execute_dispatch() -> None:
    main = (
        ROOT / "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert main.count("MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD") >= 10
    assert 'rejectMutation(503, "arm_busy_not_idle_high"' in main
    assert 'rejectMutation(503, "execute_busy_not_idle_high"' in main
    assert 'enterFault("dispatch_busy_not_idle_high"' in main
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery()" in main


def test_fresh_independent_white_containment_is_exactly_bound() -> None:
    report = white.build_report()
    assert report["contract"]["fresh_identity"] is True
    assert report["contract"]["factory_otp_white_only"] is True
    assert report["contract"]["use_after_main_action_2_or_4_abnormal"] is True
    assert report["contract"]["nvs_namespace"] != pack.NVS_NAMESPACE
    assert report["contract"]["nvs_key"] != pack.NVS_KEY
    assert all(
        item["verified"] is True for item in report["artifact_binding_status"].values()
    )
    dedicated_main = (
        ROOT
        / "src/ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_main.cpp"
    ).read_text(encoding="utf-8")
    generic_main = (
        ROOT
        / "src/ec5_runtime_lut_cross_palette_partial_hold_v1_white_containment_main.cpp"
    ).read_text(encoding="utf-8")
    identity = (
        ROOT
        / "src/ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_identity.inc"
    ).read_text(encoding="utf-8")
    assert "MF1750_ENDPOINT_AB_WHITE_CONTAINMENT" in dedicated_main
    assert 'static constexpr const char *kNvsKey = "used_yew1";' in dedicated_main
    assert "MF1750_ENDPOINT_AB_WHITE_CONTAINMENT" not in generic_main
    assert "MF1750_HUE_BRIGHTNESS_BLUE_WHITE_CONTAINMENT" not in generic_main
    assert 'static constexpr const char *kNvsKey = "used_cxw1";' in generic_main
    containment_host = (
        ROOT
        / "tools/mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(\n            pack,\n            "CLAIM_KIND"' in containment_host
    assert 'getattr(\n            pack,\n            "RESULT_KIND"' in containment_host
    assert white.CLAIM_KIND == "mf1750-endpoint-ab-white-containment-claim"
    assert white.RESULT_KIND == "mf1750-endpoint-ab-white-containment-result"
    assert pack.NVS_NAMESPACE not in identity
    for wanted in (
        white.BUILD_TAG,
        white.CAMPAIGN_ID,
        white.CONTRACT_ID,
        white.DESCRIPTOR_ID,
        white.ACTION_ID,
        white.NVS_NAMESPACE,
    ):
        assert wanted in identity


def test_repo_anchored_artifacts_claims_and_describe_from_foreign_cwd(
    tmp_path: Path,
) -> None:
    assert once.FIRMWARE_BIN.is_absolute()
    assert once.FIRMWARE_ELF.is_absolute()
    assert "build-runtime-lut-partial-hold-endpoint-ab-v1" in str(once.FIRMWARE_BIN)
    assert "build-runtime-lut-partial-hold-repeat-ptlw-v3" not in str(once.FIRMWARE_BIN)
    assert once.base.runner.DEFAULT_CLAIMS == (
        ROOT
        / ".test-output"
        / "hardware"
        / ".mf1750_runtime_lut_ptlw_yend_ab_v1_claims"
    )
    assert once.base.runner.DEFAULT_OUTPUT == (
        ROOT
        / ".test-output"
        / "hardware"
        / "MF1750_RUNTIME_LUT_PTLW_YEND_AB_20260824_V1"
    )
    assert white_once.base.DEFAULT_CLAIMS == (
        ROOT
        / ".test-output"
        / "hardware"
        / ".mf1750_endpoint_ab_white_containment_v1_claims"
    )
    assert white_once.base.DEFAULT_OUTPUT == (
        ROOT
        / ".test-output"
        / "hardware"
        / "MF1750_ENDPOINT_AB_WHITE_CONTAINMENT_20260824_V1"
    )

    for script in (
        ROOT / "tools/mf1750_runtime_lut_partial_hold_endpoint_ab_v1_once.py",
        ROOT
        / "tools/mf1750_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_once.py",
    ):
        completed = subprocess.run(
            [sys.executable, str(script), "describe"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        if "hardware_accessed" in payload:
            assert payload["hardware_accessed"] is False
        assert all(
            item["verified"] is True
            for item in payload["artifact_binding_status"].values()
        )
