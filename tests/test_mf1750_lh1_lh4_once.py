from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import mf1750_lh1_lh4_once as once


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".test-output/offline/LH1_LH4_20260912_R1"
NATIVE = ROOT / ".test-output/offline/LH1_LH4_NATIVE_20260912_R1"
BASE_URL = "http://192.168.1.4"
BOOT = "0123456789abcdef"
ARM_NONCE = "fedcba9876543210"


def json_documents(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("{")
    ]


@pytest.fixture(autouse=True)
def no_live_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("a test attempted the real HTTP transport")

    monkeypatch.setattr(once, "_http", forbidden)
    monkeypatch.setattr(once.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(once, "CLAIM_ROOT", tmp_path / "permanent-claims")


@pytest.fixture(scope="module")
def real_context() -> dict:
    return once.validate_package(PACKAGE)


def identity_document(value: dict, ctx: dict, evidence: dict, *, latched: bool) -> dict:
    value = deepcopy(value)
    value.update(ctx["identity"])
    if "boot_nonce" in value:
        value["boot_nonce"] = evidence["boot_nonce"]
    if "persisted_campaign_boot_nonce" in value:
        value["persisted_campaign_boot_nonce"] = evidence["boot_nonce"]
    value.update(
        run_id=evidence["run_id"] if latched else "",
        source_review_sha256=evidence["source_review_sha256"] if latched else "",
        prior_review_sha256=evidence["source_review_sha256"] if latched else "",
    )
    return value


class FixtureDevice:
    """Actual generated JSON structure with explicitly synthetic BUSY evidence."""

    def __init__(self, ctx: dict, evidence: dict, *, busy: int = 1):
        self.ctx, self.evidence, self.busy = ctx, evidence, busy
        self.calls: list[tuple[str, str, dict, int]] = []
        self.phase = 0
        self.rewrite = None
        values = json_documents(NATIVE / "read_only.log")
        self.initial = {
            name: identity_document(value, ctx, evidence, latched=False)
            for name, value in zip(
                ("version", "manifest", "status", "report"), values, strict=True
            )
        }
        self.initial["status"]["busy"] = busy
        self.action = deepcopy(self.initial["manifest"]["actions"][0])
        for key in (
            "prior_static_action_id",
            "boot_admission",
            "frame_sha256",
            "cs1_dtm_sha256",
            "cs2_dtm_sha256",
            "transport_code_histogram",
        ):
            self.action.pop(key)
        report = json_documents(NATIVE / "chain.log")[0]
        self.terminal = identity_document(report, ctx, evidence, latched=True)
        self.terminal["driver"].update(spi_hz=1000000, operation_id=1)
        # Native protocol doubles leave every stage at 255. Supply clearly
        # synthetic stage samples here; none is saved as physical evidence.
        for name in ("pon", "drf", "pof"):
            self.terminal["driver"]["busy_stage_samples"][name] = {
                "gate_entry_level": 1,
                "pre_command_level": 1,
                "wait_entry_level": 0,
                "wait_exit_level": 1,
                "pre_command_idle_ok": True,
                "assertion_after_idle": True,
                "pre_command_wait_ms": 0,
                "wait_ms": 100,
                "assertion_latency_ms": 1,
            }
        self.terminal["driver"]["busy_stage_samples"]["reset"].update(
            wait_entry_level=0, wait_exit_level=1
        )
        self.terminal["driver"]["busy_stage_samples"]["post_psr"].update(
            pre_command_level=1,
            pre_command_idle_ok=True,
            wait_exit_level=1,
        )
        self.terminal["driver"]["safe_finish"] = {
            "busy_before_pins_low": 1,
            "busy_after_pins_low": 1,
            "busy_after_5ms": 1,
            "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
        }
        self.terminal.update(
            job_queued_at_ms=100, job_started_at_ms=101, job_finished_at_ms=401
        )
        self.final_status = identity_document(
            self.initial["status"], ctx, evidence, latched=True
        )
        self.final_status.update(
            cursor_raw=2,
            next_ordinal=2,
            persistent_key_present=True,
            arm_request_count=1,
            execute_request_count=1,
            total_driver_call_count=1,
            busy=1,
            rst=0,
            cs=0,
            cs2=0,
        )

    def acknowledgement(self, *, execute: bool) -> dict:
        identity = identity_document(
            self.initial["report"], self.ctx, self.evidence, latched=True
        )
        common = {
            key: identity[key]
            for key in (
                *self.ctx["identity"],
                "waveform_internal_phase",
                "qualified_count",
                "run_id",
                "source_review_sha256",
                "prior_review_sha256",
                "source_nvs_complete",
                "review_digests_are_host_assertions_only",
            )
        }
        common.update(self.action)
        common.update(accepted=True, boot_nonce=BOOT)
        if execute:
            common.update(
                job_id=1,
                execute_consumed=True,
                phase=2,
                phase_name="CONSUMED",
                no_retry=True,
                no_recovery=True,
            )
        else:
            common.update(
                armed=True,
                arm_nonce=ARM_NONCE,
                phase=1,
                phase_name="ARMED",
                not_hardware_authorization=True,
            )
        return common

    def __call__(self, method: str, url: str, headers: dict, timeout: int):
        route = url.rsplit("/", 1)[-1]
        self.calls.append((method, route, deepcopy(headers), timeout))
        if method == "POST":
            assert route in ("arm", "execute")
            self.phase = 1 if route == "arm" else 2
            status, value = (
                (201 if route == "arm" else 202),
                self.acknowledgement(execute=route == "execute"),
            )
        elif self.phase == 2 and route in ("status", "report"):
            status, value = (
                200,
                deepcopy(self.final_status if route == "status" else self.terminal),
            )
        else:
            status, value = 200, deepcopy(self.initial[route])
        if self.rewrite:
            status, value = self.rewrite(method, route, status, value)
        return status, once.canonical(value)


@pytest.fixture
def protocol(real_context: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    ctx = deepcopy(real_context)
    evidence = {
        "boot_nonce": BOOT,
        "run_id": "TEST_FIXTURE_LH1",
        "source_review_sha256": "a" * 64,
    }
    evidence_path = tmp_path / "TEST_FIXTURE_evidence.json"
    evidence_path.write_bytes(once.canonical(once.seal(evidence)))
    real_validate_evidence = once.validate_evidence
    monkeypatch.setattr(once, "validate_package", lambda package: ctx)
    monkeypatch.setattr(
        once, "validate_evidence", lambda *args, **kwargs: deepcopy(evidence)
    )
    off = FixtureDevice(ctx, evidence, busy=0)
    once.diagnose(PACKAGE, evidence_path, tmp_path / "diagnostic", BASE_URL, off)
    return SimpleNamespace(
        ctx=ctx,
        evidence=evidence,
        evidence_path=evidence_path,
        diagnostic=tmp_path / "diagnostic/diagnostic.json",
        root=tmp_path,
        real_validate_evidence=real_validate_evidence,
    )


def test_real_package_is_local_and_source_bound(real_context: dict) -> None:
    assert real_context["contract"]["action_count"] == 3
    assert real_context["source"]["firmware_sha256"] == once.WHITE_BIN
    assert real_context["source"]["firmware_elf_sha256"] == once.WHITE_ELF
    assert real_context["contract"]["nvs"] == {
        "namespace": "lhist_v1",
        "cursor": "cur_lh1",
        "boot": "boot_lh1",
    }


def test_corrupt_package_binding_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "bad-package"
    package.mkdir()
    for name in ("contract.json", "build-report.json"):
        (package / name).write_bytes((PACKAGE / name).read_bytes())
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("integrity")
    manifest["inputs"][0]["sha256"] = "0" * 64
    (package / "manifest.json").write_bytes(once.canonical(once.seal(manifest)))
    build = json.loads((PACKAGE / "build-report.json").read_text(encoding="utf-8"))
    build.pop("integrity")
    build["manifest"] = once.file_binding(package / "manifest.json")
    (package / "build-report.json").write_bytes(once.canonical(once.seal(build)))
    with pytest.raises(once.RunnerError, match="binding differs"):
        once.validate_package(package)


def test_copied_manifest_cannot_validate_other_directory(tmp_path: Path) -> None:
    for name in ("contract.json", "manifest.json", "build-report.json"):
        (tmp_path / name).write_bytes((PACKAGE / name).read_bytes())
    with pytest.raises(once.RunnerError, match="this package manifest"):
        once.validate_package(tmp_path)


def test_missing_package_stops_before_http(tmp_path: Path) -> None:
    calls = []
    with pytest.raises(once.RunnerError, match="missing"):
        once.diagnose(
            tmp_path / "missing",
            tmp_path / "none",
            tmp_path / "output",
            BASE_URL,
            lambda *args: calls.append(args),
        )
    assert calls == [] and not (tmp_path / "output").exists()


@pytest.mark.parametrize("ordinal", [0, 2, 3, 4, True, "1"])
def test_only_ordinal_one_admitted_before_package_or_http(
    ordinal, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        once,
        "validate_package",
        lambda *args: pytest.fail("package read before ordinal gate"),
    )
    with pytest.raises(once.RunnerError, match="ordinal 1"):
        once.run_source(
            tmp_path,
            tmp_path / "evidence",
            tmp_path / "diag",
            tmp_path / "out",
            BASE_URL,
            ordinal,
        )
    assert not (tmp_path / "out").exists()


def test_missing_local_evidence_stops_before_http(
    real_context: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once, "validate_package", lambda *args: real_context)
    calls = []
    with pytest.raises(once.RunnerError):
        once.diagnose(
            PACKAGE,
            tmp_path / "missing-evidence",
            tmp_path / "output",
            BASE_URL,
            lambda *args: calls.append(args),
        )
    assert calls == [] and not (tmp_path / "output").exists()


@pytest.fixture
def admission(real_context: dict, tmp_path: Path):
    """Synthetic local-only evidence graph; never saved under hardware outputs."""
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    ctx = real_context

    def raw(name: str, payload: bytes = b"TEST_FIXTURE_NOT_PHYSICAL_EVIDENCE") -> dict:
        path = tmp_path / name
        path.write_bytes(payload)
        return once.file_binding(path)

    records = {}

    def record(name: str, payload: dict) -> dict:
        records[name] = deepcopy(payload)
        path = tmp_path / (name + ".json")
        path.write_bytes(once.canonical(once.seal(payload)))
        return once.file_binding(path)

    raw_evidence = raw("TEST_FIXTURE_raw.txt")
    photo = raw("TEST_FIXTURE_photo.bin")
    sidecar = record(
        "capture_sidecar",
        {
            "recorded_at": stamp,
            "firmware_sha256": once.WHITE_BIN,
            "action_id": once.WHITE_ACTION,
            "image_sha256": photo["sha256"],
        },
    )
    current = record(
        "current_white_review",
        {
            "recorded_at": stamp,
            "kind": "mf1750-lh1-current-white-review-v1",
            "verdict": "PASS",
            "source_action_id": once.WHITE_ACTION,
            "source_firmware_sha256": once.WHITE_BIN,
            "full_panel_camera_coverage": True,
            "all_four_edges_visible": True,
            "camera_usb_id": "VID_32E4:PID_4801",
            "no_intervening_visible_refresh": True,
            "reviewer": "TEST_FIXTURE",
            "human_observation": "TEST_FIXTURE_NOT_A_REAL_OBSERVATION",
            "source_terminal": ctx["source"]["terminal_evidence"],
            "source_claim": ctx["source"]["claim_evidence"],
            "photo": photo,
            "capture_sidecar": sidecar,
        },
    )
    ip_raw = json.loads(
        (
            ROOT
            / ".test-output/hardware/MF1750_WHITE_RECOVERY_20260912_W0_LH4_V1/post-flash-exact-ipv4-mac-binding.json"
        ).read_text(encoding="utf-8")
    )
    ip_raw.pop("integrity")
    ip_raw.update(
        test_fixture_only=True,
        finished_at=stamp,
        output_file=str(tmp_path / "ipv4_mac_raw.json"),
    )
    probe_text = "TEST_FIXTURE_ONLY: exact candidate 192.168.1.4"
    ip_raw["active_probe"].update(
        stdout_utf8=probe_text,
        stdout_bytes=len(probe_text.encode()),
        stdout_sha256=once.digest(probe_text.encode()),
    )
    ip_raw_binding = record("ipv4_mac_raw", ip_raw)
    ip = record(
        "ipv4_mac_binding",
        {
            "recorded_at": stamp,
            "base_url": BASE_URL,
            "candidate_ipv4": "192.168.1.4",
            "expected_mac": "A4-CB-8F-D9-FC-D4",
            "fresh_binding_passed": True,
            "device_api_requests": 0,
            "mutation_requests": 0,
            "visible_refresh_requests": 0,
            "outcome": "active_exact_mac_binding_pass",
            "raw_evidence": ip_raw_binding,
        },
    )
    flash = record(
        "app_flash_record",
        {
            "recorded_at": stamp,
            "offset": "0x10000",
            "app_only": True,
            "verify_result": "PASS",
            "firmware_sha256": ctx["firmware"]["sha256"],
            "running_app_elf_sha256": ctx["elf"]["sha256"],
            "post_flash_boot_nonce": BOOT,
            "nvs_written": False,
            "raw_evidence": raw_evidence,
        },
    )
    electrical = record(
        "external_electrical",
        {
            "recorded_at": stamp,
            "instrument": "TEST_FIXTURE",
            "ground_reference": "TEST_FIXTURE_GND",
            "operator": "TEST_FIXTURE",
            "acceptance_basis": "TEST_FIXTURE_ONLY",
            "readings": [
                {
                    "point": "TEST_FIXTURE",
                    "unit": "V",
                    "value": 0.0,
                    "recorded_at": stamp,
                }
            ],
            "verdict": "PASS",
            "boot_nonce": BOOT,
            "phase": "off",
            "external_measurement": True,
            "run_id": "TEST_FIXTURE_LH1",
            "app_flash_record": flash,
        },
    )
    release = record(
        "user_release",
        {
            "recorded_at": (now - timedelta(days=1)).isoformat(),
            "contract_id": ctx["contract"]["contract_id"],
            "action_id": ctx["contract"]["actions"][0]["action_id"],
            "ordinal": 1,
            "run_id": "TEST_FIXTURE_LH1",
            "release": "SOURCE_ONCE_THEN_STOP",
            "operator": "TEST_FIXTURE",
            "actual_user_instruction": "TEST_FIXTURE_ONLY",
        },
    )
    relay = record(
        "relay_off",
        {
            "recorded_at": stamp,
            "commanded_state": "OFF",
            "independently_queried": True,
            "channel": 1,
            "boot_nonce": BOOT,
            "pnp_instance": "TEST_FIXTURE",
            "usb_location": "TEST_FIXTURE",
            "run_id": "TEST_FIXTURE_LH1",
            "app_flash_record": flash,
            "raw_evidence": raw_evidence,
        },
    )
    successor_bin, successor_elf = (
        raw("TEST_FIXTURE_successor.bin"),
        raw("TEST_FIXTURE_successor.elf"),
    )
    successor_contract = "b" * 64
    successor_build = record(
        "successor_build",
        {
            "result": "PASS",
            "contract_id": successor_contract,
            "artifacts": [successor_bin, successor_elf],
        },
    )
    successor_review = record(
        "successor_review",
        {
            "result": "PASS",
            "contract_id": successor_contract,
            "test_evidence": [raw_evidence],
        },
    )
    successor = record(
        "post_test_successor",
        {
            "kind": "mf1750-lh1-source-post-test-white-seal-v1",
            "result": "PASS",
            "contract_id": successor_contract,
            "source_contract_id": ctx["contract"]["contract_id"],
            "accepted_source_ordinals": [1],
            "source_action_id": ctx["contract"]["actions"][0]["action_id"],
            "live_action_authorized": False,
            "firmware": successor_bin,
            "elf": successor_elf,
            "build_report": successor_build,
            "independent_review": successor_review,
        },
    )
    action = ctx["contract"]["actions"][0]
    applicability = record(
        "profile_applicability_review",
        {
            "verdict": "PASS",
            "profile_id": action["profile_id"],
            "profile_sha256": action["profile_sha256"],
            "unresolved_applicability_questions": [],
            "reviewer": "TEST_FIXTURE",
            "mode_applicability_reasoning": "TEST_FIXTURE_ONLY",
            "reference_documents": [raw_evidence],
        },
    )
    evidence = {
        "kind": "mf1750-lh1-lh4-field-evidence-v1",
        "recorded_at": stamp,
        "contract_id": ctx["contract"]["contract_id"],
        "base_url": BASE_URL,
        "run_id": "TEST_FIXTURE_LH1",
        "boot_nonce": BOOT,
        "source_review_sha256": current["sha256"],
        "current_white_review": current,
        "ipv4_mac_binding": ip,
        "app_flash_record": flash,
        "external_electrical": electrical,
        "user_release": release,
        "relay_off": relay,
        "post_test_successor": successor,
        "profile_applicability_review": applicability,
    }
    path = tmp_path / "TEST_FIXTURE_field-evidence.json"
    path.write_bytes(once.canonical(once.seal(evidence)))
    return SimpleNamespace(
        ctx=ctx, records=records, record=record, evidence=evidence, path=path, now=now
    )


def test_local_evidence_graph_accepts_complete_synthetic_fixture(admission) -> None:
    value = once.validate_evidence(
        admission.ctx, admission.path, BASE_URL, now=admission.now
    )
    assert value["run_id"] == "TEST_FIXTURE_LH1"


@pytest.fixture
def generic_capture_admission(admission):
    current = deepcopy(admission.records["current_white_review"])
    anchor = admission.ctx["source"]["terminal_evidence"]
    value = json.loads(once.read_bound(anchor))
    value.pop("integrity")
    authenticated = {
        "usb_vid": "32E4",
        "usb_pid": "4801",
        "pnp_instance_id": "TEST_FIXTURE_CAMERA_PNP",
        "alternative_name": "TEST_FIXTURE_CAMERA_ALTERNATIVE_NAME",
    }
    stamp = admission.now.isoformat()
    sidecar = {
        "schema_version": 1,
        "kind": "mf1750-lh1-camera-capture",
        "run_id": "TEST_FIXTURE_LH1",
        "stage": "CURRENT_CAMERA_OBSERVATION",
        "historical_action_anchor": {
            "path": anchor["path"],
            "bytes": anchor["bytes"],
            "file_sha256": anchor["sha256"],
            "canonical_sha256": once.digest(once.canonical(value)),
        },
        "camera": {
            "id": "TEST_FIXTURE_48MP_USB_CAMERA",
            "usb_vid": "32E4",
            "usb_pid": "4801",
            "authenticated_before": authenticated,
            "authenticated_after": deepcopy(authenticated),
            "backend": "TEST_FIXTURE",
            "requested_settings": {},
            "effective_settings_before_frame": {},
            "effective_settings_after_frame": {},
            "set_results": {},
            "read_failures": 0,
            "warmup_frames_completed": 1,
            "manual_lock_proven": False,
            "raw_supported": False,
            "iso_supported": False,
            "hardware_trigger_supported": False,
        },
        "capture_timing": {
            "started_at": stamp,
            "frame_retrieved_at": stamp,
            "frame_retrieved_at_utc": stamp,
            "completed_at": stamp,
            "hardware_frame_timestamp": None,
        },
        "coverage": {
            "scope": "TEST_FIXTURE",
            "full_panel_validity": "UNKNOWN",
            "full_panel_validity_requires_review": True,
        },
        "photo": {**current["photo"], "origin": "TEST_FIXTURE_ONLY"},
        "observation": {
            "lab_space": "camera-relative",
            "calibrated_lab": False,
            "roi": None,
            "temperature_c": None,
            "candidate_lightness": None,
            "verdict": "INCONCLUSIVE",
        },
        "output_write_contract": "O_EXCL",
    }
    current["capture_sidecar"] = admission.record("capture_sidecar", sidecar)
    admission.evidence["current_white_review"] = admission.record(
        "current_white_review", current
    )
    admission.evidence["source_review_sha256"] = admission.evidence[
        "current_white_review"
    ]["sha256"]
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))
    return admission


