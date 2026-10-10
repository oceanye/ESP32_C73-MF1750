// Compile-time identity and five-action contract for the dense 8^3
// single-pixel-history campaign. Included by ec5_chroma_grid_main.cpp only in
// the isolated MF1750_SINGLE_PIXEL_CUBE_BUILD environment.

static constexpr const char *kClassification =
    "FACTORY_OTP_FULL_SCREEN_8_CUBED_SINGLE_PIXEL_HISTORY_NO_DITHER";
static constexpr const char *kProfileSource = "factory_otp";
static constexpr const char *kIdentityRevision = "single-pixel-cube-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_SINGLE_PIXEL_CUBE_DEVICE_V1";
static constexpr const char *kLayoutId =
    "dual-controller-11x24-white-gap-8-cubed-single-pixel-history-v1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_SINGLE_PIXEL_CUBE_V1_2026-08-21";
static constexpr const char *kBootLabel = "EC5 single-pixel cube";
static constexpr const char *kTestId = "EC5-SINGLE-PIXEL-CUBE-V1";
static constexpr const char *kCampaignId = "EC5_SINGLE_PIXEL_CUBE_V1";
static constexpr const char *kContractId =
    "ddbf5b9b108de76cd02a82d21a3551036c1cb71d4ff45d0b8ee5eb2337c32d2a";
static constexpr const char *kVersionKind =
    "mf1750-ec5-single-pixel-cube-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-single-pixel-cube-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-single-pixel-cube-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-single-pixel-cube-report";
static constexpr const char *kBaselineRole =
    "SINGLE_PIXEL_CUBE_WHITE_BASELINE";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"columns_per_controller\":11,"
    "\"rows\":24,\"slots_per_controller\":264,"
    "\"unique_history_count\":512,\"reference_roi_count\":16,"
    "\"roi_count\":528,\"recipe_assignment\":\"parity_balanced\","
    "\"source_code_range\":\"0..7\",\"mid_code_range\":\"0..7\","
    "\"target_code_range\":\"0..7\","
    "\"each_roi_uniform_transport_code\":true,"
    "\"grid_x0_local\":16,\"grid_x1_local_exclusive\":496,"
    "\"grid_y0\":13,\"grid_y1_exclusive\":587,"
    "\"cell_width\":40,\"cell_height\":22,"
    "\"gap_x\":4,\"gap_y\":2}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x86\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true";

static constexpr const char *kNvsNamespace = "mf1750_spc1";
static constexpr const char *kNvsKey = "cursor_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/single-pixel-cube/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/single-pixel-cube/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/single-pixel-cube/status";
static constexpr const char *kReportRoute =
    "/api/ec5/single-pixel-cube/report";
static constexpr const char *kArmRoute =
    "/api/ec5/single-pixel-cube/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/single-pixel-cube/execute";

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
    "ARM_ONE_FIXED_FACTORY_OTP_SINGLE_PIXEL_CUBE_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_FACTORY_OTP_SINGLE_PIXEL_CUBE_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr const char *kSourceFrameSha256 =
    "f472140380c1ab2630bc888d9ab0cb5e7d1f55c66f2be43b1ca89be3749927f6";
static constexpr const char *kSourceDtmSha256 =
    "eda5cc0e7bc4a947b5186f13ce6bebced9e0e3ac0b5b49c5c27cf70c44a407d4";
static constexpr const char *kMidFrameSha256 =
    "0387640a8bf2ec344199b3602580aafa29a67f5c3e830fc9101251280e8fd28a";
static constexpr const char *kMidDtmSha256 =
    "21c6eced681bc5b6068aadfd7a3fb77cc58ebcb65b161f7d8bcc61f33003c8da";
static constexpr const char *kTargetFrameSha256 =
    "f5a8a0add6fb9f955b14165ae529176512d01c99c4607d8ea2a242b56c0b0254";
static constexpr const char *kTargetCs1DtmSha256 =
    "0ac4db5cd20921c99cf87b0cbcc526a067af716d8ef805f8583d5f80d027085d";
static constexpr const char *kTargetCs2DtmSha256 =
    "5ecd431192b23f7f3d74a03b72fc436a01906db24b74c486b17091602a7136c5";

static constexpr ActionDescriptor kActions[] = {
    {1,
     EpdChromaGridRole::White,
     "SINGLE_PIXEL_CUBE_WHITE_BASELINE",
     1,
     "FACTORY_OTP_WHITE_BASELINE",
     "032ca22f88ab82e8c6088750194b2539779f0ced441ae0ef4fdcb16a7cc91623",
     "61f446dddce6754274ed350ff2932fba424919e386cdc1ce7d52689015fa3742",
     nullptr,
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {2,
     EpdChromaGridRole::Source,
     "SINGLE_PIXEL_CUBE_SOURCE",
     1,
     "ALL_8_CUBED_SOURCE_CODES_UNIFORM_ROI",
     "a32a48b92524a4efa92a992c285816d45964061c8be627737e39c483661f5c6b",
     "a219d8c626ffb6bf04774b65be366165831c71eca66410d905286b5e8133c077",
     "61f446dddce6754274ed350ff2932fba424919e386cdc1ce7d52689015fa3742",
     kSourceFrameSha256,
     kSourceDtmSha256,
     kSourceDtmSha256,
     0xBA072E05UL,
     0x5F79C545UL,
     0x5F79C545UL,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
    {3,
     EpdChromaGridRole::Mid,
     "SINGLE_PIXEL_CUBE_MID",
     1,
     "ALL_8_CUBED_MID_CODES_UNIFORM_ROI",
     "0a031f82f6ce05f7c0e697146cea296e77e6a0f7258a0f492f7ff8f18f537fc8",
     "ce498fb534cddbe4ff8e30d5730d7ff05dc4ddf4f36e909052e73692bf3eb99c",
     "a219d8c626ffb6bf04774b65be366165831c71eca66410d905286b5e8133c077",
     kMidFrameSha256,
     kMidDtmSha256,
     kMidDtmSha256,
     0xD39B6105UL,
     0x54111345UL,
     0x54111345UL,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
    {4,
     EpdChromaGridRole::Target,
     "SINGLE_PIXEL_CUBE_TARGET",
     1,
     "ALL_8_CUBED_TARGET_CODES_UNIFORM_ROI",
     "de6644ce43368a6e1726ec31cf0bf68b189596092a4bbe90b6e5d4b56fe57b2f",
     "ed5264575256d0270f83dd90e493ed7b67387a934aade778fdd2cccd877ccf31",
     "ce498fb534cddbe4ff8e30d5730d7ff05dc4ddf4f36e909052e73692bf3eb99c",
     kTargetFrameSha256,
     kTargetCs1DtmSha256,
     kTargetCs2DtmSha256,
     0xA5587785UL,
     0x64CB96E5UL,
     0xA3EFEDA5UL,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
    {5,
     EpdChromaGridRole::White,
     "SINGLE_PIXEL_CUBE_WHITE_RECOVERY",
     1,
     "FACTORY_OTP_WHITE_RECOVERY",
     "ce8e2decf94bc71d715115a23d7b907d19550963d7e7c63ed50aecac53116091",
     "414fc723670328c798867505c06c0247fc810d13a85d39bb8e171e7238f2d435",
     "ed5264575256d0270f83dd90e493ed7b67387a934aade778fdd2cccd877ccf31",
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};
