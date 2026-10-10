#include "ec5_runtime_lut_true_r20_partial_hold_v1_identity.inc"

namespace tr20ph1 = mf1750_runtime_lut_true_r20_partial_hold_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_TRUE_COMPLETE_R20_TUPLE_SWITCH_PARTIAL_HOLD_CLEAN_PTLW_V1_BATCH1_EVIDENCE_GATED";
static constexpr const char *kProfileSource =
    "batch1_prerequisite_gated_factory_white_plus_legacy_active_and_commented_complete_535_tuples";
static constexpr const char *kIdentityRevision =
    "runtime-lut-true-r20-partial-hold-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_DEVICE_V1";
static constexpr const char *kLayoutId = tr20ph1::kVariantKey;
static constexpr const char *kBuildTag = tr20ph1::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 true-R20 complete-tuple partial HOLD V1";
static constexpr const char *kTestId = tr20ph1::kTestId;
static constexpr const char *kCampaignId = tr20ph1::kCampaignId;
static constexpr const char *kContractId = tr20ph1::kContractId;
static constexpr const char *kQualifierPrerequisiteBundleId =
    "4f10da14df6ecf4df4631214a57ca6be0fb1b51df395bca0e407b59229b8968f";
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-true-r20-partial-hold-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-true-r20-partial-hold-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-true-r20-partial-hold-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-true-r20-partial-hold-v1-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_BATCH1_TERMINAL_FACTORY_WHITE";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"external_factory_white_anchor_required\":true,"
    "\"anchor_established_by_firmware\":false,"
    "\"factory_otp_recovery_ordinal\":4,"
    "\"batch1_evidence_requirements_id\":\""
    "51ded712517377821322a83eb1264afd7a69c08678c9a69a2c3b7f6d697ae547\","
    "\"candidate_codes\":[0,0,2],"
    "\"candidate_codes_are_not_colour_names\":true,"
    "\"candidate_mapping_status\":\"REQUIRES_BATCH1_EVIDENCE\","
    "\"historical_global_header_only_cross_lut\":false,"
    "\"complete_tuple_switched_per_runtime_action\":true,"
    "\"both_controllers_receive_same_tuple_per_runtime_action\":true,"
    "\"runtime_code7_visible_action_reachable\":false,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_code7_prestage_no_refresh\":true,"
    "\"runtime_code7_prestage_bytes_per_controller\":153600,"
    "\"runtime_code7_prestage_sha256\":"
    "\"3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd\","
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_payloads_hex\":[\"003000cf004000b701\","
    "\"013001cf00f0016701\",\"003000cf01a0021701\"],"
    "\"windows\":["
    "{\"x\":48,\"y\":64,\"width\":160,\"height\":120,"
    "\"cs1_code\":0,\"cs2_code\":0},"
    "{\"x\":304,\"y\":240,\"width\":160,\"height\":120,"
    "\"cs1_code\":0,\"cs2_code\":0},"
    "{\"x\":48,\"y\":416,\"width\":160,\"height\":120,"
    "\"cs1_code\":2,\"cs2_code\":2}],"
    "\"windows_disjoint\":true,\"cs2_position_mirrored\":false,"
    "\"runtime_actions\":["
    "{\"ordinal\":1,\"tuple\":\"active\",\"code\":0,"
    "\"cs1_tuple_sha256\":\""
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586\","
    "\"cs2_tuple_sha256\":\""
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586\"},"
    "{\"ordinal\":2,\"tuple\":\"commented\",\"code\":0,"
    "\"cs1_tuple_sha256\":\""
    "626b2770b8b807992e5e1bd7751e0142f1a19e5069b864a83680b86b4466b4fd\","
    "\"cs2_tuple_sha256\":\""
    "626b2770b8b807992e5e1bd7751e0142f1a19e5069b864a83680b86b4466b4fd\"},"
    "{\"ordinal\":3,\"tuple\":\"active\",\"code\":2,"
    "\"cs1_tuple_sha256\":\""
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586\","
    "\"cs2_tuple_sha256\":\""
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586\"}],"
    "\"runtime_target_dtm_bytes_per_controller\":9600,"
    "\"runtime_combined_dtm_bytes_per_controller\":163200,"
    "\"runtime_dtm_transport\":"
    "\"FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP\","
    "\"common_runtime_refresh_sequence\":["
    "\"PON_BUSY_COMPLETE_60S_GATE\","
    "\"DRF_00_BUSY_COMPLETE_60S_GATE\","
    "\"POF_00_BUSY_COMPLETE_60S_GATE\"],"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"command_0x86\":false,\"extra_dtm_prefix_or_suffix_byte\":false,"
    "\"runtime_lut_profile_id\":\""
    "ACTIVE_BOTH_CS_CODE0_TO_COMMENTED_BOTH_CS_CODE0_TO_"
    "ACTIVE_BOTH_CS_CODE2_CLEAN_PTLW_V1\","
    "\"complete_tuple_profile_sequence\":[\"active\","
    "\"commented\",\"active\",null],"
    "\"active_tuple_sha256\":\""
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586\","
    "\"commented_tuple_sha256\":\""
    "626b2770b8b807992e5e1bd7751e0142f1a19e5069b864a83680b86b4466b4fd\","
    "\"r20_prefix_bytes\":535,\"r21_bytes\":704,"
    "\"sequential_hold_observation_required\":true,"
    "\"automatic_camera_gate_after_each_action\":true,"
    "\"busy_idle_level_required\":1,\"ordinal_1_raw_levels_accepted\":[1],"
    "\"fresh_low_admission_forbidden\":true,"
    "\"j2_off_raw0_allowed_only_on_read_only_get_diagnostic\":true,"
    "\"later_ordinal_raw_levels_accepted\":[0,1],"
    "\"late_low_is_never_treated_as_idle\":true,"
    "\"late_low_requires_same_boot_prior_complete\":true,"
    "\"late_low_requires_prior_safe_finish_high\":true,"
    "\"late_low_requires_ram_only_firmware_eligibility\":true,"
    "\"late_pof_sleep_low_eligible_boot_default\":false,"
    "\"late_pof_sleep_low_eligible_consumed_before_qualification\":true,"
    "\"per_action_revision_qualifier_required\":true,"
    "\"unqualified_busy_zero_accepted\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"factory_otp_white_actions\":true,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":true,"
    "\"true_complete_r20_tuple_switch\":true,"
    "\"historical_global_header_only_cross_lut\":false,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"batch1_evidence_gate_required\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true";