def test_generic_capture_schema_uses_independent_current_review(
    generic_capture_admission,
) -> None:
    fixture = generic_capture_admission
    value = once.validate_evidence(fixture.ctx, fixture.path, BASE_URL, now=fixture.now)
    assert value["current_white_review"] == fixture.evidence["current_white_review"]
    assert (
        fixture.records["capture_sidecar"]["coverage"]["full_panel_validity"]
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "change",
    ["anchor", "camera_usb", "camera_changed", "neighbour_mac", "expired_photo"],
)
def test_generic_capture_rejects_wrong_anchor_camera_mac_or_old_photo_before_http(
    generic_capture_admission,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    change,
) -> None:
    fixture = generic_capture_admission
    sidecar = deepcopy(fixture.records["capture_sidecar"])
    if change == "anchor":
        sidecar["historical_action_anchor"]["canonical_sha256"] = "0" * 64
    elif change == "camera_usb":
        sidecar["camera"]["usb_pid"] = "0000"
    elif change == "camera_changed":
        sidecar["camera"]["authenticated_after"]["pnp_instance_id"] = (
            "TEST_OTHER_CAMERA"
        )
    elif change == "expired_photo":
        sidecar["capture_timing"]["frame_retrieved_at_utc"] = (
            fixture.now - timedelta(seconds=once.EVIDENCE_MAX_AGE_SECONDS + 1)
        ).isoformat()
    else:
        raw = deepcopy(fixture.records["ipv4_mac_raw"])
        raw["neighbour_entries"][0]["LinkLayerAddress"] = "00-00-00-00-00-00"
        ip = deepcopy(fixture.records["ipv4_mac_binding"])
        ip["raw_evidence"] = fixture.record("ipv4_mac_raw", raw)
        fixture.evidence["ipv4_mac_binding"] = fixture.record("ipv4_mac_binding", ip)
    current = deepcopy(fixture.records["current_white_review"])
    current["capture_sidecar"] = fixture.record("capture_sidecar", sidecar)
    fixture.evidence["current_white_review"] = fixture.record(
        "current_white_review", current
    )
    fixture.evidence["source_review_sha256"] = fixture.evidence["current_white_review"][
        "sha256"
    ]
    fixture.path.write_bytes(once.canonical(once.seal(fixture.evidence)))
    monkeypatch.setattr(once, "validate_package", lambda *args: fixture.ctx)
    calls = []
    with pytest.raises(once.RunnerError):
        once.diagnose(
            PACKAGE,
            fixture.path,
            tmp_path / "generic-diagnostic",
            BASE_URL,
            lambda *args: calls.append(args),
        )
    assert calls == [] and not (tmp_path / "generic-diagnostic").exists()


