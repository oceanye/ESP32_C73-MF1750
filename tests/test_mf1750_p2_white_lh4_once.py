from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_p2_white_lh4_once as once
from tools import mf1750_p2_white_lh4_pack as pack


def test_lh4_dry_validate_and_original_consumption_identity() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True and value["network_requests"] == 0
    assert (
        pack.ENVIRONMENT == "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1"
    )
    assert pack.BUILD_ENVIRONMENT == "lhr4"
    assert (
        once.DEFAULT_CLAIMS.name
        == ".mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_claims"
    )
    assert (pack.NVS_NAMESPACE, pack.NVS_KEY) == ("p2catwsv1", "used_p2cw1")
    assert (
        value["action_id"]
        == "677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19"
    )


@pytest.mark.parametrize(
    "field,old_hash",
    [
        (
            "FIRMWARE_ELF_SHA256",
            "2b41cb8413d24b5f6c36083d5381d7d21fdd64679dd9d45dab68a1492c059ed3",
        ),
        (
            "FIRMWARE_BIN_SHA256",
            "acf27e1358f869b4f5663e8a84ad4f38ab047557c90a9d64c4fa44c66c079277",
        ),
    ],
)
def test_old_artifact_refused(
    monkeypatch: pytest.MonkeyPatch, field: str, old_hash: str
) -> None:
    monkeypatch.setattr(pack, field, old_hash)
    with pytest.raises(RuntimeError, match="differs"):
        pack.build_report(verify_artifacts=True)


def test_compile_input_change_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = deepcopy(pack.LH4_SOURCE_SHA256)
    bound["src/epd_driver.cpp"] = "0" * 64
    monkeypatch.setattr(pack, "LH4_SOURCE_SHA256", bound)
    with pytest.raises(RuntimeError, match="LH4 source or report differs"):
        pack.build_report(verify_artifacts=True)


def test_missing_diagnostic_before_delegate_or_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}")
    binding = tmp_path / "binding.json"
    binding.write_text("{}")
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", tmp_path / "missing.json")
    monkeypatch.setattr(
        once,
        "_load_delegate",
        lambda: pytest.fail("delegate accessed before prerequisite"),
    )
    with pytest.raises(RuntimeError, match="diagnostic.*missing"):
        once.run_once(
            "http://192.168.1.4",
            source_terminal_evidence=source,
            exact_ipv4_mac_binding=binding,
            confirm_j2_on=True,
            confirm_gnd_normal=True,
        )


def test_alternate_claims_refused_before_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        once,
        "_load_delegate",
        lambda: pytest.fail("delegate accessed before claims guard"),
    )
    with pytest.raises(RuntimeError, match="alternate claims"):
        once.run_once(
            "http://192.168.1.4",
            source_terminal_evidence=tmp_path / "none",
            exact_ipv4_mac_binding=tmp_path / "none",
            confirm_j2_on=True,
            confirm_gnd_normal=True,
            claims=tmp_path / "newclaims",
        )


def test_cli_missing_source_zero_request(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.mf1750_p2_white_lh4_once",
            "diagnose-j2-off",
            "--base-url",
            "http://192.168.1.4",
            "--source-terminal-evidence",
            str(tmp_path / "missing-source"),
            "--exact-ipv4-mac-binding",
            str(tmp_path / "missing-binding"),
            "--confirm-j2-off",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2 and "missing" in result.stderr


def test_actual_native_json_against_complete_delegate_in_isolated_process() -> None:
    # Slow legacy imports remain isolated from original host tests. No network is allowed.
    script = r"""
import json, socket
from copy import deepcopy
from pathlib import Path
from tools import mf1750_p2_white_lh4_once as once

def deny(*a, **kw):
    raise AssertionError("unexpected network request")
socket.create_connection = deny
socket.socket.connect = deny
socket.socket.connect_ex = deny
d = once._load_delegate()
p = Path('.test-output/offline/MF1750_WHITE_LH4_ROOT_REVIEW_20260912_V1/LH4-identity.raw.json')
v = json.loads(p.read_text(encoding='utf8'))
d.host._identity(v, running_sha=once.pack.FIRMWARE_ELF_SHA256)
rejected=[]
for field in ('environment','source_main_offline_build_file_sha256','source_main_contract_id','running_app_elf_sha256'):
    bad=deepcopy(v);bad[field]='wrong'
    try:
        d.host._identity(bad, running_sha=once.pack.FIRMWARE_ELF_SHA256)
    except (RuntimeError, ValueError):
        rejected.append(field)
    else:
        raise AssertionError(field+' incorrectly accepted')
print(json.dumps({'passed':True,'rejected':rejected,'network_requests':0}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["passed"] and len(value["rejected"]) == 4
