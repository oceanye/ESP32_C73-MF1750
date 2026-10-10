from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as pack


ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "platformio.runtime_lut_ptlw_fullframe_ab_v2.ini"
PROGRAM = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_program.inc"
CONFIG = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_main_config.inc"
IDENTITY = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_identity.inc"
QUALIFIER = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_qualifier.inc"
V1B_DRIVER = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc"
V2_DRIVER = ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v2_driver.inc"
ONCE = ROOT / "tools/mf1750_runtime_lut_ptlw_fullframe_ab_v2_once.py"
BUILD_DIR = (
    ROOT
    / ".pio/build-runtime-lut-ptlw-fullframe-ab-v2"
    / "ec5_runtime_lut_ptlw_fullframe_ab_v2"
)
BIN = BUILD_DIR / "firmware.bin"
ELF = BUILD_DIR / "firmware.elf"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def _python_literal(source: str, name: str) -> object:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing Python literal: {name}")


def test_01_isolated_build_selects_only_v2_sources_and_has_no_upload() -> None:
    ini = _text(INI)
    assert "default_envs = ec5_runtime_lut_ptlw_fullframe_ab_v2" in ini
    assert "build_dir = .pio/build-runtime-lut-ptlw-fullframe-ab-v2" in ini
    assert "-<*>" in ini
    assert "+<ec5_runtime_lut_ptlw_fullframe_ab_v2_epd_driver.cpp>" in ini
    assert "+<ec5_runtime_lut_ptlw_fullframe_ab_v2_main.cpp>" in ini
    assert "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_BUILD=1" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini
    assert "upload_port" not in ini
    assert "upload_protocol" not in ini


def test_02_pack_identity_nvs_and_all_action_ids_match_firmware_sources() -> None:
    report = pack.build_report()
    combined = _text(PROGRAM) + _text(CONFIG) + _text(IDENTITY)

    assert report["contract_id"] == pack.CONTRACT_ID
    assert tuple(item["descriptor_id"] for item in report["actions"]) == (
        pack.DESCRIPTOR_IDS
    )
    assert tuple(item["action_id"] for item in report["actions"]) == (
        pack.ACTION_IDS
    )
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.CONTRACT_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.DEVICE_API_VERSION,
        pack.IDENTITY_REVISION,
        *pack.DESCRIPTOR_IDS,
        *pack.ACTION_IDS,
    ):
        assert value in combined


def test_03_manifest_qualification_and_busy_contract_match_pack() -> None:
    program = _text(PROGRAM)
    config = _text(CONFIG)
    qualifier_contract = _slice(
        program,
        "String perActionQualificationContractJson()",
        "String busyAdmissionContractJson()",
    )
    busy_contract = _slice(
        program, "String busyAdmissionContractJson()", "String identityJson()"
    )

    assert pack.QUALIFIER_V2_BUNDLE_ID in config
    assert pack.PER_ACTION_READINESS_QUALIFICATION[
        "reset_count_including_final_posture_reset"
    ] == 5
    assert pack.PER_ACTION_READINESS_QUALIFICATION["revision_read_count"] == 4
    assert pack.PER_ACTION_READINESS_QUALIFICATION["all_samples_exact"] == [
        1,
        1,
        4,
    ]
    for token in (
        '"reset_count":5',
        '"revision_read_count":4',
        '"expected_revision_bytes":[1,1,4]',
        '"qualified_busy_stable_ms":50',
        '"failure_action_stage_command_counts_all_zero":true',
    ):
        assert token.replace('"', '\\"') in qualifier_contract
    for field in pack.BUSY_ADMISSION_CONTRACT["snapshot_fields"]:
        assert field in busy_contract
    assert [
        busy_contract.index('\\"ARM\\"'),
        busy_contract.index('\\"EXECUTE\\"'),
        busy_contract.index('\\"DISPATCH\\"'),
    ] == sorted(
        [
            busy_contract.index('\\"ARM\\"'),
            busy_contract.index('\\"EXECUTE\\"'),
            busy_contract.index('\\"DISPATCH\\"'),
        ]
    )