def null_boot_evidence(admission) -> None:
    admission.evidence["boot_nonce"] = None
    flash = deepcopy(admission.records["app_flash_record"])
    flash["post_flash_boot_nonce"] = None
    admission.evidence["app_flash_record"] = admission.record("app_flash_record", flash)
    for name in ("external_electrical", "relay_off"):
        value = deepcopy(admission.records[name])
        value.update(
            boot_nonce=None, app_flash_record=admission.evidence["app_flash_record"]
        )
        admission.evidence[name] = admission.record(name, value)
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))


def test_null_boot_off_admission_is_bound_by_exact_four_get(
    admission, tmp_path: Path
) -> None:
    null_boot_evidence(admission)
    device_evidence = {**admission.evidence, "boot_nonce": BOOT}
    fake = FixtureDevice(admission.ctx, device_evidence, busy=0)
    result = once.diagnose(
        PACKAGE, admission.path, tmp_path / "first-boot-diagnostic", BASE_URL, fake
    )
    assert result["boot_nonce"] == BOOT
    assert result["network"] == {"get": 4, "post": 0}
    assert len(fake.calls) == 4 and all(
        method == "GET" for method, _, _, _ in fake.calls
    )
    assert once.read_record(admission.path)["boot_nonce"] is None
    assert not once.claim_path(admission.ctx).exists()


