from __future__ import annotations

import re
from pathlib import Path

from tools import mf1750_ec5_u07t_identity as identity


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src" / "ec5_u07t_main.cpp"
PLATFORMIO_PATH = ROOT / "platformio.u07t.ini"


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def test_u07t_identity_literals_match_the_frozen_host_source() -> None:
    source = _source()
    variant = identity.variant()
    expected = {
        "kClassification": variant["classification"],
        "kIdentityRevision": variant["identity_revision"],
        "kDeviceApiVersion": variant["device_api_version"],
        "kLayoutId": variant["layout_id"],
        "kBuildTag": variant["build_tag"],
        "kTestId": variant["test_id"],
        "kActionId": variant["action_id"],
        "kFrameSha256": variant["frame_sha256"],
        "kDtmSha256": variant["dtm_sha256"],
        "kFormalNamespace": identity.FORMAL_NVS_NAMESPACE,
        "kFormalU04Key": identity.FORMAL_U04_NVS_KEY,
        "kFormalU07Key": identity.FORMAL_U07_NVS_KEY,
        "kTechnicalNamespace": identity.ACTIVE_NVS_NAMESPACE,
        "kTechnicalKey": identity.ACTIVE_NVS_KEY,
    }
    for name, value in expected.items():
        assert _literal(source, name) == value

    assert identity.action_id() == identity.FROZEN_ACTION_ID
    assert identity.FROZEN_ACTION_ID in source
    assert "d1874fb778b7af16a8e2c89687987d187e0fbed3a6ee279c966d427e633969a9" not in source


def test_formal_corrected_v2_namespace_is_strictly_read_only() -> None:
    source = _source()
    assert "formalV2Store.begin(kFormalNamespace, true /* readOnly */)" in source
    assert "formalV2Store.begin(kFormalNamespace, false" not in source
    for mutation in ("put", "remove", "clear", "end"):
        assert f"formalV2Store.{mutation}" not in source

    assert "formalV2Store.isKey(kFormalU04Key)" in source
    assert "formalV2Store.getUChar(kFormalU04Key, kVirgin)" in source
    assert "formalV2Store.isKey(kFormalU07Key)" in source
    assert "formalV2Store.getUChar(kFormalU07Key, kVirgin)" in source
    assert "formalU04KeyPresent &&" in source
    assert "formalU04Phase == kConsumed" in source
    assert "!formalU07KeyPresent &&" in source
    assert "formalU07Phase == kVirgin" in source


def test_only_independent_technical_key_can_be_written() -> None:
    source = _source()
    writes = re.findall(r"([A-Za-z0-9_]+)\.putUChar\(([^,]+),", source)
    assert writes == [("technicalClaimStore", "kTechnicalKey")]
    assert "technicalClaimStore.begin(kTechnicalNamespace, false /* readOnly */)" in source
    assert 'kTechnicalNamespace = "mf1750_ec5t"' in source
    assert 'kTechnicalKey = "u07t_phase"' in source
    assert 'kFormalU07Key = "u07v2_phase"' in source
    assert "formal_u07_not_virgin" in source
    assert "formal_u07_action_consumed_by_firmware" not in source
    assert "formal_u07_action_consumed\\\":false" not in source
    assert "formal_u07_unclaimed_and_virgin" in source
    assert '(formalU07Match ? "true" : "false")' in source
    assert identity.FORMAL_U07_ACTION_ID not in source
    assert identity.FORMAL_CLAIM_REGISTRY_ID not in source
    assert identity.TECHNICAL_CLAIM_REGISTRY_ID not in source


def test_formal_mismatch_and_runtime_readback_faults_do_not_persist() -> None:
    source = _source()
    read_only_fault = source[
        source.index("void enterReadOnlyFault") : source.index("void enterPersistentFault")
    ]
    assert "persistTechnicalPhase" not in read_only_fault
    assert "formal_u04_not_consumed" in source
    assert "formal_u07_not_virgin" in source
    assert 'enterReadOnlyFault("runtime_nvs_readback_failed")' in source
    assert "rejectNvsMismatch" in source
    assert "enterReadOnlyFault(error);" in source[
        source.index("void rejectNvsMismatch") : source.index("void handleArm")
    ]


