from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.parse

import pytest

from tools import mf1750_ec5_sixstate_nodither as assets
from tools import mf1750_ec5_sixstate_physical_once as runner
from tools import mf1750_ec5_sixstate_release as release


PANEL = {
    "board_id": "ESP32-C73",
    "model": "MF1750-C73",
    "pcb_revision": "rev-a1",
    "serial": "MF750M009T6420/1582643AGY44",
}
BOOT = "0123456789abcdef"
ARM = "fedcba9876543210"


def _source_snapshot() -> dict:
    return {
        "git_head": "a" * 40,
        "git_dirty": True,
        "git_status_sha256": runner.sha256(b" M test\n"),
        "git_status_line_count": 1,
        "relevant_sources": [
            {"path": path, "bytes": (runner.REPO_ROOT / path).stat().st_size, "sha256": runner.sha256((runner.REPO_ROOT / path).read_bytes())}
            for path in runner.SOURCE_PATHS
        ],
    }


def _firmware(candidate_id: str) -> bytes:
    variant = runner.FROZEN_VARIANTS[candidate_id]
    tokens = {variant["build_tag"], variant["test_id"], variant["layout_id"]}
    for action in runner.expected_actions(candidate_id):
        tokens.update((action["action_id"], action["frame_sha256"], action["cs1_dtm_sha256"]))
    return (candidate_id + "\0" + "\0".join(sorted(tokens))).encode("ascii")


def _release(tmp_path: Path, candidate: str = "U04", *, verify_panel: bool = True) -> tuple[runner.ReleaseContext, Path, Path]:
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    asset_input = tmp_path / "asset-input"
    asset_input.mkdir()
    manifests = {"U04": assets.generate_bundle(asset_input, 4), "U07": assets.generate_bundle(asset_input, 7)}
    binaries = {}
    for tag in ("U04", "U07"):
        path = tmp_path / f"{tag}.bin"
        path.write_bytes(_firmware(tag))
        binaries[tag] = path
    manifest, payloads = release.build_release(
        panel_file=panel,
        u04_binary=binaries["U04"],
        u07_binary=binaries["U07"],
        u04_asset_manifest=manifests["U04"],
        u07_asset_manifest=manifests["U07"],
        created_at="2026-08-09T12:00:00+08:00",
        _source_snapshot=_source_snapshot(),
    )
    release_file = release.publish_release(tmp_path / "release", manifest, payloads)
    context = runner.load_release(release_file, candidate, panel_file=panel if verify_panel else None)
    return context, release_file, panel


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
        self.requests.append({"method": method, "path": path, "data": request.data, "headers": {key.lower(): value for key, value in request.header_items()}})
        if not self.script:
            raise AssertionError(f"unexpected request {method} {path}")
        expected_method, expected_path, value = self.script.pop(0)
        assert (method, path) == (expected_method, expected_path)
        if isinstance(value, Exception):
            raise value
        return Response(value)


def _busy_stage(asserted: bool = True) -> dict:
    return {
        "gate_entry_level": 1,
        "pre_command_level": 1,
        "wait_entry_level": 0 if asserted else 1,
        "wait_exit_level": 1,
        "pre_command_idle_ok": True,
        "assertion_after_idle": asserted,
        "pre_command_wait_ms": 0,
        "wait_ms": 10,
        "assertion_latency_ms": 1 if asserted else 0,
    }