def test_null_boot_first_get_rejects_disagreement_after_four_reads(
    admission, tmp_path: Path
) -> None:
    null_boot_evidence(admission)
    fake = FixtureDevice(
        admission.ctx, {**admission.evidence, "boot_nonce": BOOT}, busy=0
    )
    fake.initial["report"]["boot_nonce"] = "f" * 16
    output = tmp_path / "mismatched-boot"
    with pytest.raises(once.RunnerError, match="boot binding"):
        once.diagnose(PACKAGE, admission.path, output, BASE_URL, fake)
    assert len(fake.calls) == 4 and all(
        method == "GET" for method, _, _, _ in fake.calls
    )
    assert not (output / "diagnostic.json").exists()
    assert not once.claim_path(admission.ctx).exists()


def test_null_boot_cannot_admit_j2_on_action(admission) -> None:
    null_boot_evidence(admission)
    with pytest.raises(once.RunnerError):
        once.validate_evidence(
            admission.ctx, admission.path, BASE_URL, phase="on", now=admission.now
        )


@pytest.mark.parametrize(
    "record_name,field,bad",
    [
        ("current_white_review", "full_panel_camera_coverage", False),
        ("current_white_review", "camera_usb_id", "VID_0000:PID_0000"),
        ("app_flash_record", "post_flash_boot_nonce", "f" * 16),
        ("app_flash_record", "nvs_written", True),
        ("external_electrical", "readings", []),
        ("external_electrical", "phase", "on"),
        ("ipv4_mac_binding", "expected_mac", "00-00-00-00-00-00"),
        ("post_test_successor", "live_action_authorized", True),
        (
            "profile_applicability_review",
            "unresolved_applicability_questions",
            ["TEST_UNRESOLVED"],
        ),
    ],
)
def test_real_local_evidence_validator_refuses_missing_physical_or_lineage_data(
    admission, record_name, field, bad
) -> None:
    document = deepcopy(admission.records[record_name])
    document[field] = bad
    admission.evidence[record_name] = admission.record(record_name, document)
    if record_name == "current_white_review":
        admission.evidence["source_review_sha256"] = admission.evidence[record_name][
            "sha256"
        ]
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))
    with pytest.raises(once.RunnerError):
        once.validate_evidence(
            admission.ctx, admission.path, BASE_URL, now=admission.now
        )


