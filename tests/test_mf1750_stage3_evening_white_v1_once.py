from __future__ import annotations

from pathlib import Path

from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools import mf1750_stage3_evening_white_v1_once as subject
from tools import mf1750_stage3_wf23_white_once as base


def test_describe_is_offline_fresh_and_exactly_bound() -> None:
    value = subject.describe()
    assert value["kind"] == "mf1750-stage3-evening-white-v1-facade"
    assert value["hardware_action_id"] == subject.ACTION_ID
    assert value["nvs_namespace"] == subject.NVS_NAMESPACE
    assert value["firmware_binary_sha256"] == subject.FIRMWARE_BIN_SHA256
    assert value["firmware_binary_bytes"] == subject.FIRMWARE_BIN_BYTES
    assert value["fresh_nvs_namespace"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0


def test_only_recovery_binding_is_replaced() -> None:
    with subject._binding_override():  # noqa: SLF001
        context = base.load_context()
    original = physical.load_release(base.BASE_RELEASE)
    assert context.action(1) == original.action(1)
    assert context.binding(1) == original.binding(1)
    assert context.action(2)["hardware_action_id"] == subject.ACTION_ID
    assert context.binding(2)["nvs_namespace"] == subject.NVS_NAMESPACE
    assert context.binding(2)["firmware_binary_sha256"] == subject.FIRMWARE_BIN_SHA256


def test_override_restores_base_constants() -> None:
    original = base.ACTION_ID
    with subject._binding_override():  # noqa: SLF001
        assert base.ACTION_ID == subject.ACTION_ID
        assert base.FIRMWARE_BIN == subject.FIRMWARE_BIN
    assert base.ACTION_ID == original
    assert base.ACTION_ID != subject.ACTION_ID


def test_compiled_artifacts_match_exact_sizes() -> None:
    assert Path(subject.FIRMWARE_BIN).stat().st_size == subject.FIRMWARE_BIN_BYTES
    assert Path(subject.FIRMWARE_ELF).stat().st_size == subject.FIRMWARE_ELF_BYTES
    assert base._sha_file(subject.FIRMWARE_BIN) == subject.FIRMWARE_BIN_SHA256  # noqa: SLF001
    assert base._sha_file(subject.FIRMWARE_ELF) == subject.FIRMWARE_ELF_SHA256  # noqa: SLF001


def test_source_contains_fresh_identity_and_no_startup_refresh() -> None:
    source = Path("src/ec5_stage3_wf23_white_recovery_main.cpp").read_text(
        encoding="utf-8"
    )
    config = Path("platformio.stage3_evening_white_v1.ini").read_text(encoding="utf-8")
    assert subject.BUILD_TAG in source
    assert subject.NVS_NAMESPACE in source
    assert subject.ACTION_ID in source
    assert "EPD_ENABLE_TEST_PATTERN=0" in config
    assert "MF1750_OTP_WHITE_FOR_STAGE3_EVENING_20260823=1" in config
    setup = source[source.index("void setup()") : source.index("void loop()")]
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery" not in setup
