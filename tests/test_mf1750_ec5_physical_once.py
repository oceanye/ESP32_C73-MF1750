from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.parse

import pytest

from tests.test_mf1750_ec5_white_recovery_once import (
    FROZEN_BINARY,
    FakeRC2G,
)
from tests.test_mf1750_ec5_release import _fixture_elf
from tests.test_mf1750_ec5_sixstate_physical_once import (
    _release as _sixstate_release,
)
from tools import mf1750_ec5_physical_once as runner
from tools import mf1750_ec5_release as release
from tools import mf1750_ec5_sixstate_physical_once as sixstate_runner
from tools import mf1750_ec5_white_recovery_once as white_runner


PANEL = {
    "board_id": "ESP32-C73",
    "model": "MF1750-C73",
    "pcb_revision": "rev-a1",
    "serial": "MF750M009T6420/1582643AGY44",
}
BOOT = "0123456789abcdef"
ARM = "fedcba9876543210"


def _firmware(candidate_id: str) -> bytes:
    variant = release.VARIANTS[candidate_id]
    nvs = variant["nvs_contract"]
    tokens = b"\0".join(
        str(token).encode("ascii")
        for token in (
            variant["build_tag"],
            variant["test_id"],
            variant["action_id"],
            variant["frame_sha256"],
            variant["dtm_sha256"],
            variant["identity_revision"],
            variant["device_api_version"],
            nvs["legacy"]["namespace"],
            nvs["legacy"]["key"],
            nvs["active"]["namespace"],
            nvs["active"]["key"],
        )
    )
    return b"EC5-TEST-BINARY\0" + tokens + b"\0END"


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    binaries: dict[str, Path] = {}
    elfs: dict[str, Path] = {}
    for candidate in ("U04", "U07"):
        binary = tmp_path / f"input-{candidate}.bin"
        binary.write_bytes(_firmware(candidate))
        binaries[candidate] = binary
        elf = tmp_path / f"input-{candidate}.elf"
        elf.write_bytes(_fixture_elf(release.VARIANTS[candidate]["candidate_code"]))
        elfs[candidate] = elf
    monkeypatch.setattr(
        release,
        "_source_snapshot",
        lambda: {
            "git_head": "a" * 40,
            "git_dirty": True,
            "git_status_sha256": release.sha256(b" M test\n"),
            "git_status_line_count": 1,
            "relevant_sources": [
                {
                    "path": path,
                    "bytes": (release.REPO_ROOT / path).stat().st_size,
                    "sha256": release.sha256((release.REPO_ROOT / path).read_bytes()),
                }
                for path in release.SOURCE_PATHS
            ],
        },
    )
    manifest, payloads = release.build_release(
        panel_file=panel,
        u04_binary=binaries["U04"],
        u07_binary=binaries["U07"],
        u04_elf=elfs["U04"],
        u07_elf=elfs["U07"],
        created_at="2026-08-09T10:00:00+08:00",
    )
    output = tmp_path / "release"
    release.publish_release(output, manifest, payloads)
    return output