def test_expired_field_evidence_is_not_reused(admission) -> None:
    admission.evidence["recorded_at"] = (
        admission.now - timedelta(seconds=once.EVIDENCE_MAX_AGE_SECONDS + 1)
    ).isoformat()
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))
    with pytest.raises(once.RunnerError, match="expired"):
        once.validate_evidence(
            admission.ctx, admission.path, BASE_URL, now=admission.now
        )


def test_bad_local_file_hash_stops_before_http(
    admission, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admission.evidence["external_electrical"]["sha256"] = "0" * 64
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))
    monkeypatch.setattr(once, "validate_package", lambda *args: admission.ctx)
    calls = []
    with pytest.raises(once.RunnerError, match="binding differs"):
        once.diagnose(
            PACKAGE,
            admission.path,
            tmp_path / "diagnostic",
            BASE_URL,
            lambda *args: calls.append(args),
        )
    assert calls == [] and not (tmp_path / "diagnostic").exists()


@pytest.mark.parametrize("change", ["neighbour_mac", "probe_bytes", "local_interface"])
def test_bad_raw_ipv4_mac_binding_stops_before_http(
    admission, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change
) -> None:
    raw = deepcopy(admission.records["ipv4_mac_raw"])
    if change == "neighbour_mac":
        raw["neighbour_entries"][0]["LinkLayerAddress"] = "00-00-00-00-00-00"
    elif change == "probe_bytes":
        raw["active_probe"]["stdout_bytes"] += 1
    else:
        raw["neighbour_entries"][0]["ifIndex"] = 987654
    ip = deepcopy(admission.records["ipv4_mac_binding"])
    ip["raw_evidence"] = admission.record("ipv4_mac_raw", raw)
    admission.evidence["ipv4_mac_binding"] = admission.record("ipv4_mac_binding", ip)
    admission.path.write_bytes(once.canonical(once.seal(admission.evidence)))
    monkeypatch.setattr(once, "validate_package", lambda *args: admission.ctx)
    calls = []
    with pytest.raises(once.RunnerError):
        once.diagnose(
            PACKAGE,
            admission.path,
            tmp_path / "diagnostic",
            BASE_URL,
            lambda *args: calls.append(args),
        )
    assert calls == [] and not (tmp_path / "diagnostic").exists()


