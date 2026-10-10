#include "ec5_raw_p16_crossover_position_balanced_identity.inc"

namespace srp = mf1750_raw_p16_crossover_position_balanced_current;

static constexpr const char *kClassification = srp::kClassification;
static constexpr const char *kProfileSource = srp::kProfileSource;
static constexpr const char *kIdentityRevision = srp::kIdentityRevision;
static constexpr const char *kDeviceApiVersion = srp::kDeviceApiVersion;
static constexpr const char *kLayoutId = srp::kVariantKey;
static constexpr const char *kBuildTag = srp::kBuildTag;
static constexpr const char *kBootLabel = srp::kBootLabel;
static constexpr const char *kBootSummary =
    "One fixed cross-controller L535 position-balanced 4x8 full-frame atlas; "
    "runtime code 7 is an unqualified endpoint/background";
static constexpr const char *kTestId = srp::kTestId;
static constexpr const char *kCampaignId = srp::kCampaignId;
static constexpr const char *kContractId = srp::kContractId;
#if defined(MF1750_RAW_P16_CROSSOVER_T1_AC_BUILD)
#define MF1750_P16X_KIND_BASE "mf1750-ec5-raw-p16-crossover-posbal-t1-ac-v1"
#define MF1750_P16X_ROUTE_BASE "/api/ec5/raw-p16-crossover-posbal-t1-ac-v1"
#elif defined(MF1750_RAW_P16_CROSSOVER_T2_CA_BUILD)
#define MF1750_P16X_KIND_BASE "mf1750-ec5-raw-p16-crossover-posbal-t2-ca-v1"
#define MF1750_P16X_ROUTE_BASE "/api/ec5/raw-p16-crossover-posbal-t2-ca-v1"
#else
#define MF1750_P16X_KIND_BASE \
  "mf1750-ec5-raw-p16-crossover-posbal-t3-ac-repeat-v1"
#define MF1750_P16X_ROUTE_BASE \
  "/api/ec5/raw-p16-crossover-posbal-t3-ac-repeat-v1"
#endif
static constexpr const char *kVersionKind = MF1750_P16X_KIND_BASE "-version";
static constexpr const char *kManifestKind = MF1750_P16X_KIND_BASE "-manifest";
static constexpr const char *kStatusKind = MF1750_P16X_KIND_BASE "-status";
static constexpr const char *kReportKind = MF1750_P16X_KIND_BASE "-report";
static constexpr const char *kBaselineRole = srp::kBaselineRole;
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{"
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"off_white_photos_before_atlas_required\":1,"
    "\"off_retained_atlas_photos_required\":3,"
    "\"post_white_clean_visual_gate_required\":true,"
    "\"white_actions_in_campaign\":0}";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":4,\"grid_columns_per_controller\":8,"
    "\"row_codes\":[[0,1,2,3,4,5,6,7],[6,7,0,1,2,3,4,5],"
    "[5,4,7,6,1,0,3,2],[3,2,5,4,7,6,1,0]],"
    "\"grid_x0_local\":20,\"grid_y_by_row\":[44,180,316,452],"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":552,"
    "\"cell_width\":52,\"cell_height\":100,\"gap_x\":8,\"gap_y\":36,"
    "\"background_code\":7,\"border\":false,"
    "\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"controller_r20_payloads_byte_identical\":false,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"factory_otp_white_ordinals\":[],\"runtime_lut_ordinals\":[1],"
    "\"one_visible_refresh_per_action\":true,"
    "\"samples_per_code_per_controller_per_frame\":4,"
    "\"primary_codes\":[3,5,6,7],\"guard_codes\":[4],"
    "\"control_codes\":[0,1,2],\"qualified_colours\":0,"
    "\"colour_equivalence_claimed\":false,"
    "\"controller_bus_capture_claimed\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_r20_controller_parity_probe\":false,"
    "\"crossover_r20_position_balanced_probe\":true,"
    "\"position_balanced_atlas\":true,\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,"
    "\"human_observation_gate_after_every_action\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";

static constexpr const char *kNvsNamespace = srp::kNvsNamespace;
static constexpr const char *kNvsKey = srp::kNvsKey;
static constexpr const char *kNvsBootKey = srp::kNvsBootKey;
static constexpr const char *kVersionRoute = MF1750_P16X_ROUTE_BASE "/version";
static constexpr const char *kManifestRoute =
    MF1750_P16X_ROUTE_BASE "/manifest";
static constexpr const char *kStatusRoute = MF1750_P16X_ROUTE_BASE "/status";
static constexpr const char *kReportRoute = MF1750_P16X_ROUTE_BASE "/report";
static constexpr const char *kArmRoute = MF1750_P16X_ROUTE_BASE "/arm";
static constexpr const char *kExecuteRoute = MF1750_P16X_ROUTE_BASE "/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent = srp::kArmIntent;
static constexpr const char *kExecuteIntent = srp::kExecuteIntent;

static constexpr ActionDescriptor kActions[] = {{
    1,
    EpdChromaGridRole::Source,
    srp::kRole,
    srp::kRound,
    srp::kBranch,
    srp::kDescriptorId,
    srp::kActionId,
    nullptr,
    srp::kFrameSha256,
    srp::kDtmSha256,
    srp::kDtmSha256,
    srp::kFrameFnv1a,
    srp::kDtmFnv1a,
    srp::kDtmFnv1a,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};

#undef MF1750_P16X_KIND_BASE
#undef MF1750_P16X_ROUTE_BASE
