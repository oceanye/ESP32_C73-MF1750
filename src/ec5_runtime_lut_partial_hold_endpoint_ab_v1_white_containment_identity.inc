static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_RUNTIME_LUT_PTLW_YEND_AB_WHITE_CONTAINMENT_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_PTLW_YEND_AB_WHITE_CONTAINMENT_V1_2026-08-24";
static constexpr const char *kContractId =
    "f4c17d37419554a744bb59b198265b2d4c4c69b3deab124324e44610ed701dc6";
static constexpr const char *kNvsNamespace = "rlph_yew_v1";
static constexpr const char *kDescriptorId =
    "781adbb114f3322164c8d2e3bc83a7de42eb23f04076889aa6a7aff71aaf2501";
static constexpr const char *kActionId =
    "0f4a24cdc7cbdea612ae534c72cc76ffc2e9fafdc916d18b68ea9d5dafe8f80b";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_ENDPOINT_AB_CONTAINMENT|SHA256=781adbb114f3322164c8d2e3bc83a7de42eb23f04076889aa6a7aff71aaf2501\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
