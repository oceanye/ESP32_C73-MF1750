#if !defined(MF1750_RAW_P16_CROSSOVER_W10_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_WHITE_V1_BUILD)
#error "W10 T4 V4 COMPLETE-terminal white identity requires its isolated selector"
#endif

// Fresh W10 identity derived from the sealed T4 V4 source tuple.
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_p16_w10t4ca4_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W10_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4";
static constexpr const char *kSourceContractId =
    "3a1c254d2beb0f06deb43781b1e3d9c5e94795c3a1354756c4b1a3ed12824150";
static constexpr const char *kSourceDescriptorId =
    "3c1ec52d3bc09ac0fde195d8b467e1b844357c3d5bdbc6ce0ea685962242d6d1";
static constexpr const char *kSourceActionId =
    "c778bc7ccd90fdb2f93abef2aef10ba05d48603bfe790e6f9b6b97dd34b9f154";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W10_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_WHITE_V1_2026-09-01";
static constexpr const char *kContractId =
    "772fb29a5f5eaab7cd7ad83f33500556ca2e071603ed24e4b5f3583ab4800daf";
static constexpr const char *kNvsNamespace = "p16w10t4ca4v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w10t4ca4";
static constexpr const char *kDescriptorId =
    "61156d1c4ce7b1ce65a20ce920ec7369c3780d0ad76a1b32b30e7cd91bfba008";
static constexpr const char *kActionId =
    "bf855ab498516d1f90dcc5022fe75231f5e855e661d5af1ed5bb4c56045d9aa0";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W10_T4_V4_COMPLETE_TERMINAL|SHA256=61156d1c4ce7b1ce65a20ce920ec7369c3780d0ad76a1b32b30e7cd91bfba008\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
