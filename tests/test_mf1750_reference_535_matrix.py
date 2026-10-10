from __future__ import annotations

import hashlib
from pathlib import Path
import re

import pytest

from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools import mf1750_pure_field_matrix_once as runner
from tools import mf1750_reference_535_matrix_pack as pack
from tools import mf1750_spd1657_legacy_reference_include as generator


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".test-output/offline/MF1750_STAGE3_REFERENCE_535_MATRIX_20260822_V10/release.json"


def _array(text: str, namespace: str, name: str, size: int) -> bytes:
    scope = re.search(rf"namespace {namespace} \{{(.*?)\n\}}  // namespace {namespace}", text, re.DOTALL)
    assert scope is not None
    match = re.search(rf"{name}\[{size}\] = \{{(.*?)\n\}};", scope.group(1), re.DOTALL)
    assert match is not None
    return bytes(int(value, 16) for value in re.findall(r"0x([0-9A-F]{2})", match.group(1)))


def test_generated_include_is_exact_and_reproducible() -> None:
    include = ROOT / "src/generated/spd1657_legacy_535_reference.inc"
    assert include.read_bytes() == generator.render()
    assert hashlib.sha256(include.read_bytes()).hexdigest() == (
        "cb40342fb212e232d1cfe789f60ccba9823bb0e35148f5cf916681e0c8991881"
    )
    text = include.read_text(encoding="utf-8")
    active = _array(text, "active", "kR20Payload", 799)
    commented = _array(text, "commented", "kR20Payload", 799)
    assert hashlib.sha256(active[:535]).hexdigest() == (
        "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
    )
    assert hashlib.sha256(commented[:535]).hexdigest() == (
        "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"
    )
    assert active[535:] == bytes([0xFF]) * 264
    assert commented[535:] == bytes([0xFF]) * 264
    assert _array(text, "active", "kR21Payload", 704) == bytes([0xFF]) * 704
    assert _array(text, "commented", "kR21Payload", 704) == bytes([0xFF]) * 704


def test_reference_config_has_two_treatments_and_two_recoveries() -> None:
    ini = (ROOT / "platformio.reference_535_matrix.ini").read_text(encoding="utf-8")
    environments = re.findall(r"^\[env:(ec5_pfm_[^]]+)\]$", ini, re.MULTILINE)
    assert environments == [
        "ec5_pfm_lga",
        "ec5_pfm_lga_white",
        "ec5_pfm_lgc",
        "ec5_pfm_lgc_white",
    ]
    assert "MF1750_PURE_FIELD_LAYOUT=0" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini


def test_release_binds_32_endpoints_and_reference_evidence() -> None:
    value = pack.validate_release(RELEASE)
    assert value["candidate_order"] == ["L535_ACTIVE_GLOBAL", "L535_COMMENTED_GLOBAL"]
    assert value["candidate_count"] == 2
    assert value["total_endpoint_observations"] == 32
    assert value["maximum_planned_refresh_count"] == 4
    assert value["reference_evidence"]["record_splicing"] is False
    assert value["reference_evidence"]["codes_8_through_15"] is False
    assert value["fixed_safety_axes"]["unknown_commands"] is False
    assert value["fixed_safety_axes"]["automatic_chaining"] is False


def test_shared_runner_describes_reference_release_and_loads_both_contexts() -> None:
    value = runner.describe(RELEASE)
    assert value["treatment_screens"] == 2
    assert value["white_recoveries"] == 2
    assert value["total_endpoint_observations"] == 32
    release, candidates = runner._release(RELEASE)  # noqa: SLF001
    for candidate in candidates.values():
        context = runner.load_context(release, candidate, RELEASE)
        assert context.action(1)["role"] == "PURE_FIELD_UNIFORM_CODE_ATLAS"
        assert context.action(2)["role"] == "FACTORY_OTP_WHITE_RECOVERY"
        assert context.root["profile_contract"]["vendor_filename_numeric_tokens"] == [
            -128,
            127,
        ]
        assert context.binding(1)["arm_intent"] == (
            "ARM_ONE_FIXED_PURE_FIELD_CANDIDATE_NOT_HARDWARE_AUTHORIZATION"
        )
        assert context.binding(1)["execute_intent"] == (
            "EXECUTE_ONE_FIXED_PURE_FIELD_CANDIDATE_ONCE"
        )
        assert context.binding(2)["arm_intent"] == (
            "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
        )
        assert context.binding(2)["execute_intent"] == (
            "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"
        )
        assert context.binding(1)["frame_fnv1a"] == 0x52FA55C5
        assert context.binding(1)["cs1_dtm_fnv1a"] == 0x8935B9C5
        assert context.binding(1)["cs2_dtm_fnv1a"] == 0xD36139C5
        assert context.binding(2)["frame_fnv1a"] == 0x13340DC5


def test_reference_live_version_override_accepts_exact_legacy_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, candidates = runner._release(RELEASE)  # noqa: SLF001
    candidate = candidates["L535_ACTIVE_GLOBAL"]
    observed: list[tuple[dict, int]] = []

    def original(value, _context, ordinal: int) -> None:
        observed.append((value, ordinal))

    monkeypatch.setattr(physical, "_expect_version", original)
    with runner._physical_overrides(candidate, release):  # noqa: SLF001
        physical._expect_version(  # noqa: SLF001
            {
                "profile": {
                    "compiled_profile_count": 2,
                    "global_header_profile": "LEGACY_ACTIVE_535",
                    "cs1_r20_profile": "LEGACY_ACTIVE_535",
                    "cs2_r20_profile": "LEGACY_COMMENTED_535",
                }
            },
            object(),
            1,
        )
    assert observed[0][0]["profile"]["compiled_profile_count"] == 1
    assert observed[0][1] == 1


def test_reference_live_version_override_rejects_old_dual_r20_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, candidates = runner._release(RELEASE)  # noqa: SLF001
    candidate = candidates["L535_ACTIVE_GLOBAL"]
    monkeypatch.setattr(physical, "_expect_version", lambda *_args: None)
    with runner._physical_overrides(candidate, release):  # noqa: SLF001
        with pytest.raises(physical.PhysicalOnceError, match="mapping differs"):
            physical._expect_version(  # noqa: SLF001
                {
                    "profile": {
                        "compiled_profile_count": 2,
                        "global_header_profile": "LEGACY_ACTIVE_535",
                        "cs1_r20_profile": "WF20_25",
                        "cs2_r20_profile": "WF23_25",
                    }
                },
                object(),
                1,
            )


def test_reference_terminal_driver_uses_pure_field_fnv_bindings() -> None:
    release, candidates = runner._release(RELEASE)  # noqa: SLF001
    context = runner.load_context(release, candidates["L535_ACTIVE_GLOBAL"], RELEASE)
    driver = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "pre_command_idle_failure": False,
        "input_fnv1a": 0x52FA55C5,
        "cs1_dtm_fnv1a": 0x8935B9C5,
        "cs2_dtm_fnv1a": 0xD36139C5,
        "busy_trace": {
            "idle_level": 1,
            "post_psr": {"pre_command_idle_ok": True, "wait_exit_level": 1},
            "safe_finish": {"busy_after_pins_low": 1, "busy_after_5ms": 1},
            "final_gpio": {
                "busy": 1,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        },
    }
    with runner._physical_overrides(candidates["L535_ACTIVE_GLOBAL"], release):  # noqa: SLF001
        physical._expect_terminal_driver(driver, context, 1)  # noqa: SLF001
