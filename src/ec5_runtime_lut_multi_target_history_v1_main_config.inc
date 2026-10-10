#include "ec5_runtime_lut_multi_target_history_v1_identity.inc"

namespace rlmth = mf1750_runtime_lut_multi_target_history_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_L535_MULTI_TARGET_HISTORY_CANDIDATES_NOT_QUALIFIED_COLOURS";
static constexpr const char *kProfileSource =
    "factory_otp_white_and_legacy_complete_535_reference_active_and_commented_global_headers";
static constexpr const char *kIdentityRevision =
    "runtime-lut-multi-target-history-ab-ba-factory-white-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_MULTI_TARGET_HISTORY_DEVICE_V1";
static constexpr const char *kLayoutId = rlmth::kVariantKey;
static constexpr const char *kBuildTag = rlmth::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 multi-target colour-lightness history screening AB/BA";
static constexpr const char *kTestId = rlmth::kTestId;
static constexpr const char *kCampaignId = rlmth::kCampaignId;
static constexpr const char *kContractId = rlmth::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-multi-target-history-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-multi-target-history-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-multi-target-history-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-multi-target-history-v1-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"cells_per_controller_per_direction\":64,"
    "\"directional_recipes\":128,"
    "\"total_controller_observations\":256,"
    "\"duplicate_recipe_across_controllers\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"paired_controller_observations_not_waveform_identical\":true,"
    "\"controller_payload_binding\":"
    "\"CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED\","
    "\"cs2_position_mirrored\":false,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,"
    "\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,"
    "\"gap_x\":8,\"gap_y\":8,"
    "\"row_axis\":\"target_code_0_to_7\","
    "\"column_axis\":\"source_code_0_to_7\","
    "\"horizontal_comparison_group\":"
    "\"eight_adjacent_cells_same_target_different_source\","
    "\"global_header_sequence\":[null,\"active\",\"commented\","
    "\"commented\",null,\"commented\",\"active\",\"active\",null],"
    "\"palette_source_sequence\":[\"FACTORY_OTP\",\"L535_RUNTIME\","
    "\"L535_RUNTIME\",\"L535_RUNTIME\",\"FACTORY_OTP\","
    "\"L535_RUNTIME\",\"L535_RUNTIME\",\"L535_RUNTIME\","
    "\"FACTORY_OTP\"],"
    "\"factory_otp_white_ordinals\":[1,5,9],"
    "\"factory_otp_white_fill_byte\":17,"
    "\"runtime_code7_semantics\":"
    "\"unqualified_separator_and_background_transport_code_not_white\","
    "\"runtime_code7_used_as_white\":false,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"same_boot_prior_complete_required\":true,"
    "\"skip_to_factory_white_allowed\":false,"
    "\"failure_containment_kind\":"
    "\"independent_fresh_identity_factory_otp_white\","
    "\"failure_containment_campaign_id\":"
    "\"EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT\","
    "\"failure_containment_contract_id\":"
    "\"56d037a9347269a6658aa47126ccd9ed9f1e1b568b3690ab7abe77be2b385428\","
    "\"failure_containment_firmware_bytes\":786512,"
    "\"failure_containment_firmware_sha256\":"
    "\"f6e943b302e752ca3dcafaa6ce3c724e3ed9484e03472169d1f88c76b792d9f2\","
    "\"failure_containment_elf_bytes\":13214104,"
    "\"failure_containment_elf_sha256\":"
    "\"88ee12f604db97fbe435b5b23897db35f5df33594d1cc2027702fe0a32fd8180\","
    "\"failure_containment_nvs_namespace\":\"rlmthw_v1\","
    "\"failure_containment_nvs_key\":\"used_mthw1\","
    "\"failure_containment_base_route\":"
    "\"/api/ec5/runtime-lut-multi-target-history-v1/white-containment\","
    "\"failure_containment_descriptor_id\":"
    "\"aa5298e792d28a266d2e217407d8fe3ff8b320c3e0d2e101b1b5005ab7f00e36\","
    "\"failure_containment_action_id\":"
    "\"6c36c36d8b27fe7259cc2c698d20325d35f73dbacbe4f3ba924f25a97d6a7edc\","
    "\"failure_containment_campaign_nvs_dependency\":false,"
    "\"failure_containment_automatic_dispatch\":false,"
    "\"main_campaign_resume_after_containment\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,"
    "\"multi_target_history_screening\":true,"
    "\"target_repeat_stability_probe\":true,"
    "\"brightness_candidates_only\":true,"
    "\"qualified_colours\":0,"
    "\"human_observation_gate_after_every_action\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"independent_failure_containment_bound\":true,"
    "\"runtime_code7_used_as_white\":false";

static constexpr const char *kNvsNamespace = rlmth::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_mth1";
static constexpr const char *kVersionRoute =
    "/api/ec5/multi-target-history-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/multi-target-history-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/multi-target-history-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/multi-target-history-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/multi-target-history-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/multi-target-history-v1/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_MULTI_TARGET_HISTORY_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_MULTI_TARGET_HISTORY_ACTION_ONCE";

