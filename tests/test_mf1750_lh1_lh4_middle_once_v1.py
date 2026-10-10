"""Offline synthetic transport tests for the ordinal-2 MIDDLE runner."""
from __future__ import annotations

from pathlib import Path
import pytest

from tools import mf1750_lh1_lh4_middle_once_v1 as middle


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".test-output/offline/LH1_LH4_20260912_R1"


def _source(path: Path, ctx: dict, **changes: object) -> Path:
    value = {
        "kind": "mf1750-lh1-lh4-source-terminal-reconciliation-v1",
        "contract_id": ctx["contract_id"],
        "boot_nonce": "0123456789abcdef",
        "terminal_report": {"terminal_state": "COMPLETE", "result": True,
                             "next_ordinal": 2,
                             "boot_nonce": "0123456789abcdef"},
        "terminal_status": {"cursor_raw": 2, "next_ordinal": 2,
                             "boot_nonce": "0123456789abcdef"},
        "source_replayed": False,
        "claim_created": False,
    }
    value.update(changes)
    path.write_bytes(middle.canonical(middle.seal(value)))
    return path


def _rewrite(path: Path, value: dict) -> None:
    value = {k: v for k, v in value.items() if k != "integrity"}
    path.write_bytes(middle.canonical(middle.seal(value)))


class Transport:
    def __init__(self, ctx: dict, boot: str = "0123456789abcdef"):
        self.ctx, self.boot, self.calls = ctx, boot, []
        self.polls = 0

    def __call__(self, method: str, url: str, headers: dict, timeout: int):
        route = url.rsplit("/", 1)[-1]
        self.calls.append((method, route, headers))
        action = self.ctx["middle"]
        if route == "arm":
            return 201, middle.canonical({"accepted": True, "armed": True,
                "phase": 1, "boot_nonce": self.boot, "ordinal": 2,
                "arm_nonce": "fedcba9876543210"})
        if route == "execute":
            return 202, middle.canonical({"accepted": True, "execute_consumed": True,
                "phase": 2, "job_id": 2, "boot_nonce": self.boot, "ordinal": 2})
        if route == "status":
            self.polls += 1
            cursor = 2 if self.polls == 1 else 3
            nxt = 2 if self.polls == 1 else 3
            return 200, middle.canonical({"cursor_raw": cursor, "next_ordinal": nxt,
                "phase": 0 if self.polls > 1 else 2,
                "arm_request_count": 1, "execute_request_count": 1,
                "total_driver_call_count": 2, "boot_nonce": self.boot})
        if route == "report":
            return 200, middle.canonical({"ordinal": 2, "action_id": action["action_id"],
                "terminal_state": "COMPLETE", "result": True,
                "driver_call_count_for_action": 1, "total_driver_call_count": 2,
                "no_retry": True, "boot_nonce": self.boot})
        return 200, middle.canonical({"boot_nonce": self.boot, "kind": route})


class FailingTransport(Transport):
    def __call__(self, method: str, url: str, headers: dict, timeout: int):
        if url.endswith("/status"):
            self.calls.append((method, "status", headers))
            raise OSError("synthetic GET failure")
        return super().__call__(method, url, headers, timeout)


def test_validate_package_binds_commented_middle_action() -> None:
    ctx = middle.validate_package(PACKAGE)
    assert ctx["middle"]["ordinal"] == 2
    assert ctx["middle"]["global_header"] == "commented"
    assert ctx["middle"]["driver_role"] == "Mid"


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(middle.MiddleRunnerError, match="duplicate JSON key"):
        middle.parse_json(b'{"state":1,"state":2}')


def test_source_reconciliation_requires_complete_cursor_two(tmp_path: Path) -> None:
    ctx = middle.validate_package(PACKAGE)
    path = _source(tmp_path / "source.json", ctx)
    assert middle.validate_source_reconciliation(path, ctx)["boot_nonce"] == "0123456789abcdef"
    bad = middle.read_record(path)
    bad["terminal_status"]["next_ordinal"] = 1
    _rewrite(path, bad)
    with pytest.raises(middle.MiddleRunnerError, match="cursor must be 2"):
        middle.validate_source_reconciliation(path, ctx)


def test_run_middle_synthetic_transport_is_single_action_and_sealed(tmp_path: Path) -> None:
    ctx = middle.validate_package(PACKAGE)
    source = _source(tmp_path / "source.json", ctx)
    transport = Transport(ctx)
    result = middle.run_middle(PACKAGE, source, tmp_path / "run", transport=transport,
                               sleeper=lambda _: None, initial_wait=60)
    assert result["outcome"] == "complete_pass"
    assert result["ordinal"] == 2 and result["middle_driver_calls"] == 1
    assert result["source_replayed"] is False and result["claim_created"] is False
    assert result["network"] == {"GET": 6, "POST": 2}
    assert [call[0:2] for call in transport.calls] == [
        ("GET", "version"), ("GET", "manifest"), ("GET", "status"),
        ("GET", "report"), ("POST", "arm"), ("POST", "execute"),
        ("GET", "status"), ("GET", "report")]
    with pytest.raises((FileExistsError, middle.MiddleRunnerError)):
        middle.write_new(tmp_path / "run" / "result.json", result)


@pytest.mark.parametrize("change", [
    {"source_replayed": True}, {"claim_created": True},
    {"boot_nonce": "fedcba9876543210"},
    {"terminal_report": {"terminal_state": "FAULT", "result": False}},
])
def test_source_reconciliation_rejects_replay_or_foreign_terminal(tmp_path: Path, change: dict) -> None:
    ctx = middle.validate_package(PACKAGE)
    with pytest.raises(middle.MiddleRunnerError):
        middle.validate_source_reconciliation(_source(tmp_path / "source.json", ctx, **change), ctx)


def test_run_middle_rejects_same_boot_mismatch_before_arm(tmp_path: Path) -> None:
    ctx = middle.validate_package(PACKAGE)
    source = _source(tmp_path / "source.json", ctx)
    transport = Transport(ctx, boot="fedcba9876543210")
    with pytest.raises(middle.MiddleRunnerError, match="same-boot"):
        middle.run_middle(PACKAGE, source, tmp_path / "run", transport=transport,
                          sleeper=lambda _: None, initial_wait=60)
    assert [method for method, _, _ in transport.calls] == ["GET"] * 4


def test_initial_wait_cannot_be_shortened(tmp_path: Path) -> None:
    ctx = middle.validate_package(PACKAGE)
    source = _source(tmp_path / "source.json", ctx)
    with pytest.raises(middle.MiddleRunnerError, match="at least 60"):
        middle.run_middle(PACKAGE, source, tmp_path / "run", transport=Transport(ctx),
                          sleeper=lambda _: None, initial_wait=59)


def test_get_failure_writes_exclusive_error_and_never_posts(tmp_path: Path) -> None:
    ctx = middle.validate_package(PACKAGE)
    source = _source(tmp_path / "source.json", ctx)
    transport = FailingTransport(ctx)
    with pytest.raises(middle.MiddleRunnerError, match="GET status failed"):
        middle.run_middle(PACKAGE, source, tmp_path / "run", transport=transport,
                          sleeper=lambda _: None, initial_wait=60)
    assert not any(method == "POST" for method, _, _ in transport.calls)
    assert (tmp_path / "run" / "003-get-status.error.json").exists()
    with pytest.raises((FileExistsError, middle.MiddleRunnerError)):
        middle.write_new(tmp_path / "run" / "003-get-status.error.json", b"overwrite")
