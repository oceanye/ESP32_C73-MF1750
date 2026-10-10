#if !defined(MF1750_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR_WHITE_BUILD)
#error "W2 discovery-successor white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w2_after_t2_coarse_discovery_successor_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1";
static constexpr const char *kSourceContractId =
    "464481375c0ec26034c235fcebd7091bff20f6c32b29c7cc86a9f41afbf69398";
static constexpr const char *kSourceDescriptorId =
    "4b24c2d4272b8e9c89d603154984f55d1704edf0848a447c63b9a8acbc8e7209";
static constexpr const char *kSourceActionId =
    "6ca102bdd7190cba9e524a7d8d8afa0fd6f1e57a73cb913d55aa40976912383a";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "00e1c99602f1ecef2e632647eec096f7c33a35eede00e19ebf0e255576742c4f";
static constexpr const char *kNvsNamespace = "p16w2d_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w2d1";
static constexpr const char *kDescriptorId =
    "97123851be38427788fa407a7b702c4fbbc3f94eef090db211820a0ae2b9b910";
static constexpr const char *kActionId =
    "26265cb3f26a9ae9f0b106822d163bad6cdc9776d18618726064729bcb280f6a";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR|SHA256=97123851be38427788fa407a7b702c4fbbc3f94eef090db211820a0ae2b9b910\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