class Response:
    def __init__(self, value: dict, status: int = 200) -> None:
        self.payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.status = status

    def getcode(self) -> int:
        return self.status

    def read(self, maximum: int = -1) -> bytes:
        return self.payload if maximum < 0 else self.payload[:maximum]

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class ScriptedOpen:
    def __init__(self, script: list[tuple[str, str, dict | Exception]]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []

    def __call__(self, request, timeout: float):
        method = request.get_method()
        path = urllib.parse.urlsplit(request.full_url).path
        self.requests.append(
            {
                "method": method,
                "path": path,
                "data": request.data,
                "headers": {key.lower(): value for key, value in request.header_items()},
                "timeout": timeout,
            }
        )
        if not self.script:
            raise AssertionError(f"unexpected request {method} {path}")
        expected_method, expected_path, value = self.script.pop(0)
        assert (method, path) == (expected_method, expected_path)
        if isinstance(value, Exception):
            raise value
        return Response(value)


def _device_values(context: runner.ReleaseContext) -> dict[str, dict]:
    variant = context.variant
    nvs_contract = copy.deepcopy(variant["nvs_contract"])
    common = {
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "action_id": variant["action_id"],
    }

    def nvs(phase: int) -> dict:
        return {
            "nvs_contract": copy.deepcopy(nvs_contract),
            "legacy_key_present": nvs_contract["legacy"]["expected_present"],
            "legacy_phase": nvs_contract["legacy"]["expected_phase"],
            "legacy_match": True,
            "active_key_present": phase != 0,
            "active_phase": phase,
            "active_virgin": phase == 0,
            "migration_ready": True,
        }

    def status(state: str, phase: int, arm_count: int, execute_count: int, driver_count: int) -> dict:
        return {
            "schema_version": runner.EXPECTED_DEVICE_SCHEMA_VERSION,
            "kind": "mf1750-ec5-unknown-probe-status",
            **common,
            "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
            "identity_revision": variant["identity_revision"],
            "boot_nonce": BOOT,
            "state": state,
            "fixture_self_check_passed": True,
            "driver_fixture_guard_passed": True,
            "claim_store_ready": True,
            "persistent_phase": phase,
            "arm_request_count": arm_count,
            "execute_consumed": phase >= 2,
            "execute_pending": state in ("queued", "running"),
            "execute_request_count": execute_count,
            "driver_call_count": driver_count,
            "gpio_initialized": True,
            "busy": 1,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            **nvs(phase),
        }

    version = {
        "schema_version": runner.EXPECTED_DEVICE_SCHEMA_VERSION,
        "kind": "mf1750-ec5-unknown-probe-version",
        "build_tag": variant["build_tag"],
        "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
        "identity_revision": variant["identity_revision"],
        "driver_api_version": runner.EXPECTED_DRIVER_API_VERSION,
        "candidate_code": f"0x{variant['candidate_code']:x}",
        "layout_id": variant["layout_id"],
        "automatic_execute": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "retry": False,
        "recovery": False,
        "boot_fixture_guard": "exact_driver_action_validator",
        "persistent_claim": True,
        "arm_required": True,
        "execute_limit_per_binary_candidate": 1,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
    }
    manifest = {
        "schema_version": runner.EXPECTED_DEVICE_SCHEMA_VERSION,
        "kind": "mf1750-ec5-compiled-fixture-manifest",
        **common,
        "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
        "identity_revision": variant["identity_revision"],
        "scope": "experimental_scaffold_not_hardware_authorization",
        "candidate_code": variant["candidate_code"],
        "candidate_code_hex": f"0x{variant['candidate_code']:x}",
        "layout_id": variant["layout_id"],
        "intended_initial_code": 1,
        "sequence_class": "white_initial_single_probe",
        "repetition": 1,
        "width": 1024,
        "height": 600,
        "frame_bytes": 307200,
        "pixel_packing": "row_major_4bpp_even_x_high_nibble",
        "known_white_pixels": 606208,
        "unknown_pixels": 8192,
        "roi_cs1": {"x0": 224, "x1": 288, "y0": 268, "y1": 332},
        "roi_cs2": {"x0": 736, "x1": 800, "y0": 268, "y1": 332},
        "guard_cs1": {"x0": 192, "x1": 320, "y0": 236, "y1": 364},
        "guard_cs2": {"x0": 704, "x1": 832, "y0": 236, "y1": 364},
        "mapping_cs1": [0, 0, 0, 0],
        "mapping_cs2": [1, 0, 0, 0],
        "frame_sha256": variant["frame_sha256"],
        "frame_fnv1a": f"0x{variant['frame_fnv1a']:08x}",
        "cs1_dtm_sha256": variant["dtm_sha256"],
        "cs1_dtm_fnv1a": f"0x{variant['dtm_fnv1a']:08x}",
        "cs2_dtm_sha256": variant["dtm_sha256"],
        "cs2_dtm_fnv1a": f"0x{variant['dtm_fnv1a']:08x}",
        "otp_mode": "existing_on_chip_otp_unchanged",
        "external_build_sidecar_required": True,
        "exact_driver_fixture_guard_required": True,
        "manifest_payload_sha256": None,
        "binary_sha256": None,
        "mutation_contract": {
            "bodyless": True,
            "exact_build_test_action_boot_nonce": True,
            "arm_nonce_required_for_execute": True,
            "not_hardware_authorization": True,
        },
        **nvs(0),
    }
    arm_response = {
        "accepted": True,
        "armed": True,
        **common,
        "boot_nonce": BOOT,
        "arm_nonce": ARM,
        "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
        "identity_revision": variant["identity_revision"],
        "persistent_phase": 1,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
        "not_hardware_authorization": True,
        "migration_ready": True,
    }
    execute_response = {
        "accepted": True,
        "job_id": 1,
        **common,
        "boot_nonce": BOOT,
        "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
        "identity_revision": variant["identity_revision"],
        "execute_consumed": True,
        "persistent_phase": 2,
        "no_retry": True,
        "no_recovery": True,
        "migration_ready": True,
    }
    report = {
        "schema_version": runner.EXPECTED_DEVICE_SCHEMA_VERSION,
        "kind": "mf1750-ec5-unknown-probe-report",
        "valid": True,
        **common,
        "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
        "identity_revision": variant["identity_revision"],
        "boot_nonce": BOOT,
        "candidate_code": variant["candidate_code"],
        "job_id": 1,
        "terminal_state": "completed",
        "result": True,
        "driver_fixture_guard_passed": True,
        "execute_consumed": True,
        "driver_called": True,
        "driver_call_count": 1,
        "persistent_phase": 2,
        "no_retry": True,
        "no_recovery": True,
        "job_queued_at_ms": 100,
        "job_started_at_ms": 101,
        "job_finished_at_ms": 500,
        "driver": {
            "driver_evidence_schema_version": 2,
            "operation_id": 1,
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "post_psr_busy_seen": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "failure_code": 0,
            "spi_hz": 1_000_000,
            "free_psram_before": 8_000_000,
            "largest_psram_block_before": 4_000_000,
            "input_fnv1a": variant["frame_fnv1a"],
            "cs1_dtm_fnv1a": variant["dtm_fnv1a"],
            "cs2_dtm_fnv1a": variant["dtm_fnv1a"],
            "total_ms": 399,
            "cs1_upload_ms": 20,
            "cs2_upload_ms": 20,
            "pon_ms": 40,
            "drf_ms": 200,
            "pof_ms": 40,
            "post_psr_ms": 0,
            "last_wait_stage": "post-display PSR",
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
        **nvs(2),
    }
    return {
        "version": version,
        "manifest": manifest,
        "virgin": status("ready", 0, 0, 0, 0),
        "virgin_report": {
            "schema_version": runner.EXPECTED_DEVICE_SCHEMA_VERSION,
            "kind": "mf1750-ec5-unknown-probe-report",
            "valid": False,
            **common,
            "device_api_version": runner.EXPECTED_DEVICE_API_VERSION,
            "identity_revision": variant["identity_revision"],
            "boot_nonce": BOOT,
            "candidate_code": variant["candidate_code"],
            "terminal_state": "NOT_EXECUTED",
            "error": "no_execute_report",
            "driver_fixture_guard_passed": True,
            "execute_consumed": False,
            "driver_called": False,
            "persistent_phase": 0,
            "no_retry": True,
            "no_recovery": True,
            **nvs(0),
        },
        "arm": arm_response,
        "armed": status("armed", 1, 1, 0, 0),
        "execute": execute_response,
        "terminal": status("completed", 2, 1, 1, 1),
        "report": report,
    }


def _preflight_script(values: dict[str, dict]) -> list[tuple[str, str, dict | Exception]]:
    return [
        ("GET", "/api/ec5/version", values["version"]),
        ("GET", "/api/ec5/manifest", values["manifest"]),
        ("GET", "/api/ec5/status", values["virgin"]),
        ("GET", "/api/ec5/report", values["virgin_report"]),
    ]


def _successful_script(values: dict[str, dict]) -> list[tuple[str, str, dict | Exception]]:
    return _preflight_script(values) + [
        ("POST", "/api/ec5/arm", values["arm"]),
        ("GET", "/api/ec5/status", values["armed"]),
        ("POST", "/api/ec5/execute", values["execute"]),
        ("GET", "/api/ec5/status", values["terminal"]),
        ("GET", "/api/ec5/report", values["report"]),
    ]


def _diagnostic_evidence(
    tmp_path: Path,
    context: runner.ReleaseContext,
    values: dict[str, dict],
) -> Path:
    diagnostic_values = copy.deepcopy(values)
    diagnostic_values["virgin"]["busy"] = 0
    serial = len(list(tmp_path.glob("diagnostic-*.json")))
    evidence_file = tmp_path / f"diagnostic-{context.variant_id.lower()}-{serial}.json"
    opener = ScriptedOpen(_preflight_script(diagnostic_values))
    evidence = runner.diagnose_j2_off(
        context,
        "http://192.168.4.1",
        confirm_j2_off=True,
        evidence_file=evidence_file,
        _urlopen=opener,
    )
    assert evidence["get_requests"] == 4
    assert evidence["post_requests"] == 0
    assert evidence["claim_created"] is False
    assert evidence["authorization_created"] is False
    assert [request["method"] for request in opener.requests] == ["GET"] * 4
    assert opener.script == []
    return evidence_file


def _context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate: str = "U04") -> runner.ReleaseContext:
    bundle = _bundle(tmp_path, monkeypatch)
    panel = tmp_path / "live-panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    return runner.load_release(
        bundle / "release-manifest.json",
        candidate,
        panel_file=panel,
    )


