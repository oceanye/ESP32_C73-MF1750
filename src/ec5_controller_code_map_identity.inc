#if MF1750_LEGACY_REFERENCE_MATRIX == 1
#include "ec5_controller_code_map_candidate.inc"
#else
#include "ec5_pure_field_candidate.inc"
#endif

static constexpr const char *kIdentityRevision =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    "controller-specific-code-map-v1";
#else
    "pure-field-matrix-v1";
#endif
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_EMPIRICAL_H3_DEVICE_V1";
static constexpr const char *kLayoutId =
    "EC5_PURE_FIELD_2X4_PER_HALF_128X300_V1";
static constexpr const char *kGlobalHeaderProfile = PF_GLOBAL_HEADER_PROFILE;
static constexpr const char *kActionRole = "PURE_FIELD_UNIFORM_CODE_ATLAS";
static constexpr const char *kTestId =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    PF_TREAT_TEST_ID;
#else
    "EC5-PURE-FIELD-MATRIX-V1";
#endif
static constexpr const char *kBuildTag =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    PF_TREAT_BUILD_TAG;
#else
    "MF1750_EC5_PURE_FIELD_" PF_NAME "_V1_2026-08-22";
#endif
static constexpr const char *kExpectedProfileId = PF_EXPECTED_PROFILE;
static constexpr const char *kEnvironmentId =
    "ec5_controller_code_map_l535_active_v1";
static constexpr const char *kCampaignId =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    "EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_20260823_V1";
#else
    "MF1750_STAGE3_PURE_FIELD_MATRIX_20260822";
#endif
static constexpr const char *kContractId = PF_CONTRACT;
static constexpr const char *kNvsNamespace =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    PF_TREAT_NVS_NAMESPACE;
#else
    "pfm" PF_NAME_LOWER;
#endif
static constexpr const char *kDescriptorId = PF_TREAT_DESCRIPTOR;
static constexpr const char *kActionId = PF_TREAT_ACTION;
static constexpr const char *kGeneratedIncludeSha256 =
#if MF1750_LEGACY_REFERENCE_MATRIX == 1
    "cb40342fb212e232d1cfe789f60ccba9823bb0e35148f5cf916681e0c8991881";
#else
    "86981885b2d4a0eece7060d843eaed3f942cfc62c6046620130b3c83bd58290f";
#endif
static constexpr const char *kRecoveryEnvironmentId =
    "ec5_rlph_v3_containment_white";
static constexpr const char *kRecoveryPlatformioConfig =
    "platformio.runtime_lut_partial_hold_v3_containment_white.ini";
static constexpr const char *kRecoveryNvsNamespace =
    "rlphv3cw";
static constexpr const char *kRecoveryActionId = PF_WHITE_ACTION;
static constexpr const char *kRuntimePayloadLayout = PF_LAYOUT_NAME;
#if MF1750_PURE_FIELD_LAYOUT == 3
static constexpr size_t kRuntimeR20Bytes = 799;
#else
static constexpr size_t kRuntimeR20Bytes = 535;
#endif
static constexpr size_t kRuntimeR21Bytes = 704;
#if MF1750_PURE_FIELD_LAYOUT == 0 || MF1750_PURE_FIELD_LAYOUT == 3
static constexpr bool kRuntimeR21AllFf = true;
#else
static constexpr bool kRuntimeR21AllFf = false;
#endif

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=" PF_EXPECTED_PROFILE
    "|ROLE=RUNTIME|SHA256=" PF_TREAT_DESCRIPTOR "\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
