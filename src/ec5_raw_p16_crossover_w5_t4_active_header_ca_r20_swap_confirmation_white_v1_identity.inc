#if !defined(MF1750_RAW_P16_CROSSOVER_W5_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_WHITE_V1_BUILD)
#error "W5 T4 active-header CA-R20 swap white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_p16_w5t4ca_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W5_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1";
static constexpr const char *kSourceContractId =
    "08fe1fda76a28444a0fa49b6427d2c4f31266ab06208b21376f61e4490b342e6";
static constexpr const char *kSourceDescriptorId =
    "3acce00e0b0ed8ffb14fe68d69bd393b89120152a27c957e6cc33f7370723a7f";
static constexpr const char *kSourceActionId =
    "c9a88f5b4cae0589279d3d874f81492c17d6ba4afc2f5da256fec56bec9b36a1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W5_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "7f0067e306d862cbe01b2e47d776166f9caa57fdeb46b07af65e9a42a2ffd0e7";
static constexpr const char *kNvsNamespace = "p16w5t4ca_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w5t4ca1";
static constexpr const char *kDescriptorId =
    "fe5128ce29b669874a24ae1b183517a6d1481adae5b52ee378bf985639fb8a30";
static constexpr const char *kActionId =
    "52467c4b40d29dd2706ddcb8d040676384dad7fe9aa25a246ea6b09fc86bc362";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W5_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION|SHA256=fe5128ce29b669874a24ae1b183517a6d1481adae5b52ee378bf985639fb8a30\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
