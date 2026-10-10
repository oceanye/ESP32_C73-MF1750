from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_ec5_u07t_identity as identity
from tools import mf1750_ec5_u07t_physical_once as runner
from tools import mf1750_ec5_u07t_release as release


def _context(tmp_path: Path) -> runner.ReleaseContext:
    formal = tmp_path / "formal"
    formal.mkdir()
    manifest = tmp_path / "release-manifest.json"
    firmware = tmp_path / "firmware-u07t.bin"
    elf = tmp_path / "firmware-u07t.elf"
    manifest.write_text("{}")
    firmware.write_bytes(b"firmware")
    elf.write_bytes(b"elf")
    panel = {
        "model": "MF1750-C73",
        "serial": "test-panel",
        "board_id": "ESP32-C73",
        "pcb_revision": "rev-a1",
    }
    return runner.ReleaseContext(
        release_file=manifest,
        root={
            "prerequisite_inputs": {"formal_claim_registry": str(formal)},
            "compiled_identity_report": {"valid": True},
        },
        panel=panel,
        binary_path=firmware,
        binary_sha256="1" * 64,
        elf_path=elf,
        elf_sha256="2" * 64,
        release_canonical_sha256="3" * 64,
    )


def test_authorization_is_independent_technical_action() -> None:
    assert runner.required_authorization() == (
        "AUTHORIZE_ONE_VISIBLE_EC5_U07T_TECHNICAL__ACTION_"
        "303BB39E496F39CAEF782AADACB0D63E6D4F9B42DF550D4C799A4248A8041310"
        "__NO_RETRY_NO_RECOVERY"
    )
    assert identity.FORMAL_U07_ACTION_ID.upper() not in (
        runner.required_authorization()
    )


def test_release_contract_requires_immediate_white_predecessor() -> None:
    assert release.DEVICE_CONTRACT[
        "after_u04_white_must_be_immediate_visible_predecessor"
    ] is True
    assert release.DEVICE_CONTRACT["no_intervening_visible_refresh_required"] is True
    assert release.DEVICE_CONTRACT[
        "initial_white_attestation_required_before_claim"
    ] is True
    assert release.SAFETY["formal_u07_qualification_inferred"] is False
    assert release.SAFETY["post_action_screen_remains_u07t_until_separate_recovery"] is True


def test_initial_white_attestation_is_exact_and_sealed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    evidence = tmp_path / "initial.json"
    unsigned = {
        "schema_version": 1,
        "kind": runner.INITIAL_STATE_KIND,
        "classification": runner.CLASSIFICATION,
        "panel": dict(context.panel),
        "bound_after_u04_white_action_id": identity.AFTER_U04_WHITE_ACTION_ID,
        "bound_after_u04_white_result_file_sha256": (
            identity.AFTER_U04_WHITE_RESULT_FILE_SHA256
        ),
        "bound_after_u04_white_observation_file_sha256": (
            identity.AFTER_U04_WHITE_OBSERVATION_FILE_SHA256
        ),
        "observed_at": "2026-08-09T22:30:00+08:00",
        "operator_report_verbatim": "全屏仍白，无其他刷新，电气正常",
        "full_panel_white": True,
        "no_intervening_visible_refresh_since_bound_white": True,
        "electrical_normal": True,
        "hardware_authorization": False,
        "formal_u07_qualification_inferred": False,
    }
    runner._write_new(evidence, runner._seal(unsigned))  # noqa: SLF001
    validated = runner.validate_initial_white_attestation(context, evidence)
    assert validated["no_intervening_visible_refresh_since_bound_white"] is True


def test_initial_white_attestation_rejects_intervening_refresh(tmp_path: Path) -> None:
    context = _context(tmp_path)
    evidence = tmp_path / "initial.json"
    unsigned = {
        "schema_version": 1,
        "kind": runner.INITIAL_STATE_KIND,
        "classification": runner.CLASSIFICATION,
        "panel": dict(context.panel),
        "bound_after_u04_white_action_id": identity.AFTER_U04_WHITE_ACTION_ID,
        "bound_after_u04_white_result_file_sha256": identity.AFTER_U04_WHITE_RESULT_FILE_SHA256,
        "bound_after_u04_white_observation_file_sha256": identity.AFTER_U04_WHITE_OBSERVATION_FILE_SHA256,
        "observed_at": "2026-08-09T22:30:00+08:00",
        "operator_report_verbatim": "期间刷过别的画面",
        "full_panel_white": True,
        "no_intervening_visible_refresh_since_bound_white": False,
        "electrical_normal": True,
        "hardware_authorization": False,
        "formal_u07_qualification_inferred": False,
    }
    runner._write_new(evidence, runner._seal(unsigned))  # noqa: SLF001
    with pytest.raises(runner.U07TPhysicalError, match="no_intervening"):
        runner.validate_initial_white_attestation(context, evidence)


def test_diagnostic_requires_explicit_j2_off_before_network(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(runner.U07TPhysicalError, match="J2-off"):
        runner.diagnose_j2_off(
            context,
            "http://192.0.2.1",
            confirm_j2_off=False,
            evidence_file=tmp_path / "diagnostic.json",
            formal_claim_registry=tmp_path / "formal",
            technical_claim_registry=tmp_path / "technical",
            _urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("network must not be reached")
            ),
        )


def test_formal_and_technical_claim_registry_alias_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(runner.U07TPhysicalError, match="must differ"):
        runner._technical_claim_path(  # noqa: SLF001
            context, tmp_path / "formal"
        )
