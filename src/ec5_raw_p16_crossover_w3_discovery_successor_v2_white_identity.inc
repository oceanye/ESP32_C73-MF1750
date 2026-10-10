#if !defined(MF1750_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2_WHITE_BUILD)
#error "W3 discovery-successor V2 white identity requires its isolated selector"
#endif

static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId =
    "ec5_raw_p16_crossover_w3_after_t2_coarse_discovery_successor_v2_white_v1";
static constexpr const char *kCampaignId =
    "EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2_WHITE_V1";
static constexpr const char *kSourceCampaignId =
    "EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V2";
static constexpr const char *kSourceContractId =
    "3a9dc65fcc4985cbb27195c340e910e7531b118cd8279a52dac9b49ce9558b77";
static constexpr const char *kSourceDescriptorId =
    "e80021a5d42db51180cd95873d48d979d70c6881c1dd8642b2c5b7299f126e65";
static constexpr const char *kSourceActionId =
    "c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f";
static constexpr const char *kBuildTag =
    "MF1750_EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2_WHITE_V1_2026-08-30";
static constexpr const char *kContractId =
    "69be4f9fa69df03d861b1de6f01e289aca492fd4ad87a5ea1ef18f99dc2516a4";
static constexpr const char *kNvsNamespace = "p16w3d_v1";
static constexpr const char *kFreshWhiteNvsKey = "used_w3d1";
static constexpr const char *kDescriptorId =
    "5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f";
static constexpr const char *kActionId =
    "b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9";

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2|SHA256=5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
