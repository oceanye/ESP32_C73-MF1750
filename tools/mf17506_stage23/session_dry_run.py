"""Replay the six-action blue-history session with fake relay/MCU only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from host.static_photo.common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_json_bytes,
    file_sha256,
    prepare_empty_output_dir,
    verify_integrity,
)

from .relay_contract import PowerStateMachine, RelayCommandedState, RelayContractError
from .relay_fake import FakeRelay


class SessionDryRunError(RuntimeError):
    """Raised when the fake-only dry run cannot close safely."""


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        raw = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise SessionDryRunError(f"cannot load plan manifest: {error}") from error
    if not isinstance(raw, Mapping):
        raise SessionDryRunError("plan manifest must be an object")
    try:
        verify_integrity(raw, "blue history manifest")
    except StaticPhotoContractError as error:
        raise SessionDryRunError(str(error)) from error
    manifest = dict(raw)
    if (
        manifest.get("kind") != "MF17506_BLUE_HISTORY_16_RECIPE_OFFLINE_BUNDLE"
        or manifest.get("visible_action_count") != 6
        or manifest.get("live_authorized") is not False
    ):
        raise SessionDryRunError("plan manifest boundary differs")
    return manifest, payload


def run_dry_session(
    plan_manifest: str | Path,
    *,
    output_dir: str | Path,
    fail_operation: str | None = None,
) -> dict[str, Any]:
    manifest, manifest_payload = _load_manifest(Path(plan_manifest))
    output = prepare_empty_output_dir(output_dir)
    relay = FakeRelay(fail_operation=fail_operation)
    machine = PowerStateMachine()
    actions: list[dict[str, Any]] = []
    terminal = "UNKNOWN"
    error_text: str | None = None
    try:
        identity = relay.discover()
        relay.connect(identity)
        relay.command_off()
        if relay.read_commanded_state() is not RelayCommandedState.OFF:
            raise SessionDryRunError("fake relay did not start OFF")
        machine.begin_power_on()
        relay.command_on()
        machine.relay_on_acknowledged()
        if relay.read_commanded_state() is not RelayCommandedState.ON:
            raise SessionDryRunError("fake relay did not acknowledge ON")
        machine.verify_on()
        ordinal = 0
        for batch in manifest["batches"]:
            for role in batch["visible_action_order"]:
                ordinal += 1
                action_id = f"{batch['batch_id']}:{role}"
                machine.start_action(action_id)
                frame = batch["frames"][role]["identity"]
                actions.append(
                    {
                        "ordinal": ordinal,
                        "action_id": action_id,
                        "frame_sha256": frame["sha256"],
                        "simulated_mcu_calls": 1,
                        "real_mcu_calls": 0,
                        "result": "FAKE_SUCCESS",
                    }
                )
                machine.finish_action(action_id)
        machine.begin_power_off()
        relay.command_off()
        machine.relay_off_acknowledged()
        if relay.read_commanded_state() is not RelayCommandedState.OFF:
            raise SessionDryRunError("fake relay did not acknowledge OFF")
        machine.verify_off()
        terminal = "DRY_RUN_SUCCESS_SAFE_OFF"
    except (RelayContractError, SessionDryRunError, KeyError, TypeError) as error:
        error_text = str(error)
        machine.latch_fault(error_text)
        terminal = "DRY_RUN_FAULT_LATCHED"
        try:
            relay.command_off()
        except RelayContractError:
            pass
    finally:
        relay.close()
    report_unsigned = {
        "schema_version": 1,
        "kind": "MF17506_BLUE_HISTORY_FAKE_SESSION_DRY_RUN",
        "terminal": terminal,
        "error": error_text,
        "plan_manifest": {
            "file": str(Path(plan_manifest).resolve()),
            "file_sha256": file_sha256(manifest_payload),
            "canonical_sha256": manifest["integrity"]["canonical_sha256"],
        },
        "relay_identity": relay.identity.mapping(),
        "relay_fake_calls": relay.calls,
        "state_machine_events": machine.events,
        "final_state": machine.state.value,
        "actions": actions,
        "expected_action_count": 6,
        "completed_action_count": len(actions),
        "automatic_retry_performed": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "serial_io_performed": False,
        "relay_hardware_io_performed": False,
        "visible_refreshes_performed": 0,
        "live_authorized": False,
    }
    report = attach_integrity(report_unsigned)
    payload = canonical_json_bytes(report) + b"\n"
    report_file = output / "DRY-RUN-REPORT.json"
    report_file.write_bytes(payload)
    return {
        "report_file": str(report_file.resolve()),
        "terminal": terminal,
        "final_state": machine.state.value,
        "completed_action_count": len(actions),
        "visible_refreshes_performed": 0,
        "device_io_performed": False,
        "canonical_sha256": report["integrity"]["canonical_sha256"],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fail-operation")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_dry_session(
            args.plan_manifest,
            output_dir=args.output_dir,
            fail_operation=args.fail_operation,
        )
    except SessionDryRunError as error:
        print(f"session dry-run error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["terminal"] == "DRY_RUN_SUCCESS_SAFE_OFF" else 3


if __name__ == "__main__":
    raise SystemExit(main())