@pytest.mark.parametrize(
    "document,field,bad",
    [
        ("version", "schema_version", "3"),
        ("version", "kind", "other"),
        ("version", "driver_api_version", "OTHER_DRIVER"),
        ("version", "layout_id", "OTHER_LAYOUT"),
        ("version", "partial_refresh", True),
        ("version", "full_screen_global_refresh", False),
        ("manifest", "runtime_lut_write", False),
        ("manifest", "synchronous_both_controllers", False),
        ("status", "boot_nonce", "f" * 16),
        ("status", "busy", 255),
        ("status", "arm_request_count", 1),
        ("report", "valid", True),
    ],
)
def test_four_get_rejects_wrong_schema_boot_busy_or_history(
    real_context: dict, document, field, bad
) -> None:
    evidence = {
        "boot_nonce": BOOT,
        "run_id": "TEST_FIXTURE_LH1",
        "source_review_sha256": "a" * 64,
    }
    fake = FixtureDevice(real_context, evidence)
    values = deepcopy(fake.initial)
    values[document][field] = bad
    with pytest.raises(once.RunnerError):
        once.validate_four_get(real_context, values, evidence, busy=1)


def test_j2_off_diagnostic_has_four_get_no_claim(protocol) -> None:
    diagnostic = once.read_record(protocol.diagnostic)
    assert diagnostic["network"] == {"get": 4, "post": 0}
    assert diagnostic["busy"] == 0 and diagnostic["claim_created"] is False
    assert diagnostic["driver_calls"] == diagnostic["visible_refreshes"] == 0
    assert len(diagnostic["transcripts"]) == 8
    assert not once.claim_path(protocol.ctx).exists()


