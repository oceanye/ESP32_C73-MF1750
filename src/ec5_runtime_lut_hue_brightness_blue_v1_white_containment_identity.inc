static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_hue_brightness_blue_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT";
static constexpr const char *kBuildTag =
    "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT_2026-08-24";
static constexpr const char *kContractId =
    "ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865";
static constexpr const char *kNvsNamespace = "rlhbcw_v1";
static constexpr const char *kDescriptorId =
    "0ce0319922e7e332a946f70315dadac10d4baa02051b746b15af292cdbb83baf";
static constexpr const char *kActionId =
    "808d5fb9c582f944a96ea72754a7bdfb6f8996dc93cdbcf2f2f2f35e89838555";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=BRIGHTNESS_BLUE_OTP_WHITE_CONTAINMENT|SHA256=0ce0319922e7e332a946f70315dadac10d4baa02051b746b15af292cdbb83baf\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
