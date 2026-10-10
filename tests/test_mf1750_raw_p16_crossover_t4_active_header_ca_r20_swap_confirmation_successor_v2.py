from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as pack,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_pack as v1,
)


ROOT = Path(__file__).resolve().parents[1]


def test_v1_diagnostic_is_exact_no_mutation_authority() -> None:
    value = pack.validate_v1_diagnostic_failure()
    binding = value["binding"]

    assert value["validated"] is True
    assert binding["get"] == 4
    assert binding["post"] == 0
    assert binding["permanent_claims_created"] == 0
    assert binding["visible_refreshes"] == 0
    assert binding["driver_calls"] == 0
    assert binding["terminal_state"] == "NOT_EXECUTED"
    assert binding["safe_to_supersede_without_containment"] is True


def test_v2_is_fresh_and_payload_semantics_equal_v1() -> None:
    result = pack.dry_validate()
    report = pack.build_report()
    action = report["actions"][0]
    old = v1.build_report()["actions"][0]

    assert result["result"] == "PASS"
    assert result["explicit_null_prior_fields_aligned"] is True
    assert result["experimental_payload_byte_identical_to_v1"] is True
    assert action["action_id"] not in pack.non_reusable_action_ids()
    assert old["action_id"] in pack.non_reusable_action_ids()
    assert action["supersedes_failed_unmutated_v1_action_id"] == old["action_id"]
    assert action["v1_diagnostic_failure_authority"] == (
        pack.v1_diagnostic_failure_binding()
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


def test_wire_boot_admission_matches_firmware_explicit_null_shape() -> None:
    host = once.configure()
    expected = pack.build_report()["actions"][0]["boot_admission"]
    observed = list(host.base.runner.ACTIONS)[0]["boot_admission"]

    assert observed == expected
    assert observed["required_prior_ordinal"] is None
    assert observed["required_prior_terminal_state"] is None
    assert set(observed) == {
        "campaign_boot_binding_key",
        "admission",
        "required_prior_terminal_state",
        "required_prior_ordinal",
        "firmware_arm_gate",
        "firmware_execute_gate",
        "firmware_dispatch_gate",
        "reboot_resume_allowed",
        "post_containment_resume_allowed",
    }


def test_identity_config_routes_nvs_outputs_and_claims_are_fresh() -> None:
    report = pack.build_report()
    action = report["actions"][0]
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_identity.inc"
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
        v1.build_report()["actions"][0]["action_id"],
        pack.V1_DIAGNOSTIC_FILE_SHA256,
        pack.V1_DIAGNOSTIC_CANONICAL_SHA256,
        pack.CONFIG.campaign_id,
        pack.CONFIG.nvs_namespace,
    ):
        assert value in identity_literals_joined
    assert pack.CONFIG.base_route in main_config
    assert "successor_v2_identity.inc" in selector
    assert (
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
        "SUCCESSOR_V2_BUILD=1"
    ) in ini
    assert "build_dir = .pio/b-t4ca2" in ini
    assert "[env:ec5_p16_t4ca2]" in ini
    assert "upload" not in ini.lower()
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V2"
    )
    assert str(host.DEFAULT_CLAIMS).endswith(
        ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_claims"
    )
    assert host.base.runner.ENDPOINTS == {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }


def test_sealed_artifacts_and_compile_only_build_wrapper() -> None:
    value = once.dry_validate()
    source = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_build.py"
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
    assert '"run", "-c", CONFIG' in source
    assert "upload" not in source.lower()


def test_sealed_v1_diagnostic_manifest_has_only_the_two_known_extra_fields() -> None:
    value = json.loads(pack.V1_DIAGNOSTIC_PATH.read_text(encoding="utf-8"))
    actual = next(
        item["response"]["actions"][0]
        for item in value["transcript"]
        if item["endpoint"] == "manifest"
    )
    host = once.configure()
    expected = dict(list(host.base.runner.ACTIONS)[0])
    # Normalize only fresh identities; all payload and manifest structure must match.
    for key in (
        "action_id",
        "descriptor_id",
        "role",
        "branch",
    ):
        actual[key] = expected[key]
    actual["boot_admission"]["campaign_boot_binding_key"] = pack.CONFIG.nvs_boot_key
    assert actual == expected
