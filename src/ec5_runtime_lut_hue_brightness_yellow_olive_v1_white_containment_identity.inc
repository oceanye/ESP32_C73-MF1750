static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_hue_brightness_yellow_olive_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_V1_WHITE_CONTAINMENT";
static constexpr const char *kBuildTag =
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_V1_WHITE_CONTAINMENT_2026-08-26";
static constexpr const char *kContractId =
    "fbedf22afbe6129e2824b9726f8be16f8b949c77cf02eb49d9707166d1ec095b";
static constexpr const char *kNvsNamespace = "rlhyocw_v1";
static constexpr const char *kDescriptorId =
    "99e0f93b79a8aef9e1e3256c76aec517d0bf37be8ee1b5d3074ee83c3296c3be";
static constexpr const char *kActionId =
    "ac05c0d290e91a33e92f3eccb00bce68d35b6852bae813dfabbb6950d485d45b";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=BRIGHTNESS_YELLOW_OLIVE_OTP_WHITE_CONTAINMENT|SHA256=99e0f93b79a8aef9e1e3256c76aec517d0bf37be8ee1b5d3074ee83c3296c3be\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
