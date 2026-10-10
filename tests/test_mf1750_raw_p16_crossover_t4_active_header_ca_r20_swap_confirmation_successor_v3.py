from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as v2,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]


def test_v1_v2_diagnostics_are_exact_read_only_failure_authorities() -> None:
    authorities = pack.validate_authorities()
    v2_failure = authorities["failed_v2_j2_off_diagnostic"]
    replay = v2_failure["full_transcript_replay"]

    assert v2_failure["validated"] is True
    assert v2_failure["binding"]["get"] == 4
    assert v2_failure["binding"]["post"] == 0
    assert v2_failure["binding"]["permanent_claims_created"] == 0
    assert v2_failure["binding"]["visible_refreshes"] == 0
    assert v2_failure["binding"]["driver_calls"] == 0
    assert v2_failure["binding"]["terminal_state"] == "NOT_EXECUTED"
    assert replay["result"] == "PASS"
    assert replay["normalized_field"] == "non_reusable_action_ids"
    assert replay["validators"] == ["version", "manifest", "status", "report"]
    assert replay["device_registry_count"] == 13
    assert replay["v2_host_registry_count"] == 14
    assert replay["network_requests"] == 0


def test_v3_registry_is_15_and_tombstones_v1_then_v2() -> None:
    registry = pack.non_reusable_action_ids()
    v1_action = v2.v1.build_report()["actions"][0]["action_id"]
    v2_action = v2.build_report()["actions"][0]["action_id"]
    report = pack.build_report()

    assert len(registry) == 15
    assert len(set(registry)) == 15
    assert registry[-2:] == (v1_action, v2_action)
    assert report["contract"]["non_reusable_action_ids"] == list(registry)
    assert report["actions"][0]["action_id"] not in registry


def test_version_and_manifest_share_the_exact_v3_15_entry_registry() -> None:
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    main = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main.cpp"
    ).read_text(encoding="utf-8")
    v3_branch = main_config.split(
        "#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_BUILD)",
        1,
    )[1].split("#else", 1)[0]

    assert list(pack.non_reusable_action_ids()) == (
        pack.build_report()["contract"]["non_reusable_action_ids"]
    )
    assert pack.non_reusable_action_ids()[-2] in v3_branch
    assert pack.non_reusable_action_ids()[-1] in v3_branch
    # Both endpoint builders append the same immutable registry-bearing JSON.
    assert main.count("kExternalWhiteAnchorJson") == 2
    assert "versionJson" in main and "manifestJson" in main


def test_v3_is_fresh_and_payload_semantics_equal_v1_v2() -> None:
    result = pack.dry_validate()
    report = pack.build_report()
    action = report["actions"][0]
    old = v2.build_report()["actions"][0]

    assert result["result"] == "PASS"
    assert result["v2_full_four_get_transcript_replayed"] is True
    assert result["device_and_host_registry_count"] == 15
    assert action["supersedes_failed_unmutated_v2_action_id"] == old["action_id"]
    assert action["v1_diagnostic_failure_authority"] == (
        pack.v1_diagnostic_failure_binding()
    )
    assert action["v2_diagnostic_failure_authority"] == (
        pack.v2_diagnostic_failure_binding()
    )
    for key in (
        "frame",
        "cs1_dtm",
        "cs2_dtm",
        "waveform_binding",
        "profile_id",
        "global_header",
        "global_tuple_id",
        "round",
    ):
        assert action[key] == old[key]


def test_fresh_process_direct_configure_survives_transcript_replay() -> None:
    action_id = pack.build_report()["actions"][0]["action_id"]
    code = (
        "from tools import "
        "mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_"
        "successor_v3_once as once; "
        "host=once.configure(); "
        f"assert host.base.runner.ACTIONS[0]['action_id']=='{action_id}'; "
        "print('PASS')"
    )
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "PASS"


def test_identity_config_routes_nvs_outputs_and_claims_are_fresh() -> None:
    report = pack.build_report()
    action = report["actions"][0]
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_identity.inc"
    ).read_text(encoding="utf-8")
    selector = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    ini = (ROOT / builder.CONFIG).read_text(encoding="utf-8")
    host = once.configure()
    identity_literals_joined = re.sub(r'"\s*"', "", identity)

    for value in (
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        v2.v1.build_report()["actions"][0]["action_id"],
        v2.build_report()["actions"][0]["action_id"],
        pack.V2_DIAGNOSTIC_FILE_SHA256,
        pack.V2_DIAGNOSTIC_CANONICAL_SHA256,
        pack.CONFIG.campaign_id,
        pack.CONFIG.nvs_namespace,
    ):
        assert value in identity_literals_joined
    assert pack.CONFIG.base_route in main_config
    assert "successor_v3_identity.inc" in selector
    assert (
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
        "SUCCESSOR_V3_BUILD=1"
    ) in ini
    assert "build_dir = .pio/b-t4ca3" in ini
    assert "[env:ec5_p16_t4ca3]" in ini
    assert "upload" not in ini.lower()
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V3"
    )
    assert str(host.DEFAULT_CLAIMS).endswith(
        ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_claims"
    )
    assert host.base.runner.ENDPOINTS == {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }


def test_cold_configure_restores_shared_mechanics_after_v2_replay() -> None:
    # A cached replay can hide cross-version global contamination.  Force the
    # sealed V2 transcript through the validators during this V3 configure.
    pack.replay_v2_transcript_after_known_registry_normalization.cache_clear()
    host = once.configure()

    assert once.mechanics.pack is pack
    assert host.base.runner.CAMPAIGN_ID == pack.CONFIG.campaign_id
    assert host.base.runner.ACTION_IDS == (
        pack.build_report()["actions"][0]["action_id"],
    )
    assert str(host.DEFAULT_OUTPUT).endswith("SUCCESSOR_20260831_V3")


def test_sealed_artifacts_and_compile_only_build_wrapper() -> None:
    value = once.dry_validate()
    source = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_build.py"
    ).read_text(encoding="utf-8")

    assert value["artifacts_verified"] is True
    for name, expected in pack.ARTIFACTS[pack.STAGE].items():
        assert expected != 0 and expected != "0" * 64, name
    for path, kind in zip(pack.artifact_paths(), ("bin", "elf"), strict=True):
        payload = path.read_bytes()
        assert len(payload) == pack.ARTIFACTS[pack.STAGE][f"{kind}_bytes"]
        assert hashlib.sha256(payload).hexdigest() == (
            pack.ARTIFACTS[pack.STAGE][f"{kind}_sha256"]
        )
    firmware = pack.artifact_paths()[0].read_bytes()
    registry_tail = (
        f'"{pack.non_reusable_action_ids()[-2]}",'
        f'"{pack.non_reusable_action_ids()[-1]}"'
    ).encode("ascii")
    assert firmware.count(registry_tail) == 1
    assert firmware.count(pack.CONFIG.base_route.encode("ascii")) == 6
    assert '"run", "-c", CONFIG' in source
    assert "upload" not in source.lower()