def _device(context: runner.ReleaseContext, ordinal: int) -> dict[str, dict]:
    variant = runner.FROZEN_VARIANTS[context.candidate_id]
    action = context.actions[ordinal - 1]
    gpio = {"initialized": True, "busy": 1, "rst": 0, "cs1": 0, "cs2": 0}

    def status(state: str, pending: str, next_ordinal: int, driver_called: bool, total: int, cooldown: int) -> dict:
        following = context.actions[next_ordinal - 1] if next_ordinal <= 9 else None
        return {
            "schema_version": 1,
            "kind": "mf1750-ec5-sixstate-status",
            "build_tag": variant["build_tag"],
            "test_id": variant["test_id"],
            "boot_nonce": BOOT,
            "candidate_code": variant["candidate_code"],
            "state": state,
            "next_ordinal": next_ordinal,
            "next_round": following["round"] if following else 0,
            "next_role": following["role"] if following else None,
            "next_action_id": following["action_id"] if following else None,
            "pending_phase": pending,
            "fixture_self_check_passed": True,
            "execute_pending": False,
            "current_action_driver_called": driver_called,
            "total_driver_calls_this_boot": total,
            "cooldown_ms": 150000,
            "cooldown_remaining_ms": cooldown,
            "gpio": dict(gpio),
            "no_retry": True,
            "no_recovery": True,
        }

    version = {
        "schema_version": 1,
        "kind": "mf1750-ec5-sixstate-version",
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "candidate_id": context.candidate_id,
        "candidate_code": f"0x{variant['candidate_code']:x}",
        "driver_api_version": runner.EXPECTED_DRIVER_API_VERSION,
        "layout_id": runner.LAYOUT_ID,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "lut_modification": False,
        "automatic_execute": False,
        "fixed_action_count": 9,
        "cooldown_ms": 150000,
        "persistent_progress": True,
        "retry": False,
        "recovery": False,
        "not_hardware_authorization": True,
    }
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-ec5-sixstate-manifest",
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "candidate_id": context.candidate_id,
        "candidate_code": variant["candidate_code"],
        "layout_id": runner.LAYOUT_ID,
        "geometry": {"width": 1024, "height": 600, "frame_bytes": 307200, "packing": "row_major_4bpp_even_x_high_nibble", "roi_count": 12, "roi_width": 24, "roi_height": 24, "candidate_pixels": 6912, "background_code": 1},
        "initial_codes": [1, 0, 3, 2, 5, 6],
        "y0": [48, 144, 240, 336, 432, 528],
        "roi_x0": {"cs1": 244, "cs2": 756},
        "mapping_cs1": [0, 0, 0, 0],
        "mapping_cs2": [1, 0, 0, 0],
        "sequence": [dict(item) for item in context.actions],
        "safety": {"dithering": False, "spatial_mixing": False, "uniform_single_code_rois": True, "bodyless_mutations": True, "exact_build_test_action_ordinal_boot_arm_nonce": True, "claim_before_driver": True, "max_driver_calls_per_action": 1, "cooldown_from_previous_completion_ms": 150000, "reboot_cooldown_is_conservatively_restarted": True, "network_reset_clear_retry_recovery_routes": False, "not_hardware_authorization": True},
    }
    ready = status("ready", "virgin", ordinal, False, 0, 0)
    no_report = {"schema_version": 1, "kind": "mf1750-ec5-sixstate-report", "valid": False, "terminal_state": "NOT_EXECUTED", "error": "no_execute_report", "build_tag": variant["build_tag"], "test_id": variant["test_id"], "boot_nonce": BOOT, "candidate_code": variant["candidate_code"], "next_ordinal": ordinal, "next_action_id": action["action_id"], "pending_phase": "virgin", "driver_called": False, "no_retry": True, "no_recovery": True}
    arm = {"accepted": True, "armed": True, "build_tag": variant["build_tag"], "test_id": variant["test_id"], "ordinal": ordinal, "round": action["round"], "role": action["role"], "action_id": action["action_id"], "boot_nonce": BOOT, "arm_nonce": ARM, "persistent_phase": "claimed", "not_hardware_authorization": True}
    armed = status("armed", "claimed", ordinal, False, 0, 0)
    execute = {"accepted": True, "queued": True, "build_tag": variant["build_tag"], "test_id": variant["test_id"], "boot_nonce": BOOT, "candidate_code": variant["candidate_code"], "ordinal": ordinal, "round": action["round"], "role": action["role"], "action_id": action["action_id"], "execute_consumed": True, "no_retry": True, "no_recovery": True}
    terminal = status("campaign_complete" if ordinal == 9 else "cooldown", "virgin", ordinal + 1, True, 1, 0 if ordinal == 9 else 149000)
    driver = {
        "operation_id": ordinal,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timed_out": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "mapping_applied": True,
        "input_frame_fnv1a": action["frame_fnv1a"],
        "cs1_dtm_fnv1a": action["cs1_dtm_fnv1a"],
        "cs2_dtm_fnv1a": action["cs2_dtm_fnv1a"],
        "spi_hz": 1000000,
        "total_ms": 100,
        "upload_ms": {"cs1": 10, "cs2": 10},
        "busy_seen": {"pon": True, "drf": True, "pof": True, "post_psr": False},
        "busy_stages": {name: _busy_stage(name != "post_psr") for name in ("reset", "pon", "drf", "pof", "post_psr")},
        "wait_ms": {"pon": 10, "drf": 10, "pof": 10, "post_psr": 0},
        "last_wait_stage": "post_psr",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "safe_finish": {"busy_before_pins_low": 1, "busy_after_pins_low": 1, "busy_after_5ms": 1, "final_gpio": {"busy": 1, "rst": 0, "cs1": 0, "cs2": 0}},
    }
    expected_identity = {key: action[key] for key in ("frame_sha256", "frame_fnv1a", "cs1_dtm_sha256", "cs2_dtm_sha256", "cs1_dtm_fnv1a", "cs2_dtm_fnv1a")}
    report = {"schema_version": 1, "kind": "mf1750-ec5-sixstate-report", "valid": True, "build_tag": variant["build_tag"], "test_id": variant["test_id"], "boot_nonce": BOOT, "candidate_code": variant["candidate_code"], "ordinal": ordinal, "round": action["round"], "role": action["role"], "action_id": action["action_id"], "terminal_state": "COMPLETED", "result": True, "driver_called": True, "driver_call_count_for_action": 1, "expected_identity": expected_identity, "next_ordinal": ordinal + 1, "pending_phase": "virgin", "cooldown_ms": 0 if ordinal == 9 else 150000, "job_queued_at_ms": 1, "job_started_at_ms": 2, "job_finished_at_ms": 102, "no_retry": True, "no_recovery": True, "driver": driver}
    return {"version": version, "manifest": manifest, "ready": ready, "no_report": no_report, "arm": arm, "armed": armed, "execute": execute, "terminal": terminal, "report": report}


