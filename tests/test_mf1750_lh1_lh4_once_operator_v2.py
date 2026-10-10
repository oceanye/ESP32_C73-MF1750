"""Focused offline policy tests; no synthetic record is used for live admission."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from tools import mf1750_lh1_lh4_once as original
from tools import mf1750_lh1_lh4_once_operator_v2 as runner


NOW = datetime.now(timezone.utc)
SESSION = {'boot_nonce': '0123456789abcdef', 'run_id': 'TEST_ONLY',
           'app_flash_record': {'path': 'TEST_ONLY', 'bytes': 0, 'sha256': '0' * 64}}


def record_only() -> dict:
    return {**deepcopy(SESSION), 'phase': 'on', 'operator': 'TEST_ONLY',
            'mode': runner.ELECTRICAL_RECORD_ONLY_MODE,
            'actual_user_instruction': runner.ELECTRICAL_RECORD_ONLY_INSTRUCTION,
            'verdict': 'RECORD_ONLY', 'electrical_state_proven': False,
            'external_measurement': False, 'readings': [], 'instrument': None,
            'ground_reference': None}



def test_record_only_exact_instruction_keeps_physical_unknown() -> None:
    value = record_only()
    before = deepcopy(value)
    runner.validate_electrical_policy(value, SESSION, 'on', NOW)
    assert value == before
    assert value['readings'] == [] and value['external_measurement'] is False
    assert value['electrical_state_proven'] is False


@pytest.mark.parametrize('key,value', [
    ('actual_user_instruction', ''),
    ('actual_user_instruction', '电气信息正常'),
    ('actual_user_instruction', None),
    ('mode', None),
    ('mode', 'record_only'),
    ('verdict', 'PASS'),
    ('electrical_state_proven', True),
    ('external_measurement', True),
    ('readings', [{'value': 0}]),
    ('instrument', 'invented'),
    ('ground_reference', 'invented'),
    ('operator', ''),
    ('phase', 'off'),
    ('run_id', 'foreign'),
    ('boot_nonce', 'fedcba9876543210'),
    ('app_flash_record', {}),
])
def test_record_only_cannot_override_other_session_or_fabricate_readings(key, value) -> None:
    record = record_only()
    record[key] = value
    with pytest.raises(runner.RunnerError):
        runner.validate_electrical_policy(record, SESSION, 'on', NOW)


def test_measured_default_is_unchanged_and_requires_numbers() -> None:
    value = {**deepcopy(SESSION), 'phase': 'on', 'operator': 'TEST_ONLY',
             'instrument': 'TEST_ONLY', 'ground_reference': 'TEST_ONLY',
             'acceptance_basis': 'TEST_ONLY', 'verdict': 'PASS',
             'external_measurement': True, 'readings': [
                 {'point': 'TEST_ONLY', 'unit': 'V', 'value': 0,
                  'recorded_at': NOW.isoformat()}]}
    runner.validate_electrical_policy(value, SESSION, 'on', NOW)
    value['readings'] = []
    with pytest.raises(runner.RunnerError, match='actual external'):
        runner.validate_electrical_policy(value, SESSION, 'on', NOW)



@pytest.mark.parametrize('name', [
    'claim_path', 'run_source', 'diagnose', '_diagnostic', 'validate_terminal',
    'mutation_headers', 'validate_four_get', 'validate_package', '_identity',
    'validate_ipv4_mac_raw', '_source_evidence', 'read_bound', 'verify_integrity',
])
def test_identity_protocol_claim_and_raw_gates_are_exactly_preserved(name: str) -> None:
    assert inspect.getsource(getattr(runner, name)) == inspect.getsource(getattr(original, name))
    assert runner.CLAIM_ROOT == original.CLAIM_ROOT


@pytest.mark.parametrize('ordinal', [0, 2, 3, True, '1'])
def test_disallowed_ordinal_remains_zero_io(ordinal, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, 'validate_package', lambda *args: pytest.fail('package read'))
    with pytest.raises(runner.RunnerError, match='only SOURCE ordinal 1'):
        runner.run_source(tmp_path, tmp_path / 'field', tmp_path / 'diag',
                          tmp_path / 'out', 'http://192.168.1.4', ordinal,
                          lambda *args: pytest.fail('network'))


def test_invalid_phase_and_unsigned_evidence_still_reject(tmp_path: Path) -> None:
    with pytest.raises(runner.RunnerError, match='off/on'):
        runner.validate_evidence({}, tmp_path / 'missing', 'http://192.168.1.4', phase='unknown')
    path = tmp_path / 'unsigned.json'
    path.write_bytes(runner.canonical(record_only()))
    with pytest.raises(runner.RunnerError):
        runner.read_record(path)


def test_existing_permanent_claim_blocks_before_field_read(tmp_path: Path, monkeypatch) -> None:
    ctx = {'source': {'campaign_id': 'TEST_ONLY', 'action_id': 'TEST_ONLY'}}
    monkeypatch.setattr(runner, 'CLAIM_ROOT', tmp_path / 'claims')
    monkeypatch.setattr(runner, '_source_evidence', lambda context: None)
    claim = runner.claim_path(ctx)
    claim.parent.mkdir()
    claim.write_bytes(b'TEST_ONLY')
    with pytest.raises(runner.RunnerError, match='already permanently claimed'):
        runner.validate_evidence(ctx, tmp_path / 'missing', 'http://192.168.1.4')

