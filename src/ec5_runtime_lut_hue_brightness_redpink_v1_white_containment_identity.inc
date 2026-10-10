static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_hue_brightness_redpink_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT";
static constexpr const char *kSourceCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V1";
static constexpr const char *kSourceMainContractId =
    "df7ecdc4ef3d443766045e7c242cbb9109cb3f3f6415ad926c70babf7f000278";
static constexpr const char *kBuildTag =
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT_"
    "SOURCE_SAME_BOOT_V1_2026-08-27";
static constexpr const char *kContractId =
    "10867bcecf8da5a4e716bd34547d437c7a426a3b4318a64a1bce3c1963c79020";
static constexpr const char *kNvsNamespace = "rlhrpcw_v1";
static constexpr const char *kDescriptorId =
    "bfa5851856cec82f5dae397208d38591aea941ba339f10a1b9d1d86a93026b49";
static constexpr const char *kActionId =
    "3f51f507d3d7f739cf66100177223d34aca3b6cfea1d027ca84cf5eb82d94f54";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_CONTAINMENT|SHA256=bfa5851856cec82f5dae397208d38591aea941ba339f10a1b9d1d86a93026b49\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
