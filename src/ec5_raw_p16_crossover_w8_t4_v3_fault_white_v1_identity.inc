#if !defined(MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_V1_BUILD)
#error "W8 T4 V3 fault-bound white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_p16_w8t4f_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3";
static constexpr const char *kSourceContractId =
    "e77998c71f504552cf7329b3ab1e93f7fc4346afcf8a52addeb69d5bfe1d03a7";
static constexpr const char *kSourceDescriptorId =
    "ade792564c54977026e8de0d1e70264f1854540315e601a5c6ba7239eb0420fc";
static constexpr const char *kSourceActionId =
    "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "e2531863aebd2efffe7905d6330b5632ada62bc3209e3a2740de9e0ba5f15294";
static constexpr const char *kNvsNamespace = "p16w8t4f_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w8t4f";
static constexpr const char *kDescriptorId =
    "2c99919c6dfa6aa2b020d3fede6e1528b65ef547d95652afee59639feaa4bf2a";
static constexpr const char *kActionId =
    "46f0ee263d7d6e2759d0078ba523878f29bf095bab4f9928288c9ccf76d1c348";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W8_T4_V3_FAULT|SHA256=2c99919c6dfa6aa2b020d3fede6e1528b65ef547d95652afee59639feaa4bf2a\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
