static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_hue_brightness_redpink_v2_white_containment";
static constexpr const char *kCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT";
static constexpr const char *kSourceCampaignId =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2";
static constexpr const char *kSourceMainContractId =
    "1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c";
static constexpr const char *kBuildTag =
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT_"
    "SOURCE_SINGLE_APP_BOOT_V2_2026-08-27";
static constexpr const char *kContractId =
    "73f6bb1db45aa5ec570e854067cb2ad29d6994206a8816e1eadfa7fc763c2c92";
static constexpr const char *kNvsNamespace = "rlhrpcw_v2";
static constexpr const char *kDescriptorId =
    "befaffcf0dfe1562a0a4f1d54ecb256ba2a357837598a18ef76318c20079f9cc";
static constexpr const char *kActionId =
    "4c0c5e414242832925d864cd89b64f5592b516c70bb6669683645022b265f87b";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V2|PROFILE=WF23_25|ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_CONTAINMENT|SHA256=befaffcf0dfe1562a0a4f1d54ecb256ba2a357837598a18ef76318c20079f9cc\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