def _preflight_script(values: dict) -> list[tuple[str, str, dict | Exception]]:
    return [("GET", runner._ENDPOINTS[name], values["no_report" if name == "report" else ("ready" if name == "status" else name)]) for name in ("version", "manifest", "status", "report")]


def _success_script(values: dict, execute_value: dict | Exception | None = None) -> list[tuple[str, str, dict | Exception]]:
    return _preflight_script(values) + [
        ("POST", runner._ENDPOINTS["arm"], values["arm"]),
        ("GET", runner._ENDPOINTS["status"], values["armed"]),
        ("POST", runner._ENDPOINTS["execute"], values["execute"] if execute_value is None else execute_value),
        ("GET", runner._ENDPOINTS["status"], values["terminal"]),
        ("GET", runner._ENDPOINTS["report"], values["report"]),
    ]


def _clock(*values: datetime):
    iterator = iter(values)
    return lambda: next(iterator)


def _run_action(
    context: runner.ReleaseContext,
    tmp_path: Path,
    ordinal: int,
    started: datetime,
    *,
    registry: Path,
    prior_result: Path | None = None,
    target_observation: Path | None = None,
    white_recovery: Path | None = None,
) -> Path:
    values = _device(context, ordinal)
    result_file = tmp_path / f"result-{ordinal}.json"
    runner.run_once(
        context,
        "http://device",
        ordinal,
        authorization=runner.required_authorization(context, ordinal),
        result_file=result_file,
        prior_result_file=prior_result,
        prior_target_observation_file=target_observation,
        prior_white_recovery_file=white_recovery,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=ScriptedOpen(_success_script(values)),
        _sleep=lambda _: None,
        _utcnow=_clock(started, started, started + timedelta(seconds=1)),
    )
    return result_file


