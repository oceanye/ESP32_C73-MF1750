from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from tools import mf1750_power_qualifier_pon_pof_no_drf_v2_pack as pack
from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as v1_pack
from tools import mf1750_power_qualifier_pon_pof_no_drf_v2_once as once


ROOT = Path(__file__).resolve().parents[1]
V1_DRIVER = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v1_driver.cpp"
DRIVER = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v2_driver.cpp"
HEADER = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v2.h"
MAIN = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v2_main.cpp"
INI = ROOT / "platformio.power_qualifier_pon_pof_no_drf_v2.ini"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def _firmware_manifest() -> dict[str, object]:
    source = _text(MAIN)

    def constant(name: str) -> str:
        match = re.search(
            rf"static constexpr char {name}\[\]\s*=\s*"
            rf'((?:\s*"(?:\\.|[^"\\])*"\s*)+);',
            source,
        )
        assert match is not None, name
        return "".join(
            ast.literal_eval(token)
            for token in re.findall(r'"(?:\\.|[^"\\])*"', match.group(1))
        )

    identity = ",".join(
        f'"{field}":"{constant(name)}"'
        for field, name in (
            ("build_tag", "kBuildTag"),
            ("test_id", "kTestId"),
            ("campaign_id", "kCampaignId"),
            ("contract_id", "kContractId"),
            ("descriptor_id", "kDescriptorId"),
            ("action_id", "kActionId"),
            ("device_api_version", "kDeviceApiVersion"),
            ("identity_revision", "kIdentityRevision"),
            ("classification", "kClassification"),
        )
    )
    action = json.dumps(pack.build_report()["actions"][0], separators=(",", ":"))
    values = {
        "identityJson()": identity,
        "actionJson()": action,
        "kNvsNamespace": constant("kNvsNamespace"),
        "kNvsKey": constant("kNvsKey"),
    }
    body = _slice(source, "String manifestJson()", "String statusJson()")
    expression = body[body.index("return ") + len("return ") : body.rindex(";")]
    output: list[str] = []
    for token in re.findall(
        r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*\(\)|[A-Za-z_]\w*|[()+]',
        expression,
    ):
        if token.startswith('"'):
            output.append(ast.literal_eval(token))
        elif token in values:
            output.append(values[token])
        else:
            assert token in {"String", "(", ")", "+"}, token
    value = json.loads("".join(output))
    assert isinstance(value, dict)
    return value


def test_isolated_build_compiles_only_v2_sources() -> None:
    ini = _text(INI)
    assert "default_envs = ec5_power_qualifier_pon_pof_no_drf_v2" in ini
    assert "-<*>" in ini
    assert "+<ec5_power_qualifier_pon_pof_no_drf_v2_driver.cpp>" in ini
    assert "+<ec5_power_qualifier_pon_pof_no_drf_v2_main.cpp>" in ini
    assert "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_BUILD=1" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini


def test_v2_identity_and_fresh_nvs_are_pack_bound() -> None:
    main = _text(MAIN)
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.CONTRACT_ID,
        pack.DESCRIPTOR_ID,
        pack.ACTION_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.DEVICE_API_VERSION,
        pack.IDENTITY_REVISION,
    ):
        assert value in main
    assert "epdponpof_v1" not in main
    assert "cursor_pp1" not in main
    action_json = _slice(main, "String actionJson()", "String gpioJson()")
    assert '\\"prior_static_action_id\\":' in action_json
    assert f'\\"{v1_pack.ACTION_ID}\\",' in action_json
    assert '\\"prior_static_action_id\\":null' not in action_json


def test_actual_firmware_manifest_parses_and_matches_host_validator() -> None:
    manifest = _firmware_manifest()
    once._validate_manifest(manifest)
    assert manifest["actions"] == pack.build_report()["actions"]


def test_each_revision_sample_has_own_reset_and_final_reset_is_fifth() -> None:
    driver = _text(DRIVER)
    read = _slice(
        driver,
        "Ec5PowerQualifierV2RevisionSample readRevisionAfterOwnReset",
        "bool equalRevision",
    )
    readiness = _slice(
        driver,
        "bool ec5PowerQualifierV2RunReadinessOnce()",
        "bool ec5PowerQualifierV2RunPonPofOnce()",
    )
    assert read.count("resetControllers();") == 1
    assert read.index("selectControllers(false, false);") < read.index(
        "resetControllers();"
    )
    assert read.index("resetControllers();") < read.index(
        "selectControllers(!secondController, secondController);"
    )
    assert readiness.count("readRevisionAfterOwnReset(false)") == 2
    assert readiness.count("readRevisionAfterOwnReset(true)") == 2
    assert readiness.count("resetControllers();") == 1
    assert "readinessReport.resetCount == 5U" in readiness
    assert "waitStableHigh(kReadinessHighStableMs" in readiness
    assert "readinessReport.finalRst == 1U" in readiness
    assert "readinessReport.finalCs1 == 1U" in readiness
    assert "readinessReport.finalCs2 == 1U" in readiness