def _seal_review(value: dict) -> bytes:
    sealed = copy.deepcopy(value)
    sealed["integrity"] = {"canonical_sha256": None}
    sealed["integrity"]["canonical_sha256"] = runner._sha256(
        runner.canonical_json_bytes(sealed)
    )
    return runner.canonical_json_bytes(sealed)


def _u04_prerequisite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    bundle = _bundle(tmp_path, monkeypatch)
    panel = tmp_path / "live-panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    u04 = runner.load_release(bundle / "release-manifest.json", "U04", panel_file=panel)
    u07 = runner.load_release(bundle / "release-manifest.json", "U07", panel_file=panel)
    registry = tmp_path / "claims"
    u04_result = tmp_path / "u04-result.json"
    u04_values = _device_values(u04)
    u04_diagnostic = _diagnostic_evidence(tmp_path, u04, u04_values)
    runner.run_once(
        u04,
        "http://192.168.4.1",
        authorization=runner.required_authorization(u04),
        result_file=u04_result,
        diagnostic_preflight_file=u04_diagnostic,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=ScriptedOpen(_successful_script(u04_values)),
        _sleep=lambda _seconds: None,
    )
    finished = datetime.fromisoformat(
        json.loads(u04_result.read_bytes())["finished_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    holds = {
        0: tmp_path / "u04-hold-0.json",
        5: tmp_path / "u04-hold-5.json",
        30: tmp_path / "u04-hold-30.json",
    }
    hold_times = {
        0: finished + timedelta(seconds=1),
        5: finished + timedelta(minutes=5, seconds=1),
        30: finished + timedelta(minutes=30, seconds=1),
    }
    confirmations = {
        "visual_stable": True,
        "electrical_normal": True,
        "esp32_not_restarted": True,
        "no_uncommanded_refresh": True,
    }
    monkeypatch.setattr(runner, "_utc_now", lambda: hold_times[0])
    runner.record_u04_hold_observation(
        u04,
        u04_result_file=u04_result,
        output_file=holds[0],
        hold_minutes=0,
        temperature_c=37.0,
        confirmations=confirmations,
        claim_registry=registry,
    )
    monkeypatch.setattr(runner, "_utc_now", lambda: hold_times[5])
    runner.record_u04_hold_observation(
        u04,
        u04_result_file=u04_result,
        output_file=holds[5],
        hold_minutes=5,
        temperature_c=37.0,
        confirmations=confirmations,
        prior_hold_files={0: holds[0]},
        claim_registry=registry,
    )
    monkeypatch.setattr(runner, "_utc_now", lambda: hold_times[30])
    runner.record_u04_hold_observation(
        u04,
        u04_result_file=u04_result,
        output_file=holds[30],
        hold_minutes=30,
        temperature_c=37.0,
        confirmations=confirmations,
        prior_hold_files={0: holds[0], 5: holds[5]},
        claim_registry=registry,
    )
    white_registry = tmp_path / "white-claims"
    white_result = tmp_path / "after-u04-white-result.json"
    white_time = hold_times[30] + timedelta(seconds=1)
    monkeypatch.setattr(
        white_runner,
        "_now",
        lambda: white_time.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    )
    white_runner.run_once(
        stage="after-u04",
        base_url="http://192.0.2.1",
        authorization=white_runner.required_authorization("after-u04"),
        panel_file=Path(u04.panel_file),
        rc2g_binary_file=FROZEN_BINARY,
        result_file=white_result,
        release_file=u04.path,
        candidate_result_file=u04_result,
        candidate_claim_registry=registry,
        claim_registry=white_registry,
        requester=FakeRC2G(),
        sleeper=lambda _seconds: None,
    )
    validation_now = hold_times[30] + timedelta(minutes=1)
    monkeypatch.setattr(runner, "_utc_now", lambda: validation_now)
    review = tmp_path / "u04-review.json"
    runner.finalize_u04_review(
        u04,
        u04_result_file=u04_result,
        hold_0_file=holds[0],
        hold_5_file=holds[5],
        hold_30_file=holds[30],
        white_recovery_result_file=white_result,
        rc2g_binary_file=FROZEN_BINARY,
        output_file=review,
        reviewer="Ye",
        confirmations={key: True for key in runner._FINALIZE_CONFIRMATION_KEYS},
        white_claim_registry=white_registry,
        claim_registry=registry,
    )
    return {
        "u04": u04,
        "u07": u07,
        "registry": registry,
        "u04_result": u04_result,
        "review": review,
        "hold_0": holds[0],
        "hold_5": holds[5],
        "hold_30": holds[30],
        "white_result": white_result,
        "rc2g_binary": FROZEN_BINARY,
        "white_registry": white_registry,
        "now": validation_now,
    }


def _u07_gate_kwargs(prerequisite: dict[str, object]) -> dict[str, object]:
    return {
        "u04_review_file": prerequisite["review"],
        "u04_result_file": prerequisite["u04_result"],
        "u04_hold_0_file": prerequisite["hold_0"],
        "u04_hold_5_file": prerequisite["hold_5"],
        "u04_hold_30_file": prerequisite["hold_30"],
        "u04_white_recovery_result_file": prerequisite["white_result"],
        "rc2g_binary_file": prerequisite["rc2g_binary"],
        "white_claim_registry": prerequisite["white_registry"],
    }


def test_describe_and_preflight_are_claim_free_and_get_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    described = runner.describe(context)
    assert described["claim_created"] is False
    assert described["network_requests"] == 0

    values = _device_values(context)
    opener = ScriptedOpen(_preflight_script(values))
    preflight = runner.preflight(context, "http://192.168.4.1", _urlopen=opener)
    assert preflight["boot_nonce"] == BOOT
    assert preflight["post_requests"] == 0
    assert [item["method"] for item in opener.requests] == ["GET"] * 4


def test_j2_off_diagnostic_is_exactly_four_gets_zero_posts_and_zero_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    values["virgin"]["busy"] = 0
    evidence_file = tmp_path / "j2-off-diagnostic.json"
    registry = tmp_path / "claims"
    opener = ScriptedOpen(_preflight_script(values))

    evidence = runner.diagnose_j2_off(
        context,
        "http://192.168.4.1",
        confirm_j2_off=True,
        evidence_file=evidence_file,
        _urlopen=opener,
    )

    assert [request["method"] for request in opener.requests] == ["GET"] * 4
    assert [request["path"] for request in opener.requests] == [
        "/api/ec5/version",
        "/api/ec5/manifest",
        "/api/ec5/status",
        "/api/ec5/report",
    ]
    assert evidence["get_requests"] == 4
    assert evidence["post_requests"] == 0
    assert evidence["claim_created"] is False
    assert evidence["authorization_created"] is False
    assert evidence["boot_nonce"] == BOOT
    assert not registry.exists()
    reference = runner.validate_diagnostic_preflight(context, evidence_file)
    assert reference["file_sha256"] == runner._sha256(evidence_file.read_bytes())


@pytest.mark.parametrize("failure", ["gpio", "migration"])
def test_j2_off_diagnostic_rejects_wrong_gpio_or_migration_without_evidence_or_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    values["virgin"]["busy"] = 0
    if failure == "gpio":
        values["virgin"]["rst"] = 1
    else:
        values["virgin"]["migration_ready"] = False
    evidence_file = tmp_path / "rejected-diagnostic.json"
    opener = ScriptedOpen(_preflight_script(values))

    with pytest.raises(runner.Ec5PhysicalError, match="rst|migration_ready"):
        runner.diagnose_j2_off(
            context,
            "http://192.168.4.1",
            confirm_j2_off=True,
            evidence_file=evidence_file,
            _urlopen=opener,
        )

    assert [request["method"] for request in opener.requests] == ["GET"] * 4
    assert not evidence_file.exists()
    assert not (tmp_path / "claims").exists()


def test_tampered_diagnostic_raw_bytes_block_run_before_network_or_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    good = _diagnostic_evidence(tmp_path, context, values)
    tampered_value = json.loads(good.read_bytes())
    tampered_value["endpoints"][0]["raw_base64"] = "e30="
    tampered = runner._sealed_result(
        {key: value for key, value in tampered_value.items() if key != "integrity"}
    )
    tampered_file = tmp_path / "tampered-diagnostic.json"
    tampered_file.write_bytes(runner.canonical_json_bytes(tampered))
    registry = tmp_path / "claims"
    opener = ScriptedOpen([])

    with pytest.raises(runner.Ec5PhysicalError, match="raw payload length/SHA"):
        runner.run_once(
            context,
            "http://192.168.4.1",
            authorization=runner.required_authorization(context),
            result_file=tmp_path / "must-not-exist.json",
            diagnostic_preflight_file=tampered_file,
            claim_registry=registry,
            _urlopen=opener,
        )

    assert opener.requests == []
    assert not registry.exists()


def test_run_rejects_reboot_after_diagnostic_before_claim_or_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    rebooted = copy.deepcopy(values)
    rebooted_nonce = "1111111111111111"
    rebooted["virgin"]["boot_nonce"] = rebooted_nonce
    rebooted["virgin_report"]["boot_nonce"] = rebooted_nonce
    opener = ScriptedOpen(_preflight_script(rebooted))
    registry = tmp_path / "claims"

    with pytest.raises(runner.Ec5PhysicalError, match="boot_nonce"):
        runner.run_once(
            context,
            "http://192.168.4.1",
            authorization=runner.required_authorization(context),
            result_file=tmp_path / "must-not-exist.json",
            diagnostic_preflight_file=diagnostic,
            claim_registry=registry,
            _urlopen=opener,
        )

    assert [request["method"] for request in opener.requests] == ["GET"] * 4
    assert not any(request["method"] == "POST" for request in opener.requests)
    assert not registry.exists()


def test_quarantined_release_is_rejected_during_load_before_claim_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path, monkeypatch)
    panel = tmp_path / "live-panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    (bundle / runner.QUARANTINE_MARKER).write_text(
        "QUARANTINED_DO_NOT_USE\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner,
        "_read_regular",
        lambda *_args, **_kwargs: pytest.fail(
            "quarantine must reject before reading or trusting the manifest"
        ),
    )
    registry = tmp_path / "claims"
    result_file = tmp_path / "result.json"
    with pytest.raises(runner.Ec5PhysicalError, match="release bundle is quarantined"):
        runner.load_release(
            bundle / "release-manifest.json",
            "U04",
            panel_file=panel,
        )
    assert not registry.exists()
    assert not result_file.exists()


