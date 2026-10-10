#if !defined(MF1750_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_WHITE_V1_BUILD)
#error "W7 T4 active-header CA-R20 swap successor V3 white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_p16_w7t4ca3_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W7_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3";
static constexpr const char *kSourceContractId =
    "e77998c71f504552cf7329b3ab1e93f7fc4346afcf8a52addeb69d5bfe1d03a7";
static constexpr const char *kSourceDescriptorId =
    "ade792564c54977026e8de0d1e70264f1854540315e601a5c6ba7239eb0420fc";
static constexpr const char *kSourceActionId =
    "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W7_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "3c323569d880fa3b64b6dbd3c3c7de6f32ba4621e82815c9a3acab379d5bbac8";
static constexpr const char *kNvsNamespace = "p16w7t4ca3_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w7t4ca3";
static constexpr const char *kDescriptorId =
    "b9fb902ec253b89e826ecd3624670058dfa29617cf49fbc6df6be04ac62ce952";
static constexpr const char *kActionId =
    "08c2ff14142186f8b39b79b60b7d1aab5904c24a2c40d436cf0c8aef06769ed4";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3|SHA256=b9fb902ec253b89e826ecd3624670058dfa29617cf49fbc6df6be04ac62ce952\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
