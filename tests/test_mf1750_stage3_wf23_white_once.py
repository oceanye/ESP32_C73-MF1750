from __future__ import annotations

from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools import mf1750_stage3_wf23_white_once as subject


def test_describe_is_offline_and_exactly_bound() -> None:
    value = subject.describe()
    assert value["hardware_action_id"] == subject.ACTION_ID
    assert value["firmware_binary_sha256"] == subject.FIRMWARE_BIN_SHA256
    assert value["logic_analyser_required"] is False
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0


def test_only_recovery_binding_is_replaced() -> None:
    base = physical.load_release(subject.BASE_RELEASE)
    context = subject.load_context()
    assert context.action(1) == base.action(1)
    assert context.binding(1) == base.binding(1)
    assert context.action(2)["hardware_action_id"] == subject.ACTION_ID
    assert context.binding(2)["nvs_namespace"] == subject.NVS_NAMESPACE


def test_descriptor_marker_override_is_part_of_expected_identity() -> None:
    context = subject.load_context()
    with subject._descriptor_marker_override():  # noqa: SLF001
        expected = physical._identity_expected(context, 2)  # noqa: SLF001
    assert expected["transaction_descriptor_marker"] == subject.DESCRIPTOR_MARKER
    assert expected["contract_id"] == subject.CONTRACT_ID