def test_release_schema_one_is_rejected_even_if_its_integrity_is_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path, monkeypatch)
    manifest_file = bundle / "release-manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    manifest["schema_version"] = 1
    unsigned = copy.deepcopy(manifest)
    unsigned.pop("integrity")
    manifest["integrity"] = {
        "canonical_sha256": release.sha256(unsigned),
        "scope": release.HASH_SCOPE,
    }
    manifest_file.write_bytes(release.canonical_json_bytes(manifest))

    with pytest.raises(runner.Ec5PhysicalError, match="unsupported EC5 release"):
        runner.load_release(manifest_file, "U04")


def test_success_is_exactly_arm_execute_once_and_result_revalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    opener = ScriptedOpen(_successful_script(values))
    registry = tmp_path / "claims"
    result_file = tmp_path / "result.json"
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=result_file,
        diagnostic_preflight_file=diagnostic,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=opener,
        _sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert result["post_requests"] == 2
    assert result["boot_nonce"] == BOOT
    assert result["diagnostic_preflight"]["boot_nonce"] == BOOT
    assert result["diagnostic_preflight"]["file_sha256"] == runner._sha256(
        diagnostic.read_bytes()
    )
    posts = [request for request in opener.requests if request["method"] == "POST"]
    assert [request["path"] for request in posts] == ["/api/ec5/arm", "/api/ec5/execute"]
    assert all(request["data"] is None for request in posts)
    assert posts[0]["headers"]["x-ec5-intent"] == runner.ARM_INTENT
    assert posts[1]["headers"]["x-ec5-intent"] == runner.EXECUTE_INTENT
    assert posts[1]["headers"]["x-ec5-arm-nonce"] == ARM
    assert len(list(registry.iterdir())) == 1
    assert runner.validate_result(context, result_file, claim_registry=registry)["outcome"] == "complete_pass"

    forbidden = ScriptedOpen([])
    with pytest.raises(runner.Ec5PhysicalError, match="already has"):
        runner.run_once(
            context,
            "http://192.168.4.1",
            authorization=runner.required_authorization(context),
            result_file=tmp_path / "second.json",
            diagnostic_preflight_file=diagnostic,
            claim_registry=registry,
            _urlopen=forbidden,
        )
    assert forbidden.requests == []


def test_wrong_authorization_is_zero_network_and_zero_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    opener = ScriptedOpen([])
    registry = tmp_path / "claims"
    with pytest.raises(runner.Ec5PhysicalError, match="exact candidate-bound"):
        runner.run_once(
            context,
            "http://192.168.4.1",
            authorization=(
                "AUTHORIZE_ONE_VISIBLE_EC5_U04__ACTION_"
                "BF2FCBCB29A35CF0A7915C67B48468ACA26F7A35AEF20E9FF68C9D60A37D0DF5"
                "__NO_RETRY_NO_RECOVERY"
            ),
            result_file=tmp_path / "result.json",
            diagnostic_preflight_file=tmp_path / "must-not-be-read.json",
            claim_registry=registry,
            _urlopen=opener,
        )
    assert opener.requests == []
    assert not registry.exists()