def test_04_frozen_bin_and_elf_match_runner_binding_and_embed_new_ids() -> None:
    once = _text(ONCE)
    expected_bin_bytes = _python_literal(once, "FIRMWARE_BIN_BYTES")
    expected_bin_sha = _python_literal(once, "FIRMWARE_BIN_SHA256")
    expected_elf_bytes = _python_literal(once, "FIRMWARE_ELF_BYTES")
    expected_elf_sha = _python_literal(once, "FIRMWARE_ELF_SHA256")

    assert expected_bin_bytes == 815_600
    assert expected_bin_sha == (
        "0433f67810caf2248a27c3296fbd2ae5004e34b326e6ca87c32714de932863c4"
    )
    assert expected_elf_bytes == 13_362_920
    assert expected_elf_sha == (
        "17abc695304d36a5536a5041ac52adde92643181d360d4e76b1d2d0822e59b85"
    )
    assert BIN.stat().st_size == expected_bin_bytes
    assert hashlib.sha256(BIN.read_bytes()).hexdigest() == expected_bin_sha
    assert ELF.stat().st_size == expected_elf_bytes
    elf = ELF.read_bytes()
    assert hashlib.sha256(elf).hexdigest() == expected_elf_sha
    for value in (
        pack.CONTRACT_ID,
        pack.QUALIFIER_V2_BUNDLE_ID,
        *pack.DESCRIPTOR_IDS,
        *pack.ACTION_IDS,
    ):
        assert value.encode("ascii") in elf


def test_05_elf_excludes_superseded_contract_and_action_identities() -> None:
    elf = ELF.read_bytes()
    superseded = (
        "277370737eabf62c55fd49021758ce3418f285e6254674aa8e0a4d8d4d451e42",
        pack.MECHANICAL_SOURCE_V1_CONTRACT_ID,
        pack.MECHANICAL_SOURCE_V1B_CONTRACT_ID,
        *pack.MECHANICAL_SOURCE_V1B_ACTION_IDS,
    )
    for value in superseded:
        assert value.encode("ascii") not in elf


def test_06_v2_visible_driver_is_mechanically_identical_to_sealed_v1b() -> None:
    v1b = _text(V1B_DRIVER).rstrip()
    v2 = (
        _text(V2_DRIVER)
        .replace(
            "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_BUILD",
            "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_BUILD",
        )
        .replace(
            "ec5_runtime_lut_ptlw_fullframe_ab_v2_identity.inc",
            "ec5_runtime_lut_ptlw_fullframe_ab_v1_identity.inc",
        )
        .replace(
            "mf1750_runtime_lut_ptlw_fullframe_ab_v2",
            "mf1750_runtime_lut_ptlw_fullframe_ab_v1",
        )
        .rstrip()
    )
    assert v2 == v1b


def test_07_busy_snapshot_struct_and_json_have_all_six_runtime_fields() -> None:
    program = _text(PROGRAM)
    struct = _slice(
        program,
        "struct FullframeBusyAdmissionGateEvidence",
        "struct FullframeBusyAdmissionEvidence",
    )
    json_body = _slice(
        program, "String fullframeBusyGateJson", "String fullframeBusyAdmissionJson"
    )
    cpp_fields = (
        "captured",
        "rawBusy",
        "allowed",
        "raw1Direct",
        "raw0SameBootPriorCompleteRamEligibilityUsed",
        "latePofSleepLowEligibleBeforeGate",
    )
    for field in cpp_fields:
        assert field in struct
        assert field in json_body
    for field in pack.BUSY_ADMISSION_CONTRACT["snapshot_fields"]:
        assert field in json_body


def test_08_busy_evidence_boots_strict_zero_and_resets_only_at_valid_arm() -> None:
    program = _text(PROGRAM)
    setup = program[program.index("void setup()") :]
    arm = _slice(program, "void handleArm()", "void handleExecute()")

    assert "uint8_t ordinal = 0;" in program
    assert "FullframeBusyAdmissionEvidence busyAdmissionEvidence;" in program
    assert "resetFullframeBusyAdmissionEvidence(nextOrdinal)" not in program
    assert "resetFullframeBusyAdmissionEvidence(" not in setup
    assert program.count(
        "resetFullframeBusyAdmissionEvidence(action->ordinal);"
    ) == 1
    assert arm.index("validateMutationContract") < arm.index(
        "resetFullframeBusyAdmissionEvidence(action->ordinal);"
    )


def test_09_arm_resets_then_atomically_captures_and_exposes_its_snapshot() -> None:
    program = _text(PROGRAM)
    arm = _slice(program, "void handleArm()", "void handleExecute()")
    capture = _slice(
        program,
        "bool fullframeBusyAdmissionAllowed",
        "#endif\n\nbool requestHasBodyOrArguments",
    )

    assert arm.index("resetFullframeBusyAdmissionEvidence(action->ordinal);") < (
        arm.index("FullframeBusyAdmissionGate::Arm")
    )
    assert arm.index("FullframeBusyAdmissionGate::Arm") < arm.index(
        "persistCursor(kPhaseArmed"
    )
    assert arm.index("persistCursor(kPhaseArmed") < arm.index(
        '\\"busy_admission\\":" + fullframeBusyAdmissionJson()'
    )
    assert capture.index("const int rawBusy = epdReadBusy();") < capture.index(
        "gate.captured = true;"
    )
    assert capture.index("const bool lateEligibleBeforeGate") < capture.index(
        "gate.latePofSleepLowEligibleBeforeGate = lateEligibleBeforeGate;"
    )


