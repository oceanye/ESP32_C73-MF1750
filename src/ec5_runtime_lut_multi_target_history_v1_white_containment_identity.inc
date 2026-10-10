static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_runtime_lut_multi_target_history_v1_white_containment";
static constexpr const char *kCampaignId =
    "EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT";
static constexpr const char *kBuildTag =
    "MF1750_EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT_2026-08-24";
static constexpr const char *kContractId =
    "56d037a9347269a6658aa47126ccd9ed9f1e1b568b3690ab7abe77be2b385428";
static constexpr const char *kNvsNamespace = "rlmthw_v1";
static constexpr const char *kDescriptorId =
    "aa5298e792d28a266d2e217407d8fe3ff8b320c3e0d2e101b1b5005ab7f00e36";
static constexpr const char *kActionId =
    "6c36c36d8b27fe7259cc2c698d20325d35f73dbacbe4f3ba924f25a97d6a7edc";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=MULTI_TARGET_HISTORY_OTP_WHITE_CONTAINMENT|SHA256=aa5298e792d28a266d2e217407d8fe3ff8b320c3e0d2e101b1b5005ab7f00e36\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
