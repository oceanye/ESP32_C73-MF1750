"""MF1750 photo-palette targets and conservative evidence labels.

The catalogue is deliberately independent from the live runners.  It turns
the colour-search goal into a stable, machine-readable list without upgrading
an uncalibrated visual candidate into a measured colour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True)
class SeedEndpoint:
    """One observed controller/profile/code endpoint worth collecting."""

    controller: str
    profile: str
    code: int
    observed_family: str
    evidence: str


@dataclass(frozen=True)
class TargetHue:
    """One perceptual hue family in the eventual static-photo palette."""

    hue_id: str
    name_zh: str
    priority: int
    palette_slots_256: int
    initial_lightness_steps: int
    purpose: str
    current_status: str
    seeds: tuple[SeedEndpoint, ...]


ACTIVE: Final = "active-global/CS1-active535/CS2-commented535"
COMMENTED: Final = "commented-global/CS1-active535/CS2-commented535"


TARGET_HUES: Final[tuple[TargetHue, ...]] = (
    TargetHue(
        "N",
        "中性白—灰—黑",
        0,
        32,
        8,
        "照片亮度结构、阴影和高光",
        "white-and-dark-endpoints-observed; intermediate-grays-unqualified",
        (
            SeedEndpoint("CS1", ACTIVE, 7, "白", "high-confidence-observed"),
            SeedEndpoint("CS2", ACTIVE, 7, "白", "high-confidence-observed"),
            SeedEndpoint("CS1", ACTIVE, 3, "深紫棕/近黑", "visual-candidate"),
            SeedEndpoint("CS2", ACTIVE, 3, "深蓝紫/近黑", "visual-candidate"),
        ),
    ),
    TargetHue(
        "R",
        "红",
        0,
        16,
        6,
        "肤色血色、花朵和暖色主体",
        "direct-endpoint-candidate",
        (SeedEndpoint("CS2", ACTIVE, 0, "红", "visual-candidate"),),
    ),
    TargetHue(
        "RO",
        "红橙／珊瑚／鲑粉",
        0,
        18,
        8,
        "肤色血色、暖色高光以及红—橙过渡",
        "multiple-uncalibrated-candidates",
        (SeedEndpoint("CS2", ACTIVE, 2, "鲑粉", "visual-candidate"),),
    ),
    TargetHue(
        "O",
        "橙／肤色／米肤／棕",
        0,
        32,
        8,
        "人物肤色及其阴影，是静态照片最高优先级色相族",
        "multiple-uncalibrated-candidates",
        (
            SeedEndpoint("CS2", ACTIVE, 1, "米肤/淡粉", "visual-candidate"),
            SeedEndpoint("CS2", ACTIVE, 4, "棕橙", "visual-candidate"),
            SeedEndpoint("CS1", ACTIVE, 3, "深紫棕", "search-seed"),
        ),
    ),
    TargetHue(
        "Y",
        "黄",
        0,
        16,
        6,
        "高亮暖色与自然光区域",
        "direct-endpoint-candidate",
        (SeedEndpoint("CS1", ACTIVE, 2, "黄/橄榄黄", "visual-candidate"),),
    ),
    TargetHue(
        "YG",
        "黄绿／橄榄",
        1,
        16,
        8,
        "植被高光、土壤和低饱和自然色",
        "multiple-uncalibrated-candidates",
        (
            SeedEndpoint("CS1", ACTIVE, 0, "橄榄/黄绿", "visual-candidate"),
            SeedEndpoint("CS1", ACTIVE, 4, "浅黄绿", "visual-candidate"),
        ),
    ),
    TargetHue(
        "G",
        "绿",
        0,
        20,
        6,
        "植被与常见自然场景",
        "cross-controller-high-confidence-endpoint",
        (
            SeedEndpoint("CS1", ACTIVE, 6, "绿/蓝绿", "high-confidence-observed"),
            SeedEndpoint("CS2", ACTIVE, 6, "绿/蓝绿", "high-confidence-observed"),
        ),
    ),
    TargetHue(
        "T",
        "蓝绿／青绿／teal",
        1,
        16,
        6,
        "水体、植被冷色和蓝—绿过渡",
        "green-endpoint-neighbourhood-to-search",
        (
            SeedEndpoint("CS1", ACTIVE, 6, "绿/蓝绿", "search-seed"),
            SeedEndpoint("CS2", ACTIVE, 6, "绿/蓝绿", "search-seed"),
        ),
    ),
    TargetHue(
        "C",
        "青／天蓝",
        2,
        12,
        4,
        "天空高光、水体和青—蓝过渡",
        "target-only-no-qualified-endpoint",
        (
            SeedEndpoint("CS1", ACTIVE, 6, "绿/蓝绿邻域", "search-seed"),
            SeedEndpoint("CS1", ACTIVE, 5, "蓝邻域", "search-seed"),
        ),
    ),
    TargetHue(
        "B",
        "蓝",
        0,
        28,
        8,
        "天空、水体和冷色主体；包含既有Blue-1/Blue-2线索",
        "cross-controller-high-confidence-endpoint",
        (
            SeedEndpoint("CS1", ACTIVE, 5, "蓝", "high-confidence-observed"),
            SeedEndpoint("CS2", ACTIVE, 5, "蓝", "high-confidence-observed"),
        ),
    ),
    TargetHue(
        "I",
        "靛",
        1,
        14,
        6,
        "深冷色阴影和蓝紫过渡",
        "uncalibrated-dark-candidate",
        (SeedEndpoint("CS2", ACTIVE, 3, "深蓝紫", "visual-candidate"),),
    ),
    TargetHue(
        "V",
        "紫",
        2,
        12,
        4,
        "花朵、衣物和暗部色相保持",
        "uncalibrated-dark-candidate",
        (SeedEndpoint("CS1", ACTIVE, 3, "深紫棕", "visual-candidate"),),
    ),
    TargetHue(
        "M",
        "酒红／洋红／玫红",
        1,
        18,
        6,
        "人物、花朵及红—紫过渡",
        "multiple-uncalibrated-candidates",
        (
            SeedEndpoint("CS2", ACTIVE, 1, "浅粉", "search-seed"),
            SeedEndpoint("CS2", ACTIVE, 2, "鲑粉", "search-seed"),
        ),
    ),
)

ADAPTIVE_RESERVE_SLOTS: Final = 6


def validate_catalog() -> None:
    """Fail closed if the planning catalogue becomes internally ambiguous."""

    ids = [item.hue_id for item in TARGET_HUES]
    if len(ids) != len(set(ids)):
        raise ValueError("target hue IDs must be unique")
    if (
        sum(item.palette_slots_256 for item in TARGET_HUES) + ADAPTIVE_RESERVE_SLOTS
        != 256
    ):
        raise ValueError("target hue allocation must total 256 slots")
    for item in TARGET_HUES:
        if item.priority not in (0, 1, 2):
            raise ValueError(f"invalid priority for {item.hue_id}")
        if item.initial_lightness_steps < 2:
            raise ValueError(f"too few lightness steps for {item.hue_id}")
        if not item.seeds:
            raise ValueError(f"target hue {item.hue_id} has no search seed")
        for seed in item.seeds:
            if seed.controller not in ("CS1", "CS2") or not 0 <= seed.code <= 7:
                raise ValueError(f"invalid seed for {item.hue_id}")


def build_catalog() -> dict[str, object]:
    """Return the offline catalogue with explicit qualification boundaries."""

    validate_catalog()
    return {
        "schema_version": 1,
        "kind": "mf1750-static-photo-target-hue-catalog",
        "offline_only": True,
        "hardware_accessed": False,
        "spatial_dithering": False,
        "target_palette_slots": 256,
        "palette_slot_semantics": (
            "long-term hue-family allocation across lightness, chroma and small "
            "hue subclusters; not that many lightness levels"
        ),
        "initial_target_levels": sum(
            item.initial_lightness_steps for item in TARGET_HUES
        ),
        "adaptive_reserve_slots": ADAPTIVE_RESERVE_SLOTS,
        "target_hues": [asdict(item) for item in TARGET_HUES],
        "evidence_boundary": {
            "direct_transport_slots_per_controller_profile": 8,
            "confirmed_visual_base_groups": [
                "black",
                "white",
                "yellow",
                "red",
                "blue-1",
                "blue-2",
                "green",
            ],
            "qualified_unique_colours_now": None,
            "planning_estimate_stable_colours": "10-20 pending calibration",
            "history_recipes_are_not_unique_colours": True,
            "camera_or_visual_names_are_not_lab_qualification": True,
        },
        "qualification": {
            "required": [
                "uniform single-code pixels; no spatial dithering",
                "same hue family with monotonic measured CIE L*",
                "adjacent levels remain perceptibly distinct",
                "three independent refresh repetitions",
                "5 s, 60 s and 600 s persistence observations",
                "cross-controller or mirrored duplicate agreement",
                "local HOLD does not alter previously qualified patches",
                "factory-white recovery is clean",
            ],
            "measurement": "24-colour card in frame; fixed light/exposure/white balance",
        },
        "offline_screening_batches": [
            {
                "batch_id": "BLUE-BRIGHTNESS-64-V1",
                "hue_id": "B",
                "status": "live-screened-zero-visible-brightness-candidates",
                "unique_history_recipes": 64,
                "physical_controller_observations": 128,
                "qualified_brightness_levels": 0,
                "spatial_dithering": False,
                "live_screening": {
                    "protocol_actions_complete": 6,
                    "boot_nonce": "7de23beca3837011",
                    "first_target_visible_brightness_candidates": 0,
                    "identical_target_repeat_visible_brightness_candidates": 0,
                    "operator_observation": (
                        "left and right blue matrices matched and no internal "
                        "lightness difference was visible"
                    ),
                    "runtime_code7_white_recovery": "protocol-pass-visual-fail",
                    "independent_factory_otp_white_containment": "complete-pass",
                    "result_boundary": (
                        "negative only for the screened code5/history space; not "
                        "a negative result for every lightness mechanism"
                    ),
                },
                "contract_id": (
                    "3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7"
                ),
                "firmware": {
                    "bytes": 795376,
                    "sha256": (
                        "afc978e1b9ed3ccd240302a8848c2bcc4f8727f68ec70c52b026934116a93d56"
                    ),
                    "elf_bytes": 13280776,
                    "elf_sha256": (
                        "d1cddb1ce07aa427f24b188a43390117dcf806321b6fe4f5aed87520fc3ee8e7"
                    ),
                },
                "failure_containment": {
                    "fresh_identity": True,
                    "campaign_nvs_dependency": False,
                    "contract_id": (
                        "ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865"
                    ),
                    "nvs_namespace": "rlhbcw_v1",
                    "nvs_key": "used_hbcw1",
                    "firmware_bytes": 786448,
                    "firmware_sha256": (
                        "82e49e994570c9fb43ccbd7a7faa59adb55f5290d663aae2eee305250bcea12f"
                    ),
                    "elf_bytes": 13214100,
                    "elf_sha256": (
                        "d1e895623fac56586cc6029d84644580dbbf76369ba6dd09badb7ac89e616250"
                    ),
                },
            }
        ],
        "batch_order": [
            {"batch": "L0", "hues": ["N", "R", "RO", "O", "Y", "G", "B"]},
            {"batch": "L1", "hues": ["YG", "T", "I", "M"]},
            {"batch": "L2", "hues": ["C", "V"]},
        ],
    }