def test_10_execute_captures_second_gate_before_consuming_and_exposes_both() -> None:
    program = _text(PROGRAM)
    execute = _slice(program, "void handleExecute()", "void installRoutes()")

    assert execute.index("FullframeBusyAdmissionGate::Execute") < execute.index(
        "persistCursor(kPhaseConsumed"
    )
    assert execute.index("persistCursor(kPhaseConsumed") < execute.index(
        "executePending = true;"
    )
    assert execute.index("executePending = true;") < execute.index(
        '\\"busy_admission\\":" + fullframeBusyAdmissionJson()'
    )


def test_11_dispatch_records_snapshot_before_consuming_ram_eligibility() -> None:
    program = _text(PROGRAM)
    dispatch = _slice(program, "void executePendingAction()", "}  // namespace")

    gate = dispatch.index("FullframeBusyAdmissionGate::Dispatch")
    consume = dispatch.index("latePofSleepLowEligible = false;", gate)
    qualify = dispatch.index(
        "ec5FullframePtlwV2RunPerActionReadinessOnce(action->ordinal)", consume
    )
    assert gate < consume < qualify
    assert pack.BUSY_ADMISSION_CONTRACT[
        "dispatch_records_eligibility_before_consuming_it"
    ] is True


def test_12_fresh_ordinal1_is_raw1_only_at_every_device_gate() -> None:
    program = _text(PROGRAM)
    admission = _slice(
        program,
        "bool fullframeBusyAdmissionAllowed",
        "#endif\n\nbool requestHasBodyOrArguments",
    )
    consistency = _slice(
        program,
        "bool fullframeBusyGateAllowedConsistently",
        "bool fullframeDriverEstablishesLatePofSleepLow",
    )

    assert "action.ordinal == 1 && !raw1Direct" in admission
    assert "gate.allowed = false;" in admission
    assert "rawBusy == 1" in admission
    assert "ordinal != 1U ||" in consistency
    assert "!gate.latePofSleepLowEligibleBeforeGate" in consistency
    assert pack.BUSY_ADMISSION_CONTRACT[
        "fresh_ordinal_1_requires_raw1_at_all_three_gates"
    ] is True
    assert pack.BUSY_ADMISSION_CONTRACT[
        "fresh_ordinal_1_raw0_eligibility_forbidden"
    ] is True


def test_13_later_raw0_requires_same_boot_prior_complete_ram_eligibility() -> None:
    program = _text(PROGRAM)
    admission = _slice(
        program,
        "bool fullframeBusyAdmissionAllowed",
        "#endif\n\nbool requestHasBodyOrArguments",
    )
    for token in (
        "rawBusy == 0",
        "action.ordinal == nextOrdinal",
        "action.ordinal > 1",
        "lateEligibleBeforeGate",
        "totalDriverCallCount + 1U == action.ordinal",
    ):
        assert token in admission
    assert "gate.allowed = raw1Direct || raw0EligibilityUsed;" in admission
    assert pack.BUSY_ADMISSION_CONTRACT[
        "later_raw0_requires_same_boot_prior_complete_ram_eligibility"
    ] is True


def test_14_late_eligibility_binds_all_three_allowed_xor_snapshots() -> None:
    program = _text(PROGRAM)
    consistency = _slice(
        program,
        "bool fullframeBusyGateAllowedConsistently",
        "bool fullframeDriverEstablishesLatePofSleepLow",
    )
    establish = _slice(
        program,
        "bool fullframeDriverEstablishesLatePofSleepLow",
        "bool fullframeBusyAdmissionAllowed",
    )

    assert "gate.raw1Direct ==" in consistency
    assert "gate.raw0SameBootPriorCompleteRamEligibilityUsed" in consistency
    assert "ordinal > 1U && gate.rawBusy == 0" in consistency
    assert "busyAdmissionEvidence.ordinal == completedOrdinal" in establish
    for gate in ("arm", "execute", "dispatch"):
        assert (
            f"fullframeBusyGateAllowedConsistently(busyAdmissionEvidence.{gate}"
            in establish
        )