def test_preflight_timeout_is_zero_claim_and_zero_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    opener = ScriptedOpen(
        [("GET", "/api/ec5/version", TimeoutError("device unavailable"))]
    )
    registry = tmp_path / "claims"
    diagnostic = _diagnostic_evidence(tmp_path, context, _device_values(context))
    with pytest.raises(runner.Ec5PhysicalError, match="device unavailable"):
        runner.run_once(
            context,
            "http://192.168.4.1",
            authorization=runner.required_authorization(context),
            result_file=tmp_path / "result.json",
            diagnostic_preflight_file=diagnostic,
            claim_registry=registry,
            _urlopen=opener,
        )
    assert [item["method"] for item in opener.requests] == ["GET"]
    assert not registry.exists()


def test_duplicate_key_device_json_is_rejected_during_get_only_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)

    class DuplicateResponse(Response):
        def __init__(self) -> None:
            self.payload = b'{"schema_version":1,"schema_version":1}'
            self.status = 200

    requests = []

    def opener(request, timeout: float):
        requests.append((request.get_method(), urllib.parse.urlsplit(request.full_url).path))
        return DuplicateResponse()

    with pytest.raises(runner.Ec5PhysicalError, match="duplicate key"):
        runner.preflight(context, "http://192.168.4.1", _urlopen=opener)
    assert requests == [("GET", "/api/ec5/version")]


def test_stale_arm_reply_keeps_claim_and_never_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    stale = copy.deepcopy(values["arm"])
    stale["boot_nonce"] = "1111111111111111"
    script = _preflight_script(values) + [
        ("POST", "/api/ec5/arm", stale),
        ("GET", "/api/ec5/status", values["armed"]),
        ("GET", "/api/ec5/report", values["virgin_report"]),
    ]
    opener = ScriptedOpen(script)
    registry = tmp_path / "claims"
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=tmp_path / "result.json",
        diagnostic_preflight_file=diagnostic,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=opener,
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["post_requests"] == 1
    assert [request["path"] for request in opener.requests if request["method"] == "POST"] == ["/api/ec5/arm"]
    assert len(list(registry.iterdir())) == 1


def test_lost_execute_reply_is_adjudicated_by_get_only_polling_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    script = _preflight_script(values) + [
        ("POST", "/api/ec5/arm", values["arm"]),
        ("GET", "/api/ec5/status", values["armed"]),
        ("POST", "/api/ec5/execute", TimeoutError("reply lost")),
        ("GET", "/api/ec5/status", values["terminal"]),
        ("GET", "/api/ec5/report", values["report"]),
    ]
    opener = ScriptedOpen(script)
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=tmp_path / "result.json",
        diagnostic_preflight_file=diagnostic,
        claim_registry=tmp_path / "claims",
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=opener,
    )
    assert result["outcome"] == "complete_pass"
    assert result["post_requests"] == 2
    assert len([request for request in opener.requests if request["path"] == "/api/ec5/execute"]) == 1
    assert [request["method"] for request in opener.requests[-2:]] == ["GET", "GET"]


def test_malformed_final_fnv_is_unknown_and_never_reposts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    malformed = copy.deepcopy(values["report"])
    malformed["driver"]["input_fnv1a"] ^= 1
    script = _preflight_script(values) + [
        ("POST", "/api/ec5/arm", values["arm"]),
        ("GET", "/api/ec5/status", values["armed"]),
        ("POST", "/api/ec5/execute", values["execute"]),
        ("GET", "/api/ec5/status", values["terminal"]),
        ("GET", "/api/ec5/report", malformed),
    ]
    opener = ScriptedOpen(script)
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=tmp_path / "result.json",
        diagnostic_preflight_file=diagnostic,
        claim_registry=tmp_path / "claims",
        poll_count=40,
        poll_interval_seconds=0,
        _urlopen=opener,
        _sleep=lambda _seconds: pytest.fail("stable terminal evidence must stop polling"),
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["final_report"] is None
    assert result["observed_terminal_report"] == malformed
    expected_payload = json.dumps(malformed, sort_keys=True, separators=(",", ":")).encode()
    assert result["observed_terminal_report_payload_bytes"] == len(expected_payload)
    assert result["observed_terminal_report_payload_sha256"] == runner._sha256(expected_payload)
    assert len(result["observations"]) == 1
    assert result["observations"][0]["validation_error"] == "final driver FNV evidence mismatch"
    assert "read_error" not in result["observations"][0]
    assert result["error"] == "terminal report validation failed: final driver FNV evidence mismatch"
    assert len([request for request in opener.requests if request["method"] == "POST"]) == 2
    assert opener.script == []
    assert runner.validate_result(
        context, tmp_path / "result.json", claim_registry=tmp_path / "claims"
    )["outcome"] == "unknown_do_not_retry_or_recover"

    stored = json.loads((tmp_path / "result.json").read_bytes())
    wrong_identity = copy.deepcopy(stored)
    wrong_identity["observed_terminal_report"]["action_id"] = "f" * 64
    wrong_identity["integrity"]["canonical_sha256"] = None
    wrong_identity["integrity"]["canonical_sha256"] = runner._sha256(
        runner.canonical_json_bytes(wrong_identity)
    )
    wrong_identity_file = tmp_path / "wrong-observed-identity.json"
    wrong_identity_file.write_bytes(runner.canonical_json_bytes(wrong_identity))
    with pytest.raises(runner.Ec5PhysicalError, match="final report action_id mismatch"):
        runner.validate_result(context, wrong_identity_file, claim_registry=tmp_path / "claims")

    wrong_count = copy.deepcopy(stored)
    wrong_count["final_status"]["driver_call_count"] = 2
    wrong_count["integrity"]["canonical_sha256"] = None
    wrong_count["integrity"]["canonical_sha256"] = runner._sha256(
        runner.canonical_json_bytes(wrong_count)
    )
    wrong_count_file = tmp_path / "wrong-terminal-count.json"
    wrong_count_file.write_bytes(runner.canonical_json_bytes(wrong_count))
    with pytest.raises(runner.Ec5PhysicalError, match="one consumed driver call"):
        runner.validate_result(context, wrong_count_file, claim_registry=tmp_path / "claims")