@pytest.mark.parametrize("field", ["app_flash_record", "current_white_review"])
def test_on_evidence_cannot_change_diagnostic_session_binding(protocol, field) -> None:
    protocol.evidence[field] = {
        "path": "TEST_DIFFERENT",
        "bytes": 0,
        "sha256": "0" * 64,
    }
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    with pytest.raises(once.RunnerError, match="changed diagnostic session"):
        once.run_source(
            PACKAGE,
            protocol.evidence_path,
            protocol.diagnostic,
            protocol.root / "changed-session",
            BASE_URL,
            transport=fake,
        )
    assert fake.calls == [] and not once.claim_path(protocol.ctx).exists()


def test_source_201_202_stops_after_one_refresh_and_persists_claim(protocol) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    result = once.run_source(
        PACKAGE,
        protocol.evidence_path,
        protocol.diagnostic,
        protocol.root / "source",
        BASE_URL,
        transport=fake,
    )
    assert result["outcome"] == "complete_pass"
    assert result["network"] == {"get": 6, "post": 2}
    assert result["driver_calls"] == result["visible_refreshes"] == 1
    assert result["qualified_count"] == 0 and result["next_action_authorized"] is False
    assert result["stop_and_review_required"] is True
    posts = [
        (route, headers) for method, route, headers, _ in fake.calls if method == "POST"
    ]
    assert [route for route, _ in posts] == ["arm", "execute"]
    assert posts[0][1]["X-EC5-Intent"] == protocol.ctx["arm_intent"]
    assert posts[1][1]["X-EC5-Intent"] == protocol.ctx["execute_intent"]
    assert "X-EC5-Arm-Nonce" not in posts[0][1]
    assert posts[1][1]["X-EC5-Arm-Nonce"] == ARM_NONCE
    for _, headers in posts:
        assert headers["X-EC5-Ordinal"] == "1"
        assert headers["X-LH-Prior-Review"] == headers["X-LH-Source-Review"] == "a" * 64
        assert not {"Content-Type", "Transfer-Encoding", "Content-Length"}.intersection(
            headers
        )
    assert (
        once.read_record(once.claim_path(protocol.ctx))["state"]
        == "permanently_consumed_before_first_arm"
    )


@pytest.mark.parametrize("route,status", [("arm", 200), ("execute", 201)])
def test_wrong_ack_status_leaves_permanent_claim_without_retry(
    protocol, route: str, status: int
) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    fake.rewrite = lambda method, name, code, value: (
        status if method == "POST" and name == route else code,
        value,
    )
    output = protocol.root / "failed-source"
    with pytest.raises(once.RunnerError, match="HTTP"):
        once.run_source(
            PACKAGE,
            protocol.evidence_path,
            protocol.diagnostic,
            output,
            BASE_URL,
            transport=fake,
        )
    assert [name for method, name, _, _ in fake.calls if method == "POST"] == (
        ["arm"] if route == "arm" else ["arm", "execute"]
    )
    assert once.claim_path(protocol.ctx).exists() and (output / "STOP.json").exists()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("sequence_ok", False),
        ("input_fnv1a", 0),
        ("wait_timeout", True),
        ("failure_code", 9),
    ],
)
def test_terminal_driver_failure_refused(protocol, field: str, bad) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    fake.terminal["driver"][field] = bad
    with pytest.raises(once.RunnerError):
        once.validate_terminal(
            protocol.ctx, fake.terminal, fake.final_status, protocol.evidence
        )