def test_15_qualifier_is_exact_four_revision_five_reset_high50_gate() -> None:
    qualifier = _text(QUALIFIER)
    run = _slice(
        qualifier,
        "bool ec5FullframePtlwV2RunPerActionReadinessOnce",
        "const Ec5FullframePtlwV2ReadinessReport &",
    )

    assert run.count("ffabV2ReadRevisionAfterOwnReset(false)") == 2
    assert run.count("ffabV2ReadRevisionAfterOwnReset(true)") == 2
    assert run.count("ffabV2Exact010104(") == 4
    assert "ffabV2Readiness.resetCount == 5U" in run
    assert "ffabV2Readiness.allRevisionSamplesExact010104" in run
    assert "FFABV2_STABLE_HIGH_MS" in run
    assert "ffabV2Readiness.finalBusy == 1U" in run
    assert "ffabV2Readiness.finalRst == 1U" in run
    assert "ffabV2Readiness.finalCs1 == 1U" in run
    assert "ffabV2Readiness.finalCs2 == 1U" in run


def test_16_consumed_then_qualifier_runs_once_before_driver_or_action_payload() -> None:
    program = _text(PROGRAM)
    execute = _slice(program, "void handleExecute()", "void installRoutes()")
    dispatch = _slice(program, "void executePendingAction()", "}  // namespace")

    assert execute.index("persistCursor(kPhaseConsumed") < execute.index(
        "qualificationPending = true;"
    )
    qualification_call = dispatch.index(
        "ec5FullframePtlwV2RunPerActionReadinessOnce(action->ordinal)"
    )
    exact_gate = dispatch.index("exactPerActionReadinessSuccess", qualification_call)
    driver_increment = dispatch.index("++driverCallCountForAction;", exact_gate)
    driver_call = dispatch.index("epdDisplayCompiled", driver_increment)
    assert qualification_call < exact_gate < driver_increment < driver_call
    assert dispatch.index("++qualificationCallCountForAction;") < qualification_call
    assert dispatch.index("++totalQualificationCallCount;") < qualification_call


def test_17_qualification_failure_faults_with_zero_action_stage_and_driver_counts() -> None:
    program = _text(PROGRAM)
    dispatch = _slice(program, "void executePendingAction()", "}  // namespace")
    fault_report = _slice(program, "void publishFaultReport", "void enterFault")

    failed_gate = dispatch.index("if (!qualificationResult")
    fault = dispatch.index(
        'enterFault("per_action_readiness_qualification_failed"', failed_gate
    )
    driver_increment = dispatch.index("++driverCallCountForAction;", failed_gate)
    assert failed_gate < fault < driver_increment
    assert '"driver_call_count_for_action\":" +' not in fault_report
    assert "String(driverCalled ? driverCallCountForAction : 0)" in fault_report
    for token in (
        '\\"pon\\":0',
        '\\"pof\\":0',
        '\\"drf\\":0',
        '\\"dtm_bytes\\":0',
        '\\"lut_bytes\\":0',
        '\\"ptlw_writes\\":0',
        '\\"command_0x86\\":0',
        '\\"visible_refresh_requests\\":0',
    ):
        assert token in fault_report


def test_18_all_required_surfaces_expose_busy_readiness_and_action_counts() -> None:
    program = _text(PROGRAM)
    status = _slice(program, "String statusJson()", "String driverEvidenceJson")
    no_execute = _slice(
        program, "void publishNoExecuteReport()", "void publishFaultReport"
    )
    fault = _slice(program, "void publishFaultReport", "void enterFault")
    arm = _slice(program, "void handleArm()", "void handleExecute()")
    execute = _slice(program, "void handleExecute()", "void installRoutes()")
    complete = _slice(
        program,
        "publishedReport =\n      String(\"{\\\"schema_version\\\":3,\\\"kind\\\":\\\"\")",
        "restartHttpListenerAfterBlockingPanelIo();\n}",
    )

    for surface in (status, no_execute, fault, arm, execute, complete):
        assert "fullframeBusyAdmissionJson()" in surface
    for surface in (status, no_execute, fault, complete):
        assert "ec5FullframePtlwV2ReadinessJson()" in surface
    assert "successfulActionStageCommandCountsJson(*action)" in complete
    assert '\\"qualification_called\\\":true' in complete
    assert '\\"qualification_called\\\":' in fault
    assert '\\"qualification_readiness_entry_busy_is_independent\\\":true' in (
        _slice(
            program,
            "String busyAdmissionContractJson()",
            "String identityJson()",
        )
    )
