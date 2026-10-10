#if !defined(MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1_BUILD)
#error "W11 T4 V5 COMPLETE-terminal white identity requires its isolated selector"
#endif

// Fresh W11 identity derived from the sealed T4 V5 source tuple.  W11's own
// firmware artifacts remain zero/unsealed until its isolated compile succeeds.
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_p16_w11t4ca5_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W11_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5";
static constexpr const char *kSourceContractId =
    "60a66dfecc7d221e2c91fc98476d77b7c95b5956d59222b2145352e08a82fe6e";
static constexpr const char *kSourceDescriptorId =
    "143846332e6a83514330e43c4866efa7c05e5fb9d0b648ec600699704db331d0";
static constexpr const char *kSourceActionId =
    "218107d78d9e21d05b5be0b3ea59e4403313d18ea2c062a0fbf90155915f9676";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W11_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1_2026-09-01";
static constexpr const char *kContractId =
    "52aa5c78ba61abef70327a3e86df368668857e8d99e67c59c406371f757ba85f";
static constexpr const char *kNvsNamespace = "p16w11t4ca5v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w11t4ca5";
static constexpr const char *kDescriptorId =
    "076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411";
static constexpr const char *kActionId =
    "80a9fd85ff4b93ce365b699f1caa8d7835cbeeeaf738194f70cccc0f7500b595";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W11_T4_V5_COMPLETE_TERMINAL|SHA256=076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
