#if !defined(MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_V1_BUILD)
#error "W9 W8-ARM400 successor white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_p16_w9a400_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_SUCCESSOR_FACTORY_OTP_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE_V1";
static constexpr const char *kSourceContractId =
    "e2531863aebd2efffe7905d6330b5632ada62bc3209e3a2740de9e0ba5f15294";
static constexpr const char *kSourceDescriptorId =
    "2c99919c6dfa6aa2b020d3fede6e1528b65ef547d95652afee59639feaa4bf2a";
static constexpr const char *kSourceActionId =
    "46f0ee263d7d6e2759d0078ba523878f29bf095bab4f9928288c9ccf76d1c348";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_SUCCESSOR_FACTORY_OTP_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "33cdb659c99b89808fda9679b559b1ad76b4326e66d08274caceb7d77f2dfba5";
static constexpr const char *kNvsNamespace = "p16w9a400_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w9a400";
static constexpr const char *kDescriptorId =
    "a5f01dd65e9956109c47d4564446f3cf104085999a0b017189a3a93fcf06fe1d";
static constexpr const char *kActionId =
    "72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR|SHA256=a5f01dd65e9956109c47d4564446f3cf104085999a0b017189a3a93fcf06fe1d\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
