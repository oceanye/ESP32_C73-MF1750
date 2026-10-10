static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_V1_2026-08-24";
static constexpr const char *kContractId =
    "5f1dd4cd9eff1c1824bab257fb2014665320d6493c64461daecb2ea3d2b56296";
static constexpr const char *kNvsNamespace = "rlph_gdw_v1";
static constexpr const char *kDescriptorId =
    "d466ee023380509cdfa4d593f73028288a4c877a93fef17162343de662cbafd5";
static constexpr const char *kActionId =
    "ff0c34170da3d20660e35dc79a57107ff42123979f38f488b9609b1292a9ba0b";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_GUARD_DIRECTION_AB_CONTAINMENT|SHA256=d466ee023380509cdfa4d593f73028288a4c877a93fef17162343de662cbafd5\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
