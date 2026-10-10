from copy import deepcopy
import pytest
from tools import mf1750_lh1_middle_fault_source_gate_v1 as gate


@pytest.fixture
def actual():
    ctx = gate.base.validate_package(gate.PACKAGE)
    field = gate.record(gate.SOURCE / 'field-on.json')
    status = gate.base.parse_json((gate.MIDDLE / 'post-fault-readonly/001-get-status.body.bin').read_bytes())
    report = gate.base.parse_json((gate.MIDDLE / 'post-fault-readonly/002-get-report.body.bin').read_bytes())
    return ctx, field, status, report


def test_actual_rejected_arm_not_a_driver_failure(actual):
    gate.check_fault(*actual, relay_off=True)


@pytest.mark.parametrize('key,value', [
    ('driver_called', True), ('driver_call_count_for_action', 1),
    ('total_driver_call_count', 2), ('error', 'timeout'),
    ('terminal_state', 'COMPLETE'), ('boot_nonce', '1111111111111111'),
])
def test_other_faults_cannot_use_pre_dispatch_recovery(actual, key, value):
    ctx, field, status, report = actual
    report = deepcopy(report)
    report[key] = value
    with pytest.raises(gate.base.RunnerError):
        gate.check_fault(ctx, field, status, report, relay_off=True)


@pytest.mark.parametrize('key,value', [
    ('cursor_raw', 2), ('execute_request_count', 2),
    ('execute_pending', True), ('total_driver_call_count', 2),
    ('persisted_campaign_boot_nonce', '1111111111111111'),
])
def test_ready_or_dispatched_or_rebooted_source_rejected(actual, key, value):
    ctx, field, status, report = actual
    status = deepcopy(status)
    status[key] = value
    with pytest.raises(gate.base.RunnerError):
        gate.check_fault(ctx, field, status, report, relay_off=True)