def test_coherent_early_pre_panel_fault_is_saved_complete_and_stops_after_one_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    fault_status = copy.deepcopy(values["terminal"])
    fault_status["state"] = "fault_locked"
    fault_report = copy.deepcopy(values["report"])
    fault_report["terminal_state"] = "fault_locked"
    fault_report["result"] = False
    fault_report["driver"].update(
        {
            "sequence_ok": False,
            "failure_stage": "allocation",
            "failure_code": 0,
            "mapping_applied": False,
            "pon_busy_seen": False,
            "drf_busy_seen": False,
            "pof_busy_seen": False,
            "post_psr_busy_seen": False,
            "input_fnv1a": 0,
            "cs1_dtm_fnv1a": 0,
            "cs2_dtm_fnv1a": 0,
            "cs1_upload_ms": 0,
            "cs2_upload_ms": 0,
            "pon_ms": 0,
            "drf_ms": 0,
            "pof_ms": 0,
            "post_psr_ms": 0,
            "last_wait_stage": "none",
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        }
    )
    script = _preflight_script(values) + [
        ("POST", "/api/ec5/arm", values["arm"]),
        ("GET", "/api/ec5/status", values["armed"]),
        ("POST", "/api/ec5/execute", values["execute"]),
        ("GET", "/api/ec5/status", fault_status),
        ("GET", "/api/ec5/report", fault_report),
    ]
    opener = ScriptedOpen(script)
    registry = tmp_path / "claims"
    result_file = tmp_path / "early-fault-result.json"
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=result_file,
        diagnostic_preflight_file=diagnostic,
        claim_registry=registry,
        poll_count=40,
        poll_interval_seconds=0,
        _urlopen=opener,
        _sleep=lambda _seconds: pytest.fail("stable terminal evidence must stop polling"),
    )
    assert result["outcome"] == "complete_driver_failure_no_retry"
    assert result["final_report"] == fault_report
    assert result["observed_terminal_report"] == fault_report
    expected_payload = json.dumps(fault_report, sort_keys=True, separators=(",", ":")).encode()
    assert result["observed_terminal_report_payload_bytes"] == len(expected_payload)
    assert result["observed_terminal_report_payload_sha256"] == runner._sha256(expected_payload)
    assert result["error"] == (
        "terminal driver failure: early_pre_panel_io; failure_stage=allocation; "
        "visible_refresh_started=false; no retry"
    )
    assert result["observations"] == [
        {
            "poll": 1,
            "state": "fault_locked",
            "persistent_phase": 2,
            "driver_call_count": 1,
            "report_valid": True,
            "terminal_verdict": "complete_driver_failure_no_retry",
        }
    ]
    assert len([request for request in opener.requests if request["method"] == "POST"]) == 2
    assert len([request for request in opener.requests if request["path"] == "/api/ec5/execute"]) == 1
    assert opener.script == []
    assert runner.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "complete_driver_failure_no_retry"
    with pytest.raises(runner.Ec5PhysicalError, match="complete_pass"):
        runner._candidate_result_reference(
            context,
            result_file,
            claim_registry=registry,
        )


def test_early_pre_panel_fault_accepts_nonzero_hashes_from_completed_identity_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    report = copy.deepcopy(_device_values(context)["report"])
    report["terminal_state"] = "fault_locked"
    report["result"] = False
    report["driver"].update(
        {
            "sequence_ok": False,
            "failure_stage": "cs1_identity",
            "failure_code": 0,
            "mapping_applied": False,
            "pon_busy_seen": False,
            "drf_busy_seen": False,
            "pof_busy_seen": False,
            "post_psr_busy_seen": False,
            "input_fnv1a": context.variant["frame_fnv1a"],
            "cs1_dtm_fnv1a": context.variant["dtm_fnv1a"] ^ 1,
            "cs2_dtm_fnv1a": context.variant["dtm_fnv1a"],
            "cs1_upload_ms": 0,
            "cs2_upload_ms": 0,
            "pon_ms": 0,
            "drf_ms": 0,
            "pof_ms": 0,
            "post_psr_ms": 0,
            "last_wait_stage": "none",
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        }
    )
    verdict = runner._validate_final_report(report, context, BOOT)
    assert verdict == {
        "passed": False,
        "driver": report["driver"],
        "failure_class": "early_pre_panel_io",
        "failure_stage": "cs1_identity",
        "visible_refresh_started": False,
    }


def test_ec5_v2_contract_rejects_unknown_keys_and_bad_typed_driver_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)

    version = copy.deepcopy(values["version"])
    version["unexpected"] = True
    with pytest.raises(runner.Ec5PhysicalError, match="device version keys differ"):
        runner._validate_version(version, context)

    status = copy.deepcopy(values["terminal"])
    status.pop("driver_fixture_guard_passed")
    with pytest.raises(runner.Ec5PhysicalError, match="device status keys differ"):
        runner._validate_status(
            status,
            context,
            boot_nonce=BOOT,
            allowed_states={"completed"},
        )

    report = copy.deepcopy(values["report"])
    report["driver"]["unexpected"] = 1
    with pytest.raises(runner.Ec5PhysicalError, match="final driver keys differ"):
        runner._validate_final_report(report, context, BOOT)

    report = copy.deepcopy(values["report"])
    report["driver"]["failure_code"] = True
    with pytest.raises(runner.Ec5PhysicalError, match="failure_code must be an integer"):
        runner._validate_final_report(report, context, BOOT)


def test_poll_transport_error_is_distinct_from_local_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    values = _device_values(context)
    script = _preflight_script(values) + [
        ("POST", "/api/ec5/arm", values["arm"]),
        ("GET", "/api/ec5/status", values["armed"]),
        ("POST", "/api/ec5/execute", values["execute"]),
        ("GET", "/api/ec5/status", values["terminal"]),
        ("GET", "/api/ec5/report", TimeoutError("report read lost")),
        ("GET", "/api/ec5/status", values["terminal"]),
        ("GET", "/api/ec5/report", values["report"]),
    ]
    opener = ScriptedOpen(script)
    sleeps: list[float] = []
    diagnostic = _diagnostic_evidence(tmp_path, context, values)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        authorization=runner.required_authorization(context),
        result_file=tmp_path / "result.json",
        diagnostic_preflight_file=diagnostic,
        claim_registry=tmp_path / "claims",
        poll_count=2,
        poll_interval_seconds=0.25,
        _urlopen=opener,
        _sleep=sleeps.append,
    )
    assert result["outcome"] == "complete_pass"
    assert result["observations"][0]["endpoint"] == "report"
    assert "report read lost" in result["observations"][0]["read_error"]
    assert "validation_error" not in result["observations"][0]
    assert result["observations"][1]["terminal_verdict"] == "complete_pass"
    assert sleeps == [0.25]
    assert len([request for request in opener.requests if request["method"] == "POST"]) == 2


def test_malformed_or_wrong_panel_release_fails_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path, monkeypatch)
    wrong_panel = tmp_path / "wrong-panel.json"
    wrong_panel.write_text(json.dumps({**PANEL, "serial": "OTHER"}), encoding="utf-8")
    with pytest.raises(runner.Ec5PhysicalError, match="live panel identity"):
        runner.load_release(bundle / "release-manifest.json", "U04", panel_file=wrong_panel)

    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variants"]["U04"]["action_id"] = "f" * 64
    unsigned = copy.deepcopy(manifest)
    unsigned.pop("integrity")
    manifest["integrity"] = {
        "canonical_sha256": release.sha256(unsigned),
        "scope": release.HASH_SCOPE,
    }
    manifest_path.write_bytes(release.canonical_json_bytes(manifest))
    with pytest.raises(runner.Ec5PhysicalError, match="frozen candidate"):
        runner.load_release(manifest_path, "U04")