def test_fixture_is_fixed_white_backed_mirrored_u07_without_ingress() -> None:
    source = _source()
    assert "MF1750_UNKNOWN_PROBE_CODE != 7" in source
    assert "epdValidateCompiledUnknownProbeFixture()" in source
    assert "epdDisplayCompiledUnknownProbe()" in source
    assert "epdDisplayFrame(" not in source
    assert "server.upload" not in source
    assert "HTTP_PUT" not in source
    assert "candidate_pixels\\\":8192" in source
    assert "known_white_pixels\\\":606208" in source
    assert "raw_frame_ingress\\\":false" in source
    assert "startup_refresh\\\":false" in source
    assert "dither\\\":false" in source
    assert "spatial_mixing\\\":false" in source
    assert "lut_modified\\\":false" in source
    assert "no_retry\\\":true" in source
    assert "no_recovery\\\":true" in source


def test_boot_has_no_visible_refresh_and_action_calls_driver_once() -> None:
    source = _source()
    setup = source[source.index("void setup()") : source.index("void loop()")]
    assert "epdDisplayCompiledUnknownProbe" not in setup
    assert "epdClear" not in setup
    assert source.count("const bool result = epdDisplayCompiledUnknownProbe();") == 1
    assert "driverCallCount != 0" in source
    assert "persistTechnicalPhase(kConsumed)" in source
    assert source.index("persistTechnicalPhase(kConsumed)") < source.index(
        "executePending = true"
    )


def test_every_get_and_report_shape_exposes_formal_nvs_evidence() -> None:
    source = _source()
    for function in (
        "String versionJson()",
        "String manifestJson()",
        "String statusJson()",
        "void publishNoExecuteReport()",
        "void publishRejectedMutation(const char *error)",
    ):
        start = source.index(function)
        next_function = source.find("\n}\n", start)
        block = source[start : next_function + 3]
        assert "nvsContractJson()" in block
        assert "nvsEvidenceJson()" in block
    terminal = source[source.index("void executePendingTechnicalProbe()") :]
    assert "nvsContractJson()" in terminal
    assert "nvsEvidenceJson()" in terminal
    assert "formal_u04_key_present" in source
    assert "formal_u04_phase" in source
    assert "formal_u07_key_present" in source
    assert "formal_u07_phase" in source


def test_driver_evidence_is_typed_schema_two() -> None:
    source = _source()
    required = (
        '"driver_evidence_schema_version\\\":2',
        '"failure_stage\\\":\\\"',
        '"failure_code\\\":',
        '"free_psram_before\\\":',
        '"largest_psram_block_before\\\":',
        '"input_fnv1a\\\":',
        '"cs1_dtm_fnv1a\\\":',
        '"cs2_dtm_fnv1a\\\":',
        '"safe_finish\\\":',
    )
    for token in required:
        assert token in source


def test_dedicated_platformio_environment_contract() -> None:
    platformio = PLATFORMIO_PATH.read_text(encoding="utf-8")
    section = "[env:esp32-s3-devkitc-1-ec5-u07t]"
    assert section in platformio
    block = platformio[platformio.index(section) :]
    next_section = block.find("\n[", 1)
    if next_section >= 0:
        block = block[:next_section]
    assert "+<epd_driver.cpp>" in block
    assert "+<ec5_u07t_main.cpp>" in block
    assert "-<ec5_unknown_probe_main.cpp>" in block
    assert "-<ec5_u04_u05_compare_main.cpp>" in block
    assert "-<main.cpp>" in block
    assert "MF1750_ENABLE_U07T_TECHNICAL=1" in block
    assert "MF1750_ENABLE_UNKNOWN_PROBE=1" in block
    assert "MF1750_UNKNOWN_PROBE_CODE=7" in block
