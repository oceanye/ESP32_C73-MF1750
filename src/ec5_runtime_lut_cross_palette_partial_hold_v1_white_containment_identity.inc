static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_cross_palette_partial_hold_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_WHITE_CONTAINMENT";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_WHITE_CONTAINMENT_2026-08-24";
static constexpr const char *kContractId =
    "3b2c350e3bd0da41b251b83233db0f983af24cb4a6275386334f65fd4cb6f899";
static constexpr const char *kNvsNamespace = "rlxphcw_v1";
static constexpr const char *kDescriptorId =
    "c1b96d538c3398160d1e839f27aeb99a2a70271a1ec623c9a2cff1936618c65c";
static constexpr const char *kActionId =
    "d6cd1f2debd3eceb9168b8b614a1937bcedf6044ba98ef84b9f99c1a9255a5eb";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_CONTAINMENT|SHA256=c1b96d538c3398160d1e839f27aeb99a2a70271a1ec623c9a2cff1936618c65c\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");

