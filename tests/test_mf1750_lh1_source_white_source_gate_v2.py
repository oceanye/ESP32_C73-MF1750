"""Offline tests for the strict SOURCE1 result gate.

The package and native JSON logs are repository fixtures; no transport is
opened.  Negative candidates are deliberately sealed test records and are
never treated as physical evidence.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import mf1750_lh1_lh4_once as once
from tools import mf1750_lh1_source_white_source_gate_v2 as gate


ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / ".test-output/offline/LH1_SOURCE_WHITE_20260912_R1/contract.json"
SOURCE = ROOT / ".test-output/offline/LH1_LH4_20260912_R1"
NATIVE = ROOT / ".test-output/offline/LH1_LH4_NATIVE_20260912_R1/read_only.log"


def _native_documents() -> list[dict]:
    return [json.loads(line) for line in NATIVE.read_text(encoding="utf-8").splitlines()
            if line.startswith("{")]


def _candidate(tmp_path: Path, **changes: object) -> Path:
    """Write an intentionally incomplete runner envelope for rejection tests."""
    value = {
        "kind": "mf1750-lh1-lh4-source-result-v1",
        "outcome": "complete_pass",
        "ordinal": 1,
        "contract_id": "0" * 64,
        "source_action_id": "0" * 64,
        "driver_calls": 1,
        "visible_refreshes": 1,
        "qualified_count": 0,
        "next_action_authorized": False,
        "stop_and_review_required": True,
        "claim": {},
        "terminal": {},
        "status": {},
        "network": {"get": 0, "post": 0},
    }
    value.update(changes)
    path = tmp_path / "result.json"
    path.write_bytes(once.canonical(once.seal(value)))
    return path


def test_source_context_binds_real_source_build_and_action() -> None:
    successor, ctx = gate.source_context(SUCCESSOR)
    assert successor["source_build"] == ctx["build_binding"]
    assert successor["source_firmware"] == ctx["firmware"]
    assert successor["source_elf"] == ctx["elf"]
    action = ctx["contract"]["actions"][0]
    assert action["ordinal"] == 1 and action["stage"] == "SOURCE"
    assert action["action_id"] == successor["source_action_id"]
    assert action["action_id"] != successor["action_id"]
    assert action["profile_id"] != successor["profile_id"]


def test_real_native_fixture_is_read_only_protocol_input() -> None:
    docs = _native_documents()
    assert len(docs) == 4
    assert {doc["schema_version"] for doc in docs} == {3}
    # Native startup is a four-GET sequence; this test does not call HTTP.
    assert docs[0]["kind"] == "mf1750-lightness-history-v1-version"
    assert docs[2]["kind"] == "mf1750-lightness-history-v1-status"


def test_unsigned_successor_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(SUCCESSOR.read_text(encoding="utf-8"))
    raw.pop("integrity", None)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises((once.RunnerError, gate.SourceGateError)):
        gate.source_context(path)


@pytest.mark.parametrize("change", [
    {"ordinal": 2},
    {"outcome": "failed"},
    {"source_action_id": "foreign"},
    {"network": {"get": 4, "post": 2}},
])
def test_incomplete_or_foreign_runner_envelope_stops(tmp_path: Path, change: dict) -> None:
    result = gate.evaluate(SUCCESSOR, _candidate(tmp_path, **change))
    assert result["result"] == "FAIL_STOP"
    assert result["network_accessed"] is False
    assert result["physical_admission_evaluated"] is False
    assert result["live_ready"] is False


def test_duplicate_json_is_not_accepted(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"kind":"x","kind":"y"}', encoding="utf-8")
    with pytest.raises(once.RunnerError, match="duplicate JSON key"):
        once.parse_json(path.read_bytes())


def test_invented_cursor_without_actual_terminal_graph_stops(tmp_path: Path) -> None:
    terminal = {"cursor": 2, "campaign_complete": False, "terminal_state": "COMPLETE"}
    status = {"cursor": 2, "campaign_complete": False}
    result = gate.evaluate(SUCCESSOR, _candidate(tmp_path, terminal=terminal, status=status))
    assert result["result"] == "FAIL_STOP"
    assert any(result["failures"])


def test_review_write_is_o_exclusive_and_sealed(tmp_path: Path) -> None:
    result = gate.evaluate(SUCCESSOR, _candidate(tmp_path))
    output = tmp_path / "review.json"
    gate.write_review(output, result)
    with pytest.raises((ValueError, once.RunnerError, FileExistsError)):
        gate.write_review(output, result)
    loaded = once.read_record(output)
    assert loaded["kind"] == "mf1750-lh1-source-white-source-gate-v2"


class NativeSourceDouble:
    """Generated-main JSON structure; BUSY samples below are TEST ONLY.

    The native driver stub leaves BUSY stages at the 255 sentinel. Substituting
    synthetic stages exercises host parsing, and proves no electrical fact.
    """
    def __init__(self, ctx: dict, field: dict, busy: int):
        self.ctx, self.field, self.executed = ctx, field, False
        self.initial = dict(zip(('version', 'manifest', 'status', 'report'),
                                map(deepcopy, _native_documents()), strict=True))
        for value in self.initial.values():
            self.bind(value, latched=False)
        self.initial['status']['busy'] = busy
        self.terminal = next(once.parse_json(line.encode()) for line in
            (NATIVE.parent / 'chain.log').read_text(encoding='utf-8').splitlines()
            if line.startswith('{'))
        self.bind(self.terminal, latched=True)
        driver = self.terminal['driver']
        driver.update(spi_hz=1000000, operation_id=1)
        for name in ('pon', 'drf', 'pof'):
            driver['busy_stage_samples'][name].update(
                gate_entry_level=1, pre_command_level=1, wait_entry_level=0,
                wait_exit_level=1, pre_command_idle_ok=True,
                assertion_after_idle=True, pre_command_wait_ms=0,
                wait_ms=100, assertion_latency_ms=1)
        driver['busy_stage_samples']['reset'].update(wait_entry_level=0, wait_exit_level=1)
        driver['busy_stage_samples']['post_psr'].update(pre_command_level=1,
            pre_command_idle_ok=True, wait_exit_level=1)
        driver['safe_finish'] = {'busy_before_pins_low': 1, 'busy_after_pins_low': 1,
            'busy_after_5ms': 1, 'final_gpio': {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}}
        self.terminal.update(job_queued_at_ms=100, job_started_at_ms=101,
                             job_finished_at_ms=401)
        self.status = deepcopy(self.initial['status'])
        self.bind(self.status, latched=True)
        self.status.update(cursor_raw=2, next_ordinal=2, persistent_key_present=True,
            arm_request_count=1, execute_request_count=1, total_driver_call_count=1,
            busy=1, rst=0, cs=0, cs2=0)

    def bind(self, value: dict, *, latched: bool) -> None:
        value.update(self.ctx['identity'])
        for key in ('boot_nonce', 'persisted_campaign_boot_nonce'):
            if key in value:
                value[key] = self.field['boot_nonce']
        value.update(run_id=self.field['run_id'] if latched else '',
                     source_review_sha256=self.field['source_review_sha256'] if latched else '',
                     prior_review_sha256=self.field['source_review_sha256'] if latched else '')

    def __call__(self, method: str, url: str, headers: dict, timeout: int):
        route = url.rsplit('/', 1)[-1]
        if method == 'POST':
            execute = route == 'execute'
            value = {**self.ctx['identity'], **once.expected_action(self.ctx),
                     'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
                     'source_nvs_complete': True, 'accepted': True,
                     'boot_nonce': self.field['boot_nonce'],
                     'review_digests_are_host_assertions_only': True}
            self.bind(value, latched=True)
            if execute:
                self.executed = True
                value.update(job_id=1, execute_consumed=True, phase=2,
                    phase_name='CONSUMED', no_retry=True, no_recovery=True)
            else:
                value.update(armed=True, arm_nonce='fedcba9876543210', phase=1,
                    phase_name='ARMED', not_hardware_authorization=True)
            return 202 if execute else 201, once.canonical(value)
        value = (self.status if route == 'status' else self.terminal) if self.executed else self.initial[route]
        return 200, once.canonical(value)


def _rewrite(path: Path, value: dict) -> None:
    value = {key: item for key, item in value.items() if key != 'integrity'}
    path.write_bytes(once.canonical(once.seal(value)))


@pytest.fixture
def history(tmp_path: Path, monkeypatch):
    """Actual runner generates the envelope/transcript using a fake transport.

    The field fixture intentionally lacks electrical and optical admission.
    Only generation substitutes validate_evidence; the gate must never call it.
    All claims and files remain under pytest's temporary directory.
    """
    ctx = once.validate_package(SOURCE)
    monkeypatch.setattr(once, 'CLAIM_ROOT', tmp_path / 'TEST_ONLY_claims')
    monkeypatch.setattr(once, '_http', lambda *args: pytest.fail('network attempted'))
    monkeypatch.setattr(once.time, 'sleep', lambda *args: None)
    review_path = tmp_path / 'TEST_ONLY_review.json'
    flash_path = tmp_path / 'TEST_ONLY_flash.json'
    for path in (review_path, flash_path):
        _rewrite(path, {'kind': 'TEST_ONLY_NO_PHYSICAL_EVIDENCE',
                        'electrical_state_proven': False, 'external_measurement': False})
    field = {'kind': 'mf1750-lh1-lh4-field-evidence-v1', 'test_fixture_only': True,
             'contract_id': ctx['contract']['contract_id'],
             'recorded_at': datetime.now(timezone.utc).isoformat(),
             'boot_nonce': '0123456789abcdef', 'run_id': 'TEST_ONLY_SOURCE_GATE',
             'base_url': 'http://192.168.1.4',
             'source_review_sha256': once.file_binding(review_path)['sha256'],
             'current_white_review': once.file_binding(review_path),
             'app_flash_record': once.file_binding(flash_path)}
    field_path = tmp_path / 'TEST_ONLY_field.json'
    _rewrite(field_path, field)
    monkeypatch.setattr(once, 'validate_evidence', lambda *args, **kwargs: deepcopy(field))
    once.diagnose(SOURCE, field_path, tmp_path / 'diagnostic', field['base_url'],
                  NativeSourceDouble(ctx, field, 0))
    once.run_source(SOURCE, field_path, tmp_path / 'diagnostic/diagnostic.json',
                    tmp_path / 'run', field['base_url'], transport=NativeSourceDouble(ctx, field, 1))
    monkeypatch.setattr(once, 'validate_evidence', lambda *args, **kwargs:
                        pytest.fail('historical gate attempted physical admission'))
    return SimpleNamespace(candidate=tmp_path / 'run/result.json', ctx=ctx,
                           root=tmp_path, field=field)


def test_actual_runner_envelope_and_native_source_schema_pass(history) -> None:
    review = gate.evaluate(SUCCESSOR, history.candidate)
    assert review['result'] == 'PASS', review['failures']
    checks = review['checks']
    assert checks['source_action_id'] == history.ctx['contract']['actions'][0]['action_id']
    assert checks['source_action_id'] != checks['future_white_action_id']
    assert checks['campaign_complete'] is False and checks['cursor_raw'] == 2
    assert checks['pending_ordinals'] == [2, 3]
    assert checks['network_recorded_by_source_runner'] == {'get': 6, 'post': 2}
    assert review['physical_admission_evaluated'] is False
    assert review['electrical_state_proven'] is False
    assert review['recovery_authorized'] is False


@pytest.mark.parametrize('section,key,value', [
    ('terminal', 'ordinal', 2), ('terminal', 'ordinal', 3),
    ('terminal', 'action_id', 'foreign'), ('terminal', 'profile_id', 'WF23_25'),
    ('terminal', 'terminal_state', 'FAULT'), ('terminal', 'valid', False),
    ('terminal', 'result', False), ('terminal', 'campaign_complete', True),
    ('terminal', 'driver_call_count_for_action', 2),
    ('terminal', 'boot_nonce', 'fedcba9876543210'),
    ('terminal', 'run_id', 'foreign'), ('status', 'cursor_raw', 3),
    ('status', 'campaign_complete', True), ('status', 'busy', 0),
    ('status', 'total_driver_call_count', True),
])
def test_complete_envelope_rejects_wrong_terminal_and_status(history, section, key, value) -> None:
    envelope = once.read_record(history.candidate)
    envelope[section][key] = value
    _rewrite(history.candidate, envelope)
    assert gate.evaluate(SUCCESSOR, history.candidate)['result'] == 'FAIL_STOP'


def test_complete_envelope_rejects_invented_cursor(history) -> None:
    envelope = once.read_record(history.candidate)
    envelope['status']['cursor'] = envelope['status'].pop('cursor_raw')
    _rewrite(history.candidate, envelope)
    assert gate.evaluate(SUCCESSOR, history.candidate)['result'] == 'FAIL_STOP'


@pytest.mark.parametrize('change', ['missing_raw', 'tampered_raw', 'wrong_headers',
                                     'unsigned_meta', 'copied_claim', 'stop'])
def test_complete_envelope_requires_raw_and_permanent_claim(history, change) -> None:
    out = history.candidate.parent
    if change == 'missing_raw':
        (out / '008-get-report.body.bin').unlink()
    elif change == 'tampered_raw':
        (out / '008-get-report.body.bin').write_bytes(b'{}')
    elif change in ('wrong_headers', 'unsigned_meta'):
        path = out / '005-post-arm.json'
        meta = once.read_record(path)
        if change == 'wrong_headers':
            meta['headers']['X-EC5-Ordinal'] = '2'
            _rewrite(path, meta)
        else:
            meta.pop('integrity')
            path.write_bytes(once.canonical(meta))
    elif change == 'copied_claim':
        envelope = once.read_record(history.candidate)
        copied = history.root / 'copied-claim.json'
        copied.write_bytes(once.read_bound(envelope['claim']))
        envelope['claim'] = once.file_binding(copied)
        _rewrite(history.candidate, envelope)
    else:
        _rewrite(out / 'STOP.json', {'test_only': True})
    assert gate.evaluate(SUCCESSOR, history.candidate)['result'] == 'FAIL_STOP'