static constexpr const char *kNvsNamespace = tr20ph1::kNvsNamespace;
static constexpr const char *kNvsKey = tr20ph1::kNvsKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-true-r20-partial-hold-v1/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kBatch1EvidenceRequirementsHeader =
    "X-EC5-Batch1-Evidence-Requirements-Id";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_BATCH1_EVIDENCE_GATED_TRUE_R20_PARTIAL_HOLD_V1_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_BATCH1_EVIDENCE_GATED_TRUE_R20_PARTIAL_HOLD_V1_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#define TR20PH1_RUNTIME_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)            \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, tr20ph1::kActions[INDEX].role, 1,                   \
        tr20ph1::kActions[INDEX].branch,                                      \
        tr20ph1::kActions[INDEX].descriptorId,                                \
        tr20ph1::kActions[INDEX].actionId, PRIOR,                             \
        tr20ph1::kActions[INDEX].frameSha256,                                 \
        tr20ph1::kActions[INDEX].cs1DtmSha256,                                \
        tr20ph1::kActions[INDEX].cs2DtmSha256,                                \
        tr20ph1::kActions[INDEX].frameFnv1a,                                  \
        tr20ph1::kActions[INDEX].cs1DtmFnv1a,                                 \
        tr20ph1::kActions[INDEX].cs2DtmFnv1a,                                 \
        {tr20ph1::kActions[INDEX].histogram[0],                               \
         tr20ph1::kActions[INDEX].histogram[1],                               \
         tr20ph1::kActions[INDEX].histogram[2],                               \
         tr20ph1::kActions[INDEX].histogram[3],                               \
         tr20ph1::kActions[INDEX].histogram[4],                               \
         tr20ph1::kActions[INDEX].histogram[5],                               \
         tr20ph1::kActions[INDEX].histogram[6],                               \
         tr20ph1::kActions[INDEX].histogram[7]}                               \
  }

static constexpr ActionDescriptor kActions[] = {
    TR20PH1_RUNTIME_ACTION(1, EpdChromaGridRole::Source, 0, nullptr),
    TR20PH1_RUNTIME_ACTION(2, EpdChromaGridRole::Mid, 1,
                           tr20ph1::kActions[0].actionId),
    TR20PH1_RUNTIME_ACTION(3, EpdChromaGridRole::Target, 2,
                           tr20ph1::kActions[1].actionId),
    {4, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
     "b86d3418fe0edda32b960b67eb56439ee7a0c392c40349eb0a9d960ab4365c20",
     "fd50aee18578d0d91a542471728883b9c3a2df24f0ed35d2298dfda71bbcd6bf",
     tr20ph1::kActions[2].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#undef TR20PH1_RUNTIME_ACTION
