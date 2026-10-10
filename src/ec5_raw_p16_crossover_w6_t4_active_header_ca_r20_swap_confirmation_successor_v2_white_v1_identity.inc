#if !defined(MF1750_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE_V1_BUILD)
#error "W6 T4 active-header CA-R20 swap successor V2 white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_p16_w6t4ca2_w1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W6_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2";
static constexpr const char *kSourceContractId =
    "8117592b5e21d4b3ff64b56e02cd74a9f7a2887c4635973de046f2e2b41f5951";
static constexpr const char *kSourceDescriptorId =
    "d6178baecf4e7ea9865fa511d31747f629c994fe98e00478e2cc0d8ad45ce7df";
static constexpr const char *kSourceActionId =
    "399a0ec181ece961b25b3de630ae1c313e2855d65d1036459f22aec16bf174b5";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W6_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE_V1_2026-08-31";
static constexpr const char *kContractId =
    "44da595488363c851c966cc8d07b57f654f3f885180ab030c1ff43ffed71039c";
static constexpr const char *kNvsNamespace = "p16w6t4ca2_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w6t4ca2";
static constexpr const char *kDescriptorId =
    "24508637d85b1df9001ecec0e0ca462ab41524cbb308d16346af0695782ae0c2";
static constexpr const char *kActionId =
    "0948fecfb177cbd63ec309654ddff1b1760c5b974b299390145cd6cef87bde9e";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2|SHA256=24508637d85b1df9001ecec0e0ca462ab41524cbb308d16346af0695782ae0c2\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
