from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_partial_hold_matrix as matrix
from tools import mf1750_partial_hold_once as once


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (
    ("accumulate", 0, "ec5_partial_hold_accumulate"),
    ("edges", 1, "ec5_partial_hold_edges"),
    ("cs-split", 2, "ec5_partial_hold_cs_split"),
    ("accumulate-vmirror", 3, "ec5_partial_hold_acc_vmirror"),
    (
        "accumulate-symmetric-v2",
        4,
        "ec5_partial_hold_acc_symmetric_v2",
    ),
    (
        "accumulate-symmetric-y-inclusive",
        5,
        "ec5_partial_hold_acc_symmetric_y_inclusive",
    ),
    (
        "accumulate-symmetric-blue1",
        6,
        "ec5_partial_hold_acc_symmetric_blue1",
    ),
    (
        "accumulate-symmetric-y-inclusive-blue1",
        7,
        "ec5_partial_hold_acc_symmetric_y_inclusive_blue1",
    ),
)


def test_each_variant_is_bound_to_generated_actions_and_binary() -> None:
    report = matrix.build_report()
    for name, index, environment in VARIANTS:
        once.configure_variant(name)
        description = once.describe()
        generated = report["variants"][index]
        firmware = ROOT / ".pio" / "build" / environment / "firmware.bin"
        assert description["variant"] == generated["variant"]
        assert once.runner.CONTRACT_ID == generated["contract_id"]
        assert description["visible_actions"] == 5
        assert description["firmware"]["bound"] is True
        assert description["firmware"]["bytes"] == firmware.stat().st_size
        assert description["firmware"]["sha256"] == hashlib.sha256(
            firmware.read_bytes()
        ).hexdigest()
        for configured, expected in zip(
            once.runner.ACTIONS, generated["actions"], strict=True
        ):
            assert configured["action_id"] == expected["action_id"]
            assert configured["descriptor_id"] == expected["descriptor_id"]
            assert configured["frame_sha256"] == expected["frame"]["sha256"]
            assert configured["cs1_dtm_sha256"] == expected["cs1_dtm"]["sha256"]
            assert configured["cs2_dtm_sha256"] == expected["cs2_dtm"]["sha256"]
            assert configured["transport_code_histogram"] == expected["frame"][
                "histogram"
            ]


def test_runner_declares_fixed_ptlw_and_all_mutating_shortcuts_forbidden() -> None:
    once.configure_variant("accumulate")
    value = once.describe()
    assert value["fixed_transport"] == {
        "spi_hz": 1_000_000,
        "ptlw_command": "0x83",
        "ptlw_payload_bytes": 9,
        "cropped_dtm": True,
        "synchronized_dual_controller_refresh": True,
        "blocking_refresh_first_poll_floor_seconds": 40.0,
    }
    assert all(value["forbidden_operations"].values())
    assert value["startup_refresh"] is False
    assert value["automatic_chaining"] is False
    assert value["automatic_retry"] is False
    assert value["automatic_recovery"] is False
    assert value["firmware_flash_performed_by_runner"] is False
    assert value["live_authorized"] is False


def test_cli_describe_is_offline_and_variant_explicit(capsys) -> None:
    assert once.main(["--variant", "edges", "describe"]) == 0
    output = capsys.readouterr().out
    assert "EDGE_GEOMETRY" in output
    assert "live_authorized" in output


def test_cli_poll_floor_is_inserted_and_short_polls_are_rejected() -> None:
    assert once._apply_blocking_refresh_poll_floor(["describe"]) == ["describe"]
    assert once._apply_blocking_refresh_poll_floor(["run"])[-2:] == [
        "--poll-seconds",
        "40.0",
    ]
    for arguments in (
        ["run", "--poll-seconds", "5"],
        ["run", "--poll-seconds=39.9"],
    ):
        try:
            once._apply_blocking_refresh_poll_floor(arguments)
        except SystemExit as error:
            assert ">= 40" in str(error)
        else:
            raise AssertionError("short blocking-refresh poll was accepted")
