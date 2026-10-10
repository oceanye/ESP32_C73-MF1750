from pathlib import Path
import json
import pytest
from tools.mf1750_lh1_source_white_host_gate import evaluate, write_review

PKG = Path(".test-output/offline/LH1_SOURCE_WHITE_20260912_R1")


def candidate(**changes):
    contract = json.loads((PKG / "contract.json").read_text())
    value = {
        "action_id": contract["action_id"],
        "descriptor_id": contract["descriptor_id"],
        "contract_id": contract["contract_id"],
        "profile_id": "WF23_25",
        "source_state": "FRESH_P2_FACTORY_WHITE",
        "target_state": "LH1_SOURCE",
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "boot_nonce": "abc123",
        "cursor": 2,
        "campaign_complete": True,
    }
    value.update(changes)
    return value


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_exact_source_pass_and_o_excl(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_bytes((PKG / "contract.json").read_bytes())
    terminal = tmp_path / "terminal.json"
    write_json(terminal, candidate())
    result = evaluate(contract, terminal)
    assert result["result"] == "PASS"
    output = tmp_path / "review.json"
    write_review(output, result)
    assert output.exists()
    with pytest.raises(ValueError):
        write_review(output, result)


@pytest.mark.parametrize(
    "change",
    [
        {"source_state": "MIDDLE"},
        {"target_state": "TARGET"},
        {"terminal_state": "FAULT"},
        {"result": False},
        {"cursor": 1},
        {"next_ordinal": 1},
        {
            "action_id": "677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19"
        },
    ],
)
def test_rejects_mismatch(tmp_path, change):
    contract = tmp_path / "contract.json"
    contract.write_bytes((PKG / "contract.json").read_bytes())
    terminal = tmp_path / "terminal.json"
    write_json(terminal, candidate(**change))
    assert evaluate(contract, terminal)["result"] == "FAIL_STOP"