#define RLMTH_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION,  \
                     PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1,  \
                     H2, H3, H4, H5, H6, H7)                                \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,         \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,            \
        {H0, H1, H2, H3, H4, H5, H6, H7}                                    \
  }

static constexpr ActionDescriptor kActions[] = {
    RLMTH_ACTION(
        1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "84aa76944c69d73c732824f7398a6c498432461fc66df56a990c650746014baf",
        "3086cc9437813a88fb49febe0c68fbb958ab08ca9022d566c5cbbe44c6671788",
        nullptr,
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLMTH_ACTION(
        2, EpdChromaGridRole::Source, "AB_ACTIVE_SOURCE_COLUMNS",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_ACTIVE_SOURCE_COLUMNS",
        "77cb4f956342f0c612c7daf9eee97b6fe02fb268c52ff3fa276e9a23a0496e1c",
        "d4a965f907f2cf951d8be1cc80cf6c776a50621cff41a4addf8711392241ba32",
        "3086cc9437813a88fb49febe0c68fbb958ab08ca9022d566c5cbbe44c6671788",
        "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
        "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
        0x5A43EDC5UL, 0x1E3045C5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        3, EpdChromaGridRole::Mid, "AB_COMMENTED_TARGET_ROWS",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_COMMENTED_TARGET_ROWS",
        "c99f99f140d4b792e4e988bf4a517567c0edffe899a0c00b91be6deb882e36ef",
        "54767eefbcc4feabe7afa1b8fafb88130793cbf793b0c00c4bbfee64c221f8e0",
        "d4a965f907f2cf951d8be1cc80cf6c776a50621cff41a4addf8711392241ba32",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        4, EpdChromaGridRole::Target,
        "AB_COMMENTED_TARGET_ROWS_IDENTICAL_REPEAT",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_COMMENTED_TARGET_ROWS_IDENTICAL_REPEAT",
        "b2507fcdde1672c93d01ba48cedea99b9837d52cf9e87b99f88734342c8a5d2d",
        "f6e7aef63716eb4eb81d1f38ca41c5f4430784b653a5674908d887f61acd2d36",
        "54767eefbcc4feabe7afa1b8fafb88130793cbf793b0c00c4bbfee64c221f8e0",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        5, EpdChromaGridRole::White,
        "FACTORY_OTP_WHITE_DIRECTION_SEPARATOR",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_FACTORY_OTP_WHITE_DIRECTION_SEPARATOR",
        "a36466b2df2fbf8957b2bbd3dd5cdfadf6fb9812893ba8edfe723f0b356b4a7b",
        "0f23e1c05dcf01f8d460d740736fdaca7a126f2a39b465f88ae896216d27f214",
        "f6e7aef63716eb4eb81d1f38ca41c5f4430784b653a5674908d887f61acd2d36",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLMTH_ACTION(
        6, EpdChromaGridRole::ReverseSource,
        "BA_COMMENTED_SOURCE_COLUMNS",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_BA_COMMENTED_SOURCE_COLUMNS",
        "62d2400ca7b885473d10192ad6dfe679fe17c452f205462735c044e516925d9c",
        "d3bea074e004774447adc6310d5ab310ce7b92e1c4f8fc6fd12208f2689209fe",
        "0f23e1c05dcf01f8d460d740736fdaca7a126f2a39b465f88ae896216d27f214",
        "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
        "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
        0x5A43EDC5UL, 0x1E3045C5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        7, EpdChromaGridRole::ReverseTarget, "BA_ACTIVE_TARGET_ROWS",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_BA_ACTIVE_TARGET_ROWS",
        "206da743f3973446689cf82793e45de2e57172215149ed854d5398ac01694523",
        "2b1dc1ff19809de09efe0873ff15aaa1d4c39a5b11473021634c2380e88db388",
        "d3bea074e004774447adc6310d5ab310ce7b92e1c4f8fc6fd12208f2689209fe",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        8, EpdChromaGridRole::ReverseTarget,
        "BA_ACTIVE_TARGET_ROWS_IDENTICAL_REPEAT",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_BA_ACTIVE_TARGET_ROWS_IDENTICAL_REPEAT",
        "6053ff048a1d90ce265f2e0a6a8434be97760776adcbb4bd91c64d823ce05b5a",
        "7e055e8730cfdfe79210a4d7d076ea7f2f61c7a4b66ea8b16b1b6e5a1954ccaa",
        "2b1dc1ff19809de09efe0873ff15aaa1d4c39a5b11473021634c2380e88db388",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLMTH_ACTION(
        9, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY",
        "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_FACTORY_OTP_WHITE_RECOVERY",
        "faedd9c6231769a33649ab43d4379525faa3dc8f30077e492180c519c6cace08",
        "969a8f99e245babccdb248111a9f70a427142fac858ca84f1167d300e8f5488b",
        "7e055e8730cfdfe79210a4d7d076ea7f2f61c7a4b66ea8b16b1b6e5a1954ccaa",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
};

#undef RLMTH_ACTION