def test_u07_missing_review_and_result_fail_before_claim_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u07 = prerequisite["u07"]
    registry = prerequisite["registry"]
    before = sorted(path.name for path in registry.iterdir())
    opener = ScriptedOpen([])
    with pytest.raises(runner.Ec5PhysicalError, match="requires its exact U04"):
        runner.run_once(
            u07,
            "http://192.168.4.1",
            authorization=runner.required_authorization(u07),
            result_file=tmp_path / "u07-result.json",
            diagnostic_preflight_file=tmp_path / "must-not-be-read.json",
            claim_registry=registry,
            _urlopen=opener,
        )
    assert opener.requests == []
    assert sorted(path.name for path in registry.iterdir()) == before


@pytest.mark.parametrize("failure", ["tamper", "fail", "cross_release"])
def test_u07_tampered_failed_or_cross_release_review_is_zero_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u07 = prerequisite["u07"]
    registry = prerequisite["registry"]
    source_review = prerequisite["review"]
    review = tmp_path / "tampered-u04-review.json"
    if failure == "tamper":
        payload = bytearray(source_review.read_bytes())
        payload[-2] ^= 1
        review.write_bytes(bytes(payload))
    else:
        value = json.loads(source_review.read_bytes())
        if failure == "fail":
            value["gates"]["review_pass"] = False
        else:
            value["release_canonical_sha256"] = "f" * 64
        review.write_bytes(_seal_review({key: val for key, val in value.items() if key != "integrity"}))
    before = sorted(path.name for path in registry.iterdir())
    opener = ScriptedOpen([])
    with pytest.raises(runner.Ec5PhysicalError):
        runner.run_once(
            u07,
            "http://192.168.4.1",
            authorization=runner.required_authorization(u07),
            result_file=tmp_path / "u07-result.json",
            diagnostic_preflight_file=tmp_path / "must-not-be-read.json",
            **{**_u07_gate_kwargs(prerequisite), "u04_review_file": review},
            claim_registry=registry,
            _urlopen=opener,
        )
    assert opener.requests == []
    assert sorted(path.name for path in registry.iterdir()) == before