@pytest.mark.parametrize("field,bad", [("spi_hz", 0), ("operation_id", 2)])
def test_terminal_driver_frequency_and_operation_identity(protocol, field, bad) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    fake.terminal["driver"][field] = bad
    with pytest.raises(once.RunnerError):
        once.validate_terminal(
            protocol.ctx, fake.terminal, fake.final_status, protocol.evidence
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("pre_command_level", 0),
        ("wait_exit_level", 0),
        ("assertion_after_idle", False),
        ("gate_entry_level", 255),
        ("wait_ms", -1),
    ],
)
def test_terminal_busy_evidence_refused(protocol, field: str, bad) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    fake.terminal["driver"]["busy_stage_samples"]["drf"][field] = bad
    with pytest.raises(once.RunnerError):
        once.validate_terminal(
            protocol.ctx, fake.terminal, fake.final_status, protocol.evidence
        )


@pytest.mark.parametrize("part", ["reset", "post_psr", "safe_finish", "final_gpio"])
def test_terminal_requires_reset_post_psr_and_safe_gpio(protocol, part) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    if part in ("reset", "post_psr"):
        fake.terminal["driver"]["busy_stage_samples"][part]["wait_exit_level"] = 255
    elif part == "safe_finish":
        fake.terminal["driver"]["safe_finish"]["busy_after_5ms"] = 0
    else:
        fake.final_status["rst"] = 1
    with pytest.raises(once.RunnerError):
        once.validate_terminal(
            protocol.ctx, fake.terminal, fake.final_status, protocol.evidence
        )


@pytest.mark.parametrize("field", ["wait_entry_level", "wait_exit_level"])
def test_reset_raw_busy_boolean_is_not_an_integer_sample(protocol, field) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    fake.terminal["driver"]["busy_stage_samples"]["reset"][field] = True
    with pytest.raises(once.RunnerError):
        once.validate_terminal(
            protocol.ctx, fake.terminal, fake.final_status, protocol.evidence
        )


@pytest.mark.parametrize(
    "field,bad",
    [("schema_version", 99), ("boot_nonce", None), ("total_driver_call_count", 2)],
)
def test_invalid_poll_stops_without_repeating_mutations(protocol, field, bad) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)

    def rewrite(method, route, status, value):
        if method == "GET" and route == "status" and fake.phase == 2:
            value.update(phase=2, next_ordinal=1)
            if bad is None:
                value.pop(field)
            else:
                value[field] = bad
        return status, value

    fake.rewrite = rewrite
    output = protocol.root / "invalid-poll"
    with pytest.raises(once.RunnerError):
        once.run_source(
            PACKAGE,
            protocol.evidence_path,
            protocol.diagnostic,
            output,
            BASE_URL,
            transport=fake,
        )
    assert [route for method, route, _, _ in fake.calls if method == "POST"] == [
        "arm",
        "execute",
    ]
    assert len(fake.calls) == 7
    assert once.claim_path(protocol.ctx).exists() and (output / "STOP.json").exists()


def test_different_output_cannot_reuse_source_claim(
    protocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FixtureDevice(protocol.ctx, protocol.evidence)
    once.run_source(
        PACKAGE,
        protocol.evidence_path,
        protocol.diagnostic,
        protocol.root / "first",
        BASE_URL,
        transport=fake,
    )
    claim = once.claim_path(protocol.ctx)
    original_claim = claim.read_bytes()
    # Exercise the real admission guard, retaining its source-wide claim rule.
    monkeypatch.setattr(once, "validate_evidence", protocol.real_validate_evidence)
    monkeypatch.setattr(once, "_source_evidence", lambda ctx: {})
    second = FixtureDevice(protocol.ctx, protocol.evidence)
    with pytest.raises(once.RunnerError, match="permanently claimed"):
        once.run_source(
            PACKAGE,
            protocol.evidence_path,
            protocol.diagnostic,
            protocol.root / "different-output",
            BASE_URL,
            transport=second,
        )
    assert second.calls == [] and not (protocol.root / "different-output").exists()
    assert claim.read_bytes() == original_claim


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"not-json"])
def test_strict_json_rejects_ambiguous_responses(raw: bytes) -> None:
    with pytest.raises(once.RunnerError):
        once.parse_json(raw)