def test_success_is_one_bodyless_arm_execute_and_result_replays(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    values = _device(context, 1)
    opener = ScriptedOpen(_success_script(values))
    registry = tmp_path / "claims"
    result_file = tmp_path / "result.json"
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    result = runner.run_once(
        context,
        "http://192.168.4.1",
        1,
        authorization=runner.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        poll_count=1,
        poll_interval_seconds=0,
        _urlopen=opener,
        _sleep=lambda _seconds: None,
        _utcnow=_clock(t0, t0, t0 + timedelta(seconds=1)),
    )
    assert result["outcome"] == "complete_pass"
    posts = [request for request in opener.requests if request["method"] == "POST"]
    assert [request["path"] for request in posts] == [runner._ENDPOINTS["arm"], runner._ENDPOINTS["execute"]]
    assert all(request["data"] is None for request in posts)
    assert posts[0]["headers"]["x-ec5-ordinal"] == "1"
    assert posts[1]["headers"]["x-ec5-arm-nonce"] == ARM
    assert runner.validate_result(context, result_file, claim_registry=registry)["outcome"] == "complete_pass"


def test_execute_reply_timeout_uses_get_only_and_never_reposts(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    values = _device(context, 1)
    opener = ScriptedOpen(_success_script(values, TimeoutError("reply lost")))
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    result = runner.run_once(
        context, "http://device", 1,
        authorization=runner.required_authorization(context, 1),
        result_file=tmp_path / "result.json", claim_registry=tmp_path / "claims",
        poll_count=1, poll_interval_seconds=0, _urlopen=opener, _sleep=lambda _: None,
        _utcnow=_clock(t0, t0, t0 + timedelta(seconds=1)),
    )
    assert result["outcome"] == "complete_pass"
    assert result["device"]["execute_response"] is None
    assert len([item for item in opener.requests if item["path"] == runner._ENDPOINTS["execute"]]) == 1
    assert [item["method"] for item in opener.requests[-2:]] == ["GET", "GET"]


def test_unverified_panel_is_zero_network_and_zero_claim(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path, verify_panel=False)
    opener = ScriptedOpen([])
    with pytest.raises(runner.SixStatePhysicalError, match="verified"):
        runner.run_once(
            context, "http://device", 1,
            authorization=runner.required_authorization(context, 1),
            result_file=tmp_path / "result.json", claim_registry=tmp_path / "claims",
            _urlopen=opener,
        )
    assert opener.requests == []
    assert not (tmp_path / "claims").exists()


def test_u07_missing_or_self_signed_fake_stage_a_evidence_is_zero_network(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path, candidate="U07")
    opener = ScriptedOpen([])
    common = {
        "authorization": runner.required_authorization(context, 1),
        "result_file": tmp_path / "result.json",
        "claim_registry": tmp_path / "claims",
        "_urlopen": opener,
    }
    with pytest.raises(runner.SixStatePhysicalError, match="requires real Stage-A"):
        runner.run_once(context, "http://device", 1, **common)
    assert opener.requests == [] and not (tmp_path / "claims").exists()

    fake = tmp_path / "fake.json"
    fake.write_text(json.dumps({"integrity": {"canonical_sha256": "a" * 64}}), encoding="utf-8")
    registry = tmp_path / "fake-registry"
    registry.mkdir()
    evidence = {
        "stage_a_release_file": fake,
        "stage_a_u04_result_file": fake,
        "stage_a_u04_review_file": fake,
        "stage_a_u04_hold_0_file": fake,
        "stage_a_u04_hold_5_file": fake,
        "stage_a_u04_hold_30_file": fake,
        "stage_a_after_u04_white_result_file": fake,
        "stage_a_u07_result_file": fake,
        "stage_a_u07_hold_0_file": fake,
        "stage_a_u07_hold_5_file": fake,
        "stage_a_u07_hold_30_file": fake,
        "stage_a_after_u07_white_result_file": fake,
        "stage_a_candidate_claim_registry": registry,
        "stage_a_white_claim_registry": registry,
        "stage_a_rc2g_binary_file": fake,
    }
    with pytest.raises(runner.SixStatePhysicalError, match="replay failed"):
        runner.run_once(context, "http://device", 1, **common, **evidence)
    assert opener.requests == [] and not (tmp_path / "claims").exists()


@pytest.mark.parametrize("field,value", [("busy", 0), ("rst", 1), ("cs1", 1), ("cs2", 1)])
def test_unsafe_ready_gpio_rejects_before_claim(field: str, value: int, tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    values = _device(context, 1)
    values["ready"]["gpio"][field] = value
    opener = ScriptedOpen(_preflight_script(values))
    with pytest.raises(runner.SixStatePhysicalError, match="safe idle"):
        runner.run_once(
            context, "http://device", 1,
            authorization=runner.required_authorization(context, 1),
            result_file=tmp_path / "result.json", claim_registry=tmp_path / "claims",
            _urlopen=opener,
        )
    assert not (tmp_path / "claims").exists()
    assert all(item["method"] == "GET" for item in opener.requests)


def test_unsafe_armed_gpio_claims_but_never_executes(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    values = _device(context, 1)
    values["armed"]["gpio"]["busy"] = 0
    script = _preflight_script(values) + [
        ("POST", runner._ENDPOINTS["arm"], values["arm"]),
        ("GET", runner._ENDPOINTS["status"], values["armed"]),
        ("GET", runner._ENDPOINTS["status"], values["armed"]),
        ("GET", runner._ENDPOINTS["report"], values["no_report"]),
    ]
    opener = ScriptedOpen(script)
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    result = runner.run_once(
        context, "http://device", 1,
        authorization=runner.required_authorization(context, 1),
        result_file=tmp_path / "result.json", claim_registry=tmp_path / "claims",
        poll_count=1, poll_interval_seconds=0, _urlopen=opener,
        _utcnow=_clock(t0, t0, t0 + timedelta(seconds=1)),
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert [item["path"] for item in opener.requests if item["method"] == "POST"] == [runner._ENDPOINTS["arm"]]


def test_duplicate_claim_and_wrong_authorization_are_zero_network(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    registry = tmp_path / "claims"
    registry.mkdir()
    (_ := registry / f"{context.actions[0]['action_id']}.json").write_text("{}", encoding="utf-8")
    opener = ScriptedOpen([])
    with pytest.raises(runner.SixStatePhysicalError, match="already has"):
        runner.run_once(
            context, "http://device", 1,
            authorization=runner.required_authorization(context, 1), result_file=tmp_path / "x.json",
            claim_registry=registry, _urlopen=opener,
        )
    assert opener.requests == []


def test_host_cooldown_rejects_before_network(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    registry = tmp_path / "claims"
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    first = _run_action(context, tmp_path, 1, t0, registry=registry)
    opener = ScriptedOpen([])
    with pytest.raises(runner.SixStatePhysicalError, match="cooldown"):
        runner.run_once(
            context, "http://device", 2,
            authorization=runner.required_authorization(context, 2),
            result_file=tmp_path / "too-early.json", prior_result_file=first,
            claim_registry=registry, _urlopen=opener,
            _utcnow=lambda: t0 + timedelta(seconds=100),
        )
    assert opener.requests == []
    assert not (registry / f"{context.actions[1]['action_id']}.json").exists()


def test_target_points_are_host_timed_chained_and_bind_true_red_yellow_rows(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    registry = tmp_path / "claims"
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    first = _run_action(context, tmp_path, 1, t0, registry=registry)
    target = _run_action(context, tmp_path, 2, t0 + timedelta(seconds=200), registry=registry, prior_result=first)
    completed = datetime.fromisoformat(json.loads(target.read_text())["completed_at"])
    confirmations = {name: True for name in runner._OBSERVATION_CONFIRMATIONS}
    hold0 = tmp_path / "hold0.json"
    hold5 = tmp_path / "hold5.json"
    hold30 = tmp_path / "hold30.json"
    runner.record_observation_point(
        context, result_file=target, point="hold_0min", temperature_c=37,
        output_file=hold0, prior_point_file=None, confirmations=confirmations,
        claim_registry=registry, _utcnow=lambda: completed + timedelta(seconds=1),
    )
    with pytest.raises(runner.SixStatePhysicalError, match="cannot be captured|requires 5 real"):
        runner.record_observation_point(
            context, result_file=target, point="hold_5min", temperature_c=37,
            output_file=hold5, prior_point_file=hold0, confirmations=confirmations,
            claim_registry=registry, _utcnow=lambda: completed + timedelta(minutes=4),
        )
    assert not hold5.exists()
    runner.record_observation_point(
        context, result_file=target, point="hold_5min", temperature_c=37,
        output_file=hold5, prior_point_file=hold0, confirmations=confirmations,
        claim_registry=registry, _utcnow=lambda: completed + timedelta(minutes=6),
    )
    runner.record_observation_point(
        context, result_file=target, point="hold_30min", temperature_c=37,
        output_file=hold30, prior_point_file=hold5, confirmations=confirmations,
        claim_registry=registry, _utcnow=lambda: completed + timedelta(minutes=31),
    )
    finalized = tmp_path / "target-finalized.json"
    runner.finalize_observation(
        context, result_file=target, point_files=[hold0, hold5, hold30],
        output_file=finalized, reviewer="Ye", claim_registry=registry,
        _utcnow=lambda: completed + timedelta(minutes=32),
    )
    root = json.loads(finalized.read_text())
    rows = [(item["roi_id"], item["initial_code"]) for item in root["observation"]["rois"]]
    assert rows[4:8] == [("RED-CS1", 3), ("RED-CS2", 3), ("YELLOW-CS1", 2), ("YELLOW-CS2", 2)]
    with pytest.raises(runner.SixStatePhysicalError, match="overwrite"):
        runner.record_observation_point(
            context, result_file=target, point="hold_0min", temperature_c=37,
            output_file=hold0, prior_point_file=None, confirmations=confirmations,
            claim_registry=registry, _utcnow=lambda: completed + timedelta(minutes=40),
        )

    # Even a newly self-sealed artifact cannot swap the physical red/yellow rows.
    tampered = json.loads(hold30.read_text())
    tampered["rois"][4], tampered["rois"][6] = tampered["rois"][6], tampered["rois"][4]
    unsigned = copy.deepcopy(tampered)
    unsigned.pop("integrity")
    tampered["integrity"] = {"canonical_sha256": runner.sha256(runner.canonical_json_bytes(unsigned)), "scope": runner.HASH_SCOPE}
    hold30.write_bytes(runner.canonical_json_bytes(tampered) + b"\n")
    with pytest.raises(runner.SixStatePhysicalError, match="ROI"):
        runner._validate_observation_point(
            context, hold30, result_file=target, expected_point="hold_30min", claim_registry=registry
        )


def test_white_requires_real_finalized_target_before_network(tmp_path: Path) -> None:
    context, _manifest, _panel = _release(tmp_path)
    registry = tmp_path / "claims"
    t0 = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    first = _run_action(context, tmp_path, 1, t0, registry=registry)
    target = _run_action(context, tmp_path, 2, t0 + timedelta(seconds=200), registry=registry, prior_result=first)
    opener = ScriptedOpen([])
    with pytest.raises(runner.SixStatePhysicalError, match="finalized target"):
        runner.run_once(
            context, "http://device", 3,
            authorization=runner.required_authorization(context, 3),
            result_file=tmp_path / "white.json", prior_result_file=target,
            claim_registry=registry, _urlopen=opener,
            _utcnow=lambda: t0 + timedelta(hours=1),
        )
    assert opener.requests == []
    assert not (registry / f"{context.actions[2]['action_id']}.json").exists()
    with pytest.raises(runner.SixStatePhysicalError, match="authorization"):
        runner.run_once(
            context, "http://device", 2, authorization="yes", result_file=tmp_path / "y.json",
            claim_registry=registry, _urlopen=opener,
        )
    assert opener.requests == []


def test_cli_has_no_batch_retry_recovery_or_upload_surface() -> None:
    help_text = runner._parser().format_help().lower()
    for command in ("describe", "preflight", "run", "validate", "record-observation", "finalize-observation"):
        assert command in help_text
    for forbidden in ("--retry", "--recover", "--clear-claim", "--upload", "--flash", "--run-all"):
        assert forbidden not in help_text