def test_all_four_raw_samples_must_equal_010104_before_probe() -> None:
    driver = _text(DRIVER)
    exact = _slice(driver, "bool exactRevision010104", "bool initializePowerRegisters")
    readiness = _slice(
        driver,
        "bool ec5PowerQualifierV2RunReadinessOnce()",
        "bool ec5PowerQualifierV2RunPonPofOnce()",
    )
    for token in ("bytes[0] == 0x01", "bytes[1] == 0x01", "bytes[2] == 0x04"):
        assert token in exact
    assert readiness.count("exactRevision010104(") == 4
    assert "readinessReport.allRevisionSamplesExact010104" in readiness
    assert "cs1_revision_not_010104" in readiness
    assert "cs2_revision_not_010104" in readiness
    assert "all_revision_samples_exact_010104" in driver


def test_v2_changes_reset_dimension_not_v1_spi_framing_or_timing() -> None:
    v1 = _text(V1_DRIVER)
    v2 = _text(DRIVER)
    for start, end in (
        ("void bitBangWrite8", "uint8_t bitBangRead8"),
        ("uint8_t bitBangRead8", "bool beginRevisionSession"),
    ):
        v1_block = _slice(v1, start, end)
        v2_end = "bool prepareRevisionSession" if end == "bool beginRevisionSession" else end
        v2_block = _slice(v2, start, v2_end)
        assert v2_block == v1_block
    main = _text(MAIN)
    for token in (
        "PER_SAMPLE_RESET_ONLY",
        "exact_historical_transaction_reproduction\\\":false",
        "legacy_mosi_high_before_reset_restored\\\":false",
        "legacy_post_reset_tail_2us_restored\\\":false",
        "segmented_cs_framing_changed\\\":false",
        "STOP_BEFORE_PON_AND_CREATE_FRESH_V3",
    ):
        assert token in main


def test_probe_remains_v1_exact_and_has_no_visible_command() -> None:
    v1 = _text(V1_DRIVER)
    v2 = _text(DRIVER)
    v1_probe = _slice(
        v1,
        "bool ec5PowerQualifierRunPonPofOnce()",
        "const Ec5PowerQualifierReadinessReport &ec5PowerQualifierReadinessReport()",
    )
    v2_probe = _slice(
        v2,
        "bool ec5PowerQualifierV2RunPonPofOnce()",
        "const Ec5PowerQualifierV2ReadinessReport &ec5PowerQualifierV2ReadinessReport()",
    )
    normalized = v2_probe.replace("ec5PowerQualifierV2", "ec5PowerQualifier").replace(
        "Ec5PowerQualifierV2", "Ec5PowerQualifier"
    )
    assert normalized == v1_probe
    enum_body = _slice(v2, "enum : uint8_t {", "};")
    for literal in ("0x10", "0x11", "0x12", "0x13", "0x20", "0x21", "0x83", "0x86"):
        assert literal not in enum_body
        assert f"command({literal})" not in v2
    calls = re.findall(r"command\((kCmd\w+)\)", v2)
    assert set(calls) == {
        "kCmdVendorUnlock", "kCmdPowerSetting", "kCmdPanelSetting",
        "kCmdBoosterSoftStart1", "kCmdBoosterSoftStart3",
        "kCmdBoosterSoftStart2", "kCmdPowerOffSequence", "kCmdTcon",
        "kCmdPll", "kCmdVcomInterval", "kCmdResolution",
        "kCmdPowerSaving", "kCmdTvdcs", "kCmdCascade", "kCmdPowerOn",
        "kCmdPowerOff",
    }


def test_main_keeps_one_shot_nonce_and_persistent_fail_closed_contract() -> None:
    main = _text(MAIN)
    setup = _slice(main, "void setup()", "void loop()")
    assert "ec5PowerQualifierV2RunReadinessOnce" not in setup
    assert "ec5PowerQualifierV2RunPonPofOnce" not in setup
    assert "putUChar(kNvsKey, kFresh)" not in setup
    assert "X-EC5-Qualification-Nonce" in main
    assert "exactHeader(kQualificationNonceHeader, qualificationNonce())" in main
    assert main.index("persistPhase(kQualifyConsumed)") < main.index(
        "qualifyPending = true"
    )
    assert main.index("persistPhase(kProbeConsumed)") < main.index(
        "probePending = true"
    )
    assert "ec5PowerQualifierV2ForceSafeHold();" in _slice(
        main, "void enterFault", "void rejectMutation"
    )