def test_u07_valid_finalized_u04_review_is_bound_into_claim_and_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u07 = prerequisite["u07"]
    registry = prerequisite["registry"]
    u04_result = prerequisite["u04_result"]
    values = _device_values(u07)
    opener = ScriptedOpen(_successful_script(values))
    result_file = tmp_path / "u07-result.json"
    diagnostic = _diagnostic_evidence(tmp_path, u07, values)
    result = runner.run_once(
        u07,
        "http://192.168.4.1",
        authorization=runner.required_authorization(u07),
        result_file=result_file,
        diagnostic_preflight_file=diagnostic,
        **_u07_gate_kwargs(prerequisite),
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=opener,
        _sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert result["u04_review"]["review_pass"] is True
    claim = json.loads((registry / f"{u07.variant['action_id']}.json").read_bytes())
    assert claim["u04_review"] == result["u04_review"]
    validated = runner.validate_result(
        u07,
        result_file,
        claim_registry=registry,
        **_u07_gate_kwargs(prerequisite),
    )
    assert validated["u04_review"]["u04_result_file_sha256"] == runner._sha256(
        u04_result.read_bytes()
    )


def test_finalize_u04_review_generates_exclusive_gate_consumed_by_u07_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u04 = prerequisite["u04"]
    u07 = prerequisite["u07"]
    registry = prerequisite["registry"]
    u04_result = prerequisite["u04_result"]
    recovery = prerequisite["white_result"]
    review = tmp_path / "generated-u04-review.json"
    confirmations = {key: True for key in runner._FINALIZE_CONFIRMATION_KEYS}
    generated = runner.finalize_u04_review(
        u04,
        u04_result_file=u04_result,
        hold_0_file=prerequisite["hold_0"],
        hold_5_file=prerequisite["hold_5"],
        hold_30_file=prerequisite["hold_30"],
        white_recovery_result_file=recovery,
        rc2g_binary_file=prerequisite["rc2g_binary"],
        output_file=review,
        reviewer="Ye",
        confirmations=confirmations,
        white_claim_registry=prerequisite["white_registry"],
        claim_registry=registry,
    )
    assert generated["white_recovery"]["file_sha256"] == runner._sha256(recovery.read_bytes())
    with pytest.raises(runner.Ec5PhysicalError, match="already exists"):
        runner.finalize_u04_review(
            u04,
            u04_result_file=u04_result,
            hold_0_file=prerequisite["hold_0"],
            hold_5_file=prerequisite["hold_5"],
            hold_30_file=prerequisite["hold_30"],
            white_recovery_result_file=recovery,
            rc2g_binary_file=prerequisite["rc2g_binary"],
            output_file=review,
            reviewer="Ye",
            confirmations=confirmations,
            white_claim_registry=prerequisite["white_registry"],
            claim_registry=registry,
        )

    values = _device_values(u07)
    diagnostic = _diagnostic_evidence(tmp_path, u07, values)
    result = runner.run_once(
        u07,
        "http://192.168.4.1",
        authorization=runner.required_authorization(u07),
        result_file=tmp_path / "u07-generated-gate-result.json",
        diagnostic_preflight_file=diagnostic,
        **{**_u07_gate_kwargs(prerequisite), "u04_review_file": review},
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=ScriptedOpen(_successful_script(values)),
        _sleep=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert result["u04_review"]["white_recovery_result_file_sha256"] == runner._sha256(
        recovery.read_bytes()
    )


def test_hold_evidence_rejects_future_compressed_tampered_and_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u04 = prerequisite["u04"]
    result_file = prerequisite["u04_result"]
    registry = prerequisite["registry"]
    hold0 = prerequisite["hold_0"]
    confirmation = {
        "visual_stable": True,
        "electrical_normal": True,
        "esp32_not_restarted": True,
        "no_uncommanded_refresh": True,
    }
    hold0_time = datetime.fromisoformat(
        json.loads(hold0.read_bytes())["recorded_at"].replace("Z", "+00:00")
    )
    monkeypatch.setattr(
        runner, "_utc_now", lambda: hold0_time + timedelta(minutes=4)
    )
    with pytest.raises(runner.Ec5PhysicalError, match="boundary|five minutes"):
        runner.record_hold_observation(
            u04,
            candidate_result_file=result_file,
            output_file=tmp_path / "compressed-hold5.json",
            hold_minutes=5,
            temperature_c=37.0,
            confirmations=confirmation,
            prior_hold_files={0: hold0},
            claim_registry=registry,
        )

    future = json.loads(hold0.read_bytes())
    validation_now = prerequisite["now"]
    future["recorded_at"] = (
        validation_now + timedelta(minutes=1)
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    future_file = tmp_path / "future-hold.json"
    future_file.write_bytes(
        _seal_review({key: value for key, value in future.items() if key != "integrity"})
    )
    monkeypatch.setattr(runner, "_utc_now", lambda: validation_now)
    with pytest.raises(runner.Ec5PhysicalError, match="future"):
        runner.validate_hold_observation(
            u04,
            future_file,
            result_file,
            expected_hold_minutes=0,
            claim_registry=registry,
        )

    tampered = bytearray(hold0.read_bytes())
    tampered[-2] ^= 1
    tampered_file = tmp_path / "tampered-hold.json"
    tampered_file.write_bytes(tampered)
    with pytest.raises(runner.Ec5PhysicalError, match="integrity|JSON"):
        runner.validate_hold_observation(
            u04,
            tampered_file,
            result_file,
            expected_hold_minutes=0,
            claim_registry=registry,
        )

    with pytest.raises(runner.Ec5PhysicalError, match="already exists"):
        runner.record_hold_observation(
            u04,
            candidate_result_file=result_file,
            output_file=hold0,
            hold_minutes=0,
            temperature_c=37.0,
            confirmations=confirmation,
            claim_registry=registry,
        )


def test_u07_generic_hold_chain_replays_full_u04_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prerequisite = _u04_prerequisite(tmp_path, monkeypatch)
    u07 = prerequisite["u07"]
    registry = prerequisite["registry"]
    result_file = tmp_path / "u07-result-for-holds.json"
    u07_values = _device_values(u07)
    diagnostic = _diagnostic_evidence(tmp_path, u07, u07_values)
    u07_run_time = prerequisite["now"] + timedelta(minutes=1)
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: u07_run_time.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    )
    runner.run_once(
        u07,
        "http://192.168.4.1",
        authorization=runner.required_authorization(u07),
        result_file=result_file,
        diagnostic_preflight_file=diagnostic,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=ScriptedOpen(_successful_script(u07_values)),
        _sleep=lambda _seconds: None,
        **_u07_gate_kwargs(prerequisite),
    )
    finished = datetime.fromisoformat(
        json.loads(result_file.read_bytes())["finished_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    paths = {minute: tmp_path / f"u07-hold-{minute}.json" for minute in (0, 5, 30)}
    confirmation = {
        "visual_stable": True,
        "electrical_normal": True,
        "esp32_not_restarted": True,
        "no_uncommanded_refresh": True,
    }
    validation_kwargs = _u07_gate_kwargs(prerequisite)
    for minute, prior in ((0, {}), (5, {0: paths[0]}), (30, {0: paths[0], 5: paths[5]})):
        monkeypatch.setattr(
            runner,
            "_utc_now",
            lambda minute=minute: finished + timedelta(minutes=minute, seconds=1),
        )
        runner.record_hold_observation(
            u07,
            candidate_result_file=result_file,
            output_file=paths[minute],
            hold_minutes=minute,
            temperature_c=37.0,
            confirmations=confirmation,
            prior_hold_files=prior,
            claim_registry=registry,
            result_validation_kwargs=validation_kwargs,
        )
    monkeypatch.setattr(
        runner, "_utc_now", lambda: finished + timedelta(minutes=31)
    )
    reference = runner.validate_hold_observation(
        u07,
        paths[30],
        result_file,
        expected_hold_minutes=30,
        prior_hold_files={0: paths[0], 5: paths[5]},
        claim_registry=registry,
        result_validation_kwargs=validation_kwargs,
    )
    assert reference["hold_minutes"] == 30
    assert json.loads(paths[30].read_bytes())["candidate_id"] == "U07"

    after_u07_white = tmp_path / "after-u07-white-result.json"
    white_time = finished + timedelta(minutes=31)
    monkeypatch.setattr(
        white_runner,
        "_now",
        lambda: white_time.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    )
    white_runner.run_once(
        stage="after-u07",
        base_url="http://192.0.2.1",
        authorization=white_runner.required_authorization("after-u07"),
        panel_file=Path(u07.panel_file),
        rc2g_binary_file=FROZEN_BINARY,
        result_file=after_u07_white,
        release_file=u07.path,
        candidate_result_file=result_file,
        candidate_claim_registry=registry,
        u04_review_file=prerequisite["review"],
        u04_result_file=prerequisite["u04_result"],
        u04_hold_0_file=prerequisite["hold_0"],
        u04_hold_5_file=prerequisite["hold_5"],
        u04_hold_30_file=prerequisite["hold_30"],
        u04_white_recovery_result_file=prerequisite["white_result"],
        u04_rc2g_binary_file=FROZEN_BINARY,
        u04_white_claim_registry=prerequisite["white_registry"],
        claim_registry=prerequisite["white_registry"],
        requester=FakeRC2G(),
        sleeper=lambda _seconds: None,
    )

    stage_b_dir = tmp_path / "stage-b"
    stage_b_dir.mkdir()
    stage_b_context, _stage_b_release, _stage_b_panel = _sixstate_release(
        stage_b_dir, candidate="U07"
    )
    gate = sixstate_runner._validate_stage_a_gate(
        stage_b_context,
        {
            "release_file": u07.path,
            "u04_result_file": prerequisite["u04_result"],
            "u04_review_file": prerequisite["review"],
            "u04_hold_0_file": prerequisite["hold_0"],
            "u04_hold_5_file": prerequisite["hold_5"],
            "u04_hold_30_file": prerequisite["hold_30"],
            "after_u04_white_result_file": prerequisite["white_result"],
            "u07_result_file": result_file,
            "u07_hold_0_file": paths[0],
            "u07_hold_5_file": paths[5],
            "u07_hold_30_file": paths[30],
            "after_u07_white_result_file": after_u07_white,
            "candidate_claim_registry": registry,
            "white_claim_registry": prerequisite["white_registry"],
            "rc2g_binary_file": FROZEN_BINARY,
        },
    )
    assert gate is not None
    assert gate["gate_pass"] is True
    assert gate["after_u07_white"]["stage"] == "after-u07"


def test_cli_exposes_execution_and_review_finalization_without_escape_hatches() -> None:
    help_text = runner._parser().format_help()
    for command in (
        "describe",
        "diagnose-j2-off",
        "preflight",
        "run",
        "validate",
        "observe-hold",
        "finalize-u04-review",
    ):
        assert command in help_text
    for forbidden in ("--retry", "--recover", "--clear-claim", "--upload", "--flash"):
        assert forbidden not in help_text.lower()
