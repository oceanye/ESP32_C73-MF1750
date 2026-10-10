#!/usr/bin/env python3
"""Offline contracts for the RAW-P16 crossover position-balanced campaign.

The three atlas stages reuse the reviewed same-R20 V2 4x8 packed DTM exactly:

* ``t1-ac``: active global header, CS1 active-535, CS2 commented-535;
* ``t2-ca``: commented global header, CS1 commented-535, CS2 active-535;
* ``t3-ac-repeat``: a fresh, independently consumable repeat of ``t1-ac``.

Each atlas is one full-screen refresh.  Factory-OTP white containment is a
different firmware/campaign after every atlas.  This module is offline-only;
it never accesses a device, network, serial port, relay, or camera.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Literal


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402
from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_pack as layout  # noqa: E402


Stage = Literal["t1-ac", "t2-ca", "t3-ac-repeat"]
WhiteStage = Literal["w1-after-t1", "w2-after-t2", "w3-final-after-t3"]


@dataclass(frozen=True)
class StageConfig:
    key: Stage
    suffix: str
    global_header: str
    cs1_profile: str
    cs2_profile: str
    round: int
    repeat_of: Stage | None
    nvs_namespace: str
    nvs_key: str
    nvs_boot_key: str

    @property
    def variant_key(self) -> str:
        return f"L535_RAW_P16_CROSSOVER_POSITION_BALANCED_{self.suffix}_V1"

    @property
    def build_tag(self) -> str:
        return f"MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_{self.suffix}_V1_2026-08-30"

    @property
    def test_id(self) -> str:
        return f"EC5-RAW-P16-CROSSOVER-POSBAL-{self.suffix.replace('_', '-')}-V1"

    @property
    def campaign_id(self) -> str:
        return f"EC5_RAW_P16_CROSSOVER_POSBAL_{self.suffix}_V1"

    @property
    def route_slug(self) -> str:
        return f"raw-p16-crossover-posbal-{self.suffix.lower().replace('_', '-')}-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return f"ec5_raw_p16_crossover_posbal_{self.suffix.lower()}_v1"

    @property
    def build_root(self) -> str:
        return f"build-raw-p16-crossover-posbal-{self.suffix.lower()}-v1"


STAGES: dict[Stage, StageConfig] = {
    "t1-ac": StageConfig(
        "t1-ac",
        "T1_AC",
        "active",
        "active",
        "commented",
        1,
        None,
        "p16x_t1ac_v1",
        "cur_t1ac",
        "boot_t1ac",
    ),
    "t2-ca": StageConfig(
        "t2-ca",
        "T2_CA",
        "commented",
        "commented",
        "active",
        2,
        None,
        "p16x_t2ca_v1",
        "cur_t2ca",
        "boot_t2ca",
    ),
    "t3-ac-repeat": StageConfig(
        "t3-ac-repeat",
        "T3_AC_REPEAT",
        "active",
        "active",
        "commented",
        3,
        "t1-ac",
        "p16x_t3ar_v1",
        "cur_t3ar",
        "boot_t3ar",
    ),
}


@dataclass(frozen=True)
class WhiteConfig:
    key: WhiteStage
    suffix: str
    source_stage: Stage
    nvs_namespace: str
    nvs_key: str

    @property
    def build_tag(self) -> str:
        return f"MF1750_EC5_RAW_P16_CROSSOVER_{self.suffix}_WHITE_V1_2026-08-30"

    @property
    def test_id(self) -> str:
        return f"EC5-RAW-P16-CROSSOVER-{self.suffix.replace('_', '-')}-WHITE-V1"

    @property
    def campaign_id(self) -> str:
        return f"EC5_RAW_P16_CROSSOVER_{self.suffix}_WHITE_V1"

    @property
    def route_slug(self) -> str:
        return f"raw-p16-crossover-{self.suffix.lower().replace('_', '-')}-white-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return f"ec5_raw_p16_crossover_{self.suffix.lower()}_white_v1"

    @property
    def build_root(self) -> str:
        return f"build-raw-p16-crossover-{self.suffix.lower()}-white-v1"


WHITES: dict[WhiteStage, WhiteConfig] = {
    "w1-after-t1": WhiteConfig(
        "w1-after-t1", "W1_AFTER_T1", "t1-ac", "p16x_w1_v1", "used_w1"
    ),
    "w2-after-t2": WhiteConfig(
        "w2-after-t2", "W2_AFTER_T2", "t2-ca", "p16x_w2_v1", "used_w2"
    ),
    "w3-final-after-t3": WhiteConfig(
        "w3-final-after-t3",
        "W3_FINAL_AFTER_T3",
        "t3-ac-repeat",
        "p16x_w3_v1",
        "used_w3",
    ),
}

ARTIFACTS: dict[Stage, dict[str, int | str]] = {
    "t1-ac": {
        "bin_bytes": 799_312,
        "bin_sha256": "86ec547ae7e4f0b8d74a383efa48d14346f20275c8b9452e13274c9f0496c800",
        "elf_bytes": 13_294_400,
        "elf_sha256": "b9b6557086e730a6e322067bd687b539d1d2ac69994354f041a31aa4993bee7b",
    },
    "t2-ca": {
        "bin_bytes": 799_328,
        "bin_sha256": "2880dcbd943c99133b296e5ab9be94a426efcc953440105e1c86243dc338f931",
        "elf_bytes": 13_294_416,
        "elf_sha256": "99e59db9d5f0b68a80e8834ebe085a73a10984b7b5b6981a65dc4092736c1432",
    },
    "t3-ac-repeat": {
        "bin_bytes": 799_472,
        "bin_sha256": "ccfdb42b3d027f59a22cec8c88b31b58ce1a0cf97b4ed60ca61a6e769320cb9a",
        "elf_bytes": 13_294_608,
        "elf_sha256": "b40ec1324518b1628c4445f44a10afd67e915e6111ae49283f936c6894973f95",
    },
}

WHITE_ARTIFACTS: dict[WhiteStage, dict[str, int | str]] = {
    "w1-after-t1": {
        "bin_bytes": 786_560,
        "bin_sha256": "4dc8e0333b9a37839af18cca0c76ad36d94bd621b6cbc7510b8d775dfd3e2b81",
        "elf_bytes": 13_214_660,
        "elf_sha256": "2c39bda79e4ae20687f56c8781e0732b943c2b1e7f89d63323293b0c1dbcc30e",
    },
    "w2-after-t2": {
        "bin_bytes": 786_560,
        "bin_sha256": "76b13e8257390c6657178c305828f1725782121cc2c7991c6cc241e3119a846c",
        "elf_bytes": 13_214_660,
        "elf_sha256": "57f71aa5f481c7b2e91911b0a00fdda8a1dadb3559cb974cbd727ab2e32f71ea",
    },
    "w3-final-after-t3": {
        "bin_bytes": 786_624,
        "bin_sha256": "6ffce0798428f41205f26db7dc8e7d7da89939f6b0a775c117c3989e8e1b0804",
        "elf_bytes": 13_214_660,
        "elf_sha256": "95c223989b6c6bb62cb356d873d58b06050ad83933b354a79a4f82a3c0d18baf",
    },
}


DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-position-balanced-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_POSITION_BALANCED_CROSSOVER_R20_ENDPOINT_COMPARISON_"
    "NOT_ABSOLUTE_COLOUR_QUALIFICATION"
)
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_CROSSOVER_POSITION_BALANCED_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_ARMED_RAW_P16_CROSSOVER_POSITION_BALANCED_ACTION_ONCE"
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

SEPARATOR_CODE = layout.SEPARATOR_CODE
GRID_ROWS = layout.GRID_ROWS
GRID_COLUMNS = layout.GRID_COLUMNS
GRID_X0 = layout.GRID_X0
GRID_Y_BY_ROW = layout.GRID_Y_BY_ROW
CELL_WIDTH = layout.CELL_WIDTH
CELL_HEIGHT = layout.CELL_HEIGHT
GAP_X = layout.GAP_X
GAP_Y = layout.GAP_Y
GRID_X1_EXCLUSIVE = layout.GRID_X1_EXCLUSIVE
GRID_Y1_EXCLUSIVE = layout.GRID_Y1_EXCLUSIVE
CODE_ROWS = layout.CODE_ROWS

RUNTIME_PSR = bytes((0x5F, 0xE9))
CONTROLLER_TRES = bytes((0x02, 0x00, 0x02, 0x58))
HIDDEN_ENABLE = bytes((0x01,))
R21_SHA256 = base.R21_SHA256
PROFILE_CONSTANTS = {
    "active": {
        "global_header_sha256": (
            "48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8"
        ),
        "power_payload_sha256": (
            "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2"
        ),
        "pll_payload_sha256": (
            "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
        ),
        "r20_prefix_sha256": base.ACTIVE_R20_PREFIX_SHA256,
    },
    "commented": {
        "global_header_sha256": (
            "473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f"
        ),
        "power_payload_sha256": (
            "e571c5cf13938b4f4e12b7152ef5ac7d4970ca1d7fd5aa5568b3bf5ab5b208c9"
        ),
        "pll_payload_sha256": (
            "084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5"
        ),
        "r20_prefix_sha256": base.COMMENTED_R20_PREFIX_SHA256,
    },
}

FACTORY_WHITE_FRAME_SHA256 = (
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
)
FACTORY_WHITE_DTM_SHA256 = (
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
)
FACTORY_WHITE_FRAME_FNV1A = 0x13340DC5
FACTORY_WHITE_DTM_FNV1A = 0xB7A855C5


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _profile_part(name: str) -> dict[str, Any]:
    values = PROFILE_CONSTANTS[name]
    return {
        "name": name,
        "r20_command": "0x20",
        "r20_prefix_bytes": 535,
        "r20_prefix_sha256": values["r20_prefix_sha256"],
        "r21_command": "0x21",
        "r21_bytes": 704,
        "r21_sha256": R21_SHA256,
    }


def waveform_profile(stage: Stage | StageConfig) -> dict[str, Any]:
    cfg = STAGES[stage] if isinstance(stage, str) else stage
    global_values = PROFILE_CONSTANTS[cfg.global_header]
    cs1 = _profile_part(cfg.cs1_profile)
    cs2 = _profile_part(cfg.cs2_profile)
    seed = {
        "global_header": cfg.global_header,
        "global_header_sha256": global_values["global_header_sha256"],
        "runtime_psr_sha256": sha256_bytes(RUNTIME_PSR),
        "power_payload_sha256": global_values["power_payload_sha256"],
        "pll_payload_sha256": global_values["pll_payload_sha256"],
        "tres_sha256": sha256_bytes(CONTROLLER_TRES),
        "hidden_enable_sha256": sha256_bytes(HIDDEN_ENABLE),
        "cs1": cs1,
        "cs2": cs2,
    }
    return {
        "id": (
            f"LEGACY_{cfg.global_header.upper()}_HEADER__"
            f"CS1_{cfg.cs1_profile.upper()}535__CS2_{cfg.cs2_profile.upper()}535"
        ),
        **seed,
        "runtime_psr_command": "0x00",
        "runtime_psr_bytes": len(RUNTIME_PSR),
        "power_command": "0x01",
        "power_payload_bytes": 6,
        "pll_command": "0x30",
        "pll_payload_bytes": 1,
        "tres_command": "0x61",
        "tres_bytes": len(CONTROLLER_TRES),
        "hidden_enable_command": "0xe9",
        "hidden_enable_bytes": len(HIDDEN_ENABLE),
        "controller_payloads_byte_identical": cs1 == cs2,
        "global_tuple_id": sha256_bytes(canonical_json(seed)),
    }


def atlas_frame() -> bytes:
    """Return the exact reviewed same-R20 V2 packed DTM."""

    return layout.atlas_frame()


def controller_stream(frame: bytes, controller: int) -> bytes:
    return layout.controller_stream(frame, controller)


def payload_identity(data: bytes) -> dict[str, Any]:
    return {
        "bytes": len(data),
        "fnv1a": base.fnv1a(data),
        "sha256": sha256_bytes(data),
    }


def artifact_paths(stage: Stage | StageConfig) -> tuple[Path, Path]:
    cfg = STAGES[stage] if isinstance(stage, str) else stage
    root = REPO_ROOT / ".pio" / cfg.build_root / cfg.environment
    return root / "firmware.bin", root / "firmware.elf"


def white_artifact_paths(stage: WhiteStage | WhiteConfig) -> tuple[Path, Path]:
    cfg = WHITES[stage] if isinstance(stage, str) else stage
    root = REPO_ROOT / ".pio" / cfg.build_root / cfg.environment
    return root / "firmware.bin", root / "firmware.elf"


def _positions() -> list[dict[str, int]]:
    return [
        {
            "row": row,
            "column": column,
            "code": CODE_ROWS[row][column],
            "x": layout.cell_bounds(row, column)[0],
            "y": layout.cell_bounds(row, column)[1],
            "width": CELL_WIDTH,
            "height": CELL_HEIGHT,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]


def build_report(stage: Stage) -> dict[str, Any]:
    cfg = STAGES[stage]
    frame = atlas_frame()
    cs1 = payload_identity(controller_stream(frame, 0))
    cs2 = payload_identity(controller_stream(frame, 1))
    profile = waveform_profile(cfg)
    role = f"RAW_P16_CROSSOVER_POSITION_BALANCED_{cfg.suffix}_ATLAS"
    action: dict[str, Any] = {
        "ordinal": 1,
        "role": role,
        "driver_role": "Source",
        "round": cfg.round,
        "branch": f"{cfg.variant_key}_{role}",
        "palette_source": "L535_RUNTIME",
        "global_header": cfg.global_header,
        "profile_id": profile["id"],
        "global_tuple_id": profile["global_tuple_id"],
        "waveform_binding": profile,
        "frame": base.frame_identity(frame),
        "cs1_dtm": cs1,
        "cs2_dtm": cs2,
        "controller_dtm_byte_identical": cs1 == cs2,
        "prior_static_action_id": None,
        "repeat_of_stage": cfg.repeat_of,
        "boot_admission": {
            "campaign_boot_binding_key": cfg.nvs_boot_key,
            "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
            "required_prior_terminal_state": None,
            "required_prior_ordinal": None,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        },
    }
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-position-balanced-action-v1",
        "variant": cfg.variant_key,
        "build_tag": cfg.build_tag,
        **action,
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_ACTION_V1|"
            f"{cfg.variant_key}|1|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-raw-p16-crossover-position-balanced-contract-v1",
        "stage": cfg.key,
        "variant_key": cfg.variant_key,
        "build_tag": cfg.build_tag,
        "test_id": cfg.test_id,
        "campaign_id": cfg.campaign_id,
        "base_route": cfg.base_route,
        "nvs_namespace": cfg.nvs_namespace,
        "nvs_key": cfg.nvs_key,
        "nvs_boot_key": cfg.nvs_boot_key,
        "profile": profile,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "row_codes": [list(row) for row in CODE_ROWS],
            "positions": _positions(),
            "samples_per_code_per_controller_per_frame": 4,
            "background_code": SEPARATOR_CODE,
            "border": False,
            "cs2_position_mirrored": False,
            "same_layout_both_controllers": True,
            "controller_dtm_byte_identical": True,
            "spatial_dither": False,
        },
        "analysis_priority": {
            "primary_codes": [3, 5, 6, 7],
            "guard_codes": [4],
            "control_codes": [0, 1, 2],
            "absolute_colour_claimed": False,
            "stable_new_colour_claimed": False,
        },
        "actions": [action],
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "external_containment": {
            "outside_campaign": True,
            "factory_otp_white_before_required": True,
            "factory_otp_white_after_required": True,
            "off_white_photos_before_atlas_required": 1,
            "off_retained_atlas_photos_required": 3,
            "post_white_clean_visual_gate_required": True,
            "white_actions_in_campaign": 0,
        },
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "partial_refresh": False,
        "window_refresh": False,
        "local_hold_claimed": False,
        "controller_bus_capture_claimed": False,
        "colour_equivalence_claimed": False,
        "absolute_colour_claimed": False,
        "qualified_colours": 0,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-position-balanced-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": cfg.key,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "actions": [action],
        "contract": contract,
    }


def build_white_report(stage: WhiteStage) -> dict[str, Any]:
    cfg = WHITES[stage]
    source = build_report(cfg.source_stage)
    action_seed = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "source_campaign_id": source["contract"]["campaign_id"],
        "source_contract_id": source["contract_id"],
        "frame_sha256": FACTORY_WHITE_FRAME_SHA256,
        "cs1_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
        "cs2_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
    }
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-white-descriptor-v1",
        "build_tag": cfg.build_tag,
        **action_seed,
    }
    action = {
        **action_seed,
        "descriptor_id": sha256_bytes(canonical_json(descriptor)),
    }
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_WHITE_ACTION_V1|"
            f"{cfg.campaign_id}|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-raw-p16-crossover-white-contract-v1",
        "white_stage": cfg.key,
        "build_tag": cfg.build_tag,
        "test_id": cfg.test_id,
        "campaign_id": cfg.campaign_id,
        "source_campaign_id": source["contract"]["campaign_id"],
        "source_contract_id": source["contract_id"],
        "profile_id": "WF23_25",
        "base_route": cfg.base_route,
        "nvs_namespace": cfg.nvs_namespace,
        "nvs_key": cfg.nvs_key,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-white-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "white_stage": cfg.key,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "action": action,
        "contract": contract,
    }


def campaign_matrix() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-position-balanced-campaign-matrix",
        "offline_only": True,
        "hardware_accessed": False,
        "sequence": [
            {"kind": "atlas", "key": "t1-ac"},
            {"kind": "white", "key": "w1-after-t1"},
            {"kind": "atlas", "key": "t2-ca"},
            {"kind": "white", "key": "w2-after-t2"},
            {"kind": "atlas", "key": "t3-ac-repeat", "conditional": True},
            {"kind": "white", "key": "w3-final-after-t3", "conditional": True},
        ],
        "atlas_contracts": {key: build_report(key) for key in STAGES},
        "white_contracts": {key: build_white_report(key) for key in WHITES},
        "no_autochain": True,
        "no_retry": True,
        "no_recovery": True,
    }


def main() -> int:
    print(json.dumps(campaign_matrix(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
